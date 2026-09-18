# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Well-Architected Foundations Assessment is a **read-only** Python tool that assesses an AWS Organization against the AWS Well-Architected Foundations best practices. It runs from the org management account (or a member/standalone account with reduced coverage), discovers the environment, runs a fixed set of governance checks against live AWS APIs via `boto3`, scores a maturity level (1–5), and emits an HTML report, CSV, raw JSON, and a console table.

The tool only calls read/describe/list APIs — it never mutates the AWS environment. The IAM role provisioned by the CloudFormation stack is likewise read-only.

## Commands

```bash
# Install dev deps (into a venv)
pip install -r requirements-dev.txt

# Run the full test suite (fast, ~0.5s)
python -m pytest tests/unit/ -v

# Run a single test file / test
python -m pytest tests/unit/test_maturity_scoring.py -v
python -m pytest tests/unit/test_organization.py::test_check_org_exists -v

# Coverage
python -m pytest tests/unit/ --cov=src --cov-report=term-missing

# Run the assessment locally against your credentials (writes reports to ./reports)
AWS_PROFILE=my-profile python -m src.main --output ./reports

# Run and upload reports to S3 (used in CodeBuild)
python -m src.main --output s3://bucket/prefix/
```

There is no linter configured; match existing style. Tests use `moto` to mock AWS — no real AWS calls are made in the test suite.

## Deployment

`./deploy.sh --profile <p> --region us-east-1` packages `src/`, uploads it to `wafa-source-<account-id>`, and deploys `deployment/wafa-stack.yaml` (IAM role + CodeBuild project + results bucket + a Lambda-backed CustomResource that auto-triggers the first build). CodeBuild runs `buildspec.yml`, which invokes `python -m src.main --output s3://$RESULTS_BUCKET/`. Re-run assessments with `aws codebuild start-build --project-name WAFA-wafa`.

## Architecture

The pipeline in `src/main.py::run()` is: **discover → run checks (gated by account type) → score maturity → render reports → output (local dir or S3)**.

### Account-type gating (the central control-flow decision)
`src/discovery/account_type.py::detect_account_type()` classifies the account as `management`, `member`, or `standalone` by comparing `sts:GetCallerIdentity` to `organizations:DescribeOrganization`'s `MasterAccountId`. `main.py` branches on `is_management_account`:
- **Management account** → runs the full ~35 checks (all `run_all()` modules).
- **Member / standalone** → runs only `identity.run_all(..., is_management_account=False)` and `account_resources.run_all(..., is_management_account=False)` (the ~9 per-account checks). Org-wide checks are skipped because the APIs aren't accessible.

`detect_partition()` derives partition (`aws` / `aws-us-gov` / `aws-cn`) and default region from `AWS_DEFAULT_REGION` (default `us-east-1`) so CUR/global checks target the right region. `get_enabled_regions()` always bootstraps from `us-east-1` (EC2 `DescribeRegions` filtered to `opt-in-not-required`) and falls back to a hardcoded commercial-region list on failure.

### The check contract (most important convention)
Every check function returns a **flat dict** with a fixed shape — this dict is the interface consumed by maturity scoring, the radar chart, CSV, and JSON. Keys:
`check` (unique display name — used as a join key elsewhere), `description`, `status` (`"complete"` | `"incomplete"` | `"error"`), `required` (bool), `weight` (int, drives "highest-impact next steps" ordering), `loe` (level-of-effort int), `remediationLink`, and `error` (only on `status == "error"`).

Conventions that must be preserved when adding checks:
- **Wrap every check body in `try/except`** and return a dict with `status: "error"` + `error: str(e)` on failure. A check must never raise — a failed API call is a reported error, not a crash.
- The `check` string is a **stable key**. `maturity.py` and `html_report.py` reference checks *by exact name string*. Renaming a check silently breaks maturity scoring and the radar chart. If you rename or add a check, update `src/checks/maturity.py`'s `_LEVEL_*` lists and `src/report/html_report.py`'s `CAPABILITY_AXES` accordingly.
- Each check module exposes a `run_all(...)` that returns a list of these dicts; `main.py` `extend`s them into one flat `checks` list.

### Check modules (`src/checks/`) — mapped to functional requirements (FR-#)
- `organization.py` (FR-3): org exists, ≥4 accounts, Log Archive/Audit accounts, SCP/Tag/Backup/RCP policies enabled, Security/Workloads/Infrastructure OUs. `check_org_exists`/`check_management_account` are called directly from `main.py` (not via `run_all`).
- `org_services.py` (FR-4): org-level service integrations (CloudTrail, Config, GuardDuty, Security Hub, Access Analyzer, RAM, IAM Identity Center, StackSets, Backup, Cost Optimization Hub).
- `control_tower.py` (FR-5): deployed / not drifted / latest version.
- `identity.py` (FR-6): IAM Identity Center configured, no IAM users. Takes `is_management_account` to pick which subset runs.
- `account_resources.py` (FR-7/8): per-account resources (CloudTrail trail, org trail, Config recorder + delivery channel, no EC2, no VPCs, CUR report, StackSets org access).
- `delegated_admin.py` (FR-9): informational list of delegated administrators (not a pass/fail check — bypasses the check dict shape).
- `maturity.py` (FR-11): scores level 1–5.

### Multi-region scanning
`account_resources.py` scans regions **concurrently** with `ThreadPoolExecutor`. The shared helper `_check_regions_for_resource(regions, service, api_method, result_key, check_any=...)` covers the common "does this resource exist in any region" pattern; checks with per-region-count logic (EC2, VPCs, org trail) inline their own executor loop. Regions come from `src/discovery/regions.py::get_enabled_regions()`.

### Maturity scoring (`src/checks/maturity.py`)
`calculate_maturity_level(checks)` evaluates levels sequentially (2→3→4→5); the first unmet level determines the result. It joins to checks *by name* via `_check_status`. Returns the current level plus `next_level_progress` and `next_level_checks_needed` (missing checks sorted by `weight`, highest-impact first). Level 5 requires every **non-error** check complete — checks with `status == "error"` are excluded from the L5 gate (errors fail open, not closed).

### Reports (`src/report/`)
- `html_report.py`: Jinja2-rendered single-page report with an inline-SVG radar (`_build_radar_svg`, no network/CDN dependency so the report renders offline) over 7 capability axes. Networking & Connectivity is included but maps to an empty check list, so it always scores 0 (no Phase 1 checks assess it). `CAPABILITY_AXES` maps axis → list of check names (a check may feed multiple axes); `_calculate_axis_scores` computes % complete per axis. Axis membership is defined here by check-name string, independent of which FR module the check lives in.
- `csv_export.py`: flat CSV of the check dicts for spreadsheet/Jira import.
- Raw JSON is assembled inline in `main.py` (account_info + maturity + checks + delegated_administrators).

## Specs

`.kiro/specs/` holds the authoritative requirements (`requirements.md`, FR-# numbering), design (`design.md`), and the WA Foundations check definitions (`wa-foundations-checks.json`). When adding or changing a check, reconcile it with these.
