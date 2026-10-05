import json
import re
import sys
from pathlib import Path


# ============================================================
# VIRAL SHORT-FORM MOMENT ANALYZER
# ============================================================
#
# This script does NOT invent dialogue.
# It only analyzes the original transcript and identifies
# promising sections for short-form editing.
#
# The goal is to prioritize:
# - strong hooks
# - curiosity
# - conflict
# - surprise
# - useful information
# - numbers
# - questions
# - conversational language
# - good short-form duration
# - strong endings
#
# Final "viral" performance can never be guaranteed.
#


MIN_DURATION = 10
IDEAL_MIN_DURATION = 15
IDEAL_MAX_DURATION = 27
MAX_DURATION = 35

MAX_MOMENTS = 12


# ============================================================
# HOOK / RETENTION VOCABULARY
# ============================================================

HOOK_WORDS = {
    "secret",
    "mistake",
    "truth",
    "crazy",
    "actually",
    "never",
    "always",
    "best",
    "worst",
    "why",
    "how",
    "important",
    "problem",
    "difference",
    "real",
    "learn",
    "learned",
    "discovered",
    "imagine",
    "simple",
    "easy",
    "hard",
    "wrong",
    "right",
    "first",
    "finally",
    "because",
    "nobody",
    "everyone",
    "someone",
    "nothing",
    "everything",
    "really",
    "seriously",
    "literally",
    "apparently",
    "turns",
    "turned",
    "happened",
    "happens",
    "dangerous",
    "weird",
    "insane",
    "shocking",
    "surprising",
    "unexpected",
}


CURIOSITY_WORDS = {
    "why",
    "how",
    "secret",
    "reason",
    "actually",
    "truth",
    "discovered",
    "revealed",
    "happened",
    "happens",
    "difference",
    "problem",
    "because",
    "before",
    "after",
    "until",
    "instead",
    "without",
    "unless",
    "never",
}


STRONG_WORDS = {
    "must",
    "need",
    "important",
    "wrong",
    "right",
    "never",
    "always",
    "best",
    "worst",
    "dangerous",
    "impossible",
    "possible",
    "critical",
    "massive",
    "huge",
    "crazy",
    "insane",
    "shocking",
    "secret",
    "truth",
}


WEAK_START_WORDS = {
    "so",
    "well",
    "okay",
    "alright",
    "basically",
    "um",
    "uh",
    "yeah",
    "like",
}


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()


def get_words(text):
    return re.findall(r"\b[\w']+\b", text.lower())


def contains_word(text, word):
    return re.search(
        r"\b" + re.escape(word) + r"\b",
        text.lower()
    ) is not None


def count_words(text, vocabulary):
    words = get_words(text)

    return sum(
        1 for word in words
        if word in vocabulary
    )


def count_numbers(text):
    return len(
        re.findall(
            r"\b\d+(?:[.,]\d+)?%?\b",
            text
        )
    )


def question_count(text):
    return text.count("?")


def exclamation_count(text):
    return text.count("!")


# ============================================================
# SCORE ONE CANDIDATE
# ============================================================

