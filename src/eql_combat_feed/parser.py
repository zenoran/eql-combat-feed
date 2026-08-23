"""Parse EverQuest Legends combat log lines into overlay events.

The line formats are adapted from the MIT-licensed ``eql-log-reader`` project
and verified against anonymized live EQL output. This parser intentionally ignores
third-party combat unless a source has been identified as the player's pet; false
silence is preferable to confidently crediting random NPC damage.
"""

import re
from datetime import datetime
from pathlib import Path

from .models import CombatEvent, EventKind

LOG_TS_FMT = "%a %b %d %H:%M:%S %Y"
LINE_RE = re.compile(
    r"^\[(?P<ts>[A-Za-z]{3} [A-Za-z]{3} \d{2} \d{2}:\d{2}:\d{2} \d{4})\] (?P<body>.*)$"
)
TAG_RE = re.compile(r"^(?P<body>.*[.!])\s*\((?P<tag>[A-Za-z][A-Za-z ]*)\)\s*$")

SELF_HIT_RE = re.compile(
    r"^You (?P<verb>[a-z]+) (?P<target>.+?) for (?P<amount>\d+) points? of "
    r"(?:(?P<element>[a-z]+) )?damage(?: by (?P<spell>.+?))?\.?$",
    re.IGNORECASE,
)
ATTACK_VERBS = {
    "hit",
    "hits",
    "slash",
    "slashes",
    "pierce",
    "pierces",
    "crush",
    "crushes",
    "claw",
    "claws",
    "bite",
    "bites",
    "sting",
    "stings",
    "punch",
    "punches",
    "gore",
    "gores",
    "maul",
    "mauls",
    "rend",
    "rends",
    "smash",
    "smashes",
    "strike",
    "strikes",
    "slice",
    "slices",
    "gouge",
    "gouges",
    "burn",
    "burns",
    "smite",
    "smites",
    "reave",
    "reaves",
    "kick",
    "kicks",
    "bash",
    "bashes",
    "backstab",
    "backstabs",
    "frenzy",
    "frenzies",
    "slam",
    "slams",
    "cleave",
    "cleaves",
    "shoot",
    "shoots",
}
_ATTACK_VERB_PATTERN = "|".join(sorted(ATTACK_VERBS, key=len, reverse=True))
OTHER_HIT_RE = re.compile(
    rf"^(?P<source>.+?) (?P<verb>{_ATTACK_VERB_PATTERN}) (?P<target>.+?) "
    r"for (?P<amount>\d+) points? of (?:(?P<element>[a-z]+) )?damage"
    r"(?: by (?P<spell>.+?))?\.?$",
    re.IGNORECASE,
)
SELF_MISS_RE = re.compile(
    r"^You try to (?P<verb>[a-z]+) (?P<target>.+?), but .+!$|"
    r"^You miss (?P<target_fallback>.+?)\.?$",
    re.I,
)
OTHER_MISS_RE = re.compile(
    rf"^(?P<source>.+?) tries to (?P<verb>{_ATTACK_VERB_PATTERN}) "
    r"(?P<target>.+?), but .+!$",
    re.I,
)
INCOMING_MISS_RE = re.compile(
    r"^(?P<source>.+?) (?:tries to [a-z]+ YOU, but .+!|misses? YOU\.?)$", re.I
)
INCOMING_DOT_RE = re.compile(
    r"^You have taken (?P<amount>\d+) damage from (?P<spell>.+?)(?: by (?P<source>.+?))?\.?$",
    re.I,
)
ATTRIBUTED_DOT_RE = re.compile(
    r"^(?P<target>.+?) has taken (?P<amount>\d+) damage from "
    r"(?P<owner>your|(?P<caster>[A-Za-z][A-Za-z' -]*?)'s) (?P<spell>.+?)\.?$",
    re.I,
)
HEAL_OUT_RE = re.compile(
    r"^You healed (?P<target>.+?)(?: over time)? for (?P<amount>\d+)"
    r"(?:\s*\((?P<raw>\d+)\))? hit points?(?: by (?P<spell>.+?))?\.?$",
    re.I,
)
HEAL_IN_RE = re.compile(
    r"^(?P<source>.+?) healed you(?: over time)? for (?P<amount>\d+)"
    r"(?:\s*\((?P<raw>\d+)\))? hit points?(?: by (?P<spell>.+?))?\.?$",
    re.I,
)
RESIST_OUT_RE = re.compile(r"^(?P<target>.+?) resisted your (?P<spell>.+?)!$", re.I)
RESIST_IN_RE = re.compile(r"^You resist (?P<source>.+?)[`']s (?P<spell>.+?)!$", re.I)
DS_OUT_RE = re.compile(
    r"^(?P<target>.+?) is [a-z]+ by YOUR (?P<kind>[A-Za-z ]+?) "
    r"for (?P<amount>\d+) points? of non-melee damage\.?$",
    re.I,
)
DS_IN_RE = re.compile(
    r"^YOU are [a-z]+ by (?P<source>.+?)[`']s (?P<kind>[A-Za-z ]+?) "
    r"for (?P<amount>\d+) points? of non-melee damage[.!]?$",
    re.I,
)
PET_LEADER_RE = re.compile(
    r"^(?P<pet>[A-Za-z][A-Za-z`' -]{0,60}?) says, 'My leader is (?P<owner>[A-Za-z]+)\.'$"
)
PET_ATTACK_RE = re.compile(r"^(?P<pet>.+?) told you, 'Attacking (?P<target>.+?) Master\.'$")
# "an elemental crusader has been charmed." — emitted the moment your charm
# lands, so a charm pet is attributed immediately instead of staying invisible
# until it says "Attacking X Master." (which requires an explicit /pet attack).
PET_CHARMED_RE = re.compile(r"^(?P<pet>.+?) has been charmed\.$", re.I)
SELF_KILL_RE = re.compile(r"^You have slain (?P<target>.+?)!?$", re.I)
PET_KILL_RE = re.compile(r"^(?P<target>.+?) has been slain by (?P<source>.+?)!?$", re.I)

