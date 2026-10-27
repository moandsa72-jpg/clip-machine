#!/usr/bin/env python3
"""Prepare learned posting intelligence, refresh its dashboard, then match campaigns."""

import json
import subprocess
import sys
from pathlib import Path

from semantic_campaign_matcher import main


def apply_learning(package_path):
    feedback = Path("performance/feedback.json")
    if not feedback.exists():
        return
    script = Path(__file__).with_name("apply_performance_learning.py")
    subprocess.run([sys.executable, str(script), package_path, str(feedback)], check=True)


def refresh_dashboard(package_path):
    package = json.loads(Path(package_path).read_text(encoding="utf-8"))
    campaign_id = package.get("campaign_id")
    if not campaign_id:
        return
    script = Path(__file__).with_name("create_posting_dashboard.py")
    output = Path("output/posting_dashboard") / campaign_id
    subprocess.run([sys.executable, str(script), package_path, str(output)], check=True)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("Usage: create_campaign_opportunities.py <campaign-radar/latest.json> <posting_package.json> [output.json]")
    apply_learning(sys.argv[2])
    refresh_dashboard(sys.argv[2])
    main()
