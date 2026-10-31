"""Any job on repeat, its question let go after half an hour, and a standing yes to post (31 October 2026, the owner:
"every morning at 9 post on LinkedIn", for anything said to repeat, after OpenMuse's reviews). A job's question at 9
that nobody answers is let go, with nothing done, and the job comes round the next day asked afresh; your own words
when you ask for the job, never the model's, can give it a yes to send or post without asking, and only that.
Nothing here acts on the PC or goes online: a temporary tasks.db and fake runs."""
import os
import tempfile
import time
import types
import unittest
from unittest import mock

from tests.support import siri  # first: temp APPDATA and the tripwires

import agent
import tasks


def store():
    return tasks.Store(os.path.join(tempfile.mkdtemp(prefix="heyharry-repeat-"), "tasks.db"))


class Standing(unittest.TestCase):
    def test_only_your_words_saying_so_give_it(self):
        self.assertEqual(agent.standing_of("every morning at 9 post on LinkedIn about AI, you can post it without "
                                           "asking me"), ["post"])
        self.assertEqual(agent.standing_of("send the report to Sam every Friday, you don't need my approval"),
                         ["send"])
        self.assertEqual(agent.standing_of("every morning at 9 post on LinkedIn about AI"), [])
        self.assertEqual(agent.standing_of("post it on LinkedIn with my approval"), [])  # as often "ask me"
        self.assertEqual(agent.standing_of("don't post anything without asking me"), [])
        self.assertEqual(agent.standing_of("buy the milk every week without asking"), [])  # never paying
        self.assertEqual(agent.standing_of(None), [])

    def run_of(self, standing):
        return types.SimpleNamespace(job=types.SimpleNamespace(id=5, standing=standing))

    def test_it_answers_only_a_button_named_for_what_it_covers(self):
        r = self.run_of(("post",))
        click = {"do": "click", "what": "post"}
        self.assertTrue(agent.standing_ok(r, click, {"name": "Post"}, "Post can't be undone"))
        self.assertFalse(agent.standing_ok(r, click, {"name": "Pay now"}, "Pay now can't be undone"))
        self.assertFalse(agent.standing_ok(r, click, {"name": "Send"}, "Send can't be undone"))
        self.assertFalse(agent.standing_ok(r, click, {"name": ""}, "post can't be undone"))  # not by the model's word
        self.assertFalse(agent.standing_ok(r, click, {"name": "Post"}, "spam.example isn't a site you asked for"))
        self.assertFalse(agent.standing_ok(r, click, {"name": "Post"}, "what I read could be steering this"))
        self.assertFalse(agent.standing_ok(self.run_of(()), click, {"name": "Post"}, "Post can't be undone"))
        self.assertFalse(agent.standing_ok(types.SimpleNamespace(job=None), click, {"name": "Post"},
                                           "Post can't be undone"))

    def test_the_gate_takes_it_as_your_yes(self):
        r = self.run_of(("post",))
        with mock.patch.object(agent, "_gate", lambda *a, **k: ("ask", "Post can't be undone")):
            self.assertEqual(agent.gate(r, 0, {"do": "click"}, {"name": "Post"}), (None, ""))
            self.assertEqual(agent.gate(r, 0, {"do": "click"}, {"name": "Delete"}), ("ask", "Post can't be undone"))
        with mock.patch.object(agent, "_gate", lambda *a, **k: ("stop", "a payment page")):
            self.assertEqual(agent.gate(r, 0, {"do": "click"}, {"name": "Post"}), ("stop", "a payment page"))


