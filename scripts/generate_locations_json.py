import json
import importlib.util
from pathlib import Path

# Load data.py from fnaf_help_wanted
spec = importlib.util.spec_from_file_location('data', 'fnaf_help_wanted/data.py')
data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(data)

table = data._build_location_table(data.REGION_LOCATIONS)
location_name_to_id = {k: data.LOCATION_OFFSET + v.code for k, v in table.items()}

# Exact mapping of LevelInfoTable rows to AP Minigame Locations (extracted from LevelInfoTable.uexp)
MINIGAME_ROW_MAP = {
    # Dark Rooms Normal (Map: Flashlight_Game_Ver_1_Bigger, Flashlight_Game_Ver_2, Funtime_Foxy)
    0:  {"name": "Complete Dark Rooms - Plushtrap", "category": "Dark Rooms", "hard": False, "map": "Flashlight_Game_Ver_1_Bigger"},
    1:  {"name": "Complete Dark Rooms - Nightmare BB", "category": "Dark Rooms", "hard": False, "map": "Flashlight_Game_Ver_1_Bigger"},
    2:  {"name": "Complete Dark Rooms - Plushbaby", "category": "Dark Rooms", "hard": False, "map": "Flashlight_Game_Ver_2"},
    3:  {"name": "Complete Dark Rooms - Funtime Foxy", "category": "Dark Rooms", "hard": False, "map": "Funtime_Foxy"},

    # FNAF 1 (Map: NightGuard_Office01)
    4:  {"name": "Beat FNAF 1 - Night 1", "category": "FNAF 1", "hard": False, "map": "NightGuard_Office01"},
    5:  {"name": "Beat FNAF 1 - Night 2", "category": "FNAF 1", "hard": False, "map": "NightGuard_Office01"},
    6:  {"name": "Beat FNAF 1 - Night 3", "category": "FNAF 1", "hard": False, "map": "NightGuard_Office01"},
    7:  {"name": "Beat FNAF 1 - Night 4", "category": "FNAF 1", "hard": False, "map": "NightGuard_Office01"},
    8:  {"name": "Beat FNAF 1 - Night 5 (Hard)", "category": "FNAF 1", "hard": True, "map": "NightGuard_Office01"},

    # FNAF 2 (Map: NightGuard_Office02)
    9:  {"name": "Beat FNAF 2 - Night 1", "category": "FNAF 2", "hard": False, "map": "NightGuard_Office02"},
    10: {"name": "Beat FNAF 2 - Night 2", "category": "FNAF 2", "hard": False, "map": "NightGuard_Office02"},
    11: {"name": "Beat FNAF 2 - Night 3", "category": "FNAF 2", "hard": False, "map": "NightGuard_Office02"},
    12: {"name": "Beat FNAF 2 - Night 4", "category": "FNAF 2", "hard": False, "map": "NightGuard_Office02"},
    13: {"name": "Beat FNAF 2 - Night 5 (Hard)", "category": "FNAF 2", "hard": True, "map": "NightGuard_Office02"},

    # FNAF 3 (Map: NightGuard_Office03)
    14: {"name": "Beat FNAF 3 - Night 1", "category": "FNAF 3", "hard": False, "map": "NightGuard_Office03"},
    15: {"name": "Beat FNAF 3 - Night 2", "category": "FNAF 3", "hard": False, "map": "NightGuard_Office03"},
    16: {"name": "Beat FNAF 3 - Night 3", "category": "FNAF 3", "hard": False, "map": "NightGuard_Office03"},
    17: {"name": "Beat FNAF 3 - Night 4", "category": "FNAF 3", "hard": False, "map": "NightGuard_Office03"},
    18: {"name": "Beat FNAF 3 - Night 5 (Hard)", "category": "FNAF 3", "hard": True, "map": "NightGuard_Office03"},

    # Parts and Service Normal (Map: Repair_*_Game)
    19: {"name": "Complete Parts and Service - Bonnie", "category": "Parts and Service", "hard": False, "map": "Repair_Bonnie_Game"},
    20: {"name": "Complete Parts and Service - Chica", "category": "Parts and Service", "hard": False, "map": "Repair_Chica_Game"},
    21: {"name": "Complete Parts and Service - Freddy", "category": "Parts and Service", "hard": False, "map": "Repair_Freddy_Game"},
    22: {"name": "Complete Parts and Service - Foxy", "category": "Parts and Service", "hard": False, "map": "Repair_Foxy_Game"},

    # Vent Repair Normal (Map: Vent_Game_*)
    23: {"name": "Complete Vent Repair - Mangle", "category": "Vent Repair", "hard": False, "map": "Vent_Game_Mangle_1"},
    24: {"name": "Complete Vent Repair - Ennard", "category": "Vent Repair", "hard": False, "map": "Vent_Game_Ennard_2"},

    # Night Terrors (Map: NightTerror_*)
    25: {"name": "Complete Night Terrors - Funtime Freddy", "category": "Night Terrors", "hard": False, "map": "NightTerror_FunTime_Freddy"},
    26: {"name": "Complete Night Terrors - Nightmarionne", "category": "Night Terrors", "hard": False, "map": "NightTerror_Nightmarionne"},
    27: {"name": "Complete Night Terrors - Circus Baby", "category": "Night Terrors", "hard": False, "map": "NightTerror_CircusBaby"},
    28: {"name": "Complete Night Terrors - Nightmare Fredbear", "category": "Night Terrors", "hard": False, "map": "NightTerror_Fredbear"},

    # Finale (Map: Finale_Ending)
    29: {"name": "Complete Pizza Party", "category": "Finale", "hard": True, "map": "Finale_Ending"},

    # Dark Rooms Hard (Map: Flashlight_Game_Ver_1_Bigger)
    30: {"name": "Complete Dark Rooms (Hard) - Plushtrap", "category": "Dark Rooms", "hard": True, "map": "Flashlight_Game_Ver_1_Bigger"},
    31: {"name": "Complete Dark Rooms (Hard) - Nightmare BB", "category": "Dark Rooms", "hard": True, "map": "Flashlight_Game_Ver_1_Bigger"},

    # Parts and Service Hard (Map: Repair_*_Game)
    32: {"name": "Complete Parts and Service (Hard) - Bonnie", "category": "Parts and Service", "hard": True, "map": "Repair_Bonnie_Game"},
    33: {"name": "Complete Parts and Service (Hard) - Chica", "category": "Parts and Service", "hard": True, "map": "Repair_Chica_Game"},
    34: {"name": "Complete Parts and Service (Hard) - Freddy", "category": "Parts and Service", "hard": True, "map": "Repair_Freddy_Game"},
    35: {"name": "Complete Parts and Service (Hard) - Foxy", "category": "Parts and Service", "hard": True, "map": "Repair_Foxy_Game"},

    # Dark Rooms Hard (Cont.)
    36: {"name": "Complete Dark Rooms (Hard) - Plushbaby", "category": "Dark Rooms", "hard": True, "map": "Flashlight_Game_Ver_2"},
    37: {"name": "Complete Dark Rooms (Hard) - Funtime Foxy", "category": "Dark Rooms", "hard": True, "map": "Funtime_Foxy"},

    # Vent Repair Hard
    38: {"name": "Complete Vent Repair (Hard) - Mangle", "category": "Vent Repair", "hard": True, "map": "Vent_Game_Mangle_1"},
    39: {"name": "Complete Vent Repair (Hard) - Ennard", "category": "Vent Repair", "hard": True, "map": "Vent_Game_Ennard_2"},

    # FNAF 2 Hard (Withered)
    40: {"name": "Beat FNAF 2 - Withered", "category": "FNAF 2", "hard": True, "map": "NightGuard_Office02"},
}

