"""Unit tests for src/checks/identity.py — FR-6: Identity Checks."""

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from src.checks.identity import check_iam_identity_center, check_no_iam_users, run_all

# ============================================================================
# FR-6.1: IAM Identity Center Configured
# ============================================================================


class TestCheckIamIdentityCenter:
    @patch("src.checks.identity.boto3.client")
    def test_complete_found_in_first_region(self, mock_client):
        """IDC found in first region — stops immediately."""
        mock_sso = MagicMock()
        mock_sso.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/ssoins-123"}]
        }
        mock_client.return_value = mock_sso

        result = check_iam_identity_center(["us-east-1", "eu-west-1"])
        assert result["status"] == "complete"
        # Should only be called for the first region since we found it
        mock_client.assert_called_once_with("sso-admin", region_name="us-east-1")

    @patch("src.checks.identity.boto3.client")
    def test_complete_found_in_later_region(self, mock_client):
        """IDC not in first region, found in second."""
        mock_sso_1 = MagicMock()
        mock_sso_1.list_instances.return_value = {"Instances": []}

        mock_sso_2 = MagicMock()
        mock_sso_2.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/ssoins-456"}]
        }

        mock_client.side_effect = [mock_sso_1, mock_sso_2]

        result = check_iam_identity_center(["us-east-1", "eu-west-1"])
        assert result["status"] == "complete"

    @patch("src.checks.identity.boto3.client")
    def test_incomplete_not_found_anywhere(self, mock_client):
        """IDC not found in any region."""
        mock_sso = MagicMock()
        mock_sso.list_instances.return_value = {"Instances": []}
        mock_client.return_value = mock_sso

        result = check_iam_identity_center(["us-east-1", "eu-west-1"])
        assert result["status"] == "incomplete"

    @patch("src.checks.identity.boto3.client")
    def test_skips_region_on_client_error(self, mock_client):
        """Region throws ClientError — skips to next region."""
        mock_sso_1 = MagicMock()
        mock_sso_1.list_instances.side_effect = ClientError(
            {"Error": {"Code": "InvalidRegion", "Message": "Not supported"}},
            "ListInstances",
        )

        mock_sso_2 = MagicMock()
        mock_sso_2.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/ssoins-789"}]
        }

        mock_client.side_effect = [mock_sso_1, mock_sso_2]

        result = check_iam_identity_center(["us-west-1", "us-east-1"])
        assert result["status"] == "complete"

    @patch("src.checks.identity.boto3.client")
    def test_error_on_access_denied_in_all_regions(self, mock_client):
        """AccessDenied is a permission failure, not 'not configured' — status must be error."""
        mock_sso = MagicMock()
        mock_sso.list_instances.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "ListInstances",
        )
        mock_client.return_value = mock_sso

        result = check_iam_identity_center(["us-east-1", "eu-west-1"])
        assert result["status"] == "error"
        assert "AccessDeniedException" in result["error"]

    @patch("src.checks.identity.boto3.client")
    def test_complete_despite_access_denied_in_earlier_region(self, mock_client):
        """AccessDenied in one region doesn't block success in a later region."""
        mock_sso_1 = MagicMock()
        mock_sso_1.list_instances.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Denied"}},
            "ListInstances",
        )
        mock_sso_2 = MagicMock()
        mock_sso_2.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/ssoins-999"}]
        }
        mock_client.side_effect = [mock_sso_1, mock_sso_2]

        result = check_iam_identity_center(["us-west-1", "us-east-1"])
        assert result["status"] == "complete"

    @patch("src.checks.identity.boto3.client")
    def test_error_when_throttled_everywhere(self, mock_client):
        """Throttling leaves the state unknown, so the check is not incomplete."""
        mock_client.return_value.list_instances.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Slow down"}},
            "ListInstances",
        )

        result = check_iam_identity_center(["us-east-1", "eu-west-1"])
        assert result["status"] == "error"
        assert "us-east-1: ThrottlingException" in result["error"]

    @patch("src.checks.identity.has_service_endpoint", return_value=False)
    @patch("src.checks.identity.boto3.client")
    def test_region_without_endpoint_is_skipped(self, mock_client, mock_endpoint):
        from botocore.exceptions import EndpointConnectionError

        unsupported = MagicMock()
        unsupported.list_instances.side_effect = EndpointConnectionError(
            endpoint_url="https://sso.example-region-1.amazonaws.com"
        )
        empty = MagicMock()
        empty.list_instances.return_value = {"Instances": []}
        mock_client.side_effect = [unsupported, empty]

        result = check_iam_identity_center(["example-region-1", "us-east-1"])
        assert result["status"] == "incomplete"
        mock_endpoint.assert_called_once_with("sso-admin", "example-region-1")

    @patch("src.checks.identity.has_service_endpoint", return_value=True)
    @patch("src.checks.identity.boto3.client")
    def test_connection_failure_in_supported_region_is_error(
        self, mock_client, mock_endpoint
    ):
        from botocore.exceptions import EndpointConnectionError

        unreachable = MagicMock()
        unreachable.list_instances.side_effect = EndpointConnectionError(
            endpoint_url="https://sso.eu-west-1.amazonaws.com"
        )
        empty = MagicMock()
        empty.list_instances.return_value = {"Instances": []}
        mock_client.side_effect = [unreachable, empty]

        result = check_iam_identity_center(["eu-west-1", "us-east-1"])
        assert result["status"] == "error"
        assert "eu-west-1" in result["error"]

    @patch("src.checks.identity.boto3.client")
    def test_complete_despite_failure_in_earlier_region(self, mock_client):
        failing = MagicMock()
        failing.list_instances.side_effect = RuntimeError("connection reset")
        found = MagicMock()
        found.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/ssoins-1"}]
        }
        mock_client.side_effect = [failing, found]

        result = check_iam_identity_center(["eu-west-1", "us-east-1"])
        assert result["status"] == "complete"

    @patch("src.checks.identity.boto3.client")
    def test_error_on_non_client_error(self, mock_client):
        """Non-ClientError (e.g., TypeError) is caught at outer level."""
        mock_client.side_effect = TypeError("Unexpected error")

        result = check_iam_identity_center(["us-east-1"])
        assert result["status"] == "error"
        assert "error" in result


