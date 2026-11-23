"""The look's shared parts (ui_kit.py, 22 November 2026): the curves Hedwig's motion runs on, colours mixed, the rounded
shapes drawn with soft edges, Windows' title bar painted in her sidebar's colour, and a window coming in and going out.
Nothing here opens her window; the pictures need a hidden Tk."""
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.support import siri  # noqa: F401  first: temp APPDATA and the tripwires, before anything of hers

import tkinter as tk

import ui_kit


class Curves(unittest.TestCase):
    def test_every_curve_starts_at_nothing_and_ends_whole(self):
        for name in ("POP", "ARRIVE", "STATE", "SPRING", "GLIDE"):
            curve = getattr(ui_kit, name)
            with self.subTest(curve=name):
                self.assertEqual((curve(0.0), curve(1.0)), (0.0, 1.0))
                self.assertEqual((curve(-1.0), curve(2.0)), (0.0, 1.0))  # outside it, held at its ends

    def test_a_straight_curve_is_straight_and_ease_in_out_is_even_in_the_middle(self):
        straight = ui_kit.bezier(0, 0, 1, 1)
        self.assertAlmostEqual(straight(0.3), 0.3, places=4)
        self.assertAlmostEqual(ui_kit.bezier(.42, 0, .58, 1)(0.5), 0.5, places=4)

    def test_a_curve_that_arrives_is_quick_first_then_settling(self):
        for curve in (ui_kit.POP, ui_kit.ARRIVE):
            self.assertGreater(curve(0.2), 0.2 * 2)  # well on its way a fifth in
            steps = [curve(i / 40) for i in range(41)]
            self.assertEqual(steps, sorted(steps))  # never backwards
            self.assertGreater(steps[10] - steps[0], steps[40] - steps[30])

    def test_the_spring_goes_past_its_end_and_comes_back(self):
        top = max(ui_kit.SPRING(i / 100) for i in range(101))
        self.assertGreater(top, 1.02)
        self.assertLess(top, 1.2)

    def test_a_known_value_of_the_css_curve(self):
        # cubic-bezier(.25, .1, .25, 1), CSS's "ease", is 0.8024 at half way (the spec's own figure)
        self.assertAlmostEqual(ui_kit.bezier(.25, .1, .25, 1)(0.5), 0.8024, places=3)


class Colours(unittest.TestCase):
    def test_mixed_a_part_of_the_way(self):
        self.assertEqual(ui_kit.mix("#000000", "#ffffff", 0.5), "#808080")
        self.assertEqual(ui_kit.mix("#ff0000", "#0000ff", 0.0), "#ff0000")
        self.assertEqual(ui_kit.mix("#ff0000", "#0000ff", 1.0), "#0000ff")

    def test_a_curve_that_overshoots_never_leaves_the_colours(self):
        self.assertEqual(ui_kit.mix("#000000", "#ffffff", 1.2), "#ffffff")
        self.assertEqual(ui_kit.mix("#000000", "#ffffff", -0.2), "#000000")


class TheTitleBar(unittest.TestCase):
    def test_colorref_is_blue_green_red(self):
        self.assertEqual(ui_kit.colorref("#ff8000"), 0x0080FF)
        self.assertEqual(ui_kit.colorref("#212121"), 0x212121)

    def test_windows_11_gets_the_caption_its_words_and_its_edge(self):
        attrs = dict(ui_kit.chrome_attrs(22631, "#212121", "#ffffff", True))
        self.assertEqual(attrs, {20: 1, 35: 0x212121, 36: 0xFFFFFF, 34: 0x212121})

    def test_windows_10_only_gets_its_buttons_light_or_dark(self):
        self.assertEqual(ui_kit.chrome_attrs(19045, "#212121", "#ffffff", True), [(20, 1)])
        self.assertEqual(ui_kit.chrome_attrs(19045, "#f6f6f7", "#0a0a0a", False), [(20, 0)])

    def test_an_older_windows_is_left_alone(self):
        self.assertEqual(ui_kit.chrome_attrs(17763, "#212121", "#ffffff", True), [])
        self.assertEqual(ui_kit.chrome_attrs(0, "#212121", "#ffffff", True), [])

    def test_it_is_set_one_attribute_at_a_time_and_one_that_wont_isnt_the_end_of_it(self):
        done = []

        def set_attribute(attr, value):
            if attr == 36:
                raise OSError("this build has no such thing")
            done.append((attr, value))
        got = ui_kit.title_bar(None, "#212121", "#ffffff", True, build=22631, set_attribute=set_attribute)
        self.assertEqual(got, [20, 35, 34])
        self.assertEqual(done[0], (20, 1))

    def test_with_nothing_it_can_do_it_does_nothing(self):
        set_attribute = mock.Mock()
        self.assertEqual(ui_kit.title_bar(None, "#fff000", "#000000", True, build=10240, set_attribute=set_attribute), [])
        set_attribute.assert_not_called()


