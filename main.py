#!/usr/bin/env python3
"""
KeyCast — Keyboard Overlay
Displays keypresses on screen as a floating, fade-out overlay.
Right-click the tray icon for Settings or to close.
"""

import sys
import json
import multiprocessing
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSpinBox, QDoubleSpinBox, QComboBox,
    QSystemTrayIcon, QMenu, QFontComboBox, QGroupBox, QFormLayout,
    QColorDialog, QSlider,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread, QRectF
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QBrush, QPen, QIcon, QPixmap,
    QAction, QPainterPath, QFontMetrics,
)
from pynput import keyboard as kb


# ══════════════════════════════════════════════════════════════════
#  Config
# ══════════════════════════════════════════════════════════════════

def _config_path() -> Path:
    if getattr(sys, "frozen", False):          # PyInstaller bundle
        return Path(sys.executable).parent / "keycast_config.json"
    return Path(__file__).parent / "keycast_config.json"


DEFAULTS: dict = {
    "font_family": "Segoe UI",
    "font_size":   28,
    "position":    "bottom-right",             # bottom-right|bottom-left|top-right|top-left|custom
    "custom_x":    50,
    "custom_y":    50,
    "fade_time":   2.0,                        # seconds until fully transparent
    "bg_opacity":  85,                         # 0-100 %
    "max_keys":    3,                          # max key-chips shown at once
    "text_color":  "#FFFFFF",
    "bg_color":    "#1A1A1A",
}


def load_config() -> dict:
    p = _config_path()
    if p.exists():
        try:
            with open(p, encoding="utf-8") as f:
                return {**DEFAULTS, **json.load(f)}
        except Exception:
            pass
    return dict(DEFAULTS)


