from worlds.generic.Rules import add_item_rule, add_rule, set_rule

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
from .levels import MANAGED_ITEM_NAMES, may_hold_unlock_item


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

    goal_all = multiworld.get_location(GOAL_COMPLETE_ALL_MINIGAMES, player)
    goal_hard = multiworld.get_location(GOAL_COMPLETE_ALL_MINIGAMES_HARD, player)
    goal_die = multiworld.get_location(GOAL_GLITCHTRAP_DIE, player)
    goal_survive = multiworld.get_location(GOAL_GLITCHTRAP_SURVIVE, player)
    goal_100 = multiworld.get_location(GOAL_HUNDRED_PERCENT, player)
    goal_quota = multiworld.get_location(GOAL_TOKEN_TAPE_QUOTA, player)

    # Level access: the gate item(s) plus the previous level of the chain. location_items already
    # contains the items of every level earlier in the chain, so this is equivalent to
    # "has the gate item and can reach the previous level" without a recursive can_reach.
    for location_name, required_items in world.gating_plan.location_items.items():
        set_rule(
            multiworld.get_location(location_name, player),
            lambda state, items=required_items: state.has_all(items, player),
        )

    def can_reach_all(state, checks: list[str]) -> bool:
        return all(state.can_reach(name, "Location", player) for name in checks)

    add_rule(
        goal_all,
        lambda state: can_reach_all(state, MINIGAME_AND_NIGHT_CHECKS),
    )

    add_rule(
        goal_hard,
        lambda state: can_reach_all(state, MINIGAME_AND_NIGHT_CHECKS)
        and state.can_reach("Complete Pizza Party", "Location", player)
        and state.has("Nightmare Mode License", player),
    )

    die_items = has_tapes_and_tokens(GOAL_GLITCHTRAP_DIE)
    add_rule(
        goal_die,
        lambda state: state.can_reach("Complete Pizza Party", "Location", player) and die_items(state),
    )

    survive_items = has_tapes_and_tokens(GOAL_GLITCHTRAP_SURVIVE)
    add_rule(
        goal_survive,
        lambda state: state.can_reach("Complete Pizza Party", "Location", player)
        and survive_items(state)
        and state.has("Prize Counter Key", player),
    )

    # the 100 % goal only names locations that exist: a group that is not randomized has none (its list shrinks with the toggles)
    full_clear = full_clear_checks(prizes_on, tokens_on, tapes_on)
    full_items = has_tapes_and_tokens(GOAL_HUNDRED_PERCENT)
    add_rule(
        goal_100,
        lambda state: can_reach_all(state, full_clear) and full_items(state),
    )

    add_rule(goal_quota, has_tapes_and_tokens(GOAL_TOKEN_TAPE_QUOTA))

    # Unlock items only on level-completion locations: where tapes, tokens and prizes physically are is not modelled, so an unlock item there
    # could be unreachable in the real game (see levels.may_hold_unlock_item).
    for location in multiworld.get_locations(player):
        if not may_hold_unlock_item(location.name):
            add_item_rule(location, lambda item, p=player: item.player != p or item.name not in MANAGED_ITEM_NAMES)

    multiworld.completion_condition[player] = lambda state, p=player: state.has("Victory", p)
