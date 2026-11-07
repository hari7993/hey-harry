"""Hey Harry's messaging: open the chat with the text typed in, read it back, and send only after a yes.

Two deliberate choices, both for safety:

- The recipient comes from your own contacts book (%APPDATA%\\Hey Harry\\contacts.json), as a phone number or
  username, and the chat is opened with the app's own link (whatsapp://send, tg://resolve). Searching a chat list
  by a name she heard could land on the wrong person; a number cannot.
- Nothing is ever sent until you say yes. The link only types the text into the compose box.

She learns as she goes: the first time you name someone she asks once, saves the alias, and from then on
"message Mum on WhatsApp: hi" is one step.

Apps with no link of their own (Signal, Slack, Discord and the rest) take the long way round, the way you would:
bring the app up, press its search shortcut, type the name, open the chat, type the message, stop. She can't read
any of that back, so your yes is confirming the chat as well as the words. That yes is also what teaches her: the
shortcut that worked and the name that found the person are saved, so the next one is a single sentence.
"""
from __future__ import annotations

import contextlib
import ctypes
import json
import os
import re
import subprocess
import tempfile
import time
from ctypes import wintypes as w
from urllib.parse import quote

import winplatform as win

CONTACTS_PATH = os.path.join(win.APPDATA_DIR, "contacts.json")
MAX_TEXT = 1000
user32 = ctypes.WinDLL("user32", use_last_error=True)

# Each app: how to say it, the program its window runs as, the link that opens a chat with the text typed in, what
# the link needs, and what agent-desktop can read in it (None: nothing readable, see verify)
APPS = {
    "whatsapp": {
        "say": "WhatsApp",
        "exes": ("WhatsApp.exe", "WhatsApp.Root.exe"),
        "classes": ("WinUIDesktopWin32WindowClass",),
        "link": "whatsapp://send?phone={id}&text={text}",
        "needs": "number",
        # its message box is a real element, named "Type a message to Amma" in the 2025 app ("Type a message"
        # before), and a Reconnect button means the desktop app has no link to the phone
        "compose": "Type a message",
        "offline_button": "Reconnect",
    },
    "telegram": {
        "say": "Telegram",
        "exes": ("Telegram.exe",),
        "classes": ("Qt51519QWindowIcon", "Qt5QWindowIcon", "Qt6QWindowIcon"),
        "link": "tg://resolve?domain={id}&text={text}",
        "needs": "username",
        "compose": None,  # Telegram draws its own interface, so Windows exposes nothing inside it
        "offline_button": None,
    },
}
ALIASES = {"whats app": "whatsapp", "whatsup": "whatsapp", "whats up": "whatsapp", "watsapp": "whatsapp",
           "telegramme": "telegram", "telegraph": "telegram"}

# --------------------------------------------------------------------------- apps with no link of their own
RECIPES_PATH = os.path.join(win.APPDATA_DIR, "recipes.json")
OTHER_MAX_TEXT = 300  # typed on the keyboard rather than handed over in a link, so keep it to a message
# Nearly every chat app works the same way: a shortcut puts the cursor in search, the name finds the person,
# Enter opens their chat, Enter sends. She tries this, you look at the screen, and your yes is what saves it.
DEFAULT_RECIPE = {"search": ["ctrl", "f"], "pick": ["enter"], "settle": 1.2}  # long enough for results to appear
FIRST_TRY = {"slack": ["ctrl", "k"], "discord": ["ctrl", "k"], "element": ["ctrl", "k"],
             "signal": ["ctrl", "f"], "teams": ["ctrl", "e"]}  # what each one actually uses, where it's known
MODS = {"ctrl", "alt", "shift", "cmd"}
SPECIAL = {"enter", "tab", "esc", "space", "backspace", "delete", "up", "down", "left", "right", "home", "end"}


class NeedContact(RuntimeError):
    """She doesn't know who that is yet. The message says what to ask for."""


def app_key(name):
    key = re.sub(r"[^a-z]+", "", str(name or "").lower())
    if key in APPS:
        return key
    spoken = " ".join(str(name or "").lower().split())
    return ALIASES.get(spoken) or ALIASES.get(key)


def other_key(name):
    """The name of an app with no link, flattened so "VS Code" and "vscode" are the same app."""
    return re.sub(r"[^a-z0-9]+", "", str(name or "").lower())


def needs_of(app):
    """What she needs to reach someone there: a phone number, a username, or a name to type into search."""
    spec = APPS.get(app)
    return spec["needs"] if spec else "search"


def say_of(app):
    spec = APPS.get(app)
    if spec:
        return spec["say"]
    return (read_recipes().get(app) or {}).get("say") or str(app or "that app").title()


def clean_number(value):
    """A phone number as WhatsApp's link wants it: digits only, with the country code."""
    digits = re.sub(r"\D", "", str(value or ""))
    if not 7 <= len(digits) <= 15:
        raise ValueError("that doesn't look like a phone number with its country code")
    return digits


def clean_username(value):
    name = str(value or "").strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{4,32}", name):
        raise ValueError("a Telegram username is 4 to 32 letters, numbers or underscores")
    return name


def clean_search(value):
    """A name to type into an app's search box: just the name, on one line."""
    name = " ".join(str(value or "").split())
    name = "".join(c for c in name if c.isprintable())
    if not name or not re.search(r"\w", name):
        raise ValueError("I need a name to look for")
    return name[:60]


def clean_handle(app, value):
    want = needs_of(app)
    return clean_number(value) if want == "number" else clean_username(value) if want == "username" \
        else clean_search(value)


def clean_text(value):
    text = " ".join(str(value or "").split())
    text = "".join(c for c in text if c.isprintable())
    if not text:
        raise ValueError("there's nothing to send")
    return text[:MAX_TEXT]


# Speech-to-text writes the same person more than one way: Nemotron heard "Message Mum" as "Message Mom"
# not "mama": in Telugu, Tamil and Hindi that's an uncle, and his number would have gone in as Mum's
SAME_PERSON = {"mom": "mum", "mommy": "mum", "mummy": "mum", "mumma": "mum",
               "amma": "mum", "ammi": "mum", "dad": "dad", "daddy": "dad", "papa": "dad", "pappa": "dad",
               "appa": "dad", "abbu": "dad"}


def alias_key(name):
    words = re.sub(r"[^\w\s']+", " ", str(name or "").lower()).split()
    words = [w for w in words if w not in ("my", "the")] or words  # "my mum" is mum
    return " ".join(SAME_PERSON.get(w, w) for w in words)


