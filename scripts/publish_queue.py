#!/usr/bin/env python3
"""Publish supported queue items without paid services.

YouTube can be published with a user-provided OAuth access token. TikTok direct
posting is intentionally not automated here because TikTok's current Content
Posting API rules restrict internal-only utilities and unaudited clients.
Instagram remains a ready-to-post handoff until an approved account/app flow is
configured. No third-party scheduler or paid API is used.
"""

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CHUNK_SIZE = 8 * 1024 * 1024


def load(path):
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def youtube_upload(item):
    token = os.environ.get("YOUTUBE_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("YOUTUBE_ACCESS_TOKEN is not configured")
    video_path = Path(item["video_path"])
    if not video_path.is_file():
        raise RuntimeError(f"Video not found: {video_path}")

    copy = item.get("copy", {})
    metadata = {
        "snippet": {
            "title": copy.get("title", item.get("clip_filename", "Clip"))[:100],
            "description": copy.get("description", ""),
            "tags": [x.strip("#") for x in str(copy.get("keywords", "")).split(",") if x.strip()],
            "categoryId": "22",
        },
        "status": {"privacyStatus": os.environ.get("YOUTUBE_PRIVACY", "private")},
    }
    body = json.dumps(metadata).encode("utf-8")
    request = urllib.request.Request(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(video_path.stat().st_size),
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        upload_url = response.headers.get("Location")
    if not upload_url:
        raise RuntimeError("YouTube did not return an upload URL")

    total = video_path.stat().st_size
    offset = 0
    with video_path.open("rb") as file:
        while offset < total:
            chunk = file.read(CHUNK_SIZE)
            if not chunk:
                break
            end = offset + len(chunk) - 1
            upload = urllib.request.Request(
                upload_url,
                data=chunk,
                method="PUT",
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {offset}-{end}/{total}",
                },
            )
            try:
                response = urllib.request.urlopen(upload, timeout=300)
                payload = response.read().decode("utf-8")
                if response.status in (200, 201):
                    result = json.loads(payload)
                    offset = total
                    break
                offset = end + 1
            except urllib.error.HTTPError as exc:
                if exc.code != 308:
                    raise
                range_header = exc.headers.get("Range", "")
                match = range_header.rsplit("-", 1)[-1] if "-" in range_header else ""
                try:
                    offset = int(match) + 1
                except ValueError:
                    offset = end + 1
    else:
        result = {}

    video_id = result.get("id")
    if not video_id:
        raise RuntimeError("YouTube upload completed without a video id")
    return f"https://www.youtube.com/watch?v={video_id}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("queue")
    parser.add_argument("--platform", choices=["youtube_shorts", "tiktok", "instagram_reels"], required=True)
    parser.add_argument("--execute", action="store_true", help="Actually publish supported platforms; default is dry-run")
    args = parser.parse_args()

    data = load(args.queue)
    now = datetime.now(timezone.utc).isoformat()
    results = []
    for item in data.get("queue", []):
        if item.get("platform") != args.platform:
            continue
        result = {"queue_id": item.get("queue_id"), "platform": args.platform, "status": "dry_run"}
        if not args.execute:
            results.append(result)
            continue
        if args.platform == "youtube_shorts":
            try:
                url = youtube_upload(item)
                item["published_url"] = url
                item["published_at"] = now
                item["status"] = "published"
                result.update({"status": "published", "published_url": url})
            except Exception as exc:
                item["status"] = "publish_failed"
                result.update({"status": "publish_failed", "error": str(exc)})
        else:
            item["status"] = "manual_publish_required"
            result.update({"status": "manual_publish_required", "reason": "Use the platform's official posting flow; no paid scheduler or unsupported automation is used."})
        results.append(result)
    data["last_publish_run"] = now
    save(args.queue, data)
    print(json.dumps({"results": results}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
