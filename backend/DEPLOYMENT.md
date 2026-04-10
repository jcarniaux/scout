# Scout Backend Deployment Guide

## Overview

Scout is an AWS serverless job aggregation platform that crawls multiple job boards (LinkedIn, Indeed, Glassdoor, ZipRecruiter, Dice) and provides a unified interface for job tracking and application management.

## Architecture

### Core Components

1. **Crawlers** (EventBridge-triggered)
   - LinkedIn, Indeed, Glassdoor, ZipRecruiter crawlers use JobSpy library
   - Dice crawler uses custom requests + BeautifulSoup scraping
   - Run on daily schedule
   - Send raw jobs to SQS queue

2. **Enrichment** (SQS-triggered)
   - Deduplicates jobs by title/company/location hash
   - Extracts benefits from job descriptions
   - Fetches Glassdoor ratings (with caching)
   - Stores enriched jobs in DynamoDB with 60-day TTL

3. **API** (API Gateway + Lambda)
   - GET /jobs - List jobs with filtering/pagination
   - GET /jobs/{jobId} - Get single job
   - PATCH /jobs/{jobId}/status - Update application status
   - GET /user/settings - Get user preferences
   - PUT /user/settings - Update user preferences
   - All endpoints require Cognito authentication

4. **Reports** (EventBridge-triggered)
   - Daily Report: New jobs from last 24 hours
   - Weekly Report: Application pipeline summary
   - Send via SES to subscribed users

5. **Maintenance**
   - Purge: Cleans up expired jobs and orphaned status records (daily)

## DynamoDB Tables

### scout-jobs (Main job listing table)
- PK: `JOB#{hash}` - job hash (sha256 of title|company|location)
- SK: `SOURCE#{source}#{url_hash}` - source and URL hash for uniqueness
- Attributes:
  - job_hash, source, title, company, location
  - salary_min, salary_max, job_url, date_posted, description
  - job_type, rating (Glassdoor), benefits (list)
  - created_at, crawled_at, ttl
- GSI: DateIndex (created_at, source)
- GSI: JobHashIndex (job_hash)
- TTL: 60 days

### scout-user-status (User application tracking)
- PK: `USER#{cognito_sub}` - user identifier
- SK: `JOB#{job_hash}` - job identifier
- Attributes:
  - user_id, job_id, status, notes, updated_at, created_at
- Application statuses:
  - NOT_APPLIED, APPLIED, RECRUITER_INTERVIEW
  - TECHNICAL_INTERVIEW, OFFER_RECEIVED, OFFER_ACCEPTED

### scout-users (User preferences)
- PK: `USER#{cognito_sub}`
- Attributes:
  - user_id, email, daily_report, weekly_report
  - created_at, updated_at

### scout-glassdoor-cache (Rating cache)
- PK: company_normalized - normalized company name
- Attributes:
  - company_normalized, rating, last_checked
  - ttl (7 days)

## Environment Variables

All Lambda functions require:
- `JOBS_TABLE` - scout-jobs table name
- `USER_STATUS_TABLE` - scout-user-status table name
- `USERS_TABLE` - scout-users table name
- `GLASSDOOR_CACHE_TABLE` - scout-glassdoor-cache table name
- `SQS_QUEUE_URL` - SQS queue URL for raw jobs
- `SES_SENDER_EMAIL` - sender email for reports (must be verified in SES)
- `SITE_URL` - Site URL for CORS and report links

## Deployment Steps

### 1. Prerequisites
- AWS Account with appropriate IAM permissions
- Python 3.12 runtime available
- AWS CLI configured
- Cognito User Pool created with app client
- SES email verified as sender

### 2. Build Lambda Packages

```bash
cd backend
chmod +x build.sh
./build.sh
```

This generates:
- `build/dependencies-layer.zip` - Python dependencies layer
- `build/crawlers.zip` - All crawler functions
- `build/enrichment.zip` - Enrichment Lambda
- `build/api.zip` - API handlers
- `build/reports.zip` - Report generators

### 3. Create DynamoDB Tables

```bash
# scout-jobs
aws dynamodb create-table \
  --table-name scout-jobs \
  --attribute-definitions \
    AttributeName=PK,AttributeType=S \
    AttributeName=SK,AttributeType=S \
    AttributeName=created_at,AttributeType=S \
    AttributeName=job_hash,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
  --global-secondary-indexes \
    IndexName=DateIndex,Keys=[{AttributeName=created_at,KeyType=RANGE},{AttributeName=PK,KeyType=HASH}],Projection={ProjectionType=ALL},ProvisionedThroughput={ReadCapacityUnits=5,WriteCapacityUnits=5} \
    IndexName=JobHashIndex,Keys=[{AttributeName=job_hash,KeyType=HASH}],Projection={ProjectionType=ALL},ProvisionedThroughput={ReadCapacityUnits=5,WriteCapacityUnits=5} \
  --time-to-live-specification AttributeName=ttl,Enabled=true \
  --billing-mode PAY_PER_REQUEST

# scout-user-status
aws dynamodb create-table \
  --table-name scout-user-status \
  --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST

# scout-users
aws dynamodb create-table \
  --table-name scout-users \
  --attribute-definitions AttributeName=PK,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

# scout-glassdoor-cache
aws dynamodb create-table \
  --table-name scout-glassdoor-cache \
  --attribute-definitions AttributeName=company_normalized,AttributeType=S \
  --key-schema AttributeName=company_normalized,KeyType=HASH \
  --time-to-live-specification AttributeName=ttl,Enabled=true \
  --billing-mode PAY_PER_REQUEST
```

