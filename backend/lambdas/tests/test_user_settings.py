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
        assert body["email"] == "testuser@example.com"  # from Cognito claims
        assert body["search_preferences"]["role_queries"] == []

    def test_returns_cognito_email_over_stored(self):
        """GET always returns the Cognito email, not the DynamoDB value."""
        self.table.put_item(Item={
            "pk": "USER#test-user-sub-123",
            "user_id": "USER#test-user-sub-123",
            "email": "old@example.com",
            "daily_report": True,
            "weekly_report": False,
            "role_queries": {"Security Engineer", "Cloud Architect"},
            "salary_min": Decimal("150000"),
        })
        resp = self._get()
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["email"] == "testuser@example.com"  # Cognito, not stored
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
        assert body["email"] == "testuser@example.com"  # from Cognito claims
        assert body["daily_report"] is True
        assert body["search_preferences"]["salary_min"] == 150000

    def test_stores_cognito_email_in_dynamo(self):
        """PUT always writes the Cognito email to DynamoDB for report delivery."""
        self._put({"daily_report": True})
        item = self.table.get_item(Key={"pk": "USER#test-user-sub-123"}).get("Item")
        assert item["email"] == "testuser@example.com"

    def test_updates_existing_settings(self):
        self._put({"daily_report": False})
        resp = self._put({"daily_report": True})
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["email"] == "testuser@example.com"
        assert body["daily_report"] is True

    def test_created_at_preserved_on_update(self):
        self._put({"daily_report": True})
        item1 = self.table.get_item(Key={"pk": "USER#test-user-sub-123"}).get("Item")
        created1 = item1["created_at"]

        self._put({"daily_report": False})
        item2 = self.table.get_item(Key={"pk": "USER#test-user-sub-123"}).get("Item")
        assert item2["created_at"] == created1  # preserved by if_not_exists

    # ── Validation ──────────────────────────────────────────────────────

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
class TestCognitoEmailExtraction:
    """Unit tests for the Cognito email helper."""

    def test_extracts_email_from_claims(self):
        from api.user_settings import get_cognito_email
        event = {"requestContext": {"authorizer": {"claims": {"email": "jay@example.com"}}}}
        assert get_cognito_email(event) == "jay@example.com"

    def test_returns_none_when_missing(self):
        from api.user_settings import get_cognito_email
        assert get_cognito_email({"requestContext": {"authorizer": {"claims": {}}}}) is None
        assert get_cognito_email({"requestContext": {}}) is None
        assert get_cognito_email({}) is None
