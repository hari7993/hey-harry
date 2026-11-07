"""The agents' cursors (4 November 2026, the owner's ask, from Vercel's Ship video of coloured cursors rebuilding a
page together): each job going in the background gets an arrow of its own colour with its name beside it, gliding
to what it works on (agent.do_one aims it, agent.observe sends it to its window), and a pill at the bottom of the
screen says how many are going and, once the last one's done, how long they took together.

What's drawn is only drawn: your mouse stays yours, and the jobs still take turns with the keyboard and the mouse
(agent.SCREEN). Every window here is click-through, never takes the focus, isn't in the taskbar or Alt+Tab, and is
left out of her own screenshots (winplatform.NO_CAPTURE), as overlay.py's are, on its drawing thread (overlay.UI).
The state is plain Python (begin, aim, look, end, summary), safe from any thread; only _wake reaches Windows, and
the tests replace it."""
import math
import threading
import time

# one colour an agent, as the video's: blue, pink, green, orange, purple
COLOURS = ((0.04, 0.52, 1.0), (1.0, 0.22, 0.56), (0.13, 0.75, 0.36), (1.0, 0.55, 0.0), (0.6, 0.36, 1.0))
MOST = 5  # agents at a time, one colour each (siri.JOB_WORKERS)
GLIDE = 0.5  # seconds a cursor takes to get most of the way to where it's sent
FADE = 0.4  # seconds a cursor or the pill takes to go
DONE_FOR = 4.0  # seconds "Done by 3 agents in 47.0s" stays
LABEL_WORDS, LABEL_CHARS, NOTE_CHARS = 4, 26, 18
LITTLE = {"a", "an", "the", "to", "and", "or", "in", "on", "at", "for", "with", "about", "of", "from", "into", "my"}
OFF_SCREEN = -10000  # where Windows keeps a window that's out of sight, her own browser's: no cursor goes there
# the arrow, its tip at (0, 0), in points: Windows' own pointer's shape
ARROW = ((0.0, 0.0), (0.0, 16.5), (4.0, 12.6), (6.9, 19.2), (9.6, 18.0), (6.8, 11.6), (12.0, 11.6))
NOTES = {"click": "clicking", "type": "typing", "keys": "pressing keys", "scroll": "scrolling", "open": "opening",
         "website": "opening", "switch": "switching"}

LOCK = threading.Lock()
AGENTS = {}  # job id: its Agent, while it goes or waits on your yes, and for a moment after as it fades
RUN = {"start": None, "ids": set(), "steps": 0, "ended": None, "took": 0.0}  # the agents going together now


class Agent:
    """One job's cursor: its slot (1 to MOST) and colour, its name, what it's doing now (note), where it's going
    (target, real pixels; None, beside the pill), the window it's to go to the middle of once that's found (wanted),
    and whether it's going, waiting on your yes or done (state, since)."""

    def __init__(self, job_id, slot, label, now):
        self.id, self.slot, self.label = job_id, slot, label
        self.colour = COLOURS[(slot - 1) % len(COLOURS)]
        self.note, self.steps, self.target, self.wanted, self.window = "", 0, None, None, None
        self.state, self.born, self.since = "going", now, now

    def text(self):
        """What its label says: "1 Night light", with what it's doing after it."""
        if self.state == "waiting":
            return f"{self.slot} {self.label} \u00b7 waiting for you"
        return f"{self.slot} {self.label}" + (f" \u00b7 {self.note}" if self.note else "")

    def alpha(self, now):
        """How strongly it shows: faded in as it starts, softer while it waits on you, faded out once it's done."""
        if self.state == "ended":
            return max(0.0, 1.0 - (now - self.since) / FADE)
        return min(1.0, (now - self.born) / 0.2) * (0.7 if self.state == "waiting" else 1.0)


def label_of(goal):
    """A few words of a job's goal for its cursor: "Turn on night light" of a longer goal's first words, never ending
    on a little word ("Send a mail", not "Send a mail to")."""
    words = " ".join(str(goal or "").split()).rstrip(".!?;: ").split()[:LABEL_WORDS]
    while len(words) > 1 and words[-1].lower() in LITTLE:
        words.pop()
    text = " ".join(words)
    if len(text) > LABEL_CHARS:
        text = text[:LABEL_CHARS - 1].rstrip() + "\u2026"
    return (text[:1].upper() + text[1:]) or "Task"


