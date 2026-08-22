# Damage Feed design

## Primary object: a damage event

Every qualifying outgoing line becomes one visible entry immediately. YOU and PET
have separate retained histories and separate windows; there are no synchronized
rows or blank placeholders.

Incoming damage, healing, incoming misses, resists, kills, Thorns, and other
damage-shield reflection are excluded. Outgoing misses remain because they explain
attack cadence.

## Encounter DPS

YOU and PET keep separate outgoing-damage totals on one shared encounter clock, so
both numbers use the same duration and remain directly comparable. Log timestamps
have one-second resolution, so both endpoint seconds count toward duration. Misses,
heals, incoming damage, and damage shields do not affect DPS.

A kill or more than the configured damage-lull timeout finalizes the encounter. The
completed result remains visible until the next qualifying hit starts a clean fight.
The default timeout is 10 seconds and Options permits 3–60 seconds.

## Window model

- The YOU window always exists and is visible.
- The PET window has independent position, size, scroll state, and history.
- Pet visibility is a persisted setting for classes without pets.
- Hidden Pet windows continue receiving events but never show themselves.
- Lock state, text size, history limit, log selection, Options, and Quit are shared.
- Existing combined geometry is migrated once into two half-width windows.

## Graphical grammar

| Element | Meaning |
|---|---|
| `YOU` | Player-originated stream; centered over its icon spine |
| `PET` | Identified-pet stream; centered over its icon spine |
| `123 DPS` | Actor encounter DPS; aligned with the right-hand value lane |
| `⚔` | Melee/auto-attack |
| `◆` | Physical skill such as Reave, Bash, or Cleave |
| `✦` | Spell damage |
| `ϟ` / `➶` | Proc or ranged event |
| `MISS` | Outgoing attack missed |
| Yellow/cyan amount | YOU/PET damage |
| Red amount | Critical damage |

Every window uses one center icon spine. Descriptions terminate against its left
side; values start from its right side. Icons have heavy outlines but no backing.
Labels and values use tight translucent black backing with 2px vertical padding.
The row pitch is a compact 34px at 100% text size rather than the former 44px.

## Interaction

- Entries read chronologically top-to-bottom; new events arrive at the bottom.
- Each window scrolls its own retained history.
- New activity does not move a history window while it is being reviewed.
- Hovering an entry reveals source, ability, amount, target, and critical status.
- Hovering a top edge reveals status, Options, and Quit.
- Dragging moves only that window; edges/corners resize only that window.
- Width adds description room; height controls physical row capacity.
- Text size is independent from both window dimensions.
- `Ctrl+Alt+L` toggles click-through for both windows.

## Attribution boundary

The log includes third-party NPC and player combat. YOU uses player-originated
`You ...` damage plus player-attributed DoTs/procs. PET uses sources identified
through `/pet attack`, `/pet leader`, or the player's possessive warder naming
convention.

At startup, the parser scans a bounded recent-log tail for pet ownership markers
before following new bytes. Unidentified third-party combat is discarded. This
intentionally favors silence over crediting a random NPC to the player.
