"""HTML Report Generation (FR-10.1).

Generates an interactive HTML report with:
- Maturity level score and progress
- Radar/spider chart over the 7 WA Foundations capability axes
- Executive summary
- Check results table with filtering
- Delegated administrators table
- Light/dark mode toggle
"""

import math
from html import escape as html_escape

from jinja2 import BaseLoader, select_autoescape
from jinja2.sandbox import SandboxedEnvironment

# FR-10.1: Radar chart axis mapping — check names to capability axes
CAPABILITY_AXES = {
    "Multi-Account Environment": [
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
    ],
    "Identity & Access Management": [
        "Service Control Policies enabled",
        "Resource Control Policies enabled",
        "IAM Access Analyzer organization service enabled",
        "IAM Identity Center organization service enabled",
        "IAM Identity Center configured",
        "No IAM users in account",
    ],
    "Central Observability": [
        "CloudTrail organization service enabled",
        "CloudTrail trail exists",
        "CloudTrail organization trail",
    ],
    "Resource & Inventory Management": [
        "Tag Policies enabled",
        "Backup Policies enabled",
        "AWS Config organization service enabled",
        "AWS Backup organization service enabled",
    ],
    "Security & Compliance": [
        "CloudTrail organization service enabled",
        "GuardDuty organization service enabled",
        "Security Hub organization service enabled",
        "CloudTrail trail exists",
        "CloudTrail organization trail",
        "AWS Config recorder active",
        "AWS Config delivery channel active",
        "Log Archive account exists",
    ],
    "Cloud Financial Management": [
        "Tag Policies enabled",
        "Cost Optimization Hub organization service enabled",
        "Cost and Usage Report configured",
    ],
    "Networking & Connectivity": [],
}


def _calculate_axis_scores(checks):
    """Calculate percentage score per capability axis."""
    scores = {}
    for axis_name, check_names in CAPABILITY_AXES.items():
        complete = sum(
            1
            for name in check_names
            if any(
                c.get("check") == name and c.get("status") == "complete" for c in checks
            )
        )
        scores[axis_name] = (
            round((complete / len(check_names)) * 100) if check_names else 0
        )
    return scores


def _build_radar_svg(axis_scores):
    """Render the capability radar inline so reports work without network access."""
    width = 560
    center = 280
    radius = 185
    labels_radius = 235
    axes = list(axis_scores.items())
    axis_count = len(axes)

    def point(distance, index):
        angle = -math.pi / 2 + (2 * math.pi * index / axis_count)
        return (
            center + distance * math.cos(angle),
            center + distance * math.sin(angle),
        )

    def points_for_distance(distance):
        return " ".join(
            f"{x:.1f},{y:.1f}"
            for x, y in (point(distance, index) for index in range(axis_count))
        )

    grid = "\n".join(
        f'<polygon points="{points_for_distance(radius * level / 100)}" '
        'class="radar-grid"/>'
        for level in (25, 50, 75, 100)
    )
    spokes = "\n".join(
        f'<line x1="{center}" y1="{center}" x2="{x:.1f}" y2="{y:.1f}" '
        'class="radar-spoke"/>'
        for x, y in (point(radius, index) for index in range(axis_count))
    )
    value_points = " ".join(
        f"{x:.1f},{y:.1f}"
        for x, y in (
            point(radius * score / 100, index) for index, (_, score) in enumerate(axes)
        )
    )
    # The SVG is inlined into the HTML (not a data-URI image), so the label
    # color follows the page theme via the .radar-label CSS class (near-black on
    # light, white on dark). font-size is in SVG user units; the viewBox is
    # scaled to the responsive chart container, so keep it large enough to
    # stay legible after that scale.
    label_font_size = 20
    # Conservative average glyph width as a fraction of font-size (proportional
    # font). Deliberately on the high side so the computed extents slightly
    # over-estimate and labels never clip.
    char_w = label_font_size * 0.62

    labels = []
    # Track how far label text extends left/right so we can size the viewBox to
    # fit the longest one (rather than hand-tuning a fixed pad that clips when a
    # label is long).
    min_extent = 0.0
    max_extent = float(width)
    for index, (label, score) in enumerate(axes):
        x, y = point(labels_radius, index)
        anchor = "middle"
        if x < center - 20:
            anchor = "end"
        elif x > center + 20:
            anchor = "start"

        text = f"{label} ({score}%)"
        # Width is based on the *rendered* character count. html_escape (applied
        # below) expands entities like '&' -> '&amp;', but the browser draws them
        # as one glyph, so measure the un-escaped text to size the viewBox right.
        text_w = len(text) * char_w
        # Compute the text's left/right extent based on its anchor.
        if anchor == "start":
            left, right = x, x + text_w
        elif anchor == "end":
            left, right = x - text_w, x
        else:
            left, right = x - text_w / 2, x + text_w / 2
        min_extent = min(min_extent, left)
        max_extent = max(max_extent, right)

        labels.append(
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
            f'dominant-baseline="middle" class="radar-label" font-size="{label_font_size}">'
            f"{html_escape(text)}</text>"
        )

    # Size the viewBox to the actual label extents, with a small margin, so long
    # axis labels are never clipped at the edges.
    margin = 12
    view_min_x = min_extent - margin
    view_width = (max_extent - min_extent) + 2 * margin
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_min_x:.1f} 0 {view_width:.1f} {width}" role="img"
    aria-label="WA Foundations capability coverage radar chart">
    <title>WA Foundations capability coverage</title>
    {grid}
    {spokes}
    <polygon points="{value_points}" class="radar-data"/>
    {"".join(labels)}
