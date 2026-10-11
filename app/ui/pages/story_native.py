"""Native Qt interlude management. All business operations use existing panel APIs.

页面选项与内容展示对齐控制面板：字段名走统一中文词表（未知字段回退为“补充信息”），
记忆、日程与概况按面板分区呈现；完整参数改为 schema 驱动的可视化表单。
"""
from __future__ import annotations

import json
import uuid
from html import escape

from PySide6.QtCore import Qt, QDateTime
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget,
    QFormLayout, QScrollArea, QLineEdit, QPlainTextEdit, QCheckBox, QSpinBox, QComboBox,
    QListWidget, QListWidgetItem, QSplitter, QDateTimeEdit, QDialog, QDialogButtonBox, QMessageBox,
    QFileDialog)

from .. import theme
from . import story_render as R
from .story_config_form import ConfigForm
from .story_labels import display_value, fmt_time
from .story_widgets import (Collapsible, RichBody, SectionPane, button, button_row, heading,
    hint, plain_empty, record_card, subheading)

STORY_FIELDS = {'characterName': '角色名字', 'characterProfile': '角色人设', 'world': '世界背景',
                'relationship': '关系基础', 'supportingCast': '其他角色', 'location': '生活地点',
                'style': '聊天风格', 'startingSituation': '初始情境'}
ACTIONS = {'start': '启动故事', 'pause': '暂停剧情处理', 'resume': '恢复剧情处理', 'advance': '立即推进剧情',
    'compact': '压缩剧情记忆', 'overlay-compact': '整理演化摘要', 'overlay-clear': '清除演化层',
    'schedule-refresh': '重新规划日程', 'fact-add': '添加长期记忆', 'fact-edit': '修改长期记忆',
    'forget': '忘记这条记忆', 'note': '添加剧情备注', 'cancel-intent': '取消待办',
    'reject-patch': '拒绝设定变更', 'rebase': '重置时间游标', 'purge-range': '清理时间范围',
    'purge-platform': '清理抖音剧情', 'reset': '重开当前故事', 'clear-database': '清空所有故事'}
DESTRUCTIVE = {'forget', 'cancel-intent', 'reject-patch', 'overlay-clear', 'rebase', 'purge-range',
    'purge-platform', 'reset', 'clear-database'}
LIFE_STATUS = {'busy': '忙碌中', 'asleep': '休息中', 'idle': '空闲中'}


