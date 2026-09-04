"""Application entry point."""

import argparse
import ctypes
import logging
import sys
from pathlib import Path

from PySide6.QtCore import QLockFile, QStandardPaths
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .controller import CombatFeedController
from .settings import SettingsStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Visual combat-beat overlay for EQL")
    parser.add_argument("--log", help="Explicit eqlog_*.txt file to follow")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Use an isolated development profile that can run beside the installed app",
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def configure_logging(*, dev_mode: bool = False) -> None:
    location = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    )
    location.mkdir(parents=True, exist_ok=True)
    log_name = "eql-combat-feed-dev.log" if dev_mode else "eql-combat-feed.log"
    logging.basicConfig(
        filename=location / log_name,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Windowed executables have no stderr: an uncaught exception in a Qt
    # timer/slot would vanish without a trace. Route it to the log file so a
    # silent failure always leaves a corpse to autopsy.
    def log_uncaught(exc_type, value, traceback) -> None:  # type: ignore[no-untyped-def]
        logging.getLogger("eql_combat_feed.crash").critical(
            "Unhandled exception", exc_info=(exc_type, value, traceback)
        )

    sys.excepthook = log_uncaught


def configure_windows_identity(*, dev_mode: bool = False) -> None:
    if sys.platform == "win32":
        suffix = ".dev" if dev_mode else ""
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"zenoran.eql-combat-feed{suffix}"
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_windows_identity(dev_mode=args.dev)
    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    app_name = "EQL Combat Feed DEV" if args.dev else "EQL Combat Feed"
    app.setApplicationName(app_name)
    app.setApplicationVersion(__version__)
    configure_logging(dev_mode=args.dev)

    lock_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation))
    lock_name = "eql-combat-feed-dev.lock" if args.dev else "eql-combat-feed.lock"
    lock = QLockFile(str(lock_dir / lock_name))
    lock.setStaleLockTime(10_000)
    if not lock.tryLock(100):
        QMessageBox.information(None, app_name, f"{app_name} is already running.")
        return 0

    settings = SettingsStore.for_profile(dev_mode=args.dev)
    controller = CombatFeedController(
        app,
        requested_log=args.log,
        settings=settings,
        dev_mode=args.dev,
    )
    app.aboutToQuit.connect(controller.hotkey.unregister)
    app.aboutToQuit.connect(controller.search_hotkey.unregister)
    app.aboutToQuit.connect(controller.wheel_capture.unregister)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
