"""Test -- 骨架验证 routine:submit echo + output2,start/try_start.

验 created hook,submit 拿 handle,start/try_start 失败返回 StartError 不抛.
"""
import asyncio
from typing import Any, Dict, Optional

from routine import Routine, Modules


class Test(Routine):
    meta = {'description': 'test'}
    # is_passive = True

    async def on_created(self, rid: str, kwargs: Dict[str, Any]):
        self._logger.info(f'created {rid} test')

    async def run(self, kwargs: Dict[str, Any]):
        self._logger.info('test start, self.id=%s', self.id)
        h = await self.submit('test_echo')
        m = await self.submit('output2')
        self._logger.info('test got handles: echo=%s output2=%s', h.id, m.id)
        await h.start()
        # try_start 失败不抛异常,返回 StartError;模块冲突是正常业务情况
        err = await m.try_start()
        if err:
            self._logger.warning('output2 try_start failed: %s', err)

        await asyncio.sleep(5)
        self._logger.info(f'test stopped')
