"""OvRelations ---- OV 记忆系统操作."""
from __future__ import annotations

from typing import Any, ClassVar, Dict

from pydantic import BaseModel, Field
from routine import Routine

from zero.routines._shared._paths import AGENT_ID_KEY
from .prompt import DESCRIPTION


class OvRelationsInput(BaseModel):
    uri: str = Field(description="要查询的 viking:// URI 记忆卡片")


class OvRelationsOutput(BaseModel):
    content: str = Field(description="返回结果文本")


class OvRelations(Routine):
    """OV OvRelations 操作."""

    meta: ClassVar[Dict[str, Any]] = {
        'input_schema': OvRelationsInput.model_json_schema(),
        'output_schema': OvRelationsOutput.model_json_schema(),
        'description': DESCRIPTION,
    }

    async def run(self, kwargs: Dict[str, Any]) -> str:
        agent_id = str(kwargs.pop(AGENT_ID_KEY, None) or "")
        if not agent_id:
            return "错误: 无法定位当前 agent, OV 操作不可用."
        rid_resp = await self.call('get_agent_rid', {'agent_id': agent_id})
        agent_rid = rid_resp.get('rid') if rid_resp.get('ok') else None
        if not agent_rid:
            return "错误: 无法定位 agent rid, OV 操作不可用."

        inp = OvRelationsInput(**kwargs)
        data = {'uri': inp.uri}

        try:
            resp = await self.req(agent_rid, 'ov_relations', data, timeout=60.0)
        except Exception as exc:
            return f"错误: OV OvRelations 操作失败: {type(exc).__name__}: {exc}"
        if not isinstance(resp, dict):
            return f"错误: OV OvRelations 操作返回异常: {resp!r}"
        if not resp.get("ok"):
            err = resp.get("error", "unknown")
            return f"错误: OV OvRelations 操作失败: {err}"
        return resp.get("text", "")
