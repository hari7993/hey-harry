"""Dream mode (dream.py, 28 October 2026): a pixel-art scene full screen while music plays, the song's words going by
in time with it. Its scenes and the words for them, the words of a song (LRC) and how a song is looked up, the page's
server, its window opened and closed, what's said for it, and its step. Nothing here opens a window or goes online:
tests.support trips the browser's launch and the network, and fakes stand in for both."""
import json
import os
import re
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

import requests

from tests.support import ORIGINAL, ROOT, siri, winplatform

import dream
import settings
import toolbox


def until(check, seconds=5.0):
    end = time.time() + seconds
    while time.time() < end:
        if check():
            return True
        time.sleep(0.02)
    return check()


class Reply:
    """What LRCLIB sends back."""

    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class Scenes(unittest.TestCase):
    def test_the_six_are_the_pages_own_in_the_same_order_and_names(self):
        with open(os.path.join(ROOT, "dream", "scenes.js"), encoding="utf-8") as f:
            js = f.read()
        order = re.search(r"const SCENE_ORDER = \[(.*?)\];", js).group(1)
        self.assertEqual(tuple(re.findall(r'"([a-z-]+)"', order)), dream.SCENES)
        for scene in dream.SCENES:
            label = re.search(rf'SCENES\["{scene}"\] = \{{\s*label: "([^"]+)"', js)
            self.assertEqual(label.group(1), dream.NAMES[scene], scene)

    def test_the_page_loads_nothing_from_anywhere_else(self):
        for name in ("index.html", "scenes.js"):
            with open(os.path.join(ROOT, "dream", name), encoding="utf-8") as f:
                self.assertNotRegex(f.read(), r"https?://", name)

    def test_words_name_a_scene(self):
        night, day = dream.dt.datetime(2026, 10, 28, 22), dream.dt.datetime(2026, 10, 28, 9)
        for words, want in (("night drive", "night-drive"), ("the road", "night-drive"), ("sunset", "sunset-drive"),
                            ("rainy", "rain-window"), ("the rain", "rain-window"), ("the city", "city-terrace"),
                            ("rooftop", "city-terrace"), ("moonlight", "night-beach"),
                            ("the beach at night", "night-beach"), ("morning beach", "morning-beach"),
                            ("Night Drive", "night-drive"), ("night-beach", "night-beach")):
            with self.subTest(words):
                self.assertEqual(dream.scene_for(words, night), want)
        self.assertEqual(dream.scene_for("the beach", day), "morning-beach")  # a beach with no time: by the clock
        self.assertEqual(dream.scene_for("the beach", night), "night-beach")
        self.assertIsNone(dream.scene_for("my exam"))
        self.assertIsNone(dream.scene_for(""))

    def test_a_steps_scene_is_its_id_its_name_or_words_for_it(self):
        self.assertEqual(dream.scene_id("rain-window"), "rain-window")
        self.assertEqual(dream.scene_id("City terrace"), "city-terrace")
        self.assertEqual(dream.scene_id("sunset"), "sunset-drive")
        self.assertIsNone(dream.scene_id(""))
        self.assertIsNone(dream.scene_id("somewhere"))

    def test_with_none_named_one_that_suits_the_time_each_in_turn(self):
        settings.put("dream_scene", None)
        self.assertEqual(dream.pick_scene(dream.dt.datetime(2026, 10, 28, 7)), "morning-beach")
        late = dream.dt.datetime(2026, 10, 29, 1)  # past midnight is still the night's
        self.assertEqual(dream.pick_scene(late), "night-drive")
        settings.put("dream_scene", "night-drive")
        self.assertEqual(dream.pick_scene(late), "city-terrace")
        settings.put("dream_scene", "night-beach")
        self.assertEqual(dream.pick_scene(late), "night-drive")

    def test_the_next_comes_round_again(self):
        self.assertEqual(dream.following("night-drive"), "sunset-drive")
        self.assertEqual(dream.following("rain-window"), "night-drive")


