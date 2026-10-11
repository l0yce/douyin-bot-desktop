"""douyin-bot 桌面版入口：单实例锁、崩溃兜底、首启初始化。"""
from __future__ import annotations

import datetime
import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox


def _single_instance(app: QApplication) -> bool:
    """用 QLockFile 做单实例锁。"""
    from PySide6.QtCore import QLockFile
    from app.core import paths
    lock = QLockFile(str(paths.data_dir() / "desktop.lock"))
    if not lock.tryLock(100):
        return False
    app._lock = lock  # 防止被 GC
    return True


def _init_first_run() -> None:
    """首次运行：从 example 生成 config.json（默认 engine=edge 使用系统浏览器）。"""
    from app.core.initialize import initialize
    initialize()


def _crash_log(exc: BaseException) -> None:
    try:
        from app.core.paths import logs_dir
        p = logs_dir() / f"crash-{datetime.datetime.now():%Y%m%d-%H%M%S}.log"
        p.write_text(traceback.format_exc(), encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DouyinBot.Desktop")
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("douyin-bot-desktop")
    app.setQuitOnLastWindowClosed(False)  # 关窗最小化到托盘

    if not _single_instance(app):
        QMessageBox.warning(None, "douyin-bot", "douyin-bot 桌面版已在运行（请查看系统托盘）。")
        return 0

    try:
        _init_first_run()
        from app.ui.main_window import MainWindow
        window = MainWindow()
    except SystemExit:
        raise
    except BaseException as exc:
        _crash_log(exc)
        QMessageBox.critical(None, "启动失败",
                             "桌面版启动出错，崩溃日志已写入 %APPDATA%\\douyin-bot\\desktop-logs\\。\n\n"
                             f"{exc}")
        return 1

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
