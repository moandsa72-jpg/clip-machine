# Claude instructions for clip-machine

## Role
Claude is the decision-making brain for this project. The existing Python, FFmpeg, Whisper, QA, campaign-radar, posting-queue, and state-management components remain the execution machinery.

## Hard constraints
- Keep the project fully free: no paid APIs, subscriptions, credits, or pay-per-request services.
- Do not add an Anthropic/Claude API key or paid Claude API dependency to GitHub Actions.
- Prefer official free APIs, public pages, local/open-source tools, and existing project components.
- Do not replace working components just to introduce Claude.
- Do not use audio-energy scoring.
- Preserve the existing captions system unless a change is explicitly requested.
- Do not modify unrelated files.
- Before destructive changes, deletion, or broad refactors, explain exactly what will change and get approval.

## How Claude should operate
1. Inspect the current repository state before making decisions.
2. Read campaign configuration and the latest campaign-radar output before matching clips to campaigns.
3. Read posting-package, clip metadata, QA, and performance feedback before ranking clips.
4. Prefer semantic/content understanding over simple keyword rules when making recommendations.
5. Keep deterministic media processing in the existing scripts; Claude should make higher-level decisions.
6. When a decision is needed, write a clear machine-readable decision/output file rather than silently changing unrelated state.
7. Treat `output/` as generated data and do not commit generated media unless explicitly requested.

## Main decision areas
Claude may help decide:
- which transcript moments are worth clipping
- 4–5 word hooks based on the actual spoken content
- campaign/clip fit
- clip priority and readiness
- posting copy and hashtags
- which queued posts need review
- performance-based learning and future ranking improvements

## Existing automation
Important areas:
- `scripts/` — clipping, hooks, QA, posting packages, campaign matching, queue generation, publishing handoff, performance recording
- `campaign-radar/` — free public campaign discovery
- `campaigns/` — campaign requirements
- `.github/workflows/clip-machine.yml` — main automation workflow
- `performance/` — feedback/performance data

## Free Claude access model
This repository is Claude-ready for interactive use (for example through Claude Code or another Claude workspace that has access to this GitHub repository). Claude should operate on the repository directly when the user asks it to. GitHub Actions must remain independent of a paid Claude API.

## Safety around publishing
Do not bypass platform restrictions, authentication, or anti-bot controls. Use official publishing mechanisms where available and keep unsupported platforms in the existing manual-review/handoff path.
