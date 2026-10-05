# Five Nights at Freddy's: Help Wanted × Archipelago

An unofficial [Archipelago](https://archipelago.gg) multiworld integration for **Five Nights at Freddy's: Help Wanted** (PC, Steam).
Play the game's nights and minigames normally; what you *get* for them is decided by the multiworld.

> Fan project, not affiliated with Scott Cawthon or Steel Wool Studios. No game files are included. You need your own copy of the game.

## What it does

- **153 locations**: 40 levels (FNAF 1–3 nights, Parts & Service, Vent Repair, Dark Rooms, Night Terrors, including the hard versions),
  30 Faz Tokens, 16 Glitch Tapes, 57 prizes, the Blackjack win, the hub trophies, Pizza Party, the normal ending, and 6 goals.
  (The game's list has 81 prizes, but 24 of them have no id in the save, so nothing could ever report them: they are not created.
  Their location ids stay reserved. Details in [docs/game-research.md](docs/game-research.md).)
- **Level unlocks come from items.** In `per_section` mode one item unlocks a whole section; in `per_level` mode every level has its own
  item. An item unlocks its level on its own, even when the game's usual order (Night 1 before Night 2) would not allow it yet.
  Gameplay and check sending are untouched: the mod only decides what the game shows as unlocked.
- **Your normal save is never touched.** Archipelago plays on its own save file (`Playerarchi.sav`); `Player00.sav` stays as it is.
- **Faz Token count follows the Faz Token items you received**, so the TV and the prize counter match your multiworld progress.
- **Two ways to run the client:** inside the Archipelago launcher (*FNAF Help Wanted Client*, recommended) or a standalone Python client.

## Requirements

| | |
| :--- | :--- |
| OS | Windows 10/11 |
| Game | Five Nights at Freddy's: Help Wanted on Steam |
| Archipelago | 0.6.7 or newer |
| UE4SS | v3.0.1 (the version this was tested with), installed in the game folder. **Not included**: the installer checks for it and tells you where to get it |

## Quick start

1. Download the latest release zip and unpack it.
2. Run `install-mod.ps1` (right-click → *Run with PowerShell*). It checks UE4SS, installs the mod and copies the apworld into Archipelago.
3. Copy `templates/Five Nights at Freddy's Help Wanted.yaml`, edit your options, generate or join a room.
4. Start **FNAF Help Wanted Client** from the Archipelago launcher, connect to your room, then start the game.

Full instructions and troubleshooting: [docs/installation.md](docs/installation.md).

## Options

| Option | Values | Meaning |
| :--- | :--- | :--- |
| `goal` | 6 goals | What completes your game (all levels, all levels in hard mode, the Glitchtrap endings, 100 %, a Faz Token and tape quota). |
| `required_tapes`, `required_faz_tokens` | numbers | Quotas for the goals that use them. |
| `unlock_mode` | `per_section` / `per_level` | One item per section, or one per level. |
| `hard_variants` | `grouped` / `separate` | `per_section` only: hard levels share the section item or need their own. |
| `starting_section` | 7 sections | Which section you start in (its item, or only its first level in `per_level`). |
| `death_link` | on / off | Losing a level sends a death; a death from another player makes you lose the level you are in (not in the hub yet, see below). |

## Status

Verified in the real game and room: level checks, Faz Token pickups, prize rewards, tapes, level unlocking in `per_section` and `per_level` mode
(including opening a level whose game prerequisite is not met), exactly-once item delivery, the Faz Token count, and the whole flow through the
launcher client.

Not finished or not verified yet:

- **DeathLink**: **sending works** (verified in game with Hollow Knight: losing a level kills the other player). **Receiving** is implemented (a death
  makes you lose the level you are in, by calling the game's own `LevelDefeat`; verified in game with Hollow Knight, both directions). In the hub nothing
  happens, and the game's jumpscare is not played (you get the game-over flow directly).
- **Pizza Party**: the mod never locks it, and the unlock rule of the game is not known, so the logic expects every level to be cleared first.
- **Items without an in-game effect**: Glitch Tape, Prize Counter Key, Nightmare Mode License (effect unverified) and the traps only matter for logic today.
- `hard_variants: separate` has been generated and tested but not played in a room. VR launch has not been tested (flat mode has).
- **Crashes** (2026-10-04 analysis, [docs/game-research.md](docs/game-research.md#crashes)): the game's own crash a few seconds after launch is not
  caused by the mod; just relaunch. A crash during play (about once an hour) was traced to the mod running UE4SS timers off the game thread and
  decoding garbage strings. The fix is in, **HYPOTHESIS until it has survived long play sessions**. The log now has `[DIAG]` lines for that.
- **Tape count**: the number of tapes shown in the tape area follows the Glitch Tape items you received (`derived_counters.lua`). **Verified in game with a forced value** (0 tapes in the save, forced 2 -> 2 tapes in the room); **verified with a real room**: 11 items in a row, a reconnect and a game restart (with and without the client) all gave the right number, and the shelf fills in order from `TAPE #1`. The room only re-reads the count when it loads, so leave it and re-enter after an item arrives. A save that never unlocked the tape room may keep it closed (HYPOTHESIS: a save flag, see docs/game-research.md). Playing a tape sends no check; only picking one up does.
- **Turning the mod off**: `archipelago_enabled = false,` in the mod's `config.lua` (or `FNAFHWArchipelago : 0` in `mods.txt`) gives the normal game on your normal save; see the install guide. Tested offline, not yet in a real launch.
- **Three goals cannot be generated** (`complete_all_minigames_nights_hard_mode`, `hundred_percent`, `token_tape_quota`): the logic asks for items Archipelago does not count. The default goal and the Glitchtrap endings work. See docs/TODO.md.
- **The TV's 5/10/... coin prizes still follow the vanilla pickup**, not the Faz Token items you received. Open; needs a probe of the award path.

Details and the running list: [docs/TODO.md](docs/TODO.md).

## How it works

```text
 Archipelago server <──websocket──> client (launcher or standalone)
                                        │  bridge folder: ap_inbox.txt / ap_outbox.txt
                                        ▼
                         UE4SS Lua mod inside the game  ── hooks game functions
```

The client turns server packets into short text lines for the mod, and the mod's events (a level won, a coin picked up, …) into location checks.
Architecture, protocol and research notes are in [docs/](docs/README.md).

## Repository layout

| Folder | Content |
| :--- | :--- |
| `fnaf_help_wanted/` | The apworld: items, locations, options, rules, and the launcher client (`client.py`). |
| `ap_client/` | The standalone client and the shared, transport-free core (`bridge_core.py`, `save_reader.py`). |
| `ue4ss_mod/FNAFHWArchipelago/` | The UE4SS Lua mod. |
| `scripts/` | Build, install and launch scripts, and `crash_report.py` (summarises a game crash dump for a bug report). |
| `templates/` | The player yaml template. |
| `tests/` | The test suite (no game or save files needed). |
| `docs/` | Documentation. |

### For developers

```powershell
python -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m unittest discover -s tests     # the whole suite, nothing private required
scripts\build-apworld.ps1                              # dist\fnaf_help_wanted.apworld
scripts\build-release.ps1                              # dist\FNAF-HW-Archipelago-v<version>.zip
```

See [docs/testing.md](docs/testing.md) for what the tests cover and what only an in-game run can verify.

## License

[MIT](LICENSE). Archipelago and UE4SS are separate projects with their own licenses.