SKILL_VERBS = {
    "kick": "Kick",
    "kicks": "Kick",
    "bash": "Bash",
    "bashes": "Bash",
    "backstab": "Backstab",
    "backstabs": "Backstab",
    "frenzy": "Frenzy",
    "frenzies": "Frenzy",
    "slam": "Slam",
    "slams": "Slam",
    "cleave": "Cleave",
    "cleaves": "Cleave",
    "reave": "Reave",
    "reaves": "Reave",
}
RANGED_VERBS = {"shoot", "shoots"}
NON_ATTACK_VERBS = {"have", "has", "had", "heal", "heals", "healed"}


def character_name_from_log(path: str | Path) -> str | None:
    """Extract ``Name`` from ``eqlog_Name_server.txt``."""
    name = Path(path).name
    match = re.match(r"eqlog_([^_]+)_.*\.txt$", name, re.I)
    return match.group(1) if match else None


class EqlCombatParser:
    def __init__(self, character_name: str | None = None) -> None:
        self.character_name = character_name
        self._pets: dict[str, str] = {}

    @property
    def pet_names(self) -> frozenset[str]:
        return frozenset(self._pets.values())

    def parse_line(self, line: str) -> list[CombatEvent]:
        parsed = LINE_RE.match(line.strip())
        if not parsed:
            return []
        try:
            timestamp = datetime.strptime(parsed.group("ts"), LOG_TS_FMT).timestamp()
        except ValueError:
            return []

        body = parsed.group("body").strip()
        critical = False
        while tag := TAG_RE.match(body):
            body = tag.group("body")
            critical |= tag.group("tag").lower() == "critical"

        if match := PET_LEADER_RE.match(body):
            if (
                not self.character_name
                or match.group("owner").casefold() == self.character_name.casefold()
            ):
                self._remember_pet(match.group("pet"))
            return []
        if match := PET_ATTACK_RE.match(body):
            self._remember_pet(match.group("pet"))
            return []
        if match := PET_CHARMED_RE.match(body):
            self._remember_pet(match.group("pet"))
            return []

        if match := SELF_HIT_RE.match(body):
            if match.group("verb").lower() in NON_ATTACK_VERBS:
                return []
            kind, ability = self._outgoing_kind_and_ability(match)
            return [
                CombatEvent(
                    timestamp=timestamp,
                    kind=kind,
                    amount=int(match.group("amount")),
                    ability=ability,
                    target=self._clean_target(match.group("verb"), match.group("target")),
                    critical=critical,
                    source="You",
                )
            ]

        if match := INCOMING_DOT_RE.match(body):
            return [
                CombatEvent(
                    timestamp=timestamp,
                    kind=EventKind.SPELL,
                    amount=int(match.group("amount")),
                    ability=match.group("spell"),
                    incoming=True,
                    source=match.group("source") or match.group("spell"),
                    target="You",
                    critical=critical,
                )
            ]

        if match := ATTRIBUTED_DOT_RE.match(body):
            if match.group("owner").casefold() != "your":
                return []
            return [
                CombatEvent(
                    timestamp=timestamp,
                    kind=EventKind.PROC,
                    amount=int(match.group("amount")),
                    ability=match.group("spell"),
                    target=match.group("target"),
                    critical=critical,
                    source="You",
                )
            ]

        if match := DS_OUT_RE.match(body):
            return [
                CombatEvent(
                    timestamp=timestamp,
                    kind=EventKind.DAMAGE_SHIELD,
                    amount=int(match.group("amount")),
                    ability=f"{match.group('kind').strip().title()} shield",
                    target=match.group("target"),
                    source="You",
                    critical=critical,
                )
            ]
        if match := DS_IN_RE.match(body):
            return [
                CombatEvent(
                    timestamp=timestamp,
                    kind=EventKind.DAMAGE_SHIELD,
                    amount=int(match.group("amount")),
                    ability=f"{match.group('kind').strip().title()} shield",
                    target="You",
                    source=match.group("source"),
                    incoming=True,
                    critical=critical,
                )
            ]

        if match := HEAL_OUT_RE.match(body):
            return [
                CombatEvent(
                    timestamp=timestamp,
                    kind=EventKind.HEAL,
                    amount=int(match.group("amount")),
                    ability=match.group("spell") or "Heal",
                    target=match.group("target"),
                    source="You",
                )
            ]
        if match := HEAL_IN_RE.match(body):
            return [
                CombatEvent(
                    timestamp=timestamp,
                    kind=EventKind.HEAL,
                    amount=int(match.group("amount")),
                    ability=match.group("spell") or "Heal",
                    target="You",
                    source=match.group("source"),
                    incoming=True,
                )
            ]

        if match := RESIST_OUT_RE.match(body):
            return [
                self._status_event(
                    timestamp, EventKind.RESIST, match.group("spell"), match.group("target")
                )
            ]
        if match := RESIST_IN_RE.match(body):
            return [
                self._status_event(
                    timestamp,
                    EventKind.RESIST,
                    match.group("spell"),
                    "You",
                    incoming=True,
                    source=match.group("source"),
                )
            ]
        if match := SELF_MISS_RE.match(body):
            target = match.group("target") or match.group("target_fallback")
            verb = match.group("verb")
            ability = self._physical_ability(verb) if verb else "Melee"
            return [self._status_event(timestamp, EventKind.MISS, ability, target)]
        if match := INCOMING_MISS_RE.match(body):
            # A "pet" swinging at YOU means the charm broke — it isn't ours
            # anymore. (The generic "spell has worn off of X" line can't signal
            # this: a haste buff fading off a still-charmed pet looks the same.)
            if self._is_pet(match.group("source")):
                self._forget_pet(match.group("source"))
            return [
                self._status_event(
                    timestamp,
                    EventKind.MISS,
                    "Miss",
                    "You",
                    incoming=True,
                    source=match.group("source"),
                )
            ]
        if match := OTHER_MISS_RE.match(body):
            source = match.group("source")
            if self._is_pet(source):
                return [
                    self._status_event(
                        timestamp,
                        EventKind.MISS,
                        self._physical_ability(match.group("verb")),
                        self._clean_target(match.group("verb"), match.group("target")),
                        source=source,
                    )
                ]
            return []

        if match := SELF_KILL_RE.match(body):
            return [self._status_event(timestamp, EventKind.KILL, "Slain", match.group("target"))]
        if match := PET_KILL_RE.match(body):
            source = match.group("source")
            if self._is_pet(source):
                return [
                    self._status_event(
                        timestamp,
                        EventKind.KILL,
                        "Pet kill",
                        match.group("target"),
                        source=source,
                    )
                ]
            if self._is_pet(match.group("target")):
                self._forget_pet(match.group("target"))
            return []

        if match := OTHER_HIT_RE.match(body):
            source = match.group("source")
            target = match.group("target")
            if target.casefold() in {"you", "yourself"}:
                if self._is_pet(source):
                    self._forget_pet(source)
                return [self._incoming_hit(timestamp, match, critical)]
            if self._is_pet(source):
                spell = match.group("spell")
                ability = spell or self._physical_ability(match.group("verb"))
                return [
                    CombatEvent(
                        timestamp=timestamp,
                        kind=EventKind.PET,
                        amount=int(match.group("amount")),
                        ability=ability,
                        target=self._clean_target(match.group("verb"), target),
                        critical=critical,
                        source=source,
                    )
                ]
            return []

        return []

    def _outgoing_kind_and_ability(self, match: re.Match[str]) -> tuple[EventKind, str]:
        if match.group("spell") or match.group("element"):
            return EventKind.SPELL, match.group(
                "spell"
            ) or f"{match.group('element').title()} damage"
        verb = match.group("verb").lower()
        if verb in SKILL_VERBS:
            return EventKind.SKILL, SKILL_VERBS[verb]
        if verb in RANGED_VERBS:
            return EventKind.RANGED, "Archery"
        return EventKind.MELEE, "Melee"

    def _incoming_hit(self, timestamp: float, match: re.Match[str], critical: bool) -> CombatEvent:
        spell = match.group("spell")
        element = match.group("element")
        kind = EventKind.SPELL if spell or element else EventKind.MELEE
        ability = spell or (
            f"{element.title()} damage" if element else self._physical_ability(match.group("verb"))
        )
        return CombatEvent(
            timestamp=timestamp,
            kind=kind,
            amount=int(match.group("amount")),
            ability=ability,
            target="You",
            critical=critical,
            incoming=True,
            source=match.group("source"),
        )

    @staticmethod
    def _physical_ability(verb: str) -> str:
        lowered = verb.lower()
        return SKILL_VERBS.get(lowered, "Melee")

    @staticmethod
    def _clean_target(verb: str, target: str) -> str:
        if verb.lower() in {"frenzy", "frenzies"} and target.lower().startswith("on "):
            return target[3:]
        return target

    @staticmethod
    def _status_event(
        timestamp: float,
        kind: EventKind,
        ability: str,
        target: str,
        *,
        incoming: bool = False,
        source: str = "You",
    ) -> CombatEvent:
        return CombatEvent(
            timestamp=timestamp,
            kind=kind,
            ability=ability,
            target=target,
            incoming=incoming,
            source=source,
        )

    def _remember_pet(self, name: str) -> None:
        self._pets[name.strip().casefold()] = name.strip()

    def _forget_pet(self, name: str) -> None:
        self._pets.pop(name.strip().casefold(), None)

    def _is_pet(self, name: str) -> bool:
        lowered = name.strip().casefold()
        if lowered in self._pets:
            return True
        if self.character_name:
            possessive = f"{self.character_name.casefold()}`s "
            return lowered.startswith(possessive)
        return False
