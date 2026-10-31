"""Her focus timer (focus.py): what's said plainly and what it plans, the session's parts on a clock of the test's
own, her step for the planner, and the chime and her word at a part's end."""
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.support import siri  # temp APPDATA and the tripwires, before anything else
import focus
import settings
import toolbox

HOST = SimpleNamespace(plain=siri.plain, parse_duration=siri.parse_duration, say_duration=siri.say_duration)


class Said(unittest.TestCase):
    def setUp(self):
        focus.stop()
        self.old, focus.host = focus.host, HOST
        self.watch = mock.patch.object(focus.threading, "Thread")  # no clock thread, chiming at a test's own time
        self.watch.start()

    def tearDown(self):
        self.watch.stop()
        focus.stop()
        focus.host = self.old

    def plan(self, words, gate=False):
        return focus.quick(words, siri.plain, gate)

    def test_a_pomodoro_starts_for_the_minutes_in_settings(self):
        settings.put("focus_minutes", 30)
        try:
            p = self.plan("start a pomodoro")
        finally:
            settings.put("focus_minutes", 25)
        self.assertEqual(p["steps"], [{"do": "focus", "action": "start"}])
        self.assertIn("30 minutes", p["say"])

    def test_a_said_time_is_its_length(self):
        p = self.plan("focus for 50 minutes")
        self.assertEqual(p["steps"], [{"do": "focus", "action": "start", "minutes": 50.0}])

    def test_focus_for_something_that_isnt_a_time_is_left_to_the_model(self):
        self.assertIsNone(self.plan("focus for my exam"))

    def test_pause_resume_skip_and_stop(self):
        for words, action in (("pause the pomodoro", "pause"), ("resume the focus timer", "resume"),
                              ("skip the break", "skip")):
            self.assertEqual(self.plan(words)["steps"], [{"do": "focus", "action": action}], words)
        self.assertEqual(self.plan("stop the pomodoro")["steps"], [])  # none on: nothing to stop
        focus.start(now=1000.0)
        self.assertEqual(self.plan("stop the pomodoro")["steps"], [{"do": "focus", "action": "stop"}])

    def test_from_across_the_room_only_stopping_is_taken(self):
        self.assertIsNone(self.plan("start a pomodoro", gate="cold"))
        self.assertIsNotNone(self.plan("stop the pomodoro", gate="cold"))

    def test_what_has_nothing_to_do_with_it_is_left_alone(self):
        for words in ("focus on the window", "what's the weather", "set a timer for 5 minutes"):
            self.assertIsNone(self.plan(words), words)


class Session(unittest.TestCase):
    def setUp(self):
        focus.stop()
        self.old, focus.host = focus.host, HOST
        self.watch = mock.patch.object(focus.threading, "Thread")  # no clock thread: the test moves time itself
        self.watch.start()

    def tearDown(self):
        self.watch.stop()
        focus.stop()
        focus.host = self.old

    def test_focus_then_a_break_then_the_next_round(self):
        focus.start(25 * 60, 5 * 60, now=0.0)
        s = focus.state(now=60.0)
        self.assertEqual((s["phase"], s["round"], round(s["left"])), ("focus", 1, 24 * 60))
        self.assertEqual(focus.skip(now=60.0), "break")
        s = focus.state(now=60.0)
        self.assertEqual((s["phase"], round(s["length"])), ("break", 300))
        focus.skip(now=70.0)
        self.assertEqual((focus.state(now=70.0)["phase"], focus.state(now=70.0)["round"]), ("focus", 2))

    def test_every_fourth_round_ends_in_a_long_break(self):
        focus.start(25 * 60, 5 * 60, now=0.0)
        for _ in range(3):
            focus.skip(now=0.0)
            focus.skip(now=0.0)
        self.assertEqual(focus.state(now=0.0)["round"], 4)
        focus.skip(now=0.0)
        self.assertEqual(round(focus.state(now=0.0)["length"]), focus.LONG_REST)

    def test_paused_it_keeps_what_was_left(self):
        focus.start(600, 300, now=0.0)
        self.assertTrue(focus.pause(now=100.0))
        self.assertFalse(focus.pause(now=150.0))
        s = focus.state(now=400.0)
        self.assertTrue(s["paused"])
        self.assertEqual(round(s["left"]), 500)
        self.assertTrue(focus.resume(now=400.0))
        self.assertEqual(round(focus.state(now=450.0)["left"]), 450)

    def test_the_time_left_is_said(self):
        focus.start(25 * 60, 300, now=0.0)
        self.assertIn("round 1", focus.left_line(now=11 * 60))
        focus.stop()
        self.assertIsNone(focus.state())

    def test_a_parts_end_chimes_and_she_says_so(self):
        said = []
        focus.host = SimpleNamespace(**vars(HOST), ANNOUNCE=SimpleNamespace(put=said.append))
        import winplatform
        with mock.patch.object(winplatform, "chime") as chime:
            focus._tell("Time for a break.")
        chime.assert_called_once_with("timer")
        self.assertTrue(any("break" in str(s) for s in said))


class Step(unittest.TestCase):
    def setUp(self):
        focus.stop()
        self.watch = mock.patch.object(focus.threading, "Thread")
        self.watch.start()

    def tearDown(self):
        self.watch.stop()
        focus.stop()

    def test_its_registered_as_her_own_timer(self):
        step = toolbox.get("focus")
        self.assertEqual(step.effect, "own_data")

    def test_the_steps_start_and_stop_it(self):
        self.assertEqual(focus._step({"do": "focus", "action": "start", "minutes": 10}), "focus timer on")
        self.assertEqual(round(focus.state()["length"]), 600)
        self.assertEqual(focus._step({"do": "focus", "action": "stop"}), "focus timer off")
        with self.assertRaises(RuntimeError):
            focus._step({"do": "focus", "action": "pause"})

    def test_the_planner_hears_of_it_only_when_its_asked_for(self):
        self.assertEqual(focus.prompt_block("what's the time"), "")
        self.assertIn('"do":"focus"', focus.prompt_block("start a pomodoro please"))


if __name__ == "__main__":
    unittest.main()
