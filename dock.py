"""Her dock (30 October 2026, the owner's ask, after bloom, github.com/SehajveerSingh2005/bloom): your pinned apps
and the open ones along the bottom of the screen in her island's glass, each growing as the pointer comes near it, as
a Mac's dock does, with a dot under the ones running and a name over the one pointed at. Click one to open it or bring
it to the front, and in front already, to put it down, or with more than one window to go through them; the middle
button opens another; right-click to pin it, unpin it or close its windows; drag a pinned one along to move it. Start
and Windows' search are at its left, Downloads at its right.

It hides (dock_mode) out of the way of the window in front ("smart"), or till the pointer's at the bottom of the screen
("peek"), or never ("fixed"); over a full-screen game or video always. With dock_replace_taskbar it hides Windows'
taskbar while it's on and puts it back when it's off or she quits; stopped any other way, a watchdog of hers (a second
pythonw, waiting on her) puts it back, and so does her next start. Nothing in Windows' settings is changed: the
taskbar's window is only hidden, so a restart of Explorer brings it back too.

The windows are read on a thread of their own when Windows says one came, went or was shown (a WinEvent hook on Tk's
thread, which only marks them changed), and its picture's drawn only while something on it moves."""
import ctypes
import math
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import uuid
from ctypes import wintypes as wt

import numpy as np

import bubble
import edges
import identity
import island_face as face
import settings
import winplatform as win

ICON, SLOT, GAP_W, PAD = 44, 54, 14, 9  # logical px: an icon at rest, from one to the next, a divider, round them
MAG, REACH = 1.6, 1.7  # how much the icon pointed at grows, and over how many slots either side the growing reaches
LIFT, LABEL, MARGIN, BOTTOM = 6, 26, 14, 8  # logical px: the rise, the name's pill, round it all, off the bottom
POLL, POLL_FAR, LIVE = 0.12, 0.2, 0.02  # seconds between looks at the pointer: near it, far off, and while it moves
SHOW_AFTER, HIDE_AFTER = 0.25, 0.8  # seconds at the bottom edge before a hidden dock comes, and away before it goes
FOLDERS = (("shell:Downloads", "Downloads"),)  # the Recycle Bin was here too, till the owner had it off (30 October)
# Start, then Windows' search beside it, as the taskbar has them (30 October 2026, the owner's ask)
FIRST = ({"kind": "start", "key": "start", "name": "Start", "path": "", "windows": [], "icon": None, "her": False},
         {"kind": "search", "key": "search", "name": "Search", "path": "", "windows": [], "icon": None, "her": False})
MODES = ("smart", "peek", "fixed")
TASKBAR_PINS = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Internet Explorer", "Quick Launch",
                            "User Pinned", "TaskBar")
FLAG = os.path.join(win.APPDATA_DIR, "taskbar-hidden")  # there while she has Windows' taskbar hidden

_user32 = ctypes.WinDLL("user32")  # its own, so these signatures don't change winplatform's
_user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
_user32.FindWindowW.restype = wt.HWND
_user32.GetForegroundWindow.restype = wt.HWND
_user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
_user32.IsIconic.argtypes = [wt.HWND]
_user32.IsWindowVisible.argtypes = [wt.HWND]
_user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
_user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
_user32.GetAncestor.restype = wt.HWND
_user32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
_user32.MonitorFromPoint.restype = wt.HANDLE
_user32.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.POINTER(win.MONITORINFO)]
WINEVENTPROC = ctypes.WINFUNCTYPE(None, wt.HANDLE, wt.DWORD, wt.HWND, wt.LONG, wt.LONG, wt.DWORD, wt.DWORD)
_user32.SetWinEventHook.argtypes = [wt.DWORD, wt.DWORD, wt.HMODULE, WINEVENTPROC, wt.DWORD, wt.DWORD, wt.DWORD]
_user32.SetWinEventHook.restype = wt.HANDLE
_user32.UnhookWinEvent.argtypes = [wt.HANDLE]
# the windows' events read again for: shown or hidden, made or gone, minimised or back, cloaked or not (a Store app's)
EVENTS = ((0x8001, 0x8003), (0x0016, 0x0017), (0x8017, 0x8018))
WM_CLOSE, SW_MINIMIZE, SW_HIDE, SW_SHOW = 0x10, 6, 0, 5


# --------------------------------------------------------------------------- shortcuts and pins
class _GUID(ctypes.Structure):
    _fields_ = [("raw", ctypes.c_ubyte * 16)]


def _guid(text):
    g = _GUID()
    ctypes.memmove(g.raw, uuid.UUID(text).bytes_le, 16)
    return g


CLSID_SHELL_LINK = _guid("00021401-0000-0000-c000-000000000046")
IID_SHELL_LINK = _guid("000214f9-0000-0000-c000-000000000046")  # IShellLinkW
IID_PERSIST_FILE = _guid("0000010b-0000-0000-c000-000000000046")
_ole32 = ctypes.WinDLL("ole32")
_ole32.CoCreateInstance.argtypes = [ctypes.POINTER(_GUID), ctypes.c_void_p, wt.DWORD, ctypes.POINTER(_GUID),
                                    ctypes.POINTER(ctypes.c_void_p)]
_ole32.CoCreateInstance.restype = ctypes.c_long


def _method(ptr, index, *types):
    """A COM object's method by its place in its table, called with the object first."""
    table = ctypes.cast(ctypes.c_void_p.from_address(ptr).value, ctypes.POINTER(ctypes.c_void_p))
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(table[index])


def shortcut(path):
    """What a shortcut opens, the program or file's path, or "" for one with no file behind it (a Store app's). By hand
    through IShellLinkW: comtypes' own GetPath raised IndexError on this PC on 30 October 2026."""
    win._com()
    link = ctypes.c_void_p()
    if _ole32.CoCreateInstance(ctypes.byref(CLSID_SHELL_LINK), None, 1, ctypes.byref(IID_SHELL_LINK),
                               ctypes.byref(link)) != 0 or not link.value:
        return ""
    try:
        persist = ctypes.c_void_p()
        if _method(link.value, 0, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))(
                link.value, ctypes.byref(IID_PERSIST_FILE), ctypes.byref(persist)) != 0 or not persist.value:
            return ""
        try:
            if _method(persist.value, 5, wt.LPCWSTR, wt.DWORD)(persist.value, str(path), 0) != 0:  # Load, to read
                return ""
        finally:
            _method(persist.value, 2)(persist.value)
        target = ctypes.create_unicode_buffer(1024)
        if _method(link.value, 3, wt.LPWSTR, ctypes.c_int, ctypes.c_void_p, wt.DWORD)(
                link.value, target, 1024, None, 0) != 0:  # GetPath
            return ""
        return target.value
    finally:
        _method(link.value, 2)(link.value)


def taskbar_pins():
    """The taskbar's pinned shortcuts, File Explorer first, then by name: [{"path", "name"}]. (Windows keeps their
    order in the registry, in a form of its own.)"""
    try:
        names = sorted(n for n in os.listdir(TASKBAR_PINS) if n.lower().endswith(".lnk"))
    except OSError:
        names = []
    found = [{"path": os.path.join(TASKBAR_PINS, n), "name": os.path.splitext(n)[0]} for n in names]
    found.sort(key=lambda p: p["name"].lower() != "file explorer")
    return found


def pins():
    """Your pinned apps in their order, [{"path", "name"}]: the taskbar's, the first time the dock's on."""
    kept = settings.get("dock_pins")
    if kept is None:
        kept = taskbar_pins()
        settings.put("dock_pins", kept)
    return [dict(p) for p in kept if isinstance(p, dict) and p.get("path")]


def pinned(items):
    """The pins in the order the dock has them now, for Settings."""
    return [{"path": it["path"], "name": it["name"]} for it in items if it["kind"] == "pin"]


_targets = {}


def _target(path):
    """The program a pin opens: its own path, or a shortcut's target, kept."""
    hit = _targets.get(path)
    if hit is None:
        hit = shortcut(path) if path.lower().endswith(".lnk") else path
        _targets[path] = hit
    return hit


