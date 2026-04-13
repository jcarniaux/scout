"""Tests for shared.models — serialization round-trip and edge cases."""
from decimal import Decimal

from shared.models import dynamo_serialize, dynamo_deserialize


class TestDynamoSerialize:
    def test_omits_none_values(self):
        result = dynamo_serialize({"name": "test", "empty": None})
        assert "empty" not in result
        assert result["name"] == "test"

    def test_converts_int_to_decimal(self):
        result = dynamo_serialize({"salary": 180000})
        assert result["salary"] == Decimal("180000")

    def test_converts_float_to_decimal(self):
        result = dynamo_serialize({"rating": 4.5})
        assert result["rating"] == Decimal("4.5")

    def test_preserves_booleans(self):
        result = dynamo_serialize({"daily_report": True, "weekly_report": False})
        assert result["daily_report"] is True
        assert result["weekly_report"] is False

    def test_string_list_becomes_set(self):
        result = dynamo_serialize({"benefits": ["PTO", "401(k)", "Medical"]})
        assert isinstance(result["benefits"], set)
        assert result["benefits"] == {"PTO", "401(k)", "Medical"}

    def test_omits_empty_lists(self):
        result = dynamo_serialize({"tags": []})
        assert "tags" not in result

    def test_preserves_strings(self):
        result = dynamo_serialize({"pk": "JOB#abc123"})
        assert result["pk"] == "JOB#abc123"

    def test_nested_dict(self):
        result = dynamo_serialize({"prefs": {"salary_min": 150000}})
        assert result["prefs"]["salary_min"] == Decimal("150000")


class TestDynamoDeserialize:
    def test_converts_decimal_to_int(self):
        result = dynamo_deserialize({"salary": Decimal("180000")})
        assert result["salary"] == 180000
        assert isinstance(result["salary"], int)

    def test_converts_decimal_float(self):
        result = dynamo_deserialize({"rating": Decimal("4.5")})
        assert result["rating"] == 4.5
        assert isinstance(result["rating"], float)

    def test_converts_set_to_list(self):
        result = dynamo_deserialize({"benefits": {"PTO", "Medical"}})
        assert isinstance(result["benefits"], list)
        assert set(result["benefits"]) == {"PTO", "Medical"}

    def test_preserves_other_types(self):
        result = dynamo_deserialize({"name": "test", "active": True})
        assert result["name"] == "test"
        assert result["active"] is True


class TestRoundTrip:
    def test_serialize_then_deserialize(self):
        original = {
            "pk": "JOB#abc",
            "salary_min": 180000,
            "rating": 4.2,
            "daily_report": True,
            "benefits": ["PTO", "Medical"],
            "empty": None,
        }
        serialized = dynamo_serialize(original)
        deserialized = dynamo_deserialize(serialized)

        assert deserialized["pk"] == "JOB#abc"
        assert deserialized["salary_min"] == 180000
        assert deserialized["rating"] == pytest.approx(4.2)
        assert deserialized["daily_report"] is True
        assert set(deserialized["benefits"]) == {"PTO", "Medical"}
        assert "empty" not in deserialized


# Need pytest for approx
import pytest
