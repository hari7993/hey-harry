"""Her eyes on you, through the laptop's camera (29 October 2026, the owner's ask): she knows when you've come back to
the laptop and welcomes you then, and what you've told her to do when she sees something is done ("when I wear my
glasses, turn on light mode": cues.py). Off unless you turn it on, in Settings > Let her see you.

Watching all the time while it's on, as the owner asked ("it needs to watch me all the time"): its light stays on.
Whether you're there is worked out on this PC by YuNet, OpenCV Zoo's face finder (MIT, 0.2 MB, downloaded once), or
OpenCV's older Haar finder if that can't be had: a frame every couple of seconds, looked at and let go, none kept.
What you look like is asked of the model that sees pictures only for a rule that needs it (cues.py,
siri.camera_look), one small frame at a time: as you come back, as soon as your face looks different and settles
(your glasses on or off), and every couple of minutes. Different is told on this PC: the band of your face round
your eyes, lined up by YuNet's points for your eyes, nose and mouth, against the one at her last look. On 29 October
a face sitting still matched itself at about 0.97, and moving closer took it to about 0.65.

Not while the PC's locked: unlocking is coming back, and siri.watch_return welcomes you for that."""
import collections
import os
import threading
import time

import numpy as np

import speech

EVERY = 2.0  # seconds between frames while she watches
AWAY = 90.0  # seconds with no face, and no typing, before you're taken as gone
BACK_AFTER = 300.0  # gone at least this long, and coming back is welcomed: not a few minutes looking at your phone
LOOK_EVERY = 120.0  # seconds between looks at you for the look rules while you're there, when nothing's changed. It
# was 5 minutes, and the owner put their glasses on and waited for light mode that didn't come
LOOK_GAP = 20.0  # seconds at least between two looks, however much changes
CHANGED = 0.75  # a settled face less like the one at her last look than this (0 to 1) is looked at again
STEADY = 0.85  # and settled: this like the frame before, not turning or moving
RETRY = 60.0  # seconds before a camera that wouldn't open is tried again
WARM = 0.8  # seconds of frames let go as the camera opens, while it sets its light
KEEP = 3.0  # seconds of frames kept while it's open, at half size, for a look at what was in front of it when a
# sharp sound came (cues.py: a snap is a sound with your hand up): the sound's judged 0.9 s after it, and frames from
# a second before it are looked at
NEAR = 0.08  # a face at least this share of the frame's width is someone at the laptop, not across the room. The
# owner's was 14 to 23% at the laptop on 29 October 2026; across a room a face is a few percent
RATE = 5  # frames a second asked of it as it watches: this laptop's makes 10 whatever it's asked below that
KEEP_EVERY = 0.09  # seconds between frames kept for around(), whatever it makes: 30 a second for 3 s was 20 MB


