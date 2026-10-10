"""The pure parts of scripts/generator_check.py (spoiler parsing and the misplaced-unlock-item check). Running the real generator is a manual step."""

import importlib.util
import sys
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("_fnafhw_generator_check", project_root / "scripts" / "generator_check.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check = _load()

SPOILER = """Archipelago World Version 0.6.7
Players:

Player 1: P1

Locations:

Collect All Hub Trophies: Faz Token
Prize - Plushie: Freddy Plush: Faz Token
Beat FNAF 1 - Night 1: Unlock FNAF 1 - Night 2
Collect Glitch Tape 02: FNAF 3 Access Pass

Playthrough:

0: {
  Beat FNAF 1 - Night 1: Unlock FNAF 1 - Night 2
}
"""


class TestGeneratorCheckHelpers(unittest.TestCase):
    def test_the_spoiler_locations_block_is_parsed_including_names_with_a_colon(self):
        placements = check.parse_spoiler_locations(SPOILER)
        self.assertEqual(len(placements), 4)  # the playthrough block is not read
        self.assertEqual(placements["Prize - Plushie: Freddy Plush"], "Faz Token")
        self.assertEqual(placements["Beat FNAF 1 - Night 1"], "Unlock FNAF 1 - Night 2")

    def test_an_unlock_item_on_a_non_level_location_is_reported_and_one_on_a_level_is_not(self):
        levels = check.load_levels()
        placements = check.parse_spoiler_locations(SPOILER.replace("Unlock FNAF 1 - Night 2", "FNAF 1 Access Pass"))
        bad = check.misplaced_unlock_items(placements, levels.MANAGED_ITEM_NAMES, levels.may_hold_unlock_item)
        self.assertEqual(bad, ["Collect Glitch Tape 02"])  # the access pass on a level location (Night 1) is fine; the one on a tape is not

    def test_the_group_check_flags_the_wrong_filler_and_a_wrong_location_list(self):
        data = check.load_data()
        every = {name: "Faz Token" for names in data.region_locations(True, False, True).values() for name in names}
        self.assertEqual(check.group_problems(every, (True, False, True), data).__len__(), 1)  # Faz Token items although the tokens are not randomized
        fixed = {name: "Faz Coupon" for name in every}
        self.assertEqual(check.group_problems(fixed, (True, False, True), data), [])
        self.assertTrue(check.group_problems({**fixed, "Collect Faz Token 01": "Faz Coupon"}, (True, False, True), data))  # a token location that must not exist
        on = {name: "Faz Coupon" for names in data.region_locations(True, True, True).values() for name in names}
        self.assertTrue(check.group_problems(on, (True, True, True), data))  # a coupon with the tokens randomized

    def test_the_script_checks_the_same_rule_the_world_applies(self):
        levels = check.load_levels()
        self.assertTrue(levels.may_hold_unlock_item("Beat FNAF 1 - Night 1"))
        self.assertFalse(levels.may_hold_unlock_item("Collect Faz Token 01"))
        self.assertIn("generator_check.py", (project_root / "docs" / "testing.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
