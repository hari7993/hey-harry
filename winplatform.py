"""Windows versions of everything the Mac build did with AppleScript, afplay, pbcopy and pmset."""
import asyncio
import contextlib
import ctypes
import json
import os
import re
import struct
import subprocess
import sys
import threading
import time
import winreg
from ctypes import wintypes
from functools import lru_cache
from urllib.parse import quote

import agentdesktop as _desktop


# --------------------------------------------------------------------------- the C++ runtime, first
def _system_cpp_runtime():
    """Windows' own C++ runtime, loaded before any package can load its older copy. winrt brings MSVCP140.dll
    14.29, and onnxruntime and sherpa-onnx, built with a newer one, crash in that one (a mutex, 0xc0000005) if it's
    loaded first: once a DLL of that name is in the process, every later load of the name gets it. On 22 October
    the island's media plugin imported winrt before the speech models loaded, and she crashed 4 seconds in. The
    runtime is backward compatible, so winrt runs on the newer one."""
    path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "msvcp140.dll")
    try:
        if os.path.exists(path):
            ctypes.WinDLL(path)
    except Exception:  # not Windows (the tests' stand-ins), or a runtime Windows won't load: as it was
        pass


_system_cpp_runtime()

# --------------------------------------------------------------------------- paths
# On 8 Oct `python -m unittest` from the repo root imported siri through the old hand checks (test_listen.py and co.)
# before tests/support.py had moved %APPDATA%, and the test run wrote 982 turns into her real history, 1,488 runs into
# the task log, 88 dictations, and an empty contacts book over three real people. So in a test run her real folders
# are refused outright: tests/support.py sets HEYHARRY_TESTING to the real folders before it imports anything, and a
# test runner that started without it (python -m unittest, pytest, an editor's) is told apart by what it ran. A normal
# run of hers is neither, and for her this is one dict lookup.
RUNNERS = ("pytest", "_pytest", "unittestadapter", "teamcity")  # an editor's runner loads one of these first


def _test_run():
    main = sys.modules.get("__main__")
    started = (getattr(getattr(main, "__spec__", None), "name", None) or "").split(".")[0]
    return started in ("unittest", "pytest") or any(name in sys.modules for name in RUNNERS)


# Worked out once, here: a runner is always loaded before it imports her code. Asked again on every use, a library
# that imported pytest inside her running app would have made her voice and decider folders raise from then on.
TEST_RUN = _test_run()


# She was Jev till 28 October 2026, in a program called Hey Jev: her folders, the keys in Credential Manager, the
# start-up entry and the one-at-a-time lock go by Hey Harry from then on, moved from the old names the first time
NAME, OLD_NAME = "Hey Harry", "Hey Jev"


