#!/usr/bin/env python3
"""Rank public campaign opportunities against an existing posting package."""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def load(path):
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def tokens(text):
    return {x for x in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(x) >= 3}


def clip_text(clip):
    return " ".join([
        str(clip.get("hook", {}).get("text", "")),
        str(clip.get("caption", "")),
        str(clip.get("title", "")),
    ])


def campaign_text(item):
    return " ".join([
        str(item.get("name", "")),
        str(item.get("source_platform", "")),
        str(item.get("content_type", "")),
    ])


def match_score(clip, campaign):
    ct = tokens(campaign_text(campaign))
    xt = tokens(clip_text(clip))
    overlap = len(ct & xt)
    score = min(35, overlap * 7)
    reasons = []
    if overlap:
        reasons.append(f"{overlap} topical keyword matches")
    intelligence = clip.get("intelligence", {})
    base = int(intelligence.get("score", 0) or 0)
    score += round(base * 0.45)
    if intelligence.get("decision") == "ready":
        reasons.append("clip already marked ready")
    elif intelligence.get("decision") == "review":
        reasons.append("clip needs review before posting")
    else:
        reasons.append("clip is on hold")
    rate = campaign.get("rate")
    if isinstance(rate, (int, float)):
        if rate >= 5:
            score += 20
            reasons.append(f"high payout ${rate:g}/1K")
        elif rate >= 2:
            score += 10
            reasons.append(f"payout ${rate:g}/1K")
    if campaign.get("budget_left") and campaign["budget_left"] > 0:
        score += 5
        reasons.append("budget remains")
    return min(100, int(score)), reasons


def main():
    if len(sys.argv) not in (3, 4):
        sys.exit("Usage: python scripts/create_campaign_opportunities.py <campaign-radar/latest.json> <posting_package.json> [output.json]")

    radar = load(sys.argv[1])
    package = load(sys.argv[2])
    output = Path(sys.argv[3]) if len(sys.argv) == 4 else Path("output/campaign_opportunities/opportunities.json")

    campaigns = radar.get("campaigns", []) if isinstance(radar, dict) else []
    clips = package.get("clips", []) if isinstance(package, dict) else []
    opportunities = []

    for campaign in campaigns:
        best = []
        for clip in clips:
            score, reasons = match_score(clip, campaign)
            best.append({
                "clip": clip.get("filename"),
                "score": score,
                "decision": clip.get("intelligence", {}).get("decision", "unknown"),
                "reasons": reasons,
            })
        best.sort(key=lambda x: x["score"], reverse=True)
        if best:
            opportunities.append({
                "campaign": campaign,
                "best_matches": best[:5],
                "opportunity_score": best[0]["score"],
                "recommended_action": "post_ready_clip" if best[0]["decision"] == "ready" and best[0]["score"] >= 80 else "review_match",
            })

    opportunities.sort(key=lambda x: x["opportunity_score"], reverse=True)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_campaigns": len(campaigns),
        "source_clips": len(clips),
        "opportunities": opportunities,
        "next_actions": [
            "Use the highest-scoring campaign/clip pair first.",
            "Never auto-submit a HOLD clip.",
            "Verify the campaign brief and public campaign page before submission.",
            "Record the public post URL after publishing.",
        ],
    }
    save(output, report)
    print(f"Campaign opportunities: {len(opportunities)}")
    for item in opportunities[:10]:
        c = item["campaign"]
        print(f"- [{item['opportunity_score']}] {c.get('name')} -> {item['best_matches'][0]['clip']}")


if __name__ == "__main__":
    main()
