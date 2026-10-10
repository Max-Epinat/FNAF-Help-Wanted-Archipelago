Fifth test release of **FNAF Help Wanted x Archipelago**: you can switch the prizes, the Faz Tokens and the glitch tapes out of the randomizer, and every room now has its own save. Still a prerelease: it works in the real game and in real rooms, but it has had little outside testing.

## What changed in 0.4.0 (since 0.3.1)

- **Three new options to cut the grind, all default on (so existing yamls behave exactly as before):** `randomize_prizes`, `randomize_faz_tokens` and `randomize_glitch_tapes`. Switch one off and that group is **vanilla**: it has no locations and no matching items
  (no Glitch Tape items with the tapes off, no base Faz Token items with the tokens off), you still collect it in the game, it just never sends a check.
  The multiworld gets fewer locations: 153 with everything on, 96 without prizes, 123 without Faz Tokens, 137 without tapes, 50 with all three off. Each toggle is independent.
  - With the tapes off the tape room shows the tapes you picked up (not the Glitch Tape items), and with the Faz Tokens off the TV shows the tokens you picked up.
  - **Goals never become impossible.** A goal that asks for tapes or tokens (`required_tapes`, `required_faz_tokens`, the Glitchtrap endings, 100 %) simply no longer asks for a group that is off. You still need them in the real game; the multiworld cannot check them.
  - With the Faz Tokens off, no Faz Token item is handed out either: the spare slots hold a new item, **Faz Coupon**, which does nothing. (With the tokens on the filler is still Faz Token, as before.)
  - The client drops every check of a group that is off (nothing sent, queued or logged as an error), and the in-game connection panel shows the real number of locations instead of 153.
  - Tested with the real Archipelago generator on all 8 combinations (576 runs: every goal, unlock mode, two starting sections, two seeds), with the real client core, and **by hand in real rooms, case by case: all three toggles work as intended**.
  - Side effect: `hundred_percent` and `token_tape_quota` now generate when `randomize_faz_tokens` is off (their requirement for Faz Token items is gone). This is not a fix of those goals (see below).
- **One Archipelago save per room.** Each multiworld plays on its own file, `Playerarchi_<seed>_<slot>.sav`, instead of one shared `Playerarchi.sav` that was archived whenever you joined a new room. Other rooms' saves are never touched, so going back to an older room should find its progress again.
  Rooms you started with an older version keep using `Playerarchi.sav` (nothing is renamed). The game writing progress into the new file names was seen in real rooms; **switching room while the game is already running, and going back to an older room, have not been checked yet** (start the client and connect first, then the game, and restart the game when you change room).
  The files of old rooms stay until you delete them by hand.
- **The client refuses to connect when its bridge cannot start**, and says why. (Found in a real test: a second client window was opened while the first was only `/disconnect`ed, which keeps its lock. The second window joined the new room silently with nothing written for the game, so the game kept using the previous room's save.
  Close the first window completely.)
- Update the apworld **and** the mod together (`install-mod.ps1` does both): an old mod keeps overriding the tape count and the TV, does not use the per-room save, and shows 153 locations. Rooms generated with an older version play as before.
- For maintainers: `scripts/generator_check.py --groups on,off,prizes+tapes,...` runs the full generator for the toggle combinations and compares the spoiler with the expected locations; 496 tests, and every new piece of logic was checked with deliberately broken copies (77 mutants, all caught).

## What changed in 0.3.1 (since 0.3.0)

- **New option `death_link_gift_box`** (default `true`, so existing yamls behave exactly as before). In the vanilla game the prize gift box you open after a minigame can hide a jumpscare instead of a reward, and that jumpscare is a game over, which sends a DeathLink when `death_link` is on.
  Set `death_link_gift_box: false` to keep that one game over from being sent (it still happens in your game). It only matters when `death_link` is on, it only changes sending, and deaths from other players are handled as before. Rooms generated before this option keep sending.
  The mod recognises the gift box game over by the map it happens on (`Level_Victory`). Seen working once in a real game with the option off (the gift box game over was held back, a real defeat 26 seconds later was sent); the other player's side and the other level types (only Parts and Service Bonnie was played) are **not checked yet**.

## What changed in 0.3.0 (since 0.2.0)

- **A cautious stopgap against unfinishable seeds.** The logic does not yet know where in the game each tape, Faz Token and prize really is, so for now new multiworlds put the level and section unlock items (access passes, toolkits, level unlocks) only on the 40 level-completion locations.
  Before, every seed put about 14 of them on tapes, Faz Tokens, prizes and similar locations, which could lock a level behind its own unlock item if that pickup sits inside the level.
  The goal is the opposite of a restriction: unlock items anywhere that is really reachable. This rule will be loosened once those locations are mapped.
