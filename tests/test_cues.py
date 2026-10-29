"""What she sees or hears that starts something (cues.py, camera.py, claps.py, 29 October 2026): claps and snaps told
from knocks and talking, you going and coming back as the camera sees it, the rules taught and forgotten by voice,
and done only when what they need is so. Nothing here opens the real camera, listens to the real mic or goes online:
made-up sounds, a fake camera and a fake clock stand in."""
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from unittest import mock

import numpy as np

from tests.support import siri

import camera
import claps
import cues
import hands
import settings

R = 16000


def burst(rng, decay_ms, lo, hi, amp):
    n = int(R * 0.25)
    t = np.arange(n) / R
    spec = np.fft.rfft(rng.normal(0, 1, n))
    f = np.fft.rfftfreq(n, 1 / R)
    spec[(f < lo) | (f > hi)] = 0
    x = np.fft.irfft(spec, n)
    return amp * x / np.abs(x).max() * np.exp(-t / (decay_ms / 1000))


def scene(rng, seconds, events, hiss=0.0015):
    """The room's hiss with sounds put in it: [(at seconds, sound)]."""
    a = rng.normal(0, hiss, int(R * seconds))
    for at, sound in events:
        i = int(at * R)
        a[i:i + len(sound)] += sound[:len(a) - i]
    return a.astype(np.float32)


def heard(audio, allowed=lambda i: True, played=None, at=None):
    got = []
    c = claps.Clapper(got.append, log=lambda line: None, played=played)
    for n, i in enumerate(range(0, len(audio), 512)):
        ok = allowed(n)
        if ok is None:
            c.drop()
        c.feed(audio[i:i + 512], bool(ok), None if at is None else at + i / R)
    return got


