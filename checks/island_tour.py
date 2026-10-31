"""Her island, every scene of it, for the eye (30 October 2026, the owner's pictures of an iPhone's island): her
turns, the plugins' cards and the live activities (dream mode, meeting notes, hand control, showing you, her break, a
timer), small and opened, and her feelings and the moves between them. Not a test: it draws, for you to look at.

    .venv\\Scripts\\python checks\\island_tour.py            # stills and the moves, drawn off screen
    .venv\\Scripts\\python checks\\island_tour.py --stills   # the stills only (--moves: the moves only)
    .venv\\Scripts\\python checks\\island_tour.py --live     # the real island at the top right of the screen

Off screen, into build\\island-tour: each scene at rest in her paper, light and dark looks on a light and a dark
desktop (stills\\*.png and sheet-*.png), and the moves at 60 frames a second, if ffmpeg is on the PATH: all of them
(moves-<look>.mp4), each on its own (move-<look>-<name>.mp4, for a video made of them), and with --alpha each as a
WebM with its see-through edges kept. The island draws as it does on screen, its own code on a clock of the tour's,
so a second takes as long as it needs to draw. On the screen, the corner it's in is recorded too (live-paper.mp4).
It runs on an empty temp folder for her data, as the tests do, and never on hers.
"""
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# her real folders refused, and an empty one in their place, before anything of hers is imported (tests/support.py)
os.environ.setdefault("HEYHARRY_TESTING", os.pathsep.join((os.environ.get("APPDATA", ""),
                                                            os.environ.get("LOCALAPPDATA", ""))))
DATA = tempfile.mkdtemp(prefix="heyharry-tour-")
os.environ["APPDATA"] = os.environ["LOCALAPPDATA"] = DATA

import numpy as np  # noqa: E402

import bubble  # noqa: E402
import island  # noqa: E402
import island_face as face  # noqa: E402
import island_plugins as plugins  # noqa: E402
import settings  # noqa: E402
import vision  # noqa: E402

OUT = os.path.join(ROOT, "build", "island-tour")
LIGHT = ((0.86, 0.9, 0.97), (0.96, 0.93, 0.95))  # a desktop's wallpaper, top to bottom: Windows 11's light bloom
DARK = ((0.05, 0.07, 0.14), (0.11, 0.08, 0.17))  # and its dark one
FPS = 60


class Clock:
    """The tour's time, for the island's modules in place of the time module: it moves only as the tour says."""

    def __init__(self):
        self.now = time.time()

    def time(self):
        return self.now

    @staticmethod
    def perf_counter():
        return time.perf_counter()

    @staticmethod
    def strftime(fmt, *rest):
        return time.strftime(fmt, *rest)

    @staticmethod
    def localtime(*secs):
        return time.localtime(*secs)

    @staticmethod
    def monotonic():
        return time.monotonic()


CLOCK = Clock()
import focus  # noqa: E402

for module in (island, face, plugins, focus):
    module.time = CLOCK


class Bands:
    """The music's five bands as the visualizer would hear them, made up here from the tour's clock."""
    running = True

    @property
    def levels(self):
        t = CLOCK.now
        return [0.3 + 0.65 * abs(math.sin(t * f + i * 1.3)) * (0.6 + 0.4 * math.sin(t * 0.7 + i))
                for i, f in enumerate((2.3, 3.1, 4.4, 5.9, 7.7))]


# what the panels show, as island_plugins.Hub reads it (made up: no radios are switched, nothing is looked up)
HUB_DATA = {"wifi": True, "wifi_name": "Home Wi-Fi 5G", "bluetooth": True, "bt_name": "AirPods Pro", "clock": "",
            "volume": 62, "muted": False, "brightness": 45, "battery": (84, False),
            "cpu": 12, "ram": 58, "weather": {"temp": 24, "sky": "partly cloudy", "place": "Here"},
            "outputs": [{"id": "pods", "name": "AirPods Pro", "kind": "buds", "bus": "BTHENUM", "default": True,
                         "battery": 90},
                        {"id": "spk", "name": "Speakers", "kind": "builtin", "bus": "INTELAUDIO", "default": False,
                         "battery": None},
                        {"id": "jbl", "name": "JBL Flip 5", "kind": "speaker", "bus": "BTHENUM", "default": False,
                         "battery": 25}],
            "drives": [{"letter": "E", "label": "KINGSTON", "free": 21.4e9, "total": 31.9e9}]}
