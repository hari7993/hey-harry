"""Newer skills (28 October 2026, the owner's ask): where to click, drawn on the screen (showme.py, overlay.py); files found by what's in them
(filecontents.py); a calendar (agenda.py); Spotify playlists (spotify.py); named helpers you talk to while they
work (helpers.py) and a live view of them in the corner (jobview.py, cards.py); a reply written into the email on
your screen (drafts.py); and a meeting helper with live notes and a recap (meeting.py, loopback.py).

This module joins them to her turns with as little as possible in siri.py: quick() for what's said plainly (no
model), the steps the model may plan (registered in toolbox at import, before siri works out its step sets),
prompt_block() for their lines, only when the words may ask for one (after the cached part of her prompt, as
LIST_STEPS is: test_learning.PromptSize holds the rest to its budget), stage() for a change the model planned that's
read back and asked about first, and start() for what runs in the background."""
import datetime as dt
import os
import re
import secrets
import threading
import time

import agenda
import drafts
import filecontents
import helpers
import jobview
import meeting
import showme
import spotify
import toolbox

host = None  # siri, once bind() is called
TRANSCRIBE = [None]  # her speech-to-text, once her ears are loaded (start)
TOKENS = {}  # a change she read back and you said yes to: its token, till when it counts
TOKEN_FOR = 120.0


class Say(Exception):
    """What she says instead, when one of these can't be done: never an error of the PC's own."""

# --------------------------------------------------------------------------- what's said plainly
UI_NOUNS = (r"(?:button|option|setting|settings|menu|icon|tab|link|switch|toggle|box|field|bar|page|panel|section|"
            r"checkbox|dropdown|slider)")
SHOW_ASK = re.compile(
    rf"(?:where (?:do|should|can|would|will) i (?:click|tap|press|turn|switch|toggle|change|set|enable|disable)\b.*|"
    rf"where (?:do|should|can|would) i (?:go|find|look)\b.*\b(?:{UI_NOUNS}|here|on (?:this|the) (?:page|screen)|"
    rf"in (?:this|the) (?:app|window|page|site))\b.*|"
    rf"where(?:'s| is| are) (?:the |my )?.{{1,40}}? {UI_NOUNS}s?(?: (?:here|on (?:this|the) (?:page|screen)))?|"
    rf"show me (?:where|which (?:button|one|option))\b.*|"
    rf"show me how (?:to|do i|can i) (?:turn|switch|enable|disable|change|set|open|find|add|remove|connect|pair|"
    rf"update|delete|rename|share|export|print|save|sign|log|use|get to|go to|make|fix|reset|check|see|hide|show|"
    rf"pin|move|close|mute|unmute|record|download|upload|install|uninstall|create|edit|format|sort|filter|insert)\b.*|"
    rf"point (?:out|to|at) .+|(?:highlight|circle) (?:where|the) .+|"
    rf"guide me (?:through|to|on) .+|walk me through .+|teach me (?:how )?to .+ (?:here|in this app|on this page)|"
    rf"explain (?:this|the|my) (?:screen|page|window|app|site|dashboard|form|interface|chart|graph|table|settings)"
    rf"(?: to me)?|draw (?:it|that|where|how) on (?:the|my) screen.*|"
    rf"how (?:do|can|would) i .+? (?:here|on this (?:page|screen|site)|in this (?:app|window|page|site)))")
NOT_SHOW = re.compile(r"show me where (?:it|that|they|those) (?:is|are)|where is it|show me how (?:much|many|long|old)"
                      r"\b.*|show me (?:where|how) (?:to get|i get) to .+ (?:by|on) (?:car|bus|train|foot|maps?)")
STOP_SHOWING = re.compile(r"stop showing(?: me)?(?: that| it)?|clear (?:the |my )?screen|(?:hide|clear|remove) "
                          r"(?:the |those |your )?(?:rings?|drawings?|circles?|marks?)|stop guiding(?: me)?")
DONE_WORDS = re.compile(r"(?:ok(?:ay)?,? )?(?:got it|i see|thanks?(?: you)?|thank you|that's (?:it|enough|all|fine)|"
                        r"done|found it|never ?mind|stop)")
FILE_NOUNS = re.compile(r"\b(?:files?|documents?|docs?|notes?|pdfs?|slides|presentations?|decks?|spreadsheets?|"
                        r"sheets?|word files?|text files?)\b")
FILE_ASK = re.compile(r"(?:find|search|look for|locate|get|show|which|what|any|are there|is there|do i have|open)\b")
SEARCH_INSIDE = re.compile(r"search (?:inside|in|through|within) (?:my |the )?(?:files|documents|docs|pc|computer)"
                           r"(?: for)? (?P<q>.+)|search (?:my |the )?(?:files|documents|docs) for (?P<q2>[\"'\u201c].+)")
MEETING_START = re.compile(
    r"(?:(?:please )?(?:take|start taking|keep|make|write)(?: some)? notes(?: (?:for|in|of|during|on) (?:this|the|my|our)"
    r" (?:meeting|call|class|lecture|session|interview))?|(?:start|begin|turn on|switch on)(?: the| my)? (?:meeting "
    r"(?:notes|mode|copilot|helper|assistant)|notes (?:for|of) (?:this|the|my) (?:meeting|call))|meeting mode(?: on)?|"
    r"record (?:this|the|my) (?:meeting|call)|be my meeting (?:assistant|copilot|helper)|(?:i'?m|we'?re) (?:in|on|"
    r"joining|starting) a (?:meeting|call),? (?:take|start taking) notes)")
MEETING_STOP = re.compile(
    r"(?:stop|end|finish|wrap up|turn off|switch off|close)(?: taking)?(?: (?:the|my|this|your))? (?:meeting(?: notes| mode|"
    r" copilot| helper| assistant)?|notes|note taking|recording(?: the (?:meeting|call))?)|(?:the |this |our )?(?:meeting|"
    r"call) (?:is |has )?(?:over|done|finished|ended)|meeting mode off|(?:we'?re|i'?m) done with (?:the|this) (?:meeting|"
    r"call)")
