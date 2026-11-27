from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QFrame, QHBoxLayout, QLabel, QPushButton

class CustomTitleBar(QWidget):
    """Title bar kustom dengan QFrame sebagai background container."""

    HEIGHT = 40

    def __init__(self, window: "MainWindow", title: str = "ClipCraft", only_close: bool = False):
        super().__init__(window)

        self._window = window
        self.setFixedHeight(self.HEIGHT)

        # Frame pembungkus seluruh UI
        self.frame = QFrame(self)
        self.frame.setObjectName("titleBarFrame")

        # Layout utama widget
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.frame)

        # Layout isi frame
        inner = QHBoxLayout(self.frame)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)

        # Icon
        icon = QLabel()
        icon.setObjectName("titleBarIcon")
        icon.setStyleSheet("QLabel { background-color: transparent; }")

        pixmap = QPixmap("./assets/clip_craft_square.png")
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                22, 22,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            icon.setPixmap(pixmap)

        icon.setFixedSize(40, self.HEIGHT)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner.addWidget(icon)

        # Title
        self.title_label = QLabel(title)
        self.title_label.setObjectName("titleBarText")
        self.title_label.setStyleSheet("QLabel { background-color: transparent; }")
        inner.addWidget(self.title_label)

        inner.addStretch()

        # Window controls
        if not only_close:
            self.btn_min = self._win_button("—", "winBtn")
            self.btn_max = self._win_button("□", "winBtn")
            self.btn_close = self._win_button("✕", "titleBarCloseBtn")

            inner.addWidget(self.btn_min)
            inner.addWidget(self.btn_max)
            inner.addWidget(self.btn_close)

            # Signals
            self.btn_min.clicked.connect(self._window.showMinimized)
            self.btn_max.clicked.connect(self._toggle_max)
            self.btn_close.clicked.connect(self._window.close)
        else:
            self.btn_close = self._win_button("✕", "titleBarCloseBtn")
            inner.addWidget(self.btn_close)
            # Signals
            self.btn_close.clicked.connect(self._window.close)

        self._window.windowStateChanged = self._on_state_changed

    @staticmethod
    def _win_button(text: str, obj_name: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(obj_name)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setFixedSize(36, 30)
        return btn

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.frame.setGeometry(self.rect())

    def _toggle_max(self):
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def _on_state_changed(self, _state):
        if self._window.isMaximized():
            self.btn_max.setText("❐")
            self.btn_max.setToolTip("Restore")
        else:
            self.btn_max.setText("□")
            self.btn_max.setToolTip("Maximize")

    # Drag window
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            window_handle = self._window.windowHandle()
            if window_handle is not None:
                window_handle.startSystemMove()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_max()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)