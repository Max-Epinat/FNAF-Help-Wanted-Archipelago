# Launcher client (runs inside the Archipelago launcher)

`fnaf_help_wanted/client.py` is a normal Archipelago client (`CommonContext`, Kivy window, like the installed FNaF World one). It shows up
as **"FNAF Help Wanted Client"** in the launcher (Clients) once the rebuilt `fnaf_help_wanted.apworld` is in `custom_worlds`. It drives the
same transport-free `BridgeCore` as the standalone client (`ap_client/main.py`) and talks to the game mod through the same bridge files,
so the mod and the [bridge protocol](bridge-protocol.md) are unchanged.

## Using it

1. Install the game mod once (`scripts/install-mod.ps1`), which writes the bridge folder into the mod's `config.lua`.
2. Start **FNAF Help Wanted Client** from the launcher, type the server address in the window, enter the slot name, start the game.
   Command line (testing): `ArchipelagoLauncher.exe "FNAF Help Wanted Client" -- --connect archipelago.gg:PORT --name HWtest`.
3. `/bridge` prints the bridge folder, the session and the counters.

Use **either** this client **or** the standalone one, never both: they share `<bridge>/ap_client.lock` (the second one refuses to start and
says why). The standalone client stays available (`scripts/start-client.bat`, `scripts/launch-game.bat -Client Standalone`, developer helpers). `scripts/launch-game.bat` itself now installs the current apworld and opens the Archipelago launcher on "FNAF Help Wanted Client" (`-Client Launcher`, the default; `-ArchipelagoDir` if Archipelago is not in `C:\ProgramData\Archipelago`).

## How it finds the bridge folder

`FNAFHW_BRIDGE_DIR` if set, otherwise the `bridge_dir` written in the installed mod's
`...\freddys\Binaries\Win64\Mods\FNAFHWArchipelago\config.lua` (Steam default paths, every Steam library, or `FNAFHW_GAME_ROOT`). The mod is the
single source of truth for where it reads and writes. If nothing is found the client says so and does not start a session.

## Differences from the standalone client

- Connection commands written by the game (`CONNECT`, `DISCONNECT`, `SHOW_UI`, `SAVE_PROFILE`, so the in-game F1 connection panel and
  `ap_connect`) are ignored: Archipelago owns the connection here.
- A live check and a save poll in the same pass are merged into one `LocationChecks` packet.
- The session id is **seed + slot** and the seed comes from the server's `RoomInfo`. If it is missing the client refuses to start a session
  (a wrong id would start a fresh save for a wrong session; see the incident below).
- **No bridge, no connection.** If the bridge cannot start (the folder is not found, or another client holds the lock: `/disconnect` does not release it, close its window), the client logs
  `NOT connecting. <reason>` when you connect, closes the connection and does not authenticate, again at every attempt. (2026-10-10: a second client window used to join the room with no bridge,
  wrote nothing, and the game replayed the previous session and its save. Disconnecting through `ctx.disconnect()` is the framework's own call, not seen live: **UNVERIFIED**.)
- `/bridge` also prints the save file of the session.

## Build

`scripts/build-apworld.ps1` copies `ap_client/bridge_core.py` and `ap_client/save_reader.py` into the package (list:
`scripts/vendored_client_files.json`), so there is one source for that logic. An apworld is a zip: code inside cannot read sibling files
by path, which is why `save_reader.load_prize_checks()` imports `data.py` first. `fnaf_help_wanted/__init__.py` registers the launcher
component (guarded) and imports `client.py` lazily, so generation never loads the client.

## Status

- **VERIFIED in the real launcher (2026-10-04, AP 0.6.7)**: the component is listed and starts; it finds the bridge folder from the mod's
  config; the single-instance lock refuses a second client; it connects and authenticates as `HWtest`; it resumes the real session with the
  correct baseline and sends the gate table, gate items, confirmed checks and the item snapshot, with `Player00.sav` / `Playerarchi.sav`
  byte-identical afterwards.
- **VERIFIED by tests** (`tests/test_launcher_client.py`, against stubbed framework modules, using the real vendored layout): bridge discovery,
  lock, packets, outbox watcher, merge of checks, argument handling, session safety.
- **VERIFIED live with the game running (2026-10-04, same day)**: through this client, two Faz Token pickups (live hook), beating Parts and Service -
  Bonnie and its Butter for One prize reward (save poll) all reached the server and were confirmed (session 8 checked, 0 pending); the game's
  `ITEMS_APPLIED` acknowledgements were persisted and echoed (`applied_item_count` 7 of 7); `Player00.sav` content unchanged.
- **NOT verified live**: DeathLink, the standalone-style connection commands (ignored by design), and the kvui window beyond showing the log.
  Which launcher list the component appears in was not seen by me (registered as a client component).

## Incident (2026-10-04) and the rule it produced

The first live run used `ctx.seed_name`, which is not set when `Connected` arrives, so the core fell back to the id `unknown_seed_HWtest`,
treated it as a new seed, archived the player's `Playerarchi.sav` and created a fresh one. Nothing was lost (the archive was copied back,
byte-identical, hash checked), but the lesson is encoded in tests: the seed comes from `RoomInfo`, and without one nothing is started and no
save is touched. Back up saves and session files before any live test of a new client.
