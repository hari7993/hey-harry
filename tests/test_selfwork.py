"""How she knows herself, builds into herself and heals herself (selfwork.py, 29 October 2026): what she knows of her
parts read from her code, the model a build thinks with, what a build's agent may run and edit, faults kept and fixed
once, a build put in only where her code's as it was and taken out again, a whole build in a copy with a stand-in
agent and stand-in tests, her keeper starting her again or putting a build back, and what's said about it. Nothing
here runs OpenCode, her real tests or the real app: temp git folders, fakes and a fake clock stand in."""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

from tests.support import siri

import coder
import cues
import selfwork
import settings
import toolbox


def run(*args, cwd):
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True)


def repo(files):
    """A git folder with files committed, and its commit."""
    folder = tempfile.mkdtemp(prefix="heyharry-self-")
    run("init", "-q", cwd=folder)
    run("config", "user.email", "t@t", cwd=folder)
    run("config", "user.name", "t", cwd=folder)
    run("config", "core.autocrlf", "false", cwd=folder)
    write(folder, files)
    run("add", "-A", cwd=folder)
    run("commit", "-q", "-m", "base", cwd=folder)
    return folder, subprocess.run(["git", "-C", folder, "rev-parse", "HEAD"], capture_output=True,
                                  text=True).stdout.strip()


def write(folder, files):
    for name, text in files.items():
        path = os.path.join(folder, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)


def read(folder, name):
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


TESTS = 'from tests.support import siri\nimport unittest\n\n\nclass T(unittest.TestCase):\n    def test_a(self):\n' \
        '        pass\n\n    def test_b(self):\n        pass\n'


