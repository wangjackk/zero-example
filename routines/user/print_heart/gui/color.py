"""色彩小工具 ---- 把 HSV 参数方便地转成 QColor."""

from PySide6.QtGui import QColor


def hsv(h: float, s: float = 1.0, v: float = 1.0, a: float = 1.0) -> QColor:
    """h 取 0~360(自动对 360 取模),s/v/a 取 0~1."""
    return QColor.fromHsvF(
        max(0.0, min(0.9999, (h % 360) / 360.0)),
        max(0.0, min(1.0, s)),
        max(0.0, min(1.0, v)),
        max(0.0, min(1.0, a)),
    )