class Camera:
    """The webcam, opened when it's needed and let go after: frame() is an RGB picture, or None. While it's open a
    thread of its own reads every frame it makes, keeping the newest and KEEP seconds of them at half size (around).
    Held open (hold) by hand control, at the rate it asks, so her eyes closing it for theirs never closes it under
    it."""

    def __init__(self, index=0):
        self.index, self.cap = index, None
        self.lock = threading.Lock()
        self.kept = collections.deque(maxlen=60)  # (time.monotonic(), a half-size BGR frame), KEEP seconds of them
        self.newest = None  # (time.monotonic(), the newest BGR frame, whole)
        self.stop, self.reader = threading.Event(), None
        self.holders = {}  # who's holding it open: name: the frames a second they want
        self.rate = RATE  # what it was asked for as it opened
        # one thread at a time opening or closing it: on 29 October hand control letting go reopened it while her
        # eyes' thread used it, it wouldn't open, and she crashed in the camera's own code (0xC0000374, heap)
        self.gate = threading.RLock()

    def open(self):
        with self.gate:
            if self.cap is not None:
                return self
            return self._open()

    def _open(self):
        import cv2
        for go in range(3):  # one let go a moment ago may not open again straight away
            for api in (cv2.CAP_DSHOW, cv2.CAP_MSMF):  # DirectShow first: Media Foundation wouldn't open this laptop's
                cap = cv2.VideoCapture(self.index, api)
                if cap.isOpened():
                    break
                cap.release()
            else:
                time.sleep(0.5)
                continue
            break
        else:
            raise RuntimeError("the camera won't open: Windows may have it off for desktop apps (Settings > Privacy & "
                               "security > Camera), or another app has it")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.rate = max([RATE] + list(self.holders.values()))
        cap.set(cv2.CAP_PROP_FPS, self.rate)  # kept open all the time: at 30 a second it took 6% of a core on this
        # laptop to keep making frames nobody looked at, at 5 3%. One every 2 s is all her eyes look at
        end = time.time() + WARM
        while time.time() < end:  # the first frames come dark, while it sets how bright to make them
            cap.read()
        self.cap, self.stop = cap, threading.Event()
        self.reader = threading.Thread(target=self._read, args=(cap, self.stop), name="camera", daemon=True)
        self.reader.start()
        return self

    def _read(self, cap, stop):
        import cv2
        while not stop.is_set():
            ok, bgr = cap.read()
            if not ok or bgr is None:
                time.sleep(0.05)
                continue
            now = time.monotonic()
            keep = not self.kept or now - self.kept[-1][0] >= KEEP_EVERY
            small = cv2.resize(bgr, (bgr.shape[1] // 2, bgr.shape[0] // 2), interpolation=cv2.INTER_AREA) \
                if keep else None
            with self.lock:
                self.newest = (now, bgr)
                if keep:
                    self.kept.append((now, small))
                while self.kept and now - self.kept[0][0] > KEEP:
                    self.kept.popleft()

    def frame(self, wait=1.5):
        """The newest frame as RGB, one made in the last second, waiting up to wait seconds for it; or None."""
        end = time.monotonic() + wait
        while self.cap is not None:
            with self.lock:
                newest = self.newest
            if newest is not None and time.monotonic() - newest[0] < 1.0:
                return np.ascontiguousarray(newest[1][:, :, ::-1])
            if time.monotonic() > end:
                return None
            time.sleep(0.03)
        return None

    def around(self, start, end):
        """[(time.monotonic(), half-size BGR frame)] kept from start to end."""
        with self.lock:
            return [(t, f) for t, f in self.kept if start <= t <= end]

    def newest_bgr(self, after=0.0, wait=0.25):
        """(time.monotonic(), the newest whole BGR frame) once there's one newer than after, waiting up to wait
        seconds; or None."""
        end = time.monotonic() + wait
        while True:
            with self.lock:
                newest = self.newest
            if newest is not None and newest[0] > after:
                return newest
            if time.monotonic() > end or self.cap is None:
                return None
            time.sleep(0.005)

    def hold(self, name, fps=RATE):
        """name keeps it open, at fps frames a second at least, till it lets go (let_go): opened if it wasn't,
        opened again at the rate if it was open slower."""
        with self.gate:
            self.holders[name] = fps
            if self.cap is not None and fps > self.rate:
                self._close()
            self.open()

    def let_go(self, name):
        """name's done with it. It stays open at the rate it has, and goes back to the usual one next time it's
        opened: not opened again here, as opening it again as hand control stopped is what crashed her."""
        with self.gate:
            self.holders.pop(name, None)

    def close(self):
        """Closed, unless someone's holding it open (hold)."""
        with self.gate:
            if not self.holders:
                self._close()

    def _close(self):
        with self.gate:
            if self.cap is None:
                return
            cap, reader = self.cap, self.reader
            self.stop.set()
            self.cap = None
            if reader is not None:
                reader.join(3.0)  # its read ends within a frame
            with self.lock:  # after it's stopped, or the frame it was reading lands after
                self.kept.clear()
                self.newest = None
            if reader is not None and reader.is_alive():  # still in the camera's own code: let go of it under that,
                # and it crashes, so it's let go once that read is over
                threading.Thread(target=lambda: (reader.join(30.0), cap.release()), daemon=True).start()
                return
            cap.release()

    @property
    def on(self):
        return self.cap is not None


class Faces:
    """The faces in a picture: [(x, y, w, h, score, points)], the biggest first. points: YuNet's five, (x, y) of
    each eye, the nose and the mouth's corners, or None from the Haar finder."""

    def __init__(self, notify=None):
        import cv2
        cv2.setNumThreads(1)  # a small face finder: on every core it took 19 ms of CPU a look, on one 6 ms
        self.cv2, self.haar, self.yunet = cv2, None, None
        try:
            self.yunet = cv2.FaceDetectorYN.create(speech.model_path("face", notify), "", (320, 320), 0.8, 0.3, 20)
        except Exception as exc:
            print(f"  camera: no YuNet ({exc!r}), using OpenCV's Haar finder")
            self.haar = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))

    def find(self, rgb):
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])
        h, w = bgr.shape[:2]
        if self.yunet is not None:
            k = 2 if w >= 480 else 1  # found in a half-size frame: a face at the laptop is 60 px across in it, and
            # each look takes a quarter of the time, as the camera's on all the time
            small = self.cv2.resize(bgr, (w // k, h // k), interpolation=self.cv2.INTER_AREA) if k > 1 else bgr
            self.yunet.setInputSize((w // k, h // k))
            _, found = self.yunet.detect(small)
            faces = [] if found is None else [(int(f[0] * k), int(f[1] * k), int(f[2] * k), int(f[3] * k),
                                               float(f[14]), np.float32(f[4:14]).reshape(5, 2) * k) for f in found]
        else:
            gray = self.cv2.cvtColor(bgr, self.cv2.COLOR_BGR2GRAY)
            faces = [(int(x), int(y), int(fw), int(fh), 1.0, None)
                     for x, y, fw, fh in self.haar.detectMultiScale(gray, 1.2, 5, minSize=(60, 60))]
        return sorted(faces, key=lambda f: -f[2] * f[3])


# Where YuNet's five points go in a 64 px face, lined up: ArcFace's 112 px template, scaled
TEMPLATE = np.float32([[21.9, 29.5], [42.0, 29.4], [32.0, 41.0], [23.7, 52.8], [40.4, 52.7]])


def eye_band(rgb, face):
    """The band of a face round its eyes, where glasses sit, lined up by its five points and evened out for the
    light, to tell whether it looks different. None without the points."""
    if len(face) < 6 or face[5] is None:
        return None
    import cv2
    m, _ = cv2.estimateAffinePartial2D(np.float32(face[5]), TEMPLATE)
    if m is None:
        return None
    gray = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2GRAY)
    band = cv2.GaussianBlur(cv2.warpAffine(gray, m, (64, 64), flags=cv2.INTER_AREA)[14:40, 4:60].astype(np.float32),
                            (3, 3), 0)
    return (band - band.mean()) / (band.std() + 1e-6)


def likeness(a, b):
    """How alike two eye bands are, 1 the same, 0 nothing alike."""
    return float((a * b).mean())


class Eyes:
    """Whether you're in front of the laptop, on a thread of its own (run). on_back(since, rgb): you've come back after
    being gone since since, rgb what she saw then, or None if it was your typing that said so. on_look(rgb): a
    picture of you when wants_look() says a rule needs one: when you look different, and every LOOK_EVERY."""

    def __init__(self, on_back, on_look=None, wants_look=lambda: False, enabled=lambda: True, idle=None, locked=None,
                 camera=None, faces=None, clock=time.time, notify=None):
        import winplatform as win
        self.on_back, self.on_look, self.wants_look, self.enabled = on_back, on_look, wants_look, enabled
        self.idle = idle or win.idle_seconds
        self.locked = locked or win.session_locked
        self.camera, self.faces, self.clock, self.notify = camera or Camera(), faces, clock, notify
        self.lock = threading.Lock()  # one at a time at the camera: this thread, and a clap asking if you're there
        self.seen = clock()  # when you were last seen, or last typed
        self.gone = None  # since when you've been gone, while you are
        self.looked = 0.0
        self.failed, self.failed_at = None, 0.0  # why the camera wouldn't open, and when, so it isn't tried every 2 s
        self.band = None  # your eye band at her last look
        self.last = None  # and the one before this
        self.unlike = 0  # frames in a row you've looked settled but different

    def _finder(self):
        if self.faces is None:
            self.faces = Faces(self.notify)
        return self.faces

    def someone(self, rgb):
        """True if a face near enough to be at the laptop is in rgb."""
        return self.near(rgb) is not None

    def near(self, rgb):
        """The face near enough to be at the laptop in rgb, or None."""
        faces = self._finder().find(rgb)
        return faces[0] if faces and faces[0][2] >= NEAR * rgb.shape[1] else None

    def snap(self, keep=False):
        """A picture from the camera now, opening it if need be, closing it after unless keep. None if it won't."""
        with self.lock:
            try:
                rgb = self.camera.open().frame()
                self.failed = None
            except Exception as exc:
                if self.failed != str(exc):
                    print(f"  camera: {exc}")
                self.failed, self.failed_at = str(exc), self.clock()
                rgb = None
            if not keep:
                self.camera.close()
            return rgb

    def here(self):
        """True if you're in front of the laptop now: seen in the last few seconds, typing, or in a fresh picture."""
        now = self.clock()
        if self.idle() < EVERY * 2 or (self.gone is None and now - self.seen < EVERY * 2 + 0.5):
            return True
        rgb = self.snap(keep=self.camera.on)
        if rgb is None:  # no camera to look with: taken as there, as the claps were someone's
            return self.failed is not None
        return self.someone(rgb)

    def tick(self):
        """One look, every EVERY seconds: the camera on all the time, off only while the PC's locked or it's turned
        off. You're there while she sees your face or you type."""
        now = self.clock()
        if not self.enabled() or self.locked():
            with self.lock:
                self.camera.close()
            self.seen, self.gone, self.last, self.unlike = now, None, None, 0  # unlocking is coming back, and that's
            # welcomed apart from this
            return
        rgb = None if self.failed and now - self.failed_at < RETRY else self.snap(keep=True)
        face = self.near(rgb) if rgb is not None else None
        if face is None and self.idle() >= EVERY * 2:
            if self.gone is None and now - self.seen >= AWAY:
                self.gone = self.seen
                self.last, self.unlike = None, 0
                print(f"  (camera: you've gone, {time.strftime('%H:%M')})")
            return
        self.seen = now
        band = eye_band(rgb, face) if face is not None else None
        if self._back(now, rgb if face is not None else None):
            self.band, self.last, self.unlike = band, band, 0  # she looked at you as she welcomed you
            return
        if face is not None:
            self._watch(now, rgb, band)

    def _watch(self, now, rgb, band):
        """A look at you for the look rules, when you look different from her last look and have settled, or
        LOOK_EVERY has gone by."""
        if not (self.on_look and self.wants_look()):
            return
        due = now - self.looked >= LOOK_EVERY  # the first time, straight away
        changed = False
        if not due and band is not None and self.band is not None and self.last is not None:
            settled = likeness(band, self.last) >= STEADY
            self.unlike = self.unlike + 1 if settled and likeness(band, self.band) < CHANGED else 0
            due = changed = self.unlike >= 2 and now - self.looked >= LOOK_GAP
        self.last = band
        if due:
            if changed:
                print(f"  (camera: you look different, {likeness(band, self.band):.2f} like before)")
            self.looked, self.band, self.unlike = now, band, 0
            self.on_look(rgb)

    def _back(self, now, rgb):
        """True if you've come back after long enough away to be welcomed, and were."""
        if self.gone is None:
            return False
        since, self.gone = self.gone, None
        print(f"  (camera: you're back, gone {(now - since) / 60:.0f} min{'' if rgb is not None else ', by your typing'})")
        if now - since >= BACK_AFTER:
            self.looked = now
            self.on_back(since, rgb)
            return True
        return False

    def run(self, stop=None):
        stop = stop or threading.Event()
        while not stop.wait(EVERY):
            try:
                self.tick()
            except Exception as exc:  # never the end of her eyes
                print(f"  camera: {exc!r}")
