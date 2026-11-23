"""The chat and her voice as one assistant (22 November 2026, the owner: "chat and voice the same access ... when I click
that voice it connects both chat and voice"): the chat's mic button, which raised an IndexError in the controls loop
(its ("mic",) met the branch for the Settings mic picker's ("mic", device) first), and what a typed turn does with her
voice. Runs on the listening tests' fakes: no mic, no models, no speakers."""
import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.support import siri

import chat
from tests.test_listening import Case


class TheMicButton(Case):
    """("mic",), from the chat's mic: a click to start listening, a second click to stop and take what you said."""

    def run_with(self, commands):
        said = []
        with mock.patch.object(siri, "emit", lambda notify, state, detail="": said.append((state, detail))):
            a = self.assistant(commands=commands)
        return a, said

    def test_a_click_starts_listening_and_says_how_to_finish(self):
        a, said = self.run_with([("mic",)])
        self.assertTrue(a.rec.on)
        self.assertIn(("Listening", "Click the mic again when you\u2019re done"), said)
        self.assertNotIn("[mic failed", a.out.getvalue())  # it was an IndexError, caught and shown as "didn't start"
        self.assertFalse([s for s in said if s[0] == "Something went wrong"])

    def test_a_second_click_stops_it_and_what_was_said_is_a_turn(self):
        a, said = self.run_with([("mic",), ("mic",)])
        self.assertFalse(a.rec.on)
        self.assertNotIn("[mic failed", a.out.getvalue())

    def test_the_settings_picker_still_changes_the_mic(self):
        """("mic", device), what Settings sends, is a different thing: it opens that device, it doesn't listen."""
        opened = []
        with mock.patch.object(siri.Recorder, "set_device", lambda rec, mic: opened.append(mic)):
            a, said = self.run_with([("mic", "USB mic")])
        self.assertEqual(opened, ["USB mic"])
        self.assertFalse(a.rec.on)


class ATypedTurnsVoice(unittest.TestCase):
    """What's typed in the chat is answered in words only, unless the owner turns on Speak answers (chat_speaks): then
    it's a turn like any typed to her, her answer said out loud as well as shown."""

    def test_the_chats_speaker_switch_picks_the_command(self):
        for speaks, command in ((False, "chat"), (True, "typed")):
            with self.subTest(speaks=speaks):
                self.assertEqual(chat.command_for(speaks), command)

    def test_the_default_keeps_the_chat_quiet(self):
        """The owner's own words, "when I chat, the voice assistant interrupts": nothing changes till it's turned on."""
        self.assertIs(siri.settings.DEFAULTS["chat_speaks"], False)

    def box(self, speaks=False, var=None):
        """chat.Box's speaker, on stand-ins: no Tk."""
        saved = []
        ui = SimpleNamespace(settings=SimpleNamespace(put=lambda k, v: saved.append((k, v))),
                             ACCENT="#5090f7", TEXT="#1c1e21", MUTED="#5d646f")
        box = SimpleNamespace(ui=ui, canvas=mock.Mock(), speaker=3, speaks=speaks, app=SimpleNamespace(chat_speaks_var=var),
                              speak_var=mock.Mock(**{"get.return_value": speaks}))
        return box, saved

    def test_the_speaker_is_kept_and_drawn_as_it_is(self):
        box, saved = self.box()
        chat.Box.speak(box, True)
        self.assertEqual((box.speaks, saved), (True, [("chat_speaks", True)]))
        # since 22 November 2026 the switch is a tick in the box's + menu (the owner's composer: a + at the left, the
        # waveform and Send at the right), not a speaker drawn in the box: the tick follows it
        box.speak_var.set.assert_called_with(True)
        box.speak_var.get.return_value = True
        chat.Box.speak(box, False)
        box.speak_var.set.assert_called_with(False)
        self.assertEqual(saved[-1], ("chat_speaks", False))

    def test_the_speaker_and_settings_checkbox_are_one_switch(self):
        var = mock.Mock(**{"get.return_value": False})
        box, _ = self.box(var=var)
        chat.Box.speak(box, True)
        var.set.assert_called_once_with(True)
        chat.Box.speak(self.box(var=mock.Mock(**{"get.return_value": True}))[0], True)  # already agreeing: left alone


class WhileSheStartsUp(unittest.TestCase):
    """22 November 2026, the owner: lines "come one by one, very late". Her controls loop begins only once her speech models
    are loaded, so what's typed while the header says Starting waits, then is answered one after another. It now says so."""

    def waiting(self, thread, controls=None, up=False):
        app = SimpleNamespace(controls=controls or object())
        old = siri.CONTROLS[0]
        siri.CONTROLS[0] = app.controls if up else None
        self.addCleanup(siri.CONTROLS.__setitem__, 0, old)
        return chat.starting_why(app, thread)

    def test_the_header_saying_starting_is_what_she_is_still_doing(self):
        t = chat.Thread()
        t.event("Starting", "Loading speech models\u2026")
        self.assertEqual(self.waiting(t), "Loading speech models\u2026")
        t.event("Ready", "Hold right Alt")
        self.assertEqual(self.waiting(t), "")  # her first word that she's up

    def test_a_line_typed_meanwhile_says_why_it_waits_once(self):
        t = chat.Thread()
        t.event("Starting", "Loading speech models\u2026")
        why = self.waiting(t)
        self.assertTrue(t.waiting(why))
        self.assertIn("still starting up (loading speech models)", t.items[-1]["text"])
        self.assertEqual(t.items[-1]["kind"], "note")
        t.you("open notepad")
        self.assertFalse(t.waiting(why))  # more messages before she's answered: under the same line, not a second
        t.you("and the weather")
        self.assertEqual(len([i for i in t.items if i["kind"] == "note"]), 1)

    def test_with_nothing_more_to_say_it_doesnt_say_starting_up_twice(self):
        t = chat.Thread()
        t.waiting("starting up")
        self.assertEqual(t.items[-1]["text"], "She's still starting up, so this waits. She'll answer as soon as she's ready.")

    def test_missing_keys_are_said_as_keys(self):
        t = chat.Thread()
        t.event("Starting", "Add your API keys to begin")
        t.waiting(self.waiting(t))
        self.assertIn("Keys tab", t.items[-1]["text"])

    def test_once_her_controls_loop_is_up_nothing_is_said_whatever_the_header_says(self):
        t = chat.Thread()
        t.event("Starting", "Loading voice ID\u2026")  # a voice that loads later, while she answers
        self.assertEqual(self.waiting(t, up=True), "")
        self.assertFalse(t.waiting(""))
        self.assertEqual(t.items, [])

    def test_a_new_answer_starts_the_wait_afresh(self):
        t = chat.Thread()
        why = "Loading speech models\u2026"
        t.waiting(why)
        t.her("Hello.")
        self.assertTrue(t.waiting(why))  # after an answer, a wait again is worth another line


if __name__ == "__main__":
    unittest.main()
