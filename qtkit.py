"""What every part of her Qt window is made of (22 November 2026, the owner's choice of Qt over Tk: "change to
another one", after the Tk window broke in one way or another every time it changed): her type, the Tk window's
colours, and small pieces Qt draws itself, crisp at any scaling: an icon button with a soft square under the mouse, a
pill, words cut short to their room, her face, and the wheel's glide."""
import os

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QRectF, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractButton, QGraphicsOpacityEffect, QLabel, QSizePolicy, QVBoxLayout, QWidget

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "assets", "fonts")
TYPE = 0.9  # her sizes against Hedwig's CSS px, as the Tk window draws them (assistant_ui.TYPE)
# the Tk window's own (assistant_ui): white pages, near-black words, slate for what's about them, Hedwig's blue
BG, TEXT, MUTED, FAINT, LINE, BLUE, ERROR = "#ffffff", "#111827", "#6b7280", "#9ca3af", "#e5e7eb", "#5090f7", "#c42b1c"
HOVER = "#f1f1f2"  # an icon button's square under the mouse
FAMILIES = {"words": "Segoe UI", "greeting": "Segoe UI", "icons": "Segoe MDL2 Assets"}
WEIGHTS = {"regular": QFont.Weight.Normal, "medium": QFont.Weight.Medium, "semibold": QFont.Weight.DemiBold,
           "bold": QFont.Weight.Bold}


def load_type():
    """Geist (the words), Plus Jakarta Sans (the greeting) and the icon font, for this process only. FAMILIES: what
    Qt knows each by, Windows' own where one isn't there."""
    try:
        for name in os.listdir(FONT_DIR):
            if name.startswith(("Geist", "PlusJakarta", "Figtree")) and name.lower().endswith((".ttf", ".otf")):
                QFontDatabase.addApplicationFont(os.path.join(FONT_DIR, name))
    except OSError as exc:
        print(f"  qt: couldn't load her type ({exc!r})")
    have = set(QFontDatabase.families())
    FAMILIES["words"] = next((f for f in ("Geist", "Figtree") if f in have), "Segoe UI")
    FAMILIES["greeting"] = "Plus Jakarta Sans" if "Plus Jakarta Sans" in have else FAMILIES["words"]
    FAMILIES["icons"] = "Segoe Fluent Icons" if "Segoe Fluent Icons" in have else "Segoe MDL2 Assets"
    return dict(FAMILIES)


def font(css, weight="regular", family="words"):
    """Her type at css px of Hedwig's, drawn at TYPE of that as the Tk window has it, in weight."""
    f = QFont(FAMILIES.get(family, family))
    f.setPointSizeF(max(1.0, css * TYPE * 0.75))  # Qt's points: 0.75 of a pixel at its 96 a logical inch
    f.setWeight(WEIGHTS.get(weight, QFont.Weight.Normal))
    return f


def icon_font(css):
    return font(css, family="icons")


def qc(colour, alpha=1.0):
    """A colour as Qt's, "#rrggbb", at alpha."""
    c = QColor(colour)
    if alpha < 1.0:
        c.setAlphaF(max(0.0, alpha))
    return c


def mix(a, b, t):
    """Colour a towards b by t (0 a, 1 b), "#rrggbb"."""
    ca, cb = QColor(a), QColor(b)
    t = max(0.0, min(1.0, t))
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in ((ca.red(), cb.red()), (ca.green(), cb.green()),
                                                                        (ca.blue(), cb.blue())))


def width_of(f, text):
    """How wide text is in the font f, logical px."""
    return QFontMetricsF(f).horizontalAdvance(text)


def fit(f, text, width):
    """text cut short to width px in f, an ellipsis where it's cut."""
    return QFontMetricsF(f).elidedText(text, Qt.TextElideMode.ElideRight, width)


def animations_on():
    """False when Windows' animations are off (better-motion's reduced-motion gate), as chat.animations_on."""
    try:
        import chat
        return chat.animations_on()
    except Exception:
        return True


