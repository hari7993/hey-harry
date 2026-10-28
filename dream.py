"""Dream mode (28 October 2026, the owner's ask): while music plays, a pixel-art scene fills the screen and the song's
words go by on the right in time with it, for a lofi mood. "Hey Harry, dream mode" opens it, "dream mode on the beach"
opens that scene, "next scene" changes it, and "exit dream mode" or Esc closes it. Said with nothing playing, she puts
some lofi on first.

Six scenes are drawn in code (dream/scenes.js) and shown by dream/index.html, live, so each one plays on forever with
no loop to see. It opens in its own full-screen window: Edge (or Chrome or Brave) started in app mode with a profile
of its own, so no tabs, no bars and nothing of yours in it. The page is served here, to this PC only (127.0.0.1, a
free port, a random key in its address), and asks this module what's playing a couple of times a second. This module
asks Windows' media controls, as the island does, so YouTube in a browser, Spotify, Amazon Music, Apple Music, VLC
and the rest all work. The words come from LRCLIB (lrclib.net, free, no key): it's sent the song's title, artist and
length, nothing else, and what it sends back is kept on this PC (lyrics.json), so each song is looked up once. With
no words found, or a mix or a stream rather than a song, the song's name stands in their place.

Importing this starts nothing: the server, the window and the thread following the music only run while it's open."""
import atexit
import datetime as dt
import difflib
import http.server
import json
import os
import re
import secrets
import subprocess
import threading
import time
from urllib.parse import urlsplit

import requests

import identity
import settings
import toolbox
import winplatform as win

host = None  # siri, once bind() is called
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_DIR = os.path.join(HERE, "dream")
FILES = {"": ("index.html", "text/html; charset=utf-8"), "index.html": ("index.html", "text/html; charset=utf-8"),
         "scenes.js": ("scenes.js", "text/javascript; charset=utf-8")}
SCENES = ("night-drive", "sunset-drive", "night-beach", "morning-beach", "city-terrace", "rain-window")  # SCENE_ORDER
NAMES = {"night-drive": "Night drive", "sunset-drive": "Sunset drive", "night-beach": "Night beach",
         "morning-beach": "Morning beach", "city-terrace": "City terrace", "rain-window": "Rainy window"}
# the scenes that suit the time of day, by hour (past midnight counted on from 24), taken in turn each time
TIMES = ((5, 10, ("morning-beach",)), (10, 17, ("morning-beach", "sunset-drive")),
         (17, 20, ("sunset-drive", "city-terrace")), (20, 29, ("night-drive", "city-terrace", "rain-window", "night-beach")))
LOFI = "lofi hip hop radio beats to relax study to"  # what she puts on when nothing's playing
BROWSERS = ("msedge.exe", "chrome.exe", "brave.exe")  # each takes --app and --start-fullscreen
BROWSER_PATHS = (r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
                 r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
                 r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
                 r"%LocalAppData%\Google\Chrome\Application\chrome.exe")
LRCLIB = "https://lrclib.net/api"
UA = {"User-Agent": "Hey Harry dream mode (a voice assistant for Windows)"}
HTTP = requests.Session()
CACHE = os.path.join(win.APPDATA_DIR, "lyrics.json")
CACHE_MOST = 300  # songs kept, the oldest looked-up going first
RETRY_MISSING = 24 * 3600.0  # a song LRCLIB didn't have is asked about again after a day

LOCK = threading.RLock()
NOW = {"open": False, "scene": None, "rev": 0, "track": None, "lyrics": None, "close": False}
# the page's server, the key in its address, its window once it's up, when its browser was started
SERVER, KEY, WINDOW, LAUNCHED, GEN = [None], [None], [None], [0.0], [0]
CACHE_LOCK = threading.Lock()
_CACHE = [None]
MISSING = object()


def bind(module):
    global host
    host = module


