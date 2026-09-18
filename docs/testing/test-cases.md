# WAFA Test Cases

A shared test plan for validating WAFA (Well-Architected Foundations Assessment).
Grouped by area so multiple testers can claim sections in parallel. Each case has
a stable ID, preconditions, steps, and expected result.

## How to use this doc

This file is the **test spec** — treat it as read-only. Do not record results here.
Instead:

- Claim a section (put your alias next to the group heading) so testers don't overlap.
- Run each case and note Pass / Fail / Blocked for yourself.
- **For every Fail (or Blocked), open a Bug report issue** using the repo's
  `Bug report` issue template and fill in the details there. This keeps failures
  tracked and triageable instead of scattered in a doc.
  - **Put the test case ID in the issue title**, e.g. `[Bug]: A3 — second-region deploy fails source download`.
  - Passes don't need an issue (optionally note them wherever your team tracks a run summary).

### What to include in the bug issue (maps to the template fields)

- **Affected component** and, if relevant, the **Check name / FR-#**.
- **Account mode** (Management / Member / Standalone) and **Run mode**
  (Deployed stack / Local / CloudShell).
- **Version or commit** you tested (`git rev-parse --short HEAD`).
- **AWS partition and Region(s)** — names only.
- **Steps to reproduce**, **Actual result**, **Expected result**.
- **Sanitized logs / report excerpt** — for deploy/CodeBuild failures include the
  CodeBuild build status and the failed phase message; for report issues include
  the browser + version and a screenshot.

### Sensitive data — do not paste

Issues are visible to others. **Never include** account IDs, ARNs, credentials,
customer data, or unredacted logs. Redact identifiers before pasting. Suspected
vulnerabilities go through the repo **Security** tab, not a normal issue.

## Scanning scope (read this first — avoids the #1 misconception)

**The region you deploy into does NOT limit what gets scanned.** WAFA discovers
and scans **all default-enabled regions in the account**, regardless of where the
CodeBuild job runs.

- Region discovery (`describe_regions` with `opt-in-status = opt-in-not-required`)
  returns every default-enabled region in the account. The deploy region is only
  the region used to *make that one API call* — it does not filter the results.
- The per-account resource checks (CloudTrail, Config, EC2, VPC) then fan out
  across every region in that list, in parallel.

| The deploy region controls | The deploy region does NOT control |
|---|---|
| Where the CodeBuild project runs | Which regions get scanned |
| Where the S3 source/results buckets live | Assessment coverage (always account-wide) |
| The partition default (us-gov / cn) | — |

**Intentional exclusions (not bugs, but confirm they match expectations):**
- **Opt-in regions are skipped by design.** Regions you had to manually enable
  (e.g. ap-east-1, me-south-1, some newer regions) are NOT scanned even if they
  hold resources. See test case D4.
- **A few calls are deliberately region-pinned and correct:** IAM `list_users`
  always uses us-east-1 (IAM is global); Organizations/STS are region-agnostic
  control-plane APIs; Control Tower `GetLandingZone` is re-pointed to the landing
  zone's home region (parsed from its ARN).

**So when a report is missing a region's resources, it's one of:** (a) that region
is opt-in and excluded by design, (b) the account genuinely has nothing there, or
(c) a deploy failure meant no report was produced at all (see A3) — NOT the scan
being scoped to the deploy region. Test case D3 proves the multi-region scan works.

## Environment matrix (what "coverage" means here)

| Dimension | Values to cover |
|---|---|
| Account type | Management, Member, Standalone (not in an org) |
| Deploy method | `deploy.sh` (CloudFormation + CodeBuild), `run.sh` (CloudShell local) |
| Region | us-east-1, one other commercial region (e.g. eu-west-1), an opt-in region (e.g. ap-south-2) |
| Partition | Commercial (`aws`); GovCloud / China if you have access |
| Output target | Local dir, `s3://` URI |
| Re-run | First deploy vs. second deploy (same account, different region) |

---

## Group A — Deployment via deploy.sh (CloudFormation + CodeBuild)

Owner: ____

