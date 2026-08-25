"""Central options dialog for every persisted user-facing setting."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
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

        self.damage_font_size = QDoubleSpinBox()
        self.damage_font_size.setRange(13.0, 42.0)
        self.damage_font_size.setDecimals(1)
        self.damage_font_size.setSuffix(" pt")
        self.damage_font_size.setSingleStep(1.0)
        self.damage_font_size.setValue(preferences.damage_font_size)

        self.header_font_size = QDoubleSpinBox()
        self.header_font_size.setRange(10.0, 36.0)
        self.header_font_size.setDecimals(1)
        self.header_font_size.setSuffix(" pt")
        self.header_font_size.setSingleStep(1.0)
        self.header_font_size.setValue(preferences.header_font_size)

        self.max_rows = QSpinBox()
        self.max_rows.setRange(3, 20)
        self.max_rows.setValue(preferences.max_rows)

        self.history_rows = QSpinBox()
        self.history_rows.setRange(10, 1000)
        self.history_rows.setSingleStep(10)
        self.history_rows.setValue(preferences.history_rows)

        self.encounter_timeout = QSpinBox()
        self.encounter_timeout.setRange(3, 60)
        self.encounter_timeout.setSuffix(" seconds")
        self.encounter_timeout.setValue(preferences.encounter_timeout)

        self.fade_rows = QCheckBox("Fade rows out after inactivity")
        self.fade_rows.setChecked(preferences.fade_rows)

        self.fade_delay = QSpinBox()
        self.fade_delay.setRange(3, 120)
        self.fade_delay.setSuffix(" seconds")
        self.fade_delay.setValue(preferences.fade_delay)
        self.fade_delay.setEnabled(preferences.fade_rows)
        self.fade_rows.toggled.connect(self.fade_delay.setEnabled)

        self.show_resists = QCheckBox("Show your spells being resisted")
        self.show_resists.setChecked(preferences.show_resists)

        self.show_pet = QCheckBox("Show separate Pet damage window")
        self.show_pet.setChecked(preferences.show_pet)

        self.mirror_character = QCheckBox("Mirror YOU feed (numbers on the left)")
        self.mirror_character.setChecked(preferences.mirror_character)

        self.mirror_pet = QCheckBox("Mirror PET feed (numbers on the left)")
        self.mirror_pet.setChecked(preferences.mirror_pet)

        self.auto_quit_with_game = QCheckBox("Automatically quit when EverQuest closes")
        self.auto_quit_with_game.setChecked(preferences.auto_quit_with_game)

        self.minimize_to_tray = QCheckBox("Closing the control window minimizes to tray")
        self.minimize_to_tray.setChecked(preferences.minimize_to_tray)

        self.hide_when_unfocused = QCheckBox("Hide overlays when EverQuest is not focused")
        self.hide_when_unfocused.setChecked(preferences.hide_when_unfocused)

        self.check_updates = QCheckBox("Check for updates at startup (one request to GitHub)")
        self.check_updates.setChecked(preferences.check_updates)

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
        form.addRow("Damage text size", self.damage_font_size)
        form.addRow("Header text size", self.header_font_size)
        form.addRow("Maximum visible rows", self.max_rows)
        form.addRow("History rows per window", self.history_rows)
        form.addRow("End encounter after", self.encounter_timeout)
        form.addRow("Text decay", self.fade_rows)
        form.addRow("Fade rows after", self.fade_delay)
        form.addRow("Spell resists", self.show_resists)
        form.addRow("Pet feed", self.show_pet)
        form.addRow("YOU layout", self.mirror_character)
        form.addRow("PET layout", self.mirror_pet)
        form.addRow("Game exit", self.auto_quit_with_game)
        form.addRow("Close button", self.minimize_to_tray)
        form.addRow("Focus", self.hide_when_unfocused)
        form.addRow("Updates", self.check_updates)
        form.addRow("EverQuest log", log_widget)
        form.addRow("Input mode", self.locked)

        hint = QLabel(
            "YOU and PET are independently movable/resizable windows. Damage and header "
            "text sizes are independent point sizes. Resize either window for more name room; "
            "hover a top edge for controls.\nMirror a feed to put its numbers on the left — "
            "an unmirrored feed beside a mirrored one forms one number column in the middle "
            "with descriptions growing outward.\nLocked: mouse input passes through; "
            "Ctrl+Alt+L always unlocks."
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
            damage_font_size=self.damage_font_size.value(),
            header_font_size=self.header_font_size.value(),
            encounter_timeout=self.encounter_timeout.value(),
            fade_rows=self.fade_rows.isChecked(),
            fade_delay=self.fade_delay.value(),
            show_resists=self.show_resists.isChecked(),
            show_pet=self.show_pet.isChecked(),
            mirror_character=self.mirror_character.isChecked(),
            mirror_pet=self.mirror_pet.isChecked(),
            auto_quit_with_game=self.auto_quit_with_game.isChecked(),
            minimize_to_tray=self.minimize_to_tray.isChecked(),
            hide_when_unfocused=self.hide_when_unfocused.isChecked(),
            check_updates=self.check_updates.isChecked(),
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
        self.damage_font_size.setValue(defaults.damage_font_size)
        self.header_font_size.setValue(defaults.header_font_size)
        self.max_rows.setValue(defaults.max_rows)
        self.history_rows.setValue(defaults.history_rows)
        self.encounter_timeout.setValue(defaults.encounter_timeout)
        self.fade_rows.setChecked(defaults.fade_rows)
        self.fade_delay.setValue(defaults.fade_delay)
        self.show_resists.setChecked(defaults.show_resists)
        self.show_pet.setChecked(defaults.show_pet)
        self.mirror_character.setChecked(defaults.mirror_character)
        self.mirror_pet.setChecked(defaults.mirror_pet)
        self.auto_quit_with_game.setChecked(defaults.auto_quit_with_game)
        self.minimize_to_tray.setChecked(defaults.minimize_to_tray)
        self.hide_when_unfocused.setChecked(defaults.hide_when_unfocused)
        self.check_updates.setChecked(defaults.check_updates)
        self.locked.setChecked(defaults.locked)
        self.log_file.clear()
