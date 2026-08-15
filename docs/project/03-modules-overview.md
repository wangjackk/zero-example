# 03 · 业务 Routine 模块清单

本文档列出 `zero` 项目内所有已注册的 routine,按子系统分组。给 dev agent 用:发现可用能力 / 查找入参 schema / 决定编排路径。

> 框架级 API 见 [../framework/](../framework/);编写约定见 [02-routine-conventions.md](./02-routine-conventions.md)。

## 总览

`zero/routines/__init__.py` 顶层聚合两组:

| 组 | 路径 | 角色 |
|---|---|---|
| `test` | `routines/test/` | 测试 / demo(开发期验证) |
| `user` | `routines/user/` | 业务 routine(实际功能) |

> 基础设施 host 见 `one/`(跟 zero 对等的独立进程)。

## test/ —— 测试 / demo

开发期验证型 routine,不是业务能力。验 error 透传 / run / force / 编排 / barrier 等特性。

| 类 | name | 模块 | 说明 |
|---|---|---|---|
| `Echo` | `echo` | `output` | 回显示例(骨架验证),收 text 原样返回 |
| `Test` | `test` | – | test,基础占位 |
| `Output2` | `output2` | `output` | output 占用 demo |
| `Quick` | `quick` | – | 快速 return demo(不占模块) |
| `AutoDemo` | `auto_demo` | – | AutoSP 自动串并行 demo |
| `AutoSP` | `auto_sp` | – | 自动串并行编排器(模块冲突→串行,否则→并行) |
| `Boom` | `boom` | – | start 抛异常,验 error 透传 |
| `Compose` | `compose` | – | run 子 routine 拿结果 |
| `DynamicDemo` | `dynamic_demo` | dynamic | modules 按 `kwargs.mode` 现算(`output`/`ui`/none) |
| `ForceDemo` | `force_demo` | – | force_start 抢占 demo(兄弟间横向 force) |
| `UINoop` | `ui_noop` | `ui` | ui noop(占 ui,秒退,AutoSP demo 用) |
| `WaitDemo` | `wait_demo` | – | wait barrier + duration demo |

## user/ 顶级 —— 通用业务 routine

| 类 | name | passive | 模块 | 说明 |
|---|---|---|---|---|
| `Ask` | `ask` | – | – | 给用户发单选题,等选择结果;支持 `allow_other` 自由输入。UI 弹窗不占 module(前端 `uiQueue` 串行)。 |
| `Wait` | `WAIT` | – | – | 延时 / barrier 节点。Shell 识别为 barrier——等所有左兄弟完成后再跑,跑完放行右兄弟。`duration=0` 立即返(纯 barrier)。 |
| `Dance` | `dance` | – | `body` | dance demo(占 body,`duration` 秒退出,PlayMusic 的 body 子) |
| `HttpServer` | `http_server` | ✅ | – | HTTP+WS 前门:curl 触发任意已注册 routine(`/run/{name}` 一步到位,`/start`+`/stop` 长跑型,`/docs` Swagger UI)+ WS 桥接前端(`/ws` 端点,框架事件 ↔ web 前端 JSON 协议)。 |

## user/print_heart/ —— GUI demo

| 类 | name | 模块 | 说明 |
|---|---|---|---|
| `PrintHeart` | `print_heart` | – | 弹出无边框透明桃心动画窗口,持续指定秒数。纯 UI routine,不占 module。 |

## user/query_weather/ —— 天气查询

| 类 | name | 模块 | 说明 |
|---|---|---|---|
| `QueryWeather` | `query_weather` | – | 查询指定城市的实况(base)或未来 3-4 天预报(all)天气,调高德 API + 本地缓存。 |

## user/music/ —— 音乐播放

| 类 | name | 模块 | 说明 |
|---|---|---|---|
| `PlayMusic` | `play_music` | `audio` | 按 name 播放本地音乐 |
| `ListMusic` | `list_music` | – | 列出本地音乐曲单(name + tags),无参数 |
| `Musicer` | `musicer` | – | 根据情绪/场景描述从本地歌单挑一首并播放(`hidden=True`) |

## user/xml/ —— XML 嵌套编排(legacy 兼容)

对标 XML body 编排。message 驱动,双 shell(normal + body)。

