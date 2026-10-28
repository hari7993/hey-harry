"""What her helpers and background jobs are doing, live, in a corner of the screen (28 October 2026, after
Atticus's corner chip and live mini screen): a card for each one going, with its name or title, what it's doing now,
and a live picture of the window it works in (cards.py, Windows' own thumbnails), so you can watch it work behind
your other windows. A click on one brings its window to the front; the x puts the card away till the next job.
"Show me the helpers" and "hide the mini view" turn it on and off (settings "jobview", on unless you turn it off).

It only reads what's in memory (activity.snapshot and agent.JOBS), twice a second, never tasks.db."""
import threading
import time

import activity
import agent
import helpers
import winplatform as win

host = None
EVERY = 0.6
KINDS = ("agent", "research", "command", "code", "install")
STATE_DOT = {"running": "running", "waiting_yes": "waiting", "queued": "queued", "done": "done", "failed": "failed",
             "stopped": "failed"}
_card = [None]
_state = {"closed_for": set(), "thread": None, "shown": ()}
_lock = threading.Lock()


def bind(module):
    global host
    host = module


def on():
    return host.settings.get("jobview") is not False


def sections():
    """One section for each background job going: what the card shows."""
    out = []
    for item in activity.snapshot():
        key = item.get("key") or ""
        if not key.startswith("task:") or item.get("kind") not in KINDS:
            continue
        try:
            tid = int(key.split(":", 1)[1])
        except ValueError:
            continue
        try:
            name = helpers.name_of(tid)
        except Exception:
            name = None
        job = agent.JOBS.get(tid)
        pin = getattr(job, "pin", None) if job is not None else None
        if pin and not (win.window_exists(pin) and not win.minimised(pin)):
            pin = None
        title = name or item.get("title") or f"Task {tid}"
        if name and item.get("title", "").startswith(f"{name}:"):
            note_title = item["title"][len(name) + 1:].strip()
        else:
            note_title = ""
        note = item.get("note") or ""
        if item.get("total"):
            note = f"{note} \u00b7 step {item['step']} of {item['total']}".strip(" \u00b7")
        lines = [note_title] if note_title else []
        out.append({"key": tid, "title": title, "note": note, "dot": STATE_DOT.get(item.get("state"), "running"),
                    "thumb": pin, "lines": lines})
    return out[:3]


def _clicked(key):
    if key == "close":
        with _lock:
            _state["closed_for"] = {s["key"] for s in sections()}
        if _card[0] is not None:
            _card[0].hide()
        return
    job = agent.JOBS.get(int(key)) if str(key).isdigit() else None
    pin = getattr(job, "pin", None)
    if pin and win.window_exists(pin):
        win.bring_to_front(pin)


def _loop():
    import cards
    while True:
        time.sleep(EVERY)
        try:
            shown = sections() if on() else []
            keys = {s["key"] for s in shown}
            with _lock:
                closed = _state["closed_for"]
                if closed and not keys <= closed:  # a new job since the x: the card comes back
                    _state["closed_for"] = closed = set()
                visible = [s for s in shown if s["key"] not in closed]
            sig = tuple((s["key"], s["title"], s["note"], s["dot"], s["thumb"], tuple(s["lines"])) for s in visible)
            if sig == _state["shown"]:
                continue
            _state["shown"] = sig
            if visible:
                if _card[0] is None:
                    _card[0] = cards.Card(on_click=_clicked)
                _card[0].show(visible)
            elif _card[0] is not None:
                _card[0].hide()
        except Exception as exc:
            print(f"  job view: {exc!r}")
            time.sleep(5)


def start():
    """Its watch over the jobs, once."""
    if _state["thread"] is None:
        _state["thread"] = threading.Thread(target=_loop, name="harry-jobview", daemon=True)
        _state["thread"].start()


def show(want=True):
    """"Show me the helpers": on, and back if it was put away; off, it stays away till you turn it on."""
    host.settings.put("jobview", bool(want))
    with _lock:
        _state["closed_for"] = set()
        _state["shown"] = ()
    if not want and _card[0] is not None:
        _card[0].hide()
    going = bool(sections())
    if want:
        return "Here's what they're doing, in the corner." if going else \
            "Nothing's running in the background right now. I'll show it in the corner when something is."
    return "Okay, I've put the live view away."
