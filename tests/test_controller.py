import importlib
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

qt_core = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
qt_test = pytest.importorskip("PySide6.QtTest", exc_type=ImportError)
qt_widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
QApplication = qt_widgets.QApplication
QPoint = qt_core.QPoint
QSettings = qt_core.QSettings
QSize = qt_core.QSize
Qt = qt_core.Qt
QTest = qt_test.QTest

controller_module = importlib.import_module("eql_combat_feed.controller")
CombatFeedController = controller_module.CombatFeedController
LOG_POLL_INTERVAL_MS = controller_module.LOG_POLL_INTERVAL_MS
HasteState = importlib.import_module("eql_combat_feed.models").HasteState
SettingsStore = importlib.import_module("eql_combat_feed.settings").SettingsStore


def make_controller(tmp_path: Path, *, show_pet: bool = True):
    app = QApplication.instance() or QApplication([])
    log = tmp_path / "eqlog_Hero_freeport.txt"
    log.write_text("", encoding="utf-8")
    raw = QSettings(str(tmp_path / "controller.ini"), QSettings.Format.IniFormat)
    raw.setValue("display/show_pet", show_pet)
    raw.setValue("window/split_geometry_migrated", True)
    raw.sync()
    settings = SettingsStore(raw)
    controller = CombatFeedController(app, requested_log=str(log), settings=settings)
    app.processEvents()
    return app, log, settings, controller


def test_log_poll_timer_uses_low_latency_precise_cadence(tmp_path: Path) -> None:
    _, _, _, controller = make_controller(tmp_path)

    assert controller.poll_timer.interval() == LOG_POLL_INTERVAL_MS == 50
    assert controller.poll_timer.timerType() == Qt.TimerType.PreciseTimer
    assert controller.POLL_FAILURE_REOPEN_THRESHOLD == 20

    stop_controller(controller)


