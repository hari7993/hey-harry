"""Her name: Harry, unless you give her one of your own (28 October 2026, the owner's ask, the way OpenClaw's agent
keeps the name you give it). Say "call yourself Friday" or type one in Settings > Her name, and she sticks to it:
it's the name she answers to (siri builds its wake words from wake_words), the one she calls herself (her
personality, SOUL.md, says it from then on, see rename), and the one the window, the walkthrough and your phone show
(named). Jarvis works too, whatever her name.

She was Jev till 28 October 2026, in a program called Hey Jev. Her folders, keys and start-up entry move over by
themselves (winplatform.move_home), and what she wrote about herself and you is told her new name once (moved_on).
"""
import os
import re
import shutil
import threading

import settings
import winplatform as win

DEFAULT = "Harry"
OLD = "Jev"  # her name till 28 October 2026
# How speech-to-text writes "Harry": a first list, 28 October 2026. siri's log keeps the "hey ..." phrases that didn't
# count (MAYBE_WAKE), to add the rest from. Spellings that are no word count anywhere in a phrase; real words and names
# only when she's called the way you'd call someone: "Hey Hurry", "Hairy, open Chrome", never "I'm in a hurry" or
# "play Harry Styles"
HARRY_STRONG = ("harri", "harrie", "harree", "haree", "hary", "haary")
HARRY_WEAK = ("harry", "hari", "hurry", "hairy", "harley", "harvey", "henry", "barry", "larry", "perry")
HARRY_HEARD = "Hari, Hairy or Hurry"  # what the model's told her name may come out as (siri.PROMPT)
SECOND = ("jarvis", "jervis")  # Jarvis, her second name whatever her first (picked from Alfred), and how it comes out
# Never a name of hers: how a request or a greeting starts, and what's said to her all day. Called "Open", every
# "open Notepad" would be her name and nothing more
TAKEN = {"hey", "hi", "hello", "hallo", "hullo", "hiya", "heya", "ok", "okay", "yo", "yes", "yeah", "no", "not", "stop",
         "wait", "cancel", "open", "close", "play", "pause", "search", "type", "please", "thanks", "thank", "you", "me",
         "my", "i", "a", "an", "the", "and", "or", "it", "this", "that", "what", "who", "how", "is", "are", "can"}
LETTERS = r"[A-Za-zÀ-ɏ]+(?:['’-][A-Za-zÀ-ɏ]+)*"  # a word: Zoë, O'Neil and Jean-Luc too
MOST = 24  # letters at most in all
_hooks = []
_lock = threading.Lock()
_moved = []


def name():
    """What she's called: the name you gave her, else Harry."""
    return clean(settings.get("nickname")) or DEFAULT


def clean(text):
    """A name as she'll keep it ("Friday" for " friday. "), or None if it can't be one: up to three words of letters
    and MOST letters in all, none of them TAKEN."""
    words = re.sub(r"[.,!?;:\"“”]+", " ", str(text or "")).split()
    if not 1 <= len(words) <= 3 or any(not re.fullmatch(LETTERS, w) or w.lower() in TAKEN for w in words):
        return None
    out = " ".join(w[:1].upper() + w[1:] for w in words)
    return out if 2 <= len(out) <= MOST else None


def hey():
    """How you call her: "Hey Harry"."""
    return f"Hey {name()}"


def named(text):
    """Her own words with Harry in them, the window's, her lines and her prompts, with the name she has now. Only
    hers: in anything else, Harry may be somebody else."""
    now = name()
    return text if now == DEFAULT or not text else re.sub(r"\bHarry\b", lambda m: now, str(text))


def _pattern(words):
    """A name as a regex alternative, its words however speech-to-text spaced or hyphenated them."""
    return r"\W*".join(re.escape(w.lower()) for w in re.split(r"[\s-]+", words))


def wake_words():
    """(strong, weak): her names as speech-to-text writes them, as regex alternatives (siri.find_name). Strong ones
    count anywhere in a phrase, weak ones only when she's called. A name you give her is a weak one, like Harry,
    since it may well be a word ("Max", "Friday")."""
    now = name()
    strong, weak = (HARRY_STRONG, HARRY_WEAK) if now == DEFAULT else ((), (_pattern(now),))
    return "|".join((*strong, *SECOND)), "|".join(weak)


def own():
    """Her names as she's called by them, as regex alternatives: her name and Jarvis, without the misheard ones (a
    welcome line the model wrote, her own name at the end of what she says, a message read out)."""
    return "|".join((_pattern(name()), *SECOND))


def heard():
    """What her name may come out as in speech-to-text, for the model: Harry's known ones, or a name's sound."""
    return HARRY_HEARD if name() == DEFAULT else "words that sound like it"


def on_rename(hook):
    """hook(old, new) runs after each new name, in the thread that gave it: her wake words, the window's words."""
    _hooks.append(hook)


def _swap(path, old, new):
    """The file at path with the name old, as a whole word, as new; False if it couldn't be written."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    swapped = re.sub(rf"\b{re.escape(old)}\b", lambda m: new, text)
    if swapped == text:
        return True
    try:
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            f.write(swapped)
        os.replace(path + ".tmp", path)
        return True
    except OSError:
        return False


def soul_path():
    return os.path.join(win.APPDATA_DIR, "SOUL.md")


def rename(text):
    """Gives her a new name, said or typed, and returns it. Her personality (SOUL.md) has it in place of the old one
    first, so she never answers to one name and calls herself another; then Settings keeps it and each hook runs.
    Nothing changes on ValueError, it can't be a name of hers (clean), or OSError, SOUL.md couldn't be written."""
    new = clean(text)
    if not new:
        raise ValueError(f"not a name: {text!r}")
    with _lock:
        old = name()
        if new == old:
            return new
        if not _swap(soul_path(), old, new):
            raise OSError(f"couldn't write {soul_path()}")
        settings.put("nickname", "" if new == DEFAULT else new)
    print(f"  her name: {old} -> {new}")
    for hook in list(_hooks):
        try:
            hook(old, new)
        except Exception as exc:  # one that fails never keeps the name from the rest
            print(f"  after her new name: {exc!r}")
    return new


def moved_on():
    """Once, the first time she starts as Harry (winplatform.move_home moved her folder from Hey Jev's): her
    personality and her notes about herself and you (MEMORY.md, USER.md) say her name where they said Jev. Each file
    as it was is kept beside it, with .before-harry on its name."""
    with _lock:
        if _moved or win.APPDATA_DIR not in win.MOVED:
            return
        _moved.append(True)
        memories = os.path.join(win.APPDATA_DIR, "memories")
        for path in (soul_path(), os.path.join(memories, "MEMORY.md"), os.path.join(memories, "USER.md")):
            try:
                with open(path, encoding="utf-8-sig") as f:
                    if not re.search(rf"\b{OLD}\b", f.read()):
                        continue
                shutil.copy2(path, path + ".before-harry")
            except OSError:
                continue
            if _swap(path, OLD, name()):
                print(f"  {os.path.basename(path)}: {OLD} is {name()} now")
