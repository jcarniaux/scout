# Scout Codebase Review — Security, Performance & Best Practices

**Date:** April 12, 2026  
**Scope:** Full review of Terraform IaC, Python Lambda backend, React/TypeScript frontend

---

## 1. Security

### 1.1 CRITICAL — CORS Falls Back to Wildcard Origin

**File:** `backend/lambdas/shared/response.py:17`

```python
site_url = os.environ.get("SITE_URL", "*")
```

When `SITE_URL` is missing from a Lambda's environment, all CORS responses use `Access-Control-Allow-Origin: *`. This lets any website make authenticated requests to your API using a user's Cognito token. Currently only `get_jobs` and `daily_report` Lambdas have `SITE_URL` set — the `update_status` and `user_settings` Lambdas do **not**.

**Fix:** Add `SITE_URL` to every API Lambda's environment variables in `terraform/modules/api/main.tf`, and change the fallback to reject rather than allow:

```python
site_url = os.environ.get("SITE_URL")
if not site_url:
    raise RuntimeError("SITE_URL environment variable is required")
```

---

### 1.2 HIGH — No API Gateway Request Throttling

**File:** `terraform/modules/api/main.tf`

The API Gateway stage has no `method_settings` block, so throttling defaults to AWS account-level limits (10,000 req/s). A single bad actor or bot could exhaust your Lambda concurrency or inflate your bill.

**Fix:** Add method-level throttling to the stage:

```hcl
resource "aws_api_gateway_method_settings" "all" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  stage_name  = aws_api_gateway_stage.v1.stage_name
  method_path = "*/*"

  settings {
    throttling_burst_limit = 50
    throttling_rate_limit  = 100
    logging_level          = "ERROR"
    data_trace_enabled     = false
    metrics_enabled        = true
  }
}
```

---

### 1.3 HIGH — No WAF on API Gateway

**File:** `terraform/modules/frontend/main.tf`

