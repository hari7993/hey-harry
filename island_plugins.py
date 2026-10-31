"""The island's plugins, the way MaterialYou Dynamic Island (github.com/Angel-Studio/MaterialYou-Dynamic-Island)
has them: what she's working on, live, with Stop and Deny; a popup when a notification comes in, from the
apps you pick; what's playing, with its controls; the battery when you plug in or it runs low; and a running timer
counting down. Since 30 October 2026, a live activity each, as a phone's island shows them, for dream mode, her
meeting notes, hand control, showing you where to click and her break (Live). Each can be turned on and off, and has
its own options, in the Island tab.

A plugin looks at what Windows already keeps, or at what she keeps in memory (activity.py), on one background
thread, and tells the island what to show. Nothing here sends anything anywhere. To add one, subclass Plugin and put
it in PLUGINS: what it shows as a card (Activity) is drawn without island.py knowing it.
"""
import asyncio
import collections
import ctypes
import os
import queue
import re
import sys
import threading
import time
import winreg

import activity
import settings
import watch
import winplatform as win

FULL_SCREEN = {2, 3, 4, 7}  # SHQueryUserNotificationState: busy, a game, presenting, a full-screen Store app
# the plugins whose popups Do Not Disturb hushes (island_dnd, in the island's Controls, 30 October 2026): what comes
# in from outside, never what's live or her own
HUSHED = ("notifications", "devices", "battery")
SETTINGS_PAGES = ("ms-settings:network-wifi", "ms-settings:bluetooth", "ms-settings:notifications",
                  "ms-settings:sound", "ms-settings:powersleep")  # the pages a right-click in Controls may open


class Activity:
    """What a plugin wants the island to show. kind: notification, media, battery, timer, or card for any other
    plugin's. live: it stays while it lasts (music playing, a timer running), else it's a popup that shows for a few
    seconds. mood: how her eyes react when it comes up, or changes (island_face.MOODS).

    A card's data, drawn by island._card: a row {"title", "lines" (one or two of words under it), "status" (a few
    words at its right, or "since", a time it counts up from), "state" (running, queued, waiting_yes, done, failed or
    stopped, for its glyph), "progress" (0 to 1, or None), "buttons" [{"name", "label", "data", "careful"}]}, or
    {"rows": [rows], "more": how many more there are} for a list, of which the first CARD_ROWS show. "short": the
    few words of the small island it shows while you aren't pointing at it; "badge": a count for her own turn's.
    A click on a button is the plugin's command(name, data); a careful one (Approve) counts only once the pointer has
    rested on it, and never while she's doing a task in an app.

    A live activity's (kind "live", 30 October 2026, drawn by island._live as a phone's island shows one): "glyph"
    (island_face.GLYPHS: moon, record, hand, pointer, pause), "accent" (island.ACCENTS: indigo, red, teal, ...),
    "label" (what it is, at the top of it opened), "title" and "sub" (its words, opened), "short" (its few words
    small), "since" or "until" (a time it counts up from or down to; one counting up is sent again with each new
    hour in "hours", so its clock has room for it), "progress" (0 to 1), "wave" (a waveform,
    opened), "mood" (her eyes in it, island_face.MOODS), "aura" ("breathe" or "steady": a glow round her in its
    colour) and "buttons" as a card's."""
    __slots__ = ("plugin", "kind", "data", "live", "mood", "at", "until", "seconds")

    def __init__(self, plugin, kind, data, live=False, mood=None, seconds=None):
        self.plugin, self.kind, self.data, self.live, self.mood = plugin, kind, data, live, mood
        self.at, self.until, self.seconds = time.time(), None, seconds


def get_options(plugin_id):
    return dict((settings.get("island_plugin_options") or {}).get(plugin_id) or {})


def on(plugin_id):
    """True if the plugin plugin_id is on in the Island tab, as Plugin.enabled has it, from any thread."""
    cls = next((c for c in PLUGINS if c.id == plugin_id), None)
    if cls is None:
        return False
    picked = (settings.get("island_plugins") or {}).get(plugin_id)
    return cls.default_on if picked is None else bool(picked)


class Plugin:
    """One thing the island can show. poll(now) runs on the plugins' thread every `every` seconds while it's on,
    and calls self.show(Activity) for a popup, self.live(Activity or None) for what stays while it lasts."""
    id = name = description = ""
    every = 2.0
    options = ()  # (key, label, default) for the Island tab
    default_on = True
    priority = 0  # which of the ones that stay shows when there are several: the highest

    def __init__(self, host):
        self.host = host

    def enabled(self):
        on = (settings.get("island_plugins") or {}).get(self.id)
        return self.default_on if on is None else bool(on)

    def option(self, key):
        opts = get_options(self.id)
        if key in opts:
            return opts[key]
        return next((d for k, _, d in self.options if k == key), None)

    def show(self, activity):
        if self.id in HUSHED and settings.get("island_dnd"):  # Do Not Disturb, in the island's Controls
            return
        self.host.post(("show", activity))

    def live(self, activity):
        self.host.post(("live", self.id, activity))

    def start(self):
        """When it's turned on, or the app starts: note what's there already, so it isn't news."""

    def stop(self):
        """When it's turned off: anything it shows goes."""
        self.live(None)

    def poll(self, now):
        raise NotImplementedError

    def command(self, what, data=None):
        """A click on what it shows, run on the plugins' thread."""


# --------------------------------------------------------------------------- notifications
# Your phone's apps by their Android package: Phone Link's copies of their notifications carry only that
PHONE_APPS = {
    "com.google.android.apps.nbu.paisa.user": "Google Pay", "com.phonepe.app": "PhonePe", "net.one97.paytm": "Paytm",
    "com.bt.bms": "BookMyShow", "com.jpl.jiomart": "JioMart", "com.jio.myjio": "MyJio", "in.swiggy.android": "Swiggy",
    "com.application.zomato": "Zomato", "in.amazon.mshop.android.shopping": "Amazon",
    "com.flipkart.android": "Flipkart", "com.ubercab": "Uber", "com.olacabs.customer": "Ola",
    "com.rapido.passenger": "Rapido", "com.olx.southasia": "OLX", "com.android.deskclock": "Clock",
    "com.google.android.deskclock": "Clock", "com.google.android.gm": "Gmail", "com.google.android.youtube": "YouTube",
    "com.google.android.googlequicksearchbox": "Google", "com.google.android.gms": "Google Play services",
    "com.android.vending": "Play Store", "com.google.android.apps.maps": "Google Maps",
    "com.google.android.apps.photos": "Google Photos", "com.instagram.android": "Instagram",
    "com.facebook.katana": "Facebook", "com.facebook.orca": "Messenger", "com.snapchat.android": "Snapchat",
    "com.twitter.android": "X", "com.linkedin.android": "LinkedIn", "com.openai.chatgpt": "ChatGPT",
    "com.shazam.android": "Shazam", "com.spotify.music": "Spotify", "com.netflix.mediaclient": "Netflix",
    "com.truecaller": "Truecaller", "com.sbi.lotusintouch": "SBI YONO", "com.zoho.accounts.oneauth": "Zoho OneAuth",
    "com.xiaomi.mipicks": "GetApps", "com.miui.msa.global": "MIUI",
}
GENERIC = {"com", "org", "net", "ai", "io", "in", "co", "app", "apps", "android", "desktop", "client", "stable", "beta",
           "electron", "microsoft", "google", "windows", "mobile"}  # parts of an app's ID that aren't its name


