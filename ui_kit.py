"""The look's shared parts, for her window and what opens over it (22 November 2026, the owner: "the best UI, like
Hedwig's, smooth, with genie animations, the common elements too"): the curves its motion runs on, read off
hedwig-ai.com's own styles; colours mixed; the rounded shapes her window is made of, drawn once with soft edges (Tk's
own polygons and ovals are jagged on Windows, a browser's aren't); and Windows' title bar painted in her sidebar's
colour. Nothing here starts a timer or a thread by itself, and numpy is only loaded when a shape is drawn, so it costs
her start nothing."""
import ctypes
import math
import re
import sys
import time
import tkinter as tk


# ------------------------------------------------------------------ motion
def bezier(x1, y1, x2, y2):
    """The CSS curve cubic-bezier(x1, y1, x2, y2) as a function of time, 0 to 1: how far along it is, 0 to 1, or past
    1 for a curve that overshoots and settles back, as Hedwig's pop does."""
    cx = 3.0 * x1
    bx = 3.0 * (x2 - x1) - cx
    ax = 1.0 - cx - bx
    cy = 3.0 * y1
    by = 3.0 * (y2 - y1) - cy
    ay = 1.0 - cy - by

    def x_at(s):
        return ((ax * s + bx) * s + cx) * s

    def y_at(s):
        return ((ay * s + by) * s + cy) * s

    def slope(s):
        return (3.0 * ax * s + 2.0 * bx) * s + cx

    def curve(t):
        if t <= 0.0:
            return 0.0
        if t >= 1.0:
            return 1.0
        s = t
        for _ in range(8):  # Newton's way to the s whose x is t, quick where the curve is smooth
            err = x_at(s) - t
            if abs(err) < 1e-6:
                return y_at(s)
            d = slope(s)
            if abs(d) < 1e-6:
                break
            s -= err / d
        lo, hi, s = 0.0, 1.0, t  # and halving, for where it's too flat for that
        for _ in range(60):
            err = x_at(s) - t
            if abs(err) < 1e-6:
                break
            lo, hi = (s, hi) if err < 0 else (lo, s)
            s = (lo + hi) / 2
        return y_at(s)
    return curve


# Hedwig's, from its styles (22 November 2026): what each is for, and how long it runs there
POP = bezier(.2, .9, .2, 1)  # a palette or a box coming in (0.18 s), a drawer dropping open (0.26 s), a row rising
ARRIVE = bezier(.22, 1, .36, 1)  # a thing settling into its place
STATE = bezier(.4, 0, .2, 1)  # a colour or a state changing (0.12 to 0.15 s)
SPRING = bezier(.34, 1.56, .64, 1)  # a small overshoot, for a pop that lands
GLIDE = bezier(.22, .8, .2, 1)  # the demo's camera, and what rises into the chat (0.55 to 0.9 s)


def ease(t):
    return 1 - (1 - t) ** 3  # quick, then settling


def mix(a, b, t):
    """The colour t of the way from a to b, both "#rrggbb", each part kept in range for a curve that overshoots."""
    a, b = int(a[1:], 16), int(b[1:], 16)
    return "#" + "".join(f"{max(0, min(255, round(((a >> s) & 255) * (1 - t) + ((b >> s) & 255) * t))):02x}"
                         for s in (16, 8, 0))


def motion_ok():
    """False if Windows is set to show no animations (Settings > Accessibility > Visual effects): hers that only
    please then stay still."""
    on = ctypes.c_int(1)
    try:
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(on), 0)  # SPI_GETCLIENTAREAANIMATION
    except (AttributeError, OSError):
        return True
    return bool(on.value)


_AT = re.compile(r"(\d+)x(\d+)([+-])(-?\d+)([+-])(-?\d+)")


