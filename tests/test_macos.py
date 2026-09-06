import sys
from types import SimpleNamespace

from PySide6.QtGui import QGuiApplication

from eql_combat_feed import macos


def test_spaces_behavior_drops_move_to_active_space_and_joins_all_spaces() -> None:
    qt_default = (
        macos.NS_WINDOW_COLLECTION_BEHAVIOR_MOVE_TO_ACTIVE_SPACE
        | macos.NS_WINDOW_COLLECTION_BEHAVIOR_FULL_SCREEN_PRIMARY
        | (1 << 4)
    )

    result = macos.spaces_behavior(qt_default)

    assert result & macos.NS_WINDOW_COLLECTION_BEHAVIOR_CAN_JOIN_ALL_SPACES
    assert result & macos.NS_WINDOW_COLLECTION_BEHAVIOR_FULL_SCREEN_AUXILIARY
    assert not result & macos.NS_WINDOW_COLLECTION_BEHAVIOR_MOVE_TO_ACTIVE_SPACE
    assert not result & macos.NS_WINDOW_COLLECTION_BEHAVIOR_FULL_SCREEN_PRIMARY
    assert result & (1 << 4)  # unrelated bits survive


def test_float_above_fullscreen_is_a_no_op_off_macos(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    assert macos.float_above_fullscreen(object(), disable_shadow=True) is False


class FakeWindow:
    def __init__(self) -> None:
        self._level = 25
        self._behavior = (
            macos.NS_WINDOW_COLLECTION_BEHAVIOR_MOVE_TO_ACTIVE_SPACE
            | macos.NS_WINDOW_COLLECTION_BEHAVIOR_FULL_SCREEN_PRIMARY
        )
        self.hides_on_deactivate = True
        self.has_shadow = True
        self.ordered_front = False

    def level(self) -> int:
        return self._level

    def collectionBehavior(self) -> int:
        return self._behavior

    def setLevel_(self, level: int) -> None:
        self._level = level

    def setCollectionBehavior_(self, behavior: int) -> None:
        self._behavior = behavior

    def setHidesOnDeactivate_(self, value: bool) -> None:
        self.hides_on_deactivate = value

    def setHasShadow_(self, value: bool) -> None:
        self.has_shadow = value

    def orderFrontRegardless(self) -> None:
        self.ordered_front = True


class FakeView:
    def __init__(self, window: FakeWindow) -> None:
        self._window = window

    def window(self) -> FakeWindow:
        return self._window


def test_float_above_fullscreen_configures_native_window(monkeypatch) -> None:
    window = FakeWindow()
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(QGuiApplication, "platformName", staticmethod(lambda: "cocoa"))
    monkeypatch.setitem(
        sys.modules,
        "objc",
        SimpleNamespace(objc_object=lambda **_pointer: FakeView(window)),
    )
    widget = SimpleNamespace(winId=lambda: 123, windowTitle=lambda: "feed")

    assert macos.float_above_fullscreen(widget, disable_shadow=True) is True
    assert window.level() == macos.OVERLAY_WINDOW_LEVEL
    assert window.collectionBehavior() == macos.spaces_behavior(
        macos.NS_WINDOW_COLLECTION_BEHAVIOR_MOVE_TO_ACTIVE_SPACE
        | macos.NS_WINDOW_COLLECTION_BEHAVIOR_FULL_SCREEN_PRIMARY
    )
    assert window.hides_on_deactivate is False
    assert window.has_shadow is False
    assert window.ordered_front is True
