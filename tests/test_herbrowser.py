"""Her own browser (herbrowser.py, 31 October 2026): a Chrome of her own that her jobs on websites work in, never on
your screen, driven over a pipe only she holds. FakeChrome stands in for Chrome as DevTools sees it: a page of
controls in Chrome's accessibility tree, a DOM snapshot in the screen's pixels (1.5 a page pixel, as at Windows'
150%), focus, typing and clicks, and everything sent to it. Nothing here starts a browser or goes online."""
import base64
import collections
import io
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.support import siri, winplatform  # first: temp APPDATA and the tripwires
from tests.test_background import Jobs

import agent
import herbrowser
import settings


class FakeChrome:
    """Chrome on her page, as herbrowser sends it DevTools commands."""
    K = 1.5  # screen pixels a page pixel, as on a laptop at 150%

    def __init__(self, title="Test Kitchen", url="https://www.zomato.com/"):
        self.alive, self.proc = True, SimpleNamespace(pid=4242)
        self.sent, self.title, self.url = [], title, url
        self.controls, self.order = {}, []
        self.focused, self.selected, self.scroll, self.history = None, False, (0, 0), [url]

    def add(self, role, name, box=(0, 0, 80, 20), value=None, checked=None, attrs=None, on=None, parent=None,
            disabled=False, ignored=False, tag="DIV", clickable=False):
        n = 100 + len(self.order)
        self.controls[n] = dict(role=role, name=name, box=box, value=value, checked=checked, attrs=attrs or {}, on=on,
                                parent=parent, disabled=disabled, ignored=ignored, tag=tag, clickable=clickable)
        self.order.append(n)
        return n

    def call(self, method, session=None, timeout=None, **p):
        self.sent.append((method, p))
        handler = getattr(self, "_" + method.replace(".", "_"), None)
        return handler(**p) if handler else {}

    def methods(self, prefix=""):
        return [m for m, _ in self.sent if m.startswith(prefix)]

    def at(self, x, y):
        sx, sy = self.scroll
        for n in reversed(self.order):
            c = self.controls[n]
            if c["box"] is None:
                continue
            bx, by, bw, bh = c["box"]
            if bx - sx <= x <= bx - sx + bw and by - sy <= y <= by - sy + bh:
                return n
        return None

    def press(self, n):
        c = self.controls[n]
        if c["role"] in ("textbox", "searchbox"):  # a click in a box puts the cursor in it, as in Chrome
            self.focused = n
        if c["checked"] is not None:
            c["checked"] = not c["checked"]
        if c["on"]:
            c["on"]()

    # the accessibility tree
    def _node(self, n):
        c = self.controls[n]
        props = [{"name": "focused", "value": {"value": self.focused == n}}]
        if c["checked"] is not None:
            props.append({"name": "checked", "value": {"value": "true" if c["checked"] else "false"}})
        if c["disabled"]:
            props.append({"name": "disabled", "value": {"value": True}})
        node = {"nodeId": str(n), "backendDOMNodeId": n, "role": {"value": c["role"]}, "name": {"value": c["name"]},
                "properties": props, "ignored": c["ignored"], "parentId": str(c["parent"]) if c["parent"] else "1",
                "childIds": [str(k) for k in self.order if self.controls[k]["parent"] == n]}
        if c["value"] is not None:
            node["value"] = {"value": c["value"]}
        return node

    def _Accessibility_getFullAXTree(self):
        root = {"nodeId": "1", "backendDOMNodeId": 1, "role": {"value": "RootWebArea"}, "name": {"value": self.title},
                "childIds": [str(k) for k in self.order if not self.controls[k]["parent"]]}
        return {"nodes": [root] + [self._node(n) for n in self.order]}

    def _Accessibility_getPartialAXTree(self, backendNodeId, fetchRelatives=False):
        if backendNodeId not in self.controls:
            raise RuntimeError("No node with given id found")
        nodes, n = [self._node(backendNodeId)], self.controls[backendNodeId]["parent"]
        while fetchRelatives and n:
            nodes.append(self._node(n))
            n = self.controls[n]["parent"]
        return {"nodes": nodes}

    def _DOMSnapshot_captureSnapshot(self, computedStyles=()):
        strings, ids, attrs, index, bounds, clickable = [], [1], [[]], [], [], []
        sx, sy = self.scroll

        def at(text):
            strings.append(str(text))
            return len(strings) - 1
        for n in self.order:
            c = self.controls[n]
            ids.append(n)
            attrs.append([i for k, v in c["attrs"].items() for i in (at(k), at(v))])
            if c["clickable"]:
                clickable.append(len(ids) - 1)
            if c["box"] is not None:
                x, y, w, h = c["box"]
                index.append(len(ids) - 1)
                bounds.append([x * self.K, y * self.K, w * self.K, h * self.K])
        return {"strings": strings, "documents": [{"nodes": {"backendNodeId": ids, "attributes": attrs,
                                                             "isClickable": {"index": clickable}},
                                                   "layout": {"nodeIndex": index, "bounds": bounds},
                                                   "scrollOffsetX": sx * self.K, "scrollOffsetY": sy * self.K}]}

    def _Page_getLayoutMetrics(self):
        return {"cssLayoutViewport": {"clientWidth": 1280}, "layoutViewport": {"clientWidth": 1280 * self.K}}

    def _DOM_describeNode(self, backendNodeId=None, objectId=None):
        n = self.focused if objectId == "active" else backendNodeId
        if n is None:
            return {"node": {"nodeName": "BODY", "backendNodeId": 1}}
        if n not in self.controls:
            raise RuntimeError("No node with given id found")
        c = self.controls[n]
        return {"node": {"nodeName": c["tag"], "backendNodeId": n,
                         "attributes": [i for k, v in c["attrs"].items() for i in (k, v)]}}

    def _Runtime_evaluate(self, expression, returnByValue=False):
        if expression == "document.activeElement":
            return {"result": {"objectId": "active"}}
        if expression == "document.readyState":
            return {"result": {"value": "complete"}}
        return {"result": {}}

    def _DOM_resolveNode(self, backendNodeId):
        return {"object": {"objectId": f"node:{backendNodeId}"}}

    def _Runtime_callFunctionOn(self, objectId, functionDeclaration, arguments=(), returnByValue=False):
        n, f = int(objectId.split(":")[1]), functionDeclaration
        if "document.activeElement===this" in f:
            return {"result": {"value": self.focused == n}}
        if "closest('dialog" in f:
            up = self.controls[n]["parent"]
            while up and self.controls[up]["role"] != "dialog":
                up = self.controls[up]["parent"]
            return {"result": {"value": self.controls[up]["name"] if up else ""}}
        if "this.click()" in f:
            self.press(n)
        elif "collapse(false)" in f:
            self.selected = False
        elif "this.select()" in f:
            self.selected = True
        return {"result": {}}

    def _DOM_focus(self, backendNodeId):
        self.focused = backendNodeId

    def _Input_insertText(self, text):
        c = self.controls[self.focused]
        c["value"] = text if self.selected else (c["value"] or "") + text
        self.selected = False

    def _DOM_getContentQuads(self, backendNodeId):
        box = self.controls[backendNodeId]["box"]
        if box is None:
            return {"quads": []}
        x, y, w, h = box
        x, y = x - self.scroll[0], y - self.scroll[1]
        return {"quads": [[x, y, x + w, y, x + w, y + h, x, y + h]]}

    def _Input_dispatchMouseEvent(self, type, x, y, **more):
        if type == "mouseReleased":
            n = self.at(x, y)
            if n is not None:
                self.press(n)
        if type == "mouseWheel":
            self.scroll = (self.scroll[0], max(0, self.scroll[1] + more.get("deltaY", 0)))

    def _Page_navigate(self, url):
        self.url = url
        self.history.append(url)
        return {}

    def _Target_getTargetInfo(self, targetId=None):
        return {"targetInfo": {"title": self.title, "url": self.url}}

    def _Page_getNavigationHistory(self):
        return {"currentIndex": len(self.history) - 1,
                "entries": [{"id": i + 1, "url": u} for i, u in enumerate(self.history)]}

    def _Page_captureScreenshot(self, format="png"):
        import cv2
        import numpy as np
        ok, png = cv2.imencode(".png", np.zeros((herbrowser.H, herbrowser.W, 3), np.uint8))
        return {"data": base64.b64encode(png.tobytes()).decode()}

    def _DOM_getNodeForLocation(self, x, y, includeUserAgentShadowDOM=False):
        return {"backendNodeId": self.at(x, y) or 1}