def _same(a, b):
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    return bool(a) and bool(b) and (a == b or a.startswith(b + " ") or a.endswith(" - " + b))


def read(pinned_now, size):
    """What's on the dock, read off Tk's thread: [{"kind": "start", "search", "pin", "app" or "folder", "key",
    "name", "path", "windows" (front-most first), "icon", "her"}]: Start and Search, the pins, the open apps that
    aren't pinned, then the folders. size: an icon's px, grown as far as it grows."""
    import island_art as art
    me = os.getpid()
    groups, order = {}, []
    for hwnd, exe, title in win.open_windows():
        her = win._pid(hwnd) == me
        key = "her" if her else (exe.lower() if exe else f"window:{hwnd}")
        if key not in groups:
            groups[key] = {"exe": exe, "windows": [], "title": title, "her": her}
            order.append(key)
        groups[key]["windows"].append(hwnd)
    items = [dict(it) for it in FIRST]
    used = set()
    for pin in pinned_now:
        path = pin["path"]
        if not os.path.exists(path):
            continue
        target = _target(path)
        key = target.lower() if target else None
        if key is None:  # a Store app's shortcut: its windows by its name
            key = next((g for g in order if g not in used and _same(groups[g]["title"], pin.get("name"))), None)
        group = groups.get(key) if key else None
        if group is not None:
            used.add(key)
        icon = art.exe_icon(target, size) if target.lower().endswith(".exe") else None
        if icon is None:
            icon = art.file_icon(path, size)
        name = pin.get("name") or os.path.splitext(os.path.basename(path))[0]
        items.append({"kind": "pin", "key": "pin:" + path.lower(), "name": name, "path": path, "exe": target,
                      "windows": list(group["windows"]) if group else [], "icon": icon, "her": False})
    for key in order:
        if key in used:
            continue
        g = groups[key]
        exe = g["exe"]
        if g["her"]:
            name, icon = identity.name(), art.file_icon(edges.HER_ICON, size)
        else:
            name = (win.file_description(exe) if exe else "") or \
                (os.path.splitext(os.path.basename(exe))[0].capitalize() if exe else g["title"])
            icon = art.exe_icon(exe, size) if exe else None
            if icon is None:  # a Store app: its own logo, as Start has it, else its window's small icon
                icon = art.window_app_icon(g["windows"][0], size)
            if icon is None:
                icon = art.window_icon(g["windows"][0], size)
        items.append({"kind": "app", "key": "app:" + key, "name": name, "path": exe, "exe": exe,
                      "windows": g["windows"], "icon": icon, "her": g["her"]})
    for path, name in FOLDERS:
        items.append({"kind": "folder", "key": path, "name": name, "path": path, "windows": [],
                      "icon": art.file_icon(path, size), "her": False})
    return items


def slots(items):
    """The dock's slots left to right, [(kind, item's index)]: "icon" each, "gap" for a divider before the open apps
    that aren't pinned and before the folders."""
    out, last = [], None
    for i, it in enumerate(items):
        part = {"start": "pin", "search": "pin", "pin": "pin"}.get(it["kind"], it["kind"])
        if last is not None and part != last:
            out.append(("gap", None))
        out.append(("icon", i))
        last = part
    return out


# --------------------------------------------------------------------------- where things go
def row(kinds, px, strength, s):
    """Where each slot is along the dock for the pointer at px along it (None for nowhere): ([(its middle, how much
    it's grown)], the glass's left and right), in px from the left end of the glass at rest. kinds: "icon" or "gap"
    each; s: logical px to real ones. The icon under the pointer grows MAG times, those near it less, pushing the rest
    aside; and the row slides so the pointer stays over the same part of the same icon, as a Mac's does, so nothing
    moves out from under it."""
    pad = PAD * s
    widths = [SLOT * s if kind == "icon" else GAP_W * s for kind in kinds]
    middles, x = [], pad
    for w in widths:
        middles.append(x + w / 2)
        x += w
    grow = []
    for kind, m in zip(kinds, middles):
        d = abs(m - px) / (REACH * SLOT * s) if px is not None else 9.0
        bump = math.cos(math.pi / 2 * min(1.0, d)) ** 2 if kind == "icon" else 0.0
        grow.append(1.0 + (MAG - 1.0) * max(0.0, min(1.0, strength)) * bump)
    grown = [w * g for w, g in zip(widths, grow)]
    lefts, x = [], pad
    for w in grown:
        lefts.append(x)
        x += w
    end, shift = x + pad, 0.0
    if px is not None and strength > 0 and widths:
        x, j, f = pad, len(widths) - 1, 1.0
        for i, w in enumerate(widths):
            if px < x + w:
                j, f = i, max(0.0, (px - x) / w)
                break
            x += w
        shift = px - (lefts[j] + f * grown[j]) if px >= pad else 0.0
    return [(lf + w / 2 + shift, g) for lf, w, g in zip(lefts, grown, grow)], shift, end + shift


def at_rest(kinds, s):
    """The glass's width at rest, px."""
    return (2 * PAD + sum(SLOT if kind == "icon" else GAP_W for kind in kinds)) * s


def up(mode, full, overlapped, summoned):
    """Whether the dock's up: never over a full-screen app; always when it's fixed or called up (the pointer at the
    bottom edge or on it); and, out of the way ("smart"), while the window in front isn't over where it sits."""
    if full:
        return False
    if mode == "fixed" or summoned:
        return True
    return mode == "smart" and not overlapped


def action(item, front, turn=0):
    """What a click on an item does: ("start",), ("search",), ("open", path) for one with no window, ("front",
    hwnd), or ("down", hwnd) for the app in front with one window. front: the window in front; turn: how many times
    it's been clicked in front, to go through its windows."""
    if item["kind"] in ("start", "search"):
        return (item["kind"],)
    windows = item.get("windows") or []
    if not windows:
        return ("open", item["path"]) if item.get("path") else None
    if front in windows:
        if len(windows) == 1:
            return ("down", front)
        return ("front", windows[(windows.index(front) + 1) % len(windows)])
    return ("front", windows[0])


def menu(item, pinned_paths):
    """A right-click's menu for an item, [(label, what)], what one of "new", "pin", "unpin", "close", "open" or
    None for its name at the top."""
    out = [(item["name"], None)]
    if item["kind"] in ("folder", "start", "search"):
        return out + [("Open", "open")]
    if item.get("path") and not item.get("her"):
        out.append(("New window", "new"))
        on = item["path"].lower() in pinned_paths or (item.get("exe") or "").lower() in pinned_paths
        out.append(("Unpin from the dock", "unpin") if item["kind"] == "pin" or on else ("Pin to the dock", "pin"))
    n = len(item.get("windows") or [])
    if n:
        out.append(("Close window" if n == 1 else f"Close {n} windows", "close"))
    return out


# --------------------------------------------------------------------------- Windows' taskbar
def _taskbar():
    return _user32.FindWindowW("Shell_TrayWnd", None)


