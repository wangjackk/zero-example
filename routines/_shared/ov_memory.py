"""OpenViking 长期记忆推送 + 文件操作 (业务自管 task,不用 ctx.spawn).

职责:
  - 启动时 init OV client + 用 kshell session_id 创建 OV session (1:1 对齐)
  - 每 N 轮增量 add_message 到 OV (不 commit, 只在会话边界才 commit)
  - resume 时读游标文件跳过已推的历史 (避免重推)
  - agent 关闭: 推剩余 + commit 归档 + close (agent=session, 关闭即 session 结束)
  - 文件操作: read/write/glob/grep 供 Read/Write/Glob/Grep 工具映射 viking://

OV 规范 (对照 viking_intro/design.md):
  - session 流只累积真实对话 (add_message), 不到边界不 commit
  - commit_session 唯一触发 = agent 关闭 (agent=session 模型, 关闭即 session 结束)
  - L0/L1/L2 + 记忆卡片由后端在 commit 后异步生成, 不在前端反复触发

peer_id 策略: 所有 claude agent 共用一个固定 peer_id (不区分 agent_id),
OV 后端把所有 claude 的记忆卡片归档到同一目录, 跨 agent 共享.

OV 文件夹结构:
  viking://user/default/
  ├── memories/                          # 用户记忆 (全局共享)
  ├── peers/claude/memories/             # 所有 claude agent 共用的私有记忆
  │   └── summaries/{session_id}.md      # 各 session 的压缩摘要
  ├── sessions/                          # OV session (跟 kshell session 1:1 对齐)
  ├── skills/
  └── resources/

session 对齐:
  - OV session_id = kshell session_id (create_session 时外部传入)
  - agent = session: agent 关闭即 session 结束, finalize 里 commit 归档

agent 侧只持有 self._ov 一个实例 + 调用点:
  - run() 启动调 init_async(kshell_session_id)
  - react() 里调 tick_and_maybe_push(items)  (只 add_message, 不 commit)
  - run() finally 调 finalize(items)  (推剩余 + commit 归档 + close)
  - Read/Write/Glob/Grep 工具映射 viking:// → ov_read/ov_write/ov_glob/ov_grep handler
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional

from routine.logger import setup_logger

_log = setup_logger('shared.ov_memory')

_CURSOR_FILE = 'ov_cursor.json'


class OVMemory:
    """OpenViking 长期记忆推送封装 (跨 agent 共享).

    失败不阻断主流程:init 失败 → enabled=False,后续调用全跳过.

    peer_id 由调用方指定 (如 claudecode 用 'claude', react_agent 用 'react'),
    OV 后端按 peer_id 把记忆卡片归档到 peers/{peer_id}/ 下.
    """

    def __init__(
        self,
        config: dict[str, Any] | None,
        workspace: Path | None = None,
        *,
        peer_id: str = 'claude',
    ) -> None:
        self.client: Any = None
        # OV session_id 跟 kshell session_id 1:1 对齐 (外部传入, 不自动生成)
        self.session_id: str | None = None
        self._task: asyncio.Task | None = None
        self._init_task: asyncio.Task | None = None
        # 按 msg_id 对齐 (而非 index): 压缩后 _items 变短, index 错位, msg_id 不变.
        # _last_pushed_id = 最后推到 OV 的消息 _ov_id (None = 还没推过).
        self._last_pushed_id: str | None = None
        self._push_every_n: int = 5
        self._turn_count: int = 0
        self._workspace = workspace
        self._peer_id = peer_id
        self._pending_config: dict[str, Any] | None = config

    async def init_async(self, kshell_session_id: str) -> None:
        """非阻塞初始化 OV client + 用 kshell session_id 创建 OV session.

        网络请求 (initialize + get_session) 在后台 task 跑, 不阻塞 agent 启动.
        跑完前 enabled=False, tick 跳过推送 (消息不丢, 下次 tick 推 _items 全部增量).
        跑完设 self.client + self.session_id, 后续 tick 自动开始推.
        失败只 log warning, self.client 保持 None, 后续全跳过.

        调用方应 await 此方法以等待 task 创建完成 (不等网络请求完成).
        """
        config = self._pending_config
        self._pending_config = None
        if not config:
            return
        api_key = config.get('api_key') or os.environ.get('OPENVIKING_API_KEY')
        if not api_key:
            _log.warning('ov_config set but no api_key (env OPENVIKING_API_KEY missing), OV disabled')
            return
        # 先记录 session_id, 这样 enabled 检查只需看 client
        self.session_id = kshell_session_id

        async def _bg_init():
            try:
                c = await asyncio.to_thread(self._build_client, config, api_key, kshell_session_id)
                self.client = c
                self._push_every_n = int(config.get('push_every_n_turns', 5))
                _log.info('ov initialized (peer=%s, ov_session=%s)',
                          self._peer_id, kshell_session_id)
            except Exception as exc:
                _log.warning('ov init failed: %s (OV disabled)', exc)
                self.client = None
                self.session_id = None

        self._init_task = asyncio.create_task(_bg_init())

    @staticmethod
    def _build_client(config: dict, api_key: str, session_id: str):
        from openviking.client import SyncHTTPClient
        c = SyncHTTPClient(
            url=config.get('url', 'https://api.vikingdb.cn-beijing.volces.com/openviking'),
            api_key=api_key,
            user=config.get('user', 'kshell'),
            timeout=float(config.get('timeout', 120.0)),
        )
        c.initialize()
        c.get_session(session_id, auto_create=True)
        return c

    async def finalize(self, items: list[dict] | None = None) -> None:
        """优雅关闭:推剩余消息 + 等在途 task + commit 归档 + 关闭 client.

        agent = session 模型: agent 关闭即 session 结束, commit 归档触发后端抽取记忆.
        commit 是 OV 归档的唯一触发点, finalize 是唯一调用方.
        """
        # 等 init task 完成 (如果 agent 创建后立即被 stop, init 可能还在跑)
        if self._init_task is not None and not self._init_task.done():
            try:
                await self._init_task
            except Exception:
                pass
        if not self.enabled:
            return
        sid = self.session_id
        # 1. 等在途推送完成 (不 cancel)
        if self._task is not None and not self._task.done():
            try:
                await self._task
            except Exception:
                pass
        # 2. 最后推一次剩余的消息 (只 add_message), 按 _ov_id 找增量
        if items is not None:
            remaining = self._find_incremental(items)
            if remaining:
                await self._push_async(remaining)
                self._update_last_id(remaining)
        # 3. commit 当前 session 归档 (agent 关闭 = session 结束 = 触发后端抽取记忆)
        if sid:
            try:
                def _commit():
                    self.client.commit_session(sid)
                await asyncio.to_thread(_commit)
                _log.info('ov committed session %s (archived)', sid)
            except Exception as exc:
                _log.warning('ov commit session %s failed: %s', sid, exc)
        # 4. 关闭 client
        try:
            await asyncio.to_thread(self.client.close)
        except Exception as exc:
            _log.warning('ov close failed: %s', exc)
        _log.info('ov finalized (peer=%s, session %s committed)',
                  self._peer_id, sid)

    @property
    def enabled(self) -> bool:
        """是否启用 (init 成功)."""
        return self.client is not None and self.session_id is not None

    # --- 文件操作 (供 Read/Write/Glob/Grep 工具映射 viking://) ---

    async def read(self, uri: str) -> str:
        """读取 viking:// 文件内容, 对齐本地 Read."""
        if not self.enabled:
            return '错误: OV 未启用'
        try:
            def _read():
                return self.client.read(uri)
            text = await asyncio.to_thread(_read)
            _log.info('ov read: %s (%d chars)', uri, len(text or ''))
            return text or '(文件为空)'
        except Exception as exc:
            _log.warning('ov read failed (%s): %s', uri, exc)
            return f'错误: 读取失败: {exc}'

    async def write(self, uri: str, content: str) -> str:
        """写入 viking:// 文件, 对齐本地 Write."""
        if not self.enabled:
            return '错误: OV 未启用'
        try:
            def _write():
                return self.client.write(uri, content)
            await asyncio.to_thread(_write)
            _log.info('ov write: %s (%d chars)', uri, len(content))
            return f'文件已写入: {uri}'
        except Exception as exc:
            _log.warning('ov write failed (%s): %s', uri, exc)
            return f'错误: 写入失败: {exc}'

    async def glob(self, pattern: str, uri: str = 'viking://') -> str:
        """glob 匹配 viking:// 路径, 对齐本地 Glob."""
        if not self.enabled:
            return '错误: OV 未启用'
        try:
            def _glob():
                return self.client.glob(pattern, uri=uri)
            resp = await asyncio.to_thread(_glob)
            entries = _parse_glob_resp(resp)
            if not entries:
                return 'No files found'
            _log.info('ov glob: pattern=%r uri=%s → %d files', pattern, uri, len(entries))
            return '\n'.join(entries)
        except Exception as exc:
            _log.warning('ov glob failed (%s): %s', uri, exc)
            return f'错误: glob 失败: {exc}'

    async def grep(self, pattern: str, uri: str = 'viking://') -> str:
        """文本搜索 viking:// 路径, 对齐本地 Grep."""
        if not self.enabled:
            return '错误: OV 未启用'
        try:
            def _grep():
                return self.client.grep(uri, pattern)
            resp = await asyncio.to_thread(_grep)
            lines = _parse_grep_resp(resp)
            if not lines:
                return 'No matches found'
            _log.info('ov grep: pattern=%r uri=%s → %d matches', pattern, uri, len(lines))
            return '\n'.join(lines)
        except Exception as exc:
            _log.warning('ov grep failed (%s): %s', uri, exc)
            return f'错误: grep 失败: {exc}'

    # --- OV 扩展指令 (超出标准文件操作, 通过 skill 引导 agent 使用) ---

    async def find(self, query: str, uri: str = 'viking://', limit: int = 10) -> str:
        """语义检索: 按自然语言查询匹配文件, 本地 grep 做不到."""
        if not self.enabled:
            return '错误: OV 未启用'
        try:
            def _find():
                return self.client.find(query=query, target_uri=uri, limit=limit)
            resp = await asyncio.to_thread(_find)
            items = _parse_find_resp(resp)
            if not items:
                return 'No matches found'
            _log.info('ov find: query=%r uri=%s → %d items', query, uri, len(items))
            return '\n'.join(items)
        except Exception as exc:
            _log.warning('ov find failed: %s', exc)
            return f'错误: find 失败: {exc}'

    async def peek(self, uri: str, level: int = 0) -> str:
        """分层读: level=0 读摘要(~100 token), level=1 读概览(~2k token).

        比 read 全文省 token, 适合先扫一眼再决定是否读全文.
        """
        if not self.enabled:
            return '错误: OV 未启用'
        try:
            if level == 0:
                def _peek():
                    return self.client.abstract(uri)
            else:
                def _peek():
                    return self.client.overview(uri)
            text = await asyncio.to_thread(_peek)
            _log.info('ov peek: %s level=%d (%d chars)', uri, level, len(text or ''))
            return text or '(空)'
        except Exception as exc:
            _log.warning('ov peek failed (%s): %s', uri, exc)
            return f'错误: peek 失败: {exc}'

    async def link(self, from_uri: str, to_uris: str, reason: str = '') -> str:
        """建立文件间引用关系: from_uri → to_uris."""
        if not self.enabled:
            return '错误: OV 未启用'
        try:
            def _link():
                return self.client.link(from_uri, to_uris, reason)
            await asyncio.to_thread(_link)
            _log.info('ov link: %s → %s', from_uri, to_uris)
            return f'已建立关系: {from_uri} → {to_uris}'
        except Exception as exc:
            _log.warning('ov link failed: %s', exc)
            return f'错误: link 失败: {exc}'

    async def relations(self, uri: str) -> str:
        """查询文件的关联关系."""
        if not self.enabled:
            return '错误: OV 未启用'
        try:
            def _relations():
                return self.client.relations(uri)
            resp = await asyncio.to_thread(_relations)
            lines = _parse_relations_resp(resp)
            if not lines:
                return 'No relations found'
            _log.info('ov relations: %s → %d items', uri, len(lines))
            return '\n'.join(lines)
        except Exception as exc:
            _log.warning('ov relations failed (%s): %s', uri, exc)
            return f'错误: relations 失败: {exc}'

    async def tree(self, uri: str = 'viking://') -> str:
        """递归列目录树, 比 ls 更直观."""
        if not self.enabled:
            return '错误: OV 未启用'
        try:
            def _tree():
                return self.client.tree(uri)
            resp = await asyncio.to_thread(_tree)
            lines = _parse_tree_resp(resp)
            if not lines:
                return '(空目录)'
            _log.info('ov tree: %s → %d entries', uri, len(lines))
            return '\n'.join(lines)
        except Exception as exc:
            _log.warning('ov tree failed (%s): %s', uri, exc)
            return f'错误: tree 失败: {exc}'

    async def stat(self, uri: str) -> str:
        """查文件元信息 (类型/大小/层级/标签)."""
        if not self.enabled:
            return '错误: OV 未启用'
        try:
            def _stat():
                return self.client.stat(uri)
            resp = await asyncio.to_thread(_stat)
            text = _format_stat_resp(resp)
            _log.info('ov stat: %s', uri)
            return text
        except Exception as exc:
            _log.warning('ov stat failed (%s): %s', uri, exc)
            return f'错误: stat 失败: {exc}'

    # --- 游标 (按 _ov_id 对齐, resume 不重推) ---

    def _find_incremental(self, items: list[dict]) -> list[dict]:
        """按 _ov_id 找增量: _last_pushed_id 之后的消息.

        - _last_pushed_id is None: 全部是增量 (首次推 / 压缩后 reset)
        - _last_pushed_id 在 items 中找到: 返回它之后的消息
        - 找不到 (压缩后该消息被删): 返回全部 (接受 retained 重复, 压缩不频繁)
        """
        if self._last_pushed_id is None:
            return list(items)
        for i, item in enumerate(items):
            if item.get('_ov_id') == self._last_pushed_id:
                return items[i + 1:]
        _log.info('ov cursor: last_id %s not in items (compacted?), pushing all',
                  self._last_pushed_id[:16])
        return list(items)

    def _update_last_id(self, pushed: list[dict]) -> None:
        """推送完成后, 记最后一条消息的 _ov_id 为新 cursor."""
        if not pushed:
            return
        last = pushed[-1]
        last_id = last.get('_ov_id')
        if last_id:
            self._last_pushed_id = last_id
            self._write_cursor(last_id)
            _log.info('ov cursor: last_pushed_id=%s', last_id[:16])

    def reset_cursor(self) -> None:
        """压缩后调: _items 被替换, 旧 _ov_id 可能不在新 _items 里.

        清掉 cursor, 下次 tick 推全部新 _items. 接受 retained 重复
        (压缩不频繁, OV 后端做语义去重).
        """
        self._last_pushed_id = None
        self._write_cursor(None)
        _log.info('ov cursor reset (compaction)')

    def load_cursor(self, items: list[dict]) -> None:
        """resume 时从游标文件恢复 _last_pushed_id; 首次启动后台回灌全部历史.

        - 有游标且 _ov_id 在 items 中: 从该 id 之后推增量
        - 有游标但 _ov_id 不在 items 中 (压缩后): 推全部
        - 无游标(首次): spawn 后台 task 推全部历史

        items: 调用方传入的当前全量消息列表, 每条带 _ov_id.
        """
        cursor = self._read_cursor()
        if cursor is None:
            _log.info('ov cursor: no file, backfilling %d history messages', len(items))
            # 先占位防 tick 期间重复推: 设为最后一条的 _ov_id
            if items:
                self._last_pushed_id = items[-1].get('_ov_id')
            else:
                self._last_pushed_id = None
            if items and (self._task is None or self._task.done()):
                self._task = asyncio.create_task(self._backfill_async(items))
            return
        last_id = cursor.get('last_pushed_id')
        self._last_pushed_id = last_id
        # 验证 last_id 是否在 items 中
        if last_id:
            found = any(item.get('_ov_id') == last_id for item in items)
            if found:
                _log.info('ov cursor: resume after id %s', last_id[:16])
            else:
                _log.info('ov cursor: id %s not in items (compacted?), will push all',
                          last_id[:16])
        else:
            _log.info('ov cursor: resume with null id, will push all')

    async def _backfill_async(self, messages: list[dict]) -> None:
        """首次启动后台推送全部历史对话, 推完写 cursor."""
        await self._push_async(messages)
        self._update_last_id(messages)
        _log.info('ov backfill done: pushed %d message(s)', len(messages))

    def _read_cursor(self) -> dict | None:
        if not self._workspace:
            return None
        p = self._workspace / _CURSOR_FILE
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except Exception as exc:
            _log.warning('ov cursor read failed: %s', exc)
            return None

    def _write_cursor(self, last_id: str | None) -> None:
        if not self._workspace:
            return
        p = self._workspace / _CURSOR_FILE
        try:
            p.write_text(
                json.dumps({'last_pushed_id': last_id}, ensure_ascii=False),
                encoding='utf-8',
            )
        except Exception as exc:
            _log.warning('ov cursor write failed: %s', exc)

    # --- 推送 ---

    async def _push_async(self, messages: list[dict]) -> None:
        """后台增量 add_message (to_thread 包装,不阻塞 event loop,不 commit).

        OV 规范: 会话过程中只 add_message, 不 commit; commit 只在会话边界
        (finalize) 触发一次, 避免后端反复抽取 + L0/L1/L2 重算.

        工具调用上传 (ToolPart):
        - claudecode: _items 里有独立 function_call/function_call_output 项
          (type 字段, 无 role), 按 call_id 聚合成 ToolPart, 作为独立
          assistant 消息推送 (时序正确, 后端仍能提取 tools/skills 记忆).
        - react_agent: assistant 消息的 feedback 字段 (list[dict]) 含
          {name, result, is_error, input}, 转 ToolPart 跟 TextPart 一起推
          (feedback 本就附在 assistant 上, 自然同消息).
        """
        if not self.enabled or not messages:
            return
        try:
            def _push():
                # 先聚合 claudecode 的 function_call + function_call_output
                # (按 call_id 匹配 name/arguments -> output)
                tool_map: dict[str, dict] = {}
                for item in messages:
                    t = item.get('type')
                    if t == 'function_call':
                        cid = item.get('call_id', '')
                        tool_map.setdefault(cid, {})
                        tool_map[cid]['name'] = item.get('name', '')
                        tool_map[cid]['arguments'] = item.get('arguments', '')
                    elif t == 'function_call_output':
                        cid = item.get('call_id', '')
                        tool_map.setdefault(cid, {})
                        tool_map[cid]['output'] = item.get('output', '')

                for item in messages:
                    role = item.get('role')
                    if role not in ('user', 'assistant'):
                        continue
                    content = item.get('content', '')
                    # react_agent 的 [feedback] 是工具结果伪用户消息, 不是真实
                    # 用户输入, 推到 OV 会导致后端把它当对话内容抽取记忆卡片
                    # (语义错位). 跳过, 只推真实对话.
                    if role == 'user' and content.startswith('[feedback]'):
                        continue
                    # kind='summary' 是上下文压缩摘要 (内部生成, 非真实对话),
                    # 推到 OV 会污染记忆卡片. 跳过.
                    if item.get('kind') == 'summary':
                        continue

                    parts: list[dict] = []
                    if content:
                        parts.append({"type": "text", "text": content})

                    # react_agent: assistant 消息的 feedback 字段含工具结果,
                    # 转 ToolPart 跟 TextPart 一起推
                    if role == 'assistant':
                        feedback = item.get('feedback')
                        if feedback and isinstance(feedback, list):
                            for fb in feedback:
                                if not isinstance(fb, dict):
                                    continue
                                tool_part: dict = {
                                    "type": "tool",
                                    "tool_name": str(fb.get('name', '')),
                                    "tool_output": str(fb.get('result', '')),
                                    "tool_status": (
                                        'error' if fb.get('is_error')
                                        else 'completed'
                                    ),
                                }
                                if fb.get('input') is not None:
                                    tool_part['tool_input'] = fb['input']
                                parts.append(tool_part)

                    if not parts:
                        continue
                    self.client.add_message(
                        self.session_id, role,
                        parts=parts,
                        peer_id=self._peer_id,
                    )

                # claudecode: 聚合的 function_call/output 作为独立 assistant
                # 消息推 (只含 ToolPart). 虽然跟引发它的 assistant 文本分开,
                # 但时序正确 (在文本之后, 下一轮之前), 后端记忆提取不受影响.
                for cid, tool in tool_map.items():
                    tool_part: dict = {
                        "type": "tool",
                        "tool_id": cid,
                        "tool_name": tool.get('name', ''),
                        "tool_output": tool.get('output', ''),
                        "tool_status": 'completed',
                    }
                    arguments = tool.get('arguments', '')
                    if arguments:
                        try:
                            tool_part['tool_input'] = json.loads(arguments)
                        except Exception:
                            tool_part['tool_input'] = {'raw': arguments}
                    self.client.add_message(
                        self.session_id, 'assistant',
                        parts=[tool_part],
                        peer_id=self._peer_id,
                    )
            await asyncio.to_thread(_push)
            # 明确打印上传了哪些 msg (反映 OV 实际结构: user/assistant + 聚合的 tool)
            for m in messages:
                role = m.get('role') or m.get('type', '?')
                oid = str(m.get('_ov_id', ''))[:12]
                if role in ('user', 'assistant'):
                    content = str(m.get('content', ''))[:60].replace('\n', ' ')
                    _log.info('ov ↑ %s: id=%s content=%s', role, oid, content)
                elif role == 'function_call':
                    _log.info('ov ↑ tool(asst): id=%s name=%s call_id=%s',
                              oid, m.get('name', ''), str(m.get('call_id', ''))[:12])
                elif role == 'function_call_output':
                    out = str(m.get('output', ''))[:60].replace('\n', ' ')
                    _log.info('ov ↑ tool_output(asst): id=%s call_id=%s output=%s',
                              oid, str(m.get('call_id', ''))[:12], out)
            _log.info('ov add_message %d item(s) -> OV (no commit)', len(messages))
        except Exception as exc:
            _log.warning('ov push failed: %s', exc)

    def tick_and_maybe_push(self, items: list[dict]) -> None:
        """每轮调用,内部计数到 N 时增量 add_message (不 commit).

        按 _ov_id 找增量 (压缩后 _items 变短也不会错位).
        上一个推送未完成则跳过 (防积压).
        commit 留给会话边界 (finalize).

        items: 调用方传入的当前全量消息列表, 每条带 _ov_id.
        """
        if not self.enabled:
            return
        self._turn_count += 1
        if self._turn_count < self._push_every_n:
            return
        self._turn_count = 0
        if self._task is not None and not self._task.done():
            return  # 上一个还没推完,跳过防积压
        new_msgs = self._find_incremental(items)
        if not new_msgs:
            return
        # 先更新 cursor 防止 tick 期间重复推 (task 异步, 可能延迟)
        self._update_last_id(new_msgs)
        self._task = asyncio.create_task(self._push_async(new_msgs))