class Page(unittest.TestCase):
    """herbrowser on FakeChrome: running, shown or not, with no sleeps and no browser started."""

    def setUp(self):
        self.chrome = FakeChrome()
        self.addCleanup(self.stop)
        herbrowser._chrome[0] = self.chrome
        herbrowser._page.update(session="s1", target="t1", window=1)
        herbrowser._shown[0] = False
        herbrowser._holders.clear()
        for name, value in (("_window_handle", lambda: None), ("_settle", lambda wait=0: None),
                            ("time", SimpleNamespace(sleep=lambda s: None, monotonic=time.monotonic,
                                                     time=time.time))):
            p = mock.patch.object(herbrowser, name, value)
            p.start()
            self.addCleanup(p.stop)

    def stop(self):
        herbrowser._chrome[0] = None
        herbrowser._shown[0] = False
        herbrowser._holders.clear()

    def kitchen(self):
        """A food site's page: a search box, a dish's Add, a cart, a password box, a switch, a post box and a
        Post button whose dialog asks first, a disabled button and one scrolled far down."""
        c, cart = self.chrome, [0]
        self.cart = cart
        self.search = c.add("searchbox", "Search dishes", (8, 79, 170, 22), value="", attrs={"id": "q"}, tag="INPUT")
        self.add_ = c.add("button", "Add", (106, 101, 39, 21), on=lambda: cart.__setitem__(0, cart[0] + 1))
        self.password = c.add("textbox", "Password", (98, 142, 170, 21), value="hunter2",
                              attrs={"type": "password"}, tag="INPUT")
        self.veg = c.add("checkbox", "Veg only", (12, 144, 13, 13), checked=False)
        self.post_box = c.add("textbox", "Write a post", (8, 163, 1248, 41), value="")
        self.dialog = c.add("dialog", "Post this to your feed?", None)
        self.ok = c.add("button", "OK", (500, 300, 40, 20), parent=self.dialog)
        c.add("button", "Pay now", (8, 230, 60, 20), disabled=True)
        self.far = c.add("button", "Far down button", (8, 2624, 112, 22))
        self.hidden = c.add("menuitem", "Delete account", None, ignored=False)
        return c


class Reading(Page):
    def test_her_page_reads_as_a_windows_controls(self):
        self.kitchen()
        snap = herbrowser.ui_snapshot()
        names = [(it["role"], it["name"]) for it in snap["items"]]
        self.assertEqual(names[0], ("button", "OK"))  # a dialog's controls first, as a window's are
        self.assertIn(("edit", "Search dishes"), names)
        self.assertIn(("checkbox", "Veg only"), names)
        self.assertNotIn(("button", "Pay now"), names)  # disabled, as UI Automation leaves it out
        self.assertNotIn(("menuitem", "Delete account"), names)  # nowhere on the page
        pw = next(it for it in snap["items"] if it["name"] == "Password")
        self.assertTrue(pw["password"])
        self.assertIsNone(pw["value"])  # a password's value is never read
        add = next(it for it in snap["items"] if it["name"] == "Add")
        self.assertEqual(add["rect"], (106, 101, 145, 122))  # the page's own pixels, not the screen's
        self.assertEqual(add["el"], herbrowser.Node(self.add_))
        self.assertEqual([it["id"] for it in snap["items"]], list(range(1, len(snap["items"]) + 1)))
        self.assertEqual((snap["hwnd"], snap["url"], snap["title"]), (herbrowser.TAB, self.chrome.url, "Test Kitchen"))
        far = [it["name"] for it in snap["items"]].index("Far down button")
        self.assertGreater(far, [it["name"] for it in snap["items"]].index("Add"))  # on the screen first

    def test_a_scrolled_page_gives_places_on_the_screen(self):
        self.kitchen()
        self.chrome.scroll = (0, 2000)
        far = next(it for it in herbrowser.ui_snapshot()["items"] if it["name"] == "Far down button")
        self.assertEqual(far["rect"][1], 624)

    def test_a_control_is_found_by_name_and_role_only_when_its_the_one(self):
        self.kitchen()
        self.assertEqual(herbrowser.find_ui("Add", "button"), herbrowser.Node(self.add_))
        self.assertEqual(herbrowser.find_ui("search dishes", "edit"), herbrowser.Node(self.search))
        self.assertEqual(herbrowser.find_ui(None, "edit", aid="q"), herbrowser.Node(self.search))
        self.assertIsNone(herbrowser.find_ui("Add", "link"))
        self.chrome.add("button", "Add", (106, 140, 39, 21))
        self.assertIsNone(herbrowser.find_ui("Add", "button"))  # two: she can't tell which
        self.assertEqual(len(herbrowser.find_all_ui("Add", "button")), 2)

    def test_what_a_control_is_and_holds(self):
        self.kitchen()
        info = herbrowser.ui_info(herbrowser.Node(self.search))
        self.assertEqual((info["name"], info["role"], info["aid"], info["password"]), ("Search dishes", "edit", "q",
                                                                                      False))
        self.assertTrue(herbrowser.ui_info(herbrowser.Node(self.password))["password"])
        self.assertIsNone(herbrowser.ui_value(herbrowser.Node(self.password)))
        self.assertEqual(herbrowser.ui_toggle(herbrowser.Node(self.veg)), "off")
        self.assertEqual(herbrowser.ui_dialog_text(herbrowser.Node(self.ok)), "Post this to your feed?")
        self.assertEqual(herbrowser.ui_dialog_text(herbrowser.Node(self.add_)), "")
        with self.assertRaises(LookupError):
            herbrowser.ui_info(herbrowser.Node(999))  # gone from the page

    def test_what_a_send_would_send_is_read_from_its_dialog(self):
        self.kitchen()
        fields = herbrowser.ui_fields(herbrowser.Node(self.ok))
        self.assertEqual(fields, [("button", "OK", None)])
        page = herbrowser.ui_fields()
        self.assertIn(("edit", "Password", None), page)  # never its value


