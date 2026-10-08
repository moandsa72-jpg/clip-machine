import json
import subprocess
import sys
from pathlib import Path


def run_command(command):
    print("Running:", " ".join(str(x) for x in command))
    subprocess.run(command, check=True)


def make_clip(video_path, start, end, output_path, transcript_path):
    duration = end - start

    output_path.parent.mkdir(parents=True, exist_ok=True)

    subtitle_path = output_path.with_suffix(".ass")

    # Generate captions synchronized with the original speech.
    run_command([
        sys.executable,
        "scripts/captions.py",
        str(transcript_path),
        str(start),
        str(end),
        str(subtitle_path),
    ])

    # Build a safe FFmpeg subtitle filter path.
    subtitle_filter_path = str(subtitle_path.resolve())
    subtitle_filter_path = (
        subtitle_filter_path
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )

    video_filter = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,boxblur=20:10[bgblur];"
        "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fgfit];"
        "[bgblur][fgfit]overlay=(W-w)/2:(H-h)/2,"
        "setsar=1[base];"
        f"[base]subtitles='{subtitle_filter_path}'[outv]"
    )

    command = [
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-i", str(video_path),
        "-t", str(duration),
        "-filter_complex", video_filter,
        "-map", "[outv]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path),
    ]

    run_command(command)

    # Remove the temporary subtitle file after rendering.
    if subtitle_path.exists():
        subtitle_path.unlink()


def main():
    if len(sys.argv) != 5:
        print(
            "Usage: python scripts/make_clips.py "
            "<video> <moments.json> <output_dir> <transcript.json>"
        )
        sys.exit(1)

    video_path = Path(sys.argv[1])
    moments_path = Path(sys.argv[2])
    output_dir = Path(sys.argv[3])
    transcript_path = Path(sys.argv[4])

    for path in (video_path, moments_path, transcript_path):
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

    with open(moments_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    moments = data.get("moments", [])

    if not moments:
        print("No moments found.")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    print("Creating clips with synchronized captions.")
    print(f"Moments found: {len(moments)}")

    created = 0

    for index, moment in enumerate(moments, start=1):
        start = float(moment["start"])
        end = float(moment["end"])

        if end <= start:
            print(f"Skipping invalid moment {index}")
            continue

        output_path = output_dir / f"clip_{index:02d}.mp4"

        print(f"Creating clip {index}: {start:.2f}s–{end:.2f}s")

        make_clip(
            video_path,
            start,
            end,
            output_path,
            transcript_path,
        )

        created += 1

    print("========================================")
    print("CLIP CREATION COMPLETE")
    print(f"Created: {created}")
    print(f"Output directory: {output_dir}")
    print("========================================")


if __name__ == "__main__":
    main()
