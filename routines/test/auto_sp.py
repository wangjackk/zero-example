"""AutoSP -- 模块自动串并行编排器(业务侧策略库,Shell 的 routine 门面).

输入 ``specs=[(name, kwargs), ...]``,按模块冲突自动分组:冲突对串行(输入
顺序),非冲突并行.对标老版 ``CanBlockRightSibling`` 语义,但**作为业务库**
----不嵌入内核.跟 DAG / FSM / 行为树平起平坐,都建在 ctx.submit/start/await +
ctx.conflict 原语上(kernel 只管互斥/生命周期/总线).

实现委托 ``Shell``(参考老版 Go ``shell_scheduler_go/shell/shell.go`` 的命令
队列 + ``processLeftSiblings``).本类是 routine 门面:让编排能像普通 routine
一样被 submit/call(如 AutoDemo 的 ``self.call('auto_sp', ...)``).
"""
from typing import Any, Dict

from routine import Routine
from zero.shell import Shell


class AutoSP(Routine):
    """模块自动串并行编排器(业务侧策略库)."""

    meta = {'description': '自动串并行编排器(模块冲突→串行,否则→并行)'}

    # 不 override created()----编排器自身不占模块,只编排子 routine(基类默认 None=空)

    async def run(self, kwargs: Dict[str, Any]):
        specs = kwargs.get('specs', [])
        self._logger.info('AutoSP orchestrating %d specs', len(specs))
        results = await Shell(self).run(specs)
        self._logger.info('AutoSP done: %s', results)
        return results
