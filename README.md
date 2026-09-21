# AWS Well-Architected Foundations Assessment (WAFA)

![License: MIT-0](https://img.shields.io/badge/License-MIT--0-yellow.svg)
![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![Tests](https://img.shields.io/badge/tests-168%20passing-brightgreen.svg)

WAFA is an open-source AWS foundations assessment tool. Its assessment checks
use read, list, and describe APIs to evaluate organization-level configuration
and selected resources in the account running the assessment. It produces an
actionable HTML maturity report with prioritized remediation guidance.

When run from an AWS Organizations management account, WAFA performs its full
set of organization and account checks. It does not currently assume roles into
every member account or inspect member-account resources.

Use WAFA to benchmark landing-zone maturity, help prepare for a Well-Architected
Framework Review (WAFR), or track governance and security posture over time. It
complements, but does not replace, a complete workload-level WAFR.

**Who is this for:** AWS administrators, cloud platform and DevOps engineers,
and Solutions Architects who manage AWS Organizations, AWS Control Tower, or a
multi-account landing zone.

## Contents

- [What It Checks](#what-it-checks)
- [Output](#output)
- [Maturity Levels](#maturity-levels)
- [Account Modes](#account-modes)
- [Quick Start](#quick-start)
- [Re-running the Assessment](#re-running-the-assessment)
- [Deployment Package](#deployment-package)
- [Viewing Results](#viewing-results)
- [Tear Down](#tear-down)
- [Deployment Permissions](#deployment-permissions)
- [Development](#development)
- [Project Structure](#project-structure)
- [Related AWS Resources](#related-aws-resources)

## What It Checks

| Category | Checks |
| --- | --- |
| Org Governance (FR-3) | Accounts, OUs, and Organizations policies |
| Org Integrations (FR-4) | Ten trusted-access service integrations |
| Control Tower (FR-5) | Deployment, drift, and available version |
| Identity (FR-6) | IAM Identity Center and IAM users |
| Account Resources (FR-7) | CloudTrail, Config, EC2, VPC, and cost reports |
| CloudFormation (FR-8) | StackSets organization access |

### Current scope and limitations

- Organization-level checks require the management account.
- Per-account resource checks inspect only the account running WAFA.
- Regional checks currently inspect default-enabled Regions
  (`opt-in-not-required`), not opted-in Regions.
- Dedicated account and OU checks use exact, case-insensitive names such as
  `Log Archive`, `Audit`, `Security Tooling`, `Security`, `Workloads`, and
  `Infrastructure`.
- Service-integration checks determine whether trusted access is enabled; they
  do not prove that every member account is fully configured for that service.

## Output

- **Self-contained interactive HTML report** with a radar chart covering seven
  WAFA capability axes, a maturity level from 1–5, and a filterable check table
- **CSV export** for spreadsheet or work-item import
- **Raw JSON** for automation
- **Console table** summary

### Check result statuses

- **Complete:** The check ran successfully and the observed AWS configuration
  meets the criterion.
- **Incomplete:** The check ran successfully, but the criterion is not met. This
  is a confirmed configuration gap.
- **Error:** WAFA could not reliably determine the result, usually because of
  missing permissions or an AWS API failure. An error does not necessarily mean
  the configuration is incorrect.

Only **Complete** results contribute to completion and capability scores.
**Incomplete** and **Error** results do not satisfy applicable maturity
criteria.

### Sample report

Want to see the output before running the tool? A sanitized example using
placeholder account data lives in [`sample-reports/`](sample-reports/):

- **[View a sample report](https://aws-samples.github.io/sample-wa-foundations-assessment/sample-reports/wafa-report.html)**
  — live, interactive preview through GitHub Pages
- [`wafa-report.html`](sample-reports/wafa-report.html) — HTML report source
- [`wafa-checks.csv`](sample-reports/wafa-checks.csv) — CSV export
- [`wafa-raw.json`](sample-reports/wafa-raw.json) — raw JSON

> The GitHub file links show the HTML, CSV, and JSON as source. Use
> **View a sample report** to see the report as an interactive page.

The sample models a management account with a realistic mixed posture: most
foundations are in place, with a few gaps and one permission error.

## Maturity Levels

WAFA applies a project-defined Phase 1 maturity model based on the checks
implemented in this repository. The score is an assessment aid, not an official
AWS Well-Architected Tool score.

- **Level 1 — Base:** One or more Level 2 prerequisites are not met.
- **Level 2 — Established:** The organization, management account, four or more
  accounts, and at least one recognized OU are present.
- **Level 3 — Intermediate:** Level 2 plus SCPs, a Security OU, Control Tower,
  Tag Policies, CloudTrail integration and a trail, a Config recorder, and IAM
  Identity Center.
- **Level 4 — Advanced:** Level 3 plus all ten organization service
  integrations, Backup and Resource Control Policies, Control Tower drift and
  version checks, and no IAM users, EC2 instances, or VPCs in the assessed
  account.
- **Level 5 — Expert:** Every check returned by the current Phase 1
  implementation is complete.

Only implemented checks determine the score. Descriptive maturity labels are
indicative and may not capture every characteristic of an AWS environment.
Maturity results from member or standalone accounts are provisional because
organization-wide checks are not run.

The generated HTML report renders these criteria directly from the scoring
result so its level explanation stays synchronized with the implementation.

## Account Modes

| Mode | How detected | Checks run |
| --- | --- | --- |
| Management | `MasterAccountId` matches the current account | All 35 |
| Member | Organization member but not management | 9 limited checks |
| Standalone | No organization | 9 limited checks |

The limited assessment includes organization/account detection, IAM users,
CloudTrail, Config, EC2, and VPC checks in the assessed account.

## Quick Start

### Option A: Deploy with one command (recommended)

```bash
git clone https://github.com/aws-samples/sample-wa-foundations-assessment.git
cd sample-wa-foundations-assessment
./deploy.sh --profile <your-aws-profile> --region us-east-1
```

This will:

1. Package the assessment code as `wa-foundations-source.zip`.
2. Upload the package to a region-specific S3 source bucket.
3. Deploy a CloudFormation stack containing the assessment resources.
4. Automatically trigger the first CodeBuild assessment.
5. Wait for the build and display the report location.

**Prerequisites:**

- AWS CLI v2
- `zip`
- AWS credentials for the organization management account to receive the full
  assessment; member and standalone accounts receive limited assessments
- Permission to deploy the resources summarized in
  [Deployment Permissions](#deployment-permissions)

**Options:**

```bash
# Basic
./deploy.sh --profile my-profile --region us-east-1

# Email notification
./deploy.sh \
  --profile my-profile \
  --region us-east-1 \
  --email user@example.com

# Custom CloudFormation stack name
./deploy.sh \
  --profile my-profile \
  --region us-east-1 \
  --stack-name mystack
```

### Option B: Run locally (no deployed infrastructure)

**Requires:** Python 3.9+ and AWS credentials. CodeBuild and the stack's Lambda
function use Python 3.12.

```bash
pip install -r requirements.txt
AWS_PROFILE=my-profile python -m src.main --output ./reports
```

Open `reports/wafa-report.html` in a browser. On macOS, for example:

```bash
open reports/wafa-report.html
```

This runs the assessment with your local credentials and saves reports to disk.
It does not create an S3 bucket, CodeBuild project, or other deployed resource.

### Option C: CloudShell

```bash
git clone https://github.com/aws-samples/sample-wa-foundations-assessment.git
cd sample-wa-foundations-assessment
./run-local.sh
```

Download the generated report files from the CloudShell file browser.

## Re-running the Assessment

After the initial deployment, re-run the default stack at any time:

```bash
aws codebuild start-build \
  --project-name wa-foundations-assessment \
  --profile <profile> \
  --region us-east-1
```

The default CloudFormation stack and CodeBuild project are both named
`wa-foundations-assessment`. For a custom deployment, the CodeBuild project
uses the stack name; for example, `--stack-name wa-foundations-test-1` creates
a project named `wa-foundations-test-1`. You can also choose **Start build** in
the CodeBuild console.

The results bucket is named `wa-foundations-results-<stack-UUID>` so it remains
globally unique without repeating the stack name.

> **Earlier test deployments:** The previous default stack name was `wafa`.
> Running the updated script without `--stack-name` creates the new
> `wa-foundations-assessment` stack. Delete the temporary `wafa` stack
> separately when it is no longer needed.

## Deployment Package

`deploy.sh` creates a temporary local file named
`/tmp/wa-foundations-source-<account-id>.zip`. It contains:

- `src/`
- `requirements.txt`
- `buildspec.yml`

The script uploads it to:

```text
s3://wa-foundations-source-<account-id>-<region>/wa-foundations-source.zip
```

The local temporary file is deleted after upload. The source bucket is created
outside CloudFormation and must remain available for future CodeBuild runs.
Deleting it causes builds to fail during `DOWNLOAD_SOURCE`.

Running `deploy.sh` again uploads the current local source to the same object
key. Do not place credentials or other sensitive files in the deployment
package. Review the source bucket against your organization's S3 encryption,
public-access, lifecycle, and retention requirements.

## Viewing Results

```bash
# Generate a temporary URL that expires in one hour
aws s3 presign \
  s3://<results-bucket>/<account-id>/wafa-report.html \
  --expires-in 3600 \
  --profile <profile> \
  --region us-east-1

# Download all report formats
aws s3 cp \
  s3://<results-bucket>/<account-id>/ \
  ./results/ \
  --recursive \
  --profile <profile> \
  --region us-east-1
```

## Tear Down

The results bucket has versioning enabled. Permanently delete all object
versions and delete markers before deleting the stack, or CloudFormation cannot
remove the bucket.

The following Bash example requires `jq`:

```bash
PROFILE="my-profile"
REGION=us-east-1
STACK_NAME=wa-foundations-assessment

ACCOUNT_ID=$(aws sts get-caller-identity \
  --profile "$PROFILE" \
  --query Account \
  --output text)

RESULTS_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --profile "$PROFILE" \
  --region "$REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`ResultsBucket`].OutputValue' \
  --output text)

# Delete up to 1,000 versions or delete markers per iteration.
while true; do
  VERSION_DATA=$(aws s3api list-object-versions \
    --bucket "$RESULTS_BUCKET" \
    --max-items 1000 \
    --profile "$PROFILE" \
    --region "$REGION" \
    --output json)

  DELETE_PAYLOAD=$(printf '%s' "$VERSION_DATA" | jq -c '{
    Objects: (((.Versions // []) + (.DeleteMarkers // [])) |
      map({Key, VersionId})),
    Quiet: true
  }')

  OBJECT_COUNT=$(printf '%s' "$DELETE_PAYLOAD" | jq '.Objects | length')
  [ "$OBJECT_COUNT" -eq 0 ] && break

  aws s3api delete-objects \
    --bucket "$RESULTS_BUCKET" \
    --delete "$DELETE_PAYLOAD" \
    --profile "$PROFILE" \
    --region "$REGION"
done

# The now-empty results bucket is deleted with the stack.
aws cloudformation delete-stack \
  --stack-name "$STACK_NAME" \
  --profile "$PROFILE" \
  --region "$REGION"

aws cloudformation wait stack-delete-complete \
  --stack-name "$STACK_NAME" \
  --profile "$PROFILE" \
  --region "$REGION"

# The source bucket was created outside CloudFormation.
aws s3 rb \
  "s3://wa-foundations-source-${ACCOUNT_ID}-${REGION}" \
  --force \
  --profile "$PROFILE" \
  --region "$REGION"
```

## Deployment Permissions

The deployment identity must be able to perform the AWS CLI operations in
`deploy.sh` and create, update, or delete the resources in the CloudFormation
template. Exact permissions depend on whether the operation creates, updates,
or removes a stack; this table is a service-level summary, not a complete IAM
policy.

- **STS:** Resolve the deploying AWS account.
- **CloudFormation:** Manage the stack, change sets, and outputs.
- **IAM:** Manage the assessment and Lambda roles and managed policies, and
  pass roles to AWS services.
- **S3:** Manage the source package and the source and results buckets.
- **CodeBuild:** Manage the project and inspect or start builds.
- **Lambda:** Manage the custom-resource function that starts the first build.
- **SNS:** Manage the optional notification topic and subscription.

The assessment execution role is more restricted than the deployment identity:
assessment checks use read/list/describe actions. The role can additionally read
the named source bucket, write reports only to the WAFA results bucket, write
its service logs, and publish to the optional WAFA SNS topic.

## Development

Runtime usage supports Python 3.9+. Development requires Python 3.10+ because
the pinned pytest 9 release does not support Python 3.9. CI currently tests
Python 3.12.

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Run tests (168 tests)
python -m pytest tests/unit/ -v

# Run with coverage
python -m pytest tests/unit/ --cov=src --cov-report=term-missing
```

The current suite contains 168 tests and reports 95% statement coverage.

## Project Structure

```text
sample-wa-foundations-assessment/
├── src/
│   ├── main.py                  # Orchestrator
│   ├── discovery/
│   │   ├── account_type.py      # Account-mode detection
│   │   └── regions.py           # Region discovery
│   ├── checks/
│   │   ├── organization.py      # FR-3: Org governance (12 checks)
│   │   ├── org_services.py      # FR-4: Org integrations (10 checks)
│   │   ├── control_tower.py     # FR-5: Control Tower (3 checks)
│   │   ├── identity.py          # FR-6: IAM/IDC (2 checks)
│   │   ├── account_resources.py # FR-7/8: Account resources (8 checks)
│   │   ├── delegated_admin.py   # FR-9: Informational admins
│   │   └── maturity.py          # FR-11: Level 1–5 scoring
│   └── report/
│       ├── html_report.py       # Interactive HTML and SVG radar
│       └── csv_export.py        # CSV export
├── tests/unit/                  # 168 pytest tests, 95% coverage
├── deployment/
│   └── wafa-stack.yaml          # CloudFormation template
├── deploy.sh                    # Deployment script
├── buildspec.yml                # CodeBuild instructions
├── run-local.sh                 # Local and CloudShell quick start
├── requirements.txt             # Runtime dependencies
└── requirements-dev.txt         # Development and test dependencies
```

## Related AWS Resources

- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)
- [AWS Well-Architected Tool](https://aws.amazon.com/well-architected-tool/)
- [AWS Organizations](https://aws.amazon.com/organizations/)
- [AWS Control Tower](https://aws.amazon.com/controltower/)
