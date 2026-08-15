#!/usr/bin/env python3
"""
Post the reel to Instagram using the OFFICIAL Instagram Graph API.
No unofficial libraries, no account-password login - just the sanctioned
Meta API with an access token.

One-time setup (about 15 minutes, do it once — full guide in docs/IG_SETUP.md):

  1. Your Instagram must be a Business or Creator account.
  2. It must be linked to a Facebook Page you manage.
  3. Create a Business app at https://developers.facebook.com/apps with
     the Instagram product, then generate an access token (see docs/IG_SETUP.md
     step 6 for the two token paths: the new dashboard IGAA tokens or the
     Graph API Explorer EAAG tokens).
  4. The reel must be reachable at a PUBLIC URL - the API downloads the
     video from the internet and cannot read local files.

Store in .env (already gitignored):
    IG_ACCESS_TOKEN=EAAG...      # required
    IG_USER_ID=1784...           # required for IGAA tokens; optional otherwise

Usage:
    python3 post_instagram.py --video-url https://host/post-reel.mp4 --caption "text"
    python3 post_instagram.py --dry-run        # print the exact calls, post nothing
    python3 post_instagram.py --check          # read-only: token + account + permissions
"""

import argparse
import os
import sys
import time

import gh
from ig_common import Graph, load_env_file

# How long to wait for Instagram to process the video before giving up.
# Fresh uploads to a public host can take a few minutes, so this is
# generous (5s x 30 = up to ~2.5 minutes).
POLL_SECONDS = 5
POLL_TRIES = 30


def check_token(g, user_id=None):
    """Read-only verification: who the token is, which IG account is
    linked, and which permissions are granted. Posts nothing."""
    print("checking token ...")
    if g.token.startswith("IGAA"):
        # New-flow Instagram token: graph.instagram.com has no /me/accounts
        # or /me/permissions, so verify via /me + content_publishing_limit.
        me = g.get("me", {"fields": "id,username,account_type"})
        print(f"  IG account: @{me.get('username', '?')} "
              f"(id {me.get('id', '?')}, {me.get('account_type', '?')})")
        if not user_id:
            print("  NOTE: add IG_USER_ID to .env - this token type can't "
                  "auto-find it (see docs/IG_SETUP.md)")
        limit = g.get(f"{user_id or me.get('id')}/content_publishing_limit",
                      {})
        used = limit.get("data", [{}])[0].get("quota_usage", "?")
        print(f"  publishing quota used today: {used}/25")
        print("  permissions are bundled in the token - ready to post")
        return

    # Classic Graph API token: inspect user, linked page and permissions.
    me = g.get("me", {"fields": "id,name"})
    print(f"  token user: {me.get('name', '?')} (id {me.get('id', '?')})")

    # pages_show_list is only needed when the IG user id must be resolved
    # from the token. If IG_USER_ID is set, /me/accounts is skipped.
    need = {"instagram_basic", "instagram_content_publish"}
    if user_id:
        print(f"  using IG user id from .env: {user_id} "
              "(skipping /me/accounts)")
    else:
        need.add("pages_show_list")
        accounts = g.get("me/accounts",
                         {"fields": "id,name,"
                                    "instagram_business_account{id,username}"})
        if not accounts.get("data"):
            print("  no Facebook Pages found on this token "
                  "(needs pages_show_list)")
        for page in accounts["data"]:
            ig = page.get("instagram_business_account")
            if ig:
                print(f"  linked IG: @{ig.get('username', '?')} "
                      f"(id {ig['id']}) via Page '{page.get('name')}'")
            else:
                print(f"  Page '{page.get('name')}' has no linked "
                      "Instagram account")

    perms = g.get("me/permissions", {})
    rows = [(p.get("permission"), p.get("status"))
            for p in perms.get("data", [])]
    for perm, status in sorted(rows):
        ok = "  <-- OK" if (perm in need and status == "granted") else ""
        print(f"  perm: {perm} = {status}{ok}")
    missing = sorted(need - {p for p, s in rows if s == "granted"})
    if missing:
        print("  missing / not granted: " + ", ".join(missing))
        print("  -> fix: either regenerate the token with those permissions "
              "selected, or set IG_USER_ID in .env to skip page lookup")
    else:
        print("  all required permissions granted - ready to post")


def resolve_user_id(g, user_id):
    """Ensure we have the IG user id; resolves it from the token when
    possible (classic tokens only — IGAA tokens can't auto-find it)."""
    if user_id:
        return user_id
    print("resolving your Instagram account id from the token ...")
    accounts = g.get("me/accounts",
                     {"fields": "instagram_business_account{id,username}"})
    for page in accounts.get("data", []):
        ig = page.get("instagram_business_account")
        if ig:
            print(f"  found: @{ig.get('username', '?')} (id {ig['id']})")
            return ig["id"]
    print("Could not find an Instagram Business/Creator account "
          "linked to this token's Page.")
    print("Check that: your IG is a professional account, it's linked to "
          "a Facebook Page, and the app has instagram_basic + "
          "instagram_content_publish.")
    sys.exit(1)


