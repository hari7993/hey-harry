"""Her voice from a provider (29 October 2026, the owner's ask): ElevenLabs, Sarvam or Deepgram, picked in Settings >
Voice the way the answer model is (providers.py): a provider, its key, then any of its voices, the list read live
where it has one. Fish Audio, her voice on this PC (pocket.py) and Windows' own voices are siri.py's, as before.

A voice from one of these is saved as "<provider>:<model>/<voice>": "elevenlabs:eleven_flash_v2_5/JBFqnCBsd6RMkjVDRZzb"
or "sarvam:bulbul:v3/shubh". Deepgram's model is the voice: "deepgram:aura-2-thalia-en". So a line kept in her cache
in one voice is never played for another, and nothing else needs saving.

Each gives 16-bit mono PCM at RATE: ElevenLabs and Deepgram as it's made, so she starts talking as the first of it
comes in, and Sarvam the whole line at once (its REST API has no stream). If one fails, or your credits are used up,
siri says that line in her voice on this PC instead. What goes to the provider: the line's text, and nothing else. A
line said once is kept as a wav in her cache and never sent again.

Checked against each provider's API reference on 29 October 2026: ElevenLabs' /v1/text-to-speech/{voice}/stream
(pcm_24000), /v2/voices and /v1/models; Sarvam's /text-to-speech (Bulbul v2, v3 and v4 Flash); Deepgram's /v1/speak
(Aura-2, linear16 with no container)."""
import base64
import io
import json
import os
import re
import threading
import time
import wave
from collections import namedtuple

import numpy as np
import requests

from secrets_store import get_secret
from winplatform import APPDATA_DIR

RATE = 24000  # what each is asked for, so a line plays the same whichever made it
HTTP = requests.Session()  # kept open between lines: a fresh HTTPS connection costs a few hundred ms
WAIT = (5, 30)  # seconds to connect, then to wait for each piece

Provider = namedtuple("Provider", "id name key key_url host")
PROVIDERS = (
    Provider("elevenlabs", "ElevenLabs", "ELEVENLABS_API_KEY", "https://elevenlabs.io/app/settings/api-keys",
             "https://api.elevenlabs.io"),
    Provider("sarvam", "Sarvam", "SARVAM_API_KEY", "https://dashboard.sarvam.ai", "https://api.sarvam.ai"),
    Provider("deepgram", "Deepgram", "DEEPGRAM_API_KEY", "https://console.deepgram.com", "https://api.deepgram.com"),
)
BY_ID = {p.id: p for p in PROVIDERS}
KEYS = tuple(dict.fromkeys(p.key for p in PROVIDERS))

# ElevenLabs' models till its own list is read with your key: Flash, the quickest, first
ELEVEN_MODELS = (("eleven_flash_v2_5", "Flash v2.5, the quickest"), ("eleven_turbo_v2_5", "Turbo v2.5"),
                 ("eleven_multilingual_v2", "Multilingual v2, the richest"))
# Sarvam's Bulbul voices, each model's own (its docs, 29 October 2026). v4 Flash has over 200 personas, by name,
# language and style; these two are its English ones the docs name, the first its default
SARVAM = (
    ("bulbul:v3", "Bulbul v3", ("shubh", "aditya", "ritu", "priya", "neha", "rahul", "pooja", "rohan", "simran",
                                "kavya", "amit", "dev", "ishita", "shreya", "ratan", "varun", "manan", "sumit",
                                "roopa", "kabir", "aayan", "ashutosh", "advait", "anand", "tanya", "tarun", "sunny",
                                "mani", "gokul", "vijay", "shruti", "suhani", "mohit", "kavitha", "rehan", "soham",
                                "rupali")),
    ("bulbul:v4-flash", "Bulbul v4 Flash", ("shubh_enhi_ads", "simran_en_customer")),
    ("bulbul:v2", "Bulbul v2", ("anushka", "manisha", "vidya", "arya", "abhilash", "karun", "hitesh")),
)
SARVAM_MEN = {"abhilash", "karun", "hitesh"}  # Bulbul v2's men; v3 doesn't say
# Deepgram's Aura-2 voices that speak English
AURA = ("thalia", "andromeda", "helena", "apollo", "arcas", "aries", "amalthea", "asteria", "athena", "atlas", "aurora",
        "callista", "cora", "cordelia", "delia", "draco", "electra", "harmonia", "hera", "hermes", "hyperion", "iris",
        "janus", "juno", "jupiter", "luna", "mars", "minerva", "neptune", "odysseus", "ophelia", "orion", "orpheus",
        "pandora", "phoebe", "pluto", "saturn", "selene", "theia", "vesta", "zeus")
DEFAULT_MODEL = {"elevenlabs": ELEVEN_MODELS[0][0], "sarvam": SARVAM[0][0], "deepgram": "aura-2-thalia-en"}

PATH = os.path.join(APPDATA_DIR, "voices.json")  # ElevenLabs' voices and models, read with your key
FRESH_FOR = 30 * 60
_lock = threading.Lock()
_data = None