def point_of(where):
    """(x, y) of a point, or of the middle of a rect (left, top, right, bottom); None for nothing, an empty rect, or a
    place out of sight (OFF_SCREEN)."""
    try:
        values = [float(v) for v in where]
    except (TypeError, ValueError):
        return None
    if len(values) == 4:
        left, top, right, bottom = values
        if right <= left or bottom <= top:
            return None
        x, y = (left + right) / 2, (top + bottom) / 2
    elif len(values) == 2:
        x, y = values
    else:
        return None
    if not (math.isfinite(x) and math.isfinite(y)) or x < OFF_SCREEN or y < OFF_SCREEN:
        return None
    return x, y


def _alive():
    return [a for a in AGENTS.values() if a.state != "ended"]


def begin(job_id, goal):
    """Job job_id's cursor, from now till end(): a colour no other going has, its name from goal (label_of), next to
    the pill till it's sent somewhere. A job going again after your yes keeps its own. Returns its slot."""
    now = time.time()
    with LOCK:
        _tidy(now)
        if not _alive():  # the first of a new lot
            RUN.update(start=now, ids=set(), steps=0, ended=None, took=0.0)
        agent = AGENTS.get(job_id)
        if agent is None or agent.state == "ended":
            used = {a.slot for a in _alive()}
            slot = next((n for n in range(1, MOST + 1) if n not in used), len(used) + 1)
            agent = AGENTS[job_id] = Agent(job_id, slot, label_of(goal), now)
        agent.state, agent.since = "going", now
        RUN["ids"].add(job_id)
        RUN["ended"] = None
        slot = agent.slot
    _wake()
    return slot


def aim(job_id, where=None, note=""):
    """Job job_id's cursor to where its step acts, a point or a control's rect (point_of), with what it's doing
    (note); with nowhere, or a place out of sight, it stays where it is. Each one is a step in the pill. False if
    the job has no cursor going."""
    with LOCK:
        agent = AGENTS.get(job_id)
        if agent is None or agent.state != "going":
            return False
        spot = point_of(where) if where is not None else None
        if spot is not None:
            agent.target, agent.wanted = spot, None
        agent.note = " ".join(str(note or "").split())[:NOTE_CHARS]
        agent.steps += 1
        RUN["steps"] += 1
    _wake()
    return True


def look(job_id, hwnd):
    """Job job_id's cursor to the middle of its window hwnd, the first time it looks at it: where that is is found
    when it's drawn. False if it's on it already, or has no cursor going."""
    if not isinstance(hwnd, int) or isinstance(hwnd, bool) or not hwnd:
        return False
    with LOCK:
        agent = AGENTS.get(job_id)
        if agent is None or agent.state != "going" or agent.window == hwnd:
            return False
        agent.window = agent.wanted = hwnd
    _wake()
    return True


def end(job_id, waiting=False):
    """Job job_id's go over: its cursor fades, or with waiting (a step held for your yes) it stays, softer, saying so
    till the job goes again or is stopped. Once none is going or waiting, the pill says how long they all took."""
    now = time.time()
    with LOCK:
        agent = AGENTS.get(job_id)
        if agent is None or agent.state == "ended" or (waiting and agent.state == "waiting"):
            return
        agent.state, agent.since = ("waiting" if waiting else "ended"), now
        if not _alive():
            RUN["ended"] = now
            RUN["took"] = now - (RUN["start"] or now)
    _wake()


def summary(now=None):
    """What the pill at the bottom says: "3 agents · 12 steps" while any go, "2 agents waiting for you" while they
    only wait on your yes, "Done by 3 agents in 47.0s" for a few seconds after the last, else ""."""
    with LOCK:
        return _summary(time.time() if now is None else now)


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _summary(now):
    going = sum(a.state == "going" for a in AGENTS.values())
    waiting = sum(a.state == "waiting" for a in AGENTS.values())
    if going:
        return f"{_plural(going, 'agent')} \u00b7 {_plural(RUN['steps'], 'step')}" + \
            (f" \u00b7 {waiting} waiting for you" if waiting else "")
    if waiting:
        return f"{_plural(waiting, 'agent')} waiting for you"
    if RUN["ended"] is not None and RUN["ids"] and now - RUN["ended"] < DONE_FOR:
        return f"Done by {_plural(len(RUN['ids']), 'agent')} in {RUN['took']:.1f}s"
    return ""


