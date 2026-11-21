from __future__ import annotations

from dataclasses import dataclass, asdict, replace


@dataclass
class TextItem:
    id: int = -1
    text: str = "Teks baru"
    start_sec: float = 0.0
    end_sec: float = 3.0
    x_ratio: float = 0.5
    y_ratio: float = 0.9
    font_size: int = 48
    color: str = "#000000"

    # background (gaya highlight WhatsApp)
    bg_enabled: bool = True
    bg_color: str = "#FFFFFF"
    bg_opacity: float = 0.5

    def duration(self) -> float:
        return max(0.0, self.end_sec - self.start_sec)

    def clamp(self, total_duration: float, min_dur: float = 0.3) -> "TextItem":
        total = max(0.0, float(total_duration))
        start = max(0.0, min(float(self.start_sec), total))
        end = max(0.0, min(float(self.end_sec), total))
        if end - start < min_dur:
            end = min(total, start + min_dur)
            if end - start < min_dur:
                start = max(0.0, end - min_dur)
        self.start_sec, self.end_sec = start, end
        self.x_ratio = max(0.0, min(1.0, float(self.x_ratio)))
        self.y_ratio = max(0.0, min(1.0, float(self.y_ratio)))
        self.font_size = max(8, int(self.font_size))
        self.bg_opacity = max(0.0, min(1.0, float(self.bg_opacity)))
        return self

    def copy(self, **changes) -> "TextItem":
        return replace(self, **changes)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TextItem":
        return cls(
            id=int(data.get("id", -1)),
            text=str(data.get("text", "")),
            start_sec=float(data.get("start_sec", 0.0)),
            end_sec=float(data.get("end_sec", 0.0)),
            x_ratio=float(data.get("x_ratio", 0.5)),
            y_ratio=float(data.get("y_ratio", 0.5)),
            font_size=int(data.get("font_size", 48)),
            color=str(data.get("color", "#FFFFFF")),
            bg_enabled=bool(data.get("bg_enabled", False)),
            bg_color=str(data.get("bg_color", "#000000")),
            bg_opacity=float(data.get("bg_opacity", 0.5)),
        )