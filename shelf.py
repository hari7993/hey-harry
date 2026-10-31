"""The island's shelf (30 October 2026, the owner's ask, after bloom's notch, github.com/SehajveerSingh2005/bloom):
files dropped on her eyes are kept there for later, ten at most, the newest first, and dragged out again to wherever
they're going, or copied, opened or shown in their folder. Only where they are is kept, never the files themselves,
and only while she runs, unless Settings keeps them (island_shelf_keep).

Windows' own ways, through ctypes: the island's window takes dropped files as File Explorer gives them to a window
that asks for them (DragAcceptFiles, WM_DROPFILES), and a file dragged out is the shell's own (SHCreateDataObject,
SHDoDragDrop), so it goes anywhere File Explorer's would. And so she can open for them before they're dropped, as
Glance's notch does, she's told as files come over her, move and go (Target: RegisterDragDrop, an IDropTarget of our
own), with File Explorer's picture of them still under the pointer (IDropTargetHelper)."""
import ctypes
import os
from ctypes import wintypes as wt

import settings

MOST = 10
WM_DROPFILES = 0x0233
GWLP_WNDPROC = -4
DROPEFFECT_NONE, DROPEFFECT_COPY, DROPEFFECT_MOVE, DROPEFFECT_LINK = 0, 1, 2, 4
CF_HDROP, TYMED_HGLOBAL, DVASPECT_CONTENT, CLSCTX_INPROC_SERVER = 15, 1, 1, 1
E_NOINTERFACE = -2147467262  # 0x80004002, as a signed HRESULT
IID_IDATAOBJECT = (ctypes.c_byte * 16).from_buffer_copy(
    __import__("uuid").UUID("0000010e-0000-0000-c000-000000000046").bytes_le)

_shell32 = ctypes.WinDLL("shell32")
_user32 = ctypes.WinDLL("user32")
_ole32 = ctypes.WinDLL("ole32")
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
_shell32.DragAcceptFiles.argtypes = [wt.HWND, wt.BOOL]
_shell32.DragQueryFileW.argtypes = [wt.HANDLE, wt.UINT, wt.LPWSTR, wt.UINT]
_shell32.DragQueryFileW.restype = wt.UINT
_shell32.DragFinish.argtypes = [wt.HANDLE]
_shell32.SHParseDisplayName.argtypes = [wt.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), wt.ULONG,
                                        ctypes.POINTER(wt.ULONG)]
_shell32.ILClone.argtypes = [ctypes.c_void_p]
_shell32.ILClone.restype = ctypes.c_void_p
_shell32.ILRemoveLastID.argtypes = [ctypes.c_void_p]
_shell32.ILFindLastID.argtypes = [ctypes.c_void_p]
_shell32.ILFindLastID.restype = ctypes.c_void_p
_shell32.ILFree.argtypes = [ctypes.c_void_p]
_shell32.SHCreateDataObject.argtypes = [ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
                                        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
_shell32.SHDoDragDrop.argtypes = [wt.HWND, ctypes.c_void_p, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
_set_proc = getattr(_user32, "SetWindowLongPtrW", None) or _user32.SetWindowLongW
_set_proc.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_void_p]
_set_proc.restype = ctypes.c_void_p
_user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_user32.CallWindowProcW.restype = ctypes.c_ssize_t
_ole32.RegisterDragDrop.argtypes = [wt.HWND, ctypes.c_void_p]
_ole32.RevokeDragDrop.argtypes = [wt.HWND]
_ole32.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p,
                                    ctypes.POINTER(ctypes.c_void_p)]
_ole32.ReleaseStgMedium.argtypes = [ctypes.c_void_p]
_ole32.ReleaseStgMedium.restype = None


def _iid(text):
    return (ctypes.c_byte * 16).from_buffer_copy(__import__("uuid").UUID(text).bytes_le)


IID_IUNKNOWN = _iid("00000000-0000-0000-c000-000000000046")
IID_IDROPTARGET = _iid("00000122-0000-0000-c000-000000000046")
CLSID_DRAGDROPHELPER = _iid("4657278a-411b-11d2-839a-00c04fd918d0")
IID_IDROPTARGETHELPER = _iid("4657278b-411b-11d2-839a-00c04fd918d0")
HRESULT = ctypes.c_long
# an IDropTarget's own calls; its POINTL comes by value, which on Windows is an 8-byte integer, x the low half
_QI = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
_REF = ctypes.WINFUNCTYPE(wt.ULONG, ctypes.c_void_p)
_ENTER = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p, wt.DWORD, ctypes.c_int64,
                            ctypes.POINTER(wt.DWORD))