def _pill_alpha(now):
    if _alive():
        return min(1.0, (now - (RUN["start"] or now)) / 0.25)
    if RUN["ended"] is None or not RUN["ids"]:
        return 0.0
    return max(0.0, min(1.0, (DONE_FOR - (now - RUN["ended"])) / FADE))


def _tidy(now):
    """Cursors faded out, gone."""
    for job_id in [i for i, a in AGENTS.items() if a.state == "ended" and now - a.since >= FADE]:
        AGENTS.pop(job_id, None)


def fleet():
    """The cursors as they are: [(job id, slot, its label's words, state)], by slot. For the tests and the log."""
    with LOCK:
        return [(a.id, a.slot, a.text(), a.state) for a in sorted(AGENTS.values(), key=lambda a: a.slot)]


# --------------------------------------------------------------------------- on the drawing thread
DRAWN = {"on": False, "pointers": {}, "pill": None, "home": None, "last": 0.0}


def _wake():
    """The cursors' frames going on the drawing thread (overlay.UI), if they aren't already. Never in the way of a
    job: a drawing thread that won't start is only printed. The tests replace it."""
    try:
        import overlay
        ui = overlay.UI.get()
        ui.call(_start, ui, wait=False)
    except Exception as exc:
        print(f"  agents' cursors: {exc!r}")


def _start(ui):
    if not DRAWN["on"]:
        DRAWN["on"], DRAWN["last"] = True, time.time()
        ui.animate("agents", lambda: _frame(ui))


def _polygon(points, ss=4):
    """How much of each pixel the polygon covers, 0 to 1, from ss by ss samples a pixel: (left, top, cover)."""
    import numpy as np
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    x0, y0 = int(math.floor(min(xs))) - 1, int(math.floor(min(ys))) - 1
    w, h = int(math.ceil(max(xs))) + 2 - x0, int(math.ceil(max(ys))) + 2 - y0
    gy, gx = np.mgrid[0:h * ss, 0:w * ss].astype(np.float32)
    px, py = x0 + (gx + 0.5) / ss, y0 + (gy + 0.5) / ss
    inside = np.zeros(px.shape, bool)
    for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]):
        if ay == by:
            continue
        crosses = (ay > py) != (by > py)
        inside ^= crosses & (px < ax + (py - ay) * (bx - ax) / (by - ay))
    return x0, y0, inside.reshape(h, ss, w, ss).mean(axis=(1, 3)).astype(np.float32)


class _Layer:
    """One small window of the cursors': layered, click-through, topmost, never focused, out of her screenshots;
    render() draws it, push() puts it where it goes."""

    def __init__(self, ui, s):
        import bubble
        import overlay
        import winplatform as win
        self.ui, self.s, self.key, self.size, self.shown = ui, s, None, (1, 1), False
        ex = overlay.WS_EX_LAYERED | overlay.WS_EX_TRANSPARENT | overlay.WS_EX_TOPMOST | overlay.WS_EX_TOOLWINDOW | \
            overlay.WS_EX_NOACTIVATE
        self.hwnd = ui.window(ex, None, -32000, -32000, 1, 1)
        win.NO_CAPTURE.append(self.hwnd)  # never in her own screenshots
        self.dc = bubble._new_dc(None)
        self.bitmap = self.dib = self.old = None

    def _canvas_to_window(self, canvas):
        import bubble
        size = (canvas.w, canvas.h)
        if self.bitmap is None or size != self.size:
            if self.bitmap is not None:
                bubble._select(self.dc, self.old)
                bubble._delete(self.bitmap)
            self.bitmap, self.dib = bubble._dib(self.dc, *size)
            old = bubble._select(self.dc, self.bitmap)
            self.old = self.old or old
            self.size = size
        self.dib[:] = canvas.bgra()

    def push(self, x, y, alpha):
        """Its top left corner to (x, y), real pixels, drawn alpha strong (0 to 1)."""
        import ctypes
        from ctypes import wintypes as wt
        import bubble
        import overlay
        bubble._flush()
        pos, size, src = wt.POINT(int(round(x)), int(round(y))), wt.SIZE(*self.size), wt.POINT(0, 0)
        blend = bubble._BLEND(0, 0, max(0, min(255, int(alpha * 255 + 0.5))), 1)
        bubble._ULW(self.hwnd, None, ctypes.byref(pos), ctypes.byref(size), self.dc, ctypes.byref(src), 0,
                    ctypes.byref(blend), 2)
        if not self.shown:
            overlay._u.ShowWindow(self.hwnd, overlay.SW_SHOWNOACTIVATE)
            self.shown = True

    def close(self):
        import bubble
        import overlay
        overlay._u.ShowWindow(self.hwnd, overlay.SW_HIDE)
        self.ui.destroy(self.hwnd)
        if self.bitmap is not None:
            bubble._select(self.dc, self.old)
            bubble._delete(self.bitmap)
        bubble._delete_dc(self.dc)


