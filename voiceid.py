"""Only your voice: she answers you, not other people, the TV or a video.

Each turn's speech becomes a voice print (speech.Speaker, 3D-Speaker's CAM++ through sherpa-onnx, on this PC), and
it's compared with yours from 10 sentences you read once ("Hey Jev, learn my voice"). The prints and recordings stay
in %LOCALAPPDATA%\\Hey Jev\\voice and never leave the PC.

Settings "voice_id":
    "off"       everyone counts, as before
    "learning"  after you've read the sentences: every turn is scored and logged, nothing is turned away, until
                there are enough of your own turns to set the levels from (see calibrate), then she switches to "on"
                if she can tell you apart, and says so either way
    "on"        a turn that isn't your voice is let go silently. Before the levels are set from your turns it's
                still learning: on 8 Oct "on" came from a test run, and the starting levels turned you away for 40 min

Measured on this PC (7 Oct 2026): a second or more of speech tells voices apart, your clips 0.64 to 0.90 against
Windows' David and Zira 0.06 to 0.39. Under a second it doesn't: a bare "Hey Jev" in their voices scored 0.84 to
0.97 against yours, since it's then the words that match, not the voice. So shorter turns aren't checked; ones
with her name, after a bare "Hey Jev" or just after she spoke count as yours, and others are let go while "on".
"""
import json
import os
import threading
import time

import numpy as np

import settings

MIN_SPEECH = 1.0  # seconds of speech a turn needs to be checked, see above
# Levels before calibration, from the clips above: with her name said (or straight after a bare "Hey Jev") a lower
# one, since the name is a good sign it's you; without it a higher one, so the room never reaches the model. Nobody
# is turned away on these (see learning): your real commands scored 0.33 to 0.54 against them on 8 Oct
NAMED, STRICT = 0.40, 0.50
LEVELS = {"named": (0.30, 0.55), "strict": (0.38, 0.62)}  # how far calibration may move each
# your own turns of a second or more, scored while learning, before she sets the levels: ones she acted on, with her
# name or without, since with "Answer without her name" on her name was in 1 of 150 turns and named ones never came
CALIBRATE_AFTER = 30
OWNER_PASS = 0.95  # she switches on by herself only if this many of your own turns pass at the levels she set
ROOM_PASS = 0.5  # and no more than this many of the phrases she let go as room talk, or she can't tell you apart
KEEP = 300  # scores the levels are set from, the latest, so they follow how you sound now
GROW_ABOVE = 0.15  # a turn this far over the named level, with her name, adds to her picture of your voice
MOST = 40  # prints kept: the 10 you read plus up to 30 from turns, the way "Hey Siri" fills in over time
ENROL_AGREE = 0.55  # a sentence whose print scores under this against the rest is read again; yours were 0.64 up
REDOS = 4  # sentences read again at most, so learning your voice always ends
SENTENCES = (  # short enough for the popup, and mostly what you say to her anyway
    "Hey Jev, open Chrome and play some music.",
    "Hey Jev, what's the weather like today?",
    "Hey Jev, set a timer for five minutes.",
    "Hey Jev, turn the volume down a little.",
    "Hey Jev, search YouTube for lofi songs.",
    "Remind me in twenty minutes to call Mum.",
    "Hey Jev, close this tab and go back.",
    "What's on my screen right now?",
    "Hey Jev, pause the video, please.",
    "Scroll down and read the next part to me.",
)
_lock = threading.Lock()


def folder():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Hey Jev", "voice")


def mode():
    value = settings.get("voice_id")
    return value if value in ("learning", "on") else "off"