# ============================================================================
# FR-6.2: No IAM Users
# ============================================================================


class TestCheckNoIamUsers:
    @patch("src.checks.identity.boto3.client")
    def test_complete_no_users(self, mock_client):
        """No IAM users — complete."""
        mock_iam = MagicMock()
        mock_iam.get_paginator.return_value.paginate.return_value = [{"Users": []}]
        mock_client.return_value = mock_iam

        result = check_no_iam_users()
        assert result["status"] == "complete"
        assert "assessed account" in result["description"]

    @patch("src.checks.identity.boto3.client")
    def test_incomplete_users_exist(self, mock_client):
        """IAM users exist — incomplete."""
        mock_iam = MagicMock()
        mock_iam.get_paginator.return_value.paginate.return_value = [
            {"Users": [{"UserName": "legacy-admin", "UserId": "AIDA123"}]}
        ]
        mock_client.return_value = mock_iam

        result = check_no_iam_users()
        assert result["status"] == "incomplete"

    @patch("src.checks.identity.boto3.client")
    def test_incomplete_users_on_later_page(self, mock_client):
        """Users found only on a later page — incomplete (pagination required)."""
        mock_iam = MagicMock()
        mock_iam.get_paginator.return_value.paginate.return_value = [
            {"Users": []},
            {"Users": [{"UserName": "legacy-admin", "UserId": "AIDA123"}]},
        ]
        mock_client.return_value = mock_iam

        result = check_no_iam_users()
        assert result["status"] == "incomplete"

    @patch("src.checks.identity.boto3.client")
    def test_error(self, mock_client):
        """API error."""
        mock_iam = MagicMock()
        mock_iam.get_paginator.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "ListUsers",
        )
        mock_client.return_value = mock_iam

        result = check_no_iam_users()
        assert result["status"] == "error"
        assert "error" in result

    @patch("src.checks.identity.boto3.client")
    def test_uses_partition_default_region(self, mock_client):
        """IAM is queried in the partition default region, not us-east-1."""
        mock_client.return_value.get_paginator.return_value.paginate.return_value = [
            {"Users": []}
        ]

        for region in ("us-gov-west-1", "cn-north-1"):
            mock_client.reset_mock()
            result = check_no_iam_users(region)
            assert result["status"] == "complete"
            mock_client.assert_called_once_with("iam", region_name=region)


# ============================================================================
# run_all
# ============================================================================


class TestRunAll:
    @patch("src.checks.identity.boto3.client")
    def test_management_account_runs_both(self, mock_client):
        """Management account: runs both FR-6.1 and FR-6.2."""
        mock_sso = MagicMock()
        mock_sso.list_instances.return_value = {"Instances": [{"InstanceArn": "arn"}]}

        mock_iam = MagicMock()
        mock_iam.get_paginator.return_value.paginate.return_value = [{"Users": []}]

        def client_factory(service, **kwargs):
            if service == "sso-admin":
                return mock_sso
            elif service == "iam":
                return mock_iam
            return MagicMock()

        mock_client.side_effect = client_factory

        results = run_all(["us-east-1"], is_management_account=True)
        assert len(results) == 2

    @patch("src.checks.identity.boto3.client")
    def test_non_management_runs_only_iam_users(self, mock_client):
        """Non-management account: only FR-6.2 runs."""
        mock_iam = MagicMock()
        mock_iam.get_paginator.return_value.paginate.return_value = [{"Users": []}]
        mock_client.return_value = mock_iam

        results = run_all(["us-east-1"], is_management_account=False)
        assert len(results) == 1
        assert results[0]["check"] == "No IAM users in account"
