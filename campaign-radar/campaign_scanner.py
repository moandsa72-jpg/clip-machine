#!/usr/bin/env python3
"""Read-only campaign radar. No changes are made to the production pipeline."""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "campaign-radar" / "config.json"


def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def get_json(url, api_key):
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def score_campaign(campaign, rules):
    score = 0
    reasons = []

    rate = campaign.get("rate")
    if isinstance(rate, (int, float)):
        if rate >= 10:
            score += 35
            reasons.append(f"strong rate ${rate:g}/1K")
        elif rate >= rules["minimum_rate_usd_per_1k"]:
            score += 20
            reasons.append(f"rate ${rate:g}/1K")
        else:
            reasons.append(f"low rate ${rate:g}/1K")

    score_value = campaign.get("score")
    if isinstance(score_value, (int, float)):
        score += round(max(0, min(100, score_value)) * 0.25)
        if score_value >= 70:
            reasons.append("high opportunity score")

    viral = campaign.get("viral_score")
    if isinstance(viral, (int, float)):
        score += round(max(0, min(100, viral)) * 0.15)
        if viral >= 70:
            reasons.append("high viral score")

    text = " ".join(str(campaign.get(k, "")) for k in ("name", "summary", "description")).lower()
    preferred_terms = set(rules["preferred_categories"] + rules["preferred_tags"])
    matches = sorted(term for term in preferred_terms if term.lower() in text)
    if matches:
        score += min(20, len(matches) * 5)
        reasons.append("content matches clipping/podcast focus")

    targets = [str(x).lower() for x in as_list(campaign.get("target_platforms"))]
    target_matches = [x for x in targets if x in rules["preferred_targets"]]
    if target_matches:
        score += min(10, len(set(target_matches)) * 4)
        reasons.append("accepted platform matches our pipeline")

    budget = campaign.get("budget_left")
    if isinstance(budget, (int, float)) and budget > 0:
        score += 5
        reasons.append("budget remains")

    return min(100, int(score)), reasons


def normalize(campaign, rules):
    score, reasons = score_campaign(campaign, rules)
    return {
        "id": campaign.get("id"),
        "name": campaign.get("name"),
        "url": campaign.get("url") or campaign.get("campaign_url"),
        "source_platform": campaign.get("platform"),
        "target_platforms": as_list(campaign.get("target_platforms")),
        "content_type": campaign.get("content_type"),
        "rate": campaign.get("rate"),
        "budget": campaign.get("budget"),
        "budget_left": campaign.get("budget_left"),
        "deadline": campaign.get("ends_at") or campaign.get("deadline"),
        "opportunity_score": score,
        "reasons": reasons,
    }


def main():
    config = load_config()
    api_key = os.environ.get("CLIPRADAR_API_KEY", "").strip()
    if not api_key:
        print("Campaign radar is installed but not connected: CLIPRADAR_API_KEY is not set.")
        print("No campaign source was contacted and no production workflow was changed.")
        return 0

    source = config["source"]
    rules = config["scoring"]
    params = {
        "status": source["status"],
        "target_platform": ",".join(source["target_platforms"]),
        "content_type": source["content_type"],
        "sort": "newest",
        "limit": str(source["limit"]),
    }
    url = f"{source['clipradar_base_url'].rstrip('/')}/campaigns?{urllib.parse.urlencode(params)}"

    try:
        payload = get_json(url, api_key)
    except Exception as exc:
        print(f"Campaign radar error: {exc}", file=sys.stderr)
        return 1

    campaigns = payload.get("data", payload if isinstance(payload, list) else [])
    ranked = [normalize(c, rules) for c in campaigns]
    ranked.sort(key=lambda x: x["opportunity_score"], reverse=True)
    selected = [x for x in ranked if x["opportunity_score"] >= rules["minimum_score_to_report"]]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "ClipRadar",
        "scanned": len(ranked),
        "selected": len(selected),
        "campaigns": selected,
    }
    output = ROOT / "campaign-radar" / "latest.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Campaign radar scanned {len(ranked)} live campaigns.")
    print(f"{len(selected)} campaigns passed the current score threshold.")
    for item in selected[:20]:
        print(f"- [{item['opportunity_score']}] {item['name']} | {item['rate']} | {item['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