def score_candidate(text, duration):

    words = get_words(text)

    if not words:
        return {
            "score": 0,
            "hook_score": 0,
            "curiosity_score": 0,
            "information_score": 0,
            "specificity_score": 0,
            "conversation_score": 0,
            "duration_score": 0,
            "penalty": 0,
        }

    score = 0

    hook_score = 0
    curiosity_score = 0
    information_score = 0
    specificity_score = 0
    conversation_score = 0
    duration_score = 0

    penalty = 0

    text_lower = text.lower()


    # --------------------------------------------------------
    # HOOK LANGUAGE
    # --------------------------------------------------------

    hook_hits = count_words(
        text_lower,
        HOOK_WORDS
    )

    hook_score += min(hook_hits * 2, 14)


    # --------------------------------------------------------
    # CURIOSITY
    # --------------------------------------------------------

    curiosity_hits = count_words(
        text_lower,
        CURIOSITY_WORDS
    )

    curiosity_score += min(
        curiosity_hits * 2,
        12
    )


    # --------------------------------------------------------
    # STRONG LANGUAGE
    # --------------------------------------------------------

    strong_hits = count_words(
        text_lower,
        STRONG_WORDS
    )

    hook_score += min(
        strong_hits * 1.5,
        9
    )


    # --------------------------------------------------------
    # QUESTIONS
    # --------------------------------------------------------

    questions = question_count(text)

    if questions:
        curiosity_score += min(
            questions * 4,
            8
        )


    # --------------------------------------------------------
    # NUMBERS / SPECIFIC INFORMATION
    # --------------------------------------------------------

    numbers = count_numbers(text)

    if numbers:
        specificity_score += min(
            numbers * 3,
            9
        )


    # --------------------------------------------------------
    # INFORMATION DENSITY
    # --------------------------------------------------------

    word_count = len(words)

    if word_count >= 20:
        information_score += 3

    if word_count >= 35:
        information_score += 3

    if word_count >= 50:
        information_score += 2


    # --------------------------------------------------------
    # CONVERSATIONAL SIGNALS
    # --------------------------------------------------------

    conversational_words = {
        "you",
        "your",
        "we",
        "us",
        "I",
        "me",
        "they",
        "them",
    }

    conversation_hits = sum(
        1 for word in words
        if word in conversational_words
    )

    if conversation_hits >= 2:
        conversation_score += 3

    if conversation_hits >= 5:
        conversation_score += 2


    # --------------------------------------------------------
    # DURATION
    # --------------------------------------------------------

    if IDEAL_MIN_DURATION <= duration <= IDEAL_MAX_DURATION:
        duration_score += 8

    elif MIN_DURATION <= duration < IDEAL_MIN_DURATION:
        duration_score += 3

    elif IDEAL_MAX_DURATION < duration <= MAX_DURATION:
        duration_score += 4

    else:
        duration_score -= 2


    # --------------------------------------------------------
    # WEAK BEGINNING
    # --------------------------------------------------------

    first_words = words[:3]

    if first_words:
        if first_words[0] in WEAK_START_WORDS:
            penalty += 3


    # --------------------------------------------------------
    # REPETITION
    # --------------------------------------------------------

    unique_ratio = len(set(words)) / max(
        len(words),
        1
    )

    if unique_ratio < 0.40:
        penalty += 5

    elif unique_ratio < 0.50:
        penalty += 2


    # --------------------------------------------------------
    # EXCESSIVE FILLER
    # --------------------------------------------------------

    filler_words = {
        "um",
        "uh",
        "like",
        "youknow",
        "basically",
        "actually",
        "sort",
        "kind",
    }

    filler_hits = sum(
        1 for word in words
        if word in filler_words
    )

    if len(words) >= 15:

        filler_ratio = filler_hits / len(words)

        if filler_ratio > 0.12:
            penalty += 4

        elif filler_ratio > 0.08:
            penalty += 2


    # --------------------------------------------------------
    # EXCLAMATION / ENERGY
    # --------------------------------------------------------

    if exclamation_count(text) > 0:
        hook_score += 2


    # --------------------------------------------------------
    # FINAL SCORE
    # --------------------------------------------------------

    score = (
        hook_score
        + curiosity_score
        + information_score
        + specificity_score
        + conversation_score
        + duration_score
        - penalty
    )

    return {
        "score": round(score, 2),
        "hook_score": round(hook_score, 2),
        "curiosity_score": round(curiosity_score, 2),
        "information_score": round(information_score, 2),
        "specificity_score": round(specificity_score, 2),
        "conversation_score": round(conversation_score, 2),
        "duration_score": round(duration_score, 2),
        "penalty": round(penalty, 2),
    }


# ============================================================
# BUILD CANDIDATE WINDOWS
# ============================================================

def build_windows(segments):

    windows = []

    for i, start_segment in enumerate(segments):

        start = float(
            start_segment["start"]
        )

        text_parts = []

        for j in range(
            i,
            len(segments)
        ):

            end = float(
                segments[j]["end"]
            )

            duration = end - start

            if duration > MAX_DURATION:
                break

            text_parts.append(
                clean_text(
                    segments[j]["text"]
                )
            )

            if duration >= MIN_DURATION:

                text = clean_text(
                    " ".join(text_parts)
                )

                if not text:
                    continue

                scores = score_candidate(
                    text,
                    duration
                )

                windows.append({
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "duration": round(
                        duration,
                        3
                    ),
                    "text": text,
                    **scores
                })

    return windows


