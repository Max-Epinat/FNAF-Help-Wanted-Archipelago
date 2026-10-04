from BaseClasses import Location

from .data import GAME_NAME, LOCATION_OFFSET, LOCATION_TABLE


class FNAFHWLocation(Location):
    game = GAME_NAME


location_name_to_id = {
    location_name: LOCATION_OFFSET + location_data.code
    for location_name, location_data in LOCATION_TABLE.items()
}
