"""Her window's first page, a chat (chat.py, 22 November 2026, the owner, after Hedwig's): the thread her window's
events make, your words once a turn and her steps ticked off; what a slash finds; what stays down its side; and the
window's own tabs with the chat first. Nothing here opens her window."""
import json
import os
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.support import siri  # noqa: F401  first: temp APPDATA and the tripwires, before anything of hers

import assistant_ui
import chat


def kinds(thread):
    return [(i["kind"], i["text"]) + ((i["state"],) if i["kind"] == "step" else ()) for i in thread.items]


class TheThread(unittest.TestCase):
    def test_a_typed_turn_is_your_words_once_then_her_answer(self):
        t = chat.Thread()
        self.assertTrue(t.you("open Notepad"))  # in the thread as it's sent
        for state, detail in (("Asked", "open Notepad"), ("Thinking", "open Notepad"), ("Step", "live\tOpening Notepad"),
                              ("Step", "done\tOpening Notepad"), ("Speaking", "It's open."), ("Ready", None)):
            t.event(state, detail)
        self.assertEqual(kinds(t), [("you", "open Notepad"), ("step", "Opening Notepad", "done"),
                                    ("her", "It's open.")])
        self.assertEqual((t.status, t.open), ("", False))

    def test_a_spoken_turn_is_there_too_with_her_name_or_without(self):
        t = chat.Thread()
        t.event("Listening", "Go ahead")
        self.assertEqual((t.items, t.status), ([], chat.WORKING["Listening"]))
        t.event("Heard", "Harry, what's the time?")
        t.event("Thinking", "what's the time?")  # the same turn, as she thinks about it: not said twice
        self.assertEqual(t.status, chat.WORKING["Thinking"])
        t.event("Speaking", "It's ten past four.")
        t.event("Ready", None)
        self.assertEqual(kinds(t), [("you", "Harry, what's the time?"), ("her", "It's ten past four.")])

    def test_the_same_words_asked_again_later_are_a_new_turn(self):
        t = chat.Thread()
        for _ in range(2):
            t.event("Asked", "what's the time?")
            t.event("Speaking", "It's ten past four.")
            t.event("Ready", None)
        self.assertEqual([k for k, _ in kinds(t)], ["you", "her", "you", "her"])

    def test_a_step_that_fails_says_so_and_her_line_isnt_doubled(self):
        t = chat.Thread()
        t.event("Asked", "turn off wifi")
        t.event("Step", "live\tTurning Wi-Fi off")
        t.event("Step", "live\tTurning Wi-Fi off")
        t.event("Step", "failed\tTurning Wi-Fi off")
        t.event("Speaking", "I couldn't turn Wi-Fi off.")
        t.event("Speaking", "I couldn't turn Wi-Fi off.")
        self.assertEqual(kinds(t), [("you", "turn off wifi"), ("step", "Turning Wi-Fi off", "failed"),
                                    ("her", "I couldn't turn Wi-Fi off.")])
        self.assertFalse(t.step("gone", "Anything"))  # only live, done and failed are steps

    def test_why_she_let_it_go_is_a_note_and_what_she_learned(self):
        t = chat.Thread()
        t.event("Heard", "open that bag")
        t.event("Ready", "That didn't sound like it was for me")
        t.event("Learned", "memory\tYou like lo-fi")
        t.event("Something went wrong", "No microphone")
        self.assertEqual(kinds(t)[1:], [("note", "That didn't sound like it was for me"), ("note", "You like lo-fi"),
                                        ("note", "No microphone")])
        self.assertEqual(t.items[-1]["state"], "failed")
        t.event("Ready", "Hello again")  # nothing of yours waiting: just her window's news, not the thread's
        self.assertEqual(len(t.items), 4)

    def test_how_long_she_thought_is_kept_with_her_first_words(self):
        t = chat.Thread()
        t.event("Asked", "what's the capital of Japan?")
        t.event("Thinking", "what's the capital of Japan?")
        t.thinking -= 2.2  # as if she'd thought for two seconds
        t.event("Speaking", "Tokyo.")
        t.event("Speaking", "It's also its biggest city.")
        self.assertEqual([i.get("took") for i in t.items], [None, 2, None])  # on her first line of the turn only
        t.event("Ready", None)
        t.event("Speaking", "Your timer's done.")  # nothing asked, so nothing thought over
        self.assertIsNone(t.items[-1].get("took"))

    def test_her_answer_typed_out_a_few_words_at_a_time(self):
        self.assertEqual([chat.typed_out("Three things to do today.", n) for n in (0, 2, 9)],
                         ["", "Three things", "Three things to do today."])
        self.assertTrue(all(0 <= chat.shimmer(i / 7) <= 0.6 for i in range(30)))

    def test_her_answer_told_again_as_it_grows_is_one_line(self):
        """22 November 2026: "Quite a lot, Hari..." shown twice, once as far as it had got and then whole."""
        t = chat.Thread()
        t.event("Asked", "what can you do?")
        t.event("Speaking", "Quite a lot, Hari.")
        t.event("Speaking", "Quite a lot, Hari. I open apps and sites.")
        t.event("Speaking", "I open apps and sites.")  # a sentence already there
        self.assertEqual(kinds(t), [("you", "what can you do?"), ("her", "Quite a lot, Hari. I open apps and sites.")])
        t.event("Ready", None)
        t.event("Asked", "and?")
        t.event("Speaking", "Quite a lot, Hari.")  # a new turn's answer, though it's said before
        self.assertEqual([k for k, _ in kinds(t)], ["you", "her", "you", "her"])

    def test_a_turn_she_started_herself_is_her_words_alone(self):
        """Her heads-ups are kept in history as "(heads-up)": shown as a bubble of yours till 22 November 2026."""
        t = chat.Thread()
        t.earlier([(time.time(), "(heads-up)", json.dumps({"steps": [], "say": "Sunday morning, still here?"}))])
        self.assertEqual(kinds(t), [("her", "Sunday morning, still here?")])
        self.assertEqual(t.asked(), [])

    def test_she_speaks_up_on_her_own(self):
        t = chat.Thread()
        t.event("Speaking", "Your timer's done.")
        self.assertEqual(kinds(t), [("her", "Your timer's done.")])

    def test_only_what_changes_whats_shown_counts(self):
        t = chat.Thread()
        self.assertTrue(t.event("Thinking", "hello"))
        self.assertFalse(t.event("Thinking", "hello"))
        self.assertFalse(t.event("Mood", "hearts"))
        self.assertTrue(t.event("Ready", None))  # she's no longer thinking

    def test_it_keeps_the_last_two_hundred_lines(self):
        t = chat.Thread()
        for i in range(chat.MOST + 30):
            t.her(f"line {i}")
        self.assertEqual((len(t.items), t.items[-1]["text"]), (chat.MOST, f"line {chat.MOST + 29}"))

    def test_the_turns_from_before_the_window_opened_and_what_you_last_asked(self):
        t, now = chat.Thread(), time.time()
        t.earlier([(now - 7200, "open Notepad", json.dumps({"steps": [], "say": "It's open."})),
                   (now - 600, "what's the time?", "not json"), (now - 300, "Open notepad!", None)])
        self.assertEqual([k for k, _ in kinds(t)], ["you", "her", "you", "you"])
        self.assertFalse(t.open)
        asked = t.asked(5)
        self.assertEqual([text for text, _ in asked], ["Open notepad!", "what's the time?"])  # newest first, once each
        self.assertAlmostEqual(asked[0][1], now - 300, delta=1)
        self.assertEqual(len(t.asked(1)), 1)


