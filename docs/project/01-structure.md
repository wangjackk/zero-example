# 01 · 项目结构与启动

本文档描述 `zero/` 应用的目录结构、routine 注册约定、两种启动模式,以及与 `kernel` 的协作关系。

> 框架级 API 见 [../framework/](../framework/);本文档只讲 `zero` 项目特定的约定。

## 目录结构

```
zero/
├── main.py                   # 应用入口:注册 routines + 打 banner + 起 server/client
├── shell.py                  # 业务侧编排 Shell(模块自动串并行,对标老版 Go Shell)
├── pyproject.toml            # 依赖声明(uv + path 依赖 routine)
├── modules/
│   └── __init__.py           # 全局 module 常量(OUTPUT/UI/AUDIO/BODY)+ get_modules()
├── routines/
│   ├── __init__.py           # 顶层聚合:test + user 两组(core 已搬到 one/)
│   ├── banner.py             # 启动 banner 打印(routine / module 列表)
│   ├── test/                 # 测试/demo 型 routine(开发期验证用)
│   │   ├── echo.py           # Echo:回显示例(骨架验证)
│   │   ├── boom.py           # Boom:抛异常,验 error 透传
│   │   ├── compose.py        # Compose:编排多个子 routine
│   │   ├── force_demo.py     # ForceDemo:验 force_start 抢占
│   │   ├── auto_demo.py      # AutoDemo:验 auto-start passive
│   │   └── ...
│   └── user/                 # 业务 routine(实际功能)
│       ├── wait.py           # Wait:barrier 同步点(Shell 编排用)
│       ├── http_server.py    # HttpServer:HTTP+WS 前门(curl 触发 routine + WS 桥接前端)
│       ├── ask.py            # Ask:向用户提问(审批/选项)
│       ├── dance.py          # Dance:demo(占 output 模块)
│       ├── print_heart/      # PrintHeart:GUI demo
│       ├── music/            # 音乐播放(占 audio 模块)
│       ├── query_weather/    # 天气查询(外部 API + 缓存)
│       ├── xml/              # XML 嵌套编排(legacy 兼容)
│       ├── react_agent/      # ReactAgent:reactive agent + sqlite memory
│       ├── claudecode/       # claudecode agent + 内置工具集 + skills 子系统
│       └── dag/              # DAG 编排子系统(run_dag + approval + cancel + translator)
├── frontend/                 # Vue3 + Vite 前端(独立 bun 项目)
└── doc/                      # 本目录:接口使用文档
```

## module 体系

`zero/modules/__init__.py` 定义全局互斥 module 常量:

| 常量 | 值 | 用途 |
|---|---|---|
| `MODULE_OUTPUT` | `'output'` | 输出/显示设备(屏 / UI) |
| `MODULE_UI` | `'ui'` | UI 交互通道 |
| `MODULE_AUDIO` | `'audio'` | 音频播放设备 |
| `MODULE_BODY` | `'body'` | body 帧流(async generator yield) |

`get_modules()` 返回所有 module 名列表,kernel 启动时挂 module.tree 用。

**routine 占模块靠 `on_created()` 返回 `Modules([...])`**——同一 module 同时只能被一个 started routine 占。冲突判定走 `ctx.conflict(a, b)`(cone 交集),由 Shell 编排器消费。

## routine 注册约定

### 三层聚合

`zero/routines/__init__.py` 顶层聚合三组,顺序无关(passive 与非 passive 的依赖靠 `req` 重试解决,不靠注册顺序):

```python
def get_routines() -> Routines:
    routines = Routines()
    routines.register(core_routines())     # 基础设施(supervisor 等)
    routines.register(test_routines())     # 测试 / demo
    routines.register(user_routines())     # 业务
    return routines
```

每组返回 `Routines` 实例(`routine.register` 接受 `Routines` 组会自动 flatten)。

### 组内注册:文件即 routine

每个 routine 一个文件,组 `__init__.py` 聚合注册:

