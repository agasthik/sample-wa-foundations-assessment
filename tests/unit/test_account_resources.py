"""Unit tests for src/checks/account_resources.py — FR-7 and FR-8."""

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from src.checks.account_resources import (
    check_cloudtrail_exists,
    check_cloudtrail_org_trail,
    check_config_delivery_channel,
    check_config_recorder,
    check_cur_report,
    check_no_ec2_instances,
    check_no_vpcs,
    check_stacksets_org_access,
    run_all,
)

MOCK_REGIONS = ["us-east-1", "eu-west-1"]


# ============================================================================
# FR-7.1: CloudTrail Trail Exists
# ============================================================================


class TestCheckCloudtrailExists:
    @patch("src.checks.account_resources.boto3.client")
    def test_complete(self, mock_client):
        """Trail found in a region."""
        mock_ct = MagicMock()
        mock_ct.describe_trails.return_value = {
            "trailList": [{"Name": "my-trail", "HomeRegion": "us-east-1"}]
        }
        mock_ct.get_trail_status.return_value = {"IsLogging": True}
        mock_client.return_value = mock_ct

        result = check_cloudtrail_exists(MOCK_REGIONS)
        assert result["status"] == "complete"

    @patch("src.checks.account_resources.boto3.client")
    def test_incomplete(self, mock_client):
        """No trails in any region."""
        mock_ct = MagicMock()
        mock_ct.describe_trails.return_value = {"trailList": []}
        mock_client.return_value = mock_ct

        result = check_cloudtrail_exists(MOCK_REGIONS)
        assert result["status"] == "incomplete"

    @patch("src.checks.account_resources.boto3.client")
    def test_error(self, mock_client):
        """Exception during scan."""
        mock_client.side_effect = Exception("Connection failed")

        result = check_cloudtrail_exists(MOCK_REGIONS)
        assert result["status"] == "error"


# ============================================================================
# FR-7.2: CloudTrail Org Trail
# ============================================================================


class TestCheckCloudtrailOrgTrail:
    @patch("src.checks.account_resources.boto3.client")
    def test_complete(self, mock_client):
        """Org trail found."""
        mock_ct = MagicMock()
        mock_ct.describe_trails.return_value = {
            "trailList": [{"Name": "org-trail", "IsOrganizationTrail": True}]
        }
        mock_ct.get_trail_status.return_value = {"IsLogging": True}
        mock_client.return_value = mock_ct

        result = check_cloudtrail_org_trail(MOCK_REGIONS)
        assert result["status"] == "complete"

    @patch("src.checks.account_resources.boto3.client")
    def test_incomplete(self, mock_client):
        """Trail exists but not org trail."""
        mock_ct = MagicMock()
        mock_ct.describe_trails.return_value = {
            "trailList": [{"Name": "my-trail", "IsOrganizationTrail": False}]
        }
        mock_client.return_value = mock_ct

        result = check_cloudtrail_org_trail(MOCK_REGIONS)
        assert result["status"] == "incomplete"

    @patch("src.checks.account_resources.boto3.client")
    def test_error(self, mock_client):
        mock_client.side_effect = Exception("Error")

        result = check_cloudtrail_org_trail(MOCK_REGIONS)
        assert result["status"] == "error"


# ============================================================================
# FR-7.3: Config Recorder
# ============================================================================


