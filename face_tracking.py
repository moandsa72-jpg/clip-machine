import json
import sys
from pathlib import Path

import cv2


def detect_faces(video_path):
    video = cv2.VideoCapture(str(video_path))

    if not video.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = video.get(cv2.CAP_PROP_FPS)

    if not fps or fps <= 0:
        fps = 30.0

    detector = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    samples = []
    frame_number = 0

    while True:
        success, frame = video.read()

        if not success:
            break

        frame_number += 1

        # Analyze approximately every 10th frame.
        if frame_number % 10 != 0:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        faces = detector.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(60, 60),
        )

        frame_faces = []

        for x, y, width, height in faces:
            frame_faces.append(
                {
                    "x": int(x),
                    "y": int(y),
                    "width": int(width),
                    "height": int(height),
                }
            )

        samples.append(
            {
                "time": round(frame_number / fps, 3),
                "faces": frame_faces,
            }
        )

    video.release()

    return {
        "fps": fps,
        "samples": samples,
    }


def main():
    if len(sys.argv) != 3:
        print(
            "Usage: python scripts/face_tracking.py "
            "<video> <output.json>"
        )
        sys.exit(1)

    video_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not video_path.exists():
        raise FileNotFoundError(
            f"Video not found: {video_path}"
        )

    result = detect_faces(video_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(
            result,
            file,
            indent=2,
        )

    print(
        f"Face tracking complete: "
        f"{len(result['samples'])} samples"
    )


if __name__ == "__main__":
    main()
