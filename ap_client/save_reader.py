import re
import struct
import os
from pathlib import Path
from typing import Any

# The save slot (= file name without .sav) of the Archipelago save. One file per multiworld is named by the client (`Playerarchi_<seed>_<slot>`);
# `Playerarchi` is the shared file of every version before that, still used by the sessions made then.
DEFAULT_SAVE_SLOT = "Playerarchi"
SAVE_SLOT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,150}$")


def _slot_name(slot_name: str | None) -> str:
    """The slot name to use, checked: it becomes a file name, so nothing that could leave the save folder is accepted."""
    if slot_name is None:
        return DEFAULT_SAVE_SLOT
    if not SAVE_SLOT_PATTERN.match(slot_name):
        raise ValueError(f"unsafe save slot name {slot_name!r}")
    return slot_name

# Canonical mapping for LevelInfo row IDs to minigame location names
# Extracted from FNAF Help Wanted LevelInfoTable.uexp
DEFAULT_ROW_MAP: dict[int, str] = {
    # Dark Rooms Normal
    0:  "Complete Dark Rooms - Plushtrap",
    1:  "Complete Dark Rooms - Nightmare BB",
    2:  "Complete Dark Rooms - Plushbaby",
    3:  "Complete Dark Rooms - Funtime Foxy",

    # FNAF 1
    4:  "Beat FNAF 1 - Night 1",
    5:  "Beat FNAF 1 - Night 2",
    6:  "Beat FNAF 1 - Night 3",
    7:  "Beat FNAF 1 - Night 4",
    8:  "Beat FNAF 1 - Night 5 (Hard)",

    # FNAF 2
    9:  "Beat FNAF 2 - Night 1",
    10: "Beat FNAF 2 - Night 2",
    11: "Beat FNAF 2 - Night 3",
    12: "Beat FNAF 2 - Night 4",
    13: "Beat FNAF 2 - Night 5 (Hard)",

    # FNAF 3
    14: "Beat FNAF 3 - Night 1",
    15: "Beat FNAF 3 - Night 2",
    16: "Beat FNAF 3 - Night 3",
    17: "Beat FNAF 3 - Night 4",
    18: "Beat FNAF 3 - Night 5 (Hard)",

    # Parts and Service Normal
    19: "Complete Parts and Service - Bonnie",
    20: "Complete Parts and Service - Chica",
    21: "Complete Parts and Service - Freddy",
    22: "Complete Parts and Service - Foxy",

    # Vent Repair Normal
    23: "Complete Vent Repair - Mangle",
    24: "Complete Vent Repair - Ennard",

    # Night Terrors
    25: "Complete Night Terrors - Funtime Freddy",
    26: "Complete Night Terrors - Nightmarionne",
    27: "Complete Night Terrors - Circus Baby",
    28: "Complete Night Terrors - Nightmare Fredbear",

    # Finale
    29: "Complete Pizza Party",

    # Dark Rooms Hard
    30: "Complete Dark Rooms (Hard) - Plushtrap",
    31: "Complete Dark Rooms (Hard) - Nightmare BB",

    # Parts and Service Hard
    32: "Complete Parts and Service (Hard) - Bonnie",
    33: "Complete Parts and Service (Hard) - Chica",
    34: "Complete Parts and Service (Hard) - Freddy",
    35: "Complete Parts and Service (Hard) - Foxy",

    # Dark Rooms Hard (Cont.)
    36: "Complete Dark Rooms (Hard) - Plushbaby",
    37: "Complete Dark Rooms (Hard) - Funtime Foxy",

    # Vent Repair Hard
    38: "Complete Vent Repair (Hard) - Mangle",
    39: "Complete Vent Repair (Hard) - Ennard",

    # FNAF 2 Hard (Withered)
    40: "Beat FNAF 2 - Withered",
}

