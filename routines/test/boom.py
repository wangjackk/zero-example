"""Boom -- start 故意抛异常的 routine(测试用).

验证 error 当 stopped 结果回报:不崩 server,异常透传给父 routine.给 Compose
run 它验 error 透传(捕获 RuntimeError 拿原因).
"""
from typing import Any, Dict

from routine import Routine


class Boom(Routine):
    """故意抛异常----验证 error 当 stopped 结果回报(不崩 server,error 透传给父)."""

    meta = {'description': 'boom(start 抛异常,测试 error 透传)'}

    # 不 override created()----不占模块(基类默认 None=空)

    async def run(self, kwargs: Dict[str, Any]):
        self._logger.info('boom start, about to raise')
        raise RuntimeError('boom! intentional error')