def app_label(app_id, fallback=""):
    """What an app is called, from its Windows ID: the Start menu's name, WhatsApp for Phone Link's copy of it, a
    phone app by its package, or a tidy name from the ID ("Microsoft.VisualStudioCode", Visual Studio Code). "" for
    Windows' own notices (low disk, AutoPlay) and IDs with no name in them."""
    aid = str(app_id or "")
    low = aid.lower()
    if low.startswith("windows."):  # Windows' own: low disk, AutoPlay, Settings, security
        return ""
    for name, start_id in win.loaded_start_apps():
        if start_id.lower() == low:
            return name
    name, messaging = watch._app(aid)
    if messaging or not aid:
        return name if aid else fallback
    if is_phone(aid):
        if "yourphonecalling" in low:
            return "Phone calls"
        package = aid.split("YourPhoneNotifications_", 1)[1] if "YourPhoneNotifications_" in aid else ""
        if not package:
            return fallback or name
        parts = [p for p in package.split(".") if p and p.lower() not in GENERIC]
        return PHONE_APPS.get(package.lower()) or (_tidy(parts[-1]) if parts else fallback or name)
    if "!" in aid:
        family, tail = aid.split("!", 1)
        if tail.lower().startswith(("http://", "https://")):  # a site put in the Start menu by Edge or Chrome
            host = re.sub(r"^www\.", "", re.sub(r"^https?://", "", tail, flags=re.I).split("/")[0].lower())
            return host.split(".")[0].capitalize() if host else ""
        if "://" in tail:
            return ""  # a browser extension
        aid = family
    parts = [p for p in aid.split("_", 1)[0].split(".")  # a Store app's package, before its publisher's code
             if p and p.lower() not in GENERIC and not re.fullmatch(r"[0-9A-F]{6,}", p)]
    if not parts or (re.fullmatch(r"[A-Za-z0-9]{16,}", parts[-1]) and re.search(r"\d", parts[-1])):
        return ""  # a code, not a name
    return _tidy(parts[-1])


def _tidy(word):
    """An ID's word as a name: "VisualStudioCode" is Visual Studio Code, "opencode" Opencode."""
    word = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", word)
    return word[:1].upper() + word[1:]


def is_phone(app_id):
    return "yourphone" in str(app_id).lower()


def notification_apps(days=180):
    """[{"name", "messaging", "phone", "when", "id"}] for the apps that have notified on this PC lately, newest
    first, one row a name (WhatsApp on the PC and through Phone Link are one). From Windows' own note of it."""
    found = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, watch.SETTINGS_KEY) as root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                app_id = winreg.EnumKey(root, i)
                try:
                    with winreg.OpenKey(root, app_id) as key:
                        added = winreg.QueryValueEx(key, "LastNotificationAddedTime")[0]
                except OSError:
                    continue
                when = (int(added) - watch.FILETIME_1970) / 1e7
                if when < time.time() - days * 86400:
                    continue
                messaging = watch._app(app_id)[1]
                name = app_label(app_id)
                if not name or re.fullmatch(r"\d+|\{?[0-9a-f]{8}-[0-9a-f-]{20,}\}?", name, re.I) or \
                        "notifyicongeneratedaumid" in app_id.lower():
                    continue  # Windows' own, or a tray icon's balloon, with no name to show
                row = found.get(name)
                if row is None or when > row["when"]:
                    found[name] = {"name": name, "messaging": messaging, "phone": is_phone(app_id), "when": when,
                                   "id": app_id}
    except OSError:
        pass
    for name in ("WhatsApp", "Telegram", "Messages"):  # the ones people message you in, even before they notify
        found.setdefault(name, {"name": name, "messaging": True, "phone": False, "when": 0.0, "id": ""})
    # the ones people message you in, then the PC's, then your phone's, the latest first in each
    return sorted(found.values(), key=lambda r: (not r["messaging"], r["phone"], -r["when"]))


def app_on(name, messaging):
    """Whether notifications from this app show in the island: as picked in the Island tab, else the apps people
    message you in."""
    picked = settings.get("island_apps") or {}
    return bool(picked[name]) if name in picked else bool(messaging)


class Notifications(Plugin):
    id, name = "notifications", "Notifications"
    description = "A popup when a notification comes in, from the apps you pick below. Click it to open the app."
    every = 1.5
    options = (("text", "Show what the message says", True),)

    def start(self):
        self.seen = time.time()
        self.added = watch.last_added()
        self.waiting, self.covered = {}, {}

    def poll(self, now):
        found = watch.notifications(self.seen, messages_only=False, limit=10)
        if found:
            self.seen = found[-1]["when"] + 1e-6
        front = (win.front_app_name() or "").lower()
        for n in found:
            self.covered[n["app"]] = max(self.covered.get(n["app"], 0.0), n["when"])
            label = app_label(n.get("app_id", ""), n["app"])
            messaging = watch._app(n.get("app_id", ""))[1]
            if not app_on(label, messaging) or (label.lower() in front and not is_phone(n.get("app_id"))):
                continue  # not picked, or you're looking at that app already
            self._came(Activity(self.id, "notification", {
                "app": label, "app_id": n.get("app_id", ""), "title": watch.spoken_sender(n["from"]) if
                re.fullmatch(r"[\d\s()+.-]+", n["from"].strip()) else n["from"],
                "text": n["text"] if self.option("text") else "", "phone": is_phone(n.get("app_id")),
                "messaging": bool(messaging)}, mood="surprised"))
        # WhatsApp Desktop takes its own notification away before it can be read: Windows' note that it notified
        for app_id, when in watch.last_added().items():
            if when > self.added.get(app_id, 0.0) + 1e-6:
                self.added[app_id] = when
                self.waiting[app_id] = (when, now)
        for app_id, (when, noticed) in list(self.waiting.items()):
            name = watch._app(app_id)[0]
            if self.covered.get(name, 0.0) >= when - 15:
                del self.waiting[app_id]
            elif now - noticed > 1.6:
                del self.waiting[app_id]
                label = app_label(app_id, name)
                if app_on(label, True) and not watch.own_reply(name, when):
                    self._came(Activity(self.id, "notification", {"app": label, "app_id": app_id,
                                                                  "title": "New message", "text": "",
                                                                  "phone": is_phone(app_id), "messaging": False},
                                        mood="surprised"))

    def _came(self, act):
        """A notification for the island: in its Recent panel even while Do Not Disturb hushes its popup, as
        Glance's list keeps them (30 October 2026); only in memory, there."""
        self.host.post(("recent", act))
        self.show(act)

    def command(self, what, data=None):
        if what == "open" and data:
            open_app(data.get("app_id", ""), data.get("app", ""))


def open_app(app_id, name=""):
    """The app a notification came from, brought up as the Start menu would: Phone Link for your phone's. Only an
    app that's in the Start menu is ever started."""
    if is_phone(app_id):
        app_id = "Microsoft.YourPhone_8wekyb3d8bbwe!App"
    known = {aid for _, aid in win.loaded_start_apps()}
    if app_id in known:
        import subprocess
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"], creationflags=win.CREATE_NO_WINDOW)
    elif name:
        try:
            win.launch(name)
        except Exception:
            pass


# --------------------------------------------------------------------------- media
PLAYERS = {"spotify": "Spotify", "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox", "vlc": "VLC",
           "brave": "Brave", "zunemusic": "Media Player", "microsoft.media": "Media Player", "applemusic": "Apple Music",
           "youtube": "YouTube", "amazon": "Amazon Music", "wynk": "Wynk", "gaana": "Gaana"}


def player_name(app_id):
    a = str(app_id or "").lower()
    return next((name for key, name in PLAYERS.items() if key in a), (re.split(r"[!._]", a)[0] or "Media").title())


