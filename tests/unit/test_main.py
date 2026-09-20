"""Integration-style unit tests for src/main.py — orchestrator end-to-end.

Mocks all boto3 calls to simulate a full assessment run without real AWS credentials.
Tests both management account (full) and non-management account (limited) flows.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock


from src.main import run, print_summary, upload_to_s3


def test_deployment_names_use_wa_foundations_prefix():
    """Future deployments consistently use the WA Foundations resource prefix."""
    repository_root = Path(__file__).resolve().parents[2]
    template = (repository_root / "deployment" / "wafa-stack.yaml").read_text()
    deploy_script = (repository_root / "deploy.sh").read_text()

    assert "Name: !Ref 'AWS::StackName'" in template
    assert "/aws/codebuild/WAFA-${AWS::StackName}" not in template
    assert "'wa-foundations-results-'" in template
    assert "Default: 'wa-foundations-source.zip'" in template
    assert "Value: WA-Foundations-Assessment" in template
    assert (
        "Deploys the Well-Architected Foundations Assessment for AWS Organizations"
        in template
    )
    assert "automated AWS CodeBuild execution" in template
    assert "scoped IAM permissions" in template
    assert "versioned Amazon S3 report storage" in template
    assert 'STACK_NAME="wa-foundations-assessment"' in deploy_script
    assert 'SOURCE_BUCKET="wa-foundations-source-${ACCOUNT_ID}-${REGION}"' in (
        deploy_script
    )
    assert 'SOURCE_KEY="wa-foundations-source.zip"' in deploy_script
    assert (
        "Description: Name of the S3 bucket containing generated assessment reports"
        in template
    )
    assert (
        "Description: Name of the CodeBuild project used to run or re-run the assessment"
        in template
    )
    assert 'PROJECT_NAME="$STACK_NAME"' in deploy_script
    assert 'STACK_NAME="wafa"' not in deploy_script
    assert 'PROJECT_NAME="WAFA-${STACK_NAME}"' not in deploy_script


# ============================================================================
# Shared mock fixtures
# ============================================================================


def _mock_management_account_boto3():
    """Build a mock boto3.client that simulates a well-configured management account."""

    def client_factory(service, **kwargs):
        mock = MagicMock()

        if service == "sts":
            mock.get_caller_identity.return_value = {"Account": "111111111111"}

        elif service == "organizations":
            mock.describe_organization.return_value = {
                "Organization": {"Id": "o-abc123", "MasterAccountId": "111111111111"}
            }
            # list_accounts paginator
            accounts_paginator = MagicMock()
            accounts_paginator.paginate.return_value = [
                {
                    "Accounts": [
                        {"Id": "111111111111", "Name": "Management"},
                        {"Id": "222222222222", "Name": "Log Archive"},
                        {"Id": "333333333333", "Name": "Audit"},
                        {"Id": "444444444444", "Name": "Workload-Prod"},
                    ]
                }
            ]
            # list_aws_service_access paginator
            svc_paginator = MagicMock()
            svc_paginator.paginate.return_value = [
                {
                    "EnabledServicePrincipals": [
                        {"ServicePrincipal": "cloudtrail.amazonaws.com"},
                        {"ServicePrincipal": "config.amazonaws.com"},
                        {"ServicePrincipal": "guardduty.amazonaws.com"},
                        {"ServicePrincipal": "securityhub.amazonaws.com"},
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
            # list_organizational_units paginator
            ou_paginator = MagicMock()
            ou_paginator.paginate.return_value = [
                {
                    "OrganizationalUnits": [
                        {"Id": "ou-sec", "Name": "Security"},
                        {"Id": "ou-wl", "Name": "Workloads"},
                        {"Id": "ou-infra", "Name": "Infrastructure"},
                    ]
                }
            ]
            # delegated admins paginator
            da_paginator = MagicMock()
            da_paginator.paginate.return_value = [
                {
                    "DelegatedAdministrators": [
                        {"Id": "333333333333", "Name": "Audit"},
                    ]
                }
            ]
            # delegated services paginator
            ds_paginator = MagicMock()
            ds_paginator.paginate.return_value = [
                {
                    "DelegatedServices": [
                        {"ServicePrincipal": "guardduty.amazonaws.com"},
                    ]
                }
            ]

            def get_paginator(name):
                if name == "list_accounts":
                    return accounts_paginator
                elif name == "list_aws_service_access_for_organization":
                    return svc_paginator
                elif name == "list_organizational_units_for_parent":
                    return ou_paginator
                elif name == "list_delegated_administrators":
                    return da_paginator
                elif name == "list_delegated_services_for_account":
                    return ds_paginator
                return MagicMock()

            mock.get_paginator.side_effect = get_paginator
            mock.list_roots.return_value = {
                "Roots": [
                    {
                        "Id": "r-root",
                        "PolicyTypes": [
                            {"Type": "SERVICE_CONTROL_POLICY", "Status": "ENABLED"},
                            {"Type": "TAG_POLICY", "Status": "ENABLED"},
                            {"Type": "BACKUP_POLICY", "Status": "ENABLED"},
                            {"Type": "RESOURCE_CONTROL_POLICY", "Status": "ENABLED"},
                        ],
                    }
                ]
            }

        elif service == "controltower":
            mock.list_landing_zones.return_value = {
                "landingZones": [
                    {"arn": "arn:aws:controltower:us-east-1:111:landingzone/lz1"}
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
                "Instances": [{"InstanceArn": "arn:aws:sso:::instance/ssoins-123"}]
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
            mock.describe_configuration_recorders.return_value = {
                "ConfigurationRecorders": [{"name": "default"}]
            }
            mock.describe_configuration_recorder_status.return_value = {
                "ConfigurationRecordersStatus": [{"name": "default", "recording": True}]
            }
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
            mock.describe_report_definitions.return_value = {
                "ReportDefinitions": [{"ReportName": "wafa-cur"}]
            }

        elif service == "cloudformation":
            mock.describe_organizations_access.return_value = {"Status": "ENABLED"}

        elif service == "s3":
            mock.put_object.return_value = {}

        return mock

    return client_factory


def _mock_member_account_boto3():
    """Build a mock boto3.client that simulates a member account."""

    def client_factory(service, **kwargs):
        mock = MagicMock()

        if service == "sts":
            mock.get_caller_identity.return_value = {"Account": "222222222222"}

        elif service == "organizations":
            mock.describe_organization.return_value = {
                "Organization": {"Id": "o-abc123", "MasterAccountId": "111111111111"}
            }

        elif service == "ec2":
            mock.describe_regions.return_value = {
                "Regions": [{"RegionName": "us-east-1"}]
            }
            mock.describe_instances.return_value = {"Reservations": []}
            mock.describe_vpcs.return_value = {
                "Vpcs": [{"VpcId": "vpc-default", "IsDefault": True}]
            }

        elif service == "iam":
            mock.list_users.return_value = {"Users": [{"UserName": "legacy-user"}]}

        elif service == "cloudtrail":
            mock.describe_trails.return_value = {
                "trailList": [{"Name": "trail", "IsOrganizationTrail": False}]
            }

        elif service == "config":
            mock.describe_configuration_recorders.return_value = {
                "ConfigurationRecorders": [{"name": "default"}]
            }
            mock.describe_configuration_recorder_status.return_value = {
                "ConfigurationRecordersStatus": [{"name": "default", "recording": True}]
            }
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

        return mock

    return client_factory


def _mock_standalone_account_boto3():
    """Build a mock boto3.client that simulates a standalone account (no org)."""
    from botocore.exceptions import ClientError

    def client_factory(service, **kwargs):
        mock = MagicMock()

        if service == "sts":
            mock.get_caller_identity.return_value = {"Account": "333333333333"}

        elif service == "organizations":
            mock.describe_organization.side_effect = ClientError(
                {
                    "Error": {
                        "Code": "AWSOrganizationsNotInUseException",
                        "Message": "Not in org",
                    }
                },
                "DescribeOrganization",
            )

        elif service == "ec2":
            mock.describe_regions.return_value = {
                "Regions": [{"RegionName": "us-east-1"}]
            }
            mock.describe_instances.return_value = {"Reservations": []}
            mock.describe_vpcs.return_value = {
                "Vpcs": [{"VpcId": "vpc-default", "IsDefault": True}]
            }

        elif service == "iam":
            mock.list_users.return_value = {"Users": [{"UserName": "legacy-user"}]}

        elif service == "cloudtrail":
            mock.describe_trails.return_value = {
                "trailList": [{"Name": "trail", "IsOrganizationTrail": False}]
            }

        elif service == "config":
            mock.describe_configuration_recorders.return_value = {
                "ConfigurationRecorders": [{"name": "default"}]
            }
            mock.describe_configuration_recorder_status.return_value = {
                "ConfigurationRecordersStatus": [{"name": "default", "recording": True}]
            }
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

        return mock

    return client_factory


# ============================================================================
# Management account — full assessment
# ============================================================================


class TestRunManagementAccount:
    """End-to-end test: management account runs all checks."""

    @patch("src.main.parse_args")
    @patch("src.checks.account_resources.boto3.client")
    @patch("src.checks.identity.boto3.client")
    @patch("src.checks.control_tower.boto3.client")
    @patch("src.checks.org_services.boto3.client")
    @patch("src.checks.organization.boto3.client")
    @patch("src.checks.delegated_admin.boto3.client")
    @patch("src.discovery.regions.boto3.client")
    @patch("src.discovery.account_type.boto3.client")
    def test_full_assessment_produces_reports(
        self,
        mock_acct_client,
        mock_regions_client,
        mock_da_client,
        mock_org_client,
        mock_svc_client,
        mock_ct_client,
        mock_id_client,
        mock_res_client,
        mock_parse_args,
        tmp_path,
    ):
        """Full run: management account → all checks → reports written to disk."""
        output_dir = str(tmp_path)
        mock_parse_args.return_value = MagicMock(output=output_dir)

        factory = _mock_management_account_boto3()
        mock_acct_client.side_effect = factory
        mock_regions_client.side_effect = factory
        mock_da_client.side_effect = factory
        mock_org_client.side_effect = factory
        mock_svc_client.side_effect = factory
        mock_ct_client.side_effect = factory
        mock_id_client.side_effect = factory
        mock_res_client.side_effect = factory

        checks, maturity = run()

        # Verify checks were produced
        assert len(checks) > 30  # Full assessment has 35 checks
        assert all("check" in c for c in checks)
        assert all("status" in c for c in checks)
        assert all(c["status"] in ("complete", "incomplete", "error") for c in checks)

        # Verify maturity was calculated
        assert maturity["level"] in (1, 2, 3, 4, 5)
        assert "name" in maturity

        # Verify reports were written
        assert os.path.exists(os.path.join(output_dir, "wafa-report.html"))
        assert os.path.exists(os.path.join(output_dir, "wafa-checks.csv"))
        assert os.path.exists(os.path.join(output_dir, "wafa-raw.json"))

        # Verify HTML content
        with open(os.path.join(output_dir, "wafa-report.html")) as f:
            html = f.read()
        assert "radarChart" in html
        assert "Assessment Overview" in html
        assert "Maturity Progress" in html
        assert "AWS Organization exists" in html

        # Verify CSV content
        with open(os.path.join(output_dir, "wafa-checks.csv")) as f:
            csv_content = f.read()
        assert "Check Name" in csv_content
        assert "complete" in csv_content

        # Verify JSON content
        with open(os.path.join(output_dir, "wafa-raw.json")) as f:
            raw = json.load(f)
        assert "checks" in raw
        assert "maturity" in raw
        assert "account_info" in raw
        assert raw["account_info"]["account_id"] == "111111111111"

    @patch("src.main.parse_args")
    @patch("src.checks.account_resources.boto3.client")
    @patch("src.checks.identity.boto3.client")
    @patch("src.checks.control_tower.boto3.client")
    @patch("src.checks.org_services.boto3.client")
    @patch("src.checks.organization.boto3.client")
    @patch("src.checks.delegated_admin.boto3.client")
    @patch("src.discovery.regions.boto3.client")
    @patch("src.discovery.account_type.boto3.client")
    def test_all_checks_have_valid_schema(
        self,
        mock_acct_client,
        mock_regions_client,
        mock_da_client,
        mock_org_client,
        mock_svc_client,
        mock_ct_client,
        mock_id_client,
        mock_res_client,
        mock_parse_args,
        tmp_path,
    ):
        """Every check result follows the Check Metadata Schema exactly."""
        mock_parse_args.return_value = MagicMock(output=str(tmp_path))

        factory = _mock_management_account_boto3()
        mock_acct_client.side_effect = factory
        mock_regions_client.side_effect = factory
        mock_da_client.side_effect = factory
        mock_org_client.side_effect = factory
        mock_svc_client.side_effect = factory
        mock_ct_client.side_effect = factory
        mock_id_client.side_effect = factory
        mock_res_client.side_effect = factory

        checks, _ = run()

        for c in checks:
            assert isinstance(c.get("check"), str), f"Missing 'check' string: {c}"
            assert isinstance(c.get("description"), str), f"Missing 'description': {c}"
            assert c.get("status") in ("complete", "incomplete", "error"), (
                f"Bad status: {c}"
            )
            assert isinstance(c.get("required"), bool), f"Missing 'required' bool: {c}"
            assert isinstance(c.get("weight"), int), f"Missing 'weight' int: {c}"
            assert isinstance(c.get("loe"), int), f"Missing 'loe' int: {c}"
            assert isinstance(c.get("remediationLink"), str), (
                f"Missing 'remediationLink': {c}"
            )
            assert c["remediationLink"].startswith("https://"), (
                f"Bad remediation URL: {c}"
            )
            if c["status"] == "error":
                assert "error" in c, f"Error status without 'error' field: {c}"

    @patch("src.main.parse_args")
    @patch("src.checks.account_resources.boto3.client")
    @patch("src.checks.identity.boto3.client")
    @patch("src.checks.control_tower.boto3.client")
    @patch("src.checks.org_services.boto3.client")
    @patch("src.checks.organization.boto3.client")
    @patch("src.checks.delegated_admin.boto3.client")
    @patch("src.discovery.regions.boto3.client")
    @patch("src.discovery.account_type.boto3.client")
    def test_high_maturity_when_all_passing(
        self,
        mock_acct_client,
        mock_regions_client,
        mock_da_client,
        mock_org_client,
        mock_svc_client,
        mock_ct_client,
        mock_id_client,
        mock_res_client,
        mock_parse_args,
        tmp_path,
    ):
        """When all checks pass, maturity should be Level 4 or 5."""
        mock_parse_args.return_value = MagicMock(output=str(tmp_path))

        factory = _mock_management_account_boto3()
        mock_acct_client.side_effect = factory
        mock_regions_client.side_effect = factory
        mock_da_client.side_effect = factory
        mock_org_client.side_effect = factory
        mock_svc_client.side_effect = factory
        mock_ct_client.side_effect = factory
        mock_id_client.side_effect = factory
        mock_res_client.side_effect = factory

        checks, maturity = run()

        # All our mocks return "passing" data, so maturity should be high
        assert maturity["level"] >= 4
        complete_count = sum(1 for c in checks if c["status"] == "complete")
        assert complete_count >= 30


# ============================================================================
# Member account — limited assessment
# ============================================================================


class TestRunMemberAccount:
    """End-to-end test: member account runs limited checks."""

    @patch("src.main.parse_args")
    @patch("src.checks.account_resources.boto3.client")
    @patch("src.checks.identity.boto3.client")
    @patch("src.discovery.regions.boto3.client")
    @patch("src.discovery.account_type.boto3.client")
    def test_limited_assessment(
        self,
        mock_acct_client,
        mock_regions_client,
        mock_id_client,
        mock_res_client,
        mock_parse_args,
        tmp_path,
    ):
        """Member account: only per-account checks run."""
        output_dir = str(tmp_path)
        mock_parse_args.return_value = MagicMock(output=output_dir)

        factory = _mock_member_account_boto3()
        mock_acct_client.side_effect = factory
        mock_regions_client.side_effect = factory
        mock_id_client.side_effect = factory
        mock_res_client.side_effect = factory

        checks, maturity = run()

        # Limited: FR-3.1, FR-3.2, FR-6.2, FR-7.1-7.6 = 9 checks
        assert len(checks) == 9

        # FR-3.1 should be complete (org exists)
        org_check = next(c for c in checks if c["check"] == "AWS Organization exists")
        assert org_check["status"] == "complete"

        # FR-3.2 should be incomplete (not management)
        mgmt_check = next(
            c for c in checks if c["check"] == "Management account identified"
        )
        assert mgmt_check["status"] == "incomplete"

        # FR-6.2: IAM users exist → incomplete
        iam_check = next(c for c in checks if c["check"] == "No IAM users in account")
        assert iam_check["status"] == "incomplete"

        # FR-7.6: VPCs exist → incomplete
        vpc_check = next(c for c in checks if c["check"] == "No VPCs in account")
        assert vpc_check["status"] == "incomplete"

        # Reports still generated
        assert os.path.exists(os.path.join(output_dir, "wafa-report.html"))
        assert os.path.exists(os.path.join(output_dir, "wafa-raw.json"))

    @patch("src.main.parse_args")
    @patch("src.checks.account_resources.boto3.client")
    @patch("src.checks.identity.boto3.client")
    @patch("src.discovery.regions.boto3.client")
    @patch("src.discovery.account_type.boto3.client")
    def test_member_maturity_is_low(
        self,
        mock_acct_client,
        mock_regions_client,
        mock_id_client,
        mock_res_client,
        mock_parse_args,
        tmp_path,
    ):
        """Member account can't reach high maturity (missing management-only checks)."""
        mock_parse_args.return_value = MagicMock(output=str(tmp_path))

        factory = _mock_member_account_boto3()
        mock_acct_client.side_effect = factory
        mock_regions_client.side_effect = factory
        mock_id_client.side_effect = factory
        mock_res_client.side_effect = factory

        _, maturity = run()

        # Without management account checks, can't exceed Level 1
        assert maturity["level"] == 1


