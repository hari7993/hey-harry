"""Her window in Qt (22 November 2026, the owner's choice over Tk: "change to another one", after the Tk window kept
breaking): the same look as assistant_ui's, drawn by Qt, which lays itself out, renders type with DirectWrite and
moves things with real opacity and easing.

Built here: the window's frame (the dark sidebar with your chats under Chat, the top with her state, Full access, the
pencil and the bell), her quick actions (Ctrl+K), and what runs her (her assistant's thread, its events, the island's
looks), as AssistantWindow does them. The chat is qtchat.Page; the other pages are qtpages'.

Her island, dock and screen edges are Tk's (island.py, dock.py, edges.py) and stay so: they run on a Tk root of their
own in a thread of their own (TkSide), so Qt's loop and Tk's never run inside each other.

Opened instead of the Tk window with settings window "qt" (assistant_ui.run_app); python qtwindow.py --preview path
draws a picture of it without starting her."""
import os
import queue
import random
import re
import sys
import threading
import time
import traceback

from PySide6.QtCore import QEasingCurve, QPoint, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QIcon, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (QAbstractButton, QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMenu, QMessageBox, QSizePolicy, QStackedWidget, QVBoxLayout,
                               QWidget)

import assistant_ui as ui
import chat
import identity
import qtkit as kit
import settings
import winplatform as win
from qtkit import BG, MUTED, TEXT, qc

SIDE_W, ROW, GAP = 240, 28, 14  # the sidebar's width, a row of it, the room over a section's name


def side_colours(name):
    """The sidebar's colours (assistant_ui.SIDES) by name: ground, her name, a tab you're not on, the one you're on,
    a group's name, the pill under the tab you're on, the line down its side."""
    return dict(zip(("bg", "text", "idle", "over", "group", "pill", "edge"), ui.SIDES.get(name, ui.SIDES["dark"])))


