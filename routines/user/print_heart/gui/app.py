"""QApplication 生命周期 ---- 单独开出来方便测试时复用已有 app 实例."""

import sys

from PySide6.QtWidgets import QApplication

from gui.window import HeartWindow


def run(duration: float) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    win = HeartWindow(duration)
    win.show()
    return app.exec()
