# Scout Backend - Technical Specification

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         EVENT SOURCES                            │
├──────────┬──────────┬──────────┬──────────┬────────┬────────────┤
│ LinkedIn │  Indeed  │Glassdoor │ZipRecr.  │  Dice  │ Scheduled  │
│ (JobSpy) │ (JobSpy) │ (JobSpy) │ (JobSpy) │(Custom)│ (EventBr.) │
└──────────┴──────────┴──────────┴──────────┴────────┴─────┬──────┘
                                                            │
                          ┌─────────────────────────────────┘
                          ↓
                    ┌──────────────┐
                    │ SQS Queue    │
                    │(Raw Jobs)    │
                    └──────┬───────┘
                           │
                           ↓
                    ┌──────────────────┐
                    │ Enrichment       │
                    │ Lambda (SQS)     │
                    │ - Dedup          │
                    │ - Benefits       │
                    │ - Ratings        │
                    └──────┬───────────┘
                           │
        ┌──────────────────┴──────────────────┐
        ↓                                      ↓
   ┌─────────────┐              ┌──────────────────────┐
   │ DynamoDB    │              │ Glassdoor Cache      │
   │ scout-jobs  │              │ (7-day TTL)          │
   │ (60-day TTL)│              └──────────────────────┘
   └──────┬──────┘
          │
    ┌─────┴─────────────────────────────────────┐
    │                                            │
    ↓                                            ↓
┌──────────────┐                      ┌────────────────┐
│ API Gateway  │                      │ EventBridge    │
│ (Cognito)    │                      │ (Scheduled)    │
├──────────────┤                      ├────────────────┤
│ GET /jobs    │                      │ Daily Crawl    │
│ GET /jobs/:id│                      │ Daily Report   │
│ PATCH status │                      │ Weekly Report  │
│ GET settings │                      │ Daily Purge    │
│ PUT settings │                      └────────────────┘
└──────┬───────┘                              │
       │                                      ↓
       │                       ┌──────────────────────┐
       │                       │ Reports Lambda       │
       │                       │ - daily_report       │
       │                       │ - weekly_report      │
       │                       └──────┬───────────────┘
       │                              │
       └──────────────┬───────────────┘
                      ↓
              ┌──────────────┐
              │ DynamoDB     │
              │ scout-users  │
              │ scout-status │
              └──────┬───────┘
                     │
                     ↓
              ┌──────────────┐
              │ SES Email    │
              │ (Reports)    │
              └──────────────┘
```

## Data Models

### Job (DynamoDB: scout-jobs)
```python
{
    "PK": "JOB#{hash}",                    # Partition key (job hash)
    "SK": "SOURCE#{source}#{url_hash}",    # Sort key (source uniqueness)
    
    # Core fields
    "job_hash": "sha256(...)",             # SHA256 of title|company|location
    "source": "linkedin|indeed|...",       # Job board source
    "title": "Security Engineer",          # Job title (normalized)
    "company": "Example Corp",             # Company name (normalized)
    "location": "Atlanta, GA",             # Location (normalized)
    
    # Salary information
    "salary_min": 180000,                  # Minimum salary (int or null)
    "salary_max": 220000,                  # Maximum salary (int or null)
    
    # URL and description
    "job_url": "https://...",              # Full URL to job posting
    "description": "We are looking...",    # Job description (2000 chars max)
    
    # Job details
    "job_type": "Full-time",               # Employment type
    "date_posted": "2025-04-09T...",       # ISO date posted
    
    # Enrichment
    "rating": 4.2,                         # Glassdoor rating (float or null)
    "benefits": {"PTO", "401k", "..."},   # Set of benefits found
    
    # Metadata
    "created_at": "2025-04-09T12:34Z",    # When scraped
    "crawled_at": "2025-04-09T12:34Z",    # Crawler timestamp
    "ttl": 1755555555,                     # Unix timestamp (60 days out)
}
```

### UserStatus (DynamoDB: scout-user-status)
```python
{
    "PK": "USER#{cognito_sub}",            # Partition key
    "SK": "JOB#{job_hash}",                # Sort key
    
    # User info
    "user_id": "USER#{cognito_sub}",       # Duplicate of PK
    "job_id": "JOB#{job_hash}",            # Duplicate of SK
    
    # Status tracking
    "status": "APPLIED",                   # See APPLICATION_STATUSES
    "notes": "Waiting for phone screen",   # Optional notes
    
    # Timestamps
    "created_at": "2025-04-09T12:34Z",    # First status set
    "updated_at": "2025-04-09T12:34Z",    # Last update
}
```

### UserSettings (DynamoDB: scout-users)
```python
{
    "PK": "USER#{cognito_sub}",            # Partition key
    
    # User info
    "user_id": "USER#{cognito_sub}",       # Duplicate of PK
    "email": "user@example.com",           # Email for reports
    
    # Preferences
    "daily_report": true,                  # Daily job email
    "weekly_report": true,                 # Weekly pipeline email
    
    # Timestamps
    "created_at": "2025-04-09T12:34Z",    # Account creation
    "updated_at": "2025-04-09T12:34Z",    # Last settings update
}
```

### GlassdoorCache (DynamoDB: scout-glassdoor-cache)
```python
{
    "PK": "google",                        # company_normalized (lowercase)
    
    # Rating data
    "rating": 3.8,                         # Glassdoor rating (float or null)
    "last_checked": "2025-04-09T...",     # When rating was fetched
    
    # TTL
    "ttl": 1755555555,                     # Unix timestamp (7 days out)
}
```

## API Specifications

### List Jobs
```http
GET /jobs?dateRange=7d&minRating=3.5&status=APPLIED&sort=salary&page=1&pageSize=20

