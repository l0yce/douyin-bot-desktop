"""资源路径解析：开发模式与 PyInstaller 打包模式双兼容。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def app_root() -> Path:
    """应用根目录（含 backend/）。"""
    if is_frozen():
        # PyInstaller onedir：资源在 exe 同级目录（spec 中配置）
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[2]


def backend_dir() -> Path:
    return app_root() / "backend"


def panel_dir() -> Path:
    return backend_dir() / "douyin-bot-panel"


def bot_dir() -> Path:
    return data_dir() / "douyin-friend-ai-bot"


def bot_source_dir() -> Path:
    return backend_dir() / "douyin-friend-ai-bot"


def interlude_dir() -> Path:
    return data_dir() / "douyin-interlude"


def interlude_source_dir() -> Path:
    return backend_dir() / "douyin-interlude"


def data_dir() -> Path:
    """用户可写数据目录：%APPDATA%/douyin-bot（开发时也在同一位置，保持一致）。"""
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    p = Path(os.environ.get("DOUYIN_DESKTOP_DATA_DIR", str(Path(base) / "douyin-bot")))
    p.mkdir(parents=True, exist_ok=True)
    return p


def python_exe() -> Path:
    """当前 Python 解释器（打包后为内嵌 runtime）。"""
    if is_frozen():
        bundled = Path(sys.executable).resolve().parent / "runtime" / "python" / "python.exe"
        if bundled.exists():
            return bundled
        raise FileNotFoundError("缺少内嵌 Python，请重新解压完整程序目录")
    return Path(sys.executable)


def node_exe() -> Path:
    """Node 解释器：优先内嵌，其次系统 PATH。"""
    if is_frozen():
        bundled = Path(sys.executable).resolve().parent / "runtime" / "node" / "node.exe"
        if bundled.exists():
            return bundled
        raise FileNotFoundError("缺少内嵌 Node，请重新解压完整程序目录")
    return Path("node")


def logs_dir() -> Path:
    p = data_dir() / "desktop-logs"
    p.mkdir(parents=True, exist_ok=True)
    return p
