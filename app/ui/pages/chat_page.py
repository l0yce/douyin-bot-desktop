"""A native activity inbox: scannable records beside a complete message reader."""
from __future__ import annotations
from datetime import datetime
from html import escape

from PySide6.QtCore import Qt, QTimer, QSize, QRectF
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSplitter,
    QTextBrowser, QVBoxLayout, QWidget, QFrame, QListWidget, QListWidgetItem,
    QStyledItemDelegate, QStyle,
)
from ...core.api_client import ApiClient
from .. import theme
from ..icons import icon, themed_icon

# 状态 -> (文案, 主题令牌)。这里存令牌名而不是色值，换主题后取到的就是新配色。
STATE = {
    'sent': ('已执行发送', 'ok'),
    'pending': ('等待处理', 'warn'),
    'preview': ('预览 · 未发送', 'preview'),
    'error': ('处理失败', 'bad'),
}
FALLBACK_STATE = ('运行记录', 'muted')


def state_style(key, fallback_name=None):
    """取状态的文案与色值；色值每次现取，避免留下上一套主题的颜色。"""
    name, token = STATE.get(key) or (fallback_name or FALLBACK_STATE[0], FALLBACK_STATE[1])
    return name, theme.color(token)


def label(text, role='Muted'):
    widget = QLabel(text)
    widget.setTextFormat(Qt.PlainText)
    widget.setObjectName(role)
    return widget


class FeedDelegate(QStyledItemDelegate):
    """Native selectable records; long text elides here and stays complete in the reader."""
    def sizeHint(self, option, index):
        return QSize(280, 112)

    def paint(self, painter, option, index):
        record = index.data(Qt.UserRole) or {}
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(4, 4, -4, -4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.color('selection') if selected else
                                theme.color('chip') if hovered else theme.color('plate')))
        painter.drawRoundedRect(QRectF(rect), 9, 9)
        if option.state & QStyle.State_HasFocus:
            painter.setPen(QColor(theme.color('accent_text')))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(rect.adjusted(1, 1, -1, -1)), 9, 9)
        friend = str(record.get('friend') or '未标注好友')
        avatar = QRectF(rect.left()+12, rect.top()+14, 34, 34)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.color('avatar_on') if selected else theme.color('avatar')))
        painter.drawRoundedRect(avatar, 11, 11)
        font = QFont(option.font); font.setPixelSize(15); font.setBold(True)
        painter.setFont(font); painter.setPen(QColor(theme.color('accent_text')))
        painter.drawText(avatar, Qt.AlignCenter, friend[:1])
        x = rect.left()+58
        width = max(20, rect.width()-72)
        painter.setPen(QColor(theme.color('text')))
        font.setPixelSize(14); painter.setFont(font)
        painter.drawText(x, rect.top()+28, painter.fontMetrics().elidedText(friend, Qt.ElideRight, width))
        font.setPixelSize(11); font.setBold(False); painter.setFont(font)
        painter.setPen(QColor(theme.color('faint')))
        painter.drawText(x, rect.top()+46, ChatPage.timestamp(record))
        preview = str(record.get('incoming_text') or record.get('reply_text') or record.get('reason') or record.get('error') or '选择查看完整处理记录').replace('\n', ' ')
        font.setPixelSize(12); painter.setFont(font)
        painter.setPen(QColor(theme.color('preview_text')))
        painter.drawText(rect.left()+12, rect.top()+70, painter.fontMetrics().elidedText(preview, Qt.ElideRight, max(20, rect.width()-24)))
        state, color = state_style(record.get('feed_state'), record.get('event_label') or '运行记录')
        painter.setPen(QColor(color))
        font.setPixelSize(11); painter.setFont(font)
        painter.drawText(rect.left()+12, rect.top()+92, painter.fontMetrics().elidedText(str(state), Qt.ElideRight, max(20, rect.width()-24)))
        painter.restore()


