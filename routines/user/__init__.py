"""业务 routines ---- 工具型 routine.

每个 routine 一个文件,本模块聚合注册.工具型 routine:``Wait``(barrier 同步点,
Shell 编排用),``HttpServer``(HTTP+WS 前门,curl 触发任意 routine + WS 桥接前端).
测试 / demo 型 routine 在 ``../test/``.

后续真业务 routine(alarm / camera_capture / claudecode / dag / music / ...)
按老 zero ``routines/user/`` 结构逐步加,每个一文件.
"""
from routine import Routines
from .dance import Dance
from .get_agent_rid import GetAgentRid
from .http_server import HttpServer
from .list_routines import ListRoutines
from .music import get_routines as music_routines
from .print_heart import PrintHeart
from .routine_doc import RoutineDoc
from .query_weather import get_routines as query_weather_routines
from .wait import Wait
from .xml import get_routines as xml_routines
from .agents.react_agent import routines as react_agent_routines
from .ask import Ask
from .send_message import SendMessage
from .show_image import ShowImage
from .list_running_agents import ListRunningAgents
from .get_agent_rid import GetAgentRid
from .fetch_agent_state import FetchAgentState
from .greet_by_time import GreetByTime
from .user_agent import UserAgent
from .world_agent import WorldAgent
from .agents.registry import routines as agents_routines
from .skills import routines as skills_routines
from .dag import (
    RunDag, DagApproval, DagCancel, TranslateArchon,
    Echo, MergeWeather, SummaryWeather, FlakyTask, AlwaysFail,
)


def get_routines() -> Routines:
    rs = Routines()
    # agent 启动后向 HttpServer(集成 WS 桥)req 注册自己(轮询直到成功,见
    # ReactAgent._register_with_bridge),不靠 conversation_open pubsub--后者无
    # 订阅者静默丢,依赖注册顺序.故 HttpServer 与被动 agent 的注册顺序不再敏感:
    # 无论谁先起,agent 迟早注册上.
    rs.register(Wait, HttpServer,
                xml_routines(),
                music_routines(),
                query_weather_routines(),
                Dance,
                PrintHeart,
                Ask,
                SendMessage,
                ShowImage,
                ListRunningAgents,
                GetAgentRid,
                FetchAgentState,
                GreetByTime,
                UserAgent,
                WorldAgent,
                ListRoutines,
                RoutineDoc,
                )
    # react_agent: manager(passive, auto-started) + entry + agent class.
    # multi-instance: ReactAgents manager spawns ReactAgent children on req.
    rs.register(react_agent_routines)
    # claudecode: manager(passive, auto-started) + agent class + tools.
    # agent is_passive=False, spawned by manager via submit+start.
    # claudecode_routines is a Routines instance (not a get_routines fn),
    # so pass it directly -- register flattens Routines groups.
    rs.register(agents_routines)
    # 通用 skill routines: agent 只注入 agent_id, routine 反向 req 获取 state.
    rs.register(skills_routines)
    # DAG 子系统:编排器 + 控制流节点 + 翻译器 + 示例 fixture routine.
    # dag_approval 依赖 Ask(已在上注册).
    rs.register(RunDag, DagApproval, DagCancel, TranslateArchon,
                Echo, MergeWeather, SummaryWeather, FlakyTask, AlwaysFail)
    return rs
