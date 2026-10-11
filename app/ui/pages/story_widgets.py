"""剧情页共用的原生控件。

这些控件把控制面板的版式翻译成 PySide6 原生写法：可折叠分组、自适应高度的富文本
记录体、分区滚动容器，以及统一的标题/说明/按钮工厂。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QToolButton,
    QTextBrowser, QVBoxLayout, QWidget,
)


def button(text, callback=None, primary=False):
    widget = QPushButton(text)
    widget.setProperty('primary', primary)
    if callback is not None:
        widget.clicked.connect(callback)
    return widget


def heading(text):
    label = QLabel(text)
    label.setObjectName('SectionTitle')
    label.setWordWrap(True)
    return label


def subheading(text):
    label = QLabel(text)
    label.setObjectName('SubHeading')
    label.setWordWrap(True)
    return label


def hint(text):
    label = QLabel(text)
    label.setObjectName('Muted')
    label.setWordWrap(True)
    return label


def meta(text):
    label = QLabel(text)
    label.setObjectName('SmallMuted')
    label.setWordWrap(True)
    return label


def button_row(*widgets):
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    for widget in widgets:
        if widget is None:
            continue
        if isinstance(widget, str):
            widget = QLabel(widget)
            widget.setObjectName('Muted')
        layout.addWidget(widget)
    layout.addStretch(1)
    return row


class RichBody(QTextBrowser):
    """只读富文本块，高度随内容自适应，避免在滚动区里出现二次滚动条。

    高度只通过 sizeHint / minimumSizeHint 暴露给布局，并用垂直 Fixed 策略生效。
    不能改用 setFixedHeight：那会把最大高度一并写死，而 QSplitter 会把子控件的最大
    高度累加进自己的最大高度，导致“剧情记录”的目录与正文被压成一条窄缝。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('RecordBody')
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.document().setDocumentMargin(0)
        self._height = 24
        self._queued = False
        self.document().documentLayout().documentSizeChanged.connect(self._schedule)

    def set_content(self, html):
        self.setHtml(html)
        self._measure()

    def _schedule(self):
        """文档自身变化时延迟测量，避免在布局激活过程中改高度。"""
        if self._queued:
            return
        self._queued = True
        QTimer.singleShot(0, self._measure)

    def _measure(self):
        self._queued = False
        measured = max(20, int(self.document().size().height()) + 6)
        if abs(measured - self._height) > 1:
            self._height = measured
            self.updateGeometry()

    def sizeHint(self):
        return QSize(super().sizeHint().width(), self._height)

    def minimumSizeHint(self):
        return QSize(24, self._height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._measure()

    def showEvent(self, event):
        super().showEvent(event)
        self._measure()


class Collapsible(QWidget):
    """可折叠分区；内容首次展开时才构建，避免一次生成过多控件。"""

    def __init__(self, title, builder, expanded=False, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.toggle = QToolButton()
        self.toggle.setObjectName('Disclosure')
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.toggle.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.toggle.clicked.connect(self._toggle)
        layout.addWidget(self.toggle)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(4, 2, 0, 4)
        self.body_layout.setSpacing(10)
        self.body.setVisible(expanded)
        layout.addWidget(self.body)
        self._builder = builder
        self._built = False
        self._overflow = 0

    def _toggle(self):
        expanded = self.toggle.isChecked()
        self.toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.body.setVisible(expanded)
        if expanded and not self._built:
            self._built = True
            self._builder(self.body_layout)

    def set_count(self, count):
        base = self.toggle.text().split('（')[0]
        self.toggle.setText(base if count is None else f'{base}（{count}）')


class SectionPane(QScrollArea):
    """竖向堆叠分区内容的滚动容器，重建时清空旧控件。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.body = QWidget()
        self.column = QVBoxLayout(self.body)
        self.column.setContentsMargins(2, 2, 14, 2)
        self.column.setSpacing(12)
        self.column.addStretch(1)
        self.setWidget(self.body)

    def clear(self):
        while self.column.count() > 1:
            item = self.column.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def add(self, widget):
        self.column.insertWidget(self.column.count() - 1, widget)
        return widget

    def add_layout(self, layout):
        holder = QWidget()
        holder.setLayout(layout)
        return self.add(holder)


def record_card(meta_text, html, actions=()):
    """单条记录卡片：元信息 + 富文本正文 + 行内操作按钮。"""
    card = QFrame()
    card.setFrameShape(QFrame.StyledPanel)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(8)
    if meta_text:
        layout.addWidget(meta(meta_text))
    body = RichBody()
    body.set_content(html)
    layout.addWidget(body)
    action_buttons = [w for w in actions if w is not None]
    if action_buttons:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        for widget in action_buttons:
            row.addWidget(widget)
        row.addStretch(1)
        layout.addLayout(row)
    return card


def plain_empty(text):
    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(2, 6, 2, 6)
    label = hint(text)
    layout.addWidget(label)
    return holder