class TestCheckConfigRecorder:
    @patch("src.checks.account_resources.boto3.client")
    def test_complete(self, mock_client):
        mock_cfg = MagicMock()
        mock_cfg.describe_configuration_recorders.return_value = {
            "ConfigurationRecorders": [{"name": "default"}]
        }
        mock_cfg.describe_configuration_recorder_status.return_value = {
            "ConfigurationRecordersStatus": [{"name": "default", "recording": True}]
        }
        mock_client.return_value = mock_cfg

        result = check_config_recorder(MOCK_REGIONS)
        assert result["status"] == "complete"

    @patch("src.checks.account_resources.boto3.client")
    def test_incomplete(self, mock_client):
        mock_cfg = MagicMock()
        mock_cfg.describe_configuration_recorders.return_value = {
            "ConfigurationRecorders": []
        }
        mock_cfg.describe_configuration_recorder_status.return_value = {
            "ConfigurationRecordersStatus": []
        }
        mock_client.return_value = mock_cfg

        result = check_config_recorder(MOCK_REGIONS)
        assert result["status"] == "incomplete"

    @patch("src.checks.account_resources.boto3.client")
    def test_incomplete_when_recorder_is_stopped(self, mock_client):
        mock_cfg = MagicMock()
        mock_cfg.describe_configuration_recorders.return_value = {
            "ConfigurationRecorders": [{"name": "default"}]
        }
        mock_cfg.describe_configuration_recorder_status.return_value = {
            "ConfigurationRecordersStatus": [{"name": "default", "recording": False}]
        }
        mock_client.return_value = mock_cfg

        result = check_config_recorder(MOCK_REGIONS)
        assert result["status"] == "incomplete"

    @patch("src.checks.account_resources.boto3.client")
    def test_error(self, mock_client):
        mock_client.side_effect = Exception("Error")

        result = check_config_recorder(MOCK_REGIONS)
        assert result["status"] == "error"


# ============================================================================
# FR-7.4: Config Delivery Channel
# ============================================================================


class TestCheckConfigDeliveryChannel:
    @patch("src.checks.account_resources.boto3.client")
    def test_complete(self, mock_client):
        mock_cfg = MagicMock()
        mock_cfg.describe_delivery_channels.return_value = {
            "DeliveryChannels": [{"name": "default"}]
        }
        mock_cfg.describe_delivery_channel_status.return_value = {
            "DeliveryChannelsStatus": [
                {
                    "name": "default",
                    "configHistoryDeliveryInfo": {"lastStatus": "SUCCESS"},
                }
            ]
        }
        mock_client.return_value = mock_cfg

        result = check_config_delivery_channel(MOCK_REGIONS)
        assert result["status"] == "complete"

    @patch("src.checks.account_resources.boto3.client")
    def test_incomplete(self, mock_client):
        mock_cfg = MagicMock()
        mock_cfg.describe_delivery_channels.return_value = {"DeliveryChannels": []}
        mock_cfg.describe_delivery_channel_status.return_value = {
            "DeliveryChannelsStatus": []
        }
        mock_client.return_value = mock_cfg

        result = check_config_delivery_channel(MOCK_REGIONS)
        assert result["status"] == "incomplete"

    @patch("src.checks.account_resources.boto3.client")
    def test_incomplete_when_delivery_fails(self, mock_client):
        mock_cfg = MagicMock()
        mock_cfg.describe_delivery_channels.return_value = {
            "DeliveryChannels": [{"name": "default"}]
        }
        mock_cfg.describe_delivery_channel_status.return_value = {
            "DeliveryChannelsStatus": [
                {
                    "name": "default",
                    "configHistoryDeliveryInfo": {"lastStatus": "FAILURE"},
                }
            ]
        }
        mock_client.return_value = mock_cfg

        result = check_config_delivery_channel(MOCK_REGIONS)
        assert result["status"] == "incomplete"

    @patch("src.checks.account_resources.boto3.client")
    def test_error(self, mock_client):
        mock_client.side_effect = Exception("Error")

        result = check_config_delivery_channel(MOCK_REGIONS)
        assert result["status"] == "error"


# ============================================================================
# FR-7.5: No EC2 Instances
# ============================================================================


class TestCheckNoEc2Instances:
    @patch("src.checks.account_resources.boto3.client")
    def test_complete_no_instances(self, mock_client):
        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {"Reservations": []}
        mock_client.return_value = mock_ec2

        result = check_no_ec2_instances(MOCK_REGIONS)
        assert result["status"] == "complete"
        assert "assessed account" in result["description"]

    @patch("src.checks.account_resources.boto3.client")
    def test_incomplete_instances_exist(self, mock_client):
        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [{"Instances": [{"InstanceId": "i-123"}]}]
        }
        mock_client.return_value = mock_ec2

        result = check_no_ec2_instances(MOCK_REGIONS)
        assert result["status"] == "incomplete"

    @patch("src.checks.account_resources.boto3.client")
    def test_error(self, mock_client):
        mock_client.side_effect = Exception("Error")

        result = check_no_ec2_instances(MOCK_REGIONS)
        assert result["status"] == "error"


