"""What's connected, for the island (30 October 2026, the owner's ask, after bloom's notch,
github.com/SehajveerSingh2005/bloom): the sound outputs that are on (the laptop's speakers, wired headphones, earbuds,
headphones and speakers over Bluetooth or USB), the battery Windows keeps for a Bluetooth headset, and USB drives.

Read from what Windows already keeps: Core Audio for the outputs (pycaw), the device tree (CfgMgr32) for a Bluetooth
headset's battery, and the drive letters. Windows tells Watcher when an output comes, goes or becomes the one sound
plays on, so nothing is looked at in between. Nothing changes here and nothing is sent anywhere."""
import ctypes
import re
import threading
import uuid
from ctypes import wintypes as wt

import winplatform as win

# How each output is drawn on the island (island_face.DEVICE_GLYPHS): earbuds by their names, as Windows calls most
# of them "Headphones" (on 30 October this PC had "Headphones (2- WF-C500)", Sony's earbuds)
BUDS = re.compile(r"\b(?:buds?|earbuds?|air ?pods?|pods|airdopes|wf-\w+|tws|earfun|nothing ear|jabra elite|liberty|"
                  r"soundcore|enco|redmi buds|oneplus buds|truly wireless)\b", re.I)
SPEAKER = re.compile(r"\b(?:speaker|soundbar|flip|charge|boombox|go ?\d|clip|xtreme|soundlink|wonderboom|"
                     r"gosurround|stone)\b", re.I)
HDMI = re.compile(r"\b(?:hdmi|display audio|tv|monitor|nvidia high definition|amd high definition)\b", re.I)
FORM = {1: "speaker", 3: "headphones", 5: "headphones", 9: "display"}  # PKEY_AudioEndpoint_FormFactor's values
BLUETOOTH_BUS = {"BTHENUM", "BTHHFENUM", "BTHLEDEVICE", "BTHLE"}
# a Bluetooth headset's names in the device tree, after its own: "AirPods Pro Hands-Free AG", "JBL Stereo"
PROFILE = re.compile(r"\s+(?:hands-?free(?: ag| hf)?(?: audio)?|stereo|avrcp transport|a2dp(?: sink)?|"
                     r"headset)\s*$", re.I)


def kind_of(name, form=None, bus=""):
    """What an output is, to draw: "buds", "headphones", "speaker", "jack" (wired, on the laptop's own socket),
    "display" (a TV or monitor), or "builtin" for the laptop's own speakers."""
    bus = str(bus or "").upper()
    if BUDS.search(name):
        return "buds"
    if form == 9 or HDMI.search(name):
        return "display"
    wireless = bus in BLUETOOTH_BUS or bus == "USB"
    if form in (3, 5):
        return "headphones" if wireless else "jack"
    if wireless or SPEAKER.search(name):
        return "speaker"
    return "builtin"


# --------------------------------------------------------------------------- the outputs, through Core Audio
def _key(fmtid, pid):
    from comtypes import GUID
    from pycaw.api.mmdeviceapi.depend import PROPERTYKEY
    k = PROPERTYKEY()
    k.fmtid, k.pid = GUID(fmtid), pid
    return k


def outputs():
    """The sound outputs that are on: [{"id", "name" (as she'd say it), "full" (Windows' name), "kind" (kind_of),
    "bus", "default"}], the one sound plays on marked. [] if Core Audio can't be read."""
    win._com()
    try:
        from pycaw.constants import DEVICE_STATE, EDataFlow
        from pycaw.pycaw import AudioUtilities
        enum = AudioUtilities.GetDeviceEnumerator()
        found = enum.EnumAudioEndpoints(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)
        try:
            default = enum.GetDefaultAudioEndpoint(EDataFlow.eRender.value, 1).GetId()  # eMultimedia
        except Exception:
            default = None
        name_k = _key("{a45c254e-df1c-4efd-8020-67d146a850e0}", 14)
        form_k = _key("{1da5d803-d492-4edd-8c23-e0c0ffee7f0e}", 0)
        bus_k = _key("{a45c254e-df1c-4efd-8020-67d146a850e0}", 24)
        out = []
        for i in range(found.GetCount()):
            dev = found.Item(i)
            store = dev.OpenPropertyStore(0)  # STGM_READ
            values = []
            for k in (name_k, form_k, bus_k):
                try:
                    values.append(store.GetValue(ctypes.byref(k)).GetValue())
                except Exception:
                    values.append(None)
            full, form, bus = str(values[0] or ""), values[1], str(values[2] or "")
            if not full:
                continue
            dev_id = dev.GetId()
            out.append({"id": dev_id, "name": win.output_name(full), "full": full,
                        "kind": kind_of(full, form if isinstance(form, int) else None, bus), "bus": bus.upper(),
                        "default": dev_id == default})
        return out
    except Exception as exc:
        print(f"  devices: no outputs ({exc!r})")
        return []