class SmallThings(unittest.TestCase):
    def test_one_turns_words_told_twice(self):
        self.assertTrue(chat.same_turn("Harry, open Notepad.", "open notepad"))
        self.assertTrue(chat.same_turn("what's the time?", "What's the time"))
        self.assertFalse(chat.same_turn("open Notepad", "close Notepad"))
        self.assertFalse(chat.same_turn("", "open"))

    def test_how_long_ago_in_a_few_letters(self):
        self.assertEqual([chat.ago(s) for s in (-5, 40, 61, 3599, 3600, 7300, 86400 * 3 + 5)],
                         ["now", "now", "1m", "59m", "1h", "2h", "3d"])
        self.assertEqual([chat.clock(s) for s in (59.2, 600, 3725)], ["1:00", "10:00", "1:02:05"])

    def test_the_task_held_for_your_yes(self):
        rows = [{"id": 1, "status": "done", "description": "Old"}, {"id": 2, "status": "queued", "description": "Later"},
                {"id": 4, "status": "waiting_approval", "description": "Send Sam the invoice"}]
        self.assertEqual(chat.held(rows)["id"], 4)
        self.assertIsNone(chat.held(rows[:2]))


class AfterASlash(unittest.TestCase):
    ACTIONS = [("i", "Chat", "Go to", None), ("i", "Settings", "Go to", None), ("i", "Settings: Voice", "Setting", None),
               ("i", "Settings: Voice ID", "Setting", None), ("i", "Keys: Voice and hearing", "Section", None),
               ("i", "Memory", "Go to", None)]

    def names(self, query, **kw):
        return [a[1] for a in chat.find(self.ACTIONS, query, **kw)]

    def test_every_word_somewhere_in_its_name_and_one_that_starts_with_it_first(self):
        self.assertEqual(self.names("voice"), ["Settings: Voice", "Settings: Voice ID", "Keys: Voice and hearing"])
        self.assertEqual(self.names("settings"), ["Settings", "Settings: Voice", "Settings: Voice ID"])
        self.assertEqual(self.names("voice id"), ["Settings: Voice ID"])
        self.assertEqual(self.names("go to mem"), ["Memory"])
        self.assertEqual(self.names("nothing like it"), [])

    def test_a_slash_alone_is_the_first_few_of_them(self):
        self.assertEqual(self.names(""), [a[1] for a in self.ACTIONS[:chat.SHOWN]])
        self.assertEqual(len(self.names("", most=2)), 2)


class ThePage(unittest.TestCase):
    """chat.Page's own doings, on stand-ins: no Tk."""

    def page(self, typed=""):
        sent, went = [], []
        actions = [("i", "Settings: Voice", "Setting", lambda: went.append("voice")),
                   ("i", "Memory", "Go to", lambda: went.append("memory"))]
        page = SimpleNamespace(thread=chat.Thread(), box=SimpleNamespace(get=lambda: typed, clear=mock.Mock()),
                               app=SimpleNamespace(controls=SimpleNamespace(put=sent.append),
                                                   quick_actions=lambda: actions),
                               changed=mock.Mock(), actions=None, found_now=[], at=0, _fill=mock.Mock(),
                               found=mock.Mock(), status=mock.Mock())
        for name in ("send", "_find", "run", "_clear"):
            setattr(page, name, getattr(chat.Page, name).__get__(page))
        return page, sent, went

    def test_whats_typed_is_hers_and_in_the_thread_at_once(self):
        page, sent, went = self.page("  open   Notepad ")
        page.send()
        self.assertEqual((sent, went), ([("chat", "open Notepad")], []))
        self.assertEqual(kinds(page.thread), [("you", "open Notepad")])
        page.box.clear.assert_called()

    def test_after_a_slash_the_first_thing_found_is_gone_to_and_she_isnt_asked(self):
        page, sent, went = self.page("/voice")
        page.send()
        self.assertEqual((sent, went), ([], ["voice"]))
        self.assertEqual(page.thread.items, [])

    def test_words_handed_to_it_are_sent_or_find_their_page(self):
        page, sent, went = self.page()
        page.send("Brief me")
        page.send("/memory")
        self.assertEqual((sent, went), ([("chat", "Brief me")], ["memory"]))

    def test_nothing_typed_is_nothing_sent(self):
        page, sent, went = self.page("   ")
        page.send()
        self.assertEqual((sent, went, page.thread.items), ([], [], []))