# Canonical mapping of Prize_Info_DataTable row IDs to Archipelago location checks
DEFAULT_PRIZE_MAP: dict[str, str] = {
    # Food / Drink (Category NewEnumerator4)
    "55": "Prize - Food/Drink: Disappointment Chips",
    "56": "Prize - Food/Drink: El Chip's Tortilla Chips Bold and Spicy",
    "57": "Prize - Food/Drink: Meat Bites XL",
    "58": "Prize - Food/Drink: Bonnie Bites",
    "59": "Prize - Food/Drink: Allergy Friendly Mixed Nuts",
    "60": "Prize - Food/Drink: Meat Bites",
    "61": "Prize - Food/Drink: Stick of Butter",
    "62": "Prize - Food/Drink: Pirate Plunderbar",
    "63": "Prize - Food/Drink: Foxy Cove Cooler",
    "64": "Prize - Food/Drink: Butter for One",
    "65": "Prize - Food/Drink: Freddy Fudgebar",
    "66": "Prize - Food/Drink: Exotic Beverage",
    "81": "Prize - Food/Drink: Sodaroni",
    "82": "Prize - Food/Drink: Chica Chug",
    "83": "Prize - Food/Drink: El Chip's Tortilla Chips",
    "84": "Prize - Food/Drink: Fazbar",
    "85": "Prize - Food/Drink: Lemon Chica Bar",
    "86": "Prize - Food/Drink: Slice of Cake",

    # Plushies (Category NewEnumerator2)
    "12": "Prize - Plushie: Plushbaby",
    "13": "Prize - Plushie: Plushbaby (Scrap Baby ver.)",
    "18": "Prize - Plushie: Funtime Foxy",
    "19": "Prize - Plushie: Funtime Freddy",
    "21": "Prize - Plushie: Nightmarionne Plush",
    "24": "Prize - Plushie: Toy Freddy Plush",
    "25": "Prize - Plushie: Toy Bonnie Plush",
    "26": "Prize - Plushie: Toy Chica Plush",
    "28": "Prize - Plushie: Puppet Plush",
    "30": "Prize - Plushie: Bonnie Plush",
    "31": "Prize - Plushie: Chica Plush",
    "32": "Prize - Plushie: Foxy Plush",
    "33": "Prize - Plushie: Freddy Plush",

    # Action Figures (Category NewEnumerator0)
    "34": "Prize - Action Figure: Freddy Action Figure",
    "35": "Prize - Action Figure: Ennard Action Figure",
    "36": "Prize - Action Figure: Mangle Action Figure",
    "37": "Prize - Action Figure: Toy Freddy Action Figure",
    "38": "Prize - Action Figure: Toy Bonnie Action Figure",
    "39": "Prize - Action Figure: Toy Chica Action Figure",
    "40": "Prize - Action Figure: Balloon Boy Action Figure",
    "41": "Prize - Action Figure: Puppet Action Figure",
    "42": "Prize - Action Figure: Plushtrap Action Figure",
    "43": "Prize - Action Figure: Bonnie Action Figure",
    "44": "Prize - Action Figure: Chica Action Figure",
    "45": "Prize - Action Figure: Foxy Action Figure",
    "48": "Prize - Action Figure: Nightmarionne Action Figure",
    "50": "Prize - Action Figure: Circus Baby Action Figure",
    "51": "Prize - Action Figure: Funtime Foxy Action Figure",
    "52": "Prize - Action Figure: Funtime Freddy Action Figure",
    "53": "Prize - Action Figure: Nightmare Fredbear Action Figure",
    "54": "Prize - Action Figure: Bon-Bon Action Figure",

    # Toys (Category NewEnumerator1)
    "67": "Prize - Toy: Cupcake",
    "68": "Prize - Toy: Toy phone",
    "69": "Prize - Toy: Toy Robot",
    "70": "Prize - Toy: Toy Catterpillar",

    # Bobbleheads (Category NewEnumerator6)
    "77": "Prize - Other: Freddy Bobblehead",
    "78": "Prize - Other: Chica Bobblehead",
    "79": "Prize - Other: Bonnie Bobblehead",

    # Prize Counter Token Tiers (Category NewEnumerator5)
    "88": "Prize - Plushie: Helpy Plush",
}


