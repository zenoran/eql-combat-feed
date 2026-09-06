import importlib
import os
import sys

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

    registered = hotkey.register()
    if sys.platform == "darwin":
        # Carbon registration needs a window-server session; either outcome is
        # legitimate here, and polling is not the mechanism on macOS anyway.
        hotkey.unregister()
        return
    assert registered is (os.name == "nt")
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


def test_mac_chord_translation_requires_one_letter_and_a_modifier() -> None:
    translate = hotkey_module.mac_hotkey_from_vk
    control, option = hotkey_module.VK_CONTROL, hotkey_module.VK_MENU

    assert translate((control, option, ord("L"))) == (0x25, (1 << 12) | (1 << 11))
    assert translate((control, option, ord("G"))) == (0x05, (1 << 12) | (1 << 11))
    assert translate((ord("L"),)) is None  # bare letter would swallow normal typing
    assert translate((control, ord("L"), ord("G"))) is None
    assert translate((control, 0x70)) == (0x7A, 1 << 12)  # F1
    assert translate((option, ord("7"))) == (0x1A, 1 << 11)
    assert translate((control, 0x20)) == (0x31, 1 << 12)  # Space
    assert translate((control, 0x24)) is None  # Home: not in the supported table


def test_chord_from_sequence_accepts_one_modified_key() -> None:
    chord = hotkey_module.chord_from_sequence
    ctrl = hotkey_module.VK_LWIN if sys.platform == "darwin" else hotkey_module.VK_CONTROL
    meta = hotkey_module.VK_CONTROL if sys.platform == "darwin" else hotkey_module.VK_LWIN
    option, shift = hotkey_module.VK_MENU, hotkey_module.VK_SHIFT

    assert chord("Ctrl+Alt+L") == (ctrl, option, ord("L"))
    assert chord("Meta+Alt+G") == (option, meta, ord("G"))
    assert chord("Shift+F5") == (shift, 0x74)
    assert chord("Alt+3") == (option, ord("3"))
    assert chord("Ctrl+Alt+Space") == (ctrl, option, hotkey_module.VK_SPACE)
    assert chord("Ctrl+Shift+F24") == (ctrl, shift, hotkey_module.VK_F24)
    assert chord("L") is None  # bare key would swallow normal typing
    assert chord("") is None
    assert chord("   ") is None
    assert chord("Ctrl+Alt+Home") is None
    assert chord("Ctrl+A, Ctrl+B") is None
    assert chord("not a chord") is None
    for default in (hotkey_module.default_lock_hotkey(), hotkey_module.default_search_hotkey()):
        assert chord(default) is not None
        assert hotkey_module.mac_hotkey_from_vk(chord(default)) is not None


def test_rebind_swaps_chord_without_polling_stale_keys(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    hotkey = GlobalHotkey(lambda: None, keys=(0x11, 0x12, ord("G")))
    monkeypatch.setattr(hotkey, "_chord_down", lambda: False)

    hotkey.rebind((0x11, 0x10, 0x74))

    assert hotkey.keys == (0x11, 0x10, 0x74)
    hotkey.unregister()
    assert hotkey.registered is False
    app.processEvents()


def test_hotkey_label_renders_portable_text() -> None:
    label = hotkey_module.hotkey_label("Ctrl+Alt+L")
    assert label
    assert hotkey_module.hotkey_label("") == ""