def publish(g, user_id, video_url, caption):
    """The 4 official calls: container -> poll -> publish -> permalink."""
    # 1) Create the REELS media container (the API downloads the video).
    print("creating media container ...")
    container = g.post(f"{user_id}/media", {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true",
    })["id"]
    print(f"  container id: {container}")

    # 2) Poll until Instagram has finished fetching/processing the video.
    print("waiting for Instagram to process the video ...")
    for _ in range(POLL_TRIES):
        time.sleep(POLL_SECONDS)
        status = g.get(container, {"fields": "status_code"})
        code = status.get("status_code")
        print(f"  status: {code}")
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise RuntimeError(f"Media processing failed: {status}")
    else:
        raise RuntimeError(
            f"Still processing after {POLL_TRIES * POLL_SECONDS}s - the "
            f"container (id {container}) may finish later; re-check it "
            f"with GET /{container}?fields=status_code and publish with "
            f"POST /{user_id}/media_publish. Also check the video URL is "
            "publicly reachable.")

    # 3) Publish, then print the permalink.
    print("publishing ...")
    media_id = g.post(f"{user_id}/media_publish",
                      {"creation_id": container})["id"]
    permalink = g.get(media_id, {"fields": "permalink"})
    print("Posted!",
          permalink.get("permalink",
                        f"https://www.instagram.com/reel/{media_id}/"))
    return permalink.get("permalink")


def cleanup_github_source(url, token):
    """Delete the source video from GitHub after a successful publish.

    The raw URL is only needed while Instagram downloads/processes the
    video (container status FINISHED); once the reel is live the file can
    go, which keeps the repo clean. No-op for non-GitHub URLs.
    """
    if not url.startswith("https://raw.githubusercontent.com/"):
        return
    if not token:
        print("  (skipping GitHub cleanup - no GH_TOKEN in .env)")
        return
    try:
        repo, branch, path = gh.parse_raw_url(url)
        if gh.delete(repo, branch, path, token):
            print(f"  deleted source video from GitHub ({repo}/{path})")
        else:
            print(f"  source already gone from GitHub ({repo}/{path})")
    except RuntimeError as e:
        print(f"  (cleanup failed: {e})")


def main():
    p = argparse.ArgumentParser(
        description="Post the reel via the official Instagram Graph API")
    p.add_argument("--video-url", default=None,
                   help="PUBLIC https URL of the mp4 (the API downloads it)")
    p.add_argument("--caption", default="",
                   help="caption text (default empty)")
    p.add_argument("--cleanup-url", default=None,
                   help="after publishing, delete this source URL from "
                        "GitHub (needs --gh-token or GH_TOKEN in .env)")
    p.add_argument("--token", default=None,
                   help="override IG_ACCESS_TOKEN from .env")
    p.add_argument("--user-id", default=None,
                   help="override IG_USER_ID from .env (auto-detected if "
                        "omitted)")
    p.add_argument("--check", action="store_true",
                   help="read-only: verify the token, linked account and "
                        "permissions (posts nothing)")
    p.add_argument("--gh-token", default=None,
                   help="GitHub token for --cleanup-url (default: GH_TOKEN "
                        "from .env)")
    p.add_argument("--dry-run", action="store_true",
                   help="validate inputs and print the exact API calls, "
                        "without contacting Instagram")
    args = p.parse_args()

    load_env_file()
    token = args.token or os.environ.get("IG_ACCESS_TOKEN")
    user_id = args.user_id or os.environ.get("IG_USER_ID")

    if not token:
        print("Missing IG_ACCESS_TOKEN. Add it to .env:")
        print("  IG_ACCESS_TOKEN=EAAG...")
        sys.exit(1)

    g = Graph(token)

    if args.check:
        check_token(g, user_id)
        return

    if token.startswith("IGAA") and not user_id:
        print("Error: this Instagram token can't auto-find your IG user id."
              " Add it to .env:")
        print("  IG_USER_ID=<your ig user id>   (see docs/IG_SETUP.md step 6)")
        sys.exit(1)

    if not args.video_url:
        print("Error: --video-url <public URL of the mp4> is required "
              "(or use --dry-run with it, or --check)")
        sys.exit(1)
    if not (args.video_url.startswith("https://")
            or args.video_url.startswith("http://")):
        print(f"video-url must be a public http(s) URL, got: {args.video_url}")
        sys.exit(1)

    if args.dry_run:
        print("dry run - the real run would make these official Graph API "
              "calls:")
        if user_id:
            print(f"  1. POST {g.host}/{user_id}/media")
        else:
            print(f"  1. GET  {g.host}/me/accounts  (find your linked IG "
                  "account id)")
            print(f"  2. POST {g.host}/<ig-user-id>/media")
        print("        media_type=REELS, video_url=<your URL>, "
              "share_to_feed=true")
        print(f"  3. GET  <container-id>?fields=status_code  (poll until "
              "FINISHED)")
        print(f"  4. POST <ig-user-id>/media_publish")
        print("video url:", args.video_url)
        print("caption:", repr(args.caption))
        print("(nothing was uploaded)")
        return

    user_id = resolve_user_id(g, user_id)
    publish(g, user_id, args.video_url, args.caption)
    if args.cleanup_url:
        cleanup_github_source(args.cleanup_url,
                              args.gh_token or os.environ.get("GH_TOKEN"))


def run():
    """Entry wrapper: convert any RuntimeError into a clean stderr exit."""
    try:
        main()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
