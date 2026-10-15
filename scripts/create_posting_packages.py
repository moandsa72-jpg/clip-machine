import json
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


def resolve_clip_directory(
    campaign,
    default_directory,
):
    configured_directory = campaign.get(
        "clips_directory"
    )

    if not configured_directory:
        return default_directory

    return Path(configured_directory)


def build_package(
    campaign_id,
    campaign,
    clips,
    clip_directory,
):
    rules = campaign.get("rules", {})

    warnings = []

    if rules.get("clip_min_seconds") is None:
        warnings.append(
            "Minimum clip duration has not been configured."
        )

    if rules.get("clip_max_seconds") is None:
        warnings.append(
            "Maximum clip duration has not been configured."
        )

    if not rules.get("allowed_platforms"):
        warnings.append(
            "Allowed posting platforms must be confirmed."
        )

    if not rules.get("required_hashtags"):
        warnings.append(
            "Confirm campaign-specific hashtag requirements."
        )

    if not rules.get("required_mentions"):
        warnings.append(
            "Confirm campaign-specific mention requirements."
        )

    if not rules.get("prohibited_elements"):
        warnings.append(
            "Review the campaign brief for prohibited content."
        )

    clip_packages = []

    for clip in clips:
        clip_packages.append({
            "filename": clip.name,
            "video_path": str(clip),
            "title": "",
            "caption": "",
            "hashtags": list(
                rules.get("required_hashtags") or []
            ),
            "mentions": list(
                rules.get("required_mentions") or []
            ),
            "seo_keywords": [],
            "posting_platform": None,
            "published_url": None,
            "submission_status": "not_published"
        })

    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign.get(
            "name",
            campaign_id
        ),
        "platform_type": campaign.get(
            "platform",
            campaign.get(
                "type",
                "campaign_platform"
            )
        ),
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "status": "draft_requires_campaign_review",
        "campaign_rules": rules,
        "clip_source_directory": str(clip_directory),
        "compliance_warnings": warnings,
        "clips": clip_packages,
        "instructions": [
            "Confirm the active campaign brief.",
            "Verify permitted platforms and clip duration.",
            "Complete the title, caption, and SEO keywords.",
            "Verify required hashtags and account mentions.",
            "Check prohibited content and posting requirements.",
            "Publish manually and record the public post URL.",
            "Submit the post using the campaign's required method."
        ]
    }


def main():
    if len(sys.argv) not in (4, 5):
        print(
                    sys.exit(
            "Usage: python scripts/create_posting_packages.py "
            "<campaign_config.json> <clips_directory> "
            "<output_directory> [campaign_id]"
                    )
            
            
        )
        sys.exit(1)

    config_path = Path(sys.argv[1])
    default_clips_directory = Path(sys.argv[2])
    output_directory = Path(sys.argv[3])

    selected_campaign_id = (
        sys.argv[4]
        if len(sys.argv) == 5
        else None
)
    if not config_path.is_file():
        sys.exit(
            f"Campaign config not found: {config_path}"
        )

    if not default_clips_directory.is_dir():
        sys.exit(
            f"Default clips directory not found: "
            f"{default_clips_directory}"
        )

    config = load_json(config_path)
    campaigns = config.get("campaigns")

    if not isinstance(campaigns, dict) or not campaigns:
        sys.exit(
            "Configuration must contain a non-empty "
            "'campaigns' object."
        )

    generated = 0

    for campaign_id, campaign in campaigns.items():
                if (
            selected_campaign_id
            and campaign_id != selected_campaign_id
        ):
            continue
        if not isinstance(campaign, dict):
            print(
                f"Skipping invalid campaign: {campaign_id}"
            )
            continue

        clip_directory = resolve_clip_directory(
            campaign,
            default_clips_directory
        )

        if not clip_directory.is_dir():
            sys.exit(
                f"Clip directory not found for "
                f"{campaign_id}: {clip_directory}"
            )

        clips = sorted(
            clip
            for clip in clip_directory.iterdir()
            if clip.is_file()
            and clip.suffix.lower() == ".mp4"
        )

        if not clips:
            sys.exit(
                f"No MP4 clips found for "
                f"{campaign_id} in: {clip_directory}"
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

        print(
            f"Created package for "
            f"{campaign.get('name', campaign_id)}"
        )

        print(f"  Clips included: {len(clips)}")
        print(f"  Clip source: {clip_directory}")
        print(f"  Output: {output_path}")
        print(
            f"  Compliance warnings: "
            f"{len(package['compliance_warnings'])}"
        )

        generated += 1

    if generated == 0:
        sys.exit("No campaign packages were generated.")

    print()
    print(
        f"Successfully created "
        f"{generated} campaign package(s)."
    )


if __name__ == "__main__":
    main()