class GvasError(ValueError):
    """The bytes are not a save this reader can walk: truncated, or a length or count that points outside the file."""


# A real save is about 15 KB. Nothing is read from a file far beyond that.
MAX_SAVE_BYTES = 16 * 1024 * 1024
# Property names, type names and the inner types of arrays and sets are short; anything longer is garbage, not a name.
MAX_NAME_BYTES = 1000


def _take(data: bytes, pos: int, size: int, what: str) -> bytes:
    """`size` bytes at `pos`, or GvasError when they are not all inside the file."""
    if pos < 0 or size < 0 or pos + size > len(data):
        raise GvasError(f"{what}: {size} byte(s) at offset {pos} are outside the {len(data)}-byte save")
    return data[pos:pos + size]


def _i32(data: bytes, pos: int, what: str) -> int:
    return struct.unpack("<i", _take(data, pos, 4, what))[0]


def _u32(data: bytes, pos: int, what: str) -> int:
    return struct.unpack("<I", _take(data, pos, 4, what))[0]


def _read_fstring(data: bytes, pos: int, what: str) -> tuple[str, int]:
    """An Unreal FString at `pos`: (text, offset after it). A positive length is Latin-1 bytes with a trailing NUL, a negative one is UTF-16."""
    length = _i32(data, pos, what)
    pos += 4
    if length == 0:
        return "", pos
    if length > 0:
        return _take(data, pos, length, what).decode("latin-1").rstrip("\x00"), pos + length
    size = -length * 2
    return _take(data, pos, size, what).decode("utf-16-le", errors="replace").rstrip("\x00"), pos + size


def _name_length(data: bytes, pos: int, what: str) -> int:
    """The length prefix of a type name: a small positive number, else the data is not what the walk thinks it is."""
    length = _i32(data, pos, what)
    if not 0 <= length <= MAX_NAME_BYTES:
        raise GvasError(f"{what}: implausible length {length} at offset {pos}")
    return length


def _skip_header(data: bytes) -> int:
    """Offset of the first property: after the magic, versions, engine version, build id, custom versions and the class name."""
    pos = 4 + 4 + 4 + 6 + 4
    pos += 4 + _u32(data, pos, "build id length")
    pos += 4  # custom version format
    pos += 4 + _u32(data, pos, "custom version count") * 20
    pos += 4 + _u32(data, pos, "class name length")
    return pos


