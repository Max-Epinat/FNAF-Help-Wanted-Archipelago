# FNAFHWArchipelago (UE4SS mod)

The in-game half of the FNAF Help Wanted × Archipelago integration. It hooks the game's functions to detect checks, enforces which levels are
unlocked, applies received items, and exchanges short text lines with the Archipelago client through the **bridge folder**
(`ap_inbox.txt`, `ap_outbox.txt`).

**Players:** do not copy this folder by hand. Run `install-mod.ps1` from the release package (see `docs/installation.md`); it checks UE4SS,
installs the mod, writes `config.lua` and creates the bridge folder.

## Files

| Path | Purpose |
| :--- | :--- |
| `Scripts/main.lua` | Entry point: loads the libraries and wires the bridge callbacks. |
| `Scripts/lib/` | Bridge I/O, game-thread timers and diagnostics (`game_thread.lua`), event hooks, level gate, item sync, Faz Token count, DeathLink, connection panel, console commands. |
| `locations.json`, `Scripts/lib/locations_data.lua` | Generated from the world data (`scripts/generate_locations_*.py`). Do not edit by hand. |
| `config.lua.example` | Shape of `config.lua`. The real `config.lua` is machine-specific and written by the installer. |

## Configuration

`config.lua` sets `bridge_dir` (where the mod and the client meet), the in-game panel key (`F1`) and debug logging. The Archipelago clients read the same
file to find the bridge folder, so the mod stays the single source of truth.

`archipelago_enabled = false` in `config.lua` turns the whole mod off (vanilla game, normal save); see "Playing the normal game" in `docs/installation.md`.

See `docs/architecture.md` for how the pieces fit together.
