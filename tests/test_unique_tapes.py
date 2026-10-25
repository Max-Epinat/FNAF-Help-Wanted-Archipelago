"""Unique tapes (2026-10-26): 16 tape items, one per log of the tape room, instead of 16 identical "Glitch Tape" items.

Decided with the user: names "Glitch Tape #NN (Place)" numbered by log (= the label the room shows), item codes 61-76 in log order (append only,
after Faz Coupon 60), the old "Glitch Tape" (code 1) removed for good (its code is retired, never reused; rooms generated before this version
must be regenerated), only as many tape items are progression as the goal needs and WHICH ones is random per seed, randomize_glitch_tapes: false
= no tape item at all. The log order follows the hub's section order and the level table (docs/game-research.md "Tapes").
The world glue (__init__.py, rules.py) imports Archipelago, so it is read statically here and checked for real by the generator tests.
"""

import random
import re
import sys
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tests.test_generator_check import check  # noqa: E402  (scripts/generator_check.py, loaded by path)
from tests.test_world_gating import data, levels  # noqa: E402  (loads the world's pure modules without Archipelago)

WORLD_DIR = project_root / "fnaf_help_wanted"

# (log, item name, the check of the tape that holds this log in the vanilla game) - the table agreed with the user on 2026-10-26
TABLE = [
    (1, "Glitch Tape #01 (Intro)", "Collect Prize Counter Intro Tape"),
    (2, "Glitch Tape #02 (FNAF 1)", "Collect Glitch Tape 07"),
    (3, "Glitch Tape #03 (FNAF 3)", "Collect Glitch Tape 02"),
    (4, "Glitch Tape #04 (Parts and Service Chica)", "Collect Glitch Tape 10"),
    (5, "Glitch Tape #05 (Parts and Service Freddy)", "Collect Glitch Tape 12"),
    (6, "Glitch Tape #06 (Parts and Service Foxy)", "Collect Glitch Tape 11"),
    (7, "Glitch Tape #07 (Vent Repair Mangle)", "Collect Glitch Tape 16"),
    (8, "Glitch Tape #08 (Vent Repair Ennard)", "Collect Glitch Tape 05"),
    (9, "Glitch Tape #09 (Dark Rooms Plushbaby)", "Collect Glitch Tape 03"),
    (10, "Glitch Tape #10 (Dark Rooms Funtime Foxy)", "Collect Glitch Tape 04"),
    (11, "Glitch Tape #11 (Night Terrors Circus Baby)", "Collect Glitch Tape 13"),
    (12, "Glitch Tape #12 (Night Terrors Nightmare Fredbear)", "Collect Glitch Tape 06"),
    (13, "Glitch Tape #13 (Pizza Party)", "Collect Glitch Tape 14"),
    (14, "Glitch Tape #14 (Gallery)", "Collect Glitch Tape 08"),
    (15, "Glitch Tape #15 (Hub)", "Collect Glitch Tape 09"),
    (16, "Glitch Tape #16 (Hub)", "Collect Glitch Tape 15"),
]


class TestTapeItems(unittest.TestCase):
    def test_the_sixteen_names_in_log_order(self):
        self.assertEqual(list(data.TAPE_ITEM_NAMES), [name for _, name, _ in TABLE])

    def test_codes_61_to_76_in_log_order(self):
        self.assertEqual([data.ITEM_TABLE[name].code for name in data.TAPE_ITEM_NAMES], list(range(61, 77)))

    def test_each_tape_is_one_progression_item(self):
        for name in data.TAPE_ITEM_NAMES:
            item = data.ITEM_TABLE[name]
            self.assertEqual((item.quantity, item.progression, item.skip_balancing, item.useful, item.trap), (1, True, False, False, False), name)

    def test_the_table_ties_each_log_to_the_tape_check_that_holds_it_in_the_game(self):
        self.assertEqual(data.TAPE_LOG_CHECKS, {log: check_name for log, _, check_name in TABLE})
        self.assertEqual(sorted(data.TAPE_LOG_CHECKS.values()), sorted(data.GLITCH_TAPE_CHECKS))
        # the place in each name is the map the check's pickup is on (levels.PICKUP_MAPS, read from the game's files)
        maps = {2: "NightGuard_Office01", 3: "NightGuard_Office03", 4: "Repair_Chica_Game", 5: "Repair_Freddy_Game", 6: "Repair_Foxy_Game",
                7: "Vent_Game_Mangle_1", 8: "Vent_Game_Ennard_2", 9: "Flashlight_Game_Ver_2", 10: "Funtime_Foxy", 11: "NightTerror_CircusBaby",
                12: "NightTerror_Fredbear", 13: levels.PIZZA_PARTY_MAP}
        for log, map_name in maps.items():
            self.assertEqual(levels.PICKUP_MAPS[data.TAPE_LOG_CHECKS[log]], map_name, log)
        for log in (1, 14, 15, 16):  # intro (free) and the gallery / hub tapes (filler only): not inside a level
            self.assertNotIn(data.TAPE_LOG_CHECKS[log], levels.PICKUP_MAPS)

    def test_the_names_are_unique_and_say_the_log(self):
        self.assertEqual(len(set(data.TAPE_ITEM_NAMES)), 16)
        for log, name in enumerate(data.TAPE_ITEM_NAMES, start=1):
            self.assertTrue(name.startswith("Glitch Tape #%02d (" % log), name)


