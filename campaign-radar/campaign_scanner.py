#!/usr/bin/env python3
"""Read-only, zero-cost campaign radar using public campaign listings."""

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "campaign-radar" / "config.json"


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



class CampaignCardParser(HTMLParser):
    """Associate text and links within one DOM ancestor, never across sibling cards."""
    VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self):
        super().__init__()
        self.stack = []
        self.cards = []

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "parts": []}
        self.stack.append(node)
        if tag in self.VOID_TAGS:
            self.stack.pop()

    def handle_startendtag(self, tag, attrs):
        return

    def handle_data(self, data):
        for node in self.stack:
            if node["tag"] not in {"script", "style", "noscript"}:
                node["parts"].append(data)

    def handle_endtag(self, tag):
        idx = next((i for i in range(len(self.stack) - 1, -1, -1)
                    if self.stack[i]["tag"] == tag), None)
        if idx is None:
            return
        closed = self.stack[idx:]
        if tag == "a":
            href = closed[-1]["attrs"].get("href", "")
            anchor_text = " ".join(" ".join(closed[-1]["parts"]).split())
            if href:
                for parent in reversed(self.stack[:idx]):
                    blob = " ".join(" ".join(parent["parts"]).split())
                    attrs = parent["attrs"]
                    marker = " ".join([str(attrs.get("class", "")), str(attrs.get("id", ""))]).lower()
                    if not re.search(r"(?:campaign|offer|listing|result|opportunit|card|tile|item)", marker):
                        continue
                    rate_markers = re.findall(
                        r"\$[\d.,]+(?:[kKmM])?(?:\s*[–-]\s*\$[\d.,]+(?:[kKmM])?)?\s*/\s*(?:1K|1,000|1000|1M)",
                        blob, re.I
                    )
                    if len(rate_markers) != 1:
                        continue
                    title = clean_name(anchor_text)
                    if len(title) >= 3 and not ARTIFACT_NAME_RE.search(title):
                        self.cards.append({"href": href, "anchor_text": anchor_text, "text": blob, "name": title})
                        break
        del self.stack[idx:]


def parse_campaign_cards(page, base_url, source, rules):
    parser = CampaignCardParser()
    parser.feed(page)
    campaigns = []
    for card in parser.cards:
        full_url = urllib.parse.urljoin(base_url, card["href"])
        if full_url.rstrip("/") == base_url.rstrip("/"):
            continue
        if is_campaign_url(full_url):
            continue
        rate = parse_rate(card["text"])
        if rate is None:
            continue
        name = card["name"]
        name = re.split(
            r"\$[\d.,]+(?:[kKmM])?(?:\s*[–-]\s*\$[\d.,]+(?:[kKmM])?)?\s*/\s*(?:1K|1,000|1000|1M)",
            name, maxsplit=1, flags=re.I
        )[0].strip(" -|:")
        name = re.sub(r"^(?:brand|streamer|creator)\s+", "", name, flags=re.I).strip()
        if len(name) < 3:
            continue
        campaigns.append(normalize(make_campaign(
            name, full_url, source, card["text"], rate, None
        ), rules))
    return campaigns


def load_config(path=None):
    config_path = Path(path) if path else CONFIG_PATH
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    return json.loads(config_path.read_text(encoding="utf-8"))


def fetch_page(url, attempts=3):
    last_error = None
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; clip-machine-free-campaign-radar/3.0)",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8",
            "Cache-Control": "no-cache",
        })
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 429 or attempt == attempts - 1:
                raise
            retry_after = exc.headers.get("Retry-After")
            try:
                delay = min(15, max(2, int(retry_after))) if retry_after else 2 ** attempt
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
    pattern = re.compile(r"\$([\d.,]+(?:[kKmM])?)(?:\s*[–-]\s*\$([\d.,]+(?:[kKmM])?))?\s*/\s*(?:1K|1,000|1000|1M)", re.I)
    values = []
    for low, high in pattern.findall(text):
        value = money(high or low)
        if value is not None:
            if re.search(r"/\s*1M\b", text, re.I):
                value /= 1000
            values.append(value)
    return max(values) if values else None


def parse_budgets(text):
    total_patterns = (
        r"(?:total\s+)?budget\s*(?:of|is|:|-)\s*\$([\d.,]+(?:[kKmM])?)",
        r"\$([\d.,]+(?:[kKmM])?)\s+(?:total\s+)?budget\b",
        r"\$([\d.,]+(?:[kKmM])?)\s+pool\b",
    )
    left_patterns = (
        r"(?:budget\s*)?(?:left|remaining)\s*[:\-]?\s*\$([\d.,]+(?:[kKmM])?)",
        r"\$([\d.,]+(?:[kKmM])?)\s+(?:budget\s*)?(?:left|remaining)\b",
    )
    def extract(patterns):
        values = [money(value) for pattern in patterns for value in re.findall(pattern, text, re.I)]
        values = [value for value in values if value is not None]
        return max(values) if values else None
    return extract(total_patterns), extract(left_patterns)


