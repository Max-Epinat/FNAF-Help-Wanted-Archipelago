# Game research notes

Facts about the game and UE4SS that the integration relies on. Confidence labels: **VERIFIED** (observed in game or in
game data), **PARTIAL**, **HYPOTHESIS**, **UNVERIFIED**, **BLOCKED**.

## Engine and hooks

- **VERIFIED** Unreal Engine 4.23 + UE4SS v3.0.1 (Lua). Not IL2CPP: there is no IL2CPP metadata to inspect.
- **VERIFIED** For Blueprint functions (path not starting with `/Script/`), `RegisterHook`'s **first** callback runs *after* the
  function; the second callback never fires.
- **VERIFIED** To change a Blueprint function's result, call `:set(value)` on the return-value parameter in that callback.
  Returning a value from the callback does **not** work.
- **VERIFIED** Hook parameters are `RemoteUnrealParam` wrappers: `get()` unwraps them. An `FName` only becomes text through `ToString()`.
- **VERIFIED** Calling a **hooked** Blueprint function from Lua (for example `gi:IsLevelUnlocked(4)`) crashed the game. Never self-call hooked functions.
- **VERIFIED** UE4SS console command handlers receive their arguments as a **table of words**, not a string.
- **VERIFIED** `UE4SS.log` is overwritten on every launch.

## Levels and unlocks

- **VERIFIED** Level rows come from `LevelInfoTable` (51 rows). FNAF 1 Night 1..4 = 4..7, Pizza Party = **29** (`Finale_Ending`); the old README/guide said 28 (that row is Night Terrors - Nightmare Fredbear).
- **VERIFIED** `IsLevelUnlocked(LevelID)` is called by the game when the hub night menus are built, not when a console command runs; the menu re-asks only after the hub is rebuilt.
- **VERIFIED** Overriding its result with `set(false)` locks the night in the menu.
- **HYPOTHESIS** Nights 2-4 appear to depend on `IsLevelBeaten(<Night 1 row>)` (call order shows `IsLevelBeaten(4)` nested inside `IsLevelUnlocked(5/6/7)`); not confirmed by reading the Blueprint logic.

## Faz Tokens / coins

- **VERIFIED** `SaveGameRef.PlayerTotalCoins` is **not** a stored property (reads back `nil` after a write). It is only the output name of `FNAFSaveGame:GetTotalCoinCount()`.
- **VERIFIED (asset names, discovery dump)** The count is derived from the `CollectedCoins` set (coin ids 1..30). `BP_FNAF_GameInstance.PlayerCoins` is an `IntProperty` cache; `GetCoinCount()` reads it.
- **VERIFIED** Calling the game's `UnlockCoin` would fire the `Collect Faz Token N` location hook, so item grants must not use it.
- **VERIFIED (in game 2026-10-04)** `GetTotalCoinCount` and `GetCoinCount` take their value as the first hook argument (`extra_args=1`); `:set(n)` on it changes what the main-menu TV shows. `GetCoinCount` reads through `GetTotalCoinCount`, so overriding the latter covers both.
- **VERIFIED** `GameInstance.PlayerCoins` is a plain writable property and was stale (read 0 while the real count was 1). Writing it made the 30-coin reward (Exotic Butter) appear on the prize counter. `UpdateCachedCoinCount` runs after a token pickup.
- **VERIFIED** The prize counter lists prizes by calling `HasPrize` many times, not through the coin getters.
- **VERIFIED** `Scripts/lib/faz_tokens.lua` makes the displayed count equal the number of Faz Token items in the server's list while a session is active: physical pickups raised the vanilla count 3, 4, 5 while the game kept showing 2. Pickups still send their `Collect Faz Token N` location check.
- **UNVERIFIED** The TV milestone prizes (5, 10, ... coins) did not unlock from the count override alone; they look like one-off awards made at pickup time (`AttemptAwardSpecialPrize`), not a threshold check. No world rule requires Faz Tokens for any prize location.
- Debug commands: `ap_coin_force <n>|off` (override), `ap_coin_status`.

## Archipelago server behaviour (this room, VERIFIED)

- The server sends `ReceivedItems` after `Connected` **only when the slot has items**; an empty slot gets nothing (so the client emits an empty snapshot itself).
- `ReceivedItems` also arrives right after a location check whose item belongs to the same slot.
- A restarted/reset room can have a shorter item list than the client's saved counters.

## Mod/game plumbing

