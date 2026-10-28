"""Atticus's ideas, for Windows (extras.py and its modules, 28 October 2026): where to click drawn on the screen, the
calendar, Spotify, named helpers and their live view, files by what's in them, a reply in the open email, and meeting
notes. Nothing here acts on the PC, listens or goes online: tests.support trips that, and fakes stand in for Windows
Search, the screen, the audio and the model."""
import contextlib
import datetime as dt
import io
import json
import os
import time
import unittest
from unittest import mock

import numpy as np

from tests.support import TRIPPED, siri

import agenda
import agent
import drafts
import extras
import filecontents
import filesearch
import helpers
import jobview
import loopback
import meeting
import overlay
import showme
import spotify

WED = dt.datetime(2026, 10, 28, 20, 40)  # a Wednesday evening

ICS = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0",
    "BEGIN:VTIMEZONE", "TZID:America/New_York",
    "BEGIN:DAYLIGHT", "TZOFFSETFROM:-0500", "TZOFFSETTO:-0400", "DTSTART:19700308T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU", "END:DAYLIGHT",
    "BEGIN:STANDARD", "TZOFFSETFROM:-0400", "TZOFFSETTO:-0500", "DTSTART:19701101T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU", "END:STANDARD", "END:VTIMEZONE",
    "BEGIN:VEVENT", "UID:a1", "SUMMARY:Weekly sync", "DTSTART;TZID=America/New_York:20260105T090000",
    "DTEND;TZID=America/New_York:20260105T093000", "RRULE:FREQ=WEEKLY;BYDAY=MO,TH",
    "EXDATE;TZID=America/New_York:20261102T090000", "END:VEVENT",
    "BEGIN:VEVENT", "UID:a1", "RECURRENCE-ID;TZID=America/New_York:20261029T090000", "SUMMARY:Weekly sync (moved)",
    "DTSTART;TZID=America/New_York:20261029T110000", "DTEND;TZID=America/New_York:20261029T113000", "END:VEVENT",
    "BEGIN:VEVENT", "UID:b2", "SUMMARY:Holiday", "DTSTART;VALUE=DATE:20261030", "DTEND;VALUE=DATE:20261031",
    "END:VEVENT",
    "BEGIN:VEVENT", "UID:c3", "SUMMARY:Call", "DTSTART:20261029T053000Z", "DURATION:PT45M", "END:VEVENT",
    "BEGIN:VEVENT", "UID:d4", "SUMMARY:Monthly review", "DTSTART:20250131T100000", "DTEND:20250131T110000",
    "RRULE:FREQ=MONTHLY;BYDAY=-1FR;COUNT=40", "END:VEVENT",
    "BEGIN:VEVENT", "UID:e5", "SUMMARY:Called off", "STATUS:CANCELLED", "DTSTART:20261029T100000", "END:VEVENT",
    "END:VCALENDAR"])


def ist():
    """True when this PC keeps India's time, the zone the iCal times below are worked out for."""
    return time.localtime().tm_gmtoff == 19800


class Clean(unittest.TestCase):
    def setUp(self):
        for path in (agenda.PATH, helpers.PATH):
            if os.path.exists(path):
                os.remove(path)
        agenda._feeds.clear()
        agenda._failed.clear()
        agenda.LAST.update(event=None, at=0.0)
        extras.TOKENS.clear()
        self.tripped = len(TRIPPED)

    def tearDown(self):
        meeting.NOW[0] = None
        showme.GUIDE[0] = None
        overlay.CURRENT[0] = None
        filesearch.keep_found([])  # what a test found isn't there for the next one's prompt (gated_blocks)
        filesearch.FOUND["at"] = 0.0
        siri.settings.put("jobview", None)


