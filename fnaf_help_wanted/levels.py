"""Level structure and Archipelago-authoritative unlock plan.

Pure data and pure functions: nothing here imports Archipelago, so it is unit-testable without it.

Rows are the game's ``LevelInfoTable`` rows (VERIFIED from the table dump, see docs/level-gating.md).
Pizza Party (row 29) is intentionally absent: it is never gated.

Item codes are append-only: 1..13 live in ``data.ITEM_TABLE`` and never change; the codes below
(14..59) were appended after them, and ``data.EXTRA_ITEM_CODES`` continues at 60. Never renumber or reuse a code.

Gate ids (``^[A-Z0-9_]+$``) are what the game mod sees; item names are what the Archipelago pool sees.
"""

from dataclasses import dataclass

UNLOCK_PER_SECTION = 0
UNLOCK_PER_LEVEL = 1

HARD_GROUPED = 0
HARD_SEPARATE = 1

PIZZA_PARTY_LOCATION = "Complete Pizza Party"


@dataclass(frozen=True)
class Section:
    key: str
    gate: str
    item: str  # existing item (codes 2..8), never renumbered
    hard_gate: str | None = None
    hard_item: str | None = None
    hard_item_code: int | None = None


# Order = option value order of ``starting_section``.
SECTIONS: tuple[Section, ...] = (
    Section("fnaf_1", "FNAF1", "FNAF 1 Access Pass", "FNAF1_HARD", "FNAF 1 Hard Pass", 14),
    Section("fnaf_2", "FNAF2", "FNAF 2 Access Pass", "FNAF2_HARD", "FNAF 2 Hard Pass", 15),
    Section("fnaf_3", "FNAF3", "FNAF 3 Access Pass", "FNAF3_HARD", "FNAF 3 Hard Pass", 16),
    Section("parts_and_service", "PARTS_SERVICE", "Parts and Service Toolkit",
            "PARTS_SERVICE_HARD", "Parts and Service Hard Toolkit", 17),
    Section("vent_repair", "VENT_REPAIR", "Vent Repair Toolkit",
            "VENT_REPAIR_HARD", "Vent Repair Hard Toolkit", 18),
    Section("dark_rooms", "DARK_ROOMS", "Dark Rooms Flashlight",
            "DARK_ROOMS_HARD", "Dark Rooms Hard Flashlight", 19),
    Section("night_terrors", "NIGHT_TERRORS", "Night Terrors Security Badge"),
)

SECTION_BY_KEY = {section.key: section for section in SECTIONS}


@dataclass(frozen=True)
class Level:
    row: int
    item_code: int
    location: str
    gate: str  # per-level gate id
    section: str
    hard: bool

    @property
    def item(self) -> str:
        return level_item_name(self.location)


def level_item_name(location: str) -> str:
    """'Beat FNAF 1 - Night 2' -> 'Unlock FNAF 1 - Night 2'."""
    for prefix in ("Beat ", "Complete "):
        if location.startswith(prefix):
            return "Unlock " + location[len(prefix):]
    raise ValueError(f"Unexpected level location name: {location!r}")


