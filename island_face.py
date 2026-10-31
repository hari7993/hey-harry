"""Her face in the island, as Nixi (heynixi.com) has one: two glowing eyes that blink, look around, wear glasses
while she reads the screen, headphones while music plays, turn to hearts when you say thanks, and nod off when
nothing's happened for a while. Drawn with numpy as signed distances, a few hundred pixels round each eye, so a
frame costs well under a millisecond; between blinks nothing is drawn at all.

The glass capsule (27 October 2026) has the same eyes, glowing in the colour of what she's doing (halo).

The shapes and glyphs the island's plugins use (a battery, play and pause, a progress ring, a tick) are here too, and
since 30 October 2026 (the owner's pictures of an iPhone's island) those of its live activities: a moon for dream
mode, a recording dot, a hand, a pointer, a pause, and a voice's waveform. She sleeps in dream mode, z's and all.
"""
import math
import random
import time

import numpy as np

# --------------------------------------------------------------------------- shapes, as signed distances in px


def rbox(px, py, cx, cy, hw, hh, r):
    """A rounded rectangle centred on cx, cy: less than 0 inside."""
    r = max(0.0, min(r, hw, hh))
    qx, qy = np.abs(px - cx) - (hw - r), np.abs(py - cy) - (hh - r)
    return np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0)) + np.minimum(np.maximum(qx, qy), 0.0) - r


def circle(px, py, cx, cy, r):
    return np.hypot(px - cx, py - cy) - r


def segment(px, py, ax, ay, bx, by, width):
    """A line from a to b, width px wide, with round ends."""
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy or 1e-6
    h = np.clip(((px - ax) * dx + (py - ay) * dy) / length, 0.0, 1.0)
    return np.hypot(px - ax - h * dx, py - ay - h * dy) - width / 2


def arc(px, py, cx, cy, r, width, up=True):
    """The top (or bottom) half of a ring, with round ends: "^" eyes, a headphones' band."""
    dy = (py - cy) if up else (cy - py)
    ring = np.abs(np.hypot(px - cx, py - cy) - r) - width / 2
    ends = np.minimum(np.hypot(px - (cx - r), py - cy), np.hypot(px - (cx + r), py - cy)) - width / 2
    return np.where(dy <= 0, ring, ends)


def heart(px, py, cx, cy, size):
    """A heart about size px tall, point down (Inigo Quilez's heart)."""
    x = np.abs(px - cx) / size
    y = (cy + size * 0.52 - py) / size  # its point at the bottom
    d1 = np.hypot(x - 0.25, y - 0.75) - math.sqrt(2) / 4
    m = 0.5 * np.maximum(x + y, 0.0)
    d2 = np.sqrt(np.minimum((x - 0.0) ** 2 + (y - 1.0) ** 2, (x - m) ** 2 + (y - m) ** 2)) * np.sign(x - y)
    return np.where(x + y > 1.0, d1, d2) * size


