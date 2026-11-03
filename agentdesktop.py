"""The small local client for Vercel Labs' agent-desktop command.

It keeps the command's JSON, refs and errors in one place. Nothing here sends a screen
or its controls online: agent-desktop talks to Windows' accessibility API on this PC.
"""
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path


PROTOCOL = "2"
DEFAULT_OBSERVE_MS = 1800
DEFAULT_ACTION_MS = 5000


class DesktopError(RuntimeError):
    """An agent-desktop failure, with whether another delivery would be safe."""

    def __init__(self, message, code="AGENT_DESKTOP_ERROR", error=None):
        super().__init__(str(message or "agent-desktop failed"))
        self.code = str(code or "AGENT_DESKTOP_ERROR")
        self.error = error if isinstance(error, dict) else {}
        disposition = self.error.get("disposition") or {}
        self.delivery = disposition.get("delivery")
        self.retry = disposition.get("retry")
        self.safe = self.delivery == "not_delivered" and self.retry == "safe"


class Element:
    """One element from a snapshot, addressed later by its qualified ref."""

    def __init__(self, snapshot, node, parent=None, depth=0):
        self.snapshot = snapshot
        self.node = node
        self.parent = parent
        self.depth = depth
        self.ref = str(node.get("ref_id") or "")
        self.raw_role = str(node.get("role") or "")
        self.name = str(node.get("name") or "")
        self.value = node.get("value") if isinstance(node.get("value"), str) else None
        self.description = str(node.get("description") or "")
        native = node.get("native_id") or {}
        self.aid = str(native.get("value") or "") if native.get("kind") == "automation_id" else ""
        self.native_id = str(native.get("value") or "")
        self.states = set(node.get("states") or ())
        self.actions = set(node.get("available_actions") or ())
        self.password = "secure" in self.states
        self.rect = rectangle(node.get("bounds"))
        # agent-desktop does not expose UIA ItemType or ClassName. These stay empty so callers use their existing
        # conservative path instead of treating an unknown file or terminal as safe.
        self.item_type = ""
        self.class_name = ""
        self.index = len(snapshot.elements)
        snapshot.elements.append(self)

    @property
    def children(self):
        """The direct children included in this snapshot."""
        return [el for el in self.snapshot.elements if el.parent is self]

    def descendants(self):
        """Every element below this one, in screen-reader order."""
        return [el for el in self.snapshot.elements if el is not self and el.has_ancestor(self)]

    def has_ancestor(self, ancestor):
        at = self.parent
        while at is not None:
            if at is ancestor:
                return True
            at = at.parent
        return False


class Snapshot:
    """A complete agent-desktop accessibility snapshot and its flattened elements."""

    def __init__(self, data):
        self.data = data
        window = data.get("window") or {}
        self.window_id = str(window.get("id") or "")
        self.title = str(window.get("title") or "")
        self.app = str(data.get("app") or "")
        self.complete = bool(data.get("complete"))
        self.cut = not self.complete or bool(data.get("truncated"))
        self.elements = []
        self.root = self._add(data.get("tree") or {}, None, 0)

    def _add(self, node, parent, depth):
        el = Element(self, node, parent, depth)
        for child in node.get("children") or ():
            if isinstance(child, dict):
                self._add(child, el, depth + 1)
        return el


def rectangle(bounds):
    """(left, top, right, bottom) from agent-desktop's x/y/width/height, or None."""
    if not isinstance(bounds, dict):
        return None
    try:
        x, y = float(bounds["x"]), float(bounds["y"])
        width, height = float(bounds["width"]), float(bounds["height"])
    except (KeyError, TypeError, ValueError):
        return None
    return (x, y, x + width, y + height)


def window_id(hwnd):
    """agent-desktop's Windows window id for an HWND."""
    try:
        value = int(hwnd)
    except (TypeError, ValueError):
        value = 0
    return f"w-{value}" if value else ""


def _native_name():
    machine = platform.machine().lower()
    return "agent-desktop-win32-arm64.exe" if "arm" in machine or "aarch" in machine else \
        "agent-desktop-win32-x64.exe"


