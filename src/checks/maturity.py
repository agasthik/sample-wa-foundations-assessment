"""Maturity Level Scoring (FR-11).

Calculates maturity level (1-5) based on check results.
Implements WAFA's project-defined Foundations maturity model.
"""

MATURITY_LEVELS = {
    1: {
        "name": "Base",
        "description": (
            "One or more prerequisites for an established multi-account "
            "foundation are not yet complete."
        ),
    },
    2: {
        "name": "Established",
        "description": (
            "AWS Organizations, the management account, a minimum account "
            "baseline, and an organizational unit structure are established."
        ),
    },
    3: {
        "name": "Intermediate",
        "description": (
            "Core governance, account provisioning, identity, audit logging, "
            "and resource recording foundations are in place."
        ),
    },
    4: {
        "name": "Advanced",
        "description": (
            "Organization service integrations, preventive and detective "
            "controls, and management-account hygiene checks are complete."
        ),
    },
    5: {
        "name": "Expert",
        "description": (
            "Every check returned by the current Well Architected Foundations "
            "Assessments report is complete."
        ),
    },
}


def _check_status(checks, check_name):
    """Return True if the named check has status 'complete'."""
    for c in checks:
        if c.get("check") == check_name:
            return c.get("status") == "complete"
    return False


def _all_checks_with_prefix_complete(checks, prefix_checks):
    """Return True if all checks in the given list are complete."""
    return all(_check_status(checks, name) for name in prefix_checks)


# FR-11.1: Level criteria check names
_LEVEL_2_CHECKS = [
    "AWS Organization exists",
    "Management account identified",
    "Minimum 4 accounts",
]

_LEVEL_2_ANY_OU = [
    "Security OU exists",
    "Workloads OU exists",
    "Infrastructure OU exists",
]

_LEVEL_3_CHECKS = [
    "Service Control Policies enabled",
    "Security OU exists",
    "Control Tower deployed",
    "Tag Policies enabled",
    "CloudTrail organization service enabled",
    "IAM Identity Center configured",
    "CloudTrail trail exists",
    "AWS Config recorder active",
]

_LEVEL_4_CHECKS = [
    "Backup Policies enabled",
    "Resource Control Policies enabled",
    "No IAM users in account",
    "No EC2 instances in account",
    "No VPCs in account",
    "Control Tower not drifted",
    "Control Tower latest version",
]

_LEVEL_4_ALL_ORG_SERVICES = [
    "CloudTrail organization service enabled",
    "AWS Config organization service enabled",
    "GuardDuty organization service enabled",
    "Security Hub organization service enabled",
    "IAM Access Analyzer organization service enabled",
    "RAM organization service enabled",
    "IAM Identity Center organization service enabled",
    "CloudFormation StackSets organization service enabled",
    "AWS Backup organization service enabled",
    "Cost Optimization Hub organization service enabled",
]

_LEVEL_4_CRITERIA = _LEVEL_4_CHECKS + _LEVEL_4_ALL_ORG_SERVICES

_LEVEL_5_CHECKS = [
    "StackSets organization access enabled",
]


def _level_2_progress(checks):
    """Return Level 2 progress and actionable missing checks."""
    complete = sum(1 for name in _LEVEL_2_CHECKS if _check_status(checks, name))
    ou_complete = any(_check_status(checks, name) for name in _LEVEL_2_ANY_OU)
    if ou_complete:
        complete += 1
        missing = _get_missing_checks(checks, _LEVEL_2_CHECKS)
    else:
        missing = _get_missing_checks(checks, _LEVEL_2_CHECKS + _LEVEL_2_ANY_OU)
    return (complete / (len(_LEVEL_2_CHECKS) + 1)) * 100, missing


def calculate_maturity_level(checks):
    """FR-11.1: Calculate the maturity level (1-5) based on check results.

    Args:
        checks: list of check result dicts

    Returns:
        dict with keys:
            - level: int (1-5)
            - name: str (level name)
            - description: str
            - next_level: int | None
            - next_level_progress: float (0-100)
            - next_level_checks_needed: list of str (check names needed for next level)
    """
    # Check Level 2 criteria
    level_2_met = _all_checks_with_prefix_complete(checks, _LEVEL_2_CHECKS) and any(
        _check_status(checks, name) for name in _LEVEL_2_ANY_OU
    )

    if not level_2_met:
        progress, next_checks = _level_2_progress(checks)
        return _build_result(1, 2, progress, next_checks, checks)

    # Check Level 3 criteria
    level_3_met = _all_checks_with_prefix_complete(checks, _LEVEL_3_CHECKS)

    if not level_3_met:
        next_checks = _get_missing_checks(checks, _LEVEL_3_CHECKS)
        progress = _calculate_progress(checks, _LEVEL_3_CHECKS)
        return _build_result(2, 3, progress, next_checks, checks)

    # Check Level 4 criteria
    level_4_met = _all_checks_with_prefix_complete(
        checks, _LEVEL_4_CHECKS
    ) and _all_checks_with_prefix_complete(checks, _LEVEL_4_ALL_ORG_SERVICES)

    if not level_4_met:
        next_checks = _get_missing_checks(checks, _LEVEL_4_CRITERIA)
        progress = _calculate_progress(checks, _LEVEL_4_CRITERIA)
        return _build_result(3, 4, progress, next_checks, checks)

    # Check Level 5 criteria
    all_phase1_complete = all(c.get("status") == "complete" for c in checks)
    level_5_met = (
        _all_checks_with_prefix_complete(checks, _LEVEL_5_CHECKS)
        and all_phase1_complete
    )

    if not level_5_met:
        incomplete = [c["check"] for c in checks if c.get("status") != "complete"]
        total_checks = len(checks)
        complete_count = len([c for c in checks if c.get("status") == "complete"])
        progress = (complete_count / total_checks * 100) if total_checks > 0 else 0
        return _build_result(4, 5, progress, incomplete, checks)

    return _build_result(5, None, 100, [], checks)


