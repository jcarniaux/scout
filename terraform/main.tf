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
  certificate_arn           = aws_acm_certificate.main.arn
  timeouts {
    create = "5m"
  }
  depends_on = [aws_route53_record.acm_validation]
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

  project_name        = var.project_name
  environment         = var.environment
  job_retention_days  = var.job_retention_days
}

# API Gateway Module
module "api" {
  source = "./modules/api"

  project_name              = var.project_name
  environment               = var.environment
  aws_region                = var.aws_region
  cognito_user_pool_arn     = module.auth.cognito_user_pool_arn
  dynamodb_jobs_table_name  = module.data.dynamodb_jobs_table_name
  dynamodb_jobs_table_arn   = module.data.dynamodb_jobs_table_arn
  dynamodb_user_status_table_name = module.data.dynamodb_user_status_table_name
  dynamodb_user_status_table_arn  = module.data.dynamodb_user_status_table_arn
  dynamodb_users_table_name = module.data.dynamodb_users_table_name
  dynamodb_users_table_arn  = module.data.dynamodb_users_table_arn
  domain_name               = var.domain_name
  subdomain                 = var.subdomain

  depends_on = [
    module.auth,
    module.data
  ]
}

# Crawl Module (Step Functions, Lambdas, SQS)
module "crawl" {
  source = "./modules/crawl"

  project_name        = var.project_name
  environment         = var.environment
  aws_region          = var.aws_region
  crawl_schedule      = var.crawl_schedule
  dynamodb_jobs_table_name = module.data.dynamodb_jobs_table_name
  dynamodb_jobs_table_arn  = module.data.dynamodb_jobs_table_arn
  dynamodb_user_status_table_name = module.data.dynamodb_user_status_table_name
  dynamodb_user_status_table_arn  = module.data.dynamodb_user_status_table_arn
  dynamodb_glassdoor_cache_table_name = module.data.dynamodb_glassdoor_cache_table_name
  dynamodb_glassdoor_cache_table_arn  = module.data.dynamodb_glassdoor_cache_table_arn

  depends_on = [module.data]
}

# Email Module (SES, EventBridge, Report Lambdas)
module "email" {
  source = "./modules/email"

  project_name        = var.project_name
  environment         = var.environment
  aws_region          = var.aws_region
  ses_verified_domain = var.ses_verified_domain
  daily_report_schedule  = var.daily_report_schedule
  weekly_report_schedule = var.weekly_report_schedule
  dynamodb_jobs_table_name = module.data.dynamodb_jobs_table_name
  dynamodb_jobs_table_arn  = module.data.dynamodb_jobs_table_arn
  dynamodb_users_table_name       = module.data.dynamodb_users_table_name
  dynamodb_users_table_arn        = module.data.dynamodb_users_table_arn
  dynamodb_user_status_table_name = module.data.dynamodb_user_status_table_name
  dynamodb_user_status_table_arn  = module.data.dynamodb_user_status_table_arn
  domain_name                     = var.domain_name
  subdomain                       = var.subdomain
  route53_zone_id                 = data.aws_route53_zone.root.zone_id

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

  depends_on = [
    module.crawl,
    module.api,
    module.email
  ]
}
