"""无边框 + 真透明主窗口 ---- PySide6 实现的心形动画主体.

关键效果:
- ``FramelessWindowHint + WA_TranslucentBackground``:真 alpha 不规则窗口,
  边缘羽化平滑(靠 QPainter 反走样).
- 多层同心心形由外到内,外层大而暗(辉光),内层小而亮(高光),
  中间主体用 ``QRadialGradient`` 做径向光照,视觉上是个发光的桃心.
- 心呼吸脉动(约 0.6Hz),色相随时间循环.
- 粒子从心口向上飞散,带重力拖尾,色相偏桃红并随时间漂移.
- 交互:左键拖动,双击/ESC 退出.
"""

import math
import time

from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QBrush, QPainter, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget


def _quit_app() -> None:
    """显式退出 QApplication ---- Qt.Tool 窗口不算主窗口,关闭时不会触发
    ``quitOnLastWindowClosed``,必须手动喊停,否则子进程会挂着不退."""
    app = QApplication.instance()
    if app is not None:
        app.quit()

from gui.color import hsv
from gui.heart import heart_bbox_radius, heart_path
from gui.particles import ParticleSystem
from gui.platform_win import polish_frameless


WIN_W, WIN_H = 520, 480
BASE_SCALE = 10.0
PULSE_AMP = 0.07
PULSE_FREQ = 4.5
HUE_RATE = 55.0
PARTICLE_HUE_DRIFT = 80.0
FRAME_INTERVAL_MS = 16


class HeartWindow(QWidget):
    def __init__(self, duration: float):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

        self.resize(WIN_W, WIN_H)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move((screen.width() - WIN_W) // 2, (screen.height() - WIN_H) // 2)

        self._duration = duration
        self._t0 = time.monotonic()
        self._last = self._t0
        self._t = 0.0

        self._cx = WIN_W / 2
        self._cy = WIN_H / 2 - 8

        self._particles = ParticleSystem()
        self._drag_offset: QPointF | None = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(FRAME_INTERVAL_MS)

    def showEvent(self, ev) -> None:
        super().showEvent(ev)
        polish_frameless(int(self.winId()))

    def _tick(self) -> None:
        now = time.monotonic()
        dt = now - self._last
        self._last = now
        self._t = now - self._t0

        if self._t >= self._duration:
            self.close()
            _quit_app()
            return

        pulse = 1 + PULSE_AMP * math.sin(self._t * PULSE_FREQ)
        origin = (self._cx, self._cy - heart_bbox_radius(BASE_SCALE * pulse) * 0.55)
        self._particles.update(dt, origin)
        self.update()

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        t = self._t
        base_hue = t * HUE_RATE
        pulse = 1 + PULSE_AMP * math.sin(t * PULSE_FREQ)

        self._paint_glow(p, base_hue, pulse)
        self._paint_body(p, base_hue, pulse)
        self._paint_highlight(p, base_hue, pulse)
        self._paint_particles(p, t)

        p.end()

    def _paint_glow(self, p: QPainter, base_hue: float, pulse: float) -> None:
        for i, (scale_mul, alpha) in enumerate([
            (1.55, 0.06),
            (1.38, 0.09),
            (1.22, 0.13),
            (1.10, 0.18),
        ]):
            scale = BASE_SCALE * pulse * scale_mul
            color = hsv(base_hue - i * 4, 0.85, 1.0, alpha)
            p.fillPath(heart_path(self._cx, self._cy, scale), color)

    def _paint_body(self, p: QPainter, base_hue: float, pulse: float) -> None:
        scale = BASE_SCALE * pulse
        radius = heart_bbox_radius(scale) * 1.1
        focal = QPointF(self._cx - scale * 1.6, self._cy - scale * 2.6)
        grad = QRadialGradient(focal, radius)
        grad.setColorAt(0.00, hsv(base_hue, 0.20, 1.00, 1.0))
        grad.setColorAt(0.35, hsv(base_hue, 0.90, 1.00, 1.0))
        grad.setColorAt(1.00, hsv(base_hue + 12, 1.00, 0.55, 1.0))
        p.fillPath(heart_path(self._cx, self._cy, scale), QBrush(grad))

    def _paint_highlight(self, p: QPainter, base_hue: float, pulse: float) -> None:
        hx = self._cx - BASE_SCALE * pulse * 2.4
        hy = self._cy - BASE_SCALE * pulse * 3.8
        p.fillPath(
            heart_path(hx, hy, BASE_SCALE * pulse * 0.22),
            hsv(base_hue, 0.15, 1.0, 0.85),
        )

    def _paint_particles(self, p: QPainter, t: float) -> None:
        for part in self._particles.particles:
            frac = part.frac()
            hue = (part.hue + t * PARTICLE_HUE_DRIFT)
            color = hsv(hue, 0.85, 0.7 + 0.3 * frac, frac)
            p.fillPath(heart_path(part.x, part.y, part.scale, samples=64), color)

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self._drag_offset = ev.globalPosition() - QPointF(self.frameGeometry().topLeft())

    def mouseMoveEvent(self, ev) -> None:
        if self._drag_offset is not None and (ev.buttons() & Qt.LeftButton):
            new_pos = ev.globalPosition() - self._drag_offset
            self.move(new_pos.toPoint())

    def mouseReleaseEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self._drag_offset = None

    def mouseDoubleClickEvent(self, _ev) -> None:
        self.close()
        _quit_app()

    def keyPressEvent(self, ev) -> None:
        if ev.key() == Qt.Key_Escape:
            self.close()
            _quit_app()
