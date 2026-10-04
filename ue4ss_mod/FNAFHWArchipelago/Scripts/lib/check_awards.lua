return function(env)
    local to_lower = env.to_lower
    local contains_all_keywords = env.contains_all_keywords
    local map_is_hub = env.map_is_hub

    local emitted_location_names = env.emitted_location_names

    local strict_collectible_checks = env.strict_collectible_checks
    local enable_auto_token_awards = env.enable_auto_token_awards
    local auto_token_awards = env.auto_token_awards
    local enable_auto_tape_checks = env.enable_auto_tape_checks
    local auto_tape_checks = env.auto_tape_checks
    local completion_min_seconds_by_map = env.completion_min_seconds_by_map
    local auto_completion_min_seconds = env.auto_completion_min_seconds
    local fallback_collectible_excluded_keywords = env.fallback_collectible_excluded_keywords
    local fallback_tape_allowed_keywords = env.fallback_tape_allowed_keywords

    local token_location_names = env.token_location_names
    local tape_location_names = env.tape_location_names
    local prize_location_names = env.prize_location_names
    local APBridge = env.APBridge

    local function resolve_next_location_name(location_name, location_names, allow_already_emitted)
        if type(location_name) == "string" and location_name ~= "" then
            if allow_already_emitted or not emitted_location_names[location_name] then
                return location_name
            end
        end

        if type(location_names) == "table" then
            for _, candidate_name in ipairs(location_names) do
                if type(candidate_name) == "string" and candidate_name ~= "" then
                    if allow_already_emitted or not emitted_location_names[candidate_name] then
                        return candidate_name
                    end
                end
            end
        end

        return nil
    end

    local keyword_hint_stopwords = {
        prize = true,
        rare = true,
        common = true,
        beingused = true,
        c = true,
        v2 = true,
    }

    local function build_keyword_hints(keyword)
        local hints = {}
        local text = tostring(keyword or "")
        if text == "" then
            return hints
        end

        text = text:gsub("(%l)(%u)", "%1 %2")
        text = to_lower(text):gsub("[^%w]+", " ")

        for token in string.gmatch(text, "%w+") do
            if #token >= 2 and not keyword_hint_stopwords[token] and not token:match("^%d+$") then
                table.insert(hints, token)
                if #token > 2 and token:sub(-2) == "af" then
                    local stem = token:sub(1, -3)
                    if #stem >= 3 then
                        table.insert(hints, stem)
                    end
                    table.insert(hints, "action")
                    table.insert(hints, "figure")
                end
                if token == "plushy" then
                    table.insert(hints, "plush")
                end
            end
        end

        return hints
    end

    local function score_location_name_for_keyword(location_name, keyword)
        local location_text = to_lower(location_name)
        local compact_location = location_text:gsub("[^%w]+", "")
        local score = 0
        local lowered_keyword = to_lower(keyword)

        for _, hint in ipairs(build_keyword_hints(keyword)) do
            local compact_hint = hint:gsub("[^%w]+", "")
            if compact_hint ~= "" and string.find(compact_location, compact_hint, 1, true) then
                score = score + math.min(12, 2 + #compact_hint)
            elseif string.find(location_text, hint, 1, true) then
                score = score + 4
            end
        end

        if string.find(lowered_keyword, "af", 1, true) and string.find(location_text, "action figure", 1, true) then
            score = score + 14
        end
        if string.find(lowered_keyword, "plush", 1, true) and string.find(location_text, "plushie", 1, true) then
            score = score + 14
        end
        if string.find(lowered_keyword, "bobble", 1, true) and string.find(location_text, "bobblehead", 1, true) then
            score = score + 14
        end

        return score
    end

    local function resolve_prize_location_from_mapping(mapping)
        local candidates = {}

        if type(mapping.location_name) == "string"
            and mapping.location_name ~= ""
            and not emitted_location_names[mapping.location_name]
        then
            table.insert(candidates, mapping.location_name)
        end

        if type(mapping.location_names) == "table" then
            for _, candidate_name in ipairs(mapping.location_names) do
                if type(candidate_name) == "string"
                    and candidate_name ~= ""
                    and not emitted_location_names[candidate_name]
                then
                    table.insert(candidates, candidate_name)
                end
            end
        end

        if #candidates == 0 then
            return nil, "no-unchecked-location"
        end

        if #candidates == 1 then
            return candidates[1], "single-location"
        end

        local best_name = nil
        local best_score = -1
        local tied = false

        for _, candidate_name in ipairs(candidates) do
            local score = 0
            for _, keyword in ipairs(mapping.actor_keywords) do
                score = score + score_location_name_for_keyword(candidate_name, keyword)
            end

            if score > best_score then
                best_score = score
                best_name = candidate_name
                tied = false
            elseif score == best_score then
                tied = true
            end
        end

        if best_name ~= nil and best_score > 0 and not tied then
            return best_name, "keyword-score=" .. tostring(best_score)
        end

        return candidates[1], "fallback-order"
    end

    local function resolve_map_check_location(candidate)
        if not candidate then
            return nil
        end

        return resolve_next_location_name(candidate.location_name, candidate.location_names, false)
    end

    local function resolve_token_award_count(map_name)
        if strict_collectible_checks then
            return 0
        end

        if not enable_auto_token_awards then
            return 0
        end

        local lowered = to_lower(map_name)
        for _, candidate in ipairs(auto_token_awards) do
            if contains_all_keywords(lowered, candidate.keywords) then
                local count = tonumber(candidate.count) or 0
                if count > 0 then
                    return count
                end
            end
        end

        return 0
    end

    local function resolve_tape_award_locations(map_name)
        local result = {}
        if strict_collectible_checks then
            return result
        end

        if not enable_auto_tape_checks then
            return result
        end

        local lowered = to_lower(map_name)
        for _, candidate in ipairs(auto_tape_checks) do
            if contains_all_keywords(lowered, candidate.keywords) then
                table.insert(result, candidate.location_name)
            end
        end

        return result
    end

    local function resolve_completion_min_seconds(map_name)
        local lowered = to_lower(map_name)
        for _, candidate in ipairs(completion_min_seconds_by_map) do
            if contains_all_keywords(lowered, candidate.keywords) then
                local min_seconds = tonumber(candidate.min_seconds) or 0
                if min_seconds > 0 then
                    return min_seconds
                end
            end
        end
        return auto_completion_min_seconds
    end

    local function should_use_fallback_collectible_awards(map_name)
        if map_name == nil or map_name == "" then
            return false
        end

        if map_is_hub(map_name) then
            return false
        end

        local lowered = to_lower(map_name)
        for _, keyword in ipairs(fallback_collectible_excluded_keywords) do
            if keyword ~= "" and string.find(lowered, keyword, 1, true) then
                return false
            end
        end

        if string.find(lowered, "level_victory", 1, true) then
            return false
        end
        if string.find(lowered, "level_gameover", 1, true) then
            return false
        end

        return true
    end

    local function should_use_fallback_tape_awards(map_name)
        if not should_use_fallback_collectible_awards(map_name) then
            return false
        end

        if #fallback_tape_allowed_keywords == 0 then
            return true
        end

        local lowered = to_lower(map_name)
        for _, keyword in ipairs(fallback_tape_allowed_keywords) do
            if keyword ~= "" and string.find(lowered, keyword, 1, true) then
                return true
            end
        end

        return false
    end

    local function award_next_token_checks(count)
        local awarded = 0
        for _, location_name in ipairs(token_location_names) do
            if awarded >= count then
                break
            end

            if not emitted_location_names[location_name] then
                APBridge.on_check_earned(location_name)
                awarded = awarded + 1
            end
        end

        if awarded > 0 then
            print(string.format("[FNAFHW AP] Auto-awarded %d Faz Token checks", awarded))
        else
            print("[FNAFHW AP] No remaining Faz Token checks to auto-award")
        end

        return awarded
    end

    local function award_tape_checks(location_names)
        if type(location_names) ~= "table" then
            return
        end

        local awarded = 0
        for _, location_name in ipairs(location_names) do
            if type(location_name) == "string" and location_name ~= "" then
                local was_emitted = emitted_location_names[location_name] == true
                APBridge.on_check_earned(location_name)
                if not was_emitted and emitted_location_names[location_name] then
                    awarded = awarded + 1
                end
            end
        end

        if awarded > 0 then
            print(string.format("[FNAFHW AP] Auto-awarded %d tape checks", awarded))
        end
    end

    local function award_next_tape_checks(count)
        local awarded = 0
        for _, location_name in ipairs(tape_location_names) do
            if awarded >= count then
                break
            end

            if not emitted_location_names[location_name] then
                APBridge.on_check_earned(location_name)
                awarded = awarded + 1
            end
        end

        if awarded > 0 then
            print(string.format("[FNAFHW AP] Auto-awarded %d tape checks", awarded))
        end
    end

    local function award_next_prize_checks(count)
        local awarded = 0
        for _, location_name in ipairs(prize_location_names) do
            if awarded >= count then
                break
            end

            if not emitted_location_names[location_name] then
                APBridge.on_check_earned(location_name)
                awarded = awarded + 1
            end
        end

        if awarded > 0 then
            print(string.format("[FNAFHW AP] Auto-awarded %d prize checks", awarded))
        else
            print("[FNAFHW AP] No remaining prize checks to auto-award")
        end
    end

    return {
        resolve_map_check_location = resolve_map_check_location,
        resolve_prize_location_from_mapping = resolve_prize_location_from_mapping,
        resolve_token_award_count = resolve_token_award_count,
        resolve_tape_award_locations = resolve_tape_award_locations,
        resolve_completion_min_seconds = resolve_completion_min_seconds,
        should_use_fallback_collectible_awards = should_use_fallback_collectible_awards,
        should_use_fallback_tape_awards = should_use_fallback_tape_awards,
        award_next_token_checks = award_next_token_checks,
        award_tape_checks = award_tape_checks,
        award_next_tape_checks = award_next_tape_checks,
        award_next_prize_checks = award_next_prize_checks,
    }
end
