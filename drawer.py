"""The web drawer (7 November 2026, the owner's ask, after NotchPixel's: "pin a site and it opens in a rounded drawer
under the island, even over a game"): a site pinned in the island's Web tab opens in a window of its own just under
her, its corners rounded, no title bar, over everything; a click on it in the tab again puts it away, and it's closed
when she quits. Chrome or Edge's app mode (herbrowser.program) with a profile of its own, %LOCALAPPDATA%\\Hey
Harry\\Drawer, so you sign in there once and her browser and yours are kept apart from it.

Only addresses on the internet, as her browser has it (herbrowser's rule): never this PC or your home network."""
import atexit
import ctypes
import os
import subprocess
import threading
import time
from ctypes import wintypes as wt
from urllib.parse import urlparse

import winplatform as win

W, H = 430, 660  # logical px: the drawer's size
_user32 = ctypes.WinDLL("user32")
_user32.GetWindowLongW.restype = ctypes.c_long
_user32.SetWindowLongW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_long]
_user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
_user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
_user32.SetWindowRgn.argtypes = [wt.HWND, wt.HANDLE, wt.BOOL]
_user32.GetDpiForWindow.argtypes = [wt.HWND]
_user32.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wt.UINT]
_gdi = ctypes.WinDLL("gdi32")
_dwm = ctypes.WinDLL("dwmapi")
_gdi.CreateRoundRectRgn.restype = wt.HANDLE
ENUM = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
GWL_STYLE, HWND_TOPMOST = -16, -1
FRAME = 0x00C00000 | 0x00040000 | 0x00080000 | 0x00020000 | 0x00010000  # caption, sizing, menu, min and max
SWP_FRAMECHANGED, SWP_SHOWWINDOW, SW_HIDE = 0x0020, 0x0040, 0


def normal(url):
    """url as it's kept and shown (https:// put in front of a bare name), or None if it can't be a site on the
    internet by its look alone: no name with a dot in it, an address of this PC or the home network, not http(s).
    Nothing's looked up, so it's quick enough to draw with; site() looks before one's opened."""
    url = str(url or "").strip()
    if not url:
        return None
    if "://" not in url:
        url = "https://" + url
    parts = urlparse(url)
    host = parts.hostname or ""
    if parts.scheme not in ("http", "https") or "." not in host or host.endswith((".local", ".lan", ".home")):
        return None
    try:
        import ipaddress
        if not ipaddress.ip_address(host).is_global:
            return None
    except ValueError:
        pass  # a name, not an address
    return url


def site(url):
    """url as the drawer opens it, or None for anything that isn't a site on the internet: this PC, your home
    network, a file. Its name is looked up (web._public), so it's never asked on the island's thread."""
    url = normal(url)
    if url is None:
        return None
    import web
    return url if web._public(url) else None


def name_of(url):
    """A pinned site's name for its tile: "youtube.com" for https://www.youtube.com/watch."""
    host = urlparse(url).hostname or url
    return host[4:] if host.startswith("www.") else host


def _window_of(pid):
    """The browser's own visible window (a top-level one of pid), or None yet."""
    found = []

    def look(hwnd, _):
        owner = wt.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and _user32.IsWindowVisible(hwnd) and win._class_name(hwnd) == "Chrome_WidgetWin_1":
            found.append(hwnd)
            return False
        return True
    _user32.EnumWindows(ENUM(look), 0)
    return found[0] if found else None


