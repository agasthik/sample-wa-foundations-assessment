#!/usr/bin/env python3
"""Generate the sanitized sample WAFA report committed under sample-reports/.

This script produces the example reports that let people preview WAFA's output
without running it against a real account (GitHub issue #2).

How it stays faithful (no hand-written report content):
- It calls the *real* orchestrator, ``src.main.run()``. Every check definition,
  the maturity scoring, and the HTML/CSV/JSON rendering come from production
  code in ``src/`` — this script never authors report content itself.
- The only thing it supplies is a mocked set of AWS API responses (patched at
  the ``boto3.client`` seam, exactly like the unit tests do). The mock models a
  *management* account with a realistic, mixed posture — most foundations in
  place, a few gaps, and one permission error — so the sample exercises the full
  report: complete/incomplete/error states, the "next steps" list, and a partial
  capability radar (rather than an unrealistic all-green Level 5).
- All identifiers are obvious, non-real placeholders (AWS documentation-style
  account IDs and example names), so the committed sample contains no real data.

Regenerate with:  python -m scripts.generate_sample_report
Output:           sample-reports/{wafa-report.html,wafa-checks.csv,wafa-raw.json}
"""

import os
import sys
from unittest.mock import MagicMock, patch

# Placeholder identifiers — deliberately fake (AWS "documentation" account IDs).
MGMT_ACCOUNT_ID = "111111111111"
LOG_ARCHIVE_ID = "222222222222"
AUDIT_ID = "333333333333"
WORKLOAD_ID = "444444444444"
ORG_ID = "o-example12345"


