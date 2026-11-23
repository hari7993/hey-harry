"""Her voice on this PC is tiny-voca (voca.py, 20 November 2026, the owner's ask, in Woof's place): text read a
sentence at a time by tiny-voca's own rules, a sentence too long for the model cut smaller, a stop heard between
sentences, a voice saved before (Woof's, Kokoro's, Pocket's) read as hers now, its files fetched at the versions that
were read and each checked before it's used or run, and names said as Settings has them. Nothing's downloaded here and
no model is loaded: the model and its phonemizer are stand-ins."""
import os
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

import numpy as np

from tests.support import ORIGINAL, siri  # noqa: F401  first: temp APPDATA and the tripwires, before anything of hers

import settings
import voca


class Sentences(unittest.TestCase):
    def test_a_sentence_at_a_time_and_none_broken_after_a_title_or_inside_a_number(self):
        self.assertEqual(voca.sentences("Sure. Opening Notepad."), ["Sure.", "Opening Notepad."])
        self.assertEqual(voca.sentences("Dr. Sharma is here. He said hi! Okay"),
                         ["Dr. Sharma is here.", "He said hi!", "Okay."])
        self.assertEqual(voca.sentences("Only 3.7 gigabytes left at 5 p.m. today."),
                         ["Only 3.7 gigabytes left at 5 p.m. today."])

    def test_nothing_said_is_nothing_made(self):
        self.assertEqual(voca.sentences("  "), [])
        self.assertEqual(voca.sentences("... !"), [])

    def test_a_line_with_no_mark_gets_a_full_stop_so_its_last_word_doesnt_break_off(self):
        self.assertEqual(voca.finished("Okay"), "Okay.")
        self.assertEqual(voca.finished("Okay,"), "Okay,")
        self.assertEqual(voca.finished('She said "go!"'), 'She said "go!"')
        self.assertEqual(voca.finished("  "), "")

    def test_a_sentence_too_long_is_cut_at_its_commas_then_in_two(self):
        self.assertEqual(voca.shorter("meet with Sam, update the engine, and call"),
                         ["meet with Sam,", "update the engine,", "and call"])
        self.assertEqual(voca.shorter("one two three four five"), ["one two three", "four five"])
        self.assertEqual(voca.shorter("supercalifragilistic"), [])


class Voices(unittest.TestCase):
    def test_a_voice_saved_before_is_hers_now(self):
        for old in ("woof:juno", "pocket:p248", "kokoro:af_heart", "kokoro:hf_alpha"):
            self.assertEqual(siri.voice_id(old), "voca:F2", old)
        self.assertEqual(siri.voice_id("voca:F2"), "voca:F2")
        self.assertEqual(siri.voice_id("voca:M2"), "voca:M2")
        self.assertEqual(siri.voice_name("voca:M2"), "her voice on this PC")

    def test_its_two_are_the_only_ones_on_this_pc_in_settings(self):
        on_pc = [v for _, v, _ in settings.VOICES if not __import__("re").fullmatch(r"[0-9a-f]{32}", v)]
        self.assertEqual(on_pc, ["voca:F2", "voca:M2"])  # no Woof, no Kokoro, no Pocket, no Windows voices offered
        self.assertEqual(sorted(voca.VOICES), ["F2", "M2"])
        self.assertIn(voca.DEFAULT, voca.VOICES)

    def test_who_made_it_is_shown_where_its_picked(self):
        import assistant_ui
        rows = assistant_ui.VoiceSource.rows(SimpleSource(), SimpleGroup("pc"))
        self.assertEqual([r["value"] for r in rows], ["voca:F2", "voca:M2"])
        self.assertTrue(all(r["cols"][1] == voca.CREDIT for r in rows))

    def test_a_voice_saved_before_is_shown_as_hers_in_settings(self):
        import assistant_ui
        for saved, shown in (("woof:juno", "voca:F2"), ("kokoro:af_heart", "voca:F2"), ("voca:M2", "voca:M2"),
                             (None, settings.VOICES[0][1])):
            with mock.patch.object(settings, "get", lambda name, saved=saved: saved if name == "voice" else None):
                self.assertEqual(assistant_ui.saved_voice(), shown, saved)
                self.assertEqual(assistant_ui.VoiceSource.current(SimpleSource()), shown)


class SimpleSource:
    pass


class SimpleGroup:
    def __init__(self, gid):
        self.id = gid


class Names(unittest.TestCase):
    def test_a_name_is_said_as_settings_has_it_whole_words_only(self):
        self.addCleanup(settings.put, "voice_say_as", None)
        settings.put("voice_say_as", {"Saoirse": "Seersha", "Al": "Al"})
        self.assertEqual(voca.said_as("Saoirse said hi to Saoirsea."), "Seersha said hi to Saoirsea.")
        settings.put("voice_say_as", {})
        self.assertEqual(voca.said_as("Saoirse"), "Saoirse")


