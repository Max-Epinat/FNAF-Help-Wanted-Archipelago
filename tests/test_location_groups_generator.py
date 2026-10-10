"""The group toggles through the REAL Archipelago generator (ArchipelagoGenerate.exe), full runs (never --skip_output: it skips the beatability check).

Builds the apworld from the working tree (so it never depends on a stale dist/), copies the Archipelago install into a scratch folder (the install itself is
only read) and generates one seed per combination of the three toggles. A seed counts only when its zip is written, which means it was generated AND
is beatable. Skipped when no Archipelago install is found (CI) or the run is not on Windows.
"""

import json
import os
import sys
import tempfile
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "scripts"))

import generator_check as check  # noqa: E402

ARCHIPELAGO = Path(os.environ.get("ARCHIPELAGO_DIR", r"C:\ProgramData\Archipelago"))
INSTALLED = (ARCHIPELAGO / "ArchipelagoGenerate.exe").exists() and sys.platform == "win32"
COMBINATIONS = [(p, t, g) for p in (True, False) for t in (True, False) for g in (True, False)]
NAME = {True: "on", False: "off"}


def build_apworld(target: Path) -> Path:
    """The same files scripts/build-apworld.ps1 puts into dist/fnaf_help_wanted.apworld (the folder, no caches, plus the vendored client files)."""
    world = project_root / "fnaf_help_wanted"
    vendored = json.loads((project_root / "scripts" / "vendored_client_files.json").read_text(encoding="utf-8"))
    path = target / "fnaf_help_wanted.apworld"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(world.rglob("*")):
            if file.is_file() and "__pycache__" not in file.parts:
                archive.write(file, "fnaf_help_wanted/" + file.relative_to(world).as_posix())
        for entry in vendored:
            archive.write(project_root / entry["source"], "fnaf_help_wanted/" + entry["target"])
    return path


@unittest.skipUnless(INSTALLED, "no Archipelago install (set ARCHIPELAGO_DIR) or not Windows")
class TestRealGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="fnafhw_groups_")
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(cls.tmp.name)
        apworld = build_apworld(root)
        cls.scratch = root / "ap"
        check.build_scratch(ARCHIPELAGO, cls.scratch, apworld)
        cls.data = check.load_data()
        cls.levels = check.load_levels()

    def run_all(self, jobs):
        """jobs: {tag: kwargs for check.generate}; parallel runs, one scratch folder, separate work folders."""
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {tag: pool.submit(check.generate, self.scratch, tag=tag, **kwargs) for tag, kwargs in jobs.items()}
            return {tag: future.result() for tag, future in futures.items()}

    def job(self, groups, goal="complete_all_minigames_nights", mode="per_section", hard="grouped", section="fnaf_1", seed=1, extra=""):
        return dict(goal=goal, mode=mode, hard=hard, section=section, seed=seed, groups=groups, extra_options=extra)

    def test_every_combination_of_the_three_toggles_generates_a_beatable_seed_with_the_right_locations(self):
        results = self.run_all({"c" + "".join(NAME[v][1] for v in combo): self.job(combo) for combo in COMBINATIONS})
        self.assertEqual(len(results), 8)
        for tag, (placements, reason) in results.items():
            combo = tuple(ch == "n" for ch in tag[1:])
            with self.subTest(prizes=combo[0], faz_tokens=combo[1], tapes=combo[2]):
                self.assertIsNotNone(placements, f"not generated / not beatable: {reason}")
                self.assertEqual(check.group_problems(placements, combo, self.data), [])
                expected = 50 + 57 * combo[0] + 30 * combo[1] + 16 * combo[2]
                self.assertEqual(len(placements), expected)
                self.assertEqual(check.misplaced_unlock_items(placements, self.levels.MANAGED_ITEM_NAMES, self.levels.may_hold_unlock_item), [])
                items = set(placements.values())
                self.assertEqual("Glitch Tape" in items, combo[2])  # no Glitch Tape item without tape locations
                if combo[1]:
                    self.assertNotIn("Faz Coupon", items)
                else:  # vanilla tokens: not a single Faz Token item is handed out, the spare slots hold the coupon
                    self.assertNotIn("Faz Token", items)
                    self.assertIn("Faz Coupon", items)

    def test_the_tightest_plan_with_every_group_off_still_generates(self):
        results = self.run_all({
            "level_off": self.job((False, False, False), mode="per_level", section="fnaf_1"),
            "separate_off": self.job((False, False, False), mode="per_section", hard="separate", section="night_terrors", seed=2),
        })
        for tag, (placements, reason) in results.items():
            with self.subTest(tag):
                self.assertIsNotNone(placements, reason)
                self.assertEqual(len(placements), 50)

    def test_goals_that_asked_for_tapes_still_generate_when_tapes_are_not_randomized(self):
        results = self.run_all({
            goal: self.job((True, True, False), goal=goal) for goal in ("glitchtrap_ending_die", "glitchtrap_ending_survive")})
        for goal, (placements, reason) in results.items():
            with self.subTest(goal):
                self.assertIsNotNone(placements, reason)
                self.assertEqual(check.group_problems(placements, (True, True, False), self.data), [])

    def test_a_yaml_that_excludes_a_location_of_a_group_that_is_off_is_not_an_error(self):
        extra = '  exclude_locations:\n    - "Collect Faz Token 01"\n    - "Prize - Plushie: Freddy Plush"\n'
        placements, reason = check.generate(self.scratch, "complete_all_minigames_nights", "per_section", "grouped", "fnaf_1", 3,
                                            (False, False, True), extra, tag="exclude")
        self.assertIsNotNone(placements, reason)
        self.assertEqual(check.group_problems(placements, (False, False, True), self.data), [])


if __name__ == "__main__":
    unittest.main()
