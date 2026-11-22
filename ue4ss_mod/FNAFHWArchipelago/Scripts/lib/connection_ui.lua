-- ==============================================================================
-- FNAF HW Archipelago Mod - In-Game Connection UI & Profile Manager
-- ==============================================================================

local ConnectionUI = {}

local function file_exists(path)
    local f = io.open(path, "r")
    if f then
        f:close()
        return true
    end
    return false
end

local function read_file(path)
    local f = io.open(path, "r")
    if not f then return nil end
    local content = f:read("*a")
    f:close()
    return content
end

local function write_file(path, content)
    local f = io.open(path, "w")
    if not f then return false end
    f:write(content)
    f:close()
    return true
end

function ConnectionUI.init(params)
    local bridge_dir = params.bridge_dir
    local APBridge = params.APBridge
    local mod_dir = params.mod_dir

    local profile_path = bridge_dir .. "/connection_profile.json"
    local state_path = bridge_dir .. "/connection_state.json"

    ConnectionUI.is_visible = false
    ConnectionUI.selected_index = 1 -- 1: Host, 2: Port, 3: Slot, 4: Password, 5: Connect Btn
    ConnectionUI.cursor_visible = true
    ConnectionUI.last_cursor_toggle = os.time()

    ConnectionUI.fields = {
        host = "archipelago.gg",
        port = "38281",
        slot = "Player1",
        password = "",
    }

    ConnectionUI.status = "DISCONNECTED"
    ConnectionUI.status_msg = "Press F1 to open connection menu"
    ConnectionUI.checked_count = 0
    ConnectionUI.received_count = 0
    ConnectionUI.total_count = 146 -- every group randomized; the client writes the real total of the seed into connection_state.json

    -- What the password row shows: asterisks for one set in this panel, "(saved)" for one the client keeps, else "(none)".
    function ConnectionUI.password_text()
        if ConnectionUI.fields.password ~= "" then return string.rep("*", #ConnectionUI.fields.password) end
        return ConnectionUI.password_saved and "(saved)" or "(none)"
    end

    -- "Locations Checked: 4 / 50   |   Items Received: 7"
    function ConnectionUI.counter_text()
        return string.format("Locations Checked: %d / %d   |   Items Received: %d",
            ConnectionUI.checked_count, ConnectionUI.total_count, ConnectionUI.received_count)
    end

    -- JSON string literal of `text`: quotes, backslashes and control characters are escaped, so a password like  a"b  cannot break the file.
    local function json_string(text)
        local escaped = tostring(text):gsub('[%c"\\]', function(c)
            local named = { ['"'] = '\\"', ["\\"] = "\\\\", ["\n"] = "\\n", ["\r"] = "\\r", ["\t"] = "\\t" }
            return named[c] or string.format("\\u%04x", c:byte())
        end)
        return '"' .. escaped .. '"'
    end

    -- The string value of `"key": "..."` in a JSON text, unescaped (what json.dumps in the client wrote, \uXXXX included), or nil.
    local function json_string_field(content, key)
        local i = content:match('"' .. key .. '"%s*:%s*"()')
        if not i then return nil end
        local out = {}
        local single = { n = "\n", r = "\r", t = "\t", b = "\b", f = "\f" }
        while i <= #content do
            local c = content:sub(i, i)
            if c == '"' then return table.concat(out) end
            if c == "\\" then
                local nxt = content:sub(i + 1, i + 1)
                if nxt == "u" then
                    local code = tonumber(content:sub(i + 2, i + 5), 16)
                    out[#out + 1] = code and (utf8 and utf8.char(code) or "?") or "?"
                    i = i + 6
                else
                    out[#out + 1] = single[nxt] or nxt
                    i = i + 2
                end
            else
                out[#out + 1] = c
                i = i + 1
            end
        end
        return nil  -- unterminated string: the file is cut off
    end

    -- The password is never in the profile. The client keeps it encrypted (connection_secret.dat); this panel cannot encrypt, so a password the
    -- player sets here goes into the drop file, which the client encrypts and deletes as soon as it reads the profile.
    local secret_path = bridge_dir .. "/connection_secret.dat"
    local password_drop_path = bridge_dir .. "/connection_password.txt"
    ConnectionUI.password_dirty = false  -- the player set (or cleared) the password in this panel and it is not handed over yet

    -- true when a password is stored (or on its way): the panel then shows "(saved)" instead of "(none)". An empty drop file is a cleared password.
    ConnectionUI.password_saved = false
    local function password_is_saved()
        local pending = read_file(password_drop_path)
        if pending ~= nil then return pending ~= "" end
        return file_exists(secret_path)
    end
    ConnectionUI.password_saved = password_is_saved()

    local function parse_profile(content)
        if not content then return end
        local host = json_string_field(content, "server_host")
        local port = content:match('"server_port"%s*:%s*(%d+)')
        local slot = json_string_field(content, "slot")

        if host and host ~= "" then ConnectionUI.fields.host = host end
        if port and port ~= "" then ConnectionUI.fields.port = tostring(port) end
        if slot and slot ~= "" then ConnectionUI.fields.slot = slot end
        -- a password in an old profile is left for the client to move into its encrypted store; it is not read here
    end

    local function save_profile()
        local json_str = string.format([[
{
  "server_host": %s,
  "server_port": %d,
  "slot": %s,
  "auto_connect": true
}
]], json_string(ConnectionUI.fields.host), tonumber(ConnectionUI.fields.port) or 38281, json_string(ConnectionUI.fields.slot))
        write_file(profile_path, json_str)
        if ConnectionUI.password_dirty then
            write_file(password_drop_path, ConnectionUI.fields.password)  -- an empty file means "no password"
            ConnectionUI.password_dirty = false
            ConnectionUI.fields.password = ""  -- not kept here once it is handed over
            ConnectionUI.password_saved = password_is_saved()
        end
        print("[FNAFHW AP] Saved connection profile to " .. profile_path)
    end

    -- Load existing profile
    if file_exists(profile_path) then
        parse_profile(read_file(profile_path))
        print("[FNAFHW AP] Loaded profile: " .. ConnectionUI.fields.host .. ":" .. ConnectionUI.fields.port .. " as " .. ConnectionUI.fields.slot)
    end

    local function print_screen(msg, color, duration)
        print("[FNAFHW AP] " .. msg)
        if not StaticFindObject then return end
        local ok, kismet = pcall(StaticFindObject, "/Script/Engine.Default__KismetSystemLibrary")
        if ok and kismet and kismet:IsValid() then
            color = color or { R = 0.0, G = 1.0, B = 1.0, A = 1.0 }
            duration = duration or 5.0
            pcall(function()
                kismet:PrintString(nil, msg, true, true, color, duration)
            end)
        end
    end

    -- Connect trigger
    function ConnectionUI.connect()
        save_profile()
        ConnectionUI.status = "CONNECTING"
        ConnectionUI.status_msg = "Connecting to " .. ConnectionUI.fields.host .. ":" .. ConnectionUI.fields.port .. "..."
        -- Settings go through the profile file written just above, never through the command: the outbox is an append-only file that nothing
        -- truncates, so a password put there would stay in it for good. A client that predates this still gets what it needs from the profile.
        APBridge.append_outbox("CONNECT")
        print_screen("[Archipelago] Connecting to " .. ConnectionUI.fields.host .. ":" .. ConnectionUI.fields.port .. " as " .. ConnectionUI.fields.slot, {R=0.2, G=0.8, B=1.0, A=1.0}, 5.0)
    end

    function ConnectionUI.disconnect()
        ConnectionUI.status = "DISCONNECTED"
        ConnectionUI.status_msg = "Disconnected."
        APBridge.append_outbox("DISCONNECT")
        print_screen("[Archipelago] Disconnected from server.", {R=1.0, G=0.4, B=0.4, A=1.0}, 4.0)
    end

    local last_f1_time = 0
    function ConnectionUI.toggle()
        local now = os.clock()
        if now - last_f1_time < 0.4 then return end
        last_f1_time = now

        ConnectionUI.update_state()
        ConnectionUI.is_visible = not ConnectionUI.is_visible
        print("[FNAFHW AP] Connection Menu " .. (ConnectionUI.is_visible and "OPENED" or "CLOSED"))

        -- Request Desktop GUI to bring to front
        APBridge.append_outbox("SHOW_UI")

        -- On-Screen Feedback
        if ConnectionUI.status == "CONNECTED" then
            print_screen(string.format("[Archipelago] CONNECTED (%s) | %d checks | %d items", ConnectionUI.fields.slot, ConnectionUI.checked_count, ConnectionUI.received_count), {R=0.2, G=1.0, B=0.3, A=1.0}, 6.0)
        elseif ConnectionUI.status == "CONNECTING" or ConnectionUI.status == "AUTHENTICATING" then
            print_screen("[Archipelago] CONNECTING to " .. ConnectionUI.fields.host .. ":" .. ConnectionUI.fields.port .. "...", {R=1.0, G=0.8, B=0.2, A=1.0}, 5.0)
        else
            print_screen("[Archipelago] DISCONNECTED. Opening Desktop Window... (Connecting as " .. ConnectionUI.fields.slot .. ")", {R=1.0, G=0.8, B=0.2, A=1.0}, 6.0)
            -- Auto-attempt connection if disconnected
            ConnectionUI.connect()
        end
    end

    -- Read live connection state from bridge
    function ConnectionUI.update_state()
        ConnectionUI.password_saved = password_is_saved()
        local raw = read_file(state_path)  -- nil when the client has not written it yet
        if raw then
            local st = raw:match('"status"%s*:%s*"([^"]+)"')
            local msg = raw:match('"last_message"%s*:%s*"([^"]+)"')
            local chk = raw:match('"checked_count"%s*:%s*(%d+)')
            local rcv = raw:match('"received_count"%s*:%s*(%d+)')
            local total = raw:match('"total_count"%s*:%s*(%d+)')

            if st then ConnectionUI.status = st end
            if msg then ConnectionUI.status_msg = msg end
            if chk then ConnectionUI.checked_count = tonumber(chk) or 0 end
            if rcv then ConnectionUI.received_count = tonumber(rcv) or 0 end
            if total then ConnectionUI.total_count = tonumber(total) or ConnectionUI.total_count end
        end
    end

    -- The HUD hook runs every frame while the panel is open; the client rewrites the state file at most a few times a second.
    local STATE_REFRESH_SECONDS = 0.5
    local last_state_refresh = nil
    function ConnectionUI.refresh_state_if_due(now)
        if last_state_refresh and now - last_state_refresh < STATE_REFRESH_SECONDS then return false end
        last_state_refresh = now
        ConnectionUI.update_state()
        return true
    end

    -- Register console commands
    if RegisterConsoleCommandHandler then
        RegisterConsoleCommandHandler("ap_ui", function()
            ConnectionUI.toggle()
            return true
        end)
        RegisterConsoleCommandHandler("ap_menu", function()
            ConnectionUI.toggle()
            return true
        end)
        RegisterConsoleCommandHandler("ap_connect", function(full_cmd, params)
            -- UE4SS hands the parameters over as a table of words (empty for a bare command); a string is accepted too
            local parts = {}
            if type(params) == "table" then
                for _, w in ipairs(params) do
                    table.insert(parts, tostring(w))
                end
            else
                for w in string.gmatch(params or "", "%S+") do
                    table.insert(parts, w)
                end
            end
            if #parts >= 3 then
                ConnectionUI.fields.host = parts[1]
                ConnectionUI.fields.port = parts[2]
                ConnectionUI.fields.slot = parts[3]
                ConnectionUI.fields.password = parts[4] or ""  -- the full form sets the password, so leaving it out means none
                ConnectionUI.password_dirty = true
            end
            ConnectionUI.connect()
            return true
        end)
        RegisterConsoleCommandHandler("ap_disconnect", function()
            ConnectionUI.disconnect()
            return true
        end)
        RegisterConsoleCommandHandler("ap_status", function()
            ConnectionUI.update_state()
            print(string.format("[FNAFHW AP] Status: %s | Server: %s:%s | Slot: %s | Checks: %d | Items: %d",
                ConnectionUI.status, ConnectionUI.fields.host, ConnectionUI.fields.port, ConnectionUI.fields.slot,
                ConnectionUI.checked_count, ConnectionUI.received_count
            ))
            return true
        end)
    end

    -- Register Keybinds for in-game menu navigation
    if RegisterKeyBind and Key then
        RegisterKeyBind(Key.F1, function()
            ConnectionUI.toggle()
        end)

        RegisterKeyBind(Key.TAB, function()
            if not ConnectionUI.is_visible then return end
            ConnectionUI.selected_index = (ConnectionUI.selected_index % 5) + 1
        end)

        RegisterKeyBind(Key.DOWN_ARROW, function()
            if not ConnectionUI.is_visible then return end
            ConnectionUI.selected_index = (ConnectionUI.selected_index % 5) + 1
        end)

        RegisterKeyBind(Key.UP_ARROW, function()
            if not ConnectionUI.is_visible then return end
            ConnectionUI.selected_index = ConnectionUI.selected_index - 1
            if ConnectionUI.selected_index < 1 then ConnectionUI.selected_index = 5 end
        end)

        RegisterKeyBind(Key.RETURN, function()
            if not ConnectionUI.is_visible then return end
            if ConnectionUI.selected_index == 5 or ConnectionUI.selected_index == 1 or ConnectionUI.selected_index == 3 then
                ConnectionUI.connect()
            end
        end)

        RegisterKeyBind(Key.BACKSPACE, function()
            if not ConnectionUI.is_visible then return end
            local key_map = { [1] = "host", [2] = "port", [3] = "slot", [4] = "password" }
            local f = key_map[ConnectionUI.selected_index]
            if f and #ConnectionUI.fields[f] > 0 then
                ConnectionUI.fields[f] = ConnectionUI.fields[f]:sub(1, -2)
                if f == "password" then ConnectionUI.password_dirty = true end
            elseif f == "password" and ConnectionUI.password_saved then
                ConnectionUI.password_dirty = true  -- Backspace on the "(saved)" row forgets the saved password at the next connect
                ConnectionUI.password_saved = false
            end
        end)

        -- Quick connect / disconnect hotkeys when UI is open
        RegisterKeyBind(Key.C, function()
            if not ConnectionUI.is_visible then return end
            ConnectionUI.connect()
        end)

        RegisterKeyBind(Key.D, function()
            if not ConnectionUI.is_visible then return end
            ConnectionUI.disconnect()
        end)
    end

    -- Hook AHUD:ReceiveDrawHUD to render the in-game canvas menu
    local cached_font = nil
    if RegisterHook then
        RegisterHook("/Script/Engine.HUD:ReceiveDrawHUD", function(self, SizeX, SizeY)
            if not ConnectionUI.is_visible then return end
            local canvas = self.Canvas
            if not canvas or not canvas:IsValid() then return end

            if not cached_font and FindFirstOf then
                local ok, f = pcall(FindFirstOf, "Font")
                if ok and f and f:IsValid() then cached_font = f end
            end

            ConnectionUI.refresh_state_if_due(os.clock())

            local x = 60.0
            local y = 60.0
            local line_height = 28.0

            -- Draw Title Box
            local title_color = { R = 0.2, G = 0.8, B = 1.0, A = 1.0 }
            local text_color  = { R = 1.0, G = 1.0, B = 1.0, A = 1.0 }
            local sel_color   = { R = 1.0, G = 0.85, B = 0.2, A = 1.0 }
            local status_col  = { R = 0.5, G = 0.5, B = 0.5, A = 1.0 }

            if ConnectionUI.status == "CONNECTED" then
                status_col = { R = 0.2, G = 1.0, B = 0.3, A = 1.0 }
            elseif ConnectionUI.status == "CONNECTING" or ConnectionUI.status == "AUTHENTICATING" then
                status_col = { R = 1.0, G = 0.8, B = 0.2, A = 1.0 }
            elseif ConnectionUI.status == "ERROR" then
                status_col = { R = 1.0, G = 0.3, B = 0.2, A = 1.0 }
            end

            local function draw_text(txt, posX, posY, col, scale)
                pcall(function()
                    canvas:K2_DrawText(
                        cached_font,
                        txt,
                        { X = posX, Y = posY },
                        { X = scale or 1.2, Y = scale or 1.2 },
                        col or text_color,
                        0.0,
                        { R = 0, G = 0, B = 0, A = 1 },
                        { X = 1.5, Y = 1.5 },
                        false, false, true,
                        { R = 0, G = 0, B = 0, A = 1 }
                    )
                end)
            end

            draw_text("=== ARCHIPELAGO MULTIWORLD ===", x, y, title_color, 1.4)
            y = y + line_height + 4

            draw_text(string.format("Status: [%s]  %s", ConnectionUI.status, ConnectionUI.status_msg), x, y, status_col, 1.1)
            y = y + line_height + 8

            -- Fields
            local items = {
                { label = "1. Server Host : ", val = ConnectionUI.fields.host },
                { label = "2. Server Port : ", val = ConnectionUI.fields.port },
                { label = "3. Player Slot : ", val = ConnectionUI.fields.slot },
                { label = "4. Password    : ", val = ConnectionUI.password_text() },
                { label = "5. [ CLICK TO CONNECT / DISCONNECT ]", val = "" },
            }

            for idx, item in ipairs(items) do
                local prefix = (ConnectionUI.selected_index == idx) and " > " or "   "
                local col = (ConnectionUI.selected_index == idx) and sel_color or text_color
                draw_text(prefix .. item.label .. item.val, x, y, col, 1.2)
                y = y + line_height
            end

            y = y + 8
            draw_text(ConnectionUI.counter_text(), x, y, title_color, 1.1)
            y = y + line_height

            draw_text("[RETURN/C] Connect   [D] Disconnect   [TAB/Arrows] Navigate   [F1] Close Menu",
                x, y, { R = 0.7, G = 0.7, B = 0.7, A = 1.0 }, 1.0)
        end)
    end

    return ConnectionUI
end

return ConnectionUI
