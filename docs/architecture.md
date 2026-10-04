# Architecture

## Components

```text
 Archipelago server
        ▲  websocket (Archipelago protocol)
        │
 ┌──────┴───────────────────────────────┐
 │ client                               │   launcher client:   fnaf_help_wanted/client.py   (CommonContext, Kivy window)
 │  └─ BridgeCore  (ap_client/           │   standalone client: ap_client/main.py            (websockets + tkinter window)
 │     bridge_core.py, transport-free)   │   both drive the same BridgeCore + save_reader.py
 └──────┬───────────────────────────────┘
        │ bridge folder: ap_inbox.txt (client → mod), ap_outbox.txt (mod → client), state / session files
        ▼
 UE4SS Lua mod (ue4ss_mod/FNAFHWArchipelago) inside the game
```

| Part | Responsibility |
| :--- | :--- |
| **apworld** (`fnaf_help_wanted/`) | Items, locations, options, rules (`levels.py` builds the unlock plan), `slot_data`. Also contains the launcher client. |
| **BridgeCore** (`ap_client/bridge_core.py`) | Everything that does not depend on a socket: session handling, item sync, location checks, save polling, DeathLink forwarding, the single-instance lock, bridge-folder discovery. Methods *return* the packets to send. |
| **save_reader** (`ap_client/save_reader.py`) | Reads `Playerarchi.sav` (GVAS), maps it to locations, and creates a clean AP save from `Player00.sav`. Read-only on the normal save. |
| **Clients** | Thin transports around `BridgeCore`. The launcher client is vendored with `bridge_core.py` and `save_reader.py` into the apworld at build time (an apworld is a zip). |
| **Mod** | Hooks game functions (checks), enforces level unlocks, applies item effects, shows an optional connection panel. Everything runs through `Scripts/main.lua`. |

## Sessions and saves

- A **session** is `seed + slot` (the seed name comes from the server's `RoomInfo`; a client never guesses it).
- Archipelago plays on its own save, `Playerarchi.sav`; the mod forces the game's save slot to `Playerarchi`. `Player00.sav` is only ever read, as a template.
- A **new** session archives the previous `Playerarchi.sav` (`.sav.bak`) and creates a clean one: levels, prizes, tapes (collected and listened),
  coins, hub audio and eaten objects reset. A **resumed** session keeps the file and re-snapshots a *baseline* of what it already contains, so nothing
  already earned is sent as new.
- The **server is authoritative** for checked locations; local pending checks survive until the server confirms them.

## How checks reach the server

| Check | Source |
| :--- | :--- |
| 40 levels, Pizza Party | `BP_FNAF_GameInstance_C:SaveLevelVictory(row)`, row from the game's `LevelInfoTable`; also read from the save by the client |
| 30 Faz Tokens | `UnlockCoin` and `GrabbableToken_C:AttemptGrab` hooks |
| 16 Glitch Tapes | `SetGlitchListenedTo` hook |
| 81 prizes | The client's save poll (the mod's own prize poll cannot decode prize ids and is intentionally inert) |

The client also polls `Playerarchi.sav` (at most once a second, when it changed), so a check missed by a hook is still found. A live check and a
poll in the same pass are merged into one `LocationChecks` packet.

## How items reach the game

The server's **full item list** is the source of truth, not individual `ITEM` lines. The client sends the whole list as `RECEIVED_SNAPSHOT` at every
connect, and the mod derives state from it:

| Item | Effect |
| :--- | :--- |
| Section items, hard-section items, per-level items | Authorize a level gate (`level_gate.lua`). Tested in game. |
| Faz Token | The displayed coin count equals the number of Faz Token items (`faz_tokens.lua`). Tested in game. |
| Nightmare Mode License | Sets nightmare mode (`exact_hooks.lua`); effect not verified in game. |
| Glitch Tape, Prize Counter Key, traps | No in-game effect yet; used by the logic only. |

One-shot effects are applied exactly once per session: the client persists `applied_item_count`, the mod applies items beyond it in order and
acknowledges them (`ITEMS_APPLIED`). Details: [bridge-protocol.md](bridge-protocol.md).

## Level unlocking

The mod hooks `BP_FNAF_GameInstance_C:IsLevelUnlocked`. While a session is active, a gated level is unlocked exactly when its gate is authorized
by a received item, whatever the game's own answer was. See [level-gating.md](level-gating.md).

## The mod

| File | Purpose |
| :--- | :--- |
| `Scripts/main.lua` | Loads everything, wires the bridge callbacks. |
| `lib/bridge_io.lua` | Reads the inbox, writes the outbox. |
| `lib/exact_hooks.lua`, `lib/collectible_hooks.lua`, `lib/check_awards.lua` | Event hooks that produce location checks. |
| `lib/level_gate.lua`, `lib/item_sync.lua`, `lib/faz_tokens.lua` | Level unlocks, exactly-once item effects, the coin count. |
| `lib/death_link.lua` | DeathLink: sends a death when `LevelDefeat` fires; an incoming death makes the player lose the level they are in (levels only, never replayed history). Console: `ap_dl_status`, `ap_dl_kill`, experiment commands `ap_dl_*`. See [TODO](TODO.md). |
| `lib/research_tools.lua` | Opt-in, read-only console tools for finding things in the game: `ap_class <class path>`, `ap_instances <ClassName>`, `ap_hookclass <class path>` / `ap_hookfn <function path>` (log only), `ap_watch <word>` (heavy), `ap_watch_clear`, `ap_watch_status`, and the heavy `ap_scan <word>` (froze the game in the hub: avoid). |
| `lib/connection_ui.lua`, `lib/console_commands.lua` | `F1` connection panel (standalone client) and console commands. |
| `lib/locations_data.lua`, `locations.json` | Generated from the world data by `scripts/generate_locations_*.py`. |

Console commands (UE4SS console): `ap_status`, `ap_items_status`, `ap_gate_status`, `ap_gate_grant|revoke <GATE>` (debug), `ap_coin_status`,
`ap_coin_force <n>|off`, `ap_check_id <id>`, `ap_check_name <name>`, `ap_goal`, `ap_say`, `ap_sync`, `ap_connect`, `ap_disconnect`, `ap_menu`/`ap_ui`,
and a few dump/scan helpers for research.

## Clients compared

| | Launcher client | Standalone client |
| :--- | :--- | :--- |
| Runs in | The Archipelago launcher | A Python process with a tkinter window |
| Connection | Archipelago's own UI | Its window, or the in-game `F1` panel / `ap_connect` |
| Dependencies | None (Archipelago's own) | `websockets` |
| Bridge folder | Found from the mod's `config.lua` (or `FNAFHW_BRIDGE_DIR`) | The same |

Only one may run at a time (`bridge/ap_client.lock`).

## Regenerating data

`locations.json` (mod) and `locations_data.lua` come from the world data: `python scripts/generate_locations_json.py` then
`python scripts/generate_locations_lua.py`. Both are reproducible; the committed files are exactly their output.
