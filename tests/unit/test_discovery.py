"""Unit tests for src/discovery/ — FR-2: account type detection and region discovery."""

import os
from unittest.mock import MagicMock, patch

from src.discovery.account_type import detect_account_type, detect_partition
from src.discovery.regions import (
    DEFAULT_REGIONS,
    discover_regions,
    get_enabled_regions,
)

# ============================================================================
# FR-2.1 / FR-2.2: Account Type Detection
# ============================================================================


class TestDetectPartition:
    """Tests for detect_partition (FR-1.5)."""

    def test_commercial_partition(self):
        with patch.dict(os.environ, {"AWS_DEFAULT_REGION": "us-east-1"}):
            result = detect_partition()
            assert result["partition"] == "aws"
            assert result["default_region"] == "us-east-1"

    def test_govcloud_partition(self):
        with patch.dict(os.environ, {"AWS_DEFAULT_REGION": "us-gov-west-1"}):
            result = detect_partition()
            assert result["partition"] == "aws-us-gov"
            assert result["default_region"] == "us-gov-west-1"

    def test_china_partition(self):
        with patch.dict(os.environ, {"AWS_DEFAULT_REGION": "cn-north-1"}):
            result = detect_partition()
            assert result["partition"] == "aws-cn"
            assert result["default_region"] == "cn-north-1"

    @patch("src.discovery.account_type.boto3.session.Session")
    def test_default_when_no_env_var(self, mock_session):
        mock_session.return_value.region_name = None
        with patch.dict(os.environ, {}, clear=True):
            result = detect_partition()
            assert result["partition"] == "aws"
            assert result["default_region"] == "us-east-1"

    @patch("src.discovery.account_type.boto3.session.Session")
    def test_aws_region_env_var(self, mock_session):
        """AWS_REGION is honored when AWS_DEFAULT_REGION is unset."""
        mock_session.return_value.region_name = None
        with patch.dict(os.environ, {"AWS_REGION": "us-gov-east-1"}, clear=True):
            result = detect_partition()
            assert result["partition"] == "aws-us-gov"
            assert result["default_region"] == "us-gov-west-1"

    @patch("src.discovery.account_type.boto3.session.Session")
    def test_profile_region_when_no_env_var(self, mock_session):
        """A Region configured only in the active profile selects the partition."""
        mock_session.return_value.region_name = "cn-northwest-1"
        with patch.dict(os.environ, {}, clear=True):
            result = detect_partition()
            assert result["partition"] == "aws-cn"
            assert result["default_region"] == "cn-north-1"


