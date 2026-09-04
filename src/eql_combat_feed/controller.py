"""Application orchestration: watcher, parser, split feeds, tray, and preferences."""

import logging
import os
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox, QSystemTrayIcon

from . import __version__
from .dps import EncounterDpsMeter
from .hotkey import GlobalHotkey, GlobalLockHotkey, GlobalWheelCapture
from .options import OptionsDialog
from .overlay import Actor, CombatFeedOverlay
from .parser import EqlCombatParser, character_name_from_log
from .process_monitor import (
    GameProcessEvent,
    GameProcessTracker,
    foreground_pid,
    is_game_running,
    pid_matches_process,
)
from .search_window import LogSearchWindow
from .settings import SettingsStore
from .update_check import UpdateChecker
from .watcher import LogWatcher, discover_log_file, read_recent_lines
from .window import ControlWindow

LOG = logging.getLogger(__name__)

LOG_POLL_INTERVAL_MS = 50
POLL_FAILURE_REOPEN_SECONDS = 1.0


class CombatFeedController(QObject):
    def __init__(
        self,
        app: QApplication,
        requested_log: str | None = None,
        settings: SettingsStore | None = None,
        *,
        dev_mode: bool = False,
    ) -> None:
        super().__init__()
        self.app = app
        self.dev_mode = dev_mode
        self.app_name = "EQL Combat Feed DEV" if dev_mode else "EQL Combat Feed"
        self.app.setQuitOnLastWindowClosed(False)
        self.settings = settings or SettingsStore()
        self.preferences = self.settings.load()
        self.you_overlay = CombatFeedOverlay(self.preferences, "character")
        self.pet_overlay = CombatFeedOverlay(self.preferences, "pet")
        self.overlay = self.you_overlay  # Backwards-compatible primary-window alias.
        self.parser: EqlCombatParser | None = None
        self.watcher: LogWatcher | None = None
        self.log_path: Path | None = None
        self.dps_meter = EncounterDpsMeter(self.preferences.encounter_timeout)
        self.game_tracker = GameProcessTracker()
        self._game_exit_prompt_open = False
        self._poll_failures = 0
        self._overlays_hidden = False
        self.update_checker = UpdateChecker(__version__, self)
        self.update_checker.update_available.connect(self._on_update_available)

        self.app_icon = self._make_icon()
        self.app.setWindowIcon(self.app_icon)
        self.window = ControlWindow(self.preferences, self.app_icon, dev_mode=dev_mode)
        self.window.quit_requested.connect(self.shutdown)
        self.window.lock_changed.connect(self.set_locked)
        self.window.pet_visibility_changed.connect(self.set_show_pet)
        self.window.auto_quit_changed.connect(self.set_auto_quit_with_game)
        self.window.options_requested.connect(self.show_options)
        self.window.choose_log_requested.connect(self.choose_log)
        self.window.clear_requested.connect(self.clear)
        self.search_window = LogSearchWindow(self.settings)
        self.search_window.setWindowIcon(self.app_icon)

        self.tray = QSystemTrayIcon(self.app_icon, self.app)
        self.tray.setToolTip(self.app_name)
        self.tray.setContextMenu(self._build_menu())
        self.tray.activated.connect(self._on_tray_activated)

        self._connect_overlay(self.you_overlay, "character")
        self._connect_overlay(self.pet_overlay, "pet")

        self.poll_timer = QTimer(self)
        self.poll_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.poll_timer.setInterval(LOG_POLL_INTERVAL_MS)
        self.poll_timer.timeout.connect(self._poll_log)
        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(50)
        self.animation_timer.timeout.connect(self._tick)
        self.process_timer = QTimer(self)
        self.process_timer.setInterval(2000)
        self.process_timer.timeout.connect(self._poll_game_process)
        self.focus_timer = QTimer(self)
        self.focus_timer.setInterval(500)
        self.focus_timer.timeout.connect(self._poll_focus)

        self.hotkey = GlobalLockHotkey(self.toggle_locked)
        self.app.installNativeEventFilter(self.hotkey)
        self.hotkey.register()
        self.search_hotkey = GlobalHotkey(
            self.search_window.toggle,
            keys=(GlobalHotkey.VK_CONTROL, GlobalHotkey.VK_MENU, ord("G")),
        )
        self.app.installNativeEventFilter(self.search_hotkey)
        self.search_hotkey.register()
        self.wheel_capture = GlobalWheelCapture(self._route_locked_wheel)
        self.wheel_capture.register()

        self._place_overlays()
        self.set_locked(self.preferences.locked, notify=False)
        self.you_overlay.show()
        self._apply_pet_visibility()
        self.window.show()
        self.tray.show()
        self.animation_timer.start()
        self.process_timer.start()
        self.focus_timer.start()
        self._requested_log = requested_log or self.preferences.log_file
        QTimer.singleShot(0, self._finish_startup)

    def _finish_startup(self) -> None:
        self._poll_game_process()
        self.open_log(self._requested_log)
        if self.preferences.check_updates and not self.dev_mode:
            QTimer.singleShot(3000, self.update_checker.check)

    def _connect_overlay(self, overlay: CombatFeedOverlay, actor: Actor) -> None:
        overlay.context_requested.connect(self._show_menu)
        overlay.options_requested.connect(self.show_options)
        overlay.quit_requested.connect(self.shutdown)
        overlay.position_changed.connect(
            lambda point, actor=actor: self._save_position(actor, point)
        )
        overlay.size_changed.connect(lambda size, actor=actor: self._save_size(actor, size))

    def shutdown(self) -> None:
        self.poll_timer.stop()
        self.animation_timer.stop()
        self.process_timer.stop()
        self.focus_timer.stop()
        if self.watcher:
            self.watcher.close()
        self.hotkey.unregister()
        self.search_hotkey.unregister()
        self.wheel_capture.unregister()
        self.search_window.shutdown()
        self.tray.hide()
        self.window.allow_close()
        self.window.close()
        self.you_overlay.close()
        self.pet_overlay.close()
        self.app.quit()

    def open_log(self, requested: str | Path | None = None) -> None:
        path = discover_log_file(requested)
        if path is None:
            LOG.warning("No EQL log found (requested=%r)", requested)
            self._set_status("No EQL log found — right-click to choose one", error=True)
            self.poll_timer.stop()
            return
        try:
            watcher = LogWatcher(path, self._handle_line)
            watcher.start(from_end=True)
        except OSError as error:
            LOG.exception("Unable to open EQL log")
            self._set_status(f"Cannot open {path.name}: {error}", error=True)
            self.poll_timer.stop()
            return

        if self.watcher:
            self.watcher.close()
        self.log_path = path
        self.watcher = watcher
        self.parser = EqlCombatParser(character_name_from_log(path))
        self.window.set_log_path(path)
        self.search_window.set_log_path(path)
        self.dps_meter.reset()
        self._update_dps_displays()
        self._prime_parser_state(path)
        self._update_haste_displays()
        self.preferences.log_file = path
        self.settings.save_log_file(path)
        self._set_status(f"Watching {path.name}")
        self.tray.setToolTip(f"{self.app_name}\n{path.name}")
        self._poll_failures = 0
        self.poll_timer.start()
        LOG.info("Watching %s", path)

    def choose_log(self) -> None:
        initial = str(self.log_path.parent if self.log_path else Path.home())
        selected, _ = QFileDialog.getOpenFileName(
            self.window,
            "Choose EverQuest log",
            initial,
            "EverQuest logs (eqlog_*.txt);;Text files (*.txt);;All files (*)",
        )
        if selected:
            self.open_log(selected)

    def toggle_locked(self) -> None:
        self.set_locked(not self.you_overlay.locked)

    def set_locked(self, locked: bool, *, notify: bool = True) -> None:
        self.you_overlay.set_locked(locked)
        self.pet_overlay.set_locked(locked)
        self.preferences.locked = locked
        self.settings.save_locked(locked)
        self.lock_action.setChecked(locked)
        self.window.sync_preferences(self.preferences)
        if notify:
            mode = "Locked — Ctrl+Alt+L to unlock" if locked else "Move mode — drag either window"
            self.tray.showMessage(
                self.app_name, mode, QSystemTrayIcon.MessageIcon.Information, 1200
            )

    def show_options(self) -> None:
        dialog = OptionsDialog(self.preferences, self.window)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        updated = dialog.result_preferences(self.preferences)
        previous_log = self.log_path
        previous_timeout = self.preferences.encounter_timeout
        self.preferences = updated
        self.you_overlay.apply_preferences(updated)
        self.pet_overlay.apply_preferences(updated)
        if updated.encounter_timeout != previous_timeout:
            self.dps_meter.inactivity_seconds = updated.encounter_timeout
        self._capture_geometry()
        self.settings.save(updated)
        self.lock_action.setChecked(updated.locked)
        self.show_pet_action.setChecked(updated.show_pet)
        self._apply_pet_visibility()
        self.window.sync_preferences(updated)
        if updated.log_file and updated.log_file != previous_log:
            self.open_log(updated.log_file)

    def set_show_pet(self, visible: bool) -> None:
        self.preferences.show_pet = visible
        self.show_pet_action.setChecked(visible)
        self._apply_pet_visibility()
        self._capture_geometry()
        self.settings.save(self.preferences)
        self.window.sync_preferences(self.preferences)

    def set_auto_quit_with_game(self, enabled: bool) -> None:
        self.preferences.auto_quit_with_game = enabled
        self.settings.save(self.preferences)
        self.window.sync_preferences(self.preferences)

    def _apply_pet_visibility(self) -> None:
        self._apply_overlay_visibility()

    def _apply_overlay_visibility(self) -> None:
        visible = not self._overlays_hidden
        self.you_overlay.setVisible(visible)
        self.pet_overlay.setVisible(visible and self.preferences.show_pet)

    def _poll_focus(self) -> None:
        hidden = self._should_hide_overlays()
        if hidden != self._overlays_hidden:
            self._overlays_hidden = hidden
            self._apply_overlay_visibility()

    def _should_hide_overlays(self) -> bool:
        """Hide the overlays unless EverQuest or this app is foreground.

        A closed game is the ultimate form of unfocused, so the overlays are
        hidden then too. Focusing the feed itself (control window, options,
        or an overlay) always shows them so they can be dragged, resized,
        and configured — including before the game has ever launched.
        """
        if not self.preferences.hide_when_unfocused:
            return False
        pid = foreground_pid()
        if pid is None or pid == os.getpid():
            return False
        return not pid_matches_process(pid)

    def _on_update_available(self, version: str, url: str) -> None:
        self.window.show_update_available(version, url)
        self.tray.showMessage(
            self.app_name,
            f"Update v{version} is available — open the control window to download.",
            QSystemTrayIcon.MessageIcon.Information,
            6000,
        )

    def _save_position(self, actor: Actor, point: QPoint) -> None:
        if actor == "character":
            self.preferences.position = point
            self.settings.save_position(point)
        else:
            self.preferences.pet_position = point
            self.settings.save_pet_position(point)

    def _save_size(self, actor: Actor, size) -> None:  # type: ignore[no-untyped-def]
        if actor == "character":
            self.preferences.size = size
            self.settings.save_size(size)
        else:
            self.preferences.pet_size = size
            self.settings.save_pet_size(size)

    def _capture_geometry(self) -> None:
        self.preferences.position = self.you_overlay.pos()
        self.preferences.size = self.you_overlay.size()
        self.preferences.pet_position = self.pet_overlay.pos()
        self.preferences.pet_size = self.pet_overlay.size()

    def clear(self) -> None:
        self.you_overlay.clear_entries()
        self.pet_overlay.clear_entries()
        self.dps_meter.reset()
        self._update_dps_displays()
        self._set_status(f"Watching {self.log_path.name}" if self.log_path else "Waiting for log…")

    def show_about(self) -> None:
        QMessageBox.information(
            self.window,
            self.app_name,
            "Separate YOU and PET outgoing-damage windows for EverQuest Legends.\n\n"
            "Move and resize either window independently.\n"
            "Disable the Pet window in Options for classes without pets.\n"
            "Use Ctrl+Alt+L to toggle locked click-through mode.",
        )

    def _handle_line(self, line: str) -> None:
        if self.parser is None:
            return
        changed = False
        observed_at = monotonic()
        before_haste = (
            self.parser.haste_state("character"),
            self.parser.haste_state("pet"),
        )
        for event in self.parser.parse_line(line):
            changed |= self.dps_meter.add(event, observed_at)
            actor = CombatFeedOverlay._actor_for_event(event)
            if actor == "character":
                self.you_overlay.add_event(event)
            elif actor == "pet":
                # Hidden Pet windows still retain history but never show themselves.
                self.pet_overlay.add_event(event)
        after_haste = (
            self.parser.haste_state("character"),
            self.parser.haste_state("pet"),
        )
        if after_haste != before_haste:
            self._update_haste_displays()
        if changed:
            self._update_dps_displays()

    def _update_dps_displays(self) -> None:
        self.you_overlay.set_dps(self.dps_meter.snapshot("character"))
        self.pet_overlay.set_dps(self.dps_meter.snapshot("pet"))

    def _update_haste_displays(self) -> None:
        if self.parser is None:
            return
        self.you_overlay.set_haste_state(self.parser.haste_state("character"))
        self.pet_overlay.set_haste_state(self.parser.haste_state("pet"))

    def _route_locked_wheel(self, x: int, y: int, steps: int) -> bool:
        """Consume hooked wheel notches over a visible locked overlay.

        Unlocked overlays receive wheel events natively, so the hook leaves
        them (and every other window on the system) alone.
        """
        point = QPoint(x, y)
        for overlay in (self.you_overlay, self.pet_overlay):
            if overlay.isVisible() and overlay.locked and overlay.frameGeometry().contains(point):
                overlay.scroll_history(steps)
                return True
        return False

    def _set_status(self, message: str, *, error: bool = False) -> None:
        self.you_overlay.set_status(message, error=error)
        self.pet_overlay.set_status(message, error=error)
        self.window.set_status(message, error=error)

    def _prime_parser_state(self, path: Path) -> None:
        if self.parser is None:
            return
        try:
            # Pet ownership and haste are stateful. Replay chronologically so a
            # later fade, death, replacement, or zone transition wins over older
            # landing/ownership lines without emitting historical combat rows.
            for line in read_recent_lines(path):
                self.parser.parse_line(line)
        except OSError:
            LOG.exception("Unable to scan recent log for parser state")

    # Keep read-error recovery near one second even if the poll cadence changes.
    POLL_FAILURE_REOPEN_THRESHOLD = round(
        POLL_FAILURE_REOPEN_SECONDS * 1000 / LOG_POLL_INTERVAL_MS
    )

    def _poll_log(self) -> None:
        """Poll the log, riding out transient read errors instead of dying.

        On Windows, antivirus scans, recording software, and the game itself
        can briefly lock the log and fail a single read. That must NEVER
        permanently stop the feed — we retry forever, forcing a clean reopen
        after each ~1s of continuous failure, and restore the status line as
        soon as a poll succeeds again.
        """
        if self.watcher is None:
            return
        try:
            self.watcher.poll()
        except OSError as error:
            self._poll_failures += 1
            if self._poll_failures == 1:
                LOG.exception("Log watcher poll failed; retrying")
            if self._poll_failures % self.POLL_FAILURE_REOPEN_THRESHOLD == 0:
                LOG.warning(
                    "Log still unreadable after %d attempts (%s); reopening",
                    self._poll_failures,
                    error,
                )
                self._set_status(f"Log read hiccup — retrying ({error})", error=True)
                self.watcher.close()  # next poll reopens from scratch
            return
        if self._poll_failures:
            LOG.info("Log reads recovered after %d failed polls", self._poll_failures)
            self._poll_failures = 0
            self._set_status(
                f"Watching {self.log_path.name}" if self.log_path else "Watching log"
            )

    def _poll_game_process(self) -> None:
        observed_running = is_game_running()
        event = self.game_tracker.observe(observed_running)
        self.window.set_game_running(
            self.game_tracker.running,
            seen_running=self.game_tracker.seen_running,
        )
        if event is GameProcessEvent.STOPPED:
            self._handle_game_stopped()

    def _handle_game_stopped(self) -> None:
        if self._game_exit_prompt_open:
            return
        if self.preferences.auto_quit_with_game:
            self.shutdown()
            return
        self._game_exit_prompt_open = True
        try:
            answer = QMessageBox.question(
                self.window,
                "EverQuest closed",
                "EverQuest is no longer running. Quit EQL Combat Feed too?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
        finally:
            self._game_exit_prompt_open = False
        # `==`, never `is`: QMessageBox.question returns a plain int (e.g.
        # 16384), so identity against the enum member is always False and
        # every answer would fall into the "keep running" branch.
        if answer == QMessageBox.StandardButton.Yes:
            self.shutdown()
        else:
            self.window.show_and_raise()

    def _tick(self) -> None:
        if self.dps_meter.tick(monotonic()):
            self._update_dps_displays()
        self.you_overlay.tick()
        self.pet_overlay.tick()

    def _build_menu(self) -> QMenu:
        menu = QMenu()
        self.lock_action = QAction("Locked / click-through", menu)
        self.lock_action.setCheckable(True)
        self.lock_action.triggered.connect(self.set_locked)
        menu.addAction(self.lock_action)

        self.show_pet_action = QAction("Show Pet window", menu)
        self.show_pet_action.setCheckable(True)
        self.show_pet_action.setChecked(self.preferences.show_pet)
        self.show_pet_action.triggered.connect(self.set_show_pet)
        menu.addAction(self.show_pet_action)

        menu.addAction("Open control window", self.window.show_and_raise)
        menu.addAction("Options…", self.show_options)
        menu.addAction("Choose log…", self.choose_log)
        menu.addAction("Clear feeds", self.clear)
        menu.addSeparator()
        menu.addAction("About", self.show_about)
        menu.addAction(f"Quit {self.app_name}", self.shutdown)
        return menu

    def _show_menu(self, point) -> None:  # type: ignore[no-untyped-def]
        menu = self.tray.contextMenu()
        if menu:
            menu.popup(point)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.window.show_and_raise()

    def _place_overlays(self) -> None:
        screen = self.app.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        you_position = self._visible_saved_position(self.preferences.position)
        if you_position is None:
            you_position = QPoint(
                area.right() - self.you_overlay.width() - 30,
                area.bottom() - self.you_overlay.height() - 130,
            )
        self.you_overlay.move(you_position)

        pet_position = self._visible_saved_position(self.preferences.pet_position)
        if pet_position is None:
            pet_position = QPoint(
                max(area.left() + 20, you_position.x() - self.pet_overlay.width() - 24),
                you_position.y(),
            )
        self.pet_overlay.move(pet_position)
        self._capture_geometry()

    def _visible_saved_position(self, candidate: QPoint | None) -> QPoint | None:
        if candidate is None:
            return None
        visible = any(
            screen.availableGeometry().adjusted(-80, -80, 80, 80).contains(candidate)
            for screen in self.app.screens()
        )
        return candidate if visible else None

    @staticmethod
    def _make_icon() -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#17191e"))
        painter.setPen(QColor("#d7a95f"))
        painter.drawRoundedRect(3, 3, 58, 58, 12, 12)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "⚔")
        painter.end()
        return QIcon(pixmap)
