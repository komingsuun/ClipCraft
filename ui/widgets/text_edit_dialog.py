from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .text_item import TextItem


class TextEditDialog(QDialog):
    def __init__(self, item: TextItem, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Teks")
        self.setModal(True)
        self.resize(380, 400)

        self._item = item.copy()
        self._color = QColor(item.color)
        self._bg_color = QColor(item.bg_color)
        self._deleted = False

        self._edit_text = QLineEdit(self._item.text)
        self._edit_text.setPlaceholderText("Isi teks...")

        self._spin_size = QSpinBox()
        self._spin_size.setRange(8, 200)
        self._spin_size.setValue(self._item.font_size)

        self._btn_color = QPushButton()
        self._btn_color.setFixedHeight(30)
        self._btn_color.clicked.connect(self._pick_color)
        self._refresh_color_button()

        self._slider_x, self._label_x, row_x = self._make_ratio_row(
            int(self._item.x_ratio * 100)
        )
        self._slider_y, self._label_y, row_y = self._make_ratio_row(
            int(self._item.y_ratio * 100)
        )
        self._slider_x.valueChanged.connect(
            lambda v: self._label_x.setText(f"{v}%")
        )
        self._slider_y.valueChanged.connect(
            lambda v: self._label_y.setText(f"{v}%")
        )

        self._chk_bg = QCheckBox("Aktifkan background")
        self._chk_bg.setChecked(self._item.bg_enabled)
        self._chk_bg.toggled.connect(self._on_bg_toggled)

        self._btn_bg_color = QPushButton()
        self._btn_bg_color.setFixedHeight(30)
        self._btn_bg_color.clicked.connect(self._pick_bg_color)
        self._refresh_bg_color_button()

        self._slider_bg_op, self._label_bg_op, row_bg_op = self._make_ratio_row(
            int(self._item.bg_opacity * 100)
        )
        self._slider_bg_op.valueChanged.connect(
            lambda v: self._label_bg_op.setText(f"{v}%")
        )

        form = QFormLayout()
        form.addRow("Teks:", self._edit_text)
        form.addRow("Ukuran font:", self._spin_size)
        form.addRow("Warna teks:", self._btn_color)
        form.addRow("Posisi X:", row_x)
        form.addRow("Posisi Y:", row_y)
        form.addRow("", self._chk_bg)
        form.addRow("Warna background:", self._btn_bg_color)
        form.addRow("Opasitas background:", row_bg_op)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        btn_delete = QPushButton("Hapus Teks")
        btn_delete.setObjectName("dangerBtn")
        btn_delete.clicked.connect(self._on_delete_clicked)

        bottom = QHBoxLayout()
        bottom.addWidget(btn_delete)
        bottom.addStretch(1)
        bottom.addWidget(buttons)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(bottom)

        self._on_bg_toggled(self._item.bg_enabled)

    # ---------- internal ----------
    def _make_ratio_row(self, value: int):
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(max(0, min(100, value)))
        label = QLabel(f"{slider.value()}%")
        label.setFixedWidth(40)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(slider, 1)
        h.addWidget(label)
        return slider, label, row

    def _pick_color(self):
        c = QColorDialog.getColor(self._color, self, "Pilih Warna Teks")
        if c.isValid():
            self._color = c
            self._refresh_color_button()

    def _refresh_color_button(self):
        self._btn_color.setText(self._color.name().upper())
        self._btn_color.setStyleSheet(
            f"background-color: {self._color.name()};"
            f"color: {'#000' if self._color.lightness() > 128 else '#fff'};"
            "border: 1px solid #334155; border-radius: 4px;"
        )

    def _pick_bg_color(self):
        c = QColorDialog.getColor(
            self._bg_color, self, "Pilih Warna Background"
        )
        if c.isValid():
            self._bg_color = c
            self._refresh_bg_color_button()

    def _refresh_bg_color_button(self):
        self._btn_bg_color.setText(self._bg_color.name().upper())
        self._btn_bg_color.setStyleSheet(
            f"background-color: {self._bg_color.name()};"
            f"color: {'#000' if self._bg_color.lightness() > 128 else '#fff'};"
            "border: 2px solid #334155; border-radius: 4px;"
        )

    def _on_bg_toggled(self, enabled: bool):
        self._btn_bg_color.setEnabled(enabled)
        self._slider_bg_op.setEnabled(enabled)
        self._label_bg_op.setEnabled(enabled)

    def _on_delete_clicked(self):
        self._deleted = True
        self.accept()

    # ---------- public ----------
    def was_deleted(self) -> bool:
        return self._deleted

    def result_item(self) -> TextItem:
        return self._item.copy(
            text=self._edit_text.text(),
            font_size=self._spin_size.value(),
            color=self._color.name().upper(),
            x_ratio=self._slider_x.value() / 100.0,
            y_ratio=self._slider_y.value() / 100.0,
            bg_enabled=self._chk_bg.isChecked(),
            bg_color=self._bg_color.name().upper(),
            bg_opacity=self._slider_bg_op.value() / 100.0,
        )