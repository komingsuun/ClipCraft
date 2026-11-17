from PySide6.QtCore import Qt, Signal, QUrl, QPointF
from PySide6.QtGui import QImage, QPixmap, QPolygonF, QPainter, QColor, QPen
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QWidget, QStackedLayout, QLabel, QPushButton,
    QSizePolicy, QGraphicsView, QGraphicsScene,
)

class PlayButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._playing = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(56, 56)

    def set_playing(self, playing: bool):
        self._playing = playing
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0

        # lingkaran background
        if self.underMouse():
            bg = QColor(56, 189, 248, 200)
        else:
            bg = QColor(15, 23, 42, 180)
        painter.setBrush(bg)
        painter.setPen(QPen(QColor(255, 255, 255, 200), 2))
        painter.drawEllipse(1, 1, w - 2, h - 2)

        # ikon
        painter.setBrush(QColor("white"))
        painter.setPen(Qt.NoPen)

        if self._playing:
            # dua batang vertikal (pause)
            bar_w = w * 0.12
            bar_h = h * 0.40
            gap = w * 0.10
            painter.drawRect(
                int(cx - gap / 2 - bar_w), int(cy - bar_h / 2),
                int(bar_w), int(bar_h),
            )
            painter.drawRect(
                int(cx + gap / 2), int(cy - bar_h / 2),
                int(bar_w), int(bar_h),
            )
        else:
            # segitiga play — titik berat di tengah geometris
            tri_w = w * 0.30
            tri_h = h * 0.36
            # segitiga dengan centroid di (cx, cy):
            # verteks: atas-kiri, bawah-kiri, kanan-tengah
            x0 = cx - tri_w / 2 + tri_w * 0.10   # sedikit offset visual
            y0 = cy - tri_h / 2
            y1 = cy + tri_h / 2
            x1 = x0 + tri_w
            poly = QPolygonF([
                QPointF(x0, y0),
                QPointF(x0, y1),
                QPointF(x1, cy),
            ])
            painter.drawPolygon(poly)

