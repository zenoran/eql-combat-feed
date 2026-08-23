"""Frameless, high-contrast, single-actor damage feed window."""

from dataclasses import dataclass
from typing import Literal

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QToolTip, QWidget

from .dps import DpsSnapshot
from .models import CombatEvent, EventKind
from .settings import OverlayPreferences

Actor = Literal["character", "pet"]
ResizeEdge = Literal["left", "right", "top", "bottom"]


@dataclass(slots=True)
class DisplayEntry:
    event: CombatEvent


CHARACTER_HEADER = QColor("#ffff00")
PET_HEADER = QColor("#00ffff")
CHARACTER_AMOUNT = QColor("#ffff00")
PET_AMOUNT = QColor("#00ffff")
DPS_COLOR = QColor("#7dff00")
HEADER_BACKDROP_COLOR = QColor(4, 7, 10, 210)
HEADER_DPS_BACKDROP_COLOR = QColor(0, 0, 0, 175)
BACKDROP_COLOR = QColor(0, 0, 0, 190)
HIT_SURFACE_COLOR = QColor(0, 0, 0, 1)
SOURCE_COLORS = {
    EventKind.MELEE: QColor("#ffff00"),
    EventKind.SKILL: QColor("#ff9d00"),
    EventKind.RANGED: QColor("#7dff00"),
    EventKind.SPELL: QColor("#ff3dff"),
    EventKind.PROC: QColor("#8b7dff"),
    EventKind.PET: QColor("#00ffff"),
    EventKind.MISS: QColor("#ffffff"),
}
CHARACTER_DAMAGE_KINDS = frozenset(
    {
        EventKind.MELEE,
        EventKind.SKILL,
        EventKind.RANGED,
        EventKind.SPELL,
        EventKind.PROC,
    }
)


