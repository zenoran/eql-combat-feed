from eql_combat_feed.models import EventKind
from eql_combat_feed.parser import EqlCombatParser, character_name_from_log

TS = "[Sat Aug 22 10:13:22 2026] "


def parse(body: str):
    return EqlCombatParser("Hero").parse_line(TS + body)


def test_character_name_from_log() -> None:
    assert character_name_from_log("eqlog_Hero_freeport.txt") == "Hero"
    assert character_name_from_log("other.txt") is None


def test_outgoing_melee_spell_skill_and_critical() -> None:
    melee = parse("You slash a dread skeleton for 122 points of damage.")[0]
    spell = parse("You hit a dread skeleton for 120 points of magic damage by Reaving Strike.")[0]
    skill = parse("You reave a dread skeleton for 81 points of damage. (Critical)")[0]

    assert (melee.kind, melee.amount, melee.ability) == (EventKind.MELEE, 122, "Melee")
    assert (spell.kind, spell.amount, spell.ability) == (
        EventKind.SPELL,
        120,
        "Reaving Strike",
    )
    assert (skill.kind, skill.amount, skill.ability, skill.critical) == (
        EventKind.SKILL,
        81,
        "Reave",
        True,
    )


def test_heal_uses_actual_amount_not_parenthetical_raw_value() -> None:
    event = parse("You healed Hero for 49 (127) hit points by Lifedraw.")[0]
    assert (event.kind, event.amount, event.ability) == (EventKind.HEAL, 49, "Lifedraw")


def test_incoming_multiword_source_spell_melee_dot_and_shield() -> None:
    parser = EqlCombatParser("Hero")
    melee = parser.parse_line(TS + "Linara Parlone punches YOU for 31 points of damage.")[0]
    spell = parser.parse_line(
        TS + "Linara Parlone hit you for 32 points of magic damage by Chaotic Feedback."
    )[0]
    dot = parser.parse_line(TS + "You have taken 29 damage from Searing Arrow by a magician pet.")[
        0
    ]
    shield = parser.parse_line(
        TS + "YOU are burned by a magician's flames for 6 points of non-melee damage!"
    )[0]

    assert (melee.source, melee.amount, melee.incoming) == ("Linara Parlone", 31, True)
    assert (spell.source, spell.ability, spell.amount) == (
        "Linara Parlone",
        "Chaotic Feedback",
        32,
    )
    assert (dot.source, dot.ability, dot.amount) == (
        "a magician pet",
        "Searing Arrow",
        29,
    )
    assert (shield.kind, shield.amount, shield.incoming) == (
        EventKind.DAMAGE_SHIELD,
        6,
        True,
    )


def test_miss_resist_and_kill_status_events() -> None:
    miss = parse("A magician pet tries to kick YOU, but misses!")[0]
    resist = parse("You resist a magician pet's Earth Elemental Attack!")[0]
    kill = parse("You have slain a dread skeleton!")[0]

    assert (miss.kind, miss.incoming, miss.source) == (EventKind.MISS, True, "A magician pet")
    assert (resist.kind, resist.incoming, resist.ability) == (
        EventKind.RESIST,
        True,
        "Earth Elemental Attack",
    )
    assert (kill.kind, kill.target) == (EventKind.KILL, "a dread skeleton")


def test_pet_must_be_identified_before_damage_is_credited() -> None:
    parser = EqlCombatParser("Hero")
    line = TS + "A dread skeleton pierces a goblin for 36 points of damage."
    assert parser.parse_line(line) == []

    parser.parse_line(TS + "A dread skeleton told you, 'Attacking a goblin Master.'")
    event = parser.parse_line(line)[0]
    assert (event.kind, event.amount, event.source) == (
        EventKind.PET,
        36,
        "A dread skeleton",
    )


def test_charm_lands_and_pet_is_credited_without_pet_attack_order() -> None:
    """Real trace from Zenoran's log: charmed crusader was invisible until
    an explicit /pet attack produced the 'Attacking X Master' handshake."""
    parser = EqlCombatParser("Zenoran")
    swing = TS + "An elemental crusader slashes an elemental wizard for 115 points of damage."
    assert parser.parse_line(swing) == []

    parser.parse_line(TS + "an elemental crusader has been charmed.")
    event = parser.parse_line(swing)[0]
    assert (event.kind, event.amount) == (EventKind.PET, 115)


def test_bard_charm_glaze_credits_pet_without_charmed_line() -> None:
    """Real trace from Zenoran's Plane of Fear farm: Solon's Bewitching Bravura
    emits no 'has been charmed.' line — the only land signal is
    "<mob>'s eyes glaze over." The charmed abhorrent's entire encounter went
    untracked because the parser never learned it was a pet."""
    parser = EqlCombatParser("Zenoran")
    swing = TS + "An abhorrent hits an ire ghast for 68 points of damage."
    assert parser.parse_line(swing) == []

    parser.parse_line(TS + "You begin singing Solon's Bewitching Bravura.")
    parser.parse_line(TS + "an abhorrent's eyes glaze over.")
    event = parser.parse_line(swing)[0]
    assert (event.kind, event.amount, event.source) == (EventKind.PET, 68, "An abhorrent")


