"""Her focus timer, a Pomodoro (30 October 2026, the owner's ask, after bloom's notch,
github.com/SehajveerSingh2005/bloom, whose calendar has one): "start a pomodoro", "focus for 50 minutes", "pause the
focus timer", "skip the break", "stop the pomodoro", "how long's left on my focus?".

Focus for 25 minutes (Settings, focus_minutes), a 5 minute break (break_minutes), and again, with a 15 minute break
after every fourth. The island shows it live, with Pause and Stop, and its calendar panel has its clock with Start. As
each part ends she chimes, says so once she's free, and the next begins by itself.

Kept in memory only, as her timers are: a session ends when she closes. Nothing here is sent anywhere."""
import re
import threading
import time

import settings
import toolbox

host = None  # siri, once bind() is called: plain(), parse_duration(), say_duration() and ANNOUNCE
LOCK = threading.Lock()
# the session: what part it's at (focus, break, or None for none), when that ends, what's left of it while paused,
# which round, how long a round's focus and break are, how long this part is, and the session's own number
NOW = {"phase": None, "until": 0.0, "left": 0.0, "paused": False, "round": 1, "focus": 1500, "rest": 300,
       "length": 0.0, "gen": 0}
WAKE = threading.Event()  # the thread watching the clock looks again at once: paused, skipped or stopped
LONG_EVERY, LONG_REST = 4, 900  # every fourth round ends in a long break, 15 minutes
MOST = 180 * 60  # the longest focus taken, as bloom's timer


def bind(module):
    global host
    host = module


def _minutes(key, fallback):
    try:
        return max(1.0, float(settings.get(key) or fallback))
    except (TypeError, ValueError):
        return float(fallback)


def state(now=None):
    """The session as the island shows it: {"phase", "until" (None while paused), "left", "length", "round",
    "paused"}, or None with none on."""
    now = time.time() if now is None else now
    with LOCK:
        if NOW["phase"] is None:
            return None
        left = NOW["left"] if NOW["paused"] else max(0.0, NOW["until"] - now)
        return {"phase": NOW["phase"], "until": None if NOW["paused"] else NOW["until"], "left": left,
                "length": NOW["length"], "round": NOW["round"], "paused": NOW["paused"]}


def start(seconds=None, rest=None, now=None):
    """A focus session from its first round, seconds of focus each (Settings' focus_minutes if not said) and rest
    seconds of break: what to say. One already on starts again."""
    now = time.time() if now is None else now
    focus = int(seconds) if seconds else int(_minutes("focus_minutes", 25) * 60)
    focus = max(60, min(MOST, focus))
    rest = int(rest) if rest else int(_minutes("break_minutes", 5) * 60)
    with LOCK:
        NOW.update(phase="focus", round=1, focus=focus, rest=max(60, rest), paused=False, length=float(focus),
                   until=now + focus, left=float(focus), gen=NOW["gen"] + 1)
        gen = NOW["gen"]
    WAKE.set()
    threading.Thread(target=_watch, args=(gen,), name="harry-focus", daemon=True).start()
    return f"Focus for {_say(focus)}. I'll tell you when it's time for a break."


def pause(now=None):
    """Paused where it is. True if it was going."""
    now = time.time() if now is None else now
    with LOCK:
        if NOW["phase"] is None or NOW["paused"]:
            return False
        NOW.update(paused=True, left=max(0.0, NOW["until"] - now))
    WAKE.set()
    return True


def resume(now=None):
    """Going again from where it was paused. True if it was paused."""
    now = time.time() if now is None else now
    with LOCK:
        if NOW["phase"] is None or not NOW["paused"]:
            return False
        NOW.update(paused=False, until=now + NOW["left"])
    WAKE.set()
    return True


def skip(now=None):
    """On to the next part straight away, a break or the next round: what it's at now, or None with none on."""
    now = time.time() if now is None else now
    with LOCK:
        if NOW["phase"] is None:
            return None
        _next(now)
        phase = NOW["phase"]
    WAKE.set()
    return phase


def stop():
    """The session over. True if one was on."""
    with LOCK:
        on = NOW["phase"] is not None
        NOW.update(phase=None, paused=False, gen=NOW["gen"] + 1)
    WAKE.set()
    return on


def _next(now):
    """The next part, with LOCK held: a break after focus, a long one after every LONG_EVERY rounds, and focus again
    after a break, one round on. What it says when it gets there by itself."""
    if NOW["phase"] == "focus":
        rest = LONG_REST if NOW["round"] % LONG_EVERY == 0 else NOW["rest"]
        NOW.update(phase="break", length=float(rest), until=now + rest, left=float(rest), paused=False)
        if rest == LONG_REST:
            return f"That's {NOW['round']} rounds. Take a proper break, {_say(rest)}."
        return f"Time for a break, {_say(rest)}."
    NOW.update(phase="focus", round=NOW["round"] + 1, length=float(NOW["focus"]), until=now + NOW["focus"],
               left=float(NOW["focus"]), paused=False)
    return f"Break's over. Round {NOW['round']}, {_say(NOW['focus'])} of focus."


def _watch(gen, clock=time.time):
    """The session's clock, on a thread of its own while it's on: each part's end, a chime and a word from her, and
    the next part. Asleep in between, woken by WAKE when it's paused, skipped or stopped."""
    while True:
        with LOCK:
            if NOW["gen"] != gen or NOW["phase"] is None:
                return
            wait = None if NOW["paused"] else NOW["until"] - clock()
        if wait is not None and wait <= 0:
            with LOCK:
                if NOW["gen"] != gen or NOW["phase"] is None or NOW["paused"] or NOW["until"] > clock():
                    continue
                line = _next(clock())
            _tell(line)
            continue
        WAKE.wait(None if wait is None else min(wait, 60.0))
        WAKE.clear()


