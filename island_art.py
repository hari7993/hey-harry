"""Pictures for the island, as premultiplied RGBA floats (h, w, 4) from 0 to 1: an app's own icon, a round badge
with the app's first letter when it has no icon to give (an app on your phone, through Phone Link), and a song's
cover art. Windows' own GDI and GDI+ do the drawing and decoding, so there's no image library to install.
"""
import ctypes
import os
import re
import threading
from ctypes import wintypes as wt
from functools import lru_cache

import numpy as np

import bubble
import island_face as face

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdiplus = ctypes.WinDLL("gdiplus")
_shlwapi = ctypes.WinDLL("shlwapi")
_user32.PrivateExtractIconsW.argtypes = [wt.LPCWSTR, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                         ctypes.POINTER(wt.HICON), ctypes.POINTER(wt.UINT), wt.UINT, wt.UINT]
_user32.PrivateExtractIconsW.restype = wt.UINT
_user32.DrawIconEx.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, wt.HICON, ctypes.c_int, ctypes.c_int, wt.UINT,
                               wt.HBRUSH, wt.UINT]
_user32.DestroyIcon.argtypes = [wt.HICON]
_user32.SendMessageTimeoutW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT,
                                        ctypes.POINTER(ctypes.c_size_t)]
_user32.SendMessageTimeoutW.restype = wt.LPARAM
_user32.GetClassLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
_user32.GetClassLongPtrW.restype = ctypes.c_size_t
_shlwapi.SHCreateMemStream.argtypes = [ctypes.c_void_p, wt.UINT]
_shlwapi.SHCreateMemStream.restype = ctypes.c_void_p

# the colours apps are known by, for a badge with their letter
BRANDS = {"whatsapp": (0.15, 0.83, 0.4), "telegram": (0.13, 0.62, 0.85), "discord": (0.35, 0.4, 0.95),
          "teams": (0.38, 0.39, 0.65), "outlook": (0.0, 0.47, 0.83), "gmail": (0.92, 0.26, 0.21),
          "slack": (0.29, 0.08, 0.29), "signal": (0.23, 0.46, 0.94), "instagram": (0.88, 0.19, 0.42),
          "messenger": (0.0, 0.52, 1.0), "messages": (0.1, 0.45, 0.91), "phone link": (0.0, 0.47, 0.83),
          "chrome": (0.26, 0.52, 0.96), "google chrome": (0.26, 0.52, 0.96), "spotify": (0.11, 0.73, 0.33),
          "youtube": (1.0, 0.0, 0.0), "kiro": (0.49, 0.36, 1.0), "claude": (0.85, 0.47, 0.34),
          "microsoft edge": (0.0, 0.47, 0.83), "msedge": (0.0, 0.47, 0.83), "vlc": (1.0, 0.53, 0.0),
          "hey harry": (0.06, 0.46, 0.43)}


def brand(name):
    """The colour an app is known by, or one picked from its name, always the same for the same name."""
    key = str(name or "").lower().strip()
    for known, colour in BRANDS.items():
        if known == key or re.search(rf"\b{re.escape(known)}\b", key):
            return colour
    h = (sum(ord(c) * (i + 7) for i, c in enumerate(key)) % 360) / 360.0
    import colorsys
    return colorsys.hsv_to_rgb(h, 0.55, 0.85)


_draw_lock = threading.Lock()


def _from_icon(hicon, size):
    """An icon drawn at size px, its alpha worked out from drawing it on black and on white, so old masked icons
    and new ones with their own alpha both come out right."""
    with _draw_lock:
        dc = bubble._new_dc(None)
        try:
            bitmap, pixels = bubble._dib(dc, size, size)
            old = bubble._select(dc, bitmap)
            try:
                shots = []
                for back in (0, 255):
                    pixels[:] = back
                    if not _user32.DrawIconEx(dc, 0, 0, hicon, size, size, 0, None, 3):  # DI_NORMAL
                        return None
                    bubble._flush()
                    shots.append(pixels[..., :3].astype(np.float32) / 255)
            finally:
                bubble._select(dc, old)
                bubble._delete(bitmap)
        finally:
            bubble._delete_dc(dc)
    black, white = shots
    alpha = np.clip(1 - (white - black).mean(axis=2, keepdims=True), 0.0, 1.0)
    if alpha.max() < 0.05:
        return None
    rgb = black[..., ::-1]  # blue, green, red in the picture
    return np.concatenate([np.minimum(rgb, alpha), alpha], axis=2).astype(np.float32)