_OVER = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wt.DWORD, ctypes.c_int64, ctypes.POINTER(wt.DWORD))
_LEAVE = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p)


class _Vtbl(ctypes.Structure):
    _fields_ = [("QueryInterface", _QI), ("AddRef", _REF), ("Release", _REF), ("DragEnter", _ENTER),
                ("DragOver", _OVER), ("DragLeave", _LEAVE), ("Drop", _ENTER)]


class _Com(ctypes.Structure):
    _fields_ = [("vtbl", ctypes.POINTER(_Vtbl))]


class _FormatEtc(ctypes.Structure):
    _fields_ = [("cfFormat", wt.WORD), ("ptd", ctypes.c_void_p), ("dwAspect", wt.DWORD), ("lindex", wt.LONG),
                ("tymed", wt.DWORD)]


class _StgMedium(ctypes.Structure):
    _fields_ = [("tymed", wt.DWORD), ("handle", ctypes.c_void_p), ("pUnkForRelease", ctypes.c_void_p)]


def _call(ptr, index, restype, argtypes, *args):
    """Method index of the COM object at ptr, called with args."""
    vtbl = ctypes.cast(ctypes.c_void_p.from_address(ptr).value, ctypes.POINTER(ctypes.c_void_p))
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl[index])(ptr, *args)


def _point(packed):
    """A POINTL that came as an integer: (x, y) on the screen."""
    return ctypes.c_int32(packed & 0xFFFFFFFF).value, ctypes.c_int32((packed >> 32) & 0xFFFFFFFF).value


def load():
    """The shelf as it was kept, when Settings keeps it: [] else, or for files no longer there."""
    if not settings.get("island_shelf_keep"):
        return []
    return [p for p in (settings.get("island_shelf") or []) if isinstance(p, str) and os.path.exists(p)][:MOST]


def save(items):
    """Kept for next time when Settings says so; forgotten otherwise."""
    try:
        settings.put("island_shelf", list(items)[:MOST] if settings.get("island_shelf_keep") else [])
    except OSError as exc:
        print(f"  shelf: not kept ({exc!r})")


def added(items, paths):
    """items with paths put on it, newest first, each once, MOST at most, and only what's there."""
    new = [os.path.normpath(p) for p in paths if p and os.path.exists(p)]
    out = list(dict.fromkeys(new[::-1] + [p for p in items if p not in new]))
    return out[:MOST]


def _query(drop):
    """The paths in a drop (an HDROP), MOST at most."""
    paths = []
    n = _shell32.DragQueryFileW(drop, 0xFFFFFFFF, None, 0)
    for i in range(min(n, MOST)):
        size = _shell32.DragQueryFileW(drop, i, None, 0) + 1
        buf = ctypes.create_unicode_buffer(size)
        _shell32.DragQueryFileW(drop, i, buf, size)
        paths.append(buf.value)
    return paths


def dragged(data):
    """The files in a drag (the IDataObject at data), as File Explorer gives them: [] for none, or for what isn't
    files."""
    if not data:
        return []
    fmt = _FormatEtc(CF_HDROP, None, DVASPECT_CONTENT, -1, TYMED_HGLOBAL)
    med = _StgMedium()
    if _call(data, 3, HRESULT, (ctypes.POINTER(_FormatEtc), ctypes.POINTER(_StgMedium)), ctypes.byref(fmt),
             ctypes.byref(med)) != 0:
        return []
    try:
        return _query(med.handle) if med.handle else []
    finally:
        _ole32.ReleaseStgMedium(ctypes.byref(med))


