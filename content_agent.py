#!/usr/bin/env python3
"""
Content agent — writes the text for self-care / relatable checklist posts
(the "why is my life so bad" genre) and hands it to make_post.py to render.

Usage:
    python3 content_agent.py --video                   # everything, one line
    python3 content_agent.py --post                    # ...and post it to IG
    python3 content_agent.py                            # one random draft
    python3 content_agent.py --theme sleep              # draft for a topic
    python3 content_agent.py --list-themes              # show available topics
    python3 content_agent.py --count 3                  # three drafts at once
    python3 content_agent.py --seed 7                   # reproducible draft
    python3 content_agent.py --agent local              # offline drafts
    python3 content_agent.py --render --reel            # also render images
    python3 content_agent.py --show-history             # see the last posts
    python3 content_agent.py --clear-history            # start over

Post history:
    Rendered posts are recorded in post_history.json. The agent remembers the
    last 5 posts and uses that memory to stay fresh: it rotates the checklist
    SUBJECT (so each post checks something different — money, room, friends,
    sleep...), excludes items already used, and rejects drafts whose items
    overlap too heavily with recent posts.

Gemini needs an API key (free at https://aistudio.google.com):
    echo 'GOOGLE_API_KEY=your_key' > .env
"""

import argparse
import datetime
import json
import os
import random
import re
import subprocess
import sys
import urllib.error
import urllib.request

from ig_common import load_env_file

# ---------------------------------------------------------------------------
# TOPICS — each is a different checklist SUBJECT with its own hooks and items.
# Rotating the subject is what keeps consecutive posts from feeling the same.
# ---------------------------------------------------------------------------

