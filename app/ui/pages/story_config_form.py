"""完整参数的可视化表单。

控制面板用 /api/hdsi/config 返回的 schema 生成原生控件；桌面版沿用同一份 schema，
把参数渲染成勾选框、数值框、下拉框与文本框，用户不再需要面对 JSON。接口密钥沿用
“已保存 · 留空保留”的哨兵值，保存前仍由幕间系统校验并重启引擎。
"""
from __future__ import annotations

import re
from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from .story_labels import GROUPS, HELP, KINDS, LABELS, VALUES, clean_description
from .story_labels import label as label_of
from .story_widgets import Collapsible, button, hint

HIDDEN_ROOTS = frozenset({'onebot', 'chatActions', 'stickers', 'qzone'})
SECRET_KEYS = frozenset({'apiKey', 'password', 'token', 'secret', 'extraHeaders', 'extraBody'})
SENTINEL = '__KEEP_SECRET__'


def node(schema, ref):
    """解析 schema 引用，兼容 JS 的键类型强制转换。

    控制面板是 JavaScript：对象键一律是字符串，`refs[2183]` 会自动变成
    `refs['2183']`，所以能正常取到节点。Python 不会做这层转换，而
    `/api/hdsi/config` 返回的 schema 里 refs 的键全是字符串、引用值全是数字
    （dict/list/uid/inner 共 500 余处），必须显式兼容，否则每次查表都 KeyError。
    """
    if isinstance(ref, dict):
        return ref
    refs = schema['refs']
    if ref in refs:
        return refs[ref]
    text = str(ref)
    if text in refs:
        return refs[text]
    try:
        numeric = int(text)
    except (TypeError, ValueError):
        raise KeyError(ref) from None
    if numeric in refs:
        return refs[numeric]
    raise KeyError(ref)


def variant(schema, n, value):
    """union：优先挑出与当前值匹配的分支，否则第一个非 const 分支。"""
    options = [node(schema, item) for item in n.get('list', [])]
    for option in options:
        if option.get('type') != 'object':
            continue
        entries = list((option.get('dict') or {}).items())
        if entries and all(node(schema, rid).get('type') != 'const'
                           or (value or {}).get(key) == node(schema, rid).get('value')
                           for key, rid in entries):
            return option
    for option in options:
        if option.get('type') != 'const':
            return option
    return options[0] if options else {}


def object_fields(schema, ref, value):
    n = node(schema, ref)
    kind = n.get('type')
    if kind == 'object':
        return dict(n.get('dict') or {})
    if kind == 'intersect':
        merged = {}
        for part in n.get('list', []):
            merged.update(object_fields(schema, part, value))
        return merged
    if kind == 'union':
        chosen = variant(schema, n, value)
        return object_fields(schema, chosen, value) if chosen else {}
    return {}


def default_value(schema, ref, depth=0):
    n = node(schema, ref)
    if depth > 15:
        return None
    kind = n.get('type')
    meta = n.get('meta') or {}
    if kind == 'object':
        result = {key: default_value(schema, rid, depth + 1) for key, rid in (n.get('dict') or {}).items()}
        result = {key: val for key, val in result.items() if val is not None}
        result.update(deepcopy(meta.get('default') or {}))
        return result
    if kind == 'intersect':
        merged = {}
        for part in n.get('list', []):
            merged.update(default_value(schema, part, depth + 1) or {})
        return merged
    if 'default' in meta:
        return deepcopy(meta['default'])
    if kind == 'const':
        return n.get('value')
    if kind == 'union':
        parts = n.get('list') or []
        return default_value(schema, parts[0], depth + 1) if parts else None
    if kind == 'array':
        return []
    if kind == 'boolean':
        return False
    if kind == 'number':
        return 0
    return ''


def field_title(key, n):
    """标题优先级与控制面板 hTitle 一致。

    分组名只对真正的分组容器（object / intersect）生效；其余字段先查字段词表，
    再查分组词表，最后才用描述首句兜底——否则 provider.model 会错显成“模型中心”。
    """
    kind = n.get('type')
    if kind in ('object', 'intersect') and key in GROUPS:
        return GROUPS[key]
    if key in LABELS:
        return LABELS[key]
    if key in GROUPS:
        return GROUPS[key]
    description = (n.get('meta') or {}).get('description') or ''
    description = re.sub(r'^【[^】]*】\s*', '', description)
    if description:
        sentence = description.split('。')[0].split('：')[0].split('；')[0].split('\n')[0].strip()
        if sentence:
            return sentence[:65]
    return label_of(key)


def douyin_field(path, key):
    """与控制面板一致：隐藏与抖音无关或标记为内部的根字段。"""
    if path and path[0] in HIDDEN_ROOTS:
        return False
    if len(path) > 1 and path[0] == 'model' and (path[1] == 'audio' or key == 'useForStickers'):
        return False
    if len(path) > 1 and path[0] == 'runtime' and path[1] == 'forwardMessage':
        return False
    if path and path[0] == 'sharedStory' and key == 'managerAccounts':
        return False
    return True


