#!/usr/bin/env python3
"""
Upload the reel to a PUBLIC URL via GitHub — the only host the pipeline
uses. Deterministic by design: the GitHub Contents API is reliable from
any network, the raw URL is permanent (no expiry), and the same path is
overwritten on every run.

Flow:
  1. Push the file to GH_REPO (a PUBLIC repo) via the GitHub Contents API
     (gh.py). Overwrites the existing file at the same path.
  2. Wait until the raw URL serves HTTP 200 (GitHub's CDN lags a push by
     a few seconds - we retry instead of racing the cache).
  3. Print the raw URL, which is exactly what --video-url expects.

After the reel is published, the source file is deleted from the repo
automatically (post_instagram.py --cleanup-url, wired by content_agent.py
--post) - the URL is only needed while Instagram processes the video.

Needs in .env (gitignored):
    GH_REPO=owner/repo      # a PUBLIC repo
    GH_TOKEN=ghp_...        # token with Contents read/write on that repo

Usage:
    python3 upload_reel.py [--file x.mp4] [--name reel.mp4]
    python3 content_agent.py --post --video-url "$(python3 upload_reel.py)"
"""

import argparse
import os
import sys

import gh
from ig_common import load_env_file


def main():
    p = argparse.ArgumentParser(
        description="Host the reel at a public GitHub raw URL")
    p.add_argument("--file", default="post-reel.mp4",
                   help="local file to upload (default post-reel.mp4)")
    p.add_argument("--name", default=None,
                   help="filename in the repo (default: file name)")
    args = p.parse_args()

    load_env_file()
    repo = os.environ.get("GH_REPO")
    token = os.environ.get("GH_TOKEN")
    if not repo or not token:
        print("Error: hosting needs GH_REPO (owner/repo) and GH_TOKEN in "
              ".env (see IG_SETUP.md).", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(args.file):
        print(f"Error: {args.file} not found - render it first with "
              f"python3 content_agent.py --video", file=sys.stderr)
        sys.exit(1)

    try:
        branch = gh.default_branch(repo, token)
        path = args.name or os.path.basename(args.file)
        url = gh.upload(repo, branch, path, args.file, token)
        if not gh.wait_public(url):
            raise RuntimeError(f"raw URL still not serving after 30s: {url}")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"(uploaded to github.com/{repo}, branch {branch})", file=sys.stderr)
    print(url)


if __name__ == "__main__":
    main()
