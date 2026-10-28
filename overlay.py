"""Harry drawing on your screen (28 October 2026, after Atticus): a ring round where to click, numbered steps with a
line from one to the next, a box round a part of the window, a line under what to read and a short caption, each
drawn on like a pen on a whiteboard. It sits over every window and is never in the way: clicks go through it, it
never takes the focus, it's not in the taskbar or Alt+Tab, and it's left out of her own screenshots
(winplatform.NO_CAPTURE), so the model never sees her own rings.

One thread of its own (UI) runs a Win32 message loop for every window drawn this way, here and in cards.py, so
nothing waits on Tk's main loop or holds up her voice. Positions are real pixels: the thread is per-monitor DPI
aware, as winplatform._real_pixels is, so what UI Automation and a screenshot give lines up with what's drawn."""
import ctypes
import math
import queue
import threading
import time
from ctypes import wintypes as wt

import numpy as np

import winplatform as win

_u = ctypes.WinDLL("user32", use_last_error=True)  # its own handles, so winplatform's and bubble's keep their own
_k = ctypes.WinDLL("kernel32", use_last_error=True)
LRESULT = wt.LPARAM
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HICON)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


def _sig(fn, args, res=wt.BOOL):
    fn.argtypes, fn.restype = args, res
    return fn


_sig(_u.RegisterClassExW, [ctypes.POINTER(WNDCLASSEXW)], wt.ATOM)
_sig(_u.CreateWindowExW, [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                          ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID], wt.HWND)
_sig(_u.DefWindowProcW, [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM], LRESULT)
_sig(_u.DestroyWindow, [wt.HWND])
_sig(_u.ShowWindow, [wt.HWND, ctypes.c_int])
_sig(_u.SetWindowPos, [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT])
_sig(_u.GetMessageW, [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT], ctypes.c_int)
_sig(_u.PeekMessageW, [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT])
_sig(_u.TranslateMessage, [ctypes.POINTER(wt.MSG)])
_sig(_u.DispatchMessageW, [ctypes.POINTER(wt.MSG)], LRESULT)
_sig(_u.PostThreadMessageW, [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM])
_sig(_u.SetTimer, [wt.HWND, ctypes.c_size_t, wt.UINT, ctypes.c_void_p], ctypes.c_size_t)
_sig(_u.KillTimer, [wt.HWND, ctypes.c_size_t])
_sig(_u.SetWindowDisplayAffinity, [wt.HWND, wt.DWORD])
_sig(_u.MonitorFromPoint, [wt.POINT, wt.DWORD], wt.HMONITOR)
_sig(_u.GetMonitorInfoW, [wt.HMONITOR, ctypes.POINTER(MONITORINFO)])
_sig(_u.LoadCursorW, [wt.HINSTANCE, ctypes.c_void_p], wt.HANDLE)
_sig(_u.GetAsyncKeyState, [ctypes.c_int], ctypes.c_short)
_sig(_k.GetCurrentThreadId, [], wt.DWORD)
_sig(_k.GetModuleHandleW, [wt.LPCWSTR], wt.HMODULE)
try:  # Windows 10 1607 and later
    _sig(_u.SetThreadDpiAwarenessContext, [ctypes.c_void_p], ctypes.c_void_p)
except AttributeError:
    pass
try:
    _shcore = ctypes.WinDLL("shcore")
    _sig(_shcore.GetDpiForMonitor, [wt.HMONITOR, ctypes.c_int, ctypes.POINTER(wt.UINT), ctypes.POINTER(wt.UINT)],
         ctypes.c_long)
except (OSError, AttributeError):
    _shcore = None

WM_TIMER, WM_WORK = 0x0113, 0x8001
WS_POPUP = 0x80000000
WS_EX_TOPMOST, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x8, 0x20, 0x80, 0x80000, \
    0x8000000
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
WDA_EXCLUDEFROMCAPTURE = 0x11
FRAME_MS = 33  # 30 a second while something's being drawn on; nothing at all once it's still
CLASS = "HeyHarryOverlay"
_KEPT = []  # every window procedure ever handed to Windows: never freed while a window class may still call it

