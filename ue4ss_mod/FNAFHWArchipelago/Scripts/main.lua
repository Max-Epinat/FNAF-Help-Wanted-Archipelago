-- ==============================================================================
-- FNAF: Help Wanted - Archipelago Multiworld Randomizer UE4SS Mod
-- Build: 2026-v2.0-exact-hooks-and-ui
-- ==============================================================================

local function file_exists(path)
    local f = io.open(path, "r")
    if f then
        f:close()
        return true
    end
    return false
end

-- Determine mod directory dynamically
local source = debug.getinfo(1, "S").source
if source:sub(1, 1) == "@" then
    source = source:sub(2)
end
source = source:gsub("\\", "/")

local mod_dir = source:match("^(.*)/[Ss]cripts/main.lua$")
if not mod_dir then
    local script_parent = source:match("^(.*)/main.lua$")
    if script_parent then
        mod_dir = script_parent:gsub("/[Ss]cripts$", "")
    end
end
if not mod_dir then
    mod_dir = "C:/Program Files (x86)/Steam/steamapps/common/FNAFVRHelpWanted/freddys/Binaries/Win64/Mods/FNAFHWArchipelago"
end

-- Bridge directory configuration
local config_path = mod_dir .. "/config.lua"
local bridge_dir = nil
local user_config = {}

if file_exists(config_path) then
    local ok, user_cfg = pcall(dofile, config_path)
    if ok and type(user_cfg) == "table" then user_config = user_cfg end
    if ok and type(user_cfg) == "table" and user_cfg.bridge_dir and user_cfg.bridge_dir ~= "" then
        bridge_dir = user_cfg.bridge_dir:gsub("\\", "/")
    end
end

if not bridge_dir or bridge_dir == "" or not file_exists(bridge_dir .. "/locations.json") then
    -- Check common relative locations or fallback
    local fallback_candidates = {
        bridge_dir,
        mod_dir .. "/../../../../bridge",
        mod_dir .. "/bridge",
    }
    for _, cand in ipairs(fallback_candidates) do
        if cand and cand ~= "" and file_exists(cand .. "/locations.json") then
            bridge_dir = cand:gsub("\\", "/")
            break
        end
    end
end

if not bridge_dir or bridge_dir == "" then
    bridge_dir = mod_dir .. "/bridge"
    print("[FNAFHW AP] [WARNING] config.lua not found or bridge_dir not set!")
    print("[FNAFHW AP] [WARNING] Please run scripts/install-mod.ps1 to configure automatically.")
end

local outbox_path = bridge_dir .. "/ap_outbox.txt"
local inbox_path  = bridge_dir .. "/ap_inbox.txt"

print("[FNAFHW AP] Initializing Archipelago Mod v2.0...")
print("[FNAFHW AP] Mod Directory   : " .. mod_dir)
print("[FNAFHW AP] Bridge Directory: " .. bridge_dir)

-- Load Locations Data
local locations_data = dofile(mod_dir .. "/Scripts/lib/locations_data.lua")
print(string.format("[FNAFHW AP] Loaded %d location mappings from locations_data.lua", locations_data.total_locations or 0))

local processed_item_indexes = {}
local emitted_location_names = {}
local exact_hooks = nil
local level_gate = nil
local item_sync = nil
local faz_tokens = nil
local death_link = nil

-- ITEM lines are informational only now: item effects are applied exactly once from the server's
-- full list by item_sync.lua (replayed inbox history must never re-apply them).
local function on_item(item_id, item_index)
    if processed_item_indexes[item_index] then
        return
    end
    processed_item_indexes[item_index] = true
    print(string.format("[FNAFHW AP] Received AP Item ID %d at index %d", item_id, item_index))
end

