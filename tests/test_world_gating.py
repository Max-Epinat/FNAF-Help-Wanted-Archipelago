"""World-side level gating: items, plan, rules (as data), slot_data.

`fnaf_help_wanted/__init__.py` imports Archipelago, which is not available in the dev environment, so the
pure modules (data.py, levels.py) are loaded by path, like scripts/generate_locations_json.py does. The
Archipelago-dependent glue (options.py, __init__.py, rules.py) is checked statically with ast.
"""

import ast
import importlib.util
import itertools
import json
import re
import sys
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ap_client.main import format_gate_items_line, format_gate_table_line

WORLD_DIR = project_root / "fnaf_help_wanted"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"_fnafhw_{name}", WORLD_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses need the module registered
    spec.loader.exec_module(module)
    return module


data = _load("data")
levels = _load("levels")

BASE_ITEM_CODES = {
    "Glitch Tape": 1, "FNAF 1 Access Pass": 2, "FNAF 2 Access Pass": 3, "FNAF 3 Access Pass": 4,
    "Parts and Service Toolkit": 5, "Vent Repair Toolkit": 6, "Dark Rooms Flashlight": 7,
    "Night Terrors Security Badge": 8, "Prize Counter Key": 9, "Nightmare Mode License": 10,
    "Faz Token": 11, "Hallucination": 12, "Victory": 13,
}

ALL_ITEM_CODES = {**{n: d.code for n, d in data.ITEM_TABLE.items()}, **levels.APPENDED_ITEM_CODES}
ITEM_NAME_TO_ID = {name: data.ITEM_OFFSET + code for name, code in ALL_ITEM_CODES.items()}

ALL_COMBINATIONS = list(itertools.product(
    (levels.UNLOCK_PER_SECTION, levels.UNLOCK_PER_LEVEL),
    (levels.HARD_GROUPED, levels.HARD_SEPARATE),
    [s.key for s in levels.SECTIONS],
))


def reachable(plan, items):
    """Level locations whose required items are all held (exactly what rules.py enforces)."""
    return {loc for loc, needed in plan.location_items.items() if needed <= set(items)}


class TestItemCodes(unittest.TestCase):
    def test_existing_item_codes_are_unchanged(self):
        self.assertEqual({n: d.code for n, d in data.ITEM_TABLE.items()}, BASE_ITEM_CODES)

    def test_appended_codes_are_new_unique_and_contiguous(self):
        codes = sorted(levels.APPENDED_ITEM_CODES.values())
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(codes, list(range(14, 14 + len(codes))))
        self.assertFalse(set(codes) & set(BASE_ITEM_CODES.values()))

    def test_item_names_are_unique_and_do_not_shadow_base_items(self):
        names = list(levels.APPENDED_ITEM_CODES)
        self.assertEqual(len(names), len(set(names)))
        self.assertFalse(set(names) & set(data.ITEM_TABLE))

    def test_item_counts(self):
        self.assertEqual(len(levels.HARD_ITEM_CODES), 6)  # Night Terrors has no hard variant
        self.assertEqual(len(levels.LEVEL_ITEM_CODES), 40)

    def test_section_items_are_the_existing_items(self):
        for section in levels.SECTIONS:
            self.assertIn(section.item, data.ITEM_TABLE)


