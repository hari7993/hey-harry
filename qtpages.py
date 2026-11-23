"""Her Qt window's pages other than the chat (qtwindow, 22 November 2026): To-do, Tasks, Activity, what she knows,
Settings, the Island and Keys, as assistant_ui's Tk pages have them, the same words, the same files and the same
steps, drawn by Qt. build(window) makes them all, by tab key.

Each is a Page: what it's for in grey along its top (its name is in the window's top), then what it holds. Lists are
Tables (a double-click or F2 changes a cell where one can be changed), the long pages are parts, cards that fold
(Part), with their names along the top to jump to. A page not moved over yet says so (Soon), with the classic window
a click away."""
import json
import os
import re
import time

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QComboBox, QDialog, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

import assistant_ui as ui
import identity
import qtkit as kit
import settings
from qtkit import BG, ERROR, LINE, MUTED, TEXT, qc

FIELD, FIELD_OVER, FIELD_DOWN = ui.FIELD, ui.FIELD_OVER, ui.FIELD_DOWN
STYLE = f"""
    QLineEdit {{ background: {FIELD}; border: none; border-radius: 9px; padding: 7px 10px; color: {TEXT};
                selection-background-color: #d6e4fd; selection-color: {TEXT}; }}
    QLineEdit:hover {{ background: {FIELD_OVER}; }}
    QLineEdit:focus {{ background: {FIELD_OVER}; }}
    QComboBox {{ background: {FIELD}; border: none; border-radius: 9px; padding: 6px 30px 6px 10px; color: {TEXT}; }}
    QComboBox:hover {{ background: {FIELD_OVER}; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
    QComboBox QAbstractItemView {{ background: #ffffff; border: 1px solid #e7e7ea; padding: 4px; outline: none;
                                   selection-background-color: #f3f4f6; selection-color: {TEXT}; }}
    QPushButton {{ background: {FIELD}; color: {TEXT}; border: none; border-radius: 9px; padding: 7px 14px; }}
    QPushButton:hover {{ background: {FIELD_OVER}; }}
    QPushButton:pressed {{ background: {FIELD_DOWN}; }}
    QPushButton:disabled {{ color: {kit.FAINT}; }}
    QPushButton[accent="true"] {{ background: {TEXT}; color: #ffffff; }}
    QPushButton[accent="true"]:hover {{ background: #2b3240; }}
    QTableWidget {{ background: #ffffff; border: none; gridline-color: transparent; outline: none;
                    selection-background-color: {FIELD_OVER}; selection-color: {TEXT}; }}
    QTableWidget::item {{ padding: 0 8px; border-bottom: 1px solid #f3f4f6; }}
    QTableWidget::item:selected {{ background: {FIELD_OVER}; color: {TEXT}; }}
    QHeaderView::section {{ background: #ffffff; color: {MUTED}; border: none; border-bottom: 1px solid {LINE};
                            padding: 6px 8px; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px 0; }}
    QScrollBar::handle:vertical {{ background: #d9dbe0; border-radius: 3px; min-height: 40px; }}
    QScrollBar::handle:vertical:hover {{ background: #c4c7ce; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QScrollBar:horizontal {{ height: 0; }}
    QPlainTextEdit {{ background: {FIELD}; border: none; border-radius: 10px; padding: 8px; color: {TEXT};
                      selection-background-color: #d6e4fd; selection-color: {TEXT}; }}
    QToolTip {{ background: #111827; color: #ffffff; border: none; padding: 5px 8px; border-radius: 6px; }}"""


def label(text="", f=None, colour=TEXT, wrap=False, select=False):
    """Words in her type, as the Tk window's _label."""
    w = QLabel(identity.named(text) if text else "")
    w.setFont(f or kit.font(14))
    w.setStyleSheet(f"color: {colour}; background: transparent;")
    w.setWordWrap(wrap)
    if select:
        w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return w


def button(text, command=None, accent=False):
    """A soft grey button, darker under the mouse; black for the one a box is for (accent)."""
    b = QPushButton(text)
    b.setFont(kit.font(13.5))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if accent:
        b.setProperty("accent", True)
    if command is not None:
        b.clicked.connect(lambda _=False: command())
    return b


def entry(hint, width=None):
    """A box to type in, its hint in grey while it's empty."""
    e = QLineEdit()
    e.setPlaceholderText(hint)
    e.setFont(kit.font(14))
    if width:
        e.setFixedWidth(width)
    return e


class Combo(QComboBox):
    """A drop-down, a soft grey pill with its chevron drawn in the icon font."""

    def __init__(self, values=(), parent=None):
        super().__init__(parent)
        self.setFont(kit.font(14))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.addItems(list(values))
        self.view().setFont(kit.font(14))

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setFont(kit.icon_font(9))
        p.setPen(qc(MUTED))
        p.drawText(QRectF(self.width() - 24, 0, 14, self.height()), Qt.AlignmentFlag.AlignCenter, "\ue70d")

    def wheelEvent(self, e):
        e.ignore()  # the page scrolls; a pick never changes under the wheel


