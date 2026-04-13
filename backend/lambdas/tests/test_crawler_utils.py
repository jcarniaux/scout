"""Tests for shared.crawler_utils — pure functions only (no AWS calls)."""
import pytest
from types import SimpleNamespace

from shared.crawler_utils import (
    extract_salary_min,
    extract_salary_max,
    normalize_title,
    normalize_company,
    normalize_location,
    meets_location_requirement,
    meets_salary_requirement,
)


# ── Salary extraction ────────────────────────────────────────────────────────

class TestExtractSalaryMin:
    def test_numeric_min_amount(self):
        job = SimpleNamespace(min_amount=180000)
        assert extract_salary_min(job) == 180000

    def test_string_min_amount(self):
        job = SimpleNamespace(min_amount="$180,000")
        assert extract_salary_min(job) == 180000

    def test_salary_range_string(self):
        job = SimpleNamespace(min_amount=None, salary="$180,000 - $220,000")
        assert extract_salary_min(job) == 180000

    def test_no_salary_info(self):
        job = SimpleNamespace(min_amount=None, salary=None)
        assert extract_salary_min(job) is None

    def test_no_salary_attr(self):
        job = SimpleNamespace()
        assert extract_salary_min(job) is None


class TestExtractSalaryMax:
    def test_numeric_max_amount(self):
        job = SimpleNamespace(max_amount=220000)
        assert extract_salary_max(job) == 220000

    def test_string_max_amount(self):
        job = SimpleNamespace(max_amount="$220,000")
        assert extract_salary_max(job) == 220000

    def test_salary_range_string(self):
        job = SimpleNamespace(max_amount=None, salary="$180,000 - $220,000")
        assert extract_salary_max(job) == 220000

    def test_no_salary_info(self):
        job = SimpleNamespace(max_amount=None, salary=None)
        assert extract_salary_max(job) is None


# ── Normalizers ──────────────────────────────────────────────────────────────

class TestNormalizeTitle:
    def test_title_cases(self):
        assert normalize_title("senior security engineer") == "Senior Security Engineer"

    def test_strips_whitespace(self):
        assert normalize_title("  Cloud Architect  ") == "Cloud Architect"

    def test_empty_string(self):
        assert normalize_title("") == ""

    def test_none_safe(self):
        assert normalize_title(None) == ""


class TestNormalizeCompany:
    def test_strips_whitespace(self):
        assert normalize_company("  Acme Corp  ") == "Acme Corp"

    def test_empty(self):
        assert normalize_company("") == ""

    def test_none_safe(self):
        assert normalize_company(None) == ""


class TestNormalizeLocation:
    def test_title_case(self):
        assert normalize_location("atlanta, ga") == "Atlanta, Ga"

    def test_empty(self):
        assert normalize_location("") == ""

    def test_none_safe(self):
        assert normalize_location(None) == ""


# ── Location filter ──────────────────────────────────────────────────────────

class TestMeetsLocationRequirement:
    """Core business logic — test thoroughly."""

    @pytest.mark.parametrize("location", [
        "Atlanta, GA",
        "atlanta, ga",
        "Atlanta, Georgia",
        "Atlanta, GA, United States",
    ])
    def test_atlanta_accepted(self, location):
        assert meets_location_requirement(location) is True

    @pytest.mark.parametrize("location", [
        "Remote",
        "remote",
        "Work from Home",
        "Hybrid",
        "Anywhere",
        "WFH",
    ])
    def test_remote_accepted(self, location):
        assert meets_location_requirement(location) is True

    @pytest.mark.parametrize("location", [
        "United States",
        "Remote, United States",
    ])
    def test_us_national_accepted(self, location):
        assert meets_location_requirement(location) is True

    @pytest.mark.parametrize("location", [
        None,
        "",
        "Unknown",
        "location unknown",
    ])
    def test_empty_unknown_accepted(self, location):
        assert meets_location_requirement(location) is True

    @pytest.mark.parametrize("location", [
        "New York, NY",
        "San Francisco, CA",
        "London, UK",
        "Nebraska, United States",
    ])
    def test_other_cities_rejected(self, location):
        assert meets_location_requirement(location) is False


# ── Salary filter ────────────────────────────────────────────────────────────

class TestMeetsSalaryRequirement:
    def test_none_salary_passes(self):
        assert meets_salary_requirement(None, 150000) is True

    def test_above_threshold(self):
        assert meets_salary_requirement(200000, 150000) is True

    def test_equal_threshold(self):
        assert meets_salary_requirement(150000, 150000) is True

    def test_below_threshold(self):
        assert meets_salary_requirement(100000, 150000) is False

    def test_zero_threshold(self):
        assert meets_salary_requirement(50000, 0) is True
