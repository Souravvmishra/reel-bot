# One-time setup: post reels to YouTube via the official Data API v3

The ~10-minute setup you do **once**. After it's done, posting is one command:

```bash
python3 src/content_agent.py --youtube            # generate + render + upload
python3 src/content_agent.py --post --youtube     # Instagram AND YouTube in one run
```

Everything uses only the official **YouTube Data API v3** with OAuth 2.0 —
no unofficial libraries, no password login. Unlike Instagram, YouTube accepts
a direct **file upload**, so there's no public-URL or GitHub requirement.

| # | Step | Where | Time |
|---|------|-------|------|
| 1 | Create a Google Cloud project | console.cloud.google.com | 2 min |
| 2 | Enable the YouTube Data API v3 | API Library | 1 min |
| 3 | Configure the OAuth consent screen | APIs & Services | 3 min |
| 4 | Create a Desktop-app OAuth client | Credentials | 2 min |
| 5 | Add the client id/secret to `.env` | terminal | 1 min |
| 6 | One-time login (`--auth`) | terminal + browser | 1 min |
| 7 | Verify (`--check`) | terminal | 1 min |

---

## Step 1 — Create a Google Cloud project

1. Go to https://console.cloud.google.com and create a project (or reuse one).
2. The YouTube Data API v3 is free for normal use — no billing setup needed.

## Step 2 — Enable the YouTube Data API v3

APIs & Services → **Library** → search **YouTube Data API v3** → **Enable**.

## Step 3 — Configure the OAuth consent screen

APIs & Services → **OAuth consent screen** → create:

- **User type:** External.
- App name + your email, save.
- Under **Audience** → **Test users**, add your own Google account.

The "unverified app" warning is fine for personal use — you're the test user.

## Step 4 — Create the OAuth client

APIs & Services → **Credentials** → **Create credentials** → **OAuth client
ID**:

- **Application type:** Desktop app (this enables the loopback redirect
  flow `post_youtube.py` uses).
- Copy the **Client ID** and **Client Secret**.

## Step 5 — Add them to `.env`

`.env` is already gitignored, so these never reach version control:

```bash
echo 'YT_CLIENT_ID=xxxx.apps.googleusercontent.com' >> .env
echo 'YT_CLIENT_SECRET=GOCSPX-...' >> .env
```

## Step 6 — One-time login

```bash
python3 src/post_youtube.py --auth
```

A browser opens Google's consent screen → approve it. The script catches the
redirect on a local loopback port and saves the refresh token to `.env`
automatically:

```bash
YT_REFRESH_TOKEN=<long-lived token>
```

Run this once; the refresh token lasts until you revoke it.

## Step 7 — Verify

```bash
python3 src/post_youtube.py --check
```

Prints the token expiry, granted scopes, and your channel name. It posts
nothing.

## Posting

```bash
# YouTube only
python3 src/content_agent.py --youtube

# Instagram + YouTube in one run (IG still needs IG_ACCESS_TOKEN, etc.)
python3 src/content_agent.py --post --youtube
```

Defaults:
- **Title** = the hook line (e.g. "a quick “why can't i get to the gym”
  checklist") — override with `--yt-title`.
- **Description** = the full caption text (intro + CTA + hashtags) —
  override with `--yt-description`.
- **Privacy** = `public` — override with `--yt-privacy unlisted|private`.
- The reel is vertical 1080×1920, so YouTube treats it as a Short; the
  script prints the `https://youtube.com/shorts/<id>` URL.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `token refresh failed` | The refresh token was revoked — re-run `python3 src/post_youtube.py --auth`. |
| `token exchange failed: invalid_client` | `YT_CLIENT_ID` / `YT_CLIENT_SECRET` don't match the Desktop app — re-copy from Credentials. |
| `Access blocked` / consent error | You're not a test user of the project — add your account in Step 3. |
| `upload init failed: ... quota` | The daily `videos.insert` bucket (100 uploads/day) is exhausted, or the project is out of its 10,000-unit general pool — retry tomorrow or check the Quotas page in the API console. |
| `timed out waiting for authorization` | The browser flow wasn't completed in 5 minutes — run `--auth` again. |

## FAQ

- **Is this against the rules?** No — it's the documented YouTube Data API
  path (OAuth 2.0 consent, `videos.insert`), the same one official apps use.
- **How many uploads can I make?** `videos.insert` has its own dedicated
  bucket: **up to 100 uploads per day** at 1 quota unit each (Google's
  current numbers — it used to cost 1,600 units). The general 10,000-unit
  daily pool is barely touched by uploads. In practice, YouTube's own
  upload/processing rate limits hit long before the API quota does.
- **Multiple channels?** Log in with a different Google account and run
  `--auth` again — the refresh token is stored per-account.
- **Why not just reuse the GitHub URL?** YouTube's API accepts a direct
  file upload, which is simpler and removes the public-hosting dependency
  entirely. The file upload also doesn't count against GitHub's quota.
