"""Her as a close friend (7 November 2026, the owner's ask: "it doesn't have any human personality ... how they greet,
how they converse", wanting a friend, a well-wisher, family). She'd been answering like a help desk: "Welcome back,
hari. Anything you need?" word for word 8 times running, her welcome reading out the time, the weather and the free
space on C:, and the only things she said unasked were alerts ("We're back online"). Asked, the owner picked a close
friend (chatty, playful, asks how you are), checking in often, and remembering everything a friend would.

What a friend remembers that her memory didn't keep: her learning review keeps lasting facts and leaves out one-offs,
and that's most of a life. So her notes here (life.json beside her memory): what you said you'd do and when ("I'll
call Bunty tonight"), how you've been ("tired after a long day"), what's coming up or just happened (a trip, an
interview, a birthday), what you like and do, and the people in all of it, worked out from your own words after a
turn, in the background, by the answer model (heard, notice). Only from what you said to her: never room talk she let
go, never what's on a screen.

What she does with them, as a friend would (Friend.run, on a thread of its own):
- asks about a plan once its time has come ("Did you get to call Bunty?"), once (follow_up),
- checks in now and then while you're at the PC (check_in): every CHAT_GAP at the most, never in a call, in the quiet
  hours, while you're away or while she's busy, and saying nothing when there's nothing worth saying,
- greets you with what's going on in your life (greeting), not only the weather and the C drive,
- and has them in every turn's prompt (lines), to bring up the way a friend would, never as a list.
It's all kept on this PC. "Talk less", "talk more" and "forget about the trip" are answered with no model (quick)."""
import json
import os
import random
import re
import threading
import time

import settings
import winplatform as win

LIFE_PATH = os.path.join(win.APPDATA_DIR, "memories", "life.json")
KEEP = 300  # notes kept at most, the oldest going first
# seconds between her check-ins, by chattiness. Chatty was every half hour till the owner's first try on 7 November,
# a restart and nothing from her for minutes: "she still behaves like an answering assistant, not taking initiative"
CHAT_GAP = {"chatty": 20 * 60, "sometimes": 90 * 60, "quiet": None}
FIRST_CHAT = 8 * 60  # her first check-in, chatty, this long after she starts
CHATS_A_DAY = 20  # and never more than this in a day
AFTER_TURN = 6 * 60  # seconds after you last spoke to her before she checks in: not on top of a conversation
FOLLOW_AFTER_TURN = 90  # and before she asks about a plan
AWAY = 120  # seconds without a key or the mouse after which you're not at the PC to be talked to
FOLLOW_LATER = 10 * 60  # she asks how a plan went this long after its time: not on top of its reminder
FOLLOW_WITHIN = 12 * 3600  # a plan's asked about while it's no more than this overdue; older ones close unasked
MOOD_FOR = 2 * 86400  # how long a mood stays in what she knows of you
SOON = 3 * 86400  # plans and events this near now are what her prompt carries
LINES_CHARS = 500  # her notes in a turn's prompt, at most: her prompt is near its budget (siri.DEFAULT_SOUL)
KINDS = ("plan", "mood", "event", "like", "person")
SMALL_WORDS = {"a", "an", "the", "my", "our", "that", "this", "it", "about", "i", "me", "you", "to", "of", "and", "for",
               "with", "on", "in", "at", "what", "said", "told"}  # left out of "forget about the trip to Goa"
# What in your words may be a plan, a mood, something happening, a like or someone in your life: only these turns go
# to the model to be noted, so most turns cost nothing. English, and the Hinglish heard here ("kal", "thak gaya")
SIGNAL = re.compile(
    r"\b(?:i'?ll|i will|i'?m going to|i'?m gonna|gonna|i have to|i've got to|i got to|i need to|i must|i should|"
    r"i love|i like|i hate|i prefer|my favou?rite|i always|i usually|every (?:day|morning|evening|night|week)|"
    r"remind|call|calling|text|meet|visit|in (?:a|an|\d+|\w+) (?:minutes?|hours?)|later|"  # "I noted to call Sam in twenty minutes"
    r"tomorrow|tonight|today|this (?:morning|evening|afternoon|week|weekend)|next (?:week|month)|"
    r"on (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|meeting|interview|exam|deadline|"
    r"trip|travel|flight|birthday|anniversary|wedding|party|doctor|hospital|appointment|"
    r"tired|exhausted|sleepy|stressed|worried|anxious|sad|upset|angry|bored|sick|ill|fever|headache|happy|excited|"
    r"great day|bad day|long day|my (?:mom|mum|amma|dad|nanna|father|mother|brother|sister|wife|husband|friend|"
    r"girlfriend|boyfriend|boss|client|son|daughter|team)|kal|aaj|thak gaya|thak gayi|pareshan|khush)\b", re.I)
