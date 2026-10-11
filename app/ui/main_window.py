"""主窗口：侧边导航 + 页面栈，托管进程管理器与托盘联动。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QProcess, QSize
from PySide6.QtWidgets import (
    QHBoxLayout, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QApplication,
    QPushButton, QStackedWidget, QWidget, QLabel, QVBoxLayout,
)

from ..core.api_client import ApiClient
from ..core.process_manager import ProcessManager
from .pages.chat_page import ChatPage
from .pages.logs_page import LogsPage
from .pages.status_page import StatusPage
from .pages.story_page import StoryPage
from .pages.whitelist_page import WhitelistPage
from .pages.setup_page import SetupPage
from . import theme
from .theme import Workspace, readable_placeholders
from .icons import icon, themed_pixmap
from .window_chrome import TitleBar, WindowChrome
from .application_icon import application_icon

NAV_ITEMS = ["运行状态", "模型与账号", "聊天动态", "好友白名单", "剧情与记忆", "日志中心"]
NAV_SYMBOLS = ('status', 'user', 'chat', 'friends', 'story', 'logs')


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("douyin-bot 桌面版")
        app_icon = application_icon()
        QApplication.instance().setWindowIcon(app_icon)
        self.setWindowIcon(app_icon)
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.resize(1240, 820)
        self.setMinimumSize(1000, 680)
        theme.apply(QApplication.instance())
        self.process_mgr = ProcessManager(self)
        self.process_mgr.error.connect(lambda message: QMessageBox.warning(self, "暂时无法启动", message))
        self.api = ApiClient()

        central = Workspace()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName('Sidebar')
        sidebar.setFixedWidth(220)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 24, 16, 20)
        side.setSpacing(10)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        self.brand_mark = QLabel()
        themed_pixmap(self.brand_mark, 'brand', 'accent_text', 36)
        brand_row.addWidget(self.brand_mark)
        brand = QLabel('douyin-bot')
        brand.setObjectName('Brand')
        brand_row.addWidget(brand, 1)
        side.addLayout(brand_row)
        self.service_note = QLabel('本地助手\n服务准备中')
        self.service_note.setObjectName('SidebarNote')
        side.addWidget(self.service_note)
        side.addSpacing(18)
        self.nav = QListWidget()
        self.nav.setObjectName('Navigation')
        self.nav.setIconSize(QSize(22, 22))
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for name in NAV_ITEMS:
            item = QListWidgetItem(name, self.nav)
            item.setSizeHint(QSize(180, 52))
        side.addWidget(self.nav, 1)
        self.theme_button = QPushButton()
        self.theme_button.setProperty('quiet', True)
        self.theme_button.clicked.connect(self._toggle_theme)
        theme.bind(self.theme_button, self._sync_theme_button)
        side.addWidget(self.theme_button)
        self._sync_theme_button()
        self._build_nav_icons()
        theme.bind(self.nav, self._build_nav_icons)
        content = QWidget(); content.setObjectName('PageBody')
        body = QVBoxLayout(content); body.setContentsMargins(24, 28, 24, 20); body.setSpacing(24)
        heading = QHBoxLayout()
        heading.setSpacing(16)
        titles = QVBoxLayout()
        titles.setSpacing(8)
        self.page_title = QLabel(); self.page_title.setObjectName('PageTitle')
        self.page_subtitle = QLabel(); self.page_subtitle.setObjectName('PageSubtitle'); self.page_subtitle.setWordWrap(True)
        titles.addWidget(self.page_title); titles.addWidget(self.page_subtitle)
        heading.addLayout(titles, 1)
        body.addLayout(heading)
        self.stack = QStackedWidget(); body.addWidget(self.stack, 1)
        root.addWidget(sidebar)
        root.addWidget(content, 1)
        shell = Workspace()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        self.title_bar = TitleBar(self)
        shell_layout.addWidget(self.title_bar)
        shell_layout.addWidget(central, 1)
        self.setCentralWidget(shell)
        self._window_chrome = WindowChrome(self)
        QApplication.instance().installEventFilter(self._window_chrome)
        for widget in (self, *self.findChildren(QWidget)):
            widget.setMouseTracking(True)

        self.status_page = StatusPage(self.process_mgr, self.api)
        heading.addWidget(self.status_page.actions, 0, Qt.AlignVCenter)
        self.status_page.whitelistRequested.connect(lambda: self.nav.setCurrentRow(3))
        self.setup_page = SetupPage(self.process_mgr)
        self.chat_page = ChatPage(self.api)
        self.whitelist_page = WhitelistPage(self.api)
        self.story_page = StoryPage(self.api)
        self.logs_page = LogsPage(self.api, self.process_mgr)
        for page in (self.status_page, self.setup_page, self.chat_page, self.whitelist_page,
                     self.story_page, self.logs_page):
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.currentRowChanged.connect(self._page_changed)
        self.nav.setCurrentRow(0)
        readable_placeholders(self)
        theme.bind(self, lambda: readable_placeholders(self))

        # 托盘（延迟导入避免循环依赖）
        from ..tray import TrayController
        self.tray = TrayController(self)

        # 托盘状态聚合刷新
        self._agg_timer = QTimer(self)
        self._agg_timer.timeout.connect(self._update_tray_state)
        self._agg_timer.start(2000)
        self._quitting = False
        QTimer.singleShot(0, lambda: self.process_mgr.start_service("panel"))
        self._panel_ready = False
        self._panel_timer = QTimer(self)
        self._panel_timer.timeout.connect(self._check_panel)
        self._panel_timer.start(1000)

    def _build_nav_icons(self):
        for row, symbol in enumerate(NAV_SYMBOLS):
            item = self.nav.item(row)
            if item is not None:
                item.setIcon(icon(symbol))

    def _sync_theme_button(self):
        """按钮文案写「点一下就切到哪套配色」，避免与当前状态混淆。"""
        mode = theme.current_mode()
        target = 'light' if mode == 'dark' else 'dark'
        self.theme_button.setText(theme.LABELS[target])
        self.theme_button.setIcon(icon('sun' if target == 'light' else 'moon',
                                       theme.color('accent_text'), 18))
        self.theme_button.setToolTip(f'当前为{theme.LABELS[mode]}，点击切换到{theme.LABELS[target]}')

    def _toggle_theme(self):
        mode = theme.toggle_mode()
        theme.save_mode(mode)
        theme.apply(QApplication.instance(), mode)
        # 样式表之外的东西（图标位图、内联颜色、拼好的富文本）靠登记的回调重建。
        theme.refresh_widgets(self)

    def _page_changed(self, index):
        self.page_title.setText(NAV_ITEMS[index])
        self.status_page.actions.setVisible(index == 0)
        self.page_subtitle.setText([
            '管理本地服务、登录凭据与启动状态', '配置模型连接、账号和角色人设',
            '查看好友来信、生成结果与发送记录', '选择允许机器人自动回复的好友',
            '管理角色生活、记忆、关系与聊天方式', '查看运行详情，刷新时保留阅读位置',
        ][index])

    def _check_panel(self):
        self.api.run("panel-bootstrap", self.api.health, self._panel_bootstrapped)

    def _panel_bootstrapped(self, ready):
        if ready and not self._panel_ready:
            self._panel_ready = True
            self._panel_timer.stop()
            self.story_page.reload_page()
            self.whitelist_page.refresh()

    def quit_application(self):
        self._quitting = True
        self.close()

    def start_all_services(self):
        self.process_mgr.start_all()

    def stop_all_services(self):
        self.process_mgr.stop_all()

    def _update_tray_state(self):
        running = sum(1 for s in self.process_mgr.services.values()
                      if s.active_state() == "active")
        failed = any(s.crash_count and s.desired for s in self.process_mgr.services.values())
        self.tray.update_state(running, failed)
        self.service_note.setText(f'本地助手\n{running} / 3 项服务运行中' + ('\n有服务异常' if failed else ''))

    def closeEvent(self, event):
        # 隐藏到托盘；真正退出走托盘菜单「退出」
        if self.tray.isVisible() and not self._quitting:
            event.ignore()
            self.hide()
            from PySide6.QtWidgets import QSystemTrayIcon
            self.tray.showMessage("douyin-bot", "已最小化到托盘，服务继续运行",
                                  QSystemTrayIcon.Information, 2000)
            return
        self._agg_timer.stop()
        self._panel_timer.stop()
        self.tray.hide()
        self.process_mgr.shutdown()
        event.accept()
        QApplication.instance().quit()

    def _any_service_running(self) -> bool:
        return any(s.proc and s.proc.state() != QProcess.NotRunning
                   for s in self.process_mgr.services.values())

    def _confirm_exit(self) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle("退出确认")
        box.setText("机器人服务正在运行，退出会一并停止所有子进程。确定退出？")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        return box.exec() == QMessageBox.Yes
