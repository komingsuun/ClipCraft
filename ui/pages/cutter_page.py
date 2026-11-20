import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QProgressBar, QPushButton,
    QVBoxLayout, QWidget, QSizePolicy, QDialog,
)

from core.ffmpeg import probe_media
from core.video_cutter import ensure_cut_dir
from core.workers import CutterWorker, TextBurnInWorker, ThumbnailWorker
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


class CutterPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
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

        self.preview_widget.set_texts(self.timeline.texts())

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
            y_ratio=0.5,
            font_size=48,
            color="#FFFFFF",
        )
        self.timeline.add_text(item)
        self.preview_widget.set_texts(self.timeline.texts())

    # ---------- wiring ----------
    def _wire_preview(self):
        pw = self.preview_widget
        pw.play_clicked.connect(self._on_play_preview_clicked)
        pw.position_changed.connect(self._on_player_position)
        pw.duration_changed.connect(self.timeline.set_duration)

        self.timeline.seek_requested.connect(pw.seek)
        self.timeline.range_dragging.connect(self._on_range_dragging)

        self.timeline.text_changed.connect(
            lambda *_: self.preview_widget.set_texts(self.timeline.texts())
        )
        self.timeline.text_selected.connect(
            lambda *_: self.preview_widget.set_texts(self.timeline.texts())
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
        else:
            self._auto_stop_end = self.timeline.end_seconds()
            self.preview_widget.play_from(self.timeline.start_seconds())

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(8)

        header = QLabel("Video Cutter")
        header.setObjectName("header")
        root.addWidget(header, stretch=0)

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

        root.addWidget(editor_container, stretch=1)

        self.thumb_status = QLabel(
            f"{self._process_text} | {self._thumb_text}"
        )
        self.thumb_status.setObjectName("detailLabel")
        root.addWidget(self.thumb_status, stretch=0)

        time_row = QHBoxLayout()

        self.start_input = QLineEdit()
        self.start_input.setPlaceholderText("0:00.00")
        self.start_input.setMaximumWidth(100)
        self.start_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.start_input.editingFinished.connect(self._on_start_edit)
        time_row.addWidget(self.start_input)

        self.end_input = QLineEdit()
        self.end_input.setPlaceholderText("0:00.00")
        self.end_input.setMaximumWidth(100)
        self.end_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.end_input.editingFinished.connect(self._on_end_edit)
        time_row.addWidget(self.end_input)

        reset_btn = QPushButton("Reset")
        reset_btn.setObjectName("gnrlBtn")
        reset_btn.clicked.connect(self._reset_range)
        time_row.addWidget(reset_btn)

        browse_btn = QPushButton("Source…")
        browse_btn.setObjectName("gnrlBtn")
        browse_btn.clicked.connect(self.browse_file)
        time_row.addWidget(browse_btn, stretch=0)

        self.btn_add_text = QPushButton("+ Teks")
        self.btn_add_text.setObjectName("gnrlBtn")
        self.btn_add_text.setCursor(Qt.PointingHandCursor)
        self.btn_add_text.clicked.connect(self._add_text_at_playhead)
        time_row.addWidget(self.btn_add_text, stretch=1)

        self.start_btn = QPushButton("Mulai Potong")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.clicked.connect(self.start_cut)
        time_row.addWidget(self.start_btn, stretch=1)
        time_row.addStretch()

        self.reencode_cb = QCheckBox(
            "Re-encode (akurat frame-by-frame; lebih lambat)"
        )
        root.addWidget(self.reencode_cb, stretch=0)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(0)
        btn_row.setContentsMargins(0, 0, 0, 0)

        self.cancel_btn = QPushButton("Batalkan")
        self.cancel_btn.setObjectName("dangerBtn")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_cut)

        clear_btn = QPushButton("Bersihkan Log")
        clear_btn.clicked.connect(lambda: self.log_output.clear())
        clear_btn.setObjectName("cleanLogBtn")
        clear_btn.setEnabled(True)

        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(clear_btn)

        time_row.addLayout(btn_row)
        root.addLayout(time_row)

        root.addWidget(self._label("Log"), stretch=0)
        self.log_output = LogWidget()
        self.log_output.setFixedHeight(150)
        root.addWidget(self.log_output, stretch=0)

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

        self._video_path = path
        self.file_label.setText(f"{path}")
        self.log("=" * 60)
        self.log(f"Sumber: {path}")

        if self.thumb_worker and self.thumb_worker.isRunning():
            self.thumb_worker.cancel()
            self.thumb_worker.wait(1000)

        self.timeline.clear_thumbnails()
        self.preview_widget.clear()

        try:
            dur, _, has_video = probe_media(path)
        except Exception as exc:
            self.file_label.setText(
                f"Sumber: {path} — gagal probe ({exc})"
            )
            self._duration = 0.0
            self.timeline.set_duration(0.0)
            return

        if not has_video:
            self.file_label.setText(
                f"Sumber: {path} — file tidak memiliki video stream"
            )
            self._duration = 0.0
            self.timeline.set_duration(0.0)
            return

        self._duration = dur
        self.timeline.set_range(0.0, dur)
        self.start_input.setText(_fmt_time(0.0))
        self.end_input.setText(_fmt_time(dur))

        self.preview_widget.load(path)

        from core import thumbnails
        times = thumbnails.plan_thumbnail_times(dur)
        self.timeline.set_thumbnails_count(len(times))
        self._update_thumb_status(f"Memuat 0/{len(times)} thumbnail")

        self.thumb_worker = ThumbnailWorker(path, dur, len(times))
        self.thumb_worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        self.thumb_worker.finished_signal.connect(self._on_thumbnails_done)
        self.thumb_worker.start()

        self._request_preview_update(0.0)

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
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
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
            self.cancel_btn.setEnabled(False)

    def on_progress(self, percent: float, speed: str, eta: str, status: str):
        self.progress_bar.setValue(int(percent))
        self._set_process_text(status)

    def on_finished(self, success: bool, message: str):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
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