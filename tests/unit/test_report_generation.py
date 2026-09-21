"""Unit tests for src/report/ — FR-10: Report Generation."""

from src.checks.maturity import calculate_maturity_level
from src.report.csv_export import generate_csv
from src.report.html_report import _calculate_axis_scores, generate_html


def _make_checks():
    """Create a sample set of checks for testing."""
    return [
        {
            "check": "AWS Organization exists",
            "description": "An AWS Organization should exist.",
            "status": "complete",
            "required": True,
            "weight": 6,
            "loe": 1,
            "remediationLink": "https://docs.aws.amazon.com/example",
        },
        {
            "check": "Service Control Policies enabled",
            "description": "SCPs should be enabled.",
            "status": "incomplete",
            "required": True,
            "weight": 6,
            "loe": 1,
            "remediationLink": "https://docs.aws.amazon.com/scp",
        },
        {
            "check": "Control Tower deployed",
            "description": "Control Tower should be deployed.",
            "status": "error",
            "required": True,
            "weight": 6,
            "loe": 6,
            "remediationLink": "https://docs.aws.amazon.com/ct",
            "error": "AccessDenied",
        },
    ]


def _make_maturity():
    return {
        "level": 2,
        "name": "Established",
        "description": "AWS Organizations in place with OU structure.",
        "next_level": 3,
        "next_level_progress": 45.5,
        "next_level_checks_needed": ["SCP enabled", "Control Tower deployed"],
    }


# ============================================================================
# HTML Report
# ============================================================================


class TestGenerateHtml:
    def test_html_contains_maturity_level(self):
        """HTML report shows maturity level badge."""
        checks = _make_checks()
        maturity = _make_maturity()
        html = generate_html(checks, maturity)

        assert "<title>WA-Foundations Report</title>" in html
        assert "<h1>Well Architected Foundations Assessment Report</h1>" in html
        assert "<h2>Assessment Overview</h2>" in html
        assert "<h2>Maturity Progress</h2>" in html
        assert "L2" in html
        assert "Established" in html

    def test_html_explains_maturity_levels_from_scoring_result(self):
        """HTML shows the scoring rule, ladder, and detailed criteria."""
        checks = _make_checks()
        maturity = calculate_maturity_level(checks)
        html = generate_html(checks, maturity)

        assert "How this level is determined" not in html
        assert "Maturity Methodology" in html
        assert '<div class="maturity-methodology">' in html
        assert '<details class="maturity-methodology">' not in html
        assert "highest maturity level whose required criteria are all complete" in html
        assert "Well Architected Foundations Assessments model" in html
        assert "WAFA" not in html
        assert "Check weights prioritize recommended next steps" in html
        assert "Level 1 — Base" in html
        assert "Level 5 — Expert" in html
        assert "1/4 criteria" in html
        assert "— Not assessed" in html
        assert 'class="maturity-level-step current"' in html
        assert html.index("Check Results") < html.index("Maturity Methodology")
        assert 'aria-label="Report sections"' in html
        assert 'href="#overview"' in html
        assert 'href="#maturity"' in html
        assert 'href="#methodology"' in html
        assert 'id="sectionJump"' in html
        assert "IntersectionObserver" in html

    def test_html_caveats_limited_account_maturity(self):
        """Limited-account reports explain that maturity is provisional."""
        checks = _make_checks()
        maturity = _make_maturity()
        html = generate_html(
            checks,
            maturity,
            account_info={
                "account_id": "222222222222",
                "account_type": "member",
                "is_management_account": False,
            },
        )

        assert "Limited assessment" in html
        assert "maturity level is provisional" in html
        assert "management account for a complete maturity assessment" in html

    def test_html_contains_check_table(self):
        """HTML report contains all check names."""
        checks = _make_checks()
        maturity = _make_maturity()
        html = generate_html(checks, maturity)

        assert "AWS Organization exists" in html
        assert "Service Control Policies enabled" in html
        assert "Control Tower deployed" in html
        assert 'aria-label="Check result status definitions"' in html
        assert "Verified and meets the criterion." in html
        assert "Verified but does not meet the criterion." in html
        assert "Could not be reliably assessed" in html
        assert (
            "An Error does not necessarily mean the configuration is incorrect." in html
        )

    def test_html_escapes_untrusted_check_content(self):
        """Dynamic check content cannot inject HTML or script tags."""
        checks = _make_checks()
        checks[0]["description"] = '<script>alert("xss")</script>'
        maturity = _make_maturity()
        html = generate_html(checks, maturity)

        assert "<script>alert" not in html
        assert "&lt;script&gt;alert" in html

    def test_html_contains_radar_chart(self):
        """HTML report includes a self-contained encoded radar chart."""
        checks = _make_checks()
        maturity = _make_maturity()
        html = generate_html(checks, maturity)

        assert 'id="radarChart"' in html
        # The SVG is inlined directly in the HTML (not a base64 data-URI image)
        # so the label text can follow the page's light/dark theme via CSS.
        assert "data:image/svg+xml;base64," not in html
        svg = html.split("<svg ", 1)[1].split("</svg>", 1)[0]
        # Namespace still declared (harmless when inline, required if extracted).
        assert 'xmlns="http://www.w3.org/2000/svg"' in svg
        # Labels are theme-aware via the .radar-label class and shared text
        # variable — no hardcoded per-label fill in the SVG.
        assert 'class="radar-label"' in svg
        assert 'font-size="20"' in svg
        assert 'fill="#1a1a2e"' not in svg
        assert 'fill="#8a8f98"' not in svg
        # Theme-aware CSS drives high-contrast geometry, data, and label colors.
        assert 'class="radar-grid"' in svg
        assert 'class="radar-spoke"' in svg
        assert 'class="radar-data"' in svg
        assert ".radar-label" in html
        assert ".radar-grid" in html
        assert ".radar-data" in html
        assert "fill: var(--text);" in html
        # The viewBox is padded horizontally so long axis labels are not clipped.
        view_box = svg.split('viewBox="', 1)[1].split('"', 1)[0]
        min_x, _, view_w, _ = (float(v) for v in view_box.split())
        assert min_x < 0 and view_w > 560

    def test_html_contains_assessment_overview(self):
        """HTML overview combines maturity and check-result totals."""
        checks = _make_checks()
        maturity = _make_maturity()
        html = generate_html(checks, maturity)

        assert "Assessment Overview" in html
        assert "Executive Summary" not in html
        assert "Total Checks" in html
        assert "Complete" in html
        assert "Incomplete" in html
        assert html.index("Assessment Overview") < html.index("Maturity Progress")

    def test_html_contains_theme_toggle(self):
        """HTML has light/dark mode toggle."""
        checks = _make_checks()
        maturity = _make_maturity()
        html = generate_html(checks, maturity)

        assert "toggleTheme" in html
        assert "data-theme" in html
        assert "--accent: #1F2A44;" in html
        assert "--accent: #78A9FF;" in html
        assert "--link: #2F6FED;" in html
        assert "--radar-fill: #FF9900;" in html

    def test_html_contains_delegated_admins(self):
        """HTML shows delegated administrators when provided."""
        checks = _make_checks()
        maturity = _make_maturity()
        admins = [
            {
                "accountId": "222222222222",
                "accountName": "Security",
                "services": ["guardduty.amazonaws.com"],
            }
        ]
        html = generate_html(checks, maturity, delegated_admins=admins)

        assert "222222222222" in html
        assert "Security" in html
        assert "guardduty.amazonaws.com" in html
        assert 'href="#delegated-admins"' in html
        assert 'id="delegated-admins"' in html

    def test_html_no_delegated_admins_section_when_empty(self):
        """HTML omits delegated admins section when list is empty."""
        checks = _make_checks()
        maturity = _make_maturity()
        html = generate_html(checks, maturity, delegated_admins=[])

        assert "Delegated Administrators" not in html
        assert 'href="#delegated-admins"' not in html

    def test_html_contains_remediation_links(self):
        """HTML has remediation links for each check."""
        checks = _make_checks()
        maturity = _make_maturity()
        html = generate_html(checks, maturity)

        assert "https://docs.aws.amazon.com/example" in html
        assert "Fix →" in html


