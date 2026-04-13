"""
Tests for the AI scoring logic in enrichment/handler.py.

Focuses on the two scoring-specific helpers added to the enrichment Lambda:
  - _get_users_with_resumes (with caching)
  - _score_job_for_user (Bedrock call + JSON parsing)

and the end-to-end score write path in handler().
"""
import json
import time
import pytest
import boto3
from moto import mock_aws
from unittest.mock import patch, MagicMock


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("JOBS_TABLE", "scout-jobs")
    monkeypatch.setenv("GLASSDOOR_CACHE_TABLE", "scout-glassdoor-cache")
    monkeypatch.setenv("USERS_TABLE", "scout-users")
    monkeypatch.setenv("JOB_SCORES_TABLE", "scout-job-scores")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


def _make_bedrock_response(score: int, reasoning: str) -> MagicMock:
    """Build a mock Bedrock invoke_model response."""
    body_bytes = json.dumps({
        "content": [{"text": json.dumps({"score": score, "reasoning": reasoning})}]
    }).encode()
    mock_body = MagicMock()
    mock_body.read.return_value = body_bytes
    mock_resp = MagicMock()
    mock_resp.__getitem__ = lambda self, key: mock_body if key == "body" else None
    return mock_resp


def _make_sqs_event(jobs: list) -> dict:
    """Wrap job dicts in an SQS event envelope."""
    return {
        "Records": [
            {"messageId": f"msg-{i}", "body": json.dumps(job)}
            for i, job in enumerate(jobs)
        ]
    }


# ── Unit: _get_users_with_resumes ─────────────────────────────────────────────