def polygon(px, py, points):
    """A convex shape through points, either way round: the furthest of its edges' lines, near enough a
    distance for a pixel's smooth edge."""
    n = len(points)
    area = sum(points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1] for i in range(n))
    if area < 0:  # anticlockwise on screen: the same edges the other way
        points = points[::-1]
    d = None
    for i in range(n):
        (ax, ay), (bx, by) = points[i], points[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        length = math.hypot(ex, ey) or 1e-6
        nx, ny = ey / length, -ex / length  # outwards, for points going round clockwise with y down
        side = (px - ax) * nx + (py - ay) * ny
        d = side if d is None else np.maximum(d, side)
    return d


# --------------------------------------------------------------------------- drawing into the island's pixels
class Canvas:
    """The island's colours, (h, w, 3) floats 0 to 1, drawn into a region at a time. ox, oy: where col's first
    pixel is in the coordinates things are drawn at, when col is only a part of the picture (whole pixels).
    op: for the glass capsule (27 October 2026), how opaque each pixel is, (h, w) 0 to 1, with col premultiplied by
    it: what's drawn goes over both, so words on the see-through glass come out solid."""

    def __init__(self, col, ox=0, oy=0, op=None):
        self.col = col
        self.h, self.w = col.shape[:2]
        self.ox, self.oy = int(ox), int(oy)
        self.op = op

    def _over(self, sl, m):
        """What's drawn with cover m (h, w, 1) makes those pixels that much more opaque (glass only)."""
        if self.op is not None:
            o = self.op[sl]
            o *= 1 - m[..., 0]
            o += m[..., 0]

    def region(self, x0, y0, x1, y1):
        """(slices of col, the pixels' x and y where they're drawn) for a box, or None if it's off col."""
        X0, Y0 = max(0, int(math.floor(x0 - self.ox))), max(0, int(math.floor(y0 - self.oy)))
        X1, Y1 = min(self.w, int(math.ceil(x1 - self.ox))), min(self.h, int(math.ceil(y1 - self.oy)))
        if X1 <= X0 or Y1 <= Y0:
            return None
        xs = np.arange(X0, X1, dtype=np.float32) + (0.5 + self.ox)
        ys = np.arange(Y0, Y1, dtype=np.float32)[:, None] + (0.5 + self.oy)
        return (slice(Y0, Y1), slice(X0, X1)), xs, ys

    def _part(self, pic, sl, X0, Y0):
        """The part of a picture placed at X0, Y0 that lands on the slices sl of col."""
        py, px = sl[0].start + self.oy - Y0, sl[1].start + self.ox - X0
        return pic[py:py + sl[0].stop - sl[0].start, px:px + sl[1].stop - sl[1].start]

    def shape(self, sd, bounds, colour, a=1.0, glow=0.0, spread=4.0, halo=None):
        """Fill sd(xs, ys) < 0 with colour; glow: light added round it, fading over spread px, in halo's colour if
        one's given (the capsule's eyes glow in the colour of what she's doing), else colour's."""
        r = self.region(*bounds)
        if r is None or a <= 0.003:
            return
        sl, xs, ys = r
        d = sd(xs, ys)
        dst = self.col[sl]
        colour = np.asarray(colour, np.float32)
        if glow > 0:
            g = np.exp(-np.maximum(d, 0.0) / spread) * (glow * a)
            dst += (colour if halo is None else np.asarray(halo, np.float32)) * g[..., None]
        cover = (np.clip(0.5 - d, 0.0, 1.0) * a)[..., None]
        dst *= 1 - cover
        dst += colour * cover
        self._over(sl, cover)

    def image(self, rgba, x, y, a=1.0):
        """A picture with its own alpha, premultiplied (island_art), at x, y."""
        h, w = rgba.shape[:2]
        X0, Y0 = int(round(x)), int(round(y))  # whole pixels, so the picture and its place are the same size
        r = self.region(X0, Y0, X0 + w, Y0 + h)
        if r is None or a <= 0.003:
            return
        sl = r[0]
        part = self._part(rgba, sl, X0, Y0)
        dst = self.col[sl]
        alpha = part[..., 3:4] * a
        dst *= 1 - alpha
        dst += part[..., :3] * a
        self._over(sl, alpha)

    def text(self, cover, x, y, colour, a=1.0):
        """Words (bubble.Text.render), in colour."""
        h, w = cover.shape
        X0, Y0 = int(round(x)), int(round(y))
        r = self.region(X0, Y0, X0 + w, Y0 + h)
        if r is None or a <= 0.003:
            return
        sl = r[0]
        m = (self._part(cover, sl, X0, Y0) * a)[..., None]
        dst = self.col[sl]
        dst *= 1 - m
        dst += np.asarray(colour, np.float32) * m
        self._over(sl, m)


# --------------------------------------------------------------------------- the eyes
WHITE = (0.97, 0.97, 0.98)
PINK = (1.0, 0.33, 0.6)
GOLD = (1.0, 0.84, 0.38)
RED = (1.0, 0.27, 0.23)
# the expressions, for Settings and for siri's "Mood": what each one is for
MOODS = {
    "open": "listening, and looking about when nothing's going on",
    "happy": "^ ^ when something's done, or you say hello",
    "love": "hearts when you say thanks",
    "surprised": "wide open when a notification comes in",
    "focus": "narrowed while she does something",
    "think": "looking up while she thinks",
    "glasses": "reading glasses while she looks at the screen",
    "headphones": "headphones while music plays",
    "sleepy": "half closed after a few quiet minutes",
    "sad": "drooping when something went wrong or the battery's low",
    "side": "a side look when it wasn't for her",
    "x": "crossed out for an error",
    "dream": "asleep and dreaming while dream mode is on",
}
STILL = ("love", "happy", "x", "sad", "dream")  # looks that keep her eyes in the middle, never glancing about
REACT_FOR = {"love": 2.6, "happy": 1.8, "surprised": 1.0, "sad": 2.2}  # seconds a reaction lasts
BLINKING = ("open", "surprised", "focus", "think", "glasses", "headphones", "sleepy", "side")  # the looks that blink


class Eyes:
    """Where the eyes are looking and how open they are, frame by frame: blinks every few seconds, glances about
    when there's nothing to do, and reactions (react) for a moment. update says when it next needs a frame."""

    def __init__(self, now=None):
        now = time.time() if now is None else now  # not 0: she'd start out asleep, five minutes "quiet" since then
        self.next_blink, self.blink_at, self.double = now + 2.0, None, False
        self.look = [0.0, 0.0]  # where it looks, -1 to 1 across and down, sprung to target
        self.look_v = [0.0, 0.0]
        self.target, self.next_look, self.hold_until = [0.0, 0.0], now + 4.0, 0.0
        self.mood, self.mood_until = None, 0.0
        self.last_active = now
        self.shown = "open"  # the look last drawn (update), for wait

    def react(self, mood, now):
        if mood in MOODS:
            self.mood, self.mood_until = mood, now + REACT_FOR.get(mood, 1.6)
            self.last_active = now

    def wake(self, now):
        self.last_active = now

    def update(self, now, dt, kind, wander=True, look_at=None):
        """(the expression to draw, how open 0 to 1, look x, look y, whether it's moving). kind: the scene's own
        expression; a reaction goes over it for a moment. look_at: where to look instead, -1 to 1, as at the
        mouse."""
        if self.mood and now >= self.mood_until:
            self.mood = None
        expr = self.mood or kind
        if expr == "open" and wander and now - self.last_active > 300:
            expr = "sleepy"  # five quiet minutes
        # blinks: closed for about a sixth of a second, sometimes twice
        open_ = 1.0
        self.shown = expr
        blinking = expr in BLINKING
        if self.blink_at is None and now >= self.next_blink and blinking:
            self.blink_at = now
        if self.blink_at is not None:
            u = (now - self.blink_at) / 0.17
            if u >= 1:
                self.blink_at = None
                if not self.double and random.random() < 0.18:
                    self.double, self.next_blink = True, now + 0.12
                else:
                    self.double = False
                    gap = (5.0, 9.0) if expr == "sleepy" else (2.6, 6.2)
                    self.next_blink = now + random.uniform(*gap)
            else:
                open_ = 1 - 0.9 * math.sin(math.pi * u)
        # where it looks
        if look_at is not None and expr not in ("love", "happy", "x", "dream"):
            self.target = [float(look_at[0]), float(look_at[1])]
            self.last_active = now
        elif expr == "think":
            self.target = [0.55 if int(now / 1.4) % 2 else -0.55, -0.75]
        elif expr in ("focus",):
            self.target = [0.45 * math.sin(now * 1.7), 0.35]
        elif expr == "side":
            self.target = [0.95, 0.1]
        elif not wander or expr in STILL:
            self.target = [0.0, 0.0]
        elif now >= self.next_look:
            if self.target != [0.0, 0.0] or random.random() < 0.35:
                self.target, self.next_look = [0.0, 0.0], now + random.uniform(2.5, 6.0)
            else:
                self.target = random.choice([[-0.9, 0.0], [0.9, 0.0], [-0.6, -0.55], [0.6, -0.55], [0.0, 0.5],
                                             [-0.7, 0.35], [0.7, 0.35]])
                self.next_look = now + random.uniform(0.8, 1.9)
        moving = self.blink_at is not None
        for i in (0, 1):  # a quick, slightly springy glance
            k, c = 260.0, 26.0
            steps = max(1, math.ceil(dt / 0.004))
            h = dt / steps
            for _ in range(steps):
                self.look_v[i] += (-k * (self.look[i] - self.target[i]) - c * self.look_v[i]) * h
                self.look[i] += self.look_v[i] * h
            moving = moving or abs(self.look[i] - self.target[i]) > 0.004 or abs(self.look_v[i]) > 0.02
        return expr, open_, self.look[0], self.look[1], moving

    def wait(self, now):
        """Seconds till the next blink or glance, when nothing else moves; an hour for a look that never blinks
        (asleep in dream mode, a smile), whose next blink would be long past and ask for every frame (30 October
        2026: dream mode drew 60 frames a second for as long as it was on)."""
        if self.shown not in BLINKING:
            return 3600.0
        return max(0.016, min(self.next_blink, self.next_look) - now)


def draw_eyes(cv, cx, cy, size, expr, open_=1.0, look=(0.0, 0.0), level=0.0, t=0.0, colour=WHITE, glow=True,
              a=1.0, halo=None):
    """Two eyes centred on cx, cy, each size px tall when open. level: a voice, 0 to 1, that makes them bounce.
    halo: the colour of their glow when it isn't their own (the glass capsule's, tinted by what's going on); the
    hearts keep their pink."""
    if a <= 0.003:
        return
    gx = glow * 0.5 if glow else 0.0
    spread = size * 0.2
    ew = size * 0.6
    gap = size * 2.0  # between their centres
    bounce = 1 + 0.12 * level
    lx, ly = look[0] * size * 0.36, look[1] * size * 0.26 - level * size * 0.08
    pad = size * 1.4

    def eye_box(ex, ey, w, h):
        return (ex - w - pad * 0.5, ey - h - pad * 0.5, ex + w + pad * 0.5, ey + h + pad * 0.5)

    for side in (-1, 1):
        ex, ey = cx + side * gap / 2 + lx, cy + ly
        if expr == "happy":
            r, w = size * 0.4, size * 0.22
            cv.shape(lambda xs, ys: arc(xs, ys, ex, ey + size * 0.16, r, w), eye_box(ex, ey, r, r), colour, a,
                     gx, spread, halo)
        elif expr == "love":
            s = size * 1.15 * (1 + 0.07 * math.sin(t * 7.5))
            cv.shape(lambda xs, ys: heart(xs, ys, ex, ey, s), eye_box(ex, ey, s * 0.7, s * 0.7), PINK, a,
                     0.55 if glow else 0.0, spread * 1.3)
        elif expr == "x":
            r, w = size * 0.34, size * 0.17
            cv.shape(lambda xs, ys: np.minimum(segment(xs, ys, ex - r, ey - r, ex + r, ey + r, w),
                                               segment(xs, ys, ex - r, ey + r, ex + r, ey - r, w)),
                     eye_box(ex, ey, r, r), RED, a, gx, spread)
        elif expr == "dream":  # shut, curving down like a smile, rising and falling slowly as she breathes
            r, w = size * 0.4, size * 0.19
            dy = math.sin(t * 1.3) * size * 0.06 - size * 0.16
            cv.shape(lambda xs, ys, ex=ex, ey=ey + dy: arc(xs, ys, ex, ey, r, w, up=False),
                     eye_box(ex, ey + dy + r * 0.5, r, r), colour, a, gx, spread, halo)
        else:
            w = ew * (1.12 if expr == "surprised" else 0.86 if expr == "glasses" else 1.0)
            h = size * (1.18 if expr == "surprised" else 0.84 if expr == "glasses" else 1.0) * bounce
            if expr == "focus":
                h *= 0.58
            elif expr == "sleepy":
                h *= 0.3
            elif expr == "side":
                h *= 0.62
            h = max(size * 0.1, h * open_)
            yo = (size - h) * (0.32 if expr in ("sleepy", "focus", "side") else 0.0)  # lids come down, not up
            hw, hh = w / 2, h / 2
            if expr == "sad":  # the inner corners up: a worried look
                def sd(xs, ys, ex=ex, ey=ey + yo, hw=hw, hh=hh, side=side):
                    body = rbox(xs, ys, ex, ey, hw, hh, hw)
                    nx, ny = side * 0.55, -1.0  # cut lower on the outside, so the outer corners droop
                    norm = math.hypot(nx, ny)
                    lid = ((xs - ex) * nx + (ys - (ey - hh * 0.5)) * ny) / norm
                    return np.maximum(body, lid)
            else:
                def sd(xs, ys, ex=ex, ey=ey + yo, hw=hw, hh=hh):
                    return rbox(xs, ys, ex, ey, hw, hh, min(hw, hh))
            cv.shape(sd, eye_box(ex, ey + yo, hw, hh), colour, a, gx, spread, halo)
            if expr == "glasses":  # round frames over the eyes, and the bridge
                r, lw = size * 0.62, max(1.2, size * 0.09)
                cv.shape(lambda xs, ys: np.abs(circle(xs, ys, ex, ey, r)) - lw / 2, eye_box(ex, ey, r + lw, r + lw),
                         colour, a, gx * 0.6, spread, halo)
    if expr == "glasses":
        r, lw = size * 0.62, max(1.2, size * 0.09)
        ax, bx = cx - gap / 2 + lx + r, cx + gap / 2 + lx - r
        by = cy + ly - size * 0.12
        cv.shape(lambda xs, ys: segment(xs, ys, ax, by, bx, by, lw), (ax - 2, by - 3, bx + 2, by + 3), colour, a)
    elif expr == "headphones":  # a band over the top and a cup each side
        band_r, lw = gap / 2 + size * 0.5, max(1.4, size * 0.13)
        hx, hy = cx + lx * 0.3, cy + ly * 0.3 + size * 0.3  # worn low enough for the band to fit in the pill
        g = lw + 3.5 * spread  # room for the glow to fade out
        cv.shape(lambda xs, ys: arc(xs, ys, hx, hy, band_r, lw),
                 (hx - band_r - g, hy - band_r - g, hx + band_r + g, hy + g), colour, a * 0.9, gx * 0.5, spread,
                 halo)
        g = 1 + 3.5 * spread
        for side in (-1, 1):
            px = hx + side * band_r
            cv.shape(lambda xs, ys, px=px: rbox(xs, ys, px, hy + size * 0.05, size * 0.17, size * 0.36, size * 0.12),
                     (px - size * 0.17 - g, hy - size * 0.31 - g, px + size * 0.17 + g, hy + size * 0.41 + g), colour,
                     a, gx * 0.6, spread, halo)
    if expr in ("love", "happy") and glow:
        sparkles(cv, cx, cy, size, t, a)


ORB_DASHES = 32


def draw_orb(cv, cx, cy, r, mode="idle", level=0.0, t=0.0, open_=1.0, look=(0.0, 0.0), colour=WHITE, glow=True,
             a=1.0, halo=None):
    """An orb (after thinking-orbs, MIT, by Jakub Antalik), drawn the island's way: a ring of short dashes
    round an empty middle, r px from it, its edge wobbling with smooth noise. mode "idle": it breathes; "voice": it
    ripples and the dashes stretch with level, a voice 0 to 1; "busy": a light runs round it while she thinks or
    works. open_: shut for a blink, it squashes flat as her eyes do; look: it leans a little that way."""
    if a <= 0.003:
        return
    cx, cy = cx + look[0] * r * 0.22, cy + look[1] * r * 0.16
    level = min(1.0, max(0.0, level))
    amp = {"voice": 0.06 + 0.16 * level, "busy": 0.08}.get(mode, 0.05 + 0.03 * math.sin(t * 1.3))
    turn = t * {"busy": 0.9, "voice": 0.3}.get(mode, 0.12)
    squash = 0.25 + 0.75 * open_
    lw = max(1.1, r * 0.095)
    gx = 0.22 if glow else 0.0
    n = ORB_DASHES if r >= 14 else 22  # small, as on the capsule, fewer, so each dash stands apart
    for i in range(n):
        th = i / n * math.tau + turn
        wob = amp * (0.55 * math.sin(3 * th + 1.3 * t) + 0.3 * math.sin(5 * th - 1.9 * t + 1.1) +
                     0.15 * math.sin(7 * th + 2.7 * t + 2.3))
        length = r * (0.3 + (0.42 * level * (0.55 + 0.45 * math.sin(4 * th + 8 * t)) if mode == "voice" else 0.0))
        if mode == "busy":
            aa = 0.22 + 0.78 * (0.5 + 0.5 * math.cos(th - turn - t * 3.4)) ** 3
        else:
            aa = 0.78 + 0.22 * level if mode == "voice" else 0.85
        rr = r * (1 + wob)
        c, s = math.cos(th), math.sin(th) * squash
        ax, ay = cx + c * (rr - length / 2), cy + s * (rr - length / 2)
        bx, by = cx + c * (rr + length / 2), cy + s * (rr + length / 2)
        g = lw + 3.5 * lw
        cv.shape(lambda xs, ys, ax=ax, ay=ay, bx=bx, by=by: segment(xs, ys, ax, ay, bx, by, lw),
                 (min(ax, bx) - g, min(ay, by) - g, max(ax, bx) + g, max(ay, by) + g), colour, a * aa, gx, lw, halo)


def sparkles(cv, cx, cy, size, t, a=1.0):
    """Little stars that twinkle round the eyes when she's pleased."""
    for i, (ox, oy) in enumerate(((-1.85, -0.8), (1.9, -0.65), (1.55, 0.75), (-1.6, 0.7))):
        phase = (t * 1.6 + i * 0.37) % 1.0
        k = math.sin(math.pi * phase)
        if k < 0.05:
            continue
        sx, sy, r = cx + ox * size, cy + oy * size, size * 0.22 * k
        w = max(0.8, size * 0.055)
        g = 2 + 3.5 * size * 0.12  # room for the glow to fade out, so no square shows round it
        cv.shape(lambda xs, ys, sx=sx, sy=sy, r=r, w=w: np.minimum(segment(xs, ys, sx - r, sy, sx + r, sy, w),
                                                                   segment(xs, ys, sx, sy - r, sx, sy + r, w)),
                 (sx - r - g, sy - r - g, sx + r + g, sy + r + g), GOLD, a * k, 0.5, size * 0.12)


def zzz(cv, x, y, size, t, colour=WHITE, a=1.0, halo=None):
    """Three little z's, one after another, rising up and to the right from x, y as she sleeps, growing and fading as
    they go. size: her eyes'."""
    for i in range(3):
        u = (t / 2.7 + i / 3) % 1.0
        k = math.sin(math.pi * u)
        if k < 0.06:
            continue
        h = size * (0.13 + 0.09 * u)  # half of each z's height
        zx, zy = x + u * size * 0.5, y - u * size * 0.95
        w = max(0.9, h * 0.42)
        corners = ((zx - h, zy - h), (zx + h, zy - h), (zx - h, zy + h), (zx + h, zy + h))

        def sd(xs, ys, c=corners, w=w):  # the top, the slant down to the left, the bottom
            return np.minimum(np.minimum(segment(xs, ys, *c[0], *c[1], w), segment(xs, ys, *c[1], *c[2], w)),
                              segment(xs, ys, *c[2], *c[3], w))
        g = h + w + 3 + 3.5 * size * 0.12  # and room for the glow to fade out
        cv.shape(sd, (zx - g, zy - g, zx + g, zy + g), colour, a * k * 0.9, 0.3 if halo is not None else 0.0,
                 size * 0.12, halo)


# --------------------------------------------------------------------------- the plugins' glyphs
def dots_row(cv, x, y, n, step, r, colour, level, t, mode, a=1.0):
    """A row of n dots from x, centred on y: they swell with level ("voice"), or a light runs along them
    ("busy")."""
    for i in range(n):
        if mode == "voice":
            wob = 0.5 + 0.5 * math.sin(t * 9.0 + i * 1.1)
            k = 0.55 + 0.45 * min(1.0, level * (0.6 + 0.8 * wob))
            rr, aa = r * (0.75 + 0.55 * k), a * (0.45 + 0.55 * k)
        else:
            k = max(0.0, math.cos((t * 1.6 - i / n) * math.tau)) ** 3
            rr, aa = r * (0.85 + 0.3 * k), a * (0.35 + 0.65 * k)
        px = x + i * step
        g = rr + 2 + 3.2 * r  # the glow fades out inside it
        cv.shape(lambda xs, ys, px=px, rr=rr: circle(xs, ys, px, y, rr), (px - g, y - g, px + g, y + g), colour,
                 aa, 0.25, r)


def meter(cv, x, y, h, colour, level, t, a=1.0, bars=3):
    """Nixi's three bars, left of the words, that move with your voice."""
    w = max(2.0, h * 0.2)
    for i in range(bars):
        wob = 0.5 + 0.5 * math.sin(t * 8.0 + i * 1.7)
        bh = h * (0.35 + 0.65 * min(1.0, 0.25 + level * (0.5 + wob)))
        bx = x + i * w * 1.9
        cv.shape(lambda xs, ys, bx=bx, bh=bh: rbox(xs, ys, bx, y, w / 2, bh / 2, w / 2),
                 (bx - w, y - h / 2 - 1, bx + w, y + h / 2 + 1), colour, a)


def battery(cv, x, y, h, percent, colour, fill, charging, a=1.0):
    """A battery on its side, h px tall, filled to percent, with a bolt while charging."""
    w = h * 1.9
    lw = max(1.0, h * 0.11)
    cx, cy = x + w / 2, y
    cv.shape(lambda xs, ys: np.abs(rbox(xs, ys, cx, cy, w / 2, h / 2, h * 0.28)) - lw / 2,
             (x - 2, y - h / 2 - 2, x + w + 2, y + h / 2 + 2), colour, a * 0.65)
    nub = x + w + lw * 1.3
    cv.shape(lambda xs, ys: rbox(xs, ys, nub, cy, lw * 0.8, h * 0.18, lw * 0.6), (nub - 3, cy - h / 2, nub + 3,
                                                                                  cy + h / 2), colour, a * 0.65)
    inner_w = (w - lw * 3.2) * max(0.06, min(1.0, percent / 100))
    fx = x + lw * 1.6
    cv.shape(lambda xs, ys: rbox(xs, ys, fx + inner_w / 2, cy, inner_w / 2, h / 2 - lw * 1.6, h * 0.14),
             (fx - 1, y - h / 2, fx + inner_w + 1, y + h / 2), fill, a)
    if charging:
        s = h * 0.46
        pts = [(cx + 0.15 * s, cy - s), (cx - 0.55 * s, cy + 0.12 * s), (cx - 0.05 * s, cy + 0.12 * s)]
        pts2 = [(cx - 0.15 * s, cy + s), (cx + 0.55 * s, cy - 0.12 * s), (cx + 0.05 * s, cy - 0.12 * s)]
        for p in (pts, pts2):
            cv.shape(lambda xs, ys, p=p: polygon(xs, ys, p), (cx - s, cy - s - 1, cx + s, cy + s + 1),
                     (1.0, 1.0, 1.0), a)


def ring(cv, cx, cy, r, width, left, colour, back, a=1.0):
    """A ring running down clockwise from the top, like a timer: left, the part still to go, 0 to 1."""
    def sd(xs, ys):
        return np.abs(circle(xs, ys, cx, cy, r)) - width / 2
    box = (cx - r - width, cy - r - width, cx + r + width, cy + r + width)
    cv.shape(sd, box, back, a)

    def done(xs, ys):
        turn = (np.arctan2(xs - cx, -(ys - cy)) % math.tau) / math.tau
        return np.where(turn <= left, sd(xs, ys), 9.0)
    cv.shape(done, box, colour, a)


def play_glyph(cv, cx, cy, s, playing, colour, a=1.0):
    """Pause bars while it plays, else a play triangle, s px tall."""
    if playing:
        for side in (-1, 1):
            bx = cx + side * s * 0.22
            cv.shape(lambda xs, ys, bx=bx: rbox(xs, ys, bx, cy, s * 0.12, s * 0.42, s * 0.06),
                     (bx - s * 0.2, cy - s * 0.5, bx + s * 0.2, cy + s * 0.5), colour, a)
    else:
        pts = [(cx - s * 0.32, cy - s * 0.45), (cx + s * 0.45, cy), (cx - s * 0.32, cy + s * 0.45)]
        cv.shape(lambda xs, ys: polygon(xs, ys, pts) - s * 0.02, (cx - s * 0.5, cy - s * 0.55, cx + s * 0.6,
                                                                cy + s * 0.55), colour, a)


def skip_glyph(cv, cx, cy, s, forward, colour, a=1.0):
    """Next or previous: a triangle and a bar."""
    d = 1 if forward else -1
    tip = cx + d * s * 0.28
    back = cx - d * s * 0.32
    pts = [(back, cy - s * 0.4), (tip, cy), (back, cy + s * 0.4)] if forward else \
        [(back, cy + s * 0.4), (tip, cy), (back, cy - s * 0.4)]
    cv.shape(lambda xs, ys: polygon(xs, ys, pts) - s * 0.02, (cx - s * 0.6, cy - s * 0.5, cx + s * 0.6,
                                                            cy + s * 0.5), colour, a)
    bar = cx + d * s * 0.38
    cv.shape(lambda xs, ys: rbox(xs, ys, bar, cy, s * 0.06, s * 0.4, s * 0.05),
             (bar - s * 0.12, cy - s * 0.5, bar + s * 0.12, cy + s * 0.5), colour, a)


def tick_glyph(cv, cx, cy, s, colour, a=1.0):
    """A tick about s px across, for something done."""
    w = max(1.2, s * 0.16)
    (ax, ay), (bx, by), (ex, ey) = (cx - s * 0.36, cy + s * 0.02), (cx - s * 0.1, cy + s * 0.28), \
        (cx + s * 0.38, cy - s * 0.26)
    cv.shape(lambda xs, ys: np.minimum(segment(xs, ys, ax, ay, bx, by, w), segment(xs, ys, bx, by, ex, ey, w)),
             (cx - s * 0.5 - w, cy - s * 0.4 - w, cx + s * 0.5 + w, cy + s * 0.4 + w), colour, a)


def close_glyph(cv, cx, cy, s, colour, a=1.0):
    r, w = s * 0.32, max(1.0, s * 0.12)
    cv.shape(lambda xs, ys: np.minimum(segment(xs, ys, cx - r, cy - r, cx + r, cy + r, w),
                                       segment(xs, ys, cx - r, cy + r, cx + r, cy - r, w)),
             (cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2), colour, a)


def equalizer(cv, x, cy, h, colour, level, t, a=1.0, bars=4):
    """Bars that dance while music plays, by what the speakers are playing when that's known."""
    w = max(1.6, h * 0.16)
    for i in range(bars):
        wob = 0.5 + 0.5 * math.sin(t * (6.5 + i * 1.3) + i * 2.1)
        bh = h * (0.25 + 0.75 * min(1.0, (0.35 + 0.65 * wob) * (0.3 + 0.9 * level)))
        bx = x + i * w * 2.0
        cv.shape(lambda xs, ys, bx=bx, bh=bh: rbox(xs, ys, bx, cy + (h - bh) / 2, w / 2, bh / 2, w / 2),
                 (bx - w, cy - h / 2 - 1, bx + w, cy + h / 2 + 1), colour, a)


# --------------------------------------------------------------------------- live activities' glyphs (30 October 2026)
# Each is glyph(cv, cx, cy, s, colour, a, t), about s px across and centred on cx, cy, as a phone's island draws its
# small symbols. t: seconds, while it moves (a twinkle, a pulse, a wave); None keeps it still, costing no frames.


def moon_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """A crescent moon and a small star by it that twinkles while t goes on: dream mode."""
    r = s * 0.4
    ox, oy = cx - s * 0.06, cy + s * 0.04
    bx, by, br = ox + r * 0.55, oy - r * 0.36, r * 0.84  # the dark bite out of it
    g = r + 2 + 3.5 * r * 0.5  # room for its glow to fade out, so no square shows round it
    cv.shape(lambda xs, ys: np.maximum(circle(xs, ys, ox, oy, r), -circle(xs, ys, bx, by, br)),
             (ox - g, oy - g, ox + g, oy + g), colour, a, 0.18, r * 0.5)
    k = 0.5 + 0.5 * math.sin(t * 2.6) if t is not None else 0.6
    sx, sy, sr = cx + s * 0.34, cy - s * 0.3, s * (0.09 + 0.07 * k)
    w = max(0.8, s * 0.06)
    cv.shape(lambda xs, ys: np.minimum(segment(xs, ys, sx - sr, sy, sx + sr, sy, w),
                                       segment(xs, ys, sx, sy - sr, sx, sy + sr, w)),
             (sx - sr - 2, sy - sr - 2, sx + sr + 2, sy + sr + 2), colour, a * (0.5 + 0.5 * k))


def record_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """A recording dot, as a phone's red one, with a ring swelling out of it and fading while t goes on."""
    r = s * 0.27
    if t is not None:
        u = (t / 1.7) % 1.0
        rr, lw = r * (1.15 + 0.85 * u), max(1.0, s * 0.07)
        cv.shape(lambda xs, ys: np.abs(circle(xs, ys, cx, cy, rr)) - lw / 2,
                 (cx - rr - lw - 1, cy - rr - lw - 1, cx + rr + lw + 1, cy + rr + lw + 1), colour,
                 a * 0.6 * (1 - u) ** 1.6)
    g = r + 2 + 3.5 * r * 0.5
    cv.shape(lambda xs, ys: circle(xs, ys, cx, cy, r), (cx - g, cy - g, cx + g, cy + g), colour, a, 0.3, r * 0.5)


def hand_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """An open hand, fingers up, that waves a little from the wrist while t goes on: hand control."""
    tilt = 0.16 * math.sin(t * 4.2) if t is not None else 0.0
    c, sn = math.cos(tilt), math.sin(tilt)
    wx, wy = cx, cy + s * 0.5  # it turns about the wrist

    def at(x, y):
        dx, dy = x * s, y * s + (cy - wy)
        return wx + dx * c - dy * sn, wy + dx * sn + dy * c
    w = s * 0.15
    bones = (((-0.25, -0.02), (-0.29, -0.3)), ((-0.09, -0.06), (-0.1, -0.44)), ((0.08, -0.06), (0.09, -0.42)),
             ((0.24, -0.02), (0.27, -0.26)), ((-0.17, 0.2), (-0.42, 0.0)))  # four fingers and the thumb
    palm = (at(-0.1, 0.12), at(0.1, 0.12), at(0.0, 0.28))

    def sd(xs, ys):
        d = np.minimum(segment(xs, ys, *palm[0], *palm[1], s * 0.44), segment(xs, ys, *palm[1], *palm[2], s * 0.3))
        for p, q in bones:
            d = np.minimum(d, segment(xs, ys, *at(*p), *at(*q), w))
        return d
    cv.shape(sd, (cx - s * 0.65, cy - s * 0.65, cx + s * 0.65, cy + s * 0.65), colour, a)


def pointer_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """A mouse pointer, its tip up and to the left, with a ring tapping out from its tip while t goes on: where to
    click, shown on your screen."""
    x0, y0 = cx - s * 0.26, cy - s * 0.42  # its tip
    head = [(x0, y0), (x0, y0 + s * 0.7), (x0 + s * 0.5, y0 + s * 0.5)]
    tail = (x0 + s * 0.2, y0 + s * 0.48, x0 + s * 0.36, y0 + s * 0.82)
    cv.shape(lambda xs, ys: np.minimum(polygon(xs, ys, head) - s * 0.035, segment(xs, ys, *tail, s * 0.16)),
             (x0 - 2, y0 - 2, x0 + s * 0.62, y0 + s * 0.92), colour, a)
    if t is not None:
        u = (t / 1.4) % 1.0
        rr, lw = s * (0.08 + 0.26 * u), max(1.0, s * 0.06)
        cv.shape(lambda xs, ys: np.abs(circle(xs, ys, x0, y0, rr)) - lw / 2,
                 (x0 - rr - 2, y0 - rr - 2, x0 + rr + 2, y0 + rr + 2), colour, a * 0.7 * (1 - u))


def pause_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """Two rounded bars: paused, as her break is."""
    for side in (-1, 1):
        bx = cx + side * s * 0.17
        cv.shape(lambda xs, ys, bx=bx: rbox(xs, ys, bx, cy, s * 0.09, s * 0.32, s * 0.07),
                 (bx - s * 0.15, cy - s * 0.4, bx + s * 0.15, cy + s * 0.4), colour, a)


GLYPHS = {"moon": moon_glyph, "record": record_glyph, "hand": hand_glyph, "pointer": pointer_glyph,
          "pause": pause_glyph}


def wave_bars(cv, x, cy, w, h, colour, level, t, a=1.0):
    """A voice's waveform as a phone's recorder draws it: rounded bars across w px from x, up and down from cy and at
    most h px tall, tallest in the middle, moving with t and swelling with level (0 to 1)."""
    bw = max(1.6, h * 0.12)
    n = max(4, int(w / (bw * 2.2)))
    step = w / n
    level = min(1.0, max(0.0, level))
    for i in range(n):
        ph = i * 0.83
        wob = 0.5 + 0.5 * math.sin(t * 6.1 + ph) * math.cos(t * 2.3 + ph * 1.9)
        env = math.sin(math.pi * (i + 0.5) / n) ** 0.7
        bh = max(bw, h * env * (0.22 + 0.78 * wob * (0.45 + 0.55 * level)))
        bx = x + (i + 0.5) * step
        cv.shape(lambda xs, ys, bx=bx, bh=bh: rbox(xs, ys, bx, cy, bw / 2, bh / 2, bw / 2),
                 (bx - bw, cy - h / 2 - 1, bx + bw, cy + h / 2 + 1), colour, a)


# --------------------------------------------------------------------------- the hub's glyphs (30 October 2026)
# For the island's panels, after bloom's notch (github.com/SehajveerSingh2005/bloom): its controls, its calendar, its
# devices and its shelf, and the drawings a connected device's popup has. glyph(cv, cx, cy, s, colour, a), about s px
# across, centred on cx, cy, like the live activities' above.
def _arc_up(xs, ys, cx, cy, r, w):
    """A quarter of a ring round cx, cy, r px out and w wide, its middle straight up, with round ends."""
    dx, dy = xs - cx, ys - cy
    ring = np.abs(np.hypot(dx, dy) - r) - w / 2
    wedge = (np.abs(dx) + dy) * 0.7071  # outside the quarter that points up: more than 0
    ends = np.minimum(np.hypot(dx - r * 0.7071, dy + r * 0.7071), np.hypot(dx + r * 0.7071, dy + r * 0.7071)) - w / 2
    return np.minimum(np.maximum(ring, wedge), ends)


def _arc_right(xs, ys, cx, cy, r, w):
    """_arc_up turned to face right."""
    dx, dy = xs - cx, ys - cy
    ring = np.abs(np.hypot(dx, dy) - r) - w / 2
    wedge = (np.abs(dy) - dx) * 0.7071
    ends = np.minimum(np.hypot(dx - r * 0.7071, dy - r * 0.7071), np.hypot(dx - r * 0.7071, dy + r * 0.7071)) - w / 2
    return np.minimum(np.maximum(ring, wedge), ends)


def _segments(xs, ys, points, w):
    """Lines through each pair of points, w wide, as one shape."""
    d = None
    for (ax, ay), (bx, by) in points:
        part = segment(xs, ys, ax, ay, bx, by, w)
        d = part if d is None else np.minimum(d, part)
    return d


def wifi_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """Wi-Fi as a phone's status bar has it: a dot and two arcs over it."""
    base, w = cy + s * 0.3, max(1.2, s * 0.12)
    cv.shape(lambda xs, ys: np.minimum(np.minimum(circle(xs, ys, cx, base, s * 0.09), _arc_up(xs, ys, cx, base,
                                                                                              s * 0.34, w)),
                                       _arc_up(xs, ys, cx, base, s * 0.6, w)),
             (cx - s * 0.55, cy - s * 0.45, cx + s * 0.55, cy + s * 0.45), colour, a)


def bluetooth_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """Bluetooth's rune: a line down, and two arrowheads off it to the right, crossing in the middle."""
    h, wd, w = s * 0.42, s * 0.2, max(1.1, s * 0.1)
    top, bot = (cx - wd * 0.15, cy - h), (cx - wd * 0.15, cy + h)
    ru, rl, ul, ll = (cx + wd, cy - h / 2), (cx + wd, cy + h / 2), (cx - wd, cy - h / 2.2), (cx - wd, cy + h / 2.2)
    pts = ((top, bot), (top, ru), (ru, ll), (bot, rl), (rl, ul))
    cv.shape(lambda xs, ys: _segments(xs, ys, pts, w), (cx - s * 0.4, cy - s * 0.55, cx + s * 0.4, cy + s * 0.55),
             colour, a)


def dnd_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """Do Not Disturb: a crescent moon, as a phone's."""
    r = s * 0.36
    ox, oy, bx, by = cx - s * 0.04, cy + s * 0.02, cx + s * 0.16, cy - s * 0.14
    cv.shape(lambda xs, ys: np.maximum(circle(xs, ys, ox, oy, r), -circle(xs, ys, bx, by, r * 0.86)),
             (ox - r - 2, oy - r - 2, ox + r + 2, oy + r + 2), colour, a)


def speaker_glyph(cv, cx, cy, s, colour, a=1.0, level=1.0, muted=False):
    """A speaker, with a wave for each third of level going out of it, or a cross while it's muted."""
    bx, w = cx - s * 0.16, max(1.1, s * 0.1)
    # the box and the cone apart: together they aren't convex, and polygon() takes only convex shapes
    cone = [(bx - s * 0.07, cy - s * 0.11), (bx + s * 0.12, cy - s * 0.3), (bx + s * 0.12, cy + s * 0.3),
            (bx - s * 0.07, cy + s * 0.11)]

    def body(xs, ys):
        return np.minimum(rbox(xs, ys, bx - s * 0.12, cy, s * 0.09, s * 0.11, s * 0.03), polygon(xs, ys, cone) -
                          s * 0.02)
    cv.shape(body, (bx - s * 0.3, cy - s * 0.4, bx + s * 0.2, cy + s * 0.4), colour, a)
    x0 = bx + s * 0.16
    if muted:
        r = s * 0.12
        mx = x0 + s * 0.2
        cv.shape(lambda xs, ys: _segments(xs, ys, (((mx - r, cy - r), (mx + r, cy + r)),
                                                   ((mx - r, cy + r), (mx + r, cy - r))), w),
                 (mx - r - w, cy - r - w, mx + r + w, cy + r + w), colour, a)
        return
    for i, r in enumerate((s * 0.14, s * 0.3)):
        if level > (0.01 if i == 0 else 0.5):
            cv.shape(lambda xs, ys, r=r: _arc_right(xs, ys, x0 - s * 0.06, cy, r, w),
                     (x0 - s * 0.1, cy - r - w, x0 + r + w, cy + r + w), colour, a)


def sun_glyph(cv, cx, cy, s, colour, a=1.0, level=1.0):
    """The sun for brightness, its rays longer the brighter it is."""
    r, w = s * 0.16, max(1.0, s * 0.09)
    rays = []
    for i in range(8):
        th = i * math.pi / 4
        c, sn = math.cos(th), math.sin(th)
        r0, r1 = r + s * 0.08, r + s * (0.12 + 0.12 * max(0.0, min(1.0, level)))
        rays.append(((cx + c * r0, cy + sn * r0), (cx + c * r1, cy + sn * r1)))
    cv.shape(lambda xs, ys: np.minimum(circle(xs, ys, cx, cy, r), _segments(xs, ys, rays, w)),
             (cx - s * 0.5, cy - s * 0.5, cx + s * 0.5, cy + s * 0.5), colour, a)


def calendar_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """A page of a calendar: its outline, the band along its top, and its two rings."""
    hw, hh, w = s * 0.36, s * 0.32, max(1.0, s * 0.09)
    cy2 = cy + s * 0.04

    def sd(xs, ys):
        frame = np.abs(rbox(xs, ys, cx, cy2, hw, hh, s * 0.08)) - w / 2
        band = rbox(xs, ys, cx, cy2 - hh + s * 0.09, hw, s * 0.09, s * 0.04)
        rings = _segments(xs, ys, (((cx - hw * 0.45, cy2 - hh - s * 0.1), (cx - hw * 0.45, cy2 - hh + s * 0.04)),
                                   ((cx + hw * 0.45, cy2 - hh - s * 0.1), (cx + hw * 0.45, cy2 - hh + s * 0.04))), w)
        return np.minimum(np.minimum(frame, band), rings)
    cv.shape(sd, (cx - s * 0.45, cy - s * 0.5, cx + s * 0.45, cy + s * 0.48), colour, a)


def timer_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """A stopwatch for a focus session: its face, a hand, and the button on top."""
    r, w = s * 0.32, max(1.1, s * 0.1)
    cy2 = cy + s * 0.06
    turn = (t * 0.9) % math.tau if t is not None else math.pi * 0.3
    hx, hy = cx + math.sin(turn) * r * 0.62, cy2 - math.cos(turn) * r * 0.62
    cv.shape(lambda xs, ys: np.minimum(np.abs(circle(xs, ys, cx, cy2, r)) - w / 2,
                                       _segments(xs, ys, (((cx, cy2), (hx, hy)), ((cx, cy2 - r - s * 0.04),
                                                                                  (cx, cy2 - r - s * 0.14)),
                                                          ((cx - s * 0.08, cy2 - r - s * 0.15),
                                                           (cx + s * 0.08, cy2 - r - s * 0.15))), w)),
             (cx - s * 0.45, cy - s * 0.5, cx + s * 0.45, cy + s * 0.5), colour, a)


def tray_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """The shelf: a tray with an arrow going down into it."""
    hw, w = s * 0.36, max(1.1, s * 0.1)
    top, bot = cy + s * 0.02, cy + s * 0.34
    pts = (((cx - hw, top), (cx - hw, bot)), ((cx - hw, bot), (cx + hw, bot)), ((cx + hw, bot), (cx + hw, top)),
           ((cx - hw, top), (cx - hw * 0.45, top)), ((cx - hw * 0.45, top), (cx - hw * 0.3, top + s * 0.12)),
           ((cx - hw * 0.3, top + s * 0.12), (cx + hw * 0.3, top + s * 0.12)),
           ((cx + hw * 0.3, top + s * 0.12), (cx + hw * 0.45, top)), ((cx + hw * 0.45, top), (cx + hw, top)),
           ((cx, cy - s * 0.4), (cx, cy - s * 0.02)), ((cx - s * 0.14, cy - s * 0.15), (cx, cy - s * 0.02)),
           ((cx + s * 0.14, cy - s * 0.15), (cx, cy - s * 0.02)))
    cv.shape(lambda xs, ys: _segments(xs, ys, pts, w), (cx - s * 0.48, cy - s * 0.5, cx + s * 0.48, cy + s * 0.46),
             colour, a)


def controls_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """Controls: two sliders, each with its knob, as a phone's control centre has them."""
    w = max(1.1, s * 0.1)
    pts = (((cx - s * 0.36, cy - s * 0.16), (cx + s * 0.36, cy - s * 0.16)),
           ((cx - s * 0.36, cy + s * 0.18), (cx + s * 0.36, cy + s * 0.18)))
    cv.shape(lambda xs, ys: np.minimum(np.minimum(_segments(xs, ys, pts, w), circle(xs, ys, cx + s * 0.14,
                                                                                   cy - s * 0.16, s * 0.12)),
                                       circle(xs, ys, cx - s * 0.16, cy + s * 0.18, s * 0.12)),
             (cx - s * 0.46, cy - s * 0.36, cx + s * 0.46, cy + s * 0.38), colour, a)


def headphones_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """Over-ear headphones: the band, and a cup each side."""
    r, w = s * 0.34, max(1.2, s * 0.1)
    by = cy + s * 0.06

    def sd(xs, ys):
        band = arc(xs, ys, cx, by, r, w)
        cups = np.minimum(rbox(xs, ys, cx - r, by + s * 0.12, s * 0.09, s * 0.17, s * 0.06),
                          rbox(xs, ys, cx + r, by + s * 0.12, s * 0.09, s * 0.17, s * 0.06))
        return np.minimum(band, cups)
    cv.shape(sd, (cx - s * 0.5, cy - s * 0.42, cx + s * 0.5, cy + s * 0.46), colour, a)


def buds_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """A pair of earbuds with stems, as AirPods are drawn: a round head and a stem down each."""
    w = max(1.2, s * 0.11)

    def sd(xs, ys):
        d = None
        for side in (-1, 1):
            hx = cx + side * s * 0.2
            head = circle(xs, ys, hx, cy - s * 0.14, s * 0.13)
            stem = segment(xs, ys, hx + side * s * 0.06, cy - s * 0.06, hx + side * s * 0.07, cy + s * 0.34, w)
            part = np.minimum(head, stem)
            d = part if d is None else np.minimum(d, part)
        return d
    cv.shape(sd, (cx - s * 0.5, cy - s * 0.4, cx + s * 0.5, cy + s * 0.46), colour, a)


def speaker_box_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """A speaker of its own (a Bluetooth one): a tall box with its two drivers in it."""
    w = max(1.0, s * 0.09)
    cv.shape(lambda xs, ys: np.minimum(np.minimum(np.abs(rbox(xs, ys, cx, cy, s * 0.26, s * 0.38, s * 0.09)) - w / 2,
                                                  np.abs(circle(xs, ys, cx, cy + s * 0.1, s * 0.14)) - w / 2),
                                       circle(xs, ys, cx, cy - s * 0.2, s * 0.06)),
             (cx - s * 0.36, cy - s * 0.48, cx + s * 0.36, cy + s * 0.48), colour, a)


def drive_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """A USB drive: its body, and the plug at its top."""
    w = max(1.0, s * 0.09)
    cv.shape(lambda xs, ys: np.minimum(rbox(xs, ys, cx, cy + s * 0.1, s * 0.2, s * 0.3, s * 0.07),
                                       np.abs(rbox(xs, ys, cx, cy - s * 0.3, s * 0.12, s * 0.1, s * 0.02)) - w / 2),
             (cx - s * 0.3, cy - s * 0.48, cx + s * 0.3, cy + s * 0.48), colour, a)


def jack_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """Wired earphones' plug: a slim pin over its grip, and the cable going down."""
    w = max(1.0, s * 0.1)

    def sd(xs, ys):
        pin = np.maximum(segment(xs, ys, cx, cy - s * 0.42, cx, cy - s * 0.12, s * 0.13),
                         -rbox(xs, ys, cx, cy - s * 0.24, s * 0.2, s * 0.02, 0.0))  # a ring cut round it
        grip = rbox(xs, ys, cx, cy + s * 0.06, s * 0.15, s * 0.17, s * 0.05)
        return np.minimum(np.minimum(pin, grip), segment(xs, ys, cx, cy + s * 0.2, cx, cy + s * 0.46, w))
    cv.shape(sd, (cx - s * 0.25, cy - s * 0.5, cx + s * 0.25, cy + s * 0.5), colour, a)


def chevron_glyph(cv, cx, cy, s, colour, a=1.0, right=True):
    """A chevron, < or >, for going back or on a month."""
    d, w = (1 if right else -1) * s * 0.14, max(1.1, s * 0.11)
    pts = (((cx - d, cy - s * 0.26), (cx + d, cy)), ((cx + d, cy), (cx - d, cy + s * 0.26)))
    cv.shape(lambda xs, ys: _segments(xs, ys, pts, w), (cx - s * 0.3, cy - s * 0.4, cx + s * 0.3, cy + s * 0.4),
             colour, a)


def cloud_glyph(cv, cx, cy, s, colour, a=1.0, sky="cloudy"):
    """The weather as one small drawing: the sun when it's clear, the sun behind a cloud when it's partly so, a cloud
    with drops for rain, with a bolt for a storm, else a cloud."""
    sky = str(sky or "")

    def cloud(xs, ys, ox, oy, k):
        return np.minimum(np.minimum(circle(xs, ys, ox - s * 0.16 * k, oy + s * 0.04 * k, s * 0.16 * k),
                                     circle(xs, ys, ox + s * 0.06 * k, oy - s * 0.06 * k, s * 0.22 * k)),
                          rbox(xs, ys, ox, oy + s * 0.1 * k, s * 0.3 * k, s * 0.1 * k, s * 0.1 * k))
    box = (cx - s * 0.5, cy - s * 0.5, cx + s * 0.5, cy + s * 0.5)
    if "clear" in sky or "sun" in sky:
        sun_glyph(cv, cx, cy, s, GOLD, a)
        return
    if "partly" in sky or "few" in sky:
        sun_glyph(cv, cx + s * 0.14, cy - s * 0.14, s * 0.7, GOLD, a)
    cv.shape(lambda xs, ys: cloud(xs, ys, cx - s * 0.02, cy - s * 0.02, 1.0), box, colour, a)
    w = max(1.0, s * 0.08)
    if "storm" in sky or "thunder" in sky:
        pts = [(cx + s * 0.02, cy + s * 0.16), (cx - s * 0.12, cy + s * 0.36), (cx + s * 0.06, cy + s * 0.3)]
        cv.shape(lambda xs, ys: polygon(xs, ys, pts), box, GOLD, a)
    elif "rain" in sky or "drizzle" in sky or "shower" in sky or "snow" in sky:
        drops = tuple(((cx + o, cy + s * 0.2), (cx + o - s * 0.05, cy + s * 0.36)) for o in (-s * 0.14, 0.0, s * 0.14))
        cv.shape(lambda xs, ys: _segments(xs, ys, drops, w), box, (0.39, 0.82, 1.0), a)


# --------------------------------------------------------------------------- Glance's (30 October 2026)
# For the rest of Glance's notch: the Recent panel's bell, Keep awake's cup, and each shortcut's answer
def bell_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """Notifications: a bell, its rim and its clapper."""
    w = max(1.1, s * 0.1)

    def sd(xs, ys):
        dome = np.minimum(circle(xs, ys, cx, cy - s * 0.08, s * 0.22), rbox(xs, ys, cx, cy + s * 0.06, s * 0.22,
                                                                            s * 0.12, s * 0.02))
        rim = segment(xs, ys, cx - s * 0.33, cy + s * 0.19, cx + s * 0.33, cy + s * 0.19, w * 1.3)
        return np.minimum(np.minimum(dome, rim), circle(xs, ys, cx, cy + s * 0.32, s * 0.08))
    cv.shape(sd, (cx - s * 0.42, cy - s * 0.42, cx + s * 0.42, cy + s * 0.46), colour, a)


def cup_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """Keep awake: a cup, with its handle and steam over it."""
    w = max(1.1, s * 0.1)
    bx, by = cx - s * 0.07, cy + s * 0.1

    def sd(xs, ys):
        cup = np.abs(rbox(xs, ys, bx, by, s * 0.22, s * 0.2, s * 0.07)) - w / 2
        handle = np.maximum(np.abs(circle(xs, ys, bx + s * 0.22, by - s * 0.01, s * 0.11)) - w / 2,
                            bx + s * 0.22 - xs)
        steam = _segments(xs, ys, (((bx - s * 0.08, by - s * 0.3), (bx - s * 0.04, by - s * 0.42)),
                                   ((bx + s * 0.08, by - s * 0.3), (bx + s * 0.12, by - s * 0.42))), w)
        return np.minimum(np.minimum(cup, handle), steam)
    cv.shape(sd, (cx - s * 0.42, cy - s * 0.42, cx + s * 0.42, cy + s * 0.42), colour, a)


def undo_glyph(cv, cx, cy, s, colour, a=1.0, t=None, redo=False):
    """Undo: an arrow going back round over the top to the left, as an editor's button has it; redo the other way."""
    w = max(1.2, s * 0.11)
    f = -1.0 if redo else 1.0  # redo is undo turned round
    ox, oy, r = cx + f * s * 0.06, cy + s * 0.04, s * 0.26
    tip = (ox - f * r, oy + s * 0.06)
    pts = (((tip[0] - f * s * 0.14, tip[1] - s * 0.11), tip), ((tip[0] + f * s * 0.13, tip[1] - s * 0.12), tip),
           ((ox + f * r, oy), (ox + f * r, oy + s * 0.2)))

    def sd(xs, ys):
        return np.minimum(arc(xs, ys, ox, oy, r, w), _segments(xs, ys, pts, w))
    cv.shape(sd, (cx - s * 0.48, cy - s * 0.4, cx + s * 0.48, cy + s * 0.4), colour, a)


def scissors_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """Cut: scissors, their two rings at the bottom and their blades crossing over them."""
    w = max(1.1, s * 0.1)
    r = s * 0.11

    def sd(xs, ys):
        rings = np.minimum(np.abs(circle(xs, ys, cx - s * 0.18, cy + s * 0.24, r)) - w / 2,
                           np.abs(circle(xs, ys, cx + s * 0.18, cy + s * 0.24, r)) - w / 2)
        blades = _segments(xs, ys, (((cx - s * 0.12, cy + s * 0.14), (cx + s * 0.16, cy - s * 0.38)),
                                    ((cx + s * 0.12, cy + s * 0.14), (cx - s * 0.16, cy - s * 0.38))), w)
        return np.minimum(rings, blades)
    cv.shape(sd, (cx - s * 0.36, cy - s * 0.46, cx + s * 0.36, cy + s * 0.42), colour, a)


def paste_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """Paste: a clipboard, its board and the clip at its top."""
    w = max(1.1, s * 0.1)

    def sd(xs, ys):
        board = np.abs(rbox(xs, ys, cx, cy + s * 0.06, s * 0.27, s * 0.34, s * 0.07)) - w / 2
        clip = rbox(xs, ys, cx, cy - s * 0.27, s * 0.13, s * 0.07, s * 0.04)
        lines = _segments(xs, ys, (((cx - s * 0.12, cy + s * 0.04), (cx + s * 0.12, cy + s * 0.04)),
                                   ((cx - s * 0.12, cy + s * 0.18), (cx + s * 0.05, cy + s * 0.18))), w * 0.9)
        return np.minimum(np.minimum(board, clip), lines)
    cv.shape(sd, (cx - s * 0.4, cy - s * 0.42, cx + s * 0.4, cy + s * 0.46), colour, a)


def saved_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """Saved: a tick in a ring."""
    w = max(1.1, s * 0.1)
    r = s * 0.36
    cv.shape(lambda xs, ys: np.abs(circle(xs, ys, cx, cy, r)) - w / 2, (cx - r - w, cy - r - w, cx + r + w, cy + r + w),
             colour, a)
    tick_glyph(cv, cx, cy + s * 0.02, s * 0.5, colour, a)


def shot_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """A screenshot: the four corners of a frame, as a camera's viewfinder has them, and a dot in it."""
    w = max(1.1, s * 0.1)
    hw, hh, c = s * 0.36, s * 0.3, s * 0.14
    pts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = cx + sx * hw, cy + sy * hh
            pts += [((x, y), (x - sx * c, y)), ((x, y), (x, y - sy * c))]
    cv.shape(lambda xs, ys: np.minimum(_segments(xs, ys, pts, w), circle(xs, ys, cx, cy, s * 0.1)),
             (cx - s * 0.46, cy - s * 0.4, cx + s * 0.46, cy + s * 0.4), colour, a)


def link_glyph(cv, cx, cy, s, colour, a=1.0, t=None):
    """A link: two rounded links of a chain, slanted, through each other."""
    w = max(1.1, s * 0.1)
    c, sn = 0.7071, 0.7071

    def sd(xs, ys):
        u, v = (xs - cx) * c + (ys - cy) * sn, -(xs - cx) * sn + (ys - cy) * c  # along the slant and across it
        one = np.abs(rbox(u, v, -s * 0.15, 0.0, s * 0.2, s * 0.11, s * 0.11)) - w / 2
        two = np.abs(rbox(u, v, s * 0.15, 0.0, s * 0.2, s * 0.11, s * 0.11)) - w / 2
        return np.minimum(one, two)
    cv.shape(sd, (cx - s * 0.46, cy - s * 0.46, cx + s * 0.46, cy + s * 0.46), colour, a)


SHORTCUT_GLYPHS = {"cut": scissors_glyph, "paste": paste_glyph, "undo": undo_glyph,
                   "redo": lambda cv, cx, cy, s, colour, a=1.0, t=None: undo_glyph(cv, cx, cy, s, colour, a, redo=True),
                   "save": saved_glyph, "screenshot": shot_glyph}


DEVICE_GLYPHS = {"headphones": headphones_glyph, "headset": headphones_glyph, "buds": buds_glyph,
                 "speaker": speaker_box_glyph, "drive": drive_glyph, "jack": jack_glyph}
GLYPHS.update({"wifi": wifi_glyph, "bluetooth": bluetooth_glyph, "dnd": dnd_glyph, "calendar": calendar_glyph,
               "timer": timer_glyph, "tray": tray_glyph, "controls": controls_glyph, "bell": bell_glyph,
               "awake": cup_glyph, "link": link_glyph,
               "weather": lambda cv, cx, cy, s, colour, a=1.0, t=None: cloud_glyph(cv, cx, cy, s, colour, a,
                                                                                   "partly cloudy"),
               **DEVICE_GLYPHS})
