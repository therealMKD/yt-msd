# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.ui.widgets).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
from PySide6.QtWidgets import QWidget, QLabel, QPushButton, QSlider, QSizePolicy, QStyle, QStyleOption
from PySide6.QtCore import Qt, Signal, QTimer, QEvent, QObject
from PySide6.QtGui import QPixmap, QImage, QPainter, QPainterPath, QDrag, QFontMetrics, QCursor
from PySide6.QtCore import QMimeData
from yt_msd.ui.theme import get_accent_color


def pil_to_qpixmap(pil_image):
    if pil_image is None: return QPixmap()
    img = pil_image.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg)



class ClickableSlider(QSlider):
    """A QSlider that seeks immediately on mouse press (click-to-seek), not just drag."""
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._seeking = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Compute value from click position
            val = QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(),
                event.position().toPoint().x(), self.width()
            )
            self._seeking = True
            self.setValue(val)
            self._seeking = False
            # Emit sliderMoved so on_seek fires
            self.sliderMoved.emit(val)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            val = QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(),
                event.position().toPoint().x(), self.width()
            )
            self.setValue(val)
            self.sliderMoved.emit(val)
        super().mouseMoveEvent(event)



class DoubleClickButton(QPushButton):
    """QPushButton that only triggers its primary action on double-click.

    A single left-click is reported through `singleClicked` instead of the
    standard `clicked` signal, so callers can use single clicks for selection
    (the way File Explorer does) while double clicks open or play the item."""
    doubleClicked = Signal()
    singleClicked = Signal()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        # Absorb single click so it doesn't trigger clicked signal for playback
        # (still allow default visual press styling)
        if event.button() == Qt.LeftButton:
            self.setFocus()
            self.singleClicked.emit()
        event.accept()



class _ElideTextFilter(QObject):
    """Event filter that lets a title widget shrink so sibling badge widgets
    (duration / channel labels) always keep their full width. The title text is
    elided with an ellipsis to whatever width the layout actually gives it."""

    def __init__(self, full_text, reserve=12):
        super().__init__()
        self._full = full_text
        self._reserve = reserve
        self._widget = None

    def attach(self, widget):
        self._widget = widget
        widget.installEventFilter(self)
        sp = widget.sizePolicy()
        sp.setHorizontalPolicy(QSizePolicy.Ignored)
        sp.setHorizontalStretch(1)
        widget.setSizePolicy(sp)
        widget.setMinimumWidth(0)
        self._relayout(widget)
        return self

    def set_full_text(self, text):
        self._full = text
        if self._widget is not None:
            self._relayout(self._widget)

    def eventFilter(self, obj, event):
        if obj is self._widget and event.type() in (QEvent.Resize, QEvent.Show):
            self._relayout(obj)
        return False

    def _relayout(self, widget):
        avail = widget.width() - self._reserve
        if avail <= 0:
            return
        fm = QFontMetrics(widget.font())
        full = self._full
        new_text = full if fm.horizontalAdvance(full) <= avail else fm.elidedText(full, Qt.ElideRight, avail)
        if new_text != widget.text():
            widget.setText(new_text)



