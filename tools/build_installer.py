"""Wrap the verified application directory in one Inno Setup installer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "2026.10.12"


def sha256(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def source_files():
    """Positive allowlist: never traverse personal configuration or node_modules."""
    files = [ROOT / n for n in (
        "main.py", "build.py", "douyin-bot.spec", "requirements.txt",
        "LICENSE", ".gitignore")]
    trees = ["app", "tools", "installer",
             "backend/douyin-bot-panel/app", "backend/douyin-bot-panel/static",
             "backend/douyin-friend-ai-bot/src", "backend/douyin-friend-ai-bot/scripts",
             "backend/douyin-interlude/scripts", "backend/douyin-interlude/upstream"]
    excluded = {"__pycache__", "node_modules", "evidence", "data", "logs", "state", ".git"}
    for tree in trees:
        files.extend(p for p in (ROOT / tree).rglob("*") if p.is_file()
                     and not (set(p.relative_to(ROOT).parts) & excluded)
                     and p.suffix not in {".pyc", ".pyo"})
    for tree, names in {
        "backend/douyin-bot-panel": ["requirements.txt", "fault-alerts.example.json"],
        "backend/douyin-friend-ai-bot": ["requirements.txt", "config/config.example.json", "config/persona.example.md"],
        "backend/douyin-interlude": ["package.json", "package-lock.json", "bridge-config.example.json", "bridge.cjs", "worker.cjs", "hdsi-admin.cjs", "message-grounding.cjs"],
    }.items():
        files.extend(ROOT / tree / name for name in names)
    return sorted(set(p for p in files if p.is_file()))


def build(payload: Path, output: Path, compiler: Path, version: str = VERSION) -> Path:
    payload, output = payload.resolve(), output.resolve()
    required = ["douyin-bot-desktop.exe", "_internal", "runtime/python/python.exe",
                "runtime/node/node.exe", "LICENSE", "build-manifest.json"]
    for name in required:
        if not (payload / name).exists():
            raise RuntimeError(f"Incomplete application payload: {name}")
    manifest = json.loads((payload / "build-manifest.json").read_text(encoding="utf-8"))
    if sha256(payload / required[0]) != manifest["exe_sha256"]:
        raise RuntimeError("Application EXE does not match its build manifest")
    # Refuse to distribute a stale application after source changes. Build/packaging
    # files may change independently, but all compiled application sources must match.
    for entry in manifest["sources"]:
        name = entry["path"]
        if name == "main.py" or name.startswith(("app/", "backend/")):
            if not (ROOT / name).is_file() or sha256(ROOT / name) != entry["sha256"]:
                raise RuntimeError(f"Application source changed; rebuild payload first: {name}")
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"DouyinBot-Source-{version}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in source_files():
            z.write(path, path.relative_to(ROOT).as_posix())
    subprocess.run([str(compiler), f"/DPayloadDir={payload}",
                    f"/DSourceArchive={archive}", f"/DOutputDirPath={output}",
                    f"/DAppRelease={version}", str(ROOT / "installer/setup.iss")], check=True)
    result = output / f"DouyinBot-Setup-{version}.exe"
    (output / "installer-manifest.json").write_text(json.dumps({
        "version": version, "installer": result.name, "bytes": result.stat().st_size,
        "sha256": sha256(result), "payload_exe_sha256": manifest["exe_sha256"],
        "source_archive": archive.name, "source_sha256": sha256(archive),
    }, indent=2), encoding="utf-8")
    print(f"Installer ready: {result}")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--payload", type=Path, default=ROOT / "build/payload/douyin-bot-desktop")
    ap.add_argument("--out", type=Path, default=ROOT / "release")
    ap.add_argument("--iscc", type=Path, default=Path(os.environ.get("ISCC", shutil.which("ISCC.exe") or "ISCC.exe")))
    ap.add_argument("--version", default=VERSION)
    args = ap.parse_args()
    build(args.payload, args.out, args.iscc, args.version)


if __name__ == "__main__":
    main()
