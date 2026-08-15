"""wav_player -- 统一的 WAV 播放抽象 + 后端工厂.

优先级: ffplay > pyaudio.第一次调用 ``create_wav_player()`` 时按顺序
探测每个后端的 ``is_available()``, 挑第一个就绪的实例化.
"""

from logging import Logger
from typing import List, Type

from ._base import WavPlayer
from ._ffplay import FFplayPlayer
from ._pyaudio import PyAudioPlayer


_CANDIDATES: List[Type[WavPlayer]] = [FFplayPlayer, PyAudioPlayer]


def create_wav_player(logger: Logger) -> WavPlayer:
    """按优先级挑第一个可用的后端, 构造 WavPlayer 实例.

    都不可用 → raise RuntimeError (让调用方决定是报错还是降级).
    """
    for cls in _CANDIDATES:
        if cls.is_available():
            logger.info(f'wav_player: using backend {cls.__name__}')
            return cls(logger)
    raise RuntimeError(
        'no available wav player backend: '
        'install ffplay (system) or pyaudio (pip install pyaudio)'
    )


__all__ = ['WavPlayer', 'create_wav_player']
