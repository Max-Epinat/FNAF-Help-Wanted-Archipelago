-- ==============================================================================
-- Research tools (console only). They never change the game: they only LOOK and LOG.
--
--   ap_class <class path>     list the functions (with a FLAGS line each) and properties of ONE class (its parents up to the engine ones) into
--                             <mod folder>/ap_class_<name>.txt, e.g. ap_class /Game/ProductionAssets/Blueprints/JumpScare.JumpScare_C
--   ap_instances <ClassName> [max]  list the live objects of one class (FindAllOf, first `max`, default 150), e.g. ap_instances JumpScare_C
--   ap_hookclass <class path> log every call (log only) of every function the class itself declares (engine parents, noisy and
--                             unsafe functions skipped). Lines look like "[WATCH] JumpScare_C:Jumpscare called (#1) args=1 [IntProperty=4]"
--                             (the first three calls also show how many parameters the hook received and their types and values).
--   ap_hookfn <function path> [force]  the same for one function, e.g. ap_hookfn /Game/.../BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:LevelDefeat
--                             Refuses the UNSAFE functions (see below) unless the second word is `force`.
--   ap_scan <word> [max]      list every object in the game whose full name contains <word> (case-insensitive), functions included,
--                             into <mod folder>/ap_scan_<word>.txt. WARNING: it walks ALL objects and froze the game for good in the hub
--                             (2026-10-04); prefer ap_class / ap_instances.
--   ap_watch <word> [max]     like ap_hookclass but finds the functions by walking ALL objects (can freeze the game, see ap_scan).
--   ap_watch_clear            remove those hooks again.
--   ap_watch_status           list what is watched and how often each fired.
--
-- Why: facts about the game are never guessed (see docs/game-research.md). These tools turn a question like "what plays the jumpscare?"
-- into a log line we can read.
-- ==============================================================================

local Research = {}

Research.DEFAULT_SCAN_MAX = 400
Research.DEFAULT_WATCH_MAX = 30
-- functions that run constantly would drown the log and cost frame time
Research.NOISY = { "tick", "timeline", "mouse", "hover", "blueprintupdateanimation", "receivedrawtick", "onpaint", "pre_construct" }

-- Functions that must not be hooked, even log-only. Hooking BP_FNAF_GameInstance_C with ap_hookclass (2026-10-05) made UE4SS log
-- "push_textproperty ... not supported" and "DelegateProperty not supported" and the screen stayed black when entering the tape
-- area (FadeOut -> FadeOutWithLevelLoad -> ExecuteUbergraph -> LoadCasetteRoom had all been hooked). UE4SS cannot hand text and
-- delegate parameters to Lua, and a hook on the level-loading / fade / latent-graph functions can break the flow they drive.
-- Matched against the function NAME only (the part after the colon), case-insensitive.
Research.UNSAFE = { "ubergraph", "fade", "load", "timer", "restart", "achievement", "instruction", "receiveinit", "spawnlevel", "caveat" }

-- Pure: case-insensitive plain substring test.
function Research.matches(text, keyword)
    if not text or not keyword or keyword == "" then return false end
    return tostring(text):lower():find(tostring(keyword):lower(), 1, true) ~= nil
end

-- Pure: "Function /Game/X/Y.Y_C:DoIt" -> "/Game/X/Y.Y_C:DoIt"; anything that is not a game function -> nil.
function Research.function_hook_path(full_name)
    local path = tostring(full_name or ""):match("^Function%s+(/Game/%S+:[%w_]+)$")
    return path
end

-- Pure: the short name of a hook path ("/Game/X/Y.Y_C:DoIt" -> "Y_C:DoIt").
function Research.short_name(path)
    return (tostring(path or ""):match("([^%./]+:[%w_]+)$")) or tostring(path)
end

-- Pure: functions that fire all the time are not worth watching.
function Research.is_noisy(path)
    local lowered = tostring(path or ""):lower()
    for _, word in ipairs(Research.NOISY) do
        if lowered:find(word, 1, true) then return true end
    end
    return false
end

-- Pure: functions whose hook can break the game's flow (level loading, fades, latent graphs, text/delegate parameters).
function Research.is_unsafe(path)
    local name = tostring(path or ""):match(":([%w_]+)$") or tostring(path or "")
    local lowered = name:lower()
    for _, word in ipairs(Research.UNSAFE) do
        if lowered:find(word, 1, true) then return true end
    end
    return false
end

