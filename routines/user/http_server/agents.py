"""Agent 管理的 HTTP/WS handler 函数.

由 ``server.HttpServer._on_client_message`` 和 ``app.build_app`` 调用.
模块级函数(接收 ``inst`` 第一参数),复用 self.ctx.req 查询 manager routine.

manager routine(claude_code_agents / react_agents)是独立 passive routine,
可能跑在另一个进程,故按 name 查 running 列表拿 id.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# claudecode / react agents manager routine name.bridge finds it by name via
# get_running_routines (may run in another process).
_CLAUDECODE_MANAGER_NAME = 'claude_code_agents'
_REACT_MANAGER_NAME = 'react_agents'
_REACTOR_MANAGER_NAME = 'reactor_agent_manager'
_PRIME_MANAGER_NAME = 'prime_agent_manager'
_CLAUDECODE_MANAGER_REQ_TIMEOUT = 10.0

# kind -> (entry routine name, manager name)
_KIND_ROUTING = {
    'react': ('create_react_agent', _REACT_MANAGER_NAME),
    'reactor': ('create_reactor_agent', _REACTOR_MANAGER_NAME),
    'claude': ('create_claude_agent', _CLAUDECODE_MANAGER_NAME),
    'prime': ('create_prime_agent', _PRIME_MANAGER_NAME),
}


async def find_manager_id(inst, name: str) -> str | None:
    """按 name 查 running manager routine id(跨进程正确)."""
    try:
        routines = await inst.ctx.get_running_routines()
    except Exception as exc:
        logger.warning('[bridge] get_running failed (%r)', exc)
        return None
    for r in routines:
        if str(r.get('name') or '') == name:
            rid = str(r.get('id') or '').strip()
            if rid:
                return rid
    return None


async def _list_from_manager(inst, manager_name: str, kind: str) -> list:
    manager_id = await find_manager_id(inst, manager_name)
    if manager_id is None:
        return []
    try:
        result = await inst.ctx.req(
            manager_id, 'list_agents', {},
            timeout=_CLAUDECODE_MANAGER_REQ_TIMEOUT,
        )
    except Exception as exc:
        logger.warning('[bridge] list_agents (%s) error: %s', kind, exc)
        return []
    items = list(result.get('agents') or [])
    for it in items:
        it['kind'] = kind
    return items


async def on_create_agent(inst, msg: dict, reply) -> None:
    """创建 agent (react / reactor / claude). msg 字段:kind/project_dir/agent_id/model/..."""
    req_id = msg.get('id')
    kind = str(msg.get('kind') or 'claude').strip().lower() or 'claude'
    routing = _KIND_ROUTING.get(kind)
    if routing is None:
        await reply({'type': 'agent_created', 'id': req_id, 'kind': kind,
                     'ok': False, 'error': f'unknown agent kind: {kind}'})
        return
    entry_name, _ = routing
    payload = {k: v for k, v in msg.items() if k not in ('type', 'id', 'kind')}
    try:
        result = await inst.call(entry_name, payload)
        await reply({'type': 'agent_created', 'id': req_id, 'kind': kind, **result})
    except Exception as exc:
        logger.warning('[bridge] create_agent (%s) error: %s', kind, exc)
        await reply({'type': 'agent_created', 'id': req_id, 'kind': kind,
                     'ok': False, 'error': str(exc)})


async def on_list_agents(inst, msg: dict, reply) -> None:
    """列出所有 agent (react + reactor + claude + prime, 聚合四个 manager)."""
    req_id = msg.get('id')
    try:
        react_items = await _list_from_manager(inst, _REACT_MANAGER_NAME, 'react')
        reactor_items = await _list_from_manager(inst, _REACTOR_MANAGER_NAME, 'reactor')
        claude_items = await _list_from_manager(inst, _CLAUDECODE_MANAGER_NAME, 'claude')
        prime_items = await _list_from_manager(inst, _PRIME_MANAGER_NAME, 'prime')
        await reply({'type': 'agents', 'id': req_id,
                     'agents': react_items + reactor_items + claude_items + prime_items})
    except Exception as exc:
        logger.warning('[bridge] list_agents error: %s', exc)
        await reply({'type': 'agents', 'id': req_id, 'agents': [], 'error': str(exc)})


async def on_resume_agent(inst, msg: dict, reply) -> None:
    """恢复 agent (react / reactor / claude). msg 字段: kind/agent_id/model/...

    跟 on_stop_agent 一样直接 req manager (不走 entry routine),
    因为 resume 是对已存在 agent 的操作, 跟 stop 语义一致.
    """
    req_id = msg.get('id')
    kind = str(msg.get('kind') or 'claude').strip().lower() or 'claude'
    routing = _KIND_ROUTING.get(kind)
    if routing is None:
        await reply({'type': 'agent_resumed', 'id': req_id, 'kind': kind,
                     'ok': False, 'error': f'unknown agent kind: {kind}'})
        return
    _, manager_name = routing
    payload = {k: v for k, v in msg.items() if k not in ('type', 'id', 'kind')}
    manager_id = await find_manager_id(inst, manager_name)
    if manager_id is None:
        await reply({'type': 'agent_resumed', 'id': req_id, 'kind': kind,
                     'ok': False, 'error': f'{kind} manager not running'})
        return
    try:
        result = await inst.ctx.req(
            manager_id, 'resume_agent', payload,
            timeout=_CLAUDECODE_MANAGER_REQ_TIMEOUT,
        )
        await reply({'type': 'agent_resumed', 'id': req_id, 'kind': kind, **result})
    except Exception as exc:
        logger.warning('[bridge] resume_agent (%s) error: %s', kind, exc)
        await reply({'type': 'agent_resumed', 'id': req_id, 'kind': kind,
                     'ok': False, 'error': str(exc)})


async def on_stop_agent(inst, msg: dict, reply) -> None:
    """停止 agent. 先 react, 再 reactor, 最后 claude."""
    req_id = msg.get('id')
    agent_id = str(msg.get('agent_id') or '').strip()
    if not agent_id:
        await reply({'type': 'agent_stopped', 'id': req_id, 'ok': False,
                     'error': 'agent_id is required'})
        return
    result = None
    for manager_name, kind in (
        (_REACT_MANAGER_NAME, 'react'),
        (_REACTOR_MANAGER_NAME, 'reactor'),
        (_CLAUDECODE_MANAGER_NAME, 'claude'),
        (_PRIME_MANAGER_NAME, 'prime'),
    ):
        manager_id = await find_manager_id(inst, manager_name)
        if manager_id is None:
            continue
        try:
            res = await inst.ctx.req(
                manager_id, 'stop_agent', {'agent_id': agent_id},
                timeout=_CLAUDECODE_MANAGER_REQ_TIMEOUT,
            )
        except Exception as exc:
            logger.warning('[bridge] stop_agent (%s) error: %s', kind, exc)
            continue
        if res.get('ok'):
            result = {**res, 'kind': kind}
            break
        result = result or res
    # 清理本地 ns 缓存(由 register_agent 填充)
    inst._agent_ns.pop(agent_id, None)
    inst._agent_names.pop(agent_id, None)
    inst._agent_rids.pop(agent_id, None)
    if result is None:
        result = {'ok': False, 'error': 'no agent manager running'}
    await reply({'type': 'agent_stopped', 'id': req_id, 'agent_id': agent_id, **result})


async def on_delete_agent(inst, msg: dict, reply) -> None:
    """删除 agent (DB agents 行 + messages). 先 react, 再 reactor, 最后 claude.

    live 的 agent 拒绝删除 (前端应先 stop 再 delete). 删完不可恢复.
    """
    req_id = msg.get('id')
    agent_id = str(msg.get('agent_id') or '').strip()
    if not agent_id:
        await reply({'type': 'agent_deleted', 'id': req_id, 'ok': False,
                     'error': 'agent_id is required'})
        return
    result = None
    for manager_name, kind in (
        (_REACT_MANAGER_NAME, 'react'),
        (_REACTOR_MANAGER_NAME, 'reactor'),
        (_CLAUDECODE_MANAGER_NAME, 'claude'),
        (_PRIME_MANAGER_NAME, 'prime'),
    ):
        manager_id = await find_manager_id(inst, manager_name)
        if manager_id is None:
            continue
        try:
            res = await inst.ctx.req(
                manager_id, 'delete_agent', {'agent_id': agent_id},
                timeout=_CLAUDECODE_MANAGER_REQ_TIMEOUT,
            )
        except Exception as exc:
            logger.warning('[bridge] delete_agent (%s) error: %s', kind, exc)
            continue
        if res.get('ok'):
            result = {**res, 'kind': kind}
            break
        result = result or res
    if result is None:
        result = {'ok': False, 'error': 'no agent manager running'}
    await reply({'type': 'agent_deleted', 'id': req_id, 'agent_id': agent_id, **result})