# Her colours (island.BLUE), a white halo round each stroke so it shows on a white page or a dark one, and a soft shadow
INK = (0.04, 0.52, 1.0)
HALO = (1.0, 1.0, 1.0)
SHADOW = (0.0, 0.0, 0.0)
CAPTION_BG = (0.07, 0.07, 0.08)
TEXT = (0.97, 0.97, 0.98)
DRAW_ON, POP, PING = 0.45, 0.22, 0.75  # seconds: a stroke drawn on, a number popping in, a ping going out from a ring
OLD = 0.45  # how strongly the earlier steps show once a newer one is the one to look at


def ease(x):
    """0 to 1, fast then slowing, like a pen stroke."""
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def pop(x):
    """0 to 1 with a little overshoot, for a number coming in."""
    x = min(1.0, max(0.0, x))
    return 1 + 2.2 * (x - 1) ** 3 + 1.2 * (x - 1) ** 2 if x < 1 else 1.0


class UI:
    """The thread her Win32 windows live on, with its message loop. call(fn) runs fn there (and waits for it, unless
    wait=False); animate(key, fn) calls fn every frame while it returns True. Started once, the first time it's used."""
    _one = None
    _lock = threading.Lock()

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._one is None or not cls._one.thread.is_alive():
                cls._one = cls()
            return cls._one

    def __init__(self):
        self.jobs, self.ticks, self.handlers = queue.Queue(), {}, {}
        self.tid, self.timer, self.atom = None, 0, 0
        self.ready = threading.Event()
        self.proc = WNDPROC(self._wndproc)  # kept, or Windows calls freed memory
        _KEPT.append(self.proc)
        self.cls = f"{CLASS}{len(_KEPT)}"  # a class of its own: one left from a thread that ended keeps its own proc
        self.thread = threading.Thread(target=self._loop, name="harry-overlay", daemon=True)
        self.thread.start()
        if not self.ready.wait(5):
            raise RuntimeError("the drawing thread didn't start")

    def call(self, fn, *args, wait=True, timeout=10.0):
        if threading.current_thread() is self.thread:
            return fn(*args)
        done, box = threading.Event(), {}

        def job():
            try:
                box["value"] = fn(*args)
            except Exception as exc:  # given back to whoever asked; never the end of the loop
                box["error"] = exc
            finally:
                done.set()
        self.jobs.put(job)
        _u.PostThreadMessageW(self.tid, WM_WORK, 0, 0)
        if not wait:
            return None
        if not done.wait(timeout):
            raise TimeoutError("the drawing thread didn't answer")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def animate(self, key, fn):
        """fn() every frame, on this thread, until it returns False."""
        self.ticks[key] = fn
        if not self.timer:
            self.timer = _u.SetTimer(None, 0, FRAME_MS, None)

    def still(self, key):
        self.ticks.pop(key, None)
        if not self.ticks and self.timer:
            _u.KillTimer(None, self.timer)
            self.timer = 0

    def window(self, ex_style, handler=None, x=0, y=0, w=1, h=1, style=WS_POPUP):
        """A new top-level window of hers, on this thread. handler(msg, wparam, lparam): None to let Windows do it."""
        hwnd = _u.CreateWindowExW(ex_style, self.cls, "Hey Harry", style, x, y, w, h, None, None,
                                  _k.GetModuleHandleW(None), None)
        if not hwnd:
            raise OSError(ctypes.get_last_error(), "CreateWindowExW failed")
        if handler is not None:
            self.handlers[hwnd] = handler
        return hwnd

    def destroy(self, hwnd):
        self.handlers.pop(hwnd, None)
        if hwnd in win.NO_CAPTURE:
            win.NO_CAPTURE.remove(hwnd)
        _u.DestroyWindow(hwnd)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        handler = self.handlers.get(hwnd)
        if handler is not None:
            try:
                got = handler(msg, wparam, lparam)
                if got is not None:
                    return got
            except Exception as exc:
                print(f"  overlay window: {exc!r}")
        return _u.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _loop(self):
        try:
            _u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # per monitor v2: real pixels everywhere
        except Exception:
            pass
        self.tid = _k.GetCurrentThreadId()
        msg = wt.MSG()
        _u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # this thread's message queue, made before anyone posts
        wc = WNDCLASSEXW(cbSize=ctypes.sizeof(WNDCLASSEXW), lpfnWndProc=self.proc,
                         hInstance=_k.GetModuleHandleW(None), hCursor=_u.LoadCursorW(None, ctypes.c_void_p(32512)),
                         lpszClassName=self.cls)
        self.atom = _u.RegisterClassExW(ctypes.byref(wc))
        self.ready.set()
        while True:
            got = _u.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if got in (0, -1):
                break
            if not msg.hWnd and msg.message == WM_WORK:
                self._drain()
            elif not msg.hWnd and msg.message == WM_TIMER:
                self._tick()
            else:
                _u.TranslateMessage(ctypes.byref(msg))
                _u.DispatchMessageW(ctypes.byref(msg))

    def _drain(self):
        while True:
            try:
                job = self.jobs.get_nowait()
            except queue.Empty:
                return
            job()

    def _tick(self):
        for key, fn in list(self.ticks.items()):
            try:
                keep = fn()
            except Exception as exc:
                print(f"  overlay frame: {exc!r}")
                keep = False
            if not keep:
                self.still(key)