def own_data(path):
    """path, unless this is a test run and path is in her real data, which raises instead."""
    real = os.environ.get("HEYHARRY_TESTING")
    if real is None and not TEST_RUN:
        return path
    home = os.path.expanduser("~")
    bases = (real or os.pathsep.join((os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")))).split(
        os.pathsep) + [os.path.join(home, "AppData", "Roaming"), os.path.join(home, "AppData", "Local"), home]
    target = os.path.normcase(os.path.abspath(path))
    for base in filter(None, bases):
        for name in (NAME, OLD_NAME):
            mine = os.path.normcase(os.path.abspath(os.path.join(base, name)))
            if target == mine or target.startswith(mine + os.sep):
                raise RuntimeError(f"a test run reached her real data ({path}): import tests.support first, and run "
                                   "the suite as python -m unittest discover -s tests -t .")
    return path


MOVED = []  # her folders moved from Hey Jev's as she started this time (identity.moved_on tells her notes her name)


def home(var="APPDATA"):
    """Her folder in %APPDATA% or %LOCALAPPDATA% (var): Hey Harry's, or Hey Jev's while that's the one there is
    (move_home moves it), so everything that reads or writes her data agrees on where it is, and nothing new is made
    beside an old folder that still has to move."""
    base = os.environ.get(var) or os.path.expanduser("~")
    new, old = own_data(os.path.join(base, NAME)), own_data(os.path.join(base, OLD_NAME))
    return old if os.path.isdir(old) and not os.path.exists(new) else new


def _running():
    """True while Harry or Hey Jev is open: each holds its lock (LOCKS) for as long as it runs."""
    for name in LOCKS:
        handle = kernel32.OpenMutexW(0x00100000, False, f"Local\\{name}")  # SYNCHRONIZE
        if handle:
            kernel32.CloseHandle(handle)
            return True
    return False


def move_home():
    """Hey Jev's folders as Hey Harry's, renamed in place so nothing's copied: only from app.py as she starts, before
    anything else reads her data, and never while Harry or Hey Jev is open (a second start, or the old app still
    running: its files would go from under it). One that can't be moved yet, a file in it held open, stays where it
    is and is used there till the next start."""
    global APPDATA_DIR, LOG_DIR
    if _running():
        return
    for var in ("APPDATA", "LOCALAPPDATA"):
        base = os.environ.get(var) or os.path.expanduser("~")
        new, old = own_data(os.path.join(base, NAME)), own_data(os.path.join(base, OLD_NAME))
        if os.path.isdir(old) and not os.path.exists(new):
            try:
                os.rename(old, new)
                MOVED.append(new)
                print(f"moved {old} to {new}")
            except OSError as exc:
                print(f"couldn't move {old} to {new} yet, using it as it is: {exc!r}")
    APPDATA_DIR, LOG_DIR = home("APPDATA"), os.path.join(home("LOCALAPPDATA"), "Logs")
    try:  # her log and your dictations under their old names (Hey Jev.log): carried on under the new ones
        for name in os.listdir(LOG_DIR):
            new = os.path.join(LOG_DIR, name.replace(OLD_NAME, NAME, 1))
            if name.startswith(OLD_NAME) and not os.path.exists(new):
                os.rename(os.path.join(LOG_DIR, name), new)
    except OSError as exc:
        print(f"couldn't rename her logs: {exc!r}")


APPDATA_DIR = home("APPDATA")
LOG_DIR = os.path.join(home("LOCALAPPDATA"), "Logs")
os.makedirs(APPDATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


def log_path(name):
    """Where the Mac build used ~/Library/Logs/<name>."""
    return os.path.join(LOG_DIR, name)


CREATE_NO_WINDOW = 0x08000000  # no console flashing up when the app runs without one
_ps = os.path.join(os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows",
                   "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
POWERSHELL = _ps if os.path.exists(_ps) else "powershell"  # full path, the shortcut's PATH can't always find it

# --------------------------------------------------------------------------- Win32
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ole32 = ctypes.WinDLL("ole32")
dwmapi = ctypes.WinDLL("dwmapi")
version = ctypes.WinDLL("version")
powrprof = ctypes.WinDLL("powrprof")
shell32 = ctypes.WinDLL("shell32")

HWND, DWORD, BOOL, UINT, LONG = wintypes.HWND, wintypes.DWORD, wintypes.BOOL, wintypes.UINT, wintypes.LONG
WNDENUMPROC = ctypes.WINFUNCTYPE(BOOL, HWND, wintypes.LPARAM)


class RECT(ctypes.Structure):
    _fields_ = [("left", LONG), ("top", LONG), ("right", LONG), ("bottom", LONG)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", DWORD)]


def _sig(fn, args, res=BOOL):
    fn.argtypes, fn.restype = args, res


_sig(user32.EnumWindows, [WNDENUMPROC, wintypes.LPARAM])
_sig(user32.EnumChildWindows, [HWND, WNDENUMPROC, wintypes.LPARAM])
_sig(user32.GetWindowThreadProcessId, [HWND, ctypes.POINTER(DWORD)], DWORD)
_sig(user32.IsWindowVisible, [HWND])
_sig(user32.IsIconic, [HWND])
_sig(user32.IsWindow, [HWND])
_sig(user32.IsWindowEnabled, [HWND])
_sig(user32.GetWindow, [HWND, UINT], HWND)
_sig(user32.GetAncestor, [HWND, UINT], HWND)
_sig(user32.GetWindowLongW, [HWND, ctypes.c_int], LONG)
_sig(user32.SetWindowLongW, [HWND, ctypes.c_int, LONG], LONG)
_sig(user32.GetWindowTextLengthW, [HWND], ctypes.c_int)
_sig(user32.GetWindowTextW, [HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int)
_sig(user32.GetClassNameW, [HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int)
_sig(user32.ShowWindow, [HWND, ctypes.c_int])
_sig(user32.SetWindowPos, [HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, UINT])
_sig(user32.PostMessageW, [HWND, UINT, wintypes.WPARAM, wintypes.LPARAM])
_sig(user32.SendMessageTimeoutW, [HWND, UINT, wintypes.WPARAM, wintypes.LPCWSTR, UINT, UINT,
                                  ctypes.POINTER(ctypes.c_size_t)], wintypes.LPARAM)
_sig(user32.GetForegroundWindow, [], HWND)
_sig(user32.GetWindowRect, [HWND, ctypes.POINTER(RECT)])
_sig(user32.SetForegroundWindow, [HWND])
_sig(user32.BringWindowToTop, [HWND])
_sig(user32.AttachThreadInput, [DWORD, DWORD, BOOL])
_sig(user32.SwitchToThisWindow, [HWND, BOOL], None)
_sig(user32.FindWindowW, [wintypes.LPCWSTR, wintypes.LPCWSTR], HWND)
_sig(user32.LockWorkStation, [])
_sig(user32.MonitorFromWindow, [HWND, DWORD], wintypes.HANDLE)
_sig(user32.GetMonitorInfoW, [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)])
_sig(user32.OpenClipboard, [HWND])
_sig(user32.EmptyClipboard, [])
_sig(user32.CloseClipboard, [])
_sig(user32.SetClipboardData, [UINT, wintypes.HANDLE], wintypes.HANDLE)
_sig(kernel32.GlobalAlloc, [UINT, ctypes.c_size_t], ctypes.c_void_p)
_sig(kernel32.GlobalLock, [ctypes.c_void_p], ctypes.c_void_p)
_sig(kernel32.GlobalUnlock, [ctypes.c_void_p])
_sig(kernel32.GlobalFree, [ctypes.c_void_p], ctypes.c_void_p)
_sig(kernel32.OpenProcess, [DWORD, BOOL, DWORD], wintypes.HANDLE)
_sig(kernel32.QueryFullProcessImageNameW, [wintypes.HANDLE, DWORD, wintypes.LPWSTR, ctypes.POINTER(DWORD)])
_sig(kernel32.CloseHandle, [wintypes.HANDLE])
_sig(kernel32.GetCurrentThreadId, [], DWORD)
_sig(kernel32.CreateMutexW, [ctypes.c_void_p, BOOL, wintypes.LPCWSTR], wintypes.HANDLE)
_sig(kernel32.OpenMutexW, [DWORD, BOOL, wintypes.LPCWSTR], wintypes.HANDLE)
_sig(dwmapi.DwmGetWindowAttribute, [HWND, DWORD, ctypes.c_void_p, DWORD], ctypes.c_long)
_sig(version.GetFileVersionInfoSizeW, [wintypes.LPCWSTR, ctypes.POINTER(DWORD)], DWORD)
_sig(version.GetFileVersionInfoW, [wintypes.LPCWSTR, DWORD, DWORD, ctypes.c_void_p])
_sig(version.VerQueryValueW, [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(UINT)])
_sig(powrprof.SetSuspendState, [wintypes.BOOLEAN, wintypes.BOOLEAN, wintypes.BOOLEAN], wintypes.BOOLEAN)
_sig(ole32.CoInitializeEx, [ctypes.c_void_p, DWORD], ctypes.c_long)

GW_OWNER, GA_ROOT, GA_ROOTOWNER, GWL_EXSTYLE = 4, 2, 3, -20
WS_EX_TOPMOST, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW = 0x8, 0x20, 0x80
WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x80000, 0x08000000
SW_HIDE, SW_MINIMIZE, SW_RESTORE = 0, 6, 9
SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x10, 0x40
HWND_TOPMOST = HWND(-1)
HWND_BROADCAST = HWND(0xFFFF)
WM_CLOSE, WM_SYSCOMMAND, WM_SETTINGCHANGE = 0x10, 0x112, 0x1A
SC_MONITORPOWER = 0xF170
SMTO_ABORTIFHUNG = 0x2
DWMWA_CLOAKED, DWMWA_EXTENDED_FRAME_BOUNDS = 14, 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MONITOR_DEFAULTTOPRIMARY = 1

# Windows parts that look like app windows but must never be closed or minimised as one
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Windows.UI.Core.CoreWindow"}
# and the ones agent-desktop doesn't list, so never reads (WINDOW_NOT_FOUND): the desktop, the taskbar, Search and
# Explorer's own flyouts. Not asked for at all: on 4 November 2026 the screen watch ran agent-desktop on them every
# minute, as each was in front, only to be told no such window
UNLISTED_CLASSES = SHELL_CLASSES | {"XamlExplorerHostIslandWindow_WASDK", "XamlExplorerHostIslandWindow"}
# Never force-quit these: the taskbar, the frame UWP apps live in, and Harry herself
PROTECTED = {"explorer.exe", "applicationframehost.exe", "python.exe", "pythonw.exe", "py.exe", "pyw.exe",
             "dwm.exe", "csrss.exe", "winlogon.exe", "svchost.exe", "searchhost.exe",
             "startmenuexperiencehost.exe", "shellexperiencehost.exe", "textinputhost.exe"}

# --------------------------------------------------------------------------- COM, needed by pycaw (volume) and WinRT (media)
_tls = threading.local()
RPC_E_CHANGED_MODE = -2147417850


def _com():
    """Start COM on this thread. comtypes initialises COM again when first imported, so it must match this thread."""
    if getattr(_tls, "com", None) is None:
        _tls.com = "sta" if ole32.CoInitializeEx(None, 0) == RPC_E_CHANGED_MODE else "mta"
    if "comtypes" not in sys.modules:
        sys.coinit_flags = 2 if _tls.com == "sta" else 0


# --------------------------------------------------------------------------- sounds
MEDIA_DIR = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Media")
SOUNDS = {"wake": "Speech On.wav", "dictate_start": "Speech On.wav", "dictate_stop": "Speech Off.wav",
          "timer": "Windows Notify Calendar.wav"}  # stand-ins for the Mac's Tink, Pop and Glass


def play(path, write=None):
    """Play a sound file and wait until it's done, like afplay. write(out, data, rate): plays it instead of
    out.write, False if it stopped part way."""
    import sounddevice as sd
    import soundfile as sf
    try:
        data, rate = sf.read(path, dtype="float32", always_2d=True)
    except Exception:
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME)
        return
    with sd.OutputStream(samplerate=rate, channels=data.shape[1], dtype="float32") as out:
        if write is None:
            out.write(data)
        elif not write(out, data, rate):
            out.abort()  # what's buffered goes too


def chime(name):
    path = os.path.join(MEDIA_DIR, SOUNDS[name])
    if os.path.exists(path):
        try:
            play(path)
        except Exception as exc:
            print(f"  chime failed: {exc}")


# --------------------------------------------------------------------------- volume
def _endpoint():
    _com()
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    speakers = AudioUtilities.GetSpeakers()
    ep = getattr(speakers, "EndpointVolume", None)
    if ep is None:  # older pycaw hands back the raw device
        from comtypes import CLSCTX_ALL
        ep = ctypes.cast(speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None),
                         ctypes.POINTER(IAudioEndpointVolume))
    return ep


def volume():
    return round(_endpoint().GetMasterVolumeLevelScalar() * 100)


def set_volume(level, unmute=True):
    ep = _endpoint()
    ep.SetMasterVolumeLevelScalar(max(0, min(100, level)) / 100, None)
    if unmute and level > 0:
        ep.SetMute(0, None)


def set_muted(muted):
    _endpoint().SetMute(1 if muted else 0, None)


def _app_audio(app):
    """The app's sessions in the Windows volume mixer, which is how Spotify's own volume is set here."""
    _com()
    from pycaw.pycaw import AudioUtilities
    found = []
    for session in AudioUtilities.GetAllSessions():
        proc = session.Process
        if not proc:
            continue
        try:
            path = proc.exe()
        except Exception:
            path = proc.name()
        if app.matches(path):
            found.append(session)
    if not found:
        raise RuntimeError(f"{app.name} isn't in the volume mixer yet, play something first")
    return found


def app_volume(app):
    return round(_app_audio(app)[0].SimpleAudioVolume.GetMasterVolume() * 100)


def set_app_volume(app, level):
    for session in _app_audio(app):
        session.SimpleAudioVolume.SetMasterVolume(max(0, min(100, level)) / 100, None)


def app_sounding(app):
    """True if the app is playing sound now: its session in the volume mixer runs while it plays and stops when it's
    paused. VLC 3 isn't in Windows' media controls, so this is how to tell it's the one playing."""
    try:
        return any(s.State == 1 for s in _app_audio(app))  # AudioSessionStateActive
    except Exception:
        return False


# --------------------------------------------------------------------------- brightness, Wi-Fi, Bluetooth, mic, output
# From Tomte (github.com/xditya/tomte-windows, MIT, src/Tomte.Core/Device): the laptop screen's brightness through
# WMI, Wi-Fi and Bluetooth through Windows.Devices.Radios, the mic's mute and the sound's output device through Core
# Audio, each straight away. On 25 October "Increase brightness" went to a task in Settings, which pressed Win+A and
# stopped. Tomte says the radios need a packaged app; here, unpackaged, Windows allowed them (access 1, 26 October)
def _wmi():
    _com()
    import comtypes.client
    return comtypes.client.CoGetObject("winmgmts:{impersonationLevel=impersonate}!\\\\.\\root\\wmi", dynamic=True)


def brightness():
    """The built-in screen's brightness, 0 to 100, or None with none Windows can set (an external monitor needs
    DDC/CI, which this doesn't do)."""
    try:
        for m in _wmi().ExecQuery("SELECT CurrentBrightness FROM WmiMonitorBrightness"):
            return int(m.Properties_.Item("CurrentBrightness").Value)
    except Exception:
        return None
    return None


def set_brightness(percent):
    """The built-in screen at percent, 0 to 100. RuntimeError if there's none Windows can set."""
    percent, done = max(0, min(100, int(percent))), False
    try:
        for m in _wmi().ExecQuery("SELECT * FROM WmiMonitorBrightnessMethods"):
            args = m.Methods_.Item("WmiSetBrightness").InParameters.SpawnInstance_()
            args.Properties_.Item("Timeout").Value = 1
            args.Properties_.Item("Brightness").Value = percent
            m.ExecMethod_("WmiSetBrightness", args)
            done = True
    except Exception as exc:
        raise RuntimeError("This screen's brightness isn't one Windows lets me set") from exc
    if not done:
        raise RuntimeError("This screen's brightness isn't one Windows lets me set")


RADIO_PAGES = {"wifi": "ms-settings:network-wifi", "bluetooth": "ms-settings:bluetooth"}


def _radio_call(kind, on=None):
    """kind's radio ("wifi" or "bluetooth"): with on None, True or False for on or off; else set so, True if Windows
    did. None if Windows won't let her, or there's no such radio (an adapter turned off in Device Manager)."""
    _com()
    from winrt.windows.devices.radios import Radio, RadioAccessStatus, RadioKind, RadioState
    want = {"wifi": RadioKind.WI_FI, "bluetooth": RadioKind.BLUETOOTH}[kind]

    async def run():
        if await Radio.request_access_async() != RadioAccessStatus.ALLOWED:
            return None
        radio = next((r for r in await Radio.get_radios_async() if r.kind == want), None)
        if radio is None:
            return None
        if on is None:
            return radio.state == RadioState.ON
        return await radio.set_state_async(RadioState.ON if on else RadioState.OFF) == RadioAccessStatus.ALLOWED
    try:
        return asyncio.run(run())
    except OSError:  # a radio that went away mid-call (a dongle pulled out) raises rather than saying so
        return None


def radio_on(kind):
    """True if Wi-Fi or Bluetooth (kind) is on, False if off, None if she can't tell."""
    return _radio_call(kind)


def set_radio(kind, on):
    """Wi-Fi or Bluetooth (kind) on or off. When Windows won't let her, its Settings page opens instead, as Tomte
    does, and RuntimeError says so."""
    if _radio_call(kind, bool(on)) is not True:
        open_windows_page(RADIO_PAGES[kind])
        raise RuntimeError(f"Windows didn't let me switch {'Wi-Fi' if kind == 'wifi' else 'Bluetooth'}, so I've "
                           f"opened its settings")


def _mic_endpoint():
    _com()
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    mic = AudioUtilities.GetMicrophone()
    if mic is None:
        raise RuntimeError("There's no microphone")
    return ctypes.cast(mic.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), ctypes.POINTER(IAudioEndpointVolume))


def mic_muted():
    return bool(_mic_endpoint().GetMute())


def set_mic_muted(muted):
    """Mute the default mic for every app (calls too). Her own listening uses it as well, so muted she hears only
    right Alt's push-to-talk if that's on the same mic: say it before, not after."""
    _mic_endpoint().SetMute(1 if muted else 0, None)


def output_devices():
    """[(id, name, is_default)] for the sound outputs that are on: speakers, headphones, a Bluetooth speaker."""
    _com()
    from pycaw.constants import DEVICE_STATE, EDataFlow
    from pycaw.pycaw import AudioUtilities
    try:
        current = AudioUtilities.GetSpeakers().id
    except Exception:
        current = None
    return [(d.id, d.FriendlyName, d.id == current)
            for d in AudioUtilities.GetAllDevices(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)
            if d.FriendlyName]


# Windows names an output for what it is and what it's on: "Speakers (Realtek(R) Audio)" is the laptop's own,
# "Speakers (JBL Flip 5)" or "Headphones (Galaxy Buds2 Pro)" a Bluetooth one. These words only say what it is
OUTPUT_KINDS = {"speaker", "speakers", "headphone", "headphones", "headset", "earbud", "earbuds", "earphone",
                "earphones", "audio", "sound", "output", "bluetooth", "stereo", "hands", "free"}
SOUND_CHIP = re.compile(r"realtek|high definition|intel|amd|nvidia|conexant|cirrus|audio device|smart sound", re.I)


def output_name(name):
    """An output as she'd say it: "Speakers" for the laptop's own, "JBL Flip 5" for a Bluetooth speaker."""
    m = re.fullmatch(r"(.+?) \((.+)\)", name.strip())
    return (m[1] if SOUND_CHIP.search(m[2]) else m[2]) if m else name.strip()


def pick_output(devices, name):
    """The one of devices called name: the whole name, else the one that has most of its words, a word that names it
    ("jbl", "buds") over one that only says what it is ("speaker"). LookupError, as she'd say it, for none or for
    more than one as near."""
    words = [w for w in re.findall(r"[a-z0-9]+", name.lower())
             if w not in ("the", "my", "a", "to", "device", "one", "please")]
    if not words:
        raise LookupError("Which speaker or headphones?")
    exact = [d for d in devices if d[1].lower() == name.lower().strip() or output_name(d[1]).lower() == name.lower()]
    if len(exact) == 1:
        return exact[0]

    def score(d):
        have = set(re.findall(r"[a-z0-9]+", d[1].lower()))
        return sum((1 if w in OUTPUT_KINDS else 2) for w in words
                   if w in have or w.rstrip("s") in have or w + "s" in have)
    scored = [(score(d), d) for d in devices]
    best = max((s for s, _ in scored), default=0)
    found = [d for s, d in scored if s == best and s > 0]
    if len(found) == 1:
        return found[0]
    names = " or ".join(output_name(d[1]) for d in (found or devices))
    raise LookupError(f"There's more than one like that: {names}." if found else
                      f"I can't find a sound output called {name}. There's {names}." if devices else
                      "There's no sound output on.")


def set_output(device_id):
    """Sound goes to this output from now on, in every app, as picking it in Quick Settings does."""
    _com()
    from pycaw.constants import ERole
    from pycaw.pycaw import AudioUtilities
    AudioUtilities.SetDefaultDevice(device_id, [ERole.eConsole, ERole.eMultimedia, ERole.eCommunications])


# --------------------------------------------------------------------------- media (Spotify), via Windows media controls
def media_session(app_hint=None):
    """The media session of the app whose id contains app_hint ("spotify"). With no hint, the one Windows shows in
    its media controls: whatever is playing, or played last (YouTube in Chrome, Spotify, VLC). None if there's none."""
    _com()
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager

    async def find():
        manager = await Manager.request_async()
        if app_hint is None:
            return manager.get_current_session()
        for session in manager.get_sessions():
            if app_hint in (session.source_app_user_model_id or "").lower():
                return session
        return None
    return asyncio.run(find())


def media_sessions():
    """Every media session Windows' media controls know of: each tab playing in a browser has its own."""
    _com()
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager

    async def find():
        manager = await Manager.request_async()
        return list(manager.get_sessions())
    return asyncio.run(find())


def media_command(session, command):
    calls = {"play": session.try_play_async, "pause": session.try_pause_async,
             "toggle": session.try_toggle_play_pause_async,
             "next": session.try_skip_next_async, "previous": session.try_skip_previous_async}

    async def run():
        return await calls[command]()
    return asyncio.run(run())


def media_props(session):
    """(title, artist) of what a media session is playing, "" for what it doesn't say. A YouTube video in Chrome is
    its title and its channel."""
    async def get():
        return await session.try_get_media_properties_async()
    try:
        props = asyncio.run(get())
    except Exception:
        return "", ""
    return (props.title or "").strip(), (props.artist or "").strip()


def media_title(session):
    """'Title - Artist' of what a media session is playing, or "" if it doesn't say."""
    title, artist = media_props(session)
    return f"{title} - {artist}" if title and artist else title


def media_playing(session):
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status
    return session.get_playback_info().playback_status == Status.PLAYING


def media_position(session):
    """Seconds into the current track, counting time since Windows last heard from the app."""
    from datetime import datetime, timezone
    timeline = session.get_timeline_properties()
    pos = timeline.position.total_seconds()
    try:
        if media_playing(session) and timeline.last_updated_time:
            pos += (datetime.now(timezone.utc) - timeline.last_updated_time).total_seconds()
    except Exception:
        pass
    return pos


MEDIA_STATUS = {0: "closed", 1: "opened", 2: "changing", 3: "stopped", 4: "playing", 5: "paused"}


def media_status(session):
    """What a media session is doing: "playing", "paused", "stopped", "changing", "opened" or "closed", "" if
    Windows won't say."""
    try:
        return MEDIA_STATUS.get(int(session.get_playback_info().playback_status), "")
    except Exception:
        return ""


def media_length(session):
    """How long what a media session plays is, in seconds, or 0 if it doesn't say."""
    try:
        timeline = session.get_timeline_properties()
        return max(0.0, timeline.end_time.total_seconds() - timeline.start_time.total_seconds())
    except Exception:
        return 0.0


# --------------------------------------------------------------------------- dark mode, lock, sleep
PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def dark_mode():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSONALIZE) as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False  # never set means light


def light_mode():
    """True if apps and Windows itself (the taskbar, Start) are both in light mode: dark_mode reads only the apps."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSONALIZE) as key:
            for name in ("AppsUseLightTheme", "SystemUsesLightTheme"):
                try:
                    if winreg.QueryValueEx(key, name)[0] == 0:
                        return False
                except OSError:
                    pass  # never set means light
    except OSError:
        pass
    return True


def set_dark_mode(on):
    light = 0 if on else 1
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, PERSONALIZE, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, light)
        winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, light)
    # tell the taskbar and open apps to repaint in the new theme. A window that hasn't taken the message when the wait
    # runs out never hears of it and keeps its old colours, and Explorer, repainting many windows, can take more than
    # 2 s: Tomte (Display.cs) waits 5 s, as Microsoft's PowerToys Light Switch does. A hung window is skipped at once
    result = ctypes.c_size_t()
    user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "ImmersiveColorSet", SMTO_ABORTIFHUNG, 5000,
                               ctypes.byref(result))


# --------------------------------------------------------------------------- Night light
# Windows keeps whether Night light is on in the registry, as Bond CompactBinary v1 inside a CloudStore envelope, and
# explorer.exe applies a change there at once, so it's switched as quickly as dark mode, with no Settings window. It
# isn't documented: this is the layout kvnxiao/win-nightlight-cli worked out (docs/nightlight-registry-format.md,
# Windows 11 builds 26100 and 26300; 26200 here is the same). On or off writes only the state value, the way Settings
# and Quick Settings do it. A value laid out any other way is left alone: one Windows can't read could leave it stuck
NIGHT_STATE = "\\".join((r"Software\Microsoft\Windows\CurrentVersion\CloudStore\Store\DefaultAccount\Current",
                         "default$windows.data.bluelightreduction.bluelightreductionstate",
                         "windows.data.bluelightreduction.bluelightreductionstate"))
BOND = b"CB\x01\x00"  # a marshaled Bond CompactBinary v1 struct
ENVELOPE = BOND + b"\x0a\x02\x01\x00\x2a\x06"  # its metadata (field 0: true), then the payload's timestamp
BT_BOOL, BT_UINT8, BT_UINT64, BT_INT8, BT_INT32 = 2, 3, 6, 14, 16
VARINTS = {4, 5, 6, 15, 16, 17}  # Bond's unsigned and (zigzag) signed integers, 16 to 64 bits
FILETIME_1970 = 11644473600  # seconds from 1601, where a FILETIME counts from, to 1970


def _varint(n):
    out = bytearray()
    while n > 0x7F:
        out.append(n & 0x7F | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


def _read_varint(data, i):
    n = shift = 0
    while shift < 70:
        b = data[i]
        n, i, shift = n | (b & 0x7F) << shift, i + 1, shift + 7
        if b < 0x80:
            return n, i
    raise ValueError("a number too long")


def _night_split(data):
    """(timestamp, inner payload) out of the state value, or ValueError if it isn't laid out as Windows writes it."""
    data = bytes(data)
    try:
        if not data.startswith(ENVELOPE):
            raise ValueError("not a CloudStore envelope")
        stamp, i = _read_varint(data, len(ENVELOPE))
        if data[i:i + 3] != b"\x2a\x2b\x0e":  # field 1: the data wrapper, with field 1 a list of bytes
            raise ValueError("no payload where it should be")
        size, i = _read_varint(data, i + 3)
    except IndexError:
        raise ValueError("cut short") from None
    inner = data[i:i + size]
    if len(inner) != size or data[i + size:] != b"\x00\x00\x00":
        raise ValueError("more than the payload in it")
    return stamp, inner


def _night_fields(inner):
    """{field: (Bond type, its bytes)} of the inner state, or ValueError for a type it shouldn't have."""
    if not inner.startswith(BOND):
        raise ValueError("not a Bond struct")
    fields, i = {}, len(BOND)
    try:
        while True:
            head = inner[i]
            kind, field, i = head & 0x1F, head >> 5, i + 1
            if not kind:  # BT_STOP
                break
            if field == 6:
                field, i = inner[i], i + 1
            elif field == 7:
                field, i = inner[i] | inner[i + 1] << 8, i + 2
            start = i
            if kind in (BT_BOOL, BT_UINT8, BT_INT8):
                i += 1
            elif kind in VARINTS:
                _, i = _read_varint(inner, i)
            else:
                raise ValueError(f"field {field} is of type {kind}")
            fields[field] = (kind, inner[start:i])
    except IndexError:
        raise ValueError("cut short") from None
    if i != len(inner):
        raise ValueError("more after its end")
    return fields


def _bond_field(field, kind, value):
    head = bytes([field << 5 | kind]) if field <= 5 else bytes([0xC0 | kind, field]) if field <= 0xFF else \
        bytes([0xE0 | kind, field & 0xFF, field >> 8])
    return head + value


def night_light_value(data, on, now=None):
    """The state value data with Night light on or off, as Windows Settings writes it: field 0 there (0, running)
    only when it's on, field 10 = 1 (changed by hand), field 20 = now as a FILETIME, and the envelope's timestamp the
    later of now and 2 s after the one in it, as Windows won't apply one it has seen go by. Fields it doesn't know
    stay as they are, in order."""
    now = time.time() if now is None else now
    stamp, inner = _night_split(data)
    fields = _night_fields(inner)
    if fields.get(30, (BT_BOOL, b"\x01"))[1] == b"\x00":  # usable: false
        raise RuntimeError("Night light isn't available on this screen")
    fields.pop(0, None)
    if on:
        fields[0] = (BT_INT32, b"\x00")
    fields[10] = (BT_INT32, b"\x02")  # zigzag 1
    fields[20] = (BT_UINT64, _varint(int((now + FILETIME_1970) * 10_000_000)))
    inner = BOND + b"".join(_bond_field(f, *fields[f]) for f in sorted(fields)) + b"\x00"
    return ENVELOPE + _varint(max(int(now), stamp + 2)) + b"\x2a\x2b\x0e" + _varint(len(inner)) + inner + b"\x00" * 3


def night_light():
    """True if Night light is on now, False if it's off, None if that can't be told."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, NIGHT_STATE) as key:
            return 0 in _night_fields(_night_split(winreg.QueryValueEx(key, "Data")[0])[1])
    except (OSError, ValueError):
        return None


def set_night_light(on):
    """Turns Night light on or off now, as its switch in Quick Settings does, the schedule as it was. False if it
    already was."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, NIGHT_STATE, 0,
                            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
            data = winreg.QueryValueEx(key, "Data")[0]
            if (0 in _night_fields(_night_split(data)[1])) == bool(on):
                return False
            winreg.SetValueEx(key, "Data", 0, winreg.REG_BINARY, night_light_value(data, on))
    except FileNotFoundError:
        raise RuntimeError("Night light isn't set up yet: switch it on once in Settings") from None
    except ValueError as exc:
        raise RuntimeError("I can't switch Night light directly on this version of Windows") from exc
    return True


def lock():
    if not user32.LockWorkStation():
        raise RuntimeError("Windows wouldn't lock")


def sleep():
    if not powrprof.SetSuspendState(False, False, False):
        # Modern Standby laptops refuse SetSuspendState, turning the screen off puts those to sleep
        user32.PostMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2)


def shutdown(delay=10):
    """Initiate a clean Windows shutdown with a grace period (default 10s)."""
    subprocess.Popen(["shutdown.exe", "/s", "/t", str(delay), "/c", "Hey Harry is shutting down the PC."])


def restart(delay=10):
    """Initiate a clean Windows restart with a grace period (default 10s)."""
    subprocess.Popen(["shutdown.exe", "/r", "/t", str(delay), "/c", "Hey Harry is restarting the PC."])


def abort_shutdown():
    """Cancel a pending Windows shutdown or restart."""
    subprocess.Popen(["shutdown.exe", "/a"])


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte), ("BatteryLifePercent", ctypes.c_ubyte),
                ("SystemStatusFlag", ctypes.c_ubyte), ("BatteryLifeTime", DWORD), ("BatteryFullLifeTime", DWORD)]


