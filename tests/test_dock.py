"""Her dock (dock.py): where its icons go as they grow, what's on it and in what order, when it's up, what a click
and a right-click do, its pins, and Windows' taskbar hidden only while it's on and always put back."""
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

from tests.support import siri  # noqa: F401  temp APPDATA and the tripwires, before anything else
import dock
import settings

KINDS = ["icon"] * 3 + ["gap"] + ["icon"] * 2


class Row(unittest.TestCase):
    def test_at_rest_nothing_grows_and_the_slots_are_even(self):
        places, x0, x1 = dock.row(KINDS, None, 0.0, 1.0)
        self.assertEqual([g for _, g in places], [1.0] * len(KINDS))
        self.assertAlmostEqual(x1 - x0, dock.at_rest(KINDS, 1.0))
        self.assertAlmostEqual(places[1][0] - places[0][0], dock.SLOT)

    def test_the_icon_pointed_at_grows_most_and_stays_under_the_pointer(self):
        rest, _, _ = dock.row(KINDS, None, 0.0, 1.0)
        px = rest[1][0] + 7  # a little right of the middle icon's middle
        places, x0, x1 = dock.row(KINDS, px, 1.0, 1.0)
        grows = [g for _, g in places]
        self.assertAlmostEqual(max(grows), grows[1], places=6)
        self.assertGreater(grows[1], 1.5)
        self.assertEqual(grows[3], 1.0)  # a divider never grows
        middle, grow = places[1]
        half = dock.SLOT * grow / 2
        self.assertTrue(middle - half <= px <= middle + half)  # still over the same icon
        self.assertGreater(x1 - x0, dock.at_rest(KINDS, 1.0))  # the glass widens with them

    def test_slots_have_a_divider_before_open_apps_and_before_the_folders(self):
        items = [{"kind": k} for k in ("start", "search", "pin", "pin", "app", "folder", "folder")]
        self.assertEqual([k for k, _ in dock.slots(items)],
                         ["icon", "icon", "icon", "icon", "gap", "icon", "gap", "icon", "icon"])
        self.assertEqual([k for k, _ in dock.slots([{"kind": "start"}, {"kind": "folder"}])], ["icon", "gap", "icon"])


class Up(unittest.TestCase):
    def test_when_its_up(self):
        self.assertFalse(dock.up("fixed", True, False, True))  # never over a full-screen app
        self.assertTrue(dock.up("fixed", False, True, False))
        self.assertTrue(dock.up("smart", False, False, False))
        self.assertFalse(dock.up("smart", False, True, False))  # a window's over where it sits
        self.assertTrue(dock.up("smart", False, True, True))  # unless it's called up
        self.assertFalse(dock.up("peek", False, False, False))
        self.assertTrue(dock.up("peek", False, False, True))


class Clicks(unittest.TestCase):
    def test_what_a_click_does(self):
        app = {"kind": "pin", "path": "C:/x.lnk", "windows": [11, 12]}
        self.assertEqual(dock.action({"kind": "start"}, None), ("start",))
        self.assertEqual(dock.action({"kind": "search"}, None), ("search",))  # Windows' own search
        self.assertEqual(dock.action(dict(app, windows=[]), None), ("open", "C:/x.lnk"))
        self.assertEqual(dock.action(app, 99), ("front", 11))  # brought to the front
        self.assertEqual(dock.action(app, 11), ("front", 12))  # in front: on to its next window
        self.assertEqual(dock.action(app, 12), ("front", 11))
        self.assertEqual(dock.action(dict(app, windows=[11]), 11), ("down", 11))  # its only one: put down
        self.assertIsNone(dock.action({"kind": "app", "path": "", "windows": []}, None))

    def test_the_right_click_menu(self):
        pin = {"kind": "pin", "name": "Notepad", "path": "C:/n.lnk", "exe": "C:/notepad.exe", "windows": [1, 2]}
        self.assertEqual([w for _, w in dock.menu(pin, {"c:/n.lnk"})], [None, "new", "unpin", "close"])
        self.assertEqual(dock.menu(pin, set())[-1][0], "Close 2 windows")
        app = {"kind": "app", "name": "Paint", "path": "C:/paint.exe", "exe": "C:/paint.exe", "windows": [3]}
        self.assertEqual([w for _, w in dock.menu(app, set())], [None, "new", "pin", "close"])
        her = dict(app, her=True)
        self.assertEqual([w for _, w in dock.menu(her, set())], [None, "close"])  # never pinned, nor opened again
        self.assertEqual([w for _, w in dock.menu({"kind": "folder", "name": "Downloads"}, set())], [None, "open"])


