-- ==============================================================================
-- Derived counters: what the game SHOWS follows the items received, not the vanilla save.
--
-- Same pattern as faz_tokens.lua (which is VERIFIED in game for the coin count) and level_gate.lua: hook the getter the game calls and
-- override the *result* with `ReturnValue:set(n)`. Nothing is ever written to the save: its sets (CollectedGlitches, CollectedCoins, ...)
-- are the location state the client reads to send checks.
--
-- Counters (DEFINITIONS):
--   tapes   FNAFSaveGame_C:GetGlitchCount  <- number of "Glitch Tape" items received.
--           VERIFIED (2026-10-05, ap_hookfn): entering the tape area (map Cassete_DarkRoom) calls it 16 times; the hub does not.
--           VERIFIED (2026-10-05, in game, forced value): the hook receives NO parameters (log: "extra_args=0 vanilla=nil"), so there is
--           no return-value parameter to :set; but RETURNING the value from the callback works (UE4SS: a returned value overrides the
--           function's result). With 0 tapes in the save, `ap_counter_force tapes 2` made the tape room show 2 tapes and `off`
--           put it back to 0. A real room's `!getitem Glitch Tape` gave a tape too. NOT yet verified: several items, a reconnect, and which tapes the room shows.
--
-- While no Archipelago session is active (or its item list has not arrived yet) nothing is overridden: vanilla behaviour.
-- Hooked Blueprint functions must never be called from Lua (it crashed the game): we only override the calls the game makes.
-- ==============================================================================

local DerivedCounters = {}

local SAVE = "/Game/ProductionAssets/Blueprints/Data/SaveGame/FNAFSaveGame.FNAFSaveGame_C"

DerivedCounters.DEFINITIONS = {
    { name = "tapes", item_id = 101000001, targets = { SAVE .. ":GetGlitchCount" } },  -- item id: "Glitch Tape"
}

-- Pure: how many times `item_id` is in "101000001,101000011,101000001". An empty payload is a valid, empty list.
-- Returns (count, nil) or (nil, error).
function DerivedCounters.count_items(spec, item_id)
    local count = 0
    for token in tostring(spec or ""):gmatch("[^,%s]+") do
        local id = tonumber(token)
        if not id then
            return nil, "bad item id '" .. token .. "'"
        end
        if id == item_id then count = count + 1 end
    end
    return count, nil
end

-- "/Game/X/Y.Y_C:DoIt" -> "Y_C:DoIt"
local function short_name(path)
    return (tostring(path or ""):match("([^%./]+:[%w_]+)$")) or tostring(path)
end

local function describe(v)
    if v == nil then return "nil" end
    if type(v) == "userdata" or type(v) == "table" then
        local ok, inner = pcall(function() return v:get() end)
        if ok and inner ~= nil then v = inner end
    end
    return tostring(v)
end

-- params (optional): every(name, ms, fn) runs fn periodically on the game thread (fn returning true stops it), default LoopAsync;
-- definitions overrides DEFINITIONS (tests).
function DerivedCounters.init(params)
    params = params or {}
    local every = params.every or function(_, ms, fn) if LoopAsync then LoopAsync(ms, fn) end end
    local definitions = params.definitions or DerivedCounters.DEFINITIONS

    -- per counter: forced (debug override), items (count of its item in the server's list, nil until a snapshot), hooked paths, calls
    local state = { session_id = nil, counters = {}, order = {}, logged = {} }
    for _, def in ipairs(definitions) do
        -- randomized: false when the slot did not randomize this group (RANDOMIZED_GROUPS): the game then keeps its own, vanilla, number
        state.counters[def.name] = { def = def, forced = nil, items = nil, randomized = true, hooked = {}, calls = 0 }
        state.order[#state.order + 1] = def.name
    end

    -- The value the game must show, or nil = leave the vanilla value alone.
    local function effective(counter)
        if counter.forced ~= nil then return counter.forced end
        if not counter.randomized then return nil end
        if state.session_id ~= nil then return counter.items end
        return nil
    end

    local function log_once(key, text)
        if not state.logged[key] then
            state.logged[key] = true
            print(text)
        end
    end

    local function try_hook(counter, path)
        if counter.hooked[path] or not RegisterHook then return end
        local ok = pcall(RegisterHook, path, function(self, ...)
            local args = { n = select("#", ...), ... }
            local returned = nil
            local okc, err = pcall(function()
                counter.calls = counter.calls + 1
                local ret = args[1]
                local vanilla = describe(ret)
                local want = effective(counter)
                local result = vanilla
                if want ~= nil and ret ~= nil then
                    ret:set(want)
                    result = tostring(want)
                elseif want ~= nil then
                    -- No return-value parameter was handed to the hook (GetGlitchCount: extra_args=0). UE4SS documents that a value
                    -- RETURNED by the callback overrides the function's return value. VERIFIED in game on GetGlitchCount (the tape room
                    -- showed the forced number); it did NOT work for IsLevelUnlocked, which has a return-value parameter and needs :set.
                    returned = want
                    result = tostring(want) .. " (returned from the callback)"
                end
                -- the UI polls: log each distinct outcome once
                log_once(counter.def.name .. vanilla .. result, string.format(
                    "[GAME] %s observed (%s): extra_args=%d vanilla=%s -> %s",
                    counter.def.name, short_name(path), args.n, vanilla, result))
            end)
            if not okc then print("[ERROR] Derived counter hook " .. counter.def.name .. ": " .. tostring(err)) end
            return returned
        end)
        if ok then
            counter.hooked[path] = true
            print("[ARCHI] Derived counter '" .. counter.def.name .. "' hooked on " .. path)
        end
    end

    local function all_hooked()
        for _, name in ipairs(state.order) do
            local counter = state.counters[name]
            for _, path in ipairs(counter.def.targets) do
                if not counter.hooked[path] then return false end
            end
        end
        return true
    end

    every("derived_counter_hooks", 1000, function()
        for _, name in ipairs(state.order) do
            local counter = state.counters[name]
            for _, path in ipairs(counter.def.targets) do pcall(try_hook, counter, path) end
        end
        return all_hooked()
    end)

    local self = {}

    function self.on_session_sync(session_id)
        if state.session_id ~= session_id then
            for _, name in ipairs(state.order) do state.counters[name].items = nil end
        end
        -- every connect block starts with SESSION_SYNC and then says which groups are randomized, so this is the default until that line
        for _, name in ipairs(state.order) do state.counters[name].randomized = true end
        state.session_id = session_id
        state.logged = {}
    end

    -- A group the slot does not randomize (e.g. no tape locations and no Glitch Tape items) is vanilla: stop overriding what the game shows.
    -- Returns false for a counter that does not exist.
    function self.set_randomized(name, value)
        local counter = state.counters[name]
        if not counter then return false end
        local randomized = value ~= false
        if counter.randomized ~= randomized then
            print(string.format("[ARCHI] Derived counter '%s': %s", name,
                randomized and "randomized (the game shows the item count)" or "NOT randomized (vanilla: the game shows its own count)"))
        end
        counter.randomized = randomized
        state.logged = {}
        return true
    end

    -- spec: comma-separated item ids of the whole received list (possibly empty); replaces every counter's count.
    function self.on_snapshot(spec)
        local counts = {}
        for _, name in ipairs(state.order) do
            local count, err = DerivedCounters.count_items(spec, state.counters[name].def.item_id)
            if not count then
                print("[WARN] [SYNC] Derived counters: bad snapshot ignored (" .. tostring(err) .. ")")
                return
            end
            counts[name] = count
        end
        for _, name in ipairs(state.order) do
            local counter = state.counters[name]
            if counts[name] ~= counter.items then
                print(string.format("[ARCHI] Derived counter '%s': %d item(s) received (the game shows this number)", name, counts[name]))
            end
            counter.items = counts[name]
        end
        state.logged = {}
    end

    function self.force(name, n)
        local counter = state.counters[name]
        if not counter then return false end
        counter.forced = n
        state.logged = {}
        print(string.format("[ARCHI] Derived counter '%s' override (debug): %s", name, tostring(n)))
        return true
    end

    function self.status()
        local parts = {}
        for _, name in ipairs(state.order) do
            local counter = state.counters[name]
            local hooked = 0
            for _ in pairs(counter.hooked) do hooked = hooked + 1 end
            parts[#parts + 1] = string.format("%s: forced=%s items=%s randomized=%s effective=%s hooked=%d/%d calls=%d", name,
                tostring(counter.forced), tostring(counter.items), tostring(counter.randomized), tostring(effective(counter)), hooked, #counter.def.targets, counter.calls)
        end
        return table.concat(parts, "; ")
    end

    if RegisterConsoleCommandHandler then
        RegisterConsoleCommandHandler("ap_counter_force", function(_, a1, a2)
            local name, value
            if type(a1) == "table" then name, value = a1[1], a1[2] else name, value = a1, a2 end
            if not name or not state.counters[name] then
                print("[WARN] [ARCHI] Usage: ap_counter_force <" .. table.concat(state.order, "|") .. "> <number>|off")
                return true
            end
            if value == nil or value == "off" then
                self.force(name, nil)
            else
                local n = tonumber(value)
                if not n then
                    print("[WARN] [ARCHI] Usage: ap_counter_force <name> <number>|off")
                else
                    self.force(name, math.floor(n))
                end
            end
            return true
        end)
        RegisterConsoleCommandHandler("ap_counter_status", function()
            print("[ARCHI] Derived counters: " .. self.status())
            return true
        end)
    end

    return self
end

return DerivedCounters
