"""More ways to say her scripted lines, written by the answer model in her own voice (SOUL.md), so a quick reply isn't
the same two or three lines every time. On 27 October Hari said she still sounded like a bot: the same greeting, the
same lines. Of 1,528 lines in her log, 229 were "One moment.", "On it." and "Sure, one sec." (said while she thinks),
91 were "Opening it now.", "Sure, opening it." and "Here you go.", and her welcome back was word for word the same 13
times.

Kept in %APPDATA%\\Hey Harry\\phrases.json, written again in the background every EVERY seconds and when SOUL.md
changes (siri.refresh_phrases), and each new line checked before it's kept (fits): the same {fields} as the lines it
stands for, about as short, plain spoken words with no [tags], emoji or her own name, a question only where they are
one. pick() never says the line she said last time and keeps away from the last few, and uses a new line only once
her voice for it is made (siri.warm_cache), so it plays as soon as the old ones did. Delete the file to go back to
the lines as written."""
import collections
import hashlib
import json
import os
import random
import re
import threading
import time

import winplatform as win

PATH = os.path.join(win.APPDATA_DIR, "phrases.json")
EVERY = 2 * 86400  # seconds between writes: each makes about 300 new lines for her voice to say ahead
MORE, KEEP = 5, 10  # new ways written for each line each time, and the most kept (the newest)
# and for what she says most: a filler while she thinks was 15% of all she said
MORE_FOR, KEEP_FOR = {"filler": 8, "filler_ask": 8, "greeting": 6, "thanks": 6}, {"filler": 16, "filler_ask": 16}
# a line with an app's or a site's name in it is made ahead for every app and site (siri.all_scripted_lines)
MORE_NAMED, KEEP_NAMED = 1, 2
KEEP_OUT = {"first_run", "system_shutdown", "system_restart", "system_abort_shutdown"}  # said exactly as written
SAID_KEEP = 5  # her last welcomes, so a new one sounds different (siri.fresh_welcome)
RECENT_KEEP = 4  # lines said lately for each kind, kept away from
FIELD = re.compile(r"\{(\w+)\}")
NAMED_FIELDS = {"app", "site"}
WHEN = re.compile(r"\b(?:morning|afternoon|evening|night|tonight|today|tomorrow|yesterday|weekend|week)\b", re.I)
ASK = ("These are short lines you say out loud at everyday moments, by what they're for (\"say\"), each with how many "
       "new ways to write (\"new\"). So you don't sound the same every time, write that many new ways to say each "
       "one, as yourself: everyday spoken English, about as short as the lines given and never longer, the same "
       "meaning with nothing added, no names, no emoji, no [tags]. Keep every word in braces, like {app}, exactly "
       "as it is. A question stays a question. Never repeat a line given. Reply with JSON only, the new ways for "
       "each key as an object on a row of its own: {\"key\": [\"...\", \"...\"]}\n\n")
_lock = threading.Lock()
_cache = {"mtime": None, "data": {}}
RECENT = {}  # kind: the lines said lately (pick)


def digest(text):
    return hashlib.sha1(str(text or "").strip().encode("utf-8")).hexdigest()


def load():
    """What's in phrases.json, read again only when it changes. {} if there's none or it can't be read."""
    try:
        mtime = os.path.getmtime(PATH)
    except OSError:
        return {}
    if _cache["mtime"] != mtime:
        try:
            with open(PATH, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        _cache.update(mtime=mtime, data=data if isinstance(data, dict) else {})
    return _cache["data"]


def _save(data):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)


def fields(lines):
    """The {fields} the lines share, or None if they don't all have the same ones."""
    found = {frozenset(FIELD.findall(line)) for line in lines}
    return next(iter(found)) if len(found) == 1 else None


def fits(line, base):
    """True if line can stand in for the lines in base: the same {fields}, about as short, plain spoken words, and a
    question only where they are one."""
    if not isinstance(line, str) or not line.strip() or "\n" in line or not base:
        return False
    line, want = line.strip(), fields(base)
    if want is None or frozenset(FIELD.findall(line)) != want or re.search(r"[{}]", FIELD.sub("", line)):
        return False
    if re.search(r"[\[\]<>*_#`~|\\@^=+]|https?:|\b(?:harry|jarvis)\b", line, re.I):
        return False
    if re.search(r"[^\x20-\x7e\u2018\u2019\u201c\u201d\u2013\u2014]", line):  # no emoji, nothing she'd spell out
        return False
    # no time of day the lines don't have: Haiku wrote "Morning, what can I do?" for a hello said at any hour
    if {w.lower() for w in WHEN.findall(line)} - {w.lower() for b in base for w in WHEN.findall(b)}:
        return False
    longest = max(len(b) for b in base)
    if len(line) > max(longest * 1.5, longest + 20) or len(line) < 2:
        return False
    asks = [b.rstrip().endswith("?") for b in base]
    if all(asks) != line.endswith("?") and (all(asks) or not any(asks)):
        return False  # a question for a question, never one for a line that tells
    return line[-1] in ".!?"


def pool(kind, base):
    """The lines as written, then the new ways kept for them that still fit (the lines may have changed since)."""
    out, seen = list(base), {b.lower() for b in base}
    for line in ((load().get("lines") or {}).get(kind) or []):
        if isinstance(line, str) and line.strip().lower() not in seen and fits(line, base):
            out.append(line.strip())
            seen.add(line.strip().lower())
    return out


