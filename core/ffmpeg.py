import json
import os
import shutil
import subprocess

from core.config import load_config


def _resolve_tool(key: str, name: str) -> str:
    cfg = load_config()
    custom = (cfg.get("paths", {}) or {}).get(key, "") or ""
    if custom and os.path.isfile(custom):
        return custom
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"{name} tidak ditemukan. Set path di Settings atau pasang {name}.")
    return path


def get_ffmpeg() -> str:
    return _resolve_tool("ffmpeg_path", "ffmpeg")


def get_ffprobe() -> str:
    return _resolve_tool("ffprobe_path", "ffprobe")


def get_node() -> str | None:
    cfg = load_config()
    custom = (cfg.get("paths", {}) or {}).get("node_path", "") or ""
    if custom and os.path.isfile(custom):
        return custom
    return shutil.which("node")


def probe_media(path: str):
    result = subprocess.run(
        [
            get_ffprobe(), "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,codec_name",
            "-of", "json", path,
        ],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout or "{}")
    duration = float((data.get("format") or {}).get("duration") or 0)
    streams = data.get("streams") or []
    audio_codec = next(
        (s.get("codec_name") for s in streams if s.get("codec_type") == "audio"),
        None,
    )
    has_video = any(s.get("codec_type") == "video" for s in streams)
    return duration, audio_codec, has_video


def probe_stream_info(path: str) -> dict:
    """
    Informasi lengkap untuk burn-in teks:
    width, height, fps, duration, audio_codec, has_video, has_audio.
    """
    result = subprocess.run(
        [
            get_ffprobe(), "-v", "error",
            "-show_entries",
            "format=duration:"
            "stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate",
            "-of", "json", path,
        ],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout or "{}")
    duration = float((data.get("format") or {}).get("duration") or 0)

    width = height = 0
    fps = 0.0
    audio_codec = None
    has_video = False
    has_audio = False

    for s in data.get("streams") or []:
        if s.get("codec_type") == "video" and not has_video:
            has_video = True
            width = int(s.get("width") or 0)
            height = int(s.get("height") or 0)
            fps = _parse_fraction(s.get("avg_frame_rate")) or _parse_fraction(
                s.get("r_frame_rate")
            )
        elif s.get("codec_type") == "audio" and not has_audio:
            has_audio = True
            audio_codec = s.get("codec_name")

    return {
        "width": width,
        "height": height,
        "fps": fps if fps > 0 else 30.0,
        "duration": duration,
        "audio_codec": audio_codec,
        "has_video": has_video,
        "has_audio": has_audio,
    }


def _parse_fraction(value) -> float:
    if not value:
        return 0.0
    try:
        num, _, den = str(value).partition("/")
        if den:
            n = float(num)
            d = float(den)
            return n / d if d else 0.0
        return float(num)
    except (ValueError, ZeroDivisionError):
        return 0.0


def is_ffmpeg_available() -> bool:
    try:
        get_ffmpeg()
        return True
    except Exception:
        return False


def ffmpeg_version() -> str:
    try:
        result = subprocess.run(
            [get_ffmpeg(), "-version"], capture_output=True, text=True
        )
        return result.stdout.splitlines()[0] if result.stdout else "unknown"
    except Exception as exc:
        return f"tidak tersedia ({exc})"


def probe_codecs(path: str):
    """Return (video_codec, audio_codec)."""
    result = subprocess.run(
        [
            get_ffprobe(), "-v", "error",
            "-show_entries", "stream=codec_type,codec_name",
            "-of", "json", path,
        ],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout or "{}")
    v = a = None
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and v is None:
            v = s.get("codec_name")
        elif s.get("codec_type") == "audio" and a is None:
            a = s.get("codec_name")
    return v, a