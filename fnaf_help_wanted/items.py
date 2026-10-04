from BaseClasses import Item

from .data import GAME_NAME, ITEM_OFFSET, ITEM_TABLE, ItemData
from .levels import APPENDED_ITEM_CODES


class FNAFHWItem(Item):
    game = GAME_NAME


# ITEM_TABLE holds the original items (codes 1..13). The hard-section and per-level items are appended
# with higher codes (see levels.py); existing codes never change.
ALL_ITEM_TABLE: dict[str, ItemData] = {
    **ITEM_TABLE,
    **{name: ItemData(code, progression=True) for name, code in APPENDED_ITEM_CODES.items()},
}

item_name_to_id = {
    item_name: ITEM_OFFSET + item_data.code for item_name, item_data in ALL_ITEM_TABLE.items()
}
