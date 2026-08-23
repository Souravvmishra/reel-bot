#!/usr/bin/env python3
"""
Recreate the "why is my life so bad" checklist post as a PNG with Pillow,
matching the layout of the saved reference screenshot (736 x ~654 px).

Usage:
    python3 make_post.py                       # -> post.png
    python3 make_post.py --output out.png
    python3 make_post.py --username someone --timestamp "2 Feb"
    python3 make_post.py --avatar photo.jpg    # real profile picture
"""

import argparse
import datetime

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# CONFIG — edit anything here and re-run the script.
# ---------------------------------------------------------------------------

DEJAVU   = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DEJAVU_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# colors (sampled from the reference screenshot)
BG       = (34, 34, 34)      # page background
TEXT     = (235, 235, 235)   # body text
USER_C   = (240, 240, 240)   # username (bold white)
TS_C     = (134, 134, 134)   # timestamp (muted gray)
FOLLOW_C = (40, 110, 155)    # follow button (blue)
DOTS_C   = (158, 158, 158)   # three-dot menu
AV_BG1   = (110, 126, 88)    # avatar gradient (greenish, like reference)
AV_BG2   = (74, 92, 60)
AV_SK    = (198, 200, 164)   # avatar silhouette

DEFAULT_USERNAME  = "mongoliassweetheart"
DEFAULT_TIMESTAMP = None  # None -> automatically today's date, e.g. "15 Aug"
DEFAULT_INTRO     = 'a quick \u201cwhy is my life so bad\u201d checklist'
DEFAULT_ITEMS     = [
    "how\u2019s your sleep schedule",
    "have you eaten or drank anything besides sugar and caffeine",
    "how long have you been sitting in one spot",
    "have you gone out in public recently",
    "have you taken a shower/brushed your teeth/groomed yourself properly",
    "have you spent time doing an activity that doesn\u2019t involve a screen",
    "etc",
]

# --- layout, measured from the reference screenshot at W=736 ---------------
W             = 750
AV_X, AV_Y    = 31, 31
AV_SIZE       = 52
USER_X        = 106
USER_TOP      = 38
TS_X, TS_TOP  = 114, 68
FOLLOW_GAP    = 21          # gap between username and Follow
DOTS_RIGHT    = 712         # right edge of the three-dot menu
DOTS_Y        = 45.5
DOTS_R        = 5.5
DOTS_STEP     = 23
BODY_LEFT     = 31          # intro / left margin
BULLET_CX     = 57          # bullet center
TEXT_X        = 93          # bullet text / hanging indent
INTRO_TOP     = 120
LINE_H        = 46          # line-to-line spacing within same item
INTRO_EXTRA   = 24          # extra space after the intro (hierarchy)
BULLET_EXTRA  = 18          # extra space between different bullet points
BOTTOM_PAD    = 36
AV_RADIUS     = 10

BODY_SIZE     = 26          # body font size
USER_SIZE     = 19          # username font size
FOLLOW_SIZE   = 16
TS_SIZE       = 15
WRAP_WIDTH    = 560         # max text width before wrapping (shorter for readability)

# ---------------------------------------------------------------------------


def font(size, bold=False):
    """Load the DejaVu TrueType font at `size` (bold variant optional)."""
    return ImageFont.truetype(DEJAVU_B if bold else DEJAVU, size)


def diag_gradient(w, h, c1, c2):
    """Diagonal two-color gradient image (the avatar background)."""
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = (x + y) / (w + h - 2)
            px[x, y] = (
                round(c1[0] + (c2[0] - c1[0]) * t),
                round(c1[1] + (c2[1] - c1[1]) * t),
                round(c1[2] + (c2[2] - c1[2]) * t),
            )
    return img


def avatar_square(size, path=None):
    """Full-square avatar: a cover-cropped photo or the gradient +
    silhouette placeholder (no rounded mask). This is what Instagram
    profile pictures use - the app crops them to a circle itself."""
    if path:
        # Cover-crop the photo to a square (like the app's avatar crop).
        img = Image.open(path).convert("RGB")
        w, h = img.size
        s = max(size / w, size / h)
        img = img.resize((round(w * s), round(h * s)), Image.LANCZOS)
        x, y = (img.width - size) // 2, (img.height - size) // 2
        return img.crop((x, y, x + size, y + size)).convert("RGBA")
    # Placeholder: head + shoulders on the brand gradient, same geometry
    # as the reference screenshot (coordinates are in /48 units of size).
    img = diag_gradient(size, size, AV_BG1, AV_BG2).convert("RGBA")
    d = ImageDraw.Draw(img)
    r = size / 48
    d.ellipse([(24 - 8) * r, (16.5 - 8) * r, (24 + 8) * r, (16.5 + 8) * r],
              fill=AV_SK)                       # head
    d.ellipse([(24 - 13.5) * r, (38.5 - 9.5) * r, (24 + 13.5) * r,
               (38.5 + 9.5) * r], fill=AV_SK)   # shoulders
    return img


def avatar(size, path=None):
    """Rounded-square avatar as shown in a post header - the square
    avatar with a rounded-corner mask applied."""
    img = avatar_square(size, path)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=round(AV_RADIUS * size / 48),
        fill=255)
    img.putalpha(mask)
    return img


def wrapped(draw, text, fnt, max_w):
    """Greedy word-wrap; also allows breaking after "/" (like the app)."""
    import re
    text = text.replace("/", "/\u200b")          # zero-width break after /
    words = [t for t in re.split(r"[ \u200b]+", text) if t]
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=fnt) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return [ln.replace("\u200b", "") for ln in lines] or [""]


