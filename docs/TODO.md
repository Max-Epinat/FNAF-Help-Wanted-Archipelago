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

## To verify in game

- `hard_variants: separate` in a real room (generator-verified only).
- A new seed started while the normal save is a **completed** one: the clean-save generator resets tapes (collected and listened), coins, hub audio and
  eaten objects, and its output on a real 100 % save is correct offline, but the game has not yet loaded a save made that way. Tapes appearing and the
  game starting normally would close this (it also covers an empty `ObjectsEaten` set).
- The launcher client with **DeathLink** and with VR (flat mode is what was tested).
- Whether the TV milestone prizes (5, 10, ... coins) are pickup-time awards that a physical pickup should be blocked from granting. UNVERIFIED.
- Nightmare Mode License and the other items without a verified in-game effect (Glitch Tape, Prize Counter Key, traps).

## Ideas

- A `host.yaml` setting for the bridge folder, as an alternative to reading the mod's `config.lua`.
- Packaging the UE4SS install (it is currently checked and linked, never bundled).
- Retire the tkinter standalone client once the launcher client has been used for a while.
- A `CHANGELOG` and a tagged release workflow.

## Open issues

- One game run on a seed (2026-10-04) never acknowledged any item (`[SYNC] Item sync` / `ITEMS_APPLIED` missing for ~27 minutes). Cause unknown, not
  reproduced in later runs. If it returns: add a log line in `ItemSync.tick` and check `ap_items_status`.
- Prize locations: the mod's own prize poll cannot decode prize ids and is intentionally inert; the client's save poll is the real source.
- The `SaveLevelVictory` hook often cannot resolve the level row (`RowID=nil`); checks still arrive through the client's save poll. Root cause unknown.
- A crash between applying an item effect and the client persisting its acknowledgement can re-apply the last item once.
- The mod is inert (vanilla behaviour) when no `SESSION_SYNC` was received; there is no "offline" gating by design.
