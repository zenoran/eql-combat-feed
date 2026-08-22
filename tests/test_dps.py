import pytest

from eql_combat_feed.dps import EncounterDpsMeter
from eql_combat_feed.models import CombatEvent, EventKind


def damage(
    timestamp: float,
    amount: int,
    kind: EventKind = EventKind.MELEE,
    *,
    incoming: bool = False,
) -> CombatEvent:
    return CombatEvent(
        timestamp=timestamp,
        kind=kind,
        amount=amount,
        incoming=incoming,
        source="A pet" if kind is EventKind.PET else "You",
    )


def test_you_and_pet_share_encounter_clock_but_keep_separate_totals() -> None:
    meter = EncounterDpsMeter()

    meter.add(damage(100.0, 100), observed_at=1.0)
    meter.add(damage(102.0, 50, EventKind.PET), observed_at=3.0)
    meter.add(damage(104.0, 150, EventKind.SPELL), observed_at=5.0)

    you = meter.snapshot("character")
    pet = meter.snapshot("pet")
    assert you.damage == 250
    assert pet.damage == 50
    assert you.duration == pet.duration == 5.0
    assert you.dps == pytest.approx(50.0)
    assert pet.dps == pytest.approx(10.0)
    assert you.active is pet.active is True


def test_status_and_non_feed_damage_do_not_change_dps() -> None:
    meter = EncounterDpsMeter()
    ignored = [
        damage(100.0, 0, EventKind.MISS),
        damage(100.0, 75, EventKind.HEAL),
        damage(100.0, 12, EventKind.DAMAGE_SHIELD),
        damage(100.0, 44, incoming=True),
    ]

    for event in ignored:
        assert meter.add(event, observed_at=1.0) is False

    assert meter.snapshot("character").damage == 0
    assert meter.snapshot("pet").damage == 0
    assert meter.active is False


def test_inactivity_finalizes_result_and_next_hit_starts_fresh() -> None:
    meter = EncounterDpsMeter(inactivity_seconds=10.0)
    meter.add(damage(100.0, 120), observed_at=5.0)
    meter.add(damage(101.0, 80), observed_at=6.0)

    assert meter.tick(16.0) is False
    assert meter.tick(16.01) is True
    completed = meter.snapshot("character")
    assert completed.damage == 200
    assert completed.duration == 2.0
    assert completed.dps == pytest.approx(100.0)
    assert completed.active is False

    meter.add(damage(200.0, 60), observed_at=20.0)
    fresh = meter.snapshot("character")
    assert fresh.damage == 60
    assert fresh.duration == 1.0
    assert fresh.dps == pytest.approx(60.0)
    assert fresh.active is True


def test_kill_finalizes_without_erasing_completed_result() -> None:
    meter = EncounterDpsMeter()
    meter.add(damage(100.0, 180), observed_at=1.0)
    kill = CombatEvent(timestamp=101.0, kind=EventKind.KILL, target="a gargoyle")

    assert meter.add(kill, observed_at=2.0) is True
    snapshot = meter.snapshot("character")
    assert snapshot.damage == 180
    assert snapshot.dps == pytest.approx(180.0)
    assert snapshot.active is False


def test_out_of_order_damage_extends_start_without_negative_duration() -> None:
    meter = EncounterDpsMeter()
    meter.add(damage(105.0, 50), observed_at=1.0)
    meter.add(damage(103.0, 50), observed_at=1.1)

    snapshot = meter.snapshot("character")
    assert snapshot.damage == 100
    assert snapshot.duration == 3.0
    assert snapshot.dps == pytest.approx(100 / 3)


def test_invalid_inactivity_timeout_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        EncounterDpsMeter(0)
