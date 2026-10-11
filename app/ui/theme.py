"""Approved A composition: midnight plum surfaces with restrained warm gold.

配色由令牌驱动：`DARK` / `LIGHT` 两张表 + 一份 QSS 模板。任何一处颜色都必须走
`color('token')`，不要在页面里写死十六进制值，否则换主题时会漏掉。

深色是默认值，`stylesheet('dark')` 与引入双主题之前的样式表逐字节一致
（见 tests/theme_smoke.py）。
"""
from __future__ import annotations

import re

from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import QWidget

from ..settings import settings

ASSETS = (Path(__file__).resolve().parent / 'assets').as_posix()

# ---------------------------------------------------------------- 配色令牌

DARK = {
    'base': '#1a171e',
    'workspace': '#1a171e',
    'sidebar': 'rgba(24,20,28,245)',
    'sidebar_line': '#3e3541',
    'text': '#f1ebef',
    'text_strong': '#ffffff',
    'text_soft': '#eee4ef',
    'muted': '#c5bac8',
    'faint': '#bfb3c2',
    'hint': '#a99fb0',
    'key': '#b7bdcc',
    'disabled': '#9a9fac',
    'disabled_soft': '#a297aa',
    'accent': '#e8bf82',
    'accent_hover': '#f2ce98',
    'accent_press': '#cfaa72',
    'accent_text': '#edc788',
    'accent_ink': '#241c17',
    'accent_line': '#806849',
    'accent_line_hi': '#b79768',
    'accent_deep': '#80652f',
    'selection': '#3e332e',
    'selection_text': '#f3d7ae',
    'chip': '#302735',
    'chip_text': '#c5bac8',
    'row': '#29222f',
    'row_on': '#30282d',
    'row_hover': '#382d40',
    'plate': '#241e28',
    'avatar': '#3a3043',
    'avatar_on': '#574334',
    'field': '#211c27',
    'field_off': '#232733',
    'spin_off': '#202430',
    'card': 'rgba(36,30,40,240)',
    'pane': 'rgba(32,27,38,225)',
    'line': '#473b49',
    'line_soft': '#403643',
    'line_strong': '#64566a',
    'line_input': '#8e98ad',
    'button': '#302a36',
    'button_hover': '#403445',
    'button_press': '#4c3d4e',
    'button_off': '#29242f',
    'button_off_line': '#443b4c',
    'tab': '#2b2432',
    'tab_hover': '#483a50',
    'menu': '#2b2432',
    'icon_bg': '#40342e',
    'table_head': '#302735',
    'table_head_text': '#e1d7e5',
    'handle': '#483a50',
    'scroll': '#796b83',
    'tooltip': '#382d40',
    'tooltip_line': '#796b83',
    'tooltip_text': '#ffffff',
    'ok': '#a7d9b0',
    'warn': '#edc788',
    'bad': '#f3a8a8',
    'idle': '#beb4c2',
    'preview': '#cbb8e8',
    'preview_text': '#d0c5d2',
    'icon': '#c8bec8',
    'icon_disabled': '#77707b',
}

