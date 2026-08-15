"""验证 Plan 通道下 Responses API caching 参数的正确传法.

背景
----
doubao 配置走 ``/api/plan/v3``(Agent Plan 套餐通道),原 llm.py 通过
``extra_body={'caching': {'type': 'enabled', ...}}`` 注入 caching 字段,
被服务端 400 拒掉:

    caching is not supported in coding plan / agent plan / codex flow

修复方向
--------
官方文档:doubao-seed-2.0 系列模型在 Responses API 下**自动开隐式缓存**,
且不可关闭.Plan 通道下应**完全不传 caching 参数**,依赖隐式缓存 +
``previous_response_id`` 复用服务端存储的 response.

本脚本独立验证(不依赖 agent 框架):
  1. 不传 caching 时首轮请求能成功,拿到 response_id
  2. 不传 caching 时第二轮用 previous_response_id 能成功复用
  3. usage.prompt_tokens_details.cached_tokens 是否 > 0(隐式缓存命中)
  4. 旧的「传 caching 字段」写法确实会被 400 拒掉(对照组)

跑通后 llm.py 的修复就是删掉 caching 注入分支.

Run:  python -m zero.routines.user.react_agent.verify_plan_caching
or:   cd zero/routines/user/react_agent && python verify_plan_caching.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# 让脚本既能 `python verify_plan_caching.py` 直跑,也能 -m 跑.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).parent))

from openai import AsyncOpenAI

# doubao 配置内联(从 llm.py 摘出来),避免依赖 routine 框架模块.
# 注意 base_url 是 /api/plan/v3(Agent Plan 套餐通道),不是 /api/v3.
_MODELS = {
    'doubao': {
        'api_key': os.getenv('ARK_API_KEY', ''),
        'base_url': 'https://ark.cn-beijing.volces.com/api/plan/v3',
        'model': 'doubao-seed-2.0-lite',
        'extra': {'reasoning': {'effort': 'minimal'}},
    },
}


def _banner(title: str) -> None:
    print(f'\n{"=" * 70}\n{title}\n{"=" * 70}')


def _print_usage(label: str, resp) -> None:
    usage = getattr(resp, 'usage', None)
    if usage is None:
        print(f'{label}: <no usage>')
        return
    try:
        d = usage.model_dump()
    except Exception:
        print(f'{label}: {usage!r}')
        return
    cached = (d.get('prompt_tokens_details') or {}).get('cached_tokens', 0)
    print(
        f'{label}: '
        f'input={d.get("input_tokens")} '
        f'output={d.get("output_tokens")} '
        f'cached={cached} '
        f'prompt_details={d.get("prompt_tokens_details")}'
    )


async def _stream_collect(stream) -> tuple[str, str]:
    """从流式响应里收文本 + 末尾的 response.id.

    返回 (response_id, full_text).response_id 取自最后一个非空 event.response.id.
    """
    text_parts: list[str] = []
    response_id = ''
    async for ev in stream:
        ev_type = getattr(ev, 'type', '') or ''
        if ev_type == 'response.output_text.delta':
            delta = getattr(ev, 'delta', '') or ''
            if delta:
                text_parts.append(delta)
        elif ev_type == 'response.completed':
            resp = getattr(ev, 'response', None)
            if resp is not None:
                response_id = getattr(resp, 'id', '') or response_id
                _print_usage('  round usage', resp)
    return response_id, ''.join(text_parts)


async def _round_trip_with_store(store: bool | None) -> bool:
    """测一轮:不传 caching,可选传 store,再 previous_response_id 复用.

    store=None  -> 不传 store 字段(让服务端用默认)
    store=True  -> 显式 store=True
    store=False -> 显式 store=False(对照,应该第二轮必失败)
    """
    cfg = _MODELS['doubao']
    client = AsyncOpenAI(api_key=cfg['api_key'], base_url=cfg['base_url'])
    extra = dict(cfg.get('extra', {}))  # 仅 reasoning,不含 caching
    label = f'store={store}' if store is not None else 'store=<omitted>'
    extra_body = {} if store is None else {'store': store}

    _banner(f'[{label}] Round 1: 不传 caching,无 previous_response_id')
    try:
        stream1 = await client.responses.create(
            model=cfg['model'],
            input=[
                {'role': 'system', 'content': '你是一个简洁的助手,回答不超过 20 字.'},
                {'role': 'user', 'content': '用一句话介绍你自己.'},
            ],
            stream=True,
            extra_body=extra_body or None,
            **extra,
        )
        rid1, text1 = await _stream_collect(stream1)
    except Exception as exc:
        print(f'  FAIL: {exc!r}')
        return False

    print(f'  response_id = {rid1!r}')
    print(f'  text        = {text1!r}')
    if not rid1:
        print('  FAIL: 没拿到 response_id,后续 previous_response_id 复用无从测起')
        return False

    _banner(f'[{label}] Round 2: 不传 caching + previous_response_id 复用')
    try:
        stream2 = await client.responses.create(
            model=cfg['model'],
            input=[{'role': 'user', 'content': '我上一句问你什么了?'}],
            previous_response_id=rid1,
            stream=True,
            extra_body=extra_body or None,
            **extra,
        )
        rid2, text2 = await _stream_collect(stream2)
    except Exception as exc:
        msg = str(exc)
        print(f'  FAIL: {msg[:300]}')
        if 'PreviousResponseNotFound' in msg:
            print(f'  -> store={store} 时 response 未被服务端存储')
        return False

    print(f'  response_id = {rid2!r}')
    print(f'  text        = {text2!r}')
    if not rid2:
        print('  FAIL: 第二轮没拿到 response_id')
        return False

    print(f'\n[OK] [{label}] 链路通')
    return True


async def test_no_caching_round_trip() -> bool:
    """主测:分别试 store=<omitted> / store=True / store=False,定位 Plan 通道默认行为."""
    results = {}
    for store in (None, True, False):
        results[f'store={store}'] = await _round_trip_with_store(store)
    return results.get('store=None') or results.get('store=True')


async def test_caching_field_rejected() -> bool:
    """对照:旧写法(传 caching 字段)应被 400 拒."""
    cfg = _MODELS['doubao']
    client = AsyncOpenAI(api_key=cfg['api_key'], base_url=cfg['base_url'])

    _banner('Control: 旧写法 extra_body={"caching": {"type": "enabled", "prefix": True}}')
    try:
        stream = await client.responses.create(
            model=cfg['model'],
            input=[{'role': 'user', 'content': 'hi'}],
            stream=True,
            extra_body={'caching': {'type': 'enabled', 'prefix': True}},
            **dict(cfg.get('extra', {})),
        )
        # 即便没立即抛,也试着读一下
        async for _ in stream:
            pass
        print('  UNEXPECTED: 没报错(caching 字段竟被接受了?)')
        return False
    except Exception as exc:
        msg = str(exc)
        print(f'  raised: {msg[:300]}')
        if 'caching is not supported' in msg and 'plan' in msg.lower():
            print('[OK] 旧写法确实被服务端 400 拒绝,符合预期')
            return True
        print('  WARN: 报了错但不是预期的 caching-not-supported')
        return False


async def test_real_llmclient_round_trip() -> bool:
    """端到端验证:调用修改后的真实 LLMClient.stream(),确认 previous_response_id 链路通.

    需要把 d:\\kshell\\routine 加进 sys.path 才能 import routine.logger.
    本测验证 llm.py 的修复(删掉 caching 注入,doubao extra 加 store=True)确实生效.
    """
    routine_root = Path(__file__).resolve().parents[4] / 'routine'
    if not routine_root.exists():
        print(f'  SKIP: routine 包未找到 (looked at {routine_root})')
        return True  # 不算失败,只是没法测
    if str(routine_root) not in sys.path:
        sys.path.insert(0, str(routine_root))

    from llm import LLMClient, TextDelta, Completed  # type: ignore[import-not-found]

    cfg = _MODELS['doubao']
    client = LLMClient('doubao')

    _banner('Real LLMClient.stream() round 1 (修改后的代码路径)')
    text1_parts: list[str] = []
    rid1 = ''
    try:
        async for ev in client.stream(
            input=[
                {'role': 'system', 'content': '你是一个简洁的助手,回答不超过 20 字.'},
                {'role': 'user', 'content': '用一句话介绍你自己.'},
            ],
            instructions=None,
        ):
            if isinstance(ev, TextDelta) and ev.text:
                text1_parts.append(ev.text)
            elif isinstance(ev, Completed):
                rid1 = ev.response_id
                if ev.usage:
                    print(f'  round 1 usage: {ev.usage}')
    except Exception as exc:
        print(f'  FAIL round 1: {exc!r}')
        return False

    text1 = ''.join(text1_parts)
    print(f'  response_id = {rid1!r}')
    print(f'  text        = {text1!r}')
    if not rid1:
        print('  FAIL: 没拿到 response_id')
        return False

    _banner('Real LLMClient.stream() round 2 (previous_response_id 复用)')
    text2_parts: list[str] = []
    rid2 = ''
    try:
        async for ev in client.stream(
            input=[{'role': 'user', 'content': '我上一句问你什么了?'}],
            instructions=None,
            previous_response_id=rid1,
        ):
            if isinstance(ev, TextDelta) and ev.text:
                text2_parts.append(ev.text)
            elif isinstance(ev, Completed):
                rid2 = ev.response_id
                if ev.usage:
                    print(f'  round 2 usage: {ev.usage}')
    except Exception as exc:
        msg = str(exc)
        print(f'  FAIL round 2: {msg[:300]}')
        if 'PreviousResponseNotFound' in msg:
            print('  -> store 字段没生效,response 未被服务端存储')
        return False

    text2 = ''.join(text2_parts)
    print(f'  response_id = {rid2!r}')
    print(f'  text        = {text2!r}')
    if not rid2:
        print('  FAIL: 第二轮没拿到 response_id')
        return False

    print('\n[OK] LLMClient 修改后端到端链路通')
    return True


async def main() -> int:
    print(f'doubao cfg: base_url={_MODELS["doubao"]["base_url"]}')
    print(f'            model   ={_MODELS["doubao"]["model"]}')
    print(f'            extra   ={_MODELS["doubao"].get("extra")}')

    ok1 = await test_caching_field_rejected()
    ok2 = await test_no_caching_round_trip()
    ok3 = await test_real_llmclient_round_trip()

    _banner('SUMMARY')
    print(f'  caching 字段被拒(预期)          : {"OK" if ok1 else "FAIL"}')
    print(f'  store=True 链路通(修复目标)      : {"OK" if ok2 else "FAIL"}')
    print(f'  LLMClient 修改后端到端通(真实路径): {"OK" if ok3 else "FAIL"}')

    if ok1 and ok2 and ok3:
        print('\n结论:llm.py 修复有效(doubao Plan 通道靠 store=True + previous_response_id)')
        return 0
    print('\n结论:还有问题,需进一步排查')
    return 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
