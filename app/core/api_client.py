"""面板 API 客户端：httpx 封装，桌面本地模式无需 token。"""
from __future__ import annotations

from typing import Any

import httpx
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

BASE = "http://127.0.0.1:8790"


class ApiError(Exception):
    pass


class _Result(QObject):
    done = Signal(object, object)

    def __init__(self, success, error, cleanup):
        super().__init__()
        self.success, self.error, self.cleanup = success, error, cleanup
        self.done.connect(self.deliver)

    @Slot(object, object)
    def deliver(self, value, exc):
        try:
            if exc is None:
                try:
                    self.success(value)
                except Exception as callback_exc:  # noqa: BLE001
                    # 回调里的异常若任其逸出 Qt 事件循环，页面会永久停在“读取中”。
                    if self.error:
                        self.error(callback_exc)
                    else:
                        raise
            elif self.error:
                self.error(exc)
        finally:
            self.cleanup()


class _Work(QRunnable):
    def __init__(self, fn, result):
        super().__init__()
        self.fn, self.result = fn, result

    def run(self):
        try:
            value = self.fn()
        except Exception as exc:
            self.result.done.emit(None, exc)
        else:
            self.result.done.emit(value, None)


class ApiClient:
    def __init__(self, base: str = BASE, timeout: float = 15.0):
        self._client = httpx.Client(base_url=base, timeout=timeout, trust_env=False)
        self._pending = {}

    def run(self, key, fn, success, error=None):
        """One in-flight request per view; callbacks always run on the GUI thread."""
        if key in self._pending:
            return
        result = _Result(success, error, lambda: self._pending.pop(key, None))
        self._pending[key] = result
        QThreadPool.globalInstance().start(_Work(fn, result))

    def put(self, path: str, json_body: Any = None) -> Any:
        # Applying interlude settings includes validation and a service restart.
        timeout = 280.0 if path == '/api/hdsi/config' else 60.0 if path == '/api/story' else self._client.timeout
        r = self._client.put(path, json=json_body, timeout=timeout)
        if r.status_code >= 400:
            raise ApiError(f"PUT {path} -> {r.status_code}: {r.text[:200]}")
        return r.json()

    def get(self, path: str, **params) -> Any:
        r = self._client.get(path, params=params)
        if r.status_code >= 400:
            raise ApiError(f"GET {path} -> {r.status_code}: {r.text[:200]}")
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text

    def post(self, path: str, json_body: Any = None) -> Any:
        timeout = 280.0 if path in ('/api/hdsi/action', '/api/hdsi/timeline') else self._client.timeout
        r = self._client.post(path, json=json_body, timeout=timeout)
        if r.status_code >= 400:
            raise ApiError(f"POST {path} -> {r.status_code}: {r.text[:200]}")
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text

    # ---- 常用端点便捷封装 ----
    def status(self) -> Any:
        return self.get("/api/status")

    def bot_action(self, action: str) -> Any:
        return self.post(f"/api/bot/{action}")

    def health(self) -> bool:
        try:
            return self.get("/api/health").get("ok", False)
        except Exception:
            return False
