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
  | `test_location_groups.py` | The three group toggles (`randomize_prizes`, `randomize_faz_tokens`, `randomize_glitch_tapes`): locations, ids, pool size and filler (Faz Token, or Faz Coupon with the tokens off) for all 8 combinations, the goals' tape / token requirements, the options / slot_data / template read statically. |
  | `test_location_groups_client.py` | The real `BridgeCore`: a check of a group that is off is never sent, queued or stored (mod checks, save poll, pending, resumed session), a packet without `missing_locations` filters nothing, the `RANDOMIZED_GROUPS` line, `total_count` in the status file. |
  | `test_location_groups_generator.py` | The real `ArchipelagoGenerate.exe` (full runs, built from the working tree): all 8 combinations generate a beatable seed with exactly the expected locations and no unlock item off a level location; the tightest plans; goals that asked for tapes with tapes off; `exclude_locations` naming a location that does not exist. Skipped without an Archipelago install (`ARCHIPELAGO_DIR`, default `C:\ProgramData\Archipelago`). |
  | `test_session_saves.py` | One save file per multiworld on the real core and the real save reader (synthetic template, isolated LOCALAPPDATA): names, other sessions' saves untouched, going back to an older room, sessions made before keep `Playerarchi.sav`, a deleted save, the `SAVE_SLOT` line. |
  | `test_lua_save_slot.py` | The mod side in `lupa`: the `SAVE_SLOT` line, the slot enforced and loaded once, switching session while the game runs, unsafe names refused, the save hooks keep the current slot. |
  | `test_lua_groups.py` | The mod side in `lupa`: the `RANDOMIZED_GROUPS` line, the tape count and the TV count going vanilla and coming back (new session, debug override), the connection panel's total. |
  | `test_lua_logic.py` | The mod's Lua logic run in a real Lua interpreter (`lupa`) with the game's functions stubbed: `death_link.lua` (decisions, the registered hook, the gift box rule and its `DEATH_LINK_GIFT_BOX` line, the console experiment commands), `level_gate.lua`, `item_sync.lua`, `game_thread.lua` (game-thread timers, cached game instance, diagnostics), `derived_counters.lua` (the tape count follows the items), the inbox replay collapse in `bridge_io.lua`, and the crash fixes in `exact_hooks.lua` (no prize id decoded, no `GetName`). Skipped without `lupa`. |
  | `test_tape_count_flow.py` | The tape count end to end: the real client core writes the real inbox, the real Lua modules (`bridge_io`, `item_sync`, `derived_counters`, `exact_hooks`) read it in `lupa`. Several items in a row, reconnect, game and client restarts, a new seed at 0 (including the save generator on a completed save), a shorter server list, a gap in the list, tape checks next to the count, and a 300-step random session that must never disagree with the server's list. Skipped without `lupa`. |
  | `test_mod_switch.py` | The real `main.lua` run from a temporary mod folder: `archipelago_enabled = false` in `config.lua` leaves nothing hooked, no timers, no commands and no bridge files; a missing key, `true` or any other value keeps the mod on; the line is in `config.lua.example` and the install guide. Skipped without `lupa`. |
  | `test_crash_report.py` | `scripts/crash_report.py` on synthetic minidumps (nothing from a real run). |
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

### Tape count (`derived_counters.lua`): offline versus in game

Covered offline (`tests/test_tape_count_flow.py`, `TestDerivedCounters` in `test_lua_logic.py`, `test_clean_save.py`): the number the `GetGlitchCount` hook returns follows the Glitch Tape items of the server's list
for several items in a row, a dropped connection, a reconnect, a game restart (with and without the client, with and without the acknowledgement having reached the client), a client restart, a new seed (0, nothing from
the old seed, the generated save holds no tapes, the normal save is not touched), a room reset, a gap in the list, and a random 300-step mix of all of them; tape checks are sent once whatever the count.
Known property recorded by a test: a connect starts from an empty snapshot, so the count reads 0 (not the old value) between the `RECEIVED_SNAPSHOT` line and the server's list.