# --------------------------------------------------------------------------- the scenes
SCENE_WORDS = (  # the more particular first: "night beach" before "beach", "sunset drive" before "drive"
    ("night-beach", r"(?:night|moonlit|moonlight|moon) (?:beach|sea|ocean|shore)|(?:beach|sea|ocean) (?:at|by) night|"
                    r"moon(?:light)?|lighthouse"),
    ("morning-beach", r"(?:morning|sunrise|sunny|day ?time|summer) (?:beach|sea|ocean|shore)|(?:beach|sea|ocean) in the "
                      r"morning|sunrise|morning|summer"),
    ("sunset-drive", r"sunset(?: drive)?|golden hour|dusk|(?:coast|coastal|evening) (?:drive|road)|coast|palm trees?"),
    ("night-drive", r"(?:night )?(?:drive|driving|car|road(?: trip)?|highway)(?: at night)?"),
    ("city-terrace", r"(?:city|rooftop|roof|terrace|balcony|skyline)(?: terrace| lights| at night| view)?"),
    ("rain-window", r"rain(?:y|ing)?(?: window| night| day)?|window|storm(?:y)?|cosy|cozy|candle"),
    ("beach", r"beach|sea|ocean|seaside|shore"),  # a beach with no time said: the time of day says which
)
SCENE_RX = [(scene, re.compile(rf"\b(?:{rx})\b")) for scene, rx in SCENE_WORDS]


def _hour(now=None):
    hour = (now or dt.datetime.now()).hour
    return hour + 24 if hour < 5 else hour


def scene_for(words, now=None):
    """The scene words name ("on the beach", "rainy", "night drive"), or None when they name none."""
    t = " ".join(re.sub(r"[^\w\s-]", " ", str(words or "").lower()).replace("-", " ").split())
    for scene, rx in SCENE_RX:
        if rx.search(t):
            return scene if scene != "beach" else ("morning-beach" if 5 <= _hour(now) < 18 else "night-beach")
    return None


def scene_id(value):
    """A scene from a step's "scene": its id, its name, or words for it. None for none or "" (one picked for the time)."""
    v = str(value or "").strip().lower()
    if v in SCENES:
        return v
    return next((s for s, name in NAMES.items() if name.lower() == v), None) or (scene_for(v) if v else None)


def pick_scene(now=None):
    """One that suits the time of day: the next of them after the last one shown, so it isn't always the same."""
    hour = _hour(now)
    group = next(g for a, b, g in TIMES if a <= hour < b)
    last = settings.get("dream_scene")
    return group[(group.index(last) + 1) % len(group)] if last in group else group[0]


def following(scene):
    return SCENES[(SCENES.index(scene) + 1) % len(SCENES)] if scene in SCENES else SCENES[0]


# --------------------------------------------------------------------------- the words of a song
TAGS = re.compile(r"\[(\d+):(\d{1,2}(?:[.:]\d{1,3})?)\]")
OFFSET = re.compile(r"\[offset:\s*([+-]?\d+)\s*\]", re.I)
WORD_TAG = re.compile(r"<\d+:\d{1,2}(?:[.:]\d{1,3})?>")


def parse_lrc(text):
    """[[seconds, words], ...] in time order from synced lyrics (LRC): "[01:02.50]words", a line with several times for
    a chorus sung again, [offset:+500] in milliseconds (plus: the words come sooner), and the word-by-word <01:02.80>
    marks dropped. Its [ar:...] and [ti:...] tags and anything else with no time are left out. [] for none."""
    text, shift = str(text or ""), 0.0
    off = OFFSET.search(text)
    if off:
        shift = int(off.group(1)) / 1000.0
    out = []
    for raw in text.splitlines():
        rest, stamps = raw.strip(), []
        while (m := TAGS.match(rest)):
            stamps.append(int(m.group(1)) * 60 + float(m.group(2).replace(":", ".")))
            rest = rest[m.end():].lstrip()
        words = " ".join(WORD_TAG.sub("", rest).split())
        out += [[round(max(0.0, s - shift), 2), words] for s in stamps]
    out.sort(key=lambda p: p[0])
    return out


BROWSER_APPS = re.compile(r"chrome|msedge|edge|firefox|brave|opera|vivaldi", re.I)
NOISE = re.compile(r"\s*[(\[【](?:[^)\]】]*?\b(?:official|lyrics?|audio|video|visuali[sz]er|hd|hq|4k|remaster\w*|"
                   r"explicit|clean|mv|m/v|live|version)\b[^)\]】]*)[)\]】]", re.I)