class Lyrics(unittest.TestCase):
    def test_lrc_times_choruses_an_offset_and_word_marks(self):
        lrc = ("[ar:Someone]\n[ti:Song]\n[offset:+500]\n[00:12.00]First line\n[00:15.50][01:20.00]Chorus line\n"
               "[00:17.250]<00:17.25>Word <00:17.80>by <00:18.10>word\n[01:02:50]Colon\n[00:20.00]\nno time here\n")
        self.assertEqual(dream.parse_lrc(lrc), [[11.5, "First line"], [15.0, "Chorus line"], [16.75, "Word by word"],
                                                [19.5, ""], [62.0, "Colon"], [79.5, "Chorus line"]])
        self.assertEqual(dream.parse_lrc(""), [])
        self.assertEqual(dream.parse_lrc(None), [])

    def test_a_video_title_gives_its_song_and_singer(self):
        for title, artist, app, want in (
                ("Ed Sheeran - Perfect (Official Music Video)", "EdSheeranVEVO", "Chrome", ("Perfect", "Ed Sheeran")),
                ("Perfect", "Ed Sheeran - Topic", "MSEdge", ("Perfect", "Ed Sheeran")),
                ("Blinding Lights", "The Weeknd", "Spotify.exe", ("Blinding Lights", "The Weeknd")),
                ("Peaches (feat. Daniel Caesar & Giveon)", "Justin Bieber, Daniel Caesar", "Spotify.exe",
                 ("Peaches", "Justin Bieber")),
                ("Kesariya | Brahmastra | Arijit Singh", "Sony Music India", "Chrome", ("Kesariya", "Sony Music India")),
                ("Song [Lyrics]", "Singer", "MSEdge", ("Song", "Singer"))):
            with self.subTest(title):
                self.assertEqual(dream.song_of(title, artist, app), want)

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="lyrics-")
        self.cache = mock.patch.object(dream, "CACHE", os.path.join(self.dir, "lyrics.json"))
        self.cache.start()
        dream._CACHE[0] = None
        self.asked = []

    def tearDown(self):
        self.cache.stop()
        dream._CACHE[0] = None

    def lrclib(self, *replies):
        replies = list(replies)

        def get(url, params=None, headers=None, timeout=None):
            self.asked.append(params)
            reply = replies.pop(0) if replies else Reply([])
            if isinstance(reply, Exception):
                raise reply
            return reply
        return mock.patch.object(dream.HTTP, "get", get)

    def test_words_in_time_are_found_and_kept_so_each_song_is_asked_once(self):
        found = [{"trackName": "Perfect", "artistName": "Ed Sheeran", "duration": 263,
                  "syncedLyrics": "[00:01.00]I found a love", "plainLyrics": "I found a love"}]
        with self.lrclib(Reply(found)):
            self.assertEqual(dream.lyrics_for("Perfect", "Ed Sheeran", 263.4, "Spotify.exe"),
                             {"lines": [[1.0, "I found a love"]]})
        self.assertEqual(self.asked, [{"track_name": "Perfect", "artist_name": "Ed Sheeran"}])  # nothing else sent
        dream._CACHE[0] = None  # from the file on the disk now
        with self.lrclib():
            self.assertEqual(dream.lyrics_for("Perfect", "Ed Sheeran", 263.4, "Spotify.exe"),
                             {"lines": [[1.0, "I found a love"]]})
        self.assertEqual(len(self.asked), 1)

    def test_words_with_no_times_and_a_song_with_none(self):
        with self.lrclib(Reply([{"trackName": "Hymn", "duration": 200, "plainLyrics": "one\n\ntwo"}])):
            self.assertEqual(dream.lyrics_for("Hymn", "Choir", 201, "Spotify.exe"), {"plain": ["one", "", "two"]})
        with self.lrclib(Reply([{"trackName": "Weightless", "duration": 480, "instrumental": True}])):
            self.assertEqual(dream.lyrics_for("Weightless", "Marconi Union", 482, "Spotify.exe"), {"instrumental": True})

    def test_another_song_or_another_length_is_not_this_one(self):
        other = [{"trackName": "Shape of You", "duration": 263, "syncedLyrics": "[00:01.00]The club"},
                 {"trackName": "Perfect", "duration": 400, "syncedLyrics": "[00:01.00]Live, much longer"}]
        with self.lrclib(Reply(other), Reply(other), Reply(other)):
            self.assertIsNone(dream.lyrics_for("Perfect", "Ed Sheeran", 263, "Spotify.exe"))
        self.assertEqual(len(self.asked), 3)  # by song and artist, by both as words, then by the song's name
        with self.lrclib():  # not found is kept too, so it isn't asked again at once
            self.assertIsNone(dream.lyrics_for("Perfect", "Ed Sheeran", 263, "Spotify.exe"))
        self.assertEqual(len(self.asked), 3)

    def test_a_mix_or_a_stream_is_never_looked_up(self):
        with self.lrclib():
            self.assertIsNone(dream.lyrics_for("lofi hip hop radio - beats to relax/study to", "Lofi Girl", 0, "Chrome"))
            self.assertIsNone(dream.lyrics_for("lofi hip hop mix", "Lofi Girl", 3600, "Chrome"))
            self.assertIsNone(dream.lyrics_for("3 Hours of Rain", "Calm", 3 * 3600, "Chrome"))
            self.assertIsNone(dream.lyrics_for("Perfect", "Ed Sheeran", 0, "Spotify.exe"))  # no length: no fixed song
        self.assertEqual(self.asked, [])

    def test_lrclib_out_of_reach_is_asked_again_next_time(self):
        with self.lrclib(requests.ConnectionError("offline")):
            self.assertIsNone(dream.lyrics_for("Perfect", "Ed Sheeran", 263, "Spotify.exe"))
        found = [{"trackName": "Perfect", "duration": 263, "syncedLyrics": "[00:01.00]I found a love"}]
        with self.lrclib(Reply(found)):
            self.assertEqual(dream.lyrics_for("Perfect", "Ed Sheeran", 263, "Spotify.exe"),
                             {"lines": [[1.0, "I found a love"]]})