class Shapes(unittest.TestCase):
    def test_the_middle_is_the_fill_and_a_corner_is_what_is_behind(self):
        box = ui_kit.rrect(60, 40, 12, "#ffffff", "#000000")
        self.assertEqual(box.shape, (40, 60, 3))
        self.assertEqual(tuple(box[20, 30]), (255, 255, 255))
        self.assertEqual(tuple(box[0, 0]), (0, 0, 0))
        self.assertEqual(tuple(box[20, 0]), (255, 255, 255))  # a straight side is the fill right to its edge

    def test_the_edge_of_a_corner_is_soft_not_a_step(self):
        box = ui_kit.rrect(60, 40, 12, "#ffffff", "#000000")
        row = box[2, :16, 0].astype(int)  # along the top of its top-left corner: black, then grey, then white
        self.assertTrue((row[1:] >= row[:-1]).all())
        self.assertTrue(((row > 0) & (row < 255)).sum() >= 1)

    def test_a_line_runs_round_just_inside_the_edge(self):
        box = ui_kit.rrect(60, 40, 12, "#ffffff", "#eeeeee", line="#cc0000", lw=2)
        self.assertEqual(tuple(box[20, 0]), (204, 0, 0))  # the left side is the line
        self.assertEqual(tuple(box[20, 1]), (204, 0, 0))
        self.assertEqual(tuple(box[20, 30]), (255, 255, 255))

    def test_half_the_height_is_a_pill_and_half_both_a_circle(self):
        pill = ui_kit.rrect(60, 20, 10, "#ffffff", "#000000")
        self.assertGreater(int(pill[10, 0, 0]), 240)  # the end of a pill at its middle: all but its very edge fill
        self.assertLess(int(pill[0, 0, 0]), 10)  # round above and below it
        circle = ui_kit.rrect(20, 20, 10, "#ffffff", "#000000")
        self.assertLess(int(circle[1, 1, 0]), 10)
        self.assertEqual(tuple(circle[10, 10]), (255, 255, 255))

    def test_the_four_corners_are_mirrors_of_each_other(self):
        import numpy as np
        tl, tr, bl, br = ui_kit.corners(10, "#ffffff", "#000000", "#999999")
        self.assertEqual([c.shape for c in (tl, tr, bl, br)], [(10, 10, 3)] * 4)
        self.assertTrue((tl == tr[:, ::-1]).all())
        self.assertTrue((tl == bl[::-1]).all())
        self.assertTrue((tl == br[::-1, ::-1]).all())
        self.assertTrue(np.array_equal(tl[0, 0], [0, 0, 0]))

    def test_a_chevron_has_ink_in_its_middle_and_none_in_its_corners(self):
        down = ui_kit.chevron(16, "#000000", "#ffffff")
        self.assertLess(int(down[10, 8, 0]), 100)  # the point of the V, below the middle
        self.assertEqual(tuple(down[0, 0]), (255, 255, 255))
        up = ui_kit.chevron(16, "#000000", "#ffffff", up=True)
        self.assertTrue((up == down[::-1]).all())

    def test_a_margin_of_the_back_colour_puts_a_shape_where_it_should_be(self):
        dot = ui_kit.rrect(4, 4, 2, "#ffffff", "#000000")
        padded = ui_kit.pad(dot, "#ff0000", left=3, top=1, right=2, bottom=0)
        self.assertEqual(padded.shape, (5, 9, 3))
        self.assertEqual(tuple(padded[0, 0]), (255, 0, 0))  # margin
        self.assertEqual(tuple(padded[3, 5]), (255, 255, 255))  # the dot, moved by the margin
        self.assertTrue((padded[1:, 3:7] == dot).all())

    def test_as_ppm_for_tk(self):
        data = ui_kit.ppm(ui_kit.rrect(5, 3, 1, "#ffffff", "#000000"))
        self.assertTrue(data.startswith(b"P6 5 3 255 "))
        self.assertEqual(len(data), len(b"P6 5 3 255 ") + 5 * 3 * 3)


