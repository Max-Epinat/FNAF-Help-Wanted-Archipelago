-- ==============================================================================
-- Game-thread access and diagnostics.
--
-- Why this exists (crash analysis of 2026-10-04, see docs/game-research.md "Crashes"):
--   * LoopAsync runs its callback on a UE4SS worker thread, not on the game thread. The mod used to scan the whole object array
--     (FindFirstOf) and walk save sets from those threads, several times a second. A crash dump showed exactly that: a
--     worker thread inside the object-array scan, on an object that was being destroyed 2 s after a map load.
--   * So: timers only *schedule* from the worker thread and run their body through ExecuteInGameThread, and the game instance is
--     found once and cached (a scan happens only on the game thread, at most once every RESCAN_SECONDS while it is missing).
--
-- Everything is injectable so the logic runs in a plain Lua interpreter (tests/test_lua_logic.py).
-- ==============================================================================

local GameThread = {}

GameThread.RESCAN_SECONDS = 2        -- while no game instance is cached, scan at most this often
GameThread.HEARTBEAT_SECONDS = 60    -- "[DIAG]" status line
GameThread.MAX_ERROR_KINDS = 20      -- distinct loop errors logged (each once)
GameThread.GAME_INSTANCE_CLASS = "BP_FNAF_GameInstance_C"

-- params (all optional): find_first, in_game_thread, run_on_game_thread, loop_async, now
function GameThread.init(params)
    params = params or {}
    local find_first = params.find_first or FindFirstOf
    local in_game_thread = params.in_game_thread or IsInGameThread
    local run_on_game_thread = params.run_on_game_thread or ExecuteInGameThread
    local loop_async = params.loop_async or LoopAsync
    local now = params.now or os.time

    local self = {}
    local state = {
        instance = nil, last_scan = -math.huge, scans = 0,
        started = now(), loops = {}, loop_order = {}, error_kinds = 0, errors_seen = {}, job_seen = false,
    }

    -- May the object array be scanned from the calling thread? With IsInGameThread the answer is exact. Without it (not every
    -- UE4SS build has it) a scan waits until a job has actually run on the game thread, which also keeps the call that
    -- exact_hooks makes while the mod is still loading (some other thread) from scanning.
    local function scan_allowed()
        if in_game_thread then return in_game_thread() end
        return state.job_seen
    end

    function self.uptime()
        return now() - state.started
    end

    -- The BP_FNAF_GameInstance_C object, or nil. Cheap when cached. Never scans from a thread other than the game thread.
    function self.game_instance()
        local cached = state.instance
        if cached then
            local ok, valid = pcall(function() return cached:IsValid() end)
            if ok and valid then return cached end
            state.instance = nil
        end
        if not find_first then return nil end
        if not scan_allowed() then return nil end
        local t = now()
        if t - state.last_scan < GameThread.RESCAN_SECONDS then return nil end
        state.last_scan = t
        state.scans = state.scans + 1
        local ok, found = pcall(find_first, GameThread.GAME_INSTANCE_CLASS)
        if ok and found then
            local okv, valid = pcall(function() return found:IsValid() end)
            if okv and valid then
                state.instance = found
                return found
            end
        end
        return nil
    end

    -- Run fn every `ms` milliseconds on the game thread. fn returning true stops the loop. A tick is skipped (not queued) while the
    -- previous one has not run yet, so a stalled game thread (loading screen) cannot build up a backlog. Errors are logged once each.
    function self.every(name, ms, fn)
        local loop = { name = name, runs = 0, skipped = 0, pending = false, stopped = false }
        state.loops[name] = loop
        state.loop_order[#state.loop_order + 1] = name

        local function body()
            if run_on_game_thread then state.job_seen = true end
            local ok, result = pcall(fn)
            loop.pending = false
            loop.runs = loop.runs + 1
            if not ok then
                local message = tostring(result)
                if not state.errors_seen[message] and state.error_kinds < GameThread.MAX_ERROR_KINDS then
                    state.errors_seen[message] = true
                    state.error_kinds = state.error_kinds + 1
                    print(string.format("[ERROR] [LOOP] %s: %s", name, message))
                end
            elseif result == true then
                loop.stopped = true
            end
        end

        if not loop_async then return loop end
        loop_async(ms, function()
            if loop.stopped then return true end
            if loop.pending then
                loop.skipped = loop.skipped + 1
                return false
            end
            loop.pending = true
            if run_on_game_thread then
                run_on_game_thread(body)
            else
                body()
            end
            return loop.stopped
        end)
        return loop
    end

    function self.stats(map_name)
        local parts = {}
        for _, name in ipairs(state.loop_order) do
            local loop = state.loops[name]
            parts[#parts + 1] = string.format("%s=%d/%d", name, loop.runs, loop.skipped)
        end
        return string.format("[DIAG] up=%ds map='%s' lua=%dKB gi_scans=%d loops(runs/skipped): %s",
            self.uptime(), tostring(map_name or ""), math.floor(collectgarbage("count")), state.scans, table.concat(parts, " "))
    end

    -- Map changes (a crash 2 s after a map load is a clue) and a heartbeat line, both cheap. current_map() returns the map name or "".
    function self.start_diagnostics(current_map)
        local last_map, ticks = nil, 0
        self.every("diag", 1000, function()
            ticks = ticks + 1
            local map = current_map and current_map() or ""
            if map ~= last_map then
                print(string.format("[DIAG] map: '%s' -> '%s' (up %ds)", tostring(last_map or ""), map, self.uptime()))
                last_map = map
            end
            if ticks % GameThread.HEARTBEAT_SECONDS == 0 then
                print(self.stats(map))
            end
            return false
        end)
    end

    return self
end

return GameThread
