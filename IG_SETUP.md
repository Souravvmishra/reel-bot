# One-time setup: post reels via the official Instagram Graph API

This is the ~20-minute setup you do **once**. After it's done, posting is one
command:

```bash
python3 content_agent.py --post --video-url "https://your-host/post-reel.mp4"
```

Everything here uses only the official Meta/Instagram Graph API — no password
login, no unofficial libraries. Three hard requirements (they're by design,
can't be automated around):

1. Your Instagram must be a **professional** (Business or Creator) account.
2. It must be **linked to a Facebook Page** you manage.
3. The reel must be at a **public URL** (the API downloads it from the
   internet; it can't read local files).

| # | Step | Where | Time |
|---|------|-------|------|
| 1 | Convert IG to professional | Instagram app | 5 min |
| 2 | Link IG to a Facebook Page | Instagram app | 2 min |
| 3 | Create the Meta developer app | developers.facebook.com | 3 min |
| 4 | Add the Instagram product | App dashboard | 1 min |
| 5 | Add permissions | App dashboard | 2 min |
| 6 | Generate the access token | Instagram dashboard or Graph API Explorer | 2 min |
| 7 | Verify everything | terminal | 2 min |

---

## Step 1 — Convert Instagram to a professional account

Instagram app → **Settings and activity** → **Account type** → **Switch to
professional** → choose **Creator** (or Business; either works with this API).

Why: the Instagram Graph API only works with professional accounts.

## Step 2 — Link Instagram to a Facebook Page

The account must be linked to a Facebook Page **where you are an admin**.

- If you don't have a Page yet: https://www.facebook.com/pages/create (takes a
  minute, any name is fine — it just needs to exist).
- In the Instagram app: **Settings and activity** → **Business tools and
  controls** (or for Creator accounts: **Linked accounts** → **Facebook**) →
  connect your Page.

Verify in a browser: open your Facebook Page → **Settings** → **Linked
accounts** → your Instagram handle should be listed.

## Step 3 — Create the Meta developer app

1. Go to https://developers.facebook.com/apps → **Create app**.
2. App type: choose **Business** (this is the type that can use the Instagram
   product — "Consumer" can't).
3. Name it anything (e.g. "reel-poster"), add your contact email, create.

## Step 4 — Add the Instagram product

App dashboard → **Add product** → **Instagram** → **Set up**.

You'll see warnings about App Review — ignore them for now (see the FAQ at
the bottom: you don't need review to post to your own account).

## Step 5 — Add the permissions

App dashboard → **App Review** → **Permissions and features**. Find and
**Request advanced access** for these two (both are always required):

| Permission | Why |
|------------|-----|
| `instagram_basic` | read your account |
| `instagram_content_publish` | create + publish reels |

A third one, `pages_show_list`, is only needed if you use the **Graph API
Explorer** token path below (so the script can auto-find your IG user id).
With the new dashboard token path you don't need it.

"Request advanced access" in Development mode grants it instantly for
accounts with a role on the app — yours is, so nothing to wait for. (If the
dashboard tells you to "assign the Instagram Tester role" before generating a
token: you created the app, so you're already Admin, which satisfies this.)

## Step 6 — Generate the access token

You can use either path — they produce the same kind of `EAAG...` token.

**Path A — new Instagram dashboard (recommended, fewer steps):**

1. In your app dashboard → **Instagram** → **API setup with Instagram
   business login**.
2. Scroll to **Generate access tokens** → click **Generate token** and pick
   your Instagram account. Grant the requested permissions.
3. Copy the token that appears, and also copy the **IG user id** shown for
   the connected account (the long number).

  ```bash
  echo 'IG_ACCESS_TOKEN=IGAA...' >> .env   # new-flow tokens start with IGAA
  echo 'IG_USER_ID=1784...' >> .env        # REQUIRED for this token type
  ```

  Note: these `IGAA` tokens talk to `graph.instagram.com` (the script
  detects this automatically). They can't auto-find your IG user id, so
  `IG_USER_ID` is required — the dashboard shows it next to the connected
  account, or `--check` prints it.

**Path B — Graph API Explorer:**

1. Open https://developers.facebook.com/tools/explorer/ → select your app.
2. **Add a permission**: `instagram_basic`, `instagram_content_publish`, and
   `pages_show_list`.
3. **Generate Access Token**, log in as the Facebook account that manages the
   Page, and copy the `EAAG...` token.

  ```bash
  echo 'IG_ACCESS_TOKEN=EAAG...' >> .env
  ```

  (The script auto-finds your IG user id via `/me/accounts` — that's what
  `pages_show_list` is for.)

**The token is short-lived (~1 hour).** Two options:

- **Occasional posting:** just regenerate it before each post — it takes 20
  seconds.
- **Set-and-forget:** exchange it for a **~60-day token** with the helper we
  provide (official `fb_exchange_token` endpoint). It needs your **app id
  and app secret from App settings → Basic** (not the "Instagram app secret"
  shown on the Instagram setup page):

  ```bash
  echo 'FB_APP_ID=your_app_id' >> .env
  echo 'FB_APP_SECRET=your_app_secret' >> .env
  python3 long_live_token.py --write      # reads the short-lived token from IG_ACCESS_TOKEN
  ```

  This prints the long-lived token and (with `--write`) saves it to `.env`
  automatically.

`.env` is already in `.gitignore`, so the token never reaches version control.

## Step 7 — Verify everything

```bash
# 1. Token + account + permissions check (read-only, nothing is posted):
python3 post_instagram.py --check

# 2. Render this week's reel:
python3 content_agent.py --video

# 3. Host the reel at a public URL (needs GH_REPO/GH_TOKEN in .env):
python3 upload_reel.py                    # -> prints https://raw.githubusercontent.com/....mp4

#    Confirm the URL serves the file (upload_reel.py already waits for 200):
curl -I "$(python3 upload_reel.py)"      # want HTTP 200

# 4. See the exact API calls that will be made, without posting:
python3 post_instagram.py --video-url "$(python3 upload_reel.py)" --dry-run
```

## Step 8 — Post

One command end to end (upload + generate + publish):

```bash
python3 content_agent.py --post --video-url "$(python3 upload_reel.py)"
```

or with an already-hosted URL:

```bash
python3 content_agent.py --post --video-url "https://your-host/post-reel.mp4"
```

It makes the 4 official Graph API calls (resolve account → create the REELS
container → poll until FINISHED → publish) and prints the reel permalink.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Error: Instagram API error 190: Invalid OAuth access token` | Token missing/expired — regenerate in Graph Explorer (Step 6). |
| `Could not find an Instagram Business/Creator account linked to this token's Page` | Re-check Steps 1–2 (professional account + linked Page), or set `IG_USER_ID` in `.env` so no page lookup is needed. |
| `Missing permission` errors | The token wasn't generated with all 2 (or 3) permissions — regenerate with them selected. |
| Container `ERROR` / timeout after ~60s | The video URL isn't publicly reachable or isn't a valid mp4 — check with `curl -I`. |
| `#100` invalid parameter | URL must be `https://` and point directly at the file (no interstitial page). |

## Hosting the video

The API can only download the file from a **public URL**. The pipeline uses
**GitHub exclusively** — one deterministic path, no fallback chains:

- `upload_reel.py` pushes the reel to `GH_REPO` (a PUBLIC repo) via the
  official GitHub Contents API and prints the `raw.githubusercontent.com`
  URL. Free, permanent (<100 MB), reliable from any network, and the same
  path is overwritten on every run.
- Requires in `.env`: `GH_TOKEN` (token with Contents read/write on that
  repo) and `GH_REPO=owner/repo`.

**Auto-cleanup:** once a GitHub-hosted reel is published, the source file is
deleted from the repo automatically — the URL is only needed while
Instagram downloads/processes the video, so the repo stays clean. (GitHub's
CDN may keep serving a cached copy briefly after deletion; harmless since
the reel already lives on Instagram.)

`upload_reel.py` waits for HTTP 200 on upload, so the URL is guaranteed
serving before it's handed to the post step.

## FAQ

- **Do I need App Review / to switch to Live mode?** Only if you want to post
  to **other people's** Instagram accounts. In Development mode, the API works
  for any account that has a role on your app — yours does. Fine for personal
  use forever.
- **How long does the token last?** Explorer tokens ~1 h; long-lived tokens
  ~60 days. When `--check` or a post fails with error 190, regenerate.
- **Multiple accounts?** App dashboard → **App roles** → add the second
  account as a **Tester**, log it into the Graph Explorer, generate a token
  for it.
- **Is this against the rules?** No — this is the sanctioned path Meta
  documents for programmatic publishing: professional account, linked Page,
  official Graph API, token auth. No scraping, no password login.