def _sample_management_account_client_factory():
    """boto3.client factory modelling a well-configured management account.

    Mirrors tests/unit/test_main.py::_mock_management_account_boto3 (the vetted,
    passing fixture) so the sample is structurally identical to a real run.
    """

    def client_factory(service, **kwargs):
        mock = MagicMock()

        if service == "sts":
            mock.get_caller_identity.return_value = {"Account": MGMT_ACCOUNT_ID}

        elif service == "organizations":
            mock.describe_organization.return_value = {
                "Organization": {"Id": ORG_ID, "MasterAccountId": MGMT_ACCOUNT_ID}
            }
            accounts_paginator = MagicMock()
            accounts_paginator.paginate.return_value = [
                {
                    "Accounts": [
                        {"Id": MGMT_ACCOUNT_ID, "Name": "Management"},
                        {"Id": LOG_ARCHIVE_ID, "Name": "Log Archive"},
                        {"Id": AUDIT_ID, "Name": "Audit"},
                        {"Id": WORKLOAD_ID, "Name": "Workload-Prod"},
                    ]
                }
            ]
            svc_paginator = MagicMock()
            # Realistic gap: Security Hub is NOT enabled at the org level, so the
            # "Security Hub organization service enabled" check reports incomplete.
            svc_paginator.paginate.return_value = [
                {
                    "EnabledServicePrincipals": [
                        {"ServicePrincipal": "cloudtrail.amazonaws.com"},
                        {"ServicePrincipal": "config.amazonaws.com"},
                        {"ServicePrincipal": "guardduty.amazonaws.com"},
                        {"ServicePrincipal": "access-analyzer.amazonaws.com"},
                        {"ServicePrincipal": "ram.amazonaws.com"},
                        {"ServicePrincipal": "sso.amazonaws.com"},
                        {
                            "ServicePrincipal": "member.org.stacksets.cloudformation.amazonaws.com"
                        },
                        {"ServicePrincipal": "backup.amazonaws.com"},
                        {"ServicePrincipal": "cost-optimization-hub.bcm.amazonaws.com"},
                    ]
                }
            ]
            ou_paginator = MagicMock()
            # Realistic gap: no Infrastructure OU yet → that check reports incomplete.
            ou_paginator.paginate.return_value = [
                {
                    "OrganizationalUnits": [
                        {"Id": "ou-sec", "Name": "Security"},
                        {"Id": "ou-wl", "Name": "Workloads"},
                    ]
                }
            ]
            da_paginator = MagicMock()
            da_paginator.paginate.return_value = [
                {"DelegatedAdministrators": [{"Id": AUDIT_ID, "Name": "Audit"}]}
            ]
            ds_paginator = MagicMock()
            ds_paginator.paginate.return_value = [
                {"DelegatedServices": [{"ServicePrincipal": "guardduty.amazonaws.com"}]}
            ]

            def get_paginator(name):
                return {
                    "list_accounts": accounts_paginator,
                    "list_aws_service_access_for_organization": svc_paginator,
                    "list_organizational_units_for_parent": ou_paginator,
                    "list_delegated_administrators": da_paginator,
                    "list_delegated_services_for_account": ds_paginator,
                }.get(name, MagicMock())

            mock.get_paginator.side_effect = get_paginator
            # Realistic gap: RCPs not yet enabled → "Resource Control Policies
            # enabled" reports incomplete.
            mock.list_roots.return_value = {
                "Roots": [
                    {
                        "Id": "r-root",
                        "PolicyTypes": [
                            {"Type": "SERVICE_CONTROL_POLICY", "Status": "ENABLED"},
                            {"Type": "TAG_POLICY", "Status": "ENABLED"},
                            {"Type": "BACKUP_POLICY", "Status": "ENABLED"},
                        ],
                    }
                ]
            }

        elif service == "controltower":
            mock.list_landing_zones.return_value = {
                "landingZones": [
                    {"arn": "arn:aws:controltower:us-east-1:111111111111:landingzone/lz1"}
                ]
            }
            mock.get_landing_zone.return_value = {
                "landingZone": {
                    "driftStatus": {"status": "IN_SYNC"},
                    "version": "3.3",
                    "latestAvailableVersion": "3.3",
                }
            }

        elif service == "sso-admin":
            mock.list_instances.return_value = {
                "Instances": [{"InstanceArn": "arn:aws:sso:::instance/ssoins-example"}]
            }

        elif service == "iam":
            mock.list_users.return_value = {"Users": []}

        elif service == "ec2":
            mock.describe_regions.return_value = {
                "Regions": [
                    {"RegionName": "us-east-1"},
                    {"RegionName": "us-west-2"},
                ]
            }
            mock.describe_instances.return_value = {"Reservations": []}
            mock.describe_vpcs.return_value = {"Vpcs": []}

        elif service == "cloudtrail":
            mock.describe_trails.return_value = {
                "trailList": [
                    {
                        "Name": "org-trail",
                        "IsOrganizationTrail": True,
                        "HomeRegion": "us-east-1",
                    }
                ]
            }

        elif service == "config":
            # Realistic error: the assessment role is denied the Config recorder
            # API, so "AWS Config recorder active" reports an *error* (not a false
            # incomplete) — showing how permission gaps surface in the report.
            from botocore.exceptions import ClientError

            denied = ClientError(
                {
                    "Error": {
                        "Code": "AccessDeniedException",
                        "Message": "User is not authorized to perform: "
                        "config:DescribeConfigurationRecorders",
                    }
                },
                "DescribeConfigurationRecorders",
            )
            mock.describe_configuration_recorders.side_effect = denied
            # Delivery channel is readable and healthy → that check stays complete.
            mock.describe_delivery_channels.return_value = {
                "DeliveryChannels": [{"name": "default"}]
            }
            mock.describe_delivery_channel_status.return_value = {
                "DeliveryChannelsStatus": [
                    {
                        "name": "default",
                        "configHistoryDeliveryInfo": {"lastStatus": "SUCCESS"},
                    }
                ]
            }

        elif service == "cur":
            # Realistic gap: no Cost and Usage Report configured → incomplete.
            mock.describe_report_definitions.return_value = {"ReportDefinitions": []}

        elif service == "bcm-data-exports":
            mock.list_exports.return_value = {"Exports": []}

        elif service == "cloudformation":
            mock.describe_organizations_access.return_value = {"Status": "ENABLED"}

        elif service == "s3":
            mock.put_object.return_value = {}

        return mock

    return client_factory


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(repo_root, "sample-reports")
    os.makedirs(out_dir, exist_ok=True)

    factory = _sample_management_account_client_factory()

    # Patch every boto3.client seam the assessment uses, set argv to write into
    # sample-reports/, then run the real orchestrator.
    seams = [
        "src.discovery.account_type.boto3.client",
        "src.discovery.regions.boto3.client",
        "src.checks.organization.boto3.client",
        "src.checks.org_services.boto3.client",
        "src.checks.control_tower.boto3.client",
        "src.checks.identity.boto3.client",
        "src.checks.account_resources.boto3.client",
        "src.checks.delegated_admin.boto3.client",
    ]

    from contextlib import ExitStack

    with ExitStack() as stack:
        for seam in seams:
            m = stack.enter_context(patch(seam))
            m.side_effect = factory
        old_argv = sys.argv
        sys.argv = ["generate_sample_report", "--output", out_dir]
        try:
            from src.main import run

            run()
        finally:
            sys.argv = old_argv

    print(f"\nSample reports written to: {out_dir}")


if __name__ == "__main__":
    main()