def enum_text(key, value, description):
    if key == 'mode' and value == 'active':
        return '积极参与'
    return VALUES.get(value) or KINDS.get(value) or clean_description(description) or str(value)


class ConfigForm(QWidget):
    """schema 驱动的完整参数表单，保留版本校验与未保存提示。"""

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.config = None
        self.schema = None
        self.revision = ''
        self.dirty = False
        self.busy = False
        layout = QVBoxLayout(self)
        layout.addWidget(hint('每个参数都有对应的控件，按分组展开修改即可。接口密钥留空表示保留原值；'
                              '保存前由幕间系统校验，并会重启剧情引擎。'))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.body = QWidget()
        self.column = QVBoxLayout(self.body)
        self.column.setContentsMargins(2, 2, 14, 2)
        self.column.setSpacing(10)
        self.column.addStretch(1)
        scroll.setWidget(self.body)
        layout.addWidget(scroll, 1)
        self.feedback = hint('点击“重新读取”加载完整参数。')
        layout.addWidget(self.feedback)
        row = QHBoxLayout()
        self.save_button = button('保存并生效', self.save, True)
        self.load_button = button('重新读取', self.load)
        row.addWidget(self.save_button)
        row.addWidget(self.load_button)
        row.addStretch(1)
        layout.addLayout(row)
        self.lock()

    # ---- 读写与状态 ----
    def get(self, path):
        current = self.config
        for part in path:
            try:
                current = current[part]
            except (KeyError, IndexError, TypeError):
                return None
        return current

    def set_path(self, path, value):
        current = self.config
        for part in path[:-1]:
            current = current[part]
        current[path[-1]] = value
        self.mark_dirty()

    def mark_dirty(self):
        self.dirty = True
        self.feedback.setText('有修改尚未保存。')
        self.lock()

    def lock(self):
        ready = bool(self.revision) and not self.busy
        self.load_button.setEnabled(not self.busy)
        self.save_button.setEnabled(ready and self.dirty)
        self.body.setEnabled(ready)

    def failed(self, exc):
        self.busy = False
        self.feedback.setText(f'操作失败，修改已保留。请检查服务；若配置已更新，请重新读取后再修改。\n{exc}')
        self.lock()

    # ---- 渲染 ----
    def _clear(self):
        while self.column.count() > 1:
            item = self.column.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _render(self):
        self._clear()
        root = node(self.schema, self.schema['uid'])
        for key, rid in (root.get('dict') or {}).items():
            widget = self._field(rid, [key], key)
            if widget is not None:
                self.column.insertWidget(self.column.count() - 1, widget)
        self.lock()

    def _field(self, ref, path, key):
        if not douyin_field(path, key):
            return None
        n = node(self.schema, ref)
        meta = n.get('meta') or {}
        if meta.get('hidden'):
            return None
        value = self.get(path)
        if isinstance(path[-1], int):
            title = str(key)  # 数组项标题用数据自带的名称，与控制面板一致
        elif key == 'sharedStory':
            title = '抖音好友与隐私'
        else:
            title = field_title(key, n)
        description = clean_description(meta.get('description') or '')
        if description.startswith(title) and len(description) > len(title):
            description = description[len(title):].lstrip('。：:，, ')
        fields = object_fields(self.schema, ref, value)
        if fields:
            def build(layout, fields=fields, path=list(path)):
                if description:
                    layout.addWidget(hint(description))
                for sub_key, sub_ref in fields.items():
                    widget = self._field(sub_ref, path + [sub_key], sub_key)
                    if widget is not None:
                        layout.addWidget(widget)
            return Collapsible(title, build)
        if n.get('type') == 'array':
            return self._array(title, path, n, description)
        if n.get('type') == 'const':
            return None
        return self._leaf(title, path, key, n, value, meta)

    def _array(self, title, path, n, description):
        holder = {}

        def build(layout):
            if description:
                layout.addWidget(hint(description))
            box = QVBoxLayout()
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(8)
            layout.addLayout(box)

            def sync():
                widget = holder.get('widget')
                if widget is not None:
                    widget.set_count(len(self.get(path) or []))

            def add():
                items = deepcopy(self.get(path) or [])
                items.append(default_value(self.schema, n.get('inner')))
                self.set_path(path, items)
                rebuild()
                sync()

            def remove(index):
                items = deepcopy(self.get(path) or [])
                if 0 <= index < len(items):
                    items.pop(index)
                self.set_path(path, items)
                rebuild()
                sync()

            def rebuild():
                while box.count():
                    item = box.takeAt(0)
                    widget = item.widget()
                    if widget is not None:
                        widget.setParent(None)
                        widget.deleteLater()
                for index, entry in enumerate(self.get(path) or []):
                    if isinstance(entry, dict):
                        item_key = entry.get('label') or entry.get('name') or f'第 {index + 1} 项'
                    else:
                        item_key = f'第 {index + 1} 项'
                    editor = self._field(n.get('inner'), list(path) + [index], item_key)
                    row = QWidget()
                    row_layout = QVBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    row_layout.setSpacing(6)
                    if editor is not None:
                        row_layout.addWidget(editor)
                    row_layout.addWidget(button(f'移除第 {index + 1} 项',
                                                lambda _=False, i=index: remove(i)), 0, Qt.AlignLeft)
                    box.addWidget(row)
                box.addWidget(button('添加一项', add), 0, Qt.AlignLeft)

            rebuild()

        widget = Collapsible(title, build)
        holder['widget'] = widget
        widget.set_count(len(self.get(path) or []))
        return widget

    def _leaf(self, title, path, key, n, value, meta):
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        kind = n.get('type')
        constants = [node(self.schema, item) for item in (n.get('list') or [])]
        constants = [c for c in constants if c.get('type') == 'const']
        description = clean_description(HELP.get(key) or meta.get('description') or '')
        field = None
        if kind == 'union' and constants and len(constants) == len(n.get('list') or []):
            column.addWidget(QLabel(title))
            field = QComboBox()
            for const in constants:
                field.addItem(enum_text(key, const.get('value'), (const.get('meta') or {}).get('description')),
                              const.get('value'))
            for index in range(field.count()):
                if field.itemData(index) == value:
                    field.setCurrentIndex(index)
                    break
            field.currentIndexChanged.connect(
                lambda _index, f=field, p=list(path): self.set_path(p, f.currentData()))
        elif kind == 'boolean':
            field = QCheckBox(title)
            field.setChecked(bool(value))
            field.toggled.connect(lambda checked, p=list(path): self.set_path(p, checked))
            column.addWidget(field)
        else:
            secret = meta.get('role') == 'secret' or key in SECRET_KEYS
            stored = value == SENTINEL
            multiline = meta.get('role') == 'textarea' or (isinstance(value, str) and '\n' in (value or ''))
            column.addWidget(QLabel(title))
            if multiline:
                field = QPlainTextEdit()
                field.setMinimumHeight(96)
                field.setPlainText('' if stored or value is None else str(value))
                field.textChanged.connect(
                    lambda f=field, p=list(path): self.set_path(p, f.toPlainText()))
            elif kind == 'number':
                integral = (isinstance(value, int) and not isinstance(value, bool)) or (
                    value is None and isinstance(meta.get('min'), int) and isinstance(meta.get('max'), int))
                if integral:
                    field = QSpinBox()
                    field.setRange(-2 ** 31 + 1, 2 ** 31 - 1)
                    if meta.get('min') is not None:
                        field.setMinimum(int(meta['min']))
                    if meta.get('max') is not None:
                        field.setMaximum(int(meta['max']))
                    field.setValue(int(value) if isinstance(value, int) and not isinstance(value, bool) else 0)
                else:
                    field = QDoubleSpinBox()
                    field.setDecimals(4)
                    field.setRange(-1e12, 1e12)
                    if meta.get('min') is not None:
                        field.setMinimum(float(meta['min']))
                    if meta.get('max') is not None:
                        field.setMaximum(float(meta['max']))
                    field.setValue(float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0)
                field.valueChanged.connect(
                    lambda val, p=list(path), whole=integral: self.set_path(p, int(val) if whole else float(val)))
            else:
                field = QLineEdit()
                if secret:
                    field.setEchoMode(QLineEdit.Password)
                field.setText('' if stored or value is None else str(value))
                if secret:
                    field.setPlaceholderText('已保存 · 留空保留' if stored else '尚未配置')
                field.textChanged.connect(
                    lambda text, p=list(path), sec=secret, was=stored:
                    self.set_path(p, SENTINEL if (sec and not text and was) else text))
        if field is not None:
            column.addWidget(field)
        if description:
            column.addWidget(hint(description))
        return holder

    # ---- 载入与保存 ----
    def load(self, checked=False):
        if self.busy:
            return
        if self.dirty and QMessageBox.question(self, '重新读取', '放弃尚未保存的完整参数修改？') != QMessageBox.Yes:
            return
        self.busy = True
        self.lock()
        self.feedback.setText('正在读取完整参数…')

        def done(data):
            try:
                self.schema = data['schema']
                self.config = deepcopy(data['config'])
                self.revision = data['revision']
                self.dirty = False
                self._render()
            finally:
                # 渲染失败也必须解除忙状态，否则按钮永久禁用、页面停在“正在读取完整参数…”。
                self.busy = False
                self.lock()
            self.feedback.setText(f'已读取 HDSI {data.get("version", "当前版本")} 配置')

        self.api.run('story-config', lambda: self.api.get('/api/hdsi/config'), done, self.failed)

    def save(self):
        if self.busy or not self.dirty or not self.revision:
            return
        body = {'config': deepcopy(self.config), 'revision': self.revision}
        self.busy = True
        self.lock()
        self.feedback.setText('正在校验、保存并重启幕间引擎…')

        def done(data):
            self.revision = data['revision']
            self.dirty = False
            self.busy = False
            self.feedback.setText('已保存并生效。')
            self.lock()

        self.api.run('story-config', lambda: self.api.put('/api/hdsi/config', body), done, self.failed)
