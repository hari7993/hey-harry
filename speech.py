"""Hey Harry's ears, all on the CPU, working in small pieces while you talk:

- Silero VAD hears where speech starts and stops, 32 ms at a time.
- Smart Turn, Pipecat's turn-taking model, decides at each pause whether you've finished: from how you said it,
  tone and pace, the way a person hears it, not just from the quiet. Finished: she answers straight away. Not yet:
  she waits for the rest, so a pause mid-sentence doesn't cut you off.
- Parakeet writes the words once the turn is over, in about 0.2 s.

From the end of a command to its text took 0.88 s here when half a second of quiet was the only sign you'd
finished, and 0.65 s with Smart Turn ending a turn at the first pause. That was too quick for Hari: 931 turns ended
after 0.22 s of quiet, and "Job open settings [pause] and Windows update" came as two. She waits like OpenLive's
"Patient" now (Listener.WAITS): at least 0.7 s of quiet, longer when Smart Turn says you're not done.
Nemotron, NVIDIA's streaming speech-to-text, is in Settings too: it writes the words
as you say them, but in Hari's voice it wrote "Hey Harry" as "Hello", so with it a bare greeting gets the chime
(siri.GREETING_ONLY), and it costs more CPU (see STREAM_THREADS). Whisper small.en too.

Every phrase is turned into text and checked for "Hey Harry". A dedicated wake word model was tried first
(sherpa-onnx's 3.3M keyword spotter): it never caught the "Hey Harry" in this PC's own mic recordings, while
Parakeet wrote them as "Hey Joe" and "Hey Jim".

sherpa-onnx runs the speech models and onnxruntime Smart Turn. The models download once on first use into
HEYHARRY_MODELS (D:\\HeyJev\\models on this PC, set in .env), or %LOCALAPPDATA%\\Hey Harry\\models.
"""
import contextlib
import hashlib
import os
import shutil
import tarfile
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

RATE = 16000
RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
NEMOTRON = "sherpa-onnx-nemotron-speech-streaming-en-0.6b-560ms-int8-2026-04-25"
MODELS = {  # name: (file or folder once downloaded, where it comes from, size for the status line)
    "vad": ("silero_vad.onnx", RELEASES + "silero_vad.onnx", "2 MB"),
    "parakeet": ("sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8",
                 RELEASES + "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8.tar.bz2", "460 MB"),
    "nemotron": (NEMOTRON, RELEASES + NEMOTRON + ".tar.bz2", "460 MB"),  # NVIDIA Open Model License
    "turn": ("smart-turn-v3.2-cpu.onnx", "https://huggingface.co/pipecat-ai/smart-turn-v3/resolve/"
             "f766f81d3cfdf7737ac64aad813d91bbfd56bf93/smart-turn-v3.2-cpu.onnx", "9 MB"),  # BSD 2-clause
    # 3D-Speaker's CAM++ trained on VoxCeleb (English, many accents), Apache 2.0: whose voice it is, see Speaker
    "speaker": ("3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx", "https://github.com/k2-fsa/sherpa-onnx/releases/"
                "download/speaker-recongition-models/3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx", "30 MB"),
    # YuNet, OpenCV Zoo's face finder (MIT): whether you're in front of the laptop's camera, see camera.py
    "face": ("face_detection_yunet_2023mar.onnx", "https://github.com/opencv/opencv_zoo/raw/main/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx", "0.2 MB"),
    # your hand in front of the camera, for a snap seen (hands.py): MediaPipe's palm finder and its 21 points
    "palm": ("palm_detection_mediapipe_2023feb.onnx", "https://github.com/opencv/opencv_zoo/raw/main/models/"
             "palm_detection_mediapipe/palm_detection_mediapipe_2023feb.onnx", "3.9 MB"),
    "hand": ("handpose_estimation_mediapipe_2023feb.onnx", "https://github.com/opencv/opencv_zoo/raw/main/models/"
             "handpose_estimation_mediapipe/handpose_estimation_mediapipe_2023feb.onnx", "4.1 MB"),
}
SHA256 = {"turn": "2bb026316b14a660486a75b1733cd3fbab8c2fd0314dc9af7be49f8cca967e4f",  # from Hugging Face's LFS
          "speaker": "357a834f702b80161e5b981182c038e18553c1f2ca752ed6cec2052365d4129b",  # checked 7 Oct 2026
          "face": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",  # checked 29 Oct 2026
          "palm": "78ff51c38496b7fc8b8ebdb6cc8c1abb02fa6c38427c6848254cdaba57fcce7c",  # and these two
          "hand": "db0898ae717b76b075d9bf563af315b29562e11f8df5027a1ef07b02bef6d81c"}
# Parakeet's threads. 2 till 20 November 2026, when 4 had measured as quick on a bare command (315 against 294 ms).
# It isn't on a sentence, with her running as she does now: the owner said hearing was sometimes slow, and in 1,735
# turns of her log a turn of 8 to 14 words took 0.6 s at the median and over a second a quarter of the time. Timed
# that day on room recordings beside her: 6 s of speech written in 1,129 ms on 2 threads, 883 on 3, 708 on 4 (8 times
# real time against 5) and 1,066 on 6, which is more than its 4 fast cores
PARAKEET_THREADS = 4
# Nemotron while someone talks, fed in real time, and its last words once they stop: 4.5 cores and 174 ms at 3
# threads, 2.3 cores and 222 ms at 2, 0.34 cores and 342 ms at 1. Most of it is sherpa-onnx's own onnxruntime
# keeping its helper threads spinning between pieces, which it has no setting for (Turn turns it off for Smart Turn).
# 1 since 31 October 2026, the owner's pick: measured on battery, her process kept about a core busy with nobody
# talking to her, sherpa-onnx's spinning threads the most of it, for 0.12 s quicker last words
STREAM_THREADS = 1
TURN_THREADS = 4  # Smart Turn: 16 ms at 4 threads, 26 at 2, 55 at 1. It only runs at pauses
BLAS_THREADS = 1  # numpy's own maths (OpenBLAS): see few_maths_threads


