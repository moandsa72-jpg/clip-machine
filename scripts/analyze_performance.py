import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def load(path):
    with Path(path).open(encoding="utf-8") as file:
        data = json.load(file)
    return data.get("entries", []) if isinstance(data, dict) else []


def avg(rows, key):
    values = [float(row[key]) for row in rows if isinstance(row.get(key), (int, float))]
    return round(statistics.mean(values), 2) if values else None


def summarize(rows, key):
    groups = defaultdict(list)
    for row in rows:
        value = row.get(key)
        if value not in (None, ""):
            groups[str(value)].append(row)

    result = []
    for value, items in groups.items():
        result.append({
            "value": value,
            "samples": len(items),
            "avg_views": avg(items, "views"),
            "avg_likes": avg(items, "likes"),
            "avg_comments": avg(items, "comments"),
            "avg_shares": avg(items, "shares"),
        })
    return sorted(result, key=lambda item: item["avg_views"] or 0, reverse=True)


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("performance/feedback.json")
    rows = load(path)
    minimum_samples = 3

    report = {
        "samples": len(rows),
        "minimum_samples_for_learning": minimum_samples,
        "enough_data_to_learn": len(rows) >= minimum_samples,
        "campaigns": summarize(rows, "campaign_id"),
        "platforms": summarize(rows, "platform"),
        "hooks": summarize(rows, "hook_score"),
        "topics": summarize(rows, "topic"),
        "durations": summarize(rows, "duration_seconds"),
        "notes": [],
    }

    if len(rows) < minimum_samples:
        report["notes"].append("Not enough observations to change clip ranking yet.")
    else:
        report["notes"].append("Use performance patterns as a small ranking signal, not as a replacement for campaign fit.")
        report["notes"].append("Prefer patterns supported by multiple published clips before changing future ranking.")

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
