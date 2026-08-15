"""WavPlayer 抽象基类.

所有后端 (ffplay / pyaudio / ...) 必须实现同一个最小接口:

- ``is_available()``  后端依赖是否就绪 (工厂用它挑实现)
- ``play(path, duration)``  阻塞式播放,直到播完 / 到时 / 被 stop() 打断
- ``stop()``  立即终止当前播放,重复调用安全

语义对齐:
- ``play()`` 正常播完 → 返回 None
- ``play()`` 被 ``stop()`` 打断 → 也视作正常返回 (不 raise)
- 后端本身出错 (ffplay 异常退出 / pyaudio open 失败) → raise
"""

from abc import ABC, abstractmethod
from logging import Logger
from pathlib import Path
from typing import Optional


class WavPlayer(ABC):
    """WAV 播放器统一抽象.一个实例 = 一个播放 session."""

    def __init__(self, logger: Logger):
        self._logger = logger

    @staticmethod
    @abstractmethod
    def is_available() -> bool:
        """检测该后端依赖 (可执行文件 / Python 包) 是否就绪."""

    @abstractmethod
    async def play(self, file_path: Path, duration: Optional[float] = None) -> None:
        """阻塞式播放 ``file_path``.

        duration: None 播到文件末尾; > 0 播到指定秒数
        """

    @abstractmethod
    async def stop(self) -> None:
        """立即停止当前播放.无正在播放时应静默返回."""
