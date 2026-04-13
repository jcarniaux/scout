"""
On-demand AI job scoring Lambda for Scout.

Supports two modes depending on the event payload:

  BULK MODE (async, POST /user/score-jobs):
    { "user_pk": "USER#<sub>" }
    Scores up to MAX_JOBS_TO_SCORE recent jobs, writes all to JOB_SCORES_TABLE,
    updates scoring_status = "done". Invoked asynchronously (InvokeType=Event)
    so the API always returns 202 immediately.

  SINGLE MODE (sync, POST /jobs/{jobId}/score):
    { "user_pk": "USER#<sub>", "job_hash": "<hash>" }
    Scores one specific job synchronously and returns { score, reasoning }
    directly to the caller. No status field update.
"""
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import boto3

from shared.db import DynamoDBHelper
from shared.metrics import emit_metric
from shared.models import dynamo_deserialize

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = DynamoDBHelper()
_bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))

# Cap to keep runtime well within the 300s Lambda timeout.
# ~100 jobs × ~1.5s per Bedrock call = ~150s.
MAX_JOBS_TO_SCORE = 100

# Look back this many days when querying jobs to score.
SCORE_LOOKBACK_DAYS = 30


def _score_job_for_user(job: Dict[str, Any], resume_text: str) -> Tuple[int, str]:
    """
    Call Bedrock Claude Haiku to score one job against a resume.

    Args:
        job:         Deserialized DynamoDB job item
        resume_text: Full resume text (will be truncated to 2 000 chars)

    Returns:
        Tuple of (score 0–100, one-sentence reasoning string)

    Raises:
        Exception on Bedrock or JSON parse failure (caller handles it)
    """
    model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")

    resume_excerpt = resume_text[:2000]
    description_excerpt = (job.get("description") or "")[:1500]

    prompt = (
        "Score this job posting against the candidate's resume on a 0-100 scale.\n\n"
        f"Resume:\n{resume_excerpt}\n\n"
        f"Job Title: {job.get('title', '')}\n"
        f"Company: {job.get('company', '')}\n"
        f"Description:\n{description_excerpt}\n\n"
        'Return ONLY valid JSON: {"score": <integer 0-100>, "reasoning": "<one concise sentence>"}'
    )

    response = _bedrock.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 120,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )
    raw = json.loads(response["body"].read())
    text = raw["content"][0]["text"].strip()

    # Strip markdown code fences that Haiku occasionally wraps around JSON
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text).rstrip("`").strip()

    result = json.loads(text)
    score = max(0, min(100, int(result["score"])))
    reasoning = str(result.get("reasoning", ""))[:500]
    return score, reasoning


def _fetch_recent_jobs(jobs_table: str, days: int = SCORE_LOOKBACK_DAYS) -> List[Dict[str, Any]]:
    """
    Query the DateIndex for all jobs posted in the last `days` days.
    Stops early once MAX_JOBS_TO_SCORE items have been collected.
    """
    start_date = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
    jobs: List[Dict[str, Any]] = []
    last_key: Optional[Dict] = None

    while len(jobs) < MAX_JOBS_TO_SCORE:
        items, last_key = dynamodb.query(
            jobs_table,
            "gsi1pk = :pk AND postedDate >= :start",
            {":pk": "JOB", ":start": start_date},
            index_name="DateIndex",
            scan_index_forward=False,
            limit=min(100, MAX_JOBS_TO_SCORE - len(jobs)),
            exclusive_start_key=last_key,
        )
        jobs.extend([dynamo_deserialize(i) for i in items])
        if not last_key:
            break

    return jobs[:MAX_JOBS_TO_SCORE]