def parse_gvas_save(data: bytes) -> dict[str, Any]:
    """Parse UE4.23 GVAS savegame binary into a dictionary of properties.

    Returns {} for something that is not a GVAS file. Raises GvasError for a save that is cut off or whose lengths and counts point outside
    it (a half-written or corrupt file): the caller tries again later instead of working from half a save.
    """
    if len(data) < 24 or data[:4] != b"GVAS":
        return {}
    if len(data) > MAX_SAVE_BYTES:
        raise GvasError(f"{len(data)} bytes is far more than a save")

    pos = _skip_header(data)

    parsed: dict[str, Any] = {}
    while pos < len(data):
        if pos + 4 > len(data):
            break
        name_len = struct.unpack("<i", data[pos:pos + 4])[0]
        pos += 4
        if name_len <= 0 or name_len > MAX_NAME_BYTES or pos + name_len > len(data):
            break
        name = data[pos:pos + name_len].decode("latin-1").rstrip("\x00")
        pos += name_len
        if name == "None":
            break

        if pos + 4 > len(data):
            break
        type_len = struct.unpack("<i", data[pos:pos + 4])[0]
        pos += 4
        if type_len <= 0 or type_len > MAX_NAME_BYTES or pos + type_len > len(data):
            break
        prop_type = data[pos:pos + type_len].decode("latin-1").rstrip("\x00")
        pos += type_len

        if pos + 8 > len(data):
            break
        size = struct.unpack("<Q", data[pos:pos + 8])[0]
        pos += 8

        if prop_type == "ArrayProperty":
            _name_length(data, pos, f"{name} inner type")
            inner, pos = _read_fstring(data, pos, f"{name} inner type")
            pos += 1
            if inner in ("NameProperty", "StrProperty"):
                arr_count = _u32(data, pos, f"{name} count")
                arr_pos = pos + 4
                if arr_count > (len(data) - arr_pos) // 4:  # every element has at least its own 4-byte length
                    raise GvasError(f"{name}: {arr_count} elements cannot fit in the {len(data) - arr_pos} bytes left")
                elements = []
                for _ in range(arr_count):
                    el_str, arr_pos = _read_fstring(data, arr_pos, f"{name} element")
                    elements.append(el_str)
                parsed[name] = elements
            else:
                parsed[name] = []  # an array of something else (structs, numbers): not read, skipped by its size
            pos += size
        elif prop_type == "SetProperty":
            _name_length(data, pos, f"{name} inner type")
            inner, pos = _read_fstring(data, pos, f"{name} inner type")
            pos += 1
            if inner == "IntProperty":
                num_el = _u32(data, pos + 4, f"{name} count")
                el_pos = pos + 8
                if num_el > (len(data) - el_pos) // 4:
                    raise GvasError(f"{name}: {num_el} elements cannot fit in the {len(data) - el_pos} bytes left")
                elements = []
                for _ in range(num_el):
                    elements.append(_i32(data, el_pos, f"{name} element"))
                    el_pos += 4
                parsed[name] = elements
            else:
                parsed[name] = []  # a set of objects or names: not read, skipped by its size
            pos += size
        elif prop_type == "MapProperty":
            _name_length(data, pos, f"{name} key type")
            _, pos = _read_fstring(data, pos, f"{name} key type")
            _name_length(data, pos, f"{name} value type")
            _, pos = _read_fstring(data, pos, f"{name} value type")
            pos += 1
            num_el = _u32(data, pos + 4, f"{name} count")
            m_pos = pos + 8
            if num_el > (len(data) - m_pos) // 9:  # a key's length prefix and the "None\0" that ends its struct
                raise GvasError(f"{name}: {num_el} entries cannot fit in the {len(data) - m_pos} bytes left")
            entries = {}
            for _ in range(num_el):
                key, m_pos = _read_fstring(data, m_pos, f"{name} key")
                none_idx = data.find(b"None\x00", m_pos)
                if none_idx == -1:
                    break
                struct_chunk = data[m_pos:none_idx + 5]
                m_pos = none_idx + 5

                is_comp = False
                if b"Completed_7_" in struct_chunk:
                    c_idx = struct_chunk.find(b"Completed_7_")
                    b_idx = struct_chunk.find(b"BoolProperty\x00", c_idx)
                    if b_idx != -1:
                        value_at = b_idx + len(b"BoolProperty\x00") + 8
                        if value_at < len(struct_chunk):
                            is_comp = (struct_chunk[value_at] != 0)
                entries[key] = is_comp
            parsed[name] = entries
            pos += size
        elif prop_type == "BoolProperty":
            parsed[name] = (_take(data, pos, 1, name)[0] != 0)
            pos += 2
        elif prop_type in ("IntProperty", "FloatProperty"):
            pos += 1
            if prop_type == "IntProperty":
                parsed[name] = _i32(data, pos, name)
            pos += 4
        else:
            pos += 1 + size

    return parsed


def load_prize_checks() -> list[str]:
    """Load PRIZE_CHECKS list from fnaf_help_wanted/data.py without executing full package __init__."""
    try:
        # Vendored inside the apworld (a zip archive): files cannot be read by path there, so import the data module.
        from .data import PRIZE_CHECKS  # type: ignore[import-not-found]
        return list(PRIZE_CHECKS)
    except (ImportError, ValueError):
        pass  # standalone: fall back to the file-based lookup below
    candidates = [
        Path(__file__).resolve().parent.parent / "fnaf_help_wanted" / "data.py",
        Path(__file__).resolve().parent.parent / "ue4ss_mod" / "FNAFHWArchipelago" / "locations.json",
    ]
    for cand in candidates:
        if cand.name == "data.py" and cand.exists():
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("fnaf_hw_data", cand)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    prizes = getattr(mod, "PRIZE_CHECKS", [])
                    if prizes:
                        return list(prizes)
            except Exception:
                pass
        elif cand.name == "locations.json" and cand.exists():
            try:
                import json
                raw = json.loads(cand.read_text(encoding="utf-8"))
                prizes = [entry["location_name"] for entry in raw.get("prizes", [])]
                if prizes:
                    return prizes
            except Exception:
                pass
    return []


