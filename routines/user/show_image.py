"""ShowImage -- 在前端对话流里展示一张图片.

跟 ``ask`` 类似的 UI routine,但不需要等用户响应:读图片文件 → base64 →
req 到 HttpServer → 广播 ``show_image`` 消息到前端,前端在当前 agent
对话流里渲染 ``<img>``.

用法::

    # 代码
    await self.call('show_image', {'path': 'chart.png'})
    await self.call('show_image', {'path': 'plot.png', 'caption': '销量趋势'})

    # XML
    <show_image path="chart.png"/>
    <show_image path="plot.png" caption="销量趋势"/>
"""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any, ClassVar, Dict

from pydantic import BaseModel, Field
from routine import Routine

from zero.routines._shared._paths import AGENT_ID_KEY, resolve_optional_tool_path

_BRIDGE_NAME = 'web_server'

_MIME_OVERRIDES = {
    '.svg': 'image/svg+xml',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.bmp': 'image/bmp',
}


class ShowImageInput(BaseModel):
    path: str = Field(description='图片文件路径 (相对项目根或绝对路径)')
    caption: str = Field(
        default='',
        description='图片说明文字 (可选), 显示在图片下方',
    )


class ShowImage(Routine):
    """读图片文件, 推到前端对话流渲染."""

    meta: ClassVar[Dict[str, Any]] = {
        'description': '在前端对话流展示一张图片 (支持 png/jpg/svg/gif/webp/bmp).',
        'input_schema': ShowImageInput.model_json_schema(),
    }

    async def run(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        agent_id = kwargs.pop(AGENT_ID_KEY, '')
        inp = ShowImageInput(**kwargs)
        self._logger.info('show_image called: path=%r agent_id=%r', inp.path, agent_id)

        # 解析路径 (相对 project_root)
        project_root = None
        if agent_id:
            try:
                state = await self.call('fetch_agent_state', {'agent_id': agent_id})
                project_root = state.get('project_root')
            except Exception:
                pass

        resolved = Path(resolve_optional_tool_path(None, project_root)) / inp.path
        if not resolved.is_absolute():
            resolved = Path(inp.path).resolve()
        self._logger.info('show_image resolved: %s exists=%s', resolved, resolved.is_file())
        if not resolved.is_file():
            raise FileNotFoundError(f'show_image: file not found: {inp.path}')

        # 读 + base64
        data = resolved.read_bytes()
        b64 = base64.b64encode(data).decode('ascii')

        # 推断 mime
        suffix = resolved.suffix.lower()
        mime = _MIME_OVERRIDES.get(suffix) or mimetypes.guess_type(str(resolved))[0] or 'image/png'

        # req 到 HttpServer 广播到前端
        bridge_id = await self._find_bridge_id()
        self._logger.info('show_image bridge_id=%s', bridge_id)
        if bridge_id is None:
            raise RuntimeError(f'show_image: bridge routine {_BRIDGE_NAME!r} not running')

        await self.ctx.req(bridge_id, 'show_image', {
            'agent_id': agent_id,
            'image': b64,
            'mime': mime,
            'caption': inp.caption,
            'filename': resolved.name,
        }, timeout=10.0)

        size_kb = len(data) / 1024
        self._logger.info('show_image done: %s (%s, %.1f KB)', resolved.name, mime, size_kb)
        return {
            'for_llm': f'图片已显示: {resolved.name} ({mime}, {size_kb:.1f} KB)',
        }

    async def _find_bridge_id(self) -> str | None:
        try:
            routines = await self.ctx.get_running_routines()
        except Exception:
            return None
        for r in routines:
            if str(r.get('name') or '') == _BRIDGE_NAME:
                rid = str(r.get('id') or '').strip()
                if rid:
                    return rid
        return None
