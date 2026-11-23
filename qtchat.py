"""The chat in her Qt window (qtwindow, 22 November 2026, the owner's choice of Qt over Tk): what chat.Page shows,
drawn by Qt. What's said is chat.Thread's, your chats chat.Chats' (the same chats.json the Tk window keeps), and
everything that decides what's shown is chat's own: lines_of, anchors, sources, turns, meeting_for, context_lines.

The thread is a column of turns, each built once and again only when it changes (TurnView): your words in a soft
grey bubble at the right; her words by her face, the facts in them in semibold, a longer answer a sentence a line,
the sources it drew on as small pills at its very end (an inline object in its text, PillObject); a "Thought for 9s"
row over them that opens and shuts her steps; the meeting it's about as a card. Under them, while she works, her face
with three dots pulsing and a light sweeping across what she's doing (LiveLine).

The box is Hedwig's (Box): one grey rounded field growing a line at a time, the paperclip and her badge at its left,
the waveform and Send at its right; files as chips over the words; dictation opening the row into Cancel, a live
strip and Done; a ring of the accent while it has the keyboard, travelling round it while she's busy.

The frames (Frames) are what her turn looked up, each drawn as the app it came from, in the thread after the turn
that found them; the rail (Rail) what she made or holds for you, down the right."""
import json
import math
import os
import re
import sys
import time

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QRect, QRectF, QSize, QSizeF, Qt, QTimer,
                            QVariantAnimation)
from PySide6.QtGui import (QBrush, QConicalGradient, QFontMetricsF, QImage, QLinearGradient, QPainter, QPainterPath,
                           QPalette, QPen, QPolygonF, QPyTextObject, QRadialGradient, QTextBlockFormat,
                           QTextCharFormat, QTextCursor, QTextFormat)
from PySide6.QtWidgets import (QAbstractButton, QFileDialog, QFrame, QHBoxLayout, QLabel, QLayout, QPlainTextEdit,
                               QScrollArea, QSizePolicy, QTextBrowser, QVBoxLayout, QWidget)

import chat
import chatfx
import identity
import qtkit as kit
import settings
from chat import (BUBBLE, CARD, CHIP, CHIP_INK, DIVIDER, FAILED_BG, FIELD, GLYPHS, SOURCE, SOURCE_INK, STEP_DONE,
                  STEP_DONE_INK, TINTS)
from qtkit import BG, BLUE, ERROR, FAINT, MUTED, TEXT, qc

ACCENT = BLUE
INDENT = 38  # her words start clear of her face (14 px tall, about 29 wide), and so does every line of hers after
WIDE, NARROW, RAIL_W = 640, 820, 250  # the thread's most; under this the rail goes; the rail's width
PILL = int(QTextFormat.ObjectTypes.UserObject.value) + 1  # a source's pill, an object in her answer's text
P_NAME = int(QTextFormat.Property.UserProperty.value) + 1


class Fonts:
    """The chat's type, made once QApplication is up: the Tk window's sizes (assistant_ui._setup_styles)."""

    def __init__(self):
        self.chat, self.chat_bold = kit.font(15), kit.font(15, "semibold")
        self.body, self.bold, self.h2 = kit.font(14), kit.font(14, "semibold"), kit.font(15, "semibold")
        self.small, self.badge = kit.font(12.5), kit.font(12, "medium")
        self.tiny, self.tiny_bold = kit.font(11.2), kit.font(11.2, "semibold")
        self.source = kit.font(10.6, "medium")
        self.value, self.mono = kit.font(28), kit.font(13, family="Consolas")
        self.icon, self.icon_small, self.fold = kit.icon_font(15), kit.icon_font(12), kit.icon_font(9)


F = None  # Fonts, once made (fonts())


def fonts():
    global F
    if F is None:
        F = Fonts()
    return F


# ------------------------------------------------------------------ small parts
class Flow(QLayout):
    """Widgets in a row that wraps, as words do: her steps' chips."""

    def __init__(self, parent=None, h=6, v=6):
        super().__init__(parent)
        self.items, self.h, self.v = [], h, v
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, i):
        return self.items[i] if 0 <= i < len(self.items) else None

    def takeAt(self, i):
        return self.items.pop(i) if 0 <= i < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._lay(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._lay(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for item in self.items:
            s = s.expandedTo(item.minimumSize())
        return s

    def _lay(self, rect, test):
        x, y, line = rect.x(), rect.y(), 0
        for item in self.items:
            size = item.sizeHint()
            if x > rect.x() and x + size.width() > rect.right() + 1:
                x, y, line = rect.x(), y + line + self.v, 0
            if not test:
                item.setGeometry(QRect(QPoint(x, y), size))
            x += size.width() + self.h
            line = max(line, size.height())
        return y + line - rect.y()


class YouBubble(QWidget):
    """Your words on a soft grey bubble at the right, its top right corner small (chat.bubble_ppm), as wide as they
    need up to the room it's given (set_room)."""
    PAD_X, PAD_Y, R = 13, 8, 14

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text
        self.room = 460
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._size()

    def set_room(self, room):
        room = max(140, int(room))
        if room != self.room:
            self.room = room
            self._size()

    def _size(self):
        f = fonts().chat
        r = QFontMetricsF(f).boundingRect(QRectF(0, 0, self.room - 2 * self.PAD_X, 1e6),
                                          int(Qt.TextFlag.TextWordWrap), self.text)
        self.text_rect = QRectF(self.PAD_X, self.PAD_Y, math.ceil(r.width()) + 1, math.ceil(r.height()))
        self.setFixedSize(int(self.text_rect.width() + 2 * self.PAD_X), int(self.text_rect.height() + 2 * self.PAD_Y))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h, r, s = self.width(), self.height(), self.R, 4.0
        path = QPainterPath()
        path.moveTo(r, 0)
        path.lineTo(w - s, 0)
        path.quadTo(w, 0, w, s)
        path.lineTo(w, h - r)
        path.quadTo(w, h, w - r, h)
        path.lineTo(r, h)
        path.quadTo(0, h, 0, h - r)
        path.lineTo(0, r)
        path.quadTo(0, 0, r, 0)
        p.fillPath(path, qc(BUBBLE))
        p.setFont(fonts().chat)
        p.setPen(qc(TEXT))
        p.drawText(self.text_rect, int(Qt.TextFlag.TextWordWrap), self.text)


class FileChip(QAbstractButton):
    """A file you attached, in the thread: its mark, its name and its size on a soft card; a click opens it, and one
    that's gone from where it was says so."""

    def __init__(self, path, parent=None):
        super().__init__(parent)
        import attach
        self.path = path
        name = os.path.basename(path)
        self.name = name if len(name) <= 30 else name[:19] + "\u2026" + name[-8:]
        try:
            self.size, self.there = attach.size_words(os.path.getsize(path)), True
        except OSError:
            self.size, self.there = "gone", False
        self.mark = attach.icon(path)
        f = fonts()
        self.setFixedSize(int(max(kit.width_of(f.badge, self.name), kit.width_of(f.small, self.size)) + 52), 38)
        if self.there:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.clicked.connect(lambda: os.startfile(self.path))
        self.setToolTip(path)

    def paintEvent(self, _):
        f = fonts()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(kit.mix(CHIP, "#000000", 0.03) if self.underMouse() and self.there else CHIP))
        p.drawRoundedRect(QRectF(self.rect()), 10, 10)
        p.setFont(f.icon)
        p.setPen(qc(ACCENT))
        p.drawText(QRectF(12, 0, 22, 38), Qt.AlignmentFlag.AlignVCenter, self.mark)
        p.setFont(f.badge)
        p.setPen(qc(TEXT))
        p.drawText(QRectF(38, 4, self.width() - 44, 17), Qt.AlignmentFlag.AlignVCenter, self.name)
        p.setFont(f.small)
        p.setPen(qc(MUTED))
        p.drawText(QRectF(38, 19, self.width() - 44, 16), Qt.AlignmentFlag.AlignVCenter, self.size)

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


class StepChip(QWidget):
    """A step of hers as a small chip: ticked and faintly green once it went through, a dot while it's going, red
    with a cross if it failed."""

    def __init__(self, step, parent=None):
        super().__init__(parent)
        f = fonts()
        self.state = step.get("state") or "live"
        self.failed, self.done = self.state == "failed", self.state == "done"
        self.text = kit.fit(f.badge, step.get("text") or "", 420)
        self.setFixedSize(int(8 + 11 + kit.width_of(f.badge, self.text) + 8 + 0.999), 22)
        self.setToolTip(step.get("text") or "")

    def paintEvent(self, _):
        f = fonts()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill = FAILED_BG if self.failed else STEP_DONE if self.done else CHIP
        ink = ERROR if self.failed else STEP_DONE_INK if self.done else CHIP_INK
        mark_ink = ERROR if self.failed else CHIP_INK
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(fill))
        p.drawRoundedRect(QRectF(self.rect()), 9, 9)
        mid = self.height() / 2
        glyph = GLYPHS.get(self.state, "dot")
        if glyph == "dot":
            p.setBrush(qc(mark_ink))
            p.drawEllipse(QRectF(8, mid - 2.5, 5, 5))
        else:
            p.setFont(f.fold)
            p.setPen(qc(mark_ink))
            p.drawText(QRectF(7, 0, 12, self.height()), Qt.AlignmentFlag.AlignVCenter, glyph)
        p.setFont(f.badge)
        p.setPen(qc(ink))
        p.drawText(QRectF(19, 0, self.width() - 19, self.height()), Qt.AlignmentFlag.AlignVCenter, self.text)


class PillObject(QPyTextObject):
    """A source her answer drew on, as a small pill right at its end, in its own pale tint (chat.TINTS): an object in
    her answer's text, so it wraps with the words as a word does."""

    def intrinsicSize(self, doc, pos, fmt):
        name = str(fmt.property(P_NAME) or "")
        return QSizeF(kit.width_of(fonts().source, name) + 12 + 4, 17)

    def drawObject(self, painter, rect, doc, pos, fmt):
        name = str(fmt.property(P_NAME) or "")
        fill, ink = TINTS.get(name, (SOURCE, SOURCE_INK))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(rect.x() + 2, rect.y(), rect.width() - 4, rect.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qc(fill))
        painter.drawRoundedRect(r, 4, 4)
        painter.setFont(fonts().source)
        painter.setPen(qc(ink))
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, name)
        painter.restore()


class AnswerText(QTextBrowser):
    """Her words, laid out to scan: the facts in her semibold, a longer answer a sentence a line with room over each,
    and the sources at the very end as pills. Selectable, to copy; as tall as its words, never scrolling itself."""

    def __init__(self, lines, found=(), colour=TEXT, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setOpenExternalLinks(True)
        self.setStyleSheet("QTextBrowser { background: transparent; border: none; selection-background-color: "
                           "#d6e4fd; selection-color: #111827; }")
        self.viewport().setAutoFillBackground(False)
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse |
                                     Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        doc = self.document()
        doc.setDocumentMargin(0)
        doc.setDefaultFont(fonts().chat)
        self.pills = PillObject(self)
        doc.documentLayout().registerHandler(PILL, self.pills)
        self._fill(lines, found, colour)
        doc.documentLayout().documentSizeChanged.connect(lambda *_: self._fit())

    def _fill(self, lines, found, colour):
        f = fonts()
        cur = QTextCursor(self.document())
        plain, bold = QTextCharFormat(), QTextCharFormat()
        plain.setFont(f.chat)
        plain.setForeground(qc(colour))
        bold.setFont(f.chat_bold)
        bold.setForeground(qc(TEXT))
        for n, line in enumerate(lines):
            block = QTextBlockFormat()
            block.setLineHeight(22.0, int(QTextBlockFormat.LineHeightTypes.FixedHeight.value))
            if n:
                block.setTopMargin(11)  # each single-idea line with room over it
            if n == 0:
                cur.setBlockFormat(block)
            else:
                cur.insertBlock(block)
            at = 0
            for a, z in chat.anchors(line):
                cur.insertText(line[at:a], plain)
                cur.insertText(line[a:z], bold)
                at = z
            cur.insertText(line[at:], plain)
        if found:
            cur.insertText(" ", plain)
            for name, _mark in found:
                pill = QTextCharFormat()
                pill.setObjectType(PILL)
                pill.setProperty(P_NAME, name)
                pill.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignMiddle)
                cur.insertText("\ufffc", pill)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.document().setTextWidth(self.viewport().width())
        self._fit()

    def _fit(self):
        h = math.ceil(self.document().size().height())
        if h != self.height():
            self.setFixedHeight(max(1, h))

    def wheelEvent(self, e):
        e.ignore()  # the thread scrolls, never this