class Doing(Page):
    def test_a_click_goes_into_the_page_never_your_mouse(self):
        self.kitchen()
        with mock.patch.object(winplatform, "click", side_effect=AssertionError("your mouse")):
            self.assertEqual(herbrowser.ui_act(herbrowser.Node(self.add_)), "clicked")
        self.assertEqual(self.cart[0], 1)
        moved = [p for m, p in self.chrome.sent if m == "Input.dispatchMouseEvent" and p["type"] == "mousePressed"]
        self.assertEqual((moved[0]["x"], moved[0]["y"]), (125.5, 111.5))  # its middle, in the page's pixels

    def test_one_with_no_place_is_clicked_by_its_own_click(self):
        self.kitchen()
        self.chrome.controls[self.add_]["box"] = None
        self.assertEqual(herbrowser.ui_act(herbrowser.Node(self.add_)), "invoked")
        self.assertEqual(self.cart[0], 1)

    def test_a_switch_is_set_once(self):
        self.kitchen()
        veg = herbrowser.Node(self.veg)
        self.assertEqual(herbrowser.ui_act(veg, state="on"), "toggled")
        self.assertEqual(herbrowser.ui_act(veg, state="on"), "already")
        self.assertEqual(herbrowser.ui_toggle(veg), "on")
        with self.assertRaises(RuntimeError):
            herbrowser.ui_act(herbrowser.Node(self.add_), state="on")  # not a switch

    def test_text_fills_a_box_and_a_type_step_adds_at_its_cursor(self):
        self.kitchen()
        box = herbrowser.Node(self.search)
        self.assertEqual(herbrowser.ui_act(box, "paneer"), "set")
        self.assertEqual(herbrowser.ui_act(box, "dal"), "set")  # in place of what was there
        self.assertEqual(herbrowser.ui_value(box), "dal")
        self.assertEqual(herbrowser.ui_act(box, " makhani", caret=True), "typed")
        self.assertEqual(herbrowser.ui_value(box), "dal makhani")
        self.assertEqual(herbrowser.ui_focused()["name"], "Search dishes")

    def test_keys_go_into_the_page(self):
        self.kitchen()
        herbrowser.press_keys("ctrl+a")
        down = next(p for m, p in self.chrome.sent if m == "Input.dispatchKeyEvent")
        self.assertEqual((down["key"], down["modifiers"], down["commands"]), ("a", 2, ["selectAll"]))
        herbrowser.press_keys("enter")
        enter = [p for m, p in self.chrome.sent if m == "Input.dispatchKeyEvent"][-2]
        self.assertEqual((enter["type"], enter["text"]), ("keyDown", "\r"))
        herbrowser.press_keys("shift+tab")
        tab = [p for m, p in self.chrome.sent if m == "Input.dispatchKeyEvent"][-2]
        self.assertEqual((tab["type"], tab["key"], tab["modifiers"]), ("rawKeyDown", "Tab", 8))

    def test_back_and_reload_are_the_browsers_own(self):
        self.kitchen()
        self.chrome.history.append("https://www.zomato.com/cart")
        herbrowser.press_keys("alt+left")
        self.assertIn(("Page.navigateToHistoryEntry", {"entryId": 1}), self.chrome.sent)
        herbrowser.press_keys("f5")
        self.assertIn("Page.reload", self.chrome.methods())

    def test_keys_for_its_own_bars_tabs_and_windows_arent_pressed(self):
        self.kitchen()
        for keys in ("ctrl+l", "ctrl+t", "ctrl+w", "ctrl+n", "alt+f4"):
            with self.subTest(keys=keys), self.assertRaises(RuntimeError) as why:
                herbrowser.press_keys(keys)
            self.assertEqual(str(why.exception), herbrowser.NOT_HERE)
        for keys in ("win+r", "win", "ctrl+win+d"):
            with self.subTest(keys=keys), self.assertRaisesRegex(RuntimeError, "Windows key"):
                herbrowser.press_keys(keys)
        with self.assertRaisesRegex(RuntimeError, "no capslock key"):
            herbrowser.press_keys("capslock")
        self.assertNotIn("Input.dispatchKeyEvent", self.chrome.methods())

    def test_a_click_at_a_point_and_whats_there(self):
        self.kitchen()
        self.assertEqual(herbrowser.ui_at(120, 110)["name"], "Add")
        herbrowser.click(120, 110)
        self.assertEqual(self.cart[0], 1)

    def test_a_scroll_is_a_wheel_in_her_page(self):
        self.kitchen()
        herbrowser.scroll(-5)
        self.assertEqual(self.chrome.scroll, (0, 500))
        herbrowser.scroll(5)
        self.assertEqual(self.chrome.scroll, (0, 0))

    def test_a_screenshot_is_her_pages_own(self):
        shot = herbrowser.shot()
        self.assertEqual((shot.rect, shot.to_screen(640, 450)), ((0, 0, herbrowser.W, herbrowser.H), (640, 450)))