_sig(kernel32.GetSystemPowerStatus, [ctypes.POINTER(SYSTEM_POWER_STATUS)])


def charging():
    """True while the battery is charging, False when it isn't (on battery, or plugged in and as full as it'll get:
    a Lenovo's conservation mode stops at about 60 percent), None with no battery or when Windows won't say."""
    s = SYSTEM_POWER_STATUS()
    if not kernel32.GetSystemPowerStatus(ctypes.byref(s)) or s.BatteryFlag in (128, 255):
        return None
    return bool(s.BatteryFlag & 8)


DOWNLOADS_ID = "{374DE290-123F-4565-9164-39C4925E467B}"  # the Downloads folder's ID in User Shell Folders


def downloads_folder():
    """Where browsers save what they download unless told otherwise: Windows' Downloads folder, which can be moved
    off C (on Hari's PC it's on D), else the one in the user folder."""
    for key in (r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
                path = os.path.expandvars(str(winreg.QueryValueEx(k, DOWNLOADS_ID)[0]))
        except OSError:
            continue
        if os.path.isdir(path):
            return path
    return os.path.join(os.path.expanduser("~"), "Downloads")


# --------------------------------------------------------------------------- apps
def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


@lru_cache(maxsize=512)
def file_description(path):
    """The "File description" Windows shows for an .exe, like "Visual Studio Code" for Code.exe."""
    try:
        size = version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return ""
        buf = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(path, 0, size, buf):
            return ""
        ptr, length = ctypes.c_void_p(), UINT()
        if not version.VerQueryValueW(buf, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(length)) \
                or length.value < 4:
            return ""
        lang, codepage = struct.unpack("<HH", ctypes.string_at(ptr.value, 4))
        if version.VerQueryValueW(buf, f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\FileDescription",
                                  ctypes.byref(ptr), ctypes.byref(length)) and length.value:
            return ctypes.wstring_at(ptr.value, length.value).rstrip("\x00")
    except Exception:
        pass
    return ""


class App:
    """An app from apps.json: the name it has in the Start menu, and the .exe its windows belong to."""

    def __init__(self, name, exes=()):
        self.name = name
        self.exes = {e.lower() for e in ([exes] if isinstance(exes, str) else exes or ())}
        words = _norm(name).split()
        self.joined = "".join(words)
        self.words = {w for w in words if len(w) >= 3}

    def matches(self, exe_path):
        if not exe_path:
            return False
        base = os.path.basename(exe_path).lower()
        if base in self.exes:
            return True
        stem = re.sub(r"[^a-z0-9]", "", base[:-4] if base.endswith(".exe") else base)
        # Spotify.exe, chrome.exe for "Google Chrome", Code.exe for "VS Code", and Store apps' own names with
        # Windows or Microsoft in front: WindowsCamera.exe for "Camera" ("Close camera": "Camera isn't running")
        if stem == self.joined or stem in self.words:
            return True
        bare = re.sub(r"^(?:windows|microsoft)", "", stem)  # the whole name only: "Camera Hub" isn't WindowsCamera
        if bare and bare != stem and bare == self.joined:
            return True
        return _norm(file_description(exe_path)).replace(" ", "") == self.joined

    def __repr__(self):
        return f"App({self.name!r}, {sorted(self.exes)})"


_start_apps, _start_lock = None, threading.Lock()


def start_apps(refresh=False):
    """(name, AppID) for everything in the Start menu, which covers normal and Microsoft Store apps."""
    global _start_apps
    with _start_lock:
        if _start_apps is None or refresh:
            script = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                      "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress")
            try:
                out = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
                                     capture_output=True, text=True, encoding="utf-8", errors="replace",
                                     creationflags=CREATE_NO_WINDOW, timeout=60).stdout
                data = json.loads(out) if out.strip() else []
            except Exception as exc:
                print(f"  couldn't read the Start menu: {exc}")
                data = []
            if isinstance(data, dict):
                data = [data]
            _start_apps = [(d["Name"], d["AppID"]) for d in data if d.get("Name") and d.get("AppID")]
        return _start_apps


def warm_start_apps():
    threading.Thread(target=start_apps, daemon=True).start()


def loaded_start_apps():
    """The Start menu as far as it's been read, without waiting while it's read the first time."""
    return _start_apps or []


def find_start_app(name, refresh=True):
    target, target_norm = name.lower(), _norm(name)
    for again in ((False, True) if refresh else (False,)):  # look again in case it was installed after Harry started
        apps = start_apps(refresh=again)
        for rule in (lambda n: n.lower() == target, lambda n: _norm(n) == target_norm,
                     lambda n: re.search(rf"\b{re.escape(target_norm)}\b", _norm(n))):
            hits = [a for a in apps if rule(a[0])]
            if hits:
                return min(hits, key=lambda a: len(a[0]))  # "Zoom" -> "Zoom Workplace", not something longer
    return None


def launch(name):
    hit = find_start_app(name)
    if hit:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{hit[1]}"], creationflags=CREATE_NO_WINDOW)
        return
    try:
        os.startfile(name)  # last try, anything Windows knows by name, like "notepad"
    except OSError:
        raise RuntimeError(f"Couldn't find {name} in the Start menu")


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _pid(hwnd):
    pid = DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _exe(pid):
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf, size = ctypes.create_unicode_buffer(32768), DWORD(32768)
        return buf.value if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)) else ""
    finally:
        kernel32.CloseHandle(handle)


def _children(hwnd):
    found = []
    cb = WNDENUMPROC(lambda h, _: found.append(h) or True)
    user32.EnumChildWindows(hwnd, cb, 0)
    return found


def window_exe(hwnd):
    """The .exe a window belongs to. Store apps like Calculator sit inside ApplicationFrameHost, so look one level in."""
    pid = _pid(hwnd)
    exe = _exe(pid)
    if os.path.basename(exe).lower() == "applicationframehost.exe":
        for child in _children(hwnd):
            child_pid = _pid(child)
            if child_pid != pid:
                return _exe(child_pid)
    return exe


def _is_app_window(hwnd):
    if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, GW_OWNER):
        return False
    if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW or not user32.GetWindowTextLengthW(hwnd):
        return False
    cloaked = DWORD()  # suspended Store apps and other virtual desktops
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return not cloaked.value and _class_name(hwnd) not in SHELL_CLASSES


def app_windows(app):
    """The app's windows on screen (minimised ones too), front-most first."""
    found = []
    cb = WNDENUMPROC(lambda h, _: found.append(h) or True)
    user32.EnumWindows(cb, 0)
    return [h for h in found if _is_app_window(h) and app.matches(window_exe(h))]


def open_windows():
    """Every app window on screen, minimised ones too, front-most first: [(hwnd, exe path, title)]."""
    found = []
    cb = WNDENUMPROC(lambda h, _: found.append(h) or True)
    user32.EnumWindows(cb, 0)
    return [(h, window_exe(h), window_title(h)) for h in found if _is_app_window(h)]


def _app_processes(app):
    import psutil
    me = os.getpid()
    out = []
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        if proc.info["pid"] != me and app.matches(proc.info["exe"] or proc.info["name"] or ""):
            out.append(proc)
    return out


