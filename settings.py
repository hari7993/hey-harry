"""Window and model settings, saved to %APPDATA%\\Hey Harry\\settings.json (the Mac build used NSUserDefaults)."""
import json
import os
import threading

from winplatform import APPDATA_DIR

PATH = os.path.join(APPDATA_DIR, "settings.json")
DEFAULTS = {
    "mode": "ptt",
    "mic": "",
    "keep_on_top": False,
    # free, the same model as siri.FAST_MODEL. It was space-bunny-free on OpenCode Zen, gone (410) since 11 October,
    # so a fresh install failed every request until Settings refreshed the model list
    "llm_model": "kilo/nvidia/nemotron-3-ultra-550b-a55b:free",
    # speech to text on this PC: parakeet or whisper (nemotron, which wrote as you talked, taken out 31 October 2026)
    "stt_engine": "parakeet",
    # a provider's ears for what's plainly said to her, as "sarvam:saaras:v4" (hearing.py), or "" for this PC's alone;
    # and what they're for: "all" (commands and dictation) or "dictation"
    "ears": "",
    "ears_use": "all",
    # how long she waits for you to finish before answering: patient, even or quick (speech.Listener.WAITS)
    "turn_wait": "patient",
    "echo_cancel": True,  # the mic in Windows' speech mode, so she hears you over videos and music
    "talk_over": True,  # in speech mode the mic stays on while she talks, so what you say over her is heard
    "popup": True,  # the pill at the bottom of the screen while she listens, thinks and talks
    "name": "",  # what she calls you
    "nickname": "",  # what you call her, when it isn't Harry: identity.py, changed with identity.rename
    "welcome": True,  # hello when you sign in or come back to the laptop, and what she can do
    "met": False,  # she's introduced herself since her memory was last started fresh, see backup.py --fresh
    "onboarded": False,  # her walkthrough's been through once (onboarding.py); Settings > Walkthrough shows it again
    # Full access (Settings > Safety, siri.full_access_ok): she sends a message or installs what you ask by name
    # without asking first. Off unless you turn it on in the window; full_access_until: when it goes off by itself
    "full_access": False,
    "full_access_until": 0,
    "voice_id": "off",  # only your voice: off, learning (scores, turns nobody away) or on, see voiceid.py
    # quick decisions: off, shadow (logged only) or on (lets plain room talk go), see decider.py. On since its "sure it
    # isn't for her" was right 16 times in 18 on 8 October, while she spoke or acted on 22 of 88 room-talk turns
    "decider": "on",
    # a routine started by words close in meaning to its own, said by name: off, shadow (only logged, the default
    # from 27 October until her log shows where the bar should be) or on, see siri.paraphrased
    "paraphrase_routines": "shadow",
    "voice": "",  # her Fish Audio voice, an ID from VOICES or a pasted fish.audio link. Empty: the first in VOICES
    "vision": True,  # she may look at the screen when you ask about it, see siri.see()
    # her own browser (herbrowser.py, 31 October 2026): her jobs on websites work in a Chrome of her own, out of your
    # way, signed in wherever you've signed it in; off, they work on your screen as before
    "own_browser": True,
    # her eyes on you through the laptop's camera, and her ears for claps and snaps (cues.py, 29 October 2026): she
    # welcomes you back when she sees you, and does what your rules say ("when I clap, start work mode"). Off till
    # you turn it on, in Settings > Let her see you or by saying "turn on your camera"
    "cues": False,
    # building into herself and healing herself (selfwork.py, 29 October 2026): the model she builds with, as
    # "anthropic/claude-opus-5-5" ("" for the answer model's), and whether she fixes her own faults by herself
    "builder_model": "",
    "self_heal": True,
    # her eyes on the screen all the time (screen_watch, 27 October 2026, the owner's ask): she reads the window in
    # front on this PC so your questions come with what's on it, and with commentary on, glances at it now and then
    # and speaks up when something there needs you. Never password or payment pages, or private windows
    "screen_watch": True,
    "screen_commentary": True,
    "heads_ups": True,  # she mentions what needs you: messages, a low battery, a nearly full drive, see watch.py
    "notifications": True,  # she may read Windows' notifications, for heads-ups and "any new messages?"
    # a background task's progress on your phone (siri.progress_to): "asked", only for those asked from the phone, or
    # "all", every one while you're paired, as one message each that's edited as it goes
    "phone_progress": "asked",
    "learning": True,  # she looks back over turns to learn, Hermes Agent's learning loop, see siri.review()
    # no "Hey Harry" needed: anything said that could be a request goes to the answer model, which decides if it was
    # for her or for someone else in the room, see siri.route()
    "no_name": False,
    "call_aware": True,  # during WhatsApp/Teams/Zoom/browser calls, unnamed speech is for the call; say Harry/Jarvis
    "spoken_answers": True,  # a question, even "Google when is...", is looked up and answered out loud, see siri
    # the popup: "island" (her face at the top, like Nixi's, with plugins: island.py), "card" (the iPhone Dynamic
    # Island card, bubble.Island) or "pill" (the Siri pill at the bottom)
    "popup_style": "island",
    # the island (island.py), all changed in the Island tab
    # capsule (27 October 2026: a floating glass capsule with her glowing eyes, the owner's pick from the mockups) or
    # pill (the black pill with Nixi's eyes it was before)
    # panel (28 October 2026, the owner's pick): the capsule, but her turns open into a box, what
    # you said in a bubble, her answer, how long it took and Try again
    "island_style": "panel",
    # eyes (Nixi's, her own: the owner wants them, 28 October 2026), orb (a ring of dashes, there to pick) or
    # wave (the Siri wave, the pill's alone)
    "island_face": "eyes",
    "island_theme": "paper",  # paper (white, her window's look, 29 October 2026), system, light, dark or amoled
    "island_border": False,  # a thin line round it
    "island_align": "center",  # left, center or right of the screen's top
    # hanging from the top of the screen like a notch, in the same glass, no gap above it (28 October 2026, the owner's
    # pick): the capsule and the answer card both. Off, the capsule floats a little under the top again
    "island_drop": True,
    "island_x": 0,  # px across from there
    "island_y": 8,  # px down from the top of the screen
    "island_scale": 100,  # its size, percent
    "island_radius": 22,  # its corners, px
    "island_always": True,  # her eyes stay at the top of the screen when she isn't doing anything
    "island_hide_fullscreen": True,  # not over a full-screen game, video or presentation, but for her own turns
    "island_auto_hide": 5,  # seconds a popup (a notification, the battery) stays up
    # the island's panels (30 October 2026, after bloom's notch): the one open last, Do Not Disturb (no popups from
    # outside while it's on), what sits beside her eyes while nothing's on ("" for nothing, as the owner had it from
    # 27 October, else some of weather, battery, cpu and ram, as "weather,battery"), and the shelf: kept for next
    # time or not, and what's on it
    "island_panel": "controls",
    "island_dnd": False,
    "island_status": "",
    "island_shelf_keep": False,
    "island_shelf": [],
    # her focus timer, a Pomodoro (focus.py, 30 October 2026): minutes of a round's focus, and of its break
    "focus_minutes": 25,
    "break_minutes": 5,
    # her edges of the screen (edges.py, 30 October 2026, after bloom): the volume's slider at the left edge and the
    # brightness's at the right, out when the pointer rests against it; out for a moment by itself when either
    # changes (level_hud); and round corners at the top of the screen, as a MacBook's, off to start with
    "edge_volume": True,
    "edge_brightness": True,
    "level_hud": True,
    # a change shown in the island instead, with her light along her bottom, as Glance's notch shows it (30 October
    # 2026): the edge's slider shows a change only with this off
    "level_notch": True,
    "island_corners": False,
    # the island's, the dock's and the edges' type (bubble.glance_face): "figtree", the owner's pick on 31 October
    # 2026; "glance", Glance's Plus Jakarta Sans and Poppins, theirs the day before; or "segoe", Windows' own
    "island_font": "figtree",
    # her light (island_light, 30 October 2026, after Glance's notch): lighting up in its colour as something comes
    "island_light": True,
    # her dock (dock.py, 30 October 2026, after bloom): off to start with; how it hides (smart: out of the way of the
    # window in front, peek: till the pointer's at the bottom of the screen, fixed: never); whether it hides Windows'
    # taskbar while it's on; and its pins, None till they're first read from the taskbar's
    "dock": False,
    "dock_mode": "smart",
    "dock_replace_taskbar": False,
    "dock_pins": None,
    "island_plugins": {},  # plugin ID: on or off (island_plugins.PLUGINS), missing ones as the plugin says
    "island_plugin_options": {},  # plugin ID: {option: value}
    "island_apps": {},  # app name: whether its notifications show, missing ones on for apps people message you in
}
# Fish Audio voices that speak well on its free model, for Settings > Voice: (name, ID, what she sounds like)
VOICES = (  # the first is the default when none is picked, so Hannah stays first
    ("Hannah", "9a9cf47702da476aa4629e2506d4a857", "friendly, clear"),
    ("Sarah", "933563129e564b19a115bedd57b7406a", "soft, gentle"),
    ("Laura", "e3cd384158934cc9a01029cd7d278634", "warm, calm"),
    ("Miku", "75cea27272464f8e8a529c9105d40297", "Indian accent"),
    ("Assistant", "fa97330bb80549fbb3cf84a1c421d70c", "crisp, American"),
    ("Ethan", "536d3a5e000945adb7038665781a4aca", "calm, a man"),
    # Her voice made on this PC (kokoro.py): free for good, used for Fish voices too once Fish's free model ends
    ("Harry on this PC", "kokoro:af_heart", "warm, American, offline, free for good"),
    ("Harry on this PC, Bella", "kokoro:af_bella", "American, offline, free for good"),
    ("Harry on this PC, Emma", "kokoro:bf_emma", "British, offline, free for good"),
    ("Harry on this PC, Alpha", "kokoro:hf_alpha", "an Indian voice, offline, free for good"),
    ("Harry on this PC, Beta", "kokoro:hf_beta", "an Indian voice, offline, free for good"),
    ("Harry on this PC, a man", "kokoro:am_michael", "American, offline, free for good"),
    ("Harry on this PC, a British man", "kokoro:bm_george", "British, offline, free for good"),
    # Windows' own voices: offline, instant, no Fish account needed
    ("Windows Heera", "onecore:MSTTS_V110_enIN_HeeraM", "offline, Indian English"),
    ("Windows Ravi", "onecore:MSTTS_V110_enIN_RaviM", "offline, Indian English, a man"),
    ("Windows Mark", "onecore:MSTTS_V110_enUS_MarkM", "offline, American, a man"),
    ("Windows Zira", "onecore:MSTTS_V110_enUS_ZiraM", "offline, American"),
    ("Windows David", "onecore:MSTTS_V110_enUS_DavidM", "offline, American, a man"),
)
ENV = {"llm_model": "OPENCODE_MODEL"}  # a value in .env wins, like the keys do

_lock = threading.Lock()
_data = None


def _load():
    global _data
    if _data is None:
        try:
            with open(PATH, encoding="utf-8") as f:
                _data = json.load(f)
        except (OSError, ValueError):
            _data = {}
    return _data


def get(name):
    env = ENV.get(name)
    if env and os.getenv(env):
        return os.getenv(env)
    with _lock:
        value = _load().get(name)
    if value is None or (value == "" and name in ENV):  # an emptied model box means the default model
        return DEFAULTS.get(name)
    return value


def put(name, value):
    with _lock:
        data = _load()
        data[name] = value
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, PATH)
