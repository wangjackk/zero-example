"""print_heart -- 弹出无边框透明桃心动画(PySide6).

结构:
- ``gui/``    GUI 子包:窗口/几何/粒子/色彩/应用生命周期
- ``anim.py`` 子进程入口(薄壳)
- 本模块 ``PrintHeart`` routine,负责启动/清理子进程

职责分工:
- ``run``:拉起子进程,等它跑完
- ``stop``:terminate -> 等 1s -> 必要时 kill,避免新动作到来时子进程孤儿化

Windows 下优先用 ``pythonw.exe`` 启动,避免 GUI 子进程带出一个黑色控制台窗.
"""

import asyncio
import importlib.util
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar, Dict, Optional

from pydantic import BaseModel, Field

from routine import Modules, Routine

_SCRIPT_PATH = Path(__file__).with_name('anim.py')
_TERMINATE_GRACE = 1.0


class PrintHeartInput(BaseModel):
    duration: float = Field(default=5.0, description='动画持续秒数')


def _gui_python() -> str:
    """Windows 下尽量换成 pythonw.exe,避免子进程弹黑色控制台."""
    if platform.system() != 'Windows':
        return sys.executable
    candidate = Path(sys.executable).with_name('pythonw.exe')
    return str(candidate) if candidate.exists() else sys.executable


class PrintHeart(Routine):
    """弹出一个无边框透明桃心动画窗口."""

    meta: ClassVar[Dict[str, Any]] = {
        'description': '弹出一个无边框透明桃心动画窗口, 持续指定秒数.',
        'input_schema': PrintHeartInput.model_json_schema(),
    }

    def __init__(self):
        super().__init__()
        self._proc: Optional[asyncio.subprocess.Process] = None

    async def on_created(self, rid: Optional[str] = None,
                         kwargs: Optional[Dict[str, Any]] = None) -> Optional[Modules]:
        # 纯 UI routine,不占任何模块
        return None

    async def run(self, kwargs: Dict[str, Any]):
        duration = kwargs.get('duration', 5.0)
        self._logger.info(f'print_heart {self.id}: 弹出桃心动画,持续 {duration}s ...')

        if importlib.util.find_spec('PySide6') is None:
            # 子进程跟本解释器同源,这边没有 PySide6 子进程一启动就 import 崩.
            # 提前报清晰错误,而不是让 subprocess 静默退出.
            raise RuntimeError(
                'print_heart 需要 PySide6(动画 GUI 依赖),当前解释器未安装:'
                f' {sys.executable}  -- pip install PySide6'
            )

        popen_kwargs: Dict[str, Any] = {}
        if platform.system() == 'Windows':
            popen_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

        self._proc = await asyncio.create_subprocess_exec(
            _gui_python(), str(_SCRIPT_PATH), str(duration), **popen_kwargs
        )
        await self._proc.wait()

        self._logger.info(f'print_heart {self.id}: 完成')

    async def stop(self) -> None:
        self._logger.info(f'print_heart {self.id}: stopping')
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        self._logger.info('print_heart: stop -> terminate subprocess')
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=_TERMINATE_GRACE)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
