"""Quick -- 不占模块,sleep 0.3s 后返回的快速 routine(测试用).

给 Compose.run / AutoDemo / WaitDemo 当"快进快出"子 routine:验证 run 拿结果,
编排并行搭车不增时长等.无显式 stop(sleep 完自然终止).
"""
import asyncio
from typing import Any, Dict

from routine import Routine


class Quick(Routine):
    """快速 routine:不占模块,sleep 一下就 return result.给 Compose.run 用."""

    meta = {'description': 'quick(不占模块,快速 return)'}

    # 不 override created()----不占模块(基类默认 None=空)

    async def run(self, kwargs: Dict[str, Any]):
        self._logger.info('quick start (kwargs=%s)', kwargs)
        await asyncio.sleep(0.3)
        return {'ok': True, 'echo': kwargs.get('msg', '')}
