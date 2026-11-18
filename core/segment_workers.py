import os
import shutil
import subprocess
import tempfile

import yt_dlp
from PySide6.QtCore import QThread, Signal


COMPRESSION_PRESETS = {
    "Original": (1.00, 18),
    "High": (1.00, 23),
    "Balanced": (0.75, 26),
    "Compact": (0.50, 28),
    "Small": (0.35, 30),
}

HEATMAP_PADDING_SECONDS = 5


def _build_ydl_options(cookies_from_browser=None, **extra):
    """Options yt-dlp bersama untuk pemeriksaan metadata dan unduhan."""
    options = {
        "quiet": True,
        "no_warnings": True,
        "remote_components": ["ejs:github"],
        "sleep_interval_requests": 1,
        "noplaylist": True,
        **extra,
    }

    node_path = shutil.which("node")
    if node_path:
        options["js_runtimes"] = {"node": {"path": node_path}}

    if cookies_from_browser:
        options["cookiesfrombrowser"] = (
            cookies_from_browser,
            None,
            None,
            None,
        )

    return options


class HeatmapCheckWorker(QThread):
    """Mengecek heatmap tanpa membekukan GUI."""

    result_ready = Signal(bool, dict, str)
    log_message = Signal(str)

    def __init__(self, url, cookies_from_browser=None, parent=None):
        super().__init__(parent)
        self.url = url
        self.cookies_from_browser = cookies_from_browser
        self._cancel_requested = False

    def run(self):
        try:
            self.log_message.emit("Memeriksa metadata dan heatmap URL...")
            options = _build_ydl_options(
                self.cookies_from_browser,
                skip_download=True,
            )

            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(self.url, download=False)

            if self._cancel_requested:
                self.result_ready.emit(False, {}, "Pemeriksaan dibatalkan.")
                return

            heatmap = (info or {}).get("heatmap") or []
            if not heatmap:
                self.result_ready.emit(False, {}, "")
                return

            peak = max(heatmap, key=lambda item: float(item.get("value") or 0))
            raw_start = float(peak.get("start_time") or 0)
            raw_end = float(peak.get("end_time") or 0)
            duration = float((info or {}).get("duration") or raw_end)

            if raw_end <= raw_start:
                self.result_ready.emit(False, {}, "")
                return

            start = max(0.0, raw_start - HEATMAP_PADDING_SECONDS)
            end = raw_end + HEATMAP_PADDING_SECONDS
            if duration > 0:
                end = min(duration, end)

            if end <= start:
                self.result_ready.emit(False, {}, "")
                return

            segment = {
                "title": (info or {}).get("title") or "Video",
                "id": (info or {}).get("id") or "",
                "extractor_key": (info or {}).get("extractor_key") or "",
                "duration": duration,
                "start": start,
                "end": end,
                "peak_value": float(peak.get("value") or 0),
            }
            self.log_message.emit(
                f"Heatmap ditemukan. Segmen terpopuler: "
                f"{start:.0f}s–{end:.0f}s."
            )
            self.result_ready.emit(True, segment, "")
        except yt_dlp.utils.DownloadError as exc:
            self.result_ready.emit(False, {}, str(exc))
        except Exception as exc:
            self.result_ready.emit(
                False, {}, f"{type(exc).__name__}: {exc}"
            )

    def cancel(self):
        self._cancel_requested = True


