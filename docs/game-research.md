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
- **VERIFIED** The mod reads `ap_inbox.txt` from byte 0 at every launch (see [bridge-protocol.md](bridge-protocol.md)).
- **VERIFIED** The Lua prize poll (`check_and_award_prizes`) reads prize ids as raw pointer strings, so it never maps a prize; prize checks come from the client's save poll. It is deliberately left non-functional (see its comment) because decoding it would activate a second prize-check sender.
- **UNVERIFIED** Whether the Lua `SaveLevelVictory` hook can always resolve the row (it often logs `RowID=nil`); checks still arrive through the client's save poll.

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