# --------------------------------------------------------------------------- the contacts book
def read_contacts():
    try:
        with open(CONTACTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_contact(alias, app, handle):
    """Remember who someone is, so the next message to them is one step. Returns how she'd say it."""
    key = alias_key(alias)
    app = app_key(app) or next((k for k in (other_key(app),) if k in read_recipes()), None)
    if not key or app is None:
        raise ValueError("I need a name and an app I know")
    handle = clean_handle(app, handle)
    book = read_contacts()
    entry = book.setdefault(key, {"name": " ".join(str(alias).split())[:60]})
    entry[app] = handle
    _write_json(CONTACTS_PATH, book)
    return f"{entry['name']} on {say_of(app)}"


def _write_json(path, data, emptying=False):
    """Write data whole or not at all. An empty book never replaces a contacts book with people in it unless that's
    what was asked (emptying): on 8 Oct a test run's clean-up wrote {} over the real contacts.json at 19:03, and the
    three people she'd learned that day were lost for good, the backup was from the night before."""
    if path == CONTACTS_PATH and not data and not emptying and read_contacts():
        raise ValueError("refusing to empty the contacts book without being asked to forget everyone")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=os.path.basename(path) + ".", suffix=".tmp")
    try:  # a temp file of its own, so two saves at once (the phone and the PC) can't write into each other's
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())  # on disk before it replaces the old one, so a power cut leaves one or the other
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def forget_contact(alias):
    book = read_contacts()
    if book.pop(alias_key(alias), None) is None:
        return False
    _write_json(CONTACTS_PATH, book, emptying=True)  # forgetting the last one you named leaves the book empty
    return True


def find_contact(alias, app):
    """(display name, handle) for someone in the book, or NeedContact with what to ask for."""
    key, book = alias_key(alias), read_contacts()
    entry = book.get(key)
    if entry is None:  # "mum" vs "my mum", and nicknames inside a longer name, by whole words only: "ravi" inside
        # "ravindra" would send Ravindra's message to Ravi, and Supriya's to Priya
        hits = [v for k, v in book.items() if k and (f" {k} " in f" {key} " or f" {key} " in f" {k} ")]
        entry = hits[0] if len(hits) == 1 else None
    want = needs_of(app)
    if entry is None or not entry.get(app):
        said = " ".join(str(alias).split())[:40] or "them"
        if want == "search":  # nothing to ask for: she types the name you said and you check the chat she lands on
            return said, clean_search(alias)
        asked = "phone number, with the country code" if want == "number" else f"{say_of(app)} username"
        raise NeedContact(f"I don't know {said} on {say_of(app)} yet. What's their {asked}?")
    return entry.get("name") or said_name(key), entry[app]


def said_name(key):
    return key.title() if key else "them"


def known_for(app):
    """The names she can message on an app, for the model and the window."""
    return sorted((v.get("name") or k).strip() for k, v in read_contacts().items() if v.get(app))


# --------------------------------------------------------------------------- the people she's messaging for you
# Everyone she sends a message or a file to for you, so a reply from them is told to you as theirs, on the PC and on
# your phone, whenever it comes (asked for on 8 October: "all days, 24/7"; see watch.Watcher and siri.replied). Kept
# in %APPDATA%\Hey Harry\follow_ups.json, on this PC only, until FOLLOW_MAX newer ones push it out.
FOLLOW_PATH = os.path.join(win.APPDATA_DIR, "follow_ups.json")
FOLLOW_MAX = 200


def read_follows():
    try:
        with open(FOLLOW_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def follow(app, contact, to="", handle=""):
    """Note that she messaged contact (what you call them) on app (as Windows' notifications name it: "WhatsApp"), by
    the name a notification of theirs carries: the chat's own name in the app (to), and their number. Only where the
    app can't show the chat's name (Telegram, the apps she types her way into) by what you call them."""
    chat = " ".join(str(to or "").split())
    names = [n for n in dict.fromkeys((chat or " ".join(str(contact or "").split()), str(handle or ""))) if _letters(n)]
    if not names:
        return
    book = read_follows()
    book[f"{other_key(app)}:{alias_key(contact) or _letters(names[0])}"] = {
        "app": str(app), "contact": " ".join(str(contact or names[0]).split())[:60], "names": names[:2],
        "by_alias": not chat, "when": time.time()}
    if len(book) > FOLLOW_MAX:  # the ones messaged longest ago go first
        book = dict(sorted(book.items(), key=lambda kv: kv[1].get("when", 0))[-FOLLOW_MAX:])
    _write_json(FOLLOW_PATH, book)


def followed(app, sender):
    """The person she's been messaging for you that a notification on app from sender is, or None. By the chat's own
    name, spaces and case aside but emoji kept ("Buntyyy🐼" is "Buntyyy 🐼", not "Buntyyy 🎂"), or by their number:
    never by a shorter name, as your "Ravi" is Ravi Kumar, and another Ravi isn't."""
    got, digits = _chat_key(sender), re.sub(r"\D", "", str(sender or ""))
    number = len(digits) >= 7 and re.fullmatch(r"[\d\s()+.-]+", str(sender or "").strip())
    if not _letters(sender):
        return None

    def same(entry, name):
        if number:
            return re.sub(r"\D", "", name) == digits
        return (_letters(name) == _letters(sender)) if entry.get("by_alias") else _chat_key(name) == got
    hits = [entry for entry in read_follows().values() if str(entry.get("app", "")).casefold() == str(app).casefold()
            and any(same(entry, n) for n in entry.get("names") or [])]
    # one chat you've called two things ("buntyy", then "buntyyy"): who you messaged last
    return max(hits, key=lambda e: e.get("when", 0)) if hits else None


# --------------------------------------------------------------------------- the recipes she's been taught
def read_recipes():
    try:
        with open(RECIPES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def clean_keys(keys, fallback):
    """A shortcut she may press: up to three modifiers and one ordinary key. Anything else falls back."""
    names = [str(k).strip().lower() for k in (keys or []) if str(k).strip()]
    if not names or len(names) > 4:
        return list(fallback)
    *mods, last = names
    if any(m not in MODS for m in mods):
        return list(fallback)
    if not ((len(last) == 1 and last.isalnum()) or last in SPECIAL):
        return list(fallback)
    return names


def recipe_for(app):
    """How to reach a chat in that app: what she was taught, else what it's known to use, else the usual way."""
    saved = read_recipes().get(app) or {}
    first = FIRST_TRY.get(app, DEFAULT_RECIPE["search"])
    settle = saved.get("settle", DEFAULT_RECIPE["settle"])
    try:
        settle = min(3.0, max(0.3, float(settle)))
    except (TypeError, ValueError):
        settle = DEFAULT_RECIPE["settle"]
    return {"search": clean_keys(saved.get("search"), first),
            "pick": clean_keys(saved.get("pick"), DEFAULT_RECIPE["pick"]),
            "settle": settle, "taught": bool(saved.get("uses"))}


def save_recipe(app, say, recipe):
    """Keep what just worked, so the next message in that app is one sentence."""
    book = read_recipes()
    entry = book.setdefault(app, {})
    entry.update(say=str(say or "").strip()[:40] or app.title(), search=list(recipe["search"]),
                 pick=list(recipe["pick"]), settle=recipe["settle"], uses=int(entry.get("uses") or 0) + 1,
                 learned=time.strftime("%Y-%m-%d"))
    _write_json(RECIPES_PATH, book)
    return entry


def forget_recipe(app):
    book = read_recipes()
    if book.pop(other_key(app), None) is None:
        return False
    _write_json(RECIPES_PATH, book)
    return True


def learned_apps():
    """The apps she's worked out how to message in, for the model and the window."""
    return sorted((v.get("say") or k) for k, v in read_recipes().items() if v.get("uses"))


# --------------------------------------------------------------------------- the app's window
def window_of(app):
    """The messaging app's main window, or None. Its own tray window and helpers are skipped by class."""
    spec = APPS[app]
    wanted = {e.lower() for e in spec["exes"]}
    found = []

    def visit(hwnd, _):
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value in spec["classes"] and os.path.basename(win.window_exe(hwnd)).lower() in wanted:
            found.append(hwnd)
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)(visit), 0)
    return found[0] if found else None