def save_config(cfg: dict) -> None:
    with open(_config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# ══════════════════════════════════════════════════════════════════
#  Key-name helpers
# ══════════════════════════════════════════════════════════════════

def _k(name: str):
    """Return kb.Key.<name> if it exists, else None."""
    return getattr(kb.Key, name, None)


# Build the key-name map safely — only include keys that exist in this pynput version
_RAW_KEY_MAP = {
    "space":        "Space",
    "enter":        "Enter",
    "tab":          "Tab",
    "backspace":    "⌫",
    "delete":       "Delete",
    "esc":          "Esc",
    "escape":       "Esc",          # older pynput alias
    "ctrl_l":       "Ctrl",
    "ctrl_r":       "Ctrl",
    "ctrl":         "Ctrl",
    "shift_l":      "Shift",
    "shift_r":      "Shift",
    "shift":        "Shift",
    "alt_l":        "Alt",
    "alt_r":        "AltGr",
    "alt_gr":       "AltGr",
    "alt":          "Alt",
    "cmd_l":        "Win",
    "cmd_r":        "Win",
    "cmd":          "Win",
    "caps_lock":    "Caps Lock",
    "num_lock":     "Num Lock",
    "scroll_lock":  "Scroll Lock",
    "print_screen": "Print Screen",
    "pause":        "Pause",
    "menu":         "Menu",
    "f1":  "F1",  "f2":  "F2",  "f3":  "F3",  "f4":  "F4",
    "f5":  "F5",  "f6":  "F6",  "f7":  "F7",  "f8":  "F8",
    "f9":  "F9",  "f10": "F10", "f11": "F11", "f12": "F12",
    "home":      "Home",
    "end":       "End",
    "page_up":   "Page Up",
    "page_down": "Page Down",
    "insert":    "Insert",
    "up":    "↑",
    "down":  "↓",
    "left":  "←",
    "right": "→",
}
_KEY_MAP = {_k(n): label for n, label in _RAW_KEY_MAP.items() if _k(n) is not None}

_MOD_NAMES = (
    "ctrl", "ctrl_l", "ctrl_r",
    "shift", "shift_l", "shift_r",
    "alt", "alt_l", "alt_r", "alt_gr",
    "cmd", "cmd_l", "cmd_r",
)
_MODS = frozenset(k for name in _MOD_NAMES if (k := _k(name)) is not None)


def _key_name(key) -> str:
    if key in _KEY_MAP:
        return _KEY_MAP[key]
    if hasattr(key, "char") and key.char:
        c = key.char
        return c.upper() if c.isalpha() else c
    return str(key).replace("Key.", "").capitalize()


# ══════════════════════════════════════════════════════════════════
#  Keyboard listener  (background QThread)
# ══════════════════════════════════════════════════════════════════

class _Sig(QObject):
    fired = pyqtSignal(str)


# Modifier groups — computed once at module level (walrus not allowed in class body)
_CTRL_KEYS  = frozenset(filter(None, [_k("ctrl"),  _k("ctrl_l"),  _k("ctrl_r")]))
_ALT_KEYS   = frozenset(filter(None, [_k("alt"),   _k("alt_l"),   _k("alt_r"),  _k("alt_gr")]))
_SHIFT_KEYS = frozenset(filter(None, [_k("shift"), _k("shift_l"), _k("shift_r")]))
_WIN_KEYS   = frozenset(filter(None, [_k("cmd"),   _k("cmd_l"),   _k("cmd_r")]))


class KeyboardListener(QThread):
    def __init__(self):
        super().__init__()
        self.sig = _Sig()
        self._held: set = set()
        self._raw_listener = None

    def _mod_parts(self) -> list:
        out = []
        if self._held & _CTRL_KEYS:  out.append("Ctrl")
        if self._held & _ALT_KEYS:   out.append("Alt")
        if self._held & _SHIFT_KEYS: out.append("Shift")
        if self._held & _WIN_KEYS:   out.append("Win")
        return out

    def _on_press(self, key):
        if key in _MODS:
            self._held.add(key)
            return                             # emit only when a regular key fires
        parts = self._mod_parts()
        parts.append(_key_name(key))
        self.sig.fired.emit("  +  ".join(parts))

    def _on_release(self, key):
        self._held.discard(key)

    def run(self):
        with kb.Listener(on_press=self._on_press, on_release=self._on_release) as lst:
            self._raw_listener = lst
            lst.join()

    def stop(self):
        if self._raw_listener:
            self._raw_listener.stop()
        self.quit()


# ══════════════════════════════════════════════════════════════════
#  Overlay window
# ══════════════════════════════════════════════════════════════════

_MARGIN   = 20
_GAP      = 6
_CORNER_R = 10
_PAD_X    = 18
_PAD_Y    = 8


class OverlayWindow(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        self._cfg     = cfg
        self._entries = []                     # list of [text, opacity_float]

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)                  # 20 fps — smooth fade

        self._reposition()
        self.show()
        self._remove_dwm_border()

    def _remove_dwm_border(self):
        """Tell DWM not to draw any border/shadow around this window (Windows 11)."""
        try:
            import ctypes
            hwnd = int(self.winId())
            # DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_DONOTROUND = 1
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
            )
            # DWMWA_NCRENDERING_POLICY = 2, DWMNCRP_DISABLED = 1
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 2, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
            )
        except Exception:
            pass                               # non-Windows or older Windows — ignore

    # ── helpers ──────────────────────────────────────────────────

    def _font(self) -> QFont:
        f = QFont(self._cfg["font_family"], self._cfg["font_size"])
        f.setWeight(QFont.Weight.Medium)
        return f

    def _chip_h(self) -> int:
        return QFontMetrics(self._font()).height() + _PAD_Y * 2

    def _chip_w(self, text: str, fm: QFontMetrics) -> int:
        return fm.horizontalAdvance(text) + _PAD_X * 2

    def _reposition(self):
        screen_geom = QApplication.primaryScreen().availableGeometry()
        chip_h = self._chip_h()
        # Window is one chip tall; wide enough for max_keys chips side by side.
        # Use a generous per-chip estimate so the window is never too narrow.
        chip_est = QFontMetrics(self._font()).averageCharWidth() * 12 + _PAD_X * 2
        n      = self._cfg["max_keys"]
        win_w  = chip_est * n + _GAP * max(0, n - 1) + _MARGIN * 2
        win_h  = chip_h + _MARGIN * 2

        pos = self._cfg["position"]
        sg  = screen_geom
        if pos == "bottom-right":
            x, y = sg.right() - win_w - _MARGIN, sg.bottom() - win_h - _MARGIN
        elif pos == "bottom-left":
            x, y = sg.left() + _MARGIN,           sg.bottom() - win_h - _MARGIN
        elif pos == "top-right":
            x, y = sg.right() - win_w - _MARGIN, sg.top() + _MARGIN
        elif pos == "top-left":
            x, y = sg.left() + _MARGIN,           sg.top() + _MARGIN
        else:                                   # custom
            x, y = self._cfg["custom_x"], self._cfg["custom_y"]

        self.setGeometry(x, y, win_w, win_h)

    # ── public API ───────────────────────────────────────────────

    def add_key(self, text: str):
        self._entries.append([text, 1.0])
        if len(self._entries) > self._cfg["max_keys"]:
            self._entries.pop(0)
        self.update()

    def apply_config(self, cfg: dict):
        self._cfg = cfg
        self._reposition()
        self.update()

    # ── animation tick ────────────────────────────────────────────

    def _tick(self):
        if not self._entries:
            return
        step = 0.05 / max(self._cfg["fade_time"], 0.1)
        self._entries = [[t, max(0.0, o - step)] for t, o in self._entries]
        self._entries = [e for e in self._entries if e[1] > 0.0]
        self.update()

    # ── painting ──────────────────────────────────────────────────

    def paintEvent(self, _event):
        if not self._entries:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self._font())
        fm     = painter.fontMetrics()
        chip_h = self._chip_h()

        pos        = self._cfg["position"]
        right_side = pos in ("bottom-right", "top-right")

        # Chips are horizontal. Newest chip is closest to the anchor corner.
        # right-anchored: newest on the right  → draw right-to-left
        # left-anchored:  newest on the left   → draw left-to-right
        ordered = list(reversed(self._entries)) if right_side else self._entries

        # Measure all chip widths upfront so we can place them precisely
        widths = [self._chip_w(text, fm) for text, _ in ordered]
        total_w = sum(widths) + _GAP * max(0, len(widths) - 1)

        # Vertical centre in the window
        y = _MARGIN

        if right_side:
            # start from right edge, move left
            cursor = self.width() - _MARGIN
            for (text, opacity), cw in zip(ordered, widths):
                x = cursor - cw
                self._draw_chip(painter, fm, chip_h, x, y, cw, text, opacity)
                cursor = x - _GAP
        else:
            # start from left edge, move right
            cursor = _MARGIN
            for (text, opacity), cw in zip(ordered, widths):
                self._draw_chip(painter, fm, chip_h, cursor, y, cw, text, opacity)
                cursor += cw + _GAP

        painter.end()

    def _draw_chip(self, painter, fm, chip_h, x, y, chip_w, text, opacity):
        # background pill
        bg = QColor(self._cfg["bg_color"])
        bg.setAlpha(int(self._cfg["bg_opacity"] / 100 * 255 * opacity))
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, chip_w, chip_h), _CORNER_R, _CORNER_R)
        painter.fillPath(path, QBrush(bg))

        # subtle border
        border = QColor(255, 255, 255, int(30 * opacity))
        painter.strokePath(path, QPen(border, 1))

        # text
        tc = QColor(self._cfg["text_color"])
        tc.setAlpha(int(255 * opacity))
        painter.setPen(QPen(tc))
        painter.drawText(
            int(x + _PAD_X),
            int(y + (chip_h - fm.height()) / 2 + fm.ascent()),
            text,
        )


