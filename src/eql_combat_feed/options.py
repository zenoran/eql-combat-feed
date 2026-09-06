"""Central options dialog for every persisted user-facing setting."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .hotkey import chord_from_sequence, default_lock_hotkey, default_search_hotkey
from .settings import OverlayPreferences

PORTABLE = QKeySequence.SequenceFormat.PortableText
FORM_LABEL_WIDTH = 155


class OptionsDialog(QDialog):
    def __init__(self, preferences: OverlayPreferences, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("EQL Combat Feed options")
        self.setModal(True)
        self.setMinimumWidth(520)

        self.damage_font_size = QDoubleSpinBox()
        self.damage_font_size.setRange(13.0, 42.0)
        self.damage_font_size.setDecimals(1)
        self.damage_font_size.setSuffix(" pt")
        self.damage_font_size.setSingleStep(1.0)
        self.damage_font_size.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.damage_font_size.setValue(preferences.damage_font_size)

        self.header_font_size = QDoubleSpinBox()
        self.header_font_size.setRange(10.0, 36.0)
        self.header_font_size.setDecimals(1)
        self.header_font_size.setSuffix(" pt")
        self.header_font_size.setSingleStep(1.0)
        self.header_font_size.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.header_font_size.setValue(preferences.header_font_size)

        self.max_rows = QSpinBox()
        self.max_rows.setRange(3, 20)
        self.max_rows.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.max_rows.setValue(preferences.max_rows)

        self.history_rows = QSpinBox()
        self.history_rows.setRange(10, 1000)
        self.history_rows.setSingleStep(10)
        self.history_rows.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.history_rows.setValue(preferences.history_rows)

        self.encounter_timeout = QSpinBox()
        self.encounter_timeout.setRange(3, 60)
        self.encounter_timeout.setSuffix(" seconds")
        self.encounter_timeout.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.encounter_timeout.setValue(preferences.encounter_timeout)

        self.fade_rows = QCheckBox("Fade rows out after inactivity")
        self.fade_rows.setChecked(preferences.fade_rows)

        self.fade_delay = QSpinBox()
        self.fade_delay.setRange(3, 120)
        self.fade_delay.setSuffix(" seconds")
        self.fade_delay.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.fade_delay.setValue(preferences.fade_delay)

        self.reveal_faded_rows_on_hover = QCheckBox("Reveal faded history on pointer hover")
        self.reveal_faded_rows_on_hover.setChecked(preferences.reveal_faded_rows_on_hover)
        self.reveal_faded_rows_on_hover.setToolTip(
            "Temporarily restores faded rows at full opacity. Wheel scrolling through history "
            "still works when this is disabled."
        )
        self.fade_rows.toggled.connect(self._sync_fade_controls)
        self._sync_fade_controls(preferences.fade_rows)

        self.show_resists = QCheckBox("Show your spells being resisted")
        self.show_resists.setChecked(preferences.show_resists)

        self.show_pet = QCheckBox("Show separate Pet damage window")
        self.show_pet.setChecked(preferences.show_pet)

        self.mirror_character = QCheckBox("Numbers on the left")
        self.mirror_character.setChecked(preferences.mirror_character)

        self.mirror_pet = QCheckBox("Numbers on the left")
        self.mirror_pet.setChecked(preferences.mirror_pet)

        self.auto_quit_with_game = QCheckBox("Automatically quit when EverQuest closes")
        self.auto_quit_with_game.setChecked(preferences.auto_quit_with_game)

        self.launch_eq_on_startup = QCheckBox("Launch EverQuest when Combat Feed starts")
        self.launch_eq_on_startup.setChecked(preferences.launch_eq_on_startup)
        self.launch_eq_on_startup.setToolTip(
            "Finds LaunchPad.exe beside the Logs folder for the selected EverQuest log."
        )

        self.minimize_to_tray = QCheckBox("Closing the control window minimizes to tray")
        self.minimize_to_tray.setChecked(preferences.minimize_to_tray)

        self.hide_when_unfocused = QCheckBox("Hide overlays when EverQuest is not focused")
        self.hide_when_unfocused.setChecked(preferences.hide_when_unfocused)

        self.check_updates = QCheckBox("Check for updates at startup")
        self.check_updates.setChecked(preferences.check_updates)
        self.check_updates.setToolTip("Makes one request to GitHub at startup.")

        self.locked = QCheckBox("Start and remain click-through until unlocked")
        self.locked.setChecked(preferences.locked)

        self.lock_hotkey = self._hotkey_editor(preferences.lock_hotkey)
        self.search_hotkey = self._hotkey_editor(preferences.search_hotkey)
        self.hotkey_warning = QLabel()
        self.hotkey_warning.setWordWrap(True)
        self.hotkey_warning.setStyleSheet("color: #e06c75;")
        self.hotkey_warning.hide()

        self.log_file = QLineEdit(str(preferences.log_file or ""))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._choose_log)
        log_row = QHBoxLayout()
        log_row.setContentsMargins(0, 0, 0, 0)
        log_row.addWidget(self.log_file, 1)
        log_row.addWidget(browse)
        log_widget = QWidget()
        log_widget.setLayout(log_row)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._display_tab(), "Display")
        self.tabs.addTab(self._behavior_tab(), "Behavior")
        self.tabs.addTab(self._application_tab(log_widget), "Application")

        hint = QLabel(
            "YOU and PET can be moved and resized independently. Pair an unmirrored feed with "
            "a mirrored feed to place both number lanes at the center. The lock hotkey always "
            "unlocks."
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
        layout.addWidget(self.tabs)
        layout.addWidget(hint)
        layout.addWidget(buttons)

    def _display_tab(self) -> QWidget:
        appearance = self._form_layout()
        self._add_form_row(appearance, "Damage text size", self.damage_font_size)
        self._add_form_row(appearance, "Header text size", self.header_font_size)
        self._add_form_row(appearance, "Maximum visible rows", self.max_rows)

        feeds = QVBoxLayout()
        feeds.addWidget(self.show_pet)
        feeds.addWidget(self.show_resists)
        feed_layouts = self._form_layout()
        self._add_form_row(feed_layouts, "YOU feed", self.mirror_character)
        self._add_form_row(feed_layouts, "PET feed", self.mirror_pet)
        feeds.addLayout(feed_layouts)

        layout = QVBoxLayout()
        layout.addWidget(self._group("Appearance", appearance))
        layout.addWidget(self._group("Feeds", feeds))
        layout.addStretch()
        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def _behavior_tab(self) -> QWidget:
        decay = QVBoxLayout()
        decay.addWidget(self.fade_rows)
        fade_timing = self._form_layout()
        self._add_form_row(fade_timing, "Fade rows after", self.fade_delay)
        decay.addLayout(fade_timing)
        decay.addWidget(self.reveal_faded_rows_on_hover)

        history = self._form_layout()
        self._add_form_row(history, "History rows per window", self.history_rows)
        self._add_form_row(history, "End encounter after", self.encounter_timeout)

        interaction = QVBoxLayout()
        interaction.addWidget(self.locked)
        interaction.addWidget(self.hide_when_unfocused)

        hotkeys = QVBoxLayout()
        hotkey_rows = self._form_layout()
        self._add_form_row(hotkey_rows, "Lock / unlock overlays", self.lock_hotkey)
        self._add_form_row(hotkey_rows, "Log search", self.search_hotkey)
        hotkeys.addLayout(hotkey_rows)
        hotkeys.addWidget(self.hotkey_warning)

        layout = QVBoxLayout()
        layout.addWidget(self._group("Text decay", decay))
        layout.addWidget(self._group("History and encounters", history))
        layout.addWidget(self._group("Interaction", interaction))
        layout.addWidget(self._group("Hotkeys", hotkeys))
        layout.addStretch()
        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def _application_tab(self, log_widget: QWidget) -> QWidget:
        log = QHBoxLayout()
        log.addWidget(QLabel("EverQuest log"))
        log.addWidget(log_widget, 1)

        lifecycle = QVBoxLayout()
        lifecycle.addWidget(self.launch_eq_on_startup)
        lifecycle.addWidget(self.auto_quit_with_game)
        lifecycle.addWidget(self.minimize_to_tray)
        lifecycle.addWidget(self.check_updates)

        layout = QVBoxLayout()
        layout.addWidget(self._group("Log source", log))
        layout.addWidget(self._group("Application", lifecycle))
        layout.addStretch()
        tab = QWidget()
        tab.setLayout(layout)
        return tab

    @staticmethod
    def _form_layout() -> QFormLayout:
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return form

    @staticmethod
    def _add_form_row(form: QFormLayout, text: str, field: QWidget) -> None:
        label = QLabel(text)
        label.setFixedWidth(FORM_LABEL_WIDTH)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.addRow(label, field)

    @staticmethod
    def _group(title: str, layout: QFormLayout | QHBoxLayout | QVBoxLayout) -> QGroupBox:
        group = QGroupBox(title)
        group.setLayout(layout)
        return group

    def _sync_fade_controls(self, enabled: bool) -> None:
        self.fade_delay.setEnabled(enabled)
        self.reveal_faded_rows_on_hover.setEnabled(enabled)

    @staticmethod
    def _hotkey_editor(text: str) -> QKeySequenceEdit:
        editor = QKeySequenceEdit(QKeySequence(text, PORTABLE))
        editor.setMaximumSequenceLength(1)
        editor.setClearButtonEnabled(True)
        editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        editor.setToolTip(
            "Click, then press the combination. Needs at least one modifier plus a letter, "
            "digit, F-key, or Space. Clear it to restore the default."
        )
        return editor

    @staticmethod
    def _hotkey_text(editor: QKeySequenceEdit, default: str) -> str:
        text = editor.keySequence().toString(PORTABLE).strip()
        return text or default

    def _invalid_hotkeys(self) -> list[str]:
        editors = (("Lock / unlock overlays", self.lock_hotkey), ("Log search", self.search_hotkey))
        return [
            name
            for name, editor in editors
            if editor.keySequence().toString(PORTABLE).strip()
            and chord_from_sequence(editor.keySequence().toString(PORTABLE)) is None
        ]

    def accept(self) -> None:  # type: ignore[override]
        invalid = self._invalid_hotkeys()
        if invalid:
            self.hotkey_warning.setText(
                f"{' and '.join(invalid)}: use at least one modifier (Ctrl, Alt, Shift) plus a "
                "letter, digit, F-key, or Space."
            )
            self.hotkey_warning.show()
            self.tabs.setCurrentIndex(1)
            return
        super().accept()

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
            reveal_faded_rows_on_hover=self.reveal_faded_rows_on_hover.isChecked(),
            show_resists=self.show_resists.isChecked(),
            show_pet=self.show_pet.isChecked(),
            mirror_character=self.mirror_character.isChecked(),
            mirror_pet=self.mirror_pet.isChecked(),
            auto_quit_with_game=self.auto_quit_with_game.isChecked(),
            launch_eq_on_startup=self.launch_eq_on_startup.isChecked(),
            minimize_to_tray=self.minimize_to_tray.isChecked(),
            hide_when_unfocused=self.hide_when_unfocused.isChecked(),
            check_updates=self.check_updates.isChecked(),
            locked=self.locked.isChecked(),
            lock_hotkey=self._hotkey_text(self.lock_hotkey, default_lock_hotkey()),
            search_hotkey=self._hotkey_text(self.search_hotkey, default_search_hotkey()),
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
        self.reveal_faded_rows_on_hover.setChecked(defaults.reveal_faded_rows_on_hover)
        self.show_resists.setChecked(defaults.show_resists)
        self.show_pet.setChecked(defaults.show_pet)
        self.mirror_character.setChecked(defaults.mirror_character)
        self.mirror_pet.setChecked(defaults.mirror_pet)
        self.auto_quit_with_game.setChecked(defaults.auto_quit_with_game)
        self.launch_eq_on_startup.setChecked(defaults.launch_eq_on_startup)
        self.minimize_to_tray.setChecked(defaults.minimize_to_tray)
        self.hide_when_unfocused.setChecked(defaults.hide_when_unfocused)
        self.check_updates.setChecked(defaults.check_updates)
        self.locked.setChecked(defaults.locked)
        self.lock_hotkey.setKeySequence(QKeySequence(defaults.lock_hotkey, PORTABLE))
        self.search_hotkey.setKeySequence(QKeySequence(defaults.search_hotkey, PORTABLE))
        self.hotkey_warning.hide()
        self.log_file.clear()
