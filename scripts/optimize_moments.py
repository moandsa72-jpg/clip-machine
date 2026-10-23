import json
import re
import sys
from pathlib import Path

HOOK_WORDS = {
    "secret", "mistake", "truth", "crazy", "actually", "never", "always",
    "best", "worst", "why", "how", "important", "problem", "difference",
    "real", "learned", "discovered", "imagine", "simple", "hard", "wrong",
    "right", "finally", "because", "nobody", "everyone", "really",
    "seriously", "literally", "happened", "dangerous", "weird", "insane",
    "shocking", "surprising", "unexpected", "unbelievable", "must", "need",
    "success", "failure", "win", "lose", "love", "hate", "funny", "amazing",
}
WEAK_STARTS = {"so", "well", "okay", "alright", "basically", "um", "uh", "yeah", "like", "and", "then", "oh"}
REFERENCE_STARTS = {"he", "she", "they", "it", "this", "that", "these", "those", "there", "here"}


def words(text):
    return re.findall(r"\b[\w']+\b", str(text).lower())


def clean(text):
    return re.sub(r"\s+", " ", str(text)).strip()


def score_hook(text):
    ws = words(text)
    if not ws:
        return -100
    score = 0.0
    score += min(sum(w in HOOK_WORDS for w in ws) * 3.0, 18)
    score += min(sum(w in {"you", "your", "we", "i", "my", "our"} for w in ws[:12]) * 1.5, 6)
    if "?" in text:
        score += 5
    if any(w in {"because", "but", "however", "until", "turns", "turns out"} for w in ws):
        score += 3
    if re.search(r"\b\d+(?:\.\d+)?%?\b", text):
        score += 2
    if ws[0] in WEAK_STARTS:
        score -= 8
    if ws[0] in REFERENCE_STARTS:
        score -= 7
    if len(ws) < 4:
        score -= 8
    return round(score, 2)


def load_transcript(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("segments", []) if isinstance(data, dict) else []


def segment_text(segment):
    return clean(segment.get("text", ""))


def segment_bounds(segment):
    try:
        return float(segment["start"]), float(segment["end"])
    except (KeyError, TypeError, ValueError):
        return None, None


def word_bounds(segments, start, end):
    starts = []
    ends = []
    for segment in segments:
        for item in segment.get("words", []) or []:
            try:
                ws = float(item["start"])
                we = float(item["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if we > start and ws < end and clean(item.get("word", "")):
                starts.append(max(start, ws))
                ends.append(min(end, we))
    return (min(starts) if starts else start, max(ends) if ends else end)


def candidates(segments, start, end):
    result = []
    for segment in segments:
        ss, se = segment_bounds(segment)
        text = segment_text(segment)
        if ss is None or not text or se <= start or ss >= end:
            continue
        if ss < start or ss > min(end, start + 6.0):
            continue
        result.append((ss, se, text))
    return result


def optimize(moment, segments):
    start = float(moment.get("start", 0))
    end = float(moment.get("end", 0))
    fallback = bool(moment.get("fallback"))

    if end <= start:
        return None

    trimmed_start, trimmed_end = word_bounds(segments, start, end)
    start = trimmed_start
    end = max(trimmed_end, start + 0.5)

    best = None
    for ss, se, text in candidates(segments, start, end):
        hook = score_hook(text)
        if best is None or hook > best[0]:
            best = (hook, ss, text)

    original_start = start
    hook_score = score_hook(clean(moment.get("text", "")))
    hook_text = clean(moment.get("text", ""))

    if best and not fallback:
        candidate_score, candidate_start, candidate_text = best
        proposed_duration = end - candidate_start
        # Only move the opening when it materially improves the hook and
        # preserves a useful standalone clip length.
        if candidate_score >= hook_score + 3 and proposed_duration >= 10:
            start = candidate_start
            hook_score = candidate_score
            hook_text = candidate_text

    result = dict(moment)
    result["start"] = round(start, 3)
    result["end"] = round(end, 3)
    result["hook_score"] = round(hook_score, 2)
    result["hook_text"] = hook_text[:240]
    result["hook_optimized"] = bool(best and start != original_start and not fallback)
    result["edge_silence_trimmed"] = bool(start != float(moment.get("start", start)) or end != float(moment.get("end", end)))
    return result


def main():
    if len(sys.argv) != 4:
        raise SystemExit("Usage: python scripts/optimize_moments.py <transcript.json> <moments.json> <output.json>")

    transcript_path, moments_path, output_path = map(Path, sys.argv[1:])
    segments = load_transcript(transcript_path)
    data = json.loads(moments_path.read_text(encoding="utf-8"))
    moments = data.get("moments", []) if isinstance(data, dict) else data
    if not isinstance(moments, list):
        moments = []

    optimized = [optimize(moment, segments) for moment in moments]
    optimized = [item for item in optimized if item and item["end"] > item["start"]]
    optimized.sort(key=lambda item: float(item.get("score", 0)), reverse=True)

    # Keep strong moments and remove near-duplicates after hook optimization.
    selected = []
    for item in optimized:
        overlap = False
        for other in selected:
            left = max(item["start"], other["start"])
            right = min(item["end"], other["end"])
            intersection = max(0.0, right - left)
            union = max(item["end"], other["end"]) - min(item["start"], other["start"])
            if union > 0 and intersection / union >= 0.65:
                overlap = True
                break
        if not overlap:
            selected.append(item)

    selected.sort(key=lambda item: (float(item["start"]), float(item["end"])))
    output = {
        "version": "hook-optimizer-v1",
        "moments": selected,
        "count": len(selected),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"HOOK OPTIMIZATION COMPLETE: {len(selected)} moments")


if __name__ == "__main__":
    main()
