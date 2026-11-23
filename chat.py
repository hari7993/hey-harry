"""Her window's first page, a chat (22 November 2026, the owner, after hedwig-ai.com: its dashboard "works like a chat
interface, make ours like that, access to all, do everything from there"; then "see the typography, the animations",
"see how sizing and view clean and the spaces", "ours is so big"). What's taken from it:

One box for everything, rounded, what you type along its top and a row under it with her face and name at the left
and a round Send at the right. While the chat is empty it sits in the middle of the page under "What can I help
with?", things to start from under it; once there's a chat it goes to the foot. What's typed there goes to her as a
turn of yours, as Home's box did. Typed with a slash first, "/voice", it finds anything in her window instead, a tab,
a part of a page or one row of Settings, and Enter goes there (assistant_ui.quick_actions).

A thread over it of what was said and what she did about it, typed or spoken, fed by the events her window already
gets (assistant_ui._set_status), so nothing new is asked of her. Your words in a grey bubble on the right; her answer
by her face, typed out a few words at a time as it comes; while she works, a line by her face saying what she's at,
its words shimmering; once she's answered, how long she thought, as Hedwig's "Ideated for 9s"; and each step of hers
as a small chip, ticked, or red with a cross. New lines fade in. Your chats are kept, as ChatGPT's and Claude's are,
and listed down the sidebar under Chat with how long ago: its pencil (or Ctrl+Shift+O) starts a new one, a click
opens one again, and its bin deletes it (Chats, assistant_ui._lay_recent).

And what stays, as cards beside the chat, the way Hedwig keeps a prep doc and its Outbox there rather than letting an
answer scroll away: a task she's holding for your yes, with Approve and Cancel; your to-do list; the tasks she's on;
your timers. A click on a card's name opens its tab.

Thread, find and the small helpers hold no Tk and are what the tests check; Page and Box draw them with her window's
own parts and fonts (assistant_ui: f_chat, f_body, f_small, f_bold).
"""
import base64
import json
import math
import os
import re
import sys
import time
import tkinter as tk
import uuid
from tkinter import ttk

import identity

MOST = 200  # turns' lines kept in the thread
SHOWN = 5  # things found for what's typed after a slash
HINT = "Message Harry"
ASK = "What can I help with?"
# Hedwig's own, from its styles: the box (#eaeae8), your words' bubble (its ink at 10% on white), a chip (at 6.7%,
# its words at 72%), and its grey "What can I help with?" while there's nothing yet
FIELD, BUBBLE, CHIP, CHIP_INK, HERO = "#eaeae8", "#e8e8e9", "#eeeeef", "#5c5d5f", "#9a9da3"
# and since the owner's palette the same evening ("user bubble soft gray #EFEFEF", "source pills bg #F3F4F6 text
# #6B7280", "the greeting #111827"): what's drawn now
BUBBLE, CHIP, CHIP_INK, HERO, FACE, DIVIDER = "#ebebeb", "#f3f4f6", "#6b7280", "#111827", "#d1d5db", "#ededed"
CARD, CARD_LINE = "#f4f4f5", "#f4f4f5"  # an action card in the thread: Hedwig's soft grey, no line round it
SOURCE, SOURCE_INK = "#eef2f7", "#5b6b82"  # a source's pill: a pale cool grey, its name in a darker one
# and each source in its own pale tint, its name a deeper shade of the same (the owner: "minimal light colors"): the
# app's own colour, washed out, so the eye tells Calendar from Mail at a glance without anything shouting
TINTS = {"Calendar": ("#e8f0fe", "#3b6fd6"), "Mail": ("#fce8e6", "#c0392b"), "Gmail": ("#fce8e6", "#c0392b"),
         "Notion": ("#f1f0ec", "#6b6a66"), "Web": ("#e6f4ea", "#2e7d4f"), "Files": ("#fef3db", "#a8641a"),
         "Weather": ("#e3f4fb", "#2b7ea1"), "News": ("#f1ebfd", "#6f4cc3"), "Screen": ("#eef0f3", "#55606e"),
         "Memory": ("#fdebf1", "#b4436c"), "Timers": ("#e5f6f4", "#2a8073"), "To-do": ("#e8f6ec", "#33804f"),
         "YouTube": ("#fde9e7", "#c33a2f"), "WhatsApp": ("#e5f7ec", "#228a4e"), "Telegram": ("#e6f2fb", "#2f7bbf")}
STEP_DONE, STEP_DONE_INK = "#ebf7ef", "#3f7d58"  # a step that went through: its chip faintly green
FAILED_BG = "#fdeceb"  # a step that failed: its chip faintly red
WORDS_A_TICK, TICK_MS = 2, 32  # her answer typed out: this many words each tick (about 60 a second)
FADE_MS = 240  # a new line, from white to its colour
# Both were on till 22 November 2026, when the owner asked why lines "appear one by one, very late, ... remove that
# completely": her whole answer is there the moment it arrives, so typing it out only made it later, and a line
# fading in from white held it back a quarter of a second. Off: it's drawn as it is, at once. typed_out and the
# fade stay as what they are, for a look that wants them back.
TYPED_OUT = FADE_IN = False
# while she's at it: her window's word for it, and the thread's
WORKING = {"Listening": "Listening\u2026", "Still listening": "Still listening\u2026",
           "Transcribing": "Writing down what you said\u2026", "Thinking": "Thinking\u2026",
           "Looking": "Looking at the screen\u2026", "Doing it": "On it\u2026", "Dictating": "Taking it down\u2026"}
MARKS = {"live": "\u2022", "done": "\u2713", "failed": "\u2715"}
GLYPHS = {"live": "dot", "done": "\ue73e", "failed": "\ue711"}  # how each is drawn on its chip: the icon font's tick
# and cross, the same glyphs as every other cross and tick in her window, and the live one a dot (_pill)
KINDS = ("you", "her", "step", "note")
# your chats, as ChatGPT and Claude keep them (22 November 2026, the owner: "open new chat, deleting old chat, same
# style"): this many kept, the newest; and one whose last line is older than FRESH isn't the one she opens on, a new
# one is, as the thread was only the last six hours' turns till then
CHATS_KEPT, FRESH = 50, 6 * 3600
_WORDS = re.compile(r"[^\w\s]")


def plain(text):
    """text as it's compared: its words, lower case, no marks."""
    return " ".join(_WORDS.sub(" ", str(text or "").lower()).split())


def same_turn(a, b):
    """True if a and b are one turn's words told twice: "Harry, open Notepad" as heard, "open Notepad" as she thinks
    about it."""
    a, b = plain(a), plain(b)
    return bool(a and b) and (a == b or a.endswith(b) or b.endswith(a))


def ago(secs):
    """How long ago in a few letters, for the sidebar: now, 5m, 2h, 3d."""
    secs = max(0, int(secs))
    return "now" if secs < 60 else f"{secs // 60}m" if secs < 3600 else f"{secs // 3600}h" if secs < 86400 else \
        f"{secs // 86400}d"


# Her answer made easy to scan, as the AI chats lay theirs out (22 November 2026, the owner, naming them: "bold anchor
# phrases", "inline source chips", "single-idea lines", "an embedded action card"). Only how it's shown: her words are
# hers, said out loud as they are, and nothing is asked of the model for it.
_ANCHOR = re.compile(
    r"\b\d{1,2}(?::\d{2})?\s?(?:am|pm|a\.m\.|p\.m\.)(?!\w)|\b\d{1,2}:\d{2}\b"  # 2pm, 10:30 am, 14:00
    r"|[\u20b9$\u00a3\u20ac]\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|m|bn|lakh|crore)\b)?"  # money
    r"|\b\d[\d,]*(?:\.\d+)?\s?(?:%|percent\b|minutes?\b|mins?\b|hours?\b|hrs?\b|days?\b|weeks?\b|months?\b"
    r"|seats?\b|km\b|kg\b|\u00b0[cf]?)"  # amounts with what they count
    r"|\b(?:today|tonight|tomorrow|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
    r"|\b(?:jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.? \d{1,2}(?:st|nd|rd|th)?\b"
    r"|\b\d{1,2}(?:st|nd|rd|th)? (?:of )?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b", re.I)
_NAME = re.compile(r"\b[A-Z][\w\u2019'-]*(?:\s+[A-Z][\w\u2019'-]*)*")
NOT_NAMES = {"I", "I'm", "I\u2019m", "I'll", "I\u2019ll", "I've", "I\u2019ve", "I'd", "I\u2019d", "OK", "Okay", "Hey", "Hi",
             "Yes", "No", "Sure", "Done", "Sorry", "Thanks", "Also", "And", "But", "So", "The", "A", "An", "It", "That",
             "This", "You", "Your", "PC", "AM", "PM"}
SOURCES = (  # a step's words, the source it shows by her answer, and its mark in the icon font
    (r"calendar|agenda|schedule|meeting", "Calendar", "\ue787"),
    (r"gmail|\bmail|inbox|e-?mail", "Mail", "\ue715"),
    (r"notion", "Notion", "\ue8a5"),
    (r"whatsapp", "WhatsApp", "\ue8bd"),
    (r"telegram", "Telegram", "\ue8bd"),
    (r"youtube", "YouTube", "\ue714"),
    (r"searching (?:the web|google)|reading the page|looking it up", "Web", "\ue774"),
    (r"weather", "Weather", "\ue706"),
    (r"\bnews\b", "News", "\ue8a5"),
    (r"your files|the file", "Files", "\ue8b7"),
    (r"the screen", "Screen", "\ue7f4"),
    (r"to-do", "To-do", "\ue9d5"),
    (r"your chats|remembering", "Memory", "\ue81c"),
    (r"timer", "Timers", "\ue916"),
)
LINK = re.compile(r"https?://\S+|\b(?:meet\.google\.com|zoom\.us|[\w-]+\.zoom\.us|teams\.microsoft\.com|teams\.live\.com)"
                  r"/\S+", re.I)


def anchors(text):
    """Where in her words the facts are that the eye should land on, (start, end) in order: times, days and dates,
    amounts, and names (a run of capitalised words not starting a sentence)."""
    spans = [m.span() for m in _ANCHOR.finditer(text)]
    for m in _NAME.finditer(text):
        before = text[:m.start()].rstrip(" \"'\u201c\u2018(")
        words = m.group().split()
        while words and words[0] in NOT_NAMES:
            words.pop(0)
        if not words or not before or before[-1] in ".!?:\n" or (len(words) == 1 and words[0] in NOT_NAMES):
            continue
        start = m.start() + m.group().index(words[0])
        spans.append((start, m.end()))
    spans.sort()
    out = []
    for a, z in spans:  # overlapping ones made one
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], z))
        else:
            out.append((a, z))
    return out


def lines_of(text):
    """Her answer as single-idea lines: a sentence each once it's more than a line or two, else as it is."""
    text = " ".join(str(text).split())
    if len(text) < 110:
        return [text]
    parts = re.split(r"(?<=[.!?])\s+(?=[\"\u201c'(]?[A-Z0-9])", text)
    out = []
    for part in parts:  # a short one ("Done.") stays with the next, as a line of its own reads as a stutter
        if out and len(out[-1]) < 24:
            out[-1] += " " + part
        else:
            out.append(part)
    return out


LOOKED = re.compile(r"(?:checking|searching|reading|getting|looking|finding|remembering)\b", re.I)  # a look-up's words


def sources(steps):
    """The sources a turn's steps drew on, (name, mark), each once, in order: the chips by her answer. Only steps that
    went through: a failed one gave her nothing."""
    out = []
    for step in steps:
        if step.get("state") == "failed":
            continue
        # only what she looked up is a source: "Checking calendar", "Searching the web", "Reading the page". Opening
        # Gmail is something she did, not where her answer came from (it showed a Mail pill under "Opened it")
        if not LOOKED.match(step.get("text", "")):
            continue
        for words, name, mark in SOURCES:
            if re.search(words, step.get("text", ""), re.I) and (name, mark) not in out:
                out.append((name, mark))
                break
    return out


def turns(items):
    """The thread in turns: each {"steps": its steps' indexes, "first": its first line of hers' index or None,
    "last": its last}, a turn starting at your words; and a map from each item's index to its turn."""
    out, at = [{"steps": [], "first": None, "last": None}], {}
    for i, item in enumerate(items):
        if item["kind"] == "you" and (out[-1]["steps"] or out[-1]["first"] is not None or i):
            out.append({"steps": [], "first": None, "last": None})
        turn = out[-1]
        if item["kind"] == "step":
            turn["steps"].append(i)
        elif item["kind"] == "her":
            turn["first"] = i if turn["first"] is None else turn["first"]
            turn["last"] = i
        at[i] = turn
    return out, at


def sweep(n, t, period=1.6, width=5.0):
    """The shimmer's sweep over n letters at time t: how lit each is, 0 to 1, a soft band crossing them left to right
    about once every period seconds."""
    centre = -width + (t % period) / period * (n + 2 * width)
    return [max(0.0, 1.0 - abs(i - centre) / width) for i in range(n)]


def meeting_for(answer, events, now):
    """The meeting her answer is about, for its card: of events (agenda's, soonest first), the first not over whose
    title shares a word with what she said, else the next one to start; None if there's none today."""
    upcoming = [e for e in events if not e.get("all_day") and e.get("start") and (e.get("end") or e["start"]) > now]
    said = set(re.findall(r"[a-z]{4,}", answer.lower()))
    for e in upcoming:
        if said & set(re.findall(r"[a-z]{4,}", e.get("title", "").lower())):
            return e
    return upcoming[0] if upcoming else None


def typed_out(text, words):
    """text as far as its first words words, for her answer typed out a few at a time."""
    parts = str(text).split(" ")
    return " ".join(parts[:max(0, words)])


def shimmer(t):
    """How far a working line's words are from their grey towards white at time t: 0 to 0.6, about once a second."""
    return 0.3 + 0.3 * math.sin(t * 2 * math.pi * 0.9)


class Thread:
    """What's been said, in order, as her window's events tell it. items: {"kind": "you", "her", "step" or "note",
    "text", "state", "at"}, a step's state being live, done or failed and at when it was said; her first line of a
    turn also has "took", the seconds she thought before it. status: what she's doing now, "" when nothing. changed
    counts up each time what's shown is different."""

    def __init__(self):
        self.items, self.status, self.open, self.changed, self.thinking = [], "", False, 0, None
        self.starting = ""  # what she's still doing before she can answer anything, "" once she's ready

    def _add(self, kind, text, state="", at=None, files=None):
        text = " ".join(str(text or "").split())
        if not text and not files:
            return False
        self.items.append({"kind": kind, "text": text, "state": state, "at": time.time() if at is None else at})
        if files:
            self.items[-1]["files"] = list(files)
        del self.items[:-MOST]
        self.changed += 1
        return True

    def _answered(self):
        """True if she's said something since your last words."""
        for item in reversed(self.items):
            if item["kind"] == "you":
                return False
            if item["kind"] == "her":
                return True
        return False

    def you(self, text, files=None):
        """Your words, once a turn: typed here and then told back by her as asked, or heard and then thought about,
        they're the same ones. files: what you attached with them (attach.py), shown over them."""
        last = next((i for i in reversed(self.items) if i["kind"] == "you"), None)
        if self.open and last is not None and not self._answered() and same_turn(last["text"], text):
            return False
        added = self._add("you", text, files=files)
        self.open = self.open or added
        return added

    def her(self, text):
        # her answer told again as it grows, a sentence at a time and then whole (22 November 2026: shown twice):
        # the same line, made longer, or one already in it
        last = next((i for i in reversed(self.items) if i["kind"] in ("her", "you")), None)
        if last is not None and last["kind"] == "her":
            was, now = plain(last["text"]), plain(text)
            if now and now in was:
                return False
            if was and now.startswith(was):
                last["text"] = " ".join(str(text).split())
                self.changed += 1
                return True
        first = not self._answered()
        added = self._add("her", text)
        if added and first and self.thinking is not None:
            self.items[-1]["took"] = max(0, int(time.time() - self.thinking + 0.5))
        self.thinking = None
        return added

    def step(self, state, text):
        """A step of hers: live as it starts, then the same row done or failed."""
        if state not in MARKS:
            return False
        for item in reversed(self.items):
            if item["kind"] == "you":
                break
            if item["kind"] == "step" and item["text"] == " ".join(str(text).split()) and item["state"] == "live":
                if state == "live":
                    return False
                item["state"] = state
                self.changed += 1
                return True
        return self._add("step", text, state)

    def event(self, state, detail=""):
        """One of her window's events taken in. True if what's shown changed."""
        before, was = self.changed, self.status
        text = "" if detail is None else str(detail)
        self.starting = (text.strip() or "starting up") if state == "Starting" else ""  # anything after it: she's up
        if state in ("Asked", "Heard"):
            self.you(text)
        elif state == "Thinking":
            self.you(text)
            self.status = WORKING[state]
            self.thinking = self.thinking or time.time()
        elif state == "Speaking":
            self.her(text)
            self.status = ""
        elif state == "Step":
            kind, _, label = text.partition("\t")
            self.step(kind, label)
        elif state == "Learned":
            self._add("note", text.partition("\t")[2] or text)
        elif state in WORKING:
            self.status = WORKING[state]
        elif state == "Ready":
            if self.open and text and not self._answered():
                self._add("note", text)  # why she let it go: "That didn't sound like it was for me"
            self.status, self.open, self.thinking = "", False, None
        elif state == "Something went wrong":
            self._add("note", text, "failed")
            self.status, self.open, self.thinking = "", False, None
        if self.status != was:
            self.changed += 1
        return self.changed != before

    def waiting(self, why):
        """If she can't answer yet (why: what she's still doing, from starting_why), one line in the thread saying so and
        that she will (22 November 2026, the owner: the lines "come one by one, very late": what's typed while her
        speech models load, the header saying Starting, waits for her to be ready and is answered then, one after
        another, with nothing to say so). Once for a run of messages. True if it added one."""
        if not why:
            return False
        if "key" in why.lower():
            text = "She needs her keys first: add them in the Keys tab, and she'll answer."
        else:
            what = why.rstrip(".\u2026 ")
            more = "" if what.lower() in ("", "starting up", "starting") else f" ({what[:1].lower() + what[1:]})"
            text = f"She's still starting up{more}, so this waits. She'll answer as soon as she's ready."
        for item in reversed(self.items):
            if item["kind"] == "her":
                break
            if item["kind"] == "note" and item["text"] == text:
                return False
        return self._add("note", text)

    def earlier(self, turns):
        """The turns from before the window opened, (ts, said, plan) as history keeps them, put in first."""
        for ts, said, plan in turns:
            try:
                answer = json.loads(plan or "{}")
            except (TypeError, ValueError):
                answer = {}
            answer = answer if isinstance(answer, dict) else {}
            # one she started herself is kept as "(heads-up)", "(welcome)": her words alone, not a bubble of yours
            mine = not re.fullmatch(r"\(.*\)", str(said or "").strip())
            if (self._add("you", said, at=ts) if mine else True):
                self._add("her", answer.get("say") or "", at=ts)
        self.open = False

    def reset(self, items=()):
        """Another chat in it (Chats): items its lines as kept, or none for a new one. What she's doing now stays,
        as she may be mid-answer."""
        kept = []
        for item in items:
            if isinstance(item, dict) and item.get("kind") in KINDS and (str(item.get("text") or "").strip()
                                                                          or item.get("files")):
                kept.append({**item, "text": " ".join(str(item["text"]).split()), "state": item.get("state") or "",
                             "at": float(item.get("at") or 0)})
        self.items, self.open, self.thinking = kept[-MOST:], False, None
        self.changed += 1

    def asked(self, most=5):
        """What you last asked, newest first, each once: (its words, when)."""
        out, seen = [], set()
        for item in reversed(self.items):
            if item["kind"] == "you" and plain(item["text"]) not in seen:
                seen.add(plain(item["text"]))
                out.append((item["text"], item["at"]))
                if len(out) == most:
                    break
        return out


