import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
        file.write("\n")


def probe_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def resolve_clip_directory(campaign, default_directory):
    configured_directory = campaign.get("clips_directory")
    return Path(configured_directory) if configured_directory else default_directory


def load_clip_metadata(clip):
    path = clip.with_suffix(".json")
    if not path.is_file():
        return {}
    try:
        data = load_json(path)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def compact_text(text, limit=180):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[:limit].rstrip(" .,!?-")


def build_title(campaign, metadata, index):
    hook = compact_text(metadata.get("hook_text") or metadata.get("text"), 110)
    name = campaign.get("name", campaign.get("id", "Campaign"))
    if hook:
        return f"{hook} | {name}"[:150]
    return f"{name} Clip {index:02d}"


def build_caption(campaign, metadata, rules):
    hook = compact_text(metadata.get("hook_text") or metadata.get("text"), 220)
    hashtags = " ".join(rules.get("required_hashtags") or [])
    mentions = " ".join(rules.get("required_mentions") or [])
    parts = [hook] if hook else []
    featured = campaign.get("content_requirements", {}).get("featured_person")
    if featured:
        parts.append(f"Featuring {featured}.")
    if mentions:
        parts.append(mentions)
    if hashtags:
        parts.append(hashtags)
    return " ".join(parts).strip()


def build_seo(metadata, campaign):
    text = " ".join([
        str(metadata.get("hook_text", "")),
        str(metadata.get("text", "")),
        str(campaign.get("name", "")),
        str(metadata.get("content_type", "")),
    ])
    candidates = re.findall(r"[A-Za-z0-9][A-Za-z0-9'’-]{2,}", text.lower())
    stop = {
        "the", "and", "that", "this", "with", "from", "have", "what", "when", "your",
        "they", "just", "about", "into", "for", "are", "was", "were", "been", "will",
        "clip", "video", "featuring", "really", "like",
    }
    seen = []
    for word in candidates:
        if word in stop or word in seen:
            continue
        seen.append(word)
        if len(seen) >= 15:
            break
    return seen


def posting_intelligence(metadata, duration, campaign, rules, caption):
    score = 50
    strengths = []
    warnings = []
    hook_score = metadata.get("hook_score")

    if isinstance(hook_score, (int, float)):
        if hook_score >= 8:
            score += 25
            strengths.append("strong hook")
        elif hook_score >= 6:
            score += 15
            strengths.append("solid hook")
        elif hook_score < 4:
            score -= 20
            warnings.append("weak hook")

    if metadata.get("hook_optimized"):
        score += 5
        strengths.append("hook optimized")

    if duration is None:
        warnings.append("duration unavailable")
    elif 15 <= duration <= 75:
        score += 10
        strengths.append("short-form friendly length")
    elif duration > 120:
        score -= 10
        warnings.append("long for short-form")

    text = " ".join([
        str(metadata.get("hook_text", "")),
        str(metadata.get("text", "")),
    ]).lower()
    if len(text.split()) >= 12:
        score += 5
        strengths.append("enough context for a specific caption")
    else:
        warnings.append("limited transcript context")

    if metadata.get("fallback"):
        score -= 15
        warnings.append("fallback clip requires review")

    prohibited = [str(x).lower() for x in rules.get("prohibited_elements", [])]
    compliance_notes = " ".join(prohibited)
    if compliance_notes and any(term in text for term in ("spam", "duplicate", "repost")):
        score -= 20
        warnings.append("transcript may conflict with campaign restrictions")

    required_hashtags = rules.get("required_hashtags") or []
    missing_tags = [tag for tag in required_hashtags if tag not in caption]
    if missing_tags:
        score -= 20
        warnings.append("required hashtags missing from caption")
    else:
        strengths.append("campaign hashtags included")

    featured = campaign.get("content_requirements", {}).get("featured_person")
    if featured and featured.lower() in text:
        score += 5
        strengths.append("featured person appears in text")

    score = max(0, min(100, int(score)))
    if score >= 80:
        decision = "ready"
    elif score >= 60:
        decision = "review"
    else:
        decision = "hold"

    return {
        "score": score,
        "decision": decision,
        "strengths": strengths,
        "warnings": warnings,
    }


