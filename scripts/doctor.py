import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_command(command):
    return subprocess.run(command, capture_output=True, text=True)


def load_campaigns():
    path = ROOT / "campaigns" / "config.json"
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    return data.get("campaigns", []) if isinstance(data, dict) else []


def check_command(name):
    path = shutil.which(name)
    if not path:
        return False, f"{name} not found"
    result = run_command([name, "-version"])
    if result.returncode != 0:
        return False, f"{name} is not executable"
    return True, f"{name} OK"


def check_python_scripts():
    scripts = sorted((ROOT / "scripts").glob("*.py"))
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", *[str(path) for path in scripts]],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, "Python scripts compile" if result.returncode == 0 else result.stderr.strip()


def check_campaign(campaign_id):
    campaigns = load_campaigns()
    campaign = next((item for item in campaigns if item.get("id") == campaign_id), None)
    if campaign is None:
        return False, f"campaign not found: {campaign_id}"
    if campaign.get("status") not in (None, "active", "live"):
        return False, f"campaign is not active: {campaign_id}"
    return True, f"campaign OK: {campaign_id}"


def check_logo():
    logo = ROOT / "rebel_audio_logo_transparent-1 (1).png"
    if logo.exists() and logo.stat().st_size > 0:
        return True, "campaign logo OK"
    return False, "campaign logo missing"


def check_ffmpeg_probe():
    result = run_command([
        "ffprobe", "-v", "error", "-f", "lavfi", "-i", "color=s=16x16:d=0.1",
        "-show_entries", "format=duration", "-of", "default=nw=1:nk=1",
    ])
    return result.returncode == 0, "ffprobe functional" if result.returncode == 0 else result.stderr.strip()


def main():
    campaign_id = sys.argv[1] if len(sys.argv) > 1 else None
    checks = []

    checks.append(check_command("ffmpeg"))
    checks.append(check_command("ffprobe"))
    checks.append(check_ffmpeg_probe())
    checks.append(check_python_scripts())

    if campaign_id:
        checks.append(check_campaign(campaign_id))

    # Logo is required by the current campaign setup. Keep this a hard check
    # so a missing asset fails before an expensive processing run.
    checks.append(check_logo())

    failed = [message for ok, message in checks if not ok]
    for ok, message in checks:
        print(("OK      " if ok else "ERROR   ") + message)

    print(f"Doctor complete: {len(checks) - len(failed)} passed, {len(failed)} failed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