FEAT = re.compile(r"\s*[(\[]?\b(?:feat|ft|featuring)\b\.?\s[^)\]]*[)\]]?", re.I)
CHANNEL = re.compile(r"\s*(?:vevo|- topic|official(?: channel)?)\s*$", re.I)
DASH = re.compile(r"\s[-–—]\s")
# a mix or a stream, many songs and no one set of words: "lofi hip hop radio", "beats to relax/study to", "1 hour"
MIX = re.compile(r"\b(?:lo-?fi (?:hip ?hop )?(?:radio|beats|mix|music)|beats to (?:relax|study|sleep|chill)|"
                 r"\d+ ?(?:hours?|hrs?)\b|24/7|non ?stop|(?:music|songs?|lo-?fi) mix|mixtape|playlist|compilation|"
                 r"full album|live ?stream)", re.I)


def song_of(title, artist, app=""):
    """(song, artist) to look one up by. A music app's are as it says; a video's are worked out of its title, as most
    say "Artist - Song (Official Video)": "Ed Sheeran - Perfect (Official Music Video)" from "EdSheeranVEVO" is
    ("Perfect", "Ed Sheeran"). Features and "(Lyrics)" and the like come off."""
    t, a = " ".join(str(title or "").split()), " ".join(str(artist or "").split())
    if BROWSER_APPS.search(app or "") or CHANNEL.search(a):
        t = NOISE.sub("", t)
        parts = DASH.split(t, maxsplit=1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            a, t = parts[0].strip(), parts[1].strip()
        else:
            a = CHANNEL.sub("", a).strip()
            if " " not in a:
                a = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", a)  # "EdSheeran" is "Ed Sheeran"
        t = re.split(r"\s(?:\||//)\s", t)[0]  # "Song | Album" and "Song // Live at ..."
    t = FEAT.sub("", NOISE.sub("", t)).strip(" -–—|\"'")
    a = re.split(r"\s*,\s*", FEAT.sub("", a))[0].strip() if a else ""  # "A, B" is A's
    return t, a


def _norm(s):
    return " ".join(re.sub(r"[^\w\s]", " ", NOISE.sub("", str(s or "")).lower()).split())


def _same_song(found, song):
    a, b = _norm(found.get("trackName")), _norm(song)
    return bool(a and b) and (a == b or a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= 0.7)


def _best(found, song, duration, within=45):
    """Of what LRCLIB found, the one that's this song: its name close, its length within 45 seconds of what's playing
    (a video runs on past its song), the closest of those within 10 seconds that has words in time first."""
    ok = [o for o in found if isinstance(o, dict) and _same_song(o, song)
          and (o.get("syncedLyrics") or o.get("plainLyrics") or o.get("instrumental"))]
    if duration:
        ok = [o for o in ok if abs(float(o.get("duration") or 0) - duration) <= within]
    if not ok:
        return None

    def rank(o):
        d = abs(float(o.get("duration") or 0) - duration) if duration else 0.0
        return (d > 10, not o.get("syncedLyrics"), d)
    return min(ok, key=rank)


def _lrclib(song, artist, duration):
    """LRCLIB asked by song and artist, then by both as words, then (for a name of its own, six letters or more) by
    the song's name alone, which only counts within 10 seconds of the length: a video's "Song | Film | Singer" has
    no artist to go by."""
    asks = [({"track_name": song, "artist_name": artist}, 45), ({"q": f"{artist} {song}"}, 45)] if artist else []
    if len(re.sub(r"\W", "", song)) >= 6:
        asks.append(({"q": song}, 10))
    for params, within in asks:
        r = HTTP.get(f"{LRCLIB}/search", params=params, headers=UA, timeout=8)
        if r.status_code == 404:
            continue
        r.raise_for_status()
        best = _best(r.json() or [], song, duration, within)
        if best:
            return best
    return None


def _words_of(found):
    if not found:
        return None
    lines = parse_lrc(found.get("syncedLyrics"))
    if lines:
        return {"lines": lines}
    plain = [line.strip() for line in str(found.get("plainLyrics") or "").splitlines()]
    if any(plain):
        return {"plain": plain}
    return {"instrumental": True} if found.get("instrumental") else None


def _cache():
    if _CACHE[0] is None:
        try:
            with open(CACHE, encoding="utf-8") as f:
                _CACHE[0] = json.load(f)
        except (OSError, ValueError):
            _CACHE[0] = {}
    return _CACHE[0]


def _cached(key):
    with CACHE_LOCK:
        hit = _cache().get(key)
    if not isinstance(hit, dict):
        return MISSING
    if hit.get("words") is None and time.time() - float(hit.get("at") or 0) > RETRY_MISSING:
        return MISSING
    return hit.get("words")


def _keep(key, words):
    with CACHE_LOCK:
        kept = _cache()
        kept[key] = {"at": time.time(), "words": words}
        for old in sorted(kept, key=lambda k: float(kept[k].get("at") or 0))[:max(0, len(kept) - CACHE_MOST)]:
            kept.pop(old, None)
        try:
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            with open(CACHE + ".tmp", "w", encoding="utf-8") as f:
                json.dump(kept, f)
            os.replace(CACHE + ".tmp", CACHE)
        except OSError as exc:
            print(f"  dream: couldn't keep the words: {exc!r}")


def lyrics_for(title, artist, duration=0.0, app=""):
    """The words of what's playing: {"lines": [[seconds, words], ...]} when LRCLIB has them in time with it,
    {"plain": [lines]} when it has them with no times, {"instrumental": True} for a song with none, and None when
    it's not found, has no fixed length (a stream), is a mix, or LRCLIB can't be reached (that one isn't kept, so
    it's asked again next time)."""
    song, singer = song_of(title, artist, app)
    duration = float(duration or 0)
    if not song or duration <= 0 or duration > 20 * 60 or MIX.search(f"{title} {artist}"):
        return None
    key = f"{song.lower()}|{singer.lower()}|{round(duration)}"
    hit = _cached(key)
    if hit is not MISSING:
        return hit
    try:
        words = _words_of(_lrclib(song, singer, duration))
    except (requests.RequestException, ValueError) as exc:
        print(f"  dream: LRCLIB {exc!r}")
        return None
    _keep(key, words)
    return words


# --------------------------------------------------------------------------- what's playing
def _playing():
    """What Windows' media controls show playing, or paused, as the page wants it: None for nothing."""
    try:
        session = win.media_session()
        if session is None:
            return None
        title, artist = win.media_props(session)
        if not title:
            return None
        return {"title": title, "artist": artist, "app": str(session.source_app_user_model_id or ""),
                "playing": win.media_status(session) == "playing", "position": round(max(0.0, win.media_position(session)), 2),
                "duration": round(win.media_length(session), 2), "at": time.time()}
    except Exception as exc:
        print(f"  dream: media {exc!r}")
        return None


def _follow():
    """While it's open: brings its window in front once it's up, ends dream mode when it's gone (Esc, Alt+F4) or never
    comes up, and follows what's playing, from Windows' media controls each second, its words looked up as the song
    changes. The window is followed, not the browser started: Edge hands over to another of its own, and that ends."""
    seen = MISSING
    while True:
        with LOCK:
            if not NOW["open"]:
                return
            hwnd = WINDOW[0]
        if hwnd is None:
            hwnd = _window()
            if hwnd:
                with LOCK:
                    WINDOW[0] = hwnd
                _front(hwnd)
            elif time.time() - LAUNCHED[0] > 20:
                print("  dream: its window never came up")
                close()
                return
        elif not win.shown(hwnd):
            close()
            return
        track = _playing()
        key = (track["title"], track["artist"]) if track else None
        with LOCK:
            NOW["track"] = track
            if key != seen:
                seen = key
                GEN[0] += 1
                NOW["lyrics"] = None
                if track:
                    threading.Thread(target=_look_up, args=(track, GEN[0]), daemon=True).start()
            NOW["rev"] += 1
        time.sleep(1.0)


def _look_up(track, gen):
    try:
        words = lyrics_for(track["title"], track["artist"], track["duration"], track["app"])
    except Exception as exc:  # never the end of dream mode: the song's name shows instead
        print(f"  dream: words {exc!r}")
        words = None
    with LOCK:
        if GEN[0] == gen and NOW["open"]:
            NOW["lyrics"] = words
            NOW["rev"] += 1


# --------------------------------------------------------------------------- the page's server
class _Page(http.server.BaseHTTPRequestHandler):
    """The page, its scenes and what it asks for, only under the key in its address: anything else is 404."""

    def do_GET(self):
        path, key = urlsplit(self.path).path, KEY[0]
        if not key or not path.startswith(f"/{key}/"):
            return self._send(404, b"", "text/plain")
        name = path[len(key) + 2:]
        if name in FILES:
            file, kind = FILES[name]
            with open(os.path.join(PAGE_DIR, file), "rb") as f:
                return self._send(200, f.read(), kind)
        if name == "state":
            return self._json(state())
        if name == "next":
            next_scene()
            return self._json(state())
        if name == "close":  # Esc on the page: it closes its own window, this winds the rest down
            threading.Thread(target=close, daemon=True).start()
            return self._json({"ok": True})
        return self._send(404, b"", "text/plain")

    def _json(self, value):
        self._send(200, json.dumps(value).encode("utf-8"), "application/json")

    def _send(self, code, body, kind):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, *_):
        pass


