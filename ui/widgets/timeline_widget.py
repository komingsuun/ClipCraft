from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


class TimelineWidget(QWidget):
    scrub_moved = Signal(float)
    seek_requested = Signal(float)
    range_changed = Signal(float, float)
    position_changed = Signal(float)
    range_dragging = Signal(str, float, float)  # handle, start_sec, end_sec

    HANDLE_HIT = 10
    PLAYHEAD_HIT = 6
    MIN_CLIP = 0.2

    MIN_STRIP_HEIGHT = 64
    MIN_RULER_HEIGHT = 26
    RULER_GAP = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.duration = 0.0
        self.start_sec = 0.0
        self.end_sec = 0.0
        self.playhead_sec = 0.0
        self._thumbs: list[QPixmap] = []
        self._dragging: str | None = None
        self._hover: str | None = None

        self.setMinimumHeight(
            self.MIN_STRIP_HEIGHT + self.MIN_RULER_HEIGHT + self.RULER_GAP + 6
        )
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    # ---------- public API: state ----------
    def set_duration(self, duration: float):
        self.duration = max(0.0, float(duration))
        if self.end_sec <= self.start_sec or self.end_sec > self.duration:
            self.end_sec = self.duration
        self.playhead_sec = min(self.playhead_sec, self.duration)
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

    def loaded_thumbnail_count(self) -> int:
        return sum(1 for p in self._thumbs if not p.isNull())

    # ---------- geometry ----------
    def _ruler_height(self) -> int:
        return self.MIN_RULER_HEIGHT

    def _strip_height(self) -> int:
        h = self.height() - self._ruler_height() - self.RULER_GAP - 2
        return max(self.MIN_STRIP_HEIGHT, h)

    def _strip_rect(self) -> QRect:
        return QRect(0, 0, self.width(), self._strip_height())

    def _ruler_rect(self) -> QRect:
        return QRect(
            0,
            self._strip_height() + self.RULER_GAP,
            self.width(),
            self._ruler_height(),
        )

    def _x_to_sec(self, x: int) -> float:
        if self.width() <= 0:
            return 0.0
        ratio = max(0.0, min(1.0, x / self.width()))
        return ratio * self.duration

    def _sec_to_x(self, sec: float) -> int:
        if self.duration <= 0:
            return 0
        return int(max(0.0, min(1.0, sec / self.duration)) * self.width())

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

    # ---------- events ----------
    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        pos = event.position().toPoint()

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
        if self._dragging:
            if self._dragging == "playhead":
                self._apply_playhead(self._x_to_sec(pos.x()), from_drag=True)
            else:
                self._apply_drag_handle(self._x_to_sec(pos.x()))
            event.accept()
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
        self.setCursor(Qt.ArrowCursor)
        self.update()

        if was in ("start", "end"):
            self.range_changed.emit(self.start_sec, self.end_sec)
        elif was == "playhead":
            self.seek_requested.emit(self.playhead_sec)
        event.accept()

    def keyPressEvent(self, event):
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

    # ---------- painting ----------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), QColor("#0f172a"))

        strip = self._strip_rect()
        ruler = self._ruler_rect()

        # thumbnail strip
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

        # overlay gelap di luar seleksi
        xs = self._sec_to_x(self.start_sec)
        xe = self._sec_to_x(self.end_sec)
        painter.fillRect(
            QRect(0, strip.top(), xs, strip.height()), QColor(0, 0, 0, 140)
        )
        painter.fillRect(
            QRect(xe, strip.top(), strip.width() - xe, strip.height()),
            QColor(0, 0, 0, 140),
        )

        # garis seleksi
        sel_color = (
            QColor("#7dd3fc")
            if self._dragging in ("start", "end")
            else QColor("#38bdf8")
        )
        painter.setPen(QPen(sel_color, 2))
        painter.drawLine(xs, strip.top(), xs, strip.bottom())
        painter.drawLine(xe, strip.top(), xe, strip.bottom())

        # handle
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

        # playhead
        xp = self._sec_to_x(self.playhead_sec)
        pw = 2 if self._dragging == "playhead" else 1
        painter.setPen(QPen(QColor("#f8fafc"), pw))
        painter.drawLine(xp, strip.top(), xp, strip.bottom())
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#f8fafc"))
        painter.drawEllipse(xp - 5, strip.top() - 2, 10, 10)
        painter.setBrush(Qt.NoBrush)

        # ruler
        painter.fillRect(ruler, QColor("#0b1220"))
        painter.setPen(QColor("#334155"))
        painter.drawLine(0, ruler.top(), ruler.width(), ruler.top())

        # tick adaptif
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

        # label start & end
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

        # durasi klip
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