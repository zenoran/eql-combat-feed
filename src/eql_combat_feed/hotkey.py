"""Reliable Windows global lock-toggle chord with a harmless non-Windows fallback."""

import ctypes
import sys
from collections.abc import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer
from PySide6.QtGui import QCursor

VK_CONTROL = 0x11
VK_MENU = 0x12
VK_L = 0x4C
KEY_DOWN_MASK = 0x8000
WH_MOUSE_LL = 14
WM_MOUSEWHEEL = 0x020A
WHEEL_NOTCH = 120

if sys.platform == "win32":
    _HOOKPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t
    )
else:  # keep the module importable for the cross-platform test suite
    _HOOKPROC = None


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", _POINT),
        ("mouseData", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class GlobalWheelCapture:
    """Steal wheel notches over click-through overlays via a WH_MOUSE_LL hook.

    Locked (``WindowTransparentForInput``) windows never receive wheel
    events — the OS routes them straight to the game underneath, and unlike
    cursor *position*, wheel *events* cannot be polled after the fact. A
    low-level mouse hook sees every notch before routing. The router decides
    whether a feed window under the cursor consumes it; returning 1 from the
    hook blocks the game's camera zoom for that notch — and only then.

    The hook is installed on the Qt main thread (Qt pumps Windows messages),
    so the router may touch widgets directly. The callback must stay fast and
    must never raise: a slow or crashing LL hook degrades the system mouse.
    """

    def __init__(self, router: Callable[[int, int, int], bool]) -> None:
        self.router = router
        self.registered = False
        self._handle = None
        self._proc = None

    def register(self) -> bool:
        if sys.platform != "win32":
            return False
        user32 = ctypes.windll.user32
        # Explicit 64-bit-safe signatures: the default c_int restype would
        # truncate the HHOOK handle and the CallNextHookEx result.
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            _HOOKPROC,
            ctypes.c_void_p,
            ctypes.c_ulong,
        ]
        user32.CallNextHookEx.restype = ctypes.c_ssize_t
        user32.CallNextHookEx.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]
        user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]

        @_HOOKPROC
        def proc(n_code: int, w_param: int, l_param: int) -> int:
            if n_code == 0 and w_param == WM_MOUSEWHEEL:
                try:
                    data = ctypes.cast(
                        l_param, ctypes.POINTER(_MSLLHOOKSTRUCT)
                    ).contents
                    delta = ctypes.c_short((data.mouseData >> 16) & 0xFFFF).value
                    steps = (
                        delta // WHEEL_NOTCH
                        if delta > 0
                        else -(-delta // WHEEL_NOTCH)
                    )
                    # DPI trap: the hook's MSLLHOOKSTRUCT point is PHYSICAL
                    # screen pixels, while Qt geometry lives in logical
                    # (scaled) pixels — at 175% display scale they never
                    # match. QCursor.pos() is already logical and identical
                    # to what the hover check compares against.
                    position = QCursor.pos()
                    if steps and self.router(position.x(), position.y(), steps):
                        return 1
                except Exception:  # noqa: BLE001 — never break the system mouse
                    pass
            return user32.CallNextHookEx(None, n_code, w_param, l_param)

        self._proc = proc  # keep the callback alive for the hook's lifetime
        self._handle = user32.SetWindowsHookExW(WH_MOUSE_LL, proc, None, 0)
        self.registered = bool(self._handle)
        return self.registered

    def unregister(self) -> None:
        if self._handle:
            ctypes.windll.user32.UnhookWindowsHookEx(self._handle)
        self._handle = None
        self._proc = None
        self.registered = False


class GlobalHotkey(QAbstractNativeEventFilter):
    """Poll a key chord so it works even while click-through windows are focused.

    ``RegisterHotKey`` messages do not consistently reach Qt's native event filter
    on every Windows system. ``GetAsyncKeyState`` is process-global, needs no
    focused window, and cannot lose a registration fight to another application.
    """

    VK_CONTROL = VK_CONTROL
    VK_MENU = VK_MENU

    def __init__(self, callback: Callable[[], None], *, keys: tuple[int, ...]) -> None:
        super().__init__()
        self.callback = callback
        self.keys = keys
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

    def _chord_down(self) -> bool:
        user32 = ctypes.windll.user32
        return all(user32.GetAsyncKeyState(key) & KEY_DOWN_MASK for key in self.keys)

    def nativeEventFilter(self, event_type, message) -> tuple[bool, int]:  # type: ignore[override]
        del event_type, message
        return False, 0


class GlobalLockHotkey(GlobalHotkey):
    """Ctrl+Alt+L lock-toggle chord retained for backwards compatibility."""

    def __init__(self, callback: Callable[[], None]) -> None:
        super().__init__(callback, keys=(VK_CONTROL, VK_MENU, VK_L))
