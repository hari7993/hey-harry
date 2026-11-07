"""Building into herself and healing herself taken out (7 November 2026, the owner: it didn't work well, and a build's
OpenCode and copy of her code cost memory and disk): "build yourself..." and "fix yourself" say so and queue nothing,
her faults aren't watched for or recorded, the planner isn't offered a build, Settings has no rows for them, and a
build task left from before is finished as off, never run. Her keeper, "what have you built?" and "undo your last
build" stay (selfwork.py, untouched)."""
import os
import unittest
from unittest import mock

from tests.support import siri  # first: temp APPDATA and the tripwires

import settings

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def source(name):
    return open(os.path.join(HERE, name), encoding="utf-8").read()


class Off(unittest.TestCase):
    def test_asked_to_build_or_fix_herself_she_says_its_gone_and_queues_nothing(self):
        with mock.patch.object(siri.TASK_STORE, "create", lambda *a, **k: self.fail("a build was queued")):
            for words in ("build yourself a way to read my battery out every hour", "fix yourself"):
                with self.subTest(words=words):
                    plan = siri.quick(words)
                    self.assertEqual(plan, {"steps": [], "say": siri.NO_SELF_BUILD})

    def test_what_stays_still_answers(self):
        plan = siri.quick("what have you built")
        self.assertEqual(plan["steps"], [])
        self.assertIn("Nothing yet", plan["say"])

    def test_nothing_reaches_a_build_or_a_fix(self):
        src = source("siri.py")
        for gone in ("selfwork.prompt_block(", "selfwork.fault(", "selfwork.watch(", "selfwork.started(",
                     "selfwork.Build("):
            self.assertNotIn(gone, src, gone)
        self.assertNotIn("selfwork", source("assistant_ui.py"))
        for key in ("self_heal", "builder_model"):
            self.assertNotIn(key, settings.DEFAULTS)
        self.assertNotIn('row(21, "Build herself"', source("assistant_ui.py"))
        self.assertNotIn('row(22, "Heal herself"', source("assistant_ui.py"))


if __name__ == "__main__":
    unittest.main()
