import json
import re
import sys
from pathlib import Path


# ============================================================
# CLIP MACHINE — SMART MOMENT DETECTOR V3
# ============================================================
#
# V3 changes the detector from:
#
#     "interesting words = good clip"
#
# into:
#
#     "good scene structure + understandable context
#      + strong content = good clip"
#
# Pipeline:
#
#     transcript
#         ↓
#     natural scene starts
#         ↓
#     candidate windows
#         ↓
#     quality gate
#         ↓
#     structural analysis
#         ↓
#     entertainment scoring
#         ↓
#     overlap removal
#         ↓
#     final moments
#
# No arbitrary maximum number of clips.
# ============================================================


MIN_DURATION = 10
IDEAL_MIN_DURATION = 15
IDEAL_MAX_DURATION = 27
MAX_DURATION = 35

DETECTOR_VERSION = "smart-v3"


# ============================================================
# VOCABULARY
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
    "unbelievable",
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
    "really",
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
    "failure",
    "success",
    "win",
    "lose",
    "destroy",
    "destroyed",
    "fight",
    "fighting",
}


EMOTION_WORDS = {
    "love",
    "hate",
    "angry",
    "afraid",
    "fear",
    "scared",
    "happy",
    "sad",
    "excited",
    "surprised",
    "shocked",
    "embarrassed",
    "frustrated",
    "worried",
    "amazing",
    "terrible",
    "horrible",
    "beautiful",
    "funny",
    "crazy",
    "insane",
    "unbelievable",
}


CONTRAST_WORDS = {
    "but",
    "however",
    "although",
    "instead",
    "rather",
    "yet",
    "except",
    "while",
    "though",
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
    "initially",
    "at the time",
    "back then",
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
    "the truth is",
    "that's when",
    "this is why",
}


ANSWER_MARKERS = {
    "because",
    "so",
    "that's why",
    "that is why",
    "the reason",
    "the answer",
    "it was",
    "it is",
    "actually",
    "turns out",
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
    "then",
    "oh",
}


FILLER_WORDS = {
    "um",
    "uh",
    "like",
    "basically",
    "actually",
    "sort",
    "kind",
    "youknow",
}


REFERENCE_START_WORDS = {
    "he",
    "she",
    "they",
    "it",
    "this",
    "that",
    "these",
    "those",
    "there",
    "here",
}


SOCIAL_OPENING_WORDS = {
    "clap",
    "clapping",
    "welcome",
    "gang",
    "guys",
    "everyone",
    "thanks",
    "thank",
    "please",
    "hello",
    "hi",
    "congratulations",
    "congrats",
}


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(text):
    return re.sub(
        r"\s+",
        " ",
        str(text)
    ).strip()


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


def sentence_count(text):
    return len(
        re.findall(
            r"[.!?]+",
            text
        )
    )


def is_thought_end(text):
    text = clean_text(text)

    if not text:
        return False

    return text.endswith(
        (".", "!", "?")
    )


# ============================================================
# NATURAL SCENE START
# ============================================================

def is_natural_start(
    segments,
    index
):
    if index == 0:
        return True

    current = segments[index]
    previous = segments[index - 1]

    current_text = clean_text(
        current.get("text", "")
    )

    previous_text = clean_text(
        previous.get("text", "")
    )

    if not current_text:
        return False

    # A new sentence after a completed thought.
    if is_thought_end(previous_text):
        return True

    # A noticeable silence can indicate a new thought.
    try:
        previous_end = float(
            previous["end"]
        )

        current_start = float(
            current["start"]
        )

        if current_start - previous_end >= 0.80:
            return True

    except (
        KeyError,
        TypeError,
        ValueError
    ):
        pass

    return False


# ============================================================
# OPENING QUALITY
# ============================================================