class CombatFeedOverlay(QWidget):
    position_changed = Signal(QPoint)
    size_changed = Signal(QSize)
    context_requested = Signal(QPoint)
    options_requested = Signal()
    quit_requested = Signal()

    BASE_WIDTH = 600
    ROW_HEIGHT = 31
    PADDING = 8
    TITLE_HEIGHT = 27
    HEADER_HEIGHT = 23
    HEADER_FEED_GAP = 1
    ICON_WIDTH = 34.0
    ICON_AMOUNT_GAP = 8.0
    DESCRIPTION_ICON_GAP = 10.0
    RESIZE_MARGIN = 18
    MIN_WIDTH = 240
    # Worst plausible damage / DPS strings — the amount lane is sized to fit
    # these and never grows, so extra window width all goes to descriptions.
    AMOUNT_TEMPLATE = "888,888"
    DPS_TEMPLATE = "99,999 DPS"
    MIN_DESCRIPTION_WIDTH = 24.0
    MISS_SCALE = 0.75
    HEADER_FONT_BASE = 16.8
    HEADER_ACTOR_GAP = 12.0
    HEADER_DPS_GAP = 8.0

    def __init__(self, preferences: OverlayPreferences, actor: Actor = "character") -> None:
        super().__init__()
        self.preferences = preferences
        self.actor = actor
        self._entries: list[DisplayEntry] = []
        self._history_offset = 0
        self._status = "Waiting for damage…"
        self._status_error = False
        self._drag_origin: QPoint | None = None
        self._window_origin: QPoint | None = None
        self._resize_origin: QPoint | None = None
        self._resize_geometry: QRect | None = None
        self._resize_edges: frozenset[ResizeEdge] = frozenset()
        self._hover_resize_edges: frozenset[ResizeEdge] = frozenset()
        self._controls_visible = False
        self._locked = False
        self._dps = DpsSnapshot()

        actor_name = "You" if actor == "character" else "Pet"
        self.setWindowTitle(f"EQL Combat Feed — {actor_name}")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setMinimumSize(self.MIN_WIDTH, round(self._minimum_height()))
        self._restore_size(self._saved_size())
        self.set_locked(preferences.locked)

    @property
    def locked(self) -> bool:
        return self._locked

    @property
    def text_scale(self) -> float:
        return self.preferences.damage_font_size / 21.0

    @property
    def header_scale(self) -> float:
        return self.preferences.header_font_size / self.HEADER_FONT_BASE

    @property
    def entries(self) -> tuple[DisplayEntry, ...]:
        return tuple(self._entries)

    def apply_preferences(self, preferences: OverlayPreferences) -> None:
        self.preferences = preferences
        self._entries = self._entries[-preferences.history_rows :]
        self._clamp_history_offset()
        self.setMinimumSize(self.MIN_WIDTH, round(self._minimum_height()))
        if self.height() < self.minimumHeight():
            self.resize(self.width(), self.minimumHeight())
        self.set_locked(preferences.locked)
        self.update()

    def set_locked(self, locked: bool) -> None:
        was_visible = self.isVisible()
        self._locked = locked
        if locked:
            self._controls_visible = False
            self._hover_resize_edges = frozenset()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, locked)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, locked)
        self.setCursor(Qt.CursorShape.ArrowCursor if locked else Qt.CursorShape.SizeAllCursor)
        if was_visible:
            self.show()
        self.update()

    def add_event(self, event: CombatEvent) -> bool:
        if self._actor_for_event(event) != self.actor:
            return False
        if self._history_offset:
            self._history_offset += 1
        self._entries.append(DisplayEntry(event))
        overflow = max(0, len(self._entries) - self.preferences.history_rows)
        if overflow:
            del self._entries[:overflow]
        self._clamp_history_offset()
        self.update()
        return True

    def set_status(self, message: str, *, error: bool = False) -> None:
        self._status = message
        self._status_error = error
        self.update()

    def set_dps(self, snapshot: DpsSnapshot) -> None:
        if snapshot == self._dps:
            return
        self._dps = snapshot
        self.update()

    def clear_entries(self) -> None:
        self._entries.clear()
        self._history_offset = 0
        self.update()

    def tick(self) -> None:
        return

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._locked:
            painter.fillRect(self.rect(), HIT_SURFACE_COLOR)
        if self._controls_visible and not self._locked:
            self._paint_title(painter)
        if (self._controls_visible or self._hover_resize_edges) and not self._locked:
            self._paint_resize_handles(painter)
        self._paint_header(painter)
        self._paint_feed(painter)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._locked:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if self._controls_visible and self._options_rect().contains(event.position()):
                self.options_requested.emit()
                event.accept()
                return
            if self._controls_visible and self._quit_rect().contains(event.position()):
                self.quit_requested.emit()
                event.accept()
                return
            edges = self._resize_edges_at(event.position())
            if edges:
                self._resize_edges = edges
                self._resize_origin = event.globalPosition().toPoint()
                self._resize_geometry = self.geometry()
                event.accept()
                return
            self._drag_origin = event.globalPosition().toPoint()
            self._window_origin = self.pos()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.context_requested.emit(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._resize_origin is not None and self._resize_geometry is not None:
            self._continue_resize(event.globalPosition().toPoint())
            event.accept()
            return
        if self._drag_origin is not None and self._window_origin is not None:
            self.move(self._window_origin + event.globalPosition().toPoint() - self._drag_origin)
            event.accept()
            return
        self._update_hover_state(event.position())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._resize_origin is not None:
            self._resize_origin = None
            self._resize_geometry = None
            self._resize_edges = frozenset()
            self.size_changed.emit(self.size())
            self._update_hover_state(event.position())
            event.accept()
            return
        if self._drag_origin is not None:
            self._drag_origin = None
            self._window_origin = None
            self.position_changed.emit(self.pos())
            event.accept()

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._drag_origin is None and self._resize_origin is None:
            changed = self._controls_visible or bool(self._hover_resize_edges)
            self._controls_visible = False
            self._hover_resize_edges = frozenset()
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            if changed:
                self.update()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if not self._locked and event.button() == Qt.MouseButton.LeftButton:
            self.clear_entries()
            event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._locked or len(self._entries) <= self._visible_row_capacity():
            event.ignore()
            return
        steps = event.angleDelta().y() // 120
        if steps == 0:
            pixel_y = event.pixelDelta().y()
            if pixel_y == 0:
                event.ignore()
                return
            steps = 1 if pixel_y > 0 else -1
        self._history_offset += steps
        self._clamp_history_offset()
        self.update()
        event.accept()

    def event(self, event) -> bool:  # type: ignore[no-untyped-def]
        if event.type() == QEvent.Type.ToolTip and not self._locked:
            # QHelpEvent is pre-Qt6 API: pos()/globalPos(), not position().
            point = QPointF(event.pos())
            if self._controls_visible and self._options_rect().contains(point):
                QToolTip.showText(event.globalPos(), "Options", self)
                return True
            if self._controls_visible and self._quit_rect().contains(point):
                QToolTip.showText(event.globalPos(), "Quit EQL Combat Feed", self)
                return True
            entry = self._entry_at(point)
            if entry is not None:
                target = entry.event.target or "—"
                source = entry.event.source or "You"
                critical = " · CRITICAL" if entry.event.critical else ""
                text = (
                    f"{source} · {self._source_label(entry.event)} · "
                    f"{entry.event.amount:,} → {target}{critical}"
                )
                QToolTip.showText(event.globalPos(), text, self)
                return True
        return super().event(event)

    @staticmethod
    def _actor_for_event(event: CombatEvent) -> Actor | None:
        if event.incoming or event.kind is EventKind.DAMAGE_SHIELD:
            return None
        if event.kind is EventKind.PET:
            return "pet" if event.amount > 0 else None
        if event.kind is EventKind.MISS:
            return "pet" if event.source and event.source.casefold() != "you" else "character"
        if event.amount > 0 and event.kind in CHARACTER_DAMAGE_KINDS:
            return "character"
        return None

    def _visible_entries(self) -> list[DisplayEntry]:
        end = len(self._entries) - self._history_offset
        start = max(0, end - self._visible_row_capacity())
        return self._entries[start:end]

    def _clamp_history_offset(self) -> None:
        maximum = max(0, len(self._entries) - self._visible_row_capacity())
        self._history_offset = max(0, min(maximum, self._history_offset))

    def _font(self, family: str, base_size: float, weight: QFont.Weight) -> QFont:
        font = QFont(family)
        font.setPointSizeF(base_size * self.text_scale)
        font.setWeight(weight)
        return font

    def _row_height(self) -> float:
        return self.ROW_HEIGHT * self.text_scale

    def _title_height(self) -> float:
        return self.TITLE_HEIGHT * self.text_scale

    def _header_height(self) -> float:
        return self.HEADER_HEIGHT * self.header_scale

    def _content_top(self) -> float:
        actor_rect, marker_rect, dps_rect = self._header_rects()
        content_bounds = self._header_content_bounds(
            actor_rect,
            marker_rect,
            dps_rect,
            self._header_font(QFont.Weight.Black),
            self._header_font(QFont.Weight.Bold),
        )
        background = self._header_background_rect(content_bounds)
        return self._header_divider_y(background) + self.HEADER_FEED_GAP * self.text_scale

    def _content_rect(self) -> QRectF:
        return QRectF(
            self.PADDING,
            self._content_top(),
            self.width() - self.PADDING * 2,
            self._visible_row_capacity() * self._row_height(),
        )

    def _entry_at(self, point: QPointF) -> DisplayEntry | None:
        index = int((point.y() - self._content_top()) // self._row_height())
        if index < 0:
            return None
        visible = self._visible_entries()
        return visible[index] if index < len(visible) else None

    def _minimum_height(self) -> float:
        return self._content_top() + self.PADDING + self._row_height()

    def _default_height(self) -> float:
        return (
            self._content_top()
            + self.PADDING
            + self.preferences.max_rows * self._row_height()
        )

    def _visible_row_capacity(self) -> int:
        available = max(0.0, self.height() - self._content_top())
        physical_rows = max(1, int((available + 0.5) // self._row_height()))
        return min(self.preferences.max_rows, physical_rows)

    def _saved_size(self) -> QSize | None:
        return self.preferences.size if self.actor == "character" else self.preferences.pet_size

    def _restore_size(self, saved: QSize | None) -> None:
        if saved is None or saved.width() <= 0 or saved.height() <= 0:
            self.resize(self.BASE_WIDTH, round(self._default_height()))
        else:
            self.resize(
                max(self.MIN_WIDTH, saved.width()),
                max(round(self._minimum_height()), saved.height()),
            )

    def _resize_edges_at(self, point: QPointF) -> frozenset[ResizeEdge]:
        margin = float(self.RESIZE_MARGIN)
        edges: set[ResizeEdge] = set()
        if point.x() <= margin:
            edges.add("left")
        elif point.x() >= self.width() - margin:
            edges.add("right")
        if point.y() <= margin:
            edges.add("top")
        elif point.y() >= self.height() - margin:
            edges.add("bottom")
        return frozenset(edges)

    def _continue_resize(self, global_point: QPoint) -> None:
        if self._resize_origin is None or self._resize_geometry is None:
            return
        delta = global_point - self._resize_origin
        original = self._resize_geometry
        width = original.width()
        height = original.height()
        x = original.left()
        y = original.top()
        if "left" in self._resize_edges:
            width = max(self.minimumWidth(), original.width() - delta.x())
            x = original.right() - width + 1
        elif "right" in self._resize_edges:
            width = max(self.minimumWidth(), original.width() + delta.x())
        if "top" in self._resize_edges:
            height = max(self.minimumHeight(), original.height() - delta.y())
            y = original.bottom() - height + 1
        elif "bottom" in self._resize_edges:
            height = max(self.minimumHeight(), original.height() + delta.y())
        self.setGeometry(x, y, width, height)
        self._clamp_history_offset()
        self.update()

    def _update_hover_state(self, point: QPointF) -> None:
        controls_visible = point.y() <= self.PADDING + self._title_height()
        resize_edges = self._resize_edges_at(point)
        if controls_visible != self._controls_visible or resize_edges != self._hover_resize_edges:
            self._controls_visible = controls_visible
            self._hover_resize_edges = resize_edges
            self.update()
        self._set_resize_cursor(resize_edges)

    def _set_resize_cursor(self, edges: frozenset[ResizeEdge]) -> None:
        if not edges:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        elif ({"left", "top"} <= edges) or ({"right", "bottom"} <= edges):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif ({"right", "top"} <= edges) or ({"left", "bottom"} <= edges):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif "left" in edges or "right" in edges:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeVerCursor)

    def _paint_title(self, painter: QPainter) -> None:
        rect = QRectF(
            self.PADDING,
            self.PADDING,
            self.width() - self.PADDING * 2,
            self._title_height() - 3,
        )
        path = QPainterPath()
        path.addRoundedRect(rect, 7, 7)
        painter.fillPath(path, QColor(5, 7, 10, 255))
        painter.setPen(QPen(QColor(255, 190, 60, 255), 1.5))
        painter.drawPath(path)
        painter.setPen(QColor(255, 242, 211))
        painter.setFont(self._font("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(
            rect.adjusted(10, 0, -60, 0),
            Qt.AlignmentFlag.AlignVCenter,
            self._title_text(),
        )
        self._paint_title_button(painter, self._options_rect(), "⚙", QColor("#ffe4a6"))
        self._paint_title_button(painter, self._quit_rect(), "×", QColor("#ff8b85"))

    def _title_text(self) -> str:
        if self._status_error:
            return self._status.upper()
        actor = "YOU" if self.actor == "character" else "PET"
        history = " · HISTORY" if self._history_offset else ""
        return f"{actor} DAMAGE{history}"

    def _paint_header(self, painter: QPainter) -> None:
        actor_rect, marker_rect, dps_rect = self._header_rects()
        actor = "YOU" if self.actor == "character" else "PET"
        accent = CHARACTER_HEADER if self.actor == "character" else PET_HEADER
        actor_font = self._header_font(QFont.Weight.Black)
        dps_font = self._header_font(QFont.Weight.Bold)

        content_bounds = self._header_content_bounds(
            actor_rect,
            marker_rect,
            dps_rect,
            actor_font,
            dps_font,
        )
        background_rect = self._header_background_rect(content_bounds)
        background = self._header_background_gradient(background_rect, content_bounds)
        background_path = QPainterPath()
        background_path.addRoundedRect(background_rect, 5, 5)
        painter.fillPath(background_path, background)

        marker_path = QPainterPath()
        marker_path.addRoundedRect(marker_rect, marker_rect.width() / 2, marker_rect.width() / 2)
        painter.fillPath(marker_path, QColor(accent.red(), accent.green(), accent.blue(), 220))

        self._draw_outlined_text(
            painter,
            actor_rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            actor,
            accent,
            actor_font,
        )
        if self._dps.duration > 0:
            self._draw_outlined_text(
                painter,
                dps_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._format_dps(self._dps.dps),
                DPS_COLOR,
                dps_font,
            )

    @staticmethod
    def _header_divider_y(background_rect: QRectF) -> float:
        # Visual bottom seam for content layout; no underline is painted.
        return background_rect.bottom()

    def _header_content_bounds(
        self,
        actor_rect: QRectF,
        marker_rect: QRectF,
        dps_rect: QRectF,
        actor_font: QFont,
        dps_font: QFont,
    ) -> QRectF:
        actor = "YOU" if self.actor == "character" else "PET"
        actor_bounds = self._text_backdrop_rect(
            actor_rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            actor,
            actor_font,
        )
        content = actor_bounds.united(marker_rect)
        if self._dps.duration > 0:
            dps_bounds = self._text_backdrop_rect(
                dps_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._format_dps(self._dps.dps),
                dps_font,
            )
            content = content.united(dps_bounds)
        return content.adjusted(-7, -2, 7, 2)

    def _header_background_rect(self, content_bounds: QRectF) -> QRectF:
        return QRectF(
            self.PADDING,
            content_bounds.top(),
            self.width() - self.PADDING * 2,
            content_bounds.height(),
        )

    @staticmethod
    def _header_background_gradient(
        background_rect: QRectF, content_bounds: QRectF
    ) -> QLinearGradient:
        gradient = QLinearGradient(background_rect.left(), 0, background_rect.right(), 0)
        width = max(1.0, background_rect.width())
        content_start = max(
            0.0, min(1.0, (content_bounds.left() - background_rect.left()) / width)
        )
        content_end = max(
            0.0, min(1.0, (content_bounds.right() - background_rect.left()) / width)
        )
        feather = min(0.16, max(0.06, (content_end - content_start) * 0.55))
        gradient.setColorAt(0.0, QColor(3, 5, 8, 0))
        gradient.setColorAt(max(0.0, content_start - feather), QColor(3, 5, 8, 35))
        gradient.setColorAt(content_start, HEADER_BACKDROP_COLOR)
        gradient.setColorAt(content_end, HEADER_BACKDROP_COLOR)
        gradient.setColorAt(min(1.0, content_end + feather), QColor(3, 5, 8, 35))
        gradient.setColorAt(1.0, QColor(3, 5, 8, 0))
        return gradient

    def _header_font(self, weight: QFont.Weight) -> QFont:
        font = QFont("Segoe UI")
        font.setPointSizeF(self.preferences.header_font_size)
        font.setWeight(weight)
        return font

    def _header_rects(self) -> tuple[QRectF, QRectF, QRectF]:
        row = QRectF(
            self.PADDING,
            self.PADDING + self._title_height() - 1,
            self.width() - self.PADDING * 2,
            self._header_height(),
        )
        actor = "YOU" if self.actor == "character" else "PET"
        actor_width = QFontMetricsF(
            self._header_font(QFont.Weight.Black)
        ).horizontalAdvance(actor) + 8
        dps_width = QFontMetricsF(
            self._header_font(QFont.Weight.Bold)
        ).horizontalAdvance(self.DPS_TEMPLATE) + 8
        marker_width = max(2.0, 2.5 * self.header_scale)
        marker_height = min(row.height() * 0.56, 14 * self.header_scale)
        actor_gap = max(8.0, self.HEADER_ACTOR_GAP * self.header_scale)
        dps_gap = max(5.0, self.HEADER_DPS_GAP * self.header_scale)
        cluster_width = actor_width + actor_gap + marker_width + dps_gap + dps_width
        outline_safe_right = self.width() - 3
        cluster_left = max(row.left(), outline_safe_right - cluster_width)

        actor_rect = QRectF(cluster_left, row.top(), actor_width, row.height())
        marker_left = actor_rect.right() + actor_gap
        marker_rect = QRectF(
            marker_left,
            row.center().y() - marker_height / 2,
            marker_width,
            marker_height,
        )
        dps_rect = QRectF(
            marker_rect.right() + dps_gap,
            row.top(),
            dps_width,
            row.height(),
        )
        return actor_rect, marker_rect, dps_rect

    @staticmethod
    def _format_dps(value: float) -> str:
        rounded = max(0, round(value))
        if rounded > 99_999:
            return f"{round(rounded / 1000):,}K DPS"
        return f"{rounded:,} DPS"

    def _paint_feed(self, painter: QPainter) -> None:
        content = self._content_rect()
        for index, entry in enumerate(self._visible_entries()):
            rect = QRectF(
                content.left(),
                self._content_top() + index * self._row_height(),
                content.width(),
                self._row_height(),
            )
            self._paint_entry(painter, rect, entry.event)

    def _paint_entry(self, painter: QPainter, rect: QRectF, event: CombatEvent) -> None:
        description, icon = self._source_parts(event, self.actor)
        label_color = SOURCE_COLORS[event.kind]
        amount_color = self._amount_color(event, self.actor)
        amount_text = "MISS" if event.kind is EventKind.MISS else f"{event.amount:,}"
        description_rect, icon_rect, amount_rect = self._entry_rects(rect)

        description_font = self._font("Segoe UI", 12, QFont.Weight.Black)
        painter.setFont(description_font)
        description = painter.fontMetrics().elidedText(
            description,
            Qt.TextElideMode.ElideLeft,
            max(20, round(description_rect.width())),
        )
        if description:
            self._draw_backed_outlined_text(
                painter,
                description_rect,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                description,
                label_color,
                description_font,
            )
        icon_font, amount_font = self._entry_value_fonts(event)
        # Icons intentionally have no backdrop; only the heavy outline separates them.
        self._draw_outlined_text(
            painter,
            icon_rect,
            Qt.AlignmentFlag.AlignCenter,
            icon,
            label_color,
            icon_font,
        )
        self._draw_backed_outlined_text(
            painter,
            amount_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            amount_text,
            amount_color,
            amount_font,
        )

    def _entry_value_fonts(self, event: CombatEvent) -> tuple[QFont, QFont]:
        scale = self.MISS_SCALE if event.kind is EventKind.MISS else 1.0
        return (
            self._font("Segoe UI Symbol", 17 * scale, QFont.Weight.Black),
            self._font("Segoe UI", 21 * scale, QFont.Weight.Black),
        )

    def _amount_lane_width(self) -> float:
        amount_font = self._font("Segoe UI", 21, QFont.Weight.Black)
        return QFontMetricsF(amount_font).horizontalAdvance(self.AMOUNT_TEMPLATE) + 8

    def _entry_rects(self, rect: QRectF) -> tuple[QRectF, QRectF, QRectF]:
        icon_width = self.ICON_WIDTH * self.text_scale
        description_gap = self.DESCRIPTION_ICON_GAP * self.text_scale
        amount_gap = self.ICON_AMOUNT_GAP * self.text_scale
        # Anchor the spine to the right: the amount lane is fixed-width (damage
        # text has a known ceiling), so widening the window only grows the
        # description lane instead of piling empty space right of the numbers.
        spine_x = rect.right() - self._amount_lane_width() - amount_gap - icon_width / 2
        spine_x = max(spine_x, rect.left() + self.MIN_DESCRIPTION_WIDTH + icon_width / 2)
        icon_rect = QRectF(
            spine_x - icon_width / 2,
            rect.top(),
            icon_width,
            rect.height(),
        )
        description_rect = QRectF(
            rect.left() + 4,
            rect.top(),
            max(20.0, icon_rect.left() - description_gap - rect.left() - 4),
            rect.height(),
        )
        amount_rect = QRectF(
            icon_rect.right() + amount_gap,
            rect.top(),
            max(20.0, rect.right() - icon_rect.right() - amount_gap),
            rect.height(),
        )
        return description_rect, icon_rect, amount_rect

    @staticmethod
    def _source_parts(event: CombatEvent, actor: Actor) -> tuple[str, str]:
        ability = (event.ability or "Melee").upper()
        physical_skills = {"KICK", "BASH", "BACKSTAB", "FRENZY", "SLAM", "CLEAVE", "REAVE"}
        if event.kind is EventKind.MISS:
            return (ability, "◆") if ability in physical_skills else ("", "⚔")
        if event.kind is EventKind.MELEE:
            return "", "⚔"
        if event.kind is EventKind.SKILL:
            return ability, "◆"
        if event.kind is EventKind.RANGED:
            return ability, "➶"
        if event.kind is EventKind.SPELL:
            return ability, "✦"
        if event.kind is EventKind.PROC:
            return ability, "ϟ"
        if actor == "pet":
            if ability == "MELEE":
                return "", "⚔"
            return (ability, "◆") if ability in physical_skills else (ability, "✦")
        return ability, "•"

    @staticmethod
    def _amount_color(event: CombatEvent, actor: Actor) -> QColor:
        if event.critical:
            return QColor("#ff2020")
        if event.kind is EventKind.MISS:
            return QColor("#ffffff")
        return CHARACTER_AMOUNT if actor == "character" else PET_AMOUNT

    def _paint_title_button(
        self, painter: QPainter, rect: QRectF, text: str, color: QColor
    ) -> None:
        painter.setPen(color)
        painter.setFont(self._font("Segoe UI Symbol", 11, QFont.Weight.Bold))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_resize_handles(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor(255, 190, 60, 220), 1.5))
        length = 10
        inset = 3
        for x, x_dir in ((inset, 1), (self.width() - inset, -1)):
            for y, y_dir in ((inset, 1), (self.height() - inset, -1)):
                painter.drawLine(QPointF(x, y), QPointF(x + length * x_dir, y))
                painter.drawLine(QPointF(x, y), QPointF(x, y + length * y_dir))

    def _options_rect(self) -> QRectF:
        button_size = 22 * self.text_scale
        return QRectF(
            self.width() - self.PADDING - button_size * 2 - 3,
            self.PADDING + 1,
            button_size,
            self._title_height() - 5,
        )

    def _quit_rect(self) -> QRectF:
        button_size = 22 * self.text_scale
        return QRectF(
            self.width() - self.PADDING - button_size,
            self.PADDING + 1,
            button_size,
            self._title_height() - 5,
        )

    @staticmethod
    def _text_backdrop_rect(
        rect: QRectF, alignment: Qt.AlignmentFlag, text: str, font: QFont
    ) -> QRectF:
        metrics = QFontMetricsF(font)
        glyphs = metrics.tightBoundingRect(text)
        advance = metrics.horizontalAdvance(text)
        if alignment & Qt.AlignmentFlag.AlignRight:
            origin_x = rect.right() - advance
        elif alignment & Qt.AlignmentFlag.AlignHCenter:
            origin_x = rect.center().x() - advance / 2
        else:
            origin_x = rect.left()
        if alignment & Qt.AlignmentFlag.AlignBottom:
            baseline = rect.bottom() - metrics.descent()
        elif alignment & Qt.AlignmentFlag.AlignVCenter:
            baseline = rect.center().y() + (metrics.ascent() - metrics.descent()) / 2
        else:
            baseline = rect.top() + metrics.ascent()
        # Text/value backing gets 2px vertical breathing room; icons get none at all.
        return glyphs.translated(origin_x, baseline).adjusted(-4, -2, 4, 2)

    @classmethod
    def _draw_backed_outlined_text(
        cls,
        painter: QPainter,
        rect: QRectF,
        alignment: Qt.AlignmentFlag,
        text: str,
        color: QColor,
        font: QFont,
    ) -> None:
        path = QPainterPath()
        path.addRoundedRect(cls._text_backdrop_rect(rect, alignment, text, font), 3, 3)
        painter.fillPath(path, BACKDROP_COLOR)
        cls._draw_outlined_text(painter, rect, alignment, text, color, font)

    @staticmethod
    def _draw_outlined_text(
        painter: QPainter,
        rect: QRectF,
        alignment: Qt.AlignmentFlag,
        text: str,
        color: QColor,
        font: QFont,
    ) -> None:
        painter.setFont(font)
        painter.setPen(QColor(0, 0, 0, 255))
        for dx, dy in (
            (-3.0, 0.0),
            (3.0, 0.0),
            (0.0, -3.0),
            (0.0, 3.0),
            (-2.2, -2.2),
            (2.2, -2.2),
            (-2.2, 2.2),
            (2.2, 2.2),
        ):
            painter.drawText(rect.translated(dx, dy), alignment, text)
        painter.setPen(color)
        painter.drawText(rect, alignment, text)

    @staticmethod
    def _source_label(event: CombatEvent) -> str:
        return event.ability or event.kind.value.replace("_", " ").title()
