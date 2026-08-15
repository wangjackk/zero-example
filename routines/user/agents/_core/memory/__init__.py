"""记忆系统 provider 抽象.

统一实现 LocalContextProvider: 本地 sqlite + condenser_agent 压缩.
OV 作为可选增强挂载 (同步备份 + 长期记忆查询), 不参与 resume/压缩.

agent 只持 ContextProvider 接口, 不感知后端.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def build_context_provider(
    *,
    ov_config: dict[str, Any] | None,
    writer: Any,
    workspace: Path | None,
    max_items: int = 80,
    peer_id: str = 'claude',
) -> tuple[Any, Any]:
    """构造 ContextProvider.

    返回 (ctx, ov_fs):
      - ctx: LocalContextProvider (带可选 OV 增强)
      - ov_fs: OVMemory 实例 (用于 viking:// 文件操作), None if 未启用 OV
    """
    from .local import LocalContextProvider
    if ov_config:
        from zero.routines._shared.ov_memory import OVMemory
        ov = OVMemory(ov_config, workspace, peer_id=peer_id)
        ctx = LocalContextProvider(
            writer=writer, max_items=max_items, ov=ov,
        )
        return ctx, ov
    ctx = LocalContextProvider(writer=writer, max_items=max_items)
    return ctx, None