def few_maths_threads(most=BLAS_THREADS):
    """numpy's OpenBLAS down to most threads, while she runs: it starts one for every CPU thread, 12 here, and on 31
    October its 11 helpers took 5 to 9% of a core between them, woken for the small sums she does (a sentence's
    meaning, a sound's features) and left spinning after. None of hers is big enough to need more than one. Set
    while running rather than by OPENBLAS_NUM_THREADS, which is read only before numpy is first imported, and her
    window imports it long before this. The number it's now, or None where it couldn't be set."""
    import ctypes
    import glob
    try:
        import numpy
        libs = glob.glob(os.path.join(os.path.dirname(os.path.dirname(numpy.__file__)), "numpy.libs", "*openblas*"))
        lib = ctypes.CDLL(libs[0])
        lib.scipy_openblas_set_num_threads64_(int(most))
        return lib.scipy_openblas_get_num_threads64_()
    except Exception as exc:  # another numpy build: it keeps its own threads, as before
        print(f"  couldn't set numpy's threads: {exc!r}")
        return None
# Nemotron gives the same words about 0.08 less than Parakeet: 0.88 against 0.97 for clear speech, 0.67 against
# 0.75 for Telugu and Hindi said by Windows' English voices. Moved up by that, so siri.py's 55% and 70% lines, worked
# out on Parakeet with 62 clips from this room, mean the same
SURE_SHIFT = 0.08


class Heard(str):
    """What speech-to-text wrote, and in .sure how sure it was: the average chance it gave its own words, 0 to 1.
    On 62 clips from this PC's room, clear speech came out above 0.9, "Hey Joe" said to her about 0.75, and
    mumbling, Telugu and talk across the room 0.4 to 0.6."""
    sure = 1.0
    owner = None  # how like your voice it was, -1 to 1 (voiceid.Profile.score), None if it wasn't scored
    spoke = 0.0  # seconds of speech in it, without the quiet
    voice = None  # its voice print, to add to her picture of yours when it was plainly you
    audio = None  # the turn's audio, so a provider's ears can hear it again once it's hers (hearing.py)
    asked = None  # a dictated phrase's hearing.Asked: the provider's words for it, put in before it's pasted


def heard(text, sure=1.0):
    h = Heard(text)
    h.sure = sure
    return h


def _env_file(name):
    """One value from .env, read without loading the rest of it into this process."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), encoding="utf-8") as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                if key.strip() == name and not line.lstrip().startswith("#"):
                    return value.strip().strip("\"'") or None
    except OSError:
        pass
    return None


def models_dir():
    """Where the models live. HEYHARRY_MODELS is also read from .env here, for a script that imports this without
    loading .env: one put a second 1.2 GB copy of the models on C: on 9 October, with C: nearly full. Not under the
    tests (HEYHARRY_TESTING), which must never find the real models."""
    from winplatform import home
    for name in ("HEYHARRY_MODELS", "HEYJEV_MODELS"):  # and Hey Jev's name for it, in a .env from before 28 October
        found = os.getenv(name) or (None if os.getenv("HEYHARRY_TESTING") else _env_file(name))
        if found:
            return found
    return os.path.join(home("LOCALAPPDATA"), "models")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def model_path(name, notify=None):
    """Where a model lives, downloading it the first time. A half-finished download never counts as done."""
    local, url, size = MODELS[name]
    folder = models_dir()
    path = os.path.join(folder, local)
    if os.path.exists(path):
        return path
    os.makedirs(folder, exist_ok=True)
    download = os.path.join(folder, os.path.basename(url))
    if not os.path.exists(download):
        if notify:
            notify(f"Downloading the {name} model ({size}), one time\u2026")
        urllib.request.urlretrieve(url, download + ".part")
        if name in SHA256 and _sha256(download + ".part") != SHA256[name]:
            os.remove(download + ".part")
            raise RuntimeError(f"The {name} model didn't download right, it'll try again next time")
        os.replace(download + ".part", download)  # only a finished download gets the real name
    if download == path:
        return path
    staging = path + ".unpacking"
    shutil.rmtree(staging, ignore_errors=True)
    with tarfile.open(download) as tar:
        tar.extractall(staging, filter="data")  # "data" refuses paths that would land outside the folder
    os.replace(os.path.join(staging, local), path)
    shutil.rmtree(staging, ignore_errors=True)
    os.remove(download)
    return path


PAUSE = 0.2  # seconds of quiet that make a pause, where Smart Turn is asked whether you've finished


class Voice:
    """Silero VAD (v4, as sherpa-onnx ships it), run directly: the chance of speech in each 32 ms. Not through
    sherpa-onnx's detector, which waits a quarter of a second to be sure speech has started: in the middle of a turn
    that made a pause look longer than it was, and "Hey Harry, [a breath] open Notepad" came out as two."""
    WINDOW = 512

    def __init__(self, notify=None):
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.inter_op_num_threads = so.intra_op_num_threads = 1  # a tiny model, a fraction of a millisecond a window
        self.session = ort.InferenceSession(model_path("vad", notify), sess_options=so,
                                            providers=["CPUExecutionProvider"])
        self.reset()

    def reset(self):
        self.h, self.c = np.zeros((2, 1, 64), np.float32), np.zeros((2, 1, 64), np.float32)
        self.left = np.zeros(0, np.float32)

    def __call__(self, audio):
        """The chance of speech in each whole window of the audio, in order. What's over waits for the next call."""
        x = np.concatenate([self.left, np.asarray(audio, dtype=np.float32)])
        n, out = len(x) // self.WINDOW * self.WINDOW, []
        for i in range(0, n, self.WINDOW):
            p, self.h, self.c = self.session.run(None, {"x": x[None, i:i + self.WINDOW], "h": self.h, "c": self.c})
            out.append(float(p.reshape(-1)[0]))
        self.left = x[n:]
        return out


