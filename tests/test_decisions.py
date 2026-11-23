"""Was that for her? asked of Gemini Decision (decisions.py, 18 November 2026) for words said without her name that her
decider gave little chance, before the model is asked with her whole prompt: a sure no and she stays quiet, anything
else and the model decides as before. Nothing goes online here."""
import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.support import siri  # noqa: F401  first: temp APPDATA and the tripwires, before anything of hers

import decisions

ROOM = "we went to the market yesterday and it was so crowded"


class Asking(unittest.TestCase):
    def ask(self, answer=0.03, her_line=None, now=100.0):
        sent = []

        def post(url, json=None, headers=None, timeout=None):
            sent.append(SimpleNamespace(url=url, body=json, headers=headers, timeout=timeout))
            return SimpleNamespace(raise_for_status=lambda: None,
                                   json=lambda: {"answers": {"for_her": {"type": "noul", "noul": answer}}})
        with mock.patch.object(decisions, "get_secret", lambda name: "test-key"), \
                mock.patch.object(decisions.HTTP, "post", post), contextlib.redirect_stdout(io.StringIO()):
            got = decisions.chance_for_her(ROOM, her_line, now)
        return got, sent

    def test_a_yes_or_no_question_with_the_key_in_a_header_never_the_address(self):
        got, sent = self.ask()
        self.assertEqual(got, 0.03)
        call = sent[0]
        self.assertEqual(call.url, decisions.URL)
        self.assertNotIn("test-key", call.url)
        self.assertEqual(call.headers, {"x-goog-api-key": "test-key"})
        self.assertEqual(call.body["model"], "gemini-decision-1")
        self.assertEqual(call.body["questions"]["for_her"]["type"], "noul")
        self.assertIn(ROOM, call.body["input"])

    def test_her_last_line_goes_with_it_only_if_its_recent(self):
        _, sent = self.ask(her_line=(90.0, "Night light's on."), now=100.0)
        self.assertIn("Night light's on.", sent[0].body["input"])
        _, sent = self.ask(her_line=(10.0, "Night light's on."), now=100.0)
        self.assertNotIn("Night light's on.", sent[0].body["input"])

    def test_no_key_nothing_sent_and_a_failure_is_no_answer(self):
        with mock.patch.object(decisions, "get_secret", lambda name: None), \
                mock.patch.object(decisions.HTTP, "post", side_effect=AssertionError("sent")):
            self.assertIsNone(decisions.chance_for_her(ROOM))

        def down(*args, **kw):
            raise decisions.requests.ConnectionError("no network")
        with mock.patch.object(decisions, "get_secret", lambda name: "test-key"), \
                mock.patch.object(decisions.HTTP, "post", down), contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(decisions.chance_for_her(ROOM))

    def test_off_in_settings_or_with_no_key_it_isnt_asked(self):
        with mock.patch.object(decisions, "get_secret", lambda name: "test-key"):
            with mock.patch.object(decisions.settings, "get", lambda name: False if name == "gemini_decides" else None):
                self.assertFalse(decisions.available())
            self.assertTrue(decisions.available())
        with mock.patch.object(decisions, "get_secret", lambda name: None):
            self.assertFalse(decisions.available())


class InHerTurn(unittest.TestCase):
    def setUp(self):
        self.asked = []
        for patch in (mock.patch.object(siri.decisions, "available", lambda: True),
                      mock.patch.object(siri, "JUDGED", [(0.05, None)]), mock.patch.object(siri, "AGAIN", [None])):
            patch.start()
            self.addCleanup(patch.stop)

    def gemini(self, p):
        return mock.patch.object(siri.decisions, "chance_for_her",
                                 lambda words, her_line=None: self.asked.append(words) or p)

    def test_a_sure_no_and_the_model_isnt_asked(self):
        with self.gemini(0.03), mock.patch.object(siri, "think", side_effect=AssertionError("asked the model")), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(siri.handle(ROOM, gate="cold"))
        self.assertEqual(self.asked, [ROOM])

    def test_anything_less_than_sure_goes_to_the_model_as_before(self):
        for p in (0.5, 0.9, None):
            thought = []
            with self.gemini(p), mock.patch.object(siri, "think", lambda *a, **kw: thought.append(a[0]) or None), \
                    contextlib.redirect_stdout(io.StringIO()):
                siri.handle(ROOM, gate="cold")
            self.assertEqual(thought, [ROOM], p)

    def test_asked_only_for_what_the_decider_gave_little_chance(self):
        with self.gemini(0.01):
            self.assertTrue(siri.not_for_her(ROOM))
            siri.JUDGED[0] = (decisions.LEAN, None)
            self.assertFalse(siri.not_for_her(ROOM))
            siri.JUDGED[0] = None  # said with her name, or right after her answer
            self.assertFalse(siri.not_for_her(ROOM))
        self.assertEqual(self.asked, [ROOM])

    def test_never_for_what_asks_something_or_is_said_again(self):
        with self.gemini(0.01):
            self.assertFalse(siri.not_for_her("open notepad"))
            self.assertFalse(siri.not_for_her("hey there, play some music"))
            siri.AGAIN[0] = ["we went to the market"]
            self.assertFalse(siri.not_for_her(ROOM))
        self.assertEqual(self.asked, [])


if __name__ == "__main__":
    unittest.main()