class Times(Clean):
    """What a request says about time, as she works it out with no model."""

    def test_events_said_plainly(self):
        for said, title, start, end, all_day in (
                ("add lunch with Sam tomorrow at 1 to my calendar", "Lunch with Sam", (2026, 10, 29, 13, 0), None,
                 False),
                ("put a meeting with Ravi on Friday at 3 PM for an hour", "Meeting with Ravi", (2026, 10, 30, 15, 0),
                 (2026, 10, 30, 16, 0), False),
                ("schedule dentist appointment on 5 November at 10 am", "Dentist appointment", (2026, 11, 5, 10, 0),
                 None, False),
                ("add an event called team sync next Monday at 10:30", "Team sync", (2026, 11, 2, 10, 30), None,
                 False),
                ("book a call with Priya from 2 to 3 pm on Thursday", "Call with Priya", (2026, 10, 29, 14, 0),
                 (2026, 10, 29, 15, 0), False),
                ("add Diwali party on the 8th at 7 in the evening", "Diwali party", (2026, 11, 8, 19, 0), None, False),
                ("put the gym at 6 30 am tomorrow", "Gym", (2026, 10, 29, 6, 30), None, False),
                ("add mum's birthday on 12/11", "Mum's birthday", (2026, 11, 12, 0, 0), None, True),
                ("add movie night tonight at 9", "Movie night", (2026, 10, 28, 21, 0), None, False),
                ("add review 2-3 pm tomorrow", "Review", (2026, 10, 29, 14, 0), (2026, 10, 29, 15, 0), False),
                ("put interview with Infosys on Monday at half past 11", "Interview with Infosys",
                 (2026, 11, 2, 11, 30), None, False),
                ("add flight to Delhi on the 3rd of December at 06:15", "Flight to Delhi", (2026, 12, 3, 6, 15),
                 None, False)):
            with self.subTest(said):
                got = agenda.parse_event(said, WED)
                self.assertEqual(got["title"], title)
                self.assertEqual(got["start"], dt.datetime(*start))
                self.assertEqual(got["end"], dt.datetime(*end) if end else None)
                self.assertEqual(got["all_day"], all_day)

    def test_no_day_or_time_is_no_event(self):
        for said in ("add standup every day", "add a test for the login page", "put the kettle on"):
            self.assertIsNone(agenda.parse_event(said, WED), said)

    def test_an_hour_alone_for_an_event_is_the_afternoon_one(self):
        self.assertEqual(agenda.parse_event("add call with Ravi at 3", WED)["start"].hour, 15)
        self.assertEqual(agenda.parse_event("add breakfast with Sam at 8 tomorrow", WED)["start"].hour, 8)
        self.assertEqual(agenda.parse_event("add walk tomorrow morning at 6", WED)["start"].hour, 6)

    def test_the_days_a_question_is_about(self):
        for said, a, b, label in (("what's on my calendar tomorrow", (2026, 10, 29), (2026, 10, 30), "tomorrow"),
                                  ("what do I have on Friday", (2026, 10, 30), (2026, 10, 31), "Friday"),
                                  ("next week", (2026, 11, 2), (2026, 11, 9), "next week"),
                                  ("this weekend", (2026, 10, 31), (2026, 11, 2), "this weekend")):
            got = agenda.day_range(said, WED)
            self.assertEqual((got[0], got[1], got[2]), (dt.datetime(*a), dt.datetime(*b), label), said)
        self.assertEqual(agenda.day_range("today", WED)[0], WED)  # what's left of it


