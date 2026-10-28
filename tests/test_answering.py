"""27 October: "Hey, order biryani on Zomato" got no answer five times in two minutes, and Hari said she must answer
him every time, and that she still sounded like a bot: the same greeting and the same lines. What he says again
reaches her (said_again), ordering and questions about her reach the model, and her scripted lines and her welcome
come in her own words (phrasebook, fresh_welcome)."""
import contextlib
import hashlib
import io
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from tests.support import siri
from tests.test_actions import Turn as HandleTurn
from tests.test_listening import Assistant, FakeEars
from tests.test_planner import FakeModel, Turn as ThinkTurn

import phrasebook
import speech

# how speech-to-text wrote "Hey, order biryani on Zomato" on 27 October, in order
TRIES = ["He ordered it piranhi on tomato", "They order BI on tomato", "He order Joeani on my geometric account",
         "Biryani on geometry", "Can you order me biryani and tomato"]


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


class Reaching(unittest.TestCase):
    """What he said reaches the model; talk in the room still doesn't."""

    def setUp(self):
        for target, name, value in ((siri.win, "call_apps", lambda *a, **kw: []),):
            p = mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)

    def route(self, words):
        return siri.route(speech.heard(words, 0.9), "other", open_mic=True)

    def test_his_tries_at_an_order_go_to_the_model(self):
        for words in TRIES + ["Hey, order biryani on Zomato", "Open Swiggy", "buy a phone charger on Flipkart"]:
            with self.subTest(words=words):
                self.assertEqual(self.route(words)[2], "cold")
                self.assertTrue(siri.asks_something(siri.fix_names(words), "cold"))  # the decider never lets it go

    def test_zomato_is_put_back_only_in_talk_of_food(self):
        self.assertEqual(siri.fix_names(TRIES[0]), "He ordered it piranhi on Zomato")
        self.assertEqual(siri.fix_names(TRIES[2]), "He order Joeani on my Zomato account")
        self.assertEqual(siri.fix_names(TRIES[3]), "Biryani on Zomato")
        for words in ("add tomato to the salad", "work on geometry homework", "order onions and tomatoes"):
            self.assertEqual(siri.fix_names(words), words)

    def test_asking_about_her_reaches_her(self):
        for words in ("Hello, can you listen", "Why you can't do that", "why can't you do that", "can you hear me",
                      "listen to me", "are you deaf"):
            with self.subTest(words=words):
                self.assertTrue(siri.ABOUT_HER.search(siri.words_of(words)))
                self.assertEqual(self.route(words)[2], "cold")
        for words in ("can you hear that noise", "can you listen to this song", "why didn't you do that"):
            with self.subTest(words=words):
                self.assertFalse(siri.ABOUT_HER.search(siri.words_of(words)))

    def test_hey_hello_is_hers_and_hello_hello_isnt(self):
        self.assertEqual(self.route("Hey hello")[2], "cold")
        self.assertIsNone(self.route("Hello hello"))  # how a phone call breaking up goes
        self.assertIsNone(self.route("pass me the biryani"))

    def test_zomato_and_swiggy_open_at_once(self):
        self.assertEqual(siri.quick("open zomato")["steps"], [{"do": "website", "url": "https://www.zomato.com"}])
        self.assertEqual(siri.quick("open swiggy")["steps"], [{"do": "website", "url": "https://www.swiggy.com"}])


