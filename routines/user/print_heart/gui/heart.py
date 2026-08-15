"""心脏曲线几何 ---- 经典参数方程:

    x(t) = 16 sin³t
    y(t) = 13 cos t - 5 cos 2t - 2 cos 3t - cos 4t

返回 ``QPainterPath`` 供 QPainter.fillPath 直接使用.
"""

import math

from PySide6.QtGui import QPainterPath


def heart_path(cx: float, cy: float, scale: float, samples: int = 240) -> QPainterPath:
    path = QPainterPath()
    for i in range(samples + 1):
        t = i * 2 * math.pi / samples
        sin_t = math.sin(t)
        x = 16 * sin_t * sin_t * sin_t
        y = (13 * math.cos(t)
             - 5 * math.cos(2 * t)
             - 2 * math.cos(3 * t)
             - math.cos(4 * t))
        px = cx + x * scale
        py = cy - y * scale
        if i == 0:
            path.moveTo(px, py)
        else:
            path.lineTo(px, py)
    path.closeSubpath()
    return path


def heart_bbox_radius(scale: float) -> float:
    """估算心形外接圆半径,供辉光半径参考."""
    return 17.0 * scale