# --------------------------------------------------------------------------- a Bluetooth headset's battery
_cfg = None


class DEVPROPKEY(ctypes.Structure):
    _fields_ = [("fmtid", ctypes.c_ubyte * 16), ("pid", ctypes.c_ulong)]


def _devkey(guid, pid):
    k = DEVPROPKEY()
    ctypes.memmove(k.fmtid, uuid.UUID(guid).bytes_le, 16)
    k.pid = pid
    return k


BATTERY = _devkey("104EA319-6EE2-4701-BD47-8DDBF425BBE5", 2)  # DEVPKEY_Bluetooth_Battery, a byte 0 to 100
FRIENDLY = _devkey("a45c254e-df1c-4efd-8020-67d146a850e0", 14)  # DEVPKEY_Device_FriendlyName


def _devtree():
    global _cfg
    if _cfg is None:
        _cfg = ctypes.WinDLL("CfgMgr32")
        _cfg.CM_Get_Device_ID_List_SizeW.argtypes = [ctypes.POINTER(wt.ULONG), wt.LPCWSTR, wt.ULONG]
        _cfg.CM_Get_Device_ID_ListW.argtypes = [wt.LPCWSTR, wt.LPWSTR, wt.ULONG, wt.ULONG]
        _cfg.CM_Locate_DevNodeW.argtypes = [ctypes.POINTER(wt.DWORD), wt.LPCWSTR, wt.ULONG]
        _cfg.CM_Get_DevNode_PropertyW.argtypes = [wt.DWORD, ctypes.POINTER(DEVPROPKEY), ctypes.POINTER(wt.ULONG),
                                                  ctypes.c_void_p, ctypes.POINTER(wt.ULONG), wt.ULONG]
    return _cfg


def _prop(node, key):
    """A device's property as bytes, or None."""
    cfg = _devtree()
    kind, size = wt.ULONG(), wt.ULONG(0)
    cfg.CM_Get_DevNode_PropertyW(node, ctypes.byref(key), ctypes.byref(kind), None, ctypes.byref(size), 0)
    if not size.value or size.value > 4096:
        return None
    buf = (ctypes.c_ubyte * size.value)()
    if cfg.CM_Get_DevNode_PropertyW(node, ctypes.byref(key), ctypes.byref(kind), buf, ctypes.byref(size), 0) != 0:
        return None
    return bytes(buf)


def batteries():
    """{a Bluetooth device's name: its battery, 0 to 100} for each Windows keeps one for (a headset that's said how
    full it is, over Hands-Free). It's the last one heard, kept after it's gone: only an output that's on is matched
    to it (battery_for). About 5 ms for a hundred devices (measured 30 October 2026)."""
    out = {}
    try:
        cfg = _devtree()
        size = wt.ULONG()
        if cfg.CM_Get_Device_ID_List_SizeW(ctypes.byref(size), "BTHENUM", 1) != 0 or not size.value:
            return out  # CM_GETIDLIST_FILTER_ENUMERATOR
        buf = ctypes.create_unicode_buffer(size.value)
        if cfg.CM_Get_Device_ID_ListW("BTHENUM", buf, size.value, 1) != 0:
            return out
        for inst in ctypes.wstring_at(ctypes.addressof(buf), size.value).split("\0"):
            if not inst:
                continue
            node = wt.DWORD()
            if cfg.CM_Locate_DevNodeW(ctypes.byref(node), inst, 0) != 0:
                continue
            level = _prop(node.value, BATTERY)
            if not level:
                continue
            raw = _prop(node.value, FRIENDLY)
            name = raw.decode("utf-16-le", "ignore").split("\0")[0] if raw else ""
            name = PROFILE.sub("", name).strip()
            if name and 0 <= level[0] <= 100:
                out[name] = level[0]
    except Exception as exc:
        print(f"  devices: no batteries ({exc!r})")
    return out


def battery_for(output, levels):
    """The battery of a Bluetooth output (outputs()), from batteries(): its own name's, or None."""
    if output.get("bus") not in BLUETOOTH_BUS:
        return None
    name = output.get("name", "").lower()
    for known, level in levels.items():
        k = known.lower()
        if k == name or (len(k) > 3 and (k in name or name in k)):
            return level
    return None


# --------------------------------------------------------------------------- USB drives
DRIVE_REMOVABLE = 2