def test_glaze_without_recent_own_charm_cast_is_ignored() -> None:
    """Another player's charm also prints the glaze line; without our own
    recent charm cast it must not create a pet."""
    parser = EqlCombatParser("Zenoran")
    parser.parse_line(TS + "an abhorrent's eyes glaze over.")
    assert parser.parse_line(TS + "An abhorrent hits an ire ghast for 68 points of damage.") == []


def test_glaze_outside_charm_window_is_ignored_but_reglaze_refreshes_known_pet() -> None:
    parser = EqlCombatParser("Zenoran")
    late = "[Sat Aug 22 10:14:22 2026] "  # 60s after TS, outside the 12s window
    rat_swing = "A revultant rat bites an ire ghast for 40 points of damage."
    parser.parse_line(TS + "You begin singing Solon's Bewitching Bravura.")
    parser.parse_line(late + "a revultant rat's eyes glaze over.")
    assert parser.parse_line(late + rat_swing) == []

    # But a held song silently re-lands on later pulses: once known, a
    # re-glaze refreshes the same pet regardless of the window.
    parser.parse_line(TS + "You begin singing Solon's Bewitching Bravura.")
    parser.parse_line(TS + "a revultant rat's eyes glaze over.")
    parser.parse_line(late + "a revultant rat's eyes glaze over.")
    assert parser.parse_line(late + rat_swing)[0].kind is EventKind.PET


def test_ranked_charm_song_and_bravura_expiry_clear_pet() -> None:
    parser = EqlCombatParser("Zenoran")
    parser.parse_line(TS + "You begin singing Solon's Bewitching Bravura III.")
    parser.parse_line(TS + "an abhorrent's eyes glaze over.")
    swing = TS + "An abhorrent hits an ire ghast for 68 points of damage."
    assert parser.parse_line(swing)[0].kind is EventKind.PET

    parser.parse_line(TS + "Your Solon's Bewitching Bravura spell has worn off of an abhorrent.")
    assert parser.parse_line(swing) == []


def test_same_named_hostile_does_not_erase_charmed_pet_identity() -> None:
    """Live trace: one lava crawler is charmed while identical crawlers hit YOU."""
    parser = EqlCombatParser("Zenoran")
    parser.parse_line(TS + "a lava duct crawler has been charmed.")
    swing = TS + "A lava duct crawler slashes a lava duct crawler for 120 points of damage."
    assert parser.parse_line(swing)[0].kind is EventKind.PET

    hit_you = parser.parse_line(TS + "A lava duct crawler bites YOU for 103 points of damage.")
    miss_you = parser.parse_line(TS + "A lava duct crawler tries to bite YOU, but misses!")
    assert hit_you[0].incoming
    assert miss_you[0].incoming
    assert parser.parse_line(swing)[0].kind is EventKind.PET


def test_recognized_charm_expiry_clears_pet_identity() -> None:
    parser = EqlCombatParser("Zenoran")
    parser.parse_line(TS + "a lava duct crawler has been charmed.")
    swing = TS + "A lava duct crawler slashes a lava duct crawler for 120 points of damage."
    assert parser.parse_line(swing)[0].kind is EventKind.PET

    parser.parse_line(
        TS + "Your Cajoling Whispers spell has worn off of a lava duct crawler."
    )
    assert parser.parse_line(swing) == []


def test_non_charmed_pet_turning_on_you_clears_identity() -> None:
    parser = EqlCombatParser("Zenoran")
    parser.parse_line(TS + "A dread skeleton told you, 'Attacking a goblin Master.'")
    swing = TS + "A dread skeleton slashes a goblin for 115 points of damage."
    assert parser.parse_line(swing)[0].kind is EventKind.PET

    incoming = parser.parse_line(TS + "A dread skeleton cleaves YOU for 18 points of damage.")
    assert incoming[0].incoming
    assert parser.parse_line(swing) == []


def test_outgoing_character_and_identified_pet_misses_preserve_attack_type() -> None:
    parser = EqlCombatParser("Hero")
    parser.parse_line(TS + "A dread skeleton told you, 'Attacking a goblin Master.'")

    melee_miss = parser.parse_line(TS + "You try to slash a goblin, but miss!")[0]
    skill_miss = parser.parse_line(TS + "You try to reave a goblin, but a goblin parries!")[0]
    pet_miss = parser.parse_line(
        TS + "A dread skeleton tries to bash a goblin, but a goblin dodges!"
    )[0]

    assert (melee_miss.kind, melee_miss.ability, melee_miss.source) == (
        EventKind.MISS,
        "Melee",
        "You",
    )
    assert (skill_miss.kind, skill_miss.ability) == (EventKind.MISS, "Reave")
    assert (pet_miss.kind, pet_miss.ability, pet_miss.source) == (
        EventKind.MISS,
        "Bash",
        "A dread skeleton",
    )


def test_unrelated_third_party_combat_is_ignored() -> None:
    assert parse("A dread skeleton pierces a dread skeleton for 31 points of damage.") == []
    assert (
        parse("a magician hit a dread skeleton for 200 points of magic damage by Shock of Spikes.")
        == []
    )
