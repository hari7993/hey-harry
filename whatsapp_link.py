"""Hey Harry's WhatsApp link: a linked device on your own WhatsApp that only reads (whatsapp_bridge/bridge.mjs, on
Baileys), so she can tell you what a message says, where Windows' notifications only say who it's from: "what did
Amma say?", "read my WhatsApp messages". It never sends a message, a reaction or a read receipt and never shows you
online, and takes none of your old chats: only what comes in once it's linked.

Linked once by a code you scan on your phone ("link WhatsApp": WhatsApp > Settings > Linked devices > Link a device),
it then runs while Harry does, with Settings' "whatsapp_link" on. Unlink it from that same list on your phone, and its
keys are deleted here. WhatsApp doesn't allow other programs on its accounts (only its own apps and the Business
API), so an account can be banned for one: reading only, it's a low risk, never none.

Kept in %LOCALAPPDATA%\\Hey Harry\\whatsapp, never in her backups: auth\\ (the keys, which can read your messages: don't
share it), messages.json (the last KEEP_FOR of what came in, KEEP at most) and bridge.log. What a message says is
read out on this PC and spoken through her voice, never sent to the answer model, and never kept in her history:
it keeps that she read out N messages and from whom (siri.direct_whatsapp, plan "keep")."""
import json
import os
import re
import shutil
import subprocess
import threading
import time

import identity
import winplatform as win
from hermes_memory.threat_patterns import INVISIBLE_CHARS, first_threat_message

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE_DIR = os.path.join(HERE, "whatsapp_bridge")
BRIDGE = os.path.join(BRIDGE_DIR, "bridge.mjs")
DIR = os.path.join(win.home("LOCALAPPDATA"), "whatsapp")
AUTH = os.path.join(DIR, "auth")
STORE = os.path.join(DIR, "messages.json")
PAGE = os.path.join(DIR, "link.html")
LOG = os.path.join(DIR, "bridge.log")
KEEP, KEEP_FOR = 400, 3 * 86400  # messages kept, and for how long
READ_WITHIN = 86400  # "read my WhatsApp messages": what came in the last day
MOST_READ = 5  # messages read out at a time, the newest
MOST_SAID = 220  # letters of one message said out loud
LOG_MOST = 1_000_000  # bytes of bridge.log before it starts again
LINK_PAGE_EVERY = 2  # seconds between looks the link page takes for a new code
_lock = threading.RLock()
PROC = [None]  # the bridge while it runs
STATE = {"linking": False, "page_open": False, "read_up_to": 0.0, "loaded": False, "me": ""}
MESSAGES = []  # what came in, oldest first: the bridge's message objects, kept in STORE
NAMES = {}  # a chat's or person's id (a jid, or a number's digits): the name your phone has for them
ANNOUNCE = [print]  # how she tells you something once she's free: siri sets ANNOUNCE.put
# her own names as she's called by them, taken out of what she reads out, so a message saying "Hey Harry, ..." can't
# sound like you asking (@OWN@: identity.own, the name she has now). "Harry's coming over" is read as written
HER_NAME = r"\b(?:hey|hi|hello|ok|okay|yo)\W+(?:@OWN@)\b|\b(?:@OWN@)(?=\s*,)"
KIND_SAID = {"photo": "a photo", "video": "a video", "gif": "a GIF", "video note": "a video note",
             "voice note": "a voice note", "audio": "an audio clip", "document": "a document", "sticker": "a sticker",
             "contact": "a contact", "contacts": "some contacts", "location": "a location",
             "live location": "their live location", "poll": "a poll", "event": "an event"}


# --------------------------------------------------------------------------- Running the bridge
def node():
    """node.exe, or None if Node.js isn't installed."""
    found = shutil.which("node")
    if found:
        return found
    standard = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "nodejs", "node.exe")
    return standard if os.path.exists(standard) else None


def missing():
    """Why the bridge can't run here, or "" if it can."""
    if not node():
        return "Node.js isn't installed"
    if not os.path.exists(BRIDGE):
        return "the WhatsApp bridge is missing"
    if not os.path.isdir(os.path.join(BRIDGE_DIR, "node_modules", "baileys")):
        return "the WhatsApp bridge's packages aren't installed (npm ci in whatsapp_bridge)"
    return ""