class Page(unittest.TestCase):
    """The page's server: on this PC only, and only under the key in its address."""

    def setUp(self):
        self.server, self.address = dream._serve()
        dream.KEY[0] = "k3y"
        self.was = dict(dream.NOW)
        dream.NOW.update(open=True, scene="night-drive", track=None, lyrics=None, close=False)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        dream.KEY[0] = None
        dream.NOW.clear()
        dream.NOW.update(self.was)

    def get(self, path):
        try:
            with urllib.request.urlopen(self.address + path, timeout=5) as r:
                return r.status, r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as exc:
            exc.close()
            return exc.code, "", b""

    def test_it_listens_on_this_pc_alone(self):
        self.assertTrue(self.address.startswith("http://127.0.0.1:"))
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_the_page_its_scenes_and_what_is_playing(self):
        status, kind, body = self.get("k3y/")
        self.assertEqual((status, kind), (200, "text/html; charset=utf-8"))
        self.assertIn(b"<title>Dream mode</title>", body)
        status, kind, _ = self.get("k3y/scenes.js")
        self.assertEqual((status, kind), (200, "text/javascript; charset=utf-8"))
        dream.NOW["track"] = {"title": "Perfect", "artist": "Ed Sheeran", "playing": True, "position": 3.0,
                              "duration": 263.0, "at": 1.0}
        status, kind, body = self.get("k3y/state")
        self.assertEqual((status, kind), (200, "application/json"))
        got = json.loads(body)
        self.assertEqual(got["scene"], "night-drive")
        self.assertEqual(got["track"]["title"], "Perfect")
        self.assertFalse(got["close"])

    def test_without_its_key_nothing(self):
        for path in ("state", "wrong/state", "k3y", "k3y/../dream.py", "k3y/dream.py", "k3y/../.env"):
            with self.subTest(path):
                self.assertEqual(self.get(path)[0], 404)

    def test_the_next_scene_from_the_page(self):
        status, _, body = self.get("k3y/next")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["scene"], "sunset-drive")

    def test_the_page_asks_for_what_this_serves(self):
        with open(os.path.join(ROOT, "dream", "index.html"), encoding="utf-8") as f:
            page = f.read()
        for asked in ('base + "state"', 'base + "next"', 'base + "close"', "next.close"):
            self.assertIn(asked, page)