def bring_to_front(hwnd):
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    front = user32.GetForegroundWindow()
    if front == hwnd:
        return
    # Windows stops background apps stealing focus, borrowing the front window's input queue gets round that
    me = kernel32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(front, None) if front else 0
    attached = bool(other and other != me and user32.AttachThreadInput(me, other, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, other, False)
    if user32.GetForegroundWindow() != hwnd:
        user32.SwitchToThisWindow(hwnd, True)


# --------------------------------------------------------------------------- A window by name, on a side or a screen
# "Chrome on the left, Notepad on the right", "VS Code on my big screen" (28 October 2026). Every
# display with its name and whether it's the laptop's own
# panel, from Windows' display configuration, and a window put by its visible frame, so it lands exactly on its
# half whatever its invisible resize borders. Real pixels throughout (_real_pixels), as SetWindowPos takes them
class MONITORINFOEX(ctypes.Structure):
    _fields_ = [("cbSize", DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", DWORD),
                ("szDevice", wintypes.WCHAR * 32)]


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", DWORD), ("HighPart", LONG)]


class _PATH_INFO(ctypes.Structure):  # DISPLAYCONFIG_PATH_INFO, flattened (72 bytes)
    _fields_ = [("srcAdapter", _LUID), ("srcId", ctypes.c_uint32), ("srcMode", ctypes.c_uint32),
                ("srcFlags", ctypes.c_uint32), ("tgtAdapter", _LUID), ("tgtId", ctypes.c_uint32),
                ("tgtMode", ctypes.c_uint32), ("tech", ctypes.c_uint32), ("rot", ctypes.c_uint32),
                ("scale", ctypes.c_uint32), ("rate", ctypes.c_uint32 * 2), ("order", ctypes.c_uint32),
                ("avail", BOOL), ("tgtFlags", ctypes.c_uint32), ("flags", ctypes.c_uint32)]


class _DC_HEADER(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("size", ctypes.c_uint32), ("adapter", _LUID), ("id", ctypes.c_uint32)]


class _SOURCE_NAME(ctypes.Structure):
    _fields_ = [("h", _DC_HEADER), ("gdi", wintypes.WCHAR * 32)]


class _TARGET_NAME(ctypes.Structure):
    _fields_ = [("h", _DC_HEADER), ("flags", ctypes.c_uint32), ("tech", ctypes.c_uint32), ("mfr", ctypes.c_uint16),
                ("product", ctypes.c_uint16), ("connector", ctypes.c_uint32), ("friendly", wintypes.WCHAR * 64),
                ("path", wintypes.WCHAR * 128)]


_BUILT_IN_TECH = {6, 11, 13, 0x80000000}  # LVDS, embedded DisplayPort, UDI embedded, "internal": a laptop's panel
SIDES = ("left", "right", "top", "bottom", "full", "center")


def _panels():
    """{GDI device name (\\\\.\\DISPLAY1): (its friendly name, built in?)} from the display configuration, {} if
    Windows won't say."""
    out, n_path, n_mode = {}, ctypes.c_uint32(), ctypes.c_uint32()
    try:
        if user32.GetDisplayConfigBufferSizes(2, ctypes.byref(n_path), ctypes.byref(n_mode)):
            return out
        paths, modes = (_PATH_INFO * n_path.value)(), (ctypes.c_byte * (64 * max(1, n_mode.value)))()
        if user32.QueryDisplayConfig(2, ctypes.byref(n_path), paths, ctypes.byref(n_mode), modes, None):
            return out
        for p in paths[:n_path.value]:
            src = _SOURCE_NAME(_DC_HEADER(1, ctypes.sizeof(_SOURCE_NAME), p.srcAdapter, p.srcId))
            tgt = _TARGET_NAME(_DC_HEADER(2, ctypes.sizeof(_TARGET_NAME), p.tgtAdapter, p.tgtId))
            if user32.DisplayConfigGetDeviceInfo(ctypes.byref(src)) == 0:
                user32.DisplayConfigGetDeviceInfo(ctypes.byref(tgt))
                out[src.gdi] = (tgt.friendly or "", p.tech in _BUILT_IN_TECH)
    except (AttributeError, OSError):
        pass
    return out


def _on_battery_power_pc():
    """True on a laptop (it has a battery): for the panel Windows didn't name."""
    class SPS(ctypes.Structure):
        _fields_ = [("ac", ctypes.c_byte), ("flag", ctypes.c_byte), ("pct", ctypes.c_byte), ("saver", ctypes.c_byte),
                    ("life", DWORD), ("full", DWORD)]
    s = SPS()
    return bool(kernel32.GetSystemPowerStatus(ctypes.byref(s))) and s.flag != -128 and not s.flag & 128


def monitors():
    """[{name, x, y, w, h, work: (x, y, w, h), built_in, primary}], the primary first, in real pixels."""
    found = []
    PROC = ctypes.WINFUNCTYPE(BOOL, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM)

    def each(handle, _dc, _rect, _lparam):
        info = MONITORINFOEX()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(handle, ctypes.cast(ctypes.pointer(info), ctypes.POINTER(MONITORINFO))):
            found.append(info)
        return True
    with _real_pixels():
        user32.EnumDisplayMonitors(None, None, PROC(each), 0)
    names, out, seen = _panels(), [], {}
    for info in found:
        friendly, built_in = names.get(info.szDevice, ("", False))
        name = friendly or ("Built-in Display" if built_in else "Display")
        seen[name] = seen.get(name, 0) + 1
        m, w = info.rcMonitor, info.rcWork
        out.append({"name": name if seen[name] == 1 else f"{name} {seen[name]}", "x": m.left, "y": m.top,
                    "w": m.right - m.left, "h": m.bottom - m.top,
                    "work": (w.left, w.top, w.right - w.left, w.bottom - w.top), "built_in": built_in,
                    "primary": bool(info.dwFlags & 1)})
    out.sort(key=lambda d: not d["primary"])
    if len(out) > 1 and not any(d["built_in"] for d in out) and _on_battery_power_pc():
        out[0]["built_in"] = True  # Windows didn't say: a laptop's own panel is usually the primary
    return out


def pick_monitor(mons, screen, at):
    """The display screen means: "laptop" (the built-in one), "monitor" (the biggest other one), "other" (one that
    isn't where the window is), "primary", "current" (where the window's middle is, at (x, y)), or a display's name.
    The current one when none fits."""
    here = next((m for m in mons if m["x"] <= at[0] < m["x"] + m["w"] and m["y"] <= at[1] < m["y"] + m["h"]),
                mons[0] if mons else None)
    screen = str(screen or "current").lower()
    if screen == "laptop":
        return next((m for m in mons if m["built_in"]), here)
    if screen == "monitor":
        others = [m for m in mons if not m["built_in"]] or [m for m in mons if m is not here]
        return max(others, key=lambda m: m["w"] * m["h"]) if others else here
    if screen == "other":
        return next((m for m in mons if m is not here), here)
    if screen == "primary":
        return next((m for m in mons if m["primary"]), here)
    return next((m for m in mons if screen in m["name"].lower()), here)


def rect_for(where, area, size):
    """Where a window goes in a work area (x, y, w, h): a half, the whole of it, or the middle at its own size."""
    x, y, w, h = area
    cw, ch = min(size[0], w), min(size[1], h)
    return {"left": (x, y, w // 2, h), "right": (x + w // 2, y, w - w // 2, h), "top": (x, y, w, h // 2),
            "bottom": (x, y + h // 2, w, h - h // 2), "full": (x, y, w, h),
            "center": (x + (w - cw) // 2, y + (h - ch) // 2, cw, ch)}[where]


def window_frame(hwnd):
    """The window's visible frame, (x, y, w, h), without its invisible resize borders."""
    r = RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)):
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def set_window_frame(hwnd, x, y, w, h):
    """Moves it so its visible frame lands exactly there: the window's own rectangle is a few pixels bigger."""
    r = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    fx, fy, fw, fh = window_frame(hwnd)
    dl, dt, dr, db = fx - r.left, fy - r.top, r.right - (fx + fw), r.bottom - (fy + fh)
    user32.SetWindowPos(hwnd, None, x - dl, y - dt, w + dl + dr, h + dt + db, 0x0014)  # NOZORDER | NOACTIVATE


def place_window(app, where="full", screen="current", wait=3.0):
    """Puts app's front window on a side of a screen (where in SIDES, screen as pick_monitor reads it), opening it
    first if it has none. Returns where it went, in words; RuntimeError if it has no window to move."""
    if where not in SIDES:
        raise RuntimeError("I can put a window on the left, right, top or bottom, full screen or in the middle")
    windows = app_windows(app)
    if not windows:
        open_app(app)
        end = time.time() + wait
        while not windows and time.time() < end:  # a window just opened can take a moment to show
            time.sleep(0.2)
            windows = app_windows(app)
    if not windows:
        raise RuntimeError(f"{app.name} has no window to move")
    hwnd = windows[0]
    with _real_pixels():
        if user32.IsZoomed(hwnd) or user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)  # a maximised window can't be moved: put back first
        fx, fy, fw, fh = window_frame(hwnd)
        mons = monitors()
        if not mons:
            raise RuntimeError("Windows didn't tell me about the screens")
        m = pick_monitor(mons, screen, (fx + fw // 2, fy + fh // 2))
        set_window_frame(hwnd, *rect_for(where, m["work"], (fw, fh)))
        if where == "full":
            user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE, on the display it now sits on
    bring_to_front(hwnd)
    return f"{app.name} {where} on {m['name']}"


def open_app(app, wait=8.0):
    """Like `open -a`: bring it to the front if it's open, else launch it and wait for its window. True if a window of
    it was seen (or a new one came to the front), False if none came in wait seconds: she says so, rather than that
    it's open (28 October 2026, only what she saw)."""
    windows = app_windows(app)
    if windows:
        bring_to_front(windows[0])
        return True
    front = user32.GetForegroundWindow()
    launch(app.name)
    start = time.time()
    while time.time() - start < wait:
        time.sleep(0.2)
        if app_windows(app):
            return True
        now = user32.GetForegroundWindow()  # web apps like YouTube run as chrome.exe, so their windows never match
        if now and now != front and _is_app_window(now):  # a new window came to the front, that's it
            return True
    return False


def focus_app(app):
    windows = app_windows(app)
    if not windows:
        return open_app(app)  # AppleScript's activate launches it too
    bring_to_front(windows[0])


def minimise_app(app):
    windows = app_windows(app)
    if not windows:
        raise RuntimeError(f"{app.name} has no windows open")
    for hwnd in windows:
        user32.ShowWindow(hwnd, SW_MINIMIZE)


def quit_app(app):
    windows, procs = app_windows(app), _app_processes(app)
    if not windows and not procs:
        raise RuntimeError(f"{app.name} isn't running")
    refused = 0
    for hwnd in windows:  # same as clicking X, so apps still get to ask about unsaved work
        if not user32.PostMessageW(hwnd, WM_CLOSE, 0, 0) and ctypes.get_last_error() == 5:
            refused += 1  # access denied: Windows keeps apps that run as administrator, like Task Manager, out of reach
    if windows and refused == len(windows):
        raise RuntimeError(f"Windows won't let me close {app.name}, it runs as administrator")
    deadline = time.time() + 4
    while windows and time.time() < deadline:
        time.sleep(0.25)
        windows = app_windows(app)
    if windows:  # something's still open, maybe a "save changes?" prompt, so that's up to you
        raise RuntimeError(f"{app.name} is still open, it may be asking you to save something")
    import psutil
    procs = [p for p in _app_processes(app)
             if os.path.basename(p.info["exe"] or p.info["name"] or "").lower() not in PROTECTED]
    _, alive = psutil.wait_procs(procs, timeout=4)  # give it a moment to close by itself
    for proc in alive:  # Spotify, Slack, Discord and co only drop to the tray, quit means quit
        try:
            proc.kill()
        except psutil.Error:
            pass


def front_window():
    """The window in front, or None."""
    return user32.GetForegroundWindow() or None


def shown(hwnd):
    """True if hwnd is a window that's still there and showing."""
    return bool(hwnd) and bool(user32.IsWindow(hwnd)) and bool(user32.IsWindowVisible(hwnd))


def foreground_exe():
    hwnd = user32.GetForegroundWindow()
    return window_exe(hwnd) if hwnd else ""


def window_title(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def app_path(exe):
    """Full path of a program Windows has under App Paths, like chrome.exe or msedge.exe, or None."""
    sub = rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, sub) as key:
                path = os.path.expandvars(str(winreg.QueryValueEx(key, "")[0]).strip('"'))
        except OSError:
            continue
        if os.path.isfile(path):
            return path
    return None


def front_title():
    """The title of the window in front, like "lofi music - YouTube - Google Chrome"."""
    hwnd = user32.GetForegroundWindow()
    return window_title(hwnd) if hwnd else ""


# --------------------------------------------------------------------------- calls
# Windows keeps which apps use the mic, for the mic icon on the taskbar: a key per app under ConsentStore\microphone,
# with LastUsedTimeStop 0 while it's in use. Only apps that mean a conversation count, never Voicemeeter, which can
# hold the mic all day, or Hey Harry itself, which is python. (in the key's name, in the running program's name, name)
CALL_APPS = (("whatsapp", "whatsapp", "WhatsApp"), ("msteams", "teams", "Teams"), ("teams", "teams", "Teams"),
             ("yourphone", "phoneexperiencehost", "Phone Link"), ("zoom", "zoom", "Zoom"),
             ("discord", "discord", "Discord"), ("skype", "skype", "Skype"), ("slack", "slack", "Slack"),
             ("telegram", "telegram", "Telegram"), ("signal", "signal", "Signal"), ("webex", "webex", "Webex"),
             ("chrome.exe", "chrome", "Chrome"), ("msedge.exe", "msedge", "Edge"), ("brave.exe", "brave", "Brave"),
             ("firefox.exe", "firefox", "Firefox"), ("comet.exe", "comet", "Comet"))
_MIC_KEY = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
_calls = {"at": 0.0, "apps": ()}


def _mic_users():
    """The names of the mic keys of apps using the mic right now, lower case."""
    found = []
    for sub in (_MIC_KEY, _MIC_KEY + r"\NonPackaged"):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub)
        except OSError:
            continue
        with key:
            for i in range(1000):
                try:
                    name = winreg.EnumKey(key, i)
                except OSError:
                    break
                try:
                    with winreg.OpenKey(key, name) as app:
                        start = winreg.QueryValueEx(app, "LastUsedTimeStart")[0]
                        stop = winreg.QueryValueEx(app, "LastUsedTimeStop")[0]
                except OSError:
                    continue
                if start and not stop:
                    found.append(name.lower())
    return found


def call_apps(max_age=2.0):
    """The apps that mean a call, WhatsApp, Teams, Zoom or a browser for Meet, that have the mic open right now, read
    again at most every max_age seconds. Each one's program has to be running too: a crash can leave the key saying
    in use."""
    if time.time() - _calls["at"] < max_age:
        return _calls["apps"]
    apps = []
    try:
        users = _mic_users()
        hits = [(proc, label) for key, proc, label in CALL_APPS if any(key in u for u in users)]
        if hits:
            import psutil
            running = {(p.info["name"] or "").lower() for p in psutil.process_iter(["name"])}
            apps = [label for proc, label in hits if any(proc in r for r in running)]
    except Exception:
        apps = []
    _calls.update(at=time.time(), apps=tuple(dict.fromkeys(apps)))
    return _calls["apps"]


def front_app_name():
    """The app in front by name, like "Google Chrome", so "close it" or "scroll down" make sense to the planner."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd or _pid(hwnd) == os.getpid():
        return ""  # nothing, or Harry's own window
    exe = window_exe(hwnd)
    return (file_description(exe) or os.path.splitext(os.path.basename(exe))[0]) if exe else ""


def scroll(clicks):
    """Turn the mouse wheel over the window in front, then put the pointer back. clicks > 0 scrolls up.
    The wheel, not Page Down, since keys go to the YouTube player and Home there jumps to the start of the video."""
    from pynput.mouse import Controller
    hwnd, rect = user32.GetForegroundWindow(), RECT()
    if not hwnd or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("There's no window in front to scroll")
    mouse = Controller()
    back = mouse.position
    mouse.position = ((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
    try:
        for _ in range(abs(clicks)):
            mouse.scroll(0, 1 if clicks > 0 else -1)
            time.sleep(0.01)
        time.sleep(0.05)
    finally:
        mouse.position = back


def default_browser_progid():
    base = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https"
    for sub in ("UserChoiceLatest", "UserChoice"):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{base}\\{sub}") as key:
                return winreg.QueryValueEx(key, "ProgId")[0]
        except OSError:
            continue
    return ""


def open_url(url, app=None):
    """Open a website, in a given browser if there is one, otherwise in the default browser. Web addresses only, with
    quotes, spaces and control characters percent-encoded: a quote in a planned address ended the quoted argument
    below, and the rest went to the browser as switches (Electron's CVE-2018-1000006 trick)."""
    url = quote(str(url or "").strip(), safe=":/?#[]@!$&'()*+,;=%~")
    if not re.match(r"https?://", url, re.I):  # never a file or a program, which os.startfile would run
        raise RuntimeError("I only open web addresses")
    if app:
        windows = app_windows(app)
        exe = window_exe(windows[0]) if windows else ""
        if exe:
            subprocess.Popen([exe, url], creationflags=CREATE_NO_WINDOW)
            return
        for name in sorted(app.exes):  # chrome.exe, msedge.exe, brave.exe and firefox.exe are registered by name
            try:
                os.startfile(name, arguments=f'"{url}"')
                return
            except OSError:
                continue
    os.startfile(url)


# --------------------------------------------------------------------------- keyboard and clipboard
def press(*names):
    """press("ctrl", "t"), with every key but the last held down."""
    from pynput.keyboard import Controller, Key
    keyboard = Controller()
    keys = [getattr(Key, n) if len(n) > 1 else n for n in names]
    for key in keys[:-1]:
        keyboard.press(key)
    try:
        keyboard.press(keys[-1])
        keyboard.release(keys[-1])
    finally:
        for key in reversed(keys[:-1]):
            keyboard.release(key)


def type_text(text, chunk=24, gap=0.02):
    """Type it on the keyboard, in small runs, leaving the clipboard alone.

    Line breaks are dropped on purpose: in a chat box Enter is send, and nothing here may send anything."""
    from pynput.keyboard import Controller
    keyboard = Controller()
    typed = "".join(c for c in str(text or "") if c.isprintable())
    for i in range(0, len(typed), chunk):
        keyboard.type(typed[i:i + chunk])
        time.sleep(gap)
    return len(typed)


def set_clipboard(text):
    data = text.encode("utf-16-le") + b"\x00\x00"
    for _ in range(20):  # another app may have it open for a moment
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("Couldn't open the clipboard")
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
        ptr = kernel32.GlobalLock(handle)
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(13, handle):  # CF_UNICODETEXT, Windows owns the memory from here
            kernel32.GlobalFree(handle)
            raise RuntimeError("Couldn't write to the clipboard")
    finally:
        user32.CloseClipboard()
        _mine()


_sig(user32.GetClipboardData, [UINT], wintypes.HANDLE)
_sig(user32.IsClipboardFormatAvailable, [UINT])


def clipboard_text():
    """The text on the clipboard, or None if there's none (or a picture or files instead)."""
    if not user32.IsClipboardFormatAvailable(13) or not user32.OpenClipboard(None):
        return None
    try:
        handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
        ptr = kernel32.GlobalLock(handle) if handle else None
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


_sig(user32.EnumClipboardFormats, [UINT], UINT)
_sig(user32.GetClipboardSequenceNumber, [], DWORD)
_sig(kernel32.GlobalSize, [ctypes.c_void_p], ctypes.c_size_t)
_sig(user32.FindWindowExW, [HWND, HWND, wintypes.LPCWSTR, wintypes.LPCWSTR], HWND)
GDI_FORMATS = {2, 3, 9, 14, 0x80, 0x82, 0x83, 0x8E}  # bitmaps, metafiles, palettes: handles, not memory to copy


def clipboard_snapshot():
    """Everything on the clipboard, format by format, to put back after borrowing it: text, a picture, files, and
    the marks a password manager adds so Windows keeps it out of clipboard history. [] if it's empty or busy."""
    for _ in range(20):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return []
    out = []
    try:
        fmt = user32.EnumClipboardFormats(0)
        while fmt:
            if fmt not in GDI_FORMATS:  # Windows makes CF_BITMAP again from the CF_DIB beside it
                handle = user32.GetClipboardData(fmt)
                size = kernel32.GlobalSize(handle) if handle else 0
                ptr = kernel32.GlobalLock(handle) if size else None
                if ptr:
                    try:
                        out.append((fmt, ctypes.string_at(ptr, size)))
                    finally:
                        kernel32.GlobalUnlock(handle)
            fmt = user32.EnumClipboardFormats(fmt)
    finally:
        user32.CloseClipboard()
    return out


def clipboard_restore(snapshot):
    """Puts back what clipboard_snapshot took, or empties the clipboard if it was empty."""
    for _ in range(20):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("Couldn't open the clipboard")
    try:
        user32.EmptyClipboard()
        for fmt, data in snapshot:
            handle = kernel32.GlobalAlloc(0x0042, max(1, len(data)))
            ptr = kernel32.GlobalLock(handle)
            ctypes.memmove(ptr, data, len(data))
            kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(fmt, handle):
                kernel32.GlobalFree(handle)
    finally:
        user32.CloseClipboard()
        _mine()


def clipboard_sequence():
    """A number Windows moves on at every change to the clipboard."""
    return user32.GetClipboardSequenceNumber()


OWN_CLIPS = []  # the clipboard's numbers after her own changes to it, the newest last (island_plugins.Clipboard)


def _mine():
    """The clipboard noted as hers just now, so the island never says "Copied" for what she put there."""
    OWN_CLIPS.append(user32.GetClipboardSequenceNumber())
    del OWN_CLIPS[:-8]


_sig(user32.GetClipboardFormatNameW, [UINT, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int)
_sig(user32.GetClipboardOwner, [], HWND)


def clipboard_formats():
    """(the formats on the clipboard now, as numbers, a registered one by its name, and the process that put them
    there, 0 if none said), or None while another app has it open."""
    if not user32.OpenClipboard(None):
        return None
    try:
        found, fmt = [], user32.EnumClipboardFormats(0)
        while fmt:
            if fmt >= 0xC000:  # a registered format, as a password manager's marks are
                name = ctypes.create_unicode_buffer(128)
                found.append(name.value if user32.GetClipboardFormatNameW(fmt, name, 128) else fmt)
            else:
                found.append(fmt)
            fmt = user32.EnumClipboardFormats(fmt)
        owner, pid = user32.GetClipboardOwner(), DWORD()
        if owner:
            user32.GetWindowThreadProcessId(owner, ctypes.byref(pid))
        return found, pid.value
    finally:
        user32.CloseClipboard()


def set_clipboard_files(paths):
    """Files on the clipboard, as File Explorer's Copy puts them (CF_HDROP), so Ctrl+V pastes them into a chat."""
    files = ("\0".join(str(p) for p in paths) + "\0\0").encode("utf-16-le")
    # DROPFILES: where the names start (20 bytes on), a point and a flag nobody reads, and wide names
    data = (20).to_bytes(4, "little") + bytes(12) + (1).to_bytes(4, "little") + files
    for _ in range(20):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("Couldn't open the clipboard")
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(0x0042, len(data))  # GMEM_MOVEABLE | GMEM_ZEROINIT
        ptr = kernel32.GlobalLock(handle)
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(15, handle):  # CF_HDROP
            kernel32.GlobalFree(handle)
            raise RuntimeError("Couldn't put the files on the clipboard")
    finally:
        user32.CloseClipboard()
        _mine()


def selected_files():
    """The files selected in the File Explorer window in front, as full paths: [] if none are, or another app is in
    front. Folders aren't files."""
    front = user32.GetForegroundWindow()
    if not front or _class_name(front) != "CabinetWClass":
        return []
    _com()
    import comtypes.client
    shell = comtypes.client.CreateObject("Shell.Application", dynamic=True)
    windows, tabs = shell.Windows(), []
    for i in range(windows.Count):
        try:
            window = windows.Item(i)
            if window is not None and int(window.HWND) == front:
                tabs.append(window)  # each tab of a Windows 11 File Explorer window is one, all with its handle
        except Exception:
            continue
    if len(tabs) > 1:  # the tab in front: the window's title is its name ("Downloads - File Explorer")
        title = window_title(front)
        tabs = [t for t in tabs if title.startswith(str(t.LocationName) + " - ") or title == str(t.LocationName)]
        if len(tabs) != 1:
            raise RuntimeError("I can't tell which File Explorer tab you mean. Select the file in a window with one tab")
    for window in tabs:
        try:
            items = window.Document.SelectedItems()
            paths = [items.Item(j).Path for j in range(items.Count)]
            return [p for p in paths if os.path.isfile(p)]
        except Exception:
            continue
    return []


def copied_files():
    """The files on the clipboard as File Explorer's Copy (Ctrl+C) leaves them (CF_HDROP), as full paths: [] if there
    are none or it's busy. Folders aren't files."""
    for _ in range(20):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return []
    try:
        handle = user32.GetClipboardData(15)  # CF_HDROP
        size = kernel32.GlobalSize(handle) if handle else 0
        ptr = kernel32.GlobalLock(handle) if size else None
        if not ptr:
            return []
        try:
            data = ctypes.string_at(ptr, size)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()
    start, wide = int.from_bytes(data[:4], "little"), int.from_bytes(data[16:20], "little")  # DROPFILES
    names = data[start:].decode("utf-16-le" if wide else "mbcs", "replace").split("\0")
    return [n for n in names if n and os.path.isfile(n)]


def paste(text):
    set_clipboard(text)  # stays on the clipboard too, in case the paste misses
    time.sleep(0.2)
    press("ctrl", "v")


# --------------------------------------------------------------------------- push to talk on right Alt
VK_RMENU, LLKHF_INJECTED = 0xA5, 0x10
WM_KEYDOWN, WM_SYSKEYDOWN = 0x100, 0x104
# the shortcuts the island answers (island_plugins.Clipboard, 30 October 2026, after Glance's notch, "every shortcut,
# acknowledged"), seen by the same hook: what's called with each one's name as it's pressed. They run inside the hook,
# so they must return straight away; her own key presses (injected) never count
CHORDS = []
VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN, VK_SNAPSHOT = 0x10, 0x11, 0x12, 0x5B, 0x5C, 0x2C
CHORD_KEYS = {0x56: "paste", 0x58: "cut", 0x5A: "undo", 0x59: "redo", 0x53: "save"}  # V, X, Z, Y, S with Ctrl
_sig(user32.GetAsyncKeyState, [ctypes.c_int], ctypes.c_short)


def chord(vk, held=None):
    """The shortcut a key going down makes with the keys held with it: "paste", "cut", "undo", "redo", "save" with
    Ctrl, "screenshot" for Print Screen or Win+Shift+S; None for anything else, Ctrl+Alt (AltGr, on some keyboards)
    too. Ctrl+C isn't one: the clipboard changing says that. held(vk) is True while that key's down."""
    held = held or (lambda key: bool(user32.GetAsyncKeyState(key) & 0x8000))
    windows = held(VK_LWIN) or held(VK_RWIN)
    if vk == VK_SNAPSHOT or (vk == 0x53 and windows and held(VK_SHIFT)):
        return "screenshot"
    if vk not in CHORD_KEYS or windows or not held(VK_CONTROL) or held(VK_MENU):
        return None
    if vk == 0x5A and held(VK_SHIFT):  # Ctrl+Shift+Z: redo, as most apps have it
        return "redo"
    return CHORD_KEYS[vk]


def start_ptt_listener(on_press, on_release):
    """Hold right Alt to talk. The key is swallowed, so the app in front doesn't open its menu when you let go.
    Both callbacks run inside the keyboard hook, so they must return straight away."""
    from pynput import keyboard
    held = [False]

    def event_filter(msg, data):
        if data.vkCode != VK_RMENU or data.flags & LLKHF_INJECTED:
            if CHORDS and not data.flags & LLKHF_INJECTED and msg in (WM_KEYDOWN, WM_SYSKEYDOWN) and \
                    (data.vkCode in CHORD_KEYS or data.vkCode == VK_SNAPSHOT):
                name = chord(data.vkCode)
                for told in list(CHORDS) if name else ():
                    try:
                        told(name)
                    except Exception:
                        pass
            return True
        down = msg in (WM_KEYDOWN, WM_SYSKEYDOWN)
        if down != held[0]:  # holding a key repeats key-down, only act on the change
            held[0] = down
            (on_press if down else on_release)()
        listener.suppress_event()

    listener = keyboard.Listener(win32_event_filter=event_filter)
    listener.daemon = True
    listener.start()
    return listener


# --------------------------------------------------------------------------- keep awake
ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x1, 0x2
_sig(kernel32.SetThreadExecutionState, [DWORD], DWORD)
_awake = {"stop": None}


def keep_awake(on):
    """The PC kept from sleeping, and its screen from going off, while on, as Glance's Keep Awake has it (30 October
    2026, the island's Controls): Windows holds it for as long as the thread that asked lives, so a thread of its own
    asks and waits, and it ends with her. True if it's on now."""
    if on and _awake["stop"] is None:
        stop = threading.Event()

        def hold():
            kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
            stop.wait()
            kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        _awake["stop"] = stop
        threading.Thread(target=hold, name="keep-awake", daemon=True).start()
    elif not on and _awake["stop"] is not None:
        _awake["stop"].set()
        _awake["stop"] = None
    return awake()


def awake():
    """True while keep_awake has the PC kept awake."""
    return _awake["stop"] is not None


# --------------------------------------------------------------------------- full speed
class POWER_THROTTLING_STATE(ctypes.Structure):  # PROCESS_POWER_THROTTLING_STATE
    _fields_ = [("Version", DWORD), ("ControlMask", DWORD), ("StateMask", DWORD)]


PROCESS_POWER_THROTTLING, THROTTLING_VERSION, THROTTLE_SPEED = 4, 1, 0x1  # ..._EXECUTION_SPEED
_sig(kernel32.GetCurrentProcess, [], wintypes.HANDLE)
_sig(kernel32.SetProcessInformation, [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, DWORD])


def full_speed(on):
    """Her process kept out of Windows' power throttling (EcoQoS) while on, and Windows left to decide again when
    off. Her windows are seldom the one in front, so on battery Windows takes her for background work and runs her
    on its slow cores: on 4 November, throttled, finding a hand in a camera frame took 55 ms and hand control kept up
    with 16 frames a second; not throttled, 14 ms and all 30. True if Windows took it."""
    state = POWER_THROTTLING_STATE(THROTTLING_VERSION, THROTTLE_SPEED if on else 0, 0)
    return bool(kernel32.SetProcessInformation(kernel32.GetCurrentProcess(), PROCESS_POWER_THROTTLING,
                                               ctypes.byref(state), ctypes.sizeof(state)))


# --------------------------------------------------------------------------- microphones
def _is_mapper(name):
    return name.startswith(("Microsoft Sound Mapper", "Primary Sound Capture"))


def input_devices():
    """Mics on the default audio API, so each one is listed once (Windows lists them under up to four APIs)."""
    import sounddevice as sd
    try:
        api = sd.query_hostapis(sd.default.hostapi)
    except Exception:
        return []
    names = []
    for index in api["devices"]:
        dev = sd.query_devices(index)
        if dev["max_input_channels"] > 0 and not _is_mapper(dev["name"]) and dev["name"] not in names:
            names.append(dev["name"])
    return names


LOOPBACK = re.compile(r"stereo mix|what u hear|wave out|loopback", re.I)  # records what the PC plays, not your voice


def auto_input():
    """(index, name) of the mic to use when none is picked: Windows' default, unless that's Stereo Mix."""
    default = default_input_name()
    if not LOOPBACK.search(default):
        return None, default
    for name in input_devices():
        if not LOOPBACK.search(name):
            return input_device(name), name
    return None, default


def input_device(name):
    """sounddevice index for a mic name from input_devices(), or None if it's gone."""
    import sounddevice as sd
    if not name:
        return None
    try:
        for index in sd.query_hostapis(sd.default.hostapi)["devices"]:
            dev = sd.query_devices(index)
            if dev["name"] == name and dev["max_input_channels"] > 0:
                return index
    except Exception:
        pass
    return None


def speech_input(name=""):
    """(index, full name) of a mic on WASAPI, the audio API where Windows can take what the PC is playing out of the
    mic. name is one from input_devices(), which cuts names at 31 characters, or "" for the automatic one."""
    import sounddevice as sd
    name = (name if input_device(name) is not None else auto_input()[1]).strip()
    try:
        api = next(i for i, a in enumerate(sd.query_hostapis()) if "WASAPI" in a["name"])
        for index in sd.query_hostapis(api)["devices"]:
            dev = sd.query_devices(index)
            if dev["max_input_channels"] > 0 and dev["name"].startswith(name) and not LOOPBACK.search(dev["name"]):
                return index, dev["name"]
    except Exception:
        pass
    return None


def default_input_name():
    import sounddevice as sd
    try:
        return sd.query_devices(kind="input")["name"]
    except Exception:
        return "none found"


# --------------------------------------------------------------------------- window helpers for the UI
def prepare_gui(app_id="HeyHarry.App"):
    """Sharp text on high-DPI screens, and a taskbar button of our own instead of Python's."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(app_id))
    except Exception:
        pass


_mutex = []


LOCKS = ("HeyHarrySingleInstance", "HeyJevSingleInstance")  # hers, and Hey Jev's, so neither opens over the other


def single_instance(names=LOCKS):
    """False if Harry is already running, the way a Mac app only ever opens once."""
    already = False
    for name in names:
        handle = kernel32.CreateMutexW(None, False, f"Local\\{name}")
        already = already or ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
        _mutex.append(handle)
    return not already


def show_existing(*titles):
    """Her window brought back by its title, the first of titles there is, from a second start."""
    hwnd = next(filter(None, (user32.FindWindowW("TkTopLevel", title) for title in titles)), None)
    if hwnd:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
    return bool(hwnd)


def root_hwnd(widget_id):
    return user32.GetAncestor(widget_id, GA_ROOT)


def make_overlay(hwnd):
    """Clicks go through, never takes focus, not in the taskbar or Alt+Tab."""
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
                          | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)


def show_no_activate(hwnd, x, y, w, h):
    user32.SetWindowPos(hwnd, HWND_TOPMOST, x, y, w, h, SWP_NOACTIVATE | SWP_SHOWWINDOW)


def set_click_through(hwnd, on):
    """Clicks go through the overlay to what's under it (on), or it takes them, as the island does while you point
    at its buttons. It never takes the focus either way."""
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    new = (style | WS_EX_TRANSPARENT) if on else (style & ~WS_EX_TRANSPARENT)
    if new != style:
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new)


_sig(user32.GetCursorPos, [ctypes.POINTER(wintypes.POINT)])


def cursor_pos():
    """Where the mouse is, in real pixels."""
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


VK_LBUTTON, VK_RBUTTON, VK_MBUTTON = 0x01, 0x02, 0x04


def mouse_down():
    """True while a mouse button is held down, as Windows has it this moment (GetAsyncKeyState, a few microseconds):
    how the screen watch sees a click, looking ten times a second, with no hook in the way of your mouse."""
    return any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (VK_LBUTTON, VK_RBUTTON, VK_MBUTTON))


def hide_window(hwnd):
    user32.ShowWindow(hwnd, SW_HIDE)


# --------------------------------------------------------------------------- signing in and coming back
wtsapi32 = ctypes.WinDLL("wtsapi32")
_sig(wtsapi32.WTSQuerySessionInformationW, [wintypes.HANDLE, DWORD, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p),
                                             ctypes.POINTER(DWORD)])
_sig(wtsapi32.WTSFreeMemory, [ctypes.c_void_p], None)


class _Session(ctypes.Structure):  # WTSINFOEXW at level 1, as far as the lock flag
    _fields_ = [("level", DWORD), ("_pad", DWORD), ("id", ctypes.c_ulong), ("state", ctypes.c_int),
                ("flags", ctypes.c_long)]


def session_locked():
    """True while the lock screen is up, False when you're at the desktop, None if Windows won't say."""
    buf, size = ctypes.c_void_p(), DWORD()
    if not wtsapi32.WTSQuerySessionInformationW(None, 0xFFFFFFFF, 25, ctypes.byref(buf), ctypes.byref(size)):
        return None  # 25 is WTSSessionInfoEx, 0xFFFFFFFF this session
    try:
        return {0: True, 1: False}.get(_Session.from_address(buf.value).flags)
    finally:
        wtsapi32.WTSFreeMemory(buf)


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", UINT), ("dwTime", DWORD)]


_sig(user32.GetLastInputInfo, [ctypes.POINTER(LASTINPUTINFO)])
_sig(kernel32.GetTickCount, [], DWORD)


def idle_seconds():
    """Seconds since the last key or mouse input anywhere in this session (GetLastInputInfo): how a job in the
    background knows you've stopped typing before it takes the screen (agent.screen). 0.0 if Windows won't say, so
    it waits rather than go. Input she sends herself counts too, which only makes a job wait longer."""
    info = LASTINPUTINFO(cbSize=ctypes.sizeof(LASTINPUTINFO))
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return ((kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0  # the tick count wraps after 49 days


def window_of(hwnd):
    """(hwnd, exe, title) of a window, as foreground() gives the one in front: a job's own window, read whether it's
    in front or not. (None, "", "") once it's gone."""
    if not hwnd or not user32.IsWindow(hwnd):
        return None, "", ""
    return hwnd, os.path.basename(window_exe(hwnd)).lower(), window_title(hwnd)


def window_rect(hwnd):
    """Where a window is, (left, top, right, bottom) in real pixels, or None: for a picture of it (vision.of_window)."""
    r = RECT()
    with _real_pixels():
        if not hwnd or not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return None
    return r.left, r.top, r.right, r.bottom


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"  # what starts when you sign in, also in Task Manager


def startup_command():
    """The venv's pythonw.exe running app.py, so no console flashes up, with --startup so it knows why it started."""
    here = os.path.dirname(os.path.abspath(__file__))
    exe = os.path.join(here, ".venv", "Scripts", "pythonw.exe")
    return f'"{exe if os.path.exists(exe) else sys.executable}" "{os.path.join(here, "app.py")}" --startup'


def starts_with_windows(name=NAME):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return bool(winreg.QueryValueEx(key, name)[0])
    except OSError:
        return False


def set_start_with_windows(on, name=NAME):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if on:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass


def move_start_entry():
    """Hey Jev's start-up entry, if you had one, as Hey Harry's: she still starts when you sign in, and Settings
    shows it on."""
    try:
        if starts_with_windows(OLD_NAME):
            set_start_with_windows(True)
            set_start_with_windows(False, OLD_NAME)
            print("moved the start-up entry to Hey Harry")
    except OSError as exc:
        print(f"couldn't move the start-up entry: {exc!r}")


# --------------------------------------------------------------------------- the screen, for vision mode
gdi32 = ctypes.WinDLL("gdi32")
_sig(user32.GetDC, [HWND], wintypes.HDC)
_sig(user32.ReleaseDC, [HWND, wintypes.HDC], ctypes.c_int)
_sig(user32.SetWindowDisplayAffinity, [HWND, DWORD])
_sig(user32.WindowFromPoint, [wintypes.POINT], HWND)
_sig(dwmapi.DwmFlush, [], ctypes.c_long)
_sig(gdi32.CreateCompatibleDC, [wintypes.HDC], wintypes.HDC)
_sig(gdi32.CreateCompatibleBitmap, [wintypes.HDC, ctypes.c_int, ctypes.c_int], wintypes.HBITMAP)
_sig(gdi32.SelectObject, [wintypes.HDC, wintypes.HGDIOBJ], wintypes.HGDIOBJ)
_sig(gdi32.BitBlt, [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HDC, ctypes.c_int,
                    ctypes.c_int, DWORD])
_sig(gdi32.GetDIBits, [wintypes.HDC, wintypes.HBITMAP, UINT, UINT, ctypes.c_void_p, ctypes.c_void_p, UINT], ctypes.c_int)
_sig(gdi32.DeleteObject, [wintypes.HGDIOBJ])
_sig(gdi32.DeleteDC, [wintypes.HDC])


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", DWORD), ("biWidth", LONG), ("biHeight", LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", DWORD), ("biSizeImage", DWORD),
                ("biXPelsPerMeter", LONG), ("biYPelsPerMeter", LONG), ("biClrUsed", DWORD), ("biClrImportant", DWORD)]


try:  # Windows 10 1607 and later
    _sig(user32.SetThreadDpiAwarenessContext, [ctypes.c_void_p], ctypes.c_void_p)
    _set_dpi_context = user32.SetThreadDpiAwarenessContext
except AttributeError:
    _set_dpi_context = None
NO_CAPTURE = []  # windows left out of screenshots, like the popup (bubble.py adds it)


@contextlib.contextmanager
def _real_pixels():
    """Positions in real pixels on this thread while inside, whatever the display scaling, so a screenshot and a
    click agree on where things are."""
    old = _set_dpi_context(ctypes.c_void_p(-4)) if _set_dpi_context else None  # per monitor, version 2
    try:
        yield
    finally:
        if old:
            _set_dpi_context(ctypes.c_void_p(old))


def screenshot():
    """The screen the window in front is on: (height, width, 3) RGB as a numpy array, and where that screen is,
    (left, top, right, bottom) in real pixels. Windows in NO_CAPTURE, like the popup, are left out."""
    import numpy as np
    hidden = [hw for hw in NO_CAPTURE if user32.SetWindowDisplayAffinity(hw, 0x11)]  # WDA_EXCLUDEFROMCAPTURE
    try:
        if hidden:  # a frame or two for Windows to draw the screen without them
            dwmapi.DwmFlush()
            dwmapi.DwmFlush()
        with _real_pixels():
            monitor = user32.MonitorFromWindow(user32.GetForegroundWindow(), MONITOR_DEFAULTTOPRIMARY)
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(info)
            if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                raise RuntimeError("I couldn't find the screen")
            r = info.rcMonitor
            left, top, w, h = r.left, r.top, r.right - r.left, r.bottom - r.top
            screen = user32.GetDC(None)
            mem = gdi32.CreateCompatibleDC(screen)
            bmp = gdi32.CreateCompatibleBitmap(screen, w, h)
            old = gdi32.SelectObject(mem, bmp)
            try:
                buf = ctypes.create_string_buffer(w * h * 4)
                bits = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h, biPlanes=1,
                                        biBitCount=32)  # top row first: blue, green, red and a spare byte a pixel
                if not gdi32.BitBlt(mem, 0, 0, w, h, screen, left, top, 0x00CC0020) or \
                        gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bits), 0) != h:
                    raise RuntimeError("I couldn't take a screenshot")
            finally:
                gdi32.SelectObject(mem, old)
                gdi32.DeleteObject(bmp)
                gdi32.DeleteDC(mem)
                user32.ReleaseDC(None, screen)
    finally:
        for hw in hidden:
            user32.SetWindowDisplayAffinity(hw, 0)
    return np.frombuffer(buf, np.uint8).reshape(h, w, 4)[:, :, 2::-1].copy(), (left, top, left + w, top + h)


PW_RENDERFULLCONTENT = 2  # what a browser or an app drawn by DirectComposition shows too, not a black box
_sig(user32.PrintWindow, [HWND, wintypes.HDC, UINT])


def window_image(hwnd):
    """One window as it looks, even behind others, from the window itself (PrintWindow), not the screen: (height,
    width, 3) RGB. None if it's gone or minimised, or Windows wouldn't draw it. For a watch on a window you're not
    looking at (watchers.py), so nothing else on the screen is in it."""
    import numpy as np
    if not hwnd or not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        return None
    with _real_pixels():
        r = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return None
        w, h = r.right - r.left, r.bottom - r.top
        if w < 8 or h < 8:
            return None
        screen = user32.GetDC(None)
        mem = gdi32.CreateCompatibleDC(screen)
        bmp = gdi32.CreateCompatibleBitmap(screen, w, h)
        old = gdi32.SelectObject(mem, bmp)
        try:
            buf = ctypes.create_string_buffer(w * h * 4)
            bits = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h, biPlanes=1,
                                    biBitCount=32)
            if not user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT) or \
                    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bits), 0) != h:
                return None
        finally:
            gdi32.SelectObject(mem, old)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(mem)
            user32.ReleaseDC(None, screen)
    rgb = np.frombuffer(buf, np.uint8).reshape(h, w, 4)[:, :, 2::-1]
    return None if not rgb.any() else rgb.copy()  # all black: it wouldn't draw itself