# what siri keeps that the island reads: the voice's loudness, her timers and her break
SIRI = SimpleNamespace(MIC_LEVELS=[0.0], SPEAK_LEVELS=[0.0], FOLLOW_UP=8.0, TIMERS=[], TIMERS_LOCK=threading.Lock(),
                       PAUSE={"until": 0.0, "mode": None}, CONTROLS=[None])
sys.modules["siri"] = SIRI


def make(root, theme="paper", style="panel", drop=True, scale=150):
    """A real DynamicIsland that never shows its window and whose plugins stay quiet: the tour says what's on."""
    for key, value in (("island_theme", theme), ("island_style", style), ("island_drop", drop),
                       ("island_scale", scale), ("popup", True), ("island_always", True), ("full_access", False)):
        settings.put(key, value)
    plugins.Runner.start = lambda self: None
    isl = island.DynamicIsland(root)
    isl._place = lambda area=None: None
    isl._front_icon = lambda size: None
    isl.visible_window = True
    isl.light = theme == "light"
    isl.t0 = CLOCK.now
    isl.runner.plugin("media").bands = Bands()
    isl.shelf = [os.path.join(ROOT, p) for p in ("README.md", os.path.join("docs", "banner.png"),
                                                 os.path.join("assets", "icon.png"), "checks")]
    for path in isl.shelf:  # the files' pictures fetched now, not while the tour draws
        isl.file_icons = getattr(isl, "file_icons", {})
        isl.file_icons[(path, round(34 * isl.k))] = island.art.file_icon(path, round(34 * isl.k))
    return isl


def clear(isl):
    """Nothing on: her turn over, no popups, nothing live, her panels closed, her eyes at rest."""
    isl.harry, isl.you, isl.popups, isl.popup, isl.lives = None, "", [], None, {}
    isl.hover, isl.pinned, isl.steps, isl.asked_at, isl.answered_at = False, None, None, None, None
    isl.eyes.mood, isl.shake_at, isl.flash, isl.beat_at = None, None, None, None
    isl.hub_page, isl.hub_data, isl.hub_month = None, None, None
    settings.put("island_status", "")
    focus.stop()
    isl.dirty = True


def beside(what):
    """Her eyes with what's beside them (island_status), as HUB_DATA has it."""
    def go(isl):
        settings.put("island_status", what)
        isl.hub_data = dict(HUB_DATA)
    return go


def frame(isl, dt=1 / FPS, level=None):
    """One frame as _tick has it, with no window: the scene worked out if it changed, all moved on dt, and drawn."""
    CLOCK.now += dt
    now = CLOCK.now
    t = now - isl.t0
    voice = level if level is not None else 0.35 + 0.3 * math.sin(t * 5.3) * math.sin(t * 1.7 + 1.0)
    SIRI.MIC_LEVELS[:] = [max(0.0, voice) * bubble.GAIN["mic"]]
    SIRI.SPEAK_LEVELS[:] = [max(0.0, voice) * bubble.GAIN["voice"]]
    if isl.dirty or (isl.popup is not None and isl.popup.until and now >= isl.popup.until and not isl.hover):
        isl._apply(now)
    isl._advance(now, dt)
    isl._moving(now)
    isl._draw(now)
    return isl.buf


def settle(isl, seconds=1.4):
    for _ in range(int(seconds * FPS)):
        frame(isl)


