"""One application identity for Windows shell, windows and notification area."""
from PySide6.QtGui import QIcon
from ..core import paths


def application_icon():
    return QIcon(str(paths.app_root() / "app/ui/assets/app-icon.ico"))
