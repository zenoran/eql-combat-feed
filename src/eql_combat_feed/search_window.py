"""On-demand regex search popup for the active EverQuest log."""

import re
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QCloseEvent, QColor, QFont, QKeyEvent, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from .log_search import LogSearchResult, search_log
from .settings import LogSearchHistoryEntry, SettingsStore

LOOKBACKS = (
    ("15 minutes", 15 * 60),
    ("1 hour", 60 * 60),
    ("6 hours", 6 * 60 * 60),
    ("24 hours", 24 * 60 * 60),
    ("7 days", 7 * 24 * 60 * 60),
    ("All time", None),
)


class LogSearchWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        path: Path,
        pattern: str,
        exclude_pattern: str,
        lookback_seconds: int | None,
        match_case: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.path = path
        self.pattern = pattern
        self.exclude_pattern = exclude_pattern
        self.lookback_seconds = lookback_seconds
        self.match_case = match_case

    def run(self) -> None:
        try:
            result = search_log(
                self.path,
                self.pattern,
                lookback_seconds=self.lookback_seconds,
                exclude_pattern=self.exclude_pattern,
                match_case=self.match_case,
                cancelled=self.isInterruptionRequested,
            )
        except (OSError, re.error, ValueError) as error:
            self.failed.emit(str(error))
            return
        self.completed.emit(result)