</svg>"""


def _encode_radar_svg(axis_scores):
    """Return the radar SVG markup for inlining directly in the report HTML.

    The SVG is inlined (rather than embedded as a base64 data-URI image) so the
    label text can follow the page's light/dark theme via CSS. It remains fully
    self-contained, so the report still renders without any network access.
    """
    return _build_radar_svg(axis_scores)


def generate_html(checks, maturity, delegated_admins=None, account_info=None):
    """Generate the interactive HTML report.

    Args:
        checks: list of check result dicts
        maturity: maturity level result dict
        delegated_admins: list of delegated admin dicts (optional)
        account_info: account info dict (optional)

    Returns:
        str: Complete HTML document as string
    """
    if delegated_admins is None:
        delegated_admins = []
    if account_info is None:
        account_info = {}

    axis_scores = _calculate_axis_scores(checks)
    total = len(checks)
    complete = sum(1 for c in checks if c["status"] == "complete")
    incomplete = sum(1 for c in checks if c["status"] == "incomplete")
    errors = sum(1 for c in checks if c["status"] == "error")
    pct = round(complete / total * 100) if total > 0 else 0

    # The report is a standalone HTML document, so use a sandboxed environment
    # with autoescaping instead of relying on a web framework's renderer.
    env = SandboxedEnvironment(
        loader=BaseLoader(),
        autoescape=select_autoescape(default_for_string=True, default=True),
    )
    template = env.from_string(HTML_TEMPLATE)
    rendered = template.render(
        checks=checks,
        maturity=maturity,
        delegated_admins=delegated_admins,
        account_info=account_info,
        axis_scores=axis_scores,
        radar_svg=_encode_radar_svg(axis_scores),
        total=total,
        complete=complete,
        incomplete=incomplete,
        errors=errors,
        pct=pct,
    )
    return "\n".join(line.rstrip() for line in rendered.splitlines()) + "\n"


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WA-Foundations Report</title>
<style>
:root {
    color-scheme: light;
    --bg: #F4F6F8;
    --text: #17202A;
    --card-bg: #FFFFFF;
    --border: #D7DEE7;
    --accent: #1F2A44;
    --accent-soft: #EAF0FA;
    --accent-contrast: #FFFFFF;
    --link: #2F6FED;
    --complete: #147D64;
    --complete-soft: #E8F5F1;
    --incomplete: #B42318;
    --incomplete-soft: #FDECEA;
    --error: #935B00;
    --error-soft: #FFF4DE;
    --progress-bg: #E7ECF2;
    --shadow: 0 2px 10px rgba(31, 42, 68, 0.08);
    --radar-grid: #68778A;
    --radar-fill: #FF9900;
    --radar-stroke: #B84F00;
}
[data-theme="dark"] {
    color-scheme: dark;
    --bg: #0F1724;
    --text: #E7ECF3;
    --card-bg: #182235;
    --border: #334155;
    --accent: #78A9FF;
    --accent-soft: #213654;
    --accent-contrast: #0F1724;
    --link: #8BB7FF;
    --complete: #50D3AA;
    --complete-soft: #173A35;
    --incomplete: #FF8A80;
    --incomplete-soft: #40252C;
    --error: #F5B95F;
    --error-soft: #3D321F;
    --progress-bg: #253249;
    --shadow: 0 2px 12px rgba(0, 0, 0, 0.28);
    --radar-grid: #C2CBD5;
    --radar-fill: #FFAD33;
    --radar-stroke: #FFC066;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 2rem;
    max-width: 1440px;
    margin: 0 auto;
    transition: background-color 0.2s, color 0.2s;
}
h1 { color: var(--accent); font-size: 1.8rem; margin-bottom: 0.5rem; }
h2 { font-size: 1.3rem; margin: 1.5rem 0 0.8rem; color: var(--accent); }
.header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2rem;
    padding-bottom: 1.25rem;
    border-bottom: 1px solid var(--border);
}
.report-layout {
    display: grid;
    grid-template-columns: 210px minmax(0, 1fr);
    gap: 1.5rem;
    align-items: start;
}
.report-content { min-width: 0; }
.report-section { scroll-margin-top: 1rem; }
.section-nav {
    position: sticky;
    top: 1rem;
    padding: 1rem;
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    box-shadow: var(--shadow);
}
.section-nav-title {
    display: block;
    margin-bottom: 0.75rem;
    font-size: 0.78rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    opacity: 0.7;
}
.section-nav a {
    display: block;
    padding: 0.55rem 0.7rem;
    border-radius: 4px;
    color: var(--text);
    font-size: 0.88rem;
    text-decoration: none;
}
.section-nav a:hover { background: var(--accent-soft); }
.section-nav a.active {
    background: var(--accent);
    color: var(--accent-contrast);
    font-weight: 600;
}
.mobile-section-nav {
    display: none;
    margin-bottom: 1rem;
}
.mobile-section-nav label {
    font-size: 0.85rem;
    font-weight: 600;
    white-space: nowrap;
}
.mobile-section-nav select {
    width: 100%;
    padding: 0.55rem 0.7rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--card-bg);
    color: var(--text);
    font: inherit;
}
.theme-toggle {
    cursor: pointer;
    padding: 0.5rem 1rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--card-bg);
    color: var(--text);
    font-size: 0.9rem;
}
.theme-toggle:hover { background: var(--accent-soft); }
.theme-toggle:focus-visible,
.section-nav a:focus-visible,
.mobile-section-nav select:focus-visible,
.filters button:focus-visible,
a:focus-visible {
    outline: 3px solid var(--link);
    outline-offset: 2px;
}
.card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    box-shadow: var(--shadow);
}
.card > h2:first-child { margin-top: 0; }
.overview-grid {
    display: grid;
    grid-template-columns: minmax(260px, 0.9fr) minmax(0, 1.6fr);
    gap: 2rem;
    align-items: center;
}
.overview-grid .maturity-info { margin-bottom: 0; }
.overview-stats {
    grid-template-columns: repeat(5, minmax(80px, 1fr));
    margin-bottom: 0;
}
.overview-stats .stat-value { font-size: 1.8rem; }
.account-context {
    margin-top: 1.25rem;
    padding-top: 0.9rem;
    border-top: 1px solid var(--border);
    font-size: 0.85rem;
    opacity: 0.75;
}
.maturity-badge {
    display: inline-block;
    font-size: 2rem;
    font-weight: bold;
    padding: 0.5rem 1.5rem;
    border-radius: 8px;
    background: var(--accent);
    color: var(--accent-contrast);
    margin-right: 1rem;
}
.maturity-info { display: flex; align-items: center; margin-bottom: 1rem; }
.maturity-ladder {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 0.6rem;
    margin: 1rem 0 1.25rem;
}
.maturity-level-step {
    min-width: 0;
    padding: 0.75rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    opacity: 0.65;
}
.maturity-level-step.achieved {
    border-color: var(--complete);
    background: var(--complete-soft);
    opacity: 0.85;
}
.maturity-level-step.current {
    border: 2px solid var(--accent);
    background: var(--accent-soft);
    opacity: 1;
}
.maturity-level-step.next {
    border-style: dashed;
    border-color: var(--accent);
    opacity: 1;
}
.level-step-number { display: block; font-weight: 700; }
.level-step-name {
    display: block;
    margin: 0.15rem 0 0.35rem;
    font-size: 0.85rem;
}
.level-step-state {
    display: block;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    opacity: 0.75;
}
.level-step-progress { display: block; margin-top: 0.3rem; font-size: 0.8rem; }
.maturity-methodology { margin-top: 1.25rem; }
.methodology-intro { margin: 0.8rem 0; font-size: 0.9rem; }
.level-criteria-section {
    margin-top: 0.8rem;
    padding-top: 0.8rem;
    border-top: 1px solid var(--border);
}
.level-criteria-heading {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: baseline;
}
.level-criteria-heading h3 { font-size: 1rem; }
.level-criteria-summary { font-size: 0.8rem; opacity: 0.75; }
.level-description { margin: 0.35rem 0; font-size: 0.85rem; opacity: 0.8; }
.criteria-list { list-style: none; margin-top: 0.5rem; }
.criteria-list li {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 0.75rem;
    padding: 0.35rem 0;
    border-bottom: 1px dotted var(--border);
    font-size: 0.85rem;
}
.criteria-list li:last-child { border-bottom: 0; }
.criterion-detail {
    display: block;
    margin-top: 0.15rem;
    font-size: 0.75rem;
    opacity: 0.7;
}
.criterion-status { white-space: nowrap; font-weight: 600; }
.criterion-complete .criterion-status { color: var(--complete); }
.criterion-incomplete .criterion-status { color: var(--incomplete); }
.criterion-error .criterion-status { color: var(--error); }
.criterion-not_assessed .criterion-status { opacity: 0.65; }
.progress-bar {
    width: 100%;
    height: 12px;
    background: var(--progress-bg);
    border-radius: 6px;
    overflow: hidden;
    margin: 0.5rem 0;
}
.progress-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 6px;
    transition: width 0.5s;
}
.stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1rem;
    margin-bottom: 1rem;
}
.stat-item { text-align: center; }
.stat-value { font-size: 2rem; font-weight: bold; }
.stat-label { font-size: 0.85rem; opacity: 0.7; }
.stat-complete .stat-value { color: var(--complete); }
.stat-incomplete .stat-value { color: var(--incomplete); }
.stat-error .stat-value { color: var(--error); }
.chart-container { max-width: 760px; margin: 0 auto; }
.chart-container svg { display: block; width: 100%; height: auto; }
/* Radar geometry and labels remain legible in both report themes. */
.radar-grid,
.radar-spoke {
    fill: none;
    stroke: var(--radar-grid);
    stroke-opacity: 0.65;
    stroke-width: 1.25;
    vector-effect: non-scaling-stroke;
}
.radar-data {
    fill: var(--radar-fill);
    fill-opacity: 0.3;
    stroke: var(--radar-stroke);
    stroke-width: 2.5;
    stroke-linejoin: round;
    vector-effect: non-scaling-stroke;
}
.radar-label {
    fill: var(--text);
    stroke: var(--card-bg);
    stroke-width: 2.5px;
    paint-order: stroke;
    stroke-linejoin: round;
    font-weight: 700;
}
[data-theme="dark"] .radar-grid,
[data-theme="dark"] .radar-spoke { stroke-opacity: 0.6; }
[data-theme="dark"] .radar-data { fill-opacity: 0.28; }
.filters { margin: 1rem 0; }
.filters button {
    padding: 0.4rem 1rem;
    margin-right: 0.5rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--card-bg);
    color: var(--text);
    cursor: pointer;
}
.filters button:hover { background: var(--accent-soft); }
.filters button.active {
    background: var(--accent);
    color: var(--accent-contrast);
    border-color: var(--accent);
}
table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
}
th, td {
    padding: 0.6rem 0.8rem;
    text-align: left;
    border-bottom: 1px solid var(--border);
}
th { font-weight: 600; background: var(--accent-soft); position: sticky; top: 0; }
.status-complete { color: var(--complete); font-weight: 600; }
.status-incomplete { color: var(--incomplete); font-weight: 600; }
.status-error { color: var(--error); font-weight: 600; }
.status-legend {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.75rem;
    margin: 0.75rem 0;
}
.status-legend-item {
    padding: 0.75rem;
    border: 1px solid var(--border);
    border-left-width: 4px;
    border-radius: 5px;
    font-size: 0.85rem;
}
.status-legend-item strong {
    display: block;
    margin-bottom: 0.25rem;
}
.status-legend-complete {
    border-left-color: var(--complete);
    background: var(--complete-soft);
}
.status-legend-incomplete {
    border-left-color: var(--incomplete);
    background: var(--incomplete-soft);
}
.status-legend-error {
    border-left-color: var(--error);
    background: var(--error-soft);
}
.status-legend-complete strong { color: var(--complete); }
.status-legend-incomplete strong { color: var(--incomplete); }
.status-legend-error strong { color: var(--error); }
.status-scoring-note {
    margin-bottom: 1rem;
    font-size: 0.82rem;
    opacity: 0.75;
}
a { color: var(--link); }
.next-steps li { margin: 0.3rem 0; }
.assessment-scope-note {
    margin: 1rem 0 0;
    padding: 0.75rem 1rem;
    border-left: 4px solid var(--accent);
    background: var(--accent-soft);
    font-size: 0.9rem;
}
.delegated-table { margin-top: 1rem; }
@media (max-width: 1100px) {
    .overview-grid { grid-template-columns: 1fr; }
}
@media (max-width: 900px) {
    .report-layout { display: block; }
    .section-nav { display: none; }
    .mobile-section-nav {
        position: sticky;
        top: 0;
        z-index: 10;
        display: grid;
        grid-template-columns: auto minmax(0, 1fr);
        gap: 0.75rem;
        align-items: center;
        padding: 0.75rem;
        background: var(--bg);
        border: 1px solid var(--border);
        border-radius: 6px;
    }
    .report-section { scroll-margin-top: 5rem; }
}
@media (max-width: 700px) {
    body { padding: 1rem; }
    .header { align-items: flex-start; gap: 1rem; }
    .maturity-ladder { grid-template-columns: 1fr; }
    .maturity-info { align-items: flex-start; }
    .overview-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .status-legend { grid-template-columns: 1fr; }
}
</style>
</head>
<body>
<div class="header">
    <h1>Well Architected Foundations Assessment Report</h1>
    <button class="theme-toggle" onclick="toggleTheme()">🌓 Toggle Theme</button>
</div>

<div class="mobile-section-nav">
    <label for="sectionJump">Jump to section</label>
    <select id="sectionJump" onchange="navigateToSection(this.value)">
        <option value="overview">Assessment Overview</option>
        <option value="maturity">Maturity Progress</option>
        <option value="capabilities">Capability Coverage</option>
        <option value="checks">Check Results</option>
        {% if delegated_admins %}
        <option value="delegated-admins">Delegated Administrators</option>
        {% endif %}
        {% if maturity.scoring_model %}
        <option value="methodology">Maturity Methodology</option>
        {% endif %}
    </select>
</div>

<div class="report-layout">
<aside class="section-nav" aria-label="Report sections">
    <span class="section-nav-title">Report sections</span>
    <nav>
        <a class="active" href="#overview" aria-current="location">Assessment Overview</a>
        <a href="#maturity">Maturity Progress</a>
        <a href="#capabilities">Capability Coverage</a>
        <a href="#checks">Check Results</a>
        {% if delegated_admins %}
        <a href="#delegated-admins">Delegated Administrators</a>
        {% endif %}
        {% if maturity.scoring_model %}
        <a href="#methodology">Maturity Methodology</a>
        {% endif %}
    </nav>
</aside>

<main class="report-content">
<!-- Assessment Overview -->
<div class="card report-section" id="overview">
    <h2>Assessment Overview</h2>
    <div class="overview-grid">
        <div class="maturity-info">
            <span class="maturity-badge">L{{ maturity.level }}</span>
            <div>
                <strong>{{ maturity.name }}</strong>
                <p style="opacity:0.8;font-size:0.9rem;">{{ maturity.description }}</p>
            </div>
        </div>
        <div class="stats overview-stats">
            <div class="stat-item"><div class="stat-value">{{ total }}</div><div class="stat-label">Total Checks</div></div>
            <div class="stat-item stat-complete"><div class="stat-value">{{ complete }}</div><div class="stat-label">Complete</div></div>
            <div class="stat-item stat-incomplete"><div class="stat-value">{{ incomplete }}</div><div class="stat-label">Incomplete</div></div>
            <div class="stat-item stat-error"><div class="stat-value">{{ errors }}</div><div class="stat-label">Errors</div></div>
            <div class="stat-item"><div class="stat-value">{{ pct }}%</div><div class="stat-label">Completion</div></div>
        </div>
    </div>
    {% if account_info and not account_info.get('is_management_account', False) %}
    <p class="assessment-scope-note">
        <strong>Limited assessment:</strong>
        This maturity level is provisional for the {{ account_info.get('account_type', 'non-management') }} account.
        Organization-wide checks were not run. Run the Well Architected Foundations Assessments tool from the
        management account for a complete maturity assessment.
    </p>
    {% endif %}
    <p class="account-context">Account: {{ account_info.get('account_id', 'N/A') }} ({{ account_info.get('account_type', 'N/A') }})</p>
</div>

<!-- Maturity Progress -->
<div class="card report-section" id="maturity">
    <h2>Maturity Progress</h2>
    {% if maturity.scoring_model %}
    <div class="maturity-ladder" aria-label="Maturity level progression">
        {% for level in maturity.scoring_model.levels %}
        <div class="maturity-level-step {{ level.state }}">
            <span class="level-step-number">Level {{ level.level }}</span>
            <span class="level-step-name">{{ level.name }}</span>
            <span class="level-step-state">
                {% if level.state == "achieved" %}
                Achieved
                {% elif level.state == "current" %}
                Current level
                {% elif level.state == "next" %}
                Next target
                {% else %}
                Later level
                {% endif %}
            </span>
            <span class="level-step-progress">
                {% if level.criteria_count %}
                {{ level.complete_count }}/{{ level.criteria_count }} criteria
                {% else %}
                Baseline
                {% endif %}
            </span>
        </div>
        {% endfor %}
    </div>
    {% endif %}
    {% if maturity.next_level %}
    <p>Progress toward Level {{ maturity.next_level }}:</p>
    <div class="progress-bar">
        <div class="progress-fill" style="width: {{ maturity.next_level_progress }}%"></div>
    </div>
    <p style="font-size:0.85rem;opacity:0.7;">{{ maturity.next_level_progress }}% complete</p>
    {% if maturity.next_level_checks_needed %}
    <h3 style="margin-top:1rem;font-size:1rem;">Next Steps (highest impact first):</h3>
    <ol class="next-steps">
        {% for check_name in maturity.next_level_checks_needed[:5] %}
        <li>{{ check_name }}</li>
        {% endfor %}
    </ol>
    {% endif %}
    {% else %}
    <p style="color:var(--complete);font-weight:600;">🎉 All Phase 1 criteria met!</p>
    {% endif %}
</div>

<!-- Radar Chart -->
<div class="card report-section" id="capabilities">
    <h2>Capability Coverage (WA Foundations)</h2>
    <div class="chart-container" id="radarChart">
        {{ radar_svg | safe }}
    </div>
</div>

<!-- Check Results Table -->
<div class="card report-section" id="checks">
    <h2>Check Results</h2>
    <div class="status-legend" aria-label="Check result status definitions">
        <div class="status-legend-item status-legend-complete">
            <strong>Complete</strong>
            Verified and meets the criterion.
        </div>
        <div class="status-legend-item status-legend-incomplete">
            <strong>Incomplete</strong>
            Verified but does not meet the criterion.
        </div>
        <div class="status-legend-item status-legend-error">
            <strong>Error</strong>
            Could not be reliably assessed, usually because of permissions or an AWS API failure.
        </div>
    </div>
    <p class="status-scoring-note">
        Only Complete results contribute to completion and capability scores.
        Incomplete and Error results do not satisfy maturity criteria.
        An Error does not necessarily mean the configuration is incorrect.
    </p>
    <div class="filters">
        <button class="active" onclick="filterChecks('all', this)">All ({{ total }})</button>
        <button onclick="filterChecks('complete', this)">Complete ({{ complete }})</button>
        <button onclick="filterChecks('incomplete', this)">Incomplete ({{ incomplete }})</button>
        <button onclick="filterChecks('error', this)">Errors ({{ errors }})</button>
    </div>
    <table id="checksTable">
        <thead>
            <tr>
                <th>Check</th>
                <th>Status</th>
                <th>Required</th>
                <th>LoE</th>
                <th>Remediation</th>
            </tr>
        </thead>
        <tbody>
            {% for check in checks %}
            <tr data-status="{{ check.status }}">
                <td title="{{ check.description }}">{{ check.check }}</td>
                <td class="status-{{ check.status }}">{{ check.status }}</td>
                <td>{{ "Yes" if check.required else "No" }}</td>
                <td>{{ check.loe }}</td>
                <td><a href="{{ check.remediationLink }}" target="_blank" rel="noopener">Fix →</a></td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>

{% if delegated_admins %}
<!-- Delegated Administrators -->
<div class="card report-section" id="delegated-admins">
    <h2>Delegated Administrators</h2>
    <table class="delegated-table">
        <thead>
            <tr>
                <th>Account ID</th>
                <th>Account Name</th>
                <th>Delegated Services</th>
            </tr>
        </thead>
        <tbody>
            {% for admin in delegated_admins %}
            <tr>
                <td>{{ admin.accountId }}</td>
                <td>{{ admin.accountName }}</td>
                <td>{{ admin.services | join(', ') }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endif %}

{% if maturity.scoring_model %}
<!-- Maturity Methodology -->
<div class="card report-section" id="methodology">
    <h2>Maturity Methodology</h2>
    <p class="methodology-intro">
        {{ maturity.scoring_model.rule }}
        {{ maturity.scoring_model.weight_note }}
    </p>
    <div class="maturity-methodology">
        {% for level in maturity.scoring_model.levels %}
        <section class="level-criteria-section">
            <div class="level-criteria-heading">
                <h3>Level {{ level.level }} — {{ level.name }}</h3>
                <span class="level-criteria-summary">
                    {% if level.criteria_count %}
                    {{ level.complete_count }}/{{ level.criteria_count }} complete
                    {% else %}
                    Baseline level
                    {% endif %}
                </span>
            </div>
            <p class="level-description">{{ level.description }}</p>
            {% if level.criteria %}
            <ul class="criteria-list">
                {% for criterion in level.criteria %}
                <li class="criterion-{{ criterion.status }}">
                    <span>
                        {{ criterion.name }}
                        {% if criterion.detail %}
                        <small class="criterion-detail">{{ criterion.detail }}</small>
                        {% endif %}
                    </span>
                    <span class="criterion-status">
                        {% if criterion.status == "complete" %}
                        ✓ Complete
                        {% elif criterion.status == "incomplete" %}
                        ○ Not complete
                        {% elif criterion.status == "error" %}
                        ! Error
                        {% else %}
                        — Not assessed
                        {% endif %}
                    </span>
                </li>
                {% endfor %}
            </ul>
            {% endif %}
        </section>
        {% endfor %}
    </div>
</div>
{% endif %}
</main>
</div>

<script>
// Section navigation
function navigateToSection(sectionId) {
    const section = document.getElementById(sectionId);
    if (section) {
        section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

function setActiveSection(sectionId) {
    document.querySelectorAll('.section-nav a').forEach(link => {
        const isActive = link.getAttribute('href') === `#${sectionId}`;
        link.classList.toggle('active', isActive);
        if (isActive) {
            link.setAttribute('aria-current', 'location');
        } else {
            link.removeAttribute('aria-current');
        }
    });

    const sectionJump = document.getElementById('sectionJump');
    if (sectionJump && sectionJump.querySelector(`option[value="${sectionId}"]`)) {
        sectionJump.value = sectionId;
    }
}

const sectionObserver = new IntersectionObserver(entries => {
    const visibleSections = entries
        .filter(entry => entry.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
    if (visibleSections.length) {
        setActiveSection(visibleSections[0].target.id);
    }
}, { rootMargin: '-10% 0px -75% 0px' });

document.querySelectorAll('.report-section').forEach(section => {
    sectionObserver.observe(section);
});

// Filter
function filterChecks(status, btn) {
    document.querySelectorAll('.filters button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('#checksTable tbody tr').forEach(row => {
        row.style.display = (status === 'all' || row.dataset.status === status) ? '' : 'none';
    });
}

// Theme Toggle
function toggleTheme() {
    const html = document.documentElement;
    html.dataset.theme = html.dataset.theme === 'dark' ? 'light' : 'dark';
}
</script>
</body>
</html>"""
