#!/usr/bin/env python3
"""
post_api.py — turn the reel pipeline into a hosted HTTP API.

Hit POST /post and the service generates a fresh reel, hosts it on GitHub,
publishes it to Instagram via the official Graph API, deletes the GitHub
source, and returns the permalink.

Endpoints:
    GET  /health                     account + publishing quota (read-only)
    POST /post                       run the full pipeline
         headers: X-API-Key: <API_KEY>
         ?dry_run=true               generate + host but do NOT publish
         ?no_audio=true              render a silent reel (no local music)
         ?theme=<topic>              pin the checklist subject

Needs env vars (see IG_SETUP.md): API_KEY, GOOGLE_API_KEY,
IG_ACCESS_TOKEN, IG_USER_ID, GH_REPO, GH_TOKEN.  (AUDIO_PATH optional.)

Run locally:
    .venv/bin/uvicorn post_api:app --port 8787

Deploy (free): see Dockerfile + render.yaml, or skip the server entirely
and use .github/workflows/post_reel.yml — a GitHub Actions schedule that
runs the same pipeline with no hosting at all.
"""

import json
import os
import re
import secrets
import subprocess
import sys
import threading

from fastapi import FastAPI, Header, HTTPException, Query

from content_agent import build_caption, norm_tags
from ig_common import Graph, load_env_file

HERE = os.path.dirname(os.path.abspath(__file__))
CONTENT_AGENT = os.path.join(HERE, "content_agent.py")
UPLOAD_REEL = os.path.join(HERE, "upload_reel.py")
POST_IG = os.path.join(HERE, "post_instagram.py")
HISTORY = os.path.join(HERE, "post_history.json")

# Step timeouts: generous, since fresh Gemini drafts + video encode + IG
# processing can each take a while.
GENERATE_TIMEOUT = 300
UPLOAD_TIMEOUT = 120
POST_TIMEOUT = 420

app = FastAPI(title="reel-post-api", version="1.0.0")
_lock = threading.Lock()

load_env_file()
API_KEY = os.environ.get("API_KEY", "")


def _require_key(x_api_key):
    if not API_KEY:
        raise HTTPException(503, "server misconfigured: API_KEY not set")
    if not x_api_key or not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(401, "invalid or missing X-API-Key")


def _run(cmd, timeout):
    """Run a pipeline step; raise a clean 504 on timeout."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, f"timed out after {timeout}s: "
                                 f"{' '.join(cmd)}")


def _check(proc, step):
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout).strip().splitlines()
        raise HTTPException(500, f"{step} failed: {err[-1] if err else '?'}")


def _latest_draft():
    """The draft content_agent just recorded (intro/items/hashtags)."""
    with open(HISTORY, encoding="utf-8") as f:
        history = json.load(f)
    if not history:
        raise HTTPException(500, "no draft recorded by content_agent")
    return history[-1]


@app.get("/health")
def health():
    """Read-only: account identity + today's publishing quota."""
    load_env_file()
    token = os.environ.get("IG_ACCESS_TOKEN")
    user_id = os.environ.get("IG_USER_ID")
    if not token:
        return {"ok": False, "error": "IG_ACCESS_TOKEN not set"}
    try:
        g = Graph(token)
        me = g.get("me", {"fields": "id,username,account_type"})
        limit = g.get(f"{user_id or me.get('id')}/content_publishing_limit",
                      {})
        used = limit.get("data", [{}])[0].get("quota_usage", "?")
        return {
            "ok": True,
            "account": f"@{me.get('username')}",
            "ig_user_id": me.get("id"),
            "quota_used_today": used,
            "github_repo": os.environ.get("GH_REPO"),
        }
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}


@app.post("/post")
def post(x_api_key: str = Header(default=""),
         dry_run: bool = Query(False),
         no_audio: bool = Query(False),
         theme: str = Query(None)):
    """Run the full pipeline: generate -> host -> publish -> cleanup."""
    _require_key(x_api_key)
    if not _lock.acquire(blocking=False):
        raise HTTPException(409, "a post is already running")
    try:
        return _post(dry_run, no_audio, theme)
    finally:
        _lock.release()


def _post(dry_run, no_audio, theme):
    # 1) Write + render + encode the reel (fresh Gemini draft).
    cmd = [sys.executable, CONTENT_AGENT, "--video"]
    if no_audio:
        cmd.append("--no-audio")
    if theme:
        cmd += ["--theme", theme]
    _check(_run(cmd, GENERATE_TIMEOUT), "generate")

    # 2) Host it on GitHub -> public raw URL.
    up = _run([sys.executable, UPLOAD_REEL], UPLOAD_TIMEOUT)
    _check(up, "upload")
    url = up.stdout.strip().splitlines()[-1]

    # 3) Caption from the draft the generator just recorded.
    draft = _latest_draft()
    caption = build_caption(draft["intro"], norm_tags(draft.get("hashtags")))

    if dry_run:
        return {"posted": False, "video_url": url, "caption": caption}

    # 4) Publish via the official Graph API; delete the GitHub source after.
    out = _run([sys.executable, POST_IG, "--video-url", url,
                "--caption", caption, "--cleanup-url", url], POST_TIMEOUT)
    _check(out, "post")
    m = re.search(r"Posted!\s+(\S+)", out.stdout)
    return {
        "posted": True,
        "permalink": m.group(1) if m else None,
        "video_url": url,
        "caption": caption,
    }
