-- ==============================================================================
-- Tape shelf (unique tapes, 2026-10-26): each tape item is one log, and the tape room shows exactly the logs received.
--
-- How the room works (read from the game's Blueprint code, docs/game-research.md "The tape room"):
--   * 16 shelf slots (AquiredLog_C), slot n has LogNumber n; when the room loads a slot stays only if LogNumber <= the tape count, else it
--     removes itself. derived_counters.lua makes that count the number of tape items received, so the room keeps slots 1..K.
--   * The tape player plays log <LogNumber of the slot> when the tape is played, and the label is a picture the label widget (TapeText_C)
--     picks from its integer Text in PreConstruct.
-- What this module does, on each room visit: the K kept slots get the K logs received, in shelf order, so there are no gaps: logs {2, 9}
-- -> slot 1 plays log 2, slot 2 log 9 (slot n gets the n-th log received).
-- When (2026-10-27): the job runs through game_thread.every_in_tape_room, the ONLY job allowed to run during the 0.4.2 pause after a map
-- change, and only while the map the diagnostics last saw is the tape room (never in the hub). Every 0.25 s; it waits WAIT_RUNS runs (at least
-- 0.5 s after the room was noticed), then makes at most PASSES passes (2 s) and stops early once every log is on the shelf.
-- Safety rule: a slot is touched only when its label widget exists and its Text already shows the slot's own LogNumber. Text is 0 until the
-- slot's SetupLog ran, and SetupLog runs only after the slot decided to stay (LogNumber <= the tape count). Relabelling a slot BEFORE that
-- decision would make it compare the new, higher number with the count and remove itself: the tape would be lost. Slots that remove
-- themselves never get a label number, so they are never touched either.
-- VERIFIED once in game (2026-10-26 probe, flat mode): LogNumber + the widget's Text + PreConstruct(false) relabelled a slot (TAPE #2 ->
-- TAPE #5) and it played log 5; ~10 s after the load FindAllOf still returned the slots that removed themselves, without a label widget
-- object. The user saw the feature work in a real room (2026-10-26) with the earlier ~5 s delay. HYPOTHESIS until seen in game: the new delay.
-- Side effect to know: for the first fraction of a second the shelf shows logs 1..K in plain order; playing a tape then can play a log not
-- received. Playing a tape never sends a check (exact_hooks.lua), so checks are never affected.
-- Nothing is hooked here, no game function is called except on the label widget, and nothing touches the save.
-- ==============================================================================

local TapeShelf = {}

TapeShelf.FIRST_ITEM_ID = 101000061  -- "Glitch Tape #01 (Intro)" (item code 61, fnaf_help_wanted/data.py); log n = id - 101000060
TapeShelf.LOGS = 16
TapeShelf.OLD_TAPE_ITEM_ID = 101000001  -- the retired "Glitch Tape" (code 1) of rooms generated before unique tapes: ignored
TapeShelf.INTERVAL_MS = 250  -- how often the job runs while in the tape room
TapeShelf.WAIT_RUNS = 2  -- runs that only wait at the start of a visit: the first pass comes at least 0.5 s after the room was noticed
TapeShelf.PASSES = 8  -- then at most this many passes (2 s), fewer once every log is on the shelf

-- Pure: the log (1..16) of a tape item id, or nil.
function TapeShelf.log_of_item(item_id)
    local log = tonumber(item_id) and (tonumber(item_id) - TapeShelf.FIRST_ITEM_ID + 1)
    if log and log >= 1 and log <= TapeShelf.LOGS and log == math.floor(log) then return log end
    return nil
end

-- Pure: the logs of a received list "101000062,101000011,..." in order, each once; plus how many retired "Glitch Tape" items it holds.
-- Returns (logs, old_count, nil) or (nil, 0, error).
function TapeShelf.received_logs(spec)
    local have, old = {}, 0
    for token in tostring(spec or ""):gmatch("[^,%s]+") do
        local id = tonumber(token)
        if not id then return nil, 0, "bad item id '" .. token .. "'" end
        local log = TapeShelf.log_of_item(id)
        if log then have[log] = true end
        if id == TapeShelf.OLD_TAPE_ITEM_ID then old = old + 1 end
    end
    local logs = {}
    for log = 1, TapeShelf.LOGS do
        if have[log] then logs[#logs + 1] = log end
    end
    return logs, old, nil
end

-- params: every_in_tape_room(name, ms, fn(visit)) (game_thread.every_in_tape_room: the game thread, only in the tape room), find_all(class)
-- -> list (default FindAllOf).
function TapeShelf.init(params)
    params = params or {}
    local every_in_tape_room = params.every_in_tape_room
    local find_all = params.find_all or FindAllOf

    local state = { session_id = nil, logs = nil, randomized = true, old_warned = false, visit = nil, relabelled = 0 }

    local function active()
        return state.session_id ~= nil and state.randomized and state.logs ~= nil
    end

    local function label_of(slot)
        local ok, widget = pcall(function() return slot.Widget:GetUserWidgetObject() end)
        if not ok or widget == nil then return nil end
        local okv, valid = pcall(function() return widget:IsValid() end)
        if okv and valid then return widget end
        return nil
    end

    local function name_of(slot)
        local ok, name = pcall(function() return slot:GetFullName() end)
        return ok and tostring(name) or tostring(slot)
    end

    -- The slot's own number once it has set itself up (its label shows that number), else nil: such a slot is never touched.
    local function ready_number(slot, widget)
        local ok, n, text = pcall(function() return slot.LogNumber, widget.Text end)
        n, text = ok and tonumber(n), ok and tonumber(text)
        if n and text and n >= 1 and n == text then return n end
        return nil
    end

    -- One pass: every slot that is ready and not done yet gets its log (slot n -> the n-th log received). Returns how many logs are on the shelf.
    local function pass(visit)
        local ok, list = pcall(find_all, "AquiredLog_C")
        if not ok or type(list) ~= "table" then return visit.placed end
        for _, slot in ipairs(list) do
            local widget = label_of(slot)
            local key = widget and name_of(slot)
            local n = widget and not visit.done[key] and ready_number(slot, widget)
            if n then
                local log = state.logs[n]
                visit.done[key] = true
                if log == n then
                    visit.placed = visit.placed + 1
                elseif log then
                    local okr, err = pcall(function()
                        slot.LogNumber = log
                        widget.Text = log
                        widget:PreConstruct(false)  -- the label picture is chosen from Text here
                    end)
                    if okr then
                        visit.placed = visit.placed + 1
                        state.relabelled = state.relabelled + 1
                    else
                        print(string.format("[WARN] [ARCHI] Tape shelf: could not relabel %s as log %d: %s", key, log, tostring(err)))
                    end
                end  -- no log for this place (a forced count, more kept slots than logs): it keeps its number
            end
        end
        return visit.placed
    end

    if every_in_tape_room then
        every_in_tape_room("tape_shelf", TapeShelf.INTERVAL_MS, function(visit_id)
            if not state.visit or state.visit.id ~= visit_id then
                state.visit = { id = visit_id, runs = 0, passes = 0, placed = 0, done = {}, finished = false }
            end
            local visit = state.visit
            visit.runs = visit.runs + 1
            if visit.finished or visit.runs <= TapeShelf.WAIT_RUNS or not active() then return false end
            visit.passes = visit.passes + 1
            local wanted = math.min(#state.logs, TapeShelf.LOGS)
            local placed = pass(visit)
            if placed >= wanted or visit.passes >= TapeShelf.PASSES then
                visit.finished = true
                print(string.format("[ARCHI] Tape shelf: %d of %d log(s) on the shelf after %d pass(es)%s: %s", placed, wanted, visit.passes,
                    placed >= wanted and "" or " (stopped at the cap)", table.concat(state.logs, ",")))
            end
            return false
        end)
    end

    local self = {}

    function self.on_session_sync(session_id)
        if state.session_id ~= session_id then
            state.logs = nil
            state.old_warned = false
        end
        state.session_id = session_id
        state.randomized = true  -- every connect block says which groups are randomized right after this line
    end

    function self.set_randomized(value)
        state.randomized = value ~= false
    end

    -- spec: the whole received list (item ids, possibly empty)
    function self.on_snapshot(spec)
        local logs, old, err = TapeShelf.received_logs(spec)
        if not logs then
            print("[WARN] [SYNC] Tape shelf: bad snapshot ignored (" .. tostring(err) .. ")")
            return
        end
        if old > 0 and state.session_id ~= nil and not state.old_warned then
            state.old_warned = true
            print(string.format("[WARN] [ARCHI] This room hands out the old 'Glitch Tape' item (id %d), from before unique tapes: it is ignored "
                .. "and the tape room shows no tape for it. Regenerate the room with the current apworld.", TapeShelf.OLD_TAPE_ITEM_ID))
        end
        state.logs = logs
    end

    function self.status()
        local logs = (state.logs and #state.logs > 0) and table.concat(state.logs, ",") or "none"
        return string.format("session=%s randomized=%s logs=%s visit=%s passes=%d relabelled=%d", tostring(state.session_id),
            tostring(state.randomized), logs, tostring(state.visit and state.visit.id), state.visit and state.visit.passes or 0, state.relabelled)
    end

    if RegisterConsoleCommandHandler then
        RegisterConsoleCommandHandler("ap_tape_shelf_status", function()
            print("[ARCHI] Tape shelf: " .. self.status())
            return true
        end)
    end

    return self
end

return TapeShelf