_weights = {}


def _area(src, n):
    """(indexes, weights), (n, taps) each: what averages each output pixel over the part of the input it covers (an
    area filter, as INTER_AREA is), or spreads it linearly when it grows; each pixel's weights add up to 1."""
    key = (src, n)
    hit = _weights.get(key)
    if hit is not None:
        return hit
    w = np.zeros((n, src), np.float32)
    if n <= src:
        f = src / n
        for i in range(n):
            a, b = i * f, (i + 1) * f
            for j in range(int(a), min(src, int(np.ceil(b)))):
                w[i, j] = min(b, j + 1) - max(a, j)
    else:
        pos = (np.arange(n) + 0.5) * src / n - 0.5
        lo = np.clip(np.floor(pos).astype(int), 0, src - 1)
        hi = np.clip(lo + 1, 0, src - 1)
        t = np.clip(pos - lo, 0.0, 1.0)
        w[np.arange(n), lo] += 1 - t
        w[np.arange(n), hi] += t
    w /= w.sum(axis=1, keepdims=True)
    # as taps: each output pixel's few input pixels and their weights, (n, taps) each, so it's a handful of slices
    # added up, not a matrix product (numpy's first one starts OpenBLAS, 32 MB, measured 30 October 2026)
    taps = max(1, int((w > 0).sum(axis=1).max()))
    idx = np.zeros((n, taps), np.intp)
    wts = np.zeros((n, taps), np.float32)
    for i in range(n):
        js = np.nonzero(w[i])[0]
        idx[i, :len(js)], wts[i, :len(js)] = js, w[i, js]
    hit = (idx, wts)
    if len(_weights) > 64:
        _weights.clear()
    _weights[key] = hit
    return hit


def _along(pic, axis, n):
    """pic averaged to n px along axis (0 down, 1 across) by its taps."""
    idx, wts = _area(pic.shape[axis], n)
    out = None
    for t in range(idx.shape[1]):
        part = np.take(pic, idx[:, t], axis=axis)
        weight = wts[:, t].reshape((n, 1, 1) if axis == 0 else (1, n, 1))
        out = part * weight if out is None else out + part * weight
    return out


def resample(rgba, n, m=None):
    """A picture made n px tall and m wide (n if not said), each output pixel the average of what it covers: sharp
    and even, where taking the nearest pixel shimmers and aliases (30 October 2026, the owner: the icons weren't
    sharp). numpy only, so the dock needn't load OpenCV, 40 MB or so, for it. Premultiplied pictures stay so."""
    pic = np.asarray(rgba, np.float32)
    h, w = pic.shape[:2]
    m = n if m is None else m
    if (h, w) == (n, m):
        return pic.copy()
    out = _along(pic, 0, n) if h != n else pic
    out = _along(out, 1, m) if w != m else out
    return np.ascontiguousarray(out, dtype=np.float32)


# the sizes icons are made at: one of them is drawn as it is in the program file, never scaled by Windows, and the
# picture's then averaged down to the size wanted
FRAMES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