# ============================================================================
# FR-7.6: No VPCs
# ============================================================================


class TestCheckNoVpcs:
    @patch("src.checks.account_resources.boto3.client")
    def test_complete_no_vpcs(self, mock_client):
        mock_ec2 = MagicMock()
        mock_ec2.describe_vpcs.return_value = {"Vpcs": []}
        mock_client.return_value = mock_ec2

        result = check_no_vpcs(MOCK_REGIONS)
        assert result["status"] == "complete"
        assert "assessed account" in result["description"]

    @patch("src.checks.account_resources.boto3.client")
    def test_incomplete_vpcs_exist(self, mock_client):
        mock_ec2 = MagicMock()
        mock_ec2.describe_vpcs.return_value = {
            "Vpcs": [{"VpcId": "vpc-123", "IsDefault": True}]
        }
        mock_client.return_value = mock_ec2

        result = check_no_vpcs(MOCK_REGIONS)
        assert result["status"] == "incomplete"

    @patch("src.checks.account_resources.boto3.client")
    def test_error(self, mock_client):
        mock_client.side_effect = Exception("Error")

        result = check_no_vpcs(MOCK_REGIONS)
        assert result["status"] == "error"

    @patch("src.checks.account_resources.boto3.client")
    def test_access_denied_is_error(self, mock_client):
        mock_ec2 = MagicMock()
        mock_ec2.describe_vpcs.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "DescribeVpcs",
        )
        mock_client.return_value = mock_ec2

        result = check_no_vpcs(MOCK_REGIONS)
        assert result["status"] == "error"


# ============================================================================
# FR-7.7: CUR Report
# ============================================================================


def _cur_clients(
    legacy_reports=None, exports=None, legacy_error=None, exports_error=None
):
    """Build a boto3.client side_effect serving mock cur / bcm-data-exports clients."""
    mock_cur = MagicMock()
    if legacy_error:
        mock_cur.describe_report_definitions.side_effect = legacy_error
    else:
        mock_cur.describe_report_definitions.return_value = {
            "ReportDefinitions": legacy_reports or []
        }

    mock_exports = MagicMock()
    if exports_error:
        mock_exports.list_exports.side_effect = exports_error
    else:
        mock_exports.list_exports.return_value = {"Exports": exports or []}

    clients = {"cur": mock_cur, "bcm-data-exports": mock_exports}
    return lambda service, **kwargs: clients[service], mock_cur, mock_exports


