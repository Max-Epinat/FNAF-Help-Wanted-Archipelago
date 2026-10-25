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
  | `test_location_groups_generator.py` | The real `ArchipelagoGenerate.exe` (full runs, built from the working tree): all 8 combinations generate a beatable seed with exactly the expected locations that also passes the replay with the real rules; the tightest plans; goals that asked for tapes with tapes off; `exclude_locations` naming a location that does not exist. Skipped without an Archipelago install (`ARCHIPELAGO_DIR`, default `C:\ProgramData\Archipelago`). |
  | `test_goal_generation.py` | Every goal through the real generator, one test per goal over the 8 toggle combinations (beatable, right locations, the replay with the real rules reaches every location and the goal, 30 progression Faz Tokens, the License still in the pool); the hard goal's rule (every level plus Pizza Party, no License); the harness requires every goal. Generator part skipped without an Archipelago install. |
  | `test_real_access.py` | The real access rules read from the game's files: every level's map, every tape / token pickup's map, the free and filler-only checks, the rule each one gets in every unlock mode (every level of the map), the cases of the broken room (tape 13 = Circus Baby, the Ennard pickups), the never-sent checks and unused goals not created (146 / 145 / 43 locations), the stopgap gone; and a real-generator test with **two FNAF players in one multiworld** (6 seeds) that must pass the replay for both players. |
  | `test_faz_token_progression.py` | As many base Faz Tokens are progression (skip balancing) as the goal needs (0, the quota, 30), the others and the spare-slot ones filler, read back from real seeds (`.archipelago` flags); the token goals with the tokens on, `required_faz_tokens: 30`, `start_inventory_from_pool`. |
  | `test_session_saves.py` | One save file per multiworld on the real core and the real save reader (synthetic template, isolated LOCALAPPDATA): names, other sessions' saves untouched, going back to an older room, sessions made before keep `Playerarchi.sav`, a deleted save, the `SAVE_SLOT` line. |
  | `test_lua_save_slot.py` | The mod side in `lupa`: the `SAVE_SLOT` line, the slot enforced and loaded once, switching session while the game runs, unsafe names refused, the save hooks keep the current slot. |
  | `test_lua_groups.py` | The mod side in `lupa`: the `RANDOMIZED_GROUPS` line, the tape count and the TV count going vanilla and coming back (new session, debug override), the connection panel's total. |
  | `test_lua_logic.py` | The mod's Lua logic run in a real Lua interpreter (`lupa`) with the game's functions stubbed: `death_link.lua` (decisions, the registered hook, the gift box rule and its `DEATH_LINK_GIFT_BOX` line, the console experiment commands), `level_gate.lua`, `item_sync.lua`, `game_thread.lua` (game-thread timers, cached game instance, diagnostics), `derived_counters.lua` (the tape count follows the items), the inbox replay collapse in `bridge_io.lua`, and the crash fixes in `exact_hooks.lua` (no prize id decoded, no `GetName`). Skipped without `lupa`. |
  | `test_unique_tapes.py` | Unique tapes, world side: the 16 tape items (names, codes 61-76 in log order, one progression item each, the log -> check table and the maps it names), the old "Glitch Tape" gone and code 1 retired, tapes off = no tape item, the random pick of the progression tapes, the rule counting any of the 16, and the generator harness: the replay counts the 16 (progression only, not the old name) and `tape_problems` reads a seed's tape flags. |
  | `test_lua_tape_shelf.py` | `tape_shelf.lua` in `lupa` with fake shelf slots: only labelled slots are touched, logs in shelf order with no gaps, a slot already right is left alone, retries catch a late label and then stop, a new visit relabels again, nothing outside the tape room / without a session / with tapes off, the old item ignored with one line per session, and with the real `game_thread.lua` the relabel never runs inside the 5 s pause. |
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

Covered offline (`tests/test_tape_count_flow.py`, `TestDerivedCounters` in `test_lua_logic.py`, `test_clean_save.py`): the number the `GetGlitchCount` hook returns follows the tape items of the server's list (since 2026-10-26: the number of
different tape items among the 16, the retired id counts for nothing)
for several items in a row, a dropped connection, a reconnect, a game restart (with and without the client, with and without the acknowledgement having reached the client), a client restart, a new seed (0, nothing from
the old seed, the generated save holds no tapes, the normal save is not touched), a room reset, a gap in the list, and a random 300-step mix of all of them; tape checks are sent once whatever the count.
Known property recorded by a test: a connect starts from an empty snapshot, so the count reads 0 (not the old value) between the `RECEIVED_SNAPSHOT` line and the server's list.

