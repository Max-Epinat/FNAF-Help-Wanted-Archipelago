# Level gating (Archipelago authority over vanilla unlocks)

Goal: gameplay and location checks stay possible, but the game's own *vanilla* progression must not unlock levels
that Archipelago has not authorized. FNAF decides *what the player did*; Archipelago decides *what they get for it*.

## Mechanism (VERIFIED in game)

`Scripts/lib/level_gate.lua` hooks `BP_FNAF_GameInstance_C:IsLevelUnlocked(LevelID) -> bool`, which the night menus call when
the hub is built. After the game computes its answer, the hook replaces it for **gated rows** while an AP session is active:

```text
row not gated                            -> unchanged (the game's own answer)
no active AP session (no SESSION_SYNC)   -> unchanged (vanilla behaviour)
gate authorized in the current session   -> true    (even if the game said false: its prerequisite is waived)
otherwise                                -> false   (return_value:set(false))
```

- Archipelago decides: an item for FNAF 1 Night 3 unlocks it without Night 1 and Night 2 beaten. (Until 2026-10-04 the hook only
  *lowered* the answer. **Raising VERIFIED in game 2026-10-04**: with only `Unlock FNAF 1 - Night 3` received, `IsLevelUnlocked(6)`
  went `vanilla=false -> true (authorized (vanilla prerequisite waived))` and only Night 3 was open on screen; Nights 1, 2, 4 stayed locked.)
- It never touches `SaveLevelVictory`, so finishing a level and its location check are unaffected.
- `ReturnValue:set(false)` on the hook's return parameter is what works (VERIFIED); returning `false` from the callback does not.
- The menu only re-asks when the hub is **rebuilt** (main menu and back, any level load), so changes show up after a rebuild.
- Decision function: `LevelGate.decide(row, vanilla, session_active, authorized)` (pure).

## Data flow

```text
slot_data["level_gates"]  {row: GATE}     --GATE_TABLE-->      active rows   (default: {5 = FNAF1_NIGHT2})
slot_data["gate_items"]   {itemId: GATE}  --GATE_ITEMS-->      item -> gate map
server's received items                   --RECEIVED_SNAPSHOT--> authorized gates = gates of the items received
console debug grants                      -->                  merged with the above (never from the server)
```

Authorization is derived state: each snapshot replaces the item-derived set wholesale. The world emits `level_gates` and
`gate_items` (see below); the mod's built-in Night 2 default is only used when `slot_data` carries no table.

## Rows (VERIFIED from the game's `LevelInfoTable`)

FNAF 1 Night 1..4 = rows 4..7 (Night 5 hard = 8), FNAF 2 = 9..13, FNAF 3 = 14..18, Pizza Party (`Finale_Ending`) = **29**.
The first FNAF 1 night list asks `IsLevelUnlocked` for rows 4, 5, 6, 7 (`LevelID` is an `FName`: decode it with `get()` then `ToString()`).

## Console commands (debug)

| Command | Effect |
| :--- | :--- |
| `ap_gate_grant [GATE]` | Debug-authorize a gate (default `FNAF1_NIGHT2`). Cleared when the session id changes. |
| `ap_gate_revoke [GATE]` | Remove a debug grant. |
| `ap_gate_status` | Session, item count, item-derived and debug authorizations. |
| `ap_items_status` | Item sync: session, applied count, received count. |

Rebuild the hub after each command to see the effect. A debug grant survives snapshots; item-derived authorization does not
survive a snapshot that no longer contains the item.

## Adding a gate

1. Add `row = GATE_ID` to the table the world sends in `slot_data["level_gates"]` (ids match `^[A-Z0-9_]+$`).
2. Add `itemId = GATE_ID` to `slot_data["gate_items"]` for the item(s) that authorize it.
3. Make the world's rules require that item for the matching location(s) (the item alone unlocks the level).

## World options (`fnaf_help_wanted/levels.py`, `options.py`)

| Option | Values | Effect |
| :--- | :--- | :--- |
| `unlock_mode` | `per_section` (default), `per_level` | One item per section (the 7 existing items), or one item per level. |
| `hard_variants` | `grouped` (default), `separate` | Section mode only: hard variants share the section item, or need their own `... Hard Pass/Toolkit/Flashlight` item (6 sections; Night Terrors has none). Ignored in `per_level`, where every hard level has its own item. |
| `starting_section` | `fnaf_1` (default) .. `night_terrors` | Section mode: start with that section's item. Level mode: start with only that section's first level (normal level with the lowest row). |

