"""Per-Account Resource Checks (FR-7) and CloudFormation StackSets (FR-8).

These checks run in ALL modes (management, member, standalone).
FR-7 checks use concurrent region scanning for performance (NFR-2.2).
FR-8 only runs from management account.
"""

import boto3
from botocore.exceptions import ClientError
from concurrent.futures import ThreadPoolExecutor, as_completed


_REGION_UNAVAILABLE_CODES = {
    "InvalidRegion",
    "OptInRequired",
}


def _is_region_unavailable_error(error):
    """Return True when AWS reports that a region is not enabled."""
    code = error.response.get("Error", {}).get("Code", "")
    message = error.response.get("Error", {}).get("Message", "").lower()
    return (
        code in _REGION_UNAVAILABLE_CODES
        or "opt-in" in message
        or "not enabled" in message
    )


def _check_regions_for_resource(
    regions, service_name, api_method, result_key, check_any=True
):
    """Helper: scan multiple regions concurrently for a resource.

    Args:
        regions: list of region names
        service_name: boto3 service name (e.g., 'cloudtrail')
        api_method: method name to call (e.g., 'describe_trails')
        result_key: key in response containing the list (e.g., 'trailList')
        check_any: if True, return True if resource found in any region;
                   if False, return True if resource NOT found in any region

    Returns:
        bool: depends on check_any flag
    """

    def check_region(region):
        try:
            client = boto3.client(service_name, region_name=region)
            method = getattr(client, api_method)
            resp = method()
            items = resp.get(result_key, [])
            return len(items) > 0
        except ClientError as e:
            if _is_region_unavailable_error(e):
                return False
            raise

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(check_region, r): r for r in regions}
        for future in as_completed(futures):
            found = future.result()
            if check_any and found:
                return True
            if not check_any and found:
                return False

    # If check_any: not found anywhere → False
    # If not check_any: not found anywhere → True (good)
    return not check_any


def check_cloudtrail_exists(regions):
    """FR-7.1: Verify at least one CloudTrail trail exists."""
    try:
        found = _check_regions_for_resource(
            regions, "cloudtrail", "describe_trails", "trailList", check_any=True
        )
        return {
            "check": "CloudTrail trail exists",
            "description": "At least one CloudTrail trail should be configured for audit logging.",
            "status": "complete" if found else "incomplete",
            "required": True,
            "weight": 6,
            "loe": 3,
            "remediationLink": "https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-create-a-trail-using-the-console-first-time.html",
        }
    except Exception as e:
        return {
            "check": "CloudTrail trail exists",
            "description": "At least one CloudTrail trail should be configured for audit logging.",
            "status": "error",
            "required": True,
            "weight": 6,
            "loe": 3,
            "remediationLink": "https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-create-a-trail-using-the-console-first-time.html",
            "error": str(e),
        }


def check_cloudtrail_org_trail(regions):
    """FR-7.2: Verify at least one CloudTrail org trail exists."""
    try:

        def check_region(region):
            try:
                client = boto3.client("cloudtrail", region_name=region)
                resp = client.describe_trails()
                trails = resp.get("trailList", [])
                return any(t.get("IsOrganizationTrail", False) for t in trails)
            except ClientError as e:
                if _is_region_unavailable_error(e):
                    return False
                raise

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(check_region, r) for r in regions]
            found = any(f.result() for f in futures)

        return {
            "check": "CloudTrail organization trail",
            "description": "An organization trail should be configured for centralized audit logging across all accounts.",
            "status": "complete" if found else "incomplete",
            "required": True,
            "weight": 6,
            "loe": 1,
            "remediationLink": "https://docs.aws.amazon.com/awscloudtrail/latest/userguide/creating-trail-organization.html",
        }
    except Exception as e:
        return {
            "check": "CloudTrail organization trail",
            "description": "An organization trail should be configured for centralized audit logging across all accounts.",
            "status": "error",
            "required": True,
            "weight": 6,
            "loe": 1,
            "remediationLink": "https://docs.aws.amazon.com/awscloudtrail/latest/userguide/creating-trail-organization.html",
            "error": str(e),
        }


