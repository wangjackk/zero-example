"""Agent + tool routines registration.

取代 claudecode/__init__.py 的注册中心角色:
聚合 tools/ + reactor/ + prime/ 的 routine 类, 统一注册.
"""
from routine import Routines

from .tools.shell.BackgroundShellTool import BackgroundShell
from .tools.file_ops.ReadTool import Read
from .tools.file_ops.WriteTool import Write
from .tools.file_ops.EditTool import Edit
from .tools.file_ops.GlobTool import Glob
from .tools.file_ops.GrepTool import Grep
from .tools.shell.BashTool import Bash
from .tools.remote.SshTool import SshConnect, SshDisconnect, SshExec, SshList, SshTransfer
from .tools.utils.TodoWriteTool import TodoWrite
from .tools.shell.IPython import IPython
from .tools.utils.RunRoutineTool import RunRoutine
from .tools.remote.WebSearchTool import WebSearch
from .tools.remote.WebFetchTool import WebFetch
from .tools.ov.OvFindTool import OvFind
from .tools.ov.OvPeekTool import OvPeek
from .tools.ov.OvLinkTool import OvLink
from .tools.ov.OvRelationsTool import OvRelations
from .tools.ov.OvTreeTool import OvTree
from .tools.ov.OvStatTool import OvStat
from .reactor import ReactorAgent, ReactorAgentManager, CreateReactorAgent
from .prime import PrimeAgent, PrimeAgentManager, CreatePrimeAgent
from ._core.condenser.routine import CondenserAgent

routines = Routines()
routines.register(
    Read, Write, Edit, Glob, Grep, Bash,
    SshConnect, SshExec, SshTransfer, SshDisconnect, SshList,
    TodoWrite, IPython, RunRoutine, WebSearch, WebFetch,
    OvFind, OvPeek, OvLink, OvRelations, OvTree, OvStat,
    BackgroundShell,
    ReactorAgent, ReactorAgentManager, CreateReactorAgent,
    PrimeAgent, PrimeAgentManager, CreatePrimeAgent,
    CondenserAgent,
)
