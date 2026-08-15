"""XML body 编排 routines:XmlRoutine(编排器)+ PrintBody(最小叶子).

对标 shell/zero 的 routines/core/routine.py + _parser.py,但在 zero 精简 SDK
之上重实现(inbox 驱动,无 body_shell 管线).详见 xml_routine.py 模块 docstring.
"""
from routine import Routines

from .act import Act
from .print_body import PrintBody
from .run_xml import RunXml
from .speak import Speak
from .xml_routine import XmlRoutine


def get_routines() -> Routines:
    rs = Routines()
    rs.register(
        Act,
        RunXml,
        PrintBody,
        Speak,
    )
    return rs

__all__ = [get_routines]