"""Claps and finger snaps, heard by the mic on this PC (29 October 2026, the owner's ask): two claps in front of the
laptop start work mode, and a snap while music plays turns on dream mode, or whatever you've told her they're for
(cues.py keeps that). Nothing is sent anywhere.

Heard in the mic's raw sound, on a stream of its own (Ears). Windows' speech mode, which she listens to you in, keeps
voices and takes out everything else: recorded on the owner's laptop on 29 October, a snap that stood 40 dB over the
room in the raw sound didn't show in speech mode at all, and none of their snaps had ever reached her. The raw sound
has what the PC plays in it too, so a sharp sound that came out of the speakers (a drum in a song, a clap in a video)
is told by what the PC played just then (loopback.py) and doesn't count by its sound. A song has a drum or a hi-hat
every quarter of a second, though, so on 29 October every snap the owner made over "Blank Space" was taken for one:
one that's high enough to be a snap is left to the camera (on_maybe), as a drum never comes with your hand up.

A clap or a snap is a sharp sound: in its high notes, above about 2 kHz, where music and voices are quieter, it starts
all at once out of quiet and is gone within a tenth of a second or so, with nothing going on after it. In the owner's
room on 29 October their snaps and claps rang for 70 to 100 ms, so up to RING_MS counts; a knock's or a thump's sits
far lower (under LOWEST), and a voice or music goes on, and those aren't counted. Two sharp sounds 0.15 to 0.9 s
apart are a double clap, the cue, unless both were snaps. One alone is a snap by its sound only if it's short and
high (SNAP_MS, SNAPPY); one that rings longer may still be a snap, and is told by whether your hand was up in front
of the camera then (on_maybe, cues.py): a single clap could be a book put down. Never counted while you type or move
the mouse (a key's click is a sharp sound too), while anyone talks, while she does, or while you dictate; the caller
says when (feed's allowed).

Every sharp sound is written to the log with what it was taken for, how long it lasted, how high it was and how far
over the room's sound, so the lines below can be set from a real room."""
import queue
import threading
import time
from collections import deque

import numpy as np

RATE = 16000
STEP = 64  # 4 ms a frame
ABOVE = 20.0  # dB over the room's own high notes that makes a sharp start. The owner's snap was 40 dB over; thumps
# and taps on the desk 15 to 19 dB
LOUD = -50.0  # dBFS: and its high notes at least this loud
QUIET_BEFORE = 8.0  # dB over the room at most, in the 40 ms before it
GONE = 15.0  # dB under its peak that ends it
RING_MS = 150  # the longest a clap or a snap rings in its high notes, till GONE: up to 100 ms in the owner's room
SNAP_MS = 60  # and a snap told by its sound alone, this short (the first of the owner's snaps recorded: 8 ms)
LOWEST = 600.0  # Hz: a sharp sound's own sound sits at least this high, or it was a knock or a thump (0 to 500 Hz).
# One of the owner's claps sat at 700 Hz
SNAPPY = 2200.0  # Hz: a snap's sound sits at least this high; a clap's lower
MAYBE = 1200.0  # Hz: one sharp sound alone this high may have been a snap, if a hand was up (on_maybe)
STILL = 12.0  # still within this many dB of its peak 120 to 150 ms in: a voice or music going on, not a clap
JUDGE = 0.15  # seconds after its start that it's judged
TWICE = (0.15, 0.9)  # seconds between two sharp sounds that make a double clap
REST = 1.0  # seconds after a cue in which more sharp sounds are the same clapping or snapping, not a new cue
ROOM_FLOOR = -80.0  # the room is never taken as quieter than this, so a breath in a silent room isn't a clap
PC_BEFORE, PC_AFTER = 0.3, 0.06  # seconds round a sharp sound in which one the PC played was it, from the speakers
PC_SHARP = 10.0  # dB over what the PC's been playing that makes its own sharp sound
LOOK_GAP = 1.5  # seconds at least between two looks at the camera for sharp sounds the PC made too