| 类 | name | 模块 | 说明 |
|---|---|---|---|
| `XmlRoutine` | `xml_routine` | – | XML body 编排器抽象基类 |
| `MockXmlSource` | `mock_xml_source` | – | self-driven XmlRoutine(流式随机分块 + self-close 子) |
| `Act` | `act` | – | agent 动作执行管线(XML body → 工具子 → 流式 yield 结果),`hidden=True` |
| `RunXml` | `run_xml` | – | 动态执行 XML 字符串(调试用),`hidden=True` |
| `PrintBody` | `print_body` | – | 收 message body 打印(最小叶子样板) |

## user/dag/ —— DAG 编排子系统

声明式 DAG 工作流:YAML 定义节点 + 依赖,RunDag 调度执行。详见 [user/dag/design/](../../routines/user/dag/design/) 设计文档。

| 类 | name | 模块 | 说明 |
|---|---|---|---|
| `RunDag` | `run_dag` | – | 执行指定名称的 DAG workflow,按就绪集并发调度节点。`hidden=True` |
| `DagApproval` | `dag_approval` | – | DAG 人工审批节点:暂停等 approve / reject,fail-closed。`hidden=True` |
| `DagCancel` | `dag_cancel` | – | 终止整个 DAG workflow(返回值哨兵跟父 RunDag 通信)。`hidden=True` |
| `TranslateArchon` | `translate_archon` | – | 把 Archon 工作流 YAML 翻译为本地 DAG YAML,保存到 `dags/archon/`。`hidden=True` |

**DAG demo routines**(测试节点级 retry / failure aggregation 用):

| 类 | name | 说明 |
|---|---|---|
| `Echo` | `echo` | 接收任意 kwargs,打印后原样返回(通用测试用) |
| `MergeWeather` | `merge_weather` | 把两个城市天气合并成一句话 |
| `SummaryWeather` | `summary_weather` | 对合并结果做最终汇总 |
| `FlakyTask` | `flaky_task` | 前 `fail_times` 次故意失败,之后成功——测节点级 retry |
| `AlwaysFail` | `always_fail` | 总是抛错——测 `trigger_rule`(`all_done`/`none_failed`...)与失败聚合 |

> ⚠️ `Echo`(dag)与 `Echo`(test)同名,均注册时后者覆盖前者(`Routines.register` 按 name 去重)。

## user/react_agent/ —— Reactive Agent

精简版 reactive agent,sqlite 记忆 + 每轮 push act,常驻对话。

| 类 | name | passive | 说明 |
|---|---|---|---|
| `ReactAgents` | `react_agents` | ✅ | 常驻 manager:spawn / list / stop `ReactAgent` 子实例。Agent 记录持久化到 sqlite,通过 `agent_id` 隔离。`hidden=True` |
| `ReactAgent` | `react_agent` | – | reactive agent 子实例(由 manager spawn)。每轮 push act,常驻对话。`hidden=True` |
| `CreateReactAgent` | `create_react_agent` | – | 入口 routine,通过 `ReactAgents` manager 生成新 agent,返回 `agent_id`。`hidden=True` |

## user/claudecode/ —— claudecode Agent + 工具集 + Skills

对标 Claude Code 的编码 agent,内置工具集 + skills 子系统。详见 [DESIGN.md](../../routines/user/claudecode/DESIGN.md)。

### manager + agent

| 类 | name | passive | 说明 |
|---|---|---|---|
| `ClaudeCodeAgents` | `claude_code_agents` | ✅ | 常驻 manager:`create_agent` / `list_agents` / `stop_agent` req handler。Agent 记录持久化 sqlite,通过 `agent_id` 隔离。`hidden=True` |
| `ClaudeCodeAgent` | `claude_code_agent` | – | 编码 agent 子实例(LLM 对话循环 + 工具调用 + 会话日志 + reactive 用户输入)。由 `ClaudeCodeAgents` spawn。`hidden=True` |
| `CreateClaudeAgent` | `create_claude_agent` | – | 入口 routine,通过 `ClaudeCodeAgents` manager 生成新 agent,返回 `agent_id`。`hidden=True` |
| `ConvertSessionToMempalace` | `convert_session_to_mempalace` | ✅ | 定期从 sqlite 重建 MemPalace 兼容 JSONL 文件到 `sessions_mempalace/`。`hidden=True`,`enable=False`(已禁用) |
| `Memplace` | `memplace` | – | 运行本地 MemPalace CLI。`meta['tool']=True`,`enable=False`(已禁用) |

