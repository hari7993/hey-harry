"""What the island knows of the PC's sound and drives (devices.py), its music's bars (visualizer.py), the shelf's
files (shelf.py) and the calendar's month, read from what's kept only (agenda.kept)."""
import datetime as dt
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

from tests.support import siri  # noqa: F401  temp APPDATA and the tripwires, before anything else
import agenda
import devices
import settings
import shelf
import visualizer


class Kinds(unittest.TestCase):
    def test_each_output_is_drawn_as_what_it_is(self):
        cases = (("Headphones (2- WF-C500)", 3, "BTHENUM", "buds"), ("AirPods Pro", 3, "BTHENUM", "buds"),
                 ("Rockerz 411 Hands-Free", 3, "BTHHFENUM", "headphones"), ("Headphones (Realtek)", 3, "", "jack"),
                 ("GOSURROUND 350", 1, "BTHENUM", "speaker"), ("LG TV (NVIDIA High Definition Audio)", 9, "", "display"),
                 ("Speakers (Realtek(R) Audio)", 1, "HDAUDIO", "builtin"))
        for name, form, bus, kind in cases:
            self.assertEqual(devices.kind_of(name, form, bus), kind, name)

    def test_a_bluetooth_outputs_battery_is_found_by_its_name(self):
        levels = {"AirPods Pro": 90, "Rockerz 411": 30}
        self.assertEqual(devices.battery_for({"name": "AirPods Pro", "bus": "BTHENUM"}, levels), 90)
        self.assertEqual(devices.battery_for({"name": "Rockerz 411 Stereo", "bus": "BTHENUM"}, levels), 30)
        self.assertIsNone(devices.battery_for({"name": "AirPods Pro", "bus": "USB"}, levels))  # not Bluetooth
        self.assertIsNone(devices.battery_for({"name": "Speakers", "bus": "BTHENUM"}, levels))


class Bars(unittest.TestCase):
    def tone(self, hz, loud=0.5):
        t = np.arange(visualizer.SIZE, dtype=np.float32) / visualizer.RATE
        return (loud * np.sin(2 * np.pi * hz * t)).astype(np.float32)

    def test_quiet_is_the_floor(self):
        peaks, last = [0.01] * 5, [visualizer.LEAST] * 5
        levels = visualizer.bands(np.zeros(visualizer.SIZE, np.float32), peaks, last)
        self.assertEqual(len(levels), 5)
        self.assertTrue(all(abs(v - visualizer.LEAST) < 1e-6 for v in levels))

    def test_a_tone_lifts_its_own_band_most(self):
        peaks, last = [0.01] * 5, [visualizer.LEAST] * 5
        for _ in range(12):
            levels = visualizer.bands(self.tone(1000), peaks, last)  # 1 kHz: the third band, 560 Hz to 1.7 kHz
        self.assertEqual(int(np.argmax(levels)), 2)
        self.assertTrue(all(0.0 <= v <= 1.0 for v in levels))

    def test_it_listens_only_between_start_and_stop(self):
        bars = visualizer.Bands()
        self.assertFalse(bars.running)
        with mock.patch("loopback.Loopback") as loop:
            loop.return_value.start.return_value = loop.return_value  # as the real one, started
            bars.start()
            self.assertTrue(bars.running)
            bars.stop()
        loop.return_value.stop.assert_called_once()
        self.assertFalse(bars.running)
        self.assertEqual(bars.levels, [visualizer.LEAST] * 5)


