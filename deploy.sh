#!/bin/bash
# Well-Architected Foundations Assessment Deploy Script
# Zips source, uploads to S3, deploys CloudFormation stack.
#
# Usage:
#   ./deploy.sh --profile my-profile --region us-east-1
#   ./deploy.sh --profile my-profile --region us-east-1 --email user@example.com
#   ./deploy.sh --profile my-profile --region us-east-1 --stack-name wa-foundations-test
#
# Prerequisites:
#   - AWS CLI v2 installed
#   - Credentials with permissions to create: CloudFormation, IAM, S3, CodeBuild, Lambda
#   - Should be run against the organization MANAGEMENT account for full results

set -euo pipefail

# Defaults
PROFILE=""
REGION="us-east-1"
STACK_NAME="wa-foundations-assessment"
EMAIL=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --profile)
            PROFILE="$2"
            shift 2
            ;;
        --region)
            REGION="$2"
            shift 2
            ;;
        --stack-name)
            STACK_NAME="$2"
            shift 2
            ;;
        --email)
            EMAIL="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: ./deploy.sh --profile <aws-profile> --region <region> [--stack-name <name>] [--email <address>]"
            echo ""
            echo "Options:"
            echo "  --profile     AWS CLI profile to use (required)"
            echo "  --region      AWS region (default: us-east-1)"
            echo "  --stack-name  CloudFormation stack name (default: wa-foundations-assessment)"
            echo "  --email       Email for completion notifications (optional)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [ -z "$PROFILE" ]; then
    echo "ERROR: --profile is required"
    echo "Usage: ./deploy.sh --profile <aws-profile> --region <region>"
    exit 1
fi

AWS_OPTS="--profile $PROFILE --region $REGION"

echo "============================================"
echo "  Well-Architected Foundations Assessment"
echo "============================================"
echo "Profile:    $PROFILE"
echo "Region:     $REGION"
echo "Stack:      $STACK_NAME"
echo "Email:      ${EMAIL:-none}"
echo "============================================"
echo ""

# 1. Get account ID
echo "[1/5] Detecting account..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text $AWS_OPTS)
echo "  Account: $ACCOUNT_ID"

# 2. Zip source
echo "[2/5] Packaging source code..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZIP_FILE="/tmp/wa-foundations-source-${ACCOUNT_ID}.zip"
rm -f "$ZIP_FILE"
(cd "$SCRIPT_DIR" && zip -qr "$ZIP_FILE" src/ requirements.txt buildspec.yml -x "**/__pycache__/*")
echo "  Created: $ZIP_FILE ($(du -h "$ZIP_FILE" | cut -f1))"

# 3. Create/upload to source bucket
# The bucket name includes the region so each region gets its own co-located
# source bucket. S3 bucket names are global, so a region-less name would be
# created in the first deploy's region and then reused by later deploys to
# other regions — leaving CodeBuild in region B trying to fetch its source zip
# from a bucket physically in region A, which fails at DOWNLOAD_SOURCE.
SOURCE_BUCKET="wa-foundations-source-${ACCOUNT_ID}-${REGION}"
SOURCE_KEY="wa-foundations-source.zip"
echo "[3/5] Uploading source to s3://$SOURCE_BUCKET/$SOURCE_KEY..."

# The bucket name is predictable, so confirm this account owns it before
# uploading code that CodeBuild will run. HeadBucket with
# --expected-bucket-owner returns 404 when the bucket does not exist and 403
# when it exists but belongs to another account (or is otherwise inaccessible).
if HEAD_ERROR=$(aws s3api head-bucket --bucket "$SOURCE_BUCKET" \
        --expected-bucket-owner "$ACCOUNT_ID" $AWS_OPTS 2>&1 >/dev/null); then
    echo "  Using existing source bucket owned by this account."
elif [[ "$HEAD_ERROR" == *"(404)"* ]]; then
    # 'aws s3 mb' derives the LocationConstraint from --region, including for
    # us-east-1. Passing --create-bucket-configuration here is invalid: that
    # option belongs to 'aws s3api create-bucket', not the high-level 's3 mb'.
    aws s3 mb "s3://$SOURCE_BUCKET" $AWS_OPTS
else
    echo "  ERROR: Source bucket $SOURCE_BUCKET exists but is not accessible as a"
    echo "  bucket owned by account $ACCOUNT_ID. Refusing to upload source code."
    echo "  $HEAD_ERROR"
    exit 1