class Place(unittest.TestCase):
    """Her code in a temp git folder, and her own data in a temp folder."""

    def setUp(self):
        self.code, self.base = repo({"siri.py": '"""Her voice loop."""\nX = 1\n', "app.py": '"""Her keeper."""\n',
                                     "tests/__init__.py": "", "tests/test_x.py": TESTS})
        self.data = tempfile.mkdtemp(prefix="heyharry-selfdata-")
        self.addCleanup(shutil.rmtree, self.code, True)
        self.addCleanup(shutil.rmtree, self.data, True)
        paths = {"HERE": self.code, "LOCAL": self.data, "BUILDS": os.path.join(self.data, "builds"),
                 "BUILT": os.path.join(self.data, "built.jsonl"), "FAULTS": os.path.join(self.data, "faults.jsonl"),
                 "PENDING": os.path.join(self.data, "pending.json"),
                 "TAKEN_OUT": os.path.join(self.data, "taken_out.json"), "LOG": os.path.join(self.data, "h.log")}
        for name, value in paths.items():
            patch = mock.patch.object(selfwork, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.dict(selfwork.NOTED, {}, clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.dict(selfwork.STATE, {"heal": None, "building": None, "say": None, "restart": None})
        patch.start()
        self.addCleanup(patch.stop)


class Knowing(unittest.TestCase):
    def test_she_knows_her_parts_from_her_own_code(self):
        found = dict(selfwork.parts())
        self.assertTrue(found["camera.py"].startswith("Her eyes on you"))
        self.assertTrue(found["selfwork.py"].startswith("How she knows herself"))
        self.assertNotIn("test_cues.py", found)
        text = selfwork.knowledge("how does your camera work")
        self.assertIn("Your parts", text)
        self.assertIn("- camera.py: Her eyes on you", text)
        self.assertIn("camera", text.split("Your steps")[1])  # what she can plan
        self.assertIn("about_me", text)
        self.assertIn("Models: answers", text)
        self.assertGreater(selfwork.tests_count(), 1000)

    def test_a_question_brings_its_parts_in_full(self):
        short = selfwork.knowledge("")
        full = selfwork.knowledge("tell me about your claps")
        line = lambda text: next(l for l in text.splitlines() if l.startswith("- claps.py"))
        self.assertGreater(len(line(full)), len(line(short)))

    def test_her_steps_are_in_the_registry_and_the_planner_sees_them_only_for_words_about_her(self):
        self.assertEqual(toolbox.get("about_me").effect, "info")
        improve = toolbox.get("improve")
        self.assertEqual(improve.effect, "acts")
        self.assertTrue(improve.confirm)  # planned after a read or without her name: asked about first
        self.assertEqual(selfwork.prompt_block("open spotify"), "")
        self.assertIn('{"do":"improve"', selfwork.prompt_block("can you build a feature into yourself"))
        self.assertIn("Your parts", toolbox.get("about_me").handler({"ask": "what can you do"})["about_me"])

    def test_docline_is_the_first_paragraph(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        write(folder, {"m.py": '"""One thing, said\nover two lines.\n\nMore after."""\nimport os\n', "n.py": "x = 1\n"})
        self.assertEqual(selfwork.docline(os.path.join(folder, "m.py")), "One thing, said over two lines.")
        self.assertEqual(selfwork.docline(os.path.join(folder, "n.py")), "")


class Models(unittest.TestCase):
    def test_the_model_picked_to_build_with_as_opencode_names_it_with_its_key(self):
        keys = {"ANTHROPIC_API_KEY": "sk-ant-test", "OPENCODE_ZEN_API_KEY": ""}
        with mock.patch("secrets_store.get_secret", lambda name: keys.get(name, "")):
            self.assertEqual(selfwork.for_opencode("anthropic/claude-opus-5-5"),
                             ("anthropic/claude-opus-5-5", {"ANTHROPIC_API_KEY": "sk-ant-test"}))
            self.assertEqual(selfwork.for_opencode("big-pickle"), ("opencode/big-pickle", {}))
            self.assertEqual(selfwork.for_opencode("together/meta/llama-4")[0], "togetherai/meta/llama-4")
            self.assertEqual(selfwork.for_opencode("kilo/nvidia/nemotron:free"), (None, {}))  # not in OpenCode
            # and in OpenCode's own settings, where it outranks a key OpenCode keeps that's run out
            self.assertEqual(selfwork.opencode_config("anthropic/claude-opus-5-5"),
                             {"provider": {"anthropic": {"options": {"apiKey": "sk-ant-test"}}}})
            self.assertEqual(selfwork.opencode_config("big-pickle"), {})  # no Zen key saved here

    def test_the_answer_model_till_one_is_picked(self):
        with mock.patch.dict(settings._load(), {"builder_model": "", "llm_model": "anthropic/claude-haiku-5-5"}):
            self.assertEqual(selfwork.builder_model(), "anthropic/claude-haiku-5-5")
        with mock.patch.dict(settings._load(), {"builder_model": "anthropic/claude-opus-5-5"}):
            self.assertEqual(selfwork.builder_model(), "anthropic/claude-opus-5-5")


class Guards(unittest.TestCase):
    def test_a_build_runs_her_tests_unasked_and_nothing_else(self):
        venv = r'"C:\Users\h\hey-jev\.venv\Scripts\python.exe"'
        for ok in ("python -m unittest discover -s tests -t .", f"{venv} -m unittest tests.test_cues",
                   "python -m py_compile siri.py", "python.exe -m unittest tests.test_x.T.test_a",
                   "ls", "ls -la tests", "dir", "cat siri.py", "grep -n def cues.py", "git status", "git diff",
                   "Get-ChildItem -Recurse", "find . -name *.py", 'grep -rn "sysinfo" --include=*.py . | head -50',
                   "ls tests | grep -i sys", 'grep -n "quick\\|toolbox.register" cues.py extras.py | head -80',
                   'ls tests | grep -i -E "sysinfo|cues|extras|dream"',
                   f"{venv} -m unittest tests.test_routing 2>&1 | tail -20", "git status && git diff",
                   "sed -n '15,60p' tests/test_routing.py", "ls tests; cat AGENTS.md"):
            self.assertTrue(selfwork.may_run(ok), ok)
        for no in ('python -c "import os; os.system(\'del x\')"', "python -m pip install requests",
                   "python -m unittest && del siri.py", "pip install requests", "powershell -c ls",
                   r"C:\Temp\python.exe -m unittest", "python -m unittest | tee out.txt", "git push",
                   "git checkout .", "git diff --output=x.txt", "find . -delete", "find . -name x -delete", "cat x > y", "rm siri.py",
                   "del siri.py", "curl https://example.com", "ls | del x", "cat siri.py | python -",
                   "python -m unittest > out.txt", "git status && git push", "sed -i s/a/b/ siri.py",
                   "python -m unittest &", "cat $(ls)", "ls && rm -rf ."):
            self.assertFalse(selfwork.may_run(no), no)

    def test_what_puts_her_back_is_never_edited(self):
        folder = os.path.abspath("C:/copy")
        for no in ("app.py", "./selfwork.py", "tests\\support.py", "tests/test_selfwork.py", "requirements.txt",
                   os.path.join(folder, "app.py"), "../siri.py", "D:/elsewhere/siri.py"):
            self.assertTrue(selfwork.protected(no, folder), no)
        for ok in ("siri.py", "tests/test_cues.py", os.path.join(folder, "cues.py"), ".github/x.yml"):
            self.assertFalse(selfwork.protected(ok, folder), ok)

    def test_a_job_lets_her_tests_run_and_turns_down_an_edit_it_mustnt_make(self):
        job = coder.Job("C:/copy", "x", may_run=selfwork.may_run, may_edit=lambda p: not selfwork.protected(p, "C:/copy"))
        run_tests = {"toolCall": {"kind": "execute", "rawInput": {"command": "python -m unittest tests.test_x"}}}
        self.assertTrue(job.permission(run_tests))
        pip = {"toolCall": {"kind": "execute", "rawInput": {"command": "pip install x"}}}
        self.assertFalse(job.permission(pip))  # nobody to ask: refused and listed
        self.assertTrue(job.permission({"toolCall": {"kind": "edit", "title": "cues.py",
                                                     "rawInput": {"filePath": "C:/copy/cues.py"}}}))
        self.assertFalse(job.permission({"toolCall": {"kind": "edit", "title": "Edit app.py"}}))
        self.assertFalse(job.permission({"toolCall": {"kind": "edit", "title": "x",
                                                      "locations": [{"path": "C:/copy/selfwork.py"}]}}))
        self.assertEqual(len(job.refused), 3)

    def test_a_key_in_the_code_is_found_and_code_about_keys_isnt(self):
        self.assertTrue(selfwork._secret_in('KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz"'))
        self.assertTrue(selfwork._secret_in("token = 'ghp_abcdefghijklmnopqrstu'"))
        self.assertFalse(selfwork._secret_in("token = settings.get('token')\napi_key = providers.key(p)\n"))

    def test_failing_tests_read_from_what_unittest_says(self):
        out = (b"FAIL: test_a (tests.test_x.T.test_a)\nERROR: test_b (tests.test_x.T.test_b) (gate=True)\n"
               b"ERROR: test_y (unittest.loader._FailedTest.test_y)\nRan 3 tests in 0.1s\nFAILED (failures=1)\n")
        done = subprocess.CompletedProcess([], 1, stdout=b"", stderr=out)
        with mock.patch.object(selfwork.subprocess, "run", return_value=done):
            self.assertEqual(selfwork.run_tests("C:/copy"), {"tests.test_x.T.test_a", "tests.test_x.T.test_b",
                                                              "unittest.loader._FailedTest.test_y"})
        broken = subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"SyntaxError: invalid syntax\n")
        with mock.patch.object(selfwork.subprocess, "run", return_value=broken):
            self.assertEqual(selfwork.run_tests("C:/copy"), {"the tests didn't finish"})
        with mock.patch.object(selfwork.subprocess, "run", side_effect=subprocess.TimeoutExpired("x", 1)):
            self.assertEqual(selfwork.run_tests("C:/copy"), {"the tests didn't finish"})


class Faults(Place):
    def test_a_fault_of_her_own_code_is_kept_and_fixed_once(self):
        healed = []
        selfwork.STATE["heal"] = lambda *a: healed.append(a)
        with mock.patch.object(selfwork, "HERE", os.path.dirname(cues.__file__)):
            try:
                cues.said({})  # a KeyError in cues.py
            except KeyError as exc:
                self.assertTrue(selfwork.fault(exc, "a turn", "answering 'hi'"))
                self.assertTrue(selfwork.fault(exc, "a turn"))  # again straight after: not written down again
                self.assertEqual(selfwork.faults()[0]["count"], 1)
                selfwork.NOTED["KeyError in cues.py said()"] -= selfwork.NOTE_EVERY  # a minute on
                self.assertTrue(selfwork.fault(exc, "a turn", "answering 'hi'"))
            self.assertFalse(selfwork.fault(RuntimeError("Say which folder"), "a turn"))  # hers to say, not a fault
            try:
                {}["x"]  # raised here, in a test: not her code
            except KeyError as exc:
                self.assertFalse(selfwork.fault(exc))
        self.assertEqual(len(healed), 1)
        sig, trace, where, doing = healed[0]
        self.assertEqual(sig, "KeyError in cues.py said()")
        self.assertIn("Traceback", trace)
        self.assertEqual((where, doing), ("a turn", "answering 'hi'"))
        kept = selfwork.faults()
        self.assertEqual([(f["sig"], f["count"], f["state"]) for f in kept], [(sig, 2, "fixing")])
        selfwork.healed(sig, True)
        self.assertEqual(selfwork.faults()[0]["state"], "fixed")

    def test_no_more_than_a_few_fixes_a_day_and_none_with_healing_off(self):
        healed = []
        selfwork.STATE["heal"] = lambda *a: healed.append(a)
        for n in range(selfwork.HEALS_A_DAY + 2):
            selfwork._note(f"TypeError in x.py f{n}()", "trace", "a turn", "")
        self.assertEqual(len(healed), selfwork.HEALS_A_DAY)
        with mock.patch.dict(settings._load(), {"self_heal": False}):
            shutil.rmtree(self.data, True)
            selfwork._note("TypeError in y.py g()", "trace", "a turn", "")
        self.assertEqual(len(healed), selfwork.HEALS_A_DAY)

    def test_errors_no_one_caught_on_any_thread_are_looked_at(self):
        seen = []
        old = (selfwork.sys.excepthook, threading.excepthook)
        self.addCleanup(lambda: setattr(threading, "excepthook", old[1]))
        self.addCleanup(lambda: setattr(selfwork.sys, "excepthook", old[0]))
        with mock.patch.object(selfwork, "fault", lambda exc, where="", doing="": seen.append((type(exc), where))):
            threading.excepthook = lambda args: None  # what was there before: quiet here
            selfwork.watch(heal=lambda *a: None, say=lambda line: None)
            t = threading.Thread(target=lambda: {}["x"], name="cues")
            t.start()
            t.join()
        self.assertEqual(seen, [(KeyError, "thread cues")])


class PutIn(Place):
    def build(self, files, delete=()):
        """A build's copy at the base, with files written and delete deleted, committed: (folder, commit)."""
        folder = os.path.join(self.data, "copy")
        run("worktree", "add", "-q", "--detach", folder, self.base, cwd=self.code)
        self.addCleanup(lambda: subprocess.run(["git", "-C", self.code, "worktree", "remove", "--force", folder],
                                               capture_output=True))
        write(folder, files)
        for name in delete:
            os.remove(os.path.join(folder, name))
        run("add", "-A", cwd=folder)
        run("commit", "-q", "-m", "built", cwd=folder)
        return folder, subprocess.run(["git", "-C", folder, "rev-parse", "HEAD"], capture_output=True,
                                      text=True).stdout.strip()

    def test_in_where_her_code_is_as_it_was_and_out_again(self):
        folder, commit = self.build({"siri.py": '"""Her voice loop."""\nX = 2\n', "new.py": "Y = 1\n"},
                                    delete=["app.py"])
        files = selfwork.put_in(self.base, commit, folder)
        self.assertEqual(sorted(files), ["app.py", "new.py", "siri.py"])
        self.assertIn("X = 2", read(self.code, "siri.py"))
        self.assertEqual(read(self.code, "new.py"), "Y = 1\n")
        self.assertIsNone(read(self.code, "app.py"))
        selfwork.take_out({"base": self.base, "files": files})
        self.assertIn("X = 1", read(self.code, "siri.py"))
        self.assertIsNone(read(self.code, "new.py"))
        self.assertIn("Her keeper", read(self.code, "app.py"))

    def test_nothing_in_if_her_code_changed_meanwhile(self):
        folder, commit = self.build({"siri.py": "X = 2\n", "new.py": "Y = 1\n"})
        write(self.code, {"siri.py": "X = 'yours'\n"})
        with self.assertRaisesRegex(RuntimeError, "siri.py changed while I was building"):
            selfwork.put_in(self.base, commit, folder)
        self.assertEqual(read(self.code, "siri.py"), "X = 'yours'\n")
        self.assertIsNone(read(self.code, "new.py"))  # nothing went in

    def test_line_endings_alone_arent_a_change(self):
        folder, commit = self.build({"siri.py": "X = 2\n"})
        write(self.code, {"siri.py": '"""Her voice loop."""\r\nX = 1\r\n'})
        self.assertEqual(selfwork.put_in(self.base, commit, folder), ["siri.py"])

    def test_undo_the_last_build_only_while_its_files_are_as_it_left_them(self):
        self.assertFalse(selfwork.undo_last()[0])
        folder, commit = self.build({"siri.py": '"""Her voice loop."""\nX = 2\n'})
        files = selfwork.put_in(self.base, commit, folder)
        entry = {"id": "b1", "at": 1, "kind": "build", "what": "count to two", "base": self.base, "commit": commit,
                 "files": files, "state": "in"}
        selfwork._add_row(selfwork.BUILT, entry)
        write(self.code, {"siri.py": "changed by hand\n"})
        self.assertFalse(selfwork.undo_last()[0])
        write(self.code, {"siri.py": '"""Her voice loop."""\nX = 2\n'})
        ok, said = selfwork.undo_last()
        self.assertTrue(ok)
        self.assertIn("count to two", said)
        self.assertIn("X = 1", read(self.code, "siri.py"))
        self.assertEqual(selfwork.builds()[-1]["state"], "taken out")
        self.assertFalse(selfwork.undo_last()[0])  # once


class Building(Place):
    def setUp(self):
        super().setUp()
        self.asked, self.failing = [], {}

    def agent(self, changes):
        """A stand-in coding agent: each go writes the next of changes into the copy."""
        goes = iter(changes)

        def job(folder, prompt):
            self.asked.append(prompt)
            write(folder, next(goes, {}))
            return True, getattr(self, "agent_said", "I added a battery check.")
        return job

    def fake_tests(self, folder, only=()):
        kind = "before" if folder.endswith("-before") else "after"
        got = self.failing.get(kind, [set()])
        return got.pop(0) if len(got) > 1 else got[0]

    def go(self, changes, **kw):
        build = selfwork.Build("build yourself a battery check", model="anthropic/claude-opus-5-5",
                               job=self.agent(changes), tests=self.fake_tests, **kw)
        ok, said = build.run()
        return build, ok, said

    def test_built_in_a_copy_tested_and_put_in(self):
        build, ok, said = self.go([{"battery.py": '"""Battery."""\n', "tests/test_battery.py": TESTS}])
        self.assertTrue(ok, said)
        self.assertTrue(said.startswith("I added a battery check."))
        self.assertEqual(read(self.code, "battery.py"), '"""Battery."""\n')
        self.assertIn("AGENTS.md", self.asked[0])
        self.assertIn('"build yourself a battery check"', self.asked[0])
        pending = json.load(open(selfwork.PENDING, encoding="utf-8"))
        self.assertEqual(sorted(pending["files"]), ["battery.py", "tests/test_battery.py"])
        self.assertEqual(selfwork.builds()[-1]["state"], "in")
        self.assertEqual(os.listdir(selfwork.BUILDS), [])  # the copies gone
        self.assertIn(f"refs/heyharry/builds/{build.id}", subprocess.run(
            ["git", "-C", self.code, "for-each-ref", "refs/heyharry/builds"], capture_output=True, text=True).stdout)

    def test_cut_off_words_are_said_as_the_files_it_changed(self):
        self.agent_said = "Now the whole suite:"
        _, ok, said = self.go([{"battery.py": "x = 1\n"}])
        self.assertTrue(ok)
        self.assertEqual(said, "I changed 1 file: battery.py.")

    def test_what_fails_that_didnt_goes_back_to_it(self):
        broken = "tests.test_x.T.test_a"
        self.failing = {"before": [{"tests.test_x.T.old"}], "after": [{broken, "tests.test_x.T.old"}, {broken},
                                                                       {"tests.test_x.T.old"}]}
        _, ok, said = self.go([{"battery.py": "x = 1\n"}, {"battery.py": "x = 2\n"}])
        self.assertTrue(ok, said)  # a test that failed before it doesn't count
        self.assertEqual(len(self.asked), 2)
        self.assertIn(broken, self.asked[1])
        self.assertIn("without weakening or deleting any test", self.asked[1])

    def test_still_failing_after_its_goes_and_nothing_changes(self):
        self.failing = {"after": [{"tests.test_x.T.test_a"}]}
        _, ok, said = self.go([{"battery.py": "x = 1\n"}] * selfwork.ROUNDS)
        self.assertFalse(ok)
        self.assertIn("still fail", said)
        self.assertEqual(len(self.asked), selfwork.ROUNDS)
        self.assertIsNone(read(self.code, "battery.py"))
        self.assertFalse(os.path.exists(selfwork.PENDING))

    def test_a_test_that_only_fails_sometimes_isnt_its(self):
        self.failing = {"after": [{"tests.test_x.T.test_a"}, set()]}  # the rerun of it alone passes
        _, ok, said = self.go([{"battery.py": "x = 1\n"}])
        self.assertTrue(ok, said)

    def test_not_taken_if_it_touches_what_puts_her_back_or_takes_tests_away_or_has_a_key(self):
        for changes, why in (({"app.py": "broken\n"}, "app.py"), ({"tests/test_x.py": "import unittest\n"}, "tests away"),
                             ({"k.py": 'K = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz"\n'}, "key")):
            with self.subTest(why):
                shutil.rmtree(selfwork.BUILDS, True)
                _, ok, said = self.go([changes])
                self.assertFalse(ok)
                self.assertIn(why if why != "tests away" else "took some of my tests away", said)
                self.assertIn("Nothing in me changed", said)
                self.assertIn("Her keeper", read(self.code, "app.py"))
        self.assertIsNone(read(self.code, "k.py"))

    def test_nothing_changed_nothing_built_and_one_at_a_time(self):
        _, ok, said = self.go([{}, {}])
        self.assertFalse(ok)
        self.assertIn("didn't change anything", said)
        self.assertEqual(len(self.asked), 2)  # told once more to make the change
        self.assertIn("Make the change now", self.asked[1])
        shutil.rmtree(selfwork.BUILDS, True)
        _, ok, said = self.go([{}, {"battery.py": "x = 1\n"}])
        self.assertTrue(ok, said)  # and it did
        selfwork.STATE["building"] = object()
        _, ok, said = self.go([{"battery.py": "x = 1\n"}])
        self.assertFalse(ok)
        self.assertIn("already building", said)

    def test_stopped_part_way_changes_nothing(self):
        stop = []
        # Stop pressed while the agent works: the first look at it, before its go, says carry on
        _, ok, said = self.go([{"battery.py": "x = 1\n"}], cancelled=lambda: bool(stop.append(1)) or len(stop) > 1)
        self.assertFalse(ok)
        self.assertIn("Stopped", said)
        self.assertIsNone(read(self.code, "battery.py"))
        self.assertFalse(os.path.exists(selfwork.PENDING))


class Keeper(Place):
    def keep(self, codes, before=None):
        """Her keeper over a run of exit codes: (what it returned, the commands it ran, what it told)."""
        ran, told, now = [], [], [1000.0]
        codes = list(codes)

        def run_her(cmd):
            ran.append(cmd)
            now[0] += 5
            code = codes.pop(0)
            if before:
                before(len(ran), code)
            return code
        with mock.patch.object(selfwork, "_may_heal", lambda rows, now: True):
            got = selfwork.keep(["--startup"], run=run_her, clock=lambda: now[0], sleep=lambda s: now.__setitem__(
                0, now[0] + s), tell=told.append)
        return got, ran, told

    def crash(self, n, code):  # what her log has when she crashes
        if code not in (0, selfwork.RESTART):
            with open(selfwork.LOG, "a", encoding="utf-8") as f:
                f.write("Traceback (most recent call last):\n  File \"siri.py\", line 1\nKeyError: 'x'\n")

    def test_quit_is_quit_and_a_restart_starts_her_again(self):
        got, ran, _ = self.keep([selfwork.RESTART, 0])
        self.assertEqual(got, 0)
        self.assertEqual(len(ran), 2)
        self.assertIn("--child", ran[0])
        self.assertIn("--startup", ran[0])
        self.assertNotIn("--startup", ran[1])  # only the first start is as you signed in

    def test_stopped_from_outside_stays_stopped(self):
        got, ran, _ = self.keep([1])
        self.assertEqual((got, len(ran)), (1, 1))

    def test_a_crash_starts_her_again_and_is_kept_for_her_to_fix(self):
        got, ran, _ = self.keep([1, 0], before=self.crash)
        self.assertEqual((got, len(ran)), (0, 2))
        crash = selfwork.faults()[-1]
        self.assertTrue(crash["crash"])
        self.assertEqual(crash["state"], "new")  # she fixes it once she's up, not the keeper
        self.assertIn("KeyError", crash["sig"])

    def test_a_build_she_wont_start_with_is_taken_out(self):
        selfwork._write_json(selfwork.PENDING, {"id": "b1", "what": "a battery check", "kind": "build",
                                                "base": "x", "files": ["battery.py"]})
        with mock.patch.object(selfwork, "take_out", return_value=["battery.py"]) as taken:
            got, ran, _ = self.keep([1, 0], before=self.crash)
        self.assertEqual(got, 0)
        taken.assert_called_once()
        self.assertFalse(os.path.exists(selfwork.PENDING))
        out = json.load(open(selfwork.TAKEN_OUT, encoding="utf-8"))
        self.assertEqual(out["what"], "a battery check")
        self.assertIn("KeyError", out["trace"])

    def test_four_crashes_in_ten_minutes_and_it_stops_and_says_so(self):
        got, ran, told = self.keep([1] * 6, before=self.crash)
        self.assertEqual((got, len(ran)), (1, 4))
        self.assertIn("keeps stopping", told[0])


class Starting(Place):
    def test_a_build_taken_out_is_said_and_built_once_more(self):
        said, queued = [], []
        selfwork._write_json(selfwork.TAKEN_OUT, {"id": "b1", "what": "a battery check", "kind": "build",
                                                  "trace": "KeyError"})
        selfwork.started(said.append, heal=lambda *a: None, queue=lambda *a: queued.append(a))
        self.assertIn("stopped me starting", said[0])
        self.assertEqual(queued[0][:3], ("build", "a battery check", "KeyError"))
        self.assertTrue(selfwork.Build("x", doing=queued[0][3], model="").again)  # and not again after that
        self.assertFalse(os.path.exists(selfwork.TAKEN_OUT))
        selfwork._write_json(selfwork.TAKEN_OUT, {"what": "it", "kind": "build", "again": True})
        selfwork.started(said.append, heal=lambda *a: None, queue=lambda *a: queued.append(a))
        self.assertEqual(len(queued), 1)

    def test_a_build_in_is_said_and_counts_as_started_after_a_while(self):
        said = []
        selfwork._write_json(selfwork.PENDING, {"id": "b2", "what": "a battery check", "kind": "build"})
        with mock.patch.object(selfwork, "TRIAL", 0.05):
            selfwork.started(said.append, heal=lambda *a: None)
            time.sleep(0.3)
        self.assertEqual(said, ["I'm back, and it's in: a battery check."])
        self.assertFalse(os.path.exists(selfwork.PENDING))

    def test_a_crash_is_said_and_fixed(self):
        said, healed = [], []
        selfwork._note("crash: KeyError: 'x'", "Traceback...", "her start", "", crash=True, heal_now=False)
        selfwork.started(said.append, heal=lambda *a: healed.append(a))
        self.assertIn("started again", said[0])
        self.assertEqual(healed[0][0], "crash: KeyError: 'x'")
        self.assertEqual(selfwork.faults()[-1]["state"], "fixing")
        selfwork.started(said.append, heal=lambda *a: healed.append(a))
        self.assertEqual(len(healed), 1)  # once


class Said(Place):
    def say(self, words, gate=True):
        self.queued = []
        return selfwork.quick(words, siri.plain, gate, queue=lambda *a: self.queued.append(a))

    def test_asking_for_a_feature_builds_it_in_the_background(self):
        for words in ("build yourself a feature that reads my battery every hour",
                      "add a feature to close WhatsApp when I say focus", "improve yourself so you answer faster",
                      "give yourself the ability to read PDFs aloud", "upgrade yourself to read my calendar"):
            plan = self.say(words)
            self.assertIn("build that into myself", plan["say"], words)
            self.assertEqual(self.queued, [("build", words, "", "")], words)
        for words in ("make yourself quieter", "teach yourself to open Spotify", "build me a website",
                      "add milk to my list", "add a reminder for 5 pm"):
            self.assertIsNone(self.say(words), words)
        self.assertIsNone(self.say("build yourself a feature to read my battery", gate="cold"))  # never across the room

    def test_what_shes_built_her_faults_and_fixing_them(self):
        self.assertIn("Nothing yet", self.say("what have you built for yourself")["say"])
        selfwork._add_row(selfwork.BUILT, {"id": "b1", "at": time.time(), "kind": "build", "what": "a battery check",
                                           "state": "in"})
        self.assertIn("built a battery check", self.say("what have you built")["say"])
        self.assertIn("All good", self.say("any errors lately")["say"])
        self.assertIn("nothing wrong", self.say("fix yourself")["say"])
        selfwork._note("TypeError in claps.py _judge()", "trace", "a turn", "", heal_now=False)
        self.assertIn("not yet: TypeError in claps.py _judge()", self.say("any errors lately")["say"])
        self.assertIn("I'm on it", self.say("fix yourself")["say"])
        self.assertEqual(self.queued[0][:2], ("fix", "Fix: TypeError in claps.py _judge()"))

    def test_undo_takes_the_last_build_out_and_restarts(self):
        restarts = []
        selfwork.STATE["restart"] = lambda: restarts.append(1)
        with mock.patch.object(selfwork, "undo_last", return_value=(True, "Okay, I've taken out \"it\".")):
            self.assertIn("taken out", self.say("undo your last build")["say"])
        self.assertEqual(restarts, [1])
        with mock.patch.object(selfwork, "undo_last", return_value=(False, "I haven't built anything.")):
            self.say("roll back your last change")
        self.assertEqual(restarts, [1])


class Wiring(unittest.TestCase):
    def test_a_planned_build_is_queued_as_her_task(self):
        made = []
        with mock.patch.object(siri.TASK_STORE, "create", lambda desc, kind, payload, **kw: made.append(
                (desc, kind, payload)) or 7):
            plan = siri.prepare_task_steps({"steps": [{"do": "improve", "what": "a battery check"}], "say": ""})
        self.assertEqual(made[0][:2], ("Build: a battery check", "self"))
        self.assertEqual(made[0][2]["kind"], "build")
        self.assertEqual(plan["steps"], [{"do": "task_queued", "id": 7}])
        self.assertIn("building that into myself", plan["say"])
        self.assertIn("self", siri.SLOW_TASKS)
        self.assertIn("self", siri.tasking.KINDS)

    def test_a_fault_is_fixed_as_a_task_of_its_own(self):
        made = []
        with mock.patch.object(siri.TASK_STORE, "create", lambda desc, kind, payload, **kw: made.append(
                (desc, kind, payload)) or 8):
            siri.heal_me("KeyError in cues.py said()", "Traceback", "a turn", "answering 'hi'")
        desc, kind, payload = made[0]
        self.assertEqual((kind, payload["kind"], payload["sig"]), ("self", "fix", "KeyError in cues.py said()"))
        self.assertIn("Traceback", payload["trace"])


if __name__ == "__main__":
    unittest.main()
