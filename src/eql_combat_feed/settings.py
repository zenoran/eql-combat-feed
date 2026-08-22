"""Persistent user preferences."""

from dataclasses import asdict, dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QSettings, QSize


@dataclass(slots=True)
class OverlayPreferences:
    max_rows: int = 5
    history_rows: int = 100
    font_scale: float = 1.3
    encounter_timeout: int = 10
    show_pet: bool = True
    auto_quit_with_game: bool = False
    locked: bool = False
    position: QPoint | None = None
    size: QSize | None = None
    pet_position: QPoint | None = None
    pet_size: QSize | None = None
    log_file: Path | None = None


class SettingsStore:
    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings or QSettings("zenoran", "EQL Combat Feed")

    def load(self) -> OverlayPreferences:
        position = self._settings.value("window/position")
        size = self._settings.value("window/size")
        pet_position = self._settings.value("pet_window/position")
        pet_size = self._settings.value("pet_window/size")
        log_file = self._settings.value("log/file", "", str)
        preferences = OverlayPreferences(
            max_rows=self._bounded_int("display/max_rows", 5, 3, 8),
            history_rows=self._bounded_int("display/history_rows", 100, 10, 1000),
            font_scale=self._bounded_float("display/font_scale", 1.3, 0.6, 2.0),
            encounter_timeout=self._bounded_int("display/encounter_timeout", 10, 3, 60),
            show_pet=self._settings.value("display/show_pet", True, bool),
            auto_quit_with_game=self._settings.value("app/auto_quit_with_game", False, bool),
            locked=self._settings.value("window/locked", False, bool),
            position=position if isinstance(position, QPoint) else None,
            size=size if isinstance(size, QSize) else None,
            pet_position=pet_position if isinstance(pet_position, QPoint) else None,
            pet_size=pet_size if isinstance(pet_size, QSize) else None,
            log_file=Path(log_file) if log_file else None,
        )
        self._migrate_combined_geometry(preferences)
        return preferences

    def save(self, preferences: OverlayPreferences) -> None:
        values = asdict(preferences)
        for field, value in values.items():
            if field in {"position", "size"}:
                self._settings.setValue(f"window/{field}", value)
            elif field in {"pet_position", "pet_size"}:
                key = field.removeprefix("pet_")
                self._settings.setValue(f"pet_window/{key}", value)
            elif field == "locked":
                self._settings.setValue("window/locked", value)
            elif field == "auto_quit_with_game":
                self._settings.setValue("app/auto_quit_with_game", value)
            elif field == "log_file":
                self._settings.setValue("log/file", str(value) if value else "")
            else:
                self._settings.setValue(f"display/{field}", value)
        self._settings.setValue("window/split_geometry_migrated", True)
        self._settings.sync()

    def save_position(self, point: QPoint) -> None:
        self._settings.setValue("window/position", point)
        self._settings.sync()

    def save_size(self, size: QSize) -> None:
        self._settings.setValue("window/size", size)
        self._settings.sync()

    def save_pet_position(self, point: QPoint) -> None:
        self._settings.setValue("pet_window/position", point)
        self._settings.sync()

    def save_pet_size(self, size: QSize) -> None:
        self._settings.setValue("pet_window/size", size)
        self._settings.sync()

    def save_locked(self, locked: bool) -> None:
        self._settings.setValue("window/locked", locked)
        self._settings.sync()

    def save_log_file(self, path: Path) -> None:
        self._settings.setValue("log/file", str(path))
        self._settings.sync()

    def _migrate_combined_geometry(self, preferences: OverlayPreferences) -> None:
        if self._settings.value("window/split_geometry_migrated", False, bool):
            return
        if preferences.size is not None:
            half_width = max(360, preferences.size.width() // 2)
            split_size = QSize(half_width, preferences.size.height())
            preferences.size = split_size
            preferences.pet_size = split_size
        if preferences.position is not None:
            gap = 24
            pet_x = (
                preferences.position.x()
                + (preferences.size.width() if preferences.size else 600)
                + gap
            )
            preferences.pet_position = QPoint(pet_x, preferences.position.y())
        self._settings.setValue("window/position", preferences.position)
        self._settings.setValue("window/size", preferences.size)
        self._settings.setValue("pet_window/position", preferences.pet_position)
        self._settings.setValue("pet_window/size", preferences.pet_size)
        self._settings.setValue("window/split_geometry_migrated", True)
        self._settings.sync()

    def _bounded_int(self, key: str, default: int, minimum: int, maximum: int) -> int:
        value = self._settings.value(key, default, int)
        return max(minimum, min(maximum, value))

    def _bounded_float(self, key: str, default: float, minimum: float, maximum: float) -> float:
        value = self._settings.value(key, default, float)
        return max(minimum, min(maximum, value))
