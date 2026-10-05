# Roadmap and open questions

Confidence labels (**VERIFIED**, **PARTIAL**, **HYPOTHESIS**, **UNVERIFIED**, **BLOCKED**) as in [README.md](README.md).

## Next

- **DeathLink: receiving.** The `death_link` option, the tag subscription, echo/duplicate protection and the `DEATH_LINK_MODE` line are done and
  tested. A probe in game (2026-10-04) showed that losing a level calls `BP_FNAF_GameInstance_C:LevelDefeat` exactly once (no arguments); `DefeatLevel` and
  `LoadGameOver` did not fire, `H_DefeatLevel` and `DefeatToTitle` cannot be hooked. **Sending** on `LevelDefeat` is implemented (opt-in, debounced, never
  for a death the mod caused), tested in a Lua interpreter and VERIFIED in game with Hollow Knight (2026-10-04): losing a level killed the other player, twice,
  and a Hollow Knight death reached the mod as `DEATHLINK ...`. **Receiving v1** is implemented (2026-10-04): an incoming death calls `LevelDefeat` on the
  game thread with our own hook removed for the call (calling a hooked Blueprint function from Lua crashed the game; `ap_dl_unhook` + `ap_dl_call LevelDefeat`
  was VERIFIED by hand), only inside a level, never for deaths replayed from the inbox at launch, one every 10 s. Tested in a Lua interpreter, VERIFIED in game with `ap_dl_kill`
  and with a real Hollow Knight death (2026-10-04), in both directions. **Parked:** playing the game's jumpscare before the defeat (a direct `LevelDefeat`
  skips it) and doing anything in the hub (today nothing happens there). Starting the jumpscare from Lua did not work: see "Losing a level" in
  [game-research.md](game-research.md) for what was tried and what is known.
- **Pizza Party unlock rule.** UNVERIFIED. The mod never gates it and the logic requires every level first. Decoding the game's `IsLevelUnlocked` /
  `IsLevelBeaten` Blueprint logic (names seen in its data: `PizzaPartyID`, `CompletedLevelCounter`, `GetInitialUnlockedLevels`) or probing in game
  would allow relaxing that rule.

- **Tape count: the override works with a forced value and with a real item (VERIFIED in game 2026-10-05: `!getitem Glitch Tape` gave a tape in the room).** `GetGlitchCount` hands the hook no parameters, so `:set` was impossible; returning the value from the callback works (0 tapes in the save, `ap_counter_force tapes 2` -> 2 tapes in the room, `off` -> 0).
  Offline, the whole chain (client -> inbox -> mod) is now covered for several items, reconnect, restarts, a new seed at 0 and tape checks (`tests/test_tape_count_flow.py`, 2026-10-05); that is not an in-game confirmation.
  Still to check in game: the tape room shows exactly as many tapes as Glitch Tape items received with several items, with 0 at the start and after a reconnect, and which tapes it shows (the first N? the ones the save has?). Whether a tape picked up in a level should be visible in the room before its item arrives is a design question for later.
  History of the failed first attempt follows.