# ══════════════════════════════════════════════════════════════════
#  Settings dialog
# ══════════════════════════════════════════════════════════════════

_POS_LABELS = ["Bottom-Right", "Bottom-Left", "Top-Right", "Top-Left", "Custom"]
_POS_KEYS   = ["bottom-right", "bottom-left", "top-right", "top-left", "custom"]


class SettingsDialog(QDialog):
    config_changed = pyqtSignal(dict)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self._cfg = dict(cfg)
        self.setWindowTitle("KeyCast  —  Settings")
        self.setMinimumWidth(420)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self._build_ui()
        self._load_values()

    # ── build UI ──────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        # ── Font ──────────────────────────────────────────────────
        font_box    = QGroupBox("Font")
        font_layout = QFormLayout(font_box)

        self._font_combo = QFontComboBox()
        font_layout.addRow("Family:", self._font_combo)

        self._font_size = QSpinBox()
        self._font_size.setRange(8, 96)
        self._font_size.setSuffix(" pt")
        font_layout.addRow("Size:", self._font_size)

        root.addWidget(font_box)

        # ── Position ──────────────────────────────────────────────
        pos_box    = QGroupBox("Position")
        pos_layout = QFormLayout(pos_box)

        self._pos_combo = QComboBox()
        self._pos_combo.addItems(_POS_LABELS)
        self._pos_combo.currentIndexChanged.connect(self._on_pos_changed)
        pos_layout.addRow("Anchor:", self._pos_combo)

        # custom X / Y row (hidden unless "Custom" selected)
        self._custom_lbl = QLabel("X / Y:")
        self._custom_x   = QSpinBox()
        self._custom_x.setRange(0, 9999)
        self._custom_x.setSuffix(" px")
        self._custom_y   = QSpinBox()
        self._custom_y.setRange(0, 9999)
        self._custom_y.setSuffix(" px")
        xy_row = QHBoxLayout()
        xy_row.setContentsMargins(0, 0, 0, 0)
        xy_row.addWidget(self._custom_x)
        xy_row.addWidget(QLabel("Y:"))
        xy_row.addWidget(self._custom_y)
        self._custom_widget = QWidget()
        self._custom_widget.setLayout(xy_row)
        pos_layout.addRow(self._custom_lbl, self._custom_widget)

        root.addWidget(pos_box)

        # ── Display ───────────────────────────────────────────────
        disp_box    = QGroupBox("Display")
        disp_layout = QFormLayout(disp_box)

        self._fade_spin = QDoubleSpinBox()
        self._fade_spin.setRange(0.5, 15.0)
        self._fade_spin.setSingleStep(0.5)
        self._fade_spin.setDecimals(1)
        self._fade_spin.setSuffix(" s")
        disp_layout.addRow("Fade-out time:", self._fade_spin)

        self._max_keys = QSpinBox()
        self._max_keys.setRange(1, 10)
        self._max_keys.setSuffix("  lines")
        disp_layout.addRow("Max lines shown:", self._max_keys)

        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(10, 100)
        self._opacity_lbl = QLabel()
        self._opacity_slider.valueChanged.connect(
            lambda v: self._opacity_lbl.setText(f"{v} %")
        )
        op_row = QHBoxLayout()
        op_row.setContentsMargins(0, 0, 0, 0)
        op_row.addWidget(self._opacity_slider)
        op_row.addWidget(self._opacity_lbl)
        op_widget = QWidget()
        op_widget.setLayout(op_row)
        disp_layout.addRow("Background opacity:", op_widget)

        root.addWidget(disp_box)

        # ── Colors ────────────────────────────────────────────────
        color_box    = QGroupBox("Colors")
        color_layout = QFormLayout(color_box)

        self._text_btn = QPushButton()
        self._text_btn.setFixedWidth(100)
        self._text_btn.clicked.connect(lambda: self._pick_color("text"))
        color_layout.addRow("Text:", self._text_btn)

        self._bg_btn = QPushButton()
        self._bg_btn.setFixedWidth(100)
        self._bg_btn.clicked.connect(lambda: self._pick_color("bg"))
        color_layout.addRow("Background:", self._bg_btn)

        root.addWidget(color_box)

        # ── Buttons ───────────────────────────────────────────────
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background:#cccccc;")
        root.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply)
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

    # ── helpers ──────────────────────────────────────────────────

    def _on_pos_changed(self, idx: int):
        custom = (idx == 4)
        self._custom_lbl.setVisible(custom)
        self._custom_widget.setVisible(custom)

    def _pick_color(self, which: str):
        key     = f"{which}_color"
        current = QColor(self._cfg[key])
        col     = QColorDialog.getColor(current, self, f"Pick {which} colour")
        if col.isValid():
            self._cfg[key] = col.name()
            self._refresh_btn(which)

    def _refresh_btn(self, which: str):
        btn   = self._text_btn if which == "text" else self._bg_btn
        color = self._cfg[f"{which}_color"]
        qc    = QColor(color)
        luma  = 0.299 * qc.red() + 0.587 * qc.green() + 0.114 * qc.blue()
        fg    = "#000" if luma > 128 else "#fff"
        btn.setStyleSheet(
            f"background-color:{color}; color:{fg}; border:1px solid #666; border-radius:4px;"
        )
        btn.setText(color)

    # ── load / save ───────────────────────────────────────────────

    def _load_values(self):
        self._font_combo.setCurrentFont(QFont(self._cfg["font_family"]))
        self._font_size.setValue(self._cfg["font_size"])

        pos = self._cfg["position"]
        idx = _POS_KEYS.index(pos) if pos in _POS_KEYS else 0
        self._pos_combo.setCurrentIndex(idx)
        self._on_pos_changed(idx)

        self._custom_x.setValue(self._cfg["custom_x"])
        self._custom_y.setValue(self._cfg["custom_y"])
        self._fade_spin.setValue(self._cfg["fade_time"])
        self._max_keys.setValue(self._cfg["max_keys"])
        self._opacity_slider.setValue(self._cfg["bg_opacity"])
        self._opacity_lbl.setText(f"{self._cfg['bg_opacity']} %")
        self._refresh_btn("text")
        self._refresh_btn("bg")

    def _read_form(self):
        """Copy widget values into self._cfg."""
        self._cfg["font_family"] = self._font_combo.currentFont().family()
        self._cfg["font_size"]   = self._font_size.value()
        self._cfg["position"]    = _POS_KEYS[self._pos_combo.currentIndex()]
        self._cfg["custom_x"]    = self._custom_x.value()
        self._cfg["custom_y"]    = self._custom_y.value()
        self._cfg["fade_time"]   = self._fade_spin.value()
        self._cfg["max_keys"]    = self._max_keys.value()
        self._cfg["bg_opacity"]  = self._opacity_slider.value()

    def _apply(self):
        """Apply settings to the overlay without closing the dialog."""
        self._read_form()
        save_config(self._cfg)
        self.config_changed.emit(dict(self._cfg))

    def _save(self):
        self._apply()
        self.accept()


