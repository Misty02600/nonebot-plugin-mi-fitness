"""头像缓存 (_avatar_to_data_uri) 单元测试。"""

import hashlib
import json
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from nonebug import App

TEST_URL = "https://example.com/avatar.png"
URL_HASH = hashlib.md5(TEST_URL.encode()).hexdigest()
FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _setup_cache_dir(tmp_path: Path):
    """返回 avatars 目录并 mock cache_dir。"""
    avatar_dir = tmp_path / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    return avatar_dir


@pytest.mark.asyncio
async def test_fresh_download(app: App, tmp_path: Path):
    """首次请求：下载图片并写入缓存文件和元数据。"""
    _setup_cache_dir(tmp_path)

    response = httpx.Response(
        200,
        content=FAKE_PNG,
        headers={"etag": '"abc123"', "last-modified": "Sat, 01 Jan 2026 00:00:00 GMT"},
    )

    with (
        patch("nonebot_plugin_mi_fitness.infra.service.cache_dir", tmp_path),
        patch("httpx.AsyncClient.get", return_value=response),
    ):
        from nonebot_plugin_mi_fitness.render import _avatar_to_data_uri

        result = await _avatar_to_data_uri(TEST_URL)

    cached_img = tmp_path / "avatars" / f"{URL_HASH}.png"
    cached_meta = tmp_path / "avatars" / f"{URL_HASH}.json"

    assert result.startswith("data:image/png;base64,")
    assert cached_img.exists()
    assert cached_img.read_bytes() == FAKE_PNG
    meta = json.loads(cached_meta.read_text("utf-8"))
    assert meta["etag"] == '"abc123"'
    assert meta["content_type"] == "image/png"
    assert meta["url"] == TEST_URL


@pytest.mark.asyncio
async def test_cache_hit_within_interval(app: App, tmp_path: Path):
    """缓存未过期：不发网络请求，直接返回本地路径。"""
    avatar_dir = _setup_cache_dir(tmp_path)
    cached_img = avatar_dir / f"{URL_HASH}.png"
    cached_meta = avatar_dir / f"{URL_HASH}.json"
    cached_img.write_bytes(FAKE_PNG)
    cached_meta.write_text(
        json.dumps({"url": TEST_URL, "checked_at": time.time(), "etag": "", "last_modified": ""}),
        "utf-8",
    )

    with (
        patch("nonebot_plugin_mi_fitness.infra.service.cache_dir", tmp_path),
        patch("httpx.AsyncClient.get", side_effect=AssertionError("不应发出网络请求")),
    ):
        from nonebot_plugin_mi_fitness.render import _avatar_to_data_uri

        result = await _avatar_to_data_uri(TEST_URL)

    assert result.startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_conditional_304(app: App, tmp_path: Path):
    """缓存过期 + 304 Not Modified：不替换图片，刷新 checked_at。"""
    avatar_dir = _setup_cache_dir(tmp_path)
    cached_img = avatar_dir / f"{URL_HASH}.png"
    cached_meta = avatar_dir / f"{URL_HASH}.json"
    cached_img.write_bytes(FAKE_PNG)
    old_checked = time.time() - 700000  # 超过 7 天
    cached_meta.write_text(
        json.dumps({"url": TEST_URL, "checked_at": old_checked, "etag": '"abc"', "last_modified": ""}),
        "utf-8",
    )

    response = httpx.Response(304)

    with (
        patch("nonebot_plugin_mi_fitness.infra.service.cache_dir", tmp_path),
        patch("httpx.AsyncClient.get", return_value=response),
    ):
        from nonebot_plugin_mi_fitness.render import _avatar_to_data_uri

        result = await _avatar_to_data_uri(TEST_URL)

    assert result.startswith("data:image/png;base64,")
    # 图片内容不变
    assert cached_img.read_bytes() == FAKE_PNG
    # checked_at 已刷新
    meta = json.loads(cached_meta.read_text("utf-8"))
    assert meta["checked_at"] > old_checked


@pytest.mark.asyncio
async def test_conditional_200_updates_cache(app: App, tmp_path: Path):
    """缓存过期 + 200：替换图片和元数据。"""
    avatar_dir = _setup_cache_dir(tmp_path)
    cached_img = avatar_dir / f"{URL_HASH}.png"
    cached_meta = avatar_dir / f"{URL_HASH}.json"
    cached_img.write_bytes(b"old image")
    cached_meta.write_text(
        json.dumps({"url": TEST_URL, "checked_at": 0, "etag": '"old"', "last_modified": ""}),
        "utf-8",
    )

    new_png = b"new image data"
    response = httpx.Response(
        200,
        content=new_png,
        headers={"etag": '"new-etag"', "last-modified": "Mon, 07 Mar 2026 00:00:00 GMT"},
    )

    with (
        patch("nonebot_plugin_mi_fitness.infra.service.cache_dir", tmp_path),
        patch("httpx.AsyncClient.get", return_value=response),
    ):
        from nonebot_plugin_mi_fitness.render import _avatar_to_data_uri

        result = await _avatar_to_data_uri(TEST_URL)

    assert result.startswith("data:application/octet-stream;base64,")
    assert cached_img.read_bytes() == new_png
    meta = json.loads(cached_meta.read_text("utf-8"))
    assert meta["etag"] == '"new-etag"'


@pytest.mark.asyncio
async def test_network_failure_uses_old_cache(app: App, tmp_path: Path):
    """网络失败时使用旧缓存。"""
    avatar_dir = _setup_cache_dir(tmp_path)
    cached_img = avatar_dir / f"{URL_HASH}.png"
    cached_meta = avatar_dir / f"{URL_HASH}.json"
    cached_img.write_bytes(FAKE_PNG)
    cached_meta.write_text(
        json.dumps({"url": TEST_URL, "checked_at": 0, "etag": "", "last_modified": ""}),
        "utf-8",
    )

    with (
        patch("nonebot_plugin_mi_fitness.infra.service.cache_dir", tmp_path),
        patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("connection refused")),
    ):
        from nonebot_plugin_mi_fitness.render import _avatar_to_data_uri

        result = await _avatar_to_data_uri(TEST_URL)

    assert result.startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_network_failure_no_cache_returns_empty(app: App, tmp_path: Path):
    """没有缓存 + 网络失败 → 返回空字符串。"""
    _setup_cache_dir(tmp_path)

    with (
        patch("nonebot_plugin_mi_fitness.infra.service.cache_dir", tmp_path),
        patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("connection refused")),
    ):
        from nonebot_plugin_mi_fitness.render import _avatar_to_data_uri

        result = await _avatar_to_data_uri(TEST_URL)

    assert result == ""


@pytest.mark.asyncio
async def test_empty_url_returns_empty(app: App):
    """空 URL 直接返回空字符串。"""
    from nonebot_plugin_mi_fitness.render import _avatar_to_data_uri

    assert await _avatar_to_data_uri("") == ""

