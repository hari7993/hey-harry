"""Her island's light (30 October 2026, the owner's ask, after Glance's notch, joinglance.app, and their recording of
its demo): when something comes, the island lights up in its colour. A sharp line runs down its sides and along its
bottom with a soft glow round it, and while it hangs from the top of the screen two arms of light run out along the
top either side, as though the light came from behind it; the light flares, stays a moment and fades. A level (the
battery as it charges) lights the line only as far as it goes, from the left, the way Glance's brightness does;
something wrong lights her two lower corners, in red.

Drawn with numpy, as the island is: how strong the line and the glow are at each pixel is worked out once for a shape
and kept (field), and each frame only scales that by how bright the light is now and lays it over the window's
picture round the island (shine), never over the island itself."""
import math

import numpy as np

FLARE, HOLD, FADE = 0.2, 1.1, 0.9  # seconds: it comes up, it stays, it goes, as Glance's did in the recording
ARM, ARM_MIN, ARM_MAX = 0.62, 96, 200  # each arm against the island's width, and its shortest and longest, logical px
BELOW = 34  # logical px under the island the glow reaches
KINDS = ("halo", "level", "alarm")
LINE_W = 1.2  # logical px: the line's own width, before its glow
GLOWS = ((3.0, 0.5), (8.0, 0.3), (16.0, 0.16))  # the glow's layers: how far each reaches, logical px, and how strong
GLOW_TINT = 0.45  # how much lighter than its colour the glow is, so it brightens what's behind it (shine)


def _ease(t):
    return 1 - (1 - t) ** 3


class Light:
    """One lighting up: colour (r, g, b, 0 to 1), when it began, its kind (KINDS) and, for a level, how far, 0 to
    1."""
    __slots__ = ("colour", "at", "kind", "level")

    def __init__(self, colour, at, kind="halo", level=None):
        self.colour = tuple(float(c) for c in colour)
        self.at, self.kind = float(at), kind if kind in KINDS else "halo"
        self.level = None if level is None else max(0.0, min(1.0, float(level)))

    def strength(self, now):
        """How bright it is at now, 0 to 1: up quickly, held, then fading out."""
        u = now - self.at
        if u < 0:
            return 0.0
        if u < FLARE:
            return _ease(u / FLARE)
        u -= FLARE
        if u < HOLD:
            return 1.0
        u -= HOLD
        return (1 - u / FADE) ** 2 if u < FADE else 0.0

    def spread(self, now):
        """How far its arms have run along the top of the screen, 0 to 1: to their ends a little after it flares."""
        return _ease(max(0.0, min(1.0, (now - self.at) / (2.2 * FLARE))))

    def done(self, now):
        return now - self.at >= FLARE + HOLD + FADE


def _glow(d, k):
    return sum(w * np.exp(-(d / (r * k)) ** 2) for r, w in GLOWS)