class DraggableQueueWidget(QWidget):
    """Queue container widget that supports drag-and-drop reordering of pending items."""
    order_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAcceptDrops(True)
        self._drag_start_pos = None
        self._drag_source_widget = None

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, p, self)

    def get_item_at(self, pos):
        for i in range(self.layout().count()):
            w = self.layout().itemAt(i).widget()
            if w and w.geometry().contains(pos):
                return i, w
        return None, None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            idx, w = self.get_item_at(event.position().toPoint())
            if w is not None:
                q = w.property("queue_item")
                if q and q.get('status') == 'Pending':
                    self._drag_start_pos = event.position().toPoint()
                    self._drag_source_widget = w
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._drag_source_widget and self._drag_start_pos and
                event.buttons() & Qt.LeftButton):
            dist = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            if dist > 6:
                drag = QDrag(self)
                mime = QMimeData()
                lay = self.layout()
                src_idx = -1
                for i in range(lay.count()):
                    if lay.itemAt(i).widget() == self._drag_source_widget:
                        src_idx = i
                        break
                mime.setText(str(src_idx))
                drag.setMimeData(mime)
                drag.exec(Qt.MoveAction)
        super().mouseMoveEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        src_idx = int(event.mimeData().text())
        drop_pos = event.position().toPoint()
        dst_idx, _ = self.get_item_at(drop_pos)
        if dst_idx is None:
            dst_idx = self.layout().count() - 1
        if src_idx != dst_idx and dst_idx >= 0:
            # Store the indices then emit once - the handler reads _pending_reorder
            # to do the actual reorder. Emitting before the store would fire the
            # handler with the previous drop's stale indices.
            self._pending_reorder = (src_idx, dst_idx)
            self.order_changed.emit()
        event.acceptProposedAction()
        self._drag_start_pos = None
        self._drag_source_widget = None



# The box a result thumbnail sits in, and the colour that box wears when the track
# it belongs to is the one the player is holding. See _refresh_playback_highlights.
# The tile is the outside of the box and it does not move: how much of the box shows
# around the picture is set by growing the picture until it covers the tile down to
# THUMB_BOX_INSET on every side (cover_thumbnail). Growing the picture is the only way
# to thin the band, because the band IS the leftover - scaling to fit inside the tile
# kept the aspect ratio and spent the leftover on the box, which is why it read as far
# thicker than the inset it was built with: a 16:9 thumbnail fitted into this 1.8:1 tile
# showed 6 px of colour down each side and 3 top and bottom, and a legacy 4:3 thumbnail
# showed 16 at the sides.
# The other thing that eats the box is the app stylesheet: QLabel is a QFrame, and the
# stylesheet pads every QFrame by 5 px ("QFrame { ... padding: 5px; }"). A padded label
# draws a frame of its own around the picture - it even scales the picture down into the
# padded rect - so 5 px of frame shows whatever the inset is, and an inset change is
# invisible. So the tile behind wears the colour, and the label is the size of the picture
# and carries no padding of its own.
THUMB_TILE_W = 90

THUMB_TILE_H = 50

# Two pixels, not one: at one pixel the frame vanished into the anti-aliasing on a light
# theme and the play state was impossible to read. The tile never changes size, so a wider
# inset just means the picture is cut back further.
THUMB_BOX_INSET = 2

THUMB_BOX_W = THUMB_TILE_W - 2 * THUMB_BOX_INSET

THUMB_BOX_H = THUMB_TILE_H - 2 * THUMB_BOX_INSET

# The curve of the box's corners, and the curve the picture inside it is cut to so the
# two follow the same circle instead of a square-cornered picture inside a round frame.
# The box is always the inset wider than the picture at every point of that circle, which
# is what keeps the frame an even thickness into the corners as well as down the sides.
THUMB_BOX_RADIUS = 4

THUMB_IMG_RADIUS = THUMB_BOX_RADIUS - THUMB_BOX_INSET


THUMB_BOX_PLAIN = "#2b2b2b"     # the box of every row that is not the loaded track

THUMB_BOX_PLAYING = "#1abd33"   # the box of the track the player is running

THUMB_BOX_PAUSED = "#FF8C00"    # the box of the loaded track, held where it stopped


# What a row is told about the player - "playing" or "paused", the same tokens the local
# rows carry as their play_state property - and the colour the thumbnail box wears for it.
THUMB_BOX_COLORS = {"playing": THUMB_BOX_PLAYING, "paused": THUMB_BOX_PAUSED}