class Profile:
    """Your voice prints: the ones from the sentences you read (fixed) and from turns since (rolling), the levels,
    and the scores logged while learning."""

    def __init__(self, path=None):
        self.path = path or folder()
        self.read = np.zeros((0, 0), np.float32)  # from the sentences
        self.grown = np.zeros((0, 0), np.float32)  # from turns that were plainly you
        self.named, self.strict = NAMED, STRICT
        self.calibrated = False  # the levels have been set from your own turns
        self.told = False  # she's said she can't tell your voice from the others here (see calibrate)
        self.logged = None  # the score log, read once (see scores)
        self.load()

    @property
    def ready(self):
        return len(self.read) > 0

    def load(self):
        try:
            data = np.load(os.path.join(self.path, "profile.npz"))
            self.read, self.grown = data["read"], data["grown"]
            self.named, self.strict = float(data["named"]), float(data["strict"])
            self.calibrated = bool(data["calibrated"])
            self.told = bool(data["told"]) if "told" in data.files else False
        except (OSError, KeyError, ValueError):
            pass

    def save(self):
        os.makedirs(self.path, exist_ok=True)
        tmp = os.path.join(self.path, "profile.tmp.npz")
        np.savez(tmp, read=self.read, grown=self.grown, named=self.named, strict=self.strict,
                 calibrated=self.calibrated, told=self.told)
        os.replace(tmp, os.path.join(self.path, "profile.npz"))

    def centre(self, read_only=False):
        """The middle of your prints. The ones grown from turns count for half at most, so a run of turns that
        weren't quite you can't pull it away from the sentences you read (PLAN: a guard against drift)."""
        unit = lambda c: c / (np.linalg.norm(c) or 1.0)  # noqa: E731
        c = unit(self.read.mean(axis=0))
        return c if read_only or not len(self.grown) else unit(c + unit(self.grown.mean(axis=0)))

    def score(self, print_, read_only=False):
        """How like your voice, -1 to 1 (cosine with the middle of your prints, or of the ones you read)."""
        return float(np.dot(self.centre(read_only), print_))

    def enrol(self, prints):
        """The prints from the sentences you read: a new picture of your voice, levels back to the start."""
        with _lock:
            self.read = np.asarray(prints, np.float32)
            self.grown = np.zeros((0, self.read.shape[1]), np.float32)
            self.named, self.strict, self.calibrated, self.told = NAMED, STRICT, False, False
            self.save()
            log = os.path.join(self.path, "scores.jsonl")
            if os.path.exists(log):
                os.remove(log)  # scores against the old picture don't count for the new one
            self.logged = []

    def grow(self, print_):
        with _lock:
            self.grown = np.concatenate([self.grown.reshape(-1, len(print_)), print_[None]])[-(MOST - len(self.read)):]
            self.save()

    def log(self, entry):
        os.makedirs(self.path, exist_ok=True)
        logged = self.scores()
        logged.append(entry)
        path = os.path.join(self.path, "scores.jsonl")
        if len(logged) > 2 * KEEP:  # only the latest are used: the file is cut back now and then, not on every phrase
            del logged[:-KEEP]
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(json.dumps(e) + "\n" for e in logged)
            return
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def scores(self):
        """The scores logged while learning, the latest: read from the file once and then kept, since reading it all
        again on every phrase, on the listening thread before the turn, took 25 ms at 166 lines and 48 ms at 14,000."""
        if self.logged is None:
            try:
                with open(os.path.join(self.path, "scores.jsonl"), encoding="utf-8") as f:
                    self.logged = [json.loads(line) for line in f if line.strip()][-KEEP:]
            except (OSError, ValueError):
                self.logged = []
        return self.logged

    def calibrate(self):
        """Once enough of your own turns are in, set the levels from them: about 97% pass without her name, and with
        it a little lower. A turn far under the rest of yours (a guest's or the TV's that she acted on) is left out,
        so a few can't drag the levels down and let other voices in. Then "on" if she can tell you apart: 95% of your
        turns pass, and no more than half of the room talk she let go. "unsure" if not (on 8 Oct a video scored 0.70
        to 0.84 and your commands 0.33 to 0.54): the levels are kept, for "only answer me", but she goes on
        answering everyone. None while there are too few."""
        recent = self.scores()[-KEEP:]
        mine = np.array([e["score"] for e in recent if e.get("mine")], np.float32)
        if len(mine) < CALIBRATE_AFTER:
            return None
        middle = float(np.median(mine))
        spread = max(0.05, 1.4826 * float(np.median(np.abs(mine - middle))))
        kept = mine[mine >= middle - 3 * spread]
        lo, hi = LEVELS["strict"]
        strict = min(hi, max(lo, float(np.percentile(kept, 3)) - 0.03))
        lo, hi = LEVELS["named"]
        named = min(hi, max(lo, strict - 0.08))
        room = np.array([e["score"] for e in recent if e.get("room")], np.float32)
        apart = (mine >= strict).mean() >= OWNER_PASS and (len(room) < CALIBRATE_AFTER
                                                           or (room >= strict).mean() <= ROOM_PASS)
        with _lock:
            self.named, self.strict, self.calibrated = named, strict, True
            self.save()
        return "on" if apart else "unsure"


