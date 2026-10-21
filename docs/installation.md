# Installation guide

This is for players. You need Windows, the game on Steam, and [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.7 or newer.

## 1. Install UE4SS (once)

The mod runs inside the game through **UE4SS**, which is a separate project and is **not included** in this package.

1. Download **UE4SS v3.0.1** (the version this mod was tested with) from <https://github.com/UE4SS-RE/RE-UE4SS/releases>.
2. Extract it into the game's binaries folder, next to `freddys-Win64-Shipping.exe`:

   ```text
   <Steam>\steamapps\common\FNAFVRHelpWanted\freddys\Binaries\Win64\
   ```

   After extracting, that folder contains `UE4SS.dll`, `dwmapi.dll` and a `Mods` folder.
3. Start the game once, then close it.

## 2. Install the mod and the world

Unpack the release zip (all of it, do not run the installer from inside the zip), then **double-click `install-mod.bat`**. No terminal needed; the window stays open so you can read the result.
If the game is not found by itself (for example it is on another drive), the window asks for its folder: type or paste the folder that contains `freddys`
(for example `D:\SteamLibrary\steamapps\common\FNAFVRHelpWanted`) and press Enter.

(`install-mod.bat` only runs `install-mod.ps1` for you. From a terminal you can still use
`powershell -ExecutionPolicy Bypass -File install-mod.ps1`, with the options below.)

It will:

- find the game on any drive (where Windows says Steam is, every Steam library, then the usual folders; a leftover folder without the game in it is skipped),
  or use `-GameRoot "<folder that contains freddys>"` (or the environment variable `FNAFHW_GAME_ROOT`, which the client reads too),
- check that UE4SS is installed and stop with a link if it is not,
- install the mod into `...\Win64\Mods\FNAFHWArchipelago`, with its **bridge folder** inside it,
- enable the mod in `Mods\mods.txt`,
- copy `fnaf_help_wanted.apworld` into `Archipelago\custom_worlds` inside your `%ProgramData%` folder (usually `C:\ProgramData`; use `-ArchipelagoDir` if yours is elsewhere, or
  `-SkipApworld`; without Archipelago, double-click the `.apworld` file or copy it into `custom_worlds` by hand).

`-CheckOnly` reports what it finds and changes nothing. Running it again is safe (it is also how you update).

## 3. Set your options and get a room

1. Copy `templates/Five Nights at Freddy's Help Wanted.yaml` into your Archipelago `Players` folder and edit it (the comments explain each option).
   The launcher's *Generate Template Options* button also produces an up-to-date template.
   DeathLink: `death_link` turns it on. With it on, `death_link_gift_box` (default `true`) decides whether the game over from the prize gift box jumpscare is also sent as a death;
   set it to `false` to keep that one out. It changes nothing when `death_link` is off, and it never changes what happens when another player dies.
   Less grinding: `randomize_prizes`, `randomize_faz_tokens` and `randomize_glitch_tapes` (all `true` by default) each take one kind of collectible out of the randomizer.
   A group that is `false` has no locations, no matching items (Glitch Tape, the 30 base Faz Tokens) and is **vanilla in game**: you still pick the things up and the game
   shows them as usual (the tape room shows the tapes you picked up, the TV the tokens you picked up), it just never sends a check. A goal that asks for tapes or tokens
   no longer asks for the ones that are not randomized (you still need them in the real game; the multiworld simply cannot check them).
   Update the apworld **and** the mod together (`install-mod.ps1` does both): an old mod would keep showing item counts for a group that is `false`.
2. Generate a multiworld with your yaml, or give it to whoever hosts. See the Archipelago
   [setup guide](https://archipelago.gg/tutorial/Archipelago/setup/en) for hosting.

## 4. Play

1. Open the Archipelago launcher and start **FNAF Help Wanted Client**.
2. Type the server address (for example `archipelago.gg:12345`) in the bar at the top and connect. If it asks for a slot name, type it in
   the input at the bottom and press Enter. `/bridge` in the client shows the bridge folder, the session and counters.
3. Start the game from Steam. The mod connects to the client by itself; play normally.

Notes:

- **Only one client at a time.** The launcher client and the standalone client share the same bridge folder and refuse to run together.
- Flat (desktop) mode is what has been tested. VR has not.
- The in-game `F1` connection panel and the `ap_connect` console command belong to the standalone client. With the launcher client, connect
  in the Archipelago window.

## Your saves

- Archipelago plays on its own files in `%LOCALAPPDATA%\freddys\Saved\SaveGames\`, **one per multiworld and slot**: `Playerarchi_<seed>_<slot>.sav`. Your normal `Player00.sav` is never modified.
- The first time you connect to a **new** multiworld, a fresh file is created for it. The saves of your other multiworlds are left exactly as they are, so you can
  go back to an older room and find your progress again. Reconnecting to the same room resumes where you were. Delete the files of rooms you no longer play by hand.
- Multiworlds you started with an older version keep using `Playerarchi.sav` (their file, not renamed, not archived).
- The client tells the mod which file to use at every connect. Start the client and connect **before** you start the game, and restart the game when you switch to another multiworld.
- If the client cannot start its bridge (for example a second client window is open: `/disconnect` does not release it, close its window), it says so in its window and
  **refuses to connect**. Before, it joined the room silently and the game kept using the previous session's save.
- Each seed starts from a clean state: tapes, coins, prizes and hub progress are reset in the new file. Starting a new seed while your
  normal save is a *completed* one is verified by tests but not yet by a full in-game run; if tapes or hub items are missing, please report it.

## Playing the normal game (turning the mod off)

While the mod is installed it always uses the Archipelago save (the file of the last session, `Playerarchi_<seed>_<slot>.sav`), even when no client is running, and it keeps the last session's items. To play the
unmodified game on your normal save (`Player00.sav`), turn the mod off. Both ways are read when the game starts, so **restart the game** after changing them.

- **Option 1, a line in the mod's config (recommended).** Open `...\Win64\Mods\FNAFHWArchipelago\config.lua` and add one line inside the braces:

  ```lua
  archipelago_enabled = false,
  ```

  The mod then does nothing: nothing is hooked, no checks are sent, the save is not redirected. The UE4SS log says `archipelago_enabled = false in config.lua: the mod is OFF`.
  Remove the line (or set it to `true`) to play Archipelago again.
- **Option 2, mods.txt.** In `...\Win64\Mods\mods.txt` change `FNAFHWArchipelago : 1` to `FNAFHWArchipelago : 0` (make sure no other line for it says `1`, and that the mod folder has no `enabled.txt`, which UE4SS also treats as "on").

Notes:

- **Updating turns the mod back on.** `install-mod.ps1` rewrites `config.lua` and adds `FNAFHWArchipelago : 1` to `mods.txt` when it is missing, so redo your choice after an update.
- There is no automatic switch when the client is closed: the mod cannot tell a closed client from a running one, and play on the normal save would not count for the room.
  Start the client and connect first, then the game, as in the steps above.
- To go back to Archipelago, remove the line, start the client, connect, then start the game. Your Archipelago save and its progress were not touched.

## Troubleshooting

| Message / symptom | Meaning and fix |
| :--- | :--- |
| Installer: *UE4SS … NOT found* | Do step 1, then run the installer again. |
| Client: *could not find the bridge folder* | Run `install-mod.ps1` (it writes the folder into the mod's `config.lua`), or set the environment variable `FNAFHW_BRIDGE_DIR`. |
| Client: *Another AP bridge client is already running* | Close the other client (launcher client or standalone), then start again. |
| Connected, but nothing happens in game (or the game shows your normal save) | Check that the mod loads: open `...\Win64\UE4SS.log` (next to the game you start from Steam) and search for `FNAFHW`. A working start shows `Starting Lua mod 'FNAFHWArchipelago'` and `[FNAFHW AP]` lines. No hit at all means UE4SS did not find the mod, and it prints no error for that: check that `...\Win64\Mods\FNAFHWArchipelago\Scripts\main.lua` exists (not one folder deeper), that `Mods\mods.txt` of **that same game folder** has `FNAFHWArchipelago : 1` on its own line, and that you did not install into another copy of the game (for example an old one on another drive). *(The causes are HYPOTHESIS until reported cases confirm them.)* |
| The game crashes (closes) a few seconds after start | The game has its own launch crash that comes and goes: start it again. |
| The game crashes when you enter the hub (or later) | Close everything and copy, **before starting the game again**: `...\Win64\UE4SS.log` and the newest folder in `%LOCALAPPDATA%\freddys\Saved\Crashes`. Send both in an issue. To see whether the mod is involved, try once with `archipelago_enabled = false,` in `config.lua` (see above). |
| A level is locked although you have its item | The menu only re-asks when the hub is rebuilt: go back to the main menu and enter the hub again. |
| *Connection refused* | Wrong slot name or password, or the room uses a different game/world version. |

Client logs are in `C:\ProgramData\Archipelago\logs\FNAFHWClient_*.txt`.

## Uninstall

Delete the folder `...\Win64\Mods\FNAFHWArchipelago`, remove the `FNAFHWArchipelago : 1` line from `Mods\mods.txt`, and delete
`fnaf_help_wanted.apworld` from `custom_worlds`. Your saves are untouched.
