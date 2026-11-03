"""The agent-desktop client: JSON, errors, refs and secure fields, with no real desktop command run."""
import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.support import DESKTOP_ORIGINAL, TRIPPED  # noqa: F401, installs the real-command tripwire first
import agentdesktop as desktop


def result(body, code=0, stderr=""):
    return SimpleNamespace(stdout=json.dumps(body), stderr=stderr, returncode=code)


def envelope(data):
    return {"version": "2.6", "ok": True, "command": "test", "data": data}


class Client(unittest.TestCase):
    def test_success_and_protocol_are_checked(self):
        with mock.patch.object(desktop, "_execute", return_value=result(envelope({"answer": 42}))):
            self.assertEqual(desktop.call("version"), {"answer": 42})
        with mock.patch.object(desktop, "_execute", return_value=result(
                {"version": "3.0", "ok": True, "data": {}})):
            with self.assertRaisesRegex(desktop.DesktopError, "protocol 3.0"):
                desktop.call("version")

    def test_error_keeps_delivery_and_retry_disposition(self):
        body = {"version": "2.6", "ok": False, "command": "click", "error": {
            "code": "STALE_REF", "message": "It changed", "disposition": {
                "delivery": "not_delivered", "retry": "safe"}}}
        with mock.patch.object(desktop, "_execute", return_value=result(body, 1)):
            with self.assertRaises(desktop.DesktopError) as got:
                desktop.call("click", "@s:e1")
        self.assertEqual((got.exception.code, got.exception.delivery, got.exception.retry, got.exception.safe),
                         ("STALE_REF", "not_delivered", "safe", True))

    def test_bad_output_and_a_local_timeout_fail_closed(self):
        with mock.patch.object(desktop, "_execute", return_value=SimpleNamespace(
                stdout="not json", stderr="broken", returncode=1)):
            with self.assertRaisesRegex(desktop.DesktopError, "no JSON"):
                desktop.call("snapshot")
        with mock.patch.object(desktop, "binary", return_value="agent-desktop.exe"), \
                mock.patch.object(desktop.subprocess, "run", side_effect=subprocess.TimeoutExpired("x", 1)):
            with self.assertRaises(desktop.DesktopError) as got:
                DESKTOP_ORIGINAL(("click", "@s:e1"), 1)
        self.assertEqual((got.exception.code, got.exception.safe), ("TIMEOUT", False))

    def test_snapshot_flattens_bounds_parents_actions_and_secure_state(self):
        tree = {"role": "window", "name": "Test", "bounds": {"x": 10, "y": 20, "width": 200, "height": 100},
                "children": [{"role": "dialog", "name": "Sign in", "children": [
                    {"role": "textfield", "states": ["secure", "focused"],
                     "available_actions": ["SetValue"], "native_id": {"kind": "automation_id", "value": "pw"},
                     "bounds": {"x": 20, "y": 40, "width": 100, "height": 20}, "ref_id": "@snap:e1"}]}]}
        data = {"app": "test.exe", "complete": True, "snapshot_id": "snap", "tree": tree,
                "window": {"id": "w-99", "title": "Test"}}
        with mock.patch.object(desktop, "call", return_value=data) as called:
            snap = desktop.snapshot(99)
        field = snap.elements[-1]
        self.assertEqual((snap.window_id, snap.title, desktop.window_id(99)), ("w-99", "Test", "w-99"))
        self.assertEqual((field.rect, field.aid, field.password), ((20.0, 40.0, 120.0, 60.0), "pw", True))
        self.assertEqual(field.parent.name, "Sign in")
        self.assertIn("SetValue", field.actions)
        self.assertIn("--window-id", called.call_args.args)

    def test_get_and_action_use_the_qualified_ref_and_update_post_state(self):
        data = {"app": "x.exe", "complete": True, "tree": {"role": "window", "children": [
            {"role": "checkbox", "name": "Night light", "ref_id": "@snap:e1",
             "available_actions": ["Toggle"], "states": []}]}, "window": {"id": "w-1", "title": "x"}}
        el = desktop.Snapshot(data).elements[1]
        replies = [{"value": ["checked"]}, {"post_state": {"states": ["checked"], "value": "yes"}}]
        with mock.patch.object(desktop, "call", side_effect=replies) as called:
            self.assertEqual(desktop.get(el, "states"), ["checked"])
            desktop.act(el, "check")
        self.assertEqual((el.states, el.value), ({"checked"}, "yes"))
        self.assertEqual(called.call_args_list[0].args[:3], ("get", "@snap:e1", "--property"))
        self.assertEqual(called.call_args_list[1].args[:2], ("check", "@snap:e1"))

    def test_an_element_without_a_ref_is_never_acted_on(self):
        el = desktop.Snapshot({"complete": True, "tree": {"role": "statictext", "name": "hello"}}).root
        with self.assertRaisesRegex(desktop.DesktopError, "no usable"):
            desktop.act(el, "click")


if __name__ == "__main__":
    unittest.main()
