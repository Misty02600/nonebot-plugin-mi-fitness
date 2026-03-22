from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

USER_ID = "12345678"


@pytest.fixture
def store(tmp_path: Path, after_nonebot_init: None):
    from nonebot_plugin_mi_fitness.core.models import PluginData
    from nonebot_plugin_mi_fitness.infra.service import plugin_store

    old_data = plugin_store.data
    old_path = plugin_store._path
    plugin_store.data = PluginData()
    plugin_store._path = tmp_path / "test.json"
    try:
        yield plugin_store
    finally:
        plugin_store.data = old_data
        plugin_store._path = old_path


@pytest.mark.asyncio
async def test_refresh_bind_profile_updates_relative_note_without_overwriting_nickname(
    store,
):
    from nonebot_plugin_mi_fitness.core.models import BindRecord
    from nonebot_plugin_mi_fitness.handlers.data import _refresh_bind_profile

    bind = BindRecord(
        user_id=USER_ID,
        relative_uid=999,
        relative_note="旧备注",
        nickname="原昵称",
        icon_url="",
    )
    store.add_bind(bind)

    member = MagicMock()
    member.relative_uid = 999
    member.relative_note = "新备注"
    member.relative_icon = "https://example.com/avatar.png"

    client = AsyncMock()
    client.get_relatives.return_value = [member]

    await _refresh_bind_profile(client, bind)

    refreshed = store.get_bind(USER_ID)
    assert refreshed is not None
    assert refreshed.relative_note == "新备注"
    assert refreshed.nickname == "原昵称"
    assert refreshed.icon_url == "https://example.com/avatar.png"
    assert refreshed.profile_checked_at > 0

