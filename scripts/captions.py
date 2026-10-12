import json
import sys
from pathlib import Path


def ass_time(seconds):
    total_cs = max(0, round(seconds * 100))

    hours = total_cs // 360000
    minutes = (total_cs % 360000) // 6000
    secs = (total_cs % 6000) // 100
    centiseconds = total_cs % 100

    return (
        f"{hours}:{minutes:02d}:"
        f"{secs:02d}.{centiseconds:02d}"
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

            word = item.get("word", "").strip()

            if not word:
                continue

            words.append({
                "word": word,
                "start": max(word_start, clip_start) - clip_start,
                "end": min(word_end, clip_end) - clip_start,
            })

    words.sort(key=lambda item: item["start"])

    if not words:
        raise ValueError(
            "No word timestamps found for this clip. "
            "Check work/transcript.json."
        )

    # Short readable caption groups.
    groups = []
    current = []

    for item in words:
        current.append(item)

        sentence_end = item["word"].endswith((".", "!", "?"))
        group_full = len(current) >= 4

        if sentence_end or group_full:
            groups.append(current)
            current = []

    if current:
        groups.append(current)

    header = """[Script Info]
Title: Clip Machine Precise Animated Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,72,&H00FFFFFF,&H0000FFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,80,80,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []

    for group in groups:
        group_start = group[0]["start"]

        group_end = max(
            group[-1]["end"],
            group_start + 0.12
        )

        for index, item in enumerate(group):
            word_start = item["start"]

            if index + 1 < len(group):
                next_word_start = group[index + 1]["start"]

                event_end = max(
                    next_word_start,
                    word_start + 0.06
                )
            else:
                event_end = group_end

            event_end = min(event_end, group_end)

            if event_end <= word_start:
                event_end = word_start + 0.08

            parts = []

            for other_index, other in enumerate(group):
                text = escape_text(other["word"])

                if other_index == index:
                    text = (
                        r"{\c&H0000FFFF&"
                        r"\fscx112\fscy112"
                        r"\t(0,100,\fscx100\fscy100)}"
                        + text
                        + r"{\c&H00FFFFFF&"
                        r"\fscx100\fscy100}"
                    )

                parts.append(text)

            phrase = " ".join(parts)

            events.append(
                "Dialogue: 0,"
                + ass_time(word_start)
                + ","
                + ass_time(event_end)
                + ",Default,,0,0,0,,"
                + phrase
            )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8-sig") as file:
        file.write(header)
        file.write("\n".join(events))
        file.write("\n")

    print("PRECISE WORD-SYNC CAPTIONS CREATED")
    print(f"Words: {len(words)}")
    print(f"Caption groups: {len(groups)}")
    print(f"Caption events: {len(events)}")
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
