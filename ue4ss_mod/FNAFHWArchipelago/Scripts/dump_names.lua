-- ============================================================
-- FNAF HW AP - Name Dumper Mod (standalone utility)
-- Captures map names, actor class names, prize actors, and
-- blueprint paths automatically as you play.
-- Deploy this INSTEAD of (or alongside) the AP mod temporarily.
--
-- Output file: ap_name_dump.txt  (next to this script)
-- Console commands:
--   ap_scan_world   - dump all current actors right now
--   ap_dump_clear   - clear the dump file
--   ap_dump_path    - print the path of the dump file
-- ============================================================

local MOD_VERSION = "1.0.0"

-- Find this script's directory
local source = debug.getinfo(1, "S").source
if source:sub(1, 1) == "@" then source = source:sub(2) end
source = source:gsub("\\", "/")
local mod_dir = source:match("^(.*)/[Ss]cripts/") or source:match("^(.*)/")
local dump_path = (mod_dir or ".") .. "/ap_name_dump.txt"

-- ── Helpers ────────────────────────────────────────────────

local function now_str()
    return os.date("%Y-%m-%d %H:%M:%S")
end

local function safe_str(v)
    local s = tostring(v or "")
    return s:gsub("[\n\r|]", " ")
end

local function write_line(line)
    local f = io.open(dump_path, "a")
    if f then
        f:write(line .. "\n")
        f:close()
    end
end

local function try_call(obj, method)
    if obj == nil then return nil end
    local m = obj[method]
    if type(m) ~= "function" then return nil end
    local ok, v = pcall(m, obj)
    return ok and v or nil
end

local function get_map_name()
    if not FindFirstOf then return "unknown" end
    for _, cls in ipairs({"World", "UWorld"}) do
        local ok, w = pcall(FindFirstOf, cls)
        if ok and w then
            -- strip UEDPIE prefix and path prefix
            local n = tostring(try_call(w, "GetName") or "")
            n = n:gsub("^UEDPIE_%d+_", "")
            n = n:gsub("^.+/", "")
            n = n:gsub("^.+%.", "")
            if n ~= "" then return n end
        end
    end
    return "unknown"
end

-- Dedup table so we don't write duplicate actor entries
local seen_actors = {}
local current_map = "unknown"
local last_map = "unknown"

-- ── Write header ───────────────────────────────────────────

write_line("===== FNAF HW Name Dump Started =====")
write_line("time=" .. now_str() .. " | version=" .. MOD_VERSION)
write_line("dump_path=" .. dump_path)
write_line("")
write_line("-- FORMAT: timestamp | event=<type> | map=<name> | class=<class> | name=<name> | full=<fullname> | path=<path>")
write_line("")

print("[DUMP] FNAF HW Name Dumper loaded. Output: " .. dump_path)
print("[DUMP] Commands: ap_scan_world | ap_dump_clear | ap_dump_path")

-- ── World/Actor dump function ──────────────────────────────

local function dump_actor(actor, event_type)
    if not actor then return end
    if actor.IsValid and not actor:IsValid() then return end

    local name     = safe_str(try_call(actor, "GetName"))
    local full     = safe_str(try_call(actor, "GetFullName"))
    local cls_obj  = try_call(actor, "GetClass")
    local cls_name = ""
    if cls_obj then
        cls_name = safe_str(try_call(cls_obj, "GetName"))
    end

    -- Build a unique key to avoid flooding with duplicates
    local key = cls_name .. "|" .. name
    if seen_actors[key] then return end
    seen_actors[key] = true

    local map = current_map
    local line = string.format(
        "%s | event=%s | map=%s | class=%s | name=%s | full=%s",
        now_str(), event_type, map, cls_name, name, full
    )
    write_line(line)
    print(string.format("[DUMP] %s  class=%s  name=%s", event_type, cls_name, name))
end

-- ── Hook every actor destroy (same as AP mod but logs everything) ──

