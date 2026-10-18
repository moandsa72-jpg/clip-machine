import json
import sys
from pathlib import Path

import cv2
import mediapipe as mp


def detect_faces(video_path):
    video = cv2.VideoCapture(str(video_path))

    if not video.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = video.get(cv2.CAP_PROP_FPS)

    if not fps or fps <= 0:
        fps = 30.0

    mp_face_detection = mp.solutions.face_detection

    samples = []

    frame_number = 0

    with mp_face_detection.FaceDetection(
        model_selection=1,
        min_detection_confidence=0.5,
    ) as detector:

        while True:
            success, frame = video.read()

            if not success:
                break

            frame_number += 1

            if frame_number % 10 != 0:
                continue

            rgb = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB
            )

            results = detector.process(rgb)

            frame_faces = []

            if results.detections:
                frame_height, frame_width = frame.shape[:2]

                for detection in results.detections:
                    box = detection.location_data.relative_bounding_box

                    x = max(
                        0,
                        int(box.xmin * frame_width)
                    )

                    y = max(
                        0,
                        int(box.ymin * frame_height)
                    )

                    width = int(
                        box.width * frame_width
                    )

                    height = int(
                        box.height * frame_height
                    )

                    frame_faces.append(
                        {
                            "x": x,
                            "y": y,
                            "width": width,
                            "height": height,
                        }
                    )

            samples.append(
                {
                    "time": round(
                        frame_number / fps,
                        3
                    ),
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
        exist_ok=True
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            result,
            file,
            indent=2
        )

    print(
        f"Face tracking complete: "
        f"{len(result['samples'])} samples"
    )


if __name__ == "__main__":
    main()
