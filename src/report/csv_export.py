"""CSV Report Generation (FR-10.2).

Generates a CSV file with all check results.
"""

import csv
import io


def generate_csv(checks):
    """Generate CSV content from check results.

    Args:
        checks: list of check result dicts

    Returns:
        str: CSV content as string
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow(
        [
            "Check Name",
            "Description",
            "Status",
            "Required",
            "Weight",
            "Level of Effort",
            "Remediation Link",
            "Error",
        ]
    )

    # Data rows
    for check in checks:
        writer.writerow(
            [
                check.get("check", ""),
                check.get("description", ""),
                check.get("status", ""),
                "Yes" if check.get("required") else "No",
                check.get("weight", ""),
                check.get("loe", ""),
                check.get("remediationLink", ""),
                check.get("error", ""),
            ]
        )

    return output.getvalue()
