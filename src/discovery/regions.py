"""Region discovery (FR-2.3).

Discovers enabled AWS regions (default-enabled plus opted-in) by calling
EC2 DescribeRegions.
Falls back to a hardcoded list if the API call fails.
"""

import os

import boto3
from botocore.exceptions import ClientError

# Fallbacks are used only when DescribeRegions is unavailable.
DEFAULT_REGIONS = [
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "ap-south-1",
    "ap-northeast-1",
    "ap-northeast-2",
    "ap-northeast-3",
    "ap-southeast-1",
    "ap-southeast-2",
    "ca-central-1",
    "eu-central-1",
    "eu-west-1",
    "eu-west-2",
    "eu-west-3",
    "eu-north-1",
    "sa-east-1",
]
GOVCLOUD_REGIONS = ["us-gov-east-1", "us-gov-west-1"]
CHINA_REGIONS = ["cn-north-1", "cn-northwest-1"]


def has_service_endpoint(service_name, region):
    """Return False only when botocore's endpoint data omits the region.

    Uses the endpoint data bundled with botocore, so no network call is made.
    Callers use this to tell a region that has no endpoint for the service
    from a network failure. When the data cannot be read, assume the endpoint
    exists so a connection failure is reported rather than treated as absence.
    """
    try:
        session = boto3.session.Session()
        partition = session.get_partition_for_region(region)
        return region in session.get_available_regions(
            service_name, partition_name=partition
        )
    except Exception:
        return True


def get_enabled_regions(bootstrap_region=None):
    """Discover the account's enabled regions (FR-2.3).

    Returns default-enabled (opt-in-not-required) regions plus opt-in
    regions the account has enabled (opted-in).
    Falls back to hardcoded list on failure.

    Returns:
        list[str]: List of region names
    """
    return discover_regions(bootstrap_region)[0]


def discover_regions(bootstrap_region=None):
    """Discover enabled regions and the opted-in subset in one API call.

    Returns:
        tuple(list[str], list[str]): (enabled regions, opted-in regions).
        The opted-in list is empty when discovery falls back.
    """
    if bootstrap_region is None:
        bootstrap_region = "us-east-1"
        configured_region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get(
            "AWS_REGION"
        )
        if configured_region and configured_region.startswith("us-gov-"):
            bootstrap_region = "us-gov-west-1"
        elif configured_region and configured_region.startswith("cn-"):
            bootstrap_region = "cn-north-1"

    try:
        ec2_client = boto3.client("ec2", region_name=bootstrap_region)
        response = ec2_client.describe_regions(
            Filters=[
                {
                    "Name": "opt-in-status",
                    "Values": ["opt-in-not-required", "opted-in"],
                }
            ]
        )
        found = response.get("Regions", [])
        regions = [r["RegionName"] for r in found]
        if regions:
            opted_in = [
                r["RegionName"] for r in found if r.get("OptInStatus") == "opted-in"
            ]
            return sorted(regions), sorted(opted_in)
    except (ClientError, Exception) as e:
        print(f"WARNING: Could not discover regions via API ({e}). Using default list.")

    if bootstrap_region.startswith("us-gov-"):
        return GOVCLOUD_REGIONS, []
    if bootstrap_region.startswith("cn-"):
        return CHINA_REGIONS, []
    return DEFAULT_REGIONS, []
