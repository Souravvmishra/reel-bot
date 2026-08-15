#!/usr/bin/env python3
"""
Post the reel to YouTube using the OFFICIAL YouTube Data API v3 with OAuth
2.0. No unofficial libraries, no password login - stdlib urllib only.

Unlike Instagram, the Data API accepts a direct FILE upload (resumable
protocol), so no public URL or GitHub hosting is needed.

Flow:
  1. One-time auth (--auth): opens your browser to Google's consent
     screen, catches the redirect on a local loopback port, and saves a
     refresh token to .env (YT_REFRESH_TOKEN). Do this once.
  2. Upload (default): refresh the access token -> resumable-upload the
     local MP4 (videos.insert) -> poll processing status -> print the
     Shorts URL.
  3. --check: read-only - verify the credentials, print scopes + channel.

One-time setup (about 10 minutes, do it once - full guide in YT_SETUP.md):
  1. Google Cloud Console -> create a project.
  2. Enable the "YouTube Data API v3".
  3. OAuth consent screen -> External -> add yourself as a test user.
  4. Credentials -> Create credentials -> OAuth client ID -> Desktop app.
  5. Store in .env (already gitignored):
       YT_CLIENT_ID=<...>.apps.googleusercontent.com
       YT_CLIENT_SECRET=<...>
  6. Run:  python3 post_youtube.py --auth     (one-time login)

Usage:
    python3 post_youtube.py --auth                  # one-time login
    python3 post_youtube.py --check                 # read-only verification
    python3 post_youtube.py --file post-reel.mp4 --title "..." --description "..."
    python3 post_youtube.py --dry-run --title ...   # print the calls, upload nothing
"""

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from ig_common import load_env_file

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_URL = "https://www.googleapis.com/youtube/v3"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"

# youtube.upload = upload videos; youtube.readonly = read your own channel
# (used by --check to print the channel name).
SCOPE = ("https://www.googleapis.com/auth/youtube.upload "
         "https://www.googleapis.com/auth/youtube.readonly")

# "People & Blogs" category - the default for this kind of content.
CATEGORY_ID = "22"

# How long to wait for YouTube to finish processing before giving up.
POLL_SECONDS = 5
POLL_TRIES = 12


# ---------------------------------------------------------------------------
# tiny HTTP helpers (stdlib only)
# ---------------------------------------------------------------------------

