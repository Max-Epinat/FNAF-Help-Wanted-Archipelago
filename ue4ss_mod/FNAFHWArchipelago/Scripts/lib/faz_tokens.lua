-- Faz Token effect as derived state (HYPOTHESIS under test, see docs/game-research.md).
--
-- The game derives its coin count from the CollectedCoins set; there is no stored counter to write.
-- So the effect of "Faz Token" items is to override the *result* of the count getters
-- (GetCoinCount on the game instance, GetTotalCoinCount on the save) with the number of Faz Token items
-- the server says we have, the same way level_gate.lua lowers IsLevelUnlocked.
--
-- Step 1 (this file now): observe the getters and allow a manual override (ap_coin_force N / off) to
-- prove that :set() on their return value changes what the game shows and what it unlocks.
-- Nothing is wired to items yet. These functions must never be called from Lua (hooked BP functions
-- crash the game); we only observe/override the calls the game makes.

local FazTokens = {}

FazTokens.ITEM_ID = 101000011

local GI = "/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C"
local SAVE = "/Game/ProductionAssets/Blueprints/Data/SaveGame/FNAFSaveGame.FNAFSaveGame_C"

local TARGETS = {
    { name = "GetCoinCount",         path = GI .. ":GetCoinCount",             override = true },
    { name = "GetTotalCoinCount",    path = SAVE .. ":GetTotalCoinCount",      override = true },
    { name = "UpdateCachedCoinCount", path = GI .. ":UpdateCachedCoinCount",   override = false },
}

local function describe(v)
    if v == nil then return "nil" end
    if type(v) == "userdata" then
        local ok, inner = pcall(function() return v:get() end)
        if ok and inner ~= nil then v = inner end
    end
    return tostring(v)
end

