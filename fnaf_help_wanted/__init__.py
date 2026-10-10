from typing import Any

from BaseClasses import ItemClassification
from worlds.AutoWorld import WebWorld, World

from .data import GAME_NAME, ITEM_TABLE, ItemData, filler_item_name, unrandomized_items
from .items import ALL_ITEM_TABLE, FNAFHWItem, item_name_to_id
from .levels import MANAGED_ITEM_NAMES, SECTIONS, GatingPlan, build_plan, slot_gate_data
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
            return ItemClassification.progression
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
        # randomized (Glitch Tape with the tape locations, the base Faz Tokens with the token locations): items follow their locations.
        not_randomized = unrandomized_items(
            bool(self.options.randomize_faz_tokens.value), bool(self.options.randomize_glitch_tapes.value))
        pool = []
        for item_name, item_data in ITEM_TABLE.items():
            if item_name in MANAGED_ITEM_NAMES or item_name in not_randomized:
                continue
            for _ in range(item_data.quantity):
                pool.append(self.create_item(item_name))
        for item_name in self.gating_plan.pool_items:
            pool.append(self.create_item(item_name))
        for item_name in self.gating_plan.start_items:
            self.multiworld.push_precollected(self.create_item(item_name))

        unfilled_location_count = len(self.multiworld.get_unfilled_locations(self.player))
        if len(pool) > unfilled_location_count:
            raise Exception(
                f"{self.player_name}: {len(pool)} items for {unfilled_location_count} locations"
            )
        filler_needed = unfilled_location_count - len(pool)
        for _ in range(filler_needed):
            pool.append(self.create_item(self.get_filler_item_name()))

        self.multiworld.itempool += pool

    def set_rules(self) -> None:
        set_rules(self)

    def get_filler_item_name(self) -> str:
        # Faz Token items only while the Faz Tokens are randomized; vanilla tokens get the inert Faz Coupon (see data.filler_item_name)
        return filler_item_name(bool(self.options.randomize_faz_tokens.value))

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
