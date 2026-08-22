"""Central options dialog for every persisted user-facing setting."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .settings import OverlayPreferences


class OptionsDialog(QDialog):
    def __init__(self, preferences: OverlayPreferences, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("EQL Combat Feed options")
        self.setModal(True)
        self.setMinimumWidth(460)

        self.font_scale = QSpinBox()
        self.font_scale.setRange(60, 200)
        self.font_scale.setSuffix(" %")
        self.font_scale.setSingleStep(5)
        self.font_scale.setValue(round(preferences.font_scale * 100))

        self.max_rows = QSpinBox()
        self.max_rows.setRange(3, 8)
        self.max_rows.setValue(preferences.max_rows)

        self.history_rows = QSpinBox()
        self.history_rows.setRange(10, 1000)
        self.history_rows.setSingleStep(10)
        self.history_rows.setValue(preferences.history_rows)

        self.encounter_timeout = QSpinBox()
        self.encounter_timeout.setRange(3, 60)
        self.encounter_timeout.setSuffix(" seconds")
        self.encounter_timeout.setValue(preferences.encounter_timeout)

        self.show_pet = QCheckBox("Show separate Pet damage window")
        self.show_pet.setChecked(preferences.show_pet)

        self.auto_quit_with_game = QCheckBox("Automatically quit when EverQuest closes")
        self.auto_quit_with_game.setChecked(preferences.auto_quit_with_game)

        self.locked = QCheckBox("Start and remain click-through until unlocked")
        self.locked.setChecked(preferences.locked)

        self.log_file = QLineEdit(str(preferences.log_file or ""))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._choose_log)
        log_row = QHBoxLayout()
        log_row.setContentsMargins(0, 0, 0, 0)
        log_row.addWidget(self.log_file, 1)
        log_row.addWidget(browse)
        log_widget = QWidget()
        log_widget.setLayout(log_row)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.addRow("Text size", self.font_scale)
        form.addRow("Maximum visible rows", self.max_rows)
        form.addRow("History rows per window", self.history_rows)
        form.addRow("End encounter after", self.encounter_timeout)
        form.addRow("Pet feed", self.show_pet)
        form.addRow("Game exit", self.auto_quit_with_game)
        form.addRow("EverQuest log", log_widget)
        form.addRow("Input mode", self.locked)

        hint = QLabel(
            "YOU and PET are independently movable/resizable windows. Resize either for "
            "more name room; Text size controls both. Hover a top edge for controls.\n"
            "Locked: mouse input passes through; Ctrl+Alt+L always unlocks."
        )
        hint.setWordWrap(True)
        hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        reset = buttons.addButton("Reset defaults", QDialogButtonBox.ButtonRole.ResetRole)
        reset.clicked.connect(self._reset_defaults)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(buttons)

    def result_preferences(self, current: OverlayPreferences) -> OverlayPreferences:
        log_text = self.log_file.text().strip()
        return OverlayPreferences(
            max_rows=self.max_rows.value(),
            history_rows=self.history_rows.value(),
            font_scale=self.font_scale.value() / 100.0,
            encounter_timeout=self.encounter_timeout.value(),
            show_pet=self.show_pet.isChecked(),
            auto_quit_with_game=self.auto_quit_with_game.isChecked(),
            locked=self.locked.isChecked(),
            position=current.position,
            size=current.size,
            pet_position=current.pet_position,
            pet_size=current.pet_size,
            log_file=Path(log_text) if log_text else None,
        )

    def _choose_log(self) -> None:
        current = Path(self.log_file.text()).expanduser() if self.log_file.text() else Path.home()
        initial = str(current.parent if current.suffix else current)
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Choose EverQuest log",
            initial,
            "EverQuest logs (eqlog_*.txt);;Text files (*.txt);;All files (*)",
        )
        if selected:
            self.log_file.setText(selected)

    def _reset_defaults(self) -> None:
        defaults = OverlayPreferences()
        self.font_scale.setValue(round(defaults.font_scale * 100))
        self.max_rows.setValue(defaults.max_rows)
        self.history_rows.setValue(defaults.history_rows)
        self.encounter_timeout.setValue(defaults.encounter_timeout)
        self.show_pet.setChecked(defaults.show_pet)
        self.auto_quit_with_game.setChecked(defaults.auto_quit_with_game)
        self.locked.setChecked(defaults.locked)
        self.log_file.clear()
