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
    overlay = CombatFeedOverlay(OverlayPreferences(damage_font_size=27.3), "character")

    assert overlay.ROW_HEIGHT == 31
    assert overlay._row_height() == pytest.approx(40.3)
    assert overlay._row_height() < 41

    overlay.close()
    app.processEvents()


def test_icon_has_no_backdrop_while_text_backdrop_has_two_vertical_pixels() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(OverlayPreferences(damage_font_size=27.3), "character")
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


def test_header_cluster_is_spaced_and_right_anchored() -> None:
    app = QApplication.instance() or QApplication([])
    for actor in ("character", "pet"):
        overlay = CombatFeedOverlay(OverlayPreferences(size=QSize(772, 400)), actor)
        overlay.set_dps(DpsSnapshot(damage=1234, duration=10.0, active=True))
        actor_rect, marker_rect, dps_rect = overlay._header_rects()
        dps_text = overlay._format_dps(overlay._dps.dps)
        dps_advance = QFontMetricsF(overlay._header_font(QFont.Weight.Bold)).horizontalAdvance(
            dps_text
        )

        assert marker_rect.left() - actor_rect.right() >= 8
        assert dps_rect.left() - marker_rect.right() >= 5
        assert dps_rect.width() >= dps_advance + 6
        assert dps_rect.right() == pytest.approx(overlay.width() - 3)
        assert actor_rect.left() >= overlay.PADDING
        assert overlay._title_text().startswith("YOU" if actor == "character" else "PET")

        image = render(overlay)
        marker_pixel = image.pixelColor(
            round(marker_rect.center().x()), round(marker_rect.center().y())
        )
        assert marker_pixel.alpha() > 180
        overlay.close()
    app.processEvents()


def test_header_and_damage_point_sizes_are_independent() -> None:
    app = QApplication.instance() or QApplication([])
    base = CombatFeedOverlay(
        OverlayPreferences(
            damage_font_size=27.3,
            header_font_size=22.0,
            size=QSize(772, 400),
        ),
        "character",
    )
    bigger_header = CombatFeedOverlay(
        OverlayPreferences(
            damage_font_size=27.3,
            header_font_size=30.0,
            size=QSize(772, 400),
        ),
        "character",
    )
    bigger_damage = CombatFeedOverlay(
        OverlayPreferences(
            damage_font_size=35.0,
            header_font_size=22.0,
            size=QSize(772, 400),
        ),
        "character",
    )

    assert base._header_font(QFont.Weight.Bold).pointSizeF() == pytest.approx(22.0)
    assert bigger_header._header_font(QFont.Weight.Bold).pointSizeF() == pytest.approx(30.0)
    assert bigger_header._row_height() == pytest.approx(base._row_height())
    assert bigger_damage._header_font(QFont.Weight.Bold).pointSizeF() == pytest.approx(22.0)
    assert bigger_damage._row_height() > base._row_height()

    base.close()
    bigger_header.close()
    bigger_damage.close()
    app.processEvents()


def test_header_band_anchors_feed_without_an_underline() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(
        OverlayPreferences(damage_font_size=27.3, header_font_size=22.0, size=QSize(900, 400)),
        "character",
    )
    overlay.set_dps(DpsSnapshot(damage=2461, duration=10.0, active=True))
    actor_rect, marker_rect, dps_rect = overlay._header_rects()
    content = overlay._header_content_bounds(
        actor_rect,
        marker_rect,
        dps_rect,
        overlay._header_font(QFont.Weight.Black),
        overlay._header_font(QFont.Weight.Bold),
    )
    background = overlay._header_background_rect(content)

    assert background.width() == pytest.approx(overlay.width() - overlay.PADDING * 2)
    assert overlay._header_divider_y(background) == pytest.approx(background.bottom())
    assert overlay.HEADER_FEED_GAP <= 2
    assert overlay._content_top() == pytest.approx(
        background.bottom() + overlay.HEADER_FEED_GAP * overlay.text_scale
    )

    overlay.close()
    app.processEvents()


