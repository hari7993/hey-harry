"""Her edges of the screen (30 October 2026, the owner's ask, after bloom, github.com/SehajveerSingh2005/bloom): the
volume as a slider at the left edge and the brightness at the right, sliding in when the pointer rests against that
edge (edge_volume, edge_brightness), and, if Settings says so, when either changes (level_hud); the apps playing
sound beside the volume, each with its own slider, as bloom's mixer has them; and round corners at the top of the
screen, as a MacBook's (island_corners).

Each slider is a layered window drawn with numpy, as the island is: it never takes the focus, it's left out of her
screenshots, and it takes clicks only while the pointer's on it. Drag a slider, or scroll on it; click the speaker to
mute. Windows' own volume flyout still shows as it does: bloom hides it by making Explorer's flyout window see-through,
which could hide others of Explorer's (Snap layouts) as well, so Harry leaves it be.

The levels are read on a thread of their own (Levels), and only while they're wanted: while a slider's out, the
volume about every 150 ms (0.1 ms a look) and the brightness from the power scheme every half second (0.2 ms, where
WMI took 5 to 70 ms, measured 30 October 2026), and the apps; with level_hud on and none out, the volume every 200 ms
and the brightness every second; with it off, not at all. The pointer is looked at on Tk's thread every 80 ms near an
edge or while a slider's out, every 160 ms elsewhere. Idle, the two took under 1% of a core on 30 October 2026,
about what Tk's own loop does."""
import ctypes
import math
import os
import queue
import sys
import threading
import time
import tkinter as tk
import uuid
from ctypes import wintypes as wt

import numpy as np

import bubble
import identity
import island_face as face
import settings
import winplatform as win

EDGE_REST = 0.3  # seconds the pointer rests against an edge before its slider comes
SHOW_FOR = 1.6  # seconds a slider stays after a change it came for, when level_hud has it come for changes
LEAVE = 0.6  # seconds the pointer's away from a slider it came for before it goes
POLL, POLL_FAR = 0.08, 0.16  # seconds between looks at the pointer, on Tk's thread: near an edge, and away from both
NEAR = 120  # logical px from an edge that counts as near it
VOLUME_EVERY, BRIGHT_EVERY, APPS_EVERY = 0.15, 0.5, 1.5  # seconds between looks at the levels while a slider's out
VOLUME_IDLE, BRIGHT_IDLE = 0.2, 1.0  # and while none is, for level_hud
APPS_MOST = 4  # apps beside the volume, the ones playing first
HER_ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png")
STEP = 2  # percent a notch of the wheel moves a slider
MARGIN = 18  # logical px round a slider's panel for its shadow


# --------------------------------------------------------------------------- the levels, read and set off Tk's thread
_powrprof = None


class _GUID(ctypes.Structure):
    _fields_ = [("raw", ctypes.c_ubyte * 16)]


def _guid(text):
    g = _GUID()
    ctypes.memmove(g.raw, uuid.UUID(text).bytes_le, 16)
    return g


VIDEO = _guid("7516b95f-f776-4464-8c53-06167f40cc99")  # GUID_VIDEO_SUBGROUP
BRIGHTNESS = _guid("aded5e82-b909-4619-9949-f5d71dac0bcb")  # the screen's brightness in the power plan


def plan_brightness():
    """The built-in screen's brightness as the power plan keeps it, 0 to 100, on mains or battery as the PC is now:
    it follows a change, whatever made it. None if the plan can't be read."""
    global _powrprof
    try:
        if _powrprof is None:
            _powrprof = ctypes.WinDLL("powrprof")
        scheme = ctypes.c_void_p()
        if _powrprof.PowerGetActiveScheme(None, ctypes.byref(scheme)) != 0:
            return None
        try:
            value = wt.DWORD()
            on_mains = True
            try:
                import psutil
                b = psutil.sensors_battery()
                on_mains = b is None or bool(b.power_plugged)
            except Exception:
                pass
            read = _powrprof.PowerReadACValueIndex if on_mains else _powrprof.PowerReadDCValueIndex
            if read(None, scheme, ctypes.byref(VIDEO), ctypes.byref(BRIGHTNESS), ctypes.byref(value)) != 0:
                return None
            return max(0, min(100, int(value.value)))
        finally:
            ctypes.windll.kernel32.LocalFree(scheme)
    except Exception:
        return None


def _in_notch(what, level, muted):
    """A change of the volume or the brightness handed to the island to show (island_plugins.level_news, after
    Glance's notch, 30 October 2026): True if it shows it, else the edge's slider does."""
    try:
        import island_plugins
        return island_plugins.level_news(what, level, muted)
    except Exception as exc:
        print(f"  edges: not in the notch ({exc!r})")
        return False


