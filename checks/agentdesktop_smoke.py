"""Exercise Hey Harry's agent-desktop layer against only the throwaway fixture window."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agentdesktop
import winplatform as win

TITLE = "Hey Harry agent-desktop smoke"
QUESTION = "Hey Harry smoke question"


def window(timeout=10.0):
    """The fixture window's (id, HWND), once it appears."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for item in agentdesktop.call("list-windows", timeout=4.0):
            if item.get("title") == TITLE:
                window_id = item["id"]
                return window_id, int(window_id[2:])
        time.sleep(0.2)
    raise RuntimeError("the smoke fixture did not open")


def raw_named(hwnd, name):
    snap = win._desktop_snapshot(hwnd)
    return next((item for item in snap.elements if win.clean_name(item.name) == name), None)


def main():
    fixture = Path(__file__).with_name("agentdesktop_fixture.ps1")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-File",
                                str(fixture)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, creationflags=flags)
    began = time.perf_counter()
    try:
        window_id, hwnd = window()
        agentdesktop.call("restore", "--window-id", window_id, timeout=4.0)
        start = time.perf_counter()
        snap = win.ui_snapshot(hwnd, most=100)
        snapshot_ms = round((time.perf_counter() - start) * 1000)
        if snap is None:
            raise AssertionError("the fixture snapshot failed")

        password = next((item for item in snap["items"] if item["aid"] == "secretBox"), None)
        assert password and password["password"] and password["value"] is None, "password field was exposed"
        try:
            win.ui_act(password["el"], "new secret")
        except RuntimeError as exc:
            assert "password" in str(exc).lower()
        else:
            raise AssertionError("typing into the password field was not refused")

        check = win.find_ui("Night light", "checkbox", hwnd=hwnd)
        assert check is not None
        win.ui_act(check, state="on")
        check = win.find_ui("Night light", "checkbox", hwnd=hwnd)
        assert win.ui_toggle(check) == "on", "checkbox state did not read back"

        field = win.find_ui("Message", "edit", hwnd=hwnd)
        assert field is not None
        win.ui_act(field, "hello from the smoke check")
        field = win.find_ui("Message", "edit", hwnd=hwnd)
        assert win.ui_value(field) == "hello from the smoke check", "field value did not read back"

        # typed at the cursor: the keyboard put in the box (the window brought forward for it) and a paste, the
        # clipboard put back after
        kept = win.clipboard_text()
        assert win.ui_act(field, " again", caret=True) == "pasted"
        field = win.find_ui("Message", "edit", hwnd=hwnd)
        assert "again" in (win.ui_value(field) or ""), "pasted text did not read back"
        assert win.clipboard_text() == kept, "the clipboard was not put back"

        button = win.find_ui("Say Hello", "button", hwnd=hwnd)
        assert button is not None
        win.ui_act(button)
        time.sleep(0.2)
        assert raw_named(hwnd, "hello pressed") is not None, "button action did not land"
        assert win.find_and_click_ui_element("Delete", hwnd) is False, "risky quick click was not refused"
        assert raw_named(hwnd, "delete pressed") is None, "risky button was pressed"

        # last, as the window can't be read while its question is open: a press that opens a modal question
        # doesn't come back from Invoke, and is taken as pressed once the question turns the window off
        ask = win.find_ui("Ask First", "button", hwnd=hwnd)
        assert ask is not None
        start = time.perf_counter()
        assert win.ui_act(ask) == "invoked"
        modal_ms = round((time.perf_counter() - start) * 1000)
        assert win.user32.FindWindowW(None, QUESTION), "the modal question did not open"
        assert modal_ms < 4000, f"the press that opened a question took {modal_ms} ms"

        print(json.dumps({"ok": True, "window": window_id, "snapshot_ms": snapshot_ms, "modal_press_ms": modal_ms,
                          "total_ms": round((time.perf_counter() - began) * 1000),
                          "checked": ["snapshot", "semantic click", "toggle readback", "value readback",
                                      "focus and paste", "clipboard put back", "password refusal",
                                      "risky-click refusal", "modal press"]}))
        return 0
    finally:
        process.terminate()
        try:
            process.wait(3)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
