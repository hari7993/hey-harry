"""Tasks that carry on (31 October 2026, after OpenMuse's durable tasks): a job keeps where it's got to in its task row
as it goes (tasks.Store.checkpoint, agent.saved); a job paused ("pause task 3"), stopped by a restart (recover) or
tried again ("try task 3 again") carries on from there rather than doing it all again; and "what did task 3 do?" is
answered from its row. Nothing here acts on the PC or goes online: Jobs' FakeApp, scripted model and temporary
tasks.db."""
import json
from unittest import mock

from tests.support import siri  # first: temp APPDATA and the tripwires
from tests.test_agent import Control
from tests.test_background import Jobs

import agent


class Carry(Jobs):
    def notes_app(self):
        """A notes app: a Title box and a Body box."""
        w = self.app.window("notes", "notes.exe", "Notes")
        w.controls = [Control("Title", "edit", value=""), Control("Body", "edit", value="")]
        return w

    def go(self, tid):
        siri.run_job(self.claim(tid))
        return self.store.get(tid)

    def test_a_job_keeps_where_its_got_to_as_it_goes(self):
        self.notes_app()
        self.model({"steps": [{"do": "open", "app": "notes"}]},
                   {"steps": [{"do": "click", "id": 1, "text": "Shopping"}]},
                   {"steps": [], "done": True, "expect": {"has": "Title"}, "say": "Done."})
        row = self.go(self.queue_job("write a note called shopping in the notes app in the background"))
        saved = row["payload"]["checkpoint"]
        self.assertEqual(row["status"], "completed")
        self.assertIn("opened notes", saved["notes"])
        self.assertIn('typed "Shopping" into "Title"', saved["notes"])
        self.assertIsNone(saved["url"])  # not in her browser
        said = siri.task_receipt(row["id"])
        self.assertTrue(said.startswith(f"Task {row['id']}, "), said)
        self.assertIn("done", said)
        self.assertIn('opened notes, then typed "Shopping" into "Title"', said)

    def test_paused_as_it_goes_it_waits_and_carries_on_from_there(self):
        w = self.notes_app()
        tid = [None]

        def pause_then_type():
            self.assertEqual(siri.control_job(tid[0], "pause"),
                             f"Paused task {tid[0]}. Say carry on with task {tid[0]} when you want it.")
            return {"steps": [{"do": "click", "id": 1, "text": "Shopping"}]}
        script = self.model({"steps": [{"do": "open", "app": "notes"}]}, pause_then_type,
                            # the go after carry on: it's told what the first got done, and opens the app again
                            {"steps": [{"do": "open", "app": "notes"}]},
                            {"steps": [{"do": "click", "id": 2, "text": "milk"}]},
                            {"steps": [], "done": True, "expect": {"has": "Body"}, "say": "Done."})
        tid[0] = self.queue_job("write a shopping note in the notes app in the background")
        row = self.go(tid[0])
        self.assertEqual(row["status"], "waiting_approval")
        self.assertTrue(row["payload"]["paused"])
        self.assertEqual(row["error"], f"Paused: say carry on with task {tid[0]}")
        self.assertTrue(self.told.empty())  # nothing said for a paused job: no "done", no question
        self.assertIn("opened notes", row["payload"]["checkpoint"]["notes"])
        self.assertEqual(w.controls[0].value, "")  # the step it planned as it was paused wasn't done
        self.assertEqual(siri.control_job(tid[0], "resume"), f"Carrying on with task {tid[0]} from where it got to.")
        row = self.go(tid[0])
        self.assertEqual(row["status"], "completed", row["error"])
        told = script.text(2)
        self.assertIn("A go before this one got this far: opened notes.", told)
        self.assertIn("don't do again what's done", told)
        self.assertEqual(w.controls[1].value, "milk")

    def test_a_restart_in_the_middle_asks_to_carry_on(self):
        self.notes_app()
        tid = self.queue_job("write a shopping note in the notes app in the background")
        self.claim(tid)  # running when she stopped
        self.store.checkpoint(tid, {"notes": ["opened notes"], "todo": "", "site": None, "url": None, "at": 1})
        self.assertEqual(self.store.recover(), [tid])
        row = self.store.get(tid)
        self.assertEqual(row["status"], "waiting_approval")
        self.assertTrue(row["payload"]["interrupted"])
        self.assertIn("approve it to carry on", row["error"])
        siri.ask_again(row)
        asked = self.told.get_nowait()
        self.assertIn("Should I carry on with it?", asked)
        self.assertTrue(self.store.approve(tid, asked.hold))
        script = self.model({"steps": [], "done": True, "say": "Done."})
        self.go(tid)
        self.assertIn("A go before this one got this far: opened notes.", script.text(0))

    def test_one_stopped_by_a_restart_carries_on_when_asked_by_number_too(self):
        tid = self.queue_job("write a shopping note in the notes app in the background")
        self.claim(tid)
        self.store.recover()
        self.assertEqual(siri.control_job(tid, "resume"), f"Carrying on with task {tid} from where it got to.")
        row = self.store.get(tid)
        self.assertEqual((row["status"], row["payload"]["approved"], row["payload"]["carry_on"]), ("queued", True, True))

    def test_tried_again_only_once_it_failed_or_was_stopped(self):
        tid = self.queue_job("write a shopping note in the notes app in the background")
        self.claim(tid)
        self.store.checkpoint(tid, {"notes": ["opened notes"], "todo": "", "site": None, "url": None, "at": 1})
        self.store.finish(tid, error="The model didn't answer in time, so I've stopped there.")
        self.assertEqual(siri.control_job(tid, "retry"), f"Trying task {tid} again, from where it got to.")
        script = self.model({"steps": [], "done": True, "say": "Done."})
        self.go(tid)
        told = script.text(0)
        self.assertIn("A go before this one got this far: opened notes.", told)
        self.assertIn("It ended with: The model didn't answer in time", told)
        self.assertEqual(siri.control_job(tid, "retry"),
                         f"Task {tid} is done already, so I won't do it twice. Ask me again if you want it done again.")

    def test_carry_on_never_says_yes_to_a_step_waiting_on_you(self):
        self.mail()
        self.model({"steps": [{"do": "open", "app": "mail"}]},
                   lambda: {"steps": [{"do": "click", "id": 1, "text": "ravi@example.com"},
                                      {"do": "click", "id": 2, "text": "hi"}, {"do": "click", "id": 3}]})
        tid = self.queue_job("send hi to ravi@example.com in the mail app", "send hi to ravi@example.com in the "
                                                                           "mail app in the background")
        siri.run_job(self.claim(tid))
        self.assertEqual(self.store.get(tid)["status"], "waiting_approval")
        said = siri.control_job(tid, "resume")
        self.assertTrue(said.startswith(f"Task {tid} is waiting for your yes: "), said)
        self.assertEqual(self.store.get(tid)["status"], "waiting_approval")
        self.assertEqual(self.app.sent, [])

    def test_only_her_jobs_are_paused_or_picked_up_again(self):
        rid = self.store.create("Remind me to call Mum", "reminder", {"text": "call Mum"})
        self.assertEqual(siri.control_job(rid, "pause"), f"Task {rid} isn't a job I can pause.")
        self.assertEqual(siri.control_job(999, "pause"), "I don't have a task 999.")
        tid = self.queue_job("write a note in the notes app in the background")
        self.assertEqual(siri.control_job(tid, "resume"), f"Task {tid} isn't paused.")
        self.assertTrue(self.store.pause(tid))  # queued: paused before it ever started
        self.assertIsNone(self.store.claim_due(skip=("reminder",)))
        self.assertTrue(self.store.carry_on(tid))
        self.assertEqual(self.store.claim_due(skip=("reminder",))["id"], tid)

    def test_approve_on_a_paused_jobs_card_carries_it_on(self):
        tid = self.queue_job("write a note in the notes app in the background")
        self.store.pause(tid)
        self.assertTrue(self.store.approve(tid))  # the island's Approve, the Tasks tab's, "approve task 3"
        row = self.store.get(tid)
        self.assertEqual((row["status"], row["payload"].get("carry_on"), "paused" in row["payload"]),
                         ("queued", True, False))