@lru_cache(maxsize=48)
def exe_icon(path, size):
    """The icon of a program file (or an .ico) at size px, or None: taken at the next size up that icon files keep
    (FRAMES, 256 for anything over 48), then averaged down, so it's as sharp as the file has it (30 October 2026:
    asked at 106 px, Windows scaled a 256 or a 48 itself, and the dock's icons came out soft)."""
    if not path or not os.path.exists(path):
        return None
    src = 256 if size > 48 else next(f for f in FRAMES if f >= size)
    icon, got = wt.HICON(), wt.UINT()
    try:
        n = _user32.PrivateExtractIconsW(path, 0, src, src, ctypes.byref(icon), ctypes.byref(got), 1, 0)
    except OSError:
        return None
    if not n or not icon.value or n == 0xFFFFFFFF:
        return None
    try:
        pic = _from_icon(icon, src)
    finally:
        _user32.DestroyIcon(icon)
    if pic is None or src == size:
        return pic
    return resample(_trim(pic), size)


def _trim(pic):
    """An icon with the empty margin round it cut off, kept square and centred: some files pad a small picture out
    to 256 px, which came out tiny beside the others."""
    a = pic[..., 3]
    rows, cols = np.where(a.max(axis=1) > 0.04)[0], np.where(a.max(axis=0) > 0.04)[0]
    if not len(rows) or not len(cols):
        return pic
    n = pic.shape[0]
    side = max(rows[-1] - rows[0], cols[-1] - cols[0]) + 1
    if side >= n * 0.8:  # most draw out to near their edge: left as they are
        return pic
    side = max(side, int(n * 0.8))
    cy, cx = (rows[0] + rows[-1] + 1) // 2, (cols[0] + cols[-1] + 1) // 2
    y0 = max(0, min(n - side, cy - side // 2))
    x0 = max(0, min(n - side, cx - side // 2))
    return pic[y0:y0 + side, x0:x0 + side]


# the app a window belongs to, as Windows knows it (its AppUserModelID), for a Store app's own logo
class _PropKey(ctypes.Structure):
    _fields_ = [("fmtid", ctypes.c_ubyte * 16), ("pid", wt.DWORD)]


class _PropVariant(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort), ("r3", ctypes.c_ushort),
                ("ptr", ctypes.c_void_p), ("pad", ctypes.c_void_p)]


_APP_ID = _PropKey((ctypes.c_ubyte * 16).from_buffer_copy(
    __import__("uuid").UUID("9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3").bytes_le), 5)  # PKEY_AppUserModel_ID
_IID_PROPSTORE = (ctypes.c_byte * 16).from_buffer_copy(
    __import__("uuid").UUID("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99").bytes_le)


def window_app_id(hwnd):
    """The AppUserModelID Windows has for a window (a Store app's, as "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"),
    or None."""
    try:
        import winplatform as win
        win._com()
        shell = ctypes.WinDLL("shell32")
        store = ctypes.c_void_p()
        if shell.SHGetPropertyStoreForWindow(wt.HWND(hwnd), ctypes.byref(_IID_PROPSTORE), ctypes.byref(store)) != 0 \
                or not store.value:
            return None
        try:
            table = ctypes.cast(ctypes.c_void_p.from_address(store.value).value, ctypes.POINTER(ctypes.c_void_p))
            get = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(_PropKey),
                                     ctypes.POINTER(_PropVariant))(table[5])
            value = _PropVariant()
            if get(store.value, ctypes.byref(_APP_ID), ctypes.byref(value)) != 0:
                return None
            try:
                return ctypes.wstring_at(value.ptr) if value.vt == 31 and value.ptr else None  # VT_LPWSTR
            finally:
                ctypes.WinDLL("ole32").PropVariantClear(ctypes.byref(value))
        finally:
            _release(store.value)
    except Exception:
        return None


def window_app_icon(hwnd, size):
    """A window's app's own logo, as Start shows it, for a Store app whose window and program file give only a small
    icon: None if it has none to give."""
    app_id = window_app_id(hwnd)
    if not app_id:
        return None
    pic = file_icon("shell:AppsFolder\\" + app_id, max(size, 64))
    if pic is None:
        return None
    h, w = pic.shape[:2]
    f = size / max(h, w)
    return resample(pic, max(1, round(h * f)), max(1, round(w * f)))


def window_icon(hwnd, size):
    """The icon a window shows in its title bar, for apps whose program file can't be read (Store apps)."""
    out = ctypes.c_size_t()
    for which in (1, 2, 0):  # ICON_BIG, ICON_SMALL2, ICON_SMALL
        if _user32.SendMessageTimeoutW(hwnd, 0x7F, which, 0, 0x2, 60, ctypes.byref(out)) and out.value:
            got = _from_icon(wt.HICON(out.value), size)
            if got is not None:
                return got
    for index in (-14, -34):  # GCLP_HICON, GCLP_HICONSM
        h = _user32.GetClassLongPtrW(hwnd, index)
        if h:
            got = _from_icon(wt.HICON(h), size)
            if got is not None:
                return got
    return None


_badges = {}


def badge(name, size, text_maker):
    """A round badge in the app's colour with its first letter: text_maker(px) gives a bubble.Text."""
    key = (str(name or "?")[:1].upper(), round(size), brand(name))
    hit = _badges.get(key)
    if hit is not None:
        return hit
    letter = key[0] if key[0].isalnum() else "\u2022"
    n = int(round(size))
    col = np.zeros((n, n, 3), np.float32)
    cv = face.Canvas(col)
    xs = np.arange(n, dtype=np.float32) + 0.5
    ys = (np.arange(n, dtype=np.float32) + 0.5)[:, None]
    cover = np.clip(0.5 - face.circle(xs, ys, n / 2, n / 2, n / 2 - 0.5), 0.0, 1.0)
    col[:] = np.asarray(key[2], np.float32)
    t = text_maker(max(8, round(n * 0.52)))
    glyph = t.render(letter)
    cv.text(glyph, (n - glyph.shape[1]) / 2 + 0.5, (n - glyph.shape[0]) / 2, (1.0, 1.0, 1.0))
    out = np.concatenate([col * cover[..., None], cover[..., None]], axis=2).astype(np.float32)
    if len(_badges) > 64:
        _badges.clear()
    _badges[key] = out
    return out


def tint(rgba):
    """The colour a picture is known by, for a glow round it (30 October 2026, after bloom's ambient glow round a
    song's cover): its most common vivid hue, made bright enough to glow, as (r, g, b) 0 to 1; None for a picture
    that's grey all over."""
    if rgba is None:
        return None
    px = np.asarray(rgba, np.float32)
    a = px[..., 3]
    rgb = px[..., :3] / np.maximum(a, 1e-3)[..., None]  # straight colours, from premultiplied
    hi, lo = rgb.max(axis=2), rgb.min(axis=2)
    sat = np.where(hi > 0, (hi - lo) / np.maximum(hi, 1e-6), 0.0)
    weight = sat * hi * (a > 0.5)
    if float(weight.sum()) < 0.02 * weight.size:
        return None
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.arctan2(np.sqrt(3.0) * (g - b), 2 * r - g - b)  # -pi to pi round the colour wheel
    bins = ((hue + np.pi) / (2 * np.pi) * 12).astype(int) % 12
    best = int(np.argmax(np.bincount(bins.ravel(), weights=weight.ravel(), minlength=12)))
    pick = (bins == best) & (weight > 0)
    w = weight[pick][:, None]
    colour = (rgb[pick] * w).sum(axis=0) / max(float(w.sum()), 1e-6)
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(*(float(c) for c in np.clip(colour, 0.0, 1.0)))
    return colorsys.hsv_to_rgb(h, max(0.55, s), max(0.85, v))


class _BITMAP(ctypes.Structure):
    _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long), ("bmHeight", ctypes.c_long),
                ("bmWidthBytes", ctypes.c_long), ("bmPlanes", wt.WORD), ("bmBitsPixel", wt.WORD),
                ("bmBits", ctypes.c_void_p)]


