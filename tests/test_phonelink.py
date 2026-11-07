"""Your phone on the same Wi-Fi (phonelink.py): the shelf's files for it with the key only, PC Deck answering a phone
only once it's allowed and never typing, and NectarLink's phone read and its own commands, all on this PC only."""
import http.client
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlparse

from tests.support import siri  # noqa: F401  temp APPDATA and the tripwires, before anything else
import phonelink


def fetch(url, method="GET", body=None, cookie=None):
    """(status, headers, body) from a server here, as the phone would ask it."""
    u = urlparse(url)
    con = http.client.HTTPConnection(u.hostname, u.port, timeout=5)
    headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 14)"}
    if cookie:
        headers["Cookie"] = cookie
    con.request(method, u.path, body=json.dumps(body) if body is not None else None, headers=headers)
    r = con.getresponse()
    out = (r.status, dict(r.getheaders()), r.read())
    con.close()
    return out


class Servers(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(phonelink, "lan_address", return_value="127.0.0.1")  # this PC only, in a test
        patch.start()
        self.addCleanup(patch.stop)
        self.dir = tempfile.mkdtemp()

    def test_the_shelfs_files_only_with_the_key_and_only_for_a_while(self):
        path = os.path.join(self.dir, "Ticket for Mum.pdf")
        with open(path, "wb") as f:
            f.write(b"%PDF hello")
        share = phonelink.Share([path, os.path.join(self.dir, "gone.txt")])
        self.addCleanup(share.stop)
        self.assertEqual(share.paths, [path])  # only files that are there
        status, _, page = fetch(share.url)
        self.assertEqual(status, 200)
        self.assertIn(b"Ticket for Mum.pdf", page)
        status, head, body = fetch(share.url + "f/0")
        self.assertEqual((status, body), (200, b"%PDF hello"))
        self.assertIn("attachment", head["Content-Disposition"])
        root = share.url.rsplit("/", 2)[0]
        self.assertEqual(fetch(root + "/wrongkey/")[0], 404)
        self.assertEqual(fetch(share.url + "f/9")[0], 404)
        share.until = 0  # its time's up
        self.assertEqual(fetch(share.url)[0], 410)
        with self.assertRaises(RuntimeError):
            phonelink.Share([])

    def test_the_deck_waits_for_a_phone_to_be_allowed_and_never_types(self):
        asked = []
        deck = phonelink.Deck(lambda phone, kind: asked.append((phone, kind)), lambda: [("Notepad", "C:\\n.exe")])
        self.addCleanup(deck.stop)
        status, head, page = fetch(deck.url)
        self.assertEqual(status, 200)
        self.assertIn(b"Notepad", page)
        cookie = head["Set-Cookie"].split(";")[0]
        self.assertTrue(cookie.startswith("hh_deck="))
        self.assertEqual(fetch(deck.url + "do", "POST", {"do": "hello"})[0], 404)  # no phone of its own: nothing
        with mock.patch.object(phonelink, "_user32") as user32:
            status, _, body = fetch(deck.url + "do", "POST", {"do": "move", "dx": 5, "dy": 5}, cookie)
            self.assertEqual(json.loads(body), {"state": "waiting"})
            self.assertEqual(asked, [(cookie.split("=", 1)[1], "an Android phone")])
            user32.mouse_event.assert_not_called()  # not allowed yet: the pointer stays where it is
            fetch(deck.url + "do", "POST", {"do": "move"}, cookie)
            self.assertEqual(len(asked), 1)  # asked once
            deck.allow(asked[0][0])
            fetch(deck.url + "do", "POST", {"do": "move", "dx": 900, "dy": -3}, cookie)
            user32.mouse_event.assert_called_with(phonelink.MOVE, 200, -3, 0, 0)  # a fling no further than 200
            fetch(deck.url + "do", "POST", {"do": "key", "key": "play"}, cookie)
            self.assertEqual(user32.keybd_event.call_args_list[0][0][0], 0xB3)
            user32.keybd_event.reset_mock()
            fetch(deck.url + "do", "POST", {"do": "key", "key": "a"}, cookie)  # no key that types
            fetch(deck.url + "do", "POST", {"do": "type", "text": "hunter2"}, cookie)
            user32.keybd_event.assert_not_called()
        self.assertEqual(fetch(deck.url + "do", "POST", {"x": "y" * 4000}, cookie)[0], 413)
        deck.allow("someone", False)
        self.assertEqual(json.loads(fetch(deck.url + "do", "POST", {}, "hh_deck=someone")[2]), {"state": "denied"})

    def test_its_apps_open_only_by_their_place_in_the_list(self):
        deck = phonelink.Deck(lambda *a: None, lambda: [("Notepad", "C:\\n.exe")])
        self.addCleanup(deck.stop)
        fetch(deck.url)
        with mock.patch.object(phonelink.os, "startfile") as start, \
                mock.patch.object(phonelink.threading, "Thread", side_effect=lambda target, args, **k: mock.Mock(
                    start=lambda: target(*args))):
            deck.do({"do": "app", "app": "0"})
            deck.do({"do": "app", "app": "C:\\evil.exe"})
            deck.do({"do": "app", "app": "7"})
        start.assert_called_once_with("C:\\n.exe")


class Nectar(unittest.TestCase):
    def test_its_phone_read_and_its_own_commands(self):
        folder = tempfile.mkdtemp()
        exe, db = os.path.join(folder, "nectarlink-desktop.exe"), os.path.join(folder, "nectarlink.db")
        open(exe, "w").close()
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE peers (id, name, kind, last_seen)")
        con.execute("INSERT INTO peers VALUES (1, 'Xiaomi 11 Lite NE', 'phone', 5)")
        con.commit()
        con.close()
        with mock.patch.object(phonelink, "NECTAR", exe), mock.patch.object(phonelink, "NECTAR_DB", db):
            self.assertEqual(phonelink.nectar_phone(), "Xiaomi 11 Lite NE")
            with mock.patch("subprocess.Popen") as run:
                phonelink.nectar_send([db, os.path.join(folder, "gone.txt")])
                self.assertEqual(run.call_args[0][0], [exe, "--send-to", db])
                phonelink.nectar_send(task="find-phone")
                self.assertEqual(run.call_args[0][0], [exe, "--task", "find-phone"])
                with self.assertRaises(ValueError):
                    phonelink.nectar_send(task="delete-everything")
                with self.assertRaises(RuntimeError):
                    phonelink.nectar_send([])
        with mock.patch.object(phonelink, "NECTAR", os.path.join(folder, "none.exe")):
            self.assertIsNone(phonelink.nectar_phone())

    def test_a_phones_kind_from_its_browser(self):
        self.assertEqual(phonelink.phone_name("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)"), "an iPhone")
        self.assertEqual(phonelink.phone_name("Mozilla/5.0 (Linux; Android 14)"), "an Android phone")
        self.assertEqual(phonelink.phone_name(""), "a phone")


if __name__ == "__main__":
    unittest.main()
