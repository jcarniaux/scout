# Scout — Job Aggregation & Application Tracker

**Live URL:** https://scout.carniaux.io

Scout crawls LinkedIn, Indeed, Glassdoor, ZipRecruiter, and Dice daily for senior security and cloud architecture roles (≥ $180k, Atlanta GA or US Remote), deduplicates results, enriches them with Glassdoor ratings, and presents everything in a secure web dashboard with per-user application tracking and automated email reports.

---

## Repository Layout

```
scout/
├── terraform/              # All infrastructure (Terraform 1.7+, AWS us-east-1)
│   ├── main.tf             # Root module — wires all child modules together
│   ├── variables.tf
│   ├── outputs.tf
│   ├── providers.tf        # AWS provider + optional S3 backend (see Step 2)
│   └── modules/
│       ├── auth/           # Cognito User Pool, MFA (TOTP), app client
│       ├── data/           # DynamoDB tables (jobs, user-status, users, glassdoor-cache)
│       ├── api/            # API Gateway (REST) + Lambda handlers
│       ├── crawl/          # Step Functions, SQS, crawler Lambdas, EventBridge
│       ├── email/          # SES, report Lambdas, EventBridge schedules
│       ├── frontend/       # S3, CloudFront, WAF, Route53 record
│       └── monitoring/     # SNS, CloudWatch alarms, dashboard
│
├── backend/
│   ├── lambdas/
│   │   ├── crawlers/       # linkedin, indeed, glassdoor, ziprecruiter, dice, purge
│   │   ├── enrichment/     # SQS-triggered dedup + Glassdoor rating cache
│   │   ├── api/            # get_jobs, update_status, user_settings
│   │   ├── reports/        # daily_report, weekly_report
│   │   └── shared/         # db, response, models, crawler_utils, email_templates
│   ├── requirements.txt
│   └── build.sh            # Produces build/*.zip + build/dependencies-layer.zip
│
├── frontend/               # React 18 + TypeScript + Tailwind + AWS Amplify
│   ├── src/
│   │   ├── components/     # Navbar, FilterBar, JobCard, JobList, StatusSelect …
│   │   ├── hooks/          # useJobs, useUpdateStatus, useSettings …
│   │   ├── pages/          # Dashboard, Settings
│   │   ├── services/       # api.ts — authenticated fetch wrapper
│   │   └── types/          # index.ts — Job, ApplicationStatus, JobFilters …
│   ├── .env.example
│   └── package.json
│
├── .github/workflows/
│   ├── deploy-infra.yml    # Terraform plan / apply on push to main
│   ├── deploy-backend.yml  # Build + deploy Lambdas on push to main
│   └── deploy-frontend.yml # Build React + sync to S3 + CloudFront invalidation
│
└── scripts/
    └── bootstrap.sh        # One-time account setup (state bucket, OIDC role)
```

---

## First-time deployment (step by step)

### Prerequisites

| Tool | Min version |
|------|------------|
| AWS CLI | 2.x, configured with admin creds |
| Terraform | 1.7+ |
| Node.js | 20 LTS |
| Python | 3.12 |
| Git | any |

Your AWS account must already have the **carniaux.io** hosted zone in Route 53. Terraform looks it up by name — it doesn't create it.

---

### Step 1 — Bootstrap the AWS account (run once)

```bash
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh
```

This creates:
- S3 bucket for Terraform remote state (`scout-tfstate-<account-id>`)
- DynamoDB table for state locking (`scout-tflock`)
- GitHub OIDC provider in IAM
- IAM role `scout-github-actions` with least-privilege policies

The script prints the exact values you'll need in the next steps.

---

### Step 2 — Enable remote Terraform state

Edit `terraform/providers.tf` and uncomment the `backend "s3"` block, filling in the bucket name printed by bootstrap.sh:

```hcl
backend "s3" {
  bucket         = "scout-tfstate-<your-account-id>"
  key            = "prod/terraform.tfstate"
  region         = "us-east-1"
  encrypt        = true
  dynamodb_table = "scout-tflock"
}
```

Then initialise:

```bash
cd terraform
terraform init
```

---

### Step 3 — First Terraform apply

```bash
terraform plan -var="alert_email=your@email.com"
terraform apply -var="alert_email=your@email.com"
```

This takes about 10–15 minutes (ACM certificate validation is the slow part). When it finishes, note these outputs — you'll need them for secrets:

```bash
terraform output cognito_user_pool_id
terraform output cognito_user_pool_client_id
terraform output api_gateway_url
terraform output frontend_bucket_name
terraform output cloudfront_distribution_id
```

---

### Step 4 — Add GitHub repository secrets

Go to your repo → **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|--------|-------|
| `AWS_DEPLOY_ROLE_ARN` | From bootstrap.sh output |
| `ALERT_EMAIL` | Your email for CloudWatch alarms |
| `COGNITO_USER_POOL_ID` | From `terraform output` |
| `COGNITO_USER_POOL_CLIENT_ID` | From `terraform output` |
| `API_GATEWAY_URL` | From `terraform output` (full URL incl. `/v1`) |
| `FRONTEND_BUCKET` | From `terraform output` |
| `CLOUDFRONT_DISTRIBUTION_ID` | From `terraform output` |

---

### Step 5 — Push to trigger CI/CD

```bash
git add .
git commit -m "feat: initial Scout deployment"
git push origin main
```

Three GitHub Actions workflows run in sequence (infra → backend → frontend). Watch them under the **Actions** tab. On a clean push to `main` with no infra changes, only the backend and frontend workflows run.

---

### Step 6 — Verify SES sending domain