class Smooth(unittest.TestCase):
    def pixels(self, *args):
        data = assistant_ui.smooth_ppm(*args)
        head, _, body = data.partition(b"255 ")
        return head, body

    def test_a_rounded_shape_with_soft_edges(self):
        head, body = self.pixels(20, 10, 5, "#000000", "#ffffff")
        self.assertEqual(head, b"P6 20 10 ")
        self.assertEqual(len(body), 20 * 10 * 3)
        at = lambda x, y: body[(y * 20 + x) * 3]  # noqa: E731
        self.assertEqual((at(10, 5), at(0, 0)), (0, 255))  # its middle filled, its corner the ground
        self.assertTrue(any(0 < v < 255 for v in body))  # and grey along the edge, not a jagged step

    def test_a_circle_and_odd_sizes(self):
        head, body = self.pixels(9.6, 9.6, 99, "#5090f7", "#eaeae8")  # a radius too big is a circle's
        self.assertEqual(head, b"P6 9 9 ")


class Gliding(unittest.TestCase):
    """The wheel eased out (assistant_ui.Glide), on a stand-in clock: no Tk."""

    def run_glide(self, *deltas):
        moved, frames = [], []
        glide = assistant_ui.Glide(moved.append, lambda ms, fn: frames.append(fn) or len(frames))
        for delta in deltas:
            glide.wheel(delta)
        while frames:
            frames.pop(0)()
        return moved

    def test_a_notch_goes_its_whole_way_quick_first_then_settling(self):
        moved = self.run_glide(-120)
        self.assertEqual(sum(moved), assistant_ui.Glide.NOTCH)
        self.assertGreater(moved[0], moved[-1])
        self.assertGreater(len(moved), 5)  # in steps, not one jump

    def test_up_goes_up_and_notches_add_up(self):
        self.assertEqual(sum(self.run_glide(120)), -assistant_ui.Glide.NOTCH)
        self.assertEqual(sum(self.run_glide(-120, -120, -120)), 3 * assistant_ui.Glide.NOTCH)


class ChatTurns(unittest.TestCase):
    """Typed in the chat, she answers in the chat and doesn't talk (siri.CHAT_TURN); otherwise she talks as before."""

    def test_a_chat_turns_lines_go_to_the_chat_not_out_loud(self):
        import contextvars
        shown = []
        with mock.patch.object(siri, "speak", lambda line: self.fail("said out loud")):
            contextvars.copy_context().run(lambda: (siri.CHAT_TURN.set(True),
                                                    siri.say("It's open.", lambda s, d: shown.append((s, d)))))
        self.assertEqual(shown, [("Speaking", "It's open.")])

    def test_any_other_turn_still_talks(self):
        said = []
        with mock.patch.object(siri, "speak", lambda line: said.append(line) or 0), \
                mock.patch.object(siri, "MIC", [None]):
            siri.say("It's open.", None)
        self.assertEqual(said, ["It's open."])


class TheWindow(unittest.TestCase):
    def test_the_chat_is_her_first_page_and_her_figures_have_a_tab_of_their_own(self):
        titles = dict(assistant_ui.TABS)
        self.assertEqual((assistant_ui.TABS[0], titles["stats"]), (("home", "Chat"), "Activity"))
        self.assertEqual(assistant_ui.NAV[0], (None, ("home", "todo", "tasks", "stats")))
        for key in ("home", "stats"):
            self.assertTrue(assistant_ui.ICONS[key] and assistant_ui.TAB_TINTS[key])

    def test_white_pages_no_dots_no_glass_and_a_sidebar_dark_or_light(self):
        dark = lambda colour: sum(int(colour[i:i + 2], 16) for i in (1, 3, 5)) < 3 * 128  # noqa: E731
        self.assertFalse(dark(assistant_ui.BG))
        self.assertFalse(assistant_ui.DOTTED or assistant_ui.GLASS)
        self.assertEqual(siri.settings.DEFAULTS["sidebar"], "dark")  # as Hedwig's is, the look the owner asked for
        for name, (ground, words, idle, on, group, pill, edge) in assistant_ui.SIDES.items():
            self.assertEqual(dark(ground), name == "dark", name)
            for colour in (words, idle, on):  # what's written on it reads against it
                self.assertNotEqual(dark(colour), dark(ground), (name, colour))

    def test_the_sidebar_switches_and_is_kept(self):
        self.addCleanup(siri.settings.put, "sidebar", None)
        self.addCleanup(assistant_ui.AssistantWindow.set_sidebar, SimpleNamespace(), "dark", False)
        canvas = mock.Mock()
        item = SimpleNamespace(item=7)
        app = SimpleNamespace(side=canvas, side_brand=1, nav_groups={"Setup": (2, 3)}, tab_buttons={"home": (4, 5)},
                              current_tab="home", _paint_tab=mock.Mock(), nav_bar=6, nav_ring=8, side_line=9,
                              timer_rows=[(item, item)], hint=item, leave=10, recent_head=11, recent_rows=[(12, 13)],
                              you_card=14, you_name=15, side_search=16, side_pane=20, nav_group_icons={"Setup": 17},
                              chat_bin=18, side_new=19, _lay_recent=mock.Mock(),
                              _slide_nav_bar=mock.Mock(), _lay_bottom=mock.Mock(),
                              _draw_logo=mock.Mock())
        assistant_ui.AssistantWindow.set_sidebar(app, "light")
        self.assertEqual((app.sidebar, siri.settings.get("sidebar")), ("light", "light"))
        self.assertEqual(assistant_ui.SIDE_BG, assistant_ui.SIDES["light"][0])
        canvas.configure.assert_called_with(bg=assistant_ui.SIDES["light"][0])
        app._paint_tab.assert_called_with("home", True)
        assistant_ui.AssistantWindow.set_sidebar(app, "something else", paint=False)
        self.assertEqual((app.sidebar, assistant_ui.SIDE_BG), ("dark", assistant_ui.SIDES["dark"][0]))
        self.assertEqual(siri.settings.get("sidebar"), "light")  # not kept: only drawn for, as when she starts

    def test_the_sidebar_as_hedwigs_first_tabs_top_level_the_rest_in_sections(self):
        self.assertTrue(assistant_ui.AssistantWindow._top_level("home"))
        self.assertFalse(assistant_ui.AssistantWindow._top_level("settings"))
        for name, _ in assistant_ui.NAV[1:]:
            self.assertTrue(assistant_ui.GROUP_ICONS.get(name), name)  # each section has its icon


