"""list_music - 列出本地音乐 assets/ 里可用的曲名 + tags.

给 LLM 选曲用:返回 ``{'for_llm': '...'}`` 让 react agent 把曲单喂回 LLM,
LLM 据此决定下一轮调 ``<music name="..."/>``.不占模块(纯读盘,只读 meta.json).
"""
import json
from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel

from routine import Routine

_ASSETS_DIR = Path(__file__).parent / 'assets'
_META_PATH = _ASSETS_DIR / 'meta.json'


def _load_catalog() -> Dict[str, Dict[str, Any]]:
    """读 assets/meta.json (name -> {tags}).缺失/损坏返空 dict."""
    if not _META_PATH.exists():
        return {}
    try:
        data = json.loads(_META_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _list_audio_files() -> list[str]:
    """列 assets/ 下可直接播放的音频文件名(不含扩展名)."""
    exts = {'.wav', '.mp3', '.flac', '.ogg', '.m4a'}
    names = []
    for p in sorted(_ASSETS_DIR.iterdir()):
        if p.suffix.lower() in exts:
            names.append(p.stem)
    return names


class ListMusicInput(BaseModel):
    """无参数 -- 只列出全部曲单.留空 schema 让 agent 渲染 ``<list_music/>`` 示例."""
    pass


class ListMusic(Routine):
    """列出可用曲单(name + tags).供 LLM 选曲时参考."""

    meta = {
        'description': '列出本地音乐曲单 (name + tags), 供选曲参考.无参数.',
        'input_schema': ListMusicInput.model_json_schema(),
    }

    async def run(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        catalog = _load_catalog()
        audio_files = _list_audio_files()
        # 以 meta.json 为准;缺失 meta 的音频文件补空 tags.
        if not catalog and not audio_files:
            return {'for_llm': '(曲单为空)'}
        lines = []
        names = list(catalog.keys())
        for name in audio_files:
            if name not in catalog:
                names.append(name)
                catalog[name] = {}
        for name in names:
            tags = catalog.get(name, {}).get('tags', [])
            tag_str = ', '.join(tags) if tags else '(无标签)'
            lines.append(f'- {name}: {tag_str}')
        listing = '\n'.join(lines)
        self._logger.info(f'list_music: {len(names)} songs')
        return {'songs': names, 'for_llm': listing}