def drives():
    """The USB drives in, with a disk in them: [{"letter", "label", "free", "total"}], free and total in bytes."""
    k32 = ctypes.windll.kernel32
    out = []
    try:
        mask = k32.GetLogicalDrives()
    except Exception:
        return out
    old = k32.SetErrorMode(1)  # SEM_FAILCRITICALERRORS: a card reader with no card gives no "insert a disk" box
    try:
        for i in range(26):
            if not mask & (1 << i):
                continue
            root = f"{chr(65 + i)}:\\"
            if k32.GetDriveTypeW(root) != DRIVE_REMOVABLE:
                continue
            free, total = ctypes.c_ulonglong(), ctypes.c_ulonglong()
            if not k32.GetDiskFreeSpaceExW(root, ctypes.byref(free), ctypes.byref(total), None):
                continue  # nothing in it
            label = ctypes.create_unicode_buffer(64)
            k32.GetVolumeInformationW(root, label, 64, None, None, None, None, 0)
            out.append({"letter": chr(65 + i), "label": label.value or "USB drive", "free": free.value,
                        "total": total.value})
    finally:
        k32.SetErrorMode(old)
    return out


# --------------------------------------------------------------------------- what Wi-Fi and Bluetooth are connected to
# (30 October 2026, the owner's ask: Controls says which network and which device, as a phone's does)
class _WlanGUID(ctypes.Structure):
    _fields_ = [("d1", wt.DWORD), ("d2", wt.WORD), ("d3", wt.WORD), ("d4", ctypes.c_ubyte * 8)]


class _WlanInterface(ctypes.Structure):
    _fields_ = [("guid", _WlanGUID), ("desc", wt.WCHAR * 256), ("state", wt.DWORD)]


class _WlanList(ctypes.Structure):
    _fields_ = [("n", wt.DWORD), ("index", wt.DWORD), ("items", _WlanInterface * 1)]


class _Ssid(ctypes.Structure):
    _fields_ = [("len", wt.ULONG), ("ssid", ctypes.c_ubyte * 32)]


class _WlanAssociation(ctypes.Structure):
    _fields_ = [("ssid", _Ssid), ("bss_type", wt.DWORD), ("bssid", ctypes.c_ubyte * 6), ("phy", wt.DWORD),
                ("phy_index", wt.ULONG), ("signal", wt.ULONG), ("rx", wt.ULONG), ("tx", wt.ULONG)]


class _WlanConnection(ctypes.Structure):
    _fields_ = [("state", wt.DWORD), ("mode", wt.DWORD), ("profile", wt.WCHAR * 256), ("assoc", _WlanAssociation)]


def ssid_of(raw, length, profile=""):
    """A network's name from its SSID's bytes: UTF-8 as most are, else as Windows keeps its profile."""
    data = bytes(raw[:max(0, min(32, int(length)))])
    try:
        name = data.decode("utf-8")
    except UnicodeDecodeError:
        name = data.decode("latin-1")
    name = "".join(c for c in name if c.isprintable()).strip()
    return name or str(profile or "").strip() or None


def wifi_name():
    """The name of the Wi-Fi network this PC is on, or None while it's on none (or Windows won't say: since Windows
    11 24H2 an app needs location to be let read it). About 2 ms once wlanapi's loaded, 300 ms the first time
    (measured 30 October 2026), so it's read off Tk's thread."""
    try:
        wlan = ctypes.WinDLL("wlanapi")
    except OSError:
        return None
    handle, ver = wt.HANDLE(), wt.DWORD()
    if wlan.WlanOpenHandle(2, None, ctypes.byref(ver), ctypes.byref(handle)) != 0:
        return None
    found = None
    try:
        lst = ctypes.POINTER(_WlanList)()
        if wlan.WlanEnumInterfaces(handle, None, ctypes.byref(lst)) != 0:
            return None
        try:
            items = ctypes.cast(ctypes.byref(lst.contents.items), ctypes.POINTER(_WlanInterface))
            for i in range(lst.contents.n):
                if items[i].state != 1:  # wlan_interface_state_connected
                    continue
                size, data, opcode = wt.DWORD(), ctypes.c_void_p(), wt.DWORD()
                if wlan.WlanQueryInterface(handle, ctypes.byref(items[i].guid), 7, None, ctypes.byref(size),
                                           ctypes.byref(data), ctypes.byref(opcode)) != 0 or not data.value:
                    continue  # wlan_intf_opcode_current_connection
                try:
                    att = ctypes.cast(data, ctypes.POINTER(_WlanConnection)).contents
                    found = ssid_of(att.assoc.ssid.ssid, att.assoc.ssid.len, att.profile)
                finally:
                    wlan.WlanFreeMemory(data)
                if found:
                    break
        finally:
            wlan.WlanFreeMemory(lst)
    finally:
        wlan.WlanCloseHandle(handle, None)
    return found


