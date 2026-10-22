"""Unit tests for src/checks/control_tower.py — FR-5: Control Tower Checks."""

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from src.checks.control_tower import (
    check_control_tower_deployed,
    check_control_tower_latest_version,
    check_control_tower_not_drifted,
)

# ============================================================================
# FR-5.1: Control Tower Deployed
# ============================================================================


class TestCheckControlTowerDeployed:
    @patch("src.checks.control_tower.boto3.client")
    def test_complete(self, mock_client):
        """Control Tower is deployed — landing zones list is non-empty."""
        mock_ct = MagicMock()
        mock_ct.list_landing_zones.return_value = {
            "landingZones": [
                {"arn": "arn:aws:controltower:us-east-1:111:landingzone/abc"}
            ]
        }
        mock_client.return_value = mock_ct

        result = check_control_tower_deployed()
        assert result["status"] == "complete"
        assert result["check"] == "Control Tower deployed"

    @patch("src.checks.control_tower.boto3.client")
    def test_incomplete(self, mock_client):
        """Control Tower not deployed — empty landing zones list."""
        mock_ct = MagicMock()
        mock_ct.list_landing_zones.return_value = {"landingZones": []}
        mock_client.return_value = mock_ct

        result = check_control_tower_deployed()
        assert result["status"] == "incomplete"

    @patch("src.checks.control_tower.boto3.client")
    def test_error(self, mock_client):
        """API error — check returns error status."""
        mock_ct = MagicMock()
        mock_ct.list_landing_zones.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "ListLandingZones",
        )
        mock_client.return_value = mock_ct

        result = check_control_tower_deployed()
        assert result["status"] == "error"
        assert "error" in result


# ============================================================================
# FR-5.2: Control Tower Not Drifted
# ============================================================================


class TestCheckControlTowerNotDrifted:
    @patch("src.checks.control_tower.boto3.client")
    def test_complete_not_drifted(self, mock_client):
        """Landing zone exists and is NOT drifted."""
        mock_ct = MagicMock()
        mock_ct.list_landing_zones.return_value = {
            "landingZones": [
                {"arn": "arn:aws:controltower:us-east-1:111:landingzone/abc"}
            ]
        }
        mock_ct.get_landing_zone.return_value = {
            "landingZone": {
                "driftStatus": {"status": "IN_SYNC"},
                "version": "3.3",
                "latestAvailableVersion": "3.3",
            }
        }
        mock_client.return_value = mock_ct

        result = check_control_tower_not_drifted()
        assert result["status"] == "complete"

    @patch("src.checks.control_tower.boto3.client")
    def test_get_landing_zone_uses_home_region_from_arn(self, mock_client):
        """GetLandingZone must be called in the landing zone's home region.

        The home region is parsed from the ARN returned by ListLandingZones,
        which works from any region. Regression test for false errors when
        the assessment runs outside the Control Tower home region.
        """
        lz_arn = "arn:aws:controltower:us-west-2:111:landingzone/abc"
        mock_default = MagicMock()
        mock_default.list_landing_zones.return_value = {
            "landingZones": [{"arn": lz_arn}]
        }

        mock_regional = MagicMock()
        mock_regional.get_landing_zone.return_value = {
            "landingZone": {
                "driftStatus": {"status": "IN_SYNC"},
                "version": "4.0",
                "latestAvailableVersion": "4.0",
            }
        }

        def client_factory(service, **kwargs):
            if kwargs.get("region_name") == "us-west-2":
                return mock_regional
            return mock_default

        mock_client.side_effect = client_factory

        result = check_control_tower_not_drifted()
        assert result["status"] == "complete"
        mock_client.assert_any_call("controltower", region_name="us-west-2")
        mock_regional.get_landing_zone.assert_called_once_with(
            landingZoneIdentifier=lz_arn
        )
        # The default-region client must not be used for GetLandingZone
        mock_default.get_landing_zone.assert_not_called()

    @patch("src.checks.control_tower.boto3.client")
    def test_incomplete_drifted(self, mock_client):
        """Landing zone exists and IS drifted."""
        mock_ct = MagicMock()
        mock_ct.list_landing_zones.return_value = {
            "landingZones": [
                {"arn": "arn:aws:controltower:us-east-1:111:landingzone/abc"}
            ]
        }
        mock_ct.get_landing_zone.return_value = {
            "landingZone": {
                "driftStatus": {"status": "DRIFTED"},
                "version": "3.2",
                "latestAvailableVersion": "3.3",
            }
        }
        mock_client.return_value = mock_ct

        result = check_control_tower_not_drifted()
        assert result["status"] == "incomplete"

    @patch("src.checks.control_tower.boto3.client")
    def test_incomplete_no_landing_zone(self, mock_client):
        """No landing zone exists — incomplete."""
        mock_ct = MagicMock()
        mock_ct.list_landing_zones.return_value = {"landingZones": []}
        mock_client.return_value = mock_ct

        result = check_control_tower_not_drifted()
        assert result["status"] == "incomplete"

    @patch("src.checks.control_tower.boto3.client")
    def test_error(self, mock_client):
        """API error."""
        mock_ct = MagicMock()
        mock_ct.list_landing_zones.side_effect = Exception("Timeout")
        mock_client.return_value = mock_ct

        result = check_control_tower_not_drifted()
        assert result["status"] == "error"