minigame_entries = []
for row_id, info in sorted(MINIGAME_ROW_MAP.items(), key=lambda x: x[0]):
    loc_name = info["name"]
    loc_id = location_name_to_id.get(loc_name)
    if loc_id is None:
        raise ValueError(f"Missing location name in data.py: {loc_name}")
    minigame_entries.append({
        "row_id": row_id,
        "location_id": loc_id,
        "location_name": loc_name,
        "category": info["category"],
        "hard_mode": info["hard"],
        "map_name": info["map"],
        "primary_hook": "/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:SaveLevelVictory",
        "secondary_hook": "/Game/ProductionAssets/Blueprints/BackEnd/BP_FNAFGameState.BP_FNAFGameState_C:victory",
    })

token_entries = []
for i in range(1, 31):
    loc_name = f"Collect Faz Token {i:02d}"
    loc_id = location_name_to_id[loc_name]
    token_entries.append({
        "token_number": i,
        "location_id": loc_id,
        "location_name": loc_name,
        "primary_hook": "/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:UnlockCoin",
        "actor_hook": "/Script/Engine.Actor:K2_DestroyActor",
        "actor_classes": ["GrabbableToken_C", "GrabbableToken_InitiallyFrozen_C", "HiddenCoin_C"],
    })

tape_entries = []
tape_names = ["Collect Prize Counter Intro Tape"] + [f"Collect Glitch Tape {i:02d}" for i in range(2, 17)]
for i, loc_name in enumerate(tape_names, start=1):
    loc_id = location_name_to_id[loc_name]
    tape_entries.append({
        "tape_number": i,
        "location_id": loc_id,
        "location_name": loc_name,
        "primary_hook": "/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:SetGlitchListenedTo",
        "fallback_hook": "/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:AwardGlitch",
    })

prize_entries = []
for loc_name in data.PRIZE_CHECKS:
    loc_id = location_name_to_id[loc_name]
    prize_entries.append({
        "location_id": loc_id,
        "location_name": loc_name,
        "primary_hook": "/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:AwardRandomPrize",
        "special_hook": "/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:AttemptAwardSpecialPrize",
    })

hub_entries = []
for loc_name in data.REGION_LOCATIONS["Hub"]:
    loc_id = location_name_to_id[loc_name]
    hub_entries.append({
        "location_id": loc_id,
        "location_name": loc_name,
    })

export_data = {
    "version": "2.0.0",
    "game": data.GAME_NAME,
    "location_offset": data.LOCATION_OFFSET,
    "item_offset": data.ITEM_OFFSET,
    "total_locations": len(location_name_to_id),
    "minigames": minigame_entries,
    "tokens": token_entries,
    "tapes": tape_entries,
    "prizes": prize_entries,
    "hub_goals": hub_entries,
    "row_id_to_location": {str(e["row_id"]): {"id": e["location_id"], "name": e["location_name"]} for e in minigame_entries},
    "location_name_to_id": location_name_to_id,
    "location_id_to_name": {str(v): k for k, v in location_name_to_id.items()},
}

out_path_mod = Path("ue4ss_mod/FNAFHWArchipelago/locations.json")
out_path_mod.write_text(json.dumps(export_data, indent=2), encoding="utf-8")
print(f"Generated {out_path_mod} with {len(location_name_to_id)} mapped locations!")
