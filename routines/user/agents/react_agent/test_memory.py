"""ReactAgent Memory agents table CRUD + legacy sessions migration."""
import tempfile
import unittest

from zero.routines.user.agents.react_agent.memory import Memory


class TestMemoryAgentsTable(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._mem = Memory(tempfile.mktemp(dir=self._tmpdir.name, suffix='.db'))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_register_get_agent(self):
        self._mem.register_agent('a1', 's1', model='doubao')
        row = self._mem.get_agent('a1')
        self.assertIsNotNone(row)
        self.assertEqual(row['agent_id'], 'a1')
        self.assertEqual(row['session_id'], 's1')
        self.assertEqual(row['model'], 'doubao')
        self.assertEqual(row['status'], 'live')

    def test_register_upsert_preserves_created_at_on_resume(self):
        self._mem.register_agent('a1', 's1', model='doubao')
        self._mem.flush()
        before = self._mem.get_agent('a1')
        # resume: re-register same agent_id with new session
        self._mem.register_agent('a1', 's2', model='qwen')
        self._mem.flush()
        after = self._mem.get_agent('a1')
        self.assertEqual(after['session_id'], 's2')
        self.assertEqual(after['model'], 'qwen')
        self.assertEqual(after['status'], 'live')
        self.assertEqual(before['created_at'], after['created_at'])

    def test_list_agents_newest_first(self):
        self._mem.register_agent('old', 's-old', model='doubao')
        self._mem.register_agent('new', 's-new', model='qwen')
        self._mem.flush()
        rows = self._mem.list_agents()
        self.assertEqual(len(rows), 2)
        # newest-updated first (registered later)
        self.assertEqual(rows[0]['agent_id'], 'new')

    def test_set_handle_update_status(self):
        self._mem.register_agent('a1', 's1', model='doubao')
        self._mem.set_agent_handle('a1', 'h9')
        self._mem.update_agent_status('a1', 'stopped')
        self._mem.flush()
        row = self._mem.get_agent('a1')
        self.assertEqual(row['handle_id'], 'h9')
        self.assertEqual(row['status'], 'stopped')

    def test_mark_stale_live_as_stopped(self):
        self._mem.register_agent('live1', 's1', model='doubao')
        self._mem.register_agent('live2', 's2', model='qwen')
        self._mem.update_agent_status('live1', 'stopped')  # already stopped
        n = self._mem.mark_stale_live_as_stopped()
        self.assertEqual(n, 1)  # only live2
        self._mem.flush()
        self.assertEqual(self._mem.get_agent('live1')['status'], 'stopped')
        self.assertEqual(self._mem.get_agent('live2')['status'], 'stopped')

    def test_add_message_updates_agent_title_and_timestamp(self):
        self._mem.register_agent('a1', 's1', model='doubao')
        self._mem.add_message('user', 'hello world query',
                               agent_id='a1', message_id='m1', session_id='s1')
        self._mem.flush()
        row = self._mem.get_agent('a1')
        self.assertEqual(row['title'], 'hello world query')

    def test_get_agent_unknown_returns_none(self):
        self.assertIsNone(self._mem.get_agent('nope'))


class TestMemoryLegacyMigration(unittest.TestCase):
    """Legacy single-instance sessions table -> agents rows on schema init."""

    def test_legacy_sessions_migrated_to_stopped_agents(self):
        tmpdir = tempfile.TemporaryDirectory()
        try:
            db_path = tempfile.mktemp(dir=tmpdir.name, suffix='.db')
            # phase 1: simulate legacy single-instance db (only sessions table).
            import sqlite3, time
            conn = sqlite3.connect(db_path)
            conn.execute(
                'CREATE TABLE sessions(id TEXT PRIMARY KEY, created_at TEXT, '
                'updated_at TEXT, title TEXT, summary TEXT)'
            )
            ts = f'{time.time():.6f}'
            conn.execute(
                "INSERT INTO sessions(id, created_at, updated_at, title) "
                "VALUES('legacy-sess', ?, ?, 'old chat')",
                (ts, ts),
            )
            conn.commit()
            conn.close()
            # phase 2: new Memory() runs schema init -> migrates.
            mem = Memory(db_path)
            mem.flush()
            row = mem.get_agent('legacy-sess')
            self.assertIsNotNone(row)
            self.assertEqual(row['agent_id'], 'legacy-sess')
            self.assertEqual(row['session_id'], 'legacy-sess')
            self.assertEqual(row['status'], 'stopped')
            self.assertEqual(row['title'], 'old chat')
        finally:
            tmpdir.cleanup()


if __name__ == '__main__':
    unittest.main()
