from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from .text_item import TextItem


class TimelineWidget(QWidget):
    scrub_moved = Signal(float)
    seek_requested = Signal(float)
    range_changed = Signal(float, float)
    position_changed = Signal(float)
    range_dragging = Signal(str, float, float)

    text_selected = Signal(object)            # int | None
    text_changed = Signal(int, float, float)  # id, start_sec, end_sec
    text_double_click = Signal(int)           # id
    texts_changed = Signal()                  # daftar teks berubah

    HANDLE_HIT = 10
    PLAYHEAD_HIT = 6
    MIN_CLIP = 0.2

    MIN_STRIP_HEIGHT = 64
    MIN_RULER_HEIGHT = 26
    RULER_GAP = 4

    MIN_TEXT_TRACK_HEIGHT = 30
    TEXT_TRACK_GAP = 4
    MIN_TEXT_DURATION = 0.3
    TEXT_HANDLE_HIT = 6
    SNAP_PX = 6
    DEFAULT_TEXT_DURATION = 3.0

    TEXT_CLOSE_SIZE = 14
    TEXT_CLOSE_MARGIN = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.duration = 0.0
        self.start_sec = 0.0
        self.end_sec = 0.0
        self.playhead_sec = 0.0
        self._thumbs: list[QPixmap] = []
        self._dragging: str | None = None
        self._hover: str | None = None

        self._texts: list[TextItem] = []
        self._selected_text: int | None = None
        self._next_text_id: int = 1
        self._drag_text_id: int | None = None
        self._drag_text_origin: tuple[float, float] | None = None
        self._snap_guide_sec: float | None = None

        self.setMinimumHeight(
            self.MIN_STRIP_HEIGHT
            + self.MIN_TEXT_TRACK_HEIGHT
            + self.MIN_RULER_HEIGHT
            + self.RULER_GAP
            + self.TEXT_TRACK_GAP
            + 6
        )
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    # ---------- public API: state ----------
    def set_duration(self, duration: float):
        self.duration = max(0.0, float(duration))
        if self.end_sec <= self.start_sec or self.end_sec > self.duration:
            self.end_sec = self.duration
        self.playhead_sec = min(self.playhead_sec, self.duration)
        for it in self._texts:
            it.clamp(self.duration, self.MIN_TEXT_DURATION)
        self._texts.sort(key=lambda t: t.start_sec)
        self.update()

    def set_range(self, start_sec: float, end_sec: float):
        start = max(0.0, min(float(start_sec), self.duration))
        end = max(0.0, min(float(end_sec), self.duration))
        if end - start < self.MIN_CLIP:
            end = min(self.duration, start + self.MIN_CLIP)
        self.start_sec, self.end_sec = start, end
        self.update()

    def set_playhead(self, sec: float):
        sec = max(0.0, min(float(sec), self.duration))
        if abs(sec - self.playhead_sec) > 1e-6:
            self.playhead_sec = sec
            self.update()
            self.position_changed.emit(sec)

    def start_seconds(self) -> float:
        return self.start_sec

    def end_seconds(self) -> float:
        return self.end_sec

    def playhead_seconds(self) -> float:
        return self.playhead_sec

    # ---------- public API: thumbnail ----------
    def thumbnail_count(self) -> int:
        return len(self._thumbs)

    def thumbnail_at(self, index: int) -> QPixmap:
        if 0 <= index < len(self._thumbs):
            return self._thumbs[index]
        return QPixmap()

    def thumbnail_nearest(self, sec: float) -> QPixmap:
        n = len(self._thumbs)
        if n == 0 or self.duration <= 0:
            return QPixmap()
        idx = int((max(0.0, min(sec, self.duration)) / self.duration) * n)
        idx = max(0, min(idx, n - 1))
        return self._thumbs[idx]

    def set_thumbnail_at(self, index: int, image: QImage):
        while len(self._thumbs) <= index:
            self._thumbs.append(QPixmap())
        self._thumbs[index] = QPixmap.fromImage(image)
        self.update()

    def set_thumbnails_count(self, count: int):
        if count <= 0:
            self._thumbs = []
        else:
            while len(self._thumbs) < count:
                self._thumbs.append(QPixmap())
        self.update()

    def clear_thumbnails(self):
        self._thumbs = []
        self.update()

    def clear_texts(self):
        if not self._texts and self._selected_text is None:
            return
        self._texts = []
        self._selected_text = None
        self._next_text_id = 1
        self.text_selected.emit(None)
        self.texts_changed.emit()
        self.update()

    def loaded_thumbnail_count(self) -> int:
        return sum(1 for p in self._thumbs if not p.isNull())

    # ---------- public API: text track ----------
    def set_texts(self, items: list[TextItem]):
        self._texts = []
        for it in items:
            if it.id < 0:
                it.id = self._next_text_id
                self._next_text_id += 1
            else:
                self._next_text_id = max(self._next_text_id, it.id + 1)
            it.clamp(self.duration, self.MIN_TEXT_DURATION)
            self._texts.append(it)
        self._texts.sort(key=lambda t: t.start_sec)
        if (
            self._selected_text is not None
            and not any(t.id == self._selected_text for t in self._texts)
        ):
            self._selected_text = None
            self.text_selected.emit(None)
        self.texts_changed.emit()
        self.update()

    def texts(self) -> list[TextItem]:
        return list(self._texts)

    def add_text(self, item: TextItem) -> int:
        if item.id < 0:
            item.id = self._next_text_id
            self._next_text_id += 1
        item.clamp(self.duration, self.MIN_TEXT_DURATION)
        self._texts.append(item)
        self._texts.sort(key=lambda t: t.start_sec)
        self._selected_text = item.id
        self.text_selected.emit(item.id)
        self.text_changed.emit(item.id, item.start_sec, item.end_sec)
        self.texts_changed.emit()
        self.update()
        return item.id

    def update_text(self, text_id: int, **kwargs) -> bool:
        for it in self._texts:
            if it.id == text_id:
                for k, v in kwargs.items():
                    if hasattr(it, k):
                        setattr(it, k, v)
                it.clamp(self.duration, self.MIN_TEXT_DURATION)
                self._texts.sort(key=lambda t: t.start_sec)
                self.text_changed.emit(it.id, it.start_sec, it.end_sec)
                self.texts_changed.emit()
                self.update()
                return True
        return False

    def remove_text(self, text_id: int) -> bool:
        for i, it in enumerate(self._texts):
            if it.id == text_id:
                self._texts.pop(i)
                if self._selected_text == text_id:
                    self._selected_text = None
                    self.text_selected.emit(None)
                self.texts_changed.emit()
                self.update()
                return True
        return False

    def selected_text_id(self) -> int | None:
        return self._selected_text

    def select_text(self, text_id: int | None):
        if self._selected_text == text_id:
            return
        self._selected_text = text_id
        self.text_selected.emit(text_id)
        self.update()

    def text_at_sec(self, sec: float) -> TextItem | None:
        for it in self._texts:
            if it.start_sec <= sec <= it.end_sec:
                return it
        return None

    def texts_active_at(self, sec: float) -> list[TextItem]:
        return [t for t in self._texts if t.start_sec <= sec <= t.end_sec]

    # ---------- persistence (ready, unused) ----------
    def texts_to_dict(self) -> list[dict]:
        return [t.to_dict() for t in self._texts]

    def texts_from_dict(self, data: list[dict]):
        self.set_texts([TextItem.from_dict(d) for d in data])

    # ---------- geometry ----------
    def _ruler_height(self) -> int:
        return self.MIN_RULER_HEIGHT

    def _text_track_height(self) -> int:
        return self.MIN_TEXT_TRACK_HEIGHT

    def _text_track_rect(self) -> QRect:
        top = self._strip_height() + self.TEXT_TRACK_GAP
        return QRect(0, top, self.width(), self._text_track_height())

    def _strip_height(self) -> int:
        h = (
            self.height()
            - self._ruler_height()
            - self.RULER_GAP
            - self.TEXT_TRACK_GAP
            - self._text_track_height()
            - 2
        )
        return max(self.MIN_STRIP_HEIGHT, h)

    def _strip_rect(self) -> QRect:
        return QRect(0, 0, self.width(), self._strip_height())

    def _ruler_rect(self) -> QRect:
        top = (
            self._strip_height()
            + self.TEXT_TRACK_GAP
            + self._text_track_height()
            + self.RULER_GAP
        )
        return QRect(0, top, self.width(), self._ruler_height())

    def _x_to_sec(self, x: int) -> float:
        if self.width() <= 0:
            return 0.0
        ratio = max(0.0, min(1.0, x / self.width()))
        return ratio * self.duration

    def _sec_to_x(self, sec: float) -> int:
        if self.duration <= 0:
            return 0
        return int(max(0.0, min(1.0, sec / self.duration)) * self.width())

    def _text_rect(self, item: TextItem) -> QRect:
        track = self._text_track_rect()
        x0 = self._sec_to_x(item.start_sec)
        x1 = self._sec_to_x(item.end_sec)
        if x1 <= x0:
            x1 = x0 + 2
        return QRect(x0, track.top() + 3, max(2, x1 - x0), track.height() - 6)

    def _text_close_rect(self, item: TextItem) -> QRect:
        r = self._text_rect(item)
        size = self.TEXT_CLOSE_SIZE
        margin = self.TEXT_CLOSE_MARGIN
        x = r.right() - size + margin
        y = r.top() - size + margin
        return QRect(x, y, size, size)

    def _hit_handle(self, pos) -> str | None:
        if self.duration <= 0:
            return None
        candidates = [
            ("start", self._sec_to_x(self.start_sec), self.HANDLE_HIT),
            ("end", self._sec_to_x(self.end_sec), self.HANDLE_HIT),
            ("playhead", self._sec_to_x(self.playhead_sec), self.PLAYHEAD_HIT),
        ]
        best = None
        best_dist = None
        for name, x, hit in candidates:
            d = abs(pos.x() - x)
            if d <= hit and (best_dist is None or d < best_dist):
                best, best_dist = name, d
        return best

    def _hit_text(self, pos) -> tuple[int, str] | None:
        if self.duration <= 0:
            return None
        track = self._text_track_rect()
        for it in reversed(self._texts):
            rect = self._text_rect(it)
            if not rect.contains(pos):
                continue
            if abs(pos.x() - rect.left()) <= self.TEXT_HANDLE_HIT:
                return it.id, "start"
            if abs(pos.x() - rect.right()) <= self.TEXT_HANDLE_HIT:
                return it.id, "end"
            return it.id, "body"
        return None

    def _hit_text_close(self, pos) -> int | None:
        if self._selected_text is None:
            return None
        item = self._find_text(self._selected_text)
        if item is None:
            return None
        if self._text_close_rect(item).contains(pos):
            return item.id
        return None

    # ---------- snapping ----------
    def _snap_targets_sec(self, exclude_id: int | None) -> list[float]:
        targets = [0.0, self.duration, self.start_sec, self.end_sec, self.playhead_sec]
        for it in self._texts:
            if it.id == exclude_id:
                continue
            targets.append(it.start_sec)
            targets.append(it.end_sec)
        return targets

    def _apply_snap(self, sec: float, exclude_id: int | None) -> float:
        if self.duration <= 0:
            return sec
        snap_sec = (self.SNAP_PX / max(1, self.width())) * self.duration
        best = sec
        best_d = snap_sec + 1e-9
        for t in self._snap_targets_sec(exclude_id):
            d = abs(t - sec)
            if d < best_d:
                best, best_d = t, d
        self._snap_guide_sec = best if best != sec else None
        return best

    def _find_text(self, text_id: int) -> TextItem | None:
        for it in self._texts:
            if it.id == text_id:
                return it
        return None

    # ---------- events ----------
    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        pos = event.position().toPoint()

        close_id = self._hit_text_close(pos)
        if close_id is not None:
            self.remove_text(close_id)
            event.accept()
            return

        hit_text = self._hit_text(pos)
        if hit_text:
            tid, part = hit_text
            self.setFocus()
            self.select_text(tid)
            self._drag_text_id = tid
            if part == "body":
                self._dragging = "text_move"
                item = self._find_text(tid)
                if item is not None:
                    self._drag_text_origin = (item.start_sec, item.end_sec)
            elif part == "start":
                self._dragging = "text_start"
            else:
                self._dragging = "text_end"
            self.setCursor(
                Qt.SizeHorCursor if part != "body" else Qt.ClosedHandCursor
            )
            self.update()
            event.accept()
            return

        if self._text_track_rect().contains(pos):
            self.select_text(None)
            event.accept()
            return

        if not (
            self._strip_rect().contains(pos)
            or self._ruler_rect().contains(pos)
        ):
            return

        hit = self._hit_handle(pos)
        if hit:
            self._dragging = hit
            self.setCursor(Qt.SizeHorCursor)
            self.update()
            event.accept()
            return

        sec = self._x_to_sec(pos.x())
        self._dragging = "playhead"
        self._apply_playhead(sec, from_drag=True)
        self.setCursor(Qt.SizeHorCursor)
        self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()

        if self._dragging in ("text_move", "text_start", "text_end"):
            self._apply_text_drag(pos)
            event.accept()
            return

        if self._dragging:
            if self._dragging == "playhead":
                self._apply_playhead(self._x_to_sec(pos.x()), from_drag=True)
            else:
                self._apply_drag_handle(self._x_to_sec(pos.x()))
            event.accept()
            return

        if self._hit_text_close(pos) is not None:
            self.setCursor(Qt.PointingHandCursor)
            return

        hit_text = self._hit_text(pos)
        if hit_text:
            _, part = hit_text
            new_hover = f"text_{part}"
            if new_hover != self._hover:
                self._hover = new_hover
                self.setCursor(
                    Qt.SizeHorCursor if part != "body" else Qt.OpenHandCursor
                )
                self.update()
            return

        hit = self._hit_handle(pos)
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.SizeHorCursor if hit else Qt.ArrowCursor)
            self.update()

    def mouseReleaseEvent(self, event):
        if not self._dragging:
            return
        was = self._dragging
        self._dragging = None
        self._drag_text_id = None
        self._drag_text_origin = None
        self._snap_guide_sec = None
        self.setCursor(Qt.ArrowCursor)
        self.update()

        if was in ("start", "end"):
            self.range_changed.emit(self.start_sec, self.end_sec)
        elif was == "playhead":
            self.seek_requested.emit(self.playhead_sec)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        pos = event.position().toPoint()
        hit_text = self._hit_text(pos)
        if hit_text:
            tid, _ = hit_text
            self.select_text(tid)
            self.text_double_click.emit(tid)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete and self._selected_text is not None:
            self.remove_text(self._selected_text)
            event.accept()
            return

        step = 1.0 if event.modifiers() & Qt.ShiftModifier else 0.1
        if event.key() == Qt.Key_Left:
            self.set_range(self.start_sec - step, self.end_sec)
            self.range_changed.emit(self.start_sec, self.end_sec)
        elif event.key() == Qt.Key_Right:
            self.set_range(self.start_sec + step, self.end_sec)
            self.range_changed.emit(self.start_sec, self.end_sec)
        elif event.key() == Qt.Key_Home:
            self.set_playhead(self.start_sec)
            self.seek_requested.emit(self.playhead_sec)
        elif event.key() == Qt.Key_End:
            self.set_playhead(self.end_sec)
            self.seek_requested.emit(self.playhead_sec)
        else:
            super().keyPressEvent(event)

    # ---------- internal drag ----------
    def _apply_drag_handle(self, sec: float):
        if self._dragging == "start":
            self.start_sec = max(0.0, min(sec, self.end_sec - self.MIN_CLIP))
        elif self._dragging == "end":
            self.end_sec = min(
                self.duration, max(sec, self.start_sec + self.MIN_CLIP)
            )
        self.update()
        self.range_dragging.emit(self._dragging, self.start_sec, self.end_sec)

    def _apply_playhead(self, sec: float, from_drag: bool):
        sec = max(0.0, min(sec, self.duration))
        if abs(sec - self.playhead_sec) < 1e-6:
            return
        self.playhead_sec = sec
        self.update()
        if from_drag:
            self.scrub_moved.emit(sec)
        else:
            self.position_changed.emit(sec)

    def _apply_text_drag(self, pos):
        item = (
            self._find_text(self._drag_text_id)
            if self._drag_text_id is not None
            else None
        )
        if item is None:
            return
        sec = self._x_to_sec(pos.x())

        if self._dragging == "text_move" and self._drag_text_origin:
            o_start, o_end = self._drag_text_origin
            dur = max(self.MIN_TEXT_DURATION, o_end - o_start)
            new_start = sec - dur / 2
            new_start = max(0.0, min(self.duration - dur, new_start))
            new_end = new_start + dur

            s_start = self._apply_snap(new_start, item.id)
            s_end = self._apply_snap(new_end, item.id)
            if abs(s_start - new_start) < abs(s_end - new_end):
                new_start = s_start
                new_end = new_start + dur
            else:
                new_end = s_end
                new_start = new_end - dur

            new_start = max(0.0, min(self.duration - dur, new_start))
            new_end = new_start + dur

            item.start_sec = new_start
            item.end_sec = new_end

        elif self._dragging == "text_start":
            new_start = self._apply_snap(sec, item.id)
            item.start_sec = max(
                0.0, min(new_start, item.end_sec - self.MIN_TEXT_DURATION)
            )

        elif self._dragging == "text_end":
            new_end = self._apply_snap(sec, item.id)
            item.end_sec = min(
                self.duration,
                max(new_end, item.start_sec + self.MIN_TEXT_DURATION),
            )

        self._texts.sort(key=lambda t: t.start_sec)
        self.update()
        self.text_changed.emit(item.id, item.start_sec, item.end_sec)

    # ---------- painting ----------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), QColor("#0f172a"))

        strip = self._strip_rect()
        ruler = self._ruler_rect()

        if self._thumbs and self.duration > 0:
            n = len(self._thumbs)
            cell_w = strip.width() / n
            for i, pix in enumerate(self._thumbs):
                x = int(i * cell_w)
                w = int(cell_w) + 1
                cell = QRect(x, strip.top(), w, strip.height())
                if pix.isNull():
                    painter.fillRect(cell, QColor("#1e293b"))
                else:
                    scaled = pix.scaled(
                        cell.size(),
                        Qt.KeepAspectRatioByExpanding,
                        Qt.SmoothTransformation,
                    )
                    sx = max(0, (scaled.width() - cell.width()) // 2)
                    sy = max(0, (scaled.height() - cell.height()) // 2)
                    painter.drawPixmap(
                        cell, scaled, QRect(sx, sy, cell.width(), cell.height())
                    )
        else:
            painter.fillRect(strip, QColor("#1e293b"))

        if self.duration <= 0:
            painter.setPen(QColor("#94a3b8"))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(
                strip, Qt.AlignCenter, "Pilih file video untuk melihat timeline"
            )
            painter.end()
            return

        xs = self._sec_to_x(self.start_sec)
        xe = self._sec_to_x(self.end_sec)
        painter.fillRect(
            QRect(0, strip.top(), xs, strip.height()), QColor(0, 0, 0, 140)
        )
        painter.fillRect(
            QRect(xe, strip.top(), strip.width() - xe, strip.height()),
            QColor(0, 0, 0, 140),
        )

        sel_color = (
            QColor("#7dd3fc")
            if self._dragging in ("start", "end")
            else QColor("#38bdf8")
        )
        painter.setPen(QPen(sel_color, 2))
        painter.drawLine(xs, strip.top(), xs, strip.bottom())
        painter.drawLine(xe, strip.top(), xe, strip.bottom())

        handle_w = 6
        h_color = (
            QColor("#38bdf8")
            if self._dragging in ("start", "end")
            else QColor("#0ea5e9")
        )
        painter.fillRect(
            QRect(xs - handle_w // 2, strip.top(), handle_w, 10), h_color
        )
        painter.fillRect(
            QRect(xe - handle_w // 2, strip.top(), handle_w, 10), h_color
        )
        painter.fillRect(
            QRect(xs - handle_w // 2, strip.bottom() - 10, handle_w, 10), h_color
        )
        painter.fillRect(
            QRect(xe - handle_w // 2, strip.bottom() - 10, handle_w, 10), h_color
        )

        xp = self._sec_to_x(self.playhead_sec)
        pw = 2 if self._dragging == "playhead" else 1
        painter.setPen(QPen(QColor("#f8fafc"), pw))
        painter.drawLine(xp, strip.top(), xp, strip.bottom())
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#f8fafc"))
        painter.drawEllipse(xp - 5, strip.top() - 2, 10, 10)
        painter.setBrush(Qt.NoBrush)

        # ---------- text track ----------
        text_rect = self._text_track_rect()
        painter.fillRect(text_rect, QColor("#0b1220"))
        painter.setPen(QColor("#1e293b"))
        painter.drawLine(
            text_rect.left(), text_rect.top(),
            text_rect.right(), text_rect.top(),
        )

        if self._snap_guide_sec is not None:
            xs_g = self._sec_to_x(self._snap_guide_sec)
            painter.setPen(QPen(QColor("#fbbf24"), 1, Qt.DashLine))
            painter.drawLine(xs_g, text_rect.top(), xs_g, text_rect.bottom())
            painter.setPen(Qt.NoPen)

        painter.setFont(QFont("Segoe UI", 8))
        fm_text = painter.fontMetrics()

        for it in self._texts:
            r = self._text_rect(it)
            selected = it.id == self._selected_text
            base = QColor(it.color)
            fill = QColor(base)
            fill.setAlpha(90 if selected else 60)
            painter.setBrush(fill)
            painter.setPen(
                QPen(
                    QColor("#38bdf8") if selected else QColor("#475569"),
                    2 if selected else 1,
                )
            )
            painter.drawRoundedRect(r, 4, 4)

            inner = r.adjusted(6, 0, -6, 0)
            label = fm_text.elidedText(
                it.text or "(kosong)", Qt.ElideRight, max(0, inner.width())
            )
            painter.setPen(QColor("#e2e8f0"))
            painter.drawText(inner, Qt.AlignVCenter | Qt.AlignLeft, label)

            if selected:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#38bdf8"))
                painter.drawRect(QRect(r.left() - 2, r.top(), 4, r.height()))
                painter.drawRect(QRect(r.right() - 1, r.top(), 4, r.height()))

                cr = self._text_close_rect(it)
                painter.setBrush(QColor("#ef4444"))
                painter.setPen(QPen(QColor("#0f172a"), 1))
                painter.drawEllipse(cr)
                painter.setPen(QPen(QColor("#ffffff"), 2))
                m = 4
                painter.drawLine(
                    cr.left() + m, cr.top() + m,
                    cr.right() - m, cr.bottom() - m,
                )
                painter.drawLine(
                    cr.right() - m, cr.top() + m,
                    cr.left() + m, cr.bottom() - m,
                )

        painter.setBrush(Qt.NoBrush)

        # ruler
        painter.fillRect(ruler, QColor("#0b1220"))
        painter.setPen(QColor("#334155"))
        painter.drawLine(0, ruler.top(), ruler.width(), ruler.top())

        painter.setFont(QFont("Consolas", 8))
        fm = painter.fontMetrics()
        approx_label_w = fm.horizontalAdvance("00:00.00")
        min_tick_px = max(60, approx_label_w + 12)
        tick_count = max(2, ruler.width() // min_tick_px)

        for i in range(tick_count + 1):
            ratio = i / tick_count
            x = int(ratio * ruler.width())
            t = ratio * self.duration
            painter.setPen(QColor("#475569"))
            painter.drawLine(x, ruler.top(), x, ruler.top() + 5)
            painter.setPen(QColor("#94a3b8"))
            label = self._fmt_time(t)
            if i == tick_count:
                tw = fm.horizontalAdvance(label)
                painter.drawText(x - tw - 3, ruler.top() + 18, label)
            else:
                painter.drawText(x + 3, ruler.top() + 18, label)

        painter.setPen(QColor("#38bdf8"))
        painter.setFont(QFont("Consolas", 9, QFont.Bold))
        painter.drawText(xs + 4, ruler.bottom() - 2, self._fmt_time(self.start_sec))
        fm2 = painter.fontMetrics()
        end_label = self._fmt_time(self.end_sec)
        painter.drawText(
            xe - fm2.horizontalAdvance(end_label) - 4,
            ruler.bottom() - 2,
            end_label,
        )

        painter.setPen(QColor("#e2e8f0"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        clip_len = self.end_sec - self.start_sec
        mid_x = (xs + xe) // 2
        painter.drawText(
            QRect(mid_x - 60, strip.top() + strip.height() - 22, 120, 18),
            Qt.AlignCenter,
            f"klip: {self._fmt_time(clip_len)}",
        )

        painter.end()

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        seconds = max(0.0, float(seconds))
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        if h:
            return f"{h}:{m:02d}:{s:05.2f}"
        return f"{m}:{s:05.2f}"