### 4. Create SQS Queue

```bash
aws sqs create-queue \
  --queue-name scout-jobs-raw \
  --attributes VisibilityTimeout=300,MessageRetentionPeriod=1209600
```

### 5. Upload Lambda Layer

```bash
aws lambda publish-layer-version \
  --layer-name scout-dependencies \
  --zip-file fileb://build/dependencies-layer.zip \
  --compatible-runtimes python3.12
```

### 6. Create Lambda Functions

Create each function via AWS Console or CLI. Set:
- Runtime: Python 3.12
- Handler: See list below
- Environment variables (as documented above)
- Layers: Add scout-dependencies layer
- Timeout: 300 seconds (5 minutes) for crawlers, 30 seconds for API/reports
- Memory: 512 MB for crawlers, 256 MB for others

**Crawler Functions** (from `crawlers.zip`):
- `linkedin.handler`
- `indeed.handler`
- `glassdoor.handler`
- `ziprecruiter.handler`
- `dice.handler`
- `purge.handler` (maintenance)

**Enrichment Function** (from `enrichment.zip`):
- `handler.handler`
- Trigger: SQS (scout-jobs-raw queue)
- Batch size: 10
- Batch window: 5 seconds

**API Functions** (from `api.zip`):
- `get_jobs.handler` - GET /jobs, GET /jobs/{jobId}
- `update_status.handler` - PATCH /jobs/{jobId}/status
- `user_settings.handler` - GET/PUT /user/settings
- Trigger: API Gateway (HTTP)
- Authorization: Cognito

**Report Functions** (from `reports.zip`):
- `daily_report.handler`
- `weekly_report.handler`

### 7. Set Up EventBridge Rules

```bash
# Daily crawls at 8 AM UTC
aws events put-rule \
  --name scout-daily-crawl \
  --schedule-expression "cron(0 8 * * ? *)" \
  --state ENABLED

# Daily report at 9 AM UTC
aws events put-rule \
  --name scout-daily-report \
  --schedule-expression "cron(0 9 * * ? *)" \
  --state ENABLED

# Weekly report every Monday at 9 AM UTC
aws events put-rule \
  --name scout-weekly-report \
  --schedule-expression "cron(0 9 ? * MON *)" \
  --state ENABLED

# Daily cleanup at 2 AM UTC
aws events put-rule \
  --name scout-daily-purge \
  --schedule-expression "cron(0 2 * * ? *)" \
  --state ENABLED
```

Then add targets to each rule pointing to the appropriate Lambda functions.

### 8. Configure API Gateway

Create HTTP API with:
- Cognito authorizer pointing to your user pool
- Routes:
  - `GET /jobs` → get_jobs.handler
  - `GET /jobs/{jobId}` → get_jobs.handler
  - `PATCH /jobs/{jobId}/status` → update_status.handler
  - `GET /user/settings` → user_settings.handler
  - `PUT /user/settings` → user_settings.handler

## Monitoring

### CloudWatch Logs
- Each Lambda logs to `/aws/lambda/{function-name}`
- Check for errors during crawls and processing

### CloudWatch Metrics
- Monitor Lambda duration and errors
- Track SQS queue depth
- Monitor DynamoDB consumed capacity

### Alerts
- Set up SNS alarms for:
  - Failed crawler runs
  - High SQS queue depth
  - API errors
  - Email delivery failures

## Cost Optimization

- DynamoDB: Use on-demand billing for variable workloads
- Lambda: Optimize timeout and memory settings
- SES: Monitor send quota and bounce rates
- Requests to Glassdoor: Cache aggressively to minimize API calls

## Troubleshooting

### Jobs not appearing
1. Check crawler logs in CloudWatch
2. Verify SQS queue has messages
3. Check enrichment Lambda for errors
4. Ensure DynamoDB tables exist and have correct permissions

### API returning 401 Unauthorized
1. Verify Cognito user pool is configured
2. Check API Gateway authorizer settings
3. Ensure JWT tokens are valid

### Reports not sending
1. Check SES sender email is verified
2. Monitor SES bounce and complaint rates
3. Verify user email addresses are valid
4. Check daily_report/weekly_report Lambda logs

### High costs
1. Review DynamoDB consumed capacity
2. Optimize Lambda memory settings
3. Reduce crawler frequency if needed
4. Implement request throttling if needed

## Implementation Notes

- Job deduplication uses SHA256 hash of title + company + location
- Salary extraction handles multiple formats (min_amount, max_amount, string ranges)
- Benefits extraction uses regex patterns for common benefits
- Glassdoor ratings are cached with 7-day TTL to avoid repeated scraping
- All timestamps are in UTC (ISO 8601 format)
- DynamoDB uses attribute_not_exists conditions to skip duplicate jobs