NOTE = """You keep a close friend's notes on {who}'s life, from what they just said to {her}, their assistant. Reply with one JSON object and nothing else: {{"plans": [], "mood": "", "events": [], "likes": [], "people": []}}
plans: what they said they'll do or must do, each {{"text": "call Sam", "when": "2026-11-07T19:00"}}, "when" in local time if they said one (now is {now}), else "". A plan they asked {her} to remind them of counts; a job they asked {her} to do on the PC doesn't.
mood: how they seem to be, in a few words ("tired after a long day"), only if their words show it, else "".
events: what's coming up or just happened in their life, each {{"text": "job interview at Infosys", "when": "2026-11-10"}} ("when" may be "").
likes: what they like, dislike or usually do, each a few words ("loves biryani", "plays cricket on Sundays").
people: anyone in their life they named, each {{"name": "Sam", "relation": "friend"}}, relation only if it's clear, else "".
Only what their own words say, nothing guessed. Most of the time there's nothing: then all empty."""
CHAT = """You're {name}'s close friend {her}, chatting while they're at their laptop. Say one or two short spoken sentences to them now, the way a close friend checking in would: warm, playful, a little teasing, never a lecture or a list, never "Anything you need?". Pick one thing that's worth it: something from their life below (a plan coming up, how they've been), what they're doing on the screen, how long they've been at it, a break, the time of day, a bit of fun. Don't repeat what you said lately. If nothing's worth saying right now, reply with nothing at all.
It's {when}; you last talked {ago}. {context}
What you said lately: {said}.
Reply with only the line, or nothing."""
FOLLOW = """You're {name}'s close friend {her}. Earlier they said they'd {text}{when}. Ask them about it now in one short, warm spoken sentence, the way a friend would ("So, did you get to ...?"), playful if it fits. Reply with only the line."""
GREET = """You're {name}'s close friend {her}, and they've just {how}. Greet them in one or two short spoken sentences, warm and natural, the way a close friend would, maybe teasing a little. Work these in, keeping every number, time and name exactly as written, and add no other facts: {facts}
From their life, bring up at most one thing, only if it fits naturally: {life}
{lately}Never end with "Anything you need?" or "Anything you'd like me to do?". Reply with only the line."""
# Said to her, whole (after siri.plain). Never "be quiet" or "stop talking": those stop what she's saying now
TALK_LESS = re.compile(r"(?:talk|chat|check in) less|(?:stop|don't|do not) (?:checking in(?: on me)?|chatting(?: with "
                       r"me)?)(?: so much| on your own)?|(?:don't|do not) talk (?:to me )?unless i (?:ask|talk to you)")
TALK_SOMETIMES = re.compile(r"(?:talk|chat|check in) (?:to me |with me |on me )?(?:sometimes|now and then|a bit less)")
TALK_MORE = re.compile(r"(?:talk|chat|check in) (?:to me |with me |on me )?more|check in on me|keep me company")
FORGET = re.compile(r"forget (?:what i (?:said|told you) )?about (?:my |the |that )?(.+)")
# Her hello when the model can't word it (plain_hello: offline, just woken), so it's never word for word the same
HELLO_BACK = ("Welcome back{to}.", "Hey{sp}, you're back.", "There you are{to}.", "Look who's back{to}.",
              "Oh hey{sp}, welcome back.")
HELLO_HOME = ("Hey{sp}, good {part}.", "Good {part}{to}.", "Hi{sp}, good to see you.", "There you are{to}.")
ASKS = ("Anything you need?", "What are we up to?", "What's the plan?", "Need anything?", "What can I do for you?")