# The play button on a thumbnail belongs to the pointer, not to the row: it is there while the
# pointer is on that thumbnail and gone the moment it is not. Qt is what normally says when that
# changes, and it can fail to say so. Scrolling the results list moves a row out from under a
# pointer that never moved, and Qt sends no Leave for a pointer that did not move; a row torn
# down by that same scroll still paints - with its button up - until its deleteLater lands, which
# leaves the button of a row that no longer exists sitting on whatever row is now there; and a
# row built by that same scroll can land under a pointer that never moved, for which Qt sends no
# Enter at all. So the button is decided by asking the pointer where it is rather than by
# trusting whichever event last arrived, and while a button is up that question is asked again on
# this interval - a cost that only exists while a row is actually being pointed at.
# See ThumbnailWidget._pointer_on_tile and MainApp._recheck_thumb_hover.
THUMB_HOVER_RECHECK_MS = 200



def cover_thumbnail(pixmap, width=THUMB_BOX_W, height=THUMB_BOX_H, radius=THUMB_IMG_RADIUS):
    """Scale a thumbnail until it covers width x height, cut back to that size keeping the
    middle, and round its corners to sit inside the box's own curve. Covering rather than
    fitting is what makes the box the same thickness on all four sides: the box colour is
    what is left over after the picture is placed, and a fitted 16:9 picture leaves its
    spare width as a wide band of colour down each side."""
    if pixmap.isNull():
        return pixmap
    scaled = pixmap.scaled(width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    w, h = min(width, scaled.width()), min(height, scaled.height())
    cropped = scaled.copy((scaled.width() - w) // 2, (scaled.height() - h) // 2, w, h)
    if radius <= 0:
        return cropped
    masked = QPixmap(w, h)
    masked.fill(Qt.transparent)
    painter = QPainter(masked)
    painter.setRenderHint(QPainter.Antialiasing)
    corners = QPainterPath()
    corners.addRoundedRect(0, 0, w, h, radius, radius)
    painter.setClipPath(corners)
    painter.drawPixmap(0, 0, cropped)
    painter.end()
    return masked



class ThumbnailWidget(QWidget):

    def __init__(self, video, parent_app, parent=None):
        super().__init__(parent)
        self.setFixedSize(THUMB_TILE_W, THUMB_TILE_H)
        self.video = video
        self.parent_app = parent_app
        
        self.box_color = THUMB_BOX_PLAIN
        # Without this attribute the tile's background is painted from the palette, which is a
        # flat rectangle and ignores the rounded corners the stylesheet asks for - the picture
        # inside would be cut round inside a box with square ones.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._box_style(f"background-color: {THUMB_BOX_PLAIN}; border-radius: {THUMB_BOX_RADIUS}px;")

        self.thumb_label = QLabel(self)
        self.thumb_label.setFixedSize(THUMB_BOX_W, THUMB_BOX_H)
        self.thumb_label.move(THUMB_BOX_INSET, THUMB_BOX_INSET)
        # Its own stylesheet is what keeps the picture the size it was made: without it the
        # app's QFrame padding takes 5 px off every side and the label scales the picture
        # down to fit, which is a frame nobody asked for.
        self.thumb_label.setStyleSheet("background: transparent; border: none; padding: 0px;")
        self.thumb_label.setAlignment(Qt.AlignCenter)
        
        accent = get_accent_color(parent_app.accent_color_name)
        self.play_btn = QPushButton("\uE768", self)
        self.play_btn.setToolTip("Play this track")
        self.play_btn.setFixedSize(30, 30)
        self.play_btn.move(30, 10)
        self.play_btn.setStyleSheet(f"background: rgba(0,0,0,180); color: {accent}; border-radius: 15px; font-weight: bold; font-family: 'Segoe MDL2 Assets'; font-size: 14px; padding: 0px;")
        self.play_btn.clicked.connect(self.on_play)
        self.play_btn.hide()
        
    def _pointer_on_tile(self):
        """True when the pointer is on this tile right now.

        Asked of the pointer rather than remembered from the last Enter or Leave, because a
        row can be handed an Enter by a pointer that has since moved off it, and a row can be
        left holding its button up by a departure Qt never announced: scrolling the results
        list moves rows out from under a pointer that stayed where it was, and Qt sends no
        Leave for a pointer that did not move. What a position cannot tell is another
        application's window sitting on top of this one at the same coordinates - there the
        pointer genuinely is over these pixels - and that case is left to Qt, which does report
        it as a Leave once the cursor physically leaves the window.
        """
        try:
            if not self.isVisible():
                # A row the pane has scrolled out of, or one being torn down, is not under the
                # pointer whatever its rectangle says, and its button must not survive it.
                return False
            return self.rect().contains(self.mapFromGlobal(QCursor.pos()))
        except RuntimeError:
            return False  # the row was torn down between the asking and the answering

    def set_pointer_hover(self, on):
        """Put the play button in the state the pointer warrants, and tell the app which row
        owns it.

        Only one row at a time may show the button. That is what limits the damage from a
        departure Qt never reported: the stale button is taken off as soon as any other row is
        pointed at, and MainApp._recheck_thumb_hover catches the case where no other row ever
        is. The button is raised on its tile as it is shown, so a row rebuilt around it cannot
        end up with the picture painted over the button.
        """
        try:
            if on:
                self.play_btn.show()
                self.play_btn.raise_()
                self.parent_app._note_thumb_hover(self)
            else:
                self.play_btn.hide()
                self.parent_app._forget_thumb_hover(self)
        except RuntimeError:
            pass  # this row was torn down partway through claiming it

    def refresh_play_button(self):
        """Show the button when the pointer is on this tile and hide it when it is not, reading
        the pointer rather than whichever event last happened to arrive."""
        self.set_pointer_hover(self._pointer_on_tile())

    def _refresh_after_layout(self):
        """The deferred half of showEvent: the row is not yet where the layout is going to put
        it, and the button has to be decided against the position it ends up at."""
        try:
            self.refresh_play_button()
        except RuntimeError:
            pass  # the row was torn down before the deferral landed

    def on_play(self, checked=False):
        self.parent_app.play_result(self.video)
        
    def enterEvent(self, event):
        # Qt says the pointer came onto the row; the pointer is still what decides, because a
        # row can be handed an Enter by a pointer that has already moved off it.
        self.set_pointer_hover(self._pointer_on_tile())
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        self.set_pointer_hover(False)
        super().leaveEvent(event)

    def showEvent(self, event):
        # A lazy build puts a row under a pointer that has not moved, and Qt sends no Enter for
        # a pointer that has not moved - which is the row whose button never appears until the
        # mouse is wiggled. Deferred because the layout has not placed the row yet, and skipped
        # outright when the pointer is not even in this window, which is most rows most of the
        # time: scrolling a list while the pointer sits over the player bar builds rows that
        # have no hope of being pointed at.
        window = self.window()
        if window is not None and window.rect().contains(window.mapFromGlobal(QCursor.pos())):
            QTimer.singleShot(0, self._refresh_after_layout)
        super().showEvent(event)

    def hideEvent(self, event):
        # The row went away under the pointer - the pane scrolled it out, or it is being torn
        # down - and nothing else is going to tell this row the pointer is no longer on it.
        self.set_pointer_hover(False)
        super().hideEvent(event)

    def _box_style(self, style):
        """Put the colour of the box on the tile rather than on the label. The label is a
        QFrame, and the app stylesheet pads every QFrame by 5 px, so a coloured label paints
        a 5 px frame of its own around the picture however thin the inset is. The tile is a
        plain QWidget, which that rule does not pad, and so it shows the inset exactly as
        written."""
        self.setStyleSheet(style)

    def set_highlight(self, play_state):
        """Wear the colour of what the player is doing with this track: green while it
        runs, orange while it is held where it stopped, and the plain grey the row started
        with for everything else - including a row whose state is not known any more."""
        color = THUMB_BOX_COLORS.get(play_state, THUMB_BOX_PLAIN)
        if self.box_color == color:
            return
        self.box_color = color
        self._box_style(f"background-color: {color}; border-radius: {THUMB_BOX_RADIUS}px;")
