return function(env)
    local outbox_path = env.outbox_path
    local inbox_path = env.inbox_path
    local bridge_dir = env.bridge_dir
    local emitted_location_names = env.emitted_location_names
    local baseline_location_names = env.baseline_location_names or {}
    local on_item = env.on_item
    local on_session_sync = env.on_session_sync
    local on_gate_table = env.on_gate_table
    local on_gate_items = env.on_gate_items
    local on_received_snapshot = env.on_received_snapshot
    local on_applied_items = env.on_applied_items
    local on_death_link_mode = env.on_death_link_mode
    local on_death_link_gift_box = env.on_death_link_gift_box
    local on_randomized_groups = env.on_randomized_groups
    local on_save_slot = env.on_save_slot
    local on_deathlink = env.on_deathlink

    local function ensure_file(path)
        local f = io.open(path, "a+")
        if f then
            f:close()
        end
    end

    ensure_file(outbox_path)
    ensure_file(inbox_path)

    local function append_outbox(command)
        local f = io.open(outbox_path, "a")
        if not f then
            print("[FNAFHW AP] Cannot open outbox: " .. outbox_path)
            return
        end
        f:write(command .. "\n")
        f:close()
    end

    local function load_emitted_location_names_from_state(path)
        local f = io.open(path, "r")
        if not f then
            return 0
        end

        local body = f:read("*a") or ""
        f:close()

        if body == "" then
            return 0
        end

        local list_body = body:match('"checked_location_names"%s*:%s*%[(.-)%]')
        if list_body and list_body ~= "" then
            for location_name in list_body:gmatch('"(.-)"') do
                local cleaned = tostring(location_name or "")
                cleaned = cleaned:gsub('\\"', '"')
                if cleaned ~= "" and not emitted_location_names[cleaned] then
                    emitted_location_names[cleaned] = true
                end
            end
        end

        local base_body = body:match('"savegame_baseline"%s*:%s*%[(.-)%]')
        if base_body and base_body ~= "" then
            for location_name in base_body:gmatch('"(.-)"') do
                local cleaned = tostring(location_name or "")
                cleaned = cleaned:gsub('\\"', '"')
                if cleaned ~= "" and not baseline_location_names[cleaned] then
                    baseline_location_names[cleaned] = true
                end
            end
        end

        return 1
    end

    local function split_words(line)
        local words = {}
        for token in string.gmatch(line, "%S+") do
            table.insert(words, token)
        end
        return words
    end

    local APBridge = {
        status = "DISCONNECTED",
        last_message = "",
    }

    -- is_replay: the line was already in the inbox when the game started (history, not news)
    local function handle_inbox_line(line, is_replay)
        if line == "CONNECTED" then
            APBridge.status = "CONNECTED"
            print("[FNAFHW AP] Connected to Archipelago!")
            return
        end

        if line:sub(1, 5) == "PRINT" then
            print("[FNAFHW AP] " .. line:sub(7))
            return
        end

        if line:sub(1, 6) == "STATUS" then
            local parts = split_words(line)
            APBridge.status = parts[2] or "UNKNOWN"
            APBridge.last_message = line:sub(8 + #(parts[2] or ""))
            return
        end

        if line:sub(1, 8) == "SLOT_DATA" then
            return
        end

        -- must stay before the "ITEM" handler below, which matches by prefix
        if line:sub(1, 13) == "APPLIED_ITEMS" then
            if on_applied_items then
                on_applied_items(line:sub(15))
            end
            return
        end

        if line:sub(1, 17) == "RECEIVED_SNAPSHOT" then
            if on_received_snapshot then
                on_received_snapshot(line:sub(19))
            end
            return
        end

        if line:sub(1, 10) == "GATE_ITEMS" then
            if on_gate_items then
                on_gate_items(line:sub(12))
            end
            return
        end

        if line:sub(1, 4) == "ITEM" then
            local parts = split_words(line)
            local item_id = tonumber(parts[2] or "")
            local item_index = tonumber(parts[6] or "")
            if item_id and item_index then
                on_item(item_id, item_index)
            end
            return
        end

        if line:sub(1, 12) == "SESSION_SYNC" then
            print("[FNAFHW AP] Session sync received: " .. line:sub(14))
            if on_session_sync then
                on_session_sync(line:sub(14))
            end
            for k in pairs(emitted_location_names) do
                emitted_location_names[k] = nil
            end
            for k in pairs(baseline_location_names) do
                baseline_location_names[k] = nil
            end
            return
        end

        if line:sub(1, 10) == "GATE_TABLE" then
            if on_gate_table then
                on_gate_table(line:sub(12))
            end
            return
        end

        if line:sub(1, 16) == "SESSION_BASELINE" then
            local base_loc = line:sub(18):gsub("^%s+", ""):gsub("%s+$", "")
            if base_loc ~= "" then
                baseline_location_names[base_loc] = true
            end
            return
        end

        if line:sub(1, 15) == "CONFIRMED_CHECK" then
            local parts = split_words(line)
            local loc_id = tonumber(parts[2] or "")
            local loc_name = line:sub(17 + #(parts[2] or ""))
            if loc_name and loc_name ~= "" then
                emitted_location_names[loc_name] = true
            end
            return
        end

        -- must stay before the DEATHLINK handler: all three start with DEATH
        if line:sub(1, 15) == "DEATH_LINK_MODE" then
            if on_death_link_mode then
                on_death_link_mode(line:sub(17))
            end
            return
        end

        if line:sub(1, 19) == "DEATH_LINK_GIFT_BOX" then
            if on_death_link_gift_box then
                on_death_link_gift_box(line:sub(21))
            end
            return
        end

        -- RANDOMIZED_GROUPS prizes=1 faz_tokens=0 tapes=1: which groups the slot randomizes. A key that is missing or not 0 / 1 stays "randomized"
        -- (what every version before the toggles did); a group that is not randomized is vanilla in game.
        if line:sub(1, 17) == "RANDOMIZED_GROUPS" then
            if on_randomized_groups then
                local groups = { prizes = true, faz_tokens = true, tapes = true }
                for key, value in line:sub(18):gmatch("(%a[%w_]*)=(%S*)") do
                    if groups[key] ~= nil then
                        if value == "0" then
                            groups[key] = false
                        elseif value == "1" then
                            groups[key] = true
                        end
                    end
                end
                on_randomized_groups(groups)
            end
            return
        end

        -- SAVE_SLOT Playerarchi_<seed>_<slot>: the save file (slot name, no .sav) of this multiworld. Without the line (an old client) the mod keeps
        -- using the shared Playerarchi. The name is checked where it is used (exact_hooks.lua).
        if line:sub(1, 9) == "SAVE_SLOT" then
            if on_save_slot then
                on_save_slot(line:sub(11))
            end
            return
        end

        if line:sub(1, 9) == "DEATHLINK" then
            print("[FNAFHW AP] " .. line)
            if on_deathlink then
                on_deathlink(line:sub(11), is_replay)
            end
            return
        end
    end

    -- Replay of the inbox at game launch. Every connect writes a self-contained block (CONNECTED, SESSION_SYNC, baseline,
    -- confirmed checks, DEATH_LINK_MODE, gate table/items, APPLIED_ITEMS, RECEIVED_SNAPSHOT: see docs/bridge-protocol.md), and
    -- SESSION_SYNC resets everything the blocks before it set. So only the last block (and what follows it) matters; replaying
    -- the whole history (hundreds of snapshots after a few sessions) only made the mod do hundreds of pointless state changes in
    -- the busiest second of startup. Returns the 1-based index of the first line to process (1 = all of them).
    local function replay_start(lines)
        local last_sync
        for i = #lines, 1, -1 do
            if lines[i]:sub(1, 12) == "SESSION_SYNC" then
                last_sync = i
                break
            end
        end
        if not last_sync then return 1 end
        if last_sync > 1 and lines[last_sync - 1] == "CONNECTED" then return last_sync - 1 end
        return last_sync
    end

    local inbox_position = 0
    local first_poll_done = false
    local function poll_inbox()
        local f = io.open(inbox_path, "r")
        if not f then
            return
        end

        -- the inbox is append-only and read from the start at every game launch: the first pass is history
        local is_replay = not first_poll_done
        local size = f:seek("end")
        if not is_replay and size == inbox_position then
            f:close()
            return
        end
        first_poll_done = true
        f:seek("set", inbox_position)
        local lines = {}
        for line in f:lines() do
            local trimmed = line:gsub("^%s+", ""):gsub("%s+$", "")
            if trimmed ~= "" then
                lines[#lines + 1] = trimmed
            end
        end
        inbox_position = f:seek()
        f:close()

        local first = 1
        if is_replay then
            first = replay_start(lines)
            if first > 1 then
                print(string.format("[SYNC] Inbox replay: skipped %d line(s) of older sessions, replaying the last connect (%d line(s))",
                    first - 1, #lines - first + 1))
            end
        end
        for i = first, #lines do
            handle_inbox_line(lines[i], is_replay)
        end
    end

    function APBridge.send_location_check(location_id)
        append_outbox("LOCATION_CHECK " .. tostring(location_id))
    end

    function APBridge.send_location_check_name(location_name)
        append_outbox("LOCATION_CHECK_NAME " .. tostring(location_name))
    end

    function APBridge.send_goal()
        append_outbox("GOAL")
    end

    function APBridge.sync()
        append_outbox("SYNC")
    end

    function APBridge.say(text)
        append_outbox("SAY " .. tostring(text))
    end

    function APBridge.send_deathlink(cause)
        append_outbox("DEATHLINK " .. tostring(cause or "Animatronic incident"))
    end

    function APBridge.append_outbox(command)
        append_outbox(command)
    end

    function APBridge.on_check_earned(location_name)
        local normalized = tostring(location_name or "")
        if normalized == "" then
            return
        end

        if emitted_location_names[normalized] then
            return
        end

        emitted_location_names[normalized] = true
        APBridge.send_location_check_name(normalized)
        print("[FNAFHW AP] Auto-earned check: " .. normalized)
    end

    local loaded_checked_location_names = load_emitted_location_names_from_state(bridge_dir .. "/ap_state.json")

    return {
        ensure_file = ensure_file,
        append_outbox = append_outbox,
        poll_inbox = poll_inbox,
        replay_start = replay_start,
        APBridge = APBridge,
        loaded_checked_location_names = loaded_checked_location_names,
        baseline_location_names = baseline_location_names,
    }
end