class Media(Plugin):
    id, name = "media", "Media"
    description = "What's playing, with its cover, and play, pause, next and back when you point at it."
    every = 1.0
    priority = 10
    options = (("art", "Show the cover", True), ("paused", "Stay a while after it's paused", True),
               ("bars", "Bars that move with the music, its lows to its highs", True),
               ("glow", "A glow round it in the cover's colour", True))
    PAUSED_FOR = 25.0  # seconds it stays after a pause, so it can be played again from the island

    def start(self):
        self.loop, self.manager, self.session, self.key, self.art, self.art_key = None, None, None, None, None, None
        self.props, self.props_at, self.paused_at, self.meter, self.level = None, 0.0, None, None, 0.0
        self.last, self.tint = None, None
        if getattr(self, "bands", None) is None:
            import visualizer
            self.bands = visualizer.Bands()

    def _run(self, coro):
        if self.loop is None:
            win._com()
            self.loop = asyncio.new_event_loop()
        return self.loop.run_until_complete(coro)

    def _manager(self):
        if self.manager is None:
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M
            self.manager = self._run(M.request_async())
        return self.manager

    def poll(self, now):
        self._bars(self._look(now))

    def _look(self, now):
        """What's playing now, sent to the island when it changed: True while it plays."""
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status
        try:
            session = self._manager().get_current_session()
        except Exception:
            self.manager = None
            session = None
        if session is None:
            self.session = None
            if self.last is not None:
                self.last = None
                self.live(None)
            return False
        self.session = session
        status = session.get_playback_info().playback_status
        playing = status == Status.PLAYING
        if playing:
            self.paused_at = None
        elif self.paused_at is None:
            self.paused_at = now
        if not playing and self.last is None:
            return False  # paused before it was seen playing (Amazon Music left paused hours ago): nothing to show
        if not playing and (not self.option("paused") or now - self.paused_at > self.PAUSED_FOR):
            if self.last is not None:
                self.last = None
                self.live(None)
            return False
        if self.props is None or now - self.props_at > 3.0 or (self.last and self.last.data.get("playing") != playing):
            try:
                self.props = self._run(session.try_get_media_properties_async())
            except Exception:
                self.props = None
            self.props_at = now
        p = self.props
        title = (p.title or "").strip() if p else ""
        artist = (p.artist or p.album_artist or "").strip() if p else ""
        app = player_name(session.source_app_user_model_id)
        if not title:
            title = app
        tl = session.get_timeline_properties()
        try:
            position, end = tl.position.total_seconds(), (tl.end_time - tl.start_time).total_seconds()
            from datetime import datetime, timezone
            if playing and tl.last_updated_time:
                position += (datetime.now(timezone.utc) - tl.last_updated_time).total_seconds()
        except Exception:
            position, end = 0.0, 0.0
        key = (title, artist, app)
        if self.option("art") and p and key != self.art_key:
            self.art_key, self.art = key, self._cover(p)
            import island_art
            self.tint = island_art.tint(self.art)  # the cover's own colour, for its glow (30 October 2026)
        if playing and now - getattr(self, "out_at", 0.0) > 10.0:  # where it plays, for the card (Glance's)
            self.out_at = now
            try:
                import devices
                self.output = next((o["name"] for o in devices.outputs() if o.get("default")), None)
            except Exception:
                self.output = None
        data = {"title": title, "artist": artist, "app": app, "app_id": session.source_app_user_model_id or "",
                "playing": playing, "position": max(0.0, position), "duration": max(0.0, end), "at": now,
                "art": self.art if self.option("art") else None,
                "tint": self.tint if self.option("art") and self.option("glow") else None,
                "output": getattr(self, "output", None)}
        if self.last is not None and playing and (title, artist) != (self.last.data["title"], self.last.data["artist"]):
            # another song: it peeks for a moment, as Glance's notch shows the next track (30 October 2026)
            way = getattr(self, "way", None)
            self.show(Activity(self.id, "track", {"title": title, "artist": artist, "app": app,
                                                  "art": data["art"], "tint": data["tint"],
                                                  "way": way[0] if way and now - way[1] < 4.0 else None},
                               seconds=2.4))
        same = ("title", "artist", "app", "playing", "duration")
        changed = self.last is None or any(self.last.data[k] != data[k] for k in same) or \
            self.last.data["art"] is not data["art"]
        if not changed:  # where it would be by now: a jump means it was moved along, or back
            old = self.last.data
            expected = old["position"] + (now - old["at"] if old["playing"] else 0.0)
            changed = abs(data["position"] - expected) > 2.5
        if changed:
            self.last = Activity(self.id, "media", data, live=True,
                                 mood=None if self.last is not None else "happy")
            self.live(self.last)
        if playing:
            self.level = self._level()
        return playing

    def _bars(self, playing):
        """The five bars that go with the music (visualizer.py): listening only while it plays and the island shows
        it (host.wanted), and while the Island tab leaves them on."""
        want = playing and bool(self.host.wanted.get(self.id)) and bool(self.option("bars"))
        if want and not self.bands.running:
            self.bands.start()
        elif not want and self.bands.running:
            self.bands.stop()

    def stop(self):
        bands = getattr(self, "bands", None)
        if bands is not None:
            bands.stop()
        self.live(None)

    def _cover(self, props):
        try:
            if not props.thumbnail:
                return None
            from winrt.windows.storage.streams import Buffer, InputStreamOptions
            stream = self._run(props.thumbnail.open_read_async())
            size = int(stream.size)
            if not 0 < size < 8_000_000:
                return None
            buf = Buffer(size)
            got = self._run(stream.read_async(buf, size, InputStreamOptions.READ_AHEAD))
            data = bytes(got)
            import island_art
            return island_art.decode(data, 96)
        except Exception as exc:
            print(f"  island: no cover art ({exc!r})")
            return None

    def _level(self):
        """How loud the speakers are playing, 0 to 1, for the bars."""
        try:
            if self.meter is None:
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
                device = AudioUtilities.GetSpeakers()
                device = getattr(device, "_dev", device)
                self.meter = ctypes.cast(device.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None),
                                         ctypes.POINTER(IAudioMeterInformation))
            return float(self.meter.GetPeakValue())
        except Exception:
            self.meter = None
            return 0.0

    def command(self, what, data=None):
        if self.session is None:
            return
        calls = {"toggle": self.session.try_toggle_play_pause_async, "next": self.session.try_skip_next_async,
                 "previous": self.session.try_skip_previous_async}
        if what in calls:
            if what in ("next", "previous"):
                self.way = (what, time.time())  # the song that comes peeks as the next, or the one before
            try:
                self._run(calls[what]())
            except Exception as exc:
                print(f"  island: {what} didn't work ({exc!r})")
            self.props_at = 0.0  # look again straight away
            self.host.poll_soon(self)
        elif what == "output":  # the next of the sound outputs that are on, from the music card
            try:
                import devices
                outs = devices.outputs()
                i = next((n for n, o in enumerate(outs) if o.get("default")), -1)
                if len(outs) > 1:
                    win.set_output(outs[(i + 1) % len(outs)]["id"])
                self.out_at = 0.0
            except Exception as exc:
                print(f"  island: the output didn't change ({exc!r})")
            self.host.poll_soon(self)
        elif what == "open":
            app = player_name(self.session.source_app_user_model_id)
            try:
                win.focus_app(win.App(app, [self.session.source_app_user_model_id.lower()]))
            except Exception:
                pass


# --------------------------------------------------------------------------- battery
class Battery(Plugin):
    id, name = "battery", "Battery"
    description = "The battery and its percentage when you plug in or unplug, when it's full, and when it runs low."
    every = 2.0
    options = (("percent", "Show the percentage", True), ("while_charging", "Keep showing while it charges", False))

    def start(self):
        b = win_battery()
        self.plugged = b[1] if b else None
        self.percent = b[0] if b else None
        self.warned = set()
        self.kept = None  # what the charging one shows, so it's only sent when it changes

    def poll(self, now):
        b = win_battery()
        if b is None:
            return
        percent, plugged = b
        if self.plugged is not None and plugged != self.plugged:
            self.show(Activity(self.id, "battery", {"percent": percent, "charging": plugged,
                                                    "event": "plugged" if plugged else "unplugged"},
                               mood="happy" if plugged else None, seconds=4.0 if plugged else 2.5))
            self.warned.clear()
        elif plugged and percent >= 100 and (self.percent or 0) < 100:
            self.show(Activity(self.id, "battery", {"percent": percent, "charging": True, "event": "full"},
                               mood="happy", seconds=4.0))
        elif not plugged:
            for level in (10, 20):
                if percent <= level and level not in self.warned:
                    self.warned.update(x for x in (10, 20) if x >= level)
                    self.show(Activity(self.id, "battery", {"percent": percent, "charging": False, "event": "low"},
                                       mood="sad", seconds=6.0))
                    break
        self.plugged, self.percent = plugged, percent
        keep = percent if plugged and percent < 100 and self.option("while_charging") else None
        if keep != self.kept:
            self.kept = keep
            self.live(Activity(self.id, "battery", {"percent": percent, "charging": True, "event": "charging"},
                               live=True) if keep is not None else None)

    def stop(self):
        self.kept = None
        self.live(None)


def win_battery():
    """(percent, plugged in) from Windows, or None on a PC with no battery."""
    try:
        import psutil
        b = psutil.sensors_battery()
    except Exception:
        return None
    return None if b is None else (int(round(b.percent)), bool(b.power_plugged))


