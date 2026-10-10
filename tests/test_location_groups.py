"""The three location-group toggles: `randomize_prizes`, `randomize_faz_tokens`, `randomize_glitch_tapes` (all default on).

A group that is off is NOT randomized: its locations do not exist in the multiworld (their ids stay in the table), its items
(Glitch Tape, the 30 base Faz Tokens) are not in the pool, and the game keeps its own behaviour for it (vanilla).
The pure logic lives in data.py and is tested here with the real data; the Archipelago glue is read statically (the real generator
runs in test_location_groups_generator.py).
"""

import ast
import importlib.util
import itertools
import sys
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
WORLD_DIR = project_root / "fnaf_help_wanted"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"_fnafhw_{name}", WORLD_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


data = _load("data")
levels = _load("levels")

# (prizes, faz_tokens, tapes)
COMBINATIONS = list(itertools.product((True, False), repeat=3))
UNLOCK_OPTIONS = [(mode, hard, "fnaf_1") for mode in (levels.UNLOCK_PER_SECTION, levels.UNLOCK_PER_LEVEL)
                  for hard in (levels.HARD_GROUPED, levels.HARD_SEPARATE)]


def created(prizes, faz_tokens, tapes):
    return [name for names in data.region_locations(prizes, faz_tokens, tapes).values() for name in names]


class TestLocationsPerCombination(unittest.TestCase):
    def test_the_location_count_is_the_always_there_part_plus_each_group_that_is_on(self):
        for prizes, tokens, tapes in COMBINATIONS:
            with self.subTest(prizes=prizes, tokens=tokens, tapes=tapes):
                expected = 50 + 57 * prizes + 30 * tokens + 16 * tapes  # 50 = levels, hub, goals, Blackjack
                self.assertEqual(len(created(prizes, tokens, tapes)), expected)

    def test_all_on_is_exactly_the_table_of_today(self):
        self.assertEqual(data.region_locations(True, True, True), data.ACTIVE_REGION_LOCATIONS)
        self.assertEqual(data.region_locations(), data.ACTIVE_REGION_LOCATIONS)  # the default is all on
        self.assertEqual(len(created(True, True, True)), 153)

    def test_a_group_that_is_off_has_no_locations_and_one_that_is_on_has_all_of_them(self):
        groups = {"prizes": data.ACTIVE_PRIZE_CHECKS, "faz_tokens": data.FAZ_TOKEN_CHECKS, "tapes": data.GLITCH_TAPE_CHECKS}
        self.assertEqual({key: len(value) for key, value in groups.items()}, {"prizes": 57, "faz_tokens": 30, "tapes": 16})
        for combo in COMBINATIONS:
            names = set(created(*combo))
            for flag, (key, members) in zip(combo, groups.items()):
                with self.subTest(combo=combo, group=key):
                    self.assertEqual(set(members) <= names, flag)
                    self.assertEqual(bool(set(members) & names), flag)

    def test_levels_hub_goals_and_blackjack_are_always_there(self):
        always = set(data.MINIGAME_AND_NIGHT_CHECKS) | {
            "Collect All Hub Trophies", "Complete Pizza Party", "Complete Normal Ending", "Win Prize Counter Blackjack",
            data.GOAL_COMPLETE_ALL_MINIGAMES, data.GOAL_COMPLETE_ALL_MINIGAMES_HARD, data.GOAL_GLITCHTRAP_DIE,
            data.GOAL_GLITCHTRAP_SURVIVE, data.GOAL_HUNDRED_PERCENT, data.GOAL_TOKEN_TAPE_QUOTA}
        for combo in COMBINATIONS:
            with self.subTest(combo=combo):
                self.assertLessEqual(always, set(created(*combo)))

    def test_regions_keep_their_names_and_the_order_of_their_locations(self):
        for combo in COMBINATIONS:
            regions = data.region_locations(*combo)
            self.assertEqual(list(regions), list(data.ACTIVE_REGION_LOCATIONS))
            for region, names in regions.items():
                full = data.ACTIVE_REGION_LOCATIONS[region]
                self.assertEqual(names, [name for name in full if name in names], (combo, region))

    def test_location_ids_do_not_move_whatever_the_toggles(self):
        table = data.LOCATION_TABLE
        self.assertEqual(sorted(entry.code for entry in table.values()), list(range(1, 178)))
        for combo in COMBINATIONS:
            self.assertLessEqual(set(created(*combo)), set(table))
        self.assertEqual(table["Collect Faz Token 01"].code, 108)
        self.assertEqual(table["Prize - Plushie: Freddy Plush"].code, 27)
        self.assertEqual(table["Collect Prize Counter Intro Tape"].code, 10)

    def test_a_location_group_never_contains_an_undetectable_prize(self):
        self.assertFalse(set(data.ACTIVE_PRIZE_CHECKS) & set(data.UNDETECTABLE_PRIZE_CHECKS))
        self.assertFalse(set(created(True, True, True)) & set(data.UNDETECTABLE_PRIZE_CHECKS))


