#!/usr/bin/env python3
"""Turn campaign opportunities into a platform-aware posting queue."""

import json
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


def main():
    if len(sys.argv) not in (3, 4):
        sys.exit("Usage: python scripts/create_posting_queue.py <opportunities.json> <posting_package.json> [output.json]")

    opportunities = load(sys.argv[1])
    package = load(sys.argv[2])
    output = Path(sys.argv[3]) if len(sys.argv) == 4 else Path("output/posting_queue/posting_queue.json")
    clips = {item.get("filename"): item for item in package.get("clips", [])}

    queue = []
    for opportunity in opportunities.get("opportunities", []):
        campaign = opportunity.get("campaign", {})
        match = (opportunity.get("best_matches") or [{}])[0]
        clip = clips.get(match.get("clip"))
        if not clip:
            continue
        if clip.get("intelligence", {}).get("decision") == "hold":
            continue

        for platform_key, post in clip.get("platform_posts", {}).items():
            queue.append({
                "queue_id": f"{campaign.get('id','campaign')}::{clip.get('filename','clip')}::{platform_key}",
                "campaign_id": campaign.get("id"),
                "campaign_name": campaign.get("name"),
                "campaign_url": campaign.get("url"),
                "campaign_score": opportunity.get("opportunity_score", 0),
                "clip_filename": clip.get("filename"),
                "video_path": clip.get("video_path"),
                "clip_score": clip.get("intelligence", {}).get("score", 0),
                "platform": platform_key,
                "copy": post,
                "status": "ready_for_publish_review" if opportunity.get("opportunity_score", 0) >= 80 else "needs_review",
                "published_url": None,
                "published_at": None,
                "performance": {"views": None, "likes": None, "comments": None, "shares": None},
            })

    queue.sort(key=lambda x: (x["status"] != "ready_for_publish_review", -x["campaign_score"], -x["clip_score"]))
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "draft",
        "queue_count": len(queue),
        "queue": queue,
        "instructions": [
            "Publish READY items first.",
            "Confirm campaign terms immediately before publishing.",
            "Record the public post URL and timestamp in this queue after publishing.",
            "Update performance fields from public/native platform analytics before learning from results.",
        ],
    }
    save(output, report)
    print(f"Posting queue: {len(queue)} platform posts")
    for item in queue[:20]:
        print(f"- {item['status']} | {item['platform']} | {item['campaign_name']} | {item['clip_filename']}")


if __name__ == "__main__":
    main()
