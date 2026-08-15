# Reel Pipeline

An automated "self-care checklist" content pipeline: it writes the posts with
Gemini, renders them as Instagram-style images and reels, hosts the video at a
public URL, and publishes to **Instagram** and **YouTube** using only the
official APIs.

```text
write (Gemini / local) → render (Pillow) → encode (ffmpeg, Ken Burns + audio)
      ↓
  Instagram ── hosting: GitHub raw URL (official Graph API)
  YouTube  ── direct file upload (official Data API v3)
```

Everything uses official APIs and stdlib-only HTTP — no unofficial libraries,
no account-password login.

## Quick start

```bash
.venv/bin/pip install -r requirements.txt   # Pillow, imageio-ffmpeg, fastapi, uvicorn
python3 src/content_agent.py --list-themes               # see the checklist topics
python3 src/content_agent.py --seed 7                    # one random draft
python3 src/content_agent.py --video                     # write + render + encode reel
```

Posting to real accounts needs one-time API setup:

| Channel | Setup guide | What it does |
|---------|-------------|--------------|
| Instagram | [`docs/IG_SETUP.md`](docs/IG_SETUP.md) | professional account + linked FB Page + Graph API token |
| YouTube | [`docs/YT_SETUP.md`](docs/YT_SETUP.md) | Google Cloud project + OAuth login (one time) |

### Posting

```bash
# Render the reel, host it on GitHub, publish to Instagram
python3 src/content_agent.py --post --video-url "$(python3 src/upload_reel.py)"

# Instagram + YouTube in one run (IG still needs IG_ACCESS_TOKEN, etc.)
python3 src/content_agent.py --post --youtube

# Dry-run / verification (posts nothing)
python3 src/post_instagram.py --check
python3 src/post_youtube.py --check
```

### Running it on a schedule (zero hosting)

The [`post-reel` GitHub Actions
workflow](.github/workflows/post_reel.yml) runs the same pipeline twice a day
on free runner time — nothing to host.

## Repository layout

```
.
├── src/                      # all Python: pipeline + API + bot
│   ├── content_agent.py      # orchestrator: writes drafts, renders, posts
│   ├── make_post.py          # renders the "why is my life so bad" card (Pillow)
│   ├── make_video.py         # image → MP4 reel (Ken Burns + audio, ffmpeg)
│   ├── make_avatar.py        # profile-picture PNG generator
│   ├── post_instagram.py     # publish reel via the official Graph API
│   ├── post_youtube.py       # publish reel via the official Data API v3 (OAuth)
│   ├── upload_reel.py        # host the video at a GitHub raw URL
│   ├── comment_bot.py        # auto-reply to new comments (official API)
│   ├── long_live_token.py    # exchange 1h IG token for a ~60-day one
│   ├── post_api.py           # FastAPI service wrapping the pipeline
│   ├── ig_common.py          # shared plumbing (env, Graph client, paths)
│   └── gh.py                 # minimal GitHub Contents API client
├── docs/
│   ├── IG_SETUP.md           # one-time Instagram/Graph API setup
│   └── YT_SETUP.md           # one-time YouTube/OAuth setup
├── audio/reel.mp3            # default reel music (override with AUDIO_PATH)
├── .github/workflows/post_reel.yml   # scheduled posting (GitHub Actions)
├── Dockerfile / render.yaml          # host src/post_api.py (optional)
├── post_history.json         # committed on purpose: subject-rotation memory
└── requirements.txt
```

### Key scripts in one line

| `src/…` | What it does |
|---------|--------------|
| `content_agent.py --video` | one-command pipeline: write + render + encode |
| `content_agent.py --post` | …and publish to Instagram |
| `content_agent.py --youtube` | …and publish to YouTube |
| `post_instagram.py --check` | read-only: verify token/account/permissions |
| `post_youtube.py --check` | read-only: verify credentials + channel |
| `post_api.py` | optional hosted HTTP API (`POST /post` to run everything) |

## Environment variables

All secrets live in a gitignored `.env` at the repo root (loaded
automatically) or in the host's env. The setup guides list exactly which ones
you need for Instagram vs. YouTube.

| Variable | Used for |
|----------|----------|
| `GOOGLE_API_KEY` | Gemini draft writer (free at aistudio.google.com) |
| `IG_ACCESS_TOKEN`, `IG_USER_ID` | Instagram publishing |
| `GH_REPO` (public repo), `GH_TOKEN` | hosting the reel at a raw URL |
| `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` | YouTube publishing |
| `AUDIO_PATH` | optional override for the reel music |
| `API_KEY` | only the optional hosted API |

## Design notes

- **Deterministic hosting** — the reel is always pushed to the same GitHub
  repo path, then deleted right after Instagram processes it (the URL is only
  needed while Meta downloads the video).
- **Fresh content** — `post_history.json` remembers the last posts; the agent
  rotates the checklist *subject* (sleep, money, room, …), avoids reused
  hooks/items, and rejects drafts that repeat past jokes after light
  stemming + Jaccard/ngram overlap checks.
- **No hard Gemini dependency** — the pipeline falls back from Gemini to
  local template drafts (offline) when no key is present, and tries a backup
  key on quota/HTTP errors.
- **Everything deletes after publish** — GitHub source video is removed, so
  the public repo stays clean.