# ══════════════════════════════════════════════════════════════════
#  System tray
# ══════════════════════════════════════════════════════════════════

def _make_icon() -> QIcon:
    """Generate a simple keyboard icon at runtime (no external file needed)."""
    px = QPixmap(32, 32)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # keyboard body
    p.setBrush(QBrush(QColor("#4A90D9")))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(2, 7, 28, 19, 3, 3)

    # key tiles
    p.setBrush(QBrush(QColor("#FFFFFF")))
    tiles = [
        # top row
        (5, 11, 4, 4), (11, 11, 4, 4), (17, 11, 4, 4), (23, 11, 4, 4),
        # home row
        (5, 17, 4, 4), (11, 17, 4, 4), (17, 17, 4, 4), (23, 17, 4, 4),
        # space bar
        (8, 23, 16, 3),
    ]
    for tx, ty, tw, th in tiles:
        p.drawRoundedRect(tx, ty, tw, th, 1, 1)

    p.end()
    return QIcon(px)


class TrayManager:
    def __init__(self, cfg: dict, overlay: OverlayWindow):
        self._cfg     = cfg
        self._overlay = overlay

        self._tray = QSystemTrayIcon(_make_icon())
        self._tray.setToolTip("KeyCast — Keyboard Overlay")

        menu = QMenu()
        settings_act = QAction("Settings…", menu)
        settings_act.triggered.connect(self._open_settings)
        quit_act = QAction("Close KeyCast", menu)
        quit_act.triggered.connect(QApplication.quit)

        menu.addAction(settings_act)
        menu.addSeparator()
        menu.addAction(quit_act)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def _on_activated(self, reason):
        AR = QSystemTrayIcon.ActivationReason
        if reason == AR.DoubleClick:
            self._open_settings()
        elif reason == AR.MiddleClick:
            QApplication.quit()

    def _open_settings(self):
        dlg = SettingsDialog(self._cfg)
        dlg.config_changed.connect(self._on_cfg_changed)
        dlg.exec()

    def _on_cfg_changed(self, new_cfg: dict):
        self._cfg = new_cfg
        self._overlay.apply_config(new_cfg)


# ══════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════

def main():
    multiprocessing.freeze_support()           # needed for PyInstaller --onefile

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)       # keep alive when settings dialog closes
    app.setApplicationName("KeyCast")

    cfg      = load_config()
    overlay  = OverlayWindow(cfg)
    listener = KeyboardListener()
    listener.sig.fired.connect(overlay.add_key)
    listener.start()

    tray = TrayManager(cfg, overlay)          # noqa: F841 — kept alive by reference

    ret = app.exec()
    listener.stop()
    listener.wait(2000)
    sys.exit(ret)


if __name__ == "__main__":
    main()