def qimage(rgba):
    """A numpy picture (h, w, 4), premultiplied, 0 to 1 or 0 to 255, as a QImage with its own pixels."""
    import numpy as np
    a = rgba if rgba.dtype == np.uint8 else (np.clip(rgba, 0.0, 1.0) * 255 + 0.5).astype(np.uint8)
    a = np.ascontiguousarray(a)
    h, w = a.shape[:2]
    return QImage(a.data, w, h, 4 * w, QImage.Format.Format_RGBA8888_Premultiplied).copy()


def logo(h, open_=1.0, dpr=1.0):
    """Her island as the sidebar shows it (island.logo), h logical px tall, sharp at the screen's scaling dpr, with its
    own alpha. None if it can't be drawn."""
    try:
        import island
        pm = QPixmap.fromImage(qimage(island.logo(max(4, round(h * dpr)), open_)))
        pm.setDevicePixelRatio(dpr)
        return pm
    except Exception as exc:
        print(f"  qt: couldn't draw her logo ({exc!r})")
        return None


def face(h, dpr=1.0, skin="#d1d5db", eyes="#1f2937"):
    """Her face by her words in the chat: her island's own capsule and eyes (island.logo), a soft grey with dark eyes
    as chat._face draws it, h logical px tall. None if it can't be drawn: her words stand without it."""
    try:
        import numpy as np
        import island
        rgba = island.logo(max(4, round(h * dpr)), 1.0)
        light = rgba[..., :3].mean(axis=2, keepdims=True)  # 0 its capsule, 1 its eyes
        hue = lambda c: np.array([int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)], np.float32)  # noqa: E731
        ink = hue(skin) * (1 - light) + hue(eyes) * light
        alpha = rgba[..., 3:]
        pm = QPixmap.fromImage(qimage(np.concatenate([ink * alpha, alpha], axis=2)))
        pm.setDevicePixelRatio(dpr)
        return pm
    except Exception as exc:
        print(f"  qt: couldn't draw her face ({exc!r})")
        return None


class IconButton(QAbstractButton):
    """An icon in the icon font with a soft square under the mouse and 96% of itself while it's pressed (better-motion's
    press scale): the pencil, the bell, the panel icon. colour its glyph's, hot its colour under the mouse, back the
    square's (None for none)."""

    def __init__(self, glyph, tip="", size=30, css=15, colour=MUTED, hot=TEXT, back=HOVER, radius=8, parent=None):
        super().__init__(parent)
        self.glyph, self.colour, self.hot, self.back, self.radius = glyph, colour, hot, back, radius
        self.glyph_font = icon_font(css)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)  # a click leaves the keyboard where it was (the box)
        if tip:
            self.setToolTip(tip)
            self.setAccessibleName(tip)

    def set_glyph(self, glyph):
        self.glyph = glyph
        self.update()

    def focusInEvent(self, e):
        self.keyboard = e.reason() in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason)
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        self.keyboard = False
        super().focusOutEvent(e)

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        over = self.underMouse() and self.isEnabled()
        r = QRectF(self.rect())
        if self.isDown():
            p.translate(r.center())
            p.scale(0.96, 0.96)
            p.translate(-r.center())
        if (over or (self.hasFocus() and getattr(self, "keyboard", False))) and self.back:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(self.back))
            p.drawRoundedRect(r, self.radius, self.radius)
        p.setFont(self.glyph_font)
        p.setPen(qc(self.hot if over else self.colour))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.glyph)