- **Playing a tape in the tape room no longer sends a check.** The room shows as many tapes as Glitch Tape items you received, so you could play tapes you never picked up, and each one sent its location check. Now only picking a tape up counts.
- **The `nightmare_logic` option is gone.** It only added an invented extra requirement (the Nightmare Mode License) to the two Glitchtrap goals. Yamls that still contain it keep working (Archipelago only prints a warning).
- **You can turn the mod off** to play the normal game on your normal save: add `archipelago_enabled = false,` to the mod's `config.lua` (or set `FNAFHWArchipelago : 0` in `mods.txt`), then restart the game. Steps in `INSTALL.md`.

## Quick start

You need Windows, the Steam game, [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.7 or newer, and
**UE4SS v3.0.1** (a game mod loader, not included: <https://github.com/UE4SS-RE/RE-UE4SS/releases>).

1. **Install UE4SS once.** Extract it into `...\steamapps\common\FNAFVRHelpWanted\freddys\Binaries\Win64\` (next to
   `freddys-Win64-Shipping.exe`), start the game once, then close it.
2. **Install the mod and the world.** Download `FNAF-HW-Archipelago-v0.4.0.zip`, unpack it and run `install-mod.ps1`
   (right-click, *Run with PowerShell*). It finds the game, checks UE4SS, installs the mod and copies the world into
   Archipelago's `custom_worlds`. Updating from an older version: run it again (it also turns the mod back on and rewrites `config.lua`).
3. **Set your options.** Copy `templates/Five Nights at Freddy's Help Wanted.yaml` into your Archipelago `Players` folder and edit it
   (unlock mode, starting section, which of prizes / Faz Tokens / tapes are randomized, DeathLink...). Generate a multiworld with it, or give it to whoever hosts.
4. **Play.**
   1. Open the **Archipelago Launcher** and start **FNAF Help Wanted Client**. Only one client window at a time.
   2. Type the server address (for example `archipelago.gg:12345`) in the bar at the top and connect. Type your slot name if asked.
   3. **Then** start the game from Steam. The mod connects to the client by itself.

Your normal save is never touched: Archipelago plays on its own save files, one per room. Full guide, saves and troubleshooting: `INSTALL.md` in the zip.

**Only hosting a room?** You just need `fnaf_help_wanted.apworld` (in `custom_worlds`); the players need the yaml. Both are attached to this release on their own as well as inside the zip, which holds the world, the mod, the installer and the yaml template together.

## What works (tested in the real game and a real room)

Level, Faz Token, glitch tape and prize checks, per-section and per-level unlocks, resuming a room, the Faz Token count, the tape count (several items, reconnect, restart), the three randomize toggles on and off,
a separate save file per room, and DeathLink both ways
(a death from a friend makes you lose the level you are in; no jumpscare, and nothing happens in the hub; the gift box jumpscare can be kept out of what you send with `death_link_gift_box`, seen once).

## Not verified yet, or known problems

- **Two of the six goals still cannot be generated with the Faz Tokens randomized**, and one never can: `complete_all_minigames_nights_hard_mode` always fails with *Game appears as unbeatable*, and `hundred_percent` and `token_tape_quota` fail unless `randomize_faz_tokens` is off
  (the logic asks for items Archipelago does not count). The default goal and the two Glitchtrap endings work in every combination. A fix is planned.
- **The tape room can stay closed on a save that never unlocked it.** In a test, an Archipelago save built from a never-played save refused entry even with Glitch Tape items, and opened once one save flag (`UnlockedAudioLog`) was set. The cause is likely, not confirmed. If you start from a normal save that has already used the tape room, you should not see it.
- **Where tapes, Faz Tokens and prizes really are in the game is not modelled** (they have no access rule in the logic). The unlock-items rule above keeps that from locking a level, but a goal could still wait for a tape you have not found yet. The Pizza Party unlock rule is also not known.
- **The prizes are only checks:** you do not receive prizes as items, and the Prize Counter shows the prizes you won. Giving the prizes as items is planned.
- `hard_variants: separate`, VR, and starting a new seed from a completed save have not been played in a real room.
- **The TV's 5/10/... coin prizes still follow the coins you pick up**, not the Faz Token items you receive.
- The game can crash **a few seconds after launch**, sometimes several times in a row (the crash dumps have shown the same crash inside the game's own program since April, before this mod): just relaunch.
- The mid-play crash fix of 0.2.0 is still unproven.

Found a bug? Open an issue and attach `...\Win64\UE4SS.log`. **Copy that file before you start the game again**: it is overwritten at every launch.
