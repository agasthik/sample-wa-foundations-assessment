"""Identity Checks (FR-6).

Checks IAM Identity Center configuration and IAM user presence.
FR-6.1 only runs if management account; FR-6.2 runs in all modes.
"""

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError

from src.discovery.regions import has_service_endpoint

_REGION_UNAVAILABLE_CODES = {"InvalidRegion", "OptInRequired"}


def check_iam_identity_center(regions):
    """FR-6.1: Verify IAM Identity Center is configured in at least one region.

    Iterates regions sequentially, stops on first success.
    Only runs from management account.
    """
    try:
        region_errors = []
        for region in regions:
            try:
                client = boto3.client("sso-admin", region_name=region)
                resp = client.list_instances()
                instances = resp.get("Instances", [])
                if instances:
                    return {
                        "check": "IAM Identity Center configured",
                        "description": "IAM Identity Center (SSO) should be configured for centralized identity management.",
                        "status": "complete",
                        "required": True,
                        "weight": 6,
                        "loe": 3,
                        "remediationLink": "https://docs.aws.amazon.com/singlesignon/latest/userguide/enable-identity-center.html",
                    }
            except EndpointConnectionError as e:
                # Skip only regions with no Identity Center endpoint; any
                # other connection failure leaves this region's state unknown
                if not has_service_endpoint("sso-admin", region):
                    continue
                region_errors.append(f"{region}: {e}")
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code in _REGION_UNAVAILABLE_CODES:
                    continue
                # Permission, throttling, and service failures leave this
                # region's state unknown
                region_errors.append(f"{region}: {error_code or e}")
            except Exception as e:
                region_errors.append(f"{region}: {e}")

        # Any region we could not inspect means absence is not proven
        if region_errors:
            return {
                "check": "IAM Identity Center configured",
                "description": "IAM Identity Center (SSO) should be configured for centralized identity management.",
                "status": "error",
                "required": True,
                "weight": 6,
                "loe": 3,
                "remediationLink": "https://docs.aws.amazon.com/singlesignon/latest/userguide/enable-identity-center.html",
                "error": f"Could not call sso-admin:ListInstances (IAM action sso:ListInstances) in: {', '.join(region_errors)}",
            }

        # Not found in any region
        return {
            "check": "IAM Identity Center configured",
            "description": "IAM Identity Center (SSO) should be configured for centralized identity management.",
            "status": "incomplete",
            "required": True,
            "weight": 6,
            "loe": 3,
            "remediationLink": "https://docs.aws.amazon.com/singlesignon/latest/userguide/enable-identity-center.html",
        }
    except Exception as e:
        return {
            "check": "IAM Identity Center configured",
            "description": "IAM Identity Center (SSO) should be configured for centralized identity management.",
            "status": "error",
            "required": True,
            "weight": 6,
            "loe": 3,
            "remediationLink": "https://docs.aws.amazon.com/singlesignon/latest/userguide/enable-identity-center.html",
            "error": str(e),
        }


def check_no_iam_users(default_region="us-east-1"):
    """FR-6.2: Verify no IAM users exist in the assessed account.

    Runs in ALL modes (management, member, standalone).
    IAM is global within a partition, so we query the partition default
    region (us-east-1, us-gov-west-1, or cn-north-1).
    """
    try:
        client = boto3.client("iam", region_name=default_region)
        paginator = client.get_paginator("list_users")
        no_users = True
        for page in paginator.paginate():
            if page.get("Users"):
                no_users = False
                break

        return {
            "check": "No IAM users in account",
            "description": "The assessed account should avoid IAM users; use IAM Identity Center or federation instead.",
            "status": "complete" if no_users else "incomplete",
            "required": False,
            "weight": 4,
            "loe": 1,
            "remediationLink": "https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html#bp-users-federation-idp",
        }
    except Exception as e:
        return {
            "check": "No IAM users in account",
            "description": "The assessed account should avoid IAM users; use IAM Identity Center or federation instead.",
            "status": "error",
            "required": False,
            "weight": 4,
            "loe": 1,
            "remediationLink": "https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html#bp-users-federation-idp",
            "error": str(e),
        }


def run_all(regions, is_management_account=True, default_region="us-east-1"):
    """Run all identity checks.

    Args:
        regions: list of region names for IDC discovery
        is_management_account: if True, run FR-6.1; FR-6.2 always runs
        default_region: partition default region used for IAM
    """
    results = []
    if is_management_account:
        results.append(check_iam_identity_center(regions))
    results.append(check_no_iam_users(default_region))
    return results
