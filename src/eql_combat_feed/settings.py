"""Persistent user preferences."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QPoint, QSettings, QSize

from .hotkey import chord_from_sequence, default_lock_hotkey, default_search_hotkey


@dataclass(slots=True)
class OverlayPreferences:
    max_rows: int = 5
    history_rows: int = 100
    damage_font_size: float = 16.0
    header_font_size: float = 16.0
    encounter_timeout: int = 10
    fade_rows: bool = True
    fade_delay: int = 10
    reveal_faded_rows_on_hover: bool = True
    show_resists: bool = True
    show_pet: bool = True
    # Mirrored feeds lay out amount → icon → description (numbers on the
    # LEFT). Placed beside an unmirrored feed, the two number lanes meet
    # back-to-back in the middle and descriptions grow outward. PET defaults
    # mirrored because the stock arrangement puts it to the right of YOU.
    mirror_character: bool = False
    mirror_pet: bool = True
    auto_quit_with_game: bool = False
    launch_eq_on_startup: bool = False
    minimize_to_tray: bool = False
    hide_when_unfocused: bool = True
    check_updates: bool = True
    locked: bool = False
    # Portable Qt key-sequence text (``Ctrl+Alt+L``); validated on load and
    # replaced by the platform default when empty or unsupported.
    lock_hotkey: str = field(default_factory=default_lock_hotkey)
    search_hotkey: str = field(default_factory=default_search_hotkey)
    position: QPoint | None = None
    size: QSize | None = None
    pet_position: QPoint | None = None
    pet_size: QSize | None = None
    log_file: Path | None = None


@dataclass(frozen=True, slots=True)
class LogSearchHistoryEntry:
    include: str
    exclude: str = ""
    lookback_seconds: int | None = 24 * 60 * 60
    match_case: bool = False


class SettingsStore:
    SEARCH_HISTORY_LIMIT = 20

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings or QSettings("zenoran", "EQL Combat Feed")

    @classmethod
    def for_profile(cls, *, dev_mode: bool = False) -> "SettingsStore":
        application = "EQL Combat Feed DEV" if dev_mode else "EQL Combat Feed"
        return cls(QSettings("zenoran", application))

    def load(self) -> OverlayPreferences:
        position = self._settings.value("window/position")
        size = self._settings.value("window/size")
        pet_position = self._settings.value("pet_window/position")
        pet_size = self._settings.value("pet_window/size")
        log_file = self._settings.value("log/file", "", str)
        damage_font_size, header_font_size = self._font_sizes()
        preferences = OverlayPreferences(
            max_rows=self._bounded_int("display/max_rows", 5, 3, 20),
            history_rows=self._bounded_int("display/history_rows", 100, 10, 1000),
            damage_font_size=damage_font_size,
            header_font_size=header_font_size,
            encounter_timeout=self._bounded_int("display/encounter_timeout", 10, 3, 60),
            fade_rows=self._settings.value("display/fade_rows", True, bool),
            fade_delay=self._bounded_int("display/fade_delay", 10, 3, 120),
            reveal_faded_rows_on_hover=self._settings.value(
                "display/reveal_faded_rows_on_hover", True, bool
            ),
            show_resists=self._settings.value("display/show_resists", True, bool),
            show_pet=self._settings.value("display/show_pet", True, bool),
            mirror_character=self._settings.value("display/mirror_character", False, bool),
            mirror_pet=self._settings.value("display/mirror_pet", True, bool),
            auto_quit_with_game=self._settings.value("app/auto_quit_with_game", False, bool),
            launch_eq_on_startup=self._settings.value("app/launch_eq_on_startup", False, bool),
            minimize_to_tray=self._settings.value("app/minimize_to_tray", False, bool),
            hide_when_unfocused=self._settings.value("app/hide_when_unfocused", True, bool),
            check_updates=self._settings.value("app/check_updates", True, bool),
            locked=self._settings.value("window/locked", False, bool),
            lock_hotkey=self._hotkey("hotkeys/lock", default_lock_hotkey()),
            search_hotkey=self._hotkey("hotkeys/search", default_search_hotkey()),
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
        for name, value in values.items():
            if name in {"position", "size"}:
                self._settings.setValue(f"window/{name}", value)
            elif name in {"pet_position", "pet_size"}:
                key = name.removeprefix("pet_")
                self._settings.setValue(f"pet_window/{key}", value)
            elif name == "locked":
                self._settings.setValue("window/locked", value)
            elif name in {"lock_hotkey", "search_hotkey"}:
                self._settings.setValue(f"hotkeys/{name.removesuffix('_hotkey')}", value)
            elif name == "auto_quit_with_game":
                self._settings.setValue("app/auto_quit_with_game", value)
            elif name == "launch_eq_on_startup":
                self._settings.setValue("app/launch_eq_on_startup", value)
            elif name == "minimize_to_tray":
                self._settings.setValue("app/minimize_to_tray", value)
            elif name == "hide_when_unfocused":
                self._settings.setValue("app/hide_when_unfocused", value)
            elif name == "check_updates":
                self._settings.setValue("app/check_updates", value)
            elif name == "log_file":
                self._settings.setValue("log/file", str(value) if value else "")
            else:
                self._settings.setValue(f"display/{name}", value)
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

    def load_search_history(self) -> list[LogSearchHistoryEntry]:
        raw = self._settings.value("search/history", "", str)
        if not raw:
            return []
        try:
            values = json.loads(raw)
            history = [
                LogSearchHistoryEntry(
                    include=value["include"],
                    exclude=value.get("exclude", ""),
                    lookback_seconds=value.get("lookback_seconds"),
                    match_case=bool(value.get("match_case", False)),
                )
                for value in values
                if (
                    isinstance(value, dict)
                    and isinstance(value.get("include"), str)
                    and value["include"]
                    and isinstance(value.get("exclude", ""), str)
                    and (
                        value.get("lookback_seconds") is None
                        or isinstance(value.get("lookback_seconds"), int)
                    )
                )
            ]
        except (json.JSONDecodeError, TypeError, KeyError):
            return []
        normalized = self._unique_search_history(history)
        if normalized != history:
            self.save_search_history(normalized)
        return normalized

    def save_search_history(self, history: list[LogSearchHistoryEntry]) -> None:
        payload = [asdict(entry) for entry in self._unique_search_history(history)]
        self._settings.setValue("search/history", json.dumps(payload))
        self._settings.sync()

    def _unique_search_history(
        self, history: list[LogSearchHistoryEntry]
    ) -> list[LogSearchHistoryEntry]:
        unique: list[LogSearchHistoryEntry] = []
        seen: set[tuple[str, str]] = set()
        for entry in history:
            key = (entry.include.strip(), entry.exclude.strip())
            if key in seen:
                continue
            seen.add(key)
            unique.append(entry)
            if len(unique) == self.SEARCH_HISTORY_LIMIT:
                break
        return unique

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

    def _font_sizes(self) -> tuple[float, float]:
        damage = self._settings.value("display/damage_font_size")
        header = self._settings.value("display/header_font_size")
        if damage is not None and header is not None:
            return (
                self._bounded_float("display/damage_font_size", 16.0, 13.0, 42.0),
                self._bounded_float("display/header_font_size", 16.0, 10.0, 36.0),
            )

        # Migrate the former percentage controls without a visual jump.
        old_damage_scale = self._bounded_float("display/font_scale", 1.3, 0.6, 2.0)
        old_header_scale = self._bounded_float("display/header_scale", 1.1, 0.5, 1.25)
        damage_size = 21.0 * old_damage_scale
        header_size = 16.8 * old_header_scale * old_damage_scale
        self._settings.setValue("display/damage_font_size", damage_size)
        self._settings.setValue("display/header_font_size", header_size)
        self._settings.sync()
        return damage_size, header_size

    def _hotkey(self, key: str, default: str) -> str:
        value = self._settings.value(key, "", str).strip()
        return value if value and chord_from_sequence(value) else default

    def _bounded_int(self, key: str, default: int, minimum: int, maximum: int) -> int:
        value = self._settings.value(key, default, int)
        return max(minimum, min(maximum, value))

    def _bounded_float(self, key: str, default: float, minimum: float, maximum: float) -> float:
        value = self._settings.value(key, default, float)
        return max(minimum, min(maximum, value))