```python
# zero/routines/test/__init__.py
from routine import Routines
from .echo import Echo
from .boom import Boom
# ...

def get_routines() -> Routines:
    rs = Routines()
    rs.register(Boom, Test, Compose, ForceDemo, ...)
    return rs
```

### 复杂子系统:子 Routines 组

复杂子系统(dag / claudecode / react_agent / music / query_weather)用 `Routines` 组打包,顶层 `register` 自动 flatten:

```python
# zero/routines/user/dag/__init__.py
routines = Routines()
routines.register(RunDag, DagApproval, DagCancel, TranslateArchon, ...)

# zero/routines/user/__init__.py
from .dag import (
    RunDag, DagApproval, DagCancel, TranslateArchon,
    Echo, MergeWeather, SummaryWeather, FlakyTask, AlwaysFail,
)

rs.register(RunDag, DagApproval, DagCancel, TranslateArchon, ...)
```

或直接传子组:

```python
rs.register(claudecode_routines)   # Routines 实例,自动 flatten
rs.register(react_agent_routines)
```

### routine 命名约定

- `Routine.name` 默认由类名 snake_case 转换生成(`__init_subclass__` 自动)。
- 大写 name(如 `name = 'WAIT'`)表示特殊语义 routine——Shell 编排器识别 `wait` / `WAIT` 当 barrier 处理。
- per-agent 动态注册的 routine name 带 agent 前缀(如 `agent_a/list_skills`),避免全局重名。

### `meta` 字段约定

| key | 类型 | 含义 |
|---|---|---|
| `description` | `str` | 给 LLM / 用户看的简短说明 |
| `input_schema` | `dict` | pydantic `model_json_schema()`,LLM function-calling 用 |
| `hidden` | `bool` | 隐藏(不在 banner / 列表显示,如内部 supervisor) |
| `tool` | `bool` | 标记为 agent 工具(给 claudecode agent 发现用) |
| `readonly` | `bool` | 只读(plan 模式放行) |
| `concurrency_safe` | `bool` | 可与其它工具并行 |

## 启动模式

`zero/main.py` 支持两种启动模式,跟 kernel 的 `config.yaml` 两段配置对应:

### server 模式(默认)

zero 当 gRPC server 监听,kernel 用 `as_grpc_client` 连过来。

```bash
uv run python -m zero.main                      # 默认 0.0.0.0:7777
uv run python -m zero.main 127.0.0.1:50071       # argv 覆盖监听地址
```

适用场景:kernel 在远端 / kernel 想主动连接 zero。

### client 模式(`--client`)

zero 当 gRPC client,拨 kernel 的 `as_grpc_server` 监听地址。kernel config 需配 `as_grpc_server.enable: true`。

```bash
uv run python -m zero.main --client 127.0.0.1:50051
```

适用场景:kernel 是稳定服务端,zero 是客户端(可多个 zero 连同一 kernel)。

**业务层(`RoutineHub`)两模式共用**,只换 transport。代码不感知:

```python
async def serve(addr: str, *, client: bool = False) -> None:
    routines = get_routines()
    modules = get_modules()
    print_banner(routines, modules)

    if client:
        await start_client(routines=routines, modules=modules, address=addr)
    else:
        await start_server(routines=routines, modules=modules, address=addr)
```

### 启动时序

1. `_reconfigure_stdio_utf8()` —— Windows 下强制 stdout/stderr UTF-8(避免 emoji / 中文乱码)。
2. `get_routines()` —— 聚合所有 routine 类(无实例化,只存类)。
3. `get_modules()` —— 拿 module 名表。
4. `print_banner(routines, modules)` —— 打印启动 banner。
5. `start_client` / `start_server` —— 起 routine hub,跟 kernel 建 gRPC Stream,进 main loop。
6. kernel 收到连接后:
   - 推 `module.tree`(全量 module 拓扑)。
   - 收到 zero 的 `catalog.push`(全量 routine 路由)。
   - 对每个 `is_passive=True` 的 routine 发 `lifecycle.start`(auto-start passive),
     其中 `HttpServer` 被拉起后自动开 HTTP+WS 监听(默认 7780)。

