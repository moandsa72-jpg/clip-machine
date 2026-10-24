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


def run_filter(path, filter_name):
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "info", "-i", str(path),
            "-vf", filter_name, "-an", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    return result.stderr


def detect_warnings(path, duration):
    warnings = []

    # These are quality warnings, not automatic failures. A brief black frame
    # or a short silence can be intentional, so keep the hard gate conservative.
    black_log = run_filter(path, "blackdetect=d=0.6:pix_th=0.10")
    if "black_start:" in black_log:
        warnings.append("black frame detected")

    silence_log = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "info", "-i", str(path),
            "-af", "silencedetect=noise=-45dB:d=0.8", "-vn", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    ).stderr
    if "silence_start: 0" in silence_log:
        warnings.append("silence at clip start")
    if "silence_end:" in silence_log and duration > 0:
        last_end = silence_log.rsplit("silence_end:", 1)[-1].split("|", 1)[0].strip()
        try:
            if duration - float(last_end) < 0.15:
                warnings.append("silence at clip end")
        except ValueError:
            pass

    return warnings


def validate_clip(path):
    if path.stat().st_size < 100 * 1024:
        return False, "file is unexpectedly small", []

    try:
        data = probe(path)
    except Exception as exc:
        return False, f"ffprobe failed: {exc}", []

    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if video is None:
        return False, "missing video stream", []
    if audio is None:
        return False, "missing audio stream", []

    if int(video.get("width", 0)) != 1080 or int(video.get("height", 0)) != 1920:
        return False, f"wrong dimensions: {video.get('width')}x{video.get('height')}", []

    try:
        duration = float(data.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        duration = 0

    if duration <= 0:
        return False, "invalid duration", []

    warnings = detect_warnings(path, duration)
    reason = f"1080x1920, {duration:.2f}s, audio present"
    if warnings:
        reason += "; warnings: " + ", ".join(warnings)
    return True, reason, warnings


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: validate_clips.py <clips_dir>")

    root = Path(sys.argv[1])
    clips = sorted(root.rglob("*.mp4")) if root.exists() else []
    valid = 0
    invalid = 0
    warning_count = 0
    report = {"valid": [], "invalid": [], "summary": {}}

    for clip in clips:
        ok, reason, warnings = validate_clip(clip)
        if ok:
            valid += 1
            warning_count += len(warnings)
            print(f"VALID   {clip}: {reason}")
            report["valid"].append({"path": str(clip), "warnings": warnings})
        else:
            invalid += 1
            print(f"INVALID {clip}: {reason}")
            report["invalid"].append({"path": str(clip), "reason": reason})
            clip.unlink(missing_ok=True)

    report["summary"] = {
        "valid": valid,
        "invalid_removed": invalid,
        "warnings": warning_count,
    }
    report_path = root / "validation_report.json"
    root.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)

    print(f"Validation complete: {valid} valid, {invalid} removed, {warning_count} warnings")
    if valid == 0:
        raise SystemExit("No usable clips remain after validation")


if __name__ == "__main__":
    main()
