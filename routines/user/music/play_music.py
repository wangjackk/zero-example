"""music - 播放本地音乐文件,body 派生子边放边跑(对标老版).

继承 XmlRoutine:``<music><dance duration="3"/></music>`` 边放音乐边跳舞.
dance done -> body_shell done -> request_stop -> cancel_main_task -> player.play
抛 CancelledError(ffplay 杀进程)-> run 退出.无 body 子时按 duration 自然播完.

占 ``audio`` 模块:多个 PlayMusic 串行.body 子(如 dance)占 ``body``,跟 audio
不冲突,父子并发.
"""
import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from routine import Modules
from zero.modules import MODULE_AUDIO
from ..xml.xml_routine import XmlRoutine
from .wav_player import create_wav_player


_ASSETS_DIR = Path(__file__).parent / 'assets'
_DEFAULT_NAME = 'Found-My-Way'


def _resolve(name: str) -> Path:
    """按 name 在 assets/ 下查找任意扩展名的音频文件."""
    matches = [p for p in _ASSETS_DIR.glob(f'{name}.*') if p.suffix.lower() != '.json']
    if not matches:
        raise FileNotFoundError(f'no asset matching "{name}.*" under {_ASSETS_DIR}')
    return matches[0]


class PlayMusicInput(BaseModel):
    name: str = Field(default=_DEFAULT_NAME, description='音乐名(assets/ 下的文件名,不含扩展名)')
    duration: Optional[float] = Field(
        default=10,
        description='播放秒数;>0 播指定秒数后自动退出,0 或 null 播整首',
    )


class PlayMusic(XmlRoutine):
    """按 name 播放音乐,body 派生子(如 dance)边放边跑."""

    meta = {
        'description': '按 name 播放本地音乐',
        'input_schema': PlayMusicInput.model_json_schema(),
    }

    def __init__(self):
        super().__init__()
        self._player = None

    async def on_created(self, rid: str, kwargs: Dict[str, Any]):
        await super().on_created(rid, kwargs)
        return Modules([MODULE_AUDIO])

    async def run(self, kwargs: Dict[str, Any]):
        """
        duration: 0表示播整首; >0 播指定秒数后自动退出

        example:
            <music/> 播放10s音乐
            <music><dance duration="3"/></music>边放音乐边跳舞
        """
        inputs = PlayMusicInput(**kwargs)
        name = inputs.name
        duration = inputs.duration
        if not name:
            raise ValueError('name parameter is required')
        if duration is not None and duration < 0:
            raise ValueError(f'duration must be >= 0 or None, got {duration!r}')
        if duration == 0:
            duration = None

        # 单 instance + 跨 shell 调度有漏: 第二个 run() 进来时, self._player
        # 可能仍对应上一首未完的播放.不清掉直接覆盖, 旧播放就成孤儿继续响
        # -> 听起来像"同时放两首".先把老的干掉.
        await self._stop_previous()

        file_path = _resolve(name)
        self._logger.info(
            'music: playing %s (duration=%s)',
            file_path, 'full' if duration is None else f'{duration}s',
        )

        self._player = create_wav_player(self._logger)
        await self._player.play(file_path, duration)
        self._logger.info('music: start finished')

    async def _stop_previous(self):
        player = self._player
        if player is None:
            return
        self._logger.warning(
            'music: previous player still alive, stopping before restart'
        )
        await player.stop()

    async def stop(self):
        self._logger.info('music: stopping')
        player = self._player
        if player is None:
            return
        self._logger.info('music: stop: begin')
        self._player = None
        await player.stop()
        self._logger.info('music: stop: finished')
