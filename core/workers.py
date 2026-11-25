import glob
import os
import re
import subprocess
import uuid

import yt_dlp
from PySide6.QtCore import QThread, Signal, QRect
from PySide6.QtGui import QImage, QPainter

from core.downloader import COMPRESSION_PRESETS
from core.ffmpeg import get_ffmpeg, probe_media, probe_stream_info
from core.ffmpeg import get_node

# ============================================================
# Helper nama file aman & pendek
# ============================================================
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MULTI_SPACE = re.compile(r'\s+')

_MAX_STEM_LEN = 120


# ============================================================
# Download + (opsional) kompres setelah unduh
# ============================================================
class DownloadWorker(QThread):
    progress_changed = Signal(float, str, str, str)  # percent, speed, eta, status
    log_message = Signal(str)
    finished_signal = Signal(bool, dict)

    def __init__(
        self,
        url: str,
        output_dir: str,
        noplaylist: bool,
        compression_preset: str = "Balanced",
        cookies_from_browser: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.url = url
        self.output_dir = output_dir
        self.noplaylist = noplaylist
        self.compression_preset = compression_preset
        self.cookies_from_browser = cookies_from_browser
        self._cancel_requested = False
        self._ffmpeg_process = None

    def progress_hook(self, d):
        if self._cancel_requested:
            raise yt_dlp.utils.DownloadCancelled("Dibatalkan oleh pengguna")

        if d["status"] == "downloading":
            percent_str = d.get("_percent_str", "0%").strip()
            speed = d.get("_speed_str", "N/A").strip()
            eta = d.get("_eta_str", "N/A").strip()
            try:
                percent_val = float(percent_str.replace("%", "").strip())
            except ValueError:
                percent_val = 0.0
            self.progress_changed.emit(percent_val, speed, eta, "Mengunduh...")
        elif d["status"] == "finished":
            self.progress_changed.emit(100.0, "-", "-", "Memproses file...")
            self.log_message.emit("Unduhan selesai, memproses file...")

    def _find_downloaded_file(self, info, ydl):
        if not isinstance(info, dict):
            return None
        candidates = [info.get("filepath"), info.get("_filename")]
        try:
            candidates.append(ydl.prepare_filename(info))
        except Exception:
            pass
        for item in info.get("requested_downloads") or []:
            candidates.extend([item.get("filepath"), item.get("_filename")])
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return os.path.abspath(candidate)
        media_id = info.get("id")
        if media_id:
            suffix = f"[{media_id}]"
            for name in os.listdir(self.output_dir):
                path = os.path.join(self.output_dir, name)
                if suffix in name and os.path.isfile(path) and not name.endswith((".part", ".ytdl")):
                    return os.path.abspath(path)
        return None

    def _find_downloaded_files(self, info, ydl):
        found = []
        entries = info.get("entries") if isinstance(info, dict) else None
        if entries:
            for entry in entries:
                path = self._find_downloaded_file(entry, ydl)
                if path and path not in found:
                    found.append(path)
        else:
            path = self._find_downloaded_file(info, ydl)
            if path:
                found.append(path)
        return found

    def _compress_video(self, input_path):
        preset = self.compression_preset
        settings = COMPRESSION_PRESETS.get(preset)
        if settings is None:
            self.log_message.emit("Preset Original: file dibiarkan tanpa kompresi.")
            return input_path

        ffmpeg = get_ffmpeg()
        scale, crf = settings
        duration, audio_codec, has_video = probe_media(input_path)
        if not has_video:
            self.log_message.emit("File tidak memiliki stream video; kompresi dilewati.")
            return input_path

        mp4_audio_codecs = {"aac", "mp3", "ac3", "eac3", "alac"}
        output_ext = ".mp4" if audio_codec is None or audio_codec in mp4_audio_codecs else ".mkv"
        base = os.path.splitext(input_path)[0]
        output_path = f"{base} [{preset}]{output_ext}"
        temp_path = f"{base} [{preset}].processing{output_ext}"

        if os.path.abspath(output_path) == os.path.abspath(input_path):
            raise RuntimeError("Nama file output sama dengan file sumber; kompresi dibatalkan.")

        if os.path.exists(output_path):
            stem, ext = os.path.splitext(output_path)
            counter = 2
            while os.path.exists(f"{stem} ({counter}){ext}"):
                counter += 1
            output_path = f"{stem} ({counter}){ext}"
            temp_path = f"{os.path.splitext(output_path)[0]}.processing{ext}"

        vf = f"scale=trunc(iw*{scale}/2)*2:trunc(ih*{scale}/2)*2"
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-i", input_path,
            "-map", "0:v:0", "-map", "0:a?",
            "-map_metadata", "0", "-map_chapters", "0",
            "-vf", vf,
            "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
            "-c:a", "copy",
        ]
        if output_ext == ".mp4":
            command += ["-movflags", "+faststart"]
        command += ["-progress", "pipe:1", "-nostats", temp_path]

        self.log_message.emit(
            f"Kompresi {preset}: skala {int(scale * 100)}%, CRF {crf}; "
            f"audio {audio_codec or 'tidak ada'} dipertahankan (copy)."
        )
        self.progress_changed.emit(0.0, "-", "-", "Mengompres video...")

        try:
            self._ffmpeg_process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )
            for line in self._ffmpeg_process.stdout:
                if self._cancel_requested:
                    self._ffmpeg_process.terminate()
                    raise RuntimeError("Kompresi dibatalkan oleh pengguna.")
                line = line.strip()
                if line.startswith("out_time_ms=") and duration > 0:
                    try:
                        elapsed = int(line.split("=", 1)[1]) / 1_000_000
                        percent = min(99.0, max(0.0, elapsed / duration * 100))
                        self.progress_changed.emit(percent, "-", "-", "Mengompres video...")
                    except ValueError:
                        pass

            return_code = self._ffmpeg_process.wait()
            stderr = self._ffmpeg_process.stderr.read() if self._ffmpeg_process.stderr else ""
            if return_code != 0:
                raise RuntimeError(f"FFmpeg gagal: {stderr[-1200:]}")
            if not os.path.isfile(temp_path) or os.path.getsize(temp_path) == 0:
                raise RuntimeError("FFmpeg tidak menghasilkan file output.")

            os.replace(temp_path, output_path)
            self.progress_changed.emit(100.0, "-", "-", "Kompresi selesai")
            original_size = os.path.getsize(input_path)
            compressed_size = os.path.getsize(output_path)
            if original_size:
                reduction = (1 - compressed_size / original_size) * 100
                self.log_message.emit(
                    f"Hasil kompresi: {output_path} "
                    f"({compressed_size / 1024 / 1024:.2f} MB; "
                    f"perubahan ukuran {reduction:+.1f}%)."
                )
            else:
                self.log_message.emit(f"Hasil kompresi: {output_path}")
            return output_path
        finally:
            self._ffmpeg_process = None
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def run(self):
        os.makedirs(self.output_dir, exist_ok=True)
        ydl_opts = {
            "format": "bv*+ba/b",
            "outtmpl": os.path.join(
                self.output_dir,
                "%(title).100B [%(id)s].%(ext)s"
            ),
            "trim_file_name": 100,
            "remote_components": ["ejs:github"],
            "sleep_interval_requests": 1,
            "sleep_interval": 2,
            "max_sleep_interval": 5,
            "writethumbnail": True,
            "embedthumbnail": True,
            "addmetadata": True,
            "progress_hooks": [self.progress_hook],
            "noplaylist": self.noplaylist,
            "ignoreerrors": False,
            "continuedl": True,
            "overwrites": False,
            "verbose": False,
        }

        node_path = get_node()
        if node_path:
            ydl_opts["js_runtimes"] = {"node": {"path": node_path}}

        if self.cookies_from_browser:
            ydl_opts["cookiesfrombrowser"] = (
                self.cookies_from_browser, None, None, None,
            )
            self.log_message.emit(f"Menggunakan cookie dari browser: {self.cookies_from_browser}")
        else:
            self.log_message.emit("Tidak menggunakan cookie browser.")

        info = {}
        success = False
        try:
            self.log_message.emit(f"Memproses URL: {self.url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                downloaded_paths = self._find_downloaded_files(info, ydl) if info else []

            if info and downloaded_paths:
                success = True
                self.log_message.emit(f"Unduhan berhasil: {len(downloaded_paths)} file.")
                if self.compression_preset != "Original":
                    for index, downloaded_path in enumerate(downloaded_paths, start=1):
                        if self._cancel_requested:
                            success = False
                            break
                        self.log_message.emit(
                            f"Memproses video {index}/{len(downloaded_paths)}: "
                            f"{os.path.basename(downloaded_path)}"
                        )
                        try:
                            self._compress_video(downloaded_path)
                        except Exception as exc:
                            self.log_message.emit(
                                f"Kompresi gagal ({exc}). File unduhan asli tetap tersedia."
                            )
                            if self._cancel_requested:
                                success = False
                                break
                else:
                    self.log_message.emit("Preset Original dipilih; tidak ada kompresi.")
            elif info:
                self.log_message.emit("Unduhan selesai, tetapi file hasil tidak ditemukan.")
            else:
                self.log_message.emit("Gagal mendapatkan informasi media.")
        except yt_dlp.utils.DownloadCancelled as exc:
            self.log_message.emit(f"Unduhan dibatalkan: {exc}")
        except yt_dlp.utils.DownloadError as exc:
            self.log_message.emit(f"Unduhan gagal: {exc}")
        except Exception as exc:
            self.log_message.emit(f"Error {type(exc).__name__}: {exc}")

        self.finished_signal.emit(success, info or {})

    def cancel(self):
        self._cancel_requested = True
        if self._ffmpeg_process and self._ffmpeg_process.poll() is None:
            self._ffmpeg_process.terminate()

class ClipCraftDownloadWorker(QThread):
    progress_changed = Signal(float, str, str, str)  # percent, speed, eta, status
    log_message = Signal(str)
    finished_signal = Signal(bool, str)              # success, output_path

    def __init__(
        self,
        url: str,
        tmp_dir: str,
        cookies_from_browser: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.url = url
        self.tmp_dir = os.path.abspath(tmp_dir)
        self.cookies_from_browser = cookies_from_browser
        self._cancel_requested = False

    def _cleanup_old(self):
        for path in glob.glob(os.path.join(self.tmp_dir, "clipcraft_tmp_cut.*")):
            if os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError as exc:
                    self.log_message.emit(f"Gagal hapus file lama {path}: {exc}")

    def progress_hook(self, d):
        if self._cancel_requested:
            raise yt_dlp.utils.DownloadCancelled("Dibatalkan oleh pengguna")
        if d["status"] == "downloading":
            percent_str = d.get("_percent_str", "0%").strip()
            try:
                percent_val = float(percent_str.replace("%", "").strip())
            except ValueError:
                percent_val = 0.0
            self.progress_changed.emit(
                percent_val,
                d.get("_speed_str", "N/A").strip(),
                d.get("_eta_str", "N/A").strip(),
                "Mengunduh...",
            )
        elif d["status"] == "finished":
            self.progress_changed.emit(100.0, "-", "-", "Selesai")

    def _resolve_output_path(self, info) -> str:
        if isinstance(info, dict):
            candidates = [info.get("filepath"), info.get("_filename")]
            for item in info.get("requested_downloads") or []:
                candidates.extend([item.get("filepath"), item.get("_filename")])
            for cand in candidates:
                if cand and os.path.isfile(cand):
                    return os.path.abspath(cand)

        # fallback: cari di folder tmp
        candidates = [
            p for p in glob.glob(os.path.join(self.tmp_dir, "clipcraft_tmp_cut.*"))
            if not p.endswith((".part", ".ytdl", ".temp"))
        ]
        if candidates:
            return os.path.abspath(max(candidates, key=os.path.getmtime))
        return ""

    def run(self):
        os.makedirs(self.tmp_dir, exist_ok=True)
        self._cleanup_old()

        ydl_opts = {
            "format": "bv*+ba/b",
            "outtmpl": os.path.join(self.tmp_dir, "clipcraft_tmp_cut.%(ext)s"),
            "noplaylist": True,
            "progress_hooks": [self.progress_hook],
            "continuedl": True,
            "overwrites": True,
            "ignoreerrors": False,
            "writethumbnail": False,
            "addmetadata": False,
            "verbose": False,
        }

        if self.cookies_from_browser:
            ydl_opts["cookiesfrombrowser"] = (
                self.cookies_from_browser, None, None, None
            )
            self.log_message.emit(f"Menggunakan cookie dari browser: {self.cookies_from_browser}")

        success = False
        final_path = ""
        try:
            self.log_message.emit(f"Memproses URL: {self.url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)

            final_path = self._resolve_output_path(info)
            success = bool(final_path)
            if success:
                self.log_message.emit(f"Tersimpan: {final_path}")
            else:
                self.log_message.emit("File hasil tidak ditemukan di folder tmp.")
        except yt_dlp.utils.DownloadCancelled as exc:
            self.log_message.emit(f"Unduhan dibatalkan: {exc}")
        except yt_dlp.utils.DownloadError as exc:
            self.log_message.emit(f"Unduhan gagal: {exc}")
        except Exception as exc:
            self.log_message.emit(f"Error {type(exc).__name__}: {exc}")

        self.finished_signal.emit(success, final_path)

    def cancel(self):
        self._cancel_requested = True

# ============================================================
# Kompres file lokal
# ============================================================

def _sanitize_stem(name: str, max_len: int = _MAX_STEM_LEN) -> str:
    name = _ILLEGAL_CHARS.sub("", name)
    name = _MULTI_SPACE.sub(" ", name).strip().strip(".")
    encoded = name.encode("utf-8")
    if len(encoded) > max_len:
        name = encoded[:max_len].decode("utf-8", errors="ignore").rstrip()
    return name or "video"


class CompressWorker(QThread):
    progress_changed = Signal(float, str, str, str)
    log_message = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, input_path: str, output_dir: str,
                 compression_preset: str = "Balanced", parent=None):
        super().__init__(parent)
        self.input_path = input_path
        self.output_dir = output_dir
        self.compression_preset = compression_preset
        self._cancel_requested = False
        self._ffmpeg_process = None

    def _probe(self):
        return probe_media(self.input_path)

    def _build_output_paths(self, output_ext: str):
        raw_stem = os.path.splitext(os.path.basename(self.input_path))[0]
        reserve = len(f" [{self.compression_preset}] (99)") + len(output_ext) + 8
        max_stem = max(20, _MAX_STEM_LEN - reserve)
        safe_stem = _sanitize_stem(raw_stem, max_stem)

        output_path = os.path.join(
            self.output_dir,
            f"{safe_stem} [{self.compression_preset}]{output_ext}",
        )
        if os.path.exists(output_path):
            counter = 2
            stem, ext = os.path.splitext(output_path)
            while os.path.exists(f"{stem} ({counter}){ext}"):
                counter += 1
            output_path = f"{stem} ({counter}){ext}"

        temp_path = os.path.join(
            self.output_dir, f"cc_tmp_{uuid.uuid4().hex}{output_ext}"
        )
        return output_path, temp_path

    def run(self):
        os.makedirs(self.output_dir, exist_ok=True)
        settings = COMPRESSION_PRESETS.get(self.compression_preset)
        if settings is None:
            self.finished_signal.emit(False, "Preset 'Original' tidak melakukan kompresi.")
            return

        temp_path = None
        try:
            ffmpeg = get_ffmpeg()
            scale, crf = settings
            duration, audio_codec, has_video = self._probe()
            if not has_video:
                self.finished_signal.emit(False, "File tidak memiliki stream video.")
                return

            mp4_audio_codecs = {"aac", "mp3", "ac3", "eac3", "alac"}
            output_ext = ".mp4" if audio_codec is None or audio_codec in mp4_audio_codecs else ".mkv"

            output_path, temp_path = self._build_output_paths(output_ext)

            self.log_message.emit(f"Output: {os.path.basename(output_path)}")

            vf = f"scale=trunc(iw*{scale}/2)*2:trunc(ih*{scale}/2)*2"
            command = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-i", self.input_path,
                "-map", "0:v:0", "-map", "0:a?",
                "-map_metadata", "0", "-map_chapters", "0",
                "-vf", vf,
                "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
                "-c:a", "copy",
            ]
            if output_ext == ".mp4":
                command += ["-movflags", "+faststart"]
            command += ["-progress", "pipe:1", "-nostats", temp_path]

            self.log_message.emit(
                f"Kompresi {self.compression_preset}: skala {int(scale*100)}%, CRF {crf}; "
                f"audio {audio_codec or 'tidak ada'} (copy)."
            )
            self.progress_changed.emit(0.0, "-", "-", "Mengompres video...")

            try:
                self._ffmpeg_process = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, bufsize=1,
                )
                for line in self._ffmpeg_process.stdout:
                    if self._cancel_requested:
                        self._ffmpeg_process.terminate()
                        raise RuntimeError("Kompresi dibatalkan.")
                    line = line.strip()
                    if line.startswith("out_time_ms=") and duration > 0:
                        try:
                            elapsed = int(line.split("=", 1)[1]) / 1_000_000
                            pct = min(99.0, max(0.0, elapsed / duration * 100))
                            self.progress_changed.emit(pct, "-", "-", "Mengompres video...")
                        except ValueError:
                            pass

                rc = self._ffmpeg_process.wait()
                stderr = self._ffmpeg_process.stderr.read() if self._ffmpeg_process.stderr else ""
                if rc != 0:
                    raise RuntimeError(f"FFmpeg gagal: {stderr[-1200:]}")
                if not os.path.isfile(temp_path) or os.path.getsize(temp_path) == 0:
                    raise RuntimeError("FFmpeg tidak menghasilkan file output.")

                os.replace(temp_path, output_path)
                temp_path = None
                self.progress_changed.emit(100.0, "-", "-", "Kompresi selesai")
                orig = os.path.getsize(self.input_path)
                new = os.path.getsize(output_path)
                if orig:
                    reduction = (1 - new / orig) * 100
                    self.log_message.emit(
                        f"Hasil: {output_path} ({new/1024/1024:.2f} MB; {reduction:+.1f}%)"
                    )
                self.finished_signal.emit(True, output_path)
            finally:
                self._ffmpeg_process = None
        except Exception as exc:
            self.log_message.emit(f"Error: {exc}")
            self.finished_signal.emit(False, str(exc))
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def cancel(self):
        self._cancel_requested = True
        if self._ffmpeg_process and self._ffmpeg_process.poll() is None:
            self._ffmpeg_process.terminate()