def _get_missing_checks(checks, required_check_names):
    """Get check names from required list that are not 'complete'."""
    missing = []
    for name in required_check_names:
        if not _check_status(checks, name):
            missing.append(name)
    return missing


def _calculate_progress(checks, required_check_names):
    """Calculate percentage of required checks that are complete."""
    if not required_check_names:
        return 100.0
    complete = sum(1 for name in required_check_names if _check_status(checks, name))
    return (complete / len(required_check_names)) * 100


def _criterion(checks, name):
    """Build display data for one named scoring criterion."""
    status = "not_assessed"
    for check in checks:
        if check.get("check") == name:
            status = check.get("status", "not_assessed")
            break
    return {"name": name, "status": status}


def _any_ou_criterion(checks):
    """Build the Level 2 criterion that accepts any recognized OU."""
    statuses = [_criterion(checks, name)["status"] for name in _LEVEL_2_ANY_OU]
    if "complete" in statuses:
        status = "complete"
    elif "error" in statuses:
        status = "error"
    elif "incomplete" in statuses:
        status = "incomplete"
    else:
        status = "not_assessed"

    return {
        "name": "At least one recognized organizational unit exists",
        "status": status,
        "detail": "Security OU, Workloads OU, or Infrastructure OU",
    }


def _level_state(level, current_level, next_level):
    """Return the report-display state for a maturity level."""
    if level < current_level:
        return "achieved"
    if level == current_level:
        return "current"
    if level == next_level:
        return "next"
    return "locked"


def _level_model(
    level,
    criteria,
    current_level,
    next_level,
    complete_count=None,
    criteria_count=None,
):
    """Build one level's criteria and progress for report rendering."""
    if complete_count is None:
        complete_count = sum(
            1 for criterion in criteria if criterion["status"] == "complete"
        )
    if criteria_count is None:
        criteria_count = len(criteria)

    progress = (
        round((complete_count / criteria_count) * 100, 1) if criteria_count else None
    )
    return {
        "level": level,
        "name": MATURITY_LEVELS[level]["name"],
        "description": MATURITY_LEVELS[level]["description"],
        "state": _level_state(level, current_level, next_level),
        "criteria": criteria,
        "complete_count": complete_count,
        "criteria_count": criteria_count,
        "progress": progress,
    }


def _build_scoring_model(checks, current_level, next_level):
    """Build a report-ready explanation directly from the scoring criteria."""
    level_2_criteria = [
        *[_criterion(checks, name) for name in _LEVEL_2_CHECKS],
        _any_ou_criterion(checks),
    ]
    level_3_criteria = [_criterion(checks, name) for name in _LEVEL_3_CHECKS]
    level_4_criteria = [_criterion(checks, name) for name in _LEVEL_4_CRITERIA]

    level_5_complete = sum(1 for check in checks if check.get("status") == "complete")
    if checks and level_5_complete == len(checks):
        level_5_status = "complete"
    elif any(check.get("status") == "error" for check in checks):
        level_5_status = "error"
    else:
        level_5_status = "incomplete"
    level_5_criteria = [
        {
            "name": "All checks returned by this assessment are complete",
            "status": level_5_status,
            "detail": f"{level_5_complete} of {len(checks)} checks complete",
        }
    ]

    return {
        "rule": (
            "The Well Architected Foundations Assessments model assigns the "
            "highest maturity level whose required criteria are all complete."
        ),
        "weight_note": (
            "Check weights prioritize recommended next steps; they do not "
            "change the maturity level."
        ),
        "levels": [
            _level_model(1, [], current_level, next_level),
            _level_model(2, level_2_criteria, current_level, next_level),
            _level_model(3, level_3_criteria, current_level, next_level),
            _level_model(4, level_4_criteria, current_level, next_level),
            _level_model(
                5,
                level_5_criteria,
                current_level,
                next_level,
                complete_count=level_5_complete,
                criteria_count=len(checks),
            ),
        ],
    }


def _build_result(level, next_level, progress, next_checks, checks):
    """Build the maturity scoring result dict."""
    # Sort next_checks by weight (highest first)
    weighted_next = []
    for name in next_checks:
        for c in checks:
            if c.get("check") == name:
                weighted_next.append((c.get("weight", 0), name))
                break
        else:
            weighted_next.append((0, name))

    weighted_next.sort(key=lambda x: -x[0])
    sorted_next_checks = [name for _, name in weighted_next]

    return {
        "level": level,
        "name": MATURITY_LEVELS[level]["name"],
        "description": MATURITY_LEVELS[level]["description"],
        "next_level": next_level,
        "next_level_progress": round(progress, 1),
        "next_level_checks_needed": sorted_next_checks,
        "scoring_model": _build_scoring_model(checks, level, next_level),
    }
