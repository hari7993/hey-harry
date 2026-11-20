"""Her window as a dashboard (20 November 2026, the owner's asks): the tabs in groups with one that folds, her quick
actions and what they find, and her frosted glass (glass.py). Nothing here opens her window."""
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.support import siri  # noqa: F401  first: temp APPDATA and the tripwires, before anything of hers

import assistant_ui
import glass
import settings


class Groups(unittest.TestCase):
    def test_every_tab_is_in_one_group_with_an_icon(self):
        grouped = [key for _, keys in assistant_ui.NAV for key in keys]
        self.assertEqual(sorted(grouped), sorted(key for key, _ in assistant_ui.TABS))
        self.assertEqual(len(grouped), len(set(grouped)))
        for key in grouped:
            self.assertTrue(assistant_ui.ICONS.get(key), key)
        self.assertIsNone(assistant_ui.NAV[0][0])  # the first has no name: Home and your day
        self.assertLessEqual(assistant_ui.NAV_FOLDS, {name for name, _ in assistant_ui.NAV})

    def app(self, shown=("home", "todo", "mem")):
        return SimpleNamespace(nav_y={key: 100 + i * 30 for i, key in enumerate(shown)}, nav_h=30, nav_gap=30,
                               group_y={"What she knows": 40, "More": 300}, current_tab="home",
                               _select_tab=mock.Mock())

    def test_the_tab_and_the_group_under_the_mouse(self):
        app = self.app()
        row = lambda y: assistant_ui.AssistantWindow._side_row(app, y)
        self.assertEqual((row(100), row(129), row(131), row(190), row(20)), ("home", "home", "todo", None, None))
        group = lambda y: assistant_ui.AssistantWindow._side_group(app, y)
        self.assertEqual((group(310), group(45), group(200)), ("More", None, None))  # only one that folds

    def test_up_and_down_go_through_the_tabs_shown_only(self):
        app = self.app()
        assistant_ui.AssistantWindow._tab_step(app, -1)
        app._select_tab.assert_called_with("mem")  # round from the top to the last one shown, never a folded one
        assistant_ui.AssistantWindow._tab_step(app, 1)
        app._select_tab.assert_called_with("todo")

    def test_a_group_folds_and_is_kept_and_another_doesnt(self):
        app = SimpleNamespace(nav_open=set(), _lay_nav=mock.Mock(), _slide_nav_bar=mock.Mock(), current_tab="home")
        self.addCleanup(settings.put, "nav_open", None)
        assistant_ui.AssistantWindow._fold_group(app, "More")
        self.assertEqual((app.nav_open, settings.get("nav_open")), ({"More"}, ["More"]))
        assistant_ui.AssistantWindow._fold_group(app, "More")
        self.assertEqual(settings.get("nav_open"), [])
        assistant_ui.AssistantWindow._fold_group(app, "Setup")
        self.assertEqual(app._lay_nav.call_count, 2)


class QuickActions(unittest.TestCase):
    def palette(self):
        did = []
        actions = [("i", "Settings", "Go to", lambda: did.append("settings")),
                   ("i", "Settings: Safety", "Section", lambda: did.append("safety")),
                   ("i", "Dictation history", "Go to", lambda: did.append("hist")),
                   ("i", "Keep this window on top", "Window", lambda: did.append("top"))]
        app = SimpleNamespace(controls=mock.Mock())
        return SimpleNamespace(actions=actions, app=app), did

    def names(self, p, query):
        return [a[1] for a in assistant_ui.Palette.matches(p, query)]

    def test_nothing_typed_shows_them_all(self):
        p, _ = self.palette()
        self.assertEqual(len(self.names(p, "")), 4)

    def test_every_word_typed_is_looked_for_and_a_start_comes_first(self):
        p, _ = self.palette()
        self.assertEqual(self.names(p, "set")[:2], ["Settings", "Settings: Safety"])
        self.assertEqual(self.names(p, "safety settings")[0], "Settings: Safety")
        self.assertEqual(self.names(p, "window")[0], "Keep this window on top")  # by its kind too
        self.assertEqual(self.names(p, "dict")[0], "Dictation history")

    def test_anything_else_typed_is_asked_of_her(self):
        p, _ = self.palette()
        found = assistant_ui.Palette.matches(p, "  what's the  weather ")
        self.assertEqual(len(found), 1)
        self.assertIn("what's the weather", found[0][1])
        found[0][3]()
        p.app.controls.put.assert_called_once_with(("typed", "what's the weather"))

    def test_the_one_picked_is_done_once_theyre_put_away(self):
        p, did = self.palette()
        order = []
        p.shown, p.at = p.actions, 2
        p.close = lambda: order.append("closed")
        p.actions[2] = (*p.actions[2][:3], lambda: order.append("done"))
        p.shown = p.actions
        assistant_ui.Palette.use(p)
        self.assertEqual(order, ["closed", "done"])