class Check(QAbstractButton):
    """A checkbox as the Tk window draws it (_tick_box): a hairline square with round corners, her blue under the
    mouse, and her blue with a white tick once it's on; its words after it."""

    def __init__(self, text, on=False, command=None, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(bool(on))
        self.setText(identity.named(text))
        self.setFont(kit.font(14))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        if command is not None:
            self.toggled.connect(lambda v: command(bool(v)))

    def sizeHint(self):
        return QSize(int(22 + kit.width_of(self.font(), self.text()) + 4), 26)

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = (self.height() - 14) / 2
        box = QRectF(1, y, 14, 14)
        if self.isChecked():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(ui.ACCENT))
            p.drawRoundedRect(box, 3, 3)
            pen = QPen(qc("#ffffff"), 1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPolyline(QPolygonF([QPointF(box.x() + x, box.y() + y) for x, y in ((3.5, 7.3), (6, 9.8),
                                                                                     (10.6, 4.7))]))
        else:
            p.setPen(QPen(qc(ui.ACCENT if self.underMouse() else ui.EDGE), 1))
            p.setBrush(qc("#ffffff"))
            p.drawRoundedRect(box.adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)
        p.setFont(self.font())
        p.setPen(qc(TEXT if self.isEnabled() else kit.FAINT))
        p.drawText(QRectF(22, 0, self.width() - 22, self.height()), Qt.AlignmentFlag.AlignVCenter, self.text())


class Table(QTableWidget):
    """A list as the Tk window's Treeview: a heading row in small grey, rows 34 px with a faint line under each, one
    picked at a time. editable: a double-click or F2 changes a cell, edited(row, column key, words) told of it."""

    def __init__(self, columns, editable=True, edited=None):
        super().__init__(0, len(columns))
        self.keys = [c[0] for c in columns]
        self.setHorizontalHeaderLabels([c[1] for c in columns])
        self.verticalHeader().hide()
        self.setShowGrid(False)
        self.setFont(kit.font(14))
        self.horizontalHeader().setFont(kit.font(12.5))
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.horizontalHeader().setHighlightSections(False)
        for i, (_, _, width) in enumerate(columns):
            self.setColumnWidth(i, width)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setDefaultSectionSize(34)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
                             if editable else QAbstractItemView.EditTrigger.NoEditTriggers)
        self.edited = edited
        self.itemChanged.connect(self._changed)
        self.filling = False

    def fill(self, rows, greys=()):
        """rows: each a tuple of words, in the columns' order; greys: the rows drawn in grey."""
        keep = self.selected()
        self.filling = True
        self.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if r in greys:
                    item.setForeground(qc(MUTED))
                self.setItem(r, c, item)
        self.filling = False
        if keep is not None and keep < len(rows):
            self.selectRow(keep)

    def selected(self):
        """The row picked, or None."""
        rows = self.selectionModel().selectedRows() if self.selectionModel() else []
        return rows[0].row() if rows else None

    def _changed(self, item):
        if not self.filling and self.edited is not None:
            self.edited(item.row(), self.keys[item.column()], item.text())


class Part(QFrame):
    """A part of a long page (assistant_ui._part): a card with a hairline round it, its icon and its name at its top,
    then its rows. A click on its top folds it to its name and opens it again; how you left it is kept (settings
    parts_folded)."""

    def __init__(self, title, icon, folded=False, parent=None):
        super().__init__(parent)
        self.title = title
        self.setObjectName("part")
        self.setStyleSheet(f"QFrame#part {{ background: #ffffff; border: 1px solid {LINE}; border-radius: 14px; }}")
        col = QVBoxLayout(self)
        col.setContentsMargins(20, 12, 20, 14)
        col.setSpacing(0)
        self.top = PartTop(self, title, icon)
        col.addWidget(self.top)
        self.rows = QWidget(self)
        self.rows.setObjectName("rows")
        self.rows.setStyleSheet("QWidget#rows { background: transparent; }")
        self.grid = QGridLayout(self.rows)
        self.grid.setContentsMargins(0, 8, 0, 0)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(8)
        self.grid.setColumnStretch(0, 1)
        col.addWidget(self.rows)
        kept = settings.get("parts_folded")
        kept = kept if isinstance(kept, dict) else {}
        self.shut = bool(kept.get(title, folded))
        self.rows.setVisible(not self.shut)

    def fold(self):
        self.shut = not self.shut
        now = settings.get("parts_folded")
        settings.put("parts_folded", {**(now if isinstance(now, dict) else {}), self.title: self.shut})
        self.rows.setVisible(not self.shut)
        self.top.update()

    def unfold(self):
        if self.shut:
            self.fold()

    def add(self, widget, row=None, col=0, span=1):
        """widget on the next row (or row), across span columns."""
        row = self.grid.rowCount() if row is None else row
        self.grid.addWidget(widget, row, col, 1, span)
        return row


class PartTop(QAbstractButton):
    def __init__(self, part, title, icon):
        super().__init__(part)
        self.part, self.title, self.icon = part, title, icon
        self.setFixedHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.clicked.connect(part.fold)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        p.setFont(kit.icon_font(15))
        p.setPen(qc(MUTED))
        p.drawText(QRectF(0, 0, 24, h), Qt.AlignmentFlag.AlignVCenter, self.icon)
        p.setFont(kit.font(15, "semibold"))
        p.setPen(qc(TEXT))
        p.drawText(QRectF(34, 0, self.width() - 60, h), Qt.AlignmentFlag.AlignVCenter, identity.named(self.title))
        p.setFont(kit.icon_font(9))
        p.setPen(qc(MUTED))
        p.drawText(QRectF(self.width() - 16, 0, 14, h), Qt.AlignmentFlag.AlignVCenter,
                   "\ue76c" if self.part.shut else "\ue70d")


class Chip(QAbstractButton):
    """A soft grey pill with words in it: the parts along the top of a long page, a click going to one."""

    def __init__(self, words, command):
        super().__init__()
        self.words = words
        self.setFont(kit.font(12.5))
        self.setFixedSize(int(kit.width_of(self.font(), words) + 26), 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(command)

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(FIELD_OVER if self.underMouse() else FIELD))
        p.drawRoundedRect(QRectF(self.rect()), 14, 14)
        p.setFont(self.font())
        p.setPen(qc(TEXT))
        p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, self.words)