def again(fn, tries=3, pause=0.4):
    """fn(), tried again after a safe, transient accessibility read failure; the last error otherwise."""
    for i in range(tries):
        try:
            return fn()
        except Exception as exc:
            code = getattr(exc, "code", "")
            retry = getattr(exc, "safe", False) or code in ("TIMEOUT", "WINDOW_NOT_FOUND")
            if not retry or i == tries - 1:
                raise
            time.sleep(pause)


READ_MS = 8000  # WhatsApp's page is a big one (13,000 elements when UI Automation counted them), and a read cut
# short can miss its message box


def _snapshot(hwnd):
    """One full agent-desktop read of a messaging window."""
    if hwnd is None:
        raise LookupError("the messaging window isn't open")
    return win._desktop_snapshot(hwnd, timeout_ms=READ_MS)


def _named(snap, roles, name, part=False):
    """Shown raw elements of one of roles whose clean name is exact, or contains name with part."""
    roles = {roles} if isinstance(roles, str) else set(roles)
    want = win.clean_name(name).casefold()
    out = []
    for el in snap.elements:
        label = win.clean_name(el.name).casefold()
        if el.raw_role in roles and win._shown(el) and (want in label if part else label == want):
            out.append(el)
    return out


def offline_reason(app, hwnd):
    """Why the app can't send right now, or None. WhatsApp shows Reconnect when the phone isn't linked."""
    spec = APPS[app]
    if not spec["offline_button"] or hwnd is None:
        return None
    try:
        if _find_button(hwnd, spec["offline_button"]):
            return f"{spec['say']} on this PC isn't connected to your phone"
    except Exception as exc:
        print(f"  couldn't check {app}: {exc!r}")
    return None


def compose_box(app, hwnd):
    """The app's message box and who its accessible name says the chat is to."""
    return again(lambda: _compose_box(app, hwnd))


def _compose_box(app, hwnd):
    """WhatsApp's text field named 'Type a message to Amma', or its older 'Type a message' field."""
    prefix = APPS[app]["compose"]
    if not prefix or hwnd is None:
        return None, ""
    fields = [el for el in _snapshot(hwnd).elements if el.raw_role == "textfield" and win._shown(el)]
    wanted = prefix.casefold()
    box = next((el for el in fields if win.clean_name(el.name).casefold().startswith(wanted + " to ")), None)
    box = box or next((el for el in fields if win.clean_name(el.name).casefold().startswith(wanted)), None)
    if box is None:
        return None, ""
    name = win.clean_name(box.name)
    to = name[len(prefix):].strip() if name.casefold().startswith(wanted) else ""
    return box, re.sub(r"^to\s+", "", to, flags=re.I).strip()


def box_value(box):
    """What a message box holds: "" when it's empty (WhatsApp's holds a line break then). As the read that found it
    saw it a moment ago: each box here comes from a read just made, and reading it again reads the whole window."""
    if box is None or getattr(box, "password", False):
        return ""
    return " ".join(win._text(getattr(box, "value", None) or "").split())


def typed_text(app, hwnd):
    """What the app's message box holds, where it exposes one, else None."""
    def read():
        box, _ = _compose_box(app, hwnd)
        return box_value(box) if box else None
    try:
        return again(read)
    except Exception as exc:
        print(f"  couldn't read the message box: {exc!r}")
        return None


def box_shown(app, hwnd, wait=4.0):
    """What the chat's message box holds once it appears, or None if it never does."""
    end = time.time() + wait
    while True:
        shown = typed_text(app, hwnd)
        if shown is not None or time.time() > end:
            return shown
        time.sleep(0.5)


def _wipe(app, hwnd):
    """Ctrl+A and Backspace, only while the app is still the one in front: never into another app's box."""
    if in_front(app, hwnd):
        win.press("ctrl", "a")
        win.press("backspace")


def type_into(app, hwnd, text):
    """Type text into the chat's message box, as WhatsApp's 2025 app leaves its link's text out: the box is put in
    focus first, with the app in front, and whatever was in it cleared. Then read back. Raises if it isn't there, so
    nothing half typed is ever asked about. Typed on the keyboard, as it always was: a value set from outside can
    show in WhatsApp's box without its editor knowing, and what's sent is what the editor holds."""
    box = _focus_box(app, hwnd)
    if box_value(box):  # a draft from before: it would be sent along with this
        _wipe(app, hwnd)
    win.type_text(text)
    time.sleep(0.4)
    check, _ = compose_box(app, hwnd)
    if check is None or box_value(check) != text:
        _wipe(app, hwnd)
        raise RuntimeError(f"{APPS[app]['say']} didn't take the message, so I've not sent anything")


def drawn(hwnd):
    """True once WhatsApp has either its search field or a chat's message field."""
    end, why = time.time() + LOADING, None
    while True:
        try:
            snap = _snapshot(hwnd)
            if _search_box(snap) is not None or _compose_box("whatsapp", hwnd)[0] is not None:
                return True
        except Exception as exc:
            why = exc
        if time.time() > end:
            if why is not None:
                print(f"  couldn't look at WhatsApp's page: {why!r}")
            return False
        time.sleep(0.5)


def open_chat(app, handle, text):
    """Open that person's chat with the text typed in, through the app's own link. Nothing is sent."""
    link = APPS[app]["link"].format(id=quote(str(handle), safe=""), text=quote(text, safe=""))
    hwnd = bring_up(app, link)
    time.sleep(1.2)  # the chat and the typed text need a moment to appear
    return hwnd


def bring_up(app, link):
    """Start the app's link and wait for its window to show, then put it in front: shown from the tray too, where
    WhatsApp's window is hidden and has nothing in it to read. Its window, or raises."""
    before = window_of(app)
    subprocess.run(["cmd", "/c", "start", "", link], check=False, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=win.CREATE_NO_WINDOW,
                   timeout=20)
    hwnd, end = before, time.time() + 12
    while time.time() < end:
        time.sleep(0.4)
        hwnd = window_of(app) or hwnd
        if hwnd and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            break
    if hwnd is None:
        raise RuntimeError(f"I couldn't open {APPS[app]['say']}")
    try:
        win.bring_to_front(hwnd)
    except Exception:
        pass
    return hwnd


