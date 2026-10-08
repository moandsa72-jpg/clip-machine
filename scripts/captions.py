import json
import re
import sys
from pathlib import Path


def escape_filter_path(path):
    path = str(Path(path).resolve())
    path = path.replace("\\", "\\\\")
    path = path.replace(":", "\\:")
    path = path.replace("'", "\\'")
    path = path.replace(",", "\\,")
    path = path.replace("[", "\")
    path = path.replace("]", "\")
    return path


def group_words(words, max_words=4):
    groups = []
    current = []

    for item in words:
        word = item.get("word", "").strip()

        if not word:
            continue

        current.append(item)

        # Keep captions short and readable.
        ends_sentence = bool(
            re.search(r"[.!?][\"']?$", word)
        )

        if len(current) >= max_words or ends_sentence:
            groups.append(current)
            current = []

    if current:
        groups.append(current)

    return groups


def create_ass(transcript_path, start, end, output_path):
    with open(transcript_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    words = []

    for segment in data.get("segments", []):
        for word in segment.get("words", []):
            word_start = float(word["start"])
            word_end = float(word["end"])

            if word_end <= start or word_start >= end:
                continue

            words.append({
                "word": word["word"],
                "start": max(word_start, start) - start,
                "end": min(word_end, end) - start
            })

    if not words:
        raise ValueError(
            "No word timestamps found for this clip."
        )

    groups = group_words(words, max_words=4)

    header = """[Script Info]
Title: Clip Machine Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,62,&H00FFFFFF,&H0000FFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,80,80,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def ass_time(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        whole_seconds = int(seconds % 60)
        centiseconds = int(
            round((seconds - int(seconds)) * 100)
        )

        if centiseconds >= 100:
            whole_seconds += 1
            centiseconds = 0

        if whole_seconds >= 60:
            minutes += 1
            whole_seconds = 0

        if minutes >= 60:
            hours += 1
            minutes = 0

        return (
            f"{hours}:{minutes:02d}:"
            f"{whole_seconds:02d}.{centiseconds:02d}"
        )

    events = []

    for group in groups:
        first = group[0]
        last = group[-1]

        phrase = " ".join(
            item["word"].strip()
            for item in group
        )

        # Escape characters used by ASS subtitles.
        phrase = phrase.replace("\\", "\\\\")
        phrase = phrase.replace("{", "\\{")
        phrase = phrase.replace("}", "\\}")

        # Highlight the phrase in yellow.
        phrase = (
            r"{\c&H0000FFFF&}"
            + phrase
            + r"{\c&H00FFFFFF&}"
        )

        event = (
            "Dialogue: 0,"
            + ass_time(first["start"])
            + ","
            + ass_time(max(last["end"], first["start"] + 0.08))
            + ",Default,,0,0,0,,"
            + phrase
        )

        events.append(event)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(output_path, "w", encoding="utf-8-sig") as file:
        file.write(header)
        file.write("\n".join(events))
        file.write("\n")

    print(f"Created captions: {output_path}")
    print(f"Caption phrases: {len(events)}")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(
            "Usage: python scripts/captions.py "
            "<transcript.json> <clip_start> "
            "<clip_end> <output.ass>"
        )
        sys.exit(1)

    create_ass(
        Path(sys.argv[1]),
        float(sys.argv[2]),
        float(sys.argv[3]),
        Path(sys.argv[4])