class Page(QWidget):
    """A page of her window: what it's for in grey along its top, then what it holds (body, a column), in from the
    sides; scrolling with the wheel's glide if scroll. head: (its name, what it's for), for the window's top."""

    def __init__(self, window, title, subtitle, scroll=False):
        super().__init__(window)
        self.window, self.head = window, (title, subtitle)
        self.setStyleSheet(STYLE)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), qc(BG))
        self.setPalette(palette)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 4, 28, 16)
        outer.setSpacing(0)
        self.outer = outer
        if subtitle:
            sub = label(subtitle, kit.font(13), MUTED, wrap=True)
            sub.setMaximumWidth(760)
            outer.addWidget(sub)
            outer.addSpacing(14)
        self.top_bar = None
        self.parts_ = []
        if scroll:
            self.area = QScrollArea(self)
            self.area.setWidgetResizable(True)
            self.area.setFrameShape(QFrame.Shape.NoFrame)
            inner = QWidget()
            inner.setObjectName("inner")
            inner.setStyleSheet(f"QWidget#inner {{ background: {BG}; }}")
            self.body = QVBoxLayout(inner)
            self.body.setContentsMargins(0, 0, 10, 10)
            self.body.setSpacing(14)
            self.area.setWidget(inner)
            self.glide = kit.Glide(self.area)
            outer.addWidget(self.area, 1)
            self.end = None
        else:
            self.area = None
            self.body = QVBoxLayout()
            self.body.setSpacing(10)
            outer.addLayout(self.body, 1)

    def finish(self):
        """The room under the last part, on a long page."""
        if self.area is not None:
            self.body.addStretch(1)

    def part(self, title, icon, folded=False):
        p = Part(title, icon, folded)
        self.body.addWidget(p)
        self.parts_.append((title, p))
        return p

    def jumps(self):
        """Each part's name along the top, staying there as the page scrolls; a click on one goes to it."""
        bar = QHBoxLayout()
        bar.setSpacing(6)
        for title, p in self.parts_:
            bar.addWidget(Chip(title, lambda _=False, p=p: self.go_to(p)))
        bar.addStretch(1)
        self.outer.insertLayout(self.outer.count() - 1, bar)
        self.outer.insertSpacing(self.outer.count() - 1, 14)

    def go_to(self, part):
        """The page scrolled till part is at its top, quickly, then settling (assistant_ui._jump)."""
        part.unfold()
        if self.area is None:
            return
        bar = self.area.verticalScrollBar()
        QTimer.singleShot(0, lambda: self._scroll_to(bar, part.y()))

    def _scroll_to(self, bar, y):
        end = max(bar.minimum(), min(bar.maximum(), y))
        if not kit.animations_on():
            bar.setValue(end)
            return
        anim = QVariantAnimation(self, duration=320, startValue=float(bar.value()), endValue=float(end))
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(lambda v: bar.setValue(round(v)))
        self._jump = anim
        anim.start()

    def parts(self):
        """Its parts by name, for her quick actions: (name, what goes to it)."""
        return [(title, lambda p=p: self.go_to(p)) for title, p in self.parts_]

    def bar(self, buttons, message=True):
        """A row of buttons under a list, and a note after them that says what happened (say)."""
        row = QHBoxLayout()
        row.setSpacing(6)
        for b in buttons:
            row.addWidget(b)
        self.note = label("", kit.font(12.5), MUTED)
        if message:
            row.addSpacing(6)
            row.addWidget(self.note, 1)
        else:
            row.addStretch(1)
        self.body.addSpacing(2)
        self.body.addLayout(row)
        return self.note

    def say(self, text, error=False, note=None):
        note = note or self.note
        note.setText(text)
        note.setStyleSheet(f"color: {ERROR if error else MUTED}; background: transparent;")


def top_row(*widgets, stretch_at=None):
    row = QHBoxLayout()
    row.setSpacing(8)
    for i, w in enumerate(widgets):
        if i == stretch_at:
            row.addStretch(1)
        row.addWidget(w)
    if stretch_at is None:
        row.addStretch(1)
    return row