# ============================================================================
# FR-5.3: Control Tower Latest Version
# ============================================================================


class TestCheckControlTowerLatestVersion:
    @patch("src.checks.control_tower.boto3.client")
    def test_complete_latest(self, mock_client):
        """Landing zone is on latest version."""
        mock_ct = MagicMock()
        mock_ct.list_landing_zones.return_value = {
            "landingZones": [
                {"arn": "arn:aws:controltower:us-east-1:111:landingzone/abc"}
            ]
        }
        mock_ct.get_landing_zone.return_value = {
            "landingZone": {
                "version": "3.3",
                "latestAvailableVersion": "3.3",
            }
        }
        mock_client.return_value = mock_ct

        result = check_control_tower_latest_version()
        assert result["status"] == "complete"

    @patch("src.checks.control_tower.boto3.client")
    def test_incomplete_outdated(self, mock_client):
        """Landing zone is NOT on latest version."""
        mock_ct = MagicMock()
        mock_ct.list_landing_zones.return_value = {
            "landingZones": [
                {"arn": "arn:aws:controltower:us-east-1:111:landingzone/abc"}
            ]
        }
        mock_ct.get_landing_zone.return_value = {
            "landingZone": {
                "version": "3.1",
                "latestAvailableVersion": "3.3",
            }
        }
        mock_client.return_value = mock_ct

        result = check_control_tower_latest_version()
        assert result["status"] == "incomplete"

    @patch("src.checks.control_tower.boto3.client")
    def test_incomplete_no_landing_zone(self, mock_client):
        """No landing zone — incomplete."""
        mock_ct = MagicMock()
        mock_ct.list_landing_zones.return_value = {"landingZones": []}
        mock_client.return_value = mock_ct

        result = check_control_tower_latest_version()
        assert result["status"] == "incomplete"

    @patch("src.checks.control_tower.boto3.client")
    def test_error(self, mock_client):
        """API error."""
        mock_ct = MagicMock()
        mock_ct.list_landing_zones.side_effect = Exception("Error")
        mock_client.return_value = mock_ct

        result = check_control_tower_latest_version()
        assert result["status"] == "error"


# ============================================================================
# Opt-in home regions
# ============================================================================


