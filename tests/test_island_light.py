"""Her island's light and what you copy (island_light.py, island_plugins.Clipboard; 30 October 2026, after Glance's
notch): the light flares, stays and fades, its arms running out along the top of the screen; it lights round the
island and never on it; a level only as far as it goes; something wrong at her two lower corners. And a copy said for
a moment, never a password manager's, a key only by its first letters, never her own."""
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from tests.support import siri  # noqa: F401  first: temp APPDATA and the tripwires, before anything of hers
from tests.test_watchers import until

import island
import island_light as lights
import island_plugins as plugins
import shelf
import winplatform as win

K = 1.5
X0, W, H, R, TOP, S = 300.0, 126.0, 51.0, 18.0, 30.0, 9.0


def drop(xs, ys):
    return island._drop(xs, ys, X0, W, H, R, TOP, S)


def box(xs, ys):
    return island.face.rbox(xs, ys, X0 + W / 2, TOP + (H - R) / 2, W / 2, (H + R) / 2, R)


def lit(kind="halo", level=None, colour=(0.3, 0.68, 1.0), since=0.6, dark=True, drop_=True):
    """A window's picture (alpha bytes) with only the light in it, lit since seconds ago, and the field it came from."""
    buf = np.zeros((200, 760, 4), np.uint8)
    f = lights.field(drop if drop_ else box, X0, W, H, R, TOP, K, drop_, kind, level, (760, 200),
                     soft=box if drop_ else None)
    light = lights.Light(colour, 100.0 - since, kind, level)
    lights.shine(buf, f, light, light.strength(100.0), 100.0, dark=dark)
    return buf, f


class Timing(unittest.TestCase):
    def test_it_flares_stays_and_fades(self):
        light = lights.Light((1, 0, 0), 10.0)
        self.assertEqual(light.strength(9.9), 0.0)
        self.assertLess(light.strength(10.05), light.strength(10.15))  # coming up
        self.assertEqual(light.strength(10.0 + lights.FLARE + 0.5), 1.0)  # held
        end = 10.0 + lights.FLARE + lights.HOLD + lights.FADE
        self.assertGreater(light.strength(end - 0.5), light.strength(end - 0.1))  # going
        self.assertFalse(light.done(end - 0.01))
        self.assertTrue(light.done(end + 1e-6))
        self.assertEqual(light.strength(end + 1), 0.0)
        self.assertLess(light.spread(10.05), 0.5)
        self.assertEqual(light.spread(11.0), 1.0)  # the arms out to their ends


class Shine(unittest.TestCase):
    def test_round_her_and_along_the_top_never_on_her(self):
        buf, f = lit()
        a = buf[..., 3]
        self.assertTrue((buf[..., :3] <= buf[..., 3:]).all())  # premultiplied, as Windows needs
        y = int(TOP) + 1
        self.assertGreater(a[y, int(X0 - 30 * K)], 120)  # an arm, out along the top
        self.assertGreater(a[y, int(X0 + W + 30 * K)], 120)
        self.assertLess(a[y, int(X0 - 90 * K)], a[y, int(X0 - 30 * K)])  # fading along it
        self.assertGreater(a[int(TOP + H + 1), int(X0 + W / 2)], 120)  # under her
        self.assertEqual(a[int(TOP + H / 2), int(X0 + 20):int(X0 + W - 20)].max(), 0)  # none on her
        self.assertLess(a[y + int(30 * K), int(X0 - 60 * K)], 40)  # the arms are a light along the top, not a wall
        none, _ = lit(since=-1.0)  # not come yet
        self.assertEqual(none[..., 3].max(), 0)

    def test_a_level_lights_as_far_as_it_goes(self):
        buf, _ = lit("level", 0.3)
        bottom = buf[int(TOP + H + 1), :, 3]
        self.assertGreater(bottom[int(X0 + W * 0.15)], 100)  # lit up to the level
        self.assertLess(bottom[int(X0 + W * 0.75)], 30)  # and not past it
        y = int(TOP) + 1
        self.assertGreater(buf[y, int(X0 - 25 * K), 3], 60)  # its arm runs out to the left
        self.assertEqual(buf[y, int(X0 + W + 25 * K), 3], 0)  # never to the right

    def test_something_wrong_lights_her_two_lower_corners(self):
        buf, _ = lit("alarm", colour=island.RED)
        bottom = buf[int(TOP + H + 1), :, 3]
        self.assertGreater(bottom[int(X0 + R)], 2 * bottom[int(X0 + W / 2)])
        self.assertGreater(bottom[int(X0 + W - R)], 2 * bottom[int(X0 + W / 2)])

    def test_floating_it_lights_all_round_with_no_arms(self):
        buf, f = lit(drop_=False)
        self.assertIsNone(f["rows"])
        a = buf[..., 3]
        self.assertGreater(a[int(TOP + H / 2), int(X0 - 1)], 120)  # her side
        self.assertLess(a[int(TOP + 1), int(X0 - 70 * K)], 10)  # nothing along the top past her

    def test_on_a_light_island_the_line_is_its_colour_not_white(self):
        dark, _ = lit(colour=island.GREEN)
        light, _ = lit(colour=island.GREEN, dark=False)
        y, x = int(TOP + H), int(X0 + W / 2)
        dark_px, light_px = dark[y, x, :3].astype(int), light[y, x, :3].astype(int)
        self.assertGreater(dark_px[0], light_px[0])  # bluer, the white in it, on the dark one (blue, green, red)