class _Pointer(_Layer):
    """An agent's arrow and its label, its tip pad pixels in from the window's top left corner; x, y, where its tip
    is drawn now, gliding to its target."""

    def __init__(self, ui, s, x, y):
        import bubble
        super().__init__(ui, s)
        self.font = bubble.Text(round(12.5 * s), 600)
        self.pad = int(round(8 * s))
        self.x, self.y = float(x), float(y)

    def render(self, colour, text):
        import overlay
        if self.key == (colour, text):
            return
        self.key = (colour, text)
        s, pad, font = self.s, self.pad, self.font
        arrow = [(pad + x * 1.25 * s, pad + y * 1.25 * s) for x, y in ARROW]
        lx, ly, lh = pad + 13 * s, pad + 20 * s, font.line + 8 * s
        lw = font.measure(text) + 16 * s
        canvas = overlay.Canvas(0, 0, int(math.ceil(lx + lw + pad)), int(math.ceil(ly + lh + pad)))
        x0, y0, cover = _polygon([(x + 1.2 * s, y + 2.0 * s) for x, y in arrow])
        canvas.paint(x0, y0, cover, overlay.SHADOW, 0.3)
        for (ax, ay), (bx, by) in zip(arrow, arrow[1:] + arrow[:1]):  # a white edge, so it shows on any page
            x0, y0, cover = overlay.segment(ax, ay, bx, by, 3.2 * s)
            canvas.paint(x0, y0, cover, overlay.HALO, 1.0)
        x0, y0, cover = _polygon(arrow)
        canvas.paint(x0, y0, cover, colour, 1.0)
        x0, y0, cover = overlay.filled_box(lx + 0.8 * s, ly + 1.6 * s, lx + lw + 0.8 * s, ly + lh + 1.6 * s, lh / 2)
        canvas.paint(x0, y0, cover, overlay.SHADOW, 0.22)
        x0, y0, cover = overlay.filled_box(lx - 1.2 * s, ly - 1.2 * s, lx + lw + 1.2 * s, ly + lh + 1.2 * s,
                                           lh / 2 + 1.2 * s)
        canvas.paint(x0, y0, cover, overlay.HALO, 0.9)
        x0, y0, cover = overlay.filled_box(lx, ly, lx + lw, ly + lh, lh / 2)
        canvas.paint(x0, y0, cover, colour, 1.0)
        canvas.paint(int(round(lx + 8 * s)) - 2, int(round(ly + 4 * s)) - 1, font.render(text), overlay.TEXT, 1.0)
        self._canvas_to_window(canvas)

    def close(self):
        super().close()
        self.font.close()


class _Pill(_Layer):
    """The pill at the bottom of the screen: a dot of each going agent's colour, and what summary() says."""

    def __init__(self, ui, s):
        import bubble
        super().__init__(ui, s)
        self.font = bubble.Text(round(13.5 * s), 600)

    def render(self, colours, text):
        import overlay
        if self.key == (tuple(colours), text):
            return
        self.key = (tuple(colours), text)
        s, font = self.s, self.font
        m, h = 6 * s, font.line + 18 * s
        dots = len(colours) * 12 * s + (6 * s if colours else 0)
        w = 16 * s + dots + font.measure(text) + 18 * s
        canvas = overlay.Canvas(0, 0, int(math.ceil(w + 2 * m)), int(math.ceil(h + 2 * m)))
        x0, y0, cover = overlay.filled_box(m + 1 * s, m + 2.5 * s, m + w + 1 * s, m + h + 2.5 * s, h / 2, 2.5 * s)
        canvas.paint(x0, y0, cover, overlay.SHADOW, 0.25)
        x0, y0, cover = overlay.filled_box(m, m, m + w, m + h, h / 2)
        canvas.paint(x0, y0, cover, overlay.CAPTION_BG, 0.94)
        for i, colour in enumerate(colours):
            x0, y0, cover = overlay.disc(m + 16 * s + 4.5 * s + i * 12 * s, m + h / 2, 4.5 * s)
            canvas.paint(x0, y0, cover, colour, 1.0)
        canvas.paint(int(round(m + 16 * s + dots)) - 2, int(round(m + (h - font.line) / 2)) - 1, font.render(text),
                     overlay.TEXT, 1.0)
        self._canvas_to_window(canvas)

    def close(self):
        super().close()
        self.font.close()


