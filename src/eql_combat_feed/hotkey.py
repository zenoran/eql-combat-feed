"""Global hotkey chords: Windows key polling, macOS Carbon hot keys, no-op elsewhere.

Windows polls ``GetAsyncKeyState`` for the four chord keys only. macOS uses
``RegisterEventHotKey`` — the window server delivers just the registered chord,
needs no Accessibility or Input Monitoring permission, and never exposes other
keystrokes to this process. Locked-overlay wheel capture is Windows-only.
"""

import ctypes
import logging
import sys
from collections.abc import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, Qt, QTimer
from PySide6.QtGui import QCursor, QKeySequence

LOG = logging.getLogger(__name__)

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_SPACE = 0x20
VK_L = 0x4C
VK_LWIN = 0x5B
VK_F1 = 0x70
VK_F24 = 0x87
EVENT_NOT_HANDLED_ERR = -9874  # Carbon: let the next handler on the target see the event
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


def default_lock_hotkey() -> str:
    """Portable key-sequence text for the lock toggle (Control+Option+L on macOS)."""
    return "Meta+Alt+L" if sys.platform == "darwin" else "Ctrl+Alt+L"


def default_search_hotkey() -> str:
    """Portable key-sequence text for the log-search toggle."""
    return "Meta+Alt+G" if sys.platform == "darwin" else "Ctrl+Alt+G"


def hotkey_label(text: str) -> str:
    """Human-readable form of a portable key sequence (⌃⌥L on macOS, Ctrl+Alt+L elsewhere)."""
    sequence = QKeySequence(text, QKeySequence.SequenceFormat.PortableText)
    return sequence.toString(QKeySequence.SequenceFormat.NativeText) or text


def _modifier_vks() -> tuple[tuple[Qt.KeyboardModifier, int], ...]:
    # Qt swaps Control and Meta on macOS: Qt's ControlModifier is ⌘ and
    # MetaModifier is the physical Control key. The VK chord keeps the
    # physical meaning so the Carbon translation below stays honest.
    if sys.platform == "darwin":
        control, meta = VK_LWIN, VK_CONTROL
    else:
        control, meta = VK_CONTROL, VK_LWIN
    return (
        (Qt.KeyboardModifier.ControlModifier, control),
        (Qt.KeyboardModifier.AltModifier, VK_MENU),
        (Qt.KeyboardModifier.ShiftModifier, VK_SHIFT),
        (Qt.KeyboardModifier.MetaModifier, meta),
    )


def _vk_for_qt_key(key: int) -> int | None:
    if 0x41 <= key <= 0x5A or 0x30 <= key <= 0x39:  # A-Z / 0-9 share VK values
        return key
    if key == int(Qt.Key.Key_Space):
        return VK_SPACE
    first_f, last_f = int(Qt.Key.Key_F1), int(Qt.Key.Key_F24)
    if first_f <= key <= last_f:
        return VK_F1 + (key - first_f)
    return None


def chord_from_sequence(text: str) -> tuple[int, ...] | None:
    """Translate portable key-sequence text (``Ctrl+Alt+L``) into a VK chord.

    Exactly one combination with at least one modifier and one supported key
    (letter, digit, F1–F24, Space) is accepted; anything else returns ``None``
    so callers fall back to the default instead of swallowing plain typing.
    """
    text = (text or "").strip()
    if not text:
        return None
    sequence = QKeySequence(text, QKeySequence.SequenceFormat.PortableText)
    if sequence.count() != 1:
        return None
    combination = sequence[0]
    modifiers = combination.keyboardModifiers()
    chord = [vk for modifier, vk in _modifier_vks() if modifiers & modifier]
    if not chord:
        return None
    key = combination.key()
    vk = _vk_for_qt_key(int(getattr(key, "value", key)))
    if vk is None:
        return None
    chord.append(vk)
    return tuple(chord)


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
        if sys.platform == "darwin":
            self._mac = _CarbonHotkey(self.callback, keys=self.keys)
            self.registered = self._mac.register()
            LOG.info("Hotkey %s registered=%s", self.keys, self.registered)
            return self.registered
        if sys.platform != "win32":
            return False
        self._chord_was_down = self._chord_down()
        self._timer.start()
        self.registered = True
        return True

    def rebind(self, keys: tuple[int, ...]) -> bool:
        """Swap the chord at runtime (options dialog); safe to call while unregistered."""
        self.unregister()
        self.keys = keys
        return self.register()

    def unregister(self) -> None:
        self._timer.stop()
        mac = getattr(self, "_mac", None)
        if mac is not None:
            mac.unregister()
            self._mac = None
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


