"""UINoop -- 占 ui 模块,sleep 1s 后返回的简短 routine(AutoSP demo 用).

用 ``ui``(区别于 ForceDemo 的 ``output``)避免跨 demo 干扰.给 AutoDemo 当
被编排的冲突子 routine(两个 ui_noop 串行验证模块冲突→串行).
"""
import asyncio
from typing import Any, Dict, Optional

from routine import Modules, Routine
from zero.modules import MODULE_UI


class UINoop(Routine):
    """占 ui 模块的简短 routine(sleep 1s 后 return).给 AutoSP demo 用----
    用 ``ui``(区别于 ForceDemo 的 ``output``)避免跨 demo 干扰."""

    meta = {'description': 'ui noop(占 ui,秒退,AutoSP demo 用)'}

    async def on_created(self, rid: Optional[str] = None,
                    kwargs: Optional[Dict] = None) -> Modules:
        return Modules([MODULE_UI])

    async def run(self, kwargs: Dict[str, Any]):
        n = kwargs.get('n', 0)
        self._logger.info('ui_noop %s start (n=%s)', self.id, n)
        await asyncio.sleep(1)
        self._logger.info('ui_noop %s stopped (n=%s)', self.id, n)
        return {'ui': n}
