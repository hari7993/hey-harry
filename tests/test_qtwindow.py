"""Her window in Qt (qtwindow, qtchat, qtpages, qtsettings, qtkit), built offscreen: nothing is drawn on the screen,
nothing of hers is started, and her island's side is a stand-in that does what it's asked at once."""
import json
import os
import unittest
from unittest import mock

from tests.support import TRIPPED  # noqa: F401

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication  # noqa: E402

import assistant_ui  # noqa: E402
import qtkit  # noqa: E402
import settings  # noqa: E402

APP = QApplication.instance() or QApplication([])
qtkit.load_type()


def window(**kw):
    """A window of hers, offscreen, without her assistant, animations off."""
    import qtwindow
    with mock.patch.object(assistant_ui, "missing_secrets", return_value=[]):
        w = qtwindow.Window(kw.get("tk"), start=False)
    w.resize(1240, 800)
    return w


class FakeBubble:
    visible = False

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append((name, a))


class FakeTk:
    """Her island's side, done at once on this thread."""

    def __init__(self):
        self.bubble, self.edges, self.dock = FakeBubble(), None, None

    def call(self, fn):
        fn()

    def close(self):
        pass


class Base(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(qtkit, "animations_on", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        # a new chat moves siri's follow-up cut-off (CHAT_FROM) and its files: here, never for the tests after
        import sys
        siri = sys.modules.get("siri")
        for name, value in (("CHAT_FROM", [0.0]), ("CHAT_FILES", {"paths": [], "at": 0.0})):
            if siri is not None and hasattr(siri, name):
                kept = mock.patch.object(siri, name, value)
                kept.start()
                self.addCleanup(kept.stop)
        self.w = window(tk=getattr(self, "tk", None))
        self.addCleanup(self.close)

    def close(self):
        self.w.quitting = True
        self.w.close()
        self.w.deleteLater()

    def drain(self):
        APP.processEvents()


class TheWindow(Base):
    def test_every_tab_has_a_page_and_a_row(self):
        for key, _ in assistant_ui.TABS:
            self.assertIn(key, self.w.pages)
            self.assertIn(key, self.w.side.rows)

    def test_selecting_a_tab_shows_its_page_and_lights_its_row(self):
        self.w.select("todo")
        self.assertIs(self.w.stack.currentWidget(), self.w.pages["todo"])
        self.assertTrue(self.w.side.rows["todo"].on)
        self.assertFalse(self.w.side.rows["home"].on)
        self.assertEqual(self.w.top.head.words, "To-do")

    def test_the_chat_says_expand_frames_at_the_top(self):
        self.w.select("home")
        self.assertTrue(self.w.top.head.words.startswith("Expand frames"))

    def test_her_state_at_the_top_breathes_while_she_is_busy(self):
        self.w.set_status("Thinking", "what's on my calendar")
        self.assertEqual(self.w.top.status.text_, "Thinking")
        self.assertTrue(self.w.top.status.timer.isActive())
        self.w.set_status("Ready", "")
        self.assertFalse(self.w.top.status.timer.isActive())

    def test_what_she_is_at_shows_only_while_she_starts(self):
        self.w.set_status("Starting", "Loading speech models")
        self.assertIn("Loading", self.w.top.status.detail)
        self.w.set_status("Listening", "Go ahead")
        self.assertEqual(self.w.top.status.detail, "")

    def test_full_access_pill_while_it_is_on_and_a_click_turns_it_off(self):
        settings.put("full_access", True)
        self.addCleanup(settings.put, "full_access", False)
        self.w.show_full_badge()
        self.assertFalse(self.w.top.full.isHidden())
        self.w.top.full.click()
        self.assertFalse(settings.get("full_access"))
        self.assertTrue(self.w.top.full.isHidden())

    def test_the_sidebar_goes_away_and_comes_back_and_is_kept(self):
        self.addCleanup(settings.put, "sidebar_open", True)
        self.w.toggle_sidebar(False)
        self.assertFalse(settings.get("sidebar_open"))
        self.assertTrue(self.w.side.isHidden())
        self.assertFalse(self.w.top.pane.isHidden())
        self.w.toggle_sidebar(True)
        self.assertFalse(self.w.side.isHidden())
        self.assertTrue(self.w.top.pane.isHidden())

    def test_quick_actions_go_to_tabs_and_start_a_new_chat(self):
        names = [a[1] for a in self.w.quick_actions()]
        self.assertIn("Settings", names)
        self.assertIn("New chat", names)
        self.assertIn("Use the classic window", names)

    def test_the_palette_opens_and_its_first_find_is_done_with_enter(self):
        self.w.open_palette()
        self.assertIsNotNone(self.w.palette)
        self.w.palette.box.setText("keys")
        self.w.palette.run(0)
        self.assertIsNone(self.w.palette)
        self.assertEqual(self.w.current_tab, "keys")

    def test_closing_the_window_keeps_her_listening(self):
        self.w.quitting = False
        self.w.show()
        self.w.close()
        self.assertFalse(self.w.quitting)  # minimised, not gone


class HerIsland(Base):
    tk = FakeTk()

    def test_her_turn_shows_on_the_popup_when_it_is_on(self):
        self.tk.bubble.calls.clear()
        self.w.popup = True
        self.w.set_status("Thinking", "hi")
        self.assertIn(("show", ("thinking", "hi")), self.tk.bubble.calls)

    def test_ready_puts_the_popup_away(self):
        self.tk.bubble.calls.clear()
        self.w.set_status("Ready", "")
        self.assertIn(("hide", (900,)), self.tk.bubble.calls)

    def test_a_step_is_a_row_on_her_card(self):
        self.tk.bubble.calls.clear()
        self.w.set_status("Step", "live\tChecking calendar")
        self.assertIn(("step", ("live", "Checking calendar")), self.tk.bubble.calls)


class TheChat(Base):
    def turn(self, answer="You have 3 meetings today. The big one is the review at 2pm with Priya Shah, so bring "
                           "the numbers. Then a quick sync at 4:30 pm that needs nothing from you."):
        ev = self.w.chat.her_event
        ev("Asked", "what's on today?")
        ev("Thinking", "what's on today?")
        ev("Step", "live\tChecking calendar")
        ev("Step", "done\tChecking calendar")
        ev("Speaking", answer)
        ev("Ready", "")
        self.w.chat.draw()

    def views(self):
        return [v for _, v in self.w.chat.views]

    def test_a_turn_is_your_bubble_and_her_answer(self):
        import qtchat
        self.turn()
        view = self.views()[-1]
        self.assertEqual(len(view.findChildren(qtchat.YouBubble)), 1)
        self.assertEqual(len(view.findChildren(qtchat.AnswerText)), 1)

    def test_her_answer_ends_in_its_sources_as_pills(self):
        import qtchat
        self.turn()
        text = self.views()[-1].findChildren(qtchat.AnswerText)[0]
        self.assertEqual(text.document().toPlainText().count("\ufffc"), 1)  # Calendar, as an object in the words

    def test_the_facts_in_her_answer_are_in_her_semibold(self):
        import qtchat
        self.turn()
        doc = self.views()[-1].findChildren(qtchat.AnswerText)[0].document()
        bold = []
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.charFormat().font().weight() >= 600:
                    bold.append(frag.text())
                it += 1
            block = block.next()
        self.assertIn("2pm", bold)

    def test_a_longer_answer_is_a_sentence_a_line(self):
        import qtchat
        self.turn()
        doc = self.views()[-1].findChildren(qtchat.AnswerText)[0].document()
        self.assertGreaterEqual(doc.blockCount(), 2)

    def test_her_steps_wait_under_thought_for_till_opened(self):
        import qtchat
        self.turn()
        view = self.views()[-1]
        self.assertEqual(view.findChildren(qtchat.StepChip), [])
        rows = view.findChildren(qtchat.TookRow)
        self.assertEqual(len(rows), 1)
        rows[0].click()
        self.w.chat.draw()
        self.assertEqual(len(self.views()[-1].findChildren(qtchat.StepChip)), 1)

    def test_steps_before_an_answer_show_as_chips(self):
        import qtchat
        ev = self.w.chat.her_event
        ev("Asked", "open notepad")
        ev("Step", "live\tOpening Notepad")
        self.w.chat.draw()
        self.assertEqual(len(self.views()[-1].findChildren(qtchat.StepChip)), 1)
        self.assertFalse(self.w.chat.live.isHidden() and bool(self.w.chat.thread.status))

    def test_only_a_changed_turn_is_built_again(self):
        self.turn()
        first = self.views()[0]
        self.w.chat.her_event("Asked", "and tomorrow?")
        self.w.chat.draw()
        self.assertIs(self.views()[0], first)
        self.assertEqual(len(self.views()), 2)

    def test_typing_and_sending_puts_it_in_her_controls(self):
        page = self.w.chat
        page.box.put("hello there")
        page.send()
        self.assertEqual(self.w.controls.get_nowait(), ("chat", "hello there"))
        yours = [i for i in page.thread.items if i["kind"] == "you"]
        self.assertEqual(yours[-1]["text"], "hello there")  # and, while she starts, a line saying it waits
        self.assertEqual(page.box.get(), "")

    def test_a_slash_finds_her_quick_actions_and_enter_goes_there(self):
        page = self.w.chat
        page.box.put("/keys")
        self.assertTrue(page.found_now)
        page.enter()
        self.assertEqual(self.w.current_tab, "keys")

    def test_a_suggestion_on_the_empty_page_sends_itself(self):
        page = self.w.chat
        page.hero.chips[0].click()
        self.assertEqual(self.w.controls.get_nowait()[1], page.hero.chips[0].text_)

    def test_a_new_chat_empties_the_thread_and_the_last_stays_listed(self):
        self.turn()
        was = self.w.chat.chats.current
        self.w.new_chat()
        self.assertEqual(self.w.chat.thread.items, [])
        self.assertIn(was, [cid for cid, _, _ in self.w.chat.listed()])

    def test_your_chats_are_rows_under_chat(self):
        self.turn()
        self.w.side.lay_chats()
        shown = [r for r in self.w.side.chat_rows if not r.isHidden()]
        self.assertTrue(shown)
        self.assertEqual(shown[0].key, self.w.chat.chats.current)

    def test_a_look_up_is_a_frame_after_its_turn(self):
        self.w.chat.her_event("Asked", "search acme")
        self.w.chat.her_event("Context", json.dumps({"label": "Searching the web: acme", "do": "web", "found": {
            "web": "acme", "results": {"wikipedia": {"title": "Acme Corporation",
                                                     "extract": "Acme Corporation makes scheduling software."}}}}))
        self.w.chat.draw()
        self.assertEqual(self.w.frames_n, 1)
        self.assertIsNotNone(self.w.chat.frames.parentWidget())

    def test_the_box_takes_files_and_gives_them_with_the_line(self):
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "notes.txt")
        with open(path, "w") as f:
            f.write("hi")
        box = self.w.chat.box
        self.assertTrue(box.attach([path]))
        box.put("read this")
        self.w.chat.send()
        self.assertEqual(self.w.controls.get_nowait(), ("chat", "read this", [os.path.normpath(path)]))
        self.assertEqual(box.files, [])

    def test_dictation_asks_her_for_the_mic_and_writes_what_was_said(self):
        box = self.w.chat.box
        box.voice_start()
        self.assertEqual(self.w.controls.get_nowait(), ("box voice", "start"))
        box.voice_end("done")
        self.assertEqual(self.w.controls.get_nowait(), ("box voice", "done"))
        self.w.chat.her_event("Box words", "remind me at five")
        self.assertEqual(box.get(), "remind me at five")
        self.assertIsNone(box.voice)

    def test_the_ring_travels_while_she_is_busy(self):
        box = self.w.chat.box
        self.w.chat.her_event("Thinking", "x")
        self.assertEqual(box.ring, "busy")
        self.w.chat.her_event("Ready", "")
        self.assertNotEqual(box.ring, "busy")


class ThePages(Base):
    def test_a_to_do_added_is_in_its_list(self):
        page = self.w.pages["todo"]
        page.new.setText("buy milk")
        page.add()
        self.assertEqual(page.table.rowCount(), 1)
        self.assertEqual(page.table.item(0, 0).text().lower(), "buy milk")

    def test_settings_parts_are_along_its_top_for_quick_actions(self):
        names = [n for n, _ in self.w.pages["settings"].parts()]
        self.assertEqual(names[:3], ["Safety", "Her", "Hearing you"])

    def test_pairing_without_a_bot_token_says_to_add_it(self):
        page = self.w.pages["settings"]
        with mock.patch.object(assistant_ui, "get_secret", return_value=""):
            page.pair_phone()
        self.assertIn("Keys", page.phone_state.text())

    def test_a_part_folds_and_is_kept_folded(self):
        part = self.w.pages["stats"].parts_[0][1]
        was = part.shut
        part.fold()
        self.assertNotEqual(part.shut, was)
        self.assertEqual(settings.get("parts_folded")[part.title], part.shut)
        part.fold()

    def test_a_page_not_moved_over_is_a_way_to_the_classic_window(self):
        import qtpages
        page = qtpages.Soon(self.w, "priv")
        self.assertEqual(page.head[0], "Privacy")


class Choosing(unittest.TestCase):
    def test_the_classic_window_is_what_she_opens_in_by_default(self):
        self.assertEqual(settings.DEFAULTS["window"], "tk")

    def test_starting_again_is_her_keepers_own_code(self):
        import selfwork
        self.assertEqual(assistant_ui.RESTART, selfwork.RESTART)

    def test_the_collector_runs_on_the_windows_thread_alone(self):
        import gc
        was = gc.isenabled()
        self.addCleanup(gc.enable if was else gc.disable)
        timers = []
        with mock.patch.object(gc, "collect") as collect, mock.patch.object(gc, "get_count",
                                                                             return_value=(99999, 0, 0)):
            assistant_ui.gc_here(lambda ms, fn: timers.append((ms, fn)))
            self.assertFalse(gc.isenabled())  # never by itself, on whatever thread allocates
            timers[0][1]()  # a second later, on the window's thread
            collect.assert_called_with(1)
        self.assertEqual([ms for ms, _ in timers], [1000, 1000])  # and again a second after that

    def test_with_window_qt_her_qt_window_runs(self):
        import qtwindow
        settings.put("window", "qt")
        self.addCleanup(settings.put, "window", "tk")
        with mock.patch.object(assistant_ui, "_native_faults"), \
                mock.patch.object(assistant_ui.win, "prepare_gui"), \
                mock.patch.object(assistant_ui.win, "single_instance", return_value=True), \
                mock.patch.object(assistant_ui.win, "move_start_entry"), \
                mock.patch.object(assistant_ui.identity, "moved_on"), \
                mock.patch.object(qtwindow, "run") as run, \
                mock.patch.object(assistant_ui.tk, "Tk") as tk:
            assistant_ui.run_app()
        run.assert_called_once()
        tk.assert_not_called()

    def test_a_qt_window_that_will_not_start_leaves_her_the_classic_one(self):
        import qtwindow
        settings.put("window", "qt")
        self.addCleanup(settings.put, "window", "tk")
        with mock.patch.object(assistant_ui, "_native_faults"), \
                mock.patch.object(assistant_ui.win, "prepare_gui"), \
                mock.patch.object(assistant_ui.win, "single_instance", return_value=True), \
                mock.patch.object(assistant_ui.win, "move_start_entry"), \
                mock.patch.object(assistant_ui.identity, "moved_on"), \
                mock.patch.object(qtwindow, "run", side_effect=RuntimeError("it wouldn't build")), \
                mock.patch.object(assistant_ui.tk, "Tk") as tk, \
                mock.patch.object(assistant_ui, "AssistantWindow") as classic, \
                mock.patch.object(assistant_ui, "gc_here") as collector, \
                mock.patch.object(assistant_ui.os, "_exit"), \
                mock.patch("traceback.print_exc"):
            assistant_ui.run_app()
        tk.assert_called_once()
        classic.assert_called_once()
        collector.assert_called_once()  # the classic window's thread collects too


if __name__ == "__main__":
    unittest.main()