def hide_taskbar():
    """Windows' taskbar hidden, its window only, and FLAG put down so it comes back if she stops."""
    if not os.path.exists(FLAG):
        try:
            os.makedirs(os.path.dirname(FLAG), exist_ok=True)
            with open(FLAG, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
        except OSError:
            pass
    bar = _taskbar()
    if bar and _user32.IsWindowVisible(bar):
        _user32.ShowWindow(bar, SW_HIDE)


def show_taskbar():
    """Windows' taskbar back, and FLAG gone."""
    bar = _taskbar()
    if bar:
        _user32.ShowWindow(bar, SW_SHOW)
    try:
        os.remove(FLAG)
    except OSError:
        pass


# the watchdog: waits on her, and if FLAG's still there when she's gone, the taskbar's shown again and FLAG's gone
WATCHDOG = (
    "import ctypes, os, sys\n"
    "k = ctypes.windll.kernel32\n"
    "h = k.OpenProcess(0x100000, False, int(sys.argv[1]))\n"
    "if h:\n"
    "    k.WaitForSingleObject(h, 0xFFFFFFFF)\n"
    "if os.path.exists(sys.argv[2]):\n"
    "    bar = ctypes.windll.user32.FindWindowW('Shell_TrayWnd', None)\n"
    "    if bar:\n"
    "        ctypes.windll.user32.ShowWindow(bar, 5)\n"
    "    try:\n"
    "        os.remove(sys.argv[2])\n"
    "    except OSError:\n"
    "        pass\n")


def watchdog():
    """Starts the watchdog on her: a pythonw of its own, with no window, that outlives her."""
    exe = sys.executable
    if os.path.basename(exe).lower() == "python.exe":
        exe = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return subprocess.Popen([exe, "-c", WATCHDOG, str(os.getpid()), FLAG], close_fds=True,
                            creationflags=0x08000000 | 0x00000008,  # CREATE_NO_WINDOW, DETACHED_PROCESS
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def restore_leftover():
    """Her last run ended with the taskbar hidden and nothing put it back: it's shown again."""
    if os.path.exists(FLAG):
        show_taskbar()


# --------------------------------------------------------------------------- the dock's pictures
_panels = {}


def _panel(h, s, th):
    """The glass, as three parts to make any width from: its left end, one column of its middle and its right end,
    each (colours (h, w, 3), cover (h, w)), its shadow in the cover. h: the window's height; the glass sits at its
    bottom, MARGIN in."""
    key = (h, round(s, 4), repr(sorted(th.items())))
    hit = _panels.get(key)
    if hit is not None:
        return hit
    m, gh, r = MARGIN * s, (ICON + 2 * PAD) * s, 18 * s
    end = int(math.ceil(m + r)) + 1
    w = 2 * end + 3
    xs = np.arange(w, dtype=np.float32) + 0.5
    ys = (np.arange(h, dtype=np.float32) + 0.5)[:, None]
    x0, x1, y1 = m, w - m, h - m
    y0 = y1 - gh
    cx, cy, hw, hh = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    sd = face.rbox(xs, ys, cx, cy, hw, hh, r)
    cover = np.clip(0.5 - sd, 0.0, 1.0)
    shadow = th["shadow"] * np.clip(0.5 - face.rbox(xs, ys - 3 * s, cx, cy, hw, hh, r) / (11 * s), 0.0, 1.0) ** 2
    lw = max(1.0, s)
    e = np.clip(0.5 - (np.abs(sd + 0.5 * lw) - 0.5 * lw), 0.0, 1.0) * cover * th["line_a"]
    op = cover * th["fill"]
    col = np.empty((h, w, 3), np.float32)
    col[:] = th["body"]
    col *= op[..., None]
    col *= (1.0 - e)[..., None]
    col += np.asarray(th["line"], np.float32) * e[..., None]
    op = np.clip(op * (1.0 - e) + e, 0.0, 1.0)
    np.minimum(col, op[..., None], out=col)
    op = op + np.maximum(shadow - cover, 0.0) * (1.0 - op)
    parts = ((col[:, :end].copy(), op[:, :end].copy()), (col[:, end:end + 1].copy(), op[:, end:end + 1].copy()),
             (col[:, -end:].copy(), op[:, -end:].copy()))
    if len(_panels) > 8:
        _panels.clear()
    _panels[key] = parts
    return parts


def _start_icon(n, th):
    """Windows' four panes, n px, in the glass's ink, premultiplied (n, n, 4)."""
    col = np.zeros((n, n, 3), np.float32)
    op = np.zeros((n, n), np.float32)
    cv = face.Canvas(col, op=op)
    g, q = n * 0.06, n * 0.33
    for ix in (0, 1):
        for iy in (0, 1):
            cx = n / 2 + (ix - 0.5) * (q + g)
            cy = n / 2 + (iy - 0.5) * (q + g)
            cv.shape(lambda X, Y, cx=cx, cy=cy: face.rbox(X, Y, cx, cy, q / 2, q / 2, n * 0.04),
                     (cx - q, cy - q, cx + q, cy + q), (0.25, 0.55, 1.0), 1.0)
    return np.concatenate([col, op[..., None]], axis=2)


def _into(out, col, op):
    """Premultiplied colours (h, w, 3) and cover (h, w), 0 to 1, written into a window's blue, green, red, alpha
    bytes. No clamping: all that's drawn on the dock is premultiplied already, so nothing goes over its cover or 1."""
    tmp = np.empty(op.shape + (4,), np.float32)
    tmp[..., 0], tmp[..., 1], tmp[..., 2], tmp[..., 3] = col[..., 2], col[..., 1], col[..., 0], op
    tmp *= 255.0
    tmp += 0.5
    out[...] = tmp


def _search_icon(n, th):
    """A magnifying glass, n px, in the glass's ink, premultiplied (n, n, 4): a ring, and its handle down to the
    right, as Windows' search has it."""
    col = np.zeros((n, n, 3), np.float32)
    op = np.zeros((n, n), np.float32)
    cv = face.Canvas(col, op=op)
    w = n * 0.075  # the stroke
    cx = cy = n * 0.43
    r = n * 0.22

    def ring(X, Y):
        return np.abs(np.hypot(X - cx, Y - cy) - r) - w / 2

    ax = ay = cx + r * 0.72 + w * 0.3  # the handle, from the ring out at 45 degrees
    bx = by = n * 0.8

    def handle(X, Y):
        px, py = X - ax, Y - ay
        dx, dy = bx - ax, by - ay
        h = np.clip((px * dx + py * dy) / (dx * dx + dy * dy), 0.0, 1.0)
        return np.hypot(px - h * dx, py - h * dy) - w * 0.62

    cv.shape(ring, (0, 0, n, n), th["text"], 1.0)
    cv.shape(handle, (0, 0, n, n), th["text"], 1.0)
    return np.concatenate([col, op[..., None]], axis=2)


def _scaled(pic, n):
    """A picture fitted in n px square, averaged (island_art.resample): no OpenCV in her for it (30 October 2026,
    the owner: less RAM)."""
    import island_art as art
    h, w = pic.shape[:2]
    if (h, w) == (n, n):
        return pic
    f = n / max(h, w)
    out = art.resample(pic, max(1, round(h * f)), max(1, round(w * f)))
    if out.shape[:2] == (n, n):
        return out
    square = np.zeros((n, n, 4), np.float32)  # a wide one centred in its square
    y, x = (n - out.shape[0]) // 2, (n - out.shape[1]) // 2
    square[y:y + out.shape[0], x:x + out.shape[1]] = out
    return square


# --------------------------------------------------------------------------- the dock
class Dock:
    """The dock along the bottom of the screen: started by her window (assistant_ui) while Settings has it on,
    looked after on Tk's thread. reload() after a setting changed; close() when it's turned off or she quits."""

    def __init__(self, root):
        self.root = root
        self.k = root.winfo_fpixels("1i") / 96
        self.items = [dict(it) for it in FIRST]
        self.slots = slots(self.items)
        self.results = queue.Queue()
        self.dirty, self.reading, self.read_at = True, False, 0.0
        self.hover = bubble.Spring(0.0, 0.2, 1.0)  # how much it's grown for the pointer
        self.lift = bubble.Spring(0.0, 0.3, 0.86)  # 0 down out of sight, 1 up
        self.px = None  # the pointer along the row while it's on the dock
        self.summoned, self.away, self.edge_at = False, 0.0, None
        self.full, self.full_at = False, 0.0
        self.front = None
        self.turns = {}
        self.press = self.dragging = None
        self.closed = False
        self.shown = False
        self.box = None  # the part of its picture drawn last
        self.texts = {}
        self.icons = {}  # (key, px): the icon at that size, kept while it's at rest
        self.replacing, self.dog, self.checked = False, None, 0.0
        self.known, self.span, self.redraw = set(), None, False
        self.job = None
        self.hooks, self.proc = [], WINEVENTPROC(self._event)
        self._build()
        for lo, hi in EVENTS:  # out of context, never her own windows: the callback runs on this thread
            h = _user32.SetWinEventHook(lo, hi, None, self.proc, 0, 0, 0x0002)
            if h:
                self.hooks.append(h)
        self.reload()
        self.last = time.monotonic()
        self._poll()

    # ---------------------------------------------------------------- its window
    def _build(self):
        self.top = tk.Toplevel(self.root)
        self.top.withdraw()
        self.top.overrideredirect(True)
        self.top.geometry("10x10+-20000+-20000")
        self.top.deiconify()
        self.top.update_idletasks()
        self.hwnd = win.root_hwnd(self.top.winfo_id())
        win.make_overlay(self.hwnd)
        win.NO_CAPTURE.append(self.hwnd)
        edges.prime(self.hwnd)  # before it's hidden, or Windows turns down its pictures
        win.hide_window(self.hwnd)
        self.dc = bubble._new_dc(None)
        self.bitmap = self.old = self.buf = None
        self.size = (0, 0)
        for seq, fn in (("<ButtonPress-1>", self._down), ("<B1-Motion>", self._move),
                        ("<ButtonRelease-1>", self._up), ("<ButtonRelease-2>", self._middle),
                        ("<ButtonRelease-3>", self._right)):
            self.top.bind(seq, lambda e, fn=fn: fn())

    def _text(self, px, weight):
        key = (px, weight)
        if key not in self.texts:
            self.texts[key] = bubble.Text(px, weight)
        return self.texts[key]

    def reload(self):
        """Settings read again: the taskbar hidden or back, and where it sits."""
        want = bool(settings.get("dock_replace_taskbar"))
        if want and not self.replacing:
            self.replacing = True
            hide_taskbar()
            try:
                self.dog = watchdog()
            except OSError as exc:
                print(f"  dock: no watchdog ({exc!r})")
        elif not want and self.replacing:
            self.replacing = False
            show_taskbar()
        self.dirty = True
        self.box = None
        self._place()

    def close(self):
        self.closed = True
        if self.job is not None:
            self.root.after_cancel(self.job)
        for h in self.hooks:
            _user32.UnhookWinEvent(h)
        self.hooks = []
        if self.replacing:
            self.replacing = False
            show_taskbar()
        if self.dog is not None and self.dog.poll() is None:
            self.dog.kill()  # its work's done: the taskbar's back
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

    def _screen(self):
        """(the primary screen's box, its work area), real px."""
        info = win.MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        mon = _user32.MonitorFromPoint(wt.POINT(0, 0), 1)  # MONITOR_DEFAULTTOPRIMARY
        if not mon or not _user32.GetMonitorInfoW(mon, ctypes.byref(info)):
            area = win.work_area()
            return area, area
        m, w = info.rcMonitor, info.rcWork
        return (m.left, m.top, m.right, m.bottom), (w.left, w.top, w.right, w.bottom)

    def _place(self):
        """Its size and where it sits: in the taskbar's strip at the bottom while it hides the taskbar, sized to fit
        it, else just over the bottom of the work area."""
        screen, work = self._screen()
        strip = screen[3] - work[3]
        self.s = self.k
        if self.replacing and strip > 0:
            self.s = min(self.k, max(0.5 * self.k, (strip - 4) / (ICON + 2 * PAD)))
        s = self.s
        kinds = [kind for kind, _ in self.slots]
        rest = at_rest(kinds, s)
        extra = (MAG - 1) * SLOT * s * 2 * REACH
        w = int(math.ceil(rest + 2 * extra + 2 * MARGIN * s))
        h = int(math.ceil((MARGIN + LABEL + 6 + LIFT + ICON * MAG + PAD + MARGIN) * s))
        glass_h = (ICON + 2 * PAD) * s
        bottom = screen[3] - (strip - glass_h) / 2 if self.replacing and strip > 0 else work[3] - BOTTOM * self.k
        self.x = int(round((screen[0] + screen[2]) / 2 - w / 2))
        self.y = int(round(bottom + MARGIN * s - h))
        self.row_x = self.x + (w - rest) / 2  # the glass's left end at rest, on the screen
        self.rest = rest
        self.glass = (self.row_x, bottom - glass_h, self.row_x + rest, bottom)
        self.screen = screen
        self._canvas(w, h)

    def _canvas(self, w, h):
        """Its picture w by h px, made again only when that changes."""
        if (w, h) != self.size:
            if self.bitmap is not None:
                bubble._select(self.dc, self.old)
                bubble._delete(self.bitmap)
            self.bitmap, self.buf = bubble._dib(self.dc, w, h)
            self.old = bubble._select(self.dc, self.bitmap)
            self.size = (w, h)
            self.col = np.zeros((h, w, 3), np.float32)
            self.op = np.zeros((h, w), np.float32)
            self.box = None

    # ---------------------------------------------------------------- what's on it
    def _event(self, hook, event, hwnd, obj, child, thread, when):
        """Windows' word that a window changed (on Tk's thread): read again soon if it's an app's own."""
        if obj != 0 or child != 0 or not hwnd or self.dirty:
            return
        # one of its own gone, hidden, minimised or back; or an app's window shown or uncloaked: not every tooltip
        # and menu of every app, which had it read the windows again and again (30 October 2026)
        if hwnd in self.known or (event in (0x8002, 0x8018) and _user32.GetAncestor(hwnd, 2) == hwnd and
                                  win._is_app_window(hwnd)):
            self.dirty = True

    def _read(self, pinned_now, size):
        try:
            self.results.put(("items", read(pinned_now, size)))
        except Exception as exc:
            print(f"  dock: {exc!r}")
            self.results.put(("failed",))

    def _take(self, now):
        try:
            while True:
                got = self.results.get_nowait()
                self.reading = False
                if got[0] == "items" and self.dragging is None:
                    old = [kind for kind, _ in self.slots]
                    self.items = got[1]
                    self.slots = slots(self.items)
                    self.known = {h for it in self.items for h in it["windows"]}
                    self.icons = {key: pic for key, pic in self.icons.items() if key[0] in ("start", "search")}
                    if [kind for kind, _ in self.slots] != old:
                        self._place()
                    self.box = None
                    self.redraw = True
        except queue.Empty:
            pass
        if (self.dirty or now - self.read_at > 10.0) and not self.reading and now - self.read_at > 0.3:
            self.dirty, self.reading, self.read_at = False, True, now
            size = int(round(ICON * MAG * self.k))
            threading.Thread(target=self._read, args=(pins(), size), name="harry-dock", daemon=True).start()

    # ---------------------------------------------------------------- the loop
    def _poll(self):
        self.job = None
        if self.closed:
            return
        now = time.monotonic()
        dt = min(0.05, now - self.last)
        self.last = now
        self.redraw = False
        self._take(now)
        if self._ticking(now):
            self.redraw = True
        if now - self.full_at > 2.0:
            self.full_at = now
            state = ctypes.c_int()
            try:
                ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state))
                self.full = state.value in (2, 3, 4, 7)  # a game, presenting, a full-screen app
            except Exception:
                self.full = False
            if self.replacing and now - self.checked > 2.0:  # Explorer started again, or the Start menu showed it
                self.checked = now
                hide_taskbar()
        px, py = win.cursor_pos()
        gx0, gy0, gx1, gy1 = self.glass
        sx0, sx1 = self.span or (gx0, gx1)  # as wide as it's grown
        on_row = self.lift.x > 0.5 and sx0 - 6 * self.s <= px <= sx1 + 6 * self.s and \
            gy0 - self._reach() <= py <= self.screen[3]
        at_edge = py >= self.screen[3] - 2 and gx0 <= px <= gx1
        self.edge_at = (self.edge_at or now) if at_edge else None
        if on_row or self.dragging is not None or (self.edge_at and now - self.edge_at >= SHOW_AFTER):
            self.summoned, self.away = True, now
        elif self.summoned and now - self.away > HIDE_AFTER:
            self.summoned = False
        front = _user32.GetForegroundWindow()
        if front != self.front:
            self.front, self.redraw = front, True
        mode = settings.get("dock_mode")
        mode = mode if mode in MODES else "smart"
        overlapped = mode == "smart" and self._overlapped(front)
        self.lift.go(1.0 if up(mode, self.full, overlapped, self.summoned) else 0.0)
        self.lift.step(dt)
        self.hover.go(1.0 if on_row else 0.0)
        self.hover.step(dt)
        new_px = (px - self.row_x) if on_row else self.px
        if on_row and new_px != self.px:
            self.redraw = True
        self.px = new_px if self.hover.x > 0.002 or on_row else None
        moving = not self.lift.resting(0.002) or not self.hover.resting(0.002) or self.dragging is not None
        if self.lift.x > 0.002 or self.shown:
            if moving or self.redraw or not self.shown:
                self._draw()
            if self.shown:
                win.set_click_through(self.hwnd, not on_row)
        near = py >= self.screen[3] - (ICON * MAG + 60) * self.s
        self.job = self.root.after(int(1000 * (LIVE if moving or on_row else POLL if near else POLL_FAR)),
                                   self._poll)

    def _reach(self):
        """How far over its glass the pointer is still on it, px: as far as the icons have grown and risen."""
        return (self.hover.x * (MAG - 1) * ICON + LIFT) * self.s

    def _ticking(self, now):
        """True if something on it changed by itself and it's to be drawn again: nothing on the dock does."""
        return False

    def _overlapped(self, front):
        """True if the window in front is over where the dock sits (not minimised, not the desktop)."""
        if not front or front == self.hwnd or _user32.IsIconic(front):
            return False
        r = wt.RECT()
        if not _user32.GetWindowRect(front, ctypes.byref(r)):
            return False
        if r.right - r.left >= self.screen[2] - self.screen[0] and r.bottom - r.top >= self.screen[3] - \
                self.screen[1] and win._class_name(front) in ("Progman", "WorkerW"):
            return False
        gx0, gy0, gx1, gy1 = self.glass
        return r.left < gx1 and r.right > gx0 and r.top < gy1 and r.bottom > gy0 + 4 * self.s

    # ---------------------------------------------------------------- its picture
    def layout(self):
        """(the slots as row gives them, the glass's left and right along the row)."""
        return row([kind for kind, _ in self.slots], self.px, self.hover.x, self.s)

    def _draw(self):
        s, (w, h) = self.s, self.size
        th = edges.glass()
        places, x0, x1 = self.layout()
        off = self.row_x - self.x  # the row's 0 in the window
        gy1 = h - MARGIN * s
        self.span = (self.row_x + x0, self.row_x + x1)
        reach = (MARGIN + 70) * s  # the glass's shadow, and a long name's pill over an icon at an end
        box = (max(0, int(math.floor(off + x0 - reach))), min(w, int(math.ceil(off + x1 + reach))))
        drawn = box if self.box is None else (min(box[0], self.box[0]), max(box[1], self.box[1]))
        if self.box is None:
            drawn = (0, w)
        a, b = drawn
        col, op = self.col, self.op
        left, mid, right = _panel(h, s, th)
        X0, X1 = int(round(off + x0 - MARGIN * s)), int(round(off + x1 + MARGIN * s))
        lw = left[0].shape[1]
        X0, X1 = max(0, X0), min(w, max(X1, X0 + 2 * lw + 1))
        a, b = min(a, X0), max(b, X1)
        col[:, a:X0], op[:, a:X0] = 0.0, 0.0  # cleared either side of the glass: the glass is drawn whole over its own
        col[:, X1:b], op[:, X1:b] = 0.0, 0.0
        col[:, X0:X0 + lw], op[:, X0:X0 + lw] = left
        col[:, X0 + lw:X1 - lw], op[:, X0 + lw:X1 - lw] = mid[0], mid[1]
        col[:, X1 - lw:X1], op[:, X1 - lw:X1] = right
        cv = face.Canvas(col, op=op)
        hovered = self._under(places) if self.px is not None and self.hover.x > 0.5 else None
        ink = th["text"]
        for (kind, i), (middle, grow) in zip(self.slots, places):
            cx = off + middle
            if kind == "gap":
                cv.shape(lambda X, Y, cx=cx: face.rbox(X, Y, cx, gy1 - (ICON / 2 + PAD) * s, 0.5 * max(1.0, s),
                                                       ICON * 0.36 * s, 0.5 * max(1.0, s)),
                         (cx - 2, gy1 - (ICON + PAD) * s, cx + 2, gy1 - PAD * s), ink, 0.14)
                continue
            it = self.items[i]
            n = max(4, int(round(ICON * s * grow)))
            rise = LIFT * s * (grow - 1) / (MAG - 1)
            bottom = gy1 - PAD * s - rise
            pic = self._icon(it, n, th)
            cv.image(pic, cx - n / 2, bottom - n, 0.55 if self.dragging == it["key"] else 1.0)
            if it["windows"]:  # a dot under one that's open, longer under the one in front
                wide = 4.5 * s if self.front in it["windows"] else 0.0
                r = 1.9 * s
                y = gy1 - PAD * s * 0.42
                cv.shape(lambda X, Y, cx=cx, y=y, r=r, wide=wide: face.rbox(X, Y, cx, y, r + wide, r, r),
                         (cx - r - wide - 2, y - r - 2, cx + r + wide + 2, y + r + 2), ink, 0.75)
            if hovered == i and self.dragging is None:
                self._label(cv, it["name"], cx, bottom - n - 6 * s, th)
        self.box = box
        _into(self.buf[:, a:b], col[:, a:b], op[:, a:b])
        bubble._flush()
        slide = (1.0 - min(1.0, max(0.0, self.lift.x))) * (h - (MARGIN + LABEL) * s)
        y = int(round(self.y + slide))
        alpha = max(0, min(255, int(round(255 * min(1.0, max(0.0, self.lift.x) * 1.4)))))
        if alpha <= 0:
            if self.shown:
                win.hide_window(self.hwnd)
                self.shown = False
            return
        if not self.shown:
            win.show_no_activate(self.hwnd, self.x, y, w, h)
            self.shown = True
        origin, size, src = wt.POINT(self.x, y), wt.SIZE(w, h), wt.POINT(0, 0)
        bubble._ULW(self.hwnd, None, ctypes.byref(origin), ctypes.byref(size), self.dc, ctypes.byref(src), 0,
                    ctypes.byref(bubble._BLEND(0, 0, alpha, 1)), 2)

    def _icon(self, it, n, th):
        """An item's icon n px: its own, else the first letter of its name on its colour (Start: Windows' panes)."""
        key = (it["key"], n)
        hit = self.icons.get(key)
        if hit is not None:
            return hit
        pic = it.get("icon")
        if it["kind"] in ("start", "search"):  # drawn here, the search glass in the glass's own ink
            own = (it["kind"], 0 if it["kind"] == "start" else repr(th["text"]))
            pic = self.icons.get(own)
            if pic is None:
                draw = _start_icon if it["kind"] == "start" else _search_icon
                pic = self.icons[own] = draw(int(round(ICON * MAG * self.k)), th)
        if pic is None:
            import island_art as art
            pic = art.badge(it["name"], n, lambda px: self._text(px, 600))
        pic = _scaled(np.ascontiguousarray(pic, np.float32), n)
        if self.hover.resting(0.002):  # kept only at rest: growing, each size is used once
            if len(self.icons) > 96:
                self.icons.clear()
            self.icons[key] = pic
        return pic

    def _label(self, cv, words, cx, bottom, th):
        """The name of the one pointed at, on a pill of the glass over it."""
        t = self._text(round(12 * self.s), 600)
        cover = t.render(words[:40])
        tw, s = cover.shape[1], self.s
        pw, ph = tw + 20 * s, LABEL * s
        y0 = bottom - ph
        cv.shape(lambda X, Y: face.rbox(X, Y, cx, y0 + ph / 2, pw / 2, ph / 2, ph / 2),
                 (cx - pw / 2 - 1, y0 - 1, cx + pw / 2 + 1, bottom + 1), th["body"], th["fill"])
        cv.text(cover, cx - tw / 2, y0 + (ph - cover.shape[0]) / 2, th["text"], 1.0)

    def _under(self, places):
        """The item under the pointer (its index), or None."""
        if self.px is None:
            return None
        for (kind, i), (middle, grow) in zip(self.slots, places):
            half = (SLOT if kind == "icon" else GAP_W) * self.s * grow / 2
            if kind == "icon" and middle - half <= self.px < middle + half:
                return i
        return None

    # ---------------------------------------------------------------- clicks
    @staticmethod
    def busy():
        return edges.Edges.busy()

    def _hit(self):
        places, _, _ = self.layout()
        return self._under(places)

    def _down(self):
        i = self._hit()
        self.press = (i, win.cursor_pos()[0]) if i is not None else None

    def _move(self):
        if self.press is None or self.busy():
            return
        i, x0 = self.press
        it = self.items[i] if i is not None and i < len(self.items) else None
        if it is None or it["kind"] != "pin":
            return
        x = win.cursor_pos()[0]
        if self.dragging is None and abs(x - x0) < 6 * self.s:
            return
        self.dragging = it["key"]
        places, _, _ = self.layout()
        here = self.px if self.px is not None else x - self.row_x
        pins_at = [(j, places[n][0]) for n, (kind, j) in enumerate(self.slots) if kind == "icon" and
                   self.items[j]["kind"] == "pin"]
        if not pins_at:
            return
        target = min(pins_at, key=lambda p: abs(p[1] - here))[0]
        now = next(j for j, item in enumerate(self.items) if item["key"] == self.dragging)
        if target != now:
            moved = self.items.pop(now)
            self.items.insert(target, moved)
            self.slots = slots(self.items)
            self.redraw = True

    def _up(self):
        press, self.press = self.press, None
        if self.dragging is not None:
            self.dragging = None
            settings.put("dock_pins", pinned(self.items))
            self.dirty = True
            return
        i = self._hit()
        if press is None or i is None or press[0] != i or self.busy():
            return
        it = self.items[i]
        if it["kind"] == "folder":
            self._open(it["path"])
            return
        turn = self.turns.get(it["key"], 0)
        what = action(it, self.front, turn)
        if what is None:
            return
        if what[0] == "start":
            self._start_menu()
        elif what[0] == "search":
            self._search()
        elif what[0] == "open":
            self._open(what[1])
        elif what[0] == "front":
            self.turns[it["key"]] = turn + 1
            win.bring_to_front(what[1])
        elif what[0] == "down":
            _user32.ShowWindow(what[1], SW_MINIMIZE)
        self.dirty = True

    def _middle(self):
        i = self._hit()
        if i is not None and not self.busy() and self.items[i].get("path") and not self.items[i].get("her"):
            self._open(self.items[i]["path"])

    def _right(self):
        i = self._hit()
        if i is None or self.busy():
            return
        it = self.items[i]
        paths = {p["path"].lower() for p in pins()}
        m = tk.Menu(self.top, tearoff=0)
        for label, what in menu(it, paths):
            if what is None:
                m.add_command(label=label, state="disabled")
                m.add_separator()
            else:
                m.add_command(label=label, command=lambda w=what, it=it: self._do(w, it))
        px, py = win.cursor_pos()
        try:
            m.tk_popup(int(px), int(py))
        finally:
            m.grab_release()

    def _do(self, what, it):
        """A pick from the right-click menu."""
        if self.busy():
            return
        kept = pins()
        if what in ("open", "new"):
            if it["kind"] == "start":
                self._start_menu()
            elif it["kind"] == "search":
                self._search()
            else:
                self._open(it["path"])
        elif what == "pin":
            kept.append({"path": it.get("exe") or it["path"], "name": it["name"]})
            settings.put("dock_pins", kept)
        elif what == "unpin":
            gone = {it["path"].lower(), (it.get("exe") or "").lower()}
            settings.put("dock_pins", [p for p in kept if p["path"].lower() not in gone])
        elif what == "close":  # asked to close, as its own X would: it asks about anything unsaved
            for hwnd in it["windows"]:
                _user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        self.dirty = True

    @staticmethod
    def _open(path):
        """An app, shortcut or folder opened as a double-click would, off Tk's thread: Windows can take a while."""
        def go():
            try:
                os.startfile(path)
            except OSError as exc:
                print(f"  dock: couldn't open {path!r}: {exc!r}")
        threading.Thread(target=go, name="harry-dock-open", daemon=True).start()

    @staticmethod
    def _start_menu():
        """Windows' Start menu, as the Windows key opens it."""
        _user32.keybd_event(0x5B, 0, 0, 0)  # VK_LWIN
        _user32.keybd_event(0x5B, 0, 2, 0)  # KEYEVENTF_KEYUP

    @staticmethod
    def _search():
        """Windows' own search, as Windows+S opens it: type and your apps come up first, then files and settings."""
        _user32.keybd_event(0x5B, 0, 0, 0)  # VK_LWIN
        _user32.keybd_event(0x53, 0, 0, 0)  # S
        _user32.keybd_event(0x53, 0, 2, 0)
        _user32.keybd_event(0x5B, 0, 2, 0)


