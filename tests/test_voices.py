"""Her voice and her ears from a provider (voices.py, hearing.py, 29 October 2026): a saved voice and how each provider
is asked for a line, its lists, a line kept once said and her voice on this PC when one fails; how each provider is
asked to hear a turn, only once it's plainly hers, in time or not at all, and dictation's phrases put in before it's
pasted. Nothing here goes online or plays a sound: fakes stand in for the providers and the speakers."""
import base64
import io
import json
import os
import queue
import shutil
import tempfile
import threading
import time
import unittest
import wave
from types import SimpleNamespace
from unittest import mock

import numpy as np
import requests

from tests.support import ORIGINAL, siri

import assistant_ui
import hearing
import settings
import speech
import voices


class Reply:
    """A provider's answer: JSON, audio in pieces, or an error."""

    def __init__(self, status=200, body=None, pieces=(), reason="OK"):
        self.status_code, self.body, self.pieces, self.reason = status, body, list(pieces), reason
        self.ok = status < 400

    def json(self):
        if self.body is None:
            raise ValueError("not JSON")
        return self.body

    def iter_content(self, size):
        return iter(self.pieces)


def wav_bytes(samples, rate):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.asarray(samples, dtype="<i2").tobytes())
    return out.getvalue()


KEYS = {"ELEVENLABS_API_KEY": "el-key", "SARVAM_API_KEY": "sv-key", "DEEPGRAM_API_KEY": "dg-key",
        "ASSEMBLYAI_API_KEY": "aai-key"}


class Saved(unittest.TestCase):
    def test_a_voice_says_its_provider_model_and_voice(self):
        p, model, name = voices.parse("elevenlabs:eleven_flash_v2_5/JBFqnCBsd6RMkjVDRZzb")
        self.assertEqual((p.id, model, name), ("elevenlabs", "eleven_flash_v2_5", "JBFqnCBsd6RMkjVDRZzb"))
        p, model, name = voices.parse("sarvam:bulbul:v3/shubh")
        self.assertEqual((p.id, model, name), ("sarvam", "bulbul:v3", "shubh"))
        p, model, name = voices.parse("deepgram:aura-2-thalia-en")
        self.assertEqual((p.id, model, name), ("deepgram", "aura-2-thalia-en", "aura-2-thalia-en"))
        for other in ("pocket:p248", "onecore:MSTTS_V110_enIN_HeeraM", "9a9cf47702da476aa4629e2506d4a857", "",
                      None, "elevenlabs:", "elevenlabs:abc", "deepgram:../x", "sarvam:shubh"):
            with self.subTest(other):
                self.assertIsNone(voices.parse(other))

    def test_written_back_the_same(self):
        p = voices.BY_ID["elevenlabs"]
        self.assertEqual(voices.full(p, "abc", "eleven_turbo_v2_5"), "elevenlabs:eleven_turbo_v2_5/abc")
        self.assertEqual(voices.full(p, "abc"), "elevenlabs:eleven_flash_v2_5/abc")
        self.assertEqual(voices.full(voices.BY_ID["sarvam"], "bulbul:v2/anushka"), "sarvam:bulbul:v2/anushka")

    def test_her_voice_may_be_a_providers(self):
        self.assertEqual(siri.voice_id("sarvam:bulbul:v3/shubh"), "sarvam:bulbul:v3/shubh")
        self.assertEqual(siri.voice_name("deepgram:aura-2-thalia-en"), "Deepgram")
        self.assertEqual(siri.voice_name("pocket:p248"), "her voice on this PC")
        a, b = siri.tts_path("Hi.", "elevenlabs:eleven_flash_v2_5/abc"), siri.tts_path("Hi.", "elevenlabs:eleven_v3/abc")
        self.assertNotEqual(a, b)  # a line kept in one model is never played for another