THEMES = {
    "screens": {
        "label": "Phone / doomscrolling zombie",
        "intros": [
            "a quick “why do i feel like a zombie” checklist",
            "the “my brain is fried from my phone” checklist",
            "a quick “why does everything feel like too much” checklist",
        ],
        "items": [
            "how many hours of screen time did you actually clock today",
            "have you looked at something that isn’t a screen since you woke up",
            "are you doom scrolling right now instead of doing the thing",
            "have you put your phone in another room for even one hour",
            "is your thumb developing a scroll callus",
            "did you compare your life to a stranger’s highlight reel today",
            "when did you last sit with your own thoughts, no podcast, no music",
            "did you check your phone out of boredom or out of need",
            "is your brain full of other people’s opinions right now",
            "have you watched one full video without skipping ahead",
        ],
    },
    "money": {
        "label": "Bank account crying",
        "intros": [
            "a quick “why is my bank account crying” checklist",
            "the “where did all my money go” checklist",
        ],
        "items": [
            "have you checked your balance (be brave)",
            "how many subscriptions are silently draining you every month",
            "did you buy something you didn’t need this week",
            "are you eating out because you’re too tired to cook",
            "have you impulse-bought something while sad",
            "is your anxiety actually just your credit card",
            "did you buy a coffee when there’s coffee at home",
            "are you avoiding opening your banking app",
            "have you paid that one bill you keep forgetting",
            "is ‘treat yourself’ becoming a lifestyle",
        ],
    },
    "room": {
        "label": "Room feels like a crime scene",
        "intros": [
            "a quick “why does my room feel like a crime scene” checklist",
            "the “my space is a disaster” checklist",
        ],
        "items": [
            "are there more cups in your room than in your kitchen",
            "has that pile of laundry become furniture",
            "when did you last change your sheets",
            "is your desk a landfill",
            "have you thrown away the trash that’s just… sitting there",
            "do you have 47 empty water bottles on your nightstand",
            "is your floor made of clothes",
            "have you opened your window this week",
            "is your space making your brain feel messier",
            "when did you last vacuum (ever)",
        ],
    },
    "friends": {
        "label": "Disconnected from people",
        "intros": [
            "a quick “why do i feel so disconnected” checklist",
            "the “everyone forgot about me” checklist",
            "a quick “why am i lonely despite having friends” checklist",
        ],
        "items": [
            "have you texted someone back (they’re not mad, they’re waiting)",
            "have you actually made plans or just said ‘we should hang’",
            "have you reached out first, like, ever",
            "is your friendship surviving on likes and streaks",
            "have you seen a friend in person this month",
            "are you isolating because you’re tired or because you’re scared",
            "have you told anyone how you’re actually doing",
            "is your best friend also just your phone",
            "have you replied ‘lol’ and called it a conversation",
            "when did you last hear a friend’s actual voice",
        ],
    },
    "work": {
        "label": "Dreading monday",
        "intros": [
            "a quick “why am i dreading monday” checklist",
            "the “my job is eating my soul” checklist",
        ],
        "items": [
            "have you taken a real lunch break or eaten at your desk",
            "are you answering emails at 11pm",
            "have you said no to one extra task this week",
            "is your to-do list 47 items long (that’s not a list, that’s a threat)",
            "have you actually taken your vacation days",
            "are you running on burnout and calling it hustle",
            "have you done the one task you keep avoiding all week",
            "is your work-life balance a complete lie",
            "have you logged off today or are you ‘just checking’",
            "do you remember why you took this job",
        ],
    },
    "body": {
        "label": "Body falling apart",
        "intros": [
            "a quick “why does my body hurt” checklist",
            "the “i’m 25 and my back is 80” checklist",
        ],
        "items": [
            "have you stretched in the last 72 hours",
            "are you sitting like a shrimp right now",
            "has your posture given up on life",
            "have you looked at something more than two feet from your face today",
            "is your neck doing that phone-tilt thing",
            "have you walked further than from your bed to your couch",
            "are your shoulders up by your ears",
            "have you unclenched your jaw (you’re welcome)",
            "when did you last move your body without a screen in front of it",
            "is your body trying to tell you something you’re ignoring",
        ],
    },
    "sleep": {
        "label": "Tired at 3pm",
        "intros": [
            "a quick “why am i tired at 3pm” checklist",
            "the “i slept 11 hours and i’m still exhausted” checklist",
        ],
        "items": [
            "what time did you actually go to bed (be honest)",
            "did you sleep or just lie in the dark with your phone",
            "have you had caffeine after 2pm",
            "is your room too bright, too hot, or too loud",
            "are you running on 5 hours and spite",
            "did you wake up to an alarm or to dread",
            "have you napped today and regretted it right away",
            "is your sleep schedule a suggestion",
            "have you been awake since 4am thinking about that thing",
            "did you scroll for ‘five minutes’ at midnight (it was two hours)",
        ],
    },
    "hygiene": {
        "label": "Feeling gross",
        "intros": [
            "a quick “why do i feel gross” checklist",
            "the “i haven’t showered and i’m fine with it (i’m not)” checklist",
        ],
        "items": [
            "have you showered today (or this week)",
            "have you brushed your teeth (both times)",
            "is your hair doing a thing",
            "have you changed your clothes or are you wearing yesterday’s",
            "have you washed your face",
            "are you wearing the same socks from tuesday",
            "have you looked in a mirror and flinched",
            "is your skincare routine ‘water, sometimes’",
            "when did you last do laundry",
            "do you smell like the ghost of your past self",
        ],
    },
    "outside": {
        "label": "Never leaving the house",
        "intros": [
            "a quick “why am i so pale and sad” checklist",
            "the “i live indoors now” checklist",
        ],
        "items": [
            "have you seen the sun today (it’s still there)",
            "have you touched grass, literally",
            "when did you last leave your house for a non-essential reason",
            "have you walked anywhere that isn’t to the fridge",
            "is your vitamin d level a single digit",
            "have you felt wind on your face",
            "are your curtains closed 24/7",
            "have you been outside in the last 48 hours",
            "is your outside voice a foreign language",
            "have you looked at a tree and felt something",
        ],
    },
    "anxiety": {
        "label": "Chest tight",
        "intros": [
            "a quick “why does my chest feel tight” checklist",
            "the “i’m anxious and i don’t know why” checklist",
            "a quick “why is my heart racing for no reason” checklist",
        ],
        "items": [
            "have you eaten or had water in the last six hours",
            "have you had way too much caffeine",
            "have you been doom scrolling bad news for hours",
            "have you taken ten slow breaths, like actually slow",
            "have you moved your body to burn off the nervous energy",
            "have you told someone how you feel",
            "is your body telling you to slow down",
            "are you anxious about something real or something your brain made up",
            "have you named what you’re scared of, out loud",
        ],
    },
    "brain": {
        "label": "Brain won’t shut up",
        "intros": [
            "a quick “why can’t my brain shut up” checklist",
            "the “i keep replaying that conversation” checklist",
            "a quick “why do i feel off” checklist",
        ],
        "items": [
            "have you eaten today (hungry thoughts aren’t real thoughts)",
            "is this problem happening right now or in your head",
            "would you say this out loud to your best friend",
            "have you taken five slow breaths",
            "what’s one thing you know is actually true",
            "is it 2am (go to sleep, nothing good happens after 2am)",
            "are you trying to solve a problem that hasn’t happened",
            "have you written the thought down so it stops looping",
            "is your brain replaying something from 2016",
        ],
    },
    "comparison": {
        "label": "Everyone else has it together",
        "intros": [
            "a quick “why does everyone have a better life than me” checklist",
            "the “everyone else has it together” checklist",
        ],
        "items": [
            "have you been comparing your behind-the-scenes to their highlight reel",
            "are you comparing your chapter one to their chapter twenty",
            "have you remembered they also post from their lowest moments",
            "is your feed making you feel small",
            "have you unfollowed the accounts that make you feel bad",
            "are you jealous or just tired",
            "have you done one thing today you’re proud of",
            "would you trade your whole life for theirs, problems included",
            "is ‘everyone else’ actually just five people you don’t know",
            "have you touched grass and realized the algorithm isn’t real life",
        ],
    },
    "eating": {
        "label": "Forgot to eat again",
        "intros": [
            "a quick “why am i so hangry” checklist",
            "the “i forgot to eat again” checklist",
        ],
        "items": [
            "have you eaten a meal that isn’t coffee",
            "when did you last eat something with actual nutrients",
            "are you running on sugar and vibes",
            "have you had a vegetable this week",
            "is your ‘lunch’ a granola bar you found in your bag",
            "are you hangry and blaming your friends",
            "have you drunk any water today (that ‘headache’ is thirst)",
            "did you skip breakfast and wonder why you’re crying",
            "is your diet 80 percent caffeine",
            "have you eaten at a table or standing over the sink",
        ],
    },
}