# --------------------------------------------------------------------------- the taskbar (7 November 2026)
# The owner's ask after NotchPixel's (notchpixel.com, "A taskbar, if you want one"): a notch along the bottom of the
# screen in place of Windows' taskbar, in her island's colours, hanging from the bottom edge as her island hangs from
# the top one. Start, search and your apps, which don't grow; a soft square under the one pointed at and its name on a
# pill over it; and at its right the network and the volume (Windows' quick settings), the time and the date, and the
# bell (Windows' notifications and its calendar). dock_style picks it or the dock that grows.
STYLES = ("taskbar", "dock")
BAR_H, BAR_ICON, BAR_SLOT, BAR_GAP = 46, 24, 40, 13  # logical px: its height, an icon, one to the next, a divider
BAR_PAD, BAR_R, BAR_FLARE, BAR_M = 6, 12, 10, 14  # logical px: round its ends, its corners, its shoulders, its shadow
TRAY = ("quick", "clock", "bell")  # what's at its right, after a divider (bar_cells)
TRAY_W = {"sep": BAR_GAP, "quick": 62, "bell": 38}  # their widths; the clock's is its words' and 20 more
_kernel32 = ctypes.WinDLL("kernel32")
_kernel32.GetTimeFormatEx.argtypes = [wt.LPCWSTR, wt.DWORD, ctypes.c_void_p, wt.LPCWSTR, wt.LPWSTR, ctypes.c_int]
_kernel32.GetDateFormatEx.argtypes = [wt.LPCWSTR, wt.DWORD, ctypes.c_void_p, wt.LPCWSTR, wt.LPWSTR, ctypes.c_int,
                                      wt.LPCWSTR]


