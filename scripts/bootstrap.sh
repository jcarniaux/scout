#!/bin/bash
# =============================================================================
# Scout — First-time AWS account bootstrap
# =============================================================================
# Run this ONCE before the first Terraform apply. It creates:
#   1. S3 bucket for Terraform state
#   2. DynamoDB table for state locking
#   3. IAM OIDC provider for GitHub Actions
#   4. IAM role for GitHub Actions deployments
#
# Prerequisites:
#   - AWS CLI configured with admin credentials
#   - Your GitHub repo name (owner/repo format)
# =============================================================================

set -euo pipefail

AWS_REGION="us-east-1"
PROJECT="scout"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Prompt for GitHub repo
read -rp "GitHub repo (e.g., your-username/scout): " GITHUB_REPO

echo ""
echo "=== Bootstrapping Scout for AWS Account: $ACCOUNT_ID ==="
echo ""

# --- 1. Terraform State Bucket ---
STATE_BUCKET="${PROJECT}-tfstate-${ACCOUNT_ID}"
echo "Creating Terraform state bucket: $STATE_BUCKET"

if aws s3api head-bucket --bucket "$STATE_BUCKET" 2>/dev/null; then
    echo "  Bucket already exists, skipping."
else
    aws s3api create-bucket \
        --bucket "$STATE_BUCKET" \
        --region "$AWS_REGION"

    aws s3api put-bucket-versioning \
        --bucket "$STATE_BUCKET" \
        --versioning-configuration Status=Enabled

    aws s3api put-bucket-encryption \
        --bucket "$STATE_BUCKET" \
        --server-side-encryption-configuration '{
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        }'

    aws s3api put-public-access-block \
        --bucket "$STATE_BUCKET" \
        --public-access-block-configuration \
            BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

    echo "  ✓ Created and secured"
fi

# --- 2. Terraform Lock Table ---
LOCK_TABLE="${PROJECT}-tflock"
echo "Creating DynamoDB lock table: $LOCK_TABLE"

if aws dynamodb describe-table --table-name "$LOCK_TABLE" --region "$AWS_REGION" 2>/dev/null; then
    echo "  Table already exists, skipping."
else
    aws dynamodb create-table \
        --table-name "$LOCK_TABLE" \
        --attribute-definitions AttributeName=LockID,AttributeType=S \
        --key-schema AttributeName=LockID,KeyType=HASH \
        --billing-mode PAY_PER_REQUEST \
        --region "$AWS_REGION" > /dev/null

    echo "  ✓ Created"
fi

# --- 3. GitHub OIDC Provider ---
echo "Configuring GitHub OIDC provider..."

OIDC_ARN=$(aws iam list-open-id-connect-providers \
    --query "OpenIDConnectProviderList[?ends_with(Arn, 'token.actions.githubusercontent.com')].Arn" \
    --output text)

if [ -n "$OIDC_ARN" ]; then
    echo "  OIDC provider already exists: $OIDC_ARN"
else
    OIDC_ARN=$(aws iam create-open-id-connect-provider \
        --url "https://token.actions.githubusercontent.com" \
        --client-id-list "sts.amazonaws.com" \
        --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1" \
        --query 'OpenIDConnectProviderArn' \
        --output text)

    echo "  ✓ Created: $OIDC_ARN"
fi

# --- 4. GitHub Actions IAM Role ---
ROLE_NAME="${PROJECT}-github-actions"
echo "Creating IAM role: $ROLE_NAME"

TRUST_POLICY=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Federated": "arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
            },
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {
                "StringEquals": {
                    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                },
                "StringLike": {
                    "token.actions.githubusercontent.com:sub": "repo:${GITHUB_REPO}:*"
                }
            }
        }
    ]
}
EOF
)

if aws iam get-role --role-name "$ROLE_NAME" 2>/dev/null; then
    echo "  Role already exists, updating trust policy..."
    aws iam update-assume-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-document "$TRUST_POLICY"
else
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document "$TRUST_POLICY" \
        --description "Scout GitHub Actions deployment role" > /dev/null
fi

# Attach a single consolidated inline policy instead of multiple managed policies.
# AWS limits roles to 10 attached managed policies; using one inline policy avoids
# that limit entirely and keeps permissions auditable in a single place.
#
# The policy document lives at scripts/github-actions-policy.json.
# Idempotent: put-role-policy overwrites silently if the policy already exists.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POLICY_FILE="$SCRIPT_DIR/github-actions-policy.json"

if [[ ! -f "$POLICY_FILE" ]]; then
    echo "ERROR: $POLICY_FILE not found — cannot configure role permissions" >&2
    exit 1
fi

aws iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name "scout-deploy-policy" \
    --policy-document "file://$POLICY_FILE"
echo "  ✓ Inline policy scout-deploy-policy attached"

# Detach any legacy managed policies left over from previous bootstrap runs.
# Safe to run even if none are attached.
LEGACY_POLICIES=(
    "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"
    "arn:aws:iam::aws:policy/AmazonS3FullAccess"
    "arn:aws:iam::aws:policy/AWSLambda_FullAccess"
    "arn:aws:iam::aws:policy/AmazonAPIGatewayAdministrator"
    "arn:aws:iam::aws:policy/AmazonCognitoPowerUser"
    "arn:aws:iam::aws:policy/CloudFrontFullAccess"
    "arn:aws:iam::aws:policy/AmazonSESFullAccess"
    "arn:aws:iam::aws:policy/AmazonSQSFullAccess"
    "arn:aws:iam::aws:policy/AWSStepFunctionsFullAccess"
    "arn:aws:iam::aws:policy/AmazonEventBridgeFullAccess"
    "arn:aws:iam::aws:policy/SecretsManagerReadWrite"
    "arn:aws:iam::aws:policy/IAMFullAccess"
    "arn:aws:iam::aws:policy/AmazonRoute53FullAccess"
    "arn:aws:iam::aws:policy/AWSWAFFullAccess"
    "arn:aws:iam::aws:policy/CloudWatchFullAccessV2"
    "arn:aws:iam::aws:policy/AmazonSNSFullAccess"
)
for policy in "${LEGACY_POLICIES[@]}"; do
    aws iam detach-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-arn "$policy" 2>/dev/null && echo "  ✓ Detached legacy $policy" || true
done

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
echo "  ✓ Role configured: $ROLE_ARN"

# --- Summary ---
echo ""
echo "============================================="
echo "  Bootstrap complete!"
echo "============================================="
echo ""
echo "1. Update terraform/providers.tf — uncomment the S3 backend:"
echo "   bucket         = \"$STATE_BUCKET\""
echo "   dynamodb_table = \"$LOCK_TABLE\""
echo ""
echo "2. Add these GitHub repository secrets:"
echo "   AWS_DEPLOY_ROLE_ARN = $ROLE_ARN"
echo "   ALERT_EMAIL         = your-email@example.com"
echo ""
echo "3. After first 'terraform apply', also add:"
echo "   COGNITO_USER_POOL_ID"
echo "   COGNITO_USER_POOL_CLIENT_ID"
echo "   API_GATEWAY_URL"
echo "   FRONTEND_BUCKET"
echo "   CLOUDFRONT_DISTRIBUTION_ID"
echo ""
echo "4. Run: cd terraform && terraform init && terraform plan"
echo ""
