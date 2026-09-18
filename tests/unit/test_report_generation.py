"""Unit tests for src/report/ — FR-10: Report Generation."""

import base64

from src.report.html_report import generate_html, _calculate_axis_scores
from src.report.csv_export import generate_csv


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

        assert "L2" in html
        assert "Established" in html

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
        assert "data:image/svg+xml;base64," in html
        encoded_svg = html.split("data:image/svg+xml;base64,", 1)[1].split('"', 1)[0]
        svg = base64.b64decode(encoded_svg).decode("utf-8")
        # The SVG must declare the SVG namespace, otherwise browsers refuse to
        # render it when it is loaded through an <img> data URI (broken image).
        assert 'xmlns="http://www.w3.org/2000/svg"' in svg
        assert "<svg " in svg
        # Labels use a single theme-neutral gray so they stay legible on both
        # light and dark cards (the chart is a static image and cannot inherit
        # the page theme). No stroke/halo (it reads as a blur on dark), and NOT
        # the old near-black fill (invisible in dark mode).
        assert 'fill="#8a8f98"' in svg
        assert "paint-order" not in svg
        assert 'fill="#1a1a2e"' not in svg
        # The viewBox is padded horizontally so long axis labels are not clipped.
        view_box = svg.split('viewBox="', 1)[1].split('"', 1)[0]
        min_x, _, view_w, _ = (float(v) for v in view_box.split())
        assert min_x < 0 and view_w > 560

    def test_html_contains_executive_summary(self):
        """HTML has total, complete, incomplete, error counts."""
        checks = _make_checks()
        maturity = _make_maturity()
        html = generate_html(checks, maturity)

        assert "Total Checks" in html
        assert "Complete" in html
        assert "Incomplete" in html

    def test_html_contains_theme_toggle(self):
        """HTML has light/dark mode toggle."""
        checks = _make_checks()
        maturity = _make_maturity()
        html = generate_html(checks, maturity)

        assert "toggleTheme" in html
        assert "data-theme" in html

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

    def test_html_no_delegated_admins_section_when_empty(self):
        """HTML omits delegated admins section when list is empty."""
        checks = _make_checks()
        maturity = _make_maturity()
        html = generate_html(checks, maturity, delegated_admins=[])

        assert "Delegated Administrators" not in html

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