# --------------------------------------------------------------------------- timers
class Timers(Plugin):
    """The soonest running timer. In its last URGENT seconds it says so ("urgent": its figures beat and the island
    glows orange), and when it goes off the island rings (30 October 2026): her eyes wide, a shake as a phone rings."""
    id, name = "timers", "Timers"
    description = "A running timer counting down, with a ring for how much is left."
    every = 1.0
    priority = 20  # a timer's about to go off: over the music
    URGENT = 10.0

    def start(self):
        self.shown = None

    def poll(self, now):
        siri = sys.modules.get("siri")
        found = []
        if siri is not None and hasattr(siri, "TIMERS"):
            with siri.TIMERS_LOCK:
                found = [((t.get("label") or "").capitalize(), t["end"], t["secs"]) for t in siri.TIMERS]
        found = [f for f in found if f[1] > now]
        rang = self.shown is not None and self.shown[1] <= now + 0.5  # gone by going off, not by being cancelled
        if not found:
            if self.shown is not None:
                self.shown = None
                self.live(None)
            if rang:
                self.host.post(("fx", "ring"))
            return
        label, end, total = min(found, key=lambda f: f[1])
        urgent = end - now <= self.URGENT
        key = (label, end, urgent)
        if key != self.shown:
            if rang:
                self.host.post(("fx", "ring"))
            self.shown = key
            self.live(Activity(self.id, "timer", {"label": label, "end": end, "total": max(1.0, float(total)),
                                                  "urgent": urgent}, live=True))


# --------------------------------------------------------------------------- the panels (30 October 2026)
class Hub(Plugin):
    """What the island's panels show, after bloom's notch (github.com/SehajveerSingh2005/bloom): opened by a click on
    her eyes (island.DynamicIsland._hub_open), Controls (Wi-Fi, Bluetooth, Do Not Disturb, volume and brightness),
    the calendar with the focus timer, Devices and the shelf. Read here only while one's open, or while there's
    something beside her eyes to keep up (the island says which in host.wanted), and what's slow to read (the radios,
    the brightness, the weather) on a thread of its own, so the music and the notifications never wait for it. A press
    on one of its controls runs here too, the slow ones on a thread of their own."""
    id, name = "hub", "Panels"
    description = ("Click her eyes for Controls (Wi-Fi, Bluetooth, Do Not Disturb, volume and brightness), the "
                   "calendar with a focus timer, your devices and the shelf. Scroll over it for the next one.")
    every = 1.0
    options = (("weather", "The weather at its top, from Open-Meteo at most every half hour", True),)
    SLOW_EVERY, WEATHER_EVERY, MONTH_EVERY, DEVICES_EVERY = 5.0, 1800.0, 60.0, 2.5

    def start(self):
        self.data, self.sent = {}, None
        self.slow_at = self.weather_at = self.month_at = self.devices_at = 0.0
        self.slow = self.weather = None  # the threads reading what's slow, while they run
        self.month_key, self.bright = None, {"want": None, "busy": False}

    def stop(self):
        self.sent = None

    def poll(self, now):
        want = self.host.wanted.get(self.id)
        if not want:
            return
        page = want.get("page") if isinstance(want, dict) else str(want)
        d = self.data
        d["clock"] = time.strftime("%H:%M")  # sent as the minute turns: the time beside her eyes moves with it
        try:
            import psutil
            b = psutil.sensors_battery()
            d["battery"] = (int(round(b.percent)), bool(b.power_plugged)) if b is not None else None
            d["cpu"] = int(round(psutil.cpu_percent(None)))
            d["ram"] = int(round(psutil.virtual_memory().percent))
        except Exception:
            pass
        if page == "controls":
            try:
                d["volume"], d["muted"] = win.volume(), bool(win._endpoint().GetMute())
            except Exception:
                d["volume"] = None
            self._slow(now)
        if self.option("weather"):
            self._weather(now)
        if page == "calendar":
            self._month(now, want.get("month") if isinstance(want, dict) else None)
        if page == "today":  # the to-do list, as Glance's panel has your reminders: a small file on this PC
            try:
                import todo
                d["todo"] = [{"id": i.get("id"), "text": todo.shown(i)} for i in todo.items()][:5]
            except Exception as exc:
                print(f"  island: no to-do list ({exc!r})")
                d["todo"] = []
        if page == "devices" and now - self.devices_at >= self.DEVICES_EVERY:
            self.devices_at = now
            import devices
            outs = devices.outputs()
            levels = devices.batteries() if any(o["bus"] in devices.BLUETOOTH_BUS for o in outs) else {}
            d["outputs"] = [dict(o, battery=devices.battery_for(o, levels)) for o in outs]
            d["drives"] = devices.drives()
        snapshot = dict(d)
        if snapshot != self.sent:
            self.sent = snapshot
            self.host.post(("hub", snapshot))

    def _slow(self, now):
        """The radios and the brightness, every SLOW_EVERY seconds while Controls is open, on a thread of its own:
        Windows takes 100 ms or so to say whether Wi-Fi is on (measured 30 October 2026)."""
        if now - self.slow_at < self.SLOW_EVERY or (self.slow is not None and self.slow.is_alive()):
            return
        self.slow_at = now

        def read():
            for kind in ("wifi", "bluetooth"):
                self.data[kind] = win.radio_on(kind)
            self.data["brightness"] = win.brightness()
            # which network and which device, under their buttons (30 October 2026, the owner's ask)
            import devices
            try:
                self.data["wifi_name"] = devices.wifi_name() if self.data.get("wifi") else None
            except Exception as exc:
                print(f"  island: no Wi-Fi name ({exc!r})")
                self.data["wifi_name"] = None
            try:
                if self.data.get("bluetooth"):
                    self.data["bt_name"] = devices.bluetooth_name(devices.bluetooth_connected(), devices.outputs())
                else:
                    self.data["bt_name"] = None
            except Exception as exc:
                print(f"  island: no Bluetooth name ({exc!r})")
                self.data["bt_name"] = None
            self.host.poll_soon(self)
        self.slow = threading.Thread(target=read, name="island-hub-read", daemon=True)
        self.slow.start()

    def _weather(self, now):
        """The weather where this PC is, from Open-Meteo (web.weather), at most every WEATHER_EVERY seconds and only
        while a panel's open or the weather's beside her eyes: never on this thread, which mustn't wait on the
        network."""
        if now - self.weather_at < self.WEATHER_EVERY or (self.weather is not None and self.weather.is_alive()):
            return
        self.weather_at = now

        def read():
            try:
                import web
                w = web.weather()
                self.data["weather"] = {"temp": w["now"]["temp_c"], "sky": w["now"]["sky"], "place": w["place"],
                                        "feels": w["now"].get("feels_like_c"), "humidity": w["now"].get("humidity"),
                                        "wind": w["now"].get("wind_kmh"), "days": w.get("days") or [],
                                        "hourly": w.get("hourly") or []}
            except Exception as exc:
                print(f"  island: no weather ({exc.__class__.__name__})")
                self.weather_at = time.time() - self.WEATHER_EVERY + 300  # again in five minutes
            self.host.poll_soon(self)
        self.weather = threading.Thread(target=read, name="island-weather", daemon=True)
        self.weather.start()

    def _month(self, now, key):
        """The calendar month shown: how many things are on each of its days, and what's next, from what's kept on
        this PC only (agenda.kept), looked at again every MONTH_EVERY seconds."""
        import datetime as dt
        today = dt.date.today()
        key = tuple(key) if key else (today.year, today.month)
        if key == self.month_key and now - self.month_at < self.MONTH_EVERY:
            return
        self.month_key, self.month_at = key, now
        try:
            import agenda
            year, month = key
            a = dt.datetime(year, month, 1)
            b = dt.datetime(year + (month == 12), month % 12 + 1, 1)
            days = {}
            for o in agenda.kept(a, b):
                if o["start"] and o["start"].year == year and o["start"].month == month:
                    days[o["start"].day] = days.get(o["start"].day, 0) + 1
            n = dt.datetime.now()
            later = [o for o in agenda.kept(n, n + dt.timedelta(days=14)) if not o["all_day"] and o["start"] >= n]
            nxt = {"title": later[0]["title"], "start": later[0]["start"].timestamp()} if later else None
            self.data["month"] = {"key": key, "days": days, "next": nxt}
        except Exception as exc:
            print(f"  island: no calendar ({exc!r})")
            self.data["month"] = {"key": key, "days": {}, "next": None}

    def command(self, what, data=None):
        """A press on a panel's control: volume and mute here, at once; the radios, the brightness and the rest on a
        thread of their own. Then what's shown is read again."""
        if what == "volume":
            win.set_volume(int(data))
            self.data["volume"], self.data["muted"] = int(data), False if int(data) > 0 else self.data.get("muted")
        elif what == "mute":
            win.set_muted(bool(data))
            self.data["muted"] = bool(data)
        elif what == "brightness":
            self._brightness(int(data))
        elif what in ("wifi", "bluetooth", "page", "output", "open_drive", "tick"):
            threading.Thread(target=self._do, args=(what, data), name="island-hub-press", daemon=True).start()
            return
        self.host.poll_soon(self)

    def _brightness(self, level):
        """The screen to level, through WMI, which takes 5 to 70 ms: one setter at a time, the newest level wins,
        so dragging the slider never piles them up."""
        self.bright["want"] = level
        self.data["brightness"] = level
        if self.bright["busy"]:
            return
        self.bright["busy"] = True

        def run():
            try:
                done = None
                while self.bright["want"] != done:
                    done = self.bright["want"]
                    try:
                        win.set_brightness(done)
                    except RuntimeError:
                        self.data["brightness"] = None
                        break
            finally:
                self.bright["busy"] = False
            self.host.poll_soon(self)
        threading.Thread(target=run, name="island-brightness", daemon=True).start()

    def _do(self, what, data):
        try:
            if what in ("wifi", "bluetooth"):
                try:
                    win.set_radio(what, bool(data))
                except RuntimeError as exc:  # Windows wouldn't, and its page is open instead
                    print(f"  island: {exc}")
                self.data[what] = win.radio_on(what)
            elif what == "page" and data in SETTINGS_PAGES:
                win.open_windows_page(data)
            elif what == "output" and data:
                win.set_output(str(data))
                self.devices_at = 0.0
            elif what == "open_drive" and re.fullmatch(r"[A-Z]", str(data or "")):
                os.startfile(f"{data}:\\")
            elif what == "tick" and data is not None:  # one off the to-do list, from Today
                import todo
                todo.tick(int(data))
        except Exception as exc:
            print(f"  island: {what} didn't work ({exc!r})")
        self.host.poll_soon(self)


