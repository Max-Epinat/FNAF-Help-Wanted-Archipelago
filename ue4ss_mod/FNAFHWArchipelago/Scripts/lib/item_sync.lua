-- ==============================================================================
-- One-shot item effects (Faz Token coin grants, ...) applied exactly once per item.
--
-- The server's full item list (RECEIVED_SNAPSHOT, in server index order) is the source of truth;
-- the client persists, per seed+slot session, how many of those items already had their effect
-- applied in the game (APPLIED_ITEMS). Only the items beyond that count are applied, in order,
-- and each success is reported back (ITEMS_APPLIED). When the game is not ready yet (no game
-- instance during startup) the apply fails and is simply retried on the next tick, so nothing is
-- lost to a startup race and nothing is applied twice by replayed inbox history or reconnects.
-- ==============================================================================

local ItemSync = {}

-- Pure: the items still to apply, in order. `applied` counts items by server order (0-based index).
function ItemSync.pending(applied, ids)
    local out = {}
    for i = applied + 1, #ids do
        out[#out + 1] = { index = i - 1, item_id = ids[i] }
    end
    return out
end

-- Pure: "5" -> 5, false ; "1 reset" -> 1, true ; invalid -> nil, error
function ItemSync.parse_applied(spec)
    local num, flag = tostring(spec or ""):match("^%s*(%d+)%s*(%a*)%s*$")
    if not num then
        return nil, "bad applied count '" .. tostring(spec) .. "'"
    end
    if flag ~= "" and flag ~= "reset" then
        return nil, "bad applied flag '" .. flag .. "'"
    end
    return tonumber(num), flag == "reset"
end

-- Pure: "101000002,101000011" -> {101000002, 101000011}; empty payload -> {}
function ItemSync.parse_item_ids(spec)
    local ids = {}
    for token in tostring(spec or ""):gmatch("[^,%s]+") do
        local n = tonumber(token)
        if not n then
            return nil, "bad item id '" .. token .. "'"
        end
        ids[#ids + 1] = n
    end
    return ids, nil
end

-- params.apply(item_id, index) -> true when the effect is in place, false to retry later
-- params.ack(count)            -> report "count items applied" to the client
function ItemSync.init(params)
    local apply, ack = params.apply, params.ack
    local state = { session_id = nil, applied = 0, ids = {}, last_fail_log = 0 }

    function ItemSync.on_session_sync(session_id)
        if state.session_id ~= session_id then
            state.session_id = session_id
            state.applied = 0
            state.ids = {}
            state.last_fail_log = 0
            print(string.format("[SESSION] Item sync: session '%s', applied count reset until the client reports it",
                tostring(session_id)))
        end
    end

    function ItemSync.on_applied(spec)
        local count, reset = ItemSync.parse_applied(spec)
        if not count then
            print("[WARN] [SYNC] Item sync ignored APPLIED_ITEMS: " .. tostring(reset))
            return
        end
        -- the client's count only goes down when it clamped it to a shorter server list
        if reset or count > state.applied then
            state.applied = count
        end
    end

    function ItemSync.on_snapshot(spec)
        local ids, err = ItemSync.parse_item_ids(spec)
        if not ids then
            print("[WARN] [SYNC] Item sync ignored snapshot: " .. tostring(err))
            return
        end
        state.ids = ids
    end

    function ItemSync.status()
        return state.session_id, state.applied, #state.ids
    end

    -- Apply what is pending; call periodically. Stops at the first item that cannot be applied yet.
    function ItemSync.tick()
        if state.session_id == nil then return end
        local progressed = false
        for _, item in ipairs(ItemSync.pending(state.applied, state.ids)) do
            local ok = apply(item.item_id, item.index)
            if not ok then
                local now = os.time()
                if now - state.last_fail_log >= 30 then
                    state.last_fail_log = now
                    print(string.format("[WARN] [GAME] Item %d (index %d) not applicable yet; will retry",
                        item.item_id, item.index))
                end
                break
            end
            state.applied = item.index + 1
            progressed = true
        end
        if progressed then
            ack(state.applied)
            print(string.format("[SYNC] Item sync: %d item(s) of this session applied", state.applied))
        end
    end

    return ItemSync
end

return ItemSync
