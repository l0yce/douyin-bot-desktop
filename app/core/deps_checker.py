"""启动前依赖体检：Python / Node / Firefox / Playwright / 端口。"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

from . import paths


class CheckResult:
    def __init__(self, name: str, ok: bool, detail: str, fix: str = ""):
        self.name = name
        self.ok = ok
        self.detail = detail
        self.fix = fix  # 修复指引（UI 中可点击展示）


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def run_all(skip_python: bool = False, owned_ports=()) -> list[CheckResult]:
    results: list[CheckResult] = []

    # 1. Python 版本（打包版用内嵌 runtime，跳过）
    if not skip_python:
        v = sys.version_info
        ok = v >= (3, 11)
        results.append(CheckResult(
            "Python ≥ 3.11", ok, f"当前 {v.major}.{v.minor}.{v.micro}",
            "请安装 Python 3.11+：https://www.python.org/downloads/"))

    # 2. Node ≥ 22
    node = paths.node_exe()
    node_ok, node_ver = False, "未找到"
    try:
        p = subprocess.run([str(node), "--version"], capture_output=True, text=True, timeout=10,
                           shell=False, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        node_ver = (p.stdout or "").strip()
        node_ok = p.returncode == 0 and int(node_ver.lstrip("v").split(".")[0]) >= 22
    except Exception:
        pass
    results.append(CheckResult(
        "Node.js ≥ 22", node_ok, node_ver,
        "桌面版推荐使用内嵌 Node；开发模式请安装 Node 22 LTS 或 24 LTS：https://nodejs.org/"))

    # 3. 系统浏览器（桌面版直接用用户已装的 Edge/Chrome，不用 Playwright 自带 Firefox）
    found = _find_system_browser()
    results.append(CheckResult(
        "系统浏览器（Edge/Chrome）", bool(found), str(found or "未找到"),
        "Windows 10/11 一般自带 Edge；也可安装 Chrome。机器人配置 account.engine=edge 即可使用"))

    # 4. 端口占用预检
    for port, name in [(8790, "面板端口 8790"), (8791, "控制端口 8791"), (18765, "幕间端口 18765")]:
        free = port in owned_ports or _port_free(port)
        results.append(CheckResult(
            name, free, "本程序使用中" if port in owned_ports else ("可用" if free else "被占用"),
            "关闭占用该端口的程序（netstat -ano | findstr 端口号），或已有一个 douyin-bot 在运行"))

    # 5. 机器人 config.json
    cfg = paths.bot_dir() / "config" / "config.json"
    results.append(CheckResult(
        "机器人配置 config.json", cfg.exists(), str(cfg),
        "在首次运行向导或状态页完成配置（复制 config.example.json 并填写 owner/ai）"))

    return results


def _find_system_browser() -> Path | None:
    """按 Edge → Chrome 顺序查找系统已安装的浏览器。"""
    pf = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    pf86 = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    localappdata = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = [
        pf / "Microsoft/Edge/Application/msedge.exe",
        pf86 / "Microsoft/Edge/Application/msedge.exe",
        pf / "Google/Chrome/Application/chrome.exe",
        pf86 / "Google/Chrome/Application/chrome.exe",
        localappdata / "Google/Chrome/Application/chrome.exe",
    ]
    for c in candidates:
        try:
            if c.exists():
                return c
        except OSError:
            continue
    return None
