#!/usr/bin/env python3
"""Conservative free local campaign/clip matcher."""
import json, math, re, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
STOP=set("the and that this with from have what when your they just about into for are was were been will would could there their them then than you our out not but all can has had its who how why clip clips clipping campaign views view per thousand paid get content video".split())
ALIASES={"podcast":{"podcast","podcasts","interview","interviews","show","conversation","talk","episode"},"motivation":{"motivation","motivational","inspiration","inspiring","mindset","success","discipline"},"reaction":{"reaction","react","reacting","surprise","surprised","emotional","emotion"},"car":{"car","cars","vehicle","vehicles","auto","automotive","ride","handoff"},"giveaway":{"giveaway","gift","donate","donation","charity","help","helping","surprise","family"},"music":{"music","song","songs","artist","artists","track","concert"},"gaming":{"gaming","game","games","gamer","streamer","twitch","kick","roblox"},"finance":{"finance","money","investing","investment","stocks","trading","wealth"},"entertainment":{"entertainment","viral","funny","comedy","celebrity","creator"}}
MIN_MATCH_SCORE=60
MIN_SIMILARITY=0.12

def load(path):
    with Path(path).open(encoding="utf-8") as f: return json.load(f)
def save(path,data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def tokens(text):
    out=set()
    for word in re.findall(r"[a-z0-9]+",str(text or "").lower()):
        if len(word)<3 or word in STOP: continue
        out.add(word)
        for concept,words in ALIASES.items():
            if word in words: out.add(concept)
    return out
def clip_text(c):
    hook=c.get("hook",{}) if isinstance(c.get("hook"),dict) else {}; intel=c.get("intelligence",{}) if isinstance(c.get("intelligence"),dict) else {}
    return " ".join(map(str,[hook.get("text",""),c.get("caption",""),c.get("title",""),c.get("seo_keywords",""),c.get("content_type",""),intel.get("strengths",""),c.get("transcript_excerpt","")]))
def campaign_text(c):
    req=c.get("content_requirements",{}) if isinstance(c.get("content_requirements"),dict) else {}
    return " ".join([str(c.get(k,"")) for k in ("name","source_platform","content_type","description","raw_text")]+[" ".join(map(str,c.get("platforms",[]) or []))," ".join(map(str,req.get("content_focus",[]) or [])),str(req.get("featured_person",""))])
def cosine(a,b,idf):
    common=a.keys() & b.keys()
    if not common: return 0.0
    dot=sum(a[k]*b[k]*idf.get(k,1.0)**2 for k in common); na=math.sqrt(sum((v*idf.get(k,1.0))**2 for k,v in a.items())); nb=math.sqrt(sum((v*idf.get(k,1.0))**2 for k,v in b.items()))
    return dot/(na*nb) if na and nb else 0.0
def actionable(c):
    name=str(c.get("name","")).strip(); u=urlparse(str(c.get("url","")).strip())
    return len(name)>=5 and u.scheme=="https" and bool(u.netloc) and not any(x in name.lower() for x in ("campaign details","join campaign","image image","verified image"))
def requirements(clip,campaign):
    req=campaign.get("content_requirements",{}) if isinstance(campaign.get("content_requirements"),dict) else {}; text=clip_text(clip).lower(); ts=tokens(text); penalty=0; reasons=[]; hard=False
    featured=req.get("featured_person")
    if featured and str(featured).lower() not in text: penalty-=35; hard=True; reasons.append(f"required person not detected: {featured}")
    if req.get("warren_zeiders_must_be_present") and not ("warren zeiders" in text or ("warren" in text and "zeiders" in text)): penalty-=40; hard=True; reasons.append("Warren Zeiders requirement not detected")
    focus=req.get("content_focus",[]) or []
    if focus and not any(ts & tokens(x) for x in focus): penalty-=15; reasons.append("configured campaign focus not detected")
    if req.get("positive_philanthropy_context") and not (ts & {"giveaway","gift","family","car","help","helping","surprise","donation","charity","philanthropy"}): penalty-=10; reasons.append("positive/giveaway context not detected")
    if req.get("opening_hook_required"):
        h=clip.get("hook",{}) if isinstance(clip.get("hook"),dict) else {}
        if not isinstance(h.get("score"),(int,float)) or h["score"]<6 or len(str(h.get("text","")).split()) not in (4,5): penalty-=8; reasons.append("opening hook weak or not 4–5 words")
    return penalty,reasons,hard
def score_match(clip,campaign,idf):
    cv=Counter(tokens(clip_text(clip))); campv=Counter(tokens(campaign_text(campaign))); sim=cosine(cv,campv,idf); score=int(round(min(40,sim*80))); reasons=[f"content similarity {sim:.2f}"]
    overlap=len(cv.keys() & campv.keys()); score+=min(20,overlap*2)
    intel=clip.get("intelligence",{}); decision=intel.get("decision","unknown"); score+=round(int(intel.get("score",0) or 0)*0.30)
    rate=campaign.get("rate")
    if isinstance(rate,(int,float)): score+=10 if rate>=5 else 5 if rate>=2 else 0
    penalty,req_reasons,hard=requirements(clip,campaign); score=max(0,min(100,int(score+penalty))); reasons.extend(req_reasons)
    if sim<MIN_SIMILARITY: reasons.append("rejected: similarity below minimum")
    if hard: reasons.append("rejected: required-person constraint failed")
    if decision=="hold": reasons.append("rejected: clip is on hold")
    eligible=sim>=MIN_SIMILARITY and not hard and decision!="hold" and score>=MIN_MATCH_SCORE
    return score,sim,reasons,eligible,decision
def main():
    if len(sys.argv) not in (3,4): raise SystemExit("Usage: semantic_campaign_matcher.py <radar.json> <posting_package.json> [output.json]")
    radar=load(sys.argv[1]); package=load(sys.argv[2]); output=Path(sys.argv[3]) if len(sys.argv)==4 else Path("output/campaign_opportunities/opportunities.json")
    raw=radar.get("campaigns",[]) if isinstance(radar,dict) else []; campaigns=[c for c in raw if actionable(c)]; clips=package.get("clips",[]) if isinstance(package,dict) else []
    docs=[tokens(campaign_text(c)) for c in campaigns]+[tokens(clip_text(c)) for c in clips]; df=Counter()
    for d in docs:
        for t in d: df[t]+=1
    n=max(1,len(docs)); idf={t:math.log((n+1)/(count+1))+1 for t,count in df.items()}; opportunities=[]; rejected=[]
    for camp in campaigns:
        matches=[]
        for clip in clips:
            score,sim,reasons,eligible,decision=score_match(clip,camp,idf); row={"campaign":camp.get("name"),"clip":clip.get("filename"),"score":score,"similarity":round(sim,3),"decision":decision,"eligible":eligible,"reasons":reasons}
            if eligible: matches.append({k:v for k,v in row.items() if k!="campaign"})
            else: rejected.append(row)
        matches.sort(key=lambda x:(x["score"],x["similarity"]),reverse=True)
        if matches: opportunities.append({"campaign":camp,"best_matches":matches[:5],"opportunity_score":matches[0]["score"],"recommended_action":"review_match"})
    opportunities.sort(key=lambda x:x["opportunity_score"],reverse=True)
    save(output,{"generated_at":datetime.now(timezone.utc).isoformat(),"matcher":"free_local_content_similarity_v2","minimum_match_score":MIN_MATCH_SCORE,"minimum_similarity":MIN_SIMILARITY,"source_campaigns":len(campaigns),"source_campaigns_rejected":len(raw)-len(campaigns),"source_clips":len(clips),"opportunities":opportunities,"rejected_match_count":len(rejected),"rejected_matches_sample":rejected[:100],"next_actions":["Review only eligible campaign/clip pairs.","Never auto-submit a HOLD clip.","Verify campaign terms before submission.","Record public post URL and performance after publishing."]})
    print(f"Actionable campaigns: {len(campaigns)} / {len(raw)}; eligible opportunities: {len(opportunities)}; rejected candidates: {len(rejected)}")
    for x in opportunities[:10]: print(f"- [{x['opportunity_score']}] {x['campaign'].get('name')} -> {x['best_matches'][0]['clip']}")
if __name__=="__main__": main()
