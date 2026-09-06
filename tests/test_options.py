import importlib
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

qt_core = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
qt_gui = pytest.importorskip("PySide6.QtGui", exc_type=ImportError)
qt_widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
QPoint = qt_core.QPoint
QSize = qt_core.QSize
QKeySequence = qt_gui.QKeySequence
QApplication = qt_widgets.QApplication
QDialog = qt_widgets.QDialog
QGroupBox = qt_widgets.QGroupBox
hotkey_module = importlib.import_module("eql_combat_feed.hotkey")
options_module = importlib.import_module("eql_combat_feed.options")
OptionsDialog = options_module.OptionsDialog
OverlayPreferences = importlib.import_module("eql_combat_feed.settings").OverlayPreferences


def test_options_dialog_records_hotkeys_and_rejects_bare_keys() -> None:
    app = QApplication.instance() or QApplication([])
    current = OverlayPreferences()
    dialog = OptionsDialog(current)
    assert dialog.lock_hotkey.keySequence().toString() == QKeySequence(
        current.lock_hotkey
    ).toString()

    dialog.lock_hotkey.setKeySequence(QKeySequence("Ctrl+Shift+F9"))
    dialog.search_hotkey.setKeySequence(QKeySequence())  # cleared → default
    result = dialog.result_preferences(current)
    assert result.lock_hotkey == "Ctrl+Shift+F9"
    assert result.search_hotkey == hotkey_module.default_search_hotkey()

    dialog.search_hotkey.setKeySequence(QKeySequence("G"))
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert not dialog.hotkey_warning.isHidden()
    assert "Log search" in dialog.hotkey_warning.text()

    dialog.search_hotkey.setKeySequence(QKeySequence("Alt+Space"))
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.result_preferences(current).search_hotkey == "Alt+Space"

    dialog._reset_defaults()
    assert dialog.result_preferences(current).lock_hotkey == hotkey_module.default_lock_hotkey()
    dialog.close()
    app.processEvents()


def test_options_dialog_tracks_split_window_configuration(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    current = OverlayPreferences(
        position=QPoint(10, 20),
        size=QSize(900, 465),
        pet_position=QPoint(950, 20),
        pet_size=QSize(500, 400),
    )
    dialog = OptionsDialog(current)
    dialog.damage_font_size.setValue(30.5)
    dialog.header_font_size.setValue(22.0)
    dialog.max_rows.setValue(7)
    dialog.history_rows.setValue(250)
    dialog.encounter_timeout.setValue(14)
    dialog.reveal_faded_rows_on_hover.setChecked(False)
    dialog.show_pet.setChecked(False)
    dialog.auto_quit_with_game.setChecked(True)
    dialog.launch_eq_on_startup.setChecked(True)
    dialog.minimize_to_tray.setChecked(True)
    dialog.locked.setChecked(True)
    log = tmp_path / "eqlog_Hero_freeport.txt"
    dialog.log_file.setText(str(log))

    result = dialog.result_preferences(current)

    assert result.damage_font_size == 30.5
    assert result.header_font_size == 22.0
    assert result.max_rows == 7
    assert result.history_rows == 250
    assert result.encounter_timeout == 14
    assert result.reveal_faded_rows_on_hover is False
    assert result.show_pet is False
    assert result.auto_quit_with_game is True
    assert result.launch_eq_on_startup is True
    assert result.minimize_to_tray is True
    assert result.locked is True
    assert result.position == current.position
    assert result.size == current.size
    assert result.pet_position == current.pet_position
    assert result.pet_size == current.pet_size
    assert result.log_file == log
    dialog.close()
    app.processEvents()


def test_options_dialog_organizes_controls_into_labeled_tabs() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = OptionsDialog(OverlayPreferences())

    assert [dialog.tabs.tabText(index) for index in range(dialog.tabs.count())] == [
        "Display",
        "Behavior",
        "Application",
    ]
    assert {group.title() for group in dialog.findChildren(QGroupBox)} == {
        "Appearance",
        "Feeds",
        "Text decay",
        "History and encounters",
        "Interaction",
        "Hotkeys",
        "Log source",
        "Application",
    }
    assert dialog.tabs.widget(1).isAncestorOf(dialog.reveal_faded_rows_on_hover)
    assert dialog.tabs.widget(1).isAncestorOf(dialog.lock_hotkey)
    log_group = next(
        group for group in dialog.findChildren(QGroupBox) if group.title() == "Log source"
    )
    assert isinstance(log_group.layout(), qt_widgets.QHBoxLayout)
    assert log_group.layout().stretch(1) == 1

    form_layouts = dialog.findChildren(qt_widgets.QFormLayout)
    label_widths = {
        form.itemAt(row, qt_widgets.QFormLayout.ItemRole.LabelRole).widget().minimumWidth()
        for form in form_layouts
        for row in range(form.rowCount())
    }
    assert label_widths == {options_module.FORM_LABEL_WIDTH}
    assert dialog.damage_font_size.sizePolicy().horizontalPolicy() == (
        qt_widgets.QSizePolicy.Policy.Expanding
    )
    assert dialog.max_rows.sizePolicy().horizontalPolicy() == (
        qt_widgets.QSizePolicy.Policy.Expanding
    )
    assert dialog.lock_hotkey.sizePolicy().horizontalPolicy() == (
        qt_widgets.QSizePolicy.Policy.Expanding
    )

    dialog.fade_rows.setChecked(False)
    assert dialog.fade_delay.isEnabled() is False
    assert dialog.reveal_faded_rows_on_hover.isEnabled() is False
    dialog.fade_rows.setChecked(True)
    assert dialog.fade_delay.isEnabled() is True
    assert dialog.reveal_faded_rows_on_hover.isEnabled() is True

    dialog.close()
    app.processEvents()