-- Load Bridge I/O
local bridge_io_builder = dofile(mod_dir .. "/Scripts/lib/bridge_io.lua")
local bridge_io = bridge_io_builder({
    outbox_path = outbox_path,
    inbox_path = inbox_path,
    bridge_dir = bridge_dir,
    emitted_location_names = emitted_location_names,
    on_item = on_item,
    on_session_sync = function(session_id)
        if level_gate then level_gate.on_session_sync(session_id) end
        if item_sync then item_sync.on_session_sync(session_id) end
        if faz_tokens then faz_tokens.on_session_sync(session_id) end
    end,
    on_gate_table = function(spec)
        if level_gate then level_gate.set_table(spec) end
    end,
    on_gate_items = function(spec)
        if level_gate then level_gate.set_gate_items(spec) end
    end,
    on_received_snapshot = function(spec)
        if level_gate then level_gate.apply_items_snapshot(spec) end
        if item_sync then item_sync.on_snapshot(spec) end
        if faz_tokens then faz_tokens.on_snapshot(spec) end
    end,
    on_applied_items = function(spec)
        if item_sync then item_sync.on_applied(spec) end
    end,
    on_death_link_mode = function(spec)
        if death_link then death_link.set_mode(spec) end
    end,
    on_deathlink = function(spec, is_replay)
        if death_link then death_link.on_incoming(spec, is_replay) end
    end,
})

APBridge = bridge_io.APBridge

-- Load In-Game Connection UI
local connection_ui_builder = dofile(mod_dir .. "/Scripts/lib/connection_ui.lua")
local connection_ui = connection_ui_builder.init({
    bridge_dir = bridge_dir,
    APBridge = APBridge,
    mod_dir = mod_dir,
})

-- Load Exact Event Hooks (SaveLevelVictory, UnlockCoin, etc.)
local exact_hooks_builder = dofile(mod_dir .. "/Scripts/lib/exact_hooks.lua")
exact_hooks = exact_hooks_builder.init({
    APBridge = APBridge,
    locations_data = locations_data,
    emitted_location_names = emitted_location_names,
    baseline_location_names = bridge_io.baseline_location_names,
    mod_dir = mod_dir,
})

-- Archipelago authority over vanilla level unlocks (FNAF 1 Night 2 first)
local level_gate_ok, level_gate_or_err = pcall(function()
    return dofile(mod_dir .. "/Scripts/lib/level_gate.lua").init()
end)
if level_gate_ok then
    level_gate = level_gate_or_err
else
    print("[ERROR] Level gate failed to load: " .. tostring(level_gate_or_err))
end

-- DeathLink (sends a death when a level is lost, applies incoming ones inside levels, see lib/death_link.lua)
local death_link_ok, death_link_or_err = pcall(function()
    return dofile(mod_dir .. "/Scripts/lib/death_link.lua").init({
        send = function(cause) APBridge.send_deathlink(cause) end,
        current_map = function()
            if not exact_hooks or not exact_hooks.current_map_name then return "" end
            return exact_hooks.current_map_name()
        end,
    })
end)
if death_link_ok then
    death_link = death_link_or_err
else
    print("[ERROR] DeathLink failed to load: " .. tostring(death_link_or_err))
end

-- Research tools (console only, read-only): ap_scan / ap_watch, see lib/research_tools.lua.
-- Developer tools: off unless config.lua says enable_research_tools = true.
if user_config.enable_research_tools == true then
    local research_ok, research_err = pcall(function()
        return dofile(mod_dir .. "/Scripts/lib/research_tools.lua").init({ output_dir = mod_dir })
    end)
    if not research_ok then
        print("[ERROR] Research tools failed to load: " .. tostring(research_err))
    end
else
    print("[ARCHI] Research tools are off (enable_research_tools is not set in config.lua)")
end

-- Faz Token effect: the in-game coin count follows the Faz Token items received (derived state)
local faz_ok, faz_or_err = pcall(function()
    return dofile(mod_dir .. "/Scripts/lib/faz_tokens.lua").init()
end)
if faz_ok then
    faz_tokens = faz_or_err
else
    print("[ERROR] Faz tokens failed to load: " .. tostring(faz_or_err))
end