class Pictures(unittest.TestCase):
    """The shapes as Tk pictures, made once for each look, on a hidden Tk."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"no Tk here: {exc}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_a_picture_is_made_once_for_a_look(self):
        a = ui_kit.corner_images(self.root, 8, "#ffffff", "#f0f0f0", "#cccccc")
        b = ui_kit.corner_images(self.root, 8, "#ffffff", "#f0f0f0", "#cccccc")
        self.assertIs(a, b)
        self.assertEqual((a[0].width(), a[0].height()), (8, 8))
        self.assertIsNot(a, ui_kit.corner_images(self.root, 8, "#ffffff", "#f0f0f0", None))

    def test_the_cache_is_the_applications_whichever_widget_asks(self):
        frame = tk.Frame(self.root)
        self.assertIs(ui_kit.images(frame), ui_kit.images(self.root))

    def test_a_nine_patch_is_big_enough_to_stretch(self):
        image = ui_kit.nine(self.root, 6, "#eeeeee", "#ffffff")
        b = 6 + 1  # the border ttk keeps as it is
        self.assertEqual((image.width() - 2 * b, image.height() - 2 * b), ui_kit.TILE)  # and a middle worth tiling
        self.assertGreaterEqual(ui_kit.TILE[0], 128)  # 22 November 2026: at 2 px, the Keys page took 1.8 s to open

    def test_the_backdrop_lays_its_corners_and_lines_to_the_size_it_has(self):
        frame = tk.Frame(self.root, width=120, height=80)
        frame.pack()
        back = ui_kit.Backdrop(frame, 10, "#ffffff", "#dddddd", "#ffffff")
        self.root.deiconify()
        try:
            self.root.update()
            c = back.canvas
            w, h = c.winfo_width(), c.winfo_height()
            self.assertEqual((w, h), (120, 80))
            self.assertEqual(c.coords(back.tiles[3]), [w - 10, h - 10])  # the bottom right corner sits in its corner
            self.assertEqual(c.coords(back.edges[0]), [10, 0, w - 10, 1])  # the top line between the corners
            frame.configure(width=200)
            self.root.update()
            self.assertEqual(c.coords(back.tiles[1]), [190, 0])  # and follows the frame as it grows
        finally:
            self.root.withdraw()


class ComingAndGoing(unittest.TestCase):
    """ui_kit.pop on a stand-in window and clock: eased, left where it should be, and nothing left running."""

    def window(self):
        top = mock.Mock()
        top.geometry.side_effect = lambda *a: "300x200+100+50" if not a else None
        return top

    def run_frames(self, top, **kw):
        frames, done = [], []
        root = SimpleNamespace(after=lambda ms, fn: frames.append(fn))
        with mock.patch.object(ui_kit, "motion_ok", lambda: True):
            ui_kit.pop(top, root, done=lambda: done.append(True), **kw)
            while frames:
                time.sleep(0.01)
                frames.pop(0)()
        return done

    def test_coming_in_it_ends_whole_and_in_its_place(self):
        top = self.window()
        self.assertEqual(self.run_frames(top, enter=True, ms=40, rise=6), [True])
        self.assertEqual(top.attributes.call_args_list[-1].args, ("-alpha", 1.0))
        self.assertEqual(top.geometry.call_args_list[-1].args, ("300x200+100+50",))
        started = top.attributes.call_args_list[0].args[1]
        self.assertLess(started, 0.9)

    def test_going_out_it_ends_clear_for_its_owner_to_put_it_away(self):
        top = self.window()
        self.assertEqual(self.run_frames(top, enter=False, ms=40, rise=4), [True])
        self.assertEqual(top.attributes.call_args_list[-1].args, ("-alpha", 0.0))
        self.assertEqual(top.geometry.call_args_list[-1].args, ("300x200+100+46",))  # 4 px up

    def test_a_veil_is_never_more_solid_than_it_asks(self):
        top = self.window()
        self.run_frames(top, enter=True, ms=40, rise=0, peak=0.14)
        self.assertLessEqual(max(c.args[1] for c in top.attributes.call_args_list), 0.14)
        top.geometry.assert_called_once_with()  # rise 0: it's never moved, only asked where it is

    def test_with_windows_animations_off_it_just_is_or_is_gone(self):
        for enter, alpha in ((True, 1.0), (False, 0.0)):
            top, done = self.window(), []
            with mock.patch.object(ui_kit, "motion_ok", lambda: False):
                ui_kit.pop(top, SimpleNamespace(after=lambda *a: self.fail("a timer")), enter=enter,
                           done=lambda: done.append(True))
            self.assertEqual((top.attributes.call_args_list[-1].args, done), (("-alpha", alpha), [True]))

    def test_a_window_closed_meanwhile_ends_quietly(self):
        top = self.window()
        top.attributes.side_effect = tk.TclError("bad window path name")
        frames = []
        with mock.patch.object(ui_kit, "motion_ok", lambda: True):
            ui_kit.pop(top, SimpleNamespace(after=lambda ms, fn: frames.append(fn)), enter=True)
        self.assertEqual(frames, [])  # no timer left running

    def test_the_place_of_a_window_on_a_screen_to_the_left(self):
        top = mock.Mock()
        top.geometry.return_value = "300x200+-1920+-30"
        self.assertEqual(ui_kit.place_of(top), (300, 200, -1920, -30))
        top.geometry.return_value = "300x200-5+7"
        self.assertEqual(ui_kit.place_of(top), (300, 200, -5, 7))


if __name__ == "__main__":
    unittest.main()
