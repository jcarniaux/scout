# Placeholder zip file for Lambda functions
data "archive_file" "lambda_placeholder" {
  type        = "zip"
  output_path = "${path.module}/placeholder.zip"
  source {
    content  = "# Placeholder - deployed via CI/CD"
    filename = "lambda_function.py"
  }
}

# SQS Queue for raw jobs
resource "aws_sqs_queue" "raw_jobs" {
  name                       = "${var.project_name}-raw-jobs"
  visibility_timeout_seconds = 900
  message_retention_seconds  = 86400 # 1 day

  tags = {
    Name = "${var.project_name}-raw-jobs"
  }
}

# SQS Dead Letter Queue
resource "aws_sqs_queue" "raw_jobs_dlq" {
  name = "${var.project_name}-raw-jobs-dlq"

  tags = {
    Name = "${var.project_name}-raw-jobs-dlq"
  }
}

# Configure DLQ for main queue
# aws_sqs_queue_redrive_policy takes a single JSON-encoded redrive_policy string
resource "aws_sqs_queue_redrive_policy" "raw_jobs" {
  queue_url = aws_sqs_queue.raw_jobs.id
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.raw_jobs_dlq.arn
    maxReceiveCount     = 3
  })
}

# Secrets Manager secret for scraping API keys
resource "aws_secretsmanager_secret" "scraper_keys" {
  name                    = "${var.project_name}-scraper-keys"
  recovery_window_in_days = 7

  tags = {
    Name = "${var.project_name}-scraper-keys"
  }
}

# Placeholder secret version
resource "aws_secretsmanager_secret_version" "scraper_keys" {
  secret_id = aws_secretsmanager_secret.scraper_keys.id
  secret_string = jsonencode({
    # Scraping proxy in user:pass@host:port format.
    # Multiple proxies can be comma-separated.
    # All crawlers rotate through these to avoid rate limiting.
    scraping_proxy = "placeholder"
  })

  # Ignore changes so that manual secret updates via CLI/Console
  # are not overwritten on the next terraform apply.
  lifecycle {
    ignore_changes = [secret_string]
  }
}

# IAM role for Step Functions
resource "aws_iam_role" "step_functions_role" {
  name = "${var.project_name}-step-functions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "states.amazonaws.com"
      }
    }]
  })
}

# Policy for Step Functions to invoke Lambda
resource "aws_iam_role_policy" "step_functions_lambda_policy" {
  name = "${var.project_name}-step-functions-lambda-policy"
  role = aws_iam_role.step_functions_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = "lambda:InvokeFunction"
      Resource = [
        "${aws_lambda_function.crawler_linkedin.arn}",
        "${aws_lambda_function.crawler_indeed.arn}",
        "${aws_lambda_function.crawler_glassdoor.arn}",
        "${aws_lambda_function.crawler_ziprecruiter.arn}",
        "${aws_lambda_function.crawler_dice.arn}",
        "${aws_lambda_function.purge_lambda.arn}"
      ]
    }]
  })
}

# IAM role for crawler Lambdas
resource "aws_iam_role" "crawler_role" {
  name = "${var.project_name}-crawler-role"

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
resource "aws_iam_role_policy_attachment" "crawler_basic_execution" {
  role       = aws_iam_role.crawler_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Policy for crawlers to access SQS and Secrets Manager
resource "aws_iam_role_policy" "crawler_policy" {
  name = "${var.project_name}-crawler-policy"
  role = aws_iam_role.crawler_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = aws_sqs_queue.raw_jobs.arn
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = aws_secretsmanager_secret.scraper_keys.arn
      }
    ]
  })
}

# Crawler Lambda functions (5 branches)

resource "aws_lambda_function" "crawler_linkedin" {
  filename      = data.archive_file.lambda_placeholder.output_path
  function_name = "${var.project_name}-crawler-linkedin"
  role          = aws_iam_role.crawler_role.arn
  handler       = "crawlers.linkedin.handler"
  runtime       = "python3.12"
  timeout       = 900
  memory_size   = 512

  environment {
    variables = {
      SQS_QUEUE_URL = aws_sqs_queue.raw_jobs.url
      SECRETS_ARN   = aws_secretsmanager_secret.scraper_keys.arn
    }
  }

  tags = {
    Name = "${var.project_name}-crawler-linkedin"
  }
}