def in_front(app, hwnd):
    """True if that app's window is the one in front, so Enter goes to the chat and nowhere else: its own window, or
    the web view inside it, which WhatsApp's 2025 app puts in front once its message box has the keyboard."""
    front = user32.GetForegroundWindow()
    if not front or not hwnd:
        return False
    if front == hwnd:
        return os.path.basename(win.foreground_exe()).lower() in {e.lower() for e in APPS[app]["exes"]}
    return _hosted_by(front, hwnd)


def _hosted_by(front, hwnd):
    """True if window front is a web view (msedgewebview2.exe) that the program of window hwnd started: inside that
    app, not another one that happens to use a web view too."""
    if os.path.basename(win.window_exe(front)).lower() != "msedgewebview2.exe":
        return False
    import psutil
    try:
        owner, proc = win._pid(hwnd), psutil.Process(win._pid(front))
        for _ in range(4):  # the view's own process, the web view's main one, then the app
            proc = proc.parent()
            if proc is None:
                return False
            if proc.pid == owner:
                return True
    except (psutil.Error, OSError):
        return False
    return False


# --------------------------------------------------------------------------- finding someone in WhatsApp itself
# Someone she has not been told about may already be in WhatsApp. She searches its accessible controls, opens only
# a result whose ref or checked point still belongs to WhatsApp, reads its contact panel and then asks the owner.
LOOK_AT = 3
LOADING = 25.0
SHOWN_NUMBER = re.compile(r"\+\d[\d\s()-]{6,}\d")
MARKS = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
HEADINGS = ("Chats", "Contacts", "Groups in common", "Messages", "Other contacts")
PEOPLE = ("Chats", "Contacts", "Other contacts")
PANELS = ("Contact info", "Business info", "Group info")


def whatsapp_people(name, most=LOOK_AT, stop=None):
    """People WhatsApp itself finds for name, with the phone number each contact panel shows."""
    name = clean_search(" ".join([word for word in str(name or "").split() if word.lower() not in ("my", "the")])
                        or name)
    hwnd = bring_up("whatsapp", "whatsapp:")
    box, end = None, time.time() + LOADING
    while box is None:
        box = again(lambda: _search_box(_snapshot(hwnd)))
        if box is None:
            if time.time() > end:
                raise RuntimeError("I couldn't find WhatsApp's search box")
            time.sleep(0.5)
    try:
        found = _look_for(hwnd, box, name, most, stop)
        words = name.split()
        if not found and len(words) > 1 and len(words[0]) >= 3 and not (stop and stop()):
            box = _search_box(_snapshot(hwnd))
            found = _look_for(hwnd, box, words[0], most, stop) if box is not None else []
        print(f"  WhatsApp found {len(found)} for {name!r}")
        return found
    finally:
        try:
            live = _search_box(_snapshot(hwnd))
            if live is not None:
                _set_value(live, "")
        except Exception as exc:
            print(f"  couldn't empty WhatsApp's search: {exc!r}")


def _search_box(snap):
    """WhatsApp's first text field that is not a chat or preview message box."""
    prefix = APPS["whatsapp"]["compose"].casefold()
    fields = [el for el in snap.elements if el.raw_role == "textfield" and win._shown(el)]
    return next((el for el in fields if not win.clean_name(el.name).casefold().startswith(prefix)), None)


def _set_value(element, text):
    """Fill or empty a box by its value: no key is pressed, so nothing can land anywhere else. Keys typed into
    WhatsApp's search box just after it was given the keyboard were lost, every time."""
    if element is None or "SetValue" not in element.actions:
        raise RuntimeError("that box cannot be filled safely")
    win.ui_act(element, str(text))


def _look_for(hwnd, box, name, most, stop=None):
    try:  # the keyboard in WhatsApp's page: without it a click on a result didn't open its chat
        win.ui_focus(box)
    except Exception as exc:  # the name goes in by its value and each click checks where it lands, so only a try
        print(f"  focusing WhatsApp's search: {exc!r}")
    time.sleep(0.3)
    stale = again(lambda: _rows(hwnd)) if box_value(box) else None
    _set_value(box, name)
    labels = _results(hwnd, None if stale is None else [label for label, _ in stale])
    if labels is None:
        raise RuntimeError("WhatsApp didn't show its search results")
    found = []
    for tries, (i, label) in enumerate(_by_name(labels, name)):
        if tries >= most + 2 or len(found) >= most or (stop and stop()):
            break
        if _name_rank(_label_name(label), name) == 2 and any(_name_rank(person["name"], name) < 2
                                                              for person in found):
            break
        try:
            person = _read_person(hwnd, i, label)
        except Exception as exc:
            print(f"  couldn't read that WhatsApp contact: {type(exc).__name__}")
            continue
        if person and all(known["number"] != person["number"] for known in found):
            found.append(person)
    found.sort(key=lambda person: _name_rank(person["name"], name))
    return found


WHEN = re.compile(r"\s(?:\d{1,2}:\d{2}(?:\s?[ap]\.?m\.?)?|yesterday|today|monday|tuesday|wednesday|thursday|friday"
                  r"|saturday|sunday|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})(?=\s|$)", re.I)


def _label_name(label):
    """The contact name at the start of a result label, before its message time."""
    label = " ".join(str(label).split())
    when = WHEN.search(label)
    return label[:when.start()] if when else label


def _name_rank(name, want):
    """0 for matching words, 1 for matching word starts, otherwise 2."""
    asked = [word for word in re.findall(r"\w+", str(want).casefold()) if word not in ("my", "the")]
    words = re.findall(r"\w+", str(name).casefold())
    if asked and all(word in words for word in asked):
        return 0
    if asked and all(any(candidate.startswith(word) for candidate in words) for word in asked):
        return 1
    return 2


def _by_name(labels, want):
    return sorted(enumerate(labels), key=lambda row: _name_rank(_label_name(row[1]), want))


STALE_FOR = 2.0
NOBODY = "No chats, contacts or messages found"


def _results(hwnd, stale=None, wait=5.0):
    """Stable result labels after two matching accessibility snapshots."""
    start, last = time.time(), None
    while True:
        time.sleep(0.5)
        began = time.time()
        rows = again(lambda: _rows(hwnd))
        labels = None if rows is None else [label for label, _ in rows]
        if stale is not None and labels == stale and began - start < STALE_FOR:
            labels = None
        if labels is not None and labels == last:
            return labels
        if began - start > wait:
            return labels
        last = labels


ROW_ROLES = ("row", "cell", "option", "treeitem")  # what agent-desktop calls a result's rows (UI Automation's items)