class TestCalculateAxisScores:
    def test_all_complete(self):
        """All checks complete → 100% per axis."""
        checks = [
            {"check": "AWS Organization exists", "status": "complete"},
            {"check": "Management account identified", "status": "complete"},
            {"check": "Minimum 4 accounts", "status": "complete"},
            {"check": "Log Archive account exists", "status": "complete"},
            {"check": "Audit account exists", "status": "complete"},
            {"check": "Service Control Policies enabled", "status": "complete"},
            {"check": "Tag Policies enabled", "status": "complete"},
            {"check": "Backup Policies enabled", "status": "complete"},
            {"check": "Resource Control Policies enabled", "status": "complete"},
            {"check": "Security OU exists", "status": "complete"},
            {"check": "Workloads OU exists", "status": "complete"},
            {"check": "Infrastructure OU exists", "status": "complete"},
        ]
        scores = _calculate_axis_scores(checks)
        assert scores["Multi-Account Environment"] == 100

    def test_networking_axis_is_explicit_gap(self):
        """Networking remains visible as a zero-score Phase 1 gap."""
        checks = [{"check": "Some check", "status": "complete"}]
        scores = _calculate_axis_scores(checks)
        assert scores["Networking & Connectivity"] == 0
        assert len(scores) == 7

    def test_report_has_no_external_chart_dependency(self):
        """The report embeds the radar and has no external chart dependency."""
        html = generate_html(_make_checks(), _make_maturity())
        assert 'id="radarChart"' in html
        assert "cdn.jsdelivr.net" not in html
        assert all(line == line.rstrip() for line in html.splitlines())

    def test_partial_scores(self):
        """Partial completion shows proportional score."""
        checks = [
            {"check": "CloudTrail organization service enabled", "status": "complete"},
            {"check": "CloudTrail trail exists", "status": "incomplete"},
            {"check": "CloudTrail organization trail", "status": "incomplete"},
        ]
        scores = _calculate_axis_scores(checks)
        # 1 out of 3 for Central Observability
        assert scores["Central Observability"] == 33


# ============================================================================
# CSV Export
# ============================================================================


class TestGenerateCsv:
    def test_csv_has_header(self):
        """CSV starts with header row."""
        checks = _make_checks()
        csv_content = generate_csv(checks)

        lines = csv_content.strip().split("\n")
        assert "Check Name" in lines[0]
        assert "Status" in lines[0]
        assert "Required" in lines[0]

    def test_csv_has_all_rows(self):
        """CSV has one row per check + header."""
        checks = _make_checks()
        csv_content = generate_csv(checks)

        lines = csv_content.strip().split("\n")
        assert len(lines) == 4  # 1 header + 3 data rows

    def test_csv_contains_check_data(self):
        """CSV contains actual check data."""
        checks = _make_checks()
        csv_content = generate_csv(checks)

        assert "AWS Organization exists" in csv_content
        assert "complete" in csv_content
        assert "incomplete" in csv_content
        assert "error" in csv_content
        assert "https://docs.aws.amazon.com/example" in csv_content

    def test_csv_error_field(self):
        """CSV includes error message for error checks."""
        checks = _make_checks()
        csv_content = generate_csv(checks)

        assert "AccessDenied" in csv_content