class TestOptInHomeRegion:
    OPT_IN_ARN = "arn:aws:controltower:eu-south-1:111:landingzone/abc"

    @staticmethod
    def _factory(by_region):
        def factory(service, region_name=None, **kwargs):
            return by_region[region_name]

        return factory

    @patch("src.checks.control_tower.boto3.client")
    def test_landing_zone_found_in_opted_in_home_region(self, mock_client):
        """A landing zone homed in an opt-in region is listed only from there."""
        default = MagicMock()
        default.list_landing_zones.return_value = {"landingZones": []}
        home = MagicMock()
        home.list_landing_zones.return_value = {
            "landingZones": [{"arn": self.OPT_IN_ARN}]
        }
        home.get_landing_zone.return_value = {
            "landingZone": {
                "driftStatus": {"status": "IN_SYNC"},
                "version": "4.0",
                "latestAvailableVersion": "4.0",
            }
        }
        mock_client.side_effect = self._factory({None: default, "eu-south-1": home})

        assert check_control_tower_deployed(["eu-south-1"])["status"] == "complete"
        assert check_control_tower_not_drifted(["eu-south-1"])["status"] == "complete"
        assert (
            check_control_tower_latest_version(["eu-south-1"])["status"] == "complete"
        )

    @patch("src.checks.control_tower.has_service_endpoint", return_value=False)
    @patch("src.checks.control_tower.boto3.client")
    def test_opted_in_region_without_endpoint_is_skipped(
        self, mock_client, mock_endpoint
    ):
        from botocore.exceptions import EndpointConnectionError

        default = MagicMock()
        default.list_landing_zones.return_value = {"landingZones": []}
        unsupported = MagicMock()
        unsupported.list_landing_zones.side_effect = EndpointConnectionError(
            endpoint_url="https://controltower.example-region-1.amazonaws.com"
        )
        mock_client.side_effect = self._factory(
            {None: default, "example-region-1": unsupported}
        )

        result = check_control_tower_deployed(["example-region-1"])
        assert result["status"] == "incomplete"
        mock_endpoint.assert_called_once_with("controltower", "example-region-1")

    @patch("src.checks.control_tower.has_service_endpoint", return_value=True)
    @patch("src.checks.control_tower.boto3.client")
    def test_connection_failure_in_supported_region_is_error(
        self, mock_client, mock_endpoint
    ):
        from botocore.exceptions import EndpointConnectionError

        default = MagicMock()
        default.list_landing_zones.return_value = {"landingZones": []}
        unreachable = MagicMock()
        unreachable.list_landing_zones.side_effect = EndpointConnectionError(
            endpoint_url="https://controltower.eu-south-1.amazonaws.com"
        )
        mock_client.side_effect = self._factory(
            {None: default, "eu-south-1": unreachable}
        )

        result = check_control_tower_deployed(["eu-south-1"])
        assert result["status"] == "error"

    @patch("src.checks.control_tower.boto3.client")
    def test_opted_in_region_access_denied_is_error(self, mock_client):
        default = MagicMock()
        default.list_landing_zones.return_value = {"landingZones": []}
        denied = MagicMock()
        denied.list_landing_zones.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "ListLandingZones",
        )
        mock_client.side_effect = self._factory({None: default, "eu-south-1": denied})

        result = check_control_tower_deployed(["eu-south-1"])
        assert result["status"] == "error"

    @patch("src.checks.control_tower.boto3.client")
    def test_early_region_error_does_not_hide_later_landing_zone(self, mock_client):
        default = MagicMock()
        default.list_landing_zones.return_value = {"landingZones": []}
        throttled = MagicMock()
        throttled.list_landing_zones.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "ListLandingZones",
        )
        home = MagicMock()
        home.list_landing_zones.return_value = {
            "landingZones": [{"arn": self.OPT_IN_ARN}]
        }
        mock_client.side_effect = self._factory(
            {None: default, "ap-east-1": throttled, "eu-south-1": home}
        )

        result = check_control_tower_deployed(["ap-east-1", "eu-south-1"])
        assert result["status"] == "complete"
        home.list_landing_zones.assert_called_once()

    @patch("src.checks.control_tower.boto3.client")
    def test_region_error_with_no_landing_zone_elsewhere_is_error(self, mock_client):
        default = MagicMock()
        default.list_landing_zones.return_value = {"landingZones": []}
        throttled = MagicMock()
        throttled.list_landing_zones.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "ListLandingZones",
        )
        empty = MagicMock()
        empty.list_landing_zones.return_value = {"landingZones": []}
        mock_client.side_effect = self._factory(
            {None: default, "ap-east-1": throttled, "eu-south-1": empty}
        )

        result = check_control_tower_deployed(["ap-east-1", "eu-south-1"])
        assert result["status"] == "error"
        assert "ThrottlingException" in result["error"]
        empty.list_landing_zones.assert_called_once()


class TestDriftStatusUnavailable:
    @patch("src.checks.control_tower.boto3.client")
    def test_missing_or_unknown_drift_status_is_error(self, mock_client):
        """An indeterminate drift status must not pass the check."""
        for landing_zone in (
            {},
            {"driftStatus": {}},
            {"driftStatus": {"status": "UNKNOWN"}},
        ):
            mock_ct = MagicMock()
            mock_ct.list_landing_zones.return_value = {
                "landingZones": [
                    {"arn": "arn:aws:controltower:us-east-1:111:landingzone/abc"}
                ]
            }
            mock_ct.get_landing_zone.return_value = {"landingZone": landing_zone}
            mock_client.return_value = mock_ct

            result = check_control_tower_not_drifted()
            assert result["status"] == "error"
            assert "drift status is unavailable" in result["error"]