def place_of(top):
    """(width, height, x, y) of a window as its geometry says, which can put it on a screen to the left or above the
    main one ("+-1920+0")."""
    w, h, sx, x, sy, y = _AT.fullmatch(top.geometry()).groups()
    return int(w), int(h), int(x) * (-1 if sx == "-" else 1), int(y) * (-1 if sy == "-" else 1)


def pop(top, root, enter=True, ms=180, rise=6, peak=1.0, curve=None, done=None):
    """A window coming in the way Hedwig's palette does (search-palette-in, 0.18 s on POP: from 6 px above and faded in)
    or going out (hw-overlay-out, shorter and smaller): its see-through and, with rise, its place, eased. peak is the
    most solid it gets (a veil's 0.14). Nothing is left running; done() once it's over. With Windows' animations off,
    it just is, or is gone."""
    curve = curve or POP
    if not motion_ok() or ms <= 0:
        _set(top, peak if enter else 0.0)
        if done:
            done()
        return
    w, h, x, y = place_of(top)
    began = time.perf_counter()

    def frame():
        t = min(1.0, (time.perf_counter() - began) * 1000 / ms)
        k = curve(t) if enter else 1.0 - curve(t)  # 1 is as it sits
        try:
            top.attributes("-alpha", max(0.0, min(peak, peak * k)))
            if rise:
                top.geometry(f"{w}x{h}+{x}+{y - round(rise * (1.0 - k))}")
        except tk.TclError:  # closed meanwhile
            return
        if t < 1.0:
            root.after(15, frame)
        elif done:
            done()
    frame()


def _set(top, alpha):
    try:
        top.attributes("-alpha", alpha)
    except tk.TclError:
        pass


# ------------------------------------------------------------------ Windows' title bar
def windows_build():
    """Windows' build number (22000 and up is Windows 11), 0 where there's no such thing."""
    try:
        return sys.getwindowsversion().build
    except AttributeError:
        return 0


def colorref(colour):
    """"#rrggbb" as Windows has a colour, 0x00bbggrr."""
    r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    return (b << 16) | (g << 8) | r


def chrome_attrs(build, bg, fg, dark):
    """(DWM attribute, value) to set so a window's title bar is bg with fg words, for this Windows: its buttons light
    or dark (20, from 2004 on), and the caption, its words and its edge in those colours (34, 35, 36, Windows 11
    only). Windows 10 gets what it can do, the buttons' light or dark; older ones nothing."""
    attrs = []
    if build >= 19041:
        attrs.append((20, 1 if dark else 0))
    if build >= 22000:
        attrs += [(35, colorref(bg)), (36, colorref(fg)), (34, colorref(bg))]
    return attrs


def title_bar(window, bg, fg, dark, build=None, set_attribute=None):
    """window's title bar painted bg with fg words, dark: the buttons in white. It stays the system's where Windows
    can't do it. build and set_attribute are for a test."""
    attrs = chrome_attrs(windows_build() if build is None else build, bg, fg, dark)
    if not attrs:
        return []
    if set_attribute is None:
        try:
            hwnd = ctypes.windll.user32.GetAncestor(window.winfo_id(), 2)  # GA_ROOT: the frame, not Tk's inner one

            def set_attribute(attr, value):
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(ctypes.c_int(value)), 4)
        except (AttributeError, OSError):
            return []
    done = []
    for attr, value in attrs:
        try:
            set_attribute(attr, value)
            done.append(attr)
        except (AttributeError, OSError):
            pass
    return done


# ------------------------------------------------------------------ shapes
def parse(colour):
    """"#rrggbb" as (r, g, b)."""
    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))


