"""Every goal generates a beatable seed, for every combination of the three location-group toggles (the user's rule since 2026-10-25: no goal may be
hidden, excluded or documented as broken).

Before: `complete_all_minigames_nights_hard_mode` never generated (its rule asked for the Nightmare Mode License, a `useful` item that `state.has` never
counts), and `hundred_percent` / `token_tape_quota` never generated with the Faz Tokens randomized (the Faz Tokens were filler). The License was dropped
from the hard goal (user's choice (b), 2026-10-25: the game itself ends the multiworld on Pizza Party whatever the goal, and the License has no verified
effect); it stays in the pool as a useful item. The base Faz Tokens became progression (tests/test_faz_token_progression.py).

The pure / static part runs everywhere; the real generator part (full runs, built from the working tree) is skipped without an Archipelago install.
"""

import importlib.util
import itertools
import re
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
WORLD_DIR = project_root / "fnaf_help_wanted"
sys.path.insert(0, str(project_root / "scripts"))
sys.path.insert(0, str(project_root / "tests"))

import generator_check as check  # noqa: E402
from test_location_groups_generator import ARCHIPELAGO, INSTALLED, build_apworld  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(f"_fnafhw_{name}", WORLD_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


data = _load("data")
levels = _load("levels")

COMBINATIONS = list(itertools.product((True, False), repeat=3))  # (prizes, faz_tokens, tapes)


def goal_rule_source(location_constant: str) -> str:
    """The rule of one goal location in rules.py's goal_rules table, as text."""
    rules = (WORLD_DIR / "rules.py").read_text(encoding="utf-8")
    table = rules.split("goal_rules = {", 1)[1].split("\n    }", 1)[0]
    return re.split(r"\n        GOAL_\w+: ", table.split(f"\n        {location_constant}: ", 1)[1])[0]


class TestHardGoalWithoutTheLicense(unittest.TestCase):
    def test_no_rule_asks_for_the_license(self):
        self.assertNotIn("Nightmare Mode License", (WORLD_DIR / "rules.py").read_text(encoding="utf-8"))

    def test_the_hard_goal_needs_every_level_and_pizza_party(self):
        rule = goal_rule_source("GOAL_COMPLETE_ALL_MINIGAMES_HARD")
        self.assertIn("can_reach_all(state, MINIGAME_AND_NIGHT_CHECKS)", rule)
        self.assertIn('state.can_reach("Complete Pizza Party", "Location", player)', rule)
        self.assertNotIn("state.has", rule)
        hard_levels = {level.location for level in levels.LEVELS if level.hard}
        self.assertEqual(len(hard_levels), 14)  # 13 "(Hard)" levels plus FNAF 2 - Withered
        self.assertLessEqual(hard_levels, set(data.MINIGAME_AND_NIGHT_CHECKS))  # every hard level is in the list the rule reaches
        self.assertEqual({level.location for level in levels.LEVELS}, set(data.MINIGAME_AND_NIGHT_CHECKS))  # and every level at all

    def test_the_license_stays_in_the_pool_as_a_useful_item(self):
        license_item = data.ITEM_TABLE["Nightmare Mode License"]
        self.assertEqual((license_item.code, license_item.quantity), (10, 1))
        self.assertTrue(license_item.useful)
        self.assertFalse(license_item.progression)
        self.assertNotIn("Nightmare Mode License", levels.MANAGED_ITEM_NAMES)
        self.assertNotIn("Nightmare Mode License", data.unrandomized_items(False, False))

    def test_the_mod_keeps_its_license_effect(self):
        hooks = (project_root / "ue4ss_mod" / "FNAFHWArchipelago" / "Scripts" / "lib" / "exact_hooks.lua").read_text(encoding="utf-8")
        self.assertIn("elseif item_id == 101000010 then", hooks)
        self.assertIn("gi:EnableNightmareMode(true)", hooks)


class TestEveryGoalIsRequired(unittest.TestCase):
    def test_the_harness_knows_every_goal_of_the_option_and_requires_all_of_them(self):
        options = (WORLD_DIR / "options.py").read_text(encoding="utf-8")
        goals = re.findall(r"option_(\w+) = \d+", options.split("class Goal(", 1)[1].split("\nclass ", 1)[0])
        self.assertEqual(check.ALL_GOALS, goals)
        self.assertEqual(check.REQUIRED_GOALS, check.ALL_GOALS)


@unittest.skipUnless(INSTALLED, "no Archipelago install (set ARCHIPELAGO_DIR) or not Windows")
class TestEveryGoalGenerates(unittest.TestCase):
    """One test per goal: the 8 toggle combinations, default unlock mode and start section, seed 1. A seed counts only when its zip is written."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="fnafhw_goals_")
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(cls.tmp.name)
        cls.scratch = root / "ap"
        check.build_scratch(ARCHIPELAGO, cls.scratch, build_apworld(root))

    def generate_all_combinations(self, goal):
        def one(combo):
            tag = goal[:6] + "".join("1" if on else "0" for on in combo)
            placements, reason = check.generate(self.scratch, goal, "per_section", "grouped", "fnaf_1", 1, combo, tag=tag)
            if placements is None:
                return combo, placements, reason, [], ["not generated"]
            world = dict(plan=check.plan_for(levels, "per_section", "grouped", "fnaf_1"), goal=check.goal_location(data, goal), groups=combo,
                         required_tapes=8, required_faz_tokens=15)
            logic = check.logic_problems(check.read_spoiler(self.scratch, tag), {"P1": world}, check.read_multidata(self.scratch, tag), data, levels)
            warning = check.unreachable_warning(self.scratch, tag)
            logic += [warning] if warning else []  # with the real rules no location may be out of the logic's reach
            return combo, placements, reason, check.read_location_items(self.scratch, tag), logic
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(one, COMBINATIONS))
        for combo, placements, reason, items, logic in results:
            with self.subTest(goal=goal, prizes=combo[0], faz_tokens=combo[1], tapes=combo[2]):
                self.assertIsNotNone(placements, f"not generated / not beatable: {reason}")
                self.assertEqual(check.group_problems(placements, combo, data, goal), [])
                self.assertEqual(logic, [])  # the replay with the real rules reaches every location and the goal
                tokens_needed = data.tape_token_requirements(check.goal_location(data, goal), 8, 15, combo[2], combo[1])[1]
                self.assertEqual(check.token_problems(items, combo, tokens_needed), [])  # only as many as the goal needs
                self.assertIn("Nightmare Mode License", placements.values())  # still in the pool whatever the goal
        return results

    def test_complete_all_minigames_nights(self):
        self.generate_all_combinations("complete_all_minigames_nights")

    def test_complete_all_minigames_nights_hard_mode(self):
        self.generate_all_combinations("complete_all_minigames_nights_hard_mode")

    def test_glitchtrap_ending_die(self):
        self.generate_all_combinations("glitchtrap_ending_die")

    def test_glitchtrap_ending_survive(self):
        self.generate_all_combinations("glitchtrap_ending_survive")

    def test_hundred_percent(self):
        self.generate_all_combinations("hundred_percent")

    def test_token_tape_quota(self):
        self.generate_all_combinations("token_tape_quota")


if __name__ == "__main__":
    unittest.main()
