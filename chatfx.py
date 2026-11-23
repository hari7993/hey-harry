"""The chat page's touches of motion and light (22 November 2026, the owner: "the text, fonts and animations are too
old ... latest trending styling", pointing at Claude Code and Hedwig, and asking that it be built with the design
skills installed that day; ui-ux-pro-max's "AI-Native UI": minimal chrome, one soft AI accent, a three-dot pulse while
it thinks, smooth reveals, a stagger of 60 ms at 400 ms with a little overshoot, and a visible focus on the input).

What's here holds no window of its own and asks nothing of her turn: pictures, made with numpy and Windows' own text
renderer, that chat.Page shows.

- A greeting in a soft gradient (blue to indigo to violet), drawn by GDI in Plus Jakarta Sans with its smooth edges,
  which Tk's own text can't do (greeting_ppm).
- An aurora: three pale blobs of colour drifting behind the greeting on the empty page, made once as a short loop and
  only played while that page is up (aurora_frames).
- The composer's ring: a hairline of the accent while it has the keyboard, and while she listens or thinks a gradient
  that travels round its edge with a soft light inside it, as Apple's assistant has (ring_ppm).

Every one is made at the size it's shown and kept by its caller; none runs with Windows' animations off (chat).
"""
import math
import time

# the AI's own colours, soft: Hedwig's blue into indigo into a light violet (ui-ux-pro-max's AI accent #6366F1)
STOPS = ("#5090f7", "#6366f1", "#a78bfa")
AURORA = ("#c7d7fe", "#ddd3fd", "#fbd5e8")  # the aurora's three pale blobs: sky, lilac, blush
SUGGESTIONS = (  # what the empty page offers to start from: things she does, each with its mark and a pale tint
    ("\ue787", "What's on my calendar today?", "#e8f0fe", "#3b6fd6"),
    ("\ue8bd", "Brief me on what I missed", "#f1ebfd", "#6f4cc3"),
    ("\ue8d6", "Play some focus music", "#e6f4ea", "#2e7d4f"),
    ("\ue916", "Remind me in 20 minutes", "#fef3db", "#a8641a"),
)


def hue(colour):
    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))


def along(stops, t):
    """The colour t of the way along stops (0 to 1), as (r, g, b) floats."""
    t = min(1.0, max(0.0, t)) * (len(stops) - 1)
    i = min(int(t), len(stops) - 2)
    a, b = hue(stops[i]), hue(stops[i + 1])
    f = t - i
    return tuple(a[k] + (b[k] - a[k]) * f for k in range(3))


def greeting(now=None, name=""):
    """What the empty page says first: "Good morning, Hari", by the hour; without a name, the greeting alone."""
    hour = (now or time.localtime()).tm_hour
    part = "Good morning" if 5 <= hour < 12 else "Good afternoon" if 12 <= hour < 17 else \
        "Good evening" if 17 <= hour < 23 else "Hello"  # past eleven at night and before five: just hello
    name = " ".join(str(name or "").split())
    return f"{part}, {name}" if name else part