# "etc" is the genre's signature closer, so it stays dominant.
CLOSERS = [
    "etc",
    "etc",
    "etc",
    "and if you said no to all of these — take care of yourself",
    "or none of the above and you just need a hug",
]


# ---------------------------------------------------------------------------

def generate(theme, rng, max_items=7, used_intros=None, used_items=None):
    """Local draft for a topic. `used_items` are recent items to avoid."""
    t = THEMES[theme]
    intros = t["intros"]
    if used_intros:
        fresh = [x for x in intros if x not in used_intros]
        if fresh:
            intros = fresh
    intro = rng.choice(intros)
    pool = t["items"]
    if used_items:
        fresh = [x for x in pool if x not in used_items]
        if len(fresh) >= 4:
            pool = fresh
    hi = min(max_items, len(pool))
    lo = min(5, hi)
    n = rng.randint(lo, hi)
    items = rng.sample(pool, n)
    items.append(rng.choice(CLOSERS))
    return intro, items


HISTORY_PATH = "post_history.json"

# Default music for the reel video (used when --video is given without --audio).
DEFAULT_AUDIO = ("/home/sourav/Downloads/Video by shu_bruh_ "
                 "[DLwSbs4N06w].mp3")

# Fallback caption hashtags (no "#" prefix) - used when Gemini doesn't
# return its own, or in local-agent mode. With the Gemini agent, hashtags
# are generated per post.
DEFAULT_HASHTAGS = ["checklist", "selfcare", "mentalhealth", "relatable",
                    "checkinyourself", "dailyreminder"]

# Call-to-action line placed between the intro and the hashtags in the
# caption. Voice matches the posts (lowercase, curly apostrophes).
CTA = (
    "comment “PDF” and i’ll dm you a free pdf to fix your life 🫶 "
    "make sure you’re following so it goes through"
)