resource "aws_lambda_function" "crawler_indeed" {
  filename      = data.archive_file.lambda_placeholder.output_path
  function_name = "${var.project_name}-crawler-indeed"
  role          = aws_iam_role.crawler_role.arn
  handler       = "crawlers.indeed.handler"
  runtime       = "python3.12"
  timeout       = 900
  memory_size   = 512

  environment {
    variables = {
      SQS_QUEUE_URL = aws_sqs_queue.raw_jobs.url
      SECRETS_ARN   = aws_secretsmanager_secret.scraper_keys.arn
    }
  }

  tags = {
    Name = "${var.project_name}-crawler-indeed"
  }
}

resource "aws_lambda_function" "crawler_glassdoor" {
  filename      = data.archive_file.lambda_placeholder.output_path
  function_name = "${var.project_name}-crawler-glassdoor"
  role          = aws_iam_role.crawler_role.arn
  handler       = "crawlers.glassdoor.handler"
  runtime       = "python3.12"
  timeout       = 900
  memory_size   = 512

  environment {
    variables = {
      SQS_QUEUE_URL = aws_sqs_queue.raw_jobs.url
      SECRETS_ARN   = aws_secretsmanager_secret.scraper_keys.arn
    }
  }

  tags = {
    Name = "${var.project_name}-crawler-glassdoor"
  }
}

resource "aws_lambda_function" "crawler_ziprecruiter" {
  filename      = data.archive_file.lambda_placeholder.output_path
  function_name = "${var.project_name}-crawler-ziprecruiter"
  role          = aws_iam_role.crawler_role.arn
  handler       = "crawlers.ziprecruiter.handler"
  runtime       = "python3.12"
  timeout       = 900
  memory_size   = 512

  environment {
    variables = {
      SQS_QUEUE_URL = aws_sqs_queue.raw_jobs.url
      SECRETS_ARN   = aws_secretsmanager_secret.scraper_keys.arn
    }
  }

  tags = {
    Name = "${var.project_name}-crawler-ziprecruiter"
  }
}

resource "aws_lambda_function" "crawler_dice" {
  filename      = data.archive_file.lambda_placeholder.output_path
  function_name = "${var.project_name}-crawler-dice"
  role          = aws_iam_role.crawler_role.arn
  handler       = "crawlers.dice.handler"
  runtime       = "python3.12"
  timeout       = 900
  memory_size   = 512

  environment {
    variables = {
      SQS_QUEUE_URL = aws_sqs_queue.raw_jobs.url
      SECRETS_ARN   = aws_secretsmanager_secret.scraper_keys.arn
    }
  }

  tags = {
    Name = "${var.project_name}-crawler-dice"
  }
}

# Diagnostic Lambda — read-only crawler pipeline tester
# Invoke manually: aws lambda invoke --function-name scout-crawl-diagnose out.json
resource "aws_lambda_function" "crawl_diagnose" {
  filename      = data.archive_file.lambda_placeholder.output_path
  function_name = "${var.project_name}-crawl-diagnose"
  role          = aws_iam_role.crawler_role.arn
  handler       = "crawlers.diagnose.handler"
  runtime       = "python3.12"
  timeout       = 900
  memory_size   = 512

  environment {
    variables = {
      SQS_QUEUE_URL = aws_sqs_queue.raw_jobs.url
      SECRETS_ARN   = aws_secretsmanager_secret.scraper_keys.arn
    }
  }

  tags = {
    Name = "${var.project_name}-crawl-diagnose"
  }
}

# IAM role for enrichment Lambda
resource "aws_iam_role" "enrichment_role" {
  name = "${var.project_name}-enrichment-role"

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
resource "aws_iam_role_policy_attachment" "enrichment_basic_execution" {
  role       = aws_iam_role.enrichment_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Policy for enrichment Lambda
resource "aws_iam_role_policy" "enrichment_policy" {
  name = "${var.project_name}-enrichment-policy"
  role = aws_iam_role.enrichment_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.raw_jobs.arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:GetItem"
        ]
        Resource = [
          var.dynamodb_jobs_table_arn,
          var.dynamodb_glassdoor_cache_table_arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = aws_secretsmanager_secret.scraper_keys.arn
      }
    ]
  })
}

