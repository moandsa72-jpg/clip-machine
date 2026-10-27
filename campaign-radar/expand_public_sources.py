#!/usr/bin/env python3
"""Expand the free campaign radar with additional public clipping marketplaces.

Read-only: fetches public pages only, no login, API key, paid service, or account access.
"""

import hashlib
import html
import json
import re
import time
import urllib.error
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
        self.text_parts = []
        self._href = None
        self._parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            href = attrs.get("href", "")
            if href:
                self._href = href
                self._parts = []
        elif tag not in {"script", "style", "noscript"}:
            self.text_parts.append(" ")

    def handle_data(self, data):
        if self._href is not None:
            self._parts.append(data)
        self.text_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            text = " ".join(" ".join(self._parts).split())
            if text:
                self.links.append((self._href, html.unescape(text)))
            self._href = None
            self._parts = []


def fetch_page(url, attempts=3):
    last_error = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; clip-machine-free-campaign-radar/2.0)",
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.8",
                "Cache-Control": "no-cache",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 429 or attempt == attempts - 1:
                raise
            retry_after = exc.headers.get("Retry-After")
            try:
                delay = min(12, max(2, int(retry_after))) if retry_after else 2 ** attempt
            except ValueError:
                delay = 2 ** attempt
            time.sleep(delay)
    raise last_error


def money(value):
    value = str(value).strip().replace(",", "")
    multiplier = 1
    if value.lower().endswith("k"):
        multiplier = 1000
        value = value[:-1]
    elif value.lower().endswith("m"):
        multiplier = 1000000
        value = value[:-1]
    try:
        return float(value) * multiplier
    except (TypeError, ValueError):
        return None


def parse_rate(text):
    patterns = [
        r"\$([\d.,]+(?:[kKmM])?)\s*/\s*(?:1K|1,000|per\s+1K|per\s+1,000)",
        r"\$([\d.,]+(?:[kKmM])?)\s*/\s*(?:per\s+)?1M",
        r"\$([\d.,]+(?:[kKmM])?)\s*/\s*(?:per\s+)?1000",
    ]
    values = []
    for pattern in patterns:
        for value in re.findall(pattern, text, re.I):
            parsed = money(value)
            if parsed is not None:
                if re.search(r"/\s*(?:per\s+)?1M", text, re.I):
                    parsed /= 1000
                values.append(parsed)
    return max(values) if values else None


def parse_budget(text):
    match = re.search(
        r"(?:budget\s*(?:left|remaining)?|left)\s*[:\-]?\s*\$([\d.,]+(?:[kKmM])?)",
        text,
        re.I,
    )
    if match:
        return money(match.group(1))
    return None


def parse_platforms(text):
    lowered = text.lower()
    platforms = []
    for name in ("youtube", "instagram", "tiktok", "facebook", "snapchat", "x"):
        if name in lowered:
            platforms.append(name)
    return platforms


def make_campaign(name, url, source, text, rate, budget_left=None):
    stable_key = f"{source}|{name.strip().lower()}|{url}"
    campaign_id = f"{source.lower().replace(' ', '-')}-{hashlib.sha256(stable_key.encode('utf-8')).hexdigest()[:12]}"
    return {
        "id": campaign_id,
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
    text = re.sub(r"\$[\d.,]+(?:[kKmM])?\s*/\s*(?:1K|1,000|per\s+1K|per\s+1,000|per\s+1M|1M|1000).*$", "", text, flags=re.I)
    text = re.sub(r"\b(?:paid out|rate|platforms|campaign details|image|views?)\b", " ", text, flags=re.I)
    return " ".join(text.split()).strip(" -|:")


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


def iter_json_values(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_json_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_json_values(child)


def extract_json_scripts(page):
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", page, flags=re.I | re.S)
    values = []
    for raw in scripts:
        text = html.unescape(raw).strip()
        if not text or len(text) > 5_000_000:
            continue
        candidates = [text]
        if text.startswith("<![CDATA[") and text.endswith("]]>"):
            candidates.append(text[9:-3])
        for candidate in candidates:
            try:
                values.append(json.loads(candidate))
            except (json.JSONDecodeError, TypeError):
                continue
    return values


def first_string(item, keys):
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def first_number(item, keys):
    for key in keys:
        value = item.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            parsed = parse_rate(value)
            if parsed is not None:
                return parsed
            parsed = money(value)
            if parsed is not None and parsed > 0:
                return parsed
    return None


def parse_embedded_campaigns(page, base_url, source):
    campaigns = []
    seen = set()
    for root in extract_json_scripts(page):
        for item in iter_json_values(root):
            name = first_string(item, ("name", "title", "campaignName", "campaign_name", "displayName"))
            if not name or len(name) < 3:
                continue
            raw_blob = json.dumps(item, ensure_ascii=False)
            rate = parse_rate(raw_blob)
            if rate is None:
                rate = first_number(item, ("rate", "rpm", "cpm", "payout", "payPerThousand", "ratePer1k"))
            if rate is None:
                continue
            url = first_string(item, ("url", "link", "href", "campaignUrl", "campaign_url"))
            if not url:
                url = base_url
            url = urllib.parse.urljoin(base_url, url)
            text = f"{name} {raw_blob}"
            key = (source, name.lower(), rate, url)
            if key in seen:
                continue
            seen.add(key)
            campaigns.append(make_campaign(name, url, source, text, rate, parse_budget(raw_blob)))
    return campaigns


def parse_visible_campaigns(page, base_url, source):
    parser = LinkParser()
    parser.feed(page)
    text = html.unescape(" ".join(parser.text_parts))
    text = re.sub(r"\s+", " ", text)
    campaigns = []
    seen = set()
    pattern = re.compile(
        r"(?P<name>[A-Za-z0-9][^$|]{2,180}?)\s+\$(?P<rate>[\d.,]+(?:[kKmM])?)\s*/\s*(?P<unit>1K|1,000|1M|1000)\s+views?(?P<tail>.{0,220})",
        re.I,
    )
    for match in pattern.finditer(text):
        rate = money(match.group("rate"))
        if rate is None:
            continue
        if match.group("unit").lower() == "1m":
            rate /= 1000
        name = campaign_name(match.group("name"))
        if not name or len(name) < 3:
            continue
        blob = match.group(0)
        if source != "ClipRadar" and "clip" not in blob.lower() and "campaign" not in blob.lower():
            continue
        key = (source, name.lower(), rate)
        if key in seen:
            continue
        seen.add(key)
        campaigns.append(make_campaign(name, base_url, source, blob, rate, parse_budget(blob)))
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
        ("Clipster", "https://www.clipster.com/discover"),
        ("CLIPPING.net", "https://clipping.net/"),
        ("ClipRadar", "https://www.clipradar.co/"),
    ]
    errors = [error for error in report.get("errors", []) if not error.startswith(("Clipster:", "CLIPPING.net:", "ClipRadar:"))]
    added = []
    for source, url in sources:
        try:
            page = fetch_page(url)
            items = []
            items.extend(parse_anchor_campaigns(page, url, source, require_clipping=(source != "ClipRadar")))
            items.extend(parse_embedded_campaigns(page, url, source))
            items.extend(parse_visible_campaigns(page, url, source))
            deduped = {}
            for item in items:
                deduped[(item["name"].lower(), item["rate"], item["url"])] = item
            added.extend(deduped.values())
            print(f"{source}: found {len(deduped)} public campaigns")
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
            "parsing": ["anchors", "embedded_json", "visible_text"],
        },
    })
    LATEST_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Expanded free radar coverage: {len(merged)} campaigns, {len(selected)} selected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
