from dataclasses import dataclass

from Options import Choice, DeathLink, PerGameCommonOptions, Range


class Goal(Choice):
    """What counts as game completion for this world."""

    display_name = "Goal"
    option_complete_all_minigames_nights = 0
    option_complete_all_minigames_nights_hard_mode = 1
    option_glitchtrap_ending_die = 2
    option_glitchtrap_ending_survive = 3
    option_hundred_percent = 4
    option_token_tape_quota = 5
    default = 0


class RequiredTapes(Range):
    """How many glitch tapes are required before the ending check is valid."""

    display_name = "Required Glitch Tapes"
    range_start = 0
    range_end = 16
    default = 8


class RequiredFazTokens(Range):
    """How many Faz Tokens are required for quota-based completion goals."""

    display_name = "Required Faz Tokens"
    range_start = 0
    range_end = 30
    default = 15


class UnlockMode(Choice):
    """How levels are unlocked by Archipelago items.

    per_section: one item unlocks a whole section (FNAF 1, FNAF 2, FNAF 3, Parts and Service, Vent Repair,
    Dark Rooms, Night Terrors).
    per_level: every level has its own item (every hard level too).
    In both modes the item alone unlocks the level in game, even when the game's usual order would not allow it yet
    (for example FNAF 1 Night 3 without having beaten Night 1 and 2). Pizza Party is never locked by Archipelago:
    the game decides when it can be played, and the logic expects every level to be cleared first.
    """

    display_name = "Unlock Mode"
    option_per_section = 0
    option_per_level = 1
    default = 0


class HardVariants(Choice):
    """Section mode only: how hard (Night 5 / Nightmare) variants are unlocked.

    grouped: the section's item also unlocks its hard variants.
    separate: hard variants need their own item per section.
    Ignored in per_level mode, where every hard level always has its own item.
    """

    display_name = "Hard Variants"
    option_grouped = 0
    option_separate = 1
    default = 0


class StartingSection(Choice):
    """Which section you start in.

    per_section: you start with that section's item.
    per_level: you start with only that section's first level.
    """

    display_name = "Starting Section"
    option_fnaf_1 = 0
    option_fnaf_2 = 1
    option_fnaf_3 = 2
    option_parts_and_service = 3
    option_vent_repair = 4
    option_dark_rooms = 5
    option_night_terrors = 6
    default = 0


@dataclass
class FNAFHWOptions(PerGameCommonOptions):
    goal: Goal
    required_tapes: RequiredTapes
    required_faz_tokens: RequiredFazTokens
    death_link: DeathLink
    unlock_mode: UnlockMode
    hard_variants: HardVariants
    starting_section: StartingSection