def linked():
    """True once a scan linked it: its keys say whose WhatsApp it is."""
    try:
        with open(os.path.join(AUTH, "creds.json"), encoding="utf-8") as f:
            return bool((json.load(f) or {}).get("me"))
    except (OSError, ValueError):
        return False


def running():
    proc = PROC[0]
    return proc is not None and proc.poll() is None


def start(link=False):
    """Starts the bridge, to link it (a code to scan) or as linked. True if it's running."""
    with _lock:
        if running():
            return True
        why = missing()
        if why:
            print(f"  [whatsapp: can't start, {why}]")
            return False
        load()
        os.makedirs(AUTH, exist_ok=True)
        try:
            if os.path.getsize(LOG) > LOG_MOST:
                os.remove(LOG)
        except OSError:
            pass
        log = open(LOG, "a", encoding="utf-8")
        try:
            proc = subprocess.Popen([node(), BRIDGE, AUTH] + (["--link"] if link else []), cwd=BRIDGE_DIR,
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True,
                                    encoding="utf-8", errors="replace", bufsize=1,
                                    creationflags=getattr(win, "CREATE_NO_WINDOW", 0))
        finally:
            log.close()  # the bridge has its own handle to it
        PROC[0] = proc
        STATE.update(linking=bool(link), page_open=False)
        threading.Thread(target=_read, args=(proc,), daemon=True, name="whatsapp-link").start()
        print(f"  [whatsapp: {'showing a code to link' if link else 'linked, listening'}]")
        return True


def stop(wait=4.0):
    """Ends the bridge, asking first, then by force."""
    proc = PROC[0]
    if proc is None:
        return
    try:
        proc.stdin.write('{"cmd": "stop"}\n')
        proc.stdin.flush()
        proc.wait(wait)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        proc.kill()
    PROC[0] = None


def _read(proc):
    for line in proc.stdout:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        try:
            on_event(event)
        except Exception as exc:  # one odd message never ends the link
            print(f"  [whatsapp: couldn't take {event.get('type')!r}: {exc!r}]")
    code = proc.wait()
    if PROC[0] is proc:
        PROC[0] = None
    print(f"  [whatsapp: the bridge stopped ({code})]")


def keep_running(wanted, every=15.0):
    """Runs the bridge whenever wanted() and it's linked, started again if it stops (it reconnects by itself while it
    runs, gently), and ends it once not wanted."""
    load()
    while True:
        try:
            if wanted() and linked() and not running():
                start()
            elif not wanted() and running() and not STATE["linking"]:
                stop()
        except Exception as exc:
            print(f"  [whatsapp: {exc!r}]")
        time.sleep(every)


def link_now():
    """Shows a code to scan, to link her to your WhatsApp. What she says, or raises RuntimeError with why not."""
    why = missing()
    if why:
        raise RuntimeError(f"I can't link WhatsApp: {why}.")
    if linked():
        if not running():
            start()
        return "already linked"
    stop()
    if not start(link=True):
        raise RuntimeError("I couldn't start WhatsApp's link.")
    return "showing the code"


def clear_auth():
    """Deletes its keys, unlinked: only ever the folder AUTH."""
    if os.path.basename(AUTH) == "auth" and os.path.dirname(AUTH) == DIR and os.path.isdir(AUTH):
        shutil.rmtree(AUTH, ignore_errors=True)