class SaidAgain(unittest.TestCase):
    def setUp(self):
        siri.MISSED.clear()
        self.addCleanup(siri.MISSED.clear)

    def test_the_tries_of_27_october(self):
        found = []
        for words in TRIES:
            found.append(siri.said_again(words))
            siri.missed(words)
        self.assertEqual(found[0], [])
        self.assertEqual(found[1], TRIES[:1])
        self.assertEqual(found[3], TRIES[:3])  # "Biryani on geometry": Zomato in all of them, once put back
        siri.MISSED.clear()
        siri.missed("An open pane and dry a Spider Man")
        self.assertEqual(siri.said_again("We open paint and dry a Spider Man"), ["An open pane and dry a Spider Man"])

    def test_talk_said_twice_isnt(self):
        for first, then in (("what time does the match start, pass the salt", "please pass the salt, I said"),
                            ("What a shot by Kohli", "What a shot that is"),
                            ("Spider-Man, Spider-Man, does whatever a spider can",
                             "Spider-Man, Spider-Man, friendly neighbourhood Spider-Man")):
            with self.subTest(then=then):
                siri.MISSED.clear()
                siri.missed(first)
                self.assertEqual(siri.said_again(then), [])

    def test_only_for_a_little_while_and_not_a_greeting(self):
        siri.missed(TRIES[0])
        self.assertEqual(siri.said_again(TRIES[1], now=time.time() + siri.AGAIN_WITHIN + 1), [])
        siri.missed("Hey hello")
        self.assertEqual(siri.said_again("Hey hello"), [])


class InHerEars(unittest.TestCase):
    """act_on: a try said again goes to her with the earlier ones, past the decider; one she answers isn't a try."""

    def setUp(self):
        siri.MISSED.clear()
        siri.ROOM.clear()
        self.addCleanup(siri.MISSED.clear)
        self.addCleanup(siri.ROOM.clear)
        self.a = Assistant(ears=FakeEars())
        self.addCleanup(self.a.close)
        self.handled = []

    def hear(self, words, result=False, decider="off"):
        def handle(text, *args, **kw):
            self.handled.append((str(text), list(siri.AGAIN[0] or [])))
            return result
        sure_no = type("SureNo", (), {"for_me": lambda self, words, kind: (0.01, "no")})()
        with mock.patch.object(siri, "handle", handle), \
                mock.patch.dict(siri.settings._load(), {"no_name": True, "voice_id": "off", "decider": decider,
                                                        "call_aware": False}), \
                mock.patch.object(siri.decider, "get", lambda: sure_no), \
                mock.patch.object(siri.decider, "available", lambda: True), \
                mock.patch.object(siri.decider, "log", lambda entry: None), \
                mock.patch.object(siri, "asked_last", lambda *a: False):
            self.a.var("act_on")(speech.heard(words), "other", 100)

    def test_said_again_it_goes_to_her_with_the_first_try(self):
        self.hear(TRIES[0])
        self.hear(TRIES[1])
        self.assertEqual(self.handled, [(TRIES[0], []), (TRIES[1], [TRIES[0]])])
        self.assertFalse(siri.AGAIN[0])  # only for that turn

    def test_what_she_let_go_comes_too_and_the_decider_doesnt_stop_it(self):
        self.hear("Did you check Zomato")  # let go before the model ("did you ..." is to a person)
        self.assertEqual(self.handled, [])
        self.hear("did you check Zomato for me", decider="on")
        self.assertEqual(self.handled, [("did you check Zomato for me", ["Did you check Zomato"])])

    def test_once_she_answers_what_came_before_isnt_a_try(self):
        self.hear(TRIES[0])
        self.hear(TRIES[1], result=True)
        self.assertEqual(list(siri.MISSED), [])
        self.assertEqual(list(siri.ROOM), [])  # nor shown to the model as talk in the room
        self.hear(TRIES[2])
        self.assertEqual(self.handled[-1], (TRIES[2], []))


