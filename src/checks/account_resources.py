"""Per-Account Resource Checks (FR-7) and CloudFormation StackSets (FR-8).

These checks run in ALL modes (management, member, standalone).
FR-7 checks use concurrent region scanning for performance (NFR-2.2).
FR-8 only runs from management account.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import boto3
from botocore.exceptions import ClientError

_MAX_WORKERS = 10

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


@dataclass
class RegionScan:
    """Per-region outcome of a concurrent scan.

    found: regions where the probe matched
    errors: region -> error message for regions that could not be inspected
    Regions that are absent from both were inspected and did not match, or
    reported themselves as unavailable.
    """

    found: list = field(default_factory=list)
    errors: dict = field(default_factory=dict)


def _scan_regions(regions, service_name, probe):
    """Run ``probe(client)`` concurrently in every region.

    Clients are created up front in the calling thread because
    ``boto3.client()`` uses the shared default session, which is not safe to
    use from worker threads. Botocore clients themselves are thread-safe.

    Every region is awaited, so one region's failure never hides a match in
    another region and the outcome does not depend on completion order. A
    region whose client cannot be created is recorded as an error and the
    remaining regions are still probed.
    """
    scan = RegionScan()
    clients = {}
    for region in regions:
        try:
            clients[region] = boto3.client(service_name, region_name=region)
        except Exception as e:
            scan.errors[region] = str(e)

    def run(region):
        try:
            return bool(probe(clients[region]))
        except ClientError as e:
            if _is_region_unavailable_error(e):
                return False
            raise

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {executor.submit(run, region): region for region in clients}
        for future in as_completed(futures):
            region = futures[future]
            try:
                if future.result():
                    scan.found.append(region)
            except Exception as e:
                scan.errors[region] = str(e)

    scan.found.sort()
    scan.errors = dict(sorted(scan.errors.items()))
    return scan


def _regional_result(base, scan, want_present):
    """Build a check result from a region scan.

    want_present=True: a match in any region is complete; otherwise any
    region that could not be inspected makes the result an error.
    want_present=False: a match in any region is incomplete; otherwise any
    region that could not be inspected makes the result an error.
    """
    if scan.found:
        return _with_status(base, "complete" if want_present else "incomplete")
    if scan.errors:
        details = "; ".join(
            f"{region}: {message}" for region, message in scan.errors.items()
        )
        return _with_status(
            base,
            "error",
            f"Could not inspect {len(scan.errors)} region(s): {details}",
        )
    return _with_status(base, "incomplete" if want_present else "complete")


def _with_status(base, status, error=None):
    """Return the check contract dict with status in its usual position."""
    result = {"check": base["check"], "description": base["description"]}
    result["status"] = status
    result.update({k: v for k, v in base.items() if k not in result})
    if error is not None:
        result["error"] = error
    return result


def _regional_check(base, regions, service_name, probe, want_present):
    """Scan regions and return a check result, converting failures to error."""
    try:
        scan = _scan_regions(regions, service_name, probe)
        return _regional_result(base, scan, want_present)
    except Exception as e:
        return _with_status(base, "error", str(e))


def _is_logging(client, trail):
    """Return True if the trail is currently logging.

    GetTrailStatus requires the trail ARN for shadow trails and for
    organization trails viewed from a member account.
    """
    name = trail.get("TrailARN") or trail.get("Name")
    return client.get_trail_status(Name=name).get("IsLogging") is True


def _any_logging(client, trails):
    """Return True if any trail is logging.

    Each trail is checked individually so one unreadable trail does not hide
    another that is logging. The first error is raised only when no trail is
    confirmed to be logging.
    """
    first_error = None
    for trail in trails:
        try:
            if _is_logging(client, trail):
                return True
        except ClientError as e:
            if first_error is None:
                first_error = e
    if first_error is not None:
        raise first_error
    return False


def _has_trail(client):
    trails = client.describe_trails().get("trailList", [])
    return _any_logging(client, trails)


def _has_org_trail(client):
    trails = client.describe_trails().get("trailList", [])
    return _any_logging(
        client, [t for t in trails if t.get("IsOrganizationTrail", False)]
    )


def _has_active_recorder(client):
    recorders = client.describe_configuration_recorders().get(
        "ConfigurationRecorders", []
    )
    if not recorders:
        return False
    statuses = client.describe_configuration_recorder_status().get(
        "ConfigurationRecordersStatus", []
    )
    return any(status.get("recording") is True for status in statuses)


def _has_delivering_channel(client):
    channels = client.describe_delivery_channels().get("DeliveryChannels", [])
    if not channels:
        return False
    statuses = client.describe_delivery_channel_status().get(
        "DeliveryChannelsStatus", []
    )

    # Normalise lastStatus case before comparing so the check cannot
    # silently never match.
    def delivered(info):
        return (info or {}).get("lastStatus", "").upper() == "SUCCESS"

    return any(
        delivered(status.get("configHistoryDeliveryInfo"))
        or delivered(status.get("configSnapshotDeliveryInfo"))
        for status in statuses
    )


# Terminated instances stay visible for about an hour; they do not count.
_LIVE_INSTANCE_STATES = ["pending", "running", "stopping", "stopped"]


def _has_instances(client):
    resp = client.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": _LIVE_INSTANCE_STATES}],
        MaxResults=5,
    )
    return any(r.get("Instances") for r in resp.get("Reservations", []))


def _has_vpcs(client):
    return bool(client.describe_vpcs().get("Vpcs", []))


def check_cloudtrail_exists(regions):
    """FR-7.1: Verify at least one CloudTrail trail exists."""
    base = {
        "check": "CloudTrail trail exists",
        "description": "At least one CloudTrail trail should be configured and logging.",
        "required": True,
        "weight": 6,
        "loe": 3,
        "remediationLink": "https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-create-a-trail-using-the-console-first-time.html",
    }
    return _regional_check(base, regions, "cloudtrail", _has_trail, True)


def check_cloudtrail_org_trail(regions):
    """FR-7.2: Verify at least one CloudTrail org trail exists."""
    base = {
        "check": "CloudTrail organization trail",
        "description": "An organization trail should be configured and logging for centralized audit logging across all accounts.",
        "required": True,
        "weight": 6,
        "loe": 1,
        "remediationLink": "https://docs.aws.amazon.com/awscloudtrail/latest/userguide/creating-trail-organization.html",
    }
    return _regional_check(base, regions, "cloudtrail", _has_org_trail, True)


def check_config_recorder(regions):
    """FR-7.3: Verify AWS Config recorder is active in at least one region."""
    base = {
        "check": "AWS Config recorder active",
        "description": "AWS Config recorder should be active for resource configuration tracking.",
        "required": True,
        "weight": 6,
        "loe": 2,
        "remediationLink": "https://docs.aws.amazon.com/config/latest/developerguide/gs-console.html",
    }
    return _regional_check(base, regions, "config", _has_active_recorder, True)


def check_config_delivery_channel(regions):
    """FR-7.4: Verify an AWS Config delivery channel is delivering successfully."""
    base = {
        "check": "AWS Config delivery channel active",
        "description": "AWS Config delivery channel should be configured for configuration change delivery.",
        "required": True,
        "weight": 6,
        "loe": 2,
        "remediationLink": "https://docs.aws.amazon.com/config/latest/developerguide/manage-delivery-channel.html",
    }
    return _regional_check(base, regions, "config", _has_delivering_channel, True)


def check_no_ec2_instances(regions):
    """FR-7.5: Verify no EC2 instances exist in this account."""
    base = {
        "check": "No EC2 instances in account",
        "description": "Reports whether the assessed account contains EC2 instances; centralized management accounts should keep workloads elsewhere.",
        "required": False,
        "weight": 4,
        "loe": 1,
        "remediationLink": "https://docs.aws.amazon.com/whitepapers/latest/organizing-your-aws-environment/aws-organizations.html",
    }
    return _regional_check(base, regions, "ec2", _has_instances, False)


def check_no_vpcs(regions):
    """FR-7.6: Verify no VPCs exist in this account (including defaults)."""
    base = {
        "check": "No VPCs in account",
        "description": "Reports whether the assessed account contains VPCs; centralized management accounts should keep workloads elsewhere.",
        "required": False,
        "weight": 4,
        "loe": 1,
        "remediationLink": "https://docs.aws.amazon.com/whitepapers/latest/organizing-your-aws-environment/aws-organizations.html",
    }
    return _regional_check(base, regions, "ec2", _has_vpcs, False)


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
        kwargs = {}
        while True:
            resp = client.describe_report_definitions(**kwargs)
            has_report = bool(resp.get("ReportDefinitions", []))
            if has_report or not resp.get("NextToken"):
                break
            kwargs = {"NextToken": resp["NextToken"]}
    except Exception as e:
        errors.append(f"cur: {e}")

    if not has_report and not default_region.startswith(("us-gov-", "cn-")):
        try:
            client = boto3.client("bcm-data-exports", region_name=default_region)
            kwargs = {}
            while True:
                resp = client.list_exports(**kwargs)
                has_report = bool(resp.get("Exports", []))
                if has_report or not resp.get("NextToken"):
                    break
                kwargs = {"NextToken": resp["NextToken"]}
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