class Drawer:
    """One drawer at a time: toggle(url, box) opens it in box (x, y, w, h, real px on the screen), or puts it away if
    it's that site, up already; close() when she quits."""

    def __init__(self):
        self.proc, self.hwnd, self.url, self.box, self.up = None, None, None, None, False
        self.lock = threading.Lock()
        atexit.register(self.close)

    def toggle(self, url, box):
        url = site(url)
        if url is None:
            raise RuntimeError("Only a site on the internet opens in the drawer")
        with self.lock:
            alive = self.proc is not None and self.proc.poll() is None
            if alive and url == self.url and self.up:
                self.hide()
                return False
            if alive and url == self.url and self.hwnd:
                self._place(box)
                threading.Thread(target=self._clip_again, name="harry-drawer", daemon=True).start()
                return True
            self._close()
            import herbrowser
            exe = herbrowser.program()
            if not exe:
                raise RuntimeError("There's no Chrome or Edge for the drawer")
            folder = os.path.join(win.home(), "Drawer")
            os.makedirs(folder, exist_ok=True)
            x, y, w, h = box
            self.proc = subprocess.Popen(
                [exe, f"--app={url}", f"--user-data-dir={folder}", f"--window-size={w},{h}",
                 f"--window-position={x},{y}", "--no-first-run", "--no-default-browser-check",
                 # painted the plain way, so its window can be cut to the box: through DirectComposition, as
                 # Chrome paints otherwise, the cut-off title bar and frame still showed (7 November 2026)
                 "--disable-features=Translate", "--disable-direct-composition"], close_fds=True)
            self.url, self.box, self.hwnd, self.up = url, box, None, True
        threading.Thread(target=self._dress, args=(self.proc.pid, box), name="harry-drawer", daemon=True).start()
        return True

    def _dress(self, pid, box):
        """Once its window shows: no title bar or frame, its corners round, over everything, in box."""
        for _ in range(80):
            hwnd = _window_of(pid)
            if hwnd:
                with self.lock:
                    if self.proc is None or self.proc.pid != pid:
                        return
                    self.hwnd = hwnd
                    style = _user32.GetWindowLongW(hwnd, GWL_STYLE)
                    _user32.SetWindowLongW(hwnd, GWL_STYLE, style & ~FRAME)
                    self._place(box)
                self._clip_again()
                return
            time.sleep(0.1)

    def _edges(self):
        """(the title bar Chrome draws itself at the top of an app's window, the frame it draws round the rest), px:
        as Windows' own caption and frame are (measured 45 and 10 px at 125%, 7 November 2026). Taking the window's
        frame away doesn't take them away, so they're cut off (_place)."""
        dpi = _user32.GetDpiForWindow(self.hwnd) or 96
        size = _user32.GetSystemMetricsForDpi
        frame = size(33, dpi) + size(92, dpi)  # SM_CYSIZEFRAME, SM_CXPADDEDBORDER
        return size(4, dpi) + frame, frame  # SM_CYCAPTION

    def _place(self, box):
        """In box, over everything: the window that big and its title bar and frame more, those cut off and its
        corners rounded (_clip), a drawer."""
        x, y, w, h = box
        self.box, self.up = box, True
        cap, frame = self._edges()
        _user32.SetWindowPos(self.hwnd, HWND_TOPMOST, x - frame, y - cap, w + 2 * frame, h + cap + frame,
                             SWP_FRAMECHANGED | SWP_SHOWWINDOW)
        self._clip()

    def _clip(self):
        """The window cut to the box: its title bar and frame off, its corners round. Windows owns the region."""
        if not self.hwnd or self.box is None:
            return
        cap, frame = self._edges()
        w, h = self.box[2], self.box[3]
        r = 2 * max(8, int(w * 0.04))
        region = _gdi.CreateRoundRectRgn(frame, cap, frame + w + 1, cap + h + 1, r, r)
        if region:
            _user32.SetWindowRgn(self.hwnd, region, True)
        # and no frame drawn by Windows: its glass, in the accent colour, filled the cut-off part (7 November 2026)
        off = ctypes.c_int(1)  # DWMWA_NCRENDERING_POLICY: DWMNCRP_DISABLED
        _dwm.DwmSetWindowAttribute(wt.HWND(self.hwnd), 2, ctypes.byref(off), 4)

    def _clip_again(self):
        """Chrome sets a region of its own as it lays itself out after a move: the box's cut again once it has."""
        for wait in (0.25, 0.6, 1.2):
            time.sleep(wait)
            with self.lock:
                if self.up:
                    self._clip()

    def hide(self):
        if self.hwnd:
            _user32.ShowWindow(self.hwnd, SW_HIDE)
        self.up = False

    def _close(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
        self.proc, self.hwnd, self.up = None, None, False

    def close(self):
        with self.lock:
            self._close()