def analyze_opening(text):

    words = get_words(text)

    result = {
        "score": 0,
        "weak": False,
        "fragmentary": False,
        "social": False,
        "reference": False,
        "filler": 0,
    }

    if not words:
        result["weak"] = True
        result["fragmentary"] = True
        return result

    first_word = words[0]

    if first_word in WEAK_START_WORDS:
        result["weak"] = True
        result["score"] -= 4

    if first_word in REFERENCE_START_WORDS:
        result["reference"] = True
        result["score"] -= 3

    if first_word in SOCIAL_OPENING_WORDS:
        result["social"] = True
        result["score"] -= 4

    opening = words[:8]

    filler_count = sum(
        1
        for word in opening
        if word in FILLER_WORDS
    )

    result["filler"] = filler_count

    if filler_count:
        result["score"] -= min(
            filler_count * 2,
            6
        )

    # Extremely weak opening:
    # filler/social language with no actual hook.
    if (
        result["weak"]
        and result["social"]
        and len(words) >= 5
    ):
        result["fragmentary"] = True

    return result


# ============================================================
# SELF-CONTAINEDNESS
# ============================================================

def calculate_standalone_score(text):

    words = get_words(text)

    if not words:
        return 0

    score = 0

    opening = words[:10]

    # Direct audience language is useful.
    direct_words = {
        "you",
        "your",
        "we",
        "i",
        "my",
        "our",
    }

    direct_hits = sum(
        1
        for word in opening
        if word in direct_words
    )

    if direct_hits:
        score += min(
            direct_hits * 2,
            6
        )

    # Questions can make a clip understandable.
    if question_count(text):
        score += 3

    # A named/specific subject helps.
    if count_numbers(text):
        score += 2

    # Penalize unexplained references at the beginning.
    if opening:
        if opening[0] in REFERENCE_START_WORDS:
            score -= 5

    # Very short vague openings are weak.
    if len(opening) >= 2:
        vague_pair = (
            opening[0] in REFERENCE_START_WORDS
            and opening[1] in REFERENCE_START_WORDS
        )

        if vague_pair:
            score -= 5

    return score


# ============================================================
# STRUCTURE
# ============================================================

def calculate_structure(
    text
):

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

    answer_hits = sum(
        1
        for marker in ANSWER_MARKERS
        if marker in text_lower
    )

    contrast_hits = count_words(
        text_lower,
        CONTRAST_WORDS
    )

    question_hits = question_count(
        text
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
            12
        )

    if answer_hits:
        score += min(
            answer_hits * 2,
            6
        )

    if contrast_hits:
        score += min(
            contrast_hits * 2,
            6
        )

    if (
        question_hits
        and answer_hits
    ):
        score += 7

    if (
        setup_hits
        and payoff_hits
    ):
        score += 8

    return score


# ============================================================
# PAYOFF
# ============================================================

def calculate_payoff_score(text):

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

    answer_hits = sum(
        1
        for marker in ANSWER_MARKERS
        if marker in text_lower
    )

    score = 0

    score += min(
        setup_hits * 2,
        6
    )

    score += min(
        payoff_hits * 4,
        12
    )

    score += min(
        answer_hits * 2,
        6
    )

    if (
        setup_hits
        and payoff_hits
    ):
        score += 8

    return score


# ============================================================
# SCORE CANDIDATE
# ============================================================