class LogSearchWindow(QWidget):
    """Keyboard-driven popup; closing hides it so the global chord can reopen it."""

    def __init__(self, settings: SettingsStore | None = None) -> None:
        super().__init__()
        self.settings = settings or SettingsStore()
        self.log_path: Path | None = None
        self._worker: LogSearchWorker | None = None
        self._allow_close = False
        self._history = self.settings.load_search_history()
        self.setWindowTitle("EQL Log Search — Ctrl+Alt+G")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.resize(900, 560)
        self.setMinimumSize(560, 320)
        self.setStyleSheet(
            "QWidget { background: #11151a; color: #e8edf2; }"
            "QLineEdit, QComboBox, QPlainTextEdit {"
            " background: #080b0e; border: 1px solid #39424c; padding: 6px; }"
            "QPushButton { background: #26313b; border: 1px solid #4c5c6b; padding: 7px 14px; }"
            "QPushButton:hover { background: #32404d; }"
        )

        self.pattern = QLineEdit()
        self.pattern.setPlaceholderText("words or Python regex")
        self.pattern.setClearButtonEnabled(True)
        self.pattern.returnPressed.connect(self.search)
        self.history_button = QPushButton("Recent searches…")
        self.history_button.setMinimumWidth(178)
        self.history_menu = QMenu(self.history_button)
        self.history_button.setMenu(self.history_menu)
        self._refresh_history()
        include_row = QHBoxLayout()
        include_label = QLabel("Include")
        include_label.setFixedWidth(50)
        include_row.addWidget(include_label)
        include_row.addWidget(self.pattern, 1)
        include_row.addWidget(self.history_button)

        self.exclude_pattern = QLineEdit()
        self.exclude_pattern.setPlaceholderText("optional words or regex to leave out")
        self.exclude_pattern.setClearButtonEnabled(True)
        self.exclude_pattern.returnPressed.connect(self.search)

        self.lookback = QComboBox()
        for label, seconds in LOOKBACKS:
            self.lookback.addItem(label, seconds)
        self.lookback.setCurrentIndex(3)

        self.match_case = QCheckBox("Case sensitive")
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search)

        exclude_row = QHBoxLayout()
        exclude_label = QLabel("Exclude")
        exclude_label.setFixedWidth(50)
        exclude_row.addWidget(exclude_label)
        exclude_row.addWidget(self.exclude_pattern, 1)
        exclude_row.addWidget(self.lookback)
        exclude_row.addWidget(self.match_case)
        exclude_row.addWidget(self.search_button)

        self.status = QLabel("Ctrl+Alt+G toggles this window · Escape hides it")
        self.status.setStyleSheet("color: #8e9aa6;")
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        self.results.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        fixed = self.results.font()
        fixed.setFamily("Consolas")
        self.results.setFont(fixed)

        layout = QVBoxLayout(self)
        layout.addLayout(include_row)
        layout.addLayout(exclude_row)
        layout.addWidget(self.status)
        layout.addWidget(self.results, 1)

    def set_log_path(self, path: Path | None) -> None:
        self.log_path = path

    def _refresh_history(self) -> None:
        self.history_menu.clear()
        if not self._history:
            empty = self.history_menu.addAction("No recent searches")
            empty.setEnabled(False)
            return
        for entry in self._history:
            action = QWidgetAction(self.history_menu)
            row = QWidget(self.history_menu)
            row.setObjectName("historyRow")
            row.setStyleSheet(
                "QWidget#historyRow { background: #11151a; }"
                "QWidget#historyRow:hover { background: #202832; }"
            )
            layout = QHBoxLayout(row)
            layout.setContentsMargins(9, 3, 3, 3)
            layout.setSpacing(8)
            choose = QPushButton(self._history_label(entry))
            choose.setFlat(True)
            choose.setStyleSheet(
                "text-align: left; border: 0; background: transparent; padding: 5px 2px;"
            )
            choose.clicked.connect(
                lambda checked=False, entry=entry: self._restore_history(entry)
            )
            remove = QPushButton("×")
            remove.setObjectName("deleteHistory")
            remove.setFixedSize(25, 25)
            remove.setToolTip("Delete this search")
            remove.setStyleSheet(
                "QPushButton#deleteHistory {"
                " border: 0; background: transparent; color: #8e9aa6;"
                " font-size: 17px; font-weight: bold; padding: 0; }"
                "QPushButton#deleteHistory:hover {"
                " background: #351b20; color: #ff7676; }"
            )
            remove.clicked.connect(
                lambda checked=False, entry=entry: self._delete_history(entry)
            )
            layout.addWidget(choose, 1)
            layout.addWidget(remove)
            action.setDefaultWidget(row)
            self.history_menu.addAction(action)

    @staticmethod
    def _history_label(entry: LogSearchHistoryEntry) -> str:
        label = entry.include
        if entry.exclude:
            label += f"  −  {entry.exclude}"
        return label if len(label) <= 44 else f"{label[:41]}…"

    def _restore_history(self, entry: LogSearchHistoryEntry) -> None:
        self.history_menu.close()
        self.pattern.setText(entry.include)
        self.exclude_pattern.setText(entry.exclude)
        lookback_index = self.lookback.findData(entry.lookback_seconds)
        self.lookback.setCurrentIndex(max(0, lookback_index))
        self.match_case.setChecked(entry.match_case)
        self.search()

    def _delete_history(self, entry: LogSearchHistoryEntry) -> None:
        self._history = [old for old in self._history if old != entry]
        self.settings.save_search_history(self._history)
        self._refresh_history()
        if self._history:
            self.history_menu.popup(self.history_button.mapToGlobal(self.history_button.rect().bottomLeft()))


    def _remember_search(self) -> None:
        entry = LogSearchHistoryEntry(
            include=self.pattern.text(),
            exclude=self.exclude_pattern.text(),
            lookback_seconds=self.lookback.currentData(),
            match_case=self.match_case.isChecked(),
        )
        self._history = [entry, *(old for old in self._history if old != entry)]
        self._history = self._history[: self.settings.SEARCH_HISTORY_LIMIT]
        self.settings.save_search_history(self._history)
        self._refresh_history()

    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
            return
        self.show()
        self.raise_()
        self.activateWindow()
        self.pattern.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.pattern.selectAll()

    def search(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        if self.log_path is None:
            self._show_error("No active EverQuest log.")
            return
        pattern = self.pattern.text()
        exclude_pattern = self.exclude_pattern.text()
        if not pattern:
            self._show_error("Enter words or a regex in Include.")
            return
        flags = 0 if self.match_case.isChecked() else re.IGNORECASE
        try:
            re.compile(pattern, flags)
        except re.error as error:
            self._show_error(f"Include regex: {error}")
            return
        try:
            if exclude_pattern:
                re.compile(exclude_pattern, flags)
        except re.error as error:
            self._show_error(f"Exclude regex: {error}")
            return

        self.search_button.setEnabled(False)
        self.status.setStyleSheet("color: #8e9aa6;")
        self.status.setText(f"Searching {self.log_path.name}…")
        self._worker = LogSearchWorker(
            self.log_path,
            pattern,
            exclude_pattern,
            self.lookback.currentData(),
            self.match_case.isChecked(),
            self,
        )
        self._worker.completed.connect(self._show_results)
        self._worker.failed.connect(self._show_error)
        self._worker.finished.connect(self._search_finished)
        self._worker.start()

    def _show_results(self, result: LogSearchResult) -> None:
        lines = tuple(reversed(result.lines))
        text = "\n".join(lines)
        self.results.setPlainText(text)
        self._highlight_matches(text)
        self._remember_search()
        suffix = " (latest 500; refine the regex)" if result.truncated else ""
        self.status.setStyleSheet("color: #8e9aa6;")
        self.status.setText(
            f"{len(result.lines):,} matches · {result.scanned_lines:,} lines scanned"
            f" · oldest → newest{suffix}"
        )
        self.results.moveCursor(QTextCursor.MoveOperation.End)

    def _highlight_matches(self, text: str) -> None:
        flags = 0 if self.match_case.isChecked() else re.IGNORECASE
        expression = re.compile(self.pattern.text(), flags)
        highlights: list[QTextEdit.ExtraSelection] = []
        match_format = QTextCharFormat()
        match_format.setForeground(QColor("#ffd166"))
        match_format.setFontWeight(QFont.Weight.Bold)
        offset = 0
        for line in text.splitlines(keepends=True):
            for match in expression.finditer(line.rstrip("\r\n")):
                if match.start() == match.end():
                    continue
                selection = QTextEdit.ExtraSelection()
                selection.format = match_format
                selection.cursor = QTextCursor(self.results.document())
                selection.cursor.setPosition(offset + match.start())
                selection.cursor.setPosition(
                    offset + match.end(),
                    QTextCursor.MoveMode.KeepAnchor,
                )
                highlights.append(selection)
            offset += len(line)
        self.results.setExtraSelections(highlights)

    def _show_error(self, message: str) -> None:
        self.status.setStyleSheet("color: #ff6b63;")
        self.status.setText(message)

    def _search_finished(self) -> None:
        self.search_button.setEnabled(True)
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._allow_close:
            event.accept()
            return
        self.hide()
        event.ignore()

    def shutdown(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait()
        self._allow_close = True
        self.close()
