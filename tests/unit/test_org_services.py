"""Unit tests for src/checks/org_services.py — FR-4: Organization Service Integration Checks."""

from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

from src.checks.org_services import run_all, check_org_service


class TestRunAll:
    """Tests for run_all() — all FR-4.x checks in a single pass."""

    @patch("src.checks.org_services.boto3.client")
    def test_all_services_enabled(self, mock_client):
        """Complete case: all service principals are enabled."""
        mock_org = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
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
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        results = run_all()

        assert len(results) == 10
        for r in results:
            assert r["status"] == "complete"
            assert "remediationLink" in r
            assert r["remediationLink"].startswith("https://")

    @patch("src.checks.org_services.boto3.client")
    def test_no_services_enabled(self, mock_client):
        """Incomplete case: no service principals are enabled."""
        mock_org = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"EnabledServicePrincipals": []}]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        results = run_all()

        assert len(results) == 10
        for r in results:
            assert r["status"] == "incomplete"

    @patch("src.checks.org_services.boto3.client")
    def test_partial_services_enabled(self, mock_client):
        """Mixed case: some services enabled, some not."""
        mock_org = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "EnabledServicePrincipals": [
                    {"ServicePrincipal": "cloudtrail.amazonaws.com"},
                    {"ServicePrincipal": "sso.amazonaws.com"},
                ]
            }
        ]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        results = run_all()

        assert len(results) == 10
        # CloudTrail (FR-4.1) and SSO (FR-4.7) should be complete
        cloudtrail = next(r for r in results if "CloudTrail" in r["check"])
        assert cloudtrail["status"] == "complete"
        sso = next(r for r in results if "Identity Center" in r["check"])
        assert sso["status"] == "complete"
        # GuardDuty should be incomplete
        guardduty = next(r for r in results if "GuardDuty" in r["check"])
        assert guardduty["status"] == "incomplete"

    @patch("src.checks.org_services.boto3.client")
    def test_api_error(self, mock_client):
        """Error case: API call fails — all checks marked as error."""
        mock_org = MagicMock()
        mock_org.get_paginator.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
            "ListAWSServiceAccessForOrganization",
        )
        mock_client.return_value = mock_org

        results = run_all()

        assert len(results) == 10
        for r in results:
            assert r["status"] == "error"
            assert "error" in r

    @patch("src.checks.org_services.boto3.client")
    def test_check_metadata_schema(self, mock_client):
        """Verify all checks follow the Check Metadata Schema."""
        mock_org = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"EnabledServicePrincipals": []}]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        results = run_all()

        for r in results:
            assert "check" in r and isinstance(r["check"], str)
            assert "description" in r and isinstance(r["description"], str)
            assert "status" in r and r["status"] in ("complete", "incomplete", "error")
            assert "required" in r and isinstance(r["required"], bool)
            assert "weight" in r and isinstance(r["weight"], int)
            assert "loe" in r and isinstance(r["loe"], int)
            assert "remediationLink" in r and isinstance(r["remediationLink"], str)

    @patch("src.checks.org_services.boto3.client")
    def test_required_fields_correct(self, mock_client):
        """Verify FR-4.1 and FR-4.7 are required, others are not."""
        mock_org = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"EnabledServicePrincipals": []}]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        results = run_all()

        cloudtrail = next(r for r in results if "CloudTrail" in r["check"])
        assert cloudtrail["required"] is True
        assert cloudtrail["weight"] == 6

        sso = next(r for r in results if "Identity Center" in r["check"])
        assert sso["required"] is True
        assert sso["weight"] == 6

        guardduty = next(r for r in results if "GuardDuty" in r["check"])
        assert guardduty["required"] is False


class TestCheckOrgService:
    """Tests for the individual check_org_service function."""

    @patch("src.checks.org_services.boto3.client")
    def test_single_service_complete(self, mock_client):
        """Single service check — found."""
        mock_org = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "EnabledServicePrincipals": [
                    {"ServicePrincipal": "guardduty.amazonaws.com"},
                ]
            }
        ]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = check_org_service(
            service_principal="guardduty.amazonaws.com",
            check_name="GuardDuty org service",
            description="Test",
            weight=4,
            loe=1,
            required=False,
            remediation_link="https://example.com",
        )
        assert result["status"] == "complete"

    @patch("src.checks.org_services.boto3.client")
    def test_single_service_incomplete(self, mock_client):
        """Single service check — not found."""
        mock_org = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"EnabledServicePrincipals": []}]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = check_org_service(
            service_principal="guardduty.amazonaws.com",
            check_name="GuardDuty org service",
            description="Test",
            weight=4,
            loe=1,
            required=False,
            remediation_link="https://example.com",
        )
        assert result["status"] == "incomplete"

    @patch("src.checks.org_services.boto3.client")
    def test_single_service_error(self, mock_client):
        """Single service check — API error."""
        mock_org = MagicMock()
        mock_org.get_paginator.side_effect = Exception("Network error")
        mock_client.return_value = mock_org

        result = check_org_service(
            service_principal="guardduty.amazonaws.com",
            check_name="GuardDuty org service",
            description="Test",
            weight=4,
            loe=1,
            required=False,
            remediation_link="https://example.com",
        )
        assert result["status"] == "error"
        assert "error" in result
