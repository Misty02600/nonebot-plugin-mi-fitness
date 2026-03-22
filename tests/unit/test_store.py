"""Store 数据持久化单元测试。"""

from pathlib import Path

import pytest
from nonebug import App


@pytest.mark.asyncio
async def test_add_and_get_bind(app: App, tmp_path: Path):
    from nonebot_plugin_mi_fitness.core.models import BindRecord
    from nonebot_plugin_mi_fitness.infra.store import PluginStore

    store = PluginStore(tmp_path / "test.json")
    record = BindRecord(
        user_id="12345",
        relative_uid=111,
        relative_note="小明",
        xiaomi_uid=111,
    )
    store.add_bind(record)
    result = store.get_bind("12345")
    assert result is not None
    assert result.relative_uid == 111
    assert result.relative_note == "小明"


@pytest.mark.asyncio
async def test_get_bind_not_found(app: App, tmp_path: Path):
    from nonebot_plugin_mi_fitness.infra.store import PluginStore

    store = PluginStore(tmp_path / "test.json")
    result = store.get_bind("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_update_bind(app: App, tmp_path: Path):
    from nonebot_plugin_mi_fitness.core.models import BindRecord
    from nonebot_plugin_mi_fitness.infra.store import PluginStore

    store = PluginStore(tmp_path / "test.json")
    record1 = BindRecord(user_id="12345", relative_uid=0, xiaomi_uid=111)
    store.add_bind(record1)

    record2 = BindRecord(
        user_id="12345",
        relative_uid=111,
        relative_note="小明",
        xiaomi_uid=111,
    )
    store.add_bind(record2)

    result = store.get_bind("12345")
    assert result is not None
    assert result.relative_uid == 111

    # 确保没有重复
    all_binds = store.get_all_binds()
    assert len(all_binds) == 1


@pytest.mark.asyncio
async def test_remove_bind(app: App, tmp_path: Path):
    from nonebot_plugin_mi_fitness.core.models import BindRecord
    from nonebot_plugin_mi_fitness.infra.store import PluginStore

    store = PluginStore(tmp_path / "test.json")
    record = BindRecord(user_id="12345", relative_uid=111)
    store.add_bind(record)

    assert store.remove_bind("12345") is True
    assert store.get_bind("12345") is None


@pytest.mark.asyncio
async def test_remove_nonexistent_bind(app: App, tmp_path: Path):
    from nonebot_plugin_mi_fitness.infra.store import PluginStore

    store = PluginStore(tmp_path / "test.json")
    assert store.remove_bind("12345") is False


@pytest.mark.asyncio
async def test_get_all_binds(app: App, tmp_path: Path):
    from nonebot_plugin_mi_fitness.core.models import BindRecord
    from nonebot_plugin_mi_fitness.infra.store import PluginStore

    store = PluginStore(tmp_path / "test.json")
    store.add_bind(BindRecord(user_id="u1", relative_uid=1))
    store.add_bind(BindRecord(user_id="u2", relative_uid=2))
    store.add_bind(BindRecord(user_id="u3", relative_uid=3))

    all_binds = store.get_all_binds()
    assert len(all_binds) == 3


@pytest.mark.asyncio
async def test_get_all_binds_empty(app: App, tmp_path: Path):
    from nonebot_plugin_mi_fitness.infra.store import PluginStore

    store = PluginStore(tmp_path / "test.json")
    assert store.get_all_binds() == []


@pytest.mark.asyncio
async def test_persistence(app: App, tmp_path: Path):
    """测试数据持久化——重新加载后数据是否保留。"""
    from nonebot_plugin_mi_fitness.core.models import BindRecord
    from nonebot_plugin_mi_fitness.infra.store import PluginStore

    path = tmp_path / "persist.json"

    store1 = PluginStore(path)
    store1.add_bind(BindRecord(user_id="u1", relative_uid=100))

    # 重新加载
    store2 = PluginStore(path)
    result = store2.get_bind("u1")
    assert result is not None
    assert result.relative_uid == 100


@pytest.mark.asyncio
async def test_get_bind_by_xiaomi_uid(app: App, tmp_path: Path):
    """测试按小米 UID 查询绑定记录。"""
    from nonebot_plugin_mi_fitness.core.models import BindRecord
    from nonebot_plugin_mi_fitness.infra.store import PluginStore

    store = PluginStore(tmp_path / "test.json")
    store.add_bind(BindRecord(user_id="u1", relative_uid=100, xiaomi_uid=888))

    record = store.get_bind_by_xiaomi_uid(888)
    assert record is not None
    assert record.user_id == "u1"

    not_found = store.get_bind_by_xiaomi_uid(999)
    assert not_found is None