-- params (optional): every(name, ms, fn) runs fn periodically on the game thread (fn returning true stops it);
-- game_instance() returns the cached BP_FNAF_GameInstance_C or nil. main.lua passes lib/game_thread.lua's; the defaults are
-- the plain LoopAsync / FindFirstOf calls (used by the tests).
function FazTokens.init(params)
    params = params or {}
    local every = params.every or function(_, ms, fn) if LoopAsync then LoopAsync(ms, fn) end end
    local game_instance = params.game_instance or function()
        local ok, gi = pcall(FindFirstOf, "BP_FNAF_GameInstance_C")
        if ok and gi and gi:IsValid() then return gi end
        return nil
    end
    -- forced: debug override. items_count: Faz Token items in the server's list (nil until a snapshot).
    local state = { forced = nil, items_count = nil, session_id = nil, hooked = {}, logged = {}, calls = {} }

    -- The count the game must show: debug override, else the received Faz Token items while an AP
    -- session is active. nil = leave the vanilla value alone (no session: vanilla behaviour).
    local function effective()
        if state.forced ~= nil then return state.forced end
        if state.session_id ~= nil then return state.items_count end
        return nil
    end

    local function log_once(key, text)
        if not state.logged[key] then
            state.logged[key] = true
            print(text)
        end
    end

    local function try_hook(target)
        if state.hooked[target.name] or not RegisterHook then return end
        local ok = pcall(RegisterHook, target.path, function(self, ...)
            local args = { n = select("#", ...), ... }
            local okc, err = pcall(function()
                local n = args.n
                state.calls[target.name] = (state.calls[target.name] or 0) + 1
                local ret = args[1]
                local vanilla = describe(ret)
                if not target.override then
                    local shown = {}
                    for i = 1, n do shown[#shown + 1] = describe(args[i]) end
                    vanilla = table.concat(shown, ",")
                end
                local result = vanilla
                local want = effective()
                if target.override and want ~= nil and ret ~= nil then
                    ret:set(want)
                    result = tostring(want)
                end
                -- the UI polls: log each distinct outcome once
                log_once(target.name .. vanilla .. result, string.format(
                    "[GAME] %s observed: extra_args=%d vanilla=%s -> %s", target.name, n, vanilla, result))
            end)
            if not okc then print("[ERROR] Faz token hook " .. target.name .. ": " .. tostring(err)) end
        end)
        if ok then
            state.hooked[target.name] = true
            print("[ARCHI] Faz token hook registered on " .. target.name)
        end
    end

    local function all_hooked()
        for _, t in ipairs(TARGETS) do
            if not state.hooked[t.name] then return false end
        end
        return true
    end

    every("faz_hooks", 1000, function()
        for _, t in ipairs(TARGETS) do pcall(try_hook, t) end
        return all_hooked()
    end)

    -- GameInstance.PlayerCoins is a plain IntProperty cache (verified readable, stale at 0 in the
    -- observed session). HYPOTHESIS under test: the prize counter compares it with Tokens_Needed_For_Unlock.
    local function write_cache(value)
        local ok, err = pcall(function()
            local gi = game_instance()
            if not gi then error("no game instance") end
            if state.original_cache == nil then state.original_cache = gi.PlayerCoins end
            if gi.PlayerCoins ~= value then
                gi.PlayerCoins = value
                print(string.format("[GAME] GameInstance.PlayerCoins -> %s", tostring(value)))
            end
        end)
        if not ok and not state.cache_warned then
            state.cache_warned = true
            print("[WARN] [GAME] Cannot write PlayerCoins yet: " .. tostring(err))
        end
    end

    local function refresh()
        state.logged = {}
        local want = effective()
        if want ~= nil then
            write_cache(want)
        elseif state.original_cache ~= nil then
            write_cache(state.original_cache)
            state.original_cache = nil
        end
    end

    function FazTokens.force(n)
        state.forced = n
        print("[ARCHI] Faz token count override (debug): " .. tostring(n))
        refresh()
    end

    function FazTokens.on_session_sync(session_id)
        if state.session_id ~= session_id then state.items_count = nil end
        state.session_id = session_id
        refresh()
    end

    -- spec: comma-separated item ids of the whole received list (possibly empty); replaces the count.
    function FazTokens.on_snapshot(spec)
        local count = 0
        for word in tostring(spec or ""):gmatch("[^,%s]+") do
            local id = tonumber(word)
            if not id then
                print("[WARN] [SYNC] Faz token count: bad snapshot ignored")
                return
            end
            if id == FazTokens.ITEM_ID then count = count + 1 end
        end
        if count ~= state.items_count then
            print(string.format("[ARCHI] Faz Token items received: %d (in-game coin count follows this)", count))
        end
        state.items_count = count
        refresh()
    end

    -- Re-assert the cache: the game rewrites PlayerCoins when it refreshes its own cache.
    every("faz_cache", 1000, function()
        local want = effective()
        if want ~= nil then write_cache(want) end
        return false
    end)

    function FazTokens.status()
        local parts = {}
        for _, t in ipairs(TARGETS) do
            parts[#parts + 1] = string.format("%s hooked=%s calls=%d", t.name,
                tostring(state.hooked[t.name] == true), state.calls[t.name] or 0)
        end
        local cached = "n/a"
        pcall(function()
            local gi = game_instance()
            if gi then cached = tostring(gi.PlayerCoins) end
        end)
        return string.format("forced=%s; items=%s; effective=%s; GameInstance.PlayerCoins=%s; %s",
            tostring(state.forced), tostring(state.items_count), tostring(effective()), cached,
            table.concat(parts, "; "))
    end

    if RegisterConsoleCommandHandler then
        RegisterConsoleCommandHandler("ap_coin_force", function(_, a1)
            local word = type(a1) == "table" and a1[1] or a1
            if word == nil or word == "off" then
                FazTokens.force(nil)
            else
                local n = tonumber(word)
                if not n then
                    print("[WARN] [ARCHI] Usage: ap_coin_force <number>|off")
                else
                    FazTokens.force(math.floor(n))
                end
            end
            return true
        end)
        RegisterConsoleCommandHandler("ap_coin_status", function()
            print("[ARCHI] Faz tokens: " .. FazTokens.status())
            return true
        end)
    end

    return FazTokens
end

return FazTokens
