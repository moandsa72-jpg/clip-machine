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

    # ---------------------------------------------------------
    # VERTICAL OUTPUT
    # ---------------------------------------------------------
    #
    # The source remains clear and visible.
    #
    # Instead of black space around a landscape source,
    # create a blurred copy of the same video underneath it.
    #
    # This gives us a clean 1080x1920 vertical canvas while
    # keeping the original video undistorted.
    #
    # ---------------------------------------------------------

    video_filter = (
        "[0:v]"
        "split=2[bg][fg];"

        # Background:
        # Fill the entire 1080x1920 canvas, then blur it.
        "[bg]"
        "scale=270:480:force_original_aspect_ratio=increase,"
        "crop=270:480,"
        "boxblur=6:3,"
        "scale=1080:1920"
        "[bgblur];"

        # Foreground:
        # Keep the complete landscape frame visible.
        "[fg]"
        "scale=1080:-2"
        "[fgfit];"

        # Put the clear video over the blurred background.
        "[bgblur][fgfit]"
        "overlay=(W-w)/2:(H-h)/2,"
        "setsar=1"
        "[base]"
    )

    input_args = [
        "-i",
        str(video_path),
    ]

    # ---------------------------------------------------------
    # REBEL AUDIO LOGO
    # ---------------------------------------------------------

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
        "-nostdin",
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
    if len(sys.argv) not in (5, 6, 7):
        print(
            "Usage: python scripts/make_clips.py "
            "<video> <moments.json> <output_dir> "
            "<transcript.json> [logo.png] [content_type.json]"
        )
        sys.exit(1)

    video_path = Path(sys.argv[1])
    moments_path = Path(sys.argv[2])
    output_dir = Path(sys.argv[3])
    transcript_path = Path(sys.argv[4])

    logo_path = None
    content_type_path = None

    if len(sys.argv) == 6:
    # Sixth argument can be either a logo or content profile.
    argument_path = Path(sys.argv[5])

    if argument_path.suffix.lower() == ".json":
        content_type_path = argument_path

        if not content_type_path.exists():
            raise FileNotFoundError(
                f"Content type file not found: {content_type_path}"
            )
    else:
        logo_path = argument_path

        if not logo_path.exists():
            raise FileNotFoundError(
                f"Logo file not found: {logo_path}"
            )

elif len(sys.argv) == 7:
    # Sixth argument is the logo.
    # Seventh argument is the content profile.
    logo_path = Path(sys.argv[5])
    content_type_path = Path(sys.argv[6])

    if not logo_path.exists():
        raise FileNotFoundError(
            f"Logo file not found: {logo_path}"
        )

    if not content_type_path.exists():
        raise FileNotFoundError(
            f"Content type file not found: {content_type_path}"
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

    if content_type_path:
        with open(
            content_type_path,
            "r",
            encoding="utf-8"
        ) as file:
            content_type = json.load(file)

        print(
            f"Content type: "
            f"{content_type.get('content_type', 'general')}"
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
    print("Background: blurred source video")
    print("Foreground: clear source video")

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
