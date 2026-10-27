#!/usr/bin/env python3
"""Free, local campaign/clip matcher using weighted content similarity.

No API, model, login, or paid service. Produces the same opportunity schema used
by the existing posting queue so it can replace the old keyword-only matcher.
"""
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

STOP = {
    "the","and","that","this","with","from","have","what","when","your","they",
    "just","about","into","for","are","was","were","been","will","would","could",
    "there","their","them","then","than","you","our","out","not","but","all",
    "can","has","had","its","it's","who","how","why","clip","clips","clipping",
    "campaign","views","view","per","thousand","paid","get","content","video",
}
ALIASES = {
    "podcast": {"podcast","podcasts","interview","interviews","show","conversation","talk","episode"},
    "motivation": {"motivation","motivational","inspiration","inspiring","mindset","success","discipline"},
    "reaction": {"reaction","react","reacting","surprise","surprised","emotional","emotion"},
    "car": {"car","cars","vehicle","vehicles","auto","automotive","ride"},
    "giveaway": {"giveaway","gift","donate","donation","charity","help","helping","surprise"},
    "music": {"music","song","songs","artist","artists","track","concert"},
    "gaming": {"gaming","game","games","gamer","streamer","twitch","kick","roblox"},
    "finance": {"finance","money","investing","investment","stocks","trading","wealth"},
    "entertainment": {"entertainment","viral","funny","comedy","celebrity","creator"},
}

def load(path):
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)

def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def tokens(text):
    raw = re.findall(r"[a-z0-9]+", str(text or "").lower())
    out = set()
    for word in raw:
        if len(word) < 3 or word in STOP:
            continue
        out.add(word)
        for concept, words in ALIASES.items():
            if word in words:
                out.add(concept)
    return out

def clip_text(clip):
    hook = clip.get("hook", {}) if isinstance(clip.get("hook"), dict) else {}
    intelligence = clip.get("intelligence", {}) if isinstance(clip.get("intelligence"), dict) else {}
    return " ".join([
        str(hook.get("text", "")), str(clip.get("caption", "")), str(clip.get("title", "")),
        str(clip.get("seo_keywords", "")), str(clip.get("content_type", "")),
        str(intelligence.get("strengths", "")),
    ])

def campaign_text(campaign):
    req = campaign.get("content_requirements", {}) if isinstance(campaign.get("content_requirements"), dict) else {}
    return " ".join([
        str(campaign.get("name", "")), str(campaign.get("source_platform", "")),
        str(campaign.get("content_type", "")), str(campaign.get("description", "")),
        str(campaign.get("raw_text", "")), " ".join(map(str, campaign.get("platforms", []) or [])),
        " ".join(map(str, req.get("content_focus", []) or [])), str(req.get("featured_person", "")),
    ])

def cosine(a, b, idf):
    common = a.keys() & b.keys()
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] * idf.get(k, 1.0) ** 2 for k in common)
    na = math.sqrt(sum((v * idf.get(k, 1.0)) ** 2 for k, v in a.items()))
    nb = math.sqrt(sum((v * idf.get(k, 1.0)) ** 2 for k, v in b.items()))
    return dot / (na * nb) if na and nb else 0.0

def vector(text):
    return Counter(tokens(text))

def hard_requirements(clip, campaign):
    req = campaign.get("content_requirements", {}) if isinstance(campaign.get("content_requirements"), dict) else {}
    text = clip_text(clip).lower()
    reasons = []
    penalty = 0
    featured = req.get("featured_person")
    if featured and str(featured).lower() not in text:
        penalty -= 35
        reasons.append(f"required person not detected: {featured}")
    if req.get("warren_zeiders_must_be_present"):
        if not ("warren zeiders" in text or ("warren" in text and "zeiders" in text)):
            penalty -= 40
            reasons.append("Warren Zeiders requirement not detected")
    focus = [str(x).lower() for x in req.get("content_focus", []) or []]
    focus_hits = [x for x in focus if any(t in text for t in tokens(x))]
    if focus and not focus_hits:
        penalty -= 10
        reasons.append("configured campaign focus not detected")
    if req.get("positive_philanthropy_context"):
        positive = ("giveaway","gift","family","car","help","helping","surprise","donat","charity","philanthrop")
        if any(x in text for x in positive):
            reasons.append("positive/giveaway context detected")
        else:
            penalty -= 10
            reasons.append("positive/giveaway context not detected")
    if req.get("opening_hook_required"):
        hook_score = clip.get("hook", {}).get("score") if isinstance(clip.get("hook"), dict) else None
        if not isinstance(hook_score, (int,float)) or hook_score < 6:
            penalty -= 8
            reasons.append("opening hook evidence is weak")
    return penalty, reasons

