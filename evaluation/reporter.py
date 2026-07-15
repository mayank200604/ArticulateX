# -*- coding: utf-8 -*-
"""
reporter.py — Multi-format evaluation report generator.

Generates JSON, CSV, and rich HTML reports from evaluation results.
"""

import os
import json
import csv
from datetime import datetime
from typing import Optional

from evaluation.config import REPORT_DIR


def ensure_report_dir():
    """Create report output directory if it doesn't exist."""
    os.makedirs(REPORT_DIR, exist_ok=True)


def generate_reports(
    all_results: list,
    api_data: dict = None,
    cache_stats: dict = None,
    quota_estimate: dict = None,
    mode_name: str = "full",
) -> dict:
    """
    Generate all report formats from evaluation results.

    Returns dict with paths to generated report files.
    """
    ensure_report_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"eval_{mode_name}_{timestamp}"

    paths = {}
    paths["json"] = _generate_json_report(
        all_results, api_data, cache_stats, quota_estimate, prefix,
    )
    paths["csv"] = _generate_csv_report(all_results, prefix)
    paths["html"] = _generate_html_report(
        all_results, api_data, cache_stats, quota_estimate, prefix,
    )

    return paths


# ════════════════════════════════════════════════════════════════
# JSON REPORT
# ════════════════════════════════════════════════════════════════

def _generate_json_report(
    all_results: list,
    api_data: dict,
    cache_stats: dict,
    quota_estimate: dict,
    prefix: str,
) -> str:
    """Generate comprehensive JSON report."""
    # Compute summary stats
    total_rules = 0
    total_pass = 0
    total_partial = 0
    total_fail = 0
    total_skip = 0
    total_error = 0
    total_unknown = 0

    for sc in all_results:
        for ev in sc.get("rule_evaluations", []):
            total_rules += 1
            r = ev.get("result", "")
            if r == "PASS":
                total_pass += 1
            elif r == "PARTIAL":
                total_partial += 1
            elif r == "FAIL":
                total_fail += 1
            elif r == "SKIP":
                total_skip += 1
            elif r == "ERROR":
                total_error += 1
            else:
                total_unknown += 1

    evaluated = total_rules - total_skip
    pass_rate = round(total_pass / evaluated * 100, 1) if evaluated > 0 else 0

    # Compute confidence scores per scenario
    for sc in all_results:
        confidences = [
            ev.get("confidence", 0.0)
            for ev in sc.get("rule_evaluations", [])
            if ev.get("result") not in ("SKIP", "ERROR", "UNKNOWN")
        ]
        sc["avg_confidence"] = (
            round(sum(confidences) / len(confidences), 3)
            if confidences else 0.0
        )

    report = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "framework_version": "2.0",
            "mode": prefix.split("_")[1] if "_" in prefix else "unknown",
        },
        "summary": {
            "total_rules_evaluated": total_rules,
            "evaluated_rules": evaluated,
            "pass": total_pass,
            "partial": total_partial,
            "fail": total_fail,
            "skip": total_skip,
            "error": total_error,
            "unknown": total_unknown,
            "pass_rate_percent": pass_rate,
        },
        "scenarios": all_results,
        "api_usage": api_data or {},
        "cache_stats": cache_stats or {},
        "quota_estimate": quota_estimate or {},
    }

    path = os.path.join(REPORT_DIR, f"{prefix}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return path


# ════════════════════════════════════════════════════════════════
# CSV REPORT
# ════════════════════════════════════════════════════════════════

def _generate_csv_report(all_results: list, prefix: str) -> str:
    """Generate CSV report with one row per rule evaluation."""
    path = os.path.join(REPORT_DIR, f"{prefix}.csv")

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "scenario", "mode", "level", "category", "eval_type",
            "rule", "result", "confidence", "reason",
        ])

        for sc in all_results:
            for ev in sc.get("rule_evaluations", []):
                writer.writerow([
                    sc.get("scenario", ""),
                    sc.get("mode", ""),
                    sc.get("level", ""),
                    ev.get("category", ""),
                    ev.get("eval_type", ""),
                    ev.get("rule", ""),
                    ev.get("result", ""),
                    ev.get("confidence", ""),
                    ev.get("reason", ""),
                ])

    return path


