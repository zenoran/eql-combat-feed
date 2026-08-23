import importlib
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

qt_core = pytest.importorskip("PySide6.QtCore", exc_type=ImportError)
qt_gui = pytest.importorskip("PySide6.QtGui", exc_type=ImportError)
qt_test = pytest.importorskip("PySide6.QtTest", exc_type=ImportError)
qt_widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
QPoint = qt_core.QPoint
QPointF = qt_core.QPointF
QRectF = qt_core.QRectF
QSize = qt_core.QSize
Qt = qt_core.Qt
QApplication = qt_widgets.QApplication
QColor = qt_gui.QColor
QFont = qt_gui.QFont
QFontMetricsF = qt_gui.QFontMetricsF
QImage = qt_gui.QImage
QTest = qt_test.QTest

dps_module = importlib.import_module("eql_combat_feed.dps")
models = importlib.import_module("eql_combat_feed.models")
overlay_module = importlib.import_module("eql_combat_feed.overlay")
settings_module = importlib.import_module("eql_combat_feed.settings")
DpsSnapshot = dps_module.DpsSnapshot
CombatEvent = models.CombatEvent
EventKind = models.EventKind
CombatFeedOverlay = overlay_module.CombatFeedOverlay
OverlayPreferences = settings_module.OverlayPreferences


def event(
    amount: int,
    kind: EventKind = EventKind.MELEE,
    *,
    ability: str = "Melee",
    incoming: bool = False,
) -> CombatEvent:
    return CombatEvent(
        timestamp=float(amount),
        kind=kind,
        amount=amount,
        ability=ability,
        target="a gargoyle",
        incoming=incoming,
        source="A deathly harbinger" if kind is EventKind.PET else "You",
    )


