"""Your hand as the mouse, through the laptop's camera (29 October 2026, the owner's ask, after Apple-Watch-Cursor,
which points with a watch on the wrist and clicks with a finger-to-thumb tap: "I need this for my agent, to control it
with my hands when I turn it on").

- "Hey Harry, hand control on" (or "control the PC with my hand", "use my hand as the mouse"); "stop hand control" to
  stop. It stops by itself after NO_HAND seconds with no hand in front of the camera, and while the PC's locked.
- Point: the middle of your palm moves the pointer, not a fingertip, which moves as you pinch. Your hand moves within
  the middle of the camera's view (BOX), as in a mirror, and that's the whole screen; smoothed by a One Euro filter, so
  it's steady when you hold still and keeps up when you move.
- Pinch your thumb and index finger together: the left button's pressed, and let go as they part, so a quick pinch is
  a click and one held while you move is a drag. Your thumb and middle finger: a right click.

Seen by hands.py (MediaPipe's palm finder and its 21 points, on ONNX Runtime), followed from frame to frame from the
points it found the frame before, the way MediaPipe follows a hand: the palm finder only looks again when it's lost
it, so about 4 ms of CPU a frame. The camera's shared with her eyes (camera.Camera, held while this runs) and asked
for 30 frames a second while it does."""
import math
import re
import threading
import time

import numpy as np

BOX = (0.2, 0.15, 0.8, 0.75)  # the part of the camera's view your hand moves in, as shares of it: left, top, right,
# bottom. The whole screen in it: a hand moved across all of the view went off its edges before the pointer got there
PINCH, APART = 0.22, 0.32  # thumb tip to fingertip, in lengths of the palm (wrist to middle knuckle): pinched under
# PINCH, let go over APART, so a pinch that wavers round one line doesn't click twice
STILL_MS = 0.25  # seconds after a press the pointer holds where it was, so pinching doesn't nudge a click off its mark
SLOP = 30  # pixels the hand may move in that time and still be a click
NO_HAND = 60.0  # seconds with no hand seen before hand control stops by itself
FPS = 30  # frames a second asked of the camera while this runs
PALM = (0, 5, 9, 13, 17)  # the wrist and the four knuckles: their middle is where the pointer is
TRACK = (0, 5, 9, 13, 17, 1, 2)  # the points that make a palm for the next frame, in the palm finder's own order
WRIST, THUMB, INDEX, MIDDLE, MIDDLE_KNUCKLE = 0, 4, 8, 12, 9