class TestLevelTable(unittest.TestCase):
    def test_levels_cover_exactly_the_minigame_and_night_checks(self):
        self.assertEqual({lv.location for lv in levels.LEVELS}, set(data.MINIGAME_AND_NIGHT_CHECKS))
        self.assertEqual(len(levels.LEVELS), len(data.MINIGAME_AND_NIGHT_CHECKS))

    def test_pizza_party_is_never_a_level(self):
        self.assertNotIn(29, levels.LEVEL_BY_ROW)
        self.assertNotIn("Complete Pizza Party", levels.LEVEL_BY_LOCATION)

    def test_rows_match_the_generated_row_table_from_LevelInfoTable(self):
        generated = json.loads(
            (project_root / "ue4ss_mod" / "FNAFHWArchipelago" / "locations.json").read_text(encoding="utf-8")
        )["row_id_to_location"]
        for level in levels.LEVELS:
            self.assertEqual(generated[str(level.row)]["name"], level.location, f"row {level.row}")

    def test_row_1_2_3_sections_and_existing_default_gate(self):
        self.assertEqual(levels.LEVEL_BY_ROW[5].gate, "FNAF1_NIGHT2")  # the mod's built-in default gate

    def test_gate_ids_are_valid_and_unique(self):
        pattern = re.compile(r"^[A-Z0-9_]+$")
        gates = [lv.gate for lv in levels.LEVELS]
        self.assertEqual(len(gates), len(set(gates)))
        section_gates = [g for s in levels.SECTIONS for g in (s.gate, s.hard_gate) if g]
        self.assertEqual(len(section_gates), len(set(section_gates)))
        self.assertFalse(set(gates) & set(section_gates))
        for gate in gates + section_gates:
            self.assertRegex(gate, pattern)

    def test_levels_have_no_previous_level_chain(self):
        # an item alone unlocks its level in game, so the table carries no prerequisite column
        for level in levels.LEVELS:
            self.assertFalse(hasattr(level, "after_rows"))

    def test_first_levels(self):
        firsts = {s.key: levels.first_level(s.key).location for s in levels.SECTIONS}
        self.assertEqual(firsts["fnaf_1"], "Beat FNAF 1 - Night 1")
        self.assertEqual(firsts["parts_and_service"], "Complete Parts and Service - Bonnie")
        self.assertEqual(firsts["dark_rooms"], "Complete Dark Rooms - Plushtrap")
        self.assertEqual(firsts["night_terrors"], "Complete Night Terrors - Funtime Freddy")  # lowest row (25)


