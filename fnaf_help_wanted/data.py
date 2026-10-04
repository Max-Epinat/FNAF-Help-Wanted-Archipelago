from dataclasses import dataclass

GAME_NAME = "Five Nights at Freddy's: Help Wanted"

ITEM_OFFSET = 101000000
LOCATION_OFFSET = 101100000


@dataclass(frozen=True)
class ItemData:
    code: int
    quantity: int = 1
    progression: bool = False
    useful: bool = False
    trap: bool = False


@dataclass(frozen=True)
class LocationData:
    code: int


def _build_location_table(region_locations: dict[str, list[str]]) -> dict[str, LocationData]:
    location_table: dict[str, LocationData] = {}
    next_code = 1
    for location_names in region_locations.values():
        for location_name in location_names:
            location_table[location_name] = LocationData(next_code)
            next_code += 1
    return location_table


ITEM_TABLE = {
    "Glitch Tape": ItemData(1, quantity=16, progression=True),
    "FNAF 1 Access Pass": ItemData(2, progression=True),
    "FNAF 2 Access Pass": ItemData(3, progression=True),
    "FNAF 3 Access Pass": ItemData(4, progression=True),
    "Parts and Service Toolkit": ItemData(5, progression=True),
    "Vent Repair Toolkit": ItemData(6, progression=True),
    "Dark Rooms Flashlight": ItemData(7, progression=True),
    "Night Terrors Security Badge": ItemData(8, progression=True),
    "Prize Counter Key": ItemData(9, progression=True),
    "Nightmare Mode License": ItemData(10, useful=True),
    "Faz Token": ItemData(11, quantity=30),
    "Hallucination": ItemData(12, quantity=2, trap=True),
    "Victory": ItemData(13, quantity=0, progression=True),
}

PLUSHIE_PRIZES = [
    "Freddy Plush",
    "Bonnie Plush",
    "Chica Plush",
    "Foxy Plush",
    "Golden Freddy Plush",
    "Springtrap Plush",
    "Toy Freddy Plush",
    "Toy Bonnie Plush",
    "Toy Chica Plush",
    "Mangle Plush",
    "BB Plush",
    "JJ Plush",
    "Puppet Plush",
    "Plushtrap Plush",
    "Nightmare Freddy Plush",
    "Nightmare Bonnie Plush",
    "Nightmare Chica Plush",
    "Nightmare Fredbear Plush",
    "Nightmarionne Plush",
    "Helpy Plush",
    "Plushbaby",
    "Plushbaby (Scrap Baby ver.)",
    "Funtime Foxy",
    "Funtime Freddy",
]

ACTION_FIGURE_PRIZES = [
    "Freddy Action Figure",
    "Bonnie Action Figure",
    "Chica Action Figure",
    "Foxy Action Figure",
    "Golden Freddy Action Figure",
    "Springtrap Action Figure",
    "Toy Freddy Action Figure",
    "Toy Bonnie Action Figure",
    "Toy Chica Action Figure",
    "Mangle Action Figure",
    "Puppet Action Figure",
    "Circus Baby Action Figure",
    "Ballora Action Figure",
    "Funtime Freddy Action Figure",
    "Funtime Foxy Action Figure",
    "Ennard Action Figure",
    "Balloon Boy Action Figure",
    "Plushtrap Action Figure",
    "Nightmarionne Action Figure",
    "Nightmare Fredbear Action Figure",
    "Bon-Bon Action Figure",
]

OTHER_PRIZES = [
    "Exotic Butters",
    "Mr. Cupcake",
    "Pizza Slice",
    "Faz Soda",
    "Bon-Bon Hand Puppet",
    "Mini Music Box",
    "Candy Bucket",
    "Freddy Bobblehead",
    "Bonnie Bobblehead",
    "Chica Bobblehead",
    "Foxy Bobblehead",
    "Nightmarionne Bobblehead",
    "Mystery Box",
    "Prize Counter Poster",
]

FOOD_DRINK_PRIZES = [
    "Disappointment Chips",
    "El Chip's Tortilla Chips Bold and Spicy",
    "Meat Bites XL",
    "Bonnie Bites",
    "Allergy Friendly Mixed Nuts",
    "Meat Bites",
    "Stick of Butter",
    "Pirate Plunderbar",
    "Foxy Cove Cooler",
    "Butter for One",
    "Freddy Fudgebar",
    "Exotic Beverage",
    "Sodaroni",
    "Chica Chug",
    "El Chip's Tortilla Chips",
    "Fazbar",
    "Lemon Chica Bar",
    "Slice of Cake",
]

