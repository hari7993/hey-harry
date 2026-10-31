"""Her voice on this PC is Kokoro's (kokoro.py, 31 October 2026, the owner's ask: in Pocket TTS's place, first on the
Open TTS Leaderboard): a long sentence made a clause at a time so she starts sooner, a Pocket voice saved before
read as Kokoro's, and a stop heard between pieces."""
import tempfile
import threading
import types
import unittest
from unittest import mock

import numpy as np

from tests.support import siri  # noqa: F401  first: temp APPDATA and the tripwires, before anything of hers

import kokoro
import settings


class Pieces(unittest.TestCase):
    def test_short_sentences_whole_and_a_long_one_by_its_clauses(self):
        self.assertEqual(kokoro.pieces("Sure. Opening Notepad."), ["Sure.", "Opening Notepad."])
        self.assertEqual(kokoro.pieces("You've got four things to do: meet with Sam, update the test engine, "
                                       "and call the clients."),
                         ["You've got four things to do:", "meet with Sam,", "update the test engine,",
                          "and call the clients."])

    def test_no_clause_left_too_short_to_say_alone(self):
        got = kokoro.pieces("Okay, so here is what I found on the weather for today, love.")
        self.assertTrue(all(len(p) >= 12 for p in got), got)
        self.assertEqual(" ".join(got), "Okay, so here is what I found on the weather for today, love.")

    def test_nothing_said_is_nothing_made(self):
        self.assertEqual(kokoro.pieces("  "), [])


class Voices(unittest.TestCase):
    def test_a_pocket_voice_saved_before_is_kokoros_now(self):
        self.assertEqual(siri.voice_id("pocket:p248"), "kokoro:af_heart")
        self.assertEqual(siri.voice_id("pocket:p251"), "kokoro:am_michael")
        self.assertEqual(siri.voice_id("kokoro:hf_alpha"), "kokoro:hf_alpha")

    def test_each_offered_in_settings_is_one_it_has(self):
        offered = [v.split(":", 1)[1] for _, v, _ in settings.VOICES if v.startswith("kokoro:")]
        self.assertIn(kokoro.DEFAULT, offered)
        self.assertTrue(all(v in kokoro.VOICES for v in offered))
        self.assertFalse([v for _, v, _ in settings.VOICES if v.startswith("pocket:")])


class Making(unittest.TestCase):
    def engine(self, made):
        class TTS:
            def generate(self, text, sid=0):
                made.append((text, sid))
                return types.SimpleNamespace(samples=np.ones(10, np.float32))
        engine = kokoro.Engine.__new__(kokoro.Engine)
        engine.tts, engine.used, engine.lock = TTS(), 0.0, threading.Lock()
        return engine

    def test_each_piece_played_as_its_made_in_the_voice_asked(self):
        made, heard = [], []
        audio = self.engine(made).make("You've got four things to do: meet with Sam, and call the clients.",
                                       "hf_alpha", heard.append)
        self.assertEqual([sid for _, sid in made], [kokoro.VOICES["hf_alpha"]] * 3)
        self.assertEqual(len(heard), 3)
        self.assertEqual(len(audio), 30)

    def test_a_stop_is_heard_between_pieces(self):
        made, heard = [], []
        self.engine(made).make("You've got four things to do: meet with Sam, and call the clients.",
                               on_audio=heard.append, stop=lambda: len(made) >= 1)
        self.assertEqual(len(made), 1)
        self.assertEqual(heard, [])  # stopped once the first was made, so not even that one played

    def test_stream_ends_with_none(self):
        engine = self.engine([])
        with mock.patch.object(kokoro, "engine", lambda: engine):
            q = kokoro.stream("Done.")
            got = [q.get(timeout=2), q.get(timeout=2)]
        self.assertIsNone(got[1])
        self.assertEqual(len(got[0]), 10)

    def test_not_there_until_its_downloaded(self):
        with tempfile.TemporaryDirectory() as empty, mock.patch.object(kokoro.speech, "models_dir", lambda: empty):
            self.assertFalse(kokoro.available())


if __name__ == "__main__":
    unittest.main()
