#!/usr/bin/env python3
"""
ig_common.py — shared plumbing for every script that talks to the official
Instagram Graph API (post_instagram.py, comment_bot.py, long_live_token.py,
content_agent.py). Keeps the duplicate env-loading / HTTP / error-handling
code in one place.

Everything here is stdlib-only and uses the OFFICIAL Meta/Instagram Graph
API — no unofficial libraries, no password login.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

# Official hosts (v21.0 is the current stable Graph API version).
FB_HOST = "https://graph.facebook.com/v21.0"
IG_HOST = "https://graph.instagram.com/v21.0"

# Source files live in src/, one level under the project root (where the
# shared artifacts live: post-reel.mp4, post_history.json, audio/, ...).
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def project_path(*parts):
    """Join paths under the project root, independent of the CWD the script
    is launched from (running from a subdir must not lose the artifacts)."""
    return os.path.join(ROOT, *parts)


def load_env_file(path=".env"):
    """Load KEY=VALUE lines from a local .env into os.environ.

    Existing environment variables win (setdefault) and values may be
    quoted with ' or " — both are stripped. Missing file is a no-op. The
    path is resolved relative to the CWD first, then the project root, so
    scripts keep working no matter which directory they're launched from.
    """
    candidates = [path] if os.path.isabs(path) else \
        [path, os.path.join(ROOT, path)]
    for p in candidates:
        if os.path.exists(p):
            return _load_into(p)
    return None


def _load_into(path):
    """Read one .env file's KEY=VALUE lines into os.environ (setdefault)."""
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(),
                                  value.strip().strip('"').strip("'"))


def api_host(token):
    """Pick the right official host for a token.

    New-flow Instagram tokens start with IGAA and are bound to
    graph.instagram.com; classic tokens (EAA/EAAG...) live on
    graph.facebook.com. Sending one to the wrong host gets error 190.
    """
    return IG_HOST if token.startswith("IGAA") else FB_HOST


def set_env(path, key, value):
    """Add or replace a ``KEY=VALUE`` line in a .env file.

    Preserves every other line (including comments and blank lines) and
    only touches the one matching ``key=``. Shared by long_live_token.py
    and post_youtube.py, which both save their tokens this way.
    """
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    lines = [ln for ln in lines if not ln.startswith(key + "=")]
    lines.append(f"{key}={value}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def format_api_error(e):
    """Human-readable one-liner from a urllib HTTPError.

    Meta returns JSON bodies shaped like {"error": {"code", "message"}};
    fall back to the bare HTTP status when the body isn't JSON.
    """
    try:
        body = json.loads(e.read().decode())
        err = body.get("error", {})
        return (f"Instagram API error {err.get('code', '?')}: "
                f"{err.get('message', 'unknown')}")
    except Exception:
        return f"Instagram API error: HTTP {getattr(e, 'code', '?')}"


class Graph:
    """Minimal official Graph API client (stdlib urllib only).

    - Picks the host automatically from the token type.
    - Injects ``access_token`` on every call so callers pass only their
      own parameters.
    - Raises RuntimeError with a clean one-line message on API errors.

    Usage::

        g = Graph(token)
        me = g.get("me", {"fields": "id,username"})
        container = g.post(f"{user_id}/media", {
            "media_type": "REELS", "video_url": url, "caption": text,
            "share_to_feed": "true",
        })["id"]
    """

    def __init__(self, token):
        self.token = token
        self.host = api_host(token)

    # -- internals ------------------------------------------------------

    def _url(self, path):
        return f"{self.host}/{path}"

    def _request(self, req):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(format_api_error(e)) from None

    # -- public ---------------------------------------------------------

    def get(self, path, params):
        """GET a Graph API endpoint; params are URL-encoded query args."""
        params = dict(params)
        params.setdefault("access_token", self.token)
        url = self._url(path) + "?" + urllib.parse.urlencode(params)
        return self._request(urllib.request.Request(url))

    def post(self, path, params):
        """POST a Graph API endpoint; params become the form body."""
        params = dict(params)
        params.setdefault("access_token", self.token)
        data = urllib.parse.urlencode(params).encode()
        return self._request(urllib.request.Request(self._url(path),
                                                    data=data))
