"""一键打包脚本：PyInstaller onedir + 内嵌 Python/Node 运行时。

用法：
    python build.py            # 完整打包到 dist/
    python build.py --deps     # 仅安装依赖
    python build.py --out out  # 打包到指定目录（默认 dist）
产物：<out>/douyin-bot-desktop/

说明：
- 桌面版浏览器直接使用用户系统已装的 Edge/Chrome（account.engine=edge），
  无需下载 Playwright 浏览器。
- 打包产物需要内嵌运行时：
    runtime/python/  Windows embeddable Python 3.12（含 site-packages）
    runtime/node/    Node.js 22 LTS zip 版（node.exe）
  build.py 会自动从官网下载并解压（需联网）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "runtime"

PY_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
NODE_VERSION = "22.23.3"
NODE_SHA256 = "2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71"
NODE_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-win-x64.zip"


def run(cmd: list[str], **kw) -> None:
    print("+", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True, **kw)


def install_deps() -> None:
    run([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])
    bot_req = ROOT / "backend" / "douyin-friend-ai-bot" / "requirements.txt"
    if bot_req.exists():
        run([sys.executable, "-m", "pip", "install", "-r", str(bot_req)])
    run([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0,<7"])


def _bootstrap_runtime_python(py_dir: Path) -> None:
    """给 embeddable python 启用 site-packages 并装好后端依赖。"""
    pth = next(py_dir.glob("python*._pth"), None)
    if pth:
        # Explicit search paths keep the embedded runtime independent of user Python packages.
        content = pth.read_text(encoding="utf-8").replace("\nimport site", "\n#import site")
        if "Lib/site-packages" not in content:
            content += "\nLib/site-packages\n"
        pth.write_text(content, encoding="utf-8")
    getpip = py_dir / "get-pip.py"
    if not (py_dir / "Scripts" / "pip.exe").exists():
        print("安装 pip 到内嵌 Python ...")
        urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", getpip)
        run([str(py_dir / "python.exe"), str(getpip), "--no-warn-script-location"])
        getpip.unlink(missing_ok=True)
    print("向后端依赖安装到内嵌 Python ...")
    run([str(py_dir / "python.exe"), "-m", "pip", "install", "--no-warn-script-location",
         "fastapi==0.141.1", "uvicorn==0.53.0", "-r",
         str(ROOT / "backend/douyin-friend-ai-bot/requirements.txt")])


def fetch_runtime() -> None:
    RUNTIME.mkdir(exist_ok=True)
    for url, dest, inner in [
        (PY_URL, RUNTIME / "python", ""),
        (NODE_URL, RUNTIME / "node", f"node-v{NODE_VERSION}-win-x64/"),
    ]:
        if (dest / ("python.exe" if dest.name == "python" else "node.exe")).exists():
            if dest.name == "node":
                actual = subprocess.check_output([str(dest / "node.exe"), "--version"], text=True).strip()
                if actual != "v" + NODE_VERSION:
                    raise RuntimeError(f"内嵌 Node 版本 {actual} 与锁定版本 {NODE_VERSION} 不一致，请先更新 runtime/node")
            print(f"已存在：{dest}")
            continue
        print(f"下载 {url} ...")
        zpath = RUNTIME / (dest.name + ".zip")
        if not zpath.exists() or not zipfile.is_zipfile(zpath):
            urllib.request.urlretrieve(url, zpath)
        if dest.name == "node" and hashlib.sha256(zpath.read_bytes()).hexdigest() != NODE_SHA256:
            raise RuntimeError("Node 下载校验失败，请移除下载缓存后重试")
        if not zipfile.is_zipfile(zpath):
            raise RuntimeError(f"下载结果不是 ZIP 文件：{url}，请检查网络后重试")
        tmp = RUNTIME / ("_unpack_" + dest.name)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(tmp)
        # 去掉 zip 内层目录
        src = tmp / inner.rstrip("/") if inner else tmp
        shutil.copytree(src, dest, dirs_exist_ok=True)
        # Keep a recoverable download cache; incomplete extractions are never run.
        print(f"就绪：{dest}")
    _bootstrap_runtime_python(RUNTIME / "python")
    # 幕间引擎 node_modules
    interlude = ROOT / "backend" / "douyin-interlude"
    if not (interlude / "node_modules").exists():
        run(["cmd", "/c", "npm", "install"], cwd=interlude)
    run([str(RUNTIME / "node/node.exe"), "scripts/build.mjs"], cwd=interlude)
    run([str(RUNTIME / "node/node.exe"), "-e", "require('@koishijs/plugin-database-sqlite'); require('./upstream/lib')"], cwd=interlude)


def build(dist_dir: str = "dist", runtime_link_source: str | None = None) -> None:
    if not (RUNTIME / "python/python.exe").exists() or not (RUNTIME / "node/node.exe").exists():
        raise RuntimeError("runtime/ 缺少内嵌运行时，先执行 python build.py --runtime")
    actual_node = subprocess.check_output([str(RUNTIME / "node/node.exe"), "--version"], text=True).strip()
    if actual_node != "v" + NODE_VERSION:
        raise RuntimeError("内嵌 Node 与锁定版本不一致，拒绝打包旧运行时")
    runtime_source = Path(runtime_link_source).resolve() if runtime_link_source else RUNTIME
    if runtime_link_source:
        # Optional local disk-saving release: link only an already verified release's
        # immutable runtime, never the development runtime that future builds update.
        if not (runtime_source.parent / "build-manifest.json").is_file():
            raise RuntimeError("运行时硬链接来源必须是已验收的发布目录")
        linked_version = subprocess.check_output([str(runtime_source / "node/node.exe"), "--version"], text=True).strip()
        if linked_version != actual_node:
            raise RuntimeError("运行时来源版本不匹配")
    dist = Path(dist_dir)
    if not dist.is_absolute():
        dist = ROOT / dist
    # 用 --distpath 指定产物目录：目标目录不存在时 PyInstaller 无需删除旧目录，
    # 因此可以在程序仍在运行时构建到新目录，也不会触发大批量删除的保护。
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", str(dist), str(ROOT / "douyin-bot.spec")], cwd=ROOT)
    # 把内嵌运行时复制进产物目录
    out = dist / "douyin-bot-desktop"
    out.mkdir(parents=True, exist_ok=True)
    import shutil
    for sub in ("python", "node"):
        src = runtime_source / sub
        dst = out / "runtime" / sub
        if src.exists():
            print(f"复制 runtime/{sub} → {dst}")
            shutil.copytree(src, dst, dirs_exist_ok=True,
                            copy_function=os.link if runtime_link_source else shutil.copy2)
    for name in ("LICENSE",):
        shutil.copy2(ROOT / name, out / name)
    tracked = []
    for folder in (ROOT / "app", ROOT / "backend"):
        for source in sorted(folder.rglob("*")):
            if source.is_file() and source.suffix in {".py", ".cjs", ".mjs", ".json", ".html", ".css", ".svg", ".ico", ".png"} and not any(
                    part in {"node_modules", "__pycache__", "data", "logs", "state"} for part in source.relative_to(ROOT).parts):
                # Public source only; manifest contains hashes, never file contents.
                tracked.append({"path": source.relative_to(ROOT).as_posix(),
                                "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    for name in ("main.py", "douyin-bot.spec", "build.py"):
        tracked.append({"path": name, "sha256": hashlib.sha256((ROOT / name).read_bytes()).hexdigest()})
    manifest = {"node": actual_node, "python": sys.version, "sources": tracked,
                "runtime_storage": "hardlink-to-previous-release" if runtime_link_source else "copy",
                "exe_sha256": hashlib.sha256((out / "douyin-bot-desktop.exe").read_bytes()).hexdigest()}
    (out / "build-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n打包完成：{out}")
    print("浏览器说明：桌面版直接使用系统已装的 Edge/Chrome，无需额外安装浏览器。")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--deps", action="store_true", help="仅安装依赖")
    ap.add_argument("--runtime", action="store_true", help="仅下载内嵌运行时")
    ap.add_argument("--out", default="release", help="安装包输出目录，默认 release")
    ap.add_argument("--iscc", default="ISCC.exe", help="Inno Setup 7 ISCC.exe 路径")
    ap.add_argument("--payload-only", action="store_true", help="仅构建内部程序目录")
    args = ap.parse_args()
    if args.deps:
        install_deps()
    elif args.runtime:
        fetch_runtime()
    else:
        install_deps()
        fetch_runtime()
        build("build/payload")
        if not args.payload_only:
            from tools.build_installer import build as build_installer
            build_installer(ROOT / "build/payload/douyin-bot-desktop", Path(args.out), Path(args.iscc))