def _serve():
    """A server for the page on this PC only, on a free port, running on its own thread. (server, address)."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Page)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.25}, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


def state():
    with LOCK:
        return {k: NOW[k] for k in ("scene", "rev", "track", "lyrics", "close")}


# --------------------------------------------------------------------------- its window
TITLE = "Dream mode"  # the page's <title>, so its window's


def _profile():
    return os.path.join(win.APPDATA_DIR, "dream-browser")


def _browser():
    for exe in BROWSERS:
        path = win.app_path(exe)
        if path:
            return path
    return next((p for p in map(os.path.expandvars, BROWSER_PATHS) if os.path.isfile(p)), None)


def _launch(exe, url):
    """The browser in app mode, full screen, with a profile of its own (in her folder) so nothing of yours is in it."""
    return subprocess.Popen([exe, f"--app={url}", "--start-fullscreen", f"--user-data-dir={_profile()}", "--no-first-run",
                             "--no-default-browser-check", "--disable-sync", "--hide-crash-restore-bubble"],
                            creationflags=win.CREATE_NO_WINDOW)


def _ours(pid):
    """True if process pid is a browser started with dream mode's own profile: never one of yours."""
    import psutil
    try:
        return _profile().lower() in " ".join(psutil.Process(pid).cmdline()).lower()
    except psutil.Error:
        return False


