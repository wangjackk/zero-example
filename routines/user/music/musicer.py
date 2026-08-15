"""musicer -- 根据用户描述挑一首合适的曲子并播放.

流程:
1. 读 ``assets/meta.json`` 作为歌单(name → tags).
2. 把歌单 + 用户 00_prompt 拼成提示词,``scope.push_and_wait('inference_call', ...)``
   请 LLM 输出曲名.
3. 容错地把 LLM 原始输出对齐到歌单里的 name(严格/去噪/子串三级兜底).
4. ``scope.push_and_wait('music', kwargs={'name': ...})`` 放完或被打断.

Musicer 生命 = 选 + 放,被打断时由 scope 级联取消 music(→ ffplay 被 stop() 杀掉).
"""

import json
from pathlib import Path
from typing import Any, ClassVar, Dict
# from re import T

from pydantic import BaseModel, Field
from routine3 import Routine


_ASSETS_DIR = Path(__file__).parent / 'assets'
_META_PATH = _ASSETS_DIR / 'meta.json'


def _load_catalog() -> dict[str, dict]:
    if not _META_PATH.exists():
        return {}
    try:
        data = json.loads(_META_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _build_messages(catalog: dict, user_prompt: str) -> list[dict]:
    lines = [
        f"- {name}: tags = {meta.get('tags', []) if isinstance(meta, dict) else []}"
        for name, meta in catalog.items()
    ]
    catalog_text = '\n'.join(lines) if lines else '(empty)'
    system = (
        "你是一个选曲助手.根据用户描述的情绪 / 场景 / 风格,从下方歌单里挑最合适的一首.\n\n"
        f"歌单:\n{catalog_text}\n\n"
        "只输出曲名(必须严格等于歌单中某个 name 字段),不要任何解释,前后缀,标点或换行."
    )
    return [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user_prompt},
    ]


def _resolve_name(raw: str, catalog: dict) -> str:
    """把 LLM 原始输出对齐到 catalog 中的 name.严格 → 去噪 → 子串."""
    if raw in catalog:
        return raw
    norm = raw.strip().strip('"\'`..,; \n\r\t')
    if norm in catalog:
        return norm
    lower = norm.lower()
    for name in catalog:
        if name.lower() == lower:
            return name
    for name in catalog:
        if name.lower() in lower or lower in name.lower():
            return name
    raise ValueError(f'LLM output "{raw}" does not match any song in catalog')


class MusicerInput(BaseModel):
    prompt: str = Field(default='', description='用户对曲子的情绪/场景/风格描述')


class MusicerOutput(BaseModel):
    name: str = Field(description='实际选中的曲名 (catalog 中的 name)')


class Musicer(Routine):
    """选曲 + 播放 ---- 根据情绪/场景描述,从本地歌单挑一首并播放.

    用法::
        <musicer 00_prompt="欢快的儿童向电子乐"/>
    """

    meta: ClassVar[Dict[str, Any]] = {
        'hidden': True,
        'description': '根据情绪/场景描述, 从本地歌单挑一首并播放.',
        'input_schema': MusicerInput.model_json_schema(),
        'output_schema': MusicerOutput.model_json_schema(),
    }
    async def run(self, kwargs: Dict[str, Any]) -> dict:
        prompt = kwargs.get('prompt', '')
        if not prompt:
            raise ValueError('00_prompt parameter is required')

        catalog = _load_catalog()
        if not catalog:
            raise RuntimeError(f'no music catalog at {_META_PATH}')

        messages = _build_messages(catalog, prompt)
        self._logger.info(f'musicer: select for "{prompt}" from {list(catalog.keys())}')

        h = await self.push_and_wait(
            'inference_call', kwargs={'messages': messages},
        )
        result = h.result
        raw = (result or {}).get('content', '').strip() if isinstance(result, dict) else ''
        name = _resolve_name(raw, catalog)
        self._logger.info(f'musicer: picked "{name}" (raw="{raw}")')

        await self.push_and_wait('music', kwargs={'name': name})
        return {'name': name}