class VideoPreviewWidget(QWidget):
    play_clicked = Signal()
    position_changed = Signal(float)
    duration_changed = Signal(float)
    play_state_changed = Signal(bool)
    frame_ready = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._duration = 0.0
        self._position = 0.0
        self._is_playing = False
        self._pending_seek_sec: float | None = None

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(0, 0)
        self.setStyleSheet("background-color: #000;")

        # --- media ---
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state)

        self._player.mediaStatusChanged.connect(
            lambda s: print(f"[mediaStatus] {s}")
        )
        self._player.errorOccurred.connect(
            lambda e, msg: print(f"[playerError] {e}: {msg}")
        )

        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setStackingMode(QStackedLayout.StackAll)

        # halaman 0: image placeholder (scrub)
        self._image_label = QLabel(self)
        self._image_label.setAlignment(Qt.AlignCenter)
        self._image_label.setStyleSheet("background-color: #000; color: #64748b;")
        self._image_label.setScaledContents(False)
        self._image_label.setText("Preview belum tersedia")
        self._image_label.setMinimumSize(0, 0)
        self._image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self._stack.addWidget(self._image_label)

        # halaman 1: video via QGraphicsVideoItem
        self._video_scene = QGraphicsScene(self)
        self._video_view = QGraphicsView(self._video_scene, self)
        self._video_view.setStyleSheet("background-color: #000; border: none;")
        self._video_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._video_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._video_view.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self._video_view.setMinimumSize(0, 0)
        self._video_view.setFrameShape(QGraphicsView.NoFrame)

        self._video_item = QGraphicsVideoItem()
        self._video_scene.addItem(self._video_item)
        self._player.setVideoOutput(self._video_item)

        self._stack.addWidget(self._video_view)

        self._current_pix: QPixmap | None = None
        self._stack.setCurrentIndex(0)

        # tombol play overlay
        self._play_btn = PlayButton(self)
        self._play_btn.clicked.connect(self.play_clicked.emit)
        self._play_btn.raise_()
        self._play_btn.show()
        # self._play_btn = QPushButton(self)
        # self._play_btn.setCursor(Qt.PointingHandCursor)
        # self._play_btn.setFixedSize(56, 56)
        # self._play_btn.setStyleSheet("""
        #     QPushButton {
        #         background-color: rgba(15, 23, 42, 180);
        #         border: 2px solid rgba(255,255,255,200);
        #         border-radius: 28px;
        #         color: white;
        #         font-size: 22px;
        #     }
        #     QPushButton:hover {
        #         background-color: rgba(56, 189, 248, 200);
        #     }
        # """)
        # self._play_btn.setText("▶")
        # self._play_btn.clicked.connect(self.play_clicked.emit)
        # self._play_btn.raise_()
        # self._play_btn.show()

        # label waktu
        self._time_label = QLabel(self)
        self._time_label.setStyleSheet("""
            color: #e2e8f0;
            background-color: rgba(15, 23, 42, 160);
            padding: 2px 8px;
            border-radius: 4px;
            font-family: Consolas, monospace;
            font-size: 11px;
        """)
        self._time_label.setText("0:00.00 / 0:00.00")
        self._time_label.adjustSize()
        self._stack.currentChanged.connect(self._on_stack_changed)

    def _on_stack_changed(self, index: int):
        self._play_btn.raise_()
        self._time_label.raise_()
        self._center_play_button()
        self._center_time_label()

    # ---------- lifecycle ----------
    def load(self, path: str):
        self._reset_state()
        self._player.setSource(QUrl.fromLocalFile(path))
        self._stack.setCurrentIndex(1)
        self._play_btn.raise_()
        self._time_label.raise_()        # ← tambah

    def clear(self):
        self._player.stop()
        self._player.setSource(QUrl())
        self._reset_state()
        self._current_pix = None
        self._image_label.setText("Preview belum tersedia")
        self._image_label.setPixmap(QPixmap())
        self._stack.setCurrentIndex(0)

    def _reset_state(self):
        self._duration = 0.0
        self._position = 0.0
        self._is_playing = False
        self._pending_seek_sec = None
        self._update_play_button(False)

    # ---------- playback ----------
    def play_from(self, start_sec: float):
        """Play dari start_sec. Auto-stop ditangani oleh CutterPage."""
        if self._player.source().isEmpty():
            return
        start_sec = max(0.0, min(float(start_sec), self._duration or 0.0))
        self._stack.setCurrentIndex(1)
        self._play_btn.raise_()
        self._time_label.raise_()
        self._player.setPosition(int(start_sec * 1000))
        self._player.play()
        self._play_btn.raise_()

    def play(self):
        if self._player.source().isEmpty():
            return
        self._stack.setCurrentIndex(1)
        self._play_btn.raise_()
        self._time_label.raise_()
        if self._pending_seek_sec is not None:
            self._player.setPosition(int(self._pending_seek_sec * 1000))
            self._pending_seek_sec = None
        self._player.play()
        self._play_btn.raise_()

    def pause(self):
        self._player.pause()

    def toggle_play(self):
        if self._is_playing:
            self.pause()
        else:
            self.play()

    def seek(self, sec: float):
        if self._player.source().isEmpty():
            return
        sec = max(0.0, min(float(sec), self._duration or 0.0))
        self._pending_seek_sec = sec
        self._stack.setCurrentIndex(1)
        self._play_btn.raise_()
        self._time_label.raise_()
        self._player.setPosition(int(sec * 1000))

    def seek_while_playing(self, sec: float):
        """Seek tanpa menghentikan playback. Kalau sedang playing, lanjut play
        dari posisi baru. Kalau pause, hanya seek."""
        if self._player.source().isEmpty():
            return
        sec = max(0.0, min(float(sec), self._duration or 0.0))
        self._pending_seek_sec = sec
        self._stack.setCurrentIndex(1)
        self._play_btn.raise_()
        self._time_label.raise_()
        was_playing = self._is_playing
        self._player.setPosition(int(sec * 1000))
        if was_playing and self._player.playbackState() != QMediaPlayer.PlayingState:
            self._player.play()

    def set_volume(self, volume_0_100: int):
        self._audio.setVolume(max(0, min(100, volume_0_100)) / 100.0)

    def set_muted(self, muted: bool):
        self._audio.setMuted(muted)

    # ---------- display image (scrub) ----------
    def show_frame(self, image: QImage):
        if image.isNull():
            return
        self._current_pix = QPixmap.fromImage(image)
        self._stack.setCurrentIndex(0)
        self._render_current_pix()

    def set_thumbnail(self, image: QImage):
        self.show_frame(image)

    def set_time_info(self, current: float, total: float):
        self._position = float(current)
        self._duration = float(total)
        self._time_label.setText(
            f"{self._fmt_time(self._position)} / {self._fmt_time(self._duration)}"
        )
        self._time_label.adjustSize()
        self._center_time_label()

    # ---------- info ----------
    def duration(self) -> float:
        return self._duration

    def position(self) -> float:
        return self._position

    def is_playing(self) -> bool:
        return self._is_playing

    # ---------- media events ----------
    def _on_position_changed(self, ms: int):
        sec = ms / 1000.0
        self._position = sec
        self._time_label.setText(
            f"{self._fmt_time(sec)} / {self._fmt_time(self._duration)}"
        )
        self._time_label.adjustSize()
        self._center_time_label()
        self.position_changed.emit(sec)

    def _on_duration_changed(self, ms: int):
        self._duration = ms / 1000.0
        self.duration_changed.emit(self._duration)

    def _on_playback_state(self, state):
        playing = state == QMediaPlayer.PlayingState
        if playing == self._is_playing:
            return
        self._is_playing = playing
        self._update_play_button(playing)
        self.play_state_changed.emit(playing)

    # ---------- rendering ----------
    def _update_play_button(self, playing: bool):
        self._play_btn.set_playing(playing)
        self._play_btn.setVisible(not playing)
        self._play_btn.raise_()
        self._center_play_button()
    # def _update_play_button(self, playing: bool):
    #     self._play_btn.setVisible(True)
    #     self._play_btn.setText("❚❚" if playing else "▶")
    #     self._play_btn.raise_()
    #     self._center_play_button()

    def _render_current_pix(self):
        if self._current_pix is None or self._current_pix.isNull():
            return
        area = self._image_label.size()
        if area.width() <= 0 or area.height() <= 0:
            return
        scaled = self._current_pix.scaled(
            area, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self._image_label.setPixmap(scaled)

    def _fit_video(self):
        if not hasattr(self, "_video_item") or not hasattr(self, "_video_view"):
            return
        size = self._video_view.viewport().size()
        if size.width() <= 0 or size.height() <= 0:
            return
        self._video_item.setSize(size)
        self._video_scene.setSceneRect(0, 0, size.width(), size.height())

    def _center_play_button(self):
        w = self._play_btn.width()
        h = self._play_btn.height()
        x = (self.width() - w) // 2
        y = (self.height() - h) // 2
        self._play_btn.move(x, y)

    def _center_time_label(self):
        margin = 8
        y = self.height() - self._time_label.height() - margin
        self._time_label.move(margin, y)
        self._time_label.raise_()

    # ---------- events ----------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_video()
        self._center_play_button()
        self._center_time_label()
        if self._stack.currentIndex() == 0:
            self._render_current_pix()

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_video()
        self._center_play_button()
        self._center_time_label()

    # ---------- helpers ----------
    @staticmethod
    def _fmt_time(seconds: float) -> str:
        seconds = max(0.0, float(seconds))
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        if h:
            return f"{h}:{m:02d}:{s:05.2f}"
        return f"{m}:{s:05.2f}"