TOY_PRIZES = [
    "Cupcake",
    "Toy phone",
    "Toy Catterpillar",
    "Toy Robot",
]

PRIZE_CHECKS = (
    [f"Prize - Plushie: {name}" for name in PLUSHIE_PRIZES]
    + [f"Prize - Action Figure: {name}" for name in ACTION_FIGURE_PRIZES]
    + [f"Prize - Other: {name}" for name in OTHER_PRIZES]
    + [f"Prize - Food/Drink: {name}" for name in FOOD_DRINK_PRIZES]
    + [f"Prize - Toy: {name}" for name in TOY_PRIZES]
)

FAZ_TOKEN_CHECKS = [f"Collect Faz Token {index:02d}" for index in range(1, 31)]

GLITCH_TAPE_CHECKS = [
    "Collect Prize Counter Intro Tape",
    *[f"Collect Glitch Tape {index:02d}" for index in range(2, 17)],
]

MINIGAME_AND_NIGHT_CHECKS = [
    # --- Normal mode ---
    "Beat FNAF 1 - Night 1",
    "Beat FNAF 1 - Night 2",
    "Beat FNAF 1 - Night 3",
    "Beat FNAF 1 - Night 4",
    "Beat FNAF 2 - Night 1",
    "Beat FNAF 2 - Night 2",
    "Beat FNAF 2 - Night 3",
    "Beat FNAF 2 - Night 4",
    "Beat FNAF 3 - Night 1",
    "Beat FNAF 3 - Night 2",
    "Beat FNAF 3 - Night 3",
    "Beat FNAF 3 - Night 4",
    "Complete Parts and Service - Bonnie",
    "Complete Parts and Service - Chica",
    "Complete Parts and Service - Freddy",
    "Complete Parts and Service - Foxy",
    "Complete Vent Repair - Mangle",
    "Complete Vent Repair - Ennard",
    "Complete Dark Rooms - Plushtrap",
    "Complete Dark Rooms - Plushbaby",
    "Complete Dark Rooms - Nightmare BB",
    "Complete Dark Rooms - Funtime Foxy",
    "Complete Night Terrors - Circus Baby",
    "Complete Night Terrors - Funtime Freddy",
    "Complete Night Terrors - Nightmare Fredbear",
    "Complete Night Terrors - Nightmarionne",
    # --- Hard mode (separate completions in-game) ---
    "Beat FNAF 1 - Night 5 (Hard)",
    "Beat FNAF 2 - Night 5 (Hard)",
    "Beat FNAF 2 - Withered",
    "Beat FNAF 3 - Night 5 (Hard)",
    "Complete Dark Rooms (Hard) - Plushtrap",
    "Complete Dark Rooms (Hard) - Nightmare BB",
    "Complete Dark Rooms (Hard) - Plushbaby",
    "Complete Dark Rooms (Hard) - Funtime Foxy",
    "Complete Parts and Service (Hard) - Bonnie",
    "Complete Parts and Service (Hard) - Chica",
    "Complete Parts and Service (Hard) - Freddy",
    "Complete Parts and Service (Hard) - Foxy",
    "Complete Vent Repair (Hard) - Mangle",
    "Complete Vent Repair (Hard) - Ennard",
]

FULL_CLEAR_CHECKS = [
    *MINIGAME_AND_NIGHT_CHECKS,
    "Collect All Hub Trophies",
    *GLITCH_TAPE_CHECKS,
    "Win Prize Counter Blackjack",
    "Complete Pizza Party",
    "Complete Normal Ending",
    *PRIZE_CHECKS,
    *FAZ_TOKEN_CHECKS,
]

GOAL_COMPLETE_ALL_MINIGAMES = "Goal - Complete All Minigames and Nights"
GOAL_COMPLETE_ALL_MINIGAMES_HARD = "Goal - Complete All Minigames and Nights (Hard Mode)"
GOAL_GLITCHTRAP_DIE = "Goal - Glitchtrap Ending (You Die)"
GOAL_GLITCHTRAP_SURVIVE = "Goal - Glitchtrap Ending (You Do Not Die)"
GOAL_HUNDRED_PERCENT = "Goal - 100 Percent"
GOAL_TOKEN_TAPE_QUOTA = "Goal - Faz Token and Tape Quota"