def _parse_glob_resp(resp: Any) -> list[str]:
    """解析 OV glob 返回, 提取 URI 路径列表."""
    if not isinstance(resp, dict):
        return []
    # OV glob 返回 {files: [{uri, ...}, ...]} 或类似结构
    files = resp.get('files') or resp.get('entries') or resp.get('items') or []
    if not isinstance(files, list):
        return []
    out: list[str] = []
    for it in files:
        if isinstance(it, dict):
            uri = it.get('uri') or it.get('path') or it.get('name') or ''
            if uri:
                out.append(uri)
        elif isinstance(it, str):
            out.append(it)
    return out


def _parse_grep_resp(resp: Any) -> list[str]:
    """解析 OV grep 返回, 提取匹配行."""
    if not isinstance(resp, dict):
        return []
    # OV grep 返回 {matches: [{uri, line, text, ...}, ...]} 或类似结构
    matches = resp.get('matches') or resp.get('results') or resp.get('items') or []
    if not isinstance(matches, list):
        return []
    out: list[str] = []
    for it in matches:
        if isinstance(it, dict):
            uri = it.get('uri') or it.get('path') or ''
            text = it.get('text') or it.get('line') or it.get('content') or ''
            line_no = it.get('line_number') or it.get('line') or ''
            if uri and text:
                out.append(f'{uri}:{line_no}:{text}' if line_no else f'{uri}:{text}')
            elif text:
                out.append(text)
        elif isinstance(it, str):
            out.append(it)
    return out


