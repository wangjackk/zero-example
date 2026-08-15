# kshell 文档索引

本仓库的 dev 文档分两层,放在两个位置:

- **`routine/docs/`** —— routine SDK 框架级 API(通用,与业务无关)。任何用 `routine` 包的应用都适用。
- **`zero/docs/project/`** —— zero 项目级约定与业务模块清单(特定于本仓 `zero/` 应用)。

## Agent 入口:两个 skill

| skill | 范围 | skill 目录 | 文档位置 |
|---|---|---|---|
| **`routine-sdk`** | 框架级 API(通用) | [builtin/routine-sdk/SKILL.md](../routines/user/claudecode/skills/builtin/routine-sdk/SKILL.md) | `routine/docs/` |
| **`zero-dev`** | zero 项目级(本仓特定) | [builtin/zero-dev/SKILL.md](../routines/user/claudecode/skills/builtin/zero-dev/SKILL.md) | `zero/docs/project/` |

agent 通过 `list_skills` 发现、`load_skill <name>` 加载。SKILL.md 只放**章节目录 + 按问题类型快速定位**,agent 根据当前问题主动 Read 对应章节。

**人类开发者**继续直接读 markdown;**agent** 走 skill 入口。单一真理源,无重复维护。

## 阅读顺序

### 第一次接触框架(`routine/docs/`)

| # | 文档 | 内容 |
|---|---|---|
| 01 | [routine/docs/01-overview.md](../../routine/docs/01-overview.md) | 架构概览:routine hub / kernel / transport 三方关系,两种启动模式,wire 事件分层 |
| 02 | [routine/docs/02-routine.md](../../routine/docs/02-routine.md) | `Routine` 基类:`run` / `stop` / `on_created` / `on_started` / `on_stopped` 生命周期 + `name` / `meta` / `is_passive` 类字段 |
| 03 | [routine/docs/03-registration.md](../../routine/docs/03-registration.md) | `Routines.register/deregister` + `RoutineHub.register_routine/deregister_routine` + `catalog.register/catalog.deregister` 事件同步 |
| 04 | [routine/docs/04-context.md](../../routine/docs/04-context.md) | `RunContext` API:lifecycle ack / 模块操作 / p2p 通信 / pubsub / 子 routine 编排 |
| 05 | [routine/docs/05-handle.md](../../routine/docs/05-handle.md) | `RoutineHandle`:submit/start/stop/wait + async generator body 迭代 |
| 06 | [routine/docs/06-errors.md](../../routine/docs/06-errors.md) | 异常类型对照 + 可恢复性 + `lifecycle.stopped` reason 枚举 |
| ref | [routine/docs/module-operations.md](../../routine/docs/module-operations.md) | 模块操作完整参考(acquire/release/force_acquire/force_release/load_module/unload_module/conflict) |

### 接手 zero 项目(`zero/docs/project/`)

| # | 文档 | 内容 |
|---|---|---|
| 01 | [project/01-structure.md](./project/01-structure.md) | 目录结构 + routine 注册约定 + 启动模式 + passive routine + manager+child 模式 |
| 02 | [project/02-routine-conventions.md](./project/02-routine-conventions.md) | routine 编写约定:pydantic schema first / 生命周期钩子 / 错误处理 / 日志 / per-agent workspace 隔离 |
| 03 | [project/03-modules-overview.md](./project/03-modules-overview.md) | 50 个业务 routine 模块清单 + "按能力查找"索引 |
| 04 | [project/04-end-to-end.md](./project/04-end-to-end.md) | 全流程案例:实现并调用一个 routine(冷注册/热注册 + 跨 routine 调用) |

## 文档约定

- 所有接口签名以 **`routine/routine/`** 当前实现为准,文档同步更新。
- 框架级文档跟框架代码同仓(`routine/docs/` ↔ `routine/routine/`),项目级文档跟项目代码同仓(`zero/docs/` ↔ `zero/routines/`)。
- 文档只写 **"接口契约 + 为什么这么设计"**,不写完整实现。实现交给代码。
- 跨文档引用用相对路径,代码引用标注文件位置。
- 涉及 wire 事件的,Python 侧常量在 `routine/routine/protocol.py`,Go 侧在 `kernel/conn/events.go`。