class Pins(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        for name in ("Notepad.lnk", "File Explorer.lnk", "desktop.ini"):
            open(os.path.join(self.dir, name), "w").close()
        self.old = dock.TASKBAR_PINS
        dock.TASKBAR_PINS = self.dir
        settings.put("dock_pins", None)

    def tearDown(self):
        dock.TASKBAR_PINS = self.old
        settings.put("dock_pins", None)

    def test_the_taskbars_pins_the_first_time_file_explorer_first(self):
        got = dock.pins()
        self.assertEqual([p["name"] for p in got], ["File Explorer", "Notepad"])
        self.assertEqual(settings.get("dock_pins"), got)  # kept: from now on they're the dock's own
        settings.put("dock_pins", [{"path": "C:/a.exe", "name": "A"}])
        self.assertEqual(dock.pins(), [{"path": "C:/a.exe", "name": "A"}])

    def test_whats_on_it_open_windows_by_their_app_her_own_by_her_name(self):
        notepad = os.path.join(self.dir, "Notepad.lnk")
        explorer = os.path.join(self.dir, "File Explorer.lnk")
        windows = [(1, r"C:\Windows\notepad.exe", "Untitled - Notepad"), (2, r"C:\apps\paint.exe", "Paint"),
                   (3, r"C:\Windows\explorer.exe", "Downloads - File Explorer"),
                   (4, r"C:\apps\paint.exe", "Paint 2"), (5, r"C:\py\pythonw.exe", "Hey Harry")]
        targets = {notepad: r"C:\Windows\notepad.exe", explorer: ""}  # Windows 11's File Explorer has no path
        with mock.patch.object(dock.win, "open_windows", return_value=windows), \
                mock.patch.object(dock.win, "_pid", side_effect=lambda h: os.getpid() if h == 5 else 1), \
                mock.patch.object(dock.win, "file_description", return_value=""), \
                mock.patch.object(dock, "_target", side_effect=lambda p: targets.get(p, p)), \
                mock.patch("island_art.exe_icon", return_value=None), \
                mock.patch("island_art.file_icon", return_value=None), \
                mock.patch("island_art.window_icon", return_value=None):
            items = dock.read([{"path": explorer, "name": "File Explorer"}, {"path": notepad, "name": "Notepad"},
                               {"path": os.path.join(self.dir, "Gone.lnk"), "name": "Gone"}], 64)
        self.assertEqual([(i["kind"], i["name"]) for i in items],
                         [("start", "Start"), ("search", "Search"), ("pin", "File Explorer"), ("pin", "Notepad"),
                          ("app", "Paint"), ("app", "Harry"), ("folder", "Downloads")])  # no Recycle Bin
        by = {i["name"]: i for i in items}
        self.assertEqual(by["Notepad"]["windows"], [1])
        self.assertEqual(by["File Explorer"]["windows"], [3])  # by its name, as it has no path
        self.assertEqual(by["Paint"]["windows"], [2, 4])  # one icon an app
        self.assertTrue(by["Harry"]["her"])


class Taskbar(unittest.TestCase):
    def setUp(self):
        self.shown = []
        self.patches = [mock.patch.object(dock, "_taskbar", return_value=77),
                        mock.patch.object(dock._user32, "IsWindowVisible", return_value=True),
                        mock.patch.object(dock._user32, "ShowWindow", side_effect=lambda h, c: self.shown.append(c))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        if os.path.exists(dock.FLAG):
            os.remove(dock.FLAG)

    def test_hidden_with_a_flag_and_shown_again_without(self):
        dock.hide_taskbar()
        self.assertEqual(self.shown, [dock.SW_HIDE])
        self.assertTrue(os.path.exists(dock.FLAG))
        dock.show_taskbar()
        self.assertEqual(self.shown, [dock.SW_HIDE, dock.SW_SHOW])
        self.assertFalse(os.path.exists(dock.FLAG))

    def test_a_last_run_that_left_it_hidden_is_put_right(self):
        dock.restore_leftover()
        self.assertEqual(self.shown, [])  # nothing left: nothing done
        open(dock.FLAG, "w").close()
        dock.restore_leftover()
        self.assertEqual(self.shown, [dock.SW_SHOW])
        self.assertFalse(os.path.exists(dock.FLAG))

    def test_the_watchdog_waits_on_her_and_has_no_window(self):
        with mock.patch.object(dock.subprocess, "Popen") as popen:
            dock.watchdog()
        args, kwargs = popen.call_args
        self.assertEqual(os.path.basename(args[0][0]).lower(), "pythonw.exe")
        self.assertEqual(args[0][3:], [str(os.getpid()), dock.FLAG])
        self.assertIn("ShowWindow(bar, 5)", args[0][2])
        compile(args[0][2], "watchdog", "exec")  # it's whole Python


class NotchTaskbar(unittest.TestCase):
    """7 November 2026, the owner's ask after NotchPixel's: a taskbar hanging from the bottom of the screen, its icons
    not growing, with the network and the volume, the time and the bell at its right opening Windows' own."""

    def test_its_cells_are_the_slots_then_the_tray(self):
        cells, width = dock.bar_cells(KINDS, 60.0, 1.0)
        self.assertEqual([c[0] for c in cells], list(range(len(KINDS))) + ["sep", "quick", "clock", "bell"])
        self.assertEqual(cells[0][1], dock.BAR_PAD)
        self.assertAlmostEqual(cells[1][1] - cells[0][1], dock.BAR_SLOT)  # evenly apart: nothing grows
        self.assertAlmostEqual(cells[3][2] - cells[3][1], dock.BAR_GAP)  # the divider
        self.assertAlmostEqual(cells[-2][2] - cells[-2][1], 80.0)  # the time and the date, and 20 more
        self.assertAlmostEqual(width, cells[-1][2] + dock.BAR_PAD)
        self.assertAlmostEqual(dock.bar_cells(KINDS, 90.0, 1.5)[1], 1.5 * width)

    def test_it_hangs_from_the_bottom_its_shoulders_curving_into_it(self):
        xs = np.arange(0, 200, dtype=np.float32) + 0.5
        ys = (np.arange(0, 60, dtype=np.float32) + 0.5)[:, None]
        sd = dock.bar_shape(xs, ys, 50, 150, 10, 56, 12, 10, True)
        self.assertLess(sd[30, 100], 0)  # inside
        self.assertLess(sd[55, 51], 0)  # square where it meets the edge
        self.assertLess(sd[55, 45], 0)  # a shoulder, out past its side along the edge
        self.assertGreater(sd[40, 45], 0)  # but not up its side
        self.assertGreater(sd[11, 51], 0)  # its top corners round
        self.assertGreater(sd[58, 100], 0)  # nothing below the bottom of the screen
        floating = dock.bar_shape(xs, ys, 50, 150, 10, 56, 12, 10, False)
        self.assertGreater(floating[55, 51], 0)  # floating, round all round
        self.assertGreater(floating[55, 45], 0)

    def test_the_tray_opens_windows_own(self):
        self.assertEqual(dock.tray_keys("quick", 22631), (0x5B, 0x41))  # Windows+A, quick settings
        self.assertEqual(dock.tray_keys("clock", 22631), (0x5B, 0x4E))  # Windows+N, notifications and the calendar
        self.assertEqual(dock.tray_keys("bell", 22631), (0x5B, 0x4E))
        self.assertEqual(dock.tray_keys("bell", 19045), (0x5B, 0x41))  # Windows 10's action centre

    def test_the_taskbar_is_the_look_to_start_with(self):
        self.addCleanup(settings.put, "dock_style", None)
        self.assertEqual(settings.DEFAULTS["dock_style"], "taskbar")
        with mock.patch.object(dock, "Taskbar", return_value="bar"), mock.patch.object(dock, "Dock", return_value="dock"):
            self.assertEqual(dock.make(None), "bar")
            settings.put("dock_style", "dock")
            self.assertEqual(dock.make(None), "dock")

    def test_whats_under_the_pointer(self):
        bar = object.__new__(dock.Taskbar)
        bar.slots = dock.slots([{"kind": k} for k in ("start", "search", "pin", "app")])  # three, a divider, one
        bar.cells, bar.bar_w = dock.bar_cells([k for k, _ in bar.slots], 50.0, 1.0)

        def at(what):
            cell = next(c for c in bar.cells if c[0] == what)
            bar.px = (cell[1] + cell[2]) / 2
            return bar._cell()
        self.assertEqual(at(2), 2)  # the pin
        self.assertIsNone(at(3))  # the divider
        self.assertEqual(at(4), 3)  # the open app, the fourth item
        self.assertEqual(at("clock"), "clock")
        self.assertIsNone(at("sep"))
        bar.px = None
        self.assertIsNone(bar._cell())
        places, x0, x1 = bar.layout()
        self.assertEqual(len(places), len(bar.slots))
        self.assertEqual((x0, x1), (0.0, bar.bar_w))
        self.assertEqual(bar._reach(), 0.0)  # a click just over it is the window's under it

    def test_the_time_and_the_date_in_windows_own_words(self):
        words = dock.clock_words()
        self.assertEqual(len(words), 3)
        self.assertTrue(all(words))


if __name__ == "__main__":
    unittest.main()
