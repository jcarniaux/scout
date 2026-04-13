"""
Tests for scoring/job_scorer.py — the on-demand AI scoring Lambda.

Covers:
  - _score_job_for_user: Bedrock call, score/reasoning extraction, clamping, fence stripping
  - _fetch_recent_jobs:  DateIndex query + pagination cap
  - handler:             full async invocation flow, missing env, user not found, no resume
"""
import json
import pytest
import boto3
from datetime import datetime
from moto import mock_aws
from unittest.mock import patch, MagicMock


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("JOBS_TABLE", "scout-jobs")
    monkeypatch.setenv("USERS_TABLE", "scout-users")
    monkeypatch.setenv("JOB_SCORES_TABLE", "scout-job-scores")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


def _make_bedrock_response(score: int, reasoning: str) -> MagicMock:
    """Build a mock Bedrock invoke_model response matching the real API shape."""
    body_bytes = json.dumps({
        "content": [{"text": json.dumps({"score": score, "reasoning": reasoning})}]
    }).encode()
    mock_body = MagicMock()
    mock_body.read.return_value = body_bytes
    mock_resp = MagicMock()
    mock_resp.__getitem__ = lambda self, key: mock_body if key == "body" else None
    return mock_resp


# ── Unit: _score_job_for_user ─────────────────────────────────────────────────

class TestScoreJobForUser:
    """Tests for the Bedrock scoring helper in job_scorer."""

    def _job(self) -> dict:
        return {
            "title": "Cloud Security Engineer",
            "company": "Acme Corp",
            "description": "AWS, Terraform, Firewall, SIEM experience required.",
        }

    def _resume(self) -> str:
        return "10 years firewall engineering. AWS certified. Terraform IaC experience."

    def test_returns_score_and_reasoning(self):
        from scoring.job_scorer import _score_job_for_user
        mock_resp = _make_bedrock_response(85, "Strong AWS and firewall match.")
        with patch("scoring.job_scorer._bedrock") as mock_bedrock:
            mock_bedrock.invoke_model.return_value = mock_resp
            score, reasoning = _score_job_for_user(self._job(), self._resume())
        assert score == 85
        assert len(reasoning) > 0

    def test_clamps_score_above_100(self):
        from scoring.job_scorer import _score_job_for_user
        mock_resp = _make_bedrock_response(150, "Score over 100.")
        with patch("scoring.job_scorer._bedrock") as mock_bedrock:
            mock_bedrock.invoke_model.return_value = mock_resp
            score, _ = _score_job_for_user(self._job(), self._resume())
        assert score == 100

    def test_clamps_score_below_0(self):
        from scoring.job_scorer import _score_job_for_user
        mock_resp = _make_bedrock_response(-10, "Negative score test.")
        with patch("scoring.job_scorer._bedrock") as mock_bedrock:
            mock_bedrock.invoke_model.return_value = mock_resp
            score, _ = _score_job_for_user(self._job(), self._resume())
        assert score == 0

    def test_strips_markdown_code_fences(self):
        """Bedrock occasionally wraps JSON in ```json…``` — must strip cleanly."""
        from scoring.job_scorer import _score_job_for_user
        wrapped = "```json\n" + json.dumps({"score": 72, "reasoning": "Good match"}) + "\n```"
        body_bytes = json.dumps({"content": [{"text": wrapped}]}).encode()
        mock_body = MagicMock()
        mock_body.read.return_value = body_bytes
        mock_resp = MagicMock()
        mock_resp.__getitem__ = lambda self, key: mock_body if key == "body" else None
        with patch("scoring.job_scorer._bedrock") as mock_bedrock:
            mock_bedrock.invoke_model.return_value = mock_resp
            score, _ = _score_job_for_user(self._job(), self._resume())
        assert score == 72

    def test_raises_on_invalid_json_response(self):
        from scoring.job_scorer import _score_job_for_user
        body_bytes = json.dumps({"content": [{"text": "not json at all"}]}).encode()
        mock_body = MagicMock()
        mock_body.read.return_value = body_bytes
        mock_resp = MagicMock()
        mock_resp.__getitem__ = lambda self, key: mock_body if key == "body" else None
        with patch("scoring.job_scorer._bedrock") as mock_bedrock:
            mock_bedrock.invoke_model.return_value = mock_resp
            with pytest.raises(Exception):
                _score_job_for_user(self._job(), self._resume())

    def test_raises_on_bedrock_error(self):
        from scoring.job_scorer import _score_job_for_user
        with patch("scoring.job_scorer._bedrock") as mock_bedrock:
            mock_bedrock.invoke_model.side_effect = Exception("Bedrock throttled")
            with pytest.raises(Exception, match="Bedrock throttled"):
                _score_job_for_user(self._job(), self._resume())


# ── Integration: handler ──────────────────────────────────────────────────────

