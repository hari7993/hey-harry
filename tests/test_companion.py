"""Her as a close friend (companion.py, 7 November 2026: "it doesn't have any human personality"): her notes on your
life from what you tell her, asking after a plan once its time has come, checking in now and then and never at the
wrong moment, her hello with what's going on, how chatty she is, and her hooks in siri."""
import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.support import siri  # temp APPDATA and the tripwires, before anything else
import companion
import phrasebook
import settings

NOW = time.mktime((2026, 11, 7, 18, 0, 0, 0, 0, -1))  # a Saturday, 6 in the evening


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


class Model:
    """The answer model, as a test's: each reply in turn (an exception is raised), and what it was asked."""

    def __init__(self, *replies):
        self.replies, self.asked = list(replies), []

    def __call__(self, messages):
        self.asked.append(messages)
        reply = self.replies.pop(0) if self.replies else ""
        if isinstance(reply, Exception):
            raise reply
        return reply


class Now(unittest.TestCase):
    """A friend on a clock and a folder of the test's own, at the PC, free and out of any call."""

    def setUp(self):
        self.now = [NOW]
        self.folder = tempfile.mkdtemp(prefix="life-")
        self.said, self.at, self.away = [], {"free": True, "call": False, "quiet": False}, [5]
        self.model = Model()
        self.mode = "chatty"

    def friend(self, **kw):
        made = companion.Friend(
            ask=self.model, announce=self.said.append, free=lambda: self.at["free"], idle=lambda: self.away[0],
            in_call=lambda: self.at["call"], quiet=lambda: self.at["quiet"], name=lambda: "Hari",
            her=lambda: "Harry", soul=lambda: "You are Harry, Hari's close friend.",
            now_context=lambda: "On their screen now: YouTube", mode=lambda: self.mode,
            clock=lambda: self.now[0], path=os.path.join(self.folder, "life.json"), **kw)
        return made

    def later(self, seconds):
        self.now[0] += seconds


class Notes(Now):
    NOTED = json.dumps({"plans": [{"text": "call Bunty", "when": "2026-11-07T19:00"}], "mood": "tired after a long day",
                        "events": [{"text": "job interview at Infosys", "when": "2026-11-09"}],
                        "likes": ["loves biryani"], "people": [{"name": "Bunty", "relation": "friend"}]})

    def test_what_you_say_about_your_life_is_kept_and_carried_into_her_prompt(self):
        friend = self.friend()
        self.model.replies = ["Sure. " + self.NOTED]
        with quiet():
            kept = friend.notice("I'm so tired, long day. I'll call Bunty at 7, and I've got my Infosys interview "
                                 "on Monday. Order me a biryani", "On it.")
        self.assertEqual([k["kind"] for k in kept], ["plan", "mood", "event", "like", "person"])
        self.assertIn("I'll call Bunty at 7", self.model.asked[0][-1]["content"])  # only your own words go
        self.assertIn("Saturday 2026-11-07T18:00", self.model.asked[0][0]["content"])  # now, to work "at 7" out
        lines = "\n".join(friend.lines())
        for said in ("call Bunty (today at 7 PM)", "job interview at Infosys (on Monday)",
                     "Lately: tired after a long day (today)", "loves biryani", "Bunty (friend)"):
            self.assertIn(said, lines)
        self.assertIn("close friend", lines)
        again = self.friend()  # kept on this PC, for her next start
        self.assertEqual(len(again.notes), 5)

    def test_nothing_kept_when_theres_nothing_or_the_model_fails(self):
        friend = self.friend()
        for reply in ('{"plans": [], "mood": "", "events": [], "likes": [], "people": []}', "no idea",
                      ConnectionError("offline"), '["not", "an", "object"]'):
            self.model.replies = [reply]
            with self.subTest(reply=reply), quiet():
                self.assertEqual(friend.notice("I'll be back"), [])
        self.assertEqual(friend.notes, [])
        self.assertEqual(friend.lines(), [])  # and nothing in her prompt

    def test_only_words_that_may_be_about_your_life_go_to_the_model(self):
        friend = self.friend()
        self.model.replies = [self.NOTED]
        ran = []

        class Thread:
            def __init__(self, target, args=(), **kw):
                self.go = lambda: (ran.append(args), target(*args))

            def start(self):
                self.go()
        with mock.patch.object(companion.threading, "Thread", Thread), quiet():
            for words in ("open notepad", "what's the weather", "turn the volume up"):
                friend.heard(words, "Done.")
            self.assertEqual(ran, [])
            friend.heard("I need to call Bunty tonight at 7", "Okay.")
            friend.heard("Hey Harry, I noted to call Sam in twenty minutes.", "Got it.")  # 7 November, live
        self.assertEqual(ran, [("I need to call Bunty tonight at 7", "Okay."),
                               ("Hey Harry, I noted to call Sam in twenty minutes.", "Got it.")])
        self.assertEqual(friend.last_turn, NOW)
        self.assertTrue(friend.noting.acquire(blocking=False))  # let go once it's done

    def test_the_same_thing_twice_is_kept_once(self):
        friend = self.friend()
        friend.add("person", "Bunty")
        friend.add("person", "bunty", relation="friend")
        friend.add("plan", "call Bunty")
        friend.add("plan", "Call Bunty", when=NOW + 3600)
        self.assertEqual(len(friend.notes), 2)
        self.assertEqual(friend.notes[0]["relation"], "friend")
        self.assertEqual(friend.notes[1]["when"], NOW + 3600)
        self.assertIsNone(friend.add("plan", "   "))
        friend.notes[1]["status"] = "asked"
        friend.add("plan", "call Bunty", when=NOW + 86400)  # the same again another day: asked after again
        self.assertEqual([n.get("status") for n in friend.notes], [None, "asked", "open"])

    def test_old_moods_and_far_plans_stay_out_of_her_prompt(self):
        friend = self.friend()
        friend.add("mood", "stressed about work")
        friend.add("plan", "renew the passport", when=NOW + 30 * 86400)
        self.later(3 * 86400)
        self.assertEqual(friend.lines(), [])

    def test_forget_about_something(self):
        friend = self.friend()
        friend.add("event", "trip to Goa", when=NOW + 86400)
        friend.add("plan", "pack for the Goa trip")
        friend.add("person", "Bunty")
        self.assertEqual(friend.forget("goa trip"), 2)
        self.assertEqual([n["text"] for n in friend.notes], ["Bunty"])
        self.assertEqual(friend.forget("the wedding"), 0)
        self.assertEqual(len(self.friend().notes), 1)  # gone from the file too


