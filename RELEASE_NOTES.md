Test release of **FNAF Help Wanted x Archipelago** (prerelease).

> **Warning: rooms generated before this version will not work with it. Regenerate them with this apworld.** Their tape item ("Glitch Tape") no
> longer exists: the game ignores it and the tape room stays empty. Update both the apworld **and** the mod.

## What's new (next version)

- **Every tape is unique.** There are 16 tape items, one per log, named like the label in the tape room: "Glitch Tape #01 (Intro)", "Glitch Tape #02 (FNAF 1)", ... "Glitch Tape #16 (Hub)". The tape room shows exactly the logs you received, side by side with no gaps (if you have #02 and #09, the shelf shows TAPE #2 and TAPE #9).
- When you enter the tape room the labels change within about a second. Before that the shelf shows the first tapes in plain order, so a tape played in that moment can be a log you do not have yet (it never sends a check).
- **Every goal can be generated now.** `complete_all_minigames_nights_hard_mode`, `hundred_percent` and `token_tape_quota` used to fail with "Game appears as unbeatable"; they now generate with any mix of the prize / Faz Token / tape options.
- The hard mode goal needs every level (hard ones included) and Pizza Party. It no longer asks for the Nightmare Mode License, which is still in the item pool.
- Faz Tokens and tapes now count for the goals that ask for them: exactly as many are marked important as your goal needs (none for the level goals, your quota, or all of them for 100 %), and which tapes is random per seed; the others are ordinary items. In game the TV counts every Faz Token as before (to be confirmed in a real room).
- A seed that cannot fit is refused with a message saying what to change (for example 100 % with unlock_mode per_level and prizes off has more important items than checks).
- **No more seeds stuck on a tape, token or prize inside a locked level.** Each one now needs the level(s) it is really in (read from the game's files), and a prize needs any level you can win. Unlock items can now be anywhere you can really reach.
- Checks nothing could ever tick are gone: Hub Trophies, Normal Ending, Blackjack and the goals you did not pick. A full seed has 146 checks (145 with the Glitchtrap "You Do Not Die" goal). A few checks whose condition is unsure (hub tapes, Helpy Plush, the Bobbleheads) only hold filler.

## Install

You need Windows, the Steam game, [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.7+ and [UE4SS v3.0.1](https://github.com/UE4SS-RE/RE-UE4SS/releases).

1. Extract UE4SS into `...\FNAFVRHelpWanted\freddys\Binaries\Win64\`, start the game once, close it.
2. Unzip `FNAF-HW-Archipelago-v0.4.2.zip` and double-click `install-mod.bat`.
3. Put the yaml from `templates` in your Archipelago `Players` folder and edit it.
4. Start **FNAF Help Wanted Client** from the Archipelago Launcher, connect, **then** start the game.

Your normal save is never touched. More help: `INSTALL.md` in the zip.

## Known problems

- The game sometimes crashes a few seconds after launch: just start it again.
- Rooms generated with an older version show no tapes in the tape room (see the warning at the top): regenerate them.
- VR is untested.

Found a bug? Open an issue with `...\Win64\UE4SS.log` (copy it **before** restarting the game) and, after a crash, the newest folder in `%LOCALAPPDATA%\freddys\Saved\Crashes`.