class TookRow(QAbstractButton):
    """"Thought for 9s \u203a" over her answer: the reasoning accordion the AI chats have, opening and shutting her
    steps; plain words when there are none."""

    def __init__(self, words, steps, opened, parent=None):
        super().__init__(parent)
        self.words, self.steps, self.opened = words, steps, opened
        f = fonts()
        self.setFixedSize(int(kit.width_of(f.small, words) + (20 if steps else 2)), 20)
        if steps:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus if steps else Qt.FocusPolicy.NoFocus)

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _):
        f = fonts()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ink = qc(TEXT if self.steps and self.underMouse() else MUTED)
        p.setFont(f.small)
        p.setPen(ink)
        p.drawText(QRectF(0, 0, self.width(), self.height()), Qt.AlignmentFlag.AlignVCenter, self.words)
        if self.steps:
            x = kit.width_of(f.small, self.words) + 6
            p.setFont(f.fold)
            p.drawText(QRectF(x, 1, 14, self.height()), Qt.AlignmentFlag.AlignVCenter,
                       "\ue70d" if self.opened else "\ue76c")


class MeetingCard(QWidget):
    """The meeting her answer is about, as a card in the thread: its name, when, where, and Join when it has a link
    to one. From the calendars on this PC only (agenda.kept)."""

    def __init__(self, event, now, parent=None):
        super().__init__(parent)
        start, end = event["start"], event.get("end") or event["start"]
        clock_of = lambda d: d.strftime("%I:%M%p").lstrip("0").replace(":00", "").lower()  # noqa: E731
        day = "Today" if start.date() == now.date() else "Tomorrow" if start.date() > now.date() else ""
        self.when = " \u00b7 ".join(p for p in (day, f"{clock_of(start)}\u2013{clock_of(end)}") if p)
        link = chat.LINK.search(event.get("where") or "")
        self.where = (event.get("where") or "") if not link else ""
        self.url = None
        if link:
            self.url = link.group() if link.group().lower().startswith("http") else "https://" + link.group()
        self.title = event.get("title") or "Meeting"
        self.setFixedHeight(52)
        self.setMouseTracking(True)
        self.join_rect = QRectF()

    def paintEvent(self, _):
        f = fonts()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(CARD))
        p.drawRoundedRect(QRectF(0, 0, w, h), 12, 12)
        p.setBrush(qc("#ffffff"))
        p.drawRoundedRect(QRectF(12, h / 2 - 15, 30, 30), 7, 7)
        p.setFont(f.icon_small)
        p.setPen(qc("#4f7fe0"))
        p.drawText(QRectF(12, h / 2 - 15, 30, 30), Qt.AlignmentFlag.AlignCenter, "\ue787")
        room = w - 56 - (80 if self.url else 12)
        p.setFont(f.badge)
        p.setPen(qc(TEXT))
        p.drawText(QRectF(54, 8, room, 18), Qt.AlignmentFlag.AlignVCenter, kit.fit(f.badge, self.title, room))
        p.setFont(f.small)
        p.setPen(qc(MUTED))
        more = self.when + (f" \u00b7 {self.where}" if self.where else "")
        p.drawText(QRectF(54, 26, room, 18), Qt.AlignmentFlag.AlignVCenter, kit.fit(f.small, more, room))
        if self.url:
            jw = kit.width_of(f.badge, "Join") + 36
            self.join_rect = QRectF(w - 12 - jw, h / 2 - 13, jw, 26)
            over = self.join_rect.contains(self.mapFromGlobal(self.cursor().pos()).toPointF())
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc("#f9fafb" if over else "#ffffff"))
            p.drawRoundedRect(self.join_rect, 8, 8)
            p.setFont(f.fold)
            p.setPen(qc(TEXT))
            p.drawText(QRectF(self.join_rect.x() + 10, self.join_rect.y(), 14, 26), Qt.AlignmentFlag.AlignVCenter,
                       "\ue714")
            p.setFont(f.badge)
            p.drawText(QRectF(self.join_rect.x() + 24, self.join_rect.y(), jw - 30, 26),
                       Qt.AlignmentFlag.AlignVCenter, "Join")

    def mouseMoveEvent(self, e):
        on = self.url and self.join_rect.contains(e.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if on else Qt.CursorShape.ArrowCursor)
        self.update()

    def mousePressEvent(self, e):
        if self.url and self.join_rect.contains(e.position()):
            import webbrowser
            webbrowser.open(self.url)


def meeting_card(answer):
    """The meeting card for her answer, or None if there's no meeting today or the calendar can't be read."""
    import datetime as dt
    try:
        import agenda
        now = dt.datetime.now()
        event = chat.meeting_for(answer, agenda.kept(now - dt.timedelta(hours=1), now + dt.timedelta(hours=16)), now)
    except Exception as exc:
        print(f"  chat: couldn't read the calendar for its card ({exc!r})")
        return None
    return MeetingCard(event, now) if event is not None else None


class LiveLine(QWidget):
    """What she's at now, by her face: three dots pulsing in turn (ui-ux-pro-max's AI-native typing indicator) and her
    words with a soft light sweeping across them (the AI chats' text shimmer), with its seconds once it's a second."""

    def __init__(self, page, parent=None):
        super().__init__(parent)
        self.page = page
        self.setFixedHeight(40)  # 16 over it, the line 24
        self.timer = QTimer(self, interval=40, timeout=self.update)

    def showEvent(self, e):
        self.timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def paintEvent(self, _):
        f = fonts()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(0, 16)
        h = self.height() - 16
        x = 1.0
        if self.page.face is not None:
            pm = self.page.face
            fh = pm.height() / pm.devicePixelRatio()
            p.drawPixmap(QPointF(x, (h - fh) / 2), pm)
            x = INDENT
        now = time.time()
        moving = kit.animations_on()
        for i in range(3):
            glow = 0.5 + 0.5 * math.sin(now * 2 * math.pi * 1.1 - i * 0.9) if moving else 0.6
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(kit.mix("#c7d2fe", "#6366f1", glow)))
            p.drawEllipse(QRectF(x + i * 8, h / 2 - 2.5, 5, 5))
        x += 32
        words = self.page.live_words()
        width = kit.width_of(f.chat, words)
        base, lit = kit.mix(MUTED, BG, 0.2), TEXT
        if moving:
            period, band = 1.6, max(40.0, width * 0.25)
            centre = -band + (now % period) / period * (width + 2 * band)
            g = QLinearGradient(x + centre - band, 0, x + centre + band, 0)
            g.setColorAt(0.0, qc(base))
            g.setColorAt(0.5, qc(kit.mix(base, lit, 0.85)))
            g.setColorAt(1.0, qc(base))
            p.setPen(QPen(QBrush(g), 1))
        else:
            p.setPen(qc(base))
        p.setFont(f.chat)
        p.drawText(QRectF(x, 0, self.width() - x, h), Qt.AlignmentFlag.AlignVCenter, words)


# ------------------------------------------------------------------ a turn
class TurnView(QWidget):
    """One turn of the thread: your words (and what you attached) at the right, then hers by her face, her steps,
    her notes, the sources and the meeting card, and the frames if they're from this turn."""

    def __init__(self, page, items, turn, frames=None, parent=None):
        super().__init__(parent)
        self.page, self.bubbles = page, []
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        all_items = page.thread.items
        idxs = list(range(turn["start"], turn["end"]))
        answered = turn["first"] is not None
        her_box, her_col, face_put = None, None, False
        steps_flow = None
        for i in idxs:
            item = all_items[i]
            kind = item["kind"]
            if kind == "you":
                if item.get("files"):
                    col.addSpacing(26)
                    row = QHBoxLayout()
                    row.setSpacing(6)
                    row.addStretch(1)
                    for path in item["files"]:
                        row.addWidget(FileChip(path))
                    col.addLayout(row)
                if item["text"]:
                    col.addSpacing(6 if item.get("files") else 26)
                    bubble = YouBubble(item["text"])
                    self.bubbles.append(bubble)
                    row = QHBoxLayout()
                    row.addStretch(1)
                    row.addWidget(bubble)
                    col.addLayout(row)
                col.addSpacing(2)
                continue
            if her_box is None:  # everything of hers in the turn: a column clear of her face
                her_box = QHBoxLayout()
                her_box.setSpacing(0)
                self.face_col = QVBoxLayout()
                self.face_col.setContentsMargins(0, 0, 0, 0)
                face_holder = QWidget()
                face_holder.setFixedWidth(INDENT)
                face_holder.setLayout(self.face_col)
                her_box.addWidget(face_holder, 0, Qt.AlignmentFlag.AlignTop)
                her_col = QVBoxLayout()
                her_col.setSpacing(0)
                her_col.setContentsMargins(0, 0, 0, 0)
                her_box.addLayout(her_col, 1)
                col.addLayout(her_box)
            if kind == "step":
                if answered:
                    continue  # under its "Thought for" row (her first words, below)
                if steps_flow is None:
                    her_col.addSpacing(8)
                    holder = QWidget()
                    steps_flow = Flow(holder, 6, 4)
                    her_col.addWidget(holder)
                steps_flow.addWidget(StepChip(item))
                continue
            steps_flow = None
            if kind == "her":
                first = not face_put
                if first:
                    self._her_first(her_col, item, turn, i)
                    face_put = True
                else:
                    her_col.addSpacing(6)
                found = chat.sources([all_items[s] for s in turn["steps"]]) if i == turn["last"] else []
                text = AnswerText(chat.lines_of(item["text"]), found)
                her_col.addWidget(text)
                if any(name == "Calendar" for name, _ in found):
                    words = " ".join(all_items[k]["text"] for k in range(turn["first"], i + 1)
                                     if all_items[k]["kind"] == "her")
                    card = meeting_card(words)
                    if card is not None:
                        her_col.addSpacing(10)
                        her_col.addWidget(card)
                        her_col.addSpacing(4)
            else:  # a note: why she let it go, what she learned, something wrong
                her_col.addSpacing(8)
                note = QLabel(item["text"])
                note.setWordWrap(True)
                note.setFont(fonts().small)
                note.setStyleSheet(f"color: {ERROR if item['state'] == 'failed' else MUTED}; background: transparent;")
                note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                her_col.addWidget(note)
        if frames is not None:
            col.addSpacing(18)
            col.addWidget(frames)
            col.addSpacing(6)

    def _her_first(self, her_col, item, turn, idx):
        """Her face by her first words of the turn; a "Thought for" row over them first when she thought a second or
        more or took steps for it, opening her steps under it, and a hairline under that over a longer answer."""
        page, items = self.page, self.page.thread.items
        took = item.get("took") or 0
        steps = [items[i] for i in turn["steps"]]
        head = took or steps
        her_col.addSpacing(16)
        if page.face is not None:
            face = QLabel()
            face.setPixmap(page.face)
            face.setFixedHeight(20 if head else 21)
            face.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            face.setStyleSheet("background: transparent;")
            self.face_col.addSpacing(16)
            self.face_col.addWidget(face)
            self.face_col.addStretch(1)
        if not head:
            return
        key = id(items[turn["steps"][0]]) if steps else None
        opened = key in page.opened
        words = f"Thought for {took}s" if took else f"Took {len(steps)} step{'s' if len(steps) > 1 else ''}"
        row = TookRow(words, bool(steps), opened)
        if steps:
            row.clicked.connect(lambda: page.toggle_steps(key))
        her_col.addWidget(row)
        if opened:
            her_col.addSpacing(8)
            holder = QWidget()
            flow = Flow(holder, 6, 4)
            for step in steps:
                flow.addWidget(StepChip(step))
            her_col.addWidget(holder)
        long_answer = len(chat.lines_of(item["text"])) > 1 or took >= 3 or len(steps) >= 2
        if long_answer:  # a hairline over an answer worth setting apart, not over every short one
            her_col.addSpacing(8)
            line = QFrame()
            line.setFixedHeight(1)
            line.setStyleSheet(f"background: {DIVIDER}; border: none;")
            her_col.addWidget(line)
            her_col.addSpacing(2)
        her_col.addSpacing(6)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        for bubble in self.bubbles:
            bubble.set_room(self.width() * 0.72)


