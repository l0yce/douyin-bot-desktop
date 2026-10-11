"""日志中心：运行日志 + 审计日志 + 子进程原始输出。"""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from ...core.api_client import ApiClient, ApiError


class LogsPage(QWidget):
    def __init__(self, api: ApiClient, process_mgr, parent=None):
        super().__init__(parent)
        self.api = api
        self.process_mgr = process_mgr
        lay = QVBoxLayout(self)

        row = QHBoxLayout()
        self.kind_box = QComboBox()
        self.kind_box.addItems(["运行日志", "审计日志", "机器人进程输出", "幕间引擎输出"])
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self.refresh)
        self.auto_btn = QPushButton("自动刷新：开")
        self.auto_btn.setCheckable(True)
        self.auto_btn.setChecked(True)
        self.auto_btn.toggled.connect(self._toggle_auto)
        self.kind_box.currentIndexChanged.connect(self._change_kind)
        row.addWidget(QLabel("视图："))
        row.addWidget(self.kind_box)
        row.addWidget(btn_refresh)
        row.addWidget(self.auto_btn)
        latest = QPushButton("回到最新")
        latest.clicked.connect(lambda: self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum()))
        row.addWidget(latest)
        row.addStretch()
        lay.addLayout(row)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(5000)
        lay.addWidget(self.view)
        self.feedback = QLabel("在底部时跟随新日志；向上翻阅时保留阅读位置。")
        self.feedback.setWordWrap(True)
        lay.addWidget(self.feedback)
        self._generation = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(4000)
        self.refresh()

    def _toggle_auto(self, on: bool):
        self.auto_btn.setText("自动刷新：开" if on else "自动刷新：关")
        self.timer.start(4000) if on else self.timer.stop()

    def refresh(self):
        kind = self.kind_box.currentIndex()
        generation = self._generation
        if kind >= 2:
            self._update_text(self.process_mgr.journal("douyin-friend-ai-bot" if kind == 2 else "douyin-interlude", 300))
            return
        def fetch():
            if kind == 0:
                return self.api.get("/api/logs/runtime", lines=300)
            data = self.api.get("/api/logs/audit", limit=100)
            return "\n".join(str(e) for e in data.get("entries", [])) or "暂无审计记录"
        def show(value):
            if self.kind_box.currentIndex() == kind and generation == self._generation:
                self._update_text(value)
        def failed(exc):
            if self.kind_box.currentIndex() == kind and generation == self._generation:
                self.feedback.setText(f"日志读取失败，已保留当前内容。可点击刷新重试：{exc}")
        self.api.run(f"logs-{generation}", fetch, show, failed)

    def _change_kind(self):
        self._generation += 1
        self.view.clear()
        self.refresh()

    def _update_text(self, value):
        text = str(value)
        old = self.view.toPlainText()
        if text == old:
            return
        bar = self.view.verticalScrollBar()
        following = not old or bar.value() >= bar.maximum() - 1
        old_value, horizontal = bar.value(), self.view.horizontalScrollBar().value()
        first = self.view.firstVisibleBlock()
        anchor_top = self.view.blockBoundingGeometry(first).translated(self.view.contentOffset()).top()
        old_lines, new_lines = old.split('\n'), text.split('\n')
        anchor_index = first.blockNumber()
        anchor = old_lines[anchor_index:anchor_index + 3]
        candidates = [i for i in range(len(new_lines)) if new_lines[i:i + len(anchor)] == anchor] if anchor else []
        new_index = min(candidates, key=lambda i: abs(i - anchor_index)) if candidates else anchor_index
        shift = new_index - anchor_index
        cursor = self.view.textCursor()
        position, selection_anchor = cursor.position(), cursor.anchor()
        character_shift = len('\n'.join(new_lines[:new_index])) - len('\n'.join(old_lines[:anchor_index]))
        self.view.setPlainText(text)
        restored = QTextCursor(self.view.document())
        end = self.view.document().characterCount() - 1
        restored.setPosition(max(0, min(end, selection_anchor + character_shift)))
        restored.setPosition(max(0, min(end, position + character_shift)), QTextCursor.KeepAnchor)
        self.view.setTextCursor(restored)
        if following:
            bar.setValue(bar.maximum())
        else:
            # Qt lazily lays out wrapped lines. Scroll to the anchor block first,
            # then restore the selection without letting it change the viewport.
            target = self.view.document().findBlockByNumber(new_index)
            anchor_cursor = QTextCursor(target)
            self.view.setTextCursor(anchor_cursor)
            self.view.centerCursor()
            line_height = max(1, self.view.fontMetrics().lineSpacing())
            for _ in range(3):
                top = self.view.blockBoundingGeometry(target).translated(self.view.contentOffset()).top()
                delta = round((top - anchor_top) / line_height)
                if not delta: break
                bar.setValue(bar.value() + delta)
            anchored_value = bar.value()
            self.view.setTextCursor(restored)
            bar.setValue(anchored_value)
        self.view.horizontalScrollBar().setValue(horizontal)
        self.feedback.setText("正在跟随最新日志。" if following else "正在查看历史日志，已保留阅读位置。点击“回到最新”恢复跟随。")
