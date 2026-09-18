"""Organization Service Integration Checks (FR-4).

Checks which AWS services are enabled at the organization level.
Uses a single API call to listAWSServiceAccessForOrganization (NFR-2.3).
Only runs if the current account is the management account.
"""

import boto3


# Service principal → check metadata mapping
_SERVICE_CHECKS = [
    {
        "id": "FR-4.1",
        "service_principal": "cloudtrail.amazonaws.com",
        "check": "CloudTrail organization service enabled",
        "description": "CloudTrail should be enabled as an organization service for centralized audit logging.",
        "weight": 6,
        "loe": 1,
        "required": True,
        "remediationLink": "https://docs.aws.amazon.com/awscloudtrail/latest/userguide/creating-trail-organization.html",
    },
    {
        "id": "FR-4.2",
        "service_principal": "config.amazonaws.com",
        "check": "AWS Config organization service enabled",
        "description": "AWS Config should be enabled as an organization service for resource tracking.",
        "weight": 4,
        "loe": 1,
        "required": False,
        "remediationLink": "https://docs.aws.amazon.com/config/latest/developerguide/config-rule-multi-account-deployment.html",
    },
    {
        "id": "FR-4.3",
        "service_principal": "guardduty.amazonaws.com",
        "check": "GuardDuty organization service enabled",
        "description": "GuardDuty should be enabled as an organization service for threat detection.",
        "weight": 4,
        "loe": 1,
        "required": False,
        "remediationLink": "https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_organizations.html",
    },
    {
        "id": "FR-4.4",
        "service_principal": "securityhub.amazonaws.com",
        "check": "Security Hub organization service enabled",
        "description": "Security Hub should be enabled as an organization service for centralized security findings.",
        "weight": 4,
        "loe": 1,
        "required": False,
        "remediationLink": "https://docs.aws.amazon.com/securityhub/latest/userguide/designate-orgs-admin-account.html",
    },
    {
        "id": "FR-4.5",
        "service_principal": "access-analyzer.amazonaws.com",
        "check": "IAM Access Analyzer organization service enabled",
        "description": "IAM Access Analyzer should be enabled for cross-account access analysis.",
        "weight": 4,
        "loe": 1,
        "required": False,
        "remediationLink": "https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-getting-started.html",
    },
    {
        "id": "FR-4.6",
        "service_principal": "ram.amazonaws.com",
        "check": "RAM organization service enabled",
        "description": "Resource Access Manager should be enabled for cross-account resource sharing.",
        "weight": 4,
        "loe": 1,
        "required": False,
        "remediationLink": "https://docs.aws.amazon.com/ram/latest/userguide/getting-started-sharing.html",
    },
    {
        "id": "FR-4.7",
        "service_principal": "sso.amazonaws.com",
        "check": "IAM Identity Center organization service enabled",
        "description": "IAM Identity Center (SSO) should be enabled for centralized identity management.",
        "weight": 6,
        "loe": 1,
        "required": True,
        "remediationLink": "https://docs.aws.amazon.com/singlesignon/latest/userguide/get-started-enable-identity-center.html",
    },
    {
        "id": "FR-4.8",
        "service_principal": "member.org.stacksets.cloudformation.amazonaws.com",
        "check": "CloudFormation StackSets organization service enabled",
        "description": "CloudFormation StackSets should be enabled for organization-wide deployments.",
        "weight": 5,
        "loe": 1,
        "required": False,
        "remediationLink": "https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-orgs-enable-trusted-access.html",
    },
    {
        "id": "FR-4.9",
        "service_principal": "backup.amazonaws.com",
        "check": "AWS Backup organization service enabled",
        "description": "AWS Backup should be enabled as an organization service for centralized backup management.",
        "weight": 4,
        "loe": 1,
        "required": False,
        "remediationLink": "https://docs.aws.amazon.com/aws-backup/latest/devguide/manage-cross-account.html",
    },
    {
        "id": "FR-4.10",
        "service_principal": "cost-optimization-hub.bcm.amazonaws.com",
        "check": "Cost Optimization Hub organization service enabled",
        "description": "Cost Optimization Hub should be enabled for organization-wide cost visibility.",
        "weight": 4,
        "loe": 1,
        "required": False,
        "remediationLink": "https://docs.aws.amazon.com/cost-management/latest/userguide/coh-getting-started.html",
    },
]


def _get_enabled_service_principals():
    """Fetch all enabled service principals for the organization (single API call)."""
    client = boto3.client("organizations")
    principals = []
    paginator = client.get_paginator("list_aws_service_access_for_organization")
    for page in paginator.paginate():
        for entry in page.get("EnabledServicePrincipals", []):
            principals.append(entry.get("ServicePrincipal", ""))
    return principals


def check_org_service(
    service_principal, check_name, description, weight, loe, required, remediation_link
):
    """Check if a specific service principal is enabled at org level.

    This is a generic check function used by run_all() for each FR-4.x check.
    """
    try:
        principals = _get_enabled_service_principals()
        enabled = service_principal in principals
        return {
            "check": check_name,
            "description": description,
            "status": "complete" if enabled else "incomplete",
            "required": required,
            "weight": weight,
            "loe": loe,
            "remediationLink": remediation_link,
        }
    except Exception as e:
        return {
            "check": check_name,
            "description": description,
            "status": "error",
            "required": required,
            "weight": weight,
            "loe": loe,
            "remediationLink": remediation_link,
            "error": str(e),
        }


def run_all():
    """Run all organization service integration checks (FR-4.1 through FR-4.10).

    Uses a single API call to get all enabled service principals,
    then checks each expected service against that list (NFR-2.3).
    """
    try:
        principals = _get_enabled_service_principals()
    except Exception as e:
        # If we can't get the list, mark all checks as error
        results = []
        for svc in _SERVICE_CHECKS:
            results.append(
                {
                    "check": svc["check"],
                    "description": svc["description"],
                    "status": "error",
                    "required": svc["required"],
                    "weight": svc["weight"],
                    "loe": svc["loe"],
                    "remediationLink": svc["remediationLink"],
                    "error": str(e),
                }
            )
        return results

    results = []
    for svc in _SERVICE_CHECKS:
        enabled = svc["service_principal"] in principals
        results.append(
            {
                "check": svc["check"],
                "description": svc["description"],
                "status": "complete" if enabled else "incomplete",
                "required": svc["required"],
                "weight": svc["weight"],
                "loe": svc["loe"],
                "remediationLink": svc["remediationLink"],
            }
        )
    return results
