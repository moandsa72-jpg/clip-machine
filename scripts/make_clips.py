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
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0",
            str(video_path),
        ], capture_output=True, text=True, check=True,
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


def face_centers(face_data, start, end, width):
    if not face_data:
        return []
    points = []
    for sample in face_data.get("samples", []):
        time = float(sample.get("time", -1))
        if time < start or time > end:
            continue
        faces = [
            face for face in sample.get("faces", [])
            if float(face.get("width", 0)) > 0
        ]
        if not faces:
            continue
        face = max(
            faces,
            key=lambda item: float(item.get("width", 0)) * float(item.get("height", 0)),
        )
        center = float(face.get("x", 0)) + float(face.get("width", 0)) / 2
        points.append((time, max(0.0, min(float(width), center))))
    points.sort(key=lambda item: item[0])
    return points


def smooth_points(points, window=3):
    if len(points) <= 2:
        return points
    result = []
    half = max(1, window // 2)
    for index, (time, _center) in enumerate(points):
        left = max(0, index - half)
        right = min(len(points), index + half + 1)
        centers = sorted(point[1] for point in points[left:right])
        result.append((time, centers[len(centers) // 2]))
    return result


def choose_face_center(face_data, start, end, width):
    points = smooth_points(face_centers(face_data, start, end, width))
    if not points:
        return width / 2
    centers = sorted(point[1] for point in points)
    return centers[len(centers) // 2]


def build_crop_x_expression(face_data, start, end, source_width, crop_width):
    max_x = max(0, source_width - crop_width)
    points = smooth_points(face_centers(face_data, start, end, source_width))
    if not points:
        center = source_width / 2
        return str(int(max(0, min(max_x, center - crop_width / 2))))

    selected = []
    last_time = None
    for time, center in points:
        if last_time is None or time - last_time >= 0.75:
            selected.append((time, center))
            last_time = time
    if selected[-1] != points[-1]:
        selected.append(points[-1])

    def crop_center(center):
        return max(0.0, min(float(max_x), center - crop_width / 2))

    selected = [(time, crop_center(center)) for time, center in selected]
    relative = [(time - start, x) for time, x in selected]
    if len(relative) == 1:
        return f"{relative[0][1]:.2f}"

    expression = f"{relative[-1][1]:.2f}"
    for index in range(len(relative) - 2, -1, -1):
        t0, x0 = relative[index]
        t1, x1 = relative[index + 1]
        span = max(0.001, t1 - t0)
        interpolation = f"({x0:.2f}+({x1 - x0:.2f})*(t-{t0:.3f})/{span:.3f})"
        expression = f"if(lt(t,{t1:.3f}),{interpolation},{expression})"

    first_time, first_x = relative[0]
    return f"if(lt(t,{first_time:.3f}),{first_x:.2f},{expression})"


def make_clip(video_path, start, end, output_path, transcript_path, logo_path=None, face_data=None):
    duration = end - start
    output_path.parent.mkdir(parents=True, exist_ok=True)

    subtitle_path = output_path.with_suffix(".ass")
    run_command([
        sys.executable, "scripts/captions.py", str(transcript_path),
        str(start), str(end), str(subtitle_path),
    ])

    subtitle_filter_path = str(subtitle_path.resolve())
    subtitle_filter_path = (
        subtitle_filter_path.replace("\\", "\\\\")
        .replace(":", "\\:").replace("'", "\\'")
        .replace(",", "\\,").replace("[", "\\[").replace("]", "\\]")
    )

    width, height = get_video_dimensions(video_path)
    crop_width = min(width, int(height * 9 / 16))
    crop_x_expression = build_crop_x_expression(face_data, start, end, width, crop_width)
    static_center = choose_face_center(face_data, start, end, width)
    print(f"Source dimensions: {width}x{height}")
    print(f"Face-aware camera center: {static_center:.1f}")
    print(f"Smooth crop expression: {crop_x_expression}")

    video_filter = (
        f"[0:v]crop={crop_width}:{height}:{crop_x_expression}:0,"
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
        "ffmpeg", "-y", "-nostdin", "-ss", str(start), *input_args,
        "-t", str(duration), "-filter_complex", video_filter,
        "-map", "[outv]", "-map", "0:a?", "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(output_path),
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

    data = json.loads(moments_path.read_text(encoding="utf-8"))
    moments = data.get("moments", []) if isinstance(data, dict) else data
    if not moments:
        print("No moments found.")
        sys.exit(1)

    content_type = {}
    if content_type_path:
        content_type = json.loads(content_type_path.read_text(encoding="utf-8"))
        print(f"Content type: {content_type.get('content_type', 'general')}")

    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    transcript_segments = transcript.get("segments", []) if isinstance(transcript, dict) else []
    face_data = load_face_data(face_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    print("Creating fully automated vertical clips.")
    print("Output: 1080x1920")
    print("Face-aware smooth framing: enabled" if face_data else "Face-aware framing: disabled")
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
        make_clip(video_path, start, end, output_path, transcript_path, logo_path, face_data)

        source_text = " ".join(
            str(segment.get("text", "")).strip()
            for segment in transcript_segments
            if float(segment.get("end", 0)) > start and float(segment.get("start", 0)) < end
        ).strip()
        metadata = {
            "filename": output_path.name,
            "source_video": str(video_path),
            "start": round(start, 3),
            "end": round(end, 3),
            "duration_seconds": round(end - start, 3),
            "text": source_text[:2000],
            "hook_text": moment.get("hook_text", source_text[:240]),
            "hook_score": moment.get("hook_score", 0),
            "hook_optimized": bool(moment.get("hook_optimized", False)),
            "edge_silence_trimmed": bool(moment.get("edge_silence_trimmed", False)),
            "moment_score": moment.get("score", 0),
            "fallback": bool(moment.get("fallback", False)),
            "content_type": content_type.get("content_type", "general"),
        }
        output_path.with_suffix(".json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        created += 1

    print("========================================")
    print("CLIP CREATION COMPLETE")
    print(f"Created: {created}")
    print(f"Output directory: {output_dir}")
    print("========================================")


if __name__ == "__main__":
    main()
