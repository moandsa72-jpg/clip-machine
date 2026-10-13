import json
import re
import sys
from pathlib import Path


# ============================================================
# CLIP MACHINE — SMART MOMENT DETECTOR V2
# ============================================================
#
# Finds short-form candidates using:
#
#   • opening hook strength
#   • curiosity
#   • strong statements
#   • questions
#   • numbers / specificity
#   • information density
#   • emotional language
#   • contrast
#   • story structure
#   • setup -> payoff
#   • complete-thought endings
#   • conversational language
#   • duration quality
#   • repetition penalties
#   • filler penalties
#   • weak-opening penalties
#
# No arbitrary maximum number of clips.
#
# The detector is deterministic:
# the same transcript produces the same result.
# ============================================================


MIN_DURATION = 10
IDEAL_MIN_DURATION = 15
IDEAL_MAX_DURATION = 27
MAX_DURATION = 35


# ============================================================
# VOCABULARY
# ============================================================

HOOK_WORDS = {
    "secret", "mistake", "truth", "crazy", "actually",
    "never", "always", "best", "worst", "why", "how",
    "important", "problem", "difference", "real", "learn",
    "learned", "discovered", "imagine", "simple", "easy",
    "hard", "wrong", "right", "first", "finally",
    "because", "nobody", "everyone", "nothing",
    "everything", "really", "seriously", "literally",
    "apparently", "turns", "turned", "happened",
    "happens", "dangerous", "weird", "insane",
    "shocking", "surprising", "unexpected"
}


CURIOSITY_WORDS = {
    "why", "how", "secret", "reason", "actually",
    "truth", "discovered", "revealed", "happened",
    "happens", "difference", "problem", "because",
    "before", "after", "until", "instead", "without",
    "unless", "never", "really"
}


STRONG_WORDS = {
    "must", "need", "important", "wrong", "right",
    "never", "always", "best", "worst", "dangerous",
    "impossible", "possible", "critical", "massive",
    "huge", "crazy", "insane", "shocking", "secret",
    "truth", "failure", "success", "win", "lose"
}


EMOTION_WORDS = {
    "love", "hate", "angry", "afraid", "fear",
    "scared", "happy", "sad", "excited", "surprised",
    "shocked", "embarrassed", "frustrated", "worried",
    "amazing", "terrible", "horrible", "beautiful",
    "funny", "crazy", "insane", "unbelievable"
}


CONTRAST_WORDS = {
    "but", "however", "although", "instead",
    "rather", "yet", "except", "while", "though"
}


SETUP_MARKERS = {
    "at first",
    "in the beginning",
    "before that",
    "the problem",
    "the thing is",
    "i thought",
    "we thought",
    "what happened",
    "the reason",
    "until",
    "originally",
    "initially"
}


PAYOFF_MARKERS = {
    "so",
    "that's why",
    "that is why",
    "which means",
    "the result",
    "as a result",
    "because of that",
    "turns out",
    "it turns out",
    "finally",
    "in the end",
    "what i learned",
    "what we learned",
    "the answer",
    "the truth is"
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
    "and",
    "then"
}


FILLER_WORDS = {
    "um",
    "uh",
    "like",
    "basically",
    "actually",
    "sort",
    "kind"
}


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(text):
    return re.sub(r"\s+", " ", str(text)).strip()


def get_words(text):
    return re.findall(
        r"\b[\w']+\b",
        text.lower()
    )