def window_at(x, y):
    """The .exe of the window at a point on the screen, in real pixels, or ""."""
    hwnd = root_at(x, y)
    return window_exe(hwnd) if hwnd else ""


def root_at(x, y):
    """The top-level window at a point on the screen, in real pixels, or None."""
    with _real_pixels():
        hwnd = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    return user32.GetAncestor(hwnd, GA_ROOT) if hwnd else None


def owner_of(hwnd):
    """The app window a window is part of: itself, or for a dialog, a menu or a list that dropped down from it, the
    window that owns it. None for none."""
    return user32.GetAncestor(hwnd, GA_ROOTOWNER) if hwnd else None


def front_area():
    """Where the window in front is, (left, top, right, bottom) in real pixels, with what's open from it, which can
    reach outside it: its dialogs, and the menus and lists that dropped down from it (owner_of), and a menu (#32768).
    None if there's no window in front. vision.capture cuts the task's picture to it."""
    front = user32.GetForegroundWindow()
    if not front:
        return None
    root, boxes = owner_of(front), []

    def visit(hwnd, _):
        if hwnd == front or (user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd) and
                             (owner_of(hwnd) == root or _class_name(hwnd) == "#32768")):
            rect = RECT()  # without the invisible border Windows 10 and 11 put round a window to resize it by
            if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect),
                                            ctypes.sizeof(rect)) == 0 or user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                if rect.right > rect.left and rect.bottom > rect.top:
                    boxes.append((rect.left, rect.top, rect.right, rect.bottom))
        return True
    with _real_pixels():
        user32.EnumWindows(WNDENUMPROC(visit), 0)
    if not boxes:
        return None
    return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


