"""Parse EverQuest Legends combat log lines into overlay events.

The line formats are adapted from the MIT-licensed ``eql-log-reader`` project
and verified against anonymized live EQL output. This parser intentionally ignores
third-party combat unless a source has been identified as the player's pet; false
silence is preferable to confidently crediting random NPC damage.
"""

import re
from datetime import datetime
from pathlib import Path

from .models import CombatEvent, EventKind, HasteState

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
# Bard charm (Solon's Bewitching Bravura) emits no "has been charmed." line at
# all — the only birth certificate in the log is the generic charm land message
# "<mob>'s eyes glaze over."  That message is also visible for other players'
# charms, so it only registers a pet within a short window after our own charm
# cast started ("You begin singing/casting <charm spell>").  Re-glazes of an
# already-known pet refresh attribution regardless of the window, because a
# held bard charm song re-lands silently on later pulses.
CHARM_CAST_BEGIN_RE = re.compile(r"^You begin (?:singing|casting) (?P<spell>.+?)\.$", re.I)
CHARM_GLAZE_RE = re.compile(r"^(?P<pet>.+?)'s eyes glaze over\.$", re.I)
CHARM_GLAZE_WINDOW_S = 12.0
# EQL upgraded spells log with a trailing rank ("Solon's Bewitching Bravura
# III"); strip it before comparing against CHARM_SPELLS.
_SPELL_RANK_RE = re.compile(r"\s+[IVXL]+$")
SPELL_WORN_OFF_RE = re.compile(
    r"^Your (?P<spell>.+?) spell has worn off of (?P<target>.+?)\.$", re.I
)
PET_SPELL_WORN_OFF_RE = re.compile(
    r"^Your pet's (?P<spell>.+?) spell has worn off\.$", re.I
)
PET_HASTE_LAND_RE = re.compile(
    r"^(?P<pet>.+?) (?:feels much faster|begins to move faster|foams at the mouth|goes berserk)\.$",
    re.I,
)
PET_AUGMENTATION_OF_DEATH_LAND_RE = re.compile(
    r"^(?P<pet>.+?)[`']s eyes gleam with madness\.$", re.I
)
PLAYER_DEATH_RE = re.compile(r"^(?:You died\.|You have been slain by .+?[.!])$", re.I)
ZONE_RE = re.compile(r"^(?:LOADING, PLEASE WAIT\.\.\.|You have entered .+\.)$", re.I)
PERSISTENT_HASTE_SPELLS = {
    "alacrity",
    "augmentation",
    "augmentation of death",
    "burnout",
    "celerity",
    "haste",
    "quickness",
    "spirit quickening",
    "swift like the wind",
}
CHARM_SPELLS = {
    "allure",
    "allure of the wild",
    "beguiling",
    "beguile",
    "beguile animals",
    "boltran's agacerie",
    "cajoling whispers",
    "call of karana",
    "charm",
    "dictate",
    "solon's bewitching bravura",
    "solon's song of the sirens",
}


