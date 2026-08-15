#!/usr/bin/env python3
"""
Comment bot — official Instagram Graph API only.

For every NEW comment on your latest post, replies with a single random
word. Nothing else happens on comment (no links, no CTA, no DM attempt).

API calls it makes (all official):
  GET  /me?fields=username              who am I (to skip own comments)
  GET  /{ig-user-id}/media              latest post
  GET  /{media-id}/comments             list comments
  POST /{comment-id}/replies            reply with a random word

Needs in .env: IG_ACCESS_TOKEN and IG_USER_ID (see IG_SETUP.md).
Works in Development mode: the comments endpoints just need
instagram_manage_comments granted for your own account.

Usage:
    python3 comment_bot.py                    # one pass over new comments
    python3 comment_bot.py --once             # same (default)
    python3 comment_bot.py --sleep 60         # poll forever, every 60s
    python3 comment_bot.py --reset            # forget everything already replied

State (which comments got a reply) is kept in comment_state.json so a
comment is never replied to twice.
"""

import argparse
import datetime
import json
import os
import random
import sys
import time

from ig_common import Graph, load_env_file

# Single-word, on-brand replies. "Just a random word."
WORDS = [
    "lol", "same", "relatable", "hehe", "yep", "ok", "hi", "hey",
    "valid", "real", "felt", "mood", "facts", "true", "big", "oof",
    "ah", "haha", "yes", "okay",
]

STATE_PATH = "comment_state.json"


def ts():
    return datetime.datetime.now().strftime("%H:%M:%S")


def load_state(path):
    """State file shape: {"replied": {<comment-id>: {...info...}}}."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("replied"), dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {"replied": {}}


def save_state(path, state):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def latest_post(g, user_id):
    """Most recent media on the account, or None if there are no posts."""
    media = g.get(f"{user_id}/media",
                  {"fields": "id,permalink,timestamp", "limit": 5})
    posts = media.get("data") or []
    if not posts:
        return None
    # The API returns newest first, but sort defensively by timestamp.
    return sorted(posts, key=lambda m: m.get("timestamp", ""),
                  reverse=True)[0]


def one_pass(g, user_id, state_path):
    """Reply to every new comment on the latest post. Returns count."""
    state = load_state(state_path)
    replied = state["replied"]

    my_user = g.get("me", {"fields": "username"}).get("username", "?")

    post = latest_post(g, user_id)
    if post is None:
        print(f"{ts()} no posts yet - nothing to do")
        return 0
    print(f"{ts()} latest post: {post['id']} ({post.get('timestamp', '?')})")

    comments = g.get(f"{post['id']}/comments",
                     {"fields": "id,text,username,timestamp", "limit": 100})

    acted = 0
    for c in comments.get("data") or []:
        cid = c["id"]
        if cid in replied:
            continue                      # already answered
        if c.get("username") == my_user:  # never reply to ourselves
            continue
        word = random.choice(WORDS)
        g.post(f"{cid}/replies", {"message": word})
        replied[cid] = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "word": word,
            "from": c.get("username"),
            "text": c.get("text", ""),
        }
        print(f'{ts()} replied "{word}" to @{c.get("username")}: '
              f'"{c.get("text", "")[:40]}"')
        acted += 1

    if acted == 0:
        print(f"{ts()} no new comments")
    save_state(state_path, state)
    return acted


def main():
    p = argparse.ArgumentParser(
        description="Reply to new comments on the latest post with a random "
                    "word (official Graph API)")
    p.add_argument("--once", action="store_true",
                   help="one pass, then exit (default)")
    p.add_argument("--sleep", type=float, default=60.0,
                   help="seconds between passes in loop mode (default 60)")
    p.add_argument("--reset", action="store_true",
                   help="forget everything already replied, then run")
    p.add_argument("--state", default=STATE_PATH,
                   help=f"state file (default {STATE_PATH})")
    args = p.parse_args()

    load_env_file()
    token = os.environ.get("IG_ACCESS_TOKEN")
    user_id = os.environ.get("IG_USER_ID")
    if not token or not user_id:
        print("Missing IG_ACCESS_TOKEN and/or IG_USER_ID in .env "
              "(see IG_SETUP.md step 6).", file=sys.stderr)
        sys.exit(1)

    if args.reset and os.path.exists(args.state):
        os.remove(args.state)
        print(f"{ts()} reset {args.state}")

    g = Graph(token)
    while True:
        try:
            one_pass(g, user_id, args.state)
        except RuntimeError as e:
            print(f"{ts()} Error: {e}", file=sys.stderr)
        if args.once:
            return
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()