class Sites(Page):
    def lookup(self, *addresses):
        return mock.patch.object(herbrowser.socket, "getaddrinfo",
                                 lambda host, port, **kw: [(2, 1, 6, "", (a, port)) for a in addresses])

    def test_only_public_sites(self):
        with self.lookup("142.250.183.110"):
            self.assertTrue(herbrowser.public("https://www.zomato.com/"))
            self.assertTrue(herbrowser.public("http://example.com:80/x"))
            self.assertFalse(herbrowser.public("https://www.zomato.com:8443/"))  # another port
            self.assertFalse(herbrowser.public("ftp://example.com/"))
        for address in ("127.0.0.1", "192.168.1.1", "10.0.0.5", "172.16.3.4", "169.254.169.254", "::1", "fe80::1",
                        "100.64.0.1", "0.0.0.0", "224.0.0.1"):
            with self.subTest(address=address), self.lookup(address):
                self.assertFalse(herbrowser.public("http://router.example/"))
        with self.lookup("142.250.183.110", "192.168.1.1"):  # one of its names at home: not let through
            self.assertFalse(herbrowser.public("https://sneaky.example/"))

    def test_a_name_not_found_isnt_let_through_on_trust(self):
        with mock.patch.object(herbrowser.socket, "getaddrinfo", side_effect=OSError("not found")):
            self.assertIsNone(herbrowser.public("http://myrouter/"))
            with self.assertRaisesRegex(RuntimeError, "couldn't find that site"):
                herbrowser.go("http://myrouter/")

    def test_go_opens_public_sites_only(self):
        with self.lookup("192.168.1.1"), self.assertRaisesRegex(RuntimeError, "only opens public sites"):
            herbrowser.go("http://192.168.1.1/")
        for address in ("file:///C:/Windows/win.ini", "ms-settings:display", "javascript:alert(1)", ""):
            with self.subTest(address=address), self.assertRaisesRegex(RuntimeError, "only opens web addresses"):
                herbrowser.go(address)
        self.assertNotIn("Page.navigate", self.chrome.methods())
        with self.lookup("142.250.183.110"):
            self.assertEqual(herbrowser.go("https://www.zomato.com/ncr"), "website")
        self.assertEqual(self.chrome.url, "https://www.zomato.com/ncr")


class Pipe(unittest.TestCase):
    """The pipe itself, without Chrome: NUL-separated JSON, replies by id, and a page's own questions answered."""

    def pipe(self, data):
        p = herbrowser.Pipe.__new__(herbrowser.Pipe)
        p._in, p._replies, p.alive, p.events = io.BytesIO(data), {}, True, collections.deque()
        p._ready, p.answered = threading.Condition(), []
        p.call = lambda method, session=None, timeout=None, **kw: p.answered.append((method, session, kw))
        return p

    def test_replies_by_id_and_the_rest_as_events(self):
        p = self.pipe(b'{"id":1,"result":{"a":1}}\0{"method":"Page.loadEventFired","params":{}}\0{"id":2,"res')
        p._read()
        self.assertEqual(p._replies, {1: {"id": 1, "result": {"a": 1}}})
        self.assertEqual([e["method"] for e in p.events], ["Page.loadEventFired"])
        self.assertFalse(p.alive)  # Chrome gone: no reply will come

    def test_a_pages_own_question_is_answered_no_and_leaving_yes(self):
        p = self.pipe(b"")
        p._answer({"sessionId": "s", "params": {"type": "confirm", "message": "Delete your account?"}})
        p._answer({"sessionId": "s", "params": {"type": "beforeunload", "message": ""}})
        self.assertEqual(p.answered, [("Page.handleJavaScriptDialog", "s", {"accept": False}),
                                      ("Page.handleJavaScriptDialog", "s", {"accept": True})])


class Routing(unittest.TestCase):
    """agent's win (herbrowser.Surface): her page's calls answered by herbrowser, everything else by winplatform as it
    is when called."""

    def setUp(self):
        self.real = SimpleNamespace(ui_act=lambda *a, **k: "real", window_of=lambda h: ("real", h), BROWSER_EXES={"x"},
                                    find_ui=lambda *a, **k: "real", front_window=lambda: "real", idle_seconds=lambda: 9)
        self.on = [False]
        self.win = herbrowser.Surface(self.real, on=lambda: self.on[0])

    def test_her_pages_calls_go_to_her_browser(self):
        node = herbrowser.Node(5)
        with mock.patch.object(herbrowser, "ui_act", lambda *a, **k: "hers"), \
                mock.patch.dict(herbrowser.ROUTED["el"], {"ui_act": lambda *a, **k: "hers"}), \
                mock.patch.dict(herbrowser.ROUTED["hwnd"], {"window_of": lambda h: ("hers", h)}), \
                mock.patch.dict(herbrowser.ROUTED["found"], {"find_ui": lambda *a, **k: "hers"}), \
                mock.patch.dict(herbrowser.ROUTED["run"], {"front_window": lambda: "hers"}):
            self.assertEqual(self.win.ui_act(node, "x"), "hers")
            self.assertEqual(self.win.ui_act(object(), "x"), "real")
            self.assertEqual(self.win.window_of(herbrowser.TAB), ("hers", herbrowser.TAB))
            self.assertEqual(self.win.window_of(7), ("real", 7))
            self.assertEqual(self.win.find_ui("Add", "button", hwnd=herbrowser.TAB), "hers")
            self.assertEqual(self.win.find_ui("Add", "button", None, herbrowser.TAB), "hers")
            self.assertEqual(self.win.find_ui("Add", "button", hwnd=7), "real")
            self.assertEqual(self.win.front_window(), "real")  # a run not in her browser
            self.on[0] = True
            self.assertEqual(self.win.front_window(), "hers")
        self.assertEqual(self.win.idle_seconds(), 9)  # not hers to answer, ever
        self.assertEqual(self.win.BROWSER_EXES, {"x"})

    def test_what_a_test_patches_on_winplatform_is_what_it_reaches(self):
        self.real.front_window = lambda: "patched"
        self.assertEqual(self.win.front_window(), "patched")

    def test_agent_reaches_winplatform_through_it(self):
        self.assertIsInstance(agent.win, herbrowser.Surface)
        with mock.patch.object(winplatform, "front_window", lambda: 77):
            self.assertEqual(agent.win.front_window(), 77)