class Said(Jobs):
    def test_said_by_number(self):
        for words, action in (("pause task 3", "pause"), ("hold task 3", "pause"), ("carry on with task 3", "resume"),
                              ("continue with task 3", "resume"), ("resume task 3", "resume"),
                              ("try task 3 again", "retry"), ("retry task 3", "retry"), ("do task 3 again", "retry")):
            with self.subTest(words=words):
                plan = siri.from_table(words)
                self.assertEqual(plan["steps"], [{"do": "task_control", "action": action, "id": 3}])

    def test_what_a_task_did_is_answered_from_its_row(self):
        tid = self.queue_job("add paneer tikka to my zomato cart")
        self.claim(tid)
        self.store.checkpoint(tid, {"notes": ["went to https://www.zomato.com/", 'clicked "Add" (after your yes)'],
                                    "todo": "", "site": "zomato.com", "url": "https://www.zomato.com/", "at": 1})
        self.store.finish(tid, "Added paneer tikka to your cart.")
        for words in (f"what did task {tid} do", f"how did task {tid} go", f"what happened to task {tid}"):
            with self.subTest(words=words):
                said = siri.from_table(words)["say"]
                self.assertIn("done", said)
                self.assertIn('went to https://www.zomato.com/, then clicked "Add" (after your yes).', said)
                self.assertTrue(said.endswith("Added paneer tikka to your cart."), said)
        self.assertEqual(siri.task_receipt(999), "I don't have a task 999.")

    def test_a_pause_said_runs_through_task_control(self):
        tid = self.queue_job("write a note in the notes app in the background")
        with mock.patch.object(agent, "stop_job") as stopped:
            plan = siri.prepare_task_steps(json.loads(json.dumps(siri.from_table(f"pause task {tid}"))))
        self.assertEqual(plan["say"], f"Paused task {tid}. Say carry on with task {tid} when you want it.")
        stopped.assert_called_once_with(tid)
        self.assertTrue(self.store.paused(tid))