### tools/ —— 内置工具(`meta['tool']=True`)

每个工具一个 routine,跟普通 routine 同构。`meta` 承载工具语义(`readonly` / `concurrency_safe` / `needs_approval`)。

| 类 | name | readonly | 说明 |
|---|---|---|---|
| `Read` | `read` | ✅ | 读文件(文本/图片/PDF/notebook),支持行范围 |
| `Write` | `write` | ❌ | 创建或覆盖文件;现有文件需先 Read |
| `Edit` | `edit` | ❌ | 字符串替换式局部修改;需先 Read |
| `Glob` | `glob` | ✅ | 按 glob 找文件(`**/*.ts`) |
| `Grep` | `grep` | ✅ | ripgrep 内容检索(正则) |
| `Bash` | `bash` | ❌ | 执行 shell 命令(Windows 走 PowerShell) |
| `TodoWrite` | `todo_write` | ❌ | 写结构化任务清单 |
| `IPython` | `i_python` | ❌ | 持久 IPython kernel(真 ipykernel + ZMQ) |
| `Ssh` | `ssh` | ❌ | AsyncSSH 持久会话(`action=connect/exec/...`) |

### skills/ —— Skill 管理(`meta['tool']=True`)

per-agent skill 子系统,workspace 在实例化时绑定。详见 [02-routine-conventions.md](./02-routine-conventions.md#per-agent-workspace-隔离)。

| 类 | name | readonly | 说明 |
|---|---|---|---|
| `SearchSkill` | `search_skill` | ✅ | 搜 hermes-index(~9 万 skills,6h 缓存)+ skills.sh 兜底。返回 `install_url` |
| `ListSkills` | `list_skills` | ✅ | 列已装 skill(name + 简述) |
| `LoadSkill` | `load_skill` | ✅ | 加载 skill 完整说明到对话 |
| `InstallSkill` | `install_skill` | ❌ | 从本地目录或 URL 装 skill 到 agent workspace |
| `UninstallSkill` | `uninstall_skill` | ❌ | 卸载 workspace 副本(不动 builtin 源) |

## 按能力查找

### 想触发某个 routine

| 场景 | 入口 |
|---|---|
| 一次性触发(算完即返) | `ctx.call(name, kwargs)` 或 HTTP `POST /run/{name}` |
| 长跑型(中途 stop) | `ctx.submit + handle.start + handle.stop` 或 HTTP `POST /start/{name}` + `POST /stop/{id}` |
| 触发常驻 routine 的 handler | `ctx.req(rid, event, body)` 或 HTTP `POST /req/{rid}/{event}` |
| 触发 passive routine | 不用触发——kernel 连上后 auto-start |

### 想编排多个 routine

| 场景 | 入口 |
|---|---|
| 模块自动串并行 | `Shell(self).push(...).complete().join()` |
| barrier 同步点 | `Shell.push('wait', {'duration': ...})` |
| 声明式 DAG | `ctx.call('run_dag', {'name': 'hello_dag'})` |
| XML 嵌套 | `ctx.call('run_xml', {'xml': '...'})` |

### 想跟用户交互

| 场景 | 入口 |
|---|---|
| 单选题 | `ctx.call('ask', {'question': ..., 'options': [...]})` |
| 审批节点 | `ctx.call('dag_approval', {...})`(fail-closed) |
| 前端弹窗(自定义组件) | `ctx.req(bridge_id, 'ui_request', {component, props, timeout})`(详见 `02-routine-conventions.md` UI 交互约定) |

### 想创建 agent

| 场景 | 入口 |
|---|---|
| claudecode agent | `ctx.call('create_claude_agent', {'agent_id': ..., 'project_dir': ...})` |
| react agent | `ctx.call('create_react_agent', {...})` |
| 跟 agent 对话 | `ctx.req(agent_rid, 'send_message', {'text': ...})` |

## 下一步

- 框架级 API:[../framework/](../framework/)
- 编写约定:[02-routine-conventions.md](./02-routine-conventions.md)