def build_platform_posts(campaign, metadata, rules, title, caption, seo_keywords):
    hashtags = " ".join(rules.get("required_hashtags") or [])
    keywords = ", ".join(seo_keywords[:8])
    base_caption = caption or compact_text(metadata.get("text"), 220)
    platforms = rules.get("allowed_platforms") or []
    posts = {}

    for platform in platforms:
        key = platform.lower().replace(" ", "_")
        if platform == "YouTube Shorts":
            posts[key] = {
                "title": title[:100],
                "description": f"{base_caption}\n\n{hashtags}".strip(),
                "keywords": keywords,
            }
        elif platform == "TikTok":
            posts[key] = {
                "caption": f"{base_caption} {hashtags}".strip(),
            }
        elif platform == "Instagram Reels":
            posts[key] = {
                "caption": f"{base_caption}\n\n{hashtags}".strip(),
            }
        else:
            posts[key] = {"caption": f"{base_caption} {hashtags}".strip()}
    return posts


def build_clip_package(clip, rules, campaign, index):
    duration = probe_duration(clip)
    metadata = load_clip_metadata(clip)
    clip_warnings = []

    minimum = rules.get("clip_min_seconds")
    maximum = rules.get("clip_max_seconds")
    if duration is None:
        clip_warnings.append("Could not determine clip duration.")
    else:
        if minimum is not None and duration < float(minimum):
            clip_warnings.append(f"Clip is shorter than the configured minimum of {minimum}s.")
        if maximum is not None and duration > float(maximum):
            clip_warnings.append(f"Clip is longer than the configured maximum of {maximum}s.")

    if not metadata:
        clip_warnings.append("Clip metadata sidecar is missing; generated copy may be less specific.")
    if metadata.get("fallback"):
        clip_warnings.append("Clip was generated from the under-3-minute zero-moment fallback path; review campaign fit.")
    if metadata.get("hook_score", 0) and float(metadata.get("hook_score", 0)) < 4:
        clip_warnings.append("Hook score is weak; review the opening before posting.")

    allowed = list(rules.get("allowed_platforms") or [])
    posting_platform = allowed[0] if allowed else None
    title = build_title(campaign, metadata, index)
    caption = build_caption(campaign, metadata, rules)
    seo_keywords = build_seo(metadata, campaign)
    intelligence = posting_intelligence(metadata, duration, campaign, rules, caption)

    return {
        "filename": clip.name,
        "video_path": str(clip),
        "duration_seconds": round(duration, 3) if duration is not None else None,
        "title": title,
        "caption": caption,
        "hashtags": list(rules.get("required_hashtags") or []),
        "mentions": list(rules.get("required_mentions") or []),
        "seo_keywords": seo_keywords,
        "posting_platform": posting_platform,
        "platform_posts": build_platform_posts(campaign, metadata, rules, title, caption, seo_keywords),
        "intelligence": intelligence,
        "published_url": None,
        "submission_status": "not_published",
        "hook": {
            "score": metadata.get("hook_score", 0),
            "text": metadata.get("hook_text", ""),
            "optimized": bool(metadata.get("hook_optimized", False)),
        },
        "edit_quality": {
            "edge_silence_trimmed": bool(metadata.get("edge_silence_trimmed", False)),
            "face_tracking": True,
            "captions_max_words": 4,
            "vertical_resolution": "1080x1920",
        },
        "compliance_warnings": clip_warnings,
    }