class Pill(QAbstractButton):
    """Words on a soft round pill, with a dot or an icon before them: her state at the top, Full access, a source.
    fill the pill's, ink the words', glyph_ink the icon's or dot's; height its height, pad in from its ends."""

    def __init__(self, text="", fill="#f4f4f5", ink=MUTED, css=12.5, weight="regular", glyph=None, glyph_ink=None,
                 dot=None, height=26, pad=12, radius=None, click=False, parent=None):
        super().__init__(parent)
        self.text_, self.fill, self.ink, self.glyph, self.dot = text, fill, ink, glyph, dot
        self.glyph_ink = glyph_ink or ink
        self.words_font, self.glyph_font = font(css, weight), icon_font(css * 0.86)
        self.h, self.pad = height, pad
        self.radius = height / 2 if radius is None else radius
        self.detail = ""  # more, after the words, in their colour: what she's at while she starts
        self.breath = None  # 0 to 1 while the dot breathes (StatusPill)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus if click else Qt.FocusPolicy.NoFocus)
        if click:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._size()

    def set_text(self, text, detail=None):
        self.text_ = text
        if detail is not None:
            self.detail = detail
        self._size()
        self.update()

    def _lead(self):
        """How far in the words start: past the dot or the icon, if there is one."""
        if self.dot:
            return self.pad + 12
        if self.glyph:
            return self.pad + width_of(self.glyph_font, self.glyph) + 6
        return self.pad

    def _size(self):
        w = self._lead() + width_of(self.words_font, self.text_) + self.pad
        if self.detail:
            w += 8 + width_of(self.words_font, self.detail)
        self.setFixedWidth(int(w + 0.999))

    def sizeHint(self):
        return QSize(self.width(), self.h)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        fill = self.fill
        if self.isDown():
            p.translate(r.center())
            p.scale(0.96, 0.96)
            p.translate(-r.center())
        if self.underMouse() and self.cursor().shape() == Qt.CursorShape.PointingHandCursor:
            fill = mix(fill, "#000000", 0.04)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(fill))
        p.drawRoundedRect(r, self.radius, self.radius)
        mid = r.height() / 2
        if self.dot:
            colour = self.dot if self.breath is None else mix(self.dot, self.fill, 0.45 * self.breath)
            p.setBrush(qc(colour))
            p.drawEllipse(QRectF(self.pad + 2 - 3.2, mid - 3.2, 6.4, 6.4))
        elif self.glyph:
            p.setFont(self.glyph_font)
            p.setPen(qc(self.glyph_ink))
            p.drawText(QRectF(self.pad, 0, r.width(), r.height()), Qt.AlignmentFlag.AlignVCenter, self.glyph)
        p.setFont(self.words_font)
        p.setPen(qc(self.ink))
        x = self._lead()
        p.drawText(QRectF(x, 0, r.width() - x, r.height()), Qt.AlignmentFlag.AlignVCenter, self.text_)
        if self.detail:
            x += width_of(self.words_font, self.text_) + 8
            p.drawText(QRectF(x, 0, r.width() - x, r.height()), Qt.AlignmentFlag.AlignVCenter, self.detail)


class StatusPill(Pill):
    """Her state at the top: a small dot in its colour and the word, on a soft grey pill, the dot breathing while
    she's at something (assistant_ui._draw_dot); what she's at after it only while it's worth reading."""

    def __init__(self, parent=None):
        super().__init__("Starting", dot="#d97706", parent=parent)
        self.t0, self.timer = 0.0, QTimer(self, interval=33, timeout=self._breathe)

    def set_state(self, text, colour, busy, detail=""):
        self.dot = colour
        self.set_text(text, fit(self.words_font, detail, 220) if detail else "")
        if busy and not self.timer.isActive():
            import time
            self.t0 = time.perf_counter()
            self.timer.start()
        elif not busy:
            self.timer.stop()
            self.breath = None
            self.update()

    def _breathe(self):
        import math
        import time
        phase = (time.perf_counter() - self.t0) % 1.3 / 1.3
        self.breath = 0.5 - 0.5 * math.cos(phase * 2 * math.pi)
        self.update()


class Elided(QLabel):
    """Words in one line, cut short with an ellipsis to the room they're given."""

    def __init__(self, text="", f=None, colour=TEXT, parent=None):
        super().__init__(parent)
        self.full = text
        if f is not None:
            self.setFont(f)
        self.setStyleSheet(f"color: {colour}; background: transparent;")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(10)
        self._fit()

    def set_text(self, text):
        self.full = text
        self._fit()

    def resizeEvent(self, e):
        self._fit()
        super().resizeEvent(e)

    def _fit(self):
        super().setText(fit(self.font(), self.full, max(10, self.width())))
        self.setToolTip(self.full if self.text() != self.full else "")


