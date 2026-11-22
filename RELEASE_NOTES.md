Test release of **FNAF Help Wanted x Archipelago** (prerelease).

> **Still true: rooms generated before 0.5.0 will not work.** Their tape item ("Glitch Tape") no longer exists: the game ignores it and the tape room stays empty. Regenerate them with this apworld. Rooms made with 0.5.0 keep working.

## What's new in 0.5.1

This update makes the client and the mod safer and harder to break. The randomizer does not change: your 0.5.0 rooms, yamls and saves keep working.

**Different from before**

- **Debug commands are off by default.** The console commands that change your game or the room (`ap_check_name`, `ap_check_id`, `ap_goal`, `F7`, `ap_gate_grant`, `ap_coin_force`, `ap_counter_force`, `ap_dl_kill` and the other `ap_dl_*` experiments) no longer exist unless you add `enable_debug_commands = true,` to the mod's `config.lua`. The status commands and the `F1` panel are unchanged.
- **Your room password is stored encrypted** (Windows DPAPI, tied to your Windows account) in `connection_secret.dat`, no longer in `connection_profile.json`. A password you had saved is moved there the first time the standalone client starts. On another PC or Windows account you simply enter it again.
- **The standalone client no longer opens a local port** (38424). Nothing else on your PC can send it commands any more.
- **archipelago.gg connections are always encrypted** (`wss`). Other hosts still try `ws` first, then `wss`.

**New**

- **The standalone client reconnects by itself** when the connection drops (after 2, 5, 10 and 30 seconds, then every 60) and resumes the same room and save. It does not retry after you press Disconnect, after a refusal (wrong password, slot taken) or when the address was never reachable.
- The **Send Goal** button asks you to confirm.

**Fixed**

- **`ap_connect <host> <port> <slot> [password]` from the game console works** (it failed with a Lua error). Plain `ap_connect` connects with the saved settings.
- **One bad line in the game's outbox file no longer stops the standalone client.**
- **A damaged `Player00.sav` no longer stops you from connecting.**
- **Updating no longer resets your setup.** `install-mod.ps1` keeps your `config.lua` settings and a switched-off mod in `mods.txt`, and removes files left behind by older versions.
- The panel and the client window show `/ 146` (a full seed) until they know the real total, instead of 153.
- The README no longer says three goals cannot be generated: they have worked since 0.5.0.

## Install

You need Windows, the Steam game, [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.7+ and [UE4SS v3.0.1](https://github.com/UE4SS-RE/RE-UE4SS/releases).

1. Extract UE4SS into `...\FNAFVRHelpWanted\freddys\Binaries\Win64\`, start the game once, close it.
2. Unzip `FNAF-HW-Archipelago-v0.5.1.zip` and double-click `install-mod.bat`.
3. Put the yaml from `templates` in your Archipelago `Players` folder and edit it.
4. Start **FNAF Help Wanted Client** from the Archipelago Launcher, connect, **then** start the game from Steam.

**Updating from 0.5.0:** run `install-mod.bat` from the new zip (it updates the mod and copies the new apworld into Archipelago, and keeps your `config.lua`). If you only host rooms, replace `fnaf_help_wanted.apworld` in `custom_worlds` with the new one. Update the apworld **and** the mod together.

Your normal save is never touched. More help: `INSTALL.md` in the zip.

## Known problems

- The game sometimes crashes a few seconds after launch: just start it again. Start it from Steam: starting `freddys-Win64-Shipping.exe` directly (what `scripts/launch-game.ps1` does) closed the game within seconds in our test.
- Standalone client window: when you set a new password in the in-game panel, the window's password box still shows the old one, and pressing Connect in the window saves that old text again.
- After a room server restarts without its save, the client and the panel can show a higher item count than the room really holds. Items are not given twice.
- Rooms generated with an older version show no tapes in the tape room (see the warning at the top): regenerate them.
- VR is untested.

Found a bug? Open an issue with `...\Win64\UE4SS.log` (copy it **before** restarting the game) and, after a crash, the newest folder in `%LOCALAPPDATA%\freddys\Saved\Crashes`.
