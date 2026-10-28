"""Small dark cards in a corner of the screen (28 October 2026, after Atticus's corner chip and live mini screen):
what her helpers and background jobs are doing, each with a live picture of the window it works in, and the meeting
helper's notes. The picture is Windows' own (a DWM thumbnail): it moves as the window does, even behind your other
windows, and costs nothing to draw. A card never takes the focus, isn't in the taskbar or Alt+Tab, and is left out
of screenshots and screen shares (WDA_EXCLUDEFROMCAPTURE), so the people in a call never see it.

Each card is a window on overlay's drawing thread, painted with GDI. Clicking a part of it calls on_click(key) on a
thread of its own: the key of the section clicked, or "close" for its x."""
import ctypes
import threading
from ctypes import wintypes as wt

import overlay

_u = overlay._u  # overlay's own handles, with their signatures: ShowWindow, SetWindowPos and the rest
_g = ctypes.WinDLL("gdi32", use_last_error=True)
_d = ctypes.WinDLL("dwmapi")


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [("hdc", wt.HDC), ("fErase", wt.BOOL), ("rcPaint", wt.RECT), ("fRestore", wt.BOOL),
                ("fIncUpdate", wt.BOOL), ("rgbReserved", ctypes.c_byte * 32)]


class THUMB_PROPS(ctypes.Structure):  # DWM_THUMBNAIL_PROPERTIES
    _fields_ = [("dwFlags", wt.DWORD), ("rcDestination", wt.RECT), ("rcSource", wt.RECT), ("opacity", ctypes.c_ubyte),
                ("fVisible", wt.BOOL), ("fSourceClientAreaOnly", wt.BOOL)]


_sig = overlay._sig
_sig(_u.BeginPaint, [wt.HWND, ctypes.POINTER(PAINTSTRUCT)], wt.HDC)
_sig(_u.EndPaint, [wt.HWND, ctypes.POINTER(PAINTSTRUCT)])
_sig(_u.InvalidateRect, [wt.HWND, ctypes.POINTER(wt.RECT), wt.BOOL])
_sig(_u.FillRect, [wt.HDC, ctypes.POINTER(wt.RECT), wt.HBRUSH], ctypes.c_int)
_sig(_u.DrawTextW, [wt.HDC, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.RECT), wt.UINT], ctypes.c_int)
_sig(_u.GetDpiForWindow, [wt.HWND], wt.UINT)
_sig(_u.IsWindow, [wt.HWND])
_sig(_u.IsWindowVisible, [wt.HWND])
_sig(_u.IsIconic, [wt.HWND])
_sig(_g.CreateSolidBrush, [wt.COLORREF], wt.HBRUSH)
_sig(_g.DeleteObject, [wt.HGDIOBJ])
_sig(_g.SelectObject, [wt.HDC, wt.HGDIOBJ], wt.HGDIOBJ)
_sig(_g.SetTextColor, [wt.HDC, wt.COLORREF], wt.COLORREF)
_sig(_g.SetBkMode, [wt.HDC, ctypes.c_int], ctypes.c_int)
_sig(_g.CreateFontW, [ctypes.c_int] * 5 + [wt.DWORD] * 8 + [wt.LPCWSTR], wt.HFONT)
_sig(_g.CreateCompatibleDC, [wt.HDC], wt.HDC)
_sig(_g.CreateCompatibleBitmap, [wt.HDC, ctypes.c_int, ctypes.c_int], wt.HBITMAP)
_sig(_g.BitBlt, [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HDC, ctypes.c_int, ctypes.c_int,
                 wt.DWORD])
_sig(_g.DeleteDC, [wt.HDC])
_sig(_g.Ellipse, [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int])
_sig(_g.GetStockObject, [ctypes.c_int], wt.HGDIOBJ)
_sig(_d.DwmRegisterThumbnail, [wt.HWND, wt.HWND, ctypes.POINTER(ctypes.c_void_p)], ctypes.c_long)
_sig(_d.DwmUnregisterThumbnail, [ctypes.c_void_p], ctypes.c_long)
_sig(_d.DwmUpdateThumbnailProperties, [ctypes.c_void_p, ctypes.POINTER(THUMB_PROPS)], ctypes.c_long)
_sig(_d.DwmQueryThumbnailSourceSize, [ctypes.c_void_p, ctypes.POINTER(wt.SIZE)], ctypes.c_long)
_sig(_d.DwmSetWindowAttribute, [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD], ctypes.c_long)

