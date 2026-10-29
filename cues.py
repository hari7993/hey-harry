"""What she sees or hears that starts something (29 October 2026, the owner's ask): you come back to the laptop, you
wear your glasses, you clap twice in front of it, you snap your fingers while music plays. Each is a rule: what starts
it, what has to be true as well, and what to do, in the words you'd say to her ("work mode", "turn on light mode"),
done as if you'd said them to her by name. Off with Settings > Let her see you, which is off to start with.

To start with, the owner's own three: two claps in front of the laptop, work mode; a snap in front of it while music
plays, dream mode; your glasses on, light mode. Change them by saying so: "when I clap, open Spotify", "when I take
off my glasses, turn on dark mode", "when I come back to the laptop, read my messages", "forget the snap", "what do my
claps do?". Kept in %APPDATA%\\Hey Harry\\cues.json.

Seeing you is camera.py and hearing a clap claps.py, both on this PC, all the time while it's on: the camera's light
stays on, and the mic's own sound is listened to for claps on a stream of its own, as Windows' speech mode takes them
out. A snap is seen too (the owner's ask, 29 October: "my fingers snap on camera, then it needs to do it"): a sharp
sound that may have been one counts if your hand was up in front of the camera then (hands.py). Only a look at what you're wearing goes to the model that sees pictures (siri.camera_look): one small frame, for
a look rule, as you come back, as soon as you look different, and every couple of minutes while you're there; and
one when you ask her what she sees ("can you see me?", "what am I wearing?", siri.camera_answer)."""
import json
import os
import re
import threading
import time

import camera
import claps
import settings
import toolbox
from winplatform import APPDATA_DIR

PATH = os.path.join(APPDATA_DIR, "cues.json")
FIRST = [{"id": 1, "on": "clap", "do": "work mode", "need": ["here"]},
         {"id": 2, "on": "snap", "do": "dream mode", "need": ["here", "music"]},
         {"id": 3, "on": "look", "look": "wearing glasses", "do": "turn on light mode"}]
WHAT = {"clap": "two claps", "snap": "a snap", "back": "coming back to the laptop"}
TYPED = 1.5  # seconds after a key or the mouse in which a sharp sound is the keyboard's, not you
BUSY_FOR = 0.35  # seconds after someone talks, she does or you dictate in which no sharp sound starts
AGAIN = 3.0  # seconds before the same cue counts again
WELCOME_EVERY = 900.0  # seconds: welcomed back by the camera at most this often
HINT_EVERY = 300.0  # seconds: told at most this often that a cue came but what it needs wasn't so (no music on).
# On 29 October the owner snapped a dozen times with nothing playing on the laptop, heard each time, and saw nothing
EARS_RETRY = 60.0  # seconds before a mic that wouldn't open for claps is tried again
HAND_NEAR = 0.05  # a palm at least this share of the frame's width is a hand up in front of the laptop
HAND_FRAMES = 6  # frames round a sharp sound looked at for a hand, spread out: about 100 ms of CPU each
HAND_SCORE = 0.5  # how sure the palm finder is, at least (its own default; OpenCV Zoo's demo asks 0.6)

_lock = threading.Lock()
NOW = {"eyes": None, "ears": None, "hooks": None, "music": False, "fired": {}, "looks": {}, "welcomed": 0.0,
       "busy": 0.0, "ears_failed": (None, 0.0), "hands": None}


# --------------------------------------------------------------------------- the rules
def rules():
    """Every rule, as kept: the owner's three until they're changed."""
    with _lock:
        try:
            with open(PATH, encoding="utf-8") as f:
                kept = json.load(f)
            return [r for r in kept.get("rules", []) if isinstance(r, dict) and r.get("on") and r.get("do")]
        except (OSError, ValueError, AttributeError):
            return [dict(r) for r in FIRST]


def _keep(kept):
    with _lock:
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        with open(PATH + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"rules": kept}, f, indent=2)
        os.replace(PATH + ".tmp", PATH)