- **VERIFIED** The mod forces the GameInstance `SaveSlotName` to `Playerarchi`, so the game writes `Playerarchi.sav` while the mod is active; `Player00.sav` is the normal save.
  **One save per multiworld (2026-10-10, offline tests only):** the client names `Playerarchi_<seed>_<slot>` with the `SAVE_SLOT` line and the mod forces that name instead (the same mechanism, loading the file into `SaveGameRef` once).
  **VERIFIED** (2026-10-10, real rooms: `UE4SS.log` shows `Enforced SaveSlotName='Playerarchi_<seed>_<slot>'` and the save folder holds three files of three different seeds, each written during play) that the game accepts and writes a slot with such a name. **Still HYPOTHESIS:** that switching the slot while the game is already running loads the other session's file cleanly (the rooms above were started client first, then the game), and going back to an older room.
  Found while testing the group toggles: a second client window without a bridge joined a new room and wrote nothing, so the game replayed the old session and its save (log: `Another AP bridge client is already running`); the client now refuses to connect without a bridge.
- **VERIFIED** The mod reads `ap_inbox.txt` from byte 0 at every launch (see [bridge-protocol.md](bridge-protocol.md)).
- **VERIFIED** The Lua prize poll (`check_and_award_prizes`) reads prize ids as raw pointer strings, so it never maps a prize; prize checks come from the client's save poll. Since 2026-10-05 it only *counts* the prizes (`[ARCHI] Save prize count changed`) and never decodes an element: decoding is what fed garbage to `ToString` (see "Crashes"). Do not bring the decoding back; it would also activate a second prize-check sender.
- **VERIFIED** `World:GetName()`, `GameplayStatics:GetCurrentLevelName` and `GameInstance.CurrentLevelName` come back as an FString that decodes to garbage (the `Map=` field of the `SaveLevelVictory` log line was random wide characters at both victories of the 2026-10-04 session). The map name is cut out of `World:GetFullName()`, a plain string.
- **UNVERIFIED** Whether the Lua `SaveLevelVictory` hook can always resolve the row (it often logs `RowID=nil`); checks still arrive through the client's save poll.

## Tapes, coins and prizes: what the class dumps show (2026-10-05)

`ap_class` output of the playtest machine. Function names are **VERIFIED** to exist; what each one does and which ones the menus call is **UNVERIFIED** until probed.

- `FNAFSaveGame_C` functions: `GetGlitchCount`, `HasGlitch`, `HasListenedToGlitch`, `ListenedToGlitch`, `AwardGlitch`, `GetPrizes`, `HasPrize`, `GetTotalCoinCount`, `GetLevelInfoByID`, `GetLevelInfoByName`, `GetLevelOfType`, `CheckCompletedLevels`, `SetLevelInfo`, `HasListenedToHUBVO`.
  Properties: `CollectedGlitches`, `GlitchesListenedTo`, `CollectedCoins` (sets), `Prizes` (**ArrayProperty**), `LevelInfo` (map), `GlitchtrapDefeated`, `PrizeTable`, `LevelTable`.
- `BP_FNAF_GameInstance_C` functions: `HasGlitch`, `AwardGlitch`, `SetGlitchListenedTo`, `UnlockAllGlitches`, `HasCoin`, `GetCoinCount`, `UpdateCachedCoinCount`, `UnlockCoin`, `UnlockAllCoins`, `HasPrize`, `GetAvailablePrizesForLevel`, `GetAvailablePrizesBase`,
  `GetRandomAvailablePrize`, `AwardRandomPrize`, `AttemptAwardSpecialPrize`, `UnlockAllPrizes`, `GetSaveGame`, `IsLevelUnlocked`, `IsLevelBeaten`, `IsShowtimeUnlocked`, `LoadCasetteRoom`, `LoadGallery`, `LoadGlitchKeyhole`, ...
  Properties: `PlayerCoins`, `PrizeDataTable`, `SaveGameRef`, `PizzaPartyID`, `IsInNightmareMode`. `Prizes` is an array of names (ids like `55` in the .sav file); why the Lua side read garbage from it is **UNVERIFIED**.