class Store(Clean):
    def test_added_listed_found_moved_and_gone(self):
        lunch = agenda.add("Lunch with Sam", dt.datetime(2026, 10, 29, 13, 0))
        agenda.add("Dentist", dt.datetime(2026, 10, 30, 10, 0), where="Apollo")
        agenda.add("Team offsite", dt.datetime(2026, 10, 29), all_day=True)
        found, missing = agenda.between(dt.datetime(2026, 10, 29), dt.datetime(2026, 10, 30))
        self.assertEqual(agenda.listing(found, "tomorrow", missing, WED),
                         "Tomorrow you have 2 things: Team offsite all day, and Lunch with Sam at 1 PM.")
        self.assertEqual(agenda.find("my 1 pm", WED)["title"], "Lunch with Sam")
        self.assertEqual(agenda.find("the dentist", WED)["title"], "Dentist")
        moved = agenda.change(lunch["id"], start=dt.datetime(2026, 10, 30, 14, 0))
        self.assertEqual(moved["end"], dt.datetime(2026, 10, 30, 15, 0))  # it keeps its hour
        agenda.remove(lunch["id"])
        with self.assertRaises(LookupError):
            agenda.remove(lunch["id"])

    def test_a_word_before_each_thing_once(self):
        agenda.add("Lunch with Sam", dt.datetime(2026, 10, 30, 14, 0))
        self.assertEqual(agenda.due(dt.datetime(2026, 10, 30, 13, 40)), [])
        said = agenda.due(dt.datetime(2026, 10, 30, 13, 52))
        self.assertEqual([line for _, line in said], ["Lunch with Sam starts in 8 minutes."])
        self.assertEqual(agenda.due(dt.datetime(2026, 10, 30, 13, 55)), [])  # said once

    def test_googles_own_page_filled_in(self):
        url = agenda.google_link("Lunch with Sam", dt.datetime(2026, 10, 29, 13, 0))
        self.assertIn("action=TEMPLATE&text=Lunch%20with%20Sam&dates=20261029T130000/20261029T140000", url)