# ============================================================================
# Standalone account — limited assessment
# ============================================================================


class TestRunStandaloneAccount:
    """End-to-end test: standalone account (not in an org) runs limited checks."""

    @patch("src.main.parse_args")
    @patch("src.checks.account_resources.boto3.client")
    @patch("src.checks.identity.boto3.client")
    @patch("src.discovery.regions.boto3.client")
    @patch("src.discovery.account_type.boto3.client")
    def test_limited_assessment(
        self,
        mock_acct_client,
        mock_regions_client,
        mock_id_client,
        mock_res_client,
        mock_parse_args,
        tmp_path,
    ):
        """Standalone account: same limited check set as a member account (C3)."""
        output_dir = str(tmp_path)
        mock_parse_args.return_value = MagicMock(output=output_dir)

        factory = _mock_standalone_account_boto3()
        mock_acct_client.side_effect = factory
        mock_regions_client.side_effect = factory
        mock_id_client.side_effect = factory
        mock_res_client.side_effect = factory

        checks, maturity = run()

        # Limited: FR-3.1, FR-3.2, FR-6.2, FR-7.1-7.6 = 9 checks
        assert len(checks) == 9
        assert maturity["level"] == 1

        # Not in an org → both always-run org checks are 'incomplete'.
        # check_org_exists maps AWSOrganizationsNotInUseException to 'incomplete'
        # (a standalone account legitimately has no org — a gap, not an error).
        org_check = next(c for c in checks if c["check"] == "AWS Organization exists")
        assert org_check["status"] == "incomplete"
        mgmt_check = next(
            c for c in checks if c["check"] == "Management account identified"
        )
        assert mgmt_check["status"] == "incomplete"

        # Reports still generated
        assert os.path.exists(os.path.join(output_dir, "wafa-report.html"))
        assert os.path.exists(os.path.join(output_dir, "wafa-raw.json"))

    @patch("src.main.parse_args")
    @patch("src.checks.account_resources.boto3.client")
    @patch("src.checks.identity.boto3.client")
    @patch("src.discovery.regions.boto3.client")
    @patch("src.discovery.account_type.boto3.client")
    def test_standalone_maturity_is_low(
        self,
        mock_acct_client,
        mock_regions_client,
        mock_id_client,
        mock_res_client,
        mock_parse_args,
        tmp_path,
    ):
        """Standalone account is pinned at maturity Level 1."""
        mock_parse_args.return_value = MagicMock(output=str(tmp_path))

        factory = _mock_standalone_account_boto3()
        mock_acct_client.side_effect = factory
        mock_regions_client.side_effect = factory
        mock_id_client.side_effect = factory
        mock_res_client.side_effect = factory

        _, maturity = run()

        assert maturity["level"] == 1


