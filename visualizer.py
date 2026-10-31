"""What the music sounds like, as five bars for the island (30 October 2026, the owner's ask, after bloom's notch,
github.com/SehajveerSingh2005/bloom, whose visualizer reacts to five frequency bands): the lows to the highs of what
the PC is playing, each 0 to 1, from what loopback.py hears of it.

It only listens while music plays and the island shows it (island_plugins.Media starts and stops it), and keeps
nothing: each block of sound is looked at and let go. About 30 small FFTs a second, a fraction of a millisecond each."""
import threading

import numpy as np

RATE, SIZE = 16000, 512  # loopback.py's rate, and samples looked at once: 32 ms, 31 Hz apart
# each band's FFT bins at 16 kHz: about 90-190 Hz, 190-560, 560-1.7k, 1.7-5.6k and 5.6-8k, as bloom splits them
BANDS = ((3, 6), (6, 18), (18, 54), (54, 180), (180, 256))
WEIGHT = np.float32([1.2, 1.2, 1.5, 2.8, 5.0])  # the highs are quieter: lifted so each band moves as much
FLOOR, DECAY = 0.12, 0.99  # the loudest each band's been lately, falling back a little every block
RISE, FALL, LEAST = 0.10, 0.20, 0.18  # how much of the last value each block keeps going up and going down


def bands(block, peaks, last):
    """Five levels, 0 to 1, for one SIZE-sample block of sound: each band's loudness over the loudest it's been
    lately (peaks, kept and changed here), eased from last (changed here too). The levels as a list."""
    x = np.asarray(block, np.float32)[:SIZE]
    if len(x) < SIZE:
        x = np.pad(x, (0, SIZE - len(x)))
    spectrum = np.abs(np.fft.rfft(x * np.hanning(SIZE).astype(np.float32)))
    out = []
    for i, (a, b) in enumerate(BANDS):
        mag = float(spectrum[a:b].mean()) * WEIGHT[i]
        peaks[i] = mag if mag > peaks[i] else peaks[i] * DECAY
        target = min(1.0, mag / max(peaks[i], FLOOR)) ** 0.75
        keep = RISE if target > last[i] else FALL
        last[i] = max(LEAST, min(1.0, last[i] * keep + target * (1 - keep)))
        out.append(last[i])
    return out


class Bands:
    """The five bars while it runs: levels, five floats 0 to 1 (all LEAST while quiet), changed on the loopback's own
    thread. start() and stop() as often as wanted: it listens only between them."""

    def __init__(self):
        self.levels = [LEAST] * len(BANDS)
        self.peaks, self.last = [0.01] * len(BANDS), [LEAST] * len(BANDS)
        self.loop, self.lock, self.failed = None, threading.Lock(), False

    @property
    def running(self):
        return self.loop is not None

    def start(self):
        """Listening, if it can: False if the PC's sound can't be heard (it isn't tried again till stop)."""
        with self.lock:
            if self.loop is not None or self.failed:
                return self.loop is not None
            try:
                import loopback
                self.loop = loopback.Loopback(self._block, every=0.03).start()
            except Exception as exc:
                print(f"  visualizer: can't hear the PC ({exc})")
                self.loop, self.failed = None, True
            return self.loop is not None

    def stop(self):
        with self.lock:
            loop, self.loop, self.failed = self.loop, None, False
        if loop is not None:
            loop.stop()
        self.levels = [LEAST] * len(BANDS)

    def _block(self, block):
        self.levels = bands(block, self.peaks, self.last)