class Copies(unittest.TestCase):
    def look(self, formats, pid=1):
        return lambda: (formats, pid)

    def test_what_was_copied_said_as_its_start(self):
        got = plugins.copied(self.look([13, 1, 7]), lambda: "Shall we meet at 2pm\nby the cafe?")
        self.assertEqual(got, {"what": "text", "text": "Shall we meet at 2pm by the cafe?"})
        self.assertEqual(plugins.copied(self.look([8, 2]))["what"], "picture")  # a screenshot
        self.assertEqual(plugins.copied(self.look([15]))["what"], "files")
        self.assertIsNone(plugins.copied(self.look([49161])))  # nothing she can name
        self.assertIsNone(plugins.copied(lambda: None))  # another app has it open

    def test_never_a_password_managers_and_never_her_own(self):
        for mark in plugins.EXCLUDE:
            self.assertIsNone(plugins.copied(self.look([13, mark]), lambda: "hunter2"), mark)
        import os
        self.assertIsNone(plugins.copied(self.look([13], os.getpid()), lambda: "hers"))

    def test_a_key_shows_only_its_first_letters_a_link_shows(self):
        self.assertEqual(plugins.shown("sk-live-4f21a9b8c7d6e5f4"), "sk-l\u2026")
        self.assertEqual(plugins.shown("https://example.com/item/12345"), "https://example.com/item/12345")
        self.assertTrue(plugins.shown("word " * 30).endswith("\u2026"))
        self.assertLessEqual(len(plugins.shown("word " * 30)), 60)

    def test_said_once_a_copy_and_never_for_hers(self):
        host = mock.Mock()
        p = plugins.Clipboard(host)
        with mock.patch.object(plugins.win, "clipboard_sequence", return_value=7):
            p.start()
            p.poll(0.0)
        host.post.assert_not_called()  # nothing new since she started
        with mock.patch.object(plugins.win, "clipboard_sequence", return_value=8), \
                mock.patch.object(plugins, "copied", return_value={"what": "text", "text": "hello"}):
            p.poll(1.0)
            p.poll(1.4)  # the same copy, once
        shown = [c.args[0] for c in host.post.call_args_list]
        self.assertEqual(len(shown), 1)
        self.assertEqual((shown[0][0], shown[0][1].kind, shown[0][1].data["text"]), ("show", "copied", "hello"))
        host.post.reset_mock()
        with mock.patch.object(plugins.win, "clipboard_sequence", return_value=9), \
                mock.patch.object(plugins.win, "OWN_CLIPS", [9]), \
                mock.patch.object(plugins, "copied", return_value={"what": "text", "text": "hers"}):
            p.poll(2.0)  # she pasted for you: nothing said
        host.post.assert_not_called()
        with mock.patch.object(plugins.win, "clipboard_sequence", return_value=10), \
                mock.patch.object(p, "option", return_value=False), \
                mock.patch.object(plugins, "copied", return_value={"what": "text", "text": "secret"}):
            p.poll(3.0)  # "Show what you copied" off: Copied, and not what
        self.assertEqual(host.post.call_args[0][0][1].data["text"], "")


