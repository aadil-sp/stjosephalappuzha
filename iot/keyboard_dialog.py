"""
On-Screen Touch Keyboard Dialog for 3.5" (480x320) TFT LCD
Engineered for finger/stylus touch input.
Features QWERTY letters, Numbers/Symbols (123) layout, Shift toggle,
Space, Backspace, Clear, and Done callbacks.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QWidget, QFrame
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class OnScreenKeyboardDialog(QDialog):
    def __init__(self, parent=None, prompt: str = "Enter Text:", default_text: str = "", is_password: bool = False):
        super().__init__(parent)
        self.setWindowTitle("On-Screen Touch Keyboard")
        self.setFixedSize(476, 310)
        self.setModal(True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)

        self.prompt = prompt
        self.is_password = is_password
        self.is_shift = False
        self.is_symbols = False
        self.result_text = default_text

        self.setStyleSheet("""
            QDialog {
                background-color: #0b1120;
                border: 2px solid #0284c7;
                border-radius: 12px;
            }
            QLabel {
                color: #38bdf8;
                font-weight: bold;
                font-size: 11px;
            }
            QLineEdit {
                background-color: #1e293b;
                color: #ffffff;
                border: 1.5px solid #334155;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1.5px solid #334155;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:pressed {
                background-color: #0284c7;
                border-color: #38bdf8;
                color: #ffffff;
            }
            QPushButton#BtnSpecial {
                background-color: #0f172a;
                color: #94a3b8;
                border: 1px solid #334155;
                font-size: 10px;
            }
            QPushButton#BtnDone {
                background-color: #059669;
                color: #ffffff;
                border: 1.5px solid #10b981;
                font-size: 12px;
                font-weight: bold;
            }
        """)

        self.init_ui(default_text)

    def init_ui(self, default_text):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Header: Prompt and Close (Cancel)
        top_row = QHBoxLayout()
        self.lbl_prompt = QLabel(self.prompt)
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(26, 26)
        btn_close.setObjectName("BtnSpecial")
        btn_close.clicked.connect(self.reject)
        top_row.addWidget(self.lbl_prompt)
        top_row.addStretch()
        top_row.addWidget(btn_close)
        layout.addLayout(top_row)

        # Input Row
        input_row = QHBoxLayout()
        self.txt_input = QLineEdit(default_text)
        if self.is_password:
            self.txt_input.setEchoMode(QLineEdit.Password)

        self.btn_toggle_echo = QPushButton("👁")
        self.btn_toggle_echo.setFixedSize(32, 28)
        self.btn_toggle_echo.setObjectName("BtnSpecial")
        self.btn_toggle_echo.clicked.connect(self.toggle_echo)

        self.btn_clear = QPushButton("⌫ Clear")
        self.btn_clear.setFixedHeight(28)
        self.btn_clear.setObjectName("BtnSpecial")
        self.btn_clear.clicked.connect(self.txt_input.clear)

        input_row.addWidget(self.txt_input, stretch=1)
        input_row.addWidget(self.btn_toggle_echo)
        input_row.addWidget(self.btn_clear)
        layout.addLayout(input_row)

        # Keyboard Container
        self.kb_container = QWidget()
        self.kb_layout = QVBoxLayout(self.kb_container)
        self.kb_layout.setContentsMargins(0, 2, 0, 0)
        self.kb_layout.setSpacing(3)
        layout.addWidget(self.kb_container)

        self.build_keys()

    def toggle_echo(self):
        if self.txt_input.echoMode() == QLineEdit.Password:
            self.txt_input.setEchoMode(QLineEdit.Normal)
        else:
            self.txt_input.setEchoMode(QLineEdit.Password)

    def build_keys(self):
        # Clear existing keys
        while self.kb_layout.count():
            item = self.kb_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if self.is_symbols:
            # Layout 123 / Symbols
            row1 = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]
            row2 = ["@", "#", "$", "%", "&", "*", "-", "+", "(", ")"]
            row3 = ["!", "\"", "'", ":", ";", "/", "?", "_", ",", "."]
        else:
            # Layout Letters QWERTY
            row1 = ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"]
            row2 = ["a", "s", "d", "f", "g", "h", "j", "k", "l"]
            row3 = ["z", "x", "c", "v", "b", "n", "m"]

            if self.is_shift:
                row1 = [k.upper() for k in row1]
                row2 = [k.upper() for k in row2]
                row3 = [k.upper() for k in row3]

        # Row 1
        r1_box = QHBoxLayout()
        r1_box.setSpacing(3)
        for char in row1:
            btn = QPushButton(char)
            btn.setFixedHeight(36)
            btn.clicked.connect(lambda _, c=char: self.insert_char(c))
            r1_box.addWidget(btn)
        self.kb_layout.addLayout(r1_box)

        # Row 2
        r2_box = QHBoxLayout()
        r2_box.setSpacing(3)
        for char in row2:
            btn = QPushButton(char)
            btn.setFixedHeight(36)
            btn.clicked.connect(lambda _, c=char: self.insert_char(c))
            r2_box.addWidget(btn)
        self.kb_layout.addLayout(r2_box)

        # Row 3 (with Shift / Backspace)
        r3_box = QHBoxLayout()
        r3_box.setSpacing(3)

        if not self.is_symbols:
            btn_shift = QPushButton("⇧" if not self.is_shift else "⬆")
            btn_shift.setFixedSize(48, 36)
            btn_shift.setObjectName("BtnSpecial")
            btn_shift.clicked.connect(self.toggle_shift)
            r3_box.addWidget(btn_shift)

        for char in row3:
            btn = QPushButton(char)
            btn.setFixedHeight(36)
            btn.clicked.connect(lambda _, c=char: self.insert_char(c))
            r3_box.addWidget(btn)

        btn_backspace = QPushButton("⌫")
        btn_backspace.setFixedSize(48, 36)
        btn_backspace.setObjectName("BtnSpecial")
        btn_backspace.clicked.connect(self.backspace)
        r3_box.addWidget(btn_backspace)
        self.kb_layout.addLayout(r3_box)

        # Row 4 (Mode switch, Space, Done)
        r4_box = QHBoxLayout()
        r4_box.setSpacing(4)

        btn_mode = QPushButton("ABC" if self.is_symbols else "123#")
        btn_mode.setFixedSize(58, 36)
        btn_mode.setObjectName("BtnSpecial")
        btn_mode.clicked.connect(self.toggle_symbols)
        r4_box.addWidget(btn_mode)

        btn_space = QPushButton("␣ Space")
        btn_space.setFixedHeight(36)
        btn_space.clicked.connect(lambda: self.insert_char(" "))
        r4_box.addWidget(btn_space, stretch=2)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedSize(65, 36)
        btn_cancel.setObjectName("BtnSpecial")
        btn_cancel.clicked.connect(self.reject)
        r4_box.addWidget(btn_cancel)

        btn_done = QPushButton("✓ Done")
        btn_done.setFixedSize(80, 36)
        btn_done.setObjectName("BtnDone")
        btn_done.clicked.connect(self.finish)
        r4_box.addWidget(btn_done)

        self.kb_layout.addLayout(r4_box)

    def insert_char(self, char: str):
        self.txt_input.insert(char)

    def backspace(self):
        self.txt_input.backspace()

    def toggle_shift(self):
        self.is_shift = not self.is_shift
        self.build_keys()

    def toggle_symbols(self):
        self.is_symbols = not self.is_symbols
        self.build_keys()

    def finish(self):
        self.result_text = self.txt_input.text()
        self.accept()


def get_text_input(parent=None, prompt="Enter Text:", default="", is_password=False) -> str:
    """Convenience helper to show touch keyboard dialog and return entered text."""
    dialog = OnScreenKeyboardDialog(parent=parent, prompt=prompt, default_text=default, is_password=is_password)
    if dialog.exec_() == QDialog.Accepted:
        return dialog.result_text
    return None
