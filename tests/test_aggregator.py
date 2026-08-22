from eql_combat_feed.aggregator import BeatAggregator, StreamingBeatAggregator
from eql_combat_feed.models import CombatEvent, EventKind


def test_merges_matching_hits_within_one_beat() -> None:
    events = [
        CombatEvent(10.1, EventKind.MELEE, amount=418, target="a ghoul"),
        CombatEvent(10.6, EventKind.MELEE, amount=466, target="a ghoul", critical=True),
        CombatEvent(10.7, EventKind.PET, amount=176, ability="claw", target="a ghoul"),
        CombatEvent(10.8, EventKind.MISS, incoming=True, target="You"),
        CombatEvent(10.8, EventKind.HEAL, amount=50, ability="Lifedraw", target="You"),
    ]

    beat = BeatAggregator().aggregate(events)[0]

    assert beat.total_damage == 1_060
    assert beat.incoming_damage == 0
    assert beat.total_healing == 50
    assert beat.event_count == 5
    assert beat.has_critical is True
    assert [(group.kind, group.amount, group.event_count) for group in beat.groups] == [
        (EventKind.MELEE, 884, 2),
        (EventKind.PET, 176, 1),
        (EventKind.HEAL, 50, 1),
        (EventKind.MISS, 0, 1),
    ]


def test_separates_events_across_windows() -> None:
    events = [
        CombatEvent(3.99, EventKind.SPELL, amount=100, ability="Frost Storm"),
        CombatEvent(4.01, EventKind.SPELL, amount=200, ability="Frost Storm"),
    ]

    beats = BeatAggregator().aggregate(events)

    assert [beat.total_damage for beat in beats] == [100, 200]


def test_streaming_aggregator_flushes_previous_second() -> None:
    beats = []
    stream = StreamingBeatAggregator(beats.append)
    stream.add(CombatEvent(5.1, EventKind.MELEE, amount=100))
    stream.add(CombatEvent(5.8, EventKind.MELEE, amount=50))
    assert beats == []

    stream.add(CombatEvent(6.0, EventKind.SPELL, amount=200))
    assert [beat.total_damage for beat in beats] == [150]

    stream.flush()
    assert [beat.total_damage for beat in beats] == [150, 200]


def test_rejects_non_positive_window() -> None:
    try:
        BeatAggregator(window_seconds=0)
    except ValueError as error:
        assert str(error) == "window_seconds must be positive"
    else:
        raise AssertionError("expected ValueError")
