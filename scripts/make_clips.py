import json
import subprocess
import sys
from pathlib import Path


def run_command(command):
    print("Running:", " ".join(str(x) for x in command))
    subprocess.run(command, check=True)


def get_video_dimensions(video_path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    value = result.stdout.strip()

    if "x" not in value:
        raise RuntimeError(
            f"Could not determine video dimensions: {value}"
        )

    width, height = value.split("x", 1)

    return int(width), int(height)


def make_clip(
    video_path,
    start,
    end,
    output_path,
    transcript_path,
    logo_path=None,
):
    duration = end - start

    output_path.parent.mkdir(parents=True, exist_ok=True)

    subtitle_path = output_path.with_suffix(".ass")

    run_command([
        sys.executable,
        "scripts/captions.py",
        str(transcript_path),
        str(start),
        str(end),
        str(subtitle_path),
    ])

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

    width, height = get_video_dimensions(video_path)

    aspect_ratio = width / height

    print(
        f"Source dimensions: {width}x{height} "
        f"(aspect ratio: {aspect_ratio:.3f})"
    )

    # A 9:16 source should fill the entire 1080x1920 canvas.
    is_vertical = abs(aspect_ratio - (9 / 16)) < 0.08

    if is_vertical:
        print("Vertical source detected.")
        print("Using full-frame 1080x1920 layout.")

        video_filter = (
            "[0:v]"
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
            "setsar=1"
            "[base]"
        )

    else:
        print("Non-vertical source detected.")
        print("Using blurred-background vertical layout.")

        video_filter = (
            "[0:v]split=2[bg][fg];"
            "[bg]"
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "boxblur=10:5"
            "[bgblur];"
            "[fg]"
            "scale=-1:1400"
            "[fgfit];"
            "[bgblur][fgfit]"
            "overlay=(W-w)/2:(H-h)/2,"
            "setsar=1"
            "[base]"
        )

    input_args = [
        "-i",
        str(video_path),
    ]

    if logo_path is not None:
        logo_path = Path(logo_path)

        if not logo_path.is_file():
            raise FileNotFoundError(
                f"Logo file not found: {logo_path}"
            )

        video_filter += (
            ";[1:v]"
            "scale=420:-1"
            "[logo];"
            "[base][logo]"
            "overlay=(W-w)/2:70"
            "[branded];"
            f"[branded]"
            f"subtitles='{subtitle_filter_path}'"
            "[outv]"
        )

        input_args = [
            "-i",
            str(video_path),
            "-loop",
            "1",
            "-i",
            str(logo_path),
        ]

    else:
        video_filter += (
            ";[base]"
            f"subtitles='{subtitle_filter_path}'"
            "[outv]"
        )

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start),
        *input_args,
        "-t",
        str(duration),
        "-filter_complex",
        video_filter,
        "-map",
        "[outv]",
        "-map",
        "0:a?",
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

    if subtitle_path.exists():
        subtitle_path.unlink()


def main():
    if len(sys.argv) not in (5, 6):
        print(
            "Usage: python scripts/make_clips.py "
            "<video> <moments.json> <output_dir> "
            "<transcript.json> [logo.png]"
        )
        sys.exit(1)

    video_path = Path(sys.argv[1])
    moments_path = Path(sys.argv[2])
    output_dir = Path(sys.argv[3])
    transcript_path = Path(sys.argv[4])

    logo_path = None

    if len(sys.argv) == 6:
        logo_path = Path(sys.argv[5])

        if not logo_path.exists():
            raise FileNotFoundError(
                f"Logo file not found: {logo_path}"
            )

    for path in (
        video_path,
        moments_path,
        transcript_path,
    ):
        if not path.exists():
            raise FileNotFoundError(
                f"File not found: {path}"
            )

    with open(moments_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    moments = data.get("moments", [])

    if not moments:
        print("No moments found.")
        sys.exit(1)

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    print("Creating clips with synchronized captions.")
    print("Vertical output: 1080x1920")

    if logo_path:
        print(f"Campaign logo: {logo_path}")
    else:
        print("Campaign logo: none")

    print(f"Moments found: {len(moments)}")

    created = 0

    for index, moment in enumerate(moments, start=1):
        start = float(moment["start"])
        end = float(moment["end"])

        if end <= start:
            print(
                f"Skipping invalid moment {index}"
            )
            continue

        output_path = (
            output_dir / f"clip_{index:02d}.mp4"
        )

        print(
            f"Creating clip {index}: "
            f"{start:.2f}s–{end:.2f}s"
        )

        make_clip(
            video_path,
            start,
            end,
            output_path,
            transcript_path,
            logo_path,
        )

        created += 1

    print("========================================")
    print("CLIP CREATION COMPLETE")
    print(f"Created: {created}")
    print(f"Output directory: {output_dir}")
    print("========================================")


if __name__ == "__main__":
    main()