def add(on, do, look=None, need=()):
    """A new rule, in place of one for the same cue (and the same look): returns it."""
    kept = [r for r in rules() if not (r["on"] == on and r.get("look") == look)]
    rule = {"id": max([r.get("id", 0) for r in kept] + [0]) + 1, "on": on, "do": do,
            **({"look": look} if look else {}), **({"need": list(need)} if need else {})}
    _keep(kept + [rule])
    return rule


def forget(words):
    """Takes away the rules words name ("the snap", "my glasses"): the ones taken away."""
    t = str(words).lower()
    named = {on for on, rx in (("clap", r"\bclap"), ("snap", r"\bsnap"), ("back", r"\b(?:come|coming|sit|back)\b"))
             if re.search(rx, t)}
    kept, gone = [], []
    for r in rules():
        (gone if r["on"] in named or (r["on"] == "look" and _overlap(r.get("look"), t)) else kept).append(r)
    if gone:
        _keep(kept)
    return gone


def _overlap(look, t):
    look = set(re.findall(r"[a-z]{4,}", str(look or "").lower())) - {"wearing", "with", "having"}
    words = set(re.findall(r"[a-z]{4,}", t))
    return bool(look & (words | {w.rstrip("s") for w in words}) or {w.rstrip("s") for w in look} & words)


def said(rule):
    """A rule in a few words: "two claps in front of the laptop: work mode"."""
    if rule["on"] == "look":
        when = f"when you're {rule['look']}"
    else:
        when = WHAT.get(rule["on"], rule["on"]) + (" in front of the laptop" if "here" in rule.get("need", []) else "")
        when += " while music plays" if "music" in rule.get("need", []) else ""
    return f"{when}, {rule['do']}"


# --------------------------------------------------------------------------- what's said for them
_WHEN = r"(?:when(?:ever)?|if|each time|every time)"
_DO = r",? (?:then |please |you (?:can |should )?|just )?(?P<do>.{3,80})"
_AT = r"(?: in front of (?:the |my |this )?(?:laptop|pc|computer|camera|screen))?"
CLAP_SAID = re.compile(_WHEN + rf" i clap(?: my hands)?(?: twice| two times)?{_AT}" + _DO)
SNAP_SAID = re.compile(_WHEN + rf" i snap(?: my fingers)?{_AT}(?P<music> (?:while|when) (?:music|a song|songs|something)"
                       rf"(?: is)? (?:playing|plays|on|is on|running))?{_AT}" + _DO)
_VERB = (r"(?:turn|switch|start|open|enable|disable|put|play|go|set|launch|run|close|stop|pause|mute|unmute|dim|make|"
         r"show|change|lock|read|tell|say)")
WEAR_SAID = re.compile(_WHEN + r" i(?:'m| am)? (?P<verb>wear(?:ing)?|put on|have on|take off|remove|(?:am |'m )?not "
                       r"wear(?:ing)?|don'?t wear|wear no)(?: my| a| an| the| any)? (?P<what>[a-z][a-z ]{1,30}?),? "
                       rf"(?:then |please )?(?P<do>(?:{_VERB}\b.{{2,80}}|[a-z ]{{2,30}} mode))")
BACK_SAID = re.compile(_WHEN + r" i (?:come back|get back|sit (?:down )?(?:in front of|at)|come (?:in front of|to)|"
                       r"am back)(?: (?:to |at )?(?:the |my |this )?(?:laptop|pc|computer|camera|desk|screen))?" + _DO)
FORGET_SAID = re.compile(r"(?:forget|remove|delete|stop|cancel|drop|undo)(?: the| my| that)? (?P<what>.{3,40}?)"
                         r"(?: rule| cue| trigger)?s?")
LIST_SAID = re.compile(r"what (?:do|does) (?:my |a |the )?(?:claps?|snaps?|clapping|snapping)(?: (?:do|start))?|"
                       r"what are (?:my |your )?(?:camera |clap |snap |look )?(?:rules|cues)|what happens when i "
                       r"(?:clap|snap|wear .{2,30}|come back)")
