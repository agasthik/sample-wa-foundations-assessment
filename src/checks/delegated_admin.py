"""Delegated Administrator Checks (FR-9).

Informational only — no pass/fail scoring.
Only runs from management account.
"""

import boto3


def get_delegated_administrators():
    """FR-9: Retrieve all delegated administrators and their services.

    Returns:
        tuple(list of dicts, str | None): the administrators found, as
        [{accountId, accountName, services: [str, ...], servicesError?}],
        and an error message when the list could not be fully retrieved.
        Administrators collected before a failure are kept.
    """
    admins = []
    try:
        client = boto3.client("organizations")
        paginator = client.get_paginator("list_delegated_administrators")
        for page in paginator.paginate():
            for admin in page.get("DelegatedAdministrators", []):
                account_id = admin.get("Id", "")
                account_name = admin.get("Name", "")

                # Get services for this delegated admin
                services = []
                services_error = None
                try:
                    svc_paginator = client.get_paginator(
                        "list_delegated_services_for_account"
                    )
                    for svc_page in svc_paginator.paginate(AccountId=account_id):
                        for svc in svc_page.get("DelegatedServices", []):
                            services.append(svc.get("ServicePrincipal", ""))
                except Exception as e:
                    services_error = str(e)

                admin_entry = {
                    "accountId": account_id,
                    "accountName": account_name,
                    "services": services,
                }
                if services_error:
                    admin_entry["servicesError"] = services_error
                admins.append(admin_entry)

        return admins, None
    except Exception as e:
        return admins, str(e)
