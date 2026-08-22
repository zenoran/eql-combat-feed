"""Domain models shared by parsing and rendering."""

from dataclasses import dataclass
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
