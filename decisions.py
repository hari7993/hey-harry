"""Was that for her? asked of Google's Gemini Decision 1 (the owner's ask, 18 November 2026), for what's said without
her name that her own decider (decider.py) wasn't sure of.

Till then such words went to the answer model with her whole prompt, about 3,200 tokens, to find out: in the log of
the days before, 213 of its 227 shortest answers were "not for me", each about 1.2 s and paid. Her decider gives less
than LEAN to most of them: of 2,217 such turns in its records, 88% were room talk. For those, and only once her
instant commands (quick) have passed them by, Gemini Decision is asked a yes or no, about 1 s. At NO or below she stays
quiet with no model asked; anything else, or no answer, goes to the model as before, so a request is never dropped on
its word alone. Tried that day: "Hey, turn on night light in settings" 0.94, "Let's play cricket tomorrow after
college" 0.02, "Open it." 0.49.

What's sent: those words, her last line if she spoke in the last WITHIN seconds, and the question. Nothing when the
key isn't saved (GEMINI_API_KEY, Settings > Keys) or it's turned off (gemini_decides). Its API is a decision, not
text: POST /v1beta/decisions with a "noul" (yes or no) question, the answer the chance of yes (ai.google.dev).
"""
import time

import requests

import settings
from secrets_store import get_secret

URL = "https://generativelanguage.googleapis.com/v1beta/decisions"
MODEL = "gemini-decision-1"
KEY = "GEMINI_API_KEY"
LEAN = 0.2  # her decider's chance below which Gemini is asked
NO = 0.15  # Gemini's chance of yes at or below which she stays quiet
WITHIN = 30.0  # seconds her last line counts as what they may be answering
TIMEOUT = (2.0, 2.5)  # connect, read: past it, the model decides as before
HTTP = requests.Session()  # kept open between turns, a new HTTPS connection costs a few hundred ms

QUESTION = "Is this said to the assistant, asking it to do something or asking it something?"
TRUE = "said to the assistant: a request or a question for it, like open, play, close, search, set, turn on, tell me"
FALSE = "talk with other people in the room, a phone call, a video or the TV, thinking aloud, or half-heard words"


def available():
    """True if she may ask: it's on, and a Gemini key is saved."""
    return bool(settings.get("gemini_decides")) and bool(get_secret(KEY))


def chance_for_her(words, her_line=None, now=None):
    """The chance, 0 to 1, that words said without her name were for her, as Gemini Decision sees it; None if it
    wasn't asked or didn't answer in time. her_line: (when, what) she said last, given only if it's recent."""
    key = get_secret(KEY)
    if not key or not str(words or "").strip():
        return None
    now = time.time() if now is None else now
    text = f'Heard by the microphone of a voice assistant on a Windows laptop, said without its name: "{words}"'
    if her_line and now - her_line[0] <= WITHIN:
        text += f'\nThe assistant had just said: "{her_line[1]}"'
    body = {"model": MODEL, "input": text,
            "questions": {"for_her": {"type": "noul", "instructions": QUESTION,
                                      "criteria": {"true_description": TRUE, "false_description": FALSE}}}}
    began = time.time()
    try:  # the key in a header, never the address
        r = HTTP.post(URL, json=body, headers={"x-goog-api-key": key}, timeout=TIMEOUT)
        r.raise_for_status()
        p = float(r.json()["answers"]["for_her"]["noul"])
    except Exception as exc:
        print(f"  Gemini Decision didn't answer: {type(exc).__name__}")
        return None
    print(f"  (Gemini Decision: for her {p:.2f}, {int((time.time() - began) * 1000)}ms)")
    return max(0.0, min(1.0, p))