# --------------------------------------------------------------------------- a saved voice
def parse(voice):
    """(provider, model, voice) of a voice from one of these, or None for Fish's, this PC's and Windows'."""
    head, _, rest = str(voice or "").strip().partition(":")
    p = BY_ID.get(head)
    if p is None or not rest:
        return None
    if p.id == "deepgram":
        return (p, rest, rest) if re.fullmatch(r"aura[\w-]*", rest) else None
    model, slash, name = rest.rpartition("/")
    if not slash or not name:
        return None
    return p, model or DEFAULT_MODEL[p.id], name


def full(p, voice, model=None):
    """The saved form of p's voice, with model for ElevenLabs (its default if none): "elevenlabs:<model>/<id>"."""
    if p.id == "elevenlabs":
        return f"elevenlabs:{model or DEFAULT_MODEL['elevenlabs']}/{voice}"
    return f"{p.id}:{voice}"


def ready(p):
    return bool(get_secret(p.key))


# --------------------------------------------------------------------------- her line, from the provider
def why(r):
    """A provider's own reason a request failed, in a few words: "401 Invalid API key"."""
    try:
        body = r.json()
    except ValueError:
        body = None
    found = None
    if isinstance(body, dict):
        for name in ("detail", "error", "err_msg", "message"):
            v = body.get(name)
            if isinstance(v, dict):
                v = v.get("message") or v.get("status")
            elif isinstance(v, list) and v:
                v = v[0].get("msg") if isinstance(v[0], dict) else v[0]
            if v:
                found = str(v)
                break
    return " ".join(f"{r.status_code} {found or r.reason or ''}".split())[:200]


def _pieces(text, most):
    """text in pieces of at most most characters, cut between sentences where it can be."""
    out, now = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", " ".join(str(text).split())):
        while len(sentence) > most:  # one sentence longer than that: cut between words
            cut = sentence.rfind(" ", 0, most)
            cut = cut if cut > 0 else most
            if now:
                out.append(now)
                now = ""
            out.append(sentence[:cut])
            sentence = sentence[cut:].strip()
        if now and len(now) + 1 + len(sentence) > most:
            out.append(now)
            now = ""
        now = f"{now} {sentence}".strip()
    return out + ([now] if now else [])


def _pcm_of_wav(data):
    """A wav's audio as 16-bit mono PCM at RATE."""
    with wave.open(io.BytesIO(data)) as w:
        channels, width, rate, frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.readframes(
            w.getnframes())
    if width != 2:
        raise RuntimeError(f"its audio came as {8 * width}-bit")
    a = np.frombuffer(frames, "<i2").astype(np.float32)
    if channels > 1:
        a = a.reshape(-1, channels).mean(axis=1)
    if rate != RATE and len(a):
        a = np.interp(np.arange(0, len(a), rate / RATE), np.arange(len(a)), a)
    return np.clip(a, -32768, 32767).astype("<i2").tobytes()


def _sarvam(text, model, speaker, key):
    """The whole line from Sarvam's Bulbul as PCM, asked for in pieces of at most what it takes at once: 1500
    characters on v2, 2500 after. Indian English, which takes Hindi words mixed in."""
    most = 1400 if model == "bulbul:v2" else 2400
    out = b""
    for piece in _pieces(text, most):
        body = {"text": piece, "language_code": "en-IN", "speaker": speaker, "model": model,
                "speech_sample_rate": RATE}
        if model == "bulbul:v2":
            body["enable_preprocessing"] = True  # numbers and English words said as words: v2's alone
        r = HTTP.post(f"{BY_ID['sarvam'].host}/text-to-speech", headers={"api-subscription-key": key}, json=body,
                      timeout=WAIT)
        if not r.ok:
            raise RuntimeError(f"Sarvam: {why(r)}")
        audios = (r.json() or {}).get("audios") or []
        if not audios:
            raise RuntimeError("Sarvam sent no audio")
        out += _pcm_of_wav(base64.b64decode(audios[0]))
    return out


def stream(text, voice):
    """Her line in voice as 16-bit mono PCM at RATE, a piece at a time as the provider makes it. RuntimeError with the
    provider's own reason when it won't make it."""
    p, model, name = parse(voice)
    key = get_secret(p.key)
    if not key:
        raise RuntimeError(f"there's no {p.name} key: add it in Settings > Voice")
    if p.id == "sarvam":
        pcm = _sarvam(text, model, name, key)
        for i in range(0, len(pcm), 8192):
            yield pcm[i:i + 8192]
        return
    if p.id == "elevenlabs":
        r = HTTP.post(f"{p.host}/v1/text-to-speech/{name}/stream", params={"output_format": f"pcm_{RATE}"},
                      headers={"xi-api-key": key}, json={"text": text, "model_id": model}, stream=True, timeout=WAIT)
    else:
        r = HTTP.post(f"{p.host}/v1/speak", params={"model": model, "encoding": "linear16", "sample_rate": RATE,
                                                    "container": "none"},
                      headers={"Authorization": f"Token {key}"}, json={"text": text}, stream=True, timeout=WAIT)
    if not r.ok:
        raise RuntimeError(f"{p.name}: {why(r)}")
    for piece in r.iter_content(4096):
        if piece:
            yield piece


