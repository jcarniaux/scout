data "aws_route53_zone" "root" {
  name = var.domain_name
}

# Create ACM certificate for scout.carniaux.io with DNS validation
resource "aws_acm_certificate" "main" {
  domain_name       = "${var.subdomain}.${var.domain_name}"
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "${var.project_name}-cert"
  }
}

# Create Route53 records for ACM DNS validation
resource "aws_route53_record" "acm_validation" {
  for_each = {
    for dvo in aws_acm_certificate.main.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.root.zone_id
}

# Wait for ACM certificate validation
resource "aws_acm_certificate_validation" "main" {
  certificate_arn = aws_acm_certificate.main.arn
  timeouts {
    create = "5m"
  }
  depends_on = [aws_route53_record.acm_validation]
}

# ─── Shared Lambda Layer ─────────────────────────────────────────────────────
# Contains backend/lambdas/shared/ (db, models, response, crawler_utils, etc.)
# so every Lambda gets the same version of common code without duplicating it
# inside each deployment package.  CI/CD publishes the real layer; Terraform
# uses a placeholder to bootstrap the resource.
data "archive_file" "shared_layer_placeholder" {
  type        = "zip"
  output_path = "${path.module}/shared_layer_placeholder.zip"
  source {
    content  = "# Placeholder - deployed via CI/CD"
    filename = "python/shared/__init__.py"
  }
}

resource "aws_lambda_layer_version" "shared" {
  layer_name          = "${var.project_name}-shared"
  filename            = data.archive_file.shared_layer_placeholder.output_path
  compatible_runtimes = ["python3.12"]
  description         = "Shared utilities: db, models, response, crawler_utils, oxylabs_client"

  lifecycle {
    # CI/CD publishes new versions; Terraform should not revert to placeholder.
    ignore_changes = [filename, source_code_hash]
  }
}

# Cognito Auth Module
module "auth" {
  source = "./modules/auth"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region
}

# Data Module (DynamoDB)
module "data" {
  source = "./modules/data"

  project_name       = var.project_name
  environment        = var.environment
  job_retention_days = var.job_retention_days
}

# Scoring Module (S3 resumes bucket + resume-parser Lambda)
module "scoring" {
  source = "./modules/scoring"

  project_name              = var.project_name
  environment               = var.environment
  aws_region                = var.aws_region
  dynamodb_users_table_name = module.data.dynamodb_users_table_name
  dynamodb_users_table_arn  = module.data.dynamodb_users_table_arn
  shared_layer_arn          = aws_lambda_layer_version.shared.arn

  depends_on = [module.data]
}

# API Gateway Module
module "api" {
  source = "./modules/api"

  project_name                    = var.project_name
  environment                     = var.environment
  aws_region                      = var.aws_region
  cognito_user_pool_arn           = module.auth.cognito_user_pool_arn
  dynamodb_jobs_table_name        = module.data.dynamodb_jobs_table_name
  dynamodb_jobs_table_arn         = module.data.dynamodb_jobs_table_arn
  dynamodb_user_status_table_name = module.data.dynamodb_user_status_table_name
  dynamodb_user_status_table_arn  = module.data.dynamodb_user_status_table_arn
  dynamodb_users_table_name       = module.data.dynamodb_users_table_name
  dynamodb_users_table_arn        = module.data.dynamodb_users_table_arn
  dynamodb_job_scores_table_name  = module.data.dynamodb_job_scores_table_name
  dynamodb_job_scores_table_arn   = module.data.dynamodb_job_scores_table_arn
  resumes_bucket_name             = module.scoring.resumes_bucket_name
  resumes_bucket_arn              = module.scoring.resumes_bucket_arn
  domain_name                     = var.domain_name
  subdomain                       = var.subdomain
  shared_layer_arn                = aws_lambda_layer_version.shared.arn

  depends_on = [
    module.auth,
    module.data,
    module.scoring,
  ]
}

# Crawl Module (Step Functions, Lambdas, SQS)
module "crawl" {
  source = "./modules/crawl"

  project_name                        = var.project_name
  environment                         = var.environment
  aws_region                          = var.aws_region
  crawl_schedule                      = var.crawl_schedule
  dynamodb_jobs_table_name            = module.data.dynamodb_jobs_table_name
  dynamodb_jobs_table_arn             = module.data.dynamodb_jobs_table_arn
  dynamodb_user_status_table_name     = module.data.dynamodb_user_status_table_name
  dynamodb_user_status_table_arn      = module.data.dynamodb_user_status_table_arn
  dynamodb_glassdoor_cache_table_name = module.data.dynamodb_glassdoor_cache_table_name
  dynamodb_glassdoor_cache_table_arn  = module.data.dynamodb_glassdoor_cache_table_arn
  dynamodb_users_table_name           = module.data.dynamodb_users_table_name
  dynamodb_users_table_arn            = module.data.dynamodb_users_table_arn
  dynamodb_job_scores_table_name      = module.data.dynamodb_job_scores_table_name
  dynamodb_job_scores_table_arn       = module.data.dynamodb_job_scores_table_arn
  shared_layer_arn                    = aws_lambda_layer_version.shared.arn

  depends_on = [module.data]
}

# Email Module (SES, EventBridge, Report Lambdas)
module "email" {
  source = "./modules/email"

  project_name                    = var.project_name
  environment                     = var.environment
  aws_region                      = var.aws_region
  ses_verified_domain             = var.ses_verified_domain
  daily_report_schedule           = var.daily_report_schedule
  weekly_report_schedule          = var.weekly_report_schedule
  dynamodb_jobs_table_name        = module.data.dynamodb_jobs_table_name
  dynamodb_jobs_table_arn         = module.data.dynamodb_jobs_table_arn
  dynamodb_users_table_name       = module.data.dynamodb_users_table_name
  dynamodb_users_table_arn        = module.data.dynamodb_users_table_arn
  dynamodb_user_status_table_name = module.data.dynamodb_user_status_table_name
  dynamodb_user_status_table_arn  = module.data.dynamodb_user_status_table_arn
  domain_name                     = var.domain_name
  subdomain                       = var.subdomain
  route53_zone_id                 = data.aws_route53_zone.root.zone_id
  shared_layer_arn                = aws_lambda_layer_version.shared.arn

  depends_on = [module.data]
}

# Frontend Module (S3, CloudFront, WAF)
module "frontend" {
  source = "./modules/frontend"

  project_name        = var.project_name
  environment         = var.environment
  aws_region          = var.aws_region
  domain_name         = var.domain_name
  subdomain           = var.subdomain
  acm_certificate_arn = aws_acm_certificate_validation.main.certificate_arn
  route53_zone_id     = data.aws_route53_zone.root.zone_id

  depends_on = [aws_acm_certificate_validation.main]
}

# Monitoring Module (SNS, CloudWatch Alarms, Dashboard)
module "monitoring" {
  source = "./modules/monitoring"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region
  alert_email  = var.alert_email

  # Crawler Lambda function names for monitoring
  crawler_lambda_names = module.crawl.crawler_lambda_names

  # API Gateway metrics
  api_gateway_id = module.api.api_gateway_id
  api_stage_name = module.api.api_stage_name

  # DLQ for monitoring
  dlq_url = module.crawl.dlq_url

  # SES domain for bounce rate monitoring
  ses_verified_domain = var.ses_verified_domain

  # Implicit dependencies on module.api and module.email are expressed through
  # the input variable values above (api_gateway_id, api_stage_name, etc.).
  # A broad depends_on = [module.api] would create a destroy-phase cycle when
  # aws_api_gateway_deployment uses create_before_destroy, because Terraform
  # can't resolve the ordering of the deposed deployment destruction while
  # monitoring is also being updated.
  depends_on = [module.crawl]
}