def end_of_speech(notify=None):
    """The voice detector Listener uses: Silero, 32 ms at a time."""
    return Voice(notify)


# Parakeet's weights mapped from disk (20 November 2026, the owner: she took 1,000 to 2,000 MB). Its encoder is 652
# MB, and ONNX Runtime copied all of it into her memory, then packed the weights it multiplies by into a second form
# and let the first go: 694 MB of her own for as long as she ran. ONNX Runtime can save a model with its weights, and
# those packed ones, in a file beside it (session.save_external_prepacked_constant_initializers), and maps that file
# when it loads it rather than copying it: the pages are Windows' file cache, shared, and dropped and read again
# with no page file. Measured here with sherpa-onnx loading it: 62 MB of her own after loading against 694, loaded in
# 3.5 s against 4.6, the same words and the same sureness to four places on 22 recordings from this room, and the
# same time to hear one (1,104 ms a clip against 1,110). Made once, 14 s and 1.1 GB beside the model
MAPPED = "mapped"  # the folder in Parakeet's, with encoder.onnx, its encoder.onnx.data and made.json
MAPPED_ROOM = 2 ** 30  # bytes free on the models' drive, over three times the model's size, before one's made


def _mapped_stamp(source, threads):
    """What a mapped model was made from and for: remade when the model, ONNX Runtime or the processor changes
    (ONNX Runtime says the saved model is for the PC it was made on)."""
    import platform

    import onnxruntime as ort
    return {"size": os.path.getsize(source), "mtime": int(os.path.getmtime(source)), "onnxruntime": ort.__version__,
            "cpu": platform.processor(), "threads": threads}


def mapped_model(source, folder, name="model.onnx", threads=1, notify=None, what="a model"):
    """folder, holding the ONNX model source saved as `name` with its weights in a file of their own beside it, to
    be mapped (see MAPPED), made the first time; None if it can't be (no room, or ONNX Runtime wouldn't), and the
    model is loaded the old way. ONNX Runtime given folder\\name by its path maps the weights itself; sherpa-onnx
    hands it the model as bytes, and then she must be in the folder as it loads (in_folder)."""
    import json
    made = os.path.join(folder, "made.json")
    if os.getenv("HEYHARRY_UNMAPPED"):
        return None
    try:
        stamp = _mapped_stamp(source, threads)
        with contextlib.suppress(OSError, ValueError):
            with open(made, encoding="utf-8") as f:
                if json.load(f) == stamp and os.path.getsize(os.path.join(folder, name + ".data")) > 2 ** 10:
                    return folder
        if shutil.disk_usage(os.path.dirname(source)).free < 3 * stamp["size"] + MAPPED_ROOM:
            print(f"  no room to map {what}'s weights from disk, loading them into memory")
            return None
        import onnxruntime as ort
        if notify:
            notify(f"Getting {what} ready, one time\u2026")
        t = time.time()
        shutil.rmtree(folder, ignore_errors=True)
        os.makedirs(folder)
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.log_severity_level = 3  # it warns that the model's for this PC only, which is what's wanted
        so.optimized_model_filepath = os.path.join(folder, name)
        so.add_session_config_entry("session.optimized_model_external_initializers_file_name", name + ".data")
        so.add_session_config_entry("session.optimized_model_external_initializers_min_size_in_bytes", "1024")
        so.add_session_config_entry("session.save_external_prepacked_constant_initializers", "1")
        ort.InferenceSession(source, so, providers=["CPUExecutionProvider"])  # saved as it's made, then let go
        with open(made, "w", encoding="utf-8") as f:
            json.dump(stamp, f)
        print(f"  {what}'s weights put in a file to map, {time.time() - t:.0f} s, "
              f"{os.path.getsize(os.path.join(folder, name + '.data')) / 2 ** 20:,.0f} MB")
        return folder
    except Exception as exc:
        print(f"  couldn't put {what}'s weights in a file to map ({exc!r}), loading them into memory")
        shutil.rmtree(folder, ignore_errors=True)
        return None


def mapped_encoder(d, notify=None):
    """The folder holding Parakeet's encoder to be mapped (mapped_model), made the first time from d's
    encoder.int8.onnx; None if it can't be, and the encoder is loaded the old way."""
    return mapped_model(os.path.join(d, "encoder.int8.onnx"), os.path.join(d, MAPPED), "encoder.onnx",
                        PARAKEET_THREADS, notify, "Parakeet")


@contextlib.contextmanager
def in_folder(folder):
    """She's in folder while a mapped model loads through sherpa-onnx, and back after: sherpa-onnx hands ONNX Runtime
    the model as bytes, which then looks for the weights' file in the folder the process is in."""
    was = os.getcwd()
    os.chdir(folder)
    try:
        yield
    finally:
        os.chdir(was)


def unmade(folder, what, exc):
    """A mapped model that wouldn't load (a file cut short, or an ONNX Runtime that reads it another way): said, and
    made again next time."""
    print(f"  couldn't load {what}'s mapped weights ({exc!r}), loading them into memory")
    with contextlib.suppress(OSError):
        os.remove(os.path.join(folder, "made.json"))


def _parakeet(d, notify=None):
    """sherpa-onnx's recognizer for Parakeet in folder d: its encoder mapped from disk where that's been made
    (mapped_encoder), else loaded into memory as before. She's in the mapped folder while it loads (in_folder), 3 to
    4 s, and back after."""
    import sherpa_onnx

    def load(encoder):
        return sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=encoder, decoder=os.path.join(d, "decoder.int8.onnx"),
            joiner=os.path.join(d, "joiner.int8.onnx"), tokens=os.path.join(d, "tokens.txt"),
            num_threads=PARAKEET_THREADS, model_type="nemo_transducer")
    folder = mapped_encoder(d, notify)
    if folder:
        try:
            with in_folder(folder):
                return load(os.path.join(folder, "encoder.onnx"))
        except Exception as exc:
            unmade(folder, "Parakeet", exc)
    return load(os.path.join(d, "encoder.int8.onnx"))


