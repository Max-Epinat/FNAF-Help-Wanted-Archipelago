from BaseClasses import LocationProgressType
from worlds.generic.Rules import add_rule, set_rule

from .data import (
    GOAL_COMPLETE_ALL_MINIGAMES,
    GOAL_COMPLETE_ALL_MINIGAMES_HARD,
    GOAL_GLITCHTRAP_DIE,
    GOAL_GLITCHTRAP_SURVIVE,
    GOAL_HUNDRED_PERCENT,
    GOAL_TOKEN_TAPE_QUOTA,
    MINIGAME_AND_NIGHT_CHECKS,
    full_clear_checks,
    tape_token_requirements,
)
from .levels import FILLER_ONLY_CHECKS


GOAL_LOCATION_BY_ID = {
    0: GOAL_COMPLETE_ALL_MINIGAMES,
    1: GOAL_COMPLETE_ALL_MINIGAMES_HARD,
    2: GOAL_GLITCHTRAP_DIE,
    3: GOAL_GLITCHTRAP_SURVIVE,
    4: GOAL_HUNDRED_PERCENT,
    5: GOAL_TOKEN_TAPE_QUOTA,
}


def get_goal_location_name(goal_value: int) -> str:
    return GOAL_LOCATION_BY_ID.get(goal_value, GOAL_COMPLETE_ALL_MINIGAMES)


def set_rules(world) -> None:
    player = world.player
    multiworld = world.multiworld

    required_tapes = world.options.required_tapes.value
    required_faz_tokens = world.options.required_faz_tokens.value
    prizes_on = bool(world.options.randomize_prizes.value)
    tokens_on = bool(world.options.randomize_faz_tokens.value)
    tapes_on = bool(world.options.randomize_glitch_tapes.value)

    def has_tapes_and_tokens(goal_name: str):
        """Item part of a goal. A group that is not randomized has no items, so the logic does not ask for them (see data.tape_token_requirements)."""
        tapes_needed, tokens_needed = tape_token_requirements(goal_name, required_tapes, required_faz_tokens, tapes_on, tokens_on)
        return lambda state: (
            (tapes_needed <= 0 or state.has("Glitch Tape", player, tapes_needed))
            and (tokens_needed <= 0 or state.has("Faz Token", player, tokens_needed))
        )

    goal_name = get_goal_location_name(world.options.goal.value)
    existing = {location.name: location for location in multiworld.get_locations(player)}

    # Levels need their own unlock item; Pizza Party, the tape / token pickups and the filler-only checks need ALL the items listed in the plan
    # (every level played on the pickup's map, read from the game's files: see levels.PICKUP_MAPS). Only locations this seed created get a rule.
    for location_name, required_items in world.gating_plan.location_items.items():
        if location_name in existing:
            set_rule(existing[location_name], lambda state, items=required_items: state.has_all(items, player))

    # A prize is a random award after any level win (every prize not owned yet comes out eventually), so any one level item is enough.
    any_level = world.gating_plan.any_level_items
    for location_name, location in existing.items():
        if location_name.startswith("Prize - ") and location_name not in FILLER_ONLY_CHECKS:
            set_rule(location, lambda state, items=any_level: state.has_any(items, player))

    # Checks the game sends but whose condition is not known for sure: only filler may land there. Glitchtrap "You Do Not Die" too when it is
    # not the goal (it is a real check, sent from the save, but what the real game needs for it is not modelled).
    for location_name in FILLER_ONLY_CHECKS | ({GOAL_GLITCHTRAP_SURVIVE} - {goal_name}):
        if location_name in existing:
            existing[location_name].progress_type = LocationProgressType.EXCLUDED

    def can_reach_all(state, checks: list[str]) -> bool:
        return all(state.can_reach(name, "Location", player) for name in checks)

    die_items = has_tapes_and_tokens(GOAL_GLITCHTRAP_DIE)
    survive_items = has_tapes_and_tokens(GOAL_GLITCHTRAP_SURVIVE)
    # the 100 % goal only names locations that exist: a group that is not randomized has none (its list shrinks with the toggles)
    full_clear = full_clear_checks(prizes_on, tokens_on, tapes_on)
    full_items = has_tapes_and_tokens(GOAL_HUNDRED_PERCENT)
    goal_rules = {
        GOAL_COMPLETE_ALL_MINIGAMES: lambda state: can_reach_all(state, MINIGAME_AND_NIGHT_CHECKS),
        # every level (hard ones included) plus Pizza Party; the nightmare license item is not asked for: the game ends the multiworld on Pizza Party anyway
        GOAL_COMPLETE_ALL_MINIGAMES_HARD: lambda state: can_reach_all(state, MINIGAME_AND_NIGHT_CHECKS)
        and state.can_reach("Complete Pizza Party", "Location", player),
        GOAL_GLITCHTRAP_DIE: lambda state: state.can_reach("Complete Pizza Party", "Location", player) and die_items(state),
        GOAL_GLITCHTRAP_SURVIVE: lambda state: state.can_reach("Complete Pizza Party", "Location", player)
        and survive_items(state)
        and state.has("Prize Counter Key", player),
        GOAL_HUNDRED_PERCENT: lambda state: can_reach_all(state, full_clear) and full_items(state),
        GOAL_TOKEN_TAPE_QUOTA: has_tapes_and_tokens(GOAL_TOKEN_TAPE_QUOTA),
    }
    if goal_name in existing:
        add_rule(existing[goal_name], goal_rules[goal_name])
    # Glitchtrap "You Do Not Die" exists in every seed (the client sends it); when it is not the goal it is filler only, so like the other
    # filler-only checks it only needs every level (its tape / Key requirement could name tapes that are filler in this seed).
    survive_is_goal = goal_name == GOAL_GLITCHTRAP_SURVIVE
    if not survive_is_goal and GOAL_GLITCHTRAP_SURVIVE in existing:
        every_level = world.gating_plan.location_items["Complete Pizza Party"]
        set_rule(existing[GOAL_GLITCHTRAP_SURVIVE], lambda state, items=every_level: state.has_all(items, player))

    multiworld.completion_condition[player] = lambda state, p=player: state.has("Victory", p)
