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


def load_config(path=None):
    config_path = Path(path) if path else CONFIG_PATH
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    return json.loads(config_path.read_text(encoding="utf-8"))


def fetch_page(url, attempts=3):
    last_error = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; clip-machine-free-campaign-radar/3.0)",
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
    pattern = re.compile(
        r"\$([\d.,]+(?:[kKmM])?)(?:\s*[–-]\s*\$([\d.,]+(?:[kKmM])?))?\s*/\s*(?:1K|1,000|1000|1M)",
        re.I,
    )
    values = []
    for low, high in pattern.findall(text):
        value = money(high or low)
        if value is not None:
            # 1M payouts are normalized to the project's $/1K unit.
            unit_match = re.search(r"/\s*(1M)\b", text, re.I)
            if unit_match:
                value /= 1000
            values.append(value)
    return max(values) if values else None


def parse_budget(text):
    matches = re.findall(
        r"(?:budget\s*(?:left|remaining)?|left|pool)\s*[:\-]?\s*\$([\d.,]+(?:[kKmM])?)",
        text,
        re.I,
    )
    values = [money(x) for x in matches]
    values = [x for x in values if x is not None]
    return max(values) if values else None


def parse_platforms(text):
    lowered = text.lower()
    return [name for name in ("youtube", "instagram", "tiktok", "facebook", "snapchat", "x") if name in lowered]


def clean_name(text):
    text = re.sub(r"\$[\d.,]+(?:[kKmM])?(?:\s*[–-]\s*\$[\d.,]+(?:[kKmM])?)?\s*/\s*(?:1K|1,000|1000|1M).*$", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\b(?:verified|image|join campaign|campaign details|views?)\b", " ", text, flags=re.I)
    return text.strip(" -|:")[:240]


def make_campaign(name, url, source, text, rate, budget_left=None):
    stable_key = f"{source}|{name.strip().lower()}|{url}"
    campaign_id = f"{source.lower().replace(' ', '-')}-{__import__('hashlib').sha256(stable_key.encode('utf-8')).hexdigest()[:12]}"
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
        "description": text[:1200],
        "raw_text": text[:2400],
        "discovered_by": "free_public_html",
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }


def score_campaign(campaign, rules):
    score = 0
    reasons = []
    rate = campaign.get("rate")
    if isinstance(rate, (int, float)):
        if rate >= 3:
            score += 40; reasons.append(f"strong rate ${rate:g}/1K")
        elif rate >= rules["minimum_rate_usd_per_1k"]:
            score += 25; reasons.append(f"rate ${rate:g}/1K")
        else:
            score += 5; reasons.append(f"low rate ${rate:g}/1K")
    text = " ".join([campaign.get("name", ""), campaign.get("description", "")]).lower()
    preferred = rules["preferred_categories"] + rules["preferred_tags"]
    matches = [term for term in preferred if term.lower() in text]
    if matches:
        score += min(25, len(matches) * 5); reasons.append("matches clipping/podcast focus")
    if campaign.get("budget_left") and campaign["budget_left"] > 0:
        score += 10; reasons.append("budget remains")
    if any(term in text for term in ("podcast", "interview", "show", "creator", "talk", "clipping")):
        score += 15; reasons.append("good fit for spoken-content clipping")
    return min(100, int(score)), reasons


def normalize(campaign, rules):
    score, reasons = score_campaign(campaign, rules)
    campaign["opportunity_score"] = score
    campaign["reasons"] = reasons
    return campaign


def parse_anchors(page, base_url, source, rules):
    parser = LinkParser(); parser.feed(page)
    campaigns = []
    for url, text in parser.links:
        rate = parse_rate(text)
        if rate is None:
            continue
        full_url = urllib.parse.urljoin(base_url, url)
        # Only individual detail links are actionable; avoid listing/navigation links.
        if full_url.rstrip("/") == base_url.rstrip("/"):
            continue
        if any(token in full_url.lower() for token in ("/discover", "/campaigns/", "/streamer-clipping-campaigns")):
            continue
        name = clean_name(text)
        if len(name) < 3:
            continue
        campaigns.append(normalize(make_campaign(name, full_url, source, text, rate, parse_budget(text)), rules))
    return campaigns


def parse_visible(page, base_url, source, rules):
    parser = LinkParser(); parser.feed(page)
    visible = re.sub(r"\s+", " ", html.unescape(" ".join(parser.text_parts)))
    campaigns = []
    # Look around every payout marker rather than requiring a specific word such as 'clipping'.
    marker = re.compile(r"\$[\d.,]+(?:[kKmM])?(?:\s*[–-]\s*\$[\d.,]+(?:[kKmM])?)?\s*/\s*(?:1K|1,000|1000|1M)", re.I)
    for match in marker.finditer(visible):
        start = max(0, match.start() - 180)
        end = min(len(visible), match.end() + 180)
        blob = visible[start:end]
        rate = parse_rate(blob)
        if rate is None:
            continue
        prefix = visible[start:match.start()].strip(" |:-")
        parts = re.split(r"[|·•]", prefix)
        name = clean_name(parts[-1] if parts else prefix)
        if len(name) < 3:
            continue
        campaigns.append(normalize(make_campaign(name, base_url, source, blob, rate, parse_budget(blob)), rules))
    return campaigns