class TheModel(unittest.TestCase):
    """voca.Voice with a stand-in phonemizer (40 phonemes a letter, so a short text is "long") and a stand-in model."""

    def voice(self, loud=0.5):
        asked = []

        def phonemize(text):
            if not any(c.isalnum() for c in text):
                raise ValueError("nothing to pronounce")
            return types.SimpleNamespace(ids=[1] * (40 * len(text)), stress=[0] * (40 * len(text)))

        def run(names, feeds, options):
            asked.append(feeds)
            return [np.full((1, 100), loud, np.float32)]
        return voca.Voice(types.SimpleNamespace(phonemize=phonemize), types.SimpleNamespace(run=run), None), asked

    def test_the_voice_asked_for_and_hers_for_one_it_doesnt_have(self):
        voice, asked = self.voice()
        for name in ("M2", "m2", "F2", "juno"):
            self.assertEqual(len(voice("Okay.", name)), 100)
        self.assertEqual([int(f["voice"][0]) for f in asked], [1, 1, 0, 0])
        self.assertEqual(asked[0]["tokens"].shape, (1, 200))
        self.assertEqual(asked[0]["stress"].shape, (1, 200))

    def test_nothing_to_pronounce_is_no_sound_and_the_model_isnt_asked(self):
        voice, asked = self.voice()
        self.assertEqual(len(voice("...")), 0)
        self.assertEqual(asked, [])

    def test_a_sentence_too_long_for_one_go_is_made_in_smaller_ones(self):
        voice, asked = self.voice()
        audio = voice("aaaa bbbb cccc, dddd eeee")  # 1,000 phonemes: its clauses, the first still too long, in two
        self.assertEqual(len(asked), 3)
        self.assertEqual(len(audio), 300)
        self.assertTrue(all(f["tokens"].shape[1] <= voca.MOST for f in asked))
        self.assertEqual(len(voice("a" * 20)), 0)  # one word too long to say: left out, never an error
        self.assertEqual(len(asked), 3)

    def test_a_sound_louder_than_full_is_brought_under_it(self):
        voice, _ = self.voice(loud=1.6)
        self.assertAlmostEqual(float(np.abs(voice("Okay.")).max()), voca.PEAK, places=5)
        voice, _ = self.voice(loud=0.5)
        self.assertAlmostEqual(float(np.abs(voice("Okay.")).max()), 0.5, places=5)  # a quiet one left as it is


class Making(unittest.TestCase):
    def engine(self, made):
        class TTS:
            def __call__(self, text, voice=None):
                made.append((text, voice))
                return np.ones(10, np.float32)
        engine = voca.Engine.__new__(voca.Engine)
        engine.tts, engine.used, engine.lock = TTS(), 0.0, threading.Lock()
        engine.turns, engine.live = threading.Condition(), 0
        return engine

    def setUp(self):
        patch = mock.patch.object(voca, "_held", [0.0])
        patch.start()
        self.addCleanup(patch.stop)

    def test_each_sentence_played_as_its_made_in_the_voice_asked_for(self):
        made, heard = [], []
        audio = self.engine(made).make("Sure. Opening Notepad. Done", "M2", heard.append)
        self.assertEqual(made, [("Sure.", "M2"), ("Opening Notepad.", "M2"), ("Done.", "M2")])
        self.assertEqual(len(heard), 3)
        self.assertEqual(len(audio), 30)

    def test_a_stop_is_heard_between_sentences(self):
        made, heard = [], []
        self.engine(made).make("One thing. Another thing. And a third.", on_audio=heard.append,
                               stop=lambda: len(made) >= 1)
        self.assertEqual(len(made), 1)
        self.assertEqual(heard, [])  # stopped once the first was made, so not even that one played

    def test_a_line_stopped_before_its_turn_isnt_made(self):
        made = []
        self.assertEqual(len(self.engine(made).make("One thing.", stop=lambda: True)), 0)
        self.assertEqual(made, [])

    def test_names_are_said_as_settings_has_them(self):
        self.addCleanup(settings.put, "voice_say_as", None)
        settings.put("voice_say_as", {"Saoirse": "Seersha"})
        made = []
        self.engine(made).make("Hi Saoirse.")
        self.assertEqual([text for text, _ in made], ["Hi Seersha."])

    def test_the_quiet_a_piece_starts_with_is_cut(self):
        audio = np.concatenate([np.zeros(int(0.3 * voca.RATE), np.float32), np.full(100, 0.5, np.float32)])
        self.assertEqual(len(voca.lead_trimmed(audio)), int(voca.LEAD * voca.RATE) + 100)
        self.assertEqual(len(voca.lead_trimmed(np.zeros(50, np.float32))), 50)  # no sound: left as it is

    def test_a_line_made_ahead_gives_way_to_what_shes_saying(self):
        """9 November 2026: her replies, made again for the cache in her voice then, held "Hi! What can I do for
        you?" up 3 s."""
        made, first_going, let_go = [], threading.Event(), threading.Event()
        engine = self.engine(made)
        say = engine.tts.__call__

        def slow_first(text, voice=None):
            if text.startswith("Hi"):
                first_going.set()
                let_go.wait(2)
            return say(text, voice)
        engine.tts = slow_first
        saying = threading.Thread(target=engine.make, args=("Hi! What can I do for you?",))
        saying.start()
        self.assertTrue(first_going.wait(2))
        ahead = threading.Thread(target=engine.make, args=("Opening Notepad.",), kwargs={"ahead": True})
        ahead.start()
        then = threading.Thread(target=engine.make, args=("Sure thing.",))  # asked for while the first is made
        then.start()
        end = time.time() + 2
        while engine.live < 2 and time.time() < end:
            time.sleep(0.01)
        let_go.set()
        for thread in (saying, ahead, then):
            thread.join(3)
        self.assertEqual([text for text, _ in made],
                         ["Hi!", "What can I do for you?", "Sure thing.", "Opening Notepad."])

    def test_a_line_made_ahead_waits_while_someone_talks(self):
        made = []
        voca.hold(0.3)
        t = time.time()
        self.engine(made).make("Opening Notepad.", ahead=True)
        self.assertGreaterEqual(time.time() - t, 0.25)
        self.assertEqual([text for text, _ in made], ["Opening Notepad."])

    def test_her_replies_are_made_ahead(self):
        asked = []
        with mock.patch.object(settings, "get", lambda name: "voca:F2" if name == "voice"
                               else settings.DEFAULTS.get(name)), \
                mock.patch.object(siri, "CACHE_DIR", tempfile.mkdtemp()), \
                mock.patch.object(siri, "fetch_tts", lambda line, voice=None, ahead=False:
                                  asked.append((line, voice, ahead)) or ("made.wav", 5, False)), \
                mock.patch.object(siri, "all_scripted_lines", lambda: iter(["Okay.", "On it."])):
            ORIGINAL["warm_cache"]()
        self.assertEqual(asked, [("Okay.", "voca:F2", True), ("On it.", "voca:F2", True)])

    def test_stream_ends_with_none(self):
        engine = self.engine([])
        with mock.patch.object(voca, "engine", lambda: engine):
            q = voca.stream("Done.")
            got = [q.get(timeout=2), q.get(timeout=2)]
        self.assertIsNone(got[1])
        self.assertEqual(len(got[0]), 10)

    def test_a_voice_that_fails_puts_its_error_on_the_stream(self):
        engine = self.engine([])
        engine.tts = lambda text, voice=None: (_ for _ in ()).throw(RuntimeError("no model"))
        with mock.patch.object(voca, "engine", lambda: engine):
            self.assertIsInstance(voca.stream("Done.").get(timeout=2), RuntimeError)