def _tell(line):
    """A part's end: the timer's chime, and the line said once she's free."""
    try:
        import winplatform as win
        win.chime("timer")
    except Exception as exc:
        print(f"  focus: no chime ({exc!r})")
    announce = getattr(host, "ANNOUNCE", None)
    if announce is not None:
        announce.put(line)


def _say(secs):
    if host is not None and hasattr(host, "say_duration"):
        return host.say_duration(secs)
    return f"{int(round(secs / 60))} minutes"


def left_line(now=None):
    """How long's left, said: "14 minutes of focus left in round 2." """
    s = state(now)
    if s is None:
        return "There's no focus session on."
    part = "focus" if s["phase"] == "focus" else "your break"
    paused = ", paused" if s["paused"] else ""
    return f"{_say(s['left'])} of {part} left{paused}, round {s['round']}."


# --------------------------------------------------------------------------- what's said about it
WHAT = r"(?:pomodoro|focus (?:timer|session|clock)|focus)"
START = re.compile(r"(?:(?:start|begin|set|run|put on|do|give me|set up)(?: me)?(?: a| the| my| another| one)? "
                   r"(?:pomodoro|focus (?:timer|session|clock))(?: timer)?|pomodoro(?: timer)?|(?:let'?s|time to|"
                   r"help me) focus)(?: (?:for|of) (?P<time>.+))?|focus for (?P<time2>.+)")
PAUSE = re.compile(rf"(?:pause|hold)(?: the| my)? {WHAT}(?: timer)?")
RESUME = re.compile(rf"(?:resume|continue|unpause|carry on with)(?: the| my)? {WHAT}(?: timer)?")
SKIP = re.compile(r"skip(?: the| my| this)? (?:break|focus(?: round)?|round|pomodoro)")
STOP = re.compile(rf"(?:stop|end|cancel|quit|finish|turn off|kill)(?: the| my)? {WHAT}(?: timer)?|"
                  rf"{WHAT}(?: timer)? off")
LEFT = re.compile(rf"how (?:long|much time|many minutes)(?: is|'s| 's)? left (?:on|in|of)(?: the| my)? "
                  rf"{WHAT}(?: timer)?")


def _plan(steps=(), say=""):
    return {"steps": [dict(s) for s in steps], "say": say}


def quick(words, plain, gate=False):
    """A plan for the focus timer said plainly, with no model, or None. Stopping it is fine said any way; the rest only
    with her name, never from across the room."""
    t = plain(str(words or ""))
    if STOP.fullmatch(t):
        on = state() is not None
        return _plan([{"do": "focus", "action": "stop"}] if on else (), "Focus timer off." if on else
                     "There's no focus session on.")
    if gate == "cold":
        return None
    if LEFT.fullmatch(t):
        return _plan(say=left_line())
    if PAUSE.fullmatch(t):
        return _plan([{"do": "focus", "action": "pause"}], "Paused.")
    if RESUME.fullmatch(t):
        return _plan([{"do": "focus", "action": "resume"}], "Carrying on.")
    if SKIP.fullmatch(t):
        return _plan([{"do": "focus", "action": "skip"}], "Skipped.")
    m = START.fullmatch(t)
    if not m:
        return None
    asked = (m["time"] or m["time2"] or "").strip()
    secs = None
    if asked:
        secs = host.parse_duration(asked) if host is not None else None
        if not secs:
            return None  # "focus for my exam": not a time, so the model has it
    step = {"do": "focus", "action": "start"}
    if secs:
        step["minutes"] = round(secs / 60, 2)
    focus = max(60, min(MOST, int(secs or _minutes("focus_minutes", 25) * 60)))
    return _plan([step], f"Focus for {_say(focus)}. I'll tell you when it's time for a break.")


# --------------------------------------------------------------------------- her step for the planner
LINE = ('{"do":"focus","action":"start","minutes":25}  a focus timer, a Pomodoro: focus for minutes (25 if not '
        'said), then a short break, and again; "action" "pause", "resume", "skip" (on to the break or the next '
        'round) or "stop"')
WORDS = re.compile(r"\b(?:pomodoro|focus\w*|concentrat\w*|deep work|study session|work session)\b", re.I)


def _step(step):
    action = str(step.get("action") or "start").lower()
    if action == "stop":
        return "focus timer off" if stop() else "no focus session on"
    if action in ("pause", "resume", "skip"):
        if state() is None:
            raise RuntimeError("There's no focus session on. Say start a pomodoro to begin one")
        done = {"pause": pause, "resume": resume, "skip": skip}[action]()
        return f"focus {action}d" if done else f"focus wasn't {'going' if action == 'pause' else 'paused'}"
    try:
        minutes = float(step.get("minutes") or 0)
    except (TypeError, ValueError):
        minutes = 0.0
    start(minutes * 60 if minutes > 0 else None)
    return "focus timer on"


def register():
    """Her step for it, in the registry: her own timer, as a timer is, so it may run after a read and in a routine
    ("work mode" can start one)."""
    if toolbox.get("focus") is None:
        toolbox.register("focus", effect="own_data", asks_for=None, confirm=None, handler=_step, line=LINE,
                         read_safe=True, routine_ok=True, gated_by="FOCUS_STEPS")


register()


def prompt_block(text):
    """Her line for it, for the planner, only when the words may ask for it: "" for most requests."""
    return "\n\n" + LINE if WORDS.search(str(text or "")) else ""
