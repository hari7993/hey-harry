"""Claude Code in her island (coding_agents.py, island_plugins.Agents; 31 October 2026, after Glance's notch): its
hook asks her island and answers Claude Code only with what the island said, says nothing while she isn't running,
and her hooks go in and out of Claude Code's settings leaving the rest as it was."""
import io
import json
import os
import threading
import time
import unittest
from unittest import mock

from tests.support import siri  # noqa: F401  first: temp APPDATA and the tripwires, before anything of hers

import coding_agents as agents
import island_plugins as plugins

def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


ASK = {"hook_event_name": "PermissionRequest", "tool_name": "Bash", "tool_input": {"command": "rm -rf dist/"},
       "cwd": "C:\\Work\\glance-web", "session_id": "s1"}


class Hook(unittest.TestCase):
    def setUp(self):
        for name in os.listdir(agents.folder()):
            os.remove(os.path.join(agents.folder(), name))

    def run_hook(self, event):
        out = io.StringIO()
        agents.main(io.StringIO(json.dumps(event)), out)
        return out.getvalue()

    def test_never_your_real_settings_under_the_tests(self):
        for agent in agents.AGENTS:
            self.assertTrue(agents.settings_path(agent).startswith(agents.folder()), agent)

    def test_codex_asks_too_and_cursor_only_says_its_done(self):
        agents.touch()

        def island():
            for _ in range(100):
                qs = agents.questions()
                if qs:
                    self.assertEqual(qs[0]["agent"], "Codex")
                    agents.answer(qs[0]["id"], True)
                    return
                agents.touch()
                time.sleep(0.05)
        t = threading.Thread(target=island)
        t.start()
        out = io.StringIO()
        agents.main(io.StringIO(json.dumps(ASK)), out, ["codex"])
        t.join(5)
        self.assertEqual(json.loads(out.getvalue())["hookSpecificOutput"]["decision"], {"behavior": "allow"})
        out = io.StringIO()
        agents.main(io.StringIO(json.dumps({"hook_event_name": "stop", "status": "completed",
                                            "workspace_roots": ["C:\\Work\\shop"]})), out, ["cursor"])
        self.assertEqual(out.getvalue(), "{}")  # Cursor and Codex want JSON from a stop
        out = io.StringIO()
        agents.main(io.StringIO(json.dumps({"hook_event_name": "beforeShellExecution", "command": "ls"})), out,
                    ["cursor"])
        self.assertEqual(out.getvalue(), "")  # never a permission for Cursor
        said = agents.notes()
        self.assertEqual([(n["agent"], n["kind"], n["project"]) for n in said], [("Cursor", "done", "shop")])

    def test_she_isnt_running_so_claude_asks_you_itself(self):
        self.assertEqual(self.run_hook(ASK), "")
        self.assertEqual(agents.questions(), [])

    def test_the_island_answers_and_only_that_is_said(self):
        agents.touch()

        def island():
            for _ in range(100):
                qs = agents.questions()
                if qs:
                    self.assertEqual((qs[0]["project"], qs[0]["command"]), ("glance-web", "rm -rf dist/"))
                    agents.answer(qs[0]["id"], False)
                    return
                agents.touch()
                time.sleep(0.05)
        t = threading.Thread(target=island)
        t.start()
        out = json.loads(self.run_hook(ASK))
        t.join(5)
        decision = out["hookSpecificOutput"]["decision"]
        self.assertEqual((out["hookSpecificOutput"]["hookEventName"], decision["behavior"]),
                         ("PermissionRequest", "deny"))
        self.assertEqual(agents.questions(), [])  # tidied away

    def test_no_answer_in_time_says_nothing(self):
        agents.touch()
        self.assertIsNone(agents.ask(ASK, wait=0.3, step=0.05))

    def test_waiting_done_and_the_command_running(self):
        agents.touch()
        self.run_hook({"hook_event_name": "Notification", "message": "Claude needs your permission", "cwd": "C:\\x"})
        self.run_hook({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "npm test"},
                       "cwd": "C:\\x"})
        self.run_hook({"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}, "cwd": "C:\\x"})
        self.run_hook({"hook_event_name": "Stop", "cwd": "C:\\x"})
        self.assertEqual([n["kind"] for n in agents.notes()], ["waiting", "running", "done"])
        self.assertEqual(agents.notes(), [])  # each once


class Settings(unittest.TestCase):
    def test_cursor_and_kiro_files_in_and_out(self):
        path = os.path.join(agents.folder(), "cursor-case.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "hooks": {"stop": [{"command": "notify.exe"}]}}, f)
        agents.connect(True, path, "cursor")
        got = load(path)
        self.assertEqual(len(got["hooks"]["stop"]), 2)
        self.assertIn("cursor", got["hooks"]["afterShellExecution"][0]["command"])
        self.assertNotIn("beforeShellExecution", got["hooks"])  # never asked about every command
        agents.connect(False, path, "cursor")
        self.assertEqual(load(path), {"version": 1, "hooks": {"stop": [{"command": "notify.exe"}]}})
        kiro = os.path.join(agents.folder(), "kiro-case", "harry-island.json")
        agents.connect(True, kiro, "kiro")
        self.assertEqual([h["trigger"] for h in load(kiro)["hooks"]], ["PreToolUse", "Stop"])
        self.assertTrue(agents.connected("kiro", kiro))
        agents.connect(False, kiro, "kiro")
        self.assertFalse(os.path.exists(kiro))

    def test_connect_all_does_each_and_takes_them_out(self):
        self.assertEqual(agents.connect_all(True), list(agents.AGENTS))
        self.assertTrue(all(agents.connected(a) for a in agents.AGENTS))
        agents.connect_all(False)
        self.assertFalse(any(agents.connected(a) for a in agents.AGENTS))

    def test_in_and_out_leaving_the_rest_as_it_was(self):
        path = os.path.join(agents.folder(), "claude-settings-case.json")
        mine = {"model": "opus", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "say done"}]}]}}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(mine, f)
        self.assertTrue(agents.connect(True, path))
        self.assertTrue(agents.connected(path=path))
        got = load(path)
        self.assertEqual(got["model"], "opus")
        self.assertEqual(len(got["hooks"]["Stop"]), 2)  # yours and hers
        self.assertEqual(got["hooks"]["PermissionRequest"][0]["hooks"][0]["timeout"], int(agents.WAIT) + 10)
        agents.connect(True, path)  # again: still once
        self.assertEqual(len(load(path)["hooks"]["Stop"]), 2)
        self.assertTrue(os.path.exists(path + ".harry-backup"))
        agents.connect(False, path)
        self.assertEqual(load(path), mine)
        self.assertFalse(agents.connected(path=path))

    def test_a_settings_file_it_cant_read_is_left_alone(self):
        path = os.path.join(agents.folder(), "claude-settings-broken.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not json")
        with self.assertRaises(ValueError):
            agents.connect(True, path)
        self.assertEqual(read(path), "{not json")


class Plugin(unittest.TestCase):
    def setUp(self):
        for name in os.listdir(agents.folder()):
            os.remove(os.path.join(agents.folder(), name))

    def test_a_question_is_a_card_with_a_careful_approve(self):
        host = mock.Mock()
        p = plugins.Agents(host)
        self.assertFalse(p.default_on)  # off till you turn it on
        p.start()
        self.addCleanup(p.stop)
        base = os.path.join(agents.folder(), "abc123")
        agents._write(base + ".ask.json", dict(agents.what_of(ASK), id="abc123", at=time.time()))
        p.poll(time.time())
        kind, pid, act = host.post.call_args[0][0]
        row = act.data["rows"][0]
        self.assertEqual((kind, pid, row["state"]), ("live", "agents", "waiting_yes"))
        self.assertEqual([(b["name"], b.get("careful", False)) for b in row["buttons"]],
                         [("deny", False), ("approve", True)])
        p.command("approve", "abc123")
        self.assertEqual(agents._read(base + ".answer.json"), {"allow": True})


if __name__ == "__main__":
    unittest.main()