class TalkingFirst(Now):
    def test_she_asks_after_a_plan_once_its_time_has_come_once(self):
        self.mode = "quiet"  # follow-ups whatever her chattiness; no check-ins in the way
        friend = self.friend()
        friend.add("plan", "call Bunty", when=NOW + 3600)
        self.later(10 * 60)
        self.assertEqual(friend.tick(), "")  # not yet
        self.later(50 * 60 + 5 * 60)
        self.assertEqual(friend.tick(), "")  # nor right on top of its reminder
        self.later(companion.FOLLOW_LATER - 5 * 60)
        self.model.replies = ['"Did you get to call Bunty, or is he still waiting?"']
        with quiet():
            self.assertEqual(friend.tick(), "Did you get to call Bunty, or is he still waiting?")
        self.assertEqual(self.said, ["Did you get to call Bunty, or is he still waiting?"])
        self.assertIn("call Bunty today at 7 PM", self.model.asked[0][-1]["content"])
        self.assertEqual(self.model.asked[0][0], {"role": "system", "content": "You are Harry, Hari's close friend."})
        self.later(15 * 60)
        with quiet():
            friend.tick()
        self.assertEqual(len(self.said), 1)  # once
        self.assertEqual(self.friend().notes[0]["status"], "asked")

    def test_in_plain_words_when_the_model_doesnt_answer(self):
        self.mode = "quiet"
        friend = self.friend()
        friend.add("plan", "call Bunty", when=NOW + 600)
        self.later(10 * 60 + companion.FOLLOW_LATER)
        self.model.replies = [ConnectionError("offline")]
        with quiet():
            self.assertEqual(friend.tick(), "Hey, did you get to call Bunty?")

    def test_a_plan_long_past_closes_without_a_word(self):
        friend = self.friend()
        friend.add("plan", "call Bunty", when=NOW - companion.FOLLOW_WITHIN - 60)
        self.later(15 * 60)
        self.assertIsNone(friend.due())
        self.assertEqual(friend.notes[0]["status"], "done")
        self.assertEqual(self.said, [])

    def test_never_at_the_wrong_moment(self):
        friend = self.friend()
        friend.add("plan", "call Bunty", when=NOW + 60)
        self.later(companion.CHAT_GAP["chatty"] + 60)
        for what, change in (("away from the PC", {"away": companion.AWAY + 1}), ("in a call", {"call": True}),
                             ("her quiet hours", {"quiet": True}), ("busy", {"free": False})):
            with self.subTest(what):
                self.away[0] = change.get("away", 5)
                self.at.update(free=change.get("free", True), call=change.get("call", False),
                               quiet=change.get("quiet", False))
                self.assertEqual(friend.tick(), "")
        self.assertEqual(self.model.asked, [])
        self.assertEqual(self.said, [])

    def test_not_right_on_top_of_a_conversation(self):
        friend = self.friend()
        friend.add("plan", "call Bunty", when=NOW + 60)
        self.later(companion.CHAT_GAP["chatty"])
        friend.heard("thanks")
        self.later(30)
        self.assertEqual(friend.tick(), "")
        self.later(companion.FOLLOW_AFTER_TURN)
        with quiet():
            self.assertTrue(friend.tick())

    def test_a_check_in_now_and_then(self):
        friend = self.friend()
        friend.add("event", "job interview at Infosys", when=NOW + 2 * 86400)
        self.later(companion.FIRST_CHAT - 60)
        self.assertEqual(friend.tick(), "")  # not in her first few minutes
        self.later(120)
        self.model.replies = ["You've been on YouTube a while. Prepping for Monday's interview, or is this 'research'?"]
        with quiet():
            line = friend.tick()
        self.assertTrue(line.startswith("You've been on YouTube a while."))
        self.assertEqual(self.said, [line])
        asked = self.model.asked[0][-1]["content"]
        for told in ("job interview at Infosys", "On their screen now: YouTube", "6:09 PM, a Saturday evening",
                     "you last talked 9 minutes ago", "nothing yet"):
            self.assertIn(told, asked)
        self.later(10 * 60)
        self.assertEqual(friend.tick(), "")  # and not again so soon
        self.later(companion.CHAT_GAP["chatty"])
        self.model.replies = ["Nothing."]  # nothing worth saying: nothing said
        with quiet():
            self.assertEqual(friend.tick(), "")
        self.assertIn(line, self.model.asked[1][-1]["content"])  # told what she said lately
        self.assertEqual(len(self.said), 1)

    def test_how_chatty_is_up_to_you(self):
        friend = self.friend()
        self.mode = "quiet"
        self.later(5 * 3600)
        self.assertEqual(friend.tick(), "")
        self.mode = "sometimes"
        self.model.replies = ["Hey, stretch break?"]
        with quiet():
            self.assertEqual(friend.tick(), "Hey, stretch break?")
        self.later(companion.CHAT_GAP["chatty"] + 60)
        self.assertEqual(friend.tick(), "")  # an hour and a half between, sometimes

    def test_no_more_than_so_many_a_day(self):
        friend = self.friend()
        friend.said = [(NOW + i, f"line {i}") for i in range(companion.CHATS_A_DAY)]
        self.later(companion.CHAT_GAP["chatty"])
        self.model.replies = ["One more."]
        self.assertEqual(friend.check_in(), "")
        self.assertEqual(self.model.asked, [])

    def test_a_fault_never_ends_her_thread(self):
        friend = self.friend()
        stop = mock.Mock()
        stop.wait.side_effect = [False, True]
        with mock.patch.object(friend, "tick", side_effect=RuntimeError("bad")), quiet():
            friend.run(stop)


