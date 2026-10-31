"""Her long memory (31 October 2026, the owner: "my memory is full, tell me something to forget", after OpenMuse's
memory, a list with no end to it). Hermes Agent's two small files, USER.md and MEMORY.md, go into every request, so
they're capped (hermes_memory.USER_CHAR_LIMIT, MEMORY_CHAR_LIMIT). When one is full and a model won't make room
(siri.make_room), the entries least like what you've been asking about lately move out here, never dropped (move_out),
and the ones closest in meaning to a turn's words come back into that turn's prompt (nearest, siri.memory_block):
"what song does Hari like?" still finds the jazz once it's moved out. "Forget ..." reaches here too, and the Memory
tab lists it as Long memory.

Kept in long.json beside the two files, with each entry's meaning (the decider's sentence numbers, as her history
keeps a turn's) in long-vectors.npz by the entry's hash, worked out once. Nothing of it leaves the PC."""
import hashlib
import json
import os
import re
import threading
import time

import numpy as np

import hermes_memory

FILE, VECTORS = "long.json", "long-vectors.npz"
MOST, ALIKE = 2, 0.35  # entries recalled into a turn at most, and how alike its words must be: more than history's
# 0.3 for whole turns, as an entry is a fact of a few words, and a loose one would put something odd in every prompt.
# With the real encoder (31 October): "what music does Hari like" 0.69 to his music, "call my sister" 0.36 to who she
# is in his contacts, "what's the weather" under 0.06 to everything
RECALL_CHARS = 240  # of them in the prompt, so a turn's prompt stays near its budget (tests/test_learning PromptSize)
# What's never moved out by herself while anything else can be: how you like things done, rules for her, your people
KEEP_CLOSE = re.compile(r"\b(?:prefers?|likes?|enjoys?|loves?|hates?|favou?rite|wants?|never|always|should|don'?t|"
                        r"do not|means|is called|calls?|"
                        r"sister|brother|mum|mother|dad|father|wife|husband|son|daughter|friend)\b", re.I)
_lock = threading.RLock()
_cache = {"path": None, "entries": None}
_vectors = {"path": None, "by_hash": None}


def _dir():
    return str(hermes_memory.get_memory_dir())


def _path():
    return os.path.join(_dir(), FILE)


def _key(text):
    return hashlib.sha1(" ".join(str(text).lower().split()).encode("utf-8")).hexdigest()[:16]


def entries():
    """[{"text", "about": "user" or "memory", "since"}], oldest first, read fresh when the file changed."""
    with _lock:
        path = _path()
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            _cache.update(path=path, entries=[])
            return []
        if _cache["path"] != path or _cache.get("stamp") != stamp or _cache["entries"] is None:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                found = [e for e in data if isinstance(e, dict) and str(e.get("text") or "").strip()] \
                    if isinstance(data, list) else []
            except (OSError, ValueError) as exc:
                print(f"  couldn't read her long memory: {exc!r}")
                found = []
            _cache.update(path=path, stamp=stamp, entries=found)
        return [dict(e) for e in _cache["entries"]]


def _write(found):
    os.makedirs(_dir(), exist_ok=True)
    path = _path()
    with open(path + ".part", "w", encoding="utf-8") as f:
        json.dump(found, f, ensure_ascii=False, indent=1)
    os.replace(path + ".part", path)
    _cache.update(path=path, stamp=os.path.getmtime(path), entries=found)


def keep(about, text, encode=None):
    """text kept in her long memory, about "user" (you) or "memory" (this PC), once: one already there (the same
    words, case aside) isn't kept twice. Its meaning is worked out now if encode is given. True if it's there."""
    text = " ".join(str(text or "").split())
    if not text or hermes_memory.memory_store._scan_memory_content(text):
        return False
    with _lock:
        found = entries()
        key = _key(text)
        if any(_key(e["text"]) == key for e in found):
            return True
        found.append({"text": text, "about": "memory" if about == "memory" else "user", "since": round(time.time())})
        _write(found)
    if encode is not None:
        _vector(text, encode)
    return True