class Commands(Page):
    """What's said about her browser, with no model, with her name (shown and hidden also without it)."""

    def setUp(self):
        super().setUp()
        self.did = []
        for name, value in (("show", lambda url=None: self.did.append(("show", url)) or True),
                            ("hide", lambda: self.did.append(("hide",)) or True),
                            ("close", lambda: self.did.append(("close",))),
                            ("program", lambda: r"C:\Chrome\chrome.exe")):
            p = mock.patch.object(herbrowser, name, value)
            p.start()
            self.addCleanup(p.stop)
        herbrowser.bind(siri)
        self.addCleanup(settings.put, "own_browser", True)

    def say(self, words, gate=False):
        return herbrowser.quick(words, siri.plain, gate)

    def test_show_it_to_sign_in(self):
        for words in ("show me your browser", "open your browser", "take control of your browser",
                      "let me sign in to your browser"):
            with self.subTest(words=words):
                self.did.clear()
                plan = self.say(words)
                self.assertEqual(self.did, [("show", None)])
                self.assertIn("Sign in", plan["say"])

    def test_sign_in_to_a_site_she_knows_or_one_said_as_an_address(self):
        self.say("sign in to linkedin in your browser")
        self.assertEqual(self.did[-1], ("show", "https://www.linkedin.com"))
        self.say("log into zomato on your browser")
        self.assertEqual(self.did[-1], ("show", "https://www.zomato.com"))
        self.say("sign me in to example.in in your browser")
        self.assertEqual(self.did[-1], ("show", "https://example.in"))
        plan = self.say("sign in to my bank thing in your browser")
        self.assertIn("I don't know where", plan["say"])

    def test_hidden_again_only_when_its_shown(self):
        self.assertIsNone(self.say("hide your browser"))  # not in front of you: not for her
        herbrowser._shown[0] = True
        self.assertIn("put away", self.say("hide your browser")["say"])
        self.assertIn("put away", self.say("i'm done signing in")["say"])
        self.assertEqual(self.did, [("hide",), ("hide",)])

    def test_closed_turned_off_and_on(self):
        self.say("close your browser")
        self.assertEqual(self.did, [("close",)])
        self.say("don't use your browser")
        self.assertFalse(settings.get("own_browser"))
        self.say("use your own browser")
        self.assertTrue(settings.get("own_browser"))

    def test_shown_and_hidden_without_her_name_only_when_the_words_name_her_browser(self):
        # on 31 October "show me your browser" said without her name went to the model, which opened your Chrome
        self.say("show me your browser", gate="cold")
        self.say("sign in to linkedin in your browser", gate="cold")
        self.assertEqual(self.did, [("show", None), ("show", "https://www.linkedin.com")])
        herbrowser._shown[0] = True
        self.assertIn("put away", self.say("hide your browser", gate="cold")["say"])
        self.did.clear()
        for words in ("take control", "let me sign in", "i'm done", "carry on", "hide", "close your browser",
                      "don't use your browser", "use your browser"):
            with self.subTest(words=words):
                self.assertIsNone(self.say(words, gate="cold"))  # said in the room, or more than showing it
        self.assertEqual(self.did, [])
        self.assertTrue(settings.get("own_browser"))

    def test_never_in_a_test_run_and_never_without_chrome(self):
        settings.put("own_browser", True)
        self.assertFalse(herbrowser.available())  # HEYHARRY_TESTING
        with mock.patch.dict("os.environ", {"HEYHARRY_TESTING": ""}):
            self.assertTrue(herbrowser.available())
            with mock.patch.object(herbrowser, "program", lambda: ""):
                self.assertFalse(herbrowser.available())
            settings.put("own_browser", False)
            self.assertFalse(herbrowser.available())


class Idle(Page):
    def test_closed_when_idle_never_while_shown_or_working(self):
        herbrowser._last[0] = time.monotonic() - herbrowser.IDLE - 1
        self.assertTrue(herbrowser.idle_now())
        herbrowser._shown[0] = True
        self.assertFalse(herbrowser.idle_now())
        herbrowser._shown[0] = False
        herbrowser.keep_open(3)
        self.assertFalse(herbrowser.idle_now())
        herbrowser.let_go(3)
        self.assertTrue(herbrowser.idle_now())
        herbrowser._last[0] = time.monotonic()
        self.assertFalse(herbrowser.idle_now())


