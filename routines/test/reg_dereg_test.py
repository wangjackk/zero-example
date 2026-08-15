"""RegDeregTest ---- 端到端验证运行时 register/reload/deregister 流程.

通过 HTTP 前门一键测试刚实现的 reg/reload/dereg 两跳流程::

    curl -XPOST localhost:7780/run/reg_dereg_test -H 'Content-Type: application/json' -d '{}'

内部流程(每步记 pass/fail,任一步失败不中断,最后返汇总):
1. register 一个动态生成的 routine 类 → kernel ok=true,本地可见
2. register 同名 → RegisterError(同名一律 fail,不区分 conn)
3. reload 同名 → kernel ok=true(不区分 conn 覆盖),本地类被替换
4. deregister 该 name → 两跳:kernel→cmd→本地 dereg→cmd.ack→kernel 删路由+回执,
   返回被移除的类
5. deregister 不存在的 name → DeregisterError(name 不在 kernel 路由表)

测试用的 routine name 带 ``_test_regdereg_`` 前缀 + uuid,避免跟现有 routine 冲突.
测试 routine 本身受白名单保护(DeregisterRoutineTool 不能删它),且 name 独特不会
跟业务 routine 撞.
"""
from __future__ import annotations

import uuid
from typing import Any, ClassVar, Dict, List

from pydantic import BaseModel, Field
from routine import Routine
from routine.errors import DeregisterError, RegisterError, ReloadError


class RegDeregTestInput(BaseModel):
    name_suffix: str = Field(
        default='',
        description='可选:给测试 routine name 加后缀(避免并发测试撞名).默认随机 uuid.',
    )


class _DynRoutine(Routine):
    """被测的动态 routine:run 返回固定 ok.每次测试生成独立子类(name 不同)."""

    meta: ClassVar[Dict[str, Any]] = {'description': 'dynamic test routine'}


class RegDeregTest(Routine):
    """端到端测试 register/reload/deregister 两跳流程.

    通过 HTTP /run/reg_dereg_test 触发,返回每步的 pass/fail + 详细信息.
    """

    meta: ClassVar[Dict[str, Any]] = {
        'description': '测试运行时 register/reload/deregister 流程(HTTP 前门触发)',
    }

    async def run(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        suffix = kwargs.get('name_suffix') or uuid.uuid4().hex[:8]
        name = f'_test_regdereg_{suffix}'

        results: List[Dict[str, Any]] = []

        def _step(title: str, ok: bool, detail: Any = None) -> None:
            results.append({'step': title, 'ok': ok, 'detail': detail})

        # 拿 RoutineHub(经 ctx.hub Protocol,跟 RegisterRoutineTool 同路径)
        hub = self.ctx.hub
        if hub is None:
            return {
                'ok': False,
                'error': 'no RoutineHub on ctx.hub (ctx 未绑或 _io 类型不对)',
                'results': results,
            }

        # --- 动态生成两个 Routine 子类(name 相同,类不同,用于 reload 覆盖测试) ---

        def _make_cls(class_name: str, routine_name: str) -> type:
            """动态生成 Routine 子类,显式设 name(覆盖 __init_subclass__ 自动生成)."""
            cls = type(class_name, (_DynRoutine,), {
                'name': routine_name,
                'meta': {**_DynRoutine.meta, 'description': f'dynamic test {class_name}'},
            })
            return cls

        DynV1 = _make_cls('DynV1', name)
        DynV2 = _make_cls('DynV2', name)  # reload 用(同名不同类)

        # --- Step 1: register DynV1 → 期望成功 ---

        try:
            await hub.register_routine(DynV1)
            local_cls = hub.runtime.routines.get_routine(name)
            if local_cls is DynV1:
                _step('register DynV1', True, 'kernel ok=true, 本地已 register')
            else:
                _step('register DynV1', False,
                      f'本地类不匹配:expected {DynV1}, got {local_cls}')
        except Exception as exc:
            _step('register DynV1', False,
                  f'{type(exc).__name__}: {exc}')

        # --- Step 2: register 同名 DynV2 → 期望 RegisterError(同名一律 fail) ---

        try:
            await hub.register_routine(DynV2)
            _step('register 同名 DynV2', False,
                  '应抛 RegisterError 但未抛(同名应一律 fail)')
        except RegisterError as exc:
            _step('register 同名 DynV2', True,
                  f'RegisterError 符合预期: {exc}')
        except Exception as exc:
            _step('register 同名 DynV2', False,
                  f'应抛 RegisterError, 实际抛 {type(exc).__name__}: {exc}')

        # 确认本地仍是 DynV1(未被覆盖)
        local_cls = hub.runtime.routines.get_routine(name)
        if local_cls is DynV1:
            _step('register 同名后本地仍 DynV1', True, '本地未被覆盖(符合预期)')
        else:
            _step('register 同名后本地仍 DynV1', False,
                  f'本地类应为 DynV1, got {local_cls}')

        # --- Step 3: reload 同名 DynV2 → 期望成功(不区分 conn 覆盖) ---

        try:
            await hub.reload_routine(DynV2)
            local_cls = hub.runtime.routines.get_routine(name)
            if local_cls is DynV2:
                _step('reload DynV2 覆盖 DynV1', True,
                      'kernel ok=true, 本地已覆盖为 DynV2')
            else:
                _step('reload DynV2 覆盖 DynV1', False,
                      f'本地类应为 DynV2, got {local_cls}')
        except Exception as exc:
            _step('reload DynV2 覆盖 DynV1', False,
                  f'{type(exc).__name__}: {exc}')

        # --- Step 4: deregister name → 期望成功(两跳流程,返回被移除的类) ---

        try:
            removed = await hub.deregister_routine(name)
            if removed is DynV2:
                _step('deregister name', True,
                      '两跳流程完成, 返回被移除的类 DynV2')
            elif removed is None:
                _step('deregister name', True,
                      '两跳流程完成, 返回 None(请求者≠持有者时正常)')
            else:
                _step('deregister name', False,
                      f'返回类应为 DynV2, got {removed}')
            # 本地应已删
            local_cls = hub.runtime.routines.get_routine(name)
            if local_cls is None:
                _step('deregister 后本地已删', True, '本地 Routines 已移除')
            else:
                _step('deregister 后本地已删', False,
                      f'本地仍存在: {local_cls}')
        except Exception as exc:
            _step('deregister name', False,
                  f'{type(exc).__name__}: {exc}')

        # --- Step 5: deregister 不存在的 name → 期望 DeregisterError ---

        ghost_name = f'_test_regdereg_ghost_{suffix}'
        try:
            await hub.deregister_routine(ghost_name)
            _step('deregister 不存在 name', False,
                  '应抛 DeregisterError 但未抛')
        except DeregisterError as exc:
            _step('deregister 不存在 name', True,
                  f'DeregisterError 符合预期: {exc}')
        except Exception as exc:
            _step('deregister 不存在 name', False,
                  f'应抛 DeregisterError, 实际抛 {type(exc).__name__}: {exc}')

        # --- 汇总 ---
        passed = sum(1 for r in results if r['ok'])
        total = len(results)
        all_ok = passed == total
        return {
            'ok': all_ok,
            'passed': passed,
            'total': total,
            'test_name': name,
            'results': results,
            'for_llm': (
                f'RegDeregTest {"PASSED" if all_ok else "FAILED"}: '
                f'{passed}/{total} steps ok. '
                + '; '.join(
                    f'[{("✓" if r["ok"] else "✗")}] {r["step"]}' for r in results
                )
            ),
        }