THEY_SAID = re.compile(r"what did (?:they|he|she|someone|the other person|the client|my manager|[a-z]+) (?:just )?"
                       r"(?:say|ask)|what was (?:that|the question|their question)|what(?:'s| is) (?:the|their) question|"
                       r"repeat (?:that|what they said|the question)(?: please)?")
WHAT_TO_SAY = re.compile(r"what (?:should|do|can) i (?:say|answer|reply)(?: to (?:that|this|them|him|her))?|how (?:should|"
                         r"do|can) i (?:answer|reply to|respond to) (?:that|this|them|him|her)|help me answer(?: that)?")
OPEN_NOTES = re.compile(r"(?:open|show)(?: me)? (?:the |my )?(?:last |latest )?meeting notes|(?:open|show) (?:the |my )?notes"
                        r" (?:from|of) (?:the|that|my last|the last) (?:meeting|call)")
HELPER_START = re.compile(r"(?:please )?(?:make|create|start|spin up|set up|get|add|launch|send|hire)(?: me)? (?:a |an |"
                          r"another |one )?(?:new )?(?:helper|agent|assistant|worker|bot) (?:called|named) "
                          r"(?P<name>[A-Za-z][\w-]{1,19})(?:,|:| to| and| that| who| which| for| -)? (?P<goal>.+)", re.I)
HELPER_LIST = re.compile(r"(?:what|which|how) (?:helpers|agents)(?: (?:are|do i have))?(?: (?:running|working|doing|going|"
                         r"busy|on))?|(?:what are|how are|how're) my (?:helpers|agents)(?: (?:doing|up to))?|list (?:my |the )?"
                         r"(?:helpers|agents)|(?:tell me about|check on|check) (?:my |the )?(?:helpers|agents)")
JOBVIEW_ON = re.compile(r"(?:show|open|bring up|turn on)(?: me)? (?:the )?(?:mini|live) (?:view|screen|window)|show me (?:what "
                        r")?(?:the |my )?(?:helpers?|agents?|background (?:jobs?|tasks?)) (?:are |is )?(?:doing|working|"
                        r"live)|(?:show|watch) (?:the |my )?(?:helpers?|agents?) (?:live|work(?:ing)?|in the corner)")
JOBVIEW_OFF = re.compile(r"(?:hide|close|turn off|put away|stop showing)(?: me)?(?: the)? (?:mini|live) (?:view|screen|window)|"
                         r"(?:hide|close)(?: the)? (?:helper|job|agent|task)s? (?:card|view|window)")
CAL_LIST = re.compile(
    r"what(?:'s| is| do i have| have i got| are my plans)(?: (?:on|in|for))?(?: my)? (?:calendar|agenda|schedule|diary)"
    r"(?: (?:for|on))?(?: (?P<when>.+))?|what (?:do i have|have i got|meetings do i have|events do i have|"
    r"appointments do i have|(?:is|'s) (?:on|happening) for me)(?: (?:on|for|at))? (?P<when2>today|tonight|tomorrow|"
    r"this week|next week|this weekend|this evening|(?:on )?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"on the \d+\w*|on \d+ \w+)|(?:read|check|show|open)(?: me)? my (?:calendar|agenda|schedule|diary)(?: for)?"
    r"(?: (?P<when3>.+))?|(?:do i have|have i got) any (?:meetings|events|appointments|plans)(?: (?P<when4>.+))?|"
    r"(?:any|anything on my calendar|anything planned) (?P<when5>today|tonight|tomorrow|this week|this weekend)")
CAL_NEXT = re.compile(r"what(?:'s| is) (?:my |the )?next (?:meeting|event|appointment|call|thing on my calendar)(?: today)?|"
                      r"when(?:'s| is) my next (?:meeting|event|appointment|call)|what(?:'s| is) (?:coming )?up next(?: on "
                      r"my calendar)?")
CAL_FREE = re.compile(r"am i (?:free|busy|available)(?P<when> .+)?|do i have (?:anything|something|a meeting|meetings) "
                      r"(?P<when2>(?:at|on|tomorrow|today|tonight|this|next|in the) .*)|is (?:my )?(?P<when3>.+) free")
CAL_WHEN = re.compile(r"when(?:'s| is| was| do i have| have i got)(?: my| the| our)? (?P<what>.+?)(?: on my calendar)?")
CAL_ADD = re.compile(r"(?:please )?(?:add|put|create|make|schedule|book|set up|pencil in|block(?: out)?|note down|save)\b.+",
                     re.I)
EVENT_NOUNS = re.compile(r"\b(?:calendar|diary|agenda|meeting|appointment|call|lunch|dinner|breakfast|brunch|interview|"
                         r"event|party|birthday|anniversary|flight|train|bus|class|lecture|session|demo|review|standup|"
                         r"stand-up|sync|catch ?up|catch-up|date|visit|trip|wedding|gym|workout|yoga|exam|test|deadline|"
                         r"presentation|webinar|doctor|dentist|haircut|match|concert|movie|show|game|function|pooja|puja|"
                         r"ceremony|shift|appointment|conference|offsite|1:1|one on one|one-on-one)\b", re.I)
NOT_EVENTS = re.compile(r"\b(?:remind|reminder|timer|alarm|alert|to-?do|to do list|shopping list|list|notes?|startup|"
                        r"bookmark|favou?rites?|contact|number|playlist|queue|cart|basket|command|backup|task|watch|skill|"
                        r"routine|words?|dictionary|memory|remember)\b", re.I)
CAL_MOVE = re.compile(r"(?:please )?(?:move|push|shift|reschedule|postpone|bring forward|change|delay)(?: back)?"
                      r"(?: my| the| our)? (?P<what>.+?) (?P<how>to|till|until|for|by|back to) (?P<when>.+)", re.I)
CAL_CANCEL = re.compile(r"(?:please )?(?:cancel|delete|remove|clear|drop|scrap|call off)(?: my| the| our)? (?P<what>.+?)"
                        r"(?: (?:from|off|in|on) (?:my |the )?calendar)?", re.I)
