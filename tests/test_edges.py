"""Her edges of the screen (edges.py): the sliders' parts and pictures, the levels read and set on their own thread
only while they're wanted, and a slider's presses, none while her agent works."""
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from tests.support import siri  # noqa: F401  temp APPDATA and the tripwires, before anything else
import agent
import bubble
import edges
import island
import settings

TEXTS = {}


def text(px, weight):
    if (px, weight) not in TEXTS:
        TEXTS[(px, weight)] = bubble.Text(px, weight)
    return TEXTS[(px, weight)]


APPS = [{"key": "1:a.exe", "name": "A", "exe": "a.exe", "volume": 50, "muted": False, "icon": None},
        {"key": "2:b.exe", "name": "B", "exe": "b.exe", "volume": 80, "muted": True, "icon": None}]


class Picture(unittest.TestCase):
    def test_the_volume_has_a_bar_for_each_app_beside_its_own(self):
        lay = edges.layout("volume", APPS, 1.5)
        self.assertEqual([b[0] for b in lay["bars"]], ["master", "1:a.exe", "2:b.exe"])
        self.assertEqual(len(edges.layout("brightness", APPS, 1.5)["bars"]), 1)  # the brightness has none
        x0, y0, x1, y1 = lay["panel"]
        self.assertTrue(0 < x0 < x1 < lay["w"] and 0 < y0 < y1 < lay["h"])

    def test_drawn_as_window_bytes_its_panel_kept(self):
        th = island.GLASS["dark"]
        edges._bases.clear()
        pic = edges.render("volume", 40, False, APPS, 1.5, th, text)
        lay = edges.layout("volume", APPS, 1.5)
        self.assertEqual(pic.shape, (lay["h"], lay["w"], 4))
        self.assertEqual(pic.dtype, np.uint8)
        self.assertTrue((pic[..., :3] <= pic[..., 3:]).all())  # premultiplied
        self.assertEqual(len(edges._bases), 1)
        other = edges.render("volume", 70, False, APPS, 1.5, th, text)
        self.assertEqual(len(edges._bases), 1)  # the same panel, only the bars again
        self.assertFalse(np.array_equal(pic, other))
        self.assertTrue(np.array_equal(pic[:5], other[:5]))  # the top of the shadow never moves

    def test_a_kept_column_gives_the_same_picture(self):
        th = island.GLASS["paper"]
        edges._columns.clear()
        first = edges.render("brightness", 30, False, [], 1.5, th, text)
        again = edges.render("brightness", 30, False, [], 1.5, th, text)
        self.assertTrue(np.array_equal(first, again))


class FakeEndpoint:
    def __init__(self):
        self.level, self.muted = 0.4, 0

    def GetMasterVolumeLevelScalar(self):
        return self.level

    def GetMute(self):
        return self.muted

    def SetMasterVolumeLevelScalar(self, v, _):
        self.level = v

    def SetMute(self, m, _):
        self.muted = m


class LevelsThread(unittest.TestCase):
    def setUp(self):
        self.ep = FakeEndpoint()
        self.patches = [mock.patch.object(edges.win, "_com"),
                        mock.patch.object(edges.win, "_endpoint", return_value=self.ep),
                        mock.patch.object(edges.win, "brightness", return_value=50),
                        mock.patch.object(edges.win, "set_brightness"),
                        mock.patch.object(edges, "plan_brightness", return_value=50)]
        for p in self.patches:
            p.start()
        self.levels = edges.Levels()

    def tearDown(self):
        self.levels.stop()
        self.levels.thread.join(2)
        for p in self.patches:
            p.stop()

    def until(self, kind, seconds=2.0):
        end, seen = time.monotonic() + seconds, []
        while time.monotonic() < end:
            seen += self.levels.take()
            hit = [e for e in seen if e[0] == kind]
            if hit:
                return hit
            time.sleep(0.01)
        return []

    def test_nothing_is_read_while_nothing_wants_it(self):
        self.levels.start()
        time.sleep(0.3)
        self.assertEqual([e for e in self.levels.take() if e[0] == "volume"], [])

    def test_read_once_wanted_and_set_from_tks_thread(self):
        self.levels.start()
        self.levels.hud = True
        self.levels.nudge()
        got = self.until("volume")
        self.assertEqual(got[0][1:3], (40, False))
        self.levels.do("volume", 75)
        self.assertTrue(any(e[1] == 75 for e in self.until("volume")))
        self.assertAlmostEqual(self.ep.level, 0.75)
        self.levels.do("brightness", 20)
        end = time.monotonic() + 2
        while not edges.win.set_brightness.called and time.monotonic() < end:
            time.sleep(0.01)
        edges.win.set_brightness.assert_called_with(20)


class Presses(unittest.TestCase):
    def slider(self):
        s = edges.Slider(None, "left", 1.0)
        s.level, s.x, s.y, s.shown = 50, 0, 0, True
        s.host = mock.Mock()
        s.host.busy.return_value = False
        return s

    def test_a_press_on_the_bar_sets_the_level_where_it_is(self):
        s = self.slider()
        lay = edges.layout("volume", [], 1.0)
        _, x0, y0, x1, y1 = lay["bars"][0]
        with mock.patch.object(edges.win, "cursor_pos", return_value=((x0 + x1) / 2, y0 + (y1 - y0) * 0.25)):
            s._press()
        s.host.set.assert_called_once()
        self.assertEqual(s.host.set.call_args[0][1:], ("master", 75))

    def test_the_wheel_moves_it_a_step_a_notch(self):
        s = self.slider()
        with mock.patch.object(edges.win, "cursor_pos", return_value=(-50, -50)):
            s._wheel(240)
        self.assertEqual(s.host.set.call_args[0][1:], ("master", 50 + 2 * edges.STEP))

    def test_none_while_her_agent_works(self):
        s = self.slider()
        s.host = SimpleNamespace(busy=edges.Edges.busy, set=mock.Mock())
        with agent.ACT:
            with mock.patch.object(edges.win, "cursor_pos", return_value=(30, 100)):
                s._press()
                s._wheel(120)
        s.host.set.assert_not_called()


if __name__ == "__main__":
    unittest.main()
