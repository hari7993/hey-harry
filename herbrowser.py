"""Her own browser (31 October 2026, the owner's ask, after OpenMuse's agent computer, github.com/CopilotKit/openmuse,
MIT): a Chrome of her own, with a profile only she uses, that a job in the background works in instead of taking your
screen. You sign in to the sites she should use yourself: "show me your browser" (or "sign in to LinkedIn in your
browser") puts it in front of you, you sign in, and "hide your browser" puts it away. The logins stay in its profile,
in %LOCALAPPDATA%\\Hey Harry\\Browser, so she's still signed in after a restart. She never types a password or a code: a
site that wants her to sign in again is left to you, as OpenMuse hands a sign-in to you with Take control.

Driven over a pipe of its own (Chrome's --remote-debugging-pipe), never a network port: no other program on this PC
can drive it or read its logins, as any could through a port. Chrome then tells the pages it's automated
(navigator.webdriver), and it's never disguised: a site that won't have that ("verify you're human") is left to you
too. Chrome if it's here, else Edge, which every Windows PC has. On 31 October: started in 0.5 s, 264 MB of its own
memory while it worked (light flags, FLAGS), and closed IDLE seconds after its last job.

agent.py works on its page as on a window: a job's pin is TAB, and while it is, agent's win is answered from here
(Surface): the page's controls from Chrome's own accessibility tree, as UI Automation gives a window's, and clicks,
typing and keys sent into the page, never by your mouse or keyboard. While she works its window sits just off the edge
of your screens, never minimised: minimised, Chrome stops drawing it, and its screenshots never came (31 October). Its
page is a fixed W x H then, so a screenshot's pixels are the page's.

From OpenMuse's browser worker too (apps/worker): only public sites, never this PC or your home network (a router's
page, a printer's), so a page can't send her there; a page's own pop-up questions are dismissed, so a "confirm()"
can't freeze her or slip a yes past her own; and nothing is downloaded."""
import atexit
import collections
import ipaddress
import json
import os
import re
import socket
import subprocess
import threading
import time
import warnings

import settings
import winplatform as win

host = None  # siri, for its list of sites by name (bind)
TAB = "her-browser"  # a job's pin while it works in her browser, in place of a window's handle
W, H = 1280, 900  # the page's size while she works in it, in CSS pixels, which its screenshots are in too
IDLE = 120  # seconds unused, and not shown or held by a job, before it's closed: 264 MB is a lot to keep for nothing
LOAD_WAIT = 15  # seconds a page may take to load before she looks at it anyway
CALL_WAIT = 15  # seconds one DevTools call may take
# Light, and drawing while minimised: no sync, extensions, translate or background downloads, two renderers at most,
# no sound, and a page that keeps painting and running when its window is minimised or covered. Edge's implicit
# sign-in (msImplicitSignin) is off, or it would sign her profile in with your Windows account and its passwords
FLAGS = ("--no-first-run", "--no-default-browser-check", "--disable-sync", "--disable-extensions",
         "--disable-background-networking", "--disable-default-apps", "--no-pings", "--mute-audio",
         "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
         "--disable-background-timer-throttling", "--renderer-process-limit=2",
         "--disable-features=CalculateNativeWinOcclusion,Translate,OptimizationHints,MediaRouter,"
         "AutofillServerCommunication,msImplicitSignin", f"--window-size={W},{H}")
# Chrome's accessibility roles, as agent knows a window's controls (winplatform.ROLES)
ROLE_OF = {"button": "button", "PopUpButton": "button", "ToggleButton": "button", "togglebutton": "button",
           "link": "link", "textbox": "edit", "searchbox": "edit", "textField": "edit", "TextField": "edit",
           "spinbutton": "edit", "combobox": "combobox", "ComboBoxGrouping": "combobox",
           "ComboBoxMenuButton": "combobox", "checkbox": "checkbox", "switch": "checkbox",
           "menuitemcheckbox": "checkbox", "radio": "radio", "menuitemradio": "radio", "tab": "tab",
           "menuitem": "menuitem", "option": "listitem", "listitem": "listitem", "treeitem": "listitem"}
LISTED = {"listitem"}  # capped at winplatform.SNAP_LISTS, as a mailbox's are
DIALOGS = {"dialog", "alertdialog"}
# Keys sent into the page (agent's keys step), by the names siri.press_keys takes: (key, code, Windows key code)
KEYS = {"enter": ("Enter", "Enter", 13), "tab": ("Tab", "Tab", 9), "esc": ("Escape", "Escape", 27),
        "backspace": ("Backspace", "Backspace", 8), "delete": ("Delete", "Delete", 46), "space": (" ", "Space", 32),
        "up": ("ArrowUp", "ArrowUp", 38), "down": ("ArrowDown", "ArrowDown", 40), "left": ("ArrowLeft", "ArrowLeft", 37),
        "right": ("ArrowRight", "ArrowRight", 39), "home": ("Home", "Home", 36), "end": ("End", "End", 35),
        "page_up": ("PageUp", "PageUp", 33), "page_down": ("PageDown", "PageDown", 34)}
KEY_ALIASES = {"escape": "esc", "return": "enter", "pgup": "page_up", "pageup": "page_up", "pgdn": "page_down",
               "pagedown": "page_down", "page down": "page_down", "page up": "page_up", "del": "delete",
               "arrowup": "up", "arrowdown": "down", "arrowleft": "left", "arrowright": "right"}
MODIFIERS = {"alt": 1, "ctrl": 2, "control": 2, "shift": 8}
EDITING = {"a": "selectAll", "c": "copy", "x": "cut", "v": "paste", "z": "undo", "y": "redo"}  # Ctrl+ these
NOT_HERE = "In my browser a site's opened with a website step, not keys"  # Ctrl+L, Ctrl+T and the like
LOCAL_OK = False  # this PC's own addresses opened anyway: only for the live check, which serves its page from here

_lock = threading.RLock()
_chrome = [None]  # the Pipe while it runs
_page = {"session": None, "target": None, "window": None}
_shown = [False]  # in front of you: her jobs in it wait (free)
_yours = [None]  # the window you were in when you had it shown, given back when it's put away
_last = [0.0]  # when it was last used
_holders = set()  # ids of the jobs working in it, which keep it open
_closer = []  # the thread that closes it when idle, started once


def bind(module):
    global host
    host = module