def picture(buf, box, back):
    """The window's premultiplied blue, green, red, alpha pixels in box over a wallpaper: one going from back[0] at
    the top to back[1], or a picture of one, (h, w, 3) 0 to 1. (h, w, 3) red, green, blue, 0 to 255."""
    x0, y0, x1, y1 = box
    px = buf[y0:y1, x0:x1].astype(np.float32) / 255
    if isinstance(back, np.ndarray):
        wall = back
    else:
        t = np.linspace(0.0, 1.0, y1 - y0, dtype=np.float32)[:, None, None]
        wall = np.asarray(back[0], np.float32) * (1 - t) + np.asarray(back[1], np.float32) * t
    rgb = px[..., 2::-1] + wall * (1 - px[..., 3:4])
    return (np.clip(rgb, 0.0, 1.0) * 255 + 0.5).astype(np.uint8)


def wallpaper(h, w, dark=False):
    """A desktop's wallpaper, h by w, as Windows 11's bloom is: soft light from the top middle over a wash of colour,
    blue at one side and violet at the other. (h, w, 3) 0 to 1."""
    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
    if dark:
        a, b, light = np.float32([0.04, 0.06, 0.15]), np.float32([0.13, 0.07, 0.2]), np.float32([0.18, 0.2, 0.36])
    else:
        a, b, light = np.float32([0.78, 0.86, 0.98]), np.float32([0.93, 0.85, 0.95]), np.float32([1.0, 1.0, 1.0])
    mix = np.clip(0.55 * xs + 0.45 * ys, 0.0, 1.0)[..., None]
    wall = a * (1 - mix) + b * mix
    glow = np.exp(-(((xs - 0.5) / 0.42) ** 2 + ((ys - 0.05) / 0.55) ** 2))[..., None] * (0.55 if not dark else 0.4)
    return np.clip(wall * (1 - glow) + light * glow, 0.0, 1.0).astype(np.float32)


def drawn_box(isl, pad=30):
    """Where the island and its words' bar were drawn this frame, with pad round it, in the window."""
    x0, y0, x1, y1 = isl.drawn or (0, 0, isl.cw, isl.ch)
    return max(0, x0 - pad), 0, min(isl.cw, x1 + pad), min(isl.ch, y1 + pad)


def save(path, rgb):
    with open(path, "wb") as f:
        f.write(vision.png(rgb))


# --------------------------------------------------------------------------- what's on, scene by scene
def tasks(rows, more=0):
    return plugins.Activity("tasks", "card", {"rows": rows, "more": more, "short": None, "badge": 0, "turn": None},
                            live=True)


def row(title, state, **kw):
    return dict({"key": title, "title": title, "lines": [], "status": "", "since": None, "state": state,
                 "progress": None, "buttons": [], "kind": "command"}, **kw)


def live(plugin, cls, **values):
    """A live activity as plugin's own data says, with values over it (dream's scene, a meeting's start)."""
    data = dict(cls_data(cls), **values)
    return plugins.Activity(plugin, "live", data, live=True)


def cls_data(cls):
    now = CLOCK.now
    return {
        "dream": {"glyph": "moon", "accent": "indigo", "label": "Dream mode", "title": "Night drive",
                  "short": "Night drive", "sub": "Snowman \u00b7 lofi beats", "mood": "dream", "aura": "breathe",
                  "buttons": [{"name": "next", "label": "Next scene"}, {"name": "exit", "label": "Exit"}]},
        "meeting": {"glyph": "record", "accent": "red", "label": "Meeting notes", "title": "Taking notes",
                    "sub": "Say \u201cstop the meeting notes\u201d for a recap", "since": now - 366, "wave": True},
        "hands": {"glyph": "hand", "accent": "teal", "label": "Hand control", "title": "Your hand is the mouse",
                  "sub": "Pinch to click, hold the pinch to drag", "since": now - 74,
                  "buttons": [{"name": "stop", "label": "Stop"}]},
        "guide": {"glyph": "pointer", "accent": "blue", "label": "Show me", "title": "Turn on Bluetooth",
                  "short": "Showing you", "sub": "Click where she's drawn, or say stop", "mood": "glasses",
                  "buttons": [{"name": "stop", "label": "Stop"}]},
        "break": {"glyph": "pause", "accent": "indigo", "label": "On a break", "title": "Not listening for my name",
                  "sub": "Say \u201cI\u2019m back\u201d with right Alt", "until": now + 1199, "mood": "sleepy"},
    }[cls]


