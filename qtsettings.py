"""Her Qt window's long pages (qtwindow, 22 November 2026): Settings, the Island and Keys, and the pickers Settings
opens for the answer model, her voice and how she hears you; as assistant_ui's, the same rows, words, settings and
steps, drawn by Qt with qtpages' parts.

Her island, dock and edges are Tk's, on their own thread (qtwindow.TkSide): what these pages change in them goes there
(Window.tk.call)."""
import re
import sys
import threading
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QSlider,
                               QVBoxLayout, QWidget)

import assistant_ui as ui
import identity
import qtkit as kit
import settings
from qtkit import ERROR, LINE, MUTED, qc
from qtpages import STYLE, Check, Combo, Page, Table, button, entry, label

SUB_W = 330  # a row's words under its name wrap at this, leaving the right for what it sets
SLIDER = f"""
    QSlider::groove:horizontal {{ height: 4px; background: {LINE}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {ui.ACCENT}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: #ffffff; border: 1px solid #d1d5db; width: 16px; height: 16px;
                                  margin: -7px 0; border-radius: 8px; }}
    QSlider::handle:horizontal:hover {{ border-color: {ui.ACCENT}; }}"""


class Row(QWidget):
    """A row of a long page: its name and what it does in grey under it at the left, what sets it at the right, a
    hairline over it but at the top of its card. more: a line under it all, across."""

    def __init__(self, title, sub, control=None, first=False, link=None):
        super().__init__()
        self.first = first
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 14, 0, 0)
        col.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(16)
        left = QWidget()
        left.setMaximumWidth(SUB_W)
        left.setMinimumWidth(220)
        words = QVBoxLayout(left)
        words.setContentsMargins(0, 0, 0, 0)
        words.setSpacing(2)
        self.title = label(title, kit.font(15, "semibold"))
        self.sub = label(sub, kit.font(12.5), MUTED, wrap=True)
        if link:  # where to get what the row asks for, a link by its name
            named = QHBoxLayout()
            named.setSpacing(8)
            named.addWidget(self.title)
            more = QLabel(f'<a href="{link}" style="color:{ui.ACCENT}; text-decoration:none">Get a key</a>')
            more.setFont(kit.font(13))
            more.setOpenExternalLinks(True)
            named.addWidget(more)
            named.addStretch(1)
            words.addLayout(named)
        else:
            words.addWidget(self.title)
        words.addWidget(self.sub)
        words.addStretch(1)
        row.addWidget(left, 1)
        row.addStretch(0)
        if control is not None:
            row.addWidget(control, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        col.addLayout(row)
        self.col = col

    def more(self, widget):
        self.col.addWidget(widget)

    def paintEvent(self, _):
        if not self.first:
            from PySide6.QtGui import QPainter
            p = QPainter(self)
            p.fillRect(0, 0, self.width(), 1, qc(LINE))


def stack(*widgets, align=Qt.AlignmentFlag.AlignRight, horizontal=True, spacing=8):
    """Widgets side by side (or one over another), for a row's right."""
    holder = QWidget()
    lay = QHBoxLayout(holder) if horizontal else QVBoxLayout(holder)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    if horizontal:
        lay.addStretch(1)
    for w in widgets:
        if isinstance(w, QWidget):
            lay.addWidget(w, 0, align if not horizontal else Qt.AlignmentFlag.AlignVCenter)
        else:
            lay.addLayout(w)
    return holder


class Rows:
    """A long page's rows by number, each to its part, laid out in number order once they're all made (finish)."""

    def __init__(self, page, parts):
        self.page, self.where, self.rows, self.cards = page, {}, {}, {}
        for name, icon, numbers in parts:
            card = page.part(name, icon)
            self.cards[name] = card
            self.where.update((n, card) for n in numbers)

    def add(self, n, title, sub, control=None, part=None):
        row = Row(title, sub, control)
        self.rows[n] = (part or self.where[n], row)
        return row

    def finish(self):
        firsts = set()
        for n in sorted(self.rows):
            card, row = self.rows[n]
            row.first = card not in firsts and not getattr(card, "has_top", False)
            firsts.add(card)
            card.add(row)


# ------------------------------------------------------------------ pickers
class Picker(QDialog):
    """A picker as the Tk window's ModelPicker and ListPicker: a search box over who makes them down the side and all
    of them in one list, narrowed as you type; a key box for the one picked down the side that needs a key; Enter or
    a double click uses the one picked."""

    def __init__(self, page, title, columns, use_text):
        super().__init__(page)
        self.page = page
        self.setWindowTitle(title)
        self.setStyleSheet(STYLE + " QDialog { background: #ffffff; } QListWidget { background: #fafafa; border: 1px "
                           f"solid {LINE}; border-radius: 10px; padding: 4px; outline: none; }} QListWidget::item "
                           "{ padding: 6px 8px; border-radius: 7px; } QListWidget::item:selected { background: "
                           f"{ui.ACCENT}; color: #ffffff; }}")
        self.resize(880, 560)
        self.setMinimumSize(660, 420)
        col = QVBoxLayout(self)
        col.setContentsMargins(16, 14, 16, 14)
        col.setSpacing(10)
        top = QHBoxLayout()
        top.addWidget(label("Search", kit.font(15, "semibold")))
        self.search = entry("")
        self.search.textChanged.connect(lambda _: self.typing.start())
        self.search.installEventFilter(self)
        top.addWidget(self.search, 1)
        col.addLayout(top)
        self.typing = QTimer(self, singleShot=True, interval=120, timeout=self.fill)
        mid = QHBoxLayout()
        mid.setSpacing(10)
        self.side = QListWidget()
        self.side.setFont(kit.font(14))
        self.side.setFixedWidth(220)
        self.side.currentRowChanged.connect(lambda _: self.side_picked())
        mid.addWidget(self.side)
        right = QVBoxLayout()
        self.table = Table(columns, editable=False)
        self.table.doubleClicked.connect(lambda _: self.use())
        self.table.itemSelectionChanged.connect(self.picked_changed)
        right.addWidget(self.table, 1)
        self.key_row = QWidget()
        kr = QHBoxLayout(self.key_row)
        kr.setContentsMargins(0, 4, 0, 0)
        self.key_title = label("", kit.font(14, "semibold"))
        self.key_box = entry("")
        self.key_box.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_box.returnPressed.connect(self.save_key)
        self.key_link = QLabel()
        self.key_link.setFont(kit.font(13))
        self.key_link.setOpenExternalLinks(True)
        kr.addWidget(self.key_title)
        kr.addWidget(self.key_box, 1)
        kr.addWidget(button("Save key", self.save_key))
        kr.addWidget(self.key_link)
        right.addWidget(self.key_row)
        mid.addLayout(right, 1)
        col.addLayout(mid, 1)
        self.foot = QHBoxLayout()
        self.status = label("", kit.font(12.5), MUTED, wrap=True)
        self.foot.addWidget(self.status, 1)
        self.use_button = button(use_text, self.use, accent=True)
        col.addLayout(self.foot)
        self.rows, self.only = [], None

    def finish_foot(self, *more):
        for w in more:
            self.foot.addWidget(w)
        self.foot.addWidget(button("Cancel", self.close))
        self.foot.addWidget(self.use_button)

    def eventFilter(self, obj, event):
        if obj is self.search and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.table.selected()
                row = 0 if row is None else row + (1 if event.key() == Qt.Key.Key_Down else -1)
                if self.table.rowCount():
                    self.table.selectRow(max(0, min(self.table.rowCount() - 1, row)))
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.use()
                return True
        return super().eventFilter(obj, event)

    def say(self, text, error=False):
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {ERROR if error else MUTED}; background: transparent;")

    def show_key(self, name, saved, url, needed):
        self.key_row.setVisible(needed)
        if not needed:
            return
        self.key_title.setText(f"{name} key")
        self.key_box.clear()
        self.key_box.setPlaceholderText("Saved, paste a new one to change it" if saved else "Paste it here")
        self.key_link.setText(f'<a href="{url}" style="color:{ui.ACCENT}; text-decoration:none">Get a key</a>')

    def fill_table(self, rows, pick):
        """rows: (words, grey, bold) each; pick: the row to have picked."""
        self.table.fill([r[0] for r in rows], {i for i, r in enumerate(rows) if r[1]})
        for i, r in enumerate(rows):
            if r[2]:
                for c in range(self.table.columnCount()):
                    item = self.table.item(i, c)
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
        if rows:
            self.table.selectRow(pick if pick is not None else 0)
            self.table.scrollToItem(self.table.item(pick or 0, 0))

    def picked_changed(self):
        pass

    def closeEvent(self, e):
        self.page.picker_closed(self)
        super().closeEvent(e)

    def close(self):
        self.page.picker_closed(self)
        super().close()


class ModelPick(Picker):
    """Settings > Answer model's picker: every provider's models in one list, newest first, the providers with a key
    first; the providers down the side, with a key box for the one picked there (assistant_ui.ModelPicker)."""

    def __init__(self, page):
        super().__init__(page, "Pick a model", (("model", "Model", 330), ("provider", "Provider", 140),
                                                ("price", "Price", 80), ("ctx", "Context", 70)), "Use model")
        self.order = list(ui.providers.PROVIDERS)
        self.finish_foot(button("Refresh", self.refresh))
        self.reload()
        self.search.setFocus()

    def reload(self):
        providers = ui.providers
        counts = {p.id: len(providers.cached(p)["models"]) for p in self.order}
        names = [f"All providers  ({sum(counts.values())})"] + [
            p.name + (f"  ({counts[p.id]})" if counts[p.id] else "") + ("" if providers.ready(p) else ui.SEP + "add key")
            for p in self.order]
        self.side.blockSignals(True)
        self.side.clear()
        self.side.addItems(names)
        self.side.setCurrentRow(0 if self.only is None else self.order.index(self.only) + 1)
        self.side.blockSignals(False)
        self._key()
        self.fill()

    def side_picked(self):
        at = self.side.currentRow()
        if at < 0:
            return
        self.only = None if at == 0 else self.order[at - 1]
        self._key()
        self.fill()
        if self.only is not None and ui.providers.stale(self.only):
            self.refresh()

    def _key(self):
        p = self.only
        self.show_key(getattr(p, "name", ""), p is not None and bool(ui.providers.key(p)), getattr(p, "key_url", ""),
                      p is not None and not p.local)

    def fill(self):
        providers = ui.providers
        words = self.search.text().lower().split()
        current = settings.get("llm_model")
        kept = self.selected()
        kept = providers.full(*kept) if kept else current
        rows, self.rows, pick = [], [], None
        shown = [self.only] if self.only else sorted(self.order, key=lambda p: not providers.ready(p))
        for p in shown:
            ready = providers.ready(p)
            for m in providers.cached(p)["models"]:
                price = "this PC" if p.local else "free" if m["free"] else "paid"
                if words and not all(w in f"{m['id']} {p.name} {price}".lower() for w in words):
                    continue
                full = providers.full(p, m["id"])
                ctx = f"{round(m['ctx'] / 1000)}k" if m["ctx"] >= 1000 else ""
                rows.append(((m["id"], p.name, price if ready else "add key", ctx), not ready, full == current))
                self.rows.append((p, m["id"]))
                if full == kept or pick is None and full == current:
                    pick = len(rows) - 1
        self.fill_table(rows, pick)
        p = self.only
        entry_ = providers.cached(p) if p else None
        if p and entry_["error"]:
            self.say(entry_["error"] + ".", True)
            return
        when = ""
        if p and entry_["at"]:
            ago = int((time.time() - entry_["at"]) // 60)
            when = f" Updated {'just now' if ago < 1 else f'{ago} min ago'}."
        self.say(f"{len(rows)} models{f' on {p.name}' if p else ''}, newest first. Lists refresh by themselves every "
                 f"half hour.{when}")

    def selected(self):
        row = self.table.selected()
        return self.rows[row] if row is not None and row < len(self.rows) else None

    def use(self):
        picked = self.selected()
        if not picked:
            return
        p, model_id = picked
        if not ui.providers.ready(p):
            self.only = p
            self.reload()
            self.key_box.setFocus()
            self.say(f"Add your {p.name} key first, then pick the model again.", True)
            return
        self.page.set_model(ui.providers.full(p, model_id))
        self.close()

    def save_key(self):
        p, value = self.only, self.key_box.text().strip()
        if p is None or not value:
            return
        error = self.page.save_model_key(p, value)
        if error:
            self.say(error, True)
            return
        self._key()
        self.say(f"Saved your {p.name} key. Getting its models\u2026")

    def refresh(self):
        self.say("Getting the lists\u2026")
        self.page.refresh_models(force=True, provider=self.only)


class ListPick(Picker):
    """Settings > Voice's and Speech to text's pickers, laid out as the answer model's (assistant_ui.ListPicker):
    source (VoiceSource or EarsSource, the Tk window's own, for what's in it) says what's listed."""

    def __init__(self, page, source):
        super().__init__(page, source.title, source.columns, source.use_text)
        self.source = source
        self.model_row = QWidget()
        mr = QHBoxLayout(self.model_row)
        mr.setContentsMargins(0, 0, 0, 0)
        mr.addWidget(label("Model", kit.font(14, "semibold")))
        self.model_menu = Combo()
        self.model_menu.setMinimumWidth(320)
        self.model_menu.currentIndexChanged.connect(lambda _: self.fill())
        mr.addWidget(self.model_menu)
        mr.addStretch(1)
        self.layout().insertWidget(2, self.model_row)
        self.model_ids = []
        more = []
        if isinstance(source, ui.VoiceSource):
            more.append(button("Try it", lambda: page.try_voice(self.chosen())))
        else:
            use = Combo(list(ui.EARS_USES.values()))
            use.setCurrentText(ui.EARS_USES.get(settings.get("ears_use"), ui.EARS_USES["all"]))
            use.currentIndexChanged.connect(lambda i: settings.put("ears_use", list(ui.EARS_USES)[i]))
            more += [use, button("Test", lambda: page.test_ears(self.chosen()))]
        self.finish_foot(*more)
        self.set_models(source.model_of(source.current()))
        self.reload()
        self.search.setFocus()

    def set_models(self, want=None):
        g = next((g for g in self.source.groups if self.source.models(g)), None)
        models = self.source.models(g) if g else []
        keep = want or self.model()
        self.model_ids = [m for m, _ in models]
        self.model_menu.blockSignals(True)
        self.model_menu.clear()
        self.model_menu.addItems([name for _, name in models])
        if models:
            self.model_menu.setCurrentIndex(self.model_ids.index(keep) if keep in self.model_ids else 0)
        self.model_menu.blockSignals(False)

    def model(self):
        at = self.model_menu.currentIndex()
        return self.model_ids[at] if 0 <= at < len(self.model_ids) else None

    @staticmethod
    def ready(g):
        return g.local or bool(ui.get_secret(g.key))

    def reload(self):
        counts = {g.id: len(self.source.rows(g)) for g in self.source.groups}
        names = [f"All  ({sum(counts.values())})"] + [
            g.name + (f"  ({counts[g.id]})" if counts[g.id] else "") + ("" if self.ready(g) else ui.SEP + "add key")
            for g in self.source.groups]
        self.side.blockSignals(True)
        self.side.clear()
        self.side.addItems(names)
        self.side.setCurrentRow(0 if self.only is None else self.source.groups.index(self.only) + 1)
        self.side.blockSignals(False)
        self.set_models()
        self._key()
        self.fill()

    def side_picked(self):
        at = self.side.currentRow()
        if at < 0:
            return
        self.only = None if at == 0 else self.source.groups[at - 1]
        self._key()
        self.fill()
        if self.only is not None and self.source.stale(self.only):
            self.refresh()

    def _key(self):
        g = self.only
        self.show_key(getattr(g, "name", ""), g is not None and bool(g.key and ui.get_secret(g.key)),
                      getattr(g, "key_url", ""), g is not None and not g.local)

    def fill(self):
        typed = self.search.text()
        words, current, kept = typed.lower().split(), self.source.current(), self.chosen()
        shown = [self.only] if self.only else sorted(self.source.groups, key=lambda g: not self.ready(g))
        found = [(None, row) for row in self.source.typed(typed)]
        for g in shown:
            found += [(g, row) for row in self.source.rows(g, self.model())
                      if not words or all(w in " ".join(row["cols"]).lower() for w in words)]
        rows, self.rows, pick = [], [], None
        for g, row in found:
            ready = g is None or self.ready(g)
            cols = row["cols"] if ready else (*row["cols"][:2], "add key")
            rows.append((cols, not ready, row["value"] == current))
            self.rows.append((g, row["value"]))
            if pick is None and row["value"] in (kept, current):
                pick = len(rows) - 1
        self.fill_table(rows, pick)
        self.picked_changed()
        g = self.only
        error, at = self.source.status(g) if g else ("", 0)
        if error:
            self.say(error + ".", True)
            return
        when = ""
        if at:
            ago = int((time.time() - at) // 60)
            when = f" Updated {'just now' if ago < 1 else f'{ago} min ago'}."
        self.say(f"{len(rows)} {self.source.things}{f' from {g.name}' if g else ''}.{when}")

    def picked_changed(self):
        picked = self.selected()
        self.model_row.setVisible(bool(picked and picked[0] is not None and self.source.models(picked[0])))

    def selected(self):
        row = self.table.selected()
        return self.rows[row] if row is not None and row < len(self.rows) else None

    def chosen(self):
        picked = self.selected()
        return picked[1] if picked else None

    def use(self):
        picked = self.selected()
        if not picked:
            return
        g, value = picked
        if g is not None and not self.ready(g):
            self.only = g
            self.reload()
            self.key_box.setFocus()
            self.say(f"Add your {g.name} key first, then pick it again.", True)
            return
        if self.source.use(value):
            self.close()

    def save_key(self):
        g, value = self.only, self.key_box.text().strip()
        if g is None or not value:
            return
        error = self.page.save_list_key(g, value)
        if error:
            self.say(error, True)
            return
        self._key()
        self.reload()
        self.say(f"Saved your {g.name} key.")

    def refresh(self):
        self.say("Getting the lists\u2026")
        self.page.refresh_lists(self.source, self.only)


class PickButton(QFrame):
    """What a row picks from a picker, shown on a soft grey box with its chevron; a click opens the picker."""

    def __init__(self, command, width=300):
        super().__init__()
        self.button = button("", command)
        self.button.setStyleSheet("text-align: left; padding: 7px 12px;")
        self.button.setFixedWidth(width)
        self.info = label("", kit.font(12.5), MUTED, wrap=True)
        self.info.setMaximumWidth(width + 30)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self.button, 0, Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self.info)

    def set(self, text, info, error=False):
        self.button.setText(text + "  \u25be")
        self.info.setText(info)
        self.info.setStyleSheet(f"color: {ERROR if error else MUTED}; background: transparent;")


# ------------------------------------------------------------------ Settings
class SettingsPage(Page):
    """Settings (assistant_ui._build_settings): Safety, Her, Hearing you, Seeing, Models, Speaking up, Phone and the
    Window, each a part with its name along the top."""
    PARTS = (("Safety", "\uea18", ()), ("Her", "\uf4a5", (7, 8, 14, 26)),
             ("Hearing you", "\ue720", (0, 2, 3, 10, 11, 15, 18)), ("Seeing", "\ue890", (9, 20, 23, 24)),
             ("Models", "\ue99a", (1,)), ("Speaking up", "\uea8f", (12, 13, 25)), ("Phone", "\ue8ea", (16,)),
             ("Window", "\ue737", (4, 5, 6)))

    def __init__(self, window):
        super().__init__(window, "Settings", "The microphone Harry listens with, the models she uses, and the window.",
                         scroll=True)
        self.picker, self.mic_names, self.models_loaded = None, [], False
        rows = self.rows_ = Rows(self, self.PARTS)
        # Safety, at the top: Full access, off unless turned on here
        self.full_for = Combo(["Until I turn it off", "For an hour"])
        self.full_check = Check("Full access", settings.get("full_access"), self.full_changed_here)
        safety = Row("Full access", "She does what you clearly ask by name without asking first: sends the message, "
                     "installs the app. She still never types passwords or card numbers, never pays or buys, never "
                     "deletes for good, and never acts on words she wasn't sure were for her.",
                     stack(self.full_for, self.full_check), first=True)
        rows.cards["Safety"].add(safety)
        # her name, at the top of Her
        self.nick_box = entry(identity.DEFAULT, 160)
        self.nick_box.setText(identity.name())
        self.nick_box.returnPressed.connect(lambda: self.nickname_changed(self.nick_box.text()))
        her = Row("Her name", "She answers to it and calls herself by it: \u201cHey Harry\u201d. Give her one of your "
                  "own here, or say \u201ccall yourself Friday\u201d. Jarvis works too.",
                  stack(self.nick_box, button("Save", lambda: self.nickname_changed(self.nick_box.text()))),
                  first=True)
        rows.cards["Her"].add(her)
        rows.cards["Her"].has_top = True
        self.mic_menu = Combo()
        self.mic_menu.setMinimumWidth(320)
        self.mic_menu.activated.connect(lambda _: self.mic_changed())
        self.mic_row = rows.add(0, "Microphone", ui.MIC_SUB, self.mic_menu)
        self.model_pick = PickButton(self.open_model_picker)
        rows.add(1, "Answer model", "The model that works out what you asked and answers, from any provider: OpenCode "
                 "Zen, Kilo, OpenRouter, Anthropic, OpenAI, Gemini and more. Click it for every model, newest first, "
                 "with a search box. The lists refresh by themselves every half hour. Free ones say so, the rest are "
                 "billed to your account with that provider.", self.model_pick)
        self.ears_pick = PickButton(lambda: self.open_list_picker(ui.EarsSource(self)))
        rows.add(2, "Speech to text", "Turns what you say into text, on this PC unless you pick a provider: click it "
                 "for Sarvam (best for Indian accents and Hinglish), ElevenLabs, AssemblyAI or Deepgram. The PC still "
                 "hears everything first; only what's said to her goes to them.", self.ears_pick)
        rows.add(3, "Hear me over videos", "Windows takes what the PC is playing out of the mic, so she hears you over "
                 "YouTube and music. Turn it off if she stops hearing you.",
                 Check("Echo cancelling", settings.get("echo_cancel"), self.echo_changed))
        self.on_top_check = Check("Keep window on top", window.on_top, lambda v: window.toggle_on_top(v))
        rows.add(4, "Keep on top", "Keeps this window above other apps. Ctrl+T switches it too.", self.on_top_check)
        rows.add(5, "Popup", "Her island at the top of the screen: her eyes, your words under it as you talk, and what "
                 "she's doing and saying. Its look and plugins are in the Island tab. Off, it shows only for dictation "
                 "and learning your voice.", Check("Show the popup", window.popup, self.popup_changed))
        self.startup_check = Check("Start when I sign in", ui.win.starts_with_windows(), self.startup_changed)
        rows.add(6, "Start with Windows", "Opens Hey Harry, minimised, when you sign in.", self.startup_check)
        name_box = entry("Your name", 160)
        name_box.setText(settings.get("name") or "")
        name_box.editingFinished.connect(lambda: self.name_changed(name_box.text()))
        rows.add(7, "Welcome", "When you sign in or come back to the laptop she says hello, by this name, and asks "
                 "what she can do. Just answer, no \u201cHey Harry\u201d needed.",
                 stack(name_box, Check("Say hello", settings.get("welcome"), lambda v: settings.put("welcome", v))))
        self.voice_pick = PickButton(lambda: self.open_list_picker(ui.VoiceSource(self)), 240)
        say_box = entry("Saoirse = Seersha; Siobhan = Shivawn", 300)
        say_box.setText("; ".join(f"{k} = {v}" for k, v in (settings.get("voice_say_as") or {}).items()))
        say_box.editingFinished.connect(lambda: self.say_as_changed(say_box.text()))
        voice = QWidget()
        vl = QVBoxLayout(voice)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(4)
        top = QHBoxLayout()
        top.addStretch(1)
        top.addWidget(self.voice_pick)
        top.addWidget(button("Try it", lambda: self.try_voice(None)), 0, Qt.AlignmentFlag.AlignTop)
        vl.addLayout(top)
        vl.addWidget(label("Say names as, for her voice on this PC (Saoirse = Seersha; ...)", kit.font(12.5), MUTED))
        vl.addWidget(say_box, 0, Qt.AlignmentFlag.AlignRight)
        rows.add(8, "Voice", "Her voice: Fish Audio\u2019s free model till 30 November, made on this PC, Windows\u2019 "
                 "own, or ElevenLabs, Sarvam or Deepgram with your key. Click it for every voice, with a search box; "
                 "paste a fish.audio link there for any Fish voice. Try it plays a line.", voice)
        eyes = stack(*[Check(text, settings.get(key), lambda v, k=key: settings.put(k, v)) for key, text in (
            ("vision", "Let her see the screen"), ("screen_watch", "Watch it all the time"),
            ("screen_commentary", "Speak up about it"))], horizontal=False, spacing=2)
        rows.add(9, "Vision", "When you ask about the screen, or for something she has to see like \u201cclick the "
                 "second video\u201d, she looks at a screenshot of it and acts on it. Watching, she also reads the "
                 "window in front on this PC all the time, so your questions come with what\u2019s on it, and speaking "
                 "up, she glances at it now and then and tells you when something there needs you. Never password or "
                 "payment pages, or private windows.", eyes)
        for n, (key, title, sub, text) in enumerate((
                ("no_name", "Without her name", "No \u201cHey Harry\u201d needed: she listens all the time, and the "
                 "answer model works out whether you were talking to her or to someone else. What\u2019s said that "
                 "could be a request goes to it as text.", "Answer without her name"),
                ("call_aware", "During calls", "When WhatsApp, Teams, Zoom, Discord or a browser call has the mic, "
                 "unnamed speech is for the call. Say Harry or Jarvis to talk to her.", "Require her name on calls"),
                ("heads_ups", "Heads-ups", "She speaks up when something needs you: the battery at 20 and 10 percent, "
                 "the C drive nearly full, the PC flat out for a while, the internet going, a new message. Quiet from "
                 "11 at night to 7 in the morning, except a nearly flat battery.", "Tell me"),
                ("notifications", "Notifications", "She reads the Windows notification list on this PC, for \u201cany "
                 "new messages?\u201d, welcome back and heads-ups. Phone Link brings in your phone\u2019s WhatsApp and "
                 "texts.", "Read my notifications"),
                ("learning", "Learning", "After a correction, or a task that took a few steps, she looks back over it "
                 "and keeps what she learned: a fact, a routine, a word she misheard. It all shows in the Memory tab.",
                 "Learn as she goes")), start=10):
            rows.add(n, title, sub, Check(text, settings.get(key), lambda v, k=key: settings.put(k, v)))
        self.voice_id_check = Check("Only answer my voice", settings.get("voice_id") != "off", self.voice_id_changed)
        rows.add(15, "Your voice", "She answers only you, not other people, the TV or a video. Press Learn, or say "
                 "\u201cHey Harry, learn my voice\u201d, and read her 20 short sentences. She learns your voice for a "
                 "few days first. The recordings stay on this PC.",
                 stack(self.voice_id_check, button("Learn", self.learn_voice)))
        self.pair_code = entry("Code from the bot", 160)
        self.pair_code.returnPressed.connect(self.pair_phone)
        phone = rows.add(16, "Phone", "Talk to her from your phone on Telegram. Save your bot's token in Keys, send "
                         "/start to your bot, then type the 8-letter code it replies with here and press Pair. No code? "
                         "Press Pair with the box empty first. Only your account can use it, and anything risky waits "
                         "for your Yes.", stack(self.pair_code, button("Pair", self.pair_phone),
                                                button("Unpair", self.unpair_phone)))
        self.phone_state = label("", kit.font(12.5), MUTED, wrap=True)
        phone.more(self.phone_state)
        self.phone_status()
        self.wait_menu = Combo(list(ui.WAITS.values()))
        self.wait_menu.setCurrentText(ui.WAITS.get(settings.get("turn_wait"), ui.WAITS["patient"]))
        self.wait_menu.activated.connect(lambda i: self.wait_changed(i))
        rows.add(18, "Wait before answering", "How long she waits once you stop talking. Patient lets you pause in "
                 "the middle of a sentence; Quick answers soonest but can cut you off. Takes effect when Hey Harry "
                 "next starts.", self.wait_menu)
        rows.add(20, "Let her see you", "Through the laptop's camera she welcomes you as you come back to it, and does "
                 "what you've told her when she sees or hears it: two claps, work mode; a snap while music plays, dream "
                 "mode; your glasses on, light mode. Teach her more by saying so: \u201cwhen I clap, open Spotify\u201d. "
                 "While this is on she watches all the time (the camera's light stays on), and whether you're there is "
                 "worked out on this PC; for a look rule, one small picture goes to the vision model when you look "
                 "different, and every couple of minutes. Claps are heard on this PC, in the mic's own sound.",
                 Check("Let her see you", settings.get("cues"), lambda v: settings.put("cues", v)))
        rows.add(23, "Her own browser", "Jobs on websites happen in a Chrome of her own, out of your way, never on "
                 "your screen. Sign her in to the sites she should use: press Show it (or say \u201csign in to LinkedIn "
                 "in your browser\u201d), sign in, then say \u201chide your browser\u201d. Her sign-ins stay in it; she "
                 "never types a password. Off, as it is now, her jobs on websites run in the background in your own "
                 "browser, which is signed in already; Google won't sign in to hers.",
                 stack(button("Show it", self.show_her_browser),
                       Check("Her own browser", settings.get("own_browser"), lambda v: settings.put("own_browser", v))))
        profiles = Combo([""] + list(self._chrome_profiles()))
        profiles.setCurrentText(str(settings.get("job_profile") or ""))
        profiles.activated.connect(lambda _: settings.put("job_profile", profiles.currentText()))
        profiles.setMinimumWidth(220)
        rows.add(24, "A window of her own", "Her jobs on websites open sites in this profile of your Chrome, so they "
                 "get a window of their own and yours is left alone. Make a profile called Harry in Chrome (your "
                 "picture at the top right, Add), sign in there to the sites she should use, and pick it here. Google "
                 "signs in there, as it's your ordinary Chrome. She still borrows your keyboard to type, after a pause "
                 "in yours.", profiles)
        chatty = Combo(list(ui.CHATTY.values()))
        chatty.setCurrentText(ui.CHATTY.get(settings.get("chattiness"), ui.CHATTY["chatty"]))
        chatty.activated.connect(lambda i: settings.put("chattiness", list(ui.CHATTY)[i]))
        rows.add(25, "How chatty", "Like a close friend, she checks in while you're at the PC: how your plans went, a "
                 "break, a bit of fun. Never in a call, at night or while you're away. Only when it matters, she just "
                 "asks after what you told her you'd do. Or say \u201ctalk less\u201d or \u201ccheck in on me "
                 "more\u201d.", chatty)
        self.speaks_check = Check("Say them out loud", settings.get("chat_speaks"),
                                  lambda v: window.chat.box.speak(v))
        rows.add(26, "Speak chat answers", "What you type in the chat is answered in words only, so she never talks "
                 "over you while you type. On, she says it out loud as well, as she does when you talk to her. The "
                 "speaker in the chat's box switches it too.", self.speaks_check)
        rows.finish()
        self.jumps()
        self.note = label("", kit.font(12.5), MUTED, wrap=True)
        self.body.addWidget(self.note)
        self.finish()
        self.show_models()
        self.show_ears()
        self.show_voice()
        self.auto = QTimer(self, interval=ui.providers.FRESH_FOR * 1000, timeout=self.refresh_models)

    # what she says under it all
    def say(self, text, error=False, note=None):
        super().say(identity.named(text), error, note)

    def shown(self):
        self.load_mics()
        if not self.models_loaded:
            self.models_loaded = True
            self.refresh_models()
            self.auto.start()

    def on_event(self, event):
        kind = event[0]
        if kind == "models":
            self.show_models()
        elif kind == "lists":
            if isinstance(self.picker, ListPick):
                self.picker.reload()
            self.show_voice()
            self.show_ears()
        elif kind == "tell":
            self.tell(event[1], event[2])
        elif kind == "model_check":
            self.model_pick.set(self.model_pick.button.text().rstrip(" \u25be"), event[1], event[2])

    # Full access
    def full_changed_here(self, on):
        if not self.window.set_full_access(on, 1 if self.full_for.currentIndex() == 1 else 0):
            self.full_check.blockSignals(True)
            self.full_check.setChecked(not on)
            self.full_check.blockSignals(False)
            return
        self.say("Full access is on: she sends and installs what you ask without asking first." if on else
                 "Full access is off: she asks before sending or installing.")

    def full_changed(self, on):
        if self.full_check.isChecked() != on:
            self.full_check.blockSignals(True)
            self.full_check.setChecked(on)
            self.full_check.blockSignals(False)

    def speaks_changed(self, on):
        if self.speaks_check.isChecked() != on:
            self.speaks_check.blockSignals(True)
            self.speaks_check.setChecked(on)
            self.speaks_check.blockSignals(False)

    # the microphone
    def load_mics(self):
        names = ui.win.input_devices()
        _, auto = ui.win.auto_input()
        self.mic_names = names
        self.mic_menu.blockSignals(True)
        self.mic_menu.clear()
        self.mic_menu.addItems([f"Automatic ({auto})"] + [n + ("  (PC sound only)" if "stereo mix" in n.lower()
                                                              else "") for n in names])
        mic = self.window.mic
        if mic in names:
            self.mic_menu.setCurrentIndex(names.index(mic) + 1)
            self._mic_note()
        else:
            self.mic_menu.setCurrentIndex(0)
            self.mic_row.sub.setText(identity.named(ui.MIC_SUB))
            self.mic_row.sub.setStyleSheet(f"color: {MUTED}; background: transparent;")
            gone = f"{mic} isn\u2019t plugged in, so " if mic else ""
            self.say(f"{gone}Microphone: {auto}. Automatic skips Stereo Mix, which only hears what the PC plays.")
        self.mic_menu.blockSignals(False)

    def mic_changed(self):
        i = self.mic_menu.currentIndex()
        self.window.mic = "" if i <= 0 else self.mic_names[i - 1]
        settings.put("mic", self.window.mic)
        self.window.controls.put(("mic", self.window.mic))
        self.load_mics()

    def _mic_note(self):
        mic = self.window.mic
        self.say(f"Microphone: {mic}")
        stereo = "stereo mix" in mic.lower()
        self.mic_row.sub.setText("Stereo Mix only hears what the PC plays, so she can\u2019t hear you. Pick Automatic "
                                 "or your microphone to talk to her." if stereo else identity.named(ui.MIC_SUB))
        self.mic_row.sub.setStyleSheet(f"color: {ERROR if stereo else MUTED}; background: transparent;")

    def echo_changed(self, on):
        settings.put("echo_cancel", on)
        self.window.controls.put(("mic", self.window.mic))
        self.say("Echo cancelling on, she hears you over videos and music" if on else
                 "Echo cancelling off. While a video plays, say \u201cHey Harry\u201d close to the mic, or hold right Alt")

    # the phone
    def pair_phone(self):
        typed = self.pair_code.text()
        pasted = re.search(r"code is\s+([A-Za-z0-9]{8})\b", typed, re.I)
        code = pasted[1] if pasted else "".join(typed.split())
        if not ui.get_secret("TELEGRAM_BOT_TOKEN"):
            self.phone_status("Add your bot's token in Keys first, then press Pair here.", error=True)
        elif not code and settings.get("telegram_owner"):
            self.phone_status(f"Already paired with {settings.get('telegram_owner_name') or 'your account'}. To pair "
                              "another Telegram account, press Unpair first.")
        elif not code:
            self.window.controls.put("pair phone")
            self.phone_status("Pairing is open for 10 minutes: send /start to your bot on Telegram, then type the "
                              "8-letter code it replies with in the box and press Pair.")
        elif re.fullmatch(r"[A-Za-z0-9]{8}", code):
            self.window.controls.put(("pair code", code))
            self.pair_code.clear()
            self.phone_status("Checking the code\u2026")
        else:
            self.pair_code.clear()
            self.phone_status("That isn't a pairing code: it's 8 letters and numbers, from your bot after /start. To "
                              "get one, leave the box empty and press Pair.", error=True)

    def unpair_phone(self):
        self.window.controls.put("unpair phone")
        self.phone_status("Unpairing\u2026")

    def phone_status(self, news=None, error=False):
        if news is None:
            if settings.get("telegram_owner"):
                news = f"Paired with {settings.get('telegram_owner_name') or 'your Telegram account'}. Message your " \
                       "bot to talk to her."
            elif not ui.get_secret("TELEGRAM_BOT_TOKEN"):
                news = "Not set up: add your bot's token in Keys."
            else:
                news = "Not paired yet: send /start to your bot, or press Pair with the box empty."
        if news.startswith(ui.PHONE_BAD):
            error = True
        colour = ERROR if error else ui.TEAL if news.startswith("Paired") else MUTED
        self.phone_state.setText(news)
        self.phone_state.setStyleSheet(f"color: {colour}; background: transparent;")

    # your voice
    def learn_voice(self):
        self.window.controls.put("learn voice")
        self.say("Read her each sentence in the popup, one at a time. Say \u201cstop\u201d to stop.")

    def voice_id_changed(self, on):
        import voiceid
        if not on:
            settings.put("voice_id", "off")
            self.say("She answers everyone again.")
            return
        profile = voiceid.Profile()
        if not profile.ready:
            self.voice_id_check.blockSignals(True)
            self.voice_id_check.setChecked(False)
            self.voice_id_check.blockSignals(False)
            self.learn_voice()
            return
        settings.put("voice_id", "on" if profile.calibrated else "learning")
        self.window.controls.put("voice on")
        self.say("She answers only you." if profile.calibrated else
                 "She's learning your voice for a few days, then she'll answer only you.")

    # her voice
    def show_voice(self):
        voice = ui.saved_voice()
        name = ui.AssistantWindow._voice_label(voice)
        parsed = ui.voices.parse(voice)
        if parsed and not ui.voices.ready(parsed[0]):
            info, bad = f"Add your {parsed[0].name} key: click the voice.", True
        elif parsed:
            info, bad = f"{parsed[0].name}, with your key. Each line is kept once said, and her voice on this PC fills " \
                        f"in if it fails.", False
        elif str(voice).startswith("voca:"):
            import voca
            info, bad = f"{voca.CREDIT}. Made on this PC, nothing sent anywhere.", False
        else:
            info, bad = "", False
        self.voice_pick.set(name if len(name) <= 30 else name[:29] + "\u2026", info, bad)

    def say_as_changed(self, text):
        pairs = {}
        for part in str(text).split(";"):
            word, _, sound = part.partition("=")
            if word.strip() and sound.strip():
                pairs[word.strip()] = sound.strip()
        if pairs != (settings.get("voice_say_as") or {}):
            settings.put("voice_say_as", pairs)
            self.say("Saved. Her voice on this PC says those names that way from now on.")

    def set_voice(self, voice):
        if voice == (settings.get("voice") or settings.VOICES[0][1]):
            self.show_voice()
            return
        settings.put("voice", voice)
        self.show_voice()
        paid = ui.voices.parse(voice)
        self.say(f"Voice saved. Each of her lines is made by {paid[0].name} the first time she says it, then kept, so "
                 f"it's only paid for once." if paid else
                 "Voice saved. Her usual replies are made again in it in the background, so for a few minutes some may "
                 "start a moment later.")
        siri = sys.modules.get("siri")
        if siri:
            threading.Thread(target=siri.warm_cache, daemon=True).start()

    def try_voice(self, voice=None):
        voice = voice or ui.saved_voice()
        name = settings.get("name")
        line = f"Hi{' ' + name if name else ''}, this is how I'd sound. Anything you'd like me to do?"
        self.tell("Playing a line\u2026")
        events = self.window.events

        def play():
            try:
                import siri
                ms = siri.speak(line, voice=voice)
                events.put(("tell", f"It started in {ms / 1000:.1f}s." if ms else "", False))
            except Exception as exc:
                events.put(("tell", f"Couldn\u2019t play it: {exc}", True))
        threading.Thread(target=play, daemon=True).start()

    def tell(self, text, error=False):
        if isinstance(self.picker, ListPick):
            self.picker.say(text, error)
        else:
            self.say(text, error)

    # how she hears you
    def show_ears(self):
        hearing = ui.hearing
        value = hearing.picked()
        engine = settings.get("stt_engine") or "parakeet"
        name = hearing.name_of(value) or next((f"{n}, on this PC" for e, n, _ in hearing.LOCAL if e == engine), engine)
        parsed = hearing.parse(value)
        if parsed and not ui.get_secret(parsed[0].key):
            info, bad = f"Add your {parsed[0].name} key: click it. Till then, this PC hears you.", True
        elif parsed:
            use = "dictation" if settings.get("ears_use") == "dictation" else "commands and dictation"
            info, bad = f"{parsed[0].name} hears what's said to her, for {use}. If it takes more than " \
                        f"{hearing.WAIT:.1f}s, this PC's words are used.", False
        else:
            info, bad = "Nothing you say leaves this PC.", False
        self.ears_pick.set(name if len(name) <= 36 else name[:35] + "\u2026", info, bad)

    def set_ears(self, value):
        hearing = ui.hearing
        if value.startswith("pc:"):
            engine, was = value[3:], settings.get("stt_engine") or "parakeet"
            settings.put("ears", "")
            settings.put("stt_engine", engine)
            name = next(n for e, n, _ in hearing.LOCAL if e == engine)
            self.say(f"Saved. Quit Hey Harry and open it again to switch to {name}." if engine != was else
                     f"Saved. Only this PC hears you, with {name}.")
        else:
            settings.put("ears", value)
            self.say(f"Saved. {hearing.name_of(value)} hears what's said to her from now on.")
        self.show_ears()
        return True

    def test_ears(self, value):
        hearing = ui.hearing
        if not value or value.startswith("pc:"):
            self.tell("Pick a provider's to test it. This PC's are the ones she uses now.")
            return
        parsed = hearing.parse(value)
        if not ui.get_secret(parsed[0].key):
            self.tell(f"Add your {parsed[0].name} key first.", True)
            return
        self.tell("Say something now, for four seconds\u2026")
        events = self.window.events

        def run():
            try:
                import sounddevice as sd
                device = ui.win.input_device(settings.get("mic") or "")
                device = device if device is not None else ui.win.auto_input()[0]
                audio = sd.rec(4 * hearing.RATE, samplerate=hearing.RATE, channels=1, dtype="float32", device=device)
                sd.wait()
                events.put(("tell", f"Sending it to {parsed[0].name}\u2026", False))
                got = hearing.transcribe(audio[:, 0], value)
                events.put(("tell", f"{parsed[0].name} heard \u201c{got.text or '(nothing)'}\u201d in "
                                    f"{got.ms / 1000:.2f}s.", False))
            except Exception as exc:
                events.put(("tell", f"Couldn\u2019t test it: {exc}", True))
        threading.Thread(target=run, daemon=True).start()

    # the pickers
    def open_list_picker(self, source):
        if self.picker is not None:
            self.picker.raise_()
            return
        self.picker = ListPick(self, source)
        self.picker.show()
        self.refresh_lists(source)

    def refresh_lists(self, source, group=None):
        events = self.window.events

        def fetch():
            for g in source.groups:
                if (group is not None and g.id == group.id) or (group is None and source.stale(g)):
                    source.refresh(g)
            events.put(("lists",))
        threading.Thread(target=fetch, daemon=True).start()

    def save_list_key(self, g, value):
        try:
            ui.save_secret(g.key, value)
        except Exception as exc:
            return str(exc)
        if g.key == "FISH_AUDIO_API_KEY":
            from siri import reload_keys
            reload_keys()
        getattr(self.window.pages.get("keys"), "key_saved", lambda k: None)(g.key)
        if isinstance(self.picker, ListPick):
            self.refresh_lists(self.picker.source, g)
        self.show_voice()
        self.show_ears()
        return None

    def picker_closed(self, picker):
        if self.picker is picker:
            self.picker = None

    def open_model_picker(self):
        if self.picker is not None:
            self.picker.raise_()
            return
        self.picker = ModelPick(self)
        self.picker.show()
        self.refresh_models()

    def set_model(self, value):
        providers = ui.providers
        p = providers.split(value)[0]
        settings.put("llm_model", value)
        self.show_models()
        cost = "free" if ui.opencode.is_free(value) else f"billed to your {p.name} account"
        self.model_pick.set(self.model_pick.button.text().rstrip(" \u25be"), f"Saved ({cost}). Checking it "
                            "answers\u2026")
        events = self.window.events

        def check():
            ok, result = ui.opencode.check_model(ui.get_secret("OPENCODE_ZEN_API_KEY"), value)
            events.put(("model_check", f"It answered in {result:.1f}s ({cost})." if ok else
                        f"It didn\u2019t answer: {result}", not ok))
        threading.Thread(target=check, daemon=True).start()

    def save_model_key(self, p, value):
        try:
            ui.save_secret(p.key, value)
        except Exception as exc:
            return str(exc)
        if p.key == "OPENCODE_ZEN_API_KEY":
            from siri import reload_keys
            reload_keys()
        getattr(self.window.pages.get("keys"), "key_saved", lambda k: None)(p.key)
        self.refresh_models(force=True, provider=p)
        return None

    def refresh_models(self, force=False, provider=None):
        events = self.window.events

        def fetch():
            if force and provider is not None:
                ui.providers.refresh(provider)
            ui.providers.refresh_all(only_stale=not (force and provider is None))
            events.put(("models",))
        threading.Thread(target=fetch, daemon=True).start()

    def show_models(self):
        providers = ui.providers
        p, current = providers.split(settings.get("llm_model"))
        cached = providers.cached(p)
        model = next((m for m in cached["models"] if m["id"] == current), None)
        bits, bad = [p.name], False
        if not providers.ready(p):
            bits, bad = [f"Add your {p.name} key: click the model."], True
        elif model is None and cached["models"] and not cached["error"]:
            bits, bad = [f"It isn\u2019t on {p.name}\u2019s list any more, click to pick another."], True
        else:
            bits.append("Free" if ui.opencode.is_free(settings.get("llm_model")) else
                        f"Paid, billed to your {p.name} account")
            if model and model["ctx"] >= 1000:
                bits.append(f"{round(model['ctx'] / 1000)}k context")
        self.model_pick.set(current if len(current) <= 36 else current[:35] + "\u2026", ui.SEP.join(bits), bad)
        if isinstance(self.picker, ModelPick):
            self.picker.reload()

    # the rest
    def popup_changed(self, on):
        self.window.popup = on
        settings.put("popup", on)
        tk = self.window.tk
        if tk is not None:
            def go():
                if tk.bubble is not None:
                    if not on:
                        tk.bubble.hide()
                    getattr(tk.bubble, "reload", lambda: None)()
            tk.call(go)

    def startup_changed(self, on):
        try:
            ui.win.set_start_with_windows(on)
            self.say("Hey Harry starts when you sign in" if on else "Hey Harry won't start by itself any more")
        except OSError as exc:
            self.startup_check.blockSignals(True)
            self.startup_check.setChecked(ui.win.starts_with_windows())
            self.startup_check.blockSignals(False)
            self.say(f"Couldn't change that: {exc}", error=True)

    def nickname_changed(self, text):
        try:
            new = identity.rename(" ".join(str(text or "").split()) or identity.DEFAULT)
        except ValueError:
            self.say("That can't be her name: one to three words, letters only, like Friday or Max.", error=True)
            return
        except OSError as exc:
            self.say(f"Couldn't save her name: {exc}", error=True)
            return
        self.say(f"She\u2019s {new} now. Say \u201cHey {new}\u201d.")

    def name_changed(self, name):
        name = " ".join(name.split())
        if name == (settings.get("name") or ""):
            return
        settings.put("name", name)
        self.say(f"She'll call you {name}" if name else "She won't use a name")

    def wait_changed(self, i):
        wait = list(ui.WAITS)[i]
        settings.put("turn_wait", wait)
        self.say(f"Saved. Quit Hey Harry and open it again for {ui.WAITS[wait].split(' (')[0]}.")

    def show_her_browser(self):
        def go():
            try:
                import herbrowser
                herbrowser.show()
            except Exception as exc:
                print(f"  her browser: {exc!r}")
        threading.Thread(target=go, name="show-her-browser", daemon=True).start()

    @staticmethod
    def _chrome_profiles():
        try:
            import siri
            return [siri._shown(name) for _, name, _ in siri.profiles("chrome")]
        except Exception:
            return []


# ------------------------------------------------------------------ the Island
class IslandPage(Page):
    """The Island (assistant_ui._build_island): how it looks, where it sits, how it behaves, its panels, the edges,
    the dock, its plugins and the apps it shows. Changes show on it straight away."""

    def __init__(self, window):
        import island_plugins as plugins
        super().__init__(window, "Island", "Her island at the top of the screen, like Nixi\u2019s: her eyes, your words "
                         "under it as you talk, and while she isn\u2019t busy what\u2019s playing, new notifications, the "
                         "battery and timers. Changes show on it straight away.", scroll=True)
        self.cards = {name: self.part(name, icon) for name, _, icon in ui.ISLAND_PARTS}
        self.count, self.started, self.jobs, self.apps_loaded = 0, set(), {}, False

        def row(title, sub, part=None):
            i = self.count
            self.count += 1
            part = part or ("Look" if i < 6 else "Place" if i < 11 else "Behaviour")
            return part, title, sub

        def put(spec, control):
            part, title, sub = spec
            r = Row(title, sub, control, first=part not in self.started)
            self.started.add(part)
            self.cards[part].add(r)

        def combo(spec, key, choices, change=None):
            box = Combo(list(choices.values()))
            box.setMinimumWidth(240)
            box.setCurrentText(choices.get(settings.get(key), next(iter(choices.values()))))
            done = change or (lambda value: self.changed(key, value))
            box.activated.connect(lambda i: done(list(choices)[i]))
            put(spec, box)

        def check(spec, key, text):
            put(spec, Check(text, settings.get(key), lambda v: self.changed(key, v)))

        def slider(spec, key, lo, hi, unit):
            start = settings.get(key)
            start = int(lo if start is None else start)
            s = QSlider(Qt.Orientation.Horizontal)
            s.setStyleSheet(SLIDER)
            s.setRange(lo, hi)
            s.setValue(start)
            s.setFixedWidth(190)
            shown = label(f"{start}{unit}", kit.font(12.5), MUTED)
            shown.setFixedWidth(52)

            def moved(v):  # saved once it stops moving, so dragging doesn't rebuild it every step
                shown.setText(f"{v}{unit}")
                job = self.jobs.get(key)
                if job is None:
                    job = self.jobs[key] = QTimer(self, singleShot=True, interval=250)
                    job.timeout.connect(lambda: self.changed(key, s.value()))
                job.start()
            s.valueChanged.connect(moved)
            put(spec, stack(s, shown))

        combo(row("Popup", "Her island has her eyes and the plugins below. The card and the pill show only her "
                           "turns."), "popup_style", ui.POPUP_STYLES, self.style_changed)
        combo(row("Style", "The answer card is the glass capsule, but when you talk to her it opens into a box: your "
                           "words, her answer, how long it took and Try again. The black pill sits at the top, as it "
                           "was."), "island_style", ui.ISLAND_STYLES)
        check(row("Drop", "Hangs from the top of the screen like a notch, its corners curving into the edge, with no "
                          "gap above it. Off, it floats a little under the top."), "island_drop", "Hang it from the top")
        combo(row("Face", "Her eyes blink, look about and react: hearts when you say thanks, glasses while she reads "
                          "the screen, headphones while music plays. Or the orb, a ring that ripples with a voice, or "
                          "the Siri wave on the pill."), "island_face", ui.ISLAND_FACES)
        combo(row("Theme", "Paper is white with faint dots, like this window. AMOLED is pure black, like a phone's "
                           "notch. Like Windows follows light and dark mode. Black, Graphite, Ros\u00e9, Lavender, "
                           "Peach and Sakura are NotchPixel's, each with its own colour for what's on."),
              "island_theme", ui.ISLAND_THEMES)
        combo(row("Font", "Her words on the island. Figtree is clear at small sizes; Plus Jakarta Sans and Poppins are "
                          "Glance's; Segoe is Windows' own."), "island_font", ui.ISLAND_FONTS)
        combo(row("Song's line", "How the music card shows how far the song's got, as NotchPixel's choices: a wave "
                                 "that runs while it plays, a plain line, squares, a comet or hearts."), "island_bar",
              ui.ISLAND_BARS)
        combo(row("Music at rest", "What dances beside her eyes while music plays: squares, as NotchPixel's, or "
                                   "bars."), "island_visualizer", ui.ISLAND_VISUALIZERS)
        check(row("Album colours", "The cover's colours behind the music card."), "island_album_bg",
              "Show the cover's colours")
        check(row("Border", "A thin line round it, so it shows on a dark wallpaper."), "island_border", "Show a border")
        combo(row("Where", "Along the top of the screen you're working on."), "island_align", ui.ISLAND_ALIGN)
        slider(row("Across", "Moves it left or right from there."), "island_x", -400, 400, " px")
        slider(row("Down", "How far it sits from the top of the screen, when it doesn't hang from it."), "island_y",
               0, 80, " px")
        slider(row("Size", "Bigger or smaller, eyes, words and all."), "island_scale", 70, 150, "%")
        slider(row("Corners", "How round its corners are."), "island_radius", 6, 40, " px")
        check(row("Always there", "Her eyes stay up while nothing's going on, and look at the mouse when you point at "
                                  "them. Off, it shows only when there's something to show."), "island_always",
              "Keep her eyes up")
        check(row("Full screen", "Out of the way of a full-screen game, video or presentation. Her own turns still "
                                 "show."), "island_hide_fullscreen", "Hide over full-screen apps")
        slider(row("Popups stay", "How long a notification or the battery stays up. Pointing at one keeps it."),
               "island_auto_hide", 2, 15, " s")
        check(row("Light", "Something comes and she lights up in its colour, as Glance's notch does: a line round her "
                           "and light along the top of the screen.", "Look"), "island_light", "Light up")
        combo(row("Beside her eyes", "A little of what's going on, either side of her eyes while nothing else is.",
                  "Panels"), "island_status", ui.ISLAND_STATUS)
        check(row("Do Not Disturb", "No notifications, devices or battery popping up on the island. Your own timers "
                                    "and her turns still show. The moon in Controls does the same.", "Panels"),
              "island_dnd", "Hush the island")
        check(row("Shelf", "Files dropped on her eyes wait on the shelf panel, to drag out where you want them. Off, "
                           "it's empty each time she starts.", "Panels"), "island_shelf_keep",
              "Keep the shelf for next time")
        slider(row("Focus", "A round of the focus timer, when you don't say how long. \u201cStart a pomodoro\u201d.",
                   "Panels"), "focus_minutes", 5, 90, " min")
        slider(row("Break", "The break after each round. Every fourth one is 15 minutes.", "Panels"),
               "break_minutes", 1, 30, " min")
        check(row("Volume", "Rest the pointer against the left edge of the screen: the volume slides out, with the "
                            "apps playing sound beside it.", "Edges"), "edge_volume", "At the left edge")
        check(row("Brightness", "The same at the right edge, for the screen's brightness. Only on a screen Windows can "
                                "dim.", "Edges"), "edge_brightness", "At the right edge")
        check(row("When they change", "The slider shows for a moment when the volume or brightness changes, from the "
                                      "keys or anywhere. Windows' own still shows too.", "Edges"), "level_hud",
              "Show the change")
        check(row("In the notch", "A change shows in her island instead, with her light along her bottom as far as "
                                  "it's set, as Glance's notch does. Off, the slider shows it.", "Edges"), "level_notch",
              "Show it in the notch")
        check(row("Round corners", "The top corners of the screen rounded off, like a MacBook's.", "Edges"),
              "island_corners", "Round the top corners")
        check(row("Dock", "Your pinned and open apps along the bottom of the screen. Click to open or switch, "
                          "right-click to pin.", "Dock"), "dock", "Show the dock")
        combo(row("Look", "A taskbar hanging from the bottom of the screen, with the network, the volume, the time and "
                          "the bell at its right, as NotchPixel's. Or a dock whose icons grow as you point at them, as "
                          "a Mac's.", "Dock"), "dock_style", ui.DOCK_STYLES)
        combo(row("Hiding", "Out of a window's way, or only when the pointer's at the bottom of the screen.", "Dock"),
              "dock_mode", ui.DOCK_MODES)
        check(row("Taskbar", "Hides Windows' taskbar while the dock is on, and brings it back when the dock's off or "
                             "she quits. The tray icons are under the taskbar.", "Dock"), "dock_replace_taskbar",
              "Hide Windows' taskbar")
        found = self.cards["Plugins"]
        found.add(label("What the island shows while she isn't busy. Each one reads only what Windows already keeps "
                        "on this PC, and nothing it reads leaves it.", kit.font(12.5), MUTED, wrap=True))
        for i, cls in enumerate(plugins.PLUGINS):
            on = (settings.get("island_plugins") or {}).get(cls.id)
            boxes = [Check("On", cls.default_on if on is None else bool(on),
                           lambda v, c=cls: self.plugin_changed(c.id, v))]
            opts = plugins.get_options(cls.id)
            for key, text, default in cls.options:
                boxes.append(Check(text, bool(opts.get(key, default)),
                                   lambda v, c=cls, k=key: self.plugin_option(c.id, k, v)))
            found.add(Row(cls.name, cls.description, stack(*boxes, horizontal=False, spacing=2), first=i == 0))
        notes = self.cards["Notifications"]
        notes.add(label("The apps whose notifications pop up on the island. The ones people message you in are on to "
                        "start with. Your phone's come through Phone Link.", kit.font(12.5), MUTED, wrap=True))
        self.apps_box = QWidget()
        self.apps_grid = QGridLayout(self.apps_box)
        self.apps_grid.setContentsMargins(0, 6, 0, 0)
        self.apps_grid.addWidget(label("Looking for them\u2026", kit.font(12.5), MUTED), 0, 0)
        notes.add(self.apps_box)
        self.island_note = label("Shows a notification on the island, the way they come.", kit.font(12.5), MUTED)
        bar = QHBoxLayout()
        bar.addWidget(button("Preview", self.preview))
        bar.addWidget(self.island_note, 1)
        holder = QWidget()
        holder.setLayout(bar)
        notes.add(holder)
        self.jumps()
        self.finish()

    def shown(self):
        self.load_apps()

    def changed(self, key, value):
        if settings.get(key) == value:
            return
        settings.put(key, value)
        tk = self.window.tk
        if tk is None:
            return

        def go():
            getattr(tk.bubble, "reload", lambda: None)()
            if tk.edges is not None:
                tk.edges.reload()
            if key.startswith("dock") or key == "island_theme":
                tk._dock_changed()
        tk.call(go)

    def style_changed(self, style):
        if settings.get("popup_style") == style:
            return
        settings.put("popup_style", style)
        tk = self.window.tk
        if tk is None:
            return
        events = self.window.events

        def done(got):
            events.put(("island_style", style, got))
        tk.restyle(done)

    def on_event(self, event):
        if event[0] == "island_style":
            style, got = event[1], event[2]
            name = ui.POPUP_STYLES[got][0].lower() + ui.POPUP_STYLES[got][1:]
            self.say(f"Switched to {name}" if got == style else f"That one didn't start here, so it's {name}",
                     error=got != style, note=self.island_note)
        elif event[0] == "island_apps":
            self.show_apps(event[1])

    def plugin_changed(self, plugin_id, on):
        chosen = dict(settings.get("island_plugins") or {})
        chosen[plugin_id] = bool(on)
        settings.put("island_plugins", chosen)
        self._reload()

    def plugin_option(self, plugin_id, key, value):
        chosen = {k: dict(v) for k, v in (settings.get("island_plugin_options") or {}).items()}
        chosen.setdefault(plugin_id, {})[key] = bool(value)
        settings.put("island_plugin_options", chosen)
        self._reload()

    def _reload(self):
        tk = self.window.tk
        if tk is not None:
            tk.call(lambda: getattr(tk.bubble, "reload", lambda: None)())

    def app_changed(self, name, on):
        chosen = dict(settings.get("island_apps") or {})
        chosen[name] = bool(on)
        settings.put("island_apps", chosen)

    def preview(self):
        tk = self.window.tk
        if tk is None or not hasattr(tk.bubble, "preview"):
            self.say("The preview is for her island: pick it under Popup above.", error=True, note=self.island_note)
        elif not self.window.popup:
            self.say("Turn on Show the popup in Settings first.", error=True, note=self.island_note)
        else:
            self.say("Shows a notification on the island, the way they come.", note=self.island_note)
            tk.call(lambda: tk.bubble.preview())

    def load_apps(self):
        if self.apps_loaded:
            return
        self.apps_loaded = True
        events = self.window.events

        def read():
            try:
                import island_plugins as plugins
                found = plugins.notification_apps()
            except Exception as exc:
                print(f"  couldn't list the apps that notify: {exc!r}")
                found = []
            events.put(("island_apps", found))
        threading.Thread(target=read, daemon=True).start()

    def show_apps(self, found):
        import island_plugins as plugins
        while self.apps_grid.count():
            w = self.apps_grid.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        if not found:
            self.apps_grid.addWidget(label("No app has sent a notification here lately.", kit.font(12.5), MUTED), 0, 0)
            return
        for i, app in enumerate(found):
            name = app["name"]
            text = name if len(name) <= 24 else name[:23] + "\u2026"
            if app["phone"] and not app["messaging"]:
                text += " (phone)"
            self.apps_grid.addWidget(Check(text, plugins.app_on(name, app["messaging"]),
                                           lambda v, n=name: self.app_changed(n, v)), i // 3, i % 3)


# ------------------------------------------------------------------ Keys
class KeysPage(Page):
    """Keys (assistant_ui._build_keys): each group of keys a part, a box for each that hides what's typed, and Save
    keys. Saved in Windows Credential Manager, never in a file."""

    def __init__(self, window):
        super().__init__(window, "Keys", "Saved in Windows Credential Manager. A key in .env wins over these. Saved "
                         "keys stay hidden.", scroll=True)
        self.fields = {}
        for (heading, about, rows), (name, _, icon) in zip(ui.KEY_GROUPS, ui.KEY_PARTS):
            card = self.part(name, icon)
            if about:
                card.add(label(about, kit.font(12.5), MUTED, wrap=True))
            for i, (title, key_name, use, url) in enumerate(rows):
                hint = "Already saved" if ui.get_secret(key_name) else ("Paste key" if key_name in ui.KEY_NAMES and
                                                                        key_name not in ui.OPTIONAL else "Optional")
                field = entry(hint, 300)
                field.setEchoMode(QLineEdit.EchoMode.Password)
                field.returnPressed.connect(self.save)
                self.fields[key_name] = field
                card.add(Row(title, use, field, first=i == 0 and not about, link=url))
        self.jumps()
        bar = QHBoxLayout()
        self.message = label("", kit.font(12.5), ERROR, wrap=True)
        bar.addWidget(self.message, 1)
        bar.addWidget(button("Save keys", self.save, accent=True))
        holder = QWidget()
        holder.setLayout(bar)
        self.body.addWidget(holder)
        self.finish()

    def key_saved(self, key_name):
        if key_name in self.fields:
            self.fields[key_name].setPlaceholderText("Already saved")

    def save(self):
        settings_page = self.window.pages.get("settings")
        try:
            saved = []
            for key_name, field in self.fields.items():
                value = field.text()
                if value:
                    ui.save_secret(key_name, value)
                    saved.append(key_name)
                    field.clear()
                    field.setPlaceholderText("Already saved")
            if saved and settings_page is not None:
                settings_page.show_models()
                settings_page.refresh_models()
                settings_page.show_voice()
                settings_page.show_ears()
            missing = ui.missing_secrets()
            if missing:
                names = ", ".join(n.replace("_API_KEY", "").replace("_", " ").title() for n in missing)
                self.say(f"Still needed: {names}", error=True, note=self.message)
                return
            from siri import reload_keys
            reload_keys()
            phone = "TELEGRAM_BOT_TOKEN" in saved
            if phone:
                self.window.controls.put("phone token")
            self.say("Saved. Now send /start to your bot on Telegram and type the code it replies with in Settings > "
                     "Phone" if phone and not settings.get("telegram_owner") else "Saved", note=self.message)
            if settings_page is not None:
                settings_page.phone_status()
            self.window.start_worker()
        except Exception as exc:
            self.say(str(exc), error=True, note=self.message)

