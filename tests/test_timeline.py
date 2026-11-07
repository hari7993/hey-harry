"""What you did on this PC, kept a week (timeline.py, 7 November 2026, the owner: "it needs to tell me what I've
done previously"): what's kept of each window you were in and what never is, old days let go, and what the model is
told when you ask about it, and only then."""
import datetime
import os
import re
import shutil
import tempfile
import time
import unittest
from unittest import mock

from tests.support import siri  # noqa: F401  her sandbox and tripwires first
import timeline


def visit(start, secs, **kw):
    return {"from": start, "to": start + secs, "app": "Chrome", "title": "Inbox - Gmail", "site": "mail.google.com",
            "words": "Inbox · Lunch on Friday?", "clicks": ["Compose"], "private": False, **kw}


def at(day, hour, minute=0):
    return time.mktime(datetime.datetime(*day, hour, minute).timetuple())


def asks(words):
    return bool(timeline.ASKED.search(" ".join(re.sub(r"[^\w' ]+", " ", words.lower()).split())))


class Kept(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="heyharry-timeline-")
        self.addCleanup(shutil.rmtree, self.folder, True)
        for p in (mock.patch.object(timeline, "FOLDER", self.folder), mock.patch.object(timeline, "_pruned", [None])):
            p.start()
            self.addCleanup(p.stop)
        self.noon, self.day = at((2026, 11, 7), 12), datetime.date(2026, 11, 7)

    def test_a_window_you_were_in_goes_in_its_days_file(self):
        self.assertTrue(timeline.add(visit(self.noon, 120)))
        (row,) = timeline.load(self.day)
        self.assertEqual((row["app"], row["title"], row["site"], row["clicks"]),
                         ("Chrome", "Inbox - Gmail", "mail.google.com", ["Compose"]))
        self.assertEqual(row["to"] - row["from"], 120)
        self.assertEqual(os.listdir(self.folder), ["2026-11-07.jsonl"])

    def test_one_passed_through_on_the_way_isnt_kept(self):
        self.assertFalse(timeline.add(visit(self.noon, 1.5)))
        self.assertEqual(timeline.load(self.day), [])

    def test_a_private_window_is_kept_only_as_one_that_was_open(self):
        timeline.add(visit(self.noon, 60, private=True, title="PayPal Checkout", words="Card", clicks=["Pay"]))
        (row,) = timeline.load(self.day)
        self.assertEqual(set(row), {"from", "to", "app", "private"})

    def test_codes_and_numbers_are_masked(self):
        timeline.add(visit(self.noon, 60, title="Order 4829104", words="Your code is 739104", clicks=["Pay 12345"]))
        with open(os.path.join(self.folder, "2026-11-07.jsonl"), encoding="utf-8") as f:
            raw = f.read()
        for number in ("4829104", "739104", "12345"):
            self.assertNotIn(number, raw)

    def test_a_line_cut_short_is_passed_over(self):
        timeline.add(visit(self.noon, 60))
        with open(os.path.join(self.folder, "2026-11-07.jsonl"), "a", encoding="utf-8") as f:
            f.write('{"from": 1, "to"')  # the PC went off as it was written
        self.assertEqual(len(timeline.load(self.day)), 1)

    def test_days_older_than_a_week_are_let_go_once_a_day(self):
        for day in ("2026-10-30", "2026-10-31", "2026-11-06"):
            open(os.path.join(self.folder, day + ".jsonl"), "w").close()
        timeline.prune(self.day)
        self.assertEqual(sorted(os.listdir(self.folder)), ["2026-10-31.jsonl", "2026-11-06.jsonl"])
        open(os.path.join(self.folder, "2026-10-29.jsonl"), "w").close()
        timeline.prune(self.day)
        self.assertIn("2026-10-29.jsonl", os.listdir(self.folder))  # once a day: not looked at again till tomorrow

    def test_never_raises(self):
        with mock.patch.object(timeline, "FOLDER", os.path.join(self.folder, "a file")):
            open(os.path.join(self.folder, "a file"), "w").close()
            self.assertFalse(timeline.add(visit(self.noon, 60)))
        self.assertFalse(timeline.add({"to": 5}))


