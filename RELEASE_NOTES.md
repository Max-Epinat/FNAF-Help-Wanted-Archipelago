Second test release of **FNAF Help Wanted x Archipelago**. Still a prerelease: it works in the real game and in a real room, but it has had little outside testing.

## What changed since 0.1.0

- **The tape count follows your Glitch Tape items.** The number of tapes in the tape area equals the Glitch Tape items you have received (checked in game with a real `!getitem Glitch Tape`).
  Not checked yet: several items at once, a reconnect, and which tapes are shown.
- **24 prize locations are gone.** They have no prize id in the game's save, so nothing could ever report them, and the fill could put an item there that nobody could receive.
  The world now has **153 locations (57 prizes)**. Location ids did not change.
  New multiworlds need this version's `fnaf_help_wanted.apworld`; a room generated with 0.1.0 should keep working because no id moved (not tested with an old room).
- **Crash fixes (not proven yet).** A dump of a mid-session crash showed the mod running its timers on a background thread and decoding text the game stores in a different format.
  Timers now run on the game thread, the prize list is only counted, the map name is read another way, and only the last connect of the inbox history is replayed at launch.
  This is my best explanation from the crash dumps, **not confirmed by a long play session yet**. Please tell me if the game still crashes mid-play.
- **Diagnostics.** `UE4SS.log` now has `[DIAG] map: 'A' -> 'B'` lines and a status line every minute, and a loop error shows once as `[ERROR] [LOOP] ...`.
- The research tools (off by default) refuse the functions that blacked out the tape area when hooked.

## Quick start

You need Windows, the Steam game, [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.7 or newer, and
**UE4SS v3.0.1** (a game mod loader, not included: <https://github.com/UE4SS-RE/RE-UE4SS/releases>).

1. **Install UE4SS once.** Extract it into `...\steamapps\common\FNAFVRHelpWanted\freddys\Binaries\Win64\` (next to
   `freddys-Win64-Shipping.exe`), start the game once, then close it.
2. **Install the mod and the world.** Download `FNAF-HW-Archipelago-v0.2.0.zip`, unpack it and run `install-mod.ps1`
   (right-click, *Run with PowerShell*). It finds the game, checks UE4SS, installs the mod and copies the world into
   Archipelago's `custom_worlds`. Updating from 0.1.0: run it again.
3. **Set your options.** Copy `templates/Five Nights at Freddy's Help Wanted.yaml` into your Archipelago `Players` folder and edit it
   (unlock mode, starting section, DeathLink...). Generate a multiworld with it, or give it to whoever hosts.
4. **Play.**
   1. Open the **Archipelago Launcher** and start **FNAF Help Wanted Client**.
   2. Type the server address (for example `archipelago.gg:12345`) in the bar at the top and connect. Type your slot name if asked.
   3. **Then** start the game from Steam. The mod connects to the client by itself.

Your normal save is never touched: Archipelago plays on its own save file. Full guide, saves and troubleshooting: `INSTALL.md` in the zip.

**Only hosting a room?** You just need `fnaf_help_wanted.apworld` (in `custom_worlds`); the players need the yaml.

## What works (tested in the real game and a real room)

Level, Faz Token, glitch tape and prize checks, per-section and per-level unlocks, resuming a room, the Faz Token count, the tape count (one item), and DeathLink both ways
(a death from a friend makes you lose the level you are in; no jumpscare, and nothing happens in the hub).

## Not verified yet, or known problems

- `hard_variants: separate`, VR, the Pizza Party unlock rule, starting a new seed from a completed save.
- 0.2.0 moved every timer of the mod onto the game thread. Level checks, DeathLink and reconnects were verified on 0.1.0 and have had only a short run on 0.2.0.
- **The TV's 5/10/... coin prizes still follow the coins you pick up**, not the Faz Token items you receive.
- The game can crash **a few seconds after launch**. The crash dumps put that crash inside the game's own program, not in the mod's code: just relaunch.
- The mid-play crash fix above is unproven.

Found a bug? Open an issue and attach `...\Win64\UE4SS.log`. **Copy that file before you start the game again**: it is overwritten at every launch.
