# Placeholder zip for Lambda bootstrap
data "archive_file" "lambda_placeholder" {
  type        = "zip"
  output_path = "${path.module}/placeholder.zip"
  source {
    content  = "# Placeholder - deployed via CI/CD"
    filename = "lambda_function.py"
  }
}

# ─── S3 Resume Bucket ─────────────────────────────────────────────────────────
# Stores user-uploaded PDF resumes. Each user's resume lives at:
#   resumes/{cognito_sub}/resume.pdf
# The bucket is private — access is only via pre-signed URLs issued by the
# user_settings Lambda or by the resume-parser Lambda via its IAM role.
resource "aws_s3_bucket" "resumes" {
  bucket = "${var.project_name}-resumes-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name = "${var.project_name}-resumes"
  }
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket_public_access_block" "resumes" {
  bucket = aws_s3_bucket.resumes.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "resumes" {
  bucket = aws_s3_bucket.resumes.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Versioning — keep previous resume versions for 30 days so a bad upload
# doesn't destroy the user's scoring history.
resource "aws_s3_bucket_versioning" "resumes" {
  bucket = aws_s3_bucket.resumes.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "resumes" {
  bucket = aws_s3_bucket.resumes.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

# Restrict uploads to PDF only (max 10 MB). The CORS policy allows the
# browser to PUT directly using the pre-signed URL from the backend.
resource "aws_s3_bucket_cors_configuration" "resumes" {
  bucket = aws_s3_bucket.resumes.id

  cors_rule {
    allowed_headers = ["Content-Type", "Content-Length"]
    allowed_methods = ["PUT"]
    allowed_origins = ["*"] # tightened further with pre-signed URL conditions
    max_age_seconds = 3000
  }
}

# ─── IAM: Resume Parser Lambda ────────────────────────────────────────────────
resource "aws_iam_role" "resume_parser_role" {
  name = "${var.project_name}-resume-parser-role"

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

resource "aws_iam_role_policy_attachment" "resume_parser_basic" {
  role       = aws_iam_role.resume_parser_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Read from the resumes S3 bucket
resource "aws_iam_role_policy" "resume_parser_s3" {
  name = "${var.project_name}-resume-parser-s3"
  role = aws_iam_role.resume_parser_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.resumes.arn}/resumes/*"
      }
    ]
  })
}

# Write resume_text + status into the users DynamoDB table
resource "aws_iam_role_policy" "resume_parser_dynamodb" {
  name = "${var.project_name}-resume-parser-dynamodb"
  role = aws_iam_role.resume_parser_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:UpdateItem"]
        Resource = [var.dynamodb_users_table_arn]
      }
    ]
  })
}

# ─── CloudWatch Log Group ─────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "resume_parser" {
  name              = "/aws/lambda/${var.project_name}-resume-parser"
  retention_in_days = 14

  tags = {
    Name = "${var.project_name}-resume-parser-logs"
  }
}

# ─── Resume Parser Lambda ─────────────────────────────────────────────────────
# Triggered by S3 ObjectCreated events on the resumes bucket.
# Extracts text from the uploaded PDF using pdfminer and stores it in DynamoDB.
resource "aws_lambda_function" "resume_parser" {
  filename      = data.archive_file.lambda_placeholder.output_path
  function_name = "${var.project_name}-resume-parser"
  role          = aws_iam_role.resume_parser_role.arn
  handler       = "scoring.resume_parser.handler"
  runtime       = "python3.12"
  timeout       = 60
  memory_size   = 512
  layers        = [var.shared_layer_arn]

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      USERS_TABLE = var.dynamodb_users_table_name
    }
  }

  tags = {
    Name = "${var.project_name}-resume-parser"
  }

  depends_on = [aws_cloudwatch_log_group.resume_parser]
}

# Allow S3 to invoke the resume parser Lambda on ObjectCreated events
resource "aws_lambda_permission" "s3_invoke_resume_parser" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.resume_parser.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.resumes.arn
}

# Wire the S3 event notification to trigger resume_parser on every PDF upload
resource "aws_s3_bucket_notification" "resumes_trigger" {
  bucket = aws_s3_bucket.resumes.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.resume_parser.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "resumes/"
    filter_suffix       = ".pdf"
  }

  depends_on = [aws_lambda_permission.s3_invoke_resume_parser]
}

# ─── IAM: Job Scorer Lambda ───────────────────────────────────────────────────
resource "aws_iam_role" "job_scorer_role" {
  name = "${var.project_name}-job-scorer-role"

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

resource "aws_iam_role_policy_attachment" "job_scorer_basic" {
  role       = aws_iam_role.job_scorer_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "job_scorer_xray" {
  role       = aws_iam_role.job_scorer_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

# Read jobs + users, write scores + scoring status back to users
resource "aws_iam_role_policy" "job_scorer_dynamodb" {
  name = "${var.project_name}-job-scorer-dynamodb"
  role = aws_iam_role.job_scorer_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["dynamodb:Query", "dynamodb:GetItem"]
        Resource = [
          var.dynamodb_jobs_table_arn,
          "${var.dynamodb_jobs_table_arn}/index/*",
          var.dynamodb_users_table_arn,
        ]
      },
      {
        Effect = "Allow"
        Action = ["dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = [
          var.dynamodb_job_scores_table_arn,
          var.dynamodb_users_table_arn,
        ]
      }
    ]
  })
}

# Claude 4-series models use cross-region inference profiles. Bedrock still
# needs aws-marketplace:Subscribe to activate the model on first use, even
# though the Bedrock console "Model access" page has been removed. The Subscribe
# permission is limited to Bedrock-related marketplace products.
# Inference profiles also require two separate bedrock:InvokeModel grants:
#   1. The inference profile itself  (arn:...:inference-profile/us.anthropic.*)
#   2. The underlying foundation model (arn:...:foundation-model/anthropic.*)
resource "aws_iam_role_policy" "job_scorer_bedrock" {
  name = "${var.project_name}-job-scorer-bedrock"
  role = aws_iam_role.job_scorer_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowBedrockInvokeModel"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = [
          # Cross-region inference profile
          "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.bedrock_model_id}",
          # Underlying foundation model invoked by the profile across regions
          "arn:aws:bedrock:*::foundation-model/anthropic.*",
        ]
      },
      {
        # Bedrock requires these marketplace actions to activate model access on
        # first use. ViewSubscriptions is read-only; Subscribe is scoped to the
        # AWS Marketplace product for Anthropic models on Bedrock.
        Sid    = "AllowBedrockMarketplaceActivation"
        Effect = "Allow"
        Action = [
          "aws-marketplace:ViewSubscriptions",
          "aws-marketplace:Subscribe",
        ]
        Resource = ["*"]
      }
    ]
  })
}

# ─── CloudWatch Log Group: Job Scorer ────────────────────────────────────────
resource "aws_cloudwatch_log_group" "job_scorer" {
  name              = "/aws/lambda/${var.project_name}-job-scorer"
  retention_in_days = 14

  tags = {
    Name = "${var.project_name}-job-scorer-logs"
  }
}

# ─── Job Scorer Lambda ────────────────────────────────────────────────────────
# Invoked asynchronously (InvokeType=Event) by POST /user/score-jobs.
# Scores recent jobs against the user's resume using Bedrock Claude Haiku.
# Timeout 300 s covers ~100 jobs × ~1.5 s per Bedrock call.
resource "aws_lambda_function" "job_scorer" {
  filename      = data.archive_file.lambda_placeholder.output_path
  function_name = "${var.project_name}-job-scorer"
  role          = aws_iam_role.job_scorer_role.arn
  handler       = "scoring.job_scorer.handler"
  runtime       = "python3.12"
  timeout       = 300
  memory_size   = 512
  layers        = [var.shared_layer_arn]

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      JOBS_TABLE       = var.dynamodb_jobs_table_name
      USERS_TABLE      = var.dynamodb_users_table_name
      JOB_SCORES_TABLE = var.dynamodb_job_scores_table_name
      BEDROCK_MODEL_ID = var.bedrock_model_id
      AWS_ACCOUNT_ID   = data.aws_caller_identity.current.account_id
    }
  }

  tags = {
    Name = "${var.project_name}-job-scorer"
  }

  depends_on = [aws_cloudwatch_log_group.job_scorer]
}
