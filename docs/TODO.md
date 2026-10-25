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

- **Tape room: unique tapes (2026-10-26, replaces the tape count of 2026-10-05).** The 16 tape items are one per log; `derived_counters.lua` sets the tape count to
  the number of different tape items received (the room keeps that many slots) and `tape_shelf.lua` gives the kept slots the logs received, in order. The
  count mechanism itself (returning the value from the `GetGlitchCount` hook) is VERIFIED in game since 2026-10-05; the rest is in "To verify in game" below.
  Design question still open: whether a tape picked up in a level should be visible in the room before its item arrives (today: no, the room follows the items).
- **TV milestone prizes (5/10/... coins) still follow the vanilla pickup.** They are awarded inside the physical coin pickup (`AttemptAwardSpecialPrize`), so Faz Token items alone never trigger them. Needs a probe of that award path
  (hook only `AttemptAwardSpecialPrize` and `UnlockCoin`, which the mod already hooks; log the coin count it sees) before choosing between letting the game run its own award when the item count changes (unhook, call, rehook) or something else.
- Fold `faz_tokens.lua` into `derived_counters.lua` once the tape counter is proven (it has extra behaviour: the `PlayerCoins` cache write, which the generic module does not have).
- **Find the ids of the 24 dropped prize locations** (see "Prizes" in [game-research.md](game-research.md)); every id found can be switched back on.

## Changes since v0.2.0 (for the next release notes)

- `archipelago_enabled = false` in `config.lua` turns the mod off (play the normal game); documented in the install guide.
- **Unlock items are only placed on level-completion locations** (new seeds from the new apworld; rooms already generated keep their placements). Before, every seed put about 14 unlock items on tapes, tokens, prizes and similar locations, which could make a seed unfinishable if the real pickup is behind that level. Checked with 297 real-generator runs (`scripts/generator_check.py`).
- Playing a tape in the tape room no longer sends a location check (it did, because the room shows tapes by item count: every Glitch Tape item was a free check). Only a real pickup counts. In-game confirmation pending.
- New option `death_link_gift_box` (default on = unchanged): off keeps the game over from the prize gift box jumpscare (a defeat on the map `Level_Victory`) from being sent as a DeathLink. Sending only, and only with `death_link` on. Released in 0.3.1. Seen working once in game with the option off (2026-10-06); **PARTIAL**, see "The gift box jumpscare" in game-research.md.

- **Location group toggles** (released in 0.4.0, 2026-10-10): `randomize_prizes`, `randomize_faz_tokens`, `randomize_glitch_tapes` (default on). A group that is off has no locations and no matching items and is vanilla in game; the client drops its checks; the mod stops overriding the tape count / TV count for it. Details: "Location group toggles" in [game-research.md](game-research.md). Needs the apworld **and** the mod reinstalled.

- **One Archipelago save per multiworld** (released in 0.4.0, 2026-10-10): `Playerarchi_<seed>_<slot>.sav`, named to the mod by `SAVE_SLOT`; sessions made before keep `Playerarchi.sav`. Plus: a client whose bridge cannot start refuses to connect and says why. Details in "Mod/game plumbing" in [game-research.md](game-research.md).

## Logic to check

- **Real access rules, stopgap removed (2026-10-25, unreleased).** Every tape, Faz Token and prize has the access rule the game's own files give it (a pickup needs every level played on its map; a prize any level win; the uncertain ones are filler only), and unlock items go anywhere really reachable.
  The checks nothing sends (Hub Trophies, Normal Ending, Blackjack, the unused goals) are not created. Details: docs/level-gating.md "Rules", docs/game-research.md "Where the tapes, tokens and prizes are", docs/testing.md "Real access rules, no stopgap".
  Still to see in a real room: the rules are read from game data and Blueprint code (VERIFIED offline), not seen in game.
- **Every goal generates (fixed 2026-10-25, unreleased).** `complete_all_minigames_nights_hard_mode`, `hundred_percent` and `token_tape_quota` used to fail with `Game appears as unbeatable` (the rules asked for the `useful` Nightmare Mode License and for filler Faz Tokens, which `state.has` does not count).
  Now the hard goal needs every level plus Pizza Party (no License; it stays in the pool as a useful item), and the 30 base Faz Tokens are progression (skip balancing) while the spare-slot Faz Tokens stay filler. Every goal x every toggle combination generates; see "Every goal generates" in docs/testing.md.