fi
aws s3api put-object \
    --bucket "$SOURCE_BUCKET" \
    --key "$SOURCE_KEY" \
    --body "$ZIP_FILE" \
    --expected-bucket-owner "$ACCOUNT_ID" \
    $AWS_OPTS >/dev/null
rm -f "$ZIP_FILE"
echo "  Done."

# 4. Deploy CloudFormation stack
echo "[4/5] Deploying CloudFormation stack '$STACK_NAME'..."
PARAMS="SourceBucket=$SOURCE_BUCKET SourceKey=$SOURCE_KEY AutoStartBuild=false"
if [ -n "$EMAIL" ]; then
    PARAMS="$PARAMS EmailAddress=$EMAIL"
fi

PROJECT_NAME="$STACK_NAME"

# --no-fail-on-empty-changeset: redeploying an unchanged template is expected
# (for example, to pick up a new source package) and must not stop the script.
aws cloudformation deploy \
    --template-file "$SCRIPT_DIR/deployment/wafa-stack.yaml" \
    --stack-name "$STACK_NAME" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides $PARAMS \
    --no-fail-on-empty-changeset \
    $AWS_OPTS

echo "  Stack deployed successfully."

# AutoStartBuild is disabled above so this script owns the build invocation and
# can wait on the exact ID returned by StartBuild. This remains correct if an
# unrelated manual or scheduled build starts during the deployment.
echo "  Starting CodeBuild project '$PROJECT_NAME'..."
BUILD_ID=$(aws codebuild start-build \
    --project-name "$PROJECT_NAME" \
    --query 'build.id' --output text $AWS_OPTS)
if [ -z "$BUILD_ID" ] || [ "$BUILD_ID" = "None" ]; then
    echo "  ERROR: CodeBuild did not return a build ID."
    exit 1
fi
echo "  Build: $BUILD_ID"

# 5. Show results
echo "[5/5] Getting results..."
echo ""

RESULTS_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`ResultsBucket`].OutputValue' \
    --output text $AWS_OPTS)

# Wait for this deployment's build to complete. Match the CodeBuild project
# timeout (TimeoutInMinutes: 10) plus a minute for queueing.
echo "  Waiting for CodeBuild to complete..."
BUILD_SUCCEEDED="false"
for i in $(seq 1 66); do
    STATUS=$(aws codebuild batch-get-builds \
        --ids "$BUILD_ID" \
        --query 'builds[0].buildStatus' --output text $AWS_OPTS)

    if [ "$STATUS" = "SUCCEEDED" ]; then
        echo "  Build SUCCEEDED!"
        BUILD_SUCCEEDED="true"
        break
    elif [ "$STATUS" = "FAILED" ] || [ "$STATUS" = "FAULT" ] || [ "$STATUS" = "STOPPED" ] || [ "$STATUS" = "TIMED_OUT" ]; then
        echo "  Build FAILED (status: $STATUS)"
        echo "  Check logs: aws codebuild batch-get-builds --ids $BUILD_ID $AWS_OPTS"
        exit 1
    fi
    sleep 10
done

if [ "$BUILD_SUCCEEDED" != "true" ]; then
    echo "  Build did not finish within the 11-minute wait window."
    echo "  Check status: aws codebuild batch-get-builds --ids $BUILD_ID $AWS_OPTS"
    exit 1
fi

echo ""
echo "============================================"
echo "  Assessment Deployment Complete!"
echo "============================================"
echo ""
echo "Results bucket: $RESULTS_BUCKET"
echo "Reports:"
aws s3 ls "s3://$RESULTS_BUCKET/$ACCOUNT_ID/" $AWS_OPTS 2>/dev/null || echo "  (build may still be running)"
echo ""
echo "View report:"
echo "  aws s3 presign s3://$RESULTS_BUCKET/$ACCOUNT_ID/wafa-report.html --expires-in 3600 $AWS_OPTS"
echo ""
echo "Re-run assessment:"
echo "  aws codebuild start-build --project-name $PROJECT_NAME $AWS_OPTS"
echo ""
echo "Tear down:"
echo "  The results bucket ($RESULTS_BUCKET) is versioned. Permanently delete every"
echo "  object version and delete marker before deleting the stack, or the stack"
echo "  deletion fails. Follow the 'Tear Down' section of README.md, then delete"
echo "  the source bucket s3://$SOURCE_BUCKET. The source bucket is"
echo "  region-specific; tear down each region you deployed to."