class TestOptionsSource(unittest.TestCase):
    """options.py needs Archipelago to import, so read it statically."""

    def _choice_values(self, class_name):
        tree = ast.parse((WORLD_DIR / "options.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return {
                    stmt.targets[0].id[len("option_"):]: stmt.value.value
                    for stmt in node.body
                    if isinstance(stmt, ast.Assign) and stmt.targets[0].id.startswith("option_")
                }
        self.fail(f"{class_name} not found")

    def test_starting_section_values_follow_section_order(self):
        values = self._choice_values("StartingSection")
        self.assertEqual([k for k, _ in sorted(values.items(), key=lambda kv: kv[1])],
                         [s.key for s in levels.SECTIONS])

    def test_unlock_mode_and_hard_variants_values(self):
        self.assertEqual(self._choice_values("UnlockMode"),
                         {"per_section": levels.UNLOCK_PER_SECTION, "per_level": levels.UNLOCK_PER_LEVEL})
        self.assertEqual(self._choice_values("HardVariants"),
                         {"grouped": levels.HARD_GROUPED, "separate": levels.HARD_SEPARATE})

    def test_options_dataclass_lists_the_new_options(self):
        text = (WORLD_DIR / "options.py").read_text(encoding="utf-8")
        for field in ("unlock_mode: UnlockMode", "hard_variants: HardVariants", "starting_section: StartingSection",
                      "death_link: DeathLink"):
            self.assertIn(field, text)


class TestDeathLinkGiftBoxOption(unittest.TestCase):
    """`death_link_gift_box`: a DefaultOnToggle (on = the gift box game over sends a DeathLink, as before), carried in slot_data."""

    def setUp(self):
        self.options = (WORLD_DIR / "options.py").read_text(encoding="utf-8")
        self.world = (WORLD_DIR / "__init__.py").read_text(encoding="utf-8")

    def test_it_is_a_toggle_that_is_on_by_default(self):
        tree = ast.parse(self.options)
        classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
        self.assertIn("DeathLinkGiftBox", classes)
        self.assertEqual([base.id for base in classes["DeathLinkGiftBox"].bases], ["DefaultOnToggle"])
        self.assertIn("DefaultOnToggle", re.search(r"from Options import (.*)", self.options).group(1))

    def test_it_is_a_field_of_the_options_dataclass(self):
        self.assertIn("death_link_gift_box: DeathLinkGiftBox", self.options)

    def test_its_text_says_it_only_matters_with_deathlink_and_only_for_sending(self):
        doc = ast.get_docstring(next(n for n in ast.parse(self.options).body if isinstance(n, ast.ClassDef) and n.name == "DeathLinkGiftBox")).lower()
        self.assertIn("gift box", doc)
        self.assertIn("death_link", doc)
        self.assertIn("sends", doc)

    def test_slot_data_carries_it_as_a_bool(self):
        self.assertIn('"death_link_gift_box": bool(self.options.death_link_gift_box.value)', self.world)
class TestPlanInvariants(unittest.TestCase):
    """Properties that must hold for every option combination."""

    def test_every_combination(self):
        base_quantity = sum(d.quantity for n, d in data.ITEM_TABLE.items() if n not in levels.MANAGED_ITEM_NAMES)
        unfilled = data.ACTIVE_LOCATION_COUNT - 1  # goal location holds the locked Victory; undetectable prizes are not created
        for mode, hard, start in ALL_COMBINATIONS:
            with self.subTest(mode=mode, hard=hard, start=start):
                plan = levels.build_plan(mode, hard, start)
                managed = list(plan.pool_items) + list(plan.start_items)
                self.assertEqual(len(managed), len(set(managed)), "duplicate managed item")
                self.assertTrue(set(managed) <= levels.MANAGED_ITEM_NAMES)
                self.assertTrue(set(plan.start_items) <= set(plan.gate_items))
                self.assertLessEqual(base_quantity + len(plan.pool_items), unfilled)
                # Pizza Party is never gated, every other level always is
                self.assertNotIn(29, plan.level_gates)
                self.assertEqual(set(plan.level_gates), {lv.row for lv in levels.LEVELS})
                # every gate in the table can be authorized by some item that exists in this seed
                gates = set(plan.level_gates.values())
                self.assertEqual(gates, set(plan.gate_items.values()))
                self.assertTrue(set(plan.gate_items) <= set(managed))
                # completable: with the whole managed pool, every level is reachable
                self.assertEqual(reachable(plan, managed), set(plan.location_items))
                # a level needs exactly one managed item: its own gate item, never the items of other levels
                for level in levels.LEVELS:
                    needed = plan.location_items[level.location]
                    self.assertEqual(len(needed), 1)
                    self.assertTrue(needed <= set(plan.gate_items))
                # Pizza Party is never gated but needs every level in logic (its vanilla condition is UNVERIFIED)
                pizza = plan.location_items[levels.PIZZA_PARTY_LOCATION]
                self.assertEqual(pizza, frozenset().union(*(plan.location_items[lv.location] for lv in levels.LEVELS)))
                for item in managed:
                    self.assertNotIn(levels.PIZZA_PARTY_LOCATION, reachable(plan, set(managed) - {item}),
                                     f"Pizza Party reachable without {item}")

    def test_invalid_arguments_raise(self):
        for args in ((2, 0, "fnaf_1"), (0, 2, "fnaf_1"), (0, 0, "nope")):
            with self.assertRaises(ValueError):
                levels.build_plan(*args)


class TestPerSection(unittest.TestCase):
    def test_grouped_default(self):
        plan = levels.build_plan(levels.UNLOCK_PER_SECTION, levels.HARD_GROUPED, "fnaf_1")
        self.assertEqual(plan.start_items, ("FNAF 1 Access Pass",))
        self.assertEqual(len(plan.pool_items), 6)
        self.assertFalse(set(plan.pool_items) & set(levels.HARD_ITEM_CODES))
        # the start item alone opens FNAF 1 including its hard night, nothing else
        opened = reachable(plan, plan.start_items)
        self.assertEqual(opened, {lv.location for lv in levels.LEVELS if lv.section == "fnaf_1"})
        self.assertEqual(plan.level_gates[4], "FNAF1")
        self.assertEqual(plan.level_gates[8], "FNAF1")
        self.assertEqual(plan.gate_items, {s.item: s.gate for s in levels.SECTIONS})

    def test_grouped_hard_minigame_needs_only_the_section_item(self):
        plan = levels.build_plan(levels.UNLOCK_PER_SECTION, levels.HARD_GROUPED, "fnaf_1")
        self.assertEqual(plan.location_items["Complete Parts and Service (Hard) - Bonnie"],
                         frozenset({"Parts and Service Toolkit"}))

    def test_separate_hard_needs_its_own_item(self):
        plan = levels.build_plan(levels.UNLOCK_PER_SECTION, levels.HARD_SEPARATE, "fnaf_1")
        self.assertEqual(len(plan.pool_items), 6 + 6)
        opened = reachable(plan, plan.start_items)
        self.assertIn("Beat FNAF 1 - Night 4", opened)
        self.assertNotIn("Beat FNAF 1 - Night 5 (Hard)", opened)
        with_hard = reachable(plan, plan.start_items + ("FNAF 1 Hard Pass",))
        self.assertIn("Beat FNAF 1 - Night 5 (Hard)", with_hard)
        self.assertEqual(plan.level_gates[8], "FNAF1_HARD")
        self.assertEqual(plan.gate_items["FNAF 1 Hard Pass"], "FNAF1_HARD")

    def test_separate_hard_item_alone_unlocks_the_hard_level(self):
        plan = levels.build_plan(levels.UNLOCK_PER_SECTION, levels.HARD_SEPARATE, "fnaf_1")
        self.assertIn("Beat FNAF 1 - Night 5 (Hard)", reachable(plan, ["FNAF 1 Hard Pass"]))
        self.assertNotIn("Beat FNAF 1 - Night 4", reachable(plan, ["FNAF 1 Hard Pass"]))
        self.assertEqual(plan.location_items["Complete Dark Rooms (Hard) - Plushtrap"],
                         frozenset({"Dark Rooms Hard Flashlight"}))

    def test_withered_needs_only_the_fnaf2_hard_item(self):
        plan = levels.build_plan(levels.UNLOCK_PER_SECTION, levels.HARD_SEPARATE, "fnaf_1")
        self.assertEqual(plan.location_items["Beat FNAF 2 - Withered"], frozenset({"FNAF 2 Hard Pass"}))

    def test_night_terrors_has_no_hard_item(self):
        plan = levels.build_plan(levels.UNLOCK_PER_SECTION, levels.HARD_SEPARATE, "night_terrors")
        self.assertEqual(plan.start_items, ("Night Terrors Security Badge",))
        self.assertNotIn(None, plan.gate_items)

    def test_each_starting_section_opens_only_itself(self):
        for section in levels.SECTIONS:
            plan = levels.build_plan(levels.UNLOCK_PER_SECTION, levels.HARD_GROUPED, section.key)
            opened = reachable(plan, plan.start_items)
            self.assertEqual(opened, {lv.location for lv in levels.LEVELS if lv.section == section.key})


class TestItemAloneAndPizzaParty(unittest.TestCase):
    def test_item_alone_unlocks_its_level_in_logic(self):
        plan = levels.build_plan(levels.UNLOCK_PER_LEVEL, levels.HARD_GROUPED, "fnaf_1")
        for item, location in (
            ("Unlock FNAF 1 - Night 3", "Beat FNAF 1 - Night 3"),
            ("Unlock Parts and Service - Foxy", "Complete Parts and Service - Foxy"),
            ("Unlock Parts and Service (Hard) - Chica", "Complete Parts and Service (Hard) - Chica"),
            ("Unlock Night Terrors - Nightmare Fredbear", "Complete Night Terrors - Nightmare Fredbear"),
            ("Unlock FNAF 2 - Withered", "Beat FNAF 2 - Withered"),
        ):
            self.assertEqual(plan.location_items[location], frozenset({item}))
            self.assertIn(location, reachable(plan, {item}))

    def test_section_mode_item_unlocks_the_whole_section(self):
        plan = levels.build_plan(levels.UNLOCK_PER_SECTION, levels.HARD_GROUPED, "fnaf_1")
        self.assertEqual(plan.location_items["Complete Parts and Service - Foxy"], frozenset({"Parts and Service Toolkit"}))

    def test_pizza_party_needs_everything_and_has_no_gate(self):
        for mode in (levels.UNLOCK_PER_SECTION, levels.UNLOCK_PER_LEVEL):
            plan = levels.build_plan(mode, levels.HARD_SEPARATE, "fnaf_3")
            pizza = plan.location_items[levels.PIZZA_PARTY_LOCATION]
            self.assertEqual(pizza, frozenset(plan.pool_items) | frozenset(plan.start_items))
            self.assertNotIn(29, plan.level_gates)


class TestPerLevel(unittest.TestCase):
    def setUp(self):
        self.plan = levels.build_plan(levels.UNLOCK_PER_LEVEL, levels.HARD_GROUPED, "fnaf_1")

    def test_start_is_only_the_first_level_of_the_section(self):
        self.assertEqual(self.plan.start_items, ("Unlock FNAF 1 - Night 1",))
        self.assertEqual(reachable(self.plan, self.plan.start_items), {"Beat FNAF 1 - Night 1"})
        self.assertEqual(len(self.plan.pool_items), 39)

    def test_section_and_hard_section_items_are_not_used(self):
        self.assertFalse(set(self.plan.pool_items) & set(levels.SECTION_ITEM_NAMES))
        self.assertFalse(set(self.plan.pool_items) & set(levels.HARD_ITEM_CODES))

    def test_every_level_has_its_own_item_and_gate(self):
        self.assertEqual(len(self.plan.gate_items), 40)
        self.assertEqual(len(set(self.plan.level_gates.values())), 40)
        self.assertEqual(self.plan.level_gates[5], "FNAF1_NIGHT2")
        self.assertEqual(self.plan.gate_items["Unlock FNAF 1 - Night 2"], "FNAF1_NIGHT2")

    def test_hard_variants_option_is_ignored(self):
        other = levels.build_plan(levels.UNLOCK_PER_LEVEL, levels.HARD_SEPARATE, "fnaf_1")
        self.assertEqual(self.plan, other.__class__(**{**other.__dict__, "hard_variants": levels.HARD_GROUPED}))

    def test_item_alone_does_not_need_the_previous_level(self):
        items = set(self.plan.start_items) | {"Unlock FNAF 1 - Night 3"}
        self.assertIn("Beat FNAF 1 - Night 3", reachable(self.plan, items))  # without Night 1 and Night 2
        self.assertNotIn("Beat FNAF 1 - Night 2", reachable(self.plan, items))

    def test_hard_level_needs_only_its_own_item(self):
        items = {"Unlock Parts and Service (Hard) - Bonnie"}
        self.assertIn("Complete Parts and Service (Hard) - Bonnie", reachable(self.plan, items))

    def test_starting_section_changes_the_start_item(self):
        plan = levels.build_plan(levels.UNLOCK_PER_LEVEL, levels.HARD_GROUPED, "vent_repair")
        self.assertEqual(plan.start_items, ("Unlock Vent Repair - Mangle",))
        self.assertEqual(len(plan.pool_items), 39)


class TestSlotData(unittest.TestCase):
    def test_tables_are_forwardable_by_the_client_for_every_combination(self):
        lua_pair = re.compile(r"^(\d+)=([A-Z0-9_]+)$")  # same shape as level_gate.lua's parsers
        for mode, hard, start in ALL_COMBINATIONS:
            with self.subTest(mode=mode, hard=hard, start=start):
                plan = levels.build_plan(mode, hard, start)
                slot = levels.slot_gate_data(plan, ITEM_NAME_TO_ID)
                json.dumps(slot)  # must be JSON-serializable
                table = format_gate_table_line(slot["level_gates"])
                items = format_gate_items_line(slot["gate_items"])
                self.assertIsNotNone(table)
                self.assertIsNotNone(items)
                table_pairs = table.split(" ", 1)[1].split(",")
                item_pairs = items.split(" ", 1)[1].split(",")
                self.assertEqual(len(table_pairs), len(plan.level_gates))  # nothing dropped
                self.assertEqual(len(item_pairs), len(plan.gate_items))
                for pair in table_pairs + item_pairs:
                    self.assertRegex(pair, lua_pair)

    def test_gate_items_use_real_item_ids(self):
        plan = levels.build_plan(levels.UNLOCK_PER_SECTION, levels.HARD_GROUPED, "fnaf_1")
        slot = levels.slot_gate_data(plan, ITEM_NAME_TO_ID)
        self.assertEqual(slot["gate_items"][str(data.ITEM_OFFSET + 2)], "FNAF1")  # FNAF 1 Access Pass
        self.assertEqual(slot["level_gates"]["5"], "FNAF1")


class TestWorldGlueSource(unittest.TestCase):
    """__init__.py / rules.py need Archipelago; make sure they use the plan consistently."""

    def test_world_uses_the_plan(self):
        init = (WORLD_DIR / "__init__.py").read_text(encoding="utf-8")
        for needle in ("generate_early", "build_plan(", "push_precollected", "slot_gate_data(", "MANAGED_ITEM_NAMES"):
            self.assertIn(needle, init)
        rules = (WORLD_DIR / "rules.py").read_text(encoding="utf-8")
        self.assertIn("gating_plan.location_items", rules)

    def test_modules_parse(self):
        for name in ("__init__", "options", "rules", "items", "regions", "levels", "data"):
            ast.parse((WORLD_DIR / f"{name}.py").read_text(encoding="utf-8"))



class TestUnlockItemsOnlyOnLevelLocations(unittest.TestCase):
    """The fill must never put a level's unlock item where the player can only get it by being inside a gated level.

    Only level locations are gated in the logic (each needs its own unlock item, VERIFIED in game). Where a tape, a Faz Token or a prize physically is
    is not modelled, so an unlock item on one of those could sit behind the very level it unlocks and the seed could not be finished. Keeping the
    unlock items on level-completion locations makes every unlock item obtainable by playing levels the player already has.
    (Found with the real generator: before this rule every seed put unlock items on tapes, tokens, prizes, the trophies or the blackjack win.)
    """

    OPTIONS = [(mode, hard, section) for mode in (levels.UNLOCK_PER_SECTION, levels.UNLOCK_PER_LEVEL)
               for hard in (levels.HARD_GROUPED, levels.HARD_SEPARATE) for section in levels.SECTION_BY_KEY]

    def test_only_the_forty_level_locations_may_hold_unlock_items(self):
        level_locations = {level.location for level in levels.LEVELS}
        self.assertEqual(len(level_locations), 40)
        for names in data.ACTIVE_REGION_LOCATIONS.values():
            for name in names:
                self.assertEqual(levels.may_hold_unlock_item(name), name in level_locations, name)
        for name in (levels.PIZZA_PARTY_LOCATION, "Collect Glitch Tape 02", "Collect Faz Token 01", "Win Prize Counter Blackjack",
                     "Collect All Hub Trophies", "Collect Prize Counter Intro Tape"):
            self.assertFalse(levels.may_hold_unlock_item(name), name)

    def test_every_item_a_plan_hands_out_is_restricted(self):
        for options in self.OPTIONS:
            plan = levels.build_plan(*options)
            self.assertLessEqual(set(plan.pool_items) | set(plan.start_items), set(levels.MANAGED_ITEM_NAMES), options)

    def test_there_is_always_room_for_every_unlock_item(self):
        """Each unlock item needs its own level location, and never the one it opens (that location requires it). A perfect matching must exist."""
        for options in self.OPTIONS:
            plan = levels.build_plan(*options)
            items = list(plan.pool_items)
            spots = {item: [loc for loc, needed in plan.location_items.items()
                            if loc != levels.PIZZA_PARTY_LOCATION and item not in needed] for item in items}
            owner = {}

            def place(item, seen):
                for loc in spots[item]:
                    if loc in seen:
                        continue
                    seen.add(loc)
                    if loc not in owner or place(owner[loc], seen):
                        owner[loc] = item
                        return True
                return False

            unplaced = [item for item in items if not place(item, set())]
            self.assertEqual(unplaced, [], options)

    def test_rules_py_applies_the_restriction(self):
        rules = (WORLD_DIR / "rules.py").read_text(encoding="utf-8")
        for needle in ("add_item_rule", "may_hold_unlock_item", "MANAGED_ITEM_NAMES"):
            self.assertIn(needle, rules)


class TestNightmareLogicIsGone(unittest.TestCase):
    """`nightmare_logic` was an invented extra requirement (the Nightmare Mode License is not a progression item, so a goal that needed it could never be generated)."""

    def test_the_option_the_slot_data_and_the_template_no_longer_have_it(self):
        for path in ("options.py", "__init__.py"):
            self.assertNotIn("nightmare_logic", (WORLD_DIR / path).read_text(encoding="utf-8"), path)
        self.assertNotIn("nightmare_logic", (project_root / "templates" / "Five Nights at Freddy's Help Wanted.yaml").read_text(encoding="utf-8"))
        self.assertNotIn("nightmare_logic", (project_root / "README.md").read_text(encoding="utf-8"))

    def test_only_the_hard_mode_goal_still_asks_for_the_license(self):
        """Still true today and still a generation failure (the item is `useful`, not progression): see docs/TODO.md, "Logic to check"."""
        rules = (WORLD_DIR / "rules.py").read_text(encoding="utf-8")
        self.assertEqual(rules.count("Nightmare Mode License"), 1)


class TestUndetectablePrizes(unittest.TestCase):
    """24 of the 81 prize locations have no save prize id, so nothing can ever report them: they are not created in a multiworld,
    but their ids stay (location ids are append-only)."""

    def setUp(self):
        from ap_client.save_reader import DEFAULT_PRIZE_MAP
        self.detectable = set(DEFAULT_PRIZE_MAP.values())

    def test_the_undetectable_set_is_exactly_the_prizes_the_client_cannot_map(self):
        self.assertEqual(set(data.UNDETECTABLE_PRIZE_CHECKS), set(data.PRIZE_CHECKS) - self.detectable)
        self.assertEqual(len(data.UNDETECTABLE_PRIZE_CHECKS), 24)
        self.assertEqual(len(data.ACTIVE_PRIZE_CHECKS), 57)

    def test_every_prize_location_a_multiworld_creates_can_be_detected(self):
        created = {name for names in data.ACTIVE_REGION_LOCATIONS.values() for name in names}
        self.assertEqual(created & set(data.PRIZE_CHECKS), set(data.ACTIVE_PRIZE_CHECKS))
        self.assertLessEqual(set(data.ACTIVE_PRIZE_CHECKS), self.detectable)
        self.assertFalse(created & set(data.UNDETECTABLE_PRIZE_CHECKS))

    def test_nothing_but_those_prizes_is_left_out(self):
        every = {name for names in data.REGION_LOCATIONS.values() for name in names}
        created = {name for names in data.ACTIVE_REGION_LOCATIONS.values() for name in names}
        self.assertEqual(every - created, set(data.UNDETECTABLE_PRIZE_CHECKS))
        self.assertEqual(data.ACTIVE_LOCATION_COUNT, len(created))
        self.assertEqual(data.ACTIVE_LOCATION_COUNT, 153)
        # no region lost its other locations or its order
        for region, names in data.REGION_LOCATIONS.items():
            self.assertEqual(data.ACTIVE_REGION_LOCATIONS[region], [n for n in names if n not in data.UNDETECTABLE_PRIZE_CHECKS])

    def test_location_ids_never_move(self):
        """Append-only: the full table keeps every id, including the left-out prizes and everything after them."""
        table = data.LOCATION_TABLE
        self.assertEqual(len(table), 177)
        pinned = {
            "Collect All Hub Trophies": 1, "Collect Prize Counter Intro Tape": 10, "Win Prize Counter Blackjack": 26,
            "Prize - Plushie: Freddy Plush": 27, "Prize - Plushie: Golden Freddy Plush": 31, "Prize - Other: Mystery Box": 84,
            "Prize - Toy: Toy Robot": 107, "Collect Faz Token 01": 108, "Beat FNAF 1 - Night 1": 138,
            "Complete Night Terrors - Nightmarionne": 177,
        }
        for name, code in pinned.items():
            self.assertEqual(table[name].code, code, name)
        self.assertEqual(sorted(entry.code for entry in table.values()), list(range(1, 178)))
        for name in data.UNDETECTABLE_PRIZE_CHECKS:
            self.assertIn(name, table)

    def test_the_full_clear_goal_never_asks_for_a_location_that_does_not_exist(self):
        created = {name for names in data.ACTIVE_REGION_LOCATIONS.values() for name in names}
        self.assertLessEqual(set(data.FULL_CLEAR_CHECKS), created)
        self.assertLessEqual(set(data.MINIGAME_AND_NIGHT_CHECKS), created)

    def test_the_world_creates_regions_from_the_active_table(self):
        regions = (WORLD_DIR / "regions.py").read_text(encoding="utf-8")
        # regions.py asks data.region_locations(...), which starts from ACTIVE_REGION_LOCATIONS (all on == that table, see test_location_groups.py)
        self.assertIn("region_locations(", regions)
        self.assertNotIn("REGION_LOCATIONS.get", regions)
        self.assertEqual(data.region_locations(True, True, True), data.ACTIVE_REGION_LOCATIONS)

    def test_the_location_counters_in_the_two_interfaces_match(self):
        """Both interfaces show the real total of the seed (location groups can be off); 153 is only their default when none is known."""
        for path in ("ap_client/main.py", "ue4ss_mod/FNAFHWArchipelago/Scripts/lib/connection_ui.lua"):
            text = (project_root / path).read_text(encoding="utf-8")
            self.assertIn(str(data.ACTIVE_LOCATION_COUNT), text, path)
            self.assertNotIn("177", text, path)


if __name__ == "__main__":
    unittest.main()