def score_candidate(
    text,
    duration,
    complete_thought,
    natural_start
):

    words = get_words(text)

    opening = analyze_opening(
        text
    )

    if not words:
        return {
            "score": 0,
            "quality_score": 0,
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
            "standalone_score": 0,
            "boundary_score": 0,
            "penalty": 0,
            "rejection_flags": [
                "empty"
            ],
        }

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
    standalone_score = 0
    boundary_score = 0
    penalty = 0

    rejection_flags = []

    # --------------------------------------------------------
    # OPENING
    # --------------------------------------------------------

    hook_score += max(
        0,
        opening["score"]
    )

    if opening["weak"]:
        penalty += 4

    if opening["reference"]:
        penalty += 3

    if opening["social"]:
        penalty += 4

    if opening["fragmentary"]:
        penalty += 7
        rejection_flags.append(
            "weak_social_opening"
        )

    if opening["filler"] >= 2:
        penalty += 4
        rejection_flags.append(
            "filler_opening"
        )

    # --------------------------------------------------------
    # HOOK VOCABULARY
    # --------------------------------------------------------

    hook_hits = count_words(
        text,
        HOOK_WORDS
    )

    hook_score += min(
        hook_hits * 1.5,
        12
    )

    # Strong language.
    strong_hits = count_words(
        text,
        STRONG_WORDS
    )

    hook_score += min(
        strong_hits * 1.5,
        10
    )

    # --------------------------------------------------------
    # CURIOSITY
    # --------------------------------------------------------

    curiosity_hits = count_words(
        text,
        CURIOSITY_WORDS
    )

    curiosity_score += min(
        curiosity_hits * 2,
        12
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
    # EMOTION
    # --------------------------------------------------------

    emotion_hits = count_words(
        text,
        EMOTION_WORDS
    )

    emotion_score += min(
        emotion_hits * 2,
        10
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
    # CONVERSATION
    # --------------------------------------------------------

    conversational_words = {
        "you",
        "your",
        "we",
        "us",
        "i",
        "me",
        "they",
        "them",
        "my",
        "our",
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
        duration_score += 2

    else:
        duration_score -= 3

    if duration > 32:
        penalty += 2

    # --------------------------------------------------------
    # BOUNDARY
    # --------------------------------------------------------

    if complete_thought:
        boundary_score += 6
    else:
        penalty += 7
        rejection_flags.append(
            "incomplete_thought"
        )

    if natural_start:
        boundary_score += 4
    else:
        penalty += 5
        rejection_flags.append(
            "unnatural_start"
        )
        
# --------------------------------------------------------
           # STANDALONE
# --------------------------------------------------------

    standalone_score = (
        calculate_standalone_score(
            text
    )
)

    if standalone_score < 0:
        penalty += abs(
        standalone_score
    )

        rejection_flags.append(
            "weak_context"
    )

    # --------------------------------------------------------
    # SOCIAL / HOUSEKEEPING CONTENT
    # --------------------------------------------------------

    social_hits = count_words(
        text,
        SOCIAL_OPENING_WORDS
    )

    if (
        social_hits >= 3
        and structure_score < 8
        and payoff_score < 8
    ):
        penalty += 6
        rejection_flags.append(
            "social_housekeeping"
        )

    # --------------------------------------------------------
    # FINAL SCORE
    # --------------------------------------------------------

    raw_score = (
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
        + standalone_score
        + boundary_score
        - penalty
    )

    quality_score = (
        boundary_score
        + standalone_score
        + structure_score
        + ending_score
        + information_score
        - penalty
    )

    return {
        "score": round(
            raw_score,
            2
        ),
        "quality_score": round(
            quality_score,
            2
        ),
        "hook_score": round(
            hook_score,
            2
        ),
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
        "standalone_score": round(
            standalone_score,
            2
        ),
        "boundary_score": round(
            boundary_score,
            2
        ),
        "penalty": round(
            penalty,
            2
        ),
        "rejection_flags": rejection_flags,
    }


# ============================================================
# QUALITY GATE
# ============================================================

def passes_quality_gate(scores):

    flags = scores["rejection_flags"]

    # Hard failures.
    hard_failures = {
        "empty",
        "weak_social_opening",
        "heavy_repetition",
        "heavy_filler",
        "fragmented_delivery",
    }

    if any(
        flag in hard_failures
        for flag in flags
    ):
        return False, "hard_quality_failure"

    # Incomplete thoughts are allowed only for
    # emergency transcript cases.
    if (
        "incomplete_thought" in flags
        and "unnatural_start" in flags
    ):
        return False, "bad_boundaries"

    # A clip must have enough actual quality.
    if scores["quality_score"] < 18:        
       return False, "low_quality"

    # Avoid clips that are almost entirely curiosity
    # vocabulary without supporting information.
    if (
        scores["curiosity_score"] >= 12
        and scores["information_score"] == 0
        and scores["specificity_score"] == 0
        and scores["payoff_score"] == 0
        and scores["structure_score"] == 0
        and scores["emotion_score"] == 0
    ):
        return False, "curiosity_without_content"

    return True, ""


# ============================================================
# BUILD CANDIDATE WINDOWS
# ============================================================

def build_windows(
    segments
):

    windows = []
    rejected = []

    for i, start_segment in enumerate(
        segments
    ):

        if not is_natural_start(
            segments,
            i
        ):
            continue

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

            duration = (
                end
                - start
            )

            if duration > MAX_DURATION:
                break

            segment_text = clean_text(
                segments[j].get(
                    "text",
                    ""
                )
            )

            if segment_text:
                text_parts.append(
                    segment_text
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
                complete_thought,
                True
            )

            passes, reason = passes_quality_gate(
                scores
            )

            candidate = {
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
            }

            if passes:

                windows.append(
                    candidate
                )

            else:

                rejected.append({
                    "start": candidate["start"],
                    "end": candidate["end"],
                    "score": candidate["score"],
                    "reason": reason,
                    "flags": candidate[
                        "rejection_flags"
                    ],
                })

    return windows, rejected


# ============================================================
# OVERLAP
# ============================================================

def overlap_ratio(
    a,
    b
):

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
        earliest_end
        - latest_start
    )

    shorter = min(
        a["duration"],
        b["duration"]
    )

    if shorter <= 0:
        return 0

    return (
        overlap
        / shorter
    )


# ============================================================
# REMOVE REDUNDANT CANDIDATES
# ============================================================

def remove_overlaps(
    windows
):

    selected = []

    windows = sorted(
        windows,
        key=lambda item: (
            item["score"],
            item["quality_score"],
            item["payoff_score"],
            item["structure_score"],
            item["hook_score"],
            item["curiosity_score"],
            item["information_score"],
            -abs(
                item["duration"]
                - 20
            ),
        ),
        reverse=True,
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
        key=lambda item:
        item["start"]
    )


# ============================================================
# CLASSIFICATION
# ============================================================

def classify_moment(
    moment
):

    text = moment[
        "text"
    ].lower()

    if (
        moment["payoff_score"] >= 10
        and moment["structure_score"] >= 10
    ):
        return "setup_payoff"

    if (
        "?" in text
        and moment["payoff_score"] >= 4
    ):
        return "question_answer"

    if (
        moment["emotion_score"] >= 7
    ):
        return "emotional"

    if (
        moment["specificity_score"] >= 6
        and moment["information_score"] >= 4
    ):
        return "information"

    if (
        moment["hook_score"] >= 12
        and moment["standalone_score"] >= 0
    ):
        return "strong_statement"

    if (
        moment["curiosity_score"] >= 10
    ):
        return "curiosity"

    if (
        "!" in text
        or moment["emotion_score"] >= 4
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
            f"Transcript not found: "
            f"{input_path}"
        )

    with open(
        input_path,
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(
            file
        )

    segments = data.get(
        "segments",
        []
    )

    if not segments:
        raise ValueError(
            "Transcript contains no segments."
        )

    windows, rejected = build_windows(
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
            "detector_version":
                DETECTOR_VERSION,
            "minimum_duration":
                MIN_DURATION,
            "ideal_min_duration":
                IDEAL_MIN_DURATION,
            "ideal_max_duration":
                IDEAL_MAX_DURATION,
            "maximum_duration":
                MAX_DURATION,
            "candidate_windows":
                len(windows),
            "rejected_windows":
                len(rejected),
            "selected_moments":
                len(moments),
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

    # ========================================================
    # LOG
    # ========================================================

    print()
    print(
        "========================================"
    )
    print(
        "SMART MOMENT ANALYSIS V3 COMPLETE"
    )
    print(
        "========================================"
    )

    print(
        f"Candidate windows: "
        f"{len(windows)}"
    )

    print(
        f"Rejected windows: "
        f"{len(rejected)}"
    )

    print(
        f"Final moments: "
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
            f"score={moment['score']} "
            f"quality={moment['quality_score']}"
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
            f"Standalone: "
            f"{moment['standalone_score']}"
        )

        print(
            f"Ending: "
            f"{moment['ending_score']}"
        )

        print(
            f"Penalty: "
            f"{moment['penalty']}"
        )

        print(
            f"Text: "
            f"{moment['text'][:300]}"
        )

        print(
            "----------------------------------------"
        )

    print(
        "Output: "
        f"{output_path}"
    )

    print(
        "========================================"
    )


# ============================================================
# CLI
# ============================================================

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
    
        
       
