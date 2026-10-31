"""Her island at the top of the screen, the way Nixi (heynixi.com) has it: a black island with her eyes that
blink, look about and react, the app you're in and dots that move with your voice while she listens, and what
you're saying in a bar underneath, with the fillers and the words you put right struck out as you dictate.

Its plugins (island_plugins.py, from MaterialYou Dynamic Island) use it when she isn't busy: what she's working on
stays live, step by step, and opens into a card with Stop and Deny when you point at it (or click it to
keep it open); a notification pops up from the apps you pick, what's playing shows with its cover and its controls
when you point at it, the battery when you plug in or it runs low, and a running timer counts down. Light, dark and
AMOLED (pure black) themes, its place, size and corners, and the plugins are all in the Island tab.

Two styles (27 October 2026): the glass capsule, the default, floats a little under the top of the screen, see-through
with a hairline round it, and has her glowing eyes, the pill's own, looking at the mouse while it moves and glowing in
the colour of what she's doing, and nothing else beside them when nothing's on; and the black pill it was before,
drawn exactly as it was. A small cartoon face was tried in the capsule first and put away the same day: the owner found the
eyes more alive.

The drop (28 October 2026, the owner's pick from a MacBook's notch, on by default): the capsule and the answer card
hang from the top of the screen in the same glass, square where they meet it and curving into it each side, with no
gap above (_drop) and no hairline along the top. The bar of your words still floats under them.

Paper (29 October 2026, the owner's pick, her window's own look, now the theme to start with): white glass that's
all but solid, near-black words and eyes, and on an opened card the faint dots her window has. And pointing at what's
playing, a timer, the battery or a notification on the capsule opens it the way an iPhone's island opens (the owner's
pictures): what it's from and the time along its top with her eyes in the middle where a phone has its camera, then
big figures, a bar, and round buttons in the app's own colour (_live_head).

Live activities (30 October 2026, the owner's pictures of an iPhone's island: "add animation and emotion to all"):
dream mode, meeting notes, hand control, showing you where to click and her break each have one, as any plugin can
(island_plugins.Activity's "live" kind, _live): a glyph in its own colour, her eyes looking as it says, how long it's
been going or has to go, and opened, its words, a waveform and its buttons. The parts come out from behind her eyes as
a phone's island brings them out from behind its camera, and go back in (_capsule). She moves with what she feels: a
hop for a smile, a bump for news, two beats for hearts, a shake of the head at something gone wrong, as a phone's
island shakes at a wrong passcode, and a glow round her in the feeling's colour for a moment (_feel). What's on can
glow round her too, breathing (Layout.aura): dream mode in indigo, a question waiting on you, her turn as she listens
and thinks. A timer going off rings her (_fx).

Her light (30 October 2026, the owner's ask, after Glance's notch, joinglance.app, and their recording of its demo):
whatever comes lights her up in its colour, a line down her sides and along her bottom with a glow round it and, as
she hangs from the top of the screen, light running out along it either side; a notification in its app's colour,
the battery filling as far as it's charged, red at her corners for something wrong (island_light, _light_up). And
what you copy is acknowledged, as Glance's notch acknowledges a shortcut: "Copied" and the start of it (_copied).
The same evening, the rest of Glance's notch: files dragged over her open a place to drop them with the Shelf in it
(_drop_zone), paste, cut, undo, redo, save and a screenshot are answered as a copy is, the volume and the brightness
show in her as they change (_level), the panels have Recent notifications (_hub_alerts) and Keep awake, and a
notification peeks before it opens (_peek), with a light sweeping over her as she opens (_sweep).

It's one layered window drawn with numpy, like bubble.Island: clicks go through it except while you point at its
buttons, it never takes the focus, and it's left out of her screenshots, so the model never sees its buttons. Between
blinks nothing is drawn, and a long job moves once a second. A live activity moves for LIVELY_FOR seconds after it
comes, changes or is pointed at, then rests till its clock's next tick.
"""
import ctypes
import math
import os
import re
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes as wt

import numpy as np

import askbox
import bubble
import dictation
import island_art as art
import island_face as face
import island_light as lights
import island_plugins as plugins
import settings
import winplatform as win
from bubble import LOOKS, Spring, Text

BLUE, GREEN, ORANGE = (0.04, 0.52, 1.0), (0.19, 0.82, 0.35), (1.0, 0.62, 0.04)
VIOLET, CYAN, RED = (0.69, 0.42, 1.0), (0.39, 0.82, 1.0), (1.0, 0.27, 0.23)
INDIGO, TEAL, PINK = (0.37, 0.36, 0.9), (0.25, 0.78, 0.88), (1.0, 0.22, 0.37)  # a phone's own, as the rest are
# a live activity's colour by its name (island_plugins.Activity, kind "live")
ACCENTS = {"blue": BLUE, "green": GREEN, "orange": ORANGE, "violet": VIOLET, "cyan": CYAN, "red": RED,
           "indigo": INDIGO, "teal": TEAL, "pink": PINK}
THEMES = {  # body, the bar under it, words, quieter words, eyes, eyes glow, a border, its shadow
    "amoled": {"body": (0.0, 0.0, 0.0), "cap": (0.03, 0.03, 0.035), "text": (0.96, 0.96, 0.97),
               "muted": (0.56, 0.56, 0.59), "eyes": (0.97, 0.97, 0.98), "glow": True, "line": (0.24, 0.24, 0.26),
               "shadow": 0.32, "track": (0.25, 0.25, 0.27)},
    "dark": {"body": (0.1, 0.1, 0.11), "cap": (0.13, 0.13, 0.145), "text": (0.95, 0.95, 0.96),
             "muted": (0.6, 0.6, 0.63), "eyes": (0.96, 0.96, 0.97), "glow": True, "line": (0.3, 0.3, 0.32),
             "shadow": 0.3, "track": (0.3, 0.3, 0.32)},
    "light": {"body": (0.965, 0.965, 0.975), "cap": (1.0, 1.0, 1.0), "text": (0.07, 0.07, 0.08),
              "muted": (0.42, 0.42, 0.45), "eyes": (0.11, 0.11, 0.12), "glow": False, "line": (0.8, 0.8, 0.83),
              "shadow": 0.2, "track": (0.82, 0.82, 0.85)},
    # paper (29 October 2026, her window's look): white, near-black words and eyes, and on a card her window's dots
    "paper": {"body": (1.0, 1.0, 1.0), "cap": (1.0, 1.0, 1.0), "text": (0.04, 0.04, 0.04),
              "muted": (0.45, 0.45, 0.45), "eyes": (0.06, 0.06, 0.07), "glow": False, "line": (0.9, 0.9, 0.9),
              "shadow": 0.18, "track": (0.9, 0.9, 0.91), "dots": True},
}
# Her own turns: (how her eyes look, the dots' colour, what the dots do, the bars by the words)
HARRY = {
    "listening": ("open", BLUE, "voice", BLUE), "read": ("open", ORANGE, "voice", ORANGE),
    "again": ("side", ORANGE, "voice", ORANGE), "window": ("open", ORANGE, "ring", None),
    "dictating": ("open", GREEN, "voice", GREEN), "thinking": ("think", VIOLET, "busy", None),
    "looking": ("glasses", CYAN, "busy", None), "doing": ("focus", ORANGE, "busy", None),
    "finishing": ("focus", BLUE, "busy", None), "speaking": ("open", None, "her", None),
    "error": ("sad", RED, "still", None), "phone": ("open", BLUE, "still", None),
    "note": ("side", None, "still", None),
}
# The glass capsule's themes (27 October 2026): see-through ("fill", how opaque the glass is) with a hairline round it
# ("line" at "line_a"). AMOLED and dark are dark glass; light is light glass; paper is white glass all but solid,
# with her window's dots on a card ("dots", _dots). No blur: it would cost every frame.
GLASS = {
    "dark": {"body": (0.12, 0.12, 0.14), "cap": (0.12, 0.12, 0.14), "fill": 0.78, "text": (0.96, 0.96, 0.97),
             "muted": (0.66, 0.66, 0.7), "eyes": (0.97, 0.97, 0.98), "glow": True, "line": (1.0, 1.0, 1.0),
             "line_a": 0.18, "shadow": 0.3, "track": (0.34, 0.34, 0.37)},
    "light": {"body": (0.98, 0.98, 0.99), "cap": (0.98, 0.98, 0.99), "fill": 0.85, "text": (0.07, 0.07, 0.08),
              "muted": (0.38, 0.38, 0.41), "eyes": (0.11, 0.11, 0.12), "glow": False, "line": (0.0, 0.0, 0.0),
              "line_a": 0.12, "shadow": 0.2, "track": (0.8, 0.8, 0.83)},
    # solid (30 October 2026): at 0.97 the capsule took the wallpaper's colour, pink on a red one, the owner's screenshot
    "paper": {"body": (1.0, 1.0, 1.0), "cap": (1.0, 1.0, 1.0), "fill": 1.0, "text": (0.04, 0.04, 0.04),
              "muted": (0.45, 0.45, 0.45), "eyes": (0.06, 0.06, 0.07), "glow": False, "line": (0.0, 0.0, 0.0),
              "line_a": 0.1, "shadow": 0.18, "track": (0.9, 0.9, 0.91), "dots": True},
}
# Her eyes in the capsule for how a task is going (face.MOODS), as the pill's _compact has them: ^ ^ when done,
# drooping when it failed, wide open while it waits on you, else open and glancing about. Not "focus" while one
# runs: its sway never rests, a frame every 16 ms for as long as a job lasts. Her own turns take HARRY's
TASK_LOOKS = {"done": "happy", "failed": "sad", "waiting_yes": "surprised"}
# the capsule's eyes glow in the colour of what's going on: a reaction while it lasts (done, a notification,
# something wrong), else her turn's or the task's own. White eyes, a tinted glow round them: the eyes stay hers
MOOD_TINTS = {"happy": GREEN, "surprised": BLUE, "sad": RED, "x": RED}
TINT = 0.75  # how much of the glow is the tint, the rest the eyes' own white: a wash, not a coloured ring (at 0.6
# the listening blue read as white in the previews)
GAZE_HOLD = 3.0  # seconds the pointer stays still before her eyes go back to glancing about on their own
GAZE_REACH = 220  # logical px from her eyes at which she looks as far as she can that way
BLINKS = {"open", "surprised", "focus", "think", "glasses", "headphones", "sleepy", "side"}  # as face.Eyes blinks
MIC_STATES = {"listening", "read", "again", "dictating"}
HINTS = ("Say \u201cstop", "Say \"stop", "Go ahead", "Let go")  # the window's hints, not words you said
# what the answer card's top line says she's at (_panel_harry); while she works, what she's doing, if it says
PANEL_STATUS = {"listening": "Listening", "window": "Still listening", "dictating": "Dictating", "read": "Read this out",
                "again": "Once more", "thinking": "Thinking", "looking": "Looking at the screen", "doing": "Working",
                "finishing": "Finishing", "error": "Something went wrong", "phone": "Phone"}
CLICKABLE = ("media", "notification", "card", "hub", "device", "drop")  # what takes clicks while you point at it: all else
# lets them through, and her eyes alone (idle) only while a click on them opens the panels (_hub_open)
REST = 0.5  # seconds the pointer rests on Approve before a click on it counts: an agent's click moves it there first
# How she moves with a feeling (30 October 2026): a hop for a smile, a bump outwards for news, two beats for hearts,
# a shake of the head for something gone wrong. KICKS: what each gives her width and height, logical px a second,
# into the springs that size her; a few px of give that settles as the island always does
MOOD_MOTION = {"happy": "hop", "love": "beat", "surprised": "pop", "sad": "shake", "x": "shake"}
KICKS = {"hop": (0.0, 120.0), "pop": (190.0, 85.0), "beat": (70.0, 95.0)}
MOOD_FLASH = {"happy": GREEN, "love": PINK, "surprised": BLUE, "sad": RED, "x": RED}  # the glow a feeling gives her
COPY_LIGHT = (0.55, 0.76, 1.0)  # her light for a copy, a pale blue, as Glance's for a shortcut (_light_for)
# each shortcut's answer (_copied, 30 October 2026, after Glance's "every shortcut, acknowledged"): its word and the
# colour of its glyph and her light; one said again soon after counts up (REPEATS)
SHORTCUTS = {"copy": ("Copied", BLUE), "cut": ("Cut", (1.0, 0.42, 0.36)), "paste": ("Pasted", BLUE),
             "undo": ("Undo", ORANGE), "redo": ("Redo", ORANGE), "save": ("Saved", GREEN),
             "screenshot": ("Screenshot", VIOLET)}
REPEATS = ("paste", "undo", "redo", "save")
SHAKE_FOR, FLASH_FOR, BEAT_GAP = 0.6, 0.9, 0.3  # seconds a shake and a flash last, and between the two beats
# The glow round her (Layout.aura) is her shadow in a colour, made AURA times as strong: under and round her, never
# over what's on her. Breathing, it goes from AURA_LOW to all of it and back every 2.6 s
AURA, AURA_LOW = 0.6, 0.4
# her turn's glow, the colour of her dots (HARRY), breathing while she's at it
AURA_TURNS = {"listening": "steady", "dictating": "steady", "thinking": "breathe", "looking": "breathe",
              "doing": "breathe", "finishing": "breathe", "error": "steady"}
LIVELY_FOR = 20.0  # seconds a live activity moves after it comes, changes or is pointed at: then it rests
MOVING = ("moon", "record", "hand", "pointer", "timer")  # the glyphs (face.GLYPHS) that move while they're lively
# The panels (30 October 2026, after bloom's notch): opened by a click on her eyes, one at a time, the wheel going on
# to the next; each with its glyph in the tabs along their top and its colour in her eyes' glow
HUB_PAGES = ("controls", "calendar", "today", "alerts", "devices", "shelf")
HUB_GLYPHS = {"controls": "controls", "calendar": "calendar", "today": "weather", "alerts": "bell",
              "devices": "headphones", "shelf": "tray"}
HUB_TINTS = {"controls": BLUE, "calendar": RED, "today": CYAN, "alerts": ORANGE, "devices": TEAL, "shelf": VIOLET}
# the shelf by kind, as Glance's: what's a picture, and the rest are documents (_hub_shelf)
PICTURES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic", ".svg", ".tif", ".tiff", ".ico")
HUB_LINGER = 0.9  # seconds the pointer's away from the open panels before they close
DEVICE_WORDS = {"buds": "Earbuds", "headphones": "Headphones", "speaker": "Speaker", "jack": "Wired", "drive": "Drive",
                "builtin": "This PC", "display": "Display"}
# what can sit beside her eyes (island_status), as bloom's; the time too, if you pick it (30 October 2026: the owner
# had it off on 27 October, and asked for it back as a choice)
STATUS_WIDGETS = ("time", "weather", "battery", "cpu", "ram")
SLIDER_TINTS = {"volume": BLUE, "brightness": (1.0, 0.62, 0.1)}  # Controls' sliders, filled in these
PANEL_FILL = 0.96  # how opaque the glass is on a panel or a card, with words on it (_glass)
SHELF_MOST = 10  # files the shelf keeps, the newest first, as bloom's


class _ULWINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hdcDst", wt.HDC), ("pptDst", ctypes.POINTER(wt.POINT)),
                ("psize", ctypes.POINTER(wt.SIZE)), ("hdcSrc", wt.HDC), ("pptSrc", ctypes.POINTER(wt.POINT)),
                ("crKey", wt.DWORD), ("pblend", ctypes.POINTER(bubble._BLEND)), ("dwFlags", wt.DWORD),
                ("prcDirty", ctypes.POINTER(wt.RECT))]


# Only the part that changed goes to Windows: the whole window's picture every frame took 20 ms or more
_ULWI = bubble._api(bubble._user32.UpdateLayeredWindowIndirect, [wt.HWND, ctypes.POINTER(_ULWINFO)], wt.BOOL)


