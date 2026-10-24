import html
import json
import sys
from pathlib import Path


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def escape(value):
    return html.escape(str(value or ""))


def platform_names(platform_posts):
    return ", ".join(name.replace("_", " ").title() for name in platform_posts) or "None"


def decision_class(decision):
    return {
        "ready": "ready",
        "review": "review",
        "hold": "hold",
    }.get(decision, "unknown")


def build_markdown(package):
    scan = package.get("posting_scan", {})
    lines = [
        f"# Posting Dashboard — {package.get('campaign_name', package.get('campaign_id', 'Campaign'))}",
        "",
        f"Generated: `{package.get('created_at', '')}`",
        "",
        "## Summary",
        "",
        f"- **Clips scanned:** {package.get('clip_count', 0)}",
        f"- **READY:** {scan.get('ready_count', 0)}",
        f"- **REVIEW:** {scan.get('review_count', 0)}",
        f"- **HOLD:** {scan.get('hold_count', 0)}",
        f"- **Compliance warnings:** {package.get('compliance_warning_count', 0)}",
        "",
        "## Clips",
        "",
        "| Rank | Decision | Score | Clip | Hook | Platforms | Warnings |",
        "|---:|---|---:|---|---|---|---:|",
    ]

    for rank, clip in enumerate(package.get("clips", []), start=1):
        intelligence = clip.get("intelligence", {})
        decision = str(intelligence.get("decision", "unknown")).upper()
        hook = str(clip.get("hook", {}).get("text", "")).replace("|", "\\|").replace("\n", " ")
        warnings = len(clip.get("compliance_warnings", [])) + len(intelligence.get("warnings", []))
        lines.append(
            f"| {rank} | **{decision}** | {intelligence.get('score', 0)} | "
            f"`{clip.get('filename', '')}` | {hook or '—'} | "
            f"{platform_names(clip.get('platform_posts', {}))} | {warnings} |"
        )

    lines.extend(["", "## How to use", "", "1. Start with **READY** clips from the top of the list.", "2. Inspect **REVIEW** clips before posting.", "3. Do not post **HOLD** clips until the reason is resolved.", "4. Use each clip's platform-specific copy from `posting_package.json`.", ""])
    return "\n".join(lines)


def build_html(package):
    campaign = escape(package.get("campaign_name", package.get("campaign_id", "Campaign")))
    scan = package.get("posting_scan", {})
    cards = []

    for rank, clip in enumerate(package.get("clips", []), start=1):
        intelligence = clip.get("intelligence", {})
        decision = str(intelligence.get("decision", "unknown"))
        score = intelligence.get("score", 0)
        hook = escape(clip.get("hook", {}).get("text", "")) or "No hook text"
        strengths = "".join(f"<li>{escape(item)}</li>" for item in intelligence.get("strengths", []))
        warnings = intelligence.get("warnings", []) + clip.get("compliance_warnings", [])
        warning_html = "".join(f"<li>{escape(item)}</li>" for item in warnings) or "<li>None</li>"
        platforms = escape(platform_names(clip.get("platform_posts", {})))
        cards.append(
            f"""
            <article class=\"card {decision_class(decision)}\">
              <div class=\"top\"><span>#{rank}</span><strong>{decision.upper()}</strong><b>{score}/100</b></div>
              <h2>{escape(clip.get('filename', ''))}</h2>
              <p class=\"hook\">“{hook}”</p>
              <p><b>Platforms:</b> {platforms}</p>
              <details><summary>Why this score</summary><ul>{strengths or '<li>No strengths recorded.</li>'}</ul></details>
              <details><summary>Warnings ({len(warnings)})</summary><ul>{warning_html}</ul></details>
            </article>
            """
        )

    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Posting Dashboard — {campaign}</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#f5f5f5;color:#111}}main{{max-width:1000px;margin:auto;padding:20px}}h1{{margin-bottom:6px}}.muted{{color:#666}}.summary{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:20px 0}}.stat{{background:white;border-radius:12px;padding:14px;text-align:center;box-shadow:0 1px 4px #0001}}.stat b{{display:block;font-size:25px}}.cards{{display:grid;gap:14px}}.card{{background:white;border-left:7px solid #888;border-radius:12px;padding:16px;box-shadow:0 1px 4px #0001}}.card.ready{{border-color:#16803c}}.card.review{{border-color:#b7791f}}.card.hold{{border-color:#c53030}}.top{{display:flex;justify-content:space-between;gap:12px;align-items:center}}.ready strong{{color:#16803c}}.review strong{{color:#b7791f}}.hold strong{{color:#c53030}}.hook{{font-size:20px;font-weight:600}}summary{{cursor:pointer}}li{{margin:5px 0}}@media(max-width:650px){{.summary{{grid-template-columns:repeat(2,1fr)}}}}
</style>
</head>
<body><main>
<h1>Posting Dashboard</h1><div class=\"muted\">{campaign}</div>
<div class=\"summary\">
<div class=\"stat\"><b>{scan.get('ready_count',0)}</b>READY</div>
<div class=\"stat\"><b>{scan.get('review_count',0)}</b>REVIEW</div>
<div class=\"stat\"><b>{scan.get('hold_count',0)}</b>HOLD</div>
<div class=\"stat\"><b>{package.get('clip_count',0)}</b>CLIPS</div>
</div>
<p class=\"muted\">Sorted by posting intelligence score. Review campaign requirements before publishing.</p>
<section class=\"cards\">{''.join(cards)}</section>
</main></body></html>"""


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python scripts/create_posting_dashboard.py <posting_package.json> <output_directory>")

    package_path = Path(sys.argv[1])
    output_directory = Path(sys.argv[2])
    package = load_json(package_path)
    output_directory.mkdir(parents=True, exist_ok=True)

    save_paths = {
        "posting_dashboard.html": build_html(package),
        "posting_report.md": build_markdown(package),
    }
    for filename, content in save_paths.items():
        path = output_directory / filename
        path.write_text(content, encoding="utf-8")
        print(f"Created {path}")


if __name__ == "__main__":
    main()