def make(root):
    """Her dock as Settings has it (dock_style): the taskbar, NotchPixel's, or the dock that grows, a Mac's."""
    return Dock(root) if settings.get("dock_style") == "dock" else Taskbar(root)


def bar_cells(kinds, clock_w, s):
    """The taskbar's cells left to right, ([(what, x0, x1)], its width), in px from its left end: what is the slot's
    index for each of kinds ("icon" or "gap", as slots gives them), then "sep", a divider, and the tray's (TRAY).
    clock_w: the time and the date's width."""
    cells, x = [], BAR_PAD * s
    for i, kind in enumerate(kinds):
        w = (BAR_SLOT if kind == "icon" else BAR_GAP) * s
        cells.append((i, x, x + w))
        x += w
    for what in ("sep",) + TRAY:
        w = (clock_w + 20 * s) if what == "clock" else TRAY_W[what] * s
        cells.append((what, x, x + w))
        x += w
    return cells, x + BAR_PAD * s


def bar_shape(xs, ys, x0, x1, top, bottom, r, f, flush):
    """The taskbar's outline as signed distances: its top corners round (r); flush with the bottom of the screen,
    square where it meets it, each side curving out into it over f px, her island's notch upside down
    (island._drop), and nothing below bottom; else round all round."""
    cx, hw = (x0 + x1) / 2, (x1 - x0) / 2
    if not flush:
        return face.rbox(xs, ys, cx, (top + bottom) / 2, hw, (bottom - top) / 2, r)
    body = face.rbox(xs, ys, cx, (top + bottom + r) / 2, hw, (bottom - top + r) / 2, r)  # its bottom corners below
    for corner in ((x0 - f, x1 + f) if f > 0 else ()):
        side = np.maximum(face.rbox(xs, ys, x0 if corner < x0 else x1, bottom - f / 2, f, f / 2, 0.0),
                          -face.circle(xs, ys, corner, bottom - f, f))
        body = np.minimum(body, side)
    return np.maximum(body, ys - bottom)