- The earlier "generator verified" runs used `--skip_output` and never checked beatability (see docs/testing.md).
- (Fixed 2026-10-25) Tape and Faz Token locations had no access rule; they now have the real one (see above).
- Not detected yet, so not checks: Hub Trophies, Normal Ending, Blackjack. They could come back once the mod or client can see them (needs a probe in game).

## To verify in game

- **Unique tapes (2026-10-26). The user tested it in a real room on 2026-10-26 and reports that the unique tapes work** (with the relabel about 5 s after entering); the list is kept as the regression checklist. Needs the apworld AND the mod reinstalled, and a room generated with this apworld.
  1. Receive `Glitch Tape #01 (Intro)` only: the room shows one tape, labelled TAPE #1, and it plays the intro log.
  2. Receive one later tape only (e.g. `!getitem Glitch Tape #09 (Dark Rooms Plushbaby)` in a fresh room): one tape on the shelf, labelled TAPE #9 after the relabel, playing log 9.
  3. Several logs with gaps (e.g. #02, #09, #14): the shelf shows them side by side from the first spot, labelled #2, #9, #14 in that order, each playing its own log, in flat mode (keyboard / controller selection) as well as by grabbing. `UE4SS.log`: `[ARCHI] Tape shelf: N slot(s) relabelled (pass 1); the shelf shows 3 log(s): 2,9,14`.
  4. **Faster relabel (2026-10-27; seen working by the user in a real room 2026-10-27, one session: the labels change in about a second; still to watch over more sessions: the log lines below, the hub, no tape missing).** On every room visit the labels should change about 0.5-1.75 s after the map change (often hidden by the fade-in), not about 5 s; before that the shelf shows logs 1..K in plain order and playing a tape could play a log we do not own (the check is never affected). Judge whether it is still noticeable. `UE4SS.log`: `[ARCHI] Tape shelf: K of K log(s) on the shelf after N pass(es): ...` right after the `[DIAG] map: ... -> 'Cassete_DarkRoom'` line, with no `(stopped at the cap)`.
     Also check nothing else changed: entering the hub still logs `[DIAG] map changed: timers paused for 5s`, items, tokens and the level menu still update a few seconds later, and no tape on the shelf goes missing (the shelf shows as many tapes as tape items received).
  5. A room generated before this version (only old `Glitch Tape` items): no crash, the tape room shows no tape, and `UE4SS.log` has exactly one `[WARN] [ARCHI] This room hands out the old 'Glitch Tape' item (id 101000001) ...` line per session.
  6. `randomize_glitch_tapes: false`: no tape item in the room at all, the tape room shows the tapes picked up (vanilla), no `Tape shelf` line.
  7. `ap_tape_shelf_status` and `ap_counter_status` (count = number of different tape items received) agree with what the room shows.
  Not probed, left as is: `GetGlitchtrapStage` (UNVERIFIED in game; the Blueprint code reads it straight from `GetGlitchCount`, which the mod already sets to the tape count, so the stage stays the item count as before).

- **Every goal generates (2026-10-25, world only, HYPOTHESIS in a real room).** One short room per fixed goal (`complete_all_minigames_nights_hard_mode`, `hundred_percent`, `token_tape_quota`) generates and connects; Faz Token items still arrive and the TV
  count goes up by one per Faz Token item, base or filler (`ap_coin_status`: `items=` = every Faz Token received); the Nightmare Mode License, when it arrives, logs `Granted Nightmare Mode License!` as before; reaching Pizza Party still ends the game.
  In the hard goal's spoiler the License is just one more item (no goal needs it).

- **Timers hold still after a map change** (`game_thread.lua`, for a player whose game died entering the hub). Launch (it must get past the title screen: the first version, with LoadMap hooks, crashed at start),
  go title -> hub -> a level -> hub. `UE4SS.log` must show `[DIAG] map changed: timers paused for 5s` after each `[DIAG] map:` line except the first ones at startup, items, tokens and the level menu must still
  update a few seconds later, and the heartbeat shows `held=`. Then the player's own run: does the hub load now?
- **One save per multiworld** (the game accepts and writes the new slot names: VERIFIED 2026-10-10, three rooms' files in the folder; still unchecked: switching rooms while the game is running, going back to an older room, a room from before the change). With the client started first: connect to room A, start the game, play a little (a level or a token), close the game; connect to a NEW room B (same client: `/disconnect`, `/connect`), start the game:
  B must show a clean save (no progress of A), `UE4SS.log` shows `Archipelago save slot for this session: 'Playerarchi_<seedB>_<slot>'`, `Enforced SaveSlotName=...` and `Successfully synchronized ... save`, and `SaveGames\` holds both `Playerarchi_<seedA>_...sav` and `...<seedB>...sav` and no new `.bak`.
  Then connect back to A: its progress is back. A room you started before this version must still use `Playerarchi.sav`. Also check the game really writes progress into the new file name (play a level, look at the file's timestamp).
- **No bridge**: open a second client window while the first is still open and try to connect: expect `NOT connecting. Another AP bridge client is already running ...` in its window, no `helpDev has joined`-style join in the room's server log, nothing changed in the bridge folder.
  (The refusal calls the framework's `disconnect()`: if it does not close the connection, the error is still shown and nothing is written, which is the part that matters.)

- **Location group toggles** (**VERIFIED by the user in real rooms, case by case, 2026-10-10**; the list below is kept as the regression checklist, only the room built by a 0.3.1 version and the "everything off" case may not have been run). One room per case, DeathLink off to keep it simple:
  1. All three on: behaviour exactly as before (checks sent, `[SESSION]` shows no "Not randomized" line, panel total 153, tape room and TV follow the items).
  2. `randomize_glitch_tapes: false`: play to a tape (the intro tape is the easy one) and confirm no tape check is sent (`[ARCHI] Ignoring 'Collect ...' ... not part of this multiworld` once, nothing in the room's checks, no error in the client log),
     `ap_counter_status` shows `randomized=false effective=nil`, and the tape room shows the tapes you picked up (not an empty room, not the item count). Also confirm there is no Glitch Tape item in the room.
  3. `randomize_faz_tokens: false`: pick up a token, no check sent, the TV shows the real count (`ap_coin_status`: `randomized=false effective=nil`), no Faz Token item is received at all (level and prize checks give other items, the filler is `Faz Coupon`), the 5/10/... coin prizes behave as vanilla.
  4. `randomize_prizes: false`: win a level, open the prize box, the prize is yours in the game but no prize check is sent; the level check is.
  5. Everything off: levels still send checks, Pizza Party still ends the game, the panel total reads 50, and nothing about tapes / tokens / prizes appears in the client except the one "not part of this multiworld" line per pickup.
  6. A room generated with 0.3.1 (or older) played with the new client and mod: unchanged behaviour (no filtering, `RANDOMIZED_GROUPS` all 1).

- **The crash fix** (2026-10-05, HYPOTHESIS): play an hour or more, including level wins, map changes and a restart of the game with the client running. Expect `[DIAG] map:` lines, one
  `[DIAG] up=` line a minute, `gi_scans` staying at 1-2, no `[ERROR] [LOOP]`, `[SYNC] Inbox replay: skipped N line(s)` at launch and no more `PlayerCoins -> 30` flicker.
  After a crash copy `UE4SS.log` first, then run `python scripts/crash_report.py --win64 <Win64 folder>`.
- A **new seed** from v0.2.0 on (published): it has 153 locations (57 prizes); the client counter reads `/ 153`.

- `hard_variants: separate` in a real room (generator-verified only).
- A new seed started while the normal save is a **completed** one: the clean-save generator resets tapes (collected and listened), coins, hub audio and
  eaten objects, and its output on a real 100 % save is correct offline, but the game has not yet loaded a save made that way. Tapes appearing and the
  game starting normally would close this (it also covers an empty `ObjectsEaten` set).
- **`death_link_gift_box`** (PARTIAL: `false` seen working once on Parts and Service Bonnie, 2026-10-06; still to see: `true` with a gift box scare, the other player's side, other level types). With DeathLink on, win a level and keep opening the prize box until it jumpscares you. For `false` expect, in `UE4SS.log`, `[SESSION] DeathLink gift box jumpscare is NOT sent for this slot` at connect, then `[DEATHLINK] Level lost on map 'Level_Victory', not sent: ...`, and no death for the other player.
  Then check that a real defeat in a level still sends (`Level lost on map '<level>': death sent`), and that `true` (the default) still sends the gift box one. Also look at which map the log line names for the other level types.
- The launcher client with **DeathLink** and with VR (flat mode is what was tested).
- Whether the TV milestone prizes (5, 10, ... coins) are pickup-time awards that a physical pickup should be blocked from granting. UNVERIFIED.
- Nightmare Mode License and the other items without a verified in-game effect (Prize Counter Key, traps).

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
