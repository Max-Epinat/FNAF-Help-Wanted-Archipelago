-- ==============================================================================
-- FNAF HW Archipelago Mod - Exact Blueprint & C++ Function Hooks
-- ==============================================================================

local ExactHooks = {}

function ExactHooks.init(params)
    local APBridge = params.APBridge
    local locations_data = params.locations_data or {}
    local emitted_location_names = params.emitted_location_names or {}
    local baseline_location_names = params.baseline_location_names or {}
    local mod_dir = params.mod_dir or ""

    local row_to_loc = locations_data.row_id_to_location or {}
    local name_to_id = locations_data.location_name_to_id or {}

    -- Load exact prize ID mapping table (Prize_Info_DataTable row keys to AP locations)
    local prize_id_to_loc = {}
    pcall(function()
        if mod_dir ~= "" then
            prize_id_to_loc = dofile(mod_dir .. "/Scripts/lib/prize_id_to_location.lua")
        end
    end)
    if not prize_id_to_loc then prize_id_to_loc = {} end

    -- Load full prize locations table (82 prizes)
    local prize_location_names = {}
    pcall(function()
        if mod_dir ~= "" then
            prize_location_names = dofile(mod_dir .. "/Scripts/lib/prize_location_names.lua")
        end
    end)
    if not prize_location_names or #prize_location_names == 0 then
        -- Fallback table if file loading fails
        prize_location_names = {
            "Prize - Plushie: Freddy Plush",
            "Prize - Plushie: Bonnie Plush",
            "Prize - Plushie: Chica Plush",
            "Prize - Plushie: Foxy Plush",
            "Prize - Plushie: Golden Freddy Plush",
            "Prize - Plushie: Springtrap Plush",
            "Prize - Plushie: Toy Freddy Plush",
            "Prize - Plushie: Toy Bonnie Plush",
            "Prize - Plushie: Toy Chica Plush",
            "Prize - Plushie: Mangle Plush",
            "Prize - Plushie: BB Plush",
            "Prize - Plushie: JJ Plush",
            "Prize - Plushie: Puppet Plush",
            "Prize - Plushie: Plushtrap Plush",
            "Prize - Plushie: Nightmare Freddy Plush",
            "Prize - Plushie: Nightmare Bonnie Plush",
            "Prize - Plushie: Nightmare Chica Plush",
            "Prize - Plushie: Nightmare Fredbear Plush",
            "Prize - Plushie: Nightmarionne Plush",
            "Prize - Plushie: Helpy Plush",
            "Prize - Plushie: Plushbaby",
            "Prize - Plushie: Plushbaby (Scrap Baby ver.)",
            "Prize - Plushie: Funtime Foxy",
            "Prize - Plushie: Funtime Freddy",
            "Prize - Action Figure: Freddy Action Figure",
            "Prize - Action Figure: Bonnie Action Figure",
            "Prize - Action Figure: Chica Action Figure",
            "Prize - Action Figure: Foxy Action Figure",
            "Prize - Action Figure: Golden Freddy Action Figure",
            "Prize - Action Figure: Springtrap Action Figure",
            "Prize - Action Figure: Toy Freddy Action Figure",
            "Prize - Action Figure: Toy Bonnie Action Figure",
            "Prize - Action Figure: Toy Chica Action Figure",
            "Prize - Action Figure: Mangle Action Figure",
            "Prize - Action Figure: Puppet Action Figure",
            "Prize - Action Figure: Circus Baby Action Figure",
            "Prize - Action Figure: Ballora Action Figure",
            "Prize - Action Figure: Funtime Freddy Action Figure",
            "Prize - Action Figure: Funtime Foxy Action Figure",
            "Prize - Action Figure: Ennard Action Figure",
            "Prize - Action Figure: Balloon Boy Action Figure",
            "Prize - Action Figure: Plushtrap Action Figure",
            "Prize - Action Figure: Nightmarionne Action Figure",
            "Prize - Action Figure: Nightmare Fredbear Action Figure",
            "Prize - Action Figure: Bon-Bon Action Figure",
            "Prize - Other: Exotic Butters",
            "Prize - Other: Mr. Cupcake",
            "Prize - Other: Pizza Slice",
            "Prize - Other: Faz Soda",
            "Prize - Other: Bon-Bon Hand Puppet",
            "Prize - Other: Mini Music Box",
            "Prize - Other: Candy Bucket",
            "Prize - Other: Freddy Bobblehead",
            "Prize - Other: Bonnie Bobblehead",
            "Prize - Chica Bobblehead",
            "Prize - Other: Foxy Bobblehead",
            "Prize - Other: Nightmarionne Bobblehead",
            "Prize - Other: Mystery Box",
            "Prize - Other: Prize Counter Poster",
            "Prize - Food/Drink: Disappointment Chips",
            "Prize - Food/Drink: El Chip's Tortilla Chips Bold and Spicy",
            "Prize - Food/Drink: Meat Bites XL",
            "Prize - Food/Drink: Bonnie Bites",
            "Prize - Food/Drink: Allergy Friendly Mixed Nuts",
            "Prize - Food/Drink: Meat Bites",
            "Prize - Food/Drink: Stick of Butter",
            "Prize - Food/Drink: Pirate Plunderbar",
            "Prize - Food/Drink: Foxy Cove Cooler",
            "Prize - Food/Drink: Butter for One",
            "Prize - Food/Drink: Freddy Fudgebar",
            "Prize - Food/Drink: Exotic Beverage",
            "Prize - Food/Drink: Sodaroni",
            "Prize - Food/Drink: Chica Chug",
            "Prize - Food/Drink: El Chip's Tortilla Chips",
            "Prize - Food/Drink: Fazbar",
            "Prize - Food/Drink: Lemon Chica Bar",
            "Prize - Food/Drink: Slice of Cake",
            "Prize - Toy: Cupcake",
            "Prize - Toy: Toy phone",
            "Prize - Toy: Toy Catterpillar",
            "Prize - Toy: Toy Robot"
        }
    end

    -- Map Name to AP Location Name (Deterministic fallback)
    local MAP_NAME_NORMAL = {
        ["Repair_Bonnie_Game"] = "Complete Parts and Service - Bonnie",
        ["Repair_Chica_Game"] = "Complete Parts and Service - Chica",
        ["Repair_Freddy_Game"] = "Complete Parts and Service - Freddy",
        ["Repair_Foxy_Game"] = "Complete Parts and Service - Foxy",
        ["Vent_Game_Mangle_1"] = "Complete Vent Repair - Mangle",
        ["Vent_Game_Ennard_2"] = "Complete Vent Repair - Ennard",
        ["NightTerror_FunTime_Freddy"] = "Complete Night Terrors - Funtime Freddy",
        ["NightTerror_Nightmarionne"] = "Complete Night Terrors - Nightmarionne",
        ["NightTerror_CircusBaby"] = "Complete Night Terrors - Circus Baby",
        ["NightTerror_Fredbear"] = "Complete Night Terrors - Nightmare Fredbear",
        ["Finale_Ending"] = "Complete Pizza Party",
        ["Flashlight_Game_Ver_2"] = "Complete Dark Rooms - Plushbaby",
        ["Funtime_Foxy"] = "Complete Dark Rooms - Funtime Foxy",
    }

    local MAP_NAME_HARD = {
        ["Repair_Bonnie_Game"] = "Complete Parts and Service (Hard) - Bonnie",
        ["Repair_Chica_Game"] = "Complete Parts and Service (Hard) - Chica",
        ["Repair_Freddy_Game"] = "Complete Parts and Service (Hard) - Freddy",
        ["Repair_Foxy_Game"] = "Complete Parts and Service (Hard) - Foxy",
        ["Vent_Game_Mangle_1"] = "Complete Vent Repair (Hard) - Mangle",
        ["Vent_Game_Ennard_2"] = "Complete Vent Repair (Hard) - Ennard",
        ["Flashlight_Game_Ver_2"] = "Complete Dark Rooms (Hard) - Plushbaby",
        ["Funtime_Foxy"] = "Complete Dark Rooms (Hard) - Funtime Foxy",
    }

    local awarded_coins = {}
    local awarded_prizes_count = 0
    local prize_poll_warned = false
    local next_token_index = 1
    local next_tape_index = 1

    local function emit_check(location_name)
        if not location_name or location_name == "" then return end
        if emitted_location_names[location_name] then
            return
        end
        emitted_location_names[location_name] = true
        APBridge.send_location_check_name(location_name)
        print(string.format("[FNAFHW AP] >>> CHECK EARNED: %s", location_name))
    end

    -- main.lua passes lib/game_thread.lua's cached lookup (no object-array scan per call, none off the game thread)
    local get_game_instance = params.game_instance or function()
        if not FindFirstOf then return nil end
        local ok, gi = pcall(FindFirstOf, "BP_FNAF_GameInstance_C")
        if ok and gi and gi:IsValid() then
            return gi
        end
        return nil
    end

    local GLITCH_ID_MAP = {
        [14] = "Collect Prize Counter Intro Tape",
        [0]  = "Collect Glitch Tape 02",
        [1]  = "Collect Glitch Tape 03",
        [2]  = "Collect Glitch Tape 04",
        [4]  = "Collect Glitch Tape 05",
        [5]  = "Collect Glitch Tape 06",
        [6]  = "Collect Glitch Tape 07",
        [7]  = "Collect Glitch Tape 08",
        [8]  = "Collect Glitch Tape 09",
        [9]  = "Collect Glitch Tape 10",
        [10] = "Collect Glitch Tape 11",
        [11] = "Collect Glitch Tape 12",
        [12] = "Collect Glitch Tape 13",
        [13] = "Collect Glitch Tape 14",
        [15] = "Collect Glitch Tape 15",
        [16] = "Collect Glitch Tape 16",
    }

    local function get_name_string(obj)
        if obj == nil then return "" end
        local raw = nil
        if type(obj) == "string" then
            raw = obj
        elseif type(obj) == "number" then
            return tostring(obj)
        elseif type(obj) == "userdata" then
            if obj.ToString then
                local ok, s = pcall(function() return obj:ToString() end)
                if ok and s then raw = tostring(s) end
            end
            if not raw and obj.get then
                local ok, v = pcall(function() return obj:get() end)
                if ok and v ~= nil then raw = tostring(v) end
            end
            if not raw then
                raw = tostring(obj)
            end
        else
            raw = tostring(obj)
        end

        if not raw then return "" end
        -- Strip UE4SS wrapper prefixes: e.g. "FName: ", "FString: ", "FText: "
        local cleaned = raw:gsub("^F[A-Za-z]+:%s*", "")
        -- Trim whitespace and surrounding quotes
        cleaned = cleaned:gsub("^%s+", ""):gsub("%s+$", ""):gsub('^"', ''):gsub('"$', '')
        return cleaned
    end

    -- The name of the map the world is showing, "" when unknown. Cut out of World:GetFullName(), which returns a plain string
    -- ("World /Game/.../NightGuard_Office01.NightGuard_Office01"). World:GetName(), GameplayStatics:GetCurrentLevelName and
    -- GameInstance.CurrentLevelName come back as an FString that decodes to pointer garbage (seen in game: random wide characters in the Map= log field), and
    -- Lua's FString:ToString on such a value is the access violation in the 2026-10-04 playtest crash dump. Never use them.
    local function get_current_map_name(gi)
        if not gi then return "" end
        local ok, full = pcall(function()
            if not gi:IsValid() then return "" end
            local world = gi:GetWorld()
            if world and world:IsValid() then return world:GetFullName() end
            return ""
        end)
        if not ok or not full then return "" end
        return tostring(full):match("([%w_]+)%s*$") or ""
    end

    -- Only COUNTS the prizes in the save (a diagnostic line when it changes). The elements are never decoded: the ids come back
    -- as raw pointer strings (not the prize ids), and calling ToString on them is what crashed the game once an hour (UE4SS
    -- dump, 2026-10-04: wcslen on a bogus FString pointer). Prize locations are sent by the client's save poll, which reads the
    -- ids from the .sav file. Do not "fix" the decoding here: it would activate a second prize-check sender.
    local function check_and_award_prizes(gi, is_live)
        if not gi or not gi.SaveGameRef then return end
        local save = gi.SaveGameRef
        pcall(function()
            if save.Prizes and save.Prizes.ForEach then
                local count = 0
                save.Prizes:ForEach(function()
                    count = count + 1
                end)
                if count ~= awarded_prizes_count then
                    print(string.format("[ARCHI] Save prize count changed: %d -> %d", awarded_prizes_count, count))
                end
                awarded_prizes_count = count
            end
        end)
    end

    local registered_hooks = {}
    local function try_hook(hook_path, callback)
        if registered_hooks[hook_path] then return true end
        if not RegisterHook then return false end
        local ok, err = pcall(RegisterHook, hook_path, callback)
        if ok then
            registered_hooks[hook_path] = true
            print("[FNAFHW AP] Hook registered: " .. hook_path)
            return true
        end
        return false
    end

    function ExactHooks.try_register_all()
        -- Ensure SaveSlotName is redirected to Playerarchi on GameInstance
        local gi_inst = get_game_instance()
        if gi_inst and gi_inst:IsValid() then
            pcall(function()
                local cur_slot = get_name_string(gi_inst.SaveSlotName)
                if cur_slot ~= "Playerarchi" then
                    gi_inst.SaveSlotName = "Playerarchi"
                    print(string.format("[ARCHI] Enforced SaveSlotName='Playerarchi' on active GameInstance (was: '%s')", tostring(cur_slot)))
                    -- If Playerarchi exists on disk, load it cleanly into SaveGameRef in memory
                    pcall(function()
                        local GameplayStatics = StaticFindObject("/Script/Engine.Default__GameplayStatics")
                        if GameplayStatics and GameplayStatics.DoesSaveGameExist then
                            local exists = false
                            pcall(function() exists = GameplayStatics:DoesSaveGameExist("Playerarchi", 0) end)
                            if exists and GameplayStatics.LoadGameFromSlot then
                                local loaded = GameplayStatics:LoadGameFromSlot("Playerarchi", 0)
                                if loaded and loaded:IsValid() then
                                    gi_inst.SaveGameRef = loaded
                                    print("[ARCHI] Successfully synchronized 'Playerarchi' save into in-memory SaveGameRef!")
                                end
                            end
                        end
                    end)
                end
            end)
        end

        -- Hook InitSaveGame and SaveGame to keep Playerarchi active
        try_hook("/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:InitSaveGame", function(self)
            pcall(function()
                if self and self:IsValid() then
                    self.SaveSlotName = "Playerarchi"
                    print("[ARCHI] InitSaveGame hook: SaveSlotName set to 'Playerarchi'")
                end
            end)
        end)

        try_hook("/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:SaveGame", function(self)
            pcall(function()
                if self and self:IsValid() then
                    self.SaveSlotName = "Playerarchi"
                end
            end)
        end)

        -- 1. Hook SaveLevelVictory on BP_FNAF_GameInstance_C
        try_hook("/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:SaveLevelVictory", function(self)
            local gi = self or get_game_instance()
            local map_name = get_current_map_name(gi)
            local is_hard = false
            local row_num = nil

            pcall(function()
                if gi then
                    if gi.IsInNightmareMode ~= nil then
                        is_hard = (gi.IsInNightmareMode == true)
                    end
                    if gi.CurrentLevelID ~= nil then
                        row_num = tonumber(get_name_string(gi.CurrentLevelID))
                    end
                    if not row_num and gi.CurrentLevelNameID ~= nil then
                        row_num = tonumber(get_name_string(gi.CurrentLevelNameID))
                    end
                    if not row_num and gi.CurrentLevelNumber ~= nil then
                        row_num = tonumber(get_name_string(gi.CurrentLevelNumber))
                    end
                    if not row_num and gi.GetCurrentLevelID then
                        local ok, id = pcall(function() return gi:GetCurrentLevelID() end)
                        if ok and id ~= nil then
                            row_num = tonumber(get_name_string(id))
                        end
                    end
                end
            end)

            local loc_name = nil

            -- Priority 1: Row ID resolution (Canonical LevelInfoTable primary key 0..40)
            if row_num and row_to_loc[row_num] then
                loc_name = row_to_loc[row_num].name
            end

            -- Priority 2: Map-based resolution (Fallback for standalone minigames)
            if not loc_name and map_name and map_name ~= "" then
                if is_hard and MAP_NAME_HARD[map_name] then
                    loc_name = MAP_NAME_HARD[map_name]
                elseif MAP_NAME_NORMAL[map_name] then
                    loc_name = MAP_NAME_NORMAL[map_name]
                end
            end

            -- Emit check
            if loc_name then
                local is_checked = emitted_location_names[loc_name] or baseline_location_names[loc_name]
                local action = (not is_checked) and "SEND" or "IGNORE"
                print(string.format("[ARCHI] Game event detected: SaveLevelVictory (Map='%s', Hard=%s, RowID=%s) -> Location='%s', Action=%s",
                    tostring(map_name), tostring(is_hard), tostring(row_num), loc_name, action))
                if action == "SEND" then
                    emit_check(loc_name)
                    if loc_name == "Complete Pizza Party" then
                        print("[ARCHI] Pizza Party completed! Sending Archipelago Goal packet!")
                        APBridge.send_goal()
                    end
                end
            else
                print(string.format("[ARCHI] Game event detected: SaveLevelVictory (Map='%s', Hard=%s, RowID=%s) -> Unmapped level, Action=IGNORE",
                    tostring(map_name), tostring(is_hard), tostring(row_num)))
            end
        end)

        -- 2. Hook BP_FNAFGameState_C:victory
        try_hook("/Game/ProductionAssets/Blueprints/BackEnd/BP_FNAFGameState.BP_FNAFGameState_C:victory", function(self)
            print("[FNAFHW AP] Hook: BP_FNAFGameState_C:victory event fired!")
        end)

        -- 3. Hook UnlockCoin on BP_FNAF_GameInstance_C
        try_hook("/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:UnlockCoin", function(self, CoinID)
            local cid = tonumber(get_name_string(CoinID))

            if cid and cid >= 1 and cid <= 30 then
                local loc_name = string.format("Collect Faz Token %02d", cid)
                local is_checked = emitted_location_names[loc_name] or baseline_location_names[loc_name]
                local action = (not is_checked) and "SEND" or "IGNORE"
                print(string.format("[ARCHI] Fazcoin detected: UnlockCoin CoinID=%d -> Location='%s', Action=%s", cid, loc_name, action))
                awarded_coins[cid] = true
                if action == "SEND" then
                    emit_check(loc_name)
                end
            else
                print(string.format("[ARCHI] Fazcoin detected: Unknown or invalid CoinID=%s, Action=IGNORE", tostring(cid)))
            end
        end)

        -- 4. Hook Token Grab Actors (GrabbableToken and GrabbableToken_InitiallyFrozen)
        local function on_coin_actor_grab(actor)
            pcall(function()
                if not actor then return end
                local cid = nil
                if actor.CoinID ~= nil then
                    cid = tonumber(get_name_string(actor.CoinID))
                end
                if not cid and actor.Coin_ID ~= nil then
                    cid = tonumber(get_name_string(actor.Coin_ID))
                end
                if cid and cid >= 1 and cid <= 30 and not awarded_coins[cid] then
                    local loc_name = string.format("Collect Faz Token %02d", cid)
                    local is_checked = emitted_location_names[loc_name] or baseline_location_names[loc_name]
                    local action = (not is_checked) and "SEND" or "IGNORE"
                    print(string.format("[ARCHI] Fazcoin detected: Actor grab CoinID=%d -> Location='%s', Action=%s", cid, loc_name, action))
                    awarded_coins[cid] = true
                    if action == "SEND" then
                        emit_check(loc_name)
                    end
                end
            end)
        end

        try_hook("/Game/ProductionAssets/Actors/GrabbableToken.GrabbableToken_C:AttemptGrab", on_coin_actor_grab)
        try_hook("/Game/ProductionAssets/Actors/GrabbableToken_InitiallyFrozen.GrabbableToken_InitiallyFrozen_C:AttemptGrab", on_coin_actor_grab)

        -- 5. Glitch Tape checks come from a real PICKUP only (AwardGlitch here, and the save's CollectedGlitches in the poll below / the client).
        -- Playing a tape in the tape room (SetGlitchListenedTo) must NOT send a check: the room shows as many tapes as Glitch Tape ITEMS received
        -- (derived_counters.lua), so the player can play tapes they never picked up, and each one was a free location check (found in game 2026-10-05:
        -- TAPE #2 -> Collect Glitch Tape 03). In vanilla a played tape was always a picked-up one, so nothing is lost by ignoring it.
        local awarded_glitches = {}
        local function on_glitch_tape_collected(source_name, GlitchID)
            local gid = tonumber(get_name_string(GlitchID))
            local loc_name = nil
            if gid and GLITCH_ID_MAP[gid] then
                loc_name = GLITCH_ID_MAP[gid]
            end
            if loc_name then
                local is_checked = emitted_location_names[loc_name] or baseline_location_names[loc_name]
                local action = (not is_checked) and "SEND" or "IGNORE"
                print(string.format("[ARCHI] Game event detected: %s (GlitchID=%s) -> Location='%s', Action=%s",
                    source_name, tostring(gid), loc_name, action))
                if action == "SEND" then
                    emit_check(loc_name)
                end
            else
                print(string.format("[ARCHI] Game event detected: %s with unmapped GlitchID=%s, Action=IGNORE", source_name, tostring(gid)))
            end
        end

        try_hook("/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:AwardGlitch", function(self, GlitchID)
            on_glitch_tape_collected("AwardGlitch", GlitchID)
        end)

        -- log only: which tape the player played (a diagnostic, never a check)
        try_hook("/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:SetGlitchListenedTo", function(self, GlitchID)
            print(string.format("[ARCHI] Tape listened to, no check sent: GlitchID=%s", tostring(get_name_string(GlitchID))))
        end)

        -- 6. Hook AwardRandomPrize and AttemptAwardSpecialPrize
        local function on_prize_awarded(gi)
            print("[ARCHI] Game event detected: Prize award trigger fired!")
            check_and_award_prizes(gi or get_game_instance(), true)
        end

        try_hook("/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:AwardRandomPrize", function(self, PrizeID)
            on_prize_awarded(self)
        end)

        try_hook("/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:AttemptAwardSpecialPrize", function(self)
            on_prize_awarded(self)
        end)
    end

    -- Initial safe registration attempt
    ExactHooks.try_register_all()

    -- Safety Net Poller: Inspects active SaveGameRef in memory
    function ExactHooks.poll_savegame_state()
        ExactHooks.try_register_all()
        local gi = get_game_instance()
        if not gi or not gi.SaveGameRef then return end

        local save = gi.SaveGameRef

        -- 1. Poll LevelInfo TMap in SaveGame
        pcall(function()
            if save.LevelInfo and save.LevelInfo.ForEach then
                save.LevelInfo:ForEach(function(Key, Value)
                    local key_str = get_name_string(Key)
                    local row_id = tonumber(key_str)
                    local is_completed = false
                    pcall(function()
                        if Value.Completed_7_C5B1BBD045D47AFB45A9A4AD494ABC84 ~= nil then
                            is_completed = (Value.Completed_7_C5B1BBD045D47AFB45A9A4AD494ABC84 == true)
                        end
                    end)

                    if is_completed and row_id and row_to_loc[row_id] then
                        local loc = row_to_loc[row_id]
                        local is_checked = emitted_location_names[loc.name] or baseline_location_names[loc.name]
                        local action = (not is_checked) and "SEND" or "IGNORE"
                        if action == "SEND" then
                            print(string.format("[ARCHI] Game event detected: LevelInfo Row %d (%s) is completed in save! Action=SEND",
                                row_id, loc.name))
                            emit_check(loc.name)
                        end
                    end
                end)
            end
        end)

        -- 3. Poll Prizes in SaveGame (passive check, is_live = false)
        check_and_award_prizes(gi, false)

        -- 4. Poll Coins in SaveGame (Direct mapping by CoinID 1..30)
        pcall(function()
            if save.CollectedCoins and save.CollectedCoins.ForEach then
                save.CollectedCoins:ForEach(function(arg1, arg2)
                    local elem = arg2 ~= nil and arg2 or arg1
                    local cid = tonumber(get_name_string(elem))
                    if cid and cid >= 1 and cid <= 30 then
                        local loc_name = string.format("Collect Faz Token %02d", cid)
                        local is_checked = emitted_location_names[loc_name] or baseline_location_names[loc_name]
                        local action = (not is_checked) and "SEND" or "IGNORE"
                        awarded_coins[cid] = true
                        if action == "SEND" then
                            print(string.format("[ARCHI] Fazcoin detected in save: CoinID=%d -> Location='%s', Action=SEND", cid, loc_name))
                            emit_check(loc_name)
                        end
                    end
                end)
            end
        end)

        -- 5. Poll Glitch Tapes in SaveGame (Direct mapping by GlitchID)
        pcall(function()
            if save.CollectedGlitches and save.CollectedGlitches.ForEach then
                save.CollectedGlitches:ForEach(function(arg1, arg2)
                    local elem = arg2 ~= nil and arg2 or arg1
                    local gid = tonumber(get_name_string(elem))
                    local loc_name = nil
                    if gid and GLITCH_ID_MAP[gid] then
                        loc_name = GLITCH_ID_MAP[gid]
                    end
                    if loc_name then
                        local is_checked = emitted_location_names[loc_name] or baseline_location_names[loc_name]
                        local action = (not is_checked) and "SEND" or "IGNORE"
                        if action == "SEND" then
                            print(string.format("[ARCHI] Game event detected: Glitch tape in save: GlitchID=%d -> Location='%s', Action=SEND", gid, loc_name))
                            emit_check(loc_name)
                        end
                    end
                end)
            end
        end)

        -- 6. Check GlitchtrapDefeated
        pcall(function()
            if save.GlitchtrapDefeated == true then
                local g_loc = "Goal - Glitchtrap Ending (You Do Not Die)"
                local is_checked = emitted_location_names[g_loc] or baseline_location_names[g_loc]
                local action = (not is_checked) and "SEND" or "IGNORE"
                if action == "SEND" then
                    print("[ARCHI] Game event detected: GlitchtrapDefeated in save! Action=SEND")
                    emit_check(g_loc)
                end
            end
        end)
    end

    local faz_token_noop_logged = false

    -- Received Item Applier. Returns true once the item's effect is in place, false when it cannot be
    -- applied yet (e.g. no game instance during startup): item_sync.lua retries until it succeeds, so
    -- this must report failure honestly instead of swallowing it.
    function ExactHooks.apply_received_item(item_id, item_index)
        local gi = get_game_instance()

        -- Faz Token (Item ID 101000011). VERIFIED in game 2026-10-04: SaveGameRef.PlayerTotalCoins is not
        -- a stored value (it is only the output name of FNAFSaveGame:GetTotalCoinCount; the game derives
        -- the count from the CollectedCoins set), so the old "PlayerTotalCoins += 1" never did anything.
        -- Adding a coin id through UnlockCoin would also fire the "Collect Faz Token N" location hook.
        -- The effect is derived state, owned by faz_tokens.lua (it counts Faz Token items in every
        -- received snapshot and overrides GetTotalCoinCount / writes GameInstance.PlayerCoins), so there is
        -- nothing to apply once per item here.
        if item_id == 101000011 then
            if not faz_token_noop_logged then
                faz_token_noop_logged = true
                print("[GAME] Faz Token items take effect through faz_tokens.lua (derived from the received list)")
            end
            return true
        elseif item_id == 101000010 then
            -- Nightmare Mode License
            if not gi then return false end
            local ok = pcall(function()
                gi.IsInNightmareMode = true
                if gi.EnableNightmareMode then
                    gi:EnableNightmareMode(true)
                end
                print("[FNAFHW AP] Granted Nightmare Mode License!")
            end)
            return ok
        elseif item_id >= 101000002 and item_id <= 101000008 then
            -- Access passes / toolkits: authorization is handled by level_gate.lua
            print(string.format("[FNAFHW AP] Granted Access Pass / Toolkit ID: %d", item_id))
        end
        -- items without a one-shot effect (Glitch Tape, traps, Victory, ...) need nothing yet
        return true
    end

    -- Name of the map the player is in right now ("" when unknown), for modules that must only act inside a level.
    function ExactHooks.current_map_name()
        return get_current_map_name(get_game_instance())
    end

    return ExactHooks
end

return ExactHooks