def turn(state, text="", you=""):
    """Her turn at state, after you said you."""
    def go(isl):
        if you:
            isl.asked(you)
        isl.show(state, text)
    return go


def put(*makers):
    """What stays while it lasts, made as the scene starts (each a function giving an Activity), so its clock and
    its liveliness start then."""
    def go(isl):
        for make_act in makers:
            act = make_act()
            isl.lives[act.plugin] = act
    return go


def pop(make_act):
    def go(isl):
        isl.popups.append(make_act())
    return go


def timer(left, urgent=False):
    return lambda: plugins.Activity("timers", "timer", {"label": "Tea", "end": CLOCK.now + left, "total": 600.0,
                                                        "urgent": urgent}, live=True)


def cover(size=96):
    """A song's cover made up for the tour: a sunset, orange into pink, with a dark sun low in it."""
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32) / size
    rgb = np.stack([0.98 - 0.1 * ys, 0.45 - 0.25 * ys + 0.1 * xs, 0.3 + 0.45 * ys], axis=2)
    sun = np.hypot(xs - 0.5, ys - 0.68) < 0.18
    rgb[sun] = (0.32, 0.12, 0.3)
    return np.concatenate([rgb, np.ones((size, size, 1), np.float32)], axis=2).astype(np.float32)


COVER = cover()


def song(playing=True):
    return lambda: plugins.Activity("media", "media", {"title": "Snowman", "artist": "lofi beats", "app": "Spotify",
                                                       "playing": playing, "position": 42.0, "duration": 184.0,
                                                       "at": CLOCK.now, "art": COVER,
                                                       "tint": island.art.tint(COVER)}, live=True)


def note():
    return plugins.Activity("notifications", "notification", {"app": "WhatsApp", "app_id": "", "title": "Sam",
                                                               "text": "Running ten minutes late, save me a seat",
                                                               "phone": False}, mood="surprised")


def low():
    return plugins.Activity("battery", "battery", {"percent": 18, "charging": False, "event": "low"}, mood="sad")


def hub(page, focusing=False, shelf=True):
    """Her panels open on page, showing HUB_DATA, the focus timer going if focusing, the shelf empty unless shelf."""
    def go(isl):
        import datetime as dt
        today = dt.date.today()
        data = dict(HUB_DATA, month={"key": (today.year, today.month), "days": {3: 1, 12: 2, 21: 1, 28: 1},
                                     "next": {"title": "Lunch with Sam", "start": CLOCK.now + 3 * 3600}})
        isl.hub_data = data
        if not shelf:
            isl.shelf = []
        if focusing:
            focus.start(now=CLOCK.now)
        isl._hub_open(page)
    return go


def airpods():
    return plugins.Activity("devices", "device", {"event": "connected", "kind": "buds", "name": "AirPods Pro",
                                                  "label": "Connected", "battery": 90, "bus": "BTHENUM", "id": "pods"},
                            mood="happy")


def usb():
    return plugins.Activity("devices", "device", {"event": "drive", "kind": "drive", "name": "KINGSTON", "letter": "E",
                                                  "free": 21.4e9, "total": 31.9e9, "label": "USB drive (E:)",
                                                  "battery": None}, mood="surprised")


def focusing():
    focus.start(now=CLOCK.now)
    data = plugins.Focus(SimpleNamespace(post=lambda e: None, wanted={})).data(CLOCK.now)
    return plugins.Activity("focus", "live", data, live=True)


WORKING = lambda: tasks([row("Tidy the Downloads folder", "running", progress=0.4, status="2/5",  # noqa: E731
                             lines=["Moving the installers"], buttons=[{"name": "stop", "label": "Stop"}])])