class TestCheckCurReport:
    @patch("src.checks.account_resources.boto3.client")
    def test_complete_legacy_cur(self, mock_client):
        side_effect, _, mock_exports = _cur_clients(
            legacy_reports=[{"ReportName": "my-cur"}]
        )
        mock_client.side_effect = side_effect

        result = check_cur_report("us-east-1")
        assert result["status"] == "complete"
        # Data Exports API not needed when a legacy report exists
        mock_exports.list_exports.assert_not_called()

    @patch("src.checks.account_resources.boto3.client")
    def test_complete_data_exports(self, mock_client):
        """CUR 2.0 exports created via Data Exports count as configured."""
        side_effect, _, _ = _cur_clients(exports=[{"ExportName": "MyNewCUR-2025"}])
        mock_client.side_effect = side_effect

        result = check_cur_report("us-east-1")
        assert result["status"] == "complete"

    @patch("src.checks.account_resources.boto3.client")
    def test_complete_data_exports_when_legacy_errors(self, mock_client):
        """A legacy API failure doesn't hide a healthy Data Exports report."""
        side_effect, _, _ = _cur_clients(
            legacy_error=Exception("AccessDenied"),
            exports=[{"ExportName": "MyNewCUR-2025"}],
        )
        mock_client.side_effect = side_effect

        result = check_cur_report("us-east-1")
        assert result["status"] == "complete"

    @patch("src.checks.account_resources.boto3.client")
    def test_complete_legacy_cur_on_later_page(self, mock_client):
        """A legacy report on a later page is found by following NextToken."""
        side_effect, mock_cur, _ = _cur_clients()
        mock_cur.describe_report_definitions.return_value = None
        mock_cur.describe_report_definitions.side_effect = [
            {"ReportDefinitions": [], "NextToken": "page-2"},
            {"ReportDefinitions": [{"ReportName": "my-cur"}]},
        ]
        mock_client.side_effect = side_effect

        result = check_cur_report("us-east-1")

        assert result["status"] == "complete"
        calls = mock_cur.describe_report_definitions.call_args_list
        assert [call.kwargs for call in calls] == [{}, {"NextToken": "page-2"}]

    @patch("src.checks.account_resources.boto3.client")
    def test_complete_data_exports_on_later_page(self, mock_client):
        """A Data Exports report on a later page is found via NextToken."""
        side_effect, _, mock_exports = _cur_clients()
        mock_exports.list_exports.return_value = None
        mock_exports.list_exports.side_effect = [
            {"Exports": [], "NextToken": "page-2"},
            {"Exports": [{"ExportName": "MyNewCUR-2025"}]},
        ]
        mock_client.side_effect = side_effect

        result = check_cur_report("us-east-1")

        assert result["status"] == "complete"
        calls = mock_exports.list_exports.call_args_list
        assert [call.kwargs for call in calls] == [{}, {"NextToken": "page-2"}]

    @patch("src.checks.account_resources.boto3.client")
    def test_incomplete_after_all_pages_empty(self, mock_client):
        """Empty paginated results terminate and resolve to incomplete."""
        side_effect, mock_cur, mock_exports = _cur_clients()
        mock_cur.describe_report_definitions.side_effect = [
            {"ReportDefinitions": [], "NextToken": "cur-2"},
            {"ReportDefinitions": []},
        ]
        mock_exports.list_exports.side_effect = [
            {"Exports": [], "NextToken": "exports-2"},
            {"Exports": []},
        ]
        mock_client.side_effect = side_effect

        result = check_cur_report("us-east-1")

        assert result["status"] == "incomplete"
        assert mock_cur.describe_report_definitions.call_count == 2
        assert mock_exports.list_exports.call_count == 2

    @patch("src.checks.account_resources.boto3.client")
    def test_incomplete(self, mock_client):
        side_effect, _, _ = _cur_clients()
        mock_client.side_effect = side_effect

        result = check_cur_report("us-east-1")
        assert result["status"] == "incomplete"

    @patch("src.checks.account_resources.boto3.client")
    def test_error_when_both_apis_fail(self, mock_client):
        side_effect, _, _ = _cur_clients(
            legacy_error=Exception("Error1"), exports_error=Exception("Error2")
        )
        mock_client.side_effect = side_effect

        result = check_cur_report("us-east-1")
        assert result["status"] == "error"
        assert "cur:" in result["error"]
        assert "bcm-data-exports:" in result["error"]

    @patch("src.checks.account_resources.boto3.client")
    def test_error_when_empty_legacy_and_exports_fails(self, mock_client):
        """Empty legacy + Data Exports failure → error, not a false incomplete."""
        side_effect, _, _ = _cur_clients(exports_error=Exception("AccessDenied"))
        mock_client.side_effect = side_effect

        result = check_cur_report("us-east-1")
        assert result["status"] == "error"

    @patch("src.checks.account_resources.boto3.client")
    def test_govcloud_skips_data_exports(self, mock_client):
        """GovCloud (D5): Data Exports path is skipped; no legacy report → incomplete.

        bcm-data-exports is not offered in the gov partition, so the check must
        not attempt to create that client, and the absence of a legacy CUR must
        resolve to 'incomplete' rather than 'error'.
        """
        side_effect, _, mock_exports = _cur_clients()  # no legacy reports
        mock_client.side_effect = side_effect

        result = check_cur_report("us-gov-west-1")

        assert result["status"] == "incomplete"
        assert "error" not in result
        # Data Exports API must never be touched in the gov partition.
        mock_exports.list_exports.assert_not_called()
        assert not any(
            call.args and call.args[0] == "bcm-data-exports"
            for call in mock_client.call_args_list
        )

    @patch("src.checks.account_resources.boto3.client")
    def test_china_skips_data_exports(self, mock_client):
        """China (D6): Data Exports path is skipped; no legacy report → incomplete."""
        side_effect, _, mock_exports = _cur_clients()  # no legacy reports
        mock_client.side_effect = side_effect

        result = check_cur_report("cn-north-1")

        assert result["status"] == "incomplete"
        assert "error" not in result
        mock_exports.list_exports.assert_not_called()
        assert not any(
            call.args and call.args[0] == "bcm-data-exports"
            for call in mock_client.call_args_list
        )


