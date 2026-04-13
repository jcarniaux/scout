# DynamoDB table: scout-jobs
resource "aws_dynamodb_table" "jobs" {
  name                        = "${var.project_name}-jobs"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "pk"
  range_key                   = "sk"
  deletion_protection_enabled = true

  # Point-in-time recovery
  point_in_time_recovery {
    enabled = true
  }

  # TTL
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Hash key
  attribute {
    name = "pk"
    type = "S"
  }

  # Range key
  attribute {
    name = "sk"
    type = "S"
  }

  # GSI: DateIndex (PK=gsi1pk S, SK=postedDate S)
  attribute {
    name = "gsi1pk"
    type = "S"
  }

  attribute {
    name = "postedDate"
    type = "S"
  }

  global_secondary_index {
    name            = "DateIndex"
    hash_key        = "gsi1pk"
    range_key       = "postedDate"
    projection_type = "ALL"
  }

  # GSI: RatingIndex (PK=gsi1pk S, SK=glassdoorRating S)
  attribute {
    name = "glassdoorRating"
    type = "S"
  }

  global_secondary_index {
    name            = "RatingIndex"
    hash_key        = "gsi1pk"
    range_key       = "glassdoorRating"
    projection_type = "ALL"
  }

  tags = {
    Name = "${var.project_name}-jobs"
  }
}

# DynamoDB table: scout-user-status
resource "aws_dynamodb_table" "user_status" {
  name                        = "${var.project_name}-user-status"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "pk"
  range_key                   = "sk"
  deletion_protection_enabled = true

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  # GSI: StatusIndex (PK=pk S, SK=status S)
  attribute {
    name = "status"
    type = "S"
  }

  global_secondary_index {
    name            = "StatusIndex"
    hash_key        = "pk"
    range_key       = "status"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "${var.project_name}-user-status"
  }
}

# DynamoDB table: scout-users
resource "aws_dynamodb_table" "users" {
  name                        = "${var.project_name}-users"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "pk"
  deletion_protection_enabled = true

  attribute {
    name = "pk"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "${var.project_name}-users"
  }
}

# DynamoDB table: scout-job-scores
# Per-user AI match scores — pk=USER#{sub}, sk=JOB#{hash}.
# Deletion protection intentionally omitted: scores are derived data
# that can be recomputed from resumes + job descriptions at any time.
resource "aws_dynamodb_table" "job_scores" {
  name         = "${var.project_name}-job-scores"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  # TTL mirrors the jobs table (60-day default) so scores are purged
  # automatically when the corresponding job expires.
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "${var.project_name}-job-scores"
  }
}

# DynamoDB table: scout-glassdoor-cache
resource "aws_dynamodb_table" "glassdoor_cache" {
  name         = "${var.project_name}-glassdoor-cache"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  # TTL for cache expiration
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "${var.project_name}-glassdoor-cache"
  }
}