def _request(url, data=None, headers=None, method=None):
    """Do a request; returns (status, body_bytes, lowercase-headers-dict)."""
    req = urllib.request.Request(url, data=data, headers=headers or {},
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return resp.status, resp.read(), \
                {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, e.read(), {k.lower(): v for k, v in e.headers.items()}


def _json(data, fallback=""):
    try:
        return json.loads(data.decode() or fallback)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


def _err(data):
    """Human-readable one-liner from a Google error JSON body."""
    js = _json(data)
    err = js.get("error") or {}
    if isinstance(err, dict) and err.get("message"):
        return f"{err.get('code', '?')}: {err['message']}"
    return data.decode(errors="replace")[:300] or "unknown error"


# ---------------------------------------------------------------------------
# OAuth 2.0
# ---------------------------------------------------------------------------

def _form_post(url, fields):
    body = urllib.parse.urlencode(fields).encode()
    status, data, _ = _request(
        url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    return status, _json(data)


def exchange_code(client_id, client_secret, code, redirect_uri):
    """Trade the one-time authorization code for tokens (refresh_token!)."""
    status, js = _form_post(TOKEN_URL, {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    if status != 200:
        raise RuntimeError(f"token exchange failed: "
                           f"{js.get('error_description') or js.get('error')}")
    refresh = js.get("refresh_token")
    if not refresh:
        raise RuntimeError("no refresh_token returned - go to "
                           "https://myaccount.google.com/permissions, revoke "
                           "this app, and run --auth again")
    return refresh


def refresh_access(client_id, client_secret, refresh_token):
    """Turn the long-lived refresh token into a fresh ~1h access token."""
    status, js = _form_post(TOKEN_URL, {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    if status != 200:
        raise RuntimeError(f"token refresh failed: "
                           f"{js.get('error_description') or js.get('error')}"
                           " - re-run python3 post_youtube.py --auth")
    return js["access_token"]


def auth_flow(client_id, client_secret):
    """One-time login: local loopback server -> code -> refresh token.

    Returns the refresh token (the caller saves it to .env).
    """
    # pick a free loopback port
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    import http.server
    import threading

    state = os.urandom(16).hex()
    redirect_uri = f"http://127.0.0.1:{port}/"
    auth_url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",     # required for a refresh token
        "prompt": "consent",          # forces the consent screen every time
        "state": state,
    })

    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(
                urllib.parse.urlparse(self.path).query)
            ok = query.get("state", [""])[0] == state
            result["code"] = query.get("code", [None])[0] if ok else None
            self.send_response(200 if result["code"] else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = ("<h3>Logged in! You can close this tab.</h3>"
                   if result["code"] else
                   "<h3>Authorization failed - check the URL and try again.</h3>")
            self.wfile.write(msg.encode())
            threading.Thread(target=self.server.shutdown).start()

        def log_message(self, *args):     # keep the terminal quiet
            pass

    print("opening your browser to Google's consent screen ...")
    webbrowser.open(auth_url)
    print("if the browser didn't open, visit:\n  " + auth_url + "\n")

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 1
    deadline = time.time() + 300
    while "code" not in result and time.time() < deadline:
        server.handle_request()
    server.server_close()
    if "code" not in result:
        raise RuntimeError("timed out waiting for authorization - run --auth "
                           "again")
    return exchange_code(client_id, client_secret, result["code"],
                         redirect_uri)


def save_env(path, key, value):
    """Add or replace a KEY=VALUE line in a .env file."""
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    lines = [ln for ln in lines if not ln.startswith(key + "=")]
    lines.append(f"{key}={value}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# upload + status
# ---------------------------------------------------------------------------

def upload_video(token, path, title, description, privacy):
    """Resumable upload of the local MP4; returns the new video id."""
    size = os.path.getsize(path)
    meta = json.dumps({
        "snippet": {
            "title": title[:100],
            "description": description,
            "categoryId": CATEGORY_ID,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }).encode()

    # 1) initiate: metadata -> we get the upload URL back in Location
    init = f"{UPLOAD_URL}?uploadType=resumable&part=snippet,status"
    status, data, headers = _request(init, data=meta, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/mp4",
        "X-Upload-Content-Length": str(size),
    })
    if status not in (200, 201):
        raise RuntimeError(f"upload init failed: {_err(data)}")
    location = headers.get("location")
    if not location:
        raise RuntimeError("no upload URL returned by the API")

    # 2) send the file in one PUT (a Short is small enough for a single chunk)
    print(f"uploading {os.path.basename(path)} ({size / 1e6:.1f} MB) ...")
    with open(path, "rb") as f:
        body = f.read()
    status, data, _ = _request(location, data=body, method="PUT", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "video/mp4",
        "Content-Length": str(size),
    })
    js = _json(data)
    if status not in (200, 201):
        raise RuntimeError(f"upload failed: {_err(data)}")
    video_id = js.get("id")
    if not video_id:
        raise RuntimeError("upload response had no video id")
    return video_id


def wait_ready(token, video_id):
    """Poll processing status until the video is live (or failed)."""
    print("waiting for YouTube to process the video ...")
    for _ in range(POLL_TRIES):
        time.sleep(POLL_SECONDS)
        url = f"{API_URL}/videos?part=status&id={video_id}"
        status, data, _ = _request(url,
                                   headers={"Authorization": f"Bearer {token}"})
        if status != 200:
            continue
        items = _json(data).get("items") or []
        if not items:
            continue
        proc = items[0].get("status", {}).get("processingDetails", {})
        pstatus = proc.get("processingStatus", "processing")
        print(f"  processing: {pstatus}")
        if pstatus == "succeeded":
            return
        if pstatus == "failed":
            raise RuntimeError(
                f"YouTube failed to process the video: "
                f"{proc.get('processingFailureReason', 'unknown')}")
    print("  (still processing - it usually finishes shortly; the URL works "
          "once it's done)")


def check(client_id, client_secret, refresh_token):
    """Read-only: verify the stored credentials, print scopes + channel."""
    token = refresh_access(client_id, client_secret, refresh_token)
    status, data, _ = _request(
        "https://oauth2.googleapis.com/tokeninfo?access_token=" + token)
    if status != 200:
        raise RuntimeError(f"token check failed: {_err(data)}")
    js = _json(data)
    scopes = js.get("scope", "").split()
    print(f"  token ok - expires in {js.get('expires_in')}s")
    print("  scopes: " + ", ".join(s or "none" for s in scopes))
    if SCOPE.split()[0] not in scopes:
        print("  WARNING: youtube.upload scope missing - uploads will fail "
              "(re-run --auth)")
    status, data, _ = _request(
        f"{API_URL}/channels?part=snippet&mine=true",
        headers={"Authorization": f"Bearer {token}"})
    if status == 200:
        items = _json(data).get("items") or []
        if items:
            print("  channel: " + items[0]["snippet"].get("title", "?"))
    else:
        print("  (couldn't read channel name: " + _err(data) + ")")
    print("  ready to upload")


# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="Post the reel to YouTube via the official Data API v3")
    p.add_argument("--auth", action="store_true",
                   help="one-time Google login; saves YT_REFRESH_TOKEN to .env")
    p.add_argument("--check", action="store_true",
                   help="read-only: verify the credentials (posts nothing)")
    p.add_argument("--file", default="post-reel.mp4",
                   help="local mp4 to upload (default post-reel.mp4)")
    p.add_argument("--title", default=None,
                   help="video title (max 100 chars)")
    p.add_argument("--description", default="",
                   help="video description")
    p.add_argument("--privacy", choices=["public", "unlisted", "private"],
                   default="public",
                   help="upload privacy (default public)")
    p.add_argument("--client-id", default=None,
                   help="override YT_CLIENT_ID from .env")
    p.add_argument("--client-secret", default=None,
                   help="override YT_CLIENT_SECRET from .env")
    p.add_argument("--refresh-token", default=None,
                   help="override YT_REFRESH_TOKEN from .env")
    p.add_argument("--dry-run", action="store_true",
                   help="validate inputs and print the API calls, upload "
                        "nothing")
    args = p.parse_args()

    load_env_file()
    client_id = args.client_id or os.environ.get("YT_CLIENT_ID")
    client_secret = args.client_secret or os.environ.get("YT_CLIENT_SECRET")
    refresh = args.refresh_token or os.environ.get("YT_REFRESH_TOKEN")

    if not client_id or not client_secret:
        print("Missing YT_CLIENT_ID / YT_CLIENT_SECRET in .env "
              "(see YT_SETUP.md).", file=sys.stderr)
        sys.exit(1)

    if args.auth:
        try:
            refresh = auth_flow(client_id, client_secret)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        save_env(".env", "YT_REFRESH_TOKEN", refresh)
        print("Saved YT_REFRESH_TOKEN to .env - you're set.")
        print("Verify with:  python3 post_youtube.py --check")
        return

    if args.check:
        if not refresh:
            print("No refresh token yet - run: "
                  "python3 post_youtube.py --auth", file=sys.stderr)
            sys.exit(1)
        try:
            check(client_id, client_secret, refresh)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if not refresh:
        print("No YT_REFRESH_TOKEN in .env - run: "
              "python3 post_youtube.py --auth", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(args.file):
        print(f"Error: {args.file} not found - render it first with "
              f"python3 content_agent.py --video", file=sys.stderr)
        sys.exit(1)
    if not args.title:
        print("Error: --title is required (content_agent passes the hook "
              "line automatically)", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("dry run - the real run would make these official Data API "
              "calls:")
        print("  1. POST https://oauth2.googleapis.com/token  "
              "(refresh the access token)")
        print(f"  2. POST {UPLOAD_URL}?uploadType=resumable&part=snippet,"
              "status  (returns the upload URL)")
        print("  3. PUT the file bytes to that URL  (resumable upload)")
        print(f"  4. GET {API_URL}/videos?part=status&id=<id>  (poll until "
              "succeeded)")
        print("file:", args.file)
        print("title:", args.title[:100])
        print("privacy:", args.privacy)
        print("(nothing was uploaded)")
        return

    try:
        token = refresh_access(client_id, client_secret, refresh)
        video_id = upload_video(token, args.file, args.title,
                                args.description, args.privacy)
        wait_ready(token, video_id)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print("Posted! https://youtube.com/shorts/" + video_id)


if __name__ == "__main__":
    main()