# ============================================================================
# FR-8.1: StackSets Org Access
# ============================================================================


class TestCheckStacksetsOrgAccess:
    @patch("src.checks.account_resources.boto3.client")
    def test_complete(self, mock_client):
        mock_cfn = MagicMock()
        mock_cfn.describe_organizations_access.return_value = {"Status": "ENABLED"}
        mock_client.return_value = mock_cfn

        result = check_stacksets_org_access()
        assert result["status"] == "complete"

    @patch("src.checks.account_resources.boto3.client")
    def test_incomplete(self, mock_client):
        mock_cfn = MagicMock()
        mock_cfn.describe_organizations_access.return_value = {"Status": "DISABLED"}
        mock_client.return_value = mock_cfn

        result = check_stacksets_org_access()
        assert result["status"] == "incomplete"

    @patch("src.checks.account_resources.boto3.client")
    def test_error(self, mock_client):
        mock_cfn = MagicMock()
        mock_cfn.describe_organizations_access.side_effect = ClientError(
            {
                "Error": {
                    "Code": "OrganizationAccessDeniedException",
                    "Message": "No org",
                }
            },
            "DescribeOrganizationsAccess",
        )
        mock_client.return_value = mock_cfn

        result = check_stacksets_org_access()
        assert result["status"] == "error"


# ============================================================================
# run_all
# ============================================================================


class TestRunAll:
    @patch("src.checks.account_resources.boto3.client")
    def test_management_returns_8_checks(self, mock_client):
        """Management account: all 8 checks run."""
        mock_svc = MagicMock()
        mock_svc.describe_trails.return_value = {"trailList": []}
        mock_svc.describe_configuration_recorders.return_value = {
            "ConfigurationRecorders": []
        }
        mock_svc.describe_configuration_recorder_status.return_value = {
            "ConfigurationRecordersStatus": []
        }
        mock_svc.describe_delivery_channels.return_value = {"DeliveryChannels": []}
        mock_svc.describe_delivery_channel_status.return_value = {
            "DeliveryChannelsStatus": []
        }
        mock_svc.describe_instances.return_value = {"Reservations": []}
        mock_svc.describe_vpcs.return_value = {"Vpcs": []}
        mock_svc.describe_report_definitions.return_value = {"ReportDefinitions": []}
        mock_svc.describe_organizations_access.return_value = {"Status": "DISABLED"}
        mock_client.return_value = mock_svc

        results = run_all(MOCK_REGIONS, is_management_account=True)
        assert len(results) == 8

    @patch("src.checks.account_resources.boto3.client")
    def test_non_management_returns_6_checks(self, mock_client):
        """Non-management account: only FR-7.1 through FR-7.6 run."""
        mock_svc = MagicMock()
        mock_svc.describe_trails.return_value = {"trailList": []}
        mock_svc.describe_configuration_recorders.return_value = {
            "ConfigurationRecorders": []
        }
        mock_svc.describe_delivery_channels.return_value = {"DeliveryChannels": []}
        mock_svc.describe_instances.return_value = {"Reservations": []}
        mock_svc.describe_vpcs.return_value = {"Vpcs": []}
        mock_client.return_value = mock_svc

        results = run_all(MOCK_REGIONS, is_management_account=False)
        assert len(results) == 6


# ============================================================================
# Partial region failures (SCP region deny, throttling)
# ============================================================================


def _region_factory(by_region):
    def factory(service, region_name=None, **kwargs):
        return by_region[region_name]

    return factory


def _denied(operation):
    return ClientError(
        {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "explicit deny in a service control policy",
            }
        },
        operation,
    )