# (row, item_code, location, gate, section, hard)
#
# There is deliberately no "previous level" chain: an item unlocks its level on its own, whatever the game's own
# prerequisite is (the mod raises the game's locked answer for an authorized gate, see docs/level-gating.md).
_LEVEL_ROWS = (
    (0, 20, "Complete Dark Rooms - Plushtrap", "DARK_PLUSHTRAP", "dark_rooms", False),
    (1, 21, "Complete Dark Rooms - Nightmare BB", "DARK_NIGHTMARE_BB", "dark_rooms", False),
    (2, 22, "Complete Dark Rooms - Plushbaby", "DARK_PLUSHBABY", "dark_rooms", False),
    (3, 23, "Complete Dark Rooms - Funtime Foxy", "DARK_FUNTIME_FOXY", "dark_rooms", False),
    (4, 24, "Beat FNAF 1 - Night 1", "FNAF1_NIGHT1", "fnaf_1", False),
    (5, 25, "Beat FNAF 1 - Night 2", "FNAF1_NIGHT2", "fnaf_1", False),
    (6, 26, "Beat FNAF 1 - Night 3", "FNAF1_NIGHT3", "fnaf_1", False),
    (7, 27, "Beat FNAF 1 - Night 4", "FNAF1_NIGHT4", "fnaf_1", False),
    (8, 28, "Beat FNAF 1 - Night 5 (Hard)", "FNAF1_NIGHT5_HARD", "fnaf_1", True),
    (9, 29, "Beat FNAF 2 - Night 1", "FNAF2_NIGHT1", "fnaf_2", False),
    (10, 30, "Beat FNAF 2 - Night 2", "FNAF2_NIGHT2", "fnaf_2", False),
    (11, 31, "Beat FNAF 2 - Night 3", "FNAF2_NIGHT3", "fnaf_2", False),
    (12, 32, "Beat FNAF 2 - Night 4", "FNAF2_NIGHT4", "fnaf_2", False),
    (13, 33, "Beat FNAF 2 - Night 5 (Hard)", "FNAF2_NIGHT5_HARD", "fnaf_2", True),
    (14, 34, "Beat FNAF 3 - Night 1", "FNAF3_NIGHT1", "fnaf_3", False),
    (15, 35, "Beat FNAF 3 - Night 2", "FNAF3_NIGHT2", "fnaf_3", False),
    (16, 36, "Beat FNAF 3 - Night 3", "FNAF3_NIGHT3", "fnaf_3", False),
    (17, 37, "Beat FNAF 3 - Night 4", "FNAF3_NIGHT4", "fnaf_3", False),
    (18, 38, "Beat FNAF 3 - Night 5 (Hard)", "FNAF3_NIGHT5_HARD", "fnaf_3", True),
    (19, 39, "Complete Parts and Service - Bonnie", "PS_BONNIE", "parts_and_service", False),
    (20, 40, "Complete Parts and Service - Chica", "PS_CHICA", "parts_and_service", False),
    (21, 41, "Complete Parts and Service - Freddy", "PS_FREDDY", "parts_and_service", False),
    (22, 42, "Complete Parts and Service - Foxy", "PS_FOXY", "parts_and_service", False),
    (23, 43, "Complete Vent Repair - Mangle", "VENT_MANGLE", "vent_repair", False),
    (24, 44, "Complete Vent Repair - Ennard", "VENT_ENNARD", "vent_repair", False),
    (25, 45, "Complete Night Terrors - Funtime Freddy", "NT_FUNTIME_FREDDY", "night_terrors", False),
    (26, 46, "Complete Night Terrors - Nightmarionne", "NT_NIGHTMARIONNE", "night_terrors", False),
    (27, 47, "Complete Night Terrors - Circus Baby", "NT_CIRCUS_BABY", "night_terrors", False),
    (28, 48, "Complete Night Terrors - Nightmare Fredbear", "NT_NIGHTMARE_FREDBEAR", "night_terrors", False),
    # row 29 = Pizza Party: never gated
    (30, 49, "Complete Dark Rooms (Hard) - Plushtrap", "DARK_HARD_PLUSHTRAP", "dark_rooms", True),
    (31, 50, "Complete Dark Rooms (Hard) - Nightmare BB", "DARK_HARD_NIGHTMARE_BB", "dark_rooms", True),
    (32, 51, "Complete Parts and Service (Hard) - Bonnie", "PS_HARD_BONNIE", "parts_and_service", True),
    (33, 52, "Complete Parts and Service (Hard) - Chica", "PS_HARD_CHICA", "parts_and_service", True),
    (34, 53, "Complete Parts and Service (Hard) - Freddy", "PS_HARD_FREDDY", "parts_and_service", True),
    (35, 54, "Complete Parts and Service (Hard) - Foxy", "PS_HARD_FOXY", "parts_and_service", True),
    (36, 55, "Complete Dark Rooms (Hard) - Plushbaby", "DARK_HARD_PLUSHBABY", "dark_rooms", True),
    (37, 56, "Complete Dark Rooms (Hard) - Funtime Foxy", "DARK_HARD_FUNTIME_FOXY", "dark_rooms", True),
    (38, 57, "Complete Vent Repair (Hard) - Mangle", "VENT_HARD_MANGLE", "vent_repair", True),
    (39, 58, "Complete Vent Repair (Hard) - Ennard", "VENT_HARD_ENNARD", "vent_repair", True),
    (40, 59, "Beat FNAF 2 - Withered", "FNAF2_WITHERED", "fnaf_2", True),
)