# --- macOS ------------------------------------------------------------------

# Carbon modifier bits and ANSI virtual key codes (HIToolbox/Events.h).
_MAC_MODIFIERS = {VK_LWIN: 1 << 8, VK_SHIFT: 1 << 9, VK_MENU: 1 << 11, VK_CONTROL: 1 << 12}
_MAC_KEYCODES = {
    "A": 0x00, "S": 0x01, "D": 0x02, "F": 0x03, "H": 0x04, "G": 0x05, "Z": 0x06,
    "X": 0x07, "C": 0x08, "V": 0x09, "B": 0x0B, "Q": 0x0C, "W": 0x0D, "E": 0x0E,
    "R": 0x0F, "Y": 0x10, "T": 0x11, "O": 0x1F, "U": 0x20, "I": 0x22, "P": 0x23,
    "L": 0x25, "J": 0x26, "K": 0x28, "N": 0x2D, "M": 0x2E,
    "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "5": 0x17, "6": 0x16, "7": 0x1A,
    "8": 0x1C, "9": 0x19, "0": 0x1D,
}  # fmt: skip
_MAC_VK_KEYCODES = {
    VK_SPACE: 0x31,
    VK_F1: 0x7A, VK_F1 + 1: 0x78, VK_F1 + 2: 0x63, VK_F1 + 3: 0x76, VK_F1 + 4: 0x60,
    VK_F1 + 5: 0x61, VK_F1 + 6: 0x62, VK_F1 + 7: 0x64, VK_F1 + 8: 0x65, VK_F1 + 9: 0x6D,
    VK_F1 + 10: 0x67, VK_F1 + 11: 0x6F, VK_F1 + 12: 0x69, VK_F1 + 13: 0x6B,
    VK_F1 + 14: 0x71, VK_F1 + 15: 0x6A, VK_F1 + 16: 0x40, VK_F1 + 17: 0x4F,
    VK_F1 + 18: 0x50, VK_F1 + 19: 0x5A,
}  # fmt: skip


def _mac_keycode_for_vk(key: int) -> int | None:
    if 0x41 <= key <= 0x5A or 0x30 <= key <= 0x39:
        return _MAC_KEYCODES.get(chr(key))
    return _MAC_VK_KEYCODES.get(key)


def mac_hotkey_from_vk(keys: tuple[int, ...]) -> tuple[int, int] | None:
    """Translate a Windows VK chord into ``(carbon_keycode, carbon_modifiers)``.

    Exactly one non-modifier key (letter, digit, F-key, Space) is required;
    anything else is unsupported and returns ``None`` so callers fail closed
    (no hotkey) instead of guessing.
    """
    modifiers = 0
    keycode: int | None = None
    for key in keys:
        if key in _MAC_MODIFIERS:
            modifiers |= _MAC_MODIFIERS[key]
            continue
        code = _mac_keycode_for_vk(key)
        if code is None or keycode is not None:
            return None
        keycode = code
    if keycode is None or not modifiers:
        return None
    return keycode, modifiers


class _EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


class _EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


def _four_cc(code: str) -> int:
    return int.from_bytes(code.encode("ascii"), "big")


