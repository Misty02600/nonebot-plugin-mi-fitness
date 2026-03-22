from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from mi_fitness import TokenExpiredError


@pytest.fixture
def service_module(after_nonebot_init: None):
    from nonebot_plugin_mi_fitness.infra import service

    return service


@pytest.fixture
def restore_service_state(service_module):
    old_auth = service_module.auth
    old_client = service_module.mi_client
    old_token_path = service_module._token_path
    try:
        yield service_module
    finally:
        service_module.auth = old_auth
        service_module.mi_client = old_client
        service_module._token_path = old_token_path


@pytest.mark.asyncio
async def test_invoke_with_token_retry_uses_reloaded_client(restore_service_state):
    service = restore_service_state
    stale_client = AsyncMock()
    fresh_client = AsyncMock()
    operation = AsyncMock(side_effect=[TokenExpiredError("expired"), "ok"])

    with patch.object(
        service,
        "auto_relogin",
        new=AsyncMock(return_value=fresh_client),
    ) as auto_relogin:
        result = await service.invoke_with_token_retry(operation, stale_client)

    assert result == "ok"
    auto_relogin.assert_awaited_once()
    assert operation.await_args_list == [call(stale_client), call(fresh_client)]


@pytest.mark.asyncio
async def test_invoke_with_token_retry_raises_runtime_error_after_second_expiry(
    restore_service_state,
):
    service = restore_service_state
    stale_client = AsyncMock()
    fresh_client = AsyncMock()
    operation = AsyncMock(
        side_effect=[TokenExpiredError("expired"), TokenExpiredError("expired again")]
    )

    with patch.object(
        service,
        "auto_relogin",
        new=AsyncMock(return_value=fresh_client),
    ) as auto_relogin, patch.object(
        service,
        "_close_cached_clients",
        new=AsyncMock(),
    ) as close_cached_clients:
        with pytest.raises(service.TokenRecoverRequiredError, match="Token 已过期"):
            await service.invoke_with_token_retry(operation, stale_client)

    auto_relogin.assert_awaited_once()
    close_cached_clients.assert_awaited_once()
    assert operation.await_args_list == [call(stale_client), call(fresh_client)]


@pytest.mark.asyncio
async def test_startup_check_closes_cached_resources_when_token_expired(
    tmp_path: Path,
    restore_service_state,
    monkeypatch: pytest.MonkeyPatch,
):
    service = restore_service_state
    token_path = tmp_path / "mi_token.json"
    token_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(service, "_token_path", token_path)

    fake_auth = MagicMock()
    fake_auth.is_authenticated = True
    fake_auth.close = AsyncMock()

    fake_client = AsyncMock()
    fake_client.get_relatives.side_effect = TokenExpiredError("expired")
    fake_client.close = AsyncMock()

    with patch.object(service.XiaomiAuth, "from_token", return_value=fake_auth), patch.object(
        service,
        "MiHealthClient",
        return_value=fake_client,
    ):
        await service.startup_check()

    assert service.auth is None
    assert service.mi_client is None
    fake_client.close.assert_awaited_once()
    fake_auth.close.assert_awaited_once()

