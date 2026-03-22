"""系统管理命令（超级用户）。"""

from __future__ import annotations

import httpx
from arclet.alconna import Alconna
from mi_fitness import AuthError
from nonebot.log import logger
from nonebot.permission import SUPERUSER
from nonebot.plugin import get_plugin_by_module_name
from nonebot_plugin_alconna import Image, Text, UniMessage, on_alconna
from nonebot_plugin_uninfo import Uninfo

from ..infra.service import qr_login

# 帮助
help_cmd = on_alconna(Alconna("小米帮助"), use_cmd_start=True, block=True)


@help_cmd.handle()
async def handle_help():
    """查看帮助。"""
    plugin = get_plugin_by_module_name(__name__)
    usage = plugin.metadata.usage if plugin and plugin.metadata else "暂无帮助信息"
    await help_cmd.finish(usage)

# region 登录

login_cmd = on_alconna(
    Alconna("小米登录"), permission=SUPERUSER, use_cmd_start=True, block=True
)


@login_cmd.handle()
async def handle_login(session: Uninfo):
    """超级用户扫码登录（仅限私聊）。"""
    if session.scene and session.scene.type.name != "PRIVATE":
        await login_cmd.finish("请在私聊中使用此命令")
        return

    logger.info("收到超级用户登录指令，开始二维码登录流程")

    async def _send_qr(qr_image_url: str, _login_url: str) -> None:
        """下载二维码图片并发送到聊天。"""
        async with httpx.AsyncClient() as http:
            resp = await http.get(qr_image_url)
            resp.raise_for_status()
            image_bytes = resp.content

        msg = UniMessage([
            Text("请使用小米账号 APP 扫描下方二维码完成登录（5 分钟内有效）"),
            Image(raw=image_bytes),
        ])
        await login_cmd.send(msg)
        logger.info("二维码已发送到会话，等待用户扫码确认")

    try:
        await qr_login(_send_qr)
    except AuthError as e:
        logger.warning("二维码登录失败: {}", e)
        if "超时" in str(e):
            await login_cmd.finish("二维码已过期，请重新发送「小米登录」")
        else:
            await login_cmd.finish(f"小米账号登录失败：{e}")
        return
    except Exception as e:
        logger.exception("二维码登录异常")
        await login_cmd.finish(f"小米账号登录失败：{e}")
        return

    logger.info("二维码登录流程完成")
    await login_cmd.finish("小米账号登录成功！")


# endregion