def extract_earned_locations(
    parsed: dict[str, Any],
    row_to_minigame: dict[int, str] | None = None,
) -> list[str]:
    """Convert parsed savegame properties into list of Archipelago location check names."""
    if not parsed:
        return []

    row_map = row_to_minigame or DEFAULT_ROW_MAP
    earned: list[str] = []

    # 1. Faz Tokens (direct ID mapping 1..30)
    coins = parsed.get("CollectedCoins", [])
    for coin_id in coins:
        try:
            cid = int(coin_id)
            if 1 <= cid <= 30:
                earned.append(f"Collect Faz Token {cid:02d}")
        except (ValueError, TypeError):
            pass

    # 2. Glitch Tapes (direct ID mapping)
    GLITCH_ID_MAP = {
        14: "Collect Prize Counter Intro Tape",
        0:  "Collect Glitch Tape 02",
        1:  "Collect Glitch Tape 03",
        2:  "Collect Glitch Tape 04",
        4:  "Collect Glitch Tape 05",
        5:  "Collect Glitch Tape 06",
        6:  "Collect Glitch Tape 07",
        7:  "Collect Glitch Tape 08",
        8:  "Collect Glitch Tape 09",
        9:  "Collect Glitch Tape 10",
        10: "Collect Glitch Tape 11",
        11: "Collect Glitch Tape 12",
        12: "Collect Glitch Tape 13",
        13: "Collect Glitch Tape 14",
        15: "Collect Glitch Tape 15",
        16: "Collect Glitch Tape 16",
    }
    tapes = parsed.get("CollectedGlitches", [])
    for tape_id in tapes:
        try:
            tid = int(tape_id)
            if tid in GLITCH_ID_MAP:
                earned.append(GLITCH_ID_MAP[tid])
        except (ValueError, TypeError):
            pass

    # 3. Prizes (exact row ID mapping only)
    prizes = parsed.get("Prizes", [])
    for prize_id in prizes:
        p_key = str(prize_id).strip()
        if p_key in DEFAULT_PRIZE_MAP:
            earned.append(DEFAULT_PRIZE_MAP[p_key])

    # 4. Minigame Clears from LevelInfo
    levels = parsed.get("LevelInfo", {})
    for k, completed in levels.items():
        if completed and k.isdigit():
            row_id = int(k)
            if row_id in row_map:
                earned.append(row_map[row_id])

    # 5. Glitchtrap Defeated
    if parsed.get("GlitchtrapDefeated") is True:
        earned.append("Goal - Glitchtrap Ending (You Do Not Die)")

    # Deduplicate while preserving order
    return list(dict.fromkeys(earned))


def get_archipelago_savegame_path(slot_name: str | None = None) -> Path | None:
    """Find the dedicated Archipelago savegame (`<slot_name>.sav`, default Playerarchi.sav) if it exists. Never returns Player00.sav."""
    slot_name = _slot_name(slot_name)
    appdata = os.environ.get("LOCALAPPDATA", "")
    if appdata:
        p = Path(appdata) / "freddys" / "Saved" / "SaveGames" / f"{slot_name}.sav"
        if p.exists():
            return p
    return None


def get_normal_savegame_path() -> Path | None:
    """Find the player's vanilla savegame (Player00.sav). Used solely for template data / backup."""
    appdata = os.environ.get("LOCALAPPDATA", "")
    if appdata:
        p00 = Path(appdata) / "freddys" / "Saved" / "SaveGames" / "Player00.sav"
        if p00.exists():
            return p00
    return None


