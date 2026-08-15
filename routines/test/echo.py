"""Echo -- 回显示例 routine(骨架验证用).

start 收到 text,原样返回.占 output 模块,有显式 stop(set event 让 start 退出).
给 Test / ForceDemo 当被编排的子 routine 用.
"""
import asyncio
from asyncio import Event
from typing import Any, Dict, Optional

from routine import Modules, Routine
from zero.modules import MODULE_OUTPUT


class Echo(Routine):
    """回显示例:start 收到 text,原样返回.骨架示例."""

    name = 'test_echo'

    meta = {'description': '回显示例 routine(骨架)'}

    def __init__(self):
        super().__init__()
        self._stop_event = Event()

    async def on_created(self, rid: Optional[str] = None,
                    kwargs: Optional[Dict] = None) -> Modules:
        return Modules([MODULE_OUTPUT])

    async def run(self, kwargs: Dict[str, Any]):
        self._logger.info(f'echo {self.id} start')
        await self._stop_event.wait()
        self._logger.info('echo st stopped')
        return {'echo': kwargs.get('text', '')}

    async def stop(self) -> None:
        self._logger.info(f'echo {self.id} stopping')
        self._stop_event.set()
