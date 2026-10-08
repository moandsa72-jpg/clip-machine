import json
import sys
from pathlib import Path


def ass_time(seconds):
    total_cs = round(seconds * 100)
    hours = total_cs // 360000
    minutes = (total_cs % 360000) // 6000
    seconds_part = (total_cs % 6000) // 100
    centiseconds = total_cs % 100

    return (
        f"{hours}:{minutes:02d}:"
        f"{seconds_part:02d}.{centiseconds:02d}"
    )


def escape_text(text):
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", " ")
        .strip()
    )


def create_ass(transcript_path, clip_start, clip_end, output_path):
    with open(transcript_path, "r", encoding="utf-8") as file:
        transcript = json.load(file)

    words = []

    for segment in transcript.get("segments", []):
        for item in segment.get("words", []):
            word_start = float(item["start"])
            word_end = float(item["end"])

            if word_end <= clip_start or word_start >= clip_end:
                continue

            words.append({
                "word": item["word"].strip(),
                "start": max(word_start, clip_start) - clip_start,
                "end": min(word_end, clip_end) - clip_start,
            })

    if not words:
        raise ValueError(
            "No word timestamps found for this clip. "
            "Check that transcript.json contains word timestamps."
        )

    # Group words into short, readable caption phrases.
    groups = []
    current = []

    for item in words:
        if not item["word"]:
            continue

        current.append(item)

        word = item["word"]
        sentence_end = word.endswith((".", "!", "?"))

        if len(current) >= 4 or sentence_end:
            groups.append(current)
            current = []

    if current:
        groups.append(current)

    header = """[Script Info]
Title: Clip Machine Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,62,&H00FFFFFF,&H0000FFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,80,80,360,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []

    for group in groups:
        start = group[0]["start"]
        end = group[-1]["end"]

        if end <= start:
            end = start + 0.08

        phrase = " ".join(
            escape_text(item["word"])
            for item in group
        )

        # Highlight the caption phrase in yellow.
        phrase = (
            r"{\c&H0000FFFF&}"
            + phrase
            + r"{\c&H00FFFFFF&}"
        )

        events.append(
            "Dialogue: 0,"
            + ass_time(start)
            + ","
            + ass_time(end)
            + ",Default,,0,0,0,,"
            + phrase
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8-sig") as file:
        file.write(header)
        file.write("\n".join(events))
        file.write("\n")

    print("CAPTIONS CREATED")
    print(f"Words: {len(words)}")
    print(f"Caption phrases: {len(events)}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(
            "Usage: python scripts/captions.py "
            "<transcript.json> <clip_start> "
            "<clip_end> <output.ass>"
        )
        sys.exit(1)

    create_ass(
        sys.argv[1],
        float(sys.argv[2]),
        float(sys.argv[3]),
        sys.argv[4],
    )
