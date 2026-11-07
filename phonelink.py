"""Your phone on the same Wi-Fi (7 November 2026, the owner's ask, after NotchPixel's "Files to your phone" and its
"PC Deck"): a small web server of her own, on this PC's address on the Wi-Fi only, at a random port and a random key
in its address, which the island shows as a QR code (qr.py) for the phone's camera. No app on the phone and no account.

Files: the shelf's files (island Shelf, To phone) for the phone to download, only while their code is on the island
and FILES_FOR seconds at most. Deck: the phone as a trackpad, a music remote, a few keys for slides and videos and
your dock's pinned apps, in its browser. It's off till you turn it on in the island's Deck tab, each phone is allowed
on the PC first (the island asks), it goes off DECK_IDLE seconds after the last touch, and it never types: no
password can go through it. A new key each time either starts.

Never anything but a phone on your own network: an address that isn't private is turned away, as is anything without
the key. Plain http on your Wi-Fi, as there's no certificate for it; the key and allowing each phone are its guard."""
import html
import ipaddress
import json
import os
import secrets
import socket
import threading
import time
import ctypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

FILES_FOR = 600  # seconds the shelf's files can be fetched for, at most, after their code shows
DECK_IDLE = 1800  # seconds after the last touch that the Deck turns itself off
MOST_BODY = 2048  # bytes a phone's press may have
# what the Deck's buttons press: Windows' own keys for media, slides and videos, and never one that types words
KEYS = {"play": (0xB3,), "next": (0xB0,), "previous": (0xB1,), "volume_up": (0xAF,), "volume_down": (0xAE,),
        "mute": (0xAD,), "left": (0x25,), "right": (0x27,), "up": (0x26,), "down": (0x28,), "space": (0x20,),
        "escape": (0x1B,), "slideshow": (0x74,), "fullscreen": (0x46,)}  # F5 starts slides; F, a player's full screen
_user32 = ctypes.WinDLL("user32")
MOVE, LEFT_DOWN, LEFT_UP, RIGHT_DOWN, RIGHT_UP, WHEEL = 0x0001, 0x0002, 0x0004, 0x0008, 0x0010, 0x0800


# NectarLink (7 November 2026, the owner's: "nectarlink was installed, check it, it will help"), the app on this PC
# paired with their phone: it sends files and the clipboard to the phone and rings it, from its own command line
# (--send-to, as Explorer's Send to; --task send-clipboard, find-phone). Its list of phones is read, never changed.
NECTAR = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Nectarlink", "nectarlink-desktop.exe")
NECTAR_DB = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Nectarlink", "nectarlink.db")
NECTAR_TASKS = ("send-clipboard", "find-phone")


def nectar_phone():
    """The phone NectarLink is paired with, by its name ("Xiaomi 11 Lite NE"), or None if NectarLink isn't here or has
    no phone."""
    if not (os.path.isfile(NECTAR) and os.path.isfile(NECTAR_DB)):
        return None
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{NECTAR_DB}?mode=ro", uri=True, timeout=1)
        try:
            row = con.execute("SELECT name FROM peers WHERE kind='phone' ORDER BY last_seen DESC LIMIT 1").fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    return str(row[0]) if row and row[0] else None


def nectar_send(paths=None, task=None):
    """Files to the phone through NectarLink (--send-to), or one of its tasks (NECTAR_TASKS): it's started if it isn't
    running, and does the rest itself."""
    if task is not None and task not in NECTAR_TASKS:
        raise ValueError(task)
    files = [p for p in paths or [] if os.path.isfile(p)]
    if task is None and not files:
        raise RuntimeError("There are no files to send")
    args = ["--task", task] if task else ["--send-to", *files]
    import subprocess
    subprocess.Popen([NECTAR, *args], close_fds=True, creationflags=0x08000000)


def lan_address():
    """This PC's address on its network, the one a phone on the same Wi-Fi reaches it at, or None. Asking the route to
    a test address sends nothing."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return ip if ipaddress.ip_address(ip).is_private and not ipaddress.ip_address(ip).is_loopback else None


def phone_name(agent):
    """A phone's kind, from its browser's words, for the island's question: "an iPhone", "an Android phone"."""
    agent = str(agent or "")
    if "iPhone" in agent or "iPad" in agent:
        return "an iPhone" if "iPhone" in agent else "an iPad"
    if "Android" in agent:
        return "an Android phone"
    return "a phone"