class Files(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        patch = mock.patch.object(voca.speech, "models_dir", lambda: self.dir)
        patch.start()
        self.addCleanup(patch.stop)

    def fake_files(self, body=b"x"):
        """Its files as made up here, and FILES as their hashes."""
        digests = {}
        for name in voca.FILES:
            path = os.path.join(voca.folder(), name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(body + name.encode())
            digests[name] = voca._sha256(path)
        return digests

    def test_not_there_until_its_downloaded(self):
        self.assertFalse(voca.available())
        self.fake_files()
        self.assertTrue(voca.available())

    def test_each_file_comes_from_the_version_that_was_read(self):
        self.assertEqual(voca.url("model/onnx/model.onnx"),
                         "https://huggingface.co/n4ze3m/tiny-voca/resolve/" + voca.MODEL + "/onnx/model.onnx")
        self.assertEqual(voca.url("code/dizione/data/units.txt"), "https://raw.githubusercontent.com/n4ze3m/dizione/"
                         + voca.CODE + "/src/dizione/data/units.txt")
        self.assertEqual(voca.url("code/LICENSE"),
                         "https://raw.githubusercontent.com/n4ze3m/dizione/" + voca.CODE + "/LICENSE")
        for name in voca.FILES:  # none from a branch that can move: a full commit each
            self.assertTrue(voca.MODEL in voca.url(name) or voca.CODE in voca.url(name), name)
        self.assertEqual(len(voca.MODEL), 40)
        self.assertEqual(len(voca.CODE), 40)

    def test_a_file_that_doesnt_match_is_thrown_away(self):
        def download(url, path):
            with open(path, "wb") as f:
                f.write(b"not what was read")
        with mock.patch.object(voca.urllib.request, "urlretrieve", side_effect=download):
            with self.assertRaises(RuntimeError):
                voca.fetch()
        leftover = [n for _, _, names in os.walk(self.dir) for n in names]
        self.assertEqual(leftover, [])  # nothing kept from a bad download, not even its .part

    def test_what_has_changed_on_disk_is_never_run(self):
        digests = self.fake_files()
        with mock.patch.dict(voca.FILES, digests), mock.patch.dict(voca.sys.modules):
            voca.sys.modules.pop("dizione", None)
            with open(os.path.join(voca.folder(), "code", "dizione", "engine.py"), "ab") as f:
                f.write(b"\nprint('changed')\n")
            with self.assertRaises(RuntimeError):
                voca._module(voca.folder())
            self.assertNotIn("dizione", voca.sys.modules)


if __name__ == "__main__":
    unittest.main()
