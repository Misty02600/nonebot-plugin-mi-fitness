"""数据查询命令。"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import TypeAlias

from arclet.alconna import Alconna, Args
from mi_fitness import (
    DataNotSharedError,
    DataOutOfSharedTimeScopeError,
    FamilyMemberNotFoundError,
    MiHealthClient,
)
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot_plugin_alconna import At, Image, Match, UniMessage, on_alconna
from nonebot_plugin_uninfo import Uninfo

from ..core.models import BindRecord
from ..infra.service import (
    TokenRecoverRequiredError,
    ensure_client,
    invoke_with_token_retry,
    plugin_store,
)
from ..render import (
    render_daily,
    render_heart_rate,
    render_heart_rate_weekly,
    render_sleep,
    render_sleep_weekly,
    render_steps,
    render_steps_weekly,
    render_weight,
)

QueryResult: TypeAlias = bytes | None
QueryOperation: TypeAlias = Callable[[MiHealthClient, BindRecord], Awaitable[QueryResult]]

MSG_NOT_LOGGED_IN = "查询失败，请联系超级管理员"
MSG_NOT_BOUND = "你/ta还没有绑定哦，请使用「小米绑定 <小米UID>」进行绑定"
MSG_TOKEN_RECOVER_FAILED = "查询失败，请联系超级管理员"
MSG_NO_DATA = "暂无数据"

_PROFILE_CHECK_INTERVAL = 604800  # 7 days


def _display_name(bind: BindRecord) -> str:
    """返回绑定对象的显示昵称。"""
    return bind.nickname or bind.relative_note


async def _resolve_context(
    matcher: type[Matcher],
    user_id: str,
) -> tuple[MiHealthClient, BindRecord]:
    """解析查询上下文：登录态、绑定记录。"""
    try:
        client = await ensure_client()
    except RuntimeError:
        await matcher.finish(MSG_NOT_LOGGED_IN)

    bind = plugin_store.get_bind(user_id)
    if bind is None:
        await matcher.finish(MSG_NOT_BOUND)

    return client, bind


async def _refresh_bind_profile(
    client: MiHealthClient,
    bind: BindRecord,
) -> None:
    """按需刷新绑定昵称和头像 URL。"""
    need_refresh = not bind.icon_url or (
        time.time() - bind.profile_checked_at > _PROFILE_CHECK_INTERVAL
    )
    if not need_refresh:
        return

    try:
        members = await invoke_with_token_retry(lambda c: c.get_relatives(), client)
    except Exception:
        logger.opt(exception=True).debug("刷新绑定资料失败，继续使用本地缓存")
        return

    for member in members:
        if member.relative_uid != bind.relative_uid:
            continue
        if member.relative_icon and member.relative_icon != bind.icon_url:
            bind.icon_url = member.relative_icon
        if member.relative_note and member.relative_note != bind.relative_note:
            bind.relative_note = member.relative_note
        bind.profile_checked_at = time.time()
        plugin_store.add_bind(bind)
        break


async def _run_query(
    client: MiHealthClient,
    bind: BindRecord,
    query: QueryOperation,
) -> QueryResult:
    """执行查询并处理 Token 过期自动重试。"""
    return await invoke_with_token_retry(lambda c: query(c, bind), client)


async def _finish_query_result(
    matcher: type[Matcher],
    result: QueryResult,
) -> None:
    """按结果类型发送消息。"""
    if result is None:
        await matcher.finish(MSG_NO_DATA)

    await UniMessage(Image(raw=result)).finish(reply_to=True)


def _resolve_boundary_error_message(exc: Exception) -> str | None:
    """将 MiSDK 边界异常映射为用户可读提示。

    Args:
        exc (Exception): 查询过程中抛出的异常对象。

    Returns:
        str | None: 可直接发送给用户的提示语；非边界异常时返回 None。
    """
    if isinstance(exc, FamilyMemberNotFoundError):
        return "当前账号不是 Bot 的亲友，请重新绑定"

    if isinstance(exc, DataOutOfSharedTimeScopeError):
        return "查询失败，请在小米运动健康 App 中开放查询日期范围"

    if isinstance(exc, DataNotSharedError):
        return "查询失败，请在小米运动健康 App 中开启对应共享权限"

    return None


async def _handle_query(
    matcher: type[Matcher],
    user_id: str,
    query: QueryOperation,
) -> None:
    """通用数据查询处理。

    1. 校验登录状态、绑定记录
    2. 执行查询并捕获非亲友异常
    3. Token 过期时自动重新登录并重试一次
    4. 空数据返回提示
    5. 查询成功时发送图片卡片
    """
    client, bind = await _resolve_context(
        matcher,
        user_id,
    )
    await _refresh_bind_profile(client, bind)

    try:
        result = await _run_query(client, bind, query)
    except TokenRecoverRequiredError:
        await matcher.finish(MSG_TOKEN_RECOVER_FAILED)
    except Exception as e:
        boundary_error_message = _resolve_boundary_error_message(e)
        if boundary_error_message:
            await matcher.finish(boundary_error_message)
        raise

    await _finish_query_result(matcher, result)


# region 心率

heart_rate_cmd = on_alconna(
    Alconna("小米心率", Args["target?", At]), use_cmd_start=True, block=True
)


@heart_rate_cmd.handle()
async def handle_heart_rate(session: Uninfo, target: Match[At]) -> None:
    """查看今日心率。"""

    async def query(client: MiHealthClient, bind: BindRecord) -> QueryResult:
        data = await client.get_heart_rate(bind.relative_uid)
        if not data:
            return None
        return await render_heart_rate(
            data[0],
            _display_name(bind),
            bind.icon_url,
        )

    user_id = target.result.target if target.available else session.user.id
    await _handle_query(heart_rate_cmd, user_id, query)


# endregion

# region 睡眠

sleep_cmd = on_alconna(
    Alconna("小米睡眠", Args["target?", At]), use_cmd_start=True, block=True
)


@sleep_cmd.handle()
async def handle_sleep(session: Uninfo, target: Match[At]) -> None:
    """查看今日睡眠。"""

    async def query(client: MiHealthClient, bind: BindRecord) -> QueryResult:
        data = await client.get_sleep(bind.relative_uid)
        if not data:
            return None
        return await render_sleep(
            data[0],
            _display_name(bind),
            bind.icon_url,
        )

    user_id = target.result.target if target.available else session.user.id
    await _handle_query(sleep_cmd, user_id, query)


# endregion

# region 步数

steps_cmd = on_alconna(
    Alconna("小米步数", Args["target?", At]), use_cmd_start=True, block=True
)


@steps_cmd.handle()
async def handle_steps(session: Uninfo, target: Match[At]) -> None:
    """查看今日步数。"""

    async def query(client: MiHealthClient, bind: BindRecord) -> QueryResult:
        data = await client.get_steps(bind.relative_uid)
        if not data:
            return None
        return await render_steps(
            data[0],
            _display_name(bind),
            bind.icon_url,
        )

    user_id = target.result.target if target.available else session.user.id
    await _handle_query(steps_cmd, user_id, query)


# endregion

# region 体重

weight_cmd = on_alconna(
    Alconna("小米体重", Args["target?", At]), use_cmd_start=True, block=True
)


@weight_cmd.handle()
async def handle_weight(session: Uninfo, target: Match[At]) -> None:
    """查看最新体重。"""

    async def query(client: MiHealthClient, bind: BindRecord) -> QueryResult:
        data = await client.get_weight(bind.relative_uid)
        if not data:
            return None
        return await render_weight(
            data,
            _display_name(bind),
            bind.icon_url,
        )

    user_id = target.result.target if target.available else session.user.id
    await _handle_query(weight_cmd, user_id, query)


# endregion

# region 健康日报

daily_cmd = on_alconna(
    Alconna("小米日报", Args["target?", At]), use_cmd_start=True, block=True
)


@daily_cmd.handle()
async def handle_daily(session: Uninfo, target: Match[At]) -> None:
    """查看今日综合健康数据。"""

    async def query(client: MiHealthClient, bind: BindRecord) -> QueryResult:
        summary = await client.get_latest_daily_summary(bind.relative_uid)
        return await render_daily(
            summary,
            _display_name(bind),
            bind.icon_url,
        )

    user_id = target.result.target if target.available else session.user.id
    await _handle_query(daily_cmd, user_id, query)


# endregion

# region 心率周报

heart_rate_weekly_cmd = on_alconna(
    Alconna("小米心率周报", Args["target?", At]), use_cmd_start=True, block=True
)


@heart_rate_weekly_cmd.handle()
async def handle_heart_rate_weekly(session: Uninfo, target: Match[At]) -> None:
    """查看本周心率。"""

    async def query(client: MiHealthClient, bind: BindRecord) -> QueryResult:
        data = await client.get_heart_rate(bind.relative_uid, days=7)
        if not data:
            return None
        return await render_heart_rate_weekly(
            data,
            _display_name(bind),
            bind.icon_url,
        )

    user_id = target.result.target if target.available else session.user.id
    await _handle_query(heart_rate_weekly_cmd, user_id, query)


# endregion

# region 睡眠周报

sleep_weekly_cmd = on_alconna(
    Alconna("小米睡眠周报", Args["target?", At]), use_cmd_start=True, block=True
)


@sleep_weekly_cmd.handle()
async def handle_sleep_weekly(session: Uninfo, target: Match[At]) -> None:
    """查看本周睡眠。"""

    async def query(client: MiHealthClient, bind: BindRecord) -> QueryResult:
        data = await client.get_sleep(bind.relative_uid, days=7)
        if not data:
            return None
        return await render_sleep_weekly(
            data,
            _display_name(bind),
            bind.icon_url,
        )

    user_id = target.result.target if target.available else session.user.id
    await _handle_query(sleep_weekly_cmd, user_id, query)


# endregion

# region 步数周报

steps_weekly_cmd = on_alconna(
    Alconna("小米步数周报", Args["target?", At]), use_cmd_start=True, block=True
)


@steps_weekly_cmd.handle()
async def handle_steps_weekly(session: Uninfo, target: Match[At]) -> None:
    """查看本周步数。"""

    async def query(client: MiHealthClient, bind: BindRecord) -> QueryResult:
        data = await client.get_steps(bind.relative_uid, days=7)
        if not data:
            return None
        return await render_steps_weekly(
            data,
            _display_name(bind),
            bind.icon_url,
        )

    user_id = target.result.target if target.available else session.user.id
    await _handle_query(steps_weekly_cmd, user_id, query)


# endregion