class Shelf(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.files = []
        for i in range(12):
            path = os.path.join(self.dir, f"f{i}.txt")
            open(path, "w").close()
            self.files.append(path)

    def tearDown(self):
        settings.put("island_shelf_keep", False)
        settings.put("island_shelf", [])

    def test_the_newest_first_each_once_and_only_whats_there(self):
        items = shelf.added([], self.files[:2])
        items = shelf.added(items, [self.files[0], os.path.join(self.dir, "gone.txt")])
        self.assertEqual(items, [os.path.normpath(self.files[0]), os.path.normpath(self.files[1])])
        self.assertEqual(len(shelf.added(items, self.files)), shelf.MOST)

    def test_kept_for_next_time_only_when_settings_says(self):
        shelf.save(self.files[:2])
        self.assertEqual(shelf.load(), [])
        settings.put("island_shelf_keep", True)
        shelf.save(self.files[:2])
        self.assertEqual([os.path.normpath(p) for p in shelf.load()], [os.path.normpath(p) for p in self.files[:2]])
        os.remove(self.files[0])
        self.assertEqual([os.path.normpath(p) for p in shelf.load()], [os.path.normpath(self.files[1])])


class KeptCalendar(unittest.TestCase):
    ICS = ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:a\r\nSUMMARY:Standup\r\nDTSTART:{s}\r\nDTEND:{e}\r\n"
           "END:VEVENT\r\nEND:VCALENDAR\r\n")

    def test_the_month_has_her_events_and_a_feeds_kept_file_and_never_fetches(self):
        start = (dt.datetime.now() + dt.timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        agenda.add("Dentist", start, start + dt.timedelta(hours=1))
        url = "https://calendar.example/feed.ics"
        data = agenda._load()
        data["feeds"].append({"url": url, "name": "Work"})
        agenda._save(data)
        os.makedirs(os.path.dirname(agenda._feed_file(url)), exist_ok=True)
        s = start + dt.timedelta(hours=3)
        with open(agenda._feed_file(url), "w", encoding="utf-8") as f:
            f.write(self.ICS.format(s=s.strftime("%Y%m%dT%H%M%S"),
                                    e=(s + dt.timedelta(minutes=15)).strftime("%Y%m%dT%H%M%S")))
        agenda._feeds.pop(url, None)
        with mock.patch.object(agenda, "_fetch", side_effect=AssertionError("fetched")):
            got = agenda.kept(start - dt.timedelta(days=1), start + dt.timedelta(days=1))
        titles = [o["title"] for o in got]
        self.assertIn("Dentist", titles)
        self.assertIn("Standup", titles)
        self.assertLess(titles.index("Dentist"), titles.index("Standup"))  # soonest first


if __name__ == "__main__":
    unittest.main()


class Names(unittest.TestCase):
    """What Controls says Wi-Fi and Bluetooth are on (30 October 2026)."""

    def test_a_networks_name_from_its_ssid(self):
        raw = (b"Peram Srinu" + bytes(21))
        self.assertEqual(devices.ssid_of(raw, 11), "Peram Srinu")
        self.assertEqual(devices.ssid_of("Café 5G".encode("utf-8"), len("Café 5G".encode("utf-8"))), "Café 5G")
        self.assertEqual(devices.ssid_of(bytes(32), 0, "Home"), "Home")  # a hidden one: its profile's name
        self.assertIsNone(devices.ssid_of(bytes(32), 0, ""))

    def test_bluetooth_says_the_headset_sound_plays_on_first(self):
        outs = [{"name": "AirPods Pro", "bus": "BTHENUM", "default": True}]
        self.assertEqual(devices.bluetooth_name(["AirPods Pro"], outs), "AirPods Pro")
        self.assertEqual(devices.bluetooth_name(["AirPods Pro", "MX Keys"], outs), "AirPods Pro + 1")
        self.assertEqual(devices.bluetooth_name(["MX Keys"], [{"name": "Speakers", "bus": "HDAUDIO", "default": True}]),
                         "MX Keys")
        self.assertEqual(devices.bluetooth_name(["A", "B", "C"]), "A + 2")
        self.assertIsNone(devices.bluetooth_name([], []))


class Resample(unittest.TestCase):
    """Pictures made smaller or bigger by area (island_art.resample), the dock's icons and the covers."""

    def test_a_halving_is_the_mean_of_each_block(self):
        import island_art as art
        pic = np.random.default_rng(1).random((64, 64, 4)).astype(np.float32)
        self.assertTrue(np.allclose(art.resample(pic, 32), pic.reshape(32, 2, 32, 2, 4).mean(axis=(1, 3)),
                                    atol=1e-5))

    def test_any_size_keeps_a_flat_colour_flat_and_its_edges_in(self):
        import island_art as art
        flat = np.full((106, 106, 4), 0.6, np.float32)
        for n in (17, 66, 90, 150):
            out = art.resample(flat, n)
            self.assertEqual(out.shape, (n, n, 4))
            self.assertTrue(np.allclose(out, 0.6, atol=1e-5), n)
        wide = art.resample(np.ones((40, 80, 4), np.float32), 20, 40)
        self.assertEqual(wide.shape, (20, 40, 4))