def part_of_day(hour):
    return "morning" if 5 <= hour < 12 else "afternoon" if hour < 17 else "evening" if hour < 22 else "night"


def spoken_name(name):
    """Their name as it's said and shown: "hari" typed in Settings is Hari (every welcome said "hari" till 7
    November)."""
    return " ".join(w[:1].upper() + w[1:] for w in str(name or "").split())


def when_said(ts, now=None):
    """A note's time in words: "today at 7 PM", "tomorrow", "on Monday", "on 12 November"."""
    if not ts:
        return ""
    now = time.time() if now is None else now
    t, n = time.localtime(ts), time.localtime(now)
    days = round((time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 12, 0, 0, 0, 0, -1)) -
                  time.mktime((n.tm_year, n.tm_mon, n.tm_mday, 12, 0, 0, 0, 0, -1))) / 86400)
    at = "" if (t.tm_hour, t.tm_min) == (0, 0) else \
        f" at {t.tm_hour % 12 or 12}{f':{t.tm_min:02d}' if t.tm_min else ''} {'AM' if t.tm_hour < 12 else 'PM'}"
    if days in (-1, 0, 1):
        return ("yesterday", "today", "tomorrow")[days + 1] + at
    if 1 < days < 7:
        return time.strftime("on %A", t) + at
    return f"on {t.tm_mday} {time.strftime('%B', t)}" + at


def parse_when(text):
    """A note's "when" ("2026-11-07T19:00", "2026-11-10") as seconds since 1970, or None."""
    text = str(text or "").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return time.mktime(time.strptime(text, fmt))
        except ValueError:
            continue
    return None


def plain_hello(line, back, pick=random.choice, hour=None):
    """siri.welcome_line's line with its hello and its question one of a few friendlier ways, for when the model
    can't word it: "Welcome back, Hari. Anything you need?" was said 8 times running on 7 November, offline after a
    wake. Its facts as they were."""
    head = re.match(r"Welcome (?:back|home)(, [^.]+)?\.\s*", str(line or ""))
    if not head:
        return line
    part = part_of_day(time.localtime().tm_hour if hour is None else hour)
    rest = re.sub(r"Anything (?:you need|you'd like me to do)\?$", lambda m: pick(ASKS), line[head.end():])
    name = (head.group(1) or "")[2:]
    hello = pick(HELLO_BACK if back else HELLO_HOME).format(to=f", {name}" if name else "",
                                                            sp=f" {name}" if name else "",
                                                            part="evening" if part == "night" else part)
    return f"{hello} {rest}".strip()


def json_of(raw):
    """The first JSON object in a model's reply, or {}."""
    try:
        raw = str(raw or "")
        got = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        return got if isinstance(got, dict) else {}
    except ValueError:
        return {}


def a_line(raw, most=280):
    """A model's line made fit to say: one line, no quotes round it, at most most characters; "" if it's empty or
    the model said it had nothing."""
    line = " ".join(str(raw or "").split()).strip("\"'“” ")
    if not line or line.lower().strip(".!()") in ("nothing", "none", "no", "n/a", "nothing at all"):
        return ""
    return line[:most]