def _window():
    """Its window: titled as the page is, a browser's, and of dream mode's own profile. None when there's none."""
    for hwnd, exe, title in win.open_windows():
        if title == TITLE and os.path.basename(exe).lower() in BROWSERS and _ours(win._pid(hwnd)):
            return hwnd
    return None


def _front(hwnd):
    try:
        win.bring_to_front(hwnd)
    except Exception as exc:  # Windows keeping it behind: it's open all the same
        print(f"  dream: in front {exc!r}")


def _close_windows(hwnd):
    """Asks its window to close, as clicking its X does."""
    win.user32.PostMessageW(hwnd, win.WM_CLOSE, 0, 0)


def _end_browser():
    """Ends whatever's left of dream mode's browser, the processes of its own profile and nothing else: it shuts by
    itself once its window's gone, or should."""
    import psutil
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            if (proc.info["name"] or "").lower() in BROWSERS and \
                    _profile().lower() in " ".join(proc.info["cmdline"] or []).lower():
                proc.kill()
        except psutil.Error:
            pass


def _wait(check, seconds):
    """check() each tenth of a second till it's true or the time's up: what it last gave."""
    end = time.time() + seconds
    while True:
        got = check()
        if got or time.time() >= end:
            return got
        time.sleep(0.1)


def is_open():
    with LOCK:
        return NOW["open"]


