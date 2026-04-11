# Scout — Job Aggregation & Application Tracker

**Live URL:** https://scout.carniaux.io

Scout is a serverless AWS platform that crawls five major job boards daily (LinkedIn, Indeed, Glassdoor, ZipRecruiter, Dice) for senior security and cloud architecture roles paying $180k+, deduplicates results, enriches them with Glassdoor company ratings, and presents everything in a secure web dashboard with per-user application tracking and automated email reports.

---

## Table of Contents

- [Project Goal](#project-goal)
- [Architecture Overview](#architecture-overview)
- [Technology Stack](#technology-stack)
- [Repository Structure](#repository-structure)
- [Backend — File-by-File Reference](#backend--file-by-file-reference)
  - [Shared Modules](#shared-modules-backendlambdasshared)
  - [Crawlers](#crawlers-backendlambdascrawlers)
  - [Enrichment Pipeline](#enrichment-pipeline-backendlambdasenrichment)
  - [API Handlers](#api-handlers-backendlambdasapi)
  - [Email Reports](#email-reports-backendlambdasreports)
  - [Build Script](#build-script-backendbuildsh)
- [Frontend — File-by-File Reference](#frontend--file-by-file-reference)
  - [Entry Points](#entry-points)
  - [Pages](#pages)
  - [Components](#components)
  - [Hooks](#hooks)
  - [Services](#services)
  - [Types](#types)
  - [Configuration](#configuration)
- [Infrastructure — Terraform Modules](#infrastructure--terraform-modules)
  - [Root Configuration](#root-configuration-terraform)
  - [Auth Module](#auth-module-terraformmodulesauth)
  - [Data Module](#data-module-terraformmodulesdata)
  - [API Module](#api-module-terraformmodulesapi)
  - [Crawl Module](#crawl-module-terraformmodulescrawl)
  - [Email Module](#email-module-terraformmodulesemail)
  - [Frontend Module](#frontend-module-terraformmodulesfrontend)
  - [Monitoring Module](#monitoring-module-terraformmodulesmonitoring)
- [CI/CD Pipelines](#cicd-pipelines)
- [Database Schema](#database-schema)
- [API Contract](#api-contract)
- [Deployment Guide](#deployment-guide)
  - [Prerequisites](#prerequisites)
  - [Step 1 — Bootstrap the AWS Account](#step-1--bootstrap-the-aws-account)
  - [Step 2 — Enable Remote Terraform State](#step-2--enable-remote-terraform-state)
  - [Step 3 — First Terraform Apply](#step-3--first-terraform-apply)
  - [Step 4 — Add GitHub Repository Secrets](#step-4--add-github-repository-secrets)
  - [Step 5 — Push to Trigger CI/CD](#step-5--push-to-trigger-cicd)
  - [Step 6 — Verify SES Sending Domain](#step-6--verify-ses-sending-domain)
  - [Step 7 — Create Your First User](#step-7--create-your-first-user)
  - [Step 8 — Add Scraping Credentials](#step-8--add-scraping-credentials)
- [Day-to-Day Operations](#day-to-day-operations)
- [Environment Variables Reference](#environment-variables-reference)
- [Security Posture](#security-posture)
- [Cost Estimate](#cost-estimate)
- [Troubleshooting](#troubleshooting)

---

## Project Goal

Scout was built to solve a specific problem: monitoring five job boards daily for senior-level security and cloud architecture roles, without manually checking each site. It filters by a salary floor ($180k), deduplicates across sources, and lets users track their application pipeline — all from a single dashboard.

The project also serves as a hands-on AWS learning vehicle covering serverless compute, event-driven architecture, infrastructure-as-code, and CI/CD with GitHub Actions OIDC.

**Target roles:** Security Engineer, Security Architect, Solutions Architect, Network Security Architect, Cloud Security Architect, Cloud Architect, CISO, Chief Information Security Officer, Deputy CISO, VP Information Security.

**Target locations:** Atlanta, GA (25-mile radius) and United States (remote only).

---

## Architecture Overview

```
 INTERNET
    |
 CloudFront + WAF (OWASP rules + 300 req/5min rate-limit)
    +-- S3 --> React SPA (scout.carniaux.io)
    +-- API Gateway (REST, Cognito authorizer)
         +-- GET  /jobs                 Lambda: api-get-jobs
         +-- GET  /jobs/{id}            Lambda: api-get-jobs
         +-- PATCH /jobs/{id}/status    Lambda: api-update-status
         +-- GET|PUT /user/settings     Lambda: api-user-settings
                  |
              DynamoDB
              +-- scout-jobs              (TTL 60d, DateIndex GSI, RatingIndex GSI)
              +-- scout-user-status       (StatusIndex GSI)
              +-- scout-users
              +-- scout-glassdoor-cache   (TTL 7d)

 EventBridge cron 02:00 EST daily
    +-- Step Functions (parallel state machine)
         +-- crawler-linkedin       (JobSpy)
         +-- crawler-indeed         (JobSpy)
         +-- crawler-glassdoor      (Oxylabs + BeautifulSoup)
         +-- crawler-ziprecruiter   (Oxylabs + BeautifulSoup)
         +-- crawler-dice           (Oxylabs + BeautifulSoup)
         |        +-- SQS raw-jobs --> Lambda enrichment (dedup + benefits + rating)
         +-- Lambda purge (TTL-expired cleanup)

 EventBridge cron 07:00 EST daily  --> Lambda daily-report  --> SES
 EventBridge cron 08:00 EST Sat    --> Lambda weekly-report  --> SES
```

**Data flow:** Crawlers fetch rendered search result pages, parse job listings, apply salary filtering, and send qualifying jobs to SQS. The enrichment Lambda deduplicates by content hash, extracts benefits keywords, looks up Glassdoor ratings (cached 7 days), and writes to DynamoDB with a 60-day TTL. The API serves jobs from DynamoDB via a DateIndex GSI, and the React frontend displays them with filtering, sorting, and pagination.

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Tailwind CSS 3.4, Vite, AWS Amplify (auth SDK) |
| Authentication | Amazon Cognito (User Pool, TOTP MFA required, multi-user) |
| API | Amazon API Gateway (REST) with Cognito authorizer |
| Compute | AWS Lambda (Python 3.12), 13 functions total |
| Orchestration | AWS Step Functions (parallel state machine) |
| Queue | Amazon SQS (raw jobs queue + dead-letter queue) |
| Database | Amazon DynamoDB (on-demand, 4 tables, 3 GSIs) |
| Scraping | JobSpy (LinkedIn, Indeed), Oxylabs Web Scraper Realtime API (Glassdoor, ZipRecruiter, Dice) |
| Email | Amazon SES (DKIM-signed, daily + weekly reports) |
| CDN / Hosting | Amazon CloudFront + S3 (OAC, no public bucket) |
| Security | AWS WAFv2 (OWASP rules + rate limiting), TLS 1.2+ |
| DNS | Amazon Route 53 (scout.carniaux.io) |
| Monitoring | Amazon CloudWatch (alarms, dashboard), Amazon SNS (alerts) |
| Secrets | AWS Secrets Manager (scraping credentials) |
| IaC | Terraform 1.14+ (7 modules, S3 remote state) |
| CI/CD | GitHub Actions (OIDC auth, no long-lived AWS keys) |

---

## Repository Structure

```
scout/
+-- terraform/                    # Infrastructure-as-Code
|   +-- main.tf                   # Root module — wires all child modules
|   +-- providers.tf              # AWS provider + S3 remote state backend
|   +-- variables.tf              # Input variables
|   +-- outputs.tf                # 20+ outputs for CI/CD
|   +-- modules/
|       +-- auth/                 # Cognito User Pool, MFA, app client
|       +-- data/                 # DynamoDB tables (4 tables, 3 GSIs)
|       +-- api/                  # API Gateway + 3 Lambda handlers
|       +-- crawl/                # Step Functions, SQS, 7 Lambdas, EventBridge
|       +-- email/                # SES, 2 report Lambdas, EventBridge schedules
|       +-- frontend/             # S3, CloudFront, WAF, Route53 record
|       +-- monitoring/           # SNS, CloudWatch alarms, dashboard
|
+-- backend/
|   +-- lambdas/
|   |   +-- crawlers/             # 5 crawlers + diagnose + purge
|   |   |   +-- linkedin.py       # JobSpy-based LinkedIn crawler
|   |   |   +-- indeed.py         # JobSpy-based Indeed crawler
|   |   |   +-- glassdoor.py      # Oxylabs + two-phase parser
|   |   |   +-- ziprecruiter.py   # Oxylabs + two-phase parser
|   |   |   +-- dice.py           # Oxylabs + two-phase parser
|   |   |   +-- diagnose.py       # Read-only diagnostic Lambda
|   |   |   +-- purge.py          # TTL cleanup + orphan removal
|   |   +-- enrichment/
|   |   |   +-- handler.py        # SQS-triggered dedup + benefits + ratings
|   |   +-- api/
|   |   |   +-- get_jobs.py       # GET /jobs and GET /jobs/{jobId}
|   |   |   +-- update_status.py  # PATCH /jobs/{jobId}/status
|   |   |   +-- user_settings.py  # GET/PUT /user/settings
|   |   +-- reports/
|   |   |   +-- daily_report.py   # Daily email — new jobs summary
|   |   |   +-- weekly_report.py  # Weekly email — pipeline + new jobs
|   |   +-- shared/
|   |       +-- models.py         # Data models, constants, serialization
|   |       +-- db.py             # DynamoDB helper wrapper
|   |       +-- crawler_utils.py  # Salary parsing, proxy config, normalization
|   |       +-- oxylabs_client.py # Oxylabs Realtime API client
|   |       +-- response.py       # API Gateway response builders
|   |       +-- email_templates.py# HTML email template generators
|   +-- requirements.txt          # Python dependencies
|   +-- build.sh                  # Lambda packaging script
|
+-- frontend/
|   +-- src/
|   |   +-- main.tsx              # React entry point + QueryClient
|   |   +-- App.tsx               # Root component, routing, Amplify auth
|   |   +-- amplifyconfiguration.ts # Cognito config from env vars
|   |   +-- index.css             # Tailwind directives + dark mode overrides
|   |   +-- pages/
|   |   |   +-- Dashboard.tsx     # Main job listing page with filters
|   |   |   +-- Settings.tsx      # User notification preferences
|   |   +-- components/
|   |   |   +-- Navbar.tsx        # Top nav, auth, theme toggle, mobile menu
|   |   |   +-- FilterBar.tsx     # Date range, rating, status, search, sort
|   |   |   +-- JobList.tsx       # Paginated job list with loading/error states
|   |   |   +-- JobCard.tsx       # Individual job card with status tracking
|   |   |   +-- StatusSelect.tsx  # Application status dropdown
|   |   |   +-- StatusBadge.tsx   # Color-coded status badge
|   |   |   +-- RatingBadge.tsx   # Glassdoor rating with star icon
|   |   |   +-- EmptyState.tsx    # Empty results placeholder
|   |   +-- hooks/
|   |   |   +-- useJobs.ts        # React Query hooks (5 hooks)
|   |   |   +-- useTheme.ts       # Dark/light theme with localStorage
|   |   +-- services/
|   |   |   +-- api.ts            # Authenticated API client (5 methods)
|   |   +-- types/
|   |       +-- index.ts          # TypeScript interfaces and type unions
|   +-- public/
|   |   +-- favicon.svg           # Scout magnifying glass icon
|   +-- package.json
|   +-- vite.config.ts
|   +-- tsconfig.json
|   +-- .env.example
|
+-- .github/workflows/
|   +-- deploy.yml                # Full CI/CD: Terraform + backend + frontend
|   +-- deploy-frontend.yml       # Frontend-only: build + S3 sync + invalidation
|
+-- scripts/
|   +-- bootstrap.sh              # One-time account setup (state bucket, OIDC role)
|
+-- SCOUT-architecture.md         # Detailed architecture design document
+-- README.md                     # This file
```

---

## Backend — File-by-File Reference

### Shared Modules (`backend/lambdas/shared/`)

#### `models.py` — Data Models and Constants

Defines the core data structures, application constants, and DynamoDB serialization helpers used across all Lambda functions.

**Constants:**

- `APPLICATION_STATUSES` — The seven valid application pipeline states: `NOT_APPLIED`, `NOT_INTERESTED`, `APPLIED`, `RECRUITER_INTERVIEW`, `TECHNICAL_INTERVIEW`, `OFFER_RECEIVED`, `OFFER_ACCEPTED`.
- `ROLE_QUERIES` — The ten target job titles to search for: Security Engineer, Security Architect, Solutions Architect, Network Security Architect, Cloud Security Architect, Cloud Architect, CISO, Chief Information Security Officer, Deputy CISO, VP Information Security.
- `LOCATIONS` — Two search locations: Atlanta GA (25-mile radius, on-site) and United States (remote only).
- `SALARY_MINIMUM` — The minimum salary threshold: $180,000.

**Dataclasses:**

- `Job` — Represents a crawled job listing with fields for source, title, company, location, salary range, URL, description, type, rating, benefits, and timestamps. Methods: `to_dict()` strips None values; `to_dynamo()` converts lists to DynamoDB sets.
- `UserStatus` — Tracks a user's application status for a specific job (user_id, job_id, status, notes, timestamps).
- `UserSettings` — Stores user preferences (user_id, email, daily_report toggle, weekly_report toggle).

**Functions:**

- `dynamo_deserialize(data)` — Converts DynamoDB response types to standard Python types. Handles `Decimal` to `int`/`float`, `set` to `list`, and recurses into nested dicts.
- `dynamo_serialize(data)` — Converts Python types to DynamoDB-compatible types. Converts `float`/`int` to `Decimal`, string lists to `set`, and omits `None` values.

---

#### `db.py` — DynamoDB Helper

A wrapper around the `boto3` DynamoDB Table resource that standardizes error handling and simplifies common operations.

**Class: `DynamoDBHelper`**

- `__init__(region="us-east-1")` — Creates a boto3 DynamoDB resource.
- `get_table(table_name)` — Returns a Table resource.
- `get_item(table_name, key)` — Fetches a single item by primary key. Returns the item dict or `None`.
- `put_item(table_name, item, condition_expression=None)` — Writes an item, optionally with a conditional expression (used for deduplication via `attribute_not_exists(pk)`).
- `update_item(table_name, key, update_expression, expression_attribute_values, condition_expression=None)` — Updates an item and returns the new state (`ALL_NEW`).
- `query(table_name, key_condition_expression, expression_attribute_values, ...)` — Queries a table or GSI with support for index_name, limit, pagination (exclusive_start_key), and sort order. Returns `(items, last_evaluated_key)`.
- `scan(table_name, filter_expression=None, ...)` — Full table scan with optional filtering. Returns `(items, last_evaluated_key)`.
- `batch_write(table_name, items_to_put, items_to_delete=None)` — Batch writes up to 25 items per batch using the DynamoDB batch writer context manager.
- `delete_item(table_name, key)` — Deletes a single item by primary key.

---

#### `crawler_utils.py` — Crawler Utilities

Helper functions shared by all crawler Lambdas for secrets management, salary parsing, text normalization, and salary filtering.

**Functions:**

- `get_scraper_secrets()` — Retrieves scraping credentials from AWS Secrets Manager (`SECRETS_ARN` env var). Caches the result for the lifetime of the Lambda container. Returns an empty dict on failure.
- `_parse_proxy_strings()` — Parses a comma-separated proxy list from the secrets payload into individual proxy URL strings.
- `get_proxy_list()` — Builds a proxy list for JobSpy, filtering out Oxylabs proxies (their TLS interception is incompatible with JobSpy's direct connections).
- `extract_salary_min(job)` — Extracts the minimum salary from a JobSpy job object. Handles the `min_amount` field, string parsing, and regex extraction from description text.
- `extract_salary_max(job)` — Extracts the maximum salary from a JobSpy job object using the same strategies.
- `normalize_title(title)` — Applies title-case normalization.
- `normalize_company(company)` — Trims whitespace.
- `normalize_location(location)` — Applies title-case and trims whitespace.
- `meets_salary_requirement(salary_min, minimum_threshold=180000)` — Returns `True` if the salary meets the threshold. Critically, returns `True` when salary is `None` — jobs without salary data are kept rather than discarded.

---

#### `oxylabs_client.py` — Oxylabs Web Scraper Client

A synchronous HTTP client for the Oxylabs Web Scraper Realtime API, used by the Glassdoor, ZipRecruiter, and Dice crawlers.

**Constants:**

- `REALTIME_URL` — `https://realtime.oxylabs.io/v1/queries`
- `DEFAULT_TIMEOUT` — 105 seconds
- `MAX_RETRIES` — 2 (3 total attempts with exponential backoff)

**Class: `OxylabsClient`**

- `__init__()` — Initializes the client by retrieving Oxylabs credentials from Secrets Manager.
- `_extract_credentials(secrets)` — Static method that extracts the Oxylabs username and password from the secrets dict. Supports both explicit `oxylabs_username`/`oxylabs_password` keys and legacy proxy-string parsing (`user:pass@host:port`).
- `fetch_page(url, render=True, geo_location="United States", timeout=105)` — Sends a request to Oxylabs Realtime API with `source: "universal"` and `render: "html"`. Retries on timeout, server errors (5xx), and Oxylabs target-site errors (6xx) using exponential backoff. Returns the fully rendered HTML string or `None` on failure.

---

#### `response.py` — API Response Builders

Standardized response constructors for API Gateway Lambda proxy integration.

**Functions:**

- `get_cors_headers()` — Builds CORS headers using the `SITE_URL` environment variable as the allowed origin.
- `cors_response(status_code, body)` — Constructs a complete Lambda proxy response with JSON body and CORS headers.
- `success_response(body=None, status_code=200)` — Returns a success response. Defaults to `{"success": true}` if no body is provided.
- `error_response(message, status_code=400)` — Returns an error response with the given message.
- `not_found_response(message="Not found")` — 404 response.
- `unauthorized_response(message="Unauthorized")` — 401 response.
- `forbidden_response(message="Forbidden")` — 403 response.

---

#### `email_templates.py` — HTML Email Templates

Generates responsive HTML emails for daily and weekly reports.

**Functions:**

- `base_template(title, body_html, footer="")` — Wraps content in a responsive HTML email layout with a gradient header, styled table, source badges, and footer. Returns a complete HTML document.
- `jobs_table_html(jobs)` — Renders a list of jobs as an HTML table with columns: Role & Company, Location, Salary, Rating, Source. Includes salary formatting ($180K–$220K style) and color-coded source badges.
- `status_summary_html(status_groups)` — Renders the application pipeline as grouped tables by status with count headers.
- `daily_report_email(jobs, date)` — Builds the daily report email: job count header, jobs table. Returns complete HTML.
- `weekly_report_email(status_groups, new_jobs_count, date)` — Builds the weekly report: pipeline summary, new job count, grouped status tables. Returns complete HTML.

---

### Crawlers (`backend/lambdas/crawlers/`)

Scout uses two scraping strategies depending on each job board's anti-bot protections:

| Source | Strategy | Reason |
|--------|----------|--------|
| LinkedIn | JobSpy (direct) | Guest API access, no anti-bot |
| Indeed | JobSpy (direct) | No significant rate limiting |
| Glassdoor | Oxylabs + BeautifulSoup | Cloudflare WAF blocks direct requests (400) |
| ZipRecruiter | Oxylabs + BeautifulSoup | Cloudflare WAF blocks direct requests (403) |
| Dice | Oxylabs + BeautifulSoup | Heavy JS rendering, not supported by JobSpy |

Oxylabs-based crawlers use a **two-phase resilient parser** pattern: Phase 1 tries specific CSS selectors for structured extraction; Phase 2 falls back to generic link-based extraction if Phase 1 fails. This guards against CSS selector rot — when a site redesigns, Phase 2 continues extracting jobs while the first card's HTML is dumped to CloudWatch for debugging.

---

#### `linkedin.py` — LinkedIn Crawler

Uses JobSpy to crawl LinkedIn's guest job search API.

**`handler(event, context)`** — Iterates over all role queries and locations. For each combination, calls `scrape_jobs()` with `site_name=["linkedin"]`, `results_wanted=50`, `hours_old=24`. For each result: extracts salary, checks the minimum requirement, deduplicates by URL within the run, and sends qualifying jobs to SQS. Returns `{statusCode, source, jobs_sent, errors}`.

---

#### `indeed.py` — Indeed Crawler

Uses JobSpy to crawl Indeed.

**`handler(event, context)`** — Same pattern as LinkedIn. Calls `scrape_jobs()` with `site_name=["indeed"]`, `country_indeed="USA"`, `results_wanted=50`, `hours_old=24`. Applies proxy list if configured. Returns `{statusCode, source, jobs_sent, errors}`.

---

#### `glassdoor.py` — Glassdoor Crawler

Uses Oxylabs Web Scraper API to fetch fully rendered Glassdoor search pages, then parses with BeautifulSoup.

**Functions:**

- `_build_search_url(role, location, distance, is_remote)` — Constructs a Glassdoor search URL with keyword, location, remote filter, radius, and date sorting parameters.
- `_parse_salary(text)` — Parses salary strings like "$180K - $220K". Converts "K" format to full amounts and validates against a 30k–1M range.
- `_extract_text(element, selectors)` — Tries a list of CSS selectors against a BeautifulSoup element and returns the first non-empty text match.
- `_parse_jobs_from_html(html)` — **Two-phase parser.** Phase 1 tries specific selectors: `li[data-test='jobListing']`, `li.react-job-listing`, `[data-brandviews*='JOB_CARD']`. Phase 2 falls back to finding all `a[href*='/job-listing/']` links and extracting title/company/location from the parent context. Dumps the first card's HTML to CloudWatch for debugging.
- `handler(event, context)` — Initializes OxylabsClient, iterates over roles/locations, fetches pages, parses jobs, deduplicates, and sends to SQS. Returns `{statusCode, source, jobs_sent, errors}`.

---

#### `ziprecruiter.py` — ZipRecruiter Crawler

Uses Oxylabs Web Scraper API with the same two-phase parser pattern.

**Functions:**

- `_build_search_url(role, location, distance, is_remote)` — Constructs a ZipRecruiter search URL with search query, location, radius, remote flag, and `days=1` for recent postings.
- `_parse_salary(text)` — Parses salary from "$180,000 - $220,000 a year" format. Detects hourly rates (value < 500) and converts to annual using 2,080 hours.
- `_extract_text(element, selectors)` — CSS selector fallback chain.
- `_parse_jobs_from_html(html)` — **Two-phase parser.** Phase 1 tries: `article.job_result`, `[data-testid='job-card']`, `[data-job-id]`. Phase 2 falls back to `a[href*='/jobs/']` links filtered to minimum 30-character length. Dumps first card HTML.
- `handler(event, context)` — Same orchestration pattern as Glassdoor.

---

#### `dice.py` — Dice Crawler

Uses Oxylabs Web Scraper API. Dice is not supported by JobSpy.

**Functions:**

- `_build_search_url(role, location, distance, is_remote)` — Constructs a Dice search URL with query, `countryCode=US`, `datePosted=1` (last 24 hours), and `remoteFilter=2` for remote jobs.
- `_parse_salary(text)` — Parses salary with hourly detection. Converts hourly (value < 500) to annual (2,080 factor), "K" format to full amounts.
- `_extract_text_near(element, selectors)` — Tries CSS selectors against an element, returns first non-empty text.
- `_find_closest_text(link, tag_names, max_depth=4)` — Walks up the DOM tree from a link element, searching siblings and parent children for text in specified tag names. Used in Phase 2 to find company/location near a job link.
- `_parse_jobs_from_html(html)` — **Two-phase parser.** Phase 1 tries: `dhi-search-card`, `[data-cy='search-card']`, `.card.search-card`, and container children. Phase 2 falls back to `a[href*='/job-detail/']` links with context extraction. Dumps first card HTML.
- `handler(event, context)` — Same orchestration pattern as Glassdoor.

---

#### `diagnose.py` — Crawler Diagnostics

A read-only diagnostic Lambda for testing all crawlers without writing to SQS. Useful for verifying connectivity, parsing, and salary filtering after changes.

**Functions:**

- `_test_jobspy_source(site_name, jobspy_name, role, location_config)` — Tests a JobSpy-based source (Indeed). Reports: fetch duration, status, jobs found, jobs with salary, jobs meeting the salary filter, a sample job, and DataFrame columns.
- `_test_oxylabs_source(source, role, location_config)` — Tests an Oxylabs-based source (Glassdoor, ZipRecruiter, Dice). Dynamically imports the correct crawler module. Reports: Oxylabs initialization status, test URL, fetch duration, HTML size, jobs found, parse status, salary analysis, and HTML diagnostics for empty results.
- `handler(event, context)` — Accepts optional `{sources: ["dice"], role: "Cloud Architect"}` input. Defaults to all five sources and "Cloud Security Architect". Checks secrets availability, runs diagnostics for each source, and returns a detailed report. **Does not write to SQS.**

**Invocation:**

```bash
aws lambda invoke --function-name scout-crawl-diagnose /tmp/out.json
cat /tmp/out.json | python3 -m json.tool
```

---

#### `purge.py` — Cleanup Lambda

Runs as the final step in the Step Functions crawl pipeline to clean up expired data.

**`handler(event, context)`** — Scans the jobs table for items whose `ttl` is less than the current epoch time and deletes them in batches. Then scans the user-status table, checks whether each referenced job still exists, and deletes orphaned status records. Returns `{statusCode, jobs_deleted, statuses_deleted}`.

---

### Enrichment Pipeline (`backend/lambdas/enrichment/`)

#### `handler.py` — SQS-Triggered Job Enrichment

Processes raw job messages from SQS, deduplicates, enriches with benefits and ratings, and stores in DynamoDB.

**Functions:**

- `compute_job_hash(title, company, location, job_url="")` — Generates a SHA256 hash for deduplication. When the company is missing or "Unknown" (common with LinkedIn), the job URL is used as the primary dedup key. Otherwise, uses `title|company|location`.
- `extract_benefits(description)` — Regex-based extraction of benefits from job descriptions. Detects: PTO, Sick Days, 401(k), Medical, Dental, Vision, HSA, FSA, Tuition Reimbursement, Remote Work, Stock Options. Returns a sorted list.
- `fetch_glassdoor_rating(company, cache_table)` — Fetches a Glassdoor company rating. Checks the DynamoDB cache first (7-day TTL). On cache miss, attempts a best-effort scrape of Glassdoor search results for a `companyRating` JSON field. Caches both successful ratings and failed lookups.
- `handler(event, context)` — Processes each SQS record: parses JSON, validates required fields (title + job_url), normalizes company to "Unknown" if missing, computes the job hash, builds the DynamoDB item with `pk=JOB#{hash}`, `sk=SOURCE#{source}#{url_md5}`, `gsi1pk=JOB`, and `postedDate` (date-only ISO string, falling back to today). Extracts benefits, fetches the Glassdoor rating (best effort), and performs a conditional put (`attribute_not_exists(pk)`) to skip duplicates. Sets a 60-day TTL. Returns `{statusCode, processed, stored, duplicates, errors}`.

---

### API Handlers (`backend/lambdas/api/`)

#### `get_jobs.py` — Job Listing and Detail API

Handles `GET /jobs` (list with filtering) and `GET /jobs/{jobId}` (single job detail).

**Functions:**

- `get_user_sub(event)` — Extracts the Cognito user `sub` from the API Gateway authorizer claims.
- `get_date_range_start(date_range)` — Converts a date range parameter ("24h", "7d", "30d") to a date-only ISO string (`YYYY-MM-DD`). Uses date-only format to match the enrichment Lambda's `postedDate` storage format.
- `serialize_job(item)` — Maps DynamoDB field names to the camelCase shape the frontend expects. Strips the `JOB#` prefix from `pk` to get the bare job ID. Cleans sentinel strings ("nan", "None", "") to `null`.
- `filter_jobs(jobs, user_id, min_rating, status_filter, sort_by)` — Fetches user application statuses from the user-status table, filters jobs by minimum Glassdoor rating and application status, attaches the user's status to each job, and sorts by date (default), salary, or rating.
- `list_jobs(event, context)` — Parses query parameters (dateRange, minRating, status, sort, page, pageSize), queries the DateIndex GSI (`gsi1pk=JOB AND postedDate >= start`), deserializes, filters, paginates, and returns `{jobs, total, page, pageSize, hasMore}`.
- `get_single_job(event, context)` — Queries by `pk=JOB#{jobId}`, fetches the user's application status, and returns the serialized job.
- `handler(event, context)` — Routes to `get_single_job` or `list_jobs` based on the presence of a `jobId` path parameter.

---

#### `update_status.py` — Application Status Update API

Handles `PATCH /jobs/{jobId}/status`.

**`handler(event, context)`** — Extracts the user sub and job ID, validates the request body (`status` must be one of `APPLICATION_STATUSES`, optional `notes`), and writes to the user-status table with `pk=USER#{sub}`, `sk=JOB#{jobId}`. Returns the updated status record.

---

#### `user_settings.py` — User Settings API

Handles `GET /user/settings` and `PUT /user/settings`.

**Functions:**

- `validate_email(email)` — Regex validation of email format.
- `get_settings(event, context)` — Queries the users table by `pk=USER#{sub}`. Returns user preferences or defaults if not found.
- `put_settings(event, context)` — Validates the email, writes settings to the users table with `created_at` (first write) and `updated_at`, and returns the updated settings.
- `handler(event, context)` — Routes to `get_settings` or `put_settings` based on HTTP method.

---

### Email Reports (`backend/lambdas/reports/`)

#### `daily_report.py` — Daily New Jobs Email

Triggered by EventBridge at 07:00 EST daily.

**`handler(event, context)`** — Queries the jobs table for items created in the last 24 hours via the DateIndex GSI. Scans the users table for users with `daily_report=True`. For each user with a verified email, generates a `daily_report_email` HTML template and sends it via SES. Returns `{statusCode, emails_sent, jobs_found}`.

---

#### `weekly_report.py` — Weekly Pipeline Summary Email

Triggered by EventBridge at 08:00 EST every Saturday.

**`handler(event, context)`** — Finds users with `weekly_report=True`. For each user: queries the user-status table for all their application statuses, groups jobs by status (NOT_APPLIED, APPLIED, RECRUITER_INTERVIEW, etc.), fetches job details for each group, queries new jobs from the last 7 days, generates a `weekly_report_email` HTML template, and sends via SES. Returns `{statusCode, emails_sent}`.

---

### Build Script (`backend/build.sh`)

Packages Lambda functions and dependencies into deployment zip files.

**Behavior:**

1. Validates Python syntax across all `.py` files (compile check).
2. Builds four code packages: `crawlers.zip`, `enrichment.zip`, `api.zip`, `reports.zip` — each includes its own handler(s) plus the `shared/` module.
3. Builds `dependencies-layer.zip` — pip-installs all requirements into a Lambda layer structure (`python/lib/python3.12/site-packages/`).
4. Outputs all artifacts to `build/`.

---

## Frontend — File-by-File Reference

### Entry Points

#### `src/main.tsx` — Application Entry Point

Imports React, ReactDOM, and the QueryClient provider. Configures React Query with a 5-minute stale time and 10-minute garbage collection time. Mounts the `App` component to the `#root` div, wrapped in `React.StrictMode` and `QueryClientProvider`.

---

#### `src/App.tsx` — Root Component

Configures AWS Amplify with Cognito credentials from `amplifyconfiguration.ts`. Wraps the app in Amplify's `<Authenticator>` component which gates all access behind login. Inside the auth guard, sets up `<BrowserRouter>` with two routes: `/` (Dashboard) and `/settings` (Settings). Renders the `<Navbar>` above all routes. Supports dark mode via Tailwind's `dark:` prefix on the root background.

---

### Pages

#### `src/pages/Dashboard.tsx` — Main Job Listing Page

The primary page. Reads filter state from URL search params (making filters bookmark-shareable). Calls the `useJobs` hook with the current filters, page number, and page size. Renders a header with job count, last-updated timestamp, and refresh button; the `FilterBar` component; and the `JobList` component. Resets to page 1 on any filter change.

---

#### `src/pages/Settings.tsx` — User Preferences Page

Displays the user's email (read-only from Cognito) and two toggles for daily and weekly email reports. Uses `useSettings` to fetch current preferences and `useUpdateSettings` to persist changes. Shows a 3-second success toast on save.

---

### Components

#### `src/components/Navbar.tsx` — Navigation Bar

Top navigation with responsive mobile menu. Desktop view shows logo/home link, Dashboard and Settings navigation links, user email, dark/light theme toggle (Sun/Moon icons from lucide-react), and Sign Out button. Mobile view collapses to a hamburger menu. Uses `useTheme()` for theme management and Amplify's `useAuthenticator()` for sign-out and `fetchUserAttributes()` for email display.

---

#### `src/components/FilterBar.tsx` — Filter Controls

Provides filtering controls: date range buttons (24h, 7d, 30d), minimum Glassdoor rating slider (1–5, 0.5 step), application status dropdown (all 7 statuses), text search input (searches role, company, location), sort dropdown (Most Recent, Highest Salary, Best Rated), and a clear-all button showing the active filter count. All changes call `onFiltersChange` to update the parent's URL state.

---

#### `src/components/JobList.tsx` — Paginated Job List

Renders three states: loading (3 animated skeleton cards), error (red error box with retry button), or data (grid of `JobCard` components with pagination). Pagination footer shows items-per-page selector (10, 20, 50), current/total page display, previous/next buttons, and total count. Includes an `EmptyState` component when the filtered result is empty.

---

#### `src/components/JobCard.tsx` — Job Listing Card

Displays a single job with: role name and application status dropdown in the header; company name, Glassdoor rating badge, source badge (color-coded by source), location, posted date (relative — "2 days ago"), salary range, and "View Posting" external link in the meta row; benefits pills (PTO, 401k, Medical, Remote Work, etc.) when present; and truncated notes. Calls `useUpdateStatus` when the status dropdown changes.

---

#### `src/components/StatusSelect.tsx` — Status Dropdown

A styled `<select>` for changing application status. Border color changes by status (slate for NOT_APPLIED, blue for APPLIED, amber for RECRUITER_INTERVIEW, green for OFFER_ACCEPTED, etc.). Supports disabled state.

---

#### `src/components/StatusBadge.tsx` — Status Badge (Display Only)

A read-only inline badge showing the application status with color-coded background and text. Used in contexts where the status should be visible but not editable.

---

#### `src/components/RatingBadge.tsx` — Glassdoor Rating Badge

Displays a star icon and numeric rating (or "N/A"). Color-coded: green for 4.0+, yellow for 3.0–4.0, red for below 3.0, gray for unavailable. Optionally wraps in an anchor tag linking to the Glassdoor company page.

---

#### `src/components/EmptyState.tsx` — Empty State Placeholder

Reusable UI for when no results match the current filters. Shows a search icon, configurable title and description, and an optional action button (typically "Clear Filters").

---

### Hooks

#### `src/hooks/useJobs.ts` — React Query Data Hooks

Five custom hooks built on `@tanstack/react-query`:

- `useJobs(filters, page, pageSize)` — Queries the job listing API with current filters. Query key includes all parameters for automatic cache management. 5-minute stale time.
- `useJob(jobId)` — Fetches a single job by ID. 5-minute stale time.
- `useUpdateStatus()` — Mutation that calls `api.updateStatus()`. On success, invalidates all job queries to refresh the list with the updated status.
- `useSettings()` — Fetches user notification preferences. 10-minute stale time.
- `useUpdateSettings()` — Mutation that calls `api.updateSettings()`. On success, updates the settings query cache with the response data.

---

#### `src/hooks/useTheme.ts` — Theme Management

Manages the light/dark theme toggle with `localStorage` persistence. Initializes from `localStorage['scout-theme']`, falls back to `prefers-color-scheme` system preference, defaults to light. Toggles the `dark` class on the `<html>` element for Tailwind's class-based dark mode strategy.

---

### Services

#### `src/services/api.ts` — Authenticated API Client

Provides an `api` object with five methods that handle Cognito authentication transparently.

**Internal helper: `authFetch(url, options)`** — Fetches the current Cognito ID token via `fetchAuthSession()`, adds it to the `Authorization` header, and performs the fetch. Throws on non-OK responses.

**Methods:**

- `api.getJobs(filters, page, pageSize)` — `GET /jobs` with query parameters: dateRange, minRating, status, search, sort, page, pageSize. Maps the response to `PaginatedResponse<Job>`.
- `api.getJob(jobId)` — `GET /jobs/{jobId}`. Returns a single `Job`.
- `api.updateStatus(jobId, status, notes?)` — `PATCH /jobs/{jobId}/status`. Sends `{status, notes}` in the body.
- `api.getSettings()` — `GET /user/settings`. Returns `UserSettings`.
- `api.updateSettings(settings)` — `PUT /user/settings`. Sends the settings object. Returns the updated `UserSettings`.

---

### Types

#### `src/types/index.ts` — TypeScript Definitions

- `Job` — 20 fields: jobId, roleName, company, location, salaryMin/Max, ptoDays, sickDays, match401k, benefits, postedDate, sourceUrl, source (union: linkedin | indeed | glassdoor | ziprecruiter | dice), glassdoorRating, glassdoorUrl, createdAt, applicationStatus, notes.
- `ApplicationStatus` — Union type with 7 values: NOT_APPLIED, NOT_INTERESTED, APPLIED, RECRUITER_INTERVIEW, TECHNICAL_INTERVIEW, OFFER_RECEIVED, OFFER_ACCEPTED.
- `DateRange` — Union type: '24h' | '7d' | '30d'.
- `JobFilters` — Object with optional fields: dateRange, minRating, status, search, sort.
- `UserSettings` — Object: email, dailyReport (boolean), weeklyReport (boolean).
- `PaginatedResponse<T>` — Generic: items (T[]), totalCount, page, pageSize, hasMore.

---

### Configuration

#### `src/amplifyconfiguration.ts` — Amplify Auth Config

Exports the Amplify configuration object pointing to the Cognito User Pool. Reads `VITE_USER_POOL_ID` and `VITE_USER_POOL_CLIENT_ID` from Vite environment variables.

#### `src/index.css` — Global Styles

Imports Tailwind CSS directives (base, components, utilities). Overrides Amplify UI form styling for dark mode. Adds a global `transition-colors` (200ms) and custom pulse animation for loading skeletons.

#### `.env.example` — Environment Variable Template

```
VITE_USER_POOL_ID=us-east-1_XXXXXXXXX
VITE_USER_POOL_CLIENT_ID=XXXXXXXXX
VITE_API_URL=https://XXXXXXXXX.execute-api.us-east-1.amazonaws.com/v1
```

---

## Infrastructure — Terraform Modules

All infrastructure is defined in Terraform 1.14+ with an S3 remote state backend and DynamoDB state locking.

### Root Configuration (`terraform/`)

#### `providers.tf`

Configures the AWS provider (us-east-1), the `random` provider (for Cognito domain suffix), and the `archive` provider (for Lambda packaging). Defines the S3 backend for remote state (`scout-tfstate-<account-id>`, encrypted, DynamoDB locking via `scout-tflock`). Applies default tags (Project, Environment, ManagedBy, CreatedAt) to all resources.

#### `variables.tf`

| Variable | Default | Description |
|----------|---------|-------------|
| `project_name` | `"scout"` | Resource naming prefix |
| `environment` | `"prod"` | Environment tag |
| `aws_region` | `"us-east-1"` | AWS region |
| `domain_name` | `"carniaux.io"` | Root domain (must exist in Route 53) |
| `subdomain` | `"scout"` | App subdomain (scout.carniaux.io) |
| `alert_email` | (required) | CloudWatch alarm recipient |
| `ses_verified_domain` | `"carniaux.io"` | SES sending domain |
| `job_retention_days` | `60` | DynamoDB TTL in days |
| `crawl_schedule` | `"cron(0 7 * * ? *)"` | Daily crawl (07:00 UTC = 02:00 EST) |
| `daily_report_schedule` | `"cron(0 12 * * ? *)"` | Daily email (12:00 UTC = 07:00 EST) |
| `weekly_report_schedule` | `"cron(0 13 ? * SAT *)"` | Weekly email (Sat 13:00 UTC = 08:00 EST) |

#### `main.tf`

Looks up the Route 53 hosted zone for `carniaux.io`, provisions an ACM certificate for `scout.carniaux.io` with DNS validation, and wires together all seven infrastructure modules.

#### `outputs.tf`

Exports 20+ values consumed by CI/CD: CloudFront distribution domain/ID, S3 bucket name, Cognito User Pool ID/ARN/Client ID/domain, API Gateway URL/ID, all 4 DynamoDB table names/ARNs, Step Functions state machine ARN, SQS queue URL, SES domain identity ARN, SNS alert topic ARN, CloudWatch dashboard URL, and the app URL.

---

### Auth Module (`terraform/modules/auth/`)

Provisions Amazon Cognito for user authentication.

**Resources:**

- `aws_cognito_user_pool.main` — Email as username, password policy (12+ chars, all character types required), **TOTP MFA required** (software token), email verification on signup, account recovery via verified email.
- `aws_cognito_user_pool_domain.main` — Hosted UI domain with random 8-character suffix.
- `aws_cognito_user_pool_client.spa` — SPA client (no client secret). Auth flows: `USER_SRP_AUTH`, `REFRESH_TOKEN_AUTH`. Token validity: 1 hour (access + ID), 30 days (refresh). User existence errors suppressed.

---

### Data Module (`terraform/modules/data/`)

Provisions four DynamoDB tables, all PAY_PER_REQUEST with point-in-time recovery.

See [Database Schema](#database-schema) below for details.

---

### API Module (`terraform/modules/api/`)

Provisions the REST API Gateway and three API Lambda functions.

**Resources:**

- `aws_api_gateway_rest_api.main` — The `scout-api` REST API.
- Cognito authorizer linked to the User Pool.
- API routes with CORS: `GET /jobs`, `GET /jobs/{jobId}`, `PATCH /jobs/{jobId}/status`, `GET|PUT /user/settings`, `OPTIONS` preflight on all.
- Three Lambda functions: `scout-api-get-jobs` (30s, 256MB), `scout-api-update-status` (30s, 256MB), `scout-api-user-settings` (30s, 256MB).
- IAM role with DynamoDB access (GetItem, Query, Scan, PutItem, UpdateItem, DeleteItem) on all three user-facing tables.
- Stage `v1` with access logging (requestId, IP, latency, error).

---

### Crawl Module (`terraform/modules/crawl/`)

Provisions the crawl pipeline: Step Functions, SQS, Lambda crawlers, enrichment, purge, and EventBridge schedule.

**Resources:**

- `aws_sqs_queue.raw_jobs` — Visibility timeout 900s, retention 1 day, max receive 3 before DLQ.
- `aws_sqs_queue.raw_jobs_dlq` — Dead-letter queue.
- `aws_secretsmanager_secret.scraper_keys` — Stores Oxylabs credentials.
- `aws_sfn_state_machine.crawl` — Parallel state machine with 5 crawler branches (each retries 1x on failure), followed by the purge Lambda. Error states catch failures without stopping the pipeline.
- Seven Lambda functions: 5 crawlers + diagnose (all 900s timeout, 512MB) + enrichment (300s, 512MB, SQS trigger with batch size 10, 5s batching window, partial failure reporting).
- `aws_lambda_function.purge` — 60s timeout, 256MB.
- EventBridge rule triggering the state machine daily at 02:00 EST.
- Four IAM roles: crawler (SQS send + Secrets Manager), enrichment (SQS receive/delete + DynamoDB put/update/get + Secrets Manager), purge (DynamoDB scan/delete), Step Functions (Lambda invoke), EventBridge (StartExecution).

---

### Email Module (`terraform/modules/email/`)

Provisions SES email sending and report Lambda functions.

**Resources:**

- `aws_ses_domain_identity.main` — Domain identity for carniaux.io.
- Route 53 records: TXT (domain verification), 3 CNAMEs (DKIM).
- `aws_ses_domain_identity_verification.main` — Waits for verification.
- Two Lambda functions: `scout-daily-report` and `scout-weekly-report` (both 60s, 256MB).
- IAM role with DynamoDB read access (Query, Scan, GetItem on 3 tables + GSIs) and SES SendEmail.
- Two EventBridge rules: daily at 07:00 EST, Saturday at 08:00 EST.

---

### Frontend Module (`terraform/modules/frontend/`)

Provisions the static hosting infrastructure.

**Resources:**

- `aws_s3_bucket.frontend` — Frontend assets bucket (prevent_destroy lifecycle). Public access fully blocked.
- `aws_s3_bucket_policy` — CloudFront OAC access only.
- `aws_cloudfront_origin_access_control.main` — OAC with SigV4.
- `aws_cloudfront_distribution.main` — Default root object `index.html`, custom error responses (403/404 return index.html for SPA routing), redirect HTTP to HTTPS, TLSv1.2_2021, gzip compression, CachingOptimized policy. Attached to WAFv2 ACL.
- `aws_wafv2_web_acl.main` — Two rules: AWSManagedRulesCommonRuleSet (OWASP top 10 protections) and rate limiting (300 requests per 5 minutes per IP).
- `aws_route53_record.cloudfront` — A record alias: scout.carniaux.io pointing to CloudFront.

---

### Monitoring Module (`terraform/modules/monitoring/`)

Provisions observability and alerting.

**Resources:**

- `aws_sns_topic.alerts` — Scout alerts topic with email subscription.
- **5 CloudWatch alarms:**
  - Per-crawler Lambda errors (threshold: 3+ errors in 1 hour, one alarm per crawler).
  - API Gateway 5xx errors (threshold: 5+ errors in 5 minutes).
  - DLQ messages visible (threshold: 1+).
  - SES bounce rate (threshold: 5+ bounces in 1 hour).
- `aws_cloudwatch_dashboard.main` — Four-widget dashboard: Lambda/API overview, crawler errors by function, SQS queue metrics, SES send/delivery/bounce/complaint metrics.

---

## CI/CD Pipelines

### `deploy.yml` — Full Deployment Pipeline

Triggers on push to `main` when `terraform/**`, `backend/**`, or `frontend/**` change, or via manual `workflow_dispatch` (plan/apply/destroy).

**Jobs (executed in DAG order):**

1. **terraform** — Runs `init`, `fmt -check`, `validate`, `plan`, and conditionally `apply`. Exports outputs (Cognito IDs, API URL, S3 bucket, CloudFront ID) for downstream jobs.
2. **backend-test** (parallel with terraform) — Installs Python dependencies, runs `ruff check` linting, and validates syntax compilation for all `.py` files.
3. **frontend-deploy** (depends on terraform) — Installs Node dependencies, builds the React app with Vite (injecting Cognito and API env vars), syncs to S3 (hashed assets get 1-year cache, index.html gets no-cache), and invalidates CloudFront.
4. **backend-deploy** (depends on terraform + backend-test) — Runs `build.sh`, uploads the dependency layer to S3, publishes a new Lambda layer version, and deploys all 13 Lambda functions (5 crawlers + diagnose + enrichment + 3 API + 2 reports + purge).

**Authentication:** GitHub Actions OIDC — no long-lived AWS access keys stored as secrets.

---

### `deploy-frontend.yml` — Frontend-Only Deployment

Triggers on push to `main` when only `frontend/**` changes, or via manual dispatch. Runs lint, builds, syncs to S3, and invalidates CloudFront. Lighter and faster than the full pipeline.

---

## Database Schema

### `scout-jobs` — Job Listings

| Attribute | Type | Description |
|-----------|------|-------------|
| `pk` | String (partition key) | `JOB#{sha256_hash}` |
| `sk` | String (sort key) | `SOURCE#{source}#{url_md5}` |
| `gsi1pk` | String | Always `"JOB"` — shared partition for DateIndex and RatingIndex |
| `postedDate` | String | ISO date (`YYYY-MM-DD`) — DateIndex range key |
| `job_hash` | String | SHA256 hash of title+company+location or URL |
| `source` | String | linkedin, indeed, glassdoor, ziprecruiter, dice |
| `title` | String | Job title |
| `company` | String | Company name (defaults to "Unknown") |
| `location` | String | City, State |
| `salary_min` | Number | Minimum salary (nullable) |
| `salary_max` | Number | Maximum salary (nullable) |
| `job_url` | String | Original posting URL |
| `description` | String | Job description (truncated to 2,000 chars) |
| `job_type` | String | Full-time, Part-time, etc. (nullable) |
| `date_posted` | String | Original posting date |
| `benefits` | StringSet | Extracted benefits (PTO, Medical, 401(k), etc.) |
| `rating` | Number | Glassdoor company rating (nullable) |
| `created_at` | String | ISO timestamp of when Scout stored the job |
| `crawled_at` | String | ISO timestamp of the crawl run |
| `ttl` | Number | Epoch timestamp — auto-deletes after 60 days |

**GSIs:** DateIndex (`gsi1pk` + `postedDate`, descending), RatingIndex (`gsi1pk` + `glassdoorRating`).

---

### `scout-user-status` — Application Tracking

| Attribute | Type | Description |
|-----------|------|-------------|
| `pk` | String (partition key) | `USER#{cognito_sub}` |
| `sk` | String (sort key) | `JOB#{job_hash}` |
| `status` | String | One of 7 application statuses |
| `notes` | String | User's notes (nullable) |
| `created_at` | String | ISO timestamp |
| `updated_at` | String | ISO timestamp |

**GSI:** StatusIndex (`pk` + `status`).

---

### `scout-users` — User Preferences

| Attribute | Type | Description |
|-----------|------|-------------|
| `pk` | String (partition key) | `USER#{cognito_sub}` |
| `email` | String | User's email |
| `daily_report` | Boolean | Daily email opt-in |
| `weekly_report` | Boolean | Weekly email opt-in |
| `created_at` | String | ISO timestamp |
| `updated_at` | String | ISO timestamp |

---

### `scout-glassdoor-cache` — Rating Cache

| Attribute | Type | Description |
|-----------|------|-------------|
| `pk` | String (partition key) | Lowercase company name |
| `rating` | Number | Glassdoor rating (nullable — null means lookup failed) |
| `last_checked` | String | ISO timestamp of last lookup |
| `ttl` | Number | Epoch timestamp — auto-expires after 7 days |

---

## API Contract

All endpoints require a Cognito ID token in the `Authorization` header. CORS is enabled for the configured `SITE_URL`.

### `GET /jobs`

List jobs with filtering and pagination.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dateRange` | query | `30d` | `24h`, `7d`, or `30d` |
| `minRating` | query | — | Minimum Glassdoor rating (float) |
| `status` | query | — | Filter by application status |
| `search` | query | — | Text search (role, company, location) |
| `sort` | query | `date` | `date`, `salary`, or `rating` |
| `page` | query | `1` | Page number |
| `pageSize` | query | `20` | Items per page (10, 20, 50) |

**Response:**

```json
{
  "jobs": [
    {
      "jobId": "abc123...",
      "roleName": "Cloud Security Architect",
      "company": "Acme Corp",
      "location": "Atlanta, GA",
      "source": "linkedin",
      "sourceUrl": "https://linkedin.com/jobs/view/...",
      "postedDate": "2026-04-10",
      "salaryMin": 190000,
      "salaryMax": 240000,
      "glassdoorRating": 4.2,
      "benefits": ["PTO", "Medical", "401(k)", "Remote Work"],
      "applicationStatus": "NOT_APPLIED"
    }
  ],
  "total": 47,
  "page": 1,
  "pageSize": 20,
  "hasMore": true
}
```

### `GET /jobs/{jobId}`

Returns a single job with full details and the user's application status.

### `PATCH /jobs/{jobId}/status`

**Request body:**

```json
{
  "status": "APPLIED",
  "notes": "Applied through company portal on 2026-04-11"
}
```

### `GET /user/settings`

Returns user notification preferences: `{email, dailyReport, weeklyReport}`.

### `PUT /user/settings`

**Request body:**

```json
{
  "email": "user@example.com",
  "dailyReport": true,
  "weeklyReport": true
}
```

---

## Deployment Guide

### Prerequisites

| Tool | Minimum Version |
|------|----------------|
| AWS CLI | 2.x, configured with admin credentials |
| Terraform | 1.14+ |
| Node.js | 20 LTS |
| Python | 3.12 |
| Git | any |

Your AWS account must already have the `carniaux.io` hosted zone in Route 53. Terraform looks it up by name — it does not create it.

---

### Step 1 — Bootstrap the AWS Account

Run once per AWS account:

```bash
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh
```

This creates: an S3 bucket for Terraform remote state (`scout-tfstate-<account-id>`), a DynamoDB table for state locking (`scout-tflock`), a GitHub OIDC provider in IAM, and an IAM role `scout-github-actions` with least-privilege policies.

The script prints the values you need for subsequent steps.

---

### Step 2 — Enable Remote Terraform State

Edit `terraform/providers.tf` and uncomment the `backend "s3"` block, filling in the bucket name from bootstrap.sh:

```hcl
backend "s3" {
  bucket         = "scout-tfstate-<your-account-id>"
  key            = "prod/terraform.tfstate"
  region         = "us-east-1"
  encrypt        = true
  dynamodb_table = "scout-tflock"
}
```

Initialize:

```bash
cd terraform
terraform init
```

---

### Step 3 — First Terraform Apply

```bash
terraform plan -var="alert_email=your@email.com"
terraform apply -var="alert_email=your@email.com"
```

This takes about 10–15 minutes (ACM certificate validation is the slow part). Note these outputs:

```bash
terraform output cognito_user_pool_id
terraform output cognito_user_pool_client_id
terraform output api_gateway_url
terraform output frontend_bucket_name
terraform output cloudfront_distribution_id
```

---

### Step 4 — Add GitHub Repository Secrets

Go to your repo, then Settings, then Secrets and variables, then Actions, and add:

| Secret | Value |
|--------|-------|
| `AWS_DEPLOY_ROLE_ARN` | From bootstrap.sh output |
| `ALERT_EMAIL` | Your email for CloudWatch alarms |
| `COGNITO_USER_POOL_ID` | From `terraform output` |
| `COGNITO_USER_POOL_CLIENT_ID` | From `terraform output` |
| `API_GATEWAY_URL` | From `terraform output` (include the `/v1` suffix) |
| `FRONTEND_BUCKET` | From `terraform output` |
| `CLOUDFRONT_DISTRIBUTION_ID` | From `terraform output` |

---

### Step 5 — Push to Trigger CI/CD

```bash
git add .
git commit -m "feat: initial Scout deployment"
git push origin main
```

Three GitHub Actions jobs run in sequence: Terraform apply, backend deploy (lint + build + Lambda updates), frontend deploy (build + S3 sync + CloudFront invalidation). Monitor progress under the Actions tab.

---

### Step 6 — Verify SES Sending Domain

Terraform creates the SES DNS records automatically, but the domain identity needs time to verify:

1. Go to **AWS Console, then SES, then Verified identities, then carniaux.io**.
2. If status is "Pending", wait up to 72 hours for DNS propagation.
3. Once verified, SES can send from the domain. New AWS accounts may also need to request production SES access.

---

### Step 7 — Create Your First User

Open https://scout.carniaux.io and click **Create account**. Cognito will verify your email, then prompt you to set up TOTP MFA with your authenticator app (Google Authenticator, Authy, 1Password, etc.). After login, go to Settings to configure email notification preferences.

---

### Step 8 — Add Scraping Credentials

For Glassdoor, ZipRecruiter, and Dice crawlers (which use Oxylabs):

```bash
aws secretsmanager put-secret-value \
  --secret-id scout-scraper-keys \
  --secret-string '{
    "oxylabs_username": "your-username",
    "oxylabs_password": "your-password"
  }'
```

LinkedIn and Indeed crawlers use JobSpy (no credentials needed). The `scout-scraper-keys` secret is created by Terraform — you only need to populate it with your Oxylabs credentials.

---

## Day-to-Day Operations

### Trigger a manual crawl

```bash
aws stepfunctions start-execution \
  --state-machine-arn $(cd terraform && terraform output -raw step_functions_state_machine_arn) \
  --name "manual-$(date +%s)"
```

### Run crawler diagnostics

```bash
aws lambda invoke --function-name scout-crawl-diagnose /tmp/out.json
cat /tmp/out.json | python3 -m json.tool
```

### Check Lambda logs

```bash
# Crawler logs (replace with desired source)
aws logs tail /aws/lambda/scout-crawler-linkedin --follow
aws logs tail /aws/lambda/scout-crawler-glassdoor --follow

# Enrichment
aws logs tail /aws/lambda/scout-enrichment --follow

# API
aws logs tail /aws/lambda/scout-api-get-jobs --follow
```

### Check DynamoDB job count

```bash
aws dynamodb scan --table-name scout-jobs --select COUNT --query 'Count'
```

### Check the dead-letter queue

```bash
aws sqs get-queue-attributes \
  --queue-url $(cd terraform && terraform output -raw sqs_dlq_url) \
  --attribute-names ApproximateNumberOfMessages
```

### Force CloudFront cache purge

```bash
aws cloudfront create-invalidation \
  --distribution-id $(cd terraform && terraform output -raw cloudfront_distribution_id) \
  --paths "/*"
```

---

## Environment Variables Reference

### Crawler Lambdas (5 crawlers + diagnose)

| Variable | Description |
|----------|-------------|
| `SQS_QUEUE_URL` | Raw jobs SQS queue URL |
| `SECRETS_ARN` | Secrets Manager ARN for Oxylabs credentials |

### Enrichment Lambda

| Variable | Description |
|----------|-------------|
| `JOBS_TABLE` | DynamoDB jobs table name |
| `GLASSDOOR_CACHE_TABLE` | DynamoDB Glassdoor cache table name |
| `SECRETS_ARN` | Secrets Manager ARN |

### API Lambdas (3 functions)

| Variable | Description |
|----------|-------------|
| `JOBS_TABLE` | DynamoDB jobs table name |
| `USER_STATUS_TABLE` | DynamoDB user-status table name |
| `USERS_TABLE` | DynamoDB users table name |
| `SITE_URL` | https://scout.carniaux.io (for CORS) |

### Report Lambdas (2 functions)

| Variable | Description |
|----------|-------------|
| `JOBS_TABLE` | DynamoDB jobs table name |
| `USERS_TABLE` | DynamoDB users table name |
| `USER_STATUS_TABLE` | DynamoDB user-status table name (weekly only) |
| `SES_SENDER_EMAIL` | scout@carniaux.io |
| `SITE_URL` | https://scout.carniaux.io |

### Purge Lambda

| Variable | Description |
|----------|-------------|
| `JOBS_TABLE` | DynamoDB jobs table name |
| `USER_STATUS_TABLE` | DynamoDB user-status table name |

### Frontend (.env)

| Variable | Description |
|----------|-------------|
| `VITE_USER_POOL_ID` | Cognito User Pool ID |
| `VITE_USER_POOL_CLIENT_ID` | Cognito App Client ID |
| `VITE_API_URL` | API Gateway URL (including `/v1`) |

---

## Security Posture

- **MFA required** for all users (TOTP software token — no SMS fallback).
- **CloudFront-only S3 access** via Origin Access Control (no public bucket policy).
- **WAFv2** with AWS Managed Rules (OWASP top 10) and IP-based rate limiting (300 requests per 5 minutes).
- **Least-privilege IAM** — each Lambda has its own role scoped to exactly the resources it needs.
- **Secrets in AWS Secrets Manager** — scraping credentials are never stored in environment variables or code.
- **DynamoDB encrypted at rest** with AWS-managed keys and point-in-time recovery enabled on all tables.
- **SES domain verification** with DKIM signing + SPF + DMARC.
- **TLS 1.2+ enforced** on CloudFront (TLSv1.2_2021 security policy).
- **GitHub Actions OIDC** — no long-lived AWS access keys stored as repository secrets.
- **Cognito token security** — user existence errors suppressed, SRP auth flow (password never leaves the client), 1-hour token lifetime.

---

## Cost Estimate

Estimated monthly cost for a handful of users with daily crawling:

| Service | Estimated Cost | Notes |
|---------|---------------|-------|
| Oxylabs Web Scraper | ~$30–35 | Dominant cost; per-request pricing |
| Lambda | ~$2–3 | 13 functions, mostly short-lived |
| DynamoDB | ~$1–2 | On-demand, low throughput |
| CloudFront | ~$1 | Minimal traffic |
| S3 | < $1 | Small frontend bundle |
| API Gateway | < $1 | Low request volume |
| SES | < $1 | A few emails per week |
| Route 53 | $0.50 | Hosted zone |
| Secrets Manager | $0.40 | 1 secret |
| CloudWatch | < $1 | Logs + alarms |
| **Total** | **~$40–45/month** | |

JobSpy (used for LinkedIn and Indeed) is free and open-source. The Oxylabs subscription for Glassdoor, ZipRecruiter, and Dice is the dominant cost driver.

---

## Troubleshooting

### Crawlers return 0 jobs

Run the diagnostic Lambda to isolate the issue:

```bash
aws lambda invoke --function-name scout-crawl-diagnose \
  --payload '{"sources": ["glassdoor"]}' /tmp/out.json
cat /tmp/out.json | python3 -m json.tool
```

Check the output for: Oxylabs initialization status, HTML size (0 means fetch failed), Phase 1 vs Phase 2 parse results, and the first card HTML dump. If Phase 1 finds cards but parses 0 jobs, CSS selectors have rotted — Phase 2 should still extract jobs via link fallback.

### Jobs don't appear on the website

The pipeline is: Crawlers send to SQS, Enrichment reads SQS and writes to DynamoDB, API reads DynamoDB, Frontend calls API. Check each stage:

1. **Crawlers:** Check CloudWatch logs for `jobs_sent` count. If 0, the crawlers aren't finding or parsing jobs.
2. **SQS:** Check the DLQ for failed messages: `aws sqs get-queue-attributes --queue-url <dlq-url> --attribute-names ApproximateNumberOfMessages`.
3. **Enrichment:** Check enrichment logs for `stored` vs `duplicates` vs `errors`. If all duplicates, the jobs already exist.
4. **DynamoDB:** Verify items exist: `aws dynamodb scan --table-name scout-jobs --select COUNT`.
5. **API:** Test directly: `curl -H "Authorization: Bearer <token>" https://scout.carniaux.io/v1/jobs`.
6. **Frontend:** Hard-refresh (Ctrl+Shift+R) to clear React Query cache, or click the Refresh button on the Dashboard.

### Cloudflare WAF blocks (403/400)

Glassdoor and ZipRecruiter use Cloudflare WAF which blocks direct requests. This is why these crawlers use Oxylabs (which handles anti-bot protections server-side). If you see 403/400 errors, verify your Oxylabs credentials are set in Secrets Manager.

### SES emails not sending

1. Verify the domain identity is confirmed in SES console.
2. Check if your account is still in SES sandbox mode (sandbox only sends to verified addresses).
3. Check the SES bounce alarm and CloudWatch logs for the report Lambdas.

### Terraform state lock

If a Terraform apply was interrupted, you may need to force-unlock the state:

```bash
terraform force-unlock <LOCK_ID>
```

The lock ID is shown in the error message.
