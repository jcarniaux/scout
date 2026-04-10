# SNS Topic for alerts
resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts"

  tags = {
    Name = "${var.project_name}-alerts"
  }
}

# SNS Email subscription — only created when alert_email is provided.
# Without this guard, Terraform passes an empty string to SNS and fails
# with "InvalidParameter: Invalid parameter: Endpoint".
resource "aws_sns_topic_subscription" "alerts_email" {
  count = var.alert_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# CloudWatch Alarm: Crawler Lambda errors
resource "aws_cloudwatch_metric_alarm" "crawler_errors" {
  for_each = toset(var.crawler_lambda_names)

  alarm_name          = "${each.value}-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "3600"
  statistic           = "Sum"
  threshold           = "3"
  alarm_description   = "Alert when ${each.value} has 3+ errors in 1 hour"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = each.value
  }

  tags = {
    Name = "${each.value}-errors"
  }
}

# CloudWatch Alarm: API Gateway 5xx errors
resource "aws_cloudwatch_metric_alarm" "api_5xx_errors" {
  alarm_name          = "${var.project_name}-api-5xx-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "5XXError"
  namespace           = "AWS/ApiGateway"
  period              = "300"
  statistic           = "Sum"
  threshold           = "5"
  alarm_description   = "Alert when API Gateway has 5+ 5xx errors in 5 minutes"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    ApiName = var.api_gateway_id
    Stage   = var.api_stage_name
  }

  tags = {
    Name = "${var.project_name}-api-5xx-errors"
  }
}

# CloudWatch Alarm: DLQ messages
resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  alarm_name          = "${var.project_name}-dlq-messages"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Average"
  threshold           = "1"
  alarm_description   = "Alert when DLQ has messages"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    QueueName = split("/", var.dlq_url)[4]
  }

  tags = {
    Name = "${var.project_name}-dlq-messages"
  }
}

# CloudWatch Alarm: SES bounce rate
resource "aws_cloudwatch_metric_alarm" "ses_bounce_rate" {
  alarm_name          = "${var.project_name}-ses-bounce-rate"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "Bounce"
  namespace           = "AWS/SES"
  period              = "3600"
  statistic           = "Sum"
  threshold           = "5"
  alarm_description   = "Alert when SES bounce rate exceeds threshold"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    Domain = var.ses_verified_domain
  }

  tags = {
    Name = "${var.project_name}-ses-bounce-rate"
  }
}

# CloudWatch Dashboard
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project_name}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      # Widget 1 — Lambda + API Gateway overview
      # Each entry is [namespace, metric_name] only; widget-level stat applies.
      # Dot shorthand ("." = repeat previous namespace) is NOT supported without
      # explicit dimensions, so every row uses the full namespace.
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Lambda & API Gateway"
          region = var.aws_region
          period = 300
          stat   = "Sum"
          metrics = [
            ["AWS/Lambda", "Invocations"],
            ["AWS/Lambda", "Errors"],
            ["AWS/ApiGateway", "Count"],
            ["AWS/ApiGateway", "4XXError"],
            ["AWS/ApiGateway", "5XXError"]
          ]
        }
      },
      # Widget 2 — Per-crawler error counts using proper dimension tuples
      # Format: [namespace, metric_name, dim_key, dim_value]
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Crawler Errors"
          region = var.aws_region
          period = 300
          stat   = "Sum"
          metrics = [
            for name in var.crawler_lambda_names :
            ["AWS/Lambda", "Errors", "FunctionName", name]
          ]
        }
      },
      # Widget 3 — SQS queue depth
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Queue Metrics"
          region = var.aws_region
          period = 300
          stat   = "Average"
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible"],
            ["AWS/SQS", "NumberOfMessagesSent"],
            ["AWS/SQS", "NumberOfMessagesReceived"]
          ]
        }
      },
      # Widget 4 — SES send/delivery/bounce/complaint
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Email Metrics"
          region = var.aws_region
          period = 3600
          stat   = "Sum"
          metrics = [
            ["AWS/SES", "Send"],
            ["AWS/SES", "Delivery"],
            ["AWS/SES", "Bounce"],
            ["AWS/SES", "Complaint"]
          ]
        }
      }
    ]
  })
}
