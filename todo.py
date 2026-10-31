"""Her to-do list, kept on this PC in %APPDATA%\\Hey Harry\\todo.json: "add milk to my to-do list", "what's on my
to-do list?", "cross off milk". An idea from Nixi (heynixi.com), which keeps one.

Things you tick off stay in the file a week, marked done, so "what did I get done?" has an answer and a tick by
mistake can be put back from the To-do tab; then they go.

A day said with one ("meet Sam tomorrow", "call Ravi on Friday") is kept as the date it means, from the day it was
added, and said against today's (shown): "Meet with Sam today", then "which was yesterday". Kept as the words, it
was "tomorrow" every day after (31 October 2026, the owner); lists from before then are read the same way, from the
day each was added (_dated).
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import re
import tempfile
import threading
import time

import winplatform as win

PATH = os.path.join(win.APPDATA_DIR, "todo.json")
MAX_TEXT = 200
KEEP_DONE = 7 * 86400  # seconds a ticked-off thing stays, marked done
LOCK = threading.Lock()  # the phone and the PC can both change it at once
FILLER = {"the", "a", "an", "my", "to", "of", "for", "and", "on", "in", "at", "with", "that", "this", "it", "thing",
          "item", "task"}


WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# a day said with a thing to do, and the word before it if there is one ("by", "on"), which goes with it
WHEN = re.compile(r"(?:,\s*)?\b(?:(?:by|on|for|before|until)\s+)?(?:(day after tomorrow)|(tomorrow)|"
                  r"(today|tonight|this (?:morning|afternoon|evening))|(?:(this|next)\s+)?(" + "|".join(WEEKDAYS) +
                  r"))\b", re.I)


def due_of(text, at=None):
    """(the date text is for, as 2026-10-31, and text without the words that said it) from "tomorrow", "today",
    "tonight", "day after tomorrow" or a weekday, said on the day of at (a time, now with None); (None, text) for
    none."""
    m = WHEN.search(text or "")
    if not m:
        return None, text
    day = dt.date.fromtimestamp(time.time() if at is None else float(at))
    if m.group(1):
        due = day + dt.timedelta(days=2)
    elif m.group(2):
        due = day + dt.timedelta(days=1)
    elif m.group(3):
        due = day
    else:
        ahead = (WEEKDAYS.index(m.group(5).lower()) - day.weekday()) % 7
        if ahead == 0 and (m.group(4) or "").lower() == "next":
            ahead = 7
        due = day + dt.timedelta(days=ahead)
    rest = " ".join((text[:m.start()] + " " + text[m.end():]).split()).strip(" ,.;")
    return due.isoformat(), (rest[:1].upper() + rest[1:]) if re.search(r"\w", rest) else text


def when_said(due, today=None):
    """A to-do's date as she says it on today: today, tomorrow, yesterday, on Saturday, on 12 Nov."""
    try:
        day = dt.date.fromisoformat(str(due))
    except ValueError:
        return ""
    today = today or dt.date.today()
    gap = (day - today).days
    if gap == 0:
        return "today"
    if gap == 1:
        return "tomorrow"
    if gap == -1:
        return "yesterday"
    if 1 < gap < 7:
        return f"on {day.strftime('%A')}"
    return f"on {day.day} {day.strftime('%b')}"


def shown(item, today=None):
    """A to-do as she says and shows it, its day against today's: "Meet with Sam today", "Call Ravi on Friday",
    "Meet with Sam, which was yesterday"."""
    text = str(item.get("text") or "")
    if not item.get("due"):
        return text
    when = when_said(item["due"], today)
    if not when:
        return text
    past = dt.date.fromisoformat(item["due"]) < (today or dt.date.today())
    return f"{text}, which was {when}" if past and not item.get("done") else f"{text} {when}"


def _dated(found):
    """A list from before its days were kept as dates: each thing's day worked out from the day it was added."""
    for i in found:
        if "due" not in i:
            due, rest = due_of(i["text"], i.get("added"))
            i["due"] = due
            if due:
                i["text"] = rest
    return found


def _path():
    return win.own_data(PATH)


def _read():
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
        return _dated([i for i in data if isinstance(i, dict) and i.get("text")]) if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _write(items):
    path = _path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix="todo.json.", suffix=".tmp")
    try:  # whole or not at all, as contacts.json is
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def clean(text):
    """One thing to do, as it'll be said back: on one line, without "to" or "that I need to" in front."""
    text = " ".join(str(text or "").split()).strip(" .,;:!?")
    text = re.sub(r"^(?:that )?(?:i (?:need|have|got|must|should) to |i've got to |remember to |to )", "", text, flags=re.I)
    text = "".join(c for c in text if c.isprintable())[:MAX_TEXT].strip()
    if not text or not re.search(r"\w", text):
        raise ValueError("I didn't catch what to add")
    return text[:1].upper() + text[1:]


def items(done=False):
    """What's still to do, oldest first; with done, the ticked-off ones from the last week too."""
    with LOCK:
        found = _read()
    return _tidy(found) if done else [i for i in found if not i.get("done")]


def _words(text):
    return [w for w in re.findall(r"[a-z0-9']+", str(text).lower()) if w not in FILLER]


ORDINALS = {"first": 1, "1st": 1, "one": 1, "1": 1, "second": 2, "2nd": 2, "two": 2, "2": 2, "third": 3, "3rd": 3,
            "three": 3, "3": 3, "fourth": 4, "4th": 4, "four": 4, "4": 4, "fifth": 5, "5th": 5, "five": 5, "5": 5}


