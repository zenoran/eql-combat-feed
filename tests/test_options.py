import importlib
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

qt_core = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
qt_widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
QPoint = qt_core.QPoint
QSize = qt_core.QSize
QApplication = qt_widgets.QApplication
OptionsDialog = importlib.import_module("eql_combat_feed.options").OptionsDialog
OverlayPreferences = importlib.import_module("eql_combat_feed.settings").OverlayPreferences


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
    dialog.show_pet.setChecked(False)
    dialog.auto_quit_with_game.setChecked(True)
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
    assert result.show_pet is False
    assert result.auto_quit_with_game is True
    assert result.minimize_to_tray is True
    assert result.locked is True
    assert result.position == current.position
    assert result.size == current.size
    assert result.pet_position == current.pet_position
    assert result.pet_size == current.pet_size
    assert result.log_file == log
    dialog.close()
    app.processEvents()
