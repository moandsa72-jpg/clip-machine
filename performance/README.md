# Performance Feedback

This folder is the free/local learning store for published clips.

The system is intentionally simple: after a clip is published, its public metrics can be recorded in `feedback.json`. The analysis script summarizes which hooks, topics, lengths, and campaigns are actually performing well.

No paid API, cloud analytics service, or external database is required.

## Entry shape

```json
{
  "clip_id": "clip-001",
  "campaign_id": "blastoff_jingle_jared_rebel_audio",
  "published_url": "https://example.com/post",
  "platform": "TikTok",
  "published_at": "2026-10-24T12:00:00+00:00",
  "views": 12000,
  "likes": 700,
  "comments": 45,
  "shares": 80,
  "hook_score": 8,
  "duration_seconds": 42,
  "topic": "podcasting"
}
```

The learning layer should only influence future ranking after enough observations exist. It must never pretend that a tiny sample proves a trend.