class OneEuro:
    """The One Euro filter (Casiez, Roussel and Vogel, 2012): little smoothing as a hand moves fast, a lot as it holds
    still, so the pointer neither shakes nor lags."""

    def __init__(self, min_cutoff=1.2, beta=0.02, d_cutoff=1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.x = self.dx = self.t = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        x = np.asarray(x, dtype=np.float64)
        if self.x is None or self.t is None or t <= self.t:
            self.x, self.dx, self.t = x, np.zeros_like(x), t
            return x
        dt = t - self.t
        dx = (x - self.x) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self.dx = a_d * dx + (1 - a_d) * self.dx
        cutoff = self.min_cutoff + self.beta * float(np.linalg.norm(self.dx))
        a = self._alpha(cutoff, dt)
        self.x, self.t = a * x + (1 - a) * self.x, t
        return self.x

    def reset(self):
        self.x = self.dx = self.t = None


def palm_from(points):
    """A palm for hands.Hands.points to follow the hand in the next frame by, from this frame's 21 points: the box
    round the wrist, knuckles and thumb's base, made square, and those 7 points, as the palm finder gives them."""
    kp = np.asarray(points, dtype=np.float32)[list(TRACK)]
    (x1, y1), (x2, y2) = kp.min(axis=0), kp.max(axis=0)
    cx, cy, half = (x1 + x2) / 2, (y1 + y2) / 2, max(x2 - x1, y2 - y1) / 2
    return np.r_[cx - half, cy - half, cx + half, cy + half, kp.reshape(-1), 1.0].astype(np.float32)


def measure(points):
    """(where the pointer goes as shares of the camera's view, how near the thumb is to the index tip, to the middle
    tip), the last two in lengths of the palm."""
    p = np.asarray(points, dtype=np.float64)
    size = float(np.linalg.norm(p[MIDDLE_KNUCKLE] - p[WRIST])) or 1.0
    return p[list(PALM)].mean(axis=0), float(np.linalg.norm(p[THUMB] - p[INDEX])) / size, \
        float(np.linalg.norm(p[THUMB] - p[MIDDLE])) / size


class Pointer:
    """What a hand frame by frame does with the mouse (feed): the pointer moved, the left button pressed and let go,
    a right click. mouse: move(x, y), press(), release(), right_click(); screen: (width, height) in real pixels."""

    def __init__(self, mouse, screen, frame=(640, 480)):
        self.mouse, self.screen, self.frame = mouse, screen, frame
        self.smooth = OneEuro()
        self.down = None  # (when, where) the left button was pressed, while it's held
        self.right = False  # thumb and middle finger together now: one right click a pinch
        self.at = None  # where the pointer was last put

    def place(self, xy):
        """A point in the camera's view to the screen: inside BOX, mirrored, clamped to the screen."""
        w, h = self.frame
        x0, y0, x1, y1 = BOX
        nx = min(1.0, max(0.0, (xy[0] / w - x0) / (x1 - x0)))
        ny = min(1.0, max(0.0, (xy[1] / h - y0) / (y1 - y0)))
        sw, sh = self.screen
        return int(round((1 - nx) * (sw - 1))), int(round(ny * (sh - 1)))

    def feed(self, points, t):
        """One frame: the hand's 21 points in it, or None with no hand."""
        if points is None:
            self.lost()
            return
        where, index, middle = measure(points)
        x, y = self.smooth(self.place(where), t)
        x, y = int(round(x)), int(round(y))
        if self.down is None and index < PINCH and self.at is not None:
            x, y = self.at  # pinching now: pressed where it was pointing, the pinch itself never moves it
        elif self.down is not None and t - self.down[0] < STILL_MS and math.dist((x, y), self.down[1]) < SLOP:
            x, y = self.down[1]  # just pressed: held where it was, so it's a click there
        if (x, y) != self.at:
            self.mouse.move(x, y)
            self.at = (x, y)
        if self.down is None and index < PINCH:
            self.mouse.press()
            self.down = (t, (x, y))
        elif self.down is not None and index > APART:
            self.mouse.release()
            self.down = None
        if self.down is None and not self.right and middle < PINCH and index > APART:
            self.right = True
            self.mouse.right_click()
        elif self.right and middle > APART:
            self.right = False

    def lost(self):
        """No hand: a button that was down is let go, never left held."""
        if self.down is not None:
            self.mouse.release()
            self.down = None
        self.right = False
        self.smooth.reset()


class Mouse:
    """The real mouse, through pynput, as winplatform.click moves it, in real pixels."""

    def __init__(self):
        from pynput.mouse import Button, Controller
        import winplatform as win
        self.win, self.button, self.c = win, Button, Controller()

    def move(self, x, y):
        with self.win._real_pixels():
            self.c.position = (x, y)

    def press(self):
        self.c.press(self.button.left)

    def release(self):
        self.c.release(self.button.left)

    def right_click(self):
        self.c.click(self.button.right, 1)


def screen_size():
    """(width, height) of the main screen in real pixels."""
    import ctypes
    import winplatform as win
    with win._real_pixels():
        return ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)


class HandMouse:
    """Hand control while it runs (start, stop), on a thread of its own: the camera's frames as they come, your hand
    in each followed from the last, and Pointer doing what it does. on_stop(why): it stopped by itself."""

    def __init__(self, camera, hands=None, mouse=None, screen=None, on_stop=None, locked=None, clock=time.monotonic,
                 log=print):
        self.camera, self.finder, self.mouse, self.screen = camera, hands, mouse, screen
        self.on_stop, self.locked, self.clock, self.log = on_stop, locked, clock, log
        self.stopped, self.thread, self.why = threading.Event(), None, None

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        if self.running:
            return self
        self.stopped.clear()
        self.thread = threading.Thread(target=self._run, name="hand-mouse", daemon=True)
        self.thread.start()
        return self

    def stop(self, why=None):
        self.why = why
        self.stopped.set()

    def _run(self):
        hold = getattr(self.camera, "hold", None)
        try:
            if hold is not None:
                hold("hands", FPS)
            if self.finder is None:
                import hands
                self.finder = hands.Hands()
            mouse = self.mouse or Mouse()
            pointer = Pointer(mouse, self.screen or screen_size())
            self._follow(pointer)
            pointer.lost()
        except Exception as exc:
            self.log(f"  hand control stopped: {exc!r}")
            self.why = self.why or "something went wrong with it"
        finally:
            let_go = getattr(self.camera, "let_go", None)
            if let_go is not None:
                let_go("hands")
            if self.why and self.on_stop is not None:
                self.on_stop(self.why)

    def _follow(self, pointer):
        seen, last, track = self.clock(), 0.0, None
        while not self.stopped.is_set():
            if self.locked is not None and self.locked():
                self.why = "the PC's locked"
                return
            newest = self.camera.newest_bgr(after=last)
            if newest is None:
                if self.clock() - seen > NO_HAND:
                    self.why = "I couldn't see your hand for a minute"
                    return
                continue
            last, bgr = newest
            pointer.frame = (bgr.shape[1], bgr.shape[0])
            hand = self.finder.points(bgr, track) if track is not None else None
            if hand is None:  # lost, or not found yet: the palm finder looks
                palms = self.finder.palm_boxes(bgr)
                hand = self.finder.points(bgr, max(palms, key=lambda p: p[2] - p[0])) if palms else None
            if hand is None:
                track = None
                pointer.feed(None, last)
                if self.clock() - seen > NO_HAND:
                    self.why = "I couldn't see your hand for a minute"
                    return
                continue
            seen = self.clock()
            track = palm_from(hand["points"])
            pointer.feed(hand["points"], last)