class Levels:
    """The volume, the brightness and the apps playing sound, read on a thread of its own and handed to Tk's thread
    through take(); what Tk's thread wants set (do) is set here too, the slow brightness one at a time, the newest
    winning, so a drag never piles them up."""

    def __init__(self):
        self.events, self.jobs = queue.Queue(), queue.Queue()
        self.stopped, self.wake = threading.Event(), threading.Event()
        self.want_apps = False
        self.lively = False  # a slider's out, or the pointer's resting against an edge: the levels looked at often
        self.hud = False  # level_hud's on: the levels looked at now and then, for a change to show
        self.has_brightness = None  # None till it's known whether this screen's brightness can be set
        self.thread = threading.Thread(target=self._loop, name="harry-edges", daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.stopped.set()
        self.wake.set()

    def nudge(self):
        """A look at the levels now, not when the next one's due: a slider's coming out."""
        self.wake.set()

    def take(self):
        out = []
        try:
            while True:
                out.append(self.events.get_nowait())
        except queue.Empty:
            return out

    def do(self, what, value, data=None):
        self.jobs.put((what, value, data))
        self.wake.set()

    def _loop(self):
        win._com()
        ep = None
        ep_at = vol_at = bright_at = apps_at = 0.0
        last_vol = last_bright = None
        sessions = {}
        bright_want = None
        while not self.stopped.is_set():
            now = time.monotonic()
            lively, hud = self.lively, self.hud
            try:
                if ep is None or now - ep_at > 5.0:  # the speakers looked for again now and then: they change
                    ep, ep_at = win._endpoint(), now
                while True:
                    try:
                        what, value, data = self.jobs.get_nowait()
                    except queue.Empty:
                        break
                    if what == "volume":
                        ep.SetMasterVolumeLevelScalar(max(0, min(100, int(value))) / 100, None)
                        if int(value) > 0:
                            ep.SetMute(0, None)
                    elif what == "mute":
                        ep.SetMute(1 if value else 0, None)
                    elif what == "brightness":
                        bright_want = int(value)
                    elif what in ("app_volume", "app_mute") and data in sessions:
                        vol = sessions[data].SimpleAudioVolume
                        if what == "app_volume":
                            vol.SetMasterVolume(max(0, min(100, int(value))) / 100, None)
                        else:
                            vol.SetMute(1 if value else 0, None)
                        apps_at = 0.0
                if bright_want is not None:
                    want, bright_want = bright_want, None
                    try:
                        win.set_brightness(want)
                    except RuntimeError:
                        self.has_brightness = False
                    last_bright = want  # its own change isn't news
                looking = lively or hud
                if looking and now - vol_at >= (VOLUME_EVERY if lively else VOLUME_IDLE):
                    vol_at = now
                    level = (int(round(ep.GetMasterVolumeLevelScalar() * 100)), bool(ep.GetMute()))
                    if level != last_vol:
                        self.events.put(("volume", level[0], level[1], last_vol is not None))
                        last_vol = level
                if looking and now - bright_at >= (BRIGHT_EVERY if lively else BRIGHT_IDLE) and \
                        self.has_brightness is not False:
                    bright_at = now
                    if self.has_brightness is None:
                        self.has_brightness = win.brightness() is not None
                        self.events.put(("has_brightness", self.has_brightness))
                    level = plan_brightness() if self.has_brightness else None
                    if level is not None and level != last_bright:
                        self.events.put(("brightness", level, False, last_bright is not None))
                        last_bright = level
                if self.want_apps and now - apps_at >= APPS_EVERY:
                    apps_at = now
                    sessions, apps = self._apps()
                    self.events.put(("apps", apps))
            except Exception as exc:
                print(f"  edges: {exc!r}")
                ep = None
                self.stopped.wait(2.0)
                continue
            # asleep till the next look's due or a job comes (do, nudge): none at all while nothing wants one
            due = []
            if lively or hud:
                due.append(vol_at + (VOLUME_EVERY if lively else VOLUME_IDLE))
                if self.has_brightness is not False:
                    due.append(bright_at + (BRIGHT_EVERY if lively else BRIGHT_IDLE))
            if self.want_apps:
                due.append(apps_at + APPS_EVERY)
            self.wake.wait(max(0.01, min(due) - time.monotonic()) if due else None)
            self.wake.clear()

    @staticmethod
    def _apps():
        """The apps in the volume mixer, the ones playing sound first: ({key: session}, [{"key", "name", "exe",
        "volume", "muted", "playing", "icon"}]), APPS_MOST at most; never Windows' own sounds."""
        from pycaw.pycaw import AudioUtilities
        import island_art as art
        found = []
        for s in AudioUtilities.GetAllSessions():
            proc = s.Process
            if proc is None:
                continue
            try:
                exe = proc.exe()
            except Exception:
                exe = ""
            her = proc.pid == os.getpid()  # her own voice: "Python" in Windows' mixer (30 October 2026), her name here
            name = identity.name() if her else win.file_description(exe) if exe else ""
            name = name or os.path.splitext(proc.name())[0].capitalize()
            vol = s.SimpleAudioVolume
            found.append((s.State == 1, {"key": f"{proc.pid}:{exe.lower()}", "name": name, "exe": exe, "her": her,
                                         "volume": int(round(vol.GetMasterVolume() * 100)),
                                         "muted": bool(vol.GetMute()), "playing": s.State == 1}, s))
        found.sort(key=lambda f: not f[0])
        seen, apps, sessions = set(), [], {}
        for _, app, s in found:
            if app["exe"].lower() in seen and app["exe"] and not app["her"]:
                continue  # one row an app, as the mixer shows Chrome's tabs as one
            seen.add(app["exe"].lower())
            if app["her"]:
                app["icon"] = art.file_icon(HER_ICON, 40)
            else:
                app["icon"] = art.exe_icon(app["exe"], 40) if app["exe"] else None
            apps.append(app)
            sessions[app["key"]] = s
            if len(apps) == APPS_MOST:
                break
        return sessions, apps


# --------------------------------------------------------------------------- a slider's picture
def glass():
    """The island's glass, as its theme has it (island.GLASS), so the sliders look like her."""
    import island
    name = settings.get("island_theme") or "paper"
    if name == "system":
        try:
            name = "dark" if win.dark_mode() else "light"
        except Exception:
            name = "dark"
    th = island.GLASS["light" if name == "light" else "paper" if name == "paper" else "dark"]
    # solid (30 October 2026): see-through, the words of the windows behind showed in the panel round its bars, the
    # owner's screenshot
    return dict(th, fill=1.0)


def layout(kind, apps, k):
    """Where a slider's parts go, in px of its window: {"w", "h", "panel" (x0, y0, x1, y1), "bars" [(key, x0, y0,
    x1, y1)], "glyph" (x0, y0, x1, y1)}. kind: "volume" (the master's bar, then one an app) or "brightness"."""
    m, pad = MARGIN * k, 14 * k
    bar_w, app_w, gap, bar_h = 30 * k, 24 * k, 14 * k, 168 * k
    top, foot = 24 * k, (34 * k if kind == "volume" and apps else 12 * k)
    n = len(apps) if kind == "volume" else 0
    pw = 2 * pad + bar_w + n * (gap + app_w)
    ph = pad + top + bar_h + foot + pad
    x0, y0 = m, m
    bars = [("master", x0 + pad, y0 + pad + top, x0 + pad + bar_w, y0 + pad + top + bar_h)]
    x = x0 + pad + bar_w + gap
    for app in apps[:n]:
        bars.append((app["key"], x, y0 + pad + top, x + app_w, y0 + pad + top + bar_h))
        x += app_w + gap
    b = bars[0]
    glyph = (b[1], b[4] - bar_w, b[3], b[4])
    return {"w": int(math.ceil(pw + 2 * m)), "h": int(math.ceil(ph + 2 * m)), "panel": (x0, y0, x0 + pw, y0 + ph),
            "bars": bars, "glyph": glyph}


_bases = {}


def _bytes(col, alpha):
    """Premultiplied colours (h, w, 3) and their alpha (h, w), 0 to 1, as a window's blue, green, red, alpha bytes."""
    out = np.empty(alpha.shape + (4,), np.float32)
    out[..., :3] = col[..., ::-1] * 255.0
    out[..., 3] = alpha * 255.0
    return (np.minimum(out + 0.5, 255.0)).astype(np.uint8)


def _base(kind, n, k, th):
    """A slider's window with no bars on it, as render's bytes: its glass panel, its shadow and its hairline. Kept,
    as it's most of the drawing and a level never changes it (30 October 2026: 9 of a slider's 18 ms). n: the apps
    beside the volume."""
    key = (kind, n, round(k, 4), repr(sorted(th.items())))
    hit = _bases.get(key)
    if hit is not None:
        return hit
    lay = layout(kind, [{"key": str(i)} for i in range(n)], k)
    w, h = lay["w"], lay["h"]
    x0, y0, x1, y1 = lay["panel"]
    xs = np.arange(w, dtype=np.float32) + 0.5
    ys = (np.arange(h, dtype=np.float32) + 0.5)[:, None]
    r = 22 * k
    cx, cy, hw, hh = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    sd = face.rbox(xs, ys, cx, cy, hw, hh, r)
    cover = np.clip(0.5 - sd, 0.0, 1.0)
    far = face.rbox(xs, ys - 3 * k, cx, cy, hw, hh, r)
    shadow = th["shadow"] * np.clip(0.5 - far / (11 * k), 0.0, 1.0) ** 2
    lw = max(1.0, k)
    e = np.clip(0.5 - (np.abs(sd + 0.5 * lw) - 0.5 * lw), 0.0, 1.0) * cover * th["line_a"]
    op = cover * th["fill"]
    col = np.empty((h, w, 3), np.float32)
    col[:] = th["body"]
    col *= op[..., None]
    # the hairline, then out as the window's pixels, premultiplied
    col *= (1.0 - e)[..., None]
    col += np.asarray(th["line"], np.float32) * e[..., None]
    op = op * (1.0 - e) + e
    np.clip(op, 0.0, 1.0, out=op)
    np.minimum(np.maximum(col, 0.0), op[..., None], out=col)
    out = _bytes(col, op + np.maximum(shadow - cover, 0.0) * (1.0 - op))
    if len(_bases) > 16:
        _bases.clear()
    _bases[key] = out
    return out


def render(kind, level, muted, apps, k, th, text):
    """A slider's window as premultiplied blue, green, red, alpha bytes (h, w, 4): its glass panel with its shadow,
    the master's bar filled to level with its glyph and its percentage, and an app's beside it with its icon. text(px,
    weight) gives a bubble.Text. The panel's kept (_base); each bar's drawn in a box of its own on the panel's plain
    glass, where no edge or shadow reaches, so a change of level costs only its bars."""
    lay = layout(kind, apps, k)
    out = _base(kind, len(lay["bars"]) - 1, k, th).copy()
    small = text(round(11.5 * k), 600)
    looks = repr(sorted(th.items()))
    for i, bar in enumerate(lay["bars"]):
        if i == 0:
            frac = 0.0 if muted or level is None else max(0.0, min(1.0, level / 100))
            words = ("Muted" if muted else f"{int(level)}%") if level is not None else "\u2026"
            icon, dim, filled = None, False, level is not None
        else:
            app = apps[i - 1]
            frac = 0.0 if app["muted"] else app["volume"] / 100
            words, icon, dim, filled = f"{app['volume']}", app.get("icon"), app["muted"], True
        # each column kept as it was last drawn: while one's dragged, the others aren't drawn again
        key = (kind, i, bar[1:], round(frac, 4), muted if i == 0 else dim, words, filled,
               None if icon is None else (app.get("exe"), app.get("her")), round(k, 4), looks)
        hit = _columns.get(key)
        if hit is None:
            hit = _column(kind, i, bar[1:], frac, muted, words, icon, dim, filled, k, th, small)
            if len(_columns) > 48:
                _columns.clear()
            _columns[key] = hit
        rx0, ry0, pic = hit
        out[ry0:ry0 + pic.shape[0], rx0:rx0 + pic.shape[1]] = pic
    return out


_columns = {}


def _column(kind, i, bar, frac, muted, words, icon, dim, filled, k, th, small):
    """One bar's column, drawn in a box of its own on the panel's plain glass: (x, y of its box, its bytes). i: 0
    for the master's bar, with its glyph in it, else an app's, with its icon under it."""
    bx0, by0, bx1, by1 = bar
    rx0, ry0 = int(math.floor(bx0 - 6 * k)), int(math.floor(by0 - small.line - 6 * k))
    rx1, ry1 = int(math.ceil(bx1 + 6 * k)), int(math.ceil(by1 + (32 if i else 2) * k))
    op = np.full((ry1 - ry0, rx1 - rx0), th["fill"], np.float32)
    col = np.empty(op.shape + (3,), np.float32)
    col[:] = th["body"]
    col *= op[..., None]
    cv = face.Canvas(col, ox=rx0, oy=ry0, op=op)
    bw, bh = bx1 - bx0, by1 - by0
    mx = (bx0 + bx1) / 2
    # in the colours the island's Controls fill them (30 October 2026, the owner: "more colour"): the volume blue,
    # the brightness amber, an app's a lighter blue; grey while it's muted
    import island
    fill = th["muted"] if (muted if i == 0 else dim) else \
        island.SLIDER_TINTS.get(kind, island.BLUE) if i == 0 else island.CYAN
    # the level as a slim bar over its track, its top where a press would set it, and under it the glyph, lit with it
    # (30 October 2026: a thin line with a wash and a ring round its head was "really dumb", the owner). On a dark
    # panel it's Glance's light, a tube of its colour with a bright core and a glow kept inside its column; on a light
    # one the colour itself, solid, as light on white doesn't show
    dark = th["body"][0] < 0.5
    tw = bw * 0.38
    top, foot = by0 + tw / 2, (by1 - bw if i == 0 else by1 - tw / 2)  # the middles of its round ends
    track = tuple(b + (t - b) * (0.16 if dark else 0.09) for b, t in zip(th["body"], th["text"]))
    box = (rx0, ry0, rx1, ry1)
    cv.shape(lambda X, Y: face.segment(X, Y, mx, top, mx, foot, tw), box, track, 1.0)
    lit = filled and frac > 0
    head = by1 - bh * frac  # its top edge
    if lit and head + tw / 2 < foot:
        end = max(top, head + tw / 2)
        cv.shape(lambda X, Y: face.segment(X, Y, mx, end, mx, foot, tw), box, fill, 1.0,
                 glow=0.5 if dark else 0.0, spread=2.2 * k, halo=fill)
        if dark:
            core = tuple(c + (1.0 - c) * 0.62 for c in fill)
            cv.shape(lambda X, Y: face.segment(X, Y, mx, end, mx, foot, tw * 0.36), box, core, 1.0)
    if i == 0:
        gy = by1 - bw / 2
        ink = fill if lit else th["muted"]
        if kind == "volume":
            face.speaker_glyph(cv, mx + 1 * k, gy, 19 * k, ink, 1.0, frac, muted)
        else:
            face.sun_glyph(cv, mx, gy, 18 * k, ink, 1.0, frac)
    elif icon is not None:
        s = int(round(22 * k))
        if icon.shape[0] != s:
            import island
            icon = island._resize(icon, s)
        cv.image(icon, mx - icon.shape[1] / 2, by1 + 8 * k, 0.55 if dim else 1.0)
    cover = small.render(words)
    cv.text(cover, mx - cover.shape[1] / 2, by0 - small.line - 4 * k, th["text"] if lit else th["muted"], 1.0)
    np.clip(op, 0.0, 1.0, out=op)
    np.minimum(np.maximum(col, 0.0), op[..., None], out=col)
    return rx0, ry0, _bytes(col, op)


# --------------------------------------------------------------------------- a slider's window
def prime(hwnd):
    """A first, empty picture for a layered window before it's ever hidden: for one hidden before its first, Windows
    turned down every picture after (ERROR_INVALID_PARAMETER, found 30 October 2026). The island has its first at
    once too."""
    dc = bubble._new_dc(None)
    bitmap, buf = bubble._dib(dc, 1, 1)
    old = bubble._select(dc, bitmap)
    buf[:] = 0
    try:
        bubble._ULW(hwnd, None, ctypes.byref(wt.POINT(-20000, -20000)), ctypes.byref(wt.SIZE(1, 1)), dc,
                    ctypes.byref(wt.POINT(0, 0)), 0, ctypes.byref(bubble._BLEND(0, 0, 255, 1)), 2)
    finally:
        bubble._select(dc, old)
        bubble._delete(bitmap)
        bubble._delete_dc(dc)


class Slider:
    """One edge's slider: its window, its picture and where it's slid to. side: "left" (the volume) or "right" (the
    brightness)."""

    def __init__(self, root, side, k):
        self.root, self.side, self.k = root, side, k
        self.kind = "volume" if side == "left" else "brightness"
        self.level, self.muted, self.apps = None, False, []
        self.out = bubble.Spring(0.0, 0.32, 0.86)  # 0 in, 1 out
        self.fade = 0.0
        self.shown = False
        self.why = None  # "edge" (the pointer came for it) or "change" (a level changed)
        self.until = 0.0  # when one that came for a change goes
        self.away = 0.0  # since when the pointer's been away from one it came for
        self.hwnd = self.top = None
        self.pic = self.pic_key = None
        self.texts = {}
        self.drag = None  # the bar held: its key
        self.area = None  # the work area of the screen it's out on
        self.x = self.y = 0
        self.drawn = 0.0  # when its picture was last drawn

    def text(self, px, weight):
        key = (px, weight)
        if key not in self.texts:
            self.texts[key] = bubble.Text(px, weight)
        return self.texts[key]

    def build(self):
        self.top = tk.Toplevel(self.root)
        self.top.withdraw()
        self.top.overrideredirect(True)
        self.top.geometry("10x10+-20000+-20000")
        self.top.deiconify()
        self.top.update_idletasks()
        self.hwnd = win.root_hwnd(self.top.winfo_id())
        win.make_overlay(self.hwnd)
        win.NO_CAPTURE.append(self.hwnd)
        prime(self.hwnd)
        win.hide_window(self.hwnd)
        self.dc = bubble._new_dc(None)
        self.bitmap = self.old = None
        self.size = (0, 0)
        for seq, fn in (("<ButtonPress-1>", self._press), ("<B1-Motion>", self._move),
                        ("<ButtonRelease-1>", self._release), ("<ButtonRelease-3>", self._right)):
            self.top.bind(seq, lambda e, fn=fn: fn())
        self.top.bind("<MouseWheel>", lambda e: self._wheel(e.delta))

    def close(self):
        if self.top is None:
            return
        win.hide_window(self.hwnd)
        if self.hwnd in win.NO_CAPTURE:
            win.NO_CAPTURE.remove(self.hwnd)
        if self.bitmap is not None:
            bubble._select(self.dc, self.old)
            bubble._delete(self.bitmap)
        bubble._delete_dc(self.dc)
        for t in self.texts.values():
            t.close()
        self.texts = {}
        self.top.destroy()
        self.top = None

    # ---------------------------------------------------------------- where it is
    def place(self, area):
        """(x, y) of its window's top left, slid all the way out, on the screen whose work area is area."""
        left, top, right, bottom = area
        lay = layout(self.kind, self.apps, self.k)
        y = int(round((top + bottom) / 2 - lay["h"] / 2))
        inset = 8 * self.k - MARGIN * self.k
        if self.side == "left":
            return int(round(left + inset)), y
        return int(round(right - inset - lay["w"])), y

    def panel_on_screen(self):
        """Its panel's box on the screen, (x0, y0, x1, y1), where it is now."""
        if not self.shown:
            return None
        lay = layout(self.kind, self.apps, self.k)
        x0, y0, x1, y1 = lay["panel"]
        return self.x + x0, self.y + y0, self.x + x1, self.y + y1

    def draw(self, area):
        """Its picture again if what's on it changed, and where it's slid to: one UpdateLayeredWindow, its fade as
        the window's own alpha, so a frame of the slide costs no drawing."""
        key = (self.level, self.muted, tuple((a["key"], a["volume"], a["muted"]) for a in self.apps), self.k,
               settings.get("island_theme"))
        now = time.monotonic()
        # drawn again as it changes, but while it's dragged at most every 30 ms: a frame's 5 to 9 ms of Tk's time
        if key != self.pic_key and (self.drag is None or now - self.drawn >= 0.03 or self.pic is None):
            self.pic = render(self.kind, self.level, self.muted, self.apps, self.k, glass(), self.text)
            self.pic_key, self.drawn = key, now
            h, w = self.pic.shape[:2]
            if (w, h) != self.size:
                if self.bitmap is not None:
                    bubble._select(self.dc, self.old)
                    bubble._delete(self.bitmap)
                self.bitmap, self.buf = bubble._dib(self.dc, w, h)
                self.old = bubble._select(self.dc, self.bitmap)
                self.size = (w, h)
            self.buf[...] = self.pic
            bubble._flush()
        x, y = self.place(area)
        w, h = self.size
        travel = w * 0.9
        slid = (1.0 - min(1.0, max(0.0, self.out.x))) * travel
        self.x = int(round(x - slid if self.side == "left" else x + slid))
        self.y = y
        alpha = max(0, min(255, int(round(255 * self.fade))))
        if alpha <= 0:
            if self.shown:
                win.hide_window(self.hwnd)
                self.shown = False
            return
        if not self.shown:
            win.show_no_activate(self.hwnd, self.x, self.y, w, h)
            self.shown = True
        origin, size, src = wt.POINT(self.x, self.y), wt.SIZE(w, h), wt.POINT(0, 0)
        blend = bubble._BLEND(0, 0, alpha, 1)
        bubble._ULW(self.hwnd, None, ctypes.byref(origin), ctypes.byref(size), self.dc, ctypes.byref(src), 0,
                    ctypes.byref(blend), 2)

    # ---------------------------------------------------------------- clicks, drags and the wheel
    host = None  # Edges, set by it: where presses go

    def _hit(self):
        """(what's under the pointer: "glyph", a bar's key, or None, the pointer's y on the screen)."""
        px, py = win.cursor_pos()
        lay = layout(self.kind, self.apps, self.k)
        x, y = px - self.x, py - self.y
        g = lay["glyph"]
        if self.kind == "volume" and g[0] <= x <= g[2] and g[1] <= y <= g[3]:
            return "glyph", py
        for key, x0, y0, x1, y1 in lay["bars"]:
            if x0 - 6 * self.k <= x <= x1 + 6 * self.k and y0 - 8 * self.k <= y <= y1 + 8 * self.k:
                return key, py
        return None, py

    def _press(self):
        what, py = self._hit()
        if what in (None, "glyph") or self.host is None or self.host.busy():
            return
        self.drag = what
        self._drag_to(py)

    def _move(self):
        if self.drag is not None:
            self._drag_to(win.cursor_pos()[1])

    def _release(self):
        if self.drag is not None:
            self.drag = None
            return
        what, _ = self._hit()
        if what == "glyph" and self.host is not None and not self.host.busy():
            self.host.set(self, "master", None, mute=not self.muted)

    def _right(self):
        """A right-click: its page in Windows' Settings, Sound or Display."""
        if self.host is not None and not self.host.busy():
            win.open_windows_page("ms-settings:sound" if self.kind == "volume" else "ms-settings:display")

    def _drag_to(self, py):
        lay = layout(self.kind, self.apps, self.k)
        bar = next((b for b in lay["bars"] if b[0] == self.drag), None)
        if bar is None:
            return
        level = int(round(max(0.0, min(1.0, (bar[4] - (py - self.y)) / max(1.0, bar[4] - bar[2]))) * 100))
        self.host.set(self, self.drag, level)

    def _wheel(self, delta):
        if self.host is None or self.host.busy():
            return
        notches = int(delta / 120) or (1 if delta > 0 else -1)
        what, _ = self._hit()
        what = "master" if what in (None, "glyph") else what
        if what == "master":
            now = self.level or 0
        else:
            now = next((a["volume"] for a in self.apps if a["key"] == what), 0)
        self.host.set(self, what, max(0, min(100, now + STEP * notches)))


# --------------------------------------------------------------------------- round corners at the top of the screen
class Corners:
    """Two small windows at the top corners of each screen, black where a round corner cuts the screen's square one
    off (island_corners), as a MacBook's screen has them. Drawn once, clicks go through, and placed again when the
    screens change."""
    R = 10  # logical px

    def __init__(self, root, k):
        self.root, self.k, self.windows, self.placed = root, k, [], None

    def sync(self):
        """There on each screen while island_corners is on, gone while it's off."""
        want = bool(settings.get("island_corners"))
        screens = tuple(m for m in _monitors()) if want else ()
        if screens == self.placed:
            return
        self.close()
        self.placed = screens
        r = max(4, int(round(self.R * self.k)))
        for left, top, right, _ in screens:
            for side in ("left", "right"):
                self.windows.append(self._corner(left if side == "left" else right - r, top, r, side))

    def _corner(self, x, y, r, side):
        top = tk.Toplevel(self.root)
        top.withdraw()
        top.overrideredirect(True)
        top.geometry(f"{r}x{r}+{x}+{y}")
        top.deiconify()
        top.update_idletasks()
        hwnd = win.root_hwnd(top.winfo_id())
        win.make_overlay(hwnd)
        dc = bubble._new_dc(None)
        bitmap, buf = bubble._dib(dc, r, r)
        old = bubble._select(dc, bitmap)
        xs = np.arange(r, dtype=np.float32) + 0.5
        ys = (np.arange(r, dtype=np.float32) + 0.5)[:, None]
        cx = r if side == "left" else 0.0  # the round corner's middle, inside the screen
        inside = np.clip(r - np.hypot(xs - cx, ys - r) + 0.5, 0.0, 1.0)  # 1 inside the round corner
        black = ((1.0 - inside) * 255 + 0.5).astype(np.uint8)
        buf[..., :3] = 0
        buf[..., 3] = black
        bubble._flush()
        origin, size, src = wt.POINT(x, y), wt.SIZE(r, r), wt.POINT(0, 0)
        win.show_no_activate(hwnd, x, y, r, r)
        bubble._ULW(hwnd, None, ctypes.byref(origin), ctypes.byref(size), dc, ctypes.byref(src), 0,
                    ctypes.byref(bubble._BLEND(0, 0, 255, 1)), 2)
        return top, hwnd, dc, bitmap, old

    def close(self):
        for top, hwnd, dc, bitmap, old in self.windows:
            win.hide_window(hwnd)
            bubble._select(dc, old)
            bubble._delete(bitmap)
            bubble._delete_dc(dc)
            top.destroy()
        self.windows, self.placed = [], None


_user32 = ctypes.WinDLL("user32")  # its own, so these signatures don't change winplatform's
_user32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
_user32.MonitorFromPoint.restype = wt.HANDLE
_user32.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.POINTER(win.MONITORINFO)]


