# Campaign Radar

This is an isolated, read-only campaign scanner for `clip-machine`.

## What it does

- Runs separately from the production clipping workflow.
- Reads the **public Content Rewards Discover page**; no paid API or API key is required.
- Filters the public Discover page for clipping campaigns on TikTok, YouTube, or Instagram.
- Scores campaigns for rate, remaining budget, and podcast/clipping relevance.
- Produces `campaign-radar/latest.json` as a workflow artifact.

The scanner uses normal HTTPS access to a public page. It does **not** join campaigns, spend money, submit clips, or modify the existing clip-production workflow.

## Cost

**$0.** There is no API subscription, API key, credit balance, or paid service required by this radar.

The public campaign page is the source, so the scanner can only see campaigns that Content Rewards exposes publicly on Discover. Private campaigns are not visible there.

## Run

The workflow runs once per day and can also be started manually from GitHub Actions.

## Removal

This feature is intentionally removable. To remove it later, delete only:

- `.github/workflows/campaign-radar.yml`
- `campaign-radar/config.json`
- `campaign-radar/campaign_scanner.py`
- `campaign-radar/README.md`

Nothing in the existing `clip-machine.yml` workflow depends on these files.
