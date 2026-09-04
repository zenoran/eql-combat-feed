import importlib
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

qt_widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
QApplication = qt_widgets.QApplication
hotkey_module = importlib.import_module("eql_combat_feed.hotkey")
GlobalHotkey = hotkey_module.GlobalHotkey
GlobalLockHotkey = hotkey_module.GlobalLockHotkey


def test_hotkey_poll_toggles_once_per_key_press(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    states = iter([False, True, True, False, True])
    calls = []
    hotkey = GlobalLockHotkey(lambda: calls.append(True))
    monkeypatch.setattr(hotkey, "_chord_down", lambda: next(states))

    assert hotkey.register() is (os.name == "nt")
    if os.name != "nt":
        return
    hotkey._timer.stop()
    hotkey._poll()
    hotkey._poll()
    hotkey._poll()
    hotkey._poll()

    assert calls == [True, True]
    hotkey.unregister()
    app.processEvents()


def test_generic_hotkey_keeps_configured_key_chord() -> None:
    app = QApplication.instance() or QApplication([])
    hotkey = GlobalHotkey(lambda: None, keys=(0x11, 0x12, ord("G")))

    assert hotkey.keys == (0x11, 0x12, ord("G"))
    hotkey.unregister()
    app.processEvents()


def test_unregister_stops_polling(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    calls = []
    hotkey = GlobalLockHotkey(lambda: calls.append(True))
    monkeypatch.setattr(hotkey, "_chord_down", lambda: True)
    hotkey.registered = True
    hotkey.unregister()
    hotkey._poll()

    assert calls == []
    assert hotkey.registered is False
    app.processEvents()
