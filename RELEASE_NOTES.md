Test release of **FNAF Help Wanted x Archipelago** (prerelease).

## What's new in 0.4.2

- A possible fix for the game closing when you enter the hub: the mod now waits a few seconds after each map change before doing its background work. Not confirmed yet.
- Items can show up a few seconds later right after a map change.
- Your rooms, yamls and saves keep working. Just update the mod with `install-mod.bat`.

## Install

You need Windows, the Steam game, [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.7+ and [UE4SS v3.0.1](https://github.com/UE4SS-RE/RE-UE4SS/releases).

1. Extract UE4SS into `...\FNAFVRHelpWanted\freddys\Binaries\Win64\`, start the game once, close it.
2. Unzip `FNAF-HW-Archipelago-v0.4.2.zip` and double-click `install-mod.bat`.
3. Put the yaml from `templates` in your Archipelago `Players` folder and edit it.
4. Start **FNAF Help Wanted Client** from the Archipelago Launcher, connect, **then** start the game.

Your normal save is never touched. More help: `INSTALL.md` in the zip.

## Known problems

- The game sometimes crashes a few seconds after launch: just start it again.
- Some goals can't be generated yet (`complete_all_minigames_nights_hard_mode`, and `hundred_percent` / `token_tape_quota` with Faz Tokens randomized).
- VR is untested.

Found a bug? Open an issue with `...\Win64\UE4SS.log` (copy it **before** restarting the game) and, after a crash, the newest folder in `%LOCALAPPDATA%\freddys\Saved\Crashes`.