class TestDetectAccountType:
    """Tests for detect_account_type (FR-2.1, FR-2.2)."""

    @patch("src.discovery.account_type.boto3.client")
    def test_management_account(self, mock_boto_client):
        """Complete case: account is the management account of an org."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "111111111111"}

        mock_org = MagicMock()
        mock_org.describe_organization.return_value = {
            "Organization": {
                "Id": "o-abc123",
                "MasterAccountId": "111111111111",
            }
        }

        def client_factory(service, **kwargs):
            if service == "sts":
                return mock_sts
            elif service == "organizations":
                return mock_org
            return MagicMock()

        mock_boto_client.side_effect = client_factory

        result = detect_account_type()

        assert result["account_id"] == "111111111111"
        assert result["is_management_account"] is True
        assert result["is_in_organization"] is True
        assert result["organization_id"] == "o-abc123"
        assert result["management_account_id"] == "111111111111"
        assert result["account_type"] == "management"

    @patch("src.discovery.account_type.boto3.client")
    def test_member_account(self, mock_boto_client):
        """Incomplete case: account is a member account (not management)."""
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "222222222222"}

        mock_org = MagicMock()
        mock_org.describe_organization.return_value = {
            "Organization": {
                "Id": "o-abc123",
                "MasterAccountId": "111111111111",
            }
        }

        def client_factory(service, **kwargs):
            if service == "sts":
                return mock_sts
            elif service == "organizations":
                return mock_org
            return MagicMock()

        mock_boto_client.side_effect = client_factory

        result = detect_account_type()

        assert result["account_id"] == "222222222222"
        assert result["is_management_account"] is False
        assert result["is_in_organization"] is True
        assert result["account_type"] == "member"
        assert result["management_account_id"] == "111111111111"

    @patch("src.discovery.account_type.boto3.client")
    def test_standalone_account(self, mock_boto_client):
        """Incomplete case: account is standalone (no organization)."""
        from botocore.exceptions import ClientError

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "333333333333"}

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

        def client_factory(service, **kwargs):
            if service == "sts":
                return mock_sts
            elif service == "organizations":
                return mock_org
            return MagicMock()

        mock_boto_client.side_effect = client_factory

        result = detect_account_type()

        assert result["account_id"] == "333333333333"
        assert result["is_management_account"] is False
        assert result["is_in_organization"] is False
        assert result["organization_id"] is None
        assert result["account_type"] == "standalone"

    @patch("src.discovery.account_type.boto3.client")
    def test_unexpected_error_marks_account_type_unknown(self, mock_boto_client):
        """Error case: an unexpected API error does not stop the assessment."""
        from botocore.exceptions import ClientError

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "444444444444"}

        mock_org = MagicMock()
        mock_org.describe_organization.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
            "DescribeOrganization",
        )

        def client_factory(service, **kwargs):
            if service == "sts":
                return mock_sts
            elif service == "organizations":
                return mock_org
            return MagicMock()

        mock_boto_client.side_effect = client_factory

        result = detect_account_type()

        assert result["account_type"] == "unknown"
        assert result["is_management_account"] is False
        assert "AccessDeniedException" in result["detection_error"]

    @patch("src.discovery.account_type.boto3.client")
    def test_connection_error_marks_account_type_unknown(self, mock_boto_client):
        """Error case: a non-ClientError failure (endpoint/network) does not crash the run."""
        from botocore.exceptions import EndpointConnectionError

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "444444444444"}

        mock_org = MagicMock()
        mock_org.describe_organization.side_effect = EndpointConnectionError(
            endpoint_url="https://organizations.us-east-1.amazonaws.com"
        )

        def client_factory(service, **kwargs):
            if service == "sts":
                return mock_sts
            elif service == "organizations":
                return mock_org
            return MagicMock()

        mock_boto_client.side_effect = client_factory

        result = detect_account_type()

        assert result["account_type"] == "unknown"
        assert result["is_management_account"] is False
        assert "detection_error" in result


# ============================================================================
# FR-2.3: Region Discovery
# ============================================================================


class TestGetEnabledRegions:
    """Tests for get_enabled_regions (FR-2.3)."""

    @patch("src.discovery.regions.boto3.client")
    def test_regions_returned_from_api(self, mock_boto_client):
        """Complete case: API returns a list of regions."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_regions.return_value = {
            "Regions": [
                {"RegionName": "us-east-1", "Endpoint": "ec2.us-east-1.amazonaws.com"},
                {"RegionName": "eu-west-1", "Endpoint": "ec2.eu-west-1.amazonaws.com"},
                {
                    "RegionName": "ap-southeast-1",
                    "Endpoint": "ec2.ap-southeast-1.amazonaws.com",
                },
            ]
        }
        mock_boto_client.return_value = mock_ec2

        result = get_enabled_regions()

        assert result == ["ap-southeast-1", "eu-west-1", "us-east-1"]
        mock_ec2.describe_regions.assert_called_once_with(
            Filters=[
                {
                    "Name": "opt-in-status",
                    "Values": ["opt-in-not-required", "opted-in"],
                }
            ]
        )

    @patch("src.discovery.regions.boto3.client")
    def test_opted_in_regions_included_and_reported(self, mock_boto_client):
        """Opt-in regions the account enabled are scanned and listed separately."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_regions.return_value = {
            "Regions": [
                {"RegionName": "us-east-1", "OptInStatus": "opt-in-not-required"},
                {"RegionName": "eu-south-1", "OptInStatus": "opted-in"},
                {"RegionName": "af-south-1", "OptInStatus": "opted-in"},
            ]
        }
        mock_boto_client.return_value = mock_ec2

        regions, opted_in = discover_regions()

        assert regions == ["af-south-1", "eu-south-1", "us-east-1"]
        assert opted_in == ["af-south-1", "eu-south-1"]

    @patch("src.discovery.regions.boto3.client")
    def test_fallback_reports_no_opted_in_regions(self, mock_boto_client):
        mock_boto_client.return_value.describe_regions.side_effect = Exception("x")

        regions, opted_in = discover_regions("us-east-1")

        assert regions == DEFAULT_REGIONS
        assert opted_in == []

    @patch("src.discovery.regions.boto3.client")
    def test_fallback_on_api_error(self, mock_boto_client):
        """Incomplete case: API call fails, returns fallback list."""
        from botocore.exceptions import ClientError

        mock_ec2 = MagicMock()
        mock_ec2.describe_regions.side_effect = ClientError(
            {"Error": {"Code": "UnauthorizedOperation", "Message": "Not allowed"}},
            "DescribeRegions",
        )
        mock_boto_client.return_value = mock_ec2

        result = get_enabled_regions()

        assert result == DEFAULT_REGIONS

    @patch("src.discovery.regions.boto3.client")
    def test_fallback_on_empty_response(self, mock_boto_client):
        """Edge case: API returns empty Regions list."""
        mock_ec2 = MagicMock()
        mock_ec2.describe_regions.return_value = {"Regions": []}
        mock_boto_client.return_value = mock_ec2

        result = get_enabled_regions()

        assert result == DEFAULT_REGIONS

    @patch("src.discovery.regions.boto3.client")
    def test_govcloud_bootstrap_and_fallback(self, mock_boto_client):
        mock_ec2 = MagicMock()
        mock_ec2.describe_regions.return_value = {"Regions": []}
        mock_boto_client.return_value = mock_ec2

        result = get_enabled_regions("us-gov-west-1")

        assert result == ["us-gov-east-1", "us-gov-west-1"]
        mock_boto_client.assert_called_once_with("ec2", region_name="us-gov-west-1")

    @patch("src.discovery.regions.boto3.client")
    def test_china_bootstrap_and_fallback(self, mock_boto_client):
        mock_ec2 = MagicMock()
        mock_ec2.describe_regions.return_value = {"Regions": []}
        mock_boto_client.return_value = mock_ec2

        result = get_enabled_regions("cn-north-1")

        assert result == ["cn-north-1", "cn-northwest-1"]
        mock_boto_client.assert_called_once_with("ec2", region_name="cn-north-1")


class TestHasServiceEndpoint:
    @patch("src.discovery.regions.boto3.session.Session")
    def test_listed_region_has_endpoint(self, mock_session):
        from src.discovery.regions import has_service_endpoint

        session = mock_session.return_value
        session.get_partition_for_region.return_value = "aws-us-gov"
        session.get_available_regions.return_value = ["us-gov-west-1"]

        assert has_service_endpoint("sso-admin", "us-gov-west-1") is True
        session.get_available_regions.assert_called_once_with(
            "sso-admin", partition_name="aws-us-gov"
        )

    @patch("src.discovery.regions.boto3.session.Session")
    def test_unlisted_region_has_no_endpoint(self, mock_session):
        from src.discovery.regions import has_service_endpoint

        session = mock_session.return_value
        session.get_partition_for_region.return_value = "aws"
        session.get_available_regions.return_value = ["us-east-1"]

        assert has_service_endpoint("sso-admin", "ap-southeast-7") is False

    @patch("src.discovery.regions.boto3.session.Session")
    def test_unreadable_endpoint_data_assumes_endpoint(self, mock_session):
        from src.discovery.regions import has_service_endpoint

        mock_session.return_value.get_partition_for_region.side_effect = RuntimeError(
            "unknown region"
        )
        assert has_service_endpoint("sso-admin", "us-east-1") is True