class ICal(Clean):
    """Google's and Outlook's private iCal addresses: read only, repeats worked out, in this PC's time."""

    @unittest.skipUnless(ist(), "the times below are India's")
    def test_repeats_moved_and_missed_ones_and_another_zones_clocks_changing(self):
        events = agenda.parse_ics(ICS)
        got = [(o["start"], o["title"]) for o in agenda.expand(events, dt.datetime(2026, 10, 26),
                                                                dt.datetime(2026, 11, 7))]
        self.assertIn((dt.datetime(2026, 10, 26, 18, 30), "Weekly sync"), got)  # New York in summer time
        self.assertIn((dt.datetime(2026, 11, 5, 19, 30), "Weekly sync"), got)  # and after its clocks went back
        self.assertNotIn((dt.datetime(2026, 11, 2, 19, 30), "Weekly sync"), got)  # EXDATE
        self.assertIn((dt.datetime(2026, 10, 29, 20, 30), "Weekly sync (moved)"), got)
        self.assertNotIn((dt.datetime(2026, 10, 29, 18, 30), "Weekly sync"), got)  # moved, not twice
        self.assertIn((dt.datetime(2026, 10, 29, 11, 0), "Call"), got)
        self.assertIn((dt.datetime(2026, 10, 30, 10, 0), "Monthly review"), got)  # the last Friday
        self.assertNotIn("Called off", [t for _, t in got])

    def test_a_calendar_address_is_kept_and_never_said(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            name, n = agenda.add_feed("webcal://calendar.google.com/calendar/ical/x/private-secret/basic.ics",
                                      fetch=lambda url: ICS)
        self.assertEqual((name, n), ("Google", 6))
        self.assertEqual(agenda.feeds()[0]["url"], "https://calendar.google.com/calendar/ical/x/private-secret/basic.ics")
        with contextlib.redirect_stdout(out):  # down: what was kept is read, and nothing says its address
            agenda._feeds.clear()
            agenda._fetch(agenda.feeds()[0]["url"], fetch=lambda url: (_ for _ in ()).throw(OSError("offline")))
        self.assertNotIn("private-secret", out.getvalue())
        with self.assertRaises(ValueError):
            agenda.add_feed("ftp://example.com/cal.ics")


class Routing(Clean):
    """What's said plainly goes straight to its step, no model; what isn't, isn't taken."""

    def quick(self, words, gate=False):
        with contextlib.redirect_stdout(io.StringIO()):
            return extras.quick(words, gate)

    def test_everyday_requests_are_left_alone_and_touch_nothing(self):
        for words in ("open notepad", "what time is it", "play arijit singh songs", "find my resume",
                      "remind me in 10 minutes to call mum", "what's the weather tomorrow", "set a timer for 5 minutes",
                      "tell him I'm on my way", "when is the next india match", "cancel my timers", "cancel task 3",
                      "add milk to my to-do list", "show me where it is", "what's my day like"):
            self.assertIsNone(self.quick(words), words)
        self.assertEqual(TRIPPED[self.tripped:], [])

    def test_where_do_i_click_is_shown_only_when_asked_of_her(self):
        plan = self.quick("where do I click to turn on Bluetooth")
        self.assertEqual(plan["steps"], [{"do": "show", "task": "where do I click to turn on Bluetooth"}])
        self.assertIsNone(self.quick("where do I click to turn on Bluetooth", gate="cold"))
        self.assertEqual(self.quick("explain this page to me")["steps"][0]["do"], "show")
        with mock.patch.object(siri.settings, "get", lambda k: False if k == "vision" else siri.settings.DEFAULTS.get(k)):
            self.assertIn("turned off", self.quick("show me where to change the wallpaper")["say"])

    def test_a_calendar_asked_about_and_added_to(self):
        self.assertEqual(self.quick("what's on my calendar tomorrow")["say"], "Nothing on your calendar tomorrow.")
        plan = self.quick("add lunch with Sam tomorrow at 1")
        self.assertEqual(plan["steps"][0]["do"], "event")
        self.assertEqual(plan["say"], "Added Lunch with Sam tomorrow at 1 PM.")
        self.assertIn("added Lunch with Sam", siri.do_step(plan["steps"][0]))
        self.assertIn("Lunch with Sam at 1 PM", self.quick("what's on my calendar tomorrow")["say"])
        self.assertIsNone(self.quick("add a reminder for lunch tomorrow at 1"))  # a reminder is a timer's

    def test_moving_or_cancelling_is_read_back_and_only_a_yes_does_it(self):
        start = dt.datetime.combine(dt.date.today() + dt.timedelta(days=1), dt.time(13))
        agenda.add("Lunch with Sam", start)
        plan = self.quick("move lunch with Sam to 4")
        self.assertEqual(plan["say"], "Move Lunch with Sam from tomorrow at 1 PM to tomorrow at 4 PM?")
        step = plan["confirm"]["steps"][0]
        with self.assertRaises(RuntimeError):  # without her question's token, never
            siri.do_step({k: v for k, v in step.items() if k != "token"})
        siri.do_step(step)
        self.assertEqual(agenda.find("lunch with sam")["start"], start.replace(hour=16))
        with self.assertRaises(RuntimeError):  # and only once
            siri.do_step(step)
        plan = self.quick("cancel lunch with Sam")
        self.assertTrue(plan["say"].startswith("Delete Lunch with Sam on tomorrow at 4 PM"))
        siri.do_step(plan["confirm"]["steps"][0])
        self.assertIsNone(agenda.find("lunch with sam"))

    def test_a_move_the_model_planned_is_asked_about_first(self):
        start = dt.datetime.combine(dt.date.today() + dt.timedelta(days=2), dt.time(10))
        agenda.add("Dentist", start)
        plan = extras.stage({"steps": [{"do": "event", "action": "move", "title": "Dentist",
                                        "new_start": start.replace(hour=12).isoformat(timespec="minutes")}],
                             "say": "Moved it."})
        self.assertEqual(plan["steps"], [])
        self.assertTrue(plan["say"].startswith("Move Dentist from"))
        self.assertEqual(plan["confirm"]["steps"][0]["action"], "move")
        added = {"steps": [{"do": "event", "action": "add", "title": "Gym", "start": "2026-11-01T07:00"}], "say": ""}
        self.assertIs(extras.stage(added), added)  # an add goes ahead

    def test_spotify_offers_to_install_itself_first(self):
        staged = {"steps": [], "say": "Spotify 1.3 from Spotify AB. Install it?", "confirm": {"steps": [
            {"do": "install_run"}], "say": ""}}
        with mock.patch.object(spotify, "installed", lambda: False), \
                mock.patch.object(siri, "stage_install", lambda name: staged):
            plan = self.quick("play lofi beats on Spotify")
        self.assertTrue(plan["say"].startswith("Spotify isn't on this PC yet."))
        with mock.patch.object(spotify, "installed", lambda: True):
            self.assertEqual(self.quick("play the playlist Discover Weekly on Spotify")["steps"],
                             [{"do": "spotify", "query": "Discover Weekly", "kind": "playlist"}])
            self.assertEqual(self.quick("play my liked songs")["steps"][0]["query"], "liked songs")
        web = self.quick("play lofi beats on spotify web")["steps"]
        self.assertEqual(web[0]["url"], "https://open.spotify.com/search/lofi%20beats")

    def test_files_found_by_what_is_in_them(self):
        rows = [(r"C:\Users\x\Documents\Tokyo trip plan.docx", time.time() - 86400, 1000, 900),
                (r"C:\Users\x\project\Backend\compile_errors.txt", time.time(), 10, 990)]
        with mock.patch.object(filecontents, "_rows", lambda sql: rows), \
                mock.patch.object(filesearch, "scopes", lambda phone=False: [r"C:\Users\x"]):
            plan = self.quick("find my notes about the Tokyo trip")
        self.assertTrue(plan["say"].startswith("2 files mention \u201cTokyo trip\u201d. The best match is Tokyo trip "
                                               "plan, a Word file"), plan["say"])  # never the build output first
        self.assertEqual(plan["confirm"]["steps"], [{"do": "open_file", "n": 1}])
        self.assertEqual(filesearch.recent()[0]["name"], "Tokyo trip plan.docx")  # "open the first one" works

    def test_helpers_by_name(self):
        made = []
        with mock.patch.object(siri, "queue_job", lambda goal, description=None, **kw: made.append((goal, description))
                               or 7), \
                mock.patch.object(siri.TASK_STORE, "get", lambda tid: {"id": tid, "status": "running", "payload": {
                    "goal": "find budget laptops", "words": "find budget laptops", "named": True}}):
            plan = self.quick("make a helper called Researcher to find budget laptops under 50000")
            self.assertEqual(plan["steps"][0], {"do": "helper", "action": "start", "name": "Researcher",
                                                "goal": "find budget laptops under 50000"})
            siri.do_step(plan["steps"][0])
            self.assertEqual(made[0][1], "Researcher: find budget laptops under 50000")
            self.assertEqual(helpers.name_of(7), "Researcher")
            self.assertEqual(self.quick("Researcher, also look at battery life")["say"], "Okay, I've told Researcher.")
            self.assertIn("also look at battery life", agent.JOBS[7].steer[-1])
            self.assertIn("Researcher is", self.quick("how's Researcher doing")["say"])
            self.assertEqual(extras.result_line({"id": 7}, "Lenovo IdeaPad Slim 3 is best.", True),
                             "Researcher's done. Lenovo IdeaPad Slim 3 is best.")
            self.assertEqual(siri._task_result_line({"id": 7, "kind": "agent"}, "Found three.", True),
                             "Researcher's done. Found three.")
        agent.JOBS.pop(7, None)
        self.assertIsNone(self.quick("make a helper called it to do things"))  # no name

    def test_a_reply_goes_into_the_email_in_front_never_a_chats(self):
        with mock.patch.object(drafts, "mail_window", lambda: (1, "chrome.exe", "Inbox - Gmail", "mail.google.com")):
            plan = self.quick("reply saying sounds good, see you at 7")
            self.assertEqual(plan["steps"], [{"do": "draft_reply", "text": "Sounds good, see you at 7.",
                                              "about": "reply saying sounds good, see you at 7"}])
            plan = self.quick("write a reply saying yes but ask to move it to Friday")
            self.assertEqual(plan["steps"][0]["text"], "")
            self.assertEqual(plan["steps"][0]["about"], "yes but ask to move it to friday")
        with mock.patch.object(drafts, "mail_window", lambda: None):
            self.assertIsNone(self.quick("reply saying on my way"))  # a chat's: her messaging has it
            self.assertEqual(self.quick("reply to this email saying thanks")["say"], drafts.NO_MAIL)

    def test_meeting_notes_start_and_only_her_name_counts_meanwhile(self):
        plan = self.quick("take notes in this meeting")
        self.assertEqual(plan["steps"], [{"do": "meeting", "action": "start"}])
        self.assertIsNone(self.quick("take notes in this meeting", gate="cold"))

        class Going:
            suggestion = ("Can you share the deck?", "Yes, I'll send it after the call.")
            notes = {"decisions": ["Ship on Friday"]}

            def minutes(self):
                return 5

            def transcript(self, last=None, most=4000):
                return "[10:00:00] Them: Can you share the deck by Friday?"

            def last_from(self, who="Them", n=2):
                return ["Can you share the deck by Friday?"]
        meeting.NOW[0] = Going()
        self.assertEqual(self.quick("what did they just ask")["say"],
                         "They said: \u201cCan you share the deck by Friday?\u201d")
        self.assertEqual(self.quick("what should I say")["say"], "You could say: Yes, I'll send it after the call.")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(siri.handle("so the budget for the third quarter looks fine", gate="cold"))
        self.assertEqual(TRIPPED[self.tripped:], [])  # never sent to the model
        self.assertIn("A meeting is on", extras.prompt_block("what have we decided so far"))

    def test_the_live_view_on_and_off(self):
        with mock.patch.object(jobview, "sections", lambda: []):
            self.assertIn("Nothing's running", self.quick("show me the mini view")["say"])
        with mock.patch.object(jobview, "sections", lambda: [{"key": 3}]):
            self.assertIn("in the corner", self.quick("show me the mini view")["say"])
        self.assertIsNot(siri.settings.get("jobview"), False)
        self.assertEqual(self.quick("hide the live view")["steps"], [{"do": "jobview", "on": False}])


class Prompt(Clean):
    def test_only_the_words_that_may_ask_bring_the_lines(self):
        self.assertEqual(extras.prompt_block("open notepad"), "")
        self.assertIn('{"do":"show"', extras.prompt_block("where do I click to pin this"))
        self.assertIn('{"do":"agenda"', extras.prompt_block("do I have any meetings on Friday"))
        self.assertIn('{"do":"spotify"', extras.prompt_block("put on my workout playlist"))
        self.assertIn('{"do":"files_inside"', extras.prompt_block("any documents that mention the merger"))
        self.assertLess(len(extras.prompt_block("where do I click to pin this")), 400)

    def test_every_new_step_has_its_line(self):
        for name in extras.LINES:
            self.assertIn(f'{{"do":"{name}"', siri.toolbox.get(name).line)


class Drawing(unittest.TestCase):
    """overlay's marks, worked out with no window."""

    def test_a_line_runs_edge_to_edge_never_through_the_middle(self):
        ring = overlay.Mark("ring", (100, 100, 200, 140), 1)
        box = overlay.Mark("box", (400, 80, 700, 300), 2, link=True)
        x, y = ring.edge(box.centre)
        self.assertAlmostEqual(np.hypot(x - ring.centre[0], y - ring.centre[1]), ring.r + 7, places=3)
        x, y = box.edge(ring.centre)
        self.assertAlmostEqual(x, 400 - 13, places=3)  # its left side, padded

    def test_a_big_area_is_boxed_not_ringed(self):
        self.assertEqual(overlay.Mark("ring", (0, 0, 900, 500)).kind, "box")
        self.assertEqual(overlay.Mark("ring", (0, 0, 80, 30)).kind, "ring")

    def test_a_stroke_lands_where_it_is_drawn(self):
        canvas = overlay.Canvas(0, 0, 200, 200)
        x0, y0, cover = overlay.ring(100, 100, 40, 4)
        canvas.paint(x0, y0, cover, overlay.INK)
        self.assertGreater(canvas.img[60, 100, 3], 0.9)  # on the ring
        self.assertEqual(canvas.img[100, 100, 3], 0.0)  # its middle
        half = overlay.Canvas(0, 0, 200, 200)
        x0, y0, cover = overlay.ring(100, 100, 40, 4, progress=0.25)  # a quarter, clockwise from the top
        half.paint(x0, y0, cover, overlay.INK)
        self.assertGreater(half.img[72, 128, 3], 0.5)  # up and to the right, 45 degrees round
        self.assertEqual(half.img[140, 100, 3], 0.0)  # the bottom: not yet

    def test_a_click_is_pressed_and_let_go(self):
        states = iter([False, True, True, False])
        with mock.patch.object(overlay, "pressed", lambda vk: False if vk == overlay.VK_ESCAPE else next(states)), \
                mock.patch.object(overlay.win, "cursor_pos", lambda: (5, 6)):
            self.assertEqual(overlay.wait_click(1, poll=0), ("click", (5, 6)))


class Pointing(unittest.TestCase):
    def test_marks_by_id_and_by_place_never_a_password(self):
        class Shot:
            w, h, scale, rect = 1280, 800, 1.5, (0, 0, 1920, 1200)

            def to_screen(self, x, y):
                return x * 1.5, y * 1.5
        items = [{"id": 3, "role": "button", "name": "Bluetooth", "rect": (100, 100, 220, 140), "el": None},
                 {"id": 4, "role": "edit", "name": "Password", "password": True, "rect": (0, 0, 10, 10), "el": None}]
        reply = {"marks": [{"id": 3, "say": "Click Bluetooth"}, {"id": 4, "say": "Type it"},
                           {"x": 640, "y": 400, "w": 100, "h": 40, "shape": "box", "say": "1. This part"}]}
        got = showme.points(reply, items, Shot())
        self.assertEqual([(p.kind, p.rect, p.say) for p in got],
                         [("ring", (100, 100, 220, 140), "Click Bluetooth."), ("box", (885, 570, 1035, 630),
                                                                              "This part.")])


class Meetings(unittest.TestCase):
    def test_what_one_person_said_at_a_time(self):
        turns, probs = [], iter([0.0] * 3 + [0.9] * 30 + [0.1] * 30)
        seg = meeting.Segmenter(lambda block: [next(probs)], lambda audio, began: turns.append(len(audio)))
        for _ in range(63):
            seg.feed(np.zeros(512, np.float32), now=100.0)
        self.assertEqual(len(turns), 1)
        self.assertGreaterEqual(turns[0], 30 * 512)

    def test_notes_heard_written_and_recapped_on_this_pc(self):
        class Fake:
            def __init__(self, on_block):
                self.stopped = False

            def stop(self):
                self.stopped = True
        said = iter([("Can you share the deck by Friday?", 0.9), ("Yes, I'll send it tomorrow.", 0.95)])

        def transcribe(audio):
            text, sure = next(said)
            h = siri.speech.heard(text, sure)
            return h, 10
        asked = []

        def ask(system, user):
            asked.append(system[:20])
            if system == meeting.RECAP_PROMPT:
                return json.dumps({"title": "Deck review", "summary": "They want the deck.", "decisions": ["Ship it"],
                                   "actions": [{"who": "You", "what": "send the deck", "when": "Friday"}]})
            return "Say you'll send it tomorrow."
        m = meeting.Meeting(transcribe, vad_factory=lambda: (lambda b: [0.0]), mic=Fake, loop=Fake, ask=ask,
                            card=False)
        with mock.patch.object(meeting, "FOLDER", os.path.join(os.environ["APPDATA"], "meetings")), \
                mock.patch.object(m, "path", os.path.join(os.environ["APPDATA"], "meetings", "test meeting.md")):
            m.start()
            m.turns.put(("Them", np.zeros(8000, np.float32), time.time()))
            m.turns.put(("You", np.zeros(8000, np.float32), time.time() + 3))
            end = time.time() + 5
            while len(m.lines) < 2 and time.time() < end:
                time.sleep(0.05)
            self.assertEqual([l["who"] for l in m.lines], ["Them", "You"])
            line = m.finish()
            self.assertIn("1 decision and 1 thing to do", line)
            with open(m.path, encoding="utf-8") as f:
                text = f.read()
        self.assertIn("- [ ] You: send the deck (by Friday)", text)
        self.assertIn("Them: Can you share the deck by Friday?", text)
        self.assertTrue(all(s.stopped for s in m.sources))

    def test_her_own_line_heard_back_through_the_mic_isnt_yours(self):
        self.assertGreater(meeting._similar("Can you share the deck?", "can you share the deck"), 0.9)


class Sound(unittest.TestCase):
    def test_a_tone_keeps_its_pitch_at_16_khz(self):
        r = loopback.Resampler(48000)
        tone = np.sin(2 * np.pi * 1000 * np.arange(48000) / 48000).astype(np.float32)
        out = np.concatenate([r(tone[i:i + 480]) for i in range(0, 48000, 480)])
        self.assertLess(abs(len(out) - 16000), 4)
        self.assertEqual(int(np.argmax(np.abs(np.fft.rfft(out[:16000])))), 1000)


class Replies(unittest.TestCase):
    def test_your_own_words_or_what_to_say_about_it(self):
        self.assertEqual(drafts.literal("reply: sounds good, see you at 7"), "Sounds good, see you at 7.")
        self.assertEqual(drafts.literal("Reply with thanks!"), "Thanks!")
        self.assertIsNone(drafts.literal("reply saying yes but ask him to move it to Friday"))
        self.assertIsNone(drafts.literal("reply politely that I can't make it"))
        self.assertIsNone(drafts.literal("reply to mum saying hi"))  # a chat's


class Steering(unittest.TestCase):
    def test_what_you_tell_a_running_helper_reaches_its_next_round(self):
        job = agent.Job(42, "find budget laptops", "find budget laptops", True)
        job.steer = ["also look at battery life"]
        token = agent.JOB.set(job)
        try:
            r = agent.Run(goal="find budget laptops")
        finally:
            agent.JOB.reset(token)
        obs = {"title": "Amazon", "exe": "chrome.exe", "site": "amazon.in", "items": [], "focus": None, "full": True,
               "own": True, "hwnd": 1}
        with mock.patch.object(siri, "lessons_for", lambda where: ""):
            text = agent.messages(r, obs, None)[1]["content"]
        self.assertIn("Since you started, they told you: \u201calso look at battery life\u201d", text)


class Contents(unittest.TestCase):
    def test_what_to_look_for_inside(self):
        self.assertEqual(filecontents.wanted("find my notes about the Tokyo trip")[:2][0], ["tokyo", "trip"])
        self.assertEqual(filecontents.wanted("search inside my files for 'job description'")[0], ["job", "description"])
        self.assertIsNone(filecontents.wanted("find my resume"))
        sql = filecontents.query(["o'brien", "trip"], (".pdf",))
        self.assertIn("CONTAINS(*, '\"obrien*\" AND \"trip*\"')", sql)
        self.assertIn("System.FileExtension = '.pdf'", sql)
        self.assertIn("FREETEXT(*, 'obrien trip')", filecontents.query(["o'brien", "trip"], (), loose=True))


if __name__ == "__main__":
    unittest.main()