def build_package(campaign_id, campaign, clips, clip_directory):
    rules = campaign.get("rules", {})
    requirements = campaign.get("content_requirements", {})
    warnings = []

    if rules.get("clip_min_seconds") is None:
        warnings.append("Minimum clip duration is not configured.")
    if rules.get("clip_max_seconds") is None:
        warnings.append("Maximum clip duration is not configured.")
    if not rules.get("allowed_platforms"):
        warnings.append("Allowed posting platforms are not configured.")
    if "required_hashtags" not in rules:
        warnings.append("Campaign hashtag requirements are not configured.")
    if "required_mentions" not in rules:
        warnings.append("Campaign mention requirements are not configured.")
    if not rules.get("prohibited_elements"):
        warnings.append("Campaign prohibited-content rules are not configured.")
    if requirements.get("brand_logo_overlay_required") and not requirements.get("featured_person"):
        warnings.append("Logo overlay is required but the featured person is not configured.")

    clip_packages = [
        build_clip_package(clip, rules, campaign, index)
        for index, clip in enumerate(clips, start=1)
    ]
    clip_packages.sort(key=lambda item: item["intelligence"]["score"], reverse=True)
    clip_warning_count = sum(len(clip.get("compliance_warnings", [])) for clip in clip_packages)
    ready_count = sum(clip["intelligence"]["decision"] == "ready" for clip in clip_packages)
    review_count = sum(clip["intelligence"]["decision"] == "review" for clip in clip_packages)
    hold_count = sum(clip["intelligence"]["decision"] == "hold" for clip in clip_packages)

    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign.get("name", campaign_id),
        "platform_type": campaign.get("platform", campaign.get("type", "campaign_platform")),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "draft_requires_campaign_review",
        "campaign_rules": rules,
        "content_requirements": requirements,
        "payout": campaign.get("payout", {}),
        "clip_source_directory": str(clip_directory),
        "clip_count": len(clip_packages),
        "posting_scan": {
            "status": "completed",
            "sorted_by_intelligence": True,
            "ready_count": ready_count,
            "review_count": review_count,
            "hold_count": hold_count,
            "rule": "ready >= 80, review 60-79, hold < 60",
        },
        "compliance_warning_count": len(warnings) + clip_warning_count,
        "compliance_warnings": warnings,
        "clips": clip_packages,
        "instructions": [
            "Start with the highest-intelligence-score clips; quality is preferred over quantity.",
            "Post only clips marked ready after campaign review; inspect review/hold clips first.",
            "Use the platform-specific copy generated under each clip's platform_posts section.",
            "Confirm the active campaign brief before submission.",
            "Check the campaign's prohibited elements and content requirements.",
            "Publish and record the public post URL after the platform post is live.",
        ],
    }


def main():
    if len(sys.argv) not in (4, 5):
        sys.exit("Usage: python scripts/create_posting_packages.py <campaign_config.json> <clips_directory> <output_directory> [campaign_id]")

    config_path = Path(sys.argv[1])
    default_clips_directory = Path(sys.argv[2])
    output_directory = Path(sys.argv[3])
    selected_campaign_id = sys.argv[4] if len(sys.argv) == 5 else None

    if not config_path.is_file():
        sys.exit(f"Campaign config not found: {config_path}")
    if not default_clips_directory.is_dir():
        sys.exit(f"Default clips directory not found: {default_clips_directory}")

    config = load_json(config_path)
    campaigns = config.get("campaigns")
    if not isinstance(campaigns, dict) or not campaigns:
        sys.exit("Configuration must contain a non-empty 'campaigns' object.")

    generated = 0
    for campaign_id, campaign in campaigns.items():
        if selected_campaign_id and campaign_id != selected_campaign_id:
            continue
        if not isinstance(campaign, dict):
            print(f"Skipping invalid campaign: {campaign_id}")
            continue

        clip_directory = resolve_clip_directory(campaign, default_clips_directory)
        if not clip_directory.is_dir():
            sys.exit(f"Clip directory not found for {campaign_id}: {clip_directory}")

        clips = sorted(clip_directory.rglob("*.mp4") for _ in [0])
        clips = [clip for group in clips for clip in (group if isinstance(group, list) else [])]
        if not clips:
            sys.exit(f"No MP4 clips found for {campaign_id} in: {clip_directory}")

        package = build_package(campaign_id, campaign, clips, clip_directory)
        output_path = output_directory / campaign_id / "posting_package.json"
        save_json(output_path, package)

        print(f"Created intelligent package for {campaign.get('name', campaign_id)}")
        print(f"  Clips scanned: {len(clips)}")
        print(f"  Ready: {package['posting_scan']['ready_count']}")
        print(f"  Review: {package['posting_scan']['review_count']}")
        print(f"  Hold: {package['posting_scan']['hold_count']}")
        print(f"  Clip source: {clip_directory}")
        print(f"  Output: {output_path}")
        print(f"  Compliance warnings: {package['compliance_warning_count']}")
        generated += 1

    if generated == 0:
        sys.exit("No campaign packages were generated.")
    print(f"Successfully created {generated} intelligent campaign package(s).")


if __name__ == "__main__":
    main()
