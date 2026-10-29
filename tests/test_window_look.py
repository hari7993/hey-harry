"""Her window's look (29 October 2026, the owner's pick, hero-03 on 21st.dev, then a few colours and parts): a page's
name in spaced capitals, the wheel scrolling a long page from anywhere on it but a table, and a ticked box orange with a
white tick, not clam's cross ("what is this x"). Nothing here opens her window; the tick's picture needs a hidden Tk."""
import unittest
from types import SimpleNamespace
from tkinter import ttk
from unittest import mock

from tests.support import siri  # noqa: F401  first: temp APPDATA and the tripwires, before anything of hers

import assistant_ui


class Words(unittest.TestCase):
    def test_a_pages_name_in_spaced_capitals(self):
        self.assertEqual(assistant_ui.caps("To-do"), "T\u200aO\u200a-\u200aD\u200aO")

    def test_how_far_from_a_line(self):
        self.assertAlmostEqual(assistant_ui._to_line(5, 3, (0, 0), (10, 0)), 3)
        self.assertAlmostEqual(assistant_ui._to_line(13, 4, (0, 0), (10, 0)), 5)  # past its end: from the end


class Wheel(unittest.TestCase):
    """29 October 2026: the wheel scrolled a page only over its margins, and the owner found it very hard to."""

    def window(self, under, mapped=True):
        canvas = mock.Mock()
        page = SimpleNamespace(outer=".page", canvas=canvas, bar=mock.Mock(winfo_ismapped=lambda: mapped))
        app = SimpleNamespace(pages={"settings": page}, current_tab="settings",
                              root=mock.Mock(winfo_containing=lambda x, y: under))
        return app, canvas

    def turn(self, app, delta=-120):
        assistant_ui.AssistantWindow._wheel(app, SimpleNamespace(x_root=10, y_root=10, delta=delta))

    def test_over_words_deep_in_the_page_it_scrolls_three_steps_a_notch(self):
        app, canvas = self.window(".page.!canvas.!frame.!frame3.!label7")
        self.turn(app)
        canvas.yview_scroll.assert_called_once_with(3, "units")

    def test_a_touchpads_small_turns_add_up(self):
        app, canvas = self.window(".page.!canvas.!frame.!label")
        for _ in range(3):
            self.turn(app, delta=-30)  # three quarters of a notch: two steps and a bit
        self.assertEqual(sum(c.args[0] for c in canvas.yview_scroll.call_args_list), 2)

    def test_never_off_the_page_over_a_table_or_with_nothing_to_scroll(self):
        for under, mapped in ((".pages2.!label", True), (".page.!canvas.!frame.!label", False), (None, True),
                              (mock.Mock(spec=ttk.Treeview), True)):  # a table scrolls itself
            app, canvas = self.window(under, mapped)
            self.turn(app)
            canvas.yview_scroll.assert_not_called()
        app, canvas = self.window(".page.!label")
        app.pages = {"settings": SimpleNamespace(outer=".page")}  # a page that doesn't scroll
        self.turn(app)


class Tick(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no display for Tk: {exc}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def box(self, on, hot=False):
        app = SimpleNamespace(root=self.root, s=1.5, px=lambda n: round(n * 1.5))
        return assistant_ui.AssistantWindow._tick_box(app, on, hot)

    def test_ticked_is_orange_with_a_white_tick_not_a_cross(self):
        on, off = self.box(True), self.box(False)
        n = on.width()
        self.assertEqual((n, on.height()), (21, 21))
        orange = tuple(int(assistant_ui.ACCENT[i:i + 2], 16) for i in (1, 3, 5))
        at = lambda box, x, y: tuple(box.get(x, y))[:3]
        self.assertEqual(at(on, 2, 4), orange)  # up on its left, clear of the tick
        self.assertEqual(at(on, 9, 14), (255, 255, 255))  # the tick's corner, low in the middle
        self.assertEqual(at(on, 14, 14), orange)  # where a cross's arm would be: none
        self.assertEqual(at(off, n // 2, n // 2), (255, 255, 255))  # not ticked: white inside a hairline
        self.assertNotEqual(at(off, n // 2, 0), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
