# Testing

## Python tests

```text
.venv/Scripts/python.exe -m unittest discover -s tests
```

- Run them from the repo root. They cover the client, session persistence, the bridge lines and the save reader.
- Every test class that connects a client must call `isolate_localappdata(self, self.temp_dir)`
  (`tests/localappdata_isolation.py`). `APBridgeClient._on_connected` archives and recreates
  `%LOCALAPPDATA%\freddys\Saved\SaveGames\Playerarchi.sav`, so an unisolated test can reset a developer's real save.
  To prove isolation, hash `Player00.sav` / `Playerarchi.sav` before and after a full run.
- Test files:

  | File | Covers |
  | :--- | :--- |
  | `test_bridge_core.py` | The transport-free `BridgeCore`: connect/resume, commands, items, save polling, DeathLink, `InstanceLock`, the standalone entry point. Fake save reader, no sockets. |
  | `test_launcher_client.py` | The Archipelago launcher client on the real vendored layout, with stubbed framework modules: bridge discovery, session safety, packets, watcher, arguments. |
  | `test_gate_table.py`, `test_item_sync.py` | Gate table and item snapshot forwarding, applied-count persistence, clamping, acknowledgements. |
  | `test_scenarios.py`, `test_full_validation.py`, `test_server_authority.py` | Sessions, restarts, new seeds, server authority, save isolation. |
  | `test_clean_save.py` | Clean `Playerarchi.sav` generation from a completed template (also on a real `100percent.sav` when one is in the repo root). |
  | `test_world_gating.py` | Item codes, the level table against the generated row table, every option combination, rules as data, the `slot_data` round trip. |
  | `test_lua_logic.py` | The mod's Lua logic run in a real Lua interpreter (`lupa`) with the game's functions stubbed: `death_link.lua` (decisions, the registered hook, the console experiment commands), `level_gate.lua`, `item_sync.lua`. Skipped without `lupa`. |
  | `test_installer.py` | `install-mod.ps1` against a fake game and a fake Archipelago (Windows only). |
  | `test_packaging.py` | The manifest, the yaml template kept in sync with the options, the release zip (contents, nothing private, standard zip entry names). |

## What is not covered by automated tests

`test_lua_logic.py` runs the mod's *pure* Lua logic (decisions, parsing, ordering) with the game stubbed. It cannot tell whether a hook fires,
what a game function does, or how the real UE4SS behaves: those are verified **in game** only. The procedures that have been used:

- **Inject a protocol line** into the live inbox (UTF-8, from Git Bash), e.g.
  `printf 'GATE_TABLE 4=FNAF1_NIGHT1,5=FNAF1_NIGHT2\n' >> <bridge>/ap_inbox.txt`, then rebuild the hub and read `UE4SS.log`
  (`[SESSION]`, `[GAME]`, `[ARCHI]`, `[SYNC]` lines).
- **Send a real check** through the bridge: `printf 'LOCATION_CHECK <id>\n' >> <bridge>/ap_outbox.txt` (affects the real room).
- Use the console: `ap_gate_status`, `ap_items_status`, `ap_gate_grant`, `ap_gate_revoke`.
- **Restart check**: restart both the game and the client and confirm state (`applied=N of N`, no re-applied items).

Restart the Python client after changing `ap_client/main.py`; `launch-*.bat` re-syncs the Lua files.

## World / generator check (outside unittest)

The Archipelago modules are not importable in the dev venv, so the world glue (`__init__.py`, `rules.py`) is verified by the
real generator: install `dist/fnaf_help_wanted.apworld` into `C:\ProgramData\Archipelago\custom_worlds`, put one yaml in an
empty folder and run `ArchipelagoGenerate.exe --player_files_path <dir> --outputpath <dir>` (add `--skip_output` for a fill-only
check). The `slot_data` and precollected items can be read back from the `.archipelago` file inside the zip
(zlib-compressed pickle after one version byte). Verified 2026-10-04 for per_section grouped/separate and per_level.

## Fixtures: the suite is hermetic

No test needs a private save any more. `tests/gvas_fixtures.py` builds synthetic GVAS saves (a fresh `starter_player00()`, a
`completed_template()` with tapes, coins, hub audio and eaten objects) from the layout the save generator itself walks, and
`isolate_localappdata()` installs the starter as `Player00.sav` in the temp save folder. Previously the save helpers fell back to
`Player00.sav` / `Playerarchi.sav` in the **current directory**, so the suite silently read the developer's private, gitignored files
(and failed or skipped without them). Verified on 2026-10-04: all 135 tests pass with those files hidden, from another working
directory, and with them present. The only optional extra is `TestCleanRealCompletedSave`, which also runs on a real `100percent.sav`
when one is in the repo root (skipped otherwise).
