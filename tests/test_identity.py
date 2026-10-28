"""28 October 2026: her name. Harry, or one you give her ("call yourself Friday", Settings > Her name), which she
answers to and calls herself from then on (identity.py), her island as her logo, and the move from Hey Jev, her name
till then: her folders, her keys and what she wrote about herself. No model, voice or network."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests.support import siri, winplatform  # temp APPDATA and the tripwires, before anything else

import identity
import island
import secrets_store
import settings


class Renaming(unittest.TestCase):
    def setUp(self):
        self.addCleanup(self.harry_again)
        siri.soul()  # SOUL.md as it is by default, to see her new name go into

    def harry_again(self):
        settings.put("nickname", "")
        if os.path.exists(siri.SOUL_PATH):
            os.remove(siri.SOUL_PATH)
        siri.use_name()

    def rename(self, text):
        with mock.patch("builtins.print"):
            return identity.rename(text)


class Named(Renaming):
    def test_harry_unless_you_give_her_another(self):
        self.assertEqual((identity.name(), identity.hey()), ("Harry", "Hey Harry"))
        self.assertEqual(identity.named("Say Hey Harry"), "Say Hey Harry")
        self.assertIn("You are Harry,", siri.soul())
        self.assertEqual(siri.prompt(), siri.PROMPT)  # the prompt the model reads back from its cache, as it was

    def test_a_name_is_kept_as_one(self):
        self.assertEqual(identity.clean(" friday. "), "Friday")
        self.assertEqual(identity.clean("mister robot"), "Mister Robot")
        self.assertEqual(identity.clean("Jean-Luc"), "Jean-Luc")
        for bad in ("", "open", "hey", "R2D2", "one two three four", "x", "stop", "Hey Max"):
            with self.subTest(bad=bad):
                self.assertIsNone(identity.clean(bad))

    def test_a_new_name_is_hers_everywhere_at_once(self):
        self.assertEqual(self.rename("friday"), "Friday")
        self.assertEqual(settings.get("nickname"), "Friday")
        self.assertEqual(identity.named("Harry's island"), "Friday's island")
        self.assertEqual(siri.find_name("Hey Friday, open Chrome"), (True, "open Chrome"))
        self.assertEqual(siri.find_name("Friday, what time is it?"), (True, "what time is it"))
        self.assertTrue(siri.find_name("Jarvis, mute")[0])  # her second name, whatever her first
        self.assertIsNone(siri.find_name("Hey Harry, open Chrome"))  # not her name any more
        self.assertIsNone(siri.find_name("I'm free on Friday"))  # a word, not her called
        self.assertIn("You are Friday,", siri.soul())  # she calls herself by it
        self.assertNotIn("Harry", siri.soul())
        self.assertIn("words that sound like it", siri.prompt())
        self.assertIn("“Hey Friday”", siri.ready_text(True))

    def test_the_stop_phrase_goes_with_her_new_name(self):
        self.rename("Max")
        d = siri.Dictation(lambda: siri.NAMES)
        d.start()
        d.add("Buy milk on the way home.")
        self.assertTrue(d.add("Hey Max, stop transcribing."))
        self.assertEqual(d.finish(), "Buy milk on the way home.")

    def test_back_to_harry(self):
        self.rename("Max")
        self.rename("harry")
        self.assertEqual((settings.get("nickname"), identity.name()), ("", "Harry"))
        self.assertIn("You are Harry,", siri.soul())
        self.assertTrue(siri.find_name("Hey Harry, open Chrome")[0])

    def test_hooks_hear_of_it(self):
        heard = []
        identity.on_rename(lambda old, new: heard.append((old, new)))
        self.addCleanup(identity._hooks.pop)
        self.rename("Luna")
        self.assertEqual(heard, [("Harry", "Luna")])

    def test_one_she_cant_have_changes_nothing(self):
        with self.assertRaises(ValueError):
            self.rename("open")
        self.assertEqual(identity.name(), "Harry")
        with mock.patch.object(identity, "_swap", return_value=False), self.assertRaises(OSError):
            self.rename("Max")  # SOUL.md couldn't be written: she'd answer to one name and call herself another
        self.assertEqual(identity.name(), "Harry")


class Said(Renaming):
    """Her name changed by voice: "call yourself Friday" (siri.rename_said, in the fast path)."""

    def test_call_yourself(self):
        with mock.patch("builtins.print"):
            plan = siri.quick("call yourself Luna")
        self.assertEqual(identity.name(), "Luna")
        self.assertEqual(plan["steps"], [])
        self.assertIn("I'm Luna now", plan["say"])

    def test_the_ways_to_say_it(self):
        for said, name in (("Your name is Max now.", "Max"), ("change your name to Friday", "Friday"),
                           ("Can I call you Nova?", "Nova"), ("I'll call you Jarvis", "Jarvis"),
                           ("From now on, call yourself Mister Robot.", "Mister Robot")):
            with self.subTest(said=said), mock.patch("builtins.print"):
                self.assertTrue(siri.rename_said(said))
                self.assertEqual(identity.name(), name)

    def test_not_a_rename(self):
        for said in ("I'll call you later", "I'll call you back tomorrow", "call my mum", "what's your name",
                     "I will call you when I'm free"):
            with self.subTest(said=said):
                self.assertIsNone(siri.rename_said(said))
        self.assertIsNone(siri.rename_said("call yourself Max", gate="cold"))  # never from across the room
        self.assertEqual(identity.name(), "Harry")

    def test_a_name_she_cant_have_is_said_so(self):
        plan = siri.rename_said("call yourself open")
        self.assertIn("can't be my name", plan["say"])
        self.assertEqual(identity.name(), "Harry")
        self.assertIn("already", siri.rename_said("Your name is Harry, right?")["say"])


class Logo(unittest.TestCase):
    def test_her_island_as_a_picture(self):
        back = (0.06, 0.07, 0.09)
        rgb = island.logo(24, back=back)
        self.assertEqual(rgb.shape, (24, 52, 3))  # as wide as the capsule is with nothing on
        self.assertTrue(all(abs(rgb[0, 0, i] - back[i]) < 0.01 for i in range(3)))  # its round end, the corner clear
        self.assertGreater(rgb.max(), 0.9)  # her eyes, white
        shut = island.logo(24, open_=0.0, back=back)
        self.assertLess(shut.mean(), rgb.mean())  # blinking, less of them lit
        rgba = island.logo(48)
        self.assertEqual(rgba.shape, (48, 104, 4))
        self.assertTrue((rgba[..., :3] <= rgba[..., 3:4] + 1e-6).all())  # premultiplied, as island_art's are


class MovedFromJev(unittest.TestCase):
    """Hey Jev's folders as Hey Harry's (winplatform.move_home), from app.py, and only with neither app open."""

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="heyharry-move-")
        self.addCleanup(shutil.rmtree, self.base, True)
        env = mock.patch.dict(os.environ, {"APPDATA": os.path.join(self.base, "Roaming"),
                                           "LOCALAPPDATA": os.path.join(self.base, "Local")})
        env.start()
        self.addCleanup(env.stop)
        for name, value in (("APPDATA_DIR", winplatform.APPDATA_DIR), ("LOG_DIR", winplatform.LOG_DIR),
                            ("MOVED", [])):
            p = mock.patch.object(winplatform, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.old = os.path.join(self.base, "Roaming", "Hey Jev")
        os.makedirs(os.path.join(self.old, "memories"))
        with open(os.path.join(self.old, "settings.json"), "w", encoding="utf-8") as f:
            f.write('{"mode": "wake"}')
        os.makedirs(os.path.join(self.base, "Local", "Hey Jev", "Logs"))
        with open(os.path.join(self.base, "Local", "Hey Jev", "Logs", "Hey Jev dictation.jsonl"), "w") as f:
            f.write("{}\n")

    def test_her_folders_move_as_she_starts(self):
        self.assertEqual(winplatform.home("APPDATA"), self.old)  # till then, where her data is
        with mock.patch.object(winplatform, "_running", return_value=False), mock.patch("builtins.print"):
            winplatform.move_home()
        new = os.path.join(self.base, "Roaming", "Hey Harry")
        self.assertTrue(os.path.isfile(os.path.join(new, "settings.json")))
        self.assertFalse(os.path.exists(self.old))
        self.assertEqual((winplatform.APPDATA_DIR, winplatform.home("APPDATA")), (new, new))
        self.assertIn(new, winplatform.MOVED)
        logs = os.path.join(self.base, "Local", "Hey Harry", "Logs")
        self.assertEqual(winplatform.LOG_DIR, logs)
        self.assertEqual(os.listdir(logs), ["Hey Harry dictation.jsonl"])  # your dictations, under the new name

    def test_never_while_either_app_is_open(self):
        with mock.patch.object(winplatform, "_running", return_value=True):
            winplatform.move_home()
        self.assertTrue(os.path.isdir(self.old))
        self.assertEqual(winplatform.home("APPDATA"), self.old)  # used where it is, nothing new made beside it
        self.assertFalse(os.path.exists(os.path.join(self.base, "Roaming", "Hey Harry")))

    def test_her_notes_say_her_new_name_once(self):
        new = os.path.join(self.base, "Roaming", "Hey Harry")
        with mock.patch.object(winplatform, "_running", return_value=False), mock.patch("builtins.print"):
            winplatform.move_home()
        user = os.path.join(new, "memories", "USER.md")
        with open(user, "w", encoding="utf-8") as f:
            f.write("Hari asked Jev to open Telegram.\n§\nJevon is his cousin.\n")
        with open(os.path.join(new, "SOUL.md"), "w", encoding="utf-8") as f:
            f.write("You are Jev, his assistant. Keep it short.\n")
        with mock.patch.object(identity, "_moved", []), mock.patch("builtins.print"):
            identity.moved_on()
            identity.moved_on()  # once only
        with open(user, encoding="utf-8") as f:
            self.assertEqual(f.read(), "Hari asked Harry to open Telegram.\n§\nJevon is his cousin.\n")
        with open(user + ".before-harry", encoding="utf-8") as f:
            self.assertIn("asked Jev", f.read())  # as it was, kept beside it
        with open(os.path.join(new, "SOUL.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "You are Harry, his assistant. Keep it short.\n")


class Keys(unittest.TestCase):
    def test_a_key_hey_jev_saved_is_found_and_kept_under_hey_harry(self):
        vault = {("Hey Jev", "FISH_AUDIO_API_KEY"): "fish-key"}
        with mock.patch.object(secrets_store.keyring, "get_password", side_effect=lambda s, n: vault.get((s, n))), \
                mock.patch.object(secrets_store.keyring, "set_password",
                                  side_effect=lambda s, n, v: vault.__setitem__((s, n), v)):
            self.assertEqual(secrets_store.vault_value("FISH_AUDIO_API_KEY"), "fish-key")
            self.assertIsNone(secrets_store.vault_value("KILO_API_KEY"))
        self.assertEqual(vault[("Hey Harry", "FISH_AUDIO_API_KEY")], "fish-key")
        self.assertEqual(vault[("Hey Jev", "FISH_AUDIO_API_KEY")], "fish-key")  # the old one left as it was


if __name__ == "__main__":
    unittest.main()
