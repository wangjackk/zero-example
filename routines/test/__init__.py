"""测试 / demo 型 routines ---- 端到端验证特定特性用的 routine.

每个 routine 一个文件,本模块聚合注册.这些 routine 都是开发期验证 / demo 用的
(验 error 透传 / run / force / 编排 / barrier 等),不是业务 routine.
业务 routine 在 ``../user/``.
"""

from routine import Routines

from .auto_demo import AutoDemo
from .auto_sp import AutoSP
from .boom import Boom
from .compose import Compose
from .dynamic_demo import DynamicDemo
from .echo import Echo
from .force_demo import ForceDemo
from .test import Test
from .wait_demo import WaitDemo
from .output2 import Output2
from .quick import Quick
from .ui_noop import UINoop
from .reg_dereg_test import RegDeregTest

def get_routines() -> Routines:
    rs = Routines()
    rs.register(Boom, Test, Compose, ForceDemo, AutoDemo, WaitDemo, Echo, AutoSP, Output2, Quick, UINoop, DynamicDemo, RegDeregTest)
    return rs
