"""Her voice on this PC: tiny-voca (huggingface.co/n4ze3m/tiny-voca, Muhammed Nazeem's, Apache 2.0), 4.5 million
parameters in an 21 MB ONNX file run by the onnxruntime she already has, with its own phonemizer, dizione (Apache 2.0,
numpy only), so no new package. Free for good and nothing leaves the PC, not even the words. For when Fish's free
voice ends (30 November 2026) or is down, or picked in Settings > Voice.

It took Underdog Woof's place on 20 November 2026 (the owner's ask: "it's better than that, integrate this and
remove that"). Measured on this i5-12450H that day, twelve of her lines: a short line ready in 44 ms and the longest in
0.2 s, where Woof started a short one after a second (36 times faster than real time on 4 threads against 2.2);
Parakeet heard 88% of its words as written against Woof's 90%, and "Madhusudhan" and "Amma" as well or better; about
45 MB of her own while loaded, as Woof's was. Its own page says where it's weak: foreign names and odd spellings can
be read wrong (voice_say_as, Settings > Voice, says how to say one), and it can sound a little synthetic, as its
training speech was itself made by a model.

Two voices, F2 (a woman's, hers) and M2 (a man's), American English, 24 kHz. A voice is saved as "voca:F2".

Its files are fetched the first time it's needed, the model's at MODEL and the phonemizer's code at CODE, the versions
read through before they were used, each checked against its SHA-256 (FILES) into the models folder, and the code is
imported from there, never with a .pyc beside it. Text is read a sentence at a time, cut as tiny-voca's own
infer.py cuts it (sentences, finished: no break after "Dr." or an initial, a full stop added where there's no mark,
or the last word breaks off). Its weights are mapped from disk (speech.mapped_model) and what a line needs is given
back after it (ARENA), so it holds about 17 MB for the model and 28 for the phonemizer's dictionary, and is never
let go once loaded.

A line made ahead for the cache (siri.warm_cache) gives way to one she's saying now, and waits while someone's
talking (hold), as Woof's did.
"""
import hashlib
import importlib.util
import os
import queue
import re
import shutil
import sys
import threading
import time
import urllib.request

import numpy as np

import settings
import speech

MODEL = "1e73262226dbf4ef02e9df277e81aaa1db5ce16c"  # huggingface.co/n4ze3m/tiny-voca, read 20 November 2026
CODE = "8cd889e4de7be6bd1dd2e6891344a0729fa14dd4"  # github.com/n4ze3m/dizione, its phonemizer, read the same day
FROM = (("model/", "https://huggingface.co/n4ze3m/tiny-voca/resolve/" + MODEL + "/"),  # a file's start: where it's from
        ("code/dizione/", "https://raw.githubusercontent.com/n4ze3m/dizione/" + CODE + "/src/dizione/"),
        ("code/LICENSE", "https://raw.githubusercontent.com/n4ze3m/dizione/" + CODE + "/LICENSE"))
