# Docs

One-time setup guides for connecting the reel pipeline to each platform.

| Guide | Channel | Time | What it covers |
|-------|---------|------|----------------|
| [`IG_SETUP.md`](IG_SETUP.md) | Instagram | ~20 min | professional account + linked FB Page + Meta app + Graph API token |
| [`YT_SETUP.md`](YT_SETUP.md) | YouTube | ~10 min | Google Cloud project + YouTube Data API v3 + one-time OAuth login |

Both are do-once: after they're done, posting is a single
`python3 src/content_agent.py --post --youtube` run (or the scheduled GitHub
Actions workflow).