def clock_words():
    """The time, the date, and the date in full, as Windows writes them in your own formats: ("12:58",
    "07-11-2026", "Saturday, 7 November 2026")."""
    out = []
    for call, flags in ((_kernel32.GetTimeFormatEx, 0x2), (_kernel32.GetDateFormatEx, 0x1),
                        (_kernel32.GetDateFormatEx, 0x2)):  # TIME_NOSECONDS, DATE_SHORTDATE, DATE_LONGDATE
        buf = ctypes.create_unicode_buffer(80)
        args = (None, flags, None, None, buf, 80) + ((None,) if call is _kernel32.GetDateFormatEx else ())
        out.append(buf.value if call(*args) else "")
    if not all(out):
        out = [time.strftime("%H:%M"), time.strftime("%d-%m-%Y"), time.strftime("%A, %d %B %Y")]
    return tuple(out)


def tray_state():
    """What the taskbar's tray shows: {"net": "wifi", "wired" or None, "volume": 0 to 100 or None, "muted"}. Read
    off Tk's thread (the volume's a COM call), and never online: only the adapters that are up and have an address."""
    out = {"net": None, "volume": None, "muted": False}
    try:
        import psutil
        stats, addrs = psutil.net_if_stats(), psutil.net_if_addrs()
        for name, st in stats.items():
            if not st.isup or re.search(r"loopback|vethernet|virtual|vmware|vbox|bluetooth", name, re.I):
                continue
            if not any(a.family == socket.AF_INET and not a.address.startswith(("127.", "169.254."))
                       for a in addrs.get(name, ())):
                continue
            if re.search(r"wi-?fi|wlan|wireless", name, re.I):
                out["net"] = "wifi"
                break
            out["net"] = "wired"
    except Exception:
        pass
    try:
        out["volume"] = win.volume()
        out["muted"] = bool(win._endpoint().GetMute())
    except Exception:
        pass
    return out