### A1. Fresh deploy in us-east-1 (baseline happy path)
- **Precondition:** Management account, no existing WAFA source bucket.
- **Steps:** `./deploy.sh --profile <mgmt> --region us-east-1`
- **Expected:** Stack creates; CodeBuild `SUCCEEDED`; three files land in
  `s3://<results-bucket>/<account-id>/` (wafa-report.html, wafa-checks.csv, wafa-raw.json).

### A2. Fresh deploy in a non-us-east-1 region (validates the s3 mb flag fix)
- **Precondition:** Clean account (no prior WAFA source bucket), OR fully torn down.
- **Steps:** `./deploy.sh --profile <mgmt> --region eu-west-1`
- **Expected:** Stack creates; source bucket is created **in eu-west-1**; CodeBuild
  `SUCCEEDED`; reports present.
- **Why:** Regression guard for `fix(deploy): Fix bucket creation outside us-east-1`.

### A3. Second-region deploy in an account that already deployed to us-east-1 (KNOWN RISK)
- **Precondition:** A2/A1 already ran in this account (bucket `wafa-source-<acct>` exists).
- **Steps:**
  1. `./deploy.sh --profile <mgmt> --region us-east-1` (wait for finish)
  2. `./deploy.sh --profile <mgmt> --region eu-west-1`
- **Expected (if healthy):** Second deploy's CodeBuild `SUCCEEDED`, reports present.
- **Watch for (suspected bug):** Second build FAILS at the DOWNLOAD_SOURCE phase with
  `PermanentRedirect`, `AuthorizationHeaderMalformed`, or "bucket is in this region: us-east-1".
- **Diagnostics to capture:**
  - `aws s3api get-bucket-location --bucket wafa-source-<acct>`
  - `aws codebuild batch-get-builds --ids <build-id>` (failed phase message)
- **Why:** The source bucket name is region-independent; S3 names are global, so a
  second-region deploy may reuse the us-east-1 bucket and fail the cross-region source fetch.

### A4. Deploy with email notification
- **Steps:** `./deploy.sh --profile <mgmt> --region us-east-1 --email <you>@example.com`
- **Expected:** SNS topic + subscription created; confirm the SNS subscription email;
  on build completion an email arrives referencing `s3://<results-bucket>/<account-id>/`.

### A5. Deploy without email (SNS skipped)
- **Steps:** `./deploy.sh --profile <mgmt> --region us-east-1` (no `--email`)
- **Expected:** No SNS topic created (CreateSNSTopic condition false); build still succeeds;
  post_build SNS publish is skipped (SNS_TOPIC_ARN empty).

### A6. Custom stack name
- **Steps:** `./deploy.sh --profile <mgmt> --region us-east-1 --stack-name wafa-test-1`
- **Expected:** CodeBuild project named `WAFA-wafa-test-1`; IAM role `WAFAAssessmentRole-wafa-test-1`.

### A7. Missing required --profile
- **Steps:** `./deploy.sh --region us-east-1`
- **Expected:** Exits with `ERROR: --profile is required`, non-zero exit code.

### A8. Re-run assessment without redeploying
- **Precondition:** Stack already deployed.
- **Steps:** `aws codebuild start-build --project-name WAFA-<stack> --profile <p> --region <r>`
- **Expected:** New build runs; reports overwritten in `s3://<results-bucket>/<account-id>/`.

### A9. Teardown
- **Steps:** `aws cloudformation delete-stack --stack-name <stack>` then
  `aws s3 rb s3://wafa-source-<acct> --force`