class Told(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="heyharry-timeline-")
        self.addCleanup(shutil.rmtree, self.folder, True)
        for p in (mock.patch.object(timeline, "FOLDER", self.folder), mock.patch.object(timeline, "_pruned", [None])):
            p.start()
            self.addCleanup(p.stop)
        self.now = at((2026, 11, 7), 15)  # a Saturday afternoon

    def test_only_words_asking_about_it_bring_it(self):
        for words in ("What was I doing before lunch?", "what did I do today", "Where was I?",
                      "which video was I watching", "how long was I on YouTube", "tell me what I did this morning",
                      "what have I been doing", "when did I open the report", "show me my activity",
                      "what was that site I had open earlier", "remind me what I was working on"):
            self.assertTrue(asks(words), words)
        for words in ("what is this", "play some music", "what time is it", "open chrome", "what did she say",
                      "I was thinking we could go", "what's the weather"):
            self.assertFalse(asks(words), words)
        self.assertEqual(timeline.prompt_block("play some music", now=self.now), "")

    def test_today_window_by_window_where_the_time_went_and_where_you_are(self):
        timeline.add(visit(at((2026, 11, 7), 12), 1800))
        timeline.add(visit(at((2026, 11, 7), 12, 30), 2400, app="VS Code", title="siri.py - hey-harry", site=None,
                           words="def think", clicks=[]))
        current = {"from": self.now - 600, "to": self.now, "app": "Chrome", "title": "lofi beats - YouTube",
                   "site": "youtube.com", "words": "", "clicks": ["Play"], "private": False}
        block = timeline.prompt_block("what was I doing today?", current, now=self.now)
        self.assertIn('<untrusted_tool_result source="screen"', block)  # titles and words are someone else's
        self.assertIn('12:00 PM-12:30 PM (30 min): Chrome: Inbox - Gmail (mail.google.com); clicked "Compose"', block)
        self.assertIn("VS Code: siri.py - hey-harry", block)
        self.assertIn("lofi beats - YouTube (youtube.com)", block)
        self.assertIn("The last one is the window in front now", block)
        self.assertIn("VS Code 40 min", block)
        self.assertIn("Chrome 40 min (mail.google.com 30 min, youtube.com 10 min)", block)

    def test_the_same_window_again_soon_after_is_one_visit(self):
        timeline.add(visit(self.now - 3600, 600))
        timeline.add(visit(self.now - 2990, 600, clicks=["Send"]))  # back to it 10 s later
        block = timeline.prompt_block("what was I doing", now=self.now)
        self.assertIn('(20 min): Chrome: Inbox - Gmail (mail.google.com); clicked "Compose", "Send"', block)

    def test_yesterday_and_a_day_of_the_week(self):
        timeline.add(visit(self.now - 86400, 600, title="Flights to Goa"))
        block = timeline.prompt_block("what did I do yesterday", now=self.now)
        self.assertIn("Flights to Goa", block)
        self.assertIn("Yesterday", block)
        timeline.add(visit(at((2026, 11, 2), 10), 600, title="Weekly report"))  # a Monday
        self.assertIn("Weekly report", timeline.prompt_block("what was I working on on Monday", now=self.now))
        self.assertNotIn("Weekly report", timeline.prompt_block("what did I do today", now=self.now))

    def test_a_week(self):
        for back in range(3):
            timeline.add(visit(at((2026, 11, 7 - back), 10), 3600, app="Excel", title="Budget", site=None))
        block = timeline.prompt_block("what have I been doing this week", now=self.now)
        self.assertEqual(block.count("Excel 1 h"), 3)

    def test_nothing_kept_says_so(self):
        self.assertIn("nothing kept.", timeline.prompt_block("what did I do on Monday", now=self.now))
        with mock.patch.object(timeline.settings, "get", lambda k: 1):
            self.assertIn("only the last 1 days are kept", timeline.prompt_block("what did I do on Monday",
                                                                                 now=self.now))

    def test_a_long_day_keeps_the_latest_and_their_words(self):
        start = at((2026, 11, 7), 9)
        for i in range(120):
            timeline.add(visit(start + i * 60, 50, title=f"Mail {i}", words=f"words of mail {i}"))
        block = timeline.prompt_block("what did I do today", now=self.now)
        self.assertIn("Mail 119", block)
        self.assertIn("words of mail 119", block)
        self.assertNotIn("words of mail 100", block)  # only the latest few with their words
        self.assertIn("earlier)", block)
        self.assertLess(len(block), timeline.BLOCK_CHARS + 2000)

    def test_siri_gives_it_to_the_planner_with_where_you_are(self):
        fake = mock.Mock(visiting=mock.Mock(return_value=None), lines=lambda: [])
        with mock.patch.object(siri, "SCREEN", [fake]), \
                mock.patch.object(timeline, "prompt_block", mock.Mock(return_value="")) as block, \
                mock.patch.object(siri, "ask_plan", side_effect=RuntimeError("the model")):
            with self.assertRaises(Exception):
                with mock.patch("sys.stdout"):
                    siri._think("what did I do today", False)
        block.assert_called_with("what did I do today", None)


if __name__ == "__main__":
    unittest.main()
