#!/usr/bin/env python3
"""
Exchange a short-lived Graph API token (from the Graph API Explorer) for a
long-lived one (~60 days), using the official fb_exchange_token endpoint.

The Explorer token you generate in Step 6 of docs/IG_SETUP.md lasts ~1 hour. This
helper turns it into a ~60-day token so you don't regenerate it constantly.

Needs the app id and secret (App dashboard -> App settings -> Basic):

    echo 'FB_APP_ID=your_app_id' >> .env
    echo 'FB_APP_SECRET=your_app_secret' >> .env

Usage:
    python3 long_live_token.py                              # exchange IG_ACCESS_TOKEN from .env
    python3 long_live_token.py --token EAAG...              # exchange a specific token
    python3 long_live_token.py --write                      # also save it to .env as IG_ACCESS_TOKEN
    python3 long_live_token.py --app-id 123 --app-secret abc
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from ig_common import FB_HOST, format_api_error, load_env_file, set_env


def main():
    p = argparse.ArgumentParser(
        description="Exchange a short-lived Graph API token for a "
                    "long-lived (~60 day) one")
    p.add_argument("--token", default=None,
                   help="short-lived token (default: IG_ACCESS_TOKEN from .env)")
    p.add_argument("--app-id", default=None,
                   help="Meta app id (default: FB_APP_ID from .env)")
    p.add_argument("--app-secret", default=None,
                   help="Meta app secret (default: FB_APP_SECRET from .env)")
    p.add_argument("--write", action="store_true",
                   help="save the long-lived token into .env as "
                        "IG_ACCESS_TOKEN")
    args = p.parse_args()

    load_env_file()
    token = args.token or os.environ.get("IG_ACCESS_TOKEN")
    app_id = args.app_id or os.environ.get("FB_APP_ID")
    secret = args.app_secret or os.environ.get("FB_APP_SECRET")

    if not token:
        print("Missing token. Either pass --token EAAG... or set "
              "IG_ACCESS_TOKEN in .env (see docs/IG_SETUP.md step 6).")
        sys.exit(1)
    if not app_id or not secret:
        print("Missing app id/secret. Add to .env:")
        print("  FB_APP_ID=your_app_id")
        print("  FB_APP_SECRET=your_app_secret")
        print("(App dashboard -> App settings -> Basic)")
        sys.exit(1)

    params = {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": secret,
        "fb_exchange_token": token,
    }
    # The long-lived exchange is a Facebook OAuth endpoint - it always lives
    # on graph.facebook.com, regardless of the token type being exchanged.
    url = f"{FB_HOST}/oauth/access_token?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"Error: {format_api_error(e)}", file=sys.stderr)
        sys.exit(1)

    long_token = data.get("access_token")
    if not long_token:
        print("Error: no access_token in response", file=sys.stderr)
        sys.exit(1)

    days = data.get("expires_in", 0) / 86400
    print(f"long-lived token (expires in ~{days:.0f} days):")
    print(long_token)
    if args.write:
        set_env(".env", "IG_ACCESS_TOKEN", long_token)
        print("\nSaved to .env as IG_ACCESS_TOKEN.")
        print("Verify with:  python3 post_instagram.py --check")


if __name__ == "__main__":
    main()