def window_exists(hwnd):
    """True if hwnd is still a window: Outlook's new mail closes once it's sent, a dialog in front of it doesn't."""
    return bool(hwnd) and bool(user32.IsWindow(hwnd))


def minimised(hwnd):
    """True if the window is minimised to the taskbar."""
    return bool(hwnd) and bool(user32.IsIconic(hwnd))


def click(x, y, button="left", double=False):
    """Click at a point on the screen, in real pixels. The pointer stays there, as if you'd clicked."""
    from pynput.mouse import Button, Controller
    mouse = Controller()
    with _real_pixels():
        mouse.position = (int(x), int(y))
        time.sleep(0.08)  # menus and buttons react to the pointer coming over them
        mouse.click(Button.right if button == "right" else Button.left, 2 if double else 1)


def work_area():
    """(left, top, right, bottom) of the screen you're working on, minus the taskbar."""
    monitor = user32.MonitorFromWindow(user32.GetForegroundWindow(), MONITOR_DEFAULTTOPRIMARY)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return 0, 0, 1920, 1040
    r = info.rcWork
    return r.left, r.top, r.right, r.bottom


# --------------------------------------------------------------------------- Native Windows Speech Synthesis (OneCore / SAPI5)
def native_voices():
    """Discover available Windows built-in voices (OneCore natural voices and SAPI5 desktop voices).
    Returns [(id, description, is_onecore)]. Costs 0 MB RAM."""
    voices = []
    # 1. OneCore voices (natural Windows 10/11 voices)
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens") as k:
            for i in range(winreg.QueryInfoKey(k)[0]):
                sub = winreg.EnumKey(k, i)
                try:
                    with winreg.OpenKey(k, sub) as sk:
                        desc = winreg.QueryValueEx(sk, "")[0]
                        voices.append((f"onecore:{sub}", desc, True))
                except OSError:
                    pass
    except OSError:
        pass
    # 2. SAPI5 desktop voices
    try:
        _com()
        import comtypes.client
        v = comtypes.client.CreateObject("SAPI.SpVoice")
        count = v.GetVoices().Count
        for i in range(count):
            desc = v.GetVoices().Item(i).GetDescription()
            sid = v.GetVoices().Item(i).Id
            voices.append((f"sapi:{sid}", desc, False))
    except Exception:
        pass
    return voices


_native_voice_cache = {}


def get_native_spvoice(voice_id=None):
    """Reuse cached SAPI.SpVoice object per thread for sub-10ms speech start. Per thread, since a COM object made on
    one thread mustn't be used from another."""
    _com()
    import comtypes.client
    key = (threading.get_ident(), str(voice_id or ""))
    if key in _native_voice_cache:
        return _native_voice_cache[key]
    v = comtypes.client.CreateObject("SAPI.SpVoice")
    if voice_id and str(voice_id).startswith("onecore:"):
        token_name = voice_id[len("onecore:"):]
        try:
            tok = comtypes.client.CreateObject("SAPI.SpObjectToken")
            tok.SetId(rf"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens\{token_name}")
            v.Voice = tok
        except Exception:
            pass
    elif voice_id and str(voice_id).startswith("sapi:"):
        token_id = voice_id[len("sapi:"):]
        try:
            tok = comtypes.client.CreateObject("SAPI.SpObjectToken")
            tok.SetId(token_id)
            v.Voice = tok
        except Exception:
            pass
    else:
        # Default to best natural OneCore voice available (Heera, Ravi, Mark, Zira, David)
        for cand in ("MSTTS_V110_enIN_HeeraM", "MSTTS_V110_enIN_RaviM", "MSTTS_V110_enUS_MarkM",
                     "MSTTS_V110_enUS_ZiraM", "MSTTS_V110_enUS_DavidM"):
            try:
                tok = comtypes.client.CreateObject("SAPI.SpObjectToken")
                tok.SetId(rf"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens\{cand}")
                v.Voice = tok
                break
            except Exception:
                pass
    _native_voice_cache[key] = v
    return v


def speak_native(text, voice=None, voice_id=None, wait=True, stop=None):
    """Speak text using Windows native OneCore / SAPI5 voice. 0 MB added RAM, < 15ms latency. stop(): True to stop
    part way, checked every 50 ms (the voice is this thread's, so only this thread can stop it)."""
    v = get_native_spvoice(voice or voice_id)
    if stop is None or not wait:
        v.Speak(str(text or ""), 0 if wait else 1)
        return
    v.Speak(str(text or ""), 1)  # SVSFlagsAsync
    while not v.WaitUntilDone(50):
        if stop():
            v.Speak("", 3)  # SVSFPurgeBeforeSpeak | async: what it was saying stops
            return


def native_to_wav(text, wav_path, voice=None, voice_id=None):
    """Render speech to WAV file via native Windows TTS in ~20ms, 0 MB added RAM."""
    _com()
    import comtypes.client
    v = get_native_spvoice(voice or voice_id)
    fs = comtypes.client.CreateObject("SAPI.SpFileStream")
    fs.Open(wav_path, 3, False)
    v.AudioOutputStream = fs
    try:
        v.Speak(str(text or ""), 0)
    finally:
        fs.Close()
        v.AudioOutputStream = None


# --------------------------------------------------------------------------- agent-desktop element inspection
# Buttons the fast path never presses: the vision path, with its own rules, decides those.
RISKY_CLICKS = re.compile(r"\b(?:send|delete|remove|erase|buy|pay|purchase|order|checkout|post|publish|submit|sign ?out|"
                          r"log ?out|uninstall|format|reset|discard|unsubscribe|transfer|confirm|allow|accept|install)\b")

# agent-desktop gives the same controls platform-neutral names. The rest of Harry keeps its old small vocabulary so
# learned procedures still find an edit, radio or list item by the role saved before this change.
_AGENT_ROLES = {"button": "button", "menubutton": "button", "checkbox": "checkbox", "switch": "checkbox",
                "combobox": "combobox", "textfield": "edit", "link": "link", "option": "listitem",
                "menuitem": "menuitem", "radiobutton": "radio", "tab": "tab", "document": "document"}
ROLES = tuple(dict.fromkeys(_AGENT_ROLES.values()))
BROWSER_EXES = {"chrome.exe", "msedge.exe", "brave.exe"}
OMNIBOX = "Address and search bar"
# Direction marks and a shortcut hint on the end of a name: Gmail's Send button is "Send \u202a(Ctrl-Enter)\u202c".
BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
SHORTCUT_HINT = re.compile(r"\s*\((?:ctrl|control|alt|shift|win|cmd)\s*[-+][^()]*\)$", re.I)
_sleep, _clock = time.sleep, time.monotonic  # swapped for a fake clock in tests, so polling takes no time
DESKTOP_LIMIT = _desktop.DEFAULT_OBSERVE_MS
DESKTOP_PROOF = 8000  # ms for the whole fresh read a changed control is found again in: a cut one can't prove it
SLOW_FOR = 60.0
_slow = {}  # window -> until when agent-desktop timed out on it
NO_FOCUS_FREE = "That needs the screen: it has no way in but the keyboard or the mouse"


