"""Run the real Archipelago generator on this world and check the seeds (maintainer tool, not shipped).

Why: `--skip_output` does not check that a seed can be beaten, so a "fill only" run proves little (see docs/testing.md). This runs the FULL generator in a
scratch copy of your Archipelago install (the install itself is only read) over unlock modes x goals x starting sections x seeds, and for every seed it wrote:

  * the seed must be generated (a beatability failure raises FillError and writes no zip), and
  * no unlock item (section / hard / level pass) may sit on a location that is not a level-completion location (levels.may_hold_unlock_item): where tapes,
    tokens and prizes are in the real game is not modelled, so such a seed could be unfinishable.

Usage:  py scripts/generator_check.py [--archipelago C:\\ProgramData\\Archipelago] [--seeds 1,2,3] [--sections all|fnaf_1,fnaf_2,...] [--goals a,b]
Run the tests first: they rebuild dist/fnaf_help_wanted.apworld, which is what this checks. Exit code 1 when a required goal fails or an unlock item is misplaced.
"""

import argparse
import importlib.util
import itertools
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAME = "Five Nights at Freddy's: Help Wanted"
ALL_GOALS = ["complete_all_minigames_nights", "complete_all_minigames_nights_hard_mode", "glitchtrap_ending_die",
             "glitchtrap_ending_survive", "hundred_percent", "token_tape_quota"]
REQUIRED_GOALS = ["complete_all_minigames_nights"]  # the template's goal: it must always generate
MODES = [("per_section", "grouped"), ("per_section", "separate"), ("per_level", "grouped")]


def load_levels():
    spec = importlib.util.spec_from_file_location("_fnafhw_levels", ROOT / "fnaf_help_wanted" / "levels.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_spoiler_locations(text: str) -> dict[str, str]:
    """{location: item} from the 'Locations:' block of a single-player spoiler log ('Location Name: Item Name' per line; locations may contain ': ')."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "Locations:")
    placements = {}
    for line in lines[start + 1:]:
        if not line.strip():
            if placements:
                break
            continue
        location, item = line.rsplit(": ", 1)
        placements[location.strip()] = item.strip()
    return placements


def misplaced_unlock_items(placements: dict[str, str], unlock_items, may_hold) -> list[str]:
    """Locations that hold an unlock item although they may not."""
    return sorted(location for location, item in placements.items() if item in unlock_items and not may_hold(location))


def build_scratch(archipelago: Path, scratch: Path) -> None:
    scratch.mkdir(parents=True, exist_ok=True)
    shutil.copy2(archipelago / "ArchipelagoGenerate.exe", scratch)
    shutil.copy2(archipelago / "host.yaml", scratch)
    for dll in archipelago.glob("*.dll"):
        shutil.copy2(dll, scratch)
    for folder in ("lib", "data", "share"):
        shutil.copytree(archipelago / folder, scratch / folder)
    (scratch / "custom_worlds").mkdir()
    shutil.copy2(ROOT / "dist" / "fnaf_help_wanted.apworld", scratch / "custom_worlds" / "fnaf_help_wanted.apworld")


def generate(scratch: Path, goal: str, mode: str, hard: str, section: str, seed: int):
    players, out = scratch / "Players", scratch / "output"
    for folder in (players, out):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir()
    yaml = (f'name: P1\ngame: "{GAME}"\n"{GAME}":\n  goal: {goal}\n  unlock_mode: {mode}\n  hard_variants: {hard}\n'
            f"  starting_section: {section}\n  accessibility: full\n")
    (players / "p1.yaml").write_text(yaml, encoding="utf-8")
    run = subprocess.run([str(scratch / "ArchipelagoGenerate.exe"), "--player_files_path", str(players), "--outputpath", str(out), "--seed", str(seed)],
                         cwd=scratch, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)  # stdin closed: the exe waits for Enter on failure
    text = (run.stdout or "") + (run.stderr or "")
    zips = list(out.glob("*.zip"))
    if not zips or "FillError" in text:
        reason = re.search(r"FillError: (.*)", text) or re.search(r"Error[^\n]*", text)
        return None, (reason.group(0) if reason else "no zip written")[:120]
    with zipfile.ZipFile(zips[0]) as archive:
        spoiler = next(name for name in archive.namelist() if "Spoiler" in name)
        return parse_spoiler_locations(archive.read(spoiler).decode("utf-8", "replace")), ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--archipelago", default=r"C:\ProgramData\Archipelago")
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--sections", default="all")
    parser.add_argument("--goals", default=",".join(ALL_GOALS))
    args = parser.parse_args()

    levels = load_levels()
    sections = list(levels.SECTION_BY_KEY) if args.sections == "all" else args.sections.split(",")
    goals = args.goals.split(",")
    seeds = [int(s) for s in args.seeds.split(",")]
    if not (ROOT / "dist" / "fnaf_help_wanted.apworld").exists():
        print("dist/fnaf_help_wanted.apworld is missing: run the tests first (they rebuild it)")
        return 2

    failed_required = misplaced_total = 0
    with tempfile.TemporaryDirectory(prefix="fnafhw_gen_") as tmp:
        scratch = Path(tmp) / "ap"
        build_scratch(Path(args.archipelago), scratch)
        for goal in goals:
            generated = failed = misplaced = 0
            reasons = set()
            for (mode, hard), section, seed in itertools.product(MODES, sections, seeds):
                placements, reason = generate(scratch, goal, mode, hard, section, seed)
                if placements is None:
                    failed += 1
                    reasons.add(reason)
                    continue
                generated += 1
                bad = misplaced_unlock_items(placements, levels.MANAGED_ITEM_NAMES, levels.may_hold_unlock_item)
                if bad:
                    misplaced += 1
                    print(f"  MISPLACED ({mode}/{hard}/{section}/seed {seed}): {bad[:3]}")
            print(f"{goal:42s} generated={generated:3d} failed={failed:3d} seeds-with-misplaced-unlock-items={misplaced}"
                  + (f"   [{'; '.join(sorted(reasons))[:140]}]" if reasons else ""))
            misplaced_total += misplaced
            if goal in REQUIRED_GOALS:
                failed_required += failed
    print("RESULT:", "OK" if not (failed_required or misplaced_total) else "PROBLEM")
    return 1 if (failed_required or misplaced_total) else 0


if __name__ == "__main__":
    sys.exit(main())