- Pizza Party (row 29) is never gated by the mod (the game decides when it is playable). Rows 41+ (DLC) have no locations and are not gated.
- Item codes are append-only: 1..13 unchanged, 14..19 hard-section items, 20..59 per-level items (named `Unlock <level>`).
- In per-level mode the section and hard items are not in the pool (they would do nothing).
- `slot_data["level_gates"]` = `{"<row>": GATE}` (all 40 level rows), `slot_data["gate_items"]` = `{"<item id>": GATE}`.
  Section mode gates: `FNAF1`, `FNAF2`, `FNAF3`, `PARTS_SERVICE`, `VENT_REPAIR`, `DARK_ROOMS`, `NIGHT_TERRORS`, and `*_HARD`
  (separate mode). Level mode gates: one per level, e.g. `FNAF1_NIGHT2` (same id as the mod's built-in default).
- Start items are precollected, so the server sends them as received items and they authorize their gate.

### Rules (logic)

A level location requires exactly its own gate item (the section item in section mode, the hard item for a hard level in
`separate` mode, the level's item in per-level mode). There is no "previous level" chain: the item alone unlocks the level in
game, whatever the game's own prerequisite is. (An earlier version chained levels because the mod could only lower the game's
answer; see git history, commits 4ae0d57 and before.)

| Location | Logic requires |
| :--- | :--- |
| Any level (rows 0-28, 30-40) | its own gate item only |
| Pizza Party | **every level's item**: the mod never gates it and its vanilla unlock condition is UNVERIFIED |

Pizza Party being last in logic matters: before this rule the generator could place `Unlock FNAF 1 - Night 5 (Hard)` on
`Complete Pizza Party`, which the game may only offer after that very level. Goal/prize/token/tape locations keep their rules.

**Where unlock items may be placed: a STOPGAP** (2026-10-05; the intended end state is "anywhere that is really reachable", which needs the real access of tapes, tokens and prizes, see docs/TODO.md): only on the 40 level-completion locations (`levels.may_hold_unlock_item`, applied in `rules.py` with `add_item_rule`).
Tapes, Faz Tokens, prizes, the trophies, the blackjack win, Pizza Party and the goals are not modelled as gated, so an unlock item there could sit behind the very level it opens.
A level location needs only its own item (VERIFIED), so every unlock item can always be obtained by playing levels the player already has. The real generator check is in docs/testing.md.

## Verified in game (2026-10-04, new seed, section mode, starting section FNAF 2)

- The mod received the full table (40 rows) and the 7-entry gate item map, and the precollected FNAF 2 Access Pass (item snapshot)
  authorized `FNAF2`: `Progression authorization from items (snapshot): 1 items -> [FNAF2]`.
- The game asks `IsLevelUnlocked` for the minigame rows as well, not only for the nights. In the hub, with a fresh save:
  rows 4, 14, 0, 19, 23, 25 (first level of FNAF 1, FNAF 3, Dark Rooms, Parts and Service, Vent Repair, Night Terrors) were
  vanilla-open and **denied**; row 9 (FNAF 2 Night 1) stayed open (**authorized**). Only FNAF 2 Night 1 was playable on screen.
- Each list only asked about its first two rows (e.g. 0 and 1). The second one was always *vanilla locked* on a fresh save, which
  suggests minigames also unlock in order (**HYPOTHESIS**).

## Verified in game (2026-10-04, second seed: per-level mode, starting section FNAF 3)

- Start item `Unlock FNAF 3 - Night 1` (precollected, arrives in the item snapshot) authorized exactly `FNAF3_NIGHT1`; the previous
  session's `FNAF2` authorization was cleared by the session change. Only FNAF 3 Night 1 was playable, FNAF 2 Night 1 was locked.
- The hub asked `IsLevelUnlocked` for **every** gated row (0-28 and 30-40, normal and hard). Rows 4, 9, 0, 19, 23, 25 were
  vanilla-open and denied, row 14 authorized. Every other row was *vanilla locked* on a fresh save: the later levels of every
  minigame list (1-3, 20-22, 24, 26-28), all hard rows (8, 13, 18, 30-39) and Withered (40). So the hard variants and
  every minigame after the first of its list have some vanilla prerequisite. Which one (previous level in row order, or any
  beaten level of the list) is **not** distinguishable from this data (HYPOTHESIS).

## Verified in game (2026-10-04, third seed: per-level, raised unlock played)

- With only `Unlock FNAF 1 - Night 3` received, Night 3 loaded and played normally, beating it sent `Beat FNAF 1 - Night 3` to the server,
  and Night 4 stayed locked afterwards (user-reported; the check delivery was seen on the server).

## Not verified in game

- Separate hard items (`hard_variants: separate`) in a real room (generator-verified only).
- (Verified 2026-10-04: receiving a gate item mid-session updates the authorization; with the old lower-only hook, Night 2 opened once
  Night 1 was beaten.)
- Playing a gated level to completion (check sent, next level unlocking).
