"""Delegated Administrator Checks (FR-9).

Informational only — no pass/fail scoring.
Only runs from management account.
"""

import boto3
from botocore.exceptions import ClientError


def get_delegated_administrators():
    """FR-9: Retrieve all delegated administrators and their services.

    Returns:
        list of dicts: [{accountId, accountName, services: [str, ...]}]
    """
    try:
        client = boto3.client("organizations")
        admins = []
        paginator = client.get_paginator("list_delegated_administrators")
        for page in paginator.paginate():
            for admin in page.get("DelegatedAdministrators", []):
                account_id = admin.get("Id", "")
                account_name = admin.get("Name", "")

                # Get services for this delegated admin
                services = []
                try:
                    svc_paginator = client.get_paginator(
                        "list_delegated_services_for_account"
                    )
                    for svc_page in svc_paginator.paginate(AccountId=account_id):
                        for svc in svc_page.get("DelegatedServices", []):
                            services.append(svc.get("ServicePrincipal", ""))
                except ClientError:
                    pass  # Skip if we can't get services for this account

                admins.append(
                    {
                        "accountId": account_id,
                        "accountName": account_name,
                        "services": services,
                    }
                )

        return admins
    except Exception:
        return []