class _Server:
    """A server on the Wi-Fi with its own key: url, stop(), and the pages its subclass answers (page, press)."""

    def __init__(self):
        ip = lan_address()
        if ip is None:
            raise RuntimeError("This PC isn't on a network a phone can reach")
        self.key = secrets.token_urlsafe(12)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _ok(self):
                try:
                    near = ipaddress.ip_address(self.client_address[0]).is_private
                except ValueError:
                    near = False
                if not near or not self.path.startswith(f"/{owner.key}/"):
                    self.send_error(404)
                    return None
                return self.path[len(owner.key) + 2:]

            def do_GET(self):
                rest = self._ok()
                if rest is not None:
                    owner.page(self, rest)

            def do_POST(self):
                rest = self._ok()
                if rest is None:
                    return
                n = int(self.headers.get("Content-Length") or 0)
                if n > MOST_BODY:
                    self.send_error(413)
                    return
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    self.send_error(400)
                    return
                owner.press(self, rest, body if isinstance(body, dict) else {})

        self.httpd = ThreadingHTTPServer((ip, 0), Handler)
        self.httpd.daemon_threads = True
        self.url = f"http://{ip}:{self.httpd.server_address[1]}/{self.key}/"
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="harry-phone", daemon=True)
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    @staticmethod
    def send(handler, body, kind="text/html; charset=utf-8", code=200, extra=()):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        handler.send_response(code)
        handler.send_header("Content-Type", kind)
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "no-store")
        for k, v in extra:
            handler.send_header(k, v)
        handler.end_headers()
        handler.wfile.write(data)

    def page(self, handler, rest):
        handler.send_error(404)

    def press(self, handler, rest, body):
        handler.send_error(404)


STYLE = ("<meta name='viewport' content='width=device-width,initial-scale=1,user-scalable=no'><style>"
         "body{margin:0;background:#0b0b0c;color:#efede8;font:16px system-ui,sans-serif}"
         "h1{font-size:20px;margin:22px 18px 6px}p{color:#9a9894;margin:0 18px 16px;font-size:14px}"
         "a.f{display:flex;justify-content:space-between;margin:8px 14px;padding:16px;border-radius:16px;"
         "background:#1c1c1e;color:#efede8;text-decoration:none}a.f span{color:#9a9894}</style>")


class Share(_Server):
    """The shelf's files for your phone: a page listing them, each a link that downloads it, for FILES_FOR seconds."""

    def __init__(self, paths):
        self.paths = [p for p in paths if os.path.isfile(p)]
        if not self.paths:
            raise RuntimeError("There are no files on the shelf to send")
        self.until = time.time() + FILES_FOR
        super().__init__()

    def page(self, handler, rest):
        if time.time() > self.until:
            handler.send_error(410)
            return
        if rest == "":
            rows = "".join(f"<a class='f' href='f/{i}'>{html.escape(os.path.basename(p))}"
                           f"<span>{_size(p)}</span></a>" for i, p in enumerate(self.paths))
            self.send(handler, f"<!doctype html><title>From your PC</title>{STYLE}<h1>From your PC</h1>"
                               f"<p>Tap one to save it on this phone.</p>{rows}")
            return
        if rest.startswith("f/") and rest[2:].isdigit() and int(rest[2:]) < len(self.paths):
            path = self.paths[int(rest[2:])]
            name = os.path.basename(path)
            try:
                size = os.path.getsize(path)
                with open(path, "rb") as f:
                    handler.send_response(200)
                    handler.send_header("Content-Type", "application/octet-stream")
                    handler.send_header("Content-Length", str(size))
                    handler.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(name)}")
                    handler.end_headers()
                    while True:
                        chunk = f.read(1 << 16)
                        if not chunk:
                            break
                        handler.wfile.write(chunk)
            except OSError:
                handler.send_error(404)
            return
        handler.send_error(404)


def _size(path):
    try:
        n = os.path.getsize(path)
    except OSError:
        return ""
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024