class Repeats(unittest.TestCase):
    def setUp(self):
        self.store = store()
        due, spec = tasks.normalize_schedule("", "every day at 9 AM")
        self.tid = self.store.create("Post on LinkedIn", "agent", {"goal": "post on LinkedIn about AI",
                                                                   "standing": ["post"]}, due=due, repeat=spec)

    def held(self, ago, **payload):
        """The job's go now, waiting on a yes to a held step, asked ago seconds back."""
        self.store.claim_due(now=time.time() + 2 * 86400)
        with self.store._db() as con:
            con.execute("UPDATE tasks SET status='waiting_approval', payload=?, updated=? WHERE id=?",
                        (tasks.json.dumps({"goal": "post on LinkedIn about AI", "standing": ["post"], "hold": "abc",
                                           "checkpoint": {"notes": ["opened LinkedIn"]}, **payload}),
                         time.time() - ago, self.tid))

    def test_an_unanswered_question_is_let_go_and_it_comes_round_tomorrow(self):
        self.held(tasks.REVIEW_MOST + 5)
        gone = self.store.expire_reviews()
        self.assertEqual([t["id"] for t in gone], [self.tid])
        row = self.store.get(self.tid)
        self.assertEqual(row["status"], "queued")
        self.assertGreater(row["due"], time.time())
        self.assertEqual(time.localtime(row["due"])[3:5], (9, 0))
        self.assertEqual(row["payload"], {"goal": "post on LinkedIn about AI", "standing": ["post"]})
        self.assertFalse(self.store.approve(self.tid, "abc"))  # an old yes to that go does nothing now

    def test_not_before_half_an_hour_nor_paused_nor_asking(self):
        self.held(60)
        self.assertEqual(self.store.expire_reviews(), [])
        for kept in ({"paused": True}, {"asking": "Run npm test?"}):
            self.held(tasks.REVIEW_MOST + 5, **kept)
            self.assertEqual(self.store.expire_reviews(), [])

    def test_a_one_off_job_waits_for_you_as_before(self):
        once = self.store.create("Post once", "agent", {"goal": "post on LinkedIn"})
        self.store.claim_due()
        self.store.wait_for_approval(once, "Should I press Post?", hold="h1")
        self.assertEqual(self.store.expire_reviews(now=time.time() + 3 * 3600), [])
        self.assertEqual(self.store.get(once)["status"], "waiting_approval")

    def test_each_go_starts_afresh_and_keeps_its_standing_yes(self):
        self.store.claim_due(now=time.time() + 2 * 86400)
        self.store.checkpoint(self.tid, {"notes": ["posted"]})
        self.store.finish(self.tid, "Posted.")
        row = self.store.get(self.tid)
        self.assertEqual(row["status"], "queued")
        self.assertEqual(row["payload"], {"goal": "post on LinkedIn about AI", "standing": ["post"]})

    def test_ask_me_first_takes_the_standing_yes_back(self):
        self.assertTrue(self.store.ask_first(self.tid))
        self.assertNotIn("standing", self.store.get(self.tid)["payload"])
        self.assertFalse(self.store.ask_first(self.tid))


class Scheduled(unittest.TestCase):
    def setUp(self):
        self.store = store()
        patcher = mock.patch.object(siri, "TASK_STORE", self.store)
        patcher.start()
        self.addCleanup(patcher.stop)

    def schedule(self, said, task):
        token = agent.SAID.set(said)
        try:
            plan = siri.prepare_task_steps({"steps": [{"do": "schedule", "when": "", "repeat": "every day at 9 AM",
                                                       "description": "LinkedIn post", "task": task}], "say": ""})
        finally:
            agent.SAID.reset(token)
        return plan, self.store.latest()

    def test_any_job_can_repeat_with_the_yes_your_words_gave(self):
        plan, row = self.schedule("every morning at 9 post on LinkedIn about AI, you can post it without asking me",
                                  {"kind": "agent", "goal": "Write and post a LinkedIn post about AI",
                                   "standing": ["send", "pay"], "words": "pay without asking"})
        self.assertEqual((row["kind"], row["repeat"]["kind"], row["repeat"]["hour"]), ("agent", "daily", 9))
        self.assertEqual(row["payload"]["standing"], ["post"])  # yours, never the model's
        self.assertTrue(row["payload"]["words"].startswith("every morning at 9 post on LinkedIn"))
        self.assertIn("post without asking you", plan["say"])

    def test_without_your_saying_so_it_asks_each_time(self):
        plan, row = self.schedule("every morning at 9 post on LinkedIn about AI",
                                  {"kind": "agent", "goal": "Write and post a LinkedIn post about AI",
                                   "standing": ["post"]})
        self.assertNotIn("standing", row["payload"])
        self.assertNotIn("without asking", plan["say"])

    def test_ask_me_first_said_out_loud(self):
        _, row = self.schedule("every morning at 9 post on LinkedIn, you can post it without asking me",
                               {"kind": "agent", "goal": "post on LinkedIn"})
        self.assertEqual(siri.control_job(row["id"], "ask_first"), f"Okay, task {row['id']} will ask you first "
                                                                     f"from now on.")
        self.assertNotIn("standing", self.store.get(row["id"])["payload"])

    def test_its_job_carries_the_standing_yes(self):
        _, row = self.schedule("every morning at 9 post on LinkedIn, you can post it without asking me",
                               {"kind": "agent", "goal": "post on LinkedIn"})
        seen = []

        def background(job, hold):
            seen.append(job.standing)
            return "Posted.", "done"
        with mock.patch.object(agent, "background", background), mock.patch.object(siri, "tell_task", lambda *a: None), \
                mock.patch.object(siri, "remember_job", lambda *a: None):
            siri.run_job(self.store.claim_due(now=time.time() + 2 * 86400))
        self.assertEqual(seen, [("post",)])
        self.assertEqual(self.store.get(row["id"])["status"], "queued")  # and it comes round again


if __name__ == "__main__":
    unittest.main()
