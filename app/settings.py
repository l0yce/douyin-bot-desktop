"""QSettings 持久化用户偏好。"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSettings


def settings() -> QSettings:
    """用户偏好。

    设置了 `DOUYIN_DESKTOP_DATA_DIR`（测试与沙箱运行）时改用该目录下的 ini 文件：
    测试读写的是临时目录，既不会污染真实用户的注册表项，用户的偏好也不会反过来
    改变测试与截图的结果。
    """
    override = os.environ.get("DOUYIN_DESKTOP_DATA_DIR")
    if override:
        path = Path(override) / "desktop-settings.ini"
        path.parent.mkdir(parents=True, exist_ok=True)
        return QSettings(str(path), QSettings.IniFormat)
    return QSettings("douyin-bot", "desktop")


def get(key: str, default=None):
    return settings().value(key, default)


def put(key: str, value) -> None:
    s = settings()
    s.setValue(key, value)
    s.sync()