class Told(ThinkTurn):
    """What the model is told for a try said again, and for an order."""

    def system(self):
        return str(self.model.calls[0][0][0]["content"])

    def test_a_try_said_again_comes_with_the_earlier_ones_and_is_to_her(self):
        siri.AGAIN[0] = TRIES[:2]
        self.addCleanup(siri.AGAIN.__setitem__, 0, None)
        with quiet():
            plan = self.think(TRIES[2], "cold", '{"to": "you", "steps": [], "say": "Want biryani from Zomato?"}')
        self.assertEqual(plan["say"], "Want biryani from Zomato?")
        system, said = self.system(), str(self.model.calls[0][0][-1]["content"])
        self.assertIn(f'"{TRIES[0]}"; "{TRIES[1]}"', system)
        self.assertIn("it's to you", system)
        self.assertNotIn(siri.COLD_NOTE, system)
        self.assertNotIn("Who is it said to?", said)

    def test_ordering_comes_with_how_and_paying_stays_theirs(self):
        with quiet():
            self.think("order biryani on Zomato", False, '{"steps": [], "say": "Sure."}')
        self.assertIn(siri.ORDER_STEPS, self.system())
        with quiet():
            self.think("open notepad and write hello", False, '{"steps": [], "say": "Sure."}')
        self.assertNotIn(siri.ORDER_STEPS, self.system())

    def test_what_came_before_isnt_said_to_be_for_someone_else(self):
        siri.ROOM.append((time.time(), "They order BI on tomato"))
        self.addCleanup(siri.ROOM.clear)
        with quiet():
            self.think("what's the weather", "cold", '{"to": "you", "steps": [], "say": "Sunny."}')
        self.assertIn('near the PC and not answered: "They order BI on tomato"', self.system())
        self.assertNotIn("not to you", self.system())


class Answered(HandleTurn):
    """handle: a try said again is answered, if only to ask; "Hey hello" is greeted."""

    def setUp(self):
        super().setUp()
        self.addCleanup(siri.AGAIN.__setitem__, 0, None)
        # her answers here are questions, kept in the tests' history: what a test after these hears would be taken
        # for a reply to one (asked_last)
        self.addCleanup(siri.history.clear)

    def test_said_again_and_not_made_out_she_says_so(self):
        siri.AGAIN[0] = TRIES[:1]
        with self.model(None), quiet():
            self.assertFalse(siri.handle(speech.heard(TRIES[1], 0.4), gate="cold"))  # however unsure the words
        self.assertEqual(len(self.said), 1)
        self.assertIn(self.said[0], siri.REPLIES["not_caught"])

    ASKS = {"steps": [], "say": "Sorry, I didn't catch what to order. Biryani from Zomato?"}

    def test_said_again_her_question_is_said(self):
        siri.AGAIN[0] = TRIES[:1]
        with self.model(dict(self.ASKS)), quiet():
            siri.handle(TRIES[1], gate="cold")
        self.assertEqual(self.said, [self.ASKS["say"]])

    def test_the_first_time_unclear_is_still_let_go(self):
        with self.model(dict(self.ASKS)), quiet():
            self.assertFalse(siri.handle(TRIES[0], gate="cold"))  # never "say that again" to someone else's talk
        self.assertEqual(self.said, [])

    def test_hey_hello_is_greeted_back(self):
        with mock.patch.object(siri, "think", lambda *a, **kw: self.fail("asked the model")), quiet():
            siri.handle("Hey hello", gate="cold")
        self.assertEqual(len(self.said), 1)
        self.assertIn(self.said[0], siri.REPLIES["greeting"])


