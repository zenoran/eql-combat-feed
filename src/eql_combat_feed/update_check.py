"""Optional startup update check against GitHub releases.

One anonymous HTTPS GET to the public releases API, in a daemon thread so a
slow network can never block the UI. Failures are logged and otherwise
silent; the check can be disabled entirely in Options.
"""

import json
import logging
import re
import threading
import urllib.request

from PySide6.QtCore import QObject, Signal

LOG = logging.getLogger(__name__)
RELEASES_API = "https://api.github.com/repos/zenoran/eql-combat-feed/releases/latest"
RELEASES_PAGE = "https://github.com/zenoran/eql-combat-feed/releases/latest"


def parse_version(text: str) -> tuple[int, int, int] | None:
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", text.strip())
    if not match:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def is_newer(candidate: str, current: str) -> bool:
    candidate_version = parse_version(candidate)
    current_version = parse_version(current)
    return (
        candidate_version is not None
        and current_version is not None
        and candidate_version > current_version
    )


class UpdateChecker(QObject):
    """Emits ``update_available(version, url)`` when a newer release exists."""

    update_available = Signal(str, str)

    def __init__(self, current_version: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.current_version = current_version

    def check(self) -> None:
        threading.Thread(target=self._worker, daemon=True, name="update-check").start()

    def _worker(self) -> None:
        try:
            request = urllib.request.Request(
                RELEASES_API,
                headers={
                    "User-Agent": f"eql-combat-feed/{self.current_version}",
                    "Accept": "application/vnd.github+json",
                },
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.load(response)
        except Exception:
            LOG.info("Update check failed", exc_info=True)
            return
        tag = str(data.get("tag_name") or "")
        url = str(data.get("html_url") or RELEASES_PAGE)
        if is_newer(tag, self.current_version):
            LOG.info("Update available: %s (running %s)", tag, self.current_version)
            # Cross-thread emit is safe: Qt queues it to the receiver's thread.
            self.update_available.emit(tag.lstrip("vV"), url)
        else:
            LOG.info("Up to date (%s)", self.current_version)
