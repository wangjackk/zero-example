"""LocalContextProvider — 本地 sqlite + condenser_agent 实现.

持有内存态消息列表 (_items), 通过 SessionWriter 持久化到 sqlite,
压缩走 condenser_agent routine (跨 wire).

OV 作为可选增强挂载: 开启时做同步备份 (tick + finalize) + 长期记忆查询 (find).
不参与 resume 还原和上下文压缩 — 本地 DB 始终是 source of truth.

从 Conversation 拆出消息管理 + 持久化, 去掉 response_id 管理.
"""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from routine.logger import setup_logger

_log = setup_logger('claudecode.memory.local')


class LocalContextProvider:
    """本地上下文 provider: sqlite 持久化 + condenser 压缩.

    内存态 _items 是 Responses API input 格式 (跟旧 Conversation 一致).
    持久化通过 SessionWriter (append-only event log).

    OV 可选增强 (ov 非 None 时启用):
      - init_session: 建 OV 连接 + 对齐游标 (防 tick 重复推)
      - tick: 每 N 轮后台增量推 OV (不 commit)
      - finalize_session: 推剩余 + commit 归档 + close
      - find: OV 语义检索跨 session 记忆
    """

    def __init__(
        self,
        *,
        writer: Any,
        max_items: int | None = 80,
        ov: Any = None,
    ) -> None:
        self._writer = writer
        self._max_items = max_items
        self._items: list[dict] = []
        self._ov = ov  # None = 纯本地; 非 None = 本地 + OV 增强

    @property
    def enabled(self) -> bool:
        return True

    @property
    def ov(self) -> Any:
        """暴露底层 OVMemory 供 agent 做 viking:// 文件操作 (None if 未挂载)."""
        if self._ov is not None and self._ov.enabled:
            return self._ov
        return None

    # --- 生命周期 ---

    async def init_session(self, session_id: str) -> None:
        """Local 无需初始化 (EventLog 由 SessionStore.open replay).

        OV 增强时: 后台建连接 + 从游标文件恢复 cursor. 不阻塞 agent 启动.
        本地 DB 是 source of truth, resume 由 SessionStore replay 完成,
        OV 只需读游标防 tick 重复推 + 补推崩溃前未上传的增量.

        cursor 恢复在 OV init task 完成后自动执行 (不阻塞此处).
        """
        if self._ov is None:
            return
        await self._ov.init_async(session_id)
        # cursor 对齐延迟到 init 完成后执行 (非阻塞)
        items_snapshot = list(self._items)
        asyncio.create_task(self._ov_align_after_init(items_snapshot))

    async def _ov_align_after_init(self, items: list[dict]) -> None:
        """等 OV init task 完成后从游标文件恢复 cursor.

        游标文件记录 OV 端真实最后推送的 msg_id, tick 据此补推未上传的增量.
        本地有数据时也走 load_cursor —— 不能假设"本地有的 OV 也有"(崩溃场景 tick 可能没推完).
        """
        if self._ov is None or self._ov._init_task is None:
            return
        try:
            await self._ov._init_task
        except Exception:
            return
        if not self._ov.enabled:
            return
        self._ov.load_cursor(items)

    async def finalize_session(self) -> None:
        """Local 无需收尾 (EventLog 由 SessionWriter.close 管理).

        OV 增强时: 推剩余消息 + commit 归档 + close client.
        """
        if self._ov is None or not self._ov.enabled:
            return
        try:
            await self._ov.finalize(list(self._items))
        except Exception as exc:
            _log.warning('ov finalize failed: %r', exc)

    # --- 写入 ---
    # _ov_id 跟 DB 的 entry uuid 保持一致 (resume 后 replay 读 DB uuid, 必须对得上):
    #   user/assistant  → uuid4().hex (跟 store._entry_uuid 一致: 非FC/FCO 走随机)
    #   function_call   → call_id      (跟 store._entry_uuid 的 FC 分支一致)
    #   function_call_output → f'{call_id}_output' (跟 FCO 分支一致)

    def append_user(self, text: str) -> None:
        ov_id = uuid4().hex
        self._items.append({'role': 'user', 'content': text, '_ov_id': ov_id})
        if self._writer:
            self._writer.append({'type': 'user', 'content': text, 'uuid': ov_id})
        self._maybe_trim()

    def append_assistant(self, text: str) -> None:
        if not text:
            return
        ov_id = uuid4().hex
        self._items.append({'role': 'assistant', 'content': text, '_ov_id': ov_id})
        if self._writer:
            self._writer.append({'type': 'assistant', 'content': text, 'uuid': ov_id})

    def append_function_call(
        self, name: str, arguments: str, call_id: str,
    ) -> None:
        ov_id = call_id
        self._items.append({
            'type': 'function_call',
            'name': name,
            'arguments': arguments,
            'call_id': call_id,
            '_ov_id': ov_id,
        })
        if self._writer:
            self._writer.write_function_call(name, arguments, call_id)

    def append_function_output(
        self, call_id: str, output: str,
        raw_result: Any | None = None,
    ) -> None:
        ov_id = f'{call_id}_output'
        self._items.append({
            'type': 'function_call_output',
            'call_id': call_id,
            'output': output,
            '_ov_id': ov_id,
        })
        if self._writer:
            self._writer.write_function_output(call_id, output, raw_result)

    # --- 读取 ---

    def items(self) -> list[dict]:
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)

    # --- 持久化屏障 ---

    def flush(self) -> None:
        if self._writer:
            self._writer.flush()

    # --- 压缩 ---

    async def compact(
        self,
        *,
        agent_id: str,
        session_id: str,
        model_key: str,
        max_context: int,
        plan_mode: bool,
        condense_config: dict[str, Any],
        project_root: str | None,
        cwd: str | None,
        call: Any,
    ) -> dict[str, Any] | None:
        """flush → condenser_agent → store.replay → 替换 _items.

        压缩完全本地化 (走 condenser_agent), 与 OV 无关.
        返回 response_state (供 ResponseTracker 恢复) 或 None.
        """
        if plan_mode:
            return None
        if max_context <= 0:
            return None
        if len(self._items) < 2:
            return None

        # 1. flush 确保 DB 有最新消息
        self.flush()

        # 2. 调压缩 agent (走 wire, 跨 conn 路由)
        try:
            result = await call('condenser_agent', {
                'agent_id': agent_id,
                'session_id': session_id,
                'model_key': model_key,
                'strategy': 'hybrid',
                'config': condense_config,
            })
        except Exception as exc:
            _log.warning('condenser call failed: %s (skipping)', exc)
            return None

        if not isinstance(result, dict) or not result.get('condensed'):
            return None

        _log.info(
            'context condensed: %d -> %d tokens (strategy=%s)',
            result.get('tokens_before', 0),
            result.get('tokens_after', 0),
            result.get('strategy', ''),
        )

        # 3. 从 DB 重新加载 (replay 会走 compaction 投影)
        from ..store import get_store
        store = get_store()
        _, items, response_state = store.replay(
            agent_id, session_id,
            cwd=cwd,
            project_root=project_root,
            model=model_key,
            plan_mode=plan_mode,
        )
        self._items = list(items)
        # 压缩后 _items 被替换, 旧 _ov_id 可能不在新 _items 里 → reset OV cursor,
        # 下次 tick 推全部新 _items (接受 retained 重复, 压缩不频繁).
        if self._ov is not None and self._ov.enabled:
            self._ov.reset_cursor()
        return response_state

    # --- 长期记忆 ---

    async def find(self, query: str, limit: int = 5) -> str:
        """OV 语义检索; 未挂载 OV 时返回不支持."""
        if self._ov is not None and self._ov.enabled:
            return await self._ov.find(query, limit=limit)
        return '本地模式不支持语义检索'

    # --- 增量推送 ---

    def tick(self) -> None:
        """OV 增强时每轮调用, 内部按 N 轮后台增量推; 未挂载时 no-op."""
        if self._ov is not None and self._ov.enabled:
            self._ov.tick_and_maybe_push(list(self._items))

    # --- 内部 ---

    def load_items(self, items: list[dict]) -> None:
        """从 replay 结果加载内存态 (不触发 writer)."""
        self._items = list(items)
        self._maybe_trim()

    def _maybe_trim(self) -> None:
        """超出 max_items 时裁剪到最近 max_items 条 (从第一个 user/assistant 起)."""
        if not self._max_items or len(self._items) <= self._max_items:
            return
        drop = len(self._items) - self._max_items
        while drop < len(self._items):
            if self._items[drop].get('role') in ('user', 'assistant'):
                break
            drop += 1
        self._items = self._items[drop:]