# --------------------------------------------------------------------------- what's said about it
_HANDS = r"(?:hand|hands|gesture|gestures|finger|fingers)"
ON = re.compile(r"(?:(?:turn on|start|enable|switch on|begin|use|open)(?: the| my)? )?" + _HANDS +
                r" (?:control|mouse|mode|tracking|cursor|pointer)(?: on| mode)?|"
                r"(?:let me )?control (?:the |my |this )?(?:pc|computer|laptop|mouse|cursor|screen|you)? ?with "
                r"(?:my )?" + _HANDS + r"|use my " + _HANDS + r" (?:as|like) (?:the|a) (?:mouse|cursor|pointer)")
OFF = re.compile(r"(?:(?:turn off|stop|disable|end|switch off|exit|close|quit)(?: the| my)? " + _HANDS +
                 r" (?:control|mouse|mode|tracking|cursor|pointer)|" + _HANDS +
                 r" (?:control|mouse|mode|tracking|cursor|pointer) off)")
NOW = {"mouse": None, "camera": None, "say": None}


def quick(words, plain, gate=False):
    """A plan for hand control on or off, or None. With her name only: never from across the room."""
    t = plain(str(words or ""))
    if OFF.fullmatch(t):  # stopping's always safe, her name or not
        running = NOW["mouse"] is not None and NOW["mouse"].running
        if running:
            NOW["mouse"].stop()
        return {"steps": [], "say": "Okay, hand control's off." if running else "Hand control isn't on."}
    if gate == "cold":
        return None
    if ON.fullmatch(t):
        return {"steps": [], "say": start()}
    return None


def start():
    """Hand control on, with the camera her eyes use: what to say."""
    camera_ = NOW["camera"]() if callable(NOW["camera"]) else NOW["camera"]
    if camera_ is None:
        return "I can't, my camera isn't ready yet."
    if NOW["mouse"] is not None and NOW["mouse"].running:
        return "Hand control's already on. Pinch your thumb and index finger to click."
    import winplatform as win

    def stopped(why):
        if NOW["say"] is not None:
            NOW["say"](f"Hand control's off: {why}.")
    NOW["mouse"] = HandMouse(camera_, on_stop=stopped, locked=win.session_locked).start()
    return ("Hand control's on. Hold your hand up in front of the camera and move it to point; pinch your thumb and "
            "index finger to click, and hold the pinch to drag; thumb and middle finger for a right click. Say stop "
            "hand control when you're done.")


def bind(camera, say):
    """camera: the camera her eyes use (or a function giving it), say(line): a line said once she's free."""
    NOW["camera"], NOW["say"] = camera, say


# --------------------------------------------------------------------------- her step for the planner
LINE = ('{"do":"hand_control","on":true}  their hand in front of the laptop camera moves the mouse: palm to point, '
        'thumb and index finger pinched to click, held to drag, thumb and middle finger for a right click; '
        '"on":false to stop it')
WORDS = re.compile(r"\b(?:hand|hands|gesture|gestures|fingers?)\b.*\b(?:control|mouse|cursor|pointer|click)|"
                   r"\b(?:mouse|cursor|pointer)\b.*\b(?:hand|hands|fingers?)\b", re.I)


def _step(step):
    if str(step.get("on")).lower() in ("false", "off", "0"):
        if NOW["mouse"] is not None and NOW["mouse"].running:
            NOW["mouse"].stop()
        return "hand control off"
    start()
    return "hand control on"


def register():
    """Her step for it, in the registry: it takes the mouse, so planned without her name or after a read it's asked
    about first."""
    import toolbox
    if toolbox.get("hand_control") is None:
        toolbox.register("hand_control", effect="acts", asks_for=None, confirm="Should I let your hand move the mouse?",
                         handler=_step, line=LINE, background="never", gated_by="HAND_STEPS")


def prompt_block(text):
    """Her line for it, for the planner, only when the words may ask for it: "" for most."""
    return "\n\n" + LINE if WORDS.search(str(text or "")) else ""
