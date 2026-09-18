"""Unit tests for src/checks/organization.py — FR-3: Organization Governance Checks."""

from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

from src.checks.organization import (
    check_org_exists,
    check_management_account,
    check_minimum_accounts,
    check_log_archive_account,
    check_audit_account,
    check_scp_enabled,
    check_tag_policy_enabled,
    check_backup_policy_enabled,
    check_rcp_enabled,
    check_security_ou,
    check_workloads_ou,
    check_infrastructure_ou,
)


# ============================================================================
# FR-3.1: Org Exists
# ============================================================================


class TestCheckOrgExists:
    @patch("src.checks.organization.boto3.client")
    def test_complete(self, mock_client):
        mock_org = MagicMock()
        mock_org.describe_organization.return_value = {
            "Organization": {"Id": "o-abc123", "MasterAccountId": "111111111111"}
        }
        mock_client.return_value = mock_org

        result = check_org_exists()
        assert result["status"] == "complete"
        assert result["check"] == "AWS Organization exists"

    @patch("src.checks.organization.boto3.client")
    def test_incomplete(self, mock_client):
        mock_org = MagicMock()
        mock_org.describe_organization.return_value = {"Organization": {}}
        mock_client.return_value = mock_org

        result = check_org_exists()
        assert result["status"] == "incomplete"

    @patch("src.checks.organization.boto3.client")
    def test_error(self, mock_client):
        mock_org = MagicMock()
        mock_org.describe_organization.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "DescribeOrganization",
        )
        mock_client.return_value = mock_org

        result = check_org_exists()
        assert result["status"] == "error"
        assert "error" in result

    @patch("src.checks.organization.boto3.client")
    def test_incomplete_when_not_in_organization(self, mock_client):
        """Standalone account (no org) → incomplete, not error.

        AWS returns AWSOrganizationsNotInUseException when the account is not in
        an organization. That is a governance gap to close, not a system error.
        """
        mock_org = MagicMock()
        mock_org.describe_organization.side_effect = ClientError(
            {
                "Error": {
                    "Code": "AWSOrganizationsNotInUseException",
                    "Message": "Not in org",
                }
            },
            "DescribeOrganization",
        )
        mock_client.return_value = mock_org

        result = check_org_exists()
        assert result["status"] == "incomplete"
        assert "error" not in result


# ============================================================================
# FR-3.2: Management Account
# ============================================================================


class TestCheckManagementAccount:
    def test_complete(self):
        result = check_management_account({"is_management_account": True})
        assert result["status"] == "complete"

    def test_incomplete(self):
        result = check_management_account({"is_management_account": False})
        assert result["status"] == "incomplete"

    def test_incomplete_missing_key(self):
        result = check_management_account({})
        assert result["status"] == "incomplete"


# ============================================================================
# FR-3.3: Minimum 4 Accounts
# ============================================================================


class TestCheckMinimumAccounts:
    @patch("src.checks.organization.boto3.client")
    def test_complete(self, mock_client):
        mock_org = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "Accounts": [
                    {"Id": "1", "Name": "Management"},
                    {"Id": "2", "Name": "Log Archive"},
                    {"Id": "3", "Name": "Audit"},
                    {"Id": "4", "Name": "Workload"},
                ]
            }
        ]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = check_minimum_accounts()
        assert result["status"] == "complete"

    @patch("src.checks.organization.boto3.client")
    def test_incomplete(self, mock_client):
        mock_org = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "Accounts": [
                    {"Id": "1", "Name": "Management"},
                    {"Id": "2", "Name": "Log Archive"},
                ]
            }
        ]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = check_minimum_accounts()
        assert result["status"] == "incomplete"

    @patch("src.checks.organization.boto3.client")
    def test_error(self, mock_client):
        mock_org = MagicMock()
        mock_org.get_paginator.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "ListAccounts",
        )
        mock_client.return_value = mock_org

        result = check_minimum_accounts()
        assert result["status"] == "error"


# ============================================================================
# FR-3.4: Log Archive Account
# ============================================================================


class TestCheckLogArchiveAccount:
    @patch("src.checks.organization.boto3.client")
    def test_complete(self, mock_client):
        mock_org = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "Accounts": [
                    {"Id": "1", "Name": "Management"},
                    {"Id": "2", "Name": "Log Archive"},
                ]
            }
        ]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = check_log_archive_account()
        assert result["status"] == "complete"

    @patch("src.checks.organization.boto3.client")
    def test_complete_case_insensitive(self, mock_client):
        mock_org = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"Accounts": [{"Id": "1", "Name": "log archive"}]}
        ]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = check_log_archive_account()
        assert result["status"] == "complete"

    @patch("src.checks.organization.boto3.client")
    def test_incomplete(self, mock_client):
        mock_org = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "Accounts": [
                    {"Id": "1", "Name": "Management"},
                    {"Id": "2", "Name": "Production"},
                ]
            }
        ]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = check_log_archive_account()
        assert result["status"] == "incomplete"

    @patch("src.checks.organization.boto3.client")
    def test_error(self, mock_client):
        mock_org = MagicMock()
        mock_org.get_paginator.side_effect = Exception("Connection error")
        mock_client.return_value = mock_org

        result = check_log_archive_account()
        assert result["status"] == "error"


