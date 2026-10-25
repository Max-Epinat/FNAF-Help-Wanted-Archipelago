"""Real access rules for the checks that are not levels, read from the game's own files (2026-10-25).

Why: tapes, Faz Tokens and prizes had no access rule, so the generator believed they were reachable with nothing. A real 4-player seed
(two FNAF slots) put Luigi's Mansion keys and FNAF unlock items on tapes and tokens inside locked levels and could not be finished.
Every fact below comes from the game files (docs/game-research.md, "Where the tapes, tokens and prizes are"):
  * which map each tape / Faz Token pickup is placed in (the GlitchID / CoinID of the placed actor; tape id 0 is the class default and the
    only trigger without an id is in FNAF 3; coin 20 is spawned by Parts and Service Foxy),
  * which levels are played on which map (LevelInfoTable "LevelToLoad"),
  * prizes: a level win draws a random prize not owned yet among those with CanBeAwardedFromAnyLevel (all but Helpy Plush and the Bobbleheads),
  * nothing in the mod or the client ever sends Collect All Hub Trophies, Complete Normal Ending, Win Prize Counter Blackjack, or any goal location
    but Glitchtrap "You Do Not Die": those are not created any more (ids kept).
A pickup needs EVERY level played on its map: some appear only on a night or only in the nightmare version (the Ennard tape and token are
destroyed outside nightmare mode), and every one appears in at least one of them, so "all of them" is always reachable and never too loose.
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

ALL_OPTIONS = [(mode, hard, section) for mode in (levels.UNLOCK_PER_SECTION, levels.UNLOCK_PER_LEVEL)
               for hard in (levels.HARD_GROUPED, levels.HARD_SEPARATE) for section in levels.SECTION_BY_KEY]
PICKUPS = data.GLITCH_TAPE_CHECKS + data.FAZ_TOKEN_CHECKS


def level_items(plan, *locations):
    return frozenset().union(*(plan.location_items[loc] for loc in locations))


class TestMapData(unittest.TestCase):
    def test_every_gated_level_has_its_map_from_the_level_table(self):
        self.assertEqual(set(levels.LEVEL_MAPS), {lv.row for lv in levels.LEVELS})
        groups = {}
        for row, map_name in levels.LEVEL_MAPS.items():
            groups.setdefault(map_name, set()).add(levels.LEVEL_BY_ROW[row].location)
        self.assertEqual(groups["NightGuard_Office01"], {lv.location for lv in levels.LEVELS if lv.section == "fnaf_1"})
        self.assertEqual(groups["NightGuard_Office02"], {lv.location for lv in levels.LEVELS if lv.section == "fnaf_2"})  # Withered included
        self.assertIn("Beat FNAF 2 - Withered", groups["NightGuard_Office02"])
        self.assertEqual(groups["Flashlight_Game_Ver_1_Bigger"], {"Complete Dark Rooms - Plushtrap", "Complete Dark Rooms - Nightmare BB",
                                                                  "Complete Dark Rooms (Hard) - Plushtrap", "Complete Dark Rooms (Hard) - Nightmare BB"})
        self.assertEqual(groups["Vent_Game_Ennard_2"], {"Complete Vent Repair - Ennard", "Complete Vent Repair (Hard) - Ennard"})
        self.assertEqual(groups["NightTerror_CircusBaby"], {"Complete Night Terrors - Circus Baby"})
        self.assertNotIn(levels.PIZZA_PARTY_MAP, groups)

    def test_every_tape_and_token_has_exactly_one_kind_of_rule(self):
        kinds = [set(levels.PICKUP_MAPS), set(levels.FREE_CHECKS), set(levels.FILLER_ONLY_CHECKS) & set(PICKUPS)]
        for a, b in itertools.combinations(kinds, 2):
            self.assertFalse(a & b)
        self.assertEqual(set().union(*kinds), set(PICKUPS))
        for name, map_name in levels.PICKUP_MAPS.items():
            self.assertIn(map_name, set(levels.LEVEL_MAPS.values()) | {levels.PIZZA_PARTY_MAP}, name)

    def test_the_maps_read_from_the_game(self):
        pinned = {
            "Collect Glitch Tape 02": "NightGuard_Office03", "Collect Glitch Tape 05": "Vent_Game_Ennard_2",
            "Collect Glitch Tape 07": "NightGuard_Office01", "Collect Glitch Tape 13": "NightTerror_CircusBaby",
            "Collect Glitch Tape 14": "Finale_Ending", "Collect Faz Token 10": "Flashlight_Game_Ver_1_Bigger",
            "Collect Faz Token 20": "Repair_Foxy_Game", "Collect Faz Token 25": "Vent_Game_Ennard_2", "Collect Faz Token 27": "Finale_Ending",
        }
        for name, map_name in pinned.items():
            self.assertEqual(levels.PICKUP_MAPS[name], map_name, name)
        self.assertEqual(levels.FREE_CHECKS, frozenset({"Collect Prize Counter Intro Tape", "Collect Faz Token 29"}))
        self.assertEqual(levels.FILLER_ONLY_CHECKS, frozenset({
            "Collect Glitch Tape 08", "Collect Glitch Tape 09", "Collect Glitch Tape 15", "Collect Faz Token 30",
            "Prize - Plushie: Helpy Plush", "Prize - Other: Freddy Bobblehead", "Prize - Other: Chica Bobblehead", "Prize - Other: Bonnie Bobblehead"}))
        self.assertLessEqual(levels.FILLER_ONLY_CHECKS - set(PICKUPS), set(data.ACTIVE_PRIZE_CHECKS))


class TestPlanRules(unittest.TestCase):
    def test_a_pickup_needs_every_level_of_its_map_in_every_mode(self):
        maps = {}
        for row, map_name in levels.LEVEL_MAPS.items():
            maps.setdefault(map_name, []).append(levels.LEVEL_BY_ROW[row].location)
        for options in ALL_OPTIONS:
            plan = levels.build_plan(*options)
            every = plan.location_items[levels.PIZZA_PARTY_LOCATION]
            for name, map_name in levels.PICKUP_MAPS.items():
                with self.subTest(options=options, check=name):
                    expected = every if map_name == levels.PIZZA_PARTY_MAP else level_items(plan, *maps[map_name])
                    self.assertEqual(plan.location_items[name], expected)
            for name in levels.FILLER_ONLY_CHECKS:
                self.assertEqual(plan.location_items[name], every, name)  # only once every level is open
            for name in levels.FREE_CHECKS:
                self.assertNotIn(name, plan.location_items)
            self.assertEqual(plan.any_level_items, every)

    def test_prizes_are_reachable_from_the_start_because_every_plan_starts_with_a_level(self):
        for options in ALL_OPTIONS:
            plan = levels.build_plan(*options)
            self.assertTrue(set(plan.start_items) & plan.any_level_items, options)

    def test_the_cases_that_broke_the_real_seed(self):
        plan = levels.build_plan(levels.UNLOCK_PER_LEVEL, levels.HARD_GROUPED, "night_terrors")
        self.assertEqual(plan.location_items["Collect Glitch Tape 13"], frozenset({"Unlock Night Terrors - Circus Baby"}))
        self.assertEqual(plan.location_items["Collect Faz Token 09"], frozenset(lv.item for lv in levels.LEVELS if lv.section == "fnaf_3"))
        self.assertEqual(plan.location_items["Collect Faz Token 25"], frozenset({"Unlock Vent Repair - Ennard", "Unlock Vent Repair (Hard) - Ennard"}))
        self.assertEqual(plan.location_items["Collect Faz Token 20"], frozenset({"Unlock Parts and Service - Foxy", "Unlock Parts and Service (Hard) - Foxy"}))
        section = levels.build_plan(levels.UNLOCK_PER_SECTION, levels.HARD_SEPARATE, "fnaf_1")
        self.assertEqual(section.location_items["Collect Glitch Tape 05"], frozenset({"Vent Repair Toolkit", "Vent Repair Hard Toolkit"}))

    def test_the_stopgap_is_gone(self):
        self.assertFalse(hasattr(levels, "may_hold_unlock_item"))
        rules = (WORLD_DIR / "rules.py").read_text(encoding="utf-8")
        self.assertNotIn("may_hold_unlock_item", rules)
        self.assertNotIn("add_item_rule", rules)


class TestCreatedLocations(unittest.TestCase):
    GOALS = [data.GOAL_COMPLETE_ALL_MINIGAMES, data.GOAL_COMPLETE_ALL_MINIGAMES_HARD, data.GOAL_GLITCHTRAP_DIE,
             data.GOAL_GLITCHTRAP_SURVIVE, data.GOAL_HUNDRED_PERCENT, data.GOAL_TOKEN_TAPE_QUOTA]

    def created(self, goal, groups=(True, True, True)):
        return [n for names in data.region_locations(*groups, goal=goal).values() for n in names]

    def test_checks_nothing_sends_are_never_created(self):
        self.assertEqual(data.NEVER_SENT_CHECKS, frozenset({"Collect All Hub Trophies", "Complete Normal Ending", "Win Prize Counter Blackjack"}))
        for goal in self.GOALS:
            names = set(self.created(goal))
            self.assertFalse(names & data.NEVER_SENT_CHECKS, goal)
            goals_created = {g for g in self.GOALS if g in names}
            self.assertEqual(goals_created, {goal, data.GOAL_GLITCHTRAP_SURVIVE}, goal)  # Survive is sent by the client (GlitchtrapDefeated)

    def test_the_counts(self):
        self.assertEqual(len(self.created(data.GOAL_COMPLETE_ALL_MINIGAMES)), 146)
        self.assertEqual(len(self.created(data.GOAL_GLITCHTRAP_SURVIVE)), 145)
        self.assertEqual(len(self.created(data.GOAL_COMPLETE_ALL_MINIGAMES, (False, False, False))), 43)  # 40 levels, Pizza Party, 2 goals

    def test_ids_never_move(self):
        for name in data.NEVER_SENT_CHECKS | set(self.GOALS):
            self.assertIn(name, data.LOCATION_TABLE)
        self.assertEqual(data.LOCATION_TABLE["Collect All Hub Trophies"].code, 1)
        self.assertEqual(data.LOCATION_TABLE["Win Prize Counter Blackjack"].code, 26)

    def test_goal_rules_only_name_locations_that_exist(self):
        for goal in self.GOALS:
            for groups in itertools.product((True, False), repeat=3):
                names = set(self.created(goal, groups))
                self.assertLessEqual(set(data.full_clear_checks(*groups)), names, (goal, groups))
                self.assertLessEqual(set(data.MINIGAME_AND_NIGHT_CHECKS), names)

    def test_the_world_passes_the_goal_and_marks_the_filler_only_checks(self):
        regions = (WORLD_DIR / "regions.py").read_text(encoding="utf-8")
        self.assertIn("goal=", regions)
        rules = (WORLD_DIR / "rules.py").read_text(encoding="utf-8")
        # the prize rule can never be false in a real seed (every plan starts with a level item, see below), so only its text can be checked
        for needle in ("FILLER_ONLY_CHECKS", "LocationProgressType.EXCLUDED", "any_level_items", "GOAL_GLITCHTRAP_SURVIVE",
                       "state.has_any(items, player)"):
            self.assertIn(needle, rules)
        ast.parse(rules)


class TestCountByNeed(unittest.TestCase):
    """Only as many Glitch Tapes / Faz Tokens are progression as the goal needs (the rest are filler), and a seed whose progression items cannot fit
    in the checks that may hold them is refused with a clear message (the user's choice, 2026-10-25). Found by the toggle sweep: per_level with prizes
    off and tapes on had 56 progression items for 54 checks once the never-sent checks were gone."""

    def capacity(self, mode, groups, goal, tapes=8, tokens=15):
        plan = levels.build_plan(mode, levels.HARD_GROUPED, "fnaf_1")
        return data.capacity(len(plan.pool_items), levels.FILLER_ONLY_CHECKS, groups, goal, tapes, tokens)

    def test_progression_counts_follow_the_goal(self):
        need = data.tape_token_requirements
        self.assertEqual(need(data.GOAL_COMPLETE_ALL_MINIGAMES, 8, 15, True, True), (0, 0))
        self.assertEqual(need(data.GOAL_GLITCHTRAP_DIE, 8, 15, True, True), (8, 0))
        self.assertEqual(need(data.GOAL_HUNDRED_PERCENT, 8, 15, True, True), (16, 30))
        init = (WORLD_DIR / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("tape_token_requirements(", init)

    def test_the_capacity_of_the_tight_seeds(self):
        per_level, section = levels.UNLOCK_PER_LEVEL, levels.UNLOCK_PER_SECTION
        # (progression items, checks that may hold one): 39 level items + the Key + tapes / tokens the goal needs; 40 levels + Pizza Party
        # + 13 tapes (3 are filler only) + 29 tokens (1 is filler only) + 53 prizes (4 are filler only)
        self.assertEqual(self.capacity(per_level, (False, False, True), data.GOAL_COMPLETE_ALL_MINIGAMES), (40, 54))
        self.assertEqual(self.capacity(per_level, (False, False, True), data.GOAL_HUNDRED_PERCENT), (56, 54))
        self.assertEqual(self.capacity(per_level, (False, True, True), data.GOAL_HUNDRED_PERCENT), (86, 83))
        self.assertEqual(self.capacity(per_level, (False, True, False), data.GOAL_HUNDRED_PERCENT), (70, 70))
        self.assertEqual(self.capacity(per_level, (True, True, True), data.GOAL_HUNDRED_PERCENT), (86, 136))
        self.assertEqual(self.capacity(section, (False, True, True), data.GOAL_HUNDRED_PERCENT), (53, 83))

    def test_the_world_refuses_an_impossible_seed_with_a_clear_message(self):
        init = (WORLD_DIR / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("OptionError", init)
        self.assertIn("randomize_prizes", init.split("raise OptionError(", 1)[1][:600])
        rules = (WORLD_DIR / "rules.py").read_text(encoding="utf-8")
        self.assertIn("survive_is_goal", rules)  # Survive when it is not the goal: every level only, like the other filler-only checks

    def test_the_trim_drops_the_license_before_the_traps(self):
        self.assertEqual(data.OPTIONAL_ITEMS, ("Nightmare Mode License", "Hallucination"))


sys.path.insert(0, str(project_root / "scripts"))
sys.path.insert(0, str(project_root / "tests"))
import generator_check as check  # noqa: E402
from test_location_groups_generator import ARCHIPELAGO, INSTALLED, build_apworld  # noqa: E402


@unittest.skipUnless(INSTALLED, "no Archipelago install (set ARCHIPELAGO_DIR) or not Windows")
class TestTwoFnafPlayersInOneMultiworld(unittest.TestCase):
    """The case that broke a real room: two FNAF slots whose unlock items and other progression end up on each other's tapes, tokens and prizes.
    Every seed must be generated AND pass the replay with the real rules for both players; unlock items must now appear off the levels."""

    PAIRS = [
        ("unlock_mode: per_level\n  starting_section: night_terrors\n  goal: glitchtrap_ending_die\n",
         "unlock_mode: per_level\n  starting_section: fnaf_1\n  goal: glitchtrap_ending_die\n"),
        ("unlock_mode: per_section\n  hard_variants: separate\n  starting_section: dark_rooms\n  goal: hundred_percent\n",
         "unlock_mode: per_level\n  starting_section: vent_repair\n  goal: token_tape_quota\n"),
    ]

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmp = tempfile.TemporaryDirectory(prefix="fnafhw_two_")
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(cls.tmp.name)
        cls.scratch = root / "ap"
        check.build_scratch(ARCHIPELAGO, cls.scratch, build_apworld(root))

    @staticmethod
    def world(options: str):
        get = lambda key, default: next((l.split(": ", 1)[1] for l in options.splitlines() if l.strip().startswith(key + ":")), default)  # noqa: E731
        goal = get("goal", "complete_all_minigames_nights")
        return dict(plan=check.plan_for(levels, get("unlock_mode", "per_section"), get("hard_variants", "grouped"), get("starting_section", "fnaf_1")),
                    goal=check.goal_location(data, goal), groups=(True, True, True), required_tapes=8, required_faz_tokens=15)

    def test_every_seed_is_beatable_with_the_real_rules_for_both_players(self):
        off_level = 0
        for index, (yochix, zinoxe) in enumerate(self.PAIRS):
            for seed in (1, 2, 3):
                with self.subTest(pair=index, seed=seed):
                    text, reason = check.generate_multi(self.scratch, {"Yochix": "  " + yochix, "Zinoxe": "  " + zinoxe}, seed, tag=f"two{index}{seed}")
                    self.assertIsNotNone(text, f"not generated / not beatable: {reason}")
                    worlds = {"Yochix": self.world(yochix), "Zinoxe": self.world(zinoxe)}
                    self.assertEqual(check.logic_problems(text, worlds, check.read_multidata(self.scratch, f"two{index}{seed}"), data, levels), [])
                    self.assertEqual(check.unreachable_warning(self.scratch, f"two{index}{seed}"), "")
                    off_level += check.unlock_items_off_levels(text, levels)
        self.assertGreater(off_level, 0, "unlock items can now sit on any really reachable check")


@unittest.skipUnless(INSTALLED, "no Archipelago install (set ARCHIPELAGO_DIR) or not Windows")
class TestTightSeedsInTheRealGenerator(unittest.TestCase):
    """per_level with prizes off: every goal that fits generates and passes the real-rule replay; one that cannot fit is refused with the message."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmp = tempfile.TemporaryDirectory(prefix="fnafhw_tight_")
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(cls.tmp.name)
        cls.scratch = root / "ap"
        check.build_scratch(ARCHIPELAGO, cls.scratch, build_apworld(root))

    def test_per_level_with_prizes_off(self):
        for goal in check.ALL_GOALS:
            for groups in ((False, False, True), (False, True, False), (False, True, True)):
                with self.subTest(goal=goal, groups=groups):
                    plan = check.plan_for(levels, "per_level", "grouped", "fnaf_1")
                    progression, usable = data.capacity(len(plan.pool_items), levels.FILLER_ONLY_CHECKS, groups, check.goal_location(data, goal), 8, 15)
                    tag = goal[:5] + "".join("1" if g else "0" for g in groups)
                    placements, reason = check.generate(self.scratch, goal, "per_level", "grouped", "fnaf_1", 1, groups, tag=tag)
                    if progression > usable:  # refused, and the message says what to change
                        self.assertIsNone(placements)
                        self.assertIn("OptionError", reason)
                        for word in ("randomize_prizes", "per_section"):
                            self.assertIn(word, reason)
                        continue
                    self.assertIsNotNone(placements, reason)
                    world = dict(plan=plan, goal=check.goal_location(data, goal), groups=groups, required_tapes=8, required_faz_tokens=15)
                    self.assertEqual(check.logic_problems(check.read_spoiler(self.scratch, tag), {"P1": world}, check.read_multidata(self.scratch, tag),
                                                          data, levels), [])
                    self.assertEqual(check.unreachable_warning(self.scratch, tag), "")
                    self.assertFalse(check.expected_refusal(data, levels, "per_level", "grouped", "fnaf_1", goal, groups))
                    tapes_needed, tokens_needed = data.tape_token_requirements(check.goal_location(data, goal), 8, 15, groups[2], groups[1])
                    self.assertEqual(check.token_problems(check.read_location_items(self.scratch, tag), groups, tokens_needed), [])


if __name__ == "__main__":
    unittest.main()