_CAN = r"(?:(?:can|could|will|would) you |please |i want you to |you (?:should|can) )?"
_ALWAYS = r"(?: (?:all the time|always|from now on|through (?:the|my|your) (?:camera|webcam)|please))*"
EYES_ON = re.compile(_CAN + r"(?:(?:turn on|switch on|start|use|enable|open) (?:your |the |my )?(?:camera|webcam|eyes)"
                     r"(?: on me)?|(?:(?:always|keep|start) )?(?:watch|watching) me|keep an eye on me|"
                     r"(?:always |keep )?(?:look|looking) at me)" + _ALWAYS)
EYES_OFF = re.compile(_CAN + r"(?:(?:turn off|switch off|stop|disable|close) (?:your |the |my )?(?:camera|webcam|eyes)|"
                      r"stop (?:watching|looking at|seeing) me|(?:don't|do not) (?:watch|look at) me)" + _ALWAYS)
# Asking what she sees: answered from a picture now (siri.camera_answer), never one kept. siri.plain makes "can you
# see me?" "see me"
SEE_ME = re.compile(r"(?:(?:can|do) you )?see me(?: now| right now)?|are you (?:seeing|looking at) me(?: now)?|"
                    r"(?:what|who) (?:do you see|can you see|is) (?:on|through|in front of) (?:the|my|your) "
                    r"(?:camera|webcam)|what am i wearing|how do i look|am i (?:wearing|in front of) .{2,40}|"
                    r"(?:what|which) colou?r is my .{2,30}|look at me and tell me .{2,80}|is (?:anyone|someone|"
                    r"somebody) (?:there|behind me|in front of the (?:camera|laptop))")


def _plan(say):
    return {"steps": [], "say": say}


def quick(words, plain, gate=False):
    """A plan for what's said about these cues, or None: a rule taught or forgotten, what they are, the camera on or
    off. With her name only: never from across the room. plain: siri.plain."""
    t = plain(str(words or ""))
    if SEE_ME.fullmatch(t):  # "can you see me?" asks what she sees ("can you watch me?" asks her to): answered from
        # a look, her name or not. On 29 October "Hey, can you see me?" without it went to the model, which said her
        # eyes were off with the camera on and watching
        return _plan(look_now(str(words)))
    if gate == "cold":
        return None
    if EYES_ON.fullmatch(t):
        was = settings.get("cues")
        settings.put("cues", True)
        return _plan("I'm watching you, through the camera, all the time it's on, and listening for your claps." if was
                     else "Okay, I'll watch you through the camera all the time now, and listen for your claps.")
    if EYES_OFF.fullmatch(t):
        settings.put("cues", False)
        return _plan("Okay, my camera's off, and I'm not listening for claps.")
    if LIST_SAID.fullmatch(t):
        kept = rules()
        return _plan(("Here's what I do: " + "; ".join(said(r) for r in kept) + ".") if kept else
                     "Nothing yet. Tell me, like: when I clap, start work mode.")
    for on, rx in (("clap", CLAP_SAID), ("snap", SNAP_SAID), ("back", BACK_SAID)):
        m = rx.fullmatch(t)
        if m:
            need = ["here"] if on != "back" else []
            if on == "snap" and m["music"]:
                need.append("music")
            rule = add(on, m["do"].strip(), need=need)
            return _plan(f"Okay: {said(rule)}.{_off_note()}")
    m = WEAR_SAID.fullmatch(t)
    if m:
        without = m["verb"].startswith(("take", "remove", "not", "'m not", "am not", "don", "wear no"))
        thing = m["what"].strip()
        rule = add("look", m["do"].strip(), look=f"{'not ' if without else ''}wearing {thing}")
        return _plan(f"Okay: {said(rule)}. I'll check with a look now and then through the camera.{_off_note()}")
    m = FORGET_SAID.fullmatch(t)
    if m and re.search(r"\b(?:clap|snap|wear|glasses|specs|spectacles|camera|cue|rule|look)", m["what"]):
        gone = forget(m["what"])
        return _plan(f"Okay, I've forgotten {len(gone)}: " + "; ".join(said(r) for r in gone) + "." if gone else
                     "I don't have one like that.")
    return None


