return {
    default_auto_map_checks = {
        {
            location_names = {
                "Beat FNAF 1 - Night 1",
                "Beat FNAF 1 - Night 2",
                "Beat FNAF 1 - Night 3",
                "Beat FNAF 1 - Night 4",
                "Beat FNAF 1 - Night 5 (Hard)",
            },
            keywords = { "nightguard_office01" },
        },
        {
            -- FNAF 2 Withered also uses nightguard_office02 (confirmed) - add after Night 5 Hard
            location_names = {
                "Beat FNAF 2 - Night 1",
                "Beat FNAF 2 - Night 2",
                "Beat FNAF 2 - Night 3",
                "Beat FNAF 2 - Night 4",
                "Beat FNAF 2 - Night 5 (Hard)",
                "Beat FNAF 2 - Withered",
            },
            keywords = { "nightguard_office02" },
        },
        {
            -- FNAF 3 Nights 1-4: actual gameplay map is NormalLighting (NightGuard_Office03 exits in 0s)
            location_names = {
                "Beat FNAF 3 - Night 1",
                "Beat FNAF 3 - Night 2",
                "Beat FNAF 3 - Night 3",
                "Beat FNAF 3 - Night 4",
            },
            keywords = { "normallighting" },
        },
        {
            -- FNAF 3 Night 5 Hard: uses NightmareLighting sublevel (confirmed)
            location_names = { "Beat FNAF 3 - Night 5 (Hard)" },
            keywords = { "nightmarelighting" },
        },
        -- Dead flat entries removed (keywords like {"fnaf","1","night","1"} never match a UE4 map name).
        -- FNAF 1 Nights 1-5 (Hard) handled by grouped entry above (nightguard_office01).
        -- FNAF 2 Nights 1-5 (Hard) handled by grouped entry above (nightguard_office02).
        -- FNAF 3 Nights 1-4 handled by grouped entry above (normallighting).
        -- FNAF 3 Night 5 Hard handled by grouped entry above (nightmarelighting).
        -- P&S: merge normal + hard into sequential groups (same maps, one check per clear):
        { location_names = { "Complete Parts and Service - Bonnie",  "Complete Parts and Service (Hard) - Bonnie" },  keywords = { "repair", "bonnie" } },
        { location_names = { "Complete Parts and Service - Chica",   "Complete Parts and Service (Hard) - Chica" },   keywords = { "repair", "chica" } },
        { location_names = { "Complete Parts and Service - Freddy",  "Complete Parts and Service (Hard) - Freddy" },  keywords = { "repair", "freddy" } },
        { location_names = { "Complete Parts and Service - Foxy",    "Complete Parts and Service (Hard) - Foxy" },    keywords = { "repair", "foxy" } },
        -- Confirmed real map names from UE4SS log telemetry (2026-04-05):
        -- Vent Repair: merge normal + hard into sequential groups:
        { location_names = { "Complete Vent Repair - Mangle", "Complete Vent Repair (Hard) - Mangle" }, keywords = { "vent_game_mangle" } },
        { location_names = { "Complete Vent Repair - Ennard", "Complete Vent Repair (Hard) - Ennard" }, keywords = { "vent_game_ennard" } },
        -- Dark Rooms: Plushtrap + Nightmare BB share Flashlight_Game_Ver_1_Bigger - sequential (4 clears total):
        { location_names = { "Complete Dark Rooms - Plushtrap", "Complete Dark Rooms - Nightmare BB", "Complete Dark Rooms (Hard) - Plushtrap", "Complete Dark Rooms (Hard) - Nightmare BB" }, keywords = { "flashlight_game_ver_1_bigger" } },
        -- Plushbaby: merge normal + hard:
        { location_names = { "Complete Dark Rooms - Plushbaby", "Complete Dark Rooms (Hard) - Plushbaby" }, keywords = { "flashlight_game_ver_2" } },
        -- Funtime Foxy: merge normal + hard:
        { location_names = { "Complete Dark Rooms - Funtime Foxy", "Complete Dark Rooms (Hard) - Funtime Foxy" }, keywords = { "funtimefoxyvr" } },
        { location_name = "Complete Night Terrors - Circus Baby", keywords = { "nightterror_circusbaby" } },
        { location_name = "Complete Night Terrors - Funtime Freddy", keywords = { "nightterror_funtime_freddy" } },
        { location_name = "Complete Night Terrors - Nightmare Fredbear", keywords = { "nightterror_fredbear" } },
        { location_name = "Complete Night Terrors - Nightmarionne", keywords = { "nightmarionne" } },
    },

    default_auto_token_awards = {
        { keywords = { "nightguard_office01" }, count = 2 },
    },

    default_auto_tape_checks = {
        { location_name = "Collect Prize Counter Intro Tape", keywords = { "introarcadeset" } },
    },

    default_completion_min_seconds_by_map = {
        { keywords = { "nightguard_office01" }, min_seconds = 15 },
        { keywords = { "nightguard_office02" }, min_seconds = 15 },
        { keywords = { "nightguard_office03" }, min_seconds = 15 },
    },

    default_fallback_collectible_excluded_keywords = {
        "introarcadeset",
    },

    default_fallback_tape_allowed_keywords = {
        "nightguard_office",
    },

    default_collectible_pickup_hook_paths = {
        "/Script/Engine.Actor:K2_DestroyActor",
    },

    default_collectible_coin_actor_keywords = {
        "grabbabletoken",
    },

    default_collectible_tape_actor_keywords = {
        "hiddenglitchtrigger",
        "tape",
        "cassette",
    },

    default_collectible_prize_actor_keywords = {
        "prize_",
        "BP_PrizeJack",
        "ExoticButter",
        "prizebox",
        "giftbox",
        "rewardbox",
        "mysterybox",
    },

    default_collectible_debug_map_keywords = {
        "level_victory",
        "prizecounter",
        "prize_counter",
    },

    default_collectible_prize_actor_mappings = {},

    default_collectible_prize_allowed_map_keywords = {
        "level_victory",
        "prizecounter",
        "prize_counter",
    },

    default_collectible_tape_actor_mappings = {
        {
            location_name = "Collect Prize Counter Intro Tape",
            actor_keywords = { "hiddenglitchtrigger" },
            map_keywords = { "introarcadeset" },
        },
        { location_name = "Collect Glitch Tape 02", actor_keywords = { "hiddenglitchtrigger_02" } },
        { location_name = "Collect Glitch Tape 03", actor_keywords = { "hiddenglitchtrigger_03" } },
        { location_name = "Collect Glitch Tape 04", actor_keywords = { "hiddenglitchtrigger_04" } },
        { location_name = "Collect Glitch Tape 05", actor_keywords = { "hiddenglitchtrigger_05" } },
        { location_name = "Collect Glitch Tape 06", actor_keywords = { "hiddenglitchtrigger_06" } },
        { location_name = "Collect Glitch Tape 07", actor_keywords = { "hiddenglitchtrigger_07" } },
        { location_name = "Collect Glitch Tape 08", actor_keywords = { "hiddenglitchtrigger_08" } },
        { location_name = "Collect Glitch Tape 09", actor_keywords = { "hiddenglitchtrigger_09" } },
        { location_name = "Collect Glitch Tape 10", actor_keywords = { "hiddenglitchtrigger_10" } },
        { location_name = "Collect Glitch Tape 11", actor_keywords = { "hiddenglitchtrigger_11" } },
        { location_name = "Collect Glitch Tape 12", actor_keywords = { "hiddenglitchtrigger_12" } },
        { location_name = "Collect Glitch Tape 13", actor_keywords = { "hiddenglitchtrigger_13" } },
        { location_name = "Collect Glitch Tape 14", actor_keywords = { "hiddenglitchtrigger_14" } },
        { location_name = "Collect Glitch Tape 15", actor_keywords = { "hiddenglitchtrigger_15" } },
        { location_name = "Collect Glitch Tape 16", actor_keywords = { "hiddenglitchtrigger_16" } },
    },

    default_collectible_actor_excluded_keywords = {
        "glitchtrapsetup",
    },

    default_collectible_hub_allowed_map_keywords = {
        "main_menu_with_showtime",
        "prizecounter",
        "prize_counter",
        "titlemain",
    },

    default_collectible_hub_allowed_actor_keywords = {
        "main_menu_with_showtime",
        "prizecounter",
        "prize_counter",
        "introarcadeset",
        "titlemain",
    },

    default_collectible_actor_name_dedupe_seconds = 20,

    token_location_names = {
        "Collect Faz Token 01",
        "Collect Faz Token 02",
        "Collect Faz Token 03",
        "Collect Faz Token 04",
        "Collect Faz Token 05",
        "Collect Faz Token 06",
        "Collect Faz Token 07",
        "Collect Faz Token 08",
        "Collect Faz Token 09",
        "Collect Faz Token 10",
        "Collect Faz Token 11",
        "Collect Faz Token 12",
        "Collect Faz Token 13",
        "Collect Faz Token 14",
        "Collect Faz Token 15",
        "Collect Faz Token 16",
        "Collect Faz Token 17",
        "Collect Faz Token 18",
        "Collect Faz Token 19",
        "Collect Faz Token 20",
        "Collect Faz Token 21",
        "Collect Faz Token 22",
        "Collect Faz Token 23",
        "Collect Faz Token 24",
        "Collect Faz Token 25",
        "Collect Faz Token 26",
        "Collect Faz Token 27",
        "Collect Faz Token 28",
        "Collect Faz Token 29",
        "Collect Faz Token 30",
    },

    tape_location_names = {
        "Collect Prize Counter Intro Tape",
        "Collect Glitch Tape 02",
        "Collect Glitch Tape 03",
        "Collect Glitch Tape 04",
        "Collect Glitch Tape 05",
        "Collect Glitch Tape 06",
        "Collect Glitch Tape 07",
        "Collect Glitch Tape 08",
        "Collect Glitch Tape 09",
        "Collect Glitch Tape 10",
        "Collect Glitch Tape 11",
        "Collect Glitch Tape 12",
        "Collect Glitch Tape 13",
        "Collect Glitch Tape 14",
        "Collect Glitch Tape 15",
        "Collect Glitch Tape 16",
    },
}