local function try_hook(path)
    if not RegisterHook then return false end
    local ok, err = pcall(function()
        RegisterHook(path, function(...)
            local args = { ... }
            for _, arg in ipairs(args) do
                local obj = nil
                -- handle UE4SS param wrapper
                if type(arg) == "userdata" then
                    if arg.get then
                        local ok2, v = pcall(arg.get, arg)
                        if ok2 and v and v.IsValid and v:IsValid() then obj = v end
                    end
                    if not obj and arg.IsValid and arg:IsValid() then obj = arg end
                end
                if obj then
                    dump_actor(obj, "destroy")
                    break
                end
            end
        end)
    end)
    if ok then
        print("[DUMP] Hooked: " .. path)
        return true
    else
        print("[DUMP] Hook failed: " .. path .. " - " .. tostring(err))
        return false
    end
end

-- Hook actor destroy and begin-play so we catch both spawned and destroyed actors
try_hook("/Script/Engine.Actor:K2_DestroyActor")
try_hook("/Script/Engine.Actor:ReceiveBeginPlay")
try_hook("/Script/Engine.Actor:ReceiveEndPlay")

-- ── Map name poller ────────────────────────────────────────

local function poll_map()
    local map = get_map_name()
    if map == current_map then return end
    last_map = current_map
    current_map = map

    -- Reset dedup on map change so we catch actors in fresh levels
    seen_actors = {}

    local line = string.format(
        "%s | event=map_change | prev=%s | map=%s",
        now_str(), last_map, current_map
    )
    write_line(line)
    print("[DUMP] Map: " .. last_map .. " -> " .. current_map)
end

-- ── Full world scan (manual and auto) ─────────────────────

local function scan_all_actors_in_world()
    if not FindAllOf then
        print("[DUMP] FindAllOf not available")
        return 0
    end

    local count = 0
    -- Scan every Actor subclass we care about
    local classes_to_scan = {
        "Actor",
        "StaticMeshActor",
        "SkeletalMeshActor",
        "BlueprintGeneratedClass",
    }

    for _, cls in ipairs(classes_to_scan) do
        local ok, actors = pcall(FindAllOf, cls)
        if ok and actors then
            for _, actor in ipairs(actors) do
                local ok2, _ = pcall(function()
                    dump_actor(actor, "world_scan:" .. cls)
                    count = count + 1
                end)
                if not ok2 then end
            end
        end
    end

    write_line(string.format(
        "%s | event=world_scan_done | map=%s | actors_logged=%d",
        now_str(), current_map, count
    ))
    print(string.format("[DUMP] World scan done: %d actors logged to %s", count, dump_path))
    return count
end

-- ── Console commands ───────────────────────────────────────

if RegisterConsoleCommandHandler then
    RegisterConsoleCommandHandler("ap_scan_world", function()
        print("[DUMP] Scanning all current world actors...")
        scan_all_actors_in_world()
        return true
    end)

    RegisterConsoleCommandHandler("ap_dump_clear", function()
        local f = io.open(dump_path, "w")
        if f then
            f:write("===== FNAF HW Name Dump Cleared =====\n")
            f:write("time=" .. now_str() .. "\n\n")
            f:close()
            seen_actors = {}
            print("[DUMP] Dump file cleared: " .. dump_path)
        end
        return true
    end)

    RegisterConsoleCommandHandler("ap_dump_path", function()
        print("[DUMP] Dump file path: " .. dump_path)
        return true
    end)

    -- Scan all + dump map name
    RegisterConsoleCommandHandler("ap_dump_now", function()
        poll_map()
        scan_all_actors_in_world()
        return true
    end)

    print("[DUMP] Console commands registered: ap_scan_world, ap_dump_clear, ap_dump_path, ap_dump_now")
end

-- ── Polling loop ───────────────────────────────────────────

if LoopAsync then
    -- Poll map name every 500ms
    LoopAsync(500, function()
        local ok, err = pcall(poll_map)
        if not ok then
            -- silent - don't flood console
        end
    end)

    -- Auto-scan actors every 10s (catches things missed by hooks)
    LoopAsync(10000, function()
        local ok, err = pcall(function()
            local map = current_map
            -- Only scan on gameplay maps (not hub/menu to reduce noise)
            local lower = map:lower()
            local is_hub = lower:find("hub") or lower:find("menu") or lower:find("title")
                or lower:find("caveat") or lower:find("lobby")
            if not is_hub and map ~= "unknown" then
                scan_all_actors_in_world()
            end
        end)
    end)

    print("[DUMP] Polling loops started")
end

print("[DUMP] Ready. Play normally - all actor names will be recorded automatically.")
print("[DUMP] Use 'ap_dump_now' in console to force a snapshot at any time.")
