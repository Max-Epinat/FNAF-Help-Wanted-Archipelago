-- ==============================================================================
-- DeathLink.
--
-- DeathLink is opt-in per slot: the client tells the mod with "DEATH_LINK_MODE 1|0" and forwards deaths from other players as
-- "DEATHLINK <source>::<cause>".
--
-- SENDING (VERIFIED in game 2026-10-04): the game calls BP_FNAF_GameInstance_C:LevelDefeat (no arguments) exactly once when the
-- player loses a level. We report it to the client as "DEATHLINK <cause>" in the outbox. A death that the mod itself caused
-- (an incoming DeathLink) must never be sent back, and one defeat must not be sent twice.
-- The game over that follows the prize box jumpscare (the box you open after winning a minigame) goes through the same hook, but on the
-- map Level_Victory (HYPOTHESIS: one real event in the log of 2026-10-06, see docs/game-research.md). The slot option death_link_gift_box
-- ("DEATH_LINK_GIFT_BOX 1|0", on by default) decides whether that one is sent. It only matters while DeathLink is on, and never touches receiving.
--
-- RECEIVING (v1): an incoming death makes the player lose the level they are in, by calling BP_FNAF_GameInstance_C:LevelDefeat
-- (VERIFIED in game 2026-10-04: with our hook removed the call works and the game reacts like after a real defeat). Calling a hooked
-- function from Lua crashed the game before, so the hook is removed for the call and put back afterwards. Rules:
--   * only inside a level (the map is one of LEVEL_MAPS); in the hub / menus the death is ignored for now; the game's jumpscare is not played (see docs/game-research.md);
--   * deaths that were already in the inbox when the game started are history, never applied;
--   * one death at a time (cooldown), and the defeat we caused is not sent back.
-- The console commands `ap_dl_unhook` / `ap_dl_rehook` / `ap_dl_call <name>` / `ap_dl_kill` are for experiments and testing.
-- ==============================================================================

local DeathLink = {}

local GAME_INSTANCE = "/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:"
local DEFEAT_HOOK = GAME_INSTANCE .. "LevelDefeat"

-- Functions the experiment commands may call (by name, on the game instance). Anything else is refused.
DeathLink.CALLABLE = { LevelDefeat = true, DefeatLevel = true, LoadGameOver = true }

DeathLink.DEBOUNCE_SECONDS = 3      -- one defeat must not become two deaths
DeathLink.SUPPRESS_SECONDS = 10     -- after we made the player lose, the defeat that follows is ours, not theirs
DeathLink.DEFAULT_CAUSE = "lost a level"
DeathLink.APPLY_COOLDOWN_SECONDS = 10  -- at most one incoming death every this many seconds
DeathLink.REHOOK_DELAY_MS = 2000       -- how long after the forced defeat the hook goes back

-- The maps of the playable levels (locations.json minus the finale). A test keeps this in sync with that file.
DeathLink.LEVEL_MAPS = {
    Flashlight_Game_Ver_1_Bigger = true, Flashlight_Game_Ver_2 = true, Funtime_Foxy = true,
    NightGuard_Office01 = true, NightGuard_Office02 = true, NightGuard_Office03 = true,
    NightTerror_CircusBaby = true, NightTerror_Fredbear = true, NightTerror_FunTime_Freddy = true, NightTerror_Nightmarionne = true,
    Repair_Bonnie_Game = true, Repair_Chica_Game = true, Repair_Foxy_Game = true, Repair_Freddy_Game = true,
    Vent_Game_Ennard_2 = true, Vent_Game_Mangle_1 = true,
}

-- The map the prize box scare happens on: the screen shown after a win, where the prize is collected (the prize award fires there 4-6 s
-- after it loads). A defeat on it is the gift box jumpscare, never a lost level.
DeathLink.GIFT_BOX_MAPS = { Level_Victory = true }
-- Pure: "1" / "0" -> true / false (anything else: nil)
function DeathLink.parse_mode(spec)
    local value = tostring(spec or ""):match("^%s*([01])%s*$")
    if value == nil then return nil end
    return value == "1"
