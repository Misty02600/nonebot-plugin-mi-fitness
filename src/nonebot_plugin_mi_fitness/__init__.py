"""nonebot-plugin-mi-fitness

通过小米运动健康亲友共享 API 获取健康数据。
"""

import nonebot
from nonebot import require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

from .config import Config

# 声明依赖
require("nonebot_plugin_localstore")
require("nonebot_plugin_alconna")
require("nonebot_plugin_htmlkit")
require("nonebot_plugin_uninfo")

# 导入处理器（注册命令）
from .handlers import bind as bind
from .handlers import data as data
from .handlers import system as system

# 启动时检测 token 有效性
driver = nonebot.get_driver()


@driver.on_startup
async def _on_startup() -> None:
    from .infra.service import startup_check

    await startup_check()


@driver.on_shutdown
async def _on_shutdown() -> None:
    from .infra.service import shutdown_cleanup

    await shutdown_cleanup()


__plugin_meta__ = PluginMetadata(
    name="小米运动健康",
    description="通过小米运动健康亲友共享获取心率、睡眠、步数等健康数据",
    usage="""绑定管理
  小米绑定 <小米UID> - 发送亲友申请并绑定
  小米解绑 - 解除全局绑定

数据查询
  小米心率 / 小米睡眠 / 小米步数 / 小米体重 / 小米日报
  小米心率周报 / 小米睡眠周报 / 小米步数周报""",
    type="application",
    homepage="https://github.com/Misty02600/nonebot-plugin-mi-fitness",
    config=Config,
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna",
        "nonebot_plugin_uninfo",
    ),
    extra={"author": "Misty02600"},
)
