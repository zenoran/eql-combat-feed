"""macOS window-server tweaks that Qt does not expose.

osxEQL's QoL launcher puts the Wine game window into a real macOS full-screen
Space. Verified on macOS 26 with a bare AppKit probe: a window follows into
another app's full-screen Space only when (a) it joins all Spaces as a
full-screen auxiliary window, (b) it sits above the game's level, and (c) the
owning app runs with the *accessory* activation policy (menu-bar app, no Dock
icon). A regular-policy app's windows stay parked on the desktop no matter
what the window itself says.
"""

import logging
import sys

LOG = logging.getLogger(__name__)

# winemac.drv raises a screen-covering game window to NSMainMenuWindowLevel + 1
# (25) while the game is active, so "status" level ties with it and loses.
# Pop-up-menu level (101) is above that, still below screen-saver/shielding.
OVERLAY_WINDOW_LEVEL = 101
NS_WINDOW_COLLECTION_BEHAVIOR_CAN_JOIN_ALL_SPACES = 1 << 0
NS_WINDOW_COLLECTION_BEHAVIOR_MOVE_TO_ACTIVE_SPACE = 1 << 1  # Qt's default for Tool windows
NS_WINDOW_COLLECTION_BEHAVIOR_FULL_SCREEN_PRIMARY = 1 << 7  # Qt's default for plain windows
NS_WINDOW_COLLECTION_BEHAVIOR_FULL_SCREEN_AUXILIARY = 1 << 8


def spaces_behavior(current: int) -> int:
    """Collection behavior that joins every Space, including other apps' full-screen ones.

    AppKit rejects CanJoinAllSpaces alongside MoveToActiveSpace, and Primary
    alongside Auxiliary, so both Qt defaults are cleared first.
    """
    cleared = current & ~(
        NS_WINDOW_COLLECTION_BEHAVIOR_MOVE_TO_ACTIVE_SPACE
        | NS_WINDOW_COLLECTION_BEHAVIOR_FULL_SCREEN_PRIMARY
    )
    return (
        cleared
        | NS_WINDOW_COLLECTION_BEHAVIOR_CAN_JOIN_ALL_SPACES
        | NS_WINDOW_COLLECTION_BEHAVIOR_FULL_SCREEN_AUXILIARY
    )


NS_APPLICATION_ACTIVATION_POLICY_ACCESSORY = 1


def become_accessory_app() -> bool:
    """Run as a menu-bar (accessory) app so overlays may enter full-screen Spaces.

    Side effects: no Dock icon and no Cmd-Tab entry; the tray icon and the
    control window remain the way in. Returns ``False`` when not applicable.
    """
    if sys.platform != "darwin":
        return False
    try:
        from AppKit import NSApp  # type: ignore[import-not-found]

        return bool(NSApp.setActivationPolicy_(NS_APPLICATION_ACTIVATION_POLICY_ACCESSORY))
    except Exception:  # noqa: BLE001 — cosmetic; the feed still runs on the desktop
        LOG.exception("Unable to switch to the accessory activation policy")
        return False


def float_above_fullscreen(
    widget, *, disable_shadow: bool = False
) -> bool:  # type: ignore[no-untyped-def]
    """Make ``widget``'s native window show over other apps' full-screen Spaces.

    Call from ``showEvent``: Qt recreates the NSWindow whenever window flags
    change (lock toggles ``WindowTransparentForInput``), which resets the level.
    Transparent overlay windows should pass ``disable_shadow=True``; otherwise
    Cocoa draws a faint shadow around the widget's full rectangular frame.
    Returns ``False`` when not on macOS or the native window is unavailable.
    """
    if sys.platform != "darwin":
        return False
    from PySide6.QtGui import QGuiApplication

    # winId() is only an NSView on the cocoa platform; under "offscreen"
    # (tests) or "minimal" it is an opaque handle that would crash the bridge.
    if QGuiApplication.platformName() != "cocoa":
        LOG.info("Not on the cocoa platform (%s); leaving window level alone",
                 QGuiApplication.platformName())
        return False
    try:
        import objc  # type: ignore[import-not-found]
    except ImportError:
        return False
    try:
        view = objc.objc_object(c_void_p=int(widget.winId()))
        window = view.window()
        if window is None:
            LOG.warning("No NSWindow behind %r yet; cannot join full-screen Spaces", widget)
            return False
        before = (int(window.level()), int(window.collectionBehavior()))
        window.setLevel_(OVERLAY_WINDOW_LEVEL)
        window.setCollectionBehavior_(spaces_behavior(before[1]))
        window.setHidesOnDeactivate_(False)
        if disable_shadow:
            window.setHasShadow_(False)
        # Re-order so the window server re-evaluates Space membership now.
        window.orderFrontRegardless()
        after = (int(window.level()), int(window.collectionBehavior()))
        LOG.info("%s: level/behavior %s -> %s", widget.windowTitle(), before, after)
    except Exception:  # noqa: BLE001 — cosmetic; never take the feed down over it
        LOG.exception("Unable to raise window above full-screen Spaces")
        return False
    return True


def window_report(pids: set[int]) -> list[str]:
    """Describe the window server's view of every window owned by ``pids``.

    Diagnostic only (level, bounds, alpha, on-screen). Needs no permission.
    """
    if sys.platform != "darwin":
        return []
    try:
        import objc  # type: ignore[import-not-found]

        namespace: dict[str, object] = {}
        bundle = objc.loadBundle(
            "CoreGraphics",
            namespace,
            bundle_path="/System/Library/Frameworks/CoreGraphics.framework",
        )
        objc.loadBundleFunctions(
            bundle, namespace, [("CGWindowListCopyWindowInfo", b"^{__CFArray=}II")]
        )
        infos = namespace["CGWindowListCopyWindowInfo"](0, 0)  # kCGWindowListOptionAll
    except Exception as error:  # noqa: BLE001 — diagnostics must never fail the feed
        return [f"window report unavailable: {error!r}"]
    lines: list[str] = []
    try:
        from AppKit import NSApp  # type: ignore[import-not-found]

        for window in NSApp.windows():
            lines.append(
                f"own NSWindow {window.title()!r}: visible={bool(window.isVisible())} "
                f"onActiveSpace={bool(window.isOnActiveSpace())} "
                f"hidesOnDeactivate={bool(window.hidesOnDeactivate())} "
                f"level={int(window.level())} behavior={int(window.collectionBehavior())}"
            )
    except Exception as error:  # noqa: BLE001
        lines.append(f"NSApp window list unavailable: {error!r}")
    for info in infos or []:
        pid = int(info.get("kCGWindowOwnerPID", 0))
        if pid not in pids:
            continue
        bounds = info.get("kCGWindowBounds") or {}
        lines.append(
            f"pid={pid} owner={info.get('kCGWindowOwnerName')!r} "
            f"layer={info.get('kCGWindowLayer')} alpha={info.get('kCGWindowAlpha')} "
            f"onscreen={bool(info.get('kCGWindowIsOnscreen', False))} "
            f"bounds={int(bounds.get('X', 0))},{int(bounds.get('Y', 0))} "
            f"{int(bounds.get('Width', 0))}x{int(bounds.get('Height', 0))}"
        )
    return lines