def test_control_window_is_visible_before_deferred_log_startup(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    log = tmp_path / "eqlog_Hero_freeport.txt"
    log.write_text("", encoding="utf-8")
    settings = SettingsStore(
        QSettings(str(tmp_path / "deferred.ini"), QSettings.Format.IniFormat)
    )
    controller = CombatFeedController(app, requested_log=str(log), settings=settings)

    assert controller.window.isVisible()
    assert controller.watcher is None

    app.processEvents()
    assert controller.watcher is not None

    stop_controller(controller)


def stop_controller(controller: CombatFeedController) -> None:
    controller.poll_timer.stop()
    controller.animation_timer.stop()
    controller.process_timer.stop()
    if controller.watcher:
        controller.watcher.close()
    controller.hotkey.unregister()
    controller.search_hotkey.unregister()
    controller.search_window.shutdown()
    controller.wheel_capture.unregister()
    controller.tray.hide()
    controller.window.allow_close()
    controller.window.close()
    controller.you_overlay.close()
    controller.pet_overlay.close()


def test_controller_routes_live_damage_to_separate_windows(tmp_path: Path) -> None:
    app, log, settings, controller = make_controller(tmp_path)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(
            "[Sat Aug 22 10:13:21 2026] A skeleton told you, 'Attacking a goblin Master.'\n"
        )
        handle.write("[Sat Aug 22 10:13:22 2026] You slash a skeleton for 122 points of damage.\n")
        handle.write(
            "[Sat Aug 22 10:13:22 2026] You hit a skeleton for 120 points of magic "
            "damage by Reaving Strike.\n"
        )
        handle.write(
            "[Sat Aug 22 10:13:22 2026] A skeleton bashes a goblin for 33 points of damage.\n"
        )
        handle.write("[Sat Aug 22 10:13:23 2026] A skeleton punches YOU for 3 points of damage.\n")
        handle.write("[Sat Aug 22 10:13:23 2026] You healed Hero for 40 hit points by Lifedraw.\n")
        handle.write(
            "[Sat Aug 22 10:13:24 2026] A goblin is pierced by YOUR thorns for 9 points "
            "of non-melee damage.\n"
        )

    controller._poll_log()
    app.processEvents()

    assert [item.event.amount for item in controller.you_overlay.entries] == [122, 120]
    assert [item.event.ability for item in controller.you_overlay.entries] == [
        "Melee",
        "Reaving Strike",
    ]
    assert [item.event.amount for item in controller.pet_overlay.entries] == [33]
    assert controller.you_overlay._dps.damage == 242
    assert controller.pet_overlay._dps.damage == 33
    assert controller.you_overlay._dps.duration == controller.pet_overlay._dps.duration == 1.0
    assert controller.overlay is controller.you_overlay
    assert controller.you_overlay is not controller.pet_overlay
    assert controller.window.isVisible()
    assert controller.window.log_value.text() == str(log)
    assert controller.search_window.isHidden()
    assert controller.search_window.log_path == log
    assert controller.search_hotkey.keys[-1] == ord("G")

    controller._save_position("character", QPoint(100, 200))
    controller._save_size("character", QSize(800, 400))
    controller._save_position("pet", QPoint(950, 220))
    controller._save_size("pet", QSize(500, 350))
    loaded = settings.load()
    assert loaded.position == QPoint(100, 200)
    assert loaded.size == QSize(800, 400)
    assert loaded.pet_position == QPoint(950, 220)
    assert loaded.pet_size == QSize(500, 350)

    actions = [action.text() for action in controller.tray.contextMenu().actions()]
    assert "Show Pet window" in actions
    assert "Options…" in actions
    assert "Quit EQL Combat Feed" in actions

    stop_controller(controller)


def test_hidden_pet_window_accumulates_without_showing_itself(tmp_path: Path) -> None:
    app, log, settings, controller = make_controller(tmp_path, show_pet=False)
    assert controller.pet_overlay.isHidden()

    with log.open("a", encoding="utf-8") as handle:
        handle.write(
            "[Sat Aug 22 10:13:21 2026] A skeleton told you, 'Attacking a goblin Master.'\n"
        )
        handle.write(
            "[Sat Aug 22 10:13:22 2026] A skeleton bashes a goblin for 33 points of damage.\n"
        )

    controller._poll_log()
    app.processEvents()

    assert [item.event.amount for item in controller.pet_overlay.entries] == [33]
    assert controller.pet_overlay._dps.damage == 33
    assert controller.pet_overlay.isHidden()
    assert settings.load().show_pet is False

    controller.set_show_pet(True)
    app.processEvents()
    assert controller.pet_overlay.isVisible()
    assert [item.event.amount for item in controller.pet_overlay.entries] == [33]
    assert settings.load().show_pet is True

    stop_controller(controller)


def test_lock_and_controls_apply_to_both_windows(tmp_path: Path) -> None:
    app, _, _, controller = make_controller(tmp_path)
    controller.set_locked(True, notify=False)
    assert controller.you_overlay.locked is True
    assert controller.pet_overlay.locked is True
    controller.set_locked(False, notify=False)

    options_requested = []
    quit_requested = []
    controller.you_overlay.options_requested.disconnect(controller.show_options)
    controller.you_overlay.quit_requested.disconnect(controller.shutdown)
    controller.you_overlay.options_requested.connect(lambda: options_requested.append(True))
    controller.you_overlay.quit_requested.connect(lambda: quit_requested.append(True))
    controller.you_overlay._controls_visible = True
    QTest.mouseClick(
        controller.you_overlay,
        Qt.MouseButton.LeftButton,
        pos=controller.you_overlay._options_rect().center().toPoint(),
    )
    QTest.mouseClick(
        controller.you_overlay,
        Qt.MouseButton.LeftButton,
        pos=controller.you_overlay._quit_rect().center().toPoint(),
    )
    assert options_requested == [True]
    assert quit_requested == [True]

    stop_controller(controller)


def test_controller_primes_pet_identity_from_existing_log_tail(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    log = tmp_path / "eqlog_Hero_freeport.txt"
    log.write_text(
        "[Sat Aug 22 10:13:19 2026] An old pet told you, 'Attacking a goblin Master.'\n"
        "[Sat Aug 22 10:13:20 2026] A skeleton told you, 'Attacking a goblin Master.'\n",
        encoding="utf-8",
    )
    raw = QSettings(str(tmp_path / "pet-prime.ini"), QSettings.Format.IniFormat)
    raw.setValue("window/split_geometry_migrated", True)
    settings = SettingsStore(raw)
    controller = CombatFeedController(app, requested_log=str(log), settings=settings)
    app.processEvents()

    with log.open("a", encoding="utf-8") as handle:
        handle.write(
            "[Sat Aug 22 10:13:21 2026] A skeleton slashes a goblin for 41 points of damage.\n"
        )

    controller._poll_log()
    app.processEvents()

    assert controller.parser is not None
    assert controller.parser.pet_names == frozenset({"A skeleton"})
    assert [item.event.amount for item in controller.pet_overlay.entries] == [41]

    stop_controller(controller)


def test_controller_primes_and_routes_separate_haste_states(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    log = tmp_path / "eqlog_Hero_freeport.txt"
    log.write_text(
        "[Sat Aug 22 10:13:19 2026] You feel much faster.\n"
        "[Sat Aug 22 10:13:20 2026] Kobn told you, 'Attacking a goblin Master.'\n"
        "[Sat Aug 22 10:13:21 2026] Kobn feels much faster.\n",
        encoding="utf-8",
    )
    raw = QSettings(str(tmp_path / "haste-prime.ini"), QSettings.Format.IniFormat)
    raw.setValue("window/split_geometry_migrated", True)
    controller = CombatFeedController(
        app, requested_log=str(log), settings=SettingsStore(raw)
    )
    app.processEvents()

    assert controller.you_overlay._haste_state is HasteState.ACTIVE
    assert controller.pet_overlay._haste_state is HasteState.ACTIVE
    assert controller.you_overlay.entries == ()
    assert controller.pet_overlay.entries == ()

    with log.open("a", encoding="utf-8") as handle:
        handle.write("[Sat Aug 22 10:13:22 2026] Your speed returns to normal.\n")
        handle.write(
            "[Sat Aug 22 10:13:23 2026] Your pet's Alacrity spell has worn off.\n"
        )
    controller._poll_log()
    app.processEvents()

    assert controller.you_overlay._haste_state is HasteState.MISSING
    assert controller.pet_overlay._haste_state is HasteState.MISSING
    stop_controller(controller)


def test_clear_resets_histories_and_dps(tmp_path: Path) -> None:
    app, log, _, controller = make_controller(tmp_path)
    with log.open("a", encoding="utf-8") as handle:
        handle.write("[Sat Aug 22 10:13:22 2026] You slash a skeleton for 122 points of damage.\n")

    controller._poll_log()
    app.processEvents()
    assert controller.you_overlay._dps.damage == 122

    controller.clear()

    assert controller.you_overlay.entries == ()
    assert controller.pet_overlay.entries == ()
    assert controller.you_overlay._dps.damage == 0
    assert controller.pet_overlay._dps.damage == 0

    stop_controller(controller)


def test_auto_quit_setting_persists_and_game_stop_uses_shutdown(tmp_path: Path) -> None:
    app, _, settings, controller = make_controller(tmp_path)
    shutdowns = []
    controller.shutdown = lambda: shutdowns.append(True)  # type: ignore[method-assign]

    controller.set_auto_quit_with_game(True)
    controller._handle_game_stopped()

    assert settings.load().auto_quit_with_game is True
    assert controller.window.auto_quit.isChecked()
    assert shutdowns == [True]

    stop_controller(controller)


def test_game_stop_prompt_can_keep_control_window_open(tmp_path: Path, monkeypatch) -> None:
    app, _, _, controller = make_controller(tmp_path)
    controller.preferences.auto_quit_with_game = False
    monkeypatch.setattr(
        importlib.import_module("eql_combat_feed.controller").QMessageBox,
        "question",
        lambda *args, **kwargs: importlib.import_module(
            "eql_combat_feed.controller"
        ).QMessageBox.StandardButton.No,
    )

    controller._handle_game_stopped()

    assert controller.window.isVisible()
    assert controller._game_exit_prompt_open is False

    stop_controller(controller)


def test_game_stop_prompt_yes_quits_even_with_int_dialog_result(
    tmp_path: Path, monkeypatch
) -> None:
    """QMessageBox.question returns a plain int (16384), not the enum member.

    Regression: `answer is StandardButton.Yes` was always False, so hitting
    Yes restored the control window instead of quitting the app.
    """
    app, _, _, controller = make_controller(tmp_path)
    controller.preferences.auto_quit_with_game = False
    controller_module = importlib.import_module("eql_combat_feed.controller")
    yes_as_int = int(controller_module.QMessageBox.StandardButton.Yes.value)  # 16384
    monkeypatch.setattr(
        controller_module.QMessageBox, "question", lambda *args, **kwargs: yes_as_int
    )
    shutdowns = []
    controller.shutdown = lambda: shutdowns.append(True)  # type: ignore[method-assign]

    controller._handle_game_stopped()

    assert shutdowns == [True]
    stop_controller(controller)


def test_poll_log_survives_transient_read_errors_and_recovers(tmp_path: Path) -> None:
    """A burst of OSErrors (AV scan / recording lock) must never kill the feed."""
    app, _, _, controller = make_controller(tmp_path)

    threshold = controller.POLL_FAILURE_REOPEN_THRESHOLD

    class FlakyWatcher:
        def __init__(self) -> None:
            self.failures_left = threshold
            self.closes = 0
            self.polls = 0

        def poll(self) -> int:
            self.polls += 1
            if self.failures_left > 0:
                self.failures_left -= 1
                raise OSError("locked by something rude")
            return 0

        def close(self) -> None:
            self.closes += 1

    flaky = FlakyWatcher()
    controller.watcher = flaky  # type: ignore[assignment]
    controller.poll_timer.start()

    for _ in range(threshold):
        controller._poll_log()
    assert controller.poll_timer.isActive()  # never permanently stopped
    assert flaky.closes >= 1  # forced a clean reopen after ~1s of sustained failure
    assert controller._poll_failures == threshold

    controller._poll_log()  # first success
    assert controller._poll_failures == 0
    assert controller.poll_timer.isActive()

    stop_controller(controller)


def test_overlays_hide_when_game_unfocused_and_return_on_focus(
    tmp_path: Path, monkeypatch
) -> None:
    app, _, _, controller = make_controller(tmp_path)
    controller_module = importlib.import_module("eql_combat_feed.controller")
    controller.preferences.hide_when_unfocused = True
    controller.game_tracker.running = True

    # Another app owns the foreground -> hide both overlays.
    monkeypatch.setattr(controller_module, "foreground_pid", lambda: 4242)
    monkeypatch.setattr(controller_module, "pid_matches_process", lambda pid: False)
    controller._poll_focus()
    assert not controller.you_overlay.isVisible()
    assert not controller.pet_overlay.isVisible()

    # The game regains focus -> overlays return (pet obeys show_pet).
    monkeypatch.setattr(controller_module, "pid_matches_process", lambda pid: True)
    controller._poll_focus()
    assert controller.you_overlay.isVisible()
    assert controller.pet_overlay.isVisible() == controller.preferences.show_pet

    # Our own process foreground (dragging/options) -> never hidden.
    monkeypatch.setattr(controller_module, "pid_matches_process", lambda pid: False)
    monkeypatch.setattr(controller_module, "foreground_pid", lambda: __import__("os").getpid())
    controller._poll_focus()
    assert controller.you_overlay.isVisible()

    # Game closed entirely -> still hidden while another app is foreground.
    controller.game_tracker.running = False
    monkeypatch.setattr(controller_module, "foreground_pid", lambda: 4242)
    controller._poll_focus()
    assert not controller.you_overlay.isVisible()

    # Feature disabled -> always visible.
    controller.preferences.hide_when_unfocused = False
    controller._poll_focus()
    assert controller.you_overlay.isVisible()

    stop_controller(controller)


def test_update_notification_reaches_control_window(tmp_path: Path) -> None:
    app, _, _, controller = make_controller(tmp_path)
    controller._on_update_available("9.9.9", "https://example.invalid/rel")
    assert controller.window.update_label.isVisible()
    assert "9.9.9" in controller.window.update_label.text()
    stop_controller(controller)


def test_hooked_wheel_routes_only_to_visible_locked_overlays(tmp_path: Path) -> None:
    """The WH_MOUSE_LL router consumes notches over a visible locked feed and
    leaves every other screen position (and unlocked feeds) to the game."""
    app, log, settings, controller = make_controller(tmp_path)
    you = controller.you_overlay
    inside = you.frameGeometry().center()
    outside = QPoint(you.frameGeometry().right() + 500, you.frameGeometry().bottom() + 500)

    controller.set_locked(True)
    assert controller._route_locked_wheel(inside.x(), inside.y(), 1) is True
    assert controller._route_locked_wheel(outside.x(), outside.y(), 1) is False

    controller.set_locked(False)
    assert controller._route_locked_wheel(inside.x(), inside.y(), 1) is False

    controller.wheel_capture.unregister()
    controller.hotkey.unregister()