@mock_aws
class TestGetUsersWithResumes:
    def _make_users_table(self):
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.create_table(
            TableName="scout-users",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table.meta.client.get_waiter("table_exists").wait(TableName="scout-users")
        return table

    def test_returns_only_ready_users(self):
        table = self._make_users_table()
        table.put_item(Item={"pk": "USER#a", "resume_status": "ready", "resume_text": "text A"})
        table.put_item(Item={"pk": "USER#b", "resume_status": "processing"})
        table.put_item(Item={"pk": "USER#c", "resume_status": "ready", "resume_text": "text C"})

        # Reset module-level cache
        import enrichment.handler as h
        h._users_cache = []
        h._users_cache_time = 0.0

        result = h._get_users_with_resumes()
        pks = {u["pk"] for u in result}
        assert "USER#a" in pks
        assert "USER#c" in pks
        assert "USER#b" not in pks

    def test_returns_cached_result_within_ttl(self):
        """Second call within TTL should NOT re-scan DynamoDB."""
        self._make_users_table()

        import enrichment.handler as h
        # Seed cache with stale but non-expired data
        h._users_cache = [{"pk": "USER#cached"}]
        h._users_cache_time = time.monotonic()  # just now

        result = h._get_users_with_resumes()
        assert result == [{"pk": "USER#cached"}]

    def test_returns_empty_when_table_env_missing(self, monkeypatch):
        monkeypatch.setenv("USERS_TABLE", "")
        import enrichment.handler as h
        h._users_cache = []
        h._users_cache_time = 0.0
        result = h._get_users_with_resumes()
        assert result == []


# ── Unit: _score_job_for_user ─────────────────────────────────────────────────

class TestScoreJobForUser:
    """Tests for the Bedrock scoring helper."""

    def _job(self) -> dict:
        return {
            "title": "Cloud Security Engineer",
            "company": "Acme Corp",
            "description": "AWS, Terraform, Firewall, SIEM experience required.",
        }

    def _user(self) -> dict:
        return {"pk": "USER#u1", "resume_text": "10 years firewall engineering. AWS certified."}

    def test_returns_score_and_reasoning(self):
        import enrichment.handler as h
        mock_resp = _make_bedrock_response(85, "Strong AWS and firewall match.")
        with patch.object(h._bedrock, "invoke_model", return_value=mock_resp):
            score, reasoning = h._score_job_for_user(self._job(), self._user())
        assert score == 85
        assert "firewall" in reasoning.lower() or reasoning  # non-empty

    def test_clamps_score_to_0_100(self):
        import enrichment.handler as h
        mock_resp = _make_bedrock_response(150, "Over 100 score test.")
        with patch.object(h._bedrock, "invoke_model", return_value=mock_resp):
            score, _ = h._score_job_for_user(self._job(), self._user())
        assert score == 100

    def test_strips_markdown_fences(self):
        """Bedrock occasionally wraps JSON in ```json … ``` — must handle gracefully."""
        import enrichment.handler as h
        wrapped = "```json\n" + json.dumps({"score": 72, "reasoning": "Good match"}) + "\n```"
        body_bytes = json.dumps({"content": [{"text": wrapped}]}).encode()
        mock_body = MagicMock()
        mock_body.read.return_value = body_bytes
        mock_resp = MagicMock()
        mock_resp.__getitem__ = lambda self, key: mock_body if key == "body" else None
        with patch.object(h._bedrock, "invoke_model", return_value=mock_resp):
            score, _ = h._score_job_for_user(self._job(), self._user())
        assert score == 72

    def test_raises_on_invalid_json(self):
        import enrichment.handler as h
        body_bytes = json.dumps({"content": [{"text": "not json"}]}).encode()
        mock_body = MagicMock()
        mock_body.read.return_value = body_bytes
        mock_resp = MagicMock()
        mock_resp.__getitem__ = lambda self, key: mock_body if key == "body" else None
        with patch.object(h._bedrock, "invoke_model", return_value=mock_resp):
            with pytest.raises(Exception):
                h._score_job_for_user(self._job(), self._user())


# ── Integration: handler writes scores for new jobs ───────────────────────────

@mock_aws
class TestHandlerScoringIntegration:
    def _setup(self):
        ddb = boto3.resource("dynamodb", region_name="us-east-1")

        jobs_table = ddb.create_table(
            TableName="scout-jobs",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
                {"AttributeName": "gsi1pk", "AttributeType": "S"},
                {"AttributeName": "postedDate", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "DateIndex",
                "KeySchema": [
                    {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                    {"AttributeName": "postedDate", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )

        scores_table = ddb.create_table(
            TableName="scout-job-scores",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        users_table = ddb.create_table(
            TableName="scout-users",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        cache_table = ddb.create_table(
            TableName="scout-glassdoor-cache",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        for t in [jobs_table, scores_table, users_table, cache_table]:
            t.meta.client.get_waiter("table_exists").wait(TableName=t.name)

        return jobs_table, scores_table, users_table

    def test_score_written_for_user_with_ready_resume(self):
        jobs_table, scores_table, users_table = self._setup()
        users_table.put_item(Item={
            "pk": "USER#u1",
            "resume_status": "ready",
            "resume_text": "10 years security engineering",
        })

        import enrichment.handler as h
        # Reset user cache so the scan runs fresh
        h._users_cache = []
        h._users_cache_time = 0.0

        mock_resp = _make_bedrock_response(78, "Good security background match.")
        with patch.object(h._bedrock, "invoke_model", return_value=mock_resp):
            event = _make_sqs_event([{
                "title": "Security Engineer",
                "company": "Initech",
                "location": "Atlanta, GA",
                "job_url": "https://example.com/job/1",
                "source": "indeed",
            }])
            result = h.handler(event, None)

        assert result == {"batchItemFailures": []}
        # Score record must exist in the scores table
        scan = scores_table.scan()["Items"]
        assert len(scan) == 1
        assert scan[0]["pk"] == "USER#u1"
        assert scan[0]["score"] == 78

    def test_scoring_failure_does_not_block_job_storage(self):
        """Bedrock errors must never prevent jobs from being stored."""
        jobs_table, scores_table, users_table = self._setup()
        users_table.put_item(Item={
            "pk": "USER#u2",
            "resume_status": "ready",
            "resume_text": "Security analyst",
        })

        import enrichment.handler as h
        h._users_cache = []
        h._users_cache_time = 0.0

        with patch.object(h._bedrock, "invoke_model", side_effect=Exception("Bedrock error")):
            event = _make_sqs_event([{
                "title": "Firewall Engineer",
                "company": "Bigcorp",
                "location": "Remote",
                "job_url": "https://example.com/job/2",
                "source": "linkedin",
            }])
            result = h.handler(event, None)

        # Job still stored despite Bedrock failure
        assert result == {"batchItemFailures": []}
        items = jobs_table.scan()["Items"]
        assert len(items) == 1

        # Score table should be empty (Bedrock failed)
        scores = scores_table.scan()["Items"]
        assert len(scores) == 0

    def test_no_score_when_no_users_have_resumes(self):
        jobs_table, scores_table, users_table = self._setup()
        # No users inserted

        import enrichment.handler as h
        h._users_cache = []
        h._users_cache_time = 0.0

        event = _make_sqs_event([{
            "title": "Cloud Architect",
            "company": "Tech Co",
            "location": "Atlanta, GA",
            "job_url": "https://example.com/job/3",
            "source": "dice",
        }])
        result = h.handler(event, None)
        assert result == {"batchItemFailures": []}
        assert scores_table.scan()["Items"] == []