def parse_budget_left_percent(text):
    patterns = (
        r"(?:budget\s*)?(?:left|remaining)\s*[:\-]?\s*(\d{1,3}(?:\.\d+)?)\s*%",
        r"(\d{1,3}(?:\.\d+)?)\s*%\s*(?:budget\s*)?(?:left|remaining)",
    )
    values = []
    for pattern in patterns:
        values.extend(float(value) for value in re.findall(pattern, text, re.I))
    values = [value for value in values if 0 <= value <= 100]
    return max(values) if values else None


def is_campaign_url(url):
    path = urllib.parse.urlparse(url).path.lower().rstrip("/")
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    blocked = (
        "/signup", "/sign-up", "/start", "/login", "/register", "/contact",
        "/affiliates", "/affiliate", "/about", "/pricing", "/privacy",
        "/terms", "/blog", "/discover", "/campaigns", "/dashboard",
        "/streamer-clipping-campaigns",
    )
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        return True
    return any(path == token or path.startswith(token + "/") for token in blocked)


ARTIFACT_NAME_RE = re.compile(
    r"@keyframes|@media|@supports|@context|schema\.org|FAQPage|data-hero-frame|"
    r"<!doctype|<html|<script|application/ld\+json|^\s*(?:\{|\[)",
    re.I,
)


def validate_campaign(campaign):
    name = str(campaign.get("name") or "").strip()
    url = str(campaign.get("url") or "")
    raw = str(campaign.get("raw_text") or "")
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if len(name) < 3 or ARTIFACT_NAME_RE.search(name):
        return "rejected", "name looks like CSS, JSON-LD, markup, or page boilerplate"
    if is_campaign_url(url):
        return "rejected", "URL is a signup, marketing, dashboard, or video page"
    if host.endswith("contentrewards.com"):
        if not re.search(r"/c/campaigns/[0-9a-f-]{20,}", urllib.parse.urlparse(url).path, re.I):
            return "rejected", "Content Rewards URL is not an individual campaign UUID"
    elif not re.search(r"/(?:campaign|campaigns|clip|clipping|offer|opportunit|[0-9a-f]{8}-[0-9a-f-]{20,})(?:/|$)", urllib.parse.urlparse(url).path, re.I):
        return "rejected", "URL does not resemble an individual campaign or offer"
    if re.search(r"@keyframes|@media|@supports|data-hero-frame|<!doctype|<html|<script", raw, re.I):
        return "rejected", "raw text contains CSS or HTML artifacts"
    rates = re.findall(r"\$[\d.,]+(?:[kKmM])?(?:\s*[–-]\s*\$[\d.,]+(?:[kKmM])?)?\s*/\s*(?:1K|1,000|1000|1M)", raw, re.I)
    if len(rates) != 1:
        return "low_confidence", "raw text does not contain exactly one payout rate"
    rate = campaign.get("rate")
    if rate is None or parse_rate(raw) != rate:
        return "low_confidence", "selected payout rate does not match campaign text"
    return "valid", None


def parse_platforms(text):
    lowered = text.lower()
    return [name for name in ("youtube", "instagram", "tiktok", "facebook", "snapchat", "x") if name in lowered]