def rrect(w, h, r, fill, back, line=None, lw=1.0):
    """A rounded rectangle w by h px with corners of radius r, fill over back with soft edges, and with line a hairline
    lw px wide just inside its edge, as an array (h, w, 3) of bytes. r of half the height is a pill, of half both a
    circle."""
    import numpy as np
    w, h = max(1, int(w)), max(1, int(h))
    r = max(0.0, min(float(r), w / 2, h / 2))
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32) + 0.5
    qx = np.abs(xs - w / 2) - (w / 2 - r)
    qy = np.abs(ys - h / 2) - (h / 2 - r)
    dist = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r  # in it below 0
    shape = np.clip(0.5 - dist, 0.0, 1.0)[..., None]
    rgb = lambda c: np.array(parse(c), np.float32)  # noqa: E731
    if line is None:
        pixels = rgb(back) * (1 - shape) + rgb(fill) * shape
    else:
        inner = np.clip(0.5 - (dist + lw), 0.0, 1.0)[..., None]
        pixels = rgb(back) * (1 - shape) + rgb(line) * (shape - inner) + rgb(fill) * inner
    return (pixels + 0.5).astype(np.uint8)


def ppm(rgb):
    """An array (h, w, 3) of bytes as PPM, for a Tk PhotoImage (format="ppm")."""
    h, w = rgb.shape[:2]
    return b"P6 %d %d 255 " % (w, h) + rgb.tobytes()


def corners(r, fill, back, line=None, lw=1.0):
    """The four corners of a rounded rectangle of radius r, each r by r: (top left, top right, bottom left, bottom
    right). The straight parts between them are only lines and fills, which need no softening."""
    big = rrect(2 * r, 2 * r, r, fill, back, line, lw)
    return big[:r, :r], big[:r, r:], big[r:, :r], big[r:, r:]


def _segment(xs, ys, p, q):
    """How far each of the points xs, ys is from the line from p to q."""
    import numpy as np
    dx, dy = q[0] - p[0], q[1] - p[1]
    t = np.clip(((xs - p[0]) * dx + (ys - p[1]) * dy) / (dx * dx + dy * dy), 0.0, 1.0)
    return np.hypot(xs - p[0] - t * dx, ys - p[1] - t * dy)


def chevron(size, colour, back, stroke=1.6, up=False):
    """A small chevron, pointing down or with up up, size px square, on back: a drop-down's arrow, a fold's, drawn as two
    soft strokes (Windows' own arrow in a box is a hard triangle)."""
    import numpy as np
    s = float(size)
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32) + 0.5
    a, b, c = (0.22 * s, 0.38 * s), (0.5 * s, 0.64 * s), (0.78 * s, 0.38 * s)
    if up:
        a, b, c = ((x, s - y) for x, y in (a, b, c))
    near = np.minimum(_segment(xs, ys, a, b), _segment(xs, ys, b, c))
    ink = np.clip(stroke / 2 + 0.5 - near, 0.0, 1.0)[..., None]
    rgb = lambda col: np.array(parse(col), np.float32)  # noqa: E731
    return (rgb(back) * (1 - ink) + rgb(colour) * ink + 0.5).astype(np.uint8)


def pad(rgb, back, left=0, top=0, right=0, bottom=0):
    """rgb with a margin of the back colour round it, so a small shape sits where it should in a bigger picture."""
    import numpy as np
    h, w = rgb.shape[:2]
    out = np.empty((h + top + bottom, w + left + right, 3), np.uint8)
    out[:] = parse(back)
    out[top:top + h, left:left + w] = rgb
    return out


def images(root):
    """The pictures made for root's windows, kept by what they are, so one is made once: Tk lets go of a picture nothing
    holds, and a thread of cards each making its own would be a thousand of them."""
    return root._root().__dict__.setdefault("_ui_images", {})  # on the application, whichever of its widgets asks


def corner_images(root, r, fill, back, line=None, lw=1.0):
    """The four corners (corners) as Tk pictures, made once."""
    key = ("corners", r, fill, back, line, lw)
    cache = images(root)
    if key not in cache:
        cache[key] = [tk.PhotoImage(master=root, data=ppm(a), format="ppm") for a in corners(r, fill, back, line, lw)]
    return cache[key]


TILE = (192, 48)  # the plain middle of a nine-patch, px wide and high


