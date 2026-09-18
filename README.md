# WAFA: AWS Well-Architected Foundations Assessment

![License: MIT-0](https://img.shields.io/badge/License-MIT--0-yellow.svg)
![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![Tests](https://img.shields.io/badge/tests-157%20passing-brightgreen.svg)

WAFA is an open-source, read-only tool that runs an automated AWS Well-Architected Foundations assessment across an AWS Organization. It evaluates your multi-account architecture, governance, and security posture against AWS Well-Architected Foundations best practices, then produces an actionable HTML maturity report with prioritized remediation guidance.

Use it to benchmark landing zone maturity, prepare for a Well-Architected Framework Review (WAFR), or track multi-account governance and security posture over time.

**Who is this for:** AWS administrators, cloud platform and DevOps engineers, and Solutions Architects who manage AWS Organizations, AWS Control Tower, or a multi-account landing zone.

<!--
Add a screenshot of the generated HTML report here. Keep the descriptive alt text:
it is read by GitHub, search engines, and screen readers.

![AWS Well-Architected Foundations assessment HTML report with a radar chart of seven capability axes and a maturity score](docs/report-screenshot.png)
-->

## What It Checks

| Category | Checks |
|----------|--------|
| Organization Governance (FR-3) | Org exists, 4+ accounts, Log Archive, Audit, SCPs, Tag/Backup/RCP policies, Security/Workloads/Infrastructure OUs |
| Org Service Integrations (FR-4) | CloudTrail, Config, GuardDuty, Security Hub, Access Analyzer, RAM, IAM Identity Center, StackSets, Backup, Cost Optimization Hub |
| Control Tower (FR-5) | Deployed, not drifted, latest version |
| Identity (FR-6) | IAM Identity Center configured, no IAM users in the assessed account |
| Account Resources (FR-7) | CloudTrail trail, org trail, Config recorder, Config delivery channel, no EC2, no VPCs, CUR report |
| CloudFormation (FR-8) | StackSets org access enabled |

## Output

- **Self-contained interactive HTML report** with radar chart (7 WA Foundations capability axes), maturity level (1-5), and filterable check table
- **CSV export** for spreadsheet/Jira import
- **Raw JSON** for automation
- **Console table** summary

## Quick Start

### Option A: Deploy with one command (recommended)

```bash
git clone https://github.com/aws-samples/sample-wa-foundations-assessment.git
cd sample-wa-foundations-assessment
./deploy.sh --profile <your-aws-profile> --region us-east-1
```

This will:
1. Package the source code
2. Upload it to an S3 bucket in your account
3. Deploy a CloudFormation stack (IAM Role + CodeBuild + S3 results bucket)
4. Automatically trigger the assessment
5. Show you the results

**Prerequisites:**
- AWS CLI v2 installed
- AWS credentials (profile) for the **organization management account**
- Permissions: CloudFormation, IAM, S3, CodeBuild, Lambda (see [Deployer Permissions](#deployer-permissions))

**Options:**
```bash
./deploy.sh --profile my-profile --region us-east-1                    # Basic
./deploy.sh --profile my-profile --region us-east-1 --email user@example.com  # With email notification
./deploy.sh --profile my-profile --region us-east-1 --stack-name mystack  # Custom stack name
```

### Option B: Run locally (no infrastructure)

**Requires:** Python 3.9+ (CodeBuild and the stack's Lambda run on 3.12) and AWS credentials.

```bash
pip install -r requirements.txt
AWS_PROFILE=my-profile python -m src.main --output ./reports
open reports/wafa-report.html
```

This runs the assessment using your local credentials and saves reports to disk. No S3 bucket or CodeBuild project is created.

### Option C: CloudShell

```bash
git clone https://github.com/aws-samples/sample-wa-foundations-assessment.git
cd sample-wa-foundations-assessment
pip install -q -r requirements.txt
python -m src.main --output .
```

Download the report files from the CloudShell file browser.

## Re-running the Assessment

After the initial deploy, re-run anytime:

```bash
aws codebuild start-build --project-name WAFA-wafa --profile <profile> --region us-east-1
```

Or click "Start build" in the CodeBuild console.

## Viewing Results

```bash
# Generate a temporary URL (expires in 1 hour)
aws s3 presign s3://<results-bucket>/<account-id>/wafa-report.html --expires-in 3600 --profile <profile> --region us-east-1

# Or download locally
aws s3 cp s3://<results-bucket>/<account-id>/ ./results/ --recursive --profile <profile> --region us-east-1
```

## Tear Down

```bash
# Delete the stack (removes CodeBuild, IAM role, Lambda, SNS)
aws cloudformation delete-stack --stack-name wafa --profile <profile> --region us-east-1

# Empty and delete the results bucket
aws s3 rb s3://<results-bucket> --force --profile <profile> --region us-east-1

# Delete the source bucket
aws s3 rb s3://wafa-source-<account-id> --force --profile <profile> --region us-east-1
```

## Maturity Levels

The assessment maps your results to the AWS Well-Architected Foundations maturity model:

| Level | Name | Criteria |
|-------|------|----------|
| 1 | Base | No org or minimal setup (< 4 accounts, no OUs) |
| 2 | Established | Org + 4 accounts + at least 1 OU |
| 3 | Intermediate | + SCPs, Security OU, Control Tower, tags, CloudTrail, Config, IAM IDC |
| 4 | Advanced | + GuardDuty, Security Hub, Access Analyzer, Backup, RCP, no workloads in mgmt |
| 5 | Expert | All Phase 1 checks complete |

## Account Modes

| Mode | How detected | Checks run |
|------|-------------|------------|
| Management account | `Organization.MasterAccountId == current account` | All 35 checks |
| Member account | In org but not the management account | 9 checks (CloudTrail, Config, EC2, VPC, IAM users) |
| Standalone | No organization | 9 checks (same as member) |

## Deployer Permissions

The person deploying the stack needs these permissions:

| Permission | Reason |
|-----------|--------|
| `cloudformation:*` | Create/update/describe the stack |
| `iam:CreateRole`, `iam:PutRolePolicy`, `iam:PassRole`, `iam:GetRole` | Template creates IAM roles |
| `s3:CreateBucket`, `s3:PutObject`, `s3:PutBucketEncryption`, `s3:PutBucketPublicAccessBlock`, `s3:PutBucketVersioning` | Create results + source buckets |
| `codebuild:CreateProject` | Create the CodeBuild project |
| `lambda:CreateFunction`, `lambda:InvokeFunction` | Custom Resource auto-trigger |
| `sns:CreateTopic`, `sns:Subscribe` | Only if email parameter provided |

**Note:** The WAFARole created by the stack only has read-only permissions. It cannot modify your AWS environment.

## Development

Requires Python 3.9+ (tested on 3.12).

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Run tests (157 tests, ~0.5s)
python -m pytest tests/unit/ -v

# Run with coverage
python -m pytest tests/unit/ --cov=src --cov-report=term-missing
```

## Project Structure

```
sample-wa-foundations-assessment/
├── src/
│   ├── main.py                  # Orchestrator
│   ├── discovery/
│   │   ├── account_type.py      # Management/member/standalone detection
│   │   └── regions.py           # Region discovery
│   ├── checks/
│   │   ├── organization.py      # FR-3: Org governance (12 checks)
│   │   ├── org_services.py      # FR-4: Org service integrations (10 checks)
│   │   ├── control_tower.py     # FR-5: Control Tower (3 checks)
│   │   ├── identity.py          # FR-6: IAM/IDC (2 checks)
│   │   ├── account_resources.py # FR-7/8: Per-account resources (8 checks)
│   │   ├── delegated_admin.py   # FR-9: Delegated admins (informational)
│   │   └── maturity.py          # FR-11: Level 1-5 scoring
│   └── report/
│       ├── html_report.py       # Interactive HTML + inline SVG radar
│       └── csv_export.py        # CSV export
├── tests/unit/                  # 157 pytest tests (95% coverage)
├── deployment/
│   └── wafa-stack.yaml          # CloudFormation template
├── deploy.sh                    # One-command deploy script
├── buildspec.yml                # CodeBuild instructions
├── run.sh                       # CloudShell quick start
├── requirements.txt             # Runtime deps (boto3, jinja2)
└── requirements-dev.txt         # Dev deps (pytest, moto, coverage)
```


## Related AWS Resources

- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)
- [AWS Well-Architected Tool](https://aws.amazon.com/well-architected-tool/)
- [AWS Organizations](https://aws.amazon.com/organizations/)
- [AWS Control Tower](https://aws.amazon.com/controltower/)