def clean_name(text):
    text = re.sub(r"\$[\d.,]+(?:[kKmM])?(?:\s*[–-]\s*\$[\d.,]+(?:[kKmM])?)?\s*/\s*(?:1K|1,000|1000|1M).*$", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\b(?:verified|image|join campaign|campaign details|views?)\b", " ", text, flags=re.I)
    return text.strip(" -|:")[:240]


def make_campaign(name, url, source, text, rate, budget_left=None):
    budget, explicit_budget_left = parse_budgets(text)
    if explicit_budget_left is not None:
        budget_left = explicit_budget_left
    canonical_url = urllib.parse.urlunsplit(urllib.parse.urlsplit(url)._replace(query="", fragment="")).rstrip("/")
    stable_key = f"{source}|{canonical_url.lower()}"
    campaign_id = f"{source.lower().replace(' ', '-')}-{__import__('hashlib').sha256(stable_key.encode('utf-8')).hexdigest()[:12]}"
    return {
        "id": campaign_id,
        "name": name.strip()[:240],
        "url": url,
        "source_platform": source,
        "content_type": "clipping",
        "rate": rate,
        "budget": budget,
        "budget_left": budget_left,
        "budget_left_percent": parse_budget_left_percent(text),
        "platforms": parse_platforms(text),
        "description": text[:1200],
        "raw_text": text[:2400],
        "discovered_by": "free_public_html",
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }


def score_campaign(campaign, rules):
    if not campaign.get("url") or is_campaign_url(campaign["url"]):
        return 0, ["not an actionable campaign URL"]
    if not isinstance(campaign.get("rate"), (int, float)) or campaign["rate"] <= 0:
        return 0, ["missing or invalid payout rate"]
    score = 0
    reasons = []
    rate = campaign.get("rate")
    if isinstance(rate, (int, float)):
        if rate >= rules.get("minimum_rate_usd_per_1k", 0):
            score += 40
            reasons.append("meets payout floor")
        else:
            reasons.append("below payout floor")
    if campaign.get("budget"):
        score += 20
        reasons.append("has total budget")
    if campaign.get("budget_left"):
        score += 10
        reasons.append("has explicit remaining budget")
    if campaign.get("budget_left_percent") is not None:
        score += 10
        reasons.append("has explicit remaining-budget percent")
    if campaign.get("platforms"):
        score += 10
        reasons.append("platform identified")
    if campaign.get("description") and len(campaign["description"]) >= 80:
        score += 10
        reasons.append("has useful description")
    return score, reasons


def normalize(campaign, rules):
    validation_status, rejection_reason = validate_campaign(campaign)
    score, reasons = score_campaign(campaign, rules)
    campaign["validation_status"] = validation_status
    campaign["validation_reason"] = rejection_reason
    campaign["confidence"] = "high" if validation_status == "valid" and score >= rules.get("minimum_score_to_report", 0) else ("medium" if validation_status == "valid" else "low")
    campaign["score"] = score
    campaign["score_reasons"] = reasons
    return campaign


def parse_anchors(page, base_url, source, rules):
    parser = LinkParser()
    parser.feed(page)
    campaigns = []
    for href, text in parser.links:
        full_url = urllib.parse.urljoin(base_url, href)
        rate = parse_rate(text)
        if rate is None or is_campaign_url(full_url):
            continue
        name = clean_name(text)
        if len(name) < 3:
            continue
        campaigns.append(normalize(make_campaign(name, full_url, source, text, rate, None), rules))
    return campaigns


def parse_visible(page, base_url, source, rules):
    text = " ".join(LinkParser().feed(page) or [])
    parser = LinkParser()
    parser.feed(page)
    blob = " ".join(parser.text_parts)
    rate = parse_rate(blob)
    if rate is None:
        return []
    name = clean_name(blob)
    if len(name) < 3:
        return []
    return [normalize(make_campaign(name, base_url, source, blob, rate, None), rules)]


def parse_json_scripts(page, base_url, source, rules):
    parser = HTMLParser()
    parser.feed(page)
    blobs = re.findall(r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", page, re.I | re.S)
    campaigns = []
    for blob in blobs:
        rate = parse_rate(blob)
        if rate is None:
            continue
        name_match = re.search(r"(?:campaign|name|title)\"?\s*:\s*\"([^\"]+)\"", blob, re.I)
        name = clean_name(name_match.group(1) if name_match else "Campaign")
        url_match = re.search(r"(?:url|@id)\"?\s*:\s*\"([^\"]+)\"", blob, re.I)
        url = urllib.parse.urljoin(base_url, url_match.group(1)) if url_match else base_url
        if is_campaign_url(url):
            continue
        campaigns.append(normalize(make_campaign(name, url, source, blob, rate, None), rules))
    return campaigns


def dedupe(campaigns):
    seen = set()
    result = []
    for campaign in campaigns:
        url = campaign.get("url", "")
        parsed = urllib.parse.urlsplit(url)
        canonical = urllib.parse.urlunsplit(parsed._replace(query="", fragment="")).rstrip("/").lower()
        key = canonical or campaign.get("id")
        if key in seen:
            continue
        seen.add(key)
        result.append(campaign)
    return result


def scan_source(source, rules):
    url = source["url"]
    name = source["name"]
    try:
        page = fetch_page(url)
        campaigns = []
        if source.get("parse_json_scripts"):
            campaigns.extend(parse_json_scripts(page, url, name, rules))
        if source.get("parse_cards", True):
            campaigns.extend(parse_campaign_cards(page, url, name, rules))
        if source.get("parse_anchors", True):
            campaigns.extend(parse_anchors(page, url, name, rules))
        if source.get("parse_visible"):
            campaigns.extend(parse_visible(page, url, name, rules))
        campaigns = dedupe(campaigns)
        selected = [c for c in campaigns if c.get("validation_status") == "valid" and c.get("score", 0) >= rules.get("minimum_score_to_report", 0)]
        rejected = [c for c in campaigns if c not in selected]
        return {"source": name, "url": url, "status": "ok", "campaigns": selected, "rejected": rejected, "parsed_count": len(campaigns)}
    except Exception as exc:
        return {"source": name, "url": url, "status": "error", "error": str(exc), "campaigns": [], "rejected": [], "parsed_count": 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--output", default=str(ROOT / "campaign-radar" / "latest.json"))
    args = parser.parse_args()
    config = load_config(args.config)
    rules = config.get("rules", {})
    sources = config.get("sources", [])
    results = [scan_source(source, rules) for source in sources]
    selected = [campaign for result in results for campaign in result.get("campaigns", [])]
    rejected = [campaign for result in results for campaign in result.get("rejected", [])]
    rejection_summary = {}
    for campaign in rejected:
        reason = campaign.get("validation_reason") or "below score threshold"
        rejection_summary[reason] = rejection_summary.get(reason, 0) + 1
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "campaigns": selected,
        "sources": results,
        "rejected_candidates": len(rejected),
        "rejection_summary": rejection_summary,
        "rejected_examples": rejected[:25],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Campaign radar scanned {len(selected)} public campaigns across {len(sources)} sources.")
    print(f"{len(rejected)} candidates were rejected or below the current score threshold.")


if __name__ == "__main__":
    main()
