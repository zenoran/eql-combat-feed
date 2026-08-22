import importlib
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

qt_core = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
qt_gui = pytest.importorskip("PySide6.QtGui", exc_type=ImportError)
qt_test = pytest.importorskip("PySide6.QtTest", exc_type=ImportError)
qt_widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
Qt = qt_core.Qt
QIcon = qt_gui.QIcon
QTest = qt_test.QTest
QApplication = qt_widgets.QApplication
ControlWindow = importlib.import_module("eql_combat_feed.window").ControlWindow
OverlayPreferences = importlib.import_module("eql_combat_feed.settings").OverlayPreferences


def test_control_window_is_normal_taskbar_window_and_close_requests_quit() -> None:
    app = QApplication.instance() or QApplication([])
    window = ControlWindow(OverlayPreferences(), QIcon())
    quit_requested = []
    window.quit_requested.connect(lambda: quit_requested.append(True))
    window.show()

    assert window.windowType() is not Qt.WindowType.Tool
    assert window.windowTitle().startswith("EQL Combat Feed")
    assert window.isVisible()

    window.close()
    assert quit_requested == [True]
    assert window.isVisible()

    window.allow_close()
    window.close()
    app.processEvents()


def test_close_minimizes_to_tray_when_enabled() -> None:
    app = QApplication.instance() or QApplication([])
    window = ControlWindow(OverlayPreferences(minimize_to_tray=True), QIcon())
    quit_requested = []
    window.quit_requested.connect(lambda: quit_requested.append(True))
    window.show()

    window.close()
    assert quit_requested == []  # App keeps running in the tray...
    assert not window.isVisible()  # ...with the window hidden, not destroyed.

    window.show_and_raise()
    assert window.isVisible()

    window.allow_close()
    window.close()
    app.processEvents()


def test_control_window_exposes_persisted_behavior_toggles() -> None:
    app = QApplication.instance() or QApplication([])
    preferences = OverlayPreferences(locked=True, show_pet=False, auto_quit_with_game=True)
    window = ControlWindow(preferences, QIcon())

    assert window.locked.isChecked()
    assert not window.show_pet.isChecked()
    assert window.auto_quit.isChecked()

    QTest.mouseClick(window.auto_quit, Qt.MouseButton.LeftButton)
    assert not window.auto_quit.isChecked()

    window.allow_close()
    window.close()
    app.processEvents()
