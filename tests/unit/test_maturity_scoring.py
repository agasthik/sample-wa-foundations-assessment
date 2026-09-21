"""Unit tests for src/checks/maturity.py — FR-11: Maturity Level Scoring."""

from src.checks.maturity import calculate_maturity_level


def _make_check(name, status="complete", weight=6, required=True, loe=1):
    return {
        "check": name,
        "description": f"Test check: {name}",
        "status": status,
        "required": required,
        "weight": weight,
        "loe": loe,
        "remediationLink": "https://example.com",
    }


# Full set of checks used for Level 5
_ALL_CHECK_NAMES = [
    "AWS Organization exists",
    "Management account identified",
    "Minimum 4 accounts",
    "Log Archive account exists",
    "Audit account exists",
    "Service Control Policies enabled",
    "Tag Policies enabled",
    "Backup Policies enabled",
    "Resource Control Policies enabled",
    "Security OU exists",
    "Workloads OU exists",
    "Infrastructure OU exists",
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
    "Control Tower deployed",
    "Control Tower not drifted",
    "Control Tower latest version",
    "IAM Identity Center configured",
    "No IAM users in account",
    "CloudTrail trail exists",
    "CloudTrail organization trail",
    "AWS Config recorder active",
    "AWS Config delivery channel active",
    "No EC2 instances in account",
    "No VPCs in account",
    "Cost and Usage Report configured",
    "StackSets organization access enabled",
]


class TestLevel1:
    """Level 1 — Base: no org or minimal setup."""

    def test_no_org(self):
        """No organization → Level 1."""
        checks = [
            _make_check("AWS Organization exists", "incomplete"),
            _make_check("Management account identified", "incomplete"),
            _make_check("Minimum 4 accounts", "incomplete"),
            _make_check("Security OU exists", "incomplete"),
        ]
        result = calculate_maturity_level(checks)
        assert result["level"] == 1
        assert result["name"] == "Base"
        assert result["next_level"] == 2

    def test_only_org_no_accounts(self):
        """Org exists but only 2 accounts → Level 1."""
        checks = [
            _make_check("AWS Organization exists", "complete"),
            _make_check("Management account identified", "complete"),
            _make_check("Minimum 4 accounts", "incomplete"),
            _make_check("Security OU exists", "incomplete"),
        ]
        result = calculate_maturity_level(checks)
        assert result["level"] == 1

    def test_no_ou_structure(self):
        """Has 4 accounts but no OUs → Level 1."""
        checks = [
            _make_check("AWS Organization exists", "complete"),
            _make_check("Management account identified", "complete"),
            _make_check("Minimum 4 accounts", "complete"),
            _make_check("Security OU exists", "incomplete"),
            _make_check("Workloads OU exists", "incomplete"),
            _make_check("Infrastructure OU exists", "incomplete"),
        ]
        result = calculate_maturity_level(checks)
        assert result["level"] == 1
        assert "Security OU exists" in result["next_level_checks_needed"]
        assert "Workloads OU exists" in result["next_level_checks_needed"]
        assert "Infrastructure OU exists" in result["next_level_checks_needed"]


class TestLevel2:
    """Level 2 — Established: org + accounts + at least 1 OU."""

    def test_meets_level_2(self):
        """Org + 4 accounts + Security OU → Level 2."""
        checks = [
            _make_check("AWS Organization exists", "complete"),
            _make_check("Management account identified", "complete"),
            _make_check("Minimum 4 accounts", "complete"),
            _make_check("Security OU exists", "complete"),
            # Not meeting Level 3 requirements
            _make_check("Service Control Policies enabled", "incomplete"),
            _make_check("Control Tower deployed", "incomplete"),
            _make_check("Tag Policies enabled", "incomplete"),
            _make_check("CloudTrail organization service enabled", "incomplete"),
            _make_check("IAM Identity Center configured", "incomplete"),
            _make_check("CloudTrail trail exists", "incomplete"),
            _make_check("AWS Config recorder active", "incomplete"),
        ]
        result = calculate_maturity_level(checks)
        assert result["level"] == 2
        assert result["name"] == "Established"
        assert result["next_level"] == 3
        assert result["next_level_progress"] > 0

    def test_progress_toward_level_3(self):
        """Partial Level 3 completion shows progress."""
        checks = [
            _make_check("AWS Organization exists", "complete"),
            _make_check("Management account identified", "complete"),
            _make_check("Minimum 4 accounts", "complete"),
            _make_check("Security OU exists", "complete"),
            _make_check("Service Control Policies enabled", "complete"),
            _make_check("Control Tower deployed", "complete"),
            _make_check("Tag Policies enabled", "complete"),
            _make_check("CloudTrail organization service enabled", "incomplete"),
            _make_check("IAM Identity Center configured", "incomplete"),
            _make_check("CloudTrail trail exists", "incomplete"),
            _make_check("AWS Config recorder active", "incomplete"),
        ]
        result = calculate_maturity_level(checks)
        assert result["level"] == 2
        assert result["next_level_progress"] > 30  # 4/8 checks complete


