"""Render the authored SVG to PNGs and a Windows multi-image ICO (no extra deps)."""
import os
from pathlib import Path
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QColor, QFont, QFontDatabase
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app/ui/assets"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render(size):
    svg = (ASSETS / "app-icon.svg").read_bytes()
    if size <= 24:
        # Optical correction: retain open counters with a stronger small-size stem.
        svg = svg.replace(b'stroke-width="2.8"', b'stroke-width="3.2"')
    renderer = QSvgRenderer(QByteArray(svg))
    canvas = QImage(size, size, QImage.Format_ARGB32)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    return canvas


def png_bytes(image):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    assert image.save(buffer, "PNG")
    return bytes(data)


def build():
    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    frames = [(size, png_bytes(render(size))) for size in SIZES]
    offset = 6 + 16 * len(frames)
    directory = []
    for size, data in frames:
        directory.append(struct.pack("<BBBBHHII", size if size < 256 else 0,
            size if size < 256 else 0, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    (ASSETS / "app-icon.ico").write_bytes(struct.pack("<HHH", 0, 1, len(frames)) +
        b"".join(directory) + b"".join(data for _, data in frames))
    exports = ASSETS / "app-icon-png"
    exports.mkdir(exist_ok=True)
    for size, data in frames:
        (exports / f"{size}.png").write_bytes(data)
    render(512).save(str(exports / "512.png"))
    # Real pixel sizes against both common Windows surface colours.
    sheet = QImage(1100, 560, QImage.Format_ARGB32)
    sheet.fill(QColor("#f1f2f5"))
    painter = QPainter(sheet)
    painter.setFont(QFont("Microsoft YaHei", 12))
    for row, background, ink in ((0, "#f1f2f5", "#241c2b"), (1, "#17151b", "#f1ebef")):
        y = row * 280
        painter.fillRect(0, y, 1100, 280, QColor(background))
        painter.setPen(QColor(ink))
        painter.drawText(32, y + 36, "LIGHT SURFACE" if row == 0 else "DARK SURFACE")
        x = 32
        for size in (16, 20, 24, 32, 48, 64, 128):
            painter.drawImage(x, y + 70, render(size))
            painter.drawText(x, y + 230, f"{size}px")
            x += max(90, size + 36)
        painter.drawImage(QRectF(820, y + 42, 200, 200), render(512))
    painter.end()
    preview = ROOT / ".impeccable/review/app-icon-preview.png"
    preview.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(str(preview))
    print(f"Created ICO with {len(frames)} sizes; preview: {preview}")


if __name__ == "__main__":
    build()