class Drops:
    """Files dropped on hwnd, handed to on_files([paths]), till close(). on_files runs inside Windows' own call to
    the window, in the middle of Tk handling a message, so it must only hand them on (a queue), never touch Tk: on 30
    October 2026 the island opened its shelf from here, which called Tk back while Tk was still in that call, and she
    crashed (an access violation in python314.dll) as soon as a file was dropped on her."""

    def __init__(self, hwnd, on_files):
        self.hwnd, self.on_files = hwnd, on_files
        self.old = None
        self.proc = WNDPROC(self._proc)  # kept, or Windows would call into freed memory
        _shell32.DragAcceptFiles(hwnd, True)
        self.old = _set_proc(hwnd, GWLP_WNDPROC, ctypes.cast(self.proc, ctypes.c_void_p))

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_DROPFILES:
            paths = []
            try:
                drop = wt.HANDLE(wparam)
                paths = _query(drop)
                _shell32.DragFinish(drop)
            except Exception as exc:
                print(f"  shelf: a drop went wrong ({exc!r})")
            try:
                self.on_files(paths)
            except Exception as exc:
                print(f"  shelf: {exc!r}")
            return 0
        return _user32.CallWindowProcW(self.old, hwnd, msg, wparam, lparam)

    def close(self):
        if self.old:
            _shell32.DragAcceptFiles(self.hwnd, False)
            _set_proc(self.hwnd, GWLP_WNDPROC, self.old)
            self.old = None


class Target:
    """Files dragged over hwnd, told to on_drag(what, x, y, paths) as they come ("enter"), move ("over"), go off it
    ("leave") and land ("drop"), x and y on the screen, so the island can open for them as Glance's notch does, before
    they're dropped (30 October 2026, the owner's ask). Windows' own way for a window that takes drops
    (RegisterDragDrop, with an IDropTarget made here), so a drop comes here and not to Drops, which stays for what
    isn't dragged that way. Its calls come inside Windows' call to the window, in the middle of Tk handling a message,
    as Drops' do, so on_drag must only note them, never touch Tk. Only files: nothing else dragged over her is taken.
    Needs OLE on this thread (ole); OSError if Windows won't have it."""

    def __init__(self, hwnd, on_drag):
        self.hwnd, self.on_drag = hwnd, on_drag
        self.paths, self.helper, self.on = [], None, False
        # kept, or Windows would call into freed memory; one object, kept as long as this is, so it isn't counted
        self.fns = _Vtbl(_QI(self._qi), _REF(lambda this: 1), _REF(lambda this: 1), _ENTER(self._enter),
                         _OVER(self._over), _LEAVE(self._leave), _ENTER(self._drop))
        self.obj = _Com(ctypes.pointer(self.fns))
        self.ptr = ctypes.addressof(self.obj)
        helper = ctypes.c_void_p()
        if _ole32.CoCreateInstance(ctypes.byref(CLSID_DRAGDROPHELPER), None, CLSCTX_INPROC_SERVER,
                                   ctypes.byref(IID_IDROPTARGETHELPER), ctypes.byref(helper)) == 0:
            self.helper = helper.value  # File Explorer's picture of what's dragged, drawn over her too
        hr = _ole32.RegisterDragDrop(hwnd, self.ptr)
        if hr != 0:
            self._free()
            raise OSError(f"RegisterDragDrop said {hr & 0xFFFFFFFF:#x}")
        self.on = True

    def _qi(self, this, riid, ppv):
        if ctypes.string_at(riid, 16) in (bytes(IID_IUNKNOWN), bytes(IID_IDROPTARGET)):
            ppv[0] = self.ptr
            return 0
        ppv[0] = None
        return E_NOINTERFACE

    @staticmethod
    def _effect(allowed):
        """What a drop here does, of what the drag allows: a copy, as nothing's taken from where it is (a move would
        have File Explorer delete it); a link if that's all it allows."""
        return DROPEFFECT_COPY if allowed & DROPEFFECT_COPY else DROPEFFECT_LINK if allowed & DROPEFFECT_LINK else \
            DROPEFFECT_NONE

    def _helper(self, index, argtypes, *args):
        if self.helper:
            try:
                _call(self.helper, index, HRESULT, argtypes, *args)
            except Exception as exc:
                print(f"  shelf: no drag picture ({exc!r})")

    def _enter(self, this, data, keys, packed, effect):
        try:
            self.paths = dragged(data)
            x, y = _point(packed)
            effect[0] = self._effect(effect[0]) if self.paths else DROPEFFECT_NONE
            p = wt.POINT(x, y)
            self._helper(3, (wt.HWND, ctypes.c_void_p, ctypes.POINTER(wt.POINT), wt.DWORD), self.hwnd, data,
                         ctypes.byref(p), effect[0])
            if self.paths:
                self.on_drag("enter", x, y, list(self.paths))
        except Exception as exc:
            print(f"  shelf: {exc!r}")
        return 0

    def _over(self, this, keys, packed, effect):
        try:
            x, y = _point(packed)
            effect[0] = self._effect(effect[0]) if self.paths else DROPEFFECT_NONE
            p = wt.POINT(x, y)
            self._helper(5, (ctypes.POINTER(wt.POINT), wt.DWORD), ctypes.byref(p), effect[0])
            if self.paths:
                self.on_drag("over", x, y, self.paths)
        except Exception as exc:
            print(f"  shelf: {exc!r}")
        return 0

    def _leave(self, this):
        try:
            self._helper(4, ())
            if self.paths:
                self.on_drag("leave", 0, 0, [])
        except Exception as exc:
            print(f"  shelf: {exc!r}")
        self.paths = []
        return 0

    def _drop(self, this, data, keys, packed, effect):
        try:
            paths = dragged(data) or self.paths
            x, y = _point(packed)
            effect[0] = self._effect(effect[0]) if paths else DROPEFFECT_NONE
            p = wt.POINT(x, y)
            self._helper(6, (ctypes.c_void_p, ctypes.POINTER(wt.POINT), wt.DWORD), data, ctypes.byref(p), effect[0])
            self.on_drag("drop", x, y, list(paths))
        except Exception as exc:
            print(f"  shelf: a drop went wrong ({exc!r})")
        self.paths = []
        return 0

    def _free(self):
        if self.helper:
            _call(self.helper, 2, wt.ULONG, ())
            self.helper = None

    def close(self):
        if self.on:
            _ole32.RevokeDragDrop(self.hwnd)
            self.on = False
        self._free()