**Not coverable offline** (UNVERIFIED until the user has seen it): what the tape room draws for a count N (which tapes, whether the save's tapes matter), whether the room re-reads the count while it is open,
whether `GetGlitchCount` is also called inside levels (it was only seen in the tape area), and every hook-level fact (the hook returning the value is VERIFIED once, with a forced value and with one real item).
Useful in game: `ap_counter_status` (`items=` is what the server's list gives, `effective=` what the hook returns, `calls=` how many times the game asked, `forced=nil` must hold), `ap_items_status` (`applied=N of N`),
and the log line `[GAME] tapes observed (...): extra_args=0 vanilla=nil -> N (returned from the callback)`, printed once per distinct outcome.

### Unique tapes (2026-10-26)

Tests first, shown failing on the old code (the new modules missing, `TestDerivedCounters` 9 of 16 failing, the wiring checks), then the code.
Mutation check: 37 mutants of the new code (shelf: unlabelled slots touched, no sorting, original numbers re-read, outside the room, the first tick acting, endless or
single pass, the visit not reset, PreConstruct / Text / LogNumber not set, tapes-off or session ignored, old logs kept, the old-item line repeated or missing, the
old item as log 1, ids off by one, exempt from the pause, bad snapshot accepted, one broken slot stopping the pass; the count: duplicates or the old id counted,
an id missing; main.lua wiring; world: tapes off keeping the items, a fixed pick, codes reversed, not progression, logs swapped, code 1 reused; harness: the old name
or filler counted, tape flags unchecked or the check not run), all killed. The first run left one survivor (the visit not reset), which exposed a weak test; a test
that uses every pass before leaving the room now kills it. The world glue (`__init__.py`, `rules.py`) is checked by the real generator (slow mutants below).
`scripts/generator_check.py` also runs `tape_problems` on every seed: each of the 16 tape items once, exactly the needed number progression, none with the tapes off.
Slow mutants (real generator): every / no tape item progression (killed by the real-seed flag check in `test_faz_token_progression.py`); the rule asking for one tape
or none (killed by the static check of the rule line only).
Full-run sweeps of 2026-10-26, `accessibility: full`: **(A)** all 6 goals x 3 unlock modes x sections `fnaf_1`, `night_terrors`, `parts_and_service` x seeds 1-3,
everything on: **162 of 162 generated, 0 problems**. **(B)** all 6 goals x 3 unlock modes x `fnaf_1`, `night_terrors` x seeds 1, 2 x the 8 toggle combinations:
**568 generated with 0 problems, 8 refused as expected** (the same 100 % / per_level / prizes off / tapes on seeds as before), `RESULT: OK`.
Negative control (the real script on a deliberately broken apworld, `token_tape_quota`): every tape item progression -> `16 progression tape items, expected 8`,
`RESULT: PROBLEM`, exit 1; no tape item progression -> `FillError: Game appears as unbeatable`, `RESULT: PROBLEM`, exit 1.

**Not coverable offline**: VR with relabelled slots, and what a real room's old `Glitch Tape` items do in game. (The relabel itself was seen working by the user in a
real room on 2026-10-26.)

**Faster relabel (2026-10-27).** `game_thread.every_in_tape_room` (the only exemption from the pause, the room name built in) and the shelf's new schedule
(0.25 s, wait 2 runs, at most 8 passes) with the per-slot rule (only slots whose label shows their own number). Tests first, shown failing (25 of 36 in
`test_lua_tape_shelf.py`), including `TestTheRealScheduler` with the real `game_thread.lua` on a whole-second clock like `os.time`: the shelf relabels
during the pause 2 runs after the room is noticed, another job is still held for the whole pause (4-5 s, unchanged), nothing runs in the hub or any other
map or without the diagnostics, and no file but `tape_shelf.lua` (handed it by `main.lua`) uses the exemption.
Mutation check: 19 mutants (scheduler: the room job on every map, held by the pause too, every job exempt, visits not counted, last map not recorded,
a wrong room name; shelf: label number not checked, a fake label for a missing one (nil or invalid object), no minimum wait, no cap, once a second,
no early stop, slots redone, logs by arrival instead of by place, a new visit not noticed, passes without a session, one broken slot stopping the pass;
main.lua handing the ordinary scheduler), all killed. The first run left one survivor (a fake label for a missing one): in every test the unlabelled
slots sat beyond the logs received, so the place rule hid it; a test with a log waiting for an unlabelled slot's place now kills it.
**Not coverable offline** (HYPOTHESIS until seen in a real room): the real delay, whether a pass during the room's own load is harmless, and the fade-in.

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
`complete_all_minigames_nights`, `glitchtrap_ending_die` and `glitchtrap_ending_survive` generated in all 96 runs each (the 12 runs of every combination). At the time the three other goals failed (fixed 2026-10-25, see "Every goal generates" below).
The tightest plans (per_level, all groups off: 49 slots for 43 items + 6 filler; per_section separate, all off) generate.

Generator check done on 2026-10-05 after dropping the undetectable prizes: the apworld in a trimmed copy of the Archipelago install (never the
installed `custom_worlds`), six yaml variants, `--skip_output`: all fill 152 items for 153 locations. **That run proved less than it said:** with `--skip_output` the generator
does not check that the game can be beaten. A deliberately unbeatable copy of the world (an impossible rule on the goal) also "passed" that way and only failed
(`FillError: Game appears as unbeatable`, no zip) in a full run. Use a full run, in a scratch copy of Archipelago (`ArchipelagoGenerate.exe`, `lib`, `data`, `share`, the dlls and `host.yaml`; the built apworld alone in `custom_worlds`;
stdin closed, the exe waits for Enter on a failure), and count a run as good only when the zip is written. The line `Could not access required locations for accessibility check. Missing: [...]` is a **warning** that lists locations the logic cannot reach.

### Every goal generates (2026-10-25)

Until 2026-10-25 three goals could never be generated (`FillError: Game appears as unbeatable`): `complete_all_minigames_nights_hard_mode` (its rule asked for the `Nightmare Mode License`, a `useful` item) and
`hundred_percent` / `token_tape_quota` with the Faz Tokens randomized (`state.has("Faz Token", n)` while every Faz Token was filler). Archipelago only counts progression items in `state.has`.
Fix: the hard goal no longer asks for the License (the user's choice: the game ends the multiworld on Pizza Party whatever the goal, and the License has no verified effect; it stays in the pool as a useful item), and the 30 base
Faz Tokens are `progression_skip_balancing` while the spare-slot Faz Tokens stay filler (`create_filler`). Both kinds are the same item and id, so the mod's TV count does not change (HYPOTHESIS until seen in a real room).
The seed file keeps only the progression bit: the server and every client see those tokens with flag 1, like a Glitch Tape. (Since the real access rules, later the same day: only as many as the goal needs, see "Count by need" below.)

`scripts/generator_check.py` now requires **every** goal (`REQUIRED_GOALS = ALL_GOALS`) and also checks, from the generated `.archipelago` file, that exactly 30 Faz Tokens are progression and every other Faz Token is plain filler (none with the tokens off).
Negative controls (2026-10-25, the real script on a deliberately broken apworld): the License put back into the hard goal gives `failed=3`, `RESULT: PROBLEM`, exit 1; the filler tokens made progression gives `120 progression Faz Tokens, expected 30`, `RESULT: PROBLEM`, exit 1.
Before the fix (same script, start section `fnaf_1`, seed 1, 3 unlock modes): the hard goal failed in every toggle combination, `hundred_percent` and `token_tape_quota` failed with the tokens on and generated with them off.

Full-run sweep of 2026-10-25 after the fix, `accessibility: full`, 954 runs, **every one generated (beatable), 0 misplaced unlock items, 0 location / token problems**: (A) all 6 goals x the 3 unlock modes x all 7 start sections x seeds 1-3, everything randomized (378 runs, 63 per goal); (B) all 6 goals x the 3 unlock modes x sections `fnaf_1` and `night_terrors` x seeds 1, 2 x the 8 toggle combinations (576 runs, 12 per goal and combination). Commands: `py scripts/generator_check.py --sections all --seeds 1,2,3` and `py scripts/generator_check.py --sections fnaf_1,night_terrors --seeds 1,2 --groups on,off,prizes,faz_tokens,tapes,prizes+faz_tokens,prizes+tapes,faz_tokens+tapes`.

| Goal | Generates (every toggle combination, every start section tried) |
| :--- | :--- |
| `complete_all_minigames_nights` | yes |
| `complete_all_minigames_nights_hard_mode` | yes (every level, hard ones included, plus Pizza Party) |
| `glitchtrap_ending_die`, `glitchtrap_ending_survive` | yes |
| `hundred_percent` | yes |
| `token_tape_quota` | yes |

Tests: `test_goal_generation.py` (one real-generator test per goal over the 8 toggle combinations, the hard goal's rule, the License kept in the pool, the harness requiring every goal), `test_faz_token_progression.py`; mutation check: 17 mutants (License back in the goal,
Pizza Party or the levels dropped from it, License progression or out of the pool, harness back to one required goal, token not progression / no skip-balancing / 29 copies, filler via `create_item`, `create_filler` not filler, harness checks disabled), all killed.

### Real access rules, no stopgap (2026-10-25)

The stopgap of 2026-10-05 ("unlock items only on the 40 level locations") was replaced by real access rules for every check, read from the game's files
(docs/game-research.md, "Where the tapes, tokens and prizes are"; docs/level-gating.md, "Rules"). Unlock items now go anywhere really reachable.
History: before the stopgap **27 of 27** seeds put about 14 unlock items per seed on tapes, tokens or prizes; the stopgap kept a slot's own unlock items off them,
but not another FNAF slot's items nor any other progression, and a real two-FNAF room could not be finished.

`scripts/generator_check.py` now replays every seed with an independent copy of the real rules (`logic_problems`): every created location and the goal must be
reached, and no filler-only check may hold a progression or useful item (flags read from the `.archipelago` file). It prints how many runs put an unlock item
on a non-level check. `test_real_access.py` runs the same replay on two-FNAF multiworlds.

Negative control (2026-10-25): the world as committed in `23e107d` (stopgap, no real rules), built from `git show` into a scratch folder, on the same 6
two-FNAF seeds: Archipelago generates all 6, and **all 6 fail the replay** (44 to 62 locations per player never reachable with the real rules, progression on
checks that are now filler only). The new world passes all 6.

**Count by need** (2026-10-25, the user's choice after the toggle sweep found per_level with prizes off and tapes on at 56 progression items for 54 checks):
only as many Glitch Tapes / Faz Tokens are progression as the goal needs (`data.tape_token_requirements`), the others are filler; the trim drops the License before
the traps; a seed whose progression items still cannot fit is refused with an `OptionError` naming the options to change (`data.capacity` gives the numbers:
for example 100 % with per_level, prizes off, tapes on: 56 for 54). Glitchtrap "You Do Not Die", when it is not the goal, only needs every level (filler only).
`test_real_access.py` runs the tight seeds (per_level, prizes off, every goal x 3 combinations) through the real generator: each one generates and passes the replay,
or is refused with the message.

Full-run sweeps of 2026-10-25 with the final code (every seed replayed with the real rules; the generator's "Could not access required locations" warning counts as a problem; a seed `data.capacity` says cannot fit must be refused with the `OptionError`): **(A)** all 6 goals x 3 unlock modes x all 7 start sections x seeds 1-3, everything on: **378 of 378 generated, 0 problems**, every run with unlock items on non-level checks. **(B)** all 6 goals x 3 unlock modes x sections `fnaf_1`, `night_terrors` x seeds 1, 2 x the 8 toggle combinations: **568 generated with 0 problems, 8 refused as expected** (100 % with per_level, prizes off and tapes on: 56 important items for 54 checks, and with tokens too 86 for 83), `RESULT: OK`. **(C)** 36 multiworlds with two FNAF players (6 different option sets, 3 seeds each pair): 36 of 36 generated and passed the replay for both players, 1449 unlock items on non-level checks in total.

Mutation check: 20 mutants of the new code (a tape on the wrong map, the Ennard hard row on another map, a map rule keeping one level, pickups or filler-only checks without a rule, filler-only not excluded, Survive not excluded or keeping its goal rule, never-sent checks or unused goals created, the 100 % list keeping never-sent checks, the pool not trimmed or trimming a needed item or the traps first, the goal not passed to the regions, every / no tape and token progression, no refusal, a wrong capacity): all killed. "Prizes free" is equivalent (a prize needs any level item and every seed starts with one); it is caught by a text check.

## Fixtures: the suite is hermetic

No test needs a private save any more. `tests/gvas_fixtures.py` builds synthetic GVAS saves (a fresh `starter_player00()`, a
`completed_template()` with tapes, coins, hub audio and eaten objects) from the layout the save generator itself walks, and
`isolate_localappdata()` installs the starter as `Player00.sav` in the temp save folder. Previously the save helpers fell back to
`Player00.sav` / `Playerarchi.sav` in the **current directory**, so the suite silently read the developer's private, gitignored files
(and failed or skipped without them). Verified on 2026-10-04: all 135 tests pass with those files hidden, from another working
directory, and with them present. The only optional extra is `TestCleanRealCompletedSave`, which also runs on a real `100percent.sav`
when one is in the repo root (skipped otherwise).