class Phrasebook(unittest.TestCase):
    BASE = {"app_quit": ["Okay, I've closed {app}.", "Closing {app}."], "filler": ["On it.", "One moment."],
            "screen_ask": ["Should I look at your screen for that?"]}

    def setUp(self):
        folder = tempfile.mkdtemp(prefix="phrases-")
        for name, value in (("PATH", os.path.join(folder, "phrases.json")), ("RECENT", {})):
            p = mock.patch.object(phrasebook, name, value)
            p.start()
            self.addCleanup(p.stop)
        phrasebook._cache.update(mtime=None, data={})

    def write(self, reply, base=None):
        return phrasebook.write(lambda messages: reply, "You are Harry.", base or self.BASE)

    def test_only_lines_that_can_stand_in_are_kept(self):
        made = self.write(json.dumps({
            "app_quit": ["{app}'s closed.", "Closed it.", "Shut {app} for you, Harry style.", "Closing {app} [sighs]."],
            "filler": ["Give me a sec.", "Hang on.", "Hang on.", "On it. \U0001f680", "One moment?",
                       "Right, I'm going to be working on this for you now, just a moment please.", "Working on it."],
            "screen_ask": ["Want me to look at your screen?", "I'll look at your screen."]}))
        lines = phrasebook.load()["lines"]
        self.assertEqual(lines["app_quit"], ["{app}'s closed."])  # 1 for a line made for every app (MORE_NAMED)
        self.assertEqual(lines["filler"], ["Give me a sec.", "Hang on.", "Working on it."])
        self.assertEqual(lines["screen_ask"], ["Want me to look at your screen?"])  # a question stays one
        self.assertEqual(made, 5)
        self.assertFalse(phrasebook.due("You are Harry.", self.BASE))
        self.assertTrue(phrasebook.due("You are Harry, now chattier.", self.BASE))  # a new personality
        self.assertTrue(phrasebook.due("You are Harry.", {**self.BASE, "thanks": ["Anytime."]}))  # a new line
        self.assertTrue(phrasebook.due("You are Harry.", self.BASE, now=time.time() + phrasebook.EVERY + 1))
        # no time of day the line didn't have: a hello is said at any hour
        self.assertFalse(phrasebook.fits("Morning, what can I do?", ["Hey, what can I do?"]))
        self.assertTrue(phrasebook.fits("Night light's off now.", ["Night light's off."]))

    def test_the_newest_are_kept_up_to_a_limit(self):
        base = {**self.BASE, "closed": ["Okay, it's closed.", "Closed it."]}
        for n in range(4):
            self.write(json.dumps({"closed": [f"Shut it {w}." for w in ("one", "two", "three", "four", "five", "six")]
                                   if n == 0 else [f"Wait {n} {w}." for w in ("a", "b", "c")]}), base)
        kept = phrasebook.load()["lines"]["closed"]
        self.assertEqual(len(kept), phrasebook.KEEP)
        self.assertEqual(kept[:3], ["Wait 3 a.", "Wait 3 b.", "Wait 3 c."])
        self.assertNotIn("Shut it six.", kept)  # MORE a time
        self.assertEqual(phrasebook.how_many("filler", self.BASE["filler"]), (8, 16))  # what she says most

    def test_never_the_same_line_twice_running_and_new_ones_once_ready(self):
        self.write(json.dumps({"filler": ["Give me a sec.", "Hang on.", "Working on it."]}))
        base = self.BASE["filler"]
        said = [phrasebook.pick("filler", base) for _ in range(40)]
        self.assertTrue(all(a != b for a, b in zip(said, said[1:])))
        self.assertEqual(set(said), set(base) | {"Give me a sec.", "Hang on.", "Working on it."})
        not_ready = {phrasebook.pick("filler", base, ready=lambda line: False) for _ in range(20)}
        self.assertEqual(not_ready, set(base))  # her voice for the new ones isn't made yet

    def test_say_line_and_her_cache_use_them(self):
        self.write(json.dumps({"filler": ["Give me a sec."], "app_quit": ["{app}'s closed."]}))
        with mock.patch.object(siri, "REPLIES", {**siri.REPLIES, **self.BASE}):
            self.assertIn("Give me a sec.", set(siri.all_scripted_lines()))
            self.assertIn("Notepad's closed.", set(siri.all_scripted_lines()))
            with mock.patch.object(siri, "_voiced", lambda line, fmt: True):
                said = {siri.say_line("filler") for _ in range(30)}
            self.assertIn("Give me a sec.", said)

    def test_a_kind_written_wrong_loses_only_its_own_lines(self):
        """On 27 October the first reply didn't read as JSON and no line was kept: now a kind's lines that don't
        read are skipped, written as one object (as Haiku does), a line each (as ASK asks) or cut off."""
        replies = [  # quotes out of place in app_quit's
            '{"filler": ["Give me a sec.", "Hang on."], "app_quit": ["Shut "{app}" down."], '
            '"screen_ask": ["Want me to look at your screen?"]}',
            '{"filler": ["Give me a sec.", "Hang on."]}\n{"app_quit": ["Shut "{app}" down."]}\n'
            '{"screen_ask": ["Want me to look at your screen?"]}',
            '{"filler": {"say": ["On it."], "new": ["Give me a sec.", "Hang on."]}, "app_quit": ["Shut {app}", '
            '"screen_ask": ["Want me to look at your screen?"]}',  # copying what it was asked, and a list unclosed
            '{"screen_ask": ["Want me to look at your screen?"], "filler": ["Give me a sec.", "Hang on."], '
            '"app_quit": ["{app}\'s cl',  # cut off
        ]
        for reply in replies:
            with self.subTest(reply=reply[:60]):
                phrasebook._cache.update(mtime=None, data={})
                os.path.exists(phrasebook.PATH) and os.remove(phrasebook.PATH)
                self.assertEqual(self.write(reply), 3)
                lines = phrasebook.load()["lines"]
                self.assertEqual(lines["filler"], ["Give me a sec.", "Hang on."])
                self.assertEqual(lines["screen_ask"], ["Want me to look at your screen?"])
                self.assertEqual(lines["app_quit"], [])
        with self.assertRaises(ValueError):
            self.write('{"filler": ["Give me a sec." "Hang on."]}')  # none of it reads: nothing's kept

    def test_her_welcomes_are_kept_a_few(self):
        for n in range(phrasebook.SAID_KEEP + 2):
            phrasebook.remember("welcome", f"Hi number {n}.")
        self.assertEqual(phrasebook.said("welcome")[-1], f"Hi number {phrasebook.SAID_KEEP + 1}.")
        self.assertEqual(len(phrasebook.said("welcome")), phrasebook.SAID_KEEP)