# Enrichment Lambda (triggered by SQS)
resource "aws_lambda_function" "enrichment_lambda" {
  filename      = data.archive_file.lambda_placeholder.output_path
  function_name = "${var.project_name}-enrichment"
  role          = aws_iam_role.enrichment_role.arn
  handler       = "enrichment.handler.handler"
  runtime       = "python3.12"
  timeout       = 300
  memory_size   = 512

  environment {
    variables = {
      JOBS_TABLE            = var.dynamodb_jobs_table_name
      GLASSDOOR_CACHE_TABLE = var.dynamodb_glassdoor_cache_table_name
      SECRETS_ARN           = aws_secretsmanager_secret.scraper_keys.arn
    }
  }

  tags = {
    Name = "${var.project_name}-enrichment"
  }
}

# SQS event source mapping for enrichment Lambda
resource "aws_lambda_event_source_mapping" "enrichment_sqs" {
  event_source_arn                   = aws_sqs_queue.raw_jobs.arn
  function_name                      = aws_lambda_function.enrichment_lambda.function_name
  enabled                            = true
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}

# IAM role for purge Lambda
resource "aws_iam_role" "purge_role" {
  name = "${var.project_name}-purge-role"

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
resource "aws_iam_role_policy_attachment" "purge_basic_execution" {
  role       = aws_iam_role.purge_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Policy for purge Lambda
resource "aws_iam_role_policy" "purge_policy" {
  name = "${var.project_name}-purge-policy"
  role = aws_iam_role.purge_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Scan",
          "dynamodb:DeleteItem"
        ]
        Resource = var.dynamodb_user_status_table_arn
      }
    ]
  })
}

# Purge Lambda
resource "aws_lambda_function" "purge_lambda" {
  filename      = data.archive_file.lambda_placeholder.output_path
  function_name = "${var.project_name}-purge"
  role          = aws_iam_role.purge_role.arn
  handler       = "crawlers.purge.handler"
  runtime       = "python3.12"
  timeout       = 60
  memory_size   = 256

  environment {
    variables = {
      JOBS_TABLE        = var.dynamodb_jobs_table_name
      USER_STATUS_TABLE = var.dynamodb_user_status_table_name
    }
  }

  tags = {
    Name = "${var.project_name}-purge"
  }
}

# Step Functions State Machine Definition (JSON)
resource "aws_sfn_state_machine" "crawl" {
  name     = "${var.project_name}-crawl-state-machine"
  role_arn = aws_iam_role.step_functions_role.arn
  definition = templatefile("${path.module}/state_machine.json", {
    linkedin_lambda_arn     = aws_lambda_function.crawler_linkedin.arn
    indeed_lambda_arn       = aws_lambda_function.crawler_indeed.arn
    glassdoor_lambda_arn    = aws_lambda_function.crawler_glassdoor.arn
    ziprecruiter_lambda_arn = aws_lambda_function.crawler_ziprecruiter.arn
    dice_lambda_arn         = aws_lambda_function.crawler_dice.arn
    purge_lambda_arn        = aws_lambda_function.purge_lambda.arn
  })

  tags = {
    Name = "${var.project_name}-crawl-state-machine"
  }
}

# EventBridge rule for crawl schedule
resource "aws_cloudwatch_event_rule" "crawl_schedule" {
  name                = "${var.project_name}-crawl-schedule"
  description         = "Trigger crawl at scheduled time"
  schedule_expression = var.crawl_schedule

  tags = {
    Name = "${var.project_name}-crawl-schedule"
  }
}

# EventBridge target
resource "aws_cloudwatch_event_target" "crawl_state_machine" {
  rule      = aws_cloudwatch_event_rule.crawl_schedule.name
  arn       = aws_sfn_state_machine.crawl.arn
  role_arn  = aws_iam_role.eventbridge_role.arn
  target_id = "CrawlStateMachine"
}

# IAM role for EventBridge
resource "aws_iam_role" "eventbridge_role" {
  name = "${var.project_name}-eventbridge-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "events.amazonaws.com"
      }
    }]
  })
}

# Policy for EventBridge to invoke Step Functions
resource "aws_iam_role_policy" "eventbridge_policy" {
  name = "${var.project_name}-eventbridge-policy"
  role = aws_iam_role.eventbridge_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "states:StartExecution"
      ]
      Resource = aws_sfn_state_machine.crawl.arn
    }]
  })
}