def _area_at(x, y):
    """(left, top, right, bottom) of the work area of the screen the point's on, in real pixels: a slider comes out
    on the screen the pointer's on, not the one the window in front is on."""
    info = win.MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    monitor = _user32.MonitorFromPoint(wt.POINT(int(x), int(y)), 2)  # MONITOR_DEFAULTTONEAREST
    if not monitor or not _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return win.work_area()
    r = info.rcWork
    return r.left, r.top, r.right, r.bottom


def _monitors():
    """Each screen's box, (left, top, right, bottom) in real pixels."""
    out = []
    proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)

    def seen(_hmon, _hdc, rect, _data):
        r = rect.contents
        out.append((r.left, r.top, r.right, r.bottom))
        return True
    try:
        ctypes.windll.user32.EnumDisplayMonitors(None, None, proc(seen), 0)
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------- the two, kept
class Edges:
    """The volume's slider at the left edge, the brightness's at the right, and the corners: started by her window
    (assistant_ui), looked after on Tk's thread with the levels read on their own (Levels). reload() after a setting
    changed; close() when she quits."""

    def __init__(self, root):
        self.root = root
        self.k = root.winfo_fpixels("1i") / 96
        self.levels = Levels().start()
        self.sliders = {"left": Slider(root, "left", self.k), "right": Slider(root, "right", self.k)}
        for s in self.sliders.values():
            s.host = self
            s.build()
        self.corners = Corners(root, self.k)
        self.rest = {"left": None, "right": None}  # since when the pointer's been against each edge
        self.full, self.full_at = False, 0.0
        self.closed = False
        self.job = None
        self.last = time.monotonic()
        self.corners.sync()
        self._poll()
        self.root.after(2500, self._warm)

    def _warm(self):
        """Each slider's panel drawn once while nothing's happening (30 to 80 ms), so the first to come out comes
        smoothly."""
        if self.closed:
            return
        try:
            for s in self.sliders.values():
                render(s.kind, s.level, s.muted, [], self.k, glass(), s.text)
        except Exception as exc:
            print(f"  edges: {exc!r}")

    def reload(self):
        self.corners.sync()

    def close(self):
        self.closed = True
        if self.job is not None:
            self.root.after_cancel(self.job)
        self.levels.stop()
        for s in self.sliders.values():
            s.close()
        self.corners.close()

    @staticmethod
    def busy():
        """True while she's doing a task in an app: her clicks are real ones, so none may move a slider."""
        agent = sys.modules.get("agent")
        return agent is not None and (agent.ACT.locked() or agent.RUNNING.is_set())

    def set(self, slider, what, level, mute=None):
        """A slider moved by you (or its speaker clicked, mute): shown at once, and set on Levels' thread."""
        if what == "master":
            if mute is not None:
                slider.muted = bool(mute)
                self.levels.do("mute", slider.muted)
            else:
                slider.level = level
                if level > 0:  # turned up, it's heard again, as Levels unmutes it
                    slider.muted = False
                self.levels.do(slider.kind, level)
        else:
            for app in slider.apps:
                if app["key"] == what:
                    app["volume"] = level
                    app["muted"] = False
            self.levels.do("app_volume", level, what)
        slider.away = time.monotonic()
        self._kick(slider)

    def _kick(self, slider):
        slider.why = slider.why or "edge"
        self.levels.want_apps = self.sliders["left"].why == "edge"

    def _poll(self):
        self.job = None
        if self.closed:
            return
        now = time.monotonic()
        dt = min(0.05, now - self.last)
        self.last = now
        hud = bool(settings.get("level_hud"))
        notch = bool(settings.get("level_notch"))  # a change shown in the island instead (island_plugins.Levels)
        for event in self.levels.take():
            if event[0] == "has_brightness":
                continue
            if event[0] == "apps":
                self.sliders["left"].apps = event[1]
                continue
            kind, level, muted, news = event
            s = self.sliders["left" if kind == "volume" else "right"]
            if s.drag is None:
                s.level, s.muted = level, muted
            if news and notch and not self.full and s.why != "edge" and s.drag is None and _in_notch(kind, level,
                                                                                                 muted):
                pass
            elif news and hud and not self.full and s.why != "edge":
                s.why, s.until = "change", now + SHOW_FOR
            elif s.why == "change":
                s.until = now + SHOW_FOR
        if now - self.full_at > 2.0:
            self.full_at = now
            state = ctypes.c_int()
            try:
                ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state))
                self.full = state.value in (2, 3, 4, 7)  # a game, presenting, a full-screen app
            except Exception:
                self.full = False
            self.corners.sync()
        px, py = win.cursor_pos()
        area = _area_at(px, py)
        vx = ctypes.windll.user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
        vw = ctypes.windll.user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
        top, bottom = area[1], area[3]
        middle = top + (bottom - top) * 0.15 <= py <= bottom - (bottom - top) * 0.15
        moving = False
        had_apps = self.levels.want_apps
        for side, s in self.sliders.items():
            on = bool(settings.get("edge_volume" if side == "left" else "edge_brightness"))
            if side == "right" and self.levels.has_brightness is False:
                on = False
            against = on and middle and not self.full and (px <= vx if side == "left" else px >= vx + vw - 1)
            if against:
                self.rest[side] = self.rest[side] or now
                if now - self.rest[side] >= EDGE_REST and s.why != "edge":
                    s.why = "edge"
                    if side == "left":
                        self.levels.want_apps = True
            else:
                self.rest[side] = None
            box = s.panel_on_screen()
            over = box is not None and box[0] - 8 <= px <= box[2] + 8 and box[1] - 8 <= py <= box[3] + 8
            if s.why == "edge":
                if over or against or s.drag is not None:
                    s.away = now
                elif now - s.away > LEAVE:
                    s.why = None
            elif s.why == "change" and now >= s.until and not over:
                s.why = None
            want = 1.0 if s.why else 0.0
            s.out.go(want)
            s.out.step(dt)
            s.fade = min(1.0, s.fade + dt / 0.12) if want else max(0.0, s.fade - dt / 0.2)
            if s.why or s.shown:
                if s.why is None and s.fade <= 0:
                    s.drag = None
                if not s.shown or s.area is None:  # out on the screen the pointer was on as it came
                    s.area = area
                s.draw(s.area)
                if s.shown:
                    win.set_click_through(s.hwnd, not over)
            moving = moving or not s.out.resting(0.002) or 0 < s.fade < 1 or s.drag is not None
            if side == "left" and s.why != "edge":
                self.levels.want_apps = False
        # the levels looked at often while a slider's out or coming, now and then for level_hud, else not at all
        lively = any(s.why for s in self.sliders.values()) or any(self.rest.values())
        hud = hud or notch  # the levels looked at now and then for either
        wake = (lively and not self.levels.lively) or (hud and not self.levels.hud) or \
            (self.levels.want_apps and not had_apps)
        self.levels.lively, self.levels.hud = lively, hud
        if wake:
            self.levels.nudge()
        near = px <= vx + NEAR * self.k or px >= vx + vw - 1 - NEAR * self.k
        out = lively or any(s.shown for s in self.sliders.values())
        self.job = self.root.after(16 if moving else int((POLL if near or out else POLL_FAR) * 1000), self._poll)
