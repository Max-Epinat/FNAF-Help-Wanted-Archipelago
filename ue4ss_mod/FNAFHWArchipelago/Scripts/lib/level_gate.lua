-- ==============================================================================
-- Archipelago authority over vanilla level unlocks.
--
-- The game asks BP_FNAF_GameInstance_C:IsLevelUnlocked(row) when drawing the night menus.
-- For a gated row, while an AP session is active, Archipelago decides: the row is unlocked if and only if its gate is
-- authorized in the CURRENT session, whatever the game computed (an item for FNAF 1 Night 3 unlocks it even when
-- Night 1 and Night 2 were never beaten, and a vanilla-open row without its item is locked).
-- Rows that are not gated, and every row while no AP session is active, keep the game's own answer.
-- We never touch SaveLevelVictory, so completing a level (and its location check) is unaffected.
--
-- VERIFIED in game (2026-10-03): in this hook (Blueprint function, callback runs AFTER the
-- function) `ReturnValue:set(false)` locks the night; returning false from the callback does not.
-- VERIFIED in game (2026-10-04): `ReturnValue:set(true)` on a vanilla-locked row opens it in the menu.
--
-- Authorization state lives only in memory and is dropped when the AP session id (seed_slot)
-- changes. It is never read from Playerarchi.sav.
-- ==============================================================================

local LevelGate = {}

local IS_LEVEL_UNLOCKED = "/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:IsLevelUnlocked"

-- LevelInfoTable row -> gate id. Row 5 = FNAF 1 Night 2 (rows verified from the game's
-- LevelInfoTable dump and from IsLevelUnlocked calls observed in game).
-- DEFAULT_ROWS is used until the client forwards slot_data["level_gates"] (GATE_TABLE line),
-- and again whenever the AP session changes, so a table never leaks across seeds.
LevelGate.DEFAULT_ROWS = {
    [5] = "FNAF1_NIGHT2",
}

local function copy_rows(rows)
    local out = {}
    for row, gate in pairs(rows) do out[row] = gate end
    return out
end

LevelGate.GATED_ROWS = copy_rows(LevelGate.DEFAULT_ROWS)

-- Pure parser for "5=FNAF1_NIGHT2,6=FNAF1_NIGHT3". Returns (rows, nil) or (nil, error).
function LevelGate.parse_table(spec)
    if type(spec) ~= "string" or spec == "" then
        return nil, "empty table"
    end
    local rows, count = {}, 0
    for pair in spec:gmatch("[^,]+") do
        local row, gate = pair:match("^%s*(%d+)=([A-Z0-9_]+)%s*$")
        if not row then
            return nil, "bad entry '" .. pair .. "'"
        end
        rows[tonumber(row)] = gate
        count = count + 1
    end
    if count == 0 then
        return nil, "empty table"
    end
    return rows, nil
end

function LevelGate.set_table(spec)
    local rows, err = LevelGate.parse_table(spec)
    if not rows then
        print(string.format("[WARN] [SESSION] Level gate table rejected (%s); keeping current table", tostring(err)))
        return false
    end
    LevelGate.GATED_ROWS = rows
    print("[SESSION] Level gate table set from slot_data: " .. spec)
    return true
end

-- Pure parser for "101000050=FNAF1_NIGHT2,101000051=FNAF1_NIGHT3" (item id -> gate id).
function LevelGate.parse_gate_items(spec)
    if type(spec) ~= "string" or spec == "" then
        return nil, "empty map"
    end
    local map, count = {}, 0
    for pair in spec:gmatch("[^,]+") do
        local item, gate = pair:match("^%s*(%d+)=([A-Z0-9_]+)%s*$")
        if not item then
            return nil, "bad entry '" .. pair .. "'"
        end
        map[tonumber(item)] = gate
        count = count + 1
    end
    if count == 0 then
        return nil, "empty map"
    end
    return map, nil
end