# ------------------------------------------------------------------ the frames
class Frames(QWidget):
    """The context frames (chat.Bento in Qt): what each look-up of her turn found, a small window each, drawn as the
    app it came from; what she saw on the screen wide across the top, the rest two by two. In the thread after the
    turn that found them."""
    MOST, TOP, ROW, BIG = 5, 236, 214, 520

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.found, self.big, self.turn = [], None, 0
        self.cards = {}
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def add(self, detail, turn):
        """One look-up's findings (the "Context" event's JSON) as a frame. True if one came."""
        try:
            got = json.loads(detail)
        except (TypeError, ValueError):
            return False
        label, do = str(got.get("label") or ""), str(got.get("do") or "")
        name, mark = chat.app_of(label, do)
        found = got.get("found")
        if do == "read" and isinstance(found, dict):
            page = found.get("page") if isinstance(found.get("page"), dict) else {}
            app_name = chat.site_app(page.get("url") or found.get("read"))
            known = any(app_name == n for _, n in chat.DOMAIN_APPS)
            name = app_name if known else (str(page.get("site") or "").strip() or app_name or name)
        lines = chat.context_lines(found)
        if name == "Calendar":
            lines = self._agenda() or lines
        if not lines:
            return False
        if turn != self.turn:
            self.found, self.big, self.turn = [], None, turn
        self.found.append((f"{turn}:{len(self.found)}", name, mark, label, lines, do, found))
        del self.found[:-self.MOST]
        self._lay()
        return True

    def add_picture(self, shot, title, turn):
        """What she saw on the screen (vision.LAST) as a frame, the window as it looks. True if one came."""
        if shot is None:
            return False
        if turn != self.turn:
            self.found, self.big, self.turn = [], None, turn
        self.found = [f for f in self.found if f[5] != "picture"]
        self.found.append((f"{turn}:{len(self.found)}:pic", chat.window_app(title), "\ue7f4", str(title or ""), [],
                           "picture", shot))
        del self.found[:-self.MOST]
        self._lay()
        return True

    @staticmethod
    def _agenda():
        import datetime as dt
        try:
            import agenda
            now = dt.datetime.now()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            events = agenda.kept(start, start + dt.timedelta(days=1))
        except Exception:
            return []
        return [("All day" if e.get("all_day") else e["start"].strftime("%I:%M %p").lstrip("0")) + "   " +
                e.get("title", "") + (f"  \u00b7  {e['where']}" if e.get("where") and len(e["where"]) < 40 else "")
                for e in events][:8]

    def close(self, key):
        self.found = [f for f in self.found if f[0] != key]
        self.big = None if self.big == key else self.big
        self._lay()
        self.page.frames_changed()
        self.page.changed()

    def expand(self, key):
        self.big = None if self.big == key else key
        self._lay()

    def shown(self):
        return sorted((f for f in self.found if self.big in (None, f[0])), key=lambda f: f[5] != "picture")

    def height_for(self):
        shown = self.shown()
        if self.big or len(shown) <= 1:
            return self.BIG if self.big else self.TOP
        return self.TOP + ((len(shown) - 1 + 1) // 2) * (self.ROW + 4) + 4

    def _lay(self):
        keys = [f[0] for f in self.found]
        for key in list(self.cards):
            if key not in keys:
                self.cards.pop(key).deleteLater()
        self.setFixedHeight(self.height_for() if self.found else 0)
        self._place()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()

    def _place(self):
        w = self.width()
        if w < 50:
            return
        y, col = 0, 0
        for n, f in enumerate(self.shown()):
            key = f[0]
            wide = n == 0 or self.big is not None
            cw = w if wide else (w - 4) // 2
            ch = self.BIG if self.big else self.TOP if wide else self.ROW
            card = self.cards.get(key)
            fresh = card is None
            if fresh:
                card = self.cards[key] = FrameCard(self, f)
                card.setParent(self)
            card.set(f, self.big == key)
            if wide:
                card.setGeometry(0, 0, cw, ch)
                y, col = ch + 4, 0
            else:
                card.setGeometry(col * (cw + 4), y, cw, ch)
                if col == 0:
                    col = 1
                else:
                    col, y = 0, y + ch + 4
            card.show()
            if fresh:
                card.come_in()
        for key, card in self.cards.items():
            if key not in [f[0] for f in self.shown()]:
                card.hide()


class Painter:
    """A frame's or a card's drawing, as chat.Bento's canvas calls: words wrapped to a width or left out if they'd run
    past the foot, rounded blocks, lines, discs."""

    def __init__(self, p):
        self.p = p

    def text(self, x, y, text, f, colour, width, bottom, flags=int(Qt.TextFlag.TextWordWrap)):
        """text at x, y in f, wrapped to width; left out if it would run past bottom. Its foot, or None."""
        r = QFontMetricsF(f).boundingRect(QRectF(0, 0, max(10.0, width), 1e6), flags, text)
        if y + r.height() > bottom:
            return None
        self.p.setFont(f)
        self.p.setPen(qc(colour))
        self.p.drawText(QRectF(x, y, max(10.0, width), r.height() + 1), flags, text)
        return y + r.height()

    def line(self, x, y, text, f, colour, width, align=Qt.AlignmentFlag.AlignLeft):
        """One line of text at x, y (its top), cut to width."""
        self.p.setFont(f)
        self.p.setPen(qc(colour))
        h = QFontMetricsF(f).height()
        self.p.drawText(QRectF(x, y, width, h), align | Qt.AlignmentFlag.AlignVCenter, kit.fit(f, text, width))
        return y + h

    def block(self, x, y, w, h, r, fill, line=None):
        self.p.setPen(QPen(qc(line), 1) if line else Qt.PenStyle.NoPen)
        self.p.setBrush(qc(fill))
        self.p.drawRoundedRect(QRectF(x, y, w, h), r, r)

    def rule(self, x0, y0, x1, y1, colour, width=1.0):
        self.p.setPen(QPen(qc(colour), width))
        self.p.drawLine(QPointF(x0, y0), QPointF(x1, y1))

    def disc(self, cx, cy, r, fill):
        self.p.setPen(Qt.PenStyle.NoPen)
        self.p.setBrush(qc(fill))
        self.p.drawEllipse(QPointF(cx, cy), r, r)


def soft_card(p, rect, radius=12, fill="#ffffff", line="#f0f0f1", shadow=True):
    """A card: white with the faintest hairline round it and a soft ambient shadow under it (the owner's
    "anti-wireframe styling", chat.card_ppm)."""
    if shadow:
        p.setPen(Qt.PenStyle.NoPen)
        for i, a in enumerate((0.022, 0.016, 0.010, 0.006)):
            grow = 1.5 + i * 2.5
            p.setBrush(qc("#000000", a))
            p.drawRoundedRect(rect.adjusted(-grow, -grow + 2 + i, grow, grow + 2 + i), radius + grow, radius + grow)
    p.setPen(QPen(qc(line), 1))
    p.setBrush(qc(fill))
    p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)