NOT_CANCEL = re.compile(r"\b(?:timers?|reminders?|alarms?|tasks?|task \d+|jobs?|watch(?:es|ing)?|shut ?down|restart|sleep|"
                        r"download|install|message|it all|everything|that|this|it|them|music|song|video|order|"
                        r"subscription|notes?|helpers?|agents?|meeting notes|recording)\b", re.I)
CAL_FEED = re.compile(r"(?:(?:add|connect|link|use|read|sync)(?: my)?(?: google| outlook| icloud| work| office| school)?"
                      r" calendar(?: feed| link| address| url)?:?\s*)?(?P<url>(?:https?|webcal)://\S+)", re.I)
CAL_FEED_OFF = re.compile(r"(?:remove|disconnect|forget|unlink|stop reading)(?: my)?(?: google| outlook| icloud)? "
                          r"calendars?(?: feeds?| links?| addresses?)?")
CAL_HOWTO = re.compile(r"(?:how (?:do|can) i |can you |please )?(?:connect|link|add|sync|use|read) (?:my |the )?(?:google|"
                       r"outlook|icloud|work|office) calendar(?: to you| with you| here)?")
SPOTIFY_PLAY = re.compile(
    r"(?:play|put on|start|shuffle|listen to)(?: me)? (?P<q>.+?) (?:on|in|from|with|using|via) spotify(?P<web> web|"
    r"'s website| website| on the web| in the browser)?|spotify,? play (?P<q2>.+)|(?:play|put on|shuffle) (?P<q3>my "
    r"(?:spotify )?(?:liked|saved|favou?rite) (?:songs|tracks|music)|my spotify(?: liked songs)?)", re.I)
SPOTIFY_KIND = re.compile(r"\b(?:the )?(?P<kind>playlist|album|artist|podcast|song|track|mix|radio)\b(?: called| named)?",
                          re.I)

# --------------------------------------------------------------------------- the steps the model may plan
SHOW_WORDS = re.compile(r"\b(?:where|show|point|highlight|guide|walk|explain|draw|click)\b", re.I)
DRAFT_WORDS = re.compile(r"\b(?:reply|respond|answer|write back|draft)\b", re.I)
MEETING_WORDS = re.compile(r"\b(?:meeting|notes|call|record|recap)\b", re.I)
LINES = {
    "show": '{"do":"show","task":"where to click to turn on Bluetooth"}  point it out on their screen, rings and steps '
            'drawn over it, never clicking for them: "where do I click", "show me how", "explain this page"',
    "agenda": '{"do":"agenda","when":"tomorrow"}  their calendar for a day ("today", "Friday", "this week"): its '
              'events come back',
    "event": '{"do":"event","action":"add","title":"Lunch with Sam","start":"2026-10-29T13:00","minutes":60}  an event '
             'on their calendar, start in local ISO time; action "move" with "new_start", or "cancel": she reads it '
             'back and asks first',
    "spotify": '{"do":"spotify","query":"lofi beats","kind":"playlist"}  play it in the Spotify app: a song, album, '
               'artist, podcast or playlist ("liked songs" for theirs)',
    "helper": '{"do":"helper","action":"start","name":"Researcher","goal":"find the best budget laptops"}  a named '
              'helper, a job in the background they talk to by name; action "tell" (with "words"), "status" or "stop"',
    "draft_reply": '{"do":"draft_reply","text":"","about":"say yes but ask to move it to Friday"}  a reply written into '
                   'the open email\'s reply box, never sent: "text" their exact words, else "about" what it should say',
    "meeting": '{"do":"meeting","action":"start"}  notes of the meeting or call they\'re in, both sides of it; action '
               '"stop" for the recap',
    "files_inside": '{"do":"files_inside","query":"tokyo trip"}  their files by the words inside them: the matches come '
                    'back numbered',
    "jobview": '{"do":"jobview","on":true}  the live view of their helpers and background jobs in the corner of the '
               'screen ("on": false hides it)',
}
WORDS_FOR = {
    "show": re.compile(r"\b(?:where (?:do|should|can|would) i|show me|point (?:out|to|at)|highlight|guide me|"
                       r"walk me through|explain (?:this|the|my) (?:screen|page|window|app)|draw)\b", re.I),
    "agenda": re.compile(r"\b(?:calendar|agenda|diary|appointments?|meetings?|events?|busy|free (?:at|on|tomorrow|"
                         r"today|this)|reschedule|postpone|booked|plans? for)\b", re.I),
    "spotify": re.compile(r"\b(?:spotify|playlists?)\b", re.I),
    "helper": re.compile(r"\b(?:helpers?|agents?)\b", re.I),
    "draft_reply": re.compile(r"\b(?:reply|respond|write back|draft)\b|\banswer (?:this|the|him|her|them)\b", re.I),
    "meeting": re.compile(r"\b(?:meeting|minutes|recap|take notes|notes of|transcript)\b", re.I),
    "files_inside": re.compile(r"(?=.*\b(?:files?|documents?|docs?|notes|pdfs?|slides|presentations?|spreadsheets?)\b)"
                               r"(?=.*\b(?:about|mention\w*|contain\w*|says?|inside|talks? about|refers? to)\b)", re.I),
    "jobview": re.compile(r"\b(?:mini view|live view|in the corner|watch (?:the|my) (?:helpers?|jobs?|agents?))\b", re.I),
}
WORDS_FOR["event"] = WORDS_FOR["agenda"]
MEETING_ASKS = re.compile(r"\b(?:they|he|she|someone|said|asked|say|decided|decisions?|action items?|so far|meeting|"
                          r"call|notes|summar\w+|recap|question)\b", re.I)


def bind(module):
    global host
    host = module
    for m in (showme, spotify, helpers, jobview, meeting, drafts):
        m.bind(module)


def _plan(steps=(), say=""):
    return {"steps": [dict(s) for s in steps], "say": say}