- **Expected:** Stack deletes cleanly (custom-resource Delete is a no-op); buckets removable.
- **Watch for:** Results bucket has versioning enabled — confirm whether delete-stack
  leaves the results bucket (it's not auto-emptied) and document the manual cleanup step.

---

## Group B — CloudShell / local run.sh

Owner: ____

### B1. run.sh from CloudShell in the management account
- **Steps:** clone repo, `./run.sh`
- **Expected:** Deps install; assessment runs; three report files written to the current dir.

### B2. Local run with explicit S3 output
- **Steps:** `python -m src.main --output s3://<some-bucket>/wafa/`
- **Expected:** Reports uploaded under `s3://<some-bucket>/wafa/<account-id>/`.

### B3. Local run with default output
- **Steps:** `python -m src.main` (no `--output`)
- **Expected:** Writes to `.` (current directory).

### B4. Run from CloudShell in a non-us-east-1 CloudShell region
- **Steps:** Switch CloudShell region, `./run.sh`
- **Expected:** Region discovery still enumerates all default-enabled regions; assessment
  completes (the assessment is region-agnostic; only IAM + region bootstrap are pinned).

---

## Group C — Account-mode behavior

Owner: ____

### C1. Management account = FULL assessment
- **Expected:** ~35 checks present (org governance FR-3, org services FR-4, Control Tower FR-5,
  identity FR-6 both checks, per-account FR-7 + FR-8, delegated admins FR-9).
- **Verify in wafa-raw.json:** `account_info.account_type == "management"`; org/CT/CUR/StackSets
  checks are present.

### C2. Member account = LIMITED assessment
- **Precondition:** Run from a member (non-management) account in an org.
- **Expected:** Console prints a WARNING about member account; only identity (no-IAM-users) +
  per-account FR-7.1–7.6 checks run (~9 checks). Org/CT/CUR/StackSets checks absent.
- **Verify:** `account_type == "member"`; maturity level pinned at 1.

### C3. Standalone account = LIMITED assessment
- **Precondition:** Account not in any AWS Organization.
- **Expected:** WARNING that account is not in an org; same limited check set as C2;
  `account_type == "standalone"`; maturity level 1.

### C4. Org exists / management-account-identified always run
- **Expected:** In all three modes, "AWS Organization exists" and "Management account
  identified" checks appear.

---

## Group D — Region & partition handling

Owner: ____

### D1. Region discovery returns default-enabled regions only
- **Expected:** Opt-in regions (e.g. ap-east-1, me-south-1) are NOT in the scanned set unless enabled;
  count printed matches `describe-regions` opt-in-not-required list.

### D2. Region discovery API failure → fallback list
- **How to simulate:** Deny `ec2:DescribeRegions` on the role (or force an error).
- **Expected:** Warning printed; falls back to the hardcoded 17-region `DEFAULT_REGIONS`; assessment still completes.

### D3. Resource found only in a non-us-east-1 region is detected
- **Precondition:** Create a detectable resource (e.g. a CloudTrail trail or a VPC) ONLY in eu-west-1.
- **Expected:** The relevant check reflects it (e.g. "CloudTrail trail exists" = complete;
  "No VPCs in account" = incomplete). Confirms the multi-region fan-out actually works and isn't us-east-1-only.

### D4. Opt-in region enabled in the account
- **Precondition:** Enable an opt-in region; place a resource there.
- **Expected:** Document whether WAFA scans it (by design it scans only opt-in-not-required regions,
  so an opt-in region's resources may be missed — verify and note as expected behavior vs. gap).

### D5. GovCloud partition (if available)
- **Expected:** Partition detected as `aws-us-gov`; default region us-gov-west-1; CUR "Data Exports"
  (bcm-data-exports) path skipped; assessment completes.

### D6. China partition (if available)
- **Expected:** Partition `aws-cn`; default region cn-north-1; Data Exports path skipped.

---

## Group E — Individual checks (spot-verification)

Owner: ____

For each, set up the "good" and "bad" state and confirm status flips correctly.

### E1. CloudTrail org trail (FR-7.2)
- Org trail present → complete; absent → incomplete.

### E2. AWS Config recorder active (FR-7.3)
- Recorder recording in ≥1 region → complete; none recording → incomplete.

### E3. Config delivery channel (FR-7.4)
- Delivery channel `lastStatus == Success` → complete.

### E4. No EC2 instances / No VPCs (FR-7.5 / 7.6, "absence" checks)
- Zero instances/VPCs across all regions → complete; any present → incomplete.
- **Edge:** confirm the default VPC counts as "present" (it usually does).

### E5. Cost and Usage Report (FR-7.7, management only)
- Legacy CUR present → complete; none but a CUR 2.0 Data Export present → complete;
  neither → incomplete; API error with no report → error (not false incomplete).

### E6. Org service integrations (FR-4)
- Enable/disable a service (e.g. GuardDuty) at the org level and confirm the matching
  check flips. Confirm all 10 come from a single API call (one failure marks all 10 error).

### E7. Policy types (SCP / Tag / Backup / RCP, FR-3.6–3.9)
- Enable a policy type on the root and confirm the check flips to complete.

### E8. OUs (Security / Workloads / Infrastructure, FR-3.10–3.12)
- Create an OU named "Security" → check complete (case-insensitive match).

### E9. Control Tower (FR-5)
- With a landing zone: deployed = complete; introduce drift → "not drifted" = incomplete;
  behind latest version → "latest version" = incomplete. No landing zone → checks incomplete (not error).

### E10. IAM Identity Center (FR-6.1) permission vs. absence
- SSO configured → complete; not configured anywhere → incomplete;
  `sso:ListInstances` denied → **error** (not incomplete) — confirm the distinction.

### E11. No IAM users (FR-6.2)
- Zero IAM users → complete; ≥1 user → incomplete.

---

## Group F — Maturity scoring

Owner: ____

### F1. Level 1 (baseline)
- Member/standalone or org missing core checks → level 1; `next_level_progress` and
  `next_level_checks_needed` populated.

### F2. Level advancement gating
- Satisfy all Level 2 checks + any one OU → level 2. Confirm you cannot reach level 3
  until ALL level-3 checks complete (gated ladder, not a percentage).

### F3. next_level_checks_needed ordering
- Confirm the "what to fix next" list is sorted by weight descending (highest impact first).

### F4. Level 5 requires everything
- Confirm level 5 only when StackSets org access enabled AND every check is complete.

---

## Group G — Report output & rendering

Owner: ____

### G1. Radar chart renders (regression guard)
- Open wafa-report.html in a browser. **Expected:** the capability radar chart displays
  (7 axes, orange polygon) — NOT a broken-image icon.
- **Why:** guards the `xmlns` SVG fix.

### G2. Report opens offline
- Disconnect network, open the HTML. **Expected:** fully renders (no CDN dependency;
  chart is an embedded SVG data URI).

### G3. Light/dark theme toggle
- Toggle works; both themes readable.

### G4. Check table filters
- Filter buttons (complete/incomplete/error) filter rows correctly.

### G5. CSV export integrity
- Open wafa-checks.csv. **Expected:** header row + one row per check; 8 columns; error
  column populated only for error checks.

### G6. Raw JSON schema
- wafa-raw.json contains `account_info`, `maturity`, `checks[]`, `delegated_administrators[]`.
  Every check has: check, description, status, required, weight, loe, remediationLink (+ error if error).

### G7. Special characters don't break the report
- If any account/OU name contains `<`, `>`, `&`, or quotes, confirm the HTML escapes it
  (no broken layout / no injected markup). Validates the sandboxed autoescaping.

### G8. Delegated admins table (management only)
- With ≥1 delegated administrator, confirm the table lists account + services;
  with none, confirm the section handles empty gracefully.

---

## Group H — Resilience & error handling

Owner: ____

### H1. Single check failure doesn't abort the run
- Deny one API (e.g. `config:DescribeConfigurationRecorders`). **Expected:** that check =
  error with a message; all other checks still run; reports still generated.

### H2. Partial permissions
- Run with a role missing several assessment permissions. **Expected:** graceful degradation —
  affected checks = error, assessment completes, error count shown in summary.

### H3. CodeBuild timeout boundary
- Very large org / many regions. **Expected:** completes within the 10-min CodeBuild timeout,
  or document how close it gets (perf signal for tuning max_workers).

### H4. Idempotent re-run
- Run twice back to back. **Expected:** second run overwrites reports; no residue/errors from first.

---

## Priority for a first testing pass

If testers are limited, cover these first (highest signal):
1. A1, A2, **A3** (the suspected remaining region bug)
2. C1, C2, C3 (account modes)
3. G1, G2 (report + radar regression guards)
4. D3 (multi-region resource detection)
5. H1 (resilience)
