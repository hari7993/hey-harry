"""Every row of the Settings tab belongs to one of its cards (31 October 2026: a row added without its number in the
parts table, assistant_ui._build_settings, raised KeyError as her window was built, and she crashed at every start
till her keeper gave up). Read from the source, as building the window needs a screen."""
import os
import re
import unittest

from tests.support import siri  # noqa: F401  first: temp APPDATA and the tripwires

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Rows(unittest.TestCase):
    def test_every_settings_row_is_in_a_card(self):
        src = open(os.path.join(HERE, "assistant_ui.py"), encoding="utf-8").read()
        start = src.index("def _build_settings(self)")
        end = src.index("\n    def ", start + 10)
        body = src[start:end]
        parts = body[body.index("parts = ("):body.index("cards, where, form")]
        listed = {int(n) for n in re.findall(r"\b(\d+)\b", re.sub(r'"[^"]*"', "", parts))}
        used = {int(n) for n in re.findall(r"\brow\((\d+),", body)}
        self.assertEqual(used - listed, set(), f"rows with no card: {sorted(used - listed)}")


if __name__ == "__main__":
    unittest.main()
