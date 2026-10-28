#!/usr/bin/env python3
"""Render a vertical photo slideshow draft from a ZIP of campaign reference images.

Requires FFmpeg (ffmpeg on PATH). This is a draft renderer only: it does not
publish anything. Confirm image usage rights and campaign pre-approval first.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_STORYBOARD = Path("campaigns/popmart_skullpanda/storyboard.json")


def run(cmd: list[str]) -> None:
    print("+", " ".join(str(part) for part in cmd), flush=True)
    subprocess.run(cmd, check=True)


def ffmpeg_escape(value: str) -> str:
    # Escape content used as drawtext text=... filter value.
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_file", type=Path, help="ZIP containing approved campaign photos")
    parser.add_argument("--output", type=Path, default=Path("output/campaign_drafts/skullpanda_draft.mp4"))
    parser.add_argument("--storyboard", type=Path, default=DEFAULT_STORYBOARD)
    parser.add_argument("--seconds-per-image", type=float, default=2.0)
    parser.add_argument("--width", type=int, default=720)
    parser.add_argument("--height", type=int, default=1280)
    parser.add_argument("--fps", type=int, default=24)
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        parser.error("ffmpeg was not found on PATH; install FFmpeg first")
    if not args.zip_file.is_file():
        parser.error(f"ZIP file does not exist: {args.zip_file}")
    if args.seconds_per_image <= 0 or args.fps <= 0:
        parser.error("seconds-per-image and fps must be positive")

    storyboard = json.loads(args.storyboard.read_text(encoding="utf-8"))
    slides = storyboard["slides"]
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="photo-campaign-") as tmp:
        tmpdir = Path(tmp)
        with zipfile.ZipFile(args.zip_file) as archive:
            archive.extractall(tmpdir)

        images = sorted(
            p for p in tmpdir.rglob("*")
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS
        )
        if not images:
            parser.error("No JPG, PNG, or WEBP images found inside the ZIP")

        # Prefer the explicit storyboard order; append remaining images as a fallback.
        by_name = {p.name.lower(): p for p in images}
        ordered: list[Path] = []
        for slide in slides:
            wanted = str(slide.get("image", "")).strip().lower()
            if wanted and wanted in by_name and by_name[wanted] not in ordered:
                ordered.append(by_name[wanted])
        if not ordered:
            ordered = images[:len(slides)]
        if len(ordered) < len(slides):
            # If some preferred names are absent, fill from other archive images.
            for image in images:
                if image not in ordered:
                    ordered.append(image)
                if len(ordered) >= len(slides):
                    break
        ordered = ordered[:len(slides)]

        segment_paths: list[Path] = []
        duration = args.seconds_per_image
        frame_count = max(1, round(duration * args.fps))
        for idx, (image, slide) in enumerate(zip(ordered, slides), start=1):
            segment = tmpdir / f"segment_{idx:02d}.mp4"
            title = ffmpeg_escape(str(slide.get("title", "SKULLPANDA")))
            subtitle = ffmpeg_escape(str(slide.get("subtitle", "")))
            # Use a blurred fill behind the image so portrait and landscape photos
            # both fill 9:16 without stretching or cutting off the full photo.
            vf = (
                f"scale={args.width}:{args.height}:force_original_aspect_ratio=increase,"
                f"crop={args.width}:{args.height},"
                "setsar=1,"
                "drawbox=x=0:y=ih*0.64:w=iw:h=ih*0.36:color=black@0.48:t=fill,"
                f"drawtext=text='{title}':font='DejaVu Sans':fontcolor=white:"
                f"fontsize=34:borderw=2:bordercolor=black@0.45:"
                "x=32:y=h*0.72,"
                f"drawtext=text='{subtitle}':font='DejaVu Sans':fontcolor=white:"
                f"fontsize=21:borderw=1:bordercolor=black@0.35:"
                "x=32:y=h*0.79"
            )
            run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-loop", "1", "-i", str(image), "-t", str(duration),
                "-vf", vf, "-r", str(args.fps), "-an",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(segment),
            ])
            segment_paths.append(segment)

        concat_file = tmpdir / "concat.txt"
        concat_file.write_text(
            "".join(f"file '{p.as_posix()}'\n" for p in segment_paths),
            encoding="utf-8",
        )
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c", "copy", "-movflags", "+faststart", str(args.output.resolve()),
        ])

    print(f"Draft saved to {args.output}")
    print(f"Slides: {len(ordered)} | Approx duration: {len(ordered) * duration:.1f}s")
    print("Silent draft only. Review footage permissions and get campaign approval before posting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