# ------------------------------------------------------------------ Activity
class Stats(Page):
    """Activity: what she's done for you, your dictation's figures together and her commands' together; what you use
    most; how to use her, folded shut till you want it (assistant_ui._build_stats)."""

    def __init__(self, window):
        super().__init__(window, "Activity", "What she's done for you, and what you use most.", scroll=True)
        self.cards = []
        for name, icon, first in (("Dictation", "\ue720", 0), ("Commands", "\ue945", 3)):
            p = self.part(name, icon)
            row = QHBoxLayout()
            row.setSpacing(0)
            for n in range(3):
                i = first + n
                if n:
                    line = QFrame()
                    line.setFixedWidth(1)
                    line.setStyleSheet(f"background: {LINE};")
                    row.addWidget(line)
                cell = QVBoxLayout()
                cell.setContentsMargins(18 if n else 0, 10, 8, 2)
                cell.setSpacing(2)
                value = label("", kit.font(28))
                named = QHBoxLayout()
                named.setSpacing(6)
                mark = label(ui.STAT_ICONS[i], kit.icon_font(15), ui.TINTS[ui.STAT_TINTS[i]][0])
                title = label("", kit.font(14, "semibold"))
                named.addWidget(mark)
                named.addWidget(title)
                named.addStretch(1)
                sub = label("", kit.font(12.5), MUTED, wrap=True)
                cell.addWidget(value)
                cell.addLayout(named)
                cell.addWidget(sub)
                row.addLayout(cell, 1)
                self.cards.append((value, title, sub))
            holder = QWidget()
            holder.setLayout(row)
            p.add(holder)
        p = self.part("Most used", "\ue734")
        self.top_actions = label("", kit.font(14), MUTED, wrap=True)
        p.add(self.top_actions)
        p = self.part("How to use", "\ue897", folded=True)
        p.add(label(ui.HOW_TO, kit.font(14), MUTED, wrap=True, select=True))
        self.finish()

    def shown(self):
        self.load()

    def load(self):
        words = dictations = words_today = dictations_today = 0
        today = time.strftime("%Y-%m-%d")
        if os.path.exists(ui.HISTORY):
            with open(ui.HISTORY, encoding="utf-8") as f:
                for line in f:
                    try:
                        item = json.loads(line)
                    except ValueError:
                        continue
                    n = len(item.get("text", "").split())
                    words += n
                    dictations += 1
                    if item.get("time", "").startswith(today):
                        words_today += n
                        dictations_today += 1
        heard, actions, answered, opened = 0, {}, 0, {}
        if os.path.exists(ui.LOG_FILE):
            with open(ui.LOG_FILE, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("> heard:"):
                        heard += 1
                    elif line.startswith("  action: "):
                        parts = line.split(None, 2)
                        if len(parts) < 2:
                            continue
                        actions[parts[1]] = actions.get(parts[1], 0) + 1
                        if parts[1] in ("open", "app_open") and len(parts) > 2:
                            opened[parts[2].strip()] = opened.get(parts[2].strip(), 0) + 1
                    elif line.startswith("  llm ") and not line.startswith("  llm failed"):
                        answered += 1
        saved = words / ui.TYPING_WPM - words / ui.SPEAKING_WPM
        saved_text = (f"{int(saved // 60)} h {int(saved % 60)} min" if saved >= 60 else f"{saved:.0f} min"
                      if saved >= 1 else f"{saved * 60:.0f} sec")
        apps = getattr(self.window.pages.get("apps"), "apps", [])
        names = {row[0]: row[3] or row[1] for row in apps}
        fav = max(opened, key=opened.get) if opened else None
        fav_name = names.get(fav, (fav or "None yet").replace("_", " "))
        free = ui.opencode.is_free(settings.get("llm_model"))
        cards = (
            (saved_text, "Time saved", f"vs typing at {ui.TYPING_WPM} words a minute"),
            (f"{words:,}", "Words dictated", f"{words_today:,} today"),
            (f"{dictations:,}", "Dictations", f"{dictations_today:,} today"),
            (f"{sum(actions.values()):,}", "Commands done", f"from {heard:,} things she heard"),
            (fav_name if len(fav_name) <= 14 else fav_name[:13] + "\u2026", "Most opened app",
             f"opened {opened[fav]} times" if fav else "Say \u201cHey Harry, open Spotify\u201d"),
            (f"{answered:,}", "Questions answered", "by free models, $0" if free else
             f"now on {ui.providers.split(settings.get('llm_model'))[0].name}"),
        )
        for (value, title, sub), (v, t, s) in zip(self.cards, cards):
            value.setText(v)
            title.setText(t)
            sub.setText(identity.named(s))
        merged = {}
        for a, n in actions.items():
            name = ui.ACTION_NAMES.get(a, a.replace("_", " ").capitalize())
            merged[name] = merged.get(name, 0) + n
        top = sorted(merged.items(), key=lambda kv: -kv[1])[:6]
        self.top_actions.setText("   \u00b7   ".join(f"{name}  {n}" for name, n in top) or
                                 identity.named("Nothing yet. Say \u201cHey Harry\u201d and a command to get started."))


# ------------------------------------------------------------------ Contacts
class Contacts(Page):
    def __init__(self, window):
        super().__init__(window, "Contacts", "Who Harry can message, and how. She asks once, then remembers. Nothing "
                         "is ever sent until you say yes. Double-click a cell to fix it.")
        self.table = Table((("name", "Name you say", 150), ("whatsapp", "WhatsApp number", 170),
                            ("telegram", "Telegram username", 170), ("other", "Found in other apps as", 190)),
                           edited=self.edited)
        self.body.addWidget(self.table, 1)
        self.bar([button("Remove", self.remove)])
        self.contacts = []

    def shown(self):
        self.load()

    def load(self, message=None):
        self.contacts = sorted(ui.messaging.read_contacts().items())
        rows = []
        for key, item in self.contacts:
            elsewhere = ", ".join(f"{ui.messaging.say_of(a)}: {h}" for a, h in sorted(item.items())
                                  if a not in ("name", "whatsapp", "telegram") and h)
            rows.append((item.get("name") or key, item.get("whatsapp", ""), item.get("telegram", ""), elsewhere))
        self.table.fill(rows)
        taught = ui.messaging.learned_apps()
        note = message or f"{len(self.contacts)} saved"
        if taught and not message:
            note += " \u00b7 also learned to message in " + ", ".join(taught)
        self.say(note)

    def edited(self, row, ident, value):
        value = value.strip()
        key, item = self.contacts[row]
        messaging = ui.messaging

        def rewrite(name):
            messaging.forget_contact(key)
            for app, handle in item.items():
                if app != "name" and handle:
                    messaging.save_contact(name, app, handle)
        if ident == "other":
            self.load("Harry learns those herself, so there's nothing to edit here")
            return
        try:
            if ident == "name" and value:
                rewrite(value)
            elif ident in ("whatsapp", "telegram"):
                if value:
                    messaging.save_contact(item.get("name") or key, ident, value)
                else:
                    item.pop(ident, None)
                    rewrite(item.get("name") or key)
            self.load("Saved")
        except (ValueError, RuntimeError) as exc:
            self.load(f"Couldn't save: {exc}")

    def remove(self):
        row = self.table.selected()
        if row is None:
            self.say("Pick someone in the list first", error=True)
            return
        key = self.contacts[row][0]
        ui.messaging.forget_contact(key)
        self.load(f"Removed {key}")


# ------------------------------------------------------------------ To-do
class Todo(Page):
    def __init__(self, window):
        super().__init__(window, "To-do", "Say \u201cHey Harry, add milk to my to-do list\u201d, \u201cwhat\u2019s on my "
                         "to-do list?\u201d or \u201ccross off milk\u201d. It stays on this PC. Things you tick off stay "
                         "here a week, in grey, so one ticked by mistake can be put back. Double-click one to fix it.")
        self.new = entry("Something to do", 380)
        self.new.returnPressed.connect(self.add)
        self.body.addLayout(top_row(self.new, button("Add", self.add)))
        self.table = Table((("text", "To do", 390), ("added", "Added", 130), ("done", "Done", 130)),
                           edited=self.edited)
        self.body.addWidget(self.table, 1)
        self.bar([button("Done", lambda: self.act("done")), button("Put back", lambda: self.act("back")),
                  button("Remove", lambda: self.act("remove"))])
        self.ids, self.seen = [], None

    def shown(self):
        self.load()

    def tick(self):
        if self.window.current_tab == "todo" and ui.todo_stamp() != self.seen:
            self.load()

    def load(self, message=None, error=False):
        self.seen = ui.todo_stamp()
        try:
            found = ui.todo.items(done=True)
        except Exception as exc:
            self.say(f"Couldn't read your to-do list: {exc}", error=True)
            return
        left = [i for i in found if not i.get("done")]
        done = sorted((i for i in found if i.get("done")), key=lambda i: -float(i.get("done_at") or 0))
        rows, greys, self.ids = [], set(), []
        for item in left + done:
            iid = str(item.get("id", ""))
            if not iid.isdigit() or int(iid) in self.ids:
                continue
            if item.get("done"):
                greys.add(len(rows))
            self.ids.append(int(iid))
            rows.append((ui.todo.shown(item), ui.when_text(item.get("added")),
                         ui.when_text(item.get("done_at")) if item.get("done") else ""))
        self.table.fill(rows, greys)
        self.say(message or (f"{len(left)} to do" + (f" \u00b7 {len(done)} done this week" if done else "")), error)

    def add(self):
        try:
            item, new = ui.todo.add(self.new.text())
        except (ValueError, OSError) as exc:
            self.say("Type something to do first" if isinstance(exc, ValueError) else f"Couldn't save: {exc}", True)
            return
        self.new.clear()
        self.new.setFocus()
        self.load(f"Added \u201c{item['text']}\u201d" if new else f"\u201c{item['text']}\u201d is already there")

    def edited(self, row, ident, value):
        if ident != "text":
            self.load("Only what it says can be changed")
            return
        try:
            item = ui.todo.edit(self.ids[row], value.strip())
        except ValueError:
            self.load("Type what it says, or pick it and press Remove", error=True)
            return
        except (LookupError, OSError) as exc:
            self.load(f"Couldn't save: {exc}", error=True)
            return
        self.load(f"Saved \u201c{item['text']}\u201d")

    def act(self, action):
        row = self.table.selected()
        if row is None:
            self.load("Pick one in the list first", error=True)
            return
        item_id = self.ids[row]
        try:
            item = ui.todo.tick(item_id) if action == "done" else ui.todo.undo(item_id) if action == "back" else \
                ui.todo.drop(item_id)
        except (LookupError, OSError) as exc:
            self.load(str(exc), error=True)
            return
        self.load({"done": "Ticked off", "back": "Put back", "remove": "Removed"}[action] +
                  f" \u201c{item['text']}\u201d")


# ------------------------------------------------------------------ Tasks
class Tasks(Page):
    def __init__(self, window):
        super().__init__(window, "Background tasks", "Durable work and reminders. They survive a restart; commands "
                         "that can change things wait for approval.")
        window.task_store = self.store = ui.tasking.Store()
        self.table = Table((("id", "ID", 42), ("task", "Task", 245), ("status", "Status", 115),
                            ("next", "Next run", 145), ("result", "Last result", 220)), editable=False)
        self.body.addWidget(self.table, 1)
        self.bar([button("Refresh", self.load), button("Cancel", lambda: self.act("cancel")),
                  button("Approve", lambda: self.act("approve"))])
        self.ids, self.seen, self.version = [], None, None

    def shown(self):
        self.load()

    def tick(self):
        if self.window.current_tab != "tasks" or ui.activity.version == self.version:
            return
        self.version = ui.activity.version
        if ui.activity.signature("task:") != self.seen:
            self.load()

    def load(self, message=None):
        self.seen = ui.activity.signature("task:")
        live = {item["key"]: item for item in ui.activity.snapshot()}
        try:
            tasks = self.store.list(80)
        except Exception as exc:
            self.say(f"Couldn't read tasks: {exc}", error=True)
            return
        rows, self.ids = [], []
        for task in tasks:
            due = ui.tasking.describe_due(task["due"]) if task["status"] in ("queued", "waiting_approval") else "\u2014"
            result = " ".join(str(task.get("error") or task.get("result") or "").split())
            status = task["status"].replace("_", " ")
            note = (live.get(f"task:{task['id']}") or {}).get("note") if task["status"] == "running" else ""
            rows.append((task["id"], task["description"], f"{status}, {note[0].lower()}{note[1:]}" if note else status,
                         due, result[:100]))
            self.ids.append(task["id"])
        self.table.fill(rows)
        self.say(message or f"{len(tasks)} task{'s' if len(tasks) != 1 else ''}")

    def act(self, action):
        row = self.table.selected()
        if row is None:
            self.say("Pick a task first", error=True)
            return
        task_id = self.ids[row]
        ok = self.store.cancel(task_id) if action == "cancel" else self.store.approve(task_id)
        done = "cancelled" if action == "cancel" else "approved"
        self.load(f"Task {task_id} {done}" if ok else f"Task {task_id} can't be {done}")


# ------------------------------------------------------------------ Dictionary
class Dictionary(Page):
    def __init__(self, window):
        super().__init__(window, "Dictionary", "Words the transcriber gets wrong. Anything under \u201cheard as\u201d "
                         "is swapped for the word. Double-click a cell, or press F2, to edit it.")
        self.word, self.alts, self.search = entry("Correct word", 170), entry("Heard as, comma separated", 280), \
            entry("Search", 160)
        self.alts.returnPressed.connect(self.add)
        self.search.textChanged.connect(lambda _: self.filter())
        self.body.addLayout(top_row(self.word, self.alts, button("Add word", self.add), self.search, stretch_at=3))
        self.table = Table((("word", "Word", 170), ("heard", "Heard as", 440)), edited=self.edited)
        self.body.addWidget(self.table, 1)
        self.bar([button("Remove", self.remove)])
        self.vocab = [[w, list(alts)] for w, alts in ui.read_vocab().items()]
        self.visible = []
        self.filter()

    def filter(self):
        q = self.search.text().strip().lower()
        self.visible = [i for i, (w, alts) in enumerate(self.vocab)
                        if not q or q in w.lower() or any(q in a.lower() for a in alts)]
        self.table.fill([(self.vocab[i][0], ", ".join(self.vocab[i][1])) for i in self.visible])

    def save(self, message):
        try:
            ui.save_vocab({w: alts for w, alts in self.vocab})
            self.say(message)
        except Exception as exc:
            self.say(f"Couldn't save: {exc}", error=True)
        self.filter()

    def add(self):
        word, alts = self.word.text().strip(), ui.split_list(self.alts.text())
        if not word or not alts:
            self.say("Add the word and at least one way it gets misheard", error=True)
            return
        for item in self.vocab:
            if item[0].lower() == word.lower():
                item[1] += [a for a in alts if a.lower() not in (x.lower() for x in item[1])]
                break
        else:
            self.vocab.insert(0, [word, alts])
        for field in (self.word, self.alts, self.search):
            field.clear()
        self.save(f"Added {word}, used straight away")
        self.word.setFocus()

    def edited(self, row, ident, value):
        item = self.vocab[self.visible[row]]
        if ident == "word":
            if value.strip():
                item[0] = value.strip()
        else:
            item[1] = ui.split_list(value)
        self.save("Saved, used straight away")

    def remove(self):
        row = self.table.selected()
        if row is None:
            self.say("Pick a word in the list first", error=True)
            return
        word = self.vocab.pop(self.visible[row])[0]
        self.save(f"Removed {word}")


# ------------------------------------------------------------------ Apps
class Apps(Page):
    def __init__(self, window):
        super().__init__(window, "Apps", "What Harry can open, quit, minimise or switch to. App is its name in the "
                         "Start menu. Program is the .exe, only needed if quit or switch can't find it. Restart Harry "
                         "after changes.")
        self.say_box, self.app_box, self.heard_box = entry("Name you say", 150), entry("App, as in the Start menu", 220), \
            entry("Heard as (optional)", 190)
        self.heard_box.returnPressed.connect(self.add)
        self.body.addLayout(top_row(self.say_box, self.app_box, self.heard_box, button("Add app", self.add)))
        self.table = Table((("say", "Name you say", 120), ("app", "App", 160), ("exe", "Program", 130),
                            ("heard", "Heard as", 240)), edited=self.edited)
        self.body.addWidget(self.table, 1)
        self.bar([button("Remove", self.remove)])
        with open(ui.APPS_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        # each row: [name you say (the key), app, heard as, spoken name in replies or None, exe names]; keys that
        # start "_" are her sites and the apps said on their own, kept as they are on save
        self.apps, self.extra = [], {k: v for k, v in raw.items() if k.startswith("_")}
        for k, v in raw.items():
            if k.startswith("_"):
                continue
            if isinstance(v, str):
                self.apps.append([k, v, [], None, []])
            else:
                exe = v.get("exe", [])
                self.apps.append([k, v["app"], list(v.get("heard_as", [])), v.get("say"),
                                  [exe] if isinstance(exe, str) else list(exe)])
        self.fill()

    def fill(self):
        self.table.fill([(key.replace("_", " "), app, ", ".join(exes), ", ".join(heard))
                         for key, app, heard, _, exes in self.apps])

    def save(self, message):
        lines = []
        for key, app, heard, say, exes in self.apps:
            if heard or say or exes:
                value = {"app": app, **({"say": say} if say else {}),
                         **({"exe": exes[0] if len(exes) == 1 else exes} if exes else {}),
                         **({"heard_as": heard} if heard else {})}
            else:
                value = app
            lines.append(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)}")
        lines += [f"  {json.dumps(k)}: {ui.apps_extra_json(v)}" for k, v in self.extra.items()]
        try:
            with open(ui.APPS_FILE, "w", encoding="utf-8") as f:
                f.write("{\n" + ",\n".join(lines) + "\n}\n")
            self.say(message)
        except Exception as exc:
            self.say(f"Couldn't save: {exc}", error=True)
        self.fill()

    def add(self):
        say, app = self.say_box.text().strip(), self.app_box.text().strip()
        heard = ui.split_list(self.heard_box.text())
        if not say or not app:
            self.say("Add the name you say and the app\u2019s name", error=True)
            return
        key = ui.app_key(say)
        if any(row[0] == key for row in self.apps):
            self.say(f"{say} is already in the list", error=True)
            return
        found = ui.win.find_start_app(app)
        self.apps.append([key, found[0] if found else app, heard, None, []])
        for field in (self.say_box, self.app_box, self.heard_box):
            field.clear()
        note = "" if found else f", but there's no \u201c{app}\u201d in the Start menu"
        self.save(f"Added {say}{note}. Restart Harry to use it")
        self.say_box.setFocus()

    def edited(self, row, ident, value):
        value = value.strip()
        item = self.apps[row]
        if ident == "heard":
            item[2] = ui.split_list(value)
        elif ident == "say" and ui.app_key(value):
            item[0] = ui.app_key(value)
        elif ident == "app" and value:
            item[1] = value
        elif ident == "exe":
            item[4] = ui.split_list(value)
        self.save("Saved, restart Harry to use it")

    def remove(self):
        row = self.table.selected()
        if row is None:
            self.say("Pick an app in the list first", error=True)
            return
        name = self.apps.pop(row)[0].replace("_", " ")
        self.save(f"Removed {name}, restart Harry to finish")


# ------------------------------------------------------------------ Dictation history
class History(Page):
    def __init__(self, window):
        super().__init__(window, "Dictation history", "Everything you\u2019ve dictated, newest first. Kept on this PC "
                         "only.")
        self.table = Table((("time", "When", 130), ("text", "Text", 520)), editable=False)
        self.table.doubleClicked.connect(lambda _: self.copy())
        self.body.addWidget(self.table, 1)
        self.bar([button("Copy", self.copy)])
        self.items = []

    def shown(self):
        self.load()

    def load(self):
        self.items = []
        if os.path.exists(ui.HISTORY):
            with open(ui.HISTORY, encoding="utf-8") as f:
                for line in f:
                    try:
                        item = json.loads(line)
                        self.items.append({"time": item["time"][:16], "text": item["text"]})
                    except (ValueError, KeyError):
                        continue
        self.items.reverse()
        self.table.fill([(i["time"], i["text"].replace("\n", " ")) for i in self.items])
        self.say("" if self.items else identity.named("Nothing yet. Say \u201cHey Harry, transcribe\u201d to start."))

    def copy(self):
        row = self.table.selected()
        if row is None:
            self.say("Pick one in the list first", error=True)
            return
        try:
            ui.win.set_clipboard(self.items[row]["text"])
            self.say("Copied")
        except Exception as exc:
            self.say(str(exc), error=True)


# ------------------------------------------------------------------ Memory
class Memory(Page):
    def __init__(self, window):
        super().__init__(window, "Memory", "What she knows about you, read into everything you ask, her own notes and "
                         "the skills she\u2019s learned. Say \u201cHey Harry, remember that \u2026\u201d, \u201cforget "
                         "that \u2026\u201d, or teach her: \u201cwhen I say \u2026, do \u2026\u201d. Kept on this PC, the "
                         "way Hermes Agent keeps its memory.")
        self.table = Table((("about", "About", 110), ("text", "What she remembers", 540)), editable=False)
        self.body.addWidget(self.table, 1)
        self.bar([button("Add", self.add), button("Edit this", self.edit), button("Forget this", self.forget),
                  button("Edit personality", self.personality), button("Open notes", self.open_notes),
                  button("Open the folder", self.open_folder), button("Clear conversations", self.clear)],
                 message=False)
        self.note = label("", kit.font(12.5), MUTED, wrap=True)
        self.body.addWidget(self.note)
        self.memories = []

    def shown(self):
        self.load()

    def load(self, message=None):
        store = ui.hermes_memory.store()
        try:
            store.load_from_disk()
            learned = ui.skills.list_skills(hidden=True, wait=False)
        except Exception as exc:
            self.say(f"Couldn't read her memory: {exc}", error=True)
            return
        self.memories = [("user", e) for e in store.user_entries] + [("memory", e) for e in store.memory_entries] + \
                        [("long", e["text"]) for e in ui.longmem.entries()] + [("skill", s) for s in learned]
        about = {"user": "You", "memory": "Her notes", "long": "Long memory", "skill": "Skill"}
        self.table.fill([(about[t], " ".join((ui.skill_line(e) if t == "skill" else e).split()))
                         for t, e in self.memories])
        try:
            turns = ui.history.count()
        except Exception:
            turns = 0
        kept = f"She keeps what you say to her ({turns:,} so far) and can look back through it." if turns else ""
        empty = "" if self.memories else identity.named("Nothing yet. Say \u201cHey Harry, remember that \u2026\u201d. ")
        self.say(message or (empty + kept))

    def add(self):
        MemoryEditor(self, "user", "", "Add to her memory").exec()

    def edit(self):
        row = self.table.selected()
        if row is None:
            self.say("Pick one in the list first", error=True)
            return
        target, item = self.memories[row]
        if target == "skill":
            self.say("Skills change when you teach her again: \u201cwhen I say ..., do ...\u201d", error=True)
            return
        if target == "long":
            self.say("Long memory: Forget this, then Add it the way you want it", error=True)
            return
        MemoryEditor(self, target, item, "Change what she remembers").exec()

    def forget(self):
        row = self.table.selected()
        if row is None:
            self.say("Pick one in the list first", error=True)
            return
        target, item = self.memories[row]
        if target == "skill":
            result = ui.skills.delete_skill(item["dir"], really=True, imported=bool(item.get("imported")))
        elif target == "long":
            result = {"success": ui.longmem.forget(item), "error": "Couldn't find that in her long memory"}
        else:
            result = ui.hermes_memory.memory_tool(ui.hermes_memory.store(), "remove", target, old_text=item)
        if result.get("success"):
            self.load("Forgotten")
        else:
            self.say(str(result.get("error") or "Couldn't forget that")[:120], error=True)

    def personality(self):
        try:
            import siri
            siri.soul()
            os.startfile(siri.SOUL_PATH)
            self.say("Save the file and she talks that way from the next thing you ask. Delete it to go back to how "
                     "she was.")
        except Exception as exc:
            self.say(f"Couldn't open it: {exc}", error=True)

    def open_notes(self):
        os.makedirs(ui.NOTES_DIR, exist_ok=True)
        os.startfile(ui.NOTES_DIR)

    def open_folder(self):
        os.makedirs(ui.win.APPDATA_DIR, exist_ok=True)
        os.startfile(ui.win.APPDATA_DIR)

    def clear(self):
        if QMessageBox.question(self, identity.hey(), "Forget every conversation you've had with her? What she "
                                "remembers about you stays.") != QMessageBox.StandardButton.Yes:
            return
        try:
            ui.history.clear()
            self.load("Conversations cleared")
        except Exception as exc:
            self.say(str(exc), error=True)


class MemoryEditor(QDialog):
    """Memory's Add and Edit this: one thing she remembers, about you or a note of hers, written or changed by hand,
    kept by assistant_ui.change_memory. Save keeps it, Escape leaves it."""

    def __init__(self, page, target, text, title):
        super().__init__(page)
        self.page, self.old, self.old_target = page, text or None, target
        self.setWindowTitle(title)
        self.setStyleSheet(STYLE + f" QDialog {{ background: {BG}; }}")
        self.resize(560, 320)
        col = QVBoxLayout(self)
        col.setContentsMargins(16, 14, 16, 14)
        col.setSpacing(8)
        row = QHBoxLayout()
        row.addWidget(label("About", kit.font(14, "semibold")))
        self.about = Combo(["You", "Her notes"])
        self.about.setCurrentIndex(0 if target == "user" else 1)
        row.addWidget(self.about)
        row.addStretch(1)
        col.addLayout(row)
        self.box = QPlainTextEdit(text or "")
        self.box.setFont(kit.font(14))
        col.addWidget(self.box, 1)
        self.note = label("Like: \u201cMy work account is the second one in Chrome\u201d. Never a password or a code.",
                          kit.font(12.5), MUTED, wrap=True)
        col.addWidget(self.note)
        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(button("Save", self.save, accent=True))
        bar.addWidget(button("Cancel", self.reject))
        col.addLayout(bar)
        self.box.setFocus()

    def save(self):
        target = "user" if self.about.currentIndex() == 0 else "memory"
        why = ui.change_memory(self.box.toPlainText(), target, self.old, self.old_target)
        if why:
            self.note.setText(why)
            self.note.setStyleSheet(f"color: {ERROR}; background: transparent;")
            return
        self.accept()
        self.page.load("Changed" if self.old else "Kept")


# ------------------------------------------------------------------ Privacy
class Privacy(Page):
    def __init__(self, window):
        super().__init__(window, "Privacy", "In Hey Harry mode the mic is always on, but it\u2019s heard on your PC "
                         "first. Only this ever leaves it.", scroll=True)
        self.body.setSpacing(4)
        for title, words in ui.PRIVACY:
            self.body.addWidget(label(title, kit.font(15, "semibold")))
            body = label(words, kit.font(14), MUTED, wrap=True, select=True)
            body.setMaximumWidth(760)
            self.body.addWidget(body)
            self.body.addSpacing(10)
        self.finish()


class Soon(Page):
    """A page still in the classic window: what it's for, and a way there."""

    def __init__(self, window, key):
        title = dict(ui.TABS)[key]
        super().__init__(window, title, "")
        self.body.addWidget(label("This page is still in the classic window while it's moved over to the new one.",
                                  kit.font(14), MUTED, wrap=True))
        self.body.addSpacing(6)
        self.body.addLayout(top_row(button("Open the classic window", lambda: window.use_window("tk"), accent=True)))
        self.body.addStretch(1)


PAGES = {"todo": Todo, "tasks": Tasks, "stats": Stats, "contacts": Contacts, "dict": Dictionary, "apps": Apps,
         "hist": History, "mem": Memory, "priv": Privacy}


def build(window):
    """Every page but the chat, by its tab key; one that won't build says so rather than taking the window with it."""
    import qtsettings
    pages = dict(PAGES, settings=qtsettings.SettingsPage, island=qtsettings.IslandPage, keys=qtsettings.KeysPage)
    out = {}
    for key, _ in ui.TABS:
        if key == "home":
            continue
        try:
            out[key] = pages[key](window) if key in pages else Soon(window, key)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"  qt: the {key} page didn't build ({exc!r})")
            out[key] = Soon(window, key)
    return out