## passive routine 的角色

`is_passive=True` 的 routine 由 kernel 在连接建立后**自动拉起**(单实例常驻),不需要外部触发。`zero` 里典型的 passive routine:

| routine | 作用 |
|---|---|
| `HttpServer`(`user/http_server.py`) | HTTP+WS 前门:curl 触发任意 routine + WS 桥接前端通信 |
| `ClaudeCodeAgents`(`user/claudecode/manager.py`) | claudecode agent 全局 manager(spawn 子 agent) |
| `ReactAgents`(`user/react_agent/manager.py`) | react_agent 全局 manager |

基础设施 host 见 `one/`(跟 zero 对等的独立进程)。passive routine 通常是"基础设施"或"manager",业务 routine 通过 `submit+start` 或 `req` 触发。

## manager + child 模式

`zero` 里 agent 类 routine(claudecode / react_agent)走 **manager + child** 模式:

- **manager**:passive 常驻,kernel auto-start。持有 `@request` handler(`create_agent` / `list_agents` / `stop_agent`)。
- **child**:非 passive,由 manager 在收到 `create_agent` req 时 `submit+start` 一个子 routine 实例。
- **隔离**:每个 child 独立 `agent_id`,自带 pubsub namespace + session,互不干扰。
- **生命周期**:manager 持有 live child 的 `RoutineHandle`,可 cascade-stop;child 死了 manager 收 `lifecycle.stopped` 回执。

```
┌──────────────────────────────────────────────────────────┐
│  kernel (auto-start passive on connect)                  │
│      │                                                    │
│      ▼ lifecycle.start                                    │
│  ┌──────────────────┐    req('create_agent')             │
│  │ ClaudeCodeAgents │ ←─────────────── 前端 / bridge      │
│  │  (passive mgr)   │                                    │
│  │                  │ submit+start                       │
│  │  handles: {      │ ──────────────┐                    │
│  │    agent_a: ...  │               ▼                    │
│  │    agent_b: ...  │          ┌──────────────┐          │
│  │  }               │          │ ClaudeCodeAgent│         │
│  └──────────────────┘          │  (child)      │          │
│                                │  agent_id=b   │          │
│                                └──────────────┘          │
└──────────────────────────────────────────────────────────┘
```

## per-agent 动态 routine 注册

`zero` 支持运行时为每个 agent 动态注册 per-agent skill routine(如 `agent_a/list_skills`),workspace 在实例化时绑定,实现 agent 间隔离。

详见框架文档 [../framework/03-registration.md](../framework/03-registration.md#运行时注册)。

## 编排:Shell

`zero/shell.py` 提供 `Shell` 类,业务侧模块自动串并行编排器(对标老版 Go `shell_scheduler_go/shell/shell.go`)。

```python
from zero.shell import Shell

async def run(self, kwargs):
    shell = Shell(self)                       # self 是当前 routine 实例
    h1 = await shell.push('ui_noop', {'n': 'first'})
    h2 = await shell.push('quick', {'msg': 'parallel'})
    shell.complete()
    results = await shell.join()
```

- **串并行**:每条命令跟左兄弟判 `ctx.conflict`(cone 交集)——冲突串行,不冲突并行。
- **barrier**:`name == 'wait'` 的命令是全局同步点——等所有左兄弟完成后自己跑,自己跑完后再放行右兄弟。
- **失败不中断后继**:`join()` 收集成结果列表(`StartError` / 异常 / 正常值),不抛。

详见 [zero/shell.py](../../shell.py) 文件头 docstring。

## 下一步

- routine 编写约定:[02-routine-conventions.md](./02-routine-conventions.md)
- 业务 routine 模块清单:[03-modules-overview.md](./03-modules-overview.md)