Response:
{
    "jobs": [
        {
            "PK": "JOB#...",
            "title": "Security Engineer",
            "company": "Acme Corp",
            "salary_min": 180000,
            "salary_max": 220000,
            "rating": 4.2,
            "user_status": "NOT_APPLIED",
            ...
        }
    ],
    "total": 45,
    "page": 1,
    "pageSize": 20,
    "hasMore": true
}
```

### Get Single Job
```http
GET /jobs/{jobId}

Response:
{
    "PK": "JOB#...",
    "title": "Security Engineer",
    "company": "Acme Corp",
    "job_url": "https://...",
    "description": "...",
    "user_status": "APPLIED",
    ...
}
```

### Update Application Status
```http
PATCH /jobs/{jobId}/status
Content-Type: application/json

{
    "status": "APPLIED",
    "notes": "Phone interview scheduled"
}

Response:
{
    "user_id": "USER#...",
    "job_id": "JOB#...",
    "status": "APPLIED",
    "updated_at": "2025-04-09T...",
    "notes": "Phone interview scheduled"
}
```

### Get User Settings
```http
GET /user/settings

Response:
{
    "user_id": "USER#...",
    "email": "user@example.com",
    "daily_report": true,
    "weekly_report": false
}
```

### Update User Settings
```http
PUT /user/settings
Content-Type: application/json

{
    "email": "newemail@example.com",
    "daily_report": true,
    "weekly_report": true
}