class SettingsForm(QWidget):
    """Revision-aware form; refreshing cannot silently discard local edits."""

    def __init__(self, api, endpoint, specification, help_text, story=False):
        super().__init__()
        self.api, self.endpoint, self.story = api, endpoint, story
        self.revision, self.dirty, self.busy = '', False, False
        self.fields = {}
        layout = QVBoxLayout(self)
        tip = QLabel(help_text)
        tip.setObjectName('Muted')
        tip.setWordWrap(True)
        layout.addWidget(tip)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        for key, title, kind, bounds in specification:
            if kind == 'bool':
                edit = QCheckBox(title)
                form.addRow('', edit)
                signal = edit.toggled
            elif kind == 'int':
                edit = QSpinBox()
                edit.setRange(*bounds)
                form.addRow(title, edit)
                signal = edit.valueChanged
            elif kind == 'long':
                edit = QPlainTextEdit()
                edit.setMinimumHeight(110)
                form.addRow(title, edit)
                signal = edit.textChanged
            else:
                edit = QLineEdit()
                form.addRow(title, edit)
                signal = edit.textChanged
            edit.setAccessibleName(title)
            signal.connect(self.mark_dirty)
            self.fields[key] = edit
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.feedback = QLabel('点击重新读取以加载设置。')
        self.feedback.setObjectName('Muted')
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        row = QHBoxLayout()
        self.save_button = button('保存并生效', self.save, True)
        self.reload_button = button('重新读取', self.reload)
        row.addWidget(self.save_button)
        row.addWidget(self.reload_button)
        row.addStretch()
        layout.addLayout(row)
        self.lock()

    def mark_dirty(self, *_):
        self.dirty = True
        self.feedback.setText('有修改尚未保存。')
        self.lock()

    def lock(self):
        self.save_button.setEnabled(bool(self.revision) and self.dirty and not self.busy)
        self.reload_button.setEnabled(not self.busy)
        for edit in self.fields.values():
            edit.setEnabled(bool(self.revision) and not self.busy)

    def values(self):
        return {key: widget.isChecked() if isinstance(widget, QCheckBox)
                else widget.value() if isinstance(widget, QSpinBox)
                else widget.toPlainText() if isinstance(widget, QPlainTextEdit)
                else widget.text() for key, widget in self.fields.items()}

    def receive(self, data):
        source = {**data.get('story', {}), **{k: data.get(k) for k in self.fields if k not in STORY_FIELDS}} if self.story else data['settings']
        for key, edit in self.fields.items():
            edit.blockSignals(True)
            value = source.get(key)
            if isinstance(edit, QCheckBox):
                edit.setChecked(bool(value))
            elif isinstance(edit, QSpinBox):
                edit.setValue(int(value if value is not None else edit.minimum()))
            elif isinstance(edit, QPlainTextEdit):
                edit.setPlainText(str(value or ''))
            else:
                edit.setText(str(value or ''))
            edit.blockSignals(False)
        self.revision, self.dirty = data['revision'], False
        self.feedback.setText('已读取当前设置。')

    def failed(self, exc):
        self.busy = False
        self.feedback.setText(f'操作失败，修改已保留。请检查服务；若配置已更新，请重新读取后再修改。\n{exc}')
        self.lock()

    def reload(self, checked=False):
        if self.busy:
            return
        if self.dirty and QMessageBox.question(self, '重新读取', '放弃本页未保存的修改，重新读取？') != QMessageBox.Yes:
            return
        self.busy = True
        self.lock()
        self.feedback.setText('正在读取…')

        def done(data):
            self.busy = False
            self.receive(data)
            self.lock()

        self.api.run('story-form:' + self.endpoint, lambda: self.api.get(self.endpoint), done, self.failed)

    def ensure_loaded(self):
        if not self.revision and not self.busy:
            self.reload()

    def save(self):
        if self.busy or not self.revision or not self.dirty:
            return
        values = self.values()
        if self.story:
            if not values['characterName'].strip() or not values['characterProfile'].strip():
                self.feedback.setText('请填写角色名字与角色人设。')
                return
            body = {'revision': self.revision, 'story': {k: values[k] for k in STORY_FIELDS},
                    **{k: v for k, v in values.items() if k not in STORY_FIELDS}}
        else:
            body = {'revision': self.revision, 'settings': values}
        self.busy = True
        self.lock()
        self.feedback.setText('正在保存并应用，请稍候…')

        def done(data):
            self.busy = False
            self.receive(data)
            self.feedback.setText('已保存并生效。')
            self.lock()

        self.api.run('story-form:' + self.endpoint, lambda: self.api.put(self.endpoint, body), done, self.failed)


class RecordPane(QWidget):
    """记录目录 + 阅读区，与控制面板的“选一条再看完整内容”一致。"""

    def __init__(self):
        super().__init__()
        self.records = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText('筛选已加载记录')
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        split = QSplitter()
        self.list = QListWidget()
        self.detail = RichBody()
        split.addWidget(self.list)
        split.addWidget(self.detail)
        split.setSizes([280, 560])
        layout.addWidget(split, 1)
        self.search.textChanged.connect(self.render)
        self.list.currentItemChanged.connect(self.show_detail)
        # 目录项与阅读区都是拼好的富文本，换主题后要按缓存记录重新拼一遍。
        theme.bind(self, self.render)

    def selected(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    @staticmethod
    def identity(record):
        return (str(record.get('_category', record.get('kind', ''))) + ':'
                + str(record.get('id', record.get('content', record.get('summary', '')))))

    def receive(self, records):
        selected = self.selected()
        self.records = records
        self.render(selected)

    def render(self, selected=None):
        selected = selected if isinstance(selected, dict) else self.selected()
        chosen = self.identity(selected) if selected else None
        self.list.blockSignals(True)
        self.list.clear()
        term = self.search.text().casefold()
        for record in self.records:
            kind, stamp = R.record_title(record)
            haystack = ' '.join([str(record.get('content', '')), kind, str(record.get('actor') or ''),
                                 stamp]).casefold()
            if term and term not in haystack:
                continue
            preview = R.record_preview(record) or '查看这条记录的详情'
            text = f'{kind}  {stamp}'.rstrip()
            text += f'\n{preview[:64]}'
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, record)
            self.list.addItem(item)
            if chosen == self.identity(record):
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)
        else:
            self.show_detail()
        if not self.list.count():
            self.detail.set_content(f'<p style="color:{theme.color("faint")}">'
                                    f'{"没有匹配的已加载记录。换个关键词，或读取更早记录。" if self.records else "当前时间范围内没有记录。"}'
                                    f'</p>')

    def show_detail(self, *_):
        """阅读区与控制面板一致：类型 + 时间 + 发言者，正文即记录本身。"""
        record = self.selected()
        if not record:
            return
        kind, stamp = R.record_title(record)
        actor = R.actor_name(record)
        sub = ' · '.join(part for part in (stamp, actor) if part)
        parts = [f'<p style="color:{theme.color("accent_text")};font-size:15px;font-weight:600;'
                 f'margin:0 0 4px">{escape(kind)}</p>']
        if sub:
            parts.append(f'<p style="color:{theme.color("hint")};font-size:12px;margin:0 0 10px">{escape(sub)}</p>')
        content = str(record.get('content') or record.get('summary') or '').strip()
        parts.append(f'<p style="color:{theme.color("text")};margin:0">'
                     f'{escape(content).replace(chr(10), "<br>")}</p>'
                     if content else
                     f'<p style="color:{theme.color("hint")};margin:0">这条记录没有正文。</p>')
        delivery = record.get('deliveryActions')
        if isinstance(delivery, (list, dict)) and delivery:
            parts.append(f'<p style="color:{theme.color("key")};margin:12px 0 4px">发送情况</p>'
                         f'{R.pairs_html(delivery)}')
        self.detail.set_content(''.join(parts))


