"""进程管理器：QProcess 托管 panel / interlude / bot 三个子进程。

- 启动顺序固定：panel → interlude → bot
- 崩溃自动重启（指数退避，上限 60s）
- 退出时倒序 kill 子进程树
- 内置控制 HTTP 服务（127.0.0.1:8791），panel.py 桌面模式下
  通过它替代 systemctl 获取状态 / 启停进程 / 读日志。
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal, Slot

from . import paths
from .windows_job import WindowsJob

PANEL_PORT = 8790
CTL_PORT = 8791
INTERLUDE_PORT = 18765
CONTROL_TOKEN = secrets.token_urlsafe(32)


def backend_env():
    return {"PANEL_DIR": str(paths.panel_dir()), "PANEL_DATA_DIR": str(paths.data_dir() / "panel"),
            "BOT_DIR": str(paths.bot_dir()), "BOT_SOURCE_DIR": str(paths.bot_source_dir()),
            "BOT_CONFIG": str(paths.bot_dir() / "config/config.json"),
            "INTERLUDE_DIR": str(paths.interlude_dir()),
            "BRIDGE_CONFIG": str(paths.interlude_dir() / "bridge-config.json"),
            "DESKTOP_CONTROL_TOKEN": CONTROL_TOKEN, "DOUYIN_BOT_DESKTOP": "1",
            "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}

# systemd unit 名 → 内部 key（panel.py 桌面兼容层用）
UNIT_MAP = {
    "douyin-friend-ai-bot": "bot",
    "douyin-interlude": "interlude",
    "douyin-bot-panel": "panel",
    "douyin-bot-xvfb": "xvfb",
}


class ServiceSpec:
    def __init__(self, key: str, cwd, command: list[str], env: dict | None = None):
        self.key = key
        self.cwd = cwd
        self.command = command
        self.env = env or {}


SPECS = {
    "panel": lambda: ServiceSpec(
        "panel",
        paths.panel_dir() / "app",
        [str(paths.python_exe()), "-m", "uvicorn", "app:app",
         "--app-dir", str(paths.panel_dir() / "app"),
         "--host", "127.0.0.1", "--port", str(PANEL_PORT)],
        env=backend_env(),
    ),
    "interlude": lambda: ServiceSpec(
        "interlude",
        paths.interlude_dir(),
        [str(paths.node_exe()), "--max-old-space-size=128", str(paths.interlude_source_dir() / "bridge.cjs")],
        env=backend_env(),
    ),
    "bot": lambda: ServiceSpec(
        "bot",
        paths.bot_dir(),
        [str(paths.python_exe()), str(paths.bot_source_dir() / "src/main.py"), "--config", "config/config.json"],
        env=backend_env(),
    ),
}


class ManagedService(QObject):
    stateChanged = Signal(str)  # key

    def __init__(self, spec: ServiceSpec, parent: QObject):
        super().__init__(parent)
        self.spec = spec
        self.proc: Optional[QProcess] = None
        self.desired = False          # 用户期望的运行状态
        self.started_at = 0.0
        self.crash_count = 0
        self.backoff = 0.0
        self.output: list[str] = []   # 环形日志缓冲
        self._restart_timer = QTimer(self)
        self._restart_timer.setSingleShot(True)
        self._restart_timer.timeout.connect(self._start)

    def active_state(self) -> str:
        if self.proc and self.proc.state() == QProcess.Running:
            return "active"
        if self.desired and (self._restart_timer.isActive() or (self.proc and self.proc.state() == QProcess.Starting)):
            return "activating"
        if self.crash_count and not self.desired:
            return "failed"
        return "inactive"

    def sub_state(self) -> str:
        return "running" if self.active_state() == "active" else "dead"

    def uptime(self) -> Optional[float]:
        return max(0.0, time.time() - self.started_at) if self.started_at and self.active_state() == "active" else None

    def append_output(self, text: str) -> None:
        self.output.append(text.rstrip("\n"))
        if len(self.output) > 2000:
            del self.output[:-1000]

    def start(self) -> None:
        self.desired = True
        self.crash_count = 0
        self.backoff = 0.0
        self._start()

    def _start(self) -> None:
        if self.proc and self.proc.state() != QProcess.NotRunning:
            return
        spec = self.spec
        proc = QProcess(self)
        proc.setProgram(spec.command[0])
        proc.setArguments(spec.command[1:])
        proc.setWorkingDirectory(str(spec.cwd))
        env = QProcessEnvironment.systemEnvironment()
        for k, v in spec.env.items():
            env.insert(k, v)
        proc.setProcessEnvironment(env)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(
            lambda p=proc: self.append_output(bytes(p.readAllStandardOutput()).decode("utf-8", "replace")))
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)
        proc.started.connect(self._on_started)
        self.proc = proc
        proc.start()
        self.started_at = time.time()
        self.stateChanged.emit(self.spec.key)

    def stop(self) -> None:
        self.desired = False
        self._restart_timer.stop()
        if self.proc and self.proc.state() != QProcess.NotRunning:
            if os.name == "nt" and self.proc.processId():
                # Kill descendants while the owned root PID still exists (browser and worker).
                try:
                    subprocess.run(["taskkill", "/PID", str(self.proc.processId()), "/T", "/F"],
                                   capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    self.append_output(f"[桌面管理器] 进程树清理失败：{exc}")
            # Windows 下 QProcess.terminate 发 WM_CLOSE，超时后强杀
            self.proc.terminate()
            if not self.proc.waitForFinished(1000):
                self.proc.kill()
                self.proc.waitForFinished(3000)
        self.started_at = 0
        self.stateChanged.emit(self.spec.key)

    def _on_started(self):
        try:
            self.parent().job.assign(self.proc.processId())
        except OSError as exc:
            self.append_output(f"[桌面管理器] 无法托管子进程树：{exc}")
            self.stop()
            self.crash_count += 1
        self.stateChanged.emit(self.spec.key)

    def _on_error(self, error):
        self.append_output(f"[桌面管理器] {self.proc.errorString()}")
        if error == QProcess.FailedToStart:
            self.desired = False
            self.crash_count += 1
            self.started_at = 0
        self.stateChanged.emit(self.spec.key)

    def _on_finished(self, code: int, status) -> None:  # noqa: ANN001
        self.append_output(f"[桌面管理器] 进程退出 code={code}")
        self.started_at = 0
        self.stateChanged.emit(self.spec.key)
        if self.desired:
            # 崩溃自动重启，指数退避
            self.crash_count += 1
            if self.crash_count >= 5:
                self.desired = False
                self.append_output("[桌面管理器] 连续失败五次，已停止自动重启，请检查日志")
                self.stateChanged.emit(self.spec.key)
                return
            self.backoff = min(60.0, 3.0 * (2 ** min(self.crash_count - 1, 5)))
            self._restart_timer.start(int(self.backoff * 1000))


class ProcessManager(QObject):
    allStopped = Signal()
    stateChanged = Signal(str)
    error = Signal(str)
    controlRequested = Signal(object)

    ORDER = ["panel", "interlude", "bot"]  # 启动顺序；退出时倒序

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.job = WindowsJob()
        self.services: dict[str, ManagedService] = {}
        for key in self.ORDER:
            svc = ManagedService(SPECS[key](), self)
            svc.stateChanged.connect(self.stateChanged)
            self.services[key] = svc
        self._ctl_server: Optional[ThreadingHTTPServer] = None
        self.controlRequested.connect(self._control)
        from .api_client import ApiClient
        self._api = ApiClient(timeout=2)
        self._pending_bot = False
        self._ready_timer = QTimer(self)
        self._ready_timer.setInterval(500)
        self._ready_timer.timeout.connect(self._check_ready)
        self.start_ctl_server()

    # ---- 批量启停 ----
    def start_all(self) -> None:
        self.start_service("bot")

    def stop_all(self) -> None:
        self._pending_bot = False
        self._ready_timer.stop()
        for key in reversed(self.ORDER):
            self.services[key].stop()

    def start_service(self, key: str) -> None:
        if key == "bot":
            from .initialize import bot_setup_errors
            errors = bot_setup_errors()
            if errors:
                self.error.emit("\n".join(errors))
                return
            self.start_service("panel")
            self.start_service("interlude")
            self._pending_bot = True
            self._ready_deadline = time.monotonic() + 45
            self._ready_timer.start()
            return
        if key in self.services:
            svc = self.services[key]
            if svc.desired or (svc.proc and svc.proc.state() != QProcess.NotRunning):
                return
            port = {"panel": PANEL_PORT, "interlude": INTERLUDE_PORT}[key]
            with socket.socket() as sock:
                try:
                    sock.bind(("127.0.0.1", port))
                except OSError:
                    self.error.emit(f"端口 {port} 已被其他程序占用，请先关闭占用程序")
                    return
            self.services[key].start()

    def _check_ready(self):
        if time.monotonic() > self._ready_deadline:
            self._pending_bot = False
            self._ready_timer.stop()
            self.error.emit("面板或幕间引擎在 45 秒内未就绪，请查看日志中心")
            return
        def probe():
            import httpx
            token = json.loads((paths.interlude_dir() / "bridge-config.json").read_text(encoding="utf-8"))["token"]
            with httpx.Client(timeout=2, trust_env=False) as client:
                panel = client.get(f"http://127.0.0.1:{PANEL_PORT}/api/health")
                bridge = client.get(f"http://127.0.0.1:{INTERLUDE_PORT}/health", headers={"Authorization": "Bearer " + token})
                return panel.is_success and bridge.is_success and bridge.json().get("ready", False)
        self._api.run("ready", probe, self._on_ready)

    def _on_ready(self, ready):
        if ready and self._pending_bot and all(self.services[k].desired for k in ("panel", "interlude")):
            self._pending_bot = False
            self._ready_timer.stop()
            self.services["bot"].start()

    def stop_service(self, key: str) -> None:
        if key in ("bot", "panel", "interlude"):
            self._pending_bot = False
            self._ready_timer.stop()
        if key in self.services:
            self.services[key].stop()

    def restart_service(self, key: str) -> None:
        if key in self.services:
            self.services[key].stop()
            self.start_service(key)

    @Slot(object)
    def _control(self, request):
        try:
            method, parts = request["method"], request["parts"]
            if method == "GET":
                request["result"] = self.unit_state(parts[2]) if parts[1] == "units" else {"logs": self.journal(parts[2], 500)}
            else:
                getattr(self, parts[3] + "_service")(UNIT_MAP.get(parts[2], parts[2]))
                request["result"] = {"ok": True}
        except Exception as exc:
            request["result"] = {"detail": str(exc)}
        finally:
            request["event"].set()

    def unit_state(self, unit_name: str) -> dict:
        key = UNIT_MAP.get(unit_name, unit_name)
        if key == "xvfb" or key not in self.services:
            # 桌面版无 xvfb，恒报 inactive，panel 的 status 逻辑可安全处理
            return {"ActiveState": "inactive", "SubState": "dead"}
        svc = self.services[key]
        return {
            "ActiveState": svc.active_state(),
            "SubState": svc.sub_state(),
            "MainPID": svc.proc.processId() if svc.proc and svc.active_state() == "active" else 0,
            "UptimeSeconds": svc.uptime(),
        }

    def unit_uptime(self, unit_name: str) -> Optional[float]:
        key = UNIT_MAP.get(unit_name, unit_name)
        svc = self.services.get(key)
        return svc.uptime() if svc else None

    def journal(self, unit_name: str, lines: int = 200) -> str:
        key = UNIT_MAP.get(unit_name, unit_name)
        svc = self.services.get(key)
        if not svc:
            return f"[桌面管理器] 未知单元 {unit_name}"
        return "\n".join(svc.output[-lines:])

    # ---- 控制 HTTP（127.0.0.1:8791，供 panel.py 桌面兼容层调用）----
    def start_ctl_server(self) -> None:
        mgr = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # 静默
                pass

            def _json(self, obj, code=200):
                body = json.dumps(obj).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _local_only(self) -> bool:
                return (self.client_address[0] in ("127.0.0.1", "::1") and
                        secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer " + CONTROL_TOKEN))

            def _dispatch(self, parts, method):
                req = {"parts": parts, "method": method, "event": threading.Event()}
                mgr.controlRequested.emit(req)
                if not req["event"].wait(15):
                    return self._json({"detail": "桌面进程管理器忙，请稍后重试"}, 503)
                return self._json(req["result"], 400 if "detail" in req["result"] else 200)

            def do_GET(self):  # noqa: N802
                if not self._local_only():
                    return self._json({"detail": "forbidden"}, 403)
                parts = self.path.strip("/").split("/")
                if parts[:2] == ["api", "units"] and len(parts) == 3:
                    return self._dispatch(parts, "GET")
                if parts[:2] == ["api", "journal"] and len(parts) == 3:
                    return self._dispatch(parts, "GET")
                return self._json({"detail": "not found"}, 404)

            def do_POST(self):  # noqa: N802
                if not self._local_only():
                    return self._json({"detail": "forbidden"}, 403)
                parts = self.path.strip("/").split("/")
                # /api/units/{name}/{action}
                if len(parts) == 4 and parts[:2] == ["api", "units"]:
                    name, action = parts[2], parts[3]
                    key = UNIT_MAP.get(name, name)
                    if key not in mgr.services or action not in ("start", "stop", "restart"):
                        return self._json({"detail": "not found"}, 404)
                    return self._dispatch(parts, "POST")
                return self._json({"detail": "not found"}, 404)

        try:
            self._ctl_server = ThreadingHTTPServer(("127.0.0.1", CTL_PORT), Handler)
            threading.Thread(target=self._ctl_server.serve_forever, daemon=True).start()
        except OSError as exc:
            raise RuntimeError(f"控制端口 {CTL_PORT} 被占用，无法启动桌面版") from exc

    def shutdown(self) -> None:
        self.stop_all()
        self.job.close()
        if self._ctl_server:
            self._ctl_server.shutdown()
            self._ctl_server.server_close()
            self._ctl_server = None
