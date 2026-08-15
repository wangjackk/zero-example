"""routine 注册表聚合:user(业务)+ test(验证).

基础设施 host 见 one/(跟 zero 对等的独立进程),zero 重启不影响 one.
``register`` 接受 ``Routines`` 组(routine SDK 统一接口,不像 routine3 分
``register`` / ``register_many``).
"""
from routine import Routines


def get_routines() -> Routines:
    routines = Routines()
    from .test import get_routines as test_routines
    from .user import get_routines as user_routines
    routines.register(test_routines())
    routines.register(user_routines())
    return routines