class ChatPage(QWidget):
    def __init__(self, api: ApiClient, parent=None):
        super().__init__(parent)
        self.api = api
        self.entries = []
        self.visible_entries = []
        self._selected_key = None
        self._reader_signature = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        toolbar = QFrame(); toolbar.setObjectName('Surface')
        tools = QVBoxLayout(toolbar); tools.setContentsMargins(16, 14, 16, 14); tools.setSpacing(12)
        search_row = QHBoxLayout(); search_row.setSpacing(12)
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索消息、回复或处理结果')
        self.search.setAccessibleName('搜索聊天动态')
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon('chat', size=18), QLineEdit.LeadingPosition)
        self.search_icon = self.search.actions()[0]
        theme.bind(self.search, lambda: self.search_icon.setIcon(icon('chat', size=18)))
        self.search.textChanged.connect(self.render)
        self.refresh_button = themed_icon(QPushButton('刷新动态'), 'reset', 'icon', 16)
        self.refresh_button.clicked.connect(self.refresh)
        search_row.addWidget(self.search, 1); search_row.addWidget(self.refresh_button)
        tools.addLayout(search_row)
        filters = QHBoxLayout(); filters.setSpacing(10)
        filters.addWidget(label('好友'))
        self.friend_filter = QComboBox()
        self.friend_filter.addItem('所有好友', '')
        self.friend_filter.setMinimumWidth(120)
        self.friend_filter.setAccessibleName('按好友筛选')
        self.friend_filter.currentIndexChanged.connect(self.render)
        filters.addWidget(self.friend_filter)
        filters.addSpacing(10)
        filters.addWidget(label('状态'))
        self.state_filter = QComboBox()
        self.state_filter.addItem('全部状态', '')
        for key, (name, _) in STATE.items():
            self.state_filter.addItem(name, key)
        self.state_filter.setAccessibleName('按处理状态筛选')
        self.state_filter.currentIndexChanged.connect(self.render)
        filters.addWidget(self.state_filter)
        filters.addStretch()
        self.auto_check = QCheckBox('自动刷新')
        self.auto_check.setChecked(True)
        filters.addWidget(self.auto_check)
        tools.addLayout(filters)
        layout.addWidget(toolbar)
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(8)
        feed_panel = QFrame(); feed_panel.setObjectName('Surface'); feed_panel.setMinimumWidth(260)
        feed = QVBoxLayout(feed_panel); feed.setContentsMargins(12, 16, 12, 12); feed.setSpacing(12)
        feed_header = QHBoxLayout()
        feed_header.addWidget(label('最近动态', 'SectionTitle'), 1)
        self.count_label = label('读取中', 'SmallMuted')
        feed_header.addWidget(self.count_label)
        feed.addLayout(feed_header)
        self.feed_list = QListWidget()
        self.feed_list.setObjectName('ActivityList')
        self.feed_list.setItemDelegate(FeedDelegate(self.feed_list))
        self.feed_list.setSpacing(2)
        self.feed_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.feed_list.setMouseTracking(True)
        self.feed_list.setAccessibleName('最近消息处理记录')
        self.feed_list.currentRowChanged.connect(self.show_detail)
        feed.addWidget(self.feed_list, 1)
        self.empty_note = label('暂无聊天动态\n机器人处理好友消息后，记录会出现在这里。', 'EmptyNote')
        self.empty_note.setWordWrap(True)
        self.empty_note.setAlignment(Qt.AlignCenter)
        feed.addWidget(self.empty_note, 1)
        split.addWidget(feed_panel)

        reader_panel = QFrame(); reader_panel.setObjectName('Surface'); reader_panel.setMinimumWidth(280)
        reader = QVBoxLayout(reader_panel); reader.setContentsMargins(20, 18, 20, 18); reader.setSpacing(12)
        reader_header = QHBoxLayout(); reader_header.setSpacing(12)
        self.avatar = label('聊', 'FriendAvatar'); self.avatar.setFixedSize(42, 42); self.avatar.setAlignment(Qt.AlignCenter)
        reader_header.addWidget(self.avatar)
        names = QVBoxLayout(); names.setSpacing(4)
        self.reader_title = label('消息详情', 'SectionTitle')
        self.reader_title.setWordWrap(True)
        self.reader_event = label('选择左侧动态，查看来信与处理结果', 'SmallMuted')
        self.reader_event.setWordWrap(True)
        names.addWidget(self.reader_title); names.addWidget(self.reader_event)
        reader_header.addLayout(names, 1)
        self.reader_state = label('', 'StateBadge')
        self.reader_state.hide()
        reader_header.addWidget(self.reader_state)
        reader.addLayout(reader_header)
        self.detail = QTextBrowser()
        self.detail.setObjectName('MessageReader')
        self.detail.setOpenExternalLinks(False)
        self.detail.setOpenLinks(False)
        self._apply_reader_stylesheet()
        self.detail.setPlainText('收到消息后会在这里显示处理记录。选择一条记录查看完整来信和回复。')
        reader.addWidget(self.detail, 1)
        split.addWidget(reader_panel)
        split.setStretchFactor(0, 2); split.setStretchFactor(1, 3)
        split.setSizes([340, 560])
        layout.addWidget(split, 1)
        self.feedback = label('正在读取最近聊天动态…', 'SmallMuted')
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        note = label('最近 120 条处理记录 · “已执行发送”表示网页端完成发送动作，实际投递以好友收到为准。', 'SmallMuted')
        note.setWordWrap(True); layout.addWidget(note)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._auto_refresh)
        self.timer.start(5000)
        theme.bind(self, self._on_theme_changed)

    # ---- 主题 ----
    def _reader_stylesheet(self):
        return (f'body {{color:{theme.color("text")};font-size:13px;}} p {{line-height:145%;}} '
                f'h4 {{font-size:12px;color:{theme.color("muted")};margin-top:18px;}}')

    def _apply_reader_stylesheet(self):
        self.detail.document().setDefaultStyleSheet(self._reader_stylesheet())

    def _on_theme_changed(self):
        """样式表管不到的三处：阅读区默认样式、自绘卡片、写进 HTML 的内联颜色。"""
        self._apply_reader_stylesheet()
        self.feed_list.viewport().update()
        self._reader_signature = None      # 清掉缓存，强制按新配色重拼阅读区
        self.show_detail()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def _auto_refresh(self):
        if self.auto_check.isChecked() and self.isVisible():
            self.refresh()

    def refresh(self):
        self.refresh_button.setEnabled(False)
        def failed(_):
            self.refresh_button.setEnabled(True)
            self.feedback.setText('聊天动态读取失败，已保留当前记录。请确认控制面板已启动，再点击“刷新动态”。')
        self.api.run('chat-feed', lambda: self.api.get('/api/logs/audit', limit=120), self.receive, failed)

    def receive(self, data):
        self.refresh_button.setEnabled(True)
        self.entries = [row for row in data.get('entries', []) if isinstance(row, dict)]
        selected = self.friend_filter.currentData()
        names = sorted({str(row.get('friend')) for row in self.entries if row.get('friend')})
        self.friend_filter.blockSignals(True)
        self.friend_filter.clear()
        self.friend_filter.addItem('所有好友', '')
        for name in names:
            self.friend_filter.addItem(name, name)
        self.friend_filter.setCurrentIndex(max(0, self.friend_filter.findData(selected)))
        self.friend_filter.blockSignals(False)
        self.render()

    @staticmethod
    def key(row):
        return tuple(str(row.get(name, '')) for name in ('ts', 'event', 'friend', 'delivery_id'))

    @staticmethod
    def timestamp(row):
        raw = row.get('ts')
        if not raw:
            return '未记录时间'
        try:
            return datetime.fromisoformat(str(raw).replace('Z', '+00:00')).astimezone().strftime('%m-%d %H:%M:%S')
        except ValueError:
            return str(raw)

    def render(self, *_):
        selected = self._selected_key
        scroll_position = self.feed_list.verticalScrollBar().value()
        friend = self.friend_filter.currentData()
        state = self.state_filter.currentData()
        query = self.search.text().strip().casefold()
        self.visible_entries = [row for row in self.entries if
            (not friend or str(row.get('friend', '')) == friend) and
            (not state or row.get('feed_state') == state) and
            (not query or query in ' '.join(str(row.get(key, '')) for key in
              ('friend', 'incoming_text', 'reply_text', 'event_label', 'reason', 'error')).casefold())]
        self.feed_list.blockSignals(True)
        self.feed_list.clear()
        active = 0
        for index, record in enumerate(self.visible_entries):
            if self.key(record) == selected:
                active = index
            item = QListWidgetItem()
            item.setData(Qt.UserRole, record)
            item.setText(f"{record.get('friend') or '未标注好友'} · {record.get('event_label') or '运行记录'}")
            item.setToolTip(item.text())
            item.setSizeHint(QSize(280, 112))
            self.feed_list.addItem(item)
        self.feed_list.blockSignals(False)
        has_records = bool(self.visible_entries)
        self.feed_list.setVisible(has_records)
        self.empty_note.setVisible(not has_records)
        self.count_label.setText(f'{len(self.visible_entries)} 条')
        if has_records:
            self.feed_list.setCurrentRow(active)
            self.show_detail()
            if self.key(self.visible_entries[active]) == selected:
                self.feed_list.verticalScrollBar().setValue(scroll_position)
            self.feedback.setText(f'显示 {len(self.visible_entries)} 条 / 最近读取 {len(self.entries)} 条记录')
        else:
            text = '没有匹配的聊天记录，请调整好友、状态或搜索条件。' if friend or state or query else '暂无聊天动态。机器人处理好友消息后，记录会出现在这里。'
            self.feedback.setText(text)
            self.empty_note.setText(text)
            self.detail.setPlainText(text)
            self.reader_title.setText('消息详情')
            self.reader_event.setText('选择左侧动态，查看来信与处理结果')
            self.reader_state.setText('')
            self.reader_state.hide()
            self.avatar.setText('聊')
            self._reader_signature = None

    def show_detail(self, *_):
        index = self.feed_list.currentRow()
        if not 0 <= index < len(self.visible_entries):
            return
        record = self.visible_entries[index]
        self._selected_key = self.key(record)
        signature = repr(sorted(record.items()))
        if signature == self._reader_signature:
            return
        self._reader_signature = signature
        friend = str(record.get('friend') or '未标注好友')
        self.avatar.setText(friend[:1])
        self.reader_title.setText(friend)
        self.reader_event.setText(str(record.get('event_label') or '运行记录'))
        state, color = state_style(record.get('feed_state'))
        self.reader_state.setText(state)
        self.reader_state.show()
        self.reader_state.setStyleSheet(f'color:{color};')
        def text(value):
            return escape(str(value)).replace('\n', '<br>')
        def bubble(title, value, reply=False):
            content = f'<p style="margin:0;color:{theme.color("text")};">{text(value)}</p>'
            bg = theme.color('selection') if reply else theme.color('chip')
            return (f'<h4>{title}</h4><table width="100%" cellspacing="0" cellpadding="0"><tr>'
                    + ('<td width="8%"></td>' if reply else '')
                    + f'<td bgcolor="{bg}"><table width="100%" cellpadding="14"><tr><td>{content}</td></tr></table></td>'
                    + ('' if reply else '<td width="8%"></td>') + '</tr></table>')
        result = (f'<p style="color:{theme.color("faint")};font-size:11px;">'
                  f'记录时间：{text(record.get("ts") or "未记录")}</p>')
        if record.get('incoming_text'):
            result += bubble('好友来信', record['incoming_text'])
        if record.get('reply_text'):
            title = '已执行发送的回复' if record.get('feed_state') == 'sent' else '预览回复（未发送）' if record.get('feed_state') == 'preview' else '拟回复内容'
            result += bubble(title, record['reply_text'], True)
        for key, name in (('reason', '处理说明'), ('error', '失败原因'), ('partial_reply', '部分回复')):
            if record.get(key):
                result += bubble(name, record[key])
        if not any(record.get(k) for k in ('incoming_text', 'reply_text', 'reason', 'error', 'partial_reply')):
            result += '<h4>处理记录</h4><p>这条记录未提供消息正文。</p>'
        self.detail.setHtml(result)

