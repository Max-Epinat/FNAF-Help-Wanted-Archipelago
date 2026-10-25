from BaseClasses import Item

from .data import EXTRA_ITEM_CODES, GAME_NAME, ITEM_OFFSET, ITEM_TABLE, ItemData
from .levels import APPENDED_ITEM_CODES


class FNAFHWItem(Item):
    game = GAME_NAME


# ITEM_TABLE holds the original items (codes 2..13) and the 16 tape items (61-76). The hard-section and per-level items are appended
# with codes 14..59 (see levels.py), the fillers after them; existing codes never change and retired ones (data.RETIRED_ITEM_CODES) are never reused.
ALL_ITEM_TABLE: dict[str, ItemData] = {
    **ITEM_TABLE,
    **{name: ItemData(code, progression=True) for name, code in APPENDED_ITEM_CODES.items()},
    **{name: ItemData(code) for name, code in EXTRA_ITEM_CODES.items()},  # fillers: not progression, no quantity
}

item_name_to_id = {
    item_name: ITEM_OFFSET + item_data.code for item_name, item_data in ALL_ITEM_TABLE.items()
}