def clean_name(name):
    """A control's name as a person reads it: no direction marks, single spaces, and no shortcut hint."""
    return SHORTCUT_HINT.sub("", " ".join(BIDI.sub("", str(name or "")).split())).strip()


def _text(value):
    """What's typed in a control, without direction marks and with single spaces."""
    return " ".join(BIDI.sub("", str(value or "")).split())


def _role(el):
    return _AGENT_ROLES.get(getattr(el, "raw_role", ""), "")


def _shown(el):
    """On screen, enabled and with a size: one a person could use."""
    rect, states = getattr(el, "rect", None), getattr(el, "states", set())
    return bool(rect and rect[2] > rect[0] and rect[3] > rect[1] and
                not states.intersection(("disabled", "hidden", "offscreen")))


def _desktop_snapshot(hwnd=None, timeout_ms=None):
    """The raw bounded agent-desktop snapshot. This one seam is faked by the UI helper tests."""
    return _desktop.snapshot(hwnd, timeout_ms=timeout_ms or DESKTOP_LIMIT)


def _controls(snap):
    return [el for el in snap.elements if _role(el) and _shown(el)]


def ui_info(el):
    """What a control is: name, old role, AutomationId, password flag and its agent-desktop element."""
    if el is None:
        raise LookupError("that control is gone")
    return {"name": clean_name(getattr(el, "name", "")), "role": _role(el),
            "aid": str(getattr(el, "aid", "") or ""), "password": bool(getattr(el, "password", False)),
            "class_name": str(getattr(el, "class_name", "") or ""),
            "kind": str(getattr(el, "kind", "") or ""),
            "item_type": str(getattr(el, "item_type", "") or ""), "el": el}


def _matching(snap, want, role, aid):
    items = [el for el in _controls(snap) if role not in ROLES or _role(el) == role]
    if aid:
        by_id = [el for el in items if str(el.aid) == str(aid)]
        if by_id:
            return by_id
    return [el for el in items if want and clean_name(el.name).lower() == want]


def _find(want, role, aid, hwnd):
    """Shown matching controls in hwnd. An incomplete read raises rather than pretending one is absent."""
    hwnd = hwnd or user32.GetForegroundWindow()
    if not hwnd:
        raise LookupError("no window in front to read")
    snap = _desktop_snapshot(hwnd)
    hits = _matching(snap, want, role, aid)
    if snap.cut and not hits:
        raise LookupError("agent-desktop couldn't read the whole window")
    return hits


def find_ui(name=None, role=None, aid=None, hwnd=None, wait=0.0, unique=True, strict=False):
    """The shown control in hwnd by AutomationId, else exact clean name; exactly one unless unique is false."""
    want = clean_name(name).lower()
    if not want and not aid:
        return None
    end = _clock() + wait
    while True:
        try:
            hits = _find(want, role, aid, hwnd)
        except Exception as exc:
            if strict:
                raise
            print(f"  agent-desktop: {exc!r}")
            hits = []
        if hits and (len(hits) == 1 or not unique):
            return hits[0]
        if len(hits) > 1 or _clock() >= end:
            return None
        _sleep(0.3)


def find_all_ui(name=None, role=None, aid=None, hwnd=None):
    """Every shown control find_ui would find, in screen-reader order."""
    want = clean_name(name).lower()
    if not want and not aid:
        return []
    try:
        return _find(want, role, aid, hwnd)
    except Exception as exc:
        print(f"  agent-desktop: {exc!r}")
        return []


def _hwnd(el):
    window = getattr(getattr(el, "snapshot", None), "window_id", "")
    try:
        return int(window[2:]) if window.startswith("w-") else None
    except ValueError:
        return None


def _refresh(el):
    """Replace one stale ref with the only live control of the same identity, from a whole fresh read of its window:
    a cut one, or one whose refs agent-desktop can't tell apart, can't say that one's the only one."""
    hwnd = _hwnd(el) or user32.GetForegroundWindow()
    if not hwnd:
        raise LookupError("that control changed and its window is gone")
    snap = _desktop_snapshot(hwnd, timeout_ms=DESKTOP_PROOF)
    if snap.cut or snap.identity_unproven:
        raise LookupError("that control changed and its window couldn't be read whole again")
    hits = _matching(snap, clean_name(el.name).lower(), _role(el), el.aid)
    if len(hits) != 1:
        raise LookupError("that control changed and isn't uniquely identifiable now")
    el.__dict__.update(hits[0].__dict__)
    return el


def _live(el, prop):
    try:
        return _desktop.get(el, prop)
    except _desktop.DesktopError as exc:
        if exc.code == "STALE_REF" and exc.safe:
            return _desktop.get(_refresh(el), prop)
        raise


def _ref_action(el, command, value=None, headed=False, settled=None):
    more = {} if settled is None else {"settled": settled}
    try:
        return _desktop.act(el, command, value, headed=headed, **more)
    except _desktop.DesktopError as exc:
        # STALE_REF proves nothing was delivered. Refresh once and let the ref's uniqueness check guard the retry.
        if exc.code == "STALE_REF" and exc.safe:
            return _desktop.act(_refresh(el), command, value, headed=headed, **more)
        raise


def ui_focus_free(el, text=None, state=None):
    """True if ui_act can do this semantically without focus, keyboard or pointer side effects."""
    if state in ("on", "off"):
        return True  # check/uncheck is semantic, or ui_act refuses when the control cannot Toggle
    if text is not None:
        return "SetValue" in el.actions and "readonly" not in el.states and not el.password
    return "Click" in el.actions


def ui_is_focused(el):
    """True only when a fresh state read says this control has keyboard focus."""
    try:
        return "focused" in set(_live(el, "states") or ())
    except Exception:
        return False


def ui_focus(el):
    """True once agent-desktop has put the keyboard on el and seen it there. It only does that in the window in
    front, so after its safe no the window is brought forward and it's asked once more, as UI Automation's SetFocus
    brought it forward itself (3 November: "did not become foreground before headed delivery")."""
    try:
        done = _ref_action(el, "focus", headed=True)
    except _desktop.DesktopError as exc:
        hwnd = _hwnd(el)
        if exc.code != "ACTION_FAILED" or not exc.safe or not hwnd:
            raise
        bring_to_front(hwnd)
        _sleep(0.15)
        done = _ref_action(el, "focus", headed=True)
    if ((done or {}).get("disposition") or {}).get("delivery") == "delivered_verified":
        return True
    return ui_is_focused(el)


def _modal_opened(el):
    """While a press runs: True once its window has been turned off, which a modal question over it does. None if it
    isn't on now, so a question there from before isn't taken for this press's."""
    hwnd = _hwnd(el)
    if not hwnd or not user32.IsWindowEnabled(hwnd):
        return None
    return lambda: not user32.IsWindowEnabled(hwnd)


def ui_act(el, text=None, state=None, caret=False, focus_free=False):
    """Use a control as a person would, and say how: a switch turned "on" or "off" only if it isn't already
    ("already"); text put in by agent-desktop's set-value ("set"), else by focusing it and pasting, the clipboard put
    back after ("pasted"); else pressed by its own action ("invoked"); else clicked in its middle ("clicked"). caret:
    the text goes where the cursor is (a "type" step), never by set-value, which puts it in place of everything in
    the box. focus_free: semantic actions only, for a job in the background without the screen (ui_focus_free):
    RuntimeError rather than the focus and a paste, or a click. Never a password."""
    if state in ("on", "off"):
        if "Toggle" not in el.actions:
            raise RuntimeError("That isn't something I can switch on or off")
        now = ui_toggle(el)
        if now == state:
            return "already"
        _ref_action(el, "check" if state == "on" else "uncheck")
        return "toggled"
    if text is not None:
        if el.password:
            raise RuntimeError("I won't type a password")
        if not caret and "SetValue" in el.actions and "readonly" not in el.states:
            _ref_action(el, "set-value", str(text))
            return "set"
        if focus_free:
            raise RuntimeError(NO_FOCUS_FREE)
        # pasted, as before agent-desktop: its typing sends a line break as a key of its own, which a chat box can
        # take for Send, and a paste is one key however long the text
        if not ui_focus(el):
            raise RuntimeError("I couldn't put the cursor in that box")
        kept = clipboard_snapshot()
        try:
            paste(str(text))
            time.sleep(0.3)  # the app reads the clipboard after the keys: too soon and it pastes what was there
        finally:
            clipboard_restore(kept)
        return "pasted"
    if "Click" in el.actions:
        try:
            _ref_action(el, "click", settled=_modal_opened(el))
        except _desktop.DesktopError as exc:
            # A WinForms or Win32 button that opens a modal question (Are you sure?, Save As) doesn't come back
            # from its Invoke till the question closes, so agent-desktop waits on, though it was pressed (3
            # November, the smoke window's Ask First). What's on the screen next says if it worked: it's never
            # pressed again to find out
            if exc.code != "TIMEOUT" or exc.delivery == "not_delivered":
                raise
            print("  agent-desktop: the press didn't come back, taken as pressed")
        return "invoked"
    if focus_free:
        raise RuntimeError(NO_FOCUS_FREE)
    rect = ui_rect(el) or el.rect
    _desktop.mouse_click(rect)
    return "clicked"


def ui_value(el):
    """What's typed in a control, or None for a password, an unreadable value or a stale control."""
    if el is None or getattr(el, "password", False):
        return None
    try:
        value = _live(el, "value")
        return _text(value) if isinstance(value, str) else None
    except Exception:
        return None


def ui_toggle(el):
    """'on' or 'off' for a switch or checkbox, else None."""
    if el is None or not ({getattr(el, "raw_role", "")} & {"checkbox", "switch"} or "Toggle" in el.actions):
        return None
    try:
        states = set(_live(el, "states") or ())
        return None if "indeterminate" in states else "on" if "checked" in states else "off"
    except Exception:
        return None


def ui_rect(el):
    """A control's current (left, top, right, bottom), in real screen pixels, or None."""
    try:
        return _desktop.rectangle(_live(el, "bounds"))
    except Exception:
        return None


def ui_click_point(x, y):
    """Click an already-checked foreground point through agent-desktop's headed pointer input."""
    _desktop.point_click(x, y)


def _contains(rect, x, y):
    return bool(rect and rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3])


def _area(rect):
    return (rect[2] - rect[0]) * (rect[3] - rect[1]) if rect else 0


def _climb(first):
    """first, or the control that can be pressed around it (a button around its label), never the page."""
    el = first
    for depth in range(8):
        if el is None or (depth and el.raw_role == "document"):
            break
        if _role(el) or el.actions.intersection(("Click", "Toggle")):
            return {**ui_info(el), "climbed": bool(depth)}
        el = el.parent
    return {**ui_info(first), "climbed": False}


def ui_at(x, y):
    """What's at a screen point, in real pixels, from one snapshot of the window in front: the deepest control
    there, or the one around it that can be pressed. agent-desktop has no hit test of its own, so where controls
    overlap and which is on top can't be told, one inside a dialog wins, then one whose name is a risky press: the
    gate then asks, rather than taking the harmless one under it. None if it can't say."""
    try:
        return ui_at_in(_desktop_snapshot(user32.GetForegroundWindow()), x, y)
    except Exception as exc:
        print(f"  agent-desktop: {exc!r}")
        return None


def ui_at_in(snap, x, y):
    """ui_at's answer from a snapshot already read: the screen watch keeps its last one (7 November 2026), so what's
    under the pointer, or what was just clicked, is named with no read of its own, a few milliseconds of sums over
    what's kept. None if nothing read is there."""
    inside = [el for el in snap.elements[1:] if _shown(el) and _contains(el.rect, x, y)]
    if not inside:
        return None
    leaves = [el for el in inside if not any(other.has_ancestor(el) for other in inside)]
    dialogs = [el for el in inside if _is_dialog(el)]
    if dialogs:  # a dialog is drawn over the page it's in
        top = max(dialogs, key=lambda el: el.depth)
        leaves = [el for el in leaves if el is top or el.has_ancestor(top)] or leaves
    found = [_climb(el) for el in sorted(leaves, key=lambda el: (-el.depth, _area(el.rect)))]
    return next((it for it in found if RISKY_CLICKS.search(it["name"].lower())), found[0])


def ui_focused():
    """The deepest control with keyboard focus in the foreground window, as ui_info, or None."""
    try:
        snap = _desktop_snapshot(user32.GetForegroundWindow())
        found = [el for el in snap.elements if "focused" in el.states and _role(el)]
        return ui_info(max(found, key=lambda el: el.depth)) if found else None
    except Exception as exc:
        print(f"  agent-desktop: {exc!r}")
        return None


def _is_dialog(el):
    """A dialog: a window's own, a web page's (ARIA dialog or alertdialog, Gmail's new mail), or a modal one."""
    return el.raw_role == "dialog" or getattr(el, "subrole", "") in ("dialog", "alertdialog") or \
        "modal" in el.states


def _scope(el, include_window=True):
    """The dialog el is in, else its window (include_window), else None."""
    at = el
    while at is not None:
        if _is_dialog(at) or include_window and at.raw_role == "window":
            return at
        at = at.parent
    return None


def _words(elements, most):
    out = []
    for item in elements:
        if item.password:
            continue
        for value in (clean_name(item.name), _text(item.value)):
            if value and value not in out:
                out.append(value)
        if len(" ".join(out)) >= most:
            break
    return " ".join(out)[:most]


def ui_text(el, most=6000):
    """The readable text below an element in the snapshot that produced its ref."""
    if el is None or not getattr(el, "snapshot", None):
        return ""
    return _words(el.descendants(), most)


def ui_dialog_text(el, most=300):
    """The words of the dialog a control is in (else its window), up to most characters: its title and its texts
    first, so an OK is judged by what it says yes to, like "Delete this conversation?", not cut off by its buttons."""
    try:
        box = _scope(el)
        if box is None:
            return ""
        below = box.descendants()
        return _words([box] + [it for it in below if it.raw_role == "statictext"] +
                      [it for it in below if it.raw_role != "statictext"], most)
    except Exception as exc:
        print(f"  agent-desktop: {exc!r}")
        return ""


def find_and_click_ui_element(target_name, hwnd=None):
    """Click the one safe, exact button-like control in a window through agent-desktop, or return False."""
    clean = " ".join(str(target_name or "").lower().split())
    if not clean or RISKY_CLICKS.search(clean):
        return False
    try:
        hwnd = hwnd or user32.GetForegroundWindow()
        snap = _desktop_snapshot(hwnd)
        hits = [el for el in _controls(snap) if _role(el) in ("button", "link", "menuitem", "tab", "listitem")
                and clean_name(el.name).lower() == clean]
        if snap.cut or len(hits) != 1:
            return False
        ui_act(hits[0])
        return True
    except Exception as exc:
        print(f"  agent-desktop element click failed: {exc!r}")
        return False


def foreground():
    """(hwnd, exe, title) of the window in front, exe as a lower-case file name."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None, "", ""
    return hwnd, os.path.basename(window_exe(hwnd)).lower(), window_title(hwnd)


_EXES = {}  # (hwnd, process id): its exe, for front_glance


def front_glance():
    """(hwnd, exe, title) of the window in front, as foreground() has it, for the screen watch's look four times a
    second: which program it is (window_exe, a read of its process, about a millisecond) is asked only for a window
    or a process it hasn't seen, the title (a few microseconds) every time."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None, "", ""
    key = (hwnd, _pid(hwnd))
    exe = _EXES.get(key)
    if exe is None:
        exe = os.path.basename(window_exe(hwnd)).lower()
        if len(_EXES) > 256:
            _EXES.clear()
        if exe != "applicationframehost.exe":  # a Store app's frame, its app not in it yet: asked again next time
            _EXES[key] = exe
    return hwnd, exe, window_title(hwnd)


