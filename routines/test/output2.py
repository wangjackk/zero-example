"""Output2 -- 占 output 模块,sleep 3s 后返回的 routine(骨架验证用).

给 Test / ForceDemo 当被编排的子 routine(跟 Echo 都占 output,可验模块冲突 /
force 抢占).无显式 stop(sleep 完自然终止).
"""
import asyncio
from typing import Any, Dict, Optional

from routine import Modules, Routine
from zero.modules import MODULE_OUTPUT


class Output2(Routine):
    meta = {'description': 'output'}

    async def on_created(self, rid: str, kwargs: Dict[str, Any]) -> Modules:
        return Modules([MODULE_OUTPUT])

    async def run(self, kwargs: Dict[str, Any]):
        self._logger.info('output start')
        await asyncio.sleep(3)
        self._logger.info('output stopped')
        return {'out': kwargs.get('text', '')}