def pick(kind, base, ready=None):
    """One way to say it: never the line said last time and away from the last few. A new way only once ready(line)
    says it's set to play (its voice made); the lines as written always count."""
    lines = [line for line in pool(kind, base) if line in base or ready is None or ready(line)]
    recent = RECENT.setdefault(kind, collections.deque(maxlen=RECENT_KEEP))
    keep = min(len(lines) - 1, len(recent))
    avoid = set(list(recent)[len(recent) - keep:]) if keep > 0 else set()
    line = random.choice([line for line in lines if line not in avoid] or lines)
    recent.append(line)
    return line


def due(personality, kinds, now=None):
    """True if it's time to write new ways: none yet, the last more than EVERY ago, a new personality, or lines to
    say that weren't asked about last time."""
    data, now = load(), time.time() if now is None else now
    return not data.get("lines") or now - float(data.get("made") or 0) > EVERY or \
        data.get("soul") != digest(personality) or bool(set(kinds) - set(data.get("kinds") or []))


def _json_in(text, kinds=()):
    """The JSON objects in the model's reply, one after another (ASK asks for one a kind of line, each on a line of
    its own), put together. One that doesn't read as JSON is skipped and the rest kept, and so is each kind of line
    in it that does read (_parts): the first time she started with it, on 27 October, her reply didn't read as JSON,
    and no line was kept. Haiku still wrote one object for them all."""
    text, found, at = str(text or ""), {}, 0
    decoder = json.JSONDecoder()
    while True:
        at = text.find("{", at)
        if at < 0:
            break
        try:
            obj, end = decoder.raw_decode(text, at)
        except ValueError:
            at += 1
            continue
        if isinstance(obj, dict):
            found.update(obj)
        at = end
    if set(kinds) - set(found):
        for kind, value in _parts(text, kinds):
            found.setdefault(kind, value)
    if not found:
        raise ValueError("no JSON object in the reply")
    return found


KIND_AT = re.compile(r'"(\w+)"\s*:\s*')


def _parts(text, kinds):
    """(kind, its lines) for each of kinds in a reply, read on its own from its name to the next's, so a mistake in
    one kind's lines (or a reply cut off) loses only those. Only what reads as JSON is kept, never pieces of lines."""
    marks = [m for m in KIND_AT.finditer(text) if m[1] in kinds]
    for m, after in zip(marks, marks[1:] + [None]):
        part = re.sub(r"[\s,{}]+$", "", text[m.end():after.start() if after else len(text)])
        for value in (part, part + "}"):  # a value that's an object lost its last brace with the reply's
            try:
                yield m[1], json.loads(value)
                break
            except ValueError:
                continue


def _strings(value):
    """The lines in a reply's value, however it nested them: a list, a list in a list (as it wrote on 27 October,
    copying {"say": [...], "new": 5}), or an object of them."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def how_many(kind, base):
    """(new ways to write each time, most kept) for a kind of line."""
    if fields(base) & NAMED_FIELDS:
        return MORE_NAMED, KEEP_NAMED
    return MORE_FOR.get(kind, MORE), KEEP_FOR.get(kind, KEEP)


def write(ask, personality, lines, now=None):
    """Asks for new ways to say lines ({kind: [line, ...]}, KEEP_OUT left out) with ask(messages) -> text, and keeps
    those that fit, the newest first, up to how_many's most for each. Returns how many new lines were kept."""
    asked = {k: list(v) for k, v in lines.items() if k not in KEEP_OUT and fields(v) is not None}
    wanted = {k: {"say": v, "new": how_many(k, v)[0]} for k, v in asked.items()}
    reply = _json_in(ask([{"role": "system", "content": personality},
                          {"role": "user", "content": ASK + json.dumps(wanted, ensure_ascii=False)}]), asked)
    with _lock:
        data = dict(load())
        kept, made = dict(data.get("lines") or {}), 0
        for kind, base in asked.items():
            more, most = how_many(kind, base)
            have = {b.lower() for b in base}
            new = []
            for line in _strings(reply.get(kind)):
                line = line.strip()
                if fits(line, base) and line.lower() not in have:
                    new.append(line)
                    have.add(line.lower())
            new = new[:more]
            old = [line for line in kept.get(kind) or [] if isinstance(line, str) and line.lower() not in
                   {n.lower() for n in new} and fits(line, base)]
            made += len([n for n in new if n.lower() not in {o.lower() for o in kept.get(kind) or []}])
            kept[kind] = (new + old)[:most]
        data.update(made=time.time() if now is None else now, soul=digest(personality), kinds=sorted(lines),
                    lines={k: v for k, v in kept.items() if k in asked})
        _save(data)
    return made


def said(kind):
    """The last few of a kind of line she said, oldest first: her welcomes."""
    return [s for s in ((load().get("said") or {}).get(kind) or []) if isinstance(s, str)][-SAID_KEEP:]


def remember(kind, line):
    """One more of them, the last SAID_KEEP kept."""
    with _lock:
        data = dict(load())
        lines = dict(data.get("said") or {})
        lines[kind] = (said(kind) + [str(line)])[-SAID_KEEP:]
        data["said"] = lines
        try:
            _save(data)
        except OSError as exc:
            print(f"  couldn't keep her {kind}: {exc!r}")
