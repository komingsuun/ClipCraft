from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import QPixmap, QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget, QSizeGrip, QFrame, QSizePolicy,
)

from core.common import STYLESHEET
from ui.widgets.custom_title_bar import CustomTitleBar
from ui.pages.compression_page import CompressionPage
from ui.pages.cutter_page import CutterPage
from ui.pages.downloader_page import DownloaderPage
from ui.pages.settings_page import SettingsPage
from core.config import load_config


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("ClipCraft")
        self.resize(960, 700)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(STYLESHEET)

        # ==== Main Frame: pembungkus utama ====
        self.main_frame = QFrame()
        self.main_frame.setObjectName("rootFrame")
        self.main_frame.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground, True
        )
        self.setCentralWidget(self.main_frame)

        main_layout = QVBoxLayout(self.main_frame)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ==== Root Frame: wajah window ====
        self.root_frame = QFrame()
        self.root_frame.setObjectName("rootFrame")

        main_layout.addWidget(self.root_frame)

        root_layout = QVBoxLayout(self.root_frame)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ==== Custom Title Bar ====
        self.title_bar = CustomTitleBar(self, "ClipCraft")
        root_layout.addWidget(self.title_bar)

        # ==== Body (sidebar + pages) ====
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(5, 0, 0, 5)
        body_layout.setSpacing(0)

        root_layout.addWidget(body, stretch=1)

        # ==== Sidebar ====
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)

        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 16, 12, 16)
        side_layout.setSpacing(6)

        brand = QLabel()
        brand.setObjectName("brand")

        pixmap = QPixmap("./assets/clip_craft.png")
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                150, 50,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            brand.setPixmap(pixmap)

        brand.setScaledContents(False)
        brand.setAutoFillBackground(False)

        side_layout.addWidget(brand)

        self.btn_downloader = self._nav_button("Downloader")
        self.btn_compression = self._nav_button("Video Compression")
        self.btn_cutter = self._nav_button("Video Cutter")
        self.btn_settings = self._nav_button("Settings")

        for b in (
            self.btn_downloader,
            self.btn_compression,
            self.btn_cutter,
            self.btn_settings
        ):
            side_layout.addWidget(b)

        side_layout.addStretch()
        side_layout.addWidget(
            QLabel("v1.3.0 — ClipCraft", objectName="detailLabel")
        )

        body_layout.addWidget(sidebar)

        # ==== Pages ====
        self.pages = QStackedWidget()

        self.page_downloader = DownloaderPage()
        self.page_compression = CompressionPage()
        self.page_cutter = CutterPage()
        self.page_settings = SettingsPage()

        for p in (
            self.page_downloader,
            self.page_compression,
            self.page_cutter,
            self.page_settings
        ):
            self.pages.addWidget(p)

        body_layout.addWidget(self.pages, stretch=1)

        # ==== Resize grip ====
        self.size_grip = QSizeGrip(self.root_frame)

        # ==== Navigation ====
        self.btn_downloader.clicked.connect(
            lambda: self._go(0, self.btn_downloader)
        )
        self.btn_compression.clicked.connect(
            lambda: self._go(1, self.btn_compression)
        )
        self.btn_cutter.clicked.connect(
            lambda: self._go(2, self.btn_cutter)
        )
        self.btn_settings.clicked.connect(
            lambda: self._go(3, self.btn_settings)
        )

        self._go(0, self.btn_downloader)


    def _center_on_screen(self):
        screen = (
            QGuiApplication.screenAt(self.pos())
            or QGuiApplication.primaryScreen()
        )
        if screen is None:
            return

        geo = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(geo.center())
        self.move(frame.topLeft())

    def showEvent(self, event):
        super().showEvent(event)

        if not getattr(self, "_centered", False):
            self._centered = True
            QTimer.singleShot(0, self._center_on_screen)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if hasattr(self, "size_grip"):
            QTimer.singleShot(0, self._position_size_grip)

    def _position_size_grip(self):
        if not hasattr(self, "size_grip"):
            return

        self.size_grip.adjustSize()

        self.size_grip.move(
            self.root_frame.rect().bottomRight()
            - QPoint(self.size_grip.width(), self.size_grip.height())
            + QPoint(1, 1)
        )

        self.size_grip.raise_()

    @staticmethod
    def _nav_button(text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("navBtn")
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _go(self, index: int, btn: QPushButton):
        for b in (
            self.btn_downloader,
            self.btn_compression,
            self.btn_cutter,
            self.btn_settings
        ):
            b.setChecked(b is btn)

        self.pages.setCurrentIndex(index)

    def closeEvent(self, event):
        active = []

        if self.page_downloader.has_active_worker():
            active.append("Downloader")

        if self.page_compression.has_active_worker():
            active.append("Video Compression")

        if self.page_cutter.has_active_worker():
            active.append("Video Cutter")

        if active and load_config()["ui"]["confirm_on_exit"]:
            reply = QMessageBox.question(
                self,
                "Konfirmasi",
                f"Proses masih berjalan ({', '.join(active)}). "
                "Batalkan dan keluar?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.page_downloader.request_cancel()
                self.page_compression.request_cancel()
                self.page_cutter.request_cancel()
                event.accept()
            else:
                event.ignore()
        else:
            if active:
                self.page_downloader.request_cancel()
                self.page_compression.request_cancel()
                self.page_cutter.request_cancel()

            event.accept()