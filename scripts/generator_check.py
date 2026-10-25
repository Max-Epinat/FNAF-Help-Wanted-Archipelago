"""Run the real Archipelago generator on this world and check the seeds (maintainer tool, not shipped).

Why: `--skip_output` does not check that a seed can be beaten, so a "fill only" run proves little (see docs/testing.md). This runs the FULL generator in a
scratch copy of your Archipelago install (the install itself is only read) over unlock modes x goals x starting sections x seeds, and for every seed it wrote:

  * the seed must be generated (a beatability failure raises FillError and writes no zip), and
  * replaying the seed with an independent copy of the REAL access rules (levels.PICKUP_MAPS & co, read from the game's files) must reach every location
    and the goal, and no filler-only check may hold a progression or useful item (logic_problems). Unlock items may sit anywhere really reachable.

A third check covers the location-group toggles (randomize_prizes / randomize_faz_tokens / randomize_glitch_tapes): the spoiler must list exactly the locations
the toggles leave in the multiworld (none of a group that is off, all of a group that is on).

Usage:  py scripts/generator_check.py [--archipelago <Archipelago folder, default %ProgramData%\\Archipelago>] [--seeds 1,2,3] [--sections all|fnaf_1,fnaf_2,...] [--goals a,b]
                                      [--groups on,off,prizes,faz_tokens+tapes,...]
--groups: `on` = every group randomized (the default), `off` = none, otherwise the groups joined by `+` are randomized and the others are not.
Run the tests first: they rebuild dist/fnaf_help_wanted.apworld, which is what this checks. Exit code 1 when any goal fails, the replay with the real rules fails, a location group is wrong or the Faz Token classification is wrong.
"""

import argparse
import importlib.util
import io
import itertools
import os
import pickle
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAME = "Five Nights at Freddy's: Help Wanted"
ALL_GOALS = ["complete_all_minigames_nights", "complete_all_minigames_nights_hard_mode", "glitchtrap_ending_die",
             "glitchtrap_ending_survive", "hundred_percent", "token_tape_quota"]
REQUIRED_GOALS = ALL_GOALS  # every goal must generate (since 2026-10-25); a failing goal makes the run a PROBLEM
MODES = [("per_section", "grouped"), ("per_section", "separate"), ("per_level", "grouped")]


