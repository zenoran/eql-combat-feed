"""Reliable Windows global lock-toggle chord with a harmless non-Windows fallback."""

import ctypes
import sys
from collections.abc import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer

VK_CONTROL = 0x11
VK_MENU = 0x12
VK_L = 0x4C
KEY_DOWN_MASK = 0x8000


class GlobalLockHotkey(QAbstractNativeEventFilter):
    """Poll Ctrl+Alt+L directly so click-through windows can always be recovered.

    ``RegisterHotKey`` messages do not consistently reach Qt's native event filter
    on every Windows system. ``GetAsyncKeyState`` is process-global, needs no
    focused window, and cannot lose a registration fight to another application.
    """

    def __init__(self, callback: Callable[[], None]) -> None:
        super().__init__()
        self.callback = callback
        self.registered = False
        self._chord_was_down = False
        self._timer = QTimer()
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._poll)

    def register(self) -> bool:
        if sys.platform != "win32":
            return False
        self._chord_was_down = self._chord_down()
        self._timer.start()
        self.registered = True
        return True

    def unregister(self) -> None:
        self._timer.stop()
        self._chord_was_down = False
        self.registered = False

    def _poll(self) -> None:
        if not self.registered:
            return
        chord_down = self._chord_down()
        if chord_down and not self._chord_was_down:
            self.callback()
        self._chord_was_down = chord_down

    @staticmethod
    def _chord_down() -> bool:
        user32 = ctypes.windll.user32
        return all(
            user32.GetAsyncKeyState(key) & KEY_DOWN_MASK for key in (VK_CONTROL, VK_MENU, VK_L)
        )

    def nativeEventFilter(self, event_type, message) -> tuple[bool, int]:  # type: ignore[override]
        del event_type, message
        return False, 0