def load_history(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_history(path, history):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def _norm(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


def item_overlap(a, b):
    """Fraction of the shorter item list that the other one shares."""
    aa = {_norm(x) for x in a[:-1]}
    bb = {_norm(x) for x in b[:-1]}
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / min(len(aa), len(bb))


def is_duplicate(seen, intro, items):
    """True if the same hook, same item list, or >50% item overlap exists."""
    sig = tuple(_norm(x) for x in items[:-1])
    for h in seen:
        if h.get("intro") == intro:
            return True
        hsig = tuple(_norm(x) for x in (h.get("items") or [])[:-1])
        if sig and hsig == sig:
            return True
        if item_overlap(items, h.get("items") or []) > 0.5:
            return True
    return False


def vowel_groups(w):
    """Count vowel groups in a word (a rough syllable proxy)."""
    n = 0
    prev = False
    for ch in w:
        is_v = ch in "aeiouy"
        if is_v and not prev:
            n += 1
        prev = is_v
    return n


# Common long words that are fine to use - these are never flagged.
EASY_LONG = {
    "anniversary", "appointment", "appointments", "comfortable",
    "conversation", "conversations", "disappointed", "disconnected",
    "relationships", "subscription", "subscriptions", "temperature",
}


def find_hard_words(text):
    """Words likely to trip up a fast reader: very long, or long + many
    syllables. Used to reject drafts that break the easy-reading rule."""
    hard = set()
    for raw in re.findall(r"[a-zA-Z]+(?:['’][a-zA-Z]+)?", text.lower()):
        w = raw.strip("'’")
        if w in EASY_LONG:
            continue
        if len(w) > 12 or (len(w) >= 11 and vowel_groups(w) >= 4):
            hard.add(raw)
    return sorted(hard)


def print_draft(i, source, intro, items, subject=None, tags=None,
                width=58):
    label = THEMES[source]["label"] if source in THEMES else source
    print("━" * width)
    print(f"DRAFT {i}  · source: {label}")
    if subject:
        slabel = THEMES[subject]["label"] if subject in THEMES else subject
        print(f"subject: {slabel}")
    print("━" * width)
    print(intro)
    for it in items:
        print(f"• {it}")
    if tags:
        print("tags: " + " ".join("#" + t for t in tags))
    print()


GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "{model}:generateContent")

GEMINI_PROMPT = """You write short, viral self-care "checklist" posts for
Instagram/TikTok reels.

Genre rules:
- One hook line, dramatic or relatable, that ends in the word "checklist".
- Then 6-8 short checklist items written in a gentle, slightly
  self-deprecating, relatable tone.
- All lowercase. Use curly apostrophes (\u2019) and curly quotes (\u201c \u201d).

STRICT RULE - EASY READING (this is the MOST IMPORTANT rule, never break it):
- Write like a friend texting you. The post must flow easily and be readable
  in one quick glance on a phone.
- Use short, simple, everyday words ONLY. NO hard words, NO fancy vocabulary,
  NO words anyone would have to think about or look up.
- Always pick the shorter word: "use" not "utilize", "tired" not
  "exhausted", "messy" not "cluttered", "easy" not "effortless".
- Keep sentences short and natural. Read the post out loud - if it doesn't
  sound like how you'd actually talk, rewrite it.
- Keep every checklist line short and punchy.

Originality rules (important):
- Every post must feel genuinely fresh: a new hook, a new angle, mostly new
  items. Vary the item count, the phrasing, and the sentence patterns.
- Stay on THIS POST'S SUBJECT (given below). Every item must relate directly
  to that subject - do not drift back to the generic water/sleep/screen trio
  unless it genuinely fits the subject.
- Never reuse the same sentence patterns across posts.

Example:
intro: a quick \u201cwhy is my life so bad\u201d checklist
items:
- how\u2019s your sleep schedule
- have you eaten or drank anything besides sugar and caffeine
- have you taken a shower/brushed your teeth/groomed yourself properly
- etc

Return ONLY valid JSON with keys "intro" (string), "items" (array of
strings, the last one being "etc"), and "hashtags" (array of 6-8 short
lowercase Instagram hashtags WITHOUT the # symbol - mix 2-3 broad ones like
checklist/selfcare/mentalhealth with tags specific to THIS POST'S SUBJECT;
no spaces in any tag, all must relate to the post)."""


def gemini_draft(model, api_key, recent=None, topic=None, avoid=None,
                 hard_words=None):
    """Ask Gemini for a draft; returns (intro, items, hashtags).

    `recent` is a list of recent post dicts (hooks AND items are fed to the
    model so it avoids repeating them). `topic` pins the checklist subject.
    `avoid` is a list of items from a previous attempt that was rejected as
    too similar. `hard_words` is a list of hard words to avoid from a
    previous attempt that broke the easy-reading rule.
    """
    t = THEMES.get(topic)
    prompt = GEMINI_PROMPT
    if t:
        hooks = " / ".join(f"“{x}”" for x in t["intros"][:2])
        seeds = "\n".join(f"- {x}" for x in t["items"][:4])
        prompt += (
            f"\n\nTHIS POST'S SUBJECT: {t['label']}.\n"
            "All checklist items must relate directly to this subject.\n"
            f"Hook style examples for this subject: {hooks}\n"
            "(write a NEW hook, do not copy these)\n"
            f"Sample territory for this subject (write your own, do not "
            f"copy):\n{seeds}")
    if recent:
        past = "\n".join(
            f"{i + 1}. {h.get('intro', '?')}" for i, h in enumerate(recent))
        past_items = "\n".join(
            f"- {it}" for h in recent
            for it in (h.get("items") or [])[:4])
        prompt += (
            "\n\nRecent posts you already made - do NOT repeat these hooks, "
            "angles, or items:\n" + past +
            "\nRecent items to avoid (do not reuse or closely paraphrase):\n"
            + past_items +
            "\n\nWrite something clearly different: a fresh hook, a distinct "
            "angle, and mostly new items.")
    if avoid:
        prompt += (
            "\n\nYour previous attempt was rejected as too similar to recent "
            "posts. Do NOT reuse or paraphrase these items:\n- "
            + "\n- ".join(avoid)
            + "\n\nWrite items on a clearly different track.")
    if hard_words:
        prompt += (
            "\n\nSTRICT RULE VIOLATION: your previous draft used words that "
            "are hard to read. Rewrite and completely avoid these words: "
            + ", ".join(hard_words)
            + ".\nUse the shortest, simplest everyday words possible - the "
            "easiest version of every sentence.")
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 1.0,
            "responseMimeType": "application/json",
        },
    }
    url = GEMINI_URL.format(model=model) + "?key=" + api_key
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini API error {e.code}: "
                           f"{e.read().decode()[:300]}") from e
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        text = text.strip()
        if text.startswith("```"):            # strip any code fences
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(text)
        intro, items = parsed["intro"], list(parsed["items"])
        if items and items[-1] != "etc":
            items.append("etc")
        if not isinstance(intro, str) or not items:
            raise ValueError("unexpected shape")
        return intro, items, norm_tags(parsed.get("hashtags"))
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Could not parse Gemini response: {e}") from e