WAITING = lambda: tasks([row("Install VLC", "waiting_yes", status="Needs you", lines=["Waiting for your yes"],  # noqa
                             buttons=[{"name": "approve", "label": "Approve"}, {"name": "deny", "label": "Deny"}])])
DONE = lambda: tasks([row("Back up my notes", "done", status="Done", progress=1.0)])  # noqa: E731


def scenes():
    """(name, set it up, opened too) for each still."""
    return [
        ("idle", lambda isl: None, False),
        ("idle-time", beside("time"), False),
        ("idle-weather-time-battery", beside("weather,time,battery"), False),
        ("listening", turn("listening", "Set a timer for ten minutes"), False),
        ("thinking", turn("thinking", "", "Set a timer for ten minutes"), False),
        ("speaking", turn("speaking", "Ten minutes, starting now.", "Set a timer for ten minutes"), False),
        ("error", turn("error", "I couldn't reach the model just now.", "What's the weather?"), False),
        ("timer", put(timer(215)), True),
        ("timer-last-seconds", put(timer(7.6, True)), True),
        ("working", put(WORKING), True),
        ("waiting-on-you", put(WAITING), True),
        ("done", put(DONE), False),
        ("music", put(song()), True),
        ("dream-mode", put(lambda: live("dream", "dream")), True),
        ("meeting-notes", put(lambda: live("meeting", "meeting")), True),
        ("hand-control", put(lambda: live("hands", "hands")), True),
        ("show-me", put(lambda: live("guide", "guide")), True),
        ("her-break", put(lambda: live("break", "break")), True),
        ("notification", pop(note), False),
        ("battery-low", pop(low), False),
        ("panel-controls", hub("controls"), False),
        ("panel-calendar", hub("calendar"), False),
        ("panel-calendar-focus", hub("calendar", focusing=True), False),
        ("panel-devices", hub("devices"), False),
        ("panel-shelf", hub("shelf"), False),
        ("panel-shelf-empty", hub("shelf", shelf=False), False),
        ("focus-timer", put(focusing), True),
        ("airpods-connected", pop(airpods), True),
        ("usb-drive", pop(usb), True),
    ]


def stills(root):
    """Each scene at rest (and opened, where it opens) in each look, on a light and a dark desktop, and a sheet of
    them all for each look."""
    folder = os.path.join(OUT, "stills")
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    for theme in ("paper", "light", "dark"):
        isl = make(root, theme)
        tiles = []
        for name, setup, opens in scenes():
            for opened in ((False, True) if opens else (False,)):
                clear(isl)
                settle(isl, 0.4)
                setup(isl)
                isl.hover = opened
                isl.dirty = True
                settle(isl, 1.3)
                isl.eyes.blink_at = None  # her eyes open for the picture, whatever her blinks were at
                frame(isl)
                label = name + (" (opened)" if opened else "")
                for back, back_name in ((LIGHT, "light-desk"), (DARK, "dark-desk")):
                    rgb = picture(isl.buf, drawn_box(isl), back)
                    save(os.path.join(folder, f"{theme}-{back_name}-{name}{'-opened' if opened else ''}.png"), rgb)
                    if back is (LIGHT if theme != "dark" else DARK):
                        tiles.append((label, rgb))
        save(os.path.join(OUT, f"sheet-{theme}.png"), sheet(tiles))
        print(f"  {theme}: {len(tiles)} scenes")


