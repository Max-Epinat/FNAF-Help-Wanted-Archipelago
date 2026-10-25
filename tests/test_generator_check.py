"""The pure parts of scripts/generator_check.py (spoiler parsing, the replay with the real rules, the group and token checks). Running the real generator is a manual step."""

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

    def test_seeds_with_one_and_with_several_players_are_parsed(self):
        names, placements, start = check.parse_seed(SPOILER.replace("Locations:", "Starting Items:\n\nFNAF 1 Access Pass\n\nLocations:"))
        self.assertEqual(names, ["P1"])
        self.assertEqual(placements[("Prize - Plushie: Freddy Plush", "P1")], ("Faz Token", "P1"))
        self.assertEqual(start, [("FNAF 1 Access Pass", "P1")])
        multi = ("Players: 2\n\nPlayer 1: Yochix\n\nPlayer 2: Zinoxe\n\nStarting Items:\n\nUnlock FNAF 1 - Night 1 (Yochix)\n\nLocations:\n\n"
                 "Beat FNAF 1 - Night 5 (Hard) (Yochix): Unlock FNAF 1 - Night 5 (Hard) (Zinoxe)\n"
                 "Prize - Plushie: Freddy Plush (Zinoxe): Faz Token (Yochix)\n\nPlaythrough:\n")
        names, placements, start = check.parse_seed(multi)
        self.assertEqual(names, ["Yochix", "Zinoxe"])
        self.assertEqual(placements[("Beat FNAF 1 - Night 5 (Hard)", "Yochix")], ("Unlock FNAF 1 - Night 5 (Hard)", "Zinoxe"))
        self.assertEqual(placements[("Prize - Plushie: Freddy Plush", "Zinoxe")], ("Faz Token", "Yochix"))
        self.assertEqual(start, [("Unlock FNAF 1 - Night 1", "Yochix")])

    def replay(self, lines, flags=None, start="FNAF 1 Access Pass"):
        data, levels = check.load_data(), check.load_levels()
        text = f"Players: 1\n\nStarting Items:\n\n{start}\n\nLocations:\n\n" + "\n".join(lines) + "\n\nPlaythrough:\n"
        multidata = {1: {}}
        for line in lines:
            location = line.rsplit(": ", 1)[0]
            code = data.LOCATION_OFFSET + data.LOCATION_TABLE[location].code
            multidata[1][code] = (0, 1, (flags or {}).get(location, 0))
        world = dict(plan=levels.build_plan(levels.UNLOCK_PER_SECTION, levels.HARD_GROUPED, "fnaf_1"), goal=data.GOAL_COMPLETE_ALL_MINIGAMES,
                     groups=(True, True, True), required_tapes=8, required_faz_tokens=15)
        return [p for p in check.logic_problems(text, {"P1": world}, multidata, data, levels) if "goal not reachable" not in p]

    def test_the_real_rule_replay_follows_the_maps_and_catches_a_token_holding_its_own_key(self):
        good = ["Beat FNAF 1 - Night 1: FNAF 3 Access Pass", "Collect Faz Token 07: Night Terrors Security Badge",
                "Collect Glitch Tape 13: Glitch Tape", "Collect Faz Token 01: Faz Token", "Collect Prize Counter Intro Tape: Faz Token"]
        self.assertEqual(self.replay(good), [])
        locked = ["Beat FNAF 1 - Night 1: Faz Token", "Collect Faz Token 07: FNAF 3 Access Pass"]  # an FNAF 3 token holding the FNAF 3 pass
        self.assertTrue(any("Collect Faz Token 07" in p for p in self.replay(locked)))
        self.assertTrue(any("Collect Glitch Tape 13" in p for p in self.replay(["Collect Glitch Tape 13: Faz Token"])))  # Circus Baby is locked

    def test_the_replay_flags_progression_on_a_filler_only_check(self):
        lines = ["Beat FNAF 1 - Night 1: Faz Token", "Prize - Plushie: Helpy Plush: Faz Token"]  # Helpy needs every level: unreachable here
        self.assertFalse(any("filler-only" in p for p in self.replay(lines, {"Prize - Plushie: Helpy Plush": 0})))
        self.assertTrue(any("filler-only" in p for p in self.replay(lines, {"Prize - Plushie: Helpy Plush": 1})))
        self.assertTrue(any("filler-only" in p for p in self.replay(lines, {"Prize - Plushie: Helpy Plush": 2})))  # useful counts too

    def test_the_group_check_flags_the_wrong_filler_and_a_wrong_location_list(self):
        data = check.load_data()
        every = {name: "Faz Token" for names in data.region_locations(True, False, True).values() for name in names}
        self.assertEqual(check.group_problems(every, (True, False, True), data).__len__(), 1)  # Faz Token items although the tokens are not randomized
        fixed = {name: "Faz Coupon" for name in every}
        self.assertEqual(check.group_problems(fixed, (True, False, True), data), [])
        self.assertTrue(check.group_problems({**fixed, "Collect Faz Token 01": "Faz Coupon"}, (True, False, True), data))  # a token location that must not exist
        on = {name: "Faz Coupon" for names in data.region_locations(True, True, True).values() for name in names}
        self.assertTrue(check.group_problems(on, (True, True, True), data))  # a coupon with the tokens randomized

    def test_the_token_check_wants_exactly_the_30_base_faz_tokens_as_progression(self):
        token, coupon = check.FAZ_TOKEN_ID, check.FAZ_TOKEN_ID + 49  # 101000060 = Faz Coupon
        good = [(token, 1, 0b1001)] * 30 + [(token, 1, 0)] * 96
        self.assertEqual(check.token_problems(good, (True, True, True)), [])
        self.assertTrue(check.token_problems([(token, 1, 0)] * 126, (True, True, True)))  # today's world: no token counts in logic
        self.assertTrue(check.token_problems([(token, 1, 0b1001)] * 126, (True, True, True)))  # the filler must stay filler
        self.assertTrue(check.token_problems([(token, 1, 0b1001)] * 29 + [(token, 1, 0)] * 97, (True, True, True)))
        self.assertTrue(check.token_problems(good[:30] + [(token, 1, 0b0010)], (True, True, True)))  # a filler token that is not plain filler
        self.assertEqual(check.token_problems([(coupon, 1, 0)] * 40, (True, False, True)), [])
        self.assertTrue(check.token_problems([(token, 1, 0)], (True, False, True)))  # tokens off: no Faz Token item at all

    def test_the_script_no_longer_checks_the_stopgap_and_is_documented(self):
        source = (project_root / "scripts" / "generator_check.py").read_text(encoding="utf-8")
        self.assertNotIn("may_hold_unlock_item", source)
        self.assertIn("logic_problems(", source.split("def main", 1)[1])
        self.assertIn("generator_check.py", (project_root / "docs" / "testing.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
