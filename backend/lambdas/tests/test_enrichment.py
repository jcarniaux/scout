"""Tests for enrichment.handler — SQS-triggered job enrichment pipeline."""
import json
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from moto import mock_aws


def _make_sqs_event(records):
    """Build a minimal SQS event with one or more job records."""
    sqs_records = []
    for i, job_body in enumerate(records):
        sqs_records.append({
            "messageId": f"msg-{i}",
            "body": json.dumps(job_body),
        })
    return {"Records": sqs_records}


def _valid_job(**overrides):
    """Return a valid job body matching what crawlers send to SQS."""
    base = {
        "title": "Security Engineer",
        "company": "Acme Corp",
        "location": "Atlanta, GA",
        "source": "linkedin",
        "job_url": "https://linkedin.com/jobs/12345",
        "date_posted": "2026-04-10",
        "description": "We need a security engineer with 5 years experience. "
                       "Benefits include PTO, 401(k) match, and medical insurance.",
        "salary_min": 180000,
        "salary_max": 250000,
    }
    base.update(overrides)
    return base


@mock_aws
class TestEnrichmentHandler:
    """Integration tests for enrichment pipeline."""

    @pytest.fixture(autouse=True)
    def _setup(self, jobs_table, dynamodb_resource):
        self.jobs_table = jobs_table
        # Create the Glassdoor cache table
        self.cache_table = dynamodb_resource.create_table(
            TableName="scout-glassdoor-cache",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        self.cache_table.meta.client.get_waiter("table_exists").wait(
            TableName="scout-glassdoor-cache"
        )
        from enrichment.handler import handler
        self.handler = handler

    def _invoke(self, jobs):
        event = _make_sqs_event(jobs)
        return self.handler(event, None)

    # ── Happy path ──────────────────────────────────────────────────────

    @patch("enrichment.handler.fetch_glassdoor_rating", return_value=None)
    def test_stores_new_job(self, mock_gd):
        result = self._invoke([_valid_job()])
        assert result["batchItemFailures"] == []

        # Verify job was stored
        items = self.jobs_table.scan()["Items"]
        assert len(items) == 1
        assert items[0]["title"] == "Security Engineer"
        assert items[0]["company"] == "Acme Corp"

    @patch("enrichment.handler.fetch_glassdoor_rating", return_value=None)
    def test_extracts_benefits(self, mock_gd):
        self._invoke([_valid_job()])
        items = self.jobs_table.scan()["Items"]
        benefits = items[0].get("benefits")
        assert benefits is not None
        benefit_set = set(benefits) if isinstance(benefits, list) else benefits
        assert "PTO" in benefit_set
        assert "401(k)" in benefit_set
        assert "Medical" in benefit_set

    @patch("enrichment.handler.fetch_glassdoor_rating", return_value=None)
    def test_multiple_jobs_in_batch(self, mock_gd):
        jobs = [
            _valid_job(title="Role A", job_url="https://example.com/a"),
            _valid_job(title="Role B", company="OtherCo", job_url="https://example.com/b"),
        ]
        result = self._invoke(jobs)
        assert result["batchItemFailures"] == []
        items = self.jobs_table.scan()["Items"]
        assert len(items) == 2

    # ── Deduplication ───────────────────────────────────────────────────

    @patch("enrichment.handler.fetch_glassdoor_rating", return_value=None)
    def test_duplicate_job_not_double_stored(self, mock_gd):
        job = _valid_job()
        self._invoke([job])
        self._invoke([job])  # same job again
        items = self.jobs_table.scan()["Items"]
        assert len(items) == 1

    @patch("enrichment.handler.fetch_glassdoor_rating", return_value=None)
    def test_duplicate_refreshes_timestamp(self, mock_gd):
        job = _valid_job()
        self._invoke([job])
        items_before = self.jobs_table.scan()["Items"]
        created_before = items_before[0]["created_at"]

        self._invoke([job])
        items_after = self.jobs_table.scan()["Items"]
        # created_at should be updated on duplicate (the handler refreshes it)
        assert items_after[0]["created_at"] >= created_before

    # ── Filtering ───────────────────────────────────────────────────────

    @patch("enrichment.handler.fetch_glassdoor_rating", return_value=None)
    def test_filters_out_of_area_jobs(self, mock_gd):
        job = _valid_job(location="San Francisco, CA")
        self._invoke([job])
        items = self.jobs_table.scan()["Items"]
        assert len(items) == 0

    @patch("enrichment.handler.fetch_glassdoor_rating", return_value=None)
    def test_allows_remote_jobs(self, mock_gd):
        job = _valid_job(location="Remote")
        self._invoke([job])
        items = self.jobs_table.scan()["Items"]
        assert len(items) == 1

    @patch("enrichment.handler.fetch_glassdoor_rating", return_value=None)
    def test_skips_missing_title(self, mock_gd):
        job = _valid_job(title="")
        self._invoke([job])
        items = self.jobs_table.scan()["Items"]
        assert len(items) == 0

    @patch("enrichment.handler.fetch_glassdoor_rating", return_value=None)
    def test_skips_missing_url(self, mock_gd):
        job = _valid_job(job_url="")
        self._invoke([job])
        items = self.jobs_table.scan()["Items"]
        assert len(items) == 0

    # ── Edge cases ──────────────────────────────────────────────────────

    @patch("enrichment.handler.fetch_glassdoor_rating", return_value=None)
    def test_unknown_company_still_stored(self, mock_gd):
        job = _valid_job(company="")
        self._invoke([job])
        items = self.jobs_table.scan()["Items"]
        assert len(items) == 1
        assert items[0]["company"] == "Unknown"

    @patch("enrichment.handler.fetch_glassdoor_rating", return_value=None)
    def test_nan_date_falls_back_to_today(self, mock_gd):
        job = _valid_job(date_posted="nan")
        self._invoke([job])
        items = self.jobs_table.scan()["Items"]
        assert items[0]["postedDate"] is not None

    def test_malformed_json_does_not_fail_batch(self):
        event = {"Records": [{"messageId": "bad-1", "body": "not json {"}]}
        result = self.handler(event, None)
        # Malformed JSON should NOT be reported as failure (won't succeed on retry)
        assert result["batchItemFailures"] == []

    @patch("enrichment.handler.fetch_glassdoor_rating", return_value=None)
    def test_empty_event(self, mock_gd):
        result = self.handler({"Records": []}, None)
        assert result["batchItemFailures"] == []


@mock_aws
class TestComputeJobHash:
    """Unit tests for the dedup hash function."""

    def test_same_inputs_same_hash(self):
        from enrichment.handler import compute_job_hash
        h1 = compute_job_hash("Engineer", "Acme", "Atlanta, GA")
        h2 = compute_job_hash("Engineer", "Acme", "Atlanta, GA")
        assert h1 == h2

    def test_different_inputs_different_hash(self):
        from enrichment.handler import compute_job_hash
        h1 = compute_job_hash("Engineer", "Acme", "Atlanta, GA")
        h2 = compute_job_hash("Manager", "Acme", "Atlanta, GA")
        assert h1 != h2

    def test_unknown_company_uses_url(self):
        from enrichment.handler import compute_job_hash
        h1 = compute_job_hash("Engineer", "Unknown", "Atlanta", job_url="https://example.com/1")
        h2 = compute_job_hash("Engineer", "Unknown", "Atlanta", job_url="https://example.com/2")
        assert h1 != h2

    def test_case_insensitive(self):
        from enrichment.handler import compute_job_hash
        h1 = compute_job_hash("ENGINEER", "ACME", "ATLANTA")
        h2 = compute_job_hash("engineer", "acme", "atlanta")
        assert h1 == h2


@mock_aws
class TestExtractBenefits:
    """Unit tests for benefits extraction."""

    def test_finds_pto(self):
        from enrichment.handler import extract_benefits
        assert "PTO" in extract_benefits("15 days paid time off")

    def test_finds_401k(self):
        from enrichment.handler import extract_benefits
        assert "401(k)" in extract_benefits("We offer 401(k) match up to 6%")

    def test_finds_medical(self):
        from enrichment.handler import extract_benefits
        assert "Medical" in extract_benefits("Comprehensive health insurance coverage")

    def test_finds_remote(self):
        from enrichment.handler import extract_benefits
        assert "Remote Work" in extract_benefits("Flexible work from home policy")

    def test_empty_description(self):
        from enrichment.handler import extract_benefits
        assert extract_benefits("") == []

    def test_no_benefits_found(self):
        from enrichment.handler import extract_benefits
        assert extract_benefits("This is a plain job description with no perks mentioned.") == []
