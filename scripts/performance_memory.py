import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_HISTORY = Path("work/state/performance_history.json")
GROUP_FIELDS = ("hook_style", "content_type", "framing_mode", "platform")


def load_history(path):
    path = Path(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Performance history must be a JSON list: {path}")
    return [item for item in data if isinstance(item, dict)]


def _number(value, name, required=False):
    if value is None and not required:
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be a finite, non-negative number")
    return number


def build_record(metadata, metrics, platform, posted_at=None):
    if not isinstance(metadata, dict):
        raise ValueError("Clip metadata must be a JSON object")
    if not str(metadata.get("filename", "")).strip():
        raise ValueError("Clip metadata is missing filename")
    record = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "posted_at": posted_at,
        "filename": str(metadata["filename"]),
        "campaign_id": str(metadata.get("campaign_id") or "unknown"),
        "hook_text": str(metadata.get("hook_text", "")),
        "hook_style": str(metadata.get("hook_style", "unknown")),
        "content_type": str(metadata.get("content_type", "unknown")),
        "framing_mode": str(metadata.get("framing_mode", "unknown")),
        "platform": str(platform).strip().lower(),
    }
    for key in ("views", "likes", "comments", "shares", "saves"):
        record[key] = int(_number(metrics.get(key), key))
    record["avg_watch_seconds"] = round(_number(metrics.get("avg_watch_seconds"), "avg_watch_seconds"), 3)
    record["engagement_rate"] = round(
        (record["likes"] + record["comments"] + record["shares"] + record["saves"])
        / record["views"], 6
    ) if record["views"] else 0.0
    return record


def save_record(metadata_path, metrics, platform, history_path=DEFAULT_HISTORY, posted_at=None):
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    history_path = Path(history_path)
    history = load_history(history_path)
    record = build_record(metadata, metrics, platform, posted_at)
    history.append(record)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = history_path.with_suffix(history_path.suffix + ".tmp")
    temporary.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(history_path)
    return record


def summarize(history):
    groups = defaultdict(list)
    for record in history:
        for field in GROUP_FIELDS:
            value = str(record.get(field) or "unknown")
            groups[(field, value)].append(record)
    summaries = []
    for (field, value), records in groups.items():
        count = len(records)
        summaries.append({
            "by": field,
            "value": value,
            "posts": count,
            "average_views": round(sum(float(r.get("views", 0)) for r in records) / count, 1),
            "average_engagement_rate": round(sum(float(r.get("engagement_rate", 0)) for r in records) / count, 4),
            "average_watch_seconds": round(sum(float(r.get("avg_watch_seconds", 0)) for r in records) / count, 2),
        })
    return sorted(summaries, key=lambda row: (row["by"], -row["average_views"]))



def learned_adjustment(metadata, history, minimum_samples=3, platform=None):
    """Return a small, confidence-gated ranking adjustment from prior results."""
    if not history:
        return {"adjustment": 0.0, "samples": 0, "reason": "no performance history"}

    keys = ("hook_style", "content_type", "framing_mode")
    target = {key: str(metadata.get(key) or "unknown") for key in keys}
    campaign_id = str(metadata.get("campaign_id") or "unknown")
    platform_filter = str(platform).lower() if platform else None

    eligible = []
    for record in history:
        if platform_filter and str(record.get("platform", "")).lower() != platform_filter:
            continue
        record_campaign = str(record.get("campaign_id") or "unknown")
        if campaign_id != "unknown" and record_campaign not in (campaign_id, "unknown"):
            continue
        eligible.append(record)

    matching = [
        record for record in eligible
        if all(str(record.get(key) or "unknown") == value for key, value in target.items())
    ]
    if len(matching) < minimum_samples or len(eligible) < minimum_samples:
        return {
            "adjustment": 0.0,
            "samples": len(matching),
            "reason": f"needs at least {minimum_samples} comparable posts",
        }

    def outcome(record):
        # Engagement rate and watch time are kept separate from raw views,
        # which vary heavily with account size and distribution.
        engagement = max(0.0, float(record.get("engagement_rate", 0) or 0))
        watch = max(0.0, float(record.get("avg_watch_seconds", 0) or 0))
        return engagement * 100.0 + watch

    baseline = sum(outcome(record) for record in eligible) / len(eligible)
    observed = sum(outcome(record) for record in matching) / len(matching)
    if baseline <= 0:
        adjustment = 0.0
    else:
        relative_lift = (observed - baseline) / baseline
        # Shrink small samples toward zero and cap the influence so history
        # can refine, but never overpower, footage/campaign quality.
        confidence = len(matching) / (len(matching) + 5.0)
        adjustment = max(-4.0, min(4.0, relative_lift * 4.0 * confidence))

    return {
        "adjustment": round(adjustment, 2),
        "samples": len(matching),
        "baseline_samples": len(eligible),
        "reason": "historical engagement and watch-time signal",
    }


def main():
    parser = argparse.ArgumentParser(description="Free, local performance memory for Clip Machine.")
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    sub = parser.add_subparsers(dest="command", required=True)
    record_parser = sub.add_parser("record", help="Save manually entered platform results for a clip.")
    record_parser.add_argument("metadata", type=Path, help="Clip JSON sidecar")
    record_parser.add_argument("--platform", required=True)
    record_parser.add_argument("--views", required=True, type=int)
    record_parser.add_argument("--likes", type=int, default=0)
    record_parser.add_argument("--comments", type=int, default=0)
    record_parser.add_argument("--shares", type=int, default=0)
    record_parser.add_argument("--saves", type=int, default=0)
    record_parser.add_argument("--avg-watch-seconds", type=float, default=0)
    record_parser.add_argument("--posted-at")
    sub.add_parser("report", help="Compare results by hook, content type, framing, and platform.")
    args = parser.parse_args()

    if args.command == "record":
        metrics = {key: getattr(args, key) for key in ("views", "likes", "comments", "shares", "saves", "avg_watch_seconds")}
        record = save_record(args.metadata, metrics, args.platform, args.history, args.posted_at)
        print(f"Saved performance for {record['filename']} ({record['platform']}).")
        print(f"Engagement rate: {record['engagement_rate']:.2%}")
        return

    history = load_history(args.history)
    if not history:
        print(f"No performance records yet. History file: {args.history}")
        return
    print(f"Performance records: {len(history)}")
    for row in summarize(history):
        print(
            f"{row['by']}={row['value']} | posts={row['posts']} | "
            f"avg views={row['average_views']:.1f} | "
            f"avg engagement={row['average_engagement_rate']:.2%} | "
            f"avg watch={row['average_watch_seconds']:.2f}s"
        )


if __name__ == "__main__":
    main()
