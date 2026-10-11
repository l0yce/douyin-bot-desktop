"""Compact service row: name, honest status and one relevant action."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from .. import theme
from ..icons import themed_pixmap

# 状态 -> (文案, 主题令牌)。存令牌名，换主题后取到的就是新配色。
STATE_TEXT = {
    'active': ('运行中', 'ok'),
    'activating': ('启动中…', 'warn'),
    'inactive': ('已停止', 'idle'),
    'failed': ('启动失败', 'bad'),
    'unknown': ('未知', 'idle'),
}


def state_text(state):
    """取状态的文案与色值；色值每次现取，避免留下上一套主题的颜色。"""
    name, token = STATE_TEXT.get(state) or STATE_TEXT['unknown']
    return name, theme.color(token)


class ServiceCard(QFrame):
    startClicked = Signal()
    stopClicked = Signal()

    def __init__(self, title, subtitle, parent=None, *, service='panel'):
        super().__init__(parent)
        self.setObjectName('ServiceRow')
        self._state = 'unknown'
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 12)
        lay.setSpacing(10)
        symbol = QLabel()
        symbol.setObjectName('ServiceIcon')
        symbol.setAlignment(Qt.AlignCenter)
        symbol.setFixedSize(46, 46)
        themed_pixmap(symbol, {'panel': 'panel', 'interlude': 'engine', 'bot': 'bot'}[service],
                      'accent_text', 24)
        lay.addWidget(symbol)
        names = QVBoxLayout()
        names.setSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setObjectName('ServiceTitle')
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName('Muted')
        self.subtitle_label.setWordWrap(True)
        self.detail_label = QLabel('正在读取状态')
        self.detail_label.setObjectName('SmallMuted')
        self.detail_label.setWordWrap(True)
        names.addWidget(self.title_label)
        names.addWidget(self.subtitle_label)
        names.addWidget(self.detail_label)
        lay.addLayout(names, 1)
        self.state_label = QLabel('未知')
        self.state_label.setObjectName('ServiceState')
        self.state_label.setMinimumWidth(62)
        self.state_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.state_label)
        self.btn_start = QPushButton('启动')
        self.btn_start.setProperty('primary', True)
        self.btn_stop = QPushButton('停止')
        for button in (self.btn_start, self.btn_stop):
            button.setFixedWidth(76)
            button.setAccessibleName(f'{button.text()}{title}')
            lay.addWidget(button)
        self.btn_start.clicked.connect(self.startClicked)
        self.btn_stop.clicked.connect(self.stopClicked)
        # 状态色是设进控件的内联样式，样式表管不到，换主题时要重设一遍。
        theme.bind(self, self._refresh_state_style)
        self.update_state('unknown')

    def update_state(self, state, detail=''):
        self._state = state
        text, color = state_text(state)
        self.state_label.setText(text)
        self.state_label.setStyleSheet(f'color:{color}; background:transparent;')
        self.detail_label.setText(detail or '暂无运行信息')
        running = state in ('active', 'activating')
        self.btn_start.setVisible(not running)
        self.btn_stop.setVisible(running)
        self.btn_start.setEnabled(state in ('inactive', 'failed'))
        self.btn_stop.setEnabled(running)

    def _refresh_state_style(self):
        text, color = state_text(self._state)
        self.state_label.setText(text)
        self.state_label.setStyleSheet(f'color:{color}; background:transparent;')