def tray_keys(what, build=None):
    """The keys that open what a tray part is for: Windows+A, quick settings, for the network and the volume;
    Windows+N, the notifications and the calendar, for the time and the bell (Windows 10 has them in Windows+A)."""
    build = sys.getwindowsversion().build if build is None else build
    return (0x5B, 0x41) if what == "quick" or build < 22000 else (0x5B, 0x4E)


def _wired_glyph(cv, cx, cy, s, colour, a=1.0):
    """A network cable's plug, s px: a box with its three pins and a lead down."""
    w, h = s * 0.62, s * 0.46
    lw = max(1.0, s * 0.09)
    cv.shape(lambda X, Y: np.abs(face.rbox(X, Y, cx, cy - s * 0.08, w / 2, h / 2, s * 0.08)) - lw / 2,
             (cx - w, cy - s * 0.5, cx + w, cy + s * 0.3), colour, a)
    for dx in (-0.16, 0.0, 0.16):
        px = cx + dx * s
        cv.shape(lambda X, Y, px=px: face.rbox(X, Y, px, cy - s * 0.08, lw / 2, h * 0.22, lw / 2),
                 (px - lw, cy - s * 0.3, px + lw, cy + s * 0.1), colour, a)
    cv.shape(lambda X, Y: face.rbox(X, Y, cx, cy + s * 0.3, lw / 2, s * 0.15, lw / 2),
             (cx - lw, cy + s * 0.1, cx + lw, cy + s * 0.5), colour, a)