class Welcome(unittest.TestCase):
    FACTS = "Welcome back, Hari. Battery's at 18 percent. Anything you need?"

    def setUp(self):
        folder = tempfile.mkdtemp(prefix="phrases-")
        p = mock.patch.object(phrasebook, "PATH", os.path.join(folder, "phrases.json"))
        p.start()
        self.addCleanup(p.stop)
        phrasebook._cache.update(mtime=None, data={})
        for name, value in (("soul", lambda: "You are Harry."), ("memory_block", lambda: "")):
            p = mock.patch.object(siri, name, value)
            p.start()
            self.addCleanup(p.stop)

    def welcome(self, reply, facts=None):
        asked = []

        def chat(key, messages, **kw):
            asked.append(messages)
            if isinstance(reply, Exception):
                raise reply
            return reply, {}, "test"
        with mock.patch.object(siri.opencode, "chat", chat), mock.patch.object(siri, "part_of_day", lambda: "evening"), \
                quiet():
            return siri.fresh_welcome(True, facts or self.FACTS), asked

    def test_in_her_own_words_with_the_facts_kept(self):
        line, asked = self.welcome('"Hey Hari, good to see you. Battery\'s down to 18 percent, worth plugging in."')
        self.assertEqual(line, "Hey Hari, good to see you. Battery's down to 18 percent, worth plugging in.")
        self.assertIn(self.FACTS, asked[0][-1]["content"])
        self.assertIn("evening", asked[0][-1]["content"])  # the time of day it is, which back welcomes don't say
        self.assertEqual(phrasebook.said("welcome"), [line])
        _, asked = self.welcome("Good evening, Hari. Battery's at 18 percent.")
        self.assertIn('"Hey Hari"', asked[0][-1]["content"])  # told how it began last time
        self.assertNotIn("worth plugging in", asked[0][-1]["content"])  # and not the rest, last time's news
        self.assertEqual(phrasebook.said("welcome")[-1], "Good evening, Hari. Battery's at 18 percent.")

    def test_made_up_facts_or_no_answer_and_its_as_written(self):
        for made_up in ("Welcome back, Hari. Battery's at 81 percent.",  # a number it wasn't given
                        "Welcome back, Hari. Amma messaged you, and the battery's at 18 percent.",  # 27 October
                        "Hey Hari, Bittu says hi. Battery's at 18 percent.",  # a name
                        "Good morning, Hari. Battery's at 18 percent.",  # in the evening
                        "Welcome back, Hari. It's sunny out, and the battery's at 18 percent.",  # the weather
                        "[cheerful] Welcome back!"):
            with self.subTest(made_up):
                self.assertIsNone(self.welcome(made_up)[0])
        self.assertIsNone(self.welcome(TimeoutError("slow"))[0])
        self.assertEqual(phrasebook.said("welcome"), [])
        facts = "Welcome back, Hari. Amma messaged you on WhatsApp. Anything you need?"
        self.assertEqual(self.welcome("Hey Hari, Amma sent you a WhatsApp message.", facts)[0],
                         "Hey Hari, Amma sent you a WhatsApp message.")  # what it was given, said its own way
        self.assertIsNone(siri.welcome_opener("Amma messaged you while you were away."))  # news, never told again
        # nothing left out: the weather on signing in, or who messaged
        self.assertFalse(siri.welcome_fits("Good to have you back, Hari. Let's get you set up.",
                                           "Welcome home, Hari. It's 4:58 in the evening, 31 degrees and partly cloudy "
                                           "outside. Anything you'd like me to do?", "evening"))
        self.assertFalse(siri.welcome_fits("Hey Hari, someone messaged you on WhatsApp.", facts, "evening"))
        # and nobody from her memory that it wasn't told about, even to start with
        told = "You are Harry.\nAbout them: Hari's mum is called Amma. He runs CareerID."
        self.assertFalse(siri.welcome_fits("Amma says hi, Hari. Battery's at 18 percent.", self.FACTS, "evening", told))
        self.assertTrue(siri.welcome_fits("Hey Hari. Battery's at 18 percent.", self.FACTS, "evening", told))


