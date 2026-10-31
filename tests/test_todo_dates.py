"""A to-do's day kept as the date it means (todo.py, 31 October 2026, the owner: "Meet with Sam tomorrow" was said
back as tomorrow every day after): worked out from the day it was added, and said against today's."""
import datetime as dt
import json
import os
import time
import unittest

from tests.support import siri  # noqa: F401  first: temp APPDATA and the tripwires, before anything of hers

import todo

THU = time.mktime(dt.datetime(2026, 10, 29, 20, 26).timetuple())  # a Thursday evening


class Dates(unittest.TestCase):
    def test_the_words_become_a_date(self):
        self.assertEqual(todo.due_of("Meet with Sam tomorrow", THU), ("2026-10-30", "Meet with Sam"))
        self.assertEqual(todo.due_of("Call Ravi by today", THU), ("2026-10-29", "Call Ravi"))
        self.assertEqual(todo.due_of("Send the slides day after tomorrow", THU), ("2026-10-31", "Send the slides"))
        self.assertEqual(todo.due_of("Pay rent on Monday", THU), ("2026-11-02", "Pay rent"))
        self.assertEqual(todo.due_of("Gym next Thursday", THU), ("2026-11-05", "Gym"))
        self.assertEqual(todo.due_of("Buy milk", THU), (None, "Buy milk"))
        self.assertEqual(todo.due_of("Tomorrow", THU)[1], "Tomorrow")  # nothing else said: the words stay

    def test_said_against_today(self):
        item = {"text": "Meet with Sam", "due": "2026-10-30"}
        self.assertEqual(todo.shown(item, dt.date(2026, 10, 29)), "Meet with Sam tomorrow")
        self.assertEqual(todo.shown(item, dt.date(2026, 10, 30)), "Meet with Sam today")
        self.assertEqual(todo.shown(item, dt.date(2026, 10, 31)), "Meet with Sam, which was yesterday")
        self.assertEqual(todo.shown(item, dt.date(2026, 10, 27)), "Meet with Sam on Friday")
        self.assertEqual(todo.shown({"text": "Buy milk"}), "Buy milk")

    def test_a_list_from_before_is_read_from_the_day_each_was_added(self):
        with open(todo._path(), "w", encoding="utf-8") as f:
            json.dump([{"id": 1, "text": "Meet with Sam tomorrow", "added": THU, "done": False},
                       {"id": 2, "text": "Update the test engine", "added": THU, "done": False}], f)
        left = todo.items()
        self.assertEqual([(i["text"], i["due"]) for i in left],
                         [("Meet with Sam", "2026-10-30"), ("Update the test engine", None)])

    def test_added_today_for_tomorrow(self):
        with open(todo._path(), "w", encoding="utf-8") as f:
            json.dump([], f)
        item, new = todo.add("meet with Sam tomorrow")
        self.assertTrue(new)
        self.assertEqual(item["due"], (dt.date.today() + dt.timedelta(days=1)).isoformat())
        self.assertIn("meet with Sam tomorrow", todo.said())
        self.assertIn("today is", todo.for_model())
        os.remove(todo._path())


if __name__ == "__main__":
    unittest.main()
