"""ReactorAgentManager -- resident passive routine that spawns ReactorAgent children.

与 ClaudeCodeAgents 同构, 但 spawn 的是 ReactorAgent (ContextProvider + ResponseTracker).
复用同一 sqlite Store (共享 ~/.zero/sessions.db), agent_id 前缀 reactor_.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, ClassVar, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from routine import Routine, request
from routine.logger import setup_logger

from .._core.store import Store, get_store

_log = setup_logger('reactor.manager')

_AGENT_ROUTINE_NAME = 'reactor_agent'
_MANAGER_NAME = 'reactor_agent_manager'

# OpenViking 默认配置 (跟 claudecode 一致, 保证长期记忆默认启用).
_DEFAULT_OV_CONFIG: Dict[str, Any] = {
    'url': 'https://api.vikingdb.cn-beijing.volces.com/openviking',
    'api_key': 'ZGVmYXVsdA.ZGVmYXVsdA.YzhhNmQxZTBjYWE2ZmIzOGNmNzY3Y2Y0MThmOWFmNGZlNjhkMWM5YjE0NjljNzQwYThmNTFhNGI5MjMyNDRiYg',
    'user': 'zero',
    'push_every_n_turns': 5,
}


class ReactorAgentsInput(BaseModel):
    pass


class ReactorAgentsOutput(BaseModel):
    pass


class ReactorAgentManager(Routine):
    """resident passive manager: dynamically create/list/stop ReactorAgent children."""

    is_passive = True
    meta: ClassVar[Dict[str, Any]] = {
        'hidden': True,
        'input_schema': ReactorAgentsInput.model_json_schema(),
        'output_schema': ReactorAgentsOutput.model_json_schema(),
        'description': (
            'Resident manager for ReactorAgent coding agents. Spawns/lists/stops '
            'ReactorAgent child instances on request. Agent records persist to '
            'sqlite; each child runs concurrently, isolated by agent_id.'
        ),
    }

    def __init__(self) -> None:
        super().__init__()
        self._stop = asyncio.Event()
        self._agents: Dict[str, dict] = {}
        self._stopping: set[str] = set()

    def _store_for(self) -> 'Store':
        return get_store()

    async def on_started(self) -> None:
        _log.info('reactor agents manager started')

    async def run(self, kwargs: Dict[str, Any]) -> None:
        await self._stop.wait()

    async def stop(self) -> None:
        for agent_id in list(self._agents):
            info = self._agents.get(agent_id)
            if info is None:
                continue
            handle = info.get('handle')
            if handle is not None and not handle.is_done():
                try:
                    await handle.stop()
                except Exception as exc:
                    _log.warning('stop child %s on manager stop: %r', agent_id, exc)
        self._agents.clear()
        self._stop.set()

    # ------------------------------------------------------------------
    # req handlers
    # ------------------------------------------------------------------

    @request('create_agent')
    async def on_create(self, source, data: dict) -> dict:
        data = data or {}
        store = self._store_for()
        agent_id = str(data.get('agent_id') or '').strip()
        if agent_id:
            if store.get_agent(agent_id) is not None:
                return {'ok': False, 'error': f'agent_id {agent_id} already exists; use resume instead'}
        else:
            agent_id = self._next_agent_id(store)
        if agent_id in self._agents:
            return {'ok': False, 'error': f'agent_id {agent_id} already live'}
        session_id = uuid4().hex
        try:
            store.register_agent(agent_id, session_id=session_id, model=data.get('model'))
        except Exception as exc:
            _log.warning('persist agent %s failed: %r', agent_id, exc)
        return await self._spawn_child(agent_id, data, is_resume=False, session_id=session_id)

    @request('resume_agent')
    async def on_resume(self, source, data: dict) -> dict:
        data = data or {}
        agent_id = str(data.get('agent_id') or '').strip()
        if not agent_id:
            return {'ok': False, 'error': 'agent_id is required'}
        if agent_id in self._agents:
            return {'ok': False, 'error': f'agent_id {agent_id} already live'}
        store = self._store_for()
        agent_rec = store.get_agent(agent_id)
        if agent_rec is None:
            return {'ok': False, 'error': f'agent_id {agent_id} not found'}
        session_id = str(agent_rec.get('session_id') or '') or uuid4().hex
        return await self._spawn_child(agent_id, data, is_resume=True, session_id=session_id)

    async def _spawn_child(
        self, agent_id: str, data: dict, *, is_resume: bool, session_id: str,
    ) -> dict:
        project_dir = data.get('project_dir') or data.get('project_dir_root_path')
        model = data.get('model')
        plan_mode = bool(data.get('plan_mode', False))
        extra_instructions = data.get('extra_instructions')
        max_turns = data.get('max_turns')
        # reactor 只暴露 run_routine 一个 tool, 其他 routine 通过它调用.
        enabled_tools = ['run_routine']
        disabled_tools = None
        preload_skills = data.get('preload_skills')
        level1_skills = data.get('level1_skills')
        condense_config = data.get('condense_config')
        ov_config = data.get('ov_config') or _DEFAULT_OV_CONFIG

        child_kwargs: Dict[str, Any] = {
            'agent_id': agent_id,
            'project_dir_root_path': project_dir,
            'model': model,
            'plan_mode': plan_mode,
            'extra_instructions': extra_instructions,
            'max_turns': max_turns,
            'session_id': session_id,
            'preload_skills': preload_skills,
            'level1_skills': level1_skills,
            'enabled_tools': enabled_tools,
            'disabled_tools': disabled_tools,
            'condense_config': condense_config,
            'ov_config': ov_config,
        }
        try:
            handle = await self.submit(_AGENT_ROUTINE_NAME, child_kwargs)
            await handle.start()
        except Exception as exc:
            action = 'resume' if is_resume else 'create'
            _log.error('%s reactor agent %s failed: %r', action, agent_id, exc)
            return {'ok': False, 'error': str(exc)}

        self._agents[agent_id] = {
            'handle': handle,
            'project_dir': project_dir,
            'session_id': session_id,
        }
        action = 'resumed' if is_resume else 'created'
        _log.info(
            '%s reactor agent: agent_id=%s handle_id=%s session_id=%s project_dir=%s',
            action, agent_id, handle.id, session_id, project_dir,
        )
        return {
            'ok': True,
            'agent_id': agent_id,
            'handle_id': handle.id,
            'session_id': session_id,
        }

    @request('list_agents')
    async def on_list(self, source, data: dict) -> dict:
        data = data or {}
        store = self._store_for()
        rows = store.list_agents()

        filter_pd = data.get('project_dir')
        if filter_pd:
            filter_pd_resolved = str(Path(filter_pd).resolve())
            rows = [
                r for r in rows
                if (info := self._agents.get(r.get('agent_id'))) is not None
                and info.get('project_dir')
                and str(Path(info['project_dir']).resolve()) == filter_pd_resolved
            ]

        items = []
        for row in rows:
            agent_id = row.get('agent_id', '')
            if not agent_id.startswith('reactor_'):
                continue
            info = self._agents.get(agent_id)
            live = info is not None
            handle = (info or {}).get('handle')
            items.append({
                'agent_id': agent_id,
                'model': row.get('model'),
                'title': row.get('title'),
                'created_at': row.get('created_at'),
                'updated_at': row.get('updated_at'),
                'session_id': (info or {}).get('session_id'),
                'project_dir': (info or {}).get('project_dir'),
                'handle_id': handle.id if handle else None,
                'live': live,
                'started': live,
                'done': handle.is_done() if handle else True,
            })
        return {'agents': items}

    @request('stop_agent')
    async def on_stop(self, source, data: dict) -> dict:
        data = data or {}
        agent_id = str(data.get('agent_id') or '').strip()
        if not agent_id:
            return {'ok': False, 'error': 'agent_id is required'}
        info = self._agents.get(agent_id)
        if info is None:
            return {'ok': False, 'error': f'agent_id {agent_id} not live'}
        if agent_id in self._stopping:
            return {'ok': True, 'agent_id': agent_id}
        self._stopping.add(agent_id)
        try:
            handle = info.get('handle')
            if handle is not None and not handle.is_done():
                await handle.stop()
            self._agents.pop(agent_id, None)
            _log.info('stopped reactor agent: agent_id=%s', agent_id)
            return {'ok': True, 'agent_id': agent_id}
        except Exception as exc:
            _log.warning('stop reactor agent %s failed: %r', agent_id, exc)
            return {'ok': False, 'error': str(exc)}
        finally:
            self._stopping.discard(agent_id)

    @request('delete_agent')
    async def on_delete(self, source, data: dict) -> dict:
        data = data or {}
        agent_id = str(data.get('agent_id') or '').strip()
        if not agent_id:
            return {'ok': False, 'error': 'agent_id is required'}
        if agent_id in self._agents:
            return {'ok': False, 'error': f'agent_id {agent_id} is live; stop it first'}
        store = self._store_for()
        try:
            store.delete_agent(agent_id)
        except Exception as exc:
            _log.warning('delete reactor agent %s failed: %r', agent_id, exc)
            return {'ok': False, 'error': str(exc)}
        _log.info('deleted reactor agent: agent_id=%s', agent_id)
        return {'ok': True, 'agent_id': agent_id}

    def _next_agent_id(self, store: 'Store') -> str:
        """生成下一个 reactor_<N> agent_id."""
        existing = {r.get('agent_id', '') for r in store.list_agents()}
        n = 1
        while f'reactor_{n}' in existing or f'reactor_{n}' in self._agents:
            n += 1
        return f'reactor_{n}'


# ──────────────────────────────────────────────────────────────────────────────
# entry routine (bridge -> manager)
# ──────────────────────────────────────────────────────────────────────────────

class CreateReactorAgentInput(BaseModel):
    agent_id: str | None = Field(None, description='Agent id. Auto-generated when omitted.')
    project_dir: str | None = Field(None, description='Project root directory path.')
    model: str | None = Field(None, description='LLM model name.')
    plan_mode: bool = Field(False, description='Readonly tools only.')
    extra_instructions: str | None = Field(None, description='Extra system instructions.')
    max_turns: int | None = Field(None, description='Max conversation turns.')
    preload_skills: list[str] | None = Field(None, description='Skills to preload.')
    level1_skills: list[str] | None = Field(None, description='Level-1 skill discovery.')
    enabled_tools: list[str] | None = Field(None, description='Tool whitelist.')
    disabled_tools: list[str] | None = Field(None, description='Tool blacklist.')


class CreateReactorAgentOutput(BaseModel):
    pass


class CreateReactorAgent(Routine):
    """entry routine: spawn a ReactorAgent via the resident manager."""

    meta: ClassVar[Dict[str, Any]] = {
        'hidden': True,
        'input_schema': CreateReactorAgentInput.model_json_schema(),
        'output_schema': CreateReactorAgentOutput.model_json_schema(),
        'description': (
            'Entry routine that spawns a ReactorAgent coding agent via the '
            'resident ReactorAgentManager. Returns the new agent_id.'
        ),
    }

    _REQ_TIMEOUT = 10.0

    async def run(self, kwargs: Dict[str, Any]) -> dict:
        manager_id = await self._find_manager()
        if manager_id is None:
            raise RuntimeError(
                f'{_MANAGER_NAME} manager not running; cannot spawn agent'
            )
        return await self.ctx.req(
            manager_id, 'create_agent', kwargs or {},
            timeout=self._REQ_TIMEOUT,
        )

    async def _find_manager(self) -> Optional[str]:
        for _ in range(50):
            try:
                routines = await self.ctx.get_running_routines()
            except Exception as exc:
                _log.warning('get_running failed (%r), retry', exc)
                routines = []
            for r in routines:
                if str(r.get('name') or '') == _MANAGER_NAME:
                    rid = str(r.get('id') or '').strip()
                    if rid:
                        return rid
            await asyncio.sleep(0.1)
        return None
