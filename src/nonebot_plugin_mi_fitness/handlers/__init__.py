"""命令模块

所有 NoneBot 命令处理器的统一入口。
通过导入此模块来注册所有命令。
"""

from . import (
    bind,
    data,
    system,
)

__all__ = [
    "bind",
    "data",
    "system",
]