def token():
    """A one-time key for a change she read back: only a yes to her question carries it (stage, _event)."""
    now = time.time()
    for k in [k for k, until in TOKENS.items() if until < now]:
        TOKENS.pop(k, None)
    key = secrets.token_hex(6)
    TOKENS[key] = now + TOKEN_FOR
    return key


def _take(key):
    until = TOKENS.pop(str(key or ""), 0)
    return until >= time.time()


# --------------------------------------------------------------------------- the step handlers
def _show(step):
    return showme.show(step.get("task") or step.get("goal") or "", host.NOTIFY[0])


def _agenda(step):
    a, b, label = agenda.day_range(str(step.get("when") or step.get("day") or "today"))
    found, missing = agenda.between(a, b)
    return {"agenda": label, "events": [{"title": o["title"], "when": agenda.said(o, day=True).replace(
        o["title"] + " ", "", 1), "where": o.get("where") or "", "calendar": o.get("source") or "harry"}
        for o in found[:20]] or "nothing", **({"unread": missing} if missing else {})}


def _parse_start(value):
    try:
        got = dt.datetime.fromisoformat(str(value).strip().replace("Z", ""))
        return got.replace(tzinfo=None)
    except (TypeError, ValueError):
        got = agenda.when(str(value or ""))
        return got["start"] if got else None


def _event(step):
    action = str(step.get("action") or "add").lower()
    if action in ("add", "create", "new"):
        start = _parse_start(step.get("start") or step.get("when"))
        if start is None:
            raise RuntimeError("I didn't catch when it is")
        minutes = step.get("minutes")
        end = _parse_start(step["end"]) if step.get("end") else \
            (start + dt.timedelta(minutes=int(minutes)) if str(minutes or "").isdigit() else None)
        all_day = bool(step.get("all_day")) or (len(str(step.get("start") or "")) == 10)
        try:
            o = agenda.add(step.get("title") or step.get("name"), start, end, all_day, step.get("where") or "")
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        return f"added {o['title']} {o['start']}"
    if not _take(step.get("token")):  # a move or a cancel only ever on a yes to her own question (stage)
        raise RuntimeError("I read a change to your calendar back before I make it. Ask me again")
    if action in ("move", "change", "reschedule"):
        o = agenda.change(step["id"], start=_parse_start(step["new_start"]),
                          end=_parse_start(step["new_end"]) if step.get("new_end") else None)
        return f"moved {o['title']} {o['start']}"
    if action in ("cancel", "delete", "remove"):
        agenda.remove(step["id"])
        return f"deleted {step['id']}"
    raise RuntimeError("I can add, move or cancel an event")


def _spotify(step):
    query = str(step.get("query") or step.get("name") or "").strip()
    kind = spotify.KINDS.get(str(step.get("kind") or "").lower(), "")
    if not spotify.installed():
        raise RuntimeError("Spotify isn't installed. Say install Spotify, or ask me to play it on Spotify's website")
    return spotify.play(query, kind, host.NOTIFY[0])


def _helper(step):
    action, name = str(step.get("action") or "start").lower(), str(step.get("name") or "").strip()
    if action == "start":
        try:
            line = helpers.start(name, step.get("goal") or step.get("task") or "")
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
    elif action == "tell":
        line = helpers.tell(name, step.get("words") or step.get("text") or "") or f"I don't have a helper called {name}"
    elif action == "stop":
        line = helpers.stop(name) or f"I don't have a helper called {name}"
    else:
        line = helpers.status(name) or f"I don't have a helper called {name}"
    return line


def _draft(step):
    line = drafts.reply(agent_words(), step.get("about") or "", step.get("text") or "")
    host.say(line, host.NOTIFY[0])
    return "reply written"


def agent_words():
    import agent
    return agent.SAID.get() or ""


def _meeting(step):
    action = str(step.get("action") or "start").lower()
    if action == "start":
        if TRANSCRIBE[0] is None:
            raise RuntimeError("My ears aren't ready yet. Ask me again in a moment")
        return meeting.start_meeting(TRANSCRIBE[0])
    if action == "open":
        path = meeting.last_file()
        if not path:
            raise RuntimeError("I haven't kept any meeting notes yet")
        os.startfile(path)
        return path
    said = meeting.stop_meeting()
    if said is None:
        raise RuntimeError("I wasn't taking notes")
    host.say(said, host.NOTIFY[0])
    return "notes saved"


def _files_inside(step):
    query = str(step.get("query") or "").strip()
    found = filecontents.search(f"files about {query}" if not filecontents.wanted(query) else query)
    import filesearch
    return {"files_inside": query, "found": filesearch.for_model(found) or "no file has those words in it"}


def _jobview(step):
    want = step.get("on", True) not in (False, "off", "false", 0)
    return jobview.show(want)


def register():
    """Her new steps, in the registry (toolbox), each decided once: what it changes, the words it needs said without
    her name, and how she asks about it."""
    def add(name, effect, asks_for, confirm, handler, **more):
        if toolbox.get(name) is None:
            toolbox.register(name, effect=effect, asks_for=asks_for, confirm=confirm, handler=handler,
                             line=LINES[name], gated_by="EXTRA_STEPS", **more)
    add("show", "reversible", SHOW_WORDS, "Should I show you on the screen?", _show, speak="first", background="never")
    add("agenda", "info", None, None, _agenda, parallel_ok=True, taints=True, background="never")
    add("event", "own_data", None, "Should I change your calendar?", _event, speak="after", background="never")
    add("spotify", "reversible", None, None, _spotify, read_safe=True, routine_ok=True, background="never")
    add("helper", "acts", None, "Should I start that helper?", _helper, speak="after", background="never")
    add("draft_reply", "acts", DRAFT_WORDS, "Should I write that reply in the email?", _draft, background="never")
    add("meeting", "own_data", MEETING_WORDS, "Should I take notes of this meeting?", _meeting, speak="after",
        background="never")
    add("files_inside", "info", None, None, _files_inside, parallel_ok=True, taints=True, background="never")
    add("jobview", "reversible", None, None, _jobview, read_safe=True, background="never")


