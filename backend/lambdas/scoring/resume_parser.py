"""
Resume Parser Lambda — triggered by S3 ObjectCreated on the resumes bucket.

Flow:
  1. S3 uploads resumes/{user_sub}/resume.pdf
  2. This Lambda fires via S3 event notification
  3. Downloads the PDF, extracts text with pdfminer
  4. Stores resume_text in the scout-users DynamoDB table
  5. Sets resume_status = "ready" and resume_filename

The user_sub is derived from the S3 key: resumes/{user_sub}/resume.pdf
"""
import io
import logging
import os
import urllib.parse
from datetime import datetime, timezone

import boto3

from shared.db import DynamoDBHelper

logger = logging.getLogger()
logger.setLevel(logging.INFO)

USERS_TABLE = os.environ.get("USERS_TABLE", "")

_dynamodb = DynamoDBHelper()
_s3 = boto3.client("s3")

# Maximum characters of resume text to store. A typical 2-page resume is
# ~3,000-6,000 chars. 8,000 chars captures most resumes while staying well
# under DynamoDB's 400 KB item limit and Bedrock's prompt budget.
MAX_RESUME_CHARS = 8_000


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extract plain text from a PDF using pdfminer.six.

    Returns the extracted text, truncated to MAX_RESUME_CHARS.
    Raises on completely unparseable PDFs (encrypted, corrupt).
    """
    from pdfminer.high_level import extract_text_to_fp
    from pdfminer.layout import LAParams

    output = io.StringIO()
    extract_text_to_fp(
        io.BytesIO(pdf_bytes),
        output,
        laparams=LAParams(),
        output_type="text",
        codec="utf-8",
    )
    text = output.getvalue()

    # Normalize whitespace: collapse runs of blank lines and strip excess spaces
    lines = [line.strip() for line in text.splitlines()]
    cleaned_lines = []
    prev_blank = False
    for line in lines:
        if line:
            cleaned_lines.append(line)
            prev_blank = False
        elif not prev_blank:
            cleaned_lines.append("")
            prev_blank = True
    return "\n".join(cleaned_lines).strip()[:MAX_RESUME_CHARS]


def _user_sub_from_key(s3_key: str) -> str:
    """
    Extract the user sub from the S3 key.
    Expected format: resumes/{user_sub}/resume.pdf
    """
    # key is URL-encoded by S3 events
    decoded = urllib.parse.unquote_plus(s3_key)
    parts = decoded.split("/")
    if len(parts) < 3 or parts[0] != "resumes":
        raise ValueError(f"Unexpected S3 key format: {decoded!r}")
    return parts[1]


def handler(event: dict, context) -> dict:
    """
    Process S3 ObjectCreated events for uploaded resumes.

    Updates the scout-users table with:
      - resume_text:     extracted plain text
      - resume_status:   "ready"
      - resume_filename: original filename (from the S3 key)
      - resume_updated_at: ISO timestamp
    """
    if not USERS_TABLE:
        logger.error("USERS_TABLE environment variable not set")
        return {"statusCode": 500}

    processed = 0
    errors = 0

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        logger.info(f"Processing resume: s3://{bucket}/{key}")

        try:
            user_sub = _user_sub_from_key(key)
        except ValueError as exc:
            logger.error(f"Skipping unexpected key {key!r}: {exc}")
            errors += 1
            continue

        # Download the PDF from S3
        try:
            obj = _s3.get_object(Bucket=bucket, Key=key)
            pdf_bytes = obj["Body"].read()
        except Exception as exc:
            logger.error(f"Failed to download s3://{bucket}/{key}: {exc}")
            errors += 1
            continue

        # Extract text
        try:
            resume_text = _extract_text_from_pdf(pdf_bytes)
        except Exception as exc:
            logger.error(f"PDF text extraction failed for {key!r}: {exc}")
            # Mark as error so the UI can notify the user
            _dynamodb.update_item(
                USERS_TABLE,
                key={"pk": f"USER#{user_sub}"},
                update_expression="SET resume_status = :s, resume_updated_at = :t",
                expression_attribute_values={
                    ":s": "error",
                    ":t": datetime.now(timezone.utc).isoformat(),
                },
            )
            errors += 1
            continue

        if not resume_text.strip():
            logger.warning(f"No text extracted from {key!r} (scanned PDF?)")
            _dynamodb.update_item(
                USERS_TABLE,
                key={"pk": f"USER#{user_sub}"},
                update_expression="SET resume_status = :s, resume_updated_at = :t",
                expression_attribute_values={
                    ":s": "error",
                    ":t": datetime.now(timezone.utc).isoformat(),
                },
            )
            errors += 1
            continue

        # Extract the filename from the key for display in the UI
        filename = urllib.parse.unquote_plus(key).split("/")[-1]

        char_count = len(resume_text)
        logger.info(f"Extracted {char_count} chars from {filename} for user {user_sub}")

        # Persist to DynamoDB
        _dynamodb.update_item(
            USERS_TABLE,
            key={"pk": f"USER#{user_sub}"},
            update_expression=(
                "SET resume_text = :text, resume_status = :s, "
                "resume_filename = :fn, resume_updated_at = :t"
            ),
            expression_attribute_values={
                ":text": resume_text,
                ":s": "ready",
                ":fn": filename,
                ":t": datetime.now(timezone.utc).isoformat(),
            },
        )
        processed += 1
        logger.info(f"Resume stored for user {user_sub}: {char_count} chars")

    return {
        "statusCode": 200,
        "processed": processed,
        "errors": errors,
    }
