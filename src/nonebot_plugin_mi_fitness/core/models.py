"""核心数据模型。"""

from __future__ import annotations

import msgspec


class BindRecord(msgspec.Struct):
    """用户绑定记录。

    Attributes:
        user_id: 平台用户 ID（如 QQ 号）。
        relative_uid: 亲友 UID（MiSDK FamilyMember.relative_uid）。
        relative_note: 亲友备注名（用于显示）。
        xiaomi_uid: 用户提供的小米 UID（邀请阶段使用）。
        nickname: 小米昵称（渲染卡片用）。
        icon_url: 小米头像 URL（渲染卡片用）。
    """

    user_id: str
    relative_uid: int = 0
    relative_note: str = ""
    xiaomi_uid: int = 0
    nickname: str = ""
    icon_url: str = ""
    profile_checked_at: float = 0.0


class PluginData(msgspec.Struct):
    """插件全局数据。

    Attributes:
        binds: 所有用户的全局绑定记录。
    """

    binds: list[BindRecord] = msgspec.field(default_factory=list)