class _CarbonHotkey:
    """One ``RegisterEventHotKey`` registration dispatched on Qt's main thread.

    Qt's Cocoa event loop pumps Carbon application events, so the handler runs
    on the GUI thread and the callback may touch widgets directly.
    """

    SIGNATURE = _four_cc("EQCF")
    _next_id = 1

    def __init__(self, callback: Callable[[], None], *, keys: tuple[int, ...]) -> None:
        self.callback = callback
        self.keys = keys
        self._carbon = None
        self._handler_ref = ctypes.c_void_p()
        self._hotkey_ref = ctypes.c_void_p()
        self._proc = None
        self._id = _CarbonHotkey._next_id
        _CarbonHotkey._next_id += 1

    def register(self) -> bool:
        translated = mac_hotkey_from_vk(self.keys)
        if translated is None:
            return False
        keycode, modifiers = translated
        try:
            carbon = ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
        except OSError:
            return False
        handler_type = ctypes.CFUNCTYPE(
            ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        )
        carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
        carbon.InstallEventHandler.restype = ctypes.c_int32
        carbon.InstallEventHandler.argtypes = [
            ctypes.c_void_p, handler_type, ctypes.c_size_t,
            ctypes.POINTER(_EventTypeSpec), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        ]  # fmt: skip
        carbon.RegisterEventHotKey.restype = ctypes.c_int32
        carbon.RegisterEventHotKey.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, _EventHotKeyID,
            ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p),
        ]  # fmt: skip
        carbon.GetEventParameter.restype = ctypes.c_int32
        carbon.GetEventParameter.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
            ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p,
        ]  # fmt: skip
        carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
        carbon.RemoveEventHandler.argtypes = [ctypes.c_void_p]

        hotkey_id = _EventHotKeyID(self.SIGNATURE, self._id)

        @handler_type
        def proc(call_ref: int, event: int, user_data: int) -> int:
            del call_ref, user_data
            # Every registration installs its own handler on the application
            # target and Carbon calls the newest first. Returning noErr marks
            # the event handled and STOPS the chain, so a non-matching handler
            # must return eventNotHandledErr or it silently eats every other
            # chord (search installed after lock swallowed all lock presses).
            try:
                received = _EventHotKeyID()
                status = carbon.GetEventParameter(
                    event, _four_cc("----"), _four_cc("hkid"), None,
                    ctypes.sizeof(received), None, ctypes.byref(received),
                )  # fmt: skip
                if status != 0 or (received.signature, received.id) != (
                    self.SIGNATURE, self._id
                ):
                    return EVENT_NOT_HANDLED_ERR
                LOG.debug("Hotkey %s fired", self.keys)
                self.callback()
            except Exception:  # noqa: BLE001 — never propagate into the Carbon dispatcher
                LOG.exception("Hotkey %s callback failed", self.keys)
            return 0

        spec = _EventTypeSpec(_four_cc("keyb"), 5)  # kEventClassKeyboard / kEventHotKeyPressed
        target = carbon.GetApplicationEventTarget()
        if carbon.InstallEventHandler(target, proc, 1, ctypes.byref(spec), None,
                                      ctypes.byref(self._handler_ref)) != 0:  # fmt: skip
            return False
        if carbon.RegisterEventHotKey(keycode, modifiers, hotkey_id, target, 0,
                                      ctypes.byref(self._hotkey_ref)) != 0:  # fmt: skip
            carbon.RemoveEventHandler(self._handler_ref)
            self._handler_ref = ctypes.c_void_p()
            return False
        self._carbon = carbon
        self._proc = proc  # keep the callback alive for the registration's lifetime
        return True

    def unregister(self) -> None:
        if self._carbon is None:
            return
        if self._hotkey_ref:
            self._carbon.UnregisterEventHotKey(self._hotkey_ref)
        if self._handler_ref:
            self._carbon.RemoveEventHandler(self._handler_ref)
        self._hotkey_ref = ctypes.c_void_p()
        self._handler_ref = ctypes.c_void_p()
        self._proc = None
        self._carbon = None
