STYLESHEET = """
/* ---- Base: QMainWindow transparan, JANGAN beri background solid ---- */
QMainWindow {
    background: transparent;
    color: #e2e8f0;
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 13px;
}

/* Semua widget mewarisi warna teks & font, TANPA background */
QWidget {
    color: #e2e8f0;
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 13px;
}

/* ---- Root frame: wajah window rounded ---- */
QFrame#rootFrame {
    background-color: #1e293b;
    border: 1px solid #1e293b;
    border-radius: 12px;
}

QFrame#titleBarFrame {
                background-color: rgba(15, 23, 42, 64);
                border: none;
            }

QFrame#mainFrame {
                background-color: rgba(15, 23, 42, 64);
                border: none;
            }            

QLabel#header { font-size: 24px; font-weight: 700; color: #38bdf8; }
QLabel#subtitle { color: #94a3b8; margin-bottom: 6px; }
QLabel#fieldLabel { color: #cbd5e1; font-weight: 600; margin-top: 4px; }
QLabel#statusLabel { font-weight: 600; color: #38bdf8; }
QLabel#detailLabel { color: #94a3b8; font-size: 12px; }

QLineEdit, QTextEdit, QComboBox {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 8px 10px;
    color: #e2e8f0;
    selection-background-color: #0ea5e9;
}
QComboBox QAbstractItemView {
    background-color: #1e293b;
    color: #e2e8f0;
    selection-background-color: #0ea5e9;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid #38bdf8; }

QPushButton {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 8px 16px;
    color: #e2e8f0;
    font-weight: 600;
}
QPushButton:hover { background-color: #273449; border-color: #38bdf8; }
QPushButton:disabled { color: #64748b; background-color: #172033; border-color: #1e293b; }

QProgressBar {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    height: 22px;
    text-align: center;
    color: #e2e8f0;
    font-weight: 600;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #0ea5e9, stop:1 #22d3ee);
    border-radius: 6px;
}
QFrame#progressFrame {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 10px;
}

QCheckBox { color: #cbd5e1; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid #475569; background-color: #1e293b;
}
QCheckBox::indicator:checked { background-color: #0ea5e9; border-color: #0ea5e9; }

/* ---- Sidebar ---- */
QWidget#sidebar {
    background-color: #0b1220;
    border-right: 1px solid #1e293b;
    border-bottom-left-radius: 12px;
}
QLabel#brand { color: #38bdf8; font-size: 20px; font-weight: 700; padding: 12px 8px; }
QPushButton#navBtn {
    text-align: left; padding: 10px 14px; border: 1px solid transparent;
    border-radius: 8px; background-color: transparent; color: #cbd5e1;
}
QPushButton#navBtn:hover { background-color: #1e293b; color: #e2e8f0; }
QPushButton#navBtn:checked {
    background-color: #0ea5e9; color: #0f172a; font-weight: 800;
}

/* ---- Pages area: ikut rounded kanan bawah ---- */
QStackedWidget {
    background-color: transparent;
    border-bottom-right-radius: 12px;
}

/* ---- Custom Title Bar ---- */
QLabel#titleBarText {
    color: #cbd5e1;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
    padding-left: 4px;
}
QLabel#titleBarIcon {
    padding-left: 12px;
    padding-right: 6px;
}

QPushButton#media_play {
    background-color: transparent;
    border: px solid transparent;
    background-image: url(assets/btn_media.svg);
    background-position: center;
    background-repeat: no-repeat;
    border-radius: 8px;
    color: white;
    font-size: 14px;
    font-weight: 500;
    padding: 15px;
    min-width: 100px;
    max-width: 100px;
    min-height: 100px;
    max-height: 100px;
}
QPushButton#media_play:hover {
    background-image: url(assets/btn_mediaHover.svg);
    background-position: center;
    background-repeat: no-repeat;
    background-color: transparent;
    color: black; 
}
QPushButton#media_play:disabled {
    background-image: url(assets/btn_mediaDisbld.svg);
    background-position: center;
    background-repeat: no-repeat;
    background-color: transparent;
    color: black; 
}
QPushButton#media_play:pressed {
    background-image: url(assets/btn_mediaPressed.svg);
    background-position: center;
    background-repeat: no-repeat;
    background-color: transparent;
    color: black; 
}

QPushButton#primaryBtn {
    background-color: transparent;
    border: px solid transparent;
    background-image: url(assets/btn_primary.svg);
    background-position: center;
    background-repeat: no-repeat;
    border-radius: 8px;
    color: white;
    font-size: 14px;
    font-weight: 700;
    padding: 15px;
    min-width: 130px;
    max-width: 130px;
    min-height: 50px;
    max-height: 50px;
}
QPushButton#primaryBtn:hover {
    background-image: url(assets/btn_Hover.svg);
    background-position: center;
    background-repeat: no-repeat;
    background-color: transparent; 
    color: black;
}
QPushButton#primaryBtn:disabled {
    background-image: url(assets/btn_disbld.svg);
    background-position: center;
    background-repeat: no-repeat;
    background-color: transparent;
    color: black; 
}

QPushButton#dangerBtn {
    background-color: transparent;
    border: px solid transparent;
    background-image: url(assets/btn_danger.svg);
    background-position: center;
    background-repeat: no-repeat;
    border-radius: 8px;
    color: white;
    font-size: 14px;
    font-weight: 500;
    padding: 15px;
    min-width: 130px;
    max-width: 130px;
    min-height: 50px;
    max-height: 50px;
}
QPushButton#dangerBtn:hover {
    background-image: url(assets/btn_Hover.svg);
    background-position: center;
    background-repeat: no-repeat;
    background-color: transparent;
    color: black; 
}
QPushButton#dangerBtn:disabled {
    background-image: url(assets/btn_disbld.svg);
    background-position: center;
    background-repeat: no-repeat;
    background-color: transparent;
    color: black; 
}

QPushButton#gnrlBtn {
    background-color: transparent;
    border: transparent;
    background-image: url(assets/btn_gnrl.svg);
    background-position: center;
    background-repeat: no-repeat;
    border-radius: 8px;
    color: white;
    font-size: 14px;
    font-weight: 500;
    padding: 15px;
    min-width: 130px;
    max-width: 130px;
    min-height: 40px;
    max-height: 40px;
}
QPushButton#gnrlBtn:hover {
    background-image: url(assets/btn_Hover.svg);
    background-position: center;
    background-repeat: no-repeat;
    background-color: transparent;
    color: black; 
}
QPushButton#gnrlBtn:disabled {
    background-image: url(assets/btn_disbld.svg);
    background-position: center;
    background-repeat: no-repeat;
    background-color: transparent;
    color: black; 
}

QPushButton#cleanLogBtn {
    background-color: transparent;
    border: px solid transparent;
    background-image: url(assets/btn_cleanLogBtn.svg);
    background-position: center;
    background-repeat: no-repeat;
    border-radius: 8px;
    color: white;
    font-size: 14px;
    font-weight: 500;;
    font-size: 14px;;
    font-size: 14px;
    font-weight: 700;
    padding: 15px;
    min-width: 130px;
    max-width: 130px;
    min-height: 50px;
    max-height: 50px;
}
QPushButton#cleanLogBtn:hover {
    background-image: url(assets/btn_Hover.svg);
    background-position: center;
    background-repeat: no-repeat;
    background-color: transparent;
    color: black; 
}
QPushButton#cleanLogBtn:disabled {
    background-image: url(assets/btn_disbld.svg);
    background-position: center;
    background-repeat: no-repeat;
    background-color: transparent;
    color: black; 
}

QPushButton#titleBarCloseBtn {
    background-color: #ff0000;
    border: none;
    border-radius: 12px;
    color: #ffffff;
    font-size: 14px;
    font-weight: 700;
    padding: 0px;
    margin-right: 5px;
    min-width: 26px;
    max-width: 26px;
    min-height: 26px;
    max-height: 26px;
}

QPushButton#titleBarCloseBtn:hover { background-color: #ff0000; color: #ffff00; }
QPushButton#titleBarCloseBtn:pressed { background-color: #273449; }

QPushButton#winBtn {
    background-color: transparent;
    border: none;
    border-radius: 0px;
    color: #cbd5e1;
    font-size: 14px;
    font-weight: 700;
    padding: 0;
    min-width: 46px;
    max-width: 46px;
    min-height: 36px;
    max-height: 36px;
}
QPushButton#winBtn:hover { background-color: #1e293b; color: #e2e8f0; }
QPushButton#winBtn:pressed { background-color: #273449; }

QPushButton#closeBtn {
    background-color: transparent;
    border: none;
    border-radius: 0px;
    color: #cbd5e1;
    font-size: 14px;
    font-weight: 700;
    padding: 0;
    min-width: 46px;
    max-width: 46px;
    min-height: 36px;
    max-height: 36px;
}
QPushButton#closeBtn:hover { background-color: #ef4444; color: #ffffff; }
QPushButton#closeBtn:pressed { background-color: #b91c1c; }
/* ---- Scroll area: viewport & isinya transparan ---- */
QScrollArea {
    background: transparent;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
QScrollArea > QWidget > QScrollBar {
    background: #0b1220;
}

/* ---- Group box: sesuaikan dengan tema gelap ---- */
QGroupBox {
    background-color: #0b1220;
    border: 1px solid #1e293b;
    border-radius: 10px;
    margin-top: 12px;
    padding: 12px 10px 10px 10px;
    font-weight: 700;
    color: #cbd5e1;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: #38bdf8;
    background-color: #0f172a;
}

/* ---- Widget pembungkus di dalam page ---- */
QWidget#settingsPage {
    background: transparent;
}
"""