def count_words(text, vocabulary):
    return sum(
        1
        for word in get_words(text)
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


def is_thought_end(text):
    text = clean_text(text)

    if not text:
        return False

    return text.endswith(
        (".", "!", "?")
    )


def sentence_count(text):
    return len(
        re.findall(
            r"[.!?]+",
            text
        )
    )


# ============================================================
# STRUCTURE ANALYSIS
# ============================================================

def calculate_structure_score(text):

    text_lower = text.lower()

    setup_hits = sum(
        1
        for marker in SETUP_MARKERS
        if marker in text_lower
    )

    payoff_hits = sum(
        1
        for marker in PAYOFF_MARKERS
        if marker in text_lower
    )

    contrast_hits = count_words(
        text_lower,
        CONTRAST_WORDS
    )

    score = 0

    if setup_hits:
        score += min(
            setup_hits * 3,
            8
        )

    if payoff_hits:
        score += min(
            payoff_hits * 4,
            10
        )

    if contrast_hits:
        score += min(
            contrast_hits * 2,
            6
        )

    # Strong signal:
    # setup + payoff + contrast.
    if setup_hits and payoff_hits:
        score += 8

    return score


# ============================================================
# OPENING HOOK ANALYSIS
# ============================================================

def calculate_opening_hook(text):

    words = get_words(text)

    if not words:
        return 0

    opening = words[:12]

    score = 0

    hook_hits = sum(
        1
        for word in opening
        if word in HOOK_WORDS
    )

    curiosity_hits = sum(
        1
        for word in opening
        if word in CURIOSITY_WORDS
    )

    strong_hits = sum(
        1
        for word in opening
        if word in STRONG_WORDS
    )

    score += min(
        hook_hits * 2,
        8
    )

    score += min(
        curiosity_hits * 2,
        6
    )

    score += min(
        strong_hits * 2,
        6
    )

    if words[0] in WEAK_START_WORDS:
        score -= 5

    if len(words) >= 3:
        first_three = " ".join(words[:3])

        if first_three.count("um") > 0:
            score -= 2

    return max(
        0,
        score
    )


# ============================================================
# PAYOFF ANALYSIS
# ============================================================

def calculate_payoff_score(text):

    text_lower = text.lower()

    score = 0

    setup_hits = sum(
        1
        for marker in SETUP_MARKERS
        if marker in text_lower
    )

    payoff_hits = sum(
        1
        for marker in PAYOFF_MARKERS
        if marker in text_lower
    )

    contrast_hits = count_words(
        text_lower,
        CONTRAST_WORDS
    )

    if setup_hits:
        score += min(
            setup_hits * 2,
            6
        )

    if payoff_hits:
        score += min(
            payoff_hits * 4,
            12
        )

    if contrast_hits:
        score += min(
            contrast_hits * 2,
            6
        )

    if setup_hits and payoff_hits:
        score += 8

    return score


# ============================================================
# ENDING ANALYSIS
# ============================================================

def calculate_ending_score(text):

    words = get_words(text)

    if not words:
        return 0

    score = 0

    ending = words[-12:]

    ending_strong = sum(
        1
        for word in ending
        if word in STRONG_WORDS
    )

    ending_hook = sum(
        1
        for word in ending
        if word in HOOK_WORDS
    )

    score += min(
        ending_strong * 2,
        6
    )

    score += min(
        ending_hook * 1.5,
        5
    )

    return score


# ============================================================
# SCORE CANDIDATE
# ============================================================

def score_candidate(
    text,
    duration,
    complete_thought
):

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
            "payoff_score": 0,
            "structure_score": 0,
            "emotion_score": 0,
            "ending_score": 0,
            "boundary_score": 0,
            "penalty": 0
        }

    text_lower = text.lower()

    hook_score = 0
    curiosity_score = 0
    information_score = 0
    specificity_score = 0
    conversation_score = 0
    duration_score = 0
    payoff_score = 0
    structure_score = 0
    emotion_score = 0
    ending_score = 0
    boundary_score = 0
    penalty = 0

    # --------------------------------------------------------
    # HOOK
    # --------------------------------------------------------

    hook_score += calculate_opening_hook(
        text
    )

    # Overall hook vocabulary.
    hook_hits = count_words(
        text_lower,
        HOOK_WORDS
    )

    hook_score += min(
        hook_hits * 1.5,
        10
    )

    # --------------------------------------------------------
    # CURIOSITY
    # --------------------------------------------------------

    curiosity_hits = count_words(
        text_lower,
        CURIOSITY_WORDS
    )

    curiosity_score += min(
        curiosity_hits * 2,
        14
    )

    questions = question_count(
        text
    )

    if questions:
        curiosity_score += min(
            questions * 4,
            10
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
    # EMOTION
    # --------------------------------------------------------

    emotion_hits = count_words(
        text_lower,
        EMOTION_WORDS
    )

    emotion_score += min(
        emotion_hits * 2,
        10
    )

    # --------------------------------------------------------
    # CONTRAST
    # --------------------------------------------------------

    contrast_hits = count_words(
        text_lower,
        CONTRAST_WORDS
    )

    if contrast_hits:
        structure_score += min(
            contrast_hits * 2,
            8
        )

    # --------------------------------------------------------
    # SPECIFICITY
    # --------------------------------------------------------

    numbers = count_numbers(
        text
    )

    specificity_score += min(
        numbers * 3,
        10
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

    if word_count >= 70:
        information_score += 2

    # --------------------------------------------------------
    # CONVERSATIONAL LANGUAGE
    # --------------------------------------------------------

    conversational_words = {
        "you",
        "your",
        "we",
        "us",
        "i",
        "me",
        "they",
        "them"
    }

    conversation_hits = sum(
        1
        for word in words
        if word in conversational_words
    )

    if conversation_hits >= 2:
        conversation_score += 3

    if conversation_hits >= 5:
        conversation_score += 2

    # --------------------------------------------------------
    # DURATION
    # --------------------------------------------------------

    if (
        IDEAL_MIN_DURATION
        <= duration
        <= IDEAL_MAX_DURATION
    ):
        duration_score += 8

    elif (
        MIN_DURATION
        <= duration
        < IDEAL_MIN_DURATION
    ):
        duration_score += 3

    elif (
        IDEAL_MAX_DURATION
        < duration
        <= MAX_DURATION
    ):
        duration_score += 4

    else:
        duration_score -= 2

    # --------------------------------------------------------
    # COMPLETE THOUGHT
    # --------------------------------------------------------

    if complete_thought:
        boundary_score += 6
    else:
        penalty += 5

    # --------------------------------------------------------
    # WEAK START
    # --------------------------------------------------------

    if words[0] in WEAK_START_WORDS:
        penalty += 4

    # Additional weak-opening check.
    opening = words[:5]

    weak_count = sum(
        1
        for word in opening
        if word in WEAK_START_WORDS
    )

    if weak_count >= 2:
        penalty += 3

    # --------------------------------------------------------
    # REPETITION
    # --------------------------------------------------------

    unique_ratio = (
        len(set(words))
        / max(len(words), 1)
    )

    if unique_ratio < 0.40:
        penalty += 6

    elif unique_ratio < 0.50:
        penalty += 3

    # --------------------------------------------------------
    # FILLER
    # --------------------------------------------------------

    filler_hits = sum(
        1
        for word in words
        if word in FILLER_WORDS
    )

    if len(words) >= 15:

        filler_ratio = (
            filler_hits
            / len(words)
        )

        if filler_ratio > 0.12:
            penalty += 5

        elif filler_ratio > 0.08:
            penalty += 3

    # --------------------------------------------------------
    # EXCESSIVE SHORT SENTENCES
    # --------------------------------------------------------

    sentences = sentence_count(
        text
    )

    if (
        word_count >= 30
        and sentences >= 8
    ):
        penalty += 3

    # --------------------------------------------------------
    # STRUCTURE
    # --------------------------------------------------------

    structure_score += calculate_structure_score(
        text
    )

    payoff_score = calculate_payoff_score(
        text
    )

    ending_score = calculate_ending_score(
        text
    )

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
        + payoff_score
        + structure_score
        + emotion_score
        + ending_score
        + boundary_score
        - penalty
    )

    return {
        "score": round(score, 2),
        "hook_score": round(hook_score, 2),
        "curiosity_score": round(
            curiosity_score,
            2
        ),
        "information_score": round(
            information_score,
            2
        ),
        "specificity_score": round(
            specificity_score,
            2
        ),
        "conversation_score": round(
            conversation_score,
            2
        ),
        "duration_score": round(
            duration_score,
            2
        ),
        "payoff_score": round(
            payoff_score,
            2
        ),
        "structure_score": round(
            structure_score,
            2
        ),
        "emotion_score": round(
            emotion_score,
            2
        ),
        "ending_score": round(
            ending_score,
            2
        ),
        "boundary_score": round(
            boundary_score,
            2
        ),
        "penalty": round(
            penalty,
            2
        )
    }


# ============================================================
# BUILD WINDOWS
# ============================================================

def build_windows(segments):

    windows = []

    for i, start_segment in enumerate(
        segments
    ):

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
                    segments[j].get(
                        "text",
                        ""
                    )
                )
            )

            if duration < MIN_DURATION:
                continue

            text = clean_text(
                " ".join(text_parts)
            )

            if not text:
                continue

            complete_thought = is_thought_end(
                segments[j].get(
                    "text",
                    ""
                )
            )

            scores = score_candidate(
                text,
                duration,
                complete_thought
            )

            # Only keep naturally finished thoughts,
            # unless the transcript gives us no sentence
            # boundary before the maximum window.
            if complete_thought:

                windows.append({
                    "start": round(
                        start,
                        3
                    ),
                    "end": round(
                        end,
                        3
                    ),
                    "duration": round(
                        duration,
                        3
                    ),
                    "text": text,
                    **scores
                })

            elif duration >= MAX_DURATION - 1:

                # Emergency fallback for transcripts
                # without useful punctuation.
                windows.append({
                    "start": round(
                        start,
                        3
                    ),
                    "end": round(
                        end,
                        3
                    ),
                    "duration": round(
                        duration,
                        3
                    ),
                    "text": text,
                    **scores
                })

    return windows


