# 04 · 全流程案例:实现并调用一个 routine

本章把"怎么写 / 怎么注册 / 怎么调用"串起来,适合第一次接手 zero 项目的开发者。**简单 routine 看这一篇就够了**,觉得不够时再翻框架级章节(各节末尾有链接)。

样例对应真实业务代码 [zero/routines/user/music/play_music.py](../../routines/user/music/play_music.py),可直接对照阅读。

## 步骤 1 — 写 routine

文件 `zero/routines/user/music/play_music.py`:

```python
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from routine import Routine, Modules
from zero.modules import MODULE_AUDIO
from .wav_player import create_wav_player


class PlayMusicInput(BaseModel):
    name: str = Field(default='Found-My-Way', description='音乐名(assets/ 下的文件名,不含扩展名)')
    duration: Optional[float] = Field(default=10, description='播放秒数;>0 播指定秒数,0 播整首')


class PlayMusic(Routine):
    """按 name 播放音乐,body 派生子(如 dance)边放边跑."""

    meta = {
        'description': '按 name 播放本地音乐',
        'input_schema': PlayMusicInput.model_json_schema(),
    }

    def __init__(self):
        super().__init__()
        self._player = None

    async def on_created(self, rid, kwargs):
        # 占 audio 模块:多个 PlayMusic 串行,不会同时放两首.
        # body 子(如 dance)占 body 模块,跟 audio 不冲突,父子并发.
        return Modules([MODULE_AUDIO])

    async def run(self, kwargs):
        inp = PlayMusicInput(**kwargs)
        await self._stop_previous()
        self._player = create_wav_player(self._logger)
        await self._player.play(_resolve(inp.name), inp.duration)

    async def stop(self):
        player = self._player
        if player is None:
            return
        self._player = None
        await player.stop()
```

要点:
- **`run` 是 abstractmethod**,必须 override;`stop` / `on_created` 等可选。
- **`on_created` 返回 `Modules([...])` 声明占用模块**;不 override 或返回 `None` 表示不占模块。
- **`meta` 自由扩展**,`input_schema` 给前端 / LLM 工具调用用。
- 详见 [routine/docs/02-routine.md](../../../routine/docs/02-routine.md)。

## 步骤 2 — 注册(两条路径)

> **新 routine 写到哪里?** 写到 `one/routines/`。`zero/` 是意识主体(agent 自己不能重启自己),只保留核心 agent;`one/` 是跟 zero 对等的独立 host 进程,zero 重启不影响 one,routine 更新都放这里。下面的静态注册示例用的是 `zero/routines/user/music/`,只是因为 `PlayMusic` 是 zero 自带的业务 routine;**新写的 routine 应放 `one/routines/`**。

### 路径 A:冷注册(需重启进程)

在 `zero/routines/user/music/__init__.py` 聚合(或 `one/routines/__init__.py`):

```python
from .list_music import ListMusic
from .play_music import PlayMusic
from routine import Routines

def get_routines() -> Routines:
    rs = Routines()
    rs.register(PlayMusic, ListMusic)
    return rs
```

在 `zero/routines/user/__init__.py` 接进全量聚合:

```python
rs.register(music_routines())   # 已含 PlayMusic
```

进程启动时 `zero/main.py` 调 `get_routines()` → `start_client(routines=..., hub_id='zero')`,框架自动发 `catalog.push`(带 `hub_id`)全量同步给 kernel。`hub_id` 是进程级身份(必填,如 `zero`/`one`),kernel 校验唯一性。**改 routine 代码后必须重启进程**(类是模块加载时定义的)。

### 路径 B:热注册(不重启)

LLM 在对话中写一个 `.py` 文件,然后调用 `register_routine` 工具(见 [RegisterRoutineTool.py](../../routines/user/claudecode/tools/RegisterRoutineTool/RegisterRoutineTool.py)):

```python
# 1. 把 routine 类写到磁盘(假设 path = /tmp/my_routine.py)
# 2. 调 register_routine 工具
await self.call('register_routine', {'file_path': '/tmp/my_routine.py'})
# 工具内部:importlib 加载文件 → 收集 Routine 子类 → ctx.hub.register_routine(*classes)
#   → 本地 Routines.register + catalog.register wire 事件 → kernel 回 ok=true 才落表
# 返回 {'registered': ['my_routine'], 'file_path': ..., 'module_name': ...}
```

移除走 `deregister_routine` 工具:

```python
await self.call('deregister_routine', {'name': 'my_routine'})
# 两跳流程:kernel → cmd → 本地 dereg → cmd.ack → kernel 删路由
```

reload 走 `reload_routine`(同名覆盖语义)。完整的端到端测试见 [zero/routines/test/reg_dereg_test.py](../../routines/test/reg_dereg_test.py),HTTP 一键触发:

```bash
curl -XPOST localhost:7780/run/reg_dereg_test -H 'Content-Type: application/json' -d '{}'
```

详见 [routine/docs/03-registration.md](../../../routine/docs/03-registration.md)。

## 步骤 3 — 调用

routine 在 `run()` 里用 `self.call` / `self.submit` 调用其它已注册 routine(跨进程也行,框架自动路由):

```python
class Orchestrator(Routine):
    async def run(self, kwargs):
        # 同步拿结果:submit + start + wait 一步到位
        result = await self.call('play_music', {'name': 'Found-My-Way', 'duration': 5})

        # 或:submit + start + 流式 wait(子 routine 是 async generator 时可 yield 多个结果)
        handle = await self.submit('play_music', {'name': 'Found-My-Way'})
        await handle.start()
        async for chunk in handle:
            ...   # 收子 routine yield 的流式结果
        await handle.wait()
```

详见 [routine/docs/04-context.md](../../../routine/docs/04-context.md) 和 [routine/docs/05-handle.md](../../../routine/docs/05-handle.md)。

## 速查:注册路径差异

| 路径 | 改代码后 | 何时生效 |
|---|---|---|
| **冷注册**(改 `__init__.py` + 重启进程) | 改源码 → 重启进程 | 进程起来后立即可调 |
| **热注册**(`register_routine`) | 写 `.py` 文件 + 调 API | 返回后立即可调 |
| **热移除**(`deregister_routine`) | 调 API | 返回后路由消失 |

## 下一步

- 写完 routine 想深入理解生命周期 / 类字段:[routine/docs/02-routine.md](../../../routine/docs/02-routine.md)
- 注册机制细节:[routine/docs/03-registration.md](../../../routine/docs/03-registration.md)
- `run()` 体里能调什么 API:[routine/docs/04-context.md](../../../routine/docs/04-context.md)
- 编排子 routine(handle / 流式结果):[routine/docs/05-handle.md](../../../routine/docs/05-handle.md)
- 异常处理 / 排错:[routine/docs/06-errors.md](../../../routine/docs/06-errors.md)