class Deck(_Server):
    """PC Deck: the phone's page (DECK_PAGE) and what it presses. A phone is known by a cookie of its own; until it's
    allowed on the PC (allow), nothing it presses does anything and ask(phone, its kind) has the island ask once."""

    def __init__(self, ask, apps):
        self.ask, self.apps = ask, apps  # apps(): [(name, path)] of the dock's pins, read when the page loads
        self.allowed, self.asked, self.denied = set(), set(), set()
        self.used = time.time()
        self.shown_apps = []
        super().__init__()

    def allow(self, phone, yes=True):
        (self.allowed if yes else self.denied).add(phone)
        self.asked.discard(phone)

    def _phone(self, handler):
        for part in (handler.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "hh_deck" and v:
                return v
        return None

    def page(self, handler, rest):
        if rest != "":
            handler.send_error(404)
            return
        phone = self._phone(handler) or secrets.token_urlsafe(9)
        self.shown_apps = list(self.apps())[:12]
        apps = "".join(f"<button data-app='{i}'>{html.escape(name)}</button>" for i, (name, _) in
                       enumerate(self.shown_apps))
        self.send(handler, DECK_PAGE.replace("{{APPS}}", apps),
                  extra=(("Set-Cookie", f"hh_deck={phone}; Path=/{self.key}/; HttpOnly; SameSite=Strict"),))

    def press(self, handler, rest, body):
        phone = self._phone(handler)
        if rest != "do" or not phone:
            handler.send_error(404)
            return
        if phone in self.denied:
            self.send(handler, b'{"state":"denied"}', "application/json")
            return
        if phone not in self.allowed:
            if phone not in self.asked:
                self.asked.add(phone)
                self.ask(phone, phone_name(handler.headers.get("User-Agent")))
            self.send(handler, b'{"state":"waiting"}', "application/json")
            return
        self.used = time.time()
        try:
            self.do(body)
        except Exception as exc:
            print(f"  deck: {exc!r}")
        self.send(handler, b'{"state":"ok"}', "application/json")

    def do(self, body):
        """One press from an allowed phone: the pointer moved or clicked, the wheel, a key from KEYS, or a pinned app."""
        what = str(body.get("do") or "")
        if what == "move":
            dx, dy = (max(-200, min(200, int(body.get(k) or 0))) for k in ("dx", "dy"))
            _user32.mouse_event(MOVE, dx, dy, 0, 0)
        elif what in ("click", "right"):
            down, up = (LEFT_DOWN, LEFT_UP) if what == "click" else (RIGHT_DOWN, RIGHT_UP)
            _user32.mouse_event(down, 0, 0, 0, 0)
            _user32.mouse_event(up, 0, 0, 0, 0)
        elif what == "scroll":
            _user32.mouse_event(WHEEL, 0, 0, ctypes.c_uint32(max(-600, min(600, int(body.get("dy") or 0)))).value, 0)
        elif what == "key" and body.get("key") in KEYS:
            for vk in KEYS[body["key"]]:
                _user32.keybd_event(vk, 0, 0, 0)
                _user32.keybd_event(vk, 0, 2, 0)
        elif what == "app" and str(body.get("app")).isdigit() and int(body["app"]) < len(self.shown_apps):
            path = self.shown_apps[int(body["app"])][1]
            threading.Thread(target=os.startfile, args=(path,), daemon=True).start()


DECK_PAGE = """<!doctype html><title>PC Deck</title>""" + STYLE + """<style>
#pad{margin:12px 14px;height:46vh;border-radius:22px;background:#1c1c1e;display:flex;align-items:center;
justify-content:center;color:#5d5b58;font-size:14px;touch-action:none}
.row{display:flex;gap:8px;margin:8px 14px}.row button,#apps button{flex:1;padding:14px 4px;border:0;border-radius:14px;
background:#1c1c1e;color:#efede8;font-size:15px}#apps{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;
margin:8px 14px}h2{font-size:13px;color:#9a9894;margin:14px 18px 0;font-weight:500;text-transform:uppercase}
#wait{display:none;margin:12px 14px;padding:14px;border-radius:14px;background:#3a221c;color:#ffb38a}
</style><h1>PC Deck</h1><div id='wait'>Allow this phone on your PC: the island is asking.</div>
<div id='pad'>Move one finger to point, tap to click, two to scroll</div>
<div class='row'><button data-key='previous'>&#9198;</button><button data-key='play'>&#9199;</button>
<button data-key='next'>&#9197;</button><button data-key='volume_down'>&#8722;</button>
<button data-key='mute'>&#128263;</button><button data-key='volume_up'>+</button></div>
<h2>Slides and videos</h2><div class='row'><button data-key='left'>&#8592;</button><button data-key='right'>&#8594;</button>
<button data-key='space'>Space</button><button data-key='slideshow'>F5</button><button data-key='escape'>Esc</button>
<button data-do='right'>Right-click</button></div><h2>Your apps</h2><div id='apps'>{{APPS}}</div>
<script>
function send(o){fetch('do',{method:'POST',body:JSON.stringify(o),keepalive:true}).then(r=>r.json()).then(r=>{
document.getElementById('wait').style.display=r.state=='waiting'?'block':'none';
if(r.state=='denied')document.body.innerHTML='<h1>Not allowed</h1><p>The PC said no to this phone.</p>';}).catch(()=>{});}
document.querySelectorAll('[data-key]').forEach(b=>b.onclick=()=>send({do:'key',key:b.dataset.key}));
document.querySelectorAll('[data-do]').forEach(b=>b.onclick=()=>send({do:b.dataset.do}));
document.querySelectorAll('[data-app]').forEach(b=>b.onclick=()=>send({do:'app',app:b.dataset.app}));
var pad=document.getElementById('pad'),last=null,moved=0,fingers=0,dx=0,dy=0,t0=0,queued=false;
function flush(){queued=false;if(dx||dy){send(fingers>1?{do:'scroll',dy:Math.round(-dy*4)}:{do:'move',dx:Math.round(dx),dy:Math.round(dy)});dx=dy=0;}}
pad.addEventListener('touchstart',e=>{e.preventDefault();fingers=e.touches.length;last=e.touches[0];moved=0;t0=Date.now();});
pad.addEventListener('touchmove',e=>{e.preventDefault();var t=e.touches[0];var x=(t.clientX-last.clientX)*2,y=(t.clientY-last.clientY)*2;
moved+=Math.abs(x)+Math.abs(y);dx+=x;dy+=y;last=t;if(!queued){queued=true;requestAnimationFrame(flush);}});
pad.addEventListener('touchend',e=>{e.preventDefault();if(moved<12&&Date.now()-t0<300)send({do:fingers>1?'right':'click'});});
send({do:'hello'});
</script>"""
