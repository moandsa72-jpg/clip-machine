import json
import re
import subprocess
import sys
from pathlib import Path


def probe_duration(video):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def detect_scene_changes(video):
    command = [
        "ffmpeg", "-hide_banner", "-i", str(video),
        "-vf", "select='gt(scene,0.22)',showinfo",
        "-an", "-f", "null", "-"
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    log = result.stderr
    return sorted({
        float(value)
        for value in re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", log)
    })


def build_visual_moments(duration, cuts):
    if duration < 10:
        raise ValueError(f"Source is too short for a usable clip: {duration:.2f}s")

    clip_length = min(24.0, duration)
    stride = 6.0
    candidates = []

    start = 0.0
    while start + 10.0 <= duration:
        end = min(start + clip_length, duration)
        if end - start < 10.0:
            break

        inside = [cut for cut in cuts if start + 0.5 <= cut <= end - 0.5]
        # Favor windows with several distinct visual transitions, without
        # pretending that scene changes alone prove a moment is entertaining.
        density = len(inside) / max((end - start) / 10.0, 1.0)
        spread = len({int((cut - start) // 4) for cut in inside})
        score = round(density * 4 + spread * 1.5, 2)
        candidates.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "score": score,
            "text": "Modern Warfare 4 Season 1 official trailer visual sequence",
            "fallback": True,
            "visual_only": True,
            "scene_changes": len(inside),
        })
        start += stride

    selected = []
    for candidate in sorted(candidates, key=lambda item: item["score"], reverse=True):
        if all(
            max(0.0, min(candidate["end"], item["end"]) - max(candidate["start"], item["start"]))
            / max(max(candidate["end"], item["end"]) - min(candidate["start"], item["start"]), 1.0)
            < 0.35
            for item in selected
        ):
            selected.append(candidate)
        if len(selected) >= 5:
            break

    return sorted(selected, key=lambda item: item["start"])


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python scripts/find_visual_moments.py <video> <output.json>")

    video = Path(sys.argv[1])
    output = Path(sys.argv[2])
    if not video.is_file():
        raise FileNotFoundError(f"Video not found: {video}")

    duration = probe_duration(video)
    cuts = detect_scene_changes(video)
    moments = build_visual_moments(duration, cuts)
    if not moments:
        raise RuntimeError("Visual fallback could not create any clip windows.")

    data = {
        "source": str(video),
        "detector_version": "visual-scene-fallback-v1",
        "visual_only": True,
        "scene_change_count": len(cuts),
        "moments": moments,
        "count": len(moments),
        "review_note": "No speech transcript was available. These are scene-based candidates and require manual review; no spoken dialogue or captions were invented."
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"VISUAL MOMENT FALLBACK: {len(moments)} candidates from {len(cuts)} detected scene changes")
    print("No dialogue was inferred. Review every candidate before posting.")


if __name__ == "__main__":
    main()