LEVELS: tuple[Level, ...] = tuple(Level(*row) for row in _LEVEL_ROWS)
LEVEL_BY_ROW = {level.row: level for level in LEVELS}
LEVEL_BY_LOCATION = {level.location: level for level in LEVELS}

# Everything the plan manages: these are never part of the always-present base pool.
HARD_ITEM_CODES = {s.hard_item: s.hard_item_code for s in SECTIONS if s.hard_item}
LEVEL_ITEM_CODES = {level.item: level.item_code for level in LEVELS}
SECTION_ITEM_NAMES = tuple(s.item for s in SECTIONS)
MANAGED_ITEM_NAMES = frozenset(SECTION_ITEM_NAMES) | frozenset(HARD_ITEM_CODES) | frozenset(LEVEL_ITEM_CODES)

# Extra ItemData codes (name -> code) to append to ``data.ITEM_TABLE``.
APPENDED_ITEM_CODES = {**HARD_ITEM_CODES, **LEVEL_ITEM_CODES}


# ---- Where the checks that are not levels really are: read from the game's files on 2026-10-25 (docs/game-research.md, "Where the tapes,
# tokens and prizes are"). VERIFIED from game data and Blueprint code, not yet seen in game.

# LevelInfoTable "LevelToLoad": the map each gated row is played on.
LEVEL_MAPS: dict[int, str] = {
    **{row: "Flashlight_Game_Ver_1_Bigger" for row in (0, 1, 30, 31)},
    **{row: "Flashlight_Game_Ver_2" for row in (2, 36)},
    **{row: "Funtime_Foxy" for row in (3, 37)},
    **{row: "NightGuard_Office01" for row in (4, 5, 6, 7, 8)},
    **{row: "NightGuard_Office02" for row in (9, 10, 11, 12, 13, 40)},
    **{row: "NightGuard_Office03" for row in (14, 15, 16, 17, 18)},
    **{row: "Repair_Bonnie_Game" for row in (19, 32)},
    **{row: "Repair_Chica_Game" for row in (20, 33)},
    **{row: "Repair_Freddy_Game" for row in (21, 34)},
    **{row: "Repair_Foxy_Game" for row in (22, 35)},
    **{row: "Vent_Game_Mangle_1" for row in (23, 38)},
    **{row: "Vent_Game_Ennard_2" for row in (24, 39)},
    25: "NightTerror_FunTime_Freddy",
    26: "NightTerror_Nightmarionne",
    27: "NightTerror_CircusBaby",
    28: "NightTerror_Fredbear",
}
PIZZA_PARTY_MAP = "Finale_Ending"

