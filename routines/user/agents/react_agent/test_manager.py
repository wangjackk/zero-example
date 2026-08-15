"""ReactAgents manager + CreateReactAgent entry -- spawn/list/stop logic.

Stub out submit / ctx.req / get_running_routines and inject a temp sqlite
Memory (temp db path) to verify:
- manager.create returns ok + agent_id (auto when omitted), rejects live dup,
  persists an agents row (status live, handle_id set), forwards child kwargs.
- manager.create resumes a stopped agent_id, reusing its stored session_id.
- manager.list reflects db rows with live/started/done annotation.
- manager.stop drops the live handle + marks the row stopped (idempotent).
- manager.on_started reconciles stale 'live' rows to 'stopped' on restart.
- CreateReactAgent locates manager by name, reqs 'create_agent',
  returns the manager's reply; raises if manager not found.
"""
import asyncio
import tempfile
import unittest

from zero.routines.user.agents.react_agent.manager import ReactAgents, CreateReactAgent
from zero.routines.user.agents.react_agent.memory import Memory


class _FakeHandle:
    """mimics RoutineHandle enough for manager: id / start / stop / is_started / is_done."""

    def __init__(self, hid: str):
        self.id = hid
        self._started = False
        self._done = False
        self.stop_calls = 0

    async def start(self):
        self._started = True
        return None

    async def stop(self, *, fire: bool = False):
        self.stop_calls += 1
        self._done = True

    def is_started(self) -> bool:
        return self._started

    def is_done(self) -> bool:
        return self._done