def norm_tags(tags):
    """Clean Gemini-returned hashtags: lowercase, strip '#', drop spaces,
    dedupe, cap at 8. Falls back to the default set if empty."""
    out = []
    for t in tags or []:
        t = str(t).strip().lstrip("#").lower().replace(" ", "")
        if t and t.isalnum() and t not in out:
            out.append(t)
    return out[:8] or list(DEFAULT_HASHTAGS)


def build_caption(intro, tags):
    """intro → CTA → hashtags, the exact caption Instagram receives."""
    tags = ["#" + t for t in tags]
    return intro + "\n\n" + CTA + "\n\n" + " ".join(tags)


def post_to_instagram(intro, video_url, tags):
    """Publish the reel via the official Instagram Graph API."""
    here = os.path.dirname(os.path.abspath(__file__))
    caption = build_caption(intro, tags)
    cmd = [sys.executable, os.path.join(here, "post_instagram.py"),
           "--video-url", video_url, "--caption", caption]
    # GitHub-hosted reels are deleted from the repo once published - the
    # raw URL is only needed while Instagram processes the video.
    if video_url.startswith("https://raw.githubusercontent.com/") \
            and os.environ.get("GH_TOKEN"):
        cmd += ["--cleanup-url", video_url]
    print("posting to instagram (official Graph API):",
          os.path.join(here, "post_instagram.py"), "\n")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or "").strip().splitlines()
        print(f"Error: Instagram post failed: "
              f"{err[-1] if err else 'unknown'}", file=sys.stderr)
        sys.exit(1)


def make_video(audio, audio_start):
    """Re-encode the reel MP4 with audio (make_video.py)."""
    here = os.path.dirname(os.path.abspath(__file__))
    # imageio-ffmpeg lives in .venv, so run it with that interpreter
    venv_py = os.path.join(here, ".venv", "bin", "python")
    py = venv_py if os.path.exists(venv_py) else sys.executable
    cmd = [py, os.path.join(here, "make_video.py"),
           "--audio", audio, "--audio-start", str(audio_start),
           "--zoom", "0", "--no-fade"]
    print("rendering video:", " ".join(cmd), "\n")
    subprocess.run(cmd, check=True)