def monitor_at(x, y):
    """((left, top, right, bottom) of the screen at a point, its work area, its scale), real pixels."""
    mon = _u.MonitorFromPoint(wt.POINT(int(x), int(y)), 2)  # MONITOR_DEFAULTTONEAREST
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not _u.GetMonitorInfoW(mon, ctypes.byref(info)):
        return (0, 0, 1920, 1080), (0, 0, 1920, 1040), 1.0
    r, w = info.rcMonitor, info.rcWork
    scale = 1.0
    if _shcore is not None:
        dx, dy = wt.UINT(), wt.UINT()
        if _shcore.GetDpiForMonitor(mon, 0, ctypes.byref(dx), ctypes.byref(dy)) == 0 and dx.value:
            scale = dx.value / 96
    return (r.left, r.top, r.right, r.bottom), (w.left, w.top, w.right, w.bottom), scale


# --------------------------------------------------------------------------- drawing, as numpy signed distances
class Canvas:
    """Premultiplied RGBA, 0 to 1, for a part of the screen starting at (x, y). paint() lays a stroke's coverage over
    what's there."""

    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = int(x), int(y), int(w), int(h)
        self.img = np.zeros((self.h, self.w, 4), np.float32)

    def paint(self, x0, y0, cover, rgb, alpha=1.0):
        if cover is None or alpha <= 0:
            return
        h, w = cover.shape
        X0, Y0 = max(self.x, x0), max(self.y, y0)
        X1, Y1 = min(self.x + self.w, x0 + w), min(self.y + self.h, y0 + h)
        if X1 <= X0 or Y1 <= Y0:
            return
        c = cover[Y0 - y0:Y1 - y0, X0 - x0:X1 - x0] * float(alpha)
        region = self.img[Y0 - self.y:Y1 - self.y, X0 - self.x:X1 - self.x]
        region *= (1.0 - c)[..., None]
        region[..., 0] += rgb[0] * c
        region[..., 1] += rgb[1] * c
        region[..., 2] += rgb[2] * c
        region[..., 3] += c

    def bgra(self):
        out = np.empty((self.h, self.w, 4), np.uint8)
        img = np.clip(self.img, 0.0, 1.0) * 255.0 + 0.5
        out[..., 0], out[..., 1], out[..., 2], out[..., 3] = img[..., 2], img[..., 1], img[..., 0], img[..., 3]
        return out


def _grid(x0, y0, x1, y1):
    x0, y0, x1, y1 = int(math.floor(x0)), int(math.floor(y0)), int(math.ceil(x1)), int(math.ceil(y1))
    ys, xs = np.mgrid[y0:max(y0 + 1, y1), x0:max(x0 + 1, x1)].astype(np.float32)
    return x0, y0, xs + 0.5, ys + 0.5


