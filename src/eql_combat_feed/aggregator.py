"""Aggregate noisy combat-log events into compact visual combat beats."""

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .models import BeatGroup, CombatBeat, CombatEvent, EventKind


@dataclass(slots=True)
class _GroupAccumulator:
    amount: int = 0
    event_count: int = 0
    critical_count: int = 0
    targets: set[str] | None = None

    def add(self, event: CombatEvent) -> None:
        self.amount += event.amount
        self.event_count += 1
        self.critical_count += int(event.critical)
        if event.target:
            if self.targets is None:
                self.targets = set()
            self.targets.add(event.target)


class BeatAggregator:
    """Batch and streaming fixed-window aggregation.

    Log timestamps resolve to one second, so the default window naturally maps
    to one row per timestamp. ``flush_before`` keeps the current second open for
    late lines and emits completed beats as soon as a newer timestamp arrives.
    """

    def __init__(self, window_seconds: float = 1.0) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.window_seconds = window_seconds
        self._buckets: dict[int, list[CombatEvent]] = defaultdict(list)

    def add(self, event: CombatEvent) -> None:
        self._buckets[self._bucket_for(event.timestamp)].append(event)

    def flush_before(self, timestamp: float) -> list[CombatBeat]:
        cutoff = self._bucket_for(timestamp)
        return self._flush_keys(key for key in self._buckets if key < cutoff)

    def flush_all(self) -> list[CombatBeat]:
        return self._flush_keys(self._buckets)

    def aggregate(self, events: Iterable[CombatEvent]) -> list[CombatBeat]:
        buckets: dict[int, list[CombatEvent]] = defaultdict(list)
        for event in sorted(events, key=lambda item: item.timestamp):
            buckets[self._bucket_for(event.timestamp)].append(event)
        return [self._build_beat(bucket, buckets[bucket]) for bucket in sorted(buckets)]

    def _bucket_for(self, timestamp: float) -> int:
        return int(timestamp // self.window_seconds)

    def _flush_keys(self, keys: Iterable[int]) -> list[CombatBeat]:
        selected = sorted(set(keys))
        beats = [self._build_beat(key, self._buckets[key]) for key in selected]
        for key in selected:
            del self._buckets[key]
        return beats

    def _build_beat(self, bucket: int, events: list[CombatEvent]) -> CombatBeat:
        grouped: dict[tuple[EventKind, str | None, bool], _GroupAccumulator] = {}
        targets: set[str] = set()
        for event in events:
            key = (event.kind, event.ability, event.incoming)
            grouped.setdefault(key, _GroupAccumulator()).add(event)
            if event.target:
                targets.add(event.target)

        groups = tuple(
            BeatGroup(
                kind=kind,
                ability=ability,
                amount=value.amount,
                event_count=value.event_count,
                critical_count=value.critical_count,
                targets=frozenset(value.targets or ()),
                incoming=incoming,
            )
            for (kind, ability, incoming), value in sorted(
                grouped.items(), key=self._group_sort_key
            )
        )
        outgoing_damage_kinds = {
            EventKind.MELEE,
            EventKind.SKILL,
            EventKind.RANGED,
            EventKind.SPELL,
            EventKind.PET,
            EventKind.PROC,
            EventKind.DAMAGE_SHIELD,
        }
        start = bucket * self.window_seconds
        return CombatBeat(
            started_at=start,
            ended_at=start + self.window_seconds,
            groups=groups,
            total_damage=sum(
                group.amount
                for group in groups
                if not group.incoming and group.kind in outgoing_damage_kinds
            ),
            incoming_damage=sum(
                group.amount
                for group in groups
                if group.incoming and group.kind not in {EventKind.HEAL}
            ),
            total_healing=sum(
                group.amount
                for group in groups
                if not group.incoming and group.kind is EventKind.HEAL
            ),
            has_critical=any(group.critical_count for group in groups),
            event_count=len(events),
            targets=frozenset(targets),
        )

    @staticmethod
    def _group_sort_key(
        item: tuple[tuple[EventKind, str | None, bool], _GroupAccumulator],
    ) -> tuple[bool, int, str, str]:
        (kind, ability, incoming), value = item
        return incoming, -value.amount, kind.value, ability or ""


class StreamingBeatAggregator:
    """Push events and receive complete beats through a callback."""

    def __init__(
        self,
        on_beat: Callable[[CombatBeat], None],
        window_seconds: float = 1.0,
    ) -> None:
        self._aggregator = BeatAggregator(window_seconds)
        self._on_beat = on_beat

    def add(self, event: CombatEvent) -> None:
        for beat in self._aggregator.flush_before(event.timestamp):
            self._on_beat(beat)
        self._aggregator.add(event)

    def flush(self) -> None:
        for beat in self._aggregator.flush_all():
            self._on_beat(beat)
