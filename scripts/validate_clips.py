import json
import subprocess
import sys
from pathlib import Path


def probe(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_streams",
            "-show_format",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def validate_clip(path):
    if path.stat().st_size < 100 * 1024:
        return False, "file is unexpectedly small"

    try:
        data = probe(path)
    except Exception as exc:
        return False, f"ffprobe failed: {exc}"

    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if video is None:
        return False, "missing video stream"
    if audio is None:
        return False, "missing audio stream"

    if int(video.get("width", 0)) != 1080 or int(video.get("height", 0)) != 1920:
        return False, f"wrong dimensions: {video.get('width')}x{video.get('height')}"

    try:
        duration = float(data.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        duration = 0

    if duration <= 0:
        return False, "invalid duration"

    return True, f"1080x1920, {duration:.2f}s, audio present"


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: validate_clips.py <clips_dir>")

    root = Path(sys.argv[1])
    clips = sorted(root.rglob("*.mp4")) if root.exists() else []
    valid = 0
    invalid = 0

    for clip in clips:
        ok, reason = validate_clip(clip)
        if ok:
            valid += 1
            print(f"VALID   {clip}: {reason}")
        else:
            invalid += 1
            print(f"INVALID {clip}: {reason}")
            clip.unlink(missing_ok=True)

    print(f"Validation complete: {valid} valid, {invalid} removed")
    if valid == 0:
        raise SystemExit("No usable clips remain after validation")


if __name__ == "__main__":
    main()