def _match(found, words, loose=True):
    """The thing words point at, among found: said in full, the only one with all those words in it, or by where it
    is on the list ("the second one", "number 3", "the last one"). loose: or the only one with any of the words."""
    said = " ".join(_words(words))
    if not said:
        return None
    spot = re.fullmatch(r"(?:number |no |#)?(\w+)(?: one)?", said)
    if spot and found and (spot.group(1) in ORDINALS or spot.group(1) == "last"):
        n = len(found) if spot.group(1) == "last" else ORDINALS[spot.group(1)]
        return found[n - 1] if 0 < n <= len(found) else None
    exact = [i for i in found if " ".join(_words(i["text"])) == said]
    if exact:
        return exact[0]
    wanted = set(said.split())
    hits = [i for i in found if wanted <= set(_words(i["text"]))]
    if len(hits) == 1:
        return hits[0]
    if not hits and loose:  # "milk and bread" for "Buy milk", "call ravi" for "Ring Ravi tomorrow"
        hits = [i for i in found if any(w in set(_words(i["text"])) for w in wanted if len(w) > 2)]
        return hits[0] if len(hits) == 1 else None
    return None


def find(words, loose=True):
    """The open thing words point at, or None if it's none of them or could be more than one. Not loose: every word
    said is in it, for "I've done the dishes", which may just be talk."""
    return _match(items(), words, loose)


def add(text):
    """Put it on the list, unless it's there already. Returns (the thing, True if it was new)."""
    due, text = due_of(clean(text))
    with LOCK:
        found = _read()
        same = next((i for i in found if not i.get("done") and _words(i["text"]) == _words(text)), None)
        if same:
            if due and same.get("due") != due:  # the same thing, for another day: that day now
                same["due"] = due
                _write(found)
            return same, False
        item = {"id": max((int(i.get("id") or 0) for i in found), default=0) + 1, "text": text,
                "added": time.time(), "done": False, "due": due}
        found.append(item)
        _write(found)
    return item, True


def complete(words):
    """Tick off the open thing words point at. LookupError, saying why, if it's none of them or more than one."""
    with LOCK:
        found = _read()
        item = _match([i for i in found if not i.get("done")], words)
        if item is None:
            raise LookupError(_why_not(found, words))
        item["done"], item["done_at"] = True, time.time()
        _write(_tidy(found))
    return item


def remove(words):
    """Take the thing words point at off the list altogether, as if it was never there."""
    with LOCK:
        found = _read()
        item = _match([i for i in found if not i.get("done")], words)
        if item is None:
            raise LookupError(_why_not(found, words))
        _write([i for i in found if i is not item])
    return item


def _by_id(item_id, change):
    """Change the thing with that id, for the To-do tab. change(found, item) edits it, or returns the new list."""
    with LOCK:
        found = _read()
        item = next((i for i in found if i.get("id") == item_id), None)
        if item is None:
            raise LookupError("That's not on your to-do list any more")
        changed = change(found, item)
        _write(_tidy(found if changed is None else changed))
    return item


def tick(item_id):
    """Tick it off, from the To-do tab."""
    def change(found, item):
        item["done"], item["done_at"] = True, time.time()
    return _by_id(item_id, change)


def undo(item_id):
    """Put a ticked-off thing back on the list, from the To-do tab."""
    def change(found, item):
        item["done"] = False
        item.pop("done_at", None)
    return _by_id(item_id, change)


def drop(item_id):
    """Take it off the list altogether, from the To-do tab."""
    return _by_id(item_id, lambda found, item: [i for i in found if i is not item])


def edit(item_id, text):
    """Fix what it says, from the To-do tab, when she misheard it."""
    due, text = due_of(clean(text))

    def change(found, item):
        item["text"] = text
        if due:
            item["due"] = due
    return _by_id(item_id, change)


def clear():
    """Everything off the list. Returns how many things were on it. Only ever after a yes."""
    with LOCK:
        found = _read()
        left = [i for i in found if not i.get("done")]
        _write([])
    return len(left)


def _tidy(found):
    """Ticked-off things older than a week go."""
    now = time.time()
    return [i for i in found if not i.get("done") or now - float(i.get("done_at") or now) < KEEP_DONE]


def _why_not(found, words):
    open_ = [i for i in found if not i.get("done")]
    if not open_:
        return "Your to-do list is empty"
    wanted = set(_words(words))
    if wanted and len([i for i in open_ if wanted <= set(_words(i["text"]))]) > 1:
        return f"More than one thing on your list has \u201c{' '.join(str(words).split())}\u201d in it: say which"
    return f"\u201c{' '.join(str(words).split())}\u201d isn't on your to-do list"


def said(limit=8):
    """The list as she'd say it: "You've got 3 things to do: buy milk, call Ravi and send the invoice."."""
    left = items()
    if not left:
        return "Your to-do list is empty."
    names = [shown(i)[:1].lower() + shown(i)[1:] for i in left[:limit]]
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    more = f", and {len(left) - limit} more" if len(left) > limit else ""
    count = "one thing" if len(left) == 1 else f"{len(left)} things"
    return f"You've got {count} to do: {joined}{more}."


def for_model(limit=15):
    """The list for the model's context, so "what's left?" and "tick off the second one" make sense."""
    left = items()
    if not left:
        return ""
    today = dt.date.today()
    return (f"Their to-do list (today is {today.strftime('%A')} {today.day} {today.strftime('%B')}): " +
            "; ".join(f"{n}. {shown(i, today)}" for n, i in enumerate(left[:limit], 1)) + ".")
