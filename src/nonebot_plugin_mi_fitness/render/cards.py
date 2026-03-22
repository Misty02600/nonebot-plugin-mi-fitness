"""HTML 图片渲染模块。

使用 nonebot-plugin-htmlkit 的 template_to_pic 将健康数据渲染为卡片图片。
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from mi_fitness import DailySummary, HeartRateData, SleepData, StepData, WeightData
from nonebot_plugin_htmlkit import template_to_pic

_CST = timezone(timedelta(hours=8))
_TEMPLATES = Path(__file__).parent / "templates"

# region 工具函数（供模板使用）


def _duration_str(minutes: int) -> str:
    if minutes <= 0:
        return "0m"
    h, m = divmod(minutes, 60)
    if h > 0 and m > 0:
        return f"{h}h {m}m"
    if h > 0:
        return f"{h}h"
    return f"{m}m"


def _ts_to_date(ts: int) -> str:
    if ts <= 0:
        return "--/--"
    return datetime.fromtimestamp(ts, tz=_CST).strftime("%m-%d")


def _ts_to_datetime(ts: int) -> str:
    if ts <= 0:
        return "未知"
    return datetime.fromtimestamp(ts, tz=_CST).strftime("%m-%d %H:%M")


def _today_str() -> str:
    return datetime.now(tz=_CST).strftime("%Y-%m-%d")


_FILTERS = {
    "duration_str": _duration_str,
}


def _detect_image_content_type(content: bytes) -> str:
    """根据常见图片文件头推断 MIME 类型。"""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"BM"):
        return "image/bmp"
    return "application/octet-stream"


def _image_bytes_to_data_uri(content: bytes, content_type: str) -> str:
    """将图片字节编码为 data URI。"""
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


async def _avatar_to_data_uri(url: str) -> str:
    """获取头像并缓存到本地，返回 data URI 供渲染引擎使用。

    缓存策略：
    - 首次请求直接下载并保存图片 + 元数据（etag / last_modified）。
    - 7 天内再次请求直接用本地缓存。
    - 超过 7 天发条件请求（If-None-Match / If-Modified-Since）：
      - 304：刷新 checked_at，不重新下载。
      - 200：替换图片和元数据。
      - 网络失败：继续用旧缓存。
    """
    if not url:
        return ""
    from ..infra.service import cache_dir

    avatar_dir = cache_dir / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.md5(url.encode()).hexdigest()
    cached_img = avatar_dir / f"{url_hash}.png"
    cached_meta = avatar_dir / f"{url_hash}.json"

    check_interval = 604800  # 7 days

    # 读取元数据
    meta: dict[str, str | float] = {}
    if cached_meta.exists():
        try:
            meta = json.loads(cached_meta.read_text("utf-8"))
        except Exception:
            meta = {}

    now = time.time()
    checked_at = float(meta.get("checked_at", 0))
    has_cache = cached_img.exists()

    need_check = not has_cache or (now - checked_at > check_interval)

    if need_check:
        headers: dict[str, str] = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
        }
        if has_cache:
            if etag := meta.get("etag"):
                headers["If-None-Match"] = str(etag)
            if lm := meta.get("last_modified"):
                headers["If-Modified-Since"] = str(lm)

        try:
            async with httpx.AsyncClient(follow_redirects=True) as http:
                resp = await http.get(url, headers=headers, timeout=5.0)

            if resp.status_code == 304:
                # 没变，刷新检查时间
                meta["checked_at"] = now
                cached_meta.write_text(json.dumps(meta), "utf-8")
            elif resp.status_code == 200:
                # 有新内容，更新图片和元数据
                cached_img.write_bytes(resp.content)
                content_type = resp.headers.get("content-type", "").split(";", 1)[0]
                if not content_type.startswith("image/"):
                    content_type = _detect_image_content_type(resp.content)
                meta = {
                    "url": url,
                    "checked_at": now,
                    "etag": resp.headers.get("etag", ""),
                    "last_modified": resp.headers.get("last-modified", ""),
                    "content_type": content_type,
                }
                cached_meta.write_text(json.dumps(meta), "utf-8")
            # 其他状态码：保留旧缓存
        except Exception:
            # 网络失败：保留旧缓存
            if not has_cache:
                return ""

    if not cached_img.exists():
        return ""

    try:
        content = cached_img.read_bytes()
    except Exception:
        return ""

    content_type = str(meta.get("content_type") or "")
    if not content_type.startswith("image/"):
        content_type = _detect_image_content_type(content)

    return _image_bytes_to_data_uri(content, content_type)


# endregion

# region 渲染函数

_MAX_WIDTH = 1260  # 与 style.css 中 .card width 一致


async def render_heart_rate(
    data: HeartRateData, nickname: str = "", icon_url: str = ""
) -> bytes:
    avatar = await _avatar_to_data_uri(icon_url)
    result = await template_to_pic(
        _TEMPLATES,
        "heart_rate.html",
        {
            "data": data,
            "nickname": nickname,
            "icon_url": avatar,
            "date": _today_str(),
        },
        max_width=_MAX_WIDTH,
    )
    # DEBUG: 检查输出图片实际尺寸
    import struct
    if result[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", result[16:24])
        from nonebot.log import logger
        logger.info("render_heart_rate 输出: {}x{} px, {} bytes", w, h, len(result))
    return result


async def render_sleep(
    data: SleepData, nickname: str = "", icon_url: str = ""
) -> bytes:
    avatar = await _avatar_to_data_uri(icon_url)
    return await template_to_pic(
        _TEMPLATES,
        "sleep.html",
        {
            "data": data,
            "nickname": nickname,
            "icon_url": avatar,
            "date": _today_str(),
            "duration_str": _duration_str,
        },
        max_width=_MAX_WIDTH,
    )


async def render_steps(
    data: StepData, nickname: str = "", icon_url: str = ""
) -> bytes:
    avatar = await _avatar_to_data_uri(icon_url)
    return await template_to_pic(
        _TEMPLATES,
        "steps.html",
        {
            "data": data,
            "nickname": nickname,
            "icon_url": avatar,
            "date": _today_str(),
        },
        max_width=_MAX_WIDTH,
    )


async def render_weight(
    data: WeightData, nickname: str = "", icon_url: str = ""
) -> bytes:
    avatar = await _avatar_to_data_uri(icon_url)
    return await template_to_pic(
        _TEMPLATES,
        "weight.html",
        {
            "data": data,
            "nickname": nickname,
            "icon_url": avatar,
            "date": _today_str(),
            "ts_to_datetime": _ts_to_datetime,
        },
        max_width=_MAX_WIDTH,
    )


async def render_daily(
    summary: DailySummary, nickname: str = "", icon_url: str = ""
) -> bytes:
    avatar = await _avatar_to_data_uri(icon_url)
    return await template_to_pic(
        _TEMPLATES,
        "daily.html",
        {
            "summary": summary,
            "nickname": nickname,
            "icon_url": avatar,
            "duration_str": _duration_str,
        },
        max_width=_MAX_WIDTH,
    )


async def render_heart_rate_weekly(
    data_list: list[HeartRateData], nickname: str = "", icon_url: str = ""
) -> bytes:
    valid = [d for d in data_list if d.avg_hr > 0]
    avg_hr = sum(d.avg_hr for d in valid) // len(valid) if valid else 0
    max_hr = max((d.max_hr for d in valid), default=0)
    min_hr = min((d.min_hr for d in valid if d.min_hr > 0), default=0)
    avatar = await _avatar_to_data_uri(icon_url)
    return await template_to_pic(
        _TEMPLATES,
        "heart_rate_weekly.html",
        {
            "valid_data": valid,
            "avg_hr": avg_hr,
            "max_hr": max_hr,
            "min_hr": min_hr,
            "nickname": nickname,
            "icon_url": avatar,
            "date": _today_str(),
            "ts_to_date": _ts_to_date,
        },
        max_width=_MAX_WIDTH,
    )


async def render_sleep_weekly(
    data_list: list[SleepData], nickname: str = "", icon_url: str = ""
) -> bytes:
    valid = [d for d in data_list if d.total_duration > 0]
    avg_duration = sum(d.total_duration for d in valid) // len(valid) if valid else 0
    avg_score = sum(d.sleep_score for d in valid) // len(valid) if valid else 0
    avg_deep = (
        sum(d.sleep_deep_duration for d in valid) // len(valid) if valid else 0
    )
    avatar = await _avatar_to_data_uri(icon_url)
    return await template_to_pic(
        _TEMPLATES,
        "sleep_weekly.html",
        {
            "valid_data": valid,
            "avg_duration": avg_duration,
            "avg_score": avg_score,
            "avg_deep": avg_deep,
            "nickname": nickname,
            "icon_url": avatar,
            "date": _today_str(),
            "ts_to_date": _ts_to_date,
            "duration_str": _duration_str,
        },
        max_width=_MAX_WIDTH,
    )


async def render_steps_weekly(
    data_list: list[StepData], nickname: str = "", icon_url: str = ""
) -> bytes:
    valid = [d for d in data_list if d.steps > 0]
    total_steps = sum(d.steps for d in valid)
    avg_steps = total_steps // len(valid) if valid else 0
    total_dist = sum(d.distance for d in valid)
    total_cal = sum(d.calories for d in valid)
    avatar = await _avatar_to_data_uri(icon_url)
    return await template_to_pic(
        _TEMPLATES,
        "steps_weekly.html",
        {
            "valid_data": valid,
            "total_steps": total_steps,
            "avg_steps": avg_steps,
            "total_dist": total_dist,
            "total_cal": total_cal,
            "nickname": nickname,
            "icon_url": avatar,
            "date": _today_str(),
            "ts_to_date": _ts_to_date,
        },
        max_width=_MAX_WIDTH,
    )


# endregion
