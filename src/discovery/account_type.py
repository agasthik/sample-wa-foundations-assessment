"""Account type detection (FR-2.1, FR-2.2, FR-2.5).

Detects whether the current account is:
- Management account of an AWS Organization
- Member account of an AWS Organization
- Standalone account (no organization)
- Unknown, when DescribeOrganization fails for another reason

Also detects partition (aws, aws-us-gov, aws-cn) from region.
"""

import os

import boto3
from botocore.exceptions import ClientError


def configured_region():
    """Return the Region configured for this run.

    Precedence: AWS_DEFAULT_REGION, AWS_REGION, then the active profile's
    Region (boto3 session), falling back to us-east-1.
    """
    return (
        os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("AWS_REGION")
        or boto3.session.Session().region_name
        or "us-east-1"
    )


def detect_partition():
    """Detect AWS partition from the configured Region (FR-1.5).

    Returns:
        dict with keys: partition, default_region
    """
    region = configured_region()

    if region.startswith("us-gov-"):
        return {"partition": "aws-us-gov", "default_region": "us-gov-west-1"}
    elif region.startswith("cn-"):
        return {"partition": "aws-cn", "default_region": "cn-north-1"}
    else:
        return {"partition": "aws", "default_region": "us-east-1"}


def detect_account_type():
    """Detect account type: management, member, or standalone (FR-2.1, FR-2.2).

    Returns:
        dict with keys:
            - account_id: str - current AWS account ID
            - is_management_account: bool - True if this is the management account
            - is_in_organization: bool - True if account belongs to an org
            - organization_id: str | None - org ID if in an org
            - management_account_id: str | None - management account ID if in org
            - account_type: str - "management" | "member" | "standalone" | "unknown"
            - detection_error: str - present only when account_type is "unknown"
    """
    sts_client = boto3.client("sts")
    identity = sts_client.get_caller_identity()
    current_account_id = identity["Account"]

    result = {
        "account_id": current_account_id,
        "is_management_account": False,
        "is_in_organization": False,
        "organization_id": None,
        "management_account_id": None,
        "account_type": "standalone",
    }

    try:
        org_client = boto3.client("organizations")
        org_response = org_client.describe_organization()
        org = org_response["Organization"]

        result["is_in_organization"] = True
        result["organization_id"] = org["Id"]
        result["management_account_id"] = org["MasterAccountId"]

        if org["MasterAccountId"] == current_account_id:
            result["is_management_account"] = True
            result["account_type"] = "management"
        else:
            result["account_type"] = "member"
            print(
                f"WARNING: Running from member account {current_account_id}. "
                f"Management account is {org['MasterAccountId']}. "
                "Only limited checks will run."
            )

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "AWSOrganizationsNotInUseException":
            result["account_type"] = "standalone"
            print(
                f"WARNING: Account {current_account_id} is not part of an AWS Organization. "
                "Only limited checks will run."
            )
        else:
            # Without DescribeOrganization (for example, an SCP or role
            # policy denies it) the account type cannot be determined. Run
            # the limited assessment instead of stopping without a report.
            result["account_type"] = "unknown"
            result["detection_error"] = str(e)
            print(
                f"WARNING: Could not determine whether account {current_account_id} "
                f"belongs to an AWS Organization ({error_code}). "
                "Only limited checks will run."
            )
    except Exception as e:
        # Non-API failures (for example, endpoint or network errors) leave
        # the account type undetermined as well; degrade the same way.
        result["account_type"] = "unknown"
        result["detection_error"] = str(e)
        print(
            f"WARNING: Could not determine whether account {current_account_id} "
            f"belongs to an AWS Organization ({e}). "
            "Only limited checks will run."
        )

    return result
