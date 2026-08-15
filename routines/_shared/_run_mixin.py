"""AgentRunMixin -- 通用 run handler, 供所有 agent 类混入.

HTTP /agents/{agent_id}/run/{name} 转发到 agent 的 'run' event,
agent 用本 mixin 的 handler 接收, 注入 from_agent_id 后 self.call 目标 routine.

这样 HTTP 层只转发, agent 内部执行, from_agent_id 由 agent 自己注入.
"""
from __future__ import annotations

from typing import Any

from routine import request

from ._paths import AGENT_ID_KEY


class AgentRunMixin:
    """通用 run handler. 子类需有 self._agent_id 和 self.call."""

    _agent_id: str

    @request('run')
    async def on_run(self, source, data: dict) -> dict:
        """HTTP 转发的 routine 调用. 注入 from_agent_id 后 call 目标."""
        target = str((data or {}).get('target') or '')
        kwargs = (data or {}).get('kwargs') or {}
        if not target:
            return {'ok': False, 'error': 'missing target routine name'}
        if not isinstance(kwargs, dict):
            return {'ok': False, 'error': 'kwargs must be a dict'}
        kwargs[AGENT_ID_KEY] = self._agent_id
        try:
            result: Any = await self.call(target, kwargs)  # type: ignore[attr-defined]
            return {'ok': True, 'result': result}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}
