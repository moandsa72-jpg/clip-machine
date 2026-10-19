import json
import re
import sys
from pathlib import Path


PROFILES = {
    "podcast": {
        "style": "podcast",
        "face_zoom": True,
        "speaker_focus": True,
    },
    "talking_head": {
        "style": "talking_head",
        "face_zoom": True,
        "speaker_focus": True,
    },
    "gaming": {
        "style": "gaming",
        "face_zoom": False,
        "speaker_focus": False,
    },
    "presentation": {
        "style": "presentation",
        "face_zoom": True,
        "speaker_focus": True,
    },
    "music": {
        "style": "music",
        "face_zoom": False,
        "speaker_focus": False,
    },
    "general": {
        "style": "general",
        "face_zoom": True,
        "speaker_focus": False,
    },
}


def load_transcript(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def get_text(transcript):
    parts = []

    for segment in transcript.get("segments", []):
        text = segment.get("text", "")
        if text:
            parts.append(text)

    return " ".join(parts).lower()


def count_matches(text, patterns):
    return sum(
        len(re.findall(pattern, text, flags=re.IGNORECASE))
        for pattern in patterns
    )


def detect_content_type(text):
    scores = {
        "podcast": 0,
        "talking_head": 0,
        "gaming": 0,
        "presentation": 0,
        "music": 0,
        "general": 0,
    }

    podcast_patterns = [
        r"\bpodcast\b",
        r"\bepisode\b",
        r"\bguest\b",
        r"\bhost\b",
        r"\binterview\b",
        r"\bconversation\b",
        r"\bwhat do you think\b",
        r"\btell me about\b",
        r"\bhow did you\b",
        r"\bwhen you\b",
        r"\byou mentioned\b",
    ]

    gaming_patterns = [
        r"\bgame\b",
        r"\bgaming\b",
        r"\bplayer\b",
        r"\bmatch\b",
        r"\bround\b",
        r"\bkill\b",
        r"\bweapon\b",
        r"\bquest\b",
        r"\blevel\b",
        r"\bboss\b",
        r"\bspawn\b",
        r"\bserver\b",
        r"\bwin\b",
        r"\bloss\b",
    ]

    presentation_patterns = [
        r"\bpresentation\b",
        r"\bslide\b",
        r"\bslides\b",
        r"\bfirst\b",
        r"\bsecond\b",
        r"\bthird\b",
        r"\bpoint\b",
        r"\bhere's how\b",
        r"\blet's look at\b",
        r"\btoday we\b",
    ]

    music_patterns = [
        r"\bsong\b",
        r"\bmusic\b",
        r"\bsinger\b",
        r"\bsinging\b",
        r"\bconcert\b",
        r"\bperformance\b",
        r"\bband\b",
        r"\bchorus\b",
        r"\bverse\b",
    ]

    talking_head_patterns = [
        r"\bi think\b",
        r"\bi believe\b",
        r"\bmy opinion\b",
        r"\bhere's the thing\b",
        r"\bthe reason is\b",
        r"\bthe biggest\b",
        r"\bthe best way\b",
        r"\byou need to\b",
        r"\byou should\b",
    ]

    scores["podcast"] += count_matches(text, podcast_patterns) * 3
    scores["gaming"] += count_matches(text, gaming_patterns) * 2
    scores["presentation"] += count_matches(text, presentation_patterns) * 2
    scores["music"] += count_matches(text, music_patterns) * 3
    scores["talking_head"] += count_matches(text, talking_head_patterns)

    # Strong conversational evidence.
    question_count = len(re.findall(r"\?", text))
    scores["podcast"] += min(question_count, 10)

    best_type = max(scores, key=scores.get)

    if scores[best_type] == 0:
        best_type = "general"

    return best_type, scores


def main():
    if len(sys.argv) != 3:
        print(
            "Usage: python scripts/content_detector.py "
            "<transcript.json> <output.json>"
        )
        sys.exit(1)

    transcript_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not transcript_path.exists():
        raise FileNotFoundError(
            f"Transcript not found: {transcript_path}"
        )

    transcript = load_transcript(transcript_path)
    text = get_text(transcript)

    content_type, scores = detect_content_type(text)

    result = {
        "content_type": content_type,
        "profile": PROFILES[content_type],
        "scores": scores,
    }

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
            indent=2,
            ensure_ascii=False
        )

    print(f"Content type: {content_type}")
    print(f"Scores: {scores}")


if __name__ == "__main__":
    main()