class TestPartialRegionFailures:
    REGIONS = ("ap-south-1", "eu-west-1", "us-east-1")

    def _cloudtrail(self, trails_in_us_east_1):
        denied = MagicMock()
        denied.describe_trails.side_effect = _denied("DescribeTrails")
        empty = MagicMock()
        empty.describe_trails.return_value = {"trailList": []}
        home = MagicMock()
        home.describe_trails.return_value = {"trailList": trails_in_us_east_1}
        home.get_trail_status.return_value = {"IsLogging": True}
        return _region_factory(
            {"ap-south-1": denied, "eu-west-1": empty, "us-east-1": home}
        )

    @patch("src.checks.account_resources.boto3.client")
    def test_trail_found_despite_denied_region(self, mock_client):
        """A trail in one region wins over a denied, earlier-sorted region."""
        mock_client.side_effect = self._cloudtrail(
            [{"Name": "org", "IsOrganizationTrail": True}]
        )

        assert check_cloudtrail_exists(self.REGIONS)["status"] == "complete"
        result = check_cloudtrail_org_trail(self.REGIONS)
        assert result["status"] == "complete"
        assert "error" not in result

    @patch("src.checks.account_resources.boto3.client")
    def test_not_found_with_denied_region_is_error(self, mock_client):
        """Absence cannot be concluded when a region could not be inspected."""
        mock_client.side_effect = self._cloudtrail([])

        result = check_cloudtrail_exists(self.REGIONS)
        assert result["status"] == "error"
        assert "Could not inspect 1 region(s): ap-south-1" in result["error"]

    @patch("src.checks.account_resources.boto3.client")
    def test_config_recorder_found_despite_denied_region(self, mock_client):
        denied = MagicMock()
        denied.describe_configuration_recorders.side_effect = _denied(
            "DescribeConfigurationRecorders"
        )
        active = MagicMock()
        active.describe_configuration_recorders.return_value = {
            "ConfigurationRecorders": [{"name": "default"}]
        }
        active.describe_configuration_recorder_status.return_value = {
            "ConfigurationRecordersStatus": [{"recording": True}]
        }
        mock_client.side_effect = _region_factory(
            {"ap-south-1": denied, "eu-west-1": active, "us-east-1": active}
        )

        assert check_config_recorder(self.REGIONS)["status"] == "complete"

    @patch("src.checks.account_resources.boto3.client")
    def test_vpc_found_despite_denied_region_is_incomplete(self, mock_client):
        denied = MagicMock()
        denied.describe_vpcs.side_effect = _denied("DescribeVpcs")
        with_vpc = MagicMock()
        with_vpc.describe_vpcs.return_value = {"Vpcs": [{"VpcId": "vpc-1"}]}
        empty = MagicMock()
        empty.describe_vpcs.return_value = {"Vpcs": []}
        mock_client.side_effect = _region_factory(
            {"ap-south-1": denied, "eu-west-1": empty, "us-east-1": with_vpc}
        )

        assert check_no_vpcs(self.REGIONS)["status"] == "incomplete"

    @patch("src.checks.account_resources.boto3.client")
    def test_no_instances_with_denied_region_is_error(self, mock_client):
        denied = MagicMock()
        denied.describe_instances.side_effect = _denied("DescribeInstances")
        empty = MagicMock()
        empty.describe_instances.return_value = {"Reservations": []}
        mock_client.side_effect = _region_factory(
            {"ap-south-1": denied, "eu-west-1": empty, "us-east-1": empty}
        )

        result = check_no_ec2_instances(self.REGIONS)
        assert result["status"] == "error"
        assert list(result) == [
            "check",
            "description",
            "status",
            "required",
            "weight",
            "loe",
            "remediationLink",
            "error",
        ]

    @patch("src.checks.account_resources.boto3.client")
    def test_clients_created_in_calling_thread(self, mock_client):
        """boto3.client() must not be called from worker threads."""
        import threading

        main_thread = threading.get_ident()
        creating_threads = set()

        def factory(service, region_name=None, **kwargs):
            creating_threads.add(threading.get_ident())
            client = MagicMock()
            client.describe_trails.return_value = {"trailList": []}
            return client

        mock_client.side_effect = factory

        check_cloudtrail_exists(self.REGIONS)
        assert creating_threads == {main_thread}

    @patch("src.checks.account_resources.boto3.client")
    def test_client_creation_failure_does_not_stop_other_regions(self, mock_client):
        """A region whose client cannot be built is an error, not an abort."""
        home = MagicMock()
        home.describe_trails.return_value = {"trailList": [{"Name": "t"}]}
        home.get_trail_status.return_value = {"IsLogging": True}
        empty = MagicMock()
        empty.describe_trails.return_value = {"trailList": []}

        def factory(service, region_name=None, **kwargs):
            if region_name == "ap-south-1":
                raise ValueError("cannot build client")
            return home if region_name == "us-east-1" else empty

        mock_client.side_effect = factory

        assert check_cloudtrail_exists(self.REGIONS)["status"] == "complete"
        home.describe_trails.assert_called_once()

        home.describe_trails.return_value = {"trailList": []}
        result = check_cloudtrail_exists(self.REGIONS)
        assert result["status"] == "error"
        assert (
            "Could not inspect 1 region(s): ap-south-1: cannot build client"
            in result["error"]
        )


