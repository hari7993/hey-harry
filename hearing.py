"""What you say, heard by a provider (29 October 2026, the owner's ask): Sarvam, ElevenLabs' Scribe, AssemblyAI or
Deepgram, picked in Settings > Speech to text the way the answer model is (providers.py). The PC's own ears
(speech.py) stay, and are the default.

The PC still hears everything first and decides on its own: whether "Hey Harry" was said, whether it's your voice,
when you've finished. Only a turn that's plainly hers goes out, once it's over and she's taken it: one with her name
in it, the one after a bare "Hey Harry", one she decided was for her, right Alt held, and dictation. Room talk never
leaves the PC. Then the provider's words take the place of the PC's if they come within WAIT seconds of asking; if
they're slower, or it fails, the PC's words stand, so she's never later than that. Dictation's phrases go out as
they're said, and each one's words from the provider are put in before it's pasted. "Dictation only" in Settings
keeps commands on the PC.

Sarvam is the one for Indian English and Hinglish: what Parakeet, English only, gets wrong. On 9 October Deepgram took
0.27 to 3.8 s a request from here and was taken out; it's back only as a choice, and WAIT keeps a slow one from
holding her up.

What's sent: that turn's audio, as a 16 kHz wav, and her name and yours as words to listen for. Nothing else.

Checked against each provider's API reference on 29 October 2026: Sarvam's /speech-to-text (Saaras v4, and v3's
modes), ElevenLabs' /v1/speech-to-text (Scribe v2), AssemblyAI's Sync API (sync.assemblyai.com/v1/transcribe, one
request, Universal-3.5 Pro, from July 2026), Deepgram's /v1/listen (Nova-3)."""
import io
import json
import time
import wave
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import requests

import identity
import settings
from secrets_store import get_secret

WAIT = 1.5  # seconds she waits for a provider's words to a command before going with the PC's
SETTLE = 4.0  # and at most this, all told, for dictation's last phrases once you've said stop
RATE = 16000
HTTP = requests.Session()  # kept open between turns, a new HTTPS connection costs a few hundred ms
TIMEOUT = (4, 12)
POOL = ThreadPoolExecutor(4, thread_name_prefix="hearing")

Ears = namedtuple("Ears", "id name key key_url host")
PROVIDERS = (
    Ears("sarvam", "Sarvam", "SARVAM_API_KEY", "https://dashboard.sarvam.ai", "https://api.sarvam.ai"),
    Ears("elevenlabs", "ElevenLabs", "ELEVENLABS_API_KEY", "https://elevenlabs.io/app/settings/api-keys",
         "https://api.elevenlabs.io"),
    Ears("assemblyai", "AssemblyAI", "ASSEMBLYAI_API_KEY", "https://www.assemblyai.com/dashboard",
         "https://sync.assemblyai.com"),
    Ears("deepgram", "Deepgram", "DEEPGRAM_API_KEY", "https://console.deepgram.com", "https://api.deepgram.com"),
)
BY_ID = {p.id: p for p in PROVIDERS}
KEYS = tuple(dict.fromkeys(p.key for p in PROVIDERS))
# what each can be asked for, a row each in the picker: (id, name, what it's for). An id's part after "/" is how it's
# asked: a language, or Saaras v3's mode
MODELS = {
    "sarvam": (("saaras:v4", "Saaras v4", "Indian English, the best here for Indian accents"),
               ("saaras:v4/auto", "Saaras v4, any language", "English or an Indian language, worked out each time"),
               ("saaras:v3/translit", "Saaras v3, Hinglish", "Hindi and English mixed, written in English letters"),
               ("saaras:v3/translate", "Saaras v3, into English", "any Indian language, written as English")),
    "elevenlabs": (("scribe_v2", "Scribe v2", "English"),
                   ("scribe_v2/auto", "Scribe v2, any language", "worked out each time")),
    "assemblyai": (("universal-3-5-pro", "Universal-3.5 Pro", "English, in one quick request"),
                   ("universal-3-5-pro/en-hi", "Universal-3.5 Pro, Hinglish", "English and Hindi mixed")),
    "deepgram": (("nova-3", "Nova-3", "English"),
                 ("nova-3/multi", "Nova-3, languages mixed", "English with Hindi and others")),
}
LOCAL = (("parakeet", "Parakeet", "on this PC, English, about 0.2 s (the default)"),
         ("nemotron", "Nemotron", "on this PC, your words as you talk, more CPU"),
         ("whisper", "Whisper small.en", "on this PC, English"))

Got = namedtuple("Got", "text sure ms")  # a provider's words: sure is None when it doesn't say how sure


# --------------------------------------------------------------------------- the one picked
def parse(value):
    """(provider, model, how) of saved ears like "sarvam:saaras:v3/translit", or None for the PC's own."""
    head, _, rest = str(value or "").strip().partition(":")
    p = BY_ID.get(head)
    if p is None:
        return None
    model, _, how = rest.partition("/")
    known = {m[0] for m in MODELS[p.id]}
    return (p, model, how) if rest in known else None


def picked():
    """The provider's ears picked in Settings, "sarvam:saaras:v4", or "" for the PC's own."""
    value = str(settings.get("ears") or "")
    return value if parse(value) else ""


def name_of(value):
    """"Saaras v4, Sarvam" for saved ears, or None for the PC's own."""
    parsed = parse(value)
    if parsed is None:
        return None
    rest = str(value).split(":", 1)[1]
    return f"{next(m[1] for m in MODELS[parsed[0].id] if m[0] == rest)}, {parsed[0].name}"


