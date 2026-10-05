Third test release of **FNAF Help Wanted x Archipelago**. Still a prerelease: it works in the real game and in a real room, but it has had little outside testing.

## What changed since 0.2.0

- **Seeds can no longer be made unfinishable by where the unlock items land.** New multiworlds put the level and section unlock items (access passes, toolkits, level unlocks) only on the 40 level-completion locations.
  Before, every seed put about 14 of them on tapes, Faz Tokens, prizes and similar locations, which could lock a level behind its own unlock item if that pickup sits inside the level.
  Checked with the real Archipelago generator: 297 runs (every unlock mode, every starting section, three goals), none misplaced, none failed. A room generated with 0.2.0 keeps its old placements; to get the new rule, generate with this version's `fnaf_help_wanted.apworld`.
- **Playing a tape in the tape room no longer sends a check.** The room shows as many tapes as Glitch Tape items you received, so you could play tapes you never picked up, and each one sent its location check (found in a real room: every Glitch Tape item was a free check).
  Now only picking a tape up counts. Covered by tests; **not re-checked in the game yet**.
- **The `nightmare_logic` option is gone.** It only added an invented extra requirement (the Nightmare Mode License) to the two Glitchtrap goals, and with it on those goals could not be generated. Yamls that still contain it keep working (Archipelago only prints a warning).
- **You can turn the mod off** to play the normal game on your normal save: add `archipelago_enabled = false,` to the mod's `config.lua` (or set `FNAFHWArchipelago : 0` in `mods.txt`), then restart the game. Steps in `INSTALL.md`. The option itself is tested; **a real launch with it set has not been done yet**.
- **The tape count was tested much further in the real game**: 11 items in a row, a reconnect, and a game restart with and without the client all gave the right number, and the room fills its shelf in order (`TAPE #1`, `#2`, ... down the left column, then the right one).
- For maintainers: `scripts/generator_check.py` runs the full generator on the world and checks every seed (the old "fill only" check did not verify that a seed can be beaten).

## Quick start

You need Windows, the Steam game, [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.7 or newer, and
**UE4SS v3.0.1** (a game mod loader, not included: <https://github.com/UE4SS-RE/RE-UE4SS/releases>).

1. **Install UE4SS once.** Extract it into `...\steamapps\common\FNAFVRHelpWanted\freddys\Binaries\Win64\` (next to
   `freddys-Win64-Shipping.exe`), start the game once, then close it.
2. **Install the mod and the world.** Download `FNAF-HW-Archipelago-v0.3.0.zip`, unpack it and run `install-mod.ps1`
   (right-click, *Run with PowerShell*). It finds the game, checks UE4SS, installs the mod and copies the world into
   Archipelago's `custom_worlds`. Updating from an older version: run it again (it also turns the mod back on and rewrites `config.lua`).
3. **Set your options.** Copy `templates/Five Nights at Freddy's Help Wanted.yaml` into your Archipelago `Players` folder and edit it
   (unlock mode, starting section, DeathLink...). Generate a multiworld with it, or give it to whoever hosts.
4. **Play.**
   1. Open the **Archipelago Launcher** and start **FNAF Help Wanted Client**.
   2. Type the server address (for example `archipelago.gg:12345`) in the bar at the top and connect. Type your slot name if asked.
   3. **Then** start the game from Steam. The mod connects to the client by itself.

Your normal save is never touched: Archipelago plays on its own save file. Full guide, saves and troubleshooting: `INSTALL.md` in the zip.

**Only hosting a room?** You just need `fnaf_help_wanted.apworld` (in `custom_worlds`); the players need the yaml.

## What works (tested in the real game and a real room)

Level, Faz Token, glitch tape and prize checks, per-section and per-level unlocks, resuming a room, the Faz Token count, the tape count (several items, reconnect, restart), and DeathLink both ways
(a death from a friend makes you lose the level you are in; no jumpscare, and nothing happens in the hub).

## Not verified yet, or known problems

- **Three of the six goals cannot be generated**: `complete_all_minigames_nights_hard_mode`, `hundred_percent` and `token_tape_quota` always fail with *Game appears as unbeatable* (the logic asks for items Archipelago does not count).
  The default goal and the two Glitchtrap endings work. A fix is planned; until then do not pick those three.
- **The tape room can stay closed on a save that never unlocked it.** In a test, an Archipelago save built from a never-played save refused entry even with Glitch Tape items, and opened once one save flag (`UnlockedAudioLog`) was set. The cause is likely, not confirmed. If you start from a normal save that has already used the tape room, you should not see it.
- **Where tapes, Faz Tokens and prizes really are in the game is not modelled** (they have no access rule in the logic). The unlock-items rule above keeps that from locking a level, but a goal could still wait for a tape you have not found yet. The Pizza Party unlock rule is also not known.
- `hard_variants: separate`, VR, and starting a new seed from a completed save have not been played in a real room.
- **The TV's 5/10/... coin prizes still follow the coins you pick up**, not the Faz Token items you receive.
- The game can crash **a few seconds after launch**, sometimes several times in a row (the crash dumps have shown the same crash inside the game's own program since April, before this mod): just relaunch.
- The mid-play crash fix of 0.2.0 is still unproven.

Found a bug? Open an issue and attach `...\Win64\UE4SS.log`. **Copy that file before you start the game again**: it is overwritten at every launch.
