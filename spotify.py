"""Spotify: songs, albums, artists, podcasts and playlists (28 October 2026, after Atticus's instant playlists): "play
lofi beats on Spotify", "play my Discover Weekly", "play the album Rumours on Spotify", "play my liked songs".

On Windows there's no AppleScript to tell Spotify what to play, so she opens Spotify's own search for it
(spotify:search:...), presses the play button of the best match there by UI Automation, the way you would, and
checks Windows' media controls that it's playing. If no button fits she does it as a task in the app, which then
learns it. Without the Spotify app, she offers to install it (siri.stage_install, read back and asked about), or
plays it on Spotify's website when you say so."""
import os
import re
import time
from urllib.parse import quote

import winplatform as win

host = None
KINDS = {"playlist": "playlist", "playlists": "playlist", "album": "album", "albums": "album", "artist": "artist",
         "song": "song", "songs": "song", "track": "song", "tracks": "song", "podcast": "podcast",
         "episode": "podcast", "mix": "playlist", "radio": "playlist"}
LIKED = re.compile(r"(?:my )?(?:liked|favou?rite|saved|loved) (?:songs|tracks|music)|my likes|my library", re.I)
OPEN_WAIT, PLAY_WAIT = 15.0, 7.0


def bind(module):
    global host
    host = module


def installed():
    """True if the Spotify app is on this PC: in the Start menu, or its spotify: links have an app."""
    try:
        if win.find_start_app("Spotify", refresh=False):
            return True
    except Exception:
        pass
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"spotify\shell\open\command"):
            return True
    except OSError:
        return False


def link(query):
    """The spotify: link for what was asked: your liked songs, else Spotify's search for it."""
    if LIKED.fullmatch(" ".join(str(query or "").split())):
        return "spotify:collection:tracks"
    return "spotify:search:" + quote(" ".join(str(query or "").split()))


def web(query, kind=""):
    """Spotify's web player searching for it, for when the app isn't here."""
    path = {"playlist": "playlists", "album": "albums", "artist": "artists", "song": "tracks",
            "podcast": "podcasts"}.get(kind, "")
    return "https://open.spotify.com/search/" + quote(query) + (f"/{path}" if path else "")


def _window():
    try:
        found = win.app_windows(host.SPOTIFY)
    except Exception:
        found = []
    return found[0] if found else None


def _playing():
    try:
        session = win.media_session("spotify")
        return bool(session and win.media_playing(session))
    except Exception:
        return False


def _best(items, query, kind):
    """The play button to press: one named "Play <what>" with the most of the asked-for words in it, a kind's own
    section first; the big one on the page for your liked songs."""
    want = {w for w in re.findall(r"[a-z0-9']+", query.lower()) if w not in ("the", "a", "my", "by", "of")}
    best, score = None, 0.0
    for it in items or []:
        name = str(it.get("name") or "")
        low = name.lower()
        if it.get("role") not in ("button", "menuitem", "link") or not low.startswith("play"):
            continue
        if low in ("play", "play/pause") and want:
            continue
        words = set(re.findall(r"[a-z0-9']+", low))
        hit = len(want & words) + (0.5 if kind and kind in low else 0) + (0.2 if not want else 0)
        if hit > score:
            best, score = it, hit
    return best if score >= max(1, len(want) * 0.5) or (not want and best) else None


def play(query, kind="", notify=None):
    """Plays it in the Spotify app. A few words for the log; RuntimeError with what to say when it can't."""
    query = " ".join(str(query or "").split())
    if not query:
        raise RuntimeError("I didn't catch what to play on Spotify")
    if not installed():
        raise RuntimeError("Spotify isn't installed on this PC")
    host.pause_media()  # or the video before carries on under it
    os.startfile(link(query))
    end, hwnd = time.time() + OPEN_WAIT, None
    while time.time() < end and hwnd is None:
        time.sleep(0.5)
        hwnd = _window()
    if hwnd is None:
        raise RuntimeError("Spotify didn't open")
    time.sleep(1.5)  # its search results come in a moment after the window
    pressed = False
    for _ in range(3):
        snap = win.ui_snapshot(hwnd, most=120)
        target = _best((snap or {}).get("items"), "" if LIKED.fullmatch(query) else query, kind)
        if target is not None:
            try:
                win.ui_act(target["el"])
                pressed = True
                break
            except Exception as exc:
                print(f"  spotify: {exc!r}")
        time.sleep(1.0)
    if pressed:
        end = time.time() + PLAY_WAIT
        while time.time() < end:
            if _playing():
                return f"playing {query}"
            time.sleep(0.4)
    # no button fits, or it didn't start: as a task in the app, which learns it once it works
    said, _ = host.see(f"In Spotify, play the {kind or 'top result'} for {query} from the search results that are "
                       f"open", notify)
    if said:
        host.say(said, notify)
    return f"asked the screen: {query}"