# ============================================================
# REMOVE OVERLAPPING CANDIDATES
# ============================================================

def overlap_ratio(a, b):

    latest_start = max(
        a["start"],
        b["start"]
    )

    earliest_end = min(
        a["end"],
        b["end"]
    )

    overlap = max(
        0,
        earliest_end - latest_start
    )

    shorter = min(
        a["duration"],
        b["duration"]
    )

    if shorter <= 0:
        return 0

    return overlap / shorter


def remove_overlaps(windows):

    selected = []

    windows = sorted(
        windows,
        key=lambda item: (
            item["score"],
            item["information_score"],
            item["curiosity_score"],
            -abs(
                item["duration"] - 20
            )
        ),
        reverse=True
    )

    for candidate in windows:

        overlaps = False

        for existing in selected:

            if overlap_ratio(
                candidate,
                existing
            ) > 0.50:

                overlaps = True
                break

        if not overlaps:
            selected.append(
                candidate
            )

        if len(selected) >= MAX_MOMENTS:
            break

    return sorted(
        selected,
        key=lambda item: item["start"]
    )


# ============================================================
# CLASSIFY MOMENT
# ============================================================

def classify_moment(moment):

    text = moment["text"].lower()

    if (
        "?" in text
        or moment["curiosity_score"] >= 8
    ):
        return "curiosity"

    if (
        moment["specificity_score"] >= 6
        and moment["information_score"] >= 4
    ):
        return "information"

    if (
        moment["hook_score"] >= 10
    ):
        return "strong_statement"

    if (
        "!" in text
        or moment["hook_score"] >= 7
    ):
        return "high_energy"

    return "story"


# ============================================================
# MAIN
# ============================================================

def find_moments(
    input_path,
    output_path
):

    input_path = Path(
        input_path
    )

    output_path = Path(
        output_path
    )

    if not input_path.exists():
        raise FileNotFoundError(
            f"Transcript not found: {input_path}"
        )

    with open(
        input_path,
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(file)

    segments = data.get(
        "segments",
        []
    )

    if not segments:
        raise ValueError(
            "Transcript contains no segments."
        )

    windows = build_windows(
        segments
    )

    moments = remove_overlaps(
        windows
    )

    for moment in moments:
        moment["type"] = classify_moment(
            moment
        )

    result = {
        "source": str(
            input_path
        ),

        "analysis": {
            "minimum_duration":
                MIN_DURATION,

            "ideal_min_duration":
                IDEAL_MIN_DURATION,

            "ideal_max_duration":
                IDEAL_MAX_DURATION,

            "maximum_duration":
                MAX_DURATION,

            "max_moments":
                MAX_MOMENTS,
        },

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
    ) as file:

        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2
        )

    print()
    print(
        "========================================"
    )
    print(
        "VIRAL MOMENT ANALYSIS COMPLETE"
    )
    print(
        "========================================"
    )

    print(
        f"Candidates selected: "
        f"{len(moments)}"
    )

    print()

    for number, moment in enumerate(
        moments,
        1
    ):

        print(
            f"#{number} "
            f"[{moment['type']}] "
            f"score={moment['score']}"
        )

        print(
            f"Time: "
            f"{moment['start']:.2f}s → "
            f"{moment['end']:.2f}s"
        )

        print(
            f"Duration: "
            f"{moment['duration']:.1f}s"
        )

        print(
            f"Hook: "
            f"{moment['hook_score']}"
        )

        print(
            f"Curiosity: "
            f"{moment['curiosity_score']}"
        )

        print(
            f"Information: "
            f"{moment['information_score']}"
        )

        print(
            f"Specificity: "
            f"{moment['specificity_score']}"
        )

        print(
            f"Conversation: "
            f"{moment['conversation_score']}"
        )

        print(
            f"Text: "
            f"{moment['text'][:220]}"
        )

        print(
            "----------------------------------------"
        )

    print(
        f"Output: {output_path}"
    )

    print(
        "========================================"
    )


if __name__ == "__main__":

    if len(sys.argv) != 3:

        print(
            "Usage: "
            "python scripts/find_moments.py "
            "<transcript.json> "
            "<moments.json>"
        )

        sys.exit(1)

    find_moments(
        sys.argv[1],
        sys.argv[2]
)