def test_header_content_stays_aligned_while_background_follows_window_width() -> None:
    app = QApplication.instance() or QApplication([])
    content_widths = []
    background_widths = []
    for width in (600, 1100):
        overlay = CombatFeedOverlay(
            OverlayPreferences(
                damage_font_size=27.3,
                header_font_size=22.0,
                size=QSize(width, 400),
            ),
            "character",
        )
        overlay.set_dps(DpsSnapshot(damage=2461, duration=10.0, active=True))
        actor_rect, marker_rect, dps_rect = overlay._header_rects()
        content = overlay._header_content_bounds(
            actor_rect,
            marker_rect,
            dps_rect,
            overlay._header_font(QFont.Weight.Black),
            overlay._header_font(QFont.Weight.Bold),
        )
        background = overlay._header_background_rect(content)
        content_widths.append(content.width())
        background_widths.append(background.width())
        overlay.close()

    assert content_widths[0] == pytest.approx(content_widths[1])
    assert background_widths == pytest.approx([584, 1084])
    app.processEvents()


def test_dps_header_uses_whole_grouped_values() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(OverlayPreferences(size=QSize(772, 400)), "character")

    assert QColor("#7dff00") == overlay_module.DPS_COLOR
    assert overlay.DPS_TEMPLATE == "99,999 DPS"
    assert overlay._format_dps(123.4) == "123 DPS"
    assert overlay._format_dps(123.6) == "124 DPS"
    assert overlay._format_dps(1200) == "1,200 DPS"
    assert overlay._format_dps(99_999) == "99,999 DPS"
    assert overlay._format_dps(100_000) == "100K DPS"

    overlay.close()
    app.processEvents()


def test_dps_slot_stays_fixed_from_zero_through_realistic_maximum() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(OverlayPreferences(size=QSize(772, 400)), "character")
    geometries = []
    for dps in (0, 216, 9_999, 99_999):
        overlay.set_dps(DpsSnapshot(damage=dps, duration=1.0, active=True))
        actor_rect, marker_rect, dps_rect = overlay._header_rects()
        geometries.append(
            (actor_rect.left(), marker_rect.left(), dps_rect.left(), dps_rect.width())
        )

    assert all(geometry == pytest.approx(geometries[0]) for geometry in geometries[1:])

    overlay.close()
    app.processEvents()


def test_pet_header_shows_zero_dps_during_shared_active_encounter() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(OverlayPreferences(size=QSize(600, 400)), "pet")
    overlay.set_dps(DpsSnapshot(damage=0, duration=4.0, active=True))

    image = render(overlay)
    _, _, dps_rect = overlay._header_rects()
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


def test_description_lane_keeps_names_clear_of_the_icon_spine() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(OverlayPreferences(damage_font_size=27.3), "character")
    description_rect, icon_rect, _ = overlay._entry_rects(row_rect(overlay))

    assert icon_rect.left() - description_rect.right() == pytest.approx(
        overlay.DESCRIPTION_ICON_GAP * overlay.text_scale
    )

    overlay.close()
    app.processEvents()


