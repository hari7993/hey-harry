"""Her browser not working, the job offered on your screen instead (31 October 2026, the owner's ask: "if her
browser doesn't work, do it in my browser"). Her browser's own trouble (herbrowser.Trouble: it won't start, or it
stopped answering) ends the job's go with the question "Should I do it on your screen instead?", keyed to that
question; a yes runs it again on your screen, in your own browser, and the yes is kept for its later goes. A page
that won't have her is still left to you, and nothing is done on your screen without the yes. Nothing here starts a
browser or goes online: FakeChrome, FakeApp, a temporary tasks.db."""
import unittest
from unittest import mock

from tests.support import siri  # first: temp APPDATA and the tripwires
from tests.test_agent import Control
from tests.test_herbrowser import Jobs_

import agent
import herbrowser


class Fallback(Jobs_):
    def setUp(self):
        super().setUp()
        self.posted = []
        w = self.app.window("linkedin.com", "chrome.exe", "LinkedIn", site="linkedin.com")  # your own browser
        w.controls = [Control("Start a post", on=lambda: self.posted.append(True))]

    def broken(self):
        """Her browser won't start: every go to a site in it fails as her browser's own trouble."""
        def go(url):
            raise herbrowser.Trouble("my browser didn't start (chrome.exe exited at once)")
        self.patch(herbrowser, "go", go)

    def test_her_browser_broken_asks_about_your_screen_and_a_yes_does_it_there(self):
        self.broken()
        self.model({"steps": [{"do": "website", "url": "https://www.linkedin.com"}]},
                   {"steps": [{"do": "website", "url": "https://www.linkedin.com"}]},
                   {"steps": [{"do": "click", "id": 1}]},
                   {"steps": [], "done": True, "expect": {"has": "Start a post"}, "say": "It's posted."})
        tid = self.queue_job("post on LinkedIn that I'm excited about my new AI project")
        siri.run_job(self.claim(tid))
        row = self.store.get(tid)
        self.assertEqual(row["status"], "waiting_approval")
        self.assertEqual(self.app.opened, [])  # nothing on your screen without the yes
        self.assertEqual(self.posted, [])
        asked = self.told.get_nowait()
        self.assertIsInstance(asked, siri.JobAsk)
        self.assertIn("My browser isn't working (my browser didn't start (chrome.exe exited at once))", asked)
        self.assertIn("Should I do it on your screen instead, with your mouse and keyboard?", asked)
        self.assertEqual((asked.task_id, asked.hold), (tid, row["payload"]["hold"]))
        self.assertEqual(row["payload"]["screen_offer"], asked.hold)
        self.assertFalse(self.store.approve(tid, "0123abcd"))  # only a yes to that question
        self.assertTrue(self.store.approve(tid, asked.hold))
        siri.run_job(self.claim(tid))
        self.assertEqual(self.app.opened, [{"do": "website", "url": "https://www.linkedin.com"}])  # your browser
        row = self.store.get(tid)
        self.assertTrue(row["payload"]["on_screen"])  # kept: a later go of it stays on your screen
        self.assertNotIn("screen_offer", row["payload"])
        self.assertEqual(row["status"], "waiting_approval")  # posting still waits for your yes, on your screen too
        asked = self.told.get_nowait()
        self.assertEqual(asked, f"Task {tid} asks: Should I press Start a post on linkedin.com?")
        self.assertEqual(self.posted, [])
        self.assertTrue(self.store.approve(tid, asked.hold))
        siri.run_job(self.claim(tid))
        self.assertEqual(self.posted, [True])
        self.assertEqual(self.store.get(tid)["status"], "completed")
        self.assertEqual(self.told.get_nowait(), f"Task {tid}'s done. It's posted.")

    def test_a_no_leaves_your_screen_alone(self):
        self.broken()
        self.model({"steps": [{"do": "website", "url": "https://www.linkedin.com"}]})
        tid = self.queue_job("post on LinkedIn that I'm excited about my new AI project")
        siri.run_job(self.claim(tid))
        self.told.get_nowait()
        self.assertTrue(siri.stop_task(tid))
        self.assertEqual(self.store.get(tid)["status"], "cancelled")
        self.assertEqual(self.app.opened, [])
        self.assertIsNone(self.store.claim_due())

    def test_a_page_that_wont_have_her_is_still_left_to_you(self):
        """A site's own check isn't her browser's trouble: no offer of your screen, as before."""
        self.model({"steps": [{"do": "website", "url": "https://www.zomato.com/"}]},
                   {"steps": [], "done": False, "say": "Zomato wants you to verify you're human, so I've left it."})
        tid = self.queue_job("add paneer tikka to my zomato cart")
        siri.run_job(self.claim(tid))
        row = self.store.get(tid)
        self.assertNotEqual(row["status"], "waiting_approval")
        self.assertNotIn("screen_offer", row["payload"])

    def test_on_your_screen_it_never_uses_her_browser(self):
        job = agent.Job(7, "post on LinkedIn")
        r = agent.Run.__new__(agent.Run) if hasattr(agent, "Run") else mock.Mock()
        r.job, r.pin = job, herbrowser.TAB
        step = {"do": "website", "url": "https://www.linkedin.com"}
        self.assertTrue(agent.in_browser(r, step))
        job.on_screen = True
        self.assertFalse(agent.in_browser(r, step))
        self.assertFalse(agent.in_browser(r, {"do": "click", "id": 1}))


class Trouble(unittest.TestCase):
    def test_her_browser_not_starting_is_trouble(self):
        with mock.patch.object(herbrowser, "running", lambda: False), \
                mock.patch.object(herbrowser, "_start", mock.Mock(side_effect=OSError("exited at once"))):
            with self.assertRaises(herbrowser.Trouble) as got:
                herbrowser._ensure()
        self.assertIn("my browser didn't start (exited at once)", str(got.exception))
        with mock.patch.object(herbrowser, "program", lambda: ""):
            with self.assertRaises(herbrowser.Trouble):
                herbrowser._start()
        self.assertTrue(issubclass(herbrowser.Trouble, RuntimeError))


if __name__ == "__main__":
    unittest.main()