# A long turn heard in pieces (20 November 2026). ONNX Runtime keeps the working memory of the longest audio it has
# ever been given, for good, and takes it in doubling steps: measured here, 138 MB of her own after a 3 s command,
# 239 after 10 s, 638 after 30 s and 1,167 after 45 s of room talk heard as one turn, which is most of the 1,000 to
# 2,000 MB the owner saw. So Parakeet is never given more than PIECE_MOST seconds at once: a longer turn is cut where
# it's quietest between PIECE_LEAST and PIECE_MOST seconds in, a pause between words, and its pieces' words joined
PIECE_MOST, PIECE_LEAST = 8.0, 5.0  # seconds: 158 MB of her own after 6 s, 190 after 10


def in_pieces(audio, most=PIECE_MOST, least=PIECE_LEAST):
    """audio (16 kHz) as pieces of at most `most` seconds, in order: whole if it's that short, else cut at the
    quietest fifth of a second between `least` and `most` seconds into what's left, never leaving a last piece
    under a second."""
    audio = np.asarray(audio, dtype=np.float32)
    n_most, n_least, hop = int(most * RATE), int(least * RATE), RATE // 50  # 20 ms
    out = []
    while len(audio) > n_most:
        end = max(n_least + hop * 10, min(n_most, len(audio) - RATE))
        window = audio[n_least:end]
        frames = len(window) // hop
        loud = (window[:frames * hop].reshape(frames, hop) ** 2).mean(axis=1)
        quiet = np.convolve(loud, np.ones(10, np.float32) / 10, mode="valid")  # over 0.2 s: a pause, not one sample
        cut = n_least + (int(np.argmin(quiet)) + 5) * hop
        out.append(audio[:cut])
        audio = audio[cut:]
    out.append(audio)
    return out


def transcriber(engine="parakeet", notify=None):
    """A function from 16 kHz audio to (text, ms), for Parakeet or Whisper small.en, which hear a phrase whole."""
    if engine == "whisper":
        from faster_whisper import WhisperModel
        if notify:
            notify("Loading Whisper\u2026")
        model = WhisperModel("small.en", device="cpu", compute_type="int8")

        def run(audio):
            segs, _ = model.transcribe(audio, language="en", beam_size=1, temperature=0, without_timestamps=True,
                                       condition_on_previous_text=False)
            segs = list(segs)
            sure = float(np.exp(np.mean([s.avg_logprob for s in segs]))) if segs else 1.0
            return " ".join(s.text.strip() for s in segs), sure
    else:
        d = model_path("parakeet", notify)
        if notify:
            notify("Loading Parakeet\u2026")
        rec = _parakeet(d, notify)

        def run(audio):
            words, logs = [], []
            for piece in in_pieces(audio):  # a long turn a piece at a time, for her memory (PIECE_MOST)
                s = rec.create_stream()
                s.accept_waveform(RATE, piece)
                rec.decode_stream(s)
                words.append(s.result.text.strip())
                logs.extend(getattr(s.result, "ys_log_probs", None) or [])
            probs = np.exp(np.asarray(logs or [0.0], dtype=np.float32))
            return " ".join(w for w in words if w), float(probs.mean())

    lock = threading.Lock()  # push to talk and the open mic can both want it at once

    def transcribe(audio):
        """(text, ms). text is a Heard, a str that also says how sure it is."""
        with lock:
            t = time.time()
            text, sure = run(audio)
        return heard(text.strip(), sure), int((time.time() - t) * 1000)
    if engine != "whisper":
        # the first thing it hears is the slow one, more so with its weights mapped (they're read from disk as they're
        # first used: 4.3 s for the first clip against 1.1 after, 20 November 2026): so it hears 3 s of nothing now, on
        # a thread of its own, and a turn that comes meanwhile waits its turn at the lock
        threading.Thread(target=lambda: transcribe(np.random.default_rng(0).normal(0, 1e-3, 3 * RATE).astype(
            np.float32)), name="parakeet-warm", daemon=True).start()
    return transcribe


class Whole:
    """One turn for Parakeet or Whisper, which hear a phrase whole: the words come once it's over."""
    live = False

    def __init__(self, transcribe):
        self.transcribe, self.parts = transcribe, []

    def feed(self, audio):
        self.parts.append(np.asarray(audio, dtype=np.float32))

    def text(self):
        return ""

    def audio(self, quiet=0.0):
        """The turn's audio so far. quiet: seconds of quiet at its end, left out but for the last 0.3, counted in
        samples: so a turn written at its pause (Listener.AHEAD) is given the very audio it would be at its end."""
        audio = np.concatenate(self.parts) if self.parts else np.zeros(0, np.float32)
        return audio[:max(0, len(audio) - max(0, int(round(quiet * RATE)) - int(0.3 * RATE)))]

    def finish(self, quiet=0.0):
        """(Heard, ms). quiet: seconds of quiet at the end, left out but for the last 0.3."""
        return self.transcribe(self.audio(quiet))