def _off_note():
    return "" if settings.get("cues") else " Turn on Let her see you in Settings, or say turn on your camera, and I will."


# --------------------------------------------------------------------------- watching and listening
def start(welcome, run, playing, look, see=None, mic=lambda: None, idle=None, notify=None, say=None):
    """Her eyes (camera.Eyes) and her ears for claps (claps.Ears), started once she's up. welcome(since): her
    welcome back; run(words, why): words done as if said to her; playing(): music on; look(rgb, looks): {look: bool}
    from the model that sees pictures; see(rgb, question): its answer to a question about a picture of you; mic():
    the mic to hear claps on (a sounddevice index, or None for Windows' own); idle(): seconds since a key or the
    mouse (winplatform.idle_seconds); say(line): a line said once she's free, as when a snap came with no music on."""
    hooks = {"welcome": welcome, "run": run, "playing": playing, "look": look, "see": see, "mic": mic, "idle": idle,
             "say": say}
    NOW["hooks"] = hooks
    eyes = camera.Eyes(on_back=_back, on_look=_looked, wants_look=lambda: any(r["on"] == "look" for r in rules()),
                       enabled=lambda: bool(settings.get("cues")), notify=notify)
    NOW["eyes"] = eyes

    def loop():
        while True:
            time.sleep(camera.EVERY)
            on = bool(settings.get("cues"))
            try:
                _ears(on)
            except Exception as exc:
                print(f"  claps: {exc!r}")
            if not on:
                eyes.tick()  # closes the camera, if it was on
                continue
            try:
                NOW["music"] = bool(playing())
            except Exception:
                NOW["music"] = False
            if NOW["ears"] is not None:
                NOW["ears"].hear_the_pc(NOW["music"])
            try:
                eyes.tick()
            except Exception as exc:
                print(f"  camera: {exc!r}")
    threading.Thread(target=loop, name="cues", daemon=True).start()


def _ears(on):
    """The mic's own sound for claps and snaps, on a stream of its own while Let her see you is on, closed after."""
    ears = NOW["ears"]
    if not on:
        if ears is not None:
            ears.stop()
            NOW["ears"] = None
        return
    why, when = NOW["ears_failed"]
    if ears is not None or (why and time.time() - when < EARS_RETRY):
        return
    try:
        NOW["ears"] = claps.Ears(_cue, device=NOW["hooks"]["mic"](), allowed=_allowed, on_maybe=_maybe_snap).start()
        NOW["ears_failed"] = (None, 0.0)
        print("  (listening for claps and snaps in the mic's own sound)")
    except Exception as exc:
        if why != str(exc):
            print(f"  claps: {exc}")
        NOW["ears_failed"] = (str(exc), time.time())


def _maybe_snap(at):
    """One sharp sound alone that may have been a snap (claps.Clapper.on_maybe), heard at at (time.monotonic): a snap
    if your hand was up in front of the camera then. Looked at off the listening thread."""
    if at is None or not any(r["on"] == "snap" for r in rules()):
        return
    camera_ = getattr(NOW["eyes"], "camera", None)
    if camera_ is None or not getattr(camera_, "on", False) or not hasattr(camera_, "around"):
        print("  (a sharp sound that may have been a snap, but my camera's not on to see your hand)")
        return
    threading.Thread(target=_hand_then, args=(camera_, at), name="snap-seen", daemon=True).start()