# ============================================================
# Cutter: potong klip dari file lokal
# ============================================================
class CutterWorker(QThread):
    progress_changed = Signal(float, str, str, str)
    log_message = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(
        self,
        input_path: str,
        output_dir: str,
        start_sec: float,
        end_sec: float,
        reencode: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.input_path = input_path
        self.output_dir = output_dir
        self.start_sec = max(0.0, float(start_sec))
        self.end_sec = float(end_sec)
        self.reencode = reencode
        self._cancel_requested = False
        self._ffmpeg_process = None

    def _build_output_paths(self, output_ext: str):
        raw_stem = os.path.splitext(os.path.basename(self.input_path))[0]
        reserve = len(" [cut 9999-9999] (99)") + len(output_ext) + 8
        max_stem = max(20, _MAX_STEM_LEN - reserve)
        safe_stem = _sanitize_stem(raw_stem, max_stem)

        s = int(self.start_sec)
        e = int(self.end_sec)
        tag = f" [cut {s}-{e}]"
        output_path = os.path.join(self.output_dir, f"{safe_stem}{tag}{output_ext}")
        if os.path.exists(output_path):
            counter = 2
            stem, ext = os.path.splitext(output_path)
            while os.path.exists(f"{stem} ({counter}){ext}"):
                counter += 1
            output_path = f"{stem} ({counter}){ext}"

        temp_path = os.path.join(self.output_dir, f"cc_tmp_{uuid.uuid4().hex}{output_ext}")
        return output_path, temp_path

    def run(self):
        os.makedirs(self.output_dir, exist_ok=True)
        temp_path = None
        try:
            if self.end_sec <= self.start_sec:
                raise RuntimeError("Waktu akhir harus lebih besar dari waktu mulai.")

            ffmpeg = get_ffmpeg()
            duration, _, has_video = probe_media(self.input_path)
            if not has_video:
                raise RuntimeError("File tidak memiliki stream video.")
            if self.start_sec >= duration:
                raise RuntimeError(
                    f"Waktu mulai ({self.start_sec:.1f}s) melebihi durasi file ({duration:.1f}s)."
                )
            end = min(self.end_sec, duration)
            clip_len = max(0.1, end - self.start_sec)

            output_ext = ".mp4"
            output_path, temp_path = self._build_output_paths(output_ext)

            if self.reencode:
                command = [
                    ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                    "-i", self.input_path,
                    "-ss", f"{self.start_sec:.3f}",
                    "-t", f"{clip_len:.3f}",
                    "-map", "0:v:0", "-map", "0:a?",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart",
                    "-progress", "pipe:1", "-nostats", temp_path,
                ]
                self.log_message.emit(f"Cut (re-encode) {self.start_sec:.2f}s → {end:.2f}s")
            else:
                command = [
                    ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", f"{self.start_sec:.3f}",
                    "-i", self.input_path,
                    "-t", f"{clip_len:.3f}",
                    "-map", "0", "-c", "copy",
                    "-avoid_negative_ts", "make_zero",
                    "-progress", "pipe:1", "-nostats", temp_path,
                ]
                self.log_message.emit(f"Cut (copy) {self.start_sec:.2f}s → {end:.2f}s")

            self.progress_changed.emit(0.0, "-", "-", "Memotong video...")

            try:
                self._ffmpeg_process = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, bufsize=1,
                )
                for line in self._ffmpeg_process.stdout:
                    if self._cancel_requested:
                        self._ffmpeg_process.terminate()
                        raise RuntimeError("Pemotongan dibatalkan.")
                    line = line.strip()
                    if line.startswith("out_time_ms=") and clip_len > 0:
                        try:
                            elapsed = int(line.split("=", 1)[1]) / 1_000_000
                            pct = min(99.0, max(0.0, elapsed / clip_len * 100))
                            self.progress_changed.emit(pct, "-", "-", "Memotong video...")
                        except ValueError:
                            pass

                rc = self._ffmpeg_process.wait()
                stderr = self._ffmpeg_process.stderr.read() if self._ffmpeg_process.stderr else ""
                if rc != 0:
                    raise RuntimeError(f"FFmpeg gagal: {stderr[-1200:]}")
                if not os.path.isfile(temp_path) or os.path.getsize(temp_path) == 0:
                    raise RuntimeError("FFmpeg tidak menghasilkan file output.")

                os.replace(temp_path, output_path)
                temp_path = None
                self.progress_changed.emit(100.0, "-", "-", "Pemotongan selesai")
                self.log_message.emit(f"Hasil: {output_path}")
                self.finished_signal.emit(True, output_path)
            finally:
                self._ffmpeg_process = None
        except Exception as exc:
            self.log_message.emit(f"Error: {exc}")
            self.finished_signal.emit(False, str(exc))
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def cancel(self):
        self._cancel_requested = True
        if self._ffmpeg_process and self._ffmpeg_process.poll() is None:
            self._ffmpeg_process.terminate()