class Taskbar(Dock):
    """The taskbar along the bottom of the screen, as NotchPixel's: a Dock, with its windows, pins, clicks, hiding
    and Windows' own taskbar put away, drawn as a bar whose icons don't grow, with the tray at its right."""

    def __init__(self, root):
        self.flush = False
        self.tray, self.tray_q, self.tray_at, self.tray_reading = {"net": None, "volume": None, "muted": False}, \
            queue.Queue(), 0.0, False
        self.minute, self.clock = None, clock_words()
        self.cells, self.bar_w, self.clock_w = [], 0.0, 0.0
        self.bar_pic = None  # (what it was drawn for, its colours, its cover): the glass, kept
        super().__init__(root)

    def _place(self):
        """Its size and where it sits: flush with the bottom of the screen in the taskbar's strip while it hides
        Windows' taskbar, as tall as the strip has room for, else just over the bottom of the work area."""
        screen, work = self._screen()
        strip = screen[3] - work[3]
        k = self.k
        self.flush = self.replacing and strip > 0
        self.s = s = min(k, max(0.6 * k, strip / BAR_H)) if self.flush else k
        self.clock_w = max(self._text(round(12 * s), 600).render(self.clock[0]).shape[1],
                           self._text(round(11 * s), 500).render(self.clock[1]).shape[1])
        self.cells, self.bar_w = bar_cells([kind for kind, _ in self.slots], self.clock_w, s)
        m, bar_h = BAR_M * s, BAR_H * s
        w = int(math.ceil(self.bar_w + 2 * (BAR_FLARE * s + m)))
        h = int(math.ceil((LABEL + 12) * s + bar_h + (0 if self.flush else m)))
        bottom = screen[3] if self.flush else work[3] - BOTTOM * k
        self.x = int(round((screen[0] + screen[2]) / 2 - w / 2))
        self.y = int(round(bottom + (0 if self.flush else m) - h))
        self.row_x = self.x + (w - self.bar_w) / 2
        self.rest = self.bar_w
        self.glass = (self.row_x, bottom - bar_h, self.row_x + self.bar_w, bottom)
        self.screen = screen
        self.bar_pic = None
        self._canvas(w, h)

    def layout(self):
        """(each slot's middle and how much it's grown, never, the bar's left and right), as the dock's."""
        return [((x0 + x1) / 2, 1.0) for what, x0, x1 in self.cells if not isinstance(what, str)], 0.0, self.bar_w

    def _reach(self):
        return 0.0  # nothing grows over it: a click just over it is the window's under it

    def _cell(self):
        """What's under the pointer: an item's index, one of TRAY, or None."""
        if self.px is None:
            return None
        for what, x0, x1 in self.cells:
            if x0 <= self.px < x1:
                if isinstance(what, str):
                    return what if what in TRAY else None
                kind, i = self.slots[what]
                return i if kind == "icon" else None
        return None

    def _under(self, places):
        return self._cell()

    def _hit(self):
        return self._cell()

    def _ticking(self, now):
        """The clock each minute (and the bar made wider if its words grew), and the tray read every 3 seconds."""
        changed = False
        minute = time.localtime().tm_min
        if minute != self.minute:
            self.minute = minute
            words = clock_words()
            if words != self.clock:
                self.clock, changed = words, True
                width = self.clock_w
                self._place()
                if abs(self.clock_w - width) > 1:
                    self.box = None
        try:
            while True:
                got = self.tray_q.get_nowait()
                self.tray_reading = False
                if got != self.tray:
                    self.tray, changed = got, True
        except queue.Empty:
            pass
        if now - self.tray_at > 3.0 and not self.tray_reading:
            self.tray_at, self.tray_reading = now, True
            threading.Thread(target=lambda: self.tray_q.put(tray_state()), name="harry-taskbar-tray",
                             daemon=True).start()
        return changed

    # ---------------------------------------------------------------- its picture
    def _glass_picture(self, th, bx0, by0, by1):
        """The bar's glass, (colours, cover), for the whole window: its shadow round it, from the bar alone and not
        its shoulders, and its hairline, never along the bottom of the screen it hangs from."""
        s, (w, h) = self.s, self.size
        xs = np.arange(w, dtype=np.float32) + 0.5
        ys = (np.arange(h, dtype=np.float32) + 0.5)[:, None]
        bx1 = bx0 + self.bar_w
        sd = bar_shape(xs, ys, bx0, bx1, by0, by1, BAR_R * s, BAR_FLARE * s, self.flush)
        far = bar_shape(xs, ys + 2 * s, bx0, bx1, by0, by1, BAR_R * s, 0.0, self.flush)
        cover = np.clip(0.5 - sd, 0.0, 1.0)
        shadow = th["shadow"] * np.clip(0.5 - far / (10 * s), 0.0, 1.0) ** 2
        lw = max(1.0, s)
        e = np.clip(0.5 - (np.abs(sd + 0.5 * lw) - 0.5 * lw), 0.0, 1.0) * cover * th["line_a"]
        if self.flush:
            e = e * np.clip((by1 - lw - ys) / lw, 0.0, 1.0)
        op = cover * th["fill"]
        col = np.empty((h, w, 3), np.float32)
        col[:] = th["body"]
        col *= op[..., None]
        col *= (1.0 - e)[..., None]
        col += np.asarray(th["line"], np.float32) * e[..., None]
        op = np.clip(op * (1.0 - e) + e, 0.0, 1.0)
        np.minimum(col, op[..., None], out=col)
        op = op + np.maximum(shadow - cover, 0.0) * (1.0 - op)
        return col, op

    def _draw(self):
        s, (w, h) = self.s, self.size
        th = edges.glass()
        bx0 = self.row_x - self.x  # the bar's left end in the window
        bar_h = self.glass[3] - self.glass[1]
        by1 = h - (0 if self.flush else BAR_M * s)
        by0, cy = by1 - bar_h, by1 - bar_h / 2
        key = (w, h, round(bx0, 2), round(by0, 2), self.flush, repr(sorted(th.items())))
        if self.bar_pic is None or self.bar_pic[0] != key:
            self.bar_pic = (key,) + self._glass_picture(th, bx0, by0, by1)
        col, op = self.col, self.op
        col[:], op[:] = self.bar_pic[1], self.bar_pic[2]
        cv = face.Canvas(col, op=op)
        ink = th["text"]
        under = self._cell() if self.hover.x > 0.02 and self.dragging is None else None
        n = max(4, int(round(BAR_ICON * s)))
        tip = None
        for what, x0, x1 in self.cells:
            cx = bx0 + (x0 + x1) / 2
            if what == "sep" or (not isinstance(what, str) and self.slots[what][0] == "gap"):
                cv.shape(lambda X, Y, cx=cx: face.rbox(X, Y, cx, cy, 0.5 * max(1.0, s), bar_h * 0.2, 0.5 * max(1.0, s)),
                         (cx - 2, cy - bar_h / 2, cx + 2, cy + bar_h / 2), ink, 0.16)
                continue
            me = what if isinstance(what, str) else self.slots[what][1]
            if me == under:  # the soft square under the one pointed at
                hw, hh = (x1 - x0) / 2 - 2 * s, bar_h / 2 - 5 * s
                cv.shape(lambda X, Y, cx=cx, hw=hw, hh=hh: face.rbox(X, Y, cx, cy, hw, hh, 8 * s),
                         (cx - hw - 1, cy - hh - 1, cx + hw + 1, cy + hh + 1), ink, 0.1 * min(1.0, self.hover.x * 1.5))
                tip = (me, cx)
            if isinstance(what, str):
                self._tray_part(cv, what, cx, cy, th)
                continue
            it = self.items[me]
            cv.image(self._icon(it, n, th), cx - n / 2, cy - n / 2, 0.55 if self.dragging == it["key"] else 1.0)
            if it["windows"]:  # a dot under one that's open, longer under the one in front
                wide = 3.5 * s if self.front in it["windows"] else 0.0
                r, y = 1.6 * s, by1 - 4.5 * s
                cv.shape(lambda X, Y, cx=cx, y=y, r=r, wide=wide: face.rbox(X, Y, cx, y, r + wide, r, r),
                         (cx - r - wide - 2, y - r - 2, cx + r + wide + 2, y + r + 2), ink, 0.6)
        if tip is not None and self.hover.x > 0.5:
            me, cx = tip
            words = self.items[me]["name"] if isinstance(me, int) else self._tray_name(me)
            self._tip(cv, words, cx, by0 - 6 * s, th)
        _into(self.buf, col, op)
        bubble._flush()
        slide = (1.0 - min(1.0, max(0.0, self.lift.x))) * (bar_h + (0 if self.flush else BAR_M * s))
        y = int(round(self.y + slide))
        alpha = max(0, min(255, int(round(255 * min(1.0, max(0.0, self.lift.x) * 1.4)))))
        if alpha <= 0:
            if self.shown:
                win.hide_window(self.hwnd)
                self.shown = False
            return
        if not self.shown:
            win.show_no_activate(self.hwnd, self.x, y, w, h)
            self.shown = True
        origin, size, src = wt.POINT(self.x, y), wt.SIZE(w, h), wt.POINT(0, 0)
        bubble._ULW(self.hwnd, None, ctypes.byref(origin), ctypes.byref(size), self.dc, ctypes.byref(src), 0,
                    ctypes.byref(bubble._BLEND(0, 0, alpha, 1)), 2)

    def _tray_part(self, cv, what, cx, cy, th):
        """One of the tray's parts at cx: the network and the volume as they are, the time over the date, the bell."""
        s, ink = self.s, th["text"]
        if what == "quick":
            net, x = self.tray["net"], cx - 12 * s
            if net == "wired":
                _wired_glyph(cv, x, cy, 16 * s, ink)
            else:  # Wi-Fi, faint while there's no network at all
                face.wifi_glyph(cv, x, cy, 16 * s, ink, 1.0 if net else 0.35)
            vol = self.tray["volume"]
            face.speaker_glyph(cv, cx + 12 * s, cy, 16 * s, ink, 1.0, (vol if vol is not None else 100) / 100,
                               self.tray["muted"])
        elif what == "clock":
            top, low = self._text(round(12 * s), 600), self._text(round(11 * s), 500)
            t, d = top.render(self.clock[0]), low.render(self.clock[1])
            gap = 1 * s
            y0 = cy - (top.line + low.line + gap) / 2
            cv.text(t, cx - t.shape[1] / 2, y0, ink, 1.0)
            cv.text(d, cx - d.shape[1] / 2, y0 + top.line + gap, th["muted"], 1.0)
        elif what == "bell":
            face.bell_glyph(cv, cx, cy, 16 * s, ink, 1.0)

    def _tray_name(self, what):
        """What the pill over a tray part says."""
        if what == "clock":
            return self.clock[2]
        if what == "bell":
            return "Notifications"
        vol = self.tray["volume"]
        net = {"wifi": "Wi-Fi", "wired": "Ethernet"}.get(self.tray["net"], "No network")
        return f"{net}, volume {'muted' if self.tray['muted'] else f'{vol}%'}" if vol is not None else net

    def _tip(self, cv, words, cx, bottom, th):
        """The name of the one pointed at on a pill of the glass over it, kept inside the window."""
        t = self._text(round(12 * self.s), 600)
        cover = t.render(words[:48])
        tw, s = cover.shape[1], self.s
        pw, ph = tw + 22 * s, LABEL * s
        cx = max(pw / 2 + 2, min(self.size[0] - pw / 2 - 2, cx))
        y0 = bottom - ph
        cv.shape(lambda X, Y: face.rbox(X, Y, cx, y0 + ph / 2, pw / 2, ph / 2, ph / 2),
                 (cx - pw / 2 - 1, y0 - 1, cx + pw / 2 + 1, bottom + 1), th["body"], th["fill"])
        cv.text(cover, cx - tw / 2, y0 + (ph - cover.shape[0]) / 2, th["text"], 1.0)

    # ---------------------------------------------------------------- clicks
    def _move(self):
        if self.press is not None and isinstance(self.press[0], str):
            return  # the tray's parts don't move
        super()._move()

    def _up(self):
        what = self._hit()
        if isinstance(what, str):
            press, self.press = self.press, None
            if press is not None and press[0] == what and self.dragging is None and not self.busy():
                self._keys(tray_keys(what))
            return
        super()._up()

    def _middle(self):
        if not isinstance(self._hit(), str):
            super()._middle()

    def _right(self):
        if not isinstance(self._hit(), str):
            super()._right()

    @staticmethod
    def _keys(keys):
        """keys pressed together and let go, as Start's Windows key is (_start_menu)."""
        for key in keys:
            _user32.keybd_event(key, 0, 0, 0)
        for key in reversed(keys):
            _user32.keybd_event(key, 0, 2, 0)