-- Pure: EFunctionFlags (UE 4.23) as hex plus the names that matter when reading a signature. Only the hex is authoritative.
Research.FUNCTION_FLAGS = {
    { 0x400, "Native" }, { 0x800, "Event" }, { 0x2000, "Static" }, { 0x400000, "HasOutParms" },
    { 0x4000000, "BlueprintCallable" }, { 0x8000000, "BlueprintEvent" }, { 0x10000000, "BlueprintPure" }, { 0x40000000, "Const" },
}
function Research.describe_flags(flags)
    local n = tonumber(flags)
    if not n then return "?" end
    local names = {}
    for _, entry in ipairs(Research.FUNCTION_FLAGS) do
        if n % (entry[1] * 2) >= entry[1] then names[#names + 1] = entry[2] end
    end
    return string.format("0x%08X %s", n, table.concat(names, " "))
end

-- Pure: "args=2 [IntProperty=4, BoolProperty=true]" for the values a hook received (RemoteUnrealParam wrappers). Never raises:
-- a value that cannot be read is shown as <unreadable>.
function Research.describe_args(args, count)
    local parts = {}
    for i = 1, count do
        local param = args[i]
        local kind, value = "?", "<unreadable>"
        if param ~= nil then
            local okt, t = pcall(function() return param:type() end)
            if okt and t ~= nil then kind = tostring(t) end
            local okv, v = pcall(function() return param:get() end)
            if okv and v ~= nil then
                local oks, s = pcall(tostring, v)
                value = oks and s or "<unprintable>"
            end
        else
            value = "nil"
        end
        parts[#parts + 1] = kind .. "=" .. value
    end
    return string.format("args=%d [%s]", count, table.concat(parts, ", "))
end

-- Pure: a file-name-safe version of a search word.
function Research.safe_word(word)
    return (tostring(word or ""):gsub("[^%w_%-]", "_"))
end

-- params.output_dir       folder for the scan files (the mod folder)
-- params.write(path, txt) writes a file (default: io.open), injectable for tests
-- params.for_each         iterates all game objects (default: UE4SS ForEachUObject), injectable for tests
-- params.find_object      StaticFindObject (injectable), params.find_all  FindAllOf (injectable)
function Research.init(params)
    params = params or {}
    local output_dir = params.output_dir or "."
    local write = params.write or function(path, text)
        local handle = io.open(path, "w")
        if not handle then return false end
        handle:write(text)
        handle:close()
        return true
    end
    local for_each = params.for_each or ForEachUObject
    local find_object = params.find_object or StaticFindObject
    local find_all = params.find_all or FindAllOf
    local state = { watched = {}, order = {} }

    -- Collects up to `max` matching full names. Returns the list and how many objects were looked at.
    local function collect(keyword, max)
        local found, seen_names, looked = {}, {}, 0
        if not for_each then return found, looked, "ForEachUObject is not available in this UE4SS version" end
        local ok, err = pcall(for_each, function(object)
            looked = looked + 1
            if #found >= max then return end
            local good, full = pcall(function() return object:GetFullName() end)
            if good and full and Research.matches(full, keyword) and not seen_names[full] then
                seen_names[full] = true
                found[#found + 1] = tostring(full)
            end
        end)
        if not ok then return found, looked, tostring(err) end
        return found, looked, nil
    end

    function Research.scan(keyword, max)
        max = tonumber(max) or Research.DEFAULT_SCAN_MAX
        if not keyword or keyword == "" then
            print("[RESEARCH] usage: ap_scan <word> [max]")
            return nil
        end
        local found, looked, err = collect(keyword, max)
        if err then
            print("[WARN] [RESEARCH] scan failed: " .. err)
            return nil
        end
        table.sort(found)
        local path = output_dir .. "/ap_scan_" .. Research.safe_word(keyword) .. ".txt"
        local functions = 0
        for _, full in ipairs(found) do
            if full:find("^Function ") then functions = functions + 1 end
        end
        write(path, string.format("# ap_scan '%s': %d match(es) in %d objects (max %d), %d of them functions\n%s\n",
            keyword, #found, looked, max, functions, table.concat(found, "\n")))
        print(string.format("[RESEARCH] '%s': %d match(es) (%d functions) among %d objects -> %s", keyword, #found, functions, looked, path))
        for i = 1, math.min(8, #found) do print("[RESEARCH]   " .. found[i]) end
        return found
    end

    local function full_name_of(object)
        local ok, name = pcall(function() return object:GetFullName() end)
        return ok and tostring(name) or "?"
    end

    -- Functions and properties of one class and its parents (stops at the engine classes under /Script/). Cheap: no object walk.
    function Research.class_info(class_path)
        if not class_path or class_path == "" then
            print("[RESEARCH] usage: ap_class <class path>, e.g. ap_class /Game/ProductionAssets/Blueprints/JumpScare.JumpScare_C")
            return nil
        end
        if not find_object then
            print("[WARN] [RESEARCH] StaticFindObject is not available")
            return nil
        end
        local ok, class = pcall(find_object, class_path)
        if not ok or not class or not class.IsValid or not class:IsValid() then
            print("[RESEARCH] class not found (not loaded yet?): " .. tostring(class_path))
            return nil
        end
        local lines = { "# ap_class " .. class_path }
        local functions, properties = 0, 0
        local current, guard = class, 0
        while current and guard < 12 do
            guard = guard + 1
            local name = full_name_of(current)
            lines[#lines + 1] = "CLASS " .. name
            pcall(function()
                current:ForEachFunction(function(fn)
                    functions = functions + 1
                    lines[#lines + 1] = "  FUNCTION " .. full_name_of(fn)
                    -- Lua's UFunction has only GetFunctionFlags (no ForEachProperty: that is UStruct), so the signature itself cannot be
                    -- listed; ap_hookfn shows what a hook really receives. HasOutParms / Const / BlueprintPure help to read it.
                    pcall(function()
                        lines[#lines + 1] = "    FLAGS " .. Research.describe_flags(fn:GetFunctionFlags())
                    end)
                end)
            end)
            pcall(function()
                current:ForEachProperty(function(prop)
                    properties = properties + 1
                    lines[#lines + 1] = "  PROPERTY " .. full_name_of(prop)
                end)
            end)
            if name:find("/Script/", 1, true) then break end
            local sok, super = pcall(function() return current:GetSuperStruct() end)
            if not sok or not super or not super.IsValid or not super:IsValid() then break end
            current = super
        end
        local path = output_dir .. "/ap_class_" .. Research.safe_word(class_path:match("([%w_]+)$") or class_path) .. ".txt"
        write(path, table.concat(lines, "\n") .. "\n")
        print(string.format("[RESEARCH] %s: %d function(s), %d property(ies) -> %s", class_path, functions, properties, path))
        for i = 2, math.min(40, #lines) do print("[RESEARCH]   " .. lines[i]) end
        return lines
    end

    -- Live objects of one class by its short name ("JumpScare_C").
    function Research.instances(class_name, max)
        max = tonumber(max) or 150
        if not class_name or class_name == "" then
            print("[RESEARCH] usage: ap_instances <ClassName> [max], e.g. ap_instances JumpScare_C")
            return nil
        end
        if not find_all then
            print("[WARN] [RESEARCH] FindAllOf is not available")
            return nil
        end
        local ok, objects = pcall(find_all, class_name)
        local names, total = {}, 0
        if ok and type(objects) == "table" then
            for _, object in ipairs(objects) do
                total = total + 1
                if #names < max then
                    local line = full_name_of(object)
                    -- the class path is what ap_class needs next
                    local okc, class_name = pcall(function() return object:GetClass():GetFullName() end)
                    if okc and class_name then line = line .. "   [class " .. tostring(class_name):gsub("^%S+%s+", "") .. "]" end
                    names[#names + 1] = line
                end
            end
        end
        print(string.format("[RESEARCH] %d live object(s) of %s%s", total, class_name,
            total > #names and string.format(" (showing the first %d)", #names) or ""))
        for _, name in ipairs(names) do print("[RESEARCH]   " .. name) end
        return names
    end

    local function hook_one(path)
        if state.watched[path] or not RegisterHook then return false end
        local entry = { count = 0 }
        local ok, pre, post = pcall(RegisterHook, path, function(self, ...)
            entry.count = entry.count + 1
            -- the first calls tell the story; after that only occasionally, so a busy function cannot flood the log
            if entry.count <= 3 or entry.count % 50 == 0 then
                local detail = ""
                if entry.count <= 3 then
                    local args = { ... }
                    local okd, text = pcall(Research.describe_args, args, select("#", ...))
                    detail = okd and (" " .. text) or ""
                end
                print(string.format("[WATCH] %s called (#%d)%s", Research.short_name(path), entry.count, detail))
            end
        end)
        if not ok then return false end
        entry.pre, entry.post = pre, post
        state.watched[path] = entry
        state.order[#state.order + 1] = path
        return true
    end

    function Research.hook_function(path, force)
        if not path or path == "" then
            print("[RESEARCH] usage: ap_hookfn </Game/.../Class.Class_C:Function> [force]")
            return false
        end
        if Research.is_unsafe(path) and force ~= "force" then
            print("[RESEARCH] refused: " .. path .. " drives level loading, fades or text/delegate parameters, and hooking such functions blacked out the screen. Add the word `force` to hook it anyway.")
            return false
        end
        local ok = hook_one(path)
        print(string.format("[RESEARCH] %s %s", ok and "watching" or "not hooked (already watched or not found):", path))
        return ok
    end

    -- Hooks (log only) the functions declared by the class itself. Cheap: no object walk.
    function Research.hook_class(class_path, max)
        max = tonumber(max) or 80
        if not class_path or class_path == "" then
            print("[RESEARCH] usage: ap_hookclass <class path>")
            return 0
        end
        local ok, class = pcall(find_object or function() end, class_path)
        if not ok or not class or not class.IsValid or not class:IsValid() then
            print("[RESEARCH] class not found (not loaded yet?): " .. tostring(class_path))
            return 0
        end
        local paths = {}
        pcall(function()
            class:ForEachFunction(function(fn)
                local path = Research.function_hook_path(full_name_of(fn))
                if path then paths[#paths + 1] = path end
            end)
        end)
        table.sort(paths)
        local added, skipped, unsafe = 0, 0, 0
        for _, path in ipairs(paths) do
            if Research.is_unsafe(path) then
                unsafe = unsafe + 1
            elseif Research.is_noisy(path) then
                skipped = skipped + 1
            elseif added < max and hook_one(path) then
                added = added + 1
            end
        end
        print(string.format("[RESEARCH] watching %d function(s) of %s (%d noisy and %d unsafe skipped). Do the action now, then read the [WATCH] lines.",
            added, class_path, skipped, unsafe))
        return added
    end

    function Research.watch(keyword, max)
        max = tonumber(max) or Research.DEFAULT_WATCH_MAX
        if not keyword or keyword == "" then
            print("[RESEARCH] usage: ap_watch <word> [max]")
            return 0
        end
        local found, _, err = collect(keyword, 100000)
        if err then
            print("[WARN] [RESEARCH] watch failed: " .. err)
            return 0
        end
        table.sort(found)
        local added, skipped = 0, 0
        for _, full in ipairs(found) do
            local path = Research.function_hook_path(full)
            if path and not Research.is_noisy(path) and not Research.is_unsafe(path) then
                if added < max and hook_one(path) then added = added + 1 end
            elseif path then
                skipped = skipped + 1
            end
        end
        print(string.format("[RESEARCH] watching %d function(s) matching '%s' (%d noisy skipped, max %d). Do the action now, then read the [WATCH] lines.",
            added, keyword, skipped, max))
        return added
    end

    function Research.clear()
        local removed = 0
        for _, path in ipairs(state.order) do
            local entry = state.watched[path]
            if entry and pcall(UnregisterHook, path, entry.pre, entry.post) then removed = removed + 1 end
        end
        state.watched, state.order = {}, {}
        print(string.format("[RESEARCH] removed %d watch hook(s)", removed))
        return removed
    end

    function Research.status()
        print(string.format("[RESEARCH] %d function(s) watched", #state.order))
        for _, path in ipairs(state.order) do
            print(string.format("[RESEARCH]   %s fired %d time(s)", Research.short_name(path), state.watched[path].count))
        end
    end

    if RegisterConsoleCommandHandler then
        local function arg(parameters, index)
            if type(parameters) == "table" then return parameters[index] end
            return nil
        end
        RegisterConsoleCommandHandler("ap_scan", function(_, parameters)
            Research.scan(arg(parameters, 1), arg(parameters, 2))
            return true
        end)
        RegisterConsoleCommandHandler("ap_class", function(_, parameters)
            Research.class_info(arg(parameters, 1))
            return true
        end)
        RegisterConsoleCommandHandler("ap_instances", function(_, parameters)
            Research.instances(arg(parameters, 1), arg(parameters, 2))
            return true
        end)
        RegisterConsoleCommandHandler("ap_hookclass", function(_, parameters)
            Research.hook_class(arg(parameters, 1), arg(parameters, 2))
            return true
        end)
        RegisterConsoleCommandHandler("ap_hookfn", function(_, parameters)
            Research.hook_function(arg(parameters, 1), arg(parameters, 2))
            return true
        end)
        RegisterConsoleCommandHandler("ap_watch", function(_, parameters)
            Research.watch(arg(parameters, 1), arg(parameters, 2))
            return true
        end)
        RegisterConsoleCommandHandler("ap_watch_clear", function()
            Research.clear()
            return true
        end)
        RegisterConsoleCommandHandler("ap_watch_status", function()
            Research.status()
            return true
        end)
    end

    print("[ARCHI] Research tools loaded: ap_class, ap_instances, ap_hookclass, ap_hookfn, ap_scan/ap_watch (heavy), ap_watch_clear, ap_watch_status (read-only)")
    return Research
end

return Research