LIGHT = {
    'base': '#eff1f5',
    'workspace': '#eff1f5',
    'sidebar': 'rgba(246,247,250,250)',
    'sidebar_line': '#dcdfe6',
    'text': '#1f2430',
    'text_strong': '#000000',
    'text_soft': '#2b3140',
    'muted': '#5b6373',
    'faint': '#6b7383',
    'hint': '#7b8393',
    'key': '#4d5566',
    'disabled': '#9aa1ad',
    'disabled_soft': '#8f96a3',
    'accent': '#e8bf82',
    'accent_hover': '#f0cb95',
    'accent_press': '#d9ad6b',
    'accent_text': '#9a6a10',
    'accent_ink': '#241c17',
    'accent_line': '#d8b071',
    'accent_line_hi': '#c29433',
    'accent_deep': '#a97f22',
    'selection': '#fbeed7',
    'selection_text': '#8a5c0c',
    'chip': '#eaedf2',
    'chip_text': '#5b6373',
    'row': '#ffffff',
    'row_on': '#fffaf0',
    'row_hover': '#f4f6f9',
    'plate': '#f5f7fa',
    'avatar': '#ece2d6',
    'avatar_on': '#f6e8cd',
    'field': '#f7f8fb',
    'field_off': '#eef0f4',
    'spin_off': '#e6e9ef',
    'card': 'rgba(255,255,255,250)',
    'pane': 'rgba(251,252,254,240)',
    'line': '#dcdfe6',
    'line_soft': '#e8ebf0',
    'line_strong': '#c6ccd6',
    'line_input': '#b9c0cd',
    'button': '#f7f8fb',
    'button_hover': '#eef0f4',
    'button_press': '#e4e7ed',
    'button_off': '#f2f3f6',
    'button_off_line': '#e2e5ec',
    'tab': '#eff1f5',
    'tab_hover': '#e6e9ef',
    'menu': '#ffffff',
    'icon_bg': '#f7f1e6',
    'table_head': '#f0f2f6',
    'table_head_text': '#3c4353',
    'handle': '#dfe3ea',
    'scroll': '#c6ccd6',
    'tooltip': '#2b3140',
    'tooltip_line': '#5b6373',
    'tooltip_text': '#ffffff',
    'ok': '#1f7a45',
    'warn': '#9a6a10',
    'bad': '#c0364a',
    'idle': '#6b7383',
    'preview': '#6b4fa8',
    'preview_text': '#454c5c',
    'icon': '#5b6373',
    'icon_disabled': '#a9b0bd',
}

PALETTES = {'dark': DARK, 'light': LIGHT}
LABELS = {'dark': '深色模式', 'light': '浅色模式'}

_MODE = 'dark'


# ---------------------------------------------------------------- 样式模板

