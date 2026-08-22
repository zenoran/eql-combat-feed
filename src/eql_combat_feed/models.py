"""Domain models shared by parsing, aggregation, and rendering."""

from dataclasses import dataclass, field
from enum import StrEnum


class EventKind(StrEnum):
    MELEE = "melee"
    SKILL = "skill"
    RANGED = "ranged"
    SPELL = "spell"
    PET = "pet"
    PROC = "proc"
    DAMAGE_SHIELD = "damage_shield"
    HEAL = "heal"
    MISS = "miss"
    RESIST = "resist"
    KILL = "kill"


@dataclass(frozen=True, slots=True)
class CombatEvent:
    timestamp: float
    kind: EventKind
    amount: int = 0
    ability: str | None = None
    target: str | None = None
    critical: bool = False
    incoming: bool = False
    source: str | None = None


@dataclass(frozen=True, slots=True)
class BeatGroup:
    kind: EventKind
    ability: str | None
    amount: int
    event_count: int
    critical_count: int
    targets: frozenset[str]
    incoming: bool


@dataclass(frozen=True, slots=True)
class CombatBeat:
    started_at: float
    ended_at: float
    groups: tuple[BeatGroup, ...]
    total_damage: int
    incoming_damage: int
    total_healing: int
    has_critical: bool
    event_count: int
    targets: frozenset[str] = field(default_factory=frozenset)