def _union(a, b):
    """Two boxes (x0, y0, x1, y1) as one that holds both; either may be None."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def _drop(xs, ys, x0, W, H, r, y_top, s):
    """A box hanging from the top of the screen at y_top, as signed distances: square where it meets the edge,
    its bottom corners round (r), and each side curving out into the edge over s px, a notch's shoulders. Nothing
    above y_top: a screen over this one would show it."""
    body = face.rbox(xs, ys, x0 + W / 2, y_top + (H - r) / 2, W / 2, (H + r) / 2, r)  # its top corners above
    # between its side and the edge, less a circle; the square runs on into the box as far again, so where the two
    # meet there's no seam inside her for the light to show through (30 October 2026)
    for corner in ((x0 - s, x0 + W + s) if s > 0 else ()):
        side = np.maximum(face.rbox(xs, ys, x0 if corner < x0 else x0 + W, y_top + s / 2, s, s / 2, 0.0),
                          -face.circle(xs, ys, corner, y_top + s, s))
        body = np.minimum(body, side)
    return np.maximum(body, y_top - ys)


def _spread(part, i0, i1):
    """A patch worked out with its alike middle columns as the one at i0, back to its full width."""
    h, n = part.shape[0], part.shape[1] - 1 + (i1 - i0)
    out = np.empty((h, n), part.dtype)
    out[:, :i0] = part[:, :i0]
    out[:, i0:i1] = part[:, i0:i0 + 1]
    out[:, i1:] = part[:, i0 + 1:]
    return out


class Layout:
    """What the island holds in one scene: its size, how to draw it, the words under it, and where to click.
    eyes: her expression in it, if her eyes are in it; wander: they may look about. press: for a card, what each
    hot place does, (plugin, what, data, careful). rate: the frames a second it asks for at rest. aura: (colour,
    "breathe" or "steady"), a glow round her in what's on's colour (_aura). lively: (till when, rate), more frames a
    second while it moves, after it comes (LIVELY_FOR); its glow breathes only till then."""
    __slots__ = ("key", "kind", "w", "h", "radius", "draw", "cap", "hot", "eyes", "animated", "rate", "wander",
                 "press", "face", "aura", "lively")

    def __init__(self, key, kind, w, h, draw, radius=None, cap=None, hot=(), eyes=None, animated=False, rate=0,
                 wander=True, press=None, face=False, aura=None, lively=None):
        self.key, self.kind, self.w, self.h, self.draw, self.radius = key, kind, w, h, draw, radius
        self.cap, self.hot, self.eyes, self.animated, self.rate = cap, list(hot), eyes, animated, rate
        self.wander, self.press = wander, dict(press or {})
        self.face = face  # the capsule: her eyes in it look at the mouse while it moves, _follow
        self.aura, self.lively = aura, lively


class Caption:
    """The bar under the island with the words in it. live: the part that moves (the bars that go with your
    voice), drawn again each frame over a kept picture of the rest; live_box: where that part is."""
    __slots__ = ("key", "w", "h", "draw", "animated", "live", "live_box")

    def __init__(self, key, w, h, draw, animated=False, live=None, live_box=None):
        self.key, self.w, self.h, self.draw, self.animated = key, w, h, draw, animated
        self.live, self.live_box = live, live_box


class DynamicIsland:
    """The popup: show(state, text), caption(text), hide(delay), close() and visible as bubble.Island has them,
    and react(mood) for her eyes, reload() after a setting changed, preview() for a look at a notification."""
    MARGIN, GAP = 20, 9  # logical px: room round it in the window for the shadow, and from it to the words
    FACE, WAVE, COMPACT_H = (118, 80), (176, 44), 34
    CARD_W, CAP_MAX_W, CAP_PAD_X, CAP_PAD_Y = 380, 700, 16, 11
    EYES, SMALL_EYES = 19, 13
    CARD_PAD, ROW_GAP, BUTTON_H = 14, 9, 22  # a card's rows: round them, between them, and their buttons' height
    # the capsule (27 October 2026): how far it floats under the top at least, how wide its row gets at most, and
    # the glass cards' corners. Her eyes are the pill's small ones (SMALL_EYES), as big against its height
    FLOAT, CAPSULE_MAX_W, GLASS_CORNER = 10, 330, 18
    # the drop (28 October 2026): its bottom corners while nothing's on, and the curves into the top of the screen
    DROP_CORNER, DROP_SHOULDER = 12, 6
    # the answer card (28 October 2026): its width, its tallest, and how long it stays once she's answered, in ms
    PANEL_W, PANEL_MAX_H, PANEL_LINGER = 360, 380, 8000
    panel = False  # her turns in the answer card, else as the capsule or pill has them
    drop = False  # hanging from the top of the screen like a notch, with no gap above it (_read_settings)
    asked_at = answered_at = None  # this turn: when your words ended and when she answered, for the card's "2.23 s"
    receipt = None  # (Learned or Remembered, what, when): a line under her answer for RECEIPT_FOR seconds
    steps = None  # her turn's steps, [label, live|done|failed], newest last (step); the card shows the last few
    RECEIPT_FOR = 9.0
    # her answer clicked: copied, with "Copied" where the time was for COPIED_FOR seconds; your words clicked: the
    # typing box (askbox), made the first time
    copied_at, COPIED_FOR, typing = 0.0, 1.6, None
    # how she moves with a feeling (_feel): since when she's been shaking her head, the colour she glows for a moment
    # and since when, and when the second of her hearts' two beats is due
    shake_at = flash = beat_at = None
    # her light (island_light, 30 October 2026, after Glance's notch): the one on now, and the shapes it's been worked
    # out for, kept (_shine); and whether it lights up at all (island_light, _read_settings)
    lit = light_fields = None
    lights = True
    # files dragged over her (shelf.Target, 30 October 2026, after Glance's notch): {"paths", "x", "y", "left": when
    # they went off her, or None}, noted inside Windows' call (_dragging) and seen by _hover_poll; when it was last
    # noted, and when that was seen
    drag_over = target = None
    drag_note = drag_seen = 0.0
    # notifications as they came, newest first, for the Recent panel (_hub_alerts), in memory only and RECENT_MOST at
    # most; the app it shows, or all with None; when it was last looked at
    recent = ()
    alerts_app, alerts_seen = None, 0.0
    # the words you copied, newest first (island_plugins.Clipboard), and which of the shelf's kinds shows: None for
    # all, "pictures", "documents" or "copied"
    clips = ()
    shelf_view = None
    # a notification peeking before it opens, as Glance's notch peeks (_peek): (its popup's id, till when)
    peek = None
    RECENT_MOST, PEEK_FOR, SWEEP_FOR = 24, 0.55, 0.7
    visible_window = False
    # the panels (_hub): the one open (HUB_PAGES), or None with them closed; what the Hub plugin read last; the month
    # the calendar shows, (year, month), None for this one; the slider held down, (its name, when it last sent); when
    # the wheel last changed the panel
    hub_page = hub_data = hub_month = drag = None
    wheel_at = 0.0
    bar_springs = None  # the music's five bars, sprung to its bands (_bars_step)
    HUB_W = 392

    def __init__(self, root):
        self.root = root
        self.closed = False
        self.s = root.winfo_fpixels("1i") / 96
        self.runner = plugins.Runner()
        self.light, self.busy, self.area = False, False, None
        self._read_settings()
        self._build()
        self.eyes = face.Eyes()
        self.harry, self.you, self.hide_job, self.since = None, "", None, 0.0
        self.popups, self.popup, self.lives = [], None, {}
        self.hover, self.hover_at, self.away_at, self.hover_job, self.look_at = False, 0.0, 0.0, None, None
        self.pinned = None  # the plugin whose card a click keeps open after the pointer's gone
        self.rest_pos, self.rest_at = None, 0.0  # where the pointer is, and since when it's been there
        self.alpha, self.fade, self.visible_window = 0.0, 0, False
        self.layout = self.prev = None
        self.content = self.prev_alpha = 0.0
        self.changed = 0.0
        self.cap_alpha = 0.0
        self.level, self.t0, self.last, self.job, self.dirty = 0.0, time.time(), time.time(), None, True
        self.job_due = 0.0
        self.icon, self.icon_for = None, None
        self.frame_ms, self.dt = 0.0, 0.016
        self.eye = ("open", 1.0, 0.0, 0.0, False)  # this frame's eyes (face.Eyes.update), the same for every layout
        # the capsule: where her eyes were last drawn in the window, for the mouse to be looked at (_follow), and
        # the patch drawn into, for that; where the pointer was and since when, so a still one lets her glance about
        self.face_at, self.patch_at = None, (0, 0)
        self.pointer, self.pointer_at = None, 0.0
        self.texts = {}
        self.root.after(250, self._events)
        self.runner.start()
        self.root.after(400, self._wake)

    # ------------------------------------------------------------------ settings
    def _read_settings(self):
        g = settings.get
        # the answer card is the capsule but for her turns, which it shows
        self.panel = g("island_style") not in ("capsule", "pill")
        self.style = "pill" if g("island_style") == "pill" else "capsule"
        self.drop = bool(g("island_drop"))  # hanging from the top of the screen, a notch, with no gap above it
        self.face_style = g("island_face") if g("island_face") in ("orb", "eyes", "wave") else "eyes"
        themes = ("paper", "system", "light", "dark", "amoled")
        self.theme_name = g("island_theme") if g("island_theme") in themes else "paper"
        self.border = bool(g("island_border"))
        self.align = g("island_align") if g("island_align") in ("left", "center", "right") else "center"
        self.off_x, self.off_y = int(g("island_x") or 0), int(g("island_y") if g("island_y") is not None else 8)
        self.scale = max(70, min(150, int(g("island_scale") or 100))) / 100
        self.corner = max(6, min(40, int(g("island_radius") or 22)))
        self.always = bool(g("island_always"))
        self.hide_full = bool(g("island_hide_fullscreen"))
        self.auto_hide = max(1.5, min(30.0, float(g("island_auto_hide") or 5)))
        self.enabled = bool(g("popup"))  # Settings > Show the popup: off, only the turns the window still shows
        self.lights = g("island_light") is not False  # lighting up as things come (_light_up)

    def theme(self):
        name = self.theme_name
        if name == "system":
            name = "light" if self.light else "dark"
        if self.style == "capsule":  # the drop too: the same glass, hanging
            return GLASS[name if name in ("light", "paper") else "dark"]
        return THEMES[name]

    def reload(self):
        """After a setting changed in the Island tab: it shows the change straight away."""
        old_scale = self.scale
        self._read_settings()
        if self.scale != old_scale:
            was = self.visible_window
            self._teardown()
            self._build()
            self.visible_window = False
            if was:
                self.alpha = 0.0
        self.layout = self.prev = None
        self.shapes = {}  # the shadow and the border change with the theme
        self.dirty = True
        self._place()
        self._wake()

    def preview(self):
        """A notification for a look at how they come out."""
        self.popups.append(plugins.Activity("notifications", "notification", {
            "app": "Hey Harry", "app_id": "", "title": "This is how a notification looks",
            "text": "Pick which apps show here in the Island tab.", "phone": False}, mood="surprised"))
        self.dirty = True
        self._wake()

    # ------------------------------------------------------------------ the window
    def _build(self):
        s = self.k = self.s * self.scale
        self.f_compact = Text(round(13.5 * s), 600)
        self.f_label = Text(round(12 * s), 600)
        self.f_main = Text(round(15 * s), 500)
        self.f_title = Text(round(14.5 * s), 700)
        self.f_small = Text(round(11.5 * s), 600)
        self.m = round(self.MARGIN * s)
        cap_h = 2 * self.CAP_PAD_Y * s + self.f_label.line + 2 * s + 3 * self.f_main.line
        # tall enough for a card's rows (_card) from the start: building the window again each time you point at it
        # would flicker, and the taller picture costs memory only (271 px for 140: 0.4 MB more at 100%, 0.8 MB at
        # 150%, measured 27 October), never time: only what changed is sent (_push)
        self.island_max_h = max(140 * s, self._tallest_card(), self.PANEL_MAX_H * s)
        self.cw = int(math.ceil(max(self.CAP_MAX_W, self.CARD_W) * s)) + 2 * self.m
        self.ch = int(math.ceil(self.m + self.island_max_h + self.GAP * s + cap_h + self.m))
        self.top = tk.Toplevel(self.root)
        self.top.withdraw()
        self.top.overrideredirect(True)
        self.top.geometry(f"{self.cw}x{self.ch}+-20000+-20000")  # Tk's own window covers it all, for clicks
        self.top.deiconify()
        self.top.update_idletasks()
        self.hwnd = win.root_hwnd(self.top.winfo_id())
        win.make_overlay(self.hwnd)
        win.NO_CAPTURE.append(self.hwnd)
        self.drops, self.ole = None, False  # files dropped on her eyes go on the shelf (shelf.py)
        try:
            import shelf
            # OLE, for a file dragged back out, only at the first drag out (_press_move): here it made Tk's thread a COM
            # apartment of its own for all of her run, for something most runs never do. A drop is only handed on from
            # Windows' call to the window, and put on the shelf from _events, on Tk's own time (shelf.Drops)
            self.drops = shelf.Drops(self.hwnd, lambda paths: self.runner.post(("dropped", list(paths))))
        except Exception as exc:
            print(f"  island: no shelf ({exc!r})")
        try:
            import shelf
            # and told as files come over her, so she opens for them before they're dropped, as Glance's notch does
            # (the owner's ask, 30 October 2026): a drop target needs OLE on Tk's thread from the start after all
            if shelf.ole():
                self.ole = True
                self.target = shelf.Target(self.hwnd, self._dragging)
        except Exception as exc:
            print(f"  island: files dragged over her won't open her ({exc!r})")
            self.target = None
        self.dc = bubble._new_dc(None)
        self.bitmap, self.buf = bubble._dib(self.dc, self.cw, self.ch)
        self.old_bitmap = bubble._select(self.dc, self.bitmap)
        self.buf[:] = 0
        self.drawn, self.partial = None, True  # the box drawn last frame; whether Windows takes just a part
        self.cap_key = self.cap_picture = None  # the words' bar while it stands still (_draw)
        self.origin = wt.POINT(-20000, -20000)
        if not self._push():  # Windows won't take our pictures: bubble's pill instead (see bubble.Bubble)
            raise OSError("UpdateLayeredWindow failed")
        win.hide_window(self.hwnd)
        self.W, self.H = Spring(84 * s, 0.46, 0.74), Spring(self.COMPACT_H * s, 0.4, 0.8)
        self.CW, self.CH = Spring(0.0, 0.42, 0.82), Spring(0.0, 0.38, 0.84)
        self.top.bind("<ButtonRelease-1>", lambda e: self._click(False))
        self.top.bind("<ButtonRelease-3>", lambda e: self._click(True))
        self.top.bind("<ButtonPress-1>", lambda e: self._press_down())  # a panel's slider, held and dragged
        self.top.bind("<B1-Motion>", lambda e: self._press_move())
        self.top.bind("<MouseWheel>", lambda e: self._wheel(e.delta))
        self.shapes = {}

    def _teardown(self):
        for job in (self.job, self.hover_job):
            if job:
                self.root.after_cancel(job)
        self.job = self.hover_job = None
        win.hide_window(self.hwnd)
        if getattr(self, "drops", None) is not None:
            self.drops.close()
            self.drops = None
        if self.target is not None:
            self.target.close()
            self.target = None
        if self.hwnd in win.NO_CAPTURE:
            win.NO_CAPTURE.remove(self.hwnd)
        bubble._select(self.dc, self.old_bitmap)
        bubble._delete(self.bitmap)
        bubble._delete_dc(self.dc)
        for t in (self.f_compact, self.f_label, self.f_main, self.f_title, self.f_small):
            t.close()
        self.top.destroy()

    def _place(self, area=None):
        left, top, right, bottom = area or self.area or win.work_area()
        k, m = self.k, self.m
        if self.align == "left":
            x = left + (16 + self.off_x) * k - m
        elif self.align == "right":
            x = right - (16 + self.off_x) * k - self.cw + m
        else:
            x = (left + right) / 2 + self.off_x * k - self.cw / 2
        # the drop hangs from the very top; the capsule floats, never closer to it than FLOAT, whatever Down says
        down = 0 if self.drop else max(self.off_y, self.FLOAT) if self.style == "capsule" else self.off_y
        self.origin = wt.POINT(int(round(x)), int(round(top + down * k - m)))
        if self.visible_window:
            win.show_no_activate(self.hwnd, self.origin.x, self.origin.y, self.cw, self.ch)

    def _push(self, dirty=None):
        """The picture to Windows: all of it, or only the box (x0, y0, x1, y1) that changed."""
        bubble._flush()
        size, src = wt.SIZE(self.cw, self.ch), wt.POINT(0, 0)
        blend = bubble._BLEND(0, 0, 255, 1)  # AC_SRC_OVER, with our own alpha, premultiplied
        if dirty is not None and self.partial:
            x0, y0, x1, y1 = (int(v) for v in dirty)
            if x1 <= x0 or y1 <= y0:
                return True
            rect = wt.RECT(x0, y0, x1, y1)
            info = _ULWINFO(ctypes.sizeof(_ULWINFO), None, ctypes.pointer(self.origin), ctypes.pointer(size), self.dc,
                            ctypes.pointer(src), 0, ctypes.pointer(blend), 2, ctypes.pointer(rect))
            if _ULWI(self.hwnd, ctypes.byref(info)):
                return True
            print(f"  island: Windows won't take part of the picture ({ctypes.get_last_error()}), all of it then")
            self.partial = False
        return bool(bubble._ULW(self.hwnd, None, ctypes.byref(self.origin), ctypes.byref(size), self.dc,
                                ctypes.byref(src), 0, ctypes.byref(blend), 2))

    def _island_x(self, W):
        if self.align == "left":
            return self.m
        if self.align == "right":
            return self.cw - self.m - W
        return self.cw / 2 - W / 2

    # ------------------------------------------------------------------ what the app calls
    def show(self, state, text=None):
        if self.hide_job:
            self.root.after_cancel(self.hide_job)
            self.hide_job = None
        text = re.sub(r"\[[^\]]*\]\s*", "", " ".join(str(text or "").split()))  # her [cheerful] tags aren't words
        if state in MIC_STATES or state == "window":
            self.asked_at = self.answered_at = None  # a new turn
            self.steps = None
            if self.hub_page is not None:  # you're talking to her: the panels go, her turn's in their place
                self._hub_close()
        elif self.asked_at is None:
            self.asked_at = time.time()  # your words are in
        if state == "speaking" and self.answered_at is None:
            self.answered_at = time.time()
        if not self.harry or self.harry["state"] != state:
            self.since = time.time()
            if state in ("error", "note"):  # hearts from a moment ago don't go with something going wrong
                self.eyes.mood = None
            if state == "error":  # she shakes her head at it, glowing red a moment
                self._feel("x", self.since)
            if state in MIC_STATES and (not self.harry or self.harry["state"] not in MIC_STATES):
                self._light_up(HARRY[state][1] or BLUE, now=self.since)  # a turn of yours: she lights up to listen
        if not self.harry:
            self.icon_for = None  # the app you're in now, for the dots
            self._place(win.work_area())
        self.eyes.wake(time.time())
        self.harry = {"state": state, "text": text}
        self.dirty = True
        self._wake()

    def caption(self, text):
        self.you = " ".join(str(text or "").split())
        if self.harry:
            self.dirty = True
            self._wake()

    def hide(self, delay=0):
        if delay:
            if self.panel and self.harry and self.harry["state"] in ("speaking", "error"):
                delay = max(delay, self.PANEL_LINGER)  # the answer card stays a while, to read or try again
            if self.harry and not self.hide_job:
                self.hide_job = self.root.after(delay, self._hide_later)
            return
        self.hide_job = None
        if self.harry is None:
            return
        self.harry, self.you = None, ""
        self.dirty = True
        self._wake()

    def _hide_later(self):
        self.hide_job = None
        if self.panel and self.hover and self.harry:  # not while you point at the answer card
            self.hide_job = self.root.after(1500, self._hide_later)
            return
        self.hide()

    def asked(self, text):
        """A turn you typed, or asked again (siri's Asked): a new one on her card, timed from now, with your words in
        its bubble and none of the last turn's steps."""
        self.you = " ".join(str(text or "").split())
        self.asked_at, self.answered_at, self.steps = time.time(), None, None
        if self.harry:
            self.dirty = True
            self._wake()

    def ask(self, text="", under=True):
        """The typing box (askbox) under her card, or near the top of the screen with nothing up or under False
        (right Alt tapped twice), with text in it: what you type goes to her as a turn of yours."""
        if self.typing is None:
            self.typing = askbox.AskBox(self.root, self._typed, self._box_colours, self.k)
        self.typing.k = self.k  # as big as her card, after a change in the Island tab too
        x0, y0, x1, y1 = getattr(self, "island_rect", (0, 0, 0, 0))
        near = (self.origin.x + x0, self.origin.y + y1, x1 - x0) if under and self.harry and x1 > x0 else None
        self.typing.open(text, near)

    def _typed(self, text):
        controls = getattr(sys.modules.get("siri"), "CONTROLS", [None])[0]
        if controls is not None:
            controls.put(("typed", text))

    def _box_colours(self):
        """The typing box in her card's colours: its glass, its hairline and its words."""
        th = self.theme()
        mix = lambda t: askbox.hexed(tuple((1 - t) * b + t * w for b, w in zip(th["body"], th["text"])))
        return {"body": mix(0.09), "rim": mix(0.18), "text": askbox.hexed(th["text"]),
                "muted": askbox.hexed(th["muted"])}

    def step(self, state, label):
        """A step of her turn (siri's Step): a new row, live, or the last one done or failed."""
        rows = self.steps if self.steps is not None else []
        if rows and rows[-1][0] == label and rows[-1][1] == "live":
            rows[-1][1] = state
        else:
            rows.append([label, state])
        self.steps = rows[-12:]
        if self.panel and self.harry:
            self.dirty = True
            self._wake()

    def learned(self, kind, text):
        """What she learned or remembered (siri.receipt): a line on her answer card while it's up, else a popup."""
        self.receipt = (kind, text, time.time())
        if self.panel and self.harry:
            self.dirty = True
            self.root.after(int(self.RECEIPT_FOR * 1000) + 60, self._receipt_gone)
        else:
            self.popups.append(plugins.Activity("notifications", "notification", {
                "app": "Hey Harry", "app_id": "", "title": kind, "text": text, "phone": False}, mood="happy"))
            self.popups = self.popups[-6:]
            self.dirty = True
        self._wake()

    def _receipt_gone(self):
        """Its time's up: the card loses the line, and stops drawing for it."""
        if self.receipt and time.time() - self.receipt[2] >= self.RECEIPT_FOR:
            self.receipt = None
            self.dirty = True
            self._wake()

    def _copied_gone(self):
        """"Copied" has had its time: the card shows how long she took again."""
        self.dirty = True
        self._wake()

    def react(self, mood):
        now, mood = time.time(), str(mood or "")
        self.eyes.react(mood, now)
        self._feel(mood, now)
        self._wake()

    # ------------------------------------------------------------------ how she moves with a feeling (30 October 2026)
    def _feel(self, mood, now):
        """The island moving with a feeling (MOOD_MOTION), while it's up: a kick into the springs that size it, or a
        shake of the head, and a glow round it in the feeling's colour for a moment (MOOD_FLASH). Never a frame of its
        own: the caller wakes the island, or is a frame already."""
        if not self.visible_window:
            return
        how = MOOD_MOTION.get(mood)
        if how == "shake":
            self.shake_at = now
        elif how in KICKS:
            self._kick(how)
            if how == "beat":
                self.beat_at = now + BEAT_GAP
        if mood in MOOD_FLASH:
            self.flash = (MOOD_FLASH[mood], now)
            self._light_up(MOOD_FLASH[mood], "alarm" if mood in ("sad", "x") else "halo", now=now)

    def _kick(self, how):
        dw, dh = KICKS[how]
        self.W.v += dw * self.k
        self.H.v += dh * self.k

    def _fx(self, name, now):
        """A plugin's moment: "ring", a timer gone off, her eyes wide and the island shaking as a phone rings,
        glowing orange."""
        if name == "ring":
            self.eyes.react("surprised", now)
            if self.visible_window:
                self.shake_at, self.flash = now, (ORANGE, now)
                self._light_up(ORANGE, now=now)

    def _jolt(self, now):
        """How far to the side the island's shaken this frame, in px, 0 once it's still: quick, and dying away."""
        if self.shake_at is None:
            return 0.0
        u = now - self.shake_at
        if u >= SHAKE_FOR or u < 0:
            self.shake_at = None
            return 0.0
        return 6.5 * self.k * math.exp(-u * 6.0) * math.sin(u * math.tau * 6.5)

    def _aura(self, now):
        """(colour, how strong 0 to 1) of the glow round the island this frame, or None: what's on asks for one
        (Layout.aura), breathing while it's lively, and a feeling's flash goes over it while it lasts."""
        lay, colour, strength = self.layout, None, 0.0
        if lay is not None and lay.aura is not None and self.content > 0.01:
            colour, how = lay.aura
            strength = 1.0
            if how == "breathe" and (lay.lively is None or now < lay.lively[0]):
                strength = AURA_LOW + (1 - AURA_LOW) * (0.5 + 0.5 * math.sin((now - self.t0) * math.tau / 2.6))
            strength *= self.content
        if self.flash is not None:
            u = (now - self.flash[1]) / FLASH_FOR
            if 0 <= u < 1:
                f = (1 - u) ** 2
                if f >= strength:
                    colour, strength = self.flash[0], f
            else:
                self.flash = None
        return (colour, strength) if colour is not None and strength > 0.01 else None

    # ------------------------------------------------------------------ her light (30 October 2026, after Glance)
    def _light_up(self, colour, kind="halo", level=None, now=None, held=False):
        """Her light (island_light) in colour, as Glance's notch lights up when something comes; kind and level as
        island_light.Light has them; held: going on from the one that's on, as a level moves on, with no new flare and
        its arms where they'd got to. Unless Settings has it off (island_light). The caller wakes the island, or is a
        frame already."""
        if self.lights and colour is not None:
            at = time.time() if now is None else now
            if held:
                at -= 2.2 * lights.FLARE
            self.lit = lights.Light(colour, at, kind, level)

    def _light_for(self, act, now=None):
        """The light a popup, or something that comes up, gets: a notification or what's playing in its app's colour,
        the battery plugged in green all round her, and low, red at her corners; a copy pale blue, a timer orange, the
        rest blue. Charging lit her only as far as it was charged, which read as a light gone wrong on its way round
        (30 October 2026, the owner's screenshot): its percentage beside her eyes says how far."""
        d = act.data if isinstance(act.data, dict) else {}
        if act.kind == "battery":
            if d.get("event") == "low":
                self._light_up(RED, "alarm", now=now)
            elif d.get("charging"):
                self._light_up(GREEN, now=now)
            return
        if act.kind == "level":  # along her bottom as far as it's set, as Glance's notch shows the brightness
            colour = SLIDER_TINTS.get(d.get("what"), BLUE)
            t = time.time() if now is None else now
            lit = self.lit
            going = lit is not None and not lit.done(t) and lit.kind == "level" and lit.colour == tuple(colour)
            self._light_up(colour, "level", 0.0 if d.get("muted") else (d.get("level") or 0) / 100, t, going)
            return
        if act.kind == "track" and d.get("tint") is not None:
            colour = tuple(d["tint"])
        elif act.kind in ("notification", "media", "track") and d.get("app"):
            colour = art.brand(d["app"])
        elif act.kind == "copied" and d.get("how") not in (None, "copy", "paste"):
            colour = SHORTCUTS.get(d["how"], (None, BLUE))[1]
        else:
            colour = {"copied": COPY_LIGHT, "timer": ORANGE}.get(act.kind, BLUE)
        self._light_up(colour, now=now)

    def _shine(self, now, x0, W, H, r, y0, cap_rows):
        """Her light, while one's on, laid over the picture round the island (island_light), never on her or on the
        bar of your words under her: worked out once for each shape it's on, so a frame of it only lays it."""
        lit = self.lit
        if lit is None:
            return
        if lit.done(now):
            self.lit = None
            return
        strength = lit.strength(now) * self.alpha
        if strength <= 0.003:
            return
        k = self.k
        stop = cap_rows[0] if cap_rows is not None else self.ch
        key = (round(x0 * 2), round(W * 2), round(H * 2), round(r * 2), round(y0 * 2), self.drop, lit.kind,
               None if lit.level is None else round(lit.level * 100), stop)
        if self.light_fields is None or len(self.light_fields) > 12:
            self.light_fields = {}
        f = self.light_fields.get(key)
        if f is None:
            s = self.DROP_SHOULDER * k if self.drop else 0.0
            if self.drop:
                def sd(xs, ys):
                    return _drop(xs, ys, x0, W, H, r, y0, s)
            else:
                def sd(xs, ys):
                    return face.rbox(xs, ys, x0 + W / 2, y0 + H / 2, W / 2, H / 2, r)
            def box(xs, ys):  # the plain box, smooth past her shoulders, for the glow
                return face.rbox(xs, ys, x0 + W / 2, y0 + (H - r) / 2, W / 2, (H + r) / 2, r)
            f = self.light_fields[key] = lights.field(sd, x0, W, H, r, y0, k, self.drop, lit.kind, lit.level,
                                                      (self.cw, stop), soft=box if self.drop else None)
        box = lights.shine(self.buf, f, lit, strength, now, dark=self.theme()["body"][0] < 0.5)
        if box is not None:
            self.drawn = _union(self.drawn, box)

    def _rate(self, lay, now):
        """The frames a second lay asks for now: more while it's lively (Layout.lively), else its own."""
        if lay.lively is not None and now < lay.lively[0]:
            return max(lay.rate, lay.lively[1])
        return lay.rate

    def _moving(self, now):
        """True while a feeling still moves the island: a shake, a flash or a beat to come."""
        if self.beat_at is not None and now >= self.beat_at:
            self.beat_at = None
            self._kick("beat")
        return self.shake_at is not None or self.beat_at is not None or \
            (self.flash is not None and now - self.flash[1] < FLASH_FOR) or \
            (self.lit is not None and not self.lit.done(now)) or self._sweeping(now)

    def close(self):
        self.closed = True
        self.runner.stop()
        for job in (self.job, self.hide_job, self.hover_job):
            if job:
                self.root.after_cancel(job)
        self.job = self.hide_job = self.hover_job = None
        win.hide_window(self.hwnd)
        self.visible_window = False

    def destroy(self):
        """Gone for good: the Island tab switched to the card or the pill."""
        self.close()
        try:
            self._teardown()
            for t in self.texts.values():
                t.close()
            self.texts = {}
        except Exception as exc:
            print(f"  island: couldn't tidy up ({exc!r})")

    @property
    def visible(self):
        """Her own popup is up (not just her eyes, or a plugin's)."""
        return self.harry is not None

    # ------------------------------------------------------------------ the plugins
    def _events(self):
        if self.closed:
            return
        changed = False
        for event in self.runner.take():
            kind = event[0]
            if kind == "show":
                act = event[1]
                if act.kind == "level" and self.hub_page is not None:
                    continue  # Controls' own slider moved it, and shows it
                if not self._again(act):
                    self.popups.append(act)
                    self.popups = self.popups[-6:]
            elif kind == "recent":  # a notification as it came, for the Recent panel, its popup shown or hushed
                d = dict(event[1].data, at=event[1].at)
                self.recent = [d] + list(self.recent)[:self.RECENT_MOST - 1]
                if self.hub_page == "alerts":
                    self.alerts_seen = time.time()
                elif self.hub_page is None:
                    continue
            elif kind == "live":
                if event[2] is None:
                    self.lives.pop(event[1], None)
                    if self.pinned == event[1]:
                        self.pinned = None
                else:
                    came = event[1] not in self.lives
                    self.lives[event[1]] = event[2]
                    if event[2].mood:  # it came up, or something in it did: something done, or waiting on you
                        self.eyes.react(event[2].mood, time.time())
                        self._feel(event[2].mood, time.time())
                    elif came and self.visible_window and self.harry is None and not self.popups and \
                            max(self.lives, key=plugins.priority) == event[1]:
                        self._kick("pop")  # a new one in front: the island bumps out to take it, as a phone's does
                        self._light_for(event[2])
            elif kind == "fx":  # a plugin's moment, as a timer going off (Timers)
                self._fx(event[1], time.time())
            elif kind == "hub":  # what the panels show, read again (island_plugins.Hub)
                self.hub_data = dict(event[1])
                if self.hub_page is None and not self._status_widgets():
                    continue
            elif kind == "clips":  # what you copied, to copy again from the shelf
                self.clips = list(event[1])
                if self.hub_page != "shelf":
                    continue
            elif kind == "touch":  # something on a popup up now changed (a headset's battery): drawn again
                pass
            elif kind == "dropped":  # files dropped on her eyes (shelf.Drops, shelf.Target), put on the shelf now
                self.drag_over = None
                self._dropped(event[1])
                self._light_up(VIOLET)
            elif kind == "busy":
                self.busy = event[1]
            elif kind == "place":
                self.area = event[1]
                if self.harry is None:
                    self._place(self.area)
            elif kind == "light":
                self.light = event[1]
            changed = True
        if changed:
            self.dirty = True
            self._wake()
        self.root.after(200, self._events)

    def _scene(self, now):
        """What to show now: her turn, the panels while they're open, a popup, what stays while it lasts, her eyes,
        or nothing."""
        if self.drag_over is not None and self._hub_on():  # files dragged over her: where they can go, over all
            return ("drop",)
        if self.harry:
            return ("harry",)
        if self.hub_page is not None:  # you opened them: over what pops up, which waits
            return ("hub",)
        if not self.enabled or (self.busy and self.hide_full):
            return None
        while self.popups:
            head = self.popups[0]
            if head.until is None:
                if now - head.at > (3 if head.kind in ("copied", "level") else 120):  # it waited too long to be news
                    self.popups.pop(0)
                    continue
                head.until = now + (head.seconds or self.auto_hide)
                if head.kind == "notification" and self.style == "capsule" and not self.hover:
                    self.peek = (id(head), now + self.PEEK_FOR)  # small first, then opened (_peek)
                    head.until += self.PEEK_FOR
                if head.mood:
                    self.eyes.react(head.mood, now)
                    self._feel(head.mood, now)
                self._light_for(head, now)  # in its own colour, over a feeling's
            if now < head.until or (self.hover and self.popup is head):
                self.popup = head
                return ("popup", head)
            self.popups.pop(0)
        self.popup = None
        if self.lives:  # what stays while it lasts, the one that matters most (Plugin.priority): tasks, a timer, music
            return ("live", self.lives[max(self.lives, key=plugins.priority)])
        if self.always and (self.face_style == "eyes" or self.style == "capsule"):  # the capsule always has her face
            return ("idle",)
        return None

    # ------------------------------------------------------------------ layouts
    def _make(self, scene, now):
        if scene is None:
            return None
        if scene[0] == "harry":  # pointing at her face while her turn's own row can be stopped: its card, with Stop.
            act, turn = self._turn()  # only while you point: a card pinned earlier never covers her face for a turn
            if turn and turn.get("buttons") and self.hover:
                return self._card(act)
            return self._harry()
        if scene[0] == "idle":
            return self._idle()
        if scene[0] == "hub":
            return self._hub(now)
        if scene[0] == "drop":
            return self._drop_zone(now)
        act = scene[1]
        if scene[0] == "popup" and self.peek is not None and self.peek[0] == id(act) and now < self.peek[1]:
            return self._peek(act)
        if act.kind == "copied":  # what you just copied, or a shortcut you pressed (island_plugins.Clipboard)
            return self._copied(act)
        if act.kind == "level":  # the volume or the brightness as it changes (island_plugins.Levels)
            return self._level(act)
        if act.kind == "track":  # another song, peeking (island_plugins.Media)
            return self._track(act)
        if act.kind == "notification":
            return self._notification(act)
        if act.kind == "device" and isinstance(act.data, dict):  # headphones connected, a USB drive in
            return self._glass_device(act) if self.hover and self.style == "capsule" else self._device(act)
        if act.kind == "media":
            return self._media_card(act) if self.hover else self._media(act)
        opened = self.hover and self.style == "capsule"  # as a phone's island opens (_live_head)
        if act.kind == "battery":
            return self._glass_battery(act) if opened else self._battery(act)
        if act.kind == "timer":
            return self._glass_timer(act) if opened else self._timer(act)
        if act.kind == "live" and isinstance(act.data, dict):  # dream mode, meeting notes, hand control and the rest
            return self._glass_live(act, now) if opened else self._live(act, now)
        if isinstance(act.data, dict) and (act.data.get("rows") or act.data.get("title")):  # any plugin's card
            return self._card(act) if self.hover or self.pinned == act.plugin else self._compact(act)
        return self._idle()

    def _front_icon(self, size):
        """The app you're in, for the dots while she listens: its icon, or a badge with its first letter."""
        hwnd = win.user32.GetForegroundWindow()
        if hwnd and hwnd != self.hwnd:
            try:
                exe = win.window_exe(hwnd)
            except Exception:
                exe = ""
            mine = exe and os.path.basename(exe).lower() in ("pythonw.exe", "python.exe")
            if exe and not mine:
                key = (exe.lower(), size)
                if key != self.icon_for:
                    pic = art.exe_icon(exe, size)
                    if pic is None:
                        pic = art.window_icon(hwnd, size)
                    if pic is None:
                        name = win.file_description(exe) or os.path.splitext(os.path.basename(exe))[0]
                        pic = art.badge(name, size, self._text)
                    self.icon, self.icon_for = pic, key
        return self.icon

    def _text(self, px, weight=700):
        key = (px, weight)
        if key not in self.texts:
            self.texts[key] = Text(px, weight)
        return self.texts[key]

    def _turn(self):
        """(the Tasks card, her turn's own row in it) while one runs (island_plugins.Tasks), else (None, None)."""
        act = self.lives.get("tasks")
        turn = act.data.get("turn") if act is not None and isinstance(act.data, dict) else None
        return (act, turn) if turn else (None, None)

    def _harry(self):
        k, th = self.k, self.theme()
        state, text = self.harry["state"], self.harry["text"]
        expr, colour, mode, bars = HARRY.get(state, HARRY["listening"])
        colour = colour or th["muted" if state == "note" else "text"]
        cap = self._caption(state, text, bars)
        badge = sum(int(a.data.get("badge") or 0) for a in self.lives.values() if isinstance(a.data, dict))
        turn = self._turn()[1]  # how far her turn's got (step 3/5, round 5/30), beside her dots
        if self.panel:
            return self._panel_harry(state, expr, colour)
        if self.style == "capsule":  # her eyes or the orb (the Face setting); the Siri wave is the pill's alone
            return self._capsule_harry(state, expr, colour, mode, cap, badge, turn)
        key = ("harry", state, self.face_style, badge, turn and (turn.get("status"), turn.get("progress")))
        if self.face_style == "wave":
            W, H = self.WAVE[0] * k, self.WAVE[1] * k
            kind_, source, tint, _ = LOOKS.get(state, LOOKS["listening"])

            def draw(cv, ox, oy, Wn, Hn, a, now):
                aw, ah = int(Wn - 20 * k), int(Hn - 6 * k)
                if aw < 8 or ah < 8:
                    return
                t = now - self.t0
                if kind_ == "dots":
                    img = bubble.dots(t, aw, ah)[..., None] * np.array(tint, np.float32)
                else:
                    self.level = bubble.loudness(source, self.level)
                    img = bubble.wave(t, aw, ah, 0.12 + 0.88 * self.level if source else 0.25) * \
                        np.array(tint, np.float32)
                x0, y0 = int(round(ox + (Wn - aw) / 2)), int(round(oy + (Hn - ah) / 2))
                sl = cv.region(x0, y0, x0 + aw, y0 + ah)
                if sl:
                    cv.col[sl[0]] += cv._part(img, sl[0], x0, y0) * a
            return Layout(key, "harry", W, H, draw, cap=cap, animated=True, aura=self._turn_aura(state, colour))
        W, H = self.FACE[0] * k, self.FACE[1] * k
        size = self.EYES * k
        icon = self._front_icon(round(17 * k))
        n, step, r = 5, 8.6 * k, 2.4 * k
        gr = 5.5 * k  # the turn's ring, after a gap

        src = "mic" if state in MIC_STATES else "voice" if state == "speaking" else None

        def draw(cv, ox, oy, Wn, Hn, a, now):
            t = now - self.t0
            e, open_, lx, ly, _ = self.eye
            if self.face_style == "orb":
                orb = "voice" if mode in ("voice", "her") else "busy" if mode == "busy" else "idle"
                face.draw_orb(cv, ox + Wn / 2, oy + Hn * 0.38, size * 0.95, orb, self.level if src else 0.0, t,
                              open_, (lx, ly), th["eyes"], th["glow"], a, None if colour is th["text"] else colour)
            else:
                face.draw_eyes(cv, ox + Wn / 2, oy + Hn * 0.38, size, e, open_, (lx, ly), self.level if src else 0.0,
                               t, th["eyes"], th["glow"], a)
            row_y = oy + Hn * 0.77
            iw = icon.shape[1] if icon is not None else 0
            dots = self.face_style != "orb" or mode == "ring"  # the orb shows the voice and the work itself
            row_w = iw + (9 * k if iw else 0) + ((n - 1) * step + 2 * r if dots else 0) + \
                (8 * k + 2 * gr if turn else 0)
            x = ox + Wn / 2 - row_w / 2
            if icon is not None:
                cv.image(icon, x, row_y - icon.shape[0] / 2, a)
                x += iw + 9 * k
            if mode == "ring":
                total = float(getattr(sys.modules.get("siri"), "FOLLOW_UP", 8.0))
                left = max(0.0, 1 - (now - self.since) / total)
                face.ring(cv, x + (n - 1) * step / 2 + r, row_y, 6.5 * k, 2.2 * k, left, ORANGE, th["track"], a)
            elif dots:
                dots_mode = "voice" if mode in ("voice", "her") else "busy" if mode == "busy" else "still"
                face.dots_row(cv, x + r, row_y, n, step, r, colour, self.level if mode in ("voice", "her") else 0.0,
                              t, dots_mode if dots_mode != "still" else "voice", a * (0.75 if mode == "still" else 1))
            if turn:
                gx_ = x + ((n - 1) * step + 2 * r + 8 * k if dots else 0) + gr
                self._glyph(cv, gx_, row_y, gr, turn, now, a)
            if badge:  # how many go on meanwhile, her turn's row too, in the corner: point at her for the card
                self._badge(cv, ox + Wn - 13 * k, oy + 13 * k, badge, a)
        return Layout(key, "harry", W, H, draw, cap=cap, eyes=expr, animated=state not in ("error", "note", "phone"),
                      wander=False, aura=self._turn_aura(state, colour))

    def _panel_harry(self, state, expr, colour):
        """Her turn in the answer card (28 October 2026, the owner's pick, her own eyes kept): her eyes and what
        she's doing at the top, with x to close it; what you said in a bubble on the right, the words coming in as
        you say them; her answer under it, coming in line by line; and once she's answered, how long it took and Try
        again, which asks her the same again."""
        k, th = self.k, self.theme()
        W, pad, head_h = self.PANEL_W * k, 20 * k, 44 * k
        inner = W - 2 * pad
        f_status, f_q = self._text(round(12.5 * k), 500), self._text(round(13.5 * k), 400)
        f_a, f_foot = self._text(round(15 * k), 400), self._text(round(10.5 * k), 400)
        text = self.harry["text"]
        live = state in MIC_STATES or state == "window"
        busy = state in ("thinking", "looking", "doing", "finishing")
        own = LOOKS.get(state, LOOKS["listening"])[3].rstrip("\u2026").strip()
        heard = (text if text and text != own and not text.startswith(HINTS) else "") if live else self.you
        answer = text if state in ("speaking", "error", "note", "phone") and text != own else ""
        status = PANEL_STATUS.get(state, "")
        if busy and text and not bubble._same(text, self.you):
            status = text  # what she's at: "Opening Settings"
        qx, qy = 14 * k, 9 * k
        q_lines = self._wrap([(w, True) for w in heard.split()], inner * 0.8 - 2 * qx, 4, live, f_q) if heard else []
        q_w = max((f_q.measure(" ".join(w for w, _ in line)) for line in q_lines), default=0) + 2 * qx
        q_h = len(q_lines) * f_q.line + 2 * qy
        a_lh = f_a.line + 4 * k
        a_lines = self._wrap([(w, True) for w in answer.split()], inner, 6, False, f_a) if answer else []
        done = state == "speaking" and self.answered_at is not None and self.asked_at is not None
        took = f"{max(0.0, self.answered_at - self.asked_at):.2f} s" if done else ""
        again = done and bool(self.you)
        copied = time.time() - self.copied_at < self.COPIED_FOR
        got = self.receipt if self.receipt and time.time() - self.receipt[2] < self.RECEIPT_FOR else None
        f_got = self._text(round(11 * k), 600)
        f_step, step_h = self._text(round(12 * k), 500), 19 * k
        rows = [list(r) for r in (self.steps or [])][-(3 if answer else 4):]
        earlier = len(self.steps or []) - len(rows)
        y_q = 12 * k + head_h + 8 * k
        y_s = (y_q + q_h if q_lines else 12 * k + head_h) + 12 * k  # the steps, under your words
        s_h = (len(rows) + (1 if earlier else 0)) * step_h
        y_a = (y_s + s_h + 6 * k) if rows else (y_s - 12 * k + 14 * k)
        y_f = (y_a + len(a_lines) * a_lh if a_lines else y_a - 14 * k) + 16 * k
        H = (y_f + f_foot.line if took or again or copied else y_f - 16 * k) + 16 * k
        y_r = H - 4 * k  # the receipt, under the time and Try again
        if got:
            H += f_got.line + 10 * k
        H = min(self.island_max_h, H)
        eyes_w, eyes, _ = self._face(expr, colour, voice=live or state == "speaking", busy=busy)
        x_r, x_cx, x_cy = 11 * k, W - pad - 9 * k, 12 * k + head_h / 2
        full = bool(settings.get("full_access"))  # An orange "Full access" pill, by the x
        f_badge = self._text(round(11 * k), 600)
        badge_w = (f_badge.measure("Full access") + 2 * 9 * k + 10 * k) if full else 0
        badge_h = 22 * k
        badge_x1 = W - pad - 9 * k - x_r - 8 * k
        redo = "Try again"
        redo_w = f_foot.measure(redo)
        hot = [("close", x_cx - x_r - 3 * k, x_cy - x_r - 3 * k, x_cx + x_r + 3 * k, x_cy + x_r + 3 * k)]
        if full:
            hot.append(("full", badge_x1 - badge_w, x_cy - badge_h / 2, badge_x1, x_cy + badge_h / 2))
        if q_lines and not live:  # your words: in the typing box, to fix and send again
            hot.append(("words", W - pad - q_w, y_q, W - pad, y_q + q_h))
        if a_lines:  # her answer: copied
            hot.append(("answer", pad - 4 * k, y_a - 3 * k, W - pad, y_a + len(a_lines) * a_lh))
        if again:
            hot.append(("again", W - pad - redo_w - 6 * k, y_f - 4 * k, W - pad + 6 * k, y_f + f_foot.line + 4 * k))
        fill = tuple(0.91 * b + 0.09 * t for b, t in zip(th["body"], th["text"]))  # white at 9% on the glass
        rim = tuple(0.82 * b + 0.18 * t for b, t in zip(th["body"], th["text"]))
        answered_at = self.answered_at

        def draw(cv, ox, oy, Wn, Hn, a, now):
            cy = oy + x_cy
            eyes(cv, ox + pad - 8 * k, cy, a, now)
            if status:
                col = th["muted"]
                if live or busy:  # it shimmers while she's at it
                    s = 0.35 * (0.5 + 0.5 * math.sin((now - self.t0) * 3.4))
                    col = tuple(m + (t - m) * s for m, t in zip(th["muted"], th["text"]))
                sx = ox + pad - 8 * k + eyes_w + 4 * k
                words = f_status.fit(status, max(20 * k, ox + Wn - pad - 2 * x_r - 8 * k - sx -
                                                 (badge_w + 8 * k if full else 0)))
                cv.text(f_status.render(words), sx, cy - f_status.line / 2 - 1, col, a)
            xc = ox + Wn - pad - 9 * k
            cv.shape(lambda xs, ys: face.circle(xs, ys, xc, cy, x_r), (xc - x_r - 1, cy - x_r - 1, xc + x_r + 1,
                                                                        cy + x_r + 1), fill, a)
            if full:
                bx1 = ox + Wn - pad - 9 * k - x_r - 8 * k
                bx0, bh = bx1 - badge_w, badge_h / 2
                tint = tuple(0.87 * b + 0.13 * o for b, o in zip(th["body"], ORANGE))
                cv.shape(lambda xs, ys: face.rbox(xs, ys, (bx0 + bx1) / 2, cy, badge_w / 2, bh, bh),
                         (bx0 - 1, cy - bh - 1, bx1 + 1, cy + bh + 1), tint, a)
                dx = bx0 + 9 * k + 2.5 * k
                cv.shape(lambda xs, ys: face.circle(xs, ys, dx, cy, 2.5 * k), (dx - 4 * k, cy - 4 * k, dx + 4 * k,
                                                                             cy + 4 * k), ORANGE, a)
                cv.text(f_badge.render("Full access"), dx + 5 * k, cy - f_badge.line / 2 - 1, (1.0, 0.70, 0.25), a)
            face.close_glyph(cv, xc, cy, 4.6 * k, th["text"], a * 0.85)
            if q_lines:
                bx1, by0 = ox + Wn - pad, oy + y_q
                bx0, by1 = bx1 - q_w, by0 + q_h
                mx, my = (bx0 + bx1) / 2, (by0 + by1) / 2

                def bubble_sd(xs, ys):  # round, but for its bottom-right corner: a speech-bubble tail
                    return np.minimum(face.rbox(xs, ys, mx, my, q_w / 2, q_h / 2, 16 * k),
                                      face.rbox(xs, ys, (mx + bx1) / 2, (my + by1) / 2, q_w / 4, q_h / 4, 5 * k))
                box = (bx0 - 2, by0 - 2, bx1 + 2, by1 + 2)
                cv.shape(lambda xs, ys: np.abs(bubble_sd(xs, ys)) - 0.5, box, rim, a)
                cv.shape(bubble_sd, box, fill, a)
                ty = by0 + qy
                for line in q_lines:
                    cv.text(f_q.render(" ".join(w for w, _ in line)), bx0 + qx - 2, ty, th["text"], a * 0.94)
                    ty += f_q.line
            sy = oy + y_s
            if earlier:
                cv.text(f_step.render(f"+{earlier} earlier"), ox + pad + 10 * k, sy, th["muted"], a * 0.8)
                sy += step_h
            for label, how in rows:  # a dot each: white and pulsing while it runs, green done, red failed
                cy_ = sy + f_step.line / 2 + 1
                pulse = 0.55 + 0.45 * math.sin((now - self.t0) * 6.0) if how == "live" else 1.0
                dot = th["text"] if how == "live" else GREEN if how == "done" else RED
                cv.shape(lambda xs, ys, cy_=cy_: face.circle(xs, ys, ox + pad + 2.5 * k, cy_, 2.5 * k),
                         (ox + pad - 2 * k, cy_ - 5 * k, ox + pad + 7 * k, cy_ + 5 * k), dot, a * pulse)
                words = f_step.fit(label, Wn - 2 * pad - 12 * k)
                cv.text(f_step.render(words), ox + pad + 10 * k, sy, th["text"] if how == "live" else th["muted"], a)
                sy += step_h
            if a_lines:
                col = RED if state == "error" else th["muted"] if state == "note" else th["text"]
                since = now - (answered_at or now - 10)
                for i, line in enumerate(a_lines):
                    e = min(1.0, max(0.0, since * 5.0 - i * 0.6))  # line by line, rising a little into place
                    e = 1 - (1 - e) ** 3
                    if e > 0:
                        cv.text(f_a.render(" ".join(w for w, _ in line)), ox + pad - 2,
                                oy + y_a + i * a_lh + (1 - e) * 5 * k, col, a * e)
            if copied:
                cv.text(f_foot.render("\u2713 Copied"), ox + pad - 2, oy + y_f, GREEN, a)
            elif took:
                cv.text(f_foot.render(took), ox + pad - 2, oy + y_f, th["muted"], a)
            if again:
                cv.text(f_foot.render(redo), ox + Wn - pad - redo_w - 2, oy + y_f, th["muted"], a)
            if got:  # green, then fading over its last 2 s
                left = self.RECEIPT_FOR - (now - got[2])
                fade = a * max(0.0, min(1.0, left / 2.0))
                label = f"\u2713 {got[0]}"
                lw = f_got.measure(label)
                cv.text(f_got.render(label), ox + pad - 2, oy + y_r, GREEN, fade)
                rest = f_got.fit(got[1], max(20 * k, Wn - 2 * pad - lw - 10 * k))
                cv.text(f_got.render(rest), ox + pad + lw + 6 * k, oy + y_r, th["muted"], fade)
        key = ("harry", state, "panel", heard, answer, status, took, round(H), full, got and got[2],
               tuple(tuple(r) for r in rows), copied, earlier)
        return Layout(key, "harry", W, H, draw, radius=self.GLASS_CORNER * k, hot=hot, eyes=expr, wander=False,
                      animated=state not in ("error", "note", "phone") or bool(a_lines) or bool(got), face=True,
                      aura=self._turn_aura(state, colour))

    def _panel_press(self, name):
        """x on her turn's box: it goes; Try again: the same words asked again, as a turn of yours. Your words: in
        the typing box, to fix and send again; her answer: copied (28 October 2026)."""
        if name == "close":
            self.hide()
        elif name == "words" and self.you:
            self.ask(self.you)
        elif name == "answer" and self.harry and self.harry["text"]:
            try:
                win.set_clipboard(self.harry["text"])
            except RuntimeError as exc:  # another app kept the clipboard: nothing says Copied
                print(f"  island: not copied, {exc}")
                return
            self.copied_at = time.time()
            self.dirty = True
            self._wake()
            self.root.after(int(self.COPIED_FOR * 1000) + 60, self._copied_gone)
        elif name == "full" and self._steady(time.time()):  # the badge turns it off, never her own clicks
            settings.put("full_access", False)
            settings.put("full_access_until", 0)
            print("  full access: off, from her island")
            self.dirty = True
            self._wake()
        elif name == "again" and self.you:
            controls = getattr(sys.modules.get("siri"), "CONTROLS", [None])[0]
            if controls is not None:
                controls.put(("again", self.you))

    def _badge(self, cv, cx, cy, n, a):
        """A small grey pill with n in it, centred on cx, cy."""
        th = self.theme()
        words = str(n) if n < 10 else "9+"
        cover = self.f_small.render(words)
        r = max(7.5 * self.k, cover.shape[1] / 2 + 3 * self.k)
        cv.shape(lambda xs, ys: face.rbox(xs, ys, cx, cy, r, 7.5 * self.k, 7.5 * self.k),
                 (cx - r - 1, cy - 7.5 * self.k - 1, cx + r + 1, cy + 7.5 * self.k + 1), th["track"], a)
        cv.text(cover, cx - cover.shape[1] / 2, cy - self.f_small.line / 2 - 0.5, th["text"], a)

    def _words(self, state, text):
        """(label, words, newest first, most rows, struck out) for the bar under the island."""
        own = LOOKS.get(state, LOOKS["listening"])[3].rstrip("\u2026").strip()
        text = text.rstrip(" \u2026").strip() if text else ""
        if text == own or text.startswith(HINTS):
            text = ""
        you = self.you
        if state == "dictating":
            return "", text, True, 3, True
        if state in ("listening", "read", "again"):
            return "", text, True, 2, False
        if state in ("thinking", "looking", "doing", "finishing"):
            if you and text and not bubble._same(text, you):
                return text, you, False, 2, False
            return "", you or text, False, 2, False
        if state == "speaking":
            return (f"You: {you}" if you else ""), text, False, 3, False
        if state == "window":
            return "", "", False, 1, False
        if state == "note":
            return "", text or own, False, 1, False
        if state == "error":
            return own, text, False, 2, False
        return "", text, False, 2, False

    def _caption(self, state, text, bars):
        label, words, newest, rows, struck = self._words(state, text)
        if not words and not label:
            return None
        k, th = self.k, self.theme()
        f = self.f_main
        bar_w = 20 * k if bars else 0
        avail = self.CAP_MAX_W * k - 2 * self.CAP_PAD_X * k - bar_w
        tokens = dictation.segments(words) if struck else [(w, True) for w in words.split()]
        lines = self._wrap(tokens, avail, rows, newest)
        label = self.f_label.fit(label, avail) if label else ""
        space = f.measure(" ") or 4
        widths = [sum(f.measure(" ".join(w for w, _ in run)) for run in self._runs(line)) +
                  space * (len(self._runs(line)) - 1) for line in lines]
        widest = max([self.f_label.measure(label)] + widths + [0])
        w = min(self.CAP_MAX_W * k, 2 * self.CAP_PAD_X * k + bar_w + widest + 4)
        lh, mh = self.f_label.line, f.line
        h = 2 * self.CAP_PAD_Y * k + (lh + 2 * k if label else 0) + mh * len(lines)
        quiet = state in ("note",)
        lab_colour = RED if state == "error" else th["muted"]

        def origin(ox, oy, Hn):
            return ox + self.CAP_PAD_X * k, oy + (Hn - (h - 2 * self.CAP_PAD_Y * k)) / 2

        def meter_at(ox, oy, Hn):
            x, y = origin(ox, oy, Hn)
            return x, x + 3 * k, y + (lh + 2 * k if label else 0) + mh / 2

        def live(cv, ox, oy, Wn, Hn, a, now):  # the bars, which move with your voice
            _, mx, my = meter_at(ox, oy, Hn)
            lvl = self.level if state in MIC_STATES else 0.0
            face.meter(cv, mx, my, 15 * k, bars, lvl, now - self.t0, a)

        def live_box(ox, oy, Wn, Hn):  # all the bars can reach, and short of where the words start
            x, _, my = meter_at(ox, oy, Hn)
            return x - 2, my - 7.5 * k - 3, x + bar_w - 2, my + 7.5 * k + 3

        def draw(cv, ox, oy, Wn, Hn, a, now):
            x, y = origin(ox, oy, Hn)
            if bars:
                x += bar_w
            if label:
                cv.text(self.f_label.render(label), x - 2, y, lab_colour, a)
                y += lh + 2 * k
            for line in lines:
                lx = x
                for run in self._runs(line):
                    s = " ".join(word for word, _ in run)
                    kept = run[0][1]
                    cover = f.render(s)
                    cv.text(cover, lx - 2, y, th["muted"] if (quiet or not kept) else th["text"], a)
                    rw = f.measure(s)
                    if not kept:  # struck out, as Nixi shows it
                        sy, lw = y + mh * 0.54, max(1.0, 1.3 * k)
                        cv.shape(lambda xs, ys, lx=lx, rw=rw, sy=sy, lw=lw: face.rbox(xs, ys, lx + rw / 2, sy, rw / 2,
                                                                                     lw / 2, lw / 2),
                                 (lx - 1, sy - lw, lx + rw + 1, sy + lw), th["muted"], a)
                    lx += rw + space
                y += mh
        key = ("cap", state, label, tuple(tuple(x) for x in lines), bool(bars))
        return Caption(key, w, h, draw, animated=bool(bars), live=live if bars else None,
                       live_box=live_box if bars else None)

    def _wrap(self, tokens, width, rows, newest, f=None):
        """Words with whether each is kept, in lines no wider than width: the newest rows while words come in,
        else the first ones, with an ellipsis where some were left out. f: the font, f_main unless said."""
        f = f or self.f_main
        space = f.measure(" ") or 4
        lines, cur, cur_w = [], [], 0.0
        for word, kept in tokens:
            w = f.measure(word)
            if w > width:
                word = f.fit(word, width)
                w = f.measure(word)
            if cur and cur_w + space + w > width:
                lines.append(cur)
                cur, cur_w = [], 0.0
            cur_w += (space if cur else 0) + w
            cur.append((word, kept))
        if cur:
            lines.append(cur)
        if len(lines) > rows:
            if newest:
                lines = lines[-rows:]
                lines[0] = [("\u2026", True)] + lines[0]
            else:
                lines = lines[:rows]
                word, kept = lines[-1][-1]
                lines[-1][-1] = (word + "\u2026", kept)
        return lines

    @staticmethod
    def _runs(line):
        runs = []
        for word, kept in line:
            if runs and runs[-1][0][1] == kept:
                runs[-1].append((word, kept))
            else:
                runs.append([(word, kept)])
        return runs

    def _row(self, key, kind, expr, left=None, right=None, hot=(), wander=True, rate=0, animated=False, press=None,
             tint=None, aura=None, lively=None, eyes=None):
        """The small island: something on the left, her eyes, something on the right. left and right are
        (width, draw(cv, x, cy, a, now)) or None. tint: their glow's colour on the capsule; eyes: the capsule's own
        (_face) instead; aura and lively: as Layout has them."""
        k, th = self.k, self.theme()
        if self.style == "capsule":  # her eyes in the middle, on glass
            return self._capsule(key, kind, [left, eyes or self._face(expr, tint), right], hot=hot, rate=rate,
                                 animated=animated, press=press, wander=wander, aura=aura, lively=lively)
        H = self.COMPACT_H * k
        size = self.SMALL_EYES * k
        eyes_w = 2.6 * size if self.face_style == "eyes" else 0
        pad, gap = 15 * k, 11 * k
        parts = [p for p in (left, (eyes_w, None) if eyes_w else None, right) if p]
        inner = sum(p[0] for p in parts) + gap * (len(parts) - 1)
        W = max(84 * k, inner + 2 * pad)

        def draw(cv, ox, oy, Wn, Hn, a, now):
            x = ox + Wn / 2 - inner / 2
            cy = oy + Hn / 2
            if left:
                left[1](cv, x, cy, a, now)
                x += left[0] + gap
            if eyes_w:
                e, open_, lx, ly, _ = self.eye
                face.draw_eyes(cv, x + eyes_w / 2, cy, size, e, open_, (lx, ly), 0.0, now - self.t0, th["eyes"],
                               th["glow"], a)
                x += eyes_w + gap
            if right:
                right[1](cv, x, cy, a, now)
        return Layout(key, kind, W, H, draw, hot=hot, eyes=expr if eyes_w else None, animated=animated, rate=rate,
                      wander=wander, press=press, aura=aura, lively=lively)

    def _idle(self):
        if self.style == "capsule":
            return self._capsule_idle()
        return self._row(("idle",), "idle", "open")

    def _slot_text(self, text, colour, font=None):
        font = font or self.f_compact
        cover = font.render(text)
        w = font.measure(text)

        def draw(cv, x, cy, a, now):
            cv.text(cover, x - 2, cy - font.line / 2 - 1, colour, a)
        return w, draw

    def _copied(self, act):
        """What you just copied, or a shortcut you just pressed, answered the way Glance's notch does it (30 October
        2026): its glyph in its colour and its word one side of her eyes (SHORTCUTS: "Copied", "Pasted", "Undo" and
        the rest), the other the start of what it was, or the app it was in, in quieter words; a picture or files just
        say so. The same one again soon after counts up, "Undo x3" (_again)."""
        k, th = self.k, self.theme()
        d = act.data if isinstance(act.data, dict) else {}
        how = d.get("how") if d.get("how") in SHORTCUTS else "copy"
        word, colour = SHORTCUTS[how]
        if how in ("copy", "cut"):
            word = {"picture": f"Picture {word.lower()}", "files": f"Files {word.lower()}"}.get(d.get("what"), word)
        times = int(d.get("times") or 1)
        if times > 1:
            word += f" \u00d7{times}"
        font, g = self.f_compact, 15 * k

        def mark(cv, x, cy, a, now):
            _shortcut_glyph(cv, how, x + g / 2, cy, g, colour if how != "copy" else th["text"], th["body"], a)
            cv.text(font.render(word), x + g + 7 * k - 2, cy - font.line / 2 - 1, th["text"], a)
        text = self.f_label.fit(str(d.get("text") or ("On the clipboard" if how == "screenshot" else "")), 170 * k)
        right = self._slot_text(text, th["muted"], self.f_label) if text else None
        return self._row(("copied", word, text), "copied", "happy", (g + 7 * k + font.measure(word), mark), right,
                         wander=False, tint=colour if how != "copy" else None)

    def _again(self, act):
        """True if act is the popup up now said again, the volume moved on or Undo pressed again, which it becomes in
        place, for longer and counting up, rather than another popup after it (as Glance's notch keeps one up while
        you hold the volume key)."""
        head = self.popup
        if head is None or head.until is None or head.kind != act.kind or act.kind not in ("level", "copied") or \
                not isinstance(head.data, dict) or not isinstance(act.data, dict):
            return False
        if act.kind == "level":
            if head.data.get("what") != act.data.get("what"):
                return False
        elif act.data.get("how") not in REPEATS or head.data.get("how") != act.data.get("how"):
            return False
        else:
            act.data["times"] = int(head.data.get("times") or 1) + 1
        now = time.time()
        head.data, head.at = act.data, now
        head.until = max(head.until, now + (act.seconds or 1.6))
        self._light_for(head, now)
        return True

    def _level(self, act):
        """The volume or the brightness as it changes (island_plugins.Levels), as Glance's notch shows it: its glyph
        in its colour one side of her eyes, a slim bar as far as it's set and the level the other, and her light along
        her bottom as far (_light_for)."""
        k, th = self.k, self.theme()
        d = act.data if isinstance(act.data, dict) else {}
        what = "brightness" if d.get("what") == "brightness" else "volume"
        level, muted = max(0, min(100, int(d.get("level") or 0))), bool(d.get("muted"))
        colour = th["muted"] if muted else SLIDER_TINTS[what]
        g, font = 17 * k, self.f_compact
        bw, bh = 58 * k, 5 * k
        words = "Muted" if muted else f"{level}%"
        tw = font.measure("100%")

        def glyph(cv, x, cy, a, now):
            if what == "volume":
                face.speaker_glyph(cv, x + g / 2, cy, g, colour, a, level / 100, muted)
            else:
                face.sun_glyph(cv, x + g / 2, cy, g, colour, a, level / 100)

        def bar(cv, x, cy, a, now):
            frac = 0.0 if muted else level / 100
            box = (x - 1, cy - bh, x + bw + 1, cy + bh)
            cv.shape(lambda xs, ys: face.rbox(xs, ys, x + bw / 2, cy, bw / 2, bh / 2, bh / 2), box,
                     _mix(th["body"], th["text"], 0.14), a)
            if frac > 0:
                fw = max(bh, bw * frac)
                cv.shape(lambda xs, ys: face.rbox(xs, ys, x + fw / 2, cy, fw / 2, bh / 2, bh / 2), box, colour, a)
            cover = font.render(words)
            cv.text(cover, x + bw + 8 * k - 2, cy - font.line / 2 - 1, th["text"], a)
        return self._row(("level", what, level, muted), "level", "open", (g, glyph), (bw + 8 * k + tw, bar),
                         wander=False, tint=None if muted else colour)

    def _track(self, act):
        """Another song, peeking for a moment as Glance's notch shows the next track (31 October 2026): its cover
        one side of her eyes, its name the other, after "Next" or "Back" when you skipped to it."""
        k, th = self.k, self.theme()
        d = act.data if isinstance(act.data, dict) else {}
        s = round(22 * k)
        pic = art.rounded(_resize(d["art"], s), 5 * k) if d.get("art") is not None else None
        if pic is None:
            pic = art.badge(d.get("app") or "Music", s, self._text)
        way = {"next": "Next", "previous": "Back"}.get(d.get("way"))
        words = self.f_compact.fit(str(d.get("title") or ""), 170 * k)
        font, small = self.f_compact, self.f_label

        def cover(cv, x, cy, a, now):
            cv.image(pic, x, cy - s / 2, a)

        def name(cv, x, cy, a, now):
            if way:
                tag = small.render(way)
                cv.text(tag, x - 2, cy - small.line / 2 - 1, th["muted"], a)
                x += tag.shape[1] + 6 * k
            cv.text(font.render(words), x - 2, cy - font.line / 2 - 1, th["text"], a)
        width = font.measure(words) + ((small.measure(way) + 6 * k) if way else 0)
        return self._row(("track", d.get("title"), d.get("artist"), way), "track", "headphones", (s, cover),
                         (width, name), wander=False, tint=tuple(d["tint"]) if d.get("tint") is not None else
                         art.brand(d.get("app") or ""))

    def _peek(self, act):
        """A notification's first moment, small, as Glance's notch peeks before it opens (30 October 2026, its demo):
        the app's badge and its name one side of her eyes, glowing in its colour; it opens PEEK_FOR seconds later, a
        light sweeping over her as it does (_sweep)."""
        k, th = self.k, self.theme()
        d = act.data if isinstance(act.data, dict) else {}
        app = str(d.get("app") or "Notification")
        size = round(18 * k)
        logo = self._logo(app)
        right = self._slot_text(self.f_compact.fit(app, 130 * k), th["text"])
        return self._row(("peek", app, id(act)), "peek", "surprised", (size, logo), right, wander=False,
                         tint=art.brand(app))

    def _drop_zone(self, now):
        """Files dragged over her, as Glance's notch opens for them (30 October 2026, the owner's screenshot of it,
        AirDrop left out): her eyes at the top, under them a dashed place to drop them, saying what they are, and in
        it the Shelf, lit in its colour with its dashes going round while they're over it, with how many are on it
        already. Dropped anywhere on her, they go on the shelf (_dropped), which opens to show them."""
        k, th = self.k, self.theme()
        W, pad = self.HUB_W * k, self.CARD_PAD * k
        drag = self.drag_over or {}
        paths = drag.get("paths") or []
        head_h = 26 * k
        zy, zone_h = pad + head_h + 10 * k, 152 * k
        H = zy + zone_h + pad
        tx0, tx1, ty0, ty1 = pad + 14 * k, W - pad - 14 * k, zy + 46 * k, zy + zone_h - 14 * k  # the Shelf's tile
        over = False
        rect = getattr(self, "island_rect", None)
        if drag.get("x") is not None and rect is not None:
            lx, ly = drag["x"] - self.origin.x - rect[0], drag["y"] - self.origin.y - rect[1]
            over = tx0 - 8 * k <= lx <= tx1 + 8 * k and ty0 - 8 * k <= ly <= ty1 + 8 * k
        f_t, f_s = self.f_title, self.f_small
        if len(paths) == 1:
            name = os.path.basename(paths[0].rstrip("\\/")) or paths[0]
            room = W - 2 * pad - 54 * k - f_t.measure("Drop  here")
            title = f"Drop {f_t.fit(name, room)} here"
        else:
            title = f"Drop {len(paths)} files here" if paths else "Drop files here"
        count = len(self.shelf_items())
        sub = f"{count} on it already" if count else "Kept here till you drag it out"
        expr = "happy" if over else "surprised"
        me = self._face(expr, VIOLET)
        ew = me[0]
        tile = _mix(th["body"], VIOLET, 0.16)

        def draw(cv, ox, oy, Wn, Hn, a, now):
            cy = oy + pad + head_h / 2
            me[1](cv, ox + Wn / 2 - ew / 2, cy, a, now)
            zx0, zx1, zy0 = ox + pad, ox + Wn - pad, oy + zy
            _dashed(cv, zx0, zy0, zx1, zy0 + zone_h, 14 * k, th["muted"], a * 0.55, k)
            face.tray_glyph(cv, zx0 + 22 * k, zy0 + 23 * k, 16 * k, th["muted"], a)
            cv.text(f_t.render(title), zx0 + 38 * k - 2, zy0 + 23 * k - f_t.line / 2 - 1, th["muted"], a)
            bx0, bx1, by0, by1 = ox + tx0, ox + tx1, oy + ty0, oy + ty1
            if over:
                cv.shape(lambda xs, ys: face.rbox(xs, ys, (bx0 + bx1) / 2, (by0 + by1) / 2, (bx1 - bx0) / 2,
                                                  (by1 - by0) / 2, 12 * k), (bx0 - 1, by0 - 1, bx1 + 1, by1 + 1), tile, a)
            _dashed(cv, bx0, by0, bx1, by1, 12 * k, VIOLET if over else th["muted"], a * (1.0 if over else 0.6), k,
                    shift=(now * 22 * k) if over else 0.0)
            gx = (bx0 + bx1) / 2
            face.tray_glyph(cv, gx, by0 + 24 * k, 20 * k, VIOLET if over else th["text"], a)
            word = f_t.render("Shelf")
            cv.text(word, gx - word.shape[1] / 2, by0 + 39 * k, th["text"], a)
            words = f_s.render(sub)
            cv.text(words, gx - words.shape[1] / 2, by0 + 39 * k + f_t.line, th["muted"], a)
        return Layout(("drop", over, title, count), "drop", W, H, draw, radius=self._corner(),
                      hot=[("stay", 0, 0, W, H)], eyes=me[2], face=True, animated=over)

    def _dragging(self, what, x, y, paths):
        """Files dragged over her (shelf.Target): noted for _hover_poll to show (_drop_zone), and dropped ones handed
        on to be put on the shelf from _events, as Drops' are. This runs inside Windows' call: never Tk."""
        now = time.time()
        if what == "enter" or (what == "over" and self.drag_over is None):
            self.drag_over = {"paths": list(paths), "x": x, "y": y, "left": None}
        elif what == "over":
            self.drag_over = dict(self.drag_over, x=x, y=y, left=None)
        elif what == "leave" and self.drag_over is not None:
            self.drag_over = dict(self.drag_over, left=now)
        elif what == "drop":
            self.drag_over = None
            if paths:
                self.runner.post(("dropped", list(paths)))
        self.drag_note = now

    def _sweeping(self, now):
        """True while a light sweeps over her as she opens (_sweep)."""
        lay = getattr(self, "layout", None)
        return lay is not None and self.lights and lay.kind != "harry" and lay.h >= 70 * self.k and \
            0.0 <= now - getattr(self, "changed", 0.0) < self.SWEEP_FOR

    def _sweep(self, now, ox, oy, W, H, r):
        """A light sweeping over her once as she opens into something bigger, as Glance's card opens (30 October
        2026, its demo): a soft slanted band, white on a dark island and her light's colour on a light one, kept inside
        her. (draw(cv, a), 1.0) for _paint, or None."""
        if not self._sweeping(now):
            return None
        k, th = self.k, self.theme()
        dark = th["body"][0] < 0.5
        tint = (1.0, 1.0, 1.0) if dark or self.lit is None else self.lit.colour
        u = (now - self.changed) / self.SWEEP_FOR
        band, slant = 50 * k, 0.35
        cx = ox - band - slant * H + (W + 2 * (band + slant * H)) * (1 - (1 - u) ** 2)
        strength = math.sin(math.pi * u) * (0.2 if dark else 0.14)
        cy = oy + H / 2
        box = (max(ox, cx - band - slant * H), oy, min(ox + W, cx + band + slant * H), oy + H)
        if box[2] <= box[0]:
            return None

        def draw(cv, a):
            for w, s in ((band, 0.3), (band * 0.55, 0.55), (band * 0.22, 1.0)):
                cv.shape(lambda xs, ys, w=w: np.maximum(np.abs(xs - cx + (ys - cy) * slant) - w / 2,
                                                        face.rbox(xs, ys, ox + W / 2, cy, W / 2, H / 2, r)),
                         box, tint, a * strength * s)
        return draw, 1.0

    def _battery(self, act):
        k, th = self.k, self.theme()
        d = act.data
        pct, charging, event = d["percent"], d["charging"], d["event"]
        fill = RED if pct <= 20 and not charging else GREEN if charging else th["text"]
        bh = 11 * k

        def glyph(cv, x, cy, a, now):
            face.battery(cv, x, cy, bh, pct, th["text"], fill, charging, a)
        left = (bh * 1.9 + 3 * k, glyph)
        show_pct = plugins.get_options("battery").get("percent", True)
        word = "Full" if event == "full" else f"{pct}%" if show_pct else ("Charging" if charging else "")
        right = self._slot_text(word, fill if fill != th["text"] else th["text"]) if word else None
        expr = "sad" if event == "low" else "open"
        return self._row(("battery", pct, charging, event, word), "battery", expr, left, right)

    def _timer(self, act):
        """A running timer, small: a ring for what's left, her eyes glowing orange, and how long in orange figures.
        In its last seconds (Timers' "urgent", 30 October 2026) the figures beat once a second and the island glows
        orange round it, breathing, as a phone's does before it rings."""
        k, th = self.k, self.theme()
        d = act.data
        font = self.f_compact
        slot_w = font.measure("88:88") + 2 * k
        urgent = bool(d.get("urgent"))
        ink = self._ink(ORANGE) if self.style == "capsule" else ORANGE  # deeper on light glass, as "40%" is

        def ring(cv, x, cy, a, now):
            left = max(0.0, (d["end"] - now) / d["total"])
            face.ring(cv, x + 8 * k, cy, 7 * k, 2.4 * k, left, ORANGE, th["track"], a)

        def clock(cv, x, cy, a, now):
            secs = max(0, int(math.ceil(d["end"] - now)))
            h, rem = divmod(secs, 3600)
            text = f"{h}:{rem // 60:02d}:{rem % 60:02d}" if h else f"{rem // 60}:{rem % 60:02d}"
            cv.text(font.render(text), x - 2, cy - font.line / 2 - 1, ink, a * _beat(d["end"] - now, urgent))
        return self._row(("timer", d["label"], d["end"]), "timer", "open", (16 * k, ring), (slot_w, clock),
                         rate=12 if urgent else 1, tint=ORANGE, aura=(ORANGE, "breathe") if urgent else None)

    def _media(self, act):
        k, th = self.k, self.theme()
        d = act.data
        size = round(22 * k)
        pic = art.rounded(_resize(d["art"], size), 6 * k) if d.get("art") is not None else None
        if pic is None:
            pic = art.badge(d["app"], size, self._text)

        tint = d.get("tint") if self.style == "capsule" else None  # the cover's own colour (island_art.tint)

        def cover(cv, x, cy, a, now):
            if tint is not None and d["playing"]:  # a glow round the cover in its colour, as bloom's has
                y0 = cy - size / 2
                cv.shape(lambda xs, ys: face.rbox(xs, ys, x + size / 2, cy, size / 2 - 1, size / 2 - 1, 6 * k),
                         (x - 9 * k, y0 - 9 * k, x + size + 9 * k, y0 + size + 9 * k), tint, a, 0.5, 3.2 * k)
            cv.image(pic, x, cy - size / 2, a)

        colour = (tint or GREEN) if d["playing"] else th["muted"]

        def bars(cv, x, cy, a, now):
            lvl = getattr(self.runner.plugin("media"), "level", 0.0) if d["playing"] else 0.0
            self._music_bars(cv, x + 1 * k, cy, 14 * k, colour, min(1.0, lvl * 2.2) if d["playing"] else 0.0,
                             d["playing"], now, a)
        expr = "headphones" if d["playing"] else "open"
        return self._row(("media", d["title"], d["artist"], d["playing"], id(d.get("art"))), "media", expr,
                         (size, cover), (18 * k, bars), hot=[("open", 0, 0, 10000, 10000)],
                         rate=24 if d["playing"] else 0, tint=tint if d["playing"] else None)

    def _media_card(self, act):
        if self.style == "capsule":
            return self._glass_media(act)
        k, th = self.k, self.theme()
        d = act.data
        W = self.CARD_W * k
        pad, art_s = 14 * k, round(52 * k)
        pic = art.rounded(_resize(d["art"], art_s), 9 * k) if d.get("art") is not None else None
        if pic is None:
            pic = art.badge(d["app"], art_s, self._text)
        btn, gapb = 28 * k, 4 * k
        controls_w = 3 * btn + 2 * gapb
        tx = pad + art_s + 12 * k
        tw = W - tx - pad - controls_w - 8 * k
        title = self.f_title.fit(d["title"], tw)
        sub = self.f_label.fit(" \u00b7 ".join(x for x in (d["artist"], d["app"]) if x), tw)
        bar_y = pad + art_s + 13 * k
        H = bar_y + 4 * k + 7 * k + self.f_small.line + pad * 0.7
        cy = pad + art_s / 2
        bx0 = W - pad - controls_w
        hot = [("previous", bx0, cy - btn / 2, bx0 + btn, cy + btn / 2),
               ("toggle", bx0 + btn + gapb, cy - btn / 2, bx0 + 2 * btn + gapb, cy + btn / 2),
               ("next", bx0 + 2 * (btn + gapb), cy - btn / 2, bx0 + 3 * btn + 2 * gapb, cy + btn / 2),
               ("open", 0, 0, bx0 - 4 * k, bar_y - 2 * k)]

        def draw(cv, ox, oy, Wn, Hn, a, now):
            cv.image(pic, ox + pad, oy + pad, a)
            cv.text(self.f_title.render(title), ox + tx - 2, oy + cy - self.f_title.line + 1, th["text"], a)
            cv.text(self.f_label.render(sub), ox + tx - 2, oy + cy + 2 * k, th["muted"], a)
            for i, (name, x0, y0, x1, y1) in enumerate(hot[:3]):
                gx, gy = ox + (x0 + x1) / 2, oy + (y0 + y1) / 2
                if name == "toggle":
                    face.play_glyph(cv, gx, gy, 18 * k, d["playing"], th["text"], a)
                else:
                    face.skip_glyph(cv, gx, gy, 14 * k, name == "next", th["text"], a)
            pos = d["position"] + ((now - d["at"]) if d["playing"] else 0.0)
            dur = d["duration"]
            frac = max(0.0, min(1.0, pos / dur)) if dur > 0 else 0.0
            x0, x1, y = ox + pad, ox + Wn - pad, oy + bar_y + 2 * k
            lw = 3.6 * k
            cv.shape(lambda xs, ys: face.rbox(xs, ys, (x0 + x1) / 2, y, (x1 - x0) / 2, lw / 2, lw / 2),
                     (x0 - 1, y - lw, x1 + 1, y + lw), th["track"], a)
            if frac > 0:
                xe = x0 + (x1 - x0) * frac
                cv.shape(lambda xs, ys: face.rbox(xs, ys, (x0 + xe) / 2, y, max(lw / 2, (xe - x0) / 2), lw / 2,
                                                  lw / 2), (x0 - 1, y - lw, xe + 1, y + lw), th["text"], a)
            if dur > 0:
                ty = y + 6 * k
                el, rest = _clock(pos), "-" + _clock(max(0.0, dur - pos))
                cv.text(self.f_small.render(el), x0 - 2, ty, th["muted"], a)
                cover = self.f_small.render(rest)
                cv.text(cover, x1 - cover.shape[1] + 2, ty, th["muted"], a)
        return Layout(("media-card", d["title"], d["artist"], d["playing"], id(d.get("art"))), "media", W, H, draw,
                      radius=self._corner(), hot=hot, rate=2)

    def _notification(self, act):
        if self.style == "capsule":
            return self._glass_note(act)
        k, th = self.k, self.theme()
        d = act.data
        W = self.CARD_W * k
        pad, bs = 14 * k, round(34 * k)
        pic = art.badge(d["app"], bs, self._text)
        tx = pad + bs + 12 * k
        tw = W - tx - pad
        head = self.f_small.fit((d["app"] + (" \u00b7 on your phone" if d.get("phone") else "")).upper(), tw - 40 * k)
        title = self.f_title.fit(d["title"] or d["app"], tw)
        lines = self.f_label.wrap(d["text"], tw, 2) if d.get("text") else []
        body = self.f_small.line + 3 * k + self.f_title.line + (2 * k + self.f_label.line * len(lines) if lines else 0)
        H = pad * 2 + max(bs, body)
        hot = [("dismiss", W - 30 * k, 0, W, 26 * k), ("open", 0, 0, W, H)]

        def draw(cv, ox, oy, Wn, Hn, a, now):
            cv.image(pic, ox + pad, oy + pad, a)
            y = oy + pad - 1 * k
            cv.text(self.f_small.render(head), ox + tx - 2, y, th["muted"], a)
            if self.hover:
                face.close_glyph(cv, ox + Wn - 18 * k, oy + 14 * k, 12 * k, th["muted"], a)
            else:
                cover = self.f_small.render("now")
                cv.text(cover, ox + Wn - pad - cover.shape[1] + 2, y, th["muted"], a)
            y += self.f_small.line + 3 * k
            cv.text(self.f_title.render(title), ox + tx - 2, y, th["text"], a)
            y += self.f_title.line + 2 * k
            for line in lines:
                cv.text(self.f_label.render(line), ox + tx - 2, y, th["text"], a * 0.86)
                y += self.f_label.line
        return Layout(("note", d["app"], d["title"], d.get("text", ""), id(act)), "notification", W, H, draw,
                      radius=self._corner(), hot=hot)

    # ------------------------------------------------------------------ cards (island_plugins.Activity)
    def _tallest_card(self):
        """A card's height with every row at its tallest (buttons, two lines and a bar) and "+N more" under them."""
        k = self.k
        row = max(self.f_label.line, self.BUTTON_H * k) + 2 * k + 2 * self.f_small.line + 9 * k
        # and room for the glass card's header (her eyes and "2 tasks", 26 px, and 10 under it) and its bars a little
        # lower: the window is built once for either style, and only what changed is ever sent (_push), so the
        # pill's picture is the same
        glass = (26 + 10) * k + plugins.CARD_ROWS * 3 * k
        return 2 * self.CARD_PAD * k + plugins.CARD_ROWS * (row + self.ROW_GAP * k) + self.f_small.line + 5 * k + glass

    @staticmethod
    def _card_rows(d):
        """A card's rows (its "rows", or the card itself as one) as many as show, and how many more there are."""
        rows = list(d.get("rows") or [d])
        return rows[:plugins.CARD_ROWS], int(d.get("more") or 0) + max(0, len(rows) - plugins.CARD_ROWS)

    def _state_colour(self, state):
        th = self.theme()
        return {"waiting_yes": ORANGE, "done": GREEN, "failed": RED}.get(state, th["muted"])

    def _glyph(self, cv, cx, cy, r, row, now, a):
        """How a row's going, small: a ring for how far it's got, a light stepping along three dots once a second
        when that isn't known, an orange ring while it waits on you, a tick once it's done, a cross if it wasn't."""
        th = self.theme()
        state, done = row.get("state") or "running", row.get("progress")
        if state == "done":
            face.tick_glyph(cv, cx, cy, 2.1 * r, GREEN, a)
        elif state in ("failed", "stopped"):
            face.close_glyph(cv, cx, cy, 2.4 * r, RED if state == "failed" else th["muted"], a)
        elif state in ("waiting_yes", "queued") or done is not None:
            part = 1.0 if state == "waiting_yes" else done or 0.0  # none yet: only its track, not a sliver at the top
            face.ring(cv, cx, cy, r, 0.34 * r, part, ORANGE if state == "waiting_yes" else BLUE if part > 0 else
                      th["track"], th["track"], a)
        else:  # the light on dot int(now) % 3: once a second, never a frame for each step of it
            step = 0.95 * r
            face.dots_row(cv, cx - step, cy, 3, step, 0.3 * r, CYAN, 0.0, (int(now) % 3) / 3 / 1.6, "busy", a)

    def _compact(self, act):
        """A card's small island while you aren't pointing at it: how its first row's going (_glyph), her eyes, and
        a few words: how far it's got, how long it's been going, or how many there are."""
        if self.style == "capsule":
            return self._capsule_task(act)
        k = self.k
        d = act.data
        rows, more = self._card_rows(d)
        lead = rows[0] if rows else {}
        font = self.f_compact
        text = d.get("short") or lead.get("status") or ""
        since = lead.get("since") if not text else None
        if not text and since is None:
            text = font.fit(str(lead.get("title") or ""), 150 * k)
        colour = self._state_colour(lead.get("state")) if not d.get("short") and lead.get("state") != "running" \
            else self.theme()["text"]
        slot_w = font.measure("88:88") + 2 * k if since is not None else font.measure(text)

        def glyph(cv, x, cy, a, now):
            self._glyph(cv, x + 8 * k, cy, 7 * k, lead, now, a)

        def words(cv, x, cy, a, now):
            cv.text(font.render(text or _clock(max(0.0, now - since))), x - 2, cy - font.line / 2 - 1, colour, a)
        expr = {"done": "happy", "failed": "sad", "waiting_yes": "surprised"}.get(lead.get("state"), "open")
        live = any((r.get("state") or "running") == "running" for r in rows)
        return self._row(("card-row", act.plugin, text, since is not None, repr(lead), len(rows) + more), "card",
                         expr, (16 * k, glyph), (slot_w, words) if slot_w else None, hot=[("pin", 0, 0, 10000, 10000)],
                         rate=1 if live else 0, press={"pin": (act.plugin, "pin", None, False)})

    def _card(self, act):
        """A plugin's card, open while you point at it or after a click on it: up to CARD_ROWS rows, each with how
        it's going (_glyph), its title, a few words at its right, a line or two under it, a bar for how far it's got
        and its buttons, then "+N more". The Tasks plugin's list is one; any plugin can show one without this file
        knowing it (island_plugins.Activity). A clock that's running moves once a second, never every frame."""
        if self.style == "capsule":
            return self._glass_card(act)
        k, th = self.k, self.theme()
        rows, more = self._card_rows(act.data)
        W = self.CARD_W * k
        pad, gap = self.CARD_PAD * k, self.ROW_GAP * k
        hot, press, parts, y = [], {}, [], pad
        for row in rows:
            h, draw_row = self._card_row(row, y, W, pad, act.plugin, hot, press)
            parts.append(draw_row)
            y += h + gap
        tail = f"+{more} more" if more else ""
        H = min(self.island_max_h, y - gap + pad + (self.f_small.line + 5 * k if tail else 0))
        hot.append(("pin", 0, 0, W, H))  # anywhere else on it keeps it open, or lets it go again
        press["pin"] = (act.plugin, "pin", None, False)

        def draw(cv, ox, oy, Wn, Hn, a, now):
            for draw_row in parts:
                draw_row(cv, ox, oy, a, now)
            if tail:
                cv.text(self.f_small.render(tail), ox + pad + 27 * k - 2, oy + y - gap + 5 * k, th["muted"], a)
        live = any((r.get("state") or "running") == "running" for r in rows)
        return Layout(("card", act.plugin, repr(rows), more), "card", W, H, draw, radius=self.corner * k, hot=hot,
                      rate=1 if live else 0, press=press)

    def _card_row(self, row, y0, W, pad, plugin, hot, press):
        """One row of a card from y0: (its height, draw(cv, ox, oy, a, now)). Its buttons go in hot and press."""
        k, th = self.k, self.theme()
        small, label = self.f_small, self.f_label
        bh, bpad, bgap = self.BUTTON_H * k, 10 * k, 6 * k
        buttons, x = [], W - pad
        for b in reversed(row.get("buttons") or []):
            words = str(b.get("label") or b.get("name") or "")
            bw = small.measure(words) + 2 * bpad
            buttons.insert(0, (b, words, x - bw, x))
            x -= bw + bgap
        right = x if buttons else W - pad  # where the words at its right end
        status, since = row.get("status") or "", row.get("since")
        since = since if not status else None
        sw = small.measure(status) if status else small.measure("88:88") if since is not None else 0
        tx = pad + 27 * k
        title = label.fit(" ".join(str(row.get("title") or "").split()), max(20 * k, right - tx - sw - 8 * k))
        lines = [small.fit(" ".join(str(t).split()), right - tx) for t in (row.get("lines") or [])[:2] if t]
        done = row.get("progress")
        h1 = max(label.line, bh if buttons else 0)
        h = h1 + (2 * k + small.line * len(lines) if lines else 0) + (9 * k if done is not None else 0)
        cy = y0 + h1 / 2
        for b, words, bx0, bx1 in buttons:
            name = f"b{len(press)}"
            press[name] = (plugin, b.get("name"), b.get("data"), bool(b.get("careful", b.get("name") == "approve")))
            hot.append((name, bx0 - 2 * k, cy - bh / 2 - 2 * k, bx1 + 2 * k, cy + bh / 2 + 2 * k))
        state_colour = self._state_colour(row.get("state"))

        def draw(cv, ox, oy, a, now):
            self._glyph(cv, ox + pad + 9 * k, oy + cy, 7 * k, row, now, a)
            cv.text(label.render(title), ox + tx - 2, oy + cy - label.line / 2 - 1, th["text"], a)
            words = status or (_clock(max(0.0, now - since)) if since is not None else "")
            if words:
                cover = small.render(words)
                cv.text(cover, ox + right - cover.shape[1] + 2, oy + cy - small.line / 2 - 1, state_colour, a)
            for b, text, bx0, bx1 in buttons:
                approve = b.get("name") == "approve"
                fill, ink = (GREEN, (0.02, 0.02, 0.03)) if approve else \
                    (th["track"], RED if b.get("name") == "stop" else th["text"])
                bx, by, bw = ox + (bx0 + bx1) / 2, oy + cy, (bx1 - bx0) / 2
                cv.shape(lambda xs, ys, bx=bx, by=by, bw=bw: face.rbox(xs, ys, bx, by, bw, bh / 2, bh / 2),
                         (ox + bx0 - 1, by - bh / 2 - 1, ox + bx1 + 1, by + bh / 2 + 1), fill, a)
                cover = small.render(text)
                cv.text(cover, bx - cover.shape[1] / 2, by - small.line / 2 - 0.5, ink, a)
            ly = oy + y0 + h1 + 2 * k
            for line in lines:
                cv.text(small.render(line), ox + tx - 2, ly, th["muted"], a)
                ly += small.line
            if done is not None:  # how far it's got, as the music's bar (_media_card)
                x0, x1, by, lw = ox + tx, ox + right, ly + 4 * k, 3.2 * k
                cv.shape(lambda xs, ys: face.rbox(xs, ys, (x0 + x1) / 2, by, (x1 - x0) / 2, lw / 2, lw / 2),
                         (x0 - 1, by - lw, x1 + 1, by + lw), th["track"], a)
                if done > 0:
                    xe = x0 + (x1 - x0) * min(1.0, done)
                    cv.shape(lambda xs, ys: face.rbox(xs, ys, (x0 + xe) / 2, by, max(lw / 2, (xe - x0) / 2), lw / 2,
                                                      lw / 2), (x0 - 1, by - lw, xe + 1, by + lw),
                             GREEN if row.get("state") == "done" else BLUE, a)
        return h, draw

    # ------------------------------------------------------------------ the glass capsule (27 October 2026)
    def _corner(self):
        """A card's corners: the Corners setting on the pill, the glass card's own 18 px on the capsule."""
        return (self.GLASS_CORNER if self.style == "capsule" else self.corner) * self.k

    def _mood(self, now):
        """Her reaction while it lasts (thanks, done, a notification), or None. Read here, not from face.Eyes.update:
        the capsule asks for no frame while one lasts, only one when it's over (_capsule_wait)."""
        e = self.eyes
        return e.mood if e.mood and now < e.mood_until else None

    def _eyes_w(self):
        """How much room her eyes have on the capsule: wider than the pill's small rows give them (2.6 sizes), as
        hearts, headphones and the sparkles round them took the clock's room and the capsule's edge, and a glance
        to one side all but touched what's beside them (27 October previews)."""
        return 3.2 * self.SMALL_EYES * self.k

    def _face(self, expr, tint=None, voice=False, busy=False, lively=0.0):
        """Her eyes as a part of a capsule's row: (width, draw, expr). The pill's own (face.draw_eyes, face.Eyes:
        her blinks, her glances about, her reactions), as big; expr: how they look (face.MOODS), unless a reaction's
        on. tint: the colour of what's going on, in their glow (MOOD_TINTS while a reaction lasts); voice: they
        bounce with it, as on the pill's big face; busy: she's thinking or working. With the Face setting on the
        orb (28 October 2026), the orb in their place, rippling with the voice, a light running round it
        while she's busy and breathing when nothing's on, blinking and looking as they would. Asleep in dream mode
        (30 October 2026), with room on her right for the z's that rise from her till lively (a time) is past."""
        k, th = self.k, self.theme()
        size, w = self.SMALL_EYES * k, self._eyes_w()
        orb = self.face_style == "orb"
        zs = 0.9 * size if expr == "dream" else 0.0
        w += zs

        def draw(cv, x, cy, a, now):
            cx = x + (w - zs) / 2
            self.face_at = (cx + self.patch_at[0], cy + self.patch_at[1])  # in the window, for _follow
            e, open_, lx, ly, _ = self.eye
            colour = MOOD_TINTS.get(self._mood(now), tint)
            halo = None if colour is None or not th["glow"] else \
                tuple(TINT * c + (1 - TINT) * w_ for c, w_ in zip(colour, th["eyes"]))
            if zs and e == "dream" and now < lively:
                face.zzz(cv, cx + size * 1.35, cy - size * 0.15, size, now - self.t0, th["eyes"], a, halo)
            if orb:
                face.draw_orb(cv, cx, cy, 9 * k, "voice" if voice else "busy" if busy else "idle",
                              self.level if voice else 0.0, now - self.t0, open_, (lx, ly), th["eyes"], th["glow"], a,
                              halo)
                return
            face.draw_eyes(cv, cx, cy, size, e, open_, (lx, ly), self.level if voice else 0.0, now - self.t0,
                           th["eyes"], th["glow"], a, halo)
        return w, draw, expr

    def _capsule(self, key, kind, parts, hot=(), rate=0, animated=False, press=None, cap=None, under=None,
                 wander=True, aura=None, lively=None, tall=False):
        """The capsule's row: parts, (width, draw(cv, x, cy, a, now)) each, her eyes (_face, which also says how
        they look) among them, side by side. Eyes at an end sit in the round end, their glow clear of its edge.
        under: drawn after them, below the capsule if it likes (a task's progress line). wander: her eyes glance
        about when nothing else says where to look. As it comes in, the rest come out from behind her eyes, the way
        a phone's island brings its parts out from behind its camera, and as it goes they go back in (30 October
        2026). aura and lively: as Layout has them. tall: room for two lines of words, as a phone's AirPods have."""
        k = self.k
        H = (44 if tall else self.COMPACT_H) * k
        parts = [p for p in parts if p]
        gap = 10 * k
        edge = 16 * k  # eyes at an end: room in the round end for their glow and a sparkle
        left = edge if len(parts[0]) == 3 else 15 * k
        right = edge if len(parts[-1]) == 3 else 15 * k
        inner = sum(p[0] for p in parts) + gap * (len(parts) - 1)
        W = max(H, left + inner + right)
        expr = next((p[2] for p in parts if len(p) == 3), "open")
        offsets, x = [], 0.0  # where each part starts along the row
        for p in parts:
            offsets.append(x)
            x += p[0] + gap
        eyes = next((off + p[0] / 2 for p, off in zip(parts, offsets) if len(p) == 3), None)  # her eyes' middle

        def draw(cv, ox, oy, Wn, Hn, a, now):
            x0 = ox + left + (Wn - (left + inner + right)) / 2
            cy = oy + Hn / 2
            out = 1 - (1 - min(1.0, a)) ** 3  # how far out from behind her eyes the rest have come
            for p, off in zip(parts, offsets):
                x = x0 + off
                if out < 1 and eyes is not None and len(p) != 3:
                    x += (eyes - off - p[0] / 2) * (1 - out)
                p[1](cv, x, cy, a, now)
            if under is not None:
                under(cv, ox, oy, Wn, Hn, a, now)
        return Layout(key, kind, W, H, draw, cap=cap, hot=hot, eyes=expr, animated=animated, rate=rate,
                      wander=wander, press=press, face=True, aura=aura, lively=lively)

    def _capsule_idle(self):
        """Nothing going on: just her eyes, glancing about or at the mouse while it moves. Drawn again when she
        blinks or glances, a reaction comes and goes or the mouse moves her eyes a pixel, and never in between. The
        time was beside them till the owner asked for it to go (27 October)."""
        # the orb breathes while nothing's on, 10 frames a second: about 2 ms each, so it costs next to nothing.
        # A click on her eyes opens the panels (30 October 2026), when they're on: only then does it take clicks
        hot = [("hub", 0, 0, 10000, 10000)] if self._hub_on() else []
        parts = self._status_parts()
        return self._capsule(("idle", tuple(p[3] for p in parts)), "idle",
                             [p[:2] for p in parts if p[2] == "left"] + [self._face("open")] +
                             [p[:2] for p in parts if p[2] == "right"], hot=hot,
                             rate=10 if self.face_style == "orb" else 0)

    def _ink(self, colour):
        """A colour for words on the glass: as it is on dark glass, darker on light glass, where amber "40%" was
        hard to read (27 October previews), and a dim one lighter on dark glass: dream mode's indigo was 3.4 to 1
        on it, and is 5.8 to 1 so (30 October). The others are bright enough already, and stay as they were."""
        if self.theme()["body"][0] > 0.5:  # light glass, or paper
            return tuple(c * 0.72 for c in colour)
        if _luma(colour) < 0.2:
            return _mix(colour, (1.0, 1.0, 1.0), 0.3)
        return colour

    def _capsule_harry(self, state, expr, colour, mode, cap, badge, turn):
        """Her turn in the capsule: her eyes as the pill has them for it (HARRY), glowing in its colour, the app you're
        in, the dots that move with a voice, how far her turn's got and how many go on meanwhile, the words under
        it as ever."""
        k = self.k
        icon = self._front_icon(round(17 * k))
        n, step, r = 5, 8.6 * k, 2.4 * k
        gr = 5.5 * k
        parts = [self._face(expr, colour, voice=state in MIC_STATES or state == "speaking", busy=mode == "busy")]
        if icon is not None:
            parts.append((icon.shape[1], lambda cv, x, cy, a, now: cv.image(icon, x, cy - icon.shape[0] / 2, a)))

        def dots(cv, x, cy, a, now):  # as the pill has them (_harry)
            t = now - self.t0
            if mode == "ring":
                total = float(getattr(sys.modules.get("siri"), "FOLLOW_UP", 8.0))
                left = max(0.0, 1 - (now - self.since) / total)
                face.ring(cv, x + (n - 1) * step / 2 + r, cy, 6.5 * k, 2.2 * k, left, ORANGE, self.theme()["track"],
                          a)
            else:
                dots_mode = "voice" if mode in ("voice", "her") else "busy" if mode == "busy" else "still"
                face.dots_row(cv, x + r, cy, n, step, r, colour, self.level if mode in ("voice", "her") else 0.0, t,
                              dots_mode if dots_mode != "still" else "voice", a * (0.75 if mode == "still" else 1))
        if self.face_style != "orb" or mode == "ring":  # the orb shows the voice and the work itself
            parts.append(((n - 1) * step + 2 * r, dots))
        if turn:
            parts.append((2 * gr, lambda cv, x, cy, a, now: self._glyph(cv, x + gr, cy, gr, turn, now, a)))
        if badge:
            br = self._badge_r(badge)
            parts.append((2 * br, lambda cv, x, cy, a, now: self._badge(cv, x + br, cy, badge, a)))
        key = ("harry", state, "capsule", badge, turn and (turn.get("status"), turn.get("progress")))
        # her eyes do as her turn says (looking up while she thinks, about while she works), as on the pill
        return self._capsule(key, "harry", parts, animated=state not in ("error", "note", "phone"), cap=cap,
                             wander=False, aura=self._turn_aura(state, colour))

    @staticmethod
    def _turn_aura(state, colour):
        """Her turn's glow round the island (AURA_TURNS): her dots' colour, steady while she listens, breathing while
        she thinks or works, red when something's gone wrong; None while she speaks."""
        how = AURA_TURNS.get(state)
        return (colour, how) if how and colour is not None else None

    def _badge_r(self, n):
        """Half the width of _badge's pill for n."""
        return max(7.5 * self.k, (self.f_small.measure(str(n) if n < 10 else "9+") + 4) / 2 + 3 * self.k)

    def _glass_colour(self, row):
        """A row's colour on the capsule: amber running (violet for research), blue waiting on you, green done,
        red failed, grey stopped or next; violet for a plugin's card that says nothing of a state."""
        state = row.get("state")
        if state is None:
            return VIOLET
        if state == "running":
            return VIOLET if row.get("kind") == "research" else ORANGE
        return {"waiting_yes": BLUE, "done": GREEN, "failed": RED}.get(state, self.theme()["muted"])

    def _line(self, cv, x0, x1, y, lw, frac, colour, now, track, a):
        """A rounded progress line from x0 to x1 on y, lw thick: frac of it in colour over its track, or, when how
        far isn't known (None), a short piece that steps along it once a second."""
        cv.shape(lambda xs, ys: face.rbox(xs, ys, (x0 + x1) / 2, y, (x1 - x0) / 2, lw / 2, lw / 2),
                 (x0 - 1, y - lw, x1 + 1, y + lw), track, a)
        if frac is None:
            piece = 0.28 * (x1 - x0)
            s0 = x0 + (x1 - x0 - piece) * ((int(now) % 4) / 3)
            s1 = s0 + piece
        else:
            s0, s1 = x0, x0 + (x1 - x0) * max(0.0, min(1.0, frac))
        if s1 - s0 > 0.5:
            cv.shape(lambda xs, ys: face.rbox(xs, ys, (s0 + s1) / 2, y, max(lw / 2, (s1 - s0) / 2), lw / 2, lw / 2),
                     (s0 - 1, y - lw, s1 + 1, y + lw), colour, a)

    def _capsule_task(self, act):
        """What she's working on, small, in the capsule: her eyes glowing in its colour, the first one's title, how
        far it's got ("40%") or how long it's been going, how many there are, and a thin line under the capsule
        for how far (or a piece stepping along it once a second when that isn't known)."""
        k, th = self.k, self.theme()
        d = act.data
        rows, more = self._card_rows(d)
        lead = rows[0] if rows else {}
        n = len(rows) + more
        state = lead.get("state")
        colour = self._glass_colour(lead)
        font = self.f_compact
        done = lead.get("progress")
        since = None
        if state == "running" and done is not None:
            words = f"{int(round(done * 100))}%"
        else:
            words = lead.get("status") or ""
            since = lead.get("since") if not words else None
        words_w = font.measure("88:88") + 2 * k if since is not None else font.measure(words)
        br = self._badge_r(n) if n > 1 else 0
        size, gap = self._eyes_w(), 10 * k
        avail = self.CAPSULE_MAX_W * k - 16 * k - 15 * k - size - gap - \
            (words_w + gap if words_w else 0) - (2 * br + gap if br else 0)
        title = font.fit(" ".join(str(lead.get("title") or "").split()), max(30 * k, avail))
        parts = [self._face(TASK_LOOKS.get(state, "open"), colour),
                 self._slot_text(title, th["text"]) if title else None]
        ink = self._ink(colour)
        if words_w:
            def tell(cv, x, cy, a, now):
                cv.text(font.render(words or _clock(max(0.0, now - since))), x - 2, cy - font.line / 2 - 1, ink, a)
            parts.append((words_w, tell))
        if br:
            parts.append((2 * br, lambda cv, x, cy, a, now: self._badge(cv, x + br, cy, n, a)))
        under = None
        if state == "running" or done is not None:
            def under(cv, ox, oy, Wn, Hn, a, now):  # just under the capsule, along its straight part
                self._line(cv, ox + Hn / 2, ox + Wn - Hn / 2, oy + Hn + 5.5 * k, 2 * k, done, colour, now,
                           th["track"], a)
        live = any((r.get("state") or "running") == "running" for r in rows)
        aura, lively = self._waiting(act, rows)
        return self._capsule(("card-row", act.plugin, title, words, since is not None, repr(lead), n), "card", parts,
                             hot=[("pin", 0, 0, 10000, 10000)], rate=1 if live else 0,
                             press={"pin": (act.plugin, "pin", None, False)}, under=under, aura=aura, lively=lively)

    def _lively(self, act, opened=False):
        """Till when act moves: LIVELY_FOR after it came or last changed, or after you started pointing at it."""
        since = act.at
        if opened:
            since = max(since, getattr(self, "hover_at", 0.0))
        return since + LIVELY_FOR

    def _waiting(self, act, rows, opened=False):
        """(aura, lively) for a card or its small island: one waiting on your yes glows round her in its colour,
        breathing a while, then steady (30 October 2026); (None, None) for the rest."""
        if not any(r.get("state") == "waiting_yes" for r in rows):
            return None, None
        return (self._glass_colour({"state": "waiting_yes"}), "breathe"), (self._lively(act, opened), 12)

    def _glass_card(self, act):
        """A plugin's card on the capsule, open while you point at it or after a click on it: a glass panel with "2
        tasks" (or the card's title) at its top, her eyes in the middle of it and the time at its right, as a phone's
        island opens (29 October 2026), then each row's title, its note and a bar in its colour, with Stop or Deny as
        on the pill: the same places to click, doing the same."""
        k, th = self.k, self.theme()
        d = act.data
        rows, more = self._card_rows(d)
        lead = rows[0] if rows else {}
        n = len(rows) + more
        W = self.CARD_W * k
        pad, gap = self.CARD_PAD * k, self.ROW_GAP * k
        head_h, ew = 26 * k, self._eyes_w()  # its top line, her eyes and the heading
        if d.get("rows") is not None:
            head = d.get("short") or d.get("title") or (f"{n} tasks" if n != 1 else "1 task")
        else:  # the card is its one row: its plugin's name over it, not its title twice
            head = act.plugin.replace("_", " ").capitalize()
        head = self.f_title.fit(str(head), W / 2 - ew / 2 - pad - 8 * k)  # left of her eyes
        me = self._face(TASK_LOOKS.get(lead.get("state"), "open"), self._glass_colour(lead))
        hot, press, parts, y = [], {}, [], pad + head_h + 8 * k
        for row in rows:
            h, draw_row = self._glass_row(row, y, W, pad, act.plugin, hot, press)
            parts.append(draw_row)
            y += h + gap
        tail = f"+{more} more" if more else ""
        H = min(self.island_max_h, y - gap + pad + (self.f_small.line + 5 * k if tail else 0))
        hot.append(("pin", 0, 0, W, H))  # anywhere else on it keeps it open, or lets it go again
        press["pin"] = (act.plugin, "pin", None, False)

        def draw(cv, ox, oy, Wn, Hn, a, now):
            hy = oy + pad + head_h / 2
            cv.text(self.f_title.render(head), ox + pad - 2, hy - self.f_title.line / 2 - 1, th["text"], a)
            me[1](cv, ox + Wn / 2 - ew / 2, hy, a, now)
            clock = self.f_label.render(_now())
            cv.text(clock, ox + Wn - pad - clock.shape[1] + 2, hy - self.f_label.line / 2 - 1, th["muted"], a)
            for draw_row in parts:
                draw_row(cv, ox, oy, a, now)
            if tail:
                cv.text(self.f_small.render(tail), ox + pad - 2, oy + y - gap + 5 * k, th["muted"], a)
        live = any((r.get("state") or "running") == "running" for r in rows)
        aura, lively = self._waiting(act, rows, opened=True)
        return Layout(("card", act.plugin, repr(rows), more), "card", W, H, draw, radius=self._corner(), hot=hot,
                      eyes=me[2], rate=1 if live else 0, press=press, face=True, aura=aura, lively=lively)

    def _glass_row(self, row, y0, W, pad, plugin, hot, press):
        """One row of a glass card from y0: (its height, draw(cv, ox, oy, a, now)): its title with a few words at
        its right and its buttons, its note in quieter words, and a 3 px bar in its colour. Its buttons go in hot
        and press just as the pill's do (_card_row)."""
        k, th = self.k, self.theme()
        small, label = self.f_small, self.f_label
        bh, bpad, bgap = self.BUTTON_H * k, 10 * k, 6 * k
        buttons, x = [], W - pad
        for b in reversed(row.get("buttons") or []):
            words = str(b.get("label") or b.get("name") or "")
            bw = small.measure(words) + 2 * bpad
            buttons.insert(0, (b, words, x - bw, x))
            x -= bw + bgap
        right = x if buttons else W - pad
        status, since = row.get("status") or "", row.get("since")
        since = since if not status else None
        sw = small.measure(status) if status else small.measure("88:88") if since is not None else 0
        tx = pad
        title = label.fit(" ".join(str(row.get("title") or "").split()), max(20 * k, right - tx - sw - 8 * k))
        lines = [small.fit(" ".join(str(t).split()), W - pad - tx) for t in (row.get("lines") or [])[:2] if t]
        h1 = max(label.line, bh if buttons else 0)
        h = h1 + (2 * k + small.line * len(lines) if lines else 0) + 10 * k
        cy = y0 + h1 / 2
        for b, words, bx0, bx1 in buttons:
            name = f"b{len(press)}"
            press[name] = (plugin, b.get("name"), b.get("data"), bool(b.get("careful", b.get("name") == "approve")))
            hot.append((name, bx0 - 2 * k, cy - bh / 2 - 2 * k, bx1 + 2 * k, cy + bh / 2 + 2 * k))
        colour = self._glass_colour(row)
        state, done = row.get("state"), row.get("progress")
        frac = done if done is not None else 1.0 if state in ("done", "failed", "waiting_yes") else \
            None if state in ("running", None) else 0.0

        def draw(cv, ox, oy, a, now):
            cv.text(label.render(title), ox + tx - 2, oy + cy - label.line / 2 - 1, th["text"], a)
            words = status or (_clock(max(0.0, now - since)) if since is not None else "")
            if words:
                cover = small.render(words)
                cv.text(cover, ox + right - cover.shape[1] + 2, oy + cy - small.line / 2 - 1, colour, a)
            for b, text, bx0, bx1 in buttons:  # Approve green, Stop red as a call's end is, Deny grey
                fill, ink = (GREEN, (0.02, 0.02, 0.03)) if b.get("name") == "approve" else \
                    (RED, (1.0, 1.0, 1.0)) if b.get("name") == "stop" else (th["track"], th["text"])
                bx, by, bw = ox + (bx0 + bx1) / 2, oy + cy, (bx1 - bx0) / 2
                cv.shape(lambda xs, ys, bx=bx, by=by, bw=bw: face.rbox(xs, ys, bx, by, bw, bh / 2, bh / 2),
                         (ox + bx0 - 1, by - bh / 2 - 1, ox + bx1 + 1, by + bh / 2 + 1), fill, a)
                cover = small.render(text)
                cv.text(cover, bx - cover.shape[1] / 2, by - small.line / 2 - 0.5, ink, a)
            ly = oy + y0 + h1 + 2 * k
            for line in lines:
                cv.text(small.render(line), ox + tx - 2, ly, th["muted"], a)
                ly += small.line
            if state is not None or done is not None:
                self._line(cv, ox + tx, ox + W - pad, ly + 5 * k, 3 * k, frac, colour, now, th["track"], a)
        return h, draw

    # ------------------------------------------------------------------ opened, as a phone's island (29 October 2026)
    def _live_head(self, W, name, icon, expr, tint=None, right=None, lively=0.0):
        """The top of a card opened on the capsule, the way an iPhone's island opens (the owner's pictures): what
        it's from on the left, its icon (icon(cv, x, cy, a, now), 18 px) and its name, her eyes in the middle where
        a phone has its camera, glowing in tint, and the time on the right, or right's words. (its height, draw(cv,
        ox, oy, Wn, a, now), how her eyes look). lively: as _face has it."""
        k, th = self.k, self.theme()
        pad, h, small = self.CARD_PAD * k, 26 * k, self.f_label
        me = self._face(expr, tint, lively=lively)
        words = small.render(small.fit(str(name), W / 2 - me[0] / 2 - pad - 34 * k))

        def draw(cv, ox, oy, Wn, a, now):
            cy = oy + pad + h / 2
            x = ox + pad
            if icon is not None:
                icon(cv, x, cy, a, now)
                x += 25 * k
            cv.text(words, x - 2, cy - small.line / 2 - 1, th["muted"], a)
            me[1](cv, ox + Wn / 2 - me[0] / 2, cy, a, now)
            say = _now() if right is None else right
            if say:
                tail = small.render(say)
                cv.text(tail, ox + Wn - pad - tail.shape[1] + 2, cy - small.line / 2 - 1, th["muted"], a)
        return h, draw, me[2]

    def _logo(self, app):
        """An app's round badge for a card's top, 18 px, and what draws it there."""
        size = round(18 * self.k)
        pic = art.badge(app, size, self._text)
        return lambda cv, x, cy, a, now: cv.image(pic, x, cy - size / 2, a)

    def _glass_media(self, act):
        """What's playing, opened on the capsule while you point at it, as the iPhone's Spotify card is: the player
        and her eyes at the top, the cover with the song and who it's by, how far it's got, then back, play or pause
        in a round button of the player's own colour, and next. The same places to click as before."""
        k, th = self.k, self.theme()
        d = act.data
        W, pad, small = self.CARD_W * k, self.CARD_PAD * k, self.f_small
        tint = art.brand(d["app"])
        head_h, head, expr = self._live_head(W, d["app"] or "Now playing", self._logo(d["app"]),
                                             "headphones" if d["playing"] else "open", tint if d["playing"] else None)
        art_s = round(56 * k)
        pic = art.rounded(_resize(d["art"], art_s), 10 * k) if d.get("art") is not None else None
        if pic is None:
            pic = art.badge(d["app"], art_s, self._text)
        y_art = pad + head_h + 10 * k
        tx = pad + art_s + 12 * k
        tw = W - tx - pad - 26 * k
        title = self.f_title.fit(d["title"], tw)
        sub = self.f_label.fit(" \u00b7 ".join(x for x in (d["artist"], d["app"]) if x), tw)
        y_bar = y_art + art_s + 14 * k
        y_btn, r = y_bar + small.line + 12 * k, 19 * k
        H = y_btn + 2 * r + pad
        cx, gap = W / 2, 64 * k
        hot = [("previous", cx - gap - r, y_btn, cx - gap + r, y_btn + 2 * r),
               ("toggle", cx - r, y_btn, cx + r, y_btn + 2 * r),
               ("next", cx + gap - r, y_btn, cx + gap + r, y_btn + 2 * r),
               ("open", 0, 0, W, y_bar - 4 * k)]
        # where it plays, under it, as Glance's card says; a click moves it to the next speakers or headphones
        out = small.render(small.fit(f"Playing on {d['output']}", W - 2 * pad - 24 * k)) if d.get("output") else None
        y_out = H - pad + 4 * k
        if out is not None:
            H += small.line + 6 * k
            hot.insert(0, ("output", W / 2 - out.shape[1] / 2 - 18 * k, y_out - 2 * k, W / 2 + out.shape[1] / 2 + 4 * k,
                           y_out + small.line + 2 * k))

        glow = d.get("tint") if d["playing"] else None  # the cover's own colour (island_art.tint), round it

        def draw(cv, ox, oy, Wn, Hn, a, now):
            head(cv, ox, oy, Wn, a, now)
            if glow is not None:  # its ambience, as bloom's: a soft light behind the cover in its colour
                ax, ay = ox + pad + art_s / 2, oy + y_art + art_s / 2
                cv.shape(lambda xs, ys: face.rbox(xs, ys, ax, ay, art_s / 2 - 2, art_s / 2 - 2, 10 * k),
                         (ax - art_s, ay - art_s, ax + art_s, ay + art_s), glow, a, 0.45, 9 * k)
            cv.image(pic, ox + pad, oy + y_art, a)
            mid = oy + y_art + art_s / 2
            cv.text(self.f_title.render(title), ox + tx - 2, mid - self.f_title.line + 1, th["text"], a)
            cv.text(self.f_label.render(sub), ox + tx - 2, mid + 2 * k, th["muted"], a)
            lvl = getattr(self.runner.plugin("media"), "level", 0.0) if d["playing"] else 0.0
            self._music_bars(cv, ox + Wn - pad - 20 * k, mid, 16 * k, (glow or tint) if d["playing"] else th["muted"],
                             min(1.0, lvl * 2.2) if d["playing"] else 0.0, d["playing"], now, a)
            pos = d["position"] + ((now - d["at"]) if d["playing"] else 0.0)
            dur = d["duration"]
            if dur > 0:  # how far it's got, with the time gone and the time to go either side
                el, rest = small.render(_clock(pos)), small.render("-" + _clock(max(0.0, dur - pos)))
                x0, x1, ty = ox + pad, ox + Wn - pad, oy + y_bar
                cv.text(el, x0 - 2, ty, th["muted"], a)
                cv.text(rest, x1 - rest.shape[1] + 2, ty, th["muted"], a)
                self._line(cv, x0 + el.shape[1] + 8 * k, x1 - rest.shape[1] - 8 * k, ty + small.line / 2, 4 * k,
                           max(0.0, min(1.0, pos / dur)), tint, now, th["track"], a)
            by = oy + y_btn + r
            face.skip_glyph(cv, ox + cx - gap, by, 15 * k, False, th["text"], a)
            cv.shape(lambda xs, ys: face.circle(xs, ys, ox + cx, by, r),
                     (ox + cx - r - 1, by - r - 1, ox + cx + r + 1, by + r + 1), tint, a)
            face.play_glyph(cv, ox + cx + (0 if d["playing"] else 1.5 * k), by, 17 * k, d["playing"],
                            (1.0, 1.0, 1.0), a)
            face.skip_glyph(cv, ox + cx + gap, by, 15 * k, True, th["text"], a)
            if out is not None:
                ox0 = ox + Wn / 2 - out.shape[1] / 2 + 8 * k
                face.speaker_glyph(cv, ox0 - 12 * k, oy + y_out + small.line / 2, 13 * k, th["muted"], a)
                cv.text(out, ox0 - 2, oy + y_out, th["muted"], a)
        return Layout(("media-card", d["title"], d["artist"], d["playing"], id(d.get("art")), d.get("output")),
                      "media", W, H, draw,
                      radius=self._corner(), hot=hot, eyes=expr, rate=24 if d["playing"] else 2, face=True,
                      aura=(glow, "steady") if glow is not None else None)

    def _glass_note(self, act):
        """A notification on the capsule, as a phone's island shows one: the app's badge and name at the top, her
        eyes in the middle and "now", or x to dismiss it while you point at it, then who it's from and what it
        says."""
        k, th = self.k, self.theme()
        d = act.data
        W, pad = self.CARD_W * k, self.CARD_PAD * k
        name = d["app"] + (" \u00b7 on your phone" if d.get("phone") else "")
        head_h, head, expr = self._live_head(W, name, self._logo(d["app"]), "open", art.brand(d["app"]),
                                             right="" if self.hover else "now")
        tw = W - 2 * pad
        title = self.f_title.fit(d["title"] or d["app"], tw)
        lines = self.f_label.wrap(d["text"], tw, 2) if d.get("text") else []
        y_t = pad + head_h + 8 * k
        H = y_t + self.f_title.line + (2 * k + self.f_label.line * len(lines) if lines else 0) + pad
        # Reply, on a message from someone (31 October 2026, after Glance's): her typing box, with who to and where in
        # it already, and what you type goes to her as a turn, so she asks before sending it, as ever
        reply = bool(d.get("messaging")) and bool(d.get("title")) and d.get("title") != "New message"
        bw, bh = self.f_label.measure("Reply") + 24 * k, self.BUTTON_H * k
        if reply:
            H += bh + 8 * k
        hot = [("dismiss", W - 34 * k, 0, W, pad + head_h + 4 * k)] + \
            ([("reply", W - pad - bw, H - pad - bh, W - pad, H - pad)] if reply else []) + [("open", 0, 0, W, H)]
        brand = art.brand(d["app"])

        def draw(cv, ox, oy, Wn, Hn, a, now):
            head(cv, ox, oy, Wn, a, now)
            if self.hover:
                face.close_glyph(cv, ox + Wn - pad - 6 * k, oy + pad + head_h / 2, 12 * k, th["muted"], a)
            y = oy + y_t
            cv.text(self.f_title.render(title), ox + pad - 2, y, th["text"], a)
            y += self.f_title.line + 2 * k
            for line in lines:
                cv.text(self.f_label.render(line), ox + pad - 2, y, th["text"], a * 0.86)
                y += self.f_label.line
            if reply:
                bx1, by1 = ox + Wn - pad, oy + Hn - pad
                cv.shape(lambda xs, ys: face.rbox(xs, ys, bx1 - bw / 2, by1 - bh / 2, bw / 2, bh / 2, bh / 2),
                         (bx1 - bw - 1, by1 - bh - 1, bx1 + 1, by1 + 1), brand, a)
                cover = self.f_label.render("Reply")
                cv.text(cover, bx1 - bw / 2 - cover.shape[1] / 2, by1 - bh / 2 - self.f_label.line / 2 - 1,
                        (1.0, 1.0, 1.0), a)
        return Layout(("note", d["app"], d["title"], d.get("text", ""), id(act)), "notification", W, H, draw,
                      radius=self._corner(), hot=hot, eyes=expr, face=True)

    def _glass_timer(self, act):
        """A timer opened on the capsule while you point at it: what it's for and her eyes at the top, how long's
        left in big orange figures, and a line going down with it."""
        k, th = self.k, self.theme()
        d = act.data
        W, pad = self.CARD_W * k, self.CARD_PAD * k

        def ring(cv, x, cy, a, now):
            face.ring(cv, x + 9 * k, cy, 7 * k, 2.4 * k, max(0.0, (d["end"] - now) / d["total"]), ORANGE,
                      th["track"], a)
        head_h, head, expr = self._live_head(W, d["label"] or "Timer", ring, "open", ORANGE)
        big = self._text(round(30 * k), 300)
        y_big = pad + head_h + 6 * k
        y_line = y_big + big.line + 8 * k
        H = y_line + 4 * k + pad
        of = self.f_label.render(f"of {_clock(d['total'])}")

        urgent = bool(d.get("urgent"))

        def draw(cv, ox, oy, Wn, Hn, a, now):
            head(cv, ox, oy, Wn, a, now)
            cv.text(big.render(_clock(max(0, math.ceil(d["end"] - now)))), ox + pad - 2, oy + y_big, self._ink(ORANGE),
                    a * _beat(d["end"] - now, urgent))
            cv.text(of, ox + Wn - pad - of.shape[1] + 2, oy + y_big + big.line - self.f_label.line - 6 * k,
                    th["muted"], a)
            left = max(0.0, (d["end"] - now) / d["total"])
            self._line(cv, ox + pad, ox + Wn - pad, oy + y_line + 2 * k, 4 * k, left, ORANGE, now, th["track"], a)
        return Layout(("timer-card", d["label"], d["end"]), "timer", W, H, draw, radius=self._corner(), eyes=expr,
                      rate=12 if urgent else 1, face=True, aura=(ORANGE, "breathe") if urgent else None)

    def _glass_battery(self, act):
        """The battery opened on the capsule while you point at it: Battery and her eyes at the top, how full it is
        in big figures in its colour, whether it's charging, and a bar as full as it is."""
        k, th = self.k, self.theme()
        d = act.data
        pct, charging, event = d["percent"], d["charging"], d["event"]
        fill = RED if pct <= 20 and not charging else GREEN if charging else th["text"]
        W, pad = self.CARD_W * k, self.CARD_PAD * k

        def glyph(cv, x, cy, a, now):
            face.battery(cv, x, cy, 9 * k, pct, th["text"], fill, charging, a)
        head_h, head, expr = self._live_head(W, "Battery", glyph, "sad" if event == "low" else "open",
                                             None if fill is th["text"] else fill)
        big = self._text(round(30 * k), 300)
        says = self.f_title.render({"full": "Full", "low": "Low: plug it in"}.get(event) or
                                   ("Charging" if charging else "On battery"))
        y_big = pad + head_h + 6 * k
        y_line = y_big + big.line + 8 * k
        H = y_line + 4 * k + pad

        def draw(cv, ox, oy, Wn, Hn, a, now):
            head(cv, ox, oy, Wn, a, now)
            cv.text(big.render(f"{pct}%"), ox + pad - 2, oy + y_big, fill, a)
            cv.text(says, ox + Wn - pad - says.shape[1] + 2, oy + y_big + big.line - self.f_title.line - 6 * k,
                    th["text"] if fill is th["text"] else fill, a)
            self._line(cv, ox + pad, ox + Wn - pad, oy + y_line + 2 * k, 4 * k, pct / 100, fill, now, th["track"], a)
        return Layout(("battery-card", pct, charging, event), "battery", W, H, draw, radius=self._corner(),
                      eyes=expr, face=True)

    # ------------------------------------------------------------------ live activities (30 October 2026)
    def _icon(self, name, colour, s, lively=0.0):
        """A live activity's glyph (face.GLYPHS), s px across, as icon(cv, x, cy, a, now) drawn from x: moving till
        lively (a time), still after it. None for a glyph it doesn't know."""
        glyph = face.GLYPHS.get(name)
        if glyph is None:
            return None

        def icon(cv, x, cy, a, now):
            glyph(cv, x + s / 2, cy, s, colour, a, now - self.t0 if now < lively else None)
        return icon

    @staticmethod
    def _live_moves(d, lively, expr):
        """(aura, lively) for a live activity: a glyph that moves, dreaming eyes or a breathing glow ask for 12 frames
        a second till lively (a time), and none of their own after (Layout.lively)."""
        aura = (_accent(d.get("accent")), d["aura"]) if d.get("aura") in ("breathe", "steady") else None
        moves = d.get("glyph") in MOVING or expr == "dream" or (aura is not None and aura[1] == "breathe")
        return aura, ((lively, 12) if moves else None)

    def _live(self, act, now):
        """A plugin's live activity, small, as a phone's island shows one: its glyph in its colour on the left, her
        eyes in the middle looking as it says (its "mood") and glowing in its colour, and on the right how long it's
        been going or has to go, or a few words, in its colour. Any plugin can show one without this file knowing it
        (island_plugins.Activity, kind "live")."""
        k = self.k
        d = act.data
        accent = _accent(d.get("accent"))
        ink, font, s = self._ink(accent), self.f_compact, 17 * k
        lively = self._lively(act)
        icon = self._icon(d.get("glyph"), accent, s, lively)
        timed = _timed(d)
        if timed:
            def clock(cv, x, cy, a, now):
                cv.text(font.render(_live_clock(d, now)), x - 2, cy - font.line / 2 - 1, ink, a)
            right = (_clock_w(font, d, now) + 2 * k, clock)
        else:
            words = font.fit(" ".join(str(d.get("short") or d.get("title") or "").split()), 150 * k)
            right = self._slot_text(words, ink) if words else None
        expr = d.get("mood") if d.get("mood") in face.MOODS else "open"
        eyes = self._face(expr, accent, lively=lively) if self.style == "capsule" else None
        aura, moves = self._live_moves(d, lively, expr)
        return self._row(("live-row", act.plugin, repr(d)), "card", expr, (s, icon) if icon else None, right,
                         hot=[("pin", 0, 0, 10000, 10000)], rate=1 if timed else 0,
                         press={"pin": (act.plugin, "pin", None, False)}, tint=accent, aura=aura, lively=moves,
                         eyes=eyes)

    def _glass_live(self, act, now):
        """A live activity opened on the capsule while you point at it, as a phone's island opens one: its glyph and
        name at the top, her eyes in the middle and the time; what it is in big words with a quieter line under them,
        and how long it's been going or has to go in big figures in its colour at the right; then its waveform, how
        far it's got, and its buttons, round as a phone's. A click on one is its plugin's command, as on a card."""
        k, th = self.k, self.theme()
        d = act.data
        accent = _accent(d.get("accent"))
        ink, W, pad = self._ink(accent), self.CARD_W * k, self.CARD_PAD * k
        lively = self._lively(act, opened=True)
        expr = d.get("mood") if d.get("mood") in face.MOODS else "open"
        icon = self._icon(d.get("glyph"), accent, 17 * k, lively)
        head_h, head, expr = self._live_head(W, d.get("label") or act.plugin.replace("_", " ").capitalize(), icon,
                                             expr, accent, lively=lively)
        big = self._text(round(28 * k), 300)
        timed = _timed(d)
        clock_w = _clock_w(big, d, now) + 4 * k if timed else 0
        tw = W - 2 * pad - (clock_w + 12 * k if timed else 0)
        title = self.f_title.fit(" ".join(str(d.get("title") or "").split()), tw)
        sub = self.f_label.fit(" ".join(str(d.get("sub") or "").split()), tw)
        text_h = self.f_title.line + (2 * k + self.f_label.line if sub else 0)
        y_t = pad + head_h + 10 * k
        row_h = max(text_h, big.line if timed else 0)
        y = y_t + row_h
        wave, done = bool(d.get("wave")), _live_done(d, now)
        y_w = y + 8 * k
        if wave:
            y = y_w + 26 * k
        y_p = y + 10 * k
        if done is not None:
            y = y_p + 4 * k
        bh, placed, x = 30 * k, [], W - pad
        for b in reversed(list(d.get("buttons") or [])):  # right to left, as a phone's
            words = str(b.get("label") or b.get("name") or "")
            bw = self.f_label.measure(words) + 28 * k
            placed.insert(0, (b, words, x - bw, x))
            x -= bw + 8 * k
        y_b = y + 12 * k
        if placed:
            y = y_b + bh
        H = min(self.island_max_h, y + pad)
        hot, press = [], {}
        for b, words, x0, x1 in placed:
            name = f"b{len(press)}"
            press[name] = (act.plugin, b.get("name"), b.get("data"), bool(b.get("careful")))
            hot.append((name, x0 - 2 * k, y_b - 2 * k, x1 + 2 * k, y_b + bh + 2 * k))
        hot.append(("pin", 0, 0, W, H))  # anywhere else on it keeps it open, or lets it go again
        press["pin"] = (act.plugin, "pin", None, False)

        def draw(cv, ox, oy, Wn, Hn, a, now):
            head(cv, ox, oy, Wn, a, now)
            ty = oy + y_t + (row_h - text_h) / 2
            cv.text(self.f_title.render(title), ox + pad - 2, ty, th["text"], a)
            if sub:
                cv.text(self.f_label.render(sub), ox + pad - 2, ty + self.f_title.line + 2 * k, th["muted"], a)
            if timed:
                cover = big.render(_live_clock(d, now))
                cv.text(cover, ox + Wn - pad - cover.shape[1] + 2, oy + y_t + (row_h - big.line) / 2, ink, a)
            if wave:
                face.wave_bars(cv, ox + pad, oy + y_w + 13 * k, Wn - 2 * pad, 24 * k, accent,
                               float(d.get("level") or 0.6), now - self.t0, a)
            if done is not None:
                frac = _live_done(d, now)  # it moves on with its clock
                self._line(cv, ox + pad, ox + Wn - pad, oy + y_p + 2 * k, 4 * k, done if frac is None else frac,
                           accent, now, th["track"], a)
            for b, words, x0, x1 in placed:
                self._pill_button(cv, ox + x0, oy + y_b, x1 - x0, bh, words, b.get("name"), accent, a)
        aura, moves = self._live_moves(d, lively, expr)
        return Layout(("live", act.plugin, repr(d)), "card", W, H, draw, radius=self._corner(), hot=hot, eyes=expr,
                      animated=wave, rate=1 if timed else 0, press=press, face=True, aura=aura, lively=moves)

    def _pill_button(self, cv, x, y, w, h, words, name, accent, a, solid=False):
        """A round-ended button, as a phone's live activities have them: tinted in its colour on the glass, its words
        in that colour. Stop and Exit are red, as a call's end is; the rest the activity's own. solid: the one that
        does what it's for, in its colour with white words."""
        th = self.theme()
        colour = RED if name in ("stop", "exit") else accent
        fill = colour if solid else _mix(th["body"], colour, 0.15 if th["body"][0] > 0.5 else 0.26)
        cx, cy = x + w / 2, y + h / 2
        cv.shape(lambda xs, ys: face.rbox(xs, ys, cx, cy, w / 2, h / 2, h / 2), (x - 1, y - 1, x + w + 1, y + h + 1),
                 fill, a)
        cover = self.f_label.render(words)
        cv.text(cover, cx - cover.shape[1] / 2, cy - self.f_label.line / 2 - 0.5,
                (1.0, 1.0, 1.0) if solid else self._ink(colour), a)

    # ------------------------------------------------------------------ the panels (30 October 2026)
    # After bloom's notch (github.com/SehajveerSingh2005/bloom), the owner's ask: a click on her eyes opens them, the
    # wheel goes on to the next, and the pointer leaving closes them. What's in them is read on the plugins' thread
    # (island_plugins.Hub) and drawn here; a press on one is sent back there, never done on this thread.
    def _hub_on(self):
        """True if a click on her eyes opens the panels: they're on in the Island tab, on the capsule's glass."""
        return self.style == "capsule" and plugins.on("hub")

    def _hub_open(self, page=None):
        """The panels open, on page, else the one you had open last (island_panel). False if they're off."""
        if not self._hub_on():
            return False
        page = page if page in HUB_PAGES else settings.get("island_panel")
        self.hub_page = page if page in HUB_PAGES else HUB_PAGES[0]
        self.hub_month, self.drag = None, None
        if self.hub_page == "alerts":
            self.alerts_seen = time.time()
        self.hover, self.away_at = True, time.time()
        self._hub_want()
        self.dirty = True
        self._wake()
        return True

    def _hub_close(self):
        self.hub_page = self.drag = None
        self._hub_want()
        self.dirty = True
        self._wake()

    def _hub_go(self, page):
        """Another panel: page, or 1 and -1 for the next and the one before, remembered for next time."""
        if isinstance(page, int):
            i = HUB_PAGES.index(self.hub_page) if self.hub_page in HUB_PAGES else 0
            page = HUB_PAGES[(i + page) % len(HUB_PAGES)]
        if page not in HUB_PAGES or page == self.hub_page:
            return
        self.hub_page, self.drag = page, None
        if page == "alerts":
            self.alerts_seen = time.time()
        try:
            settings.put("island_panel", page)
        except OSError:
            pass
        self._hub_want()
        self.dirty = True
        self._wake()

    def _hub_want(self):
        """What the Hub plugin reads (Runner.want): the panel open and its month, else what's beside her eyes."""
        runner = getattr(self, "runner", None)
        if runner is None:
            return
        if self.hub_page is not None:
            runner.want("hub", {"page": self.hub_page, "month": self.hub_month})
        elif self._status_widgets():
            runner.want("hub", {"page": None})
        else:
            runner.want("hub", None)

    @staticmethod
    def _agent_busy():
        """True while she's doing a task in an app: her clicks are real ones, so none may land on a control here."""
        agent = sys.modules.get("agent")
        return agent is not None and (agent.ACT.locked() or agent.RUNNING.is_set())

    def _hub(self, now):
        """The panels, open: a tab for each along their top (HUB_PAGES), her eyes in the middle where a phone has its
        camera, glowing in the panel's colour, and the weather, the battery and the time; under them the one open."""
        k = self.k
        W, pad = self.HUB_W * k, self.CARD_PAD * k
        page = self.hub_page if self.hub_page in HUB_PAGES else HUB_PAGES[0]
        d = self.hub_data or {}
        head_h = 26 * k
        y0 = pad + head_h + 12 * k
        body_h, body, hot, key = getattr(self, "_hub_" + page)(W, pad, y0, d, now)
        H = min(self.island_max_h, y0 + body_h + pad)
        head, head_hot, expr = self._hub_head(W, pad, head_h, page, d)

        def draw(cv, ox, oy, Wn, Hn, a, now):
            head(cv, ox, oy, Wn, a, now)
            body(cv, ox, oy, Wn, Hn, a, now)
        return Layout(("hub", page, key, round(H)), "hub", W, H, draw, radius=self._corner(),
                      hot=head_hot + hot + [("stay", 0, 0, W, H)], eyes=expr, rate=1, face=True)

    def _hub_head(self, W, pad, head_h, page, d):
        """The panels' top: (draw(cv, ox, oy, Wn, a, now), its places to click, how her eyes look)."""
        k, th = self.k, self.theme()
        many = len(HUB_PAGES) > 5  # six tabs and her eyes in one row: a little smaller, a little closer
        r, small = (10.5 if many else 12) * k, self.f_label
        tabs, hot, x = [], [], pad
        for p in HUB_PAGES:
            tabs.append((p, x + r))
            hot.append((f"tab:{p}", x - 2 * k, pad - 2 * k, x + 2 * r + 2 * k, pad + head_h + 2 * k))
            x += 2 * r + (3.5 if many else 5) * k
        me = self._face("open", HUB_TINTS[page])
        ew = me[0]
        hot.append(("close", W / 2 - ew / 2, pad - 2 * k, W / 2 + ew / 2, pad + head_h + 2 * k))
        weather = d.get("weather") if plugins.get_options("hub").get("weather", True) else None
        battery = d.get("battery")
        unseen = any(n.get("at", 0.0) > self.alerts_seen for n in self.recent)  # a dot on Recent's tab

        def draw(cv, ox, oy, Wn, a, now):
            cy = oy + pad + head_h / 2
            for p, cx in tabs:
                on = p == page
                if on:  # the open one on a round of its own colour (30 October 2026, the owner: "more colour")
                    cv.shape(lambda xs, ys, cx=cx: face.circle(xs, ys, ox + cx, cy, r),
                             (ox + cx - r - 1, cy - r - 1, ox + cx + r + 1, cy + r + 1), HUB_TINTS[p], a)
                face.GLYPHS[HUB_GLYPHS[p]](cv, ox + cx, cy, 15 * k, (1.0, 1.0, 1.0) if on else th["muted"], a)
                if p == "alerts" and unseen and not on:
                    dx, dy, dr = ox + cx + r * 0.6, cy - r * 0.6, 3.2 * k
                    cv.shape(lambda xs, ys, dx=dx, dy=dy: face.circle(xs, ys, dx, dy, dr),
                             (dx - dr - 1, dy - dr - 1, dx + dr + 1, dy + dr + 1), ORANGE, a)
            me[1](cv, ox + Wn / 2 - ew / 2, cy, a, now)
            x = ox + Wn - pad
            clock = small.render(_now())
            x -= clock.shape[1] - 2
            cv.text(clock, x, cy - small.line / 2 - 1, th["muted"], a)
            if battery is not None:
                pct, charging = battery
                words = small.render(f"{pct}%")
                x -= words.shape[1] + 6 * k
                cv.text(words, x, cy - small.line / 2 - 1, th["muted"], a)
                bh = 8.5 * k
                x -= bh * 1.9 + 4 * k
                low = pct <= 20 and not charging
                face.battery(cv, x, cy, bh, pct, th["text"], RED if low else GREEN if charging else th["text"],
                             charging, a)
            if weather:
                words = small.render(f"{weather['temp']}\u00b0")
                x -= words.shape[1] + 8 * k
                cv.text(words, x, cy - small.line / 2 - 1, th["muted"], a)
                x -= 15 * k
                face.cloud_glyph(cv, x + 6 * k, cy, 15 * k, th["muted"], a, weather.get("sky"))
        return draw, hot, me[2]

    def _hub_controls(self, W, pad, y0, d, now):
        """Controls, as a phone's control centre has them: Wi-Fi, Bluetooth and Do Not Disturb as round buttons, in
        their colour while they're on, and the volume and the brightness as sliders, to click, drag or scroll. Do Not
        Disturb is the island's own: no popups while it's on (island_plugins.HUSHED); right-click one for its own page
        in Windows' Settings. (its height, draw, its places to click, what it shows)"""
        k, th = self.k, self.theme()
        inner = W - 2 * pad
        r = 21 * k
        dnd = bool(settings.get("island_dnd"))
        # under each its name, and what it's on (30 October 2026, the owner's ask): the network, the device
        tiles = (("wifi", "Wi-Fi", d.get("wifi"), BLUE, _on_line(d.get("wifi"), d.get("wifi_name"))),
                 ("bluetooth", "Bluetooth", d.get("bluetooth"), BLUE,
                  _on_line(d.get("bluetooth"), d.get("bt_name"))),
                 ("dnd", "Do Not Disturb", dnd, INDIGO, "On" if dnd else "Off"),
                 # Glance's Keep Awake (30 October 2026): the PC and its screen kept from sleeping while it's on
                 ("awake", "Keep awake", win.awake(), ORANGE, "On" if win.awake() else "Off"))
        step = inner / len(tiles)
        lab_y = y0 + 2 * r + 7 * k
        sub_y = lab_y + self.f_small.line - 1 * k
        f_sub = self._text(round(10.5 * k), 500)
        sl_y = sub_y + f_sub.line + 12 * k
        sl_h, gap = 32 * k, 10 * k
        sliders = (("volume", d.get("volume"), bool(d.get("muted"))), ("brightness", d.get("brightness"), False))
        hot = []
        for i, tile in enumerate(tiles):
            cx = pad + step * (i + 0.5)
            hot.append((f"toggle:{tile[0]}", cx - r - 6 * k, y0 - 4 * k, cx + r + 6 * k, sub_y + f_sub.line))
        for j, (name, level, _) in enumerate(sliders):
            y = sl_y + j * (sl_h + gap)
            if level is not None:
                if name == "volume":  # its speaker mutes it
                    hot.append(("mute", pad, y, pad + sl_h, y + sl_h))
                hot.append((f"slider:{name}", pad, y - 3 * k, W - pad, y + sl_h + 3 * k))
        off = _mix(th["body"], th["text"], 0.12)

        def draw(cv, ox, oy, Wn, Hn, a, now):
            for i, (name, label, state, colour, sub) in enumerate(tiles):
                cx, cy = ox + pad + step * (i + 0.5), oy + y0 + r
                on = bool(state)
                cv.shape(lambda xs, ys, cx=cx, cy=cy: face.circle(xs, ys, cx, cy, r),
                         (cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1), colour if on else off,
                         a * (1.0 if state is not None else 0.5))
                face.GLYPHS[name](cv, cx, cy, 21 * k, (1.0, 1.0, 1.0) if on else th["text"], a)
                cover = self.f_small.render(self.f_small.fit(label, step - 4 * k))
                cv.text(cover, cx - cover.shape[1] / 2, oy + lab_y, th["text"], a)
                if sub:
                    cover = f_sub.render(f_sub.fit(sub, step - 6 * k))
                    cv.text(cover, cx - cover.shape[1] / 2, oy + sub_y, colour if on and name not in ("dnd", "awake")
                            else th["muted"], a)
            for j, (name, level, muted) in enumerate(sliders):
                self._slider(cv, ox + pad, oy + sl_y + j * (sl_h + gap), Wn - 2 * pad, sl_h, name, level, muted, a)
        key = (tuple(t[2] for t in tiles), tuple(t[4] for t in tiles), tuple(s[1:] for s in sliders))
        return sl_y + 2 * sl_h + gap - y0, draw, hot, key

    def _slider(self, cv, x, y, w, h, name, level, muted, a):
        """A level as a phone's control centre slider has it: a round-ended bar filled as far as it's set, its glyph
        on the fill's round end and the level at its right."""
        k, th = self.k, self.theme()
        r, cy = h / 2, y + h / 2
        cv.shape(lambda xs, ys: face.rbox(xs, ys, x + w / 2, cy, w / 2, r, r), (x - 1, y - 1, x + w + 1, y + h + 1),
                 _mix(th["body"], th["text"], 0.1), a)
        frac = 0.0 if muted or level is None else max(0.0, min(1.0, level / 100))
        fw = max(h, w * frac)
        # filled in its own colour (30 October 2026, the owner: "more colour"), as Windows' quick settings fills them
        # in its accent: the volume blue, the brightness a warm amber; grey while it's muted
        fill = th["muted"] if muted else SLIDER_TINTS.get(name, BLUE)
        if level is not None:
            cv.shape(lambda xs, ys: face.rbox(xs, ys, x + fw / 2, cy, fw / 2, r, r),
                     (x - 1, y - 1, x + fw + 1, y + h + 1), fill, a)
        ink = (1.0, 1.0, 1.0) if level is not None else th["muted"]
        if name == "volume":
            face.speaker_glyph(cv, x + r + 1 * k, cy, 19 * k, ink, a, frac, muted)
        else:
            face.sun_glyph(cv, x + r, cy, 18 * k, ink, a, frac)
        words = ("Muted" if muted else f"{int(level)}%") if level is not None else \
            ("Not on this screen" if name == "brightness" else "\u2026")
        cover = self.f_small.render(words)
        tx = x + w - 12 * k - cover.shape[1] + 2 if level is not None else x + h + 6 * k - 2
        over = level is not None and x + fw > tx
        cv.text(cover, tx, cy - self.f_small.line / 2 - 1, (1.0, 1.0, 1.0) if over else th["muted"], a)

    def _hub_calendar(self, W, pad, y0, d, now):
        """The calendar, as bloom's has it with its timer: the month with today ringed in red and a dot under each
        day with something on (from what's kept on this PC, island_plugins.Hub._month), < and > for the months
        either side, what's next under it; and at its right the focus timer (focus.py), its clock big, with Start,
        or Pause and Stop."""
        import calendar as months
        import datetime as dt
        k, th = self.k, self.theme()
        inner = W - 2 * pad
        today = dt.date.today()
        year, month = self.hub_month or (today.year, today.month)
        info = d.get("month") if isinstance(d.get("month"), dict) else None
        if info is not None and tuple(info.get("key") or ()) != (year, month):
            info = None
        days = (info or {}).get("days") or {}
        weeks = months.Calendar(0).monthdayscalendar(year, month)
        gw = inner * 0.56
        cell_w, cell_h = gw / 7, 22 * k
        title_h = 22 * k
        y_week = y0 + title_h + 4 * k
        y_grid = y_week + self.f_small.line + 3 * k
        y_next = y_grid + len(weeks) * cell_h + 8 * k
        body_h = y_next + self.f_small.line - y0
        title = months.month_name[month] + ("" if year == today.year else f" {year}")
        f_month, f_day = self._text(round(14 * k), 700), self._text(round(11.5 * k), 600)
        hot = [("month:-1", pad + gw - 46 * k, y0 - 2 * k, pad + gw - 24 * k, y0 + title_h),
               ("month:1", pad + gw - 22 * k, y0 - 2 * k, pad + gw, y0 + title_h),
               ("month:0", pad, y0 - 2 * k, pad + gw - 50 * k, y0 + title_h)]
        fx = pad + gw + 16 * k  # the focus timer, at the right
        fw = W - pad - fx
        fs, foc = None, _focus()
        if foc is not None:
            fs = foc.state(now)
        resting = fs is not None and fs["phase"] == "break"
        accent = GREEN if resting else ORANGE
        if fs is None:
            acts = [("start", "Start")]
        elif resting:
            acts = [("skip", "Skip"), ("stop", "Stop")]
        else:
            acts = [("resume", "Resume") if fs["paused"] else ("pause", "Pause"), ("stop", "Stop")]
        bh, bgap = 28 * k, 6 * k
        y_btn = y_next - 8 * k - bh
        bw = (fw - bgap * (len(acts) - 1)) / len(acts)
        placed = []
        for i, (name, words) in enumerate(acts):
            bx = fx + i * (bw + bgap)
            placed.append((name, words, bx))
            hot.append((f"focus:{name}", bx - 2 * k, y_btn - 2 * k, bx + bw + 2 * k, y_btn + bh + 2 * k))
        big = self._text(round(30 * k), 300)
        focus_len = int(float(settings.get("focus_minutes") or 25) * 60)
        nxt = (info or {}).get("next")

        def draw(cv, ox, oy, Wn, Hn, a, now):
            cv.text(f_month.render(title), ox + pad - 2, oy + y0 + (title_h - f_month.line) / 2, th["text"], a)
            mid = oy + y0 + title_h / 2
            face.chevron_glyph(cv, ox + pad + gw - 35 * k, mid, 13 * k, th["muted"], a, right=False)
            face.chevron_glyph(cv, ox + pad + gw - 11 * k, mid, 13 * k, th["muted"], a, right=True)
            for i, letter in enumerate("MTWTFSS"):
                cover = self.f_small.render(letter)
                cv.text(cover, ox + pad + cell_w * (i + 0.5) - cover.shape[1] / 2, oy + y_week, th["muted"], a)
            for row, week in enumerate(weeks):
                for col, day in enumerate(week):
                    if not day:
                        continue
                    cx = ox + pad + cell_w * (col + 0.5)
                    cy = oy + y_grid + cell_h * (row + 0.5)
                    is_today = (year, month, day) == (today.year, today.month, today.day)
                    if is_today:
                        rr = min(cell_w, cell_h) * 0.46
                        cv.shape(lambda xs, ys, cx=cx, cy=cy, rr=rr: face.circle(xs, ys, cx, cy, rr),
                                 (cx - rr - 1, cy - rr - 1, cx + rr + 1, cy + rr + 1), RED, a)
                    cover = f_day.render(str(day))
                    cv.text(cover, cx - cover.shape[1] / 2, cy - f_day.line / 2 - 1,
                            (1.0, 1.0, 1.0) if is_today else th["text"] if col < 5 else th["muted"], a)
                    if days.get(day) and not is_today:
                        dy = cy + cell_h * 0.38
                        cv.shape(lambda xs, ys, cx=cx, dy=dy: face.circle(xs, ys, cx, dy, 1.6 * k),
                                 (cx - 3 * k, dy - 3 * k, cx + 3 * k, dy + 3 * k), ORANGE, a)
            if nxt:
                when = time.strftime("%a %I:%M %p", time.localtime(nxt["start"])).replace(" 0", " ")
                words = self.f_small.fit(f"Next \u00b7 {nxt['title']} \u00b7 {when}", gw + fw)
            else:
                words = "Nothing on in the next two weeks" if info is not None else ""
            if words:
                cv.text(self.f_small.render(words), ox + pad - 2, oy + y_next, th["muted"], a)
            # the focus timer
            label = ("Break" if resting else "Focus") + (f" \u00b7 round {fs['round']}" if fs else "")
            cv.text(self.f_small.render(label), ox + fx - 2, oy + y0 + 2 * k, self._ink(accent), a)
            secs = focus_len if fs is None else (fs["left"] if fs["paused"] else max(0.0, fs["until"] - now))
            clock = big.render(_clock(math.ceil(secs)))
            cv.text(clock, ox + fx - 2, oy + y0 + self.f_small.line + 4 * k, th["text"], a)
            ly = oy + y0 + self.f_small.line + big.line + 12 * k
            if fs is not None:  # how far through this part, under the clock
                done = 1 - secs / max(1.0, fs["length"])
                self._line(cv, ox + fx, ox + fx + fw, ly, 4 * k, done, accent, now, th["track"], a)
                if fs["paused"]:
                    note = "Paused"
                elif resting:
                    note = "Back to it at " + time.strftime("%I:%M", time.localtime(fs["until"])).lstrip("0")
                else:
                    note = "Done at " + time.strftime("%I:%M", time.localtime(fs["until"])).lstrip("0")
            else:  # what a round is, where the bar goes while one runs
                rest = int(float(settings.get("break_minutes") or 5))
                note = f"{rest} min break after"
            cover = self.f_small.render(self.f_small.fit(note, fw))
            cv.text(cover, ox + fx - 2, ly + 10 * k, th["muted"], a)
            for i, (name, words, bx) in enumerate(placed):
                self._pill_button(cv, ox + bx, oy + y_btn, bw, bh, words, name, accent, a, solid=i == 0)
        key = (year, month, tuple(sorted(days.items())), nxt and nxt["start"],
               fs and (fs["phase"], fs["paused"], fs["round"]))
        return body_h, draw, hot, key

    def _hub_devices(self, W, pad, y0, d, now):
        """Devices: the sound outputs that are on, each drawn as what it is, with its battery when Windows has it and
        a tick on the one sound plays on (a click on another moves the sound there), then the USB drives (a click
        opens one)."""
        k, th = self.k, self.theme()
        outs, drives = d.get("outputs"), d.get("drives") or []
        rows = []
        for o in outs or []:
            how = DEVICE_WORDS.get(o.get("kind"), "Sound")
            bus = " \u00b7 Bluetooth" if str(o.get("bus")) in ("BTHENUM", "BTHHFENUM", "BTHLEDEVICE") else \
                " \u00b7 USB" if o.get("bus") == "USB" else ""
            rows.append((o.get("kind"), o.get("name") or "Sound", how + bus, o.get("battery"), bool(o.get("default")),
                         None if o.get("default") else f"out:{o.get('id')}"))
        for dr in drives:
            rows.append(("drive", f"{dr['label']} ({dr['letter']}:)",
                         f"{_size(dr['free'])} free of {_size(dr['total'])}", None, False, f"drive:{dr['letter']}"))
        rows = rows[:5]
        row_h = 40 * k
        body_h = max(1, len(rows)) * row_h
        hot = [(name, pad - 4 * k, y0 + i * row_h, W - pad + 4 * k, y0 + (i + 1) * row_h)
               for i, (*_, name) in enumerate(rows) if name]
        f_name = self.f_label

        def draw(cv, ox, oy, Wn, Hn, a, now):
            if not rows:
                words = "Looking\u2026" if outs is None else "Nothing else connected"
                cover = f_name.render(words)
                cv.text(cover, ox + Wn / 2 - cover.shape[1] / 2, oy + y0 + row_h / 2 - f_name.line / 2,
                        th["muted"], a)
                return
            for i, (kind, name, sub, battery, here, _) in enumerate(rows):
                cy = oy + y0 + i * row_h + row_h / 2
                gx = ox + pad + 14 * k
                cv.shape(lambda xs, ys, gx=gx, cy=cy: face.circle(xs, ys, gx, cy, 15 * k),
                         (gx - 16 * k, cy - 16 * k, gx + 16 * k, cy + 16 * k), _mix(th["body"], th["text"], 0.1), a)
                glyph = face.DEVICE_GLYPHS.get(kind)
                if glyph is None:
                    face.speaker_glyph(cv, gx, cy, 17 * k, th["text"], a)
                else:
                    glyph(cv, gx, cy, 17 * k, th["text"], a)
                tx = ox + pad + 38 * k
                right = ox + Wn - pad - (44 * k if battery is not None else 0) - (22 * k if here else 0)
                cv.text(f_name.render(f_name.fit(name, right - tx)), tx - 2, cy - f_name.line + 1, th["text"], a)
                cv.text(self.f_small.render(self.f_small.fit(sub, right - tx)), tx - 2, cy + 1 * k, th["muted"], a)
                x = ox + Wn - pad
                if here:
                    face.tick_glyph(cv, x - 8 * k, cy, 14 * k, BLUE, a)
                    x -= 22 * k
                if battery is not None:
                    self._battery_ring(cv, x - 15 * k, cy, 13 * k, battery, a)
        key = tuple((r[1], r[2], r[3], r[4]) for r in rows) + ((outs is None),)
        return body_h, draw, hot, key

    def _battery_ring(self, cv, cx, cy, r, pct, a):
        """A battery as a ring, as a phone's island shows a headset's: green, orange under 30, red under 15, with its
        percentage inside."""
        th = self.theme()
        colour = GREEN if pct >= 30 else ORANGE if pct >= 15 else RED
        face.ring(cv, cx, cy, r, max(1.6, r * 0.2), pct / 100, colour, th["track"], a)
        f = self._text(max(7, round(r * 0.72)), 700)
        cover = f.render(f"{int(pct)}")
        cv.text(cover, cx - cover.shape[1] / 2, cy - f.line / 2 - 0.5, self._ink(colour), a)

    def _hub_alerts(self, W, pad, y0, d, now):
        """Recent notifications, as Glance's list has them (30 October 2026): a chip for all of them, with how many,
        and one for each of the apps most came from; then the newest few of the one picked, each with its app's badge,
        its name and how long ago, who it's from and what it says, and a click opens its app. Kept in memory only, as
        they came, while she runs (recent). (its height, draw, its places to click, what it shows)"""
        k, th = self.k, self.theme()
        items, apps, rows, more = self._alerts()
        f_s, f_l = self.f_small, self.f_label
        chip_h, gap = 24 * k, 10 * k
        row_h = 13 * k + 2 * f_s.line + f_l.line  # its app, who it's from and what it says, with room round them
        hot = []
        chips, x = [], pad
        clear = f_s.render("Clear") if items else None
        right = W - pad - (clear.shape[1] + 10 * k if clear is not None else 0)
        for key, label in [(None, f"All  {len(items)}")] + [(app, app) for app in apps]:
            cover = f_s.render(f_s.fit(label, 110 * k))
            w = cover.shape[1] + 20 * k
            if x + w > right:
                break
            chips.append((key, cover, x, w))
            hot.append((f"chip:{key or ''}", x, y0, x + w, y0 + chip_h))
            x += w + 6 * k
        if clear is not None:
            hot.append(("clear", right, y0, W - pad, y0 + chip_h))
        ry = y0 + chip_h + gap
        for i in range(len(rows)):
            hot.append((f"alert:{i}", pad, ry + i * row_h, W - pad, ry + (i + 1) * row_h))
        body_h = chip_h + gap + max(1, len(rows)) * row_h + (f_s.line + 2 * k if more else 0)
        bs = round(30 * k)
        badges = [art.badge(n["app"], bs, self._text) for n in rows]
        tx = pad + bs + 11 * k
        tw = W - tx - pad

        def draw(cv, ox, oy, Wn, Hn, a, now):
            for key, cover, cx0, w in chips:
                on = key == self.alerts_app
                fill = ORANGE if on else _mix(th["body"], th["text"], 0.09)
                cv.shape(lambda xs, ys, cx0=cx0, w=w: face.rbox(xs, ys, ox + cx0 + w / 2, oy + y0 + chip_h / 2, w / 2,
                                                                chip_h / 2, chip_h / 2),
                         (ox + cx0 - 1, oy + y0 - 1, ox + cx0 + w + 1, oy + y0 + chip_h + 1), fill, a)
                cv.text(cover, ox + cx0 + 10 * k - 2, oy + y0 + chip_h / 2 - f_s.line / 2 - 1,
                        (1.0, 1.0, 1.0) if on else th["text"], a)
            if clear is not None:
                cv.text(clear, ox + Wn - pad - clear.shape[1] + 2, oy + y0 + chip_h / 2 - f_s.line / 2 - 1,
                        th["muted"], a)
            if not rows:
                cx = ox + Wn / 2
                face.bell_glyph(cv, cx, oy + ry + 14 * k, 22 * k, th["muted"], a)
                cover = f_s.render("Nothing yet: what the apps you pick say lands here")
                cv.text(cover, cx - cover.shape[1] / 2, oy + ry + 30 * k, th["muted"], a)
                return
            for i, n in enumerate(rows):
                y = oy + ry + i * row_h
                if i:
                    cv.shape(lambda xs, ys, y=y: face.segment(xs, ys, ox + tx, y, ox + Wn - pad, y, max(1.0, 0.8 * k)),
                             (ox + tx - 1, y - 2, ox + Wn - pad + 1, y + 2), _mix(th["body"], th["text"], 0.1), a)
                cv.image(badges[i], ox + pad, y + 8 * k, a)
                ago = f_s.render(_ago(now - n.get("at", now)))
                cv.text(ago, ox + Wn - pad - ago.shape[1] + 2, y + 6 * k, th["muted"], a)
                head = f_s.render(f_s.fit(n["app"] + (" \u00b7 on your phone" if n.get("phone") else ""),
                                          tw - ago.shape[1] - 8 * k))
                cv.text(head, ox + tx - 2, y + 6 * k, th["muted"], a)
                cv.text(f_l.render(f_l.fit(n.get("title") or n["app"], tw)), ox + tx - 2, y + 6 * k + f_s.line,
                        th["text"], a)
                if n.get("text"):
                    words = " ".join(str(n["text"]).split())
                    cv.text(f_s.render(f_s.fit(words, tw)), ox + tx - 2, y + 6 * k + f_s.line + f_l.line,
                            th["muted"], a)
            if more:
                cover = f_s.render(f"{more} more")
                cv.text(cover, ox + Wn / 2 - cover.shape[1] / 2, oy + ry + len(rows) * row_h, th["muted"], a)
        key = (self.alerts_app, len(items), tuple((n["app"], n.get("title"), n.get("at")) for n in rows),
               tuple(_ago(now - n.get("at", now)) for n in rows))
        return body_h, draw, hot, key

    def _hub_today(self, W, pad, y0, d, now):
        """Today, as Glance's weather and reminders: the weather now, big, with how it feels, the next six hours and
        the next days, from Open-Meteo through the Hub (at most every half hour, while the panels are open); under it
        your to-do list (todo.py), a ring to tick each off and Add, which opens her typing box. (its height, draw, its
        places to click, what it shows)"""
        k, th = self.k, self.theme()
        w = d.get("weather") if isinstance(d.get("weather"), dict) else None
        todo = [t for t in (d.get("todo") or []) if isinstance(t, dict)]
        f_s, f_l, f_t = self.f_small, self.f_label, self.f_title
        big = self._text(round(30 * k), 300)
        inner = W - 2 * pad
        now_h = big.line + 4 * k
        hours = (w.get("hourly") or [])[:6] if w else []
        days = (w.get("days") or [])[:3] if w else []
        hour_h = (f_s.line * 2 + 30 * k) if hours else 0
        day_h = (f_s.line + 6 * k) if days else 0
        wy = y0
        ty = wy + (now_h + 8 * k + hour_h + day_h if w else f_s.line + 8 * k) + 8 * k  # the to-do list's top
        row_h = f_l.line + 10 * k
        hot = [("todo_add", W - pad - f_l.measure("+ Add") - 8 * k, ty - 2 * k, W - pad, ty + f_l.line + 2 * k)]
        for i, t in enumerate(todo):
            y = ty + f_l.line + 8 * k + i * row_h
            hot.append((f"tick:{t['id']}", pad, y, pad + 26 * k, y + row_h))
        body_h = ty - y0 + f_l.line + 8 * k + max(1, len(todo)) * row_h

        def draw(cv, ox, oy, Wn, Hn, a, now):
            if w:
                face.cloud_glyph(cv, ox + pad + 18 * k, oy + wy + now_h / 2, 32 * k, CYAN, a, w.get("sky"))
                temp = big.render(f"{w.get('temp')}\u00b0")
                cv.text(temp, ox + pad + 42 * k, oy + wy, th["text"], a)
                tx = ox + pad + 42 * k + temp.shape[1] + 10 * k
                cv.text(f_l.render(str(w.get("sky") or "").capitalize()), tx - 2, oy + wy + 4 * k, th["text"], a)
                cv.text(f_s.render(f_s.fit(str(w.get("place") or ""), 140 * k)), tx - 2, oy + wy + 4 * k + f_l.line,
                        th["muted"], a)
                bits = [f"Feels {w['feels']}\u00b0" if w.get("feels") is not None else "",
                        f"{w['humidity']}% humid" if w.get("humidity") is not None else "",
                        f"{w['wind']} km/h wind" if w.get("wind") is not None else ""]
                for j, bit in enumerate(b for b in bits if b):
                    cover = f_s.render(bit)
                    cv.text(cover, ox + Wn - pad - cover.shape[1] + 2, oy + wy + 2 * k + j * f_s.line, th["muted"], a)
                y = oy + wy + now_h + 8 * k
                if hours:
                    step = inner / len(hours)
                    for j, hr in enumerate(hours):
                        cx = ox + pad + step * (j + 0.5)
                        h12 = hr["hour"] % 12 or 12
                        lab = f_s.render("Now" if j == 0 else f"{h12} {'am' if hr['hour'] < 12 else 'pm'}")
                        cv.text(lab, cx - lab.shape[1] / 2, y, th["muted"], a)
                        face.cloud_glyph(cv, cx, y + f_s.line + 10 * k, 15 * k, th["text"], a, hr.get("sky"))
                        t = f_s.render(f"{hr['temp_c']}\u00b0")
                        cv.text(t, cx - t.shape[1] / 2, y + f_s.line + 20 * k, th["text"], a)
                    y += hour_h
                if days:
                    step = inner / len(days)
                    for j, day in enumerate(days):
                        cx = ox + pad + step * (j + 0.5)
                        name = _day_name(day.get("day"), j)
                        words = f_s.render(f"{name}  {day['high_c']}\u00b0 / {day['low_c']}\u00b0")
                        cv.text(words, cx - words.shape[1] / 2, y, th["muted"], a)
            else:
                cover = f_s.render("The weather shows here once it's read (it's on in the Island tab)")
                cv.text(cover, ox + Wn / 2 - cover.shape[1] / 2, oy + wy, th["muted"], a)
            cv.shape(lambda xs, ys: face.segment(xs, ys, ox + pad, oy + ty - 6 * k, ox + Wn - pad, oy + ty - 6 * k,
                                                 max(1.0, 0.8 * k)),
                     (ox + pad - 1, oy + ty - 8 * k, ox + Wn - pad + 1, oy + ty - 4 * k), _mix(th["body"], th["text"], 0.1),
                     a)
            cv.text(f_l.render("To do"), ox + pad - 2, oy + ty, th["text"], a)
            add = f_l.render("+ Add")
            cv.text(add, ox + Wn - pad - add.shape[1] + 2, oy + ty, CYAN, a)
            if not todo:
                cover = f_s.render("Nothing on it. Say \u201cadd milk to my to-do list\u201d, or Add")
                cv.text(cover, ox + pad - 2, oy + ty + f_l.line + 12 * k, th["muted"], a)
            for i, t in enumerate(todo):
                y = oy + ty + f_l.line + 8 * k + i * row_h
                cy, cx, rr = y + row_h / 2, ox + pad + 9 * k, 7.5 * k
                cv.shape(lambda xs, ys, cx=cx, cy=cy: np.abs(face.circle(xs, ys, cx, cy, rr)) - 0.7 * k,
                         (cx - rr - 2, cy - rr - 2, cx + rr + 2, cy + rr + 2), th["muted"], a)
                cv.text(f_l.render(f_l.fit(t["text"], Wn - 2 * pad - 30 * k)), ox + pad + 26 * k - 2,
                        cy - f_l.line / 2 - 1, th["text"], a)
        key = (w and (w.get("temp"), w.get("sky"), tuple(h.get("temp_c") for h in hours)),
               tuple((t["id"], t["text"]) for t in todo))
        return body_h, draw, hot, key

    def _alerts(self):
        """Recent notifications: (all of them, the apps most came from, three at most, the newest few of the one
        picked, how many more of it there are)."""
        items = [n for n in self.recent if isinstance(n, dict) and n.get("app")]
        counts = {}
        for n in items:
            counts[n["app"]] = counts.get(n["app"], 0) + 1
        apps = sorted(counts, key=lambda app: -counts[app])[:3]
        if self.alerts_app not in counts:
            self.alerts_app = None
        picked = [n for n in items if self.alerts_app is None or n["app"] == self.alerts_app]
        return items, apps, picked[:3], max(0, len(picked) - 3)

    def _hub_shelf(self, W, pad, y0, d, now):
        """The shelf: files dropped on her eyes, kept here for later (_shelf), each with its icon, its name and its
        size, and an x to take it off; a click opens one, a right-click has the rest, and one dragged out goes where
        it's dropped. Under them, that the files stay where they are, on this PC, as Glance says of its shelf."""
        k, th = self.k, self.theme()
        everything = list(self.shelf_items())
        clips = [c for c in self.clips if isinstance(c, dict)]
        # chips along its top, as Glance's shelf has them: all of it, its pictures, its documents, and what you copied
        pics = [p for p in everything if os.path.splitext(p)[1].lower() in PICTURES]
        docs = [p for p in everything if p not in pics]
        views = ((None, f"All  {len(everything)}"), ("pictures", f"Pictures  {len(pics)}"),
                 ("documents", f"Documents  {len(docs)}"), ("copied", f"Copied  {len(clips)}"))
        view = self.shelf_view if self.shelf_view in ("pictures", "documents", "copied") else None
        f = self.f_small
        chip_h = 22 * k
        chips, hot, cx0 = [], [], pad
        for key_, label in views:
            cover = f.render(label)
            cw = cover.shape[1] + 18 * k
            chips.append((key_, cover, cx0, cw))
            hot.append((f"view:{key_ or 'all'}", cx0, y0, cx0 + cw, y0 + chip_h))
            cx0 += cw + 6 * k
        y_chips, y0 = y0, y0 + chip_h + 10 * k

        def draw_chips(cv, ox, oy, a):
            for key_, cover, x, cw in chips:
                on = key_ == view
                cv.shape(lambda xs, ys, x=x, cw=cw: face.rbox(xs, ys, ox + x + cw / 2, oy + y_chips + chip_h / 2, cw / 2,
                                                              chip_h / 2, chip_h / 2),
                         (ox + x - 1, oy + y_chips - 1, ox + x + cw + 1, oy + y_chips + chip_h + 1),
                         VIOLET if on else _mix(th["body"], th["text"], 0.09), a)
                cv.text(cover, ox + x + 9 * k - 2, oy + y_chips + chip_h / 2 - f.line / 2 - 1,
                        (1.0, 1.0, 1.0) if on else th["text"], a)
        if view == "copied":
            return self._shelf_clips(W, pad, y0, clips, chip_h + 10 * k, draw_chips, hot, now)
        shown_ = pics if view == "pictures" else docs if view == "documents" else everything
        index = [everything.index(p) for p in shown_]  # where each is on the shelf, which a click names
        items = shown_
        tile_w, tile_h = 70 * k, 80 * k
        per_row = max(1, int((W - 2 * pad) // tile_w))
        if not items:
            body_h = 86 * k + chip_h + 10 * k
        else:
            rows = math.ceil(len(items) / per_row)
            body_h = rows * tile_h + self.f_small.line + 4 * k + chip_h + 10 * k
            for i in range(len(items)):
                row, col = divmod(i, per_row)
                x = pad + col * tile_w
                y = y0 + row * tile_h
                n = index[i]
                hot.append((f"unshelf:{n}", x + tile_w - 18 * k, y, x + tile_w, y + 18 * k))  # before the tile's own
                hot.append((f"shelf:{n}", x, y, x + tile_w, y + tile_h))
        icons = [self._file_icon(path, round(34 * k)) for path in items]
        sizes = [_file_size(path) for path in items]

        def draw(cv, ox, oy, Wn, Hn, a, now):
            draw_chips(cv, ox, oy, a)
            if not items:
                cx = ox + Wn / 2
                face.tray_glyph(cv, cx, oy + y0 + 22 * k, 30 * k, th["muted"], a)
                for j, words in enumerate(("Drop files on her eyes to keep them here", "for later, then drag them out "
                                           "where they're going")):
                    cover = f.render(words)
                    cv.text(cover, cx - cover.shape[1] / 2, oy + y0 + 46 * k + j * f.line, th["muted"], a)
                return
            for i, path in enumerate(items):
                row, col = divmod(i, per_row)
                x, y = ox + pad + col * tile_w, oy + y0 + row * tile_h
                pic = icons[i]
                if pic is not None:
                    cv.image(pic, x + tile_w / 2 - pic.shape[1] / 2, y + 4 * k, a)
                face.close_glyph(cv, x + tile_w - 9 * k, y + 8 * k, 8 * k, th["muted"], a)
                name = f.fit(os.path.basename(path.rstrip("\\/")) or path, tile_w - 4 * k)
                cover = f.render(name)
                cv.text(cover, x + tile_w / 2 - cover.shape[1] / 2, y + 42 * k, th["text"], a)
                if sizes[i]:
                    cover = f.render(sizes[i])
                    cv.text(cover, x + tile_w / 2 - cover.shape[1] / 2, y + 42 * k + f.line, th["muted"], a)
            cover = f.render("Only where they are is kept: your files stay on this PC")
            cv.text(cover, ox + Wn / 2 - cover.shape[1] / 2, oy + y0 + math.ceil(len(items) / per_row) * tile_h,
                    th["muted"], a)
        return body_h, draw, hot, (view, tuple(items), tuple(sizes), len(clips))

    def _shelf_clips(self, W, pad, y0, clips, top, draw_chips, hot, now):
        """The shelf's Copied: the words you copied, newest first, a key or a password only by its first letters
        (island_plugins.shown), a link with a link's glyph; a click copies one again, as Glance's clipboard has them.
        In memory only, while she runs."""
        k, th = self.k, self.theme()
        f, f_l = self.f_small, self.f_label
        rows = clips[:6]
        row_h = f_l.line + 12 * k
        for i in range(len(rows)):
            hot.append((f"clip:{i}", pad, y0 + i * row_h, W - pad, y0 + (i + 1) * row_h))
        body_h = top + max(1, len(rows)) * row_h

        def draw(cv, ox, oy, Wn, Hn, a, now):
            draw_chips(cv, ox, oy, a)
            if not rows:
                cover = f.render("What you copy shows here, to copy again. Never a password manager's")
                cv.text(cover, ox + Wn / 2 - cover.shape[1] / 2, oy + y0 + 6 * k, th["muted"], a)
                return
            for i, c in enumerate(rows):
                y = oy + y0 + i * row_h
                cy = y + row_h / 2
                if c.get("link"):
                    face.GLYPHS["link"](cv, ox + pad + 8 * k, cy, 14 * k, BLUE, a)
                else:
                    _copy_glyph(cv, ox + pad + 8 * k, cy, 13 * k, th["muted"], th["body"], a)
                ago = f.render(_ago(now - c.get("at", now)))
                cv.text(ago, ox + Wn - pad - ago.shape[1] + 2, cy - f.line / 2 - 1, th["muted"], a)
                words = f_l.fit(str(c.get("text") or ""), Wn - 2 * pad - 32 * k - ago.shape[1])
                cv.text(f_l.render(words), ox + pad + 24 * k - 2, cy - f_l.line / 2 - 1, th["text"], a)
        return body_h, draw, hot, ("copied", tuple((c.get("text"), c.get("at")) for c in rows))

    def _hub_press(self, name, right):
        """A click on the panels: a tab, her eyes (they close), a control, a month, the focus timer, a device or a
        shelf's file. Never while she's doing a task in an app (_agent_busy)."""
        if not name or name in ("stay",) or name.startswith("slider:"):
            return
        if self._agent_busy():
            print(f"  island: {name} not pressed, she's doing a task in an app")
            return
        kind, _, arg = name.partition(":")
        if kind == "tab":
            self._hub_go(arg)
        elif kind == "close":
            self._hub_close()
        elif kind == "toggle":
            self._hub_toggle(arg, right)
        elif kind == "mute":
            d = self.hub_data if self.hub_data is not None else {}
            d["muted"] = not d.get("muted")
            self.hub_data = d
            self.runner.do("hub", "mute", d["muted"])
        elif kind == "month":
            import datetime as dt
            if arg == "0":
                self.hub_month = None
            else:
                y, m = self.hub_month or (dt.date.today().year, dt.date.today().month)
                m += int(arg)
                y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
                self.hub_month = (y, m)
            self._hub_want()
        elif kind == "focus":
            foc = _focus()
            if foc is not None and arg in ("start", "pause", "resume", "skip", "stop"):
                getattr(foc, arg)()
        elif kind == "out":
            self.runner.do("hub", "output", arg)
        elif kind == "drive":
            self.runner.do("hub", "open_drive", arg)
        elif kind == "shelf":
            self._shelf_press(int(arg), right)
            return
        elif kind == "view":  # the shelf's kinds
            self.shelf_view = None if arg == "all" else arg
        elif kind == "clip":  # one you copied, copied again
            clips = [c for c in self.clips if isinstance(c, dict)][:6]
            if 0 <= int(arg) < len(clips) and not right:
                c = clips[int(arg)]
                win.set_clipboard(c["full"])
                self.popups.append(plugins.Activity("clipboard", "copied", {"how": "copy", "what": "text",
                                                                            "text": c.get("text") or ""}, seconds=1.6))
        elif kind == "tick":  # Today's to-do list
            d = self.hub_data if self.hub_data is not None else {}
            d["todo"] = [t for t in d.get("todo") or [] if str(t.get("id")) != arg]
            self.hub_data = d
            self.runner.do("hub", "tick", arg)
        elif kind == "todo_add":
            self.ask("Add to my to-do list: ", under=False)
        elif kind == "unshelf":
            items = self.shelf_items()
            if 0 <= int(arg) < len(items) and not right:
                self._shelf_drop(items[int(arg)])
            return
        elif kind == "chip":  # Recent's apps
            self.alerts_app = arg or None
        elif kind == "alert":
            rows = self._alerts()[2]
            if 0 <= int(arg) < len(rows) and not right:
                self.runner.do("notifications", "open", {"app_id": rows[int(arg)].get("app_id", ""),
                                                         "app": rows[int(arg)]["app"]})
        elif kind == "clear":
            self.recent, self.alerts_app = [], None
        self.dirty = True
        self._wake()

    def _hub_toggle(self, name, right):
        """Wi-Fi, Bluetooth or Do Not Disturb switched, shown switched at once; a right-click opens its page in
        Windows' Settings instead."""
        if right:
            page = {"wifi": "ms-settings:network-wifi", "bluetooth": "ms-settings:bluetooth",
                    "dnd": "ms-settings:notifications", "awake": "ms-settings:powersleep"}.get(name)
            if page:
                self.runner.do("hub", "page", page)
            return
        if name == "dnd":
            settings.put("island_dnd", not settings.get("island_dnd"))
            return
        if name == "awake":
            win.keep_awake(not win.awake())
            return
        d = self.hub_data if self.hub_data is not None else {}
        if d.get(name) is None:  # not read yet: nothing to switch from
            return
        d[name] = not d[name]
        self.hub_data = d
        self.runner.do("hub", name, d[name])

    def _press_down(self):
        """The button down on a panel's slider: it's held (drag) and set where it's pressed. On a shelf's file: it
        may be dragged out (shelf_drag)."""
        lay = self.layout
        self.dragged_out = False  # a new press: whatever was dragged out before is done with
        if lay is None or lay.kind != "hub":
            return
        px, py = win.cursor_pos()
        name = self._hot(px - self.origin.x, py - self.origin.y) or ""
        if self._agent_busy():
            return
        if name.startswith("shelf:"):
            self.shelf_drag = (int(name.split(":", 1)[1]), px, py)
        if not name.startswith("slider:"):
            return
        self.drag = (name.split(":", 1)[1],)
        self._drag_to(px)

    def _press_move(self):
        if self.drag is not None:
            self._drag_to(win.cursor_pos()[0])
        elif self.shelf_drag is not None:
            i, x0, y0 = self.shelf_drag
            px, py = win.cursor_pos()
            if abs(px - x0) + abs(py - y0) > 6:  # it's moving: out it goes, as File Explorer drags a file
                self.shelf_drag = None
                items = self.shelf_items()
                import shelf
                if 0 <= i < len(items) and (self.ole or shelf.ole()):
                    self.ole = True
                    self.dragged_out = True
                    shelf.drag_out(self.hwnd, [items[i]])

    # ------------------------------------------------------------------ the shelf (30 October 2026)
    shelf = shelf_drag = None
    dragged_out = dropping = False

    def shelf_items(self):
        """The shelf's files, newest first (shelf.py), as kept from last time if Settings keeps them."""
        if self.shelf is None:
            try:
                import shelf
                self.shelf = shelf.load()
            except Exception:
                self.shelf = []
        return self.shelf

    def _dropped(self, paths):
        """Files dropped on her eyes: on the shelf, newest first, and the shelf opened to show them."""
        import shelf
        items = shelf.added(self.shelf_items(), paths)
        if not items:
            return
        self.shelf = items
        shelf.save(items)
        self.dropping = False
        self._feel("happy", time.time())
        if not self._hub_open("shelf"):
            self.dirty = True
            self._wake()

    def _file_icon(self, path, size):
        """A shelf file's picture at size px, or None while it's being fetched: on a thread of its own, as the shell
        takes 80 to 200 ms to make one (measured 30 October 2026), and the panels drawn again once it's here."""
        icons = self.__dict__.setdefault("file_icons", {})
        key = (path, size)
        if key in icons:
            return icons[key]
        icons[key] = None

        def fetch():
            ctypes.windll.ole32.CoInitializeEx(None, 2)  # the shell's pictures want an apartment of their own
            icons[key] = art.file_icon(path, size)
            runner = getattr(self, "runner", None)
            if runner is not None:
                runner.post(("touch",))
        threading.Thread(target=fetch, name="island-file-icon", daemon=True).start()
        return None

    def _shelf_press(self, i, right):
        """A shelf's file clicked: opened; right-clicked: what else can be done with it."""
        items = self.shelf_items()
        if self.dragged_out:  # the button came up at the end of a drag out: not a click
            self.dragged_out = False
            return
        if not 0 <= i < len(items):
            return
        path = items[i]
        if not right:
            try:
                os.startfile(path)
            except OSError as exc:
                print(f"  shelf: couldn't open it ({exc!r})")
            return
        import shelf
        menu = tk.Menu(self.top, tearoff=0)
        menu.add_command(label="Open", command=lambda: os.startfile(path) if os.path.exists(path) else None)
        menu.add_command(label="Show in folder", command=lambda: shelf.show_in_folder(path))
        menu.add_command(label="Copy", command=lambda: win.set_clipboard_files([path]))
        menu.add_separator()
        menu.add_command(label="Take off the shelf", command=lambda: self._shelf_drop(path))
        menu.add_command(label="Clear the shelf", command=lambda: self._shelf_drop(None))
        px, py = win.cursor_pos()
        try:
            menu.tk_popup(px, py)
        finally:
            menu.grab_release()

    def _shelf_drop(self, path):
        """path taken off the shelf, or all of them with None."""
        import shelf
        self.shelf = [p for p in self.shelf_items() if path is not None and p != path]
        shelf.save(self.shelf)
        self.dirty = True
        self._wake()

    def _drag_to(self, px):
        """The held slider set to where the pointer is across it, px on the screen."""
        lay = self.layout
        if lay is None or self.drag is None:
            return
        what = self.drag[0]
        box = next((h for h in lay.hot if h[0] == f"slider:{what}"), None)
        if box is None:
            return
        x0 = self.origin.x + self.island_rect[0] + box[1]
        x1 = self.origin.x + self.island_rect[0] + box[3]
        self._set_level(what, int(round(max(0.0, min(1.0, (px - x0) / max(1.0, x1 - x0))) * 100)))

    def _set_level(self, what, level):
        """The volume or the brightness at level, 0 to 100: shown at once, and sent to the plugins' thread, which
        sets it (island_plugins.Hub.command)."""
        d = self.hub_data if self.hub_data is not None else {}
        if d.get(what) == level and not (what == "volume" and d.get("muted")):
            return
        d[what] = level
        if what == "volume" and level > 0:
            d["muted"] = False
        self.hub_data = d
        self.runner.do("hub", what, level)
        self.dirty = True
        self._wake()

    def _wheel(self, delta):
        """The wheel over the island: over a slider it moves it 5 at a time; over the panels it goes on to the next
        one (back for the wheel up); over her eyes or what's on it opens the panels, as bloom's notch does."""
        notches = int(delta / 120) or (1 if delta > 0 else -1 if delta < 0 else 0)
        lay = self.layout
        if not notches or lay is None or self.harry is not None:
            return
        if lay.kind == "hub":
            px, py = win.cursor_pos()
            name = self._hot(px - self.origin.x, py - self.origin.y) or ""
            if name.startswith("slider:") or name == "mute":
                what = "volume" if name == "mute" else name.split(":", 1)[1]
                level = (self.hub_data or {}).get(what)
                if level is not None and not self._agent_busy():
                    self._set_level(what, max(0, min(100, int(level) + 5 * notches)))
                return
            now = time.time()
            if now - self.wheel_at >= 0.3:
                self.wheel_at = now
                self._hub_go(-1 if notches > 0 else 1)
            return
        if self._hub_on():
            self.wheel_at = time.time()
            self._hub_open()

    # ------------------------------------------------------------------ what's beside her eyes (30 October 2026)
    def _status_widgets(self):
        """The widgets beside her eyes while nothing's on (Settings > Island > Beside her eyes, island_status), in
        order: [] for none, as the owner had it from 27 October."""
        raw = str(settings.get("island_status") or "")
        return [w for w in (s.strip() for s in raw.split(",")) if w in STATUS_WIDGETS][:len(STATUS_WIDGETS)]

    def _status_parts(self):
        """The widgets beside her eyes as the capsule's parts: (width, draw, "left" or "right", what it shows). The
        first half go left of her eyes, the rest right; one alone goes right."""
        names = self._status_widgets() if self.style == "capsule" else []
        if not names:
            return []
        k, th = self.k, self.theme()
        d = self.hub_data or {}
        f = self.f_compact
        parts = []
        for i, name in enumerate(names):
            side = "left" if i < len(names) // 2 else "right"
            if name == "time":  # drawn again each minute: the Hub sends its clock as it changes
                words = _now()
                parts.append((*self._slot_text(words, th["text"]), side, ("time", words)))
            elif name == "battery" and d.get("battery"):
                pct, charging = d["battery"]
                words = f"{pct}%"
                bh = 9 * k
                tw = f.measure(words)
                low = pct <= 20 and not charging

                def draw(cv, x, cy, a, now, pct=pct, charging=charging, words=words, low=low, bh=bh):
                    face.battery(cv, x, cy, bh, pct, th["text"], RED if low else GREEN if charging else th["text"],
                                 charging, a)
                    cv.text(f.render(words), x + bh * 1.9 + 6 * k - 2, cy - f.line / 2 - 1, th["text"], a)
                parts.append((bh * 1.9 + 6 * k + tw, draw, side, ("battery", pct, charging)))
            elif name == "weather" and d.get("weather"):
                w = d["weather"]
                words = f"{w['temp']}\u00b0"

                def draw(cv, x, cy, a, now, words=words, sky=w.get("sky")):
                    face.cloud_glyph(cv, x + 8 * k, cy, 17 * k, th["text"], a, sky)
                    cv.text(f.render(words), x + 19 * k - 2, cy - f.line / 2 - 1, th["text"], a)
                parts.append((19 * k + f.measure(words), draw, side, ("weather", w["temp"], w.get("sky"))))
            elif name in ("cpu", "ram") and d.get(name) is not None:
                words = f"{name.upper()} {d[name]}%"
                parts.append((*self._slot_text(words, th["text"]), side, (name, d[name])))
        return parts

    # ------------------------------------------------------------------ a device's popup (30 October 2026)
    def _device(self, act):
        """Headphones, earbuds or a speaker connected or gone, sound moved to another, or a USB drive in, small, as
        a phone's island shows AirPods: what it is drawn on the left, her eyes, "Connected" over its name, and its
        battery in a ring when Windows has it."""
        k, th = self.k, self.theme()
        d = act.data
        kind, event = d.get("kind"), d.get("event")
        s = 22 * k
        glyph = face.DEVICE_GLYPHS.get(kind)

        def icon(cv, x, cy, a, now):
            if glyph is None:
                face.speaker_glyph(cv, x + s / 2, cy, s, th["text"], a)
            else:
                glyph(cv, x + s / 2, cy, s, th["text"], a)
        fl, fn = self._text(round(10.5 * k), 600), self._text(round(14 * k), 700)  # small and grey over it, as a phone
        name = fn.fit(str(d.get("name") or ""), 150 * k)
        label = str(d.get("label") or "")
        tw = max(fl.measure(label), fn.measure(name))

        def words(cv, x, cy, a, now):
            cv.text(fl.render(label), x - 2, cy - fl.line - 0.5 * k, th["muted"], a)
            cv.text(fn.render(name), x - 2, cy - 2 * k, th["text"], a)
        battery = d.get("battery")
        r = 13 * k
        expr = "headphones" if event == "connected" and kind in ("buds", "headphones", "jack") else \
            "surprised" if event == "drive" else "open"
        parts = [(s, icon), self._face(expr, GREEN if event == "connected" else None), (tw, words)]
        if battery is not None:
            parts.append((2 * r, lambda cv, x, cy, a, now: self._battery_ring(cv, x + r, cy, r, battery, a)))
        key = ("device", event, kind, name, battery, id(act))
        if self.style != "capsule":
            return self._row(key, "device", expr, (s, icon), self._slot_text(name, th["text"]),
                             hot=[("open", 0, 0, 10000, 10000)])
        return self._capsule(key, "device", parts, hot=[("open", 0, 0, 10000, 10000)], tall=True)

    def _glass_device(self, act):
        """A device's popup opened while you point at it: what it is and her eyes at its top, its name big, how
        it's connected or how full it is, its battery in a line, and Sound settings, or Open for a drive."""
        k, th = self.k, self.theme()
        d = act.data
        kind, event = d.get("kind"), d.get("event")
        W, pad = self.CARD_W * k, self.CARD_PAD * k
        glyph = face.DEVICE_GLYPHS.get(kind)

        def icon(cv, x, cy, a, now):
            if glyph is None:
                face.speaker_glyph(cv, x + 9 * k, cy, 18 * k, th["muted"], a)
            else:
                glyph(cv, x + 9 * k, cy, 18 * k, th["muted"], a)
        bus = str(d.get("bus") or "")
        where = "USB drive" if event == "drive" else "Bluetooth" if bus.startswith("BTH") else \
            "USB" if bus == "USB" else "Sound"
        expr = "headphones" if event == "connected" and kind in ("buds", "headphones", "jack") else "open"
        head_h, head, expr = self._live_head(W, where, icon, expr, GREEN if event == "connected" else None)
        title = self.f_title.fit(str(d.get("name") or ""), W - 2 * pad)
        if event == "drive":
            sub = f"{_size(d.get('free') or 0)} free of {_size(d.get('total') or 0)}"
        else:
            sub = str(d.get("label") or "") + (f" \u00b7 {DEVICE_WORDS.get(kind, 'Sound')}" if kind else "")
        battery = d.get("battery")
        y_t = pad + head_h + 8 * k
        y_s = y_t + self.f_title.line + 2 * k
        y_l = y_s + self.f_label.line + 10 * k
        bh = 28 * k
        y_b = (y_l + 12 * k) if battery is not None else y_s + self.f_label.line + 12 * k
        H = y_b + bh + pad
        words = "Open" if event == "drive" else "Sound settings"
        bw = self.f_label.measure(words) + 28 * k
        hot = [("open", W - pad - bw, y_b, W - pad, y_b + bh), ("dismiss", W - 34 * k, 0, W, pad + head_h + 4 * k),
               ("open", 0, 0, W, H)]

        def draw(cv, ox, oy, Wn, Hn, a, now):
            head(cv, ox, oy, Wn, a, now)
            cv.text(self.f_title.render(title), ox + pad - 2, oy + y_t, th["text"], a)
            cv.text(self.f_label.render(sub), ox + pad - 2, oy + y_s, th["muted"], a)
            if battery is not None:
                colour = GREEN if battery >= 30 else ORANGE if battery >= 15 else RED
                pct = self.f_label.render(f"{battery}%")
                cv.text(pct, ox + Wn - pad - pct.shape[1] + 2, oy + y_l - self.f_label.line / 2 - 1, colour, a)
                self._line(cv, ox + pad, ox + Wn - pad - pct.shape[1] - 6 * k, oy + y_l, 4 * k, battery / 100, colour,
                           now, th["track"], a)
            self._pill_button(cv, ox + Wn - pad - bw, oy + y_b, bw, bh, words, "open",
                              BLUE if event != "drive" else ORANGE, a)
        return Layout(("device-card", kind, title, battery, id(act)), "device", W, H, draw, radius=self._corner(),
                      hot=hot, eyes=expr, face=True)

    # ------------------------------------------------------------------ the music's bars (30 October 2026)
    def _bands(self):
        """The music's five bands now, each 0 to 1 (visualizer.Bands), or None while they aren't being listened to."""
        runner = getattr(self, "runner", None)
        media = runner.plugin("media") if runner is not None else None
        bands = getattr(media, "bands", None)
        return list(bands.levels) if bands is not None and bands.running else None

    def _bars_step(self, dt):
        """The five bars sprung toward the bands (bubble.Spring, a little bounce), once a frame while music shows."""
        levels = self._bands()
        if levels is None:
            self.bar_springs = None
            return
        if self.bar_springs is None or len(self.bar_springs) != len(levels):
            self.bar_springs = [Spring(v, 0.2, 0.55) for v in levels]
        for spring, v in zip(self.bar_springs, levels):
            spring.go(v)
            spring.step(dt)

    def _music_bars(self, cv, x, cy, h, colour, level, playing, now, a):
        """The bars that go with the music, from x and centred on cy, h px tall at most: five, its lows to its
        highs, while they're being listened to; else the four that dance by how loud it is, as before."""
        springs = self.bar_springs if playing else None
        if springs is None:
            face.equalizer(cv, x, cy, h, colour, level, now - self.t0, a)
            return
        w = max(1.6, h * 0.16)
        for i, spring in enumerate(springs):
            bh = h * max(0.14, min(1.08, spring.x))
            bx = x + w / 2 + i * w * 2.0
            cv.shape(lambda xs, ys, bx=bx, bh=bh: face.rbox(xs, ys, bx, cy, w / 2, bh / 2, w / 2),
                     (bx - w, cy - h / 2 - 2, bx + w, cy + h / 2 + 2), colour, a)

    def _capsule_wait(self, now, lay, moving):
        """Seconds till the capsule's next frame: at once while it moves, she blinks or her eyes are on their way
        somewhere, 30 a second while the dots go with a voice or hearts beat, once a second for a long job, and
        otherwise only at her next blink or glance about or when a reaction ends, with the mouse moving her eyes by
        _follow in between. Never a frame for nothing."""
        e = self.eyes
        if moving or e.blink_at is not None or self._looking():
            return 0.016
        rate = self._rate(lay, now)
        if lay.animated or (lay.cap is not None and lay.cap.animated):
            wait = 0.033
        elif rate:
            wait = 1.0 / rate
        else:
            wait = 3600.0
        if lay.lively is not None and now < lay.lively[0]:  # and a frame as it comes to rest, drawn still
            wait = min(wait, max(0.016, lay.lively[0] - now + 0.01))
        mood = self._mood(now)
        look = mood or self.eye[0]  # how her eyes look: the reaction while one's on, else the scene's own
        if look in ("love", "happy"):  # the hearts beat and the sparkles twinkle while they're on
            wait = min(wait, 0.033)
        elif mood:
            wait = min(wait, max(0.016, e.mood_until - now + 0.01))
        # a smile, hearts and her eyes asleep in dream mode don't blink: no frame waits for a blink that never comes,
        # whose time, long past, asked for every frame (30 October 2026)
        if look in BLINKS:
            due = e.next_blink
            if lay.wander and self.look_at is None:  # and her next glance about, when the mouse isn't moving her
                due = min(due, e.next_look)
            wait = min(wait, max(0.016, due - now))
        return wait

    def _follow(self, x, y, now):
        """Her eyes toward the pointer at x, y (in the window) while it moves, and back to glancing about on their
        own once it's been still GAZE_HOLD seconds. A frame only when that moves them a whole pixel (draw_eyes moves
        them look * 0.36 of their size across and 0.26 down), so a still or slow mouse costs nothing between the
        70 ms looks at it (_hover_poll); face.Eyes springs them there, as when she glances about."""
        if self.face_at is None:
            return
        if (x, y) != self.pointer:
            self.pointer, self.pointer_at = (x, y), now
        look = None
        if now - self.pointer_at < GAZE_HOLD:
            reach, size = GAZE_REACH * self.k, self.SMALL_EYES * self.k
            sx, sy = 1 / (0.36 * size), 1 / (0.26 * size)  # a whole pixel's worth of looking, across and down
            lx = max(-1.0, min(1.0, (x - self.face_at[0]) / reach))
            ly = max(-1.0, min(1.0, (y - self.face_at[1]) / reach))
            look = (round(lx / sx) * sx, round(ly / sy) * sy)
        if look != self.look_at:
            self.look_at = look
            self._wake()

    # ------------------------------------------------------------------ the frames
    def _wake(self):
        """A frame now, even if the next was set for later (her eyes resting between blinks can wait seconds)."""
        now = time.time()
        if self.job:
            if self.job_due - now <= 0.02:
                return
            self.root.after_cancel(self.job)
        self.last = max(self.last, now - 0.016)
        self.job_due = now
        self.job = self.root.after(0, self._tick)

    def _apply(self, now):
        scene = self._scene(now)
        new = self._make(scene, now)
        self.dirty = False
        if new is None:
            if getattr(self, "runner", None) is not None:
                self.runner.want("media", None)
            if self.fade > 0:
                self.fade = -1
                if self.layout is not None:
                    self.prev, self.prev_alpha, self.layout, self.content = self.layout, self.content, None, 0.0
            return
        if not self.visible_window:
            self._place()
            self.W.jump(new.w * 0.7)
            self.H.jump(new.h * 0.8)
            self.CW.jump(0.0)
            self.CH.jump(0.0)
            self.alpha, self.layout, self.prev, self.cap_alpha = 0.0, None, None, 0.0
            self.buf[:] = 0
            self.drawn = None
            win.show_no_activate(self.hwnd, self.origin.x, self.origin.y, self.cw, self.ch)
            self._push()
            self.visible_window = True
            self._hover_poll()
        self.fade = 1
        old = self.layout
        if old is not None and (new.key == old.key or old.kind == new.kind == "harry" or
                                old.kind == new.kind == "idle" or
                                (old.kind == new.kind and old.kind in ("card", "hub") and old.key[:2] == new.key[:2]) or
                                # the volume moved on, Undo again, a file over the Shelf: in place
                                (old.kind == new.kind and old.kind in ("level", "copied", "drop"))):
            # the same scene with its words moved on, her next step, a card's, a panel's levels: straight away
            self.layout = new
        elif old is None:
            self.layout, self.content, self.changed = new, 0.0, now
        else:
            if self.prev is None or self.content > self.prev_alpha:
                self.prev, self.prev_alpha = old, self.content
            self.layout, self.content, self.changed = new, 0.0, now
        self.W.go(new.w)
        self.H.go(new.h)
        if new.cap:
            self.CW.go(new.cap.w)
            self.CH.go(new.cap.h)
        runner = getattr(self, "runner", None)
        if runner is not None:  # the music's bars listen only while it's shown (island_plugins.Media._bars)
            runner.want("media", True if new.kind == "media" else None)

    def _tick(self):
        self.job = None
        now = time.time()
        self.dt = dt = min(0.05, max(0.0, now - self.last))
        self.last = now
        if self.peek is not None and now >= self.peek[1]:  # a notification done peeking: opened (_peek)
            self.peek = None
            self.dirty = True
        if self.dirty or (self.popup is not None and self.popup.until and now >= self.popup.until and not self.hover):
            self._apply(now)
        if not self.visible_window:
            return
        self._advance(now, dt)
        try:
            t = time.perf_counter()
            changed = self._draw(now)
            if changed is not None:
                self._push(changed)
            self.frame_ms = (time.perf_counter() - t) * 1000
        except Exception as exc:  # a drawing error must never take the app down
            print(f"  island draw failed: {exc!r}")
        if self.fade < 0 and self.alpha <= 0:
            win.hide_window(self.hwnd)
            win.set_click_through(self.hwnd, True)
            self.visible_window, self.layout, self.prev, self.hover = False, None, None, False
            return
        lay = self.layout
        moving = not all(sp.resting() for sp in (self.W, self.H, self.CW, self.CH)) or self.prev is not None \
            or (lay is not None and self.content < 1) or 0 < self.alpha < 1 or 0 < self.cap_alpha < 1 \
            or self._moving(now)
        animated = lay is not None and (lay.animated or (lay.cap is not None and lay.cap.animated))
        eyes_moving = lay is not None and lay.eyes is not None and (self.eyes.blink_at is not None or
                                                                     self.eyes.mood is not None or self._looking())
        idle = lay is not None and lay.kind == "idle"
        if lay is not None and lay.face:
            wait = self._capsule_wait(now, lay, moving)
        elif moving or (animated and self.face_style == "wave") or \
                (eyes_moving and (not idle or self.eyes.blink_at is not None)):
            wait = 0.016
        elif animated or eyes_moving:  # the dots and bars that go with a voice, and her eyes glancing about while
            wait = 0.033  # nothing's on: 30 frames a second look the same, for half the work
        elif lay is not None and self._rate(lay, now):
            wait = 1.0 / self._rate(lay, now)
        elif lay is not None and lay.eyes is not None and self.eye[0] in ("love", "happy"):
            wait = 0.033  # the sparkles twinkle, as on the capsule
        elif lay is not None and lay.eyes is not None:
            wait = self.eyes.wait(now)
        else:
            wait = 1.0
        if lay is not None and not lay.face and lay.lively is not None and now < lay.lively[0]:
            wait = min(wait, max(0.016, lay.lively[0] - now + 0.01))  # a frame as it comes to rest, drawn still
        if self.popup is not None and self.popup.until:
            wait = min(wait, max(0.016, self.popup.until - now))
        if self.peek is not None:
            wait = min(wait, max(0.016, self.peek[1] - now))
        ms = max(16, int(wait * 1000))
        self.job_due = now + ms / 1000
        self.job = self.root.after(ms, self._tick)

    def _advance(self, now, dt):
        """Everything that moves, moved on dt seconds for the frame at now: the fades, the springs that size the island
        and its words' bar, her eyes, and the voice that moves her dots. Drawn after, by _draw."""
        self.alpha = min(1.0, self.alpha + dt / 0.16) if self.fade > 0 else max(0.0, self.alpha - dt / 0.26)
        if self.prev is not None:
            self.prev_alpha -= dt / 0.1
            if self.prev_alpha <= 0:
                self.prev = None
        if self.layout is not None and now - self.changed > 0.06:
            self.content = min(1.0, self.content + dt / 0.18)
        cap = self.layout.cap if self.layout is not None else None
        self.cap_alpha = min(1.0, self.cap_alpha + dt / 0.16) if cap else max(0.0, self.cap_alpha - dt / 0.12)
        for spring in (self.W, self.H, self.CW, self.CH):
            spring.step(dt)
        lay = self.layout or self.prev
        if lay is not None and lay.eyes is not None:  # once a frame, whatever's fading in or out
            self.eye = self.eyes.update(now, dt, lay.eyes, wander=lay.wander, look_at=self.look_at)
        if lay is not None and lay.kind == "media":
            self._bars_step(dt)
        if lay is not None and lay.kind == "harry":
            src = "mic" if self.harry and self.harry["state"] in MIC_STATES else \
                "voice" if self.harry and self.harry["state"] == "speaking" else None
            self.level = bubble.loudness(src, self.level) if src else self.level * 0.85

    def _looking(self):
        e = self.eyes
        return any(abs(e.look[i] - e.target[i]) > 0.004 or abs(e.look_v[i]) > 0.02 for i in (0, 1))

    def _theme_name(self):
        return ("light" if self.light else "dark") if self.theme_name == "system" else self.theme_name

    def _shape(self, x0, W, H, r, y_top, drop=False):
        """(patch slices, cover, alpha with the shadow, the border's cover or None) of a rounded rectangle. Its
        shadow reaches 5.5k past its sides and 8.5k below it, so the patch goes no further; and once inside the
        corners every column is alike, so the middle is worked out once (a 700 px bar costs what a 90 px one
        does)."""
        key = (round(x0 * 2), round(W * 2), round(H * 2), round(r * 2), round(y_top * 2), self._theme_name(),
               self.border, self.style, drop)
        hit = self.shapes.get(key)
        if hit is not None:
            return hit
        k = self.k
        s = self.DROP_SHOULDER * k if drop else 0.0
        X0, X1 = max(0, int(x0 - 6 * k - s - 1)), min(self.cw, int(math.ceil(x0 + W + 6 * k + s + 1)))
        Y0, Y1 = max(0, int(y_top - 3 * k - 1)), min(self.ch, int(math.ceil(y_top + H + 9 * k + 1)))
        xs = np.arange(X0, X1, dtype=np.float32) + 0.5
        ys = np.arange(Y0, Y1, dtype=np.float32)[:, None] + 0.5
        cx, cy = x0 + W / 2, y_top + H / 2
        reach = W / 2 - min(r, W / 2, H / 2) - 7 * k - 2  # past the corners, the shadow's edge and the border
        mid = np.nonzero(np.abs(xs - cx) <= reach)[0] if reach > 0 else ()
        i0 = i1 = None
        if len(mid) > 4:
            i0, i1 = int(mid[0]), int(mid[-1]) + 1
            xs = np.concatenate([xs[:i0], np.asarray([cx], np.float32), xs[i1:]])
        if drop:
            # its shadow from the box alone: from the shoulders too, it ringed their curves in grey
            sd, far = _drop(xs, ys, x0, W, H, r, y_top, s), _drop(xs, ys - 3 * k, x0, W, H, r, y_top, 0.0)
        else:
            sd, far = face.rbox(xs, ys, cx, cy, W / 2, H / 2, r), face.rbox(xs, ys - 3 * k, cx, cy, W / 2, H / 2, r)
        cover = np.clip(0.5 - sd, 0.0, 1.0)
        shadow = self.theme()["shadow"] * np.clip(0.5 - far / (11 * k), 0.0, 1.0) ** 2
        alpha = cover + shadow * (1 - cover)
        if self.style == "capsule":  # glass always has its hairline, about a pixel just inside its edge
            lw = max(1.0, k)
            edge = np.clip(0.5 - (np.abs(sd + 0.5 * lw) - 0.5 * lw), 0.0, 1.0) * cover
            if drop:  # round its sides and bottom, never along the top of the screen it hangs from
                edge *= np.clip((ys - y_top - lw) / lw, 0.0, 1.0)
        else:
            edge = np.clip(0.5 - (np.abs(sd + 0.7 * k) - 0.6 * k), 0.0, 1.0) if self.border else None
        if i0 is not None:
            cover, alpha = _spread(cover, i0, i1), _spread(alpha, i0, i1)
            edge = _spread(edge, i0, i1) if edge is not None else None
        hit = ((slice(Y0, Y1), slice(X0, X1)), cover, alpha, edge)
        if len(self.shapes) > 24:
            self.shapes.clear()
        self.shapes[key] = hit
        return hit

    def _paint(self, sl, cover, alpha, edge, body, items, a, over=None, dots=False, aura=None):
        """A rounded box and what's on it into the window's picture. over: the rows of the patch (from, to) that
        land on something drawn already this frame, which it goes over; the rest was cleared, so it's written.
        dots: paper's dots on it, if it's as tall as a card (_dots). aura: (colour, how strong), a glow round it
        (_glow)."""
        h, w = cover.shape
        col = np.empty((h, w, 3), np.float32)
        col[:] = body
        if dots and self.theme().get("dots") and h > 70 * self.k:
            self._dots(col, sl)
        op = self._glass(col, cover)
        cv = face.Canvas(col, op=op)
        for draw, ia in items:
            if ia > 0.01:
                draw(cv, min(ia, 1.0))
        self._compose(self.buf[sl], col, cover, alpha, edge, a, over, op, aura)

    def _dots(self, col, sl):
        """Paper's dots, as her window has them (29 October 2026): black at 15% every 20 px, in step across the
        island's window whatever's open, under all that's drawn on the card."""
        gap, d = max(6, round(20 * self.k)), max(1, round(1.4 * self.k))
        ys = np.nonzero((np.arange(sl[0].start, sl[0].start + col.shape[0]) - gap // 2) % gap < d)[0]
        xs = np.nonzero((np.arange(sl[1].start, sl[1].start + col.shape[1]) - gap // 2) % gap < d)[0]
        if len(ys) and len(xs):
            col[np.ix_(ys, xs)] *= 0.85

    def _glass(self, col, cover, tall=None):
        """On the capsule, how opaque its glass is at each pixel, with col (its body's colour) made premultiplied by
        it, so what's drawn on it goes over both (face.Canvas); None on the pill, which is solid. tall: the patch's
        height, px. The small capsule is see-through glass; a panel or a card grows all but solid as it's taller
        (30 October 2026, the owner: the calendar had the wallpaper and the windows behind showing through its words,
        which looked cheap without a blur behind it)."""
        if self.style != "capsule":
            return None
        th = self.theme()
        h = (cover.shape[0] if tall is None else tall) / self.k
        t = max(0.0, min(1.0, (h - 64.0) / 50.0))  # the capsule's about 50 logical px with its shadow, a card 120+
        op = cover * (th["fill"] + (max(th["fill"], PANEL_FILL) - th["fill"]) * t)
        col *= op[..., None]
        return op

    def _paint_part(self, sl, cover, alpha, edge, body, box, draw, a):
        """Only box (x0, y0, x1, y1 in the patch) of a patch painted again: a caption's moving bars, over a
        kept picture of the rest."""
        h, w = cover.shape
        x0, y0 = max(0, int(math.floor(box[0]))), max(0, int(math.floor(box[1])))
        x1, y1 = min(w, int(math.ceil(box[2]))), min(h, int(math.ceil(box[3])))
        if x1 <= x0 or y1 <= y0:
            return
        col = np.empty((y1 - y0, x1 - x0, 3), np.float32)
        col[:] = body
        op = self._glass(col, cover[y0:y1, x0:x1], tall=h)  # as opaque as the whole patch was painted
        draw(face.Canvas(col, x0, y0, op), 1.0)
        out = self.buf[sl[0].start + y0:sl[0].start + y1, sl[1].start + x0:sl[1].start + x1]
        self._compose(out, col, cover[y0:y1, x0:x1], alpha[y0:y1, x0:x1],
                      edge[y0:y1, x0:x1] if edge is not None else None, a, None, op)

    def _compose(self, out, col, cover, alpha, edge, a, over, op=None, aura=None):
        """Colours (straight, 0 to 1) with their cover and alpha into out, the window's pixels: blue, green, red,
        alpha, premultiplied. Four channels at a time and no more passes than it needs. op: the glass's (_glass),
        with col premultiplied by it. aura: as _paint has it."""
        if op is not None:
            self._compose_glass(out, col, cover, alpha, edge, a, over, op, aura)
            return
        if edge is not None:
            col += (np.asarray(self.theme()["line"], np.float32) - col) * edge[..., None]
        np.clip(col, 0.0, 1.0, out=col)
        h, w = cover.shape
        src = np.empty((h, w, 4), np.float32)
        np.multiply(col[..., ::-1], (cover * (255.0 * a))[..., None], out=src[..., :3])
        sa = alpha * a if a < 1 else alpha
        if aura is not None:  # never into the kept shape's own alpha
            sa = self._glow(src, alpha - cover, sa if a < 1 else alpha.copy(), aura, a)
        np.multiply(sa, 255.0, out=src[..., 3])
        if over is not None and over[1] > over[0]:
            r0, r1 = over
            src[r0:r1] += out[r0:r1] * (1.0 - sa[r0:r1])[..., None]
        src += 0.5
        np.minimum(src, 255.0, out=src)
        out[...] = src

    def _compose_glass(self, out, col, cover, alpha, edge, a, over, op, aura=None):
        """_compose for the capsule's glass: col is premultiplied by op, how opaque each pixel is (the glass's fill
        where nothing's drawn, 1 under words and glyphs, and also below the glass where its progress line is). The
        hairline goes over it, the shadow (alpha less cover) under it, and what comes out stays premultiplied, as
        UpdateLayeredWindowIndirect needs: no colour brighter than its alpha. aura: as _paint has it."""
        th = self.theme()
        if edge is not None:
            e = edge * th["line_a"]
            col *= (1.0 - e)[..., None]
            col += np.asarray(th["line"], np.float32) * e[..., None]
            op *= 1.0 - e
            op += e
        np.clip(op, 0.0, 1.0, out=op)
        np.maximum(col, 0.0, out=col)
        np.minimum(col, op[..., None], out=col)  # a glow adds light, not cover: never more than the pixel holds
        h, w = cover.shape
        src = np.empty((h, w, 4), np.float32)
        np.multiply(col[..., ::-1], 255.0 * a, out=src[..., :3])
        shade = np.maximum(alpha - cover, 0.0) * (1.0 - op)  # the shadow shows only where the glass doesn't
        sa = op + shade
        if a < 1:
            sa *= a
        if aura is not None:
            sa = self._glow(src, shade, sa, aura, a)
        np.multiply(sa, 255.0, out=src[..., 3])
        if over is not None and over[1] > over[0]:
            r0, r1 = over
            src[r0:r1] += out[r0:r1] * (1.0 - sa[r0:r1])[..., None]
        src += 0.5
        np.minimum(src, 255.0, out=src)
        out[...] = src

    def _glow(self, src, shade, sa, aura, a):
        """The aura (colour, how strong 0 to 1, and the box inside the island where there's no shadow) over the shadow
        in src, the premultiplied pixels about to go out: the shadow lit in its colour, AURA times as strong as the
        shadow and never more than 0.65, so it glows under and round the island and never over it. shade: how much
        shadow each pixel has, 0 to 1; sa: their alpha, which it changes. Only the bands round that inner box are
        worked out: all of a card was 2 ms a frame more, its bands a quarter of that (30 October 2026)."""
        strength = aura[1] * AURA / max(0.05, self.theme()["shadow"])
        colour = np.asarray(aura[0][::-1], np.float32) * 255.0
        for rows, cols in _bands(shade.shape, aura[2] if len(aura) > 2 else None):
            g = np.minimum(np.maximum(shade[rows, cols], 0.0) * strength, 0.65)
            if g.size == 0:
                continue
            if a < 1:
                g *= a
            keep = 1.0 - g
            part = src[rows, cols]
            part[..., :3] *= keep[..., None]
            part[..., :3] += colour * g[..., None]
            sa[rows, cols] = g + sa[rows, cols] * keep
        return sa

    def _grow(self, sl):
        box = (sl[1].start, sl[0].start, sl[1].stop, sl[0].stop)
        self.drawn = _union(self.drawn, box)

    def _draw(self, now):
        """This frame into the window's picture. Only what the last frame covered is cleared, and only the box
        that holds both is given back for _push: the rest of the picture stays empty."""
        old, self.drawn = self.drawn, None
        if old is not None:
            self.buf[old[1]:old[3], old[0]:old[2]] = 0
        if self.alpha <= 0:
            return old
        k, m, th = self.k, self.m, self.theme()
        W, H = max(self.W.x, 10 * k), max(self.H.x, 10 * k)
        x0 = self._island_x(W) + self._jolt(now)  # shaking its head, if it is (_feel)
        y0 = m
        # the words under it first, so the island's shadow falls over them
        caps = [(lay.cap, a) for lay, a in ((self.prev, self.prev_alpha), (self.layout, self.content))
                if lay is not None and lay.cap is not None]
        CW, CH = self.CW.x, self.CH.x
        cap_rows = None
        if caps and self.cap_alpha > 0.01 and CW > 12 * k and CH > 8 * k:
            cx0 = self._island_x(CW)
            cy0 = y0 + H + self.GAP * k
            r = min(CH / 2, 18 * k)
            sl, cover, alpha, edge = self._shape(cx0, CW, CH, r, cy0)
            ox, oy = cx0 - sl[1].start, cy0 - sl[0].start
            ca = self.alpha * self.cap_alpha
            # while the bar stands still with the same words, its picture is kept and only its bars drawn again
            one = caps[0][0] if len(caps) == 1 and caps[0][1] >= 0.999 and ca >= 0.999 else None
            key = (one.key, sl[0].start, sl[0].stop, sl[1].start, sl[1].stop, round(CW * 2), round(CH * 2),
                   self._theme_name(), self.border, self.style) if one is not None else None
            if key is not None and key == self.cap_key:
                self.buf[sl] = self.cap_picture
            elif key is not None:
                self._paint(sl, cover, alpha, edge, th["cap"],
                            [(lambda cv, a: one.draw(cv, ox, oy, CW, CH, a, now), 1.0)], ca)
                self.cap_key, self.cap_picture = key, self.buf[sl].copy()
            else:
                def both(cv, a, c):
                    c.draw(cv, ox, oy, CW, CH, a, now)
                    if c.live:
                        c.live(cv, ox, oy, CW, CH, a, now)
                self._paint(sl, cover, alpha, edge, th["cap"],
                            [(lambda cv, a, c=c: both(cv, a, c), c_a) for c, c_a in caps], ca)
                self.cap_key = self.cap_picture = None
            if key is not None and one.live:
                self._paint_part(sl, cover, alpha, edge, th["cap"], one.live_box(ox, oy, CW, CH),
                                 lambda cv, a: one.live(cv, ox, oy, CW, CH, a, now), ca)
            self._grow(sl)
            cap_rows = (sl[0].start, sl[0].stop)
        lay = self.layout or self.prev
        if lay is not None and lay.radius:
            r = lay.radius
        elif self.drop:  # a notch's corners, not the capsule's round ends
            r = self.DROP_CORNER * k
        elif self.style == "capsule":  # fully round ends
            r = H / 2
        else:
            r = min(H / 2, self.corner * k)
        r = min(r, H / 2)
        sl, cover, alpha, edge = self._shape(x0, W, H, r, y0, self.drop)
        ox, oy = x0 - sl[1].start, y0 - sl[0].start
        self.patch_at = (sl[1].start, sl[0].start)  # where her face is drawn from, in the window (_face)
        # what opens comes up into place as it fades in, after Glance's cards (30 October 2026)
        rise = (1.0 - self.content) ** 2 * 5 * k if self._sweeping(now) else 0.0
        items = [(lambda cv, a, L=L, dy=dy: L.draw(cv, ox, oy + dy, W, H, a, now), la) for L, la, dy in
                 ((self.prev, self.prev_alpha, 0.0), (self.layout, self.content, rise)) if L is not None]
        sweep = self._sweep(now, ox, oy, W, H, r)
        if sweep is not None:
            items.append(sweep)
        over = None
        if cap_rows is not None:  # where its shadow falls on the bar
            over = (max(sl[0].start, cap_rows[0]) - sl[0].start, min(sl[0].stop, cap_rows[1]) - sl[0].start)
        aura = self._aura(now)
        if aura is not None:  # and where inside it no shadow is, which the glow can leave alone (_glow)
            inset = max(r, 2.0)
            aura += ((ox + inset, oy + 2.0, ox + W - inset, oy + H - 2.0),)
        self._paint(sl, cover, alpha, edge, th["body"], items, self.alpha, over, dots=True, aura=aura)
        self._grow(sl)
        self._shine(now, x0, W, H, r, y0, cap_rows)
        self.island_rect = (x0, y0, x0 + W, y0 + H)
        return _union(old, self.drawn)

    # ------------------------------------------------------------------ pointing and clicking
    def _hover_poll(self):
        self.hover_job = None
        if not self.visible_window:
            return
        now = time.time()
        if self.drag_note != self.drag_seen:  # files came over her, moved or went (_dragging): drawn as they are
            self.drag_seen = self.drag_note
            self.dirty = True
            self._wake()
        drag = self.drag_over
        if drag is not None and ((drag["left"] is not None and now - drag["left"] > 0.4) or now - self.drag_note > 2.0):
            self.drag_over = None  # gone off her a moment, or the drag ended without Windows saying so
            self.dirty = True
            self._wake()
        px, py = win.cursor_pos()
        x, y = px - self.origin.x, py - self.origin.y
        x0, y0, x1, y1 = getattr(self, "island_rect", (0, 0, 0, 0))
        near = x0 - 6 <= x <= x1 + 6 and y0 - 6 <= y <= y1 + 6
        lay = self.layout
        clickable = lay is not None and (lay.kind in CLICKABLE or (lay.kind in ("harry", "idle") and bool(lay.hot)))
        if (px, py) != self.rest_pos:  # moved: Approve waits for it to rest again (_steady)
            self.rest_pos, self.rest_at = (px, py), now
        if near or self.drag is not None:  # a slider held and dragged off it is still being held
            self.away_at = now
            if not self.hover and now - self.hover_at > 0.15:
                self.hover = True
                self.dirty = True
                self._wake()
        else:
            self.hover_at = now
            if self.hub_page is not None and now - self.away_at > HUB_LINGER:  # the pointer's gone: they close
                self._hub_close()
            if self.hover and now - self.away_at > 0.35:
                self.hover = False
                self.dirty = True
                self._wake()
        win.set_click_through(self.hwnd, not (self.hover and clickable))
        if lay is not None and lay.face and lay.kind != "harry":  # the capsule's eyes look at the pointer while it
            self._follow(x, y, now)  # moves, wherever it is; on her turn they do as it says (HARRY), as on the pill
        elif self.hover and lay is not None and lay.kind == "idle":  # her eyes follow the mouse
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            self.look_at = (max(-1.0, min(1.0, (x - cx) / max(1.0, (x1 - x0) / 2))),
                            max(-1.0, min(1.0, (y - cy) / max(1.0, (y1 - y0)))))
            self._wake()
        elif self.look_at is not None:
            self.look_at = None
            self._wake()
        if self.hover and lay is not None and lay.hot:
            hot = self._hot(x, y)
            try:
                self.top.configure(cursor="hand2" if hot else "arrow")
            except tk.TclError:
                pass
        self.hover_job = self.root.after(70, self._hover_poll)

    def _hot(self, x, y):
        lay = self.layout
        if lay is None:
            return None
        x0, y0 = self.island_rect[:2]
        for name, a, b, c, d in lay.hot:
            if x0 + a <= x <= x0 + c and y0 + b <= y <= y0 + d:
                return name
        return None

    def _click(self, right):
        px, py = win.cursor_pos()
        name = self._hot(px - self.origin.x, py - self.origin.y)
        lay = self.layout
        if lay is None:
            return
        if lay.kind == "notification" and self.popup is not None:
            if name == "open" and not right:
                self.runner.do("notifications", "open", self.popup.data)
            elif name == "reply" and not right:
                d = self.popup.data
                self.ask(f"Reply to {d.get('title')} on {d.get('app')}: ", under=False)
            self.popup.until = 0.0  # gone, opened or not
            self.hover = False
            self.dirty = True
            self._wake()
        elif lay.kind == "media" and name and not right:
            self.runner.do("media", name)
        elif lay.kind == "card":
            self._press(lay.press.get(name), right)
        elif lay.kind == "harry" and name and not right:  # the answer card's x and Try again
            self._panel_press(name)
        elif lay.kind == "idle" and name == "hub" and not right:  # a click on her eyes: the panels
            self._hub_open()
        elif lay.kind == "hub":
            self.shelf_drag = None
            if self.drag is not None:  # a slider let go: it's set where it was left
                self.drag = None
                return
            self._hub_press(name, right)
        elif lay.kind == "device" and self.popup is not None:
            if name == "open" and not right:
                self.runner.do("devices", "open", dict(self.popup.data))
            if name in ("open", "dismiss") or right:
                self.popup.until = 0.0
                self.hover = False
                self.dirty = True
                self._wake()

    def _press(self, what, right):
        """A click on a card: a right click, or one on the card itself, keeps it open or lets it go; a button is its
        plugin's command, run on the plugins' thread. A careful one (Approve) only once the pointer has rested on it
        and she isn't doing a task in an app (_steady)."""
        if right or what is None or what[1] == "pin":
            plugin = what[0] if what is not None else None
            self.pinned = None if right or self.pinned else plugin
            self.dirty = True
            self._wake()
            return
        plugin, name, data, careful = what
        if careful and not self._steady(time.time()):
            print(f"  island: {name} not pressed, the pointer hadn't rested on it (or she's busy in an app)")
            return
        self.runner.do(plugin, name, data)

    def _steady(self, now):
        """True if the pointer's rested on the island REST seconds, where it is now, and she isn't doing a task in an
        app: her clicks are real ones (winplatform.click moves the pointer there and clicks 80 ms later), so they
        never press Approve, and neither does one landing while hers runs."""
        agent = sys.modules.get("agent")
        if agent is not None and (agent.ACT.locked() or agent.RUNNING.is_set()):
            return False
        return win.cursor_pos() == self.rest_pos and now - self.rest_at >= REST


def _now():
    """The time as an opened card's top has it: 4:41."""
    return time.strftime("%I:%M").lstrip("0")


def _on_line(on, name):
    """The line under Wi-Fi's or Bluetooth's button: the network or the device it's on, "Not connected" while it's
    on with none, "Off", or "" while it isn't known yet."""
    if on is None:
        return ""
    if not on:
        return "Off"
    return name or "Not connected"


def _shortcut_glyph(cv, how, cx, cy, s, colour, body, a=1.0):
    """A shortcut's glyph (SHORTCUTS), s px across: the two sheets for a copy, else island_face's own."""
    draw = face.SHORTCUT_GLYPHS.get(how)
    if draw is None:
        _copy_glyph(cv, cx, cy, s, colour, body, a)
    else:
        draw(cv, cx, cy, s, colour, a)


def _dashed(cv, x0, y0, x1, y1, r, colour, a, k, shift=0.0):
    """A rounded box's outline from x0, y0 to x1, y1 in dashes, as Glance's drop zone has it, moved on by shift px
    (they go round while files are over it)."""
    lw, dash, gap = max(1.0, 1.4 * k), 7 * k, 5 * k
    period = dash + gap
    shift %= period  # a time in px is too big a number for the float32 places it's added to
    cx, cy, hw, hh = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2

    def line(xs, ys):
        return np.abs(face.rbox(xs, ys, cx, cy, hw, hh, r)) - lw / 2

    def dashes(along):
        u = np.mod(along + shift, period)
        return np.where(u < dash, np.maximum(-u, u - dash), np.minimum(u - dash, period - u))
    # worked out only along its edges, in strips, its round corners solid: over all of the box it was 80 ms a frame
    e = lw + 1
    for box, across in (((x0 + r, y0 - e, x1 - r, y0 + e), True), ((x0 + r, y1 - e, x1 - r, y1 + e), True),
                        ((x0 - e, y0 + r, x0 + e, y1 - r), False), ((x1 - e, y0 + r, x1 + e, y1 - r), False)):
        cv.shape(lambda xs, ys, across=across: np.maximum(line(xs, ys), dashes(xs if across else ys)), box, colour,
                 a)
    for bx, by in ((x0, y0), (x1 - r, y0), (x0, y1 - r), (x1 - r, y1 - r)):
        cv.shape(line, (bx - e, by - e, bx + r + e, by + r + e), colour, a)


def _file_size(path):
    """A shelf file's size as a drive's is said (_size), 184 KB or 2.4 MB; "Folder" for a folder; "" if it's gone."""
    try:
        if os.path.isdir(path):
            return "Folder"
        return _size(os.path.getsize(path))
    except OSError:
        return ""


def _day_name(day, i):
    """A forecast's day as Today's panel says it: Today, Tomorrow, then its weekday, as Sat."""
    import datetime as dt
    if i == 0:
        return "Today"
    if i == 1:
        return "Tomorrow"
    return (dt.date.today() + dt.timedelta(days=i)).strftime("%a")


def _ago(secs):
    """How long ago, as a notification list says it: now, 5 min, 2 h, 3 d."""
    secs = max(0, int(secs))
    if secs < 60:
        return "now"
    if secs < 3600:
        return f"{secs // 60} min"
    if secs < 86400:
        return f"{secs // 3600} h"
    return f"{secs // 86400} d"


def _copy_glyph(cv, cx, cy, s, colour, body, a=1.0):
    """Two sheets, one over the other, s px across: what's copied. body: the island's colour, which the front one's
    filled with, so the back one's corner goes behind it."""
    lw, h, rr = max(1.0, s * 0.11), s * 0.3, s * 0.12
    for front, (dx, dy) in ((False, (-0.13 * s, -0.13 * s)), (True, (0.13 * s, 0.13 * s))):
        bx, by = cx + dx, cy + dy
        box = (bx - h - lw - 1, by - h - lw - 1, bx + h + lw + 1, by + h + lw + 1)
        if front:
            cv.shape(lambda xs, ys, bx=bx, by=by: face.rbox(xs, ys, bx, by, h, h, rr), box, body, a)
        cv.shape(lambda xs, ys, bx=bx, by=by: np.abs(face.rbox(xs, ys, bx, by, h, h, rr)) - lw / 2, box, colour, a)


def _clock(secs):
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    return f"{h}:{rem // 60:02d}:{rem % 60:02d}" if h else f"{rem // 60}:{rem % 60:02d}"


def _live_clock(d, now):
    """How long a live activity has to go (its "until"), has left while it's paused ("left"), or has been going (its
    "since"), as 4:05; "" for none of them."""
    if d.get("until") is not None:
        return _clock(max(0, math.ceil(d["until"] - now)))
    if d.get("left") is not None:
        return _clock(max(0, math.ceil(d["left"])))
    if d.get("since") is not None:
        return _clock(max(0.0, now - d["since"]))
    return ""


def _timed(d):
    """True if a live activity has a clock to show (_live_clock)."""
    return any(d.get(k) is not None for k in ("until", "left", "since"))


def _live_done(d, now):
    """How far through it a live activity is, 0 to 1: its "progress", or how much of its "length" has gone by
    "until" or "left"; None when that isn't known."""
    if d.get("progress") is not None:
        return d["progress"]
    length = d.get("length")
    if not length:
        return None
    left = d["until"] - now if d.get("until") is not None else d.get("left")
    return None if left is None else max(0.0, min(1.0, 1 - left / length))


def _clock_w(font, d, now):
    """Room for a live activity's clock in font: 88:88's, or as wide as it is now if that's wider (an hour or more).
    A clock counting up is sent again each hour (island_plugins.Live), so its room grows as it does."""
    return max(font.measure("88:88"), font.measure(_live_clock(d, now)))


def _beat(left, urgent):
    """How bright a timer's figures are, left seconds before it goes off: in its last ones (urgent), brightest as
    each second comes up and dimmer between; else always all of it."""
    if not urgent:
        return 1.0
    return 0.55 + 0.45 * (0.5 + 0.5 * math.cos((left % 1.0) * math.tau))


def _focus():
    """Her focus timer's module (focus.py), or None if it can't be had."""
    try:
        import focus
        return focus
    except Exception:
        return None


def _size(n):
    """Bytes as a drive's size is said: 12.3 GB, 840 MB."""
    n = float(n or 0)
    for unit, step in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6)):
        if n >= step:
            v = n / step
            return f"{v:.1f} {unit}" if v < 100 else f"{v:.0f} {unit}"
    return f"{n / 1e3:.0f} KB"


def _bands(shape, inner):
    """The parts of a patch (h, w) round the box inner (x0, y0, x1, y1 in it): above, below, left and right of it, as
    (rows, columns) slices; all of it when there's no box in it."""
    h, w = shape
    whole = [(slice(0, h), slice(0, w))]
    if inner is None:
        return whole
    x0, y0 = max(0, int(math.ceil(inner[0]))), max(0, int(math.ceil(inner[1])))
    x1, y1 = min(w, int(inner[2])), min(h, int(inner[3]))
    if x1 <= x0 or y1 <= y0:
        return whole
    return [(slice(0, y0), slice(0, w)), (slice(y1, h), slice(0, w)), (slice(y0, y1), slice(0, x0)),
            (slice(y0, y1), slice(x1, w))]


def _accent(value):
    """A live activity's colour: one of ACCENTS by its name, an (r, g, b) as it is, violet for anything else."""
    if isinstance(value, (tuple, list)) and len(value) == 3:
        return tuple(float(c) for c in value)
    return ACCENTS.get(str(value or ""), VIOLET)


def _mix(a, b, t):
    """The colour t of the way from a to b."""
    return tuple((1 - t) * x + t * y for x, y in zip(a, b))


def _luma(colour):
    """How light a colour (r, g, b, 0 to 1) looks, 0 to 1: its relative luminance, as contrast is worked out."""
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in colour]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _resize(rgba, size):
    """A square picture made size px, each pixel the average of what it covers (island_art.resample): a cover's or
    an icon's edges stay smooth, where the nearest pixel made them jagged (30 October 2026)."""
    return art.resample(rgba, size)


def logo(h, open_=1.0, back=None, look=(0.0, 0.0)):
    """Her island as a picture (28 October 2026, the owner's ask): the glass capsule with her glowing eyes, as it floats
    at the top of the screen with nothing on, h px tall and as wide as it is there. The window's logo, and her icon.
    back: the colour behind it, (r, g, b) 0 to 1, for straight colours (h, w, 3); None for a picture with its own alpha
    (h, w, 4), premultiplied as island_art's are, its glass solid. open_: how open her eyes are, 0 to 1, for a blink;
    look: where they look, -1 to 1 across and down."""
    th, k = GLASS["dark"], h / DynamicIsland.COMPACT_H
    w = int(round((2 * 16 + 3.2 * DynamicIsland.SMALL_EYES) * k))  # her eyes in the round ends (_capsule, _eyes_w)
    xs = np.arange(w, dtype=np.float32) + 0.5
    ys = (np.arange(h, dtype=np.float32) + 0.5)[:, None]
    sd = face.rbox(xs, ys, w / 2, h / 2, w / 2 - 0.5, h / 2 - 0.5, h / 2)
    cover = np.clip(0.5 - sd, 0.0, 1.0)[..., None]
    lw = max(1.0, k)  # the hairline, about a pixel just inside its edge (_shape)
    edge = np.clip(0.5 - (np.abs(sd + 0.5 * lw) - 0.5 * lw), 0.0, 1.0)[..., None] * cover * th["line_a"]
    body = np.asarray(th["body"], np.float32)
    if back is not None:  # the glass, a little of what's behind it showing through
        body = body * th["fill"] + np.asarray(back, np.float32) * (1 - th["fill"])
    col = np.empty((h, w, 3), np.float32)
    col[:] = body
    col += (np.asarray(th["line"], np.float32) - col) * edge
    face.draw_eyes(face.Canvas(col), w / 2, h / 2, DynamicIsland.SMALL_EYES * k, "open", open_, look,
                   colour=th["eyes"], glow=th["glow"])
    np.clip(col, 0.0, 1.0, out=col)
    if back is None:
        return np.concatenate([col * cover, cover], axis=2).astype(np.float32)
    return (col * cover + np.asarray(back, np.float32) * (1 - cover)).astype(np.float32)