class MemoryPane(SectionPane):
    """记忆与演化：长期记忆、剧情摘要、设定演化，选项与面板一致。"""

    def __init__(self, controller):
        super().__init__()
        self.controller = controller

    def receive(self, data):
        self.clear()
        controller = self.controller
        overlay = data.get('overlay') or {}

        self.add(heading('长期记忆'))
        self.add(hint('事实会持续积累。修改会保留旧记录的历史，忘记后不再参与当前记忆。'))
        self.add(button_row(
            button(ACTIONS['fact-add'], lambda: controller.open_action('fact-add')),
            button(ACTIONS['compact'], lambda: controller.open_action('compact')),
            button('刷新', controller.reload_page)))
        facts = [f for f in (data.get('facts') or []) if isinstance(f, dict)]
        if facts:
            for fact in facts:
                info = R.meta_line(display_value(fact.get('scope'), 'scope'),
                                   f'#{fact["id"]}' if fact.get('id') is not None else None,
                                   fmt_time(fact.get('updatedAt')) if fact.get('updatedAt') else None)
                self.add(record_card(info, R.record_html(fact, skip=('id', 'scope', 'updatedAt', 'createdAt')),
                                     [button(ACTIONS['fact-edit'], lambda _=False, r=fact: controller.open_action('fact-edit', r)),
                                      button(ACTIONS['forget'], lambda _=False, r=fact: controller.open_action('forget', r))]))
        else:
            self.add(plain_empty('还没有长期事实记忆。'))

        self.add(self._list_module('压缩后的剧情摘要', data.get('memories') or [],
            lambda item: record_card(
                fmt_time(item.get('createdAt')) if item.get('createdAt') else None,
                R.record_html(item, skip=('id', 'createdAt')),
                ())))

        self.add(heading('设定演化'))
        self.add(hint('查看角色、世界与关系在互动中的变化。'))
        self.add(button_row(
            button(ACTIONS['overlay-compact'], lambda: controller.open_action('overlay-compact')),
            button(ACTIONS['overlay-clear'], lambda: controller.open_action('overlay-clear'))))
        if overlay.get('state'):
            self.add(record_card(None, R.pairs_html(overlay['state'])))
        self.add(subheading('待处理的设定变更'))
        proposed = [p for p in (overlay.get('proposed') or []) if isinstance(p, dict)]
        if proposed:
            for patch in proposed:
                self.add(record_card(
                    fmt_time(patch.get('createdAt')) if patch.get('createdAt') else None,
                    R.record_html(patch, prose_keys=('summary',), skip=('id', 'createdAt')),
                    [button(ACTIONS['reject-patch'], lambda _=False, r=patch: controller.open_action('reject-patch', r))]))
        else:
            self.add(plain_empty('没有待处理的设定变更。'))
        self.add(self._pairs_module('已应用变更与关系演化', {
            'applied': overlay.get('applied'), 'snapshots': overlay.get('snapshots'),
            'participantOverlays': overlay.get('participantOverlays')}))

    def _list_module(self, title, items, render):
        entries = [item for item in items if isinstance(item, dict)]
        def build(layout):
            if not entries:
                layout.addWidget(hint('暂无记录。'))
                return
            for entry in entries:
                layout.addWidget(render(entry))
        widget = Collapsible(title, build)
        widget.set_count(len(entries))
        return widget

    def _pairs_module(self, title, payload):
        def build(layout):
            body = RichBody()
            body.set_content(R.pairs_html(payload))
            layout.addWidget(body)
        return Collapsible(title, build)


