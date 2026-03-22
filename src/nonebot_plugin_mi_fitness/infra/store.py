"""JSON 数据持久化 Store。"""

from __future__ import annotations

from pathlib import Path

import msgspec

from ..core.models import BindRecord, PluginData


class PluginStore:
    """插件数据管理器。

    职责：
    - 全局用户绑定的读写
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.data: PluginData = self._load()

    def _load(self) -> PluginData:
        if self._path.exists():
            return msgspec.json.decode(self._path.read_bytes(), type=PluginData)
        return PluginData()

    def save(self) -> None:
        self._path.write_bytes(msgspec.json.encode(self.data))

    # region 绑定管理

    def add_bind(self, record: BindRecord) -> None:
        """添加或更新绑定。"""
        for i, existing_record in enumerate(self.data.binds):
            if existing_record.user_id == record.user_id:
                self.data.binds[i] = record
                self.save()
                return
        self.data.binds.append(record)
        self.save()

    def remove_bind(self, user_id: str) -> bool:
        """移除绑定，返回是否成功。"""
        before = len(self.data.binds)
        self.data.binds = [
            record for record in self.data.binds if record.user_id != user_id
        ]
        if len(self.data.binds) < before:
            self.save()
            return True
        return False

    def get_bind(self, user_id: str) -> BindRecord | None:
        """获取用户绑定。"""
        for record in self.data.binds:
            if record.user_id == user_id:
                return record
        return None

    def get_bind_by_xiaomi_uid(self, xiaomi_uid: int) -> BindRecord | None:
        """获取绑定到指定小米 UID 的记录。"""
        for record in self.data.binds:
            if record.xiaomi_uid == xiaomi_uid:
                return record
        return None

    def get_all_binds(self) -> list[BindRecord]:
        """获取所有绑定。"""
        return list(self.data.binds)

    # endregion
