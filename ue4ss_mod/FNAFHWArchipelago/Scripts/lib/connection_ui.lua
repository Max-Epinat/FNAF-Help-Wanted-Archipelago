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

    -- Simple JSON string decoder for key-value pairs
    local function parse_profile(content)
        if not content then return end
        local host = content:match('"server_host"%s*:%s*"([^"]+)"')
        local port = content:match('"server_port"%s*:%s*(%d+)')
        local slot = content:match('"slot"%s*:%s*"([^"]+)"')
        local pwd  = content:match('"password"%s*:%s*"([^"]*)"')

        if host and host ~= "" then ConnectionUI.fields.host = host end
        if port and port ~= "" then ConnectionUI.fields.port = tostring(port) end
        if slot and slot ~= "" then ConnectionUI.fields.slot = slot end
        if pwd then ConnectionUI.fields.password = pwd end
    end

    local function save_profile()
        local json_str = string.format([[
{
  "server_host": "%s",
  "server_port": %d,
  "slot": "%s",
  "password": "%s",
  "auto_connect": true
}
]], ConnectionUI.fields.host, tonumber(ConnectionUI.fields.port) or 38281, ConnectionUI.fields.slot, ConnectionUI.fields.password)
        write_file(profile_path, json_str)
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
        local cmd = string.format("CONNECT %s %s %s %s",
            ConnectionUI.fields.host,
            ConnectionUI.fields.port,
            ConnectionUI.fields.slot,
            ConnectionUI.fields.password
        )
        APBridge.append_outbox(cmd)
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
        if file_exists(state_path) then
            local raw = read_file(state_path)
            if raw then
                local st = raw:match('"status"%s*:%s*"([^"]+)"')
                local msg = raw:match('"last_message"%s*:%s*"([^"]+)"')
                local chk = raw:match('"checked_count"%s*:%s*(%d+)')
                local rcv = raw:match('"received_count"%s*:%s*(%d+)')

                if st then ConnectionUI.status = st end
                if msg then ConnectionUI.status_msg = msg end
                if chk then ConnectionUI.checked_count = tonumber(chk) or 0 end
                if rcv then ConnectionUI.received_count = tonumber(rcv) or 0 end
            end
        end
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
        RegisterConsoleCommandHandler("ap_connect", function(full_cmd, params_str)
            local parts = {}
            for w in string.gmatch(params_str or "", "%S+") do
                table.insert(parts, w)
            end
            if #parts >= 3 then
                ConnectionUI.fields.host = parts[1]
                ConnectionUI.fields.port = parts[2]
                ConnectionUI.fields.slot = parts[3]
                ConnectionUI.fields.password = parts[4] or ""
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

            ConnectionUI.update_state()

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
                { label = "4. Password    : ", val = (ConnectionUI.fields.password == "" and "(none)" or string.rep("*", #ConnectionUI.fields.password)) },
                { label = "5. [ CLICK TO CONNECT / DISCONNECT ]", val = "" },
            }

            for idx, item in ipairs(items) do
                local prefix = (ConnectionUI.selected_index == idx) and " > " or "   "
                local col = (ConnectionUI.selected_index == idx) and sel_color or text_color
                draw_text(prefix .. item.label .. item.val, x, y, col, 1.2)
                y = y + line_height
            end

            y = y + 8
            draw_text(string.format("Locations Checked: %d / 153   |   Items Received: %d",
                ConnectionUI.checked_count, ConnectionUI.received_count), x, y, title_color, 1.1)
            y = y + line_height

            draw_text("[RETURN/C] Connect   [D] Disconnect   [TAB/Arrows] Navigate   [F1] Close Menu",
                x, y, { R = 0.7, G = 0.7, B = 0.7, A = 1.0 }, 1.0)
        end)
    end

    return ConnectionUI
end

return ConnectionUI