class Hello(Now):
    def test_her_hello_as_a_friend_with_whats_going_on(self):
        friend = self.friend()
        friend.add("event", "job interview at Infosys", when=NOW + 2 * 86400)
        self.model.replies = ["There you are, Hari! Battery's at 18 percent, so plug in before you prep for Monday."]
        line = friend.greeting(True, "Welcome back, Hari. Battery's at 18 percent. Anything you need?",
                               ["Hey Hari"])
        self.assertTrue(line.startswith("There you are, Hari!"))
        asked = self.model.asked[0][-1]["content"]
        self.assertIn("Welcome back, Hari. Battery's at 18 percent.", asked)
        self.assertNotIn("Anything you need?", asked.split("Work these in")[1].split("\n")[0])
        self.assertIn("job interview at Infosys", asked)
        self.assertIn('"Hey Hari"', asked)  # not the way she began lately
        self.assertIn("come back to the laptop", asked)
        self.model.replies = [TimeoutError("slow")]
        with quiet():
            self.assertEqual(friend.greeting(False, "Welcome home, Hari."), "")

    def test_offline_not_word_for_word_the_same(self):
        line = "Welcome back, Hari. Mum sent you a message on WhatsApp. Anything you need?"
        said = {companion.plain_hello(line, True, pick=lambda options, i=i: options[i % len(options)])
                for i in range(5)}
        self.assertEqual(len(said), 5)
        for hello in said:
            self.assertIn("Hari", hello)
            self.assertIn("Mum sent you a message on WhatsApp.", hello)
            self.assertTrue(hello.endswith("?"))  # so she still listens for the answer
        home = companion.plain_hello("Welcome home, Hari. It's 9:01 in the morning. Anything you'd like me to do?",
                                     False, pick=lambda options: options[1], hour=9)
        self.assertEqual(home, "Good morning, Hari. It's 9:01 in the morning. What are we up to?")
        night = companion.plain_hello("Welcome home.", False, pick=lambda options: options[0], hour=23)
        self.assertEqual(night, "Hey, good evening.")  # never "good night" as a hello
        self.assertEqual(companion.plain_hello("Battery's low.", True), "Battery's low.")

    def test_their_name_with_a_capital(self):
        self.assertEqual(companion.spoken_name("hari"), "Hari")
        self.assertEqual(companion.spoken_name("  hari   kumar "), "Hari Kumar")
        self.assertEqual(companion.spoken_name(None), "")
        self.assertEqual(companion.spoken_name("McKenzie"), "McKenzie")

    def test_times_in_words(self):
        for when, words in ((NOW + 3600, "today at 7 PM"), (NOW + 86400 - 1800, "tomorrow at 5:30 PM"),
                            (time.mktime((2026, 11, 9, 0, 0, 0, 0, 0, -1)), "on Monday"),
                            (NOW - 86400, "yesterday at 6 PM"),
                            (time.mktime((2026, 11, 20, 0, 0, 0, 0, 0, -1)), "on 20 November")):
            with self.subTest(words):
                self.assertEqual(companion.when_said(when, NOW), words)
        self.assertEqual(companion.parse_when("2026-11-07T19:00"), NOW + 3600)
        self.assertIsNone(companion.parse_when("tonight"))