def _hand_then(camera_, at):
    time.sleep(max(0.0, at + 0.45 - time.monotonic()))  # the frames just after it too: one the PC played as well is
    # asked about straight away, not 0.9 s on
    frames = _spread(camera_.around(at - 0.6, at + 0.4), at)
    biggest = 0.0
    try:
        finder = NOW["hands"]
        if finder is None:
            import hands
            finder = NOW["hands"] = hands.Hands()
        for t, bgr in frames:
            for p in finder.palm_boxes(bgr, score=HAND_SCORE):
                share = (p[2] - p[0]) / bgr.shape[1]
                biggest = max(biggest, share)
                if share >= HAND_NEAR:
                    print(f"  (a sharp sound with your hand up in front of the camera, {t - at:+.1f} s from it, "
                          f"{share:.0%} of its width: a snap)")
                    _cue("snap")
                    return
    except Exception as exc:
        print(f"  couldn't look for your hand: {exc!r}")
        return
    hint = ""
    try:  # how near it came, for the log: the palm finder's best guess in them, and how light and sharp they were
        import cv2
        best = max((p for _, bgr in frames for p in finder.palm_boxes(bgr, score=0.05)), key=lambda p: p[18],
                   default=None)
        grays = [cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) for _, bgr in frames]
        light = sum(float(g.mean()) for g in grays) / max(1, len(grays))
        sharp = sum(float(cv2.Laplacian(g, cv2.CV_64F).var()) for g in grays) / max(1, len(grays))
        hint = (f"; its best guess {best[18]:.2f} sure, {(best[2] - best[0]) / frames[0][1].shape[1]:.0%} wide"
                if best is not None else "; no guess at all") + f"; light {light:.0f}, sharp {sharp:.0f}"
    except Exception:
        pass
    print(f"  (a sharp sound, but no hand up in front of the camera in {len(frames)} frames round it"
          + (f", the biggest {biggest:.0%} of its width" if biggest else "") + f"{hint}: not a snap)")


def _spread(frames, at, apart=0.15):
    """Up to HAND_FRAMES of frames, at least apart seconds from each other, those just before the sound first: a
    hand's sharpest as it's held ready to snap, blurred as it snaps."""
    picked = []
    for t, bgr in sorted(frames, key=lambda f: abs(f[0] - (at - 0.15))):
        if all(abs(t - p[0]) >= apart for p in picked):
            picked.append((t, bgr))
        if len(picked) == HAND_FRAMES:
            break
    return picked


def busy(talking):
    """What the listener hears, block by block: talking is True while someone talks, she does, or you dictate, and
    no clap or snap starts till a moment after."""
    if talking:
        NOW["busy"] = time.time() + BUSY_FOR


def _allowed():
    """For claps.Ears, as each piece of sound comes: None while you type (a sharp sound that started was a key's
    click), False while someone talks, else True."""
    idle = (NOW["hooks"] or {}).get("idle")
    if idle is not None and idle() < TYPED:
        return None
    return time.time() >= NOW["busy"]


def look_now(question):
    """What she says to a question about what she sees of you ("can you see me?"): from a picture now, by the model
    that sees pictures, or why she can't."""
    if not settings.get("cues"):
        return "Not right now, my camera's off. Say watch me, and I'll keep an eye on you through it."
    eyes, hooks = NOW["eyes"], NOW["hooks"]
    if eyes is None or not hooks or hooks.get("see") is None:
        return "My eyes are still starting up, ask me again in a moment."
    rgb = eyes.snap(keep=eyes.camera.on)
    if rgb is None:
        return f"I can't, my camera won't open: {eyes.failed or 'it gave me nothing'}."
    return hooks["see"](rgb, question)


def _cue(kind):
    """Two claps or a snap heard: the rules for it, done if what they need is so. Off the listening thread, as seeing
    whether you're there can open the camera for a moment."""
    now = time.time()
    if now - NOW["fired"].get(kind, 0.0) < AGAIN:
        return
    NOW["fired"][kind] = now
    threading.Thread(target=_cued, args=(kind,), daemon=True).start()