-- Pure parser for "101000002,101000011". An empty payload is a valid, empty list.
function LevelGate.parse_item_ids(spec)
    local ids = {}
    if spec == nil then return ids, nil end
    for token in tostring(spec):gmatch("[^,%s]+") do
        local n = tonumber(token)
        if not n then
            return nil, "bad item id '" .. token .. "'"
        end
        ids[#ids + 1] = n
    end
    return ids, nil
end

-- Pure: set of gate ids authorized by the given received item ids.
function LevelGate.gates_for_items(item_ids, gate_items)
    local gates = {}
    for _, id in ipairs(item_ids) do
        local gate = gate_items[id]
        if gate then gates[gate] = true end
    end
    return gates
end

-- Pure decision, no engine access. Returns (unlocked, reason).
function LevelGate.decide(row, vanilla_unlocked, session_active, authorized)
    local gate = LevelGate.GATED_ROWS[row]
    if not gate then
        return vanilla_unlocked, "not gated"
    end
    if not session_active then
        return vanilla_unlocked, "no AP session (vanilla behaviour)"
    end
    if authorized[gate] then
        if vanilla_unlocked then
            return true, "authorized"
        end
        return true, "authorized (vanilla prerequisite waived)"
    end
    return false, "denied"
end

local function describe(v)
    if v == nil then return "nil" end
    if type(v) == "userdata" then
        local ok, inner = pcall(function() return v:get() end)
        if ok and inner ~= nil then v = inner end
    end
    -- LevelID is an FName: it only becomes "5" through ToString (verified in game)
    if type(v) == "userdata" then
        local ok, str = pcall(function() return v:ToString() end)
        if ok and str ~= nil then return tostring(str) end
    end
    return tostring(v)
end

function LevelGate.init()
    -- item_authorized is derived from the server's received items (authoritative, replaced
    -- wholesale by every snapshot); debug_authorized holds manual console grants only.
    local state = {
        session_id = nil, item_ids = {}, gate_items = {},
        item_authorized = {}, debug_authorized = {}, logged = {},
    }
    local auth_view = setmetatable({}, {
        __index = function(_, gate)
            return state.item_authorized[gate] or state.debug_authorized[gate]
        end,
    })

    local function names(set)
        local list = {}
        for g in pairs(set) do list[#list + 1] = g end
        table.sort(list)
        return table.concat(list, ",")
    end

    local function recompute_item_authorization(reason)
        state.item_authorized = LevelGate.gates_for_items(state.item_ids, state.gate_items)
        state.logged = {}
        print(string.format("[ARCHI] Progression authorization from items (%s): %d items -> [%s]",
            reason, #state.item_ids, names(state.item_authorized)))
    end

    function LevelGate.set_gate_items(spec)
        local map, err = LevelGate.parse_gate_items(spec)
        if not map then
            print(string.format("[WARN] [SESSION] Gate item map rejected (%s); keeping current map", tostring(err)))
            return false
        end
        state.gate_items = map
        print("[SESSION] Gate item map set from slot_data: " .. spec)
        recompute_item_authorization("gate map changed")
        return true
    end

    function LevelGate.apply_items_snapshot(spec)
        local ids, err = LevelGate.parse_item_ids(spec)
        if not ids then
            print(string.format("[WARN] [SYNC] Received-items snapshot rejected (%s); keeping current authorization", tostring(err)))
            return false
        end
        state.item_ids = ids
        recompute_item_authorization("snapshot")
        return true
    end

    function LevelGate.on_session_sync(session_id)
        -- Every (re)connect re-sends the table and gate item map when slot_data has them, and always
        -- sends a received-items snapshot, so those are reset to defaults here. Without this, a table
        -- replayed from old inbox history would outlive a connect whose slot_data has none.
        LevelGate.GATED_ROWS = copy_rows(LevelGate.DEFAULT_ROWS)
        state.gate_items = {}
        if state.session_id ~= session_id then
            state.item_ids = {}
            state.item_authorized = {}
            state.debug_authorized = {}
            state.logged = {}
            print(string.format("[SESSION] Level gate: new AP session '%s' (was '%s'), authorizations cleared",
                tostring(session_id), tostring(state.session_id)))
        end
        state.session_id = session_id
    end

    function LevelGate.authorize(gate_id)
        state.debug_authorized[gate_id] = true
        state.logged = {}
        print("[ARCHI] Progression authorization GRANTED (debug): " .. gate_id)
    end

    function LevelGate.revoke(gate_id)
        state.debug_authorized[gate_id] = nil
        state.logged = {}
        print("[ARCHI] Progression authorization REVOKED (debug): " .. gate_id)
    end

    local hooked = false
    local function try_hook()
        if hooked or not RegisterHook then return end
        local ok = pcall(RegisterHook, IS_LEVEL_UNLOCKED, function(self, level_id, return_value)
            local okc, err = pcall(function()
                local row = tonumber(describe(level_id))
                local gate = row and LevelGate.GATED_ROWS[row]
                if not gate then return end
                local vanilla = (return_value:get() == true)
                local unlocked, reason = LevelGate.decide(row, vanilla, state.session_id ~= nil, auth_view)
                if unlocked ~= vanilla then
                    return_value:set(unlocked)
                end
                -- the menu polls constantly: log each distinct outcome once
                local key = gate .. tostring(vanilla) .. tostring(unlocked)
                if not state.logged[key] then
                    state.logged[key] = true
                    print(string.format("[GAME] Vanilla IsLevelUnlocked(%d) %s requested: vanilla=%s -> %s (%s)",
                        row, gate, tostring(vanilla), tostring(unlocked), reason))
                end
            end)
            if not okc then print("[ERROR] Level gate hook: " .. tostring(err)) end
        end)
        if ok then
            hooked = true
            print("[ARCHI] Level gate hook registered on IsLevelUnlocked")
        end
    end

    if LoopAsync then
        LoopAsync(1000, function()
            pcall(try_hook)
            return hooked
        end)
    end

    if RegisterConsoleCommandHandler then
        local function arg1(a1)
            if type(a1) == "table" then return a1[1] end
            return a1
        end
        -- Debug only, until an Archipelago item is chosen to authorize each gate.
        RegisterConsoleCommandHandler("ap_gate_grant", function(_, a1)
            LevelGate.authorize(arg1(a1) or "FNAF1_NIGHT2")
            return true
        end)
        RegisterConsoleCommandHandler("ap_gate_revoke", function(_, a1)
            LevelGate.revoke(arg1(a1) or "FNAF1_NIGHT2")
            return true
        end)
        RegisterConsoleCommandHandler("ap_gate_status", function()
            print(string.format("[ARCHI] Level gate: session=%s items=%d from_items=[%s] debug=[%s]",
                tostring(state.session_id), #state.item_ids, names(state.item_authorized), names(state.debug_authorized)))
            return true
        end)
    end

    print("[ARCHI] Level gate loaded (gated rows: FNAF1_NIGHT2). Debug: ap_gate_grant / ap_gate_revoke / ap_gate_status")
    return LevelGate
end

return LevelGate