def _load_world_module(name):
    spec = importlib.util.spec_from_file_location(f"_fnafhw_{name}", ROOT / "fnaf_help_wanted" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_levels():
    return _load_world_module("levels")


def load_data():
    return _load_world_module("data")


GROUP_OPTIONS = {"prizes": "randomize_prizes", "faz_tokens": "randomize_faz_tokens", "tapes": "randomize_glitch_tapes"}


def parse_groups(text: str) -> tuple[bool, bool, bool]:
    """'on' -> (True, True, True), 'off' -> all False, 'prizes+tapes' -> those two on (order: prizes, faz_tokens, tapes)."""
    if text == "on":
        return (True, True, True)
    if text == "off":
        return (False, False, False)
    wanted = set(text.split("+"))
    unknown = wanted - set(GROUP_OPTIONS)
    if unknown:
        raise ValueError(f"unknown group(s) {sorted(unknown)}; use on, off or a + joined list of {sorted(GROUP_OPTIONS)}")
    return tuple(key in wanted for key in GROUP_OPTIONS)  # type: ignore[return-value]


def goal_location(data, goal: str) -> str:
    """Option value name -> goal location name."""
    return dict(zip(ALL_GOALS, data.GOAL_CHECKS))[goal]


def group_problems(placements: dict[str, str], groups: tuple[bool, bool, bool], data, goal: str = "complete_all_minigames_nights") -> list[str]:
    """What the spoiler gets wrong about the created locations: a location of a group that is off (or a never-sent check, or an unused goal),
    a missing one, or a wrong total."""
    expected = {name for names in data.region_locations(*groups, goal=goal_location(data, goal)).values() for name in names}
    problems = []
    extra = sorted(set(placements) - expected)
    missing = sorted(expected - set(placements))
    if extra:
        problems.append(f"{len(extra)} location(s) that should not exist, e.g. {extra[:2]}")
    if missing:
        problems.append(f"{len(missing)} location(s) missing, e.g. {missing[:2]}")
    if len(placements) != len(expected):
        problems.append(f"{len(placements)} locations, expected {len(expected)}")
    items = set(placements.values())
    if not groups[1] and "Faz Token" in items:
        problems.append("a Faz Token item although the Faz Tokens are not randomized (the filler should be Faz Coupon)")
    if groups[1] and "Faz Coupon" in items:
        problems.append("a Faz Coupon although the Faz Tokens are randomized")
    return problems


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


def parse_seed(text: str) -> tuple[list[str], dict[tuple[str, str], tuple[str, str]], list[tuple[str, str]]]:
    """(player names in id order, {(location, its player): (item, its player)}, [(start item, player)]) from a spoiler with 1..n players.
    With one player the spoiler has no '(Player)' suffixes; with several, the known player names tell the suffix apart from '(Hard)' and co."""
    lines = text.splitlines()
    names = [m.group(1) for m in (re.match(r"^Player \d+: (.+)$", line) for line in lines) if m] or ["P1"]
    single = len(names) == 1

    def split(part: str) -> tuple[str, str]:
        if single:
            return part.strip(), names[0]
        for name in names:
            if part.endswith(f" ({name})"):
                return part[:-len(name) - 3].strip(), name
        raise ValueError(f"no player suffix in {part!r}")

    def block(header: str) -> list[str]:
        start = next(i for i, line in enumerate(lines) if line.strip() == header)
        out = []
        for line in lines[start + 1:]:
            if not line.strip():
                if out:
                    break
                continue
            out.append(line.strip())
        return out

    placements = {}
    for line in block("Locations:"):
        if single:
            location, item = line.rsplit(": ", 1)
            placements[split(location)] = split(item)
            continue
        for name in names:  # the location part ends with " (<player>): "
            marker = f" ({name}): "
            if marker in line:
                location, item = line.split(marker, 1)
                placements[(location.strip(), name)] = split(item)
                break
    start_items = [split(line) for line in block("Starting Items:")] if any(line.strip() == "Starting Items:" for line in lines) else []
    return names, placements, start_items


def read_multidata(scratch: Path, tag: str = "run") -> dict[int, dict[int, tuple[int, int, int]]]:
    """{player id: {location id: (item id, owning player, classification flags)}} of the seed generate() just wrote for `tag`."""
    with zipfile.ZipFile(next((scratch / f"output_{tag}").glob("*.zip"))) as archive:
        raw = archive.read(next(name for name in archive.namelist() if name.endswith(".archipelago")))
    multidata = _LooseUnpickler(io.BytesIO(zlib.decompress(raw[1:]))).load()  # one version byte, then a zlib-compressed pickle
    return {player: {loc: tuple(entry[:3]) for loc, entry in locations.items()} for player, locations in multidata["locations"].items()}


def logic_problems(text: str, worlds: dict, multidata: dict, data, levels) -> list[str]:
    """Replay a seed with an independent copy of the REAL access rules and report what fails.

    worlds: {player name: dict(plan=levels.GatingPlan, goal=goal location name, groups=(prizes, tokens, tapes), required_tapes=n, required_faz_tokens=n)}
    for the FNAF players (any other game is ignored). Every created location of those players must be reached, so must their goal, and no
    filler-only check may hold a progression or useful item. Mirrors the rules on purpose instead of importing rules.py: it checks the wiring."""
    names, placements, start_items = parse_seed(text)
    ids = {name: i + 1 for i, name in enumerate(names)}
    have: dict[tuple[str, str], int] = {}
    tokens: dict[str, int] = {}  # progression Faz Tokens / Glitch Tapes received (only those count for the goals, like state.has)
    tapes: dict[str, int] = {}
    for item, player in start_items:
        have[(item, player)] = have.get((item, player), 0) + 1

    def flags(location: str, player: str) -> int:
        code = data.LOCATION_OFFSET + data.LOCATION_TABLE[location].code
        return multidata[ids[player]][code][2]

    reached: set[tuple[str, str]] = set()

    def owns(item: str, player: str) -> bool:
        return have.get((item, player), 0) > 0

    def rule(location: str, player: str) -> bool:
        w = worlds[player]
        plan = w["plan"]
        if location == data.GOAL_GLITCHTRAP_SURVIVE and w["goal"] != location:  # filler only when not the goal: every level
            return all(owns(item, player) for item in plan.location_items[levels.PIZZA_PARTY_LOCATION])
        if location in data.GOAL_CHECKS:
            tapes_needed, tokens_needed = data.tape_token_requirements(location, w["required_tapes"], w["required_faz_tokens"], w["groups"][2], w["groups"][1])
            counts = tapes.get(player, 0) >= tapes_needed and tokens.get(player, 0) >= tokens_needed
            levels_done = all((name, player) in reached for name in data.MINIGAME_AND_NIGHT_CHECKS)
            party = (levels.PIZZA_PARTY_LOCATION, player) in reached
            return {
                data.GOAL_COMPLETE_ALL_MINIGAMES: levels_done,
                data.GOAL_COMPLETE_ALL_MINIGAMES_HARD: levels_done and party,
                data.GOAL_GLITCHTRAP_DIE: party and counts,
                data.GOAL_GLITCHTRAP_SURVIVE: party and counts and owns("Prize Counter Key", player),
                data.GOAL_HUNDRED_PERCENT: counts and all((name, player) in reached for name in data.full_clear_checks(*w["groups"])),
                data.GOAL_TOKEN_TAPE_QUOTA: counts,
            }[location]
        if location in plan.location_items:
            return all(owns(item, player) for item in plan.location_items[location])
        if location.startswith("Prize - "):
            return any(owns(item, player) for item in plan.any_level_items)
        if location in levels.FREE_CHECKS:
            return True
        raise KeyError(f"no real rule known for {location!r}")

    fnaf = {key: value for key, value in placements.items() if key[1] in worlds}
    changed = True
    while changed:
        changed = False
        for (location, player), (item, owner) in fnaf.items():
            if (location, player) in reached or not rule(location, player):
                continue
            reached.add((location, player))
            changed = True
            have[(item, owner)] = have.get((item, owner), 0) + 1
            if item in ("Faz Token", "Glitch Tape") and owner in worlds and flags(location, player) & PROGRESSION_FLAG:
                counter = tokens if item == "Faz Token" else tapes
                counter[owner] = counter.get(owner, 0) + 1
    problems = []
    for player, w in worlds.items():
        missing = sorted(location for (location, p) in fnaf if p == player and (location, p) not in reached)
        if missing:
            problems.append(f"{player}: {len(missing)} location(s) not reachable with the real rules, e.g. {missing[:3]}")
        if (w["goal"], player) not in reached:
            problems.append(f"{player}: goal not reachable with the real rules")
        filler_only = levels.FILLER_ONLY_CHECKS | ({data.GOAL_GLITCHTRAP_SURVIVE} - {w["goal"]})
        bad = sorted(location for (location, p) in fnaf if p == player and location in filler_only and flags(location, p) & 0b0011)
        if bad:
            problems.append(f"{player}: progression or useful item on filler-only check(s) {bad[:3]}")
    return problems


def unlock_items_off_levels(text: str, levels) -> int:
    """How many unlock items sit on a location that is not a level (possible since the stopgap was removed)."""
    _names, placements, _start = parse_seed(text)
    return sum(1 for (location, _p), (item, _o) in placements.items() if item in levels.MANAGED_ITEM_NAMES and location not in levels.LEVEL_BY_LOCATION)


UNREACHABLE_WARNING = "Could not access required locations"


def unreachable_warning(scratch: Path, tag: str = "run") -> str:
    """The generator's warning about locations the logic can never reach ('' when there is none): with the real rules there must be none."""
    log = scratch / f"log_{tag}.txt"
    text = log.read_text(encoding="utf-8") if log.exists() else ""
    line = next((l for l in text.splitlines() if UNREACHABLE_WARNING in l), "")
    return line[:300]


def expected_refusal(data, levels, mode: str, hard: str, section: str, goal: str, groups, required_tapes: int = 8, required_faz_tokens: int = 15) -> bool:
    """True when the seed has more progression items than checks that may hold them: the world refuses it with an OptionError (data.capacity)."""
    plan = plan_for(levels, mode, hard, section)
    progression, usable = data.capacity(len(plan.pool_items), levels.FILLER_ONLY_CHECKS, groups, goal_location(data, goal), required_tapes, required_faz_tokens)
    return progression > usable


def read_spoiler(scratch: Path, tag: str = "run") -> str:
    with zipfile.ZipFile(next((scratch / f"output_{tag}").glob("*.zip"))) as archive:
        return archive.read(next(name for name in archive.namelist() if "Spoiler" in name)).decode("utf-8", "replace")


def plan_for(levels, mode: str, hard: str, section: str):
    return levels.build_plan(levels.UNLOCK_PER_LEVEL if mode == "per_level" else levels.UNLOCK_PER_SECTION,
                             levels.HARD_SEPARATE if hard == "separate" else levels.HARD_GROUPED, section)


FAZ_TOKEN_ID = 101000011  # data.ITEM_OFFSET + 11, the id the mod counts for the TV
PROGRESSION_FLAG = 0b0001  # ItemClassification.progression in the flags the server sends with every item


class _LooseUnpickler(pickle.Unpickler):
    """Reads the generated .archipelago file without Archipelago's modules: any class it names becomes an empty stand-in (only plain data is used)."""

    def find_class(self, module, name):
        try:
            return super().find_class(module, name)
        except Exception:
            return type(name, (), {"__init__": lambda self, *a, **k: None, "__setstate__": lambda self, state: None})


def read_location_items(scratch: Path, tag: str = "run", player: int = 1) -> list[tuple[int, int, int]]:
    """(item id, owning player, classification flags) of every location of `player` in the seed generate() just wrote for `tag`."""
    with zipfile.ZipFile(next((scratch / f"output_{tag}").glob("*.zip"))) as archive:
        raw = archive.read(next(name for name in archive.namelist() if name.endswith(".archipelago")))
    multidata = _LooseUnpickler(io.BytesIO(zlib.decompress(raw[1:]))).load()  # one version byte, then a zlib-compressed pickle
    return [tuple(entry[:3]) for entry in multidata["locations"][player].values()]


def token_problems(location_items, groups: tuple[bool, bool, bool], base_tokens: int = 30) -> list[str]:
    """With the Faz Tokens randomized exactly `base_tokens` Faz Tokens are progression (as many as the goal needs: 0, required_faz_tokens or 30) and
    every other Faz Token is plain filler; with them off there is no Faz Token item at all."""
    flags = [f for item_id, _player, f in location_items if item_id == FAZ_TOKEN_ID]
    if not groups[1]:
        return [f"{len(flags)} Faz Token item(s) although the Faz Tokens are not randomized"] if flags else []
    problems = []
    progression = sum(1 for f in flags if f & PROGRESSION_FLAG)
    if progression != base_tokens:
        problems.append(f"{progression} progression Faz Tokens, expected {base_tokens}")
    odd = sorted({f for f in flags if not f & PROGRESSION_FLAG and f != 0})
    if odd:
        problems.append(f"filler Faz Tokens with flags {odd}, expected 0 (plain filler)")
    return problems


def build_scratch(archipelago: Path, scratch: Path, apworld: Path | None = None) -> None:
    scratch.mkdir(parents=True, exist_ok=True)
    shutil.copy2(archipelago / "ArchipelagoGenerate.exe", scratch)
    shutil.copy2(archipelago / "host.yaml", scratch)
    for dll in archipelago.glob("*.dll"):
        shutil.copy2(dll, scratch)
    for folder in ("lib", "data", "share"):
        shutil.copytree(archipelago / folder, scratch / folder)
    (scratch / "custom_worlds").mkdir()
    shutil.copy2(apworld or ROOT / "dist" / "fnaf_help_wanted.apworld", scratch / "custom_worlds" / "fnaf_help_wanted.apworld")


def generate(scratch: Path, goal: str, mode: str, hard: str, section: str, seed: int,
             groups: tuple[bool, bool, bool] = (True, True, True), extra_options: str = "", tag: str = "run"):
    """Run the real generator once. `extra_options` is raw yaml appended to the game section (two-space indented lines); `tag` keeps parallel runs apart."""
    players, out = scratch / f"Players_{tag}", scratch / f"output_{tag}"
    for folder in (players, out):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir()
    group_yaml = "".join(f"  {option}: {'true' if on else 'false'}\n" for on, option in zip(groups, GROUP_OPTIONS.values()))
    yaml = (f'name: P1\ngame: "{GAME}"\n"{GAME}":\n  goal: {goal}\n  unlock_mode: {mode}\n  hard_variants: {hard}\n'
            f"  starting_section: {section}\n  accessibility: full\n{group_yaml}{extra_options}")
    (players / "p1.yaml").write_text(yaml, encoding="utf-8")
    run = subprocess.run([str(scratch / "ArchipelagoGenerate.exe"), "--player_files_path", str(players), "--outputpath", str(out), "--seed", str(seed)],
                         cwd=scratch, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)  # stdin closed: the exe waits for Enter on failure
    text = (run.stdout or "") + (run.stderr or "")
    (scratch / f"log_{tag}.txt").write_text(text, encoding="utf-8")
    zips = list(out.glob("*.zip"))
    if not zips or "FillError" in text:
        reason = re.search(r"OptionError: (.*)", text) or re.search(r"FillError: (.*)", text) or re.search(r"Error[^\n]*", text)
        return None, (reason.group(0) if reason else "no zip written")[:400]
    with zipfile.ZipFile(zips[0]) as archive:
        spoiler = next(name for name in archive.namelist() if "Spoiler" in name)
        return parse_spoiler_locations(archive.read(spoiler).decode("utf-8", "replace")), ""


def generate_multi(scratch: Path, yamls: dict[str, str], seed: int, tag: str = "multi") -> tuple[str | None, str]:
    """Run the real generator once with several players: {player name: the game section's options as two-space indented yaml}.
    Returns (spoiler text, "") or (None, reason)."""
    players, out = scratch / f"Players_{tag}", scratch / f"output_{tag}"
    for folder in (players, out):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir()
    for index, (name, options) in enumerate(yamls.items(), 1):
        (players / f"p{index}_{name}.yaml").write_text(f'name: {name}\ngame: "{GAME}"\n"{GAME}":\n  accessibility: full\n{options}', encoding="utf-8")
    run = subprocess.run([str(scratch / "ArchipelagoGenerate.exe"), "--player_files_path", str(players), "--outputpath", str(out), "--seed", str(seed)],
                         cwd=scratch, capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
    text = (run.stdout or "") + (run.stderr or "")
    (scratch / f"log_{tag}.txt").write_text(text, encoding="utf-8")
    if not list(out.glob("*.zip")) or "FillError" in text:
        reason = re.search(r"FillError: (.*)", text) or re.search(r"Error[^\n]*", text)
        return None, (reason.group(0) if reason else "no zip written")[:160]
    return read_spoiler(scratch, tag), ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--archipelago", default=os.path.join(os.environ.get("ProgramData", ""), "Archipelago"),
                        help="the Archipelago installation (default: %%ProgramData%%\\Archipelago)")
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--sections", default="all")
    parser.add_argument("--goals", default=",".join(ALL_GOALS))
    parser.add_argument("--groups", default="on", help="location-group combinations to run, comma separated (see the top of this file)")
    args = parser.parse_args()

    levels = load_levels()
    sections = list(levels.SECTION_BY_KEY) if args.sections == "all" else args.sections.split(",")
    goals = args.goals.split(",")
    seeds = [int(s) for s in args.seeds.split(",")]
    group_runs = [(text, parse_groups(text)) for text in args.groups.split(",")]
    data = load_data()
    if not (ROOT / "dist" / "fnaf_help_wanted.apworld").exists():
        print("dist/fnaf_help_wanted.apworld is missing: run the tests first (they rebuild it)")
        return 2

    failed_required = logic_total = group_total = off_level_runs = 0
    with tempfile.TemporaryDirectory(prefix="fnafhw_gen_") as tmp:
        scratch = Path(tmp) / "ap"
        build_scratch(Path(args.archipelago), scratch)
        for goal in goals:
            for group_text, groups in group_runs:
                generated = failed = logic_bad = group_bad = refused = 0
                reasons = set()
                for (mode, hard), section, seed in itertools.product(MODES, sections, seeds):
                    placements, reason = generate(scratch, goal, mode, hard, section, seed, groups)
                    refuse = expected_refusal(data, levels, mode, hard, section, goal, groups)
                    if refuse or placements is None:
                        if refuse and placements is None and "OptionError" in reason:
                            refused += 1  # too many important items for this combination: refused with the message, as intended
                        else:
                            failed += 1
                            reasons.add(reason if placements is None else "generated although it should have been refused")
                        continue
                    warning = unreachable_warning(scratch)
                    if warning:
                        logic_bad += 1
                        print(f"  UNREACHABLE ({mode}/{hard}/{section}/seed {seed}): {warning}")
                    generated += 1
                    text = read_spoiler(scratch)
                    world = dict(plan=plan_for(levels, mode, hard, section), goal=goal_location(data, goal), groups=groups,
                                 required_tapes=8, required_faz_tokens=15)  # the option defaults (the yaml does not set them)
                    bad = logic_problems(text, {"P1": world}, read_multidata(scratch), data, levels)
                    if bad:
                        logic_bad += 1
                        print(f"  REAL RULES ({mode}/{hard}/{section}/seed {seed}): {'; '.join(bad)}")
                    off_level_runs += unlock_items_off_levels(text, levels) > 0
                    tokens_needed = data.tape_token_requirements(goal_location(data, goal), 8, 15, groups[2], groups[1])[1]
                    wrong = group_problems(placements, groups, data, goal) + token_problems(read_location_items(scratch), groups, tokens_needed)
                    if wrong:
                        group_bad += 1
                        print(f"  GROUPS {group_text} ({mode}/{hard}/{section}/seed {seed}): {'; '.join(wrong)}")
                label = goal if len(group_runs) == 1 and group_text == "on" else f"{goal} [{group_text}]"
                print(f"{label:52s} generated={generated:3d} failed={failed:3d} refused-as-expected={refused} real-rule-problems={logic_bad} group-problems={group_bad}"
                      + (f"   [{'; '.join(sorted(reasons))[:140]}]" if reasons else ""))
                logic_total += logic_bad
                group_total += group_bad
                if goal in REQUIRED_GOALS:
                    failed_required += failed
    print(f"runs with an unlock item on a non-level check (allowed since the stopgap was removed): {off_level_runs}")
    problem = failed_required or logic_total or group_total
    print("RESULT:", "OK" if not problem else "PROBLEM")
    return 1 if problem else 0


if __name__ == "__main__":
    sys.exit(main())