class Jobs_(Jobs):
    """A job in the background on a website, done in her own browser: never your screen, every gate the same."""

    def setUp(self):
        super().setUp()
        self.chrome = FakeChrome(title="Zomato", url="about:blank")
        self.cart = [0]

        def add():
            self.cart[0] += 1
            self.chrome.controls[self.view]["name"] = f"View cart ({self.cart[0]})"
        self.chrome.add("searchbox", "Search dishes", (8, 79, 170, 22), value="", tag="INPUT")
        self.add_ = self.chrome.add("button", "Add", (106, 101, 39, 21), on=add)
        self.view = self.chrome.add("link", "View cart (0)", (900, 20, 120, 20))
        settings.put("own_browser", True)
        herbrowser._shown[0] = False
        herbrowser._holders.clear()
        for target, name, value in ((herbrowser, "available", lambda: True), (herbrowser, "public", lambda a: True),
                                    (herbrowser, "_ensure", self.ensure), (herbrowser, "_settle", lambda wait=0: None),
                                    (herbrowser, "_window_handle", lambda: None),
                                    (herbrowser, "time", SimpleNamespace(sleep=lambda s: None,
                                                                         monotonic=time.monotonic, time=time.time))):
            self.patch(target, name, value)
        self.addCleanup(lambda: herbrowser._chrome.__setitem__(0, None))

    def ensure(self):
        herbrowser._chrome[0] = self.chrome
        herbrowser._page.update(session="s1", target="t1", window=1)
        return self.chrome

    def add_id(self, name="Add"):
        return next(it["id"] for it in herbrowser.ui_snapshot()["items"] if it["name"] == name)

    def test_a_job_on_a_site_works_in_her_browser_and_never_takes_your_screen(self):
        front = self.app.front
        leased = []
        self.patch(agent, "screen", lambda r: leased.append(r) or self.fail("it took your screen"))
        self.model({"steps": [{"do": "website", "url": "https://www.zomato.com/"}]},
                   lambda: {"steps": [{"do": "click", "id": self.add_id()}]},
                   {"steps": [], "done": True, "expect": {"has": "View cart (1)"}, "say": "Added it to your cart."})
        tid = self.queue_job("add paneer tikka to my zomato cart")
        siri.run_job(self.claim(tid))
        self.assertEqual(self.chrome.url, "https://www.zomato.com/")  # in her browser
        self.assertEqual(self.app.opened, [])  # nothing opened on your screen
        self.assertIs(self.app.front, front)  # your window still in front
        self.assertEqual(leased, [])
        # Zomato's a site your words named, and Add isn't a very sensitive place: no yes for it (the owner, 31 October)
        self.assertTrue(self.told.empty() or not isinstance(self.told.queue[0], siri.JobAsk))
        self.assertEqual(self.cart[0], 1)  # clicked in her page
        self.assertEqual(self.store.get(tid)["status"], "completed")
        self.assertNotIn(tid, herbrowser._holders)  # let go once it's over: it can close when idle

    def test_placing_the_order_still_waits_for_your_yes(self):
        placed = []
        self.chrome.add("button", "Place order", (1000, 800, 120, 30), on=lambda: placed.append(True))
        self.model({"steps": [{"do": "website", "url": "https://www.zomato.com/"}]},
                   lambda: {"steps": [{"do": "click", "id": self.add_id()}, {"do": "click", "id": self.add_id(
                       "Place order")}]})
        tid = self.queue_job("add paneer tikka to my zomato cart and order it")
        siri.run_job(self.claim(tid))
        self.assertEqual(self.cart[0], 1)  # Add went ahead
        self.assertEqual(placed, [])  # the order waits
        asked = self.told.get_nowait()
        self.assertIn("Place order", asked)
        self.assertEqual(self.store.get(tid)["status"], "waiting_approval")

    def test_a_site_you_didnt_name_still_asks(self):
        def go(job, r):
            r.pin = herbrowser.TAB
            herbrowser.go("https://www.zomato.com/")
            agent.observe(r)
            el = herbrowser.ui_info(herbrowser.find_ui("Add", "button"))
            self.chrome.url = "https://phish.example/menu"  # a link took her there
            elsewhere = agent.gate(r, 0, {"do": "click", "id": 2}, el)
            self.chrome.url = "https://www.zomato.com/"
            named = agent.gate(r, 0, {"do": "click", "id": 2}, el)
            return elsewhere, named
        elsewhere, named = self.run_in_job(5, go, goal="add paneer tikka to my zomato cart")
        self.assertEqual(elsewhere, ("ask", "what I read could be steering this"))
        self.assertEqual(named, (None, ""))

    def test_only_the_very_sensitive_ask(self):
        def go(job, r):
            r.pin = herbrowser.TAB
            herbrowser.go("https://www.zomato.com/")
            agent.observe(r)
            asked = {}
            for name in ("Remove", "Clear", "Submit", "Confirm", "Accept", "Sign out", "Unsubscribe", "Report",
                         "Send", "Post", "Pay now", "Place order", "Buy now", "Delete", "Share", "Comment",
                         "Proceed to checkout", "Uninstall"):
                el = {"name": name, "role": "button", "aid": "", "password": False, "el": herbrowser.Node(1)}
                asked[name] = agent.gate(r, 0, {"do": "click", "id": 1}, el)[0]
            return asked
        asked = self.run_in_job(5, go, goal="sort out my zomato account")
        self.assertEqual({k for k, v in asked.items() if v == "ask"},
                         {"Send", "Post", "Pay now", "Place order", "Buy now", "Delete", "Share", "Comment",
                          "Proceed to checkout", "Uninstall"})
        self.assertEqual({k for k, v in asked.items() if v is None},
                         {"Remove", "Clear", "Submit", "Confirm", "Accept", "Sign out", "Unsubscribe", "Report"})

    def test_the_model_is_told_its_in_her_browser_and_sees_her_page(self):
        script = self.model({"steps": [{"do": "website", "url": "https://www.zomato.com/"}]},
                            {"steps": [], "done": True, "say": "It's open."})
        siri.run_job(self.claim(self.queue_job("open zomato and look at the menu")))
        self.assertIn("your own browser", script.text(0))
        self.assertIn('"Add"', script.text(1))  # her page's controls, read from Chrome's own tree
        self.assertIn("Search dishes", script.text(1))

    def test_a_job_waits_while_you_have_her_browser(self):
        herbrowser._shown[0] = True
        self.patch(herbrowser, "wait_till_free", mock.Mock(side_effect=TimeoutError()))

        def go(job, r):
            r.pin = herbrowser.TAB
            return agent._go(r)
        line = self.run_in_job(4, go, goal="add dal to my cart")
        self.assertEqual(line, "You had my browser the whole time, so I've left it.")
        self.assertNotIn("Input.dispatchMouseEvent", self.chrome.methods())

    def test_a_turns_task_never_uses_her_browser(self):
        r = agent.start(goal="post on linkedin")
        self.assertFalse(agent.in_browser(r, {"do": "website", "url": "https://www.linkedin.com"}))
        token = agent.RUN.set(r)
        try:
            self.assertTrue(agent.needs_screen({"do": "website", "url": "https://www.linkedin.com"}))
        finally:
            agent.RUN.reset(token)

    def test_which_steps_of_a_job_go_to_her_browser(self):
        def go(job, r):
            asked = [agent.in_browser(r, s) for s in (
                {"do": "website", "url": "https://www.zomato.com"}, {"do": "website", "url": "ms-settings:display"},
                {"do": "open", "app": "Chrome"}, {"do": "open", "app": "Google Chrome"},
                {"do": "open", "app": "the browser"}, {"do": "open", "app": "Notepad"}, {"do": "click", "id": 1})]
            r.pin = herbrowser.TAB
            on_tab = [agent.in_browser(r, s) for s in ({"do": "click", "id": 1}, {"do": "keys", "keys": "enter"},
                                                       {"do": "switch", "to": "Excel"}, {"do": "open", "app": "Excel"})]
            return asked, on_tab
        asked, on_tab = self.run_in_job(4, go)
        self.assertEqual(asked, [True, False, True, True, True, False, False])
        self.assertEqual(on_tab, [True, True, False, False])

    def test_a_chat_site_is_left_alone_in_her_browser_too(self):
        obs = {"full": True, "exe": "chrome.exe", "title": "Instagram", "site": "instagram.com", "items": [],
               "url": "https://www.instagram.com/direct/inbox/"}
        self.assertEqual(agent.off_limits(obs)[0], "chat")


class Planner(unittest.TestCase):
    """siri sends a task on a website to her browser, as a job, unless you asked to see it."""

    def setUp(self):
        p = mock.patch.object(herbrowser, "available", lambda: True)
        p.start()
        self.addCleanup(p.stop)

    def plan(self, *steps):
        return {"steps": list(steps), "say": ""}

    def test_a_task_after_opening_a_site_is_a_job_in_her_browser(self):
        plan = self.plan({"do": "website", "url": "https://www.linkedin.com"},
                         {"do": "screen", "task": "write a post saying I'm excited about my project"})
        self.assertTrue(siri.for_her_browser(plan, "post on linkedin that I'm excited about my project"))
        done = siri.backgrounded(plan, "post on linkedin that I'm excited about my project")
        self.assertEqual([s["do"] for s in done["steps"]], ["background"])
        self.assertIn("https://www.linkedin.com", done["steps"][0]["hints"])

    def test_a_task_naming_a_site_she_knows_is_one_too(self):
        self.assertTrue(siri.for_her_browser(self.plan({"do": "task", "goal": "add paneer tikka to my zomato cart"}),
                                             "add paneer tikka to my zomato cart"))
        self.assertTrue(siri.for_her_browser(self.plan({"do": "task", "goal": "check my orders on amazon.in"}), "x"))

    def test_not_when_you_ask_to_see_it_or_its_on_your_screen(self):
        site = {"do": "website", "url": "https://www.linkedin.com"}
        task = {"do": "screen", "task": "show my notifications"}
        self.assertFalse(siri.for_her_browser(self.plan(site, task), "show me my linkedin notifications"))
        self.assertFalse(siri.for_her_browser(self.plan(site, task), "open linkedin on my screen"))
        self.assertFalse(siri.for_her_browser(self.plan({"do": "screen", "task": "click the sign in button"}),
                                              "click the sign in button"))
        self.assertFalse(siri.for_her_browser(self.plan({"do": "screen", "task": "click linkedin's sign in"}), "x"))
        self.assertFalse(siri.for_her_browser(self.plan({"do": "website", "url": "https://youtube.com"}), "open yt"))

    def test_not_without_her_browser(self):
        with mock.patch.object(herbrowser, "available", lambda: False):
            plan = self.plan({"do": "website", "url": "https://www.linkedin.com"}, {"do": "screen", "task": "post"})
            self.assertFalse(siri.for_her_browser(plan, "post on linkedin"))
            self.assertIs(siri.backgrounded(plan, "post on linkedin"), plan)


