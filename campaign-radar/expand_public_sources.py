#!/usr/bin/env python3
"""Expand the free campaign radar with additional public clipping marketplaces.

Read-only: fetches public pages only, no login, API key, paid service, or account access.
"""

import html
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "campaign-radar" / "config.json"
LATEST_PATH = ROOT / "campaign-radar" / "latest.json"


class LinkParser(HTMLParser):
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


def fetch_page(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "clip-machine-free-campaign-radar/1.0",
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
    patterns = [
        r"\$([\d.,]+(?:[kKmM])?)\s*/\s*(?:1K|1,000)",
        r"\$([\d.,]+(?:[kKmM])?)\s*/\s*(?:per\s+)?1M",
        r"\$([\d.,]+(?:[kKmM])?)\s*/\s*(?:per\s+)?1000",
    ]
    values = []
    for pattern in patterns:
        values.extend(money(value) for value in re.findall(pattern, text, re.I))
    values = [value for value in values if value is not None]
    if not values:
        return None
    value = max(values)
    # Clipster advertises per 1M; convert it to the same $/1K unit used elsewhere.
    if re.search(r"/\s*(?:per\s+)?1M", text, re.I):
        value /= 1000
    return value


def parse_budget(text):
    match = re.search(
        r"(?:budget\s*(?:left)?|left)\s*\$([\d.,]+(?:[kKmM])?)",
        text,
        re.I,
    )
    if match:
        return money(match.group(1))
    match = re.search(
        r"\$([\d.,]+(?:[kKmM])?)\s*/\s*\$([\d.,]+(?:[kKmM])?)",
        text,
        re.I,
    )
    return money(match.group(1)) if match else None


def parse_platforms(text):
    lowered = text.lower()
    platforms = []
    for name in ("youtube", "instagram", "tiktok", "facebook", "snapchat", "x"):
        if name in lowered:
            platforms.append(name)
    return platforms


def make_campaign(name, url, source, text, rate, budget_left=None):
    return {
        "id": f"{source.lower().replace(' ', '-')}-{abs(hash((name, url))) % 10**12}",
        "name": name.strip()[:240],
        "url": url,
        "source_platform": source,
        "content_type": "clipping",
        "rate": rate,
        "budget": None,
        "budget_left": budget_left,
        "platforms": parse_platforms(text),
        "discovered_by": "free_public_html",
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }


def campaign_name(text):
    text = re.sub(r"\$[\d.,]+(?:[kKmM])?\s*/\s*(?:1K|1,000|per\s+1M|1M).*$", "", text, flags=re.I)
    text = re.sub(r"\b(?:paid out|rate|platforms|campaign details|image)\b", " ", text, flags=re.I)
    return " ".join(text.split()).strip()


def parse_anchor_campaigns(page, base_url, source, require_clipping=False):
    parser = LinkParser()
    parser.feed(page)
    campaigns = []
    seen = set()
    for href, text in parser.links:
        full_url = urllib.parse.urljoin(base_url, href)
        lowered_href = full_url.lower()
        lowered_text = text.lower()
        if require_clipping and "clipping" not in lowered_text and "campaign" not in lowered_text:
            continue
        if source == "Clipster" and "/discover" not in lowered_href:
            continue
        if source == "CLIPPING.net" and "clipping.net" not in lowered_href:
            continue
        if source == "ClipRadar" and "clipradar" not in lowered_href and "campaign" not in lowered_text:
            continue

        rate = parse_rate(text)
        if rate is None:
            continue
        name = campaign_name(text)
        if not name or len(name) < 3:
            continue
        key = (source, name.lower(), rate)
        if key in seen:
            continue
        seen.add(key)
        campaigns.append(make_campaign(name, full_url, source, text, rate, parse_budget(text)))
    return campaigns


def score(item, rules):
    value = 0
    name = item["name"].lower()
    rate = item.get("rate")
    if isinstance(rate, (int, float)):
        if rate >= 3:
            value += 40
        elif rate >= rules["minimum_rate_usd_per_1k"]:
            value += 25
        else:
            value += 5
    preferred = rules["preferred_categories"] + rules["preferred_tags"]
    value += min(25, sum(5 for term in preferred if term.lower() in name))
    if any(term in name for term in ("podcast", "interview", "show", "creator", "talk", "clipping")):
        value += 15
    if item.get("budget_left"):
        value += 10
    return min(100, value)


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    rules = config["scoring"]
    report = json.loads(LATEST_PATH.read_text(encoding="utf-8")) if LATEST_PATH.exists() else {}
    existing = report.get("campaigns", []) + report.get("kick_campaigns", [])
    sources = [
        ("Clipster", "https://www.clipster.gg/discover"),
        ("CLIPPING.net", "https://clipping.net/"),
        ("ClipRadar", "https://www.clipradar.co/"),
    ]
    errors = list(report.get("errors", []))
    added = []
    for source, url in sources:
        try:
            page = fetch_page(url)
            items = parse_anchor_campaigns(page, url, source, require_clipping=(source != "ClipRadar"))
            added.extend(items)
            print(f"{source}: found {len(items)} public campaigns")
        except Exception as exc:
            errors.append(f"{source}: {exc}")
            print(f"{source}: scan failed: {exc}")

    merged = []
    seen = set()
    for item in existing + added:
        key = (item.get("name", "").strip().lower(), item.get("source_platform", ""))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        item["opportunity_score"] = score(item, rules)
        item.setdefault("reasons", [])
        merged.append(item)

    merged.sort(key=lambda item: item.get("opportunity_score", 0), reverse=True)
    selected = [item for item in merged if item.get("opportunity_score", 0) >= rules["minimum_score_to_report"]]
    kick = [item for item in merged if "kick" in item.get("name", "").lower()]
    report.update({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scanned": len(merged),
        "selected": len(selected),
        "campaigns": selected,
        "kick_campaigns": kick,
        "errors": errors,
        "coverage": {
            "direct_public_sources": ["Content Rewards", "Clipster", "CLIPPING.net"],
            "public_aggregator_sources": ["ClipPay", "ClipRadar"],
            "scan_mode": "free_public_html",
        },
    })
    LATEST_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Expanded free radar coverage: {len(merged)} campaigns, {len(selected)} selected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