class TestTheOldItemIsGone(unittest.TestCase):
    def all_codes(self):
        return ({name: item.code for name, item in data.ITEM_TABLE.items()} | dict(levels.APPENDED_ITEM_CODES) | dict(data.EXTRA_ITEM_CODES))

    def test_glitch_tape_is_not_an_item_any_more(self):
        self.assertNotIn("Glitch Tape", self.all_codes())

    def test_its_code_is_retired_and_never_reused(self):
        self.assertEqual(data.RETIRED_ITEM_CODES, {1: "Glitch Tape"})
        codes = list(self.all_codes().values())
        self.assertEqual(len(codes), len(set(codes)))
        self.assertFalse(set(codes) & set(data.RETIRED_ITEM_CODES))

    def test_nothing_in_the_world_or_the_harness_names_the_old_item(self):
        pattern = re.compile(r"""["']Glitch Tape["']""")
        for path in sorted(WORLD_DIR.glob("*.py")) + [project_root / "scripts" / "generator_check.py"]:
            text = path.read_text(encoding="utf-8")
            if path.name == "data.py":
                text = text.replace('RETIRED_ITEM_CODES = {1: "Glitch Tape"}', "")
            self.assertIsNone(pattern.search(text), path.name)


class TestPool(unittest.TestCase):
    def test_tapes_off_means_no_tape_item_at_all(self):
        self.assertEqual(data.unrandomized_items(True, False), frozenset(data.TAPE_ITEM_NAMES))
        self.assertEqual(data.unrandomized_items(False, False), frozenset(data.TAPE_ITEM_NAMES) | {"Faz Token"})
        self.assertEqual(data.unrandomized_items(True, True), frozenset())

    def test_the_pool_holds_each_tape_once_when_tapes_are_on(self):
        base = [name for name, item in data.ITEM_TABLE.items() if name not in levels.MANAGED_ITEM_NAMES for _ in range(item.quantity)]
        self.assertEqual(sorted(name for name in base if name.startswith("Glitch Tape")), sorted(data.TAPE_ITEM_NAMES))
        self.assertEqual(len(base), 16 + 1 + 1 + 30 + 2)  # tapes, Prize Counter Key, License, Faz Tokens, traps (as many items as before)

    def test_the_progression_tapes_are_picked_at_random_per_seed(self):
        picks = [data.pick_progression_tapes(random.Random(seed), 5) for seed in range(20)]
        for pick in picks:
            self.assertEqual(len(pick), 5)
            self.assertLessEqual(pick, frozenset(data.TAPE_ITEM_NAMES))
        self.assertGreater(len(set(picks)), 1)  # not always the same five
        self.assertEqual(data.pick_progression_tapes(random.Random(3), 5), data.pick_progression_tapes(random.Random(3), 5))  # same seed, same pick
        self.assertEqual(data.pick_progression_tapes(random.Random(1), 0), frozenset())
        self.assertEqual(data.pick_progression_tapes(random.Random(1), 16), frozenset(data.TAPE_ITEM_NAMES))
        self.assertEqual(data.pick_progression_tapes(random.Random(1), 99), frozenset(data.TAPE_ITEM_NAMES))

    def test_the_world_uses_the_random_pick_and_counts_any_of_the_sixteen(self):
        init = (WORLD_DIR / "__init__.py").read_text(encoding="utf-8")
        rules = (WORLD_DIR / "rules.py").read_text(encoding="utf-8")
        self.assertIn("pick_progression_tapes(self.random, tapes_needed)", init)
        self.assertIn("state.has_from_list(TAPE_ITEM_NAMES, player, tapes_needed)", rules)

    def test_the_quota_never_asks_for_more_tapes_than_exist(self):
        options = (WORLD_DIR / "options.py").read_text(encoding="utf-8")
        tapes = options.split("class RequiredTapes", 1)[1].split("class ", 1)[0]
        self.assertLessEqual(int(re.search(r"range_end = (\d+)", tapes).group(1)), len(data.TAPE_ITEM_NAMES))


