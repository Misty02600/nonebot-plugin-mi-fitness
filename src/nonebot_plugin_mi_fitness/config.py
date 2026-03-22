from __future__ import annotations

from pydantic import BaseModel


class Config(BaseModel):
    """nonebot-plugin-mi-fitness 配置项。

    当前无需额外配置，登录通过超管发送「小米登录」触发扫码完成。
    """


if not hasattr(Config, "model_fields") and hasattr(Config, "__fields__"):
    Config.model_fields = Config.__fields__  # type: ignore[attr-defined]