class YourChats(unittest.TestCase):
    """Your chats kept as ChatGPT and Claude keep them (chat.Chats): new, opened again, deleted, and kept in a file."""

    def setUp(self):
        import tempfile
        self.path = os.path.join(tempfile.mkdtemp(), "chats.json")

    def lines(self, *words):
        return [{"kind": "you" if i % 2 == 0 else "her", "text": w, "state": "", "at": time.time() + i}
                for i, w in enumerate(words)]

    def test_none_yet_then_one_kept_and_read_back(self):
        chats = chat.Chats(self.path)
        self.assertFalse(chats.found)
        self.assertEqual((chats.lines(), chats.listed()), ([], []))
        chats.keep(self.lines("open Notepad", "It's open."))
        again = chat.Chats(self.path)
        self.assertTrue(again.found)
        self.assertEqual(again.current, chats.current)
        self.assertEqual([i["text"] for i in again.lines()], ["open Notepad", "It's open."])
        self.assertEqual([t for _, t, _ in again.listed()], ["open Notepad"])  # named by your first words

    def test_a_new_chat_leaves_the_last_in_the_list_and_isnt_listed_till_something_is_said(self):
        chats = chat.Chats(self.path)
        chats.keep(self.lines("first chat"))
        first = chats.current
        chats.start()
        self.assertNotEqual(chats.current, first)
        chats.keep([])
        self.assertEqual([c for c, _, _ in chats.listed()], [first])
        chats.keep(self.lines("second chat"))
        self.assertEqual([t for _, t, _ in chats.listed()], ["second chat", "first chat"])  # newest first

    def test_an_old_chat_opens_again_as_it_was(self):
        chats = chat.Chats(self.path)
        chats.keep(self.lines("first chat", "Hi."))
        first = chats.current
        chats.start()
        chats.keep(self.lines("second chat"))
        self.assertEqual([i["text"] for i in chats.open(first)], ["first chat", "Hi."])
        self.assertEqual(chat.Chats(self.path).current, first)
        self.assertIsNone(chats.open("no such chat"))

    def test_deleting_a_chat_and_the_open_one_leaves_a_new_chat_open(self):
        chats = chat.Chats(self.path)
        chats.keep(self.lines("first chat"))
        first = chats.current
        chats.start()
        chats.keep(self.lines("second chat"))
        self.assertFalse(chats.delete(first))
        self.assertEqual([t for _, t, _ in chat.Chats(self.path).listed()], ["second chat"])
        second = chats.current
        self.assertTrue(chats.delete(second))
        self.assertNotEqual(chats.current, second)
        self.assertEqual((chats.listed(), chats.lines()), ([], []))

    def test_only_the_newest_are_kept_and_a_broken_file_is_none(self):
        chats = chat.Chats(self.path)
        for i in range(chat.CHATS_KEPT + 5):
            chats.start()
            chats.keep([{"kind": "you", "text": f"chat {i}", "state": "", "at": 1000.0 + i}])
        self.assertEqual(len(chats.listed()), chat.CHATS_KEPT)
        self.assertEqual(chats.listed(2)[0][1], f"chat {chat.CHATS_KEPT + 4}")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{not json")
        broken = chat.Chats(self.path)
        self.assertEqual((broken.found, broken.listed()), (False, []))

    def test_a_chat_named_by_her_words_when_youve_said_nothing(self):
        self.assertEqual(chat.title([{"kind": "her", "text": "Your timer's done."}]), "Your timer's done.")
        self.assertEqual(chat.title([]), "New chat")

    def test_the_thread_made_another_chat_keeps_only_whole_lines(self):
        t = chat.Thread()
        t.event("Thinking", "open Notepad")
        t.reset([{"kind": "you", "text": "  hi   there ", "at": 5}, {"kind": "odd", "text": "x"}, "nonsense",
                 {"kind": "her", "text": ""}])
        self.assertEqual(kinds(t), [("you", "hi there")])
        self.assertEqual((t.items[0]["state"], t.items[0]["at"]), ("", 5.0))
        self.assertEqual((t.status, t.open, t.thinking), (chat.WORKING["Thinking"], False, None))  # she's still at it


class ChatsOnThePage(unittest.TestCase):
    """New chat, opening one and deleting one, on chat.Page with stand-ins: no Tk."""

    def page(self):
        import tempfile
        chats = chat.Chats(os.path.join(tempfile.mkdtemp(), "chats.json"))
        root = SimpleNamespace(after=lambda ms, fn: None, after_cancel=lambda job: None)
        page = SimpleNamespace(thread=chat.Thread(), chats=chats, save_job=None, reveal={}, shown_n=0, jump=False,
                               app=SimpleNamespace(root=root, _lay_recent=mock.Mock()), changed=mock.Mock(),
                               _clear=mock.Mock(), _focus=mock.Mock())
        for name in ("save", "_fresh", "_show", "new_chat", "open_chat", "delete_chat", "listed"):
            setattr(page, name, getattr(chat.Page, name).__get__(page))
        self.addCleanup(setattr, siri, "CHAT_FROM", list(siri.CHAT_FROM))
        return page

    def test_new_chat_keeps_this_one_and_empties_the_thread(self):
        page = self.page()
        page.thread.you("open Notepad")
        first = page.chats.current
        page.new_chat()
        self.assertEqual((page.thread.items, page.jump), ([], True))
        self.assertNotEqual(page.chats.current, first)
        self.assertEqual([c for c, _, _ in page.chats.listed()], [first])
        self.assertAlmostEqual(siri.CHAT_FROM[0], time.time(), delta=5)  # her follow-ups start again from here
        page.new_chat()  # pressed again on an empty one: still the one new chat
        self.assertEqual(len(page.chats.listed()), 1)

    def test_an_old_chat_opens_and_the_open_one_deleted_leaves_a_new_one(self):
        page = self.page()
        page.thread.you("first chat")
        first = page.chats.current
        page.new_chat()
        page.thread.you("second chat")
        page.open_chat(first)
        self.assertEqual(kinds(page.thread), [("you", "first chat")])
        self.assertEqual([t for _, t, _ in page.chats.listed()], ["second chat", "first chat"])
        page.delete_chat(first)
        self.assertEqual((page.thread.items, [t for _, t, _ in page.chats.listed()]), ([], ["second chat"]))

    def test_the_list_shows_a_new_chat_at_once_and_the_open_one_as_it_is_now(self):
        """22 November 2026, the owner: the pencil did nothing to be seen, and rows a second stale opened the wrong one."""
        page = self.page()
        page.thread.you("first chat")
        page.save()
        first = page.chats.current
        page.new_chat()
        self.assertEqual([(c == first, t) for c, t, _ in page.listed()], [(False, "New chat"), (True, "first chat")])
        page.thread.you("second chat")  # not kept yet: still listed, by its words
        self.assertEqual([t for _, t, _ in page.listed()], ["second chat", "first chat"])
        self.assertEqual(len(page.listed(1)), 1)

class FollowUpsInANewChat(unittest.TestCase):
    def test_turns_from_before_new_chat_arent_her_follow_ups(self):
        self.addCleanup(setattr, siri, "CHAT_FROM", list(siri.CHAT_FROM))
        now = time.time()
        turns = [(now - 600, "open Notepad", "{}"), (now - 10, "what's the time?", "{}")]
        siri.CHAT_FROM[0] = now - 60
        seen = []

        def blocks(text, recent):
            seen.append(recent)
            raise LookupError("far enough")
        with mock.patch.object(siri.history, "recent", lambda *a, **k: turns), \
                mock.patch.object(siri, "gated_blocks", blocks):
            with self.assertRaises(LookupError):
                siri._think("close it", "named")
        self.assertEqual([said for _, said, _ in seen[0]], ["what's the time?"])


class AttachedFiles(unittest.TestCase):
    """Files attached in the box (attach.py): they go with what's sent, show over your words, and New chat forgets
    them. On stand-ins: no Tk."""

    def setUp(self):
        import tempfile
        self.folder = tempfile.mkdtemp()
        self.paths = []
        for name in ("a.pdf", "b.png"):
            self.paths.append(os.path.join(self.folder, name))
            with open(self.paths[-1], "wb") as f:
                f.write(b"x")

    def test_sent_with_your_words_or_alone(self):
        sent = []
        box = SimpleNamespace(get=lambda: "what's this?", clear=mock.Mock(), files=list(self.paths))
        box.take = lambda: (list(box.files), box.files.clear())[0]
        page = SimpleNamespace(thread=chat.Thread(), box=box, app=SimpleNamespace(controls=SimpleNamespace(
            put=sent.append)), changed=mock.Mock(), _clear=mock.Mock(), found_now=[])
        chat.Page.send.__get__(page)()
        self.assertEqual(sent, [("chat", "what's this?", self.paths)])
        self.assertEqual((page.thread.items[0]["text"], page.thread.items[0]["files"]), ("what's this?", self.paths))
        self.assertEqual(box.files, [])
        box.get, box.files = (lambda: ""), [self.paths[1]]
        chat.Page.send.__get__(page)()
        self.assertEqual(sent[-1], ("chat", "", [self.paths[1]]))  # a file alone is sent too
        self.assertEqual(chat.title(page.thread.items[1:]), "b.png")  # a chat of only a file is named by it

    def test_the_box_takes_each_file_once_and_lets_one_go(self):
        box = SimpleNamespace(files=[], _focused=mock.Mock(), _resize=mock.Mock())
        for name in ("attach", "drop", "take"):
            setattr(box, name, getattr(chat.Box, name).__get__(box))
        self.assertTrue(box.attach(self.paths + [self.paths[0], os.path.join(self.folder, "gone.txt")]))
        self.assertEqual(box.files, self.paths)
        self.assertFalse(box.attach([self.paths[0]]))
        box.drop(0)
        self.assertEqual(box.files, [self.paths[1]])
        self.assertEqual((box.take(), box.files), ([self.paths[1]], []))

    def test_a_new_chat_forgets_the_files_attached_before(self):
        self.addCleanup(setattr, siri, "CHAT_FROM", list(siri.CHAT_FROM))
        siri.CHAT_FILES.update(paths=list(self.paths), at=time.time())
        chat.Page._fresh(SimpleNamespace())
        self.assertEqual(siri.CHAT_FILES["paths"], [])

class ScannableAnswers(unittest.TestCase):
    """Her answer laid out to scan, and the parts round it (22 November 2026): no Tk."""
    ANSWER = ("Your 2pm is the Juniper website review with Maya Chen. She wants to start with pricing, not the homepage. "
              "Their plan is $49 a seat, 20% off till Friday.")

    def test_the_facts_the_eye_lands_on(self):
        found = [self.ANSWER[a:z] for a, z in chat.anchors(self.ANSWER)]
        self.assertEqual(found, ["2pm", "Juniper", "Maya Chen", "$49", "20%", "Friday"])
        self.assertEqual(chat.anchors("I'll do it. Okay, done."), [])  # a sentence's first word isn't a name
        self.assertEqual([t[a:z] for t in ["Back at 10:30 am on 5th of Dec."] for a, z in chat.anchors(t)],
                         ["10:30 am", "5th of Dec"])

    def test_a_sentence_a_line_once_its_long(self):
        self.assertEqual(chat.lines_of("It's open."), ["It's open."])
        lines = chat.lines_of(self.ANSWER)
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[1].startswith("She wants"))
        self.assertEqual(chat.lines_of("Done. " + self.ANSWER)[0][:10], "Done. Your")  # a short one stays with the next

    def test_the_sources_a_turn_drew_on(self):
        steps = [{"text": "Checking calendar", "state": "done"}, {"text": "Searching the web: x", "state": "done"},
                 {"text": "Checking calendar", "state": "done"}, {"text": "Getting the news", "state": "failed"},
                 {"text": "Opening Notepad", "state": "done"}]
        self.assertEqual([name for name, _ in chat.sources(steps)], ["Calendar", "Web"])

    def test_the_thread_in_turns(self):
        items = [{"kind": k} for k in ("her", "you", "step", "step", "her", "her", "you", "step")]
        found, at = chat.turns(items)
        self.assertEqual([(t["steps"], t["first"], t["last"]) for t in found],
                         [([], 0, 0), ([2, 3], 4, 5), ([7], None, None)])
        self.assertIs(at[3], found[1])

    def test_the_shimmer_sweeps_across(self):
        early, late = chat.sweep(10, 0.2), chat.sweep(10, 1.2)
        self.assertEqual(len(early), 10)
        self.assertLess(early.index(max(early)), late.index(max(late)))  # left to right
        self.assertTrue(all(0.0 <= v <= 1.0 for v in early + late))

    def test_the_meeting_its_card_is_for(self):
        import datetime as dt
        now = dt.datetime(2026, 11, 22, 13, 0)
        events = [{"title": "Standup", "start": now - dt.timedelta(hours=2), "end": now - dt.timedelta(hours=1)},
                  {"title": "Lunch", "start": now + dt.timedelta(minutes=20), "end": now + dt.timedelta(hours=1)},
                  {"title": "Juniper website review", "start": now + dt.timedelta(hours=1),
                   "end": now + dt.timedelta(hours=2)},
                  {"title": "Holiday", "all_day": True, "start": now, "end": now}]
        self.assertEqual(chat.meeting_for(self.ANSWER, events, now)["title"], "Juniper website review")
        self.assertEqual(chat.meeting_for("What's next?", events, now)["title"], "Lunch")
        self.assertIsNone(chat.meeting_for("x", events[:1], now))
        self.assertTrue(chat.LINK.search("Room 4, https://meet.google.com/abc-defg-hij"))
        self.assertTrue(chat.LINK.search("zoom.us/j/123"))


