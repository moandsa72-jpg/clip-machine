#!/usr/bin/env python3
"""Read-only, zero-cost campaign radar using the public Content Rewards Discover page."""

import html
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "campaign-radar" / "config.json"


class CampaignLinkParser(HTMLParser):
    """Collect public campaign-detail links and their visible text."""

    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attrs = dict(attrs)
        href = attrs.get("href", "")
        if "/discover/" in href and href.rstrip("/").split("/")[-1] != "discover":
            self._href = href
            self._parts = []

    def handle_data(self, data):
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            text = " ".join(" ".join(self._parts).split())
            if text:
                self.links.append((self._href, html.unescape(text)))
            self._href = None
            self._parts = []


def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def fetch_page(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "clip-machine-campaign-radar/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def money(value):
    value = value.strip().replace(",", "")
    multiplier = 1
    if value.lower().endswith("k"):
        multiplier = 1000
        value = value[:-1]
    if value.lower().endswith("m"):
        multiplier = 1000000
        value = value[:-1]
    try:
        return float(value) * multiplier
    except ValueError:
        return None


def parse_campaign(url, text):
    # Campaign cards expose compact public data such as:
    # "Clip Farm·2d Backyard Breaks$64.8K/$70.2K296$2/1K"
    rate_match = re.search(r"\$([\d.,]+(?:[kKmM])?)(?:\s*)/(?:1K|1,000)", text)
    budget_match = re.search(
        r"\$([\d.,]+(?:[kKmM])?)\s*/\s*\$([\d.,]+(?:[kKmM])?)",
        text,
    )
    if not rate_match:
        pool_match = re.search(r"\$([\d.,]+(?:[kKmM])?)\s+pool", text, re.I)
        rate = None
    else:
        rate = money(rate_match.group(1))
        pool_match = None

    budget_spent = money(budget_match.group(1)) if budget_match else None
    budget_total = money(budget_match.group(2)) if budget_match else None
    if pool_match:
        budget_total = money(pool_match.group(1))
        budget_spent = None

    clean = re.sub(r"\s+", " ", text).strip()
    # Remove the leading creator/agency and age when the card provides them.
    clean = re.sub(r"^[^·]+·(?:today|\d+[dwmy])\s+", "", clean, flags=re.I)
    # Remove compact financial/stat fields from the end to isolate the campaign name.
    name = re.sub(r"\$[\d.,]+(?:[kKmM])?\s*/\s*\$[\d.,]+(?:[kKmM])?.*$", "", clean).strip()
    name = re.sub(r"\$[\d.,]+(?:[kKmM])?\s+pool.*$", "", name, flags=re.I).strip()
    if not name:
        name = clean

    campaign_url = urllib.parse.urljoin("https://contentrewards.com/", url)
    return {
        "id": campaign_url.rstrip("/").split("/")[-1],
        "name": name,
        "url": campaign_url,
        "raw": clean,
        "rate": rate,
        "budget_total": budget_total,
        "budget_spent": budget_spent,
        "budget_left": (
            max(0, budget_total - budget_spent)
            if budget_total is not None and budget_spent is not None
            else budget_total
        ),
    }


def score_campaign(campaign, rules):
    score = 0
    reasons = []

    rate = campaign.get("rate")
    if isinstance(rate, (int, float)):
        if rate >= 3:
            score += 40
            reasons.append(f"strong rate ${rate:g}/1K")
        elif rate >= rules["minimum_rate_usd_per_1k"]:
            score += 25
            reasons.append(f"rate ${rate:g}/1K")
        else:
            reasons.append(f"low rate ${rate:g}/1K")

    text = campaign.get("name", "").lower()
    preferred_terms = set(rules["preferred_categories"] + rules["preferred_tags"])
    matches = sorted(term for term in preferred_terms if term.lower() in text)
    if matches:
        score += min(25, len(matches) * 5)
        reasons.append("matches clipping/podcast focus")

    if campaign.get("budget_left", 0) > 0:
        score += 10
        reasons.append("budget remains")

    if campaign.get("budget_left") and campaign.get("budget_total"):
        remaining_ratio = campaign["budget_left"] / campaign["budget_total"]
        if remaining_ratio >= 0.5:
            score += 10
            reasons.append("at least half the budget remains")

    if any(term in text for term in ("podcast", "interview", "show", "creator", "talk")):
        score += 15
        reasons.append("good fit for spoken-content clipping")

    return min(100, int(score)), reasons


def normalize(campaign, rules):
    score, reasons = score_campaign(campaign, rules)
    return {
        "id": campaign["id"],
        "name": campaign["name"],
        "url": campaign["url"],
        "source_platform": "Content Rewards",
        "content_type": "clipping",
        "rate": campaign["rate"],
        "budget": campaign["budget_total"],
        "budget_left": campaign["budget_left"],
        "opportunity_score": score,
        "reasons": reasons,
    }


def main():
    config = load_config()
    source = config["source"]
    rules = config["scoring"]

    params = source.get("query", {})
    query = urllib.parse.urlencode(params)
    url = source["discover_url"]
    if query:
        url = f"{url}?{query}"

    try:
        page = fetch_page(url)
    except Exception as exc:
        print(f"Campaign radar error: {exc}", file=sys.stderr)
        return 1

    parser = CampaignLinkParser()
    parser.feed(page)

    campaigns = []
    seen = set()
    for campaign_url, text in parser.links:
        campaign = parse_campaign(campaign_url, text)
        if campaign["id"] in seen:
            continue
        seen.add(campaign["id"])
        if campaign["rate"] is None and campaign["budget_total"] is None:
            continue
        campaigns.append(campaign)

    ranked = [normalize(c, rules) for c in campaigns]
    ranked.sort(key=lambda x: x["opportunity_score"], reverse=True)
    selected = [x for x in ranked if x["opportunity_score"] >= rules["minimum_score_to_report"]]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Content Rewards public Discover",
        "source_url": url,
        "scanned": len(ranked),
        "selected": len(selected),
        "campaigns": selected,
    }
    output = ROOT / "campaign-radar" / "latest.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Campaign radar scanned {len(ranked)} public campaigns.")
    print(f"{len(selected)} campaigns passed the current score threshold.")
    for item in selected[:20]:
        print(f"- [{item['opportunity_score']}] {item['name']} | ${item['rate'] or 0:g}/1K | {item['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