def _band(d, width, soft=1.0):
    """Coverage of a stroke width wide round its centre line, d the distance from it."""
    return np.clip((width / 2 - d) / soft + 0.5, 0.0, 1.0)


def _sweep(xs, ys, cx, cy, progress, k):
    """What a pen going round clockwise from the top has drawn by progress (0 to 1); k: pixels per radian at the edge."""
    if progress >= 1:
        return 1.0
    theta = np.mod(np.arctan2(xs - cx, cy - ys), 2 * np.pi)
    return np.clip((progress * 2 * np.pi - theta) * k + 0.5, 0.0, 1.0)


def ring(cx, cy, r, width, progress=1.0, soft=1.0):
    pad = width + soft * 2
    x0, y0, xs, ys = _grid(cx - r - pad, cy - r - pad, cx + r + pad, cy + r + pad)
    cover = _band(np.abs(np.hypot(xs - cx, ys - cy) - r), width, soft) * _sweep(xs, ys, cx, cy, progress, max(r, 1.0))
    return x0, y0, cover


def disc(cx, cy, r, soft=1.0):
    x0, y0, xs, ys = _grid(cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2)
    return x0, y0, np.clip((r - np.hypot(xs - cx, ys - cy)) / soft + 0.5, 0.0, 1.0)


def _rbox_d(xs, ys, x0, y0, x1, y1, radius):
    cx, cy, hx, hy = (x0 + x1) / 2, (y0 + y1) / 2, max(1.0, (x1 - x0) / 2), max(1.0, (y1 - y0) / 2)
    radius = min(radius, hx, hy)
    qx, qy = np.abs(xs - cx) - (hx - radius), np.abs(ys - cy) - (hy - radius)
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - radius


def box(x0, y0, x1, y1, radius, width, progress=1.0, soft=1.0):
    pad = width + soft * 2
    gx, gy, xs, ys = _grid(x0 - pad, y0 - pad, x1 + pad, y1 + pad)
    d = _rbox_d(xs, ys, x0, y0, x1, y1, radius)
    cover = _band(np.abs(d), width, soft)
    if progress < 1:
        cx, cy, hx, hy = (x0 + x1) / 2, (y0 + y1) / 2, max(1.0, (x1 - x0) / 2), max(1.0, (y1 - y0) / 2)
        cover = cover * _sweep((xs - cx) / hx * min(hx, hy) + cx, (ys - cy) / hy * min(hx, hy) + cy, cx, cy, progress,
                               min(hx, hy))
    return gx, gy, cover


def filled_box(x0, y0, x1, y1, radius, soft=1.0):
    gx, gy, xs, ys = _grid(x0 - 2, y0 - 2, x1 + 2, y1 + 2)
    return gx, gy, np.clip(-_rbox_d(xs, ys, x0, y0, x1, y1, radius) / soft + 0.5, 0.0, 1.0)


def segment(ax, ay, bx, by, width, progress=1.0, soft=1.0):
    """A line from a to b with round ends, drawn on from a as far as progress."""
    bx, by = ax + (bx - ax) * progress, ay + (by - ay) * progress
    pad = width + soft * 2
    x0, y0, xs, ys = _grid(min(ax, bx) - pad, min(ay, by) - pad, max(ax, bx) + pad, max(ay, by) + pad)
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    h = np.clip(((xs - ax) * dx + (ys - ay) * dy) / length, 0.0, 1.0) if length > 0 else 0.0
    return x0, y0, _band(np.hypot(xs - ax - dx * h, ys - ay - dy * h), width, soft)


def _layers(canvas, cover_fn, width, s, alpha):
    """A stroke as she draws it: a soft shadow, a white halo, then her blue."""
    for w, rgb, a, soft in ((width + 9 * s, SHADOW, 0.16, 3.0 * s), (width + 5 * s, HALO, 0.92, 1.0),
                            (width, INK, 1.0, 1.0)):
        x0, y0, cover = cover_fn(w, soft)
        canvas.paint(x0, y0, cover, rgb, a * alpha)