# ============================================================================
# FR-3.5: Audit Account
# ============================================================================


class TestCheckAuditAccount:
    @patch("src.checks.organization.boto3.client")
    def test_complete_audit(self, mock_client):
        mock_org = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"Accounts": [{"Id": "1", "Name": "Audit"}]}
        ]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = check_audit_account()
        assert result["status"] == "complete"

    @patch("src.checks.organization.boto3.client")
    def test_complete_security_tooling(self, mock_client):
        mock_org = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"Accounts": [{"Id": "1", "Name": "Security Tooling"}]}
        ]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = check_audit_account()
        assert result["status"] == "complete"

    @patch("src.checks.organization.boto3.client")
    def test_incomplete(self, mock_client):
        mock_org = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"Accounts": [{"Id": "1", "Name": "Production"}]}
        ]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = check_audit_account()
        assert result["status"] == "incomplete"

    @patch("src.checks.organization.boto3.client")
    def test_error(self, mock_client):
        mock_org = MagicMock()
        mock_org.get_paginator.side_effect = Exception("Timeout")
        mock_client.return_value = mock_org

        result = check_audit_account()
        assert result["status"] == "error"


# ============================================================================
# FR-3.6: SCP Enabled
# ============================================================================


class TestCheckScpEnabled:
    @patch("src.checks.organization.boto3.client")
    def test_complete(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.return_value = {
            "Roots": [
                {
                    "Id": "r-abc",
                    "PolicyTypes": [
                        {"Type": "SERVICE_CONTROL_POLICY", "Status": "ENABLED"}
                    ],
                }
            ]
        }
        mock_client.return_value = mock_org

        result = check_scp_enabled()
        assert result["status"] == "complete"

    @patch("src.checks.organization.boto3.client")
    def test_incomplete_not_enabled(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.return_value = {
            "Roots": [
                {
                    "Id": "r-abc",
                    "PolicyTypes": [
                        {"Type": "SERVICE_CONTROL_POLICY", "Status": "PENDING_ENABLE"}
                    ],
                }
            ]
        }
        mock_client.return_value = mock_org

        result = check_scp_enabled()
        assert result["status"] == "incomplete"

    @patch("src.checks.organization.boto3.client")
    def test_incomplete_empty_policy_types(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.return_value = {
            "Roots": [{"Id": "r-abc", "PolicyTypes": []}]
        }
        mock_client.return_value = mock_org

        result = check_scp_enabled()
        assert result["status"] == "incomplete"

    @patch("src.checks.organization.boto3.client")
    def test_error(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "ListRoots",
        )
        mock_client.return_value = mock_org

        result = check_scp_enabled()
        assert result["status"] == "error"


# ============================================================================
# FR-3.7: Tag Policy Enabled
# ============================================================================


class TestCheckTagPolicyEnabled:
    @patch("src.checks.organization.boto3.client")
    def test_complete(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.return_value = {
            "Roots": [
                {
                    "Id": "r-abc",
                    "PolicyTypes": [{"Type": "TAG_POLICY", "Status": "ENABLED"}],
                }
            ]
        }
        mock_client.return_value = mock_org

        result = check_tag_policy_enabled()
        assert result["status"] == "complete"

    @patch("src.checks.organization.boto3.client")
    def test_incomplete(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.return_value = {
            "Roots": [{"Id": "r-abc", "PolicyTypes": []}]
        }
        mock_client.return_value = mock_org

        result = check_tag_policy_enabled()
        assert result["status"] == "incomplete"

    @patch("src.checks.organization.boto3.client")
    def test_error(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.side_effect = Exception("Network error")
        mock_client.return_value = mock_org

        result = check_tag_policy_enabled()
        assert result["status"] == "error"


# ============================================================================
# FR-3.8: Backup Policy Enabled
# ============================================================================


class TestCheckBackupPolicyEnabled:
    @patch("src.checks.organization.boto3.client")
    def test_complete(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.return_value = {
            "Roots": [
                {
                    "Id": "r-abc",
                    "PolicyTypes": [{"Type": "BACKUP_POLICY", "Status": "ENABLED"}],
                }
            ]
        }
        mock_client.return_value = mock_org

        result = check_backup_policy_enabled()
        assert result["status"] == "complete"
        assert result["required"] is False

    @patch("src.checks.organization.boto3.client")
    def test_incomplete(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.return_value = {
            "Roots": [{"Id": "r-abc", "PolicyTypes": []}]
        }
        mock_client.return_value = mock_org

        result = check_backup_policy_enabled()
        assert result["status"] == "incomplete"

    @patch("src.checks.organization.boto3.client")
    def test_error(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.side_effect = Exception("Error")
        mock_client.return_value = mock_org

        result = check_backup_policy_enabled()
        assert result["status"] == "error"


# ============================================================================
# FR-3.9: RCP Enabled
# ============================================================================


class TestCheckRcpEnabled:
    @patch("src.checks.organization.boto3.client")
    def test_complete(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.return_value = {
            "Roots": [
                {
                    "Id": "r-abc",
                    "PolicyTypes": [
                        {"Type": "RESOURCE_CONTROL_POLICY", "Status": "ENABLED"}
                    ],
                }
            ]
        }
        mock_client.return_value = mock_org

        result = check_rcp_enabled()
        assert result["status"] == "complete"

    @patch("src.checks.organization.boto3.client")
    def test_incomplete(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.return_value = {
            "Roots": [{"Id": "r-abc", "PolicyTypes": []}]
        }
        mock_client.return_value = mock_org

        result = check_rcp_enabled()
        assert result["status"] == "incomplete"

    @patch("src.checks.organization.boto3.client")
    def test_error(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.side_effect = Exception("Error")
        mock_client.return_value = mock_org

        result = check_rcp_enabled()
        assert result["status"] == "error"


# ============================================================================
# FR-3.10: Security OU
# ============================================================================


class TestCheckSecurityOu:
    @patch("src.checks.organization.boto3.client")
    def test_complete(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.return_value = {"Roots": [{"Id": "r-abc"}]}
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "OrganizationalUnits": [
                    {"Id": "ou-1", "Name": "Security"},
                    {"Id": "ou-2", "Name": "Workloads"},
                ]
            }
        ]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = check_security_ou()
        assert result["status"] == "complete"

    @patch("src.checks.organization.boto3.client")
    def test_complete_case_insensitive(self, mock_client):
        """OU name match is case-insensitive (e.g. 'security' → complete)."""
        mock_org = MagicMock()
        mock_org.list_roots.return_value = {"Roots": [{"Id": "r-abc"}]}
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"OrganizationalUnits": [{"Id": "ou-1", "Name": "security"}]}
        ]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = check_security_ou()
        assert result["status"] == "complete"

    @patch("src.checks.organization.boto3.client")
    def test_incomplete(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.return_value = {"Roots": [{"Id": "r-abc"}]}
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"OrganizationalUnits": [{"Id": "ou-1", "Name": "Workloads"}]}
        ]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = check_security_ou()
        assert result["status"] == "incomplete"

    @patch("src.checks.organization.boto3.client")
    def test_error(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.side_effect = Exception("Error")
        mock_client.return_value = mock_org

        result = check_security_ou()
        assert result["status"] == "error"


# ============================================================================
# FR-3.11: Workloads OU
# ============================================================================


class TestCheckWorkloadsOu:
    @patch("src.checks.organization.boto3.client")
    def test_complete(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.return_value = {"Roots": [{"Id": "r-abc"}]}
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"OrganizationalUnits": [{"Id": "ou-1", "Name": "Workloads"}]}
        ]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = check_workloads_ou()
        assert result["status"] == "complete"

    @patch("src.checks.organization.boto3.client")
    def test_incomplete(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.return_value = {"Roots": [{"Id": "r-abc"}]}
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"OrganizationalUnits": [{"Id": "ou-1", "Name": "Security"}]}
        ]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = check_workloads_ou()
        assert result["status"] == "incomplete"

    @patch("src.checks.organization.boto3.client")
    def test_error(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.side_effect = Exception("Error")
        mock_client.return_value = mock_org

        result = check_workloads_ou()
        assert result["status"] == "error"


# ============================================================================
# FR-3.12: Infrastructure OU
# ============================================================================


class TestCheckInfrastructureOu:
    @patch("src.checks.organization.boto3.client")
    def test_complete(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.return_value = {"Roots": [{"Id": "r-abc"}]}
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"OrganizationalUnits": [{"Id": "ou-1", "Name": "Infrastructure"}]}
        ]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = check_infrastructure_ou()
        assert result["status"] == "complete"

    @patch("src.checks.organization.boto3.client")
    def test_incomplete(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.return_value = {"Roots": [{"Id": "r-abc"}]}
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"OrganizationalUnits": [{"Id": "ou-1", "Name": "Sandbox"}]}
        ]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = check_infrastructure_ou()
        assert result["status"] == "incomplete"

    @patch("src.checks.organization.boto3.client")
    def test_error(self, mock_client):
        mock_org = MagicMock()
        mock_org.list_roots.side_effect = Exception("Error")
        mock_client.return_value = mock_org

        result = check_infrastructure_ou()
        assert result["status"] == "error"
