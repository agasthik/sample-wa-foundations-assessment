"""Unit tests for src/checks/delegated_admin.py — FR-9: Delegated Administrator Checks."""

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError, EndpointConnectionError

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

        result, error = get_delegated_administrators()

        assert error is None
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

        result, error = get_delegated_administrators()
        assert result == []
        assert error is None

    @patch("src.checks.delegated_admin.boto3.client")
    def test_reports_error_on_failure(self, mock_client):
        """API error → empty list plus an error message (no crash)."""
        mock_org = MagicMock()
        mock_org.get_paginator.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "ListDelegatedAdministrators",
        )
        mock_client.return_value = mock_org

        result, error = get_delegated_administrators()
        assert result == []
        assert "AccessDeniedException" in error

    @patch("src.checks.delegated_admin.boto3.client")
    def test_keeps_admins_collected_before_failure(self, mock_client):
        """A failure partway through pagination keeps earlier admins."""

        def pages():
            yield {"DelegatedAdministrators": [{"Id": "222222222222", "Name": "A"}]}
            raise ClientError(
                {"Error": {"Code": "ThrottlingException", "Message": "Slow"}},
                "ListDelegatedAdministrators",
            )

        da_paginator = MagicMock()
        da_paginator.paginate.return_value = pages()
        svc_paginator = MagicMock()
        svc_paginator.paginate.return_value = [{"DelegatedServices": []}]
        mock_org = MagicMock()
        mock_org.get_paginator.side_effect = lambda name: (
            da_paginator if name == "list_delegated_administrators" else svc_paginator
        )
        mock_client.return_value = mock_org

        result, error = get_delegated_administrators()
        assert [a["accountId"] for a in result] == ["222222222222"]
        assert "ThrottlingException" in error

    @patch("src.checks.delegated_admin.boto3.client")
    def test_records_per_account_service_error(self, mock_client):
        da_paginator = MagicMock()
        da_paginator.paginate.return_value = [
            {"DelegatedAdministrators": [{"Id": "222222222222", "Name": "A"}]}
        ]
        svc_paginator = MagicMock()
        svc_paginator.paginate.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "ListDelegatedServicesForAccount",
        )
        mock_org = MagicMock()
        mock_org.get_paginator.side_effect = lambda name: (
            da_paginator if name == "list_delegated_administrators" else svc_paginator
        )
        mock_client.return_value = mock_org

        result, error = get_delegated_administrators()
        assert error is None
        assert result[0]["services"] == []
        assert "AccessDeniedException" in result[0]["servicesError"]

    @patch("src.checks.delegated_admin.boto3.client")
    def test_connection_error_keeps_services_and_later_admins(self, mock_client):
        da_paginator = MagicMock()
        da_paginator.paginate.return_value = [
            {
                "DelegatedAdministrators": [
                    {"Id": "222222222222", "Name": "Security"},
                    {"Id": "333333333333", "Name": "Audit"},
                ]
            }
        ]

        def service_pages(account_id):
            if account_id == "222222222222":
                yield {
                    "DelegatedServices": [
                        {"ServicePrincipal": "guardduty.amazonaws.com"}
                    ]
                }
                raise EndpointConnectionError(
                    endpoint_url="https://organizations.us-east-1.amazonaws.com"
                )
            yield {
                "DelegatedServices": [{"ServicePrincipal": "securityhub.amazonaws.com"}]
            }

        svc_paginator = MagicMock()
        svc_paginator.paginate.side_effect = lambda AccountId: service_pages(AccountId)
        mock_org = MagicMock()
        mock_org.get_paginator.side_effect = lambda name: (
            da_paginator if name == "list_delegated_administrators" else svc_paginator
        )
        mock_client.return_value = mock_org

        result, error = get_delegated_administrators()

        assert error is None
        assert [admin["accountId"] for admin in result] == [
            "222222222222",
            "333333333333",
        ]
        assert result[0]["services"] == ["guardduty.amazonaws.com"]
        assert "Could not connect to the endpoint URL" in result[0]["servicesError"]
        assert result[1]["services"] == ["securityhub.amazonaws.com"]
        assert "servicesError" not in result[1]