def site_of(url):
    """The domain of a web address, without www., or None when it is not an address."""
    m = re.match(r"(?:[a-z][\w+.-]*://)?(?:[^@/\s]*@)?([a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,})(?::\d+)?(?:[/?#]|$)",
                 str(url or "").strip(), re.I)
    return m[1].lower().removeprefix("www.") if m else None


def browser_site():
    """The site in the foreground Chrome, Edge or Brave address bar, or None."""
    hwnd, exe, _ = foreground()
    if exe not in BROWSER_EXES:
        return None
    box = find_ui(OMNIBOX, "edit", hwnd=hwnd)
    return site_of(ui_value(box)) if box is not None else None


def window_site(hwnd, exe=None):
    """The site a browser window shows, in front or behind other windows, or None."""
    if not hwnd:
        return None
    exe = exe or os.path.basename(window_exe(hwnd)).lower()
    if exe not in BROWSER_EXES:
        return None
    box = find_ui(OMNIBOX, "edit", hwnd=hwnd)
    return site_of(ui_value(box)) if box is not None else None


TAB_BROWSERS = BROWSER_EXES | {"firefox.exe"}
TITLE_PARTS = re.compile(r"\s+[-|/\u00b7\u2013\u2014]\s+")
TITLE_COUNT = re.compile(r"^\(\d[\d,]*\+?\)\s*")


def shows_site(title, names):
    """True if a browser window or tab title has one of the site's own title parts."""
    names = [names] if isinstance(names, str) else names
    parts = {" ".join(TITLE_COUNT.sub("", p).split()).lower() for p in TITLE_PARTS.split(BIDI.sub("", title or ""))}
    return any(" ".join(str(n).split()).lower() in parts for n in names if str(n).strip())


def browser_windows():
    """Browser windows on screen, minimised ones too, front-most first."""
    found = []
    cb = WNDENUMPROC(lambda h, _: found.append(h) or True)
    user32.EnumWindows(cb, 0)
    return [h for h in found if _is_app_window(h) and os.path.basename(window_exe(h)).lower() in TAB_BROWSERS]


def _tab_items(hwnd):
    """The tabs in a browser window's agent-desktop snapshot, as (element, name)."""
    snap = _desktop_snapshot(hwnd)
    return [(el, clean_name(el.name)) for el in snap.elements if el.raw_role == "tab" and _shown(el)]


def close_site_tab(names):
    """Bring forward and close the browser tab showing a site, or raise when it cannot be identified safely."""
    windows = browser_windows()
    target = next((h for h in windows if shows_site(window_title(h), names)), None)
    for hwnd in windows if target is None else ():
        try:
            tab = next((el for el, name in _tab_items(hwnd) if shows_site(name, names)), None)
        except Exception as exc:
            print(f"  agent-desktop: {exc!r}")
            continue
        if tab is None:
            continue
        bring_to_front(hwnd)
        _sleep(0.15)
        ui_act(tab)
        _sleep(0.3)
        target = hwnd
        break
    if target is None:
        raise LookupError("no tab shows it")
    bring_to_front(target)
    _sleep(0.15)
    title = window_title(target)
    if user32.GetForegroundWindow() != target or not shows_site(title, names):
        raise RuntimeError("its browser window didn't come to the front")
    press("ctrl", "w")
    return title


SNAP_LISTS = 15
SNAP_NAME = 60


def _inside(rect, box):
    return bool(rect and box and box[0] <= rect[0] and box[1] <= rect[1] and rect[2] <= box[2] and rect[3] <= box[3])


def _snapshot_items(snap, most, browser=False, lists=SNAP_LISTS):
    page = next((el.rect for el in snap.elements if el.raw_role == "document" and _shown(el)), None)
    focused_el = max((el for el in snap.elements if "focused" in el.states and _role(el)),
                     key=lambda el: el.depth, default=None)
    dialog = _scope(focused_el, include_window=False) if focused_el else None
    listed, cut, items = 0, bool(snap.cut), []
    for el in _controls(snap):
        role, name = _role(el), clean_name(el.name)[:SNAP_NAME]
        if browser and page and role == "tab" and el.rect[3] <= page[1]:
            continue
        if role == "listitem":
            listed += 1
            if listed > lists:
                cut = True
                continue
        value = None if el.password else _text(el.value) if el.value else None
        if not name and not value and role not in ("edit", "document", "combobox"):
            continue
        state = None
        if el.raw_role in ("checkbox", "switch") or "Toggle" in el.actions:
            state = "on" if "checked" in el.states else "off"
        items.append({"id": 0, "role": role, "name": name, "value": value, "state": state,
                      "password": el.password, "focus": "focused" in el.states, "aid": el.aid,
                      "rect": el.rect, "class_name": el.class_name, "kind": el.kind,
                      "item_type": el.item_type, "el": el})
    total = len(items)
    if total > most:
        def rank(item):
            if item["role"] == "edit" and item["name"] == OMNIBOX:
                return 0
            return 1 if dialog and _inside(item["rect"], dialog.rect) else 2 if _inside(item["rect"], page) else 3
        items, cut = sorted(items, key=rank)[:most], True
    for number, item in enumerate(items, 1):
        item["id"] = number
    focused = None if focused_el is None else (_role(focused_el), clean_name(focused_el.name)[:SNAP_NAME],
                                                None if focused_el.password else _text(focused_el.value))
    web = None if page is None else sum(1 for item in items if item["role"] != "document" and
                                        _inside(item["rect"], page))
    return items, web, total, focused, cut


def ui_snapshot(hwnd=None, most=60, settle=True, raw=False):
    """The foreground or named window's controls from one bounded agent-desktop snapshot. settle: a browser page
    with almost nothing on it yet is read again half a second later, for a task, as it may still be loading; the
    screen watch's look every few seconds takes it as it is, and reads it again on its next look. raw: the snapshot
    itself comes too, as "raw", for ui_at_in."""
    hwnd = hwnd or user32.GetForegroundWindow()
    if not hwnd or _clock() < _slow.get(hwnd, 0.0) or _class_name(hwnd) in UNLISTED_CLASSES:
        return None
    exe, began = os.path.basename(window_exe(hwnd)).lower(), _clock()
    browser = exe in BROWSER_EXES
    try:
        snap = _desktop_snapshot(hwnd)
        items, web, total, focused, cut = _snapshot_items(snap, most, browser)
        if settle and browser and web is not None and web < 5:
            _sleep(0.5)
            began = _clock()
            snap = _desktop_snapshot(hwnd)
            items, web, total, focused, cut = _snapshot_items(snap, most, browser)
    except Exception as exc:
        print(f"  agent-desktop snapshot: {exc!r}")
        _slow[hwnd] = _clock() + SLOW_FOR
        return None
    if _clock() - began > 2 * DESKTOP_LIMIT / 1000:
        _slow[hwnd] = _clock() + SLOW_FOR
    box = next((item for item in items if item["role"] == "edit" and item["name"] == OMNIBOX), None)
    return {"hwnd": hwnd, "title": window_title(hwnd), "exe": exe,
            "site": site_of(box["value"]) if box is not None and browser else None,
            "focus": next((item["id"] for item in items if item["focus"]), None), "total": total,
            "focused": focused, "cut": cut, "items": items, **({"raw": snap} if raw else {})}


def _same_scope(old, candidate):
    if old.aid:
        return old.aid == candidate.aid
    if clean_name(old.name):
        return clean_name(old.name) == clean_name(candidate.name)
    return old.rect == candidate.rect


def ui_fields(el=None):
    """Every readable field in the control's dialog, else in its foreground window; None on an uncertain read."""
    try:
        hwnd = _hwnd(el) if el is not None else user32.GetForegroundWindow()
        if not hwnd:
            return None
        snap = _desktop_snapshot(hwnd)
        old_dialog = _scope(el, include_window=False) if el is not None else None
        scope = snap.root
        if old_dialog is not None:
            matches = [at for at in snap.elements if _is_dialog(at) and _same_scope(old_dialog, at)]
            if len(matches) != 1:
                return None
            scope = matches[0]
        elements = [scope] + scope.descendants()
        return [(_role(item), clean_name(item.name), None if item.password else _text(item.value))
                for item in elements if _role(item) and _shown(item)]
    except Exception as exc:
        print(f"  agent-desktop: {exc!r}")
        return None


# --------------------------------------------------------------------------- Native Window Management & Shell
def maximize_foreground_window():
    """Maximize the active foreground window using Win32 ShowWindow (< 1ms)."""
    _com()
    hwnd = user32.GetForegroundWindow()
    if hwnd:
        user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE


def restore_foreground_window():
    """Restore/unmaximize the active foreground window (< 1ms)."""
    _com()
    hwnd = user32.GetForegroundWindow()
    if hwnd:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE


def minimize_foreground_window():
    """Minimize the active foreground window (< 1ms)."""
    _com()
    hwnd = user32.GetForegroundWindow()
    if hwnd:
        user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE


def show_desktop():
    """Toggle or show desktop via Windows Shell COM (< 5ms, 0 RAM)."""
    _com()
    import comtypes.client
    shell = comtypes.client.CreateObject("Shell.Application")
    shell.ToggleDesktop()


SHELL_FOLDERS = {"shell:MyComputerFolder", "shell:RecycleBinFolder", "shell:Downloads", "shell:Personal",
                 "shell:My Pictures", "shell:My Music", "shell:My Video", "shell:Desktop"}
# What they're called, for an "open" step: a model planned "open recycle bin" as an app, which no Start menu has
SHELL_NAMES = {"recycle bin": "shell:RecycleBinFolder", "this pc": "shell:MyComputerFolder",
               "my computer": "shell:MyComputerFolder", "downloads": "shell:Downloads", "documents": "shell:Personal",
               "my documents": "shell:Personal", "pictures": "shell:My Pictures"}


def open_folder(path_or_uri):
    """Open a folder in File Explorer. Only an existing folder or one of SHELL_FOLDERS: os.startfile would run a
    program or script if handed one, so files are refused."""
    target = str(path_or_uri or "").strip()
    if target in SHELL_FOLDERS:
        os.startfile(target)
        return
    full = os.path.abspath(os.path.expandvars(os.path.expanduser(target)))
    if not target or not os.path.isdir(full):
        raise RuntimeError("I can only open folders that exist")
    os.startfile(full)


def open_snipping_tool():
    """Launch Windows Snipping Tool / screenclip protocol."""
    os.startfile("ms-screenclip:")


# Windows' own tools and Settings pages, by what people call them, for an "open" step (windows_page): on 25 October
# "Open device manager" searched Google, Device Manager not being in the Start menu, and a task in Settings went to
# https://display for ms-settings:display. Only these open by name: a Settings page can't run anything, and none of
# these tools starts a program by itself (Run, Task Scheduler, the registry and command windows are left out)
WINDOWS_PAGES = {
    "windows update": "ms-settings:windowsupdate", "windows updates": "ms-settings:windowsupdate",
    "updates": "ms-settings:windowsupdate", "update settings": "ms-settings:windowsupdate",
    "check for updates": "ms-settings:windowsupdate-action",
    "display": "ms-settings:display", "display settings": "ms-settings:display", "screen settings": "ms-settings:display",
    "sound settings": "ms-settings:sound", "sound": "ms-settings:sound", "audio settings": "ms-settings:sound",
    "bluetooth": "ms-settings:bluetooth", "bluetooth settings": "ms-settings:bluetooth",
    "bluetooth and devices": "ms-settings:bluetooth", "devices": "ms-settings:bluetooth",
    "wifi": "ms-settings:network-wifi", "wi fi": "ms-settings:network-wifi", "wifi settings": "ms-settings:network-wifi",
    "network settings": "ms-settings:network", "internet settings": "ms-settings:network",
    "network and internet": "ms-settings:network", "hotspot": "ms-settings:network-mobilehotspot",
    "mobile hotspot": "ms-settings:network-mobilehotspot", "vpn": "ms-settings:network-vpn",
    "airplane mode": "ms-settings:network-airplanemode", "flight mode": "ms-settings:network-airplanemode",
    "installed apps": "ms-settings:appsfeatures", "apps and features": "ms-settings:appsfeatures",
    "apps settings": "ms-settings:appsfeatures", "default apps": "ms-settings:defaultapps",
    "startup apps": "ms-settings:startupapps", "storage": "ms-settings:storagesense",
    "storage settings": "ms-settings:storagesense", "battery settings": "ms-settings:batterysaver",
    "battery saver": "ms-settings:batterysaver", "power settings": "ms-settings:powersleep",
    "power and battery": "ms-settings:powersleep", "night light settings": "ms-settings:nightlight",
    "personalization": "ms-settings:personalization", "personalisation": "ms-settings:personalization",
    "wallpaper": "ms-settings:personalization-background", "background": "ms-settings:personalization-background",
    "themes": "ms-settings:themes", "colors": "ms-settings:colors", "colours": "ms-settings:colors",
    "lock screen settings": "ms-settings:lockscreen", "taskbar settings": "ms-settings:taskbar",
    "notification settings": "ms-settings:notifications", "notifications settings": "ms-settings:notifications",
    "focus": "ms-settings:focus", "do not disturb": "ms-settings:notifications",
    "privacy": "ms-settings:privacy", "privacy settings": "ms-settings:privacy",
    "camera settings": "ms-settings:privacy-webcam", "camera privacy": "ms-settings:privacy-webcam",
    "camera permissions": "ms-settings:privacy-webcam", "microphone settings": "ms-settings:privacy-microphone",
    "microphone privacy": "ms-settings:privacy-microphone", "mic settings": "ms-settings:privacy-microphone",
    "location settings": "ms-settings:privacy-location", "date and time": "ms-settings:dateandtime",
    "time settings": "ms-settings:dateandtime", "language settings": "ms-settings:regionlanguage",
    "keyboard settings": "ms-settings:typing", "mouse settings": "ms-settings:mousetouchpad",
    "touchpad settings": "ms-settings:devices-touchpad", "printers": "ms-settings:printers",
    "printers and scanners": "ms-settings:printers", "accounts": "ms-settings:yourinfo",
    "sign in options": "ms-settings:signinoptions", "about": "ms-settings:about", "about this pc": "ms-settings:about",
    "system settings": "ms-settings:display", "accessibility": "ms-settings:easeofaccess",
    "windows security": "windowsdefender:", "virus protection": "windowsdefender:",
    "device manager": "devmgmt.msc", "disk management": "diskmgmt.msc", "event viewer": "eventvwr.msc",
    "task manager": "taskmgr.exe", "control panel": "control.exe", "system information": "msinfo32.exe",
    "resource monitor": "resmon.exe", "character map": "charmap.exe", "network connections": "ncpa.cpl",
    "programs and features": "appwiz.cpl", "sound control panel": "mmsys.cpl", "power options": "powercfg.cpl",
    "system properties": "sysdm.cpl", "mouse properties": "main.cpl"}
SETTINGS_PAGE = re.compile(r"ms-settings:[a-z0-9-]*", re.I)  # any Settings page, as a model may name one


def windows_page(name):
    """What opens one of Windows' tools or Settings pages called name ("Device Manager", "the Windows Update page",
    "camera settings"), else None."""
    key = " ".join(re.sub(r"[^a-z0-9]+", " ", str(name or "").lower().replace("wi-fi", "wifi")).split())
    key = re.sub(r"^(?:open |the |my )+", "", key)
    for k in (key, re.sub(r" (?:page|window|app|tool|settings? page)$", "", key), re.sub(r"^windows ", "", key)):
        if k in WINDOWS_PAGES:
            return WINDOWS_PAGES[k]
    return None


def open_windows_page(target):
    """Opens one of WINDOWS_PAGES' tools or pages, or a Settings page (ms-settings:...): nothing else, as
    os.startfile would run whatever it's handed."""
    target = str(target or "").strip()
    if target not in WINDOWS_PAGES.values() and not SETTINGS_PAGE.fullmatch(target):
        raise RuntimeError("I can only open Windows' own settings and tools that way")
    os.startfile(target)

