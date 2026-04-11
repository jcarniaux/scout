"""
Data models and constants for Scout backend.
"""
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from decimal import Decimal

# Application statuses
APPLICATION_STATUSES = [
    "NOT_APPLIED",
    "NOT_INTERESTED",
    "APPLIED",
    "RECRUITER_INTERVIEW",
    "TECHNICAL_INTERVIEW",
    "OFFER_RECEIVED",
    "OFFER_ACCEPTED",
]

# Role queries for job search
ROLE_QUERIES = [
    "Security Engineer",
    "Security Architect",
    "Solutions Architect",
    "Network Security Architect",
    "Cloud Security Architect",
    "Cloud Architect",
    "CISO",
    "Chief Information Security Officer",
    "Deputy CISO",
    "VP Information Security",
]

# Location configurations
LOCATIONS = [
    {"location": "Atlanta, GA", "distance": 25, "remote": False},
    {"location": "United States", "distance": None, "remote": True},
]

# Salary minimum threshold
SALARY_MINIMUM = 180000


@dataclass
class Job:
    """Job listing model."""

    source: str  # linkedin, indeed, glassdoor, ziprecruiter, dice
    title: str
    company: str
    location: str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    job_url: str = ""
    date_posted: Optional[str] = None
    description: str = ""
    job_type: Optional[str] = None  # Full-time, Part-time, etc.
    rating: Optional[float] = None  # Glassdoor rating
    benefits: Optional[List[str]] = field(default_factory=list)
    crawled_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_at: Optional[str] = None
    ttl: Optional[int] = None  # DynamoDB TTL timestamp

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict, handling None values."""
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}

    def to_dynamo(self) -> Dict[str, Any]:
        """Convert to DynamoDB format."""
        data = self.to_dict()
        # Convert lists to sets for DynamoDB if needed
        if data.get("benefits"):
            data["benefits"] = set(data["benefits"])
        return data


@dataclass
class UserStatus:
    """User's application status for a job."""

    user_id: str  # USER#{cognito_sub}
    job_id: str  # JOB#{hash}
    status: str  # One of APPLICATION_STATUSES
    notes: Optional[str] = None
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return asdict(self)


@dataclass
class UserSettings:
    """User configuration and preferences."""

    user_id: str  # USER#{cognito_sub}
    email: str
    daily_report: bool = False
    weekly_report: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return asdict(self)


def dynamo_deserialize(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert DynamoDB types to Python types.
    Handles Decimal -> float/int conversion for JSON serialization.
    """
    if not isinstance(data, dict):
        return data

    result = {}
    for k, v in data.items():
        if isinstance(v, Decimal):
            # Try to convert to int, fallback to float
            if v % 1 == 0:
                result[k] = int(v)
            else:
                result[k] = float(v)
        elif isinstance(v, dict):
            result[k] = dynamo_deserialize(v)
        elif isinstance(v, list):
            result[k] = [dynamo_deserialize(item) if isinstance(item, dict) else item for item in v]
        elif isinstance(v, set):
            result[k] = list(v)
        else:
            result[k] = v
    return result


def dynamo_serialize(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert Python types to DynamoDB-compatible types.
    Lists become sets for set attributes, None values are omitted.
    """
    if not isinstance(data, dict):
        return data

    result = {}
    for k, v in data.items():
        if v is None:
            continue  # Omit None values
        elif isinstance(v, bool):
            result[k] = v  # Keep booleans
        elif isinstance(v, (int, float)):
            result[k] = Decimal(str(v))
        elif isinstance(v, dict):
            result[k] = dynamo_serialize(v)
        elif isinstance(v, list):
            # Check if all items are strings (benefits, for example)
            if all(isinstance(item, str) for item in v):
                result[k] = set(v)
            else:
                result[k] = v
        else:
            result[k] = v
    return result
