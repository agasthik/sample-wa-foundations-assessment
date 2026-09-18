"""Account type detection (FR-2.1, FR-2.2, FR-2.5).

Detects whether the current account is:
- Management account of an AWS Organization
- Member account of an AWS Organization
- Standalone account (no organization)

Also detects partition (aws, aws-us-gov, aws-cn) from region.
"""

import os
import boto3
from botocore.exceptions import ClientError


def detect_partition():
    """Detect AWS partition from AWS_DEFAULT_REGION environment variable (FR-1.5).

    Returns:
        dict with keys: partition, default_region
    """
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

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
            - account_type: str - "management" | "member" | "standalone"
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
            raise

    return result