-- One-shot item effects, applied exactly once per item from the server's list (see item_sync.lua)
local item_sync_ok, item_sync_or_err = pcall(function()
    return dofile(mod_dir .. "/Scripts/lib/item_sync.lua").init({
        apply = function(item_id, index)
            if not (exact_hooks and exact_hooks.apply_received_item) then return false end
            return exact_hooks.apply_received_item(item_id, index) == true
        end,
        ack = function(count)
            APBridge.append_outbox("ITEMS_APPLIED " .. tostring(count))
        end,
    })
end)
if item_sync_ok then
    item_sync = item_sync_or_err
else
    print("[ERROR] Item sync failed to load: " .. tostring(item_sync_or_err))
end

-- Redirect default save slot to Playerarchi
pcall(function()
    if StaticFindObject then
        local cdo = StaticFindObject("/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.Default__BP_FNAF_GameInstance_C")
        if cdo and cdo:IsValid() then
            cdo.SaveSlotName = "Playerarchi"
            print("[FNAFHW AP] Set SaveSlotName='Playerarchi' on GameInstance CDO")
        end
    end
end)

-- Console Commands
if RegisterConsoleCommandHandler then
    -- UE4SS passes console arguments as a table of words (not a string)
    local function console_arg_string(arg)
        if type(arg) == "table" then
            return table.concat(arg, " ")
        end
        return arg ~= nil and tostring(arg) or ""
    end

    RegisterConsoleCommandHandler("ap_check_name", function(full_cmd, location_name)
        local name = console_arg_string(location_name)
        if name ~= "" then
            APBridge.send_location_check_name(name)
            print("[FNAFHW AP] Manual check requested: " .. name)
            return true
        end
        print("[FNAFHW AP] Usage: ap_check_name <Exact Location Name>")
        return false
    end)

    RegisterConsoleCommandHandler("ap_check_id", function(full_cmd, location_id)
        local id_num = tonumber(console_arg_string(location_id))
        if id_num then
            APBridge.send_location_check(id_num)
            print("[FNAFHW AP] Manual check requested: " .. tostring(id_num))
            return true
        end
        print("[FNAFHW AP] Usage: ap_check_id <Numeric Location ID>")
        return false
    end)

    RegisterConsoleCommandHandler("ap_items_status", function()
        if item_sync then
            local sid, applied, total = item_sync.status()
            print(string.format("[SYNC] Item sync: session=%s applied=%d of %d received", tostring(sid), applied, total))
        else
            print("[SYNC] Item sync is not loaded")
        end
        return true
    end)

    RegisterConsoleCommandHandler("ap_goal", function()
        APBridge.send_goal()
        print("[FNAFHW AP] Manual goal status sent")
        return true
    end)

    RegisterConsoleCommandHandler("ap_sync", function()
        APBridge.sync()
        print("[FNAFHW AP] Sent SYNC command to bridge")
        return true
    end)
end

-- Keybinds (F1 for Connection UI, F7 for Goal test)
if RegisterKeyBind and Key then
    RegisterKeyBind(Key.F7, function()
        APBridge.send_goal()
        print("[FNAFHW AP] Sent test goal")
    end)
end

-- Main Async Polling Loop (Checks inbox and checks safety net savegame state every 500ms)
if LoopAsync then
    LoopAsync(250, function()
        pcall(function()
            bridge_io.poll_inbox()
        end)
    end)

    -- SaveGame Safety Net every 2000ms
    LoopAsync(2000, function()
        pcall(function()
            if exact_hooks and exact_hooks.poll_savegame_state then
                exact_hooks.poll_savegame_state()
            end
        end)
    end)

    LoopAsync(1000, function()
        pcall(function()
            if item_sync then item_sync.tick() end
        end)
    end)

    print("[FNAFHW AP] Polling loops started.")
end

-- Safely register hooks on GameThread via LoopAsync
if LoopAsync then
    LoopAsync(1000, function()
        pcall(function()
            if exact_hooks and exact_hooks.try_register_all then
                exact_hooks.try_register_all()
            end
        end)
    end)
end

-- Notify bridge of mod presence
APBridge.sync()

print("[FNAFHW AP] FNAF HW Archipelago Mod Ready! Press F1 to open Connection Menu.")
