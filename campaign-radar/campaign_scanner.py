#!/usr/bin/env python3
"""Read-only, zero-cost campaign radar using public campaign listings."""

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


class LinkParser(HTMLParser):
    """Collect public links and their visible text."""

    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href", "")
        if href:
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
    elif value.lower().endswith("m"):
        multiplier = 1000000
        value = value[:-1]
    try:
        return float(value) * multiplier
    except ValueError:
        return None


def parse_rate(text):
    matches = re.findall(r"\$([\d.,]+(?:[kKmM])?)\s*/\s*(?:1K|1,000)", text)
    values = [money(value) for value in matches]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def parse_budget(text):
    match = re.search(
        r"(?:budget\s*left|left)\s*\$([\d.,]+(?:[kKmM])?)",
        text,
        re.I,
    )
    return money(match.group(1)) if match else None


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
            score += 5
            reasons.append(f"low rate ${rate:g}/1K")

    text = campaign.get("name", "").lower()
    preferred_terms = set(rules["preferred_categories"] + rules["preferred_tags"])
    matches = sorted(term for term in preferred_terms if term.lower() in text)
    if matches:
        score += min(25, len(matches) * 5)
        reasons.append("matches clipping/podcast focus")

    if campaign.get("budget_left") is not None:
        if campaign["budget_left"] > 0:
            score += 10
            reasons.append("budget remains")
        if campaign.get("budget_total") and campaign["budget_total"] > 0:
            if campaign["budget_left"] / campaign["budget_total"] >= 0.5:
                score += 10
                reasons.append("at least half the budget remains")

    if any(term in text for term in ("podcast", "interview", "show", "creator", "talk")):
        score += 15
        reasons.append("good fit for spoken-content clipping")

    if "kick" in text or campaign.get("source_platform") == "Clipping.net":
        score += 5
        reasons.append("Kick/streamer opportunity")

    return min(100, int(score)), reasons


def normalize(campaign, rules):
    score, reasons = score_campaign(campaign, rules)
    return {
        "id": campaign["id"],
        "name": campaign["name"],
        "url": campaign["url"],
        "source_platform": campaign["source_platform"],
        "content_type": "clipping",
        "rate": campaign["rate"],
        "budget": campaign.get("budget_total"),
        "budget_left": campaign.get("budget_left"),
        "opportunity_score": score,
        "reasons": reasons,
    }


def parse_content_rewards(page, rules):
    parser = LinkParser()
    parser.feed(page)
    campaigns = []
    seen = set()
    for url, text in parser.links:
        if "/discover/" not in url:
            continue
        rate = parse_rate(text)
        if rate is None:
            continue
        full_url = urllib.parse.urljoin("https://contentrewards.com/", url)
        campaign_id = full_url.rstrip("/").split("/")[-1]
        if campaign_id in seen:
            continue
        seen.add(campaign_id)
        name = re.sub(r"\$[\d.,]+(?:[kKmM])?\s*/\s*(?:1K|1,000).*$", "", text).strip()
        campaigns.append(normalize({
            "id": campaign_id,
            "name": name or text,
            "url": full_url,
            "source_platform": "Content Rewards",
            "rate": rate,
            "budget_total": None,
            "budget_left": None,
        }, rules))
    return campaigns


def parse_clippay(page, rules):
    """Parse ClipPay's public index, which aggregates multiple campaign networks."""
    parser = LinkParser()
    parser.feed(page)
    campaigns = []
    seen = set()
    for url, text in parser.links:
        rate = parse_rate(text)
        if rate is None or "campaign" not in text.lower() and "clipping" not in text.lower():
            continue

        source = "ClipPay index"
        lowered = text.lower()
        if "clipping.net" in lowered or "kick clipping" in lowered:
            source = "Clipping.net"
        elif "whop content rewards" in lowered:
            source = "Content Rewards"
        elif "vyro" in lowered:
            source = "Vyro"

        full_url = urllib.parse.urljoin("https://getclippay.com/", url)
        campaign_id = full_url.rstrip("/").split("/")[-1] or text
        key = (campaign_id, text)
        if key in seen:
            continue
        seen.add(key)

        name = re.sub(r"\$[\d.,]+(?:[kKmM])?\s*/\s*(?:1K|1,000).*$", "", text).strip()
        budget_left = parse_budget(text)
        campaigns.append(normalize({
            "id": campaign_id,
            "name": name or text,
            "url": full_url,
            "source_platform": source,
            "rate": rate,
            "budget_total": None,
            "budget_left": budget_left,
        }, rules))

    return campaigns


def main():
    config = load_config()
    source = config["source"]
    rules = config["scoring"]

    params = source.get("query", {})
    query = urllib.parse.urlencode(params)
    content_rewards_url = source["discover_url"]
    if query:
        content_rewards_url = f"{content_rewards_url}?{query}"

    sources = [
        ("Content Rewards public Discover", content_rewards_url, parse_content_rewards),
        ("ClipPay public campaign index", config["clip_pay_index_url"], parse_clippay),
    ]

    ranked = []
    seen = set()
    errors = []
    for source_name, url, parser in sources:
        try:
            page = fetch_page(url)
            items = parser(page, rules)
            for item in items:
                key = (item["name"].lower(), item["rate"], item["source_platform"])
                if key in seen:
                    continue
                seen.add(key)
                ranked.append(item)
        except Exception as exc:
            errors.append(f"{source_name}: {exc}")

    ranked.sort(key=lambda x: x["opportunity_score"], reverse=True)
    selected = [x for x in ranked if x["opportunity_score"] >= rules["minimum_score_to_report"]]
    kick = [x for x in ranked if "kick" in x["name"].lower()]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": [url for _, url, _ in sources],
        "scanned": len(ranked),
        "selected": len(selected),
        "kick_campaigns": kick,
        "campaigns": selected,
        "errors": errors,
    }
    output = ROOT / "campaign-radar" / "latest.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Campaign radar scanned {len(ranked)} public campaigns across {len(sources)} sources.")
    print(f"{len(kick)} Kick-related campaigns found.")
    print(f"{len(selected)} campaigns passed the current score threshold.")
    for item in kick[:20]:
        rate = item["rate"]
        rate_text = f"${rate:g}/1K" if rate is not None else "rate not listed"
        print(f"- KICK [{item['opportunity_score']}] {item['name']} | {rate_text} | {item['url']}")
    for item in selected[:20]:
        rate = item["rate"]
        rate_text = f"${rate:g}/1K" if rate is not None else "rate not listed"
        print(f"- [{item['opportunity_score']}] {item['name']} | {rate_text} | {item['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
