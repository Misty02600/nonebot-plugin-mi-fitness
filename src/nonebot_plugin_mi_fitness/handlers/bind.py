"""绑定管理命令。"""

from __future__ import annotations

import time

from arclet.alconna import Alconna, Args
from nonebot_plugin_alconna import Match, on_alconna
from nonebot_plugin_uninfo import Uninfo

from ..core.models import BindRecord
from ..infra.service import (
    TokenRecoverRequiredError,
    ensure_client,
    invoke_with_token_retry,
    plugin_store,
)

# region 绑定

bind_cmd = on_alconna(
    Alconna("小米绑定", Args["uid?", str]),
    use_cmd_start=True,
    block=True,
)


@bind_cmd.handle()
async def handle_bind(uid: Match[str], session: Uninfo):
    """绑定小米账号。Bot 向用户发送亲友申请。"""
    if not uid.available or not uid.result.strip().isdigit():
        await bind_cmd.finish("请发送有效的小米UID参数")
        return

    xiaomi_uid = int(uid.result.strip())
    user_id = session.user.id

    # 全局去重：同一个小米 UID 只能被一个成员绑定
    existed_bind = plugin_store.get_bind_by_xiaomi_uid(xiaomi_uid)
    if existed_bind and existed_bind.user_id != user_id:
        await bind_cmd.finish("该小米账号已被其他成员绑定")
        return

    try:
        client = await ensure_client()
    except RuntimeError:
        await bind_cmd.finish("绑定失败，请联系超级管理员")
        return

    # 验证用户 UID 是否存在（Token 过期时自动重登一次）
    try:
        user_info = await invoke_with_token_retry(
            lambda c: c.verify_user(xiaomi_uid),
            client,
        )
    except TokenRecoverRequiredError:
        await bind_cmd.finish("登录失败，Token 已失效")
        return
    if not user_info:
        await bind_cmd.finish(f"未找到小米 UID: {xiaomi_uid}")
        return

    note = user_info.nickname or str(xiaomi_uid)

    # 情况 1：已经是亲友 → 直接绑定为 active
    try:
        members = await invoke_with_token_retry(lambda c: c.get_relatives(), client)
    except TokenRecoverRequiredError:
        await bind_cmd.finish("登录失败，Token 已失效")
        return
    for m in members:
        if m.relative_uid == xiaomi_uid:
            plugin_store.add_bind(
                BindRecord(
                    user_id=user_id,
                    relative_uid=m.relative_uid,
                    relative_note=m.relative_note or note,
                    xiaomi_uid=xiaomi_uid,
                    nickname=user_info.nickname,
                    icon_url=m.relative_icon or user_info.icon,
                    profile_checked_at=time.time(),
                ),
            )
            await bind_cmd.finish("绑定成功！")
            return

    # 情况 2：尚未成为亲友 → 发送邀请并保存绑定
    try:
        success = await invoke_with_token_retry(
            lambda c: c.invite_relative(xiaomi_uid, relative_note=note),
            client,
        )
    except TokenRecoverRequiredError:
        await bind_cmd.finish("登录失败，Token 已失效")
        return
    if not success:
        await bind_cmd.finish("发送亲友申请失败，请稍后重试")
        return

    plugin_store.add_bind(
        BindRecord(
            user_id=user_id,
            relative_uid=xiaomi_uid,
            relative_note=note,
            xiaomi_uid=xiaomi_uid,
            nickname=user_info.nickname,
            icon_url=user_info.icon,
            profile_checked_at=time.time(),
        ),
    )
    await bind_cmd.finish(
        f"已向「{note}」(UID: {xiaomi_uid}) 发送亲友申请\n"
        "请在小米运动健康 App 中同意邀请，之后即可查询数据"
    )


# endregion

# region 解绑

unbind_cmd = on_alconna(
    Alconna("小米解绑"),
    use_cmd_start=True,
    block=True,
)


@unbind_cmd.handle()
async def handle_unbind(session: Uninfo):
    """解除绑定。"""
    user_id = session.user.id

    if plugin_store.remove_bind(user_id):
        await unbind_cmd.finish("解绑成功！")
    else:
        await unbind_cmd.finish("你还没有绑定账号哦")


# endregion