def match_score(clip, campaign, idf):
    cv = vector(clip_text(clip)); campv = vector(campaign_text(campaign))
    similarity = cosine(cv, campv, idf)
    score = int(round(min(40, similarity * 80)))
    reasons = [f"content similarity {similarity:.2f}"]
    overlap = len(set(cv) & set(campv))
    if overlap:
        score += min(20, overlap * 2)
        reasons.append(f"{overlap} shared concepts/terms")
    intelligence = clip.get("intelligence", {})
    base = int(intelligence.get("score", 0) or 0)
    score += round(base * 0.30)
    if intelligence.get("decision") == "ready": reasons.append("clip already marked ready")
    elif intelligence.get("decision") == "review": reasons.append("clip needs review")
    else: reasons.append("clip is on hold")
    rate = campaign.get("rate")
    if isinstance(rate, (int,float)):
        if rate >= 5: score += 15; reasons.append(f"high payout ${rate:g}/1K")
        elif rate >= 2: score += 8; reasons.append(f"payout ${rate:g}/1K")
    if campaign.get("budget_left") and campaign["budget_left"] > 0:
        score += 5; reasons.append("budget remains")
    penalty, hard_reasons = hard_requirements(clip, campaign)
    score = max(0, min(100, int(score + penalty))); reasons.extend(hard_reasons)
    return score, reasons

def main():
    if len(sys.argv) not in (3,4):
        raise SystemExit("Usage: semantic_campaign_matcher.py <campaign-radar/latest.json> <posting_package.json> [output.json]")
    radar = load(sys.argv[1]); package = load(sys.argv[2])
    output = Path(sys.argv[3]) if len(sys.argv) == 4 else Path("output/campaign_opportunities/opportunities.json")
    campaigns = radar.get("campaigns", []) if isinstance(radar, dict) else []
    clips = package.get("clips", []) if isinstance(package, dict) else []
    docs = [tokens(campaign_text(c)) for c in campaigns] + [tokens(clip_text(c)) for c in clips]
    df = Counter(); n = max(1, len(docs))
    for doc in docs:
        for term in doc: df[term] += 1
    idf = {term: math.log((n + 1) / (count + 1)) + 1.0 for term, count in df.items()}
    opportunities = []
    for campaign in campaigns:
        best = []
        for clip in clips:
            score, reasons = match_score(clip, campaign, idf)
            best.append({"clip": clip.get("filename"), "score": score, "decision": clip.get("intelligence", {}).get("decision", "unknown"), "reasons": reasons})
        best.sort(key=lambda x: x["score"], reverse=True)
        if best:
            top = best[0]
            action = "post_ready_clip" if top["decision"] == "ready" and top["score"] >= 80 else "review_match"
            opportunities.append({"campaign": campaign, "best_matches": best[:5], "opportunity_score": top["score"], "recommended_action": action})
    opportunities.sort(key=lambda x: x["opportunity_score"], reverse=True)
    save(output, {"generated_at": datetime.now(timezone.utc).isoformat(), "matcher": "free_local_content_similarity_v1", "source_campaigns": len(campaigns), "source_clips": len(clips), "opportunities": opportunities, "next_actions": ["Use the highest-scoring campaign/clip pair first.", "Never auto-submit a HOLD clip.", "Verify campaign terms immediately before submission.", "Record public post URL and performance after publishing."]})
    print(f"Semantic campaign opportunities: {len(opportunities)}")
    for item in opportunities[:10]: print(f"- [{item['opportunity_score']}] {item['campaign'].get('name')} -> {item['best_matches'][0]['clip']}")

if __name__ == "__main__": main()