# --------------------------------------------------------------------------- what she draws
class Mark:
    """One thing she points at: kind "ring" (where to click), "box" (an area to look at), "underline" (words to read)
    or "dot" (a point), round rect = (left, top, right, bottom) in real pixels; n, its number; caption, a few words
    next to it; link, a line drawn from the mark before."""

    def __init__(self, kind, rect, n=None, caption="", link=False, s=1.0):
        self.kind = kind if kind in ("ring", "box", "underline", "dot") else "ring"
        l, t, r, b = (float(v) for v in rect)
        self.rect = (min(l, r), min(t, b), max(l, r), max(t, b))
        self.n, self.caption, self.link, self.s = n, " ".join(str(caption or "").split()), link, s
        self.born = time.time()
        w, h = self.rect[2] - self.rect[0], self.rect[3] - self.rect[1]
        if self.kind == "ring" and (w > 300 * s or h > 140 * s):
            self.kind = "box"  # a big area isn't a thing to click, ringed it would cover the screen
        cx, cy = (self.rect[0] + self.rect[2]) / 2, (self.rect[1] + self.rect[3]) / 2
        self.centre = (cx, cy)
        self.r = max(20 * s, min(150 * s, math.hypot(w, h) / 2 + 8 * s))
        self.caption_box, self.rows = None, []

    def anchor(self):
        """Where a line to it ends, and the corner its number sits on."""
        cx, cy = self.centre
        if self.kind == "ring":
            return (cx, cy), (cx - self.r * 0.71, cy - self.r * 0.71)
        if self.kind == "dot":
            return (cx, cy), (cx - 14 * self.s, cy - 14 * self.s)
        l, t, r, b = self.rect
        pad = 6 * self.s
        if self.kind == "underline":
            return (l, b + pad), (l - 4 * self.s, b + pad)
        return (cx, cy), (l - pad, t - pad)

    def edge(self, toward):
        """Where a line from it toward a point leaves it: on its ring, or the side of its box, never its middle."""
        cx, cy = self.centre
        dx, dy = toward[0] - cx, toward[1] - cy
        length = math.hypot(dx, dy)
        if length < 1:
            return cx, cy
        ux, uy = dx / length, dy / length
        s = self.s
        if self.kind == "ring":
            return cx + ux * (self.r + 7 * s), cy + uy * (self.r + 7 * s)
        if self.kind == "dot":
            return cx + ux * 16 * s, cy + uy * 16 * s
        l, t, r, b = self.rect
        pad = 13 * s if self.kind == "box" else 8 * s
        hx, hy = (r - l) / 2 + pad, (b - t) / 2 + pad
        k = min(hx / abs(ux) if abs(ux) > 1e-6 else 1e9, hy / abs(uy) if abs(uy) > 1e-6 else 1e9)
        return cx + ux * k, cy + uy * k

    def bounds(self):
        """Everything it draws, its caption too, as (left, top, right, bottom)."""
        s = self.s
        if self.kind == "ring":
            cx, cy = self.centre
            r = self.r + 28 * s  # its ping going out
            out = [cx - r, cy - r, cx + r, cy + r]
        else:
            l, t, r, b = self.rect
            pad = 24 * s
            out = [l - pad, t - pad, r + pad, b + pad]
        if self.caption_box:
            l, t, r, b = self.caption_box
            out = [min(out[0], l - 8 * s), min(out[1], t - 8 * s), max(out[2], r + 8 * s), max(out[3], b + 12 * s)]
        return out

    def layout_caption(self, text_font, screen):
        """Where its caption goes: under it if there's room on the screen, else over it, kept on the screen."""
        if not self.caption:
            return
        s = self.s
        rows = text_font.wrap(self.caption, int(320 * s), 3)
        if not rows:
            return
        widest = max(text_font.measure(r) for r in rows)
        pad_x, pad_y, gap = 12 * s, 8 * s, 14 * s
        w, h = widest + 2 * pad_x, len(rows) * text_font.line + 2 * pad_y
        if self.kind == "ring":
            cx, cy = self.centre
            top, bottom, left = cy - self.r, cy + self.r, cx - w / 2
        else:
            left, top, _, bottom = self.rect
        y = bottom + gap if bottom + gap + h <= screen[3] - 8 * s else top - gap - h
        x = min(max(screen[0] + 8 * s, left), screen[2] - 8 * s - w)
        y = min(max(screen[1] + 8 * s, y), screen[3] - 8 * s - h)
        self.caption_box, self.rows = (x, y, x + w, y + h), rows

    def draw(self, canvas, now, fonts, current, before=None):
        s, age = self.s, now - self.born
        alpha = 1.0 if current else OLD
        progress = ease(age / DRAW_ON)
        stroke = 3.6 * s
        if self.link and before is not None and progress > 0:  # from the step before, drawn on first
            # from the edge of the one before to the edge of this one, never centre to centre
            (ax, ay), (bx, by) = before.edge(self.centre), self.edge(before.centre)
            length = math.hypot(bx - ax, by - ay)
            ux, uy = ((bx - ax) / length, (by - ay) / length) if length > 1 else (0.0, 0.0)
            if self.n is not None and length > 1:  # stopping short of its number, not on it
                badge = self.anchor()[1]
                while length > 30 * s and math.hypot(bx - badge[0], by - badge[1]) < 24 * s:
                    bx, by, length = bx - ux * 4 * s, by - uy * 4 * s, length - 4 * s
            if length > 20 * s:
                p = ease(age / (DRAW_ON * 0.8))
                _layers(canvas, lambda w, soft: segment(ax, ay, bx, by, w * 0.8, p, soft), stroke, s, alpha * 0.9)
                if p >= 1:  # its head, two short strokes back from the tip
                    for turn in (0.5, -0.5):
                        hx = bx - (ux * math.cos(turn) - uy * math.sin(turn)) * 13 * s
                        hy = by - (ux * math.sin(turn) + uy * math.cos(turn)) * 13 * s
                        _layers(canvas, lambda w, soft, hx=hx, hy=hy: segment(bx, by, hx, hy, w * 0.8, 1.0, soft),
                                stroke, s, alpha * 0.9)
        if self.kind == "ring":
            cx, cy = self.centre
            _layers(canvas, lambda w, soft: ring(cx, cy, self.r, w, progress, soft), stroke, s, alpha)
            if current and progress >= 1:  # a ping going out, twice, so the eye finds it
                for start in (DRAW_ON, DRAW_ON + 0.9):
                    t = (age - start) / PING
                    if 0 <= t <= 1:
                        x0, y0, cover = ring(cx, cy, self.r + 26 * s * ease(t), 2.4 * s)
                        canvas.paint(x0, y0, cover, INK, 0.55 * (1 - t))
        elif self.kind == "dot":
            cx, cy = self.centre
            _layers(canvas, lambda w, soft: ring(cx, cy, 9 * s, w, progress, soft), stroke, s, alpha)
            x0, y0, cover = disc(cx, cy, 4 * s)
            canvas.paint(x0, y0, cover, INK, alpha * progress)
        elif self.kind == "underline":
            l, _, r, b = self.rect
            y = b + 5 * s
            _layers(canvas, lambda w, soft: segment(l, y, r, y, w, progress, soft), stroke, s, alpha)
        else:
            l, t, r, b = self.rect
            pad = 6 * s
            _layers(canvas, lambda w, soft: box(l - pad, t - pad, r + pad, b + pad, 10 * s, w, progress, soft),
                    stroke, s, alpha)
        if self.n is not None:  # its number, popping in on the corner
            k = pop((age - DRAW_ON * 0.6) / POP)
            if k > 0:
                (_, _), (bx, by) = self.anchor()
                rr = 12.5 * s * k
                for r_, rgb, a in ((rr + 2.5 * s, HALO, 0.95), (rr, INK, 1.0)):
                    x0, y0, cover = disc(bx, by, r_)
                    canvas.paint(x0, y0, cover, rgb, a * alpha)
                if k > 0.6:
                    glyph = fonts["badge"].render(str(self.n))
                    gx, gy = int(round(bx - glyph.shape[1] / 2)), int(round(by - glyph.shape[0] / 2))
                    canvas.paint(gx, gy, glyph, TEXT, alpha * min(1.0, (k - 0.6) / 0.4))
        if current and self.caption_box:  # its caption, fading in once the stroke's mostly there
            a = min(1.0, max(0.0, (age - DRAW_ON * 0.7) / 0.2))
            if a > 0:
                l, t, r, b = self.caption_box
                x0, y0, cover = filled_box(l, t, r, b, 10 * s)
                canvas.paint(x0, y0, cover, CAPTION_BG, 0.92 * a)
                font = fonts["caption"]
                for i, row in enumerate(self.rows):
                    glyph = font.render(row)
                    canvas.paint(int(round(l + 12 * s)) - 2, int(round(t + 8 * s + i * font.line)) - 1, glyph, TEXT, a)

    def busy(self, now):
        """True while it still moves: drawn on, its number popping in, its pings."""
        return now - self.born < DRAW_ON + 0.9 + PING + 0.05


