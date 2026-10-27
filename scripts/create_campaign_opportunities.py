#!/usr/bin/env python3
"""Prepare learned posting intelligence, then run semantic campaign matching."""

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


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("Usage: create_campaign_opportunities.py <campaign-radar/latest.json> <posting_package.json> [output.json]")
    apply_learning(sys.argv[2])
    main()