class Live:
    """One turn for Nemotron: audio goes in as it comes, in pieces of any size, and the words build up while you
    talk, a 0.56 s piece at a time."""
    live = True
    CHUNK, READS = 0.56, 0.65  # seconds the model moves on each time, and reads each time (its metadata: 56, 65 frames)

    def __init__(self, ears):
        self.ears, self.fed = ears, 0
        with ears.lock:
            self.s = ears.rec.create_stream()

    def feed(self, audio):
        with self.ears.lock:
            self.s.accept_waveform(RATE, np.asarray(audio, dtype=np.float32))
            self.fed += len(audio)
            while self.ears.rec.is_ready(self.s):
                self.ears.rec.decode_stream(self.s)

    def text(self):
        """The words so far. The last half second or so is still to come."""
        with self.ears.lock:
            return self.ears.rec.get_result(self.s).strip()

    def finish(self, quiet=0.2):
        """(Heard, ms) once the last words are through. quiet: seconds since the speech stopped. The model often
        writes a word a piece after it hears it, and a piece only goes through once it's whole, so it gets quiet up
        to the end of the piece after the one the speech ended in. With less, "Hey Harry" came out as "H"."""
        t = time.time()
        fed = self.fed / RATE
        need = (int((fed - quiet) / self.CHUNK) + 1) * self.CHUNK + self.READS + 0.03
        with self.ears.lock:
            self.s.accept_waveform(RATE, np.zeros(int(max(0.0, need - fed) * RATE), np.float32))
            self.s.input_finished()
            while self.ears.rec.is_ready(self.s):
                self.ears.rec.decode_stream(self.s)
            r = self.ears.rec.get_result_all(self.s)
        logs = list(r.ys_probs)
        sure = min(1.0, float(np.exp(np.asarray(logs, dtype=np.float64)).mean()) + SURE_SHIFT) if logs else 1.0
        return heard(r.text.strip(), sure), int((time.time() - t) * 1000)


class Ears:
    """Speech-to-text for the open mic and right Alt: session() for one turn, fed as the audio comes, and
    transcribe(audio) for a whole one. engine: parakeet or whisper (once you stop), or nemotron (writes as you
    talk)."""

    def __init__(self, engine="parakeet", notify=None):
        self.engine = engine
        self.live = engine == "nemotron"
        few_maths_threads()  # once, as her ears start: numpy's maths on one thread from here (few_maths_threads)
        if not self.live:
            self._whole = transcriber(engine, notify)
            return
        import sherpa_onnx
        d = model_path("nemotron", notify)
        if notify:
            notify("Loading Nemotron\u2026")
        # blank_penalty 1: without it the last word went missing now and then ("who directed Iron Man [two]")
        self.rec = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=os.path.join(d, "tokens.txt"), encoder=os.path.join(d, "encoder.int8.onnx"),
            decoder=os.path.join(d, "decoder.int8.onnx"), joiner=os.path.join(d, "joiner.int8.onnx"),
            num_threads=STREAM_THREADS, sample_rate=RATE, feature_dim=128, enable_endpoint_detection=False,
            decoding_method="greedy_search", blank_penalty=1.0)
        self.lock = threading.Lock()  # push to talk and the open mic can both want it at once
        warm = Live(self)  # the first decode is the slow one, better now than on the first command
        warm.feed(np.zeros(RATE, np.float32))
        warm.finish()

    def session(self):
        return Live(self) if self.live else Whole(self._whole)

    def transcribe(self, audio):
        """(Heard, ms) for audio you already have, all of it."""
        s = self.session()
        s.feed(audio)
        return s.finish()


# --------------------------------------------------------------------------- Smart Turn: have you finished?
def _mel_filters(n_fft=400, n_mels=80):
    """Whisper's 80 mel bands (Slaney), the same numbers as librosa and faster-whisper."""
    fftfreqs = np.fft.rfftfreq(n=n_fft, d=1.0 / RATE)
    mels = np.linspace(0.0, 45.245640471924965, n_mels + 2)
    freqs = 200.0 / 3 * mels
    log = mels >= 15.0
    freqs[log] = 1000.0 * np.exp(np.log(6.4) / 27.0 * (mels[log] - 15.0))
    ramps = freqs[:, None] - fftfreqs[None, :]
    fdiff = np.diff(freqs)
    weights = np.maximum(0, np.minimum(-ramps[:-2] / fdiff[:-1, None], ramps[2:] / fdiff[1:, None]))
    return weights * (2.0 / (freqs[2:n_mels + 2] - freqs[:n_mels]))[:, None]


_MEL, _WINDOW = _mel_filters(), np.hanning(401)[:-1]


def _features(audio):
    """What Smart Turn reads: the last 8 s, quiet in front if it's shorter, evened out, as Whisper's log-mel
    spectrogram. Matches transformers' WhisperFeatureExtractor(chunk_length=8) to within 1e-5."""
    x = np.asarray(audio, dtype=np.float64)[-8 * RATE:]
    x = np.pad(x, (8 * RATE - len(x), 0))
    x = (x - x.mean()) / np.sqrt(x.var() + 1e-7)
    frames = np.lib.stride_tricks.sliding_window_view(np.pad(x, 200, mode="reflect"), 400)[::160]
    spec = np.abs(np.fft.rfft(frames * _WINDOW, axis=-1)) ** 2
    log = np.log10(np.maximum(_MEL @ spec[:-1].T, 1e-10))
    log = np.maximum(log, log.max() - 8.0)
    return ((log + 4.0) / 4.0).astype(np.float32)[None]


class Turn:
    """Smart Turn v3.2 (Pipecat, BSD 2-clause): has the speaker finished their turn? A Whisper Tiny encoder that
    hears the sound itself, so the pitch falling at the end of a sentence counts, or staying up mid-thought, the
    way a person hears it. 8 MB, 94% right on English in Pipecat's tests, about 20 ms here."""

    def __init__(self, notify=None):
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.inter_op_num_threads, so.intra_op_num_threads = 1, TURN_THREADS
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        # its helper threads sleep between runs: by default onnxruntime keeps them spinning, burning CPU for nothing
        so.add_session_config_entry("session.intra_op.allow_spinning", "0")
        # and what a run needs is given back after it, not kept in onnxruntime's own pool: 17 MB less off Windows
        so.enable_cpu_mem_arena = False
        self.session = ort.InferenceSession(model_path("turn", notify), sess_options=so,
                                            providers=["CPUExecutionProvider"])
        self.finished(np.zeros(RATE, np.float32))  # the first run is the slow one

    def finished(self, audio):
        """The chance, 0 to 1, that they're done, from all of what they've said this turn and the pause after it."""
        return float(self.session.run(None, {"input_features": _features(audio)})[0].reshape(-1)[0])


