from typing import Any

from BaseClasses import ItemClassification
from Options import OptionError
from worlds.AutoWorld import WebWorld, World

from .data import (GAME_NAME, GOAL_GLITCHTRAP_SURVIVE, ITEM_TABLE, TAPE_ITEM_NAMES, ItemData, filler_item_name, pick_progression_tapes,
                   tape_token_requirements, trim_to_fit, unrandomized_items)
from .items import ALL_ITEM_TABLE, FNAFHWItem, item_name_to_id
from .levels import FILLER_ONLY_CHECKS, MANAGED_ITEM_NAMES, SECTIONS, GatingPlan, build_plan, slot_gate_data
from .locations import location_name_to_id
from .options import FNAFHWOptions
from .regions import create_regions
from .rules import get_goal_location_name, set_rules


class FNAFHWWebWorld(WebWorld):
    pass


class FNAFHWWorld(World):
    game = GAME_NAME
    web = FNAFHWWebWorld()
    options_dataclass = FNAFHWOptions
    options: FNAFHWOptions
    topology_present = True

    item_name_to_id = item_name_to_id
    location_name_to_id = location_name_to_id

    gating_plan: GatingPlan

    def generate_early(self) -> None:
        self.gating_plan = build_plan(
            self.options.unlock_mode.value,
            self.options.hard_variants.value,
            SECTIONS[self.options.starting_section.value].key,
        )

    def create_regions(self) -> None:
        create_regions(self)

    @staticmethod
    def _get_item_classification(item_data: ItemData) -> ItemClassification:
        if item_data.trap:
            return ItemClassification.trap
        if item_data.progression:
            return ItemClassification.progression_skip_balancing if item_data.skip_balancing else ItemClassification.progression
        if item_data.useful:
            return ItemClassification.useful
        return ItemClassification.filler

    def create_item(self, name: str) -> FNAFHWItem:
        item_data = ALL_ITEM_TABLE[name]
        return FNAFHWItem(
            name,
            self._get_item_classification(item_data),
            item_name_to_id[name],
            self.player,
        )

    def create_items(self) -> None:
        goal_location_name = get_goal_location_name(self.options.goal.value)
        goal_location = self.multiworld.get_location(goal_location_name, self.player)
        goal_location.place_locked_item(self.create_item("Victory"))

        # Section / hard / per-level items are decided by the unlock plan, everything else is fixed, except the items of a group that is not
        # randomized (the 16 tape items with the tape locations, the base Faz Tokens with the token locations): items follow their locations.
        not_randomized = unrandomized_items(
            bool(self.options.randomize_faz_tokens.value), bool(self.options.randomize_glitch_tapes.value))
        names = []
        for item_name, item_data in ITEM_TABLE.items():
            if item_name in MANAGED_ITEM_NAMES or item_name in not_randomized:
                continue
            names += [item_name] * item_data.quantity
        names += self.gating_plan.pool_items
        for item_name in self.gating_plan.start_items:
            self.multiworld.push_precollected(self.create_item(item_name))

        unfilled_location_count = len(self.multiworld.get_unfilled_locations(self.player))
        # Only as many tape items / Faz Tokens are progression as the goal needs; the others are filler (a Faz Token is the same item and id
        # either way: the game counts them all). Which tape items stay progression is picked at random per seed (any of them counts for the goal).
        tapes_needed, tokens_needed = tape_token_requirements(
            goal_location_name, self.options.required_tapes.value, self.options.required_faz_tokens.value,
            bool(self.options.randomize_glitch_tapes.value), bool(self.options.randomize_faz_tokens.value))
        progression_tapes = pick_progression_tapes(self.random, tapes_needed)
        still_progression = {"Faz Token": tokens_needed}
        pool = []
        # the tightest plan has one item too many: drop the License (then a trap), never an item a rule needs (data.trim_to_fit)
        for item_name in trim_to_fit(names, unfilled_location_count):
            if item_name in TAPE_ITEM_NAMES:
                pool.append(self.create_item(item_name) if item_name in progression_tapes
                            else FNAFHWItem(item_name, ItemClassification.filler, item_name_to_id[item_name], self.player))
            elif item_name in still_progression:
                progression = still_progression[item_name] > 0
                still_progression[item_name] -= 1
                pool.append(self.create_item(item_name) if progression
                            else FNAFHWItem(item_name, ItemClassification.filler, item_name_to_id[item_name], self.player))
            else:
                pool.append(self.create_item(item_name))

        # A seed whose progression items cannot fit in the checks that may hold them cannot be generated: say which options to change.
        holders = [loc for loc in self.multiworld.get_unfilled_locations(self.player)
                   if loc.name not in FILLER_ONLY_CHECKS and loc.name != GOAL_GLITCHTRAP_SURVIVE]
        progression_count = sum(1 for item in pool if item.advancement)
        if progression_count > len(holders):
            raise OptionError(
                f"{self.player_name}: this FNAF Help Wanted seed has {progression_count} important items but only {len(holders)} checks that can "
                f"hold them (goal {self.options.goal.current_key}). Turn randomize_prizes on, use unlock_mode per_section, or lower "
                f"required_tapes / required_faz_tokens.")
        if len(pool) > unfilled_location_count:
            raise Exception(
                f"{self.player_name}: {len(pool)} items for {unfilled_location_count} locations"
            )
        filler_needed = unfilled_location_count - len(pool)
        for _ in range(filler_needed):
            pool.append(self.create_filler())

        self.multiworld.itempool += pool

    def set_rules(self) -> None:
        set_rules(self)

    def get_filler_item_name(self) -> str:
        # Faz Token items only while the Faz Tokens are randomized; vanilla tokens get the inert Faz Coupon (see data.filler_item_name)
        return filler_item_name(bool(self.options.randomize_faz_tokens.value))

    def create_filler(self) -> FNAFHWItem:
        # Always plain filler: create_item of a Faz Token gives one of the progression base tokens (also what start_inventory and plando get), the spare
        # slots must not add more of those. Same name and id, so the game counts both kinds alike.
        name = self.get_filler_item_name()
        return FNAFHWItem(name, ItemClassification.filler, item_name_to_id[name], self.player)

    def fill_slot_data(self) -> dict[str, Any]:
        return {
            "goal": self.options.goal.value,
            "required_tapes": self.options.required_tapes.value,
            "required_faz_tokens": self.options.required_faz_tokens.value,
            "death_link": bool(self.options.death_link.value),
            "death_link_gift_box": bool(self.options.death_link_gift_box.value),
            "unlock_mode": self.options.unlock_mode.value,
            "hard_variants": self.options.hard_variants.value,
            "starting_section": self.options.starting_section.value,
            "randomize_prizes": bool(self.options.randomize_prizes.value),
            "randomize_faz_tokens": bool(self.options.randomize_faz_tokens.value),
            "randomize_glitch_tapes": bool(self.options.randomize_glitch_tapes.value),
            **slot_gate_data(self.gating_plan, item_name_to_id),
            "item_name_to_id": item_name_to_id,
            "location_name_to_id": location_name_to_id,
        }


def _register_launcher_component() -> None:
    """Add "FNAF Help Wanted Client" to the Archipelago launcher. Guarded: generation must never depend on it."""
    try:
        from worlds.LauncherComponents import Component, components
    except Exception:
        return

    def run_client(*args):
        from multiprocessing import Process

        from .client import main  # lazy: the client framework is only imported when the client is launched

        Process(target=main, args=(list(args),)).start()  # the launcher's arguments (e.g. --connect host:port)

    try:
        from worlds.LauncherComponents import Type

        components.append(Component("FNAF Help Wanted Client", func=run_client, component_type=Type.CLIENT))
    except Exception:
        components.append(Component("FNAF Help Wanted Client", func=run_client))


_register_launcher_component()