def drag_out(hwnd, paths):
    """paths dragged from hwnd, as File Explorer drags files, till they're dropped: True if they were. Runs Windows'
    own drag loop on this thread (it must have OLE, island._build sees to it), so it returns once they land."""
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        return False
    pidls = []
    parent = data = None
    try:
        for p in paths:
            pidl = ctypes.c_void_p()
            if _shell32.SHParseDisplayName(p, None, ctypes.byref(pidl), 0, None) == 0 and pidl.value:
                pidls.append(pidl.value)
        if not pidls:
            return False
        parent = _shell32.ILClone(pidls[0])
        _shell32.ILRemoveLastID(parent)
        # only those in the first one's folder go together: a data object is one folder's files
        first = os.path.dirname(os.path.normpath(paths[0])).lower()
        kids = [_shell32.ILFindLastID(pidl) for pidl, p in zip(pidls, paths)
                if os.path.dirname(os.path.normpath(p)).lower() == first]
        arr = (ctypes.c_void_p * len(kids))(*kids)
        data = ctypes.c_void_p()
        if _shell32.SHCreateDataObject(parent, len(kids), arr, None, ctypes.byref(IID_IDATAOBJECT),
                                       ctypes.byref(data)) != 0 or not data.value:
            return False
        effect = wt.DWORD()
        hr = _shell32.SHDoDragDrop(hwnd, data, None, DROPEFFECT_COPY | DROPEFFECT_MOVE | DROPEFFECT_LINK,
                                   ctypes.byref(effect))
        return hr == 0x00040100  # DRAGDROP_S_DROP
    except Exception as exc:
        print(f"  shelf: couldn't drag it out ({exc!r})")
        return False
    finally:
        if data is not None and data.value:
            vtbl = ctypes.cast(ctypes.c_void_p.from_address(data.value).value, ctypes.POINTER(ctypes.c_void_p))
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])(data.value)
        if parent:
            _shell32.ILFree(parent)
        for pidl in pidls:
            _shell32.ILFree(pidl)


def ole():
    """OLE on this thread, for drag_out: True if it's there (or was already)."""
    return _ole32.OleInitialize(None) in (0, 1)  # S_OK, S_FALSE


def show_in_folder(path):
    """File Explorer opened on path's folder, with path selected."""
    import subprocess
    import winplatform as win
    subprocess.Popen(["explorer.exe", "/select,", os.path.normpath(path)], creationflags=win.CREATE_NO_WINDOW)