class MostPlayedDownloadWorker(QThread):
    """
    Mengunduh satu sumber A/V gabungan, lalu memotong segmen dengan FFmpeg.
    Signal progress sengaja sama dengan DownloadWorker agar UI yang ada tetap dipakai.
    """

    progress_changed = Signal(float, str, str, str)
    log_message = Signal(str)
    finished_signal = Signal(bool, dict)

    def __init__(
        self,
        url,
        output_dir,
        segment,
        compression_preset="Balanced",
        cookies_from_browser=None,
        parent=None,
    ):
        super().__init__(parent)
        self.url = url
        self.output_dir = output_dir
        self.segment = dict(segment)
        self.compression_preset = compression_preset
        self.cookies_from_browser = cookies_from_browser
        self._cancel_requested = False
        self._ffmpeg_process = None
        self._download_progress = 0.0

    def _progress_hook(self, data):
        if self._cancel_requested:
            raise yt_dlp.utils.DownloadCancelled(
                "Dibatalkan oleh pengguna"
            )

        if data.get("status") == "downloading":
            percent_text = data.get("_percent_str", "0%").strip()
            try:
                percent = float(percent_text.replace("%", "").strip())
            except (TypeError, ValueError):
                percent = 0.0

            # Unduhan mengisi 0–80%; pemotongan FFmpeg mengisi 80–100%.
            self._download_progress = max(
                self._download_progress,
                min(80.0, max(0.0, percent * 0.8)),
            )
            self.progress_changed.emit(
                self._download_progress,
                data.get("_speed_str", "N/A").strip(),
                data.get("_eta_str", "N/A").strip(),
                "Mengunduh sumber video...",
            )
        elif data.get("status") == "finished":
            self._download_progress = 80.0
            self.progress_changed.emit(
                80.0, "-", "-", "Menyiapkan pemotongan segmen..."
            )

    @staticmethod
    def _unique_output_path(directory, title, media_id):
        safe_title = yt_dlp.utils.sanitize_filename(
            title or "video", restricted=False
        ).strip(" .")
        if not safe_title:
            safe_title = "video"

        base = f"{safe_title} [{media_id or 'media'}] [Most Played]"
        path = os.path.join(directory, f"{base}.mp4")
        counter = 2
        while os.path.exists(path):
            path = os.path.join(directory, f"{base} ({counter}).mp4")
            counter += 1
        return path

    @staticmethod
    def _locate_downloaded_source(info, ydl, temp_dir):
        candidates = []
        if isinstance(info, dict):
            candidates.extend([info.get("filepath"), info.get("_filename")])
            try:
                candidates.append(ydl.prepare_filename(info))
            except Exception:
                pass
            for item in info.get("requested_downloads") or []:
                candidates.extend([item.get("filepath"), item.get("_filename")])

        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return os.path.abspath(candidate)

        # Fallback untuk hasil merge yt-dlp ketika filepath belum terisi.
        ignored = (".part", ".ytdl", ".json", ".jpg", ".jpeg", ".png", ".webp")
        for root, _, names in os.walk(temp_dir):
            for name in names:
                if name.lower().endswith(ignored):
                    continue
                path = os.path.join(root, name)
                if os.path.isfile(path) and os.path.getsize(path) > 0:
                    return os.path.abspath(path)
        return None

    def _cut_segment(self, source_path, output_path):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError(
                "FFmpeg tidak ditemukan. Pastikan FFmpeg terpasang."
            )

        start = float(self.segment["start"])
        end = float(self.segment["end"])
        duration = end - start
        if duration <= 0:
            raise RuntimeError("Rentang segmen heatmap tidak valid.")

        scale, crf = COMPRESSION_PRESETS.get(
            self.compression_preset,
            COMPRESSION_PRESETS["Balanced"],
        )

        temp_output = output_path[:-4] + ".processing.mp4"
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-ss", f"{start:.3f}",
            "-i", source_path,
            "-t", f"{duration:.3f}",
            "-map", "0:v:0",
            "-map", "0:a:0?",
        ]

        if scale < 1.0:
            vf = (
                f"scale=trunc(iw*{scale}/2)*2:"
                f"trunc(ih*{scale}/2)*2"
            )
            command += ["-vf", vf]

        # H.264/AAC menjaga hasil potongan kompatibel dengan pemutar umum.
        # Preset Original memakai CRF 18 dan resolusi penuh.
        command += [
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", str(crf),
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            "-progress", "pipe:1",
            "-nostats",
            temp_output,
        ]

        self.log_message.emit(
            f"Memotong segmen {start:.0f}s–{end:.0f}s "
            f"dengan preset {self.compression_preset}."
        )
        self.progress_changed.emit(
            80.0, "-", "-", "Memotong dan memproses segmen..."
        )

        try:
            self._ffmpeg_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            for line in self._ffmpeg_process.stdout:
                if self._cancel_requested:
                    self._ffmpeg_process.terminate()
                    raise RuntimeError("Pemotongan dibatalkan oleh pengguna.")

                line = line.strip()
                if line.startswith("out_time_ms="):
                    try:
                        elapsed = int(line.split("=", 1)[1]) / 1_000_000
                        percent = min(99.0, max(0.0, elapsed / duration * 100))
                        overall = 80.0 + percent * 0.2
                        self.progress_changed.emit(
                            overall,
                            "-",
                            "-",
                            "Memotong dan memproses segmen...",
                        )
                    except (TypeError, ValueError):
                        pass

            return_code = self._ffmpeg_process.wait()
            stderr = (
                self._ffmpeg_process.stderr.read()
                if self._ffmpeg_process.stderr
                else ""
            )
            if return_code != 0:
                raise RuntimeError(f"FFmpeg gagal: {stderr[-1500:]}")
            if not os.path.isfile(temp_output) or os.path.getsize(temp_output) == 0:
                raise RuntimeError("FFmpeg tidak menghasilkan file segmen.")

            os.replace(temp_output, output_path)
        finally:
            self._ffmpeg_process = None
            if os.path.exists(temp_output):
                try:
                    os.remove(temp_output)
                except OSError:
                    pass

    def run(self):
        os.makedirs(self.output_dir, exist_ok=True)
        info = {}
        success = False
        temp_dir = tempfile.mkdtemp(
            prefix=".clipcraft-most-played-",
            dir=self.output_dir,
        )

        try:
            self.log_message.emit(
                f"Mengunduh sumber untuk segmen most played: {self.url}"
            )
            ydl_options = _build_ydl_options(
                self.cookies_from_browser,
                format="bv*+ba/b",
                outtmpl=os.path.join(
                    temp_dir, "%(title).200s [%(id)s].%(ext)s"
                ),
                merge_output_format="mp4",
                progress_hooks=[self._progress_hook],
                ignoreerrors=False,
                continuedl=True,
                overwrites=True,
                verbose=False,
            )

            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                info = ydl.extract_info(self.url, download=True)
                source_path = (
                    self._locate_downloaded_source(info, ydl, temp_dir)
                    if info else None
                )

            if self._cancel_requested:
                raise RuntimeError("Unduhan dibatalkan oleh pengguna.")
            if not source_path:
                raise RuntimeError(
                    "File sumber hasil unduhan tidak ditemukan."
                )

            output_path = self._unique_output_path(
                self.output_dir,
                self.segment.get("title") or (info or {}).get("title"),
                self.segment.get("id") or (info or {}).get("id"),
            )
            self._cut_segment(source_path, output_path)

            success = True
            info = dict(info or {})
            info["filepath"] = output_path
            info["title"] = self.segment.get("title") or info.get("title")
            info["extractor_key"] = (
                self.segment.get("extractor_key")
                or info.get("extractor_key")
            )
            info["segment_start"] = self.segment["start"]
            info["segment_end"] = self.segment["end"]
            self.progress_changed.emit(
                100.0, "-", "-", "Unduhan segmen selesai."
            )
            self.log_message.emit(f"Segmen tersimpan: {output_path}")

        except yt_dlp.utils.DownloadCancelled as exc:
            self.log_message.emit(f"Unduhan dibatalkan: {exc}")
        except Exception as exc:
            self.log_message.emit(f"Unduhan segmen gagal: {type(exc).__name__}: {exc}")
        finally:
            if self._ffmpeg_process and self._ffmpeg_process.poll() is None:
                self._ffmpeg_process.terminate()
            shutil.rmtree(temp_dir, ignore_errors=True)
            self.finished_signal.emit(success, info or {})

    def cancel(self):
        self._cancel_requested = True
        if self._ffmpeg_process and self._ffmpeg_process.poll() is None:
            self._ffmpeg_process.terminate()