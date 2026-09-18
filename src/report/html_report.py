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
        'fill="none" stroke="#9aa0a6" stroke-opacity="0.35"/>'
        for level in (25, 50, 75, 100)
    )
    spokes = "\n".join(
        f'<line x1="{center}" y1="{center}" x2="{x:.1f}" y2="{y:.1f}" '
        'stroke="#9aa0a6" stroke-opacity="0.35"/>'
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
    # scaled down to the chart container (~500px), so keep it large enough to
    # stay legible after that scale.
    label_font_size = 18
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
    <polygon points="{value_points}" fill="#ff9900" fill-opacity="0.22"
        stroke="#ff9900" stroke-width="2"/>
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
    pct = round((complete / total * 100)) if total > 0 else 0

    # The report is a standalone HTML document, so use a sandboxed environment
    # with autoescaping instead of relying on a web framework's renderer.
    env = SandboxedEnvironment(
        loader=BaseLoader(),
        autoescape=select_autoescape(default_for_string=True, default=True),
    )
    template = env.from_string(HTML_TEMPLATE)
    return template.render(
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


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WAFA Report</title>
<style>
:root {
    --bg: #ffffff;
    --text: #1a1a2e;
    --card-bg: #f8f9fa;
    --border: #e0e0e0;
    --accent: #232f3e;
    --complete: #1b8a4a;
    --incomplete: #d13212;
    --error: #8d6e00;
    --progress-bg: #e9ecef;
}
[data-theme="dark"] {
    --bg: #1a1a2e;
    --text: #e0e0e0;
    --card-bg: #16213e;
    --border: #2a2a4a;
    --accent: #ff9900;
    --complete: #2ecc71;
    --incomplete: #ff6b6b;
    --error: #f39c12;
    --progress-bg: #2a2a4a;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 2rem;
    max-width: 1200px;
    margin: 0 auto;
    transition: all 0.3s;
}
h1 { font-size: 1.8rem; margin-bottom: 0.5rem; }
h2 { font-size: 1.3rem; margin: 1.5rem 0 0.8rem; color: var(--accent); }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; }
.theme-toggle {
    cursor: pointer;
    padding: 0.5rem 1rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--card-bg);
    color: var(--text);
    font-size: 0.9rem;
}
.card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
}
.maturity-badge {
    display: inline-block;
    font-size: 2rem;
    font-weight: bold;
    padding: 0.5rem 1.5rem;
    border-radius: 8px;
    background: var(--accent);
    color: white;
    margin-right: 1rem;
}
.maturity-info { display: flex; align-items: center; margin-bottom: 1rem; }
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
.chart-container { max-width: 500px; margin: 0 auto; }
.chart-container svg { display: block; width: 100%; height: auto; }
/* Radar axis labels follow the theme: near-black on light, white on dark. */
.radar-label { fill: #1a1a2e; font-weight: 600; }
[data-theme="dark"] .radar-label { fill: #ffffff; }
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
.filters button.active { background: var(--accent); color: white; border-color: var(--accent); }
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
th { font-weight: 600; background: var(--card-bg); position: sticky; top: 0; }
.status-complete { color: var(--complete); font-weight: 600; }
.status-incomplete { color: var(--incomplete); font-weight: 600; }
.status-error { color: var(--error); font-weight: 600; }
a { color: var(--accent); }
.next-steps li { margin: 0.3rem 0; }
.assessment-scope-note {
    margin: 1rem 0 0;
    padding: 0.75rem 1rem;
    border-left: 4px solid var(--accent);
    background: var(--progress-bg);
    font-size: 0.9rem;
}
.delegated-table { margin-top: 1rem; }
</style>
</head>
<body>
<div class="header">
    <h1>WAFA Assessment Report</h1>
    <button class="theme-toggle" onclick="toggleTheme()">🌓 Toggle Theme</button>
</div>

<!-- Maturity Level -->
<div class="card">
    <h2>Maturity Level</h2>
    <div class="maturity-info">
        <span class="maturity-badge">L{{ maturity.level }}</span>
        <div>
            <strong>{{ maturity.name }}</strong>
            <p style="opacity:0.8;font-size:0.9rem;">{{ maturity.description }}</p>
        </div>
    </div>
    {% if account_info and not account_info.get('is_management_account', False) %}
    <p class="assessment-scope-note">
        <strong>Limited assessment:</strong>
        This maturity level is provisional for the {{ account_info.get('account_type', 'non-management') }} account.
        Organization-wide checks were not run. Run WAFA from the management account for a complete maturity assessment.
    </p>
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

<!-- Executive Summary -->
<div class="card">
    <h2>Executive Summary</h2>
    <div class="stats">
        <div class="stat-item"><div class="stat-value">{{ total }}</div><div class="stat-label">Total Checks</div></div>
        <div class="stat-item stat-complete"><div class="stat-value">{{ complete }}</div><div class="stat-label">Complete</div></div>
        <div class="stat-item stat-incomplete"><div class="stat-value">{{ incomplete }}</div><div class="stat-label">Incomplete</div></div>
        <div class="stat-item stat-error"><div class="stat-value">{{ errors }}</div><div class="stat-label">Errors</div></div>
        <div class="stat-item"><div class="stat-value">{{ pct }}%</div><div class="stat-label">Completion</div></div>
    </div>
    <p style="font-size:0.85rem;opacity:0.7;">Account: {{ account_info.get('account_id', 'N/A') }} ({{ account_info.get('account_type', 'N/A') }})</p>
</div>

<!-- Radar Chart -->
<div class="card">
    <h2>Capability Coverage (WA Foundations)</h2>
    <div class="chart-container" id="radarChart">
        {{ radar_svg | safe }}
    </div>
</div>

<!-- Check Results Table -->
<div class="card">
    <h2>Check Results</h2>
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
<div class="card">
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

<script>
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
