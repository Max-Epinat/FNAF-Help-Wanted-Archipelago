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

Unpack the release zip, then run `install-mod.ps1` (right-click → *Run with PowerShell*, or from a terminal:
`powershell -ExecutionPolicy Bypass -File install-mod.ps1`).

It will:

- find the game (or use `-GameRoot "<folder that contains freddys>"`),
- check that UE4SS is installed and stop with a link if it is not,
- install the mod into `...\Win64\Mods\FNAFHWArchipelago`, with its **bridge folder** inside it,
- enable the mod in `Mods\mods.txt`,
- copy `fnaf_help_wanted.apworld` into `C:\ProgramData\Archipelago\custom_worlds` (use `-ArchipelagoDir` if yours is elsewhere, or
  `-SkipApworld`; without Archipelago, double-click the `.apworld` file or copy it into `custom_worlds` by hand).

`-CheckOnly` reports what it finds and changes nothing. Running it again is safe (it is also how you update).

## 3. Set your options and get a room

1. Copy `templates/Five Nights at Freddy's Help Wanted.yaml` into your Archipelago `Players` folder and edit it (the comments explain each option).
   The launcher's *Generate Template Options* button also produces an up-to-date template.
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

- Archipelago plays on its own file, `%LOCALAPPDATA%\freddys\Saved\SaveGames\Playerarchi.sav`. Your normal `Player00.sav` is never modified.
- The first time you connect to a **new** seed, a fresh `Playerarchi.sav` is created and the previous one is kept next to it as
  `Playerarchi_<number>.sav.bak`. Reconnecting to the same seed resumes where you were.
- Each seed starts from a clean state: tapes, coins, prizes and hub progress are reset in the new file. Starting a new seed while your
  normal save is a *completed* one is verified by tests but not yet by a full in-game run; if tapes or hub items are missing, please report it.

## Troubleshooting

| Message / symptom | Meaning and fix |
| :--- | :--- |
| Installer: *UE4SS … NOT found* | Do step 1, then run the installer again. |
| Client: *could not find the bridge folder* | Run `install-mod.ps1` (it writes the folder into the mod's `config.lua`), or set the environment variable `FNAFHW_BRIDGE_DIR`. |
| Client: *Another AP bridge client is already running* | Close the other client (launcher client or standalone), then start again. |
| Connected, but nothing happens in game | Check that the mod loads: open `...\Win64\UE4SS.log` and look for `[FNAFHW AP]` lines. Check `Mods\mods.txt` contains `FNAFHWArchipelago : 1`. |
| A level is locked although you have its item | The menu only re-asks when the hub is rebuilt: go back to the main menu and enter the hub again. |
| *Connection refused* | Wrong slot name or password, or the room uses a different game/world version. |

Client logs are in `C:\ProgramData\Archipelago\logs\FNAFHWClient_*.txt`.

## Uninstall

Delete the folder `...\Win64\Mods\FNAFHWArchipelago`, remove the `FNAFHWArchipelago : 1` line from `Mods\mods.txt`, and delete
`fnaf_help_wanted.apworld` from `custom_worlds`. Your saves are untouched.