def open_scene(scene=None):
    """Opens dream mode on scene (one of SCENES, or None for one that suits the time), or changes to that scene if it's
    open already. The scene shown. RuntimeError with a reason she can say when it can't open."""
    scene = scene if scene in SCENES else None
    with LOCK:
        hwnd = WINDOW[0]
        if NOW["open"] and (hwnd is None or win.shown(hwnd)):
            if scene and scene != NOW["scene"]:
                _show(scene)
            return NOW["scene"]
        gone = NOW["open"]
    if gone:  # its window was closed, and the thread following the music hasn't seen it yet
        close()
    exe = _browser()
    if not exe:
        raise RuntimeError("Dream mode needs Edge or Chrome, and I can't find either")
    _settle()
    scene = scene or pick_scene()
    server, address = _serve()
    key = secrets.token_urlsafe(18)
    with LOCK:
        SERVER[0], KEY[0], WINDOW[0], LAUNCHED[0] = server, key, None, time.time()
        NOW.update(open=True, close=False, track=None, lyrics=None)
        _show(scene)
    try:
        _launch(exe, f"{address}{key}/")
    except OSError as exc:
        print(f"  dream: {exc!r}")
        with LOCK:
            NOW["open"] = False
        _wind_down(server)
        raise RuntimeError("I couldn't open dream mode's window") from exc
    threading.Thread(target=_follow, daemon=True).start()
    return scene


def _show(scene):
    NOW["scene"] = scene
    NOW["rev"] += 1
    try:
        settings.put("dream_scene", scene)
    except OSError:
        pass


def next_scene():
    """The next of the six, while it's open: the scene now shown."""
    with LOCK:
        if NOW["open"]:
            _show(following(NOW["scene"]))
        return NOW["scene"]


def close():
    """Ends dream mode: the page closes its own window when it next asks what's playing, and whatever's still there
    after that is closed for it, the browser, the server and all. True if it was open."""
    with LOCK:
        if not NOW["open"]:
            return False
        NOW.update(open=False, close=True)
        NOW["rev"] += 1
        server, hwnd, launched = SERVER[0], WINDOW[0], LAUNCHED[0]
    threading.Thread(target=_wind_down, args=(server, hwnd, launched), daemon=True).start()
    return True


def _wind_down(server, hwnd=None, launched=0.0):
    """After close: the page's own close given a moment, then its X clicked for it, then what's left of its browser
    ended; the server last, as the page asks it to learn it's closing."""
    if hwnd is None and time.time() - launched < 15:  # closed as it opened: its window may be on its way
        hwnd = _wait(_window, 5.0)
    if hwnd is not None and not _wait(lambda: not win.shown(hwnd), 2.5):
        _close_windows(hwnd)
        _wait(lambda: not win.shown(hwnd), 3.0)
    _end_browser()
    if server is not None:
        server.shutdown()
        server.server_close()
    with LOCK:
        if SERVER[0] is server:
            SERVER[0], KEY[0], WINDOW[0] = None, None, None
            NOW["close"] = False


def _settle():
    """A window still closing goes first: the next one shares its profile, so it would open in that one, and go too."""
    if not _wait(lambda: _window() is None, 5.0):
        _end_browser()


@atexit.register
def _at_exit():
    hwnd = WINDOW[0]
    if NOW["open"] and hwnd:
        try:
            _close_windows(hwnd)
        except Exception:
            pass


# --------------------------------------------------------------------------- her step, and the words for it
LINE = ('{"do":"dream","scene":"rain-window"}  dream mode: a pixel-art scene full screen while their music plays, '
        'its words going by on the right in time; scene night-drive, sunset-drive, night-beach, morning-beach, '
        'city-terrace or rain-window, "" for one that suits the time; "action":"next" for another scene, "close" to '
        'leave it')
WORDS = re.compile(r"\b(?:dream\w*|scenes?|lo-?fi|vibes?|mood|aesthetic|ambien\w*)\b", re.I)


def _step(step):
    action = str(step.get("action") or "open").lower()
    if action in ("close", "stop", "off", "exit", "leave"):
        return "closed" if close() else "wasn't open"
    if action == "next":
        if not is_open():
            raise RuntimeError("Dream mode isn't on. Say dream mode to start it")
        return next_scene()
    return open_scene(scene_id(step.get("scene")))


def register():
    """Her step for it, in the registry: it opens a window, as opening an app does, so after a read it may go ahead
    and a routine may hold it; never in the background, as it takes the whole screen."""
    if toolbox.get("dream") is None:
        toolbox.register("dream", effect="reversible", asks_for=None, confirm=None, handler=_step, line=LINE,
                         read_safe=True, routine_ok=True, background="never", gated_by="DREAM_STEPS")