# ════════════════════════════════════════════════════════════════
# HTML REPORT
# ════════════════════════════════════════════════════════════════

def _generate_html_report(
    all_results: list,
    api_data: dict,
    cache_stats: dict,
    quota_estimate: dict,
    prefix: str,
) -> str:
    """Generate rich interactive HTML report."""

    # Compute stats
    total_rules = 0
    total_pass = 0
    total_partial = 0
    total_fail = 0
    total_skip = 0
    total_error = 0
    scenario_stats = []

    for sc in all_results:
        s_pass = s_fail = s_partial = s_skip = 0
        for ev in sc.get("rule_evaluations", []):
            total_rules += 1
            r = ev.get("result", "")
            if r == "PASS":
                total_pass += 1
                s_pass += 1
            elif r == "PARTIAL":
                total_partial += 1
                s_partial += 1
            elif r == "FAIL":
                total_fail += 1
                s_fail += 1
            elif r == "SKIP":
                total_skip += 1
                s_skip += 1
            else:
                total_error += 1

        s_total = s_pass + s_fail + s_partial
        s_rate = round(s_pass / s_total * 100) if s_total > 0 else 0
        scenario_stats.append({
            "name": sc.get("scenario", ""),
            "pass": s_pass,
            "fail": s_fail,
            "partial": s_partial,
            "skip": s_skip,
            "total": s_pass + s_fail + s_partial + s_skip,
            "rate": s_rate,
        })

    evaluated = total_rules - total_skip
    pass_rate = round(total_pass / evaluated * 100, 1) if evaluated > 0 else 0

    # API stats
    api_summary = api_data.get("summary", {}) if api_data else {}
    api_total = api_summary.get("total_requests", 0)
    api_tokens = api_summary.get("total_tokens", 0)
    api_cost = api_summary.get("cost_estimate_usd", 0)

    # Cache stats
    c_hits = cache_stats.get("hits", 0) if cache_stats else 0
    c_misses = cache_stats.get("misses", 0) if cache_stats else 0
    c_rate = cache_stats.get("hit_rate", 0) if cache_stats else 0

    # Build failed rules table rows
    failed_rows = ""
    for sc in all_results:
        for ev in sc.get("rule_evaluations", []):
            if ev.get("result") in ("FAIL", "PARTIAL"):
                color = "#ff4444" if ev["result"] == "FAIL" else "#ff9800"
                failed_rows += f"""
                <tr>
                    <td>{sc.get('scenario', '')}</td>
                    <td>{ev.get('category', '')}</td>
                    <td>{ev.get('eval_type', '')}</td>
                    <td>{ev.get('rule', '')[:80]}</td>
                    <td style="color: {color}; font-weight: bold">{ev.get('result', '')}</td>
                    <td style="font-size: 0.85em">{ev.get('reason', '')}</td>
                </tr>"""

    # Build per-scenario cards
    scenario_cards = ""
    for ss in scenario_stats:
        bar_color = "#4caf50" if ss["rate"] >= 80 else "#ff9800" if ss["rate"] >= 60 else "#ff4444"
        scenario_cards += f"""
        <div class="card">
            <h3>{ss['name']}</h3>
            <div class="progress-bar">
                <div class="progress-fill" style="width: {ss['rate']}%; background: {bar_color}"></div>
            </div>
            <div class="stats-row">
                <span class="stat pass">✓ {ss['pass']}</span>
                <span class="stat partial">~ {ss['partial']}</span>
                <span class="stat fail">✗ {ss['fail']}</span>
                <span class="stat skip">⊘ {ss['skip']}</span>
                <span class="stat rate">{ss['rate']}%</span>
            </div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ArticulateX Evaluation Report</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
        background: #0a0a0f;
        color: #e0e0e0;
        padding: 2rem;
        line-height: 1.6;
    }}
    .header {{
        text-align: center;
        padding: 2rem 0;
        border-bottom: 1px solid #222;
        margin-bottom: 2rem;
    }}
    .header h1 {{
        font-size: 1.8rem;
        background: linear-gradient(135deg, #667eea, #764ba2);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }}
    .header .timestamp {{
        color: #666;
        font-size: 0.85rem;
        margin-top: 0.5rem;
    }}
    .summary-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 1rem;
        margin-bottom: 2rem;
    }}
    .metric {{
        background: #111118;
        border: 1px solid #222;
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
    }}
    .metric .value {{
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.3rem;
    }}
    .metric .label {{
        color: #888;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}
    .metric.pass .value {{ color: #4caf50; }}
    .metric.fail .value {{ color: #ff4444; }}
    .metric.rate .value {{ color: #667eea; }}
    .metric.tokens .value {{ color: #ff9800; font-size: 1.5rem; }}
    .metric.cost .value {{ color: #00bcd4; }}
    .metric.cache .value {{ color: #9c27b0; }}
    .section {{ margin-bottom: 2rem; }}
    .section h2 {{
        font-size: 1.2rem;
        color: #aaa;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #1a1a2e;
    }}
    .cards-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 1rem;
    }}
    .card {{
        background: #111118;
        border: 1px solid #222;
        border-radius: 12px;
        padding: 1.2rem;
    }}
    .card h3 {{
        font-size: 1rem;
        margin-bottom: 0.8rem;
        color: #ccc;
    }}
    .progress-bar {{
        height: 8px;
        background: #1a1a2e;
        border-radius: 4px;
        overflow: hidden;
        margin-bottom: 0.8rem;
    }}
    .progress-fill {{
        height: 100%;
        border-radius: 4px;
        transition: width 0.5s ease;
    }}
    .stats-row {{
        display: flex;
        gap: 0.8rem;
        flex-wrap: wrap;
    }}
    .stat {{
        font-size: 0.85rem;
        font-weight: 600;
    }}
    .stat.pass {{ color: #4caf50; }}
    .stat.partial {{ color: #ff9800; }}
    .stat.fail {{ color: #ff4444; }}
    .stat.skip {{ color: #666; }}
    .stat.rate {{ color: #667eea; margin-left: auto; }}
    table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.85rem;
    }}
    th, td {{
        padding: 0.7rem;
        text-align: left;
        border-bottom: 1px solid #1a1a2e;
    }}
    th {{
        background: #111118;
        color: #888;
        text-transform: uppercase;
        font-size: 0.75rem;
        letter-spacing: 0.05em;
        position: sticky;
        top: 0;
    }}
    tr:hover td {{
        background: #111118;
    }}
</style>
</head>
<body>

<div class="header">
    <h1>ArticulateX Evaluation Report</h1>
    <div class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
</div>

<div class="summary-grid">
    <div class="metric rate">
        <div class="value">{pass_rate}%</div>
        <div class="label">Pass Rate</div>
    </div>
    <div class="metric pass">
        <div class="value">{total_pass}</div>
        <div class="label">Passed</div>
    </div>
    <div class="metric fail">
        <div class="value">{total_fail}</div>
        <div class="label">Failed</div>
    </div>
    <div class="metric">
        <div class="value">{total_partial}</div>
        <div class="label">Partial</div>
    </div>
    <div class="metric">
        <div class="value">{total_skip}</div>
        <div class="label">Skipped</div>
    </div>
    <div class="metric tokens">
        <div class="value">{api_tokens:,}</div>
        <div class="label">Total Tokens</div>
    </div>
    <div class="metric">
        <div class="value">{api_total}</div>
        <div class="label">API Calls</div>
    </div>
    <div class="metric cost">
        <div class="value">${api_cost:.4f}</div>
        <div class="label">Est. Cost</div>
    </div>
    <div class="metric cache">
        <div class="value">{round(c_rate * 100)}%</div>
        <div class="label">Cache Hit Rate</div>
    </div>
</div>

<div class="section">
    <h2>Per-Scenario Results</h2>
    <div class="cards-grid">
        {scenario_cards}
    </div>
</div>

<div class="section">
    <h2>Failed &amp; Partial Rules</h2>
    <div style="overflow-x: auto;">
    <table>
        <thead>
            <tr>
                <th>Scenario</th>
                <th>Category</th>
                <th>Eval Type</th>
                <th>Rule</th>
                <th>Result</th>
                <th>Reason</th>
            </tr>
        </thead>
        <tbody>
            {failed_rows if failed_rows else '<tr><td colspan="6" style="text-align:center;color:#4caf50">All rules passed!</td></tr>'}
        </tbody>
    </table>
    </div>
</div>

</body>
</html>"""

    path = os.path.join(REPORT_DIR, f"{prefix}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    return path
