return function(env)
    local state = env.state

    local victory_scene_entry_prize_count = nil

    local function map_is_level_victory(map_name)
        return env.map_matches_any_keyword(map_name, { "level_victory" })
    end

    local function count_emitted_prize_checks()
        local emitted_count = 0
        for _, location_name in ipairs(env.prize_location_names or {}) do
            if env.emitted_location_names and env.emitted_location_names[location_name] then
                emitted_count = emitted_count + 1
            end
        end
        return emitted_count
    end

    local function handle_victory_scene_transition(previous_map_name, current_map_name)
        local entered_victory = map_is_level_victory(current_map_name)
            and not map_is_level_victory(previous_map_name)
        local exited_victory = map_is_level_victory(previous_map_name)
            and not map_is_level_victory(current_map_name)

        if entered_victory then
            victory_scene_entry_prize_count = count_emitted_prize_checks()
            return
        end

        if not exited_victory then
            return
        end

        local prize_count_before = victory_scene_entry_prize_count
        local prize_count_after = count_emitted_prize_checks()
        victory_scene_entry_prize_count = nil

        if prize_count_before ~= nil and prize_count_after > prize_count_before then
            return
        end

        local awarded = env.award_next_prize_checks(1)
        if awarded > 0 then
            print(
                "[FNAFHW AP] Awarded fallback prize check on Level_Victory exit: "
                    .. tostring(previous_map_name)
                    .. " -> "
                    .. tostring(current_map_name)
            )
        end
    end

    local function poll_auto_map_checks()
        if not env.enable_auto_map_checks then
            return
        end

        if env.map_poll_startup_grace_seconds > 0 then
            local elapsed_since_mod_load = env.now_seconds() - env.mod_started_at
            if elapsed_since_mod_load < env.map_poll_startup_grace_seconds then
                return
            end
        end

        local map_name = env.get_current_map_name()
        if not map_name then
            return
        end

        if map_name == state.last_map_name then
            return
        end

        local previous_map_name = state.last_map_name
        print("[FNAFHW AP] Map changed: " .. tostring(previous_map_name) .. " -> " .. tostring(map_name))

        handle_victory_scene_transition(previous_map_name, map_name)

        local in_hub = env.map_is_hub(map_name)
        if state.active_map_candidate and map_name ~= state.active_map_candidate.map_name then
            local elapsed = env.now_seconds() - state.active_map_candidate.start_time
            local min_seconds = tonumber(state.active_map_candidate.min_seconds) or env.auto_completion_min_seconds
            local should_settle = in_hub or env.settle_on_any_map_exit
            if should_settle then
                if elapsed >= min_seconds then
                    local exits_to_failure_map = env.map_matches_any_keyword(map_name, env.completion_failure_map_keywords)
                    if state.active_map_candidate.location_name then
                        if exits_to_failure_map then
                            print(
                                "[FNAFHW AP] Suppressed map completion check on failure exit: "
                                    .. state.active_map_candidate.location_name
                                    .. " ("
                                    .. tostring(map_name)
                                    .. ")"
                            )
                        else
                            env.APBridge.on_check_earned(state.active_map_candidate.location_name)
                        end
                    end
                    local token_count = tonumber(state.active_map_candidate.token_count or 0) or 0
                    if token_count > 0 then
                        env.award_next_token_checks(token_count)
                    end
                    env.award_tape_checks(state.active_map_candidate.tape_locations)
                    local tape_count = tonumber(state.active_map_candidate.tape_count or 0) or 0
                    if tape_count > 0 then
                        env.award_next_tape_checks(tape_count)
                    end
                    local prize_count = tonumber(state.active_map_candidate.prize_count or 0) or 0
                    if prize_count > 0 then
                        env.award_next_prize_checks(prize_count)
                    end
                    print("[FNAFHW AP] Settled auto-check context on map exit: " .. map_name)
                else
                    local label = state.active_map_candidate.location_name or state.active_map_candidate.map_name or "token award"
                    print(
                        string.format(
                            "[FNAFHW AP] Ignored '%s' (left map too quickly: %ds < %ds)",
                            label,
                            elapsed,
                            min_seconds
                        )
                    )
                end
                state.active_map_candidate = nil
            end
        end

        if in_hub then
            state.last_map_name = map_name
            return
        end

        local matched_candidate = env.resolve_map_check(map_name)
        local matched_location = env.resolve_map_check_location(matched_candidate)
        local token_count = env.resolve_token_award_count(map_name)
        local tape_locations = env.resolve_tape_award_locations(map_name)

        if not env.strict_collectible_checks
            and token_count <= 0
            and env.auto_award_tokens_on_all_gameplay_maps
            and env.should_use_fallback_collectible_awards(map_name)
        then
            token_count = env.default_token_checks_per_map
        end

        local tape_count = 0
        if not env.strict_collectible_checks
            and #tape_locations == 0
            and env.auto_award_tapes_on_all_gameplay_maps
            and env.should_use_fallback_tape_awards(map_name)
        then
            tape_count = env.default_tape_checks_per_map
        end

        if matched_location or token_count > 0 or #tape_locations > 0 or tape_count > 0 then
            local min_seconds = env.resolve_completion_min_seconds(map_name)
            state.active_map_candidate = {
                location_name = matched_location,
                start_time = env.now_seconds(),
                map_name = map_name,
                token_count = token_count,
                tape_locations = tape_locations,
                tape_count = tape_count,
                min_seconds = min_seconds,
            }
            if matched_location then
                print("[FNAFHW AP] Armed auto-check from map: " .. matched_location)
            end
            if token_count > 0 then
                print(string.format("[FNAFHW AP] Armed auto token awards: %d", token_count))
            end
            if #tape_locations > 0 then
                print(string.format("[FNAFHW AP] Armed auto tape checks: %d", #tape_locations))
            end
            if tape_count > 0 then
                print(string.format("[FNAFHW AP] Armed fallback tape checks: %d", tape_count))
            end
            if min_seconds ~= env.auto_completion_min_seconds then
                print(string.format("[FNAFHW AP] Using map-specific min completion: %ds", min_seconds))
            end
        else
            if state.active_map_candidate then
                print(
                    "[FNAFHW AP] Keeping armed auto-check context through intermediate map: "
                        .. map_name
                )
            end
        end

        state.last_map_name = map_name
    end

    return {
        poll_auto_map_checks = poll_auto_map_checks,
    }
end