- **VERIFIED** (`ap_hookfn` probe, 2026-10-05, offline, vanilla save with 4 tapes) Only single getters were hooked: `FNAFSaveGame_C:GetGlitchCount` fired **16 times** when the tape area (map `Cassete_DarkRoom`) was entered and 0 times in the hub;
  `FNAFSaveGame_C:HasGlitch`, `FNAFSaveGame_C:HasListenedToGlitch`, `BP_FNAF_GameInstance_C:HasGlitch` and `BP_FNAF_GameInstance_C:HasCoin` fired **0 times** there. The tape area loaded normally with these hooks.
  So the tape area gets its count from `GetGlitchCount`, not from per-tape `Has...` queries. **UNVERIFIED** what the 16 calls are (one per tape slot?) and whether the tapes listed come from the same count or read `CollectedGlitches` directly.
- **VERIFIED (negative)** Overriding `GetGlitchCount` does not work: the hook callback receives **no parameters** (`extra_args=0`, unlike `GetTotalCoinCount`, which receives its return value), so there is no value to `:set`, and
  `ap_counter_force tapes 2` changed nothing in the tape area (2026-10-05). The earlier hypothesis "the tape count is the return value of `GetGlitchCount`" is therefore **wrong in that form**.
  **UNVERIFIED** why a function with no parameters is called 16 times when the tape area loads (a setter? a function whose result goes into a Blueprint local? the real count read elsewhere?).
- **VERIFIED** (`ap_instances Actor`, inside the tape area, 2026-10-05) The room `/Game/Scenes/Cassete_DarkRoom` holds **16 `AquiredLog_C` actors** (`AquiredLog16` .. `AquiredLog31`), a `CasettePlayerSetup_C`, a `TapeRoom_PlayerPawn_C`, a `Button_TapeRoom_C`, the level blueprint `Cassete_DarkRoom_C`, a `GlitchtrapSetup2_C` and `ENV_MOD_TapeHolder_01_2`.
  **HYPOTHESIS** (consistent with the forced-value result) the 16 calls to `GetGlitchCount` when the room loads are one per `AquiredLog_C` (one per tape), each deciding whether to show its tape.
- **VERIFIED** (in game, 2026-10-05, offline, forced value) Returning a value from the hook callback overrides `GetGlitchCount`: with 0 tapes in the save, `ap_counter_force tapes 2` made the tape room show **2 tapes** (log: `extra_args=0 vanilla=nil -> 2 (returned from the callback)`) and `ap_counter_force tapes off` put it back to 0.
  This is the opposite of `IsLevelUnlocked`, which has a return-value parameter and needs `:set`. It also follows a real room: one `!getitem Glitch Tape` gave a tape in the room (user report, 2026-10-05). **UNVERIFIED**: which tapes the room shows (the first N? any?), several items, and a reconnect.
- **VERIFIED** (UE4SS docs + the dump of 2026-10-05) Lua's `UFunction` type has only `GetFunctionFlags` / `SetFunctionFlags` (and the `UObject` methods); `ForEachProperty` belongs to `UStruct`. A first attempt to list function parameters with `fn:ForEachProperty` produced nothing at all
  (and its test passed only because the test stubbed the missing method). So a function's signature cannot be listed from Lua; `ap_class` now prints `FLAGS` per function instead (hex plus HasOutParms / Const / BlueprintPure ...), and `ap_hookfn` logs `args=N [Type=value, ...]` for a function's first three calls.
- **VERIFIED** (UE4SS source, `lua_unreal_script_function_hook_pre`) A hook callback receives `self` and the `CPF_Parm` parameters; the function's return property is handled apart, and UE4SS documents that a value *returned* by the callback overrides the function's result.
  For Blueprint hooks (the callback runs after the function) returning did not work for `IsLevelUnlocked` (2026-10-03), so `:set` on the return-value parameter is what works where that parameter exists. `derived_counters.lua` also returns the value when it received no parameter: **HYPOTHESIS**, low odds, not yet tried.
- **PARTIAL** The 5/10-coin prizes come from `AttemptAwardSpecialPrize` (seen firing inside the 10th pickup). Not probed yet.
- **VERIFIED** Entering the tape area runs, in this order: `FadeOut`, `FadeOutWithLevelLoad`, `ExecuteUbergraph_BP_FNAF_GameInstance`, `LoadCasetteRoom` (the map change then follows).
- **VERIFIED** Rates while idle in the hub: `GetSaveGame` about 330 calls/s, `IsNightmareModeEnabled`, `GetFLCameraSensitivity`, `GetTetheredCameraSensitivity` about 165/s each. Do not hook those.

### Tape room tests with the count following the items (2026-10-05, in game, flat mode, one room)

