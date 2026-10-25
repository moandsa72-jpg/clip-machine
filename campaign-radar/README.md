# Campaign Radar

This is a read-only, zero-cost campaign scanner for `clip-machine`.

## What it does

- Runs separately once per day and can also be refreshed by the production clipping workflow.
- Reads public campaign listings; no paid API or API key is required.
- Looks for clipping opportunities across public campaign indexes, including Kick/streamer opportunities when publicly listed.
- Scores campaigns for payout, budget, and podcast/clipping relevance.
- Produces `campaign-radar/latest.json`.
- The production workflow uses the fresh report to match generated clips to campaign opportunities and build a posting queue.

The scanner uses normal HTTPS access to public pages. It does **not** join campaigns, spend money, submit clips, or publish posts.

## Cost

**$0.** There is no API subscription, API key, credit balance, paid scheduler, or pay-per-request service required by this radar.

The scanner can only see campaigns that its public sources expose. Private campaigns are not visible.

## Posting handoff

The posting queue contains:

- campaign URL and score
- best matching clip
- platform
- platform-specific caption/title data
- publish status
- public post URL placeholder
- performance fields for views, likes, comments, and shares

The queue is uploaded as a workflow artifact. Publishing is handled only through supported/free platform flows; no sketchy browser bot or paid scheduler is used.

## Removal

The radar remains intentionally removable. To remove the radar feature and its integration, delete only:

- `.github/workflows/campaign-radar.yml`
- `campaign-radar/config.json`
- `campaign-radar/campaign_scanner.py`
- `campaign-radar/README.md`
- `scripts/create_campaign_opportunities.py`
- `scripts/create_posting_queue.py`
- `scripts/publish_queue.py`
- `scripts/record_performance.py`

Then remove the campaign-opportunity/queue steps from `.github/workflows/clip-machine.yml`.
