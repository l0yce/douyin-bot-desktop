"""Explicit reconciliation of uncertain deliveries; never schedules a resend."""
import json
import time
from pathlib import Path
from durable_files import atomic_write, revision


def unresolved(path: Path, kind: str) -> list[dict]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    data = json.loads(raw)
    rows = []
    if kind == "direct":
        for key, friend in data.get("friends", {}).items():
            attempt = friend.get("direct_send_attempt")
            if attempt:
                rows.append({"kind": kind, "key": key, "revision": revision(raw),
                             "text": "\n".join(attempt.get("segments", []))})
    else:
        for key, item in data.get("outbox", {}).items():
            if item.get("status") in ("unknown", "sending"):
                rows.append({"kind": kind, "key": key, "revision": revision(raw),
                             "text": str(item.get("content", "")), "friend": item.get("senderId", "")})
    return rows


def reconcile(path: Path, kind: str, key: str, expected: str, resolution: str) -> None:
    if resolution not in ("sent", "skip"):
        raise ValueError("请选择已发送或跳过，不支持自动重发")
    raw = path.read_bytes()
    if revision(raw) != expected:
        raise ValueError("记录已变化，请重新读取后核对")
    data = json.loads(raw)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if kind == "direct":
        friend = data["friends"][key]
        attempt = friend.get("direct_send_attempt")
        if not attempt:
            raise ValueError("此记录已经处理")
        # Both resolutions consume the original incoming window. 'skip' deliberately
        # abandons it; sending the same reply again is never implicit.
        friend.update(attempt["acknowledged_state"])
        friend["direct_send_attempt"] = None
        friend["last_send_reconciliation"] = {**attempt, "resolution": resolution, "reviewed_at": stamp}
        if resolution == "sent":
            friend["last_replied_at"] = stamp
            friend["replied_at"] = list(friend.get("replied_at", [])) + [stamp]
    else:
        item = data["outbox"][key]
        if item.get("status") not in ("unknown", "sending"):
            raise ValueError("此记录已经处理")
        item.update(status="sent" if resolution == "sent" else "permanent-failed",
                    manualResolution=resolution, reviewedAt=stamp)
    # Recovery is offline: the caller must stop both services and hold config_lock.
    atomic_write(Path(str(path) + ".recovery.bak"), raw)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
