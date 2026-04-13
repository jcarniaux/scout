"""Tests for api.update_status handler — PATCH /jobs/{jobId}/status."""
import json
import pytest
from decimal import Decimal
from moto import mock_aws

from tests.conftest import make_api_event


@mock_aws
class TestUpdateStatusHandler:
    """Full integration tests against moto-mocked DynamoDB."""

    @pytest.fixture(autouse=True)
    def _setup(self, user_status_table):
        """Ensure mock table exists before each test."""
        self.table = user_status_table
        # Import handler AFTER env vars are set (autouse _set_env fixture)
        from api.update_status import handler
        self.handler = handler

    def _call(self, job_id="abc123", status="APPLIED", notes="", user_sub="test-user-sub-123"):
        body = {"status": status}
        if notes:
            body["notes"] = notes
        event = make_api_event(
            method="PATCH",
            path=f"/jobs/{job_id}/status",
            body=body,
            path_params={"jobId": job_id},
            user_sub=user_sub,
        )
        return self.handler(event, None)

    # ── Happy path ──────────────────────────────────────────────────────

    def test_creates_status_record(self):
        resp = self._call(status="APPLIED")
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["status"] == "APPLIED"
        assert body["user_id"] == "USER#test-user-sub-123"
        assert body["job_id"] == "JOB#abc123"

    def test_stored_in_dynamo(self):
        self._call(status="APPLIED", notes="sent resume")
        item = self.table.get_item(
            Key={"pk": "USER#test-user-sub-123", "sk": "JOB#abc123"}
        ).get("Item")
        assert item is not None
        assert item["status"] == "APPLIED"
        assert item["notes"] == "sent resume"

    def test_overwrite_existing_status(self):
        self._call(status="APPLIED")
        self._call(status="RECRUITER_INTERVIEW")
        item = self.table.get_item(
            Key={"pk": "USER#test-user-sub-123", "sk": "JOB#abc123"}
        ).get("Item")
        assert item["status"] == "RECRUITER_INTERVIEW"

    @pytest.mark.parametrize("status", [
        "NOT_APPLIED", "NOT_INTERESTED", "APPLIED",
        "RECRUITER_INTERVIEW", "TECHNICAL_INTERVIEW",
        "OFFER_RECEIVED", "OFFER_ACCEPTED",
    ])
    def test_all_valid_statuses(self, status):
        resp = self._call(status=status)
        assert resp["statusCode"] == 200

    # ── Validation ──────────────────────────────────────────────────────

    def test_missing_status_returns_400(self):
        event = make_api_event(
            method="PATCH",
            path="/jobs/abc123/status",
            body={"notes": "no status field"},
            path_params={"jobId": "abc123"},
        )
        resp = self.handler(event, None)
        assert resp["statusCode"] == 400
        assert "Missing status" in json.loads(resp["body"])["error"]

    def test_invalid_status_returns_400(self):
        resp = self._call(status="BANANA")
        assert resp["statusCode"] == 400
        assert "Invalid status" in json.loads(resp["body"])["error"]

    def test_notes_too_long_returns_400(self):
        resp = self._call(notes="x" * 501)
        assert resp["statusCode"] == 400
        assert "500 characters" in json.loads(resp["body"])["error"]

    def test_notes_at_limit_accepted(self):
        resp = self._call(notes="x" * 500)
        assert resp["statusCode"] == 200

    def test_long_job_id_returns_400(self):
        resp = self._call(job_id="x" * 129)
        assert resp["statusCode"] == 400

    def test_missing_job_id_returns_400(self):
        event = make_api_event(
            method="PATCH",
            path="/jobs//status",
            body={"status": "APPLIED"},
            path_params={},
        )
        resp = self.handler(event, None)
        assert resp["statusCode"] == 400

    def test_invalid_json_returns_400(self):
        event = make_api_event(method="PATCH", path="/jobs/abc/status", path_params={"jobId": "abc"})
        event["body"] = "not json {"
        resp = self.handler(event, None)
        assert resp["statusCode"] == 400

    # ── Auth ────────────────────────────────────────────────────────────

    def test_missing_auth_returns_401(self):
        event = make_api_event(
            method="PATCH",
            path="/jobs/abc/status",
            body={"status": "APPLIED"},
            path_params={"jobId": "abc"},
        )
        # Remove authorizer claims
        event["requestContext"]["authorizer"]["claims"] = {}
        resp = self.handler(event, None)
        assert resp["statusCode"] == 401

    # ── Environment ─────────────────────────────────────────────────────

    def test_missing_env_var_returns_500(self, monkeypatch):
        monkeypatch.delenv("USER_STATUS_TABLE", raising=False)
        resp = self._call()
        assert resp["statusCode"] == 500