def test_window_width_and_font_size_remain_independent() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(
        OverlayPreferences(size=QSize(600, 420), damage_font_size=27.3), "character"
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
    # And it fits the worst-case damage template at the current scale.
    amount_font = overlay._font("Segoe UI", 21, QFont.Weight.Black)
    assert wide_amount.width() >= QFontMetricsF(amount_font).horizontalAdvance("888,888") + 6

    overlay.close()
    app.processEvents()


def test_header_size_does_not_widen_combat_amount_lane() -> None:
    app = QApplication.instance() or QApplication([])
    small = CombatFeedOverlay(
        OverlayPreferences(header_font_size=14.0, size=QSize(700, 420)), "character"
    )
    large = CombatFeedOverlay(
        OverlayPreferences(header_font_size=34.0, size=QSize(700, 420)), "character"
    )

    _, _, small_amount = small._entry_rects(row_rect(small))
    _, _, large_amount = large._entry_rects(row_rect(large))
    assert large_amount.width() == pytest.approx(small_amount.width())
    assert large_amount.left() == pytest.approx(small_amount.left())

    small.close()
    large.close()
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


def test_miss_text_and_icon_are_smaller_without_changing_hit_sizes() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(OverlayPreferences(damage_font_size=27.3), "character")
    miss = event(0, EventKind.MISS)
    hit = event(123, EventKind.MELEE)

    miss_icon, miss_amount = overlay._entry_value_fonts(miss)
    hit_icon, hit_amount = overlay._entry_value_fonts(hit)

    assert overlay.MISS_SCALE == 0.75
    assert miss_icon.pointSizeF() == pytest.approx(hit_icon.pointSizeF() * 0.75)
    assert miss_amount.pointSizeF() == pytest.approx(hit_amount.pointSizeF() * 0.75)

    overlay.close()
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


def test_critical_rows_keep_normal_pitch_with_bigger_text() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(OverlayPreferences(), "character")
    plain = event(123, EventKind.SPELL, ability="Ice Comet")
    crit = CombatEvent(
        timestamp=plain.timestamp,
        kind=plain.kind,
        amount=plain.amount,
        ability=plain.ability,
        target=plain.target,
        critical=True,
        source=plain.source,
    )

    _, plain_amount_font = overlay._entry_value_fonts(plain)
    _, crit_amount_font = overlay._entry_value_fonts(crit)
    assert crit_amount_font.family() == plain_amount_font.family() == "Segoe UI"
    assert crit_amount_font.pointSizeF() > plain_amount_font.pointSizeF()
    # Same row pitch as every other row — bigger text, no padding gap (0.17.0).
    assert overlay._entry_height(crit) == pytest.approx(overlay._entry_height(plain))

    # MISS crits stay ordinary rows.
    miss = CombatEvent(
        timestamp=plain.timestamp,
        kind=EventKind.MISS,
        amount=0,
        ability="Melee",
        target=plain.target,
        critical=True,
        source=plain.source,
    )
    assert overlay._entry_height(miss) == pytest.approx(overlay._entry_height(plain))

    overlay.close()
    app.processEvents()


def test_tooltip_help_event_uses_qhelpevent_api_without_crashing() -> None:
    """Regression: QHelpEvent has pos()/globalPos(), not position() — hovering
    a row for a tooltip raised AttributeError in the field (0.14.1 crash log)."""
    QHelpEvent = qt_gui.QHelpEvent
    QEvent = qt_core.QEvent
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(OverlayPreferences(), "character")
    overlay.add_event(event(123, EventKind.SPELL, ability="Lifedraw"))

    rect = row_rect(overlay)
    local = QPoint(round(rect.center().x()), round(rect.center().y()))
    help_event = QHelpEvent(QEvent.Type.ToolTip, local, overlay.mapToGlobal(local))
    assert overlay.event(help_event) is True  # handled: tooltip shown, no crash

    overlay.close()
    app.processEvents()


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def _fading_overlay(**prefs: object) -> tuple[CombatFeedOverlay, _FakeClock]:
    QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(
        OverlayPreferences(fade_delay=10, **prefs), "character"
    )
    clock = _FakeClock()
    overlay._now = clock  # type: ignore[method-assign]
    return overlay, clock


def test_rows_fade_out_after_inactivity_and_stop_taking_space() -> None:
    overlay, clock = _fading_overlay()
    for amount in (100, 200, 300):
        overlay.add_event(event(amount))
    assert len(overlay._visible_entries()) == 3

    clock.now += 9.9  # still inside the delay: fully opaque
    assert all(overlay._entry_alpha(e) == 1.0 for e in overlay._entries)

    clock.now += 0.85  # mid-fade
    mid = overlay._entry_alpha(overlay._entries[0])
    assert 0.0 < mid < 1.0
    assert mid == pytest.approx(0.5, abs=0.05)

    clock.now += 5.0  # long past delay + fade duration
    assert all(overlay._entry_alpha(e) == 0.0 for e in overlay._entries)
    assert overlay._visible_entries() == []
    # Decayed rows leave display but stay in history.
    assert len(overlay._entries) == 3

    overlay.add_event(event(400))
    visible = overlay._visible_entries()
    assert [e.event.amount for e in visible] == [400]

    overlay.close()


def test_each_row_decays_on_its_own_clock() -> None:
    overlay, clock = _fading_overlay()
    overlay.add_event(event(100))
    clock.now += 8.0
    overlay.add_event(event(200))
    clock.now += 3.0  # first row age 11s (fading), second age 3s (opaque)
    first, second = overlay._entries
    assert 0.0 < overlay._entry_alpha(first) < 1.0
    assert overlay._entry_alpha(second) == 1.0
    assert [e.event.amount for e in overlay._visible_entries()] == [100, 200]
    overlay.close()


def test_history_scroll_pauses_decay_and_shows_full_opacity() -> None:
    overlay, clock = _fading_overlay(max_rows=2, size=QSize(600, 140))
    for amount in (100, 200, 300, 400):
        overlay.add_event(event(amount))
    clock.now += 30.0
    assert overlay._visible_entries() == []

    overlay._history_offset = 2
    assert all(overlay._entry_alpha(e) == 1.0 for e in overlay._entries)
    assert overlay._visible_entries() != []

    overlay._history_offset = 0
    assert overlay._visible_entries() == []
    overlay.close()


def test_fade_disabled_keeps_rows_indefinitely() -> None:
    overlay, clock = _fading_overlay(fade_rows=False)
    overlay.add_event(event(100))
    clock.now += 3600.0
    assert overlay._entry_alpha(overlay._entries[0]) == 1.0
    assert len(overlay._visible_entries()) == 1
    overlay.close()


def test_tick_repaints_only_while_a_fade_is_in_motion() -> None:
    overlay, clock = _fading_overlay()
    overlay.add_event(event(100))
    updates: list[int] = []
    overlay.update = lambda *a: updates.append(1)  # type: ignore[method-assign]

    overlay.tick()  # first signature capture
    overlay.tick()  # stable while fully opaque
    assert len(updates) == 1

    clock.now += 10.5  # mid-fade: every tick repaints
    overlay.tick()
    clock.now += 0.05
    overlay.tick()
    assert len(updates) == 3

    clock.now += 30.0  # fully decayed: one final repaint, then quiet
    overlay.tick()
    overlay.tick()
    assert len(updates) == 4
    overlay.close()


def test_outgoing_resists_route_to_character_and_respect_the_toggle() -> None:
    app = QApplication.instance() or QApplication([])
    resist = CombatEvent(
        timestamp=1.0,
        kind=EventKind.RESIST,
        ability="Selo's Chords of Cessation",
        target="an abhorrent",
        source="You",
    )
    incoming = CombatEvent(
        timestamp=1.0,
        kind=EventKind.RESIST,
        ability="Ice Comet",
        target="You",
        source="a gargoyle",
        incoming=True,
    )
    shown = CombatFeedOverlay(OverlayPreferences(), "character")
    assert shown.add_event(resist) is True
    assert shown.add_event(incoming) is False
    assert CombatFeedOverlay._actor_for_event(resist) == "character"

    hidden = CombatFeedOverlay(OverlayPreferences(show_resists=False), "character")
    assert hidden.add_event(resist) is False
    assert hidden.entries == ()

    pet = CombatFeedOverlay(OverlayPreferences(), "pet")
    assert pet.add_event(resist) is False

    shown.close()
    hidden.close()
    pet.close()
    app.processEvents()


def test_resist_rows_render_smaller_with_spell_name_and_resist_text() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = CombatFeedOverlay(OverlayPreferences(), "character")
    resist = CombatEvent(
        timestamp=1.0,
        kind=EventKind.RESIST,
        ability="Denon's Disruptive Discord",
        target="an abhorrent",
        source="You",
    )
    hit = event(1462, EventKind.SPELL, ability="Ice Comet")

    description, icon = overlay._source_parts(resist, "character")
    assert description == "DENON'S DISRUPTIVE DISCORD"
    assert icon == "⊘"

    _, resist_font = overlay._entry_value_fonts(resist)
    _, hit_font = overlay._entry_value_fonts(hit)
    assert resist_font.pointSizeF() < hit_font.pointSizeF()
    assert resist_font.pointSizeF() == pytest.approx(
        hit_font.pointSizeF() * overlay.MISS_SCALE
    )

    # Resist rows are never crit rows and never grow.
    assert overlay._entry_height(resist) == pytest.approx(overlay._row_height())

    overlay.close()
    app.processEvents()


def test_offscreen_history_fading_does_not_trigger_repaints() -> None:
    """Regression (0.16.0): the tick signature covered ALL history entries, so
    during combat some off-screen row was always mid-fade and both overlays
    repainted at a continuous 20fps, delaying damage display."""
    overlay, clock = _fading_overlay(max_rows=3)
    for amount in range(100, 110):  # old rows destined to fade off-screen
        overlay.add_event(event(amount))
    clock.now += 9.0
    for amount in (900, 901, 902):  # fresh rows fill the visible window
        overlay.add_event(event(amount))

    updates: list[int] = []
    overlay.update = lambda *a: updates.append(1)  # type: ignore[method-assign]

    clock.now += 1.5  # old rows now mid-fade, but none of them are visible
    overlay.tick()  # first signature capture may repaint once
    baseline = len(updates)
    for _ in range(10):
        clock.now += 0.05
        overlay.tick()
    assert len(updates) == baseline  # quiescent while visible rows are opaque

    clock.now += 8.6  # now the visible rows themselves fade: repaints resume
    overlay.tick()
    assert len(updates) == baseline + 1
    overlay.close()