def _write(path, pcm):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm[:len(pcm) - len(pcm) % 2])


def to_wav(text, voice, path):
    """Her line in voice, kept as a wav at path, for her cache."""
    pcm = b"".join(stream(text, voice))
    if len(pcm) < 2:
        raise RuntimeError("no audio came back")
    _write(path, pcm)


def keep(path, pcm):
    """A line she's just said in full, kept at path as a wav for next time, written whole or not at all."""
    if len(pcm) < 2:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _write(path + ".part", pcm)
        os.replace(path + ".part", path)
    except OSError as exc:
        print(f"  voices: couldn't keep the line: {exc!r}")


# --------------------------------------------------------------------------- their voices, for the picker
def _load():
    global _data
    if _data is None:
        try:
            with open(PATH, encoding="utf-8") as f:
                _data = json.load(f)
        except (OSError, ValueError):
            _data = {}
    return _data


def _save():
    try:
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        with open(PATH + ".tmp", "w", encoding="utf-8") as f:
            json.dump(_data, f)
        os.replace(PATH + ".tmp", PATH)
    except OSError as exc:
        print(f"  voices: couldn't keep the lists: {exc!r}")


def cached(p):
    """What's known of p's voices: {"voices": [{"id", "name", "about"}], "models": [(id, name)], "at", "error"}.
    ElevenLabs' are your account's, read with your key; Sarvam's and Deepgram's are fixed."""
    if p.id == "sarvam":
        voices = [{"id": f"{model}/{speaker}", "name": speaker.split("_")[0].title(),
                   "about": f"{label}{', a man' if speaker in SARVAM_MEN else ''}"
                            + (f", {speaker.split('_', 2)[2]}" if speaker.count("_") == 2 else "")}
                  for model, label, speakers in SARVAM for speaker in speakers]
        return {"voices": voices, "models": [], "at": 0, "error": ""}
    if p.id == "deepgram":
        voices = [{"id": f"aura-2-{name}-en", "name": name.title(), "about": "Aura-2, English"} for name in AURA]
        return {"voices": voices, "models": [], "at": 0, "error": ""}
    with _lock:
        entry = _load().get(p.id) or {}
    return {"voices": entry.get("voices") or [], "models": [tuple(m) for m in entry.get("models") or ELEVEN_MODELS],
            "at": entry.get("at") or 0, "error": entry.get("error") or ""}


def stale(p):
    return p.id == "elevenlabs" and ready(p) and time.time() - cached(p)["at"] > FRESH_FOR


def refresh(p, timeout=15):
    """Reads ElevenLabs' voices and models with your key (the others' are fixed): what's known after."""
    if p.id != "elevenlabs":
        return cached(p)
    key = get_secret(p.key)
    if not key:
        return cached(p)
    try:
        voices, token = [], None
        for _ in range(10):  # 100 a page, up to a thousand
            params = {"page_size": 100, **({"next_page_token": token} if token else {})}
            r = HTTP.get(f"{p.host}/v2/voices", params=params, headers={"xi-api-key": key}, timeout=timeout)
            if not r.ok:
                raise RuntimeError(why(r))
            body = r.json() or {}
            for v in body.get("voices") or []:
                labels = v.get("labels") or {}
                about = ", ".join(str(x) for x in (labels.get("accent"), labels.get("gender"), labels.get("age"),
                                                   labels.get("use_case") or labels.get("descriptive")) if x)
                voices.append({"id": v["voice_id"], "name": v.get("name") or v["voice_id"],
                               "about": about or str(v.get("category") or "")})
            token = body.get("next_page_token")
            if not body.get("has_more") or not token:
                break
        r = HTTP.get(f"{p.host}/v1/models", headers={"xi-api-key": key}, timeout=timeout)
        models = [[m["model_id"], m.get("name") or m["model_id"]] for m in (r.json() if r.ok else [])
                  if isinstance(m, dict) and m.get("can_do_text_to_speech")]
        entry = {"voices": voices, "models": models or [list(m) for m in ELEVEN_MODELS], "at": time.time(), "error": ""}
    except (requests.RequestException, ValueError, RuntimeError, KeyError, TypeError) as exc:
        old = cached(p)
        entry = {"voices": old["voices"], "models": [list(m) for m in old["models"]], "at": old["at"],
                 "error": f"Couldn't read {p.name}'s voices: {exc}"}
    with _lock:
        _load()[p.id] = entry
        _save()
    return cached(p)


def name_of(voice):
    """"Shubh, Sarvam" for a saved voice, from what's known of its provider's list; None if it isn't one of these."""
    parsed = parse(voice)
    if parsed is None:
        return None
    p, model, name = parsed
    key = name if p.id == "elevenlabs" else (model if p.id == "deepgram" else f"{model}/{name}")
    found = next((v for v in cached(p)["voices"] if v["id"] == key), None)
    return f"{found['name'] if found else name}, {p.name}"