# --------------------------------------------------------------------------- What the bridge says
def on_event(event):
    kind = event.get("type")
    if kind == "qr":
        write_page(event.get("url"))
        if not STATE["page_open"]:
            STATE["page_open"] = True
            open_page()
    elif kind == "open":
        STATE["me"] = str((event.get("me") or {}).get("id") or "")
        if event.get("linked"):
            STATE["linking"] = False
            write_page(state="linked")
            print("  [whatsapp: linked]")
            ANNOUNCE[0]("WhatsApp's linked. From now on I can read you what comes in, and I'll never send anything "
                        "from it.")
        else:
            print("  [whatsapp: connected]")
    elif kind == "message":
        keep(event)
    elif kind == "contacts":
        with _lock:
            for c in event.get("contacts") or []:
                name = str(c.get("name") or "").strip()  # as saved on your phone, never their own profile name
                if name:
                    for key in (c.get("id"), c.get("lid"), c.get("pn"), digits(c.get("pn") or c.get("id"))):
                        if key:
                            NAMES[str(key)] = name[:60]
            save()
    elif kind == "logged_out":
        STATE["linking"] = False
        clear_auth()
        print("  [whatsapp: unlinked, its keys deleted]")
        ANNOUNCE[0]("WhatsApp unlinked me, so I've stopped reading it. Say link WhatsApp to link me again.")
    elif kind == "status":
        state = event.get("state")
        print(f"  [whatsapp: {state}" + (f", {event.get('code')} {event.get('why') or ''}".rstrip()
                                         if event.get("code") else "") + "]")
        if state == "qr_expired":
            STATE["linking"] = False
            write_page(state="expired")
            ANNOUNCE[0]("The WhatsApp code ran out before it was scanned. Say link WhatsApp for a new one.")
        elif state == "refused":
            STATE["linking"] = False
            ANNOUNCE[0]("WhatsApp turned down the link, so I've stopped trying. You can see Linked devices on your "
                        "phone.")


def write_page(url=None, state="code"):
    """The page with the code to scan, which looks again every LINK_PAGE_EVERY seconds for a new one."""
    if state == "code" and not url:
        return
    body = {
        "code": f'<img src="{url}" alt="WhatsApp link code"><p>On your phone: <b>WhatsApp &gt; Settings &gt; Linked '
                f'devices &gt; Link a device</b>, then point it at this code. It changes every 20 seconds or so.</p>'
                f'<p class="small">This links Hey Harry to your WhatsApp to read what comes in. It never sends '
                f'anything. WhatsApp doesn\'t allow other programs on its accounts, so there\'s a small risk to the '
                f'account. Unlink it any time from that same list.</p>',
        "linked": "<h2>Linked</h2><p>Hey Harry can read what comes in on WhatsApp now. You can close this tab.</p>",
        "expired": "<h2>The code ran out</h2><p>Say <b>link WhatsApp</b> for a new one.</p>",
    }[state]
    refresh = f'<meta http-equiv="refresh" content="{LINK_PAGE_EVERY}">' if state == "code" else ""
    html = (f'<!doctype html><html><head><meta charset="utf-8">{refresh}<title>Link WhatsApp to Hey Harry</title>'
            '<style>body{font-family:Segoe UI,sans-serif;background:#fff;color:#030712;text-align:center;'
            'margin:40px auto;max-width:520px}img{width:320px;height:320px;image-rendering:pixelated}'
            'p{color:#364152;line-height:1.5}.small{font-size:13px;color:#697282}</style></head><body>'
            f'<h1>Link WhatsApp</h1>{body}</body></html>')
    os.makedirs(DIR, exist_ok=True)
    tmp = PAGE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, PAGE)


def open_page():
    try:
        os.startfile(PAGE)
    except OSError as exc:
        print(f"  [whatsapp: couldn't open the code: {exc!r}]")


# --------------------------------------------------------------------------- What came in
def digits(jid):
    """The phone number in a jid ("919876543210@s.whatsapp.net"), or "" for one without (a group, an @lid)."""
    jid = str(jid or "")
    return re.sub(r"\D", "", jid.split("@")[0].split(":")[0]) if jid.endswith("@s.whatsapp.net") else ""


def load():
    with _lock:
        if STATE["loaded"]:
            return
        STATE["loaded"] = True
        try:
            with open(STORE, encoding="utf-8") as f:
                data = json.load(f) or {}
        except (OSError, ValueError):
            return
        MESSAGES[:] = [m for m in data.get("messages") or [] if isinstance(m, dict) and m.get("at")]
        NAMES.update({str(k): str(v) for k, v in (data.get("names") or {}).items()})
        STATE["read_up_to"] = float(data.get("read_up_to") or 0.0)