class Said(Now):
    def setUp(self):
        super().setUp()
        p = mock.patch.dict(settings._load(), {})
        p.start()
        self.addCleanup(p.stop)

    def test_how_chatty_switched_by_voice(self):
        for words, mode in (("Talk less.", "quiet"), ("check in on me more", "chatty"),
                            ("talk to me now and then", "sometimes"), ("keep me company", "chatty"),
                            ("Can you stop checking in on me so much?", "quiet")):
            with self.subTest(words):
                plan = companion.quick(words, siri.plain, False)
                self.assertEqual(plan["steps"], [])
                self.assertTrue(plan["say"])
                self.assertEqual(settings.get("chattiness"), mode)
        for words in ("be quiet", "stop talking", "talk to me", "you talk less than Bunty"):  # never hers
            with self.subTest(words):
                self.assertIsNone(companion.quick(words, siri.plain, False))

    def test_forget_only_when_her_notes_have_it(self):
        friend = self.friend()
        friend.add("event", "trip to Goa")
        self.assertIsNone(companion.quick("forget about the wedding", siri.plain, False, friend))  # her memory's
        self.assertEqual(companion.quick("forget about the trip", siri.plain, False, friend)["say"], "Okay, forgotten.")
        self.assertEqual(friend.notes, [])
        self.assertIsNone(companion.quick("forget about the trip", siri.plain, False, None))

    def test_through_her_quick_path(self):
        with mock.patch.object(siri, "routines", lambda: []), quiet():
            plan = siri.quick("talk less")
        self.assertEqual(plan["say"], "Okay, I'll keep it down. Just what you told me you'd do.")
        self.assertEqual(settings.get("chattiness"), "quiet")


