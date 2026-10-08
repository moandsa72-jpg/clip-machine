import json
import subprocess
import sys
from pathlib import Path


def run_command(command):
    print("Running:")
    print(" ".join(str(x) for x in command))
    subprocess.run(command, check=True)


def make_clip(video_path, start, end, output_path):
    duration = end - start

    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start),
        "-i",
        str(video_path),
        "-t",
        str(duration),
        "-vf",
        (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920"
        ),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    run_command(command)


def main():
    if len(sys.argv) != 4:
        print(
            "Usage: python scripts/make_clips.py "
            "<video> <moments.json> <output_dir>"
        )
        sys.exit(1)

    video_path = Path(sys.argv[1])
    moments_path = Path(sys.argv[2])
    output_dir = Path(sys.argv[3])

    if not video_path.exists():
        raise FileNotFoundError(
            f"Video not found: {video_path}"
        )

    if not moments_path.exists():
        raise FileNotFoundError(
            f"Moments file not found: {moments_path}"
        )

    with open(moments_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    moments = data.get("moments", [])

    if not moments:
        print("No moments found.")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    print()
    print("========================================")
    print("CREATING SHORT-FORM CLIPS")
    print("========================================")
    print(f"Moments found: {len(moments)}")
    print()

    created = 0

    for index, moment in enumerate(moments, start=1):

        start = float(moment["start"])
        end = float(moment["end"])

        if end <= start:
            print(f"Skipping moment {index}: invalid timing")
            continue

        output_path = output_dir / f"clip_{index:02d}.mp4"

        print(
            f"Clip {index}: "
            f"{start:.2f}s → {end:.2f}s"
        )

        make_clip(
            video_path,
            start,
            end,
            output_path
        )

        created += 1

    print()
    print("========================================")
    print("CLIP CREATION COMPLETE")
    print("========================================")
    print(f"Created: {created}")
    print(f"Output directory: {output_dir}")
    print("========================================")


if __name__ == "__main__":
    main()