def _rows(hwnd):
    """(label, row) for each person among the search results, in order: the rows under Chats or Contacts that open a
    chat. Each shows three times in the tree; only one of them can be picked and takes the keyboard (Select and
    SetFocus). [] if WhatsApp says it found nobody, None if it shows neither yet: whichever comes first in the page."""
    snap = _snapshot(hwnd)
    shown = next((el for el in snap.elements if win._shown(el) and (
        el.raw_role == "grid" and win.clean_name(el.name) == "Search results." or
        el.raw_role == "statictext" and win.clean_name(el.name) == NOBODY)), None)
    if shown is None:
        return None
    if shown.raw_role != "grid":
        return []
    out, under = [], ""
    for row in shown.descendants():
        if row.raw_role not in ROW_ROLES:
            continue
        label = win.clean_name(row.name)
        if label in HEADINGS:
            under = label
        elif under in PEOPLE and row.ref and win._shown(row) and {"Select", "SetFocus"} <= row.actions:
            out.append((label, row))
    return out


def _read_person(hwnd, i, label):
    """Open the same indexed result if it still has label, then read the matching contact panel."""
    rows = _rows(hwnd) or []
    if i >= len(rows) or rows[i][0] != label or not _open_row(hwnd, rows[i][1], label):
        return None
    person = _panel_person(hwnd)
    if person is None:
        return None
    name, shown = person
    if not _same_chat(label, name or shown):
        return None
    return {"name": name or shown, "number": clean_number(shown), "shown": shown}


def _panel_person(hwnd):
    """Open the current chat's contact panel, read its own name and number, and close that panel."""
    details = _find_button(hwnd, "Profile details")
    if details is None:
        return None
    try:
        _click(details)
    except Exception as exc:
        print(f"  opening WhatsApp's contact panel: {type(exc).__name__}")
    panel, title = _panel(hwnd)
    if panel is None:
        return None
    try:
        if title == "Group info":
            return None
        # its texts, as it shows them, in order: a button's or a box's words are never taken for a name
        said = [" ".join(MARKS.sub("", str(item.name or "")).split()) for item in panel.descendants()
                if item.raw_role == "statictext"]
        said = [value for value in said if value]
        # the number on a line of its own, under the name: never one inside their About
        at = next((i for i, value in enumerate(said) if SHOWN_NUMBER.fullmatch(value)), None)
        if at is None:
            return None
        return (said[at - 1] if at and said[at - 1] not in PANELS else ""), said[at]
    finally:
        try:
            close = next((item for item in panel.descendants()
                          if item.raw_role == "button" and win.clean_name(item.name) == "Close"), None)
            if close is not None:
                _click(close)
        except Exception as exc:
            print(f"  closing WhatsApp's contact panel: {type(exc).__name__}")


def _open_row(hwnd, row, label):
    """Open a search result's chat with a click on its name, as you would: a result's own action opened one chat
    and then nothing more, every time. Only if WhatsApp is in front and that spot is its own window, so nothing else
    is ever clicked: not the popup over it, not another app. True once the chat open is that result's, by the name
    its message box is to; False if it isn't clicked, or doesn't come up."""
    rect = win.ui_rect(row) or row.rect
    if not rect or rect[2] <= rect[0] or rect[3] <= rect[1]:
        return False
    x, y = rect[0] + (rect[2] - rect[0]) * 0.6, (rect[1] + rect[3]) / 2  # on the name, clear of the photo
    if not in_front("whatsapp", hwnd) or not _ours(hwnd, win.root_at(x, y)):
        return False
    win.ui_click_point(x, y)
    start = time.time()
    while True:
        time.sleep(0.3)
        began = time.time()
        _, to = compose_box("whatsapp", hwnd)
        if to and _same_chat(label, to):
            if began - start < 0.5:
                time.sleep(0.8)
            return True
        if began - start > 4.0:
            return False


def _ours(hwnd, at):
    return bool(at) and (at == hwnd or _hosted_by(at, hwnd))


def _chat_key(name):
    return re.sub(r"[\s\ufe0f]+", "", str(name or "")).casefold()


def _letters(text):
    return re.sub(r"\W+", "", str(text)).casefold()


def _same_chat(label, name):
    key = _letters(name)
    if key:
        return _letters(label).startswith(key)
    name = " ".join(str(name).split())
    return bool(name) and " ".join(str(label).split()).startswith(name)


def _panel(hwnd, wait=3.0):
    """The accessible container around WhatsApp's just-opened contact-panel heading."""
    end = time.time() + wait
    while True:
        time.sleep(0.3)
        snap = _snapshot(hwnd)
        head = next((el for el in snap.elements if win.clean_name(el.name) in PANELS and win._shown(el)), None)
        if head is not None:
            break
        if time.time() > end:
            return None, ""
    search = _search_box(snap)
    compose = next((el for el in snap.elements if el.raw_role == "textfield" and
                    win.clean_name(el.name).casefold().startswith(APPS["whatsapp"]["compose"].casefold())), None)
    keep_clear = [el.rect for el in (search, compose) if el is not None and el.rect]
    if not keep_clear:
        return None, ""
    panel = head
    while panel.parent is not None and panel.parent.raw_role != "window":
        up = panel.parent
        rect = up.rect
        if not rect or any(rect[0] <= (kept[0] + kept[2]) / 2 <= rect[2] and
                           rect[1] <= (kept[1] + kept[3]) / 2 <= rect[3] for kept in keep_clear):
            break
        panel = up
    return panel, win.clean_name(head.name)


# Files and photos, on WhatsApp: put on the clipboard as File Explorer's Copy does and pasted into the chat, where
# WhatsApp shows them in its preview ("Open photo, holiday.jpg, item 1 of 2", "Send 2 selected"), read back from there
# before the yes, and sent with its own Send button after it. A no presses Esc and its Discard.
MAX_FILES = 10
MAX_FILE_MB = 100  # WhatsApp takes up to 2 GB, but she'd be uploading for minutes: past this, send it yourself


def check_files(paths):
    """The files, if they can go: there, files, and not too many or too big. Raises with why not."""
    paths = [os.path.abspath(str(p)) for p in paths or []]
    if not paths:
        raise RuntimeError("there's no file to send")
    if len(paths) > MAX_FILES:
        raise RuntimeError(f"that's {len(paths)} files, I send up to {MAX_FILES} at a time")
    for p in paths:
        if not os.path.isfile(p):
            raise RuntimeError(f"I can't find {os.path.basename(p)} any more")
        if os.path.getsize(p) > MAX_FILE_MB * 1024 * 1024:
            raise RuntimeError(f"{os.path.basename(p)} is over {MAX_FILE_MB} MB, send that one yourself")
    return paths


def _button(hwnd, name, part=False):
    """A button read again after a safe, transient agent-desktop failure."""
    return again(lambda: _find_button(hwnd, name, part))


def _find_button(hwnd, name, part=False):
    """The one first button in a window whose name is exact, or contains name with part."""
    found = _named(_snapshot(hwnd), ("button", "menubutton"), name, part)
    return found[0] if found else None


def _click(button):
    """Use a button's saved ref; agent-desktop refuses a stale or ambiguous target before delivery."""
    return win.ui_act(button)