class Glide(QObject):
    """The wheel's glide, as the Tk window's (assistant_ui.Glide): each notch adds to where the page is going and it
    gets there over 200 ms, easing out; at once with Windows' animations off."""

    def __init__(self, area, notch=96):
        super().__init__(area)
        self.bar, self.notch, self.target = area.verticalScrollBar(), notch, None
        self.anim = QVariantAnimation(self, duration=200, easingCurve=QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(lambda v: self.bar.setValue(round(v)))
        self.anim.finished.connect(lambda: setattr(self, "target", None))
        area.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Type.Wheel:
            return False
        dy = event.angleDelta().y() or 0
        if not dy:
            return False
        if event.pixelDelta().y() and not event.angleDelta().x():  # a touchpad's own smooth scroll: as it comes
            self.anim.stop()
            self.target = None
            self.bar.setValue(self.bar.value() - event.pixelDelta().y())
            return True
        start = self.bar.value()
        base = self.target if self.target is not None and self.anim.state() == QVariantAnimation.State.Running \
            else start
        self.target = max(self.bar.minimum(), min(self.bar.maximum(), base - dy / 120 * self.notch))
        self.anim.stop()
        if not animations_on():
            self.bar.setValue(round(self.target))
            self.target = None
            return True
        self.anim.setStartValue(float(start))
        self.anim.setEndValue(float(self.target))
        self.anim.start()
        return True

    def stop(self):
        self.anim.stop()
        self.target = None


class Rise(QWidget):
    """A widget in a layout that comes in rising a few px and from clear to whole (come_in), without moving what's
    round it: its room stays the same while what's in it rises."""

    def __init__(self, child, rise=10, parent=None):
        super().__init__(parent)
        self.child, self.rise = child, rise
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, rise)
        self.lay.setSpacing(0)
        self.lay.addWidget(child, 0, Qt.AlignmentFlag.AlignHCenter)
        self.anim = None

    def come_in(self, delay=0, ms=420):
        """Up into place and whole, ms after delay (a 60 ms stagger between parts reads as one entrance)."""
        if not animations_on():
            self.lay.setContentsMargins(0, 0, 0, self.rise)
            return
        fx = QGraphicsOpacityEffect(self.child)
        fx.setOpacity(0.0)
        self.child.setGraphicsEffect(fx)
        self.lay.setContentsMargins(0, self.rise, 0, 0)
        anim = QVariantAnimation(self, duration=ms, startValue=0.0, endValue=1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def step(t):
            r = round(self.rise * (1 - spring(t)))
            self.lay.setContentsMargins(0, max(0, r), 0, self.rise - max(0, r))
            try:
                fx.setOpacity(min(1.0, t * 1.4))
            except RuntimeError:  # gone meanwhile
                pass

        def done():
            self.lay.setContentsMargins(0, 0, 0, self.rise)
            self.child.setGraphicsEffect(None)  # nothing between it and the screen once it's in
        anim.valueChanged.connect(step)
        anim.finished.connect(done)
        self.anim = anim
        QTimer.singleShot(max(0, delay), anim.start)


def spring(t):
    """A spring's way to 1 (stiffness 350, damping 30, as chat.spring), a touch past it and back."""
    try:
        import chat
        return chat.spring(t)
    except Exception:
        return 1 - (1 - t) ** 3


def fade_in(widget, ms=240, delay=0):
    """widget from clear to whole over ms, after delay; nothing with Windows' animations off."""
    if not animations_on():
        return None
    fx = QGraphicsOpacityEffect(widget)
    fx.setOpacity(0.0)
    widget.setGraphicsEffect(fx)
    anim = QVariantAnimation(widget, duration=ms, startValue=0.0, endValue=1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def step(v):
        try:
            fx.setOpacity(v)
        except RuntimeError:
            pass

    def done():
        try:
            widget.setGraphicsEffect(None)
        except RuntimeError:
            pass
    anim.valueChanged.connect(step)
    anim.finished.connect(done)
    QTimer.singleShot(max(0, delay), anim.start)
    widget._fade = anim  # kept with it, or Python lets it go
    return anim