class TestLevel3:
    """Level 3 — Intermediate: SCPs, CT, tags, logging."""

    def test_meets_level_3(self):
        """All Level 3 criteria met → Level 3."""
        checks = [
            _make_check("AWS Organization exists", "complete"),
            _make_check("Management account identified", "complete"),
            _make_check("Minimum 4 accounts", "complete"),
            _make_check("Security OU exists", "complete"),
            _make_check("Service Control Policies enabled", "complete"),
            _make_check("Control Tower deployed", "complete"),
            _make_check("Tag Policies enabled", "complete"),
            _make_check("CloudTrail organization service enabled", "complete"),
            _make_check("IAM Identity Center configured", "complete"),
            _make_check("CloudTrail trail exists", "complete"),
            _make_check("AWS Config recorder active", "complete"),
            # Not meeting Level 4
            _make_check("GuardDuty organization service enabled", "incomplete"),
            _make_check("Security Hub organization service enabled", "incomplete"),
            _make_check(
                "IAM Access Analyzer organization service enabled", "incomplete"
            ),
            _make_check("Backup Policies enabled", "incomplete"),
            _make_check("Resource Control Policies enabled", "incomplete"),
            _make_check("No IAM users in account", "incomplete"),
            _make_check("No EC2 instances in account", "incomplete"),
            _make_check("No VPCs in account", "incomplete"),
            _make_check("Control Tower not drifted", "incomplete"),
            _make_check("Control Tower latest version", "incomplete"),
        ]
        result = calculate_maturity_level(checks)
        assert result["level"] == 3
        assert result["name"] == "Intermediate"
        assert result["next_level"] == 4

    def test_level_4_progress_counts_each_org_service_once(self):
        """Overlapping Level 4 criteria must not skew progress or next steps."""
        checks = [_make_check(name, "complete") for name in _ALL_CHECK_NAMES]
        guardduty = next(
            c for c in checks if c["check"] == "GuardDuty organization service enabled"
        )
        guardduty["status"] = "incomplete"

        result = calculate_maturity_level(checks)

        assert result["level"] == 3
        assert result["next_level"] == 4
        assert result["next_level_progress"] == 94.1  # 16 of 17 unique checks
        assert result["next_level_checks_needed"] == [
            "GuardDuty organization service enabled"
        ]

    def test_scoring_model_describes_all_levels_from_the_same_criteria(self):
        """Report explanation uses the criteria that determine the score."""
        checks = [_make_check(name, "complete") for name in _ALL_CHECK_NAMES]
        guardduty = next(
            c for c in checks if c["check"] == "GuardDuty organization service enabled"
        )
        guardduty["status"] = "incomplete"

        result = calculate_maturity_level(checks)
        model = result["scoring_model"]

        assert [level["level"] for level in model["levels"]] == [1, 2, 3, 4, 5]
        assert [level["state"] for level in model["levels"]] == [
            "achieved",
            "achieved",
            "current",
            "next",
            "locked",
        ]
        level_4 = model["levels"][3]
        level_4_names = [criterion["name"] for criterion in level_4["criteria"]]
        assert level_4["criteria_count"] == 17
        assert len(level_4_names) == len(set(level_4_names))
        assert level_4["complete_count"] == 16
        assert level_4["progress"] == 94.1


