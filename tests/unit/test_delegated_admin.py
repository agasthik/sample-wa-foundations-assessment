"""Unit tests for src/checks/delegated_admin.py — FR-9: Delegated Administrator Checks."""

from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

from src.checks.delegated_admin import get_delegated_administrators


class TestGetDelegatedAdministrators:
    @patch("src.checks.delegated_admin.boto3.client")
    def test_returns_admins_with_services(self, mock_client):
        """Complete case: delegated admins found with services."""
        mock_org = MagicMock()
        mock_da_paginator = MagicMock()
        mock_da_paginator.paginate.return_value = [
            {
                "DelegatedAdministrators": [
                    {"Id": "222222222222", "Name": "Security"},
                    {"Id": "333333333333", "Name": "Shared Services"},
                ]
            }
        ]

        mock_svc_paginator = MagicMock()
        mock_svc_paginator.paginate.return_value = [
            {
                "DelegatedServices": [
                    {"ServicePrincipal": "guardduty.amazonaws.com"},
                    {"ServicePrincipal": "securityhub.amazonaws.com"},
                ]
            }
        ]

        def get_paginator(name):
            if name == "list_delegated_administrators":
                return mock_da_paginator
            elif name == "list_delegated_services_for_account":
                return mock_svc_paginator
            return MagicMock()

        mock_org.get_paginator.side_effect = get_paginator
        mock_client.return_value = mock_org

        result = get_delegated_administrators()

        assert len(result) == 2
        assert result[0]["accountId"] == "222222222222"
        assert result[0]["accountName"] == "Security"
        assert "guardduty.amazonaws.com" in result[0]["services"]

    @patch("src.checks.delegated_admin.boto3.client")
    def test_returns_empty_when_no_admins(self, mock_client):
        """No delegated admins → empty list."""
        mock_org = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"DelegatedAdministrators": []}]
        mock_org.get_paginator.return_value = mock_paginator
        mock_client.return_value = mock_org

        result = get_delegated_administrators()
        assert result == []

    @patch("src.checks.delegated_admin.boto3.client")
    def test_returns_empty_on_error(self, mock_client):
        """API error → returns empty list (no crash)."""
        mock_org = MagicMock()
        mock_org.get_paginator.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "ListDelegatedAdministrators",
        )
        mock_client.return_value = mock_org

        result = get_delegated_administrators()
        assert result == []
