"""Synthetic GVAS saves for tests, built from the layout the save generator itself walks.

They replace the private, gitignored Player00.sav / Playerarchi.sav / 100percent.sav that tests used to pick up silently from the
current directory.
"""

import struct


def fstring(text: str) -> bytes:
    raw = text.encode("latin-1") + b"\x00"
    return struct.pack("<i", len(raw)) + raw


def set_prop(name, inner, values):
    body = struct.pack("<II", 0, len(values)) + b"".join(values)
    return fstring(name) + fstring("SetProperty") + struct.pack("<Q", len(body)) + fstring(inner) + b"\x00" + body


def int_set(name, ints):
    return set_prop(name, "IntProperty", [struct.pack("<i", i) for i in ints])


def object_set(name, paths):
    return set_prop(name, "ObjectProperty", [fstring(p) for p in paths])


def bool_prop(name, value):
    return fstring(name) + fstring("BoolProperty") + struct.pack("<Q", 0) + bytes([1 if value else 0]) + b"\x00"


def int_prop(name, value):
    return fstring(name) + fstring("IntProperty") + struct.pack("<Q", 4) + b"\x00" + struct.pack("<i", value)


def str_prop(name, text):
    value = fstring(text)
    return fstring(name) + fstring("StrProperty") + struct.pack("<Q", len(value)) + b"\x00" + value


def name_array(name, names):
    body = struct.pack("<I", len(names)) + b"".join(fstring(n) for n in names)
    return fstring(name) + fstring("ArrayProperty") + struct.pack("<Q", len(body)) + fstring("NameProperty") + b"\x00" + body


def header():
    return (
        b"GVAS" + struct.pack("<II", 2, 517) + struct.pack("<HHH", 4, 23, 1) + struct.pack("<I", 0)
        + fstring("++UE4+Release-4.23")  # branch
        + struct.pack("<I", 3)  # custom version format
        + struct.pack("<I", 0)  # no custom versions
        + fstring("/Game/ProductionAssets/Blueprints/Data/SaveGame/FNAFSaveGame.FNAFSaveGame_C")
    )


def completed_template() -> bytes:
    return header() + b"".join([
        name_array("Prizes", ["Prize_A", "Prize_B", "Prize_C"]),
        int_set("CollectedGlitches", [1, 2, 3, 4]),
        bool_prop("HasPlayedMenuInstructions", True),
        int_set("GlitchesListenedTo", [1, 2, 3, 4, 5]),
        int_set("HUBUpdateVOListenedTo", [1, 2]),
        int_set("HUBUpdateVOCollected", [1, 2]),
        int_prop("NumberOfGamesWon", 7),
        int_prop("NumberOfGamesLost", 3),
        object_set("ObjectsEaten", ["/Game/Maps/Hub.Hub:PersistentLevel.Pizza_1", "/Game/Maps/Hub.Hub:PersistentLevel.Pizza_2"]),
        int_set("CollectedCoins", [1, 2, 3]),
        bool_prop("EULAAgreed", True),
        str_prop("GammaSettings", "1.25"),
        fstring("None"),
    ])


def walk(buf: bytes):
    """Top-level properties as {name: (type, raw value bytes)}; independent of save_reader's own walker."""
    pos = 4 + 4 + 4 + 6 + 4
    n = struct.unpack("<I", buf[pos:pos + 4])[0]
    pos += 4 + n + 4
    c = struct.unpack("<I", buf[pos:pos + 4])[0]
    pos += 4 + c * 20
    n = struct.unpack("<I", buf[pos:pos + 4])[0]
    pos += 4 + n
    out = {}
    while pos < len(buf):
        n = struct.unpack("<i", buf[pos:pos + 4])[0]
        pos += 4
        name = buf[pos:pos + n].decode("latin-1").rstrip("\0")
        pos += n
        if name == "None":
            break
        n = struct.unpack("<i", buf[pos:pos + 4])[0]
        pos += 4
        ptype = buf[pos:pos + n].decode("latin-1").rstrip("\0")
        pos += n
        size = struct.unpack("<Q", buf[pos:pos + 8])[0]
        pos += 8
        if ptype in ("ArrayProperty", "SetProperty"):
            n = struct.unpack("<i", buf[pos:pos + 4])[0]
            pos += 4 + n + 1
            out[name] = (ptype, buf[pos:pos + size])
            pos += size
        elif ptype == "MapProperty":
            n = struct.unpack("<i", buf[pos:pos + 4])[0]
            pos += 4 + n
            n = struct.unpack("<i", buf[pos:pos + 4])[0]
            pos += 4 + n + 1
            out[name] = (ptype, buf[pos:pos + size])
            pos += size
        elif ptype == "BoolProperty":
            out[name] = (ptype, buf[pos:pos + 1])
            pos += 2
        else:
            pos += 1
            out[name] = (ptype, buf[pos:pos + size])
            pos += size
    return out


def starter_player00() -> bytes:
    """A fresh normal save: only the starting basketball (prize row 3), no progress."""
    return header() + b"".join([
        name_array("Prizes", ["3"]),
        bool_prop("HasPlayedMenuInstructions", True),
        int_prop("NumberOfGamesWon", 0),
        bool_prop("EULAAgreed", True),
        str_prop("GammaSettings", "1.0"),
        fstring("None"),
    ])