def level(named, kind):
    """Which level a turn is held to: "named" with her name in it or just after a bare "Hey Jev", else "strict"."""
    return "named" if named or kind == "armed" else "strict"


def learning(profile):
    """Scoring and turning nobody away: "learning", or "on" before the levels were set from your own turns."""
    return mode() == "learning" or (mode() == "on" and not profile.calibrated)


def odd_one(prints):
    """Which of the sentences read is unlike the rest (its print against the middle of the others under
    ENROL_AGREE), to read again, or None. On 8 Oct two scored 0.39 and 0.43 against the other eight and were kept."""
    v = np.asarray(prints, np.float32)
    if len(v) < 3:
        return None
    total = v.sum(axis=0)
    alike = [float(p @ (total - p)) / (np.linalg.norm(total - p) or 1.0) for p in v]
    i = int(np.argmin(alike))
    return i if alike[i] < ENROL_AGREE else None


def judge(profile, score, speech_secs, named, kind):
    """(counts, why) for a turn with this score (None: not scored) and seconds of speech. counts is False only
    for a turn that isn't your voice while voice ID is on; while learning everything counts."""
    lvl = level(named, kind)
    if mode() == "off" or not profile.ready:
        return True, "off"
    if score is None or speech_secs < MIN_SPEECH:
        # too short to tell voices apart: her name, a bare "Hey Jev" before it, or just after she spoke means you
        if named or kind in ("armed", "follow_up") or learning(profile):
            return True, "short"
        return False, "short, without her name"
    limit = profile.named if lvl == "named" else profile.strict
    if score >= limit or learning(profile):
        return True, f"{score:.2f} {lvl}"
    return False, f"{score:.2f} under {limit:.2f} {lvl}"


def after_turn(profile, print_, score, speech_secs, named, kind, counted, result=None):
    """After a turn of a second or more. While learning its score is kept: as yours when she acted on it (result
    True, "playing" or "dictate": a command she did, a yes to her question), as room talk when she let it go
    (False), and once there are enough of yours the levels are set (calibrate). Returns "on" when that switched her
    on, "unsure" the first time she can't tell you apart, else None. A named turn plainly like the sentences you
    read adds to her picture of your voice."""
    if not profile.ready or score is None or mode() == "off" or speech_secs < MIN_SPEECH:
        return None  # under a second the words match, not the voice: kept out of the levels, as before
    if learning(profile):
        mine = bool(counted) and (result is True or result in ("playing", "dictate"))
        profile.log({"when": round(time.time()), "score": round(score, 3), "level": level(named, kind),
                     "secs": round(speech_secs, 2), "mine": mine, "room": result is False})
        said = profile.calibrate()
        if said == "on":
            settings.put("voice_id", "on")
            return "on"
        if said == "unsure" and not profile.told:
            with _lock:
                profile.told = True
                profile.save()
            return "unsure"
    if counted and named and print_ is not None and profile.score(print_, True) >= profile.named + GROW_ABOVE:
        profile.grow(print_)
    return None
