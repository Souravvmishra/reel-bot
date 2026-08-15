#!/usr/bin/env python3
"""
gh.py — minimal GitHub Contents API client (stdlib only).

Used to host the reel at a raw.githubusercontent.com URL and to delete it
again once Instagram has processed the video. The source URL is only
needed while Meta downloads/processes the container (status FINISHED), so
deleting it after publish keeps the repo clean.

Docs: https://docs.github.com/rest/repos/contents
"""

import base64
import json
import time
import urllib.error
import urllib.request

API = "https://api.github.com"


def _req(method, url, token, body=None):
    """One GitHub REST call; body is JSON-serialized when given. Returns
    the parsed JSON, or None for a 204 (successful DELETE). Raises
    HTTPError with the plain status for the caller to interpret."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "reel-pipeline/1.0",
    }
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status == 204:            # no content (e.g. successful DELETE)
            return None
        return json.loads(resp.read().decode())


def api_error(e):
    """Human-readable one-liner from a GitHub API HTTPError body."""
    try:
        body = json.loads(e.read().decode())
        return f"GitHub API error: {body.get('message', 'unknown')}"
    except Exception:
        return f"GitHub API error: HTTP {getattr(e, 'code', '?')}"


def default_branch(repo, token):
    """Default branch of a repo (avoids hardcoding 'main')."""
    return _req("GET", f"{API}/repos/{repo}", token).get("default_branch",
                                                         "main")


def raw_url(repo, branch, path):
    """Public raw URL a POST can point at; repo must be public."""
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"


def parse_raw_url(url):
    """Split a raw.githubusercontent.com URL into (repo, branch, path)."""
    parts = url.split("/")
    # https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path...>
    return "/".join(parts[3:5]), parts[5], "/".join(parts[6:])


def upload(repo, branch, path, filepath, token, message="upload reel"):
    """Create or OVERWRITE the file via the Contents API; returns the raw
    URL. Updating an existing file needs its current sha, so we fetch it
    first (404 = new file, no sha needed)."""
    with open(filepath, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    body = {"message": message, "content": content, "branch": branch}
    try:
        meta = _req("GET", f"{API}/repos/{repo}/contents/{path}", token)
        body["sha"] = meta["sha"]
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise RuntimeError(api_error(e)) from None
    try:
        _req("PUT", f"{API}/repos/{repo}/contents/{path}", token, body)
    except urllib.error.HTTPError as e:
        raise RuntimeError(api_error(e)) from None
    return raw_url(repo, branch, path)


def delete(repo, branch, path, token, message="delete reel after publish"):
    """DELETE the file (needs its current sha). Returns True if it was
    deleted, False if it was already gone."""
    try:
        meta = _req("GET", f"{API}/repos/{repo}/contents/{path}", token)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise RuntimeError(api_error(e)) from None
    try:
        _req("DELETE", f"{API}/repos/{repo}/contents/{path}", token,
             {"message": message, "sha": meta["sha"], "branch": branch})
    except urllib.error.HTTPError as e:
        raise RuntimeError(api_error(e)) from None
    return True


def wait_public(url, tries=15, delay=2):
    """Poll a raw URL until GitHub's CDN serves it with 200.

    A freshly pushed file can 404 for a few seconds while the CDN
    propagates, so we retry instead of racing the cache.
    """
    for i in range(1, tries + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                if resp.status == 200:
                    return True
        except urllib.error.HTTPError as e:
            if e.code != 404:             # 404 = CDN lag; anything else is real
                raise RuntimeError(api_error(e)) from None
        except Exception:
            pass
        time.sleep(delay)
    return False
