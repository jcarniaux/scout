"""Tests for shared.response module."""
import json
from shared.response import (
    cors_response,
    error_response,
    forbidden_response,
    get_cors_headers,
    not_found_response,
    success_response,
    unauthorized_response,
)


class TestCorsHeaders:
    def test_returns_site_url_as_origin(self):
        headers = get_cors_headers()
        assert headers["Access-Control-Allow-Origin"] == "https://scout.example.com"

    def test_includes_required_methods(self):
        headers = get_cors_headers()
        for method in ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            assert method in headers["Access-Control-Allow-Methods"]

    def test_includes_auth_header(self):
        headers = get_cors_headers()
        assert "Authorization" in headers["Access-Control-Allow-Headers"]

    def test_empty_origin_when_site_url_unset(self, monkeypatch):
        monkeypatch.delenv("SITE_URL", raising=False)
        headers = get_cors_headers()
        assert headers["Access-Control-Allow-Origin"] == ""


class TestCorsResponse:
    def test_structure(self):
        resp = cors_response(200, {"key": "value"})
        assert resp["statusCode"] == 200
        assert "headers" in resp
        assert json.loads(resp["body"]) == {"key": "value"}

    def test_serializes_non_json_types(self):
        """datetime and other types should serialize via default=str."""
        from datetime import datetime

        resp = cors_response(200, {"ts": datetime(2025, 1, 1)})
        body = json.loads(resp["body"])
        assert body["ts"] == "2025-01-01 00:00:00"


class TestSuccessResponse:
    def test_default_body(self):
        resp = success_response()
        assert resp["statusCode"] == 200
        assert json.loads(resp["body"]) == {"success": True}

    def test_custom_body(self):
        resp = success_response({"jobs": []})
        assert json.loads(resp["body"]) == {"jobs": []}

    def test_custom_status_code(self):
        resp = success_response(status_code=201)
        assert resp["statusCode"] == 201


class TestErrorResponse:
    def test_default_400(self):
        resp = error_response("bad input")
        assert resp["statusCode"] == 400
        assert json.loads(resp["body"]) == {"error": "bad input"}

    def test_custom_status(self):
        resp = error_response("server error", 500)
        assert resp["statusCode"] == 500


class TestConvenienceResponses:
    def test_not_found(self):
        resp = not_found_response()
        assert resp["statusCode"] == 404

    def test_unauthorized(self):
        resp = unauthorized_response()
        assert resp["statusCode"] == 401

    def test_forbidden(self):
        resp = forbidden_response()
        assert resp["statusCode"] == 403