class FrameCard(QWidget):
    """A small app window in the frames: the app's name at the top left with its own colour's dot, expand and close
    at the right, and what was found drawn as that app would show it (chat.Bento._window and its _draw_*)."""
    M, LEAD = 7, 26

    def __init__(self, frames, found):
        super().__init__()
        self.frames, self.found, self.big = frames, found, False
        self.setMouseTracking(True)
        self.hot = None
        self.offset = 0.0  # px it's still below its place, coming in
        self.pic = None

    def set(self, found, big):
        if found is not self.found or big != self.big:
            self.found, self.big = found, big
            self.update()

    def come_in(self):
        """In from 10 px below, settling as a damped spring does (chat.spring); just there with animations off."""
        if not kit.animations_on():
            return
        anim = QVariantAnimation(self, duration=420, startValue=0.0, endValue=1.0)
        anim.valueChanged.connect(lambda t: (setattr(self, "offset", 10 * (1 - kit.spring(t))), self.update()))
        anim.finished.connect(lambda: (setattr(self, "offset", 0.0), self.update()))
        self._anim = anim
        anim.start()

    def _icons(self):
        w = self.width()
        return {"expand": QRectF(w - self.M - 40, 2, 20, 20), "close": QRectF(w - self.M - 18, 2, 20, 20)}

    def mouseMoveEvent(self, e):
        hot = next((k for k, r in self._icons().items() if r.contains(e.position())), None)
        if hot != self.hot:
            self.hot = hot
            self.setCursor(Qt.CursorShape.PointingHandCursor if hot else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, e):
        self.hot = None
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        key = self.found[0]
        hot = next((k for k, r in self._icons().items() if r.contains(e.position())), None)
        if hot == "expand":
            self.frames.expand(key)
        elif hot == "close":
            self.frames.close(key)

    def paintEvent(self, _):
        f = fonts()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.translate(0, self.offset)
        key, name, mark, label, lines, do, found = self.found
        w, h, m = self.width(), self.height(), self.M
        theme = chat.theme_of(found) if isinstance(found, dict) else None
        dot = TINTS.get(name, TINTS.get({"Google Calendar": "Calendar"}.get(name, ""), (None, theme or "#9ca3af")))[1]
        cv = Painter(p)
        cv.disc(m + 5, 12, 3, dot)
        cv.line(m + 14, 4, name, f.badge, MUTED, w - 80)
        for which, r in self._icons().items():
            p.setFont(f.icon_small)
            p.setPen(qc(TEXT if self.hot == which else FAINT))
            glyph = ("\ue740" if not self.big else "\ue73f") if which == "expand" else "\ue711"
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, glyph)
        card = QRectF(m, self.LEAD, w - 2 * m, h - self.LEAD - 10)
        soft_card(p, card)
        box = (card.x() + 16, card.y() + 16, card.right() - 16, card.bottom() - 12)
        p.save()
        clip = QPainterPath()
        clip.addRoundedRect(card.adjusted(1, 1, -1, -1), 11, 11)
        p.setClipPath(clip)
        view = chat.Bento._view_of(do, name, found if found is not None else {}, lines)
        try:
            getattr(self, f"_draw_{view}")(cv, box, label, lines, found if found is not None else {})
        except Exception as exc:
            print(f"  chat: couldn't draw the {view} frame ({exc!r})")
        p.restore()

    # each app as itself (chat.Bento's _draw_*, in QPainter's terms)
    def _draw_lines(self, cv, box, label, lines, found):
        f = fonts()
        x0, y, x1, bottom = box
        title = label.partition(": ")[2].strip()
        if title:
            y = (cv.text(x0, y, title, f.bold, TEXT, x1 - x0, bottom) or y) + 8
        for line in lines:
            foot = cv.text(x0, y, line, f.small, MUTED, x1 - x0, bottom)
            if foot is None:
                break
            y = foot + 6

    def _draw_search(self, cv, box, label, lines, found):
        """A results page as Google lays one out: the search in a white rounded bar, the short answer, then each result
        as its site on a small disc, its name and where it's from in grey, and its title in Google's link blue."""
        f = fonts()
        x0, y, x1, bottom = box
        results = found.get("results") or {}
        cv.block(x0, y, x1 - x0, 30, 15, "#ffffff", "#dfe1e5")
        cv.p.setFont(f.icon_small)
        cv.p.setPen(qc("#9aa0a6"))
        cv.p.drawText(QRectF(x0 + 8, y, 16, 30), Qt.AlignmentFlag.AlignCenter, "\ue721")
        cv.line(x0 + 32, y + 6, str(found.get("web") or label.partition(": ")[2]), f.small, "#202124",
                x1 - x0 - 44)
        y += 42
        answer = results.get("answer")
        if isinstance(answer, str) and answer.strip():
            y = (cv.text(x0, y, answer.strip()[:280], f.bold, "#202124", x1 - x0, bottom) or y) + 12
        rows = []
        wiki = results.get("wikipedia")
        if isinstance(wiki, dict) and (wiki.get("title") or wiki.get("extract")):
            rows.append(("Wikipedia", "wikipedia.org", wiki.get("title") or "", wiki.get("extract") or ""))
        for story in results.get("news") or []:
            if isinstance(story, dict):
                rows.append((story.get("source") or "News", story.get("when") or "", story.get("title") or "", ""))
        for source, where, title, more in rows:
            if y + 40 > bottom:
                break
            cv.disc(x0 + 11, y + 11, 11, "#f1f3f4")
            cv.p.setFont(f.badge)
            cv.p.setPen(qc("#5f6368"))
            cv.p.drawText(QRectF(x0, y, 22, 22), Qt.AlignmentFlag.AlignCenter, str(source)[:1].upper())
            cv.line(x0 + 30, y, str(source), f.small, "#202124", x1 - x0 - 30)
            if where:
                cv.line(x0 + 30, y + 14, str(where), f.tiny, "#4d5156", x1 - x0 - 30)
            foot = cv.text(x0, y + 32, str(title), kit.font(15), "#1a0dab", x1 - x0, bottom)
            if foot is None:
                break
            y = foot + 4
            if more:
                y = cv.text(x0, y, str(more)[:200], f.small, "#4d5156", x1 - x0, bottom) or y
            y += 12

    def _draw_news(self, cv, box, label, lines, found):
        self._draw_search(cv, box, label, lines, {"web": found.get("news"),
                                                  "results": {"news": found.get("headlines")}})

    def _draw_picture(self, cv, box, label, lines, found):
        """What she saw: the window as it really looks, its own colours and type, cut to the frame from its top."""
        import vision
        x0, y0, x1, bottom = box
        x0, y0, x1 = x0 - 16, y0 - 16, x1 + 16
        w, h = int(x1 - x0), int(bottom + 12 - y0)
        dpr = self.devicePixelRatioF()
        look = (id(found), w, h)
        if self.pic is None or self.pic[0] != look:
            small = vision.shrink(found, max(8, int(w * dpr)))[:max(8, int(h * dpr))]
            image = QImage.fromData(vision.png(small))
            image.setDevicePixelRatio(dpr)
            self.pic = (look, image)
        cv.p.drawImage(QPointF(x0, y0), self.pic[1])

    def _draw_page(self, cv, box, label, lines, found):
        """A page read, as a browser shows it: its address in a rounded bar with a lock, the site's own band in its
        colour, its title big, its words, its to-dos with their boxes."""
        f = fonts()
        x0, y, x1, bottom = box
        page = found.get("page") or {}
        url = str(page.get("url") or found.get("read") or "")
        host = re.sub(r"^https?://(?:www\.)?", "", url).split("/")[0]
        theme = chat.theme_of(found)
        cv.block(x0, y, x1 - x0, 28, 14, "#f1f3f4")
        cv.p.setFont(f.icon_small)
        cv.p.setPen(qc(MUTED))
        cv.p.drawText(QRectF(x0 + 6, y, 16, 28), Qt.AlignmentFlag.AlignCenter, "\ue72e")
        cv.line(x0 + 30, y + 5, host or url, f.small, TEXT, x1 - x0 - 40)
        y += 38
        site = str(page.get("site") or "")
        if theme or site:
            ink = kit.mix(theme, "#000000", 0.25) if theme else MUTED
            band = kit.mix(theme, "#ffffff", 0.88) if theme else "#f4f4f5"
            cv.p.fillRect(QRectF(x0 - 16, y, x1 - x0 + 32, 26), qc(band))
            cv.line(x0, y + 4, site or host, f.badge, ink, x1 - x0)
            y += 36
        else:
            y += 4
        title = str(page.get("title") or "")
        if title:
            y = (cv.text(x0, y, title, f.h2, TEXT, x1 - x0, bottom) or y) + 10
        for para in [p.strip() for p in str(page.get("text") or "").split("\n") if p.strip()][:10]:
            todo = re.match(r"(?:[-*]\s*)?\[([ xX])\]\s*(.*)", para)
            if todo:
                if y + 20 > bottom:
                    break
                done = todo[1].lower() == "x"
                cv.block(x0, y + 3, 13, 13, 3, ACCENT if done else "#ffffff", None if done else "#c4c7cc")
                if done:
                    cv.p.setFont(f.fold)
                    cv.p.setPen(qc("#ffffff"))
                    cv.p.drawText(QRectF(x0, y + 3, 13, 13), Qt.AlignmentFlag.AlignCenter, "\ue73e")
                foot = cv.text(x0 + 22, y + 1, todo[2][:200], f.small, MUTED if done else "#374151", x1 - x0 - 22,
                               bottom)
            else:
                foot = cv.text(x0, y, para[:320], f.small, "#374151", x1 - x0, bottom)
            if foot is None:
                break
            y = foot + 8

    def _draw_weather(self, cv, box, label, lines, found):
        """The weather as a weather app shows it: the temperature big, the sky and the place by it, the days under."""
        f = fonts()
        x0, y, x1, bottom = box
        got = found.get("result") or {}
        now = got.get("now") or {}
        temp = now.get("temp_c")
        cv.line(x0, y, f"{temp}\u00b0" if temp is not None else "\u2014", kit.font(39), TEXT, 110)
        sky = str(now.get("sky") or (got.get("days") or [{}])[0].get("sky") or "").capitalize()
        cv.line(x0 + 110, y + 8, sky, f.bold, TEXT, x1 - x0 - 110)
        cv.line(x0 + 110, y + 30, str(got.get("place") or found.get("weather") or ""), f.small, MUTED,
                x1 - x0 - 110)
        y += 76
        days = [d for d in got.get("days") or [] if isinstance(d, dict)][:3]
        col = (x1 - x0) / max(1, len(days))
        for i, d in enumerate(days):
            if y + 40 > bottom:
                break
            x = x0 + i * col
            cv.line(x, y, str(d.get("day") or "").capitalize(), f.small, MUTED, col - 6)
            hi, lo = d.get("high", d.get("max_c")), d.get("low", d.get("min_c"))
            cv.line(x, y + 20, (f"{hi}\u00b0" if hi is not None else "") + (f" / {lo}\u00b0" if lo is not None else ""),
                    f.bold, TEXT, col - 6)

    def _draw_day(self, cv, box, label, lines, found):
        """The calendar as a day, Google Calendar's own: the hours down the left, each meeting a block of its blue
        with the words in white, now a thin red line across."""
        import datetime as dt
        f = fonts()
        x0, y0, x1, bottom = box
        try:
            import agenda
            now = dt.datetime.now()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            events = [e for e in agenda.kept(start, start + dt.timedelta(days=1)) if not e.get("all_day")]
        except Exception:
            events = []
        if not events:
            return self._draw_lines(cv, box, label, lines, found)
        first = max(0, min(min(e["start"].hour for e in events), now.hour) - 1)
        hour_h = 34
        hours = max(1, int((bottom - y0) // hour_h))
        for i in range(hours):
            y = y0 + i * hour_h
            cv.line(x0, y, dt.datetime(2000, 1, 1, (first + i) % 24).strftime("%I %p").lstrip("0"), f.tiny,
                    "#70757a", 44)
            cv.rule(x0 + 46, y + 7, x1, y + 7, "#dadce0")
        for e in events:
            top = y0 + 7 + ((e["start"].hour - first) + e["start"].minute / 60) * hour_h
            end = e.get("end") or e["start"] + dt.timedelta(minutes=30)
            tall = max(26, (end - e["start"]).total_seconds() / 3600 * hour_h - 2)
            if top > bottom or top + 10 < y0:
                continue
            tall = min(tall, bottom - top)
            cv.block(x0 + 52, top, x1 - x0 - 52, tall, 5, "#039be5")
            cv.line(x0 + 60, top + 4, e.get("title") or "", f.badge, "#ffffff", x1 - x0 - 68)
            if tall > 36:
                cv.line(x0 + 60, top + 21, e["start"].strftime("%I:%M %p").lstrip("0") + " \u2013 " +
                        end.strftime("%I:%M %p").lstrip("0"), f.small, "#e1f5fe", x1 - x0 - 68)
        if first <= now.hour < first + hours:
            y = y0 + 7 + ((now.hour - first) + now.minute / 60) * hour_h
            cv.rule(x0 + 46, y, x1, y, "#ea4335", 1.4)
            cv.disc(x0 + 46, y, 4, "#ea4335")

    def _gmail_mark(self, cv, x, y, size):
        """Gmail's M, its four colours: blue and green posts, the red V between them, a touch of yellow."""
        def poly(points, colour):
            cv.p.setPen(Qt.PenStyle.NoPen)
            cv.p.setBrush(qc(colour))
            cv.p.drawPolygon(QPolygonF([QPointF(x + a * size, y + b * size * 0.75) for a, b in points]))
        poly([(0, 0.1), (0.22, 0.28), (0.22, 1), (0.08, 1), (0, 0.92)], "#4285f4")
        poly([(1, 0.1), (0.78, 0.28), (0.78, 1), (0.92, 1), (1, 0.92)], "#34a853")
        poly([(0, 0.1), (0.5, 0.5), (1, 0.1), (1, 0.36), (0.5, 0.76), (0, 0.36)], "#ea4335")
        poly([(0.78, 0.28), (1, 0.1), (1, 0.36), (0.78, 0.53)], "#fbbc04")

    def _draw_mail(self, cv, box, label, lines, found):
        """Mail, as Gmail shows one message: Gmail's bar with its M, its name and "Search mail" in its pale blue pill;
        the subject, the sender's initials on a coloured disc, their name and address, "to me", the time, the words."""
        f = fonts()
        x0, y, x1, bottom = box
        if isinstance(found, dict) and isinstance(found.get("page"), dict):
            page = found["page"]
            found = {"subject": page.get("title") or "", "body": page.get("text") or ""}
        cv.p.fillRect(QRectF(x0 - 16, y - 16, x1 - x0 + 32, 46), qc("#f6f8fc"))
        self._gmail_mark(cv, x0, y + 2, 18)
        cv.line(x0 + 24, y, "Gmail", kit.font(16), "#5f6368", 60)
        pill_x = x0 + 84
        cv.block(pill_x, y - 5, max(60, x1 - pill_x), 26, 13, "#eaf1fb")
        cv.line(pill_x + 14, y, "Search mail", f.small, "#5f6368", max(40, x1 - pill_x - 20))
        y += 44
        sender = str(found.get("from") or found.get("sender") or "")
        name, _, address = sender.partition("<")
        name, address = name.strip(), address.strip("> ")
        subject = str(found.get("subject") or "")
        if subject:
            y = (cv.text(x0, y, subject, kit.font(16), "#1f1f1f", x1 - x0, bottom) or y) + 12
        if name or address:
            initials = "".join(w[:1] for w in (name or address).split()[:2]).upper()
            colours = ("#e8508a", "#7b61ff", "#1a73e8", "#e37400", "#188038", "#c5221f")
            cv.disc(x0 + 15, y + 15, 15, colours[sum(map(ord, name or address)) % len(colours)])
            cv.p.setFont(f.badge)
            cv.p.setPen(qc("#ffffff"))
            cv.p.drawText(QRectF(x0, y, 30, 30), Qt.AlignmentFlag.AlignCenter, initials or "?")
            who = name or address
            cv.line(x0 + 40, y + 1, who, f.bold, "#1f1f1f", x1 - x0 - 40)
            if address and name:
                cv.line(x0 + 44 + kit.width_of(f.bold, who), y + 2, f"<{address}>", f.tiny, "#5e5e5e",
                        max(10, x1 - x0 - 48 - kit.width_of(f.bold, who)))
            cv.line(x0 + 40, y + 18, "to me", f.small, "#5e5e5e", 80)
            when = found.get("when") or found.get("time")
            if when:
                cv.line(x0, y + 2, str(when), f.small, "#5e5e5e", x1 - x0, Qt.AlignmentFlag.AlignRight)
            y += 44
        for para in [p.strip() for p in str(found.get("body") or found.get("text") or "").split("\n") if p.strip()]:
            foot = cv.text(x0, y, para, f.small, "#1f1f1f", x1 - x0, bottom)
            if foot is None:
                break
            y = foot + 9

    def _draw_notion(self, cv, box, label, lines, found):
        """A page in Notion, as Notion draws one: the path to it in small grey, its title large and bold, its words,
        each to-do with its box, and the one her answer is about marked in Notion's yellow (from what she said)."""
        f = fonts()
        x0, y, x1, bottom = box
        ink, grey = "#37352f", "#9b9a97"
        page = found.get("page") if isinstance(found, dict) and isinstance(found.get("page"), dict) else {}
        url = str(page.get("url") or found.get("read") or "")
        title = str(page.get("title") or "").split(" | ")[0].strip()
        path = [w.replace("-", " ") for w in re.sub(r"^https?://[^/]+/?", "", url).split("?")[0].split("/") if w]
        path = [re.sub(r"\s+[0-9a-f]{32}$", "", w).strip().capitalize() for w in path][-3:]
        if path:
            cv.line(x0, y, " / ".join(path), f.tiny, grey, x1 - x0)
            y += 24
        if title:
            y = (cv.text(x0, y, title, kit.font(24, "bold"), ink, x1 - x0, bottom) or y) + 6
        if page.get("edited"):
            cv.line(x0, y, f"Last edited {page['edited']}", f.small, grey, x1 - x0)
            y += 22
        y += 8
        said = self.frames.page.answer_words()
        texts = [t.strip() for t in str(page.get("text") or "\n".join(lines)).split("\n") if t.strip()]
        for n, text in enumerate(texts[:14]):
            todo = re.match(r"(?:[-*]\s*)?\[([ xX])\]\s*(.*)", text)
            heading = not todo and n + 1 < len(texts) and len(text) < 48 and \
                re.match(r"(?:[-*]\s*)?\[", texts[n + 1]) is not None
            if y + 22 > bottom:
                break
            if todo:
                done, words = todo[1].lower() == "x", todo[2]
                about = len(said & set(re.findall(r"[a-z]{4,}", words.lower()))) >= 2
                fw = f.bold if about else f.small
                r = QFontMetricsF(fw).boundingRect(QRectF(0, 0, x1 - x0 - 28, 1e6), int(Qt.TextFlag.TextWordWrap),
                                                   words)
                if y + 1 + r.height() > bottom:
                    break
                if about:  # Notion's yellow behind what her answer is about
                    cv.p.fillRect(QRectF(x0 + 22, y, r.width() + 4, r.height() + 2), qc("#fbf3db"))
                cv.text(x0 + 24, y + 1, words, fw, grey if done else ink, x1 - x0 - 28, bottom)
                cv.block(x0 + 1, y + 3, 13, 13, 3, "#2383e2" if done else "#ffffff", None if done else ink)
                if done:
                    cv.p.setFont(f.fold)
                    cv.p.setPen(qc("#ffffff"))
                    cv.p.drawText(QRectF(x0 + 1, y + 3, 13, 13), Qt.AlignmentFlag.AlignCenter, "\ue73e")
                y += r.height() + 10
            else:
                foot = cv.text(x0, y, text, f.bold if heading else f.small, ink, x1 - x0, bottom)
                if foot is None:
                    break
                y = foot + (8 if heading else 6)

    def _draw_checklist(self, cv, box, label, lines, found):
        """A checklist, as a notes app has one: its title, then each item with its box, ticked or not."""
        f = fonts()
        x0, y, x1, bottom = box
        title = label.partition(": ")[2].strip() or (lines[0] if not re.match(r"\s*(?:[-*]\s*)?\[", lines[0]) else "")
        if title:
            y = (cv.text(x0, y, title, f.h2, TEXT, x1 - x0, bottom) or y) + 12
        for line in lines:
            m = re.match(r"\s*(?:[-*]\s*)?\[([ xX])\]\s*(.*)", line)
            if not m:
                continue
            if y + 22 > bottom:
                break
            done = m[1].lower() == "x"
            cv.block(x0, y + 3, 14, 14, 3, ACCENT if done else "#ffffff", None if done else "#9ca3af")
            if done:
                cv.p.setFont(f.fold)
                cv.p.setPen(qc("#ffffff"))
                cv.p.drawText(QRectF(x0, y + 3, 14, 14), Qt.AlignmentFlag.AlignCenter, "\ue73e")
            foot = cv.text(x0 + 24, y + 1, m[2], f.small, MUTED if done else TEXT, x1 - x0 - 24, bottom)
            if foot is None:
                break
            y = foot + 10


# ------------------------------------------------------------------ the rail
class RailCard(QWidget):
    """A card in the rail (chat.Dock in Qt): its top white with its mark, its name and a small cross; under it a small
    dark picture of what's in it, and its buttons there: the message waiting for your yes (Send, Don't), a task held
    for your yes (Approve, Cancel), a note she saved (its first lines; a click opens it)."""

    def __init__(self, rail, key, kind, what):
        super().__init__(rail)
        self.rail, self.key, self.kind, self.what = rail, key, kind, what
        self.setMouseTracking(True)
        self.hot, self.buttons, self.offset = None, {}, 0.0
        self.setFixedWidth(RAIL_W)
        self.setFixedHeight(self._height())

    def sign(self):
        return repr(sorted(self.what.items())) if isinstance(self.what, dict) else repr(self.what)

    def _lines(self):
        path = self.what["path"]
        name = os.path.splitext(os.path.basename(path))[0].replace("-", " ").replace("_", " ")
        lines = [ln.strip("#*- ").strip() for ln in self.what["words"].splitlines() if ln.strip()][:6]
        if lines and lines[0].lower() == name.lower():
            lines = lines[1:]
        return name, lines

    def _height(self):
        if self.kind == "draft":
            return 132
        if self.kind == "task":
            return 118
        return 40 + 16 * max(2, len(self._lines()[1])) + 28

    def come_in(self):
        """In from 24 px to the right, settling as a damped spring does."""
        if not kit.animations_on():
            return
        anim = QVariantAnimation(self, duration=420, startValue=0.0, endValue=1.0)
        anim.valueChanged.connect(lambda t: (setattr(self, "offset", 24 * (1 - kit.spring(t))), self.update()))
        anim.finished.connect(lambda: (setattr(self, "offset", 0.0), self.update()))
        self._anim = anim
        anim.start()

    def mouseMoveEvent(self, e):
        hot = next((k for k, r in self.buttons.items() if r.contains(e.position())), None)
        if hot != self.hot:
            self.hot = hot
            self.setCursor(Qt.CursorShape.PointingHandCursor if hot else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, e):
        self.hot = None
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        hot = next((k for k, r in self.buttons.items() if r.contains(e.position())), None)
        page = self.rail.page
        if hot == "cross":
            self.rail.gone.add(self.key)
            page.keep(force=True)
        elif hot == "send":
            page.window.controls.put(("chat", "yes"))
        elif hot == "dont":
            page.window.controls.put(("chat", "no"))
        elif hot == "approve":
            page.decide("approve")
        elif hot == "cancel":
            page.decide("cancel")
        elif hot == "open":
            os.startfile(self.what["path"])

    def _button(self, p, right, y, text, key, fill, ink):
        f = fonts()
        w = kit.width_of(f.tiny, text) + 16
        r = QRectF(right - w, y - 10, w, 20)
        self.buttons[key] = r
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(kit.mix(fill, "#ffffff", 0.12) if self.hot == key else fill))
        p.drawRoundedRect(r, 10, 10)
        p.setFont(f.tiny)
        p.setPen(qc(ink))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
        return r.x()

    def paintEvent(self, _):
        f = fonts()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(self.offset, 0)
        w, h = self.width(), self.height()
        soft_card(p, QRectF(6, 2, w - 12, h - 10))
        self.buttons = {}
        cv = Painter(p)
        mark, title, colour = {"draft": ("\ue724", "Outbox", ACCENT),
                               "task": ("\ue8fb", "Waiting for your yes", "#d9902f")}.get(
            self.kind, ("\ue8a5", None, "#7c5cf2"))
        if self.kind == "note":
            name, lines = self._lines()
            title = name[:1].upper() + name[1:]
        p.setFont(f.icon_small)
        p.setPen(qc(colour))
        p.drawText(QRectF(14, 10, 16, 20), Qt.AlignmentFlag.AlignCenter, mark)
        cv.line(34, 11, title, f.badge, TEXT, w - 76)
        self.buttons["cross"] = QRectF(w - 32, 10, 20, 20)
        p.setFont(f.icon_small)
        p.setPen(qc(TEXT if self.hot == "cross" else FAINT))
        p.drawText(self.buttons["cross"], Qt.AlignmentFlag.AlignCenter, "\ue711")
        dark_h = {"draft": 86, "task": 72}.get(self.kind, 16 * max(2, len(self._lines()[1]) if self.kind == "note"
                                                                   else 2) + 14)
        x0, y0 = 18, 34
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc("#1f1f1f"))
        p.drawRoundedRect(QRectF(x0, y0, w - 36, dark_h), 5, 5)
        right = w - 28
        if self.kind == "draft":
            to = str(self.what.get("contact") or "them")
            to_fit = kit.fit(f.badge, to, 120)
            cv.line(x0 + 10, y0 + 6, to_fit, f.badge, "#ffffff", 120)
            where = (self.what.get("app") or "").capitalize()
            if where:
                cx = x0 + 16 + kit.width_of(f.badge, to_fit)
                cw = kit.width_of(f.tiny, where) + 10
                cv.block(cx, y0 + 7, cw, 15, 4, "#3a3a3a")
                cv.line(cx + 5, y0 + 7, where, f.tiny, "#c7c7c7", cw)
            cv.line(x0 + 10, y0 + 27, " ".join(str(self.what.get("text") or "").split()), f.tiny, "#a3a3a3",
                    w - 58)
            left = self._button(p, right, y0 + 66, "Don't", "dont", "#3a3a3a", "#e5e5e5")
            self._button(p, left - 6, y0 + 66, "Send", "send", ACCENT, "#ffffff")
        elif self.kind == "task":
            cv.text(x0 + 10, y0 + 10, " ".join(str(self.what.get("description") or "").split())[:160], f.tiny,
                    "#d4d4d4", w - 58, y0 + 44)
            left = self._button(p, right, y0 + 56, "Cancel", "cancel", "#3a3a3a", "#e5e5e5")
            self._button(p, left - 6, y0 + 56, "Approve", "approve", ACCENT, "#ffffff")
        else:
            _, lines = self._lines()
            y = y0 + 8
            for n, line in enumerate(lines):
                cv.line(x0 + 10, y, line, f.tiny_bold if n == 0 else f.tiny, "#f5f5f5" if n == 0 else "#a3a3a3",
                        w - 66)
                y += 16
            self.buttons["open"] = QRectF(x0, y0, w - 36, dark_h)