register()


def prompt_block(text):
    """Her line for it, for the planner, only when the words may ask for it: "" for most requests."""
    return "\n\n" + LINE if WORDS.search(str(text or "")) else ""


DREAM = r"(?:dream(?:y)? ?(?:mode|mood|mod)|lo-?fi mode)"
OPEN = re.compile(rf"(?:(?:turn on|switch on|start|open|enable|begin|enter|go (?:in)?to|take me (?:in)?to|put on|"
                  rf"launch|activate|let'?s (?:go|do)(?: to)?|show me|i want|give me|time for|bring up|run|play)"
                  rf"(?: the| my| a| some)? )?{DREAM}(?: on)?(?: (?:(?:with|on|at|in|for|of|by) )?(?:the |a |my )?"
                  rf"(?P<scene>.+))?")
SCENE_FIRST = re.compile(rf"(?P<scene>.+?) {DREAM}(?: on)?")
CLOSE = re.compile(rf"(?:(?:turn off|switch off|stop|close|exit|end|leave|quit|disable|get out of|come out of|cancel|"
                   rf"finish|shut)(?: the| my)? {DREAM}(?: now)?|{DREAM} off)")
# only with a scene's own word: a bare "next" or "something else" with music on is the next song
NEXT = re.compile(r"(?:(?:show me |give me |go to )?(?:the )?(?:next|another|a different|a new|some other|other) "
                  r"(?:scene|view|place|animation|background)|(?:change|switch|swap)(?: the| this)? "
                  r"(?:scene|view|animation|background))")
GO_SCENE = re.compile(r"(?:(?:switch|change|go|move|jump|cut) (?:it )?(?:to|over to)|show me|take me to|let'?s go to|"
                      r"put on|i want|give me)(?: the| a| some)? (?P<scene>.+)")
WAKE = re.compile(r"wake (?:me )?up|(?:that'?s )?enough dreaming|stop dreaming")


def _plan(steps=(), say=""):
    return {"steps": [dict(s) for s in steps], "say": say}


def quick(words, gate=False):
    """A plan for dream mode said plainly, with no model, or None. Only with her name said: it fills the screen, so
    never from words across the room."""
    if gate == "cold" or host is None:
        return None
    t = host.plain(str(words or ""))
    own = "|".join(re.escape(n) for n in {identity.name().lower(), identity.DEFAULT.lower()} if n)
    t = re.sub(rf"^(?:{own})\s+", "", t).strip()
    if not t:
        return None
    on = is_open()
    if CLOSE.fullmatch(t) or (on and WAKE.fullmatch(t)):
        return _plan([{"do": "dream", "action": "close"}], "Okay.") if on else _plan(say="Dream mode isn't on.")
    if on:
        if NEXT.fullmatch(t):
            return _plan([{"do": "dream", "action": "next"}], NAMES[following(NOW["scene"])] + ".")
        go = GO_SCENE.fullmatch(t)
        scene = scene_for(go["scene"]) if go else None
        if scene:
            return _plan([{"do": "dream", "action": "open", "scene": scene}], NAMES[scene] + ".")
    m = OPEN.fullmatch(t) or SCENE_FIRST.fullmatch(t)
    if not m:
        return None
    asked = (m["scene"] or "").strip()
    scene = scene_for(asked) if asked else None
    if asked and not scene:
        return None  # "dream mode for my exam": not a scene, so the model has it
    if on:
        scene = scene or NOW["scene"]
        return _plan([{"do": "dream", "action": "open", "scene": scene}], NAMES[scene] + ".")
    scene = scene or pick_scene()
    steps, say = [{"do": "dream", "action": "open", "scene": scene}], f"Dream mode, {NAMES[scene].lower()}."
    if not host.media_playing():
        if _paused():  # your song, paused: on again rather than something else
            steps.insert(0, {"do": "media", "action": "play"})
        else:
            steps.insert(0, {"do": "youtube", "query": LOFI, "play": True})
            say = f"Putting on some lofi. {say}"
    return _plan(steps, say)


def _paused():
    """True if Windows' media controls show a song paused, one there to play again."""
    try:
        session = win.media_session()
        return bool(session) and win.media_status(session) == "paused"
    except Exception:
        return False
