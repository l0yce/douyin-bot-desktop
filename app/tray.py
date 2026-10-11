"""托盘图标：状态变色、快捷启停、打开主窗口。"""
from __future__ import annotations

from PySide6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QMenu, QSystemTrayIcon
from .ui.application_icon import application_icon

RUNNING_COLOR = QColor("#34c759")   # 全部运行：绿
PARTIAL_COLOR = QColor("#ffab00")   # 部分运行：橙
STOPPED_COLOR = QColor("#8e8e93")   # 已停止：灰
FAILED_COLOR = QColor("#ff453a")    # 崩溃：红


def _icon(color: QColor) -> QIcon:
    pm = application_icon().pixmap(64, 64)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(color)
    p.setPen(QColor("#1c1c1e"))
    pen = p.pen()
    pen.setWidth(3)
    p.setPen(pen)
    p.drawEllipse(45, 45, 16, 16)
    p.end()
    return QIcon(pm)


class TrayController(QSystemTrayIcon):
    def __init__(self, window):
        super().__init__(_icon(STOPPED_COLOR), window)
        self.window = window
        menu = QMenu()
        act_open = QAction("打开主窗口", menu)
        act_open.triggered.connect(self._show_window)
        self.act_toggle = QAction("启动全部服务", menu)
        self.act_toggle.triggered.connect(self._toggle_all)
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self.window.quit_application)
        menu.addAction(act_open)
        menu.addAction(self.act_toggle)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)
        self.setToolTip("douyin-bot 桌面版")
        self.show()

    def _show_window(self) -> None:
        self.window.showNormal()
        self.window.activateWindow()

    def _toggle_all(self) -> None:
        if any(s.desired for s in self.window.process_mgr.services.values()):
            self.window.stop_all_services()
        else:
            self.window.start_all_services()

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self._show_window()

    def update_state(self, running: int, failed: bool) -> None:
        if running == 3:
            self.setIcon(_icon(RUNNING_COLOR))
            self.setToolTip("douyin-bot 桌面版：全部运行中")
        elif failed:
            self.setIcon(_icon(FAILED_COLOR))
            self.setToolTip("douyin-bot 桌面版：有服务崩溃，等待重启")
        elif running > 0:
            self.setIcon(_icon(PARTIAL_COLOR))
            self.setToolTip("douyin-bot 桌面版：部分运行中")
        else:
            self.setIcon(_icon(STOPPED_COLOR))
            self.setToolTip("douyin-bot 桌面版：已停止")
        self.act_toggle.setText("停止全部服务" if running > 0 else "启动全部服务")