def wanted(what):
    """True if a provider's ears are picked for what ("commands" or "dictation"), with its key there."""
    value = picked()
    if not value or (what == "commands" and settings.get("ears_use") == "dictation"):
        return False
    return bool(get_secret(parse(value)[0].key))


# --------------------------------------------------------------------------- asking one
def wav(audio):
    """16 kHz float audio as a 16-bit mono wav."""
    a = np.clip(np.asarray(audio, dtype=np.float32).reshape(-1), -1.0, 1.0)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((a * 32767).astype("<i2").tobytes())
    return out.getvalue()


def terms():
    """Words to listen for: her name and what she calls you."""
    names = [identity.name(), settings.get("name") or ""]
    return [n for n in dict.fromkeys(" ".join(str(n).split()) for n in names) if n]


def _why(r, p):
    import voices
    return f"{p.name}: {voices.why(r)}"


def transcribe(audio, value=None):
    """A Got for audio (16 kHz float) from the ears in value, or the ones picked. RuntimeError with the provider's
    reason if it fails."""
    parsed = parse(value or picked())
    if parsed is None:
        raise RuntimeError("no provider's ears are picked")
    p, model, how = parsed
    key = get_secret(p.key)
    if not key:
        raise RuntimeError(f"there's no {p.name} key: add it in Settings > Speech to text")
    data, t = wav(audio), time.time()
    if p.id == "sarvam":
        form = {"model": model, "language_code": "unknown" if how == "auto" or model == "saaras:v3" else "en-IN"}
        if how in ("translit", "translate"):
            form["mode"] = how
        if model == "saaras:v4" and terms():
            form["keyterms"] = json.dumps(terms())
        r = HTTP.post(f"{p.host}/speech-to-text", headers={"api-subscription-key": key},
                      files={"file": ("turn.wav", data, "audio/wav")}, data=form, timeout=TIMEOUT)
        if not r.ok:
            raise RuntimeError(_why(r, p))
        text, sure = str((r.json() or {}).get("transcript") or ""), None
    elif p.id == "elevenlabs":
        form = {"model_id": model, "tag_audio_events": "false", **({} if how == "auto" else {"language_code": "en"})}
        r = HTTP.post(f"{p.host}/v1/speech-to-text", headers={"xi-api-key": key},
                      files={"file": ("turn.wav", data, "audio/wav")}, data=form, timeout=TIMEOUT)
        if not r.ok:
            raise RuntimeError(_why(r, p))
        body = r.json() or {}
        logs = [w["logprob"] for w in body.get("words") or [] if w.get("type") == "word" and "logprob" in w]
        text, sure = str(body.get("text") or ""), (float(np.exp(np.mean(logs))) if logs else None)
    elif p.id == "assemblyai":
        files = {"audio": ("turn.wav", data, "audio/wav"),
                 "config": (None, json.dumps({"language_codes": ["en", "hi"] if how == "en-hi" else ["en"]}),
                            "application/json")}
        r = HTTP.post(f"{p.host}/v1/transcribe", headers={"Authorization": key, "X-AAI-Model": model}, files=files,
                      timeout=TIMEOUT)
        if not r.ok:
            raise RuntimeError(_why(r, p))
        body = r.json() or {}
        text, sure = str(body.get("text") or ""), body.get("confidence")
    else:
        params = {"model": model, "language": "multi" if how == "multi" else "en", "smart_format": "true",
                  "keyterm": terms()}
        r = HTTP.post(f"{p.host}/v1/listen", params=params, data=data,
                      headers={"Authorization": f"Token {key}", "Content-Type": "audio/wav"}, timeout=TIMEOUT)
        if not r.ok:
            raise RuntimeError(_why(r, p))
        alt = (((r.json() or {}).get("results") or {}).get("channels") or [{}])[0].get("alternatives") or [{}]
        text, sure = str(alt[0].get("transcript") or ""), alt[0].get("confidence")
    sure = None if sure is None else max(0.0, min(1.0, float(sure)))
    return Got(" ".join(text.split()), sure, int((time.time() - t) * 1000))


class Asked:
    """A turn's audio sent to the picked provider on a thread, from the moment it's plainly hers: its words, once
    they come, if they come in time."""

    def __init__(self, audio, value):
        self.value, self.t = value, time.time()
        self.name = parse(value)[0].name
        self.future = POOL.submit(transcribe, audio, value)

    def words(self, until=None):
        """Its Got if it came by until (time.time()), by default WAIT after it was asked, and has words in it; None
        if it was late, failed or empty, said in the log as which."""
        until = self.t + WAIT if until is None else until
        try:
            got = self.future.result(timeout=max(0.0, until - time.time()))
        except TimeoutError:
            print(f"  ({self.name} was slower than {until - self.t:.1f}s, going with this PC's words)")
            return None
        except Exception as exc:
            print(f"  ({self.name} couldn't hear it: {exc}, going with this PC's words)")
            return None
        return got if got.text.strip(" .,!?") else None


def ask(audio, what):
    """A turn's audio sent to the provider picked for what ("commands" or "dictation"), or None when there's none, it
    has no key, or the audio's empty."""
    if audio is None or len(audio) < RATE // 10 or not wanted(what):
        return None
    return Asked(audio, picked())