_TEMPLATE = '''
QWidget { color:{text}; font-family:"Microsoft YaHei UI","Segoe UI"; font-size:13px; }
QMainWindow,QDialog { background:{base}; }
QWidget#Workspace,QWidget#PageBody,QWidget#PageHeader { background:transparent; }
QWidget#Sidebar { background:{sidebar}; border-right:1px solid {sidebar_line}; }
QLabel { background:transparent; }
QLabel#Brand { color:{text}; font-size:19px; font-weight:600; padding:8px 0; }
QLabel#PageTitle { font-size:32px; font-weight:700; color:{text}; }
QLabel#PageSubtitle { color:{muted}; font-size:13px; }
QLabel#SidebarNote { color:{faint}; font-size:12px; padding:0 0 0 4px; }
QLabel#Muted { color:{muted}; font-size:12px; }
QLabel#SmallMuted { color:{faint}; font-size:11px; }
QLabel#SectionTitle { font-size:18px; font-weight:600; color:{text}; }
QLabel#ServiceTitle { font-size:15px; font-weight:600; }
QLabel#ServiceState,QLabel#CheckState { font-size:12px; font-weight:600; }
QLabel#WhitelistSummary { color:{accent_text}; font-size:18px; font-weight:600; }
QLabel#HealthState { font-size:13px; font-weight:600; }
QLabel#FriendAvatar { background:{avatar}; color:{accent_text}; font-size:18px; font-weight:600; border-radius:13px; }
QLabel#ScopeSummary { color:{accent_text}; font-size:17px; font-weight:600; }
QLabel#GuideTitle { color:{text_soft}; font-size:13px; font-weight:600; }
QLabel#EmptyNote { color:{faint}; font-size:13px; padding:20px 8px; }
QLabel#StateBadge { background:{chip}; color:{chip_text}; font-size:11px; border-radius:6px; padding:6px 8px; }
QFrame#FriendRow { background:{row}; border:1px solid {line}; border-radius:10px; }
QFrame#FriendRow[enabledFriend="true"] { background:{row_on}; border-color:{accent_line}; }
QFrame#FriendRow:hover { border-color:{accent_line_hi}; }
QFrame#SocialDivider { background:{line}; border:0; }
QListWidget#ActivityList { background:transparent; border:0; border-radius:0; padding:0; }
QListWidget#ActivityList::item { padding:0; border:0; margin:0; }
QTextBrowser#MessageReader { background:transparent; border:0; padding:0; border-radius:0; }
QFrame#Surface,QFrame#HealthStrip { background:{card}; border:1px solid {line}; border-radius:12px; }
QFrame#ServiceRow { background:transparent; border:0; border-top:1px solid {line_soft}; border-radius:0; }
QLabel#ServiceIcon { background:{icon_bg}; border-radius:23px; }
QListWidget#Navigation { background:transparent; border:0; outline:0; }
QListWidget#Navigation::item { padding:8px 12px; margin:4px 0; border:1px solid transparent; border-radius:8px; color:{muted}; }
QListWidget#Navigation::item:hover { background:{chip}; color:{text_strong}; }
QListWidget#Navigation::item:selected { background:{selection}; color:{accent_text}; border-color:{accent_line}; }
QPushButton { background:{button}; border:1px solid {line_strong}; border-radius:7px; padding:8px 12px; min-height:20px; }
QPushButton:hover { background:{button_hover}; border-color:{accent_line_hi}; }
QPushButton:pressed { background:{button_press}; }
QPushButton:focus { border-color:{accent_text}; }
QPushButton[primary="true"] { background:{accent}; border-color:{accent}; color:{accent_ink}; font-weight:600; }
QPushButton[primary="true"]:hover { background:{accent_hover}; }
QPushButton[primary="true"]:pressed { background:{accent_press}; }
QPushButton[quiet="true"] { background:transparent; border-color:transparent; color:{muted}; }
QPushButton[quiet="true"]:hover { background:{chip}; border-color:{line_strong}; color:{text}; }
QPushButton[quiet="true"]:focus { border-color:{accent_text}; }
QPushButton:disabled { color:{disabled_soft}; background:{button_off}; border-color:{button_off_line}; }
QLineEdit,QPlainTextEdit,QTextEdit,QTextBrowser,QAbstractSpinBox,QComboBox {
 background:{field}; color:{text}; border:1px solid {line_strong}; border-radius:7px;
 padding:8px; selection-background-color:{accent}; selection-color:{accent_ink};
}
QLineEdit:focus,QPlainTextEdit:focus,QTextEdit:focus,QAbstractSpinBox:focus,QComboBox:focus { border-color:{accent}; }
QLineEdit:disabled,QAbstractSpinBox:disabled,QPlainTextEdit:disabled { color:{disabled}; background:{field_off}; }
QComboBox QAbstractItemView { background:{menu}; color:{text}; selection-background-color:{selection}; selection-color:{accent_text}; padding:5px; }
QCheckBox { spacing:8px; padding:5px 0; }
QCheckBox::indicator { width:16px; height:16px; border:1px solid {line_input}; border-radius:4px; background:{field}; }
QCheckBox::indicator:checked { background:{accent}; border:3px solid {accent_deep}; }
QCheckBox::indicator:checked { image:url("{assets}/check.svg"); }
QCheckBox::indicator:focus { border-color:{accent_text}; }
QAbstractSpinBox { padding-right:28px; }
QAbstractSpinBox::up-button { subcontrol-origin:border; subcontrol-position:top right; width:24px; background:{handle}; border-top-right-radius:5px; }
QAbstractSpinBox::down-button { subcontrol-origin:border; subcontrol-position:bottom right; width:24px; background:{handle}; border-bottom-right-radius:5px; }
QAbstractSpinBox::up-arrow { image:url("{assets}/up.svg"); width:12px; height:8px; }
QAbstractSpinBox::down-arrow { image:url("{assets}/down.svg"); width:12px; height:8px; }
QAbstractSpinBox::up-button:disabled,QAbstractSpinBox::down-button:disabled { background:{spin_off}; }
QCheckBox:disabled { color:{disabled}; }
QTabWidget::pane { border:0; background:{pane}; }
QTabBar::tab { background:{tab}; color:{muted}; padding:10px 12px; margin:0 3px 7px 0; border-radius:5px; }
QTabBar::tab:selected { color:{accent_text}; background:{selection}; }
QTabBar::tab:hover { background:{tab_hover}; }
QTabBar QToolButton { background:{chip}; color:{accent_text}; border:1px solid {line_strong}; border-radius:4px; padding:3px; }
QTabBar QToolButton:hover { background:{tab_hover}; }
QTabBar QToolButton::left-arrow { image:url("{assets}/left.svg"); width:10px; height:12px; }
QTabBar QToolButton::right-arrow { image:url("{assets}/right.svg"); width:10px; height:12px; }
QScrollArea { border:0; background:transparent; }
QScrollArea>QWidget>QWidget { background:transparent; }
QListWidget,QTreeWidget,QTableWidget { background:{field}; alternate-background-color:{tab}; border:1px solid {line}; border-radius:7px; outline:0; }
QListWidget::item { padding:12px 10px; border-bottom:1px solid {line_soft}; }
QTreeWidget::item,QTableWidget::item { padding:7px; }
QListWidget::item:selected,QTreeWidget::item:selected,QTableWidget::item:selected { background:{selection}; color:{selection_text}; }
QListWidget::item:hover,QTreeWidget::item:hover { background:{row_hover}; }
QHeaderView::section { background:{table_head}; color:{table_head_text}; border:0; border-bottom:1px solid {line_strong}; padding:9px; }
QSplitter::handle { background:{handle}; width:1px; height:1px; margin:5px; }
QFrame[frameShape="6"] { background:{card}; border:1px solid {line}; border-radius:12px; padding:8px; }
/* 多行文本编辑器与只读文本视图同样是 StyledPanel 的 QFrame，会一并命中上面的卡片规则。
   它们属于输入控件，必须回到字段外观（与 QLineEdit / QAbstractSpinBox 完全一致），
   否则同一张表单里多行框的底色、边框与圆角都和别人不一样。 */
QPlainTextEdit[frameShape="6"],QTextEdit[frameShape="6"],QTextBrowser[frameShape="6"] {
 background:{field}; border:1px solid {line_strong}; border-radius:7px; padding:8px;
}
QPlainTextEdit[frameShape="6"]:focus,QTextEdit[frameShape="6"]:focus { border-color:{accent}; }
QPlainTextEdit[frameShape="6"]:disabled,QTextEdit[frameShape="6"]:disabled { color:{disabled}; background:{field_off}; }
QScrollBar:vertical { background:transparent; width:10px; margin:2px; }
QScrollBar::handle:vertical { background:{scroll}; border-radius:4px; min-height:28px; }
QScrollBar:horizontal { background:transparent; height:10px; margin:2px; }
QScrollBar::handle:horizontal { background:{scroll}; border-radius:4px; min-width:28px; }
QScrollBar::add-line,QScrollBar::sub-line { width:0; height:0; }
QScrollBar::add-page,QScrollBar::sub-page { background:transparent; }
QToolTip { background:{tooltip}; color:{tooltip_text}; border:1px solid {tooltip_line}; padding:6px; }
QMenu { background:{menu}; color:{text}; border:1px solid {line_strong}; }
QMenu::item:selected { background:{selection}; }
QLabel#SubHeading { font-size:15px; font-weight:600; color:{text}; padding:2px 0; }
QTextBrowser#RecordBody { background:transparent; border:0; padding:0; }
QToolButton#Disclosure { background:transparent; border:0; color:{accent_text}; font-size:15px; font-weight:600; padding:6px 2px; }
QToolButton#Disclosure:hover { color:{accent_hover}; }
QToolButton#Disclosure:focus { border:0; }
'''