def sheet(tiles, cols=4, pad=18):
    """The tiles in a grid, each with its name under it, on grey."""
    tw = max(t[1].shape[1] for t in tiles)
    th = max(t[1].shape[0] for t in tiles)
    label = bubble.Text(22, 600)
    lh = label.line + 10
    rows = math.ceil(len(tiles) / cols)
    out = np.full((rows * (th + lh + pad) + pad, cols * (tw + pad) + pad, 3), 236, np.uint8)
    for i, (name, rgb) in enumerate(tiles):
        r, c = divmod(i, cols)
        x, y = pad + c * (tw + pad), pad + r * (th + lh + pad)
        h, w = rgb.shape[:2]
        out[y:y + h, x + (tw - w) // 2:x + (tw - w) // 2 + w] = rgb
        cover = label.render(name)
        ch, cw = cover.shape
        ty, tx = y + th + 4, x + 4
        part = out[ty:ty + ch, tx:tx + min(cw, tw - 8)].astype(np.float32)
        m = cover[:, :part.shape[1], None]
        out[ty:ty + ch, tx:tx + part.shape[1]] = (part * (1 - m) + 40 * m).astype(np.uint8)
    label.close()
    return out


# --------------------------------------------------------------------------- the moves
LIVE = [False]  # on the screen, where the island takes what's posted itself, five times a second


def send(*events):
    """What the plugins' thread would post (Runner.post), taken as the island takes it (_events)."""
    def go(isl):
        for event in events:
            isl.runner.post(event)
        if not LIVE[0]:
            isl._events()
    return go


def says(text):
    return lambda isl: isl.show("listening", text)


def hover(on):
    def go(isl):
        isl.hover, isl.dirty = on, True
        isl.hover_at = CLOCK.now
    return go


def hide(isl):
    isl.hide()


def feel(mood):
    return lambda isl: isl.react(mood)


def comes(plugin, kind):
    """A live activity of the tour's (cls_data) coming up, as its plugin would send it."""
    return lambda isl: send(("live", plugin, live(plugin, kind)))(isl)


def moves():
    """(name, seconds, [(at, what happens)]) for each move: her turn; dream mode coming in and opened; a timer's last
    seconds and its ring; a question answered and done; something gone wrong; a thank you; the other live ones. Each
    starts and ends with nothing on, her eyes alone, so one runs into the next."""
    asked = "Set a timer for ten minutes"
    return [
        ("her-turn", 9.5, [(0.7, says("")), (1.1, says("Set a timer")), (1.5, says("Set a timer for ten")),
                           (1.9, says(asked)), (2.7, turn("thinking", "", asked)),
                           (4.6, turn("speaking", "Ten minutes, starting now.")), (8.0, hide)]),
        ("dream-mode", 9.0, [(0.6, comes("dream", "dream")), (3.8, hover(True)), (6.6, hover(False)),
                             (7.6, send(("live", "dream", None)))]),
        ("timer", 9.5, [(0.4, lambda isl: send(("live", "timers", timer(7.0, True)()))(isl)),
                        (7.4, send(("live", "timers", None), ("fx", "ring")))]),
        ("waiting-then-done", 8.0, [(0.5, lambda isl: send(("live", "tasks", WAITING()))(isl)),
                                    (4.6, lambda isl: send(("live", "tasks", plugins.Activity(
                                        "tasks", "card", DONE().data, live=True, mood="happy")))(isl)),
                                    (7.0, send(("live", "tasks", None)))]),
        ("something-wrong", 5.5, [(0.5, turn("thinking", "", "What's the weather?")),
                                  (1.8, turn("error", "I couldn't reach the model just now.")), (4.6, hide)]),
        ("thank-you", 5.0, [(0.5, turn("speaking", "Any time.", "Thank you, Harry")), (0.6, feel("love")),
                            (3.8, hide)]),
        ("meeting-notes", 7.0, [(0.5, comes("meeting", "meeting")), (2.6, hover(True)), (5.0, hover(False)),
                                (5.9, send(("live", "meeting", None)))]),
        ("hand-control", 6.0, [(0.4, comes("hands", "hands")), (2.0, hover(True)), (4.0, hover(False)),
                               (4.8, send(("live", "hands", None)))]),
        ("show-me", 4.4, [(0.4, comes("guide", "guide")), (3.4, send(("live", "guide", None)))]),
        ("her-break", 4.4, [(0.4, comes("break", "break")), (3.4, send(("live", "break", None)))]),
        ("notification", 6.6, [(0.5, lambda isl: send(("show", note()))(isl))]),
    ]


# the reel's own: her hello at the start, and her goodbye at the end
HELLO = ("hello", 4.0, [(1.4, feel("happy"))])
GOODBYE = ("goodbye", 4.5, [(1.0, feel("love"))])


def encoder(path, w, h, alpha=False, rate=FPS):
    """ffmpeg taking raw frames on its stdin: an MP4 to watch, or a WebM with its see-through edges kept."""
    if alpha:
        codec = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "20", "-row-mt", "1",
                 "-auto-alt-ref", "0"]
    else:
        codec = ["-c:v", "libx264", "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p", "-movflags",
                 "+faststart"]
    return subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba" if alpha else "rgb24",
                             "-s", f"{w}x{h}", "-r", str(rate), "-i", "-", *codec, path], stdin=subprocess.PIPE)