REGION_LOCATIONS = {
    "Menu": [],
    "Hub": [
        "Collect All Hub Trophies",
        "Complete Pizza Party",
        "Complete Normal Ending",
        GOAL_COMPLETE_ALL_MINIGAMES,
        GOAL_COMPLETE_ALL_MINIGAMES_HARD,
        GOAL_GLITCHTRAP_DIE,
        GOAL_GLITCHTRAP_SURVIVE,
        GOAL_HUNDRED_PERCENT,
        GOAL_TOKEN_TAPE_QUOTA,
    ],
    "Prize Counter": [*GLITCH_TAPE_CHECKS, "Win Prize Counter Blackjack", *PRIZE_CHECKS],
    "Faz Tokens": [*FAZ_TOKEN_CHECKS],
    "FNAF 1": [
        "Beat FNAF 1 - Night 1",
        "Beat FNAF 1 - Night 2",
        "Beat FNAF 1 - Night 3",
        "Beat FNAF 1 - Night 4",
    ],
    "FNAF 1 - Hard": [
        "Beat FNAF 1 - Night 5 (Hard)",
    ],
    "FNAF 2": [
        "Beat FNAF 2 - Night 1",
        "Beat FNAF 2 - Night 2",
        "Beat FNAF 2 - Night 3",
        "Beat FNAF 2 - Night 4",
    ],
    "FNAF 2 - Hard": [
        "Beat FNAF 2 - Night 5 (Hard)",
        "Beat FNAF 2 - Withered",
    ],
    "FNAF 3": [
        "Beat FNAF 3 - Night 1",
        "Beat FNAF 3 - Night 2",
        "Beat FNAF 3 - Night 3",
        "Beat FNAF 3 - Night 4",
    ],
    "FNAF 3 - Hard": [
        "Beat FNAF 3 - Night 5 (Hard)",
    ],
    "Parts and Service": [
        "Complete Parts and Service - Bonnie",
        "Complete Parts and Service - Chica",
        "Complete Parts and Service - Freddy",
        "Complete Parts and Service - Foxy",
    ],
    "Parts and Service - Hard": [
        "Complete Parts and Service (Hard) - Bonnie",
        "Complete Parts and Service (Hard) - Chica",
        "Complete Parts and Service (Hard) - Freddy",
        "Complete Parts and Service (Hard) - Foxy",
    ],
    "Vent Repair": [
        "Complete Vent Repair - Mangle",
        "Complete Vent Repair - Ennard",
    ],
    "Vent Repair - Hard": [
        "Complete Vent Repair (Hard) - Mangle",
        "Complete Vent Repair (Hard) - Ennard",
    ],
    "Dark Rooms": [
        "Complete Dark Rooms - Plushtrap",
        "Complete Dark Rooms - Plushbaby",
        "Complete Dark Rooms - Nightmare BB",
        "Complete Dark Rooms - Funtime Foxy",
    ],
    "Dark Rooms - Hard": [
        "Complete Dark Rooms (Hard) - Plushtrap",
        "Complete Dark Rooms (Hard) - Nightmare BB",
        "Complete Dark Rooms (Hard) - Plushbaby",
        "Complete Dark Rooms (Hard) - Funtime Foxy",
    ],
    "Night Terrors": [
        "Complete Night Terrors - Circus Baby",
        "Complete Night Terrors - Funtime Freddy",
        "Complete Night Terrors - Nightmare Fredbear",
        "Complete Night Terrors - Nightmarionne",
    ],
}

LOCATION_TABLE = _build_location_table(REGION_LOCATIONS)

REGION_CONNECTIONS = {
    "Menu": ["Hub"],
    "Hub": [
        "Prize Counter",
        "Faz Tokens",
        "FNAF 1",
        "FNAF 1 - Hard",
        "FNAF 2",
        "FNAF 2 - Hard",
        "FNAF 3",
        "FNAF 3 - Hard",
        "Parts and Service",
        "Parts and Service - Hard",
        "Vent Repair",
        "Vent Repair - Hard",
        "Dark Rooms",
        "Dark Rooms - Hard",
        "Night Terrors",
    ],
    "Prize Counter": [],
    "Faz Tokens": [],
    "FNAF 1": [],
    "FNAF 1 - Hard": [],
    "FNAF 2": [],
    "FNAF 2 - Hard": [],
    "FNAF 3": [],
    "FNAF 3 - Hard": [],
    "Parts and Service": [],
    "Parts and Service - Hard": [],
    "Vent Repair": [],
    "Vent Repair - Hard": [],
    "Dark Rooms": [],
    "Dark Rooms - Hard": [],
    "Night Terrors": [],
}