- **VERIFIED** (screenshots, log) The room shows the **first N slots in order**, N = number of Glitch Tape items: N=1 `TAPE #1`; N=2 `#1`-`#2`; N=11 `#1`-`#8` down the left column and `#9`-`#11` at the top of the right column. The save held no tape (`CollectedGlitches` absent), so the picture comes only from the override. Several items in a row, six in about 3 s, and non-tape items changed the count exactly as expected.
- **VERIFIED** (log) The room does not re-read the count while it is open: `GetGlitchCount` was not called again for 3+ minutes after an item arrived, and the new tape showed on re-entry. (That the display did not change inside the room is inferred from the calls, not seen.)
- **VERIFIED** (log) Reconnecting the client reads `0` then `11` in the same second (every connect starts from an empty snapshot), `applied=15 of 15`, nothing re-applied. A game restart with the client OFF replays the last connect block and gives the same 11 tapes and `applied=15 of 15`.
- **PARTIAL** `GetGlitchCount` is called about 4-6 times when the hub loads and about 16 when the tape room loads (`calls` 22 -> 43 -> 69 across hub reloads and room entries); the earlier probe saw none in the hub. Why the hub asks is **HYPOTHESIS**. No sign of calls inside a level (the intro scene).
- **HYPOTHESIS** (one locked launch, one open launch) The tape room entrance needs `UnlockedAudioLog = true` in the save: a save built from a fresh starter save (flag absent) refused entry even with 1 tape item; the same save with only that flag added opened the room and `VisitedDarkRoom` stayed absent. Every earlier save that worked had the flag. The clean-save generator copies it from the template, so a player starting from a never-played normal save may find the room locked until they unlock it in vanilla.
- **VERIFIED** Picking up the intro tape fired `AwardGlitch` once with `GlitchID=14` (`Collect Prize Counter Intro Tape`), saved `CollectedGlitches=[14]`, was queued while the client was disconnected and sent on reconnect; the id does not come from our count (11/12). The returned Glitch Tape raised the room to 12.
- **VERIFIED** Playing a tape in the room fired the `SetGlitchListenedTo` check: `Collect Glitch Tape 03` and `11` were sent with `CollectedGlitches` = `[14]` and `GlitchesListenedTo` = `[1, 10]`. **PARTIAL** which tapes were played (probably `TAPE #2` and `#11`, so slot = GlitchID + 1) is inferred. Fixed: the hook now only logs (`[ARCHI] Tape listened to, no check sent`); offline tests cover it, the in-game confirmation is pending.

### `ap_hookclass` on the game instance blacked out the tape area (2026-10-05)

- **VERIFIED** (log) `ap_hookclass` on `BP_FNAF_GameInstance_C` hooked 78 functions, among them the fade, level-load and event-graph functions above. At the moment the tape area was entered UE4SS logged
  `[push_textproperty] Operation::GetParam is not supported` (14 times) and `Tried accessing unreal property ... 'DelegateProperty' not supported`, and the screen stayed black. The game did not crash.
- **PARTIAL** Cause: hooks on functions with text or delegate parameters (`FadeOutWithTimerEvent` takes a delegate) and on the level-loading chain broke the flow. No black screen was reported without those hooks, but which hook did it is **HYPOTHESIS**
  (confirm: enter the tape area on a launch with the research tools off, or with only the safe getters hooked).
- **Fix** `research_tools.lua` now skips the UNSAFE functions in `ap_hookclass` / `ap_watch` (names containing ubergraph, fade, load, timer, restart, achievement, instruction, receiveinit, spawnlevel, caveat) and `ap_hookfn` refuses them unless the second word is `force`.
  Probe single getters with `ap_hookfn`, never a whole class that owns level loading.
- `enable_research_tools = true` itself is not the cause of the instant crashes seen on the same evening: those dumps are the game's own launch crash (signature C below).

## Crashes

Analysed on 2026-10-05 from the dumps of 2026-10-04 (`<game>\freddys\Binaries\Win64\crash_*.dmp`, written by UE4SS, and
`%LOCALAPPDATA%\freddys\Saved\Crashes\*\UE4Minidump.dmp`, written by the game). `python scripts/crash_report.py --win64 <that Win64 folder>` prints the
facts below for a dump. The offsets are for the game exe of 2026-03-21 and UE4SS v3.0.1 (build d935b5b). Dumps are 20+ MB and must never be committed.

