import json
import sys
from pathlib import Path

from faster_whisper import WhisperModel


def transcribe_video(video_path, output_path):
    video_path = Path(video_path)
    output_path = Path(output_path)

    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    print(f"Loading Whisper model...")
    
    model = WhisperModel(
        "tiny",
        device="cpu",
        compute_type="int8"
    )

    print(f"Transcribing: {video_path}")

    segments, info = model.transcribe(
        str(video_path),
        beam_size=5,
        vad_filter=True,
        word_timestamps=True
    )

    transcript_segments = []

    for segment in segments:
        words = []

        if segment.words:
            for word in segment.words:
                words.append({
                    "word": word.word,
                    "start": round(word.start, 3),
                    "end": round(word.end, 3)
                })

        transcript_segments.append({
            "start": round(segment.start, 3),
            "end": round(segment.end, 3),
            "text": segment.text.strip(),
            "words": words
        })

    result = {
        "language": info.language,
        "language_probability": round(info.language_probability, 4),
        "duration": round(info.duration, 3),
        "segments": transcript_segments
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print()
    print("========================================")
    print("TRANSCRIPTION COMPLETE")
    print("========================================")
    print(f"Language: {info.language}")
    print(f"Duration: {info.duration:.2f} seconds")
    print(f"Segments: {len(transcript_segments)}")
    print(f"Output: {output_path}")
    print("========================================")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python scripts/transcribe.py "
            "<video> <output.json>"
        )
        sys.exit(1)

    transcribe_video(
        sys.argv[1],
        sys.argv[2]
  )