class VoiceInTheBox(unittest.TestCase):
    """The box's mic, as ChatGPT's dictation: on stand-ins, no Tk."""

    def box(self, typed=""):
        asked = []
        state = {"text": typed}
        box = SimpleNamespace(voice=None, voice_at=0.0, files=[], mic_fn=asked.append, wave=[], timer=1, writing=2,
                              cancel_back=3, cancel_x=4, done_back=5, done_tick=6, _show_voice=mock.Mock(),
                              _wave_tick=mock.Mock(), canvas=mock.Mock(), entry=mock.Mock(),
                              get=lambda: state["text"], put=lambda text: state.update(text=text),
                              app=SimpleNamespace(animate=mock.Mock()), set_ring=mock.Mock())
        for name in ("voice_start", "voice_end", "voice_key", "voice_words"):
            setattr(box, name, getattr(chat.Box, name).__get__(box))
        box._show_voice.side_effect = lambda on: setattr(box, "voice", box.voice if on else None)
        return box, asked, state

    def test_spoken_then_written_after_whats_typed(self):
        box, asked, state = self.box("remind me")
        box.voice_start()
        self.assertEqual((box.voice, asked), ("rec", ["start"]))
        self.assertTrue(box.voice_key("done"))  # Enter, as the tick
        self.assertEqual((box.voice, asked), ("writing", ["start", "done"]))
        box.voice_words("  to call   Vamsi at five ")
        self.assertEqual((box.voice, state["text"]), (None, "remind me to call Vamsi at five"))

    def test_thrown_away_and_nothing_heard_leaves_the_box_as_it_was(self):
        box, asked, state = self.box("hi")
        box.voice_start()
        box.voice_end("cancel")
        self.assertEqual((box.voice, asked, state["text"]), (None, ["start", "cancel"], "hi"))
        self.assertFalse(box.voice_key("done"))  # not dictating: Enter sends as ever
        box.voice_start()
        box.voice_end("done")
        box.voice_words("")
        self.assertEqual((box.voice, state["text"]), (None, "hi"))

    def test_how_tall_a_bar_is_for_how_loud(self):
        self.assertEqual(chat.level_height(0.0), 0.0)
        self.assertEqual(chat.level_height(0.003), 0.0)  # a room's hush
        self.assertLess(chat.level_height(0.02), chat.level_height(0.06))
        self.assertEqual(chat.level_height(0.5), 1.0)

    def test_the_words_come_back_to_the_box_not_the_thread(self):
        page = SimpleNamespace(box=mock.Mock(), thread=chat.Thread(), changed=mock.Mock())
        chat.Page.event.__get__(page)("Box words", "call Vamsi")
        page.box.voice_words.assert_called_once_with("call Vamsi")
        self.assertEqual(page.thread.items, [])

    def test_the_mic_records_how_loud_each_block_is_for_the_waveform(self):
        import numpy as np
        import queue
        rec = siri.Recorder.__new__(siri.Recorder)
        rec._level, rec.on, rec.frames, rec.wake, rec.dictating = [0.0, 0], True, [], False, False
        rec._paused, rec._soft, rec.side, rec.blocks = False, False, None, queue.Queue()
        siri.BOX_LEVELS.clear()
        rec._cb(np.full((512, 1), 0.1, np.float32))
        self.assertAlmostEqual(siri.BOX_LEVELS[-1], 0.1, places=4)
        rec.on = False
        rec._cb(np.full((512, 1), 0.1, np.float32))
        self.assertEqual(len(siri.BOX_LEVELS), 1)  # only while it records