| Signature | Dumps | What the dump shows |
| :--- | :--- | :--- |
| **C** `freddys-Win64-Shipping.exe+0x92d06f`, null read | 19 (13 in April, 6 in October), 3-9 s after process start | **VERIFIED** inside the game's own exe, not UE4SS or the mod. **HYPOTHESIS** it is the game's own startup bug; UE4SS was present in all of those runs, so whether it needs UE4SS is **UNVERIFIED**. Relaunching works. One more April dump (2026-04-06, uptime 2770 s, `freddys-Win64-Shipping.exe+0x8f3708`) is a different mid-session crash inside the game exe; not understood. (HANDOVER called it `UE4SS+0x555256`: the dumps do not show that.) |
| **B** `UE4SS.dll+0x3c4113`, read of `0xFFFFFFFE` | the playtest crash (uptime exactly 3600 s) and one at 11 s | **VERIFIED** the faulting instruction is the `wcslen` loop of UE4SS's Lua `FString:ToString`, on a bogus string pointer. **PARTIAL** no stack: the mod called `ToString` on garbage in two places, `save.Prizes:ForEach` (every 2 s from a worker thread, and on every prize award) and `World:GetName()` (every level victory). Most garbage pointers are readable, so it crashes only when one is not: about once an hour fits. |
| **A** `UE4SS.dll+0x52dbb9`, read of `0x18` | 7 of 10 on 2026-10-04, uptime 47-804 s; the last one 2 s after a map load | **VERIFIED** the faulting thread is a UE4SS **worker thread** (it starts at `ucrtbase!thread_start`, 25.9 s of CPU), not the game's first thread. **PARTIAL** (disassembly, no symbols) the code compares the class name of each object during an object-array scan (`FindFirstOf`/`FindAllOf` by name) and the object had `ClassPrivate == NULL`, i.e. it was being destroyed. **HYPOTHESIS** the mod's `LoopAsync` timers caused it: they ran about 3-4 full `FindFirstOf` scans a second off the game thread, and about 900 log lines of replayed inbox history in the first two seconds of every launch. |

- **VERIFIED** (UE4SS documentation) `LoopAsync` / `ExecuteAsync` run their callback in an async thread, `ExecuteInGameThread` on the game thread, and `LoopAsync` is deprecated.
  Newer UE4SS has `LoopInGameThreadWithDelay`; whether v3.0.1 has it is **UNVERIFIED** (the mod uses `LoopAsync` only to schedule and `ExecuteInGameThread` for the work).
- **Fix** (2026-10-05, `lib/game_thread.lua`): every periodic job runs through `ExecuteInGameThread`; the game instance is cached, and never searched for off the game thread;
  the prize poll counts without decoding; the map name comes from `GetFullName()`; the first pass over the inbox replays only the last connect block.
  Status: **HYPOTHESIS** until a play session of an hour or more has passed without crash A or B. Crash C is not touched by this.
- **Diagnostics**: `[DIAG] map: 'A' -> 'B' (up Ns)` at every map change and a `[DIAG] up=... map=... lua=...KB gi_scans=... loops(runs/skipped)` line every 60 s; `ap_diag` prints it on demand;
  a loop error appears once as `[ERROR] [LOOP] <name>: ...`. A crash right after a `map:` line, or `skipped` counts that keep growing, are the clues.
- The playtest's own `UE4SS.log` was lost: the log is overwritten at the next launch (the relaunch came a minute later). After a crash, copy `UE4SS.log` **before** starting the game again.

## Prizes (2026-10-05)

- **VERIFIED** Prizes reach the room: the client's persisted state of the playtest lists 11 `Prize - ...` locations among its 34 checks (10 tokens, 4 tapes, 11 prizes, 9 levels), found by parsing `Playerarchi.sav`.
- **VERIFIED** Flow: a level victory is followed about 8 s later by `AwardRandomPrize` (prize count 14 -> 15 -> 16 in the log). **PARTIAL** the 10th vanilla coin also awarded one (16 -> 17 in the same pickup, between `UpdateCachedCoinCount` and `UnlockCoin` finishing): the TV milestone prizes look like awards made inside the pickup flow.
- **VERIFIED** The client's id map (`DEFAULT_PRIZE_MAP`) covers 57 of the 81 prize locations. A 100 % save holds 66 prize ids: 57 map, 9 have no location (2, 3, 4, 9, 10, 75, 80, 87, 118). So **24 prize locations can never be reported, even by a 100 % save**: Golden Freddy / Springtrap / Mangle / BB / JJ / Plushtrap / Nightmare x4 plushies, Golden Freddy / Springtrap / Ballora figures, and 11 "Other" prizes (Exotic Butters, Mr. Cupcake, Pizza Slice, Faz Soda, Bon-Bon Hand Puppet, Mini Music Box, Candy Bucket, Foxy and Nightmarionne Bobbleheads, Mystery Box, Prize Counter Poster).
  **HYPOTHESIS** some of the 9 unmapped ids are some of these 24 (for example the coin-tier prizes), the rest being cut or unobtainable content. Which ones is **UNVERIFIED** and cannot be read offline (the pak is encrypted).
