# Placeholder zip file for Lambda functions
data "archive_file" "lambda_placeholder" {
  type        = "zip"
  output_path = "${path.module}/placeholder.zip"
  source {
    content  = "# Placeholder - deployed via CI/CD"
    filename = "lambda_function.py"
  }
}

# SES Domain Identity — managed by Terraform.
# Note: aws_ses_domain_identity does not support tags.
resource "aws_ses_domain_identity" "main" {
  domain = var.ses_verified_domain
}

# SES domain verification TXT record
resource "aws_route53_record" "ses_verification" {
  zone_id = var.route53_zone_id
  name    = "_amazonses.${var.ses_verified_domain}"
  type    = "TXT"
  ttl     = 1800
  records = [aws_ses_domain_identity.main.verification_token]

  allow_overwrite = true
}

# Wait for SES to confirm the domain is verified
resource "aws_ses_domain_identity_verification" "main" {
  domain = aws_ses_domain_identity.main.id

  depends_on = [aws_route53_record.ses_verification]
}

# Generate DKIM tokens
resource "aws_ses_domain_dkim" "main" {
  domain = aws_ses_domain_identity.main.domain
}

# DKIM CNAME records — allow_overwrite handles any pre-existing records
# (e.g. from a prior verification in another region or account)
resource "aws_route53_record" "ses_dkim" {
  count   = 3
  zone_id = var.route53_zone_id
  name    = "${aws_ses_domain_dkim.main.dkim_tokens[count.index]}._domainkey.${var.ses_verified_domain}"
  type    = "CNAME"
  ttl     = 1800
  records = ["${aws_ses_domain_dkim.main.dkim_tokens[count.index]}.dkim.amazonses.com"]

  allow_overwrite = true
}

# IAM role for report Lambdas
resource "aws_iam_role" "report_role" {
  name = "${var.project_name}-report-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# Basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "report_basic_execution" {
  role       = aws_iam_role.report_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Policy for report Lambdas
resource "aws_iam_role_policy" "report_policy" {
  name = "${var.project_name}-report-policy"
  role = aws_iam_role.report_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:GetItem"
        ]
        Resource = [
          var.dynamodb_jobs_table_arn,
          "${var.dynamodb_jobs_table_arn}/index/*",
          var.dynamodb_users_table_arn,
          var.dynamodb_user_status_table_arn,
          "${var.dynamodb_user_status_table_arn}/index/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail"
        ]
        Resource = aws_ses_domain_identity.main.arn
      }
    ]
  })
}

# Daily report Lambda
resource "aws_lambda_function" "daily_report" {
  filename      = data.archive_file.lambda_placeholder.output_path
  function_name = "${var.project_name}-daily-report"
  role          = aws_iam_role.report_role.arn
  handler       = "reports.daily_report.handler"
  runtime       = "python3.12"
  timeout       = 60
  memory_size   = 256

  environment {
    variables = {
      JOBS_TABLE       = var.dynamodb_jobs_table_name
      USERS_TABLE      = var.dynamodb_users_table_name
      SES_SENDER_EMAIL = "scout@${var.ses_verified_domain}"
      SITE_URL         = "https://${var.subdomain}.${var.domain_name}"
    }
  }

  tags = {
    Name = "${var.project_name}-daily-report"
  }
}

# Weekly report Lambda
resource "aws_lambda_function" "weekly_report" {
  filename      = data.archive_file.lambda_placeholder.output_path
  function_name = "${var.project_name}-weekly-report"
  role          = aws_iam_role.report_role.arn
  handler       = "reports.weekly_report.handler"
  runtime       = "python3.12"
  timeout       = 60
  memory_size   = 256

  environment {
    variables = {
      JOBS_TABLE        = var.dynamodb_jobs_table_name
      USERS_TABLE       = var.dynamodb_users_table_name
      USER_STATUS_TABLE = var.dynamodb_user_status_table_name
      SES_SENDER_EMAIL  = "scout@${var.ses_verified_domain}"
      SITE_URL          = "https://${var.subdomain}.${var.domain_name}"
    }
  }

  tags = {
    Name = "${var.project_name}-weekly-report"
  }
}

# Lambda permissions for EventBridge
resource "aws_lambda_permission" "daily_report_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.daily_report.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_report_schedule.arn
}

resource "aws_lambda_permission" "weekly_report_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.weekly_report.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.weekly_report_schedule.arn
}

# EventBridge rules

# Daily report schedule
resource "aws_cloudwatch_event_rule" "daily_report_schedule" {
  name                = "${var.project_name}-daily-report-schedule"
  description         = "Trigger daily report at scheduled time"
  schedule_expression = var.daily_report_schedule

  tags = {
    Name = "${var.project_name}-daily-report-schedule"
  }
}

resource "aws_cloudwatch_event_target" "daily_report" {
  rule      = aws_cloudwatch_event_rule.daily_report_schedule.name
  target_id = "DailyReportLambda"
  arn       = aws_lambda_function.daily_report.arn
}

# Weekly report schedule
resource "aws_cloudwatch_event_rule" "weekly_report_schedule" {
  name                = "${var.project_name}-weekly-report-schedule"
  description         = "Trigger weekly report at scheduled time"
  schedule_expression = var.weekly_report_schedule

  tags = {
    Name = "${var.project_name}-weekly-report-schedule"
  }
}

resource "aws_cloudwatch_event_target" "weekly_report" {
  rule      = aws_cloudwatch_event_rule.weekly_report_schedule.name
  target_id = "WeeklyReportLambda"
  arn       = aws_lambda_function.weekly_report.arn
}