WM_PAINT, WM_ERASEBKGND, WM_LBUTTONUP, WM_MOUSEACTIVATE, WM_SETCURSOR = 0x000F, 0x0014, 0x0202, 0x0021, 0x0020
MA_NOACTIVATE = 3
DT_LEFT, DT_WORDBREAK, DT_NOPREFIX, DT_END_ELLIPSIS, DT_SINGLELINE, DT_CALCRECT, DT_RIGHT = 0, 0x10, 0x800, 0x8000, \
    0x20, 0x400, 0x2
THUMB_FLAGS = 0x1 | 0x4 | 0x8 | 0x10  # its rectangle, opacity, whether it shows, and the whole window
SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x10, 0x40
HWND_TOPMOST = wt.HWND(-1)


def rgb(r, g, b):
    return r | (g << 8) | (b << 16)


BG, LINE_BG = rgb(24, 24, 27), rgb(36, 36, 40)
TITLE, BODY, MUTED = rgb(244, 244, 246), rgb(214, 214, 220), rgb(150, 150, 158)
DOTS = {"running": rgb(10, 132, 255), "waiting": rgb(255, 159, 10), "done": rgb(48, 209, 88),
        "failed": rgb(255, 69, 58), "recording": rgb(255, 69, 58), "queued": rgb(150, 150, 158)}
FACES = ("Segoe UI Variable Text", "Segoe UI")