# ============================================================
# Burn-in teks: cut + gambar teks ke setiap frame, pipe ke FFmpeg
# ============================================================
class TextBurnInWorker(QThread):
    progress_changed = Signal(float, str, str, str)
    log_message = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(
        self,
        input_path: str,
        output_dir: str,
        start_sec: float,
        end_sec: float,
        texts_as_dict: list[dict],
        parent=None,
    ):
        super().__init__(parent)
        self.input_path = input_path
        self.output_dir = output_dir
        self.start_sec = max(0.0, float(start_sec))
        self.end_sec = float(end_sec)
        self.texts_as_dict = list(texts_as_dict or [])
        self._cancel_requested = False
        self._decode_proc = None
        self._encode_proc = None

    def _build_output_paths(self, output_ext: str):
        raw_stem = os.path.splitext(os.path.basename(self.input_path))[0]
        reserve = len(" [cut 9999-9999] (99)") + len(output_ext) + 8
        max_stem = max(20, _MAX_STEM_LEN - reserve)
        safe_stem = _sanitize_stem(raw_stem, max_stem)

        s = int(self.start_sec)
        e = int(self.end_sec)
        tag = f" [cut {s}-{e}]"
        output_path = os.path.join(self.output_dir, f"{safe_stem}{tag}{output_ext}")
        if os.path.exists(output_path):
            counter = 2
            stem, ext = os.path.splitext(output_path)
            while os.path.exists(f"{stem} ({counter}){ext}"):
                counter += 1
            output_path = f"{stem} ({counter}){ext}"

        temp_path = os.path.join(self.output_dir, f"cc_tmp_{uuid.uuid4().hex}{output_ext}")
        return output_path, temp_path

    def run(self):
        os.makedirs(self.output_dir, exist_ok=True)
        temp_path = None
        try:
            from ui.widgets.text_item import TextItem
            from ui.widgets.text_renderer import draw_texts
            from PySide6.QtGui import QImage, QPainter
            from PySide6.QtCore import QRect

            if self.end_sec <= self.start_sec:
                raise RuntimeError("Waktu akhir harus lebih besar dari waktu mulai.")

            info = probe_stream_info(self.input_path)
            if not info.get("has_video"):
                raise RuntimeError("File tidak memiliki stream video.")
            width = int(info.get("width") or 0)
            height = int(info.get("height") or 0)
            fps = float(info.get("fps") or 30.0)
            duration = float(info.get("duration") or 0.0)
            if width <= 0 or height <= 0:
                raise RuntimeError("Tidak bisa membaca resolusi video sumber.")
            if fps <= 0:
                fps = 30.0
            if self.start_sec >= duration:
                raise RuntimeError(
                    f"Waktu mulai ({self.start_sec:.1f}s) melebihi durasi file ({duration:.1f}s)."
                )

            end = min(self.end_sec, duration)
            clip_len = max(0.1, end - self.start_sec)

            texts = [TextItem.from_dict(d) for d in self.texts_as_dict]
            for t in texts:
                t.start_sec = max(0.0, t.start_sec - self.start_sec)
                t.end_sec = max(0.0, t.end_sec - self.start_sec)

            ffmpeg = get_ffmpeg()
            output_path, temp_path = self._build_output_paths(".mp4")

            frame_bytes = width * height * 3
            frame_size_arg = f"{width}x{height}"

            decode_cmd = [
                ffmpeg, "-hide_banner", "-loglevel", "error",
                "-ss", f"{self.start_sec:.3f}",
                "-t", f"{clip_len:.3f}",
                "-i", self.input_path,
                "-an",
                "-vf", "format=rgb24",
                "-f", "rawvideo", "-pix_fmt", "rgb24",
                "-s", frame_size_arg, "-r", f"{fps:.6f}",
                "-",
            ]
            encode_cmd = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "rawvideo", "-pix_fmt", "rgb24",
                "-s", frame_size_arg, "-r", f"{fps:.6f}",
                "-i", "-",
                "-ss", f"{self.start_sec:.3f}",
                "-t", f"{clip_len:.3f}",
                "-i", self.input_path,
                "-map", "0:v:0", "-map", "1:a?",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-colorspace", "bt709",
                "-color_primaries", "bt709",
                "-color_trc", "bt709",
                "-color_range", "tv",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                "-progress", "pipe:1", "-nostats",
                temp_path,
            ]

            self.log_message.emit(
                f"Burn-in teks {len(texts)} item; "
                f"{frame_size_arg} @ {fps:.3f} fps; "
                f"{self.start_sec:.2f}s → {end:.2f}s"
            )
            self.progress_changed.emit(0.0, "-", "-", "Memproses frame + teks...")

            self._decode_proc = subprocess.Popen(
                decode_cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            self._encode_proc = subprocess.Popen(
                encode_cmd,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, bufsize=0,
            )

            frame_index = 0
            total_frames = max(1, int(round(clip_len * fps)))

            def _drain_progress():
                if not self._encode_proc or not self._encode_proc.stdout:
                    return
                import select
                fd = self._encode_proc.stdout.fileno()
                ready, _, _ = select.select([fd], [], [], 0)
                if not ready:
                    return
                line = self._encode_proc.stdout.readline()
                if not line:
                    return
                line = line.decode(errors="ignore").strip()
                if line.startswith("out_time_ms=") and clip_len > 0:
                    try:
                        elapsed = int(line.split("=", 1)[1]) / 1_000_000
                        pct = min(99.0, max(0.0, elapsed / clip_len * 100))
                        self.progress_changed.emit(
                            pct, "-", "-", "Memproses frame + teks..."
                        )
                    except ValueError:
                        pass

            while True:
                if self._cancel_requested:
                    raise RuntimeError("Pemrosesan dibatalkan.")

                raw = self._decode_proc.stdout.read(frame_bytes)
                if not raw or len(raw) < frame_bytes:
                    break

                t = frame_index / fps

                # frame sumber: RGB888, stride width*3 (tight dari rawvideo)
                src_image = QImage(
                    raw, width, height, width * 3,
                    QImage.Format.Format_RGB888,
                )

                # kanvas output dijamin RGB888 tanpa padding
                out_image = QImage(width, height, QImage.Format.Format_RGB888)
                out_image.fill(0)

                p = QPainter(out_image)
                p.drawImage(0, 0, src_image)
                draw_texts(p, QRect(0, 0, width, height), texts, t)
                p.end()

                data = out_image.constBits().tobytes()
                expected = width * height * 3
                if len(data) != expected:
                    bpl = out_image.bytesPerLine()
                    mv = memoryview(data)
                    rows = []
                    for y in range(height):
                        off = y * bpl
                        rows.append(mv[off:off + width * 3])
                    data = b"".join(rows)

                if frame_index == 0:
                    self.log_message.emit(
                        f"[burnin] fmt={out_image.format()} "
                        f"bpl={out_image.bytesPerLine()} "
                        f"expected_bpl={width * 3} "
                        f"datalen={len(data)} expected_len={expected}"
                    )

                self._encode_proc.stdin.write(data)
                self._encode_proc.stdin.flush()

                frame_index += 1
                if frame_index % 5 == 0 or frame_index == total_frames:
                    _drain_progress()
                    if total_frames > 0:
                        pct = min(99.0, frame_index / total_frames * 100)
                        self.progress_changed.emit(
                            pct, "-", "-", "Memproses frame + teks..."
                        )

            try:
                self._encode_proc.stdin.close()
            except Exception:
                pass

            try:
                self._decode_proc.wait(timeout=30)
            except Exception:
                pass

            if self._encode_proc.stdout:
                for line in self._encode_proc.stdout:
                    line = line.decode(errors="ignore").strip()
                    if line.startswith("out_time_ms=") and clip_len > 0:
                        try:
                            elapsed = int(line.split("=", 1)[1]) / 1_000_000
                            pct = min(99.0, max(0.0, elapsed / clip_len * 100))
                            self.progress_changed.emit(
                                pct, "-", "-", "Memproses frame + teks..."
                            )
                        except ValueError:
                            pass

            rc = self._encode_proc.wait()
            stderr = (
                self._encode_proc.stderr.read()
                if self._encode_proc.stderr else b""
            )
            if rc != 0:
                raise RuntimeError(
                    f"FFmpeg encode gagal: {stderr.decode(errors='ignore')[-1200:]}"
                )
            if not os.path.isfile(temp_path) or os.path.getsize(temp_path) == 0:
                raise RuntimeError("FFmpeg tidak menghasilkan file output.")

            os.replace(temp_path, output_path)
            temp_path = None
            self.progress_changed.emit(100.0, "-", "-", "Burn-in selesai")
            self.log_message.emit(f"Hasil: {output_path}")
            self.finished_signal.emit(True, output_path)
        except Exception as exc:
            self.log_message.emit(f"Error: {exc}")
            self.finished_signal.emit(False, str(exc))
        finally:
            for proc in (self._decode_proc, self._encode_proc):
                if proc and proc.poll() is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
            self._decode_proc = None
            self._encode_proc = None
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def cancel(self):
        self._cancel_requested = True
        for proc in (self._decode_proc, self._encode_proc):
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass


# ============================================================
# Thumbnail strip untuk cutter
# ============================================================
class ThumbnailWorker(QThread):
    thumbnail_ready = Signal(int, QImage)
    finished_signal = Signal(bool, str)

    def __init__(
        self,
        input_path: str,
        duration: float,
        count: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.input_path = input_path
        self.duration = float(duration)
        self.count = count
        self._cancel_requested = False

    def run(self):
        from core import thumbnails

        times = thumbnails.plan_thumbnail_times(self.duration, self.count)
        if not times:
            self.finished_signal.emit(False, "Durasi tidak valid.")
            return

        cache_dir = thumbnails.cache_dir_for(self.input_path)
        total = len(times)
        ok_count = 0

        for i, t in enumerate(times):
            if self._cancel_requested:
                self.finished_signal.emit(False, "Dibatalkan.")
                return

            out = thumbnails.thumbnail_path(cache_dir, i)
            success = thumbnails.extract_one(self.input_path, t, out)
            if not success:
                continue

            image = QImage(out)
            if not image.isNull():
                self.thumbnail_ready.emit(i, image)
                ok_count += 1

        self.finished_signal.emit(True, f"{ok_count}/{total} thumbnail siap.")

    def cancel(self):
        self._cancel_requested = True