"""Your hand as the mouse (handmouse.py, 29 October 2026): the pointer smoothed, placed from the middle of your palm as
in a mirror, a pinch a click or a drag and never a button left held, a right click with the middle finger, the hand
followed from frame to frame, and turned on and off by voice. A stand-in mouse, camera and hand finder: nothing here
moves the real pointer or opens the real camera."""
import unittest
from unittest import mock

import numpy as np

from tests.support import siri

import handmouse


def hand(cx, cy, pinch=False, right=False, size=50.0):
    """21 points of a hand whose palm's middle is near (cx, cy): its palm size long, thumb and index tips together if
    pinch, thumb and middle tips together if right."""
    p = np.zeros((21, 2), np.float32)
    p[handmouse.WRIST] = (cx, cy + size * 0.6)
    p[handmouse.MIDDLE_KNUCKLE] = (cx, cy - size * 0.4)
    p[5], p[13], p[17] = (cx - size * 0.3, cy - size * 0.35), (cx + size * 0.3, cy - size * 0.35), \
        (cx + size * 0.55, cy - size * 0.2)
    p[1], p[2] = (cx - size * 0.5, cy + size * 0.3), (cx - size * 0.7, cy)
    p[handmouse.THUMB] = (cx - size * 0.9, cy - size * 0.5)
    p[handmouse.INDEX] = (cx - size * 0.4, cy - size * 1.3)
    p[handmouse.MIDDLE] = (cx, cy - size * 1.4)
    if pinch:
        p[handmouse.INDEX] = p[handmouse.THUMB] + (size * 0.05, 0)
    if right:
        p[handmouse.MIDDLE] = p[handmouse.THUMB] + (size * 0.05, 0)
    return p


class FakeMouse:
    def __init__(self):
        self.did, self.at = [], None

    def move(self, x, y):
        self.at = (x, y)

    def press(self):
        self.did.append(("press", self.at))

    def release(self):
        self.did.append(("release", self.at))

    def right_click(self):
        self.did.append(("right", self.at))


class Smoothing(unittest.TestCase):
    def test_steady_when_still_quick_when_moving(self):
        f = handmouse.OneEuro()
        rng = np.random.default_rng(1)
        still = [f((500 + rng.normal(0, 4), 300), t / 30)[0] for t in range(60)]
        self.assertLess(np.std(still[20:]), 2.5)  # a shaking hand held still: a steady pointer
        f.reset()
        moved = [f((100 + 40 * t, 300), t / 30)[0] for t in range(30)]
        self.assertGreater(moved[-1], 100 + 40 * 29 - 120)  # keeps up with a quick move, a little behind


class Placing(unittest.TestCase):
    def test_the_middle_of_the_view_is_the_screen_as_in_a_mirror(self):
        p = handmouse.Pointer(FakeMouse(), (1920, 1080))
        x0, y0, x1, y1 = handmouse.BOX
        self.assertEqual(p.place((640 * (x0 + x1) / 2, 480 * (y0 + y1) / 2)), (960, 540))
        self.assertEqual(p.place((640 * x0, 480 * y0)), (1919, 0))  # your hand to the left of the view: the right
        self.assertEqual(p.place((640 * x1, 480 * y1)), (0, 1079))
        self.assertEqual(p.place((0, 0)), (1919, 0))  # past the box's edge: the screen's edge, never off it


class Pinching(unittest.TestCase):
    def setUp(self):
        self.mouse = FakeMouse()
        self.p = handmouse.Pointer(self.mouse, (1920, 1080))
        self.t = 0.0

    def frame(self, points):
        self.t += 1 / 30
        self.p.feed(points, self.t)

    def test_a_quick_pinch_is_a_click_where_you_were_pointing(self):
        for _ in range(10):
            self.frame(hand(320, 270))
        before = self.mouse.at
        self.frame(hand(321, 270, pinch=True))
        self.frame(hand(322, 271, pinch=True))
        self.frame(hand(322, 271))
        self.assertEqual([d[0] for d in self.mouse.did], ["press", "release"])
        self.assertEqual(self.mouse.did[0][1], before)  # pinching didn't nudge it
        self.assertEqual(self.mouse.did[1][1], before)

    def test_a_held_pinch_moved_is_a_drag(self):
        for _ in range(10):
            self.frame(hand(300, 270))
        self.frame(hand(300, 270, pinch=True))
        for x in range(300, 380, 4):
            self.frame(hand(x, 270, pinch=True))
        self.frame(hand(380, 270))
        press, release = self.mouse.did
        self.assertEqual((press[0], release[0]), ("press", "release"))
        self.assertLess(release[1][0], press[1][0] - 100)  # dragged across, mirrored

    def test_a_pinch_wavering_at_the_line_clicks_once(self):
        for _ in range(5):
            self.frame(hand(320, 270))
        base = hand(320, 270)
        size = 50.0
        for gap in (0.2, 0.26, 0.21, 0.27, 0.2):  # between PINCH and APART after the first: still the same pinch
            pts = base.copy()
            pts[handmouse.INDEX] = pts[handmouse.THUMB] + (size * gap, 0)
            self.frame(pts)
        self.assertEqual([d[0] for d in self.mouse.did], ["press"])

    def test_thumb_and_middle_finger_is_a_right_click_once(self):
        for _ in range(5):
            self.frame(hand(320, 270))
        for _ in range(5):
            self.frame(hand(320, 270, right=True))
        self.frame(hand(320, 270))
        self.frame(hand(320, 270, right=True))
        self.assertEqual([d[0] for d in self.mouse.did], ["right", "right"])

    def test_losing_the_hand_never_leaves_the_button_held(self):
        self.frame(hand(320, 270))
        self.frame(hand(320, 270, pinch=True))
        self.frame(None)
        self.assertEqual([d[0] for d in self.mouse.did], ["press", "release"])