class Rail(QWidget):
    """The deliverables rail down the chat's right (chat.Dock): what she made or holds for you, newest kind first;
    crossed out ones stay gone this run."""

    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.gone, self.cards, self.shown = set(), {}, []
        self.pinned = bool(settings.get("dock_pinned"))
        self.setFixedWidth(RAIL_W + 6)
        self.col = QVBoxLayout(self)
        self.col.setContentsMargins(0, 2, 6, 0)
        self.col.setSpacing(4)
        self.col.addStretch(1)

    def items(self, held_task, pending, notes):
        out = []
        if pending:
            out.append((f"draft {pending['id']}", "draft", pending))
        if held_task:
            out.append((f"task {held_task['id']}", "task", held_task))
        out += [(f"note {path}", "note", {"path": path, "words": words}) for path, words in notes]
        return [i for i in out if i[0] not in self.gone]

    def show_items(self, items):
        keys = [k for k, _, _ in items]
        if keys == self.shown and all(self.cards[k].sign() == (repr(sorted(w.items())) if isinstance(w, dict) else
                                                               repr(w)) for k, _, w in items):
            return bool(keys)  # as it was: nothing laid out again, twice a second
        for key in list(self.cards):
            if key not in keys:
                card = self.cards.pop(key)
                self.col.removeWidget(card)
                card.deleteLater()
        for n, (key, kind, what) in enumerate(items):
            card = self.cards.get(key)
            fresh = card is None or card.sign() != (repr(sorted(what.items())) if isinstance(what, dict) else
                                                     repr(what))
            if fresh:
                if card is not None:
                    self.col.removeWidget(card)
                    card.deleteLater()
                card = self.cards[key] = RailCard(self, key, kind, what)
                if key not in self.shown:
                    card.come_in()
            self.col.removeWidget(card)
            self.col.insertWidget(n, card)
            card.show()
        self.shown = keys
        return bool(keys)


# ------------------------------------------------------------------ the empty page
class Hero(QWidget):
    """The empty page's greeting (chatfx): a slow aurora of three pale blobs behind "Good afternoon, Hari" in its
    gradient, "What can I help with?" under it and four things to start from, which send themselves; it comes in with
    a spring, 60 ms between parts. The aurora moves only while it's shown, with Windows' animations on."""

    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.t0 = time.perf_counter()
        self.timer = QTimer(self, interval=50, timeout=self.update)
        f = fonts()
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addStretch(42)
        self.greet = Greeting(self)
        self.ask = QLabel(chat.ASK)
        self.ask.setFont(kit.font(14 * 1.2))
        self.ask.setStyleSheet(f"color: {MUTED}; background: transparent;")
        self.parts = [kit.Rise(self.greet, 12), kit.Rise(self.ask, 12)]
        col.addWidget(self.parts[0], 0, Qt.AlignmentFlag.AlignHCenter)
        col.addSpacing(6)
        col.addWidget(self.parts[1], 0, Qt.AlignmentFlag.AlignHCenter)
        col.addSpacing(9)
        self.chips = []
        for pair in (chatfx.SUGGESTIONS[:2], chatfx.SUGGESTIONS[2:]):
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addStretch(1)
            for mark, text, fill, ink in pair:
                chip = Suggestion(mark, text, fill, ink)
                chip.clicked.connect(lambda _=False, t=text: page.send(t))
                rise = kit.Rise(chip, 10)
                self.parts.append(rise)
                self.chips.append(chip)
                row.addWidget(rise)
            row.addStretch(1)
            col.addLayout(row)
        col.addStretch(58)
        del f

    def refresh(self):
        name = " ".join(str(settings.get("name") or "").split()).split(" ")[0]
        self.greet.set_words(chatfx.greeting(name=name))

    def show_now(self):
        self.refresh()
        self.show()
        self.raise_()
        for n, part in enumerate(self.parts):
            part.come_in(delay=n * 60)
        self.timer.start()

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def showEvent(self, e):
        self.timer.start()
        super().showEvent(e)

    def paintEvent(self, _):
        """The aurora, about the greeting: three soft blobs, each a gaussian of its pale colour as chatfx's are, drawn
        at half size and smoothed out, so it costs next to nothing."""
        w, h = self.width(), self.height()
        if w < 10 or h < 10:
            return
        p = QPainter(self)
        if not kit.animations_on() or self.page.window.current_tab != "home":
            a = 0.0
            self.timer.stop()
        else:
            a = (time.perf_counter() - self.t0) * 2 * math.pi / 14.0  # one slow circle every 14 s
        aw, ah = 640, 290
        cx0 = w / 2
        cy0 = self.greet.mapTo(self, QPoint(0, 0)).y() + 60 if self.greet.isVisible() else h * 0.42
        mx, my = 2 * aw * 0.26 + 8, 2 * ah * 0.42 + 8  # each blob's whole fall-off, all round
        k = 0.25
        img = QImage(int((aw + 2 * mx) * k), int((ah + 2 * my) * k), QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        q = QPainter(img)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.scale(k, k)
        q.translate(mx, my)
        for i, colour in enumerate(chatfx.AURORA):
            cx = aw * (0.32 + 0.18 * i) + aw * 0.06 * math.cos(a + i * 2.1)
            cy = ah * 0.55 + ah * 0.12 * math.sin(a * (1 + 0.3 * i) + i)
            rx, ry = aw * 0.26, ah * 0.42
            q.save()
            q.translate(cx, cy)
            q.scale(1.0, ry / rx)
            g = QRadialGradient(QPointF(0, 0), 2 * rx)
            for t, v in ((0.0, 1.0), (0.25, 0.78), (0.5, 0.37), (0.75, 0.105), (1.0, 0.0)):
                g.setColorAt(t, qc(colour, 0.5 * v))
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(QBrush(g))
            q.drawEllipse(QPointF(0, 0), 2 * rx, 2 * rx)
            q.restore()
        q.end()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(QRectF(cx0 - aw / 2 - mx, cy0 - ah / 2 - my, aw + 2 * mx, ah + 2 * my), img)


class Greeting(QWidget):
    """The greeting in its gradient, blue into indigo into violet (chatfx.STOPS), its letters filled with it as a
    path: crisp at any size, the aurora showing between them."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.words, self.path = "", QPainterPath()
        self.qfont = kit.font(32 / kit.TYPE, "semibold", family="greeting")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.set_words("Hello")

    def set_words(self, words):
        if words == self.words:
            return
        self.words = words
        path = QPainterPath()
        path.addText(0, 0, self.qfont, words)
        box = path.boundingRect()
        self.path = path.translated(-box.left() + 2, -box.top() + 3)
        self.setFixedSize(int(box.width()) + 6, int(box.height()) + 8)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, self.width(), 0)
        for n, stop in enumerate(chatfx.STOPS):
            g.setColorAt(n / (len(chatfx.STOPS) - 1), qc(stop))
        p.fillPath(self.path, QBrush(g))


class Suggestion(QAbstractButton):
    """Something to start from on the empty page: its mark in its colour and its words, on a pale pill of the same
    hue, a shade deeper under the mouse."""

    def __init__(self, mark, text, fill, ink, parent=None):
        super().__init__(parent)
        self.mark, self.text_, self.fill, self.ink = mark, text, fill, ink
        f = fonts()
        self.setFixedSize(int(kit.width_of(f.small, text) + 46 + 0.999), 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(text)

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _):
        f = fonts()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        if self.isDown():
            p.translate(r.center())
            p.scale(0.96, 0.96)
            p.translate(-r.center())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(kit.mix(self.fill, self.ink, 0.08) if self.underMouse() else self.fill))
        p.drawRoundedRect(r, 17, 17)
        p.setFont(f.icon_small)
        p.setPen(qc(self.ink))
        p.drawText(QRectF(8, 0, 16, r.height()), Qt.AlignmentFlag.AlignCenter, self.mark)
        p.setFont(f.small)
        p.setPen(qc(TEXT))
        p.drawText(QRectF(32, 0, r.width() - 36, r.height()), Qt.AlignmentFlag.AlignVCenter, self.text_)


# ------------------------------------------------------------------ the box
class Edit(QPlainTextEdit):
    """What you type into the box: Enter sends and Shift+Enter is a new line, as the AI chats have it; Ctrl+V takes
    files or a picture too; Up, Down and Esc are the box's while it shows what a slash found."""

    def __init__(self, box):
        super().__init__(box)
        self.box = box

    def keyPressEvent(self, e):
        key, mods = e.key(), e.modifiers()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (mods & Qt.KeyboardModifier.ShiftModifier):
            self.box.page.enter()
            return
        if key == Qt.Key.Key_Escape:
            if not self.box.voice_key("cancel"):
                self.box.page.clear_found(box=True)
            return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down) and self.box.page.found_now:
            self.box.page.move_found(1 if key == Qt.Key.Key_Down else -1)
            return
        if key == Qt.Key.Key_V and mods & Qt.KeyboardModifier.ControlModifier and self.box.paste():
            return
        super().keyPressEvent(e)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.box.set_ring(focus=True)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.box.set_ring(focus=False)


