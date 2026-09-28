from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("YGO Combo Navigator")
    app.setFont(QFont("Microsoft YaHei UI", 9))

    project_root = Path(__file__).resolve().parents[1]
    window = MainWindow(project_root=project_root)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