class Card:
    """A card in a corner of the screen, on the drawing thread. show(sections) puts it up with what it says now, each
    section a dict: key, title, note, dot (a DOTS name), thumb (a window to show live, or None), lines (a few
    more); hide() takes it down. on_click(key) for a click on a section, "close" for its x."""
    WIDTH, PAD, GAP, THUMB_H, MARGIN = 320, 14, 12, 168, 16

    def __init__(self, on_click=None, corner="bottom-right"):
        self.ui = overlay.UI.get()
        self.on_click, self.corner = on_click, corner
        self.hwnd, self.sections, self.thumbs, self.hits = None, [], {}, []
        self.s, self.fonts, self.size = 1.0, {}, (0, 0)
        self.visible = False

    # ------------------------------------------------------------------ from any thread
    def show(self, sections):
        self.ui.call(self._show, [dict(s) for s in sections], wait=False)

    def hide(self):
        self.ui.call(self._hide, wait=False)

    def close(self):
        self.ui.call(self._close, wait=False)

    # ------------------------------------------------------------------ on the drawing thread
    def _make(self):
        ex = overlay.WS_EX_TOPMOST | overlay.WS_EX_TOOLWINDOW | overlay.WS_EX_NOACTIVATE
        self.hwnd = self.ui.window(ex, self._handle, -32000, -32000, 10, 10)
        _u.SetWindowDisplayAffinity(self.hwnd, overlay.WDA_EXCLUDEFROMCAPTURE)  # never in a screen share
        corner = ctypes.c_int(2)  # Windows 11's round corners
        _d.DwmSetWindowAttribute(self.hwnd, 33, ctypes.byref(corner), 4)
        border = wt.DWORD(rgb(58, 58, 64))
        _d.DwmSetWindowAttribute(self.hwnd, 34, ctypes.byref(border), 4)
        self.s = (_u.GetDpiForWindow(self.hwnd) or 96) / 96
        s = self.s
        for name, px, weight in (("title", 14, 600), ("body", 12.5, 400), ("small", 11.5, 400), ("x", 15, 400)):
            for face in FACES:
                font = _g.CreateFontW(-round(px * s), 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 5, 0, face)
                if font:
                    self.fonts[name] = font
                    break

    def _measure(self, dc, text, font, width, lines=None):
        _g.SelectObject(dc, self.fonts[font])
        r = wt.RECT(0, 0, int(width), 0)
        flags = DT_CALCRECT | DT_NOPREFIX | (DT_WORDBREAK if lines != 1 else DT_SINGLELINE)
        _u.DrawTextW(dc, text, -1, ctypes.byref(r), flags)
        return r.bottom - r.top

    def _show(self, sections):
        if self.hwnd is None:
            self._make()
        self.sections = sections
        self._layout()
        self._thumbs()
        _u.InvalidateRect(self.hwnd, None, False)
        if not self.visible:
            self.visible = True

    def _layout(self):
        """Each section's place, the thumbnails' too, then the card's size and its corner of the screen."""
        s, pad, gap = self.s, self.PAD * self.s, self.GAP * self.s
        w = int(self.WIDTH * s)
        inner = w - 2 * pad
        dc = _g.CreateCompatibleDC(None)
        try:
            y, self.hits, self.places = pad, [], []
            for sec in self.sections:
                top = y
                title_h = self._measure(dc, sec.get("title") or "", "title", inner - 34 * s, 1)
                y += title_h
                note_h = self._measure(dc, sec.get("note") or "", "small", inner, 2) if sec.get("note") else 0
                y += note_h + (4 * s if note_h else 0)
                thumb = None
                if sec.get("thumb") and _u.IsWindow(sec["thumb"]) and not _u.IsIconic(sec["thumb"]):
                    thumb = (int(pad), int(y + 4 * s), int(pad + inner), int(y + 4 * s + self.THUMB_H * s))
                    y = thumb[3] + 4 * s
                lines = [str(t) for t in sec.get("lines") or [] if str(t).strip()]
                heights = [self._measure(dc, t, "body", inner, 3) for t in lines]
                y += sum(heights) + 4 * s * len(heights)
                self.places.append({"top": top, "title_h": title_h, "note_h": note_h, "thumb": thumb,
                                    "lines": list(zip(lines, heights))})
                self.hits.append((sec.get("key"), top, y))
                y += gap
            h = int(y - gap + pad)
        finally:
            _g.DeleteDC(dc)
        h = max(h, int(48 * s))
        self.size = (w, h)
        _, work, _ = overlay.monitor_at(0, 0)
        m = self.MARGIN * s
        x = work[2] - w - m if "right" in self.corner else work[0] + m
        # at the top, clear of a maximised window's own buttons
        y = work[3] - h - m if "bottom" in self.corner else work[1] + m + 44 * s
        _u.SetWindowPos(self.hwnd, HWND_TOPMOST, int(x), int(y), w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)

    def _thumbs(self):
        """Live pictures of the windows the sections show, from Windows' compositor."""
        wanted = {}
        for sec, place in zip(self.sections, self.places):
            if place["thumb"] is not None:
                wanted[sec["thumb"]] = place["thumb"]
        for src in list(self.thumbs):
            if src not in wanted:
                _d.DwmUnregisterThumbnail(self.thumbs.pop(src))
        for src, (l, t, r, b) in wanted.items():
            handle = self.thumbs.get(src)
            if handle is None:
                h = ctypes.c_void_p()
                if _d.DwmRegisterThumbnail(self.hwnd, src, ctypes.byref(h)) != 0:
                    continue
                handle = self.thumbs[src] = h
            size = wt.SIZE()
            _d.DwmQueryThumbnailSourceSize(handle, ctypes.byref(size))
            bw, bh = r - l, b - t
            if size.cx > 0 and size.cy > 0:  # as it is, fitted in and centred
                k = min(bw / size.cx, bh / size.cy)
                fw, fh = int(size.cx * k), int(size.cy * k)
                l, t = l + (bw - fw) // 2, t + (bh - fh) // 2
                r, b = l + fw, t + fh
            props = THUMB_PROPS(dwFlags=THUMB_FLAGS, rcDestination=wt.RECT(l, t, r, b), opacity=255, fVisible=True,
                                fSourceClientAreaOnly=False)
            _d.DwmUpdateThumbnailProperties(handle, ctypes.byref(props))

    def _paint(self, hdc):
        w, h = self.size
        mem = _g.CreateCompatibleDC(hdc)
        bmp = _g.CreateCompatibleBitmap(hdc, w, h)
        old = _g.SelectObject(mem, bmp)
        try:
            s, pad = self.s, self.PAD * self.s
            inner = w - 2 * pad
            brush = _g.CreateSolidBrush(BG)
            _u.FillRect(mem, ctypes.byref(wt.RECT(0, 0, w, h)), brush)
            _g.DeleteObject(brush)
            _g.SetBkMode(mem, 1)
            for i, (sec, place) in enumerate(zip(self.sections, self.places)):
                top = place["top"]
                dot = DOTS.get(sec.get("dot") or "", None)
                tx = pad
                if dot is not None:  # its state, as a coloured dot before the title
                    r = 4 * s
                    cy = top + place["title_h"] / 2
                    brush = _g.CreateSolidBrush(dot)
                    pen = _g.GetStockObject(8)  # NULL_PEN
                    ob, op = _g.SelectObject(mem, brush), _g.SelectObject(mem, pen)
                    _g.Ellipse(mem, int(pad), int(cy - r), int(pad + 2 * r + 1), int(cy + r + 1))
                    _g.SelectObject(mem, ob)
                    _g.SelectObject(mem, op)
                    _g.DeleteObject(brush)
                    tx = pad + 2 * r + 7 * s
                self._text(mem, sec.get("title") or "", "title", TITLE, tx, top, inner - (tx - pad) - 26 * s, 1)
                if i == 0:  # its x, top right
                    self._text(mem, "\u00d7", "x", MUTED, w - pad - 14 * s, top - 3 * s, 16 * s, 1)
                y = top + place["title_h"]
                if place["note_h"]:
                    self._text(mem, sec.get("note") or "", "small", MUTED, pad, y + 2 * s, inner, 2)
                    y += place["note_h"] + 4 * s
                if place["thumb"] is not None:
                    l, t, r_, b = place["thumb"]
                    brush = _g.CreateSolidBrush(LINE_BG)
                    _u.FillRect(mem, ctypes.byref(wt.RECT(l, t, r_, b)), brush)
                    _g.DeleteObject(brush)
                    y = b + 4 * s
                for text, height in place["lines"]:
                    self._text(mem, text, "body", BODY, pad, y, inner, 3)
                    y += height + 4 * s
            _g.BitBlt(hdc, 0, 0, w, h, mem, 0, 0, 0x00CC0020)
        finally:
            _g.SelectObject(mem, old)
            _g.DeleteObject(bmp)
            _g.DeleteDC(mem)

    def _text(self, dc, text, font, colour, x, y, width, lines):
        _g.SelectObject(dc, self.fonts[font])
        _g.SetTextColor(dc, colour)
        r = wt.RECT(int(x), int(y), int(x + width), int(y + 400 * self.s))
        flags = DT_NOPREFIX | DT_END_ELLIPSIS | (DT_SINGLELINE if lines == 1 else DT_WORDBREAK)
        _u.DrawTextW(dc, text, -1, ctypes.byref(r), flags)

    def _handle(self, msg, wparam, lparam):
        if msg == WM_PAINT:
            ps = PAINTSTRUCT()
            hdc = _u.BeginPaint(self.hwnd, ctypes.byref(ps))
            try:
                self._paint(hdc)
            finally:
                _u.EndPaint(self.hwnd, ctypes.byref(ps))
            return 0
        if msg == WM_ERASEBKGND:
            return 1
        if msg == WM_MOUSEACTIVATE:  # a click on it never takes the focus from what you're doing
            return MA_NOACTIVATE
        if msg == WM_LBUTTONUP:
            x, y = ctypes.c_short(lparam & 0xFFFF).value, ctypes.c_short((lparam >> 16) & 0xFFFF).value
            w = self.size[0]
            key = "close" if x >= w - (self.PAD + 22) * self.s and y <= (self.PAD + 24) * self.s else \
                next((k for k, top, bottom in self.hits if top <= y <= bottom), None)
            if self.on_click is not None and key is not None:
                threading.Thread(target=self._clicked, args=(key,), daemon=True).start()
            return 0
        return None

    def _clicked(self, key):
        try:
            self.on_click(key)
        except Exception as exc:
            print(f"  card click: {exc!r}")

    def _hide(self):
        for handle in self.thumbs.values():
            _d.DwmUnregisterThumbnail(handle)
        self.thumbs.clear()
        if self.hwnd is not None:
            _u.ShowWindow(self.hwnd, overlay.SW_HIDE)
        self.visible = False

    def _close(self):
        self._hide()
        if self.hwnd is not None:
            self.ui.destroy(self.hwnd)
            self.hwnd = None
        for font in self.fonts.values():
            _g.DeleteObject(font)
        self.fonts = {}