class Devices(Plugin):
    """A popup when headphones, earbuds or a speaker connect or go, with their battery when Windows has it, when sound
    moves to another output, and when a USB drive goes in (devices.py). Windows says when an output changes
    (devices.Watcher), so it's only read again then, or every LOOK seconds to be sure; the drives are a look at the
    drive letters, a few microseconds."""
    id, name = "devices", "Devices"
    description = ("A popup when headphones, earbuds or a speaker connect or go, with their battery, and when a USB "
                   "drive goes in.")
    every = 2.0
    LOOK, BATTERY_AGAIN = 60.0, 4.0  # a battery is only said a few seconds after a headset connects

    def start(self):
        import devices
        self.watcher = devices.Watcher()
        self.watcher.start()
        self.seen = self.disks = None
        self.looked = 0.0
        self.pending = None  # (the popup, its output's id, when to look at its battery again)

    def stop(self):
        watcher = getattr(self, "watcher", None)  # off from the start: never started
        if watcher is not None:
            watcher.stop()
        self.live(None)

    def poll(self, now):
        import devices
        disks = {d["letter"]: d for d in devices.drives()}
        if self.disks is not None:
            for letter in sorted(disks.keys() - self.disks.keys()):
                d = disks[letter]
                self.show(Activity(self.id, "device", {"event": "drive", "kind": "drive", "name": d["label"],
                                                       "letter": letter, "free": d["free"], "total": d["total"],
                                                       "label": f"USB drive ({letter}:)", "battery": None},
                                   mood="surprised"))
        self.disks = disks
        if self.pending is not None and now >= self.pending[2]:
            act, dev_id, _ = self.pending
            self.pending = None
            out = next((o for o in (self.seen or {}).values() if o["id"] == dev_id), None)
            if out is not None:
                level = devices.battery_for(out, devices.batteries())
                if level is not None and act.data.get("battery") is None:
                    act.data["battery"] = level  # the popup's own data: drawn again, it says it
                    self.host.post(("touch",))
        if not self.watcher.changed.is_set() and now - self.looked < self.LOOK:
            return
        self.watcher.changed.clear()
        self.looked = now
        outs = {o["id"]: o for o in devices.outputs()}
        old, self.seen = self.seen, outs
        if old is None:
            return  # what's on as it starts isn't news
        came = [o for i, o in outs.items() if i not in old and o["kind"] not in ("builtin", "display")]
        gone = [o for i, o in old.items() if i not in outs and o["kind"] not in ("builtin", "display")]
        default = next((o for o in outs.values() if o["default"]), None)
        was = next((o for o in old.values() if o["default"]), None)
        levels = devices.batteries() if any(o["bus"] in devices.BLUETOOTH_BUS for o in came) else {}
        for o in came:
            act = Activity(self.id, "device", {"event": "connected", "kind": o["kind"], "name": o["name"],
                                               "label": "Connected", "battery": devices.battery_for(o, levels),
                                               "bus": o["bus"], "id": o["id"]}, mood="happy")
            self.show(act)
            if act.data["battery"] is None and o["bus"] in devices.BLUETOOTH_BUS:
                self.pending = (act, o["id"], now + self.BATTERY_AGAIN)
        for o in gone:
            self.show(Activity(self.id, "device", {"event": "disconnected", "kind": o["kind"], "name": o["name"],
                                                   "label": "Disconnected", "battery": None, "bus": o["bus"]}))
        if default is not None and was is not None and default["id"] != was["id"] and \
                not any(o["id"] == default["id"] for o in came):
            self.show(Activity(self.id, "device", {"event": "moved", "kind": default["kind"], "name": default["name"],
                                                   "label": "Sound moved to", "battery": None, "bus": default["bus"]}))

    def command(self, what, data=None):
        """A click on a device's popup: a USB drive opens in File Explorer, a sound output opens Sound settings."""
        if what != "open" or not isinstance(data, dict):
            return
        try:
            if data.get("event") == "drive" and re.fullmatch(r"[A-Z]", str(data.get("letter") or "")):
                os.startfile(f"{data['letter']}:\\")
            else:
                win.open_windows_page("ms-settings:sound")
        except Exception as exc:
            print(f"  island: couldn't open it ({exc!r})")


# --------------------------------------------------------------------------- live activities (30 October 2026)
# The owner's pictures of an iPhone's island, and their ask: "dream mode, time, working time, the others ... add
# animation and emotion to all". Each reads only what its module keeps in memory, as the Tasks plugin does, and only
# once that module's been loaded by her: nothing here starts any of them.
def _module(name):
    return sys.modules.get(name)


