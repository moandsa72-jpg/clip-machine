# SKULLPANDA campaign draft

This folder contains the storyboard for a silent vertical photo-slideshow draft based on the Pop Mart / SKULLPANDA campaign brief.

## Build locally

1. Install FFmpeg and make sure `ffmpeg` is on your PATH.
2. Put the approved reference-photo ZIP somewhere accessible (for example, `input/Doja Cat x Pop Mart.zip`).
3. From the repository root, run:

```bash
python scripts/create_photo_campaign_draft.py "input/Doja Cat x Pop Mart.zip"
```

The MP4 is written to `output/campaign_drafts/skullpanda_draft.mp4`. Override it with `--output path/to/draft.mp4`.

The renderer creates an approximately 16-second 9:16 silent draft with text overlays. It does not publish or submit anything. The ZIP is not checked into this repository; add it to `input/` locally before running.

## Before posting

- Confirm the campaign has authorized these exact reference images for clipping.
- Submit the draft for pre-approval before posting.
- Social caption must contain the exact text `SKULLPANDA`, hashtag `#skullpanda`, and tag `@popmart_us`.
- Clip length must be at least 10 seconds.
- Do not publish recycled or reposted content.
