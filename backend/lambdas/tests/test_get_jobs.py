"""Tests for api.get_jobs handler — GET /jobs and GET /jobs/{jobId}."""
import json
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from moto import mock_aws

from tests.conftest import make_api_event


def _make_job_item(job_hash, title="Security Engineer", company="Acme Corp",
                   location="Atlanta, GA", source="linkedin", salary_min=None,
                   rating=None, days_ago=0, contract_type=None):
    """Build a DynamoDB job item matching the Scout schema."""
    posted = (datetime.utcnow() - timedelta(days=days_ago)).date().isoformat()
    item = {
        "pk": f"JOB#{job_hash}",
        "sk": f"SOURCE#{source}#test",
        "gsi1pk": "JOB",
        "postedDate": posted,
        "job_hash": job_hash,
        "source": source,
        "title": title,
        "company": company,
        "location": location,
        "job_url": f"https://example.com/jobs/{job_hash}",
        "created_at": datetime.utcnow().isoformat(),
    }
    if salary_min is not None:
        item["salary_min"] = Decimal(str(salary_min))
    if rating is not None:
        item["rating"] = Decimal(str(rating))
    if contract_type is not None:
        item["contract_type"] = contract_type
    return item


@mock_aws
class TestGetSingleJob:
    """GET /jobs/{jobId} — fetch a single job by ID."""

    @pytest.fixture(autouse=True)
    def _setup(self, jobs_table, user_status_table):
        self.jobs_table = jobs_table
        self.status_table = user_status_table
        from api.get_jobs import handler
        self.handler = handler

    def _seed_job(self, job_hash="hash1", **kwargs):
        item = _make_job_item(job_hash, **kwargs)
        self.jobs_table.put_item(Item=item)
        return item

    def _get(self, job_id, user_sub="test-user-sub-123"):
        event = make_api_event(
            method="GET",
            path=f"/jobs/{job_id}",
            path_params={"jobId": job_id},
            user_sub=user_sub,
        )
        return self.handler(event, None)

    def test_returns_job(self):
        self._seed_job("hash1", title="Cloud Architect", company="BigCo")
        resp = self._get("hash1")
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["jobId"] == "hash1"
        assert body["roleName"] == "Cloud Architect"
        assert body["company"] == "BigCo"

    def test_not_found(self):
        resp = self._get("nonexistent")
        assert resp["statusCode"] == 404

    def test_includes_user_status(self):
        self._seed_job("hash1")
        self.status_table.put_item(Item={
            "pk": "USER#test-user-sub-123",
            "sk": "JOB#hash1",
            "status": "APPLIED",
        })
        resp = self._get("hash1")
        body = json.loads(resp["body"])
        assert body["applicationStatus"] == "APPLIED"

    def test_default_status_is_not_applied(self):
        self._seed_job("hash1")
        resp = self._get("hash1")
        body = json.loads(resp["body"])
        assert body["applicationStatus"] == "NOT_APPLIED"

    def test_missing_auth_returns_401(self):
        event = make_api_event(
            method="GET", path="/jobs/hash1",
            path_params={"jobId": "hash1"},
        )
        event["requestContext"]["authorizer"]["claims"] = {}
        resp = self.handler(event, None)
        assert resp["statusCode"] == 401