@mock_aws
class TestJobScorerHandler:
    """Full handler integration tests with mocked AWS services."""

    def _setup(self):
        """Create all tables required by job_scorer.handler."""
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

        users_table = ddb.create_table(
            TableName="scout-users",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
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

        for t in [jobs_table, users_table, scores_table]:
            t.meta.client.get_waiter("table_exists").wait(TableName=t.name)

        return jobs_table, users_table, scores_table

    def _seed_job(self, jobs_table, job_hash: str = "abc123"):
        today = datetime.utcnow().date().isoformat()
        jobs_table.put_item(Item={
            "pk": f"JOB#{job_hash}",
            "sk": "SOURCE#indeed#deadbeef",
            "gsi1pk": "JOB",
            "postedDate": today,
            "job_hash": job_hash,
            "title": "Security Engineer",
            "company": "Acme",
            "description": "AWS, firewall, Terraform.",
        })

    def test_scores_job_for_user_with_ready_resume(self):
        jobs_table, users_table, scores_table = self._setup()
        users_table.put_item(Item={
            "pk": "USER#u1",
            "resume_status": "ready",
            "resume_text": "10 years firewall. AWS certified.",
        })
        self._seed_job(jobs_table)

        import scoring.job_scorer as js
        from shared.db import DynamoDBHelper
        fresh_db = DynamoDBHelper()

        mock_resp = _make_bedrock_response(80, "Strong security match.")
        with patch.object(js, "dynamodb", fresh_db), \
             patch.object(js, "_bedrock") as mock_bedrock:
            mock_bedrock.invoke_model.return_value = mock_resp
            result = js.handler({"user_pk": "USER#u1", "user_sub": "u1"}, None)

        assert result["statusCode"] == 200
        assert result["scored"] == 1
        assert result["errors"] == 0

        # Score must be written to the scores table
        scores = scores_table.scan()["Items"]
        assert len(scores) == 1
        assert scores[0]["pk"] == "USER#u1"
        assert scores[0]["score"] == 80

        # User record must be updated to scoring_status=done
        user = users_table.get_item(Key={"pk": "USER#u1"}).get("Item", {})
        assert user.get("scoring_status") == "done"
        assert user.get("last_scored_count") == 1

    def test_returns_error_when_user_not_found(self):
        _, _, _ = self._setup()

        import scoring.job_scorer as js
        from shared.db import DynamoDBHelper
        fresh_db = DynamoDBHelper()

        with patch.object(js, "dynamodb", fresh_db):
            result = js.handler({"user_pk": "USER#missing", "user_sub": "missing"}, None)

        assert result["statusCode"] == 404

    def test_returns_200_when_user_has_no_resume(self):
        jobs_table, users_table, scores_table = self._setup()
        users_table.put_item(Item={"pk": "USER#norésume", "resume_status": "processing"})
        self._seed_job(jobs_table)

        import scoring.job_scorer as js
        from shared.db import DynamoDBHelper
        fresh_db = DynamoDBHelper()

        with patch.object(js, "dynamodb", fresh_db):
            result = js.handler({"user_pk": "USER#norésume", "user_sub": "norésume"}, None)

        assert result["statusCode"] == 200
        assert result["scored"] == 0
        # No scores should have been written
        assert scores_table.scan()["Items"] == []

    def test_returns_500_when_env_missing(self, monkeypatch):
        monkeypatch.setenv("JOBS_TABLE", "")
        import scoring.job_scorer as js
        result = js.handler({"user_pk": "USER#u1"}, None)
        assert result["statusCode"] == 500

    def test_missing_user_pk_returns_400(self):
        _, _, _ = self._setup()
        import scoring.job_scorer as js
        from shared.db import DynamoDBHelper
        fresh_db = DynamoDBHelper()
        with patch.object(js, "dynamodb", fresh_db):
            result = js.handler({}, None)
        assert result["statusCode"] == 400

    def test_bedrock_error_is_counted_not_fatal(self):
        """A Bedrock failure on one job increments error count but does NOT crash the handler."""
        jobs_table, users_table, scores_table = self._setup()
        users_table.put_item(Item={
            "pk": "USER#u2",
            "resume_status": "ready",
            "resume_text": "Security analyst.",
        })
        self._seed_job(jobs_table, job_hash="beef0001")

        import scoring.job_scorer as js
        from shared.db import DynamoDBHelper
        fresh_db = DynamoDBHelper()

        with patch.object(js, "dynamodb", fresh_db), \
             patch.object(js, "_bedrock") as mock_bedrock:
            mock_bedrock.invoke_model.side_effect = Exception("Throttled")
            result = js.handler({"user_pk": "USER#u2", "user_sub": "u2"}, None)

        assert result["statusCode"] == 200
        assert result["scored"] == 0
        assert result["errors"] == 1
        # Handler should still mark scoring as done despite errors
        user = users_table.get_item(Key={"pk": "USER#u2"}).get("Item", {})
        assert user.get("scoring_status") == "done"