end

-- Pure: "Bob::fell into a pit" -> "Bob", "fell into a pit" (a missing cause gets a default)
function DeathLink.parse_death(spec)
    local text = tostring(spec or "")
    local source, cause = text:match("^(.-)::(.*)$")
    if not source then
        return (text ~= "" and text or "Someone"), "Died."
    end
    if source == "" then source = "Someone" end
    if cause == "" then cause = "Died." end
    return source, cause
end

-- Pure: should a defeat that was just observed be reported as a death? Returns (send, reason). `map_name` is the map the player was in
-- ("" or nil when unknown: then it is a normal defeat). A state without send_gift_box means "send".
function DeathLink.decide_send(state, now, map_name)
    if not state.enabled then
        return false, "DeathLink is off for this slot"
    end
    if now < (state.suppress_until or 0) then
        return false, "this defeat was caused by an incoming death"
    end
    if state.send_gift_box == false and DeathLink.GIFT_BOX_MAPS[tostring(map_name or "")] then
        return false, "the prize box jumpscare (gift box) is not sent for this slot"
    end
    if state.last_sent ~= nil and (now - state.last_sent) < DeathLink.DEBOUNCE_SECONDS then
        return false, "same defeat (debounced)"
    end
    return true, "the player lost a level"
end

-- Pure: should an incoming death be applied now? Returns (apply, reason).
function DeathLink.decide_apply(state, map_name, now, is_replay)
    if not state.enabled then
        return false, "DeathLink is off for this slot"
    end
    if is_replay then
        return false, "old death from before the game started"
    end
    if now < (state.apply_cooldown_until or 0) then
        return false, "another death was applied a moment ago"
    end
    if not DeathLink.LEVEL_MAPS[tostring(map_name or "")] then
        return false, "the player is not in a level (map '" .. tostring(map_name or "") .. "')"
    end
    return true, "the player is in a level"
end

