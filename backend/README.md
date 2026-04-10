# Scout Backend

Complete AWS serverless backend for Scout job aggregation platform.

## Project Structure

```
backend/
├── requirements.txt                  # Python dependencies
├── build.sh                         # Build script for packaging Lambdas
├── DEPLOYMENT.md                    # Deployment and setup guide
├── README.md                        # This file
│
└── lambdas/
    ├── shared/                      # Shared utilities
    │   ├── models.py               # Data models and constants
    │   ├── db.py                   # DynamoDB helper class
    │   ├── response.py             # API Gateway response builders
    │   ├── crawler_utils.py        # Crawler helper functions
    │   └── email_templates.py      # HTML email templates
    │
    ├── crawlers/                   # Job crawling functions
    │   ├── linkedin.py             # LinkedIn crawler (JobSpy)
    │   ├── indeed.py               # Indeed crawler (JobSpy)
    │   ├── glassdoor.py            # Glassdoor crawler (JobSpy)
    │   ├── ziprecruiter.py         # ZipRecruiter crawler (JobSpy)
    │   ├── dice.py                 # Dice crawler (custom scraping)
    │   └── purge.py                # Cleanup old jobs and statuses
    │
    ├── enrichment/                 # Job enrichment pipeline
    │   └── handler.py              # SQS-triggered enrichment processor
    │
    ├── api/                        # REST API endpoints
    │   ├── get_jobs.py            # List and get jobs
    │   ├── update_status.py        # Update application status
    │   └── user_settings.py        # User preferences management
    │
    └── reports/                    # Report generation
        ├── daily_report.py         # Daily new jobs email
        └── weekly_report.py        # Weekly pipeline summary email
```

## Key Features

### Crawlers
- **Multi-source**: LinkedIn, Indeed, Glassdoor, ZipRecruiter, Dice
- **Salary filtering**: Minimum $180k threshold (configurable)
- **Job deduplication**: SHA256 hash-based (title + company + location)
- **Best effort**: Graceful error handling for source failures

### Enrichment
- **Benefits extraction**: Regex-based extraction of 401k, PTO, health insurance, etc.
- **Ratings**: Glassdoor company ratings with 7-day cache
- **Deduplication**: Conditional put to skip duplicate jobs
- **TTL**: 60-day auto-expiration of jobs

### API
- **Cognito authentication**: All endpoints require valid JWT
- **Filtering**: By date range, Glassdoor rating, application status
- **Sorting**: By date (default), salary, or rating
- **Pagination**: Offset-based with configurable page size
- **User status tracking**: NOT_APPLIED, APPLIED, INTERVIEWING, OFFERS

### Reports
- **Daily**: New jobs from last 24 hours
- **Weekly**: Application pipeline summary
- **HTML emails**: Responsive design with styling
- **SES integration**: Verified sender email required

## Technology Stack

- **Runtime**: Python 3.12
- **AWS Services**:
  - Lambda (Compute)
  - DynamoDB (Database)
  - SQS (Queue)
  - SES (Email)
  - Secrets Manager (Credentials)
  - EventBridge (Scheduling)
  - API Gateway (HTTP API)
  - Cognito (Authentication)
  - CloudWatch (Logging)
- **Libraries**:
  - `python-jobspy` - Job scraping library
  - `boto3` - AWS SDK
  - `requests` - HTTP client
  - `beautifulsoup4` - HTML parsing
  - `pydantic` - Data validation

## Environment Variables

Required for all Lambda functions:
- `JOBS_TABLE` - DynamoDB jobs table
- `USER_STATUS_TABLE` - User application status table
- `USERS_TABLE` - User preferences table
- `GLASSDOOR_CACHE_TABLE` - Ratings cache table
- `SQS_QUEUE_URL` - SQS queue for raw jobs
- `SES_SENDER_EMAIL` - Verified SES sender email
- `SITE_URL` - Site URL for CORS headers

## Database Schema

### scout-jobs
Stores job listings with:
- Hash-based deduplication (PK: `JOB#{hash}`)
- Multi-source support (SK: `SOURCE#{source}#{url_hash}`)
- Glassdoor ratings and extracted benefits
- 60-day TTL for auto-expiration

### scout-user-status
Tracks user application status:
- PK: `USER#{cognito_sub}`
- SK: `JOB#{job_hash}`
- Statuses: NOT_APPLIED, APPLIED, INTERVIEWING, OFFERS

### scout-users
User preferences and settings:
- Email address
- Daily report subscription
- Weekly report subscription

### scout-glassdoor-cache
Caches Glassdoor company ratings:
- 7-day TTL to minimize API calls
- Normalized company name lookup

## API Endpoints

### Jobs
- `GET /jobs` - List jobs with filtering/sorting/pagination
- `GET /jobs/{jobId}` - Get single job details
- `PATCH /jobs/{jobId}/status` - Update application status

### User Settings
- `GET /user/settings` - Get user preferences
- `PUT /user/settings` - Update preferences

## Building and Deploying

### Local Build
```bash
cd backend
./build.sh
```

Generates deployment packages in `build/`:
- `dependencies-layer.zip` - Shared Python dependencies
- `crawlers.zip` - All crawler functions
- `enrichment.zip` - Enrichment processor
- `api.zip` - API handlers
- `reports.zip` - Report generators

### Deploy to AWS
See [DEPLOYMENT.md](./DEPLOYMENT.md) for complete setup instructions including:
- DynamoDB table creation
- SQS queue setup
- Lambda function creation
- API Gateway configuration
- EventBridge scheduling
- SES email verification

## Performance Considerations

- **Crawlers**: 50 jobs per role/location, 24-hour window
- **Enrichment**: Batch processing with 10-message SQS batches
- **API**: Pagination with configurable page sizes (default 20)
- **Reports**: Efficient table scans with filter expressions
- **Caching**: Glassdoor ratings cached for 7 days

## Cost Estimates

Based on typical usage:
- **Crawlers**: ~$0.20/day (5 sources × ~10 runs each)
- **Enrichment**: ~$0.10/day (depends on job volume)
- **API**: ~$0.05/day (low traffic)
- **Reports**: ~$0.10/day (2 emails)
- **DynamoDB**: ~$5-10/month (on-demand pricing)
- **SES**: Minimal (unless high email volume)

**Total estimate**: $200-250/month for single user with moderate activity

## Testing

Each Lambda can be tested locally using:
```python
from lambdas.crawlers.linkedin import handler

event = {}
context = None
result = handler(event, context)
print(result)
```

For testing with LocalStack or local DynamoDB, set environment variables to point to local endpoints.

## Contributing

- Follow PEP 8 style guide
- Add type hints to all functions
- Include docstrings for public functions
- Use logging for debugging
- Handle exceptions gracefully with logging

## License

Part of Scout job aggregation platform.