- **Decision** `UNDETECTABLE_PRIZE_CHECKS` (`fnaf_help_wanted/data.py`) keeps the 24 out of the multiworld: a location nobody can check would hold an item nobody can receive, and the fill may put a progression item there. Their ids stay reserved (ids are append-only). To bring one back, find its save id (play, then diff the `Prizes` list of `Playerarchi.sav`), add it to `DEFAULT_PRIZE_MAP`, remove the name from the set; a test keeps the set equal to "prizes minus the client's map".

## Losing a level (DeathLink research, 2026-10-04)

- **VERIFIED** Losing a level calls `BP_FNAF_GameInstance_C:LevelDefeat` exactly once, with no arguments. About two seconds later the game reloads a level
  (the game-over flow). `DefeatLevel` and `LoadGameOver` did **not** fire at that moment; `H_DefeatLevel` and `DefeatToTitle` cannot be hooked.
- **VERIFIED** Calling `LoadGameOver` from the console (`ap_dl_call LoadGameOver`, on the game instance, inside a level, with no hook on it) loads the
  game-over screen.
- **VERIFIED** `DefeatLevel` is not a callable function on the game instance: calling it errors. **HYPOTHESIS**: it is an event dispatcher / property.
- **VERIFIED** Calling `LevelDefeat` itself works, with our own hook removed first (`ap_dl_unhook`, then `ap_dl_call LevelDefeat`): it returns normally and
  the game reloads a level about two seconds later, exactly like after a real defeat. (The first attempt had been refused by the tool: a registration loop
  re-hooked it one second after `ap_dl_unhook`; fixed and covered by a test.) Calling it while our hook is on it crashed the game before.
- **VERIFIED** (2026-10-04) `ap_dl_kill` in `Repair_Bonnie_Game` made the player lose the level through this path (unhook, `LevelDefeat` on the game thread, hook back
  after 2 s; the hook was active again afterwards). The map name comes from `World:GetFullName()` (`GetName()` returns pointer garbage). The hub's map is
  `Main_Menu_With_Showtime`.
- **UNVERIFIED** Whether that defeat includes the jumpscare: a real defeat probably runs level code (the jumpscare) before `LevelDefeat`, which a direct
  call skips.
- **UNVERIFIED** What `LoadGameOver` does in the hub, and whether the game has a jumpscare that can be played on its own. The research tools
  `ap_scan <word>` (lists every game object whose name contains the word, into `ap_scan_<word>.txt` in the mod folder) and `ap_watch <word>` (log-only hooks
  on the matching game functions, lines `[WATCH] ... called`) exist to answer such questions from a real run.
- **VERIFIED** DeathLink works both ways with Hollow Knight (2026-10-04): losing a level kills the other player and a death from the other player makes you lose the level you are in.
- **VERIFIED** `ap_scan jumpscare` in the hub froze the game for good (it walks every object). Use `ap_class` / `ap_instances` instead.
- **VERIFIED (asset names in the pak index)** Jumpscares are per enemy: one animation asset each (`Bonnie_Jumpscare_01`, `Foxy_Jumpscare_01`, `Mangle_Jumpscare_01`, ...).
  Generic Blueprints exist: `/Game/ProductionAssets/Blueprints/JumpScare` (`JumpScare_C`), `GalleryJumpScare_C` and a data table `Data/JumpScareList`. What they do
  is **UNVERIFIED**. The pak contents are encrypted, so assets cannot be read offline without the AES key.