def high(a):
    """The high notes of some audio: its second difference, which keeps 4 kHz and up, halves 2 kHz and takes most
    of 500 Hz and under away. Cheap, and what's before a block is carried in by the caller."""
    return a[2:] - 2 * a[1:-1] + a[:-2]


def db_frames(h):
    """dBFS of each STEP of h."""
    n = len(h) // STEP
    return 10 * np.log10((h[:n * STEP].reshape(n, STEP) ** 2).mean(axis=1) + 1e-12)


class Clapper:
    """Hears claps and snaps in the mic's raw 16 kHz sound fed to it as it comes, and calls on_cue("clap") for a
    double clap and on_cue("snap") for a snap. on_maybe(at): one sharp sound alone that may have been a snap, heard at
    at (time.monotonic, from feed's at), once no second one came. played(start, end): True if the PC itself played a
    sharp sound between those times."""

    def __init__(self, on_cue, log=print, played=None, on_maybe=None):
        self.on_cue, self.log, self.played, self.on_maybe = on_cue, log, played, on_maybe
        self.frames, self.dbs = deque(maxlen=64), deque(maxlen=64)  # the last quarter second, 4 ms at a time
        self.room = None  # the room's own high notes, dBFS, worked out as it goes from the first sound heard
        self.n = 0  # frames heard so far: the clock claps are timed by, so a late block doesn't change it
        self.start = None  # the frame a sharp sound started on, while it's waited on to judge
        self.started_at = None  # and when, by the clock feed's at goes by
        self.waiting = None  # (frame, a snap by its sound, maybe a snap, when) of a sharp sound judged, while a second
        # one may still come
        self.rested = -1 << 30  # the frame of the last cue
        self.tail = np.zeros(2, np.float32)  # the last two samples before this block, for high()
        self.rest = np.zeros(0, np.float32)
        self.at = None  # when the next sample was heard, if feed is told
        self.asked = -1e9  # when the camera was last asked about one the PC played a sharp sound with

    def feed(self, block, allowed=True, at=None):
        """Takes the next of the mic's audio. allowed: False while someone talks, she talks or you dictate: no sharp
        sound starts then. One that started before is judged all the same: a clap's own sound could make the
        listener think someone had started talking. at: time.monotonic() of the block's first sample, for played."""
        block = np.asarray(block, dtype=np.float32).reshape(-1)
        if at is not None:
            self.at = at - len(self.rest) / RATE
        a = np.concatenate([self.rest, block])
        whole = len(a) // STEP * STEP
        self.rest = a[whole:]
        h = high(np.concatenate([self.tail, a[:whole]]))
        if whole >= 2:
            self.tail = a[whole - 2:whole]
        dbs = db_frames(h)
        for i, db in enumerate(dbs):
            self._frame(a[i * STEP:(i + 1) * STEP], float(db), allowed)
            if self.at is not None:
                self.at += STEP / RATE

    def drop(self):
        """You've typed or moved the mouse: a sharp sound that's started is let go, as it was a key's click."""
        self.start = None

    def _frame(self, frame, db, allowed):
        if self.room is None:
            self.room = max(ROOM_FLOOR, db)
        self.frames.append(frame)
        self.dbs.append(db)
        self.n += 1
        if self.waiting is not None and (self.n - self.waiting[0]) * STEP / RATE > TWICE[1]:
            first, self.waiting = self.waiting, None  # no second one came
            if first[1]:
                self._cue("snap")
            elif first[2] and self.on_maybe is not None:
                self.on_maybe(first[3])
        if self.start is not None:
            if self.n - self.start >= int(JUDGE * RATE / STEP):
                self._judge()
                self.start = None
            return
        if allowed and db >= self.room + ABOVE and db >= LOUD:  # what came before only looked at then: 250 times
            before = list(self.dbs)[-11:-1]  # a second, it was most of the work
            if before and max(before) <= self.room + QUIET_BEFORE:
                self.start = self.n - 1  # this frame
                self.started_at = self.at
                return
        self._room(db)

    def _room(self, db):
        """The room's own high notes: down quickly, up slowly, and not at all for a sound well over it."""
        if db < self.room:
            self.room = max(ROOM_FLOOR, 0.9 * self.room + 0.1 * db)
        elif db < self.room + 6:
            self.room += 0.01 * (db - self.room)
        else:
            self.room += 0.0005 * (db - self.room)  # a room that's got louder for good, slowly

    def _judge(self):
        """What the sharp sound that started at self.start was: a snap, a clap or neither."""
        since = self.n - self.start
        dbs = np.array(list(self.dbs)[-since:])
        frames = list(self.frames)
        at = int(np.argmax(dbs[:5]))
        peak = float(dbs[at])
        under = np.nonzero(dbs[at:] < peak - GONE)[0]
        ms = (at + (int(under[0]) if len(under) else len(dbs) - at)) * STEP * 1000 / RATE
        late = dbs[int(0.12 * RATE / STEP):]
        still = len(late) > 0 and float(np.mean(late)) > peak - STILL
        # where its own sound sits: the spectrum of its first 32 ms less the room's, from the 32 ms before it
        sound = np.concatenate(frames[-since:][:8])
        room = np.concatenate(frames[-since - 10:-since - 2]) if len(frames) >= since + 10 else np.zeros_like(sound)
        win = np.hanning(len(sound))
        power = np.abs(np.fft.rfft(sound * win)) ** 2 - np.abs(np.fft.rfft(room[:len(sound)] * win)) ** 2
        power = np.clip(power, 0, None)
        freqs = np.fft.rfftfreq(len(sound), 1 / RATE)
        pitch = float((power * freqs).sum()) / (float(power.sum()) + 1e-12)
        sharp = not still and ms <= RING_MS and pitch >= LOWEST
        pc = sharp and self.played is not None and self.started_at is not None and \
            self.played(self.started_at - PC_BEFORE, self.started_at + PC_AFTER)
        snap = sharp and ms <= SNAP_MS and pitch >= SNAPPY  # a snap by its sound alone
        ask = pc and pitch >= MAYBE and self.on_maybe is not None and self.started_at - self.asked >= LOOK_GAP
        kind = ("from the PC, or a snap: asking the camera" if ask else "from the PC") if pc else \
            ("snap" if snap else "clap or snap" if pitch >= MAYBE else "clap") if sharp else "neither"
        self.log(f"  (a sharp sound: {kind}, {ms:.0f} ms, {pitch / 1000:.1f} kHz, {peak - self.room:.0f} dB over the "
                 f"room{', still going' if still else ''})")
        if ask:  # never counted by its sound, nor as half of a double clap: only your hand up says it was you
            self.asked = self.started_at
            self.on_maybe(self.started_at)
        elif sharp and not pc:
            self._counted(snap, self.start, pitch >= MAYBE, self.started_at, pitch >= SNAPPY)

    def _counted(self, snap, start, maybe=False, at=None, high=None):
        """A sharp sound counted: snap, a snap by its sound alone; maybe, high enough to have been one; high, as high
        as a snap (two of those are snapping, not clapping)."""
        if (start - self.rested) * STEP / RATE < REST:
            return  # more of the same clapping
        high = snap if high is None else high
        if self.waiting is None:
            self.waiting = (start, snap, maybe, at, high)
            return
        apart = (start - self.waiting[0]) * STEP / RATE
        if apart < TWICE[0]:
            return  # its own echo
        both = self.waiting[4] and high
        self.waiting = None
        self._cue("snap" if both else "clap")
        self.rested = start

    def _cue(self, kind):
        self.rested = self.n
        self.on_cue(kind)


