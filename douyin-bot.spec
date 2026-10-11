# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：douyin-bot 桌面版（onedir）。"""
import os
from pathlib import Path

ROOT = Path(SPECPATH)  # noqa: F821
BACKEND = ROOT / "backend"

datas = [
    (str(ROOT / "app" / "ui" / "assets"), "app/ui/assets"),
    (str(ROOT / "LICENSE"), "."),
    (str(BACKEND / "douyin-bot-panel" / "app"), "backend/douyin-bot-panel/app"),
    (str(BACKEND / "douyin-bot-panel" / "static"), "backend/douyin-bot-panel/static"),
    (str(BACKEND / "douyin-interlude" / "bridge.cjs"), "backend/douyin-interlude"),
    (str(BACKEND / "douyin-interlude" / "worker.cjs"), "backend/douyin-interlude"),
    (str(BACKEND / "douyin-interlude" / "bridge-config.example.json"), "backend/douyin-interlude"),
    (str(BACKEND / "douyin-interlude" / "upstream" / "lib"), "backend/douyin-interlude/upstream/lib"),
    (str(BACKEND / "douyin-interlude" / "hdsi-admin.cjs"), "backend/douyin-interlude"),
    (str(BACKEND / "douyin-interlude" / "message-grounding.cjs"), "backend/douyin-interlude"),
    (str(BACKEND / "douyin-friend-ai-bot" / "src"), "backend/douyin-friend-ai-bot/src"),
    (str(BACKEND / "douyin-friend-ai-bot" / "config" / "config.example.json"), "backend/douyin-friend-ai-bot/config"),
    (str(BACKEND / "douyin-friend-ai-bot" / "config" / "persona.example.md"), "backend/douyin-friend-ai-bot/config"),
]
# 幕间引擎 node_modules 整体打入
if (BACKEND / "douyin-interlude" / "node_modules").exists():
    datas.append((str(BACKEND / "douyin-interlude" / "node_modules"), "backend/douyin-interlude/node_modules"))

hiddenimports = [
    "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
]

a = Analysis(
    ["main.py"],  # noqa: F821
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy"],
    noarchive=False,
)
a.datas = [entry for entry in a.datas if "__pycache__" not in entry[0] and not entry[0].endswith(".pyc")]
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="douyin-bot-desktop",
    console=False,
    icon=str(ROOT / "app/ui/assets/app-icon.ico"),
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="douyin-bot-desktop",
)
