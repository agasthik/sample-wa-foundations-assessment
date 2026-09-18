"""Identity Checks (FR-6).

Checks IAM Identity Center configuration and IAM user presence.
FR-6.1 only runs if management account; FR-6.2 runs in all modes.
"""

import boto3
from botocore.exceptions import ClientError


def check_iam_identity_center(regions):
    """FR-6.1: Verify IAM Identity Center is configured in at least one region.

    Iterates regions sequentially, stops on first success.
    Only runs from management account.
    """
    try:
        access_denied_errors = []
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
                        "remediationLink": "https://docs.aws.amazon.com/singlesignon/latest/userguide/get-started-enable-identity-center.html",
                    }
            except ClientError as e:
                # Distinguish permission failures from regions that don't support SSO
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code in (
                    "AccessDeniedException",
                    "AccessDenied",
                    "UnauthorizedException",
                ):
                    access_denied_errors.append(f"{region}: {error_code}")
                # Otherwise region might not support SSO, try next
                continue

        # Permission failures mean we couldn't determine the real state
        if access_denied_errors:
            return {
                "check": "IAM Identity Center configured",
                "description": "IAM Identity Center (SSO) should be configured for centralized identity management.",
                "status": "error",
                "required": True,
                "weight": 6,
                "loe": 3,
                "remediationLink": "https://docs.aws.amazon.com/singlesignon/latest/userguide/get-started-enable-identity-center.html",
                "error": f"Access denied calling sso-admin:ListInstances (IAM action sso:ListInstances) in: {', '.join(access_denied_errors)}",
            }

        # Not found in any region
        return {
            "check": "IAM Identity Center configured",
            "description": "IAM Identity Center (SSO) should be configured for centralized identity management.",
            "status": "incomplete",
            "required": True,
            "weight": 6,
            "loe": 3,
            "remediationLink": "https://docs.aws.amazon.com/singlesignon/latest/userguide/get-started-enable-identity-center.html",
        }
    except Exception as e:
        return {
            "check": "IAM Identity Center configured",
            "description": "IAM Identity Center (SSO) should be configured for centralized identity management.",
            "status": "error",
            "required": True,
            "weight": 6,
            "loe": 3,
            "remediationLink": "https://docs.aws.amazon.com/singlesignon/latest/userguide/get-started-enable-identity-center.html",
            "error": str(e),
        }


def check_no_iam_users():
    """FR-6.2: Verify no IAM users exist in the assessed account.

    Runs in ALL modes (management, member, standalone).
    IAM is global, so we query us-east-1.
    """
    try:
        client = boto3.client("iam", region_name="us-east-1")
        resp = client.list_users()
        users = resp.get("Users", [])
        no_users = len(users) == 0

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


def run_all(regions, is_management_account=True):
    """Run all identity checks.

    Args:
        regions: list of region names for IDC discovery
        is_management_account: if True, run FR-6.1; FR-6.2 always runs
    """
    results = []
    if is_management_account:
        results.append(check_iam_identity_center(regions))
    results.append(check_no_iam_users())
    return results