def _normalized_spell(spell: str) -> str:
    return _SPELL_RANK_RE.sub("", spell.strip()).casefold()
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
        self._charmed_pets: set[str] = set()
        self._last_charm_cast: float | None = None
        self._haste_sources: dict[str, set[str]] = {"character": set(), "pet": set()}
        self._haste_states: dict[str, HasteState] = {
            "character": HasteState.UNKNOWN,
            "pet": HasteState.UNKNOWN,
        }

    @property
    def pet_names(self) -> frozenset[str]:
        return frozenset(self._pets.values())

    def haste_state(self, actor: str) -> HasteState:
        return self._haste_states[actor]

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

        if body == "You feel much faster.":
            self._add_haste("character", "standard")
            return []
        if body == "Your speed returns to normal.":
            self._remove_haste("character", "standard")
            return []
        if body == "You feel your body pulse with energy.":
            self._add_haste("character", "augmentation")
            return []
        if body == "The pulsing energy fades.":
            self._remove_haste("character", "augmentation")
            return []
        if PLAYER_DEATH_RE.match(body):
            self._set_haste_missing("character")
            self._forget_all_pets()
            return []
        if ZONE_RE.match(body):
            # Buffs and pets can survive zoning, but log-only tracking loses the
            # authoritative continuity signal. Unknown is safer than inventing
            # either an active or missing state after the loading screen.
            self._set_haste_unknown("character")
            self._pets.clear()
            self._charmed_pets.clear()
            self._set_haste_unknown("pet")
            return []

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
            self._remember_pet(match.group("pet"), charmed=True)
            return []
        if match := PET_HASTE_LAND_RE.match(body):
            if self._is_pet(match.group("pet")):
                self._add_haste("pet", self._pet_haste_source(body))
            return []
        if match := PET_AUGMENTATION_OF_DEATH_LAND_RE.match(body):
            if self._is_pet(match.group("pet")):
                self._add_haste("pet", "augmentation of death")
            return []
        if match := PET_SPELL_WORN_OFF_RE.match(body):
            spell = _normalized_spell(match.group("spell"))
            if self._is_persistent_haste_spell(spell):
                self._remove_haste("pet", spell)
            return []
        if match := CHARM_CAST_BEGIN_RE.match(body):
            if _normalized_spell(match.group("spell")) in CHARM_SPELLS:
                self._last_charm_cast = timestamp
            return []
        if match := CHARM_GLAZE_RE.match(body):
            pet = match.group("pet")
            recently_charming = (
                self._last_charm_cast is not None
                and 0 <= timestamp - self._last_charm_cast <= CHARM_GLAZE_WINDOW_S
            )
            if recently_charming or self._is_pet(pet):
                self._remember_pet(pet, charmed=True)
            return []
        if match := SPELL_WORN_OFF_RE.match(body):
            spell = _normalized_spell(match.group("spell"))
            target = match.group("target")
            if spell in CHARM_SPELLS:
                self._forget_pet(target)
            elif self._is_pet(target) and self._is_persistent_haste_spell(spell):
                self._remove_haste("pet", spell)
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
            # Summoned pets cannot share a name with hostile NPCs, so one
            # attacking us is strong evidence ownership ended. Charmed NPCs
            # routinely *do* share names; only the charm-expiry line may clear
            # those or an unrelated same-named mob will erase pet attribution.
            if self._is_pet(match.group("source")) and not self._is_charmed_pet(
                match.group("source")
            ):
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
                if self._is_pet(source) and not self._is_charmed_pet(source):
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

    def _remember_pet(self, name: str, *, charmed: bool = False) -> None:
        key = name.strip().casefold()
        if key not in self._pets:
            # EQL exposes one controllable pet at a time. A different known pet
            # proves replacement; the first identity found during startup replay
            # does not prove whether that already-existing pet is hasted.
            replacing = bool(self._pets)
            self._pets.clear()
            self._charmed_pets.clear()
            if replacing:
                self._set_haste_missing("pet")
        self._pets[key] = name.strip()
        if charmed:
            self._charmed_pets.add(key)

    def _forget_pet(self, name: str) -> None:
        key = name.strip().casefold()
        if key not in self._pets:
            return
        self._pets.pop(key, None)
        self._charmed_pets.discard(key)
        self._set_haste_missing("pet")

    def _forget_all_pets(self) -> None:
        self._pets.clear()
        self._charmed_pets.clear()
        self._set_haste_missing("pet")

    @staticmethod
    def _is_persistent_haste_spell(spell: str) -> bool:
        # Ranked spells normalize to their base name. Burnout ranks are named
        # "Burnout II/III/IV", while every other supported family is exact.
        return spell in PERSISTENT_HASTE_SPELLS or spell.startswith("burnout ")

    @staticmethod
    def _pet_haste_source(body: str) -> str:
        lowered = body.casefold()
        if lowered.endswith(" begins to move faster."):
            return "haste"
        if lowered.endswith(" foams at the mouth."):
            return "spirit quickening"
        if lowered.endswith(" goes berserk."):
            return "burnout"
        return "standard"

    @staticmethod
    def _haste_family(source: str) -> str:
        normalized = _normalized_spell(source)
        if normalized in {"quickness", "alacrity", "celerity", "swift like the wind"}:
            return "standard"
        if normalized.startswith("burnout"):
            return "burnout"
        return normalized

    def _add_haste(self, actor: str, source: str) -> None:
        self._haste_sources[actor].add(self._haste_family(source))
        self._haste_states[actor] = HasteState.ACTIVE

    def _remove_haste(self, actor: str, source: str) -> None:
        sources = self._haste_sources[actor]
        family = self._haste_family(source)
        if family in sources:
            sources.discard(family)
        elif not sources:
            # Startup replay may include a fade without its older landing line.
            # That fade still proves persistent haste is gone. If another family
            # is confirmed active, however, an unrelated fade must not clear it.
            self._haste_states[actor] = HasteState.MISSING
            return
        self._haste_states[actor] = HasteState.ACTIVE if sources else HasteState.MISSING

    def _set_haste_unknown(self, actor: str) -> None:
        self._haste_sources[actor].clear()
        self._haste_states[actor] = HasteState.UNKNOWN

    def _set_haste_missing(self, actor: str) -> None:
        self._haste_sources[actor].clear()
        self._haste_states[actor] = HasteState.MISSING

    def _is_charmed_pet(self, name: str) -> bool:
        return name.strip().casefold() in self._charmed_pets

    def _is_pet(self, name: str) -> bool:
        lowered = name.strip().casefold()
        if lowered in self._pets:
            return True
        if self.character_name:
            possessive = f"{self.character_name.casefold()}`s "
            return lowered.startswith(possessive)
        return False
