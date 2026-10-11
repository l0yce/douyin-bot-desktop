"""Friend permissions with draft-safe editing and explicit save feedback."""
from __future__ import annotations
import json
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout,
    QWidget, QScrollArea, QFrame, QLineEdit, QComboBox, QLayout,
)
from PySide6.QtCore import Qt, QTimer
from ...core.api_client import ApiClient
from .. import theme
from ..icons import icon, themed_icon, themed_pixmap


def label(text, role='Muted'):
    result = QLabel(text)
    result.setTextFormat(Qt.PlainText)
    result.setObjectName(role)
    return result


class WhitelistPage(QWidget):
    def __init__(self, api: ApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self.friends = []
        self.checks = []
        self.rows = []
        self._baseline = '[]'
        self._revision = None
        self._loaded = False
        self._saving = False
        self._discovering = False
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(16)
        tools = QFrame(); tools.setObjectName('Surface')
        toolbar = QVBoxLayout(tools); toolbar.setContentsMargins(16, 14, 16, 14); toolbar.setSpacing(12)
        row = QHBoxLayout(); row.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索昵称或抖音号')
        self.search.setAccessibleName('搜索白名单好友')
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon('friends', size=18), QLineEdit.LeadingPosition)
        self.search_icon = self.search.actions()[0]
        theme.bind(self.search, lambda: self.search_icon.setIcon(icon('friends', size=18)))
        self.search.textChanged.connect(self._filter)
        row.addWidget(self.search, 1)
        self.filter = QComboBox()
        self.filter.addItem('全部好友', 'all')
        self.filter.addItem('已启用', 'enabled')
        self.filter.addItem('未启用', 'disabled')
        self.filter.setAccessibleName('按白名单启用状态筛选')
        self.filter.currentIndexChanged.connect(self._filter)
        row.addWidget(self.filter)
        self.refresh_button = QPushButton('刷新')
        themed_icon(self.refresh_button, 'reset', 'icon', 16)
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.refresh_button)
        self.discover_button = QPushButton('发现好友')
        themed_icon(self.discover_button, 'friends', 'accent_text', 16)
        self.discover_button.clicked.connect(self.discover)
        row.addWidget(self.discover_button)
        toolbar.addLayout(row)
        self.owner_label = label('我的抖音号：正在读取', 'SmallMuted')
        toolbar.addWidget(self.owner_label)
        lay.addWidget(tools)

        workspace = QHBoxLayout(); workspace.setSpacing(16)
        list_panel = QFrame(); list_panel.setObjectName('Surface')
        left = QVBoxLayout(list_panel); left.setContentsMargins(16, 16, 16, 12); left.setSpacing(12)
        list_header = QHBoxLayout()
        list_header.addWidget(label('好友列表', 'SectionTitle'), 1)
        self.list_count = label('读取中', 'SmallMuted')
        list_header.addWidget(self.list_count)
        left.addLayout(list_header)
        scroll = QScrollArea(); scroll.setFrameShape(QFrame.NoFrame); scroll.setWidgetResizable(True)
        container = QWidget()
        self.list_area = QVBoxLayout(container)
        self.list_area.setContentsMargins(0, 0, 0, 0); self.list_area.setSpacing(10)
        self.list_area.setAlignment(Qt.AlignTop)
        scroll.setWidget(container); left.addWidget(scroll, 1)
        self.friend_scroll = scroll
        self.empty = label('正在读取好友白名单…', 'EmptyNote')
        self.empty.setAlignment(Qt.AlignCenter); self.empty.setWordWrap(True)
        left.addWidget(self.empty, 1)
        workspace.addWidget(list_panel, 3)

        scope_scroll = QScrollArea()
        scope_scroll.setFrameShape(QFrame.NoFrame)
        scope_scroll.setWidgetResizable(True)
        scope_scroll.setFixedWidth(244)
        scope_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scope_panel = QFrame(); scope_panel.setObjectName('Surface')
        scope_scroll.setWidget(scope_panel)
        scope = QVBoxLayout(scope_panel); scope.setContentsMargins(20, 22, 20, 20); scope.setSpacing(16)
        scope.setSizeConstraint(QLayout.SetMinimumSize)
        mark = QLabel(); themed_pixmap(mark, 'shield', 'accent_text', 30)
        mark.setFixedSize(30, 30)
        scope.addWidget(mark)
        scope.addWidget(label('回复范围', 'SectionTitle'))
        self.scope_summary = label('读取白名单后显示启用范围', 'ScopeSummary')
        self.scope_summary.setWordWrap(True); scope.addWidget(self.scope_summary)
        self.draft_note = label('只对已保存并启用的好友自动回复。', 'Muted')
        self.draft_note.setWordWrap(True); scope.addWidget(self.draft_note)
        divider = QFrame(); divider.setObjectName('SocialDivider'); divider.setFixedHeight(1); scope.addWidget(divider)
        for title, note in (
            ('导入登录凭据', '先在运行状态页导入 Cookies。'),
            ('发现好友', '停止机器人后读取好友列表，不会发送消息。'),
            ('选择回复对象', '勾选好友并保存，新发现的好友默认未启用。'),
        ):
            heading = label(title, 'GuideTitle')
            desc = label(note, 'SmallMuted'); desc.setWordWrap(True)
            scope.addWidget(heading); scope.addWidget(desc)
        scope.addStretch()
        workspace.addWidget(scope_scroll)
        lay.addLayout(workspace, 1)
        footer = QFrame(); footer.setObjectName('Surface')
        bottom = QHBoxLayout(footer); bottom.setContentsMargins(16, 12, 16, 12); bottom.setSpacing(16)
        self.hint = label('先导入 Cookies 并停止机器人，再发现好友。', 'Muted')
        self.hint.setWordWrap(True); bottom.addWidget(self.hint, 1)
        self.save_button = QPushButton('保存修改')
        self.save_button.setProperty('primary', True)
        self.save_button.setMinimumWidth(108)
        self.save_button.clicked.connect(self.save)
        bottom.addWidget(self.save_button)
        lay.addWidget(footer)
        self.poll = QTimer(self); self.poll.setInterval(2000); self.poll.timeout.connect(self._poll_discovery)
        self._update_summary()
        self.refresh()

    def _items(self):
        return [dict(friend, enabled=check.isChecked()) for friend, check in zip(self.friends, self.checks)]

    def _signature(self):
        return json.dumps(self._items(), ensure_ascii=False, sort_keys=True)

    def _dirty(self):
        return self._signature() != self._baseline

    def _clear(self):
        while self.list_area.count():
            item = self.list_area.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.checks.clear()
        self.rows.clear()

    def refresh(self):
        if self._saving or self._discovering:
            return
        if self._dirty():
            answer = QMessageBox.question(self, '有未保存修改', '刷新会重新读取已保存的白名单，放弃当前修改吗？',
                                          QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        # Edits made while the asynchronous read is pending also stay protected.
        signature = self._signature()
        self.refresh_button.setEnabled(False)
        self.hint.setText('正在读取好友白名单…')
        def received(data):
            self.refresh_button.setEnabled(True)
            if self._signature() != signature:
                self.hint.setText('读取已完成，已保留读取期间的未保存修改。')
                return
            self._show_friends(data)
            self.hint.setText('选择需要自动回复的好友，修改后点击保存。')
        def failed(exc):
            self.refresh_button.setEnabled(True)
            self.hint.setText(f'读取失败，已保留当前好友与修改：{exc}')
            if not self._loaded:
                self.empty.setText('暂时无法读取好友\n请确认控制面板已启动，再点击刷新。')
        self.api.run('whitelist', lambda: self.api.get('/api/whitelist'), received, failed)

    def _show_friends(self, data, mark_saved=True):
        self._clear()
        self._revision = data.get("revision", self._revision)
        self.friends = [friend for friend in data.get('friends', []) if isinstance(friend, dict)]
        self._loaded = True
        if 'owner_douyin_id' in data or self.owner_label.text() == '我的抖音号：正在读取':
            self.owner_label.setText(f"我的抖音号：{data.get('owner_douyin_id') or '未配置'}")
        for friend in self.friends:
            row = QFrame(); row.setObjectName('FriendRow')
            row.setProperty('enabledFriend', bool(friend.get('enabled')))
            content = QHBoxLayout(row); content.setContentsMargins(14, 16, 14, 16); content.setSpacing(12)
            name = str(friend.get('name') or '未提供昵称')
            avatar = label(name[:1], 'FriendAvatar')
            avatar.setFixedSize(42, 42); avatar.setAlignment(Qt.AlignCenter)
            content.addWidget(avatar)
            names = QVBoxLayout(); names.setSpacing(6)
            display = label(name, 'ServiceTitle'); display.setWordWrap(True)
            names.addWidget(display)
            identifier = friend.get('douyin_id')
            identity = label(f'抖音号：{identifier}' if identifier else '未提供抖音号', 'SmallMuted')
            identity.setWordWrap(True)
            identity.setTextInteractionFlags(Qt.TextSelectableByMouse)
            names.addWidget(identity)
            content.addLayout(names, 1)
            check = QCheckBox('自动回复')
            check.setAccessibleName(f'{name}自动回复')
            check.setChecked(bool(friend.get('enabled')))
            content.addWidget(check)
            self.checks.append(check); self.rows.append(row)
            check.toggled.connect(lambda checked, target=row: self._toggled(target, checked))
            self.list_area.addWidget(row)
        if mark_saved:
            self._baseline = self._signature()
        self._update_summary()
        self._filter()

    def _toggled(self, row, checked):
        row.setProperty('enabledFriend', checked)
        row.style().unpolish(row); row.style().polish(row); row.update()
        self._update_summary()
        self._filter()

    def _update_summary(self):
        enabled = sum(check.isChecked() for check in self.checks)
        self.scope_summary.setText(f'{enabled} / {len(self.friends)} 位好友已选择' if self._loaded else '读取白名单后显示启用范围')
        dirty = self._dirty()
        self.draft_note.setText('当前选择尚未保存，保存后才会更新回复范围。' if dirty else '只对已保存并启用的好友自动回复。')
        self.save_button.setEnabled(self._loaded and dirty and not self._saving and not self._discovering)
        self.save_button.setText('正在保存…' if self._saving else '保存修改')
        self.discover_button.setEnabled(not self._saving and not self._discovering)
        if dirty and not self._saving and not self._discovering:
            self.hint.setText('有未保存修改 · 请保存后使新的回复范围生效。')
        elif not dirty and self.hint.text().startswith('有未保存修改'):
            self.hint.setText('当前选择与已保存的白名单一致。')

    def _filter(self, *_):
        query = self.search.text().strip().casefold()
        state = self.filter.currentData()
        visible = 0
        for friend, check, row in zip(self.friends, self.checks, self.rows):
            matches = (not query or query in f"{friend.get('name', '')} {friend.get('douyin_id', '')}".casefold())
            matches = matches and (state == 'all' or state == 'enabled' and check.isChecked() or state == 'disabled' and not check.isChecked())
            row.setVisible(matches)
            visible += int(matches)
        self.list_count.setText(f'{visible} / {len(self.friends)} 位')
        self.empty.setVisible(visible == 0)
        self.friend_scroll.setVisible(visible > 0)
        if self._loaded:
            self.empty.setText('没有匹配的好友\n请调整搜索或启用状态筛选。' if self.friends else '白名单还没有好友\n导入 Cookies 后点击“发现好友”。')

    def discover(self):
        if self._saving or self._discovering:
            return
        self._discovering = True
        self.refresh_button.setEnabled(False)
        self._update_summary()
        def started(_):
            self.hint.setText('正在只读发现好友，浏览器可能打开；不会发送消息。')
            self.poll.start()
        def failed(exc):
            self._discovering = False
            self.refresh_button.setEnabled(True)
            self._update_summary()
            self.hint.setText(f'发现好友失败：{exc}')
        self.api.run('discover-start', lambda: self.api.post('/api/discover/run'), started, failed)

    def _poll_discovery(self):
        self.api.run('discover-poll', lambda: self.api.get('/api/discover'), self._discovered,
                     lambda exc: self.hint.setText(f'发现状态读取失败，正在重试：{exc}'))

    def _discovered(self, result):
        if result.get('running'):
            return
        self.poll.stop()
        self._discovering = False
        self.refresh_button.setEnabled(True)
        self._update_summary()
        if result.get('returncode') != 0:
            self.hint.setText('发现失败，请检查 Cookies 是否有效、浏览器是否可用。\n' + result.get('output', '')[-1200:])
            return
        existing = self._items()
        known = {friend.get('sec_uid') for friend in existing if friend.get('sec_uid')}
        for candidate in result.get('candidates', []):
            uid = candidate.get('sec_uid')
            if not uid or uid not in known:
                existing.append(dict(candidate, enabled=False))
                if uid:
                    known.add(uid)
        self._show_friends({'friends': existing}, mark_saved=False)
        self.hint.setText(f"发现 {len(result.get('candidates', []))} 位好友。新好友默认未启用；保存后更新白名单。")

    def save(self):
        if not self._loaded or not self._dirty() or self._saving or self._discovering:
            return
        items = self._items()
        self._saving = True
        for row in self.rows:
            row.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self._update_summary()
        def finish():
            self._saving = False
            for row in self.rows:
                row.setEnabled(True)
            self.refresh_button.setEnabled(True)
        def saved(result):
            finish()
            self._revision = result.get("revision", self._revision)
            self._baseline = json.dumps(items, ensure_ascii=False, sort_keys=True)
            self._update_summary()
            self.hint.setText(f"已保存 · 已更新 {result.get('count', len(items))} 位好友的回复范围。")
        def failed(exc):
            finish(); self._update_summary()
            self.hint.setText(f'保存失败，修改已保留，请重试：{exc}')
        self.api.run('whitelist-save', lambda: self.api.put('/api/whitelist', {'friends': items, 'revision': self._revision}), saved, failed)

