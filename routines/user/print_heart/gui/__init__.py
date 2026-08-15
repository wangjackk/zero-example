"""print_heart GUI 子包 ---- PySide6 实现的无边框透明心形动画.

模块划分:
- ``color``    : HSV -> QColor 工具
- ``heart``    : 心脏曲线 -> QPainterPath
- ``particles``: 粒子系统(纯逻辑,不碰 Qt 绘制)
- ``window``   : 无边框透明主窗口,负责把以上组件画出来
- ``app``      : QApplication 生命周期
"""