# ------------------------------------------------------------------ the sidebar
class NavRow(QAbstractButton):
    """A row of the sidebar: a tab (its icon in its own pale tint and its name), a section's name, or one of your
    chats (its title cut to its room and how long ago at the right, or its bin under the mouse). end: a glyph at its
    right end that's a button of its own (Chat's pencil, a chat's bin), its click end_clicked."""

    def __init__(self, side, text, kind, glyph="", tint=None, end="", key=None):
        super().__init__(side)
        self.side, self.text_, self.kind, self.glyph, self.tint, self.end, self.key = side, text, kind, glyph, tint, \
            end, key
        self.when, self.on, self.lit, self.fold = "", False, False, None
        self.end_clicked = None
        self.setFixedHeight(ROW)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setMouseTracking(True)
        self.setAccessibleName(text)
        self.over_end = False

    def mouseMoveEvent(self, e):
        over = bool(self.end) and e.position().x() >= self.width() - 36
        if over != self.over_end:
            self.over_end = over
            self.update()
        super().mouseMoveEvent(e)

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.over_end = False
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if self.end and self.end_clicked and e.position().x() >= self.width() - 36 and \
                self.rect().contains(e.position().toPoint()):
            self.setDown(False)
            self.end_clicked()
            return
        super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        c = self.side.colours
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        over = self.underMouse()
        clickable = self.cursor().shape() == Qt.CursorShape.PointingHandCursor
        if over and not self.on and clickable:  # a soft pill under the mouse, paler than the tab you're on's
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(kit.mix(c["bg"], c["pill"], 0.55)))
            p.drawRoundedRect(QRectF(8, 0, w - 16, h), 9, 9)
        top = self.kind in ("top", "section")
        ink = c["over"] if self.on or self.lit or (over and clickable and not self.over_end) else \
            c["text"] if top else c["idle"]
        if self.glyph:
            p.setFont(self.side.f_icon)
            p.setPen(qc(self.tint or ink))
            p.drawText(QRectF(16, 0, 24, h), Qt.AlignmentFlag.AlignVCenter, self.glyph)
        f = self.side.f_on if top or self.on else self.side.f_row
        right = w - 16
        if self.kind == "chat":
            when_w = kit.width_of(self.side.f_when, self.when)
            if over and self.end:
                p.setFont(self.side.f_icon_small)
                p.setPen(qc(c["over"] if self.over_end else c["idle"]))
                p.drawText(QRectF(right - 16, 0, 16, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                           self.end)
            else:
                p.setFont(self.side.f_when)
                p.setPen(qc(c["group"]))
                p.drawText(QRectF(right - when_w, 0, when_w, h), Qt.AlignmentFlag.AlignVCenter, self.when)
            room = right - 42 - max(when_w, 16) - 10
            p.setFont(f)
            p.setPen(qc(ink))
            p.drawText(QRectF(42, 0, room, h), Qt.AlignmentFlag.AlignVCenter, kit.fit(f, self.text_, room))
            return
        if self.end:  # Chat's pencil at its row's end
            p.setFont(self.side.f_icon)
            p.setPen(qc(c["over"] if self.over_end else c["idle"]))
            p.drawText(QRectF(right - 20, 0, 20, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       self.end)
            right -= 28
        if self.fold is not None:  # a section that folds: its arrow, down while open
            p.setFont(self.side.f_fold)
            p.setPen(qc(c["group"]))
            p.drawText(QRectF(right - 16, 0, 16, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       "\ue70d" if self.fold else "\ue76c")
            right -= 20
        p.setFont(f)
        p.setPen(qc(ink))
        p.drawText(QRectF(42, 0, right - 42, h), Qt.AlignmentFlag.AlignVCenter, kit.fit(f, self.text_, right - 42))


class YouCard(QAbstractButton):
    """Your card at the sidebar's foot, as Hedwig has one: the first letter of your name on a disc, your name, and a
    chevron that says it opens a menu."""

    def __init__(self, side):
        super().__init__(side)
        self.side = side
        self.setFixedHeight(42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName("Your menu")

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _):
        c, s = self.side.colours, self.side
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        if self.isDown():
            p.translate(r.center())
            p.scale(0.98, 0.98)
            p.translate(-r.center())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(kit.mix(c["pill"], c["over"], 0.05) if self.underMouse() else c["pill"]))
        p.drawRoundedRect(r, 13, 13)
        mid = r.height() / 2
        p.setBrush(qc("#e8663c"))
        p.drawEllipse(QRectF(8, mid - 11, 22, 22))
        name = " ".join(str(settings.get("name") or "").split()) or "You"
        p.setFont(s.f_badge)
        p.setPen(qc("#ffffff"))
        p.drawText(QRectF(8, mid - 11, 22, 22), Qt.AlignmentFlag.AlignCenter, name[:1].upper())
        p.setFont(s.f_you)
        p.setPen(qc(c["text"]))
        p.drawText(QRectF(38, 0, r.width() - 70, r.height()), Qt.AlignmentFlag.AlignVCenter,
                   kit.fit(s.f_you, name, r.width() - 70))
        p.setFont(s.f_icon_small)
        p.setPen(qc(c["idle"]))
        p.drawText(QRectF(r.width() - 26, 0, 14, r.height()), Qt.AlignmentFlag.AlignVCenter, "\ue76c")


class Sidebar(QWidget):
    """The sidebar as Hedwig's: her island at the top with search and the panel icon; Chat with your chats under it
    (as many as there's room for), To-do, Tasks and Activity; each other group a section, its icon and name in white
    and its tabs under it in grey; the timers and your card at its foot. The pill under the tab you're on slides to the
    next one."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setFixedWidth(SIDE_W)
        self.colours = side_colours(settings.get("sidebar") or "dark")
        self.f_icon, self.f_icon_small, self.f_fold = kit.icon_font(15), kit.icon_font(12), kit.icon_font(9)
        self.f_row, self.f_on = kit.font(13.5), kit.font(13.5, "medium")
        self.f_when, self.f_badge, self.f_you = kit.font(12.5), kit.font(12, "medium"), kit.font(13, "semibold")
        self.f_timer = kit.font(13, family="Consolas")
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 8)
        col.setSpacing(0)
        top = QWidget(self)
        top.setFixedHeight(60)
        row = QHBoxLayout(top)
        row.setContentsMargins(14, 0, 10, 0)
        row.setSpacing(2)
        self.logo = QLabel(top)
        self.logo.setStyleSheet("background: transparent;")
        row.addWidget(self.logo)
        row.addStretch(1)
        c = self.colours
        self.search = kit.IconButton("\ue721", "Quick actions (Ctrl+K)", colour=c["idle"], hot=c["over"],
                                     back=kit.mix(c["bg"], c["pill"], 0.7))
        self.pane = kit.IconButton("\ue89f", "Hide the sidebar (Ctrl+B)", colour=c["idle"], hot=c["over"],
                                   back=kit.mix(c["bg"], c["pill"], 0.7))
        self.search.clicked.connect(window.open_palette)
        self.pane.clicked.connect(lambda: window.toggle_sidebar(False))
        row.addWidget(self.search)
        row.addWidget(self.pane)
        col.addWidget(top)
        self.nav = QWidget(self)
        self.nav_col = QVBoxLayout(self.nav)
        self.nav_col.setContentsMargins(0, 0, 0, 0)
        self.nav_col.setSpacing(0)
        col.addWidget(self.nav)
        col.addStretch(1)
        self.timers = QWidget(self)
        self.timer_col = QVBoxLayout(self.timers)
        self.timer_col.setContentsMargins(18, 0, 18, 6)
        self.timer_col.setSpacing(0)
        self.timer_rows = []
        for _ in range(3):  # up to three timers, soonest on top
            line = QWidget(self.timers)
            line.setFixedHeight(22)
            lay = QHBoxLayout(line)
            lay.setContentsMargins(0, 0, 0, 0)
            name, left = QLabel(line), QLabel(line)
            name.setFont(self.f_when)
            left.setFont(self.f_timer)
            lay.addWidget(name, 1)
            lay.addWidget(left)
            line.hide()
            self.timer_rows.append((line, name, left))
            self.timer_col.addWidget(line)
        col.addWidget(self.timers)
        foot = QWidget(self)
        lay = QHBoxLayout(foot)
        lay.setContentsMargins(8, 0, 8, 0)
        self.you = YouCard(self)
        self.you.clicked.connect(window.you_menu)
        lay.addWidget(self.you)
        col.addWidget(foot)
        self.rows, self.chat_rows, self.section_rows = {}, [], {}
        was = settings.get("nav_open")
        self.nav_open = {name for name in ui.NAV_FOLDS if name in (was if isinstance(was, list) else ())}
        self.current = None
        self._build_nav()
        self.pill_y = None  # where the pill under the tab you're on is drawn, sliding (select)
        self.pill_anim = QVariantAnimation(self, duration=200, easingCurve=QEasingCurve.Type.OutCubic)
        self.pill_anim.valueChanged.connect(self._pill_moved)
        self.blink_open = 1.0
        self._paint_colours()
        self._draw_logo()
        QTimer.singleShot(2500, self._blink)

    def _tint(self, key):
        pair = ui.SIDE_TINTS.get(key)
        return None if pair is None else pair[0] if self.colours["bg"] == ui.SIDES["dark"][0] else pair[1]

    def _build_nav(self):
        titles = dict(ui.TABS)
        for name, keys in ui.NAV:
            if name:
                spacer = QWidget(self.nav)
                spacer.setFixedHeight(GAP)
                self.nav_col.addWidget(spacer)
                head = NavRow(self, ui.SECTION_LABELS.get(name, name), "section", ui.GROUP_ICONS.get(name, ""),
                              self._tint(name))
                if name in ui.NAV_FOLDS:
                    head.fold = name in self.nav_open
                    head.clicked.connect(lambda n=name: self.fold(n))
                else:
                    head.setCursor(Qt.CursorShape.ArrowCursor)
                    head.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                self.section_rows[name] = head
                self.nav_col.addWidget(head)
            for key in keys:
                top = not name
                row = NavRow(self, titles[key], "top" if top else "indent", ui.ICONS.get(key, "") if top else "",
                             self._tint(key) if top else None, key=key)
                row.clicked.connect(lambda k=key: self.window.select(k))
                self.rows[key] = row
                self.nav_col.addWidget(row)
                if key == "home":  # New chat's pencil at the end of its row, and your chats under it
                    row.end = "\ue70f"
                    row.end_clicked = self.window.new_chat
                    row.setToolTip("Chat  \u00b7  the pencil starts a new one (Ctrl+Shift+O)")
                    for _ in range(ui.RECENT):
                        chat_row = NavRow(self, "", "chat", end="\ue74d")
                        chat_row.hide()
                        chat_row.clicked.connect(lambda r=chat_row: self.window.open_chat(r.key))
                        chat_row.end_clicked = lambda r=chat_row: self.window.delete_chat(r.key)
                        self.chat_rows.append(chat_row)
                        self.nav_col.addWidget(chat_row)

    def fold(self, name):
        """A section that folds (More) opened or shut, and kept so."""
        self.nav_open ^= {name}
        settings.put("nav_open", sorted(self.nav_open))
        self.lay_nav()

    def lay_nav(self):
        """Each section's tabs shown or folded away; as many of your chats under Chat as leave the rest clear of your
        card; the pill under the tab you're on where that tab is now."""
        for name, keys in ui.NAV:
            if not name:
                continue
            shown = name not in ui.NAV_FOLDS or name in self.nav_open or self.current in keys
            head = self.section_rows[name]
            if head.fold is not None:
                head.fold = shown
                head.update()
            for key in keys:
                self.rows[key].setVisible(shown)
        self.lay_chats()

    def lay_chats(self):
        """Your chats under Chat, newest first, the open one lit: as many as there's room for."""
        page = getattr(self.window, "chat", None)
        fixed = 60 + 8 + 42 + sum(not line.isHidden() for line, _, _ in self.timer_rows) * 22 + 6
        rows = sum(1 for r in self.rows.values() if not r.isHidden()) + len(self.section_rows)
        room = self.height() - fixed - rows * ROW - len(self.section_rows) * GAP - 10
        most = max(0, min(ui.RECENT, room // ROW)) if self.height() > 100 else ui.RECENT
        chats = page.listed(most) if page is not None and most else []
        for i, row in enumerate(self.chat_rows):
            if i < len(chats):
                cid, text, at = chats[i]
                row.text_, row.when, row.key = text, chat.ago(time.time() - at), cid
                row.lit = cid == page.chats.current
                row.setAccessibleName(text)
                row.setToolTip(text)
                row.show()
                row.update()
            else:
                row.hide()
        QTimer.singleShot(0, self._place_pill)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.lay_chats()

    def select(self, key):
        """The tab you're on lit, the pill sliding under it."""
        self.current = key
        for k, row in self.rows.items():
            row.on = k == key
            row.update()
        self.lay_nav()

    def _place_pill(self):
        row = self.rows.get(self.current)
        if row is None or row.isHidden():
            self.pill_y = None
            self.update()
            return
        y = row.mapTo(self, QPoint(0, 0)).y()
        if self.pill_y is None or not kit.animations_on() or not self.isVisible():
            self.pill_anim.stop()
            self.pill_y = float(y)
            self.update()
            return
        if abs(self.pill_y - y) < 0.5:
            return
        self.pill_anim.stop()
        self.pill_anim.setStartValue(float(self.pill_y))
        self.pill_anim.setEndValue(float(y))
        self.pill_anim.start()

    def _pill_moved(self, y):
        self.pill_y = y
        self.update()

    def paintEvent(self, _):
        c = self.colours
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qc(c["bg"]))
        p.fillRect(QRectF(self.width() - 1, 0, 1, self.height()), qc(c["edge"]))  # its line by the page
        if self.pill_y is not None:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(c["pill"]))
            p.drawRoundedRect(QRectF(8, self.pill_y, SIDE_W - 16, ROW), 9, 9)

    def set_colours(self, name):
        """Dark, as Hedwig's is, or light (assistant_ui.SIDES): everything of it painted again."""
        self.colours = side_colours(name)
        for key, row in self.rows.items():
            if row.kind == "top":
                row.tint = self._tint(key)
        for name_, head in self.section_rows.items():
            head.tint = self._tint(name_)
        self._paint_colours()
        self._draw_logo()
        for child in self.findChildren(QAbstractButton):
            child.update()
        self.update()

    def _paint_colours(self):
        c = self.colours
        for button in (self.search, self.pane):
            button.colour, button.hot, button.back = c["idle"], c["over"], kit.mix(c["bg"], c["pill"], 0.7)
        for _, name, left in self.timer_rows:
            name.setStyleSheet(f"color: {c['text']}; background: transparent;")
            left.setStyleSheet(f"color: {ui.ACCENT}; background: transparent;")

    def _draw_logo(self):
        pm = kit.logo(24, self.blink_open, self.devicePixelRatioF())
        if pm is not None:
            self.logo.setPixmap(pm)

    def _blink(self):
        """Her eyes on the logo shut and open again, a fifth of a second, now and then, as the island's do."""
        if not kit.animations_on() or not self.isVisible():
            QTimer.singleShot(random.randint(3500, 8000), self._blink)
            return
        anim = QVariantAnimation(self, duration=220, startValue=0.0, endValue=1.0)
        anim.valueChanged.connect(lambda t: (setattr(self, "blink_open", abs(1 - 2 * t)), self._draw_logo()))
        anim.finished.connect(lambda: (setattr(self, "blink_open", 1.0), self._draw_logo(),
                                       QTimer.singleShot(random.randint(3500, 8000), self._blink)))
        self._blinking = anim
        anim.start()

    def show_timers(self, timers):
        """Up to three timers over your card: their names and what's left, soonest on top."""
        changed = False
        for i, (line, name, left) in enumerate(self.timer_rows):
            if i < len(timers):
                label, secs = timers[i]
                m, sec = divmod(int(secs + 0.999), 60)
                h, m = divmod(m, 60)
                name.setText(label if len(label) <= 18 else label[:17] + "\u2026")
                left.setText(f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}")
                changed |= line.isHidden()
                line.show()
            else:
                changed |= not line.isHidden()
                line.hide()
        if changed:
            self.lay_chats()


# ------------------------------------------------------------------ the top
class HeadButton(QAbstractButton):
    """"Expand frames" at the top's left, as Hedwig's: its icon, its words with how many frames, and an arrow, down
    while they're shown; on another page the page's name, which does nothing."""

    def __init__(self, parent):
        super().__init__(parent)
        self.words, self.on_chat, self.open = "Expand frames", True, False
        self.f_icon, self.f_words, self.f_fold = kit.icon_font(12), kit.font(12.5), kit.icon_font(9)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setFixedHeight(30)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.set(self.words, True, False)

    def set(self, words, on_chat, open_):
        self.words, self.on_chat, self.open = words, on_chat, open_
        self.setCursor(Qt.CursorShape.PointingHandCursor if on_chat else Qt.CursorShape.ArrowCursor)
        w = kit.width_of(self.f_words, words) + (20 + 18 if on_chat else 0) + 4
        self.setFixedWidth(int(w + 0.999))
        self.update()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ink = qc(TEXT if self.on_chat and self.underMouse() else MUTED)
        h, x = self.height(), 0.0
        if self.on_chat:
            p.setFont(self.f_icon)
            p.setPen(ink)
            p.drawText(QRectF(0, 0, 18, h), Qt.AlignmentFlag.AlignVCenter, "\ue80a")
            x = 20
        p.setFont(self.f_words)
        p.setPen(ink)
        p.drawText(QRectF(x, 0, self.width() - x, h), Qt.AlignmentFlag.AlignVCenter, self.words)
        if self.on_chat:
            x += kit.width_of(self.f_words, self.words) + 6
            p.setFont(self.f_fold)
            p.drawText(QRectF(x, 1, 14, h), Qt.AlignmentFlag.AlignVCenter, "\ue70d" if self.open else "\ue76c")


class TopBar(QWidget):
    """The top, one short row as Hedwig's: the panel icon while the sidebar's away, then "Expand frames" (or the
    page's name) at the left; her state in a soft pill, Full access as a pale blue one while it's on, the pencil and
    the bell at the right. 44 px, nothing drawn under it."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setFixedHeight(44)
        row = QHBoxLayout(self)
        row.setContentsMargins(20, 0, 13, 0)
        row.setSpacing(0)
        self.pane = kit.IconButton("\ue8a0", "Show the sidebar (Ctrl+B)")
        self.pane.clicked.connect(lambda: window.toggle_sidebar(True))
        row.addWidget(self.pane)
        self.pane_gap = QWidget(self)
        self.pane_gap.setFixedWidth(6)
        row.addWidget(self.pane_gap)
        self.head = HeadButton(self)
        self.head.clicked.connect(window.frames_click)
        row.addWidget(self.head)
        row.addStretch(1)
        self.status = kit.StatusPill(self)
        row.addWidget(self.status)
        self.full_gap = QWidget(self)
        self.full_gap.setFixedWidth(8)
        row.addWidget(self.full_gap)
        self.full = kit.Pill("Full access", fill="#eef4ff", ink="#3b6fd6", glyph="\uea18", click=True)
        self.full.setToolTip("Full access is on: she sends and installs what you ask without asking first. Click to "
                             "turn it off.")
        self.full.clicked.connect(lambda: window.set_full_access(False))
        row.addWidget(self.full)
        row.addSpacing(7)
        self.pencil = kit.IconButton("\ue70f", "New chat (Ctrl+Shift+O)", css=12)
        self.pencil.clicked.connect(window.new_chat)
        row.addWidget(self.pencil)
        row.addSpacing(6)
        self.bell = kit.IconButton("\uea8f", "What she's done (Activity)", css=12)
        self.bell.clicked.connect(lambda: window.select("stats"))
        row.addWidget(self.bell)
        self.show_full(False)
        self.show_pane(False)

    def show_full(self, on):
        self.full.setVisible(on)
        self.full_gap.setVisible(on)

    def show_pane(self, on):
        self.pane.setVisible(on)
        self.pane_gap.setVisible(on)

    def paintEvent(self, _):
        QPainter(self).fillRect(self.rect(), qc(BG))


# ------------------------------------------------------------------ quick actions
class Palette(QFrame):
    """Her quick actions over the window (Ctrl+K, or search at the sidebar's top), as the Tk window's Palette: a box
    to type in and what matches it, best first; Up and Down go through them, Enter does one, Esc puts it away."""
    MOST = 8

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setObjectName("palette")
        self.setStyleSheet("QFrame#palette { background: #ffffff; border: 1px solid #ececee; border-radius: 14px; }")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 10)
        shadow.setColor(qc("#000000", 0.14))
        self.setGraphicsEffect(shadow)
        col = QVBoxLayout(self)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(2)
        self.box = QLineEdit(self)
        self.box.setPlaceholderText("Search her pages, settings and chats")
        self.box.setFont(kit.font(15))
        self.box.setStyleSheet(f"QLineEdit {{ border: none; background: transparent; color: {TEXT}; padding: 8px 10px;"
                               f" selection-background-color: #dbe6fd; }}")
        self.box.textChanged.connect(self._fill)
        self.box.installEventFilter(self)
        col.addWidget(self.box)
        line = QFrame(self)
        line.setFixedHeight(1)
        line.setStyleSheet("background: #f1f1f2; border: none;")
        col.addWidget(line)
        self.list = QWidget(self)
        self.list_col = QVBoxLayout(self.list)
        self.list_col.setContentsMargins(0, 4, 0, 0)
        self.list_col.setSpacing(0)
        self.rows = []
        for i in range(self.MOST):
            row = PaletteRow(self, i)
            self.rows.append(row)
            self.list_col.addWidget(row)
        col.addWidget(self.list)
        self.empty = QLabel("Nothing in her window is called that.", self)
        self.empty.setFont(kit.font(12.5))
        self.empty.setStyleSheet(f"color: {MUTED}; padding: 10px 12px; background: transparent;")
        col.addWidget(self.empty)
        self.actions, self.found, self.at = window.quick_actions(), [], 0
        self.setFixedWidth(560)
        self._fill("")
        self.show()
        self.raise_()
        self.box.setFocus()
        kit.fade_in(self, 150)

    def place(self):
        self.adjustSize()
        self.move((self.window.width() - self.width()) // 2, 96)

    def _fill(self, text=None):
        text = self.box.text() if text is None else text
        was = [a[1] for a in self.found]
        self.found = chat.find(self.actions, text, self.MOST) if text.strip() else self.actions[:self.MOST]
        if [a[1] for a in self.found] != was:
            self.at = 0
        for i, row in enumerate(self.rows):
            if i < len(self.found):
                row.set(self.found[i], i == self.at)
                row.show()
            else:
                row.hide()
        self.empty.setVisible(not self.found)
        self.place()

    def eventFilter(self, obj, event):
        if obj is self.box and event.type() == event.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self.found:
                self.at = (self.at + (1 if key == Qt.Key.Key_Down else -1)) % len(self.found)
                for i, row in enumerate(self.rows[:len(self.found)]):
                    row.set(self.found[i], i == self.at)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.run(self.at)
                return True
            if key == Qt.Key.Key_Escape:
                self.close_()
                return True
        return super().eventFilter(obj, event)

    def run(self, i):
        if 0 <= i < len(self.found):
            what = self.found[i][3]
            self.close_()
            what()

    def close_(self):
        if self.window.palette is self:
            self.window.palette = None
        self.window.drop_scrim()
        self.hide()
        self.deleteLater()
        self.window.focus_box()


class PaletteRow(QAbstractButton):
    """One of her quick actions: its icon, its name, and what kind of thing it is at the right."""

    def __init__(self, palette, i):
        super().__init__(palette.list)
        self.palette, self.i, self.action, self.lit = palette, i, None, False
        self.setFixedHeight(38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.f_icon, self.f_name, self.f_kind = kit.icon_font(14), kit.font(14), kit.font(12)
        self.clicked.connect(lambda: palette.run(self.i))

    def set(self, action, lit):
        self.action, self.lit = action, lit
        self.update()

    def enterEvent(self, e):
        if self.palette.at != self.i and self.i < len(self.palette.found):
            self.palette.at = self.i
            for i, row in enumerate(self.palette.rows[:len(self.palette.found)]):
                row.set(self.palette.found[i], i == self.i)
        super().enterEvent(e)

    def paintEvent(self, _):
        if self.action is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        if self.lit:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc("#f3f4f6"))
            p.drawRoundedRect(r, 9, 9)
        icon, name, kind = self.action[:3]
        p.setFont(self.f_icon)
        p.setPen(qc(MUTED))
        p.drawText(QRectF(12, 0, 24, r.height()), Qt.AlignmentFlag.AlignVCenter, icon)
        p.setFont(self.f_kind)
        kind_w = kit.width_of(self.f_kind, kind)
        p.drawText(QRectF(r.width() - 12 - kind_w, 0, kind_w, r.height()), Qt.AlignmentFlag.AlignVCenter, kind)
        p.setFont(self.f_name)
        p.setPen(qc(TEXT))
        room = r.width() - 44 - kind_w - 24
        p.drawText(QRectF(44, 0, room, r.height()), Qt.AlignmentFlag.AlignVCenter, kit.fit(self.f_name, name, room))


class Scrim(QWidget):
    """A faint veil over the window behind her quick actions; a click on it puts them away."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setGeometry(window.rect())
        self.show()
        self.raise_()

    def paintEvent(self, _):
        QPainter(self).fillRect(self.rect(), qc("#0b0f19", 0.06))

    def mousePressEvent(self, _):
        if self.window.palette is not None:
            self.window.palette.close_()


# ------------------------------------------------------------------ her island's side
class TkSide:
    """Her island, dock and screen edges, which are Tk's (island.py, dock.py, edges.py), on a Tk root of their own in
    a thread of their own: Qt's loop and Tk's never run inside each other. What the window asks of them is queued and
    done there (call); what they say to her goes to siri's controls, as from the Tk window."""

    def __init__(self):
        self.calls, self.root, self.bubble, self.edges, self.dock = queue.Queue(), None, None, None, None
        self.ready = threading.Event()
        threading.Thread(target=self._run, name="harry-tk", daemon=True).start()

    def _run(self):
        import tkinter as tk
        try:
            root = self.root = tk.Tk()
            root.withdraw()
            root.report_callback_exception = lambda kind, exc, tb: traceback.print_exception(kind, exc, tb)
            from bubble import Bubble
            self.bubble = Bubble(root)
            try:
                import edges
                self.edges = edges.Edges(root)
            except Exception as exc:
                print(f"  the edges didn't start: {exc!r}")
            self._dock_changed()
        except Exception as exc:
            print(f"  qt: her island's side didn't start ({exc!r})")
            traceback.print_exc()
            self.ready.set()
            return
        self.ready.set()
        root.after(15, self._drain)
        root.mainloop()

    def call(self, fn):
        """fn() on the island's thread, soon."""
        self.calls.put(fn)

    def _drain(self):
        while True:
            try:
                fn = self.calls.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                traceback.print_exc()
        try:
            self.root.after(15, self._drain)
        except Exception:
            pass

    def _dock_changed(self):
        """Her dock as Settings has it now (assistant_ui._dock_changed)."""
        want = bool(settings.get("dock"))
        taskbar = settings.get("dock_style") != "dock"
        if self.dock is not None and want and (type(self.dock).__name__ == "Taskbar") != taskbar:
            self.dock.close()
            self.dock = None
        if self.dock is not None and not want:
            self.dock.close()
            self.dock = None
        elif self.dock is not None:
            self.dock.reload()
        elif want:
            try:
                import dock
                self.dock = dock.make(self.root)
            except Exception as exc:
                print(f"  the dock didn't start: {exc!r}")
                self.dock = None
        elif os.path.exists(os.path.join(win.APPDATA_DIR, "taskbar-hidden")):
            import dock
            dock.show_taskbar()

    def dock_changed(self):
        self.call(self._dock_changed)

    def restyle(self, done=None):
        """Her popup made again in the style Settings has now (bubble.Bubble falls back if Windows won't draw it).
        done(its kind) on the island's thread: "island", "card" or "pill"."""
        def go():
            from bubble import Bubble
            old = self.bubble
            if old is not None:
                getattr(old, "destroy", old.close)()
            self.bubble = Bubble(self.root)
            if done is not None:
                done("island" if hasattr(self.bubble, "reload") else "pill" if type(self.bubble).__name__ == "Pill"
                     else "card")
        self.call(go)

    def close(self):
        """The dock first puts Windows' taskbar back, if it hid it; then the edges and the island go."""
        if self.root is None:
            return
        done = threading.Event()

        def go():
            for part in (self.edges, self.dock):
                if part is not None:
                    try:
                        part.close()
                    except Exception as exc:
                        print(f"  qt: couldn't close a part ({exc!r})")
            try:
                if self.bubble is not None:
                    self.bubble.close()
            except Exception:
                pass
            done.set()
            try:
                self.root.quit()
            except Exception:
                pass
        self.call(go)
        done.wait(2.0)


def island_status(bubble, popup, state, detail):
    """What her popup shows for one of her events (assistant_ui._set_status, its island half), on the island's
    thread."""
    if bubble is None:
        return
    if state == "Heard":
        if popup:
            bubble.caption(detail)
        return
    if state == "Mood":
        getattr(bubble, "react", lambda mood: None)(detail)
        return
    if state == "Step":
        kind, _, text = str(detail).partition("\t")
        getattr(bubble, "step", lambda kind, text: None)(kind, text)
        return
    if state == "Asked":
        getattr(bubble, "asked", lambda text: None)(detail)
        return
    if state == "Learned":
        kind, _, text = str(detail).partition("\t")
        getattr(bubble, "learned", lambda kind, text: None)(kind, text)
        return
    enrol = next((look for start, look in ui.ENROL.items() if state.startswith(start)), None)
    pill, text = ui.PILL.get(state) or enrol, detail
    if enrol:
        n = re.search(r"(\d+) of (\d+)", state)
        text = f"{n[1]}/{n[2]}  {detail}" if n else detail
    elif state == "Ready" and detail and bubble.visible and \
            str(detail).replace("\u2019", "'").startswith(ui.READY_NEWS):
        pill = "note"
    if pill and (popup or pill in ("dictating", "finishing", "read", "again", "note", "phone")):
        hint = state == "Listening" and str(detail or "").startswith(("Go ahead", "Let go"))
        bubble.show(pill, None if hint else text)
        if pill in ui.HOLD:
            bubble.hide(ui.HOLD[pill])
    else:
        bubble.hide(900 if state == "Ready" else 0)


# ------------------------------------------------------------------ the window
class Window(QMainWindow):
    """Her window in Qt: the sidebar, and beside it the top and the page you're on (one at a time, as the Tk
    window's), and what runs her: her assistant's thread, its events (notify, drained here), her island's looks
    (TkSide), the timers twice a second. tk: her island's side, or None for none (a preview, a test); start: her
    assistant started too."""

    def __init__(self, tk=None, start=True):
        super().__init__()
        self.tk = tk
        self.controls, self.events = queue.Queue(), queue.Queue()
        self.worker_started = False
        self.mode = settings.get("mode") if settings.get("mode") in ui.MODES else "ptt"
        self.mic = settings.get("mic") or ""
        self.on_top = bool(settings.get("keep_on_top"))
        self.popup = bool(settings.get("popup"))
        self.palette, self.scrim, self.current_tab = None, None, None
        self.side_open = settings.get("sidebar_open") is not False
        self.detail_text, self.state = "Loading speech models\u2026", "Starting"
        self.badge_on = None
        self.frames_n, self.frames_open = 0, False
        self.quitting = False
        self.setWindowTitle(identity.hey())
        if os.path.exists(ui.ICON):
            self.setWindowIcon(QIcon(ui.ICON))
        self._size_window()
        body = QWidget(self)
        row = QHBoxLayout(body)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.side = Sidebar(self)
        row.addWidget(self.side)
        main = QWidget(body)
        col = QVBoxLayout(main)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self.top = TopBar(self)
        col.addWidget(self.top)
        self.stack = QStackedWidget(main)
        self.stack.setStyleSheet(f"QStackedWidget {{ background: {BG}; }}")
        col.addWidget(self.stack, 1)
        row.addWidget(main, 1)
        self.setCentralWidget(body)
        import qtchat
        import qtpages
        self.chat = qtchat.Page(self)
        self.pages = {"home": self.chat}
        self.pages.update(qtpages.build(self))
        for key, _ in ui.TABS:
            self.stack.addWidget(self.pages[key])
        self._shortcuts()
        if not self.side_open:
            self.side.setFixedWidth(0)
            self.side.hide()
        self.select("keys" if ui.missing_secrets() else "home")
        self.top.show_pane(not self.side_open)
        self.show_full_badge()
        self.drain_timer = QTimer(self, interval=50, timeout=self._drain)
        self.drain_timer.start()
        self.tick_timer = QTimer(self, interval=500, timeout=self._tick)
        self.tick_timer.start()
        identity.on_rename(lambda *a: self.events.put(("renamed",)))
        self.status_to("Starting", "Add your API keys to begin" if ui.missing_secrets() else self.detail_text)
        if start and not ui.missing_secrets():
            self.start_worker()

    def _size_window(self):
        screen = QApplication.primaryScreen().availableGeometry()
        w, h = min(ui.W, int(screen.width() * 0.92)), min(ui.H, int(screen.height() * 0.88))
        self.resize(w, h)
        self.move(screen.x() + (screen.width() - w) // 2, screen.y() + max(0, (screen.height() - h) // 2 - 30))
        self.setMinimumSize(940, 600)
        if self.on_top:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

    def _shortcuts(self):
        for keys, fn in (("Ctrl+K", self.open_palette), ("Ctrl+B", lambda: self.toggle_sidebar()),
                         ("Ctrl+Shift+O", self.new_chat), ("Ctrl+Q", self.quit), ("Ctrl+M", self.showMinimized),
                         ("Ctrl+T", lambda: self.toggle_on_top())):
            QShortcut(QKeySequence(keys), self, activated=fn, context=Qt.ShortcutContext.WindowShortcut)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.scrim is not None:
            self.scrim.setGeometry(self.rect())
        if self.palette is not None:
            self.palette.place()

    # ------------------------------------------------------------------ pages
    def select(self, key):
        """The page key in the window, the tab lit and the top saying what it is."""
        if key not in self.pages:
            return
        page = self.pages[key]
        self.current_tab = key
        self.stack.setCurrentWidget(page)
        getattr(page, "shown", lambda: None)()
        self.side.select(key)
        self.lay_head()

    def lay_head(self):
        on_chat = self.current_tab == "home"
        page = self.pages.get(self.current_tab)
        words = ("Expand frames" + (f" \u00b7 {self.frames_n}" if self.frames_n else "")) if on_chat else \
            identity.named(getattr(page, "head", ("", ""))[0] or "")
        self.top.head.set(words, on_chat, self.frames_open)

    def frames_click(self):
        if self.current_tab == "home":
            self.chat.toggle_frames()

    def focus_box(self):
        if self.current_tab == "home":
            self.chat.focus_box()

    # ------------------------------------------------------------------ the sidebar
    def toggle_sidebar(self, open_=None):
        """The sidebar slid away (the page has the window; the top's panel icon brings it back) or back, kept
        (settings sidebar_open): 260 ms coming, 220 going, at once with Windows' animations off."""
        open_ = (not self.side_open) if open_ is None else bool(open_)
        if open_ == self.side_open:
            return
        self.side_open = open_
        settings.put("sidebar_open", open_)
        side = self.side
        self.top.show_pane(not open_)
        if not kit.animations_on():
            side.setFixedWidth(SIDE_W if open_ else 0)
            side.setVisible(open_)
            return
        start = side.width() if side.isVisible() else 0
        side.show()
        anim = QVariantAnimation(self, duration=260 if open_ else 220, easingCurve=QEasingCurve.Type.OutCubic)
        anim.setStartValue(float(start))
        anim.setEndValue(float(SIDE_W if open_ else 0))
        anim.valueChanged.connect(lambda v: side.setFixedWidth(round(v)))
        anim.finished.connect(lambda: side.setVisible(open_))
        self._side_anim = anim
        anim.start()

    def set_sidebar(self, name):
        settings.put("sidebar", name if name in ui.SIDES else "dark")
        self.side.set_colours(name)

    def you_menu(self):
        """Your card's menu, opening up from it: how she listens, Full access off while it's on, Settings, the classic
        window and Quit."""
        menu = styled_menu(self)
        for mode in ui.MODES:
            act = menu.addAction(identity.named(ui.MODE_LABELS[mode]))
            act.setCheckable(True)
            act.setChecked(mode == self.mode)
            act.triggered.connect(lambda _=False, m=mode: self.set_mode(m))
        menu.addSeparator()
        if settings.get("full_access"):
            menu.addAction("Turn Full access off").triggered.connect(lambda: self.set_full_access(False))
        menu.addAction("Settings").triggered.connect(lambda: self.select("settings"))
        menu.addAction("Use the classic window").triggered.connect(lambda: self.use_window("tk"))
        menu.addAction(identity.named("Quit Hey Harry")).triggered.connect(self.quit)
        you = self.side.you
        at = you.mapToGlobal(QPoint(0, 0))
        menu.exec(QPoint(at.x(), at.y() - menu.sizeHint().height() - 6))

    # ------------------------------------------------------------------ chats
    def new_chat(self):
        self.select("home")
        self.chat.new_chat()
        self.side.lay_chats()

    def open_chat(self, cid):
        if cid is None:
            return
        self.select("home")
        self.chat.open_chat(cid)
        self.side.lay_chats()

    def delete_chat(self, cid):
        if cid is None:
            return
        self.chat.delete_chat(cid)
        self.side.lay_chats()

    # ------------------------------------------------------------------ quick actions
    def open_palette(self):
        if self.palette is not None:
            self.palette.close_()
            return
        self.scrim = Scrim(self)
        self.palette = Palette(self)

    def drop_scrim(self):
        if self.scrim is not None:
            self.scrim.hide()
            self.scrim.deleteLater()
            self.scrim = None

    def quick_actions(self):
        """What her quick actions offer, as (icon, its name, its kind, what does it), as the Tk window's: every tab,
        each part of the long pages, a new chat and each of yours, and what the window itself does."""
        titles, out = dict(ui.TABS), []
        for _, keys in ui.NAV:
            out += [(ui.ICONS[key], titles[key], "Go to", lambda key=key: self.select(key)) for key in keys]
        for _, keys in ui.NAV:
            for key in keys:
                for name, go in getattr(self.pages.get(key), "parts", lambda: [])():
                    out.append((ui.ICONS[key], f"{titles[key]}: {name}", "Section",
                                lambda key=key, go=go: (self.select(key), QTimer.singleShot(120, go))))
        other = ui.MODES[1 - ui.MODES.index(self.mode)]
        listen = {"wake": "Listen for \u201cHey Harry\u201d", "ptt": "Hold right Alt to talk"}[other]
        dark = self.side.colours["bg"] == ui.SIDES["dark"][0]
        out.append(("\ue70f", "New chat", "Chat", self.new_chat))
        out += [("\ue8bd", text, "Chat", lambda cid=cid: self.open_chat(cid)) for cid, text, _ in self.chat.listed()]
        out += [("\ue720", identity.named(listen), "Mode", lambda: self.set_mode(other)),
                ("\ue718", "Stop keeping this window on top" if self.on_top else "Keep this window on top", "Window",
                 self.toggle_on_top),
                ("\ue89f", "Hide the sidebar" if self.side_open else "Show the sidebar", "Window",
                 lambda: self.toggle_sidebar()),
                ("\ue790", "Make the sidebar light" if dark else "Make the sidebar dark", "Window",
                 lambda: self.set_sidebar("light" if dark else "dark")),
                ("\ue7f4", "Use the classic window", "Window", lambda: self.use_window("tk")),
                ("\ue921", "Minimise to the taskbar", "Window", self.showMinimized),
                ("\ue7e8", identity.named("Quit Hey Harry"), "Window", self.quit)]
        return out

    # ------------------------------------------------------------------ her state
    def show_full_badge(self):
        on = bool(settings.get("full_access"))
        if on != self.badge_on:
            self.badge_on = on
            self.top.show_full(on)

    def set_full_access(self, on, hours=0):
        """Full access on (only after a yes) or off (from anywhere). True if it's as asked."""
        if on:
            ok = QMessageBox.question(
                self, "Turn on Full access?",
                "Harry will send the messages you ask for and install the apps you ask for without asking first.\n\n"
                "She'll still ask before deleting, paying or buying, and she never types passwords.\n\n"
                "Only for what you say with her name.") == QMessageBox.StandardButton.Yes
            if not ok:
                return False
        settings.put("full_access", bool(on))
        settings.put("full_access_until", time.time() + hours * 3600 if on and hours else 0)
        self.show_full_badge()
        getattr(self.pages.get("settings"), "full_changed", lambda on: None)(bool(on))
        return True

    def status_to(self, state, detail=None):
        """Her state at the top: its dot in its colour, breathing while she's at something; what she's at after it
        only while she starts up or something's wrong."""
        if detail is not None:
            self.detail_text = " ".join(str(detail).split())
        self.state = state
        enrol = next((look for start, look in ui.ENROL.items() if state.startswith(start)), None)
        colour = ui.STATUS_COLORS.get(state, ui.STATUS_COLORS["Listening"] if enrol else TEXT)
        detail = self.detail_text if state in ("Starting", "Something went wrong") else ""
        self.top.status.set_state(state, colour, state in ui.BUSY or bool(enrol), detail)

    def set_mode(self, mode):
        siri = sys.modules.get("siri")
        if mode == self.mode and not (siri is not None and hasattr(siri, "paused") and siri.paused()):
            return
        self.mode = mode
        settings.put("mode", mode)
        self.controls.put(("mode", mode))

    def toggle_on_top(self, value=None):
        self.on_top = (not self.on_top) if value is None else bool(value)
        settings.put("keep_on_top", self.on_top)
        shown = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.on_top)
        if shown:
            self.show()
        check = getattr(self.pages.get("settings"), "on_top_check", None)
        if check is not None and check.isChecked() != self.on_top:  # Ctrl+T: Settings' own box says so too
            check.blockSignals(True)
            check.setChecked(self.on_top)
            check.blockSignals(False)

    def use_window(self, which):
        """Her window as Tk's again (or Qt's): kept in settings, and she starts again in it."""
        settings.put("window", which)
        self.quit(restart=True)

    # ------------------------------------------------------------------ her assistant
    def start_worker(self):
        if self.worker_started:
            return
        self.worker_started = True
        threading.Thread(target=self._run_assistant, name="harry-assistant", daemon=True).start()

    def _run_assistant(self):
        try:
            from siri import run_voice_assistant
            run_voice_assistant(self.notify, self.controls, self.mode, self.mic)
        except Exception as exc:
            print(f"assistant stopped: {exc}")
            traceback.print_exc()
            self.notify("Something went wrong", str(exc))

    def notify(self, state, detail=""):
        """From her assistant's threads: Qt is only touched on its own thread, in _drain."""
        self.events.put(("status", state, detail))

    def _drain(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                return
            try:
                if event[0] == "status":
                    self.set_status(event[1], event[2])
                elif event[0] == "renamed":
                    self.setWindowTitle(identity.hey())
                else:  # what a page's thread found: the models read, a voice played, the apps that notify
                    for page in self.pages.values():
                        getattr(page, "on_event", lambda e: None)(event)
            except Exception:
                traceback.print_exc()

    def set_status(self, state, detail):
        self.chat.her_event(state, detail)
        if state in ("Box words", "Context"):
            return
        if state == "Type":  # right Alt tapped twice: the typing box at the top of the screen, else the chat's
            if self.tk is not None and self.tk.bubble is not None and hasattr(self.tk.bubble, "ask"):
                self.tk.call(lambda: self.tk.bubble.ask("", under=False))
            else:
                self.select("home")
                self.showNormal()
                self.raise_()
                self.activateWindow()
                self.chat.focus_box()
            return
        if self.tk is not None:
            popup = self.popup
            self.tk.call(lambda: island_status(self.tk.bubble, popup, state, detail))
        if state in ("Heard", "Mood", "Step", "Asked", "Learned"):
            return
        self.status_to(state, detail)
        if state == "Phone" and detail:
            getattr(self.pages.get("settings"), "phone_status", lambda d: None)(detail)

    def _tick(self):
        siri = sys.modules.get("siri")
        timers = siri.timer_snapshot()[:3] if hasattr(siri, "timer_snapshot") else []
        self.side.show_timers(timers)
        for page in self.pages.values():
            getattr(page, "tick", lambda: None)()
        self.show_full_badge()

    # ------------------------------------------------------------------ going
    def closeEvent(self, e):
        """Closing keeps her listening: the window goes to the taskbar, which brings it back (Ctrl+Q quits)."""
        if self.quitting:
            e.accept()
            return
        e.ignore()
        self.showMinimized()

    def quit(self, restart=False):
        self.quitting = True
        try:
            self.chat.save()
        except Exception as exc:
            print(f"  couldn't keep the chat: {exc!r}")
        if self.tk is not None:
            self.tk.close()
        sys.stdout.flush()
        if restart:
            ui.start_again()
        QApplication.instance().quit()


def styled_menu(parent):
    """A menu in her window's look: white, rounded, a hairline round it, her type, a soft grey row under the mouse."""
    menu = QMenu(parent)
    menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint |
                        Qt.WindowType.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    menu.setFont(kit.font(14))
    menu.setStyleSheet(f"""
        QMenu {{ background: #ffffff; border: 1px solid #e7e7ea; border-radius: 12px; padding: 6px; }}
        QMenu::item {{ color: {TEXT}; padding: 7px 14px 7px 30px; border-radius: 8px; }}
        QMenu::item:selected {{ background: #f3f4f6; }}
        QMenu::indicator {{ width: 14px; height: 14px; left: 9px; }}
        QMenu::separator {{ height: 1px; background: #f0f0f2; margin: 5px 8px; }}""")
    return menu


def run():
    """Her window in Qt, with her island's side on its own thread; till she's quit."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(identity.hey())
    app.setQuitOnLastWindowClosed(False)  # closing the window keeps her listening
    kit.load_type()
    app.setFont(kit.font(14))
    # the window first, with nothing of hers started: if it won't build, this raises and assistant_ui.run_app opens
    # the classic window instead, with no island already up from here
    window = Window(None, start=False)
    ui.gc_here(lambda ms, fn: QTimer.singleShot(ms, fn))  # what Python collects is let go here, on Qt's thread
    window.tk = TkSide()
    window.tk.ready.wait(5)  # her island built before her assistant starts, as the classic window has it
    if not ui.missing_secrets():
        window.start_worker()
    if "--startup" in sys.argv:  # started as you signed in: on the taskbar
        window.showMinimized()
    else:
        window.show()
        window.raise_()
        window.activateWindow()
    app.exec()
    sys.stdout.flush()
    os._exit(0)


def preview(path, ms=900, size=(1240, 800), setup=None):
    """A picture of the window as Qt draws it, ms after it opens, saved at path, without her assistant or island.
    setup(window): anything to put in it first. Its size."""
    app = QApplication.instance() or QApplication(sys.argv)
    kit.load_type()
    app.setFont(kit.font(14))
    window = Window(None, start=False)
    window.resize(*size)
    if setup is not None:
        setup(window)
    window.show()
    out = {}

    def shoot():
        image = window.grab()
        image.save(path)
        out["size"] = (image.width(), image.height())
        window.quitting = True
        window.close()
        app.quit()
    QTimer.singleShot(ms, shoot)
    app.exec()
    return out.get("size")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--preview":
        print(preview(sys.argv[2]))
    else:
        run()