class Lines(unittest.TestCase):
    """A line asked of each provider, as its API reference has it."""

    def setUp(self):
        self.asked = []
        self.keys = mock.patch.object(voices, "get_secret", lambda name: KEYS.get(name))
        self.keys.start()

    def tearDown(self):
        self.keys.stop()

    def post(self, *replies):
        replies = list(replies)

        def post(url, **kw):
            self.asked.append((url, kw))
            return replies.pop(0)
        return mock.patch.object(voices.HTTP, "post", post)

    def test_elevenlabs_streams_pcm(self):
        with self.post(Reply(pieces=[b"\x01\x00", b"\x02\x00"])):
            got = list(voices.stream("Hello.", "elevenlabs:eleven_flash_v2_5/abc"))
        self.assertEqual(got, [b"\x01\x00", b"\x02\x00"])
        url, kw = self.asked[0]
        self.assertEqual(url, "https://api.elevenlabs.io/v1/text-to-speech/abc/stream")
        self.assertEqual(kw["params"], {"output_format": "pcm_24000"})
        self.assertEqual(kw["headers"], {"xi-api-key": "el-key"})
        self.assertEqual(kw["json"], {"text": "Hello.", "model_id": "eleven_flash_v2_5"})
        self.assertTrue(kw["stream"])

    def test_deepgram_streams_raw_linear16(self):
        with self.post(Reply(pieces=[b"\x05\x00"])):
            self.assertEqual(list(voices.stream("Hi.", "deepgram:aura-2-thalia-en")), [b"\x05\x00"])
        url, kw = self.asked[0]
        self.assertEqual(url, "https://api.deepgram.com/v1/speak")
        self.assertEqual(kw["params"], {"model": "aura-2-thalia-en", "encoding": "linear16", "sample_rate": 24000,
                                        "container": "none"})
        self.assertEqual(kw["headers"], {"Authorization": "Token dg-key"})
        self.assertEqual(kw["json"], {"text": "Hi."})

    def test_sarvam_a_wav_at_once_made_24k_and_a_long_line_in_pieces(self):
        clip = base64.b64encode(wav_bytes(np.full(22050, 1000), 22050)).decode()
        with self.post(Reply(body={"audios": [clip]}), Reply(body={"audios": [clip]})):
            pcm = b"".join(voices.stream(("A sentence that goes on. " * 120).strip(), "sarvam:bulbul:v3/shubh"))
        self.assertEqual(len(self.asked), 2)  # over 2,400 characters: two pieces, cut between sentences
        url, kw = self.asked[0]
        self.assertEqual(url, "https://api.sarvam.ai/text-to-speech")
        self.assertEqual(kw["headers"], {"api-subscription-key": "sv-key"})
        body = kw["json"]
        self.assertEqual((body["language_code"], body["speaker"], body["model"], body["speech_sample_rate"]),
                         ("en-IN", "shubh", "bulbul:v3", 24000))
        self.assertNotIn("enable_preprocessing", body)  # v2's alone
        self.assertTrue(all(len(kw["json"]["text"]) <= 2400 for _, kw in self.asked))
        self.assertAlmostEqual(len(pcm) / 2, 2 * 24000, delta=4)  # each second of 22.05 kHz is a second at 24 kHz

    def test_a_providers_reason_when_it_wont(self):
        for reply, words in ((Reply(401, {"detail": {"status": "quota_exceeded", "message": "Quota exceeded"}}),
                              "ElevenLabs: 401 Quota exceeded"),
                             (Reply(402, {"err_msg": "Insufficient credits"}), "Deepgram: 402 Insufficient credits"),
                             (Reply(403, {"error": {"message": "Invalid API key"}}), "Sarvam: 403 Invalid API key"),
                             (Reply(500, None, reason="Server Error"), "ElevenLabs: 500 Server Error")):
            voice = {"E": "elevenlabs:eleven_flash_v2_5/abc", "D": "deepgram:aura-2-thalia-en",
                     "S": "sarvam:bulbul:v2/anushka"}[words[0]]
            with self.subTest(words), self.post(reply):
                with self.assertRaisesRegex(RuntimeError, words):
                    list(voices.stream("Hi.", voice))

    def test_no_key_says_where_to_add_it(self):
        with mock.patch.object(voices, "get_secret", lambda name: None):
            with self.assertRaisesRegex(RuntimeError, "no ElevenLabs key: add it in Settings > Voice"):
                list(voices.stream("Hi.", "elevenlabs:eleven_flash_v2_5/abc"))

    def test_kept_as_a_wav_whole_or_not_at_all(self):
        folder = tempfile.mkdtemp(prefix="voices-")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "line.wav")
        voices.keep(path, np.arange(100, dtype="<i2").tobytes())
        with wave.open(path) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()), (1, 2, 24000, 100))
        self.assertFalse(os.path.exists(path + ".part"))