_shell32 = ctypes.WinDLL("shell32")
_gdi32 = ctypes.WinDLL("gdi32")
_shell32.SHCreateItemFromParsingName.argtypes = [wt.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                                 ctypes.POINTER(ctypes.c_void_p)]
_shell32.SHCreateItemFromParsingName.restype = ctypes.c_long
_gdi32.GetObjectW.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p]
_gdi32.GetBitmapBits.argtypes = [wt.HANDLE, ctypes.c_long, ctypes.c_void_p]
_gdi32.DeleteObject.argtypes = [wt.HANDLE]
_IMAGE_FACTORY = (ctypes.c_byte * 16).from_buffer_copy(
    __import__("uuid").UUID("bcc18b79-ba16-442f-80c4-8a59c30c463b").bytes_le)  # IID_IShellItemImageFactory
_files = {}


def file_icon(path, size):
    """A file's or a folder's own picture at size px, as File Explorer shows it: a picture's or a video's thumbnail,
    else its icon (IShellItemImageFactory), premultiplied (h, w, 4) floats; None if Windows gives none. Kept for next
    time (30 October 2026: the island's shelf)."""
    key = (str(path), int(size))
    if key in _files:
        return _files[key]
    pic = None
    try:
        import winplatform as win
        win._com()
        factory = ctypes.c_void_p()
        if _shell32.SHCreateItemFromParsingName(str(path), None, ctypes.byref(_IMAGE_FACTORY),
                                                ctypes.byref(factory)) == 0 and factory.value:
            try:
                vtbl = ctypes.cast(ctypes.c_void_p.from_address(factory.value).value,
                                   ctypes.POINTER(ctypes.c_void_p))
                get_image = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wt.SIZE, ctypes.c_int,
                                               ctypes.POINTER(wt.HBITMAP))(vtbl[3])
                bmp = wt.HBITMAP()
                if get_image(factory.value, wt.SIZE(int(size), int(size)), 0, ctypes.byref(bmp)) == 0 and bmp.value:
                    try:
                        pic = _from_bitmap(bmp.value, int(size))
                    finally:
                        _gdi32.DeleteObject(bmp)
            finally:
                _release(factory.value)
    except Exception as exc:
        print(f"  island: no picture for a file ({exc!r})")
    if len(_files) > 64:
        _files.clear()
    _files[key] = pic
    return pic