class Window(unittest.TestCase):
    """Opened and closed with its browser faked: no window comes up, so none is waited for."""

    def setUp(self):
        self.launched = []
        self.patches = [mock.patch.object(dream, "_browser", lambda: r"C:\Edge\msedge.exe"),
                        mock.patch.object(dream, "_launch", lambda exe, url: self.launched.append((exe, url))),
                        mock.patch.object(dream, "_follow", lambda: None),
                        mock.patch.object(dream, "_window", lambda: None),
                        mock.patch.object(dream, "_end_browser", lambda: None),
                        mock.patch.object(dream, "_wait", lambda check, seconds: check())]
        for p in self.patches:
            p.start()

    def tearDown(self):
        dream.close()
        until(lambda: dream.SERVER[0] is None)
        for p in self.patches:
            p.stop()

    def test_it_opens_full_screen_on_a_scene_and_closes(self):
        self.assertEqual(dream.open_scene("rain-window"), "rain-window")
        self.assertTrue(dream.is_open())
        (exe, url), = self.launched
        self.assertEqual(exe, r"C:\Edge\msedge.exe")
        self.assertRegex(url, rf"^http://127\.0\.0\.1:\d+/{re.escape(dream.KEY[0])}/$")
        with urllib.request.urlopen(url, timeout=5) as r:
            self.assertIn(b"Dream mode", r.read())
        self.assertEqual(dream.state()["scene"], "rain-window")
        self.assertEqual(dream.open_scene("night-beach"), "night-beach")  # open already: that scene, no new window
        self.assertEqual(len(self.launched), 1)
        self.assertEqual(dream.next_scene(), "morning-beach")
        self.assertTrue(dream.close())
        self.assertTrue(dream.state()["close"])  # the page closes its own window when it next looks
        self.assertTrue(until(lambda: dream.SERVER[0] is None))
        self.assertFalse(dream.is_open())
        with self.assertRaises(urllib.error.URLError):
            urllib.request.urlopen(url, timeout=2)
        self.assertFalse(dream.close())

    def test_its_window_closed_it_opens_again(self):
        dream.open_scene("city-terrace")
        dream.WINDOW[0] = 7  # its window came up, and then Esc or Alt+F4 closed it
        with mock.patch.object(dream.win, "shown", lambda hwnd: False):
            self.assertEqual(dream.open_scene("sunset-drive"), "sunset-drive")
        self.assertEqual(len(self.launched), 2)
        self.assertTrue(dream.is_open())

    def test_while_its_window_is_up_the_same_window_changes_scene(self):
        dream.open_scene("city-terrace")
        dream.WINDOW[0] = 7
        with mock.patch.object(dream.win, "shown", lambda hwnd: True):
            self.assertEqual(dream.open_scene("rain-window"), "rain-window")
        self.assertEqual(len(self.launched), 1)

    def test_with_no_browser_she_says_so(self):
        with mock.patch.object(dream, "_browser", lambda: None):
            with self.assertRaisesRegex(RuntimeError, "needs Edge or Chrome"):
                dream.open_scene("night-drive")
        self.assertEqual(self.launched, [])

    def test_its_browser_is_full_screen_in_app_mode_with_a_profile_of_its_own(self):
        got = {}
        with mock.patch.object(dream.subprocess, "Popen", lambda args, **kw: got.setdefault("args", args)):
            ORIGINAL["dream._launch"](r"C:\Edge\msedge.exe", "http://127.0.0.1:5/k/")
        args = got["args"]
        self.assertEqual(args[0], r"C:\Edge\msedge.exe")
        self.assertIn("--app=http://127.0.0.1:5/k/", args)
        self.assertIn("--start-fullscreen", args)
        profile = next(a for a in args if a.startswith("--user-data-dir=")).split("=", 1)[1]
        self.assertTrue(profile.startswith(winplatform.APPDATA_DIR))