def render(overlay: CombatFeedOverlay) -> QImage:
    image = QImage(overlay.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    overlay.render(image)
    return image


def row_rect(overlay: CombatFeedOverlay, index: int = 0) -> QRectF:
    content = overlay._content_rect()
    return QRectF(
        content.left(),
        overlay._content_top() + index * overlay._row_height(),
        content.width(),
        overlay._row_height(),
    )


def test_each_actor_window_accepts_only_its_own_events() -> None:
    app = QApplication.instance() or QApplication([])
    preferences = OverlayPreferences(max_rows=3, history_rows=10)
    you = CombatFeedOverlay(preferences, "character")
    pet = CombatFeedOverlay(preferences, "pet")

    character_hit = event(124, EventKind.SPELL, ability="Lifedraw")
    pet_hit = event(66, EventKind.PET, ability="Cleave")
    assert you.add_event(character_hit) is True
    assert you.add_event(pet_hit) is False
    assert pet.add_event(character_hit) is False
    assert pet.add_event(pet_hit) is True

    assert [item.event for item in you.entries] == [character_hit]
    assert [item.event for item in pet.entries] == [pet_hit]
    assert you._source_parts(character_hit, "character") == ("LIFEDRAW", "✦")
    assert pet._source_parts(pet_hit, "pet") == ("CLEAVE", "◆")

    you.close()
    pet.close()
    app.processEvents()


def test_misses_route_correctly_but_incoming_heal_and_thorns_do_not() -> None:
    app = QApplication.instance() or QApplication([])
    you = CombatFeedOverlay(OverlayPreferences(), "character")
    pet = CombatFeedOverlay(OverlayPreferences(), "pet")
    character_miss = event(0, EventKind.MISS, ability="Reave")
    pet_miss = CombatEvent(
        timestamp=2.0,
        kind=EventKind.MISS,
        ability="Melee",
        target="a gargoyle",
        source="A deathly harbinger",
    )
    noise = [
        event(44, incoming=True),
        event(75, EventKind.HEAL, ability="Lifedraw"),
        event(12, EventKind.DAMAGE_SHIELD, ability="Thorns shield"),
    ]

    for combat_event in [*noise, character_miss, pet_miss]:
        you.add_event(combat_event)
        pet.add_event(combat_event)

    assert [item.event for item in you.entries] == [character_miss]
    assert [item.event for item in pet.entries] == [pet_miss]
    assert all(CombatFeedOverlay._actor_for_event(item) is None for item in noise)

    you.close()
    pet.close()
    app.processEvents()


def test_single_window_history_cap_offset_and_new_activity_hold() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(
        OverlayPreferences(max_rows=2, history_rows=4, size=QSize(600, 300)),
        "character",
    )
    for amount in range(1, 6):
        overlay.add_event(event(amount))

    assert [item.event.amount for item in overlay.entries] == [2, 3, 4, 5]
    overlay._history_offset = 1
    assert [item.event.amount for item in overlay._visible_entries()] == [3, 4]
    overlay.add_event(event(6))
    assert overlay._history_offset == 2
    assert [item.event.amount for item in overlay._visible_entries()] == [3, 4]

    overlay.close()
    app.processEvents()


def test_row_pitch_is_dense_and_scales_with_text() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(OverlayPreferences(font_scale=1.3), "character")

    assert overlay.ROW_HEIGHT == 34
    assert overlay._row_height() == pytest.approx(44.2)
    assert overlay._row_height() < 45

    overlay.close()
    app.processEvents()


def test_icon_has_no_backdrop_while_text_backdrop_has_two_vertical_pixels() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(OverlayPreferences(font_scale=1.3), "character")
    spell = event(123, EventKind.SPELL, ability="Lifedraw")
    overlay.add_event(spell)

    image = render(overlay)
    description_rect, icon_rect, amount_rect = overlay._entry_rects(row_rect(overlay))
    description_font = overlay._font("Segoe UI", 12, QFont.Weight.Black)
    amount_font = overlay._font("Segoe UI", 21, QFont.Weight.Black)
    description_backdrop = overlay._text_backdrop_rect(
        description_rect,
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        "LIFEDRAW",
        description_font,
    )
    amount_backdrop = overlay._text_backdrop_rect(
        amount_rect,
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        "123",
        amount_font,
    )
    glyph_height = QFontMetricsF(description_font).tightBoundingRect("LIFEDRAW").height()

    assert description_backdrop.height() == pytest.approx(glyph_height + 4)
    assert amount_backdrop.height() > QFontMetricsF(amount_font).tightBoundingRect("123").height()
    # A pixel near the icon-box corner is only the alpha-1 hit surface, not a plate.
    icon_corner = image.pixelColor(round(icon_rect.left() + 2), round(icon_rect.top() + 2))
    description_plate = image.pixelColor(
        round(description_backdrop.left() + 2), round(description_backdrop.center().y())
    )
    assert icon_corner.alpha() <= 1
    assert description_plate.alpha() >= 180

    overlay.close()
    app.processEvents()


def test_header_uses_the_same_three_lanes_as_damage_rows() -> None:
    app = QApplication.instance() or QApplication([])
    for actor in ("character", "pet"):
        overlay = CombatFeedOverlay(OverlayPreferences(size=QSize(772, 400)), actor)
        overlay.set_dps(DpsSnapshot(damage=1234, duration=10.0, active=True))
        header_row = QRectF(
            overlay.PADDING,
            overlay.PADDING + overlay._title_height() - 1,
            overlay.width() - overlay.PADDING * 2,
            overlay._header_height(),
        )
        actor_rect, divider_rect, dps_rect = overlay._entry_rects(header_row)
        _, icon_rect, damage_rect = overlay._entry_rects(row_rect(overlay))

        assert actor_rect.right() == pytest.approx(icon_rect.left() - 6 * overlay.text_scale)
        assert divider_rect.center().x() == pytest.approx(icon_rect.center().x())
        assert dps_rect.left() == pytest.approx(damage_rect.left())
        assert overlay._title_text().startswith("YOU" if actor == "character" else "PET")

        image = render(overlay)
        divider_pixel = image.pixelColor(
            round(divider_rect.center().x()), round(divider_rect.center().y())
        )
        assert divider_pixel.alpha() > 150
        assert max(divider_pixel.red(), divider_pixel.green(), divider_pixel.blue()) < 130
        overlay.close()
    app.processEvents()


def test_dps_badge_is_distinct_and_formats_compactly() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(OverlayPreferences(size=QSize(772, 400)), "character")
    overlay.set_dps(DpsSnapshot(damage=1234, duration=10.0, active=True))

    assert QColor("#7dff00") == overlay_module.DPS_COLOR
    assert overlay._format_dps(123.4) == "123.4 DPS"
    assert overlay._format_dps(1200) == "1.2K DPS"
    assert overlay._format_dps(12) == "12 DPS"

    overlay.close()
    app.processEvents()


def test_pet_header_shows_zero_dps_during_shared_active_encounter() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(OverlayPreferences(size=QSize(600, 400)), "pet")
    overlay.set_dps(DpsSnapshot(damage=0, duration=4.0, active=True))

    image = render(overlay)
    header_row = QRectF(
        overlay.PADDING,
        overlay.PADDING + overlay._title_height() - 1,
        overlay.width() - overlay.PADDING * 2,
        overlay._header_height(),
    )
    _, _, dps_rect = overlay._entry_rects(header_row)
    green_pixels = 0
    for x in range(round(dps_rect.left()), round(dps_rect.right()) + 1):
        for y in range(round(dps_rect.top()), round(dps_rect.bottom()) + 1):
            pixel = image.pixelColor(x, y)
            if pixel.green() > 200 and pixel.red() < 180:
                green_pixels += 1

    assert overlay._format_dps(overlay._dps.dps) == "0 DPS"
    assert green_pixels > 0

    overlay.close()
    app.processEvents()


def test_window_width_and_font_size_remain_independent() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(
        OverlayPreferences(size=QSize(600, 420), font_scale=1.3), "character"
    )
    narrow_description, narrow_icon, _ = overlay._entry_rects(row_rect(overlay))
    narrow_font = overlay._font("Segoe UI", 12, QFont.Weight.Black)
    text_width = QFontMetricsF(narrow_font).horizontalAdvance("REAVING STRIKE")

    overlay.resize(900, 420)
    wide_description, wide_icon, _ = overlay._entry_rects(row_rect(overlay))
    wide_font = overlay._font("Segoe UI", 12, QFont.Weight.Black)

    assert wide_description.width() > narrow_description.width()
    assert wide_description.width() >= text_width
    assert wide_font.pointSizeF() == pytest.approx(narrow_font.pointSizeF())
    assert wide_icon.width() == pytest.approx(narrow_icon.width())

    overlay.close()
    app.processEvents()


def test_extra_width_grows_descriptions_not_the_amount_lane() -> None:
    """Widening the window must not pile empty space right of the numbers."""
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(OverlayPreferences(size=QSize(400, 420)), "pet")
    _, _, narrow_amount = overlay._entry_rects(row_rect(overlay))

    overlay.resize(900, 420)
    _, wide_icon, wide_amount = overlay._entry_rects(row_rect(overlay))

    # Amount lane is fixed-width — damage text has a known ceiling.
    assert wide_amount.width() == pytest.approx(narrow_amount.width())
    # The lane hugs the right edge instead of starting at the window's center.
    assert wide_amount.right() == pytest.approx(row_rect(overlay).right())
    assert wide_icon.center().x() > overlay.width() / 2
    # And it fits the worst-case templates at the current scale.
    amount_font = overlay._font("Segoe UI", 21, QFont.Weight.Black)
    dps_font = overlay._font("Segoe UI", 13, QFont.Weight.Black)
    assert wide_amount.width() >= QFontMetricsF(amount_font).horizontalAdvance("888,888")
    assert wide_amount.width() >= QFontMetricsF(dps_font).horizontalAdvance("888.8K DPS")

    overlay.close()
    app.processEvents()


def test_resize_zone_is_large_and_mouse_press_starts_resize() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(OverlayPreferences(), "character")
    middle_y = overlay.height() / 2

    assert overlay._resize_edges_at(QPointF(15, middle_y)) == frozenset({"left"})
    assert overlay._resize_edges_at(QPointF(15, 15)) == frozenset({"left", "top"})
    overlay.show()
    QTest.mousePress(
        overlay,
        Qt.MouseButton.LeftButton,
        pos=QPoint(15, round(middle_y)),
    )
    assert overlay._resize_edges == frozenset({"left"})
    QTest.mouseRelease(
        overlay,
        Qt.MouseButton.LeftButton,
        pos=QPoint(15, round(middle_y)),
    )

    overlay.close()
    app.processEvents()


def test_pet_window_restores_pet_size_not_you_size() -> None:
    app = QApplication.instance() or QApplication([])
    preferences = OverlayPreferences(size=QSize(800, 400), pet_size=QSize(500, 300))
    you = CombatFeedOverlay(preferences, "character")
    pet = CombatFeedOverlay(preferences, "pet")

    assert you.size() == QSize(800, 400)
    assert pet.size() == QSize(500, 300)

    you.close()
    pet.close()
    app.processEvents()


def test_critical_amount_is_red_without_extra_label() -> None:
    critical = event(123)
    critical = CombatEvent(
        timestamp=critical.timestamp,
        kind=critical.kind,
        amount=critical.amount,
        ability=critical.ability,
        target=critical.target,
        critical=True,
        source=critical.source,
    )

    assert CombatFeedOverlay._amount_color(critical, "character") == QColor("#ff2020")
    assert CombatFeedOverlay._source_parts(critical, "character") == ("", "⚔")