# The map each tape / Faz Token pickup is placed in: the GlitchID / CoinID of the placed HiddenGlitchTrigger_02 / HiddenCoin actor
# ("Collect Glitch Tape NN" = GlitchID + 2 for GlitchIDs 0-2 and GlitchID + 1 from 4 on (no GlitchID 3), the intro tape is GlitchID 14; "Collect Faz Token NN" = CoinID). Only those two actors award tapes and coins.
# Tape 02 (GlitchID 0, the class default) is the one trigger without an id, in FNAF 3; coin 20 is spawned by Parts and Service Foxy (GrabbableFoxyHead).
# Some pickups show only on some nights or only in the nightmare version (the Ennard tape and coin 25 are destroyed outside it), so a pickup needs
# EVERY level played on its map: each one appears in at least one of them.
PICKUP_MAPS: dict[str, str] = {
    "Collect Glitch Tape 02": "NightGuard_Office03",
    "Collect Glitch Tape 03": "Flashlight_Game_Ver_2",
    "Collect Glitch Tape 04": "Funtime_Foxy",
    "Collect Glitch Tape 05": "Vent_Game_Ennard_2",
    "Collect Glitch Tape 06": "NightTerror_Fredbear",
    "Collect Glitch Tape 07": "NightGuard_Office01",
    "Collect Glitch Tape 10": "Repair_Chica_Game",
    "Collect Glitch Tape 11": "Repair_Foxy_Game",
    "Collect Glitch Tape 12": "Repair_Freddy_Game",
    "Collect Glitch Tape 13": "NightTerror_CircusBaby",
    "Collect Glitch Tape 14": PIZZA_PARTY_MAP,
    "Collect Glitch Tape 16": "Vent_Game_Mangle_1",
    **{f"Collect Faz Token {i:02d}": "NightGuard_Office01" for i in (1, 2, 3)},
    **{f"Collect Faz Token {i:02d}": "NightGuard_Office02" for i in (4, 5, 6)},
    **{f"Collect Faz Token {i:02d}": "NightGuard_Office03" for i in (7, 8, 9)},
    "Collect Faz Token 10": "Flashlight_Game_Ver_1_Bigger",
    **{f"Collect Faz Token {i:02d}": "Repair_Bonnie_Game" for i in (11, 12, 13)},
    **{f"Collect Faz Token {i:02d}": "Repair_Chica_Game" for i in (14, 15, 16)},
    **{f"Collect Faz Token {i:02d}": "Repair_Freddy_Game" for i in (17, 18)},
    **{f"Collect Faz Token {i:02d}": "Repair_Foxy_Game" for i in (19, 20)},
    **{f"Collect Faz Token {i:02d}": "NightTerror_CircusBaby" for i in (21, 22, 23)},
    "Collect Faz Token 24": "Vent_Game_Mangle_1",
    **{f"Collect Faz Token {i:02d}": "Vent_Game_Ennard_2" for i in (25, 26)},
    **{f"Collect Faz Token {i:02d}": PIZZA_PARTY_MAP for i in (27, 28)},
}

# Reachable with nothing (VERIFIED in game): the intro tape and the hub coin.
FREE_CHECKS = frozenset({"Collect Prize Counter Intro Tape", "Collect Faz Token 29"})

# Checks the game can send but whose condition is not known for sure: only filler may land there (the user's choice), and the logic only expects
# them once every level is open. Hub / gallery tapes and the gallery coin; Helpy Plush (the 25-coin milestone prize, never a random award);
# the Bobbleheads (prize category 6: only drawn in the DLC levels).
FILLER_ONLY_CHECKS = frozenset({
    "Collect Glitch Tape 08", "Collect Glitch Tape 09", "Collect Glitch Tape 15", "Collect Faz Token 30",
    "Prize - Plushie: Helpy Plush", "Prize - Other: Freddy Bobblehead", "Prize - Other: Chica Bobblehead", "Prize - Other: Bonnie Bobblehead",
})
# Every other prize: a level win draws a random prize not owned yet among those with CanBeAwardedFromAnyLevel, so any level the player can play
# hands them all out eventually (GetAvailablePrizesForLevel / GetRandomAvailablePrize).


def first_level(section_key: str) -> Level:
    """First level of a section = its normal level with the lowest LevelInfoTable row."""
    candidates = [lv for lv in LEVELS if lv.section == section_key and not lv.hard]
    return min(candidates, key=lambda lv: lv.row)


