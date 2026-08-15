"""OvLink ---- OV 记忆系统操作."""
from __future__ import annotations

from typing import Any, ClassVar, Dict

from pydantic import BaseModel, Field
from routine import Routine

from zero.routines._shared._paths import AGENT_ID_KEY
from .prompt import DESCRIPTION


class OvLinkInput(BaseModel):
    from_uri: str = Field(description="源记忆卡片 viking:// URI")
    to_uris: str = Field(description="目标卡片 URI，多个用空格/逗号分隔")
    reason: str = Field(description="建立关联的理由/语义描述")


class OvLinkOutput(BaseModel):
    content: str = Field(description="返回结果文本")


class OvLink(Routine):
    """OV OvLink 操作."""

    meta: ClassVar[Dict[str, Any]] = {
        'input_schema': OvLinkInput.model_json_schema(),
        'output_schema': OvLinkOutput.model_json_schema(),
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

        inp = OvLinkInput(**kwargs)
        data = {'from_uri': inp.from_uri, 'to_uris': inp.to_uris, 'reason': inp.reason}

        try:
            resp = await self.req(agent_rid, 'ov_link', data, timeout=60.0)
        except Exception as exc:
            return f"错误: OV OvLink 操作失败: {type(exc).__name__}: {exc}"
        if not isinstance(resp, dict):
            return f"错误: OV OvLink 操作返回异常: {resp!r}"
        if not resp.get("ok"):
            err = resp.get("error", "unknown")
            return f"错误: OV OvLink 操作失败: {err}"
        return resp.get("text", "")