_TOKEN = re.compile(r'\{([a-z_]+)\}')


def stylesheet(mode: str = 'dark') -> str:
    """按配色令牌生成样式表；未知令牌立即报错，避免静默漏色。"""
    tokens = dict(PALETTES.get(mode, DARK))
    tokens['assets'] = ASSETS

    def swap(match):
        name = match.group(1)
        if name not in tokens:
            raise KeyError(f'未知主题令牌: {{{name}}}')
        return tokens[name]

    return _TOKEN.sub(swap, _TEMPLATE)


STYLE = stylesheet('dark')   # 深色为默认；保留常量名以兼容既有引用


# ---------------------------------------------------------------- 运行时

class _Signals(QObject):
    """主题切换广播：页面据此重绘自绘行与富文本。"""
    changed = Signal(str)


signals = _Signals()


def current_mode() -> str:
    return _MODE


def color(name: str) -> str:
    """取当前主题的令牌值（页面里的颜色都必须走这里）。"""
    return PALETTES[_MODE][name]


def labels() -> dict:
    return dict(LABELS)


def _palette_for(app, mode: str) -> None:
    tokens = PALETTES[mode]
    palette = app.palette()
    palette.setColor(QPalette.Window, QColor(tokens['base']))
    palette.setColor(QPalette.WindowText, QColor(tokens['text']))
    palette.setColor(QPalette.Base, QColor(tokens['field']))
    palette.setColor(QPalette.AlternateBase, QColor(tokens['tab']))
    palette.setColor(QPalette.Text, QColor(tokens['text']))
    palette.setColor(QPalette.Button, QColor(tokens['button']))
    palette.setColor(QPalette.ButtonText, QColor(tokens['text']))
    palette.setColor(QPalette.Highlight, QColor(tokens['accent']))
    palette.setColor(QPalette.HighlightedText, QColor(tokens['accent_ink']))
    palette.setColor(QPalette.PlaceholderText, QColor(tokens['muted']))
    palette.setColor(QPalette.ToolTipBase, QColor(tokens['tooltip']))
    palette.setColor(QPalette.ToolTipText, QColor(tokens['tooltip_text']))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(tokens['disabled']))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(tokens['disabled']))
    app.setPalette(palette)


