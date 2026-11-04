"""Her agents' cursors (cursors.py): what each job's arrow says and where it goes, the colours they share out, the
pill's words at the bottom of the screen on a clock of the test's own, and the arrow's shape. Nothing's drawn: the
tests' support replaces the one way to Windows (cursors._wake)."""
import unittest
from types import SimpleNamespace
from unittest import mock

from tests import support
from tests.support import siri  # temp APPDATA and the tripwires, before anything else
import cursors


class Fleet(unittest.TestCase):
    def setUp(self):
        self.now = [1000.0]
        self.clock = mock.patch.object(cursors, "time", SimpleNamespace(time=lambda: self.now[0]))
        self.clock.start()
        cursors.AGENTS.clear()
        cursors.RUN.update(start=None, ids=set(), steps=0, ended=None, took=0.0)

    def tearDown(self):
        self.clock.stop()
        cursors.AGENTS.clear()

    def test_nothing_is_ever_drawn_in_the_tests(self):
        self.assertIsNot(cursors._wake, support.CURSORS_WAKE)

    def test_as_many_agents_as_jobs_at_a_time(self):
        self.assertEqual(siri.JOB_WORKERS, cursors.MOST)
        self.assertEqual(len(set(cursors.COLOURS)), cursors.MOST)

    def test_each_agent_has_a_colour_no_other_going_has(self):
        self.assertEqual([cursors.begin(n, f"job {n}") for n in (11, 12, 13)], [1, 2, 3])
        colours = {cursors.AGENTS[n].colour for n in (11, 12, 13)}
        self.assertEqual(len(colours), 3)
        cursors.end(12)
        self.assertEqual(cursors.begin(14, "job 14"), 2)  # the colour of one that's done is free again
        self.assertEqual(cursors.AGENTS[14].colour, cursors.COLOURS[1])

    def test_its_label_is_a_few_words_of_its_goal(self):
        self.assertEqual(cursors.label_of("turn on night light."), "Turn on night light")
        self.assertEqual(cursors.label_of("write a shopping list with milk and eggs in Notepad"), "Write a shopping list")
        self.assertEqual(cursors.label_of("send a mail to Ravi about the report"), "Send a mail")
        self.assertEqual(cursors.label_of("summarise https://example.com/a/very/long/page"), "Summarise https://example\u2026")
        self.assertEqual(cursors.label_of(""), "Task")
        cursors.begin(5, "turn on night light")
        cursors.aim(5, (0, 0, 10, 10), "clicking")
        self.assertEqual(cursors.fleet(), [(5, 1, "1 Turn on night light \u00b7 clicking", "going")])

    def test_it_goes_to_a_point_or_the_middle_of_a_control_and_never_out_of_sight(self):
        self.assertEqual(cursors.point_of((100, 200, 300, 260)), (200.0, 230.0))
        self.assertEqual(cursors.point_of((40, 50)), (40.0, 50.0))
        for where in (None, (10, 10, 10, 30), (-32000, -32000, -31000, -31500), "here", (1, 2, 3)):
            self.assertIsNone(cursors.point_of(where), where)
        cursors.begin(7, "job")
        cursors.aim(7, (100, 200, 300, 260), "clicking")
        cursors.aim(7, (-32000, -32000, -31000, -31500), "typing")  # her own browser, out of sight: it stays
        cursors.aim(7, None, "pressing keys")
        self.assertEqual(cursors.AGENTS[7].target, (200.0, 230.0))
        self.assertEqual(cursors.AGENTS[7].note, "pressing keys")
        self.assertFalse(cursors.aim(8, (0, 0, 5, 5)))  # a job with no cursor going

    def test_it_goes_to_a_window_the_first_time_it_looks_at_it(self):
        cursors.begin(7, "job")
        self.assertTrue(cursors.look(7, 4242))
        self.assertFalse(cursors.look(7, 4242))
        self.assertEqual(cursors.AGENTS[7].wanted, 4242)  # where it is is found when it's drawn
        cursors.aim(7, (0, 0, 20, 20))
        self.assertIsNone(cursors.AGENTS[7].wanted)  # a step's own place comes first
        self.assertTrue(cursors.look(7, 5151))
        for hwnd in (None, 0, True, "tab"):
            self.assertFalse(cursors.look(7, hwnd), hwnd)

    def test_the_pill_counts_agents_and_steps_then_says_how_long_they_took(self):
        self.assertEqual(cursors.summary(), "")
        cursors.begin(1, "a")
        cursors.begin(2, "b")
        for _ in range(3):
            cursors.aim(1, (0, 0, 10, 10))
        self.assertEqual(cursors.summary(), "2 agents \u00b7 3 steps")
        self.now[0] += 20
        cursors.begin(3, "c")
        cursors.end(1)
        self.assertEqual(cursors.summary(), "2 agents \u00b7 3 steps")
        cursors.end(2, waiting=True)
        self.assertEqual(cursors.summary(), "1 agent \u00b7 3 steps \u00b7 1 waiting for you")
        self.now[0] += 27
        cursors.end(3)
        self.assertEqual(cursors.summary(), "1 agent waiting for you")
        self.assertEqual(cursors.begin(2, "b"), 2)  # your yes: it goes again with its own colour
        cursors.aim(2, (0, 0, 10, 10))
        cursors.end(2)
        self.assertEqual(cursors.summary(), "Done by 3 agents in 47.0s")
        self.now[0] += cursors.DONE_FOR
        self.assertEqual(cursors.summary(), "")

    def test_a_new_lot_counts_from_its_own_start(self):
        cursors.begin(1, "a")
        cursors.aim(1, (0, 0, 10, 10))
        cursors.end(1)
        self.now[0] += 60
        cursors.begin(2, "b")
        self.assertEqual(cursors.summary(), "1 agent \u00b7 0 steps")
        self.now[0] += 2.5
        cursors.end(2)
        self.assertEqual(cursors.summary(), "Done by 1 agent in 2.5s")

    def test_one_stopped_while_it_waits_on_you_goes(self):
        cursors.begin(4, "a")
        cursors.end(4, waiting=True)
        self.assertEqual([state for *_, state in cursors.fleet()], ["waiting"])
        cursors.end(4)
        self.assertEqual([state for *_, state in cursors.fleet()], ["ended"])
        self.now[0] += cursors.FADE + 0.01
        cursors.begin(9, "b")  # faded out by the next one's start
        self.assertEqual([job for job, *_ in cursors.fleet()], [9])

    def test_it_shows_softly_while_it_waits_and_fades_once_done(self):
        cursors.begin(4, "a")
        self.assertEqual(cursors.AGENTS[4].alpha(self.now[0]), 0.0)
        self.assertAlmostEqual(cursors.AGENTS[4].alpha(self.now[0] + 0.2), 1.0)
        self.now[0] += 1
        cursors.end(4, waiting=True)
        self.assertAlmostEqual(cursors.AGENTS[4].alpha(self.now[0]), 0.7)
        cursors.end(4)
        self.assertAlmostEqual(cursors.AGENTS[4].alpha(self.now[0] + cursors.FADE), 0.0)


class Arrow(unittest.TestCase):
    def test_the_arrow_covers_its_own_shape_and_nothing_else(self):
        points = [(10 + x * 2, 10 + y * 2) for x, y in cursors.ARROW]
        x0, y0, cover = cursors._polygon(points)
        area = abs(sum(ax * by - bx * ay for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]))) / 2
        self.assertAlmostEqual(float(cover.sum()), area, delta=area * 0.03)
        self.assertGreater(cover[int(10 + 2 * 8 - y0), int(10 + 2 * 2 - x0)], 0.99)  # inside, by its stem
        self.assertEqual(float(cover[int(10 + 2 * 2 - y0), int(10 + 2 * 10 - x0)]), 0.0)  # right of its tip
        self.assertTrue(0.0 <= float(cover.min()) and float(cover.max()) <= 1.0)


if __name__ == "__main__":
    unittest.main()