def render(args, intro, items):
    here = os.path.dirname(os.path.abspath(__file__))
    cmd = [sys.executable, os.path.join(here, "make_post.py"),
           "--intro", intro]
    for it in items:
        cmd += ["--item", it]
    if args.username:
        cmd += ["--username", args.username]
    if args.output:
        cmd += ["--output", args.output]
    if args.reel:
        cmd += ["--reel", "--reel-scale", str(args.reel_scale)]
    print("rendering:", " ".join(cmd), "\n")
    subprocess.run(cmd, check=True)


def main():
    p = argparse.ArgumentParser(
        description="Write self-care checklist posts and render them")
    p.add_argument("--theme", choices=sorted(THEMES),
                   help="topic to write for (default: rotated by history)")
    p.add_argument("--list-themes", action="store_true",
                   help="list all topics and exit")
    p.add_argument("--count", type=int, default=1,
                   help="how many drafts to generate (default 1)")
    p.add_argument("--seed", type=int, default=None,
                   help="seed for reproducible drafts")
    p.add_argument("--agent", choices=["local", "gemini"], default="gemini",
                   help="who writes the drafts: local banks, or the Gemini "
                        "API (default gemini)")
    p.add_argument("--model", default="gemini-3.5-flash",
                   help="Gemini model to use (default gemini-3.5-flash)")
    p.add_argument("--max-items", type=int, default=7,
                   help="max checklist items per draft (default 7)")
    p.add_argument("--history", default=HISTORY_PATH,
                   help="post-history JSON file (default post_history.json)")
    p.add_argument("--show-history", action="store_true",
                   help="show the last posts and exit")
    p.add_argument("--clear-history", action="store_true",
                   help="clear the post history and exit")
    p.add_argument("--video", action="store_true",
                   help="one-command pipeline: write + render images + "
                        "re-encode post-reel.mp4 with audio")
    p.add_argument("--post", action="store_true",
                   help="like --video, then publish the reel to Instagram "
                        "via the official Graph API (needs --video-url and "
                        "IG_ACCESS_TOKEN in .env)")
    p.add_argument("--video-url", default=None,
                   help="(with --post) PUBLIC https URL where post-reel.mp4 "
                        "is hosted - the Graph API downloads it from there. "
                        "Omit to auto-host the reel on GitHub.")
    p.add_argument("--audio", default=None,
                   help="(with --video) audio file for the reel (default: "
                        "AUDIO_PATH env var or the local default)")
    p.add_argument("--no-audio", action="store_true",
                   help="(with --video) render the reel silently - for "
                        "hosts that don't have the local music file")
    p.add_argument("--audio-start", type=float, default=3.89,
                   help="(with --video) start offset in seconds into the "
                        "audio file (default 3.89 = last 8s of the track)")
    p.add_argument("--render", action="store_true",
                   help="render the last draft with make_post.py")
    p.add_argument("--reel", action="store_true",
                   help="(with --render) also build the 1080x1920 reel image")
    p.add_argument("--username", default=None,
                   help="(with --render) username override")
    p.add_argument("--output", default=None,
                   help="(with --render) output file for post.png")
    p.add_argument("--reel-scale", type=float, default=1.2,
                   help="(with --render) reel card scale (default 1.2)")
    args = p.parse_args()

    if args.post:                       # --post implies the whole pipeline
        args.video = True
        if not args.video_url:
            print("(no --video-url given - the reel will be hosted on "
                  "GitHub automatically)")
    if args.video:                      # --video implies the whole pipeline
        args.render = True
        args.reel = True

    if args.list_themes:
        print("Topics:\n")
        for name, t in THEMES.items():
            print(f"  {name:<12} {t['label']}")
        return

    history = load_history(args.history)
    if args.show_history:
        if not history:
            print("No posts in history yet.")
            return
        print(f"{len(history)} posts recorded ({args.history}):\n")
        for h in history[-12:]:
            ts = h.get("ts", "?")
            src = h.get("source", "?")
            th = h.get("theme") or ""
            print(f"  {ts}  [{src} · {th}]  {h.get('intro', '')}")
        return
    if args.clear_history:
        save_history(args.history, [])
        print(f"Cleared {args.history}")
        return

    rng = random.Random(args.seed)
    recent = history[-5:]                       # remember the last 5 posts

    # rotate the checklist subject: skip topics used in the last 5 posts
    recent_themes = {h.get("theme") for h in recent if h.get("theme")}
    if args.theme:
        themes = [args.theme]
        if args.theme in recent_themes:
            print(f"(note: topic '{args.theme}' was used in a recent post)",
                  file=sys.stderr)
    else:
        themes = [t for t in THEMES if t not in recent_themes] or list(THEMES)

    used_intros = {h.get("intro") for h in history}
    recent_items = [it for h in recent for it in (h.get("items") or [])]

    api_key = None
    if args.agent == "gemini":
        load_env_file()
        api_key = (os.environ.get("GOOGLE_API_KEY")
                   or os.environ.get("GEMINI_API_KEY"))
        if not api_key:
            print("No Gemini API key found (set GOOGLE_API_KEY or "
                  "GEMINI_API_KEY). Falling back to local drafts.\n",
                  file=sys.stderr)
            args.agent = "local"

    seen = list(history)
    last = None
    last_tags = None
    last_meta = {"source": None, "theme": None}
    used_this_run = []
    for i in range(1, args.count + 1):
        avail = [t for t in themes if t not in used_this_run] or themes
        theme = rng.choice(avail)
        used_this_run.append(theme)
        if args.agent == "gemini":
            source = f"gemini ({args.model})"
            intro = items = tags = None
            avoid = None
            hard_list = None
            for _ in range(3):         # retry if it repeats or is hard to read
                try:
                    intro, items, tags = gemini_draft(args.model, api_key,
                                                      recent, topic=theme,
                                                      avoid=avoid,
                                                      hard_words=hard_list)
                except RuntimeError as e:
                    print(f"Gemini failed: {e}", file=sys.stderr)
                    intro = items = None
                    break
                hard = find_hard_words(intro + " " + " ".join(items))
                if not hard and not is_duplicate(seen, intro, items):
                    break
                if hard:
                    print(f"(rejected: hard words {hard})", file=sys.stderr)
                    hard_list = hard
                else:
                    avoid = items
                intro = items = None
            if intro is None:
                print("Falling back to local draft.\n", file=sys.stderr)
                source = "local (fallback)"
                intro, items = generate(theme, rng, args.max_items,
                                        used_intros, recent_items)
                tags = DEFAULT_HASHTAGS
            last_meta = {"source": source, "theme": theme}
        else:
            source = theme
            intro, items = generate(theme, rng, args.max_items,
                                    used_intros, recent_items)
            tags = DEFAULT_HASHTAGS
            last_meta = {"source": source, "theme": theme}
        print_draft(i, source, intro, items, subject=theme, tags=tags)
        seen.append({"intro": intro, "items": items, "hashtags": tags})
        last = (intro, items)
        last_tags = tags

    if args.render and last:
        render(args, *last)
        history.append({
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "source": last_meta["source"],
            "theme": last_meta["theme"],
            "intro": last[0],
            "items": last[1],
            "hashtags": last_tags,
        })
        save_history(args.history, history)
        print(f"\nRecorded to {args.history} ({len(history)} posts total)")
        if args.video:
            audio = (args.audio or os.environ.get("AUDIO_PATH")
                     or DEFAULT_AUDIO)
            if args.no_audio:
                make_video("", args.audio_start)      # silent reel
                print("Done: post-reel.mp4 updated with the new post "
                      "(no audio).")
            elif not os.path.exists(audio):
                print(f"Note: audio file not found: {audio} — images "
                      f"rendered, video not updated. Pass --audio <file> "
                      f"or --no-audio.", file=sys.stderr)
            else:
                make_video(audio, args.audio_start)
                print("Done: post-reel.mp4 updated with the new post.")
            if args.post:
                url = args.video_url
                if not url:
                    # Self-contained: host the freshly made reel on GitHub.
                    print("hosting the reel on GitHub ...")
                    here = os.path.dirname(os.path.abspath(__file__))
                    up = subprocess.run(
                        [sys.executable, os.path.join(here, "upload_reel.py")],
                        capture_output=True, text=True)
                    if up.returncode != 0:
                        err = (up.stderr or up.stdout).strip().splitlines()
                        print(f"Error: auto-host failed: "
                              f"{err[-1] if err else '?'}", file=sys.stderr)
                        sys.exit(1)
                    url = up.stdout.strip().splitlines()[-1]
                    print(f"  hosted at {url}")
                post_to_instagram(last[0], url, last_tags)
                print("Done: reel posted to Instagram.")
        else:
            print("Next step (add your audio):")
            print("  .venv/bin/python make_video.py --audio song.mp3 "
                  "--audio-start 3.89 --zoom 0 --no-fade")


if __name__ == "__main__":
    main()