register()


# --------------------------------------------------------------------------- what the planner's told, when it may help
def prompt_block(text):
    """The lines for her new steps the words may ask for, and what's going on with them: "" for most requests."""
    t = str(text or "")
    kinds = [k for k in LINES if WORDS_FOR[k].search(t)]
    names = [n for n in helpers.names() if re.search(rf"\b{re.escape(n)}\b", t, re.I)]
    if names and "helper" not in kinds:
        kinds.append("helper")
    if meeting.on() and MEETING_ASKS.search(t) and "meeting" not in kinds:
        kinds.append("meeting")
    if not kinds:
        return ""
    out = "\n\n" + "\n".join(LINES[k] for k in kinds)
    if "helper" in kinds:
        going = [f"{e['name']} ({helpers.doing(e, row)})" for e, row in helpers.live()]
        if going:
            out += "\nTheir helpers now: " + "; ".join(going) + "."
    if "meeting" in kinds and meeting.on():
        out += meeting.context_lines()
    return out


# --------------------------------------------------------------------------- what's said plainly, done with no model
POLITE_HEAD = re.compile(r"^(?:(?:hey|hi|ok|okay|so)[,!.]?\s+)?(?:(?:harry|jev|jarvis)[,!.]?\s+)?(?:(?:can|could|would|"
                         r"will) you\s+(?:please\s+)?|please\s+)", re.I)
POLITE_TAIL = re.compile(r"[,\s]+(?:please|for me)[.!?]*$", re.I)  # never "thanks": "reply saying thanks" means it


def quick(words, gate=False):
    """A plan for one of these said plainly, or None. gate "cold": said without her name, so only what reads, and
    never what acts on the screen or starts something."""
    raw = " ".join(str(words or "").split()).strip()
    raw = POLITE_TAIL.sub("", POLITE_HEAD.sub("", raw)).strip() or raw  # "can you ... please", its capitals kept
    if not raw:
        return None
    t = host.plain(raw)
    named = gate != "cold"
    low = raw.lower().strip(" .!?")
    # guiding you on the screen: the words that end it
    if showme.guiding():
        if STOP_SHOWING.fullmatch(t):
            showme.stop()
            return _plan(say="Okay.")
        if DONE_WORDS.fullmatch(t):
            showme.stop()  # and on to her usual answer to "thanks"
    for fn in (_meeting_quick, _helper_quick, _calendar_quick, _spotify_quick, _files_quick, _show_quick,
               _draft_quick, _jobview_quick):
        try:
            plan = fn(raw, t, low, named)
        except (Say, ValueError) as exc:  # hers to say: "That isn't a calendar address."
            return _plan(say=f"{str(exc).rstrip('.')}.")
        except Exception as exc:  # the PC's own trouble: the model has the turn instead
            print(f"  {fn.__name__}: {exc!r}")
            return None
        if plan:
            return plan
    return None


def _meeting_quick(raw, t, low, named):
    if MEETING_START.fullmatch(t) and named:
        if meeting.on():
            return _plan(say=f"I'm already taking notes, {meeting.NOW[0].minutes()} minutes in.")
        say = (meeting.FIRST_TIME + " I'll only answer to my name till you say stop.") \
            if not host.settings.get("meeting_told") else "Taking notes. I'll only answer to my name till you say stop."
        return _plan([{"do": "meeting", "action": "start"}], say)
    if MEETING_STOP.fullmatch(t) and (named or meeting.on()):
        if not meeting.on():
            return _plan(say="I'm not taking notes right now.")
        host.say("Okay, writing up the notes.", host.NOTIFY[0])
        said = meeting.stop_meeting() or "I wasn't taking notes."
        if said.endswith("Want me to open them?"):
            return {"steps": [], "say": said, "exact": True,
                    "confirm": _plan([{"do": "meeting", "action": "open"}], "Opening them.")}
        return {**_plan(say=said), "exact": True}
    if OPEN_NOTES.fullmatch(t) and named:
        return _plan([{"do": "meeting", "action": "open"}], "Opening them.") if meeting.last_file() else \
            _plan(say="I haven't kept any meeting notes yet.")
    if meeting.on() and named and THEY_SAID.fullmatch(t):
        said = meeting.NOW[0].last_from("Them", 2)
        if not said:
            return _plan(say="I haven't heard them say anything yet.")
        return {**_plan(say=f"They said: \u201c{said[-1]}\u201d"), "exact": True}
    if meeting.on() and named and WHAT_TO_SAY.fullmatch(t) and meeting.NOW[0].suggestion:
        return {**_plan(say=f"You could say: {meeting.NOW[0].suggestion[1]}"), "exact": True}
    return None


def _named_helper(name):
    return next((n for n in helpers.names() if n.lower() == str(name or "").lower()), None)


def _helper_quick(raw, t, low, named):
    m = HELPER_START.fullmatch(raw.strip(" .!?"))
    if m and named:
        if not helpers.good_name(m["name"]):
            return None
        return _plan([{"do": "helper", "action": "start", "name": m["name"], "goal": m["goal"]}],
                     f"{m['name'][:1].upper() + m['name'][1:]}'s on it. Ask me how it's doing any time.")
    if HELPER_LIST.fullmatch(t):
        return _plan(say=helpers.listing())
    if not helpers.names():
        return None
    m = re.fullmatch(r"(?:how(?:'s| is) (?P<a>\w+)(?: (?:doing|getting on|going|coming along|progressing))?|what(?:'s| is) "
                     r"(?P<b>\w+) (?:doing|up to|working on)|(?:any )?news from (?P<c>\w+)|is (?P<d>\w+) (?:done|finished|"
                     r"ready)(?: yet)?|check on (?P<e>\w+))", t)
    if m:
        name = _named_helper(next(g for g in m.groups() if g))
        if name:
            return _plan(say=helpers.status(name))
    m = re.fullmatch(r"(?:stop|cancel|kill|end|halt|fire) (?:the )?(?P<name>\w+)(?: helper| agent)?", t)
    if m and _named_helper(m["name"]):
        return _plan([{"do": "helper", "action": "stop", "name": _named_helper(m["name"])}], "")
    m = re.fullmatch(r"(?:tell|ask|remind|let) (?P<name>\w+) (?:to |that |know |about )?(?P<msg>.+)", raw.strip(" .!?"),
                     re.I) or re.fullmatch(r"(?P<name>\w+),? (?P<msg>(?:also|now|instead|please|and|focus|look|check|try|"
                                           r"don't|do not|use|stick|only|add|skip|make|keep|change|switch|include|"
                                           r"ignore|write|find|search|compare|save|wait|hold|pause|start|go)\b.+)",
                                           raw.strip(" .!?"), re.I)
    if m and _named_helper(m["name"]):
        name = _named_helper(m["name"])
        line = helpers.tell(name, m["msg"], named)
        return _plan(say=line) if line else None
    return None


