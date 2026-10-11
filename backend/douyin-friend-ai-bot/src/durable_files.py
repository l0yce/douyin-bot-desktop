"""Durable file replacement and a shared cross-process configuration lock."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time

_mutex = threading.RLock()


def revision(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def atomic_write(path: Path, raw: bytes) -> None:
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".durable-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def config_lock(path: Path):
    """All desktop configuration writers lock the same config.json sidecar."""
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _mutex, lock_path.open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + 10
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("配置正被其他操作使用，请稍后重试")
                    time.sleep(.05)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            recover_transaction(path)
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def recover_transaction(config_path: Path) -> None:
    """Roll back an interrupted multi-file save before any subsequent writer/read."""
    journal = Path(str(config_path) + ".transaction")
    if not journal.exists():
        return
    records = json.loads(journal.read_text(encoding="utf-8"))
    for record in records:
        target = Path(record["target"])
        old = Path(record["backup"])
        # Backups are kept as recovery evidence; never silently skip a missing one.
        atomic_write(target, old.read_bytes())
    journal.unlink()


def commit_files(config_path: Path, updates: dict[Path, bytes]) -> None:
    """Caller holds config_lock. Journal makes interrupted saves recoverable."""
    backup_dir = Path(config_path).parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = time.time_ns()
    records = []
    for index, path in enumerate(updates):
        backup = backup_dir / f"transaction-{stamp}-{index}.bak"
        atomic_write(backup, path.read_bytes())
        records.append({"target": str(path.resolve()), "backup": str(backup.resolve())})
    journal = Path(str(config_path) + ".transaction")
    atomic_write(journal, json.dumps(records).encode("utf-8"))
    try:
        for path, raw in updates.items():
            atomic_write(path, raw)
    except BaseException:
        recover_transaction(config_path)
        raise
    journal.unlink()
