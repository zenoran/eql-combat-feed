"""Encounter-scoped DPS accounting, independent from Qt rendering."""

from dataclasses import dataclass
from typing import Literal

from .models import CombatEvent, EventKind

Actor = Literal["character", "pet"]

CHARACTER_DAMAGE_KINDS = frozenset(
    {
        EventKind.MELEE,
        EventKind.SKILL,
        EventKind.RANGED,
        EventKind.SPELL,
        EventKind.PROC,
    }
)


@dataclass(frozen=True, slots=True)
class DpsSnapshot:
    damage: int = 0
    duration: float = 0.0
    active: bool = False

    @property
    def dps(self) -> float:
        return self.damage / self.duration if self.duration > 0 else 0.0


class EncounterDpsMeter:
    """Track player and pet damage on one shared encounter clock.

    EverQuest log timestamps resolve to one second. Encounter duration therefore
    includes both endpoint seconds: hits at 10:00:00 and 10:00:04 span five
    logged combat seconds. A kill or a configurable damage lull finalizes the
    encounter; the completed result remains available until the next pull.
    """

    def __init__(self, inactivity_seconds: float = 10.0) -> None:
        if inactivity_seconds <= 0:
            raise ValueError("inactivity_seconds must be positive")
        self.inactivity_seconds = inactivity_seconds
        self._started_at: float | None = None
        self._last_damage_at: float | None = None
        self._last_observed_at: float | None = None
        self._damage: dict[Actor, int] = {"character": 0, "pet": 0}
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def add(self, event: CombatEvent, observed_at: float) -> bool:
        """Consume an event and return whether the displayed DPS changed."""
        if event.kind is EventKind.KILL:
            return self.finalize()

        actor = self._damage_actor(event)
        if actor is None:
            return False

        if self._should_start_new_encounter(event.timestamp, observed_at):
            self.reset()

        if not self._active:
            self._started_at = event.timestamp
            self._active = True

        assert self._started_at is not None
        self._started_at = min(self._started_at, event.timestamp)
        self._last_damage_at = max(self._last_damage_at or event.timestamp, event.timestamp)
        self._last_observed_at = observed_at
        self._damage[actor] += event.amount
        return True

    def tick(self, observed_at: float) -> bool:
        """Finalize an active encounter after a real-time damage lull."""
        if (
            self._active
            and self._last_observed_at is not None
            and observed_at - self._last_observed_at > self.inactivity_seconds
        ):
            return self.finalize()
        return False

    def finalize(self) -> bool:
        if not self._active:
            return False
        self._active = False
        self._last_observed_at = None
        return True

    def reset(self) -> None:
        self._started_at = None
        self._last_damage_at = None
        self._last_observed_at = None
        self._damage = {"character": 0, "pet": 0}
        self._active = False

    def snapshot(self, actor: Actor) -> DpsSnapshot:
        if self._started_at is None or self._last_damage_at is None:
            return DpsSnapshot()
        duration = max(1.0, self._last_damage_at - self._started_at + 1.0)
        return DpsSnapshot(self._damage[actor], duration, self._active)

    def _should_start_new_encounter(self, timestamp: float, observed_at: float) -> bool:
        if self._started_at is None:
            return False
        if not self._active:
            return True
        log_lull = self._last_damage_at is not None and (
            timestamp - self._last_damage_at > self.inactivity_seconds
        )
        observed_lull = self._last_observed_at is not None and (
            observed_at - self._last_observed_at > self.inactivity_seconds
        )
        return log_lull or observed_lull

    @staticmethod
    def _damage_actor(event: CombatEvent) -> Actor | None:
        if event.incoming or event.amount <= 0:
            return None
        if event.kind is EventKind.PET:
            return "pet"
        if event.kind in CHARACTER_DAMAGE_KINDS:
            return "character"
        return None