class Soul(unittest.TestCase):
    def setUp(self):
        self.old = None
        if os.path.exists(siri.SOUL_PATH):
            with open(siri.SOUL_PATH, encoding="utf-8") as f:
                self.old = f.read()
        self.addCleanup(self.restore)

    def restore(self):
        if self.old is None:
            if os.path.exists(siri.SOUL_PATH):
                os.remove(siri.SOUL_PATH)
        else:
            with open(siri.SOUL_PATH, "w", encoding="utf-8") as f:
                f.write(self.old)

    def soul(self, text, olds):
        os.makedirs(os.path.dirname(siri.SOUL_PATH), exist_ok=True)
        with open(siri.SOUL_PATH, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        with mock.patch.object(siri, "OLD_SOULS", olds), quiet():
            got = siri.soul()
        with open(siri.SOUL_PATH, encoding="utf-8") as f:
            return got, f.read().strip()

    def test_an_old_default_nobody_changed_is_brought_up_to_date(self):
        old = "You are Harry, the old way."
        self.assertEqual(self.soul(old, (old,)), (siri.DEFAULT_SOUL, siri.DEFAULT_SOUL))

    def test_one_they_wrote_is_theirs(self):
        mine = "You are Harry, and you talk like a pirate."
        self.assertEqual(self.soul(mine, ("something else",)), (mine, mine))
        self.assertIn("Sound alive, never scripted", siri.DEFAULT_SOUL)

    def test_the_27_october_default_moves_on_too(self):
        """Hari's SOUL.md held the 27 October default (sound alive) when the 28 October one (answer first) came: it
        moves on to the default that has both, as he never edited it. It said Jev then, her name till 28 October:
        siri.soul reads a SOUL.md with that name as Harry's."""
        self.assertEqual(hashlib.sha1(siri.OLD_SOULS[1].strip().replace("Harry", "Jev").encode()).hexdigest(),
                         "28f385809c29f94ca47a4698496356fcbd95be41")
        self.assertIn("Answer first", siri.DEFAULT_SOUL)
        self.assertNotIn(siri.DEFAULT_SOUL.strip(), [old.strip() for old in siri.OLD_SOULS])


if __name__ == "__main__":
    unittest.main()