# ============================================================================
# S3 upload path
# ============================================================================


class TestUploadToS3:
    """Test the S3 upload logic."""

    @patch("src.main.boto3.client")
    def test_upload_to_s3(self, mock_client):
        """Files are uploaded with correct keys."""
        mock_s3 = MagicMock()
        mock_client.return_value = mock_s3

        upload_to_s3(
            "s3://my-bucket/reports/",
            "111111111111",
            [
                ("wafa-report.html", "<html>test</html>", "text/html"),
                ("wafa-raw.json", '{"test": true}', "application/json"),
            ],
        )

        assert mock_s3.put_object.call_count == 2
        calls = mock_s3.put_object.call_args_list

        # First call: HTML report
        assert calls[0].kwargs["Bucket"] == "my-bucket"
        assert calls[0].kwargs["Key"] == "reports/111111111111/wafa-report.html"
        assert calls[0].kwargs["ContentType"] == "text/html"

        # Second call: JSON
        assert calls[1].kwargs["Key"] == "reports/111111111111/wafa-raw.json"

    @patch("src.main.boto3.client")
    def test_upload_to_s3_no_prefix(self, mock_client):
        """S3 upload works when URI has no prefix (just bucket)."""
        mock_s3 = MagicMock()
        mock_client.return_value = mock_s3

        upload_to_s3(
            "s3://my-bucket",
            "123456789012",
            [("wafa-report.html", "test", "text/html")],
        )

        call = mock_s3.put_object.call_args
        assert call.kwargs["Bucket"] == "my-bucket"
        assert call.kwargs["Key"] == "123456789012/wafa-report.html"


