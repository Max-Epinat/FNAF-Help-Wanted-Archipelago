Test release of **FNAF Help Wanted x Archipelago** (prerelease).

## What's new (next version)

- **Every goal can be generated now.** `complete_all_minigames_nights_hard_mode`, `hundred_percent` and `token_tape_quota` used to fail with "Game appears as unbeatable"; they now generate with any mix of the prize / Faz Token / tape options.
- The hard mode goal needs every level (hard ones included) and Pizza Party. It no longer asks for the Nightmare Mode License, which is still in the item pool.
- The 30 Faz Tokens that replace the token pickups now count for the goals. The extra Faz Tokens that fill spare slots don't. In game a Faz Token is still a Faz Token: the TV counts all of them, as before (to be confirmed in a real room).
- Only new rooms change. Rooms you already generated keep working. Update the apworld; the mod is unchanged.

## Install

You need Windows, the Steam game, [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.7+ and [UE4SS v3.0.1](https://github.com/UE4SS-RE/RE-UE4SS/releases).

1. Extract UE4SS into `...\FNAFVRHelpWanted\freddys\Binaries\Win64\`, start the game once, close it.
2. Unzip `FNAF-HW-Archipelago-v0.4.2.zip` and double-click `install-mod.bat`.
3. Put the yaml from `templates` in your Archipelago `Players` folder and edit it.
4. Start **FNAF Help Wanted Client** from the Archipelago Launcher, connect, **then** start the game.

Your normal save is never touched. More help: `INSTALL.md` in the zip.

## Known problems

- The game sometimes crashes a few seconds after launch: just start it again.
- VR is untested.

Found a bug? Open an issue with `...\Win64\UE4SS.log` (copy it **before** restarting the game) and, after a crash, the newest folder in `%LOCALAPPDATA%\freddys\Saved\Crashes`.
