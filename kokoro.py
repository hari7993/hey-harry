"""Her voice on this PC: Kokoro-82M v1.0 (Apache 2.0) through the sherpa-onnx already used for speech-to-text, so no
new package. Free for good and nothing leaves the PC, not even the words. For when Fish's free voice ends (30 November
2026) or is down, or picked in Settings > Voice.

It took Kyutai's Pocket TTS's place on 31 October 2026 (the owner's ask): first for English on the Open TTS
Leaderboard, both for clear words (0.69 WER against Pocket's 0.83) and for sounding natural (UTMOS 4.51 against 4.36).

Measured on this i5-12450H (31 Oct 2026), the full model (the int8 one was three times slower here): 1.3 to 1.9 s to
load, +400 MB while loaded, three times faster than real time on 4 threads. It makes a sentence whole before any of
it can play, 1.2 s for a 57-letter one, so a long sentence is made a clause at a time (pieces): a clause is ready in
about 0.5 s. It loads when first needed and unloads after IDLE seconds unused.

Its voices are its own (it can't copy a recording as Pocket did): American and British English, and Hindi ones that
say English with an Indian voice. A voice is saved by its name, as "kokoro:af_heart".
"""
import os
import queue
import re
import threading
import time

import numpy as np
import psutil

import speech

FOLDER = "kokoro-multi-lang-v1_0"  # github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models, 333 MB (speech.MODELS)
# the ones offered, by their speaker numbers in this model (k2-fsa.github.io/sherpa/onnx/tts/pretrained_models)
VOICES = {"af_heart": 3, "af_bella": 2, "bf_emma": 21, "hf_alpha": 31, "hf_beta": 32, "am_michael": 16,
          "bm_george": 26}
DEFAULT = "af_heart"
RATE = 24000
IDLE = 300.0  # seconds unused before it's let go, giving back its 400 MB
THREADS = 4  # 1.2 s for a sentence against 1.5 s on 2; only while she's talking
CLAUSE = 40  # letters: a sentence longer than this is made a clause at a time


def available(voice=DEFAULT):
    return os.path.isfile(os.path.join(speech.models_dir(), FOLDER, "model.onnx"))


def pieces(text):
    """text in the pieces it's made in: its sentences, and a long one cut after its commas, colons and semicolons,
    no piece shorter than about a dozen letters (a lone "Okay," made alone sounded clipped)."""
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+", " ".join(str(text).split())):
        if len(sentence) <= CLAUSE:
            out.append(sentence)
            continue
        part = ""
        for clause in re.split(r"(?<=[,;:])\s+", sentence):
            part = f"{part} {clause}".strip()
            if len(part) >= 12:
                out.append(part)
                part = ""
        if part:
            if out:
                out[-1] += " " + part
            else:
                out.append(part)
    return [p for p in out if p]


class Engine:
    def __init__(self):
        self.tts, self.used = None, 0.0
        self.lock = threading.Lock()  # one line at a time: sherpa-onnx's TTS isn't for two threads at once
        threading.Thread(target=self._let_go, daemon=True).start()

    def _load(self):
        import sherpa_onnx
        d = speech.model_path("kokoro")
        model = sherpa_onnx.OfflineTtsKokoroModelConfig(
            model=os.path.join(d, "model.onnx"), voices=os.path.join(d, "voices.bin"),
            tokens=os.path.join(d, "tokens.txt"), lexicon=os.path.join(d, "lexicon-us-en.txt"),
            data_dir=os.path.join(d, "espeak-ng-data"))
        config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(kokoro=model, num_threads=THREADS, provider="cpu"),
            max_num_sentences=1)
        self.tts = sherpa_onnx.OfflineTts(config)
        print(f"  her voice on this PC loaded, {psutil.Process().memory_info().rss / 2 ** 20:,.0f} MB in use")

    def make(self, text, voice=DEFAULT, on_audio=None, stop=None):
        """Say text in voice: on_audio(samples, float32 at RATE) gets it a piece at a time. Returns all of it.
        stop(): True to stop making it, as when she's been stopped mid-line. Asked before it starts and before each
        piece, so a line queued behind others isn't made in full after a stop."""
        made = []
        if stop and stop():
            return np.zeros(0, np.float32)
        with self.lock:
            for piece in pieces(text):
                if stop and stop():  # stopped while it waited, or between pieces
                    break
                if self.tts is None:
                    self._load()
                self.used = time.time()
                audio = np.asarray(self.tts.generate(piece, sid=VOICES.get(voice, VOICES[DEFAULT])).samples,
                                   np.float32)
                self.used = time.time()
                made.append(audio)
                if on_audio is not None and not (stop and stop()):
                    on_audio(audio)
        return np.concatenate(made) if made else np.zeros(0, np.float32)

    def _let_go(self):
        while True:
            time.sleep(30)
            with self.lock:
                if self.tts is not None and time.time() - self.used > IDLE:
                    self.tts = None


_engine = []
_engine_lock = threading.Lock()


def engine():
    with _engine_lock:
        if not _engine:
            _engine.append(Engine())
        return _engine[0]


def stream(text, voice=DEFAULT, stop=None):
    """A queue that gets her voice for text a piece at a time (float32 at RATE), then None; an exception instead if
    it failed. Made on its own thread, so it can be under way while another line plays."""
    out = queue.Queue()

    def run():
        try:
            engine().make(text, voice, out.put, stop)
            out.put(None)
        except Exception as exc:
            out.put(exc)
    threading.Thread(target=run, daemon=True).start()
    return out


def to_wav(text, path, voice=DEFAULT):
    import soundfile as sf
    sf.write(path, engine().make(text, voice), RATE, subtype="PCM_16")
