import importlib
from pathlib import Path

import pytest

qt_core = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
QPoint = qt_core.QPoint
QSettings = qt_core.QSettings
QSize = qt_core.QSize
settings_module = importlib.import_module("eql_combat_feed.settings")
OverlayPreferences = settings_module.OverlayPreferences
SettingsStore = settings_module.SettingsStore


def test_settings_round_trip_split_window_configuration(tmp_path: Path) -> None:
    log = tmp_path / "eqlog_Hero_freeport.txt"
    preferences = OverlayPreferences(
        max_rows=8,
        history_rows=250,
        font_scale=1.55,
        encounter_timeout=14,
        show_pet=False,
        auto_quit_with_game=True,
        minimize_to_tray=True,
        locked=True,
        position=QPoint(321, 654),
        size=QSize(900, 500),
        pet_position=QPoint(1250, 654),
        pet_size=QSize(500, 420),
        log_file=log,
    )

    settings_file = tmp_path / "settings.ini"
    settings = QSettings(str(settings_file), QSettings.Format.IniFormat)
    settings.setValue("window/split_geometry_migrated", True)
    store = SettingsStore(settings)
    store.save(preferences)
    loaded = SettingsStore(QSettings(str(settings_file), QSettings.Format.IniFormat)).load()

    assert loaded == preferences


def test_combined_geometry_migrates_to_two_half_width_windows_once(tmp_path: Path) -> None:
    settings_file = tmp_path / "migration.ini"
    settings = QSettings(str(settings_file), QSettings.Format.IniFormat)
    settings.setValue("window/position", QPoint(100, 200))
    settings.setValue("window/size", QSize(1568, 617))
    settings.sync()

    loaded = SettingsStore(settings).load()

    assert loaded.position == QPoint(100, 200)
    assert loaded.size == QSize(784, 617)
    assert loaded.pet_position == QPoint(908, 200)
    assert loaded.pet_size == QSize(784, 617)

    loaded_again = SettingsStore(settings).load()
    assert loaded_again.size == QSize(784, 617)
    assert loaded_again.pet_position == QPoint(908, 200)
    assert loaded_again.pet_size == QSize(784, 617)