def nine(root, r, fill, back, line=None, lw=1.0):
    """A rounded box as one small picture to be stretched by a ttk image element, whose border is r + 1: the corners kept
    as they are, the plain edges and middle tiled between them. Made once for each look.

    ttk tiles the middle, one blit for each copy of it, so a middle of two pixels made a wide box a few thousand blits
    and her Keys page, with its two dozen boxes, took 1.8 s to open (22 November 2026): the middle is as big as a
    box ever needs to be, and a wide one is a few copies."""
    key = ("nine", r, fill, back, line, lw)
    cache = images(root)
    if key not in cache:
        b = r + 1
        cache[key] = tk.PhotoImage(master=root, data=ppm(rrect(2 * b + TILE[0], 2 * b + TILE[1], r, fill, back, line, lw)),
                                   format="ppm")
    return cache[key]


def picture(root, key, make):
    """make() as a Tk picture (an array from rrect or chevron), made once for key."""
    cache = images(root)
    if key not in cache:
        cache[key] = tk.PhotoImage(master=root, data=ppm(make()), format="ppm")
    return cache[key]


class Backdrop:
    """A rounded, hairline-edged ground drawn behind a frame's own children, which stay as they were, packed and gridded
    in it (22 November 2026: her cards had square corners beside her rounded box and buttons). A canvas placed over the
    whole frame and lowered under what's in it; it paints its four soft corners and plain lines and fills between them,
    which is a dozen items moved when the frame's size changes, so a card can be dragged as wide as you like.

    The frame's padding should clear its corners, about a third of the radius and a bit more."""

    def __init__(self, frame, radius, fill, line, back, lw=1):
        self.frame, self.r, self.lw = frame, int(radius), lw
        self.fill, self.line, self.back = fill, line, back
        c = self.canvas = tk.Canvas(frame, bg=back, highlightthickness=0, bd=0)
        c.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.lower(c)  # the widget under the frame's own children, not Canvas.lower, which is for items
        self.size = (0, 0)
        self.tiles = [c.create_image(0, 0, anchor="nw") for _ in range(4)]
        self.fills = [c.create_rectangle(0, 0, 0, 0, fill=fill, width=0) for _ in range(2)]
        self.edges = [c.create_rectangle(0, 0, 0, 0, fill=line, width=0) for _ in range(4)] if line else []
        self.restyle(fill, line)
        c.bind("<Configure>", self._lay)

    def restyle(self, fill=None, line=None):
        """Another ground or edge colour, as for a card under the mouse."""
        self.fill = fill or self.fill
        self.line = line if line is not None else self.line
        for tile, image in zip(self.tiles, corner_images(self.canvas, self.r, self.fill, self.back,
                                                         self.line if self.edges else None, self.lw)):
            self.canvas.itemconfigure(tile, image=image)
        for item in self.fills:
            self.canvas.itemconfigure(item, fill=self.fill)
        for item in self.edges:
            self.canvas.itemconfigure(item, fill=self.line)

    def _lay(self, event=None):
        c, r, lw = self.canvas, self.r, self.lw
        w, h = c.winfo_width(), c.winfo_height()
        if (w, h) == self.size or w < 2 * r or h < 2 * r:
            return
        self.size = (w, h)
        for tile, (x, y) in zip(self.tiles, ((0, 0), (w - r, 0), (0, h - r), (w - r, h - r))):
            c.coords(tile, x, y)
        c.coords(self.fills[0], r, 0, w - r, h)
        c.coords(self.fills[1], 0, r, w, h - r)
        if self.edges:
            for item, box in zip(self.edges, ((r, 0, w - r, lw), (r, h - lw, w - r, h), (0, r, lw, h - r),
                                              (w - lw, r, w, h - r))):
                c.coords(item, *box)
            # the fills run to the very edge, under the lines: the lines are drawn over them
            for item in self.edges:
                c.tag_raise(item)
        for tile in self.tiles:
            c.tag_raise(tile)