class Shortcuts(unittest.TestCase):
    """Every shortcut answered (30 October 2026, the owner: "when I pasted it didn't respond"): the keyboard hook she
    has for push to talk names each, never her own presses, and the Clipboard plugin says it."""

    @staticmethod
    def held(*keys):
        return lambda vk: vk in keys

    def test_which_keys_make_which(self):
        ctrl, shift, alt, lwin = win.VK_CONTROL, win.VK_SHIFT, win.VK_MENU, win.VK_LWIN
        self.assertEqual(win.chord(0x56, self.held(ctrl)), "paste")
        self.assertEqual(win.chord(0x58, self.held(ctrl)), "cut")
        self.assertEqual(win.chord(0x5A, self.held(ctrl)), "undo")
        self.assertEqual(win.chord(0x5A, self.held(ctrl, shift)), "redo")
        self.assertEqual(win.chord(0x59, self.held(ctrl)), "redo")
        self.assertEqual(win.chord(0x53, self.held(ctrl)), "save")
        self.assertEqual(win.chord(0x53, self.held(lwin, shift)), "screenshot")
        self.assertEqual(win.chord(win.VK_SNAPSHOT, self.held()), "screenshot")
        self.assertIsNone(win.chord(0x56, self.held()))  # V alone is typing
        self.assertIsNone(win.chord(0x56, self.held(ctrl, alt)))  # AltGr on some keyboards
        self.assertIsNone(win.chord(0x43, self.held(ctrl)))  # Ctrl+C: the clipboard says that

    def test_the_hook_tells_them_and_never_her_own(self):
        got = []
        with mock.patch("pynput.keyboard.Listener") as listener, mock.patch.object(win, "CHORDS", [got.append]), \
                mock.patch.object(win, "chord", return_value="paste"):
            win.start_ptt_listener(lambda: None, lambda: None)
            hook = listener.call_args.kwargs["win32_event_filter"]
            self.assertTrue(hook(win.WM_KEYDOWN, SimpleNamespace(vkCode=0x56, flags=0)))  # passed on to the app
            hook(win.WM_KEYDOWN, SimpleNamespace(vkCode=0x56, flags=win.LLKHF_INJECTED))  # her own paste
            hook(0x101, SimpleNamespace(vkCode=0x56, flags=0))  # the key coming up
        self.assertEqual(got, ["paste"])

    def plugin(self):
        host = mock.Mock()
        p = plugins.Clipboard(host)
        chords = []
        patch = mock.patch.object(plugins.win, "CHORDS", chords)
        patch.start()
        self.addCleanup(patch.stop)
        with mock.patch.object(plugins.win, "clipboard_sequence", return_value=1):
            p.start()
        self.assertEqual(chords, [p._pressed])
        return p, host, chords

    def shown(self, host):
        return [c.args[0][1] for c in host.post.call_args_list if c.args[0][0] == "show"]

    def test_paste_says_what_was_copied_and_undo_the_app(self):
        p, host, _ = self.plugin()
        p.last = {"what": "text", "text": "Shall we meet"}
        now = time.time()
        p._pressed("paste")
        host.poll_soon.assert_called_with(p, 0.0)
        p._pressed("undo")
        with mock.patch.object(plugins.win, "clipboard_sequence", return_value=1), \
                mock.patch.object(plugins.win, "front_app_name", return_value="Word"):
            p.poll(now)
        said = [(a.data["how"], a.data["text"]) for a in self.shown(host)]
        self.assertEqual(said, [("paste", "Shall we meet"), ("undo", "Word")])

    def test_a_cut_and_a_screenshot_are_said_as_the_clipboard_changes(self):
        p, host, _ = self.plugin()
        now = time.time()
        p._pressed("cut")
        with mock.patch.object(plugins.win, "clipboard_sequence", return_value=1):
            p.poll(now)
        self.assertEqual(self.shown(host), [])  # not yet: it's said with what was cut
        with mock.patch.object(plugins.win, "clipboard_sequence", return_value=2), \
                mock.patch.object(plugins, "copied", return_value={"what": "text", "text": "a line"}):
            p.poll(now + 0.3)
        p._pressed("screenshot")
        with mock.patch.object(plugins.win, "clipboard_sequence", return_value=3), \
                mock.patch.object(plugins, "copied", return_value={"what": "picture", "text": ""}):
            p.poll(time.time())
        said = [(a.data["how"], a.data["text"]) for a in self.shown(host)]
        self.assertEqual(said, [("cut", "a line"), ("screenshot", "")])
        self.assertEqual(p.last, {"what": "picture", "text": ""})

    def test_off_they_go_unsaid_and_stopping_lets_go_of_the_hook(self):
        p, host, chords = self.plugin()
        p._pressed("paste")
        with mock.patch.object(plugins.win, "clipboard_sequence", return_value=1), \
                mock.patch.object(p, "option", return_value=False):
            p.poll(time.time())
        self.assertEqual(self.shown(host), [])
        p.stop()
        self.assertEqual(chords, [])


