import importlib
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

qt_core = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
qt_test = pytest.importorskip("PySide6.QtTest", exc_type=ImportError)
qt_widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
QApplication = qt_widgets.QApplication
QSettings = qt_core.QSettings
Qt = qt_core.Qt
QTest = qt_test.QTest
LogSearchResult = importlib.import_module("eql_combat_feed.log_search").LogSearchResult
LogSearchWindow = importlib.import_module("eql_combat_feed.search_window").LogSearchWindow
settings_module = importlib.import_module("eql_combat_feed.settings")
LogSearchHistoryEntry = settings_module.LogSearchHistoryEntry
SettingsStore = settings_module.SettingsStore


def make_window(tmp_path):
    settings = QSettings(str(tmp_path / "search-window.ini"), QSettings.Format.IniFormat)
    return LogSearchWindow(SettingsStore(settings))


def test_search_window_starts_hidden_and_toggles(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = make_window(tmp_path)

    assert window.isHidden()
    window.toggle()
    app.processEvents()
    assert window.isVisible()
    assert window.pattern.hasFocus()
    window.toggle()
    assert window.isHidden()

    window.shutdown()
    app.processEvents()


def test_escape_and_close_hide_search_window(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = make_window(tmp_path)
    window.show()

    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert window.isHidden()

    window.show()
    window.close()
    assert window.isHidden()

    window.shutdown()
    app.processEvents()


def test_search_window_reports_results_and_regex_errors(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "eqlog_Hero_freeport.txt"
    path.write_text("a match\n", encoding="utf-8")
    window = make_window(tmp_path)
    window.set_log_path(path)

    window.pattern.setText("(")
    window.search()
    assert "unterminated" in window.status.text().lower()
    assert window._worker is None

    window.exclude_pattern.setText("(")
    window.pattern.setText("valid")
    window.search()
    assert window.status.text().startswith("Exclude regex:")
    assert window._worker is None

    window.exclude_pattern.clear()
    window.pattern.setText("^new|old")
    window._show_results(LogSearchResult(("newest", "older old"), 17, truncated=True))
    assert window.results.toPlainText() == "older old\nnewest"
    selections = window.results.extraSelections()
    highlighted = [selection.cursor.selectedText() for selection in selections]
    assert highlighted == ["old", "old", "new"]
    highlight_format = selections[0].format
    assert highlight_format.background().style() == Qt.BrushStyle.NoBrush
    assert highlight_format.foreground().color().name() == "#ffd166"
    assert highlight_format.fontWeight() > 400
    assert "2 matches" in window.status.text()
    assert "oldest → newest" in window.status.text()
    assert "latest 500" in window.status.text()
    assert window.results.textCursor().atEnd()

    window.shutdown()
    app.processEvents()


def test_history_picker_restores_settings_and_reruns(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    store = SettingsStore(
        QSettings(str(tmp_path / "history-picker.ini"), QSettings.Format.IniFormat)
    )
    entry = LogSearchHistoryEntry("loot", "minor", 3600, True)
    store.save_search_history([entry])
    window = LogSearchWindow(store)
    calls = []
    monkeypatch.setattr(window, "search", lambda: calls.append(True))

    window._restore_history(entry)

    assert window.pattern.text() == "loot"
    assert window.exclude_pattern.text() == "minor"
    assert window.lookback.currentData() == 3600
    assert window.match_case.isChecked()
    assert calls == [True]

    window.pattern.setText("loot")
    window.exclude_pattern.setText("minor")
    window._remember_search()
    window._remember_search()
    assert window._history == [entry]
    assert len(window.history_menu.actions()) == 1

    history_action = window.history_menu.actions()[0]
    history_row = history_action.defaultWidget()
    remove = history_row.findChildren(qt_widgets.QPushButton)[1]
    QTest.mouseClick(remove, Qt.MouseButton.LeftButton)

    assert window._history == []
    assert store.load_search_history() == []
    empty = window.history_menu.actions()[0]
    assert empty.text() == "No recent searches"
    assert not empty.isEnabled()

    window.shutdown()
    app.processEvents()
