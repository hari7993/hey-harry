"""Her window as it looks, one picture a tab, for the eye (22 November 2026, the owner: "make it the best UI"). Not a
test: it draws her real window and saves what it drew, so a change to the look is judged by looking, not by reading.

    .venv\\Scripts\\python checks\\ui_tour.py                 # every tab, into build\\ui-tour\\now
    .venv\\Scripts\\python checks\\ui_tour.py before          # into build\\ui-tour\\before, to set beside an after
    .venv\\Scripts\\python checks\\ui_tour.py now home,keys   # only these tabs
    .venv\\Scripts\\python checks\\ui_tour.py now --motion    # and how a page opens, as a few frames each, with times

The window is the real one (assistant_ui.AssistantWindow) with the assistant itself not started: no mic, no models, no
keys read, nothing sent. It runs under the tests' own tripwires and on an empty temp folder for her data
(tests/support.py), never on hers. Each picture is the window's own rectangle, so nothing else on your screen is in it.
"""
import ctypes
import os
import struct
import sys
import time
import zlib
from ctypes import wintypes as wt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tests import support  # noqa: E402,F401  (first: her real folders refused, temp ones in their place, tripwires)

import numpy as np  # noqa: E402

import winplatform as win  # noqa: E402

user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
for fn, args, res in ((user32.GetDC, [wt.HWND], wt.HDC), (user32.ReleaseDC, [wt.HWND, wt.HDC], ctypes.c_int),
                      (user32.GetWindowRect, [wt.HWND, ctypes.POINTER(wt.RECT)], wt.BOOL),
                      (user32.PrintWindow, [wt.HWND, wt.HDC, wt.UINT], wt.BOOL),
                      (user32.GetAncestor, [wt.HWND, wt.UINT], wt.HWND),
                      (gdi32.CreateCompatibleDC, [wt.HDC], wt.HDC),
                      (gdi32.CreateCompatibleBitmap, [wt.HDC, ctypes.c_int, ctypes.c_int], wt.HBITMAP),
                      (gdi32.SelectObject, [wt.HDC, wt.HGDIOBJ], wt.HGDIOBJ),
                      (gdi32.GetDIBits, [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p,
                                         wt.UINT], ctypes.c_int),
                      (gdi32.DeleteObject, [wt.HGDIOBJ], wt.BOOL), (gdi32.DeleteDC, [wt.HDC], wt.BOOL)):
    fn.argtypes, fn.restype = args, res


class Header(ctypes.Structure):
    _fields_ = [("size", wt.DWORD), ("width", wt.LONG), ("height", wt.LONG), ("planes", wt.WORD), ("bits", wt.WORD),
                ("compression", wt.DWORD), ("image", wt.DWORD), ("xppm", wt.LONG), ("yppm", wt.LONG),
                ("used", wt.DWORD), ("important", wt.DWORD)]


def grab(hwnd):
    """The window's own picture as (width, height, rgb bytes), whatever is in front of it (PrintWindow)."""
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    screen = user32.GetDC(None)
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, w, h)
    old = gdi32.SelectObject(memory, bitmap)
    user32.PrintWindow(hwnd, memory, 2)  # PW_RENDERFULLCONTENT: what DWM shows, not just what the window paints
    head = Header(ctypes.sizeof(Header), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)  # top-down, 32 bits
    pixels = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(memory, bitmap, 0, h, pixels, ctypes.byref(head), 0)
    gdi32.SelectObject(memory, old)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory)
    user32.ReleaseDC(None, screen)
    bgra = np.frombuffer(pixels, np.uint8).reshape(h, w, 4)
    return w, h, np.ascontiguousarray(bgra[..., 2::-1]).tobytes()


def save_png(path, w, h, rgb):
    """rgb (w * h * 3 bytes) as a PNG, with nothing but the standard library and numpy."""
    rows = np.zeros((h, w * 3 + 1), np.uint8)
    rows[:, 1:] = np.frombuffer(rgb, np.uint8).reshape(h, w * 3)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(rows.tobytes(), 5)) + chunk(b"IEND", b""))


def settle(root, seconds=0.25):
    """Tk drawn, and a moment for its frames and for Windows to put them on the screen."""
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        root.update()
        time.sleep(0.01)


def main(argv):
    flags = [a for a in argv if a.startswith("--")]
    args = [a for a in argv if not a.startswith("--")]
    label = args[0] if args else "now"
    only = args[1].split(",") if len(args) > 1 else None
    out = os.path.join(ROOT, "build", "ui-tour", label)
    os.makedirs(out, exist_ok=True)
    win.prepare_gui()  # sharp, and in real pixels, as she starts
    import tkinter as tk

    import assistant_ui
    from secrets_store import KEY_NAMES  # noqa: F401
    assistant_ui.missing_secrets = lambda: []  # no keys read from Windows' store, none shown as missing
    assistant_ui.get_secret = lambda *a, **k: ""
    assistant_ui.save_secret = lambda *a, **k: None

    class Quiet:  # the popup and the island, which would put a window of their own on the screen
        def __getattr__(self, name):
            return lambda *a, **k: None
    assistant_ui.Bubble = lambda root: Quiet()
    assistant_ui.AssistantWindow._start_edges = lambda self: None
    assistant_ui.AssistantWindow._start_worker = lambda self: None
    assistant_ui.settings.put("onboarded", True)
    root = tk.Tk()
    root.report_callback_exception = lambda kind, exc, tb: print("  Tk callback:", repr(exc))
    began = time.perf_counter()
    app = assistant_ui.AssistantWindow(root)
    print(f"built her window in {(time.perf_counter() - began) * 1000:.0f} ms")
    root.attributes("-topmost", True)
    settle(root, 0.8)
    hwnd = user32.GetAncestor(root.winfo_id(), 2)
    for key, name in assistant_ui.TABS:
        if only and key not in only:
            continue
        began = time.perf_counter()
        app._select_tab(key)
        root.update_idletasks()
        opened = (time.perf_counter() - began) * 1000
        settle(root)
        w, h, rgb = grab(hwnd)
        save_png(os.path.join(out, f"{key}.png"), w, h, rgb)
        print(f"  {key:<9} {name:<18} opened in {opened:5.0f} ms   {w}x{h}")
    if "--chat" in flags:  # a chat, as it comes: typed while she starts up, then her turn with its steps and answer
        app._select_tab("home")
        page = app.chat
        for words in ("Get me ready for my 2pm", "and open the pricing doc"):
            page.box.put(words)
            page.send()
        settle(root)
        w, h, rgb = grab(hwnd)
        save_png(os.path.join(out, "chat-starting.png"), w, h, rgb)
        page.thread.starting = ""  # she's up: the rest as her window's events tell it
        page.event("Thinking", "Get me ready for my 2pm")
        page.event("Step", "live\tOpening your calendar")
        page.event("Step", "done\tOpening your calendar")
        page.event("Step", "live\tOpening the pricing doc")
        page.event("Step", "failed\tOpening the pricing doc")
        page.event("Speaking", "Your 2pm is the Juniper website review with Maya. She wants to start with pricing, "
                   "not the homepage. I couldn't open the pricing doc, so open it from Notion and I'll read it.")
        page.event("Ready", "")
        settle(root, 0.5)
        w, h, rgb = grab(hwnd)
        save_png(os.path.join(out, "chat-turn.png"), w, h, rgb)
        print("  chat      two scenes saved")
    root.destroy()
    print("pictures in", out)


if __name__ == "__main__":
    main(sys.argv[1:])
