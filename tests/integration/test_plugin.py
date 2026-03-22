import pytest
from nonebug import App

from fake import fake_group_message_event_v11


@pytest.mark.asyncio
async def test_plugin_metadata(app: App):
    """测试插件元数据加载是否正常"""
    from nonebot_plugin_mi_fitness import __plugin_meta__

    assert __plugin_meta__.name == "小米运动健康"
    assert "亲友共享" in __plugin_meta__.description
    assert __plugin_meta__.type == "application"


@pytest.mark.asyncio
async def test_handlers_loaded(app: App):
    """测试命令处理器加载是否正常"""
    from nonebot_plugin_mi_fitness.handlers import bind, data, system

    assert bind is not None
    assert data is not None
    assert system is not None


@pytest.mark.asyncio
async def test_fake_event():
    """测试虚拟事件创建"""
    from nonebot.adapters.onebot.v11 import Message

    event = fake_group_message_event_v11(message=Message("测试消息"))
    assert event.message_type == "group"
    assert event.user_id == 12345678
    assert str(event.message) == "测试消息"