class PCSound:
    """What the PC plays (loopback.Loopback), kept for the last couple of seconds as the loudness of its high notes,
    so a sharp sound the mic heard can be told as one that came out of the speakers."""

    def __init__(self):
        self.times, self.dbs = deque(maxlen=600), deque(maxlen=600)  # 2.4 s of 4 ms frames
        self.tail = np.zeros(2, np.float32)
        self.lock = threading.Lock()
        self.source = None

    def start(self):
        if self.source is None:
            import loopback
            self.source = loopback.Loopback(self.feed, every=0.03).start()
        return self

    def stop(self):
        if self.source is not None:
            self.source.stop()
            self.source = None

    def feed(self, block, at=None):
        block = np.asarray(block, dtype=np.float32).reshape(-1)
        at = time.monotonic() - len(block) / RATE if at is None else at
        h = high(np.concatenate([self.tail, block]))
        self.tail = block[-2:]
        with self.lock:
            for i, db in enumerate(db_frames(h)):
                self.times.append(at + i * STEP / RATE)
                self.dbs.append(float(db))

    @property
    def on(self):
        return self.source is not None

    def played(self, start, end):
        """True if what the PC played had a sharp sound of its own between start and end."""
        with self.lock:
            times, dbs = np.array(self.times), np.array(self.dbs)
        if not len(times):
            return False
        usual = float(np.median(dbs))
        inside = dbs[(times >= start) & (times <= end)]
        return bool(len(inside)) and float(inside.max()) >= max(usual + PC_SHARP, -70.0)


