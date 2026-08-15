"""AutoDemo -- AutoSP 自动串并行端到端 demo.

编排 [ui_noop, quick, ui_noop]:
  - ui_noop[0] (ui 模块, 1s) + quick (无模块, 0.3s) → 不冲突 → 并行.
  - ui_noop[1] (ui) → 跟 ui_noop[0] 冲突 → 等第一个完成.

预期:ui_noop[0] + quick 同时 start;quick 0.3s 完成;ui_noop[0] 1s 完成 →
ui_noop[1] start;1s 后完成.总时长 ≈ 2s(两个 ui_noop 串行),quick 并行
搭车不增时长----验证"模块交集则串行否则并行".用 ui 避开 ForceDemo 的 output.
"""
from typing import Any, Dict

from routine import Routine


class AutoDemo(Routine):
    """AutoSP 端到端 demo:编排 [ui_noop, quick, ui_noop]."""

    meta = {'description': 'AutoSP 自动串并行 demo'}
    # is_passive = True

    async def run(self, kwargs: Dict[str, Any]):
        specs = [
            ('ui_noop', {'n': 'first'}),
            ('quick', {'msg': 'parallel'}),
            ('ui_noop', {'n': 'second'}),
        ]
        self._logger.info('AutoDemo: run AutoSP with %d specs %r',
                          len(specs), [n for n, _ in specs])
        results = await self.call('auto_sp', {'specs': specs})
        self._logger.info('AutoDemo results: %s', results)
