"""WaitDemo -- Wait barrier + duration 端到端 demo.

编排 [quick(0.3), wait(0.5), quick(0.3)].wait 是双向全局同步点:等所有
左兄弟完成 → 自己 sleep duration → 放行右兄弟.quick 不占模块,两个 quick
本不冲突(无 wait 会并行),但中间的 wait 把它们切成串行两段.

预期时序:
  - quick[before] start(0.0),0.3s 完成
  - wait 等 quick[before] → 0.3s start,sleep 0.5s → 0.8s 完成
  - quick[after] 等 wait → 0.8s start,0.3s → 1.1s 完成
总时长 ≈ 1.1s.验证 wait "等左兄弟 + 阻塞右兄弟 + duration"三合一语义.
"""
from typing import Any, Dict

from routine import Routine


class WaitDemo(Routine):
    """Wait barrier + duration 端到端 demo:编排 [quick(0.3), wait(0.5), quick(0.3)]."""

    meta = {'description': 'wait barrier + duration demo'}
    # is_passive = True

    async def run(self, kwargs: Dict[str, Any]):
        specs = [
            ('quick', {'msg': 'before'}),
            ('wait', {'duration': 0.5}),
            ('quick', {'msg': 'after'}),
        ]
        self._logger.info('WaitDemo: run with %d specs %r',
                          len(specs), [n for n, _ in specs])
        results = await self.call('auto_sp', {'specs': specs})
        self._logger.info('WaitDemo results: %s', results)