class Lists(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="voices-")
        self.addCleanup(shutil.rmtree, self.folder, True)
        for patch in (mock.patch.object(voices, "PATH", os.path.join(self.folder, "voices.json")),
                      mock.patch.object(voices, "_data", None),
                      mock.patch.object(voices, "get_secret", lambda name: KEYS.get(name))):
            patch.start()
            self.addCleanup(patch.stop)

    def test_sarvams_and_deepgrams_are_fixed(self):
        sarvam = voices.cached(voices.BY_ID["sarvam"])["voices"]
        self.assertIn({"id": "bulbul:v3/shubh", "name": "Shubh", "about": "Bulbul v3"}, sarvam)
        self.assertIn({"id": "bulbul:v2/karun", "name": "Karun", "about": "Bulbul v2, a man"}, sarvam)
        self.assertIn({"id": "bulbul:v4-flash/shubh_enhi_ads", "name": "Shubh", "about": "Bulbul v4 Flash, ads"}, sarvam)
        self.assertEqual(len(sarvam), 37 + 2 + 7)
        self.assertEqual(len(voices.cached(voices.BY_ID["deepgram"])["voices"]), len(voices.AURA))

    def test_elevenlabs_your_accounts_voices_and_models_read_with_your_key(self):
        pages = [Reply(body={"voices": [{"voice_id": "v1", "name": "Rachel", "labels": {"accent": "american",
                                                                                       "gender": "female"}}],
                             "has_more": True, "next_page_token": "t2"}),
                 Reply(body={"voices": [{"voice_id": "v2", "name": "Raju", "labels": {}, "category": "cloned"}],
                             "has_more": False}),
                 Reply(body=[{"model_id": "eleven_flash_v2_5", "name": "Flash v2.5", "can_do_text_to_speech": True},
                             {"model_id": "eleven_english_sts_v2", "name": "STS", "can_do_text_to_speech": False}])]
        asked = []

        def get(url, params=None, headers=None, timeout=None):
            asked.append((url, params, headers))
            return pages.pop(0)
        p = voices.BY_ID["elevenlabs"]
        with mock.patch.object(voices.HTTP, "get", get):
            entry = voices.refresh(p)
        self.assertEqual(entry["voices"], [{"id": "v1", "name": "Rachel", "about": "american, female"},
                                           {"id": "v2", "name": "Raju", "about": "cloned"}])
        self.assertEqual(entry["models"], [("eleven_flash_v2_5", "Flash v2.5")])
        self.assertEqual(asked[0], ("https://api.elevenlabs.io/v2/voices", {"page_size": 100}, {"xi-api-key": "el-key"}))
        self.assertEqual(asked[1][1], {"page_size": 100, "next_page_token": "t2"})
        self.assertEqual(voices.name_of("elevenlabs:eleven_flash_v2_5/v2"), "Raju, ElevenLabs")
        self.assertEqual(voices.name_of("sarvam:bulbul:v3/ritu"), "Ritu, Sarvam")
        with mock.patch.object(voices.HTTP, "get", lambda *a, **k: Reply(401, {"detail": {"message": "Bad key"}})):
            entry = voices.refresh(p)  # what was read before stays, and why it couldn't now is said
        self.assertEqual(len(entry["voices"]), 2)
        self.assertIn("401 Bad key", entry["error"])