def straight_rgba(buf, box):
    """The window's premultiplied blue, green, red, alpha in box as straight red, green, blue, alpha bytes."""
    x0, y0, x1, y1 = box
    px = buf[y0:y1, x0:x1].astype(np.float32)
    a = px[..., 3:4]
    rgb = np.where(a > 0, px[..., 2::-1] * 255 / np.maximum(a, 1), 0)
    return np.concatenate([np.clip(rgb, 0, 255), a], axis=2).astype(np.uint8)


def record(root, theme="paper", back=LIGHT, alpha=False, screen=False, which=None, scale=150):
    """Each move frame by frame at FPS into moves-<theme>.mp4 on a desktop, each on its own too (move-<theme>-
    <name>.mp4, for a video made of them), and with alpha as a WebM with its see-through edges kept. screen: as a
    1920 by 1080 screen, her island at the top of it on a wallpaper (wallpaper()), 30 frames a second, for the
    HyperFrames video of it. which: the moves, moves() unless said; scale: her size, percent."""
    if shutil.which("ffmpeg") is None:
        print("  no ffmpeg on the PATH: no moves")
        return
    isl = make(root, theme, scale=scale)
    k = isl.k
    top = isl.m if isl.drop else 0
    w = isl.cw - isl.cw % 2
    h = int(250 * k) - int(250 * k) % 2
    rate, x_in = FPS, 0
    if screen:
        w, h, rate = 1920, 1080, 30
        back = wallpaper(h, w, dark=theme == "dark")
        theme = f"screen-{theme}"
        x_in = (w - isl.cw) // 2  # the island's window in the middle of the screen's top
        base = (back * 255 + 0.5).astype(np.uint8)
        rows = min(h, isl.ch - top)
        under = back[:rows, x_in:x_in + isl.cw]
    box = (0, top, w, top + h) if not screen else (0, top, isl.cw, top + rows)

    def shot():
        if not screen:
            return picture(isl.buf, box, back)
        out = base.copy()
        out[:rows, x_in:x_in + isl.cw] = picture(isl.buf, box, under)
        return out
    film = encoder(os.path.join(OUT, f"moves-{theme}.mp4"), w, h, rate=rate)
    for name, seconds, script in which or moves():
        clear(isl)
        settle(isl, 0.6)
        one = encoder(os.path.join(OUT, f"move-{theme}-{name}.mp4"), w, h, rate=rate)
        clip = encoder(os.path.join(OUT, f"move-{theme}-{name}.webm"), w, h, alpha=True) if alpha else None
        start, todo, n = CLOCK.now, sorted(script, key=lambda s: s[0]), 0
        while CLOCK.now - start < seconds - 0.5 / rate:
            while todo and CLOCK.now - start >= todo[0][0]:
                todo.pop(0)[1](isl)
            frame(isl, 1 / rate)
            rgb = shot().tobytes()
            film.stdin.write(rgb)
            one.stdin.write(rgb)
            if clip is not None:
                clip.stdin.write(straight_rgba(isl.buf, box).tobytes())
            n += 1
        for enc in (one, clip):
            if enc is not None:
                enc.stdin.close()
                enc.wait()
        print(f"  {theme} {name}: {n} frames")
    film.stdin.close()
    film.wait()