if __name__ == "__main__":
    unittest.main()


class LiveCard(unittest.TestCase):
    """A job's card in the corner (jobview): a live picture of the window it works in now, her own browser's for one
    working there, which Windows draws though it's off your screens; a click on its card hands you her browser."""

    def setUp(self):
        import activity
        activity.clear()
        self.addCleanup(activity.clear)
        agent.JOBS.clear()
        self.addCleanup(agent.JOBS.clear)
        for name, value in (("window_exists", lambda h: h in (4242, 555)), ("minimised", lambda h: False)):
            p = mock.patch.object(winplatform, name, value)
            p.start()
            self.addCleanup(p.stop)

    def job(self, tid, pin):
        import activity
        job = agent.Job(tid, "add dal to my zomato cart")
        job.runs.append(SimpleNamespace(pin=pin))
        agent.JOBS[tid] = job
        activity.publish(f"task:{tid}", title="Add dal to my Zomato cart", kind="agent", state="running",
                         note="Working in my browser")
        return job

    def test_a_job_in_her_browser_shows_her_page(self):
        import jobview
        self.job(7, herbrowser.TAB)
        with mock.patch.object(herbrowser, "window", lambda: 4242):
            (card,) = jobview.sections()
        self.assertEqual((card["key"], card["thumb"]), (7, 4242))

    def test_a_job_on_your_screen_shows_the_window_it_opened(self):
        import jobview
        self.job(8, 555)  # opened since it started: the job's own pin was never set
        (card,) = jobview.sections()
        self.assertEqual(card["thumb"], 555)

    def test_clicking_its_card_hands_you_her_browser(self):
        import jobview
        self.job(7, herbrowser.TAB)
        with mock.patch.object(herbrowser, "show") as shown, \
                mock.patch.object(winplatform, "bring_to_front", side_effect=AssertionError("your window")):
            jobview._clicked(7)
        shown.assert_called_once_with()


class Remote(Page):
    """Take control from your phone (remote_view, remote_tap, remote_type): her page as a numbered picture with a
    button for each number, your taps clicking in her page, and her jobs waiting while you have it."""

    def setUp(self):
        super().setUp()
        self.kitchen()
        self.addCleanup(herbrowser.remote_end)
        self.sent, self.pictures = [], []
        host = SimpleNamespace(PHONE={"send": lambda chat, line: self.sent.append((chat, line)),
                                      "control": lambda chat, jpeg, caption, rows, message: self.pictures.append(
                                          (chat, caption, rows, message)) or 77})
        p = mock.patch.object(herbrowser, "host", host)
        p.start()
        self.addCleanup(p.stop)
        herbrowser.remote_start(42)

    def buttons(self, rows):
        return {label: data for row in rows for label, data in row}

    def test_each_control_on_the_screen_gets_a_numbered_button(self):
        jpeg, caption, rows = herbrowser.remote_view()
        self.assertTrue(jpeg.startswith(b"\xff\xd8"))  # a small JPEG
        labels = list(self.buttons(rows))
        self.assertIn("Test Kitchen", caption)
        self.assertTrue(any(label.endswith(". OK") for label in labels))
        self.assertTrue(any(label.endswith(". Search dishes (box)") for label in labels))
        self.assertFalse(any("Password" in label for label in labels))  # never offered over Telegram
        self.assertFalse(any("Far down" in label for label in labels))  # not on the screen
        self.assertEqual(labels[-6:], ["Type", "Scroll down", "Scroll up", "Back", "New picture", "Done"])
        self.assertTrue(all(len(data.encode()) <= 64 for data in self.buttons(rows).values()))  # Telegram's limit

    def test_a_tap_clicks_in_her_page(self):
        _, _, rows = herbrowser.remote_view()
        add = next(data for label, data in self.buttons(rows).items() if label.endswith(". Add"))
        self.assertEqual(herbrowser.remote_tap(add), ("view", ""))
        self.assertEqual(self.cart[0], 1)

    def test_a_tap_on_an_older_picture_clicks_nothing(self):
        _, _, old = herbrowser.remote_view()
        herbrowser.remote_view()  # a newer picture since
        add = next(data for label, data in self.buttons(old).items() if label.endswith(". Add"))
        kind, line = herbrowser.remote_tap(add)
        self.assertEqual((kind, self.cart[0]), ("view", 0))
        self.assertIn("older picture", line)

    def test_typing_goes_into_the_box_you_tapped_never_a_password(self):
        _, _, rows = herbrowser.remote_view()
        tap = self.buttons(rows)
        box = next(data for label, data in tap.items() if "Search dishes" in label)
        herbrowser.remote_tap(box)  # a click puts the cursor in it
        self.assertEqual(herbrowser.remote_tap(tap["Type"])[0], "say")
        self.assertTrue(herbrowser.remote_wants_text())
        self.assertEqual(herbrowser.remote_type("dal makhani"), ("view", ""))
        self.assertEqual(herbrowser.ui_value(herbrowser.Node(self.search)), "dal makhani")
        self.assertFalse(herbrowser.remote_wants_text())
        self.chrome.focused = self.password  # the cursor in the password box
        _, _, rows = herbrowser.remote_view()
        self.assertEqual(herbrowser.remote_tap(self.buttons(rows)["Type"]), ("say", herbrowser.NO_PASSWORDS))
        self.assertEqual(herbrowser.remote_type("hunter3"), ("say", herbrowser.NO_PASSWORDS))
        self.assertIsNone(herbrowser.ui_value(herbrowser.Node(self.password)))

    def test_her_jobs_wait_while_you_have_it_and_carry_on_after_done(self):
        self.assertTrue(herbrowser.shown())
        _, _, rows = herbrowser.remote_view()
        self.assertEqual(herbrowser.remote_tap(self.buttons(rows)["Done"])[0], "say")
        self.assertFalse(herbrowser.shown())
        herbrowser.remote_start(42)
        herbrowser._remote["at"] -= herbrowser.REMOTE_IDLE + 1  # no tap for 5 minutes
        self.assertFalse(herbrowser.shown())

    def test_a_tap_comes_back_as_a_new_picture_in_place(self):
        herbrowser.to_phone(42)
        self.assertEqual(self.pictures[-1][0], 42)
        self.assertIsNone(self.pictures[-1][3])  # the first: a new message
        _, _, rows, _ = self.pictures[-1]
        herbrowser.phone_tap(self.buttons(rows)["Scroll down"], 42)
        self.assertEqual(self.pictures[-1][3], 77)  # changed in place
        herbrowser.phone_tap(self.buttons(self.pictures[-1][2])["Done"], 42)
        self.assertEqual(self.sent[-1], (42, "Done. I'll carry on with my jobs in it."))

    def test_show_me_your_browser_from_your_phone_comes_to_your_phone(self):
        herbrowser.remote_end()
        host = SimpleNamespace(PHONE=herbrowser.host.PHONE, PHONE_CHAT=SimpleNamespace(get=lambda: 42),
                               origin=lambda: "phone", SITES=siri.SITES, key_of=siri.key_of)
        with mock.patch.object(herbrowser, "host", host), mock.patch.object(herbrowser, "public", lambda a: True), \
                mock.patch.object(herbrowser, "program", lambda: r"C:\Chrome\chrome.exe"), \
                mock.patch.object(herbrowser, "show", side_effect=AssertionError("on the PC")):
            plan = herbrowser.quick("open zomato in your browser", siri.plain)
        self.assertIn("Tap a number", plan["say"])
        self.assertEqual(self.chrome.url, "https://www.zomato.com")
        self.assertEqual(self.pictures[-1][0], 42)
        self.assertTrue(herbrowser.remote_on())