WAITING = re.compile(r"Open [\w ]+, (?P<name>.+), item \d+ of \d+")


def waiting(hwnd):
    """See _waiting, retried only after a safe read failure."""
    return again(lambda: _waiting(hwnd))


def _waiting(hwnd):
    """The file names and count in WhatsApp's attachment preview."""
    buttons = [el for el in _snapshot(hwnd).elements if el.raw_role in ("button", "menubutton") and win._shown(el)]
    names, count = {}, 0
    for button in buttons:
        label = win.clean_name(button.name)
        match = WAITING.fullmatch(label)
        if match:
            names[label] = match["name"]
        match = re.fullmatch(r"Send (\d+) selected", label)
        if match:
            count = int(match[1])
    return sorted(names.values()), count


def _caption_box(hwnd):
    """The preview caption box, retried only after a safe read failure."""
    return again(lambda: _find_caption_box(hwnd))


def _find_caption_box(hwnd):
    """The text field named exactly 'Type a message', which the attachment preview owns."""
    found = _named(_snapshot(hwnd), "textfield", "Type a message")
    return found[0] if found else None


def _focus_box(app, hwnd):
    """The chat's message box, with the keyboard in it and the app in front, or raises."""
    end = time.time() + 3.0  # the chat the link opened may still be drawing its box: a moment, then again
    while True:
        box, _ = compose_box(app, hwnd)
        if box and in_front(app, hwnd):
            # the read just made says if the keyboard's there (the link usually leaves it there), else agent-desktop
            # puts it there and checks
            if ("focused" in box.states or win.ui_focus(box)) and in_front(app, hwnd):
                return box
        if time.time() > end:
            raise RuntimeError(f"I couldn't get to the message box in {APPS[app]['say']}, so I've not typed "
                               f"anything" if box else f"{APPS[app]['say']} didn't come to the front, so I've not "
                               f"typed anything")
        time.sleep(0.3)


def prepare_files(app, contact, paths, caption=""):
    """Open the chat and put the files in WhatsApp's preview, with a caption if there's one, ready for a yes.
    Nothing is sent. Returns what she should read back, as prepare does."""
    app = app_key(app)
    if app != "whatsapp":
        raise RuntimeError("I can only send files on WhatsApp so far")
    paths = check_files(paths)
    caption = " ".join(str(caption or "").split())[:MAX_TEXT]
    name, handle = find_contact(contact, app)
    before = chat_open(app)
    cold = window_of(app) is None  # as in prepare
    hwnd = open_chat(app, handle, "")
    if cold and not drawn(hwnd):
        raise RuntimeError(offline_reason(app, hwnd) or f"{APPS[app]['say']} is still starting, so I've not sent "
                           f"anything. Ask me again in a moment")
    if box_shown(app, hwnd) is None:  # as in prepare: not linked, or the chat didn't open
        why = offline_reason(app, hwnd)
        raise RuntimeError(why or f"{APPS[app]['say']} didn't open the chat with {name}, so I've not sent anything")
    _opened(app, hwnd, before, name, handle)
    if waiting(hwnd)[1] and not discard_preview(app, hwnd):  # files left waiting from before would go too
        raise RuntimeError(f"something's already waiting to go in {APPS[app]['say']}, so I've not added anything")
    box = _focus_box(app, hwnd)
    _, to = compose_box(app, hwnd)
    if box_value(box):  # a draft from before: it would go as the caption
        win.press("ctrl", "a")
        win.press("backspace")
    saved, changed = win.clipboard_snapshot(), None
    names, count = [], 0
    try:
        win.set_clipboard_files(paths)
        changed = win.clipboard_sequence()
        time.sleep(1.2)  # the chat the link just opened can miss a paste straight away
        if not (in_front(app, hwnd) and win.ui_is_focused(box)):
            raise RuntimeError(f"{APPS[app]['say']} went out of the front, so I've not sent anything")
        win.press("ctrl", "v")
        for _ in range(4):
            time.sleep(1.0)
            names, count = waiting(hwnd)
            if count:
                break
    except Exception as exc:  # whatever was pasted is taken out again, never left one Enter from going
        discard_preview(app, hwnd)
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"{APPS[app]['say']} stopped answering, so I've not sent anything") from exc
    finally:
        try:  # what you'd copied comes back, all of it, unless you've copied something since
            if changed is None or win.clipboard_sequence() == changed:
                win.clipboard_restore(saved)
        except Exception as exc:
            print(f"  couldn't put the clipboard back: {exc!r}")
    if count != len(paths) or names != sorted(os.path.basename(p) for p in paths):
        discard_preview(app, hwnd)
        raise RuntimeError(f"{APPS[app]['say']} didn't take {'the file' if len(paths) == 1 else 'all the files'} "
                           f"as they are, so I've not sent anything")
    try:
        return _with_caption(app, hwnd, caption, {"app": app, "say": APPS[app]["say"], "contact": name,
                                                  "handle": handle, "text": caption, "hwnd": hwnd, "checked": True,
                                                  "other": False, "to": to, "files": paths})
    except Exception as exc:
        discard_preview(app, hwnd)
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"{APPS[app]['say']} stopped answering, so I've not sent anything") from exc


def _with_caption(app, hwnd, caption, ready):
    """The caption typed into the preview's own box and read back, then ready as it is. On the keyboard, as the
    message is (type_into), once agent-desktop has seen the keyboard in that box with WhatsApp in front."""
    if caption:  # into the preview's own caption box: "Type a message", to nobody
        box = _caption_box(hwnd)
        focused = bool(box) and in_front(app, hwnd) and (win.ui_is_focused(box) or win.ui_focus(box))
        if not (focused and in_front(app, hwnd)):
            discard_preview(app, hwnd)
            raise RuntimeError("I couldn't get to the caption box, so I've not sent anything")
        win.type_text(caption)
        time.sleep(0.4)
        box = _caption_box(hwnd)
        if box is None or box_value(box) != caption:
            discard_preview(app, hwnd)
            raise RuntimeError(f"{APPS[app]['say']} didn't take the caption, so I've not sent anything")
    return ready


def discard_preview(app, hwnd):
    """Take the files out of WhatsApp's preview with its own Remove attachment buttons, so they aren't left waiting
    in the chat (Esc only asks "Discard unsent message?"), then check none are. The buttons are exact
    agent-desktop refs, so a stale or ambiguous one is refused before delivery."""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    for _ in range(MAX_FILES + 4):
        try:
            if not waiting(hwnd)[1]:
                return True
            button = _button(hwnd, "Remove attachment")
            if button is None:
                break
            _click(button)
        except Exception as exc:  # "An event was unable to invoke any of the subscribers": a moment, then again
            print(f"  clearing WhatsApp's preview: {type(exc).__name__}, again")
        time.sleep(0.6)
    try:
        return not waiting(hwnd)[1]
    except Exception:
        return False