def check_config_recorder(regions):
    """FR-7.3: Verify AWS Config recorder is active in at least one region."""
    try:

        def check_region(region):
            try:
                client = boto3.client("config", region_name=region)
                recorders = client.describe_configuration_recorders().get(
                    "ConfigurationRecorders", []
                )
                if not recorders:
                    return False
                statuses = client.describe_configuration_recorder_status().get(
                    "ConfigurationRecordersStatus", []
                )
                return any(status.get("recording") is True for status in statuses)
            except ClientError as e:
                if _is_region_unavailable_error(e):
                    return False
                raise

        with ThreadPoolExecutor(max_workers=10) as executor:
            found = any(
                future.result()
                for future in (
                    executor.submit(check_region, region) for region in regions
                )
            )

        return {
            "check": "AWS Config recorder active",
            "description": "AWS Config recorder should be active for resource configuration tracking.",
            "status": "complete" if found else "incomplete",
            "required": True,
            "weight": 6,
            "loe": 2,
            "remediationLink": "https://docs.aws.amazon.com/config/latest/developerguide/gs-console.html",
        }
    except Exception as e:
        return {
            "check": "AWS Config recorder active",
            "description": "AWS Config recorder should be active for resource configuration tracking.",
            "status": "error",
            "required": True,
            "weight": 6,
            "loe": 2,
            "remediationLink": "https://docs.aws.amazon.com/config/latest/developerguide/gs-console.html",
            "error": str(e),
        }


def check_config_delivery_channel(regions):
    """FR-7.4: Verify an AWS Config delivery channel is delivering successfully."""
    try:

        def check_region(region):
            try:
                client = boto3.client("config", region_name=region)
                channels = client.describe_delivery_channels().get(
                    "DeliveryChannels", []
                )
                if not channels:
                    return False
                statuses = client.describe_delivery_channel_status().get(
                    "DeliveryChannelsStatus", []
                )

                # DescribeDeliveryChannelStatus returns lastStatus uppercased
                # (SUCCESS / FAILURE / NOT_APPLICABLE). Normalise before
                # comparing so the check cannot silently never match.
                def delivered(info):
                    return (info or {}).get("lastStatus", "").upper() == "SUCCESS"

                return any(
                    delivered(status.get("configHistoryDeliveryInfo"))
                    or delivered(status.get("configSnapshotDeliveryInfo"))
                    for status in statuses
                )
            except ClientError as e:
                if _is_region_unavailable_error(e):
                    return False
                raise

        with ThreadPoolExecutor(max_workers=10) as executor:
            found = any(
                future.result()
                for future in (
                    executor.submit(check_region, region) for region in regions
                )
            )

        return {
            "check": "AWS Config delivery channel active",
            "description": "AWS Config delivery channel should be configured for configuration change delivery.",
            "status": "complete" if found else "incomplete",
            "required": True,
            "weight": 6,
            "loe": 2,
            "remediationLink": "https://docs.aws.amazon.com/config/latest/developerguide/manage-delivery-channel.html",
        }
    except Exception as e:
        return {
            "check": "AWS Config delivery channel active",
            "description": "AWS Config delivery channel should be configured for configuration change delivery.",
            "status": "error",
            "required": True,
            "weight": 6,
            "loe": 2,
            "remediationLink": "https://docs.aws.amazon.com/config/latest/developerguide/manage-delivery-channel.html",
            "error": str(e),
        }


def check_no_ec2_instances(regions):
    """FR-7.5: Verify no EC2 instances exist in this account."""
    try:

        def check_region(region):
            try:
                client = boto3.client("ec2", region_name=region)
                resp = client.describe_instances()
                reservations = resp.get("Reservations", [])
                return len(reservations) > 0
            except ClientError as e:
                if _is_region_unavailable_error(e):
                    return False
                raise

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(check_region, r) for r in regions]
            any_instances = any(f.result() for f in futures)

        return {
            "check": "No EC2 instances in account",
            "description": "Reports whether the assessed account contains EC2 instances; centralized management accounts should keep workloads elsewhere.",
            "status": "complete" if not any_instances else "incomplete",
            "required": False,
            "weight": 4,
            "loe": 1,
            "remediationLink": "https://docs.aws.amazon.com/whitepapers/latest/organizing-your-aws-environment/aws-organizations.html",
        }
    except Exception as e:
        return {
            "check": "No EC2 instances in account",
            "description": "Reports whether the assessed account contains EC2 instances; centralized management accounts should keep workloads elsewhere.",
            "status": "error",
            "required": False,
            "weight": 4,
            "loe": 1,
            "remediationLink": "https://docs.aws.amazon.com/whitepapers/latest/organizing-your-aws-environment/aws-organizations.html",
            "error": str(e),
        }