FOLDER = "tiny-voca-" + MODEL[:8]
FILES = {  # what it needs, and each one's SHA-256 at those versions
    "code/LICENSE": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
    "code/dizione/__init__.py": "24217fbe139a40de36a7cbb73dafb771559c87194c9ce9098e8e65b9d7f4a4f3",
    "code/dizione/__main__.py": "7283fe453b4d25042748b617a0b5f436d2965dac1f2cddc2d1d6c859fff5a3b1",
    "code/dizione/align.py": "9c14ba39de859f8008df6138dbd8cbed50f254043ddadfd4ebfef1dd3ca9b794",
    "code/dizione/convert.py": "a88320f514615ec5e790983ddd800f9de6849af096fa36d0b4c962122d986405",
    "code/dizione/data/abbreviations.txt": "89064821a56c06aa38756642b9774b561edc53399b433f2b2dbc07156c6df2f7",
    "code/dizione/data/chat.txt": "6b8e80ffca0c15917aff103d5805a0a62b43d7e3fbce5a7c9a4ca0b707eec1ce",
    "code/dizione/data/endings.txt": "ce4ab4798e96b6adec09d3bd5d1d0413976460cb8d02092377d67bd18f34d9c3",
    "code/dizione/data/exceptions.txt": "978f6687c0c919b59ef391f29d64d2f82ef43d37150ef4b5a88a6c9394c1fcbd",
    "code/dizione/data/function_words.txt": "d74956771ca5dcd8247b2eb9c2ceadcf525ad3e6df621361071a3e1ee6f9e148",
    "code/dizione/data/homograph_fixes.txt": "fcaa38ab846ed3f9122c90a027b770e59f37d46581295acb2a797f33e7e5e504",
    "code/dizione/data/homograph_rules.txt": "7971282ac2f3ed80934881f4c9f9a2348b2f1e7634df6947cb5f1847a87782ec",
    "code/dizione/data/letters.txt": "1cb533378c70c437b952b3938df48f5e94e18187bf612f4881b339ccf5b06882",
    "code/dizione/data/phrases.txt": "9cd5e6b2ed62cfe838738aae88287a163055ae09493a56568ccdd9daab9183bd",
    "code/dizione/data/units.txt": "b1ebe3d00c9da9579e9d6dcef6cd6a843505c82f1553fa7ec111a740b7a06e5a",
    "code/dizione/engine.py": "19934b30b8a2ad4f9d0c74df2fb9b74ff3c295d9e41a8d429ada3d99fd9c2a97",
    "code/dizione/g2p.py": "7eae21ddbb9722f45e68f514eeaf6720cec9b7b230b9215b2dd05b84a80ea79a",
    "code/dizione/homographs.py": "3d194cedfaab6351e7f70690b22fe46ca30d29edac56ce0c07b0b19cf6eee2b9",
    "code/dizione/morphology.py": "20dd237575001b85e9740f16d4acd59dbd77cd28f784bf149a6836fc663a3dfb",
    "code/dizione/normalize.py": "e08cace2700af81ac6b06a5aa7b45b9072cf5b10d2cb4fbd071585e963612a30",
    "code/dizione/sentence.py": "e2f973a67d7d681d6fc88a28d3337687b095da297dbfa2fcd7f0f1c2e131876b",
    "code/dizione/symbols.py": "e66f42fc7f14f7971151abd28b1c1c4c080e2697552a934ee445afd91e8ee879",
    "code/dizione/tables.py": "3ea77dd4ce7eb1c11af4ea59befff912c64ab0810c44048acd2f7ac4638ec567",
    "model/LICENSE": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
    "model/config.json": "27bcbf322fc428581f0e959be1c141dd7751c61f4fed5eded326e779b215f69c",
    "model/onnx/model.onnx": "fe6d918791a15b82e37465981d7f27a070e46b46635e5a3482fc8dff87a1ae46",
    "model/phonemizer/LICENSE.cmudict": "bd4ce8e44170a5f9f481310ca85c51de3c4f851a65e679b40e603b143bd3542a",
    "model/phonemizer/LICENSE.homograph-data": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
    "model/phonemizer/align.json": "864763dbd558a864950266b2c30627f1cad203e75062ee842ee63c653e823b75",
    "model/phonemizer/g2p.json": "c518fd839ea0109c0b2b4f778c17506bf0d7653557b8b8c97a4c8dd9883d4432",
    "model/phonemizer/g2p.npz": "eb3fd519ff00e72d850928d2fccb968adc36134bca2f3bda09de7e794c2ed01b",
    "model/phonemizer/homographs.json": "9c3a96fcdf79fa27d1b3686dc6a507c37e4f754966928608ee9ddb617ba39192",
    "model/phonemizer/lexicon.json": "4d67c1f94b86405a5b8766fb13b8cd92a1371204767dd709582a337e8e0ab334",
    "model/phonemizer/lexicon.tsv": "3fc930345c6b3cabc533981c4b212fa309eec83913fcdbd42919338270d64b06",
    "model/phonemizer/sources.json": "f4c54924d30a5bc0bc1e3d7b058adb924484b3fab8541bc8d8bcecfb028fdbad",
}
SIZE = "27 MB"
CREDIT = "tiny-voca by Muhammed Nazeem"
VOICES = {"F2": 0, "M2": 1}  # as the model numbers them
DEFAULT = "F2"
RATE = 24000
THREADS = 4  # onnxruntime's, asleep between lines: 36 times real time against 23 on 2
MOST = 480  # phonemes in one go of the model, which takes 512: a longer sentence is cut at its commas (shorter)
PEAK = 0.99  # the loudest a piece is let be: the model can peak above 1, which clips as 16-bit
HOLD = 8.0  # seconds after someone starts talking that lines made ahead wait, so the answer finds her voice free
LEAD = 0.1  # seconds of quiet kept before a piece's first sound
# what a line needs is given back to Windows after it rather than kept in onnxruntime's pool: 17 MB of hers for the
# model against 49, the long line still made in 0.2 s (with the pool off altogether it took 0.36)
ARENA = ("memory.enable_memory_arena_shrinkage", "cpu:0")
# the voices she had on this PC before, as saved in settings: all hers now in tiny-voca's
WAS = ("woof:", "kokoro:", "pocket:")
# tiny-voca's own rules for where a sentence ends (its infer.py, Apache 2.0): never after a title or an initial
_SENTENCE_END = re.compile(r"""(?:(?<=[.!?\u2026])|(?<=[.!?\u2026]["')\]]))\s+(?=["'(\[]?[A-Z0-9])""")
_NOT_AN_END = re.compile(r"(?:\b(?:mr|mrs|ms|dr|prof|sr|jr|st|vs|etc|no|inc|ltd|co|e\.g|i\.e|a\.m|p\.m)|\b[A-Z])\.$",
                         re.IGNORECASE | re.ASCII)