SES DNS records are created automatically by Terraform but the domain identity still needs to be verified in the AWS console:

1. AWS Console → **SES → Verified identities** → `carniaux.io`
2. If status is "Pending", wait up to 72 hours for DNS propagation
3. Once verified, SES exits sandbox mode for this domain (you may also need to request production access if your account is new)

---

### Step 7 — Create your first user

Open https://scout.carniaux.io and click **Create account**. Cognito will:
1. Verify your email
2. Prompt you to set up TOTP MFA with your authenticator app (Google Authenticator, Authy, 1Password, etc.)

After login, go to **Settings** to configure your email notification preferences.

---

## Day-to-day operations

### Trigger a manual crawl

```bash
aws stepfunctions start-execution \
  --state-machine-arn $(cd terraform && terraform output -raw step_functions_state_machine_arn) \
  --name "manual-$(date +%s)"
```

### Check Lambda logs

```bash
# Crawler logs (e.g. LinkedIn)
aws logs tail /aws/lambda/scout-crawler-linkedin --follow

# Enrichment
aws logs tail /aws/lambda/scout-enrichment --follow

# API
aws logs tail /aws/lambda/scout-api-get-jobs --follow
```

### Check DynamoDB job count

```bash
aws dynamodb scan \
  --table-name scout-jobs \
  --select COUNT \
  --query 'Count'
```

### Force a CloudFront cache purge

```bash
aws cloudfront create-invalidation \
  --distribution-id $(cd terraform && terraform output -raw cloudfront_distribution_id) \
  --paths "/*"
```

---

## Upgrading the scraping backend

The crawlers currently use [JobSpy](https://github.com/speedyapply/JobSpy) — a free, open-source Python library (no API key required). It works well for low-volume personal use. If you hit rate limits or anti-bot blocks, upgrade to a paid proxy:

1. Add your API key to AWS Secrets Manager:
   ```bash
   aws secretsmanager put-secret-value \
     --secret-id scout-scraper-keys \
     --secret-string '{"SCRAPINGBEE_API_KEY":"your-key"}'
   ```
2. Update `backend/lambdas/crawlers/` to read the key and pass it to the scraping client
3. Push to deploy

No Terraform changes needed — the `scout-scraper-keys` secret already exists.

---

## Architecture summary

```
 INTERNET
    │
 CloudFront + WAF (rate-limit, OWASP rules)
    ├── S3  →  React SPA (scout.carniaux.io)
    └── API Gateway (REST, Cognito authorizer)
         ├── GET  /jobs               Lambda: api-get-jobs
         ├── GET  /jobs/{id}          Lambda: api-get-jobs
         ├── PATCH /jobs/{id}/status  Lambda: api-update-status
         └── GET|PUT /user/settings   Lambda: api-user-settings
                  │
              DynamoDB
              ├── scout-jobs           (TTL 60d, DateIndex GSI, RatingIndex GSI)
              ├── scout-user-status    (StatusIndex GSI)
              ├── scout-users
              └── scout-glassdoor-cache (TTL 7d)

 EventBridge cron 02:00 EST
    └── Step Functions
         ├── [parallel] crawler-linkedin
         ├── [parallel] crawler-indeed
         ├── [parallel] crawler-glassdoor
         ├── [parallel] crawler-ziprecruiter
         ├── [parallel] crawler-dice
         │        └── SQS raw-jobs → Lambda enrichment (dedup + Glassdoor cache)
         └── Lambda purge

 EventBridge cron 07:00 EST daily  → Lambda daily-report  → SES
 EventBridge cron 08:00 EST Sat    → Lambda weekly-report → SES
```

**Cost: ~$40–45/month** (dominated by the optional scraping proxy; JobSpy itself is free)

---

## Environment variables reference

### All crawler Lambdas
| Variable | Description |
|----------|-------------|
| `SQS_QUEUE_URL` | Raw jobs SQS queue URL |
| `SECRETS_ARN` | Secrets Manager ARN for scraping keys |

### Enrichment Lambda
| Variable | Description |
|----------|-------------|
| `JOBS_TABLE` | DynamoDB jobs table name |
| `GLASSDOOR_CACHE_TABLE` | DynamoDB Glassdoor cache table name |
| `SECRETS_ARN` | Secrets Manager ARN |

### API Lambdas
| Variable | Description |
|----------|-------------|
| `JOBS_TABLE` | DynamoDB jobs table name |
| `USER_STATUS_TABLE` | DynamoDB user-status table name |
| `USERS_TABLE` | DynamoDB users table name |
| `SITE_URL` | https://scout.carniaux.io |

### Report Lambdas
| Variable | Description |
|----------|-------------|
| `JOBS_TABLE` | DynamoDB jobs table name |
| `USERS_TABLE` | DynamoDB users table name |
| `USER_STATUS_TABLE` | DynamoDB user-status table name (weekly only) |
| `SES_SENDER_EMAIL` | scout@carniaux.io |
| `SITE_URL` | https://scout.carniaux.io |

---

## Security posture

- MFA required for all users (TOTP — no SMS)
- CloudFront-only access to S3 (OAC, no public bucket)
- WAF: AWS Managed Rules + rate limiting (300 req/5 min/IP)
- All Lambda roles follow least-privilege IAM
- Secrets in AWS Secrets Manager (not env vars)
- DynamoDB encrypted at rest, point-in-time recovery enabled
- SES domain verified with DKIM + SPF + DMARC
- All traffic TLS 1.2+ (TLSv1.2_2021 policy on CloudFront)
- GitHub Actions uses OIDC (no long-lived AWS keys stored as secrets)