class TestFullClearList(unittest.TestCase):
    def test_the_100_percent_list_only_names_locations_that_exist(self):
        for combo in COMBINATIONS:
            with self.subTest(combo=combo):
                self.assertLessEqual(set(data.full_clear_checks(*combo)), set(created(*combo)))

    def test_it_keeps_everything_else_and_loses_only_the_groups_that_are_off(self):
        self.assertEqual(data.full_clear_checks(True, True, True), data.FULL_CLEAR_CHECKS)
        none = set(data.full_clear_checks(False, False, False))
        self.assertEqual(set(data.FULL_CLEAR_CHECKS) - none,
                         set(data.ACTIVE_PRIZE_CHECKS) | set(data.FAZ_TOKEN_CHECKS) | set(data.GLITCH_TAPE_CHECKS))
        self.assertIn("Complete Pizza Party", none)
        self.assertIn("Win Prize Counter Blackjack", none)
        self.assertIn("Collect All Hub Trophies", none)


class TestPoolPerCombination(unittest.TestCase):
    """Items follow their locations: no Glitch Tape without tape locations, no base Faz Token without token locations."""

    def pool(self, combo, unlock):
        prizes, tokens, tapes = combo
        off = data.unrandomized_items(tokens, tapes)
        plan = levels.build_plan(*unlock)
        base = {name: item.quantity for name, item in data.ITEM_TABLE.items()
                if name not in levels.MANAGED_ITEM_NAMES and name not in off}
        return base, plan

    def test_the_items_of_a_group_that_is_off_are_not_in_the_pool(self):
        self.assertEqual(data.unrandomized_items(True, True), frozenset())
        self.assertEqual(data.unrandomized_items(False, True), frozenset({"Faz Token"}))
        self.assertEqual(data.unrandomized_items(True, False), frozenset({"Glitch Tape"}))
        self.assertEqual(data.unrandomized_items(False, False), frozenset({"Faz Token", "Glitch Tape"}))
        self.assertFalse(data.unrandomized_items(False, False) & levels.MANAGED_ITEM_NAMES)
        self.assertFalse(data.unrandomized_items(False, False) - set(data.ITEM_TABLE))  # only real, existing items

    def test_the_pool_always_fits_and_the_freed_slots_become_filler(self):
        for combo in COMBINATIONS:
            for unlock in UNLOCK_OPTIONS:
                with self.subTest(combo=combo, unlock=unlock):
                    base, plan = self.pool(combo, unlock)
                    unfilled = len(created(*combo)) - 1  # the goal location holds the locked Victory
                    pool = sum(quantity for name, quantity in base.items() if name != "Victory") + len(plan.pool_items)
                    self.assertGreaterEqual(unfilled - pool, 0, "the pool must never be bigger than the locations")
                    # tapes and tokens take their items along with their locations, so only the prizes change the amount of filler
                    self.assertEqual(unfilled - pool, 45 + 57 * combo[0] - len(plan.pool_items))

    def test_every_group_off_still_has_room_for_the_heaviest_plan(self):
        combo = (False, False, False)
        for unlock in UNLOCK_OPTIONS:
            base, plan = self.pool(combo, unlock)
            self.assertEqual(sum(base[n] for n in base if n != "Victory"), 4)  # Prize Counter Key, License, 2 traps
            self.assertLessEqual(4 + len(plan.pool_items), len(created(*combo)) - 1)
        self.assertEqual(len(created(*combo)) - 1, 49)

    def test_the_quota_options_never_ask_for_more_than_the_pool_has(self):
        text = (WORLD_DIR / "options.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        ranges = {}
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name in ("RequiredTapes", "RequiredFazTokens"):
                ranges[node.name] = next(s.value.value for s in node.body if isinstance(s, ast.Assign) and s.targets[0].id == "range_end")
        self.assertLessEqual(ranges["RequiredTapes"], data.ITEM_TABLE["Glitch Tape"].quantity)
        self.assertLessEqual(ranges["RequiredFazTokens"], data.ITEM_TABLE["Faz Token"].quantity)
        self.assertEqual(len(data.GLITCH_TAPE_CHECKS), data.ITEM_TABLE["Glitch Tape"].quantity)
        self.assertEqual(len(data.FAZ_TOKEN_CHECKS), data.ITEM_TABLE["Faz Token"].quantity)


class TestFiller(unittest.TestCase):
    """Spare slots are filled with Faz Token items only while the Faz Tokens are randomized. With them off (vanilla) the filler is "Faz Coupon", an item
    with no effect, so the room does not hand out Faz Token items the game then ignores (found in a real room 2026-10-10)."""

    def test_the_filler_follows_the_token_toggle(self):
        self.assertEqual(data.filler_item_name(True), "Faz Token")
        self.assertEqual(data.filler_item_name(False), "Faz Coupon")

    def test_the_coupon_is_a_new_appended_item_that_changes_nothing_that_exists(self):
        self.assertEqual(data.EXTRA_ITEM_CODES, {"Faz Coupon": 60})
        used = {item.code for item in data.ITEM_TABLE.values()} | set(levels.APPENDED_ITEM_CODES.values())
        self.assertNotIn(60, used)
        self.assertEqual(sorted(used), list(range(1, 14)) + list(range(14, 60)))  # 1..59 are unchanged and 60 is the next free id
        self.assertNotIn("Faz Coupon", data.ITEM_TABLE)

    def test_the_world_registers_and_uses_it(self):
        items = (WORLD_DIR / "items.py").read_text(encoding="utf-8")
        init = (WORLD_DIR / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("EXTRA_ITEM_CODES", items)
        self.assertIn("filler_item_name(", init)
        self.assertNotIn('create_item("Faz Token")', init)  # the filler is chosen, not fixed
        self.assertNotIn('return "Faz Token"', init)

    def test_the_coupon_is_not_progression_and_has_no_quantity(self):
        self.assertNotIn("Faz Coupon", {name for name, item in data.ITEM_TABLE.items() if item.progression})


class TestGoalRequirements(unittest.TestCase):
    """A group that is not randomized cannot be asked for as items: its requirement leaves the logic (the game itself still has the tapes / tokens)."""

    def need(self, goal, tapes_on, tokens_on, required_tapes=8, required_tokens=15):
        return data.tape_token_requirements(goal, required_tapes, required_tokens, tapes_on, tokens_on)

    def test_all_on_is_what_the_rules_asked_before(self):
        self.assertEqual(self.need(data.GOAL_GLITCHTRAP_DIE, True, True), (8, 0))
        self.assertEqual(self.need(data.GOAL_GLITCHTRAP_SURVIVE, True, True), (8, 0))
        self.assertEqual(self.need(data.GOAL_GLITCHTRAP_DIE, True, True, required_tapes=0), (1, 0))  # max(1, required)
        self.assertEqual(self.need(data.GOAL_HUNDRED_PERCENT, True, True), (16, 30))
        self.assertEqual(self.need(data.GOAL_TOKEN_TAPE_QUOTA, True, True), (8, 15))
        self.assertEqual(self.need(data.GOAL_COMPLETE_ALL_MINIGAMES, True, True), (0, 0))
        self.assertEqual(self.need(data.GOAL_COMPLETE_ALL_MINIGAMES_HARD, True, True), (0, 0))

    def test_tapes_off_drops_the_tape_requirement_of_every_goal(self):
        for goal in (data.GOAL_GLITCHTRAP_DIE, data.GOAL_GLITCHTRAP_SURVIVE, data.GOAL_HUNDRED_PERCENT, data.GOAL_TOKEN_TAPE_QUOTA):
            self.assertEqual(self.need(goal, False, True)[0], 0, goal)
        self.assertEqual(self.need(data.GOAL_TOKEN_TAPE_QUOTA, False, True), (0, 15))

    def test_tokens_off_drops_the_token_requirement_of_every_goal(self):
        for goal in (data.GOAL_HUNDRED_PERCENT, data.GOAL_TOKEN_TAPE_QUOTA):
            self.assertEqual(self.need(goal, True, False)[1], 0, goal)
        self.assertEqual(self.need(data.GOAL_TOKEN_TAPE_QUOTA, True, False), (8, 0))

    def test_no_combination_is_rejected(self):
        for combo in COMBINATIONS:
            for goal in (data.GOAL_COMPLETE_ALL_MINIGAMES, data.GOAL_GLITCHTRAP_DIE, data.GOAL_HUNDRED_PERCENT, data.GOAL_TOKEN_TAPE_QUOTA):
                self.assertEqual(len(self.need(goal, combo[2], combo[1])), 2)  # always an answer, never an error
        rules = (WORLD_DIR / "rules.py").read_text(encoding="utf-8")
        init = (WORLD_DIR / "__init__.py").read_text(encoding="utf-8")
        self.assertNotIn("OptionError", rules + init)


class TestWorldGlueSource(unittest.TestCase):
    """options.py, __init__.py, regions.py and rules.py need Archipelago to import, so they are read statically."""

    OPTIONS = {"RandomizePrizes": "randomize_prizes", "RandomizeFazTokens": "randomize_faz_tokens",
               "RandomizeGlitchTapes": "randomize_glitch_tapes"}

    def setUp(self):
        self.options = (WORLD_DIR / "options.py").read_text(encoding="utf-8")
        self.init = (WORLD_DIR / "__init__.py").read_text(encoding="utf-8")
        self.regions = (WORLD_DIR / "regions.py").read_text(encoding="utf-8")
        self.rules = (WORLD_DIR / "rules.py").read_text(encoding="utf-8")

    def test_the_three_options_are_toggles_that_are_on_by_default(self):
        classes = {n.name: n for n in ast.parse(self.options).body if isinstance(n, ast.ClassDef)}
        for class_name, field in self.OPTIONS.items():
            with self.subTest(option=field):
                self.assertEqual([b.id for b in classes[class_name].bases], ["DefaultOnToggle"])
                self.assertIn(f"{field}: {class_name}", self.options)
                doc = ast.get_docstring(classes[class_name]).lower()
                self.assertIn("vanilla", doc)

    def test_the_options_say_what_they_do_to_items_and_the_game(self):
        docs = {n.name: ast.get_docstring(n).lower() for n in ast.parse(self.options).body
                if isinstance(n, ast.ClassDef) and n.name in self.OPTIONS}
        self.assertIn("glitch tape", docs["RandomizeGlitchTapes"])
        self.assertIn("faz token", docs["RandomizeFazTokens"])
        self.assertIn("prize", docs["RandomizePrizes"])

    def test_the_world_creates_regions_and_the_pool_from_the_toggles(self):
        self.assertIn("region_locations(", self.regions)
        self.assertNotIn("ACTIVE_REGION_LOCATIONS", self.regions)
        for field in self.OPTIONS.values():
            self.assertIn(f"self.options.{field}.value", self.init)
        self.assertIn("unrandomized_items(", self.init)

    def test_slot_data_carries_the_three_toggles_as_booleans(self):
        for field in self.OPTIONS.values():
            self.assertIn(f'"{field}": bool(self.options.{field}.value)', self.init)

    def test_the_rules_filter_the_100_percent_list_and_the_item_requirements(self):
        self.assertIn("full_clear_checks(", self.rules)
        self.assertIn("tape_token_requirements(", self.rules)
        self.assertNotIn("FULL_CLEAR_CHECKS", self.rules)  # the unfiltered list must not be used by a rule

    def test_the_template_lists_the_three_options_defaulting_to_on(self):
        text = (project_root / "templates" / "Five Nights at Freddy's Help Wanted.yaml").read_text(encoding="utf-8")
        for field in self.OPTIONS.values():
            block = text.split(f"  {field}:", 1)[1].split("\n\n", 1)[0]
            self.assertIn("'true': 50", block, field)
            self.assertIn("'false': 0", block, field)


if __name__ == "__main__":
    unittest.main()