class Friend:
    """Her notes on your life, and her talking to you as a friend. ask: messages -> the answer model's reply (raises
    when it doesn't answer); announce: line -> said once she's free; free: () -> no turn of hers, dictation or the
    like going on; idle: () -> seconds since your last key or mouse; in_call, quiet: () -> True in a call, in her quiet
    hours; name, her: () -> your name, hers; soul: () -> her personality, for what she says; now_context: () -> a line
    on what's going on now (the screen); mode: () -> "chatty", "sometimes" or "quiet"."""

    def __init__(self, ask, announce, free, idle, in_call, quiet, name, her=lambda: "Harry", soul=lambda: "",
                 now_context=lambda: "", mode=lambda: "chatty", clock=time.time, path=LIFE_PATH):
        self.ask, self.announce, self.free, self.idle = ask, announce, free, idle
        self.in_call, self.quiet, self.name, self.her, self.soul = in_call, quiet, name, her, soul
        self.now_context, self.mode, self.clock, self.path = now_context, mode, clock, path
        self.lock = threading.Lock()
        self.noting = threading.Lock()  # one note-taking at a time
        self.notes = self._load()
        self.last_turn = clock()  # when you last spoke to her: no check-in on top of a conversation
        self.last_said = clock() - CHAT_GAP["chatty"] + FIRST_CHAT  # when she last spoke unasked, as if: her first
        # check-in, chatty, FIRST_CHAT after she starts
        self.said = []  # (when, what) she said unasked lately, so she doesn't say it again

    # ------------------------------------------------------------------ her notes
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                notes = json.load(f)
            return [n for n in notes if isinstance(n, dict) and n.get("text") and n.get("kind") in KINDS]
        except (OSError, ValueError, TypeError):
            return []

    def _save(self):
        """Her notes to life.json, the newest KEEP. Called holding self.lock."""
        self.notes = self.notes[-KEEP:]
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            part = self.path + ".part"
            with open(part, "w", encoding="utf-8") as f:
                json.dump(self.notes, f, ensure_ascii=False, indent=1)
            os.replace(part, self.path)
        except OSError as exc:
            print(f"  couldn't keep her notes: {exc!r}")

    def add(self, kind, text, when=None, relation=""):
        """One note kept: a plan, a mood, an event, a like or a person; the note, or None for no text. The same one
        twice is kept once, a person's relation and a plan's time filled in when they come later; a plan she's asked
        after is a new one when it's said again."""
        text = " ".join(str(text or "").split())[:200]
        if not text or kind not in KINDS:
            return None
        with self.lock:
            for n in self.notes:
                if n["kind"] == kind and n["text"].lower() == text.lower() and n.get("status", "open") == "open":
                    if relation and not n.get("relation"):
                        n["relation"] = relation
                    if when and not n.get("when"):
                        n["when"] = when
                    if kind == "mood":  # tired again today: it's today's
                        n["said"] = self.clock()
                    self._save()
                    return n
            note = {"kind": kind, "text": text, "when": when, "said": self.clock(),
                    **({"status": "open"} if kind == "plan" else {}), **({"relation": relation} if relation else {})}
            self.notes.append(note)
            self._save()
            return note

    def forget(self, about):
        """Her notes about something taken out ("forget about the trip"): how many."""
        words = [w for w in re.findall(r"\w+", str(about).lower()) if w not in SMALL_WORDS]
        if not words:
            return 0
        with self.lock:
            kept = [n for n in self.notes if not all(w in n["text"].lower() or w == n.get("relation", "").lower()
                                                     for w in words)]
            gone = len(self.notes) - len(kept)
            if gone:
                self.notes = kept
                self._save()
        return gone

    def heard(self, words, reply="", gate=False):
        """After a turn of yours: words that may be about your life are noted in the background (notice)."""
        self.last_turn = self.clock()
        if words and SIGNAL.search(str(words)) and self.noting.acquire(blocking=False):
            threading.Thread(target=self._notice, args=(str(words), str(reply or "")), name="friend-notes",
                             daemon=True).start()

    def _notice(self, words, reply):
        try:
            self.notice(words, reply)
        except Exception as exc:  # never the end of her
            print(f"  couldn't note that: {exc!r}")
        finally:
            self.noting.release()

    def notice(self, words, reply=""):
        """What your words say about your life, as the model reads them (NOTE), kept: the notes kept."""
        now = self.clock()
        try:
            got = json_of(self.ask([{"role": "system", "content": NOTE.format(
                her=self.her(), who=self.name() or "the user",
                now=time.strftime("%A %Y-%m-%dT%H:%M", time.localtime(now)))},
                {"role": "user", "content": f"They said: {words}\n{self.her()} said: {reply}"}]))
        except Exception as exc:
            print(f"  couldn't note that: {exc!r}")
            return []
        kept = []
        for p in got.get("plans") or []:
            if isinstance(p, dict):
                kept.append(self.add("plan", p.get("text"), parse_when(p.get("when"))))
        if isinstance(got.get("mood"), str):
            kept.append(self.add("mood", got["mood"]))
        for e in got.get("events") or []:
            if isinstance(e, dict):
                kept.append(self.add("event", e.get("text"), parse_when(e.get("when"))))
        for like in got.get("likes") or []:
            if isinstance(like, str):
                kept.append(self.add("like", like))
        for p in got.get("people") or []:
            if isinstance(p, dict):
                kept.append(self.add("person", p.get("name"), relation=" ".join(str(p.get("relation") or "").split())))
        kept = [k for k in kept if k]
        if kept:
            print(f"  noted: {'; '.join(k['kind'] + ' ' + k['text'] for k in kept)}")
        return kept

    def life(self, now=None):
        """What's going on in your life now, short: plans and events near now, a recent mood, likes, the people."""
        now = self.clock() if now is None else now
        with self.lock:
            notes = list(self.notes)

        def near(n):
            return not n.get("when") or abs(n["when"] - now) < SOON

        def at(n):
            return f" ({when_said(n['when'], now)})" if n.get("when") else ""

        plans = [n for n in notes if n["kind"] == "plan" and n.get("status") == "open" and near(n)][-5:]
        events = [n for n in notes if n["kind"] == "event" and near(n) and now - n["said"] < 30 * 86400][-4:]
        moods = [n for n in notes if n["kind"] == "mood" and now - n["said"] < MOOD_FOR][-1:]
        likes = [n for n in notes if n["kind"] == "like"][-6:]
        people = [n for n in notes if n["kind"] == "person"][-8:]
        parts = []
        if plans:
            parts.append("Their plans: " + "; ".join(n["text"] + at(n) for n in plans) + ".")
        if events:
            parts.append("Going on: " + "; ".join(n["text"] + at(n) for n in events) + ".")
        if moods:
            parts.append(f"Lately: {moods[0]['text']} ({when_said(moods[0]['said'], now).split(' at ')[0]}).")
        if likes:
            parts.append("They: " + "; ".join(n["text"] for n in likes) + ".")
        if people:
            parts.append("Their people: " + ", ".join(n["text"] + (f" ({n['relation']})" if n.get("relation") else "")
                                                      for n in people) + ".")
        return parts

    def lines(self, now=None):
        """Her notes for a turn's prompt, to bring up the way a close friend would, never read out as a list."""
        text = "\n".join(self.life(now))
        if not text:
            return []
        return ["What you know of their life lately, from what they told you (bring it up now and then the way a "
                "close friend would, never as a list):\n" + text[:LINES_CHARS]]

    # ------------------------------------------------------------------ talking first
    def _messages(self, prompt):
        soul = str(self.soul() or "").strip()
        return ([{"role": "system", "content": soul}] if soul else []) + [{"role": "user", "content": prompt}]

    def can_talk(self):
        """True if she may say something unasked now: you're at the PC, not in a call or her quiet hours, and she's
        free."""
        return self.idle() <= AWAY and not self.in_call() and not self.quiet() and self.free()

    def due(self, now=None):
        """The plan whose time came FOLLOW_LATER ago and that she hasn't asked about, or None. One overdue by more than
        FOLLOW_WITHIN is closed unasked: a follow-up a day late is nagging, not a friend."""
        now = self.clock() if now is None else now
        found, closed = None, False
        with self.lock:
            for n in self.notes:
                if n["kind"] == "plan" and n.get("status") == "open" and n.get("when") and \
                        n["when"] + FOLLOW_LATER <= now:
                    if now - n["when"] > FOLLOW_WITHIN:
                        n["status"], closed = "done", True
                    elif found is None:
                        found = n
            if closed:
                self._save()
        return found

    def follow_up(self, note, now=None):
        """A plan come due, asked about once, warmly ("Did you get to call Bunty?"): the line."""
        now = self.clock() if now is None else now
        when = f" {when_said(note['when'], now)}" if note.get("when") else ""
        try:
            line = a_line(self.ask(self._messages(FOLLOW.format(
                her=self.her(), name=self.name() or "them", text=note["text"], when=when))))
        except Exception as exc:
            print(f"  couldn't word a follow-up: {exc!r}")
            line = ""
        line = line or f"Hey, did you get to {note['text']}?"
        with self.lock:
            note["status"] = "asked"
            self._save()
        self._say(line, now)
        return line

    def check_in(self, now=None):
        """A friend's word now and then (CHAT): the line, or "" when nothing's worth saying."""
        now = self.clock() if now is None else now
        day = time.localtime(now)[:3]
        if sum(time.localtime(w)[:3] == day for w, _ in self.said) >= CHATS_A_DAY:
            return ""
        lt = time.localtime(now)
        when = f"{lt.tm_hour % 12 or 12}:{lt.tm_min:02d} {'AM' if lt.tm_hour < 12 else 'PM'}, a " \
               f"{time.strftime('%A', lt)} {part_of_day(lt.tm_hour)}"
        minutes = int((now - self.last_turn) // 60)
        ago = "just now" if minutes < 1 else f"{minutes} minutes ago" if minutes < 120 else f"{minutes // 60} hours ago"
        context = "\n".join(p for p in self.life(now) + [str(self.now_context() or "")] if p)
        said = "; ".join(w for _, w in self.said[-5:]) or "nothing yet"
        self.last_said = now  # tried: the next try waits its gap too, whether she said something or not
        try:
            line = a_line(self.ask(self._messages(CHAT.format(
                her=self.her(), name=self.name() or "them", when=when, ago=ago, context=context, said=said))))
        except Exception as exc:
            print(f"  couldn't check in: {exc!r}")
            return ""
        if line:
            self._say(line, now)
        return line

    def _say(self, line, now):
        self.said = (self.said + [(now, line)])[-40:]
        self.last_said = now
        print(f"  friend: {line}")
        self.announce(line)

    def tick(self, now=None):
        """One look: a plan come due, else a check-in if it's time: what she'll say, or ""."""
        now = self.clock() if now is None else now
        if not self.can_talk():
            return ""
        note = self.due(now)
        if note is not None and now - self.last_turn >= FOLLOW_AFTER_TURN and now - self.last_said >= 10 * 60:
            return self.follow_up(note, now)
        gap = CHAT_GAP.get(self.mode(), CHAT_GAP["chatty"])
        if gap and now - self.last_said >= gap and now - self.last_turn >= AFTER_TURN and self.idle() <= 60:
            return self.check_in(now)
        return ""

    def run(self, stop=None, every=20.0):
        stop = stop or threading.Event()
        while not stop.wait(every):
            try:
                self.tick()
            except Exception as exc:  # never the end of her
                print(f"  friend: {exc!r}")

    # ------------------------------------------------------------------ hello
    def greeting(self, back, facts, lately=(), ask=None, now=None):
        """Her hello as a close friend: facts (siri.welcome_line's: who messaged, a low battery, today's reminders) in
        her words, with one thing from your life if it fits; lately: how her last hellos began, not to start that way
        again; ask: the model, when it must be quicker than self.ask. "" if the model doesn't answer."""
        now = self.clock() if now is None else now
        how = "come back to the laptop" if back else f"signed in this {part_of_day(time.localtime(now).tm_hour)}"
        facts = re.sub(r"\s*Anything (?:you need|you'd like me to do)\?", "", str(facts or "")).strip() or "nothing"
        life = " ".join(self.life(now)) or "nothing"
        lately = [str(o) for o in lately if o]
        prompt = GREET.format(her=self.her(), name=self.name() or "them", how=how, facts=facts, life=life,
                              lately=("Don't start the way you did lately (" + ", ".join(f'"{o}"' for o in lately)
                                      + ").\n") if lately else "")
        try:
            return a_line((ask or self.ask)(self._messages(prompt)), 320)
        except Exception as exc:
            print(f"  couldn't greet as a friend: {exc!r}")
            return ""


def quick(words, plain, gate, friend=None):
    """"Talk less", "talk more", "check in now and then": how chatty she is, switched there and then; "forget about
    the trip": her notes on it gone. A plan with only what she says, or None."""
    t = plain(str(words or ""))
    for rx, mode, line in ((TALK_LESS, "quiet", "Okay, I'll keep it down. Just what you told me you'd do."),
                           (TALK_SOMETIMES, "sometimes", "Okay, I'll check in now and then."),
                           (TALK_MORE, "chatty", "Ha, you'll be sick of me. I'll check in more.")):
        if rx.fullmatch(t):
            settings.put("chattiness", mode)
            return {"steps": [], "say": line}
    forget = FORGET.fullmatch(t)
    if forget and friend is not None and friend.forget(forget.group(1)):  # else it's her memory's, as before
        return {"steps": [], "say": "Okay, forgotten."}
    return None