def get_active_savegame_path(prefer_archi: bool = True) -> Path | None:
    """Find the active savegame. When prefer_archi=True, STRICTLY returns Playerarchi.sav without leaking Player00."""
    if prefer_archi:
        return get_archipelago_savegame_path()
    return get_normal_savegame_path()


# Top-level SetProperty progress sets that a fresh game starts with empty: name -> inner property type.
# Layout (verified against real saves, see the property walk of 100percent.sav): name, "SetProperty", size 8,
# inner type, flag byte 0, remove-count u32 0, element-count u32 0.
_RESET_SETS = {
    "CollectedGlitches": "IntProperty",
    "CollectedCoins": "IntProperty",
    "GlitchesListenedTo": "IntProperty",
    "HUBUpdateVOListenedTo": "IntProperty",
    "HUBUpdateVOCollected": "IntProperty",
    "ObjectsEaten": "ObjectProperty",
}


def _empty_set_property(name: str, inner_type: str) -> bytes:
    def fstring(text: str) -> bytes:
        raw = text.encode("latin-1") + b"\x00"
        return struct.pack("<i", len(raw)) + raw

    return (
        fstring(name)
        + fstring("SetProperty")
        + struct.pack("<Q", 8)
        + fstring(inner_type)
        + b"\x00"
        + struct.pack("<II", 0, 0)
    )


def create_clean_playerarchi_data(template_data: bytes) -> bytes:
    """
    Generate a 100% clean, unplayed Archipelago save binary from a GVAS template.
    Preserves engine header, EULA, and menu instruction flags, while resetting:
    - LevelInfo: all 37 minigame row completions to False
    - Prizes: empty ArrayProperty (NameProperty)
    - CollectedGlitches / CollectedCoins: empty SetProperty (IntProperty)
    - GlitchesListenedTo, HUBUpdateVOListenedTo, HUBUpdateVOCollected: empty (tapes and hub audio of a completed
      template must not count as already listened to / collected)
    - ObjectsEaten: empty SetProperty (ObjectProperty)
    - NumberOfGamesWon: 0
    Everything else (settings, EULA, menu flags, statistics) is kept from the template. The template is only read.
    Raises GvasError when the template is not a GVAS save or its lengths point outside it; nothing is written then.
    """
    if template_data[:4] != b"GVAS":
        raise GvasError("the template is not a GVAS save")
    if len(template_data) > MAX_SAVE_BYTES:
        raise GvasError(f"{len(template_data)} bytes is far more than a save")
    buf = bytearray(template_data)

    # 1. Reset all LevelInfo Completed booleans to False
    pos = 0
    while True:
        c_idx = buf.find(b"Completed_7_C5B1BBD045D47AFB45A9A4AD494ABC84\x00", pos)
        if c_idx == -1:
            break
        b_idx = buf.find(b"BoolProperty\x00", c_idx)
        if b_idx != -1 and b_idx - c_idx < 100:
            val_offset = b_idx + len(b"BoolProperty\x00") + 8
            if val_offset < len(buf):  # a cut-off file may end before the value
                buf[val_offset] = 0
        pos = c_idx + 1

    # 2. Reset NumberOfGamesWon to 0
    w_idx = buf.find(b"NumberOfGamesWon\x00")
    if w_idx != -1:
        val_idx = w_idx + len(b"NumberOfGamesWon\x00") + 4 + len(b"IntProperty\x00") + 4 + 4 + 1
        if val_idx + 4 <= len(buf):  # assigning past the end of a bytearray would APPEND instead of resetting
            buf[val_idx : val_idx + 4] = b"\x00\x00\x00\x00"

    # 3. Dynamically parse top-level properties and replace Prizes, CollectedGlitches, CollectedCoins
    pos = _skip_header(buf)

    output = bytearray(buf[:pos])

    while pos < len(buf):
        start = pos
        if pos + 4 > len(buf):
            output += buf[pos:]
            break
        name_len = struct.unpack("<i", buf[pos : pos + 4])[0]
        pos += 4
        if name_len <= 0 or name_len > 1000 or pos + name_len > len(buf):
            output += buf[start:]
            break
        name = buf[pos : pos + name_len].decode("latin-1").rstrip("\x00")
        pos += name_len
        if name == "None":
            output += buf[start:]
            break

        if pos + 4 > len(buf):
            output += buf[start:]
            break
        type_len = struct.unpack("<i", buf[pos : pos + 4])[0]
        pos += 4
        if type_len <= 0 or type_len > 1000 or pos + type_len > len(buf):
            output += buf[start:]
            break
        prop_type = buf[pos : pos + type_len].decode("latin-1").rstrip("\x00")
        pos += type_len

        if pos + 8 > len(buf):
            output += buf[start:]
            break
        size = struct.unpack("<Q", buf[pos : pos + 8])[0]
        pos += 8

        if prop_type == "ArrayProperty":
            pos += 4 + _name_length(buf, pos, f"{name} inner type") + 1 + size
        elif prop_type == "SetProperty":
            pos += 4 + _name_length(buf, pos, f"{name} inner type") + 1 + size
        elif prop_type == "MapProperty":
            pos += 4 + _name_length(buf, pos, f"{name} key type")
            pos += 4 + _name_length(buf, pos, f"{name} value type") + 1 + size
        elif prop_type == "BoolProperty":
            pos += 2
        elif prop_type in ("IntProperty", "FloatProperty"):
            pos += 1 + 4
        else:
            pos += 1 + size
        if pos <= start:  # every property moves forward; anything else would walk the same bytes for ever
            raise GvasError(f"{name}: the walk did not advance")

        prop_block = buf[start:pos]

        if name == "Prizes":
            # Empty ArrayProperty (NameProperty, uint64 size = 4, uint32 count = 0)
            empty_p = (
                b"\x07\x00\x00\x00Prizes\x00"
                b"\x0e\x00\x00\x00ArrayProperty\x00"
                b"\x04\x00\x00\x00\x00\x00\x00\x00"
                b"\r\x00\x00\x00NameProperty\x00"
                b"\x00"
                b"\x00\x00\x00\x00"
            )
            output += empty_p
        elif name in _RESET_SETS:
            output += _empty_set_property(name, _RESET_SETS[name])
        else:
            output += prop_block

    return bytes(output)


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write the save through a temp file and os.replace, so an interrupted write never leaves a truncated save for the game to load.
    If Windows refuses the replace (the game has the file open) the bytes are written in place, as before."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    try:
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        path.write_bytes(data)


