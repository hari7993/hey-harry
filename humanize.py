"""Her lines without the tells of machine writing (7 November 2026, the owner's ask: "speak like humanizer", after
blader's humanizer, github.com/blader/humanizer, MIT, which rewrites prose by Wikipedia's "Signs of AI writing").
The model is told too (siri.DEFAULT_SOUL), and this catches what slips through, in code, on every line she says
(siri.tidy): the chatbot's leftovers ("Certainly!", "I hope this helps"), the run-up before the point ("Here's the
thing"), the sayings that sound deep ("at the end of the day"), the words nobody says out loud ("utilize", "delve"),
the weighing of "not just X but Y", the qualifiers stacked for safety ("could potentially"), the dash as the only
joint, and the model's disclaimers ("as of my last update"). Only what a rule can do without changing what she
means: a list of three, a repeated opening or the passive are left alone, as humanizer's own "when not to act" has
it. A question of hers is never cut, and a line that would be left empty is left as it was. A few microseconds a
line: it's on the voice path."""
import re

START = r"(?:^|(?<=[.!?] ))"
# the run-up before the point, the staged candour and the chatbot's hello: dropped at the start of a sentence, with
# the mark after it. "Look" and "Honestly" only with their comma: "Look at the screen" is an order
LEADS = re.compile(START + r"(?:Of course|Certainly|Absolutely|Great question|Good question|Excellent question|"
                   r"I'd be happy to help|Real talk|Let's be honest|Let's dive in|"
                   r"Let's break (?:this|it) down|Let's explore|Here's the thing|The thing is|"
                   r"Here's what you need to know|To be clear|Don't get me wrong|Without further ado|Quick note|"
                   r"It's worth noting that|It's important to note that|It is important to note that|Note that|"
                   r"Interestingly|Importantly|Needless to say|As you (?:may |might |probably )?know)[,!:.]?\s+"
                   r"|" + START + r"(?:Look|Honestly|Well|Basically|Essentially),\s+", re.I)
# a whole sentence that's the chatbot talking, not her: gone. Never her own offer ("Want me to open it?")
CLOSERS = re.compile(r"(?:^|\s)(?:I hope (?:this|that|it) helps|Hope (?:this|that) helps|Let me know if [^.?!]*|"
                     r"(?:Is there )?[Aa]nything else (?:I can|you need|you'd like|you want)[^.?!]*|"
                     r"Feel free to [^.?!]*|Don't hesitate to [^.?!]*|(?:Would you like|Do you want) me to continue|"
                     r"Should I continue|I'm here (?:to help|if you need)[^.?!]*|"
                     r"If you (?:have|need) any (?:other|more|further) (?:questions|help)[^.?!]*)[.!?]+", re.I)
# sayings that sound deep, and the qualifiers stacked for safety: the words go, the sentence stays
PADDING = re.compile(r"\b(?:at the end of the day|at its core|in reality|fundamentally|the real question is|"
                     r"what really matters is|the heart of the matter is|to be fair|in essence|"
                     r"as of my (?:last|latest|most recent) (?:update|training)(?: in \w+ \d{4})?|"
                     r"based on (?:the )?available information|from what I can tell|it goes without saying that)"
                     r",?\s*", re.I)
QUALIFIERS = ((re.compile(r"\bcould potentially\b", re.I), "could"), (re.compile(r"\bmight arguably\b", re.I), "might"),
              (re.compile(r"\bmay potentially\b", re.I), "may"), (re.compile(r"\bit's also possible that\b ", re.I), ""))
# the words nobody says out loud, swapped for the ones they do, the first letter kept as it was
WORDS = {"utilize": "use", "utilizes": "uses", "utilized": "used", "utilizing": "using", "leverage": "use",
         "leverages": "uses", "leveraged": "used", "leveraging": "using", "crucial": "important",
         "pivotal": "important", "additionally": "also", "furthermore": "also", "meticulously": "carefully",
         "meticulous": "careful", "showcase": "show", "showcases": "shows", "showcased": "showed",
         "garner": "get", "garnered": "got", "enhance": "improve", "enhances": "improves", "enhanced": "improved",
         "commence": "start", "commenced": "started", "endeavor": "try", "endeavour": "try", "facilitate": "help",
         "facilitates": "helps", "subsequently": "then", "numerous": "many", "optimal": "best",
         "underscores": "shows", "underscore": "show"}