@mock_aws
class TestListJobs:
    """GET /jobs — paginated listing with filters."""

    @pytest.fixture(autouse=True)
    def _setup(self, jobs_table, user_status_table):
        self.jobs_table = jobs_table
        self.status_table = user_status_table
        from api.get_jobs import handler
        self.handler = handler

    def _seed_jobs(self, count=5, **kwargs):
        for i in range(count):
            item = _make_job_item(f"hash{i}", title=f"Role {i}", days_ago=i, **kwargs)
            self.jobs_table.put_item(Item=item)

    def _list(self, query_params=None, user_sub="test-user-sub-123"):
        event = make_api_event(
            method="GET",
            path="/jobs",
            query_params=query_params or {},
            user_sub=user_sub,
        )
        return self.handler(event, None)

    def test_returns_paginated_list(self):
        self._seed_jobs(5)
        resp = self._list({"dateRange": "30d", "pageSize": "3", "page": "1"})
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert len(body["jobs"]) == 3
        assert body["total"] == 5
        assert body["hasMore"] is True

    def test_page_two(self):
        self._seed_jobs(5)
        resp = self._list({"pageSize": "3", "page": "2"})
        body = json.loads(resp["body"])
        assert len(body["jobs"]) == 2
        assert body["hasMore"] is False

    def test_empty_results(self):
        resp = self._list()
        body = json.loads(resp["body"])
        assert body["jobs"] == []
        assert body["total"] == 0

    def test_source_filter(self):
        self._seed_jobs(3, source="linkedin")
        item = _make_job_item("indeed1", source="indeed")
        self.jobs_table.put_item(Item=item)

        resp = self._list({"sources": "indeed"})
        body = json.loads(resp["body"])
        assert body["total"] == 1
        assert body["jobs"][0]["source"] == "indeed"

    def test_status_filter(self):
        self._seed_jobs(3)
        self.status_table.put_item(Item={
            "pk": "USER#test-user-sub-123",
            "sk": "JOB#hash0",
            "status": "APPLIED",
        })
        resp = self._list({"status": "APPLIED"})
        body = json.loads(resp["body"])
        assert body["total"] == 1

    def test_salary_sort(self):
        for i, sal in enumerate([100000, 200000, 150000]):
            item = _make_job_item(f"sal{i}", salary_min=sal)
            self.jobs_table.put_item(Item=item)
        resp = self._list({"sort": "salary"})
        body = json.loads(resp["body"])
        salaries = [j["salaryMin"] for j in body["jobs"]]
        assert salaries == sorted(salaries, reverse=True)

    def test_contract_type_filter(self):
        for ct, h in [("permanent", "perm1"), ("contract", "cont1"), ("freelance", "free1")]:
            item = _make_job_item(h, title=f"{ct} role", contract_type=ct)
            self.jobs_table.put_item(Item=item)
        # Also add a job with no contract_type
        item = _make_job_item("none1", title="Unknown type")
        self.jobs_table.put_item(Item=item)

        resp = self._list({"contractTypes": "permanent"})
        body = json.loads(resp["body"])
        assert body["total"] == 1
        assert body["jobs"][0]["contractType"] == "permanent"

    def test_contract_type_filter_multiple(self):
        for ct, h in [("permanent", "perm1"), ("contract", "cont1"), ("freelance", "free1")]:
            item = _make_job_item(h, title=f"{ct} role", contract_type=ct)
            self.jobs_table.put_item(Item=item)

        resp = self._list({"contractTypes": "permanent,freelance"})
        body = json.loads(resp["body"])
        assert body["total"] == 2
        types = {j["contractType"] for j in body["jobs"]}
        assert types == {"permanent", "freelance"}

    def test_missing_auth_returns_401(self):
        event = make_api_event(method="GET", path="/jobs")
        event["requestContext"]["authorizer"]["claims"] = {}
        resp = self.handler(event, None)
        assert resp["statusCode"] == 401


@mock_aws
class TestSerializeJob:
    """Unit tests for the serialize_job helper."""

    def test_strips_job_prefix(self):
        from api.get_jobs import serialize_job
        result = serialize_job({"pk": "JOB#abc123", "title": "SRE"})
        assert result["jobId"] == "abc123"

    def test_sanitizes_nan_strings(self):
        from api.get_jobs import serialize_job
        result = serialize_job({"pk": "JOB#x", "description": "nan", "location": "None"})
        assert result["description"] is None
        assert result["location"] == ""  # falls back to ""

    def test_defaults(self):
        from api.get_jobs import serialize_job
        result = serialize_job({"pk": "JOB#x"})
        assert result["company"] == "Unknown"
        assert result["applicationStatus"] == "NOT_APPLIED"

    def test_serializes_contract_type(self):
        from api.get_jobs import serialize_job
        result = serialize_job({"pk": "JOB#x", "contract_type": "permanent"})
        assert result["contractType"] == "permanent"

    def test_contract_type_null_when_missing(self):
        from api.get_jobs import serialize_job
        result = serialize_job({"pk": "JOB#x"})
        assert result["contractType"] is None


@mock_aws
class TestGetDateRangeStart:
    """Unit tests for date range calculation."""

    def test_24h(self):
        from api.get_jobs import get_date_range_start
        result = get_date_range_start("24h")
        expected = (datetime.utcnow() - timedelta(hours=24)).date().isoformat()
        assert result == expected

    def test_7d(self):
        from api.get_jobs import get_date_range_start
        result = get_date_range_start("7d")
        expected = (datetime.utcnow() - timedelta(days=7)).date().isoformat()
        assert result == expected

    def test_default_is_30d(self):
        from api.get_jobs import get_date_range_start
        result = get_date_range_start("invalid")
        expected = (datetime.utcnow() - timedelta(days=30)).date().isoformat()
        assert result == expected
