"""通用 skill routines -- 公共层, 供各 agent 专用 wrapper 通过 ``self.call`` 调用.

通用层 routine 入参如实含 ``skill_dir`` / ``cache_dir``, ``hidden=True`` 不暴露给 LLM.
专用层 wrapper (claudecode / react_agent) 各自定义窄 Input (不含 skill_dir), 在 run()
里注入 skill_dir 后 ``self.call('list_skills', ...)`` 调通用层.
"""
from routine import Routines
from .list_skills import ListSkills
from .load_skill import LoadSkill
from .install_skill import InstallSkill
from .uninstall_skill import UninstallSkill
from .search_skill import SearchSkill

routines = Routines()
routines.register(ListSkills, LoadSkill, InstallSkill, UninstallSkill, SearchSkill)

__all__ = ['routines']