class Scene:
    """What she's drawing now, on one screen: marks added one at a time (add), the newest the one to look at, the
    earlier ones fainter; cleared (clear) or gone by itself after hold seconds with nothing new. Every call goes to
    the drawing thread; any thread may make them."""

    def __init__(self, hold=30.0):
        self.ui = UI.get()
        self.hold, self.marks, self.hwnd, self.until = hold, [], None, time.time() + hold
        self.fonts = None
        self.screen, self.dib, self.dc, self.bitmap, self.old = None, None, None, None, None
        self.dirty, self.closed, self.fade = None, False, None
        self.key = f"scene:{id(self)}"

    # ------------------------------------------------------------------ from any thread
    def add(self, kind, rect, n=None, caption="", link=False):
        """One more mark, the one to look at now. Returns it, or None once the scene is closed."""
        return self.ui.call(self._add, kind, rect, n, caption, link)

    def clear(self, fade=True):
        if not self.closed:
            self.ui.call(self._clear, fade, wait=False)

    @property
    def alive(self):
        return not self.closed

    # ------------------------------------------------------------------ on the drawing thread
    def _add(self, kind, rect, n, caption, link):
        if self.closed:
            return None
        import bubble  # GDI text, made on this thread
        l, t, r, b = rect
        if self.screen is None:
            self.screen, work, s = monitor_at((l + r) / 2, (t + b) / 2)
            self.work, self.s = work, s
            self.fonts = {"caption": bubble.Text(round(15 * s), 500), "badge": bubble.Text(round(13.5 * s), 700)}
            self._window()
        mark = Mark(kind, rect, n, caption, link and bool(self.marks), self.s)
        mark.layout_caption(self.fonts["caption"], self.work)
        self.marks.append(mark)
        self.until = time.time() + self.hold
        self.fade = None
        self.ui.animate(self.key, self._frame)
        return mark

    def _window(self):
        import bubble
        l, t, r, b = self.screen
        w, h = r - l, b - t
        ex = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        self.hwnd = self.ui.window(ex, None, l, t, w, h)
        win.NO_CAPTURE.append(self.hwnd)  # never in her own screenshots
        self.dc = bubble._new_dc(None)
        self.bitmap, self.dib = bubble._dib(self.dc, w, h)
        self.old = bubble._select(self.dc, self.bitmap)
        self.dib[:] = 0
        _u.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        self._push()

    def _push(self):
        import bubble
        l, t, r, b = self.screen
        bubble._flush()
        size, src, pos = wt.SIZE(r - l, b - t), wt.POINT(0, 0), wt.POINT(l, t)
        blend = bubble._BLEND(0, 0, 255, 1)
        bubble._ULW(self.hwnd, None, ctypes.byref(pos), ctypes.byref(size), self.dc, ctypes.byref(src), 0,
                    ctypes.byref(blend), 2)

    def _frame(self):
        if self.closed:
            return False
        now = time.time()
        if self.fade is None and now >= self.until:
            self.fade = now
        fading = 1.0 if self.fade is None else max(0.0, 1.0 - (now - self.fade) / 0.25)
        if fading <= 0:
            self._close()
            return False
        sl, st, sr, sb = self.screen
        box_ = None
        for m in self.marks:
            b = m.bounds()
            box_ = b if box_ is None else [min(box_[0], b[0]), min(box_[1], b[1]), max(box_[2], b[2]),
                                           max(box_[3], b[3])]
        x0, y0 = max(sl, int(box_[0])), max(st, int(box_[1]))
        x1, y1 = min(sr, int(math.ceil(box_[2]))), min(sb, int(math.ceil(box_[3])))
        if self.dirty is not None:  # what was drawn last time, gone first
            dx0, dy0, dx1, dy1 = self.dirty
            self.dib[dy0 - st:dy1 - st, dx0 - sl:dx1 - sl] = 0
        if x1 > x0 and y1 > y0:
            canvas = Canvas(x0, y0, x1 - x0, y1 - y0)
            for i, m in enumerate(self.marks):
                m.draw(canvas, now, self.fonts, i == len(self.marks) - 1, self.marks[i - 1] if i else None)
            if fading < 1:
                canvas.img *= fading
            self.dib[y0 - st:y1 - st, x0 - sl:x1 - sl] = canvas.bgra()
            self.dirty = (x0, y0, x1, y1)
        self._push()
        moving = any(m.busy(now) for m in self.marks) or self.fade is not None
        if not moving:  # still: no frames till something changes, but it still goes when its time is up
            threading.Timer(max(0.05, self.until - now), lambda: self.ui.call(self._wake, wait=False)).start()
        return moving

    def _wake(self):
        if not self.closed:
            self.ui.animate(self.key, self._frame)

    def _clear(self, fade):
        if self.closed:
            return
        if fade and self.marks:
            self.until = 0
            self.fade = time.time()
            self.ui.animate(self.key, self._frame)
        else:
            self._close()

    def _close(self):
        import bubble
        if self.closed:
            return
        self.closed = True
        self.ui.still(self.key)
        if self.hwnd:
            _u.ShowWindow(self.hwnd, SW_HIDE)
            self.ui.destroy(self.hwnd)
            self.hwnd = None
        if self.dc:
            bubble._select(self.dc, self.old)
            bubble._delete(self.bitmap)
            bubble._delete_dc(self.dc)
            self.dc = None
        for font in (self.fonts or {}).values():
            font.close()
        self.fonts = None