def save():
    with _lock:
        os.makedirs(DIR, exist_ok=True)
        tmp = STORE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"messages": MESSAGES, "names": NAMES, "read_up_to": STATE["read_up_to"]}, f,
                      ensure_ascii=False)
        os.replace(tmp, STORE)


def keep(message, now=None):
    """One more message, the oldest dropped past KEEP or KEEP_FOR. False if it was had already."""
    now = time.time() if now is None else now
    m = {k: message.get(k) for k in ("id", "chat", "chat_pn", "chat_name", "group", "from_me", "sender", "sender_pn",
                                     "push_name", "at", "kind", "text")}
    m["at"] = float(m.get("at") or now)
    with _lock:
        load()
        if any(o.get("id") == m["id"] and o.get("chat") == m["chat"] for o in MESSAGES if m["id"]):
            return False
        MESSAGES.append(m)
        MESSAGES.sort(key=lambda o: o["at"])
        MESSAGES[:] = [o for o in MESSAGES if now - o["at"] < KEEP_FOR][-KEEP:]
        save()
    return True


def _contacts_book():
    """{the last 10 digits of a number: its name} from her contacts book (messaging.read_contacts)."""
    try:
        import messaging
        book = messaging.read_contacts()
    except Exception:
        return {}
    out = {}
    for alias, c in (book or {}).items():
        number = re.sub(r"\D", "", str((c or {}).get("whatsapp") or ""))
        if len(number) >= 7:
            out[number[-10:]] = str((c or {}).get("name") or alias)
    return out


def _from_toasts(m):
    """The name your phone has for a one-to-one chat, from WhatsApp's own notification of the message on this PC
    (watch.notifications): its title is the name, its text the message. "" if none matches."""
    text = " ".join(str(m.get("text") or "").split()).lower()[:40]
    if m.get("group") or len(text) < 4:
        return ""
    try:
        import watch
        toasts = watch.notifications(m["at"] - 120)
    except Exception:
        return ""
    for n in toasts:
        if n.get("app") == "WhatsApp" and abs(float(n.get("when") or 0) - m["at"]) < 300 and \
                text in " ".join(str(n.get("text") or "").split()).lower():
            return str(n.get("from") or "")[:60]
    return ""


def _number_said(number):
    return "a number ending in " + " ".join(number[-4:]) if len(number) >= 4 else "someone"


def name_of(m, book=None):
    """Who a one-to-one message is from, or whose group it's in, as your phone names them."""
    book = _contacts_book() if book is None else book
    if m.get("group"):
        return str(m.get("chat_name") or NAMES.get(str(m.get("chat"))) or "a group")
    number = digits(m.get("chat_pn")) or digits(m.get("chat"))
    found = (book.get(number[-10:]) if number else None) or NAMES.get(str(m.get("chat"))) or \
        NAMES.get(str(m.get("chat_pn"))) or (NAMES.get(number) if number else None)
    if not found:
        found = _from_toasts(m)
        if found and not re.fullmatch(r"[\d\s()+.-]+", found):
            with _lock:
                NAMES[str(m.get("chat"))] = found
                save()
    if found and not re.fullmatch(r"[\d\s()+.-]+", found):
        return found
    return str(m.get("push_name") or "").strip()[:60] or _number_said(number)


def sender_of(m, book=None):
    """Who sent a message in a group."""
    book = _contacts_book() if book is None else book
    number = digits(m.get("sender_pn")) or digits(m.get("sender"))
    return (book.get(number[-10:]) if number else None) or NAMES.get(str(m.get("sender"))) or \
        str(m.get("push_name") or "").strip()[:60] or _number_said(number)


def matches(who, m, book=None):
    """True if who ("Amma", "Ravi") is whom message m is from, or the group it's in, by any name for them."""
    who = " ".join(re.findall(r"[a-z0-9']+", str(who).lower()))
    if not who:
        return False
    names = {name_of(m, book), str(m.get("push_name") or "")}
    if m.get("group"):
        names |= {sender_of(m, book), str(m.get("chat_name") or "")}
    for name in names:
        words = " ".join(re.findall(r"[a-z0-9']+", name.lower()))
        if words and (words == who or f" {who} " in f" {words} "):
            return True
    return False