# ============================================================================
# print_summary
# ============================================================================


class TestPrintSummary:
    """Test console output formatting."""

    def test_prints_without_error(self, capsys):
        """print_summary doesn't crash and outputs expected content."""
        checks = [
            {
                "check": "Test Check",
                "description": "A test",
                "status": "complete",
                "required": True,
                "weight": 6,
                "loe": 1,
                "remediationLink": "https://example.com",
            },
            {
                "check": "Another Check",
                "description": "Another test",
                "status": "incomplete",
                "required": False,
                "weight": 4,
                "loe": 2,
                "remediationLink": "https://example.com",
            },
        ]
        maturity = {
            "level": 2,
            "name": "Established",
            "description": "Org in place.",
            "next_level": 3,
            "next_level_progress": 50.0,
            "next_level_checks_needed": ["SCP enabled"],
        }

        print_summary(checks, maturity)
        captured = capsys.readouterr()

        assert "WAFA ASSESSMENT RESULTS" in captured.out
        assert "Level 2" in captured.out or "Maturity Level: 2" in captured.out
        assert "Test Check" in captured.out
        assert "complete" in captured.out
        assert "incomplete" in captured.out
        assert "50%" in captured.out

    def test_prints_level_5_no_next_steps(self, capsys):
        """Level 5: no next level shown."""
        checks = [
            {
                "check": "All Done",
                "description": "Done",
                "status": "complete",
                "required": True,
                "weight": 6,
                "loe": 1,
                "remediationLink": "https://example.com",
            },
        ]
        maturity = {
            "level": 5,
            "name": "Expert",
            "description": "Fully codified.",
            "next_level": None,
            "next_level_progress": 100,
            "next_level_checks_needed": [],
        }

        print_summary(checks, maturity)
        captured = capsys.readouterr()

        assert "Expert" in captured.out
        assert "Progress toward" not in captured.out
