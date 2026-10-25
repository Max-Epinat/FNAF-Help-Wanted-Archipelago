from BaseClasses import Region

from .data import REGION_CONNECTIONS, region_locations
from .locations import FNAFHWLocation, location_name_to_id
from .rules import get_goal_location_name


def create_regions(world) -> None:
    multiworld = world.multiworld
    player = world.player

    # a group that is not randomized has no locations, nor do the checks nothing sends and the unused goals (see data.region_locations); ids stay
    locations_by_region = region_locations(
        bool(world.options.randomize_prizes.value),
        bool(world.options.randomize_faz_tokens.value),
        bool(world.options.randomize_glitch_tapes.value),
        goal=get_goal_location_name(world.options.goal.value),
    )
    for region_name in REGION_CONNECTIONS:
        region = Region(region_name, player, multiworld)
        for location_name in locations_by_region.get(region_name, []):
            location = FNAFHWLocation(
                player,
                location_name,
                location_name_to_id[location_name],
                region,
            )
            region.locations.append(location)
        multiworld.regions.append(region)

    for source_name, target_names in REGION_CONNECTIONS.items():
        source_region = multiworld.get_region(source_name, player)
        for target_name in target_names:
            target_region = multiworld.get_region(target_name, player)
            source_region.connect(target_region, f"{source_name} -> {target_name}")
