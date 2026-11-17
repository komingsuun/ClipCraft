import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    # Set global font (opsional)
    app.setStyle("Fusion")

    window = MainWindow()

    # ==== Frameless + translucent ====
    window.setWindowFlags(Qt.WindowType.FramelessWindowHint)
    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()