def field(sd, x0, W, H, r, y_top, k, drop, kind="halo", level=None, size=(1, 1), soft=None):
    """What a light round the island covers, worked out once for its shape: {"box": its slices of the window, "line"
    and "glow": how strong each is at a pixel there round the island, 0 to 1, "rows": the arms' line and glow down the
    box, "cols": how far each column is along an arm, 0 at the island and 1 at the arm's end (-1 off them), "arm": an
    arm's length in px, "cover": how much of a pixel is the island, which the light never goes over}; None if none of
    it is in the window. sd(xs, ys): the island's signed distance, below 0 inside; its top at y_top, the top of the
    screen when it hangs from it (drop), which is where the arms run. size: the window's width and how far down the
    light may go (the top of the words' bar under the island). soft(xs, ys): a smoother distance for the glow, the
    plain box: the curves of a notch's shoulders bend sd's distances off them, and the glow showed a ring there."""
    width, height = size
    arm = min(ARM_MAX * k, max(ARM_MIN * k, ARM * W)) if drop else 0.0
    if kind == "level":
        arm *= 0.45
    elif kind == "alarm":
        arm *= 0.5
    pad = 22 * k
    X0, X1 = max(0, int(x0 - arm - pad)), min(width, int(math.ceil(x0 + W + arm + pad)))
    Y0 = max(0, int(y_top if drop else y_top - BELOW * k))
    Y1 = min(height, int(math.ceil(y_top + H + BELOW * k)))
    if X1 <= X0 or Y1 <= Y0:
        return None
    xs = np.arange(X0, X1, dtype=np.float32) + 0.5
    ys = np.arange(Y0, Y1, dtype=np.float32)[:, None] + 0.5
    d = sd(xs, ys)
    cover = np.clip(0.5 - d, 0.0, 1.0)
    line = np.exp(-(np.abs(d) / (LINE_W * k)) ** 2)
    glow = _glow(np.maximum(d if soft is None else soft(xs, ys), 0.0), k)
    if kind == "level":  # as far as the level from the left, its end a little brighter
        to = x0 + W * (level or 0.0)
        reach = np.clip((to - xs) / (5 * k) + 0.5, 0.0, 1.0)
        head = 0.35 * np.exp(-((xs - to) ** 2 + (ys - (y_top + H)) ** 2) / (2 * (3.5 * k) ** 2))
        line, glow = line * reach, glow * reach + head * reach
    elif kind == "alarm":  # her two lower corners
        cy, spread_ = y_top + H - r, (r + 14 * k) ** 2
        near = np.maximum(np.exp(-((xs - (x0 + r)) ** 2 + (ys - cy) ** 2) / spread_),
                          np.exp(-((xs - (x0 + W - r)) ** 2 + (ys - cy) ** 2) / spread_))
        line, glow = line * near, glow * near
    rows = cols = None
    if drop and arm > 0:  # the top of the screen either side: how far below it, and how far out from her shoulders
        below = ys[:, 0] - y_top
        rows = (np.exp(-(below / (LINE_W * k)) ** 2), _glow(below, k))
        out = np.maximum(x0 - xs, xs - (x0 + W))  # px past her sides
        cols = np.where(out > 0, out / max(arm, 1.0), -1.0).astype(np.float32)
        if kind == "level":
            cols[xs > x0] = -1.0  # a level's light runs out to the left only
    # only the pixels it lights, kept as their places and their own line, glow and arms: inside her and far off it's
    # nothing, and working those out each frame took 33 ms of a panel's 56 (30 October 2026)
    some = (cover < 0.999) & ((line + glow) > 1 / 512)
    if rows is not None:
        some |= (rows[1][:, None] > 1 / 512) & (cols[None, :] >= 0)
    py, px = np.nonzero(some)
    picked = {"py": py, "px": px, "pl": line[py, px], "pg": glow[py, px], "keep": 1.0 - cover[py, px]}
    if rows is not None:
        picked.update(pr0=rows[0][py], pr1=rows[1][py], pc=cols[px])
    return dict({"box": (slice(Y0, Y1), slice(X0, X1)), "line": line, "glow": glow, "rows": rows, "cols": cols,
                 "arm": arm, "cover": cover, "k": k}, **picked)


def shine(buf, f, light, strength, now, dark=True):
    """light laid over buf, the window's picture (blue, green, red, alpha bytes, premultiplied), where f (field) says
    and strength bright: over the shadow round the island, never the island itself, and premultiplied, as Windows
    needs. On a dark island its line is near white, on a light one the colour itself, or it would vanish on a light
    screen; and its glow is a lighter tint of the colour either way: laid over a wallpaper of another colour, the
    colour itself made mud (green on red came out brown, the owner's screenshot, 30 October 2026), where a light tint
    brightens it, as light does. Returns the box it went over, (x0, y0, x1, y1), or None."""
    if f is None or strength <= 0.003:
        return None
    k, (rows_sl, cols_sl) = f["k"], f["box"]
    line, glow = f["pl"], f["pg"]  # only where it lights (field)
    if f["rows"] is not None:
        c = f["pc"]
        front = light.spread(now)  # the arms running out as it flares, their ends soft, fading along them
        along = np.where(c >= 0, np.clip((front - c) * f["arm"] / (8 * k) + 0.5, 0.0, 1.0) *
                         np.clip(1.0 - c, 0.0, 1.0) ** 1.4, 0.0)
        line = line + f["pr0"] * along
        glow = glow + f["pr1"] * along
    keep = f["keep"] * strength
    L = np.minimum(line, 1.0) * keep
    G = np.minimum(glow, 1.0) * keep
    a = np.minimum(L + G, 1.0)
    colour = np.asarray(light.colour, np.float32)
    core = colour + (1.0 - colour) * 0.6 if dark else colour
    tint = colour + (1.0 - colour) * GLOW_TINT
    rgb = core[None, :] * L[:, None] + tint[None, :] * G[:, None]
    np.minimum(rgb, a[:, None], out=rgb)  # premultiplied: no channel brighter than its alpha
    ys, xs = f["py"] + rows_sl.start, f["px"] + cols_sl.start
    out = buf[ys, xs].astype(np.float32)
    out *= (1.0 - a)[:, None]
    out[:, :3] += rgb[:, ::-1] * 255.0
    out[:, 3] += a * 255.0
    out += 0.5
    np.minimum(out, 255.0, out=out)
    buf[ys, xs] = out
    return cols_sl.start, rows_sl.start, cols_sl.stop, rows_sl.stop