def parse_json_scripts(page, base_url, source, rules):
    campaigns = []
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", page, flags=re.I | re.S)
    for raw in scripts:
        raw = html.unescape(raw).strip()
        if not raw or len(raw) > 5_000_000:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                name = next((item.get(k) for k in ("name", "title", "campaignName", "campaign_name", "displayName") if isinstance(item.get(k), str) and item.get(k).strip()), None)
                blob = json.dumps(item, ensure_ascii=False)
                rate = parse_rate(blob)
                if rate is None:
                    for key in ("rate", "rpm", "payout", "ratePer1k", "payPerThousand"):
                        value = item.get(key)
                        if isinstance(value, (int, float)):
                            rate = float(value); break
                if name and rate is not None:
                    url = next((item.get(k) for k in ("url", "link", "href", "campaignUrl", "campaign_url") if isinstance(item.get(k), str) and item.get(k)), base_url)
                    url = urllib.parse.urljoin(base_url, url)
                    if url.rstrip("/") == base_url.rstrip("/"):
                        continue
                    if any(token in url.lower() for token in ("/discover", "/campaigns/", "/streamer-clipping-campaigns")):
                        continue
                    campaigns.append(normalize(make_campaign(name, url, source, blob, rate, parse_budget(blob)), rules))
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
    return campaigns


def inspect_page(page):
    """Return parser diagnostics without storing page content in the report."""
    parser = LinkParser()
    parser.feed(page)
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script\s*>", page, flags=re.I | re.S)
    return {
        "html_bytes": len(page.encode("utf-8", errors="replace")),
        "anchors_with_text": len(parser.links),
        "script_blocks": len(scripts),
        "payout_markers_in_html": len(re.findall(
            r"\$[\d.,]+(?:[kKmM])?(?:\s*[–-]\s*\$[\d.,]+(?:[kKmM])?)?\s*/\s*(?:1K|1,000|1000|1M)",
            html.unescape(page), flags=re.I
        )),
        "json_script_blocks": sum(
            1 for raw in scripts
            if raw.strip().startswith(("{", "["))
        ),
    }


def parse_source(page, url, source, rules):
    # Avoid broad text windows: they can merge neighboring cards and misassign rates.
    # Diagnostics show whether a page has payout markers the current safe parsers miss.
    items = parse_anchors(page, url, source, rules)
    items.extend(parse_json_scripts(page, url, source, rules))
    deduped = {}
    for item in items:
        key = (item["name"].lower(), item.get("rate"), item.get("source_platform"))
        deduped[key] = item
    return list(deduped.values())


def main():
    parser = argparse.ArgumentParser(description="Scan public campaign listings for clipping opportunities.")
    parser.add_argument("--config", help="Optional JSON config path; defaults to campaign-radar/config.json.")
    parser.add_argument("--output", help="Optional report path; defaults to campaign-radar/latest.json.")
    args = parser.parse_args()
    config = load_config(args.config); rules = config["scoring"]
    sources = [
        ("Content Rewards", config["source"]["discover_url"]),
        ("ClipPay", config["clip_pay_index_url"]),
        ("Clipster", "https://www.clipster.com/discover"),
        ("CLIPPING.net", "https://clipping.net/"),
        ("ClipRadar", "https://www.clipradar.co/"),
    ]
    ranked = []; seen = set(); errors = []; source_diagnostics = []
    for source_name, url in sources:
        status = {"name": source_name, "url": url, "status": "unknown"}
        try:
            page = fetch_page(url)
            status.update(inspect_page(page))
            items = parse_source(page, url, source_name, rules)
            status.update({
                "status": "ok" if items else (
                    "payout_markers_unparsed" if status["payout_markers_in_html"] else
                    "no_payout_markers_found"
                ),
                "candidates_parsed": len(items),
            })
            print(
                f"{source_name}: parsed {len(items)} candidates; "
                f"anchors={status['anchors_with_text']}, "
                f"payout_markers={status['payout_markers_in_html']}, "
                f"JSON scripts={status['json_script_blocks']}; status={status['status']}"
            )
            for item in items:
                key = (item["name"].lower(), item.get("rate"), item.get("source_platform"))
                if key in seen: continue
                seen.add(key); ranked.append(item)
        except Exception as exc:
            status.update({"status": "request_failed", "error": str(exc)})
            errors.append(f"{source_name}: {exc}")
            print(f"{source_name}: scan failed: {exc}")
        source_diagnostics.append(status)
    ranked.sort(key=lambda x: x["opportunity_score"], reverse=True)
    selected = [x for x in ranked if x["opportunity_score"] >= rules["minimum_score_to_report"]]
    kick = [x for x in ranked if "kick" in x.get("name", "").lower() or "kick" in x.get("description", "").lower()]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": [url for _, url in sources],
        "scanned": len(ranked),
        "selected": len(selected),
        "kick_campaigns": kick,
        "campaigns": selected,
        "errors": errors,
        "source_diagnostics": source_diagnostics,
        "coverage": {
            "direct_public_sources": ["Content Rewards", "Clipster", "CLIPPING.net"],
            "public_aggregator_sources": ["ClipPay", "ClipRadar"],
            "scan_mode": "free_public_html",
            "parsing": ["individual_anchors", "embedded_json"],
            "diagnostic_statuses": [
                "ok", "payout_markers_unparsed",
                "no_payout_markers_found", "request_failed"
            ],
        },
    }
    output = Path(args.output) if args.output else ROOT / "campaign-radar" / "latest.json"
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Report saved to: {output}")
    print(f"Campaign radar scanned {len(ranked)} public campaigns across {len(sources)} sources.")
    print(f"{len(selected)} campaigns passed the current score threshold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