class TheWorkspace(unittest.TestCase):
    """The composer's look, the deliverables rail and the context canvas (22 November 2026): their parts with no Tk."""

    def pixel(self, ppm, w, x, y):
        body = ppm.partition(b"255 ")[2]
        return tuple(body[(y * w + x) * 3:(y * w + x) * 3 + 3])

    def test_the_composer_a_white_card_with_a_hairline_and_a_shadow_under_it(self):
        w, h = 120, 80
        ppm = chat.composer_ppm(w, h, (10, 6, 110, 62), 20, fill="#ffffff", line="#e5e7eb", back="#ffffff")
        self.assertEqual(ppm.partition(b"255 ")[0], b"P6 120 80 ")
        self.assertEqual(self.pixel(ppm, w, 60, 30), (255, 255, 255))  # inside: white
        self.assertEqual(self.pixel(ppm, w, 60, 6), (229, 231, 235))  # its top edge: the hairline
        self.assertLess(self.pixel(ppm, w, 60, 66)[0], 255)  # under it: a soft shadow
        self.assertGreaterEqual(min(self.pixel(ppm, w, 0, 0)), 253)  # far off it: the ground, or as near as makes none

    def test_your_bubble_has_one_small_corner_at_its_top_right(self):
        w, h = 60, 40
        ppm = chat.bubble_ppm(w, h, 16, 3, "#efefef", "#ffffff")
        self.assertEqual(self.pixel(ppm, w, 1, 1), (255, 255, 255))  # top left: round, the ground shows
        self.assertEqual(self.pixel(ppm, w, w - 2, 1), (239, 239, 239))  # top right: near square
        self.assertEqual(self.pixel(ppm, w, w - 2, h - 2), (255, 255, 255))  # bottom right: round

    def test_a_spring_settles_home_a_touch_past_it_first(self):
        self.assertEqual((chat.spring(0.0), chat.spring(1.0)), (0.0, 1.0))
        self.assertGreater(max(chat.spring(t / 50) for t in range(51)), 1.0)

    def test_what_a_look_up_found_as_lines_for_its_card(self):
        found = {"query": "juniper", "results": [{"title": "Juniper pricing", "snippet": "Team is $49 a seat.",
                                                 "url": "https://juniper.co/pricing"},
                                                {"title": "Juniper pricing", "snippet": "Team is $49 a seat."}]}
        self.assertEqual(chat.context_lines(found), ["Juniper pricing", "Team is $49 a seat.",
                                                     "Url: https://juniper.co/pricing"])  # each once
        self.assertEqual(chat.context_lines("line one" + chr(10) * 2 + "line two"), ["line one", "line two"])
        self.assertLessEqual(sum(map(len, chat.context_lines({"text": "word " * 900}, most=100))), 230)
        self.assertEqual(chat.app_of("Checking calendar")[0], "Calendar")
        self.assertEqual(chat.app_of("Doing a thing", "odd_step")[0], "Odd step")

    def test_the_message_waiting_for_your_yes_is_the_outbox_card(self):
        plan = {"steps": [{"do": "message", "app": "whatsapp", "contact": "Maya", "text": "See you at 2"}]}
        siri_now = SimpleNamespace(PENDING={"plan": plan, "until": time.time() + 60, "id": "q1"})
        self.assertEqual(chat.pending_message(siri_now),
                         {"id": "q1", "contact": "Maya", "app": "whatsapp", "text": "See you at 2"})
        siri_now.PENDING["until"] = time.time() - 1
        self.assertIsNone(chat.pending_message(siri_now))  # run out
        self.assertIsNone(chat.pending_message(SimpleNamespace(PENDING={"plan": {"steps": [{"do": "lock"}]},
                                                                         "until": time.time() + 60})))
        self.assertIsNone(chat.pending_message(None))

    def test_the_rail_newest_kind_first_and_what_you_crossed_out_stays_out(self):
        dock = SimpleNamespace(gone=set())
        items = chat.Dock.items(dock, {"id": 3, "description": "Send the invoice"},
                                {"id": "q1", "contact": "Maya", "text": "hi"}, [("a.md", "# A")], [("Tea", "3:05")])
        # and no timers card: the sidebar shows your timers on every tab, so here they'd be the same thing twice
        self.assertEqual([kind for _, kind, _ in items], ["draft", "task", "note"])
        dock.gone.add("task 3")
        self.assertEqual([kind for _, kind, _ in chat.Dock.items(dock, {"id": 3}, None, [], [])], [])

    def test_the_canvas_takes_each_look_up_and_a_new_turn_starts_it_over(self):
        bento = SimpleNamespace(found=[], big=None, turn=0, MOST=5, draw=mock.Mock(), _agenda=lambda: [])
        add = chat.Bento.add.__get__(bento)
        web = json.dumps({"do": "web", "label": "Searching the web: tea", "found": {"results": [{"title": "Tea"}]}})
        self.assertTrue(add(web, 1))
        self.assertTrue(add(web, 1))
        self.assertEqual([f[1] for f in bento.found], ["Web", "Web"])
        self.assertTrue(add(json.dumps({"do": "weather", "label": "Checking the weather", "found": "Sunny, 24"}), 2))
        self.assertEqual([f[1] for f in bento.found], ["Weather"])  # the last turn's went
        self.assertFalse(add("not json", 2))
        self.assertFalse(add(json.dumps({"do": "web", "label": "x", "found": {}}), 2))  # nothing to show

    def test_her_look_ups_reach_the_window_as_context(self):
        shown = []
        with mock.patch.object(siri, "NOTIFY", [lambda state, detail: shown.append((state, detail))]):
            siri.show_context({"do": "weather"}, {"weather": "Sunny"})
            siri.show_context({"do": "skill_view", "name": "x"}, {"skill": "..."})  # a skill read isn't shown
        self.assertEqual([state for state, _ in shown], ["Context"])
        self.assertEqual(json.loads(shown[0][1])["found"], {"weather": "Sunny"})