def make_post(output, username=DEFAULT_USERNAME, timestamp=DEFAULT_TIMESTAMP,
              intro=DEFAULT_INTRO, items=None, avatar_path=None, reel=False,
              reel_scale=1.3):
    """Render the checklist card to `output`; with reel=True also write the
    1080x1920 reel canvas at `<output stem>-reel.png`."""
    items = items or DEFAULT_ITEMS
    if timestamp is None:                     # auto: today's date, "15 Aug"
        today = datetime.date.today()
        timestamp = f"{today.day} {today.strftime('%b')}"

    f_user   = font(USER_SIZE, bold=True)
    f_follow = font(FOLLOW_SIZE, bold=True)
    f_ts     = font(TS_SIZE)
    f_body   = font(BODY_SIZE)

    meas = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    # header: username width -> Follow sits right after it
    user_w = meas.textlength(username, font=f_user)
    follow_w = meas.textlength("Follow", font=f_follow)
    follow_x = USER_X + user_w + FOLLOW_GAP
    dots_w = 3 * (2 * DOTS_R) + 2 * (DOTS_STEP - 2 * DOTS_R)
    dots_x0 = DOTS_RIGHT - dots_w

    # body layout (wrap each paragraph)
    layout = []                      # list of (is_bullet, [lines...])
    intro_w = W - BODY_LEFT - 30
    layout.append((False, wrapped(meas, intro, f_body, intro_w)))
    for it in items:
        layout.append((True, wrapped(meas, it, f_body, WRAP_WIDTH)))

    n_lines = sum(len(ls) for _, ls in layout)
    n_bullets = sum(1 for is_bullet, _ in layout if is_bullet)
    body_h = LINE_H * (n_lines - 1) + INTRO_EXTRA + BULLET_EXTRA * n_bullets
    # height: from avatar top to last text baseline, plus bottom pad
    last_top = INTRO_TOP + body_h
    ascent, descent = f_body.getmetrics()
    H = last_top + ascent + descent + BOTTOM_PAD

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # avatar
    av = avatar(AV_SIZE, avatar_path)
    img.paste(av, (AV_X, AV_Y), av)

    # username + follow (same line)
    u_asc, _ = f_user.getmetrics()
    d.text((USER_X, USER_TOP + u_asc), username, font=f_user,
           fill=USER_C, anchor="ls")
    d.text((follow_x, USER_TOP + u_asc), "Follow", font=f_follow,
           fill=FOLLOW_C, anchor="ls")

    # three-dot menu (top right)
    for i in range(3):
        cx = dots_x0 + DOTS_R + i * DOTS_STEP
        d.ellipse([cx - DOTS_R, DOTS_Y - DOTS_R, cx + DOTS_R, DOTS_Y + DOTS_R],
                  fill=DOTS_C)

    # timestamp
    ts_asc, _ = f_ts.getmetrics()
    d.text((TS_X, TS_TOP + ts_asc), timestamp, font=f_ts, fill=TS_C,
           anchor="ls")

    # body
    b_asc, _ = f_body.getmetrics()
    y = INTRO_TOP
    for is_bullet, lines in layout:
        for i, ln in enumerate(lines):
            baseline = y + b_asc
            x = BODY_LEFT if (not is_bullet) else TEXT_X
            if is_bullet and i == 0:
                d.text((BULLET_CX, baseline), "\u2022", font=f_body,
                       fill=TEXT, anchor="ms")
            d.text((x, baseline), ln, font=f_body, fill=TEXT, anchor="ls")
            y += LINE_H
        if is_bullet:
            y += BULLET_EXTRA
        elif len(layout) > 1:
            y += INTRO_EXTRA

    img.save(output)
    print(f"Wrote {output} ({img.width}x{img.height}px)")

    if reel:
        # place the (scaled-up) post on a 9:16 Instagram Reel canvas
        reel_w, reel_h = 1080, 1920
        card = img.resize(
            (round(img.width * reel_scale), round(img.height * reel_scale)),
            Image.LANCZOS)
        canvas = Image.new("RGB", (reel_w, reel_h), BG)
        canvas.paste(card, ((reel_w - card.width) // 2,
                            (reel_h - card.height) // 2))
        reel_out = output.replace(".png", "-reel.png")
        canvas.save(reel_out)
        print(f"Wrote {reel_out} ({canvas.width}x{canvas.height}px, "
              f"card at {reel_scale:.2f}x)")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Generate the post mockup PNG")
    p.add_argument("--output", default="post.png")
    p.add_argument("--username", default=DEFAULT_USERNAME)
    p.add_argument("--timestamp", default=DEFAULT_TIMESTAMP)
    p.add_argument("--intro", default=DEFAULT_INTRO)
    p.add_argument("--item", action="append", dest="items",
                   help="checklist item (repeatable; overrides defaults)")
    p.add_argument("--avatar", default=None,
                   help="path to a photo to use as the profile picture")
    p.add_argument("--reel", action="store_true",
                   help="also place the post on an Instagram Reel 9:16 canvas")
    p.add_argument("--reel-scale", type=float, default=1.3,
                   help="how much to scale up the post on the reel canvas "
                        "(default 1.3)")
    args = p.parse_args()
    make_post(args.output, args.username, args.timestamp, args.intro,
              args.items, args.avatar, args.reel, args.reel_scale)