def title(items):
    """A chat's name in the list: its first words of yours, or hers if you've said nothing in it, or the name of the
    first file you attached."""
    first = next((i for i in items if i["kind"] == "you" and i["text"]), None) or \
        next((i for i in items if i["kind"] == "her"), None)
    if first:
        return first["text"][:80]
    files = next((i["files"] for i in items if i.get("files")), None)
    return os.path.basename(files[0])[:80] if files else "New chat"


class Chats:
    """Your chats, as ChatGPT and Claude keep them: the one open now (current) and those before it, each its lines
    (Thread.items), its title and when it last changed. A chat with nothing in it yet isn't listed. Kept whole in
    path, a JSON file of hers (chats.json); found: there was one to read."""

    def __init__(self, path):
        self.path, self.chats, self.current = path, [], None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.found = True
        except (OSError, ValueError):
            data, self.found = {}, False
        data = data if isinstance(data, dict) else {}
        chats = data.get("chats") if isinstance(data.get("chats"), list) else []
        self.chats = [c for c in chats if isinstance(c, dict) and c.get("id") and isinstance(c.get("items"), list)]
        self.current = data.get("current") or uuid.uuid4().hex[:12]

    def _get(self, cid):
        return next((c for c in self.chats if c["id"] == cid), None)

    def lines(self):
        """The open chat's lines, [] for a new one."""
        chat = self._get(self.current)
        return chat["items"] if chat else []

    def keep(self, items):
        """The open chat's lines as they are now, kept, it at the top of the list; with none it isn't listed."""
        items = [dict(i) for i in items]
        chat = self._get(self.current)
        if not items:
            if chat is not None:
                self.chats.remove(chat)
        else:
            if chat is None:
                chat = {"id": self.current}
                self.chats.append(chat)
            chat.update(items=items, title=title(items), at=items[-1]["at"])
        self.chats.sort(key=lambda c: -float(c.get("at") or 0))
        self.chats = [c for i, c in enumerate(self.chats) if i < CHATS_KEPT or c["id"] == self.current]
        self._write()

    def start(self):
        """A new chat open, with nothing in it yet; the one before stays in the list. Its id."""
        self.current = uuid.uuid4().hex[:12]
        self._write()
        return self.current

    def open(self, cid):
        """cid's lines, it now the open chat; None if there's no such chat."""
        chat = self._get(cid)
        if chat is None:
            return None
        self.current = cid
        self._write()
        return chat["items"]

    def delete(self, cid):
        """cid's chat gone from the list for good. True if it was the open one, which leaves a new one open."""
        self.chats = [c for c in self.chats if c["id"] != cid]
        was = cid == self.current
        if was:
            self.current = uuid.uuid4().hex[:12]
        self._write()
        return was

    def listed(self, most=None):
        """(id, title, when it last changed), newest first."""
        out = [(c["id"], c.get("title") or "New chat", float(c.get("at") or 0)) for c in self.chats]
        return out if most is None else out[:most]

    def _write(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path + ".tmp", "w", encoding="utf-8") as f:
                json.dump({"current": self.current, "chats": self.chats}, f, ensure_ascii=False)
            os.replace(self.path + ".tmp", self.path)  # whole or not at all: a crash mid-write leaves the last one
        except OSError as exc:
            print(f"  chat: couldn't keep your chats ({exc!r})")


def pending_message(siri):
    """The message her turn is waiting on your yes to send (siri.PENDING), for the rail's Outbox card: {"id",
    "contact", "app", "text"}; None if there's none."""
    pending = getattr(siri, "PENDING", None) or {}
    plan = pending.get("plan")
    if not isinstance(plan, dict) or time.time() >= float(pending.get("until") or 0):
        return None
    for step in plan.get("steps") or ():
        if isinstance(step, dict) and step.get("contact") and (step.get("text") or step.get("caption")):
            return {"id": str(pending.get("id") or int(float(pending.get("until") or 0))),
                    "contact": str(step["contact"]), "app": str(step.get("app") or ""),
                    "text": str(step.get("text") or step.get("caption"))}
    return None


def starting_why(app, thread):
    """What she's still doing before she can answer what's typed, or "" once she can: her controls loop (siri.CONTROLS)
    is the one that takes it, and it begins only once her speech models are loaded, so until it has, a line waits in
    app's queue. Not the header's word, which says Starting again for a voice that loads later while she answers."""
    siri = sys.modules.get("siri")
    up = siri is not None and getattr(siri, "CONTROLS", (None,))[0] is getattr(app, "controls", 0)
    return "" if up else thread.starting


def command_for(speaks):
    """What the chat puts in her controls for a line you typed: "chat" answers it in words only (siri.CHAT_TURN), "typed"
    is a turn like any typed to her, her answer said out loud as well as shown. speaks: Speak answers is on."""
    return "typed" if speaks else "chat"


def find(actions, query, most=SHOWN):
    """Her quick actions, (icon, name, kind, what does it), for what's typed after the slash, best first: every
    word of it somewhere in a name or a kind, one whose name starts with it on top. The first few of them all, in
    their order, for a slash alone."""
    words = plain(query).split()
    found = [a for a in actions if all(w in plain(f"{a[1]} {a[2]}") for w in words)]
    found.sort(key=lambda a: not plain(a[1]).startswith(plain(query)))
    return found[:most]


def held(rows):
    """The first task held for your yes, or None: the one the chat offers Approve and Cancel for."""
    return next((r for r in rows if r.get("status") == "waiting_approval"), None)


def level_height(rms):
    """How tall a bar of the waveform is for a mic loudness (its RMS, 0 to 1): 0 to 1, speech filling most of it and
    a room's hush near none."""
    return min(1.0, max(0.0, (float(rms) - 0.004) / 0.1) ** 0.65) if rms > 0.004 else 0.0


def clock(secs):
    m, s = divmod(int(secs + 0.999), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def composer_ppm(w, h, box, r, fill="#ffffff", line="#e5e7eb", back="#ffffff", lift=4, blur=18, dark=0.07):
    """The composer's card as a PPM, w by h: a rounded box (x0, y0, x1, y1) of fill with a hairline of line round it,
    on back, with a soft shadow under it lift px down and blur px wide, at most dark black: the floating white pill the
    owner asked for (22 November 2026: "elevated pill card, 1px solid #E5E7EB, a soft diffused shadow"). Drawn with
    numpy, its edges soft, once for each size (Box keeps them)."""
    import numpy as np
    hue = lambda c: np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], np.float32)  # noqa: E731
    x0, y0, x1, y1 = box
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32) + 0.5

    def distance(cy):  # to the rounded box's edge, below 0 inside it
        qx = np.abs(xs - (x0 + x1) / 2) - ((x1 - x0) / 2 - r)
        qy = np.abs(ys - cy) - ((y1 - y0) / 2 - r)
        return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
    d = distance((y0 + y1) / 2)
    shade = dark * np.exp(-np.maximum(distance((y0 + y1) / 2 + lift), 0) ** 2 / (2 * (blur / 2.2) ** 2))
    out = hue(back) * (1 - shade[..., None])  # the shadow, black at most dark on the ground
    edge = np.clip(0.5 - d, 0, 1)[..., None]  # inside the box's outline
    inner = np.clip(-0.5 - d, 0, 1)[..., None]  # inside its hairline
    out = out * (1 - edge) + hue(line) * edge
    out = out * (1 - inner) + hue(fill) * inner
    return b"P6 %d %d 255 " % (w, h) + (out + 0.5).clip(0, 255).astype("uint8").tobytes()


_FRAMED = {}


def framed(app, w, h, r, fill, line, back):
    """A rounded shape of fill with a 1 px hairline of line round it, on back, as one picture: two pictures laid one
    on the other left the line's colour in the corners, outside the curve. Made once for each size and kept."""
    key = (int(w), int(h), round(r, 1), fill, line, back)
    if key not in _FRAMED:
        _FRAMED[key] = tk.PhotoImage(master=app.root, format="ppm", data=composer_ppm(
            int(w), int(h), (0, 0, int(w), int(h)), r, fill=fill, line=line, back=back, dark=0))
    return _FRAMED[key]


def bubble_ppm(w, h, r, small, fill, back):
    """Your words' bubble as a PPM: rounded r at three corners and small at its top right, the corner by the edge
    it's said from, as the AI chats draw theirs ("rounded-2xl rounded-tr-sm")."""
    import numpy as np
    hue = lambda c: np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], np.float32)  # noqa: E731
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32) + 0.5
    rad = np.where((xs > w / 2) & (ys < h / 2), float(small), float(r))
    qx, qy = np.abs(xs - w / 2) - (w / 2 - rad), np.abs(ys - h / 2) - (h / 2 - rad)
    d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - rad
    a = np.clip(0.5 - d, 0, 1)[..., None]
    out = hue(back) * (1 - a) + hue(fill) * a
    return b"P6 %d %d 255 " % (w, h) + (out + 0.5).astype("uint8").tobytes()


_MOTION = []


def animations_on():
    """True unless Windows' "Show animations in Windows" is off (Settings > Accessibility > Visual effects): then cards
    and the dictation strip are just there, with no travel. Read once."""
    if not _MOTION:
        try:
            import ctypes
            on = ctypes.c_int(1)
            ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(on), 0)  # SPI_GETCLIENTAREAANIMATION
            _MOTION.append(bool(on.value))
        except Exception:
            _MOTION.append(True)
    return _MOTION[0]


def spring(t):
    """t from 0 to 1 eased as a damped spring settles: quick, a touch past 1, then home (the owner's "damped spring
    physics": stiffness 350, damping 30, a mass of 1, over the 0.42 s a card takes to come in)."""
    if t >= 1:
        return 1.0
    return 1 - math.exp(-6.3 * t) * (math.cos(4.7 * t) + 6.3 / 4.7 * math.sin(4.7 * t))


