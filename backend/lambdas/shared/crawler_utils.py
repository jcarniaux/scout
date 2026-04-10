"""
Utility functions for job crawlers.
"""
import logging
import re
from typing import Optional

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def extract_salary_min(job: any) -> Optional[int]:
    """
    Extract minimum salary from a JobSpy job object.

    JobSpy returns salary as:
    - min_amount: minimum salary
    - max_amount: maximum salary
    - Or as a string like "$180,000 - $220,000"

    Args:
        job: JobSpy job dataframe row

    Returns:
        Minimum salary as int, or None if not found
    """
    try:
        # Try min_amount field first
        if hasattr(job, "min_amount") and job.min_amount:
            val = job.min_amount
            if isinstance(val, str):
                # Remove currency symbols and commas
                val = re.sub(r"[^\d]", "", val)
                return int(val) if val else None
            return int(val)
    except (ValueError, AttributeError):
        pass

    # Try salary field (some sources have combined string)
    if hasattr(job, "salary") and job.salary:
        try:
            salary_str = str(job.salary)
            # Extract first number from string like "$180,000 - $220,000"
            matches = re.findall(r"\d+(?:,\d+)*", salary_str)
            if matches:
                return int(matches[0].replace(",", ""))
        except (ValueError, AttributeError):
            pass

    return None


def extract_salary_max(job: any) -> Optional[int]:
    """
    Extract maximum salary from a JobSpy job object.

    Args:
        job: JobSpy job dataframe row

    Returns:
        Maximum salary as int, or None if not found
    """
    try:
        # Try max_amount field first
        if hasattr(job, "max_amount") and job.max_amount:
            val = job.max_amount
            if isinstance(val, str):
                val = re.sub(r"[^\d]", "", val)
                return int(val) if val else None
            return int(val)
    except (ValueError, AttributeError):
        pass

    # Try salary field and extract second number
    if hasattr(job, "salary") and job.salary:
        try:
            salary_str = str(job.salary)
            matches = re.findall(r"\d+(?:,\d+)*", salary_str)
            if len(matches) > 1:
                return int(matches[1].replace(",", ""))
        except (ValueError, AttributeError):
            pass

    return None


def normalize_title(title: str) -> str:
    """Normalize job title to title case."""
    return title.strip().title() if title else ""


def normalize_company(company: str) -> str:
    """Normalize company name."""
    return company.strip() if company else ""


def normalize_location(location: str) -> str:
    """Normalize location string."""
    if not location:
        return ""
    # Clean up and title case
    cleaned = location.strip().title()
    return cleaned


def meets_salary_requirement(salary_min: Optional[int], minimum_threshold: int = 180000) -> bool:
    """
    Check if a salary meets minimum requirement.

    Args:
        salary_min: Minimum salary from job posting
        minimum_threshold: Required minimum salary

    Returns:
        True if salary meets or exceeds threshold (or if no salary info)
    """
    if salary_min is None:
        # No salary info, assume it meets requirement
        return True
    return salary_min >= minimum_threshold
