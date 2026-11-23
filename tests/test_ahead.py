"""A turn's words written ahead (speech.Listener.AHEAD, 20 November 2026, the owner: hearing is sometimes slow).
Parakeet writes a turn whole, and did it once the turn had ended, after the quiet she waits through. Now it's written
during that quiet, from the very audio it would be given at the end, so the words are the same and there sooner; said
on, it's thrown away and written again. The ears here are stand-ins: no model, no mic. Smart Turn's
stand-in says 90%: finished, but not so sure that the turn ends sooner (Listener.SOON)."""
import threading
import time
import unittest

import numpy as np

from tests.test_listening import BLOCK, RATE, FakeEars, FakeTurn, blocks, listener  # tests.support comes first there

import speech


def feed(ear, *parts):
    """parts: (seconds, 1.0 for speech or 0.0 for quiet). Returns where the last speech ended, in samples."""
    spoken = 0
    for secs, value in parts:
        for block in blocks(secs, value):
            ear.feed(block)
            spoken = ear.pos if value else spoken
    return spoken


def written(ear):
    """Waits for what's being written ahead, if anything is. True if something was."""
    if ear.ahead is None:
        return False
    ear.ahead.result(5)
    return True


class Keeping(FakeEars):
    """Ears that keep every piece of audio they're given to write."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.given = []

    def transcribe(self, audio):
        self.given.append(np.array(audio))
        return super().transcribe(audio)


class WrittenAhead(unittest.TestCase):
    def test_its_written_in_the_quiet_she_waits_through_and_only_once(self):
        ears = FakeEars()
        ear, phrases = listener(ears, turn=FakeTurn(0.9), wait="patient")
        feed(ear, (0.5, 0.0), (1.2, 1.0), (0.2, 0.0))
        self.assertIsNone(ear.ahead)  # not yet: the audio it's given at the end has 0.3 s of the quiet
        feed(ear, (0.2, 0.0))
        self.assertTrue(written(ear))
        self.assertEqual((ears.calls, phrases), (1, []))  # written, and the turn not over yet
        feed(ear, (1.0, 0.0))
        self.assertEqual([p[2] for p in phrases], ["word"])
        self.assertEqual(ears.calls, 1)  # not written again at its end

    def test_its_given_the_very_audio_it_would_be_at_the_end(self):
        heard = []
        for ahead in (speech.Listener.AHEAD, 99.0):  # as she does now, and as she did: only once the turn's over
            ears = Keeping()
            ear, phrases = listener(ears, turn=FakeTurn(0.9), wait="patient")
            ear.AHEAD = ahead
            feed(ear, (0.5, 0.0), (1.2, 1.0), (0.45, 0.0))
            self.assertEqual(written(ear), ahead < 1)
            feed(ear, (1.0, 0.0))
            self.assertEqual((len(phrases), len(ears.given)), (1, 1))
            heard.append(ears.given[0])
        self.assertTrue(np.array_equal(heard[0], heard[1]))
        tail = int(0.3 * RATE)  # the speech and 0.3 s of the quiet after it
        self.assertEqual((float(heard[0][-tail - 1]), float(np.abs(heard[0][-tail:]).max())), (1.0, 0.0))

    def test_said_on_after_the_pause_its_thrown_away_and_written_again(self):
        ears = FakeEars()
        ear, phrases = listener(ears, turn=FakeTurn(0.9), wait="patient")
        feed(ear, (0.5, 0.0), (1.2, 1.0), (0.5, 0.0))
        self.assertTrue(written(ear))
        feed(ear, (0.8, 1.0))
        self.assertIsNone(ear.ahead)  # they went on: what was written is half of it
        feed(ear, (3.0, 0.0))
        self.assertEqual([p[2] for p in phrases], ["word word"])
        self.assertEqual(ears.calls, 2)

    def test_when_smart_turn_thinks_they_havent_finished_it_waits_before_writing(self):
        ears = FakeEars()
        ear, phrases = listener(ears, turn=FakeTurn(0.1), wait="patient")
        feed(ear, (0.5, 0.0), (1.2, 1.0), (0.8, 0.0))
        self.assertFalse(written(ear))  # they most likely go on: nothing written for nothing
        feed(ear, (0.3, 0.0))
        self.assertTrue(written(ear))  # a second of quiet (SETTLE): written now, well before the 2.5 s she waits
        self.assertEqual(phrases, [])
        feed(ear, (2.0, 0.0))
        self.assertEqual((len(phrases), ears.calls), (1, 1))

    def test_a_turn_that_ends_sooner_takes_whats_being_written(self):
        ears = FakeEars()
        ear, phrases = listener(ears, turn=FakeTurn(0.99), wait="patient")  # all but certain: over at 0.4 s (SOON)
        spoken = feed(ear, (0.5, 0.0), (1.2, 1.0), (3.0, 0.0))
        self.assertEqual(([p[2] for p in phrases], ears.calls), (["word"], 1))
        self.assertAlmostEqual((phrases[0][3] - spoken) / RATE, speech.Listener.SOON, delta=0.05)

    def test_a_short_turn_written_as_a_whole_sentence_doesnt_wait_the_full_second(self):
        """"Turn the volume up.": under a second of speech, so Smart Turn isn't asked, and it waited a second."""
        for words, waited in (("Volume up.", 0.7), ("Is it on?", 0.7), ("Hey Harry, open", 1.0), ("Volume up", 1.0)):
            with self.subTest(words=words):
                ears = FakeEars(write=lambda audio, words=words: words)
                ear, phrases = listener(ears, turn=FakeTurn(0.9), wait="patient")
                spoken = feed(ear, (0.5, 0.0), (0.6, 1.0), (3.0, 0.0))
                self.assertEqual(([p[2] for p in phrases], ears.calls), ([words], 1))
                self.assertAlmostEqual((phrases[0][3] - spoken) / RATE, waited, delta=0.05)

    def test_a_short_greeting_still_waits_for_the_rest_full_stop_or_not(self):
        ears = FakeEars(write=lambda audio: "Hello.")
        ear, phrases = listener(ears, turn=FakeTurn(0.9), wait="patient", hold_for=lambda words: "Hello" in str(words))
        spoken = feed(ear, (0.5, 0.0), (0.6, 1.0), (4.0, 0.0))
        self.assertAlmostEqual((phrases[0][3] - spoken) / RATE, speech.Listener.LONGEST, delta=0.05)

    def test_a_short_turn_is_written_once_too(self):
        ears = FakeEars()
        ear, phrases = listener(ears, turn=FakeTurn(0.9), wait="patient")
        feed(ear, (0.5, 0.0), (0.5, 1.0), (3.0, 0.0))  # under a second of speech: Smart Turn isn't asked
        self.assertEqual((len(phrases), ears.calls), (1, 1))

    def test_ears_that_write_as_you_talk_arent_written_ahead(self):
        ears = FakeEars(live=True)
        ear, phrases = listener(ears, turn=FakeTurn(0.9), wait="patient")
        feed(ear, (0.5, 0.0), (1.2, 1.0), (0.5, 0.0))
        self.assertIsNone(ear.ahead)
        feed(ear, (1.0, 0.0))
        self.assertEqual((len(phrases), ears.finished), (1, 1))

    def test_a_quick_wait_ends_before_anythings_written_ahead(self):
        ears = FakeEars()
        ear, phrases = listener(ears, turn=FakeTurn(0.9), wait="quick")
        feed(ear, (0.5, 0.0), (1.2, 1.0), (0.26, 0.0))
        self.assertEqual((len(phrases), ears.calls), (1, 1))  # over at the first pause, written there as before

    def test_if_writing_ahead_fails_its_written_at_the_end(self):
        fails = [RuntimeError("no room")]

        class Failing(FakeEars):
            def transcribe(self, audio):
                if fails:
                    raise fails.pop()
                return super().transcribe(audio)
        ears = Failing()
        ear, phrases = listener(ears, turn=FakeTurn(0.9), wait="patient")
        feed(ear, (0.5, 0.0), (1.2, 1.0), (3.0, 0.0))
        self.assertEqual([p[2] for p in phrases], ["word"])