class TestTapeFlagsInASeed(unittest.TestCase):
    """generator_check.tape_problems reads the generated seed: each tape item once, exactly the needed number progression, the rest plain filler."""

    IDS = list(range(101000061, 101000077))

    def seed(self, progression):
        return [(item_id, 1, 1 if index < progression else 0) for index, item_id in enumerate(self.IDS)] + [(101000011, 1, 0)]

    def test_a_good_seed(self):
        self.assertEqual(check.tape_problems(self.seed(8), (True, True, True), 8), [])
        self.assertEqual(check.tape_problems(self.seed(0), (True, True, True), 0), [])
        self.assertEqual(check.tape_problems([(101000011, 1, 0)], (True, True, False), 0), [])

    def test_the_wrong_number_of_progression_tapes(self):
        self.assertTrue(check.tape_problems(self.seed(16), (True, True, True), 8))
        self.assertTrue(check.tape_problems(self.seed(7), (True, True, True), 8))

    def test_a_missing_doubled_or_odd_tape(self):
        self.assertTrue(check.tape_problems(self.seed(8)[1:], (True, True, True), 8))  # log 1 missing
        self.assertTrue(check.tape_problems(self.seed(8) + [(101000070, 1, 0)], (True, True, True), 8))  # log 10 twice
        odd = self.seed(8)
        odd[12] = (odd[12][0], 1, 0b0010)  # a "useful" tape
        self.assertTrue(check.tape_problems(odd, (True, True, True), 8))

    def test_the_old_item_or_tapes_with_the_tapes_off(self):
        self.assertTrue(check.tape_problems(self.seed(8) + [(101000001, 1, 0)], (True, True, True), 8))
        self.assertTrue(check.tape_problems(self.seed(0), (True, True, False), 0))

    def test_the_script_runs_it_on_every_seed(self):
        source = (project_root / "scripts" / "generator_check.py").read_text(encoding="utf-8")
        self.assertIn("tape_problems(", source.split("def main", 1)[1])


class TestReplayCountsTheSixteen(unittest.TestCase):
    """scripts/generator_check.py replays each seed; its tape count must count the 16 tape items (progression only), not the old name."""

    def replay(self, lines, flags):
        data_, levels_ = check.load_data(), check.load_levels()
        text = "Players: 1\n\nStarting Items:\n\nFNAF 1 Access Pass\n\nLocations:\n\n" + "\n".join(lines) + "\n\nPlaythrough:\n"
        multidata = {1: {}}
        for line in lines:
            location = line.rsplit(": ", 1)[0]
            multidata[1][data_.LOCATION_OFFSET + data_.LOCATION_TABLE[location].code] = (0, 1, flags.get(location, 0))
        world = dict(plan=levels_.build_plan(levels_.UNLOCK_PER_SECTION, levels_.HARD_GROUPED, "fnaf_1"), goal=data_.GOAL_TOKEN_TAPE_QUOTA,
                     groups=(True, True, True), required_tapes=2, required_faz_tokens=0)
        return check.logic_problems(text, {"P1": world}, multidata, data_, levels_)

    def lines(self, first, second):
        return [f"Collect Prize Counter Intro Tape: {first}", f"Collect Faz Token 29: {second}", "Goal - Faz Token and Tape Quota: Victory"]

    def test_two_progression_tape_items_reach_a_two_tape_goal(self):
        flags = {"Collect Prize Counter Intro Tape": 1, "Collect Faz Token 29": 1}
        problems = self.replay(self.lines("Glitch Tape #05 (Parts and Service Freddy)", "Glitch Tape #16 (Hub)"), flags)
        self.assertFalse([p for p in problems if "goal" in p], problems)

    def test_filler_tape_items_do_not_count(self):
        problems = self.replay(self.lines("Glitch Tape #05 (Parts and Service Freddy)", "Glitch Tape #16 (Hub)"), {"Collect Prize Counter Intro Tape": 1})
        self.assertTrue([p for p in problems if "goal not reachable" in p], problems)

    def test_the_old_name_does_not_count(self):
        flags = {"Collect Prize Counter Intro Tape": 1, "Collect Faz Token 29": 1}
        problems = self.replay(self.lines("Glitch Tape", "Glitch Tape"), flags)
        self.assertTrue([p for p in problems if "goal not reachable" in p], problems)


if __name__ == "__main__":
    unittest.main()