# ============================================================================
# Trail logging, active instances
# ============================================================================


class TestTrailLoggingAndInstanceState:
    @patch("src.checks.account_resources.boto3.client")
    def test_stopped_trails_do_not_count(self, mock_client):
        mock_ct = MagicMock()
        mock_ct.describe_trails.return_value = {
            "trailList": [
                {
                    "Name": "org",
                    "TrailARN": "arn:aws:cloudtrail:us-east-1:111111111111:trail/org",
                    "IsOrganizationTrail": True,
                }
            ]
        }
        mock_ct.get_trail_status.return_value = {"IsLogging": False}
        mock_client.return_value = mock_ct

        assert check_cloudtrail_exists(MOCK_REGIONS)["status"] == "incomplete"
        assert check_cloudtrail_org_trail(MOCK_REGIONS)["status"] == "incomplete"
        mock_ct.get_trail_status.assert_called_with(
            Name="arn:aws:cloudtrail:us-east-1:111111111111:trail/org"
        )

    @patch("src.checks.account_resources.boto3.client")
    def test_trail_status_error_is_error(self, mock_client):
        mock_ct = MagicMock()
        mock_ct.describe_trails.return_value = {"trailList": [{"Name": "t"}]}
        mock_ct.get_trail_status.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "GetTrailStatus",
        )
        mock_client.return_value = mock_ct

        assert check_cloudtrail_exists(MOCK_REGIONS)["status"] == "error"

    @patch("src.checks.account_resources.boto3.client")
    def test_unreadable_trail_does_not_hide_logging_trail(self, mock_client):
        mock_ct = MagicMock()
        mock_ct.describe_trails.return_value = {
            "trailList": [
                {"Name": "denied", "IsOrganizationTrail": True},
                {"Name": "logging", "IsOrganizationTrail": True},
            ]
        }

        def trail_status(Name):
            if Name == "denied":
                raise _denied("GetTrailStatus")
            return {"IsLogging": True}

        mock_ct.get_trail_status.side_effect = trail_status
        mock_client.return_value = mock_ct

        assert check_cloudtrail_exists(MOCK_REGIONS)["status"] == "complete"
        assert check_cloudtrail_org_trail(MOCK_REGIONS)["status"] == "complete"

    @patch("src.checks.account_resources.boto3.client")
    def test_unreadable_and_stopped_trails_are_error(self, mock_client):
        mock_ct = MagicMock()
        mock_ct.describe_trails.return_value = {
            "trailList": [{"Name": "stopped"}, {"Name": "denied"}]
        }

        def trail_status(Name):
            if Name == "denied":
                raise _denied("GetTrailStatus")
            return {"IsLogging": False}

        mock_ct.get_trail_status.side_effect = trail_status
        mock_client.return_value = mock_ct

        assert check_cloudtrail_exists(MOCK_REGIONS)["status"] == "error"

    @patch("src.checks.account_resources.boto3.client")
    def test_instance_check_ignores_terminated_instances(self, mock_client):
        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {"Reservations": []}
        mock_client.return_value = mock_ec2

        assert check_no_ec2_instances(MOCK_REGIONS)["status"] == "complete"
        _, kwargs = mock_ec2.describe_instances.call_args
        assert kwargs["Filters"] == [
            {
                "Name": "instance-state-name",
                "Values": ["pending", "running", "stopping", "stopped"],
            }
        ]
