#!/usr/bin/env python3
"""
Content agent — writes the text for self-care / relatable checklist posts
(the "why is my life so bad" genre) and hands it to make_post.py to render.

Usage:
    python3 src/content_agent.py --video                   # everything, one line
    python3 src/content_agent.py --post                    # ...and post it to IG
    python3 src/content_agent.py --youtube                 # ...and post it to YouTube
    python3 src/content_agent.py --post --youtube          # both, in one run
    python3 src/content_agent.py                           # one random draft
    python3 src/content_agent.py --theme sleep             # draft for a topic
    python3 src/content_agent.py --list-themes             # show available topics
    python3 src/content_agent.py --count 3                 # three drafts at once
    python3 src/content_agent.py --seed 7                  # reproducible draft
    python3 src/content_agent.py --agent local             # offline drafts
    python3 src/content_agent.py --render --reel           # also render images
    python3 src/content_agent.py --show-history            # see the last posts
    python3 src/content_agent.py --clear-history           # start over

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

from ig_common import ROOT, load_env_file, project_path

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
        "keywords": ["screen", "phone", "scroll", "thumb", "app",
                     "doom", "video", "feed", "media"],
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
        "keywords": ["bank", "money", "card", "bill", "pay", "buy",
                     "bought", "subscription", "spend", "balance",
                     "account", "coffee"],
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
        "keywords": ["room", "bed", "laundry", "sheet", "desk",
                     "trash", "floor", "clothes", "cup", "window",
                     "vacuum", "mess"],
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
        "keywords": ["friend", "text", "message", "hang", "call",
                     "voice", "plan", "lonely", "isolat", "repli",
                     "reach"],
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
        "keywords": ["work", "job", "email", "meeting", "monday",
                     "desk", "office", "task", "deadline", "lunch",
                     "vacation", "boss"],
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
        "keywords": ["body", "back", "neck", "shoulder", "posture",
                     "stretch", "walk", "jaw", "sit", "pain", "hurt",
                     "move"],
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
        "keywords": ["sleep", "bed", "tired", "nap", "caffeine",
                     "alarm", "midnight", "wake", "awake", "night",
                     "slept", "exhausted"],
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
        "keywords": ["shower", "brush", "teeth", "hair", "wash",
                     "clothes", "sock", "mirror", "smell", "face",
                     "gross", "laundry"],
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
        "keywords": ["sun", "outside", "grass", "walk", "door",
                     "window", "air", "vitamin", "tree", "house",
                     "indoor", "curtain"],
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
        "keywords": ["anxiet", "anxious", "breath", "chest", "heart",
                     "nervous", "panic", "worr", "calm", "racing",
                     "tight", "scared"],
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
        "keywords": ["brain", "thought", "think", "overthink", "replay",
                     "worr", "problem", "mind", "loop", "shut", "2am"],
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
        "keywords": ["compar", "jealous", "envy", "everyone",
                     "highlight", "someone", "grid", "feed", "behind",
                     "life", "post"],
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
        "keywords": ["eat", "food", "meal", "plate", "hungr",
                     "hangry", "lunch", "breakfast", "snack",
                     "vegetable", "water", "coffee"],
    },
    "marriage": {
        "label": "Marriage feels like roommates",
        "intros": [
            "a quick “why does my marriage feel like a roommate situation” checklist",
            "the “we said forever and now we just coexist” checklist",
            "a quick “why are we married but lonely” checklist",
        ],
        "items": [
            "when did you last go on an actual date with them",
            "do you talk about anything besides chores and logistics",
            "have you texted them something flirty today",
            "are you both on your phones on the same couch",
            "when did you last ask about their day and actually listen",
            "have you said thank you for the small stuff lately",
            "are you fighting about the same thing since 2019",
            "have you touched them without it leading somewhere",
            "do you still like them or just love them",
            "have you picked them over being right this week",
        ],
        "keywords": ["marriage", "married", "spouse", "husband", "wife",
                     "partner", "date", "fight", "argue", "love",
                     "couch", "forever"],
    },
    "social": {
        "label": "Social life is a desert",
        "intros": [
            "a quick “why is my social life a desert” checklist",
            "the “i have no plans and it’s saturday” checklist",
        ],
        "items": [
            "have you said yes to anything this month",
            "is your weekend calendar just your couch",
            "have you made the first move or always waited",
            "are you still texting back within 24 hours",
            "is your whole social life just work friends",
            "have you done something social without a screen",
            "when did you last laugh out loud with a person",
            "are you waiting for someone else to plan it",
            "have you invited anyone to anything ever",
            "is your ‘i’m busy’ actually ‘i’m scared’",
        ],
        "keywords": ["social", "plan", "weekend", "invite", "hang",
                     "party", "lonely", "couch", "saturday", "friend",
                     "yes"],
    },
    "dating": {
        "label": "Can’t talk to the opposite gender",
        "intros": [
            "a quick “why can’t i talk to the opposite gender” checklist",
            "the “i turn into a different person around them” checklist",
        ],
        "items": [
            "have you had a normal conversation without performing",
            "are you being yourself or a character you made up",
            "do you flirt or just panic and go silent",
            "have you asked about them instead of talking about you",
            "do you treat them like an alien species or a person",
            "have you texted first or are you waiting forever",
            "is every interaction a job interview in your head",
            "have you remembered they’re also nervous",
            "are you scared of rejection or of being seen",
            "have you smiled like a human instead of a mannequin",
        ],
        "keywords": ["date", "dating", "flirt", "text", "crush",
                     "reject", "nervous", "gender", "talk", "confident",
                     "silent", "character"],
    },
    "philosophy": {
        "label": "Existential crisis at 3am",
        "intros": [
            "a quick “why am i having an existential crisis at 3am” checklist",
            "the “what is the point of any of this” checklist",
        ],
        "items": [
            "have you eaten today (deep thoughts are hungry thoughts)",
            "is this a real question or a 3am question",
            "are you tired (all philosophy hits harder when tired)",
            "have you touched grass and looked at the sky",
            "is your crisis about the universe or your to-do list",
            "are you avoiding life by thinking about existence",
            "have you talked to a person instead of a concept",
            "is your meaning of life just a nap away",
            "have you done one small real thing today",
            "are you trying to solve everything at once again",
        ],
        "keywords": ["philosoph", "exist", "meaning", "point", "universe",
                     "life", "3am", "deep", "crisis", "purpose", "nap",
                     "real"],
    },
    "psychology": {
        "label": "Self-diagnosing at 2am",
        "intros": [
            "a quick “why am i psychoanalyzing myself at 2am” checklist",
            "the “i diagnosed myself with everything” checklist",
        ],
        "items": [
            "have you read one article and now you’re a doctor",
            "have you labeled a normal feeling as a disorder",
            "is your personality a list of online diagnoses",
            "have you actually asked a real professional",
            "are you using therapy words as weapons on yourself",
            "is your brain just tired, not broken",
            "have you slept or are you analyzing on empty",
            "are you overthinking a text (it was fine)",
            "have you done one thing without analyzing it first",
            "is this insight or just spiraling with extra steps",
        ],
        "keywords": ["psycholog", "diagnos", "doctor", "disorder",
                     "therap", "analyz", "label", "professional",
                     "symptom", "article", "insight", "spiral"],
    },
    "gym": {
        "label": "Gym motivation is dead",
        "intros": [
            "a quick “why can’t i get to the gym” checklist",
            "the “i bought the membership and never went back” checklist",
        ],
        "items": [
            "have you actually gone or just watched gym content",
            "is your gym bag packed or just a dream",
            "are you ‘too tired’ for the 50th day in a row",
            "are you comparing your day one to their year five",
            "have you eaten actual protein or just protein bars",
            "is your routine ‘looking at the gym from my car’",
            "did you sleep (muscles grow in bed, not the gym)",
            "have you gone twice in the same week this month",
            "is your goal real or a new year’s ghost",
            "would you go if it was just for you, not the mirror",
        ],
        "keywords": ["gym", "workout", "exercis", "muscle", "protein",
                     "membership", "lift", "train", "routine", "fit",
                     "motivat"],
    },
    "procrastination": {
        "label": "Can’t start anything",
        "intros": [
            "a quick “why can’t i start anything” checklist",
            "the “i’ll do it later (i won’t)” checklist",
        ],
        "items": [
            "is the task actually big or just loud in your head",
            "have you broken it into a stupidly small first step",
            "are you waiting for motivation that never comes",
            "have you started for just five minutes (that’s the trick)",
            "is your phone in the same room right now",
            "are you scrolling to feel productive instead of doing",
            "have you done the hardest thing first or saved it forever",
            "is ‘i work better under pressure’ just your excuse",
            "would future you forgive you or be mad",
            "have you just done one tiny thing yet",
        ],
        "keywords": ["procrastinat", "start", "task", "later", "scroll",
                     "motivat", "minute", "deadline", "avoid", "done",
                     "pressure", "phone"],
    },
    "confidence": {
        "label": "Confidence in the gutter",
        "intros": [
            "a quick “why is my confidence in the gutter” checklist",
            "the “i feel like i’m failing at being me” checklist",
        ],
        "items": [
            "are you comparing your insides to everyone’s outsides",
            "have you done one thing you said you’d do today",
            "is your self talk something you’d say to a friend",
            "are you waiting to feel ready before you start",
            "have you remembered the things you’re actually good at",
            "are you confusing confidence with being perfect",
            "have you stood up straight and faked it a little",
            "is your bar set by strangers on the internet",
            "have you kept a promise to yourself this week",
            "did you show up even when you didn’t feel like it",
        ],
        "keywords": ["confiden", "self", "worth", "ready", "perfect",
                     "believ", "proud", "promise", "compar", "show",
                     "fail"],
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


HISTORY_PATH = project_path("post_history.json")

# Default music for the reel video (used when --video is given without
# --audio). Lives in the repo's audio/ dir, committed alongside the code,
# so the pipeline works from anywhere (override with AUDIO_PATH in .env).
DEFAULT_AUDIO = os.path.join(ROOT, "audio", "reel.mp3")

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
    """Read the post-history JSON (a list of post dicts); [] on any error."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_history(path, history):
    """Persist the post-history JSON (kept human-readable for diffing)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def _norm(s):
    """Lowercase + strip all non-alphanumerics; used for exact-match checks."""
    return "".join(ch for ch in s.lower() if ch.isalnum())


# Filler words dropped before comparing items, so two drafts that say the
# same thing in different wrapper words still get caught.
STOPWORDS = {
    "a", "about", "actually", "again", "all", "an", "and", "any", "are",
    "at", "be", "been", "being", "but", "by", "can", "could", "did",
    "do", "does", "done", "down", "even", "ever", "feel", "feeling",
    "feels", "for", "from", "get", "go", "going", "got", "have", "how",
    "in", "into", "is", "it", "its", "just", "like", "make", "me",
    "my", "of", "on", "one", "or", "out", "really", "right", "should",
    "so", "some", "that", "the", "their", "them", "there", "they",
    "this", "to", "today", "two", "up", "was", "we", "were", "what",
    "when", "why", "will", "with", "would", "you", "your",
}


def _stem(w):
    """Crude stemmer - good enough for overlap detection."""
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[:-len(suf)]
    return w


def content_tokens(text):
    """Content words of a line: lowercased, lightly stemmed, no filler."""
    out = []
    for raw in re.findall(r"[a-zA-Z’']+", text.lower()):
        w = raw.strip("’'")
        if w in STOPWORDS or len(w) < 3:
            continue
        w = _stem(w)
        if w:
            out.append(w)
    return out


def _ngrams(tokens, n):
    """Set of length-`n` character-gram tuples of a token list."""
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def item_similarity(a, b):
    """Jaccard similarity of two items' content-word sets."""
    ta, tb = set(content_tokens(a)), set(content_tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


# Jokes recycled across past posts. A draft that reaches for any of these
# (even freshly worded) gets rejected - they've been done to death.
REPEATED_BITS = [
    r"raccoon",                       # the pantry-raccoon grazing joke
    r"pantry",
    r"required a plate",
    r"cheap lawn chair",
    r"horrify a chiropractor",
    r"folded (up )?like a",
]


def _item_is_stale(cand, hist):
    """True if `cand` repeats `hist` in substance (not just verbatim)."""
    if _norm(cand) == _norm(hist):
        return True
    if item_similarity(cand, hist) > 0.55:
        return True
    ta, tb = content_tokens(cand), content_tokens(hist)
    if len(_ngrams(ta, 4) & _ngrams(tb, 4)) >= 1:
        return True
    if len(_ngrams(ta, 3) & _ngrams(tb, 3)) >= 3:
        return True
    return False


def find_duplicate_items(items, seen):
    """History items too close to `items` (the closer is ignored).

    Returns the offending lines so they can be fed back to the writer as
    "avoid these" - much better feedback than a bare reject.
    """
    hits = []
    for cand in items[:-1]:
        for raw in REPEATED_BITS:
            if re.search(raw, cand, re.IGNORECASE):
                hits.append(cand)
        for h in seen:
            for hist in (h.get("items") or [])[:-1]:
                if _item_is_stale(cand, hist):
                    hits.append(hist)
    return list(dict.fromkeys(hits))          # dedupe, keep order


def is_duplicate(seen, intro, items):
    """True if the same hook appears, or any item repeats a past one."""
    for h in seen:
        if h.get("intro") == intro:
            return True
    return bool(find_duplicate_items(items, seen))


def off_theme_items(items, keywords):
    """Items that mention none of the theme's keywords at all - the closer
    is ignored. Used to reject drafts that drifted off-subject."""
    return [it for it in items[:-1]
            if not any(k in it.lower() for k in keywords)]


def _error_code(exc):
    """HTTP status from a gemini_draft RuntimeError, or None."""
    m = re.search(r"API error (\d+)", str(exc))
    return int(m.group(1)) if m else None


# API errors worth retrying with a different key: invalid key (400 when
# the request itself is fine - which it always is here), auth failures,
# quota exhaustion, and server hiccups. Anything else is the prompt's
# fault and retrying with another key won't help.
KEY_SWITCHABLE = {400, 401, 403, 429, 500, 502, 503, 504}


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
    """Pretty-print one draft to the terminal (hook, bullets, tags)."""
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
- STRICT RULE - STAY ON SUBJECT: every item MUST be specifically about THIS
  POST'S SUBJECT. Items about water, sleep, posture, screens, eating, or
  texting friends that could appear in ANY self-care checklist are banned
  unless they directly serve the subject. When in doubt, rewrite the item to
  be specific to the subject.
- Never reuse the same sentence patterns across posts.
- Never repeat jokes you (or past posts) have used: no grazing like a
  raccoon, no cheap lawn chair, no "meal that required a plate", no folded
  like a shrimp. Fresh jokes only.

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
                 hard_words=None, off_topic=None):
    """Ask Gemini for a draft; returns (intro, items, hashtags).

    `recent` is a list of recent post dicts (hooks AND items are fed to the
    model so it avoids repeating them). `topic` pins the checklist subject.
    `avoid` is a list of items from a previous attempt that was rejected as
    too similar. `hard_words` is a list of hard words to avoid from a
    previous attempt that broke the easy-reading rule. `off_topic` is a list
    of items from a previous attempt that drifted off the subject.
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
    if off_topic:
        prompt += (
            "\n\nSTRICT RULE VIOLATION: your previous draft went off-subject. "
            "These items have nothing to do with THIS POST'S SUBJECT and were "
            "rejected:\n- " + "\n- ".join(off_topic)
            + "\n\nRewrite EVERY item so it is specifically about THIS "
            "POST'S SUBJECT. No generic self-care items that could appear in "
            "any checklist.")
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


def post_to_youtube(intro, items, tags, title=None, description=None,
                    privacy="public"):
    """Publish the reel to YouTube via the Data API v3. Unlike Instagram,
    YouTube accepts a direct file upload, so no hosted URL is needed."""
    here = os.path.dirname(os.path.abspath(__file__))
    cmd = [sys.executable, os.path.join(here, "post_youtube.py"),
           "--file", project_path("post-reel.mp4"),
           "--title", title or intro,
           "--description", description or build_caption(intro, tags),
           "--privacy", privacy]
    print("posting to youtube (Data API v3):",
          os.path.join(here, "post_youtube.py"), "\n")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or "").strip().splitlines()
        print(f"Error: YouTube post failed: "
              f"{err[-1] if err else 'unknown'}", file=sys.stderr)
        sys.exit(1)


def make_video(audio, audio_start):
    """Re-encode the reel MP4 with audio (make_video.py)."""
    here = os.path.dirname(os.path.abspath(__file__))
    # imageio-ffmpeg lives in .venv, so run it with that interpreter
    venv_py = os.path.join(ROOT, ".venv", "bin", "python")
    py = venv_py if os.path.exists(venv_py) else sys.executable
    cmd = [py, os.path.join(here, "make_video.py"),
           "--audio", audio, "--audio-start", str(audio_start),
           "--zoom", "0", "--no-fade"]
    print("rendering video:", " ".join(cmd), "\n")
    subprocess.run(cmd, check=True)


def render(args, intro, items):
    """Render a draft to post.png (and post-reel.png with --reel)."""
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
    p.add_argument("--youtube", action="store_true",
                   help="like --video, then publish the reel to YouTube via "
                        "the Data API v3 (needs YT_CLIENT_ID, "
                        "YT_CLIENT_SECRET, YT_REFRESH_TOKEN in .env - see "
                        "docs/YT_SETUP.md)")
    p.add_argument("--yt-title", default=None,
                   help="(with --youtube) video title (default: the hook "
                        "line)")
    p.add_argument("--yt-description", default=None,
                   help="(with --youtube) video description (default: the "
                        "caption text)")
    p.add_argument("--yt-privacy", choices=["public", "unlisted", "private"],
                   default="public",
                   help="(with --youtube) upload privacy (default public)")
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

    if args.post or args.youtube:       # --post / --youtube imply the pipeline
        args.video = True
    if args.post and not args.video_url:
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

    api_keys = None
    if args.agent == "gemini":
        load_env_file()
        # Primary key first, then any backups - if the primary is out of
        # quota or revoked, the run tries the next key before giving up.
        api_keys = list(dict.fromkeys(k for k in (
            os.environ.get("GOOGLE_API_KEY"),
            os.environ.get("GOOGLE_API_KEY_BACKUP"),
            os.environ.get("GEMINI_API_KEY"),
            os.environ.get("GEMINI_API_KEY_BACKUP"),
        ) if k))
        if not api_keys:
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
            off_list = None
            ki = 0
            for _ in range(3):  # retry if it repeats, drifts, or is hard
                try:
                    intro, items, tags = gemini_draft(args.model, api_keys[ki],
                                                      recent, topic=theme,
                                                      avoid=avoid,
                                                      hard_words=hard_list,
                                                      off_topic=off_list)
                except RuntimeError as e:
                    code = _error_code(e)
                    if code in KEY_SWITCHABLE and ki + 1 < len(api_keys):
                        print(f"Gemini key {ki + 1} failed (HTTP {code}); "
                              f"trying the next key", file=sys.stderr)
                        ki += 1
                        continue
                    # Not a key problem (e.g. malformed JSON from the model)
                    # - retry the same prompt; the budget above limits it.
                    print(f"Gemini attempt failed: {e}", file=sys.stderr)
                    continue
                hard = find_hard_words(intro + " " + " ".join(items))
                dups = find_duplicate_items(items, seen)
                off = off_theme_items(items, THEMES[theme]["keywords"])
                if not hard and not dups \
                        and len(off) <= len(items[:-1]) // 3:
                    break
                if hard:
                    print(f"(rejected: hard words {hard})", file=sys.stderr)
                    hard_list = hard
                elif dups:
                    print("(rejected: repeats past posts)", file=sys.stderr)
                    avoid = dups
                else:
                    print(f"(rejected: off-subject {off})", file=sys.stderr)
                    off_list = off
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
            if args.youtube:
                post_to_youtube(last[0], last[1], last_tags,
                                args.yt_title, args.yt_description,
                                args.yt_privacy)
                print("Done: reel posted to YouTube.")
        else:
            print("Next step (add your audio):")
            print("  .venv/bin/python src/make_video.py --audio song.mp3 "
                  "--audio-start 3.89 --zoom 0 --no-fade")


if __name__ == "__main__":
    main()