class _SystemTime(ctypes.Structure):
    _fields_ = [(f, wt.WORD) for f in ("y", "mo", "dow", "d", "h", "mi", "s", "ms")]


class _BtInfo(ctypes.Structure):
    _fields_ = [("size", wt.DWORD), ("address", ctypes.c_ulonglong), ("cod", wt.ULONG), ("connected", wt.BOOL),
                ("remembered", wt.BOOL), ("authenticated", wt.BOOL), ("seen", _SystemTime), ("used", _SystemTime),
                ("name", wt.WCHAR * 248)]


class _BtSearch(ctypes.Structure):
    _fields_ = [("size", wt.DWORD), ("auth", wt.BOOL), ("remembered", wt.BOOL), ("unknown", wt.BOOL),
                ("connected", wt.BOOL), ("inquiry", wt.BOOL), ("timeout", ctypes.c_ubyte), ("radio", wt.HANDLE)]


def bluetooth_connected():
    """The names of the Bluetooth devices connected now, from the ones Windows remembers: no search of the air, so
    about 30 ms (measured 30 October 2026). Classic Bluetooth only: a low-energy mouse isn't in it."""
    out = []
    try:
        bt = ctypes.WinDLL("bthprops.cpl")
        bt.BluetoothFindFirstDevice.restype = wt.HANDLE
        bt.BluetoothFindNextDevice.argtypes = [wt.HANDLE, ctypes.POINTER(_BtInfo)]
        bt.BluetoothFindDeviceClose.argtypes = [wt.HANDLE]
    except (OSError, AttributeError):
        return out
    params = _BtSearch(ctypes.sizeof(_BtSearch), True, True, False, True, False, 0, None)
    info = _BtInfo()
    info.size = ctypes.sizeof(info)
    h = bt.BluetoothFindFirstDevice(ctypes.byref(params), ctypes.byref(info))
    if not h:
        return out
    try:
        while True:
            name = " ".join(info.name.split())
            if info.connected and name and name not in out:
                out.append(name)
            info = _BtInfo()
            info.size = ctypes.sizeof(info)
            if not bt.BluetoothFindNextDevice(h, ctypes.byref(info)):
                break
    finally:
        bt.BluetoothFindDeviceClose(h)
    return out


def bluetooth_name(connected, outs=()):
    """What Controls says Bluetooth is on: the output sound plays on if it's a Bluetooth one (it's the one you'd ask
    about), else the first device connected, with "+ n" for more; None for none."""
    for o in outs or ():
        if o.get("default") and o.get("bus") in BLUETOOTH_BUS and o.get("name"):
            rest = [n for n in connected if n.lower() not in o["name"].lower() and o["name"].lower() not in n.lower()]
            return o["name"] + (f" + {len(rest)}" if rest else "")
    if not connected:
        return None
    return connected[0] + (f" + {len(connected) - 1}" if len(connected) > 1 else "")


# --------------------------------------------------------------------------- told when they change
class Watcher:
    """Windows' word that an output came, went, or became the one sound plays on (IMMNotificationClient), as a flag:
    changed is set, and the reader looks again. start() on a thread with COM in its multithreaded apartment, as the
    island's plugins have; stop() to let it go."""

    def __init__(self):
        self.changed = threading.Event()
        self.changed.set()  # look the first time
        self.client = self.enum = None

    def start(self):
        try:
            win._com()
            from pycaw.callbacks import MMNotificationClient
            from pycaw.pycaw import AudioUtilities
            flag = self.changed

            class Told(MMNotificationClient):
                def on_default_device_changed(self, flow, flow_id, role, role_id, default_device_id):
                    flag.set()

                def on_device_added(self, added_device_id):
                    flag.set()

                def on_device_removed(self, removed_device_id):
                    flag.set()

                def on_device_state_changed(self, device_id, new_state, new_state_id):
                    flag.set()
            self.enum = AudioUtilities.GetDeviceEnumerator()
            self.client = Told()
            self.enum.RegisterEndpointNotificationCallback(self.client)
            return True
        except Exception as exc:
            print(f"  devices: not told of changes, looking every so often ({exc!r})")
            self.client = None
            return False

    def stop(self):
        if self.client is not None and self.enum is not None:
            try:
                self.enum.UnregisterEndpointNotificationCallback(self.client)
            except Exception:
                pass
        self.client = self.enum = None