- **VERIFIED** (`ap_class`, `ap_instances`, 2026-10-04) `JumpScare_C` is a **pawn placed in each level**, not a hub object: `ap_instances JumpScare_C` found
  `/Game/Scenes/Repair_Games/Repair_Bonnie_Game.Repair_Bonnie_Game:PersistentLevel.JumpScare_2` in Parts and Service Bonnie and nothing in the hub.
  `GalleryJumpScare_C` is not loaded in the hub (class not found, 0 instances). The class declares 93 functions; the interesting ones are `Jumpscare`,
  `TriggerKillState`, `Test`, `ReceiveBeginPlay`, per-enemy `*_Ref` / `FoxyRepairJumpscare` / `CaptainFoxyJumpscare` / `Glitchtrap` / `BonnyOpenFace` and two
  timelines (`PhantomJumpscareFade`); properties include `JumpscareSFX`, `JumpscareDelay`, `ResetLevelAfterScare?`, `IsNightmareMode`.
- **VERIFIED** (`ap_hookclass` on `JumpScare_C` + `ap_hookfn` on `LevelDefeat`, 2026-10-04) A real defeat in Parts and Service Bonnie runs, in this order:
  `JumpScare_C:BonnieWithEyeControl`, `JumpScare_C:TriggerKillState`, a few `ExecuteUbergraph_JumpScare` steps, then `LevelDefeat` about 4 s after the scare started,
  then the level reloads. So the jumpscare plays before `LevelDefeat`, and a direct `LevelDefeat` call skips it.
- **VERIFIED** Calling `JumpScare_C` functions from Lua on the level's object did not work: `BonnieWithEyeControl` returned without visible effect, and
  `TriggerKillState` raised an error whose value is a function (with no argument, after `BonnieWithEyeControl`, and the probe never got to test arguments).
  `ap_class` shows 0 parameters for both. **UNVERIFIED** why. Parked; the experiment commands were removed.

### The gift box jumpscare (2026-10-06)

In the vanilla game the prize gift box you open after a minigame can hide a jumpscare instead of a reward. That is a game over.

