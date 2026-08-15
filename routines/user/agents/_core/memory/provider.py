"""ContextProvider — 上下文存取抽象.

职责:
  - 持有内存态消息列表 (_items)
  - 持久化 (Local: sqlite / Ov: OV session)
  - 上下文压缩 (Local: condenser / Ov: no-op)
  - 长期记忆检索 (Local: no-op / Ov: find)

agent 只依赖此接口; response_id 管理由 ResponseTracker 独立负责.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ContextProvider(Protocol):
    """上下文存取抽象.

    消息格式 (Responses API input items):
      {'role': 'user', 'content': str}
      {'role': 'assistant', 'content': str}
      {'type': 'function_call', 'name': str, 'arguments': str, 'call_id': str}
      {'type': 'function_call_output', 'call_id': str, 'output': str}
    """

    @property
    def enabled(self) -> bool:
        """是否启用."""
        ...

    # --- 生命周期 ---

    async def init_session(self, session_id: str) -> None:
        """启动时初始化 (Ov: 创建 client + session + 回灌; Local: no-op)."""
        ...

    async def finalize_session(self) -> None:
        """关闭时收尾 (Ov: 推剩余 + commit + close; Local: no-op)."""
        ...

    # --- 写入 (内存态 + 持久化) ---

    def append_user(self, text: str) -> None:
        """追加 user 消息."""
        ...

    def append_assistant(self, text: str) -> None:
        """追加 assistant 消息 (空文本跳过)."""
        ...

    def append_function_call(
        self, name: str, arguments: str, call_id: str,
    ) -> None:
        """追加 function_call."""
        ...

    def append_function_output(
        self, call_id: str, output: str,
        raw_result: Any | None = None,
    ) -> None:
        """追加 function_call_output."""
        ...

    # --- 读取 ---

    def items(self) -> list[dict]:
        """当前内存态消息列表 (Responses API input 格式)."""
        ...

    def __len__(self) -> int:
        """内存态消息条数."""
        ...

    # --- 持久化屏障 ---

    def flush(self) -> None:
        """阻塞直到所有入队写操作落盘."""
        ...

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
        """检查并执行压缩.

        返回 response_state (压缩后恢复用) 或 None (未压缩).
        压缩后 items() 会变, 调用方需用返回值重置 ResponseTracker.
        """
        ...

    # --- 长期记忆 ---

    async def find(self, query: str, limit: int = 5) -> str:
        """语义检索跨 session 记忆."""
        ...

    # --- 增量推送 (Ov: 推 session; Local: no-op) ---

    def tick(self) -> None:
        """每轮调用, 内部按策略决定是否增量推送."""
        ...