def _api_gw_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap a response dict in API Gateway proxy integration format."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Dispatcher: single-job mode when event contains job_hash or pathParameters.jobId,
    bulk mode otherwise.

    Supports two invocation patterns:
    - API Gateway proxy (POST /jobs/{jobId}/score): reads user_sub from Cognito claims
      and jobId from pathParameters; returns an API GW-formatted response.
    - Direct Lambda invocation (async bulk, or sync single): reads user_pk / job_hash
      directly from the event dict; returns a plain dict.
    """
    # Detect API Gateway proxy events
    is_api_gw = "requestContext" in event

    if is_api_gw:
        try:
            user_sub = event["requestContext"]["authorizer"]["claims"]["sub"]
        except (KeyError, TypeError):
            return _api_gw_response(401, {"error": "Unauthorized"})
        job_hash: str = (event.get("pathParameters") or {}).get("jobId", "")
        user_pk: str = f"USER#{user_sub}"
    else:
        user_pk = event.get("user_pk", "")
        job_hash = event.get("job_hash", "")

    jobs_table = os.environ.get("JOBS_TABLE", "")
    users_table = os.environ.get("USERS_TABLE", "")
    job_scores_table = os.environ.get("JOB_SCORES_TABLE", "")

    if not jobs_table or not users_table or not job_scores_table:
        logger.error("Missing required environment variables")
        if is_api_gw:
            return _api_gw_response(500, {"error": "Missing environment variables"})
        return {"statusCode": 500, "error": "Missing environment variables"}

    if not user_pk:
        logger.error("Missing user_pk in event payload")
        if is_api_gw:
            return _api_gw_response(400, {"error": "Missing user_pk"})
        return {"statusCode": 400, "error": "Missing user_pk"}

    if job_hash:
        result = _score_single(user_pk, job_hash, jobs_table, users_table, job_scores_table)
        if is_api_gw:
            status_code = result.get("statusCode", 200)
            body = {k: v for k, v in result.items() if k != "statusCode"}
            return _api_gw_response(status_code, body)
        return result

    return _score_bulk(user_pk, jobs_table, users_table, job_scores_table)


def _score_single(
    user_pk: str,
    job_hash: str,
    jobs_table: str,
    users_table: str,
    job_scores_table: str,
) -> Dict[str, Any]:
    """
    Score one specific job synchronously and return {score, reasoning}.
    Called from POST /jobs/{jobId}/score (synchronous Lambda invocation).
    """
    # Fetch user + resume
    user = dynamodb.get_item(users_table, {"pk": user_pk})
    if not user:
        return {"statusCode": 404, "error": "User not found"}

    resume_text: str = user.get("resume_text", "")
    if not resume_text:
        return {"statusCode": 400, "error": "No resume uploaded"}

    # Fetch the specific job — query by pk, take first matching item
    try:
        items, _ = dynamodb.query(
            jobs_table,
            "pk = :pk",
            {":pk": f"JOB#{job_hash}"},
        )
        if not items:
            return {"statusCode": 404, "error": "Job not found"}
        job = dynamo_deserialize(items[0])
    except Exception as exc:
        logger.error(f"Failed to fetch job {job_hash}: {exc}", exc_info=True)
        return {"statusCode": 500, "error": "Failed to fetch job"}

    # Score it
    try:
        score, reasoning = _score_job_for_user(job, resume_text)
    except Exception as exc:
        logger.error(f"Bedrock scoring failed for job {job_hash}: {exc}", exc_info=True)
        return {"statusCode": 500, "error": "Scoring failed"}

    # Persist the score
    ttl = int((datetime.utcnow() + timedelta(days=60)).timestamp())
    try:
        dynamodb.put_item(job_scores_table, {
            "pk": user_pk,
            "sk": f"JOB#{job_hash}",
            "score": score,
            "reasoning": reasoning,
            "scored_at": datetime.utcnow().isoformat(),
            "ttl": ttl,
        })
    except Exception as exc:
        logger.warning(f"Failed to persist score for {job_hash}: {exc}")

    emit_metric("Scout/Scoring", "JobsScored", 1)
    return {"statusCode": 200, "score": score, "reasoning": reasoning}


def _score_bulk(
    user_pk: str,
    jobs_table: str,
    users_table: str,
    job_scores_table: str,
) -> Dict[str, Any]:
    """Score all recent jobs for the user (async bulk mode)."""

    # ── Fetch user + resume ────────────────────────────────────────────────────
    user = dynamodb.get_item(users_table, {"pk": user_pk})
    if not user:
        logger.error(f"User {user_pk} not found")
        _mark_done(users_table, user_pk, scored=0)
        return {"statusCode": 404, "error": "User not found"}

    resume_text: str = user.get("resume_text", "")
    if not resume_text:
        logger.warning(f"User {user_pk} has no resume_text — nothing to score")
        _mark_done(users_table, user_pk, scored=0)
        return {"statusCode": 200, "scored": 0}

    # ── Fetch recent jobs ──────────────────────────────────────────────────────
    try:
        jobs = _fetch_recent_jobs(jobs_table)
    except Exception as exc:
        logger.error(f"Failed to fetch jobs: {exc}", exc_info=True)
        _mark_done(users_table, user_pk, scored=0)
        return {"statusCode": 500, "error": "Failed to fetch jobs"}

    logger.info(f"Scoring {len(jobs)} jobs for user {user_pk}")

    # TTL: match the job TTL (60 days from now)
    ttl = int((datetime.utcnow() + timedelta(days=60)).timestamp())

    total_scored = 0
    total_errors = 0

    for job in jobs:
        job_hash = job.get("job_hash") or (
            job.get("pk", "")[len("JOB#"):] if job.get("pk", "").startswith("JOB#") else ""
        )
        if not job_hash:
            continue

        try:
            score, reasoning = _score_job_for_user(job, resume_text)
            dynamodb.put_item(job_scores_table, {
                "pk": user_pk,
                "sk": f"JOB#{job_hash}",
                "score": score,
                "reasoning": reasoning,
                "scored_at": datetime.utcnow().isoformat(),
                "ttl": ttl,
            })
            total_scored += 1
        except Exception as exc:
            total_errors += 1
            logger.warning(
                f"Scoring failed for user {user_pk} on job {job_hash[:8]}…: {exc}"
            )

    logger.info(
        f"Scoring complete for {user_pk}: "
        f"{total_scored} scored, {total_errors} errors"
    )

    emit_metric("Scout/Scoring", "JobsScored", total_scored)
    emit_metric("Scout/Scoring", "ScoringErrors", total_errors)

    _mark_done(users_table, user_pk, scored=total_scored)
    return {"statusCode": 200, "scored": total_scored, "errors": total_errors}


def _mark_done(users_table: str, user_pk: str, scored: int) -> None:
    """Update the user record to reflect scoring completion."""
    try:
        dynamodb.update_item(
            users_table,
            key={"pk": user_pk},
            update_expression=(
                "SET scoring_status = :s, last_scored_at = :t, last_scored_count = :c"
            ),
            expression_attribute_values={
                ":s": "done",
                ":t": datetime.utcnow().isoformat(),
                ":c": scored,
            },
        )
    except Exception as exc:
        logger.warning(f"Failed to mark scoring done for {user_pk}: {exc}")
