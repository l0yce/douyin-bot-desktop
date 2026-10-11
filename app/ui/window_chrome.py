"""Theme-aware window chrome with Qt's native move and resize operations."""
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton

from . import theme
from .icons import themed_pixmap


class CaptionButton(QPushButton):
    def __init__(self, action, label, parent=None):
        super().__init__(parent)
        self.action = action
        self.setAccessibleName(label)
        self.setToolTip(label)
        self.setFixedSize(46, 40)
        self.setCursor(Qt.ArrowCursor)
        self.setFocusPolicy(Qt.StrongFocus)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.underMouse() or self.hasFocus():
            painter.fillRect(self.rect(), QColor(theme.color('button_press' if self.isDown() else 'button_hover')))
        tint = theme.color('bad' if self.action == 'close' and self.underMouse() else 'text')
        painter.setPen(QPen(QColor(tint), 1.3))
        x, y = self.width() // 2, self.height() // 2
        if self.action == 'minimize':
            painter.drawLine(x - 5, y, x + 5, y)
        elif self.action == 'close':
            painter.drawLine(x - 5, y - 5, x + 5, y + 5)
            painter.drawLine(x + 5, y - 5, x - 5, y + 5)
        elif self.window().isMaximized():
            painter.drawRect(x - 3, y - 6, 8, 8)
            painter.fillRect(x - 6, y - 3, 9, 9, QColor(theme.color('base')))
            painter.drawRect(x - 6, y - 3, 8, 8)
        else:
            painter.drawRect(x - 5, y - 5, 10, 10)


class TitleBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.setFixedHeight(40)
        self.setCursor(Qt.ArrowCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 0, 0)
        row.setSpacing(9)
        self.mark = QLabel()
        self.mark.setAttribute(Qt.WA_TransparentForMouseEvents)
        themed_pixmap(self.mark, 'brand', 'accent_text', 18)
        row.addWidget(self.mark)
        self.label = QLabel(window.windowTitle())
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents)
        row.addWidget(self.label)
        row.addStretch(1)
        self.minimize = CaptionButton('minimize', '最小化', self)
        self.maximize = CaptionButton('maximize', '最大化', self)
        self.close_button = CaptionButton('close', '关闭到托盘', self)
        for button in (self.minimize, self.maximize, self.close_button):
            row.addWidget(button)
        self.minimize.clicked.connect(window.showMinimized)
        self.maximize.clicked.connect(self.toggle_maximized)
        self.close_button.clicked.connect(window.close)
        window.windowTitleChanged.connect(self.label.setText)
        theme.bind(self, self.refresh)
        self.refresh()

    def refresh(self):
        self.label.setStyleSheet(f"color: {theme.color('muted')}; font-size: 12px; font-weight: 500;")
        self.update()
        for button in (self.minimize, self.maximize, self.close_button):
            button.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme.color('base')))
        painter.setPen(QColor(theme.color('sidebar_line')))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

    def toggle_maximized(self):
        window = self.window()
        window.showNormal() if window.isMaximized() else window.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_maximized()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)


class WindowChrome(QObject):
    """Keep resize borders usable without drawing the OS's white caption."""
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.resizing_cursor = False

    def edges_at(self, point):
        window = self.window
        edges = Qt.Edges()
        if window.isMaximized() or window.isFullScreen():
            return edges
        margin = 5
        if point.x() < margin:
            edges |= Qt.LeftEdge
        elif point.x() >= window.width() - margin:
            edges |= Qt.RightEdge
        if point.y() < margin:
            edges |= Qt.TopEdge
        elif point.y() >= window.height() - margin:
            edges |= Qt.BottomEdge
        return edges

    def eventFilter(self, watched, event):
        window = self.window
        if watched is window and event.type() == QEvent.WindowStateChange:
            restored = not window.isMaximized()
            window.title_bar.maximize.setToolTip('最大化' if restored else '还原')
            window.title_bar.maximize.setAccessibleName('最大化' if restored else '还原')
            window.title_bar.maximize.update()
        if not isinstance(watched, QWidget) or watched.window() is not window:
            return False
        if event.type() in (QEvent.MouseMove, QEvent.MouseButtonPress):
            point = window.mapFromGlobal(event.globalPosition().toPoint())
            edges = self.edges_at(point)
            if event.type() == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton and edges and window.windowHandle():
                    return window.windowHandle().startSystemResize(edges)
            elif edges:
                horizontal = bool(edges & (Qt.LeftEdge | Qt.RightEdge))
                vertical = bool(edges & (Qt.TopEdge | Qt.BottomEdge))
                if horizontal and vertical:
                    same = bool(edges & Qt.LeftEdge) == bool(edges & Qt.TopEdge)
                    cursor = Qt.SizeFDiagCursor if same else Qt.SizeBDiagCursor
                else:
                    cursor = Qt.SizeHorCursor if horizontal else Qt.SizeVerCursor
                window.setCursor(cursor)
                self.resizing_cursor = True
            elif self.resizing_cursor:
                window.unsetCursor()
                self.resizing_cursor = False
        return False
