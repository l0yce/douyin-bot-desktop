"""运行状态页：三进程状态卡片、启停按钮、Cookie 导入、依赖体检结果。"""
from __future__ import annotations

import json

from PySide6.QtCore import Qt, QTimer, Signal, QProcess
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget, QInputDialog,
    QFrame, QGridLayout, QScrollArea, QDialog, QDialogButtonBox, QPlainTextEdit, QComboBox,
)

from ...core import deps_checker
from ...core.api_client import ApiClient, ApiError
from .. import theme
from ..widgets.service_card import ServiceCard, state_text
from ..icons import themed_icon, themed_pixmap

SERVICE_TITLES = {
    "panel": ("控制面板", "本地 HTTP API · 8790"),
    "interlude": ("幕间引擎", "剧情与记忆桥接"),
    "bot": ("机器人", "抖音消息自动回复"),
}


class StatusPage(QWidget):
    whitelistRequested = Signal()

    def _review_uncertain_sends(self):
        if any(s.desired or (s.proc and s.proc.state() != QProcess.NotRunning)
               for key, s in self.process_mgr.services.items() if key != "panel"):
            QMessageBox.information(self, "请先停止服务", "停止机器人和幕间引擎后，再核对待确认发送。")
            return
        def received(data):
            items = data.get("items", [])
            if not items:
                QMessageBox.information(self, "发送记录", "没有待人工核对的发送记录。")
                return
            labels = [f"{i + 1}. {row.get('friend') or row['key']} · {row['text'][:60]}"
                      for i, row in enumerate(items)]
            selected, ok = QInputDialog.getItem(self, "选择待核对记录", "请在抖音中核对真实聊天记录：", labels, 0, False)
            if not ok:
                return
            item = items[labels.index(selected)]
            dialog = QDialog(self)
            dialog.setWindowTitle("记录核对结果")
            dialog.resize(560, 400)
            layout = QVBoxLayout(dialog)
            preview = QPlainTextEdit()
            preview.setReadOnly(True)
            preview.setPlainText(item["text"])
            preview.setAccessibleName("待核对回复完整内容")
            layout.addWidget(preview, 1)
            choices = QComboBox()
            choices.addItems(["已确认发出", "跳过此次回复，继续处理后续新消息"])
            layout.addWidget(choices)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.button(QDialogButtonBox.Ok).setText("继续")
            buttons.button(QDialogButtonBox.Cancel).setText("取消")
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            ok = dialog.exec() == QDialog.Accepted
            choice = choices.currentText()
            if not ok:
                return
            resolution = "sent" if choice == "已确认发出" else "skip"
            if QMessageBox.question(self, "确认人工核对结果",
                    "保存后将解除这条记录的阻塞，不会重发原回复。确认已经核对真实聊天记录？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            payload = {**item, "resolution": resolution, "confirmed": True}
            self.api.run("send-recovery-save", lambda: self.api.post("/api/send-recovery", payload),
                         lambda r: QMessageBox.information(self, "已处理", r["message"]),
                         lambda e: QMessageBox.warning(self, "处理失败", str(e)))
        self.api.run("send-recovery-read", lambda: self.api.get("/api/send-recovery"), received,
                     lambda e: QMessageBox.warning(self, "读取失败", str(e)))

    def __init__(self, process_mgr, api: ApiClient, parent=None):
        super().__init__(parent)
        self.process_mgr = process_mgr
        self.api = api
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        self.actions = QWidget()
        actions = QHBoxLayout(self.actions)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(10)
        self.btn_all_start = QPushButton("启动全部")
        self.btn_all_start.setProperty('primary', True)
        themed_icon(self.btn_all_start, 'play', 'accent_ink', 16)
        self.btn_all_stop = QPushButton("停止全部")
        themed_icon(self.btn_all_stop, 'stop', 'icon', 16)
        self.btn_all_start.clicked.connect(self._start_all)
        self.btn_all_stop.clicked.connect(self._stop_all)
        actions.addWidget(self.btn_all_start)
        actions.addWidget(self.btn_all_stop)
        self.btn_send_recovery = QPushButton("核对待确认发送")
        self.btn_send_recovery.clicked.connect(self._review_uncertain_sends)
        actions.addWidget(self.btn_send_recovery)

        health, health_layout = self._panel('HealthStrip', margins=18)
        health_row = QHBoxLayout()
        health_row.setSpacing(20)
        self.health_labels = {}
        self.health_states = {}
        for key in ("panel", "interlude", "bot"):
            title, sub = SERVICE_TITLES[key]
            column = QVBoxLayout()
            column.setSpacing(6)
            status = QLabel(title + " · 正在读取")
            status.setObjectName('HealthState')
            status.setTextFormat(Qt.PlainText)
            desc = QLabel(sub)
            desc.setObjectName('SmallMuted')
            column.addWidget(status)
            column.addWidget(desc)
            health_row.addLayout(column, 1)
            self.health_labels[key] = status
        health_layout.addLayout(health_row)
        lay.addWidget(health)

        work = QHBoxLayout()
        work.setSpacing(16)
        service_panel, services = self._panel()
        services.setSpacing(4)
        self._section_title(services, "本地服务")
        headings = QHBoxLayout()
        headings.addWidget(self._label("服务", 'SmallMuted'), 1)
        state_heading = self._label("状态", 'SmallMuted')
        state_heading.setFixedWidth(62)
        state_heading.setAlignment(Qt.AlignCenter)
        action_heading = self._label("操作", 'SmallMuted')
        action_heading.setFixedWidth(76)
        action_heading.setAlignment(Qt.AlignCenter)
        headings.addWidget(state_heading)
        headings.addSpacing(14)
        headings.addWidget(action_heading)
        services.addLayout(headings)
        self.cards = {}
        for key in ("panel", "interlude", "bot"):
            title, sub = SERVICE_TITLES[key]
            card = ServiceCard(title, sub, service=key)
            card.startClicked.connect(lambda _=False, k=key: self.process_mgr.start_service(k))
            card.stopClicked.connect(lambda _=False, k=key: self.process_mgr.stop_service(k))
            self.cards[key] = card
            services.addWidget(card)
        work.addWidget(service_panel, 3)
        right = QVBoxLayout()
        right.setSpacing(16)
        account_panel, account = self._panel()
        self._section_title(account, "账号与登录", 'user')
        account_note = self._label("导入或粘贴抖音登录 Cookies，用于机器人登录。", 'Muted')
        account_note.setWordWrap(True)
        account.addWidget(account_note)
        account.addStretch()
        cookie_row = QHBoxLayout()
        cookie_row.setSpacing(10)
        btn_cookie = QPushButton("导入 Cookies")
        themed_icon(btn_cookie, 'upload', 'accent_text', 16)
        btn_cookie.clicked.connect(self._import_cookies)
        cookie_row.addWidget(btn_cookie)
        btn_paste = QPushButton("粘贴 Cookies")
        themed_icon(btn_paste, 'paste', 'icon', 16)
        btn_paste.clicked.connect(self._paste_cookies)
        cookie_row.addWidget(btn_paste)
        account.addLayout(cookie_row)
        right.addWidget(account_panel, 1)
        whitelist_panel, whitelist = self._panel()
        whitelist_heading = QHBoxLayout()
        title = self._label("好友白名单", 'SectionTitle')
        whitelist_heading.addWidget(title, 1)
        view_whitelist = QPushButton("管理")
        view_whitelist.setProperty('quiet', True)
        view_whitelist.clicked.connect(self.whitelistRequested)
        whitelist_heading.addWidget(view_whitelist)
        whitelist.addLayout(whitelist_heading)
        self.summary_label = self._label("正在读取白名单…", 'WhitelistSummary')
        self.summary_label.setWordWrap(True)
        whitelist.addWidget(self.summary_label)
        whitelist_note = self._label("仅对白名单中启用的好友自动回复。", 'Muted')
        whitelist_note.setWordWrap(True)
        whitelist.addWidget(whitelist_note)
        right.addWidget(whitelist_panel, 1)
        work.addLayout(right, 2)
        lay.addLayout(work)

        deps_panel, deps = self._panel()
        deps_heading = QHBoxLayout()
        shield = QLabel()
        themed_pixmap(shield, 'shield', 'accent_text', 24)
        deps_heading.addWidget(shield)
        deps_heading.addWidget(self._label("环境体检", 'SectionTitle'), 1)
        details = QPushButton("查看详情")
        details.setProperty('quiet', True)
        details.clicked.connect(self._show_deps_details)
        deps_heading.addWidget(details)
        self.btn_deps = QPushButton("重新体检")
        themed_icon(self.btn_deps, 'reset', 'icon', 16)
        self.btn_deps.clicked.connect(self._run_deps)
        deps_heading.addWidget(self.btn_deps)
        deps.addLayout(deps_heading)
        self.deps_feedback = self._label("检查本地运行环境是否满足要求", 'SmallMuted')
        self.deps_feedback.setWordWrap(True)
        deps.addWidget(self.deps_feedback)
        self.deps_grid = QGridLayout()
        self.deps_grid.setHorizontalSpacing(24)
        self.deps_grid.setVerticalSpacing(10)
        deps.addLayout(self.deps_grid)
        self.deps_text = "正在检查本地运行环境…"
        self.deps_marks = []
        lay.addWidget(deps_panel)
        self.server_note = self._label("", 'SmallMuted')
        self.server_note.setAlignment(Qt.AlignRight)
        self.server_note.setWordWrap(True)
        lay.addWidget(self.server_note)
        lay.addStretch()

        self._run_deps()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)
        self.refresh()
        # 健康栏与体检结果的颜色是内联样式，样式表管不到，换主题要重设。
        theme.bind(self, self._on_theme_changed)

    def _apply_health_style(self, key):
        state = self.health_states.get(key)
        text, color = state_text(state) if state else ('正在读取', theme.color('muted'))
        self.health_labels[key].setText(f"{SERVICE_TITLES[key][0]}  ·  {text}")
        self.health_labels[key].setStyleSheet(f"color:{color};")

    @staticmethod
    def _paint_mark(label, ok):
        label.setStyleSheet(f"color:{theme.color('ok' if ok else 'warn')};")

    def _on_theme_changed(self):
        """健康栏与体检结果的颜色是内联样式，样式表管不到。

        体检结果只重涂颜色，不重建网格：`deleteLater()` 要等事件循环才真正删除，
        重建会让新旧两套格子在截图里叠在一起（`processEvents()` 不派发 DeferredDelete）。
        """
        for key in self.health_labels:
            self._apply_health_style(key)
        for label, ok in self.deps_marks:
            self._paint_mark(label, ok)

    @staticmethod
    def _label(text, role):
        label = QLabel(text)
        label.setTextFormat(Qt.PlainText)
        label.setObjectName(role)
        return label

    @staticmethod
    def _panel(name='Surface', margins=20):
        panel = QFrame()
        panel.setObjectName(name)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(margins, margins, margins, margins)
        layout.setSpacing(12)
        return panel, layout

    def _section_title(self, layout, text, symbol=None):
        row = QHBoxLayout()
        row.setSpacing(12)
        if symbol:
            image = QLabel()
            themed_pixmap(image, symbol, 'accent_text', 22)
            row.addWidget(image)
        row.addWidget(self._label(text, 'SectionTitle'), 1)
        layout.addLayout(row)

    def _start_all(self):
        self.process_mgr.start_all()

    def _stop_all(self):
        self.process_mgr.stop_all()

    def refresh(self):
        for key, card in self.cards.items():
            svc = self.process_mgr.services.get(key)
            if svc:
                detail = f"重启次数 {svc.crash_count}"
                if (u := svc.uptime()) is not None:
                    m, s = divmod(int(u), 60)
                    h, m = divmod(m, 60)
                    detail = f"已运行 {h:d}:{m:02d}:{s:02d} · {detail}"
                card.update_state(svc.active_state(), detail)
                self.health_states[key] = svc.active_state()
                self._apply_health_style(key)
        self.api.run("status", self.api.status, self._show_status,
                     self._status_error)

    def _status_error(self, error):
        self.summary_label.setText("控制面板暂未连接")
        self.summary_label.setToolTip(str(error))
        self.server_note.setText("连接失败，正在重试；可到日志中心查看详情。")

    def _show_status(self, st):
            wl = st.get("whitelist", {})
            self.summary_label.setText(
                f"{wl.get('enabled', '—')} / {wl.get('total', '—')} 位好友已启用")
            self.summary_label.setToolTip("")
            stamp = st.get('server_time')
            self.server_note.setText(f"本机时间：{stamp}" if stamp else "")

    def _import_cookies(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 Cookies 文件（从浏览器导出的 JSON）", "",
                                              "JSON (*.json);;所有文件 (*)")
        if not path:
            return
        try:
            content = open(path, "r", encoding="utf-8").read()
        except OSError as e:
            QMessageBox.warning(self, "读取失败", str(e))
            return
        self._submit_cookies(content)

    def _paste_cookies(self):
        content, ok = QInputDialog.getMultiLineText(self, "导入 Cookies", "粘贴 Cookie-Editor 导出的完整 JSON 或 Cookie 请求头：")
        if ok and content.strip():
            self._submit_cookies(content)

    def _submit_cookies(self, content):
        self.api.run("cookie-import", lambda: self.api.post("/api/cookies/import", {"content": content}),
                     lambda r: QMessageBox.information(self, "导入成功", r.get("message", "已导入")),
                     lambda e: QMessageBox.warning(self, "导入失败", str(e)))

    def _run_deps(self):
        self.btn_deps.setEnabled(False)
        self.deps_feedback.setText("正在检查本地运行环境…")
        owned = [8791]
        for key, port in (("panel", 8790), ("interlude", 18765)):
            if self.process_mgr.services[key].active_state() == "active":
                owned.append(port)
        self.api.run("deps", lambda: deps_checker.run_all(owned_ports=owned), self._show_deps, self._deps_error)

    def _deps_error(self, error):
        self.btn_deps.setEnabled(True)
        self.deps_feedback.setText(f"体检暂未完成：{error}。请重新体检。")

    def _show_deps(self, results):
        self.btn_deps.setEnabled(True)
        self.deps_marks = []
        while self.deps_grid.count():
            item = self.deps_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # 必须先摘掉父子关系：takeAt 不reparent，而 deleteLater 要等事件
                # 循环才生效，期间旧格子仍然可见、会和新格子叠在一起。
                widget.setParent(None)
                widget.deleteLater()
        lines = []
        for index, r in enumerate(results):
            mark = "通过" if r.ok else "待处理"
            lines.append(f"{mark} {r.name}：{r.detail}" + (f"（修复：{r.fix}）" if not r.ok and r.fix else ""))
            cell = QWidget()
            row = QHBoxLayout(cell)
            row.setContentsMargins(0, 7, 0, 7)
            title = self._label(r.name, 'SmallMuted')
            title.setWordWrap(True)
            row.addWidget(title, 1)
            state = self._label(mark, 'CheckState')
            self.deps_marks.append((state, bool(r.ok)))
            self._paint_mark(state, bool(r.ok))
            row.addWidget(state)
            cell.setToolTip(lines[-1])
            self.deps_grid.addWidget(cell, index // 3, index % 3)
        self.deps_text = "\n\n".join(lines) or "未返回检查结果，请重新体检。"
        pending = sum(not r.ok for r in results)
        self.deps_feedback.setText(f"{len(results)} 项检查 · {pending} 项待处理；详情中包含完整结果与修复说明。")

    def _show_deps_details(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("环境体检详情")
        dialog.resize(700, 480)
        layout = QVBoxLayout(dialog)
        reader = QPlainTextEdit()
        reader.setReadOnly(True)
        reader.setPlainText(self.deps_text)
        layout.addWidget(reader)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.button(QDialogButtonBox.Close).setText("关闭")
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()
