"""Dance -- 占 body 模块,duration 秒后退出的叶子 routine.

给 PlayMusic 当 body 派生子用:``<music><dance duration="3"/></music>``
边放音乐边跳舞,duration 秒后 dance done,body_shell done 触发 PlayMusic 停播放.

占 ``body`` 模块--多个 dance 兄弟串行(同一时刻只能一个占 body);不跟 ``audio``
冲突(PlayMusic 占 audio,dance 占 body,父子可并发).duration 默认 5 秒.
"""
import asyncio
from typing import Any, Dict

from routine import Modules, Routine
from zero.modules import MODULE_BODY


def parse_duration(value) -> float:
    """解析 duration(秒).None / 0 / 负数 / 解析失败 -> 0(立即 done)."""
    if value is None or isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return max(0.0, float(value))
    if isinstance(value, str):
        try:
            return max(0.0, float(value))
        except ValueError:
            return 0.0
    return 0.0


class Dance(Routine):
    """dance routine:占 body 模块,duration 秒后退出."""

    meta = {'description': 'dance(占 body,duration 秒退出,PlayMusic 的 body 子)'}

    async def on_created(self, rid: str, kwargs: Dict[str, Any]) -> Modules:
        return Modules([MODULE_BODY])

    async def run(self, kwargs: Dict[str, Any]) -> dict[str, Any]:
        duration = parse_duration(kwargs.get('duration', 5))
        self._logger.info('dance %s start (duration=%ss)', self.id, duration)
        if duration > 0:
            await asyncio.sleep(duration)
        self._logger.info('dance %s done', self.id)
        return {'danced': duration}
