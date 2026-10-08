"""Second reality check, parsing and routing: attributes on one line, misheard searches, two durations in a reminder,
and test_open_mic.py's report of the model's time."""
import contextlib
import io
import time
import unittest
from unittest import mock

from tests.support import siri

from tests import test_routing

import speech


class OneLineAttributes(unittest.TestCase):
    """R1: Ling wrote several key=value arguments on one line ending " /", and they ran together."""

    def test_the_lofi_timer_reply(self):
        raw = ('<tool_call>timer\n seconds=300 label="5 min" alert="Hey, your 5-minute timer\'s up." /\n'
               '<tool_call>youtube\n query="lofi music" play=true /')  # as Ling wrote it on 8 October
        self.assertEqual(siri.parse_plan(raw)["steps"], [
            {"do": "timer", "seconds": 300, "label": "5 min", "alert": "Hey, your 5-minute timer's up."},
            {"do": "youtube", "query": "lofi music", "play": True}])

    def test_bare_and_json_values_next_to_others(self):
        self.assertEqual(siri.parse_plan('<tool_call>youtube query=lofi music play=false />')["steps"],
                         [{"do": "youtube", "query": "lofi music", "play": False}])
        self.assertEqual(siri.parse_plan('<tool_call>schedule\nwhen="in 5 minutes" task={"kind": "reminder", '
                                         '"text": "call Mum"} /\n</tool_call>')["steps"],
                         [{"do": "schedule", "when": "in 5 minutes", "task": {"kind": "reminder", "text": "call Mum"}}])

    def test_one_a_line_as_before(self):
        self.assertEqual(siri.parse_plan('<tool_call>web\nquery="who won the 2024 T20 World Cup</arg_value>\n'
                                         '</tool_call>')["steps"], [{"do": "web", "query": "who won the 2024 T20 World Cup"}])
        self.assertEqual(siri.parse_plan('<tool_call>say\ntext="She said "hi" to you"\n</tool_call>')["say"],
                         'She said "hi" to you')  # a quote inside the value, not the end of it
        self.assertEqual(siri.parse_plan('<tool_call>website\nurl=https://example.com/?q=a b\n</tool_call>')["steps"],
                         [{"do": "website", "url": "https://example.com/?q=a b"}])


class TwoDurations(unittest.TestCase):
    """R3: "for 10 minutes in 1 hour" added both up."""

    def test_the_in_part_is_when(self):
        self.assertEqual(siri.parse_duration("remind me to stretch for 10 minutes in 1 hour"), 3600)
        self.assertEqual(siri.parse_reminder("remind me to stretch for 10 minutes in 1 hour"), "stretch for 10 minutes")
        self.assertEqual(siri.parse_duration("remind me after an hour and a half to eat"), 5400)
        self.assertEqual(siri.parse_duration("set a timer for 1 hour 30"), 5400)  # no "in": all of it, as before


class MisheardSearches(test_routing.Routing):
    """R2: a misheard search or video ran on the PC before the model, which puts misheard words right, saw it."""

    def quick(self, words, gate=False, sure=1.0):
        with contextlib.redirect_stdout(io.StringIO()):
            return siri.quick(words, gate, sure) if (gate, sure) != (False, 1.0) else siri.quick(words)

    def test_unsure_words_go_to_the_model(self):
        for words, sure in (("play ten", 0.55), ("search for amount", 0.88), ("play avengers doomshare tyler", 0.8)):
            with self.subTest(words=words):
                self.assertIsNone(self.quick(words, "cold", sure))
                self.assertIsNone(self.quick(words, False, sure))

    def test_spelled_letters_go_to_the_model(self):
        self.assertIsNone(self.quick("search career eye dee on you tube"))
        self.assertIsNone(self.quick("play pee dee eff tutorial"))

    def test_you_tube_is_youtube(self):
        self.assertEqual(self.quick("search lofi beats on you tube")["steps"],
                         [{"do": "youtube", "query": "lofi beats", "play": False}])
        self.assertEqual(self.quick("play lofi beats on you tube")["steps"],
                         [{"do": "youtube", "query": "lofi beats", "play": True}])

    def test_sure_words_stay_on_the_pc(self):
        self.assertEqual(self.quick("search career id", sure=0.96)["steps"],
                         [{"do": "google", "query": "career id", "play": False}])
        self.assertEqual(self.quick("play arijit singh songs", sure=0.95)["steps"],
                         [{"do": "youtube", "query": "arijit singh songs", "play": True}])
        self.assertEqual(self.quick("open notepad", sure=0.6)["steps"][0]["do"], "open")  # a known name, not a query
        with mock.patch.object(siri, "LAST_QUERY", ["lofi"]):  # the last search, not the words heard
            self.assertEqual(self.quick("play the second video", sure=0.75)["steps"],
                             [{"do": "youtube", "query": "lofi", "play": True, "rank": 2}])

    def test_handle_passes_how_sure(self):
        asked, ran, _ = self.handle(speech.heard("play lofi beats", 0.8), False)
        self.assertTrue(asked)
        self.assertIsNone(ran)
        asked, ran, _ = self.handle(speech.heard("play lofi beats", 0.97), False)
        self.assertFalse(asked)
        self.assertEqual(ran["steps"], [{"do": "youtube", "query": "lofi beats", "play": True}])


class OpenMicReport(unittest.TestCase):
    """test_open_mic.py timed whole turns, so phrases settled on the PC in about 0 s pulled the model's average down."""

    def test_only_the_model_is_timed(self):
        import test_open_mic

        def think(words, gate, notify=None, sure=1.0):
            time.sleep(0.4)  # the model's time
            return {"steps": [], "say": "Jon Favreau."}

        def handle(text, words, ms, notify, gate):
            plan = siri.think(words, gate) if str(text) == "Who directed Iron Man" else \
                {"steps": [{"do": dict(test_open_mic.CASES)[str(text)] or "say"}], "say": ""}
            if dict(test_open_mic.CASES)[str(text)] is not None:
                siri.run_plan(plan, notify)

        out = io.StringIO()
        with mock.patch.object(siri, "think", think), mock.patch.object(siri, "handle", handle), \
                mock.patch.object(siri, "route", lambda text, kind, open_mic=False: (text, text, "cold")), \
                mock.patch.object(siri, "run_plan", siri.run_plan), mock.patch.object(siri, "learn_later"), \
                mock.patch.object(siri.win, "call_apps", siri.win.call_apps), \
                mock.patch.object(test_open_mic.history, "add", test_open_mic.history.add), \
                contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit):
                test_open_mic.main()
        report = out.getvalue()
        self.assertRegex(report, r"1 went to the model, which took 0\.[45]s on average")  # 0.0s, over all 20
        self.assertRegex(report, r"'Who directed Iron Man' .* \(want say, model 0\.[45]s\)")
        self.assertIn("the other 19 were settled on this PC", report)


if __name__ == "__main__":
    unittest.main()