def apply(app, mode: str | None = None) -> str:
    """套用主题：更新样式表与调色板，并广播给页面重绘。"""
    global _MODE
    mode = mode if mode in PALETTES else saved_mode()
    _MODE = mode
    app.setStyleSheet(stylesheet(mode))
    _palette_for(app, mode)
    signals.changed.emit(mode)
    return mode


def saved_mode() -> str:
    """上次选择的配色；与其它用户偏好存在一起。"""
    mode = settings().value('theme', 'dark')
    return mode if mode in PALETTES else 'dark'


def save_mode(mode: str) -> None:
    store = settings()
    store.setValue('theme', mode)
    store.sync()


def toggle_mode() -> str:
    return 'light' if _MODE == 'dark' else 'dark'


def readable_placeholders(root) -> None:
    """让占位符文字在两种主题下都可读。"""
    shade = QColor(color('muted'))
    for widget in [root, *root.findChildren(QWidget)]:
        palette = widget.palette()
        palette.setColor(QPalette.PlaceholderText, shade)
        widget.setPalette(palette)


def bind(widget, rebuild) -> None:
    """登记「换主题时要重跑」的回调。

    样式表管不到的东西——图标位图、内联颜色、拼好的富文本——都必须在切换时重建，
    否则会留下上一套配色的痕迹。回调挂在控件上，`refresh_widgets()` 统一触发。
    """
    callbacks = getattr(widget, '_theme_rebuilds', None)
    if callbacks is None:
        callbacks = []
        widget._theme_rebuilds = callbacks
    callbacks.append(rebuild)


def refresh_widgets(root) -> None:
    """遍历控件树，重跑所有登记过的主题回调。"""
    for widget in [root, *root.findChildren(QWidget)]:
        for rebuild in getattr(widget, '_theme_rebuilds', ()) or ():
            rebuild()


class Workspace(QWidget):
    """页面底板：填充当前主题的工作区底色，并广播主题变化。"""

    def __init__(self):
        super().__init__()
        self.setObjectName('Workspace')
        signals.changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _mode):
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(color('workspace')))