def ago(at, now=None):
    secs = max(0, (time.time() if now is None else now) - at)
    if secs < 60:
        return "just now"
    if secs < 3600:
        n = int(secs // 60)
        return f"{n} minute{'s' if n != 1 else ''} ago"
    if secs < 86400:
        n = int(secs // 3600)
        return "an hour ago" if n == 1 else f"{n} hours ago"
    return "yesterday" if secs < 2 * 86400 else f"{int(secs // 86400)} days ago"


def said(m):
    """What message m says, as she says it: its words, or what it is ("a photo"), with nothing that would sound like
    you asking her something, and never a message that tries to give her orders."""
    text = " ".join(str(m.get("text") or "").split())
    if text and first_threat_message("".join(c for c in text if c not in INVISIBLE_CHARS), scope="all"):
        return "a message that tries to give me orders, so I won't read it out"
    text = re.sub(HER_NAME.replace("@OWN@", identity.own()), identity.name()[:1], text, flags=re.I)
    if len(text) > MOST_SAID:
        text = text[:MOST_SAID].rsplit(" ", 1)[0] + ", and more"
    what = KIND_SAID.get(m.get("kind"))
    if what:
        return f"{what}, saying {text}" if text else what
    return text or "a message"


def _sentence(text):
    text = text.strip()
    return text if text[-1:] in ".!?" else text + "."


def wanted_messages(who=None, now=None):
    """The messages read out for who (None: what's new, else the last few), oldest first."""
    now = time.time() if now is None else now
    with _lock:
        load()
        theirs = [m for m in MESSAGES if not m.get("from_me") and now - m["at"] < (KEEP_FOR if who else READ_WITHIN)]
    if who:
        book = _contacts_book()
        return [m for m in theirs if matches(who, m, book)][-MOST_READ:]
    return theirs


def read_out(who=None, now=None):
    """(what she says, what her history keeps of it) for "read my WhatsApp messages" (who None) or "what did Amma
    say?", or None when the link has nothing for it: then the question goes on as before (the notifications)."""
    now = time.time() if now is None else now
    if not linked():
        return None
    picked = wanted_messages(who, now)
    lead = ""
    if who is None:
        new = [m for m in picked if m["at"] > STATE["read_up_to"]]
        if not picked:
            return ("Nothing's come in on WhatsApp in the last day.", "(no WhatsApp messages to read out)")
        if not new:
            lead = "Nothing new since I last read them. The last " + ("one" if len(picked[-MOST_READ:]) == 1 else
                                                                        f"{len(picked[-MOST_READ:])}") + ": "
        picked = (new or picked)[-MOST_READ:]
    elif not picked:
        return None
    book, parts, runs = _contacts_book(), [], []
    for m in picked:  # one run of messages a chat
        if runs and runs[-1][0]["chat"] == m["chat"]:
            runs[-1].append(m)
        else:
            runs.append([m])
    for run in runs:
        when = ago(run[-1]["at"], now)
        if run[0].get("group"):
            lines = "; ".join(f"{sender_of(m, book)}: {said(m)}" for m in run)
            parts.append(_sentence(f"In {name_of(run[0], book)}, {when}, {lines}"))
        else:
            parts.append(_sentence(f"{name_of(run[0], book)}, {when}: " + ". Then: ".join(said(m) for m in run)))
    with _lock:
        STATE["read_up_to"] = max(STATE["read_up_to"], max(m["at"] for m in picked))
        save()
    who_said = sorted({name_of(run[0], book) for run in runs})
    keep_line = f"(read out {len(picked)} WhatsApp message{'s' if len(picked) != 1 else ''} from " + \
        ", ".join(who_said) + ")"
    return lead + " ".join(parts), keep_line


def latest_chat_name(within=600.0, now=None):
    """Whom the newest message in the last within seconds is from, for "what did he say?" after a heads-up."""
    now = time.time() if now is None else now
    with _lock:
        load()
        theirs = [m for m in MESSAGES if not m.get("from_me") and now - m["at"] < within]
    return name_of(theirs[-1]) if theirs else None
