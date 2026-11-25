import os
import sys

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QProgressBar, QPushButton,
    QVBoxLayout, QWidget, QSizePolicy, QDialog, QToolBar, QToolButton,
)

from core.common import CustomTitleBar, STYLESHEET
from core.config import load_config
from core.downloader import COOKIE_BROWSERS
from core.ffmpeg import probe_media
from core.segment_workers import HeatmapCheckWorker, MostPlayedDownloadWorker
from core.video_cutter import ensure_cut_dir
from core.workers import CutterWorker, TextBurnInWorker, ThumbnailWorker, DownloadWorker
from ui.widgets.log_widget import LogWidget
from ui.widgets.timeline_widget import TimelineWidget
from ui.widgets.video_preview_widget import VideoPreviewWidget
from ui.widgets.text_item import TextItem
from ui.widgets.text_edit_dialog import TextEditDialog


def _parse_time(text: str) -> float:
    text = (text or "").strip()
    if not text:
        raise ValueError("kosong")
    parts = text.split(":")
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    raise ValueError("format waktu tidak dikenal")

def _fmt_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:05.2f}"
    return f"{m}:{s:05.2f}"

class DownloadByUrlDialog(QDialog):
    # Sinyal untuk meneruskan file hasil unduhan ke video cutter.
    download_ready = QtCore.Signal(str)

    TMP_DIR = os.path.join("downloads", "tmp")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            QtCore.Qt.WindowType.Dialog
            | QtCore.Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._drag_pos = None

        # Pastikan folder tmp ada.
        os.makedirs(self.TMP_DIR, exist_ok=True)

        cfg = load_config()
        self.worker = None
        self.heatmap_worker = None
        self._downloaded_filepath = None

        self._build_ui(cfg)
        self._apply_title_bar_style()
        self._title_bar.installEventFilter(self)

    # ------------------------------------------------------------------ UI
    def _build_ui(self, cfg):
        main_frame = QFrame()
        main_frame.setFrameShape(QFrame.Shape.StyledPanel)
        main_frame.setFrameShadow(QFrame.Shadow.Raised)

        main_layout = QVBoxLayout(main_frame)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._title_bar = CustomTitleBar(self, only_close=True)
        main_layout.addWidget(self._title_bar)

        # ---------------- Body ----------------
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setFrameShadow(QFrame.Shadow.Raised)
        frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        frame.setStyleSheet(
            "background-color: rgba(30, 30, 30, 0.8); padding: 10px;"
        )
        body = QVBoxLayout(frame)
        body.setContentsMargins(5, 15, 5, 15)
        body.setSpacing(8)

        # URL
        url_row = QHBoxLayout()
        label_url = QLabel("URL Video")
        label_url.setObjectName("label_input_url")
        label_url.setStyleSheet("background-color: transparent;")
        url_row.addWidget(label_url)

        self.input_url = QLineEdit(frame)
        self.input_url.setObjectName("input_url")
        self.input_url.setMinimumWidth(400)
        self.input_url.setStyleSheet(
            "background-color: rgba(30, 30, 30, 0.8);"
        )
        self.input_url.returnPressed.connect(self.download)
        url_row.addWidget(self.input_url, stretch=1)
        body.addLayout(url_row)

        # Cookies + Compression
        opt_row = QHBoxLayout()
        opt_row.addWidget(self._label("Cookie Browser"))
        self.cookies_combo = QtWidgets.QComboBox()
        for label, value in COOKIE_BROWSERS:
            self.cookies_combo.addItem(label, value)
        idx = self.cookies_combo.findData(
            cfg["downloader"]["cookies_browser"]
        )
        self.cookies_combo.setCurrentIndex(max(0, idx))
        self.cookies_combo.setMinimumWidth(160)
        opt_row.addWidget(self.cookies_combo)

        opt_row.addSpacing(16)
        opt_row.addWidget(self._label("Kualitas"))
        self.compression_combo = QtWidgets.QComboBox()
        self.compression_combo.addItem("Original — tanpa kompresi", "Original")
        self.compression_combo.addItem("High — kualitas tinggi", "High")
        self.compression_combo.addItem("Balanced — rekomendasi", "Balanced")
        self.compression_combo.addItem("Compact — ukuran lebih kecil", "Compact")
        self.compression_combo.addItem("Small — ukuran minimal", "Small")
        idx = self.compression_combo.findData(
            cfg["downloader"]["compression_preset"]
        )
        self.compression_combo.setCurrentIndex(max(0, idx))
        self.compression_combo.setMinimumWidth(200)
        opt_row.addWidget(self.compression_combo)
        opt_row.addStretch()
        body.addLayout(opt_row)

        # Checkbox most-played
        cb_row = QHBoxLayout()
        self.most_played_cb = QCheckBox("YT Most Played Segment")
        self.most_played_cb.setObjectName("most_played_cb")
        self.most_played_cb.setToolTip(
            "Periksa heatmap YouTube dan unduh segmen dengan pemutaran "
            "tertinggi. YouTube only!"
        )
        self.most_played_cb.toggled.connect(self.on_most_played_toggled)
        cb_row.addWidget(self.most_played_cb)
        cb_row.addStretch()
        body.addLayout(cb_row)

        # Progress
        progress_frame = QFrame()
        progress_frame.setObjectName("progressFrame")
        pl = QVBoxLayout(progress_frame)
        pl.setContentsMargins(10, 8, 10, 8)
        pl.setSpacing(6)
        self.status_label = QLabel("Siap")
        self.status_label.setObjectName("statusLabel")
        pl.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        pl.addWidget(self.progress_bar)
        self.detail_label = QLabel("Kecepatan: -   |   ETA: -")
        self.detail_label.setObjectName("detailLabel")
        pl.addWidget(self.detail_label)
        body.addWidget(progress_frame)

        # Log
        self.log_output = LogWidget()
        self.log_output.setMaximumHeight(110)
        body.addWidget(self.log_output)

        main_layout.addWidget(frame, stretch=1)

        # ---------------- Footer ----------------
        btn_frame = QFrame()
        btn_frame.setFrameShape(QFrame.Shape.StyledPanel)
        btn_frame.setFrameShadow(QFrame.Shadow.Sunken)
        btn_frame.setStyleSheet(
            """
            background-color: rgba(30, 30, 30, 0.8);
            padding: 10px;
            border-bottom-left-radius: 8px;
            border-bottom-right-radius: 8px;
            """
        )
        footer = QHBoxLayout(btn_frame)
        footer.setContentsMargins(5, 5, 5, 5)
        footer.setSpacing(8)

        self.btn_download = QPushButton("Download")
        self.btn_download.setMaximumWidth(100)
        self.btn_download.clicked.connect(self.download)

        self.btn_cancel = QPushButton("Batalkan")
        self.btn_cancel.setMaximumWidth(100)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_download)

        self.btn_close = QPushButton("Tutup")
        self.btn_close.setMaximumWidth(100)
        self.btn_close.clicked.connect(self.finish_dialog)

        footer.addWidget(self.most_played_cb)
        footer.addStretch()
        footer.addWidget(self.btn_download)
        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_close)

        main_layout.addWidget(btn_frame)
        self.setLayout(main_layout)

    def _apply_title_bar_style(self):
        self._title_bar.setStyleSheet(
            """
            QWidget {
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border-style: solid;
                border-width: 1px;
                border-color: transparent;
                background-color: rgba(255, 255, 255, 0.9);
                color: black;
            }
            QCheckBox { color: #cbd5e1; spacing: 8px; }
            QCheckBox::indicator {
                width: 16px; height: 16px; border-radius: 4px;
                border: 1px solid #475569; background-color: #1e293b;
            }
            QCheckBox::indicator:checked {
                background-color: #0ea5e9; border-color: #0ea5e9;
            }
            QPushButton#titleBarCloseBtn {
                background-color: #ff0000;
                border: none;
                border-radius: 12px;
                color: #ffffff;
                font-size: 14px;
                font-weight: 700;
                padding: 0px;
                margin-right: 5px;
                min-width: 26px; max-width: 26px;
                min-height: 26px; max-height: 26px;
            }
            QPushButton#titleBarCloseBtn:hover { background-color: #ff0000; color: #ffff00; }
            QPushButton#titleBarCloseBtn:pressed { background-color: #273449; }
            QPushButton#winBtn {
                background-color: transparent;
                border: none;
                color: #cbd5e1;
                font-size: 14px;
                font-weight: 700;
                min-width: 46px; max-width: 46px;
                min-height: 36px; max-height: 36px;
            }
            QPushButton#winBtn:hover { background-color: #1e293b; color: #e2e8f0; }
            QPushButton#winBtn:pressed { background-color: #273449; }
            """
        )

    @staticmethod
    def _label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("fieldLabel")
        lbl.setStyleSheet("color: #cbd5e1; background: transparent;")
        return lbl

    # ------------------------------------------------------------- helpers
    def log(self, message: str):
        self.log_output.append_log(message)

    def _set_busy(self, busy: bool, status=None):
        self.btn_download.setEnabled(not busy)
        self.btn_cancel.setEnabled(busy)
        self.btn_close.setEnabled(not busy)
        if status:
            self.status_label.setText(status)

    def has_active_worker(self) -> bool:
        return (
            (self.worker is not None and self.worker.isRunning())
            or (
                self.heatmap_worker is not None
                and self.heatmap_worker.isRunning()
            )
        )

    # ----------------------------------------------------- most-played flow
    def on_most_played_toggled(self, checked: bool):
        if not checked:
            return

        if self.has_active_worker():
            self.most_played_cb.blockSignals(True)
            self.most_played_cb.setChecked(False)
            self.most_played_cb.blockSignals(False)
            return

        url = self.input_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Peringatan", "URL tidak boleh kosong.")
            self.most_played_cb.setChecked(False)
            return

        self.progress_bar.setValue(0)
        self.detail_label.setText("Memeriksa heatmap...")
        self.status_label.setText("Memeriksa heatmap URL...")
        self.btn_download.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.log("=" * 60)
        self.log(f"Memeriksa heatmap: {url}")

        self.heatmap_worker = HeatmapCheckWorker(
            url=url,
            cookies_from_browser=self.cookies_combo.currentData(),
        )
        self.heatmap_worker.log_message.connect(self.log)
        self.heatmap_worker.result_ready.connect(self.on_heatmap_checked)
        self.heatmap_worker.start()

    def on_heatmap_checked(self, has_heatmap: bool, segment: dict, error: str):
        self.heatmap_worker = None
        self.btn_download.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.detail_label.setText("Kecepatan: -   |   ETA: -")

        if error:
            cancelled = "dibatalkan" in error.lower()
            self.status_label.setText(
                "Pemeriksaan dibatalkan" if cancelled else "Gagal memeriksa heatmap"
            )
            if not cancelled:
                QMessageBox.warning(self, "Gagal Memeriksa URL", error)
            self.most_played_cb.setChecked(False)
            return

        if not has_heatmap:
            self.status_label.setText("Heatmap tidak ditemukan")
            QMessageBox.information(
                self,
                "Heatmap Tidak Tersedia",
                "URL yang diberikan tidak memiliki data heatmap, "
                "silakan masukkan url yang lain!",
                QMessageBox.Ok,
            )
            self.most_played_cb.setChecked(False)
            return

        start_seg = float(segment["start"])
        end_seg = float(segment["end"])
        message = (
            "Benar Anda akan download segmen most played "
            f"{start_seg:.0f}-{end_seg:.0f}?"
        )
        reply = QMessageBox.question(
            self,
            "Konfirmasi Most Played Segment",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self.start_most_played_download(segment)
        else:
            self.status_label.setText("Siap")
            self.progress_bar.setValue(0)
            self.detail_label.setText("Kecepatan: -   |   ETA: -")
            self.most_played_cb.setChecked(False)

    def start_most_played_download(self, segment: dict):
        if self.has_active_worker():
            return

        browser = self.cookies_combo.currentData()
        preset = self.compression_combo.currentData()

        self.progress_bar.setValue(0)
        self.status_label.setText("Memulai unduhan segmen...")
        self.detail_label.setText("Kecepatan: -   |   ETA: -")
        self._set_busy(True)
        self.log("=" * 60)
        self.log(
            f"Most Played: {segment['start']:.0f}s–{segment['end']:.0f}s"
        )
        self.log(f"Folder tmp: {self.TMP_DIR}")
        self.log(f"Preset output: {preset}")
        self.log(f"Cookie browser: {browser or 'tidak ada'}")

        self.worker = MostPlayedDownloadWorker(
            url=self.input_url.text().strip(),
            output_dir=self.TMP_DIR,
            segment=segment,
            compression_preset=preset,
            cookies_from_browser=browser,
        )
        self.worker.progress_changed.connect(self.on_progress)
        self.worker.log_message.connect(self.log)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    # -------------------------------------------------------- normal flow
    def download(self):
        url = self.input_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Peringatan", "URL tidak boleh kosong.")
            return

        if self.has_active_worker():
            return

        # Checkbox most-played menjalankan alur cek heatmap sendiri.
        if self.most_played_cb.isChecked():
            return

        browser = self.cookies_combo.currentData()
        self.progress_bar.setValue(0)
        self.status_label.setText("Memulai unduhan...")
        self.detail_label.setText("Kecepatan: -   |   ETA: -")
        self.btn_download.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.log("=" * 60)
        self.log(f"Memulai unduhan: {url}")
        self.log(f"Folder tmp: {self.TMP_DIR}")
        self.log(f"Preset output: {self.compression_combo.currentData()}")
        self.log(f"Cookie browser: {browser or 'tidak ada'}")

        self.worker = DownloadWorker(
            url=url,
            output_dir=self.TMP_DIR,
            noplaylist=True,
            compression_preset=self.compression_combo.currentData(),
            cookies_from_browser=browser,
        )
        self.worker.progress_changed.connect(self.on_progress)
        self.worker.log_message.connect(self.log)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def cancel_download(self):
        if self.heatmap_worker and self.heatmap_worker.isRunning():
            self.heatmap_worker.cancel()
            self.status_label.setText("Membatalkan pemeriksaan heatmap...")
            self.log("Permintaan pembatalan pemeriksaan heatmap dikirim.")
            self.btn_cancel.setEnabled(False)
            return

        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.status_label.setText("Membatalkan...")
            self.log("Permintaan pembatalan dikirim.")
            self.btn_cancel.setEnabled(False)

    # --------------------------------------------------------- callbacks
    def on_progress(self, percent: float, speed: str, eta: str, status: str):
        self.progress_bar.setValue(max(0, min(100, int(percent))))
        self.status_label.setText(status)
        self.detail_label.setText(f"Kecepatan: {speed}   |   ETA: {eta}")

    def on_finished(self, success: bool, info: dict):
        self.btn_download.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_close.setEnabled(True)

        self.worker = None
        self._reset_most_played()

        if not success:
            self.status_label.setText("Gagal / Dibatalkan")
            return

        self.progress_bar.setValue(100)
        self.status_label.setText("Selesai ✓")
        self.log("-" * 60)
        self.log(f"Judul  : {info.get('title', '-')}")
        self.log(f"Situs  : {info.get('extractor_key', '-')}")

        filepath = self._resolve_output_path(info)
        if filepath:
            self.log(f"File   : {filepath}")
        self.log(f"Folder : {os.path.abspath(self.TMP_DIR)}")
        self.log("-" * 60)

        if not filepath or not os.path.isfile(filepath):
            self.status_label.setText("Download selesai, tetapi file tidak ditemukan.")
            QMessageBox.warning(
                self,
                "File Tidak Ditemukan",
                "Download selesai, tetapi file hasil unduhan tidak ditemukan."
            )
            return

        # Serahkan ke video cutter
        self._downloaded_filepath = filepath
        self.download_ready.emit(filepath)
        self.accept()

    @staticmethod
    def _resolve_output_path(info: dict) -> str | None:
        """Cari path file hasil unduhan dari dict info yt-dlp."""
        if not isinstance(info, dict):
            return None

        # 1. Key standar yt-dlp
        for key in ("filepath", "_filename"):
            p = info.get(key)
            if p and os.path.isfile(p):
                return os.path.abspath(p)

        # 2. requested_downloads (hasil merge bv+ba)
        for item in info.get("requested_downloads") or []:
            for key in ("filepath", "_filename"):
                p = item.get(key)
                if p and os.path.isfile(p):
                    return os.path.abspath(p)

        # 3. entries (playlist — ambil yang pertama)
        for entry in info.get("entries") or []:
            p = DownloadByUrlDialog._resolve_output_path(entry)
            if p:
                return p

        return None

    def finish_dialog(self):
        """Serahkan file hasil download ke CutterPage saat tombol Tutup ditekan."""
        filepath = self._downloaded_filepath
        if filepath and os.path.isfile(filepath):
            self.download_ready.emit(filepath)
            self.accept()
            return
        self.reject()

    def _reset_most_played(self):
        if self.most_played_cb.isChecked():
            self.most_played_cb.setChecked(False)

    def request_cancel(self):
        """Dipanggil saat dialog ditutup (reject/close) agar worker berhenti bersih."""
        if self.heatmap_worker and self.heatmap_worker.isRunning():
            self.heatmap_worker.cancel()
            self.heatmap_worker.wait(2000)
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(2000)

    # ------------------------------------------------------- window drag
    def eventFilter(self, obj, event):
        if obj is not None and event.type() == QtCore.QEvent.Type.MouseButtonPress:
            if event.button() == QtCore.Qt.MouseButton.LeftButton:
                self.windowHandle().startSystemMove()
                return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        self.request_cancel()
        super().closeEvent(event)

    def reject(self):
        self.request_cancel()
        super().reject()
class CutterPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        # self.url_download_worker = DownloadWorker()
        self.thumb_worker: ThumbnailWorker | None = None
        self._duration = 0.0
        self._video_path = ""

        self._process_text = "Siap"
        self._thumb_text = "Thumbnail 0/0 thumbnail siap"

        self._preview_timer = QTimer()
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(50)
        self._preview_timer.timeout.connect(self._update_preview_frame)
        self._pending_preview_time = 0.0

        self._auto_stop_end: float | None = None

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setMinimumSize(0, 0)

        self._build_ui()
        self._wire_preview()

        self.timeline.setMinimumHeight(160)
        self.timeline.text_double_click.connect(self._on_text_double_click)

    def _on_text_double_click(self, text_id: int):
        item = next((t for t in self.timeline.texts() if t.id == text_id), None)
        if item is None:
            return
        dlg = TextEditDialog(item, self)
        if dlg.exec() == QDialog.Accepted:
            if dlg.was_deleted():
                self.timeline.remove_text(text_id)
                return
            r = dlg.result_item()
            self.timeline.update_text(
                text_id,
                text=r.text,
                font_size=r.font_size,
                color=r.color,
                x_ratio=r.x_ratio,
                y_ratio=r.y_ratio,
                bg_enabled=r.bg_enabled,
                bg_color=r.bg_color,
                bg_opacity=r.bg_opacity,
            )

    def _add_text_at_playhead(self):
        if self.timeline.duration <= 0:
            return
        start = self.timeline.playhead_seconds()
        dur = self.timeline.DEFAULT_TEXT_DURATION
        end = min(start + dur, self.timeline.duration)
        if end - start < self.timeline.MIN_TEXT_DURATION:
            start = max(0.0, end - self.timeline.MIN_TEXT_DURATION)
        item = TextItem(
            text="Teks baru",
            start_sec=start,
            end_sec=end,
            x_ratio=0.5,
            y_ratio=0.8,
            font_size=48,
            color="#000000",
        )
        self.timeline.add_text(item)

    # ---------- wiring ----------
    def _wire_preview(self):
        pw = self.preview_widget
        pw.play_clicked.connect(self._on_play_preview_clicked)
        pw.position_changed.connect(self._on_player_position)
        pw.duration_changed.connect(self.timeline.set_duration)

        self.timeline.seek_requested.connect(pw.seek)
        self.timeline.range_dragging.connect(self._on_range_dragging)

        self.timeline.texts_changed.connect(
            lambda: self.preview_widget.set_texts(self.timeline.texts())
        )
        self.preview_widget.set_playhead(self.timeline.playhead_seconds())

    def _on_player_position(self, sec: float):
        self.timeline.set_playhead(sec)
        if self._auto_stop_end is not None and sec >= self._auto_stop_end:
            end = self._auto_stop_end
            self._auto_stop_end = None
            self.preview_widget.pause()
            self.timeline.set_playhead(end)

    def _on_range_dragging(self, handle: str, start_sec: float, end_sec: float):
        if not self.preview_widget.is_playing():
            return
        if handle == "start":
            self._auto_stop_end = end_sec
            self.preview_widget.seek_while_playing(start_sec)
        elif handle == "end":
            self._auto_stop_end = None
            self.preview_widget.pause()

    def _on_play_preview_clicked(self):
        if self.preview_widget.is_playing():
            self._auto_stop_end = None
            self.preview_widget.pause()
            return

        self._auto_stop_end = self.timeline.end_seconds()
        pos = self.preview_widget.position()
        start = self.timeline.start_seconds()
        end = self.timeline.end_seconds()
        if pos < start or pos >= end:
            self.preview_widget.play_from(start)
        else:
            self.preview_widget.play()

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 10, 20, 10)
        root.setSpacing(8)

        header = QLabel("Video Cutter")
        header.setObjectName("header")
        root.addWidget(header, stretch=0)

        content_row = QHBoxLayout()
        content_row.setSpacing(4)

        # toolbar
        self.toolbar = QToolBar()
        self.toolbar.setIconSize(QSize(24, 24))
        self.toolbar.setOrientation(Qt.Vertical)
        self.toolbar.setMinimumWidth(44)  # lebar toolbar
        self.toolbar.setMinimumHeight(200)  # beri tinggi supaya tidak runtuh
        self.toolbar.setMovable(False)
        self.toolbar.setStyleSheet("""
            QToolBar {
                background: transparent;
                border: none;
                spacing: 4px;
                padding: 0;
            }
            QToolButton {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2f4a63,
                    stop:1 #233648
                );
                border-top: px solid #3f6280;
                border-left: 2px solid #2b3f54;
                border-right: 2px solid #1b2a39;
                border-bottom: 3px solid #14202b;
                border-radius: 6px;
                padding: 0;
                color: #f1f5f9;
                font-size: 16px;
                min-width: 36px;
                max-width: 36px;
                min-height: 36px;
                max-height: 36px;
            }
            QToolButton:hover {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3b5c7a,
                    stop:1 #2a4560
                );
                border-top: 1px solid #5b86a8;
                border-bottom: 2px solid #16232f;
            }
            QToolButton:pressed {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a2a38,
                    stop:1 #263a4d
                );
                border-top: 2px solid #0f1922;
                border-bottom: 1px solid #2f4a63;
            }
            QToolButton:disabled {
                background-color: #1c2833;
                border-top: 1px solid #263646;
                border-left: 1px solid #22303e;
                border-right: 1px solid #18232e;
                border-bottom: 2px solid #121a22;
                color: #5a7186;
            }
        """)
        self.toolbar.addSeparator()
        self.act_reset = self._make_action("↺", "Reset rentang ke 0 – durasi")
        self.act_reset.triggered.connect(self._reset_range)
        self.toolbar.addAction(self.act_reset)

        self.toolbar.addSeparator()

        self.act_source = self._make_action("📂", "Pilih file video sumber")
        self.act_source.triggered.connect(self.browse_file)
        self.toolbar.addAction(self.act_source)

        self.act_url = self._make_action("🔗", "Copy & paste url kedalam input text")
        self.act_url.triggered.connect(self.browse_url)
        self.toolbar.addAction(self.act_url)

        self.toolbar.addSeparator()

        self.act_add_text = self._make_action("+T", "Tambah teks baru di posisi playhead")
        self.act_add_text.triggered.connect(self._add_text_at_playhead)
        self.toolbar.addAction(self.act_add_text)

        self.act_clear_texts = self._make_action("🗑T", "Hapus semua teks di timeline")
        self.act_clear_texts.triggered.connect(self._clear_all_texts)
        self.toolbar.addAction(self.act_clear_texts)

        # self.toolbar.addSeparator()

        self.act_cut = self._make_action("✂️", "Mulai potong klip")
        self.act_cut.triggered.connect(self.start_cut)
        self.toolbar.addAction(self.act_cut)

        self.act_cancel = self._make_action("✖", "Batalkan proses yang sedang berjalan")
        self.act_cancel.triggered.connect(self.cancel_cut)
        self.act_cancel.setEnabled(False)
        self.toolbar.addAction(self.act_cancel)

        # self.toolbar.addSeparator()

        self.act_clear_log = self._make_action("🗑", "Bersihkan log")
        self.act_clear_log.triggered.connect(lambda: self.log_output.clear())
        self.toolbar.addAction(self.act_clear_log)

        # editor container
        editor_container = QFrame()
        editor_container.setObjectName("editorContainer")
        editor_container.setStyleSheet("""
            #editorContainer {
                background-color: #1a1a1a;
                border-radius: 12px;
                border: 1px solid #333;
            }
        """)
        editor_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        editor_container.setMinimumSize(0, 0)

        editor_layout = QVBoxLayout(editor_container)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        self.file_label = QLabel("Belum ada file dipilih")
        self.file_label.setObjectName("sourceFileLabel")
        self.file_label.setWordWrap(True)
        self.file_label.setFixedHeight(40)
        self.file_label.setContentsMargins(12, 10, 12, 6)
        self.file_label.setStyleSheet("""
            #sourceFileLabel {
                color: #e0e0e0;
                font-size: 13px;
                font-weight: 300;
                background: transparent;
            }
        """)
        self.file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor_layout.addWidget(
            self.file_label, stretch=0, alignment=Qt.AlignmentFlag.AlignTop
        )

        self.preview_widget = VideoPreviewWidget()
        self.preview_widget.setMinimumHeight(200)
        self.preview_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        editor_layout.addWidget(self.preview_widget, stretch=4)

        self.timeline = TimelineWidget()
        self.timeline.range_changed.connect(self._on_timeline_range_changed)
        self.timeline.scrub_moved.connect(self._on_scrub_moved)
        self.timeline.seek_requested.connect(self._on_seek_requested)
        self.timeline.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        editor_layout.addWidget(self.timeline, stretch=1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(1)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #2a2a2a;
                border: none;
                border-radius: 2px;
                margin: 0px 8px;
            }
            QProgressBar::chunk {
                background-color: #4caf50;
                border-radius: 2px;
            }
        """)
        editor_layout.addWidget(self.progress_bar, stretch=0)

        content_row.addWidget(editor_container, stretch=1)
        content_row.addWidget(self.toolbar, stretch=0)

        root.addLayout(content_row, stretch=1)

        # baris atas: start | end | stretch | status
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self.start_input = QLineEdit()
        self.start_input.setPlaceholderText("0:00.00")
        self.start_input.setMaximumWidth(110)
        self.start_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.start_input.setStyleSheet("font-weight: 500; font-size: 16px;")
        self.start_input.editingFinished.connect(self._on_start_edit)
        top_row.addWidget(self.start_input)

        self.end_input = QLineEdit()
        self.end_input.setPlaceholderText("0:00.00")
        self.end_input.setMaximumWidth(110)
        self.end_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.end_input.setStyleSheet("font-weight: 500;  font-size: 16px;")
        self.end_input.editingFinished.connect(self._on_end_edit)
        top_row.addWidget(self.end_input)

        top_row.addStretch(1)

        self.thumb_status = QLabel(
            f"{self._process_text} | {self._thumb_text}"
        )
        self.thumb_status.setObjectName("detailLabel")
        top_row.addWidget(self.thumb_status, stretch=0)

        root.addLayout(top_row)

        self.reencode_cb = QCheckBox(
            "Re-encode (akurat frame-by-frame; lebih lambat)"
        )
        root.addWidget(self.reencode_cb, stretch=0)

        root.addWidget(self._label("Log"), stretch=0)
        self.log_output = LogWidget()
        self.log_output.setFixedHeight(100)
        root.addWidget(self.log_output, stretch=0)

    def _make_action(self, text: str, tooltip: str):
        act = self.toolbar.addAction(text)
        act.setToolTip(tooltip)
        return act

    @staticmethod
    def _label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("fieldLabel")
        return lbl

    @staticmethod
    def _open_folder(path: str):
        try:
            if not path or not os.path.isdir(path):
                return
            if os.name == "nt":
                os.startfile(path)
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception:
            pass

    # ---------- file ----------
    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih Video",
            "",
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.ts);;All Files (*)",
        )
        if not path:
            return

        if self.timeline.texts():
            ans = QMessageBox.question(
                self,
                "Konfirmasi",
                "Membuka source baru akan menghapus teks lama. Lanjutkan?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                return
            self.timeline.clear_texts()

        self.load_video(path)

    def browse_url(self):
        dialog = DownloadByUrlDialog(self)
        dialog.download_ready.connect(self.load_downloaded_video)
        dialog.exec()

    def load_downloaded_video(self, filepath: str):
        if not filepath or not os.path.isfile(filepath):
            QMessageBox.warning(
                self,
                "Download Error",
                "File hasil download tidak ditemukan."
            )
            return

        if self.timeline.texts():
            ans = QMessageBox.question(
                self,
                "Konfirmasi",
                "Membuka video baru akan menghapus teks lama. Lanjutkan?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                return
            self.timeline.clear_texts()

        self.load_video(filepath)

    def load_video(self, path: str):
        """Memuat video ke preview, timeline, dan thumbnail worker."""
        if not path or not os.path.isfile(path):
            QMessageBox.warning(
                self,
                "File Tidak Valid",
                "File video tidak ditemukan."
            )
            return

        self._video_path = os.path.abspath(path)
        self.file_label.setText(self._video_path)

        self.log("=" * 60)
        self.log(f"Sumber: {self._video_path}")

        if self.thumb_worker and self.thumb_worker.isRunning():
            self.thumb_worker.cancel()
            self.thumb_worker.wait(1000)
        self.thumb_worker = None

        self.timeline.clear_thumbnails()
        self.preview_widget.clear()

        try:
            dur, _, has_video = probe_media(self._video_path)
        except Exception as exc:
            self.file_label.setText(
                f"Sumber: {self._video_path} — gagal probe ({exc})"
            )
            self._duration = 0.0
            self.timeline.set_duration(0.0)
            return

        if not has_video:
            self.file_label.setText(
                f"Sumber: {self._video_path} — file tidak memiliki video stream"
            )
            self._duration = 0.0
            self.timeline.set_duration(0.0)
            return

        self._duration = dur
        self.timeline.set_range(0.0, dur)
        self.start_input.setText(_fmt_time(0.0))
        self.end_input.setText(_fmt_time(dur))

        self.preview_widget.load(self._video_path)

        from core import thumbnails

        times = thumbnails.plan_thumbnail_times(dur)
        self.timeline.set_thumbnails_count(len(times))
        self._update_thumb_status(f"Memuat 0/{len(times)} thumbnail")

        self.thumb_worker = ThumbnailWorker(
            self._video_path, dur, len(times)
        )
        self.thumb_worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        self.thumb_worker.finished_signal.connect(self._on_thumbnails_done)
        self.thumb_worker.start()

        self._request_preview_update(0.0)

    def _clear_all_texts(self):
        if not self.timeline.texts():
            return
        ans = QMessageBox.question(
            self,
            "Konfirmasi",
            "Hapus semua teks di timeline?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        self.timeline.clear_texts()
        self.log("Semua teks dihapus.")

    # ---------- thumbnail callbacks ----------
    def _on_thumbnail_ready(self, index: int, image):
        self.timeline.set_thumbnail_at(index, image)
        loaded = self.timeline.loaded_thumbnail_count()
        total = self.timeline.thumbnail_count()
        self._update_thumb_status(f"Memuat {loaded}/{total} thumbnail")
        if index == 0:
            self.preview_widget.set_thumbnail(image)

    def _on_thumbnails_done(self, success: bool, message: str):
        self._update_thumb_status(f"Thumbnail {message}")
        self.thumb_worker = None

    # ---------- status ----------
    def _set_process_text(self, text: str):
        self._process_text = text or "-"
        self.thumb_status.setText(
            f"{self._process_text} | {self._thumb_text}"
        )

    def _update_thumb_status(self, thumbnail_text: str):
        self._thumb_text = thumbnail_text
        self.thumb_status.setText(
            f"{self._process_text} | {self._thumb_text}"
        )

    # ---------- preview / timeline ----------
    def _on_scrub_moved(self, seconds: float):
        self.preview_widget.set_time_info(seconds, self._duration)
        self._pending_preview_time = seconds
        self._preview_timer.start()

    def _on_seek_requested(self, seconds: float):
        self.preview_widget.set_time_info(seconds, self._duration)

    def _request_preview_update(self, seconds: float):
        self._pending_preview_time = seconds
        self.preview_widget.set_time_info(seconds, self._duration)
        self._preview_timer.start()

    def _update_preview_frame(self):
        if self._duration <= 0:
            return
        pix = self.timeline.thumbnail_nearest(self._pending_preview_time)
        if not pix.isNull():
            self.preview_widget.show_frame(pix.toImage())

    def _on_timeline_range_changed(self, start: float, end: float):
        self.start_input.blockSignals(True)
        self.end_input.blockSignals(True)
        self.start_input.setText(_fmt_time(start))
        self.end_input.setText(_fmt_time(end))
        self.start_input.blockSignals(False)
        self.end_input.blockSignals(False)

        if self.preview_widget.is_playing():
            if self._auto_stop_end is None or abs(end - self._auto_stop_end) > 1e-3:
                self._auto_stop_end = None
                self.preview_widget.pause()

    def _on_start_edit(self):
        try:
            val = _parse_time(self.start_input.text())
        except ValueError:
            self.start_input.setText(_fmt_time(self.timeline.start_seconds()))
            return
        self.timeline.set_range(val, self.timeline.end_seconds())
        self._on_timeline_range_changed(
            self.timeline.start_seconds(), self.timeline.end_seconds()
        )

    def _on_end_edit(self):
        try:
            val = _parse_time(self.end_input.text())
        except ValueError:
            self.end_input.setText(_fmt_time(self.timeline.end_seconds()))
            return
        self.timeline.set_range(self.timeline.start_seconds(), val)
        self._on_timeline_range_changed(
            self.timeline.start_seconds(), self.timeline.end_seconds()
        )

    def _reset_range(self):
        self.timeline.set_range(0.0, self._duration)
        self._on_timeline_range_changed(0.0, self._duration)

    # ---------- logging ----------
    def log(self, msg: str):
        self.log_output.append_log(msg)

    # ---------- cut ----------
    def start_cut(self):
        src = self._video_path or ""
        if not src or not os.path.isfile(src):
            QMessageBox.warning(self, "Peringatan", "Pilih file video yang valid.")
            return
        if self.worker and self.worker.isRunning():
            return

        start = self.timeline.start_seconds()
        end = self.timeline.end_seconds()
        if end <= start:
            QMessageBox.warning(self, "Waktu", "Waktu akhir harus > waktu mulai.")
            return

        out_dir = ensure_cut_dir()
        self.log(f"Output: {out_dir}")

        texts = self.timeline.texts()
        has_texts = bool(texts)

        self.progress_bar.setValue(0)
        self._set_process_text("Memulai pemotongan...")
        self.act_cut.setEnabled(False)
        self.act_cancel.setEnabled(True)
        self.log("-" * 40)
        self.log(f"Range : {_fmt_time(start)} → {_fmt_time(end)}")

        if has_texts:
            self.log(
                f"Mode  : burn-in teks ({len(texts)} item) — re-encode dipaksa"
            )
            self.worker = TextBurnInWorker(
                input_path=src,
                output_dir=out_dir,
                start_sec=start,
                end_sec=end,
                texts_as_dict=[t.to_dict() for t in texts],
            )
        else:
            self.log(
                f"Mode  : {'re-encode' if self.reencode_cb.isChecked() else 'copy'}"
            )
            self.worker = CutterWorker(
                input_path=src,
                output_dir=out_dir,
                start_sec=start,
                end_sec=end,
                reencode=self.reencode_cb.isChecked(),
            )
        self.worker.progress_changed.connect(self.on_progress)
        self.worker.log_message.connect(self.log)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def cancel_cut(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self._set_process_text("Membatalkan...")
            self.log("Permintaan pembatalan dikirim.")
            self.act_cancel.setEnabled(False)

    def on_progress(self, percent: float, speed: str, eta: str, status: str):
        self.progress_bar.setValue(int(percent))
        self._set_process_text(status)

    def on_finished(self, success: bool, message: str):
        self.act_cut.setEnabled(True)
        self.act_cancel.setEnabled(False)
        if success:
            self.progress_bar.setValue(100)
            self._set_process_text("Selesai ✓")
            self.log(f"File tersimpan: {message}")
        else:
            self._set_process_text("Gagal / Dibatalkan")
            self.log(f"Gagal: {message}")
        self.worker = None

    def has_active_worker(self) -> bool:
        return (
            (self.worker is not None and self.worker.isRunning())
            or (self.thumb_worker is not None and self.thumb_worker.isRunning())
        )

    def request_cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(2000)
        if self.thumb_worker and self.thumb_worker.isRunning():
            self.thumb_worker.cancel()
            self.thumb_worker.wait(2000)