"""Locally authored line icons for the native workspace."""
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import theme

PATHS = {
    'status': '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="m6 12 3-1 2 5 3-9 2 5h2"/>',
    'user': '<circle cx="12" cy="7" r="4"/><path d="M4 21v-3a8 8 0 0 1 16 0v3Z"/>',
    'chat': '<path d="M21 12a8 8 0 0 1-8 8H9l-5 3v-6a8 8 0 0 1-1-5 9 9 0 0 1 18 0Z"/><path d="M7 11h.01M12 11h.01M17 11h.01"/>',
    'friends': '<circle cx="9" cy="7" r="3"/><path d="M2 21v-3a7 7 0 0 1 14 0v3ZM16 4a3 3 0 0 1 0 6m3 4a6 6 0 0 1 3 5v2"/>',
    'story': '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    'logs': '<path d="M6 3h9l4 4v14H6Z M15 3v5h4M9 12h7M9 16h7"/>',
    'image': '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 7"/>',
    'reset': '<path d="M3 10a9 9 0 1 1 1 7M3 4v6h6"/>',
    'panel': '<rect x="3" y="3" width="18" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>',
    'engine': '<path d="m12 3 9 5-9 5-9-5Zm-9 9 9 5 9-5m-18 5 9 5 9-5"/>',
    'bot': '<rect x="3" y="7" width="18" height="14" rx="4"/><path d="M12 3v4M7 13h.01M17 13h.01M8 17h8"/><circle cx="12" cy="2" r="1"/>',
    'upload': '<path d="M12 16V3m-5 5 5-5 5 5M3 16v5h18v-5"/>',
    'paste': '<rect x="5" y="4" width="15" height="18" rx="2"/><rect x="9" y="2" width="7" height="4" rx="1"/><path d="M3 7v12"/>',
    'shield': '<path d="m12 2 9 4v7c0 5-9 9-9 9s-9-4-9-9V6Z M7 12l3 3 7-7"/>',
    'play': '<path d="m8 4 12 8-12 8Z"/>',
    'stop': '<rect x="5" y="5" width="14" height="14" rx="1"/>',
    'brand': '<path d="M13 3v12a5 5 0 1 1-5-5M17 4c0 4 2 6 5 7"/>',
    'sun': '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    'moon': '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z"/>',
}


def icon(name, color=None, size=24):
    """绘制图标；颜色缺省时取当前主题的常规图标色。"""
    tint_normal = theme.color('icon') if color is None else color
    result = QIcon()
    for mode, tint in ((QIcon.Normal, tint_normal),
                       (QIcon.Selected, theme.color('accent_text')),
                       (QIcon.Disabled, theme.color('icon_disabled'))):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
               f'fill="none" stroke="{tint}" stroke-width="1.6" '
               f'stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>')
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        QSvgRenderer(QByteArray(svg.encode())).render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(2)
        result.addPixmap(pixmap, mode)
    return result


def themed_icon(widget, name, token='icon', size=24):
    """给控件设置图标，并登记主题切换后重绘（QIcon 位图在创建时就已烘焙）。"""
    def draw():
        widget.setIcon(icon(name, theme.color(token), size))

    theme.bind(widget, draw)
    draw()
    return widget


def themed_pixmap(widget, name, token='icon', size=24):
    """给 QLabel 设置图标位图，并登记主题切换后重绘。"""
    def draw():
        widget.setPixmap(icon(name, theme.color(token), size).pixmap(size, size))

    theme.bind(widget, draw)
    draw()
    return widget