def forget(text):
    """The entry text names taken out: by its words exactly (case aside), else the one entry that has them all. True
    if one went."""
    want = " ".join(str(text or "").lower().split())
    if not want:
        return False
    with _lock:
        found = entries()
        hits = [e for e in found if " ".join(e["text"].lower().split()) == want]
        if not hits:
            words = set(re.findall(r"\w+", want))
            hits = [e for e in found if words and words <= set(re.findall(r"\w+", e["text"].lower()))]
        if len(hits) != 1:
            return False
        _write([e for e in found if e is not hits[0]])
        return True


def _vectors_load():
    path = os.path.join(_dir(), VECTORS)
    if _vectors["path"] == path and _vectors["by_hash"] is not None:
        return _vectors["by_hash"]
    by_hash = {}
    try:
        with np.load(path) as data:
            by_hash = {k: data[k] for k in data.files}
    except (OSError, ValueError):
        pass
    _vectors.update(path=path, by_hash=by_hash)
    return by_hash


def _vector(text, encode):
    """The meaning of text, worked out once (encode: the decider's, about 16 ms) and kept by its hash."""
    key = _key(text)
    with _lock:
        by_hash = _vectors_load()
        v = by_hash.get(key)
        if v is None:
            v = np.asarray(encode(text), np.float32)
            by_hash[key] = v
            try:
                os.makedirs(_dir(), exist_ok=True)
                np.savez(os.path.join(_dir(), VECTORS), **by_hash)
            except OSError as exc:
                print(f"  couldn't keep her long memory's meanings: {exc!r}")
        return v


def nearest(words, encode, most=MOST, alike=ALIKE):
    """The entries closest in meaning to words, best first, up to most, at least alike (a dot product of the
    decider's unit vectors). [] with nothing kept, no encoder, or nothing close."""
    found = entries()
    if not found or encode is None or not str(words or "").strip():
        return []
    try:
        wanted = np.asarray(encode(words), np.float32)
        scores = [(float(_vector(e["text"], encode) @ wanted), e) for e in found]
    except Exception as exc:
        print(f"  couldn't look through her long memory: {exc!r}")
        return []
    best = sorted((s for s in scores if s[0] >= alike), key=lambda s: -s[0])
    return [e for _, e in best[:most]]


def recalled(words, encode, chars=RECALL_CHARS):
    """What a turn's prompt gets from here for words (siri.memory_block): a short block of the nearest entries, or
    ""."""
    lines, used = [], 0
    for e in nearest(words, encode):
        line = ("- " if e["about"] == "user" else "- (this PC) ") + e["text"]
        if used + len(line) > chars:
            break
        lines.append(line)
        used += len(line) + 1
    return "\n\nMore she remembers, recalled for these words:\n" + "\n".join(lines) if lines else ""


def move_out(store, target, need, encode=None, lately=()):
    """Room made in the small file for target (store: hermes_memory's) by moving entries out here, least like what
    you've been asking about lately (lately: the words of recent turns) first, and the ones to keep close (KEEP_CLOSE)
    last, until need characters are free. Without an encoder, the oldest first. Returns the entries moved, [] if
    nothing could be."""
    store.load_from_disk()
    found = list(store._entries_for(target))
    if not found or need <= 0:
        return []
    order = list(range(len(found)))
    if encode is not None and lately:
        try:
            asked = np.stack([np.asarray(encode(w), np.float32) for w in lately if str(w).strip()])
            scores = [float(np.max(asked @ np.asarray(encode(e), np.float32))) for e in found]
            order.sort(key=lambda i: scores[i])
        except Exception as exc:
            print(f"  couldn't rank her memory by what's been asked: {exc!r}")
    order.sort(key=lambda i: bool(KEEP_CLOSE.search(found[i])))  # a stable sort: the close ones go last
    sep = hermes_memory.memory_store.ENTRY_DELIMITER
    moving, freed = [], 0
    for i in order:
        if freed >= need:
            break
        moving.append(found[i])
        freed += len(found[i]) + len(sep)
    if freed < need:
        return []
    ops = [{"action": "remove", "old_text": e} for e in moving]
    result = hermes_memory.memory_tool(store, target=target, operations=ops)
    if not result.get("success"):
        print(f"  couldn't move entries out of her memory: {str(result.get('error'))[:120]}")
        return []
    for e in moving:
        keep(target, e, encode)
    print(f"  moved {len(moving)} out to her long memory, for room")
    return moving
