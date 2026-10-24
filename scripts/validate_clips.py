import json
import subprocess
import sys
from pathlib import Path

try:
    import cv2
    import mediapipe as mp
except ImportError:
    cv2 = None
    mp = None


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


def load_metadata(path):
    metadata_path = path.with_suffix(".json")
    if not metadata_path.is_file():
        return None
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def metadata_qa(path):
    warnings = []
    metadata = load_metadata(path)
    if metadata is None:
        warnings.append("missing or unreadable clip metadata")
        return warnings, {"metadata_found": False}

    hook_text = str(metadata.get("hook_text", "")).strip()
    hook_count = int(metadata.get("hook_word_count", len(hook_text.split()))) if hook_text else 0
    if not hook_text:
        warnings.append("missing opening hook")
    elif hook_count != 4 and hook_count != 5:
        warnings.append(f"hook is {hook_count} words; expected 4–5")

    framing_mode = metadata.get("framing_mode")
    if framing_mode != "stable_dead_zone_capped_speed":
        warnings.append("clip was rendered without the stable framing mode")

    return warnings, {
        "metadata_found": True,
        "hook_word_count": hook_count,
        "hook_text": hook_text,
        "framing_mode": framing_mode,
    }


def visual_face_qa(path, duration):
    """Sample the rendered clip and check whether face framing looks stable."""
    result = {
        "available": bool(cv2 is not None and mp is not None),
        "samples": 0,
        "detections": 0,
        "detection_ratio": 0.0,
        "median_center_x": None,
        "max_center_jump": None,
        "median_face_height": None,
        "warnings": [],
    }
    if cv2 is None or mp is None:
        result["warnings"].append("visual face QA unavailable")
        return result

    sample_count = min(8, max(4, int(duration // 2) + 1))
    times = [0.0] if sample_count == 1 else [duration * i / (sample_count - 1) for i in range(sample_count)]
    centers = []
    heights = []

    video = cv2.VideoCapture(str(path))
    if not video.isOpened():
        result["warnings"].append("could not open clip for visual QA")
        return result

    detector = mp.solutions.face_detection
    with detector.FaceDetection(model_selection=1, min_detection_confidence=0.5) as face_detector:
        for time in times:
            video.set(cv2.CAP_PROP_POS_MSEC, time * 1000.0)
            success, frame = video.read()
            if not success:
                continue
            result["samples"] += 1
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            detections = face_detector.process(rgb).detections
            if not detections:
                continue

            frame_height, frame_width = frame.shape[:2]
            detection = max(
                detections,
                key=lambda item: max(0.0, item.location_data.relative_bounding_box.width)
                * max(0.0, item.location_data.relative_bounding_box.height),
            )
            box = detection.location_data.relative_bounding_box
            center_x = box.xmin + box.width / 2.0
            face_height = max(0.0, box.height)
            centers.append(max(0.0, min(1.0, center_x)))
            heights.append(face_height)

    video.release()

    result["detections"] = len(centers)
    result["detection_ratio"] = round(
        len(centers) / max(1, result["samples"]), 3
    )
    if centers:
        ordered = sorted(centers)
        result["median_center_x"] = round(ordered[len(ordered) // 2], 3)
        result["max_center_jump"] = round(
            max(abs(right - left) for left, right in zip(centers, centers[1:]))
            if len(centers) > 1 else 0.0,
            3,
        )
        ordered_heights = sorted(heights)
        result["median_face_height"] = round(
            ordered_heights[len(ordered_heights) // 2], 3
        )

        if result["detection_ratio"] < 0.5:
            result["warnings"].append("face missing in most visual QA samples")
        if result["median_center_x"] < 0.25 or result["median_center_x"] > 0.75:
            result["warnings"].append("face is consistently off-center")
        if result["max_center_jump"] > 0.16:
            result["warnings"].append("rapid face/camera movement detected")
        if result["median_face_height"] > 0.42:
            result["warnings"].append("face is very large; possible excessive zoom")
    else:
        result["warnings"].append("no face detected in visual QA samples")

    return result


def validate_clip(path):
    if path.stat().st_size < 100 * 1024:
        return False, "file is unexpectedly small", [], {}

    try:
        data = probe(path)
    except Exception as exc:
        return False, f"ffprobe failed: {exc}", [], {}

    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if video is None:
        return False, "missing video stream", [], {}
    if audio is None:
        return False, "missing audio stream", [], {}

    if int(video.get("width", 0)) != 1080 or int(video.get("height", 0)) != 1920:
        return False, f"wrong dimensions: {video.get('width')}x{video.get('height')}", [], {}

    try:
        duration = float(data.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        duration = 0

    if duration <= 0:
        return False, "invalid duration", [], {}

    warnings = detect_warnings(path, duration)
    metadata_warnings, metadata_details = metadata_qa(path)
    warnings.extend(metadata_warnings)
    face_details = visual_face_qa(path, duration)
    warnings.extend(face_details["warnings"])

    reason = f"1080x1920, {duration:.2f}s, audio present"
    if warnings:
        reason += "; warnings: " + ", ".join(warnings)

    details = {
        "metadata": metadata_details,
        "visual_face_qa": face_details,
    }
    return True, reason, warnings, details


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
        ok, reason, warnings, details = validate_clip(clip)
        if ok:
            valid += 1
            warning_count += len(warnings)
            print(f"VALID   {clip}: {reason}")
            report["valid"].append({
                "path": str(clip),
                "warnings": warnings,
                "qa": details,
            })
        else:
            invalid += 1
            print(f"INVALID {clip}: {reason}")
            report["invalid"].append({"path": str(clip), "reason": reason})
            clip.unlink(missing_ok=True)

    report["summary"] = {
        "valid": valid,
        "invalid_removed": invalid,
        "warnings": warning_count,
        "visual_face_qa": bool(cv2 is not None and mp is not None),
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