# ============================================================
# OVERLAP
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


# ============================================================
# REMOVE REDUNDANT CANDIDATES
# ============================================================

def remove_overlaps(windows):

    selected = []

    windows = sorted(
        windows,
        key=lambda item: (
            item["score"],
            item["payoff_score"],
            item["structure_score"],
            item["hook_score"],
            item["curiosity_score"],
            item["information_score"],
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

    return sorted(
        selected,
        key=lambda item: item["start"]
    )


# ============================================================
# CLASSIFICATION
# ============================================================

def classify_moment(moment):

    text = moment["text"].lower()

    if (
        moment["payoff_score"] >= 12
        and moment["structure_score"] >= 10
    ):
        return "setup_payoff"

    if (
        "?" in text
        or moment["curiosity_score"] >= 10
    ):
        return "curiosity"

    if (
        moment["specificity_score"] >= 6
        and moment["information_score"] >= 4
    ):
        return "information"

    if moment["emotion_score"] >= 6:
        return "emotional"

    if moment["hook_score"] >= 12:
        return "strong_statement"

    if (
        "!" in text
        or moment["hook_score"] >= 8
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
            "detector_version":
                "smart-v2"
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
        "SMART MOMENT ANALYSIS V2 COMPLETE"
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
            f"Payoff: "
            f"{moment['payoff_score']}"
        )

        print(
            f"Structure: "
            f"{moment['structure_score']}"
        )

        print(
            f"Emotion: "
            f"{moment['emotion_score']}"
        )

        print(
            f"Ending: "
            f"{moment['ending_score']}"
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
