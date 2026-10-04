return function(ctx)
    local RegisterConsoleCommandHandler = ctx.RegisterConsoleCommandHandler
    if not RegisterConsoleCommandHandler then
        print("[FNAFHW AP] RegisterConsoleCommandHandler not available; use keybinds only")
        return
    end

    local function join_parameters(parameters, start_index)
        local result = ""
        for i = start_index, #parameters, 1 do
            if i > start_index then
                result = result .. " "
            end
            result = result .. tostring(parameters[i])
        end
        return result
    end

    RegisterConsoleCommandHandler("ap_check_name", function(full_command, parameters)
        if #parameters < 1 then
            print("[FNAFHW AP] Usage: ap_check_name <exact location name>")
            return true
        end

        local location_name = join_parameters(parameters, 1)
        ctx.APBridge.send_location_check_name(location_name)
        print("[FNAFHW AP] Sent location check by name: " .. location_name)
        return true
    end)

    RegisterConsoleCommandHandler("ap_check_id", function(full_command, parameters)
        if #parameters < 1 then
            print("[FNAFHW AP] Usage: ap_check_id <location id>")
            return true
        end

        ctx.APBridge.send_location_check(parameters[1])
        print("[FNAFHW AP] Sent location check by id: " .. tostring(parameters[1]))
        return true
    end)

    RegisterConsoleCommandHandler("ap_goal", function(full_command, parameters)
        ctx.APBridge.send_goal()
        print("[FNAFHW AP] Sent goal")
        return true
    end)

    RegisterConsoleCommandHandler("ap_say", function(full_command, parameters)
        if #parameters < 1 then
            print("[FNAFHW AP] Usage: ap_say <message>")
            return true
        end

        local message = join_parameters(parameters, 1)
        ctx.APBridge.say(message)
        print("[FNAFHW AP] Sent chat: " .. message)
        return true
    end)

    RegisterConsoleCommandHandler("ap_sync", function(full_command, parameters)
        ctx.append_outbox("SYNC")
        print("[FNAFHW AP] Sent sync")
        return true
    end)

    RegisterConsoleCommandHandler("ap_map", function(full_command, parameters)
        local map_name = ctx.get_current_map_name() or "<unknown>"
        print("[FNAFHW AP] Current map: " .. map_name)
        return true
    end)

    RegisterConsoleCommandHandler("ap_auto_status", function(full_command, parameters)
        print(
            string.format(
                "[FNAFHW AP] Auto map checks: %s | map candidates: %d | token candidates: %d | tape candidates: %d | token fallback: %s (%d/map) | tape fallback: %s (%d/map) | collectible strict mode: %s | base min seconds: %d | map min overrides: %d | settle on any map exit: %s",
                ctx.enable_auto_map_checks and "enabled" or "disabled",
                #ctx.auto_map_checks,
                #ctx.auto_token_awards,
                #ctx.auto_tape_checks,
                ctx.auto_award_tokens_on_all_gameplay_maps and "on" or "off",
                ctx.default_token_checks_per_map,
                ctx.auto_award_tapes_on_all_gameplay_maps and "on" or "off",
                ctx.default_tape_checks_per_map,
                ctx.strict_collectible_checks and "on" or "off",
                ctx.auto_completion_min_seconds,
                #ctx.completion_min_seconds_by_map,
                ctx.settle_on_any_map_exit and "yes" or "no"
            )
        )
        if #ctx.fallback_collectible_excluded_keywords > 0 then
            print(
                string.format(
                    "[FNAFHW AP] Fallback collectible excludes active (%d keyword entries)",
                    #ctx.fallback_collectible_excluded_keywords
                )
            )
        end
        if #ctx.fallback_tape_allowed_keywords > 0 then
            print(
                string.format(
                    "[FNAFHW AP] Fallback tape allowlist active (%d keyword entries)",
                    #ctx.fallback_tape_allowed_keywords
                )
            )
        end
        return true
    end)

    RegisterConsoleCommandHandler("ap_collectible_debug_status", function(full_command, parameters)
        print(
            string.format(
                "[FNAFHW AP] Collectible telemetry: %s | file: %s | map filters: %d | prize mappings: %d | unmapped prize fallback: %s",
                ctx.enable_collectible_debug_telemetry and "enabled" or "disabled",
                ctx.collectible_debug_telemetry_file,
                #ctx.collectible_debug_map_keywords,
                #ctx.collectible_prize_actor_mappings,
                ctx.collectible_prize_unmapped_awards_next and "on" or "off"
            )
        )
        return true
    end)

    print("[FNAFHW AP] Console commands registered: ap_check_name, ap_check_id, ap_goal, ap_say, ap_sync, ap_map, ap_auto_status, ap_collectible_debug_status")
end
