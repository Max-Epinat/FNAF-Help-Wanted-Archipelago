return function(env)
    local try_call = env.try_call
    local to_lower = env.to_lower
    local now_seconds = env.now_seconds
    local get_current_map_name = env.get_current_map_name
    local get_last_map_name = env.get_last_map_name
    local get_active_map_candidate = env.get_active_map_candidate

    local contains_all_keywords = env.contains_all_keywords
    local contains_all_keywords_fuzzy = env.contains_all_keywords_fuzzy
    local contains_any_keywords = env.contains_any_keywords
    local contains_any_keywords_fuzzy = env.contains_any_keywords_fuzzy
    local map_is_hub = env.map_is_hub

    local should_log_collectible_telemetry = env.should_log_collectible_telemetry
    local append_collectible_telemetry = env.append_collectible_telemetry

    local collectible_tape_actor_mappings = env.collectible_tape_actor_mappings
    local collectible_prize_actor_mappings = env.collectible_prize_actor_mappings
    local collectible_prize_allowed_map_keywords = env.collectible_prize_allowed_map_keywords
    local collectible_prize_unmapped_awards_next = env.collectible_prize_unmapped_awards_next
    local collectible_actor_excluded_keywords = env.collectible_actor_excluded_keywords
    local collectible_hub_allowed_map_keywords = env.collectible_hub_allowed_map_keywords
    local collectible_hub_allowed_actor_keywords = env.collectible_hub_allowed_actor_keywords
    local collectible_coin_actor_keywords = env.collectible_coin_actor_keywords
    local collectible_tape_actor_keywords = env.collectible_tape_actor_keywords
    local collectible_prize_actor_keywords = env.collectible_prize_actor_keywords
    local collectible_pickup_hook_dedupe_seconds = env.collectible_pickup_hook_dedupe_seconds
    local collectible_actor_name_dedupe_seconds = env.collectible_actor_name_dedupe_seconds
    local enable_coin_identity_lock = env.enable_coin_identity_lock

    local recent_collectible_actor_events = env.recent_collectible_actor_events
    local recent_collectible_identity_events = env.recent_collectible_identity_events
    local collected_coin_identity_keys = env.collected_coin_identity_keys

    local resolve_prize_location_from_mapping = env.resolve_prize_location_from_mapping

    local award_next_token_checks = env.award_next_token_checks
    local award_next_prize_checks = env.award_next_prize_checks
    local APBridge = env.APBridge
    local announce_prize_checks_to_ap_chat = env.announce_prize_checks_to_ap_chat

    local RegisterHook = env.RegisterHook
    local unpack_values = env.unpack_values
    local print = env.print

    local function get_actor_identity(actor)
        local full_name = tostring(try_call(actor, "GetFullName") or "")
        if full_name == "" then
            full_name = tostring(try_call(actor, "GetName") or "")
        end
        return full_name
    end

    local function build_coin_identity_key(current_map, actor_identity)
        local lowered_map = to_lower(current_map)
        local lowered_identity = to_lower(actor_identity)
        if lowered_identity == "" then
            return ""
        end

        local persistent_object = lowered_identity:match("persistentlevel%.([^%s]+)")
        if persistent_object and persistent_object ~= "" then
            -- Keep full persistent object identity so distinct token actors
            -- like ..._CAT_986 and ..._CAT_944 do not collapse to one key.
            return lowered_map .. "|" .. persistent_object
        end

        local compact = lowered_identity:gsub("\r", " "):gsub("\n", " ")
        return lowered_map .. "|" .. compact
    end

    local function resolve_tape_location_from_actor(actor_identity, context_text)
        local lowered_actor = to_lower(actor_identity)
        local lowered_context_text = to_lower(context_text)
        if lowered_actor == "" then
            return nil
        end

        local lowered_context = lowered_actor .. " " .. lowered_context_text

        for _, mapping in ipairs(collectible_tape_actor_mappings) do
            if contains_all_keywords(lowered_actor, mapping.actor_keywords) then
                if #mapping.map_keywords == 0 or contains_all_keywords(lowered_actor, mapping.map_keywords) then
                    return mapping.location_name
                end
            end
        end

        return nil
    end

    local function resolve_prize_location_from_actor(actor_identity, context_text)
        local lowered_actor = to_lower(actor_identity)
        local lowered_context_text = to_lower(context_text)
        if lowered_actor == "" then
            return nil
        end

        local lowered_context = lowered_actor .. " " .. lowered_context_text

        for _, mapping in ipairs(collectible_prize_actor_mappings) do
            if contains_all_keywords_fuzzy(lowered_actor, mapping.actor_keywords) then
                if #mapping.map_keywords == 0 or contains_all_keywords_fuzzy(lowered_actor, mapping.map_keywords) then
                    local resolved_location, reason = resolve_prize_location_from_mapping(mapping)
                    if resolved_location ~= nil then
                        return resolved_location, reason
                    end
                end
            end
        end

        return nil, "no-mapping"
    end

    local function param_to_object(param)
        if param == nil then
            return nil
        end

        if type(param) == "userdata" then
            if param.get then
                local ok, value = pcall(param.get, param)
                if ok and value and value.IsValid and value:IsValid() then
                    return value
                end
            end
            if param.IsValid and param:IsValid() then
                return param
            end
        end

        if type(param) == "table" then
            if type(param.get) == "function" then
                local ok, value = pcall(param.get, param)
                if ok and value and value.IsValid and value:IsValid() then
                    return value
                end
            end
            if param.IsValid and param:IsValid() then
                return param
            end
        end

        return nil
    end

    local function extract_actor_from_hook_args(...)
        local args = { ... }
        for _, arg in ipairs(args) do
            local object = param_to_object(arg)
            if object then
                return object
            end
        end
        return nil
    end

    local function actor_matches_keywords(actor, keywords)
        if actor == nil or #keywords == 0 then
            return false
        end

        local full_name = to_lower(try_call(actor, "GetFullName"))
        local name = to_lower(try_call(actor, "GetName"))

        for _, keyword in ipairs(keywords) do
            if keyword ~= "" then
                if full_name ~= "" and string.find(full_name, keyword, 1, true) then
                    return true
                end
                if name ~= "" and string.find(name, keyword, 1, true) then
                    return true
                end
            end
        end

        return false
    end

    local function is_duplicate_collectible_event(actor)
        if collectible_pickup_hook_dedupe_seconds <= 0 then
            return false
        end

        local address = try_call(actor, "GetAddress")
        if address == nil then
            return false
        end

        local key = tostring(address)
        local current = now_seconds()
        local previous = recent_collectible_actor_events[key]
        recent_collectible_actor_events[key] = current
        if previous == nil then
            return false
        end

        return (current - previous) < collectible_pickup_hook_dedupe_seconds
    end

    local function is_duplicate_collectible_identity_event(identity_key)
        if collectible_actor_name_dedupe_seconds <= 0 then
            return false
        end

        local current = now_seconds()
        local previous = recent_collectible_identity_events[identity_key]
        recent_collectible_identity_events[identity_key] = current
        if previous == nil then
            return false
        end

        return (current - previous) < collectible_actor_name_dedupe_seconds
    end

    local function build_collectible_context_blob(current_map, actor_identity)
        local context_parts = {
            to_lower(actor_identity),
            to_lower(current_map),
            to_lower(get_last_map_name()),
        }

        local active_map_candidate = get_active_map_candidate()
        if active_map_candidate and active_map_candidate.map_name then
            table.insert(context_parts, to_lower(active_map_candidate.map_name))
        end

        return table.concat(context_parts, " ")
    end

    local function on_collectible_actor_event(actor, hook_path)
        if not actor or (actor.IsValid and not actor:IsValid()) then
            return
        end

        local current_map = get_current_map_name()
        if is_duplicate_collectible_event(actor) then
            return
        end

        local actor_identity = get_actor_identity(actor)
        local actor_name_only = tostring(try_call(actor, "GetName") or "")
        local actor_full_name = tostring(try_call(actor, "GetFullName") or "")
        local normalized_identity = to_lower(actor_identity)
        if normalized_identity == "" then
            return
        end

        for _, keyword in ipairs(collectible_actor_excluded_keywords) do
            if keyword ~= "" and string.find(normalized_identity, keyword, 1, true) then
                return
            end
        end

        local context_blob = build_collectible_context_blob(current_map, actor_identity)
        local telemetry_for_event = should_log_collectible_telemetry(current_map, actor_identity)
        local identity_key = normalized_identity .. "|" .. context_blob
        if is_duplicate_collectible_identity_event(identity_key) then
            if telemetry_for_event then
                append_collectible_telemetry("dedupe_identity", {
                    { key = "map", value = current_map },
                    { key = "hook", value = hook_path },
                    { key = "actor", value = actor_identity },
                })
            end
            return
        end

        local matched_coin = actor_matches_keywords(actor, collectible_coin_actor_keywords)
        local matched_tape = actor_matches_keywords(actor, collectible_tape_actor_keywords)
        local matched_prize = actor_matches_keywords(actor, collectible_prize_actor_keywords)
        if not matched_coin and not matched_tape and not matched_prize then
            if telemetry_for_event then
                append_collectible_telemetry("ignored_not_collectible", {
                    { key = "map", value = current_map },
                    { key = "hook", value = hook_path },
                    { key = "actor", value = actor_identity },
                    { key = "name", value = actor_name_only },
                    { key = "full", value = actor_full_name },
                })
            end
            return
        end

        local mapped_tape_location = nil
        if matched_tape then
            mapped_tape_location = resolve_tape_location_from_actor(actor_identity, context_blob)
        end

        local coin_identity_key = ""
        local coin_already_collected = false
        if matched_coin and enable_coin_identity_lock then
            coin_identity_key = build_coin_identity_key(current_map, actor_identity)
            if coin_identity_key ~= "" and collected_coin_identity_keys[coin_identity_key] then
                coin_already_collected = true
            end
        end

        local mapped_prize_location = nil
        local mapped_prize_reason = ""
        local allow_unmapped_prize_award = false
        if matched_prize then
            mapped_prize_location, mapped_prize_reason = resolve_prize_location_from_actor(actor_identity, context_blob)
            if mapped_prize_location == nil and collectible_prize_unmapped_awards_next then
                allow_unmapped_prize_award = contains_any_keywords_fuzzy(to_lower(actor_identity), collectible_prize_allowed_map_keywords)
            end
        end

        if telemetry_for_event then
            append_collectible_telemetry("classified", {
                { key = "map", value = current_map },
                { key = "hook", value = hook_path },
                { key = "actor", value = actor_identity },
                { key = "name", value = actor_name_only },
                { key = "full", value = actor_full_name },
                { key = "coin", value = matched_coin and "1" or "0" },
                { key = "coin_key", value = coin_identity_key },
                { key = "coin_recollect", value = coin_already_collected and "1" or "0" },
                { key = "tape", value = matched_tape and "1" or "0" },
                { key = "prize", value = matched_prize and "1" or "0" },
                { key = "mapped_tape", value = mapped_tape_location or "" },
                { key = "mapped_prize", value = mapped_prize_location or "" },
                { key = "prize_reason", value = mapped_prize_reason or "" },
                { key = "allow_unmapped_prize", value = allow_unmapped_prize_award and "1" or "0" },
                { key = "context", value = context_blob },
            })
        end

        if current_map and map_is_hub(current_map) then
            local allowed_hub_map = contains_any_keywords(to_lower(actor_identity), collectible_hub_allowed_map_keywords)
            local allowed_hub_actor = contains_any_keywords(to_lower(actor_identity), collectible_hub_allowed_actor_keywords)
            local has_explicit_tape_mapping = mapped_tape_location ~= nil
            local has_explicit_prize_mapping = mapped_prize_location ~= nil
            if not allowed_hub_map
                and not allowed_hub_actor
                and not has_explicit_tape_mapping
                and not has_explicit_prize_mapping
                and not allow_unmapped_prize_award
            then
                if telemetry_for_event then
                    append_collectible_telemetry("blocked_hub_gate", {
                        { key = "map", value = current_map },
                        { key = "hook", value = hook_path },
                        { key = "actor", value = actor_identity },
                    })
                end
                return
            end
        end

        if matched_coin then
            if coin_already_collected then
                if telemetry_for_event then
                    append_collectible_telemetry("ignored_coin_recollect", {
                        { key = "map", value = current_map },
                        { key = "hook", value = hook_path },
                        { key = "actor", value = actor_identity },
                        { key = "coin_key", value = coin_identity_key },
                    })
                end
                print(
                    "[FNAFHW AP] Ignored re-collected coin actor: "
                        .. tostring(actor_identity)
                        .. " ["
                        .. tostring(coin_identity_key)
                        .. "]"
                )
            else
                if coin_identity_key ~= "" then
                    collected_coin_identity_keys[coin_identity_key] = true
                end
                local awarded_count = award_next_token_checks(1)
                print(
                    "[FNAFHW AP] Pickup hook coin detected via "
                        .. tostring(hook_path)
                        .. ": "
                        .. tostring(actor_identity)
                        .. " -> token-awards="
                        .. tostring(awarded_count)
                )
            end
        end

        if matched_tape then
            if mapped_tape_location then
                APBridge.on_check_earned(mapped_tape_location)
                print(
                    "[FNAFHW AP] Pickup hook tape detected via "
                        .. tostring(hook_path)
                        .. ": "
                        .. tostring(actor_identity)
                        .. " -> "
                        .. mapped_tape_location
                )
            else
                print(
                    "[FNAFHW AP] Ignored unmatched tape actor: "
                        .. tostring(actor_identity)
                )
            end
        end

        if matched_prize then
            if mapped_prize_location then
                APBridge.on_check_earned(mapped_prize_location)
                if announce_prize_checks_to_ap_chat then
                    APBridge.say("[FNAFHW] Prize check sent: " .. tostring(mapped_prize_location))
                end
                if telemetry_for_event then
                    append_collectible_telemetry("award_prize_mapped", {
                        { key = "map", value = current_map },
                        { key = "hook", value = hook_path },
                        { key = "actor", value = actor_identity },
                        { key = "location", value = mapped_prize_location },
                        { key = "reason", value = mapped_prize_reason or "" },
                    })
                end
                print(
                    "[FNAFHW AP] Pickup hook prize detected via "
                        .. tostring(hook_path)
                        .. ": "
                        .. tostring(actor_identity)
                        .. " -> "
                        .. mapped_prize_location
                        .. ((mapped_prize_reason ~= "") and (" [" .. tostring(mapped_prize_reason) .. "]") or "")
                )
            elseif allow_unmapped_prize_award then
                award_next_prize_checks(1)
                if telemetry_for_event then
                    append_collectible_telemetry("award_prize_unmapped_next", {
                        { key = "map", value = current_map },
                        { key = "hook", value = hook_path },
                        { key = "actor", value = actor_identity },
                    })
                end
                print(
                    "[FNAFHW AP] Pickup hook unmapped prize actor detected via "
                        .. tostring(hook_path)
                        .. ": "
                        .. tostring(actor_identity)
                        .. " -> awarded next prize check"
                )
            else
                if telemetry_for_event then
                    append_collectible_telemetry("ignored_unmapped_prize", {
                        { key = "map", value = current_map },
                        { key = "hook", value = hook_path },
                        { key = "actor", value = actor_identity },
                    })
                end
                print(
                    "[FNAFHW AP] Ignored unmatched prize actor: "
                        .. tostring(actor_identity)
                )
            end
        end
    end

    local function register_collectible_pickup_hooks()
        if not env.enable_collectible_pickup_hooks then
            print("[FNAFHW AP] Collectible pickup hooks disabled in config")
            return
        end

        if not RegisterHook then
            print("[FNAFHW AP] RegisterHook unavailable; collectible pickup hooks disabled")
            return
        end

        local registered = 0
        for _, hook_path in ipairs(env.collectible_pickup_hook_paths) do
            if hook_path ~= "" then
                local ok, err = pcall(function()
                    RegisterHook(hook_path, function(...)
                        local hook_args = { ... }
                        local callback_ok, callback_err = pcall(function()
                            local actor = extract_actor_from_hook_args(unpack_values(hook_args))
                            on_collectible_actor_event(actor, hook_path)
                        end)
                        if not callback_ok then
                            print("[FNAFHW AP] Collectible hook callback error: " .. tostring(callback_err))
                        end
                    end)
                end)

                if ok then
                    registered = registered + 1
                    print("[FNAFHW AP] Registered collectible pickup hook: " .. hook_path)
                else
                    print(
                        "[FNAFHW AP] Failed to register collectible pickup hook "
                            .. hook_path
                            .. ": "
                            .. tostring(err)
                    )
                end
            end
        end

        if registered == 0 then
            print("[FNAFHW AP] No collectible pickup hooks registered")
        end
    end

    return {
        register_collectible_pickup_hooks = register_collectible_pickup_hooks,
        on_collectible_actor_event = on_collectible_actor_event,
    }
end