class Speaker:
    """Whose voice it is: a voice print of the speech in a turn, 512 numbers, from 3D-Speaker's CAM++ (sherpa-onnx's
    SpeakerEmbeddingExtractor, as in its speaker-identification-with-vad.py example), compared in voiceid.py. The
    quiet is taken out first with Silero: with it left in, Windows' voices matched Hari's clips as well as his own did.
    About 20 to 50 ms for 1 to 4 s of speech here, on one thread, while speech-to-text finishes."""

    PRINT_MOST = 8.0  # seconds of speech a voice print is made from: 1 to 4 s is a command's

    def __init__(self, notify=None):
        import sherpa_onnx
        source = model_path("speaker", notify)

        def load(model):
            return sherpa_onnx.SpeakerEmbeddingExtractor(
                sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=model, num_threads=1))
        # its weights mapped from disk, as Parakeet's are (mapped_model): 41 MB of her own for 72, the same print
        folder = mapped_model(source, source + ".mapped", threads=1, what="voice ID")
        self.extractor = None
        if folder:
            try:
                with in_folder(folder):
                    self.extractor = load(os.path.join(folder, "model.onnx"))
            except Exception as exc:
                unmade(folder, "voice ID", exc)
        self.extractor = self.extractor or load(source)
        self.vad = Voice(notify)
        self.lock = threading.Lock()

    def speech(self, audio):
        """Only the speech in the audio, each bit of it with 64 ms either side."""
        with self.lock:
            self.vad.reset()
            chances = np.array(self.vad(audio))
        keep = np.flatnonzero(np.convolve(chances >= Listener.ON, np.ones(5), "same") > 0)
        w = Voice.WINDOW
        return np.concatenate([audio[i * w:(i + 1) * w] for i in keep]) if len(keep) else np.zeros(0, np.float32)

    def print(self, audio):
        """(voice print or None, seconds of speech)."""
        audio = self.speech(np.asarray(audio, dtype=np.float32))
        secs = len(audio) / RATE
        if secs < 0.3:
            return None, secs
        stream = self.extractor.create_stream()
        # the first PRINT_MOST seconds of speech are whose voice it is: ONNX Runtime keeps the working memory of the
        # longest it's been given (see PIECE_MOST), 166 MB after 59 s of speech and 1.5 s to make (20 November 2026)
        stream.accept_waveform(RATE, audio[:int(self.PRINT_MOST * RATE)])
        stream.input_finished()
        if not self.extractor.is_ready(stream):
            return None, secs
        v = np.array(self.extractor.compute(stream), np.float32)
        return v / (np.linalg.norm(v) or 1.0), secs