def _cued(kind):
    for rule in [r for r in rules() if r["on"] == kind]:
        need = rule.get("need", [])
        if "music" in need and not NOW["music"]:
            print(f"  ({WHAT[kind]}, but nothing's playing: not {rule['do']!r})")
            say = (NOW["hooks"] or {}).get("say")
            if say is not None and time.time() - NOW.get("hinted", 0.0) >= HINT_EVERY:
                NOW["hinted"] = time.time()
                say(f"That was {'a snap' if kind == 'snap' else WHAT[kind]}. {rule['do'].capitalize()} needs music "
                    f"playing on the laptop: play something and {'snap' if kind == 'snap' else 'clap'} again.")
            continue
        eyes = NOW["eyes"]
        if "here" in need and eyes is not None and not eyes.here():
            print(f"  ({WHAT[kind]}, but nobody's in front of the laptop: not {rule['do']!r})")
            continue
        _run(rule, WHAT[kind])


def _back(since, rgb):
    """You've come back to the laptop: her welcome back, at most every WELCOME_EVERY, then the rules for coming back,
    then the look rules with what she saw."""
    now = time.time()
    if now - NOW["welcomed"] >= WELCOME_EVERY:
        NOW["welcomed"] = now
        NOW["hooks"]["welcome"](since)
    for rule in [r for r in rules() if r["on"] == "back"]:
        _run(rule, WHAT["back"])
    if rgb is not None:
        _looked(rgb)


def _looked(rgb):
    """A picture of you: what each look rule asks of it, from the model that sees pictures, and the rules done whose
    look has just come true (not again while it stays so)."""
    looks = list(dict.fromkeys(r["look"] for r in rules() if r["on"] == "look" and r.get("look")))
    if not looks:
        return
    try:
        seen = NOW["hooks"]["look"](rgb, looks) or {}
    except Exception as exc:
        print(f"  camera look failed: {exc!r}")
        return
    for look in looks:
        if look not in seen:
            continue
        was, NOW["looks"][look] = NOW["looks"].get(look), bool(seen[look])
        if seen[look] and was is not True:
            for rule in [r for r in rules() if r["on"] == "look" and r.get("look") == look]:
                _run(rule, f"you're {look}")


def _run(rule, why):
    print(f"\n  (cue: {why}, so {rule['do']!r})")
    NOW["hooks"]["run"](rule["do"], why)


# --------------------------------------------------------------------------- her step for the planner
LINE = ('{"do":"camera","ask":"are they wearing glasses?"}  look at them through the laptop camera now and answer '
        'ask about what you see (what they wear or hold, whether anyone is there); the answer comes back to you. You '
        'can see them when Let her see you is on')
WORDS = re.compile(r"\b(?:camera|webcam|see me|watch me|look at me|looking at me|wearing|how do i look|in front of "
                   r"(?:the|my|your) (?:laptop|camera|screen)|glasses|specs|spectacles)\b", re.I)


def _step(step):
    return {"camera": look_now(str(step.get("ask") or "What do you see?"))}


def register():
    """Her step for it, in the registry: a look-up, what she sees coming back to the model to answer from."""
    if toolbox.get("camera") is None:
        toolbox.register("camera", effect="info", asks_for=None, confirm=None, handler=_step, line=LINE,
                         background="never", gated_by="CAMERA_STEPS")


register()


def prompt_block(text):
    """Her line for it, and what she can see by, for the planner, only when the words may be about it: "" else."""
    if not WORDS.search(str(text or "")):
        return ""
    on = settings.get("cues") or bool(getattr(getattr(NOW["eyes"], "camera", None), "on", False))  # as it is
    told = "; ".join(said(r) for r in rules()) or "nothing yet"
    return (f"\n\n{LINE}\nYou have eyes: the laptop's camera, with Let her see you {'on' if on else 'off'}"
            f"{'' if on else ' (they can say watch me to turn it on)'}. While it's on you watch them all the time, "
            f"welcome them back to the laptop, and do what they've taught you: {told}.")