class EachAppAsItself(unittest.TestCase):
    """Frames drawn as the app or site they came from (22 November 2026, the owner: "use their original theme ...
    for all apps and websites"): no Tk."""

    def test_a_page_is_named_for_its_app_or_its_own_site(self):
        self.assertEqual(chat.site_app("https://mail.google.com/mail/u/0/#inbox"), "Gmail")
        self.assertEqual(chat.site_app("https://www.notion.so/juniper/Brief-0123"), "Notion")
        self.assertEqual(chat.site_app("juniper.notion.site/brief"), "Notion")
        self.assertEqual(chat.site_app("https://www.theverge.com/story"), "theverge.com")  # its host, if no app
        self.assertEqual(chat.host_of("https://www.Example.com/a/b"), "example.com")

    def test_a_window_is_named_for_the_app_its_title_names(self):
        self.assertEqual(chat.window_app("Inbox (3) - Gmail - Google Chrome"), "Gmail")
        self.assertEqual(chat.window_app("Pricing – Desktop – Figma"), "Figma")
        self.assertEqual(chat.window_app(""), "Screen")

    def test_a_sites_own_colour_as_it_declares_it(self):
        page = lambda theme: {"page": {"theme": theme}}  # noqa: E731
        self.assertEqual(chat.theme_of(page("#5200ff")), "#5200ff")
        self.assertEqual(chat.theme_of(page("#abc")), "#aabbcc")
        self.assertIsNone(chat.theme_of(page("red")))  # only colours written as #hex
        self.assertIsNone(chat.theme_of({}))
        import web
        reader = web._Reader()
        reader.feed('<html><head><meta name="theme-color" content="#5200FF"><meta property="og:site_name" '
                    'content="The Verge"><meta name="theme-color" content="#000000"></head><body></body></html>')
        self.assertEqual((reader.theme, reader.site), ("#5200ff", "The Verge"))  # the first it says

    def test_the_frames_name_each_page_and_keep_one_look_at_the_screen(self):
        bento = SimpleNamespace(found=[], big=None, turn=1, MOST=5, _agenda=lambda: [])
        add = chat.Bento.add.__get__(bento)
        for url, site in (("https://mail.google.com/x", ""), ("https://www.theverge.com/x", "The Verge"),
                          ("https://example.org/x", "")):
            add(json.dumps({"do": "read", "label": "Reading the page",
                            "found": {"read": url, "page": {"url": url, "site": site, "text": "Some words here"}}}), 1)
        self.assertEqual([f[1] for f in bento.found], ["Gmail", "The Verge", "example.org"])
        picture = chat.Bento.add_picture.__get__(bento)
        self.assertTrue(picture("rgb", "Inbox - Gmail - Google Chrome", 1))
        self.assertTrue(picture("rgb2", "Figma", 1))
        self.assertEqual([f[1] for f in bento.found if f[5] == "picture"], ["Figma"])  # the latest look alone
        self.assertFalse(picture(None, "x", 1))

    def test_the_frames_are_as_tall_as_their_rows(self):
        px = lambda n: n  # noqa: E731
        bento = SimpleNamespace(found=[("a",)] * 1, big=None, px=px, TOP=236, ROW=214, BIG=520)
        height = chat.Bento.height.__get__(bento)
        self.assertEqual(height(), 236)
        bento.found = [("a",), ("b",), ("c",)]
        self.assertEqual(height(), 236 + 214 + 2 + 2)  # the wide one, and the two under it in a row
        bento.found = [("a",), ("b",), ("c",), ("d",)]
        self.assertEqual(height(), 236 + 2 * (214 + 2) + 2)
        bento.big = "b"
        self.assertEqual(height(), 520)

    def test_her_answers_words_mark_what_it_is_about(self):
        page = SimpleNamespace(thread=chat.Thread())
        page.thread.her("The decision today: monthly pricing, annual pricing, or both.")
        self.assertTrue({"monthly", "annual", "pricing"} <= chat.Page.answer_words(page))