class Listener:
    """Mic audio in, 32 ms at a time, turns out, as on_phrase(audio, kind, text, ms). kind is one of:

    "dictation"  every turn while dictating
    "armed"      a turn that starts soon after a bare "Hey Harry" (see arm)
    "follow_up"  a turn that starts in the few seconds after she answered, no name needed
    "other"      anything else, which only counts if it has "Hey Harry" in it
    A turn is everything someone says until they've finished: speech-to-text is fed as it comes (ears), and at
    each pause Smart Turn (turn) says whether that was the end. on_words(text, kind) gets the words so far while
    they talk, when the ears write as you go. ms: how long the words took after the pause.
    Time is counted in samples, not on the clock, so a test can feed it faster than real time.
    """

    ON, OFF = 0.5, 0.35  # Silero's chance of speech: a turn starts above ON, and in one, only under OFF is quiet
    START = 2  # windows in a row over ON that start a turn, 64 ms, so a click doesn't
    PRE_ROLL = 0.4  # seconds put back before the speech that started a turn, for a soft start like the H of "Hey"
    KEEP = 45 * RATE  # audio kept, enough for the longest turn and its pre-roll
    MAX_TURN = 15.0  # seconds: a turn this long ends anyway, so a video that never stops still gets checked
    # A turn that's for her (after her name, in a follow-up window, or with her name in the words) may run longer: a
    # long instruction cut at 15 s came back as two turns, and the second, without her name, was ignored
    MAX_TURN_HERS = 40.0
    SHORT = 1.0  # a turn with less speech than this, like a bare "Hey Harry" before the rest, never ends at the first pause
    # How long she waits for you to finish, Settings > Wait before answering, from OpenLive's turn presets
    # (katipally/openlive, apps/web/src/lib/live/pipelineConfig.ts): QUIET, the quiet she always waits; FINISHED,
    # Smart Turn's chance that you're done for her to go then; MAYBE, the chance she goes on after SETTLE seconds of
    # quiet (or none, for a short turn); LONGEST, the most she waits when it says you're not done. "quick" is how it
    # was until 25 October: a turn ended at the first pause, 0.22 s, whenever Smart Turn was over 50% sure, and 90%
    # of 1,459 turns were. "Job open settings [pause] and Windows update" came as two, the second let go
    WAITS = {"patient": {"QUIET": 0.7, "FINISHED": 0.65, "MAYBE": 0.3, "SETTLE": 1.0, "LONGEST": 2.5},
             "even": {"QUIET": 0.5, "FINISHED": 0.5, "MAYBE": 0.2, "SETTLE": 0.8, "LONGEST": 2.0},
             "quick": {"QUIET": 0.0, "FINISHED": 0.5, "MAYBE": 0.15, "SETTLE": 0.5, "LONGEST": 1.2}}
    WAIT = "patient"  # Hari: "a little delay is fine"
    QUIET, FINISHED, MAYBE, SETTLE, LONGEST = WAITS[WAIT].values()  # each wait has them in this order
    # Written ahead (20 November 2026, the owner: hearing is sometimes slow). Parakeet and Whisper write a turn whole,
    # and wrote it once the turn had ended: 0.7 s of quiet waited through with nothing done, then the writing, 0.2 to
    # 1.5 s more by the turn's length. Now it's written on a thread of its own once the pause is AHEAD seconds old,
    # from the audio it would be given at the end (Whole.audio keeps 0.3 s of the quiet, so not before that), and if
    # nothing more is said the turn ends with its words there or nearly: the same words, about 0.4 s sooner. Said on
    # and it's thrown away and written again at the next pause. When Smart Turn thinks they haven't finished, which
    # is when they most often go on, it isn't started till SETTLE, so little is written for nothing
    AHEAD = 0.3
    # All but certain (20 November 2026, the owner: "I need stupid fast"). When Smart Turn is SURE you've finished,
    # the turn ends after SOON seconds of quiet rather than QUIET: 0.3 s sooner. In her log 485 of the 819 turns it
    # was asked about were at 95% or over. On the 22 room recordings kept that day, with 31 pauses inside their
    # turns, not one pause of 0.4 to 0.7 s that someone went on after was at 95%; at 90% one was (0.54 s, 94%), so
    # it's 95. Under that it waits as before, which is what keeps "open settings [pause] and Windows update" whole
    SURE, SOON = 0.95, 0.4

    def __init__(self, vad, ears, on_phrase, on_speech=lambda: None, turn=None, on_words=None, hold_for=None,
                 is_hers=None, speaker=None, wait=None):
        """hold_for(words so far): True to wait the longest before ending, for words that are only the start.
        is_hers(words so far): True if her name is in them, so a long turn isn't cut at MAX_TURN.
        speaker(audio): (voice print or None, seconds of speech), worked out while speech-to-text finishes and put on
        the text as .voice and .spoke (Speaker.print), for voiceid. wait: one of WAITS, how long she waits for you to
        finish; WAIT if it's not one."""
        for name, value in self.WAITS.get(wait, self.WAITS[self.WAIT]).items():
            setattr(self, name, value)
        self.vad, self.ears, self.on_phrase, self.on_speech, self.turn = vad, ears, on_phrase, on_speech, turn
        self.on_words = on_words or (lambda text, kind: None)
        self.hold_for = hold_for or (lambda words: False)
        self.is_hers = is_hers or (lambda words: False)
        self.speaker = speaker
        self.prints = ThreadPoolExecutor(1) if speaker else None
        self.writers = ThreadPoolExecutor(1, thread_name_prefix="written-ahead")  # see AHEAD
        self.dictating = False
        self.reset()

    def reset(self, window=0.0):
        """Start over after a gap in the audio. window: seconds in which a turn counts without the name."""
        self.vad.reset()
        self.pos, self.armed, self.talking, self.run = 0, False, False, 0
        self.window_end = int(window * RATE)
        self.recent, self.recent_start = [], 0  # the last few seconds of blocks, and where the first one starts
        self.speech_start = None  # where the speech going on now began, while someone is talking
        self.session = None  # speech-to-text for the turn going on now
        self.turn_start = self.onset = self.voice = 0  # where the turn's audio starts, its speech, and the last of it
        self.cut = 0  # where the last turn cut at MAX_TURN ended, so the next one doesn't hear any of it again
        self.chance, self.turn_ms, self.words = None, 0, ""
        self.early = None  # (words, ms) of a short turn Parakeet or Whisper wrote at its pause, see feed
        self.ahead = None  # the turn's words being written at its pause, a future of (words, ms): see AHEAD
        self.ended = (None, 0.0)

    def arm(self, secs):
        """After a bare "Hey Harry": the next phrase is the command, if it starts within secs."""
        self.armed, self.window_end = True, self.pos + int(secs * RATE)

    def open(self, secs):
        """A turn that starts within secs counts without the name, as a follow_up: she decides if it was for her."""
        self.armed, self.window_end = False, self.pos + int(secs * RATE)

    def end(self):
        """The audio stops here, as when she starts talking: a turn waiting in a pause ends now, as if finished,
        rather than being lost when the listener starts over. One cut off while still talking is let go."""
        if self.session is not None and not self.talking:
            self._end()

    def talking_for(self):
        """Seconds the speech going on now has lasted, 0 when nobody is talking."""
        return (self.pos - self.speech_start) / RATE if self.speech_start is not None else 0.0

    def _audio(self, start):
        recent = np.concatenate(self.recent) if self.recent else np.zeros(0, np.float32)
        return recent[max(0, start - self.recent_start):]

    def partial(self, secs=2.5):
        """The start of the turn going on now, up to secs of it, so it can be checked for her name early."""
        if self.session is None:
            return np.zeros(0, dtype=np.float32)
        return self._audio(self.turn_start)[:int(secs * RATE)]

    def state(self):
        """"armed" or "window" while a phrase counts without the name, else None. A turn that began in time keeps it
        until it's over: the popup closed while Hari was still talking, when the window ran out mid-sentence."""
        if (self.onset if self.session is not None else self.pos) >= self.window_end:
            return None
        return "armed" if self.armed else "window"

    def _hers(self):
        """True if the turn going on now is plainly for her, so it's let run to the end of what you're saying."""
        return self.dictating or self._kind() in ("armed", "follow_up") or self.is_hers(self.words)

    def _kind(self):
        if self.dictating:
            return "dictation"
        if self.onset < self.window_end:
            return "armed" if self.armed else "follow_up"
        return "other"

    def _end(self):
        audio, kind, session, early = self._audio(self.turn_start), self._kind(), self.session, self.early
        quiet = (self.pos - self.voice) / RATE
        self.session, self.words, self.talking, self.early = None, "", False, None
        self.ended = (self.chance, quiet)  # why it ended, for the log: Smart Turn's chance and the quiet
        whose = self.prints.submit(self.speaker, audio) if self.prints and kind != "dictation" else None
        text, ms = early or self._written(session, quiet)
        if whose is not None:
            text = text if isinstance(text, Heard) else heard(text)
            try:
                text.voice, text.spoke = whose.result()
            except Exception as exc:
                print(f"  voice print failed: {exc!r}")
        self.on_phrase(audio, kind, text, ms + self.turn_ms)

    def _ahead_due(self, quiet):
        """True once the pause is old enough for the turn's words to be written ahead: AHEAD seconds when Smart Turn
        thinks they may have finished, or wasn't asked; SETTLE when it thinks they haven't."""
        likely = self.chance is None or self.chance >= self.MAYBE
        return quiet >= (self.AHEAD if likely else max(self.AHEAD, self.SETTLE))

    def _whole_sentence(self):
        """True if the turn's words are written ahead and end as a sentence does: "Turn the volume up." For a turn
        too short to ask Smart Turn about (SHORT), which waited SETTLE, a second, for want of anything to go on:
        Parakeet's full stop is something, and such a turn ends after QUIET like one Smart Turn calls finished. A
        quarter of the turns in her log were these (20 November 2026, the owner: "I need stupid fast")."""
        ahead = self.ahead
        if ahead is None or not ahead.done() or ahead.exception() is not None:
            return False
        return str(ahead.result()[0]).rstrip().endswith((".", "!", "?"))

    def _written(self, session, quiet):
        """(words, ms) of the turn: what was written ahead at its pause, waited for if it's still being written, else
        written now. ms: how long they took from here, which is what you wait."""
        ahead, self.ahead = self.ahead, None
        if ahead is not None:
            t = time.time()
            try:
                return ahead.result()[0], int((time.time() - t) * 1000)
            except Exception as exc:
                print(f"  writing ahead failed ({exc!r}), written now")
        return session.finish(quiet)

    def feed(self, block, dictating=False):
        if dictating != self.dictating:
            self.dictating = dictating
            self.reset()
        self.pos += len(block)
        self.recent.append(block)
        while self.pos - self.recent_start - len(self.recent[0]) >= self.KEEP:
            self.recent_start += len(self.recent.pop(0))
        for p in self.vad(block):  # one window a block, from the mic
            self.run = self.run + 1 if p >= self.ON else 0
            if p >= self.ON or (self.session is not None and p >= self.OFF):
                self.voice = self.pos
        if self.session is None:
            if self.run < self.START:
                return
            # a turn begins, with what came just before it
            self.onset = self.pos - self.run * Voice.WINDOW
            self.turn_start = max(self.recent_start, self.cut, self.onset - int(self.PRE_ROLL * RATE))
            self.session, self.chance, self.turn_ms = self.ears.session(), None, 0
            # Nemotron needs a moment of quiet before the speech, or fast speech loses its first word: "Open
            # Notepad" came out as "Notepad", "When will Gemini..." as "Will Gemini...", 4 of 9 sentences said
            # quickly. Talking the instant she stops leaves no audio before it, so quiet is made up to fill
            short = int(self.PRE_ROLL * RATE) - (self.onset - self.turn_start)
            if self.session.live and short > 0:
                self.session.feed(np.zeros(short, np.float32))
            self.session.feed(self._audio(self.turn_start))
            self.on_speech()
        else:
            self.session.feed(block)  # pauses too, so the words keep their timing
        quiet = (self.pos - self.voice) / RATE  # seconds since the last speech
        talking, was = quiet < PAUSE, self.talking
        self.talking = talking
        if talking:
            if not was:
                self.speech_start = self.pos - len(block)
            # still talking, so what Smart Turn said or was written no longer counts
            self.chance = self.early = self.ahead = None
        else:
            self.speech_start = None
        if self.session.live:
            words = self.session.text()
            if words != self.words:
                self.words = words
                self.on_words(words, self._kind())
        if talking:
            long_for = self.MAX_TURN_HERS if self._hers() else self.MAX_TURN
            if (self.pos - self.turn_start) / RATE >= long_for:
                # the next turn starts from here: with the speech still counted from before, a TV that never paused
                # started a new turn on every block, each the same 15 s again, 102 in a row in the log
                self.run, self.cut = 0, self.pos
                self._end()
            return
        spoke = (self.voice - self.onset) / RATE  # seconds of the turn with speech in
        if was and self.turn and not self.dictating and spoke >= self.SHORT:  # a pause: have they finished?
            t = time.time()
            try:
                self.chance = self.turn.finished(self._audio(self.turn_start))
            except Exception as exc:
                print(f"  smart turn failed: {exc!r}")
                self.chance = None
            self.turn_ms = int((time.time() - t) * 1000)
        if self.ahead is None and self.early is None and not self.session.live and self._ahead_due(quiet):
            # its audio taken here, on the mic's thread, so what's written is this pause's and no later block's
            self.ahead = self.writers.submit(self.session.transcribe, self.session.audio(quiet))
        # "Hello" and a pause is the start of "Hello [breath] Harry": ending there cut her name off, 3 times in 3 one
        # evening, so with only a greeting written it waits the longest for the rest
        held = self.hold_for(self.words)
        done = self.chance is not None and self.chance >= self.FINISHED
        if self.chance is None and self.turn and not self.dictating and spoke < self.SHORT and quiet >= self.QUIET:
            done = self._whole_sentence()
        sure = self.chance is not None and self.chance >= self.SURE and quiet >= self.SOON  # see SOON
        if quiet >= self.LONGEST or (not held and (sure or (quiet >= self.QUIET and (
                done or (quiet >= self.SETTLE and (self.chance is None or self.chance >= self.MAYBE)))))):
            if not self.session.live and spoke < self.SHORT and quiet < self.LONGEST:
                # Parakeet and Whisper only write once you stop, so a short turn is written here, when it would end
                # anyway, and waits the same if that's only a greeting: "Hello [700 ms] Harry" came out as "Hello." and
                # "Jeff". Anything else ends as soon as before, without being written twice
                self.early = self.early or self._written(self.session, quiet)
                if self.hold_for(self.early[0]):
                    return
            self._end()
