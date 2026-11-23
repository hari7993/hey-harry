"""Her memory kept small (20 November 2026, the owner: she took 1,000 to 2,000 MB). Parakeet's weights are mapped from
a file rather than copied into her (speech.mapped_encoder, _parakeet), a long turn is heard in pieces so ONNX
Runtime's working memory stays that of 10 seconds (speech.in_pieces), and numpy's OpenBLAS starts on one thread
(winplatform). Nothing here loads a model: the recognizer is a stand-in."""
import os
import tempfile
import threading
import types
import unittest
from unittest import mock

import numpy as np

from tests.support import siri  # noqa: F401  first: temp APPDATA and the tripwires

import speech


class Pieces(unittest.TestCase):
    def tone(self, secs, loud=0.3):
        return (np.sin(np.arange(int(secs * speech.RATE)) * 0.05) * loud).astype(np.float32)

    def test_a_command_is_heard_whole(self):
        audio = self.tone(7.5)
        got = speech.in_pieces(audio)
        self.assertEqual(len(got), 1)
        self.assertTrue(np.array_equal(got[0], audio))

    def test_a_long_turn_is_cut_at_its_pauses_and_nothing_is_lost(self):
        quiet = np.zeros(int(0.5 * speech.RATE), np.float32)
        audio = np.concatenate([self.tone(6.0), quiet, self.tone(6.5), quiet, self.tone(5.5), quiet, self.tone(4.0)])
        got = speech.in_pieces(audio)
        self.assertTrue(np.array_equal(np.concatenate(got), audio))
        self.assertTrue(all(len(p) <= speech.PIECE_MOST * speech.RATE for p in got), [len(p) for p in got])
        self.assertTrue(all(len(p) >= speech.RATE for p in got))
        for piece in got[:-1]:  # each cut falls in a pause: the piece ends in quiet
            self.assertLess(float(np.abs(piece[-speech.RATE // 20:]).max()), 0.01)

    def test_talk_with_no_pause_is_still_cut_and_the_last_piece_is_never_tiny(self):
        got = speech.in_pieces(self.tone(8.4))
        self.assertEqual(len(got), 2)
        self.assertGreaterEqual(len(got[1]), speech.RATE)
        self.assertLessEqual(len(got[0]), speech.PIECE_MOST * speech.RATE)

    def test_the_pieces_words_are_joined_and_her_sureness_is_over_them_all(self):
        seen = []

        class Stream:
            def accept_waveform(self, rate, audio):
                self.n = len(audio)
                seen.append(len(audio) / rate)
                self.result = types.SimpleNamespace(text=f" piece{len(seen)} ", ys_log_probs=[np.log(0.5)])

        rec = types.SimpleNamespace(create_stream=Stream, decode_stream=lambda s: None)
        quiet = types.SimpleNamespace(Thread=lambda **kw: types.SimpleNamespace(start=lambda: None),
                                      Lock=threading.Lock)
        with (mock.patch.object(speech, "model_path", lambda *a: "x"),
              mock.patch.object(speech, "_parakeet", lambda d, notify=None: rec),
              mock.patch.object(speech, "threading", quiet)):  # its warm-up at the start isn't this test's
            text, ms = speech.transcriber("parakeet")(self.tone(25))
        self.assertGreaterEqual(len(seen), 3)
        self.assertEqual(str(text), " ".join(f"piece{i}" for i in range(1, len(seen) + 1)))
        self.assertAlmostEqual(text.sure, 0.5, places=3)
        self.assertTrue(all(s <= speech.PIECE_MOST for s in seen), seen)


class MappedEncoder(unittest.TestCase):
    def test_no_room_or_no_onnxruntime_and_the_old_way_is_used(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "encoder.int8.onnx"), "wb").write(b"not a model")
            with mock.patch.object(speech.shutil, "disk_usage", lambda p: types.SimpleNamespace(free=10 ** 6)):
                self.assertIsNone(speech.mapped_encoder(d))
            self.assertIsNone(speech.mapped_encoder(d))  # ONNX Runtime won't read it: said, and None
            self.assertFalse(os.path.exists(os.path.join(d, speech.MAPPED, "made.json")))

    def test_a_mapped_encoder_that_wont_load_falls_back_and_is_made_again_next_time(self):
        loaded = []

        def from_transducer(encoder, **kw):
            loaded.append((os.path.basename(encoder), os.path.basename(os.getcwd())))
            if "mapped" in encoder:
                raise RuntimeError("cut short")
            return "recognizer"
        fake = types.SimpleNamespace(OfflineRecognizer=types.SimpleNamespace(from_transducer=from_transducer))
        was = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            folder = os.path.join(d, speech.MAPPED)
            os.makedirs(folder)
            open(os.path.join(folder, "made.json"), "w").write("{}")
            with mock.patch.dict("sys.modules", {"sherpa_onnx": fake}), \
                    mock.patch.object(speech, "mapped_encoder", lambda d, notify=None: folder):
                self.assertEqual(speech._parakeet(d), "recognizer")
            self.assertEqual(loaded, [("encoder.onnx", speech.MAPPED), ("encoder.int8.onnx", os.path.basename(was))])
            self.assertFalse(os.path.exists(os.path.join(folder, "made.json")))
        self.assertEqual(os.getcwd(), was)  # and she's back in her own folder either way


class OneThread(unittest.TestCase):
    def test_numpys_threads_are_said_before_anything_imports_it(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "winplatform.py"),
                   encoding="utf-8").read()
        said = src.index('os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")')
        self.assertLess(said, src.index("import asyncio"))
        self.assertFalse([line for line in src[:said].splitlines() if line.startswith(("import ", "from "))
                          and line != "import os"])


if __name__ == "__main__":
    unittest.main()