class Box(QWidget):
    """The chat's box, Hedwig's own (chat.Box): one soft grey rounded field, what you type along its top, growing a
    line at a time up to six; a row under it, the paperclip and her badge (her face and name, which open a small menu)
    at the left, the waveform and the round blue Send at the right. Files wait as white chips over the words, each
    with a cross. The waveform dictates: the row opens into Cancel, a live strip of what the mic hears with how long,
    and Done; what was said is written into the box (siri.box_voice). A ring of the accent while it has the keyboard,
    and a gradient travelling round it while she's busy."""
    TALL, ROUND, MOST_LINES, BAND = 84, 28, 6, 44
    VOICE_MOST, WRITING_MOST = 300, 45

    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.files, self.voice, self.voice_at, self.hearing = [], None, 0.0, False
        self.focus_on = self.busy_on = False
        self.ring, self.ring_at = None, 0.0
        self.speaks = bool(settings.get("chat_speaks"))
        self.hot = None
        self.strip_open = 1.0
        self.buttons = {}
        self.setMouseTracking(True)
        f = fonts()
        self.edit = Edit(self)
        self.edit.setFont(f.chat)
        self.edit.setPlaceholderText(identity.named(chat.HINT))
        self.edit.setFrameShape(QFrame.Shape.NoFrame)
        self.edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.edit.setStyleSheet(f"QPlainTextEdit {{ background: transparent; color: {TEXT}; border: none; "
                                f"selection-background-color: #d6e4fd; selection-color: {TEXT}; }}")
        self.edit.document().setDocumentMargin(0)
        palette = self.edit.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, qc(FAINT))
        self.edit.setPalette(palette)
        self.edit.textChanged.connect(self._typed)
        self.line_h = QFontMetricsF(f.chat).lineSpacing()
        self.lines = 1
        self.ring_timer = QTimer(self, interval=33, timeout=self._ring_tick)
        self.bar_timer = QTimer(self, interval=90, timeout=self.update)
        self.wave_timer = QTimer(self, interval=40, timeout=self._wave_tick)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._resize()

    # its size and what's in it
    def _height(self):
        return self.TALL + (self.lines - 1) * self.line_h + (self.BAND if self.files else 0)

    def _resize(self):
        self.setFixedHeight(int(self._height()))
        self._lay()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._lay()

    def _lay(self):
        band = self.BAND if self.files else 0
        self.edit.setGeometry(18, int(band + 15), max(60, self.width() - 36), int(self.lines * self.line_h + 4))
        self.edit.setVisible(self.voice is None)
        self.update()

    def _typed(self):
        lines = max(1, min(self.MOST_LINES, self._display_lines()))
        if lines != self.lines:
            self.lines = lines
            self._resize()
        self.update()
        self.page.typed()

    def _display_lines(self):
        n, block = 0, self.edit.document().begin()
        while block.isValid():
            n += max(1, block.layout().lineCount())
            block = block.next()
        return n

    def get(self):
        return self.edit.toPlainText()

    def put(self, text):
        self.edit.setPlainText(text)
        cur = self.edit.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        self.edit.setTextCursor(cur)

    def clear(self):
        self.edit.clear()

    def focus(self):
        self.edit.setFocus()

    def _empty(self):
        return not self.get().strip() and not self.files

    # files
    def pick(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Attach files")
        self.attach(paths)
        self.focus()

    def attach(self, paths):
        import attach
        before = len(self.files)
        for path in paths or ():
            path = os.path.normpath(str(path))
            if os.path.isfile(path) and path not in self.files and len(self.files) < attach.MOST_FILES:
                self.files.append(path)
        if len(self.files) != before:
            self._resize()
            return True
        return False

    def drop(self, i):
        if 0 <= i < len(self.files):
            del self.files[i]
            self._resize()

    def take(self):
        files, self.files = self.files, []
        if files:
            self._resize()
        return files

    def paste(self):
        """Ctrl+V: files copied in File Explorer, or a picture copied (a screenshot), attached. True if it took them;
        words are pasted as ever."""
        import winplatform as win
        try:
            files = win.clipboard_files()
            if files:
                return self.attach(files)
            dib = win.clipboard_picture()
            if dib:
                import attach
                png = attach.dib_png(dib)
                if png:
                    folder = os.path.join(win.home("LOCALAPPDATA"), "attachments")
                    return self.attach([attach.keep_pasted(png, folder)])
        except Exception as exc:
            print(f"  chat: couldn't take what was pasted ({exc!r})")
        return False

    # its ring
    def set_ring(self, focus=None, busy=None):
        if focus is not None:
            self.focus_on = focus
        if busy is not None:
            self.busy_on = busy
        ring = "busy" if self.busy_on or self.voice == "rec" else "focus" if self.focus_on else None
        if ring != self.ring:
            self.ring = ring
            if ring == "busy" and kit.animations_on():
                self.ring_timer.start()
            else:
                self.ring_timer.stop()
            self.update()

    def _ring_tick(self):
        self.ring_at = (self.ring_at + 0.033 / 2.4) % 1.0  # round once every 2.4 s
        self.update()

    # voice
    def listening(self, on):
        if on != self.hearing:
            self.hearing = on
            if on:
                self.bar_timer.start()
            else:
                self.bar_timer.stop()
            self.update()

    def voice_start(self):
        if self.voice:
            return
        self.voice, self.voice_at = "rec", time.time()
        self.page.window.controls.put(("box voice", "start"))
        self.set_ring()
        self._lay()
        self.strip_open = 0.0
        if kit.animations_on():  # opening out from the waveform button, a small element's 300 ms
            anim = QVariantAnimation(self, duration=300, startValue=0.0, endValue=1.0)
            anim.valueChanged.connect(lambda t: (setattr(self, "strip_open", kit.spring(t)), self.update()))
            self._strip_anim = anim
            anim.start()
        else:
            self.strip_open = 1.0
        self.wave_timer.start()

    def voice_end(self, action):
        if self.voice != "rec":
            return
        self.page.window.controls.put(("box voice", action))
        if action == "done":
            self.voice, self.voice_at = "writing", time.time()
            self.update()
        else:
            self._voice_off()

    def voice_key(self, action):
        if self.voice == "rec":
            self.voice_end(action)
            return True
        return bool(self.voice)

    def voice_words(self, text):
        if not self.voice:
            return
        self._voice_off()
        text = " ".join(str(text or "").split())
        if text:
            was = self.get().rstrip()
            self.put(f"{was} {text}" if was else text)
        self.focus()

    def _voice_off(self):
        self.voice = None
        self.wave_timer.stop()
        self.set_ring()
        self._lay()

    def _wave_tick(self):
        if self.voice == "writing" and time.time() - self.voice_at > self.WRITING_MOST:
            self._voice_off()
            return
        if self.voice == "rec" and time.time() - self.voice_at >= self.VOICE_MOST:
            self.voice_end("done")
        self.update()

    def speak(self, on):
        self.speaks = bool(on)
        settings.put("chat_speaks", self.speaks)
        getattr(self.page.window.pages.get("settings"), "speaks_changed", lambda on: None)(self.speaks)

    def menu(self):
        """Her badge's menu, opening up from it: attach files, talk to her out loud, and whether typed answers are
        said."""
        import qtwindow
        menu = qtwindow.styled_menu(self)
        menu.addAction("Attach files\u2026").triggered.connect(self.pick)
        menu.addAction(f"Talk to {identity.name()}").triggered.connect(
            lambda: self.page.window.controls.put(("mic",)))
        act = menu.addAction("Say typed answers out loud")
        act.setCheckable(True)
        act.setChecked(self.speaks)
        act.toggled.connect(self.speak)
        r = self.buttons.get("badge", QRectF(50, self.height() - 40, 60, 28))
        at = self.mapToGlobal(QPoint(int(r.x()) - 6, int(r.y())))
        menu.exec(QPoint(at.x(), at.y() - menu.sizeHint().height() - 8))

    # the mouse
    def _hit(self, pos):
        return next((k for k, r in self.buttons.items() if r.contains(pos)), None)

    def mouseMoveEvent(self, e):
        hot = self._hit(e.position())
        if hot != self.hot:
            self.hot = hot
            self.setCursor(Qt.CursorShape.PointingHandCursor if hot else Qt.CursorShape.IBeamCursor
                           if self.voice is None else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, e):
        self.hot = None
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        self.pressed = self._hit(e.position())
        self.update()
        if self.pressed is None and self.voice is None:
            self.focus()

    def mouseReleaseEvent(self, e):
        hot, self.pressed = self._hit(e.position()), getattr(self, "pressed", None)
        pressed, self.pressed = self.pressed, None
        self.update()
        if hot is None or hot != pressed:
            return
        if hot == "clip":
            self.pick()
        elif hot == "badge":
            self.menu()
        elif hot == "wave":
            self.voice_start()
        elif hot == "send":
            if self._empty():
                self.focus()
            else:
                self.page.send()
        elif hot == "cancel":
            self.voice_end("cancel")
        elif hot == "done":
            self.voice_end("done")
        elif hot.startswith("cross"):
            self.drop(int(hot[5:]))

    # drawing
    def paintEvent(self, _):
        import attach
        f = fonts()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        field = QRectF(0.5, 0.5, w - 1, h - 1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(FIELD))
        p.drawRoundedRect(field, self.ROUND, self.ROUND)
        ring = self.ring if kit.animations_on() or self.ring != "busy" else "focus"
        if ring == "focus":
            p.setPen(QPen(qc("#a5b4fc"), 1.3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(field.adjusted(0.4, 0.4, -0.4, -0.4), self.ROUND, self.ROUND)
        elif ring == "busy":
            g = QConicalGradient(QPointF(w / 2, h / 2), -360 * self.ring_at)
            stops = list(chatfx.STOPS) + list(reversed(chatfx.STOPS[:-1]))
            for n, stop in enumerate(stops):
                g.setColorAt(n / (len(stops) - 1), qc(stop))
            for width, alpha in ((7.0, 0.10), (4.0, 0.16)):  # a soft light just inside it
                c = QPen(QBrush(g), width)
                p.setOpacity(alpha)
                p.setPen(c)
                p.setBrush(Qt.BrushStyle.NoBrush)
                inset = width / 2 + 0.8
                p.drawRoundedRect(field.adjusted(inset, inset, -inset, -inset), self.ROUND - inset,
                                  self.ROUND - inset)
            p.setOpacity(1.0)
            p.setPen(QPen(QBrush(g), 1.8))
            p.drawRoundedRect(field.adjusted(0.9, 0.9, -0.9, -0.9), self.ROUND, self.ROUND)
        self.buttons = {}
        cv = Painter(p)
        if self.files:  # the files' chips along the top, as many as there's room for, then how many more
            x, top, end = 14.0, 10.0, w - 14
            for i, path in enumerate(self.files):
                name = os.path.basename(path)
                name = name if len(name) <= 26 else name[:16] + "\u2026" + name[-8:]
                cw = 30 + kit.width_of(f.badge, name) + 30
                more = len(self.files) - i
                if x + cw > end - (40 if more > 1 else 0):
                    cv.line(x + 4, top + 8, f"+{more}", f.badge, MUTED, 40)
                    break
                cv.block(x, top, cw, 32, 10, "#ffffff")
                p.setFont(f.icon_small)
                p.setPen(qc(ACCENT))
                p.drawText(QRectF(x + 4, top, 22, 32), Qt.AlignmentFlag.AlignCenter, attach.icon(path))
                cv.line(x + 30, top + 7, name, f.badge, TEXT, cw - 56)
                cross = QRectF(x + cw - 24, top + 6, 20, 20)
                self.buttons[f"cross{i}"] = cross
                p.setFont(f.fold)
                p.setPen(qc(TEXT if self.hot == f"cross{i}" else MUTED))
                p.drawText(cross, Qt.AlignmentFlag.AlignCenter, "\ue711")
                x += cw + 8
        low = h - 26
        if self.voice:
            self._paint_voice(p, cv, w, low)
            return
        # the paperclip; her badge 24 px clear of it, as borderless controls want (better-layout)
        self.buttons["clip"] = QRectF(4, low - 14, 28, 28)
        p.setFont(f.icon)
        p.setPen(qc(TEXT if self.hot == "clip" else MUTED))
        p.drawText(self.buttons["clip"], Qt.AlignmentFlag.AlignCenter, "\ue723")
        x = 50.0
        face = self.page.small_face
        badge_w = (face.width() / face.devicePixelRatio() + 6 if face is not None else 0) + \
            kit.width_of(f.badge, identity.name())
        self.buttons["badge"] = QRectF(x - 4, low - 13, badge_w + 8, 26)
        if face is not None:
            fh = face.height() / face.devicePixelRatio()
            p.drawPixmap(QPointF(x, low - fh / 2), face)
            x += face.width() / face.devicePixelRatio() + 6
        cv.line(x, low - 9, identity.name(), f.badge, ACCENT if self.hot == "badge" else TEXT, 120)
        cx = w - 28
        # the waveform: five thin bars, red and moving with your voice while she hears you
        wx = cx - 36
        self.buttons["wave"] = QRectF(wx - 13, low - 13, 26, 26)
        levels = None
        if self.hearing:
            siri = sys.modules.get("siri")
            got = list(getattr(siri, "MIC_LEVELS", ()))[-5:]
            got = [0.0] * (5 - len(got)) + got
            levels = [chat.level_height(v) for v in (got[0], got[2], got[4], got[3], got[1])]
        colour = ERROR if self.hearing else TEXT if self.hot == "wave" else MUTED
        pen = QPen(qc(colour), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        for i in range(5):
            tall = (0.35, 0.75, 1.0, 0.6, 0.3)[i] if levels is None else 0.2 + 0.8 * levels[i]
            half = max(1.2, tall * 6)
            bx = wx + (i - 2) * 3.4
            p.drawLine(QPointF(bx, low - half), QPointF(bx, low + half))
        # Send: her blue once there's something to send, paler till then, darker under the mouse; 96% held down
        r = 16.0 * (0.96 if getattr(self, "pressed", None) == "send" else 1.0)
        self.buttons["send"] = QRectF(cx - 16, low - 16, 32, 32)
        send = kit.mix(ACCENT, FIELD, 0.5) if self._empty() else kit.mix(ACCENT, "#000000", 0.12) \
            if self.hot == "send" else ACCENT
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(send))
        p.drawEllipse(QPointF(cx, low), r, r)
        p.setFont(f.icon_small)
        p.setPen(qc("#ffffff"))
        p.drawText(QRectF(cx - 16, low - 16, 32, 32), Qt.AlignmentFlag.AlignCenter, "\ue74a")

    def _paint_voice(self, p, cv, w, cy):
        """Cancel at the row's left, Done at its right, and between them the strip, opening out from where the
        waveform button was, its bars and how long in it; "Writing it down" while what was said is written up."""
        f = fonts()
        left, right, h = 12.0, w - 12.0, 32.0
        cancel_w = kit.width_of(f.badge, "Cancel") + 32
        done_w = kit.width_of(f.badge, "Done") + 52
        rec = self.voice == "rec"
        if rec:
            self.buttons["cancel"] = QRectF(left, cy - h / 2, cancel_w, h)
            self.buttons["done"] = QRectF(right - done_w, cy - h / 2, done_w, h)
            cv.block(left, cy - h / 2, cancel_w, h, h / 2, "#f9fafb" if self.hot == "cancel" else "#ffffff")
            p.setFont(f.badge)
            p.setPen(qc(TEXT))
            p.drawText(self.buttons["cancel"], Qt.AlignmentFlag.AlignCenter, "Cancel")
            cv.block(right - done_w, cy - h / 2, done_w, h, h / 2,
                     kit.mix(ACCENT, "#000000", 0.1) if self.hot == "done" else ACCENT)
            p.setFont(f.icon_small)
            p.setPen(qc("#ffffff"))
            p.drawText(QRectF(right - done_w + 12, cy - h / 2, 16, h), Qt.AlignmentFlag.AlignCenter, "\ue73e")
            p.setFont(f.badge)
            p.drawText(QRectF(right - done_w + 30, cy - h / 2, done_w - 40, h), Qt.AlignmentFlag.AlignVCenter, "Done")
        x1 = right - done_w - 10
        full0 = left + cancel_w + 10
        start = (w - 28 - 36) - 12
        x0 = start + (full0 - start) * max(0.0, self.strip_open)
        sw = max(38.0, x1 - x0)
        cv.block(x1 - sw, cy - h / 2, sw, h, h / 2, "#ffffff")
        if not rec:
            cv.line(x1 - sw + 16, cy - 9, "Writing it down\u2026", f.badge, MUTED, sw - 24)
            return
        took = time.time() - self.voice_at
        cv.line(x1 - 60, cy - 9, chat.clock(took) if took >= 1 else "0:00", f.badge, MUTED, 46,
                Qt.AlignmentFlag.AlignRight)
        b0, b1, step = x1 - sw + 16, x1 - 66, 5.0
        n = max(0, int((b1 - b0) // step))
        siri = sys.modules.get("siri")
        levels = list(getattr(siri, "BOX_LEVELS", ()))[-n:] if n else []
        levels = [0.0] * (n - len(levels)) + levels
        for i, level in enumerate(levels):
            tall = chat.level_height(level)
            half = max(1.3, tall * 13)
            pen = QPen(qc(TEXT if tall > 0.06 else FAINT), 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            bx = b0 + i * step
            p.drawLine(QPointF(bx, cy - half), QPointF(bx, cy + half))


class FoundList(QWidget):
    """What a slash in the box found among her quick actions, over the box: each its icon, its name and its kind, the
    one Enter does lit."""

    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.rows = []
        self.setMouseTracking(True)

    def show_found(self, found, at):
        self.found, self.at = found, at
        self.setFixedHeight(8 + 38 * len(found) + 8 if found else 0)
        self.setVisible(bool(found))
        self.update()

    def mouseMoveEvent(self, e):
        i = int((e.position().y() - 8) // 38)
        if 0 <= i < len(self.found) and i != self.page.found_at:
            self.page.found_at = i
            self.show_found(self.found, i)

    def mousePressEvent(self, e):
        i = int((e.position().y() - 8) // 38)
        self.page.run_found(i)

    def paintEvent(self, _):
        f = fonts()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        soft_card(p, QRectF(1, 1, self.width() - 2, self.height() - 4), 14)
        for i, (icon, name, kind, _) in enumerate(self.found):
            r = QRectF(8, 8 + i * 38, self.width() - 16, 38)
            if i == self.at:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(qc("#f3f4f6"))
                p.drawRoundedRect(r, 9, 9)
            p.setFont(f.icon)
            p.setPen(qc(MUTED))
            p.drawText(QRectF(r.x() + 10, r.y(), 24, 38), Qt.AlignmentFlag.AlignVCenter, icon)
            p.setFont(f.small)
            kw = kit.width_of(f.small, kind)
            p.drawText(QRectF(r.right() - 12 - kw, r.y(), kw, 38), Qt.AlignmentFlag.AlignVCenter, kind)
            p.setFont(f.body)
            p.setPen(qc(TEXT))
            p.drawText(QRectF(r.x() + 42, r.y(), r.width() - 70 - kw, 38), Qt.AlignmentFlag.AlignVCenter,
                       kit.fit(f.body, name, r.width() - 70 - kw))


# ------------------------------------------------------------------ the page
class Page(QWidget):
    """The chat as her Qt window shows it (chat.Page in Qt): the thread in the middle no wider than WIDE, the box at
    its foot, the greeting while there's nothing yet, the rail down the right while it has a card and there's room."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        fonts()
        self.head = ("Chat", "")
        self.thread = chat.Thread()
        self.thread.starting = "starting up"
        self.opened = set()
        self.views = []  # (its signature, TurnView), one a turn
        self.found_now, self.found_at, self.actions = [], 0, None
        self.turn_n, self.frames_open, self.frames_after = 0, True, None
        self.waiting, self.notes, self.kept, self.ticks = None, [], None, 0
        self.pending = False
        dpr = window.devicePixelRatioF() if window is not None else 1.0
        self.face = kit.face(14, dpr)
        self.small_face = kit.face(12, dpr, skin="#cfd2d8")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.column = QWidget(self)
        col = QVBoxLayout(self.column)
        col.setContentsMargins(0, 0, 0, 14)
        col.setSpacing(0)
        self.scroll = QScrollArea(self.column)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{ background: {BG}; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 2px 4px 0; }}
            QScrollBar::handle:vertical {{ background: #d9dbe0; border-radius: 3px; min-height: 40px; }}
            QScrollBar::handle:vertical:hover {{ background: #c4c7ce; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}""")
        self.content = QWidget()
        self.content.setObjectName("content")
        self.content.setStyleSheet(f"QWidget#content {{ background: {BG}; }}")
        self.lines = QVBoxLayout(self.content)
        self.lines.setContentsMargins(0, 4, 0, 12)
        self.lines.setSpacing(0)
        self.live = LiveLine(self)
        self.live.hide()
        self.lines.addWidget(self.live)
        self.lines.addStretch(1)
        self.scroll.setWidget(self.content)
        self.glide = kit.Glide(self.scroll)
        self.at_bottom, self.adjusting = True, False  # you're reading the end: a new line keeps you there
        self.scroll.verticalScrollBar().rangeChanged.connect(self._range_changed)
        self.scroll.verticalScrollBar().valueChanged.connect(self._scrolled)
        col.addWidget(self.scroll, 1)
        self.foot = QWidget(self.column)
        foot = QVBoxLayout(self.foot)
        foot.setContentsMargins(0, 6, 0, 0)
        foot.setSpacing(4)
        self.found = FoundList(self.foot)
        self.found.hide()
        foot.addWidget(self.found)
        self.status = QLabel("", self.foot)
        self.status.setFont(fonts().small)
        self.status.setStyleSheet(f"color: {MUTED}; padding-left: 8px; background: transparent;")
        self.status.hide()
        foot.addWidget(self.status)
        self.box = Box(self)
        foot.addWidget(self.box)
        col.addWidget(self.foot)
        row.addWidget(self.column, 1)
        self.rail = Rail(self)
        self.rail.hide()
        row.addWidget(self.rail)
        self.hero = Hero(self)
        self.hero.hide()
        self.frames = Frames(self)
        self.save_timer = QTimer(self, singleShot=True, interval=1000, timeout=self.save)
        self.draw_timer = QTimer(self, singleShot=True, interval=0, timeout=self.draw)
        import winplatform as win
        self.chats = chat.Chats(os.path.join(win.APPDATA_DIR, "chats.json"))
        if self.chats.found:
            lines = self.chats.lines()
            if lines and time.time() - float(lines[-1].get("at") or 0) > chat.FRESH:
                self.chats.start()
            else:
                self.thread.reset(lines)
        else:
            try:
                import history
                self.thread.earlier(history.recent(6, chat.FRESH, cold=False))
            except Exception as exc:
                print(f"  chat: couldn't read the last turns ({exc!r})")
            self.chats.keep(self.thread.items)
        self.jump = True
        self.empty_now = None
        self.draw()

    # ------------------------------------------------------------------ layout
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._centre()

    def _centre(self):
        room = self.column.width()
        pad = max(16, (room - WIDE) // 2)
        self.lines.setContentsMargins(pad, 4, pad, 12)
        self.foot.layout().setContentsMargins(pad, 6, pad, 0)
        self.hero.setGeometry(self.scroll.geometry().translated(self.column.pos()))
        self._lay_side()

    def _lay_side(self, items=None):
        """The rail while it has a card (or is pinned) and there's room; else the chat has the page."""
        has = bool(self.rail.shown) if items is None else items
        want = (has or self.rail.pinned) and self.width() >= NARROW
        if want != self.rail.isVisible():
            self.rail.setVisible(want)
            QTimer.singleShot(0, self._centre)

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._centre)

    # ------------------------------------------------------------------ her events
    def her_event(self, state, detail=""):
        """One of her window's events (Window.set_status): into the thread, and drawn if it shows; the box's ring and
        waveform as she listens and thinks."""
        if state == "Box words":
            self.box.voice_words(detail)
            return
        if state == "Context":
            if self.frames.add(detail, self.turn_n):
                self._frames_here()
                self.toggle_frames(True)
            return
        if state in ("Asked", "Heard"):
            self.turn_n += 1
        if state == "Step" and str(detail).startswith("done\t") and "screen" in str(detail).lower():
            QTimer.singleShot(0, self._screen_frame)
        if state in ("Listening", "Still listening", "Transcribing", "Thinking", "Looking", "Doing it"):
            self.box.set_ring(busy=True)
        elif state in ("Ready", "Speaking", "Something went wrong"):
            self.box.set_ring(busy=False)
        if state in ("Listening", "Still listening"):
            self.box.listening(True)
        elif state in ("Transcribing", "Thinking", "Ready", "Speaking", "Heard", "Something went wrong"):
            self.box.listening(False)
        if self.thread.event(state, detail):
            self.changed()

    def changed(self):
        if not self.draw_timer.isActive():
            self.draw_timer.start()
        if not self.save_timer.isActive():
            self.save_timer.start()

    # ------------------------------------------------------------------ the thread
    def _turns(self):
        """The thread in turns, as chat.turns, each with where it starts and ends in the items."""
        items = self.thread.items
        if not items:
            return []
        out, _ = chat.turns(items)
        starts = [0] + [i for i, item in enumerate(items) if item["kind"] == "you" and i]
        ends = starts[1:] + [len(items)]
        return [{**turn, "start": a, "end": z} for turn, a, z in zip(out, starts, ends)]

    def _sign(self, turn):
        items = self.thread.items
        parts = tuple((id(items[i]), items[i]["kind"], items[i]["text"], items[i]["state"],
                       tuple(items[i].get("files") or ()), items[i].get("took"))
                      for i in range(turn["start"], turn["end"]))
        steps = turn["steps"]
        opened = bool(steps) and id(items[steps[0]]) in self.opened
        return parts, opened

    def draw(self):
        """The thread as it is now: each turn built again only if it changed; at its end unless you'd scrolled up."""
        if self.jump:
            self.at_bottom = True
        self.jump = False
        turns = self._turns()
        items = self.thread.items
        frames_turn = None
        if self.frames_open and self.frames.found:
            start = next((n for n, i in enumerate(items) if id(i) == self.frames_after), None)
            frames_turn = next((k for k, t in enumerate(turns) if start is not None and t["start"] <= start < t["end"]),
                               len(turns) - 1)
        signs = [self._sign(turn) + (k == frames_turn,) for k, turn in enumerate(turns)]
        again = [k for k in range(len(turns)) if k >= len(self.views) or self.views[k][0] != signs[k]]
        going = [v for k, (_, v) in enumerate(self.views) if k in again or k >= len(turns)]
        holder = self.frames.parentWidget()
        while holder is not None and holder not in going:
            holder = holder.parentWidget()
        if holder is not None:  # the frames out of a turn that's going, before it takes them with it
            self.frames.setParent(None)
        for k in again:
            view = TurnView(self, items, turns[k], self.frames if k == frames_turn else None)
            if k < len(self.views):
                old = self.views[k][1]
                self.lines.replaceWidget(old, view)
                old.deleteLater()
                self.views[k] = (signs[k], view)
            else:
                self.lines.insertWidget(len(self.views), view)
                self.views.append((signs[k], view))
                if k == len(turns) - 1 and not self.empty_now and len(items) > 1:
                    kit.fade_in(view, 200)
        while len(self.views) > len(turns):
            _, old = self.views.pop()
            self.lines.removeWidget(old)
            old.deleteLater()
        if self.frames.found and self.frames_open:
            self.frames.show()
        self.live.setVisible(bool(self.thread.status and items))
        self._lay_empty(not items)
        if hasattr(self.window, "side"):
            self.window.side.lay_chats()

    def _scrolled(self, value):
        if not self.adjusting:
            self.at_bottom = value >= self.scroll.verticalScrollBar().maximum() - 24

    def _range_changed(self, _lo, hi):
        if self.at_bottom:  # what's new is in view the moment it's there
            self.adjusting = True
            self.glide.stop()
            self.scroll.verticalScrollBar().setValue(hi)
            self.adjusting = False

    def _lay_empty(self, empty):
        if empty == self.empty_now:
            return
        self.empty_now = empty
        if empty:
            self._centre()
            self.hero.show_now()
        else:
            self.hero.hide()

    def live_words(self):
        status, began = self.thread.status, self.thread.thinking
        took = int(time.time() - began) if began else 0
        return status + (f"  {took}s" if took >= 1 else "")

    def toggle_steps(self, key):
        self.opened ^= {key}
        self.changed()

    # ------------------------------------------------------------------ your chats
    def save(self):
        self.save_timer.stop()
        self.chats.keep(self.thread.items)

    def listed(self, most=None):
        items = self.thread.items
        now = (self.chats.current, chat.title(items) if items else "New chat",
               float(items[-1]["at"]) if items else time.time())
        out = sorted([now] + [c for c in self.chats.listed() if c[0] != self.chats.current], key=lambda c: -c[2])
        return out if most is None else out[:most]

    def _fresh(self):
        siri = sys.modules.get("siri")
        if siri is not None and hasattr(siri, "CHAT_FROM"):
            siri.CHAT_FROM[0] = time.time()
        if siri is not None and hasattr(siri, "CHAT_FILES"):
            siri.CHAT_FILES.update(paths=[], at=0.0)

    def _show(self, items):
        self.thread.reset(items)
        for _, view in self.views:
            self.lines.removeWidget(view)
            view.deleteLater()
        self.views = []
        self.frames.found, self.frames.big = [], None
        self.frames_changed()
        self.jump = True
        self.clear_found(box=False)
        self.draw()

    def new_chat(self):
        self.save()
        if self.thread.items:
            self.chats.start()
            self._show([])
        self._fresh()
        QTimer.singleShot(60, self.focus_box)

    def open_chat(self, cid):
        if cid == self.chats.current:
            return
        self.save()
        items = self.chats.open(cid)
        if items is not None:
            self._show(items)
            self._fresh()

    def delete_chat(self, cid):
        self.save()
        if self.chats.delete(cid):
            self._show([])
            self._fresh()

    # ------------------------------------------------------------------ the box
    def shown(self):
        self.keep(force=True)
        QTimer.singleShot(60, self.focus_box)
        if self.empty_now:
            self.hero.timer.start()

    def focus_box(self):
        if self.window.current_tab == "home" and self.window.isActiveWindow():
            self.box.focus()

    def enter(self):
        if not self.box.voice_key("done"):
            if self.found_now:
                self.run_found(self.found_at)
            else:
                self.send()

    def send(self, text=None):
        """What's in the box, or text: after a slash, the first thing found is gone to; anything else is hers, a turn
        of yours, in the thread straight away."""
        text = " ".join((self.box.get() if text is None else text).split())
        files = list(self.box.files)
        if not text and not files:
            return
        if text.startswith("/") and not files:
            self._find(text)
            self.run_found(self.found_at)
            return
        self.box.clear()
        if files:
            self.box.take()
        self.clear_found(box=False)
        added = self.thread.you(text, files)
        if self.thread.waiting(chat.starting_why(self.window, self.thread)) or added:
            self.jump = True
            self.changed()
        if files:
            self.window.controls.put(("chat", text, files))
            return
        self.window.controls.put((chat.command_for(self.box.speaks), text))

    def typed(self):
        text = self.box.get()
        if text.startswith("/"):
            self._find(text)
        elif self.found_now or self.actions is not None:
            self.clear_found(box=False)

    def _find(self, text):
        if self.actions is None:
            self.actions = self.window.quick_actions()
        was = [a[1] for a in self.found_now]
        self.found_now = chat.find(self.actions, text[1:])
        if [a[1] for a in self.found_now] != was:
            self.found_at = 0
        self.found.show_found(self.found_now, self.found_at)
        if self.found_now:
            self.status.hide()
        elif len(text) > 1:
            self.status.setText("Nothing in her window is called that. Without the slash, she's asked.")
            self.status.show()
        else:
            self.status.hide()

    def move_found(self, step):
        if self.found_now:
            self.found_at = (self.found_at + step) % len(self.found_now)
            self.found.show_found(self.found_now, self.found_at)

    def clear_found(self, box=True):
        self.found_now, self.actions, self.found_at = [], None, 0
        self.found.show_found([], 0)
        self.status.hide()
        if box:
            self.box.clear()

    def run_found(self, i):
        if not 0 <= i < len(self.found_now):
            return
        what = self.found_now[i][3]
        self.clear_found()
        what()

    # ------------------------------------------------------------------ what stays
    def tick(self):
        if self.window.current_tab != "home":
            return
        self.ticks += 1
        self.keep(force=self.ticks % 6 == 0)
        if self.thread.status:
            self.live.update()

    def decide(self, action):
        task, store = self.waiting, getattr(self.window, "task_store", None)
        if task is None or store is None:
            return
        ok = store.cancel(task["id"]) if action == "cancel" else store.approve(task["id"])
        done = "cancelled" if action == "cancel" else "approved"
        self.thread._add("note", f"Task {task['id']} {done}." if ok else f"Task {task['id']} can't be {done} now.",
                         "" if ok else "failed")
        self.changed()
        self.keep(force=True)

    def keep(self, force=False):
        siri = sys.modules.get("siri")
        if force or self.kept is None:
            try:
                store = getattr(self.window, "task_store", None)
                self.waiting = chat.held(store.list(40) if store is not None else [])
            except Exception as exc:
                print(f"  chat: couldn't read the tasks ({exc!r})")
            self.notes = self._notes()
            if hasattr(self.window, "side"):
                self.window.side.lay_chats()
        self.kept = True
        items = self.rail.items(self.waiting, chat.pending_message(siri), self.notes)
        self.rail.show_items(items)
        self._lay_side(bool(items))

    def _notes(self):
        import assistant_ui as ui
        folder = getattr(ui, "NOTES_DIR", None)
        try:
            paths = [os.path.join(folder, n) for n in os.listdir(folder) if n.lower().endswith((".md", ".txt"))]
        except (OSError, TypeError):
            return []
        fresh = sorted((p for p in paths if time.time() - os.path.getmtime(p) < chat.Dock.NOTES_FOR),
                       key=os.path.getmtime, reverse=True)[:2]
        out = []
        for path in fresh:
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    out.append((path, f.read(600)))
            except OSError:
                pass
        return out

    def answer_words(self):
        last = next((i["text"] for i in reversed(self.thread.items) if i["kind"] == "her"), "")
        return frozenset(re.findall(r"[a-z]{4,}", last.lower()))

    def _screen_frame(self):
        vision = sys.modules.get("vision")
        last = getattr(vision, "LAST", None) or [None, 0.0, ""]
        if last[0] is not None and time.time() - float(last[1]) < 120 and \
                self.frames.add_picture(getattr(last[0], "small", None), last[2], self.turn_n):
            self._frames_here()
            self.toggle_frames(True)

    def _frames_here(self):
        last = next((i for i in reversed(self.thread.items) if i["kind"] == "you"), None)
        self.frames_after = id(last) if last is not None else None

    def toggle_frames(self, open_=None):
        self.frames_open = (not self.frames_open) if open_ is None else bool(open_)
        self.frames_changed()
        self.changed()

    def frames_changed(self):
        self.window.frames_n = len(self.frames.found)
        self.window.frames_open = self.frames_open and bool(self.frames.found)
        if hasattr(self.window, "top"):
            self.window.lay_head()
