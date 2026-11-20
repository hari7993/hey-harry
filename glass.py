"""Frosted glass for her window (20 November 2026, the owner's ask: "a frosted glass effect so that we can see some
of the background seep through subtly", her other panels too). The desktop's wallpaper, blurred soft and washed
towards white, is drawn behind her sidebar, the top of her window and her quick actions, cut to where each is on the
screen, so it moves under them as the window does: what Windows 11 calls Mica. Made here rather than asked of
Windows, whose own backdrop only shows through pixels drawn black: Tk draws with GDI, which leaves no alpha, so
near-black words on it would turn to glass too. The wallpaper is read and blurred once, on a thread, at an eighth of
its size (about 0.15 s, once), and only that small picture is kept, about 100 kB: the owner's rule is that she stays
light. A move of the window draws out the bit behind each panel again, a few ms. No wallpaper to read (a plain
colour) means no glass, and her window is white as it was."""
import ctypes
import os

SPI_GETDESKWALLPAPER = 0x0073
SMALLER = 8  # the wallpaper is blurred at one in this many of its pixels: frosted glass has no detail to lose
SOFT = 0.045  # how far the blur reaches, of the screen's width


def wallpaper():
    """The desktop wallpaper's file, or None for a plain colour or one that isn't there."""
    buf = ctypes.create_unicode_buffer(520)
    try:
        ok = ctypes.windll.user32.SystemParametersInfoW(SPI_GETDESKWALLPAPER, len(buf), buf, 0)
    except (AttributeError, OSError):
        return None
    return buf.value if ok and buf.value and os.path.isfile(buf.value) else None


def frost(size, path=None):
    """The wallpaper as frosted glass has it, for a screen of size (w, h): filling the screen as Windows' Fill does,
    blurred and a touch richer in colour, kept small: an array of one in SMALLER of the screen's pixels each way, by
    3, 0-255 in RGB (pane draws it out to full size). None if there's no wallpaper or it can't be read."""
    path = path or wallpaper()
    if not path:
        return None
    try:
        import cv2
        import numpy as np
        picture = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)  # fromfile: any letters in its path
        if picture is None:
            return None
        w, h = int(size[0]), int(size[1])
        sw, sh = max(8, w // SMALLER), max(8, h // SMALLER)
        ph, pw = picture.shape[:2]
        scale = max(sw / pw, sh / ph)  # Fill: all of the screen covered, the rest cut off evenly
        fit = cv2.resize(picture, (max(sw, round(pw * scale)), max(sh, round(ph * scale))), interpolation=cv2.INTER_AREA)
        x, y = (fit.shape[1] - sw) // 2, (fit.shape[0] - sh) // 2
        small = cv2.GaussianBlur(fit[y:y + sh, x:x + sw], (0, 0), max(2.0, sw * SOFT))
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[..., 1] = np.clip(hsv[..., 1] * 1.25, 0, 255)  # washed towards white next, so a little colour to spare
        small = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
        return cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    except Exception as exc:  # a picture cv2 can't read: white, as before
        print(f"  no frosted glass: {exc!r}")
        return None


def pane(frosted, x, y, w, h, white, step=1):
    """The w by h of the glass at x, y on the screen: frosted (frost's, one in SMALLER of the screen's pixels) drawn
    out smooth to full size there and washed towards white by white (0 the wallpaper as blurred, 1 plain white), an
    array h by w by 3 of 0-255. Only what's behind a panel is ever made, a few ms each time the window moves, so all
    she keeps is the small picture, about 100 kB. step: one pixel in that many each way, for a panel's whole
    background, which Tk then draws out (20 November 2026: at every pixel a sidebar and the top took 86 ms, and
    opening a page stuttered; one in 4 is 16 times less, and glass this soft shows no difference). Off the screen's
    edge (a window dragged half away, another monitor) it's the edge's own colour carried on."""
    import numpy as np
    sh, sw = frosted.shape[:2]
    fy = np.clip((np.arange(y, y + h, step) + step / 2) / SMALLER - 0.5, 0, sh - 1)
    fx = np.clip((np.arange(x, x + w, step) + step / 2) / SMALLER - 0.5, 0, sw - 1)
    y0, x0 = fy.astype(np.intp), fx.astype(np.intp)
    y1, x1 = np.minimum(y0 + 1, sh - 1), np.minimum(x0 + 1, sw - 1)
    wy, wx = (fy - y0).astype(np.float32)[:, None, None], (fx - x0).astype(np.float32)[None, :, None]
    rows = frosted[y0].astype(np.float32) * (1 - wy) + frosted[y1].astype(np.float32) * wy
    full = rows[:, x0] * (1 - wx) + rows[:, x1] * wx
    return (full * (1 - white) + 255.0 * white + 0.5).astype(np.uint8)


def cut(frosted, x, y, w, h, white, step=1):
    """pane's, as a PPM picture for tk.PhotoImage."""
    made = pane(frosted, x, y, w, h, white, step)
    return b"P6 %d %d 255 " % (made.shape[1], made.shape[0]) + made.tobytes()
