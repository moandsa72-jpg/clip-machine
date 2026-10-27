#!/usr/bin/env python3
"""Record published post performance into the local learning dataset."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def load(path):
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalize_platform(value):
    return str(value or "").strip().lower().replace(" ", "_")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--clip", required=True)
    parser.add_argument("--post-url", required=True)
    parser.add_argument("--views", type=int, default=0)
    parser.add_argument("--likes", type=int, default=0)
    parser.add_argument("--comments", type=int, default=0)
    parser.add_argument("--shares", type=int, default=0)
    parser.add_argument("--hook-score", type=float, default=None)
    parser.add_argument("--topic", default="")
    parser.add_argument("--duration-seconds", type=float, default=None)
    args = parser.parse_args()

    path = Path("performance/feedback.json")
    data = load(path) if path.exists() else {"version": 2, "entries": []}
    entries = data.setdefault("entries", [])
    views = max(0, args.views)
    engagement_per_1k = None
    if views > 0:
        engagement_per_1k = round((max(0, args.likes) + 2 * max(0, args.comments) + 3 * max(0, args.shares)) / views * 1000, 4)
    entries.append({
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "campaign_id": args.campaign_id,
        "platform": normalize_platform(args.platform),
        "clip": args.clip,
        "post_url": args.post_url,
        "views": views,
        "likes": max(0, args.likes),
        "comments": max(0, args.comments),
        "shares": max(0, args.shares),
        "engagement_per_1k": engagement_per_1k,
        "hook_score": args.hook_score,
        "topic": args.topic,
        "duration_seconds": args.duration_seconds,
    })
    data["version"] = max(2, int(data.get("version", 1) or 1))
    save(path, data)
    print(f"Recorded performance for {args.campaign_id} / {args.platform} / {args.clip}")


if __name__ == "__main__":
    main()
