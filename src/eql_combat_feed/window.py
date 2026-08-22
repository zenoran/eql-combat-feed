"""Normal taskbar-visible control window for the overlay application."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .settings import OverlayPreferences


class ControlWindow(QMainWindow):
    quit_requested = Signal()
    lock_changed = Signal(bool)
    pet_visibility_changed = Signal(bool)
    auto_quit_changed = Signal(bool)
    options_requested = Signal()
    choose_log_requested = Signal()
    clear_requested = Signal()

    def __init__(self, preferences: OverlayPreferences, icon: QIcon) -> None:
        super().__init__()
        self._allow_close = False
        self.setWindowTitle(f"EQL Combat Feed {__version__}")
        self.setWindowIcon(icon)
        self.setMinimumSize(500, 310)
        self.resize(560, 340)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)

        heading = QLabel("EQL Combat Feed")
        heading.setStyleSheet("font-size: 20px; font-weight: 700;")
        subtitle = QLabel("Damage and DPS. That's it.")
        subtitle.setStyleSheet("color: #707780;")

        self.status_value = QLabel("Starting…")
        self.status_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.log_value = QLabel("No log selected")
        self.log_value.setWordWrap(True)
        self.log_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.game_value = QLabel("Looking for EverQuest…")

        status_grid = QGridLayout()
        status_grid.addWidget(QLabel("Status"), 0, 0)
        status_grid.addWidget(self.status_value, 0, 1)
        status_grid.addWidget(QLabel("EverQuest"), 1, 0)
        status_grid.addWidget(self.game_value, 1, 1)
        status_grid.addWidget(QLabel("Log"), 2, 0)
        status_grid.addWidget(self.log_value, 2, 1)
        status_grid.setColumnStretch(1, 1)
        status_group = QGroupBox("Current state")
        status_group.setLayout(status_grid)

        self.locked = QCheckBox("Locked / click-through")
        self.locked.setChecked(preferences.locked)
        self.locked.toggled.connect(self.lock_changed)
        self.show_pet = QCheckBox("Show Pet overlay")
        self.show_pet.setChecked(preferences.show_pet)
        self.show_pet.toggled.connect(self.pet_visibility_changed)
        self.auto_quit = QCheckBox("Automatically quit when EverQuest closes")
        self.auto_quit.setChecked(preferences.auto_quit_with_game)
        self.auto_quit.toggled.connect(self.auto_quit_changed)

        toggles = QVBoxLayout()
        toggles.addWidget(self.locked)
        toggles.addWidget(self.show_pet)
        toggles.addWidget(self.auto_quit)
        behavior_group = QGroupBox("Behavior")
        behavior_group.setLayout(toggles)

        choose_log = QPushButton("Choose log…")
        choose_log.clicked.connect(self.choose_log_requested)
        clear = QPushButton("Clear feeds")
        clear.clicked.connect(self.clear_requested)
        options = QPushButton("Options…")
        options.clicked.connect(self.options_requested)
        close = QPushButton("Quit")
        close.clicked.connect(self.quit_requested)

        buttons = QHBoxLayout()
        buttons.addWidget(choose_log)
        buttons.addWidget(clear)
        buttons.addStretch(1)
        buttons.addWidget(options)
        buttons.addWidget(close)

        layout = QVBoxLayout()
        layout.addWidget(heading)
        layout.addWidget(subtitle)
        layout.addSpacing(6)
        layout.addWidget(status_group)
        layout.addWidget(behavior_group)
        layout.addStretch(1)
        layout.addLayout(buttons)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

    def set_status(self, message: str, *, error: bool = False) -> None:
        self.status_value.setText(message)
        self.status_value.setStyleSheet("color: #b00020;" if error else "")

    def set_log_path(self, path: Path | None) -> None:
        self.log_value.setText(str(path) if path else "No log selected")

    def set_game_running(self, running: bool, *, seen_running: bool) -> None:
        if running:
            self.game_value.setText("Running")
            self.game_value.setStyleSheet("color: #16803a; font-weight: 600;")
        elif seen_running:
            self.game_value.setText("Closed")
            self.game_value.setStyleSheet("color: #9a4d00; font-weight: 600;")
        else:
            self.game_value.setText("Not running yet")
            self.game_value.setStyleSheet("")

    def sync_preferences(self, preferences: OverlayPreferences) -> None:
        for widget, value in (
            (self.locked, preferences.locked),
            (self.show_pet, preferences.show_pet),
            (self.auto_quit, preferences.auto_quit_with_game),
        ):
            widget.blockSignals(True)
            widget.setChecked(value)
            widget.blockSignals(False)

    def show_and_raise(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def allow_close(self) -> None:
        self._allow_close = True

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._allow_close:
            event.accept()
            return
        event.ignore()
        self.quit_requested.emit()