def _home():
    """Where the pill goes, at the bottom middle of the main screen's work area, and that screen's scale."""
    import overlay
    _, work, s = overlay.monitor_at(0, 0)
    return (work[0] + work[2]) / 2, work[3] - 22 * s, s


def _window_spots(wanted):
    """The middle of each window cursors are sent to, where it is now: {hwnd: (x, y)}, those that can be seen."""
    import winplatform as win
    spots = {}
    for hwnd in wanted:
        try:
            spot = point_of(win.window_rect(hwnd))
        except Exception:
            spot = None
        if spot is not None:
            spots[hwnd] = spot
    return spots


def _frame(ui):
    """One frame: each cursor a little nearer where it's going, its label redrawn when it changes, the pill too;
    everything closed, and the frames stopped, once nothing's left to show."""
    try:
        return _draw(ui)
    except Exception as exc:
        print(f"  agents' cursors: {exc!r}")
        _close_all()
        return False


def _draw(ui):
    now = time.time()
    with LOCK:
        _tidy(now)
        wanted = {a.wanted for a in AGENTS.values() if a.wanted is not None}
    spots = _window_spots(wanted) if wanted else {}
    if DRAWN["home"] is None:
        DRAWN["home"] = _home()
    hx, hy, s = DRAWN["home"]
    with LOCK:
        for agent in AGENTS.values():
            if agent.wanted in spots:  # spread a little by slot, so two on one window don't sit on each other
                x, y = spots[agent.wanted]
                spread = (agent.slot - 1) % MOST - (MOST - 1) / 2
                agent.target, agent.wanted = (x + spread * 30 * s, y + (agent.slot % 2) * 18 * s), None
        seen = [(a.id, a.slot, a.colour, a.text(), a.alpha(now), a.target)
                for a in sorted(AGENTS.values(), key=lambda a: a.slot)]
        words, pill_alpha = _summary(now), _pill_alpha(now)
        colours = [a.colour for a in sorted(_alive(), key=lambda a: a.slot)]
    if not seen and pill_alpha <= 0:
        _close_all()
        return False
    dt = max(0.0, min(0.1, now - DRAWN["last"]))
    DRAWN["last"] = now
    follow = 1.0 - math.exp(-dt * 3.0 / GLIDE)
    pointers = DRAWN["pointers"]
    for job_id in [i for i in pointers if i not in {row[0] for row in seen}]:
        pointers.pop(job_id).close()
    for job_id, slot, colour, text, alpha, target in seen:
        tx, ty = target or (hx + (slot - (MOST + 1) / 2) * 34 * s, hy - 70 * s)  # beside the pill till it's sent
        pointer = pointers.get(job_id)
        if pointer is None:
            pointer = pointers[job_id] = _Pointer(ui, s, hx, hy - 30 * s)
        pointer.x += (tx - pointer.x) * follow
        pointer.y += (ty - pointer.y) * follow
        pointer.render(colour, text)
        settled = max(0.0, 1.0 - math.hypot(tx - pointer.x, ty - pointer.y) / (24 * s))
        wobble = 3.0 * s * settled  # a little drift once it's there, so it reads as at work
        pointer.push(pointer.x - pointer.pad + wobble * math.sin(now * 1.7 + slot * 1.3),
                     pointer.y - pointer.pad + wobble * math.cos(now * 1.3 + slot * 2.1), alpha)
    pill = DRAWN["pill"]
    if words and pill_alpha > 0:
        if pill is None:
            pill = DRAWN["pill"] = _Pill(ui, s)
        pill.render(colours, words)
        pill.push(hx - pill.size[0] / 2, hy - pill.size[1], pill_alpha)
    elif pill is not None:
        DRAWN["pill"] = None
        pill.close()
    return True


def _close_all():
    for pointer in DRAWN["pointers"].values():
        try:
            pointer.close()
        except Exception as exc:
            print(f"  agents' cursors: {exc!r}")
    DRAWN["pointers"].clear()
    if DRAWN["pill"] is not None:
        try:
            DRAWN["pill"].close()
        except Exception as exc:
            print(f"  agents' cursors: {exc!r}")
        DRAWN["pill"] = None
    DRAWN["on"], DRAWN["home"] = False, None