def send_files(ready):
    """Click Send in WhatsApp's preview, once it still holds exactly these files in the same chat, then check it went
    (the preview closes, and the chat's message box has the keyboard again). Only ever called after a yes."""
    app, hwnd, paths = ready["app"], ready.get("hwnd"), ready["files"]
    if not hwnd or not user32.IsWindow(hwnd):
        raise RuntimeError(f"{APPS[app]['say']} isn't open any more, so I've not sent it")
    try:
        win.bring_to_front(hwnd)
    except Exception:
        pass
    time.sleep(0.5)
    if not in_front(app, hwnd):
        raise RuntimeError(f"{APPS[app]['say']} isn't in front, so I've not sent it")
    _, to = compose_box(app, hwnd)
    if ready.get("to") and to != ready["to"]:
        raise RuntimeError("another chat is open now, so I've not sent it")
    names, count = waiting(hwnd)
    button = _button(hwnd, f"Send {count} selected") if count else None
    if count != len(paths) or names != sorted(os.path.basename(p) for p in paths) or button is None:
        raise RuntimeError("what's waiting to go changed, so I've not sent it")
    try:
        _click(button)  # once, whatever it says: Invoke often reports an error for a click that worked
    except Exception as exc:
        print(f"  clicking Send: {type(exc).__name__}, checking what it did")
    answered = False
    for _ in range(6):  # the preview closes once WhatsApp has taken them
        time.sleep(1.0)
        try:
            left = waiting(hwnd)[1]
        except Exception:
            continue
        answered = True
        if not left:
            what = os.path.basename(paths[0]) if len(paths) == 1 else f"{len(paths)} files"
            return True, f"Sent {what} to {ready['contact']}."
    if not answered:
        raise RuntimeError("I pressed Send but couldn't check it went, so look at WhatsApp before asking again")
    raise RuntimeError("WhatsApp still shows it waiting to go, so it may not have sent")


def chat_open(app):
    """The name of the chat open in the app now, as its message box says ("Type a message to Ravi"), or ""."""
    hwnd = window_of(app) if APPS[app]["compose"] else None
    try:
        return compose_box(app, hwnd)[1] if hwnd else ""
    except Exception:
        return ""


def _theirs(app, to, name, handle):
    """True if the chat called to is that person's: by what you call them, emoji aside ("Amma 💖" for Amma, never
    "Mumbai Office" for Mum), the chat she followed for them, or their number."""
    entry = read_follows().get(f"{other_key(APPS[app]['say'])}:{alias_key(name)}") or {}
    digits = re.sub(r"\D", "", str(to))
    return bool(_letters(to)) and _letters(to) == _letters(name) or \
        any(_chat_key(n) == _chat_key(to) for n in entry.get("names") or []) or \
        (len(digits) >= 7 and digits == re.sub(r"\D", "", str(handle)))


def _number_open(hwnd):
    """The number of the chat open in WhatsApp, digits only, off its contact panel, or empty."""
    try:
        person = _panel_person(hwnd)
        return re.sub(r"\D", "", person[1]) if person else ""
    except Exception as exc:
        print(f"  couldn't read the chat's number: {type(exc).__name__}")
        return ""


def _opened(app, hwnd, before, name, handle, wait=2.0):
    """Raises unless the chat open is that person's. The link doesn't always switch chats: for a number not on
    WhatsApp it stays on the chat that was open, and she'd type into Ravi's chat, send it there after a yes, say
    "Sent to Mum." and take Ravi's replies for Mum's. So it's theirs by its name (_theirs), or it changed, given a
    moment, from the chat open before (before), as only the link changes it; or else the number on its contact panel
    is theirs, as for Mum's chat already open, named Amma. A box that names no chat (the app before 2025) can't be
    checked, as before."""
    end, to = time.time() + wait, compose_box(app, hwnd)[1]
    while to and not (_theirs(app, to, name, handle) or (before and _chat_key(to) != _chat_key(before))):
        if time.time() > end:
            if APPS[app]["needs"] == "number" and _number_open(hwnd) == re.sub(r"\D", "", str(handle)):
                return
            raise RuntimeError(f"{APPS[app]['say']} has {to}'s chat open, not {name}'s. Is the number I have for "
                               f"them right? I've not typed anything")
        time.sleep(0.4)
        to = compose_box(app, hwnd)[1] or to


def prepare(app, contact, text):
    """Open the chat with the message typed in, ready for a yes. Returns what she should read back."""
    app = app_key(app)
    if app is None:
        raise RuntimeError("I can only message on WhatsApp or Telegram so far")
    text = clean_text(text)
    name, handle = find_contact(contact, app)
    before = chat_open(app)
    cold = APPS[app]["compose"] and window_of(app) is None  # quit, not just in the tray: see drawn
    hwnd = open_chat(app, handle, text)
    if cold and not drawn(hwnd):
        raise RuntimeError(offline_reason(app, hwnd) or f"{APPS[app]['say']} is still starting, so I've not typed "
                           f"anything. Ask me again in a moment")
    # what the box holds, as box_shown read it: read a second time it could come back unreadable, and then the text
    # the 2025 app's link leaves out was never typed
    shown = box_shown(app, hwnd) if APPS[app]["compose"] else typed_text(app, hwnd)
    if APPS[app]["compose"] and shown is None:
        # no message box: not linked to the phone (the Reconnect button: a 7 s look on the 2025 app's big page, so
        # only now), or the chat didn't open, as for a number not on WhatsApp. Never Enter into whatever that is
        why = offline_reason(app, hwnd)
        raise RuntimeError(why or f"{APPS[app]['say']} didn't open the chat with {name}, so I've not typed anything")
    _opened(app, hwnd, before, name, handle)
    if APPS[app]["compose"]:  # the chat may have switched while _opened waited: one more read of its box, if it
        reread = typed_text(app, hwnd)  # reads, never box_shown's 4 s of tries again
        shown = shown if reread is None else reread
    if shown is not None and shown != text:  # the link left the text out (WhatsApp's 2025 app): she types it
        type_into(app, hwnd, text)
        shown = text
    _, to = compose_box(app, hwnd) if shown is not None else (None, "")
    return {"app": app, "say": APPS[app]["say"], "contact": name, "handle": handle, "text": text, "hwnd": hwnd,
            "checked": shown is not None, "other": False, "to": to}


