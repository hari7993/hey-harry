"""The web drawer (drawer.py): only sites on the internet, opened in Chrome's app mode with a profile of its own and
painted so it can be cut to a drawer, and a click on the same site again putting it away. No browser is started."""
import unittest
from unittest import mock

from tests.support import siri  # noqa: F401  temp APPDATA and the tripwires, before anything else
import drawer


class Sites(unittest.TestCase):
    def test_only_sites_on_the_internet(self):
        self.assertEqual(drawer.normal("youtube.com"), "https://youtube.com")
        self.assertEqual(drawer.normal("https://web.whatsapp.com/"), "https://web.whatsapp.com/")
        for local in ("http://192.168.1.1", "localhost", "router", "file:///C:/x", "nas.local", "http://10.0.0.2:8080",
                      "", "javascript:alert(1)"):
            self.assertIsNone(drawer.normal(local), local)
        self.assertEqual(drawer.name_of("https://www.youtube.com/watch?v=1"), "youtube.com")

    def test_a_name_that_leads_home_is_turned_away_when_its_opened(self):
        with mock.patch("web._public", return_value=False):
            self.assertIsNone(drawer.site("sneaky.example.com"))
        with mock.patch("web._public", return_value=True):
            self.assertEqual(drawer.site("example.com"), "https://example.com")


class Drawer(unittest.TestCase):
    def test_it_opens_in_app_mode_and_a_click_again_puts_it_away(self):
        d = drawer.Drawer()
        proc = mock.Mock(pid=4242)
        proc.poll.return_value = None
        with mock.patch.object(drawer, "site", side_effect=lambda u: drawer.normal(u)), \
                mock.patch("herbrowser.program", return_value="C:\\chrome.exe"), \
                mock.patch.object(drawer.subprocess, "Popen", return_value=proc) as run, \
                mock.patch.object(drawer.threading, "Thread"), \
                mock.patch.object(drawer, "_user32") as user32:
            self.assertTrue(d.toggle("youtube.com", (100, 80, 500, 700)))
            args = run.call_args[0][0]
            self.assertEqual(args[0], "C:\\chrome.exe")
            self.assertIn("--app=https://youtube.com", args)
            self.assertIn("--disable-direct-composition", args)  # so its window can be cut to a drawer
            self.assertTrue(any(a.startswith("--user-data-dir=") and a.endswith("Drawer") for a in args))
            d.hwnd = 77  # its window found (_dress)
            self.assertFalse(d.toggle("youtube.com", (100, 80, 500, 700)))  # the same one again: put away
            user32.ShowWindow.assert_called_with(77, drawer.SW_HIDE)
            self.assertFalse(d.up)
            d.toggle("web.whatsapp.com", (100, 80, 500, 700))  # another: the first closed for it
            proc.terminate.assert_called_once()
            with self.assertRaises(RuntimeError):
                d.toggle("http://192.168.1.1", (0, 0, 10, 10))
        d.proc = None


if __name__ == "__main__":
    unittest.main()
