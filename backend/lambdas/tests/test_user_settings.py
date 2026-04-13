"""Tests for api.user_settings handler — GET & PUT /user/settings."""
import json
import pytest
from decimal import Decimal
from moto import mock_aws

from tests.conftest import make_api_event


@mock_aws
class TestGetSettings:
    """GET /user/settings — read user preferences."""

    @pytest.fixture(autouse=True)
    def _setup(self, users_table):
        self.table = users_table
        from api.user_settings import handler
        self.handler = handler

    def _get(self, user_sub="test-user-sub-123"):
        event = make_api_event(method="GET", path="/user/settings", user_sub=user_sub)
        return self.handler(event, None)

    def test_returns_defaults_for_new_user(self):
        resp = self._get()
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["daily_report"] is False
        assert body["weekly_report"] is False
        assert body["email"] is None
        assert body["search_preferences"]["role_queries"] == []

    def test_returns_stored_settings(self):
        self.table.put_item(Item={
            "pk": "USER#test-user-sub-123",
            "user_id": "USER#test-user-sub-123",
            "email": "jay@example.com",
            "daily_report": True,
            "weekly_report": False,
            "role_queries": {"Security Engineer", "Cloud Architect"},
            "salary_min": Decimal("150000"),
        })
        resp = self._get()
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["email"] == "jay@example.com"
        assert body["daily_report"] is True
        assert body["search_preferences"]["salary_min"] == 150000

    def test_missing_auth_returns_401(self):
        event = make_api_event(method="GET", path="/user/settings")
        event["requestContext"]["authorizer"]["claims"] = {}
        resp = self.handler(event, None)
        assert resp["statusCode"] == 401


@mock_aws
class TestPutSettings:
    """PUT /user/settings — update user preferences."""

    @pytest.fixture(autouse=True)
    def _setup(self, users_table):
        self.table = users_table
        from api.user_settings import handler
        self.handler = handler

    def _put(self, body, user_sub="test-user-sub-123"):
        event = make_api_event(
            method="PUT",
            path="/user/settings",
            body=body,
            user_sub=user_sub,
        )
        return self.handler(event, None)

    # ── Happy path ──────────────────────────────────────────────────────

    def test_creates_new_user_settings(self):
        resp = self._put({
            "email": "jay@example.com",
            "daily_report": True,
            "weekly_report": False,
            "search_preferences": {
                "role_queries": ["Security Engineer"],
                "locations": [{"location": "Atlanta, GA", "remote": True}],
                "salary_min": 150000,
                "salary_max": 250000,
            },
        })
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["email"] == "jay@example.com"
        assert body["daily_report"] is True
        assert body["search_preferences"]["salary_min"] == 150000

    def test_updates_existing_settings(self):
        # Create initial settings
        self._put({"email": "old@example.com", "daily_report": False})
        # Update
        resp = self._put({"email": "new@example.com", "daily_report": True})
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["email"] == "new@example.com"
        assert body["daily_report"] is True

    def test_created_at_preserved_on_update(self):
        self._put({"daily_report": True})
        item1 = self.table.get_item(Key={"pk": "USER#test-user-sub-123"}).get("Item")
        created1 = item1["created_at"]

        self._put({"daily_report": False})
        item2 = self.table.get_item(Key={"pk": "USER#test-user-sub-123"}).get("Item")
        assert item2["created_at"] == created1  # preserved by if_not_exists

    # ── Validation ──────────────────────────────────────────────────────

    def test_invalid_email_returns_400(self):
        resp = self._put({"email": "not-an-email"})
        assert resp["statusCode"] == 400
        assert "email" in json.loads(resp["body"])["error"].lower()

    def test_email_too_long_returns_400(self):
        resp = self._put({"email": "a" * 250 + "@b.co"})
        assert resp["statusCode"] == 400

    def test_role_queries_not_list_returns_400(self):
        resp = self._put({"search_preferences": {"role_queries": "not a list"}})
        assert resp["statusCode"] == 400

    def test_too_many_role_queries_returns_400(self):
        resp = self._put({"search_preferences": {"role_queries": [f"role{i}" for i in range(51)]}})
        assert resp["statusCode"] == 400

    def test_locations_not_list_returns_400(self):
        resp = self._put({"search_preferences": {"locations": "not a list"}})
        assert resp["statusCode"] == 400

    def test_too_many_locations_returns_400(self):
        resp = self._put({"search_preferences": {"locations": [{"location": f"city{i}"} for i in range(51)]}})
        assert resp["statusCode"] == 400

    def test_invalid_json_returns_400(self):
        event = make_api_event(method="PUT", path="/user/settings")
        event["body"] = "{bad json"
        resp = self.handler(event, None)
        assert resp["statusCode"] == 400


@mock_aws
class TestSettingsDispatcher:
    """Handler routes to correct sub-handler based on HTTP method."""

    @pytest.fixture(autouse=True)
    def _setup(self, users_table):
        from api.user_settings import handler
        self.handler = handler

    def test_unsupported_method_returns_405(self):
        event = make_api_event(method="DELETE", path="/user/settings")
        resp = self.handler(event, None)
        assert resp["statusCode"] == 405


@mock_aws
class TestValidateEmail:
    """Unit tests for the email validation helper."""

    def test_valid_emails(self):
        from api.user_settings import validate_email
        assert validate_email("user@example.com") is True
        assert validate_email("first.last@company.co") is True
        assert validate_email("user+tag@example.com") is True

    def test_invalid_emails(self):
        from api.user_settings import validate_email
        assert validate_email("no-at-sign") is False
        assert validate_email("@missing-local.com") is False
        assert validate_email("user@") is False
        assert validate_email("user@.com") is False