- **PARTIAL** (one real event, `UE4SS.log` 2026-10-06 18:28 UTC, and the user's own account: two Bonnie defeats and one gift box defeat that session) It goes through the **same** hook as a normal defeat: `BP_FNAF_GameInstance_C:LevelDefeat` fired once and DeathLink sent (`[DEATHLINK] Level lost: death sent to the multiworld`), then the map went to `Level_GameOver` 2 s later, exactly as after a defeat inside a level.
  The difference is the map: the `[DIAG]` poll showed `Level_Victory` from 18:28:10 to 18:28:20 with no change in between, and `LevelDefeat` came at 18:28:18 (+8 s), with **no** `Prize award trigger fired!` (`AwardRandomPrize`) for that victory.
- **VERIFIED** (8 other victories in the same log) The prize is awarded on the map `Level_Victory`: `AwardRandomPrize` fires 4-6 s after it loads, the hub follows about 10-15 s later. A real defeat in a level shows `Repair_Bonnie_Game` -> `Level_GameOver`.
- **VERIFIED** (code) `Level_Victory` is not in `DeathLink.LEVEL_MAPS`, so an incoming DeathLink during the victory screen / prize box is already ignored.
- **HYPOTHESIS** A defeat on `Level_Victory` is always the gift box jumpscare, and every level type (nights, Pizza Party, hard variants) shows its prize box on that same map: only Parts and Service Bonnie has been seen, in two gift box events (2026-10-06 18:28 and 23:26 UTC).
- **VERIFIED** (in game, 2026-10-06 23:26 UTC) The mod's own map read inside the `LevelDefeat` hook gives `Level_Victory` for the gift box game over (log line `[DEATHLINK] Level lost on map 'Level_Victory', ...`) and `Repair_Bonnie_Game` for a defeat in the level.
  Background: the `SaveLevelVictory` log lines show `Map=''` because that hook uses its `self` argument, a `RemoteUnrealParam` (UE4SS documents that the first callback argument needs `:get()`); `death_link.lua` reads the map from the cached game instance instead and treats an empty or unreadable map as a normal defeat.
- **UNVERIFIED** Which game function runs only for the box scare (none found; `JumpScare_C` is placed in each level and nothing is known about `Level_Victory`). Not needed by the design.
- **Option** `death_link_gift_box` (default on = send, as before; off = the mod does not send a defeat on `Level_Victory`). Only sending changes; only with `death_link` on. The line `DEATH_LINK_GIFT_BOX 1|0` carries it (see [bridge-protocol.md](bridge-protocol.md)).
  **PARTIAL** Seen working once with the option off (2026-10-06 23:26 UTC, game and bridge folder): `[SESSION] DeathLink gift box jumpscare is NOT sent for this slot` at connect, the gift box game over logged `not sent: the prize box jumpscare (gift box) ...`, `ap_outbox.txt` got no `DEATHLINK` line for it, and a real defeat 26 s later was sent (`death sent`).
  **UNVERIFIED** the other player's side (that nothing arrived), the default `true` path with a gift box scare in the new code (the 18:28 scare was sent by the version before the option; tests cover `true`), and the other level types.

## Location group toggles (2026-10-10)

Player feedback: the prizes take a lot of grinding. Three independent yaml toggles, all default on (= every older yaml and room behaves as before):
`randomize_prizes` (57 locations), `randomize_faz_tokens` (30), `randomize_glitch_tapes` (16). **Decision (with the user): a group that is off is not randomized, it is vanilla.**

- **World** (offline tests + the real generator, see [testing.md](testing.md)): the group has no locations (ids stay in `LOCATION_TABLE`, never renumbered), no matching items (Glitch Tape ×16 with the tapes, the 30 base Faz Tokens with the tokens;
  "items follow locations", so the pool always fits: filler is `45 + 57*prizes - M` tokens for M unlock items), and the logic stops asking for them. Locations per combination: `50 + 57 prizes + 30 tokens + 16 tapes`
  (153 all on, 50 all off). The goals never become impossible: a tape or token requirement of a goal (`required_tapes`, `required_faz_tokens`, the 100 % goal's 16 tapes / 30 tokens, the Glitchtrap goals' tapes) leaves the logic
  when its group is off, and the 100 % goal's location list shrinks to the locations that exist. **VERIFIED in code** (`exact_hooks.lua`: completing Pizza Party sends the goal packet) that the game itself ends the multiworld
  on Pizza Party whatever `goal` says, so the `goal` option only changes what the generator requires; what the real game needs for a goal (30 coins, 16 tapes, ...) cannot be enforced by Archipelago either way.
- **Client**: a check for a location that is not in this multiworld is dropped everywhere (mod `LOCATION_CHECK` / `LOCATION_CHECK_NAME`, the save poll, the pending queue and the flush at connect). The set of locations that exist is the server's `checked_locations` + `missing_locations`
  of the `Connected` packet; without `missing_locations` nothing is filtered. **VERIFIED offline** with the real `BridgeCore`; **UNVERIFIED in a real room**. (From memory, the Archipelago server also ignores location ids it does not know; not needed and not checked.)
- **Mod**: one new inbox line, `RANDOMIZED_GROUPS prizes=1|0 faz_tokens=1|0 tapes=1|0`, in every connect block ([bridge-protocol.md](bridge-protocol.md)). With `tapes=0` `derived_counters.lua` returns nothing from the `GetGlitchCount` hook, with `faz_tokens=0` `faz_tokens.lua` leaves `GetCoinCount` / `GetTotalCoinCount` alone
  and puts the game's own `PlayerCoins` back. The hooks themselves still emit their checks; the client drops them. `connection_state.json` now carries `total_count` so the in-game panel shows the real total ("4 / 50") instead of 153.
- **VERIFIED in game** (the user tested each case in real rooms, 2026-10-10, and reports that prizes, Faz Tokens and tapes each turn on and off as intended; the statements below are what was checked): with `tapes` off the tape room shows the tapes picked up in the Archipelago save (it starts clean, so it shows none until a tape is picked up; the tape-room entrance flag question of "Tape room entrance" above is unchanged);
  with `faz_tokens` off the TV shows the tokens picked up; no `Faz Token` item is handed out (the filler is the new item `Faz Coupon`, code 60, no effect: the first version of the toggle still used Faz Token filler, and a real room handed out Faz Token items the vanilla TV ignored, 2026-10-10); prizes are still awarded by the game and nothing is sent.
- **Prize milestones on the TV / Prize Counter** (5/10/... coins, open item 8): counted by what the save poll sees. A prize whose save id is in `DEFAULT_PRIZE_MAP` is a prize check (obeys `randomize_prizes`); it is never a Faz Token check (those are `CollectedCoins` ids 1-30). Their award path is still the vanilla pickup: **UNVERIFIED**.
- Pre-existing and untouched (while the tokens ARE randomized): filler is `Faz Token`, so a default seed receives about 126 Faz Token items and the TV (which follows the item count) can read above 30; the three ungeneratable goals still fail for the reasons in [TODO.md](TODO.md) with tokens on
  (with tokens off the Faz Token requirement of `hundred_percent` / `token_tape_quota` disappears, see testing.md for what the generator did).
