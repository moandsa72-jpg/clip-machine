import json
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
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def resolve_clip_directory(campaign, default_directory):
    configured_directory = campaign.get("clips_directory")

    if not configured_directory:
        return default_directory

    return Path(configured_directory)


def build_clip_package(clip, rules):
    duration = probe_duration(clip)
    clip_warnings = []

    minimum = rules.get("clip_min_seconds")
    maximum = rules.get("clip_max_seconds")

    if duration is None:
        clip_warnings.append("Could not determine clip duration.")
    else:
        if minimum is not None and duration < float(minimum):
            clip_warnings.append(
                f"Clip is shorter than the configured minimum of {minimum}s."
            )
        if maximum is not None and duration > float(maximum):
            clip_warnings.append(
                f"Clip is longer than the configured maximum of {maximum}s."
            )

    return {
        "filename": clip.name,
        "video_path": str(clip),
        "duration_seconds": round(duration, 3) if duration is not None else None,
        "title": "",
        "caption": "",
        "hashtags": list(rules.get("required_hashtags") or []),
        "mentions": list(rules.get("required_mentions") or []),
        "seo_keywords": [],
        "posting_platform": None,
        "published_url": None,
        "submission_status": "not_published",
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
        build_clip_package(clip, rules)
        for clip in clips
    ]

    clip_warning_count = sum(
        len(clip.get("compliance_warnings", []))
        for clip in clip_packages
    )

    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign.get("name", campaign_id),
        "platform_type": campaign.get(
            "platform",
            campaign.get("type", "campaign_platform"),
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "draft_requires_campaign_review",
        "campaign_rules": rules,
        "content_requirements": requirements,
        "payout": campaign.get("payout", {}),
        "clip_source_directory": str(clip_directory),
        "clip_count": len(clip_packages),
        "compliance_warning_count": len(warnings) + clip_warning_count,
        "compliance_warnings": warnings,
        "clips": clip_packages,
        "instructions": [
            "Confirm the active campaign brief before submission.",
            "Review each clip's duration and compliance warnings.",
            "Complete the title, caption, and SEO keywords.",
            "Use the required hashtags and account mentions exactly as configured.",
            "Check the campaign's prohibited elements and content requirements.",
            "Select a permitted posting platform.",
            "Publish manually and record the public post URL.",
            "Submit the post using the campaign's required submission method.",
        ],
    }


def main():
    if len(sys.argv) not in (4, 5):
        sys.exit(
            "Usage: python scripts/create_posting_packages.py "
            "<campaign_config.json> <clips_directory> "
            "<output_directory> [campaign_id]"
        )

    config_path = Path(sys.argv[1])
    default_clips_directory = Path(sys.argv[2])
    output_directory = Path(sys.argv[3])
    selected_campaign_id = sys.argv[4] if len(sys.argv) == 5 else None

    if not config_path.is_file():
        sys.exit(f"Campaign config not found: {config_path}")

    if not default_clips_directory.is_dir():
        sys.exit(
            f"Default clips directory not found: {default_clips_directory}"
        )

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

        clip_directory = resolve_clip_directory(
            campaign,
            default_clips_directory,
        )

        if not clip_directory.is_dir():
            sys.exit(
                f"Clip directory not found for {campaign_id}: {clip_directory}"
            )

        clips = sorted(
            clip
            for clip in clip_directory.rglob("*.mp4")
            if clip.is_file()
        )

        if not clips:
            sys.exit(
                f"No MP4 clips found for {campaign_id} in: {clip_directory}"
            )

        package = build_package(
            campaign_id,
            campaign,
            clips,
            clip_directory,
        )

        output_path = (
            output_directory
            / campaign_id
            / "posting_package.json"
        )

        save_json(output_path, package)

        print(f"Created package for {campaign.get('name', campaign_id)}")
        print(f"  Clips included: {len(clips)}")
        print(f"  Clip source: {clip_directory}")
        print(f"  Output: {output_path}")
        print(f"  Compliance warnings: {package['compliance_warning_count']}")

        generated += 1

    if generated == 0:
        sys.exit("No campaign packages were generated.")

    print()
    print(f"Successfully created {generated} campaign package(s).")


if __name__ == "__main__":
    main()
