from BaseClasses import Region

from .data import ACTIVE_REGION_LOCATIONS, REGION_CONNECTIONS
from .locations import FNAFHWLocation, location_name_to_id


def create_regions(world) -> None:
    multiworld = world.multiworld
    player = world.player

    for region_name in REGION_CONNECTIONS:
        region = Region(region_name, player, multiworld)
        for location_name in ACTIVE_REGION_LOCATIONS.get(region_name, []):
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