class LevelsInTheNotch(unittest.TestCase):
    """The volume and the brightness as they change, handed from the edges' watcher to the island (Levels)."""

    def test_handed_on_only_while_shown(self):
        self.assertFalse(plugins.level_news("volume", 40))  # not on: the edge's slider shows it
        host = mock.Mock()
        p = plugins.Levels(host)
        p.start()
        self.addCleanup(p.stop)
        self.assertTrue(plugins.level_news("volume", 40))
        plugins.level_news("volume", 46)
        plugins.level_news("brightness", 70)
        host.poll_soon.assert_called_with(p, 0.0)
        p.poll(time.time())
        said = sorted((c.args[0][1].data["what"], c.args[0][1].data["level"]) for c in host.post.call_args_list
                      if c.args[0][0] == "show")
        self.assertEqual(said, [("brightness", 70), ("volume", 46)])  # the newest of each
        p.stop()
        self.assertIsNone(plugins.Levels.running)

    def test_the_edges_hand_it_on(self):
        import edges
        with mock.patch.object(plugins, "level_news", return_value=True) as news:
            self.assertTrue(edges._in_notch("volume", 30, False))
        news.assert_called_once_with("volume", 30, False)


class DropTarget(unittest.TestCase):
    """shelf.Target, told as files come over her, move, go and land, so she opens for them before the drop."""

    def target(self):
        got = []
        t = object.__new__(shelf.Target)
        t.hwnd, t.on_drag, t.paths, t.helper, t.on, t.ptr = 1, lambda *a: got.append(a), [], None, False, 1234
        return t, got

    def test_files_only_and_copied_never_moved(self):
        t, got = self.target()
        packed = (5 << 32) | (0xFFFFFFFF & -20)  # x -20, on a screen to the left; y 5
        self.assertEqual(shelf._point(packed), (-20, 5))
        effect = [shelf.DROPEFFECT_COPY | shelf.DROPEFFECT_MOVE]
        with mock.patch.object(shelf, "dragged", return_value=["C:\\a.pdf"]):
            self.assertEqual(t._enter(None, 99, 0, packed, effect), 0)
        self.assertEqual(effect, [shelf.DROPEFFECT_COPY])  # a move would have File Explorer delete it
        self.assertEqual(got, [("enter", -20, 5, ["C:\\a.pdf"])])
        effect = [shelf.DROPEFFECT_COPY]
        t._over(None, 0, packed, effect)
        t._leave(None)
        self.assertEqual([g[0] for g in got], ["enter", "over", "leave"])
        got.clear()
        effect = [shelf.DROPEFFECT_COPY]
        with mock.patch.object(shelf, "dragged", return_value=[]):  # words dragged from a page, not files
            t._enter(None, 99, 0, packed, effect)
        self.assertEqual((effect, got), ([shelf.DROPEFFECT_NONE], []))
        with mock.patch.object(shelf, "dragged", return_value=["C:\\b.txt"]):
            t._drop(None, 99, 0, packed, [shelf.DROPEFFECT_LINK])
        self.assertEqual(got, [("drop", -20, 5, ["C:\\b.txt"])])

    def test_it_answers_as_a_drop_target_only(self):
        t, _ = self.target()
        out = (shelf.ctypes.c_void_p * 1)()
        iid = shelf.ctypes.create_string_buffer(bytes(shelf.IID_IDROPTARGET), 16)
        self.assertEqual(t._qi(None, shelf.ctypes.addressof(iid), out), 0)
        self.assertEqual(out[0], 1234)
        other = shelf.ctypes.create_string_buffer(bytes(shelf.IID_IDROPTARGETHELPER), 16)
        self.assertEqual(t._qi(None, shelf.ctypes.addressof(other), out), shelf.E_NOINTERFACE)


class KeepAwake(unittest.TestCase):
    def test_held_by_a_thread_of_its_own_till_let_go(self):
        calls = []
        with mock.patch.object(win.kernel32, "SetThreadExecutionState", side_effect=calls.append):
            self.assertTrue(win.keep_awake(True))
            self.assertTrue(win.keep_awake(True))  # once
            self.assertTrue(until(lambda: len(calls) == 1))
            self.assertEqual(calls[0], win.ES_CONTINUOUS | win.ES_SYSTEM_REQUIRED | win.ES_DISPLAY_REQUIRED)
            self.assertFalse(win.keep_awake(False))
            self.assertTrue(until(lambda: len(calls) == 2))
        self.assertEqual(calls[1], win.ES_CONTINUOUS)
        self.assertFalse(win.awake())


if __name__ == "__main__":
    unittest.main()