# --------------------------------------------------------------------------- on the screen
def on_screen(root, theme):
    """The real island, its own window at the top right of the screen (her own stays in the middle), going through
    the moves on the real clock; with ffmpeg on the PATH, that corner of the screen recorded to live-<theme>.mp4."""
    import winplatform as win
    LIVE[0] = True
    for module in (island, face, plugins):
        module.time = time  # the real clock, as she has it
    for key, value in (("island_theme", theme), ("island_style", "panel"), ("island_drop", True),
                       ("island_align", "right"), ("island_scale", 100), ("popup", True), ("island_always", True),
                       ("full_access", False)):
        settings.put(key, value)
    plugins.Runner.start = lambda self: None
    isl = island.DynamicIsland(root)
    isl._front_icon = lambda size: None
    isl._hover_poll = lambda: None  # pointing at it is the tour's to say
    script, at = [], 1.5
    for name, seconds, steps in moves():
        script += [(at + t, step) for t, step in steps]
        script.append((at + seconds - 0.2, lambda isl: (clear(isl), isl._wake())))
        at += seconds
    left, top, right, bottom = win.work_area()
    film = None
    if shutil.which("ffmpeg"):  # the right of the top only, clear of her own island in the middle
        w, h = int(620 * isl.k) // 2 * 2, int(300 * isl.k) // 2 * 2
        film = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "gdigrab", "-framerate", "30", "-draw_mouse",
                                 "0", "-offset_x", str(right - w), "-offset_y", str(top), "-video_size", f"{w}x{h}",
                                 "-i", "desktop", "-t", str(at + 1), "-c:v", "libx264", "-crf", "16", "-pix_fmt",
                                 "yuv420p", os.path.join(OUT, f"live-{theme}.mp4")], stdin=subprocess.PIPE)
    began = time.time()

    def voice():
        t = time.time() - began
        level = max(0.0, 0.35 + 0.3 * math.sin(t * 5.3) * math.sin(t * 1.7 + 1.0))
        SIRI.MIC_LEVELS[:] = [level * bubble.GAIN["mic"]]
        SIRI.SPEAK_LEVELS[:] = [level * bubble.GAIN["voice"]]
        root.after(50, voice)

    def run(step):
        CLOCK.now = time.time()  # the scenes' clocks and timers start now
        try:
            step(isl)
            isl.dirty = True
            isl._wake()
        except Exception as exc:
            print(f"  tour: {exc!r}")
    for t, step in script:
        root.after(int(t * 1000), run, step)
    root.after(int((at + 1.5) * 1000), root.quit)
    voice()
    isl._wake()
    root.mainloop()
    isl.destroy()
    if film is not None:
        film.wait()
    print(f"  on screen, {theme}: {at:.0f} s")


def main():
    import tkinter as tk
    if "--live" in sys.argv:
        import winplatform as win
        win.prepare_gui()  # sharp on a scaled screen, as her own window is
    root = tk.Tk()
    root.withdraw()
    os.makedirs(OUT, exist_ok=True)
    try:
        if "--live" in sys.argv:
            on_screen(root, "paper")
            return
        if "--moves" not in sys.argv and "--reel" not in sys.argv:
            stills(root)
        if "--reel" in sys.argv:  # the moves on a screen, for the video made of them: all of them in her light
            # glass, and dream mode after dark, at 200% so she's big enough to see in a video
            record(root, "light", screen=True, which=[HELLO] + moves() + [GOODBYE], scale=200)
            record(root, "dark", screen=True, which=[m for m in moves() if m[0] == "dream-mode"], scale=200)
        elif "--stills" not in sys.argv:
            record(root, "paper", LIGHT, alpha="--alpha" in sys.argv)
            record(root, "dark", DARK, alpha="--alpha" in sys.argv)
    finally:
        root.destroy()
        shutil.rmtree(DATA, ignore_errors=True)
        print(f"  in {OUT}")


if __name__ == "__main__":
    main()
