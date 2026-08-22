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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Visual combat-beat overlay for EQL")
    parser.add_argument("--log", help="Explicit eqlog_*.txt file to follow")
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def configure_logging() -> None:
    location = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    )
    location.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=location / "eql-combat-feed.log",
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


def configure_windows_identity() -> None:
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "zenoran.eql-combat-feed"
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_windows_identity()
    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    app.setApplicationName("EQL Combat Feed")
    app.setApplicationVersion(__version__)
    configure_logging()

    lock_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation))
    lock = QLockFile(str(lock_dir / "eql-combat-feed.lock"))
    lock.setStaleLockTime(10_000)
    if not lock.tryLock(100):
        QMessageBox.information(None, "EQL Combat Feed", "EQL Combat Feed is already running.")
        return 0

    controller = CombatFeedController(app, requested_log=args.log)
    app.aboutToQuit.connect(controller.hotkey.unregister)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