class Claps(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(7)
        self.clap = lambda amp=0.6: burst(self.rng, 25, 300, 2500, amp)
        self.snap = lambda amp=0.3: burst(self.rng, 7, 2200, 7900, amp)

    def test_two_claps_are_the_cue_one_alone_isnt(self):
        self.assertEqual(heard(scene(self.rng, 3, [(1.0, self.clap()), (1.35, self.clap())])), ["clap"])
        self.assertEqual(heard(scene(self.rng, 3, [(1.0, self.clap()), (1.7, self.clap(0.4))])), ["clap"])
        self.assertEqual(heard(scene(self.rng, 3, [(1.0, self.clap())])), [])
        self.assertEqual(heard(scene(self.rng, 4, [(1.0, self.clap()), (2.5, self.clap())])), [])  # too far apart

    def test_a_snap_loud_or_soft(self):
        self.assertEqual(heard(scene(self.rng, 3, [(1.0, self.snap())])), ["snap"])
        self.assertEqual(heard(scene(self.rng, 3, [(1.0, self.snap(0.08))])), ["snap"])

    def test_snapping_away_is_one_snap_and_two_snaps_are_no_double_clap(self):
        three = scene(self.rng, 4, [(1.0, self.snap()), (1.5, self.snap()), (2.0, self.snap())])
        self.assertEqual(heard(three), ["snap"])  # the third is the same snapping
        self.assertEqual(heard(scene(self.rng, 3, [(1.0, self.snap()), (1.4, self.snap())])), ["snap"])

    def test_heard_over_music_but_not_what_the_pc_plays(self):
        t = np.arange(R * 4) / R
        song = (0.05 * np.sin(2 * np.pi * 220 * t) + 0.03 * np.sin(2 * np.pi * 330 * t)).astype(np.float32)
        audio = scene(self.rng, 4, [(0, song), (1.5, self.snap())])
        self.assertEqual(heard(audio), ["snap"])  # music's low notes don't hide it
        self.assertEqual(heard(audio, played=lambda start, end: True, at=100.0), [])  # a drum in the song
        maybes = []  # or the owner's snap over it: their hand up says which, so it's the camera's
        c = claps.Clapper(lambda kind: None, log=lambda line: None, played=lambda start, end: True,
                          on_maybe=maybes.append)
        for i in range(0, len(audio), 512):
            c.feed(audio[i:i + 512], True, 100.0 + i / R)
        self.assertEqual(len(maybes), 1)
        self.assertAlmostEqual(maybes[0], 101.5, delta=0.1)
        asked = []
        heard(audio, played=lambda start, end: asked.append((start, end)) or False, at=100.0)
        self.assertEqual(len(asked), 1)
        self.assertLess(asked[0][0], 101.5)  # round when it was heard: a little before and just after
        self.assertGreater(asked[0][1], 101.5)

    def test_what_the_pc_plays_is_told_by_its_own_sharp_sounds(self):
        pc = claps.PCSound()
        quiet = self.rng.normal(0, 0.002, 512).astype(np.float32)
        for k in range(60):
            pc.feed(quiet, at=50.0 + k * 512 / R)
        self.assertFalse(pc.played(50.0, 52.0))
        hit = quiet.copy()
        hit[100:180] += burst(self.rng, 5, 2500, 7000, 0.4)[:80]
        pc.feed(hit, at=52.0)
        self.assertTrue(pc.played(51.9, 52.1))
        self.assertFalse(pc.played(53.0, 54.0))
        self.assertFalse(claps.PCSound().played(0, 1))  # nothing heard from the PC yet

    def test_not_a_quiet_room_talking_or_a_knock(self):
        self.assertEqual(heard(scene(self.rng, 3, [])), [])
        t = np.arange(R * 2) / R
        voice = 0.15 * np.sin(2 * np.pi * 160 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
        self.assertEqual(heard(scene(self.rng, 4, [(1.0, voice)])), [])
        knock = lambda: burst(self.rng, 40, 60, 600, 0.5)
        self.assertEqual(heard(scene(self.rng, 3, [(1.0, knock()), (1.3, knock())])), [])  # knock knock

    def test_never_while_not_allowed(self):
        audio = scene(self.rng, 3, [(1.0, self.clap()), (1.35, self.clap())])
        self.assertEqual(heard(audio, allowed=lambda n: False), [])  # talking or dictating
        second = int(1.35 * R / 512)  # the second clap while someone talks: no double clap
        self.assertEqual(heard(audio, allowed=lambda n: not second - 2 <= n <= second + 8), [])

    def test_one_that_started_counts_even_if_talking_starts_with_it_but_not_a_key(self):
        audio = scene(self.rng, 3, [(1.0, self.snap())])
        at = int(1.0 * R / 512)
        self.assertEqual(heard(audio, allowed=lambda n: n <= at), ["snap"])  # its own sound woke the listener
        self.assertEqual(heard(audio, allowed=lambda n: True if n <= at else None), [])  # a key's click

    def test_in_the_mics_own_sound_the_owners_snap_and_nothing_else(self):
        # what the owner's laptop heard on 29 October, by its loudness in the high notes 4 ms at a time: the room
        # round -58 dBFS, a thump on the desk 18 dB over it (low, not counted), and their snap 40 dB over it
        rng = np.random.default_rng(3)
        room = rng.normal(0, 0.0012, R * 3).astype(np.float32)
        thump = burst(rng, 30, 80, 500, 0.4)
        snap = burst(rng, 5, 1500, 4500, 0.35)
        self.assertEqual(heard(room + scene(rng, 3, [(0.7, thump)], hiss=0)), [])
        self.assertEqual(heard(room + scene(rng, 3, [(0.7, snap)], hiss=0)), ["snap"])

    def test_claps_that_ring_in_a_room_still_count_twice_over(self):
        # 29 October: the owner's claps rang 60 to 100 ms in their room, one at 0.7 kHz, and none had counted
        ringing = lambda: burst(self.rng, 45, 300, 2500, 0.6)  # 60 to 70 ms in its high notes
        self.assertEqual(heard(scene(self.rng, 3, [(1.0, ringing()), (1.4, ringing())])), ["clap"])
        self.assertEqual(heard(scene(self.rng, 3, [(1.0, ringing())])), [])  # one alone isn't the cue

    def test_one_sharp_high_sound_that_rings_asks_the_camera(self):
        maybes, got = [], []
        c = claps.Clapper(got.append, log=lambda line: None, on_maybe=maybes.append)
        audio = scene(self.rng, 3, [(1.0, burst(self.rng, 40, 1400, 5000, 0.4))])  # a snap that rang 70-100 ms
        for i in range(0, len(audio), 512):
            c.feed(audio[i:i + 512], True, 200.0 + i / R)
        self.assertEqual(got, [])  # not a snap by its sound alone
        self.assertEqual(len(maybes), 1)
        self.assertAlmostEqual(maybes[0], 201.0, delta=0.1)  # when it was heard, for the camera's frames then
        maybes.clear()  # a short, high one is a snap by itself, the camera not asked
        quick = scene(self.rng, 3, [(1.0, self.snap())])
        c = claps.Clapper(got.append, log=lambda line: None, on_maybe=maybes.append)
        for i in range(0, len(quick), 512):
            c.feed(quick[i:i + 512], True, 300.0 + i / R)
        self.assertEqual((got, maybes), (["snap"], []))


class FakeCapture:
    """cv2.VideoCapture's stand-in: a numbered frame each read, at about 20 a second."""

    def __init__(self):
        self.n = 0

    def read(self):
        time.sleep(0.05)
        self.n += 1
        return True, np.full((480, 640, 3), self.n % 255, np.uint8)

    def release(self):
        pass


class Frames(unittest.TestCase):
    def test_frames_kept_a_few_seconds_at_half_size_and_the_newest_whole(self):
        cam = camera.Camera()
        cam.cap, cam.stop = FakeCapture(), threading.Event()
        with mock.patch.object(camera, "KEEP", 0.5):
            cam.reader = threading.Thread(target=cam._read, args=(cam.cap, cam.stop), daemon=True)
            cam.reader.start()
            time.sleep(0.9)
            kept = cam.around(0, time.monotonic() + 1)
            self.assertTrue(4 <= len(kept) <= 13, len(kept))  # half a second of them, the older let go
            self.assertEqual(kept[0][1].shape, (240, 320, 3))
            self.assertLess(kept[-1][0] - kept[0][0], 0.55)
            self.assertEqual(cam.frame().shape, (480, 640, 3))
            self.assertEqual(cam.around(0, 1), [])  # nothing from long ago
            cam.close()
        self.assertFalse(cam.on)
        self.assertIsNone(cam.frame(wait=0.1))
        self.assertEqual(cam.around(0, time.monotonic() + 1), [])


class Snaps(unittest.TestCase):
    """A snap seen: a sharp sound with your hand up in front of the camera then (cues._maybe_snap)."""

    def setUp(self):
        self.ran = []
        for patch in (mock.patch.dict(cues.NOW, {"hooks": {"run": lambda words, why: self.ran.append(words)},
                                                 "fired": {}, "music": True, "eyes": None, "hands": None}),
                      mock.patch.object(cues, "rules", lambda: [{"on": "snap", "do": "dream mode",
                                                                 "need": ["music"]}])):
            patch.start()
            self.addCleanup(patch.stop)
        self.frames = [(t, np.zeros((240, 320, 3), np.uint8)) for t in (99.4, 99.8, 100.2, 100.6)]
        cam = mock.Mock(on=True)
        cam.around = lambda start, end: [f for f in self.frames if start <= f[0] <= end]
        cues.NOW["eyes"] = mock.Mock(camera=cam)
        self.palms = []
        cues.NOW["hands"] = mock.Mock(palm_boxes=lambda bgr, **kw: self.palms)

    def look(self, at=100.0):
        with mock.patch.object(cues.threading, "Thread", lambda target, args, **kw: mock.Mock(
                start=lambda: target(*args))):
            cues._maybe_snap(at)
        time.sleep(0.05)  # _cued's own thread

    def test_a_hand_up_makes_the_sound_a_snap(self):
        self.palms = [np.r_[100, 80, 160, 150, np.zeros(14), 0.9]]  # 60 px of 320: a hand at the laptop
        with mock.patch.object(cues, "_cue", lambda kind: self.ran.append(kind)):
            self.look()
        self.assertEqual(self.ran, ["snap"])

    def test_no_hand_or_a_far_one_isnt(self):
        with mock.patch.object(cues, "_cue", lambda kind: self.ran.append(kind)):
            self.look()
            self.palms = [np.r_[100, 80, 110, 90, np.zeros(14), 0.9]]  # 10 px: across the room
            self.look()
        self.assertEqual(self.ran, [])

    def test_only_with_a_snap_rule_and_the_camera_on(self):
        self.palms = [np.r_[100, 80, 160, 150, np.zeros(14), 0.9]]
        with mock.patch.object(cues, "_cue", lambda kind: self.ran.append(kind)), \
                mock.patch.object(cues, "rules", lambda: [{"on": "clap", "do": "work mode"}]):
            self.look()
        cues.NOW["eyes"].camera.on = False
        with mock.patch.object(cues, "_cue", lambda kind: self.ran.append(kind)):
            self.look()
        self.assertEqual(self.ran, [])


class Hands(unittest.TestCase):
    def test_the_palm_finders_places_are_mediapipes(self):
        a = hands.anchors()
        self.assertEqual(a.shape, (2016, 2))
        self.assertAlmostEqual(float(a[0][0]), 0.5 / 24)
        self.assertAlmostEqual(float(a[-1][1]), 11.5 / 12)

    def test_how_the_thumb_and_middle_finger_are(self):
        points = np.zeros((21, 2), np.float32)
        points[hands.MIDDLE_KNUCKLE] = (0, -100)  # a palm 100 px long
        points[hands.THUMB_TIP], points[hands.MIDDLE_TIP] = (20, -160), (20, -180)
        near, curl = hands.shape(points)
        self.assertAlmostEqual(near, 0.2, places=3)  # thumb on the middle tip: ready to snap
        self.assertAlmostEqual(curl, np.hypot(20, 180) / 100, places=3)

    def test_its_models_are_downloaded_once_and_checked(self):
        import speech
        for name in ("palm", "hand"):
            self.assertIn(name, speech.MODELS)
            self.assertEqual(len(speech.SHA256[name]), 64)


class FakeCamera:
    def __init__(self, eyes_on):
        self.eyes_on, self.cap, self.opened, self.broken = eyes_on, None, 0, False

    def open(self):
        if self.broken:
            raise RuntimeError("the camera won't open")
        if self.cap is None:
            self.cap, self.opened = True, self.opened + 1
        return self

    def frame(self):
        return np.full((480, 640, 3), 1 if self.eyes_on() else 0, np.uint8)

    def close(self):
        self.cap = None

    @property
    def on(self):
        return self.cap is not None


class FakeFaces:
    def find(self, rgb):
        return [(200, 120, 220, 220, 0.95)] if rgb[0, 0, 0] else []


class Eyes(unittest.TestCase):
    """You going and coming back, as the camera and your typing say."""

    def setUp(self):
        self.now, self.idle, self.locked, self.there = 1000.0, 0.0, False, True
        self.backs, self.looks = [], []
        self.cam = FakeCamera(lambda: self.there)
        self.eyes = camera.Eyes(on_back=lambda since, rgb: self.backs.append((since, rgb is not None)),
                                on_look=lambda rgb: self.looks.append(self.now), wants_look=lambda: True,
                                idle=lambda: self.idle, locked=lambda: self.locked, camera=self.cam,
                                faces=FakeFaces(), clock=lambda: self.now)

    def go(self, seconds, idle_too=True):
        for _ in range(int(seconds / camera.EVERY)):
            self.now += camera.EVERY
            if idle_too:
                self.idle += camera.EVERY
            self.eyes.tick()

    def test_watching_all_the_time_typing_or_not(self):
        self.idle = 0.5
        self.eyes.tick()
        self.assertTrue(self.cam.on)
        self.idle = 600.0
        self.go(10)
        self.assertTrue(self.cam.on)
        self.assertEqual(self.backs, [])
        self.assertEqual(self.cam.opened, 1)  # opened once and kept open

    def test_gone_and_back_in_front_of_it_is_welcomed_once(self):
        self.idle = 600.0
        self.go(10)
        self.assertTrue(self.cam.on)  # idle: watching
        self.there = False
        self.go(camera.AWAY + camera.BACK_AFTER + 30)
        self.assertIsNotNone(self.eyes.gone)
        self.there = True
        self.go(4)
        self.assertEqual(len(self.backs), 1)
        self.assertTrue(self.backs[0][1])  # with what she saw
        self.go(20)
        self.assertEqual(len(self.backs), 1)

    def test_back_by_typing_after_a_while_away(self):
        self.idle = 600.0
        self.there = False
        self.go(camera.AWAY + camera.BACK_AFTER + 10)
        self.idle = 0.0
        self.now += 1
        self.eyes.tick()
        self.assertEqual(self.backs, [(self.backs[0][0], False)])  # with the camera covered: your typing said so

    def test_a_short_time_away_is_no_welcome(self):
        self.idle = 600.0
        self.there = False
        self.go(camera.AWAY + 20)
        self.there = True
        self.go(4)
        self.assertEqual(self.backs, [])

    def test_locked_is_left_to_the_unlock(self):
        self.idle = 600.0
        self.there = False
        self.go(camera.AWAY + camera.BACK_AFTER + 10)
        self.locked = True
        self.go(4)
        self.assertFalse(self.cam.on)
        self.locked, self.idle = False, 0.0
        self.go(2, idle_too=False)
        self.assertEqual(self.backs, [])  # unlocking is welcomed by watch_return, not twice

    def test_looks_every_couple_of_minutes_while_nothing_changes(self):
        self.idle = 1.0
        self.go(camera.LOOK_EVERY * 2 + 10, idle_too=False)
        self.assertEqual(len(self.looks), 3)  # straight away, then every LOOK_EVERY

    def test_looks_again_as_soon_as_you_look_different_and_settle(self):
        rng = np.random.default_rng(5)
        z = lambda a: (a - a.mean()) / a.std()
        glasses_off, glasses_on = z(rng.normal(size=(26, 56))), z(rng.normal(size=(26, 56)))
        face = {"band": glasses_off}
        with mock.patch.object(camera, "eye_band", lambda rgb, f: face["band"]):
            self.go(4, idle_too=False)
            self.assertEqual(len(self.looks), 1)  # the first look
            self.go(30, idle_too=False)
            self.assertEqual(len(self.looks), 1)  # the same face: no more till LOOK_EVERY
            face["band"] = glasses_on
            self.go(2 * camera.EVERY, idle_too=False)
            self.assertEqual(len(self.looks), 1)  # not while it's still changing
            self.go(camera.EVERY, idle_too=False)
            self.assertEqual(len(self.looks), 2)  # settled and different: looked at again
            face["band"] = glasses_off  # straight back off: not again till LOOK_GAP after the last look
            self.go(camera.LOOK_GAP - 4, idle_too=False)
            self.assertEqual(len(self.looks), 2)
            self.go(6, idle_too=False)
            self.assertEqual(len(self.looks), 3)
            self.go(30, idle_too=False)
            self.assertEqual(len(self.looks), 3)  # and the same face after: no more

    def test_a_camera_that_wont_open_isnt_tried_every_frame(self):
        self.cam.broken = True
        self.idle = 600.0
        tries = []
        open_ = self.cam.open
        self.cam.open = lambda: tries.append(self.now) or open_()
        self.go(camera.RETRY - 5)
        self.assertEqual(len(tries), 1)
        self.go(10)
        self.assertEqual(len(tries), 2)

    def test_there_typing_seen_or_no_camera_to_tell(self):
        self.idle = 0.5
        self.assertTrue(self.eyes.here())
        self.idle, self.there = 600.0, False
        self.eyes.seen = self.now - 600
        self.assertFalse(self.eyes.here())
        self.there = True
        self.assertTrue(self.eyes.here())
        self.cam.broken, self.there = True, False
        self.assertTrue(self.eyes.here())  # no camera: the claps were someone's


class Rules(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="cues-")
        self.addCleanup(shutil.rmtree, self.folder, True)
        for patch in (mock.patch.object(cues, "PATH", os.path.join(self.folder, "cues.json")),
                      mock.patch.dict(settings._load(), {"cues": True})):
            patch.start()
            self.addCleanup(patch.stop)
        self.ran = []
        self.hooks = {"welcome": lambda since: self.ran.append(("welcome", since)),
                      "run": lambda words, why: self.ran.append((words, why)), "playing": lambda: False,
                      "look": lambda rgb, looks: {}, "echo": lambda: True}
        patch = mock.patch.dict(cues.NOW, {"hooks": self.hooks, "eyes": None, "music": False, "fired": {}, "looks": {},
                                           "welcomed": 0.0})
        patch.start()
        self.addCleanup(patch.stop)

    def say(self, words, gate=False):
        return cues.quick(words, siri.plain, gate)

    def test_the_owners_three_to_start_with(self):
        self.assertEqual([(r["on"], r["do"]) for r in cues.rules()],
                         [("clap", "work mode"), ("snap", "dream mode"), ("look", "turn on light mode")])
        self.assertEqual(cues.rules()[1]["need"], ["here", "music"])

    def test_taught_by_saying_so(self):
        self.assertIn("two claps in front of the laptop, open spotify", self.say("When I clap, open Spotify")["say"])
        self.assertEqual([r["do"] for r in cues.rules() if r["on"] == "clap"], ["open spotify"])  # in place of the old
        plan = self.say("when I snap my fingers while music is playing turn on dream mode")
        self.assertEqual([r.get("need") for r in cues.rules() if r["on"] == "snap"], [["here", "music"]])
        self.assertIn("while music plays", plan["say"])
        self.say("when I wear my spectacles enable the light mode")
        self.say("when I take off my glasses turn on dark mode")
        looks = {r["look"]: r["do"] for r in cues.rules() if r["on"] == "look"}
        self.assertEqual(looks["wearing spectacles"], "enable the light mode")
        self.assertEqual(looks["not wearing glasses"], "turn on dark mode")
        self.say("when I come back to the laptop read my messages")
        self.assertEqual([r["do"] for r in cues.rules() if r["on"] == "back"], ["read my messages"])

    def test_forgotten_and_listed(self):
        self.assertIn("dream mode", self.say("what do my snaps do")["say"])
        self.assertIn("I've forgotten 1", self.say("forget the snap")["say"])
        self.assertEqual([r["on"] for r in cues.rules()], ["clap", "look"])
        self.assertIn("forgotten 1", self.say("remove my glasses rule")["say"])
        self.assertEqual(self.say("forget the snap")["say"], "I don't have one like that.")
        self.assertIsNone(self.say("stop the music"))  # not one of these

    def test_the_camera_on_and_off_by_voice_never_from_across_the_room(self):
        self.assertIsNone(self.say("turn on your camera", gate="cold"))
        self.say("turn off your camera")
        self.assertFalse(settings.get("cues"))
        self.say("watch me")
        self.assertTrue(settings.get("cues"))
        self.assertIsNone(self.say("when I clap open Spotify", gate="cold"))
        for words in ("Can you watch me?", "watch me all the time", "keep watching me", "please look at me"):
            settings.put("cues", False)
            self.assertIn("watch", self.say(words)["say"], words)
            self.assertTrue(settings.get("cues"), words)
        self.say("stop watching me")
        self.assertFalse(settings.get("cues"))

    def test_can_you_see_me_is_answered_from_a_look_now_or_why_not(self):
        settings.put("cues", False)
        self.assertIn("camera's off", self.say("can you see me?")["say"])
        settings.put("cues", True)
        asked = []
        self.hooks["see"] = lambda rgb, question: asked.append(question) or "Yes, I can see you, with your glasses on."
        eyes = mock.Mock(camera=mock.Mock(on=True), failed=None)
        eyes.snap.return_value = np.zeros((4, 4, 3), np.uint8)
        cues.NOW["eyes"] = eyes
        self.assertEqual(self.say("Can you see me?")["say"], "Yes, I can see you, with your glasses on.")
        self.assertEqual(asked, ["Can you see me?"])
        self.assertEqual(self.say("what am I wearing")["steps"], [])
        eyes.snap.return_value, eyes.failed = None, "the camera won't open"
        self.assertIn("won't open", self.say("do you see me")["say"])
        self.assertIsNone(self.say("can you see the screen"))  # the screen's another matter
        eyes.snap.return_value = np.zeros((4, 4, 3), np.uint8)
        self.assertEqual(self.say("can you see me", gate="cold")["say"], "Yes, I can see you, with your glasses on.")
        self.assertIsNone(self.say("watch me", gate="cold"))  # but the camera's never turned on from across the room

    def test_the_planner_knows_her_eyes_only_for_words_about_them(self):
        self.assertEqual(cues.prompt_block("open spotify"), "")
        block = cues.prompt_block("can you see what I'm wearing")
        self.assertIn('{"do":"camera"', block)
        self.assertIn("two claps in front of the laptop, work mode", block)
        self.assertIsNotNone(cues.toolbox.get("camera"))
        self.assertEqual(cues._step({"ask": "glasses?"}), {"camera": cues.look_now("glasses?")})

    def test_no_clap_starts_while_someone_talks_or_you_type(self):
        idle = [60.0]
        self.hooks["idle"] = lambda: idle[0]
        self.assertTrue(cues._allowed())
        cues.busy(True)
        self.assertFalse(cues._allowed())
        cues.NOW["busy"] = 0.0
        idle[0] = 0.2
        self.assertIsNone(cues._allowed())  # typing: a sharp sound that started was a key

    def test_a_snap_with_no_music_on_says_so_now_and_then(self):
        said = []
        self.hooks["say"] = said.append
        with mock.patch.dict(cues.NOW, {"hinted": 0.0}):
            cues._cued("snap")
            cues._cued("snap")
        self.assertEqual(len(said), 1)  # once, not every snap
        self.assertIn("needs music playing on the laptop", said[0])
        self.assertEqual(self.ran, [])

    def test_a_clap_or_snap_only_when_what_it_needs_is_so(self):
        cues._cued("clap")  # nobody to see: no camera on, so taken as there
        self.assertEqual(self.ran, [("work mode", "two claps")])
        cues._cued("snap")  # dream mode only with music on
        self.assertEqual(len(self.ran), 1)
        cues.NOW["music"] = True
        cues._cued("snap")
        self.assertEqual(self.ran[-1], ("dream mode", "a snap"))
        cues.NOW["eyes"] = mock.Mock(here=lambda: False)
        cues._cued("clap")
        self.assertEqual(len(self.ran), 2)  # nobody in front of the laptop

    def test_a_look_starts_its_rule_as_it_comes_true_not_while_it_stays(self):
        seen = {"wearing glasses": True}
        self.hooks["look"] = lambda rgb, looks: {k: v for k, v in seen.items() if k in looks}
        rgb = np.zeros((4, 4, 3), np.uint8)
        cues._looked(rgb)
        cues._looked(rgb)
        self.assertEqual(self.ran, [("turn on light mode", "you're wearing glasses")])
        seen["wearing glasses"] = False
        cues._looked(rgb)
        seen["wearing glasses"] = True
        cues._looked(rgb)
        self.assertEqual(len(self.ran), 2)

    def test_back_at_the_laptop_a_welcome_then_its_rules(self):
        self.say("when I come back read my messages")
        cues._back(123.0, None)
        cues._back(124.0, None)  # again straight after: no second welcome
        self.assertEqual(self.ran, [("welcome", 123.0), ("read my messages", "coming back to the laptop"),
                                    ("read my messages", "coming back to the laptop")])


class Look(unittest.TestCase):
    def test_one_small_picture_to_the_model_that_sees(self):
        sent = {}

        def chat(key, messages, **kw):
            sent["messages"], sent["model"] = messages, kw.get("model")
            return '{"1": true, "2": false}', None, None
        with mock.patch.object(siri.opencode, "chat", chat):
            got = siri.camera_look(np.zeros((480, 640, 3), np.uint8), ["wearing glasses", "wearing a cap"])
        self.assertEqual(got, {"wearing glasses": True, "wearing a cap": False})
        self.assertEqual(sent["model"], siri.BACKUP_MODEL)
        parts = sent["messages"][1]["content"]
        self.assertEqual(parts[0]["text"], "1. They are wearing glasses.\n2. They are wearing a cap.")
        self.assertTrue(parts[1]["image_url"]["url"].startswith("data:image/png;base64,"))
        with mock.patch.object(siri.opencode, "chat", side_effect=RuntimeError("offline")):
            self.assertEqual(siri.camera_look(np.zeros((8, 8, 3), np.uint8), ["wearing glasses"]), {})

    def test_off_till_turned_on_and_on_this_pc(self):
        self.assertFalse(settings.DEFAULTS["cues"])
        with open(os.path.join(os.path.dirname(camera.__file__), "requirements.txt"), encoding="utf-8") as f:
            self.assertIn("opencv-python-headless==", f.read())


if __name__ == "__main__":
    unittest.main()