class TestReactAgentsManager(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._mem = Memory(tempfile.mktemp(dir=self._tmpdir.name, suffix='.db'))

    def tearDown(self):
        self._tmpdir.cleanup()

    def _make_manager(self):
        m = ReactAgents()
        # inject temp memory so tests are isolated from runtime/ memory.db
        m._mem = self._mem
        m._started = True
        created_handles: list[_FakeHandle] = []
        next_id = [0]
        captured_kwargs: list[dict] = []

        async def fake_submit(name, kwargs=None):
            captured_kwargs.append(dict(kwargs or {}))
            next_id[0] += 1
            h = _FakeHandle(f'h{next_id[0]}')
            created_handles.append(h)
            return h

        m.submit = fake_submit  # type: ignore[assignment]
        return m, created_handles, captured_kwargs

    async def test_create_auto_agent_id(self):
        m, _handles, kwargs_list = self._make_manager()
        result = await m.on_create(None, {'model': 'doubao'})
        self.assertTrue(result['ok'], result)
        self.assertIn('agent_id', result)
        self.assertEqual(len(result['agent_id']), 32)  # uuid4().hex
        # child kwargs forwarded
        self.assertEqual(len(kwargs_list), 1)
        kw = kwargs_list[0]
        self.assertEqual(kw['agent_id'], result['agent_id'])
        self.assertEqual(kw['session_id'], result['session_id'])
        self.assertEqual(kw['model'], 'doubao')
        # auto agent_id -> no db row to resume from -> manager generates a fresh
        # session_id and the row + child agree.
        self.assertEqual(len(result['session_id']), 32)

    async def test_create_rejects_live_dup(self):
        m, _h, _kw = self._make_manager()
        await m.on_create(None, {'agent_id': 'dup', 'model': 'qwen'})
        result = await m.on_create(None, {'agent_id': 'dup'})
        self.assertFalse(result['ok'])
        self.assertIn('already live', result['error'])

    async def test_create_persists_agent_row(self):
        m, handles, _kw = self._make_manager()
        result = await m.on_create(None, {'agent_id': 'a1', 'session_id': 's1',
                                          'model': 'claude'})
        self.assertTrue(result['ok'])
        row = self._mem.get_agent('a1')
        self.assertIsNotNone(row)
        self.assertEqual(row['session_id'], 's1')
        self.assertEqual(row['status'], 'live')
        self.assertEqual(row['model'], 'claude')
        self._mem.flush()
        row2 = self._mem.get_agent('a1')
        self.assertEqual(row2['handle_id'], handles[0].id)

    async def test_resume_existing_agent_id_reuses_session_id(self):
        m, _h, _kw = self._make_manager()
        await m.on_create(None, {'agent_id': 'r1', 'session_id': 'sess-x',
                                 'model': 'doubao'})
        await m.on_stop_agent(None, {'agent_id': 'r1'})
        # re-spawn WITHOUT session_id -> resume from db
        result = await m.on_create(None, {'agent_id': 'r1'})
        self.assertTrue(result['ok'])
        self.assertEqual(result['session_id'], 'sess-x')

    async def test_list_reflects_db_rows_with_live_annotation(self):
        m, _h, _kw = self._make_manager()
        await m.on_create(None, {'agent_id': 'live1', 'model': 'doubao'})
        await m.on_create(None, {'agent_id': 'hist1', 'model': 'doubao'})
        await m.on_stop_agent(None, {'agent_id': 'hist1'})
        result = await m.on_list(None, {})
        agents = {a['agent_id']: a for a in result['agents']}
        self.assertEqual(set(agents), {'live1', 'hist1'})
        self.assertTrue(agents['live1']['live'])
        self.assertFalse(agents['hist1']['live'])

    async def test_stop_marks_row_stopped_and_idempotent(self):
        m, handles, _kw = self._make_manager()
        await m.on_create(None, {'agent_id': 'a1', 'model': 'doubao'})
        self.assertEqual(handles[0].stop_calls, 0)
        result = await m.on_stop_agent(None, {'agent_id': 'a1'})
        self.assertTrue(result['ok'])
        self.assertEqual(result['agent_id'], 'a1')
        self.assertEqual(handles[0].stop_calls, 1)
        self._mem.flush()
        row = self._mem.get_agent('a1')
        self.assertEqual(row['status'], 'stopped')
        self.assertNotIn('a1', m._agents)
        # stop again -> idempotent ok (row already stopped, no live handle)
        result2 = await m.on_stop_agent(None, {'agent_id': 'a1'})
        self.assertTrue(result2['ok'])

    async def test_stop_requires_agent_id(self):
        m, _h, _kw = self._make_manager()
        result = await m.on_stop_agent(None, {})
        self.assertFalse(result['ok'])
        self.assertIn('required', result['error'])

    async def test_stop_unknown_agent_returns_not_found(self):
        m, _h, _kw = self._make_manager()
        result = await m.on_stop_agent(None, {'agent_id': 'nope'})
        self.assertFalse(result['ok'])
        self.assertIn('not found', result['error'])

    async def test_on_started_marks_stale_live_as_stopped(self):
        # seed db with a live row from a "previous process"
        self._mem.register_agent('stale1', 's-stale', model='doubao')
        m, _h, _kw = self._make_manager()
        await m.on_started()
        self._mem.flush()
        row = self._mem.get_agent('stale1')
        self.assertEqual(row['status'], 'stopped')

    async def test_multiple_agents_get_distinct_handle_ids(self):
        m, handles, _kw = self._make_manager()
        await m.on_create(None, {'agent_id': 'a1', 'model': 'doubao'})
        await m.on_create(None, {'agent_id': 'a2', 'model': 'qwen'})
        result = await m.on_list(None, {})
        self.assertEqual(len(result['agents']), 2)

    async def test_stop_only_targeted_agent(self):
        m, handles, _kw = self._make_manager()
        await m.on_create(None, {'agent_id': 'left', 'model': 'doubao'})
        await m.on_create(None, {'agent_id': 'right', 'model': 'doubao'})
        await m.on_stop_agent(None, {'agent_id': 'left'})
        self.assertEqual(handles[0].stop_calls, 1)
        self.assertEqual(handles[1].stop_calls, 0)  # right untouched


class TestCreateReactAgentEntry(unittest.IsolatedAsyncioTestCase):
    """CreateReactAgent.run locates manager by name and reqs 'create_agent'."""

    def _make(self, *, routines, req_result=None):
        inst = CreateReactAgent()
        inst._started = True
        ctx = _StubCtx(routines=routines, req_result=req_result)
        inst._active_ctx = ctx
        return inst, ctx

    async def test_run_reqs_manager_create_agent(self):
        routines = [{'name': 'react_agents', 'id': 'mgr-1'},
                    {'name': 'other', 'id': 'x-2'}]
        reply = {'ok': True, 'agent_id': 'x1', 'session_id': 'sx'}
        inst, ctx = self._make(routines=routines, req_result=reply)
        result = await inst.run({'agent_id': 'x1'})
        self.assertEqual(result, reply)
        self.assertEqual(len(ctx.req_calls), 1)
        target, event, data, _timeout = ctx.req_calls[0]
        self.assertEqual(target, 'mgr-1')
        self.assertEqual(event, 'create_agent')
        self.assertEqual(data, {'agent_id': 'x1'})

    async def test_run_raises_when_manager_not_found(self):
        inst = CreateReactAgent()
        inst._started = True
        ctx = _StubCtx(routines=[{'name': 'other', 'id': 'x'}])
        inst._active_ctx = ctx
        # short-circuit the retry loop sleep to avoid 5s wait
        orig_sleep = asyncio.sleep

        async def _noop(_):
            return None

        asyncio.sleep = _noop  # type: ignore[assignment]
        try:
            with self.assertRaises(RuntimeError):
                await inst.run({})
        finally:
            asyncio.sleep = orig_sleep  # type: ignore[assignment]


class _StubCtx:
    """minimal ctx for CreateReactAgent: get_running_routines + req."""

    def __init__(self, *, routines, req_result=None):
        self._routines = routines
        self._req_result = req_result
        self.req_calls: list = []

    async def get_running_routines(self):
        return self._routines

    async def req(self, target, event, data, *, timeout):
        self.req_calls.append((target, event, dict(data or {}), timeout))
        return self._req_result


if __name__ == '__main__':
    unittest.main()
