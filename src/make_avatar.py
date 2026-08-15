#!/usr/bin/env python3
"""
Render the profile picture used in the posts as a square PNG ready to
upload to Instagram.

By default this is the green-gradient silhouette placeholder (the same art
that appears on every post); pass --avatar photo.jpg to cover-crop a real
photo instead. Instagram shows profile pics as a circle, so a full square
(no rounded mask) is what we want - it fills the circular crop perfectly.

Usage:
    python3 make_avatar.py                          # -> profile_pic.png (1080x1080)
    python3 make_avatar.py --output pic.png --size 320
    python3 make_avatar.py --avatar photo.jpg       # cover-crop a real photo
"""

import argparse

from make_post import avatar_square


def main():
    p = argparse.ArgumentParser(
        description="Render the profile picture used in the posts")
    p.add_argument("--output", default="profile_pic.png")
    p.add_argument("--size", type=int, default=1080,
                   help="square size in px (default 1080)")
    p.add_argument("--avatar", default=None,
                   help="path to a photo to cover-crop instead of the "
                        "silhouette placeholder")
    args = p.parse_args()

    img = avatar_square(args.size, args.avatar)
    img.save(args.output)
    print(f"saved {args.output} ({img.size[0]}x{img.size[1]})")


if __name__ == "__main__":
    main()
