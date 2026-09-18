"""Region discovery (FR-2.3).

Discovers enabled AWS regions by calling EC2 DescribeRegions.
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


def get_enabled_regions(bootstrap_region=None):
    """Discover all default-enabled regions via EC2 DescribeRegions (FR-2.3).

    Returns only regions that are opt-in-not-required (default-enabled).
    Falls back to hardcoded list on failure.

    Returns:
        list[str]: List of region names
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
            Filters=[{"Name": "opt-in-status", "Values": ["opt-in-not-required"]}]
        )
        regions = [r["RegionName"] for r in response.get("Regions", [])]
        if regions:
            return sorted(regions)
    except (ClientError, Exception) as e:
        print(f"WARNING: Could not discover regions via API ({e}). Using default list.")

    if bootstrap_region.startswith("us-gov-"):
        return GOVCLOUD_REGIONS
    if bootstrap_region.startswith("cn-"):
        return CHINA_REGIONS
    return DEFAULT_REGIONS