-- params.send(cause)        report a death to the client (APBridge.send_deathlink)
-- params.now()              seconds, default os.time (injectable for tests)
-- params.current_map()      name of the map the player is in ("" when unknown)
-- params.game_instance()    the BP_FNAF_GameInstance_C object or nil
-- params.every(name, ms, fn) run fn periodically on the game thread (fn returning true stops it), default LoopAsync
-- params.on_game_thread(fn) run fn on the game thread (default ExecuteInGameThread, else immediately)
-- params.later(ms, fn)      run fn after a delay (default ExecuteWithDelay, else immediately)
function DeathLink.init(params)
    params = params or {}
    local send = params.send
    local now = params.now or os.time
    local current_map = params.current_map or function() return "" end
    local game_instance = params.game_instance or function()
        local ok, gi = pcall(FindFirstOf, "BP_FNAF_GameInstance_C")
        if ok and gi and gi:IsValid() then return gi end
        return nil
    end
    local every = params.every or function(_, ms, fn) if LoopAsync then LoopAsync(ms, fn) end end
    local on_game_thread = params.on_game_thread or (ExecuteInGameThread and function(fn) ExecuteInGameThread(fn) end) or function(fn) fn() end
    local later = params.later or (ExecuteWithDelay and function(ms, fn) ExecuteWithDelay(ms, fn) end) or function(_, fn) fn() end
    local state = {
        enabled = false, send_gift_box = true, suppress_until = 0, last_sent = nil, hook_ids = nil, user_unhooked = false,
        defeats_seen = 0, sent = 0, received = 0, applied = 0, apply_cooldown_until = 0,
    }

    function DeathLink.state() return state end

    function DeathLink.set_mode(spec)
        local enabled = DeathLink.parse_mode(spec)
        if enabled == nil then
            print("[WARN] [SESSION] DeathLink mode ignored: bad value '" .. tostring(spec) .. "'")
            return
        end
        state.enabled = enabled
        state.send_gift_box = true  -- every connect block repeats DEATH_LINK_GIFT_BOX right after this line; an older client never sends it
        print("[SESSION] DeathLink " .. (enabled and "ENABLED" or "disabled") .. " for this slot")
    end

    -- "DEATH_LINK_GIFT_BOX 1|0": whether the game over after the prize box jumpscare is sent as a death (1 = yes, the default).
    function DeathLink.set_gift_box_mode(spec)
        local send_it = DeathLink.parse_mode(spec)
        if send_it == nil then
            print("[WARN] [SESSION] DeathLink gift box mode ignored: bad value '" .. tostring(spec) .. "'")
            return
        end
        state.send_gift_box = send_it
        print("[SESSION] DeathLink gift box jumpscare " .. (send_it and "is sent" or "is NOT sent") .. " for this slot")
    end

    function DeathLink.is_enabled() return state.enabled end

    -- A level was lost (called from the LevelDefeat hook, also usable from tests).
    function DeathLink.on_defeat()
        state.defeats_seen = state.defeats_seen + 1
        local current = now()
        -- the map is only read while DeathLink is on (nothing new happens for a slot without it); unreadable = a normal defeat
        local map_name = ""
        if state.enabled then
            local okm, value = pcall(current_map)
            if okm and value ~= nil then map_name = tostring(value) end
        end
        local where = map_name ~= "" and (" on map '" .. map_name .. "'") or ""
        local ok, reason = DeathLink.decide_send(state, current, map_name)
        if not ok then
            print(string.format("[DEATHLINK] Level lost%s, not sent: %s", where, reason))
            return false
        end
        state.last_sent = current
        state.sent = state.sent + 1
        if send then send(DeathLink.DEFAULT_CAUSE) end
        print(string.format("[DEATHLINK] Level lost%s: death sent to the multiworld", where))
        return true
    end

    -- ---- applying an incoming death --------------------------------------------------------------------------------

    local register_hook

    -- Makes the player lose the level, on the game thread: remove our LevelDefeat hook, call LevelDefeat, put the hook back.
    -- Returns true when the request was queued.
    local function apply_defeat(why)
        on_game_thread(function()
            local gi = game_instance()
            if not gi then
                print("[DEATHLINK] Not applied: no game instance")
                return
            end
            local was_hooked = state.hook_ids ~= nil
            if was_hooked then
                local ok, err = pcall(UnregisterHook, DEFEAT_HOOK, state.hook_ids.pre, state.hook_ids.post)
                if not ok then
                    print("[WARN] [DEATHLINK] Not applied: could not remove the hook (" .. tostring(err) .. ")")
                    return
                end
                state.hook_ids = nil
            end
            state.suppress_until = now() + DeathLink.SUPPRESS_SECONDS
            local ok, err = pcall(function() gi:LevelDefeat() end)
            if ok then
                state.applied = state.applied + 1
                print("[DEATHLINK] Level lost on purpose (" .. tostring(why) .. ")")
            else
                print("[ERROR] [DEATHLINK] LevelDefeat failed: " .. tostring(err))
            end
            if was_hooked then
                later(DeathLink.REHOOK_DELAY_MS, function()
                    local okh, errh = pcall(register_hook)
                    if not okh then print("[ERROR] [DEATHLINK] could not hook LevelDefeat again: " .. tostring(errh)) end
                end)
            end
        end)
        return true
    end

    -- A death from another player. `is_replay` is true for lines that were already in the inbox when the game started.
    function DeathLink.on_incoming(spec, is_replay)
        local source, cause = DeathLink.parse_death(spec)
        state.received = state.received + 1
        local current = now()
        local map_name = current_map()
        local apply, reason = DeathLink.decide_apply(state, map_name, current, is_replay)
        if not apply then
            print(string.format("[DEATHLINK] Death from %s (%s) not applied: %s", source, cause, reason))
            return false
        end
        state.apply_cooldown_until = current + DeathLink.APPLY_COOLDOWN_SECONDS
        print(string.format("[DEATHLINK] Death received from %s (%s): the player loses this level (%s)", source, cause, map_name))
        return apply_defeat("DeathLink from " .. source)
    end

    -- ---- game hook ---------------------------------------------------------------------------------------------------

    function register_hook()
        -- the registration loop keeps running after it succeeded, so it must not undo a hook the user removed on purpose
        if state.hook_ids or state.user_unhooked or not RegisterHook then return false end
        local ok, pre_id, post_id = pcall(RegisterHook, DEFEAT_HOOK, function(self, ...)
            local okc, err = pcall(DeathLink.on_defeat)
            if not okc then print("[ERROR] DeathLink defeat hook: " .. tostring(err)) end
        end)
        if ok then
            state.hook_ids = { pre = pre_id, post = post_id }
            print("[DEATHLINK] watching LevelDefeat")
            return true
        end
        return false
    end

    every("deathlink_hook", 1000, function()
        local done = false
        pcall(function() done = register_hook() end)
        return done
    end)

    -- ---- experiment commands (console) ---------------------------------------------------------------------------------

    if RegisterConsoleCommandHandler then
        RegisterConsoleCommandHandler("ap_dl_status", function()
            print(string.format("[DEATHLINK] enabled=%s hooked=%s map='%s' defeats seen=%d sent=%d received=%d applied=%d suppress_for=%ds",
                tostring(state.enabled), tostring(state.hook_ids ~= nil), tostring(current_map()), state.defeats_seen, state.sent,
                state.received, state.applied, math.max(0, (state.suppress_until or 0) - now())))
            return true
        end)

        -- Test without a friend: behaves like an incoming death (level only, cooldown), even when DeathLink is off for the slot.
        RegisterConsoleCommandHandler("ap_dl_kill", function()
            local was_enabled = state.enabled
            state.enabled = true
            local applied = DeathLink.on_incoming("Console::ap_dl_kill test", false)
            state.enabled = was_enabled
            print("[DEATHLINK] ap_dl_kill: " .. (applied and "requested" or "nothing done, see the line above"))
            return true
        end)

        RegisterConsoleCommandHandler("ap_dl_unhook", function()
            if not state.hook_ids then
                print("[DEATHLINK] LevelDefeat is not hooked")
                return true
            end
            local ok, err = pcall(UnregisterHook, DEFEAT_HOOK, state.hook_ids.pre, state.hook_ids.post)
            if ok then
                state.hook_ids = nil
                state.user_unhooked = true
                print("[DEATHLINK] LevelDefeat unhooked. Remember `ap_dl_rehook` afterwards.")
            else
                print("[WARN] [DEATHLINK] could not unhook: " .. tostring(err))
            end
            return true
        end)

        RegisterConsoleCommandHandler("ap_dl_rehook", function()
            state.user_unhooked = false
            print(register_hook() and "[DEATHLINK] LevelDefeat hooked again" or "[DEATHLINK] LevelDefeat already hooked (or could not hook)")
            return true
        end)

        -- Experiment: call one whitelisted function on the game instance, from the console (game thread). Never while it is hooked.
        RegisterConsoleCommandHandler("ap_dl_call", function(_, parameters)
            local name = type(parameters) == "table" and parameters[1] or parameters
            if not name or not DeathLink.CALLABLE[name] then
                print("[DEATHLINK] usage: ap_dl_call <LevelDefeat|DefeatLevel|LoadGameOver>")
                return true
            end
            if state.hook_ids and name == "LevelDefeat" then
                print("[DEATHLINK] refused: LevelDefeat is hooked and calling a hooked function crashed the game before. Run ap_dl_unhook first.")
                return true
            end
            local gi = game_instance()
            if not gi then
                print("[DEATHLINK] no game instance yet")
                return true
            end
            state.suppress_until = now() + DeathLink.SUPPRESS_SECONDS  -- whatever this causes is not a death to report
            local ok, err = pcall(function() gi[name](gi) end)
            print(string.format("[DEATHLINK] called %s: %s", name, ok and "returned normally" or ("error: " .. tostring(err))))
            return true
        end)
    end

    print("[ARCHI] DeathLink loaded: sends a death when a level is lost, applies incoming deaths inside levels")
    return DeathLink
end

return DeathLink