def binary():
    """The native executable installed by npm, or raise with the setup command."""
    override = os.environ.get("HEYHARRY_AGENT_DESKTOP")
    if override and os.path.isfile(override):
        return override
    name = _native_name()
    candidates = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "npm" / "node_modules" / "agent-desktop" / "bin" / name)
    shim = shutil.which("agent-desktop.cmd") or shutil.which("agent-desktop")
    if shim:
        folder = Path(shim).resolve().parent
        candidates += [folder / "node_modules" / "agent-desktop" / "bin" / name,
                       folder.parent / "node_modules" / "agent-desktop" / "bin" / name]
    found = shutil.which(name)
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise DesktopError("agent-desktop isn't installed. Run: npm install -g agent-desktop", "NOT_INSTALLED")


def available():
    """True when the native command can be found, without starting it."""
    try:
        binary()
        return True
    except DesktopError:
        return False


def _execute(args, timeout):
    """Run the native command once. Tests replace this before any real desktop can be read."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return subprocess.run([binary(), *map(str, args)], stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", creationflags=flags,
                              timeout=max(0.1, float(timeout)), check=False)
    except subprocess.TimeoutExpired as exc:
        # A timed-out mutating command may already have landed. No caller retries it from this exception.
        raise DesktopError("agent-desktop took too long", "TIMEOUT") from exc
    except OSError as exc:
        raise DesktopError(f"agent-desktop couldn't start: {exc}", "START_FAILED") from exc


def call(*args, timeout=8.0):
    """Run one command and return its data object, or raise DesktopError."""
    done = _execute(args, timeout)
    text = str(getattr(done, "stdout", "") or "").strip()
    try:
        envelope = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        detail = str(getattr(done, "stderr", "") or "").strip()
        message = "agent-desktop returned no JSON" + (f": {detail[:240]}" if detail else "")
        raise DesktopError(message, "BAD_OUTPUT") from exc
    if not isinstance(envelope, dict):
        raise DesktopError("agent-desktop returned invalid JSON", "BAD_OUTPUT")
    version = str(envelope.get("version") or "")
    if version.split(".", 1)[0] != PROTOCOL:
        raise DesktopError(f"agent-desktop protocol {version or 'unknown'} isn't supported", "BAD_VERSION")
    if not envelope.get("ok"):
        error = envelope.get("error") or {}
        raise DesktopError(error.get("message") or "agent-desktop failed", error.get("code"), error)
    data = envelope.get("data")
    if not isinstance(data, (dict, list)):
        raise DesktopError("agent-desktop returned no data", "BAD_OUTPUT")
    return data


def snapshot(hwnd=None, timeout_ms=DEFAULT_OBSERVE_MS, max_depth=50):
    """A window's full local accessibility tree, including bounds and non-interactive text."""
    args = ["snapshot"]
    if hwnd:
        args += ["--window-id", window_id(hwnd)]
    args += ["--include-bounds", "--max-depth", str(max_depth), "--compact", "--timeout-ms", str(timeout_ms)]
    return Snapshot(call(*args, timeout=timeout_ms / 1000 + 3.0))


def get(element, prop):
    """A live property of an element ref."""
    if not isinstance(element, Element) or not element.ref:
        raise DesktopError("that control has no usable agent-desktop ref", "NO_REF")
    data = call("get", element.ref, "--property", prop, timeout=4.0)
    return data.get("value")


def act(element, command, value=None, headed=False, timeout_ms=DEFAULT_ACTION_MS):
    """Run one ref action. A mutating failure is never retried here."""
    if not isinstance(element, Element) or not element.ref:
        raise DesktopError("that control has no usable agent-desktop ref", "NO_REF")
    args = [command, element.ref]
    if value is not None:
        args.append(str(value))
    if headed:
        args.append("--headed")
    args += ["--timeout-ms", str(timeout_ms)]
    data = call(*args, timeout=timeout_ms / 1000 + 3.0)
    post = data.get("post_state") or {}
    if isinstance(post.get("value"), str):
        element.value = post["value"]
    if isinstance(post.get("states"), list):
        element.states = set(post["states"])
        element.password = "secure" in element.states
    return data


def mouse_click(rect, timeout_ms=DEFAULT_ACTION_MS):
    """Click the middle of rect with the real pointer; only for a foreground action."""
    if not rect or rect[2] <= rect[0] or rect[3] <= rect[1]:
        raise DesktopError("that control has no place on the screen", "NO_BOUNDS")
    x, y = round((rect[0] + rect[2]) / 2), round((rect[1] + rect[3]) / 2)
    return call("mouse-click", "--xy", f"{x},{y}", "--headed", "--timeout-ms", str(timeout_ms),
                timeout=timeout_ms / 1000 + 3.0)