def text_mask(text, family, size, weight=600):
    """text as GDI draws it, its edges smoothed, as an alpha mask (a numpy array of 0 to 1). Raises if GDI can't."""
    import ctypes
    from ctypes import wintypes as wt

    import numpy as np
    gdi, user = ctypes.windll.gdi32, ctypes.windll.user32
    gdi.CreateFontW.restype = wt.HFONT
    gdi.CreateCompatibleDC.restype = wt.HDC
    gdi.CreateDIBSection.restype = wt.HBITMAP
    gdi.SelectObject.restype = wt.HGDIOBJ
    gdi.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
    gdi.DeleteObject.argtypes = [wt.HGDIOBJ]
    gdi.DeleteDC.argtypes = [wt.HDC]
    gdi.CreateCompatibleDC.argtypes = [wt.HDC]
    gdi.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wt.DWORD] * 8 + [wt.LPCWSTR]
    gdi.GetTextExtentPoint32W.argtypes = [wt.HDC, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.SIZE)]
    gdi.CreateDIBSection.argtypes = [wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p), wt.HANDLE,
                                     wt.DWORD]
    gdi.SetBkMode.argtypes = [wt.HDC, ctypes.c_int]
    gdi.SetTextColor.argtypes = [wt.HDC, wt.DWORD]
    gdi.TextOutW.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, wt.LPCWSTR, ctypes.c_int]
    user.GetDC.restype = wt.HDC
    user.GetDC.argtypes = [wt.HWND]
    user.ReleaseDC.argtypes = [wt.HWND, wt.HDC]

    class Header(ctypes.Structure):
        _fields_ = [("size", wt.DWORD), ("width", wt.LONG), ("height", wt.LONG), ("planes", wt.WORD),
                    ("bits", wt.WORD), ("compression", wt.DWORD), ("image", wt.DWORD), ("xppm", wt.LONG),
                    ("yppm", wt.LONG), ("used", wt.DWORD), ("important", wt.DWORD)]
    screen = user.GetDC(None)
    dc = gdi.CreateCompatibleDC(screen)
    font = gdi.CreateFontW(-int(size), 0, 0, 0, int(weight), 0, 0, 0, 1, 0, 0, 4, 0, family)  # ANTIALIASED_QUALITY
    old_font = gdi.SelectObject(dc, font)
    extent = wt.SIZE()
    gdi.GetTextExtentPoint32W(dc, text, len(text), ctypes.byref(extent))
    pad = max(2, int(size) // 6)
    w, h = extent.cx + 2 * pad, extent.cy + 2 * pad
    header = Header(ctypes.sizeof(Header), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    dib = gdi.CreateDIBSection(dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
    old_bmp = gdi.SelectObject(dc, dib)
    try:
        gdi.SetBkMode(dc, 1)  # TRANSPARENT: white letters on the black the section starts as
        gdi.SetTextColor(dc, 0xFFFFFF)
        gdi.TextOutW(dc, pad, pad, text, len(text))
        gdi.GdiFlush()
        raw = (ctypes.c_ubyte * (w * h * 4)).from_address(bits.value)
        mask = np.frombuffer(raw, np.uint8).reshape(h, w, 4)[..., 1].astype(np.float32) / 255.0
        return mask.copy()
    finally:
        gdi.SelectObject(dc, old_bmp)
        gdi.SelectObject(dc, old_font)
        gdi.DeleteObject(dib)
        gdi.DeleteObject(font)
        gdi.DeleteDC(dc)
        user.ReleaseDC(None, screen)


def greeting_ppm(text, family, size, back="#ffffff", stops=STOPS, fade=1.0, weight=600):
    """The greeting as a PPM: its letters in the gradient, left to right, on back, at fade of their strength (0 to 1,
    for coming in). (the PPM's bytes, its width, its height)"""
    import numpy as np
    mask = text_mask(text, family, size, weight) * float(fade)
    h, w = mask.shape
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    grad = np.stack([np.interp(xs, np.linspace(0, 1, len(stops)), [hue(s)[k] for s in stops]) for k in range(3)], -1)
    out = np.array(hue(back), np.float32) * (1 - mask[..., None]) + grad[None, :, :] * mask[..., None]
    return b"P6 %d %d 255 " % (w, h) + (out + 0.5).clip(0, 255).astype("uint8").tobytes(), w, h


def aurora_frames(w, h, n=24, back="#ffffff", colours=AURORA, strength=0.55):
    """The aurora's loop: n PPMs, w by h, of three soft blobs of colours drifting slowly on back, each frame a step
    of one slow circle so the loop runs on with no seam."""
    import numpy as np
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    base = np.array(hue(back), np.float32)
    out = []
    for f in range(n):
        a = 2 * math.pi * f / n
        img = np.zeros((h, w, 3), np.float32) + base
        for i, colour in enumerate(colours):
            cx = w * (0.32 + 0.18 * i) + w * 0.06 * math.cos(a + i * 2.1)
            cy = h * 0.55 + h * 0.12 * math.sin(a * (1 + 0.3 * i) + i)
            rx, ry = w * 0.26, h * 0.42
            weight = np.exp(-(((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2)) * strength
            img = img * (1 - weight[..., None]) + np.array(hue(colour), np.float32) * weight[..., None]
        edge = np.minimum(np.minimum(xs, w - 1 - xs) / (w * 0.18), np.minimum(ys, h - 1 - ys) / (h * 0.3)).clip(0, 1)
        img = base * (1 - edge[..., None]) + img * edge[..., None]  # fading into the page at every side
        out.append(b"P6 %d %d 255 " % (w, h) + (img + 0.5).clip(0, 255).astype("uint8").tobytes())
    return out


def ring_ppm(w, h, r, fill, back, phase=None, accent="#a5b4fc", stops=STOPS):
    """The composer's field with its ring, w by h, corners r, as a PPM: phase None for a still hairline of accent
    (it has the keyboard), or 0 to 1 for the gradient's place as it travels round the edge, with a soft light just
    inside it (she's listening or thinking)."""
    import numpy as np
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32) + 0.5
    qx, qy = np.abs(xs - w / 2) - (w / 2 - r), np.abs(ys - h / 2) - (h / 2 - r)
    d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r  # below 0 inside
    inside = np.clip(0.5 - d, 0, 1)[..., None]
    out = np.array(hue(back), np.float32) * (1 - inside) + np.array(hue(fill), np.float32) * inside
    if phase is None:
        line = np.clip(1.0 - np.abs(d + 0.9) / 0.9, 0, 1)[..., None]
        return b"P6 %d %d 255 " % (w, h) + (out * (1 - line) + np.array(hue(accent), np.float32) * line + 0.5) \
            .clip(0, 255).astype("uint8").tobytes()
    angle = (np.arctan2(ys - h / 2, (xs - w / 2) * (h / max(w, 1))) / (2 * math.pi) + 0.5 + phase) % 1.0
    tri = 1 - np.abs(angle * 2 - 1)  # 0 to 1 to 0 round the edge: the gradient there and back, so it loops
    grad = np.stack([np.interp(tri, np.linspace(0, 1, len(stops)), [hue(s)[k] for s in stops]) for k in range(3)], -1)
    line = np.clip(1.0 - np.abs(d + 1.2) / 1.3, 0, 1)[..., None]
    glow = (np.exp(np.minimum(d, 0) / 9.0) * (d < 0) * 0.22)[..., None]
    out = out * (1 - glow) + grad * glow
    out = out * (1 - line) + grad * line
    return b"P6 %d %d 255 " % (w, h) + (out + 0.5).clip(0, 255).astype("uint8").tobytes()


def png_rgba(rgba):
    """An RGBA numpy array (h, w, 4 of uint8) as a PNG's bytes, with nothing but zlib: its alpha kept, so Tk lays it
    over whatever is under it (the aurora) with soft edges."""
    import struct
    import zlib

    import numpy as np
    h, w = rgba.shape[:2]
    raw = np.zeros((h, w * 4 + 1), np.uint8)
    raw[:, 1:] = np.ascontiguousarray(rgba).reshape(h, w * 4)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (bytes((137, 80, 78, 71, 13, 10, 26, 10)) + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw.tobytes(), 6)) + chunk(b"IEND", b""))


def greeting_png(text, family, size, stops=STOPS, weight=600):
    """The greeting as a PNG with its alpha: its letters in the gradient and nothing round them, to lie over the
    aurora. (its bytes, width, height)"""
    import numpy as np
    mask = text_mask(text, family, size, weight)
    h, w = mask.shape
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    grad = np.stack([np.interp(xs, np.linspace(0, 1, len(stops)), [hue(s)[k] for s in stops]) for k in range(3)], -1)
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., :3] = (np.broadcast_to(grad[None, :, :], (h, w, 3)) + 0.5).astype(np.uint8)
    rgba[..., 3] = (mask * 255 + 0.5).clip(0, 255).astype(np.uint8)
    return png_rgba(rgba), w, h


def pill_png(w, h, r, fill):
    """A rounded pill of fill as a PNG with its alpha: soft-edged, with nothing round it."""
    import numpy as np
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32) + 0.5
    qx, qy = np.abs(xs - w / 2) - (w / 2 - r), np.abs(ys - h / 2) - (h / 2 - r)
    d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., :3] = hue(fill)
    rgba[..., 3] = (np.clip(0.5 - d, 0, 1) * 255 + 0.5).astype(np.uint8)
    return png_rgba(rgba)
