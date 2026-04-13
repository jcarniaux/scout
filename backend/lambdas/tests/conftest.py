"""
Shared test fixtures for Scout backend tests.

Uses moto to mock AWS services so tests never touch real infrastructure.
"""
import json
import pytest
import boto3
from moto import mock_aws


# ── Environment variables ────────────────────────────────────────────────────
# Set BEFORE importing any handler (they read os.environ at module level).
@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    """Inject required Lambda environment variables for every test."""
    monkeypatch.setenv("JOBS_TABLE", "scout-jobs")
    monkeypatch.setenv("USER_STATUS_TABLE", "scout-user-status")
    monkeypatch.setenv("USERS_TABLE", "scout-users")
    monkeypatch.setenv("GLASSDOOR_CACHE_TABLE", "scout-glassdoor-cache")
    monkeypatch.setenv("SITE_URL", "https://scout.example.com")
    monkeypatch.setenv("SES_SENDER_EMAIL", "scout@example.com")
    monkeypatch.setenv("SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123456789012/scout-raw-jobs")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


# ── DynamoDB helpers ─────────────────────────────────────────────────────────
@pytest.fixture
def dynamodb_resource():
    """Mocked DynamoDB resource via moto."""
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        yield ddb


@pytest.fixture
def jobs_table(dynamodb_resource):
    """Create a mock jobs table matching the Scout schema."""
    table = dynamodb_resource.create_table(
        TableName="scout-jobs",
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
            {"AttributeName": "gsi1pk", "AttributeType": "S"},
            {"AttributeName": "postedDate", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "DateIndex",
                "KeySchema": [
                    {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                    {"AttributeName": "postedDate", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.meta.client.get_waiter("table_exists").wait(TableName="scout-jobs")
    return table


@pytest.fixture
def user_status_table(dynamodb_resource):
    """Create a mock user-status table."""
    table = dynamodb_resource.create_table(
        TableName="scout-user-status",
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.meta.client.get_waiter("table_exists").wait(TableName="scout-user-status")
    return table


@pytest.fixture
def users_table(dynamodb_resource):
    """Create a mock users table."""
    table = dynamodb_resource.create_table(
        TableName="scout-users",
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.meta.client.get_waiter("table_exists").wait(TableName="scout-users")
    return table


# ── API Gateway event helpers ────────────────────────────────────────────────
def make_api_event(
    method: str = "GET",
    path: str = "/",
    body: dict = None,
    path_params: dict = None,
    query_params: dict = None,
    user_sub: str = "test-user-sub-123",
    user_email: str = "testuser@example.com",
) -> dict:
    """Build a minimal API Gateway proxy event."""
    event = {
        "httpMethod": method,
        "path": path,
        "pathParameters": path_params or {},
        "queryStringParameters": query_params or {},
        "headers": {"Authorization": "Bearer fake-token"},
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": user_sub,
                    "email": user_email,
                },
            },
        },
    }
    if body is not None:
        event["body"] = json.dumps(body)
    else:
        event["body"] = None
    return event
