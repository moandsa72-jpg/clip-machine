#!/usr/bin/env python3
"""Apply free, local performance feedback to a posting package."""
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def load(path, default):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def tokens(text):
    return {x for x in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(x) >= 4}


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: apply_performance_learning.py <posting_package.json> <feedback.json>")
    package_path = Path(sys.argv[1])
    feedback_path = Path(sys.argv[2])
    package = load(package_path, {})
    data = load(feedback_path, {"entries": []})
    entries = [e for e in data.get("entries", []) if isinstance(e, dict)]
    by_campaign = defaultdict(list)
    by_platform = defaultdict(list)
    by_hook = defaultdict(list)
    for entry in entries:
        views = max(0, int(entry.get("views") or 0))
        if views <= 0:
            continue
        likes = max(0, int(entry.get("likes") or 0))
        comments = max(0, int(entry.get("comments") or 0))
        shares = max(0, int(entry.get("shares") or 0))
        engagement = (likes + 2 * comments + 3 * shares) / views * 1000
        by_campaign[(entry.get("campaign_id"), entry.get("platform"))].append(engagement)
        by_platform[entry.get("platform")].append(engagement)
        hook_score = entry.get("hook_score")
        if isinstance(hook_score, (int, float)):
            bucket = "strong" if hook_score >= 8 else "solid" if hook_score >= 6 else "weak"
            by_hook[bucket].append(engagement)

    global_values = [v for values in by_platform.values() for v in values]
    baseline = sum(global_values) / len(global_values) if global_values else None

    for clip in package.get("clips", []):
        intelligence = clip.setdefault("intelligence", {})
        adjustment = 0.0
        signals = []
        campaign_id = package.get("campaign_id")
        for platform in (clip.get("platform_posts") or {}).keys():
            values = by_campaign.get((campaign_id, platform)) or by_platform.get(platform, [])
            if values and baseline is not None:
                average = sum(values) / len(values)
                delta = max(-8, min(8, (average / baseline - 1) * 8))
                adjustment = max(adjustment, delta)
                signals.append(f"{platform} historical engagement {average:.2f}/1K")

        hook_score = (clip.get("hook") or {}).get("score")
        bucket = "strong" if isinstance(hook_score, (int, float)) and hook_score >= 8 else "solid" if isinstance(hook_score, (int, float)) and hook_score >= 6 else "weak"
        values = by_hook.get(bucket, [])
        if values and baseline is not None:
            average = sum(values) / len(values)
            delta = max(-5, min(5, (average / baseline - 1) * 5))
            adjustment = max(adjustment, delta)
            signals.append(f"{bucket} hook history {average:.2f}/1K")

        if signals:
            old_score = int(intelligence.get("score", 0) or 0)
            new_score = max(0, min(100, round(old_score + adjustment)))
            intelligence["score"] = new_score
            intelligence["performance_learning"] = {
                "adjustment": round(adjustment, 2),
                "signals": signals,
                "sample_count": len(entries),
            }
            if new_score >= 80 and intelligence.get("decision") != "hold" and not any("not detected" in str(w).lower() for w in intelligence.get("warnings", [])):
                intelligence["decision"] = "ready"
            elif new_score >= 60 and intelligence.get("decision") == "hold":
                intelligence["decision"] = "review"

    package["performance_learning"] = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "entries_used": len(entries),
        "baseline_engagement_per_1k": round(baseline, 3) if baseline is not None else None,
        "method": "free_local_historical_engagement",
        "max_adjustment_points": 8,
    }
    package_path.write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Performance learning applied: {len(entries)} feedback entries")


if __name__ == "__main__":
    main()
