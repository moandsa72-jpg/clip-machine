#!/usr/bin/env python3
"""Build a conservative platform-aware posting queue from eligible matches."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

MIN_QUEUE_SCORE = 60

def load(path):
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)

def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def main():
    if len(sys.argv) not in (3, 4):
        sys.exit("Usage: create_posting_queue.py <opportunities.json> <posting_package.json> [output.json]")
    opportunities = load(sys.argv[1])
    package = load(sys.argv[2])
    output = Path(sys.argv[3]) if len(sys.argv) == 4 else Path("output/posting_queue/posting_queue.json")
    clips = {item.get("filename"): item for item in package.get("clips", [])}
    queue, rejected = [], []
    seen = set()
    for opportunity in opportunities.get("opportunities", []):
        campaign = opportunity.get("campaign", {})
        score = int(opportunity.get("opportunity_score", 0) or 0)
        matches = opportunity.get("best_matches") or []
        if score < MIN_QUEUE_SCORE or not matches:
            rejected.append({"campaign": campaign.get("name"), "reason": "no eligible match above queue threshold"})
            continue
        match = matches[0]
        if match.get("eligible") is False:
            rejected.append({"campaign": campaign.get("name"), "reason": "matcher marked pair ineligible"})
            continue
        clip = clips.get(match.get("clip"))
        if not clip:
            rejected.append({"campaign": campaign.get("name"), "reason": "matched clip missing from posting package"})
            continue
        if clip.get("intelligence", {}).get("decision") == "hold":
            rejected.append({"campaign": campaign.get("name"), "reason": "clip is on hold"})
            continue
        campaign_url = str(campaign.get("url", "")).strip()
        parsed = urlparse(campaign_url)
        if parsed.scheme != "https" or not parsed.netloc:
            rejected.append({"campaign": campaign.get("name"), "reason": "campaign has no valid HTTPS URL"})
            continue
        for platform_key, post in clip.get("platform_posts", {}).items():
            queue_id = f"{campaign.get('id','campaign')}::{clip.get('filename','clip')}::{platform_key}"
            if queue_id in seen:
                continue
            seen.add(queue_id)
            queue.append({
                "queue_id": queue_id, "campaign_id": campaign.get("id"),
                "campaign_name": campaign.get("name"), "campaign_url": campaign_url,
                "campaign_score": score, "match_similarity": match.get("similarity"),
                "match_reasons": match.get("reasons", []),
                "clip_filename": clip.get("filename"), "video_path": clip.get("video_path"),
                "clip_score": clip.get("intelligence", {}).get("score", 0),
                "platform": platform_key, "copy": post, "status": "needs_review",
                "published_url": None, "published_at": None,
                "performance": {"views": None, "likes": None, "comments": None, "shares": None},
            })
    queue.sort(key=lambda x: (-x["campaign_score"], -x["clip_score"], x["platform"]))
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "draft_requires_human_review", "minimum_match_score": MIN_QUEUE_SCORE,
        "queue_count": len(queue), "rejected_opportunity_count": len(rejected),
        "rejected_opportunities": rejected[:100], "queue": queue,
        "instructions": [
            "Every queue entry requires human review; none is automatically approved.",
            "Confirm campaign identity, individual campaign URL, payout, deadlines and prohibited content before publishing.",
            "Record the public post URL and timestamp after publishing.",
            "Update performance from public/native platform analytics before learning from results.",
        ],
    }
    save(output, report)
    print(f"Posting queue: {len(queue)} review-only platform posts; rejected opportunities: {len(rejected)}")
    for item in queue[:20]:
        print(f"- {item['status']} | {item['platform']} | {item['campaign_name']} | {item['clip_filename']}")
if __name__ == "__main__":
    main()
