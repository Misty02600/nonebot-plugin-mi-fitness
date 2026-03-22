"""Handler 集成测试（nonebug）。

使用 nonebug 模拟消息事件，验证 handler 的完整处理流程。
MiSDK 客户端通过 mock 注入。
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any, cast
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import nonebot
import pytest
from nonebot.adapters.onebot.v11 import Adapter as OB11Adapter
from nonebot.adapters.onebot.v11 import Bot as OB11Bot
from nonebot.adapters.onebot.v11 import Message
from nonebug import App

from fake import fake_group_message_event_v11, fake_private_message_event_v11

# 默认群组 / 用户 ID（与 fake.py 一致）
GROUP_ID = "87654321"
USER_ID = "12345678"


# region fixtures


@pytest.fixture
def store(tmp_path: Path):
    """将真实 plugin_store 切换到临时路径，测试后恢复。"""
    from nonebot_plugin_mi_fitness.core.models import PluginData
    from nonebot_plugin_mi_fitness.infra.service import plugin_store

    old_data = plugin_store.data
    old_path = plugin_store._path
    plugin_store.data = PluginData()
    plugin_store._path = tmp_path / "test.json"
    yield plugin_store
    plugin_store.data = old_data
    plugin_store._path = old_path


@pytest.fixture
def mock_client():
    """创建 MiHealthClient mock 并覆盖全局缓存。"""
    from nonebot_plugin_mi_fitness.infra import service

    client = AsyncMock()
    # 保存原始的缓存
    old_mi_client = service.mi_client
    old_auth = service.auth
    try:
        # 使用 mock 替换全局缓存
        service.mi_client = client
        service.auth = AsyncMock()
        service.auth.is_authenticated = True
        yield client
    finally:
        # 恢复原始缓存
        service.mi_client = old_mi_client
        service.auth = old_auth


@pytest.fixture
def mock_client_not_logged_in():
    """模拟未登录状态（ensure_client 抛出 RuntimeError）。"""
    with patch(
        "nonebot_plugin_mi_fitness.handlers.bind.ensure_client",
        new_callable=AsyncMock,
        side_effect=RuntimeError("未登录"),
    ), patch(
        "nonebot_plugin_mi_fitness.handlers.data.ensure_client",
        new_callable=AsyncMock,
        side_effect=RuntimeError("未登录"),
    ):
        yield


def _make_user_info(nickname: str = "测试用户", uid: int = 999):
    """创建 VerifiedUserInfo mock。"""
    info = MagicMock()
    info.nickname = nickname
    info.user_id = uid
    info.icon = ""
    return info


def _make_relative(relative_uid: int = 999, relative_note: str = "测试用户"):
    """创建 FamilyMember mock。"""
    m = MagicMock()
    m.relative_uid = relative_uid
    m.relative_note = relative_note
    m.relative_icon = ""
    return m


def _ob11_bot(ctx):
    """创建 OneBot V11 bot，使用已注册的真实 OB11 适配器。

    按 nonebug 文档推荐方式：nonebot.get_adapter(Adapter) + create_bot(base=Bot)。
    这样 bot.adapter.get_name() 返回 "OneBot V11"，alconna 会使用正确的
    OB11 exporter 解析 MsgTarget（提取 group_id 等）。
    """
    adapter = nonebot.get_adapter(OB11Adapter)
    bot = ctx.create_bot(base=OB11Bot, adapter=adapter)
    bot.get_group_info = AsyncMock(
        return_value={"group_id": int(GROUP_ID), "group_name": "测试群"}
    )
    bot.get_group_member_info = AsyncMock(
        return_value={
            "user_id": int(USER_ID),
            "card": "",
            "role": "member",
            "join_time": 0,
            "sex": "unknown",
            "nickname": "test",
        }
    )
    bot.get_login_info = AsyncMock(return_value={"user_id": 1, "nickname": "bot"})
    bot.get_stranger_info = AsyncMock(
        return_value={"user_id": int(USER_ID), "nickname": "test", "sex": "unknown"}
    )
    bot.get_friend_list = AsyncMock(return_value=[])
    bot.get_group_list = AsyncMock(return_value=[])
    return bot


def _add_default_bind(store) -> None:
    """为当前默认群和用户添加一条绑定记录。"""
    from nonebot_plugin_mi_fitness.core.models import BindRecord

    store.add_bind(
        BindRecord(
            user_id=USER_ID,
            relative_uid=999,
            relative_note="小明",
            xiaomi_uid=999,
        ),
    )


async def _assert_query_command_sends_image(
    app: App,
    store,
    mock_client,
    *,
    command_attr: str,
    message: str,
    client_method: str,
    client_value_factory,
    render_target: str,
) -> None:
    """断言查询命令在有数据时发送图片消息。"""
    _add_default_bind(store)
    getattr(mock_client, client_method).return_value = client_value_factory()

    data_handlers = import_module("nonebot_plugin_mi_fitness.handlers.data")
    command = getattr(data_handlers, command_attr)

    with patch(render_target, new=AsyncMock(return_value=b"fake-image")) as render_mock:
        async with app.test_matcher(command) as ctx:
            event = fake_group_message_event_v11(message=Message(message))
            ctx.receive_event(bot=_ob11_bot(ctx), event=event)
            ctx.should_call_send(event, ANY)  # pyright: ignore[reportArgumentType]
            ctx.should_finished(command)

    render_mock.assert_awaited_once()


# endregion

# region 绑定命令


@pytest.mark.asyncio
async def test_bind_invite_sent(app: App, store, mock_client):
    """绑定：用户不在亲友列表 -> 发送邀请 -> 保存 pending。"""
    mock_client.verify_user.return_value = _make_user_info("小明", 999)
    mock_client.get_relatives.return_value = []
    mock_client.invite_relative.return_value = True

    from nonebot_plugin_mi_fitness.handlers.bind import bind_cmd

    async with app.test_matcher(bind_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米绑定 999"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(
            event,
            "已向「小明」(UID: 999) 发送亲友申请\n"
            "请在小米运动健康 App 中同意邀请，之后即可查询数据",
        )
        ctx.should_finished(bind_cmd)

    bind = store.get_bind(USER_ID)
    assert bind is not None
    assert bind.xiaomi_uid == 999


@pytest.mark.asyncio
async def test_bind_already_relative(app: App, store, mock_client):
    """绑定：用户已是亲友 -> 直接绑定为 active。"""
    mock_client.verify_user.return_value = _make_user_info("小明", 999)
    mock_client.get_relatives.return_value = [_make_relative(999, "小明")]

    from nonebot_plugin_mi_fitness.handlers.bind import bind_cmd

    async with app.test_matcher(bind_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米绑定 999"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(event, "绑定成功！")
        ctx.should_finished(bind_cmd)

    bind = store.get_bind(USER_ID)
    assert bind is not None


@pytest.mark.asyncio
async def test_bind_uid_not_found(app: App, store, mock_client):
    """绑定：UID 不存在。"""
    mock_client.verify_user.return_value = None

    from nonebot_plugin_mi_fitness.handlers.bind import bind_cmd

    async with app.test_matcher(bind_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米绑定 999"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(event, "未找到小米 UID: 999")
        ctx.should_finished(bind_cmd)


@pytest.mark.asyncio
async def test_bind_invalid_uid(app: App, store, mock_client):
    """绑定：UID 格式无效。"""
    from nonebot_plugin_mi_fitness.handlers.bind import bind_cmd

    async with app.test_matcher(bind_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米绑定 abc"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(
            event, "请发送有效的小米UID参数"
        )
        ctx.should_finished(bind_cmd)


@pytest.mark.asyncio
async def test_bind_not_logged_in(app: App, store, mock_client_not_logged_in):
    """绑定：Bot 未登录。"""
    from nonebot_plugin_mi_fitness.handlers.bind import bind_cmd

    async with app.test_matcher(bind_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米绑定 999"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(
            event,
            "绑定失败，请联系超级管理员",
        )
        ctx.should_finished(bind_cmd)


@pytest.mark.asyncio
async def test_bind_private_chat(app: App, store, mock_client):
    """绑定：私聊中使用应正常工作（个人级别绑定）。"""
    mock_client.verify_user.return_value = _make_user_info("小明", 999)
    mock_client.get_relatives.return_value = []
    mock_client.invite_relative.return_value = True

    from nonebot_plugin_mi_fitness.handlers.bind import bind_cmd

    async with app.test_matcher(bind_cmd) as ctx:
        event = fake_private_message_event_v11(message=Message("/小米绑定 999"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(
            event,
            "已向「小明」(UID: 999) 发送亲友申请\n"
            "请在小米运动健康 App 中同意邀请，之后即可查询数据",
        )
        ctx.should_finished(bind_cmd)

    bind = store.get_bind("10")
    assert bind is not None
    assert bind.xiaomi_uid == 999


@pytest.mark.asyncio
async def test_bind_in_private_then_query_in_group(app: App, store, mock_client):
    """绑定：私聊绑定后可在群聊直接查询。"""
    mock_client.verify_user.return_value = _make_user_info("小明", 999)
    mock_client.get_relatives.return_value = []
    mock_client.invite_relative.return_value = True

    from nonebot_plugin_mi_fitness.handlers.bind import bind_cmd
    from nonebot_plugin_mi_fitness.handlers.data import heart_rate_cmd

    async with app.test_matcher(bind_cmd) as ctx:
        event = fake_private_message_event_v11(message=Message("/小米绑定 999"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(
            event,
            "已向「小明」(UID: 999) 发送亲友申请\n"
            "请在小米运动健康 App 中同意邀请，之后即可查询数据",
        )
        ctx.should_finished(bind_cmd)

    hr_data = MagicMock()
    hr_data.avg_hr = 72
    hr_data.max_hr = 120
    hr_data.min_hr = 55
    hr_data.avg_rhr = 60
    hr_data.latest_hr = MagicMock(bpm=75, time=1700000000)
    mock_client.get_heart_rate.return_value = [hr_data]

    async with app.test_matcher(heart_rate_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米心率"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(event, ANY)  # pyright: ignore[reportArgumentType]
        ctx.should_finished(heart_rate_cmd)


@pytest.mark.asyncio
async def test_bind_invite_failed(app: App, store, mock_client):
    """绑定：邀请发送失败。"""
    mock_client.verify_user.return_value = _make_user_info("小明", 999)
    mock_client.get_relatives.return_value = []
    mock_client.invite_relative.return_value = False

    from nonebot_plugin_mi_fitness.handlers.bind import bind_cmd

    async with app.test_matcher(bind_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米绑定 999"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(event, "发送亲友申请失败，请稍后重试")
        ctx.should_finished(bind_cmd)


@pytest.mark.asyncio
async def test_bind_rebind(app: App, store, mock_client):
    """换绑：已有绑定的情况下重新绑定新 UID。"""
    from nonebot_plugin_mi_fitness.core.models import BindRecord

    store.add_bind(BindRecord(user_id=USER_ID, relative_uid=888, xiaomi_uid=888))

    mock_client.verify_user.return_value = _make_user_info("小红", 999)
    mock_client.get_relatives.return_value = []
    mock_client.invite_relative.return_value = True

    from nonebot_plugin_mi_fitness.handlers.bind import bind_cmd

    async with app.test_matcher(bind_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米绑定 999"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(
            event,
            "已向「小红」(UID: 999) 发送亲友申请\n"
            "请在小米运动健康 App 中同意邀请，之后即可查询数据",
        )
        ctx.should_finished(bind_cmd)

    bind = store.get_bind(USER_ID)
    assert bind is not None
    assert bind.xiaomi_uid == 999


@pytest.mark.asyncio
async def test_bind_duplicate_uid_other_user(app: App, store, mock_client):
    """绑定：其他成员已绑定该 UID，应直接拒绝。"""
    from nonebot_plugin_mi_fitness.core.models import BindRecord

    store.add_bind(
        BindRecord(
            user_id="22222222",
            relative_uid=999,
            relative_note="小明",
            xiaomi_uid=999,
        ),
    )

    from nonebot_plugin_mi_fitness.handlers.bind import bind_cmd

    async with app.test_matcher(bind_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米绑定 999"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(event, "该小米账号已被其他成员绑定")
        ctx.should_finished(bind_cmd)

    mock_client.verify_user.assert_not_called()
    mock_client.invite_relative.assert_not_called()


# endregion

# region 解绑命令


@pytest.mark.asyncio
async def test_unbind_success(app: App, store, mock_client):
    """解绑：已有绑定。"""
    from nonebot_plugin_mi_fitness.core.models import BindRecord

    store.add_bind(BindRecord(user_id=USER_ID, relative_uid=999, xiaomi_uid=999))

    from nonebot_plugin_mi_fitness.handlers.bind import unbind_cmd

    async with app.test_matcher(unbind_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米解绑"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(event, "解绑成功！")
        ctx.should_finished(unbind_cmd)

    assert store.get_bind(USER_ID) is None


@pytest.mark.asyncio
async def test_unbind_not_bound(app: App, store, mock_client):
    """解绑：未绑定。"""
    from nonebot_plugin_mi_fitness.handlers.bind import unbind_cmd

    async with app.test_matcher(unbind_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米解绑"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(event, "你还没有绑定账号哦")
        ctx.should_finished(unbind_cmd)


# endregion

# region 数据查询（lazy-confirm）


@pytest.mark.asyncio
async def test_query_private_chat(app: App, store, mock_client):
    """查询：私聊中使用应正常工作（返回未绑定提示）。"""
    from nonebot_plugin_mi_fitness.handlers.data import heart_rate_cmd

    async with app.test_matcher() as ctx:
        event = fake_private_message_event_v11(message=Message("/小米心率"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(
            event, "你/ta还没有绑定哦，请使用「小米绑定 <小米UID>」进行绑定"
        )
        ctx.should_finished(heart_rate_cmd)


@pytest.mark.asyncio
async def test_query_active_bind(app: App, store, mock_client):
    """查询心率：active 绑定 -> 正常返回数据。"""
    from nonebot_plugin_mi_fitness.core.models import BindRecord

    store.add_bind(
        BindRecord(
            user_id=USER_ID,
            relative_uid=999,
            relative_note="小明",
            xiaomi_uid=999,
        ),
    )

    hr_data = MagicMock()
    hr_data.avg_hr = 72
    hr_data.max_hr = 120
    hr_data.min_hr = 55
    hr_data.avg_rhr = 60
    hr_data.latest_hr = MagicMock(bpm=75, time=1700000000)
    mock_client.get_heart_rate.return_value = [hr_data]

    from nonebot_plugin_mi_fitness.handlers.data import heart_rate_cmd

    async with app.test_matcher(heart_rate_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米心率"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(event, ANY)  # pyright: ignore[reportArgumentType]
        ctx.should_finished(heart_rate_cmd)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command_attr", "message", "client_method", "client_value_factory", "render_target"),
    [
        pytest.param(
            "sleep_cmd",
            "/小米睡眠",
            "get_sleep",
            lambda: [MagicMock()],
            "nonebot_plugin_mi_fitness.handlers.data.render_sleep",
            id="sleep",
        ),
        pytest.param(
            "steps_cmd",
            "/小米步数",
            "get_steps",
            lambda: [MagicMock()],
            "nonebot_plugin_mi_fitness.handlers.data.render_steps",
            id="steps",
        ),
        pytest.param(
            "weight_cmd",
            "/小米体重",
            "get_weight",
            MagicMock,
            "nonebot_plugin_mi_fitness.handlers.data.render_weight",
            id="weight",
        ),
        pytest.param(
            "daily_cmd",
            "/小米日报",
            "get_latest_daily_summary",
            MagicMock,
            "nonebot_plugin_mi_fitness.handlers.data.render_daily",
            id="daily",
        ),
        pytest.param(
            "heart_rate_weekly_cmd",
            "/小米心率周报",
            "get_heart_rate",
            lambda: [MagicMock()],
            "nonebot_plugin_mi_fitness.handlers.data.render_heart_rate_weekly",
            id="heart-rate-weekly",
        ),
        pytest.param(
            "sleep_weekly_cmd",
            "/小米睡眠周报",
            "get_sleep",
            lambda: [MagicMock()],
            "nonebot_plugin_mi_fitness.handlers.data.render_sleep_weekly",
            id="sleep-weekly",
        ),
        pytest.param(
            "steps_weekly_cmd",
            "/小米步数周报",
            "get_steps",
            lambda: [MagicMock()],
            "nonebot_plugin_mi_fitness.handlers.data.render_steps_weekly",
            id="steps-weekly",
        ),
    ],
)
async def test_query_commands_send_rendered_image(
    app: App,
    store,
    mock_client,
    command_attr: str,
    message: str,
    client_method: str,
    client_value_factory,
    render_target: str,
):
    """查询命令：有数据时应发送渲染后的图片。"""
    await _assert_query_command_sends_image(
        app,
        store,
        mock_client,
        command_attr=command_attr,
        message=message,
        client_method=client_method,
        client_value_factory=client_value_factory,
        render_target=render_target,
    )


@pytest.mark.asyncio
async def test_handle_query_render_failure_bubbles():
    """查询：渲染失败时不降级为文本，也不误报 token 错误。"""
    from nonebot_plugin_mi_fitness.core.models import BindRecord
    from nonebot_plugin_mi_fitness.handlers.data import _handle_query

    finish = AsyncMock()
    matcher = type("DummyMatcher", (), {"finish": finish})
    client = AsyncMock()
    bind = BindRecord(user_id=USER_ID, relative_uid=999, relative_note="小明")
    session = MagicMock()
    session.scene_path = GROUP_ID
    session.user.id = USER_ID

    async def query(_client, _bind):
        raise RuntimeError("render failed")

    with (
        patch(
            "nonebot_plugin_mi_fitness.handlers.data._resolve_context",
            new=AsyncMock(return_value=(client, bind)),
        ),
        patch(
            "nonebot_plugin_mi_fitness.handlers.data._refresh_bind_profile",
            new=AsyncMock(),
        ),
    ):
        with pytest.raises(RuntimeError, match="render failed"):
            await _handle_query(cast(Any, matcher), cast(Any, session), query)

    finish.assert_not_awaited()


@pytest.mark.asyncio
async def test_query_token_recover_required(app: App, store, mock_client):
    """查询：token 无法自动恢复时返回明确提示。"""
    from nonebot_plugin_mi_fitness.handlers.data import heart_rate_cmd
    from nonebot_plugin_mi_fitness.infra.service import TokenRecoverRequiredError

    _add_default_bind(store)

    with (
        patch(
            "nonebot_plugin_mi_fitness.handlers.data._refresh_bind_profile",
            new=AsyncMock(),
        ),
        patch(
            "nonebot_plugin_mi_fitness.handlers.data.invoke_with_token_retry",
            new=AsyncMock(side_effect=TokenRecoverRequiredError("expired")),
        ),
    ):
        async with app.test_matcher(heart_rate_cmd) as ctx:
            event = fake_group_message_event_v11(message=Message("/小米心率"))
            ctx.receive_event(bot=_ob11_bot(ctx), event=event)
            ctx.should_call_send(
                event,
                "查询失败，请联系超级管理员",
            )
            ctx.should_finished(heart_rate_cmd)


@pytest.mark.asyncio
async def test_query_pending_bind_auto_activate(app: App, store, mock_client):
    """查询：已绑定时可直接查询。"""
    from nonebot_plugin_mi_fitness.core.models import BindRecord

    store.add_bind(
        BindRecord(
            user_id=USER_ID,
            relative_uid=999,
            relative_note="小明",
            xiaomi_uid=999,
        ),
    )

    hr_data = MagicMock()
    hr_data.avg_hr = 72
    hr_data.max_hr = 120
    hr_data.min_hr = 55
    hr_data.avg_rhr = 60
    hr_data.latest_hr = MagicMock(bpm=75, time=1700000000)
    mock_client.get_heart_rate.return_value = [hr_data]

    from nonebot_plugin_mi_fitness.handlers.data import heart_rate_cmd

    async with app.test_matcher(heart_rate_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米心率"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(event, ANY)  # pyright: ignore[reportArgumentType]
        ctx.should_finished(heart_rate_cmd)


@pytest.mark.asyncio
async def test_query_pending_bind_not_accepted(app: App, store, mock_client):
    """查询：非亲友时提示重新绑定。"""
    from mi_fitness import FamilyMemberNotFoundError

    from nonebot_plugin_mi_fitness.core.models import BindRecord

    store.add_bind(
        BindRecord(
            user_id=USER_ID,
            relative_uid=999,
            relative_note="小明",
            xiaomi_uid=999,
        ),
    )

    mock_client.get_heart_rate.side_effect = FamilyMemberNotFoundError("未找到亲友")

    from nonebot_plugin_mi_fitness.handlers.data import heart_rate_cmd

    async with app.test_matcher(heart_rate_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米心率"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(event, "当前账号不是 Bot 的亲友，请重新绑定")
        ctx.should_finished(heart_rate_cmd)


@pytest.mark.asyncio
async def test_query_data_not_shared(app: App, store, mock_client):
    """查询：亲友未共享该数据类型。"""
    from mi_fitness import DataNotSharedError

    from nonebot_plugin_mi_fitness.core.models import BindRecord

    store.add_bind(
        BindRecord(
            user_id=USER_ID,
            relative_uid=999,
            relative_note="小明",
            xiaomi_uid=999,
        ),
    )

    mock_client.get_heart_rate.side_effect = DataNotSharedError("未共享")

    from nonebot_plugin_mi_fitness.handlers.data import heart_rate_cmd

    async with app.test_matcher(heart_rate_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米心率"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(
            event,
            "查询失败，请在小米运动健康 App 中开启对应共享权限",
        )
        ctx.should_finished(heart_rate_cmd)


@pytest.mark.asyncio
async def test_query_data_out_of_shared_time_scope(app: App, store, mock_client):
    """查询：日期超出亲友共享时间范围。"""
    from mi_fitness import DataOutOfSharedTimeScopeError

    from nonebot_plugin_mi_fitness.core.models import BindRecord

    store.add_bind(
        BindRecord(
            user_id=USER_ID,
            relative_uid=999,
            relative_note="小明",
            xiaomi_uid=999,
        ),
    )

    mock_client.get_heart_rate.side_effect = DataOutOfSharedTimeScopeError("超出范围")

    from nonebot_plugin_mi_fitness.handlers.data import heart_rate_cmd

    async with app.test_matcher(heart_rate_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米心率"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(event, "查询失败，请在小米运动健康 App 中开放查询日期范围")
        ctx.should_finished(heart_rate_cmd)


@pytest.mark.asyncio
async def test_query_not_bound(app: App, store, mock_client):
    """查询：未绑定 -> 提示绑定。"""
    from nonebot_plugin_mi_fitness.handlers.data import heart_rate_cmd

    async with app.test_matcher(heart_rate_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米心率"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(
            event, "你/ta还没有绑定哦，请使用「小米绑定 <小米UID>」进行绑定"
        )
        ctx.should_finished(heart_rate_cmd)


@pytest.mark.asyncio
async def test_query_no_data(app: App, store, mock_client):
    """查询：已绑定但无数据。"""
    from nonebot_plugin_mi_fitness.core.models import BindRecord

    store.add_bind(
        BindRecord(
            user_id=USER_ID,
            relative_uid=999,
            relative_note="小明",
            xiaomi_uid=999,
        ),
    )

    mock_client.get_heart_rate.return_value = []

    from nonebot_plugin_mi_fitness.handlers.data import heart_rate_cmd

    async with app.test_matcher(heart_rate_cmd) as ctx:
        event = fake_group_message_event_v11(message=Message("/小米心率"))
        ctx.receive_event(bot=_ob11_bot(ctx), event=event)
        ctx.should_call_send(event, "暂无数据")
        ctx.should_finished(heart_rate_cmd)


# endregion

# region 系统命令


@pytest.mark.asyncio
async def test_login_timeout_returns_clear_message():
    """系统命令：二维码登录超时时返回重试提示。"""
    from mi_fitness import AuthError

    from nonebot_plugin_mi_fitness.handlers import system

    with (
        patch.object(system, "qr_login", new=AsyncMock(side_effect=AuthError("扫码超时"))),
        patch.object(system.login_cmd, "finish", new=AsyncMock()) as finish,
    ):
        session = MagicMock()
        session.scene.type.name = "PRIVATE"
        await system.handle_login(session)

    finish.assert_awaited_once_with("二维码已过期，请重新发送「小米登录」")


# endregion