CURRENT = [None]  # the scene on the screen now: a new one takes its place


def scene(hold=30.0):
    """A new, empty scene, the one before it cleared."""
    old, CURRENT[0] = CURRENT[0], Scene(hold)
    if old is not None:
        old.clear(fade=False)
    return CURRENT[0]


def clear():
    """Whatever she's drawn, gone."""
    old, CURRENT[0] = CURRENT[0], None
    if old is not None:
        old.clear()


def showing():
    return CURRENT[0] is not None and CURRENT[0].alive


# --------------------------------------------------------------------------- the mouse and Esc, while she shows you
VK_LBUTTON, VK_ESCAPE = 0x01, 0x1B


def pressed(vk):
    return bool(_u.GetAsyncKeyState(vk) & 0x8000)


def wait_click(timeout, stop=None, poll=0.03):
    """Waits for a left click anywhere (pressed and let go). "click" with where it was, "esc" if Esc was pressed,
    "stop" if stop() said so, else "timeout"."""
    end, down = time.time() + timeout, pressed(VK_LBUTTON)
    while time.time() < end:
        if stop is not None and stop():
            return "stop", None
        if pressed(VK_ESCAPE):
            return "esc", None
        now = pressed(VK_LBUTTON)
        if down and not now:
            return "click", win.cursor_pos()
        down = now
        time.sleep(poll)
    return "timeout", None
