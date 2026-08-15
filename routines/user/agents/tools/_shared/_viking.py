"""viking:// URI 识别 + 路由到 OV 文件操作.

现有 Read/Write/Glob/Grep 工具检测到 viking:// 前缀时, 通过 ctx.req 回调 agent,
agent 调 OVMemory 的文件操作方法. 对 agent 完全透明: 同样的工具/参数/返回格式.
"""
from __future__ import annotations

from typing import Any

from zero.routines._shared._paths import AGENT_ID_KEY

_VIKING_PREFIX = 'viking://'

_DEFAULT_TIMEOUT = 60.0


def is_viking_uri(path: str | None) -> bool:
    """检测路径是否是 viking:// URI."""
    return bool(path) and str(path).startswith(_VIKING_PREFIX)


async def ov_route(
    ctx: Any,
    kwargs: dict[str, Any],
    op: str,
    data: dict[str, Any],
    timeout: float = _DEFAULT_TIMEOUT,
) -> str:
    """通过 ctx.req 回调 agent 执行 OV 文件操作, 返回格式化文本.

    agent 侧 handler 返回 {ok: bool, text: str, error?: str}.
    成功返回 text, 失败返回错误提示文本 (跟本地工具报错风格一致).
    """
    agent_id = kwargs.get(AGENT_ID_KEY)
    if not agent_id:
        return '错误: 无法定位当前 agent, viking:// 操作不可用.'
    rid_resp = await ctx.call('get_agent_rid', {'agent_id': agent_id})
    agent_rid = rid_resp.get('rid') if rid_resp.get('ok') else None
    if not agent_rid:
        return '错误: 无法定位 agent rid, viking:// 操作不可用.'
    try:
        resp = await ctx.req(agent_rid, op, data, timeout=timeout)
    except Exception as exc:
        return f'错误: viking:// 操作失败: {type(exc).__name__}: {exc}'
    if not isinstance(resp, dict):
        return f'错误: viking:// 操作返回异常: {resp!r}'
    if not resp.get('ok'):
        err = resp.get('error', 'unknown')
        return f'错误: {err}'
    return resp.get('text', '')
