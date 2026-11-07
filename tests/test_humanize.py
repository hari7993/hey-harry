"""Her lines without the tells of machine writing (humanize.py, 7 November 2026, the owner's ask, after blader's
humanizer): the chatbot's leftovers, run-ups, deep-sounding padding, the words nobody says, "not just X but Y" and
stacked qualifiers taken out of what she says, in code, with what she means left as it was. Nothing here goes
online."""
import unittest

from tests.support import siri  # first: temp APPDATA and the tripwires

import humanize


class Plain(unittest.TestCase):
    def check(self, pairs):
        for before, after in pairs:
            with self.subTest(before=before):
                self.assertEqual(humanize.plain(before), after)

    def test_the_chatbots_hello_and_goodbye_go(self):
        self.check((("Certainly! It's five o'clock.", "It's five o'clock."),
                    ("Great question! Tokyo is the capital of Japan.", "Tokyo is the capital of Japan."),
                    ("Night light's on. I hope this helps!", "Night light's on."),
                    ("It's 26 degrees. Let me know if you need anything else.", "It's 26 degrees."),
                    ("Done. Is there anything else I can help you with?", "Done."),
                    ("Of course, I'd be happy to help. Opening Notepad now.", "Opening Notepad now."),
                    ("Sure, one sec.", "Sure, one sec.")))  # hers, and human

    def test_the_run_up_and_the_padding_go(self):
        self.check((("Here's the thing: your battery is at 9 percent.", "Your battery is at 9 percent."),
                    ("Honestly, the second one is cheaper.", "The second one is cheaper."),
                    ("Look at the screen first.", "Look at the screen first."),  # an order, not a run-up
                    ("At the end of the day, the Pixel is the better buy.", "The Pixel is the better buy."),
                    ("It's worth noting that the shop closes at nine.", "The shop closes at nine."),
                    ("As of my last update, the rate was 83 rupees.", "The rate was 83 rupees."),
                    ("It could potentially rain later.", "It could rain later.")))

    def test_the_words_nobody_says_are_swapped(self):
        self.check((("You can utilize the second profile.", "You can use the second profile."),
                    ("Let me delve into the settings.", "Let me look into the settings."),
                    ("This is crucial for the build.", "This is important for the build."),
                    ("Additionally, the timer's set.", "Also, the timer's set."),
                    ("It plays a key role in the sync.", "It matters for the sync."),
                    ("Leveraging the cache enhances speed.", "Using the cache improves speed.")))

    def test_not_just_x_but_y_says_both_plainly(self):
        self.check((("It's not just fast, but accurate.", "It's fast and accurate."),
                    ("Not only is it cheap but it lasts.", "Not only is it cheap but it lasts."),  # turned round: left
                    ("It's not a phone, it's a camera with a SIM.", "It's a camera with a SIM."),
                    ("The point is not speed but safety.", "The point is not speed but safety.")))  # plain not X but Y: left

    def test_dashes_and_cases_and_what_stays(self):
        self.check((("Two things — the mic and the camera.", "Two things, the mic and the camera."),
                    ("It's five. Want me to set a timer?", "It's five. Want me to set a timer?"),  # her own offer
                    ("Should I press Send?", "Should I press Send?"),
                    ("Three things: milk, eggs and bread.", "Three things: milk, eggs and bread."),  # a real list
                    ("", ""), ("   ", "   "), ("I hope this helps!", "I hope this helps!")))  # nothing else to say


class InHerLines(unittest.TestCase):
    def test_tidy_says_it_plainly_cut_or_not(self):
        self.assertEqual(siri.tidy("Certainly! It's five o'clock. Let me know if you need anything else."),
                         "It's five o'clock.")
        self.assertEqual(siri.tidy("Here's the thing: should I send it to Ravi?", cut=False),
                         "Should I send it to Ravi?")

    def test_her_default_personality_says_so_too(self):
        self.assertIn("not X but Y", siri.DEFAULT_SOUL)
        self.assertTrue(any("No filler like" in old for old in siri.OLD_SOULS))  # the one before, so it moves on


if __name__ == "__main__":
    unittest.main()
