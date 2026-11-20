from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter

from .text_item import TextItem

_BG_PADDING = 8   # px relatif (ikut skala font)
_BG_PAD_X = 32   # kiri-kanan
_BG_PAD_Y = 6    # atas-bawah
_BG_RADIUS = 16


def draw_texts(
    painter: QPainter,
    target_rect: QRect,
    texts: list[TextItem],
    playhead_sec: float,
):
    """Gambar semua teks aktif (start <= playhead <= end) ke painter."""
    if target_rect.height() <= 0 or target_rect.width() <= 0:
        return
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    for it in texts:
        if not (it.start_sec <= playhead_sec <= it.end_sec):
            continue
        _draw_one(painter, target_rect, it)


def _draw_one(painter: QPainter, target: QRect, item: TextItem):
    scale = target.height() / 720.0
    px = max(8, int(item.font_size * scale))
    font = QFont("Segoe UI", -1)
    font.setPixelSize(px)
    font.setBold(True)
    painter.setFont(font)

    text = item.text or ""
    if not text:
        return

    fm = painter.fontMetrics()
    tw = fm.horizontalAdvance(text)
    th = fm.height()

    cx = target.left() + int(item.x_ratio * target.width())
    cy = target.top() + int(item.y_ratio * target.height())
    rect = QRect(cx - tw // 2, cy - th // 2, tw, th)

    # ---------- background (varian A: highlight mengikuti teks) ----------
    if item.bg_enabled:
        bg = QColor(item.bg_color)
        bg.setAlphaF(max(0.0, min(1.0, item.bg_opacity)))
        pad_x = max(2, int(_BG_PAD_X * scale))
        pad_y = max(1, int(_BG_PAD_Y * scale))
        radius = max(0, int(_BG_RADIUS * scale))
        bg_rect = rect.adjusted(-pad_x, -pad_y, pad_x, pad_y)
        painter.setBrush(bg)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(bg_rect, radius, radius)
        painter.setBrush(Qt.NoBrush)

    # ---------- teks (dengan bayangan tipis) ----------
    painter.setPen(QColor(0, 0, 0, 160))
    painter.drawText(rect.translated(2, 2), Qt.AlignCenter, text)
    painter.setPen(QColor(item.color))
    painter.drawText(rect, Qt.AlignCenter, text)