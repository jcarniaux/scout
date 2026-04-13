"""
Tests for the resume_parser Lambda.

Uses moto to mock S3 and DynamoDB. Uses minimal in-memory PDFs
(created with reportlab or a raw byte fixture) so we don't need real PDF files.
"""
import io
import pytest
import boto3
from moto import mock_aws
from unittest.mock import patch


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _aws_env(monkeypatch):
    """Inject Lambda env vars needed by resume_parser."""
    monkeypatch.setenv("USERS_TABLE", "scout-users")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


def _make_s3_event(bucket: str, key: str) -> dict:
    """Build a minimal S3 ObjectCreated event."""
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": key},
                }
            }
        ]
    }


def _minimal_pdf_bytes(text: str = "Software Engineer with Python and AWS experience.") -> bytes:
    """
    Build a tiny but real single-page PDF using reportlab if available,
    falling back to a hardcoded minimal PDF byte string.

    The fallback is a 1-page PDF that says "Hello" — enough for pdfminer
    to extract at least some text so extraction tests can pass.
    """
    try:
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(100, 750, text)
        c.save()
        return buf.getvalue()
    except ImportError:
        # Minimal hand-crafted PDF (contains the word "Hello")
        return (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
            b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
            b"4 0 obj<</Length 44>>\nstream\nBT /F1 12 Tf 100 700 Td (Hello) Tj ET\nendstream\nendobj\n"
            b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
            b"xref\n0 6\n0000000000 65535 f \n"
            b"0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
            b"0000000266 00000 n \n0000000360 00000 n \n"
            b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n441\n%%EOF\n"
        )


# ── Unit tests: _user_sub_from_key ────────────────────────────────────────────

class TestUserSubFromKey:
    def test_normal_key(self):
        from scoring.resume_parser import _user_sub_from_key
        assert _user_sub_from_key("resumes/abc-123/resume.pdf") == "abc-123"

    def test_url_encoded_key(self):
        from scoring.resume_parser import _user_sub_from_key
        assert _user_sub_from_key("resumes/user%2Bsub/resume.pdf") == "user+sub"

    def test_invalid_key_raises(self):
        from scoring.resume_parser import _user_sub_from_key
        with pytest.raises(ValueError):
            _user_sub_from_key("uploads/abc/resume.pdf")

    def test_too_short_raises(self):
        from scoring.resume_parser import _user_sub_from_key
        with pytest.raises(ValueError):
            _user_sub_from_key("resumes/onlyone")


# ── Unit tests: _extract_text_from_pdf ───────────────────────────────────────

class TestExtractText:
    def test_returns_string(self):
        from scoring.resume_parser import _extract_text_from_pdf
        pdf = _minimal_pdf_bytes()
        result = _extract_text_from_pdf(pdf)
        assert isinstance(result, str)

    def test_truncates_to_max_chars(self):
        from scoring.resume_parser import _extract_text_from_pdf, MAX_RESUME_CHARS
        pdf = _minimal_pdf_bytes()
        result = _extract_text_from_pdf(pdf)
        assert len(result) <= MAX_RESUME_CHARS

    def test_raises_on_empty_bytes(self):
        from scoring.resume_parser import _extract_text_from_pdf
        with pytest.raises(Exception):
            _extract_text_from_pdf(b"not a pdf")


# ── Integration tests: handler ────────────────────────────────────────────────

@mock_aws
class TestHandler:
    """Full handler integration tests with mocked AWS services."""

    def _setup(self):
        """Create required AWS resources inside the mock context."""
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.create_table(
            TableName="scout-users",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table.meta.client.get_waiter("table_exists").wait(TableName="scout-users")

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="scout-resumes-test")
        return table, s3

    def test_successful_parse_sets_ready_status(self):
        table, s3 = self._setup()

        pdf_bytes = _minimal_pdf_bytes("Python AWS DevOps Engineer resume")
        s3.put_object(Bucket="scout-resumes-test", Key="resumes/user-001/resume.pdf", Body=pdf_bytes)

        # Both the S3 client and DynamoDBHelper are created at module level before the
        # mock context activates, so we patch them with fresh moto-backed instances.
        import scoring.resume_parser as rp
        from shared.db import DynamoDBHelper
        fresh_db = DynamoDBHelper()
        with patch.object(rp, "_s3", s3), patch.object(rp, "_dynamodb", fresh_db):
            event = _make_s3_event("scout-resumes-test", "resumes/user-001/resume.pdf")
            result = rp.handler(event, None)

        assert result["statusCode"] == 200
        assert result["processed"] == 1
        assert result["errors"] == 0

        item = table.get_item(Key={"pk": "USER#user-001"}).get("Item", {})
        assert item.get("resume_status") == "ready"
        assert "resume_text" in item
        assert item.get("resume_filename") == "resume.pdf"

    def _patched_handler(self, s3_client):
        """Return a context manager that patches both module-level AWS clients."""
        import scoring.resume_parser as rp
        from shared.db import DynamoDBHelper
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            fresh_db = DynamoDBHelper()
            with patch.object(rp, "_s3", s3_client), patch.object(rp, "_dynamodb", fresh_db):
                yield rp

        return _ctx()

    def test_empty_pdf_sets_error_status(self):
        """An empty / image-only PDF (no extractable text) should set status=error."""
        table, s3 = self._setup()
        s3.put_object(Bucket="scout-resumes-test", Key="resumes/user-002/resume.pdf", Body=b"%PDF-1.4")

        with self._patched_handler(s3) as rp:
            with patch.object(rp, "_extract_text_from_pdf", return_value="   "):
                result = rp.handler(
                    _make_s3_event("scout-resumes-test", "resumes/user-002/resume.pdf"), None
                )
        assert result["errors"] == 1

    def test_bad_s3_key_format_is_skipped(self):
        _, s3 = self._setup()
        # Bad key — no S3 download happens, so no need to store a file
        with self._patched_handler(s3) as rp:
            result = rp.handler(
                _make_s3_event("scout-resumes-test", "uploads/user-003/resume.pdf"), None
            )
        assert result["errors"] == 1
        assert result["processed"] == 0

    def test_multiple_records_processed_independently(self):
        table, s3 = self._setup()
        pdf = _minimal_pdf_bytes()
        s3.put_object(Bucket="scout-resumes-test", Key="resumes/u-a/resume.pdf", Body=pdf)
        s3.put_object(Bucket="scout-resumes-test", Key="resumes/u-b/resume.pdf", Body=pdf)

        event = {
            "Records": [
                {"s3": {"bucket": {"name": "scout-resumes-test"}, "object": {"key": "resumes/u-a/resume.pdf"}}},
                {"s3": {"bucket": {"name": "scout-resumes-test"}, "object": {"key": "resumes/u-b/resume.pdf"}}},
            ]
        }
        with self._patched_handler(s3) as rp:
            result = rp.handler(event, None)
        assert result["processed"] == 2
        assert result["errors"] == 0

    def test_missing_users_table_env_returns_500(self):
        # USERS_TABLE is a module-level constant — patch it directly
        import scoring.resume_parser as rp
        with patch.object(rp, "USERS_TABLE", ""):
            result = rp.handler(_make_s3_event("bucket", "resumes/x/resume.pdf"), None)
        assert result["statusCode"] == 500