class TestLevel4:
    """Level 4 — Advanced: detective controls + all org services."""

    def test_meets_level_4(self):
        """All Level 4 criteria met → Level 4."""
        checks = [_make_check(name, "complete") for name in _ALL_CHECK_NAMES]
        # Make one Level 5 check incomplete to prevent Level 5
        for c in checks:
            if c["check"] == "StackSets organization access enabled":
                c["status"] = "incomplete"
        result = calculate_maturity_level(checks)
        assert result["level"] == 4
        assert result["name"] == "Advanced"
        assert result["next_level"] == 5


class TestLevel5:
    """Level 5 — Expert: all checks complete."""

    def test_all_complete(self):
        """Every check is complete → Level 5."""
        checks = [_make_check(name, "complete") for name in _ALL_CHECK_NAMES]
        result = calculate_maturity_level(checks)
        assert result["level"] == 5
        assert result["name"] == "Expert"
        assert result["next_level"] is None
        assert result["next_level_progress"] == 100
        assert result["next_level_checks_needed"] == []


class TestProgressAndNextChecks:
    """Test progress calculation and next-check ordering."""

    def test_next_checks_sorted_by_weight(self):
        """Next checks should be sorted by weight descending."""
        checks = [
            _make_check("AWS Organization exists", "complete"),
            _make_check("Management account identified", "complete"),
            _make_check("Minimum 4 accounts", "complete"),
            _make_check("Security OU exists", "complete"),
            # Level 3 checks with varying weights
            _make_check("Service Control Policies enabled", "incomplete", weight=6),
            _make_check("Control Tower deployed", "incomplete", weight=6),
            _make_check("Tag Policies enabled", "incomplete", weight=6),
            _make_check(
                "CloudTrail organization service enabled", "incomplete", weight=6
            ),
            _make_check("IAM Identity Center configured", "incomplete", weight=6),
            _make_check("CloudTrail trail exists", "incomplete", weight=6),
            _make_check("AWS Config recorder active", "incomplete", weight=6),
        ]
        result = calculate_maturity_level(checks)
        # All weights are 6, so they should still be in the list
        assert len(result["next_level_checks_needed"]) == 7

    def test_error_checks_block_level_5(self):
        """Error checks must prevent Level 5 because posture is unknown."""
        checks = [_make_check(name, "complete") for name in _ALL_CHECK_NAMES]
        checks.append(_make_check("Some errored check", "error"))
        result = calculate_maturity_level(checks)
        assert result["level"] == 4
        assert "Some errored check" in result["next_level_checks_needed"]

    def test_next_checks_ordered_by_weight_descending(self):
        """With differing weights, next-check order is highest-weight-first (F3).

        The prior coverage used all-equal weights, which could not distinguish
        descending order from insertion order. Here every Level 3 check has a
        distinct weight, so the assertion actually pins the ordering.
        """
        checks = [
            _make_check("AWS Organization exists", "complete"),
            _make_check("Management account identified", "complete"),
            _make_check("Minimum 4 accounts", "complete"),
            _make_check("Security OU exists", "complete"),
            # Level 3 checks, all incomplete, each a distinct weight
            _make_check("Service Control Policies enabled", "incomplete", weight=3),
            _make_check("Control Tower deployed", "incomplete", weight=9),
            _make_check("Tag Policies enabled", "incomplete", weight=1),
            _make_check(
                "CloudTrail organization service enabled", "incomplete", weight=7
            ),
            _make_check("IAM Identity Center configured", "incomplete", weight=5),
            _make_check("CloudTrail trail exists", "incomplete", weight=8),
            _make_check("AWS Config recorder active", "incomplete", weight=2),
        ]
        result = calculate_maturity_level(checks)

        needed = result["next_level_checks_needed"]
        # Map name -> weight for the checks we set
        weight_by_name = {c["check"]: c["weight"] for c in checks}
        weights_in_order = [weight_by_name[name] for name in needed]

        # The list must be sorted by weight, highest first.
        assert weights_in_order == sorted(weights_in_order, reverse=True)
        # And concretely: the two highest-weight items lead the list.
        assert needed[0] == "Control Tower deployed"  # weight 9
        assert needed[1] == "CloudTrail trail exists"  # weight 8