WORD = re.compile(r"\b(" + "|".join(sorted(WORDS, key=len, reverse=True)) + r")\b", re.I)
PHRASES = ((re.compile(r"\bdelve into\b", re.I), "look into"), (re.compile(r"\bdelves into\b", re.I), "looks into"),
           (re.compile(r"\ba deep dive into\b", re.I), "a close look at"),
           (re.compile(r"\b(?:a|is a|stands as a) testament to\b", re.I), "is a sign of"),
           (re.compile(r"\bplays? a (?:key|crucial|pivotal|vital|critical) role in\b", re.I), "matters for"),
           (re.compile(r"\bin the realm of\b", re.I), "in"), (re.compile(r"\bin order to\b", re.I), "to"))
# the chatbot's way of saying it can't: "I'm unable to", "I don't have the ability to", "with the tools I have here",
# "as an AI". A person says "I can't"
REFUSALS = ((re.compile(r"\b(?:I am|I'm) (?:unable|not able) to\b", re.I), "I can't"),
            (re.compile(r"\bI (?:do not|don't) have the (?:ability|capability) to\b", re.I), "I can't"),
            (re.compile(r"\bI lack the ability to\b", re.I), "I can't"),
            (re.compile(r",? ?\bwith the tools (?:I have|available to me)(?: here)?\b", re.I), ""),
            (re.compile(r"\b(?:as|being) (?:an|just an) AI(?: assistant| model)?,?\s*", re.I), ""),
            (re.compile(r"\bI'm just an AI(?: assistant)?,?\s*", re.I), ""))
# a sign-off that offers nothing in particular, a sentence of its own after what she's said: "Want me to do anything
# here?", "What are you trying to get done?". Gone only then: an offer that names a thing ("Want me to set a timer?")
# stays, so does a hello's "what can I do for you?", and so does a welcome's question, which lets you answer her
# without her name (siri.welcome)
SIGN_OFFS = re.compile(r"(?<=[.!?]) (?:Want me to (?:do|help with) anything(?: else| here| with (?:that|this|it))?|"
                       r"Want me to pull up any of (?:those|them)|Want me to do anything (?:else )?(?:here|with it)|"
                       r"What are you trying to (?:get done|do)|Is there anything (?:else )?(?:I can|you'd like|"
                       r"you need|you want)[^?]*)\?$", re.I)
# "not just fast, but accurate" weighs the second half against a first nobody claimed: both, plainly. Never when
# the first half starts with a verb turned round ("not only did it rain"), which "and" would garble
AUX = r"(?!(?:did|does|do|is|was|were|are|has|have|had|can|could|will|would|should)\b)"
NOT_JUST = re.compile(r"\bnot (?:just|only|merely|simply) " + AUX + r"([^,.;:!?]{1,60}?),? but (?:also )?"
                      r"([^,.;:!?]{1,80})", re.I)
# "It's not a phone, it's a camera": the second half is the claim
ITS_NOT = re.compile(r"\b(it'?s|that'?s|this is) not ([^,.;:!?]{1,50}), (?:it'?s|that'?s|this is) ", re.I)
DASHES = re.compile(r"\s*(?:—|–|--)\s*")


def _case(old, new):
    """new with old's first letter's case."""
    return new[:1].upper() + new[1:] if old[:1].isupper() else new


def plain(text):
    """text, said the way a person says it (see the top): the same words where no rule applies."""
    text = str(text or "")
    if not text.strip():
        return text
    out = DASHES.sub(", ", text)
    out = CLOSERS.sub("", out)
    for _ in range(3):  # "Of course, I'd be happy to help." is two of them, one behind the other
        out, n = LEADS.subn("", out)
        if not n:
            break
    out = PADDING.sub("", out)
    for pattern, swap in QUALIFIERS:
        out = pattern.sub(swap, out)
    for pattern, swap in PHRASES + REFUSALS:
        out = pattern.sub(lambda m, s=swap: _case(m.group(0), s), out)
    out = SIGN_OFFS.sub("", out)
    out = WORD.sub(lambda m: _case(m.group(1), WORDS[m.group(1).lower()]), out)
    out = NOT_JUST.sub(lambda m: f"{m.group(1)} and {m.group(2)}", out)
    out = ITS_NOT.sub(lambda m: _case(m.group(1), m.group(1).lower() + " "), out)
    out = re.sub(r"\s+([,.;:!?])", r"\1", re.sub(r"[ \t]{2,}", " ", out)).strip()
    out = re.sub(r"^[,;:\s]+|(?<=[.!?] )[,;:\s]+", "", out)  # a comma left at a start
    out = re.sub(START + r"([a-z])", lambda m: m.group(1).upper(), out)  # each sentence starts with a capital
    if not re.search(r"\w", out):
        return text
    return out