class Speaking(unittest.TestCase):
    """Her line in a provider's voice: kept once said in full, never made ahead, and her voice on this PC when it
    fails."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="tts-")
        self.addCleanup(shutil.rmtree, self.folder, True)
        patch = mock.patch.object(siri, "CACHE_DIR", self.folder)
        patch.start()
        self.addCleanup(patch.stop)
        siri.HER.stop.clear()

    def test_a_line_said_in_full_is_kept(self):
        voice = "deepgram:aura-2-thalia-en"
        with mock.patch.object(voices, "stream", lambda text, v: iter([b"\x01\x00" * 50, b"\x02\x00" * 50])):
            line = ORIGINAL["Line"]("Okay.", voice)
            got = [line.audio.get(timeout=5) for _ in range(3)]
        self.assertEqual(got[2], None)
        self.assertTrue(until(lambda: os.path.exists(line.path)))
        with wave.open(line.path) as w:
            self.assertEqual(w.getnframes(), 100)
        self.assertIsNone(ORIGINAL["Line"]("Okay.", voice).audio)  # next time, from the cache: nothing asked

    def test_one_that_fails_is_said_in_her_voice_on_this_pc(self):
        said = []

        def broken(text, v):
            raise RuntimeError("Deepgram: 402 Insufficient credits")
            yield  # noqa: unreachable, a generator
        with mock.patch.object(voices, "stream", broken), \
                mock.patch.object(siri.pocket, "available", lambda: False), \
                mock.patch.object(siri.win, "speak_native", lambda text, **kw: said.append(text)):
            ORIGINAL["Line"]("Sorry about that.", "deepgram:aura-2-thalia-en").play()
        self.assertEqual(said, ["Sorry about that."])

    def test_a_kept_line_is_made_by_the_provider(self):
        made = []

        def to_wav(text, v, path):
            made.append((text, v))
            with open(path, "wb") as f:
                f.write(wav_bytes([0] * 10, 24000))
        with mock.patch.object(voices, "to_wav", to_wav):
            path, ms, cached = ORIGINAL["fetch_tts"]("On it.", "sarvam:bulbul:v3/shubh")
        self.assertEqual(made, [("On it.", "sarvam:bulbul:v3/shubh")])
        self.assertTrue(os.path.exists(path) and not cached)

    def test_never_made_ahead_in_a_voice_paid_by_the_line(self):
        with mock.patch.object(settings, "get", lambda name: "elevenlabs:eleven_flash_v2_5/abc" if name == "voice"
                               else settings.DEFAULTS.get(name)), \
                mock.patch.object(siri, "fetch_tts", side_effect=AssertionError("made ahead")), \
                mock.patch.object(siri, "all_scripted_lines", lambda: iter(["Okay.", "On it."])):
            ORIGINAL["warm_cache"]()


def until(check, seconds=5.0):
    end = time.time() + seconds
    while time.time() < end:
        if check():
            return True
        time.sleep(0.02)
    return check()


class Ears(unittest.TestCase):
    def setUp(self):
        self.asked, self.saved = [], {}
        for patch in (mock.patch.object(hearing, "get_secret", lambda name: KEYS.get(name)),
                      mock.patch.object(settings, "get", lambda name: self.saved.get(name, settings.DEFAULTS.get(name))),
                      mock.patch.object(hearing.identity, "name", lambda: "Harry")):
            patch.start()
            self.addCleanup(patch.stop)
        self.saved["name"] = "Hari"
        self.audio = (np.sin(np.arange(16000) / 10) * 0.3).astype(np.float32)

    def post(self, reply):
        def post(url, **kw):
            self.asked.append((url, kw))
            return reply
        return mock.patch.object(hearing.HTTP, "post", post)

    def test_the_ones_picked_and_what_for(self):
        self.assertEqual(hearing.picked(), "")
        self.assertFalse(hearing.wanted("commands"))
        self.saved["ears"] = "sarvam:saaras:v3/translit"
        self.assertEqual(hearing.picked(), "sarvam:saaras:v3/translit")
        self.assertEqual(hearing.name_of(hearing.picked()), "Saaras v3, Hinglish, Sarvam")
        self.assertTrue(hearing.wanted("commands") and hearing.wanted("dictation"))
        self.saved["ears_use"] = "dictation"
        self.assertFalse(hearing.wanted("commands"))
        self.assertTrue(hearing.wanted("dictation"))
        self.saved["ears"] = "sarvam:made-up"
        self.assertEqual(hearing.picked(), "")
        with mock.patch.object(hearing, "get_secret", lambda name: None):
            self.saved["ears"] = "deepgram:nova-3"
            self.assertFalse(hearing.wanted("dictation"))  # no key: this PC's ears

    def test_sarvam_with_her_name_and_yours_to_listen_for(self):
        with self.post(Reply(body={"transcript": "Hey Harry, open YouTube", "language_code": "en-IN"})):
            got = hearing.transcribe(self.audio, "sarvam:saaras:v4")
        self.assertEqual((got.text, got.sure), ("Hey Harry, open YouTube", None))
        url, kw = self.asked[0]
        self.assertEqual(url, "https://api.sarvam.ai/speech-to-text")
        self.assertEqual(kw["headers"], {"api-subscription-key": "sv-key"})
        self.assertEqual(kw["data"], {"model": "saaras:v4", "language_code": "en-IN",
                                      "keyterms": json.dumps(["Harry", "Hari"])})
        name, data, kind = kw["files"]["file"]
        with wave.open(io.BytesIO(data)) as w:
            self.assertEqual((w.getframerate(), w.getnchannels(), w.getnframes()), (16000, 1, 16000))
        with self.post(Reply(body={"transcript": "kal ka weather batao"})):
            hearing.transcribe(self.audio, "sarvam:saaras:v3/translit")
        self.assertEqual(self.asked[1][1]["data"], {"model": "saaras:v3", "language_code": "unknown", "mode": "translit"})

    def test_scribe_and_how_sure_its_words_were(self):
        body = {"text": "open notepad", "words": [{"text": "open", "type": "word", "logprob": -0.1},
                                                 {"text": " ", "type": "spacing", "logprob": 0.0},
                                                 {"text": "notepad", "type": "word", "logprob": -0.3}]}
        with self.post(Reply(body=body)):
            got = hearing.transcribe(self.audio, "elevenlabs:scribe_v2")
        self.assertAlmostEqual(got.sure, float(np.exp(-0.2)), places=4)
        url, kw = self.asked[0]
        self.assertEqual(url, "https://api.elevenlabs.io/v1/speech-to-text")
        self.assertEqual(kw["data"], {"model_id": "scribe_v2", "tag_audio_events": "false", "language_code": "en"})

    def test_assemblyai_in_one_request(self):
        with self.post(Reply(body={"text": "Open Spotify.", "confidence": 0.93})):
            got = hearing.transcribe(self.audio, "assemblyai:universal-3-5-pro/en-hi")
        self.assertEqual((got.text, got.sure), ("Open Spotify.", 0.93))
        url, kw = self.asked[0]
        self.assertEqual(url, "https://sync.assemblyai.com/v1/transcribe")
        self.assertEqual(kw["headers"], {"Authorization": "aai-key", "X-AAI-Model": "universal-3-5-pro"})
        self.assertEqual(kw["files"]["config"][1], json.dumps({"language_codes": ["en", "hi"]}))
        self.assertEqual(kw["files"]["audio"][2], "audio/wav")

    def test_deepgram_nova_3(self):
        body = {"results": {"channels": [{"alternatives": [{"transcript": "pause the music", "confidence": 0.88}]}]}}
        with self.post(Reply(body=body)):
            got = hearing.transcribe(self.audio, "deepgram:nova-3/multi")
        self.assertEqual((got.text, got.sure), ("pause the music", 0.88))
        url, kw = self.asked[0]
        self.assertEqual(url, "https://api.deepgram.com/v1/listen")
        self.assertEqual(kw["params"], {"model": "nova-3", "language": "multi", "smart_format": "true",
                                        "keyterm": ["Harry", "Hari"]})
        self.assertEqual(kw["headers"], {"Authorization": "Token dg-key", "Content-Type": "audio/wav"})

    def test_a_providers_reason_when_it_cant(self):
        with self.post(Reply(401, {"error": {"message": "Invalid API key"}})):
            with self.assertRaisesRegex(RuntimeError, "Sarvam: 401 Invalid API key"):
                hearing.transcribe(self.audio, "sarvam:saaras:v4")

    def test_asked_only_when_picked_with_audio_to_send(self):
        self.assertIsNone(hearing.ask(self.audio, "commands"))  # nothing picked
        self.saved["ears"] = "deepgram:nova-3"
        self.assertIsNone(hearing.ask(None, "commands"))
        self.assertIsNone(hearing.ask(self.audio[:800], "commands"))  # 50 ms: nothing to hear
        with mock.patch.object(hearing, "transcribe", lambda audio, value: hearing.Got("hi", None, 5)):
            asked = hearing.ask(self.audio, "commands")
            self.assertEqual(asked.words(), hearing.Got("hi", None, 5))
        self.assertEqual(asked.name, "Deepgram")

    def test_in_time_or_not_at_all(self):
        self.saved["ears"] = "sarvam:saaras:v4"
        gate = threading.Event()

        def slow(audio, value):
            gate.wait(5)
            return hearing.Got("too late", None, 2000)
        with mock.patch.object(hearing, "transcribe", slow):
            asked = hearing.ask(self.audio, "commands")
            t = time.time()
            self.assertIsNone(asked.words(until=time.time() + 0.2))
            self.assertLess(time.time() - t, 1.0)
            gate.set()
        with mock.patch.object(hearing, "transcribe", lambda a, v: (_ for _ in ()).throw(requests.ConnectionError())):
            self.assertIsNone(hearing.ask(self.audio, "commands").words())
        with mock.patch.object(hearing, "transcribe", lambda a, v: hearing.Got(" . ", None, 5)):
            self.assertIsNone(hearing.ask(self.audio, "commands").words())  # nothing in it


class FakeAsked:
    def __init__(self, text, sure=None, ms=420, name="Sarvam"):
        self.got, self.name = (hearing.Got(text, sure, ms) if text is not None else None), name

    def words(self, until=None):
        return self.got


class Taken(unittest.TestCase):
    """A turn she's taken, in the provider's words; what she decided about it stands."""

    def test_the_providers_words_for_a_named_turn(self):
        pc = speech.heard("Hey Harry, open you tube", 0.62)
        what = siri.route(pc, "other")
        got, ms = siri.heard_better(what, pc, "other", False, 300, FakeAsked("Hey Harry, open YouTube.", 0.95))
        self.assertEqual(str(got[1]).strip(" ."), "open YouTube")
        self.assertEqual(got[2], what[2])  # her decision stands
        self.assertEqual(ms, 720)
        self.assertAlmostEqual(got[0].sure, 0.95)

    def test_words_that_ask_her_nothing_leave_the_pcs(self):
        pc = speech.heard("Hey Harry, what's the time", 0.9)
        what = siri.route(pc, "other")
        for heard in ("Hey Harry", "", None):
            with self.subTest(heard):
                asked = FakeAsked(heard) if heard is not None else None
                self.assertEqual(siri.heard_better(what, pc, "other", False, 300, asked)[0], what)

    def test_a_follow_up_keeps_its_gate(self):
        pc = speech.heard("and tomorrow", 0.7)
        what = siri.route(pc, "follow_up")
        got, _ = siri.heard_better(what, pc, "follow_up", False, 200, FakeAsked("And tomorrow?"))
        self.assertEqual((got[1], got[2]), ("And tomorrow?", what[2]))
        self.assertAlmostEqual(got[0].sure, 0.7)  # it didn't say how sure: the PC's stands

    def test_nothing_sent_when_none_are_picked(self):
        pc = speech.heard("Hey Harry, open Notepad", 0.9)
        pc.audio = np.zeros(16000, np.float32)
        what = siri.route(pc, "other")
        with mock.patch.object(hearing, "wanted", lambda what: False), \
                mock.patch.object(hearing, "transcribe", side_effect=AssertionError("sent")):
            self.assertEqual(siri.heard_better(what, pc, "other", False, 100), (what, 100))

    def test_dictation_in_the_providers_words_the_stop_phrase_still_off(self):
        stop = siri.Dictation(lambda: siri.NAMES).stop_rx
        heard = [speech.heard("dear sir i am writing"), speech.heard("about the meating"),
                 speech.heard("thanks stop transcribing")]
        heard[0].asked, heard[1].asked = FakeAsked("Dear Sir, I am writing"), FakeAsked("about the meeting.")
        heard[2].asked = FakeAsked("Thanks.")  # its stop phrase went missing: the PC's words stay for the last
        self.assertEqual(siri.dictated_better(heard, stop, time.time()), 2)
        self.assertEqual(heard, ["Dear Sir, I am writing", "about the meeting.", "thanks stop transcribing"])
        heard[2].asked = FakeAsked("Thanks. Stop transcribing.")
        self.assertEqual(siri.dictated_better(heard, stop, time.time()), 1)
        self.assertEqual(heard[2], "Thanks. Stop transcribing.")


class Pickers(unittest.TestCase):
    """What Settings' pickers list, without the window."""

    def test_her_voices_and_ears(self):
        app = SimpleNamespace()
        voice = assistant_ui.VoiceSource(app)
        self.assertEqual([g.id for g in voice.groups], ["pc", "fish", "elevenlabs", "sarvam", "deepgram"])
        rows = voice.rows(voice.groups[3])
        self.assertIn("sarvam:bulbul:v3/shubh", [r["value"] for r in rows])
        typed = voice.typed("https://fish.audio/m/9a9cf47702da476aa4629e2506d4a857/")
        self.assertEqual(typed[0]["value"], "9a9cf47702da476aa4629e2506d4a857")
        self.assertEqual(voice.group_of("deepgram:aura-2-luna-en"), "deepgram")
        self.assertEqual(voice.group_of("pocket:p248"), "pc")
        ears = assistant_ui.EarsSource(app)
        values = [r["value"] for g in ears.groups for r in ears.rows(g)]
        self.assertEqual(values[:3], ["pc:parakeet", "pc:nemotron", "pc:whisper"])
        self.assertTrue(all(hearing.parse(v) for v in values[3:]))
        self.assertEqual(len(values), 3 + sum(len(m) for m in hearing.MODELS.values()))


if __name__ == "__main__":
    unittest.main()
