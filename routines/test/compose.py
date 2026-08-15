"""Compose -- 验证 self.run 同步拿子 routine result(submit → start → wait 一步).

run quick 拿结果;再 run boom 验 error 透传(捕获 RuntimeError 拿原因).
"""
from typing import Any, Dict

from routine import Routine


class Compose(Routine):
    """compose:用 self.run 同步拿子 routine 结果(submit → start → wait 一步)."""

    meta = {'description': 'compose(run 子 routine 拿结果)'}
    # is_passive = True

    async def run(self, kwargs: Dict[str, Any]):
        self._logger.info('compose start, running quick...')
        result = await self.call('quick', {'msg': 'hello'})
        self._logger.info('compose got result: %s', result)

        # 验证 error 透传:run 一个会抛异常的子 routine,捕获 RuntimeError 拿原因
        try:
            await self.call('boom')
        except RuntimeError as e:
            self._logger.info('compose caught boom error: %s', e)