def _when_of(*parts):
    return next((p for p in parts if p), "") or ""


def _calendar_quick(raw, t, low, named):
    m = CAL_FEED.fullmatch(raw.strip(" .")) if named else None
    if m and ("calendar" in low or "/ical/" in low or low.endswith(".ics")):
        name, n = agenda.add_feed(m["url"])
        return _plan(say=f"Done, I can read your {name} calendar now: {n} events in it. I'll check it every 10 "
                         f"minutes, and never change anything there.")
    if CAL_FEED_OFF.fullmatch(t) and named:
        n = agenda.remove_feeds()
        return _plan(say="Okay, I've stopped reading your other calendars." if n else
                     "I'm only reading your calendar on this PC.")
    if CAL_HOWTO.fullmatch(t) and named:
        return _plan(say="In Google Calendar on the web, open Settings, pick your calendar, and copy its secret "
                         "address in iCal format. Then type add my calendar and paste it in my typing box, or send it "
                         "to me from your phone. Outlook has the same under Settings, Calendar, Shared calendars, "
                         "Publish a calendar.")
    m = CAL_NEXT.fullmatch(t)
    if m:
        o = agenda.next_up()
        if not o:
            return _plan(say="Nothing coming up on your calendar.")
        agenda.LAST.update(event=o, at=time.time())
        return _plan(say=f"Next up: {agenda.said(o)}.")
    briefing = any(getattr(host, n, None) is not None and getattr(host, n).fullmatch(t) for n in ("BRIEF_ASK",
                                                                                                  "MISSED_ASK"))
    m = None if briefing else CAL_LIST.fullmatch(t)  # "what have I got on today?" is her briefing, calendar and all
    if m:
        a, b, label = agenda.day_range(_when_of(*m.groups()) or "today")
        found, missing = agenda.between(a, b)
        if not found and label == "today":
            later = agenda.next_up()
            if later:
                agenda.LAST.update(event=later, at=time.time())
                return _plan(say=f"Nothing else today. Next up: {agenda.said(later)}.")
        return _plan(say=agenda.listing(found, label, missing))
    m = CAL_FREE.fullmatch(t)
    if m:
        got = agenda.when(_when_of(*m.groups()) or "now")
        if got is None:
            return None
        start = got["start"] if not got["all_day"] else dt.datetime.combine(got["date"], dt.time(9))
        end = got["end"] or (start + dt.timedelta(hours=1) if not got["all_day"] else
                             dt.datetime.combine(got["date"], dt.time(22)))
        busy = agenda.free_at(start, end)
        when = ("then" if not got["all_day"] else agenda._day_said(start, dt.datetime.now()))
        if not busy:
            return _plan(say=f"Yes, you're free {when}." if when != "then" else
                         f"Yes, you're free at {agenda._clock_said(start)}.")
        o = busy[0]
        agenda.LAST.update(event=o, at=time.time())
        return _plan(say=f"You've got {o['title']} from {agenda._clock_said(o['start'])} to "
                         f"{agenda._clock_said(o['end'])}.")
    m = CAL_MOVE.fullmatch(raw.strip(" .!?"))
    if m and named:
        o = agenda.find(m["what"])
        if o:
            return _move(o, m["how"], m["when"])
    m = CAL_CANCEL.fullmatch(raw.strip(" .!?"))
    if m and named and not NOT_CANCEL.search(m["what"]):
        o = agenda.find(m["what"])
        by_time = re.search(r"\b\d{1,2}(?:[:.]\d\d)? ?(?:am|pm|a\.m\.|p\.m\.|o'clock)\b", m["what"], re.I)
        if o and (EVENT_NOUNS.search(m["what"]) or _close(o["title"], m["what"]) or by_time):
            return _cancel(o)
    m = CAL_WHEN.fullmatch(t)
    if m and not re.search(r"\b(?:next|last)\b.*\b(?:match|game|episode|season|film|movie|launch|release|sale|update|"
                           r"election|holiday|festival|eclipse|train|flight|bus)\b", m["what"]):
        o = agenda.find(m["what"])
        if o and _close(o["title"], m["what"]):
            agenda.LAST.update(event=o, at=time.time())
            return _plan(say=f"{agenda.said(o)}.")
    if named and CAL_ADD.fullmatch(raw.strip(" .!?")) and EVENT_NOUNS.search(raw) and not NOT_EVENTS.search(raw):
        e = agenda.parse_event(raw)
        if e is None:
            return None
        if agenda.WORDS_GOOGLE.search(raw) and agenda.feeds():
            url = agenda.google_link(e["title"], e["start"], e["end"], e["all_day"])
            return _plan([{"do": "website", "url": url}], "I've filled it in on Google Calendar. Press Save to add it.")
        step = {"do": "event", "action": "add", "title": e["title"], "start": e["start"].strftime("%Y-%m-%dT%H:%M"),
                "all_day": e["all_day"]}
        if e["end"]:
            step["end"] = e["end"].strftime("%Y-%m-%dT%H:%M")
        when = agenda.said({**e, "where": ""}, day=True)[len(e["title"]) + 1:]
        return _plan([step], f"Added {e['title']} {when}." + ("" if not e["all_day"] else ""))
    return None