class Live(Plugin):
    """A plugin that shows one live activity (kind "live") while what it follows is on: data(now) gives its data, or
    None while it's off. It's sent only when it changes. mood: her reaction as it comes up (island_face.MOODS)."""
    every = 1.0
    mood = None

    def start(self):
        self.shown = None

    def data(self, now):
        raise NotImplementedError

    def poll(self, now):
        data = self.data(now)
        if data is not None and data.get("since") is not None:  # sent again each hour, so its clock gets room
            data["hours"] = int(max(0.0, now - data["since"]) // 3600)
        if data == self.shown:
            return
        came = self.shown is None
        self.shown = data
        self.live(Activity(self.id, "live", data, live=True, mood=self.mood if came else None)
                  if data is not None else None)

    def stop(self):
        self.shown = None
        self.live(None)


class Dream(Live):
    """Dream mode while it's open (dream.py): its scene and the song, her eyes asleep with z's rising, and a breathing
    indigo glow; opened, the next scene and Exit, as "next scene" and "exit dream mode" do."""
    id, name = "dream", "Dream mode"
    description = "While dream mode is on: its scene and the song, with Next scene and Exit when you point at it."
    priority = 15  # over the music it plays, under a timer

    def data(self, now):
        dream = _module("dream")
        if dream is None or not dream.is_open():
            return None
        state = dream.state()
        track = state.get("track") or {}
        scene = dream.NAMES.get(state.get("scene"), "Dreaming")
        song = " \u00b7 ".join(str(x) for x in (track.get("title"), track.get("artist")) if x)
        return {"glyph": "moon", "accent": "indigo", "label": "Dream mode", "title": scene, "short": scene,
                "sub": song or "Lo-fi and a pixel scene", "mood": "dream", "aura": "breathe",
                "buttons": [{"name": "next", "label": "Next scene"}, {"name": "exit", "label": "Exit"}]}

    def command(self, what, data=None):
        dream = _module("dream")
        if dream is not None and what in ("next", "exit"):
            (dream.next_scene if what == "next" else dream.close)()
            self.host.poll_soon(self)


class Meeting(Live):
    """Her meeting notes while she takes them (meeting.py): a red recording dot and how long it's been going, as a
    phone shows it's recording; opened, a waveform. She's hearing the call, so it comes before a timer."""
    id, name = "meeting", "Meeting notes"
    description = "While she takes notes in a meeting: a red dot and how long it's been going."
    priority = 25

    def data(self, now):
        m = getattr(_module("meeting"), "NOW", [None])[0]
        if m is None:
            return None
        return {"glyph": "record", "accent": "red", "label": "Meeting notes", "title": "Taking notes",
                "sub": "Say \u201cstop the meeting notes\u201d for a recap", "since": float(m.started), "wave": True}


class Hands(Live):
    """Hand control while it's on (handmouse.py): a waving hand in teal and how long it's been on, her eyes on the
    pointer your hand moves; opened, Stop."""
    id, name = "hands", "Hand control"
    description = "While your hand moves the mouse: how long it's been on, and Stop when you point at it."
    priority = 22

    def start(self):
        super().start()
        self.since = None

    def _mouse(self):
        mouse = (getattr(_module("handmouse"), "NOW", None) or {}).get("mouse")
        return mouse if mouse is not None and mouse.running else None

    def data(self, now):
        if self._mouse() is None:
            self.since = None
            return None
        self.since = self.since or now
        return {"glyph": "hand", "accent": "teal", "label": "Hand control", "title": "Your hand is the mouse",
                "sub": "Pinch to click, hold the pinch to drag", "since": self.since,
                "buttons": [{"name": "stop", "label": "Stop"}]}

    def command(self, what, data=None):
        mouse = self._mouse()
        if what == "stop" and mouse is not None:
            mouse.stop("you stopped it on the island")
            self.host.poll_soon(self)


class Guide(Live):
    """Showing you where to click (showme.py): a pointer tapping in blue and what it's showing you, her reading
    glasses on; opened, Stop, as Esc does."""
    id, name = "guide", "Show me"
    description = "While she shows you where to click: what it's showing you, and Stop when you point at it."
    every = 0.5
    priority = 26

    def _guide(self):
        g = (getattr(_module("showme"), "GUIDE", None) or [None])[0]
        return g if g is not None and not g.stopped.is_set() else None

    def data(self, now):
        g = self._guide()
        if g is None:
            return None
        return {"glyph": "pointer", "accent": "blue", "label": "Show me", "title": str(g.goal or "Where to click"),
                "short": "Showing you", "sub": "Click where she's drawn, or say stop", "mood": "glasses",
                "buttons": [{"name": "stop", "label": "Stop"}]}

    def command(self, what, data=None):
        g = self._guide()
        if what == "stop" and g is not None:
            g.stop()
            self.host.poll_soon(self)


class Break(Live):
    """Her break while it lasts (siri's PAUSE, "take a break for 20 minutes"): two bars and how long it has to go, her
    eyes heavy; she doesn't answer to her name till it's over."""
    id, name = "break", "Her break"
    description = "While she's on a break and not listening for her name: how long it has to go."
    priority = 5

    def data(self, now):
        until = float((getattr(_module("siri"), "PAUSE", None) or {}).get("until") or 0.0)
        if until <= now:
            return None
        return {"glyph": "pause", "accent": "indigo", "label": "On a break", "title": "Not listening for my name",
                "sub": "Say \u201cI\u2019m back\u201d with right Alt", "until": until, "mood": "sleepy"}


class Focus(Live):
    """Her focus timer while a session's on (focus.py): focus or a break, how long's left and a line for it, the
    round, with Pause or Skip and Stop. Its clock moves on the island; it's only sent again as it pauses or moves on."""
    id, name = "focus", "Focus timer"
    description = "While a focus session (a Pomodoro) runs: focus or a break, how long's left, with Pause and Stop."
    priority = 18  # under a timer that's about to go off, over dream mode and the music

    def data(self, now):
        focus = _module("focus")
        s = focus.state(now) if focus is not None else None
        if s is None:
            return None
        resting = s["phase"] == "break"
        if resting:
            buttons = [{"name": "skip", "label": "Skip"}, {"name": "stop", "label": "Stop"}]
        else:
            buttons = [{"name": "resume" if s["paused"] else "pause", "label": "Resume" if s["paused"] else "Pause"},
                       {"name": "stop", "label": "Stop"}]
        return {"glyph": "timer", "accent": "green" if resting else "orange",
                "label": "Break" if resting else "Focus", "title": "Take a break" if resting else "Focusing",
                "sub": f"Round {s['round']}" + (", paused" if s["paused"] else ""),
                "until": s["until"], "left": round(s["left"]) if s["paused"] else None, "length": s["length"],
                "buttons": buttons}

    def command(self, what, data=None):
        focus = _module("focus")
        if focus is None:
            return
        calls = {"pause": focus.pause, "resume": focus.resume, "skip": focus.skip, "stop": focus.stop}
        if what in calls:
            calls[what]()
        elif what == "start":
            focus.start()
        self.host.poll_soon(self)


# --------------------------------------------------------------------------- tasks
CARD_ROWS = 3  # rows a card shows at once; the rest are "+N more"
SHORT = {"waiting_yes": "Needs you", "queued": "Next", "done": "Done", "failed": "Failed", "stopped": "Stopped"}
MOODS = (("waiting_yes", "surprised"), ("failed", "sad"), ("done", "happy"))  # her eyes when one comes to this


class Tasks(Plugin):
    """What she's working on (activity.py), as a card: her plan step by step, a task in an app round by round, a
    background command, install, research or coding job, and a question waiting on your yes. Read from memory only,
    never tasks.db: its 5 s busy wait would stall the music and the notifications on this thread. A press goes to a
    thread of its own (command) for the same reason."""
    id, name = "tasks", "Tasks"
    description = ("What she's working on, live: her plan step by step, a task in an app round by round and work in "
                   "the background, with Stop. Point at it for the list.")
    every = 0.5
    priority = 30  # over a timer and the music: it may be waiting on you

    def start(self):
        self.data, self.states = None, {}

    def poll(self, now):
        items = activity.snapshot(now)
        rows = [self.row(item) for item in items]
        # her turn's own row (run_plan's step i of n, a task in an app round by round) while it runs: her face is up
        # all that time and covered it, so its round and its Stop were never seen (27 October, review). The island
        # shows how far it's got beside her dots and opens the card over her face while you point at it; first in it
        turn = next((r for r in rows if r["key"].startswith("turn:") and r["state"] == "running"), None)
        rows.sort(key=lambda r: r is not turn)
        background = sum(item["origin"] == "task" and item["state"] not in activity.OVER for item in items)
        data = {"rows": rows[:CARD_ROWS], "more": max(0, len(rows) - CARD_ROWS),
                "short": f"{len(rows)} tasks" if len(rows) > 1 else None, "badge": background + (turn is not None),
                "turn": turn}
        states = {item["key"]: item["state"] for item in items}
        came = {state for key, state in states.items() if self.states.get(key) != state}
        self.states = states
        if data == self.data:
            return
        self.data = data
        mood = next((m for state, m in MOODS if state in came), None)
        self.live(Activity(self.id, "card", data, live=True, mood=mood) if rows else None)

    def row(self, item):
        """One of hers as a card's row: its title, its note, how far it's got and its buttons."""
        state, step, total = item["state"], item["step"], item["total"]
        press = {"key": item["key"], "needs": item["needs"]}
        buttons = []
        if state == "waiting_yes" and item["needs"] and item["answers"]:
            # Approve is back (29 October, the owner's ask): it counts only once the pointer has rested on it
            # (island's careful press), only for the question still waiting (activity.press's needs id), and never
            # while she's doing a task in an app, whose clicks are real ones (island_answer, tasks.Store)
            buttons.append({"name": "approve", "label": "Approve", "data": press})
            buttons.append({"name": "deny", "label": "Deny", "data": press})
        elif state in ("running", "queued") and item["stops"]:
            buttons.append({"name": "stop", "label": "Stop", "data": press})
        progress = 1.0 if state == "done" else max(0.0, min(1.0, (step - 1) / total)) \
            if state == "running" and total and step else None
        status = SHORT.get(state) or (f"{step}/{total}" if total and step else "")
        return {"key": item["key"], "title": item["title"], "lines": [item["note"]] if item["note"] else [],
                "status": status, "since": None if status else item["started"], "state": state,
                "progress": progress, "buttons": buttons, "kind": item["kind"]}  # research shows violet on the capsule

    def command(self, what, data=None):
        """Stop, Approve or Deny on a row (activity.press), on a thread of its own: a background task's goes through
        tasks.db, and her question's through siri's controls loop."""
        if what not in ("stop", "approve", "deny") or not isinstance(data, dict):
            return
        threading.Thread(target=activity.press, args=(data.get("key"), what, data.get("needs", "")),
                         name="island-press", daemon=True).start()


# --------------------------------------------------------------------------- what you copy
# a password manager's marks on what it copies, asking that nothing watching the clipboard reads it
EXCLUDE = ("ExcludeClipboardContentFromMonitorProcessing", "Clipboard Viewer Ignore", "CanIncludeInClipboardHistory")
SECRET = re.compile(r"[A-Za-z0-9_\-+/=.~:]{16,}")  # one long word of letters and digits: a key, a code, a password


def shown(text, most=60):
    """The start of what was copied, as the island says it: on one line, and a key, a code or a password only by its
    first four letters."""
    words = " ".join(str(text or "").split())
    if SECRET.fullmatch(words) and re.search(r"\d", words) and re.search(r"[A-Za-z]", words) and \
            not re.match(r"(https?://|www\.)", words):  # a link shows, as Glance's clipboard has them
        return words[:4] + "\u2026"
    return words if len(words) <= most else words[:most - 1].rstrip() + "\u2026"


def copied(look=None, read=None):
    """What's on the clipboard now, as the island says it: {"what": "text" (with "text", its start), "picture" or
    "files"}, or None for nothing to say: a password manager's copy (EXCLUDE), her own, one that's busy, or nothing
    she can name. look() gives (its formats, the process that put them there), as winplatform.clipboard_formats
    does; read() its text."""
    got = (look or win.clipboard_formats)()
    if got is None:
        return None
    formats, pid = got
    if pid == os.getpid() or any(f in EXCLUDE for f in formats if isinstance(f, str)):
        return None
    if 13 in formats:  # CF_UNICODETEXT
        text = shown((read or win.clipboard_text)())
        return {"what": "text", "text": text} if text else None
    if 15 in formats:  # CF_HDROP
        return {"what": "files", "text": ""}
    if any(f in formats for f in (2, 8, 17)):  # CF_BITMAP, CF_DIB, CF_DIBV5: a screenshot, a picture
        return {"what": "picture", "text": ""}
    return None


class Clipboard(Plugin):
    """What you copy, acknowledged for a moment (30 October 2026, the owner's ask, after Glance's notch, which answers
    every shortcut): "Copied" and the start of what it was, or that it was a picture or files. Only when Windows says
    the clipboard changed and it wasn't her (winplatform.OWN_CLIPS: pasting for you, putting back what was there);
    never what a password manager copies; nothing read is kept or sent anywhere.

    And the rest of the shortcuts, the same evening ("when I pasted it didn't respond", the owner): paste, cut, undo,
    redo, save and a screenshot, from the keyboard hook she already has (winplatform.CHORDS), never her own presses.
    A paste says the start of what was copied last, from what's kept here, as reading the clipboard as you paste could
    make the paste fail; undo, redo and save the app they were in. A cut or a screenshot is said as the clipboard
    changes with it, a screenshot only for a picture."""
    id, name = "clipboard", "Copy and shortcuts"
    description = ("A moment's word when you copy, cut, paste, undo, redo, save or take a screenshot, with the start "
                   "of what you copied. Never a password manager's.")
    every = 0.4
    options = (("preview", "Show what you copied", True), ("shortcuts", "Answer paste, undo, save and screenshots",
                                                           True))
    CUT_FOR, SHOT_FOR = 1.5, 90.0  # seconds a cut, and a screenshot, have to reach the clipboard to be said as one

    def start(self):
        self.seq = win.clipboard_sequence()
        self.last = None  # what's on the clipboard, as copied() said it, for a paste
        # the words you copied, newest first, to copy again from the shelf (Glance's clipboard, 31 October 2026):
        # in memory only, never a password manager's (copied), CLIPS at most
        self.clips = []
        self.chords = collections.deque(maxlen=12)
        self.cut_at = self.shot_at = 0.0
        if self._pressed not in win.CHORDS:
            win.CHORDS.append(self._pressed)

    def stop(self):
        if self._pressed in win.CHORDS:
            win.CHORDS.remove(self._pressed)
        self.host.post(("clips", []))
        super().stop()

    def _pressed(self, name):
        """A shortcut pressed (winplatform.chord), inside the keyboard hook: only noted, and looked at soon."""
        self.chords.append((name, time.time()))
        self.host.poll_soon(self, 0.0)

    def poll(self, now):
        answer = bool(self.option("shortcuts"))
        while self.chords:
            name, at = self.chords.popleft()
            if not answer or now - at > 2.0:
                continue
            if name == "cut":
                self.cut_at = at
            elif name == "screenshot":
                self.shot_at = at
            else:
                self._answer(name)
        seq = win.clipboard_sequence()
        if seq == self.seq:
            return
        self.seq = seq
        if seq in win.OWN_CLIPS:
            return
        got = copied()
        if got is not None:
            self.last = dict(got)
            if got["what"] == "text":
                self._keep(now)
            how = "copy"
            if answer and now - self.cut_at < self.CUT_FOR:
                how, self.cut_at = "cut", 0.0
            elif answer and got["what"] == "picture" and now - self.shot_at < self.SHOT_FOR:
                how, self.shot_at = "screenshot", 0.0
            got["how"] = how
            if not self.option("preview") or how == "screenshot":
                got["text"] = ""
            self.show(Activity(self.id, "copied", got, seconds=2.2))

    CLIPS = 12

    def _keep(self, now):
        """The words just copied, kept whole for the shelf's Copied (island.DynamicIsland._hub_shelf) and sent to the
        island; the same again only moves up."""
        try:
            full = str(win.clipboard_text() or "")[:5000]
        except Exception:
            return
        if not full.strip():
            return
        self.clips = [{"full": full, "text": shown(full, 80), "at": now,
                       "link": bool(re.match(r"\s*(https?://|www\.)", full))}] + \
            [c for c in self.clips if c["full"] != full][:self.CLIPS - 1]
        self.host.post(("clips", [dict(c) for c in self.clips]))

    def _answer(self, name):
        """Paste, undo, redo or save, said: a paste with what it was, as copied last; the rest with the app."""
        data = {"how": name, "what": None, "text": ""}
        if name == "paste" and self.last is not None:
            data["what"] = self.last.get("what")
            if self.option("preview"):
                data["text"] = self.last.get("text") or ""
        elif name != "paste":
            try:
                data["text"] = win.front_app_name()
            except Exception:
                pass
        self.show(Activity(self.id, "copied", data, seconds=1.6))


# --------------------------------------------------------------------------- coding agents
class Agents(Plugin):
    """Claude Code, Codex, Cursor and Kiro in her island (coding_agents.py, 31 October 2026, after Glance's): a
    question Claude Code or Codex needs your OK for as a card with Deny and Approve (careful, as her own: the pointer
    must rest on it, and never while she's doing a task in an app), the command one's running and how long, and a
    moment's word when one's waiting on you or done. Off to start with: on, it puts its hooks in the settings of each
    that's on this PC, and off takes them out."""
    id, name = "agents", "Coding agents"
    description = ("Claude Code and Codex ask you here before a command they need your OK for, Approve or Deny; they, "
                   "Cursor and Kiro say what they're running and when they're done. Turning this on adds Harry's "
                   "hooks to their settings (in Codex, trust them once with /hooks).")
    every = 0.5
    default_on = False
    priority = 28  # it may be waiting on you: over all but her own tasks

    def start(self):
        import coding_agents
        self.agents = coding_agents
        self.asked, self.running, self.shown = set(), {}, None
        print(f"  island: coding agents connected: {', '.join(coding_agents.connect_all(True)) or 'none on this PC'}")
        coding_agents.touch()

    def stop(self):
        """Off, or never on (the plugins' thread stops each that's off as it starts): her hooks out, if they're in."""
        import coding_agents
        coding_agents.connect_all(False)
        super().stop()

    def poll(self, now):
        a = self.agents
        a.touch()
        for n in a.notes():
            key = n.get("session") or n.get("project")
            if n["kind"] == "running":
                self.running[key] = n
            elif n["kind"] == "ran":
                self.running.pop(key, None)
            else:
                done = n["kind"] == "done"
                self.running.pop(key, None)
                self.show(Activity(self.id, "card", {
                    "title": f"{n['agent']} {'is done' if done else 'is waiting on you'} \u00b7 {n['project']}",
                    "lines": [n["message"]] if n.get("message") else [], "state": "done" if done else "waiting_yes",
                    "short": "Done" if done else "Waiting"}, mood="happy" if done else "surprised", seconds=5))
        rows = []
        for q in a.questions():
            rows.append({"title": f"{q['agent']} \u00b7 {q['project']}", "lines": [f"{q['tool']}: {q['command']}"],
                         "status": "Needs you", "state": "waiting_yes", "progress": None,
                         "buttons": [{"name": "deny", "label": "Deny", "data": q["id"]},
                                     {"name": "approve", "label": "Approve", "data": q["id"], "careful": True}]})
        for n in list(self.running.values()):
            if now - n.get("at", now) > 600:  # its end never came: gone
                self.running.pop(n.get("session") or n.get("project"), None)
                continue
            rows.append({"title": f"{n['agent']} \u00b7 {n['project']}", "lines": [f"$ {n['command']}"],
                         "status": "", "since": n.get("at"), "state": "running", "progress": None})
        fresh = {q["id"] for q in a.questions()} - self.asked
        self.asked |= fresh
        key = tuple((r["title"], tuple(r["lines"]), r["state"]) for r in rows)
        if key == self.shown:
            return
        self.shown = key
        if not rows:
            self.live(None)
            return
        waiting = sum(r["state"] == "waiting_yes" for r in rows)
        self.live(Activity(self.id, "card", {"rows": rows, "short": f"{waiting} needs you" if waiting else
                                             "Running"}, live=True, mood="surprised" if fresh else None))

    def command(self, what, data=None):
        if what in ("approve", "deny") and data:
            self.agents.answer(data, what == "approve")
            self.host.poll_soon(self, 0.0)


# --------------------------------------------------------------------------- the volume and the brightness
LEVEL_NEWS = collections.deque(maxlen=16)  # (what, level, muted) as edges.py saw them change, for Levels


def level_news(what, level, muted=False):
    """The volume or the brightness changed (edges.Levels saw it): shown in the notch (Levels). True if it will be;
    False with the island not showing them, when the edge's own slider should."""
    plugin = Levels.running
    if plugin is None or not settings.get("popup"):
        return False
    LEVEL_NEWS.append((what, int(level), bool(muted)))
    plugin.host.poll_soon(plugin, 0.0)
    return True


class Levels(Plugin):
    """The volume or the brightness as it changes, in the notch, the way Glance's shows it (30 October 2026, the
    owner's ask): its glyph, a slim bar and the level beside her eyes, and her light along her bottom as far as it's
    set. Read by the edges' own watcher (edges.Levels, level_notch), which hands each change here (level_news), so
    nothing's read twice; the newest of each, as a held key sends many."""
    id, name = "levels", "Volume and brightness"
    description = ("The volume or the brightness as it changes, from the keys or anywhere, in the notch, with her "
                   "light along her bottom as far as it's set.")
    every = 5.0
    running = None  # the one that's on, for level_news

    def start(self):
        LEVEL_NEWS.clear()
        Levels.running = self

    def stop(self):
        if Levels.running is self:
            Levels.running = None
        super().stop()

    def poll(self, now):
        newest = {}
        while LEVEL_NEWS:
            what, level, muted = LEVEL_NEWS.popleft()
            newest[what] = (level, muted)
        for what, (level, muted) in newest.items():
            self.show(Activity(self.id, "level", {"what": what, "level": level, "muted": muted}, seconds=1.6))


PLUGINS = (Tasks, Agents, Notifications, Clipboard, Levels, Media, Battery, Timers, Dream, Meeting, Hands, Guide, Break,
           Focus, Devices, Hub)


def priority(plugin_id):
    """How much what plugin_id keeps on the island matters next to the others' (Plugin.priority): tasks, showing you
    where to click, meeting notes, hand control, a timer, the focus timer, dream mode, music, her break, then the
    battery."""
    return next((cls.priority for cls in PLUGINS if cls.id == plugin_id), 0)


class Runner:
    """The plugins' thread: each on plugin polled when it's due, what they say kept for the island to take
    (take), clicks run here (do), and the island told when a full-screen app is up or the screen in front changed."""

    def __init__(self):
        self.events = queue.Queue()
        self.jobs = queue.Queue()
        self.plugins = [cls(self) for cls in PLUGINS]
        self.due = {p.id: 0.0 for p in self.plugins}
        self.on = {}
        self.busy, self.area, self.light = None, None, None
        # what the island wants read while it shows it, by plugin id: the Hub's panel that's open, and its month
        self.wanted = {}
        self.thread = threading.Thread(target=self._loop, name="island-plugins", daemon=True)
        self.stopped = False

    def start(self):
        self.thread.start()

    def stop(self):
        self.stopped = True

    def post(self, event):
        self.events.put(event)

    def take(self):
        out = []
        try:
            while True:
                out.append(self.events.get_nowait())
        except queue.Empty:
            return out

    def do(self, plugin_id, what, data=None):
        self.jobs.put((plugin_id, what, data))

    def poll_soon(self, plugin, after=0.3):
        self.due[plugin.id] = min(self.due.get(plugin.id, 0.0), time.time() + after)

    def want(self, plugin_id, what=None):
        """The island wants plugin_id read while it shows it (what: what of it, as the Hub's open panel), or no more
        with what None; read straight away when that changes."""
        if what is None:
            self.wanted.pop(plugin_id, None)
            return
        if self.wanted.get(plugin_id) != what:
            self.wanted[plugin_id] = what
            self.due[plugin_id] = 0.0

    def plugin(self, plugin_id):
        return next((p for p in self.plugins if p.id == plugin_id), None)

    def _loop(self):
        win._com()
        last_screen = 0.0
        while not self.stopped:
            now = time.time()
            try:
                while True:
                    pid, what, data = self.jobs.get_nowait()
                    p = self.plugin(pid)
                    if p is not None:
                        p.command(what, data)
            except queue.Empty:
                pass
            except Exception as exc:
                print(f"  island: a click failed ({exc!r})")
            shown = bool(settings.get("popup"))  # with the popup off in Settings they all rest
            for p in self.plugins:
                try:
                    on = shown and p.enabled()
                    if on != self.on.get(p.id):
                        self.on[p.id] = on
                        p.start() if on else p.stop()
                    if on and now >= self.due[p.id]:
                        self.due[p.id] = now + p.every
                        p.poll(now)
                    elif on and p.id == "media" and getattr(p, "last", None) is not None and \
                            p.last.data.get("playing"):
                        p.level = p._level()  # the bars move with the music between looks
                except Exception as exc:
                    self.due[p.id] = now + 10  # a plugin that fails waits, and never stops the others
                    print(f"  island: {p.name} failed ({exc!r})")
            if now - last_screen > 2.0:
                last_screen = now
                self._screen()
            time.sleep(0.1)

    def _screen(self):
        state = ctypes.c_int()
        try:
            ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state))
            busy = state.value in FULL_SCREEN
        except Exception:
            busy = False
        if busy != self.busy:
            self.busy = busy
            self.post(("busy", busy))
        try:
            area = win.work_area()
        except Exception:
            area = None
        if area != self.area:
            self.area = area
            self.post(("place", area))
        try:
            light = not win.dark_mode()
        except Exception:
            light = False
        if light != self.light:
            self.light = light
            self.post(("light", light))