class Said(unittest.TestCase):
    def plan(self, words, gate=False, playing=True, paused=False, on=False, scene="night-drive"):
        with mock.patch.object(siri, "media_playing", lambda: playing), \
                mock.patch.object(dream, "_paused", lambda: paused), \
                mock.patch.object(dream, "is_open", lambda: on), \
                mock.patch.object(dream, "pick_scene", lambda now=None: "city-terrace"), \
                mock.patch.dict(dream.NOW, {"scene": scene if on else None}):
            return dream.quick(words, gate)

    def test_dream_mode_said_opens_it(self):
        for words in ("dream mode", "Turn on dream mode.", "enable dream mode", "dream mode on", "dreammode",
                      "can you put on dream mode please", "Harry, start dream mode", "go to dream mode"):
            with self.subTest(words):
                self.assertEqual(self.plan(words), {"steps": [{"do": "dream", "action": "open", "scene": "city-terrace"}],
                                                    "say": "Dream mode, city terrace."})

    def test_with_a_scene(self):
        for words, scene in (("dream mode with the rain", "rain-window"), ("night drive dream mode", "night-drive"),
                             ("rainy dream mode", "rain-window"), ("dream mode sunset", "sunset-drive"),
                             ("turn on dream mode in the city", "city-terrace")):
            with self.subTest(words):
                self.assertEqual(self.plan(words)["steps"], [{"do": "dream", "action": "open", "scene": scene}])
        self.assertIsNone(self.plan("dream mode for my exam"))  # not a scene: the model has it

    def test_with_nothing_playing_some_lofi_first_and_a_paused_song_played_again(self):
        plan = self.plan("dream mode", playing=False)
        self.assertEqual(plan["steps"][0], {"do": "youtube", "query": dream.LOFI, "play": True})
        self.assertEqual(plan["steps"][1]["do"], "dream")
        self.assertTrue(plan["say"].startswith("Putting on some lofi."))
        plan = self.plan("dream mode", playing=False, paused=True)
        self.assertEqual(plan["steps"][0], {"do": "media", "action": "play"})

    def test_never_from_across_the_room(self):
        self.assertIsNone(self.plan("dream mode", gate="cold"))
        self.assertIsNone(self.plan("exit dream mode", gate="cold", on=True))

    def test_closing_it(self):
        for words in ("exit dream mode", "turn off dream mode", "dream mode off", "close the dream mode"):
            with self.subTest(words):
                self.assertEqual(self.plan(words, on=True)["steps"], [{"do": "dream", "action": "close"}])
        self.assertEqual(self.plan("wake up", on=True)["steps"], [{"do": "dream", "action": "close"}])
        self.assertEqual(self.plan("exit dream mode"), {"steps": [], "say": "Dream mode isn't on."})
        self.assertIsNone(self.plan("wake up"))  # with it closed, not hers to take

    def test_scenes_changed_while_it_is_on(self):
        for words in ("next scene", "change the scene", "another scene", "show me a different scene"):
            with self.subTest(words):
                self.assertEqual(self.plan(words, on=True), {"steps": [{"do": "dream", "action": "next"}],
                                                             "say": "Sunset drive."})
        self.assertEqual(self.plan("take me to the city", on=True)["steps"],
                         [{"do": "dream", "action": "open", "scene": "city-terrace"}])
        self.assertIn(self.plan("show me the beach", on=True)["steps"][0]["scene"], ("morning-beach", "night-beach"))
        for words in ("next", "next song", "something else", "put on some music"):  # the music's, not the scene's
            with self.subTest(words):
                self.assertIsNone(self.plan(words, on=True))
        self.assertIsNone(self.plan("next scene"))  # with it closed


class Step(unittest.TestCase):
    def test_registered_like_opening_an_app_never_in_the_background(self):
        tool = toolbox.get("dream")
        self.assertEqual((tool.effect, tool.read_safe, tool.routine_ok, tool.background, tool.gated_by),
                         ("reversible", True, True, "never", "DREAM_STEPS"))
        self.assertEqual(tool.args, ("scene",))
        self.assertIn("dream", siri.KNOWN_STEPS)

    def test_doing_it(self):
        with mock.patch.object(dream, "close", lambda: True):
            self.assertEqual(siri.do_step({"do": "dream", "action": "close"}), "closed")
        with mock.patch.object(dream, "open_scene", lambda scene: scene or "picked"):
            self.assertEqual(siri.do_step({"do": "dream", "scene": "rain"}), "rain-window")
            self.assertEqual(siri.do_step({"do": "dream"}), "picked")
        with mock.patch.object(dream, "is_open", lambda: False):
            with self.assertRaisesRegex(RuntimeError, "isn't on"):
                siri.do_step({"do": "dream", "action": "next"})

    def test_the_planner_hears_of_it_only_for_words_that_may_ask(self):
        self.assertIn('{"do":"dream"', dream.prompt_block("put on something with lofi vibes"))
        self.assertEqual(dream.prompt_block("what's the weather like"), "")

    def test_its_card_says_what_it_does(self):
        self.assertEqual(siri.step_label({"do": "dream", "scene": "rain-window"}), "Opening dream mode")
        self.assertEqual(siri.step_label({"do": "dream", "action": "next"}), "Changing the scene")
        self.assertEqual(siri.step_label({"do": "dream", "action": "close"}), "Leaving dream mode")


if __name__ == "__main__":
    unittest.main()
