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
                expected = 43 + 57 * prizes + 30 * tokens + 16 * tapes  # 43 = 40 levels, Pizza Party, the goal, Glitchtrap "You Do Not Die"
                self.assertEqual(len(created(prizes, tokens, tapes)), expected)

    def test_all_on_is_the_table_without_the_never_sent_checks_and_the_unused_goals(self):
        self.assertEqual(data.region_locations(), data.region_locations(True, True, True))  # the default is all on
        self.assertEqual(len(created(True, True, True)), 146)  # 153 before 2026-10-25 (3 never-sent checks and 4 unused goals left out)

    def test_a_group_that_is_off_has_no_locations_and_one_that_is_on_has_all_of_them(self):
        groups = {"prizes": data.ACTIVE_PRIZE_CHECKS, "faz_tokens": data.FAZ_TOKEN_CHECKS, "tapes": data.GLITCH_TAPE_CHECKS}
        self.assertEqual({key: len(value) for key, value in groups.items()}, {"prizes": 57, "faz_tokens": 30, "tapes": 16})
        for combo in COMBINATIONS:
            names = set(created(*combo))
            for flag, (key, members) in zip(combo, groups.items()):
                with self.subTest(combo=combo, group=key):
                    self.assertEqual(set(members) <= names, flag)
                    self.assertEqual(bool(set(members) & names), flag)

    def test_levels_pizza_party_and_the_goal_are_always_there(self):
        always = set(data.MINIGAME_AND_NIGHT_CHECKS) | {"Complete Pizza Party", data.GOAL_COMPLETE_ALL_MINIGAMES, data.GOAL_GLITCHTRAP_SURVIVE}
        for combo in COMBINATIONS:
            with self.subTest(combo=combo):
                self.assertLessEqual(always, set(created(*combo)))
                self.assertFalse(set(created(*combo)) & data.NEVER_SENT_CHECKS)

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
        self.assertEqual(data.full_clear_checks(True, True, True), [n for n in data.FULL_CLEAR_CHECKS if n not in data.NEVER_SENT_CHECKS])
        none = set(data.full_clear_checks(False, False, False))
        self.assertEqual(set(data.FULL_CLEAR_CHECKS) - none,
                         set(data.ACTIVE_PRIZE_CHECKS) | set(data.FAZ_TOKEN_CHECKS) | set(data.GLITCH_TAPE_CHECKS) | data.NEVER_SENT_CHECKS)
        self.assertIn("Complete Pizza Party", none)
        self.assertNotIn("Win Prize Counter Blackjack", none)  # never sent by anything: not a location any more
        self.assertNotIn("Collect All Hub Trophies", none)


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
        self.assertEqual(data.unrandomized_items(True, False), frozenset(data.TAPE_ITEM_NAMES))
        self.assertEqual(data.unrandomized_items(False, False), frozenset({"Faz Token", *data.TAPE_ITEM_NAMES}))
        self.assertFalse(data.unrandomized_items(False, False) & levels.MANAGED_ITEM_NAMES)
        self.assertFalse(data.unrandomized_items(False, False) - set(data.ITEM_TABLE))  # only real, existing items

    def test_the_pool_always_fits_and_the_freed_slots_become_filler(self):
        for combo in COMBINATIONS:
            for unlock in UNLOCK_OPTIONS:
                with self.subTest(combo=combo, unlock=unlock):
                    base, plan = self.pool(combo, unlock)
                    unfilled = len(created(*combo)) - 1  # the goal location holds the locked Victory
                    names = [n for n, q in base.items() if n != "Victory" for _ in range(q)] + list(plan.pool_items)
                    # tapes and tokens take their items along with their locations, so only the prizes change the amount of filler
                    self.assertEqual(unfilled - len(names), 38 + 57 * combo[0] - len(plan.pool_items))
                    fitted = data.trim_to_fit(names, unfilled)
                    self.assertLessEqual(len(fitted), unfilled, "the pool must never be bigger than the locations")
                    self.assertEqual(len(fitted), min(len(names), unfilled))

    def test_every_group_off_the_heaviest_plan_loses_the_license_and_nothing_else(self):
        combo = (False, False, False)
        self.assertEqual(len(created(*combo)) - 1, 42)
        for unlock in UNLOCK_OPTIONS:
            base, plan = self.pool(combo, unlock)
            names = [n for n, q in base.items() if n != "Victory" for _ in range(q)] + list(plan.pool_items)
            self.assertEqual(sorted(n for n in names if n not in plan.pool_items),
                             ["Hallucination", "Hallucination", "Nightmare Mode License", "Prize Counter Key"])
            fitted = data.trim_to_fit(names, 42)
            dropped = list(names)
            for name in fitted:
                dropped.remove(name)
            if unlock[0] == levels.UNLOCK_PER_LEVEL:  # 39 level items + 4 = 43 for 42 slots: the License goes (it cannot fill a filler-only check)
                self.assertEqual(dropped, ["Nightmare Mode License"])
            else:
                self.assertEqual(dropped, [])

    def test_trimming_only_ever_drops_optional_items_license_first(self):
        self.assertEqual(data.OPTIONAL_ITEMS, ("Nightmare Mode License", "Hallucination"))
        names = ["A", "Hallucination", "Nightmare Mode License", "Hallucination", "B"]
        self.assertEqual(data.trim_to_fit(names, 5), names)
        self.assertEqual(data.trim_to_fit(names, 4), ["A", "Hallucination", "Hallucination", "B"])
        self.assertEqual(data.trim_to_fit(names, 3), ["A", "Hallucination", "B"])
        self.assertEqual(data.trim_to_fit(names, 2), ["A", "B"])
        self.assertEqual(data.trim_to_fit(names, 1), ["A", "B"])  # never a needed item: the world then reports the overflow
        init = (WORLD_DIR / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("trim_to_fit(names, unfilled_location_count)", init)

    def test_the_quota_options_never_ask_for_more_than_the_pool_has(self):
        text = (WORLD_DIR / "options.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        ranges = {}
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name in ("RequiredTapes", "RequiredFazTokens"):
                ranges[node.name] = next(s.value.value for s in node.body if isinstance(s, ast.Assign) and s.targets[0].id == "range_end")
        self.assertLessEqual(ranges["RequiredTapes"], len(data.TAPE_ITEM_NAMES))
        self.assertLessEqual(ranges["RequiredFazTokens"], data.ITEM_TABLE["Faz Token"].quantity)
        self.assertEqual(len(data.GLITCH_TAPE_CHECKS), len(data.TAPE_ITEM_NAMES))
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
        # 2..59 are unchanged, 60 is the coupon, 61-76 the tape items (2026-10-26); 1 (the old "Glitch Tape") is retired, never reused
        self.assertEqual(sorted(used), list(range(2, 60)) + list(range(61, 77)))
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

    def test_every_combination_has_an_answer_and_only_a_seed_too_big_to_fit_is_refused(self):
        for combo in COMBINATIONS:
            for goal in (data.GOAL_COMPLETE_ALL_MINIGAMES, data.GOAL_GLITCHTRAP_DIE, data.GOAL_HUNDRED_PERCENT, data.GOAL_TOKEN_TAPE_QUOTA):
                self.assertEqual(len(self.need(goal, combo[2], combo[1])), 2)  # always an answer
        # the toggles alone never refuse a seed; the one refusal is a seed whose important items cannot fit (tests/test_real_access.py)
        rules = (WORLD_DIR / "rules.py").read_text(encoding="utf-8")
        self.assertNotIn("OptionError", rules)
        init = (WORLD_DIR / "__init__.py").read_text(encoding="utf-8")
        self.assertEqual(init.count("raise OptionError("), 1)


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