# --------------------------------------------------------------------------- Chrome, over its own pipe
class Pipe:
    """Chrome's DevTools protocol over a pipe of its own: a JSON message ending in a NUL each way. Two anonymous
    pipes, their handles inherited by Chrome alone (--remote-debugging-io-pipes) and no other process."""

    def __init__(self, args):
        import msvcrt
        to_r, to_w = os.pipe()
        from_r, from_w = os.pipe()
        handles = [msvcrt.get_osfhandle(to_r), msvcrt.get_osfhandle(from_w)]
        for h in handles:
            os.set_handle_inheritable(h, True)
        info = subprocess.STARTUPINFO()
        info.lpAttributeList = {"handle_list": handles}  # only these two go to Chrome, none of hers
        # shown without taking the focus: on 31 October its window, off your screens, still became the one your
        # keys went to
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 4  # SW_SHOWNOACTIVATE
        with warnings.catch_warnings():  # the handle list stands in for close_fds, which is the point
            warnings.simplefilter("ignore", RuntimeWarning)
            self.proc = subprocess.Popen([*args, "--remote-debugging-pipe",
                                          f"--remote-debugging-io-pipes={handles[0]},{handles[1]}"],
                                         startupinfo=info, close_fds=False, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
        os.close(to_r)
        os.close(from_w)
        self._out = os.fdopen(to_w, "wb", buffering=0)
        self._in = os.fdopen(from_r, "rb", buffering=0)
        self._replies, self._n, self.alive = {}, 0, True
        self._ready = threading.Condition()
        self._send = threading.Lock()
        self.events = collections.deque(maxlen=100)
        threading.Thread(target=self._read, name="her-browser", daemon=True).start()

    def _read(self):
        buf = b""
        try:
            while True:
                chunk = self._in.read(1 << 20)
                if not chunk:
                    break
                buf += chunk
                while b"\0" in buf:
                    raw, _, buf = buf.partition(b"\0")
                    try:
                        msg = json.loads(raw)
                    except ValueError:
                        continue
                    if msg.get("method") == "Page.javascriptDialogOpening":
                        threading.Thread(target=self._answer, args=(msg,), daemon=True).start()
                    with self._ready:
                        if "id" in msg:
                            self._replies[msg["id"]] = msg
                            self._ready.notify_all()
                        else:
                            self.events.append(msg)
        except OSError:
            pass
        with self._ready:
            self.alive = False
            self._ready.notify_all()

    def _answer(self, msg):
        """A page's own question (alert, confirm, prompt) answered no, so it can't freeze her page or slip a yes past
        hers; "Leave this page?" answered yes, as only her going elsewhere asks it."""
        params = msg.get("params") or {}
        leave = params.get("type") == "beforeunload"
        print(f"  her browser: the page asked {str(params.get('message') or '')[:80]!r}, "
              f"{'left it' if leave else 'said no'}")
        try:
            self.call("Page.handleJavaScriptDialog", session=msg.get("sessionId"), timeout=5, accept=leave)
        except Exception as exc:
            print(f"  her browser: {exc!r}")

    def call(self, method, session=None, timeout=CALL_WAIT, **params):
        """The result of one DevTools command. RuntimeError with Chrome's own message if it refused it,
        TimeoutError if it didn't answer in time, ConnectionError once Chrome has gone."""
        with self._send:
            if not self.alive:
                raise ConnectionError("my browser has closed")
            self._n += 1
            n = self._n
            msg = {"id": n, "method": method, "params": params}
            if session:
                msg["sessionId"] = session
            try:
                self._out.write(json.dumps(msg).encode() + b"\0")
            except OSError:
                raise ConnectionError("my browser has closed")
        end = time.monotonic() + timeout
        with self._ready:
            while n not in self._replies:
                if not self.alive:
                    raise ConnectionError("my browser has closed")
                left = end - time.monotonic()
                if left <= 0:
                    raise TimeoutError(f"my browser didn't answer {method}")
                self._ready.wait(left)
            reply = self._replies.pop(n)
        if "error" in reply:
            raise RuntimeError(str(reply["error"].get("message") or reply["error"]))
        return reply.get("result") or {}

    def close(self):
        try:
            self.call("Browser.close", timeout=3)
        except Exception:
            pass
        try:
            self.proc.wait(5)
        except Exception:
            self.proc.kill()
        for f in (self._out, self._in):
            try:
                f.close()
            except OSError:
                pass


def program():
    """Chrome's path on this PC, else Edge's, else ""."""
    local = os.environ.get("LOCALAPPDATA", "")
    places = [os.path.join(local, r"Google\Chrome\Application\chrome.exe")]
    for root in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
        places.append(os.path.join(root, r"Google\Chrome\Application\chrome.exe"))
    for root in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
        places.append(os.path.join(root, r"Microsoft\Edge\Application\msedge.exe"))
    return next((p for p in places if p and os.path.isfile(p)), "")


def exe():
    """Its program's name as agent knows a window's: chrome.exe or msedge.exe."""
    return os.path.basename(program()).lower() or "chrome.exe"


def profile():
    """Where its logins live, apart from her other data and yours."""
    return os.path.join(win.home("LOCALAPPDATA"), "Browser")


def available():
    """True if a job may work in her browser: it's on in Settings, and there's a Chrome or Edge for it. Never in a
    test run, which mustn't start a browser."""
    return bool(settings.get("own_browser")) and not os.getenv("HEYHARRY_TESTING") and bool(program())


def running():
    return _chrome[0] is not None and _chrome[0].alive


def shown():
    """True while you have her browser: in front of you on the PC (show), or from your phone (remote_on). Her jobs in
    it wait meanwhile (wait_till_free)."""
    return running() and (_shown[0] or remote_on())


def _orphans():
    """Kills a Chrome left on her profile by an earlier run of hers that didn't get to close it: a second one on
    the same profile hands over to it and quits at once, and she could never drive it."""
    import psutil
    mine = profile().lower()
    for proc in psutil.process_iter(["pid", "cmdline"]):
        line = " ".join(proc.info["cmdline"] or []).lower()
        if "--remote-debugging-pipe" in line and f"--user-data-dir={mine}" in line:
            try:
                proc.kill()
            except psutil.Error:
                pass


class Trouble(RuntimeError):
    """Her browser itself can't be used: it won't start, or it stopped answering. Not a page that won't have her
    (a sign-in, a check), which is left to you. A job that hits this is offered on your screen instead
    (siri.screen_offer, 31 October 2026, the owner's ask)."""


def _start():
    path = program()
    if not path:
        raise Trouble("there's no Chrome or Edge on this PC for my browser")
    os.makedirs(profile(), exist_ok=True)
    _orphans()
    was = win.front_window()
    left, top = _away_spot()
    chrome = Pipe([path, f"--user-data-dir={profile()}", *FLAGS, f"--window-position={left},{top}", "about:blank"])
    try:
        target = None
        for _ in range(50):  # its first tab comes up a moment after Chrome answers
            target = next((t for t in chrome.call("Target.getTargets")["targetInfos"] if t["type"] == "page"), None)
            if target:
                break
            time.sleep(0.1)
        tid = target["targetId"] if target else chrome.call("Target.createTarget", url="about:blank")["targetId"]
        session = chrome.call("Target.attachToTarget", targetId=tid, flatten=True)["sessionId"]
        window = chrome.call("Browser.getWindowForTarget", targetId=tid)["windowId"]
        for domain in ("Page", "DOM", "Accessibility"):
            chrome.call(f"{domain}.enable", session=session)
        chrome.call("Browser.setDownloadBehavior", behavior="deny")  # nothing of a page's saved to this PC
    except Exception:
        chrome.close()
        raise
    _chrome[0] = chrome
    _page.update(session=session, target=tid, window=window)
    _shown[0] = False
    _put_away()
    _give_back(was)
    if not _closer:  # once a run: the closer when idle, and her browser closed with her
        _closer.append(threading.Thread(target=_close_when_idle, name="her-browser-idle", daemon=True))
        _closer[0].start()
        atexit.register(close)
    print("  her browser started")


def _ensure():
    """Her browser, started if it isn't running. Raises Trouble if it can't be."""
    with _lock:
        _last[0] = time.monotonic()
        if not running():
            try:
                _start()
            except Trouble:
                raise
            except Exception as exc:
                raise Trouble(f"my browser didn't start ({exc})") from exc
        return _chrome[0]


def start():
    """Her browser running, out of your way, for a job that asked for a browser. True once it is."""
    _ensure()
    return True


def call(method, timeout=CALL_WAIT, **params):
    """One DevTools command on her page. Trouble if her browser has stopped answering (its pipe gone)."""
    chrome = _ensure()
    try:
        return chrome.call(method, session=_page["session"], timeout=timeout, **params)
    except (OSError, EOFError) as exc:
        raise Trouble(f"my browser stopped answering ({exc})") from exc


def _browser_call(method, **params):
    return _ensure().call(method, **params)


def _screens():
    """(left, top, width, height) of all your screens together, in Windows' virtual screen."""
    m = win.user32.GetSystemMetrics
    return m(76), m(77), m(78), m(79)


def _away_spot():
    """Where her window sits while she works: just left of all your screens, where you never see it."""
    left, top, _, _ = _screens()
    return left - W - 200, top


def _give_back(hwnd):
    """The focus given back to your window hwnd if hers took it: off your screens, it would have your keys."""
    mine = _window_handle()
    if hwnd and hwnd != mine and mine is not None and win.front_window() == mine and win.window_exists(hwnd):
        win.bring_to_front(hwnd)


def _put_away():
    """Off the edge of your screens, and drawing at W x H: what she works in, out of your way, and the focus left
    where it was."""
    was = win.front_window()
    left, top = _away_spot()
    _browser_call("Browser.setWindowBounds", windowId=_page["window"], bounds={"windowState": "normal"})
    _browser_call("Browser.setWindowBounds", windowId=_page["window"],
                  bounds={"left": left, "top": top, "width": W, "height": H})
    call("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False)
    call("Emulation.setFocusEmulationEnabled", enabled=True)  # its page acts as if in front, though it isn't
    _give_back(was)


def _keep_away():
    """Puts her window back off your screens if it's come onto one (a screen plugged in where it sat) while you
    don't have it: checked at each look."""
    hwnd = _window_handle()
    if hwnd is None or _shown[0]:
        return
    box = win.window_rect(hwnd)
    with win._real_pixels():  # as window_rect gives it
        left, top, width, height = _screens()
    if box is not None and box[2] > left and box[0] < left + width and box[3] > top and box[1] < top + height:
        _put_away()


def window():
    """Its window's handle while it runs, else None: for the live picture of it on a job's card (jobview), which
    Windows draws though it's off your screens, at no cost to her."""
    return _window_handle() if running() else None


def _window_handle():
    """Its window's handle, by its own process, never your Chrome's: they're the same program."""
    import ctypes
    pid = _chrome[0].proc.pid if running() else None
    for hwnd, _path, _title in win.open_windows():
        owner = ctypes.c_ulong()
        win.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            return hwnd
    return None


def show(url=None):
    """Her browser in front of you, at url if given (a site to sign in to), at its own size. While it's shown her
    jobs in it wait (free), so your clicks and hers never mix. True once it's there."""
    with _lock:
        _ensure()
        if not _shown[0]:
            front = win.front_window()
            _yours[0] = front if front != _window_handle() else None
        _shown[0] = True
        if url:
            go(url)
        call("Emulation.clearDeviceMetricsOverride")
        left, top, width, height = _screens()
        _browser_call("Browser.setWindowBounds", windowId=_page["window"], bounds={"windowState": "normal"})
        _browser_call("Browser.setWindowBounds", windowId=_page["window"],
                      bounds={"left": left + 40, "top": top + 40, "width": min(W, width - 80),
                              "height": min(H, height - 80)})
        hwnd = _window_handle()
        if hwnd:
            win.bring_to_front(hwnd)
        return True


def hide():
    """Put away again, for her jobs to carry on in. False if it isn't running."""
    with _lock:
        if not running():
            _shown[0] = False
            return False
        _shown[0] = False
        remote_end()
        _last[0] = time.monotonic()
        _put_away()
        _give_back(_yours[0])
        _yours[0] = None
        return True


def close():
    """Closed, its logins kept in its profile. Her jobs in it open it again if they need it."""
    with _lock:
        chrome, _chrome[0] = _chrome[0], None
        _shown[0] = False
        _page.update(session=None, target=None, window=None)
    if chrome is not None:
        chrome.close()
        print("  her browser closed")


def keep_open(job_id):
    """A job working in it: it isn't closed for being idle while one is."""
    _holders.add(job_id)


def let_go(job_id):
    _holders.discard(job_id)


def idle_now():
    """True if it's running for nothing: not in front of you, no job working in it, and unused IDLE seconds."""
    with _lock:
        return running() and not _shown[0] and not _holders and time.monotonic() - _last[0] > IDLE


def _close_when_idle():
    while True:
        time.sleep(15)
        if idle_now():
            close()


def wait_till_free(stopped, deadline):
    """Waits while you have her browser in front (show): her job's clicks would land among yours. stopped() ends
    the wait at once; past deadline (time.time()) it's TimeoutError."""
    while shown():
        if stopped():
            return
        if time.time() >= deadline:
            raise TimeoutError("you had my browser the whole time")
        time.sleep(0.3)


# --------------------------------------------------------------------------- The page: where it is, going places
def _info():
    return _browser_call("Target.getTargetInfo", targetId=_page["target"])["targetInfo"]


def title():
    return _info().get("title") or "" if running() else ""


def url():
    return _info().get("url") or "" if running() else ""


def site():
    """The site its page is on, as winplatform.site_of has a browser's (None for a blank page)."""
    return win.site_of(url()) if running() else None


def _ready_state():
    try:
        return call("Runtime.evaluate", expression="document.readyState", returnByValue=True)["result"].get("value")
    except Exception:
        return None


def _settle(wait=LOAD_WAIT):
    """Waits for the page to load, up to wait seconds, then a moment for what its JavaScript draws."""
    end = time.monotonic() + wait
    time.sleep(0.2)
    while time.monotonic() < end and _ready_state() != "complete":
        time.sleep(0.2)
    time.sleep(0.4)


def public(address):
    """True if address is a public web site's, as OpenMuse's worker allows: http or https on their own ports, its
    name looked up and every address it has on the internet, never this PC, your home network or a reserved range."""
    from urllib.parse import urlsplit
    try:
        parts = urlsplit(str(address or "").strip())
        port = parts.port
    except ValueError:
        return False
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname or \
            (port not in (None, 80, 443) and not LOCAL_OK):
        return False
    found = None
    for attempt in range(2):  # a second look after a moment: on 31 October one lookup of zomato.com failed in a blip
        try:
            found = {a[4][0] for a in socket.getaddrinfo(parts.hostname, port or 443, proto=socket.IPPROTO_TCP)}
            break
        except OSError:
            if attempt == 0:
                time.sleep(1.0)
    if found is None:
        return None  # not found: a name only your home network knows is never let through on trust
    for a in found:
        ip = ipaddress.ip_address(a.split("%")[0])
        if LOCAL_OK and ip.is_loopback:
            continue
        if not ip.is_global or ip.is_multicast:
            return False
    return True


def go(address):
    """Her page at address: a public web site's only, never a file, this PC, your home network or a setting.
    RuntimeError if it can't be."""
    address = str(address or "").strip()
    if not re.match(r"https?://", address, re.I):
        raise RuntimeError("my browser only opens web addresses")
    ok = public(address)
    if ok is None:
        raise RuntimeError("I couldn't find that site")
    if not ok:
        raise RuntimeError("my browser only opens public sites, never this PC or your home network")
    got = call("Page.navigate", url=address)
    if got.get("errorText"):
        raise RuntimeError(f"that page didn't open ({got['errorText']})")
    _settle()
    return "website"


# --------------------------------------------------------------------------- The page's controls, as a window's
class Node:
    """One control on her page, by Chrome's own id for it (backendDOMNodeId), as a UI Automation element is one of a
    window's: what agent keeps in an item's "el" and hands back to press it."""
    __slots__ = ("id",)

    def __init__(self, node_id):
        self.id = int(node_id)

    def __eq__(self, other):
        return isinstance(other, Node) and other.id == self.id

    def __hash__(self):
        return hash(("node", self.id))

    def __repr__(self):
        return f"Node({self.id})"


def _prop(node, name):
    for p in node.get("properties") or ():
        if p.get("name") == name:
            return (p.get("value") or {}).get("value")
    return None


def _role(node):
    return ROLE_OF.get(str((node.get("role") or {}).get("value") or ""), "")


def _name(node):
    return win.clean_name((node.get("name") or {}).get("value"))


def _layout():
    """{backend id: (left, top, right, bottom) on the page as it's scrolled now, and its DOM attributes}, from one
    DOM snapshot of the main frame: each control's place and its id, type and so on, in one call."""
    snap = call("DOMSnapshot.captureSnapshot", computedStyles=[])
    # its boxes come in the screen's pixels (1.5 a page pixel at Windows' 150%, 31 October), the page's are wanted
    sizes = call("Page.getLayoutMetrics")
    page_w = (sizes.get("cssLayoutViewport") or {}).get("clientWidth") or 0
    screen_w = (sizes.get("layoutViewport") or {}).get("clientWidth") or 0
    k = page_w / screen_w if page_w and screen_w else 1.0
    strings, out = snap.get("strings") or [], {}
    if not snap.get("documents"):
        return out
    doc = snap["documents"][0]
    nodes, layout = doc.get("nodes") or {}, doc.get("layout") or {}
    backend = nodes.get("backendNodeId") or []
    attrs = nodes.get("attributes") or []
    clickable = set((nodes.get("isClickable") or {}).get("index") or [])  # what Chrome says responds to a click
    sx, sy = doc.get("scrollOffsetX") or 0, doc.get("scrollOffsetY") or 0
    for i, box in zip(layout.get("nodeIndex") or [], layout.get("bounds") or []):
        if i >= len(backend) or len(box) < 4:
            continue
        pairs = attrs[i] if i < len(attrs) else []
        named = {strings[pairs[k]].lower(): strings[pairs[k + 1]] for k in range(0, len(pairs) - 1, 2)
                 if pairs[k] < len(strings) and pairs[k + 1] < len(strings)}
        x, y, w, h = (v * k for v in box[:4])
        x, y = x - sx * k, y - sy * k
        out[backend[i]] = {"rect": (round(x), round(y), round(x + w), round(y + h)), "attrs": named,
                           "click": i in clickable}
    return out


def _tree():
    return call("Accessibility.getFullAXTree").get("nodes") or []


def _password(attrs):
    return str((attrs or {}).get("type") or "").lower() == "password"


# What a site may build a control from instead of a button or a link: a block Chrome says is clicked on (DOMSnapshot's
# isClickable), offered as a button named by the text in it (_controls)
PLAIN = {"generic", "heading", "image", "img", "paragraph", "group", "article", "figure", "cell", "row", "section",
         "region", "LabelText", "none", "presentation"}


def _inside(a, b):
    """True if box a is inside box b."""
    return a[0] >= b[0] and a[1] >= b[1] and a[2] <= b[2] and a[3] <= b[3]


def _text_under(n, by_id, most=60):
    """What a plain block says: the text and the pictures' names in it, in reading order, up to most characters."""
    words, todo, looked = [], list(n.get("childIds") or []), 0
    while todo and looked < 150 and sum(len(w) + 1 for w in words) < most:
        node = by_id.get(todo.pop(0))
        looked += 1
        if node is None:
            continue
        if str((node.get("role") or {}).get("value") or "") in ("StaticText", "image", "img"):
            if not node.get("ignored") and _name(node):
                words.append(_name(node))
            continue
        todo[:0] = list(node.get("childIds") or [])
    return win.clean_name(" ".join(words))[:most]


def _rank(n, by_id, rect):
    """0 in an open dialog, 1 on the screen, 2 scrolled away."""
    left, top, right, bottom = rect
    rank = 1 if left < W and right > 0 and top < H and bottom > 0 else 2
    up, steps = n.get("parentId"), 0
    while up is not None and steps < 40:
        parent = by_id.get(up)
        if parent is None:
            break
        if str((parent.get("role") or {}).get("value") or "") in DIALOGS:
            return 0
        up, steps = parent.get("parentId"), steps + 1
    return rank


def _controls(nodes, places):
    """Every shown, enabled control of the page, in its order: (item without an id, AX node, rank, its whole name),
    rank 0 in an open dialog, 1 on the screen, 2 scrolled away. A control by its role (ROLE_OF), and a block a site
    built one from that Chrome says is clicked on: on 31 October Zomato's delivery page had 124 of those (restaurant
    cards, its own buttons) to 76 with a control's role, and they were offered to neither her jobs nor your phone.
    Each is a button named by the text in it: the outermost of those nested, never one round or in a real control
    (that's offered itself) or as big as half the page, and never one with no words."""
    by_id = {n.get("nodeId"): n for n in nodes}
    found = []
    for i, n in enumerate(nodes):
        role = _role(n)
        if not role or n.get("ignored") or _prop(n, "disabled"):
            continue
        place = places.get(n.get("backendDOMNodeId"))
        if place is None:
            continue
        left, top, right, bottom = place["rect"]
        if right <= left or bottom <= top:
            continue
        name = _name(n)
        if not name and role != "edit":
            continue
        password = role == "edit" and _password(place["attrs"])
        value = None if password else (n.get("value") or {}).get("value")
        state = _prop(n, "checked")
        state = _prop(n, "pressed") if state is None else state
        state = {"true": "on", True: "on", "false": "off", False: "off"}.get(state)
        found.append((i, {"role": role, "name": name[:win.SNAP_NAME],
                          "value": " ".join(str(value).split()) if value not in (None, "") else None,
                          "state": state, "password": password, "focus": bool(_prop(n, "focused")),
                          "aid": str(place["attrs"].get("id") or ""), "rect": place["rect"],
                          "el": Node(n["backendDOMNodeId"])}, n, _rank(n, by_id, place["rect"]), name))
    real, kept = [f[1]["rect"] for f in found], []
    for i, n in enumerate(nodes):
        if _role(n) or n.get("ignored") or _prop(n, "disabled") or \
                str((n.get("role") or {}).get("value") or "") not in PLAIN:
            continue
        place = places.get(n.get("backendDOMNodeId"))
        if place is None or not place.get("click"):
            continue
        rect = place["rect"]
        if rect[2] - rect[0] < 4 or rect[3] - rect[1] < 4 or (rect[2] - rect[0]) * (rect[3] - rect[1]) > W * H // 2:
            continue
        if any(_inside(r, rect) or _inside(rect, r) for r in real) or any(_inside(rect, r) for r in kept):
            continue
        name = _name(n) or _text_under(n, by_id)
        if not name:
            continue
        kept.append(rect)
        found.append((i, {"role": "button", "name": name[:win.SNAP_NAME], "value": None, "state": None,
                          "password": False, "focus": bool(_prop(n, "focused")),
                          "aid": str(place["attrs"].get("id") or ""), "rect": rect,
                          "el": Node(n["backendDOMNodeId"])}, n, _rank(n, by_id, rect), name))
    found.sort(key=lambda f: f[0])  # in the page's own order
    out, twins = [], set()
    for _, item, n, rank, name in found:  # one of each: Zomato's breadcrumb links were each read twice, in one place
        twin = (item["role"], name, item["rect"])
        if twin not in twins:
            twins.add(twin)
            out.append((item, n, rank, name))
    return out


def ui_snapshot(hwnd=None, most=60):
    """Her page as winplatform.ui_snapshot gives a window: {"hwnd", "title", "exe", "site", "focus", "total",
    "focused", "cut", "url", "items"}, the controls in an open dialog first, then those on the screen, then the
    rest, list items capped, names cut. A password's value is never read. None if Chrome couldn't say."""
    try:
        _keep_away()
        found = _controls(_tree(), _layout())
    except Exception as exc:
        print(f"  her browser: {exc!r}")
        return None
    ordered = [c for c, _, _, _ in sorted(found, key=lambda c: c[2])]
    items, lists = [], 0
    for it in ordered:
        if it["role"] in LISTED:
            lists += 1
            if lists > win.SNAP_LISTS:
                continue
        if len(items) < most:
            items.append({**it, "id": len(items) + 1})
    focused = next(((c["role"], c["name"], c["value"]) for c, _, _, _ in found if c["focus"]), None)
    return {"hwnd": TAB, "title": title(), "exe": exe(), "site": site(), "url": url(),
            "focus": next((it["id"] for it in items if it["focus"]), None), "total": len(found),
            "focused": focused, "cut": len(items) < len(found), "items": items}


def _node(el):
    """The AX node for a Node now, LookupError once it's gone from the page."""
    try:
        nodes = call("Accessibility.getPartialAXTree", backendNodeId=el.id, fetchRelatives=False).get("nodes") or []
    except RuntimeError as exc:
        raise LookupError(f"it's gone from the page ({exc})")
    mine = next((n for n in nodes if n.get("backendDOMNodeId") == el.id), nodes[0] if nodes else None)
    if mine is None:
        raise LookupError("it's gone from the page")
    return mine


def _attrs(el):
    try:
        node = call("DOM.describeNode", backendNodeId=el.id).get("node") or {}
    except RuntimeError:
        return {}
    pairs = node.get("attributes") or []
    return {str(pairs[k]).lower(): pairs[k + 1] for k in range(0, len(pairs) - 1, 2)}


def ui_info(el, plain=True):
    """What a control is, as winplatform.ui_info: {"name", "role", "aid", "password", "el"}. plain: a block with no
    control's role is a button named by the text in it, as _controls offered it."""
    node, attrs = _node(el), _attrs(el)
    role, name = _role(node), _name(node)
    if not role and plain:
        nodes = _tree()
        mine = next((x for x in nodes if x.get("backendDOMNodeId") == el.id), node)
        role, name = "button", name or _text_under(mine, {x.get("nodeId"): x for x in nodes})
    return {"name": name, "role": role, "aid": str(attrs.get("id") or ""),
            "password": role == "edit" and _password(attrs), "el": el}


def ui_value(el):
    """What's typed in it, or None: a password's is never read."""
    try:
        node = _node(el)
        if _password(_attrs(el)):
            return None
        value = (node.get("value") or {}).get("value")
        return None if value is None else " ".join(str(value).split())
    except Exception:
        return None


def ui_toggle(el):
    """"on" or "off" for a switch or a tick box, else None."""
    try:
        node = _node(el)
    except Exception:
        return None
    state = _prop(node, "checked")
    state = _prop(node, "pressed") if state is None else state
    return {"true": "on", True: "on", "false": "off", False: "off"}.get(state)


def ui_focus_free(el, text=None, state=None):
    """Always: nothing in her browser takes your screen."""
    return True


def _object(el):
    return call("DOM.resolveNode", backendNodeId=el.id)["object"]["objectId"]


def _on(el, function, *args):
    """function, a JavaScript function's source, run with this as the control: what it gives back."""
    got = call("Runtime.callFunctionOn", objectId=_object(el), functionDeclaration=function,
               arguments=[{"value": a} for a in args], returnByValue=True)
    return (got.get("result") or {}).get("value")


def ui_dialog_text(el, most=300):
    """The words of the dialog it's in, so an OK is judged by what it says yes to; "" if it isn't in one."""
    try:
        return str(_on(el, "function(most){const d=this.closest('dialog,[role=dialog],[role=alertdialog]');"
                           "return d?(d.innerText||'').replace(/\\s+/g,' ').trim().slice(0,most):''}", most) or "")
    except Exception:
        return ""


def _find(name, role, aid):
    """The shown, enabled controls (_controls) of this role by their id, else by their whole name."""
    want = win.clean_name(name).lower()
    found = _controls(_tree(), _layout())

    def hits(by_aid):
        return [c["el"] for c, _, _, whole in found if (not role or c["role"] == role) and
                (str(c["aid"]) == str(aid) if by_aid else whole.lower() == want)]
    out = hits(True) if aid else hits(False)
    if not out and aid and want:  # its id changed with the site's version: then by its name
        out = hits(False)
    return out


def find_ui(name=None, role=None, aid=None, hwnd=None, wait=0.0, unique=True, strict=False):
    """As winplatform.find_ui, on her page: the one shown, enabled control of this role by its id, else by its name,
    looked for again for up to wait seconds; None if there's none, or two with unique."""
    if not win.clean_name(name) and not aid:
        return None
    end = time.monotonic() + wait
    while True:
        try:
            hits = _find(name, role, aid)
        except Exception as exc:
            if strict:
                raise LookupError(f"couldn't read my browser's page ({exc})")
            hits = []
        if hits and (len(hits) == 1 or not unique):
            return hits[0]
        if len(hits) > 1 or time.monotonic() >= end:
            return None
        time.sleep(0.3)


def find_all_ui(name=None, role=None, aid=None, hwnd=None):
    if not win.clean_name(name) and not aid:
        return []
    try:
        return _find(name, role, aid)
    except Exception as exc:
        print(f"  her browser: {exc!r}")
        return []


def ui_fields(el=None):
    """What a send would send, as winplatform.ui_fields: [(role, name, value)] of every shown control in the dialog
    el is in, else on the page. A password's value is never read. None if the page couldn't be read."""
    try:
        nodes, places = _tree(), _layout()
    except Exception:
        return None
    by_id = {n.get("nodeId"): n for n in nodes}
    scope = None
    if el is not None:
        mine = next((n for n in nodes if n.get("backendDOMNodeId") == el.id), None)
        up, steps = (mine or {}).get("nodeId"), 0
        while up is not None and steps < 40:
            n = by_id.get(up)
            if n is None:
                break
            if str((n.get("role") or {}).get("value") or "") in DIALOGS:
                scope = n["nodeId"]
                break
            up, steps = n.get("parentId"), steps + 1
    out = []
    for c, n, _, _ in _controls(nodes, places):
        if scope is not None:
            up, inside, steps = n.get("parentId"), False, 0
            while up is not None and steps < 60:
                if up == scope:
                    inside = True
                    break
                up, steps = (by_id.get(up) or {}).get("parentId"), steps + 1
            if not inside:
                continue
        out.append((c["role"], c["name"], None if c["password"] else c["value"]))
    return out


def ui_focused():
    """The control the keyboard's in on her page, as winplatform.ui_focused, or None: nothing but the page itself."""
    try:
        got = call("Runtime.evaluate", expression="document.activeElement")
        obj = (got.get("result") or {}).get("objectId")
        if not obj:
            return None
        node = call("DOM.describeNode", objectId=obj).get("node") or {}
        if str(node.get("nodeName") or "").upper() in ("BODY", "HTML", "IFRAME"):
            return None
        info = ui_info(Node(node["backendNodeId"]), plain=False)  # a box, or a control with its own role
        return info if info["role"] else None
    except Exception:
        return None


def ui_at(x, y):
    """The control at a point on her page (in its CSS pixels, as its screenshots are), or the nearest one round it
    that can be pressed, with "climbed" as winplatform.ui_at has it. None if there's nothing there."""
    try:
        got = call("DOM.getNodeForLocation", x=int(x), y=int(y), includeUserAgentShadowDOM=False)
        nodes = call("Accessibility.getPartialAXTree", backendNodeId=got["backendNodeId"],
                     fetchRelatives=True).get("nodes") or []
    except Exception:
        return None
    by_id = {n.get("nodeId"): n for n in nodes}
    first = next((n for n in nodes if n.get("backendDOMNodeId") == got["backendNodeId"]), None)
    node, depth = first, 0
    while node is not None and depth < 8:
        if _role(node) and node.get("backendDOMNodeId"):
            return {**ui_info(Node(node["backendDOMNodeId"])), "climbed": bool(depth)}
        node, depth = by_id.get(node.get("parentId")), depth + 1
    if first is None or not first.get("backendDOMNodeId"):
        return None
    return {"name": _name(first), "role": "", "aid": "", "password": False, "el": Node(first["backendDOMNodeId"]),
            "climbed": False}


# --------------------------------------------------------------------------- Doing things in it
def _mouse(x, y, button="left", count=1):
    call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
    for n in range(1, count + 1):
        for kind in ("mousePressed", "mouseReleased"):
            call("Input.dispatchMouseEvent", type=kind, x=x, y=y, button=button, clickCount=n)


def click(x, y, button="left", double=False):
    """A click at a point on her page, in its CSS pixels, as you'd click it."""
    _mouse(float(x), float(y), "right" if button == "right" else "left", 2 if double else 1)
    time.sleep(0.3)
    return "clicked"


def _click_node(el):
    """A control clicked in its middle, scrolled into view first; one with no place on the page (hidden behind a
    menu) by its own click() instead."""
    try:
        call("DOM.scrollIntoViewIfNeeded", backendNodeId=el.id)
        quads = call("DOM.getContentQuads", backendNodeId=el.id).get("quads") or []
    except RuntimeError:
        quads = []
    if quads and len(quads[0]) >= 8:
        q = quads[0]
        _mouse(sum(q[0::2]) / 4, sum(q[1::2]) / 4)
        time.sleep(0.3)
        return "clicked"
    _on(el, "function(){this.click()}")
    time.sleep(0.3)
    return "invoked"


def _focus(el, at_end=False):
    """The keyboard put in a box, its cursor at the end of what's in it if at_end and it wasn't in it already."""
    was = _on(el, "function(){return document.activeElement===this||this.contains(document.activeElement)}")
    call("DOM.focus", backendNodeId=el.id)
    if at_end and not was:
        _on(el, "function(){if(typeof this.setSelectionRange==='function'&&this.value!==undefined){"
                "const n=this.value.length;this.setSelectionRange(n,n)}else if(this.isContentEditable){"
                "const r=document.createRange();r.selectNodeContents(this);r.collapse(false);"
                "const s=getSelection();s.removeAllRanges();s.addRange(r)}}")


def ui_act(el, text=None, state=None, caret=False, focus_free=False):
    """As winplatform.ui_act, on her page: a switch set only if it isn't already ("already", "toggled"), text put
    in place of what's in a box ("set") or typed at its cursor (caret, "typed"), else a click ("clicked")."""
    if state in ("on", "off"):
        now = ui_toggle(el)
        if now is None:
            raise RuntimeError("That isn't something I can switch on or off")
        if now == state:
            return "already"
        _click_node(el)
        return "toggled"
    if text is not None:
        _focus(el, at_end=caret)
        if not caret:
            _on(el, "function(){if(typeof this.select==='function'&&this.value!==undefined){this.select()}"
                    "else if(this.isContentEditable){const r=document.createRange();r.selectNodeContents(this);"
                    "const s=getSelection();s.removeAllRanges();s.addRange(r)}}")
        call("Input.insertText", text=str(text))
        return "typed" if caret else "set"
    return _click_node(el)


def _key(name):
    name = KEY_ALIASES.get(name, name)
    if name in KEYS:
        return KEYS[name], None
    if re.fullmatch(r"f([1-9]|1[0-2])", name):
        n = int(name[1:])
        return (name.upper(), name.upper(), 111 + n), None
    if len(name) == 1 and name.isalnum():
        code = f"Key{name.upper()}" if name.isalpha() else f"Digit{name}"
        return (name, code, ord(name.upper())), name
    raise RuntimeError(f"There's no {name or 'such'} key")


def press_keys(combo):
    """A shortcut pressed on her page, by the names siri.press_keys takes ("ctrl+a", "shift+tab", "enter").
    Back, forward and reload are done as the browser would; the ones for its own address bar, tabs and windows
    aren't keys here (NOT_HERE), nor is the Windows key."""
    parts = [p.strip() for p in re.split(r"\s*\+\s*", str(combo or "").lower().strip()) if p.strip()]
    if not parts:
        raise RuntimeError("There's no such key")
    mods = 0
    for p in parts[:-1]:
        if p in ("win", "windows", "cmd", "super", "meta", "start"):
            raise RuntimeError("I don't press the Windows key")
        if p not in MODIFIERS:
            raise RuntimeError(f"There's no {p} key")
        mods |= MODIFIERS[p]
    last = parts[-1]
    if last in ("win", "windows", "cmd", "super", "meta", "start"):
        raise RuntimeError("I don't press the Windows key")
    if (mods == 1 and last in ("left", "right")) or (mods == 0 and last in ("browserback", "browserforward")):
        history = call("Page.getNavigationHistory")
        at = history["currentIndex"] + (-1 if last in ("left", "browserback") else 1)
        if 0 <= at < len(history["entries"]):
            call("Page.navigateToHistoryEntry", entryId=history["entries"][at]["id"])
            _settle()
        return "keys"
    if (mods == 0 and last == "f5") or (mods == 2 and last == "r"):
        call("Page.reload")
        _settle()
        return "keys"
    if mods & 2 and last in ("l", "t", "n", "w", "tab", "f4") or (mods == 1 and last == "f4"):
        raise RuntimeError(NOT_HERE)
    (key, code, vk), char = _key(last)
    event = {"key": key, "code": code, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk, "modifiers": mods}
    if mods == 2 and last in EDITING:
        event["commands"] = [EDITING[last]]
    text = char if char and not mods & 3 else " " if last == "space" and not mods & 3 else \
        "\r" if last == "enter" and not mods & 3 else None
    call("Input.dispatchKeyEvent", type="keyDown" if text else "rawKeyDown", **({"text": text} if text else {}),
         **event)
    call("Input.dispatchKeyEvent", type="keyUp", **event)
    time.sleep(0.2)
    return "keys"


def scroll(notches):
    """The page scrolled as a mouse wheel would: up for a positive notches, down for a negative."""
    call("Input.dispatchMouseEvent", type="mouseWheel", x=W / 2, y=H / 2, deltaX=0, deltaY=-100 * int(notches))
    time.sleep(0.3)
    return "scroll"


def shot():
    """A screenshot of her page as agent sends a window's (vision.Shot), its pixels the page's own."""
    import base64
    import cv2
    import numpy as np
    import vision
    data = base64.b64decode(call("Page.captureScreenshot", format="png")["data"])
    bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise RuntimeError("my browser's page couldn't be seen")
    rgb = bgr[:, :, ::-1].copy()
    return vision.Shot(rgb, (0, 0, rgb.shape[1], rgb.shape[0]))


# --------------------------------------------------------------------------- agent's window, answered from here
def window_of(hwnd):
    return (TAB, exe(), title()) if running() else (None, "", "")


def window_site(hwnd, exe_name=None):
    return site()


def window_exists(hwnd):
    return running()


def bring_to_front(hwnd):
    """Never: she works in it out of sight, and you bring it up yourself (show)."""
    return None


def owner_of(hwnd):
    return TAB


def root_at(x, y):
    return TAB


def window_at(x, y):
    return program()


def front_window():
    return TAB if running() else None


def foreground():
    return window_of(TAB)


def browser_site():
    return site()


ROUTED = {  # what's answered from here, and when: an element of her page, her page's handle, or a run working in it
    "el": {"ui_info": ui_info, "ui_act": ui_act, "ui_value": ui_value, "ui_toggle": ui_toggle,
           "ui_focus_free": ui_focus_free, "ui_dialog_text": ui_dialog_text},
    "hwnd": {"window_of": window_of, "window_site": window_site, "window_exists": window_exists,
             "bring_to_front": bring_to_front, "ui_snapshot": ui_snapshot, "owner_of": owner_of},
    "found": {"find_ui": find_ui, "find_all_ui": find_all_ui},
    "run": {"front_window": front_window, "foreground": foreground, "ui_focused": ui_focused,
            "browser_site": browser_site, "ui_at": ui_at, "window_at": window_at, "root_at": root_at,
            "click": click, "scroll": scroll, "ui_fields": ui_fields},
}


class Surface:
    """winplatform as agent.py reaches it (its win): the same in every way, except for what's about her page, which
    is answered from here. A call is hers when it's given an element of her page (Node) or her page's handle (TAB),
    or, for those about the window in front, when the run asking works in her browser (on()). Whatever isn't hers
    goes to winplatform as it is when it's called, so a test that patches winplatform patches this too."""

    def __init__(self, real, on):
        self._real, self._on = real, on

    def __getattr__(self, name):
        value = getattr(self._real, name)
        if not callable(value) or not any(name in group for group in ROUTED.values()):
            return value
        real, on = self._real, self._on

        def either(*args, **kw):
            if _mine(name, args, kw, on):
                return next(group[name] for group in ROUTED.values() if name in group)(*args, **kw)
            return getattr(real, name)(*args, **kw)
        either.__name__ = name
        return either


def _mine(name, args, kw, on):
    if name in ROUTED["el"]:
        return bool(args) and isinstance(args[0], Node)
    if name in ROUTED["hwnd"]:
        return bool(args) and args[0] == TAB
    if name in ROUTED["found"]:
        return (kw.get("hwnd") if "hwnd" in kw else args[3] if len(args) > 3 else None) == TAB
    if name == "ui_fields" and args and args[0] is not None:
        return isinstance(args[0], Node)
    return bool(on())


# --------------------------------------------------------------------------- From your phone
# OpenMuse's Take control, tap to click, on Telegram (31 October 2026, the owner's ask): a picture of her page with each
# control on the screen numbered, a button for each number, and Type, scrolling, Back, a new picture and Done. One
# message, changed in place as you tap. Only your Telegram account's taps reach it (telegram_bot._tap), her jobs in it
# wait while you have it (shown), and a password is never taken over Telegram: you sign in at the PC. A small JPEG
# made only when you tap, nothing kept running for it
REMOTE_IDLE = 300  # seconds after your last tap that her jobs wait for you, then carry on
REMOTE_MOST = 16  # controls with a button of their own: two to a row, as Telegram shows them on a phone
_remote = {"chat": None, "message": None, "token": "", "nodes": {}, "typing": False, "at": 0.0}
NO_PASSWORDS = "I won't take a password over Telegram. Sign in at the PC: say show me your browser there."


def remote_on():
    """True while you're using her browser from your phone: a tap in the last REMOTE_IDLE seconds, and not Done."""
    return _remote["chat"] is not None and time.monotonic() - _remote["at"] < REMOTE_IDLE


def remote_start(chat):
    _remote.update(chat=chat, message=None, typing=False, at=time.monotonic())


def remote_end():
    _remote.update(chat=None, message=None, typing=False, nodes={})


def remote_wants_text():
    """True if your next message on the phone is text for her browser (after Type)."""
    return _remote["typing"] and remote_on()


# An icon's own name in a control's ("location-fill", "chevron-down"), or a word for a picture, left out of a button's
# label on your phone; a control named by nothing else goes after the ones with words (remote_view)
ICON_WORD = re.compile(r"[a-z]+(?:-[a-z0-9]+)+|illustration|icon|image|img|logo|svg", re.I)


def _label(name):
    """A control's name as a button on your phone: "illustration Dining Out" is Dining Out, "filter Filters" Filters,
    "Cuisines chevron-down" Cuisines. "" if it's only an icon's."""
    words = [w for w in str(name).split() if not ICON_WORD.fullmatch(w)]
    words = [w for i, w in enumerate(words) if not (i + 1 < len(words) and
                                                     w.lower().rstrip("s") == words[i + 1].lower().rstrip("s"))]
    return " ".join(words)


def remote_view():
    """Her page for your phone: (a JPEG of it, a caption, rows of buttons as (label, data)): a number drawn on each of
    the first REMOTE_MOST controls on the screen, an open dialog's first, then as you'd read them, top to bottom and
    left to right (a page's own order put Zomato's search box at 17, under its links), those named by words before
    those that are only an icon, a button for each, then Type, scrolling, Back, a new picture and Done. A button's
    data carries this picture's token, so a tap on an older picture clicks nothing."""
    import base64
    import cv2
    import numpy as np
    _keep_away()
    found = [(it, rank) for it, _, rank, _ in _controls(_tree(), _layout()) if rank < 2]
    picture = cv2.imdecode(np.frombuffer(base64.b64decode(call("Page.captureScreenshot", format="png")["data"]),
                                         np.uint8), cv2.IMREAD_COLOR)
    token, nodes, buttons = os.urandom(3).hex(), {}, []
    found.sort(key=lambda f: (f[1], not _label(f[0]["name"]), max(0, f[0]["rect"][1]) // 24, f[0]["rect"][0]))
    seen = [it for it, _ in found if it["name"] and not it["password"] and it["rect"][1] < H and it["rect"][3] > 0]
    for n, it in enumerate(seen[:REMOTE_MOST], 1):
        nodes[str(n)] = it["el"]
        label = _label(it["name"]) or it["name"]
        buttons.append((f"{n}. {label[:26]}" + (" (box)" if it["role"] == "edit" else ""), f"b:{token}:c{n}"))
        if picture is not None:  # its number on the picture, on its top left corner, clear of most of its label
            x, y = max(11, it["rect"][0]), max(11, it["rect"][1])
            cv2.circle(picture, (x, y), 11, (36, 99, 235), -1)
            cv2.putText(picture, str(n), (x - (5 if n < 10 else 10), y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (255, 255, 255), 1, cv2.LINE_AA)
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([("Type", f"b:{token}:t"), ("Scroll down", f"b:{token}:sd"), ("Scroll up", f"b:{token}:su")])
    rows.append([("Back", f"b:{token}:bk"), ("New picture", f"b:{token}:r"), ("Done", f"b:{token}:x")])
    jpeg = cv2.imencode(".jpg", picture, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes() if picture is not None else b""
    _remote.update(token=token, nodes=nodes, at=time.monotonic())
    where = site()
    caption = (f"{title() or 'My browser'}{' · ' + where if where else ''}. Tap a number to click it. To type, tap the "
               f"box, then Type, then send me the text.")
    return jpeg, caption, rows


def remote_tap(data):
    """A tap on one of remote_view's buttons: ("view", line) for a new picture, with line said first if any, or
    ("say", line) for words alone."""
    _, token, action = (str(data).split(":") + ["", ""])[:3]
    if not running():
        remote_end()
        return "say", "My browser's closed. Say show me your browser to open it."
    if token != _remote["token"]:
        return "view", "That was an older picture, so I've not clicked anything. Here's the page now."
    _remote["at"] = time.monotonic()
    if action == "x":
        remote_end()
        return "say", "Done. I'll carry on with my jobs in it."
    if action in ("sd", "su"):
        scroll(-5 if action == "sd" else 5)
    elif action == "bk":
        press_keys("alt+left")
    elif action == "t":
        box = ui_focused()
        if box is None or box["role"] not in ("edit", "combobox"):
            return "say", "Tap a box first, then Type."
        if box["password"]:
            return "say", NO_PASSWORDS
        _remote["typing"] = True
        return "say", f"Send me what to type into {box['name'] or 'that box'}."
    elif action.startswith("c") and action[1:] in _remote["nodes"]:
        ui_act(_remote["nodes"][action[1:]])
        _settle(3)
    return "view", ""


def remote_type(text):
    """What you sent after Type, typed where the box you tapped has its cursor. Never into a password box."""
    _remote["typing"] = False
    box = ui_focused()
    if box is None:
        return "say", "The box isn't picked any more. Tap it again, then Type."
    if box["password"]:
        return "say", NO_PASSWORDS
    ui_act(box["el"], str(text), caret=True)
    _remote["at"] = time.monotonic()
    return "view", ""


def to_phone(chat, line=""):
    """Her page sent to your phone (remote_view), with line said first if any; else in place of the last picture."""
    send, control = host.PHONE.get("send"), host.PHONE.get("control")
    if line and send:
        send(chat, line)
        _remote["message"] = None  # the picture under the words, not above them
    picture, caption, rows = remote_view()
    if control is not None and picture:
        _remote["message"] = control(chat, picture, caption, rows, _remote["message"]) or _remote["message"]


def phone_tap(data, chat):
    """A tap on your phone (telegram_bot's on_browser), on a thread of its own: done, and answered there."""
    try:
        kind, line = remote_tap(data)
        if kind == "view":
            to_phone(chat, line)
        elif line and host.PHONE.get("send"):
            host.PHONE["send"](chat, line)
    except Exception as exc:
        print(f"  her browser, from your phone: {exc!r}")
        if host.PHONE.get("send"):
            host.PHONE["send"](chat, "That didn't work in my browser.")


def phone_text(text, chat):
    """The text you sent after Type, typed into her page, and a new picture back."""
    try:
        kind, line = remote_type(text)
        if kind == "view":
            to_phone(chat, line)
        elif line and host.PHONE.get("send"):
            host.PHONE["send"](chat, line)
    except Exception as exc:
        print(f"  her browser, from your phone: {exc!r}")


# --------------------------------------------------------------------------- Said to her
_YOUR = r"(?:your|ur|her|harry'?s)(?: own)? browser"
SHOW = re.compile(rf"(?:(?:show|open|bring up|pull up|give)(?: me)? {_YOUR}|take control(?: of {_YOUR})?|let me "
                  rf"(?:sign|log) in(?: (?:to|in|on) {_YOUR})?)")
SIGN_IN = re.compile(rf"(?:let me |i(?:'ll| will| want to| wanna) )?(?:sign|log)(?: me)? ?in(?:to| to| on)? (?P<site>.+?) "
                     rf"(?:in|on|with|using) {_YOUR}|open (?P<open>.+?) (?:in|on) {_YOUR}")
HIDE = re.compile(rf"(?:hide|minimi[sz]e|put away|put back)(?: {_YOUR})?|(?:i'?m |i am )?done(?: signing in| logging"
                  rf" in)?(?:,? (?:you can )?(?:hide it|carry on|go ahead))?|carry on(?: in {_YOUR})?")
CLOSE = re.compile(rf"(?:close|quit|shut) {_YOUR}")
TURN_ON = re.compile(rf"(?:use|turn on|switch on) {_YOUR}")
TURN_OFF = re.compile(rf"(?:(?:don'?t|do not|stop) us(?:e|ing)|turn off|switch off) {_YOUR}")


def _address(said):
    """A web address for a site you named: one she knows by name (siri.SITES), or one said as an address."""
    said = str(said or "").strip().lower().removeprefix("my ").strip()
    if host is not None:
        known = host.SITES.get(host.key_of(said)) if hasattr(host, "key_of") else None
        if known:
            return known[1], known[0]
    if re.fullmatch(r"(?:https?://)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/\S*)?", said):
        return (said if said.startswith("http") else f"https://{said}"), said
    return None, said


def _plan(say):
    return {"steps": [], "say": say}


def quick(words, plain, gate=False):
    """A plan for what's said about her browser, or None: show it to sign in (at a site), hide it, close it, use it
    or not. Without her name only shown and hidden, and only when the words name her browser: on 31 October "show me
    your browser" said so went to the model, which opened your own Chrome instead."""
    t = plain(str(words or ""))
    if gate == "cold" and not (re.search(rf"\b{_YOUR}\b", t) and (SHOW.fullmatch(t) or SIGN_IN.fullmatch(t) or
                                                                  HIDE.fullmatch(t))):
        return None
    if TURN_OFF.fullmatch(t):
        settings.put("own_browser", False)
        close()
        return _plan("Okay, I won't use my own browser: jobs on websites go on your screen again.")
    if TURN_ON.fullmatch(t):
        settings.put("own_browser", True)
        return _plan("Okay, I'll do jobs on websites in my own browser, out of your way."
                     if program() else "I'd need Chrome or Edge on this PC for that.")
    if CLOSE.fullmatch(t):
        close()
        return _plan("I've closed my browser. Your sign-ins in it are kept.")
    m = SIGN_IN.fullmatch(t)
    if m or SHOW.fullmatch(t):
        if not program():
            return _plan("I'd need Chrome or Edge on this PC for my own browser.")
        address, name = _address((m["site"] or m["open"]) if m else "")
        if m and address is None:
            return _plan(f"I don't know where {name} is. Say its address, like sign in to example.com in your browser.")
        chat = host.PHONE_CHAT.get() if host is not None and host.origin() == "phone" else None
        if chat is not None:  # asked from your phone: her page comes to it, to tap (remote_view)
            try:
                start()
                if address:
                    go(address)
                remote_start(chat)
                to_phone(chat)
            except Exception as exc:
                print(f"  her browser: {exc!r}")
                return _plan("My browser wouldn't open.")
            return _plan("Here's my browser. Tap a number to click it; my jobs in it wait till you tap Done.")
        try:
            show(address)
        except Exception as exc:
            print(f"  her browser: {exc!r}")
            return _plan("My browser wouldn't open.")
        if m and m["site"]:
            return _plan(f"Here's my browser at {name}. Sign in, then say hide your browser. I'll stay signed in.")
        return _plan("Here's my browser. Sign in to anything you'd like me to use, then say hide your browser. "
                     "I'll wait while you have it.")
    if HIDE.fullmatch(t) and shown():
        hide()
        return _plan("Okay, it's put away. I'll carry on in it in the background.")
    return None


def prompt_line():
    """What a job working in her browser is told, after the agent prompt."""
    return ("You're working in your own browser: a Chrome only you use, signed in to the sites the user signed in to "
            "there. Use website for an address; there's no address bar, tab strip or other app in it. Keys for the "
            "page only. A sign-in page, a code or a 'verify you're human' check: no steps, done false, and say what's "
            "in the way, and that they can sign you in by saying 'show me your browser'.")