@dataclass(frozen=True)
class GatingPlan:
    unlock_mode: int
    hard_variants: int
    starting_section: str
    level_gates: dict[int, str]  # row -> gate id
    gate_items: dict[str, str]  # item NAME -> gate id
    location_items: dict[str, frozenset[str]]  # location -> item names ALL required: levels, Pizza Party, pickups, filler-only checks
    pool_items: tuple[str, ...]  # managed items to put in the pool (start items excluded)
    start_items: tuple[str, ...]  # managed items the player starts with
    any_level_items: frozenset[str] = frozenset()  # a prize needs ANY one of these (any level the player can win)


def build_plan(unlock_mode: int, hard_variants: int, starting_section: str) -> GatingPlan:
    if unlock_mode not in (UNLOCK_PER_SECTION, UNLOCK_PER_LEVEL):
        raise ValueError(f"Unknown unlock_mode {unlock_mode!r}")
    if hard_variants not in (HARD_GROUPED, HARD_SEPARATE):
        raise ValueError(f"Unknown hard_variants {hard_variants!r}")
    if starting_section not in SECTION_BY_KEY:
        raise ValueError(f"Unknown starting_section {starting_section!r}")

    per_level = unlock_mode == UNLOCK_PER_LEVEL
    separate = hard_variants == HARD_SEPARATE and not per_level  # hard_variants is a section-mode option

    level_gates: dict[int, str] = {}
    gate_items: dict[str, str] = {}
    direct: dict[int, str] = {}  # row -> item name that directly gates it

    if per_level:
        for level in LEVELS:
            level_gates[level.row] = level.gate
            gate_items[level.item] = level.gate
            direct[level.row] = level.item
        pool = [level.item for level in LEVELS]
        start = [first_level(starting_section).item]
    else:
        for section in SECTIONS:
            gate_items[section.item] = section.gate
            if separate and section.hard_item:
                gate_items[section.hard_item] = section.hard_gate
        for level in LEVELS:
            section = SECTION_BY_KEY[level.section]
            if level.hard and separate:
                level_gates[level.row] = section.hard_gate
                direct[level.row] = section.hard_item
            else:
                level_gates[level.row] = section.gate
                direct[level.row] = section.item
        pool = [section.item for section in SECTIONS]
        if separate:
            pool += [section.hard_item for section in SECTIONS if section.hard_item]
        start = [SECTION_BY_KEY[starting_section].item]

    # A level needs exactly its own gate item (no chain: the item alone unlocks it in game).
    location_items: dict[str, frozenset[str]] = {
        level.location: frozenset({direct[level.row]}) for level in LEVELS
    }

    # Pizza Party is never gated by the mod. The game opens it once every base level but Withered is beaten (IsLevelUnlocked, read from its
    # Blueprint code, not seen in game); requiring every level is at least as strict, so no item needed for a level can be placed on it.
    every_level = frozenset().union(*location_items.values())
    location_items[PIZZA_PARTY_LOCATION] = every_level

    map_items: dict[str, frozenset[str]] = {}
    for level in LEVELS:
        map_items[LEVEL_MAPS[level.row]] = map_items.get(LEVEL_MAPS[level.row], frozenset()) | {direct[level.row]}
    map_items[PIZZA_PARTY_MAP] = every_level
    for check, map_name in PICKUP_MAPS.items():
        location_items[check] = map_items[map_name]
    for check in FILLER_ONLY_CHECKS:
        location_items[check] = every_level

    pool_items = list(pool)
    for item in start:
        pool_items.remove(item)

    return GatingPlan(
        unlock_mode=unlock_mode,
        hard_variants=hard_variants,
        starting_section=starting_section,
        level_gates=level_gates,
        gate_items=gate_items,
        location_items=location_items,
        pool_items=tuple(pool_items),
        start_items=tuple(start),
        any_level_items=every_level,
    )


def slot_gate_data(plan: GatingPlan, item_name_to_id: dict[str, int]) -> dict[str, dict[str, str]]:
    """The two slot_data tables the client forwards to the game mod (JSON object keys are strings)."""
    return {
        "level_gates": {str(row): gate for row, gate in plan.level_gates.items()},
        "gate_items": {str(item_name_to_id[name]): gate for name, gate in plan.gate_items.items()},
    }