class HowLongYouWait(unittest.TestCase):
    """ms, in her log as "stt 123ms": how long the words took once the turn was over, which is what's waited."""

    def listener(self, ears):
        took = []
        ear = speech.Listener(type(listener(FakeEars())[0].vad)(), ears,
                              lambda audio, kind, text, ms: took.append(ms), turn=None, wait="patient")
        return ear, took

    def test_nothing_when_the_words_were_there_already(self):
        ears = FakeEars()
        ear, took = self.listener(ears)
        feed(ear, (0.5, 0.0), (1.2, 1.0), (0.5, 0.0))
        self.assertTrue(written(ear))
        feed(ear, (1.0, 0.0))
        self.assertEqual(len(took), 1)
        self.assertLess(took[0], 50)

    def test_only_whats_left_when_theyre_still_being_written(self):
        go, started = threading.Event(), threading.Event()

        class Slow(FakeEars):
            def transcribe(self, audio):
                started.set()
                go.wait(5)
                return super().transcribe(audio)
        ear, took = self.listener(Slow())
        feed(ear, (0.5, 0.0), (1.2, 1.0), (0.5, 0.0))
        self.assertTrue(started.wait(5))
        threading.Timer(0.2, go.set).start()
        t = time.time()
        feed(ear, (1.0, 0.0))  # the turn ends while it's still being written: waited for, not written again
        self.assertGreaterEqual(time.time() - t, 0.15)
        self.assertEqual(len(took), 1)
        self.assertGreaterEqual(took[0], 100)


class TheAudioOfATurn(unittest.TestCase):
    def test_the_quiet_at_its_end_is_left_out_but_for_the_last_bit_to_the_sample(self):
        whole = speech.Whole(lambda audio: (speech.heard(""), 0))
        for block in blocks(2.0, 1.0):
            whole.feed(block)
        total = len(np.concatenate(whole.parts))
        self.assertEqual(len(whole.audio()), total)
        self.assertEqual(len(whole.audio(0.25)), total)
        self.assertEqual(len(whole.audio(0.5)), total - int(0.2 * RATE))
        for quiet_blocks in (10, 11, 22, 40):  # however old the pause: the same place in the audio
            q = quiet_blocks * BLOCK / RATE
            self.assertEqual(total + quiet_blocks * BLOCK - (int(round(q * RATE)) - int(0.3 * RATE)),
                             total + int(0.3 * RATE))
        self.assertEqual(len(speech.Whole(None).audio(1.0)), 0)


if __name__ == "__main__":
    unittest.main()
