# -*- coding: utf-8 -*-
"""好友会话状态存储：记录每个白名单好友最近一次已处理的消息指纹，避免重复回复。"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from durable_files import atomic_write

_LOCK = threading.RLock()


class StateCorruptionError(RuntimeError):
    """Sending must stop when the deduplication ledger cannot be trusted."""



def text_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def msg_fingerprint(text: str, ts: str = "") -> str:
    return text_fingerprint(f"{text}|{ts}")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class StateStore:
    """state/replied_state.json 的读写封装，带进程内锁，文件损坏时停止，保留原文件及最近的有效备份。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = {"version": 1, "friends": {}}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if (not isinstance(raw, dict) or raw.get("version") != 1
                    or not isinstance(raw.get("friends"), dict)
                    or any(not isinstance(v, dict) for v in raw["friends"].values())):
                raise ValueError("不支持或损坏的会话状态格式")
            self._data = raw
        except (ValueError, OSError) as exc:
            raise StateCorruptionError(
                f"会话状态读取失败，已停止自动回复以避免重复发送。保留文件：{self.path}；"
                f"请核对聊天记录后恢复状态备份 {self.path}.bak。原因：{exc}"
            ) from exc

    def _save(self) -> None:
        if self.path.exists():
            # The previous generation is evidence, never loaded automatically: doing so
            # could rewind acknowledged messages and cause a duplicate send.
            atomic_write(Path(str(self.path) + ".bak"), self.path.read_bytes())
        atomic_write(self.path, json.dumps(self._data, ensure_ascii=False, indent=2).encode("utf-8"))

    def friend_state(self, friend: str) -> dict[str, Any]:
        entry = self._data["friends"].setdefault(friend, {})
        if not isinstance(entry, dict):
            entry = {}
            self._data["friends"][friend] = entry
        return entry

    def get(self, friend: str, key: str, default: Any = None) -> Any:
        return self.friend_state(friend).get(key, default)

    def set(self, friend: str, key: str, value: Any) -> None:
        self.update(friend, **{key: value})

    def update(self, friend: str, **kwargs: Any) -> None:
        with _LOCK:
            previous = copy.deepcopy(self._data)
            self.friend_state(friend).update(kwargs)
            try:
                self._save()
            except BaseException:
                self._data = previous
                raise

    def snapshot(self) -> dict[str, Any]:
        with _LOCK:
            return json.loads(json.dumps(self._data, ensure_ascii=False))