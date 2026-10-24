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


def score_hook(text, focus_terms=None):
    ws = words(text)
    if not ws:
        return -100
    score = 0.0
    score += min(sum(w in HOOK_WORDS for w in ws) * 3.0, 18)
    score += min(sum(w in {"you", "your", "we", "i", "my", "our"} for w in ws[:12]) * 1.5, 6)
    if "?" in text:
        score += 5
    if any(w in {"because", "but", "however", "until", "turns"} for w in ws):
        score += 3
    if re.search(r"\b\d+(?:\.\d+)?%?\b", text):
        score += 2
    if ws[0] in WEAK_STARTS:
        score -= 8
    if ws[0] in REFERENCE_STARTS:
        score -= 7
    if len(ws) < 4:
        score -= 8
    if focus_terms:
        text_lower = " ".join(ws)
        for term in focus_terms:
            if term in text_lower:
                score += 4
    return round(score, 2)


def hook_tokens(text):
    return re.findall(r"\S+", clean(text))


def select_short_hook(text, focus_terms=None):
    """Return a punchy 4–5 word phrase from the real transcript text."""
    tokens = hook_tokens(text)
    if len(tokens) <= 5:
        return clean(text)

    best = None
    limit = min(len(tokens), 16)
    for size in (5, 4):
        for start in range(0, max(0, limit - size + 1)):
            candidate = " ".join(tokens[start:start + size]).strip()
            if not candidate:
                continue
            candidate_score = score_hook(candidate, focus_terms)

            first_word = words(candidate)[:1]
            if first_word and first_word[0] in WEAK_STARTS:
                candidate_score -= 5
            if first_word and first_word[0] in REFERENCE_STARTS:
                candidate_score -= 3

            # Prefer the requested short-hook shape, then the strongest wording.
            ranking = (candidate_score, 1 if size == 5 else 0, -start)
            if best is None or ranking > best[0]:
                best = (ranking, candidate)

    if best:
        return best[1]

    return " ".join(tokens[:5])


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
    starts, ends = [], []
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


def candidates(segments, start, end, hook_window):
    result = []
    for segment in segments:
        ss, se = segment_bounds(segment)
        text = segment_text(segment)
        if ss is None or not text or se <= start or ss >= end:
            continue
        if ss < start or ss > min(end, start + hook_window):
            continue
        result.append((ss, se, text))
    return result


def optimize(moment, segments, focus_terms, hook_window):
    original_start = float(moment.get("start", 0))
    original_end = float(moment.get("end", 0))
    start, end = original_start, original_end
    fallback = bool(moment.get("fallback"))
    if end <= start:
        return None

    trimmed_start, trimmed_end = word_bounds(segments, start, end)
    start = trimmed_start
    end = max(trimmed_end, start + 0.5)

    best = None
    for ss, se, text in candidates(segments, start, end, hook_window):
        hook = score_hook(text, focus_terms)
        if best is None or hook > best[0]:
            best = (hook, ss, text)

    original_text = clean(moment.get("text", ""))
    hook_score = score_hook(original_text, focus_terms)
    hook_source = original_text

    if best and not fallback:
        candidate_score, candidate_start, candidate_text = best
        proposed_duration = end - candidate_start
        if candidate_score >= hook_score + 3 and proposed_duration >= 10:
            start = candidate_start
            hook_score = candidate_score
            hook_source = candidate_text

    result = dict(moment)
    result["start"] = round(start, 3)
    result["end"] = round(end, 3)
    result["hook_score"] = round(hook_score, 2)
    result["hook_source_text"] = hook_source[:240]
    result["hook_text"] = select_short_hook(hook_source, focus_terms)
    result["hook_word_count"] = len(words(result["hook_text"]))
    result["hook_optimized"] = bool(best and start != original_start and not fallback)
    result["hook_deadline_seconds"] = hook_window
    result["edge_silence_trimmed"] = bool(start != original_start or end != original_end)
    return result


def load_campaign(config_path, campaign_id):
    if not config_path or not campaign_id:
        return {}, [], 3.0
    try:
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        campaign = config.get("campaigns", {}).get(campaign_id, {})
        req = campaign.get("content_requirements", {})
        focus = [str(x).lower() for x in req.get("content_focus", [])]
        featured = req.get("featured_person")
        if featured:
            focus.append(str(featured).lower())
        if req.get("warren_zeiders_must_be_present"):
            focus.append("warren zeiders")
        hook_window = float(req.get("opening_hook_deadline_seconds", 3))
        return req, focus, hook_window
    except Exception:
        return {}, [], 3.0


def main():
    if len(sys.argv) not in (4, 6):
        raise SystemExit("Usage: python scripts/optimize_moments.py <transcript.json> <moments.json> <output.json> [campaign_config.json campaign_id]")

    transcript_path, moments_path, output_path = map(Path, sys.argv[1:4])
    config_path = sys.argv[4] if len(sys.argv) == 6 else None
    campaign_id = sys.argv[5] if len(sys.argv) == 6 else None
    requirements, focus_terms, hook_window = load_campaign(config_path, campaign_id)
    segments = load_transcript(transcript_path)
    data = json.loads(moments_path.read_text(encoding="utf-8"))
    moments = data.get("moments", []) if isinstance(data, dict) else data
    if not isinstance(moments, list):
        moments = []

    optimized = [optimize(moment, segments, focus_terms, hook_window) for moment in moments]
    optimized = [item for item in optimized if item and item["end"] > item["start"]]
    optimized.sort(key=lambda item: (float(item.get("hook_score", 0)), float(item.get("score", 0))), reverse=True)

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
        "version": "hook-optimizer-v3",
        "campaign_id": campaign_id,
        "campaign_requirements_used": bool(requirements),
        "moments": selected,
        "count": len(selected),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"HOOK OPTIMIZATION COMPLETE: {len(selected)} moments")
    print("Hook shape: 4–5 words")
    print(f"Campaign-aware focus: {bool(focus_terms)}")
    print(f"Hook deadline: {hook_window:.1f}s")


if __name__ == "__main__":
    main()