def send(ready):
    """Press Enter in the chat she opened, then check it went. Only ever called after a yes."""
    if ready.get("files"):
        return send_files(ready)
    if ready.get("other"):
        return _send_other(ready)
    app, hwnd, text = ready["app"], ready.get("hwnd"), ready["text"]
    if not hwnd or not user32.IsWindow(hwnd):
        raise RuntimeError(f"{APPS[app]['say']} isn't open any more, so I've not sent it")
    try:
        win.bring_to_front(hwnd)
    except Exception:
        pass
    time.sleep(0.5)
    if not in_front(app, hwnd):
        raise RuntimeError(f"{APPS[app]['say']} isn't in front, so I've not sent it")
    box, to = compose_box(app, hwnd) if APPS[app]["compose"] else (None, "")
    if box:
        if ready.get("to") and to != ready["to"]:
            raise RuntimeError("another chat is open now, so I've not sent it")
        if box_value(box) != text:
            raise RuntimeError("the message in the box changed, so I've not sent it")
        if "focused" not in box.states:  # Enter only after this exact box has focus, where it sends
            if not win.ui_focus(box):
                raise RuntimeError(f"I couldn't get to the message box in {APPS[app]['say']}, so I've not sent it")
            box, current_to = compose_box(app, hwnd)
            if box is None or current_to != to or "focused" not in box.states:
                raise RuntimeError(f"I couldn't get to the message box in {APPS[app]['say']}, so I've not sent it")
        if not in_front(app, hwnd):
            raise RuntimeError(f"I couldn't get to the message box in {APPS[app]['say']}, so I've not sent it")
    elif ready.get("checked"):
        raise RuntimeError(f"I can't see the message box in {APPS[app]['say']} now, so I've not sent it")
    win.press("enter")
    time.sleep(1.0)
    left = typed_text(app, hwnd)
    for _ in range(4 if box else 0):  # a box that was there a moment ago: read again, never guessed at
        if left is not None:
            break
        time.sleep(0.5)
        left = typed_text(app, hwnd)
    if left is not None:  # the box empties when WhatsApp takes the message
        if left == text:
            raise RuntimeError("it's still sitting in the message box, so it may not have sent")
        return True, f"Sent to {ready['contact']}."
    if box:  # never "Sent" unchecked: after "Sent, as far as I can tell" you said it hadn't come, and asked again, and
        # "Hi" went four times (8 October)
        return False, (f"I pressed Enter, but couldn't read {APPS[app]['say']} back to check it went. Look at the "
                       f"chat before asking me again.")
    return True, f"Sent to {ready['contact']}, as far as I can tell. {APPS[app]['say']} doesn't let me read it back."


# --------------------------------------------------------------------------- the long way round, for other apps
def in_front_of(app_obj):
    """True if that app is the one in front, so a keystroke lands in it and nowhere else."""
    return bool(app_obj) and app_obj.matches(win.foreground_exe())


def focus_other(app_obj, say):
    """Bring the app up and wait until it really is in front. Nothing is typed before this says yes."""
    try:
        win.open_app(app_obj)
    except RuntimeError as exc:
        raise RuntimeError(f"I couldn't open {say}: {exc}")
    end = time.time() + 10
    while time.time() < end:
        windows = win.app_windows(app_obj)
        if windows:
            try:
                win.bring_to_front(windows[0])
            except Exception:
                pass
            time.sleep(0.4)
            if in_front_of(app_obj):
                return windows[0]
        time.sleep(0.3)
    raise RuntimeError(f"I couldn't get {say} to the front, so I've typed nothing")


def _type_now(app_obj, say, value):
    """Type, but only while that app is still the window in front."""
    if not in_front_of(app_obj):
        raise RuntimeError(f"{say} isn't in front any more, so I've stopped and sent nothing")
    win.type_text(value)


def prepare_other(spoken, app_obj, contact, text):
    """Walk an app that has no link of its own: search the name, open the chat, type the message, stop.

    None of it can be read back, so the yes that follows is confirming the chat as much as the words."""
    say = str(getattr(app_obj, "name", "") or spoken or "").strip()
    say = say if any(c.isupper() for c in say) else say.title()  # "signal" as heard reads better as Signal
    app = other_key(spoken) or other_key(say)
    if not app:
        raise RuntimeError("I need the name of an app")
    text = clean_text(text)[:OTHER_MAX_TEXT]
    name, search = find_contact(contact, app)
    recipe = recipe_for(app)
    focus_other(app_obj, say)
    win.press(*recipe["search"])  # the cursor lands in search, and the name typed next replaces what was there
    time.sleep(0.5)
    _type_now(app_obj, say, search)
    time.sleep(recipe["settle"])
    if not in_front_of(app_obj):
        raise RuntimeError(f"{say} isn't in front any more, so I've stopped and sent nothing")
    win.press(*recipe["pick"])  # open the chat it found
    time.sleep(recipe["settle"])
    _type_now(app_obj, say, text)
    time.sleep(0.3)
    return {"app": app, "say": say, "contact": name, "handle": search, "text": text, "hwnd": None,
            "checked": False, "other": True, "recipe": recipe, "obj": app_obj}


def _send_other(ready):
    """Press Enter, then keep what worked: the shortcut, and the name that found the person."""
    app_obj, say = ready["obj"], ready["say"]
    if not in_front_of(app_obj):
        raise RuntimeError(f"{say} isn't in front any more, so I've not sent it")
    win.press("enter")
    time.sleep(0.6)
    try:
        save_recipe(ready["app"], say, ready["recipe"])
        save_contact(ready["contact"], ready["app"], ready["handle"])
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"  sent, but couldn't remember how: {exc!r}")
    return True, f"Sent to {ready['contact']} on {say}. I can't read {say} back, so do check it landed."


def discard(ready):
    """Clear a message you said no to, so it isn't left sitting in someone's chat. Only if the app is in front, and
    where she can read the box, only the message she typed, still in the chat she typed it in, with the keyboard in
    its box: a no once wiped the draft you'd started to Ravi meanwhile, and left Mum's "hi" in her box."""
    if not ready:
        return False
    try:
        app, hwnd = ready.get("app"), ready.get("hwnd")
        if ready.get("files"):  # only these files, in their chat: a send to Amma that ran out took out the photo
            # you had attached to Ravi meanwhile, as every Remove attachment in the window was clicked
            if not hwnd or not user32.IsWindow(hwnd):
                return False
            names = waiting(hwnd)[0]
            if not names:
                return True
            to = compose_box(app, hwnd)[1] if APPS[app]["compose"] else ""
            if (ready.get("to") and to != ready["to"]) or names != sorted(os.path.basename(p) for p in ready["files"]):
                return False
            return discard_preview(app, hwnd)
        if not (in_front_of(ready["obj"]) if ready.get("other") else (hwnd and in_front(app, hwnd))):
            return False
        box, to = (None, "") if ready.get("other") or not APPS[app]["compose"] else compose_box(app, hwnd)
        if box:
            if (ready.get("to") and to != ready["to"]) or box_value(box) != ready["text"]:
                return False
            if "focused" not in box.states:
                if not win.ui_focus(box):
                    return False
                box, current_to = compose_box(app, hwnd)
                if box is None or current_to != to or "focused" not in box.states:
                    return False
            if not in_front(app, hwnd):
                return False
        elif ready.get("checked"):  # it was read before: not now, so it isn't the box she typed in
            return False
        win.press("ctrl", "a")
        time.sleep(0.15)
        win.press("backspace")
        time.sleep(0.2)
        left = None if ready.get("other") else typed_text(app, hwnd)
        return left is None or not str(left).strip()
    except Exception as exc:
        print(f"  couldn't clear the message box: {exc!r}")
        return False