class SchedulePane(SectionPane):
    """日程与待办：角色日程、待办与延迟消息、世界事件、网页观察。"""

    def __init__(self, controller):
        super().__init__()
        self.controller = controller

    def receive(self, data):
        self.clear()
        controller = self.controller
        self.add(heading('角色日程'))
        self.add(hint('预规划是角色生活安排，实际发生的事情以剧情记录为准。'))
        self.add(button_row(
            button(ACTIONS['schedule-refresh'], lambda: controller.open_action('schedule-refresh')),
            button('刷新', controller.reload_page)))
        if data.get('schedule'):
            self.add(record_card(None, R.pairs_html(data['schedule'])))
        else:
            self.add(plain_empty('还没有日程。启用日程预规划后，引擎在后续回合或记忆整理时建立安排。'))

        self.add(subheading('待办与延迟消息'))
        intents = [i for i in (data.get('intents') or []) if isinstance(i, dict)]
        if intents:
            for intent in intents:
                info = R.meta_line(display_value(intent.get('type'), 'type'),
                                   fmt_time(intent.get('notBefore')) if intent.get('notBefore') else None)
                self.add(record_card(info, R.record_html(intent, skip=('id', 'type', 'notBefore')),
                                     [button(ACTIONS['cancel-intent'], lambda _=False, r=intent: controller.open_action('cancel-intent', r))]))
        else:
            self.add(plain_empty('没有待办或延迟消息。'))

        self.add(subheading('世界事件'))
        events = [e for e in (data.get('events') or []) if isinstance(e, dict)]
        if events:
            for event in events:
                info = R.meta_line(display_value(event.get('status'), 'status'),
                                   fmt_time(event.get('occursAt')) if event.get('occursAt') else None)
                self.add(record_card(info, R.record_html(event, skip=('id', 'status', 'occursAt'))))
        else:
            self.add(plain_empty('没有世界事件。'))

        observations = [o for o in (data.get('observations') or []) if isinstance(o, dict)]
        widget = Collapsible('网页观察记录', self._observation_builder(observations))
        widget.set_count(len(observations))
        self.add(widget)

    def _observation_builder(self, observations):
        def build(layout):
            if not observations:
                layout.addWidget(hint('暂无记录。'))
                return
            for observation in observations:
                title = observation.get('title') or observation.get('query') or '网页观察'
                info = R.meta_line(title, display_value(observation.get('status'), 'status'))
                layout.addWidget(record_card(
                    info, R.record_html(observation, skip=('id', 'status', 'title')),
                    [hint(str(observation.get('url'))) if observation.get('url') else None]))
        return build