def ensure_clean_archipelago_save(
    target_path: Path | None = None,
    template_path: Path | None = None,
    slot_name: str | None = None,
) -> Path:
    """Write a clean Archipelago save (`<slot_name>.sav`, default Playerarchi.sav) from the normal save as template."""
    if target_path is None:
        slot_name = _slot_name(slot_name)
        appdata = os.environ.get("LOCALAPPDATA", "")
        if appdata:
            target_path = Path(appdata) / "freddys" / "Saved" / "SaveGames" / f"{slot_name}.sav"
        else:
            target_path = Path(f"{slot_name}.sav")

    target_path.parent.mkdir(parents=True, exist_ok=True)

    if template_path is None:
        template_path = get_normal_savegame_path()

    if template_path and template_path.exists():
        try:
            clean_bytes = create_clean_playerarchi_data(template_path.read_bytes())
        except GvasError as e:
            # A damaged Player00.sav must not take the connection down with it: say so and write nothing, as when there is no template.
            print(f"[Save Manager] Warning: {template_path.name} could not be used as the template ({e}); no clean save was written for {target_path.name}.")
        else:
            _write_bytes_atomic(target_path, clean_bytes)
            print(f"[Save Manager] Created clean Archipelago save '{target_path.name}' ({len(clean_bytes)} bytes).")
    else:
        print(f"[Save Manager] Warning: Template save not found to generate {target_path.name}.")

    return target_path
