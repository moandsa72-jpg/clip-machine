import json
import re
import sys
from pathlib import Path


MIN_DURATION = 12
MAX_DURATION = 30
MAX_MOMENTS = 10


HOOK_WORDS = {
    "secret", "mistake", "truth", "crazy", "actually",
    "never", "always", "best", "worst", "why",
    "how", "important", "problem", "difference",
    "real", "learn", "discovered", "imagine",
    "simple", "easy", "hard", "wrong", "right",
    "first", "finally", "because"
}


def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()


def score_text(text):
    """
    Give a transcript section a simple quality score.

    This is deliberately deterministic:
    no fake engagement, no invented dialogue,
    and no AI rewriting of the source material.
    """

    text_lower = text.lower()
    words = re.findall(r"\b[\w']+\b", text_lower)

    if not words:
        return 0

    score = 0

    # Strong opening / hook language
    for word in HOOK_WORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", text_lower):
            score += 2

    # Questions often create useful short-form openings
    if "?" in text:
        score += 3

    # Numbers can make a clip more concrete
    if re.search(r"\b\d+(?:\.\d+)?\b", text):
        score += 2

    # Longer useful sentences
    if len(words) >= 20:
        score += 2

    if len(words) >= 35:
        score += 2

    # Avoid extremely short fragments
    if len(words) < 8:
        score -= 3

    # Avoid excessive repetition
    unique_ratio = len(set(words)) / max(len(words), 1)

    if unique_ratio > 0.55:
        score += 2

    return score


def build_windows(segments):
    windows = []

    for i, start_segment in enumerate(segments):
        start = float(start_segment["start"])
        text_parts = []

        for j in range(i, len(segments)):
            end = float(segments[j]["end"])
            duration = end - start

            if duration > MAX_DURATION:
                break

            text_parts.append(clean_text(segments[j]["text"]))

            if duration >= MIN_DURATION:
                text = clean_text(" ".join(text_parts))

                if text:
                    score = score_text(text)

                    windows.append({
                        "start": round(start, 3),
                        "end": round(end, 3),
                        "duration": round(duration, 3),
                        "score": score,
                        "text": text
                    })

    return windows


def remove_overlaps(windows):
    selected = []

    # Highest scoring candidates first
    windows = sorted(
        windows,
        key=lambda x: (
            x["score"],
            -abs(x["duration"] - 20)
        ),
        reverse=True
    )

    for candidate in windows:
        overlaps = False

        for existing in selected:
            latest_start = max(
                candidate["start"],
                existing["start"]
            )

            earliest_end = min(
                candidate["end"],
                existing["end"]
            )

            overlap = max(
                0,
                earliest_end - latest_start
            )

            shorter_duration = min(
                candidate["duration"],
                existing["duration"]
            )

            if shorter_duration > 0:
                overlap_ratio = overlap / shorter_duration

                if overlap_ratio > 0.50:
                    overlaps = True
                    break

        if not overlaps:
            selected.append(candidate)

        if len(selected) >= MAX_MOMENTS:
            break

    return sorted(
        selected,
        key=lambda x: x["start"]
    )


def find_moments(input_path, output_path):
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(
            f"Transcript not found: {input_path}"
        )

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data.get("segments", [])

    if not segments:
        raise ValueError(
            "Transcript contains no segments."
        )

    windows = build_windows(segments)

    moments = remove_overlaps(windows)

    result = {
        "source": str(input_path),
        "minimum_duration": MIN_DURATION,
        "maximum_duration": MAX_DURATION,
        "moments": moments
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()
    print("========================================")
    print("MOMENT DETECTION COMPLETE")
    print("========================================")
    print(f"Candidates found: {len(moments)}")
    print()

    for number, moment in enumerate(moments, 1):
        print(
            f"{number}. "
            f"{moment['start']:.2f}s → "
            f"{moment['end']:.2f}s "
            f"({moment['duration']:.1f}s) "
            f"score={moment['score']}"
        )

        print(f"   {moment['text'][:180]}")
        print()

    print(f"Output: {output_path}")
    print("========================================")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python scripts/find_moments.py "
            "<transcript.json> <moments.json>"
        )
        sys.exit(1)

    find_moments(
        sys.argv[1],
        sys.argv[2]
              )