def _close(title, words):
    """True if the words name the event: one of their longer words is in its title."""
    have = set(re.findall(r"[a-z0-9']+", str(title).lower()))
    want = {w for w in re.findall(r"[a-z0-9']+", str(words).lower()) if len(w) > 2} - \
        {"the", "my", "our", "with", "meeting", "event", "appointment", "call", "calendar", "next", "today",
         "tomorrow"}
    return bool(want & have) or bool(re.search(r"\b(?:meeting|appointment|event|call)\b", str(words), re.I))


def _move(o, how, words, new=None):
    """Her question about moving an event, with its yes ready, or a page to move it on where it lives. new: where to,
    when the model already said it exactly."""
    now = dt.datetime.now()
    start = o["start"]
    words = " ".join(str(words or "").split())
    shift = agenda.LENGTH.search("for " + words) if how == "by" and new is None else None
    if new is not None:
        pass
    elif shift:
        n = shift["n"] or "1"
        n = 0.5 if n.startswith("half") else 1 if n in ("a", "an", "one") else 2 if n == "two" else \
            3 if n == "three" else float(n) if re.fullmatch(r"\d+(?:\.\d+)?", n) else 1
        minutes = 30 if shift["half"] else 90 if shift["hr"] else int(n * (60 if shift["u"][0] == "h" else 1))
        new = start + dt.timedelta(minutes=-minutes if re.search(r"\b(?:earlier|forward|back)\b", words) else minutes)
    else:
        # "to 4" is a time: the same day. Said bare, as "at 4" would be
        got = agenda.when(words, now) or (agenda.when("at " + words, now) if re.match(r"\d", words) else None)
        if got is None:
            return None
        if got["clock"] is not None and not agenda.DAY.search(words.lower()):
            new = dt.datetime.combine(start.date(), dt.time(*got["clock"]))  # "to 4": the same day
        elif got["clock"] is None:
            new = dt.datetime.combine(got["date"], start.time())  # "to Friday": the same time
        else:
            new = got["start"]
    if o.get("id") is None:  # from Google or Outlook: moved there
        url = agenda.google_day(start) if (o.get("source") or "").lower() == "google" else None
        if url:
            return _plan([{"do": "website", "url": url}], f"{o['title']} is in your Google calendar, so I've opened "
                                                          f"that day there for you to move it.")
        return _plan(say=f"{o['title']} is in your {o.get('source') or 'other'} calendar, so it needs moving there.")
    length = (o["end"] - o["start"]) if o.get("end") else dt.timedelta(hours=1)
    key = token()
    question = f"Move {o['title']} from {agenda._day_said(start, now)} at {agenda._clock_said(start)} to " \
               f"{agenda._day_said(new, now)} at {agenda._clock_said(new)}?"
    step = {"do": "event", "action": "move", "id": o["id"], "new_start": new.strftime("%Y-%m-%dT%H:%M"),
            "new_end": (new + length).strftime("%Y-%m-%dT%H:%M"), "token": key}
    return {"steps": [], "say": question, "exact": True,
            "confirm": _plan([step], f"Done, {o['title']} is {agenda._day_said(new, now)} at "
                                     f"{agenda._clock_said(new)} now.")}


def _cancel(o):
    now = dt.datetime.now()
    if o.get("id") is None:
        url = agenda.google_day(o["start"]) if (o.get("source") or "").lower() == "google" else None
        if url:
            return _plan([{"do": "website", "url": url}], f"{o['title']} is in your Google calendar, so I've opened "
                                                          f"that day there for you.")
        return _plan(say=f"{o['title']} is in your {o.get('source') or 'other'} calendar, so it's cancelled there.")
    key = token()
    when = "all day" if o["all_day"] else f"at {agenda._clock_said(o['start'])}"
    return {"steps": [], "say": f"Delete {o['title']} on {agenda._day_said(o['start'], now)} {when} from your "
                                f"calendar?", "exact": True,
            "confirm": _plan([{"do": "event", "action": "cancel", "id": o["id"], "token": key}],
                             f"Deleted {o['title']}.")}


def _spotify_quick(raw, t, low, named):
    m = SPOTIFY_PLAY.fullmatch(" ".join(raw.split()).strip(" .!?"))  # as said, so "Discover Weekly" keeps its capitals
    if not m or not named:
        return None
    q = (m["q"] or m["q2"] or m["q3"] or "").strip(" ,")
    kind = ""
    k = SPOTIFY_KIND.search(q)
    if k:
        kind = spotify.KINDS.get(k["kind"].lower(), "")
        q = " ".join((q[:k.start()] + " " + q[k.end():]).replace(" my ", " ").split()).strip()
        q = re.sub(r"^(?:my|the|some|a|an) ", "", q, flags=re.I).strip() or q
    if not q:
        return None
    if spotify.LIKED.fullmatch(f"my {q}") or spotify.LIKED.fullmatch(q):
        q = "liked songs"
    if m["web"]:
        return _plan([{"do": "website", "url": spotify.web(q, kind)},
                      {"do": "screen", "task": f"On Spotify's web player, play the {kind or 'top result'} for {q}"}],
                     "")
    if not spotify.installed():
        plan = host.stage_install("Spotify")
        if plan and plan.get("confirm"):
            plan = {**plan, "say": "Spotify isn't on this PC yet. " + str(plan.get("say") or ""), "exact": True}
            return plan
        return _plan(say="Spotify isn't installed. Say install Spotify, or ask me to play it on Spotify's website.")
    return _plan([{"do": "spotify", "query": q, "kind": kind}], "")