_CLAUSE_END = re.compile(r"(?<=[,;:\u2014])\s+")
_CLOSING = "\"'\u201d\u2019)]\u00bb"  # these may stand after the last mark: She said "go!"


def folder():
    return os.path.join(speech.models_dir(), FOLDER)


def available(voice=DEFAULT):
    """True once its files are here (it fetches them the first time it speaks)."""
    return all(os.path.isfile(os.path.join(folder(), name)) for name in FILES)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def url(name):
    """Where the file `name` of FILES is fetched from, at the version that was read."""
    for start, base in FROM:
        if name.startswith(start):
            return base + name[len(start):]
    raise KeyError(name)


def fetch(notify=None):
    """Its files, fetched at MODEL and CODE the first time and each checked against FILES; a file that doesn't match
    is thrown away, and nothing's used till all of them do. Its folder."""
    where = folder()
    missing = [name for name in FILES if not os.path.isfile(os.path.join(where, name))]
    if missing and notify:
        notify(f"Downloading her voice on this PC ({SIZE}), one time\u2026")
    for name in missing:
        path = os.path.join(where, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        urllib.request.urlretrieve(url(name), path + ".part")
        if _sha256(path + ".part") != FILES[name]:
            os.remove(path + ".part")
            raise RuntimeError("Her voice on this PC didn't download right, it'll try again next time")
        os.replace(path + ".part", path)  # only a checked file gets the real name
    return where


def _module(where):
    """Its phonemizer's own code, dizione, from its folder, each file checked again before it's run: what's run is
    what was read. Never from a .pyc beside it, which nothing checks: any there are taken out, and none is written."""
    for name, digest in FILES.items():
        if _sha256(os.path.join(where, name)) != digest:
            raise RuntimeError(f"Her voice on this PC has changed on disk ({name}), so it isn't run")
    if "dizione" in sys.modules:
        return sys.modules["dizione"]
    package = os.path.join(where, "code", "dizione")
    shutil.rmtree(os.path.join(package, "__pycache__"), ignore_errors=True)
    os.environ["DIZIONE_DATA"] = os.path.join(where, "model", "phonemizer")  # where it looks for its dictionary
    spec = importlib.util.spec_from_file_location("dizione", os.path.join(package, "__init__.py"),
                                                  submodule_search_locations=[package])
    module = importlib.util.module_from_spec(spec)
    sys.modules["dizione"] = module
    written, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
        module.phonemize("Hello.")  # its own parts imported and its dictionary read now, 0.3 s, not on a line
    except Exception:
        for name in [n for n in sys.modules if n == "dizione" or n.startswith("dizione.")]:
            sys.modules.pop(name, None)
        raise
    finally:
        sys.dont_write_bytecode = written
    return module


def said_as(text):
    """text with the names Settings says how to say (voice_say_as, {"Saoirse": "Seersha"}) put as she should say
    them, whole words only."""
    for word, sound in (settings.get("voice_say_as") or {}).items():
        if word and sound:
            text = re.sub(rf"\b{re.escape(str(word))}\b", str(sound), text)
    return text


def finished(text):
    """text with a full stop added when it ends without a mark: before a mark the voice lets the sound fall, and
    without one the last word breaks off (tiny-voca's own rule)."""
    body = str(text).rstrip()
    if not body:
        return ""
    last = body.split()[-1]
    if any(c.isalnum() for c in last):
        marked = last.rstrip(_CLOSING)[-1:] in tuple(".!?\u2026,;:")
    else:
        marked = any(c in ".!?\u2026" for c in last) or last in (",", ";", ":")
    return body if marked else body + "."


def sentences(text):
    """text's sentences, the pieces it's made in, with no break after a title or an initial or inside a number
    (tiny-voca's own rule), and none that has nothing to say."""
    parts, current = [], ""
    for piece in _SENTENCE_END.split(" ".join(str(text).split())):
        current = f"{current} {piece}" if current else piece
        if not _NOT_AN_END.search(current):
            parts.append(current)
            current = ""
    if current:
        parts.append(current)
    return [finished(p) for p in parts if any(c.isalnum() for c in p)]


def shorter(text):
    """text in smaller pieces, for a sentence too long for one go of the model: cut after its commas and the like if
    it has any, else in two between words; [] for a single word."""
    parts = _CLAUSE_END.split(text)
    if len(parts) > 1:
        return parts
    words = text.split(" ")
    if len(words) < 2:
        return []
    half = (len(words) + 1) // 2
    return [" ".join(words[:half]), " ".join(words[half:])]


def lead_trimmed(audio, keep=LEAD):
    """audio from keep seconds before its first sound (louder than 1%), so the quiet it starts with isn't waited
    through. All of it if there's no sound."""
    loud = np.flatnonzero(np.abs(audio) > 0.01)
    return audio[max(0, int(loud[0]) - int(keep * RATE)):] if len(loud) else audio


_held = [0.0]  # lines made ahead wait till then


def hold(seconds=HOLD):
    """Someone's started talking: lines made ahead wait seconds, so the answer to them isn't made behind one. Only
    notes the time, so it's nothing to call each time speech starts."""
    _held[0] = max(_held[0], time.time() + seconds)


class Voice:
    """The model and its phonemizer, loaded: voice(piece, name) is piece's sound, float32 at RATE, nothing for a
    piece with nothing to pronounce (another script, signs only)."""

    def __init__(self, dizione, session, run):
        self.dizione, self.session, self.run = dizione, session, run

    def __call__(self, piece, voice=DEFAULT):
        try:
            phones = self.dizione.phonemize(finished(piece))
        except ValueError:  # nothing in it to pronounce
            return np.zeros(0, np.float32)
        if len(phones.ids) > MOST:  # too long for one go: its clauses, then halves
            parts = shorter(piece)
            made = [self(part, voice) for part in parts]
            return np.concatenate(made) if made else np.zeros(0, np.float32)
        one = lambda value: np.array([value], np.float32)  # noqa: E731
        audio = self.session.run(["audio"], {
            "tokens": np.array([phones.ids], np.int64), "stress": np.array([phones.stress], np.int64),
            "voice": np.array([VOICES.get(str(voice).upper(), VOICES[DEFAULT])], np.int64), "speed": one(1.0),
            "pitch_shift": one(0.0), "pitch_range": one(1.0)}, self.run)[0][0]
        loudest = float(np.abs(audio).max()) if len(audio) else 0.0
        return np.asarray(audio * (PEAK / loudest) if loudest > PEAK else audio, np.float32)


class Engine:
    def __init__(self):
        self.tts, self.used = None, 0.0
        self.lock = threading.Lock()  # one line at a time
        self.turns = threading.Condition()  # tells a line made ahead when no line she's saying is waiting
        self.live = 0  # lines she's saying now, being made or waiting to be

    def _load(self):
        import onnxruntime as ort
        where = fetch(print)
        dizione = _module(where)
        so = ort.SessionOptions()
        so.inter_op_num_threads, so.intra_op_num_threads = 1, THREADS
        so.add_session_config_entry("session.intra_op.allow_spinning", "0")  # asleep between lines, not spinning
        source = os.path.join(where, "model", "onnx", "model.onnx")
        # its weights mapped from disk, as Parakeet's are: 9 MB of her own as it loads against 37
        mapped = speech.mapped_model(source, os.path.join(speech.models_dir(), FOLDER + "-mapped"), threads=THREADS,
                                     what="her voice")
        session = None
        if mapped:
            try:
                session = ort.InferenceSession(os.path.join(mapped, "model.onnx"), sess_options=so,
                                               providers=["CPUExecutionProvider"])
            except Exception as exc:
                speech.unmade(mapped, "her voice", exc)
        session = session or ort.InferenceSession(source, sess_options=so, providers=["CPUExecutionProvider"])
        run = ort.RunOptions()
        run.add_run_config_entry(*ARENA)
        self.tts = Voice(dizione, session, run)
        print("  her voice on this PC loaded (tiny-voca)")

    def make(self, text, voice=DEFAULT, on_audio=None, stop=None, ahead=False):
        """Say text in voice: on_audio(samples, float32 at RATE) gets it a sentence at a time. Returns all of it.
        stop(): True to stop making it, as when she's been stopped mid-line. Asked before it starts and before each
        sentence, so a line queued behind others isn't made in full after a stop. ahead: made for the cache, not to
        be said now (see _ahead)."""
        if stop and stop():
            return np.zeros(0, np.float32)
        if ahead:
            return self._ahead(text, voice)
        made = []
        with self.turns:
            self.live += 1
        try:
            with self.lock:
                for piece in sentences(said_as(text)):
                    if stop and stop():  # stopped while it waited, or between sentences
                        break
                    audio = self._say(piece, voice)
                    made.append(audio)
                    if on_audio is not None and len(audio) and not (stop and stop()):
                        on_audio(audio)
        finally:
            with self.turns:
                self.live -= 1
                self.turns.notify_all()
        return np.concatenate(made) if made else np.zeros(0, np.float32)

    def _ahead(self, text, voice=DEFAULT):
        """text made for the cache: a sentence at a time, each only once no line she's saying is waiting and
        nobody's started talking in the last HOLD seconds, so the most a line she says waits is the one sentence
        under way. All of it."""
        made = []
        for piece in sentences(said_as(text)):
            while True:
                with self.turns:
                    while self.live or time.time() < _held[0]:
                        self.turns.wait(min(1.0, max(0.05, _held[0] - time.time())))
                with self.lock:
                    if self.live:  # one came in meanwhile: it goes first
                        continue
                    made.append(self._say(piece, voice))
                    break
        return np.concatenate(made) if made else np.zeros(0, np.float32)

    def _say(self, piece, voice=DEFAULT):
        """piece in her voice, its first sound LEAD seconds in. Loaded the first time."""
        if self.tts is None:
            self._load()
        self.used = time.time()
        audio = lead_trimmed(np.asarray(self.tts(piece, voice), np.float32))
        self.used = time.time()
        return audio


_engine = []
_engine_lock = threading.Lock()


def engine():
    with _engine_lock:
        if not _engine:
            _engine.append(Engine())
        return _engine[0]


def stream(text, voice=DEFAULT, stop=None):
    """A queue that gets her voice for text a sentence at a time (float32 at RATE), then None; an exception instead
    if it failed. Made on its own thread, so it can be under way while another line plays."""
    out = queue.Queue()

    def run():
        try:
            engine().make(text, voice, out.put, stop)
            out.put(None)
        except Exception as exc:
            out.put(exc)
    threading.Thread(target=run, daemon=True).start()
    return out


def to_wav(text, path, voice=DEFAULT, ahead=False):
    import soundfile as sf
    sf.write(path, engine().make(text, voice, ahead=ahead), RATE, subtype="PCM_16")