class PhoneTaps(unittest.TestCase):
    """telegram_bot: a tap on her browser's picture reaches her browser only from your account."""

    def tap(self, user, data):
        import asyncio
        import telegram_bot
        got = threading.Event()
        seen = []
        bot = telegram_bot.Bot(on_message=None, on_tap=lambda *a: seen.append(("yes/no", a)),
                               on_browser=lambda data, chat: seen.append(("browser", data, chat)) or got.set())

        async def answer():
            return None
        q = SimpleNamespace(data=data, message=SimpleNamespace(chat_id=42, message_id=5), answer=answer)
        update = SimpleNamespace(callback_query=q, effective_user=SimpleNamespace(id=user))
        with mock.patch.object(telegram_bot, "owner", lambda: 42):
            asyncio.run(bot._tap(update, None))
        got.wait(2)
        return seen

    def test_your_taps_reach_her_browser(self):
        self.assertEqual(self.tap(42, "b:a1b2c3:c4"), [("browser", "b:a1b2c3:c4", 42)])

    def test_anyone_elses_do_nothing(self):
        self.assertEqual(self.tap(99, "b:a1b2c3:c4"), [])


class PlainBlocks(Page):
    """What a site built from plain blocks that Chrome says is clicked on (DOMSnapshot's isClickable): offered as a
    button named by its own text, for her jobs and your phone, as real Zomato's restaurant cards and its own buttons
    weren't on 31 October."""

    def page(self):
        c = self.chrome
        self.scroll_btn = c.add("generic", "", (600, 860, 90, 20), clickable=True)
        inner = c.add("generic", "", (600, 860, 80, 20), clickable=True, parent=self.scroll_btn)  # nested in it
        c.add("StaticText", "Scroll down", (600, 860, 80, 20), parent=inner)
        card = c.add("generic", "", (40, 300, 300, 200), clickable=True)  # a card round a real link
        c.add("link", "Paneer Palace", (50, 310, 120, 20), parent=card)
        c.add("generic", "", (0, 0, 1280, 3000), clickable=True)  # the whole page, a click catcher
        c.add("generic", "", (700, 300, 50, 50), clickable=True)  # nothing in it to name it by
        self.order_btn = c.add("generic", "", (900, 800, 140, 40), clickable=True)
        c.add("StaticText", "Place order", (900, 800, 140, 40), parent=self.order_btn)
        c.add("generic", "Not clickable", (900, 100, 100, 20))  # no click handler: just text

    def test_a_clickable_block_is_a_button_named_by_its_text(self):
        self.page()
        names = [(it["role"], it["name"]) for it in herbrowser.ui_snapshot()["items"]]
        self.assertIn(("button", "Scroll down"), names)
        self.assertIn(("button", "Place order"), names)
        self.assertIn(("link", "Paneer Palace"), names)
        self.assertEqual(names.count(("button", "Scroll down")), 1)  # the outer block, once, not the one in it
        self.assertEqual(sum(1 for r, n in names if "Paneer Palace" in n), 1)  # the card round it isn't offered
        self.assertEqual([n for r, n in names if r == "button"], ["Scroll down", "Place order"])
        self.assertNotIn("Not clickable", [n for _, n in names])

    def test_it_is_found_again_and_known_by_its_name(self):
        self.page()
        node = herbrowser.find_ui("Scroll down", "button")
        self.assertEqual(node, herbrowser.Node(self.scroll_btn))
        info = herbrowser.ui_info(node)
        self.assertEqual((info["role"], info["name"]), ("button", "Scroll down"))

    def test_the_very_sensitive_ones_still_ask(self):
        self.page()
        r = agent.Run(goal="add dal to my zomato cart")
        r.job = SimpleNamespace(id=1)
        el = herbrowser.ui_info(herbrowser.find_ui("Place order", "button"))
        with mock.patch.object(agent, "front", lambda run=None: (herbrowser.TAB, "chrome.exe", "Zomato")),                 mock.patch.object(agent, "site_in", lambda run, exe: "zomato.com"):
            self.assertEqual(agent.gate(r, 0, {"do": "click", "id": 1}, el), ("ask", "Place order can't be undone"))


class PhoneOrder(Page):
    """Your phone's buttons as you'd read the page, not in its code's order, each control once, labelled by its words."""

    def setUp(self):
        super().setUp()
        c = self.chrome
        c.add("link", "Bottom link", (40, 600, 100, 20))  # first in the page's code, low on the screen
        c.add("searchbox", "Search for restaurant, cuisine or a dish", (500, 10, 400, 40), tag="INPUT")
        c.add("link", "Home /", (80, 90, 50, 20))
        c.add("link", "Home /", (80, 90, 50, 20))  # read twice in one place, as Zomato's breadcrumbs were
        c.add("tab", "illustration Dining Out", (80, 120, 200, 80))
        c.add("button", "location-fill", (240, 20, 20, 20))
        self.addCleanup(herbrowser.remote_end)
        herbrowser.remote_start(42)

    def test_in_reading_order_once_each_icons_last(self):
        _, _, rows = herbrowser.remote_view()
        labels = [label for row in rows[:-2] for label, _ in row]
        self.assertEqual(labels, ["1. Search for restaurant, cui (box)", "2. Home /", "3. Dining Out", "4. Bottom link",
                                  "5. location-fill"])

    def test_labels_lose_icon_words(self):
        self.assertEqual(herbrowser._label("illustration Dining Out"), "Dining Out")
        self.assertEqual(herbrowser._label("filter Filters"), "Filters")
        self.assertEqual(herbrowser._label("Cuisines chevron-down"), "Cuisines")
        self.assertEqual(herbrowser._label("App Download Logo"), "App Download")
        self.assertEqual(herbrowser._label("location-fill"), "")
        self.assertEqual(herbrowser._label("Add to cart"), "Add to cart")