class Following(unittest.TestCase):
    def test_a_palm_for_the_next_frame_from_this_ones_points(self):
        palm = handmouse.palm_from(hand(320, 270))
        self.assertEqual(palm.shape, (19,))
        x1, y1, x2, y2 = palm[:4]
        self.assertAlmostEqual(float(x2 - x1), float(y2 - y1), places=3)  # square, as the palm finder's
        kp = palm[4:18].reshape(7, 2)
        self.assertTrue(((kp >= (x1, y1)) & (kp <= (x2, y2))).all())
        np.testing.assert_allclose(kp[0], hand(320, 270)[handmouse.WRIST])  # in the palm finder's own order

    def test_followed_frame_to_frame_and_stopped_with_no_hand_for_a_while(self):
        class Camera:
            def __init__(self):
                self.t, self.held = 0.0, []

            def newest_bgr(self, after=0.0, wait=0.25):
                self.t += 1 / 30
                return self.t, np.zeros((480, 640, 3), np.uint8)

            def hold(self, name, fps):
                self.held.append(("hold", name, fps))

            def let_go(self, name):
                self.held.append(("let go", name))

        cam, seen, now = Camera(), {"palms": 0, "followed": 0}, [0.0]

        class Finder:
            def palm_boxes(self, bgr):
                seen["palms"] += 1
                return [np.r_[300, 250, 340, 290, np.zeros(14), 0.9]] if cam.t < 1.0 else []

            def points(self, bgr, palm):
                if palm[-1] != 0.9:
                    seen["followed"] += 1  # followed from the last frame's points
                return {"points": hand(320, 270)} if cam.t < 1.0 else None

        stops = []
        m = handmouse.HandMouse(cam, hands=Finder(), mouse=FakeMouse(), screen=(1920, 1080), on_stop=stops.append,
                                clock=lambda: now.__setitem__(0, now[0] + 0.5) or now[0])
        m._run()
        self.assertEqual(seen["palms"] - seen["followed"] < 5, False)  # the palm finder only once it's lost it
        self.assertGreater(seen["followed"], 20)
        self.assertEqual(cam.held, [("hold", "hands", handmouse.FPS), ("let go", "hands")])
        self.assertEqual(stops, ["I couldn't see your hand for a minute"])


class Said(unittest.TestCase):
    def say(self, words, gate=True):
        return handmouse.quick(words, siri.plain, gate)

    def test_on_and_off_by_voice_never_from_across_the_room(self):
        started = []
        with mock.patch.object(handmouse, "start", lambda: started.append(1) or "on"):
            for words in ("hand control on", "turn on hand control", "start gesture control",
                          "control the PC with my hand", "use my hand as the mouse"):
                self.assertEqual(self.say(words)["say"], "on", words)
            self.assertIsNone(self.say("hand control on", gate="cold"))
        self.assertEqual(len(started), 5)
        running = mock.Mock(running=True)
        with mock.patch.dict(handmouse.NOW, {"mouse": running}):
            self.assertIn("off", self.say("stop hand control")["say"])
        running.stop.assert_called_once()
        with mock.patch.dict(handmouse.NOW, {"mouse": None}):
            self.assertIn("isn't on", self.say("turn off hand control")["say"])
            self.assertIn("isn't on", self.say("hand control off", gate="cold")["say"])  # off, from anywhere
        self.assertIsNone(self.say("hand me the remote"))

    def test_the_planner_has_its_step_only_for_words_of_it(self):
        self.assertEqual(handmouse.prompt_block("open spotify"), "")
        self.assertIn('{"do":"hand_control"', handmouse.prompt_block("let my hand move the mouse"))
        self.assertTrue(siri.toolbox.get("hand_control").confirm)


if __name__ == "__main__":
    unittest.main()