- (history) **Tape count: NOT WORKING (tried 2026-10-05).** `lib/derived_counters.lua` hooks `FNAFSaveGame_C:GetGlitchCount`, but that function reaches the hook with no parameters (`extra_args=0`), so there is no return value to override and the tape area
  showed no change with `ap_counter_force tapes 2`. The engine in `derived_counters.lua` (item count -> override, session handling, console commands, tests) is fine and stays for other targets; the *target* is unknown.
  The attempt to list function parameters from Lua failed too (Lua's `UFunction` has no `ForEachProperty`), see "Tapes, coins and prizes" in game-research.md. Next, in order: (1) retest `ap_counter_force tapes 2` with the callback-return experiment;
  (2) inside the tape area run `ap_instances UserWidget 100` and `ap_instances Actor 400` to learn which Blueprint classes the room is made of, then `ap_class` those and `ap_hookfn` their safe getters (`args=N [...]` shows what each receives);
  (3) if the room reads `CollectedGlitches` directly, say so plainly: the mod cannot change the number without writing the save set, which is the location state (corrupts checks) - then the options are to leave the tape area vanilla or to accept a save-level design.
- **TV milestone prizes (5/10/... coins) still follow the vanilla pickup.** They are awarded inside the physical coin pickup (`AttemptAwardSpecialPrize`), so Faz Token items alone never trigger them. Needs a probe of that award path
  (hook only `AttemptAwardSpecialPrize` and `UnlockCoin`, which the mod already hooks; log the coin count it sees) before choosing between letting the game run its own award when the item count changes (unhook, call, rehook) or something else.
- Fold `faz_tokens.lua` into `derived_counters.lua` once the tape counter is proven (it has extra behaviour: the `PlayerCoins` cache write, which the generic module does not have).
  **Decided (2026-10-05): the tape menu follows the Glitch Tape ITEMS received** (like the Faz Token count), not the tape checks. The 16 items are identical, so the
  menu will show the first N tapes in the game's tape order, N = number of Glitch Tape items. Still to settle once the probe names the getters: whether the physical
  pickup should still show a tape the player has not "received" yet (the check is sent either way).
- **Find the ids of the 24 dropped prize locations** (see "Prizes" in [game-research.md](game-research.md)); every id found can be switched back on.

## Changes since v0.2.0 (for the next release notes)

- `archipelago_enabled = false` in `config.lua` turns the mod off (play the normal game); documented in the install guide.
- **Unlock items are only placed on level-completion locations** (new seeds from the new apworld; rooms already generated keep their placements). Before, every seed put about 14 unlock items on tapes, tokens, prizes and similar locations, which could make a seed unfinishable if the real pickup is behind that level. Checked with 297 real-generator runs (`scripts/generator_check.py`).
- Playing a tape in the tape room no longer sends a location check (it did, because the room shows tapes by item count: every Glitch Tape item was a free check). Only a real pickup counts. In-game confirmation pending.

## Logic to check

- **Done 2026-10-05: unlock items only on level-completion locations**, so a tape, token or prize that is physically inside a gated level can never hold that level's unlock item (before: every seed did that, about 14 per seed). 297 real-generator runs, 0 misplaced; see docs/testing.md.
  Still open: where tapes, tokens and prizes really are (they have no access rule, which only matters now for the other progression items: Glitch Tapes, Prize Counter Key, Nightmare Mode License, all needed only for goals), and the Pizza Party unlock condition.
- **Three of the six goals cannot be generated** (full generator run, 2026-10-05, deterministic): `complete_all_minigames_nights_hard_mode`, `hundred_percent` and `token_tape_quota` always fail with `Game appears as unbeatable`, (the Glitchtrap goals failed only with the `nightmare_logic` option, removed on 2026-10-05: it was an invented extra requirement for the Nightmare Mode License).
  Cause: the rules need `Nightmare Mode License` (classified `useful`) and `Faz Token` copies (not progression), which Archipelago does not count. Fix (a world change, needs a decision): make the 30 base Faz Tokens and the License progression (keep the filler Faz Tokens filler), then re-run the sweep in docs/testing.md. Until then hide or warn about those goals in the template.
- The earlier "generator verified" runs used `--skip_output` and never checked beatability (see docs/testing.md).
- **Tape and Faz Token locations have no access rule in the world** (`Prize Counter` and `Faz Tokens` regions connect from the Hub with no requirement; only levels are gated). If a tape or token is physically inside a gated level, a seed can put that level's
  access item on that tape and soft-lock the player. Needs the tape-id -> level map from the game (`AwardGlitch` logs `GlitchID` and the map name); pre-existing, not caused by the listen change.

## To verify in game

- **The crash fix** (2026-10-05, HYPOTHESIS): play an hour or more, including level wins, map changes and a restart of the game with the client running. Expect `[DIAG] map:` lines, one
  `[DIAG] up=` line a minute, `gi_scans` staying at 1-2, no `[ERROR] [LOOP]`, `[SYNC] Inbox replay: skipped N line(s)` at launch and no more `PlayerCoins -> 30` flicker.
  After a crash copy `UE4SS.log` first, then run `python scripts/crash_report.py --win64 <Win64 folder>`.
- A **new seed** from v0.2.0 on (published): it has 153 locations (57 prizes); the client counter reads `/ 153`.

- `hard_variants: separate` in a real room (generator-verified only).
- A new seed started while the normal save is a **completed** one: the clean-save generator resets tapes (collected and listened), coins, hub audio and
  eaten objects, and its output on a real 100 % save is correct offline, but the game has not yet loaded a save made that way. Tapes appearing and the
  game starting normally would close this (it also covers an empty `ObjectsEaten` set).
- The launcher client with **DeathLink** and with VR (flat mode is what was tested).
- Whether the TV milestone prizes (5, 10, ... coins) are pickup-time awards that a physical pickup should be blocked from granting. UNVERIFIED.
- Nightmare Mode License and the other items without a verified in-game effect (Glitch Tape, Prize Counter Key, traps).

## Ideas

- **Mod off switch** (done 2026-10-05): `archipelago_enabled = false` in `config.lua`, documented in the install guide (with the `mods.txt` way). Not done: `install-mod.ps1` rewrites `config.lua` and re-adds `FNAFHWArchipelago : 1`
  to `mods.txt`, so an update turns the mod back on (preserve the line in the installer?), and an automatic switch when the client is closed (needs a client heartbeat; the mod cannot tell a closed client from a running one, and play on the normal save would queue false checks and never reach the room).
- A `host.yaml` setting for the bridge folder, as an alternative to reading the mod's `config.lua`.
- Packaging the UE4SS install (it is currently checked and linked, never bundled).
- Retire the tkinter standalone client once the launcher client has been used for a while.
- A `CHANGELOG` and a tagged release workflow.

## Open issues

- One game run on a seed (2026-10-04) never acknowledged any item (`[SYNC] Item sync` / `ITEMS_APPLIED` missing for ~27 minutes). Cause unknown, not
  reproduced in later runs. If it returns: add a log line in `ItemSync.tick` and check `ap_items_status`.
- Prize locations: the mod's own prize poll only counts the prizes (it must never decode them: that crashed the game); the client's save poll is the real source.
- `lib/auto_map_poller.lua`, `lib/collectible_hooks.lua`, `lib/check_awards.lua` are shipped but never loaded by `main.lua` (dead code). They also loop and scan: delete them before anyone loads them.
- `connection_ui.lua` looks up a font with `FindFirstOf` inside the HUD hook while its panel is open and no font is cached (game thread, only while the panel is visible).
- The inbox reader consumes a half-written last line as if it were complete (client writes mid-poll); never seen, not guarded.
- The `SaveLevelVictory` hook often cannot resolve the level row (`RowID=nil`); checks still arrive through the client's save poll. Root cause unknown.
- A crash between applying an item effect and the client persisting its acknowledgement can re-apply the last item once.
- The mod is inert (vanilla behaviour) when no `SESSION_SYNC` was received; there is no "offline" gating by design.