class InSiri(Now):
    FACTS = "Welcome back, Hari. Battery's at 18 percent. Anything you need?"
    LIFE = "Their plans: call Bunty (today at 7 PM). Their people: Bunty (friend), Amma (mother)."

    def setUp(self):
        super().setUp()
        folder = tempfile.mkdtemp(prefix="phrases-")
        for target, name, value in ((phrasebook, "PATH", os.path.join(folder, "phrases.json")),
                                    (siri, "part_of_day", lambda: "evening")):
            p = mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)
        phrasebook._cache.update(mtime=None, data={})
        p = mock.patch.dict(settings._load(), {"name": "hari"})
        p.start()
        self.addCleanup(p.stop)

    def test_a_friend_hello_may_bring_up_your_life_but_makes_nothing_up(self):
        fits = siri.friend_fits
        for line in ("Hey Hari, good to see you. Battery's at 18 percent, and did you call Bunty yet?",
                     "There you are, Hari! Battery's at 18 percent. Say hi to Amma for me.",
                     "Hey Hari. Battery's at 18 percent, so plug in before seven."):
            with self.subTest(line):
                self.assertTrue(fits(line, self.FACTS, self.LIFE))
        for line in ("Hey Hari, Bittu says hi. Battery's at 18 percent.",  # a name from neither
                     "Hey Hari. Battery's at 81 percent.",  # a number
                     "Hey Hari. Battery's at 18 percent, and call Bunty at 9.",  # nor a time it wasn't given
                     "Hey Hari, it's sunny out. Battery's at 18 percent.",  # the weather
                     "Hey Hari, good to see you!",  # the battery left out
                     "Good morning, Hari. Battery's at 18 percent.",  # in the evening
                     "[cheerful] Hey Hari. Battery's at 18 percent."):
            with self.subTest(line):
                self.assertFalse(fits(line, self.FACTS, self.LIFE))
        facts = "Welcome back, Hari. Amma messaged you on WhatsApp. Anything you need?"
        self.assertFalse(fits("Hey Hari, someone messaged you on WhatsApp.", facts, ""))  # who messaged, left out

    def test_her_welcome_as_a_friend_and_without_one(self):
        self.assertIsNone(siri.friend_welcome(True, self.FACTS))  # not started
        friend = self.friend()
        friend.add("plan", "call Bunty", when=NOW + 3600)
        self.model.replies = ["Hey Hari! Battery's at 18 percent. Still on for calling Bunty?",
                              "Welcome back, Hari. Battery's at 18 percent and the weather's lovely."]
        line = "Hey Hari! Battery's at 18 percent. Still on for calling Bunty?"
        with mock.patch.object(siri, "FRIEND", [friend]), quiet(), \
                mock.patch.object(siri, "friend_ask", lambda messages, wait=30: self.model(messages)):
            self.assertEqual(siri.friend_welcome(True, self.FACTS), line)
            self.assertEqual(phrasebook.said("welcome"), [line])
            self.assertIsNone(siri.friend_welcome(True, self.FACTS))  # the weather, made up: fresh_welcome's go
        self.assertIn('"Hey Hari"', self.model.asked[1][-1]["content"])  # not the way she began last time

    def test_a_reminder_said_back_as_a_friend_would(self):
        """7 November, live: "I noted to call Sam in twenty minutes" was answered "Task 8 is scheduled for today at
        2:57 PM." """
        store = siri.tasking.Store(os.path.join(tempfile.mkdtemp(prefix="tasks-"), "tasks.db"))
        with mock.patch.object(siri, "TASK_STORE", store), quiet():
            plan = siri.prepare_task_steps({"steps": [{"do": "schedule", "when": "in 20 minutes", "description":
                                                       "Call Sam", "task": {"kind": "reminder", "text": "call Sam"}}],
                                            "say": ""})
        self.assertRegex(plan["say"], r"^Got it, I'll remind you today at \d{1,2}:\d\d [AP]M\.$")
        self.assertNotIn("Task", plan["say"])
        self.assertEqual(store.list(active=True)[0]["kind"], "reminder")

    def test_her_welcome_says_their_name_with_a_capital(self):
        with mock.patch.object(siri, "pc_warnings", lambda: []):
            self.assertEqual(siri.welcome_line(True), "Welcome back, Hari. Anything you need?")
        with mock.patch.object(siri, "SCREEN", []), mock.patch.object(siri, "FRIEND", []):
            self.assertIn("Their name is Hari, never any other.", siri.context())

    def test_the_model_is_told_about_your_life(self):
        fake = SimpleNamespace(lines=lambda: ["What you know of their life lately: call Bunty (today at 7 PM)"])
        with mock.patch.object(siri, "SCREEN", []), mock.patch.object(siri, "FRIEND", [fake]):
            self.assertIn("call Bunty (today at 7 PM)", siri.context())
        with mock.patch.object(siri, "SCREEN", []), mock.patch.object(siri, "FRIEND", []):
            self.assertNotIn("their life lately", siri.context())


if __name__ == "__main__":
    unittest.main()