def check_no_vpcs(regions):
    """FR-7.6: Verify no VPCs exist in this account (including defaults)."""
    try:

        def check_region(region):
            try:
                client = boto3.client("ec2", region_name=region)
                resp = client.describe_vpcs()
                vpcs = resp.get("Vpcs", [])
                return len(vpcs) > 0
            except ClientError as e:
                if _is_region_unavailable_error(e):
                    return False
                raise

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(check_region, r) for r in regions]
            any_vpcs = any(f.result() for f in futures)

        return {
            "check": "No VPCs in account",
            "description": "Reports whether the assessed account contains VPCs; centralized management accounts should keep workloads elsewhere.",
            "status": "complete" if not any_vpcs else "incomplete",
            "required": False,
            "weight": 4,
            "loe": 1,
            "remediationLink": "https://docs.aws.amazon.com/whitepapers/latest/organizing-your-aws-environment/aws-organizations.html",
        }
    except Exception as e:
        return {
            "check": "No VPCs in account",
            "description": "Reports whether the assessed account contains VPCs; centralized management accounts should keep workloads elsewhere.",
            "status": "error",
            "required": False,
            "weight": 4,
            "loe": 1,
            "remediationLink": "https://docs.aws.amazon.com/whitepapers/latest/organizing-your-aws-environment/aws-organizations.html",
            "error": str(e),
        }


def check_cur_report(default_region="us-east-1"):
    """FR-7.7: Verify at least one Cost and Usage Report is defined.

    Checks both APIs a report can live behind:
    - Legacy CUR (cur:DescribeReportDefinitions) — reports created via the
      legacy "Cost & Usage Reports" console page
    - BCM Data Exports (bcm-data-exports:ListExports) — CUR 2.0 exports
      created via the newer "Data Exports" console page

    Only runs from management account. Legacy CUR is queried in the
    partition default region. Data Exports is queried only in the
    commercial partition, where AWS provides the service.
    """
    errors = []
    has_report = False

    try:
        client = boto3.client("cur", region_name=default_region)
        while True:
            resp = client.describe_report_definitions()
            has_report = has_report or bool(resp.get("ReportDefinitions", []))
            if has_report or not resp.get("NextToken"):
                break
            resp = client.describe_report_definitions(NextToken=resp["NextToken"])
    except Exception as e:
        errors.append(f"cur: {e}")

    if not has_report and not default_region.startswith(("us-gov-", "cn-")):
        try:
            client = boto3.client("bcm-data-exports", region_name=default_region)
            while True:
                resp = client.list_exports()
                has_report = has_report or bool(resp.get("Exports", []))
                if has_report or not resp.get("NextToken"):
                    break
                resp = client.list_exports(NextToken=resp["NextToken"])
        except Exception as e:
            errors.append(f"bcm-data-exports: {e}")

    result = {
        "check": "Cost and Usage Report configured",
        "description": "A Cost and Usage Report should be configured for cost visibility.",
        "status": "complete" if has_report else "incomplete",
        "required": False,
        "weight": 4,
        "loe": 1,
        "remediationLink": "https://docs.aws.amazon.com/cur/latest/userguide/cur-create.html",
    }
    # Only report an error state if no report was found AND at least one
    # API call failed — a failure leaves us unable to say "incomplete".
    if not has_report and errors:
        result["status"] = "error"
        result["error"] = "; ".join(errors)
    return result


def check_stacksets_org_access():
    """FR-8.1: Verify CloudFormation StackSets organization access is enabled."""
    try:
        client = boto3.client("cloudformation")
        resp = client.describe_organizations_access()
        status = resp.get("Status", "")
        enabled = status == "ENABLED"

        return {
            "check": "StackSets organization access enabled",
            "description": "CloudFormation StackSets should have organization access enabled for cross-account deployments.",
            "status": "complete" if enabled else "incomplete",
            "required": False,
            "weight": 5,
            "loe": 1,
            "remediationLink": "https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-activate-trusted-access.html",
        }
    except Exception as e:
        return {
            "check": "StackSets organization access enabled",
            "description": "CloudFormation StackSets should have organization access enabled for cross-account deployments.",
            "status": "error",
            "required": False,
            "weight": 5,
            "loe": 1,
            "remediationLink": "https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-activate-trusted-access.html",
            "error": str(e),
        }


def run_all(regions, is_management_account=True, default_region="us-east-1"):
    """Run all per-account resource checks.

    FR-7.1 through FR-7.6 run in ALL modes.
    FR-7.7 and FR-8.1 run only from management account.
    """
    results = [
        check_cloudtrail_exists(regions),
        check_cloudtrail_org_trail(regions),
        check_config_recorder(regions),
        check_config_delivery_channel(regions),
        check_no_ec2_instances(regions),
        check_no_vpcs(regions),
    ]

    if is_management_account:
        results.append(check_cur_report(default_region))
        results.append(check_stacksets_org_access())

    return results
