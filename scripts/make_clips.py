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
        raise RuntimeError(f"Could not determine video dimensions: {value}")
    width, height = value.split("x", 1)
    return int(width), int(height)


def load_face_data(path):
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def choose_face_center(face_data, start, end, width, height):
    if not face_data:
        return width / 2

    centers = []
    for sample in face_data.get("samples", []):
        time = float(sample.get("time", -1))
        if time < start or time > end:
            continue
        for face in sample.get("faces", []):
            x = float(face.get("x", 0))
            w = float(face.get("width", 0))
            if w > 0:
                centers.append(x + w / 2)

    if not centers:
        return width / 2

    # Median center is robust against one-off false detections.
    centers.sort()
    return centers[len(centers) // 2]


def make_clip(video_path, start, end, output_path, transcript_path, logo_path=None, face_data=None):
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
        subtitle_filter_path.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )

    width, height = get_video_dimensions(video_path)
    center_x = choose_face_center(face_data, start, end, width, height)

    # Target 9:16. For wide source video, crop around the detected face center.
    crop_width = min(width, int(height * 9 / 16))
    crop_x = max(0, min(width - crop_width, int(center_x - crop_width / 2)))

    print(f"Source dimensions: {width}x{height}")
    print(f"Face-aware crop: x={crop_x}, width={crop_width}")

    video_filter = (
        f"[0:v]crop={crop_width}:{height}:{crop_x}:0,"
        "split=2[bg][fg];"
        "[bg]scale=270:480:force_original_aspect_ratio=increase,"
        "crop=270:480,boxblur=6:3,scale=1080:1920[bgblur];"
        "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fgfit];"
        "[bgblur][fgfit]overlay=(W-w)/2:(H-h)/2,setsar=1[base]"
    )

    input_args = ["-i", str(video_path)]

    if logo_path is not None:
        logo_path = Path(logo_path)
        if not logo_path.is_file():
            raise FileNotFoundError(f"Logo file not found: {logo_path}")
        video_filter += (
            ";[1:v]scale=420:-1[logo];"
            "[base][logo]overlay=(W-w)/2:70[branded];"
            f"[branded]subtitles='{subtitle_filter_path}'[outv]"
        )
        input_args = ["-i", str(video_path), "-loop", "1", "-i", str(logo_path)]
    else:
        video_filter += f";[base]subtitles='{subtitle_filter_path}'[outv]"

    command = [
        "ffmpeg", "-y", "-nostdin", "-ss", str(start),
        *input_args, "-t", str(duration),
        "-filter_complex", video_filter,
        "-map", "[outv]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        str(output_path),
    ]

    run_command(command)
    if subtitle_path.exists():
        subtitle_path.unlink()


def main():
    if len(sys.argv) not in (5, 6, 7, 8):
        print(
            "Usage: python scripts/make_clips.py <video> <moments.json> "
            "<output_dir> <transcript.json> [logo.png] [content_type.json] [faces.json]"
        )
        sys.exit(1)

    video_path = Path(sys.argv[1])
    moments_path = Path(sys.argv[2])
    output_dir = Path(sys.argv[3])
    transcript_path = Path(sys.argv[4])
    logo_path = None
    content_type_path = None
    face_path = None

    for argument in sys.argv[5:]:
        path = Path(argument)
        if path.suffix.lower() == ".json":
            if "face" in path.name.lower():
                face_path = path
            else:
                content_type_path = path
        else:
            logo_path = path

    for path in (video_path, moments_path, transcript_path):
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

    if logo_path and not logo_path.exists():
        raise FileNotFoundError(f"Logo file not found: {logo_path}")
    if content_type_path and not content_type_path.exists():
        raise FileNotFoundError(f"Content type file not found: {content_type_path}")
    if face_path and not face_path.exists():
        raise FileNotFoundError(f"Face data file not found: {face_path}")

    with open(moments_path, "r", encoding="utf-8") as file:
        moments = json.load(file).get("moments", [])

    if not moments:
        print("No moments found.")
        sys.exit(1)

    content_type = None
    if content_type_path:
        content_type = json.loads(content_type_path.read_text(encoding="utf-8"))
        print(f"Content type: {content_type.get('content_type', 'general')}")

    face_data = load_face_data(face_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Creating fully automated vertical clips.")
    print("Output: 1080x1920")
    print("Face-aware framing: enabled" if face_data else "Face-aware framing: disabled")
    print(f"Campaign logo: {logo_path or 'none'}")

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
            video_path, start, end, output_path, transcript_path,
            logo_path, face_data,
        )
        created += 1

    print("========================================")
    print("CLIP CREATION COMPLETE")
    print(f"Created: {created}")
    print(f"Output directory: {output_dir}")
    print("========================================")


if __name__ == "__main__":
    main()