def _from_bitmap(hbmp, size):
    """A 32-bit bitmap from the shell as a premultiplied picture, size px at most each way."""
    bm = _BITMAP()
    if not _gdi32.GetObjectW(hbmp, ctypes.sizeof(bm), ctypes.byref(bm)) or bm.bmBitsPixel != 32:
        return None
    w, h = bm.bmWidth, abs(bm.bmHeight)
    raw = (ctypes.c_ubyte * (w * h * 4))()
    if not _gdi32.GetBitmapBits(hbmp, len(raw), raw):
        return None
    px = np.frombuffer(raw, np.uint8).reshape(h, w, 4).astype(np.float32) / 255
    rgb, alpha = px[..., 2::-1], px[..., 3:4]
    if float(alpha.max()) <= 0.0:  # a bitmap with no alpha at all: all of it's solid
        alpha = np.ones_like(alpha)
    elif float((rgb - alpha).max()) > 0.02:  # brighter than its cover: straight colours, so premultiplied here
        rgb = rgb * alpha
    out = np.concatenate([np.minimum(rgb, alpha), alpha], axis=2)
    if max(w, h) > size:
        f = max(w, h) / size
        ys = np.minimum((np.arange(int(h / f)) * f).astype(int), h - 1)
        xs = np.minimum((np.arange(int(w / f)) * f).astype(int), w - 1)
        out = out[ys][:, xs]
    return np.ascontiguousarray(out, dtype=np.float32)


def rounded(rgba, radius):
    """A picture with its corners rounded off."""
    h, w = rgba.shape[:2]
    xs = np.arange(w, dtype=np.float32) + 0.5
    ys = (np.arange(h, dtype=np.float32) + 0.5)[:, None]
    m = np.clip(0.5 - face.rbox(xs, ys, w / 2, h / 2, w / 2, h / 2, radius), 0.0, 1.0)[..., None]
    return (rgba * m).astype(np.float32)