**Not coverable offline** (UNVERIFIED until the user has seen it): what the tape room draws for a count N (which tapes, whether the save's tapes matter), whether the room re-reads the count while it is open,
whether `GetGlitchCount` is also called inside levels (it was only seen in the tape area), and every hook-level fact (the hook returning the value is VERIFIED once, with a forced value and with one real item).
Useful in game: `ap_counter_status` (`items=` is what the server's list gives, `effective=` what the hook returns, `calls=` how many times the game asked, `forced=nil` must hold), `ap_items_status` (`applied=N of N`),
and the log line `[GAME] tapes observed (...): extra_args=0 vanilla=nil -> N (returned from the callback)`, printed once per distinct outcome.

## World / generator check (outside unittest)

The Archipelago modules are not importable in the dev venv, so the world glue (`__init__.py`, `rules.py`) is verified by the
real generator: install `dist/fnaf_help_wanted.apworld` into `C:\ProgramData\Archipelago\custom_worlds`, put one yaml in an
empty folder and run `ArchipelagoGenerate.exe --player_files_path <dir> --outputpath <dir>` (**never add `--skip_output` for a beatability check**: it
skips it, see below). The `slot_data` and precollected items can be read back from the `.archipelago` file inside the zip
(zlib-compressed pickle after one version byte). Verified 2026-10-04 for per_section grouped/separate and per_level.

Side effect to know: `test_packaging.py` runs `build-release.ps1`, which rebuilds `dist\fnaf_help_wanted.apworld` from the working tree on every
run (only the zip goes to the test's temp folder). Do not upload `dist\*.apworld` after a test run as if it were an older release build.

**Location group toggles** (2026-10-10): `py scripts/generator_check.py --groups on,off,prizes,faz_tokens,tapes,prizes+faz_tokens,prizes+tapes,faz_tokens+tapes` runs every goal x unlock mode x section x seed for each combination
(`on` = everything randomized, `off` = nothing, `a+b` = those groups randomized) and, besides beatability and the unlock-item rule, compares the spoiler with `data.region_locations(...)`: no location of a group that is off, every location of a group that is on, the right total.
Mutation check of the new code: 33 mutants (each toggle ignored, items kept in the pool, unfiltered 100 % list, requirement kept, client filter removed or inverted, pending not filtered, line not written / inverted / not routed, vanilla switch removed, panel total ignored), all killed.
One save per multiworld and the "no bridge" refusal: 37 more mutants (name shared / not sanitized, slot not set, stored slot ignored / unsafe stored slot trusted, line not written or routed, mod ignoring or not validating the name, the save hooks resetting it, the client connecting or not disconnecting without a bridge, ...), all killed.
A first mutant run also showed that an unfiltered 100 % list is a real generator error (`KeyError: 'Collect Prize Counter Intro Tape'`), not only a theoretical one.

Full-run sweep of 2026-10-10 (all 6 goals x the 3 unlock modes x sections `fnaf_1` and `night_terrors` x seeds 1, 2 x the 8 toggle combinations = 576 runs, `accessibility: full`): **0 spoiler/location mismatches, 0 misplaced unlock items**, and
`complete_all_minigames_nights`, `glitchtrap_ending_die` and `glitchtrap_ending_survive` generated in all 96 runs each (the 12 runs of every combination). `complete_all_minigames_nights_hard_mode` still fails everywhere (License not progression, unchanged).
`hundred_percent` and `token_tape_quota` still fail with the Faz Tokens randomized, as before (Faz Token not progression), **but generate once `randomize_faz_tokens` is false**: their failing requirement (`Faz Token` copies) is then no longer in the logic.
That is a side effect of "a group that is off is not asked for", not a fix of those goals; the fix of item 3 in HANDOVER is still open. The tightest plans (per_level, all groups off: 49 slots for 43 items + 6 filler; per_section separate, all off) generate.

Generator check done on 2026-10-05 after dropping the undetectable prizes: the apworld in a trimmed copy of the Archipelago install (never the
installed `custom_worlds`), six yaml variants, `--skip_output`: all fill 152 items for 153 locations. **That run proved less than it said:** with `--skip_output` the generator
does not check that the game can be beaten. A deliberately unbeatable copy of the world (an impossible rule on the goal) also "passed" that way and only failed
(`FillError: Game appears as unbeatable`, no zip) in a full run. Use a full run, in a scratch copy of Archipelago (`ArchipelagoGenerate.exe`, `lib`, `data`, `share`, the dlls and `host.yaml`; the built apworld alone in `custom_worlds`;
stdin closed, the exe waits for Enter on a failure), and count a run as good only when the zip is written. The line `Could not access required locations for accessibility check. Missing: [...]` is a **warning** that lists locations the logic cannot reach.

Full-run sweep of 2026-10-05 (6 goals x per_section grouped / separate x per_level, `accessibility` full on seed 1 and minimal on seeds 2-5, deterministic; run before the `nightmare_logic` option was removed, with it off, which is what the world does now):

| Goal | Generates |
| :--- | :--- |
| `complete_all_minigames_nights` | yes |
| `glitchtrap_ending_die`, `glitchtrap_ending_survive` | yes (they failed only with the since-removed `nightmare_logic` on) |
| `complete_all_minigames_nights_hard_mode` | **never** |
| `hundred_percent`, `token_tape_quota` | **never** |

Cause (classification, unchanged since the first commit): the goal rules call `state.has("Nightmare Mode License")` and `state.has("Faz Token", n)`, but those items are `useful` / filler, and Archipelago only counts progression items in `state.has`, so the goal location can never be reached.
These are loud generation failures, not stuck players. The shipped template (goal `complete_all_minigames_nights`) generates.

**Unlock items on level locations only** (rule added 2026-10-05, `levels.may_hold_unlock_item`, applied in `rules.py`): before it, **27 of 27** seeds put at least one unlock item (about 14 per seed) on a tape, token, prize, trophy or blackjack location,
where the real game may need the very level it unlocks. After it: **297 of 297** runs generated and 0 misplaced (default start, 108 runs on 12 seeds; each of the 7 starting sections, 189 runs; per_section grouped / separate and per_level;
goals `complete_all_minigames_nights`, `glitchtrap_ending_die`, `glitchtrap_ending_survive`). Repeat it with `py scripts/generator_check.py` (run the tests first, they rebuild the apworld; it only reads your Archipelago install and checks every seed's spoiler).
What this does NOT prove: that the tape / token / prize locations themselves are reachable in the real game (they may need levels; the unlock items are simply never placed there), or the Pizza Party unlock condition.

## Fixtures: the suite is hermetic

No test needs a private save any more. `tests/gvas_fixtures.py` builds synthetic GVAS saves (a fresh `starter_player00()`, a
`completed_template()` with tapes, coins, hub audio and eaten objects) from the layout the save generator itself walks, and
`isolate_localappdata()` installs the starter as `Player00.sav` in the temp save folder. Previously the save helpers fell back to
`Player00.sav` / `Playerarchi.sav` in the **current directory**, so the suite silently read the developer's private, gitignored files
(and failed or skipped without them). Verified on 2026-10-04: all 135 tests pass with those files hidden, from another working
directory, and with them present. The only optional extra is `TestCleanRealCompletedSave`, which also runs on a real `100percent.sav`
when one is in the repo root (skipped otherwise).