WAF is only attached to CloudFront. If someone discovers your API Gateway URL (which is in the browser's network tab), they can hit it directly, bypassing CloudFront WAF entirely.

**Fix:** Either attach a regional WAFv2 WebACL to the API Gateway stage, or use a CloudFront distribution in front of API Gateway with the existing WAF.

---

### 1.4 HIGH — SQS Queues Not Encrypted

**File:** `terraform/modules/crawl/main.tf:12-29`

Neither the `raw-jobs` queue nor the DLQ have encryption enabled. Job data (titles, companies, URLs) transit and rest in plaintext.

**Fix:**
```hcl
resource "aws_sqs_queue" "raw_jobs" {
  name                       = "${var.project_name}-raw-jobs"
  sqs_managed_sse_enabled    = true
  # ...
}
```

---

### 1.5 HIGH — No CloudFront Security Response Headers

**File:** `terraform/modules/frontend/main.tf`

No response headers policy is attached to CloudFront. The app serves no `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security`, or `Referrer-Policy` headers.

**Fix:** Add a `aws_cloudfront_response_headers_policy` with security headers and attach it to the distribution's `default_cache_behavior`.

---

### 1.6 MEDIUM — No Input Length Validation on API Endpoints

**Files:** `backend/lambdas/api/update_status.py`, `backend/lambdas/api/user_settings.py`

The `notes` field in status updates and `role_queries` entries have no max-length validation. An attacker could send megabytes of data per field, inflating DynamoDB storage costs and potentially causing Lambda timeouts.

**Fix:** Add explicit length guards:
```python
if len(notes) > 500:
    return error_response("Notes must be 500 characters or fewer", 400)
```

---

### 1.7 MEDIUM — Error Responses May Leak Internal Details

**Files:** Multiple Lambda handlers

Some error paths pass raw exception messages to `error_response()`:
```python
return {"statusCode": 500, "error": str(e)}  # enrichment/handler.py
```

This could expose DynamoDB table names, ARNs, or stack traces to callers.

**Fix:** Log the full error, return a generic message:
```python
logger.error(f"Error: {e}", exc_info=True)
return error_response("Internal server error", 500)
```

---

### 1.8 MEDIUM — No API Gateway Request Validators

**File:** `terraform/modules/api/main.tf`

No `aws_api_gateway_request_validator` resources exist. Malformed requests (wrong content type, missing required params) hit Lambda instead of being rejected at the gateway. This wastes Lambda invocations and cold start budget.

**Fix:** Create a request validator and attach it to methods that accept a body (PATCH, PUT).

---

### 1.9 MEDIUM — Missing IPv6 DNS Record

**File:** `terraform/modules/frontend/main.tf`

CloudFront has `is_ipv6_enabled = true` but Route53 only has an `A` record (IPv4). IPv6 clients will fail to resolve `scout.carniaux.io`.

**Fix:** Add an AAAA alias record alongside the existing A record.

---

### 1.10 LOW — Lambda Log Groups Retain Indefinitely

**File:** `terraform/modules/crawl/main.tf`, `terraform/modules/email/main.tf`

Lambda auto-creates `/aws/lambda/<function-name>` log groups with no retention policy. Only the API Gateway log group has `retention_in_days = 7`. Over time, crawler logs will accumulate and cost money.

**Fix:** Create explicit `aws_cloudwatch_log_group` resources for each Lambda with appropriate retention (7-30 days).

---

### 1.11 LOW — S3 Bucket Versioning Not Explicitly Enabled

**File:** `terraform/modules/frontend/main.tf`

The frontend bucket has `ignore_changes = [versioning]` which preserves whatever state exists, but never explicitly enables versioning. Without versioning, a bad deploy has no easy S3-level rollback.

**Fix:** Add `aws_s3_bucket_versioning` resource with `status = "Enabled"`.

---

## 2. Performance

### 2.1 CRITICAL — `list_jobs` Loads Entire Dataset per Page Request

**File:** `backend/lambdas/api/get_jobs.py:241-254`

```python
all_items: list = []
last_key = None
while True:
    items, last_key = dynamodb.query(...)
    all_items.extend(items)
    if not last_key:
        break
```

Every page request (even page 1 of 20 items) fetches **all** jobs from the last 30 days, then filters and slices in Python. With hundreds of jobs, this is wasteful. With thousands, it'll timeout.

**Fix (short-term):** Use DynamoDB's `Limit` parameter and `ExclusiveStartKey` for server-side pagination. Track the last-evaluated key in the frontend.

**Fix (long-term):** Store user statuses in a GSI on the jobs table to avoid the separate user-status query entirely.

---

### 2.2 HIGH — N+1 Query Pattern in Orphaned Status Cleanup

**File:** `backend/lambdas/crawlers/purge.py:108-126`

The purge Lambda scans ALL user-status records, then issues a **separate DynamoDB query for each one** to check if the parent job still exists. With 500 status records, that's 500 queries.

**Fix:** Scan the jobs table first to build a set of existing job hashes. Then scan statuses and check membership in-memory. Two scans instead of N+1 queries.

---

### 2.3 HIGH — Synchronous Glassdoor Rating Fetch in Enrichment

**File:** `backend/lambdas/enrichment/handler.py:139-143`

For each SQS message, the enrichment Lambda makes a synchronous HTTP GET to Glassdoor's website. With a batch of 10 messages, that's up to 50+ seconds of HTTP calls (5s timeout × 10). This blocks the entire batch processing.

**Fix:** Decouple rating lookups into a separate asynchronous process (a dedicated Lambda or a second SQS queue). The enrichment Lambda should store the job immediately and mark `rating_pending: true`.

---

### 2.4 HIGH — Daily Report Uses Wrong Query Key

**File:** `backend/lambdas/reports/daily_report.py:47-53`

```python
jobs, _ = dynamodb.query(
    jobs_table,
    "created_at >= :start",     # ← This is NOT a valid KeyConditionExpression
    {":start": start_date},
    index_name="DateIndex",     # DateIndex keys: gsi1pk + postedDate
)
```

`created_at` is not a key attribute on the DateIndex (which uses `gsi1pk` and `postedDate`). This query will throw a `ValidationException` at runtime. The daily report is broken.

**Fix:**
```python
jobs, _ = dynamodb.query(
    jobs_table,
    "gsi1pk = :pk AND postedDate >= :start",
    {":pk": "JOB", ":start": start_date},
    index_name="DateIndex",
    scan_index_forward=False,
)
```

---

### 2.5 MEDIUM — Individual SQS `send_message` Calls in Crawlers

**Files:** All crawler handlers (linkedin.py, dice.py, glassdoor.py, etc.)

Each crawler sends jobs to SQS one at a time via `sqs_client.send_message()`. With 50+ jobs per crawler, that's 50+ API calls.

**Fix:** Batch using `sqs_client.send_message_batch()` (up to 10 messages per call). This cuts API calls by ~10x.

---

### 2.6 MEDIUM — Enrichment Lambda Doesn't Return `batchItemFailures`

**File:** `backend/lambdas/enrichment/handler.py`, `terraform/modules/crawl/main.tf:386`

The SQS event source mapping uses `function_response_types = ["ReportBatchItemFailures"]`, but the handler returns a simple `{"statusCode": 200, ...}` dict — never `{"batchItemFailures": [...]}`. When a single message fails, ALL 10 messages in the batch get retried.

**Fix:** Track failed message IDs and return them properly:
```python
failed = []
for record in event["Records"]:
    try:
        # ... process ...
    except Exception:
        failed.append({"itemIdentifier": record["messageId"]})

return {"batchItemFailures": failed}
```

---

### 2.7 MEDIUM — No Lambda X-Ray Tracing

**Files:** All Lambda function definitions in Terraform

No Lambda function has `tracing_config { mode = "Active" }`. Without X-Ray, you can't trace latency across Step Functions → Lambda → SQS → Lambda → DynamoDB.

**Fix:** Add `tracing_config { mode = "Active" }` to Lambda resources and grant `xray:PutTraceSegments` + `xray:PutTelemetryRecords` permissions.

---

### 2.8 LOW — CloudFront Cache Could Be Smarter

**File:** `terraform/modules/frontend/main.tf`

The distribution uses a single `CachingOptimized` policy for everything. Vite generates hash-based filenames under `/assets/` that are safe to cache aggressively (1 year), while `index.html` should have short/no cache.

**Fix:** Add an ordered cache behavior for `/assets/*` with a long-TTL policy, and use a short-TTL or no-cache policy for the default behavior.

---

## 3. Best Practices

### 3.1 CRITICAL — Missing Frontend Source Files (Build Will Fail)

**File:** `frontend/src/App.tsx`, `frontend/src/hooks/useJobs.ts`, `frontend/src/components/JobList.tsx`

These files import modules that don't exist in the repo:

| Import | Expected File | Status |
|--------|--------------|--------|
| `@/pages/Dashboard` | `src/pages/Dashboard.tsx` | **Missing** |
| `@/pages/Settings` | `src/pages/Settings.tsx` | **Missing** |
| `@/services/api` | `src/services/api.ts` | **Missing** |
| `@/types` | `src/types/index.ts` | **Missing** |
| `./JobCard` | `src/components/JobCard.tsx` | **Missing** |

The frontend cannot compile without these files.

**Fix:** Create the missing page components, API service layer, and type definitions.

---

### 3.2 HIGH — Glassdoor Crawler Doesn't Use Dynamic Search Config

**File:** `backend/lambdas/crawlers/glassdoor.py:26`

```python
from shared.models import ROLE_QUERIES, LOCATIONS, SALARY_MINIMUM
```

Every other crawler uses `load_search_config()` to read user preferences from DynamoDB. Glassdoor imports hardcoded defaults directly, so changes in the Settings page have no effect on Glassdoor crawls.

**Fix:** Replace with `from shared.search_config import load_search_config` and use `config = load_search_config()` in the handler, matching the pattern in `linkedin.py` and `dice.py`.

---

### 3.3 HIGH — Duplicate `get_user_sub()` Function

**Files:** `get_jobs.py:20`, `update_status.py:21`, `user_settings.py:22`

The identical function is copy-pasted across three files.

**Fix:** Move it to `shared/auth.py` and import it.

---

### 3.4 HIGH — `put_settings` Uses Full Replace Instead of Partial Update

**File:** `backend/lambdas/api/user_settings.py:171`

`put_item` replaces the entire DynamoDB record. If a user has fields not included in the PUT body (e.g. `created_at` stored previously, custom fields), they get silently dropped. Two concurrent saves could also overwrite each other.

**Fix:** Use `update_item` with a targeted `UpdateExpression` that only modifies the fields being changed.

---

### 3.5 MEDIUM — No `package-lock.json` in Version Control

**File:** `frontend/`

Only `package.json` exists. Without a lockfile, `npm install` may resolve different dependency versions across environments, causing "works on my machine" bugs.

**Fix:** Run `npm install` and commit `package-lock.json`.

---

### 3.6 MEDIUM — Hardcoded `CreatedAt` Tag

**File:** `terraform/providers.tf:28`

```hcl
CreatedAt = "2026-04-09"
```

This is a static string that will never update. It gives a false impression that all resources were created on April 9th.

**Fix:** Either remove it, or use `timestamp()` with `ignore_changes` in lifecycle so it's set once at creation time and not updated.

---

### 3.7 MEDIUM — No Terraform State Backup Strategy

**File:** `terraform/providers.tf`

The S3 backend bucket (`scout-tfstate-634502671794`) has no explicit versioning, replication, or lifecycle policy defined in the codebase. If the state file is corrupted or accidentally deleted, the entire infrastructure becomes unmanageable.

**Fix:** Enable S3 versioning and point-in-time recovery on the state bucket (ideally managed in a separate bootstrap Terraform config).

---

### 3.8 MEDIUM — No React Error Boundary

**File:** `frontend/src/App.tsx`

There's no error boundary component. An unhandled exception in any component (e.g., a null pointer in `JobCard`) crashes the entire app with a white screen.

**Fix:** Add a top-level `ErrorBoundary` component that catches render errors and shows a fallback UI with a retry button.

---

### 3.9 MEDIUM — Frontend `index.html` Missing Security Meta Tags

**File:** `frontend/index.html`

No `<meta>` tags for CSP, and no `<meta name="referrer" content="strict-origin-when-cross-origin">`. Combined with missing CloudFront security headers (1.5), the app has no defense against XSS or clickjacking.

**Fix:** At minimum, add `<meta http-equiv="Content-Security-Policy" content="default-src 'self'; ...">`.

---

### 3.10 LOW — No Lambda Layers for Shared Dependencies

**Files:** All Lambda function definitions

Each Lambda deploys its own copy of `boto3`, `requests`, `beautifulsoup4`, etc. This inflates deployment package sizes and slows CI/CD.

**Fix:** Create a Lambda Layer with shared Python dependencies. Reference it in each function's `layers` attribute.

---

### 3.11 LOW — `ziprecruiter.py` and `indeed.py` Not in Step Functions

**File:** `terraform/modules/crawl/main.tf:458-471`

The Step Functions state machine only invokes `linkedin`, `indeed`, and `dice` Lambdas. Glassdoor and ZipRecruiter Lambdas are defined in Terraform but **not wired into the state machine**, so they never run on schedule.

**Fix:** Add Glassdoor and ZipRecruiter Lambda invocations to the state machine definition in `state_machine.json`, or remove them if intentionally disabled.

---

### 3.12 LOW — Inconsistent Error Counting in Enrichment

**File:** `backend/lambdas/enrichment/handler.py:228-229`

Location-filtered jobs (valid behavior, not an error) are counted as `total_errors += 1`. This inflates the error metric and could trigger false alarms.

**Fix:** Add a separate `total_filtered` counter for location/salary filtering.

---

## Priority Summary

| Priority | Count | Key Items |
|----------|-------|-----------|
| **Critical** | 4 | CORS wildcard, full-dataset pagination, broken daily report query, missing frontend files |
| **High** | 7 | No API throttling, no API WAF, SQS unencrypted, no CloudFront headers, N+1 purge, sync Glassdoor fetch, Glassdoor config mismatch |
| **Medium** | 10 | Input validation, error leaks, request validators, IPv6, enrichment batch failures, X-Ray, put vs update, lockfile, error boundary, CSP |
| **Low** | 5 | Log retention, S3 versioning, Lambda layers, unused crawlers, error counting |

---

*Generated from full codebase review of Scout project — Terraform, Python backend, React frontend.*
