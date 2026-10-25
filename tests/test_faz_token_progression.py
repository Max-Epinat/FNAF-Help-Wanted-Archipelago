"""As many base Faz Tokens are progression as the goal needs (0, required_faz_tokens or all 30); the others and the spare-slot ones stay filler.

Why: the goals `hundred_percent` and `token_tape_quota` ask for Faz Token items (`state.has("Faz Token", n)`), and Archipelago only counts progression items in
`state.has`. With every Faz Token classified as filler those two goals could never be generated while the Faz Tokens are randomized (`FillError: Game appears
as unbeatable`, 2026-10-05 and again 2026-10-25). The filler Faz Tokens that fill the spare slots keep the filler classification: the logic never needs more
than the 30 base ones (`required_faz_tokens` tops out at 30), and ~96 extra progression items would only slow the fill and mislabel them in hints.
Both kinds are the same item (same name, same id): the mod counts Faz Token items by id for the TV, so the classification changes nothing in game.
Since 2026-10-25 only as many are progression as the goal needs (the user's choice "count by need"): the tight per_level seeds did not fit otherwise.

The pure part reads data.py; the rest runs the REAL generator (full runs, built from the working tree) and reads each item's classification flags back
from the generated `.archipelago` file. Skipped without an Archipelago install.
"""

import importlib.util
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "scripts"))
sys.path.insert(0, str(project_root / "tests"))

import generator_check as check  # noqa: E402
from test_location_groups_generator import ARCHIPELAGO, INSTALLED, build_apworld  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(f"_fnafhw_{name}", project_root / "fnaf_help_wanted" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


data = _load("data")


class TestFazTokenItemData(unittest.TestCase):
    def test_the_base_faz_tokens_are_progression_without_balancing_and_there_are_30(self):
        token = data.ITEM_TABLE["Faz Token"]
        self.assertTrue(token.progression)
        self.assertTrue(token.skip_balancing)  # 30 counted copies: progression balancing would only drag them early
        self.assertEqual(token.quantity, 30)
        self.assertEqual(token.quantity, len(data.FAZ_TOKEN_CHECKS))
        self.assertEqual(token.code, 11)  # the id the mod counts (101000011) never moves

    def test_the_filler_is_built_as_filler_whatever_create_item_says(self):
        """create_item("Faz Token") is what Archipelago calls for start_inventory and plando, so it gives a progression token; the spare slots go
        through create_filler, which must give a plain filler one."""
        init = (project_root / "fnaf_help_wanted" / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("def create_filler(self)", init)
        body = init.split("def create_filler(self)", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("ItemClassification.filler", body)
        self.assertIn("self.get_filler_item_name()", body)
        self.assertIn("pool.append(self.create_filler())", init)
        self.assertNotIn("pool.append(self.create_item(self.get_filler_item_name()))", init)

    def test_skip_balancing_maps_to_its_archipelago_classification(self):
        """Read statically: the seed file only keeps the progression bit, so a real seed cannot show this one."""
        init = (project_root / "fnaf_help_wanted" / "__init__.py").read_text(encoding="utf-8")
        body = init.split("def _get_item_classification(", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("ItemClassification.progression_skip_balancing if item_data.skip_balancing else ItemClassification.progression", body)

    def test_the_tape_items_and_the_coupon_are_unchanged(self):
        for name in data.TAPE_ITEM_NAMES:
            self.assertTrue(data.ITEM_TABLE[name].progression)
            self.assertFalse(data.ITEM_TABLE[name].skip_balancing)
        self.assertNotIn("Faz Coupon", data.ITEM_TABLE)


@unittest.skipUnless(INSTALLED, "no Archipelago install (set ARCHIPELAGO_DIR) or not Windows")
class TestFazTokenClassificationInRealSeeds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="fnafhw_tokens_")
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(cls.tmp.name)
        cls.scratch = root / "ap"
        check.build_scratch(ARCHIPELAGO, cls.scratch, build_apworld(root))

    def run_all(self, jobs):
        """jobs: {tag: (goal, groups, extra yaml)} -> {tag: (placements, reason, location items)}; parallel, one scratch folder."""
        def one(tag, goal, groups, extra):
            placements, reason = check.generate(self.scratch, goal, "per_section", "grouped", "fnaf_1", 1, groups, extra, tag=tag)
            return placements, reason, (check.read_location_items(self.scratch, tag) if placements is not None else [])
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {tag: pool.submit(one, tag, *job) for tag, job in jobs.items()}
            return {tag: future.result() for tag, future in futures.items()}

    def test_the_token_goals_generate_and_exactly_the_needed_tokens_are_progression(self):
        on = (True, True, True)
        results = self.run_all({
            "hundred": ("hundred_percent", on, ""),
            "quota": ("token_tape_quota", on, ""),
            "quota30": ("token_tape_quota", on, "  required_faz_tokens: 30\n  required_tapes: 16\n"),
            "levels": ("complete_all_minigames_nights", on, ""),  # a goal that does not need tokens: none is progression
            "tokens_off": ("token_tape_quota", (True, False, True), ""),
            "from_pool": ("hundred_percent", on, "  start_inventory_from_pool:\n    Faz Token: 5\n"),
        })
        for tag, (placements, reason, items) in results.items():
            with self.subTest(tag):
                self.assertIsNotNone(placements, f"not generated / not beatable: {reason}")
                groups = (True, False, True) if tag == "tokens_off" else on
                needed = {"hundred": 30, "quota": 15, "quota30": 30, "levels": 0, "tokens_off": 0}
                if tag != "from_pool":  # five tokens went to the start inventory, the rest of the pool is unchanged
                    self.assertEqual(check.token_problems(items, groups, needed[tag]), [])
                # unique tapes: the 16 tape items once each, as many progression as the goal needs (default required_tapes 8)
                tapes_needed = {"hundred": 16, "quota": 8, "quota30": 16, "levels": 0, "tokens_off": 8, "from_pool": 16}
                self.assertEqual(check.tape_problems(items, groups, tapes_needed[tag]), [])
        self.assertTrue(any(i == check.FAZ_TOKEN_ID and not f & 1 for i, _, f in results["levels"][2]), "the default seed has filler Faz Tokens")
        # what the server and every client see: plain progression (1), like a Glitch Tape; the skip-balancing bit never leaves the generator
        progression_flags = {f for i, _, f in results["hundred"][2] if i == check.FAZ_TOKEN_ID and f & 1}
        self.assertEqual(progression_flags, {0b0001})


if __name__ == "__main__":
    unittest.main()