def _parse_find_resp(resp: Any) -> list[str]:
    """解析 OV find 返回, 提取 URI + 摘要."""
    if not isinstance(resp, dict):
        return []
    items = resp.get('memories') or resp.get('resources') or resp.get('skills') or resp.get('items') or []
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for it in items:
        if isinstance(it, dict):
            uri = it.get('uri') or it.get('path') or ''
            abstract = it.get('abstract') or it.get('overview') or it.get('content') or ''
            score = it.get('score', 0.0)
            if uri:
                line = f'{uri}'
                if abstract:
                    line += f' — {abstract[:200]}'
                if score:
                    line += f' (score={score:.2f})'
                out.append(line)
    return out


def _parse_relations_resp(resp: Any) -> list[str]:
    """解析 OV relations 返回."""
    if isinstance(resp, list):
        items = resp
    elif isinstance(resp, dict):
        items = resp.get('relations') or resp.get('items') or resp.get('links') or []
    else:
        return []
    out: list[str] = []
    for it in items:
        if isinstance(it, dict):
            uri = it.get('uri') or it.get('to') or it.get('target') or ''
            reason = it.get('reason') or it.get('relation') or ''
            if uri:
                out.append(f'{uri}' + (f' — {reason}' if reason else ''))
        elif isinstance(it, str):
            out.append(it)
    return out