Response:
{
    "user_id": "USER#...",
    "email": "newemail@example.com",
    "daily_report": true,
    "weekly_report": true,
    "updated_at": "2025-04-09T..."
}
```

## Processing Pipelines

### Crawler → Enrichment Flow
1. Crawler runs on EventBridge schedule
2. Searches 10 roles × 2 locations = 20 searches
3. JobSpy returns 50 results per search (max 1000 raw jobs)
4. Filters jobs below $180k salary minimum
5. Sends remaining jobs to SQS queue as JSON messages
6. Each crawler publishes metrics: jobs_sent, errors

### SQS → Enrichment Flow
1. Enrichment Lambda polls SQS (batch size 10, window 5s)
2. For each message:
   a. Parse JSON job data
   b. Normalize: title case, clean company/location
   c. Hash: SHA256(title|company|location) → job_hash
   d. Dedup: Try conditional put with attribute_not_exists(PK)
   e. Skip if job already exists (ConditionalCheckFailedException)
   f. Extract benefits: Regex patterns in description
   g. Fetch Glassdoor rating: Check cache, scrape if miss
   h. Store in DynamoDB with TTL
   i. Log: processed count, stored count, duplicates, errors

### Report Generation Flow
1. EventBridge triggers daily/weekly report Lambda
2. Query user preferences: daily_report=true or weekly_report=true
3. For each subscribed user:
   a. Fetch recent jobs (24h for daily, 7d for weekly)
   b. Query user's application statuses
   c. Build HTML email from template
   d. Send via SES
   e. Log: emails sent count
4. Gracefully continue on per-user failures

## Performance Characteristics

### Crawler Functions
- **Duration**: 30-120 seconds per crawler (depends on JobSpy)
- **Memory**: 512 MB sufficient
- **Concurrency**: Sequential execution (one crawler per role/location)
- **Cost**: ~$0.20/day for 5 crawlers

### Enrichment Lambda
- **Batch size**: 10 messages from SQS
- **Duration**: 5-30 seconds per batch
- **Memory**: 256 MB sufficient
- **Throughput**: ~100 jobs/second possible
- **Glassdoor cache**: Reduces external API calls by 90%+

### API Handlers
- **Duration**: 100-500 ms per request
- **Memory**: 256 MB sufficient
- **Query performance**: DynamoDB on-demand, <100ms typical
- **Pagination**: Max 1000 items per query (client should limit)

### Report Lambda
- **Duration**: 10-30 seconds per report type
- **Email generation**: <100ms per email
- **SES sending**: ~200ms per email
- **Total daily/weekly cost**: <$0.20

## Rate Limiting & Quotas

### JobSpy Crawling
- ~50 results per search (configurable)
- 10 roles × 2 locations = 20 concurrent searches
- Max ~1000 raw jobs per crawl cycle
- No API key required (best effort scraping)

### SES Email
- Default quota: 50,000 emails/day
- Bounce limit: 5% (monitoring required)
- Complaint limit: 0.1% (monitoring required)

### DynamoDB (On-Demand)
- Read: $1.25 per million reads
- Write: $6.25 per million writes
- Expected: <10 million ops/month for single user

### Lambda Concurrency
- Default: 1000 concurrent executions
- Crawler functions: Sequential (1 at a time)
- API functions: Auto-scaling (burst to 100s)
- Reports: 2 sequential (daily + weekly separate)

## Error Handling Strategy

### Crawlers
- If JobSpy fails: Log error, continue next role
- If SQS send fails: Retry built into boto3
- If quota exceeded: Graceful timeout, log warning

### Enrichment
- If JSON parse fails: Skip message, log, continue
- If DynamoDB write fails: Retry (conditional check is not an error)
- If Glassdoor fetch fails: Continue without rating
- If benefits extraction fails: Skip, store without benefits

### API
- Missing Cognito claims: 401 Unauthorized
- Invalid parameters: 400 Bad Request
- Missing jobId: 404 Not Found
- DynamoDB failures: 500 Internal Server Error

### Reports
- Missing user email: Skip user, continue
- SES send fails: Log error, continue next user
- DynamoDB queries fail: Retry with exponential backoff

## Monitoring & Alerts

### CloudWatch Metrics
```
/aws/lambda/scout-linkedin:
  - Invocations
  - Duration (Max: 300s)
  - Errors
  - Throttles

/aws/lambda/scout-enrichment:
  - Invocations
  - Duration (Max: 60s)
  - Errors
  - Lambda concurrent executions (Max: 10)

/aws/lambda/scout-api-*:
  - Invocations
  - Duration (Max: 30s)
  - Errors
  - 4xx errors (400, 401, 404)
  - 5xx errors (500)
```

### Recommended Alarms
- Crawler duration > 300 seconds
- Enrichment error rate > 5%
- API 5xx errors > 1%
- SQS queue depth > 1000 messages
- DynamoDB write throttling events
- SES bounce rate > 5%

### Logging
- All functions log to CloudWatch
- Log level: INFO in production, DEBUG available
- Log format: JSON with timestamps and error context
- Retention: 30 days default (adjust as needed)

## Security Considerations

### Authentication
- Cognito JWT in API Gateway authorizer
- User sub extracted from claims
- All API endpoints require valid token

### Authorization
- Users can only access their own statuses
- No cross-user data leakage
- DynamoDB queries scoped to user_id

### Credential Management
- AWS credentials: IAM roles (no hardcoding)
- SES: Email verified in AWS account
- Secrets Manager: API keys if needed (for future sources)

### Data Protection
- DynamoDB encryption at rest (AWS-managed)
- TLS for all AWS API calls
- Email data in transit: SES handles encryption
- No PII in logs (user sub only)

### Disaster Recovery
- DynamoDB point-in-time recovery (enable in production)
- SQS dead-letter queue for failed messages
- CloudWatch logs retention for audit trail
- Backup: Regular DynamoDB exports to S3 recommended

## Cost Optimization

### Current Implementation
- Lambda: Pay per 100ms, 512MB minimum
- DynamoDB: On-demand (pay per 1M ops)
- SQS: Free tier covers most usage
- SES: $0.10 per 1000 emails

### Optimization Opportunities
1. **Lambda memory**: Tune memory per function for optimal cost/performance
2. **DynamoDB**: Switch to provisioned if traffic is predictable
3. **Glassdoor cache**: Increase TTL to reduce external calls
4. **Crawler frequency**: Reduce from daily to every 2-3 days if acceptable
5. **Archived jobs**: Export to S3 after 60 days instead of delete

### Estimated Monthly Costs (Single User)
```
Lambda compute:      ~$5
DynamoDB:           ~$10
SQS:                ~$0
SES:                ~$1
Total:              ~$16/month (very low volume)
```

Scales linearly with job volume and user count.
