"""DynamicDemo -- modules 按 kwargs 现算的 routine(实例级 modules 验证).

验证实例级 modules 支持:``created()`` 按 kwargs 返不同 modules,经 created 回报回带
kernel → submitted 回执带给父 handle(``handle.modules``),编排器据此算冲突.

kwargs ``mode``:
  - ``mode=='output'`` → 占 output 模块
  - ``mode=='ui'``      → 占 ui 模块
  - 其它/缺省           → 不占模块

跟 Echo(created return ['output'] 静态)对比:同样占 output,但 dynamic 是 created 时才算.
编排器 push 两个 mode='output' 的 DynamicDemo → handle.modules 都含 output → 冲突 → 串行;
push 一个 output 一个 ui → 不冲突 → 并行.

无显式 stop(sleep 完自然终止),跟 Quick 同款----只验 modules 现算,不验长生命周期.
"""
import asyncio
from typing import Any, Dict, Optional

from routine import Modules, Routine
from zero.modules import MODULE_OUTPUT, MODULE_UI


class DynamicDemo(Routine):
    """modules 按 kwargs['mode'] 现算(实例级)."""

    meta = {'description': 'dynamic modules demo(modules 按 kwargs mode 现算)'}

    async def on_created(self, rid: Optional[str] = None,
                    kwargs: Optional[Dict] = None) -> Optional[Modules]:
        # 按 kwargs['mode'] 决定占哪个模块----实例级现算,created 回报回带.
        # 不占模块时返回 None(等价 Modules() 空).
        if kwargs is None:
            self._mods = []
            return None
        mode = kwargs.get('mode', '')
        if mode == 'output':
            self._mods = [MODULE_OUTPUT]
        elif mode == 'ui':
            self._mods = [MODULE_UI]
        else:
            self._mods = []
        return Modules(self._mods) if self._mods else None

    async def run(self, kwargs: Dict[str, Any]):
        mode = kwargs.get('mode', '')
        mods = getattr(self, '_mods', [])
        self._logger.info('dynamic_demo start (mode=%s, modules=%s)', mode, mods)
        await asyncio.sleep(0.3)
        return {'ok': True, 'mode': mode, 'modules': mods}
