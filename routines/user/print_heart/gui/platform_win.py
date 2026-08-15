"""Windows 11 平台细节 ---- 通过 DWM API 关掉系统给无边框透明窗口画的那条
外边框(不关就会看到一个白/灰色的矩形框飘在外面).

只在 Windows 上生效,其他平台调用即 no-op,上游无需分支.
"""

from __future__ import annotations

import ctypes
import platform
from ctypes import wintypes


DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34

DWMWCP_DONOTROUND = 1
DWMWA_COLOR_NONE = 0xFFFFFFFE


def polish_frameless(hwnd: int) -> None:
    """去掉 Win11 给无边框窗口加的外边框 + 圆角.非 Windows 直接返回."""
    if platform.system() != 'Windows' or not hwnd:
        return
    try:
        dwm = ctypes.windll.dwmapi
    except (OSError, AttributeError):
        return

    try:
        corner = ctypes.c_int(DWMWCP_DONOTROUND)
        dwm.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(corner),
            ctypes.sizeof(corner),
        )
    except OSError:
        pass

    try:
        color = ctypes.c_uint(DWMWA_COLOR_NONE)
        dwm.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(DWMWA_BORDER_COLOR),
            ctypes.byref(color),
            ctypes.sizeof(color),
        )
    except OSError:
        pass