class Box:
    """The chat's box, Hedwig's own (22 November 2026, the owner, sending its screenshots: "see their original one,
    its quality and its theme"; it was a white floating card with a shadow for an evening, after a prompt): one soft
    grey rounded field, no line round it and no shadow, what you type along its top, growing a line at a time as you
    write more (Shift+Enter for a new line, Enter sends), and a row under it: a paperclip and her badge, her face and
    name, at the left; a small waveform and the round blue Send at the right. hint shows in grey while it's empty.

    The paperclip attaches files (as does Ctrl+V of copied files or a picture: attach.py), which wait as white chips
    over the words, each with a cross, and go with what's sent. Her badge opens a small menu: attach files, talk to her
    out loud, and whether typed answers are said too.

    The waveform dictates, as ChatGPT's does: the row opens into Cancel, a live strip of what the mic hears with how
    long, and Done, and what was said is written into the box to look over and send (mic(action): "start", "done",
    "cancel", siri.box_voice). While she hears you otherwise (right Alt, or Talk) its bars move with your voice, in
    red. talk(): a voice turn.
    It answers to what her window asks of Home's box: get, clear, focus_force, bind."""
    BAND = 44  # the chips' row over the words, while there are any
    WAVE_MS, VOICE_MOST, WRITING_MOST = 40, 300, 45  # the waveform drawn this often; dictation's longest; its write-up's
    TALL, ROUND, MOST_LINES = 84, 28, 6  # the box's least height and its corners (Hedwig's 32 at TYPE); its lines
    RING_STEPS = 24  # the busy ring's places round the edge, made one a frame as it goes and kept
    SIDE, TOP, FOOT = 0, 0, 0  # no room round it: no shadow to make room for
    SOFT, SOFT_OVER = "#f1f3f4", "#e5e7eb"  # the menu's row under the mouse

    def __init__(self, app, parent, ui, hint, send, face, mic=None, talk=None):
        self.app, self.ui, self.hint, px = app, ui, hint, app.px
        self.showing, self.face_image, self.lines = False, face, 1
        self.files = []  # attached, waiting to go with the next line sent
        self.send_fn, self.talk_fn, self.mic_fn = send, talk, mic
        self.hearing, self.voice, self.voice_at, self.wave_job, self.bar_job = False, None, 0.0, None, None
        self.cards = {}  # the composer's card for each size, kept
        self.ring, self.rings, self.ring_at, self.ring_job = None, {}, 0, None  # its ring (set_ring)
        self.focus_on = self.busy_on = False
        size = app.f_chat[1] if isinstance(app.f_chat[1], int) else -15
        self.font = (app.f_chat[0], size)  # 15 px, as the thread's (the owner: "crisp 15px placeholder")
        import tkinter.font as tkfont
        self.line_h = tkfont.Font(root=app.root, font=self.font).metrics("linespace")
        self.h = self._height()
        c = self.canvas = tk.Canvas(parent, height=self.h, bg=ui.BG, highlightthickness=0, bd=0)
        self.back = c.create_image(0, 0, anchor="nw")
        self.entry = tk.Text(c, height=1, wrap="word", font=self.font, bd=0, relief="flat", bg=FIELD, fg=ui.TEXT,
                             insertbackground=ui.TEXT, highlightthickness=0, padx=0, pady=0, undo=True, maxundo=50,
                             selectbackground=ui.TINTS["blue"][1], selectforeground=ui.TEXT)
        self.window = c.create_window(0, 0, anchor="nw", window=self.entry)
        # the paperclip at the row's left, as Hedwig's: a click picks files to attach
        self.clip = c.create_text(0, 0, anchor="w", text="\ue723", font=app.f_icon, fill=ui.MUTED, tags="clip")
        self._hover("clip", lambda on: c.itemconfigure(self.clip, fill=ui.TEXT if on else ui.MUTED))
        c.tag_bind("clip", "<Button-1>", lambda e: self.pick())
        # her badge by it, as Hedwig's workspace badge: her face and her name, which open the menu (_menu)
        self.face = c.create_image(0, 0, anchor="w", image=face, tags="badge") if face is not None else None
        self.name = c.create_text(0, 0, anchor="w", text=identity.name(), font=app.f_badge, fill=ui.TEXT, tags="badge")
        self._hover("badge", lambda on: c.itemconfigure(self.name, fill=ui.ACCENT if on else ui.TEXT))
        c.tag_bind("badge", "<Button-1>", lambda e: self._menu())
        self.plus_back = self.plus = None  # (the + of the white composer, gone with it)
        # the waveform: five thin bars, no button round them, dictation (voice_start)
        self.wave_back = c.create_rectangle(0, 0, 0, 0, fill="", outline="", tags="wavebutton")  # what's clicked
        self.bars = [c.create_line(0, 0, 0, 0, fill=ui.MUTED, width=px(1.8), capstyle="round", tags="wavebutton")
                     for _ in range(5)]
        self.over_wave = False
        self._hover("wavebutton", lambda on: (setattr(self, "over_wave", on), self._lay_bars()))
        if mic is not None:
            c.tag_bind("wavebutton", "<Button-1>", lambda e: self.voice_start())
        # Send, round and blue, paler while there's nothing to send
        self.button = c.create_image(0, 0, anchor="center", tags="send")
        self.arrow = c.create_text(0, 0, text="\ue74a", font=app.f_icon_small, fill="#ffffff", tags="send")
        self.over_send = False
        self._hover("send", lambda on: self._paint_send(over=on))
        c.tag_bind("send", "<Button-1>", lambda e: self._send_click())
        # what dictation shows along the row: Cancel, the strip with its bars and how long, and Done; "Writing it
        # down" in the strip while what was said is written up
        self.strip = c.create_image(0, 0, anchor="w", state="hidden", tags="voice")
        self.wave = []
        self.timer = c.create_text(0, 0, anchor="e", font=app.f_badge, fill=ui.MUTED, state="hidden", tags="voice")
        self.writing = c.create_text(0, 0, anchor="w", text="Writing it down\u2026", font=app.f_badge, fill=ui.MUTED,
                                     state="hidden", tags="voice")
        self.cancel_back = c.create_image(0, 0, anchor="w", state="hidden", tags=("voice", "cancel"))
        self.cancel_x = c.create_text(0, 0, text="Cancel", font=app.f_badge, fill=ui.TEXT, state="hidden",
                                      tags=("voice", "cancel"))
        self.done_back = c.create_image(0, 0, anchor="e", state="hidden", tags=("voice", "done"))
        self.done_tick = c.create_text(0, 0, text="Done", font=app.f_badge, fill="#ffffff", state="hidden",
                                       tags=("voice", "done"))
        self.done_icon = c.create_text(0, 0, text="\ue73e", font=app.f_icon_small, fill="#ffffff", state="hidden",
                                       tags=("voice", "done"))
        for tag, action in (("cancel", "cancel"), ("done", "done")):
            c.tag_bind(tag, "<Button-1>", lambda e, a=action: self.voice_end(a))
            self._hover(tag, lambda on: None)
        # Send pressed: 96% of itself till it's let go (better-motion's press scale)
        c.tag_bind("send", "<ButtonPress-1>", lambda e: self._press(self.button, 32, None), add="+")
        c.tag_bind("send", "<ButtonRelease-1>", lambda e: self._lay(), add="+")
        self.speaks = bool(ui.settings.get("chat_speaks"))
        c.bind("<Configure>", lambda e: self._lay())
        c.bind("<Button-1>", lambda e: self.entry.focus_set(), add="+")
        # the hint stays while the box has the keyboard, till the first key: as a placeholder does
        self.entry.bind("<Key>", self._key, add="+")
        self.entry.bind("<FocusIn>", lambda e: self.showing and self.entry.mark_set("insert", "1.0"), add="+")
        self.entry.bind("<ButtonRelease-1>", lambda e: self.showing and self.entry.mark_set("insert", "1.0"), add="+")
        self.entry.bind("<FocusOut>", self._left, add="+")
        self.entry.bind("<FocusIn>", lambda e: self.set_ring(focus=True), add="+")
        self.entry.bind("<FocusOut>", lambda e: self.set_ring(focus=False), add="+")
        self.entry.bind("<Control-v>", self._paste, add="+")
        self.entry.bind("<Control-V>", self._paste, add="+")
        self.entry.bind("<Shift-Return>", self._newline)
        self._left()

    # ------------------------------------------------------------------ its parts
    def _circle(self, size, colour):
        r = self.app.px(size) / 2
        return self.app.smooth(2 * r, 2 * r, r, colour, FIELD)  # on the box's grey

    def _press(self, item, size, colour):
        """A round button held down: 96% of its size, the press scale, till it's let go (_lay draws it back)."""
        if colour is None:  # Send's own colour, as it is now
            ui = self.ui
            colour = ui.mix(ui.ACCENT, FIELD, 0.5) if self._empty() else ui.mix(ui.ACCENT, "#000000", 0.12)
        self.canvas.itemconfigure(item, image=self._circle(size * 0.96, colour))

    def _hover(self, tag, paint):
        c = self.canvas
        c.tag_bind(tag, "<Enter>", lambda e: (c.configure(cursor="hand2"), paint(True)))
        c.tag_bind(tag, "<Leave>", lambda e: (c.configure(cursor=""), paint(False)))

    def _height(self):
        px = self.app.px
        return px(self.TOP) + px(self.TALL) + (self.lines - 1) * self.line_h + \
            (px(self.BAND) if self.files else 0) + px(self.FOOT)

    def _card(self, w, h):
        """The box's grey rounded field for this size, with its ring: none, the accent's hairline while it has the
        keyboard, or the gradient at its place round the edge while she's busy (chatfx.ring_ppm). Each kept."""
        import chatfx
        state = self.ring if animations_on() or self.ring != "busy" else "focus"
        if state is None:
            return self.app.smooth(w, h, self.app.px(self.ROUND), FIELD, self.ui.BG)
        phase = None if state == "focus" else (self.ring_at % self.RING_STEPS) / self.RING_STEPS
        key = (w, h, phase)
        if key not in self.rings:
            self.rings[key] = tk.PhotoImage(master=self.app.root, format="ppm", data=chatfx.ring_ppm(
                w, h, self.app.px(self.ROUND), FIELD, self.ui.BG, phase))
            if len(self.rings) > self.RING_STEPS + 6:
                self.rings.pop(next(iter(self.rings)))
        return self.rings[key]

    def set_ring(self, focus=None, busy=None):
        """Its ring for what's happening: busy (she's listening, thinking, or you're dictating) travels round it;
        focus alone is a still hairline."""
        if focus is not None:
            self.focus_on = focus
        if busy is not None:
            self.busy_on = busy
        ring = "busy" if self.busy_on or self.voice == "rec" else "focus" if self.focus_on else None
        if ring != self.ring:
            self.ring = ring
            self.canvas.itemconfigure(self.back, image=self._card(self.canvas.winfo_width(), self.h)) \
                if self.canvas.winfo_width() > 1 else None
            if ring == "busy" and self.ring_job is None:
                self._ring_tick()

    def _ring_tick(self):
        """The gradient a step further round, about 16 a second, while she's busy."""
        self.ring_job = None
        if self.ring != "busy":
            return
        self.ring_at += 1
        w = self.canvas.winfo_width()
        if w > 1:
            self.canvas.itemconfigure(self.back, image=self._card(w, self.h))
        self.ring_job = self.app.root.after(60, self._ring_tick)

    def _menu(self):
        """Her badge's menu, opening up from it: attach files, talk to her out loud, and whether typed answers are
        said."""
        ui, app = self.ui, self.app
        menu = tk.Menu(self.canvas, tearoff=0, font=app.f_body, bg="#ffffff", fg=ui.TEXT, activebackground=self.SOFT,
                       activeforeground=ui.TEXT, relief="flat", bd=0, activeborderwidth=0)
        menu.add_command(label="  Attach files\u2026", command=self.pick)
        if self.talk_fn is not None:
            menu.add_command(label=f"  Talk to {identity.name()}", command=self.talk_fn)
        self.speak_var = tk.BooleanVar(master=app.root, value=self.speaks)
        menu.add_checkbutton(label="  Say typed answers out loud", variable=self.speak_var,
                             command=lambda: self.speak(self.speak_var.get()))
        x, y = getattr(self, "badge_at", (0, 0))
        menu.update_idletasks()
        try:
            menu.tk_popup(self.canvas.winfo_rootx() + x - self.app.px(6),
                          self.canvas.winfo_rooty() + y - self.app.px(16) - menu.winfo_reqheight())
        finally:
            menu.grab_release()

    # ------------------------------------------------------------------ files
    def pick(self):
        """Files picked in Windows' own Open box, attached."""
        from tkinter import filedialog
        try:
            paths = filedialog.askopenfilenames(parent=self.canvas.winfo_toplevel(), title="Attach files")
        except tk.TclError:
            paths = ()
        self.attach(paths)
        self.entry.focus_set()

    def attach(self, paths):
        """paths in the box, each once, up to attach.MOST_FILES. True if any came in."""
        import attach
        before = len(self.files)
        for path in paths or ():
            path = os.path.normpath(str(path))
            if os.path.isfile(path) and path not in self.files and len(self.files) < attach.MOST_FILES:
                self.files.append(path)
        if len(self.files) != before:
            self._focused()
            self._resize()
            return True
        return False

    def drop(self, i):
        """The i-th file out of the box again."""
        if 0 <= i < len(self.files):
            del self.files[i]
            self._resize()

    def take(self):
        """The files attached, and the box without them."""
        files, self.files = self.files, []
        if files:
            self._resize()
        return files

    def _paste(self, event=None):
        """Ctrl+V: files copied in File Explorer, or a picture copied (a screenshot), attached; words pasted as ever."""
        win = getattr(self.ui, "win", None)
        try:
            files = win.clipboard_files() if win is not None else []
            if files:
                return "break" if self.attach(files) else None
            dib = win.clipboard_picture() if win is not None else None
            if dib:
                import attach
                png = attach.dib_png(dib)
                if png:
                    folder = os.path.join(win.home("LOCALAPPDATA"), "attachments")
                    return "break" if self.attach([attach.keep_pasted(png, folder)]) else None
        except Exception as exc:  # the clipboard is anyone's: what's on it never breaks the box
            print(f"  chat: couldn't take what was pasted ({exc!r})")
        if self.showing:  # words pasted over the hint replace it
            self._focused()
        self.canvas.after_idle(self._grow)
        return None

    def _resize(self):
        h = self._height()
        if h != self.h:
            self.h = h
            self.canvas.configure(height=h)
        self._lay()

    def _grow(self):
        """As many lines tall as what's typed takes, up to MOST_LINES; past that it scrolls."""
        try:
            got = self.entry.count("1.0", "end-1c", "displaylines")
            lines = (got[0] if isinstance(got, tuple) else got or 0) + 1
        except tk.TclError:
            return
        lines = max(1, min(self.MOST_LINES, lines))
        if lines != self.lines:
            self.lines = lines
            self._resize()

    def _newline(self, event=None):
        """Shift+Enter: a new line in what you're writing, as the AI chats have it (Enter sends)."""
        self._focused()
        self.entry.insert("insert", "\n")
        self.canvas.after_idle(self._grow)
        return "break"

    def _chips(self, w, top):
        """The files' chips along the top of the box: a soft pill each with its mark, its name cut to fit and a cross,
        as many as the width has room for, then how many more."""
        c, px, ui, app = self.canvas, self.app.px, self.ui, self.app
        import attach
        c.delete("chip")
        self.chip_photos = []
        x, h, end = px(self.SIDE) + px(14), px(32), w - px(self.SIDE) - px(14)
        for i, path in enumerate(self.files):
            name = os.path.basename(path)
            name = name if len(name) <= 26 else name[:16] + "\u2026" + name[-8:]
            width = px(30) + app._measure(app.f_badge, name) + px(30)
            more = len(self.files) - i
            if x + width > end - (px(40) if more > 1 else 0):
                c.create_text(x + px(4), top + h // 2, anchor="w", text=f"+{more}", font=app.f_badge,
                              fill=ui.MUTED, tags="chip")
                break
            photo = app.smooth(width, h, px(10), "#ffffff", FIELD)  # white on the box's grey
            self.chip_photos.append(photo)
            c.create_image(x, top, anchor="nw", image=photo, tags="chip")
            c.create_text(x + px(11), top + h // 2, anchor="w", text=attach.icon(path), font=app.f_icon_small,
                          fill=ui.ACCENT, tags="chip")
            c.create_text(x + px(30), top + h // 2, anchor="w", text=name, font=app.f_badge, fill=ui.TEXT,
                          tags="chip")
            cross = c.create_text(x + width - px(14), top + h // 2, text="\ue711", font=app.f_fold, fill=ui.MUTED,
                                  tags=("chip", f"cross{i}"))
            c.tag_bind(f"cross{i}", "<Button-1>", lambda e, i=i: self.drop(i))
            c.tag_bind(f"cross{i}", "<Enter>", lambda e, k=cross: (c.configure(cursor="hand2"),
                                                                    c.itemconfigure(k, fill=ui.TEXT)))
            c.tag_bind(f"cross{i}", "<Leave>", lambda e, k=cross: (c.configure(cursor=""),
                                                                    c.itemconfigure(k, fill=ui.MUTED)))
            x += width + px(8)

    def _key(self, event):
        if self.showing and (event.char and event.char.isprintable() or event.keysym in ("BackSpace", "Delete")):
            self._focused()
        self.canvas.after_idle(self._grow)

    def _lay(self):
        c, px = self.canvas, self.app.px
        w = c.winfo_width()
        if w < 2:
            return
        c.itemconfigure(self.back, image=self._card(w, self.h))
        left, top = px(self.SIDE), px(self.TOP)
        band = px(self.BAND) if self.files else 0
        self._chips(w, top + px(10)) if self.files else c.delete("chip")
        # what you type: 18 px in, 16 under its top (or the chips)
        c.coords(self.window, left + px(18), top + band + px(15))
        c.itemconfigure(self.window, width=max(px(60), w - 2 * left - px(36)), height=self.lines * self.line_h)
        # the row, 22 px up from its foot: the paperclip and her badge at the left, the waveform and Send at the right
        low = self.h - px(self.FOOT) - px(26)  # Send's corners inside the box's own curve, not past it
        c.coords(self.clip, left + px(16), low)
        x = left + px(50)  # 24 px clear of the paperclip's glyph, as borderless controls want (better-layout)
        self.badge_at = (x, low)
        if self.face is not None:
            c.coords(self.face, x, low)
            x += self.face_image.width() + px(6)
        c.coords(self.name, x, low)
        cx = w - left - px(28)
        self.send_at, self.wave_at = (cx, low), (cx - px(36), low)
        c.coords(self.button, cx, low)
        c.coords(self.arrow, cx, low)
        c.coords(self.wave_back, cx - px(48), low - px(12), cx - px(24), low + px(12))
        self._lay_bars()
        self._paint_send()
        if self.voice:
            self._lay_voice(w)

    # ------------------------------------------------------------------ voice
    def _empty(self):
        return not self.get() and not self.files

    def _send_click(self):
        """Send what's typed and attached; with nothing there, the box gets the keyboard."""
        if self._empty():
            self.entry.focus_set()
        else:
            self.send_fn()

    def _paint_send(self, over=None):
        """Send: her blue once there's something to send, paler till then, darker under the mouse."""
        if over is not None:
            self.over_send = over
        ui, empty = self.ui, self._empty()
        colour = ui.mix(ui.ACCENT, FIELD, 0.5) if empty else \
            ui.mix(ui.ACCENT, "#000000", 0.12) if self.over_send else ui.ACCENT
        self.canvas.itemconfigure(self.button, image=self._circle(32, colour))

    def _lay_bars(self, levels=None):
        """The waveform button's five pill bars, still, or as tall as levels (five, 0 to 1) while she hears you."""
        cx, cy = getattr(self, "wave_at", (0, 0))
        px = self.app.px
        ui = self.ui
        for i, bar in enumerate(self.bars):
            tall = (0.35, 0.75, 1.0, 0.6, 0.3)[i] if levels is None else 0.2 + 0.8 * levels[i]
            half = max(px(1.2), tall * px(6))
            x = cx + (i - 2) * px(3.4)
            self.canvas.coords(bar, x, cy - half, x, cy + half)
            self.canvas.itemconfigure(bar, fill=ui.ERROR if self.hearing else ui.TEXT if getattr(self, "over_wave", False)
                                      else ui.MUTED)

    def _bar_tick(self):
        """While she hears you (right Alt, or Talk): the button's bars moving with your voice (siri.MIC_LEVELS)."""
        self.bar_job = None
        if not self.hearing:
            self._lay_bars()
            return
        siri = sys.modules.get("siri")
        got = list(getattr(siri, "MIC_LEVELS", ()))[-5:]
        got = [0.0] * (5 - len(got)) + got
        self._lay_bars([level_height(v) for v in (got[0], got[2], got[4], got[3], got[1])])
        self.bar_job = self.app.root.after(90, self._bar_tick)

    def voice_start(self):
        """The waveform button: dictation into the box, its strip opening out along the row."""
        if self.voice or self.mic_fn is None:
            return
        self.voice, self.voice_at = "rec", time.time()
        self.mic_fn("start")
        self._show_voice(True)
        self.set_ring()
        if animations_on():  # opening out from the waveform button, a small element's 300 ms
            self.app.animate("box voice", 300, lambda t: self._open_strip(spring(t)))
        self._wave_tick()

    def voice_end(self, action):
        """Done (what was said written into the box) or Cancel (thrown away)."""
        if self.voice != "rec":
            return
        self.mic_fn(action)
        if action == "done":
            self.voice, self.voice_at = "writing", time.time()
            for item in self.wave:
                self.canvas.itemconfigure(item, state="hidden")
            for tag in ("cancel", "done"):
                self.canvas.itemconfigure(tag, state="hidden")
            self.canvas.itemconfigure(self.timer, state="hidden")
            self.canvas.itemconfigure(self.writing, state="normal")
        else:
            self._show_voice(False)

    def voice_key(self, action):
        """Enter (done) or Esc (cancel) while dictating; True if it was taken."""
        if self.voice == "rec":
            self.voice_end(action)
            return True
        return bool(self.voice)

    def voice_words(self, text):
        """What was said, written down (siri's "Box words"): after what's typed already, and the box back."""
        if not self.voice:
            return
        self._show_voice(False)
        text = " ".join(str(text or "").split())
        if text:
            was = self.get().rstrip()
            self.put(f"{was} {text}" if was else text)
        self.entry.focus_set()

    def _show_voice(self, on):
        c = self.canvas
        if not on:
            self.voice = None
            self.app.root.after_idle(self.set_ring)
            if self.wave_job is not None:
                self.app.root.after_cancel(self.wave_job)
                self.wave_job = None
        for item in (self.clip, self.name, self.wave_back, self.button, self.arrow, *self.bars) + \
                ((self.face,) if self.face is not None else ()):
            c.itemconfigure(item, state="hidden" if on else "normal")
        c.itemconfigure("voice", state="normal" if on else "hidden")
        c.itemconfigure(self.writing, state="hidden")
        for item in self.wave:
            c.itemconfigure(item, state="normal" if on else "hidden")
        self.strip_open = 0.0 if on else 1.0
        self._lay()

    def _open_strip(self, t):
        self.strip_open = t
        w = self.canvas.winfo_width()
        if self.voice and w > 1:
            self._lay_voice(w)

    def _lay_voice(self, w):
        """Cancel at the row's left, Done at its right, and between them the strip, opening out from where the
        waveform button was (strip_open, 0 to 1), its bars and how long in it."""
        c, px, ui, app = self.canvas, self.app.px, self.ui, self.app
        left = px(self.SIDE) + px(12)
        right = w - px(self.SIDE) - px(12)
        cy = self.send_at[1] if hasattr(self, "send_at") else self.h // 2
        h = px(32)
        cancel_w = app._measure(app.f_badge, "Cancel") + px(32)
        done_w = app._measure(app.f_badge, "Done") + px(52)
        c.itemconfigure(self.cancel_back, image=app.smooth(cancel_w, h, h / 2, "#ffffff", FIELD))
        c.coords(self.cancel_back, left, cy)
        c.coords(self.cancel_x, left + cancel_w / 2, cy)
        c.itemconfigure(self.done_back, image=app.smooth(done_w, h, h / 2, ui.ACCENT, FIELD))
        c.coords(self.done_back, right, cy)
        c.coords(self.done_icon, right - done_w + px(20), cy)
        c.coords(self.done_tick, right - done_w / 2 + px(9), cy)
        x1 = right - done_w - px(10)
        full0 = left + cancel_w + px(10)
        start = getattr(self, "wave_at", (x1, cy))[0] - px(12)
        x0 = int(start + (full0 - start) * max(0.0, getattr(self, "strip_open", 1.0)))
        sw = max(px(38), x1 - x0)
        c.itemconfigure(self.strip, image=app.smooth(sw, h, h / 2, "#ffffff", FIELD))
        c.coords(self.strip, x1 - sw, cy)
        c.coords(self.timer, x1 - px(14), cy)
        c.coords(self.writing, x1 - sw + px(16), cy)
        b0, b1, step = x1 - sw + px(16), x1 - px(56), px(5)
        n = max(0, (b1 - b0) // step)
        while len(self.wave) < n:
            self.wave.append(c.create_line(0, 0, 0, 0, fill=ui.TEXT, width=px(2.4), capstyle="round",
                                           tags="wave", state="normal" if self.voice == "rec" else "hidden"))
        while len(self.wave) > n:
            c.delete(self.wave.pop())
        self.wave_box = (b0, b1, step, cy)
        self._draw_wave()

    def _draw_wave(self):
        """The bars as loud as the last of what the mic heard, the newest at the right, quiet ones a dot."""
        if not self.wave or not hasattr(self, "wave_box"):
            return
        c, px = self.canvas, self.app.px
        x0, x1, step, cy = self.wave_box
        siri = sys.modules.get("siri")
        levels = list(getattr(siri, "BOX_LEVELS", ()))[-len(self.wave):] if self.voice == "rec" else []
        levels = [0.0] * (len(self.wave) - len(levels)) + levels
        tallest = px(13)
        for i, (bar, level) in enumerate(zip(self.wave, levels)):
            x = x0 + i * step
            half = max(px(1.3), level_height(level) * tallest)
            c.coords(bar, x, cy - half, x, cy + half)
            c.itemconfigure(bar, fill=self.ui.TEXT if level_height(level) > 0.06 else self.ui.FAINT)

    def _wave_tick(self):
        self.wave_job = None
        if self.voice == "writing" and time.time() - self.voice_at > self.WRITING_MOST:
            self._show_voice(False)  # no words came back: the box as it was, not stuck
            return
        if self.voice != "rec":
            if self.voice:
                self.wave_job = self.app.root.after(200, self._wave_tick)
            return
        took = time.time() - self.voice_at
        if took >= self.VOICE_MOST:  # the longest a dictation goes: written down as far as it got
            self.voice_end("done")
            self.wave_job = self.app.root.after(200, self._wave_tick)
            return
        self.canvas.itemconfigure(self.timer, text=clock(took) if took >= 1 else "0:00")
        self._draw_wave()
        self.wave_job = self.app.root.after(self.WAVE_MS, self._wave_tick)

    def listening(self, on):
        """She's hearing you, from Talk or right Alt: the waveform button's bars red and moving with your voice."""
        if on != self.hearing:
            self.hearing = on
            self._lay_bars()
            if on and self.bar_job is None:
                self._bar_tick()

    def speak(self, on):
        """Speak answers on or off, kept (settings chat_speaks); the next line you type is answered that way."""
        self.speaks = bool(on)
        self.ui.settings.put("chat_speaks", self.speaks)
        menu = getattr(self, "speak_var", None)  # the + menu's tick, the same switch
        if menu is not None and bool(menu.get()) != self.speaks:
            menu.set(self.speaks)
        var = getattr(self.app, "chat_speaks_var", None)  # Settings' own checkbox, the same switch
        if var is not None and bool(var.get()) != self.speaks:
            var.set(self.speaks)

    # ------------------------------------------------------------------ what's typed
    def _focused(self, _=None):
        if self.showing:
            self.showing = False
            self.entry.delete("1.0", "end")
            self.entry.configure(fg=self.ui.TEXT)
        self.canvas.after_idle(self._paint_send)

    def _left(self, _=None):
        if not self.showing and not self.entry.get("1.0", "end-1c"):
            self.showing = True
            self.entry.configure(fg=self.ui.FAINT)
            self.entry.insert("1.0", self.hint)
            self.entry.mark_set("insert", "1.0")

    def get(self):
        return "" if self.showing else self.entry.get("1.0", "end-1c")

    def put(self, text):
        self._focused()
        self.entry.delete("1.0", "end")
        self.entry.insert("1.0", text)
        self.entry.mark_set("insert", "end-1c")
        self.canvas.after_idle(self._grow)

    def clear(self):
        self._focused()
        self.entry.delete("1.0", "end")
        self._paint_send()
        self.canvas.after_idle(self._grow)
        try:
            focused = self.entry.focus_get() is self.entry
        except (KeyError, tk.TclError):
            focused = False
        if not focused:
            self._left()

    def bind(self, *args, **kw):
        return self.entry.bind(*args, **kw)

    def focus_set(self):
        self.entry.focus_set()

    def focus_force(self):
        self.entry.focus_force()


# ------------------------------------------------------------------ the right side: what she made, what she looked at
def context_lines(found, most=900):
    """What a look-up found (siri.show_context) as plain lines for its card: titles, snippets and values, in order,
    each once, about most letters in all."""
    out, seen = [], set()
    keep = ("title", "name", "subject", "summary", "snippet", "description", "text", "say", "when", "where", "temp",
            "conditions", "forecast", "source", "url", "path", "said", "reply")

    def add(text):
        text = " ".join(str(text).split())
        if text and text.lower() not in seen and sum(map(len, out)) < most:
            seen.add(text.lower())
            out.append(text if len(text) <= 220 else text[:217] + "\u2026")

    def walk(v, depth=0):
        if depth > 5 or sum(map(len, out)) >= most:
            return
        if isinstance(v, dict):
            for k in keep:
                if isinstance(v.get(k), (str, int, float)) and str(v.get(k)).strip():
                    add(v[k] if k in ("title", "name", "subject", "summary", "snippet", "description", "text", "say")
                        else f"{k.capitalize()}: {v[k]}")
            for k, val in v.items():
                if k not in keep and isinstance(val, (dict, list)):
                    walk(val, depth + 1)
                elif k not in keep and isinstance(val, str) and len(val) > 30:
                    add(val)
        elif isinstance(v, list):
            for item in v[:12]:
                walk(item, depth + 1)
        elif isinstance(v, str):
            for line in v.splitlines():
                add(line)
    walk(found)
    return out


DOMAIN_APPS = (  # a page's address, the app it is: its frame's name and, for some, its own look (Bento._view_of)
    ("mail.google.com", "Gmail"), ("notion.so", "Notion"), ("notion.site", "Notion"), ("figma.com", "Figma"),
    ("docs.google.com", "Google Docs"), ("calendar.google.com", "Google Calendar"), ("drive.google.com", "Drive"),
    ("github.com", "GitHub"), ("youtube.com", "YouTube"), ("linkedin.com", "LinkedIn"), ("x.com", "X"),
    ("twitter.com", "X"), ("reddit.com", "Reddit"), ("wikipedia.org", "Wikipedia"), ("slack.com", "Slack"),
)


def host_of(url):
    """A page's address without its scheme, www and path: "juniper.co"."""
    return re.sub(r"^(?:https?://)?(?:www\.)?", "", str(url or "")).split("/")[0].lower()


def site_app(url):
    """The app a page's address is, "Gmail" or "Notion", or its host if it's none of those; "" with no address."""
    host = host_of(url)
    return next((name for domain, name in DOMAIN_APPS if host == domain or host.endswith("." + domain)), host)


def theme_of(found):
    """A page's own colour, as it declares it (web.read's "theme"), or None."""
    page = found.get("page") if isinstance(found, dict) and isinstance(found.get("page"), dict) else {}
    theme = str(page.get("theme") or "")
    if re.fullmatch(r"#[0-9a-f]{3}", theme):
        theme = "#" + "".join(ch * 2 for ch in theme[1:])
    return theme if re.fullmatch(r"#[0-9a-f]{6}", theme) else None


def window_app(title):
    """The app a window's title names, for the frame of what she saw: "Gmail" for "Inbox - Gmail - Google Chrome",
    else its last part, the app itself ("Figma", "Google Chrome")."""
    parts = [p.strip() for p in re.split(r"\s+[-\u2013\u2014|]\s+", str(title or "")) if p.strip()]
    for domain, name in DOMAIN_APPS:
        if any(name.lower() == p.lower() for p in parts):
            return name
    return parts[-1] if parts else "Screen"


def app_of(label, do=""):
    """The app a look-up stands for on its card, (name, mark): Calendar, Web, Files ... from its words."""
    found = sources([{"text": label, "state": "done"}])
    return found[0] if found else ((do or "Look-up").replace("_", " ").capitalize(), "\ue721")


def card_ppm(w, h, px, line="#f2f2f2", back="#fafafa", fill="#ffffff", radius=12, shadow=True, lead=0):
    """A card's picture, w by h: white with the faintest hairline round it (black at 5%), its 12 px corners, and a
    soft ambient shadow (black at 3%, 12 px), on the canvas: the owner's "anti-wireframe styling"."""
    m, top, foot = (px(7), px(2), px(10)) if shadow else (0, 0, 0)
    return composer_ppm(w, h, (m, top + lead, w - m, h - foot), px(radius), fill=fill, line=line, back=back, lift=px(2),
                        blur=px(12), dark=0.035 if shadow else 0)


class Hero:
    """The empty page's greeting (chatfx): a canvas in the middle of the thread's room with the aurora drifting behind,
    the greeting in its gradient, the question under it and the four suggestions, which send themselves. It comes in
    with a spring, the suggestions 60 ms apart (ui-ux-pro-max's stagger), and its aurora plays only while it's up, on
    the chat's tab, with Windows' animations on."""
    W, H = 640, 330

    def __init__(self, app, parent, ui, page):
        self.app, self.ui, self.page, self.px = app, ui, page, app.px
        self.canvas = tk.Canvas(parent, bg=ui.BG, highlightthickness=0, bd=0)
        self.frames, self.at, self.job, self.making, self.drawn, self.up = [], 0, None, False, None, False

    def show(self):
        """Up in the middle of the page, drawn and coming in. False if it can't be drawn (then the plain words)."""
        try:
            self._draw()
        except Exception as exc:  # GDI or a font missing: the page keeps its plain words
            print(f"  chat: couldn't draw the greeting ({exc!r})")
            return False
        self.canvas.place(relx=0.5, rely=0.42, anchor="center")
        self.up = True
        self._come_in()
        self._aurora()
        return True

    def hide(self):
        self.up = False
        self.canvas.place_forget()
        if self.job is not None:
            self.app.root.after_cancel(self.job)
            self.job = None

    def _draw(self):
        import chatfx
        app, px, ui, c = self.app, self.px, self.ui, self.canvas
        w, h = px(self.W), px(self.H)
        name = " ".join(str(ui.settings.get("name") or "").split()).split(" ")[0]
        words = chatfx.greeting(name=name)
        if self.drawn == (w, words):
            return
        c.delete("all")
        c.configure(width=w, height=h)
        self.aurora_item = c.create_image(w // 2, h // 2 - px(20), tags="aurora")
        png, gw, gh = chatfx.greeting_png(words, "Plus Jakarta Sans SemiBold", px(32))
        # its letters in the gradient with nothing round them, so the aurora shows through between them
        self.greet = tk.PhotoImage(master=app.root, data=base64.b64encode(png), format="png")
        c.create_image(w // 2, px(118), image=self.greet, tags=("greet", "lift"))
        c.create_text(w // 2, px(166), text=ASK, font=(app.f_body[0], round(app.f_body[1] * 1.2)), fill=ui.MUTED,
                      tags=("ask", "lift"))
        self.chips = []
        x, y, row = 0, px(214), []
        for n, (mark, text, fill, ink) in enumerate(chatfx.SUGGESTIONS):
            cw = app._measure(app.f_small, text) + px(46)
            tag = f"chip{n}"
            photo = tk.PhotoImage(master=app.root, format="png",
                                  data=base64.b64encode(chatfx.pill_png(cw, px(34), px(17), fill)))  # over the aurora
            self.chips.append(photo)
            c.create_image(0, 0, anchor="w", image=photo, tags=(tag, "chip"))
            c.create_text(px(16), 0, text=mark, font=app.f_icon_small, fill=ink, tags=(tag, "chip"))
            c.create_text(px(32), 0, anchor="w", text=text, font=app.f_small, fill=ui.TEXT, tags=(tag, "chip"))
            c.tag_bind(tag, "<Button-1>", lambda e, t=text: self.page.send(t))
            c.tag_bind(tag, "<Enter>", lambda e: c.configure(cursor="hand2"))
            c.tag_bind(tag, "<Leave>", lambda e: c.configure(cursor=""))
            row.append((tag, cw))
        # two rows of two, each row centred, 10 px between chips and rows
        self.chip_rows = [row[:2], row[2:]]
        for r, chips in enumerate(self.chip_rows):
            total = sum(cw for _, cw in chips) + px(10) * (len(chips) - 1)
            x = (w - total) // 2
            for tag, cw in chips:
                c.move(tag, x, y + r * px(44))
                x += cw + px(10)
        self.drawn = (w, words)
        if not self.frames and not self.making:
            self._make_aurora(w, h)

    def _make_aurora(self, w, h):
        """The aurora's loop, made at half size on a thread (numpy's work, 24 frames) and drawn out to full by Tk."""
        import threading
        import chatfx
        self.making = True
        half = (max(8, w // 2), max(8, (h - self.px(40)) // 2))

        made = []  # filled by the thread, looked for from Tk's own (a thread never calls Tk itself)

        def make():
            try:
                made.append(chatfx.aurora_frames(half[0], half[1], 24, back=self.ui.BG))
            except Exception as exc:
                print(f"  chat: couldn't make the aurora ({exc!r})")
                made.append([])

        def look():
            if made:
                self._have_aurora(made[0])
            else:
                self.app.root.after(100, look)
        threading.Thread(target=make, daemon=True).start()
        self.app.root.after(100, look)

    def _have_aurora(self, frames):
        try:
            self.frames = [tk.PhotoImage(master=self.app.root, data=f, format="ppm").zoom(2) for f in frames]
        except tk.TclError:
            self.frames = []
        self.making = False
        if self.frames and self.up:
            self.canvas.itemconfigure(self.aurora_item, image=self.frames[0])
            self._aurora()

    def _aurora(self):
        """The aurora's next frame, about 14 a second, while the greeting is up on the chat's tab."""
        if self.job is not None:
            self.app.root.after_cancel(self.job)
            self.job = None
        if not (self.up and self.frames):
            return
        if not animations_on() or getattr(self.app, "current_tab", "home") != "home":
            self.canvas.itemconfigure(self.aurora_item, image=self.frames[0])
            self.job = self.app.root.after(800, self._aurora)  # still, and looked at again in a moment
            return
        self.at = (self.at + 1) % len(self.frames)
        self.canvas.itemconfigure(self.aurora_item, image=self.frames[self.at])
        self.job = self.app.root.after(70, self._aurora)

    def _come_in(self):
        """The greeting and question up 12 px with a spring, then the suggestions, 60 ms apart, 16 px each."""
        if not animations_on():
            return
        c = self.canvas
        moved = {"lift": [0.0]}
        tags = ["lift"] + [tag for chips in self.chip_rows for tag, _ in chips]
        for n, tag in enumerate(tags):
            dist = self.px(12) if tag == "lift" else self.px(16)
            moved[tag] = [dist]
            c.move(tag, 0, dist)

            def step(t, tag=tag, dist=dist):
                left = dist * (1 - spring(t))
                c.move(tag, 0, left - moved[tag][0])
                moved[tag][0] = left
            self.app.root.after(n * 60, lambda tag=tag, step=step: self.app.animate(f"hero {tag}", 420, step))


class Panel:
    """A card stack's common parts: a canvas per card, drawn whole each time what it shows changes, coming in with a
    spring from a little to the side; and the app it lives in."""

    def __init__(self, app, parent, ui):
        self.app, self.ui, self.px = app, ui, app.px
        self.frame = tk.Frame(parent, bg=ui.BG)
        self.cards = {}  # key: its canvas

    def _canvas(self, key, w, h, parent=None, lead=0, fill="#ffffff", line="#f2f2f2"):
        c = self.cards.get(key)
        fresh = c is None
        if fresh:
            c = self.cards[key] = tk.Canvas(parent or self.frame, bg=self.ui.BG, highlightthickness=0, bd=0)
        else:  # drawn again mid-spring: the spring stops, or it would go on moving what's drawn now
            self.app.animate(f"card {id(c)}", 1, lambda t: None)
        c.delete("all")
        c.configure(width=w, height=h)
        look = (w, h, lead, fill, line, self.ui.BG)
        photos = self.__dict__.setdefault("photos", {})
        if look not in photos:
            photos[look] = tk.PhotoImage(master=self.app.root, format="ppm", data=card_ppm(
                w, h, self.px, back=self.ui.BG, lead=lead, fill=fill, line=line))
            if len(photos) > 24:
                photos.pop(next(iter(photos)))
        c.photo = photos[look]
        c.create_image(0, 0, anchor="nw", image=c.photo, tags="back")
        return c, fresh

    def _come_in(self, c, dx=0, dy=0):
        """A new card in from dx, dy px off, settling as a damped spring does (spring); just there with Windows'
        animations off."""
        came = self.__dict__.setdefault("came_in", set())
        key = next((k for k, v in self.cards.items() if v is c), None)
        if not animations_on() or key in came:
            return
        came.add(key)
        moved = [0.0, 0.0]

        def step(t):
            k = 1 - spring(t)
            x, y = dx * k, dy * k
            c.move("all", x - moved[0], y - moved[1])
            moved[:] = [x, y]
        step(0.0)
        self.app.animate(f"card {id(c)}", 420, step)

    def _button(self, c, x, y, text, tag, fill, ink, command, anchor="w", back="#ffffff", small=False):
        """A rounded pill button on a card: its words, its colour, what a click does. Its right edge (its left one,
        anchored at its right)."""
        app, px = self.app, self.px
        font = (app.f_small[0], round(app.f_small[1] * 0.9)) if small else app.f_badge
        w, h = app._measure(font, text) + (px(16) if small else px(22)), px(20) if small else px(28)
        x0 = x if anchor == "w" else x - w
        photo = app.smooth(w, h, h / 2, fill, back)
        c.create_image(x0, y, anchor="w", image=photo, tags=tag)
        c.create_text(x0 + w / 2, y, text=text, font=font, fill=ink, tags=tag)
        c.tag_bind(tag, "<Button-1>", lambda e: command())
        c.tag_bind(tag, "<Enter>", lambda e: c.configure(cursor="hand2"))
        c.tag_bind(tag, "<Leave>", lambda e: c.configure(cursor=""))
        c.keep = getattr(c, "keep", []) + [photo]
        return x0 + w

    def _small_w(self, text):
        """How wide a small button with text is (_button, small)."""
        app = self.app
        return app._measure((app.f_small[0], round(app.f_small[1] * 0.9)), text) + self.px(16)

    def _icon(self, c, x, y, mark, tag, command, colour=None):
        ui = self.ui
        item = c.create_text(x, y, text=mark, font=self.app.f_icon_small, fill=colour or ui.FAINT, tags=tag)
        c.tag_bind(tag, "<Button-1>", lambda e: command())
        c.tag_bind(tag, "<Enter>", lambda e: (c.configure(cursor="hand2"), c.itemconfigure(item, fill=ui.TEXT)))
        c.tag_bind(tag, "<Leave>", lambda e: (c.configure(cursor=""), c.itemconfigure(item, fill=colour or ui.FAINT)))
        return item


class Dock(Panel):
    """The deliverables rail, 280 px down the chat's right (22 November 2026, the owner: "whenever the AI creates a
    document, summary, or email draft, animate a compact artifact card into this right rail"): what she made or is
    holding for you, each a white card with its mark, its name and a cross, and a small picture of what's in it: the
    message waiting for your yes, as its recipient and words with Send and Don't; a task held for your yes; the notes
    she saved today, as small dark pages; your timers. A pin at its top keeps it open with nothing in it; the pencil
    starts a new chat."""
    WIDE = 250  # Hedwig's rail cards are small: a thumbnail of each thing made
    NOTES_FOR = 24 * 3600  # notes saved this long ago or less are in it

    def __init__(self, app, parent, ui, page):
        super().__init__(app, parent, ui)
        self.page, px = page, app.px
        self.frame.configure(width=px(self.WIDE))
        self.pinned = bool(ui.settings.get("dock_pinned"))
        self.gone = set()  # crossed out: not shown again this run
        self.shown = []  # the keys drawn, in order
        # no heading: Hedwig's rail is its cards alone, at the top right (the pencil is the top's own now)
        self.body = tk.Frame(self.frame, bg=ui.BG)
        self.body.pack(fill="both", expand=True)

    def items(self, held_task, pending, notes, timers):
        """What's in it now, newest kind first: (key, kind, what it shows)."""
        out = []
        if pending:
            out.append((f"draft {pending['id']}", "draft", pending))
        if held_task:
            out.append((f"task {held_task['id']}", "task", held_task))
        out += [(f"note {path}", "note", {"path": path, "words": words}) for path, words in notes]
        # (your timers were a card here too till the same evening: the sidebar shows them on every tab, so here they
        # were the same thing twice)
        return [i for i in out if i[0] not in self.gone]

    def show(self, items):
        """items drawn as cards, the new ones coming in; True if there's any."""
        keys = [k for k, _, _ in items]
        for key in list(self.cards):
            if key not in keys:
                self.cards.pop(key).destroy()
        width = self.px(self.WIDE)
        for key, kind, what in items:
            sign = repr(sorted(what.items())) if isinstance(what, dict) else repr(what)
            c = self.cards.get(key)
            if c is not None and getattr(c, "sign", None) == sign:
                continue
            draw = {"draft": self._draft, "task": self._task, "note": self._note, "timers": self._timers}[kind]
            c, fresh = draw(key, width, what)
            c.sign = sign
            if fresh:
                self._come_in(c, dx=self.px(24))
        for key in keys:  # in their order
            self.cards[key].pack_forget()
        for key in keys:
            self.cards[key].pack(fill="x", pady=(0, self.px(4)), in_=self.body)
        self.shown = keys
        return bool(keys)

    def _top(self, c, w, mark, title, key, colour=None):
        """A card's top, white: its mark in its colour and its name in bold at the left, a small cross at the right."""
        app, px, ui = self.app, self.px, self.ui
        c.create_text(px(20), px(20), text=mark, font=app.f_icon_small, fill=colour or ui.ACCENT)
        c.create_text(px(34), px(20), anchor="w", font=app.f_badge, fill=ui.TEXT,
                      text=app._fit(title, app.f_badge, w - px(76)))
        self._icon(c, w - px(22), px(20), "\ue711", "cross", lambda: self.cross(key))

    def _dark(self, c, w, top, h):
        """The card's small dark picture of what's in it, set in under its top: its corners its own less the inset,
        so the two curves run together (better-ui: concentric radii)."""
        px = self.px
        c.dark = self.app.smooth(w - px(24), h, px(5), "#1f1f1f", "#ffffff")
        c.create_image(px(12), top, anchor="nw", image=c.dark)
        return px(12), top

    def cross(self, key):
        self.gone.add(key)
        self.page.keep(force=True)

    def _draft(self, key, w, what):
        """The message waiting for your yes: Outbox, with a dark strip of whom it's to, its words, Send and Don't."""
        app, px, ui = self.app, self.px, self.ui
        tiny = (app.f_small[0], round(app.f_small[1] * 0.9))
        c, fresh = self._canvas(key, w, px(132))
        self._top(c, w, "\ue724", "Outbox", key)
        x0, y0 = self._dark(c, w, px(34), px(86))
        to = str(what.get("contact") or "them")
        c.create_text(x0 + px(10), y0 + px(14), anchor="w", text=app._fit(to, app.f_badge, px(120)), font=app.f_badge,
                      fill="#ffffff")
        where = (what.get("app") or "").capitalize()
        if where:
            chip_x = x0 + px(16) + app._measure(app.f_badge, app._fit(to, app.f_badge, px(120)))
            c.chip = app.smooth(app._measure(tiny, where) + px(10), px(15), px(4), "#3a3a3a", "#1f1f1f")
            c.create_image(chip_x, y0 + px(14), anchor="w", image=c.chip)
            c.create_text(chip_x + px(5), y0 + px(14), anchor="w", text=where, font=tiny, fill="#c7c7c7")
        c.create_text(x0 + px(10), y0 + px(34), anchor="w", font=tiny, fill="#a3a3a3",
                      text=app._fit(" ".join(str(what.get("text") or "").split()), tiny, w - px(48)))
        right = w - px(22)
        self._button(c, right, y0 + px(66), "Don't", "dont", "#3a3a3a", "#e5e5e5",
                     lambda: app.controls.put(("chat", "no")), anchor="e", back="#1f1f1f", small=True)
        self._button(c, right - self._small_w("Don't") - px(6), y0 + px(66), "Send", "send", ui.ACCENT, "#ffffff",
                     lambda: app.controls.put(("chat", "yes")), anchor="e", back="#1f1f1f", small=True)
        return c, fresh

    def _task(self, key, w, what):
        app, px, ui = self.app, self.px, self.ui
        tiny = (app.f_small[0], round(app.f_small[1] * 0.9))
        c, fresh = self._canvas(key, w, px(118))
        self._top(c, w, "\ue8fb", "Waiting for your yes", key, colour="#d9902f")
        x0, y0 = self._dark(c, w, px(34), px(72))
        c.create_text(x0 + px(10), y0 + px(10), anchor="nw", width=w - px(48), font=tiny, fill="#d4d4d4",
                      text=app._fit(" ".join(str(what.get("description") or "").split()), tiny, (w - px(52)) * 2))
        right = w - px(22)
        self._button(c, right, y0 + px(56), "Cancel", "cancel", "#3a3a3a", "#e5e5e5",
                     lambda: self.page.decide("cancel"), anchor="e", back="#1f1f1f", small=True)
        self._button(c, right - self._small_w("Cancel") - px(6), y0 + px(56), "Approve", "approve", ui.ACCENT,
                     "#ffffff", lambda: self.page.decide("approve"), anchor="e", back="#1f1f1f", small=True)
        return c, fresh

    def _note(self, key, w, what):
        """A note she saved: its name on the white top, and its first lines as a small dark page under it, which
        opens it, as Hedwig's prep doc is."""
        app, px, ui = self.app, self.px, self.ui
        tiny = (app.f_small[0], round(app.f_small[1] * 0.85))
        tiny_bold = (app.f_bold[0], round(app.f_small[1] * 0.85))
        path = what["path"]
        name = os.path.splitext(os.path.basename(path))[0].replace("-", " ").replace("_", " ")
        lines = [ln.strip("#*- ").strip() for ln in what["words"].splitlines() if ln.strip()][:6]
        if lines and lines[0].lower() == name.lower():
            lines = lines[1:]
        c, fresh = self._canvas(key, w, px(40) + px(16) * max(2, len(lines)) + px(28))
        self._top(c, w, "\ue8a5", name[:1].upper() + name[1:], key, colour="#7c5cf2")
        x0, y0 = self._dark(c, w, px(34), px(16) * max(2, len(lines)) + px(14))
        y = y0 + px(10)
        for n, line in enumerate(lines):
            c.create_text(x0 + px(10), y, anchor="nw", text=app._fit(line, tiny, w - px(56)), tags="open",
                          font=tiny_bold if n == 0 else tiny, fill="#f5f5f5" if n == 0 else "#a3a3a3")
            y += px(16)
        c.tag_bind("open", "<Button-1>", lambda e: os.startfile(path))
        c.tag_bind("open", "<Enter>", lambda e: c.configure(cursor="hand2"))
        c.tag_bind("open", "<Leave>", lambda e: c.configure(cursor=""))
        return c, fresh

    def _timers(self, key, w, what):
        app, px, ui = self.app, self.px, self.ui
        timers = what["timers"]
        c, fresh = self._canvas(key, w, px(44) + px(24) * len(timers) + px(8))
        self._top(c, w, "\ue916", "Timers", key)
        for n, (label, left) in enumerate(timers):
            y = px(50) + n * px(24)
            c.create_text(px(20), y, anchor="w", text=app._fit(label or "Timer", app.f_small, w - px(110)),
                          font=app.f_small, fill=ui.TEXT)
            c.create_text(w - px(22), y, anchor="e", text=left, font=app.f_mono, fill=ui.ACCENT)
        return c, fresh


class Bento(Panel):
    """The context canvas (22 November 2026, the owner: "a split-screen AI workspace with a bento context canvas ...
    miniature app window cards that open automatically when the AI retrieves context"): what each look-up of her turn
    found (siri.show_context), each a small window with its app's name at the top left and expand and close at the top
    right, showing only the slice that matters: the day's meetings for the calendar, a page's title and its words for
    the web. The first is wide across the top, the rest two by two under it. A new turn's start clears the last one's;
    with none left it closes and the rail is back."""
    MOST = 5
    TOP, ROW, BIG = 236, 214, 520  # the wide frame's height, each row's under it, and one expanded

    def height(self):
        """How tall the frames are together: the wide one, then a row for each two after it, or one expanded."""
        px = self.px
        shown = [f for f in self.found if self.big in (None, f[0])]
        if self.big or len(shown) <= 1:
            return px(self.BIG) if self.big else px(self.TOP)
        return px(self.TOP) + ((len(shown) - 1 + 1) // 2) * (px(self.ROW) + px(2)) + px(2)

    def __init__(self, app, parent, ui, page):
        super().__init__(app, parent, ui)
        self.page, px = page, app.px
        self.found, self.big = [], None  # (key, app name, mark, label, lines), newest last; the one expanded
        self.turn = 0  # the turn the cards are from (Page counts its turns)
        self._make_grid()

    def _make_grid(self):
        self.grid = tk.Frame(self.frame, bg=self.ui.BG)
        self.grid.pack(fill="both", expand=True)
        self.grid.grid_columnconfigure(0, weight=1, uniform="half")
        self.grid.grid_columnconfigure(1, weight=1, uniform="half")

    def rebuild(self, parent, width, height):
        """The frames made again in parent (the thread, which destroys the windows set in it whenever it's drawn
        again), width by height: a new frame and its cards, their pictures from what's kept."""
        try:
            self.frame.destroy()
        except tk.TclError:
            pass
        self.frame = tk.Frame(parent, bg=self.ui.BG, width=width, height=height)
        self.frame.grid_propagate(False)
        self.frame.pack_propagate(False)
        self.cards = {}
        self._make_grid()
        self.draw()
        return self.frame

    def add(self, detail, turn):
        """One look-up's findings (the "Context" event's JSON) as a card. True if one came."""
        try:
            got = json.loads(detail)
        except (TypeError, ValueError):
            return False
        label, do = str(got.get("label") or ""), str(got.get("do") or "")
        name, mark = app_of(label, do)
        found = got.get("found")
        if do == "read" and isinstance(found, dict):  # a page: named for the app it is, by its address
            page = found.get("page") if isinstance(found.get("page"), dict) else {}
            app_name = site_app(page.get("url") or found.get("read"))
            known = any(app_name == n for _, n in DOMAIN_APPS)
            name = app_name if known else (str(page.get("site") or "").strip() or app_name or name)
        lines = context_lines(got.get("found"))
        if name == "Calendar":
            lines = self._agenda() or lines
        if not lines:
            return False
        if turn != self.turn:  # a new turn: the last one's cards go
            self.found, self.big, self.turn = [], None, turn
        self.found.append((f"{turn}:{len(self.found)}", name, mark, label, lines, do, got.get("found")))
        del self.found[:-self.MOST]
        return True

    def add_picture(self, rgb, title, turn):
        """What she saw on the screen (vision.LAST: the picture taken for her answer) as a frame, the app as it really
        looks, named for its window. True if one came."""
        if rgb is None:
            return False
        if turn != self.turn:
            self.found, self.big, self.turn = [], None, turn
        name = window_app(title)
        self.found = [f for f in self.found if f[5] != "picture"]  # one look at the screen: the latest
        self.found.append((f"{turn}:{len(self.found)}:pic", name, "\ue7f4", str(title or ""), [], "picture", rgb))
        del self.found[:-self.MOST]
        return True

    def _agenda(self):
        """The day's meetings, for the calendar's card: "2:00 PM  Website review", from this PC's calendars."""
        import datetime as dt
        try:
            import agenda
            now = dt.datetime.now()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            events = agenda.kept(start, start + dt.timedelta(days=1))
        except Exception:
            return []
        return [("All day" if e.get("all_day") else e["start"].strftime("%I:%M %p").lstrip("0")) + "   " +
                e.get("title", "") + (f"  \u00b7  {e['where']}" if e.get("where") and len(e["where"]) < 40 else "")
                for e in events][:8]

    def clear(self):
        self.found, self.big = [], None
        self.page._lay_frames()
        self.page.changed()

    def close(self, key):
        self.found = [f for f in self.found if f[0] != key]
        self.big = None if self.big == key else self.big
        self.page._lay_frames()
        self.page.changed()

    def expand(self, key):
        self.big = None if self.big == key else key
        self.page.changed()

    def draw(self):
        px = self.px
        keys = [f[0] for f in self.found]
        for key in list(self.cards):
            if key not in keys:
                self.cards.pop(key).destroy()
        width = max(px(300), int(self.frame.cget("width") or px(700)))  # the thread's width (Page._put_frames)
        # what she saw on the screen first, wide across the top as Hedwig's design frame is; the rest two by two
        shown = sorted((f for f in self.found if self.big in (None, f[0])), key=lambda f: f[5] != "picture")
        top_h, row_h = self.TOP, self.ROW
        for n, (key, name, mark, label, lines, do, found) in enumerate(shown):
            wide = n == 0 or self.big is not None
            w = width if wide else (width - px(4)) // 2
            h = px(self.BIG) if self.big else px(top_h) if wide else px(row_h)
            sign = (w, h, self.big == key, tuple(lines), self.page.answer_words() if do == "read" else ())
            c = self.cards.get(key)
            if c is None or getattr(c, "sign", None) != sign:
                c, fresh = self._canvas(key, w, h, self.grid, lead=px(26))
                c.sign = sign
                self._window(c, w, h, key, name, mark, label, lines, do, found)
                if fresh:
                    self._come_in(c, dy=px(10))
            c.grid_forget()
        row, col = 0, 0
        for n, (key, *_rest) in enumerate(shown):
            c = self.cards[key]
            if n == 0 or self.big is not None:
                c.grid(row=0, column=0, columnspan=2, sticky="nw", pady=(0, px(2)))
                row, col = 1, 0
            else:
                c.grid(row=row, column=col, sticky="nw", pady=(0, px(2)))
                row, col = (row, 1) if col == 0 else (row + 1, 0)
        for key, *_rest in self.found:
            if key not in [s[0] for s in shown]:
                self.cards[key].grid_forget()

    # ------------------------------------------------------------------ each app as itself
    def _window(self, c, w, h, key, name, mark, label, lines, do="", found=None):
        """A small app window: its name at the top left, expand and close at its right, and under them what was found
        drawn as the app it came from would show it (the owner: "authentic app-native UI views inside each card"): a
        search as a results page, a page read as a page in a browser, the weather as the weather, the calendar as a
        day; mail and a checklist when what came back is shaped as one. Anything else as its lines."""
        app, px, ui = self.app, self.px, self.ui
        m = px(7)
        # over the card, on the canvas, as Hedwig's frames have it: the app's name at the left, expand and close at
        # the right. No bar inside the card and no line under one: the card is the app's own view (oil-ui's
        # subtraction: a box inside a box, and a line where space already parts them, both go)
        theme = theme_of(found)
        dot = TINTS.get(name, TINTS.get({"Google Calendar": "Calendar"}.get(name, ""), (None, theme or "#9ca3af")))[1]
        c.create_oval(m + px(2), px(9), m + px(8), px(15), fill=dot, width=0)
        c.create_text(m + px(14), px(12), anchor="w", text=name, font=app.f_badge, fill=ui.MUTED)
        self._icon(c, w - m - px(30), px(12), "\ue740" if self.big != key else "\ue73f", "expand",
                   lambda: self.expand(key))
        self._icon(c, w - m - px(8), px(12), "\ue711", "close", lambda: self.close(key))
        box = (m + px(16), px(26) + px(16), w - m - px(16), h - px(22))  # where the app's own view goes
        found = found if found is not None else {}
        view = self._view_of(do, name, found, lines)
        try:
            getattr(self, f"_draw_{view}")(c, box, label, lines, found)
        except Exception as exc:  # what came back wasn't the shape it looked: as lines, never a broken card
            print(f"  chat: couldn't draw the {view} card ({exc!r})")
            c.delete("view")
            self._draw_lines(c, box, label, lines, found)

    @staticmethod
    def _view_of(do, name, found, lines):
        """Which app's view a card is drawn as."""
        if do == "picture":
            return "picture"
        inner = found.get("results") if isinstance(found, dict) else None
        if do == "read" and name == "Gmail":
            return "mail"
        if do == "read" and name == "Notion":
            return "notion"
        if isinstance(found, dict) and (found.get("from") or found.get("sender")) and \
                (found.get("subject") or found.get("body")):
            return "mail"
        if sum(bool(re.match(r"\s*(?:[-*]\s*)?\[[ xX]\]", line)) for line in lines) >= 2:
            return "checklist"
        if do == "web" and isinstance(inner, dict):
            return "search"
        if do == "read" and isinstance(found, dict) and isinstance(found.get("page"), dict):
            return "page"
        if do == "weather" and isinstance(found, dict) and isinstance(found.get("result"), dict):
            return "weather"
        if do == "news" and isinstance(found, dict) and isinstance(found.get("headlines"), list):
            return "news"
        if name == "Calendar":
            return "day"
        return "lines"

    def _text(self, c, x, y, text, font, fill, width, bottom):
        """Words on the card, wrapped to width, or left out if they'd run past bottom. Their foot, or None."""
        item = c.create_text(x, y, anchor="nw", text=text, font=font, fill=fill, width=width, tags="view")
        if c.bbox(item)[3] > bottom:
            c.delete(item)
            return None
        return c.bbox(item)[3]

    def _draw_lines(self, c, box, label, lines, found):
        app, px, ui = self.app, self.px, self.ui
        x0, y, x1, bottom = box
        title = label.partition(": ")[2].strip()
        if title:
            y = (self._text(c, x0, y, title, app.f_bold, ui.TEXT, x1 - x0, bottom) or y) + px(8)
        for line in lines:
            foot = self._text(c, x0, y, line, app.f_small, ui.MUTED, x1 - x0, bottom)
            if foot is None:
                break
            y = foot + px(6)

    def _draw_search(self, c, box, label, lines, found):
        """A results page as Google lays one out (the owner: "their original theme"): the search in a white rounded
        bar with a hairline, the short answer if there is one, then each result as its site on a small disc, its
        name and where it's from in grey, and its title in Google's link blue."""
        app, px, ui = self.app, self.px, self.ui
        x0, y, x1, bottom = box
        results = found.get("results") or {}
        c.bar = framed(app, x1 - x0, px(30), px(15), "#ffffff", "#dfe1e5", "#ffffff")
        c.create_image(x0, y, anchor="nw", image=c.bar, tags="view")
        c.create_text(x0 + px(14), y + px(15), text="\ue721", font=app.f_icon_small, fill="#9aa0a6", tags="view")
        c.create_text(x0 + px(32), y + px(15), anchor="w", tags="view", font=app.f_small, fill="#202124",
                      text=app._fit(str(found.get("web") or label.partition(": ")[2]), app.f_small, x1 - x0 - px(44)))
        y += px(42)
        answer = results.get("answer")
        if isinstance(answer, str) and answer.strip():
            y = (self._text(c, x0, y, answer.strip()[:280], app.f_bold, "#202124", x1 - x0, bottom) or y) + px(12)
        wiki = results.get("wikipedia")
        rows = []
        if isinstance(wiki, dict) and (wiki.get("title") or wiki.get("extract")):
            rows.append(("Wikipedia", "wikipedia.org", wiki.get("title") or "", wiki.get("extract") or ""))
        for story in results.get("news") or []:
            if isinstance(story, dict):
                rows.append((story.get("source") or "News", story.get("when") or "", story.get("title") or "", ""))
        c.disc = []
        for source, where, title, more in rows:
            if y + px(40) > bottom:
                break
            c.disc.append(app.smooth(px(22), px(22), px(11), "#f1f3f4", "#ffffff"))
            c.create_image(x0, y, anchor="nw", image=c.disc[-1], tags="view")
            c.create_text(x0 + px(11), y + px(11), text=str(source)[:1].upper(), font=app.f_badge, fill="#5f6368",
                          tags="view")
            c.create_text(x0 + px(30), y + px(2), anchor="nw", font=app.f_small, fill="#202124", tags="view",
                          text=app._fit(str(source), app.f_small, x1 - x0 - px(30)))
            if where:
                c.create_text(x0 + px(30), y + px(16), anchor="nw", font=(app.f_small[0], round(app.f_small[1] * 0.9)),
                              fill="#4d5156", text=app._fit(str(where), app.f_small, x1 - x0 - px(30)), tags="view")
            foot = self._text(c, x0, y + px(32), str(title), (app.f_body[0], round(app.f_body[1] * 1.08)), "#1a0dab",
                              x1 - x0, bottom)
            if foot is None:
                break
            y = foot + px(4)
            if more:
                y = (self._text(c, x0, y, str(more)[:200], app.f_small, "#4d5156", x1 - x0, bottom) or y)
            y += px(12)

    def _draw_picture(self, c, box, label, lines, found):
        """What she saw: the window as it really looks, its own colours and type, cut to the frame from its top (the
        slice that matters is usually there), nothing redrawn."""
        import vision
        app, px = self.app, self.px
        x0, y0, x1, bottom = box
        x0, y0, x1 = x0 - px(16), y0 - px(16), x1 + px(16)  # edge to edge in the card, as a screenshot is
        w, h = int(x1 - x0), int(bottom + px(10) - y0)
        look = (id(found), w, h)
        pics = self.__dict__.setdefault("pics", {})
        if look not in pics:
            small = vision.shrink(found, max(8, w - 2))[:max(8, h - 2)]
            pics.clear()  # only the latest look at the screen is kept
            pics[look] = tk.PhotoImage(master=app.root, format="png", data=base64.b64encode(vision.png(small)))
        c.pic = pics[look]
        c.create_image(x0 + 1, y0 + 1, anchor="nw", image=c.pic, tags="view")

    def _draw_page(self, c, box, label, lines, found):
        """A page read, as a browser shows it: its address in a rounded bar with a lock, its title big, its words."""
        app, px, ui = self.app, self.px, self.ui
        x0, y, x1, bottom = box
        page = found.get("page") or {}
        url = str(page.get("url") or found.get("read") or "")
        host = re.sub(r"^https?://(?:www\.)?", "", url).split("/")[0]
        theme = theme_of(found)
        c.bar = app.smooth(x1 - x0, px(28), px(14), "#f1f3f4", "#ffffff")
        c.create_image(x0, y, anchor="nw", image=c.bar, tags="view")
        c.create_text(x0 + px(14), y + px(14), text="\ue72e", font=app.f_icon_small, fill=ui.MUTED, tags="view")
        c.create_text(x0 + px(30), y + px(14), anchor="w", text=app._fit(host or url, app.f_small, x1 - x0 - px(40)),
                      font=app.f_small, fill=ui.TEXT, tags="view")
        y += px(38)
        site = str(page.get("site") or "")
        if theme or site:  # the site's own band, its colour washed pale, its name in its colour: any site as itself
            ink = ui.mix(theme, "#000000", 0.25) if theme else ui.MUTED
            band = ui.mix(theme, "#ffffff", 0.88) if theme else "#f4f4f5"
            c.create_rectangle(x0 - px(16) + 1, y, x1 + px(16) - 1, y + px(26), fill=band, width=0, tags="view")
            c.create_text(x0, y + px(13), anchor="w", text=site or host, font=app.f_badge, fill=ink, tags="view")
            y += px(36)
        else:
            y += px(4)
        title = str(page.get("title") or "")
        if title:
            y = (self._text(c, x0, y, title, app.f_h2, ui.TEXT, x1 - x0, bottom) or y) + px(10)
        for para in [p.strip() for p in str(page.get("text") or "").split("\n") if p.strip()][:10]:
            box = re.match(r"(?:[-*]\s*)?\[([ xX])\]\s*(.*)", para)
            if box:  # a to-do on the page: its box, ticked or not, as a notes page draws it
                if y + px(20) > bottom:
                    break
                done = box[1].lower() == "x"
                c.create_rectangle(x0, y + px(3), x0 + px(13), y + px(16), outline=ui.ACCENT if done else "#c4c7cc",
                                   fill=ui.ACCENT if done else "#ffffff", width=1, tags="view")
                if done:
                    c.create_text(x0 + px(6.5), y + px(9.5), text="\ue73e", font=app.f_fold, fill="#ffffff",
                                  tags="view")
                foot = self._text(c, x0 + px(22), y + px(1), box[2][:200], app.f_small,
                                  ui.MUTED if done else "#374151", x1 - x0 - px(22), bottom)
            else:
                foot = self._text(c, x0, y, para[:320], app.f_small, "#374151", x1 - x0, bottom)
            if foot is None:
                break
            y = foot + px(8)

    def _draw_weather(self, c, box, label, lines, found):
        """The weather as a weather app shows it: the temperature big, the sky and the place by it, the days under."""
        app, px, ui = self.app, self.px, self.ui
        x0, y, x1, bottom = box
        got = found.get("result") or {}
        now = got.get("now") or {}
        temp = now.get("temp_c")
        c.create_text(x0, y, anchor="nw", text=f"{temp}\u00b0" if temp is not None else "\u2014", tags="view",
                      font=(app.f_value[0], int(app.f_value[1] * 1.4)), fill=ui.TEXT)
        c.create_text(x0 + px(110), y + px(8), anchor="nw", tags="view", font=app.f_bold, fill=ui.TEXT,
                      text=str(now.get("sky") or (got.get("days") or [{}])[0].get("sky") or "").capitalize())
        c.create_text(x0 + px(110), y + px(30), anchor="nw", text=str(got.get("place") or found.get("weather") or ""),
                      font=app.f_small, fill=ui.MUTED, tags="view")
        y += px(76)
        days = [d for d in got.get("days") or [] if isinstance(d, dict)][:3]
        col = (x1 - x0) / max(1, len(days))
        for i, d in enumerate(days):
            if y + px(40) > bottom:
                break
            x = x0 + i * col
            c.create_text(x, y, anchor="nw", text=str(d.get("day") or "").capitalize(), font=app.f_small,
                          fill=ui.MUTED, tags="view")
            hi, lo = d.get("high", d.get("max_c")), d.get("low", d.get("min_c"))
            c.create_text(x, y + px(20), anchor="nw", tags="view", font=app.f_bold, fill=ui.TEXT,
                          text=(f"{hi}\u00b0" if hi is not None else "") + (f" / {lo}\u00b0" if lo is not None else ""))

    def _draw_news(self, c, box, label, lines, found):
        self._draw_search(c, box, label, lines, {"web": found.get("news"), "results": {"news": found.get("headlines")}})

    def _draw_day(self, c, box, label, lines, found):
        """The calendar as a day: the hours down the left, each meeting a soft blue block at its time."""
        import datetime as dt
        app, px, ui = self.app, self.px, self.ui
        x0, y0, x1, bottom = box
        try:
            import agenda
            now = dt.datetime.now()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            events = [e for e in agenda.kept(start, start + dt.timedelta(days=1)) if not e.get("all_day")]
        except Exception:
            events = []
        if not events:
            return self._draw_lines(c, box, label, lines, found)
        first = min(e["start"].hour for e in events)
        first = max(0, min(first, now.hour) - 1)
        hour_h = px(34)
        hours = max(1, int((bottom - y0) // hour_h))
        for i in range(hours):
            y = y0 + i * hour_h
            label_at = (dt.datetime(2000, 1, 1, (first + i) % 24)).strftime("%I %p").lstrip("0")
            c.create_text(x0, y, anchor="nw", text=label_at, font=(app.f_small[0], round(app.f_small[1] * 0.9)),
                          fill="#70757a", tags="view")
            c.create_line(x0 + px(46), y + px(7), x1, y + px(7), fill="#dadce0", tags="view")
        c.blocks = []
        for e in events:
            top = y0 + px(7) + ((e["start"].hour - first) + e["start"].minute / 60) * hour_h
            end = e.get("end") or e["start"] + dt.timedelta(minutes=30)
            tall = max(px(26), (end - e["start"]).total_seconds() / 3600 * hour_h - px(2))
            if top > bottom or top + px(10) < y0:
                continue
            tall = min(tall, bottom - top)
            # Google Calendar's own: a block of its blue with the words in white (the owner: "their original theme")
            c.blocks.append(app.smooth(x1 - x0 - px(52), tall, px(5), "#039be5", "#ffffff"))
            c.create_image(x0 + px(52), top, anchor="nw", image=c.blocks[-1], tags="view")
            c.create_text(x0 + px(60), top + px(5), anchor="nw", font=app.f_badge, fill="#ffffff", tags="view",
                          text=app._fit(e.get("title") or "", app.f_badge, x1 - x0 - px(68)))
            if tall > px(36):
                c.create_text(x0 + px(60), top + px(22), anchor="nw", font=app.f_small, fill="#e1f5fe", tags="view",
                              text=e["start"].strftime("%I:%M %p").lstrip("0") + " \u2013 " +
                              end.strftime("%I:%M %p").lstrip("0"))
        if first <= now.hour < first + hours:  # now, as a thin red line across the day
            y = y0 + px(7) + ((now.hour - first) + now.minute / 60) * hour_h
            c.create_line(x0 + px(46), y, x1, y, fill="#ea4335", width=max(1, px(1.4)), tags="view")
            c.create_oval(x0 + px(42), y - px(4), x0 + px(50), y + px(4), fill="#ea4335", width=0, tags="view")

    def _gmail_mark(self, c, x, y, size):
        """Gmail's M, its four colours, drawn: blue and green posts, the red V between them, a touch of yellow."""
        def poly(points, colour):
            c.create_polygon([v for px_, py_ in points for v in (x + px_ * size, y + py_ * size * 0.75)],
                             fill=colour, outline="", tags="view")
        poly([(0, 0.1), (0.22, 0.28), (0.22, 1), (0.08, 1), (0, 0.92)], "#4285f4")
        poly([(1, 0.1), (0.78, 0.28), (0.78, 1), (0.92, 1), (1, 0.92)], "#34a853")
        poly([(0, 0.1), (0.5, 0.5), (1, 0.1), (1, 0.36), (0.5, 0.76), (0, 0.36)], "#ea4335")
        poly([(0.78, 0.28), (1, 0.1), (1, 0.36), (0.78, 0.53)], "#fbbc04")

    def _draw_mail(self, c, box, label, lines, found):
        """Mail, as Gmail shows one message (the owner's own reference): Gmail's bar along the top, its M and its
        name and "Search mail" in its pale blue pill; then the subject, the sender's initials on a coloured disc,
        their name and address, "to me", the time at the right, and the message."""
        app, px, ui = self.app, self.px, self.ui
        x0, y, x1, bottom = box
        if isinstance(found, dict) and isinstance(found.get("page"), dict):  # a Gmail page read: its words
            page = found["page"]
            found = {"subject": page.get("title") or "", "body": page.get("text") or ""}
        # Gmail's own bar, the full width of the frame, its pale grey-blue
        bar_x0, bar_x1 = x0 - px(16), x1 + px(16)
        c.create_rectangle(bar_x0 + 1, y - px(16) + 1, bar_x1 - 1, y + px(30), fill="#f6f8fc", width=0, tags="view")
        self._gmail_mark(c, x0, y + px(2), px(18))
        c.create_text(x0 + px(24), y + px(8), anchor="w", text="Gmail", font=(app.f_body[0], round(app.f_body[1] * 1.15)),
                      fill="#5f6368", tags="view")
        pill_x = x0 + px(84)
        c.pill = app.smooth(max(px(60), x1 - pill_x), px(26), px(13), "#eaf1fb", "#f6f8fc")
        c.create_image(pill_x, y + px(8), anchor="w", image=c.pill, tags="view")
        c.create_text(pill_x + px(14), y + px(8), anchor="w", text="Search mail", font=app.f_small, fill="#5f6368",
                      tags="view")
        y += px(44)
        sender = str(found.get("from") or found.get("sender") or "")
        name, _, address = sender.partition("<")
        name, address = name.strip(), address.strip("> ")
        subject = str(found.get("subject") or "")
        if subject:
            y = (self._text(c, x0, y, subject, (app.f_body[0], round(app.f_body[1] * 1.14)), "#1f1f1f", x1 - x0,
                            bottom) or y) + px(12)
        if name or address:
            initials = "".join(w[:1] for w in (name or address).split()[:2]).upper()
            colours = ("#e8508a", "#7b61ff", "#1a73e8", "#e37400", "#188038", "#c5221f")
            c.disc = app.smooth(px(30), px(30), px(15), colours[sum(map(ord, name or address)) % len(colours)],
                                "#ffffff")
            c.create_image(x0, y, anchor="nw", image=c.disc, tags="view")
            c.create_text(x0 + px(15), y + px(15), text=initials or "?", font=app.f_badge, fill="#ffffff", tags="view")
            who = c.create_text(x0 + px(40), y + px(3), anchor="nw", font=app.f_bold, fill="#1f1f1f", tags="view",
                                text=name or address)
            if address and name:
                c.create_text(c.bbox(who)[2] + px(4), y + px(4), anchor="nw", text=f"<{address}>", tags="view",
                              font=(app.f_small[0], round(app.f_small[1] * 0.92)), fill="#5e5e5e")
            c.create_text(x0 + px(40), y + px(20), anchor="nw", text="to me", font=app.f_small, fill="#5e5e5e",
                          tags="view")
            if found.get("when") or found.get("time"):
                c.create_text(x1, y + px(4), anchor="ne", text=str(found.get("when") or found.get("time")),
                              font=app.f_small, fill="#5e5e5e", tags="view")
            y += px(44)
        for para in [p.strip() for p in str(found.get("body") or found.get("text") or "").split("\n") if p.strip()]:
            foot = self._text(c, x0, y, para, app.f_small, "#1f1f1f", x1 - x0, bottom)
            if foot is None:
                break
            y = foot + px(9)

    def _draw_notion(self, c, box, label, lines, found):
        """A page in Notion, as Notion draws one (the owner's own reference): the path to it in small grey, its title
        large and bold, then its words, a heading in bold, each to-do with its box, and the one her answer is about
        marked in Notion's yellow (Page.answer_words): marked from what she said, never made up."""
        app, px = self.app, self.px
        x0, y, x1, bottom = box
        ink, grey = "#37352f", "#9b9a97"
        page = found.get("page") if isinstance(found, dict) and isinstance(found.get("page"), dict) else {}
        url = str(page.get("url") or found.get("read") or "")
        title = str(page.get("title") or "").split(" | ")[0].strip()
        path = [w.replace("-", " ") for w in re.sub(r"^https?://[^/]+/?", "", url).split("?")[0].split("/") if w]
        path = [re.sub(r"\s+[0-9a-f]{32}$", "", w).strip().capitalize() for w in path][-3:]
        if path:
            c.create_text(x0, y, anchor="nw", text=app._fit(" / ".join(path), app.f_small, x1 - x0), tags="view",
                          font=(app.f_small[0], round(app.f_small[1] * 0.92)), fill=grey)
            y += px(24)
        if title:
            y = (self._text(c, x0, y, title, (app.f_bold[0], round(app.f_bold[1] * 1.75)), ink, x1 - x0, bottom)
                 or y) + px(6)
        if page.get("edited"):
            c.create_text(x0, y, anchor="nw", text=f"Last edited {page['edited']}", font=app.f_small, fill=grey,
                          tags="view")
            y += px(22)
        y += px(8)
        said = self.page.answer_words()
        texts = [t.strip() for t in str(page.get("text") or "\n".join(lines)).split("\n") if t.strip()]
        for n, text in enumerate(texts[:14]):
            todo = re.match(r"(?:[-*]\s*)?\[([ xX])\]\s*(.*)", text)
            heading = not todo and n + 1 < len(texts) and len(text) < 48 and \
                re.match(r"(?:[-*]\s*)?\[", texts[n + 1]) is not None
            if y + px(22) > bottom:
                break
            if todo:
                done, words = todo[1].lower() == "x", todo[2]
                about = len(said & set(re.findall(r"[a-z]{4,}", words.lower()))) >= 2
                item = c.create_text(x0 + px(24), y + px(1), anchor="nw", text=words, width=x1 - x0 - px(28),
                                     font=app.f_bold if about else app.f_small, fill=grey if done else ink,
                                     tags="view")
                bb = c.bbox(item)
                if bb[3] > bottom:
                    c.delete(item)
                    break
                c.create_rectangle(x0 + 1, y + px(3), x0 + px(14), y + px(16), outline=ink if not done else "#2383e2",
                                   fill="#2383e2" if done else "#ffffff", width=1, tags="view")
                if done:
                    c.create_text(x0 + px(7.5), y + px(9.5), text="\ue73e", font=app.f_fold, fill="#ffffff", tags="view")
                if about:  # Notion's yellow behind what her answer is about
                    mark = c.create_rectangle(bb[0] - px(2), bb[1], bb[2] + px(2), bb[3], fill="#fbf3db", width=0,
                                              tags="view")
                    c.tag_lower(mark, item)
                y = bb[3] + px(10)
            else:
                foot = self._text(c, x0, y, text, app.f_bold if heading else app.f_small, ink, x1 - x0, bottom)
                if foot is None:
                    break
                y = foot + px(8 if heading else 6)

    def _draw_checklist(self, c, box, label, lines, found):
        """A checklist, as a notes app has one: its title, then each item with its box, ticked or not."""
        app, px, ui = self.app, self.px, self.ui
        x0, y, x1, bottom = box
        title = label.partition(": ")[2].strip() or (lines[0] if not re.match(r"\s*(?:[-*]\s*)?\[", lines[0]) else "")
        if title:
            y = (self._text(c, x0, y, title, app.f_h2, ui.TEXT, x1 - x0, bottom) or y) + px(12)
        for line in lines:
            m = re.match(r"\s*(?:[-*]\s*)?\[([ xX])\]\s*(.*)", line)
            if not m:
                continue
            if y + px(22) > bottom:
                break
            done = m[1].lower() == "x"
            c.create_rectangle(x0, y + px(3), x0 + px(14), y + px(17), outline="#9ca3af" if not done else ui.ACCENT,
                               fill=ui.ACCENT if done else "#ffffff", width=1, tags="view")
            if done:
                c.create_text(x0 + px(7), y + px(10), text="\u2713", font=app.f_small, fill="#ffffff", tags="view")
            foot = self._text(c, x0 + px(24), y + px(1), m[2], app.f_small, ui.MUTED if done else ui.TEXT,
                              x1 - x0 - px(24), bottom)
            if foot is None:
                break
            y = foot + px(10)


class Page:
    """The chat as her window shows it, built in page (assistant_ui._page) with app's fonts and ui's colours and
    parts (ui: the assistant_ui module, which can't be imported from here as it imports this)."""
    # the kept cards' width; the page's under which they go; the thread's most, which keeps her lines near 75
    # letters, the measure better-typography (jakubkrehel/skills, installed 22 November 2026) asks of reading text
    # (WIDE: 640 again, near Hedwig's own column and about 80 letters a line, which is where reading is easy; it was
    # 768 for an evening, after a prompt, and lines ran past a hundred letters)
    RAIL, NARROW, WIDE = 280, 820, 640

    def __init__(self, app, page, ui):
        self.app, self.page, self.ui, px = app, page, ui, app.px
        self.thread, self.bubbles, self.pending, self.width = Thread(), [], False, 0
        self.thread.starting = "starting up"  # till her first word of how she is: Ready, Listening ... (Thread.event)
        self.actions, self.found_now, self.at, self.ticks, self.kept = None, [], 0, 0, None
        self.shown_n = 0  # the items drawn once already: any after them are new, and come in (fade, typed out)
        self.reveal = {}  # an answer of hers being typed out: its item's id: words shown so far
        self.fades, self.live_job, self.type_job = {}, None, None
        self.opened = set()  # the turns whose steps are open under their "Thought for" row: each's first step's id
        self.face = self._face(15)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        self.column = tk.Frame(page, bg=ui.BG)  # the thread and the box under it, in the middle of their room
        self.column.grid(row=0, column=0, sticky="nsew")
        self.column.grid_columnconfigure(0, weight=1)
        self.column.grid_rowconfigure(1, weight=1)  # the thread has the room; the frames over it (row 0) theirs
        page.bind("<Configure>", self._centre, add="+")
        self.holder = holder = tk.Frame(self.column, bg=ui.BG)
        holder.grid(row=1, column=0, sticky="nsew")
        # one line tall as asked for, so it takes only the room the page gives it: at Tk's 24 lines it held the box
        # low on an empty chat (_lay_empty)
        self.text = tk.Text(holder, wrap="word", height=1, bd=0, highlightthickness=0, bg=ui.BG, fg=ui.TEXT,
                            font=app.f_chat,
                            cursor="arrow", padx=px(2), pady=px(4), state="disabled", takefocus=0,
                            selectbackground=ui.TINTS["blue"][1], selectforeground=ui.TEXT,
                            inactiveselectbackground="")
        self.bar = ttk.Scrollbar(holder, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=self._scrolled)
        self.text.pack(side="left", fill="both", expand=True)
        self.indent = indent = px(30)  # her words start clear of her face, and so does every line after
        tag = self.text.tag_configure
        tag("you", justify="right", spacing1=px(26), spacing3=px(2), rmargin=px(2))
        tag("you_more", justify="right", spacing1=px(6), spacing3=px(2), rmargin=px(2))  # your words under your files
        tag("took", font=app.f_small, foreground=ui.MUTED, lmargin1=px(1), lmargin2=indent, spacing1=px(16))
        tag("her", lmargin1=px(1), lmargin2=indent, rmargin=px(32), spacing1=px(16), spacing2=px(5))  # 1.5 apart
        tag("her_more", lmargin1=indent, lmargin2=indent, rmargin=px(32), spacing1=px(6), spacing2=px(5))
        tag("steps", lmargin1=indent, lmargin2=indent, spacing1=px(8), spacing2=px(4))
        tag("note", font=app.f_small, foreground=ui.MUTED, lmargin1=indent, lmargin2=indent, spacing1=px(8))
        tag("note_failed", font=app.f_small, foreground=ui.ERROR, lmargin1=indent, lmargin2=indent, spacing1=px(8))
        tag("live", font=app.f_chat, foreground=ui.MUTED, lmargin1=px(1), lmargin2=indent, spacing1=px(16))
        # her answer laid out to scan: each sentence after the first a line of its own with room over it, and the
        # facts in it in her semibold, a shade darker (anchors, lines_of)
        tag("her_line", lmargin1=indent, lmargin2=indent, rmargin=px(32), spacing1=px(11), spacing2=px(5))
        tag("anchor", font=(app.f_bold[0], app.f_chat[1]), foreground=ui.TEXT)
        tag("card", lmargin1=indent, lmargin2=indent, spacing1=px(10), spacing3=px(4))
        tag("sources", lmargin1=indent - px(2), lmargin2=indent, spacing1=px(8), spacing2=px(4))
        tag("divider", lmargin1=indent, lmargin2=indent, spacing1=px(8), spacing3=px(2))
        tag("frames", lmargin1=0, lmargin2=0, spacing1=px(18), spacing3=px(6))
        tag("pulse", font=(app.f_small[0], round(app.f_small[1] * 0.75)))  # the thinking dots, small
        tag("chevron", font=app.f_fold if hasattr(app, "f_fold") else app.f_icon_small)
        self.text.bind("<Configure>", self._resized)
        # the wheel glides it as it does her pages (assistant_ui.Glide), over your words' bubbles too
        self.glide = ui.Glide(lambda n: self.text.yview_scroll(n, "pixels"), app.root.after)
        self.text.bind("<MouseWheel>", self._wheel)
        self.title = app._label(holder, ASK, app.f_hero, HERO)  # in grey in the middle while there's nothing yet
        # the empty page as the AI apps have it now (chatfx): "Good afternoon, Hari" in a soft gradient over a slow
        # aurora, "What can I help with?" under it and four things to start from, coming in one after another
        self.hero = Hero(app, holder, ui, self)
        foot = self.foot = tk.Frame(self.column, bg=ui.BG)
        foot.grid(row=2, column=0, sticky="ew", pady=(px(6), px(14)))
        self.status = app._label(foot, "", app.f_small, ui.MUTED)  # what a slash found, or didn't
        self.found = tk.Frame(foot, bg=ui.BG, highlightthickness=1, highlightbackground=ui.LINE)  # what a slash finds
        self.rows = []
        for i in range(SHOWN):
            row = tk.Frame(self.found, bg=ui.BG, cursor="hand2")
            row.pack(fill="x")
            icon = tk.Label(row, font=app.f_icon, fg=ui.MUTED, bg=ui.BG, width=3)
            icon.pack(side="left", pady=px(6))
            name = tk.Label(row, font=app.f_body, fg=ui.TEXT, bg=ui.BG, anchor="w")
            name.pack(side="left", fill="x", expand=True)
            kind = tk.Label(row, font=app.f_small, fg=ui.MUTED, bg=ui.BG)
            kind.pack(side="right", padx=px(12))
            for part in (row, icon, name, kind):
                part.bind("<Button-1>", lambda e, i=i: self.run(i))
            self.rows.append((row, icon, name, kind))
        self.box = Box(app, foot, ui, identity.named(HINT), self.send, self._face(12, FIELD),
                       mic=lambda action: app.controls.put(("box voice", action)),
                       talk=lambda: app.controls.put(("mic",)))
        self.box.canvas.pack(fill="x")
        self.box.bind("<Return>", lambda e: self._enter())
        self.box.bind("<KeyRelease>", self._typed)
        self.box.bind("<Down>", lambda e: self._move(1))
        self.box.bind("<Up>", lambda e: self._move(-1))
        self.box.bind("<Escape>", lambda e: "break" if self.box.voice_key("cancel") else self._clear())
        # the right side (22 November 2026, the owner: "a right-side artifact dock" and "a bento context canvas"):
        # the deliverables rail, what she made or holds for you (Dock), or while her turn looked something up, the
        # context canvas, wider, of what she found (Bento). Neither while there's nothing in it, or no room
        self.rail = tk.Frame(page, bg=ui.BG, width=px(Dock.WIDE))
        self.rail.grid(row=0, column=1, sticky="ns", padx=(px(20), px(6)), pady=(px(2), 0))
        self.rail.grid_propagate(False)
        self.rail.pack_propagate(False)
        self.waiting, self.notes, self.turn_n, self.side_now = None, [], 0, None
        self.dock = Dock(app, self.rail, ui, self)
        # the frames: in the thread itself, after the turn that found them, scrolling with it as Hedwig's do
        # (_put_frames; a band fixed over the thread left four frames a hundred pixels each)
        self.bento = Bento(app, self.text, ui, self)
        self.frames_open, self.frames_after = True, None  # shown; the turn they're from (its first line's id)
        # the chat she was in, unless it's gone quiet for a while: then a new one. The first time, the last few
        # turns from her history are its first chat
        self.chats, self.save_job, self.jump = Chats(os.path.join(ui.win.APPDATA_DIR, "chats.json")), None, False
        if self.chats.found:
            lines = self.chats.lines()
            if lines and time.time() - float(lines[-1].get("at") or 0) > FRESH:
                self.chats.start()
            else:
                self.thread.reset(lines)
        else:
            try:
                self.thread.earlier(ui.history.recent(6, FRESH, cold=False))
            except Exception as exc:  # her history is a file on this PC: a broken one doesn't take the window with it
                print(f"  chat: couldn't read the last turns ({exc!r})")
            self.chats.keep(self.thread.items)
        self.shown_n = len(self.thread.items)  # what was there before the window opened just is, without coming in
        self.empty_now = None
        self.changed()
        self.keep(force=True)

    def _face(self, size, back=None):
        """Her face, her island's own eyes, size logical px tall, on back (the white by default): a soft grey capsule
        with dark eyes, not the island's black one, which looked heavy by every line (22 November 2026, the owner:
        "hard, make it smooth and polished"). None if it can't be drawn: then her words stand without it."""
        try:
            import numpy as np
            import island
            rgba = island.logo(self.app.px(size), 1.0)
            light = rgba[..., :3].mean(axis=2, keepdims=True)  # 0 its capsule, 1 its eyes
            hue = lambda c: np.array([int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)], np.float32)  # noqa: E731
            ink = hue(FACE) * (1 - light) + hue("#1f2937") * light  # a soft grey pill with dark eyes
            alpha = rgba[..., 3:]
            rgb = ink * alpha + hue(back or self.ui.BG) * (1 - alpha)
            h, w = rgb.shape[:2]
            return tk.PhotoImage(master=self.app.root, format="ppm",
                                 data=b"P6 %d %d 255 " % (w, h) + (rgb * 255 + 0.5).astype("uint8").tobytes())
        except Exception as exc:
            print(f"  chat: couldn't draw her face ({exc!r})")
            return None

    def _centre(self, event=None):
        """The thread and its box no wider than WIDE, in the middle of the room they have."""
        px = self.app.px
        room = self.page.winfo_width() - (int(self.rail.cget("width")) + px(26) if self.rail.winfo_manager() else 0)
        pad = max(0, (room - px(self.WIDE)) // 2)
        if room > 1 and pad != getattr(self, "pad", None):
            self.pad = pad
            self.column.grid_configure(padx=(pad, pad))

    def _lay_empty(self, empty):
        """While there's no chat yet, the greeting in the middle of the page, a touch high (Hero), with the box at its
        foot as ever, as Hedwig has it; or the plain words, if the greeting can't be drawn."""
        if empty == self.empty_now:
            return
        self.empty_now = empty
        if empty:
            if not self.hero.show():
                self.title.place(relx=0.5, rely=0.44, anchor="center")
        else:
            self.hero.hide()
            self.title.place_forget()

    # ------------------------------------------------------------------ the thread
    def event(self, state, detail=""):
        """One of her window's events (assistant_ui._set_status): into the thread, and drawn if it shows; and the
        mic red while she's listening."""
        if state == "Box words":  # what you said into the box's mic, written down: into the box
            self.box.voice_words(detail)
            return
        if state == "Context":  # what a look-up of her turn found: a frame in the thread, after this turn
            if self.bento.add(detail, self.turn_n):
                self._frames_here()
                self.toggle_frames(True)
            return
        if state in ("Asked", "Heard"):  # a new turn: the context canvas starts over with its first look-up
            self.turn_n += 1
        if state == "Step" and str(detail).startswith("done\t") and "screen" in str(detail).lower():
            self.app.root.after_idle(self._screen_frame)  # what she saw, as it looks, over the thread

        if state in ("Listening", "Still listening", "Transcribing", "Thinking", "Looking", "Doing it"):
            self.box.set_ring(busy=True)  # the composer's ring travelling while she's at it
        elif state in ("Ready", "Speaking", "Something went wrong"):
            self.box.set_ring(busy=False)
        if state in ("Listening", "Still listening"):
            self.box.listening(True)
        elif state in ("Transcribing", "Thinking", "Ready", "Speaking", "Heard", "Something went wrong"):
            self.box.listening(False)
        if self.thread.event(state, detail):
            self.changed()

    def changed(self):
        if not self.pending:  # once, however many came together
            self.pending = True
            self.app.root.after_idle(self.draw)
        if self.save_job is None:  # and kept a second later, once for a run of them
            self.save_job = self.app.root.after(1000, self.save)

    # ------------------------------------------------------------------ your chats
    def save(self):
        """The open chat kept as it is now (Chats.keep)."""
        if self.save_job is not None:
            try:
                self.app.root.after_cancel(self.save_job)
            except (ValueError, tk.TclError):
                pass
            self.save_job = None
        self.chats.keep(self.thread.items)

    def listed(self, most=None):
        """Your chats for the sidebar, (id, title, when), newest first: the open one as it is now, not as it was kept
        a second ago, and as "New chat" at the top while there's nothing in it (22 November 2026, the owner: the
        pencil did nothing to be seen, and a click on a row a second stale opened the one next to it)."""
        items = self.thread.items
        now = (self.chats.current, title(items) if items else "New chat",
               float(items[-1]["at"]) if items else time.time())
        out = sorted([now] + [c for c in self.chats.listed() if c[0] != self.chats.current], key=lambda c: -c[2])
        return out if most is None else out[:most]

    def _fresh(self):
        """Her follow-ups ("close it") don't reach back past now: the chat on screen is all of it (siri.CHAT_FROM)."""
        siri = sys.modules.get("siri")
        if siri is not None and hasattr(siri, "CHAT_FROM"):
            siri.CHAT_FROM[0] = time.time()
        if siri is not None and hasattr(siri, "CHAT_FILES"):  # and the files attached before aren't "this" any more
            siri.CHAT_FILES.update(paths=[], at=0.0)

    def _show(self, items):
        """The thread made items, drawn at once, at its end."""
        self.thread.reset(items)
        self.reveal.clear()
        self.shown_n, self.jump = len(self.thread.items), True
        self._clear(box=False)
        self.changed()

    def new_chat(self):
        """A new chat, as ChatGPT's and Claude's New chat: this one stays in the list, the thread's empty, and the box
        has the keyboard."""
        self.save()
        if self.thread.items:
            self.chats.start()
            self._show([])
        self._fresh()
        self.app.root.after(60, self._focus)

    def open_chat(self, cid):
        """A chat from the list open again, as it was left."""
        if cid == self.chats.current:
            return
        self.save()
        items = self.chats.open(cid)
        if items is not None:
            self._show(items)
            self._fresh()

    def delete_chat(self, cid):
        """A chat gone from the list; the open one leaves a new chat open. Her memory of what was said stays."""
        self.save()
        if self.chats.delete(cid):
            self._show([])
            self._fresh()
        else:
            self.app._lay_recent()

    def _scrolled(self, lo, hi):
        self.bar.set(lo, hi)
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            self.bar.pack_forget()
        elif not self.bar.winfo_ismapped():
            self.bar.pack(side="right", fill="y", before=self.text)

    def _resized(self, event):
        if abs(event.width - self.width) > self.app.px(24):  # your words' bubbles wrap to the new width
            self.width = event.width
            self.changed()

    def _wheel(self, event):
        self.glide.wheel(event.delta, self.app.s)
        return "break"

    def _glide_down(self):
        """To the end of the thread, at once: a new line is in view the moment it's there (22 November 2026: it glided
        there over a third of a second, which was a line arriving late). Your own wheel still glides (assistant_ui.Glide)."""
        self.text.see("end")

    def _pill(self, text, wrap, fill, fg, font, pad_x, pad_y, radius, mark=None, mark_fg=None, you=False,
              mark_font=None):
        """Words on a rounded pill, as wide as they need up to wrap: your words' bubble (you: its top right corner
        small), or a step's chip with its mark before it. (the canvas, its words and its pill, for a fade)"""
        ui, px = self.ui, self.app.px
        c = tk.Canvas(self.text, bg=ui.BG, highlightthickness=0, bd=0)
        x = pad_x
        items = []
        if mark:
            words = c.create_text(0, pad_y, anchor="nw", text="X", font=font)  # the words' line, to centre the mark on
            mid = (c.bbox(words)[1] + c.bbox(words)[3]) / 2
            c.delete(words)
            if mark == "dot":  # live: a small dot, not a character
                items.append((c.create_oval(x, mid - px(2.5), x + px(5), mid + px(2.5), fill=mark_fg, width=0),
                              mark_fg))
            else:
                items.append((c.create_text(x, mid, anchor="w", text=mark, font=mark_font or font, fill=mark_fg),
                              mark_fg))
            x = c.bbox(items[0][0])[2] + px(6)
        words = c.create_text(x, pad_y, anchor="nw", text=text, font=font, fill=fg, width=wrap)
        items.append((words, fg))
        x1, y1 = c.bbox(words)[2:]
        w, h = x1 + pad_x, y1 + pad_y
        c.configure(width=w, height=h)
        if you:
            c.photo = tk.PhotoImage(master=self.app.root, format="ppm",
                                    data=bubble_ppm(w, h, radius, px(4), fill, ui.BG))
        else:
            c.photo = self.app.smooth(w, h, radius, fill, ui.BG)  # kept with it, or Tk lets the picture go
        c.tag_lower(c.create_image(0, 0, anchor="nw", image=c.photo))
        c.bind("<MouseWheel>", self._wheel)
        return c, items

    def _file_chip(self, path):
        """A file you attached, in the thread: its mark, its name and its size on a hairline card; a click opens it,
        and one that's gone from where it was says so."""
        import attach
        ui, px, app = self.ui, self.app.px, self.app
        name = os.path.basename(path)
        name = name if len(name) <= 30 else name[:19] + "\u2026" + name[-8:]
        try:
            size, there = attach.size_words(os.path.getsize(path)), True
        except OSError:
            size, there = "gone", False
        c = tk.Canvas(self.text, bg=ui.BG, highlightthickness=0, bd=0, cursor="hand2" if there else "")
        mark = c.create_text(px(12), px(19), anchor="w", text=attach.icon(path), font=app.f_icon, fill=ui.ACCENT)
        words = c.create_text(px(38), px(12), anchor="w", text=name, font=app.f_badge, fill=ui.TEXT)
        c.create_text(px(38), px(27), anchor="w", text=size, font=app.f_small, fill=ui.MUTED)
        w = max(c.bbox(words)[2], c.bbox(mark)[2]) + px(14)
        h = px(38)
        c.configure(width=w, height=h)
        c.photo = app.smooth(w, h, px(10), CHIP, ui.BG)
        c.tag_lower(c.create_image(0, 0, anchor="nw", image=c.photo))
        if there:
            c.bind("<Button-1>", lambda e: os.startfile(path))  # in the app Windows opens it with
        c.bind("<MouseWheel>", self._wheel)
        return c

    def _fade_in(self, key, canvas=None, items=(), tag=None, colour=None):
        """A new line coming in: its words from white to their colour (a tag of the thread's), or a pill's from
        white to theirs (canvas items, each (item, its colour))."""
        if not FADE_IN:
            return
        ui = self.ui

        def step(t):
            try:
                if tag is not None:
                    self.text.tag_configure(tag, foreground=ui.mix(ui.BG, colour, t))
                for item, final in items:
                    canvas.itemconfigure(item, fill=ui.mix(ui.BG, final, t))
            except tk.TclError:  # drawn again meanwhile: what it faded is gone
                pass
        step(0.0)
        self.app.animate(f"chat fade {key}", FADE_MS, step)

    def _her(self, t, idx, item, first, new, turn=None):
        """Her words: by her face when they're the first of her turn; when she thought a second or more or took steps
        for it, a row over them first, "Thought for 9s \u203a", which opens and shuts those steps (the reasoning
        accordion the AI chats have, 22 November 2026). Laid out to scan: the facts in bold, a longer answer a
        sentence a line; and after her turn's last words, the sources it drew on as small chips."""
        px, items = self.app.px, self.thread.items
        took = item.get("took") or 0
        steps = [items[i] for i in (turn or {}).get("steps", ())] if first else []
        head = first and (took or steps)
        if first:
            style = "took" if head else "her"
            if self.face is not None:
                t.insert("end", "\u200b", style)
                t.image_create("end", image=self.face, align="center", padx=px(1))
                t.insert("end", "  ", style)
            if head:
                key = id(items[turn["steps"][0]]) if steps else None
                opened = key in self.opened
                words = f"Thought for {took}s" if took else f"Took {len(steps)} step{'s' if len(steps) > 1 else ''}"
                tags = ("took", f"acc{idx}") if steps else ("took",)
                t.insert("end", words, tags)
                if steps:  # its chevron in the icon font, along while shut and down while open
                    t.insert("end", "  ", tags)
                    t.insert("end", "\ue70d" if opened else "\ue76c", tags + ("chevron",))
                t.insert("end", "\n", "took")
                if steps:
                    t.tag_bind(f"acc{idx}", "<Button-1>", lambda e, k=key: self._toggle(k))
                    t.tag_bind(f"acc{idx}", "<Enter>", lambda e: t.configure(cursor="hand2"))
                    t.tag_bind(f"acc{idx}", "<Leave>", lambda e: t.configure(cursor="arrow"))
                if opened:  # its steps, under the row that opened them
                    t.insert("end", "\u200b", "steps")
                    for step in steps:
                        t.window_create("end", window=self._step_chip(step), align="center")
                        t.insert("end", " ", "steps")
                    t.insert("end", "\n", "steps")
                # and a hairline under it, over her words (the owner: "followed by a subtle 1px solid #F3F4F6
                # horizontal divider") when there's an answer worth setting apart: not for "Here you go." after one
                # step, where a line under every short turn read as clutter (oil-ui's subtraction)
                long_answer = len(lines_of(item["text"])) > 1 or took >= 3 or len(steps) >= 2
                if long_answer:
                    line = tk.Frame(t, bg=DIVIDER, height=max(1, px(1)), width=self._measure_wrap())
                    self.bubbles.append(line)
                    t.insert("end", "\u200b", "divider")
                    t.window_create("end", window=line, align="center")
                    t.insert("end", "\n", "divider")
        style = "her" if first and not head else "her_more"
        shown = self.reveal.get(id(item))
        extra = (f"fade{idx}",) if new else ()
        t.mark_set(f"say{idx}", "end-1c")
        t.mark_gravity(f"say{idx}", "left")
        if shown is not None:  # being typed out: plain, till it's whole
            t.insert("end", typed_out(item["text"], shown), (style,) + extra)
        else:
            for n, line in enumerate(lines_of(item["text"])):
                tags = (style if n == 0 else "her_line",) + extra
                if n:
                    t.insert("end", "\n", tags)
                at = 0
                for a, z in anchors(line):
                    t.insert("end", line[at:a], tags)
                    t.insert("end", line[a:z], tags + ("anchor",))
                    at = z
                t.insert("end", line[at:], tags)
        t.mark_set(f"said{idx}", "end-1c")
        t.mark_gravity(f"said{idx}", "right")
        found = sources([items[i] for i in turn.get("steps", ())]) if turn is not None and idx == turn.get("last") \
            else []
        if found:  # where her answer came from, right at its end, as citation pills (the owner: "placed right at
            # the end of sentences"). Each takes the line's own tag, so one that wraps keeps its margin, not under
            # her face as an untagged window did
            last = "her_line" if shown is None and len(lines_of(item["text"])) > 1 else style
            t.insert("end", " ", (last,))
            for name, mark in found:
                at = t.index("end-1c")
                t.window_create("end", window=self._source_chip(name, mark), align="center", padx=px(2))
                t.tag_add(last, at)
        t.insert("end", "\n", style)
        if any(name == "Calendar" for name, _ in found):
            card = self._meeting_card(" ".join(items[i]["text"] for i in range(turn["first"], idx + 1)
                                               if items[i]["kind"] == "her"))
            if card is not None:  # the meeting it's about, to join from right here
                t.insert("end", "\u200b", "card")
                t.window_create("end", window=card)
                t.insert("end", "\n", "card")
        if new:
            self._fade_in(idx, tag=f"fade{idx}", colour=self.ui.TEXT)

    def _measure_wrap(self):
        """How wide her words run in the thread now, for a hairline under them."""
        width = self.text.winfo_width() if self.text.winfo_width() > 1 else self.app.px(560)
        return max(self.app.px(120), width - self.indent - self.app.px(36))

    def _toggle(self, key):
        """A turn's steps opened under its "Thought for" row, or shut again."""
        self.opened ^= {key}
        self.changed()

    def _step_chip(self, step):
        """A step of hers as a small chip: ticked, live, or red with a cross."""
        ui, px = self.ui, self.app.px
        failed = step["state"] == "failed"
        done = step["state"] == "done"
        chip, _ = self._pill(step["text"], px(420), FAILED_BG if failed else STEP_DONE if done else CHIP,
                             ui.ERROR if failed else STEP_DONE_INK if done else CHIP_INK,
                             self.app.f_badge, px(8), px(3), px(9), GLYPHS[step["state"]],
                             ui.ERROR if failed else CHIP_INK, mark_font=self.app.f_fold)
        self.bubbles.append(chip)
        return chip

    def _source_chip(self, name, mark=None):
        """A source her answer drew on, as a compact pill at its end: its name in small grey on a paler grey, with
        little rounding (the owner: "12px, bg #F3F4F6, text #6B7280, px-2 py-0.5 rounded-md")."""
        ui, px, app = self.ui, self.app.px, self.app
        c = tk.Canvas(self.text, bg=ui.BG, highlightthickness=0, bd=0)
        tiny = (app.f_badge[0], round(app.f_small[1] * 0.85))
        fill, ink = TINTS.get(name, (SOURCE, SOURCE_INK))
        words = c.create_text(px(6), px(8.5), anchor="w", text=name, font=tiny, fill=ink)
        w, h = c.bbox(words)[2] + px(6), px(17)
        c.configure(width=w, height=h)
        c.photo = app.smooth(w, h, px(4), fill, ui.BG)
        c.tag_lower(c.create_image(0, 0, anchor="nw", image=c.photo))
        c.bind("<MouseWheel>", self._wheel)
        self.bubbles.append(c)
        return c

    def _meeting_card(self, answer):
        """The meeting her answer is about as a card in the thread, as the AI chats embed one: its name, when, where,
        and Join when it has a link to one. From the calendars on this PC only (agenda.kept): nothing fetched here.
        None if there's no meeting today."""
        import datetime as dt
        try:
            import agenda
            now = dt.datetime.now()
            event = meeting_for(answer, agenda.kept(now - dt.timedelta(hours=1), now + dt.timedelta(hours=16)), now)
        except Exception as exc:
            print(f"  chat: couldn't read the calendar for its card ({exc!r})")
            return None
        if event is None:
            return None
        ui, px, app = self.ui, self.app.px, self.app
        start, end = event["start"], event.get("end") or event["start"]
        clock_of = lambda d: d.strftime("%I:%M%p").lstrip("0").replace(":00", "").lower()  # noqa: E731
        day = "Today" if start.date() == now.date() else "Tomorrow" if start.date() > now.date() else ""
        when = " \u00b7 ".join(p for p in (day, f"{clock_of(start)}\u2013{clock_of(end)}") if p)
        link = LINK.search(event.get("where") or "")
        where = (event.get("where") or "") if not link else ""
        w, h = max(px(300), int(self.text.winfo_width() - self.indent - px(36))), px(52)
        c = tk.Canvas(self.text, bg=ui.BG, highlightthickness=0, bd=0, width=w, height=h)
        c.photo = app.smooth(w, h, px(12), CARD, ui.BG)
        c.create_image(0, 0, anchor="nw", image=c.photo)
        c.mark = app.smooth(px(30), px(30), px(7), "#ffffff", CARD)
        c.create_image(px(12), h // 2, anchor="w", image=c.mark)
        c.create_text(px(27), h // 2, text="\ue787", font=app.f_icon_small, fill="#4f7fe0")
        room = w - px(56) - (px(80) if link else px(12))
        c.create_text(px(54), px(18), anchor="w", font=app.f_badge, fill=ui.TEXT,
                      text=app._fit(event.get("title") or "Meeting", app.f_badge, room))
        c.create_text(px(54), px(34), anchor="w", font=app.f_small, fill=ui.MUTED,
                      text=app._fit(when + (f" \u00b7 {where}" if where else ""), app.f_small, room))
        if link:  # Join, quiet, as Hedwig's: white on the grey with a camera before it; the meeting's own link
            url = link.group() if link.group().lower().startswith("http") else "https://" + link.group()
            jw = app._measure(app.f_badge, "Join") + px(36)
            c.join = app.smooth(jw, px(26), px(8), "#ffffff", CARD)
            c.create_image(w - px(12), h // 2, anchor="e", image=c.join, tags="join")
            c.create_text(w - px(12) - jw + px(14), h // 2, text="\ue714", font=app.f_fold, fill=ui.TEXT, tags="join")
            c.create_text(w - px(12) - jw / 2 + px(7), h // 2, text="Join", font=app.f_badge, fill=ui.TEXT,
                          tags="join")
            c.tag_bind("join", "<Button-1>", lambda e: __import__("webbrowser").open(url))
            c.tag_bind("join", "<Enter>", lambda e: c.configure(cursor="hand2"))
            c.tag_bind("join", "<Leave>", lambda e: c.configure(cursor=""))
        c.bind("<MouseWheel>", self._wheel)
        self.bubbles.append(c)
        return c

    def _type_tick(self):
        """Her answers being typed out: a few more words of each, in place, without drawing the rest again."""
        self.type_job = None
        t = self.text
        for idx, item in enumerate(self.thread.items):
            n = self.reveal.get(id(item))
            if n is None:
                continue
            n += WORDS_A_TICK
            if n >= len(item["text"].split(" ")):
                del self.reveal[id(item)]
                n = None
            else:
                self.reveal[id(item)] = n
            try:
                t.configure(state="normal")
                tags = t.tag_names(f"say{idx}")
                t.delete(f"say{idx}", f"said{idx}")
                t.insert(f"say{idx}", item["text"] if n is None else typed_out(item["text"], n), tags)
                t.configure(state="disabled")
            except tk.TclError:  # drawn again meanwhile, with how far it had got
                pass
        if self.reveal:
            self.type_job = self.app.root.after(TICK_MS, self._type_tick)
        if t.yview()[1] >= 0.9 and "chat glide" not in self.app._anims:
            t.see("end")

    def _live_words(self):
        """What she's at now, with how long she's been at it once that's a second: "Thinking\u2026 4s"."""
        status, began = self.thread.status, self.thread.thinking
        took = int(time.time() - began) if began else 0
        return status + (f"  {took}s" if took >= 1 else "")

    def _live(self):
        """The line by her face while she works: a soft bright band sweeping across its grey letters, as the AI chats'
        text shimmer does (22 November 2026: till then the whole line faded in and out), and its seconds counting."""
        self.live_job = None
        if not self.thread.status:
            return
        t, ui = self.text, self.ui
        try:
            words = self._live_words()
            if words != getattr(self, "live_shown", None):  # a second more: its letters again, in place
                t.configure(state="normal")
                t.delete("live_from", "live_to")
                for i in range(3):  # the three-dot pulse (ui-ux-pro-max's AI-native typing indicator)
                    t.insert("live_to", "\u25cf", ("live", "pulse", f"dot{i}"))
                t.insert("live_to", "   ", ("live",))
                for i, letter in enumerate(words):
                    t.insert("live_to", letter, ("live", f"sh{i}"))
                t.configure(state="disabled")
                self.live_shown = words
            now = time.time()
            for i in range(3):  # each dot swelling in colour in turn, a third of a beat after the last
                glow = 0.5 + 0.5 * math.sin(now * 2 * math.pi * 1.1 - i * 0.9)
                t.tag_configure(f"dot{i}", foreground=ui.mix("#c7d2fe", "#6366f1", glow))
            base, lit = ui.mix(ui.MUTED, ui.BG, 0.2), ui.TEXT
            for i, glow in enumerate(sweep(len(words), time.time())):
                t.tag_configure(f"sh{i}", foreground=ui.mix(base, lit, glow * 0.85))
        except tk.TclError:
            return
        self.live_job = self.app.root.after(40, self._live)

    def draw(self):
        """The thread as it is now, at its end unless you'd scrolled up to read. What's new since the last time comes
        in: a fade, and her answer typed out."""
        self.pending = False
        t, px, ui = self.text, self.app.px, self.ui
        follow = self.jump or not self.bubbles or t.yview()[1] >= 0.98
        self.top_was = t.yview()[0] if self.bubbles and not self.jump else None
        self.jump = False
        items = self.thread.items
        for idx in range(self.shown_n, len(items)):
            if TYPED_OUT and items[idx]["kind"] == "her" and idx > 0:
                self.reveal.setdefault(id(items[idx]), 0)
        t.configure(state="normal")
        t.delete("1.0", "end")
        for bubble in self.bubbles:
            bubble.destroy()
        self.bubbles = []
        wrap = max(px(180), int((t.winfo_width() if t.winfo_width() > 1 else px(520)) * 0.72))
        answered, in_steps = False, False  # she's said something since your last words; a row of chips is open
        _, turn_at = turns(items)
        # where the frames go: before the first words of yours after the turn they're from, else at the end
        frames_at = None
        if self.frames_open and self.bento.found:
            start = next((n for n, i in enumerate(items) if id(i) == self.frames_after), None)
            frames_at = next((n for n in range(start + 1, len(items)) if items[n]["kind"] == "you"), len(items)) \
                if start is not None else len(items)
        for idx, item in enumerate(items):
            if idx == frames_at:
                if in_steps:
                    t.insert("end", "\n", "steps")
                    in_steps = False
                self._put_frames(t)
            new = idx >= self.shown_n
            if in_steps and item["kind"] != "step":
                t.insert("end", "\n", "steps")
                in_steps = False
            if item["kind"] == "you":
                if item.get("files"):  # what you attached, over your words, each a chip that opens it
                    t.insert("end", "\u200b", "you")
                    for path in item["files"]:
                        chip = self._file_chip(path)
                        self.bubbles.append(chip)
                        t.window_create("end", window=chip, padx=px(3))
                    t.insert("end", "\n", "you")
                if item["text"]:
                    bubble, parts = self._pill(item["text"], wrap, BUBBLE, ui.TEXT, self.app.f_chat, px(13), px(8),
                                               px(14))
                    self.bubbles.append(bubble)
                    under = "you_more" if item.get("files") else "you"
                    t.insert("end", "\u200b", under)  # the line's first letter: what puts it on the right
                    t.window_create("end", window=bubble)
                    t.insert("end", "\n", under)
                    if new:
                        self._fade_in(idx, bubble, parts)
                answered = False
            elif item["kind"] == "her":
                self._her(t, idx, item, not answered, new, turn_at.get(idx))
                answered = True
            elif item["kind"] == "step" and turn_at[idx]["first"] is not None:
                continue  # answered: under its "Thought for" row, shut till it's opened (_her)
            elif item["kind"] == "step":
                failed = item["state"] == "failed"
                chip, parts = self._pill(item["text"], wrap, FAILED_BG if failed else CHIP,
                                         ui.ERROR if failed else CHIP_INK, self.app.f_badge, px(8), px(3),
                                         px(9), GLYPHS[item["state"]], ui.ERROR if failed else CHIP_INK,
                                         mark_font=self.app.f_fold)
                self.bubbles.append(chip)
                t.insert("end", "\u200b" if not in_steps else " ", "steps")
                t.window_create("end", window=chip, align="center")
                in_steps = True
                if new:
                    self._fade_in(idx, chip, parts)
            else:
                tag = "note_failed" if item["state"] == "failed" else "note"
                t.insert("end", item["text"] + "\n", (tag, f"fade{idx}") if new else tag)
                if new:
                    self._fade_in(idx, tag=f"fade{idx}", colour=ui.ERROR if item["state"] == "failed" else ui.MUTED)
        if in_steps:
            t.insert("end", "\n", "steps")
        if frames_at == len(items):
            self._put_frames(t)
        if self.thread.status and items:  # what she's at now, by her face
            if self.face is not None:
                t.insert("end", "\u200b", "live")
                t.image_create("end", image=self.face, align="center", padx=px(1))
                t.insert("end", "  ", "live")
            t.mark_set("live_from", "end-1c")
            t.mark_gravity("live_from", "left")
            t.mark_set("live_to", "end-1c")
            t.mark_gravity("live_to", "right")
            t.insert("end", "\n", "live")
            self.live_shown = None  # its letters put in by _live, each its own for the sweep
            if self.live_job is not None:
                self.app.root.after_cancel(self.live_job)
            self._live()
        t.configure(state="disabled")
        self.shown_n = len(items)
        if self.reveal and self.type_job is None:
            self.type_job = self.app.root.after(TICK_MS, self._type_tick)
        if follow:
            was = getattr(self, "top_was", None)
            if was is not None and items:  # where it was before this drawing, then down to what's new, gliding
                t.yview_moveto(was)
                self._glide_down()
            else:
                t.see("end")
        elif self.top_was is not None:  # reading further up (a turn's steps opened there): it stays where it was
            t.yview_moveto(self.top_was)
        self._lay_empty(not items)
        if not self.found_now:
            self.status.pack_forget()
        getattr(self.app, "_lay_recent", lambda: None)()  # what you last asked, down the sidebar

    # ------------------------------------------------------------------ the box
    def shown(self):
        """Her window has come to this page: the box is ready to type in."""
        self.keep(force=True)
        self.app.root.after(60, self._focus)

    def _focus(self):
        try:
            if self.app.current_tab == "home" and self.app.root.focus_displayof() is not None:
                self.box.focus_set()
        except (KeyError, tk.TclError):
            pass

    def again(self, text):
        """Something you asked before, back in the box: to send again, or change first."""
        self.box.put(text)
        self.box.focus_set()

    def _enter(self):
        """Enter: Done while dictating, else what's in the box sent; never a new line in it (Shift+Enter is that)."""
        if not self.box.voice_key("done"):
            self.send()
        return "break"

    def send(self, text=None):
        """What's in the box, or text: after a slash, the first thing found is gone to; anything else is hers, a
        turn of yours as if said with her name, and it's in the thread straight away."""
        text = " ".join((self.box.get() if text is None else text).split())
        files = list(getattr(self.box, "files", ()))
        if not text and not files:
            return
        if text.startswith("/") and not files:
            self._find(text)
            self.run(self.at)
            return
        self.box.clear()
        if files:
            self.box.take()
        self._clear(box=False)
        added = self.thread.you(text, files)
        if self.thread.waiting(starting_why(self.app, self.thread)) or added:  # and, while she starts up, why it waits
            self.changed()
        if files:  # with what you attached: answered in the chat, which has them (siri.chat_turn, attach.py)
            self.app.controls.put(("chat", text, files))
            return
        # answered here, in words (siri.CHAT_TURN), or out loud too with the speaker on in the box (command_for)
        self.app.controls.put((command_for(bool(getattr(self.box, "speaks", False))), text))

    def _typed(self, event=None):
        getattr(self.box, "_paint_send", lambda: None)()  # an arrow once there's something to send, bars without
        if event is not None and event.keysym in ("Up", "Down", "Return", "Escape"):
            return
        text = self.box.get()
        if text.startswith("/"):
            self._find(text)
        elif self.found_now or self.actions is not None:
            self._clear(box=False)

    def _find(self, text):
        if self.actions is None:  # read once a search: every tab, part and row of Settings
            self.actions = self.app.quick_actions()
        was = [a[1] for a in self.found_now]
        self.found_now = find(self.actions, text[1:])
        if [a[1] for a in self.found_now] != was:
            self.at = 0
        self._fill(text)

    def _fill(self, text=""):
        ui, px = self.ui, self.app.px
        for i, (row, icon, name, kind) in enumerate(self.rows):
            if i < len(self.found_now):
                a = self.found_now[i]
                bg = CHIP if i == self.at else ui.BG
                icon.configure(text=a[0], bg=bg)
                name.configure(text=a[1], bg=bg)
                kind.configure(text=a[2], bg=bg)
                row.configure(bg=bg)
                row.pack(fill="x")
            else:
                row.pack_forget()
        if self.found_now:
            self.status.pack_forget()
            self.found.pack(fill="x", pady=(0, px(6)), before=self.box.canvas)
        else:
            self.found.pack_forget()
            if len(text) > 1:
                self.status.configure(text="Nothing in her window is called that. Without the slash, she's asked.")
                self.status.pack(anchor="w", padx=px(8), pady=(0, px(4)), before=self.box.canvas)
            else:
                self.status.pack_forget()

    def _move(self, step):
        if self.found_now:
            self.at = (self.at + step) % len(self.found_now)
            self._fill()
            return "break"

    def _clear(self, box=True):
        self.found_now, self.actions, self.at = [], None, 0
        self.found.pack_forget()
        self.status.pack_forget()
        if box:
            self.box.clear()
            return "break"

    def run(self, i):
        """The i-th thing found: gone to, and the box is clear again."""
        if not 0 <= i < len(self.found_now):
            return
        what = self.found_now[i][3]
        self._clear()
        what()

    # ------------------------------------------------------------------ what stays
    def tick(self):
        """Twice a second from her window: the timers each time, the lists every three seconds, while this page is
        the one up."""
        if getattr(self.app, "current_tab", None) != "home":
            return
        self.ticks += 1
        self.keep(force=self.ticks % 6 == 0)

    def decide(self, action):
        """Approve or Cancel on the task held for your yes: done as her Tasks tab does it, and said in the thread."""
        task, store = self.waiting, getattr(self.app, "task_store", None)
        if task is None or store is None:
            return
        ok = store.cancel(task["id"]) if action == "cancel" else store.approve(task["id"])
        done = "cancelled" if action == "cancel" else "approved"
        self.thread._add("note", f"Task {task['id']} {done}." if ok else f"Task {task['id']} can't be {done} now.",
                         "" if ok else "failed")
        self.changed()
        self.keep(force=True)

    def keep(self, force=False):
        """What the right side shows, from her state: the timers each time, the tasks, a message waiting for your yes
        and the notes saved today every few seconds; and which of the rail and the canvas is up."""
        siri = sys.modules.get("siri")
        timers = [(label, clock(secs)) for label, secs in
                  (siri.timer_snapshot()[:3] if hasattr(siri, "timer_snapshot") else [])]
        if force or self.kept is None:
            try:
                store = getattr(self.app, "task_store", None)
                self.waiting = held(store.list(40) if store is not None else [])
            except Exception as exc:
                print(f"  chat: couldn't read the tasks ({exc!r})")
            self.notes = self._notes()
            getattr(self.app, "_lay_recent", lambda: None)()  # and how long ago each chat was
        self.kept = True
        items = self.dock.items(self.waiting, pending_message(siri), self.notes, timers)
        self.dock.show(items)
        self._lay_side(bool(items))

    def answer_words(self):
        """The words of four letters or more in her latest answer, for a frame to mark what it's about."""
        last = next((i["text"] for i in reversed(self.thread.items) if i["kind"] == "her"), "")
        return frozenset(re.findall(r"[a-z]{4,}", last.lower()))

    def _screen_frame(self):
        """Her turn looked at the screen: what she saw, as a frame (vision.LAST), if it's from just now."""
        vision = sys.modules.get("vision")
        last = getattr(vision, "LAST", None) or [None, 0.0, ""]
        if last[0] is not None and time.time() - float(last[1]) < 120 and \
                self.bento.add_picture(getattr(last[0], "small", None), last[2], self.turn_n):
            self._frames_here()
            self.toggle_frames(True)

    def _frames_here(self):
        """The frames belong to this turn: they're drawn after it, before the next words of yours."""
        last = next((i for i in reversed(self.thread.items) if i["kind"] == "you"), None)
        self.frames_after = id(last) if last is not None else None

    def toggle_frames(self, open_=None):
        """The context frames in the thread shown or hidden ("Expand frames" at the top); shown by themselves when
        her turn finds something."""
        self.frames_open = (not self.frames_open) if open_ is None else bool(open_)
        self._lay_frames()
        self.changed()

    def _lay_frames(self):
        """The top's "Expand frames" told how many there are and whether they're shown."""
        self.app.frames_n, self.app.frames_open = len(self.bento.found), self.frames_open and bool(self.bento.found)
        getattr(self.app, "_lay_head", lambda: None)()

    def _put_frames(self, t):
        """The frames, here in the thread: as wide as the thread, as tall as their rows need (Bento.height)."""
        px = self.app.px
        width = (t.winfo_width() if t.winfo_width() > 1 else px(700)) - px(10)
        frame = self.bento.rebuild(t, width, self.bento.height())
        t.insert("end", "\u200b", "frames")
        t.window_create("end", window=frame)
        t.insert("end", "\n", "frames")

    def _notes(self):
        """The notes she saved in the last day, newest first, two at most: (path, their first words)."""
        folder = getattr(self.ui, "NOTES_DIR", None)
        try:
            paths = [os.path.join(folder, n) for n in os.listdir(folder) if n.lower().endswith((".md", ".txt"))]
        except (OSError, TypeError):
            return []
        fresh = sorted((p for p in paths if time.time() - os.path.getmtime(p) < Dock.NOTES_FOR),
                       key=os.path.getmtime, reverse=True)[:2]
        out = []
        for path in fresh:
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    out.append((path, f.read(600)))
            except OSError:
                pass
        return out

    def _lay_side(self, items=None):
        """The rail while it has a card (or is pinned) and there's room; else the chat has the page."""
        px = self.app.px
        width = self.page.winfo_width()
        items = bool(self.dock.shown) if items is None else items
        want = ("dock", px(Dock.WIDE)) if (items or self.dock.pinned) and (width < 2 or width >= px(self.NARROW)) \
            else None
        if want == self.side_now:
            return
        self.side_now = want
        if want is None:
            self.rail.grid_remove()
        else:
            self.rail.configure(width=want[1])
            self.dock.frame.pack(fill="both", expand=True)
            self.rail.grid()
        self._centre()