class StoryPage(QWidget):
    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.data = {}
        self.action_busy = False
        self.timeline_entries = []
        self.timeline_query = None
        self.cursor = None
        layout = QVBoxLayout(self)
        self.feedback = QLabel('启动幕间引擎后即可读取剧情。')
        self.feedback.setObjectName('Muted')
        self.feedback.setWordWrap(True)
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.feedback)
        self._build_overview()
        self._build_settings()
        self._build_timeline()
        self.memory = MemoryPane(self)
        self.tabs.addTab(self.memory, '记忆与演化')
        self.schedule = SchedulePane(self)
        self.tabs.addTab(self.schedule, '日程与待办')
        self.cooperation = SettingsForm(api, '/api/conversation-context', [
            ('enabled', '参考双方聊天记录', 'bool', None),
            ('history_messages', '最近聊天消息条数', 'int', (5, 100)),
            ('cancel_on_manual', '我手动发消息时取消待发送的机器人回复', 'bool', None)],
            '将你手动发送的消息纳入对应好友的上下文。条数是双方消息总数，按好友区分；实际数量受聊天界面加载情况影响。')
        self.tabs.addTab(self.cooperation, '聊天协作')
        self.video = SettingsForm(api, '/api/video-comments', [
            ('enabled', '使用视频评论作为回复参考', 'bool', None),
            ('comment_count', '参考评论条数', 'int', (1, 5)),
            ('max_comment_chars', '每条评论最多字数', 'int', (30, 150)),
            ('cache_hours', '缓存时间（小时）', 'int', (0, 72)),
            ('timeout_seconds', '读取等待上限（秒）', 'int', (15, 90))],
            '仅参考卡片信息与评论，不观看视频。评论不可读取时降级使用卡片信息；评论是网友观点，不能当作已经看过视频的事实。')
        self.tabs.addTab(self.video, '视频评论')
        self.advanced = ConfigForm(api)
        self.tabs.addTab(self.advanced, '高级设置')
        self._build_tools()
        self.tabs.currentChanged.connect(self.tab_changed)

    # ---- 概况 ----
    def _build_overview(self):
        page = SectionPane()
        self.overview_actions = QWidget()
        self.overview_actions_layout = QHBoxLayout(self.overview_actions)
        self.overview_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.overview_actions_layout.setSpacing(8)
        page.add(self.overview_actions)
        self.overview_text = RichBody()
        page.add(self.overview_text)
        self._set_overview_actions(None)
        # 概况正文是拼好的富文本，换主题后按最近一次读到的数据重拼。
        theme.bind(self.overview_text, lambda: self._render_overview(self.data))
        self.tabs.addTab(page, '概况')

    def _set_overview_actions(self, story):
        while self.overview_actions_layout.count():
            item = self.overview_actions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        if story:
            self.overview_actions_layout.addWidget(button(ACTIONS['pause'], lambda: self.open_action('pause')))
            self.overview_actions_layout.addWidget(button(ACTIONS['resume'], lambda: self.open_action('resume')))
            self.overview_actions_layout.addWidget(button(ACTIONS['advance'], lambda: self.open_action('advance')))
        else:
            self.overview_actions_layout.addWidget(button(ACTIONS['start'], lambda: self.open_action('start'), True))
        self.overview_actions_layout.addWidget(button('刷新状态', self.reload_page))
        self.overview_actions_layout.addStretch(1)

    def _render_overview(self, data):
        story = data.get('story')
        self._set_overview_actions(story)
        if not story:
            self.overview_text.set_content(
                f'<p style="color:{theme.color("faint")};line-height:1.9">等待故事开始。<br><br>'
                '先填写角色设定、配置模型并启用至少一位白名单好友，然后点击“启动故事”；也可以等待好友发来消息。</p>')
            return
        state = story.get('state') or {}
        frame = state.get('sceneFrame') or {}
        overlay = state.get('settingOverlay') or {}
        setting = story.get('setting') or {}
        running = data.get('phase') == 'running'
        rows = {
            '角色': (setting.get('character') or {}).get('name'),
            '剧情已推进到': fmt_time(story.get('cursorAt')) if story.get('cursorAt') else '',
            '当前地点' if frame.get('place') else '设定地点':
                frame.get('place') or overlay.get('location') or setting.get('location'),
            '正在做什么': frame.get('ongoingActivity'),
            '当前心情': frame.get('affectiveBaseline'),
            '生活状态': LIFE_STATUS.get((state.get('lifeStatus') or {}).get('status')),
        }
        pending = int((data.get('queue') or {}).get('pending') or 0)
        unknown = int((data.get('queue') or {}).get('unknown') or 0)
        queue_note = (f'有 {unknown} 条消息需要核实发送结果，可在日志中查看。' if unknown
                      else f'有 {pending} 条消息等待发送。' if pending else '')
        badge = (f'<span style="background:{theme.color("selection")};'
                 f'color:{theme.color("selection_text")};">运行中</span>' if running else
                 f'<span style="background:{theme.color("chip")};'
                 f'color:{theme.color("chip_text")};">已暂停</span>')
        parts = [f'<h2 style="color:{theme.color("text")};font-size:18px;margin:0 0 4px">角色近况 {badge}</h2>',
                 f'<p style="color:{theme.color("faint")};margin:0 0 10px">'
                 f'{"剧情引擎已连接" if (data.get("queue") or {}).get("ready") else "剧情引擎正在准备"}'
                 f'{" · " + escape(queue_note) if queue_note else ""}</p>',
                 R.rows_html(rows)]
        parts.append(f'<h3 style="color:{theme.color("text_soft")};font-size:15px;margin:14px 0 6px">'
                     '参与者与关系</h3>')
        participants = [p for p in (data.get('participants') or []) if isinstance(p, dict)]
        if participants:
            for participant in participants:
                status = participant.get('state') or {}
                last = max([t for t in (participant.get('lastActiveAt'), status.get('lastUserMessageAt'),
                                        status.get('lastCharacterMessageAt')) if t] or [''])
                notes = status.get('relationshipNotes')
                notes = '；'.join(x for x in notes if isinstance(x, str)) if isinstance(notes, list) else ''
                name = participant.get('name') or participant.get('displayName') or participant.get('username') or '聊天好友'
                parts.append(f'<p style="color:{theme.color("text")};font-weight:600;'
                             f'margin:10px 0 4px">{escape(str(name))}</p>')
                parts.append(R.rows_html({
                    '当前关系': status.get('relationshipOverlay') or participant.get('relationship'),
                    '最近互动': fmt_time(last) if last else '',
                    '关系变化': notes}))
        else:
            parts.append(f'<p style="color:{theme.color("faint")}">好友发来消息后，会在这里显示关系记录。</p>')
        parts.append(f'<p style="color:{theme.color("faint")};margin-top:12px;line-height:1.8">'
                     '完整经过在“剧情记录”中查看，生活安排在“日程与待办”中查看。<br>'
                     '聊天会推进角色剧情，并按需要积累记忆、关系变化和后续计划。<br>'
                     '图片和分享视频通过抖音适配器读取；分享视频目前读取卡片信息，不会观看视频内容。<br>'
                     '日程、情绪变化、世界事件与网页浏览是否启用，可在“高级设置”中调整。</p>')
        self.overview_text.set_content(''.join(parts))

    # ---- 设定 ----
    def _build_settings(self):
        spec = [(k, v, 'text' if k in ('characterName', 'location') else 'long', None) for k, v in STORY_FIELDS.items()]
        spec += [('autoAdvanceEnabled', '不聊天时，继续推进角色生活', 'bool', None),
                 ('allowProactiveMessages', '允许角色主动给白名单好友发消息', 'bool', None),
                 ('autoAdvanceIntervalMinutes', '生活推进间隔（分钟）', 'int', (5, 1440))]
        self.settings = SettingsForm(self.api, '/api/story', spec,
            '设定角色是谁、生活在哪里，以及你们的故事从哪里开始。保存时会应用设置并重启幕间引擎；'
            '已有聊天记忆会保留，不会重新开局。正在处理消息时请等待。', True)
        self.tabs.addTab(self.settings, '设定')

    # ---- 剧情记录 ----
    def _build_timeline(self):
        self.timeline_page = QWidget()
        layout = QVBoxLayout(self.timeline_page)
        row = QHBoxLayout()
        self.date_from = QDateTimeEdit(QDateTime.currentDateTime().addDays(-7))
        self.date_to = QDateTimeEdit(QDateTime.currentDateTime())
        for edit in (self.date_from, self.date_to):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat('yyyy-MM-dd HH:mm')
        self.track = QComboBox()
        self.track.addItem('全部记录', '')
        for value, name in [('messages', '聊天消息'), ('script', '角色生活'), ('system', '系统与管理'),
                            ('alter', '情绪变化'), ('compaction', '记忆压缩')]:
            self.track.addItem(name, value)
        row.addWidget(self.date_from)
        row.addWidget(QLabel('至'))
        row.addWidget(self.date_to)
        row.addWidget(QLabel('查看内容'))
        row.addWidget(self.track)
        self.query_button = button('查询', self.query_timeline, True)
        row.addWidget(self.query_button)
        row.addStretch(1)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(button('最近 7 天（截至现在）', self.recent_timeline))
        row.addWidget(button(ACTIONS['note'], lambda: self.open_action('note')))
        self.more = button('读取更早记录', lambda: self.query_timeline(more=True))
        self.more.setEnabled(False)
        row.addWidget(self.more)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(hint('先在目录里选一条，再查看完整内容；发送状态以平台回执为准。搜索仅作用于已加载记录。'))
        self.timeline = RecordPane()
        layout.addWidget(self.timeline, 1)
        self.tabs.addTab(self.timeline_page, '剧情记录')

    # ---- 数据与日志 ----
    def _build_tools(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(hint('导出文件可能包含聊天、人设与好友信息，请妥善保管。清理操作需要输入“确认”，系统会先备份。'))
        row = QHBoxLayout()
        row.addWidget(button('导出剧情数据', self.export))
        row.addWidget(button('读取幕间日志', self.load_logs))
        row.addStretch(1)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.tools_actions = QComboBox()
        for action in ('rebase', 'purge-range', 'purge-platform', 'reset', 'clear-database'):
            self.tools_actions.addItem(ACTIONS[action], action)
        row.addWidget(self.tools_actions)
        row.addWidget(button('执行数据维护', lambda: self.open_action(self.tools_actions.currentData())))
        row.addStretch(1)
        layout.addLayout(row)
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        layout.addWidget(self.logs, 1)
        self.tabs.addTab(page, '数据与日志')

    def tab_changed(self, index):
        widget = self.tabs.widget(index)
        if isinstance(widget, SettingsForm):
            widget.ensure_loaded()
        elif widget is self.advanced:
            if self.advanced.config is None:
                self.advanced.load()
        elif widget is self.timeline_page:
            if self.timeline_query is None:
                self.recent_timeline()
        elif index in (0, 3, 4):
            self.reload_page()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.data:
            self.reload_page()

    def reload_page(self, checked=False):
        self.feedback.setText('正在读取角色近况…')
        self.api.run('story-overview', lambda: self.api.get('/api/hdsi/overview'), self.receive,
                     lambda exc: self.feedback.setText(f'剧情读取失败，请启动幕间引擎后重试。已有内容已保留。\n{exc}'))

    def receive(self, data):
        self.data = data
        queue = data.get('queue') or {}
        self._render_overview(data)
        self.memory.receive(data)
        self.schedule.receive(data)
        self.feedback.setText(f'已读取角色近况 · 待发送 {queue.get("pending", 0)} 条 · '
                              f'发送结果待核实 {queue.get("unknown", 0)} 条')

    # ---- 剧情记录查询 ----
    def recent_timeline(self):
        self.date_to.setDateTime(QDateTime.currentDateTime())
        self.date_from.setDateTime(QDateTime.currentDateTime().addDays(-7))
        self.query_timeline()

    def query_timeline(self, checked=False, more=False):
        if not self.query_button.isEnabled():
            return
        if more:
            if not self.cursor or not self.timeline_query:
                return
            query = {**self.timeline_query, 'cursor': self.cursor}
        else:
            start, end = self.date_from.dateTime(), self.date_to.dateTime()
            if start > end or start.secsTo(end) > 14 * 86400:
                self.feedback.setText('请选择有效时间范围，每次最多查询 14 天。')
                return
            query = {'from': start.toUTC().toString(Qt.ISODateWithMs),
                     'to': end.toUTC().toString(Qt.ISODateWithMs), 'limit': 50}
            if self.track.currentData():
                query['tracks'] = [self.track.currentData()]
        self.query_button.setEnabled(False)
        self.more.setEnabled(False)
        self.feedback.setText('正在查询剧情记录…')

        def done(data):
            records = {self.timeline.identity(e): e for e in self.timeline_entries} if more else {}
            for record in data.get('entries', []):
                records[self.timeline.identity(record)] = record
            self.timeline_entries = sorted(records.values(),
                key=lambda e: (str(e.get('occurredAt', '')), str(e.get('id', ''))), reverse=True)
            self.timeline_query = {k: v for k, v in query.items() if k != 'cursor'}
            self.cursor = data.get('nextCursor')
            self.timeline.receive(self.timeline_entries)
            self.query_button.setEnabled(True)
            self.more.setEnabled(bool(self.cursor))
            self.feedback.setText(f'已加载 {len(self.timeline_entries)} 条剧情记录，最新在前。')

        def failed(exc):
            self.query_button.setEnabled(True)
            self.more.setEnabled(bool(self.cursor))
            self.feedback.setText(f'查询失败，已保留上次结果：{exc}')

        self.api.run('story-timeline', lambda: self.api.post('/api/hdsi/timeline', query), done, failed)

    # ---- 操作对话框 ----
    def open_action(self, action, record=None):
        if self.action_busy:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(ACTIONS[action])
        dialog.resize(520, 350)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        layout.addLayout(form)
        fields = {}
        args = {}
        help_text = '操作将提交给幕间引擎，完成后刷新近况。'
        if action == 'advance':
            help_text = '会调用模型推进生活剧情；允许主动联系时，可能向白名单好友发送消息。'
        if action in ('compact', 'overlay-compact', 'schedule-refresh'):
            help_text = '此操作可能调用模型，耗时一两分钟；提交后请等待，不要重复操作。'
        tip = QLabel(help_text)
        tip.setObjectName('Muted')
        tip.setWordWrap(True)
        layout.insertWidget(0, tip)
        if action in ('fact-add', 'fact-edit', 'note'):
            edit = QPlainTextEdit()
            edit.setPlainText((record or {}).get('content', ''))
            form.addRow('内容', edit)
            fields['content'] = edit
        if action == 'fact-add':
            edit = QComboBox()
            for key in ('character', 'world', 'relationship', 'event', 'promise'):
                edit.addItem(display_value(key, 'scope'), key)
            form.addRow('分类', edit)
            fields['scope'] = edit
        if action == 'overlay-clear':
            edit = QComboBox()
            for key, name in [('character', '角色'), ('perspective', '视角'), ('relationship', '关系'),
                              ('world', '世界'), ('all', '全部演化层')]:
                edit.addItem(name, key)
            form.addRow('清除范围', edit)
            fields['target'] = edit
        if action == 'purge-range':
            for key, source in [('from', self.date_from), ('to', self.date_to)]:
                edit = QDateTimeEdit(source.dateTime())
                edit.setCalendarPopup(True)
                edit.setDisplayFormat('yyyy-MM-dd HH:mm')
                form.addRow('起始时间' if key == 'from' else '结束时间', edit)
                fields[key] = edit
        if action == 'purge-platform':
            args['platform'] = 'douyin'
        if record and record.get('id') is not None:
            args['id'] = record['id']
        if action in DESTRUCTIVE:
            note = QLabel('此操作会改变已有记录，系统将先备份。请输入“确认”继续。')
            note.setWordWrap(True)
            form.addRow(note)
            edit = QLineEdit()
            form.addRow('确认操作', edit)
            fields['confirm'] = edit
        feedback = QLabel()
        feedback.setWordWrap(True)
        layout.addWidget(feedback)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText('执行')
        buttons.button(QDialogButtonBox.Cancel).setText('取消')
        layout.addWidget(buttons)
        operation_id = uuid.uuid4().hex

        def submit():
            for key, widget in fields.items():
                args[key] = (widget.toPlainText() if isinstance(widget, QPlainTextEdit)
                             else widget.currentData() if isinstance(widget, QComboBox)
                             else widget.dateTime().toUTC().toString(Qt.ISODateWithMs) if isinstance(widget, QDateTimeEdit)
                             else widget.text())
            if 'content' in args and not 1 <= len(args['content'].strip()) <= 8000:
                feedback.setText('请输入 1 至 8000 字内容。')
                return
            if action in DESTRUCTIVE and args.get('confirm') != '确认':
                feedback.setText('请输入“确认”。')
                return
            if action == 'purge-range' and fields['from'].dateTime() > fields['to'].dateTime():
                feedback.setText('结束时间不能早于起始时间。')
                return
            self.action_busy = True
            buttons.setEnabled(False)
            feedback.setText('处理中，请稍候…')
            for widget in fields.values():
                widget.setEnabled(False)
            payload = {'action': action, 'args': dict(args), 'operationId': operation_id}

            def done(data):
                self.action_busy = False
                dialog.accept()
                self.reload_page()
                if action == 'note' and self.timeline_query:
                    self.query_timeline()

            def failed(exc):
                self.action_busy = False
                feedback.setText(f'操作未确认完成，请先检查结果。{exc}')
                buttons.setEnabled(True)
                buttons.button(QDialogButtonBox.Ok).setText('重试同一次操作')

            self.api.run('story-action', lambda: self.api.post('/api/hdsi/action', payload), done, failed)

        buttons.accepted.connect(submit)
        buttons.rejected.connect(dialog.reject)
        self.action_dialog = dialog
        dialog.open()

    def export(self):
        filename, _ = QFileDialog.getSaveFileName(self, '导出剧情数据', 'douyin-story.json', 'JSON (*.json)')
        if not filename:
            return

        def done(data):
            from pathlib import Path
            try:
                Path(filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                self.feedback.setText('剧情数据已导出，请妥善保管。')
            except OSError as exc:
                self.feedback.setText('导出文件写入失败：' + str(exc))

        self.api.run('story-export', lambda: self.api.get('/api/hdsi/export'), done,
                     lambda exc: self.feedback.setText('导出失败：' + str(exc)))

    def load_logs(self):
        self.api.run('story-logs', lambda: self.api.get('/api/hdsi/logs'),
                     lambda data: self.logs.setPlainText(data.get('text', '')),
                     lambda exc: self.feedback.setText('日志读取失败：' + str(exc)))
