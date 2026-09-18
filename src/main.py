"""WAFA — Well-Architected Foundations Assessment — Main Orchestrator.

Entry point that works in both CloudShell and CodeBuild modes.
Calls discovery, then runs checks based on account type, generates reports.
"""

import argparse
import json
import os

import boto3

from src.discovery.account_type import detect_account_type, detect_partition
from src.discovery.regions import get_enabled_regions
from src.checks import (
    organization,
    org_services,
    control_tower,
    identity,
    account_resources,
)
from src.checks.delegated_admin import get_delegated_administrators
from src.checks.maturity import calculate_maturity_level
from src.report.html_report import generate_html
from src.report.csv_export import generate_csv


def parse_args():
    parser = argparse.ArgumentParser(
        description="Well-Architected Foundations Assessment (WAFA)"
    )
    parser.add_argument(
        "--output",
        default=".",
        help="Output directory or S3 URI (s3://bucket/prefix/) for reports",
    )
    return parser.parse_args()


def print_summary(checks, maturity):
    """Print console summary table (FR-10.1)."""
    total = len(checks)
    complete = sum(1 for c in checks if c["status"] == "complete")
    incomplete = sum(1 for c in checks if c["status"] == "incomplete")
    errors = sum(1 for c in checks if c["status"] == "error")
    pct = (complete / total * 100) if total > 0 else 0

    print("\n" + "=" * 80)
    print("WAFA ASSESSMENT RESULTS")
    print("=" * 80)
    print(f"\nMaturity Level: {maturity['level']} — {maturity['name']}")
    print(f"  {maturity['description']}")
    if maturity["next_level"]:
        print(
            f"\n  Progress toward Level {maturity['next_level']}: {maturity['next_level_progress']:.0f}%"
        )
        if maturity["next_level_checks_needed"]:
            print("  Next steps (highest impact first):")
            for name in maturity["next_level_checks_needed"][:5]:
                print(f"    • {name}")

    print(
        f"\nTotal Checks: {total} | Complete: {complete} | Incomplete: {incomplete} | Errors: {errors}"
    )
    print(f"Completion: {pct:.0f}%\n")

    # Table header
    print(f"{'Check':<50} {'Status':<12} {'Required':<10} {'LoE':<5}")
    print("-" * 80)
    for c in checks:
        name = c["check"][:48]
        status = c["status"]
        required = "Yes" if c.get("required") else "No"
        loe = str(c.get("loe", ""))
        print(f"{name:<50} {status:<12} {required:<10} {loe:<5}")

    print("-" * 80)


def upload_to_s3(output_path, account_id, files):
    """Upload report files to S3 if output is an S3 URI."""
    # Parse S3 URI
    bucket = output_path.replace("s3://", "").split("/")[0]
    prefix = "/".join(output_path.replace("s3://", "").split("/")[1:])
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    prefix += f"{account_id}/"

    s3 = boto3.client("s3")
    for filename, content, content_type in files:
        key = f"{prefix}{filename}"
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        print(f"  Uploaded: s3://{bucket}/{key}")


def _configure_aws_retries():
    """Use botocore standard retries for throttling and transient failures."""
    os.environ.setdefault("AWS_RETRY_MODE", "standard")
    os.environ.setdefault("AWS_MAX_ATTEMPTS", "5")


def run():
    """Main assessment orchestration."""
    _configure_aws_retries()
    args = parse_args()

    print("WAFA Assessment starting...")
    print("-" * 40)

    # 1. Discover account type and partition
    partition_info = detect_partition()
    print(f"Partition: {partition_info['partition']}")

    account_info = detect_account_type()
    print(f"Account: {account_info['account_id']} ({account_info['account_type']})")

    # 2. Discover regions
    regions = get_enabled_regions(partition_info["default_region"])
    print(f"Regions discovered: {len(regions)}")
    print("-" * 40)

    # 3. Run checks based on account type
    checks = []
    delegated_admins = []

    # FR-3.1, FR-3.2: Always run
    checks.append(organization.check_org_exists())
    checks.append(organization.check_management_account(account_info))

    if account_info["is_management_account"]:
        print("Running FULL assessment (management account)...")

        # FR-3.3 through FR-3.12: Organization governance
        checks.extend(organization.run_all())

        # FR-4: Organization service integrations
        checks.extend(org_services.run_all())

        # FR-5: Control Tower
        checks.extend(control_tower.run_all())

        # FR-6: Identity (management account runs both checks)
        checks.extend(identity.run_all(regions, is_management_account=True))

        # FR-7 + FR-8: Per-account resources (all + management-only)
        checks.extend(
            account_resources.run_all(
                regions,
                is_management_account=True,
                default_region=partition_info["default_region"],
            )
        )

        # FR-9: Delegated administrators (informational)
        delegated_admins = get_delegated_administrators()

    else:
        print("Running LIMITED assessment (non-management account)...")
        # FR-2.4: Limited checks for non-management accounts
        checks.extend(identity.run_all(regions, is_management_account=False))
        checks.extend(
            account_resources.run_all(
                regions,
                is_management_account=False,
                default_region=partition_info["default_region"],
            )
        )

    # 4. Calculate maturity level
    maturity = calculate_maturity_level(checks)

    # 5. Print console summary
    print_summary(checks, maturity)

    # 6. Generate reports
    html_content = generate_html(checks, maturity, delegated_admins, account_info)
    csv_content = generate_csv(checks)
    raw_json = json.dumps(
        {
            "account_info": account_info,
            "maturity": maturity,
            "checks": checks,
            "delegated_administrators": delegated_admins,
        },
        indent=2,
        default=str,
    )

    # 7. Output reports
    if args.output.startswith("s3://"):
        print("\nUploading reports to S3...")
        upload_to_s3(
            args.output,
            account_info["account_id"],
            [
                ("wafa-report.html", html_content, "text/html"),
                ("wafa-checks.csv", csv_content, "text/csv"),
                ("wafa-raw.json", raw_json, "application/json"),
            ],
        )
    else:
        output_dir = args.output
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "wafa-report.html"), "w") as f:
            f.write(html_content)
        with open(os.path.join(output_dir, "wafa-checks.csv"), "w") as f:
            f.write(csv_content)
        with open(os.path.join(output_dir, "wafa-raw.json"), "w") as f:
            f.write(raw_json)
        print(f"\nReports saved to: {output_dir}/")

    print("\nWAFA Assessment complete.")
    return checks, maturity


if __name__ == "__main__":
    run()
