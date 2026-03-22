"""服务实例化

集中管理 MiSDK 客户端和数据存储实例。
登录方式：超管发送「小米登录」→ Bot 生成二维码 → 超管用小米 APP 扫码。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

import nonebot_plugin_localstore as store
from mi_fitness import MiHealthClient, XiaomiAuth
from nonebot.log import logger

from .store import PluginStore

# 数据路径
data_dir = store.get_data_dir("nonebot_plugin_mi_fitness")
cache_dir = store.get_cache_dir("nonebot_plugin_mi_fitness")

# 数据存储
plugin_store = PluginStore(data_dir / "binds.json")

# region MiSDK 认证与客户端

auth: XiaomiAuth | None = None
mi_client: MiHealthClient | None = None

_token_path = data_dir / "mi_token.json"
_TOKEN_RELOGIN_REQUIRED = "Token 已过期，请超管发送「小米登录」重新扫码"


class TokenRecoverRequiredError(RuntimeError):
    """当前 token 无法自动恢复，需要人工重新登录。"""


async def _close_cached_clients() -> None:
    """关闭当前缓存的认证与客户端实例，避免连接泄漏。"""
    global auth, mi_client

    if mi_client is not None:
        try:
            await mi_client.close()
        except Exception:
            logger.debug("关闭 MiHealthClient 时出现异常，忽略")

    if auth is not None:
        try:
            await auth.close()
        except Exception:
            logger.debug("关闭 XiaomiAuth 时出现异常，忽略")

    auth = None
    mi_client = None


async def shutdown_cleanup() -> None:
    """插件退出时释放 MiSDK 相关资源。"""
    await _close_cached_clients()


_ResultT = TypeVar("_ResultT")


async def invoke_with_token_retry(
    operation: Callable[[MiHealthClient], Awaitable[_ResultT]],
    client: MiHealthClient | None = None,
) -> _ResultT:
    """统一执行 MiSDK 调用：Token 过期时自动重登并重试一次。

    Args:
        operation: 接收 MiHealthClient 的异步操作函数。
        client: 可选的客户端对象。若为 None，将调用 ensure_client() 获取。
    """
    from mi_fitness import TokenExpiredError

    if client is None:
        client = await ensure_client()

    try:
        return await operation(client)
    except TokenExpiredError:
        client = await auto_relogin()

    try:
        return await operation(client)
    except TokenExpiredError as exc:
        await _close_cached_clients()
        raise TokenRecoverRequiredError(_TOKEN_RELOGIN_REQUIRED) from exc


async def qr_login(
    qr_callback: Callable[[str, str], Awaitable[None]],
    *,
    poll_interval: float = 2.0,
    max_wait: float = 300.0,
) -> MiHealthClient:
    """通过二维码扫码登录。

    Args:
        qr_callback: 二维码展示回调。接收 ``(qr_image_url, login_url)``。
        poll_interval: 长轮询间隔（秒）。
        max_wait: 扫码超时时间（秒）。

    Returns:
        已认证的 MiHealthClient。
    """
    global auth, mi_client
    logger.info("开始二维码登录流程，准备生成二维码")

    await _close_cached_clients()

    local_auth = XiaomiAuth()
    try:
        await local_auth.login_qr(
            qr_callback=qr_callback,
            poll_interval=poll_interval,
            max_wait=max_wait,
        )
        local_auth.save_token(_token_path)
        auth = local_auth
        mi_client = MiHealthClient(auth)
        logger.info("二维码扫码登录成功, user_id={}", auth.token.user_id)
        return mi_client
    except Exception:
        await local_auth.close()
        raise


async def ensure_client() -> MiHealthClient:
    """确保 MiHealthClient 已初始化并完成认证。

    从本地 token 文件恢复；若无 token 则抛出 RuntimeError
    提示超管发送「小米登录」。

    Returns:
        已认证的 MiHealthClient 实例。

    Raises:
        RuntimeError: 未登录。
    """
    global auth, mi_client

    if mi_client is not None and auth is not None and auth.is_authenticated:
        return mi_client

    if _token_path.exists():
        try:
            local_auth = XiaomiAuth.from_token(_token_path)
            if local_auth.is_authenticated:
                auth = local_auth
                mi_client = MiHealthClient(auth)
                logger.info("从本地 token 恢复小米账号登录")
                return mi_client
        except Exception:
            logger.warning("token 文件加载失败")

    raise RuntimeError("小米账号未登录")


async def auto_relogin() -> MiHealthClient:
    """Token 过期后尝试从 token 文件重新加载。

    若 token 文件也无效则抛出异常提示超管重新登录。

    Raises:
        RuntimeError: 需要重新登录。
    """
    global auth, mi_client

    await _close_cached_clients()

    if _token_path.exists():
        try:
            local_auth = XiaomiAuth.from_token(_token_path)
            if local_auth.is_authenticated:
                auth = local_auth
                mi_client = MiHealthClient(auth)
                logger.info("从 token 文件重新加载成功")
                return mi_client
        except Exception:
            pass

    raise TokenRecoverRequiredError(_TOKEN_RELOGIN_REQUIRED)


async def startup_check() -> None:
    """启动时检测 token 是否有效。"""
    global auth, mi_client

    if not _token_path.exists():
        logger.warning("未找到小米 token 文件，请超级用户发送「小米登录」完成首次登录")
        return

    try:
        local_auth = XiaomiAuth.from_token(_token_path)
        if not local_auth.is_authenticated:
            logger.warning(
                "小米 token 文件内容不完整，请超级用户发送「小米登录」重新登录"
            )
            return
        auth = local_auth
        mi_client = MiHealthClient(auth)
        logger.info("已从本地 token 恢复小米账号")
    except Exception:
        logger.warning("小米 token 文件加载失败，请超级用户发送「小米登录」重新登录")
        return

    from mi_fitness import TokenExpiredError

    try:
        await mi_client.get_relatives()
        logger.info("小米 token 验证通过 ✅")
    except TokenExpiredError:
        logger.warning("小米 token 已过期，请超级用户发送「小米登录」重新登录")
        await _close_cached_clients()
    except Exception as exc:
        logger.warning("小米 token 验证时出错: {}，token 可能仍然有效", exc)


# endregion