def _files_quick(raw, t, low, named):
    m = SEARCH_INSIDE.fullmatch(raw.strip(" .!?").lower())
    if not m and not (FILE_ASK.match(t) and FILE_NOUNS.search(t) and filecontents.INSIDE.search(t)):
        return None
    said = raw if not m else f"files about {m['q'] or m['q2']}"
    got = filecontents.wanted(said)
    if got is None:
        return None
    try:
        found = filecontents.search(said)
    except RuntimeError as exc:  # "Windows Search isn't answering, so I can't look inside your files"
        raise Say(str(exc)) from exc
    say = filecontents.said(found, got[2])
    if not found:
        return _plan(say=say)
    return {"steps": [], "say": say, "confirm": _plan([{"do": "open_file", "n": 1}])}


def _show_quick(raw, t, low, named):
    if not named or NOT_SHOW.fullmatch(t) or not SHOW_ASK.fullmatch(t):
        return None
    if not host.settings.get("vision"):
        return _plan(say="Looking at the screen is turned off in Settings, so I can't show you.")
    return _plan([{"do": "show", "task": raw}], "")


def _draft_quick(raw, t, low, named):
    if not named:
        return None
    text = low
    lit = drafts.LITERAL.fullmatch(" ".join(raw.split()))
    gen = re.fullmatch(r"(?:please )?(?:write|draft|compose|type)(?: me)? (?:a |an )?(?:reply|response|answer)(?: to "
                       r"(?:this|it|him|her|them|the (?:e-?mail|mail)|this (?:e-?mail|mail)))?(?:,? (?:saying|that says?|"
                       r"that|telling (?:him|her|them)|to say|about|and say|and tell (?:him|her|them)) (?P<about>.+))?|"
                       r"(?:reply|respond|answer)(?: to)? (?:this|the) (?:e-?mail|mail)(?:,? (?:saying|telling (?:him|"
                       r"her|them)|and say|and tell (?:him|her|them)|that) (?P<about2>.+))?", text)
    if not lit and not gen:
        return None
    mailish = bool(re.search(r"\b(?:e-?mail|mail|gmail|outlook)\b", text))
    try:  # just told someone replied on WhatsApp: "reply saying ..." is to them, whatever's in front
        who = host.REPLYING.get(host.origin()) or {}
        if who.get("contact") and time.time() < who.get("until", 0) and not mailish:
            return None
    except Exception:
        pass
    try:
        mail = drafts.mail_window()
    except Exception as exc:
        print(f"  draft: couldn't tell what's in front ({exc!r})")
        mail = None
    if mail is None:
        if mailish:
            return _plan(say=drafts.NO_MAIL)
        return None  # a reply in a chat: her messaging has that
    own = drafts.literal(raw)
    about = (gen["about"] or gen["about2"] or "") if gen else (lit["text"] if lit and not own else "")
    return _plan([{"do": "draft_reply", "text": own or "", "about": about or raw}], "")


def _jobview_quick(raw, t, low, named):
    if JOBVIEW_OFF.fullmatch(t):
        return _plan([{"do": "jobview", "on": False}], "Okay, I've put the live view away.")
    if JOBVIEW_ON.fullmatch(t) and named:
        line = jobview.show(True)
        listing = helpers.listing() if helpers.live() else ""
        return _plan(say=(listing + " " + line).strip() if listing else line)
    return None


# --------------------------------------------------------------------------- a change the model planned, asked first
def stage(plan, words=""):
    """The model's plan with a move or a cancel of a calendar event turned into her question about it, read back,
    whose yes alone carries the change (token). Anything else as it was."""
    steps = plan.get("steps") or []
    for i, s in enumerate(steps):
        if not isinstance(s, dict) or s.get("do") != "event":
            continue
        action = str(s.get("action") or "add").lower()
        if action in ("add", "create", "new"):
            continue
        if s.get("token") and s["token"] in TOKENS:
            continue  # her own, from a question you said yes to
        o = None
        if s.get("id"):
            o = next((e for e in agenda.between(dt.datetime.now() - dt.timedelta(days=1),
                                                dt.datetime.now() + dt.timedelta(days=60))[0]
                      if e.get("id") == s["id"]), None)
        o = o or agenda.find(" ".join(str(s.get(k) or "") for k in ("title", "start", "when")).strip() or words)
        if o is None:
            return _plan(say="I couldn't find that on your calendar.")
        if action in ("move", "change", "reschedule"):
            new = _parse_start(s.get("new_start") or s.get("to") or s.get("start"))
            if new is None:
                return _plan(say="When should it move to?")
            return _move(o, "to", "", new=new) or _plan(say="When should it move to?")
        return _cancel(o)
    return plan


# --------------------------------------------------------------------------- the rest of her day
def hush():
    """True while she takes meeting notes: only her name counts, so the meeting's talk is never a request."""
    return meeting.on()


def brief_line(now=None):
    """Today's calendar for her briefing, or ""."""
    try:
        return agenda.today_line()
    except Exception as exc:
        print(f"  briefing's calendar: {exc!r}")
        return ""


def result_line(task, text, ok):
    """How a helper's job ended, by its name: "Researcher's done. ..." None for any other task."""
    try:
        name = helpers.name_of(task.get("id"))
    except Exception:
        name = None
    if not name:
        return None
    text = " ".join(str(text or "").split())[-240:]
    return (f"{name}'s done. {text}" if text else f"{name}'s done.") if ok else \
        (f"{name} couldn't finish. {text}" if text else f"{name} couldn't finish.")


def _reminders():
    """A word before each thing on your calendar starts, said once she's free."""
    time.sleep(45)
    while True:
        try:
            if host.settings.get("heads_ups") and not host.paused() and not meeting.on():
                for _, line in agenda.due():
                    host.ANNOUNCE.put(line)
        except Exception as exc:
            print(f"  calendar reminders: {exc!r}")
        time.sleep(30)


_started = []


def start(transcribe=None):
    """Once her ears are loaded: what runs in the background."""
    if transcribe is not None:
        TRANSCRIBE[0] = transcribe
    if _started:
        return
    _started.append(True)
    threading.Thread(target=_reminders, name="harry-calendar", daemon=True).start()
    try:
        jobview.start()
    except Exception as exc:
        print(f"  job view didn't start: {exc!r}")