class Ears:
    """The mic's raw sound for a Clapper, on a stream of its own while Let her see you is on, and what the PC plays
    beside it. allowed(): whether a sharp sound may start now."""

    def __init__(self, on_cue, device=None, allowed=lambda: True, log=print, on_maybe=None):
        self.device, self.allowed, self.log = device, allowed, log
        self.pc = PCSound()
        self.clapper = Clapper(on_cue, log=log, played=self.pc.played, on_maybe=on_maybe)
        self.blocks = queue.Queue(maxsize=200)
        self.stream, self.stopped = None, threading.Event()
        self.pc_failed = None

    def start(self):
        import sounddevice as sd
        stream = None
        for raw in (True, False):  # raw: none of Windows' sound processing; not every mic offers it
            try:
                extra = sd.WasapiSettings(auto_convert=True)
                if raw:
                    extra._streaminfo.streamOption = sd._lib.eStreamOptionRaw
                stream = sd.InputStream(device=self.device, samplerate=RATE, channels=1, dtype="float32",
                                        blocksize=512, callback=self._heard, extra_settings=extra)
                break
            except Exception as exc:
                if not raw:
                    raise RuntimeError(f"the mic won't open for claps: {exc}") from exc
        stream.start()
        self.stream = stream
        threading.Thread(target=self._run, name="claps", daemon=True).start()
        return self

    def hear_the_pc(self, on):
        """What the PC plays is listened to only while something's playing (music, a video: siri.media_playing), as
        a sharp sound from the speakers comes from one of those, and it costs 2% of a core."""
        if on and not self.pc.on and not self.stopped.is_set():
            try:
                self.pc.start()
            except Exception as exc:  # no way to hear what the PC plays: a song's drums could count, so said
                if self.pc_failed != str(exc):
                    self.log(f"  claps: can't hear what the PC plays ({exc}), so a sharp sound from it may count")
                self.pc_failed = str(exc)
        elif not on and self.pc.on:
            self.pc.stop()

    def stop(self):
        self.stopped.set()
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        self.pc.stop()

    def _heard(self, indata, frames, time_info, status):
        try:
            self.blocks.put_nowait((time.monotonic() - frames / RATE, indata[:, 0].copy()))
        except queue.Full:
            pass

    def _run(self):
        while not self.stopped.is_set():
            try:
                at, block = self.blocks.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                ok = self.allowed()
                if ok is None:  # typing: a sharp sound started was a key's click
                    self.clapper.drop()
                self.clapper.feed(block, bool(ok), at)
            except Exception as exc:
                self.log(f"  claps: {exc!r}")
