"""A window of her own for her jobs on websites, a profile of your own Chrome (siri.job_profile, agent.own_window,
31 October 2026, the owner's ask, after Google refused to sign in to her own browser): a job's site opens in the
profile Settings names, when Chrome has it; a step that names a browser or profile keeps its own; a turn's step, you
watching, opens where it always did; and no such profile means your usual one, said once. Nothing here opens a
browser: the Jobs fixture's FakeApp takes the open."""
import contextlib
import io
import unittest
from unittest import mock

from tests.support import siri  # first: temp APPDATA and the tripwires
from tests.test_background import Jobs

import agent
import settings


class OwnWindow(Jobs):
    def setUp(self):
        super().setUp()
        settings.put("job_profile", "Harry")
        self.patch(siri, "default_browser", lambda: "chrome")
        self.patch(siri, "find_profile", lambda key, spoken: "Profile 2" if spoken == "Harry" else self.missing(spoken))
        siri._job_profile_said.clear()
        w = self.app.window("linkedin.com", "chrome.exe", "LinkedIn", site="linkedin.com")
        w.controls = []

    @staticmethod
    def missing(spoken):
        raise RuntimeError(f"There's no {spoken} profile in Chrome")

    def test_a_jobs_site_opens_in_her_profile_and_a_named_one_stays(self):
        job = agent.Job(3, "post on LinkedIn")
        r = mock.Mock(job=job)
        self.assertEqual(agent.own_window(r, {"do": "website", "url": "https://www.linkedin.com", "x": 1}),
                         {"do": "website", "url": "https://www.linkedin.com", "profile": "Harry"})
        self.assertEqual(agent.own_window(r, {"do": "open", "app": "Google Chrome"}),
                         {"do": "open", "app": "Google Chrome", "profile": "Harry"})
        self.assertEqual(agent.own_window(r, {"do": "open", "app": "Notepad"}), {"do": "open", "app": "Notepad"})
        self.assertEqual(agent.own_window(r, {"do": "website", "url": "https://x.com", "profile": "Work"}),
                         {"do": "website", "url": "https://x.com", "profile": "Work"})
        self.assertEqual(agent.own_window(r, {"do": "website", "url": "https://x.com", "browser": "Microsoft Edge"}),
                         {"do": "website", "url": "https://x.com", "browser": "Microsoft Edge"})
        # a turn's step, you watching: where it always opened
        self.assertEqual(agent.own_window(mock.Mock(job=None), {"do": "website", "url": "https://x.com"}),
                         {"do": "website", "url": "https://x.com"})
        self.assertEqual(agent.own_window(None, {"do": "website", "url": "https://x.com"}),
                         {"do": "website", "url": "https://x.com"})

    def test_no_such_profile_means_your_usual_one_said_once(self):
        settings.put("job_profile", "Nobody")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(siri.job_profile(), "")
            self.assertEqual(siri.job_profile(), "")
        self.assertEqual(out.getvalue().count("There's no Nobody profile"), 1)
        settings.put("job_profile", "")
        self.assertEqual(siri.job_profile(), "")
        settings.put("job_profile", "Harry")
        self.assertEqual(siri.job_profile(), "Harry")

    def test_a_job_on_your_screen_opens_the_site_in_her_window(self):
        self.model({"steps": [{"do": "website", "url": "https://www.linkedin.com"}]},
                   {"steps": [], "done": True, "expect": {"has": "LinkedIn"}, "say": "It's open."})
        tid = self.queue_job("open LinkedIn and check my notifications in the background")
        siri.run_job(self.claim(tid))
        self.assertEqual(self.app.opened, [{"do": "website", "url": "https://www.linkedin.com", "profile": "Harry"}])
        self.assertEqual(self.store.get(tid)["status"], "completed")


if __name__ == "__main__":
    unittest.main()