def _parse_tree_resp(resp: Any) -> list[str]:
    """解析 OV tree 返回, 递归展平."""
    out: list[str] = []
    def _walk(node: Any, prefix: str = ''):
        if isinstance(node, dict):
            name = node.get('name') or node.get('uri') or node.get('path') or ''
            etype = node.get('type') or ''
            if name:
                marker = '/' if etype in ('directory', 'dir', 'folder') else ''
                out.append(f'{prefix}{name}{marker}')
            children = node.get('children') or node.get('items') or []
            new_prefix = prefix + '  '
            for child in children:
                _walk(child, new_prefix)
        elif isinstance(node, list):
            for item in node:
                _walk(item, prefix)
    _walk(resp)
    return out


def _format_stat_resp(resp: Any) -> str:
    """格式化 OV stat 返回为可读文本."""
    if not isinstance(resp, dict):
        return str(resp)
    lines = []
    for key in ('uri', 'type', 'size', 'level', 'tags', 'mtime', 'created_at'):
        val = resp.get(key)
        if val is not None:
            lines.append(f'{key}: {val}')
    # 其他字段
    for key, val in resp.items():
        if key not in ('uri', 'type', 'size', 'level', 'tags', 'mtime', 'created_at') and val is not None:
            lines.append(f'{key}: {val}')
    return '\n'.join(lines) if lines else '(无信息)'


