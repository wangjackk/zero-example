"""react_agent -- reactive agent (ContextProvider memory + built-in LLM, autonomous unit).

Multi-instance model: ReactAgents resident manager spawns ReactAgent children
on request; CreateReactAgent is the entry routine the bridge submits. Each
child runs concurrently, isolated by agent_id.

记忆系统走 ReactContextProvider (provider.py): 封装 Memory (sqlite 持久化)
+ 可选 OVMemory (同步备份 + 长期记忆), 默认启用 OV (peer_id='react', 跟
reactor/prime 的 'claude' 隔离). agent 只依赖 provider 接口, 不直接接触 Memory/OVMemory.

ReactCondenserAgent 是 react_agent 专用的上下文压缩 routine (跟 reactor/prime 的
CondenserAgent 平级, 各写各的; 共享 BaseCondenserRoutine 模板 + strategies 策略包).
"""
from routine import Routines

from .agent import ReactAgent
from .condenser import ReactCondenserAgent
from .manager import ReactAgents, CreateReactAgent

routines = Routines()
routines.register(
    ReactAgents,
    CreateReactAgent,
    ReactAgent,
    ReactCondenserAgent,
)

__all__ = [
    'ReactAgent',
    'ReactAgents',
    'CreateReactAgent',
    'ReactCondenserAgent',
    'routines',
]