class TouchesOfLight(unittest.TestCase):
    """The empty page's greeting, its aurora and the composer's ring (chatfx): their pictures, no window."""

    def test_the_greeting_by_the_hour_and_your_name(self):
        import chatfx
        at = lambda hour: time.struct_time((2026, 11, 22, hour, 0, 0, 6, 326, 0))  # noqa: E731
        self.assertEqual(chatfx.greeting(at(9), "Hari"), "Good morning, Hari")
        self.assertEqual(chatfx.greeting(at(14), "Hari"), "Good afternoon, Hari")
        self.assertEqual(chatfx.greeting(at(20), ""), "Good evening")
        self.assertEqual(chatfx.greeting(at(2), "Hari"), "Hello, Hari")

    def test_the_gradient_runs_from_its_first_colour_to_its_last(self):
        import chatfx
        self.assertEqual(chatfx.along(("#000000", "#ffffff"), 0.0), (0.0, 0.0, 0.0))
        self.assertEqual(chatfx.along(("#000000", "#ffffff"), 1.0), (255.0, 255.0, 255.0))
        self.assertEqual(chatfx.along(("#000000", "#ff0000", "#ffffff"), 0.5), (255.0, 0.0, 0.0))

    def test_a_pill_is_a_png_with_soft_edges_and_nothing_round_it(self):
        import zlib
        import chatfx
        png = chatfx.pill_png(40, 20, 10, "#e8f0fe")
        self.assertTrue(png.startswith(bytes((137, 80, 78, 71, 13, 10, 26, 10))))
        raw = zlib.decompress(png[png.index(b"IDAT") + 4:png.index(b"IEND") - 8])
        row = lambda y: raw[y * (40 * 4 + 1) + 1:(y + 1) * (40 * 4 + 1)]  # noqa: E731
        self.assertEqual(row(0)[3], 0)  # its corner: clear, the aurora shows
        self.assertEqual(row(10)[20 * 4 + 3], 255)  # its middle: solid
        self.assertEqual(tuple(row(10)[80:83]), (0xe8, 0xf0, 0xfe))

    def test_the_aurora_loops_and_the_ring_is_drawn_still_or_travelling(self):
        import chatfx
        frames = chatfx.aurora_frames(24, 12, n=4)
        self.assertEqual(len(frames), 4)
        self.assertTrue(all(f.startswith(b"P6 24 12 255 ") for f in frames))
        self.assertNotEqual(frames[0], frames[1])  # it moves
        still = chatfx.ring_ppm(60, 30, 14, "#eaeae8", "#ffffff")
        going = chatfx.ring_ppm(60, 30, 14, "#eaeae8", "#ffffff", phase=0.25)
        self.assertEqual(len(still), len(going))
        self.assertNotEqual(still, going)

class OnlyLookUpsAreSources(unittest.TestCase):
    def test_opening_an_app_isnt_where_her_answer_came_from(self):
        """22 November 2026, live: "Opened it for you." showed a Mail pill, as the step was "Opening Gmail"."""
        steps = [{"text": "Opening Gmail", "state": "done"}, {"text": "Playing lofi on YouTube", "state": "done"}]
        self.assertEqual(chat.sources(steps), [])
        self.assertEqual([n for n, _ in chat.sources([{"text": "Checking calendar", "state": "done"}])], ["Calendar"])

if __name__ == "__main__":
    unittest.main()
