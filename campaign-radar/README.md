# Campaign Radar

This is an isolated, read-only campaign scanner for `clip-machine`.

## What it does

- Runs separately from the production clipping workflow.
- Queries ClipRadar's campaign feed when `CLIPRADAR_API_KEY` is configured.
- Filters for live clipping opportunities accepted on TikTok, YouTube, or Instagram.
- Scores campaigns for rate, opportunity/viral signals, remaining budget, and podcast/clipping relevance.
- Produces `campaign-radar/latest.json` as a workflow artifact.

It does **not** join campaigns, spend money, submit clips, or modify the existing clip-production workflow.

## Setup

Add a GitHub Actions repository secret named `CLIPRADAR_API_KEY` with a ClipRadar API key that has the `campaigns:read` scope.

The workflow can also be started manually from GitHub Actions. It is scheduled independently of the production workflow.

## Removal

This feature is intentionally removable. To remove it later, delete only:

- `.github/workflows/campaign-radar.yml`
- `campaign-radar/config.json`
- `campaign-radar/campaign_scanner.py`
- `campaign-radar/README.md`

Nothing in the existing `clip-machine.yml` workflow depends on these files.