# --------------------------------------------------------------------------- cover art, decoded by GDI+
class _StartupInput(ctypes.Structure):
    _fields_ = [("GdiplusVersion", ctypes.c_uint32), ("DebugEventCallback", ctypes.c_void_p),
                ("SuppressBackgroundThread", wt.BOOL), ("SuppressExternalCodecs", wt.BOOL)]


class _BitmapData(ctypes.Structure):
    _fields_ = [("Width", ctypes.c_uint), ("Height", ctypes.c_uint), ("Stride", ctypes.c_int),
                ("PixelFormat", ctypes.c_int), ("Scan0", ctypes.c_void_p), ("Reserved", ctypes.c_size_t)]


class _Rect(ctypes.Structure):
    _fields_ = [("X", ctypes.c_int), ("Y", ctypes.c_int), ("Width", ctypes.c_int), ("Height", ctypes.c_int)]


_token = ctypes.c_size_t()
_gdip_lock = threading.Lock()
PARGB = 0x000E200B  # PixelFormat32bppPARGB: blue, green, red, alpha, premultiplied


def _release(com_ptr):
    """IUnknown::Release on a raw COM pointer."""
    vtbl = ctypes.cast(ctypes.c_void_p.from_address(com_ptr).value, ctypes.POINTER(ctypes.c_void_p))
    ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])(com_ptr)


def decode(data, size, radius=0.0):
    """A JPEG or PNG (bytes) as a size x size picture, the middle of it if it isn't square, or None."""
    if not data:
        return None
    with _gdip_lock:
        if not _token.value:
            inp = _StartupInput(1, None, False, False)
            if _gdiplus.GdiplusStartup(ctypes.byref(_token), ctypes.byref(inp), None) != 0:
                return None
        raw = ctypes.create_string_buffer(bytes(data), len(data))
        stream = _shlwapi.SHCreateMemStream(raw, len(data))
        if not stream:
            return None
        image, thumb = ctypes.c_void_p(), ctypes.c_void_p()
        try:
            if _gdiplus.GdipCreateBitmapFromStream(ctypes.c_void_p(stream), ctypes.byref(image)) != 0:
                return None
            w, h = ctypes.c_uint(), ctypes.c_uint()
            _gdiplus.GdipGetImageWidth(image, ctypes.byref(w))
            _gdiplus.GdipGetImageHeight(image, ctypes.byref(h))
            if not w.value or not h.value:
                return None
            k = size / min(w.value, h.value)
            tw, th = max(size, round(w.value * k)), max(size, round(h.value * k))
            if _gdiplus.GdipGetImageThumbnail(image, tw, th, ctypes.byref(thumb), None, None) != 0:
                return None
            rect, bits = _Rect(0, 0, tw, th), _BitmapData()
            if _gdiplus.GdipBitmapLockBits(thumb, ctypes.byref(rect), 1, PARGB, ctypes.byref(bits)) != 0:
                return None
            stride = abs(bits.Stride)
            try:
                start = bits.Scan0 if bits.Stride > 0 else bits.Scan0 + bits.Stride * (th - 1)
                buf = ctypes.string_at(start, stride * th)
            finally:
                _gdiplus.GdipBitmapUnlockBits(thumb, ctypes.byref(bits))
        finally:
            for img in (thumb, image):
                if img.value:
                    _gdiplus.GdipDisposeImage(img)
            _release(stream)
    px = np.frombuffer(buf, np.uint8).reshape(th, stride // 4, 4)[:, :tw]
    if bits.Stride < 0:  # stored bottom row first
        px = px[::-1]
    y0, x0 = (th - size) // 2, (tw - size) // 2
    px = px[y0:y0 + size, x0:x0 + size]
    out = np.concatenate([px[..., 2::-1], px[..., 3:4]], axis=2).astype(np.float32) / 255
    return rounded(out, radius) if radius else out