class Glass(unittest.TestCase):
    def test_a_pane_is_the_wallpaper_washed_towards_white(self):
        import numpy as np
        frosted = np.full((4, 6, 3), 100, np.uint8)
        self.assertTrue((glass.pane(frosted, 0, 0, 16, 8, 0.8) == 224).all())  # 100 a fifth, white four fifths
        self.assertTrue((glass.pane(frosted, 0, 0, 16, 8, 1.0) == 255).all())

    def test_the_small_picture_is_drawn_out_smooth_behind_a_panel_and_its_edge_carries_on(self):
        import numpy as np
        frosted = np.zeros((4, 6, 3), np.uint8)
        frosted[:, 3:] = 200  # dark on the left of the screen, light on the right
        n = glass.SMALLER
        row = glass.pane(frosted, 0, n, 6 * n, 1, 0.0)[0, :, 0].astype(int)
        self.assertEqual((row[0], row[-1]), (0, 200))
        self.assertTrue((np.diff(row) >= 0).all())
        self.assertLessEqual(np.diff(row).max(), 200 // n + 1)  # a slope between them, never a step
        off = glass.pane(frosted, 6 * n - 2, 4 * n - 2, 40, 30, 0.0)  # past the right and the bottom
        self.assertEqual(off.shape, (30, 40, 3))
        self.assertTrue((off == 200).all())
        ppm = glass.cut(frosted, 0, 0, 5, 3, 0.5)
        self.assertTrue(ppm.startswith(b"P6 5 3 255 "))
        self.assertEqual(len(ppm), len(b"P6 5 3 255 ") + 5 * 3 * 3)

    def test_a_panels_glass_is_made_at_one_pixel_in_four_so_a_page_opens_smooth(self):
        """20 November 2026, the owner: "very slow ... not smooth". Every pixel of a sidebar and the top was 86 ms."""
        import time
        import numpy as np
        frosted = np.broadcast_to(np.linspace(0, 255, 240).astype(np.uint8)[None, :, None], (150, 240, 3))
        small = glass.pane(frosted, 300, 200, 330, 1050, 0.8, assistant_ui.GLASS_STEP)
        self.assertEqual(small.shape, (263, 83, 3))  # a sixteenth of its pixels
        whole = glass.pane(frosted, 300, 200, 330, 1050, 0.8)
        near = whole[2::4, 2::4].astype(int)  # the same glass, at the pixels it was made for
        self.assertLess(abs(small[:near.shape[0], :near.shape[1]].astype(int) - near).max(), 3)
        began = time.perf_counter()
        for _ in range(5):
            glass.cut(frosted, 300, 200, 330, 1050, 0.8, assistant_ui.GLASS_STEP)
            glass.cut(frosted, 630, 200, 1260, 260, 0.87, assistant_ui.GLASS_STEP)
        self.assertLess((time.perf_counter() - began) / 5, 0.03)

    def test_the_wallpaper_frosted_to_the_screens_size_and_none_without_one(self):
        import cv2
        import numpy as np
        folder = tempfile.mkdtemp(prefix="heyharry-glass-")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "wall.png")
        picture = np.zeros((90, 160, 3), np.uint8)
        picture[:, 80:] = (40, 40, 220)  # half black, half red
        cv2.imwrite(path, picture)
        frosted = glass.frost((320, 200), path)
        self.assertEqual(frosted.shape, (200 // glass.SMALLER, 320 // glass.SMALLER, 3))  # kept small
        self.assertLess(frosted.nbytes, 4000)
        self.assertGreater(int(frosted[12, 38, 0]), int(frosted[12, 2, 0]) + 60)  # red still on the right, in RGB
        full = glass.pane(frosted, 0, 100, 320, 1, 0.0)[0, :, 0].astype(int)
        self.assertLess(abs(np.diff(full)).max(), 12)  # and no hard line between them: blurred
        self.assertIsNone(glass.frost((320, 200), os.path.join(folder, "none.png")))
        with mock.patch.object(glass, "wallpaper", lambda: None):
            self.assertIsNone(glass.frost((320, 200)))

    def test_its_on_till_turned_off(self):
        self.assertIs(settings.DEFAULTS["glass"], True)


if __name__ == "__main__":
    unittest.main()
