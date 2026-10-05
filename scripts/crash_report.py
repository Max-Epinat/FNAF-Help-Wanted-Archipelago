"""Summarise a game crash dump (and the end of UE4SS.log) as a few lines of text. Standard library only, read-only.

    py scripts/crash_report.py [dump.dmp ...] [--win64 <game>\\freddys\\Binaries\\Win64] [--log UE4SS.log]

With no dump given it looks at the newest dumps in `--win64` (UE4SS writes crash_*.dmp there) and in
`%LOCALAPPDATA%\\freddys\\Saved\\Crashes\\*\\UE4Minidump.dmp` (the game's own crash reporter).

The dumps are 20+ MB and must never be committed; the text this prints is what to paste into a bug report.
The signature table is for the dumps seen on 2026-10-04 (game exe of 2026-03-21, UE4SS v3.0.1 build d935b5b): a different build
has different offsets, so an unknown signature only means "not seen before".
"""

import argparse
import datetime
import glob
import os
import re
import struct
import sys

MODULE_LIST, THREAD_LIST, EXCEPTION, MISC_INFO, THREAD_INFO_LIST = 4, 3, 6, 15, 17

# (module, rva) -> what is known about it. Offsets come from disassembling the shipped binaries (docs/game-research.md, "Crashes").
KNOWN_SIGNATURES = {
    ("freddys-Win64-Shipping.exe", 0x92D06F):
        "the game's own intermittent launch crash (null read a few seconds after start, since April); not caused by the mod",
    ("UE4SS.dll", 0x3C4113):
        "UE4SS Lua FString:ToString read a bogus pointer (wcslen loop). Seen when Lua decoded garbage FStrings: the old prize poll and World:GetName()",
    ("UE4SS.dll", 0x52DBB9):
        "UE4SS object-array scan (FindFirstOf/FindAllOf by class name) hit an object being destroyed (ClassPrivate == NULL); "
        "when the thread is a UE4SS worker thread, a Lua timer touched game objects off the game thread",
}

ACCESS = {0: "read", 1: "write", 8: "execute"}


def _unpack(fmt, data, offset):
    return struct.unpack_from(fmt, data, offset)


def parse_minidump(data):
    """Return a dict with modules, exception, uptime and thread facts. Raises ValueError on a file that is not a minidump."""
    if len(data) < 32 or data[:4] != b"MDMP":
        raise ValueError("not a minidump (empty or truncated file?)")
    _, _, stream_count, directory_rva, _, timestamp, _ = _unpack("<4sIIIIIQ", data, 0)
    streams = {}
    for index in range(stream_count):
        kind, size, rva = _unpack("<III", data, directory_rva + 12 * index)
        streams[kind] = (size, rva)

    modules = []
    if MODULE_LIST in streams:
        offset = streams[MODULE_LIST][1]
        for index in range(_unpack("<I", data, offset)[0]):
            base, size, _, _, name_rva = _unpack("<QIIII", data, offset + 4 + index * 108)
            name_len = _unpack("<I", data, name_rva)[0]
            name = data[name_rva + 4:name_rva + 4 + name_len].decode("utf-16le")
            modules.append((base, size, name.replace("/", "\\").split("\\")[-1]))

    def locate(address):
        for base, size, name in modules:
            if base <= address < base + size:
                return name, address - base
        return None, address

    info = {"timestamp": timestamp, "modules": modules, "locate": locate, "streams": sorted(streams)}
    if THREAD_LIST in streams:
        info["thread_count"] = _unpack("<I", data, streams[THREAD_LIST][1])[0]
    if MISC_INFO in streams:
        created = _unpack("<IIII", data, streams[MISC_INFO][1])[3]
        info["uptime_seconds"] = timestamp - created if created else None

    if EXCEPTION in streams:
        offset = streams[EXCEPTION][1]
        thread_id = _unpack("<I", data, offset)[0]
        code, _, _, address, parameter_count = _unpack("<IIQQI", data, offset + 8)
        parameters = _unpack("<15Q", data, offset + 8 + 32)[:min(parameter_count, 15)]
        module, rva = locate(address)
        info["exception"] = {
            "thread_id": thread_id, "code": code, "address": address, "module": module, "rva": rva, "parameters": parameters}

    if THREAD_INFO_LIST in streams and "exception" in info:
        offset = streams[THREAD_INFO_LIST][1]
        header_size, entry_size, count = _unpack("<III", data, offset)
        rows = []
        for index in range(count):
            thread_id, _, _, _, created, _, kernel, user, start, _ = _unpack(
                "<IIIIQQQQQQ", data, offset + header_size + index * entry_size)
            rows.append((created, thread_id, start, user))
        rows.sort()
        for order, (_, thread_id, start, user) in enumerate(rows):
            if thread_id == info["exception"]["thread_id"]:
                start_module, start_rva = locate(start)
                info["fault_thread"] = {
                    "start_module": start_module, "start_rva": start_rva, "cpu_seconds": user / 1e7, "created_order": order,
                    "is_first_thread": order == 0}
    return info


def describe(info, name="dump"):
    lines = [f"== {name}"]
    when = datetime.datetime.fromtimestamp(info["timestamp"], datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    uptime = info.get("uptime_seconds")
    lines.append(f"written {when}; process uptime {uptime} s; {info.get('thread_count', '?')} threads")
    exc = info.get("exception")
    if not exc:
        lines.append("no exception record in this dump")
        return "\n".join(lines)
    where = f"{exc['module']}+0x{exc['rva']:x}" if exc["module"] else f"unknown module, address 0x{exc['address']:x}"
    lines.append(f"exception 0x{exc['code']:08x} at {where}")
    if exc["code"] == 0xC0000005 and len(exc["parameters"]) >= 2:
        kind = ACCESS.get(exc["parameters"][0], "access")
        lines.append(f"access violation: {kind} of address 0x{exc['parameters'][1]:x}"
                     + (" (a null pointer plus a small offset)" if exc["parameters"][1] < 0x10000 else ""))
    thread = info.get("fault_thread")
    if thread:
        start = f"{thread['start_module']}+0x{thread['start_rva']:x}" if thread["start_module"] else "unknown"
        kind = "the game's first (main) thread" if thread["is_first_thread"] else "NOT the first thread"
        lines.append(f"faulting thread {exc['thread_id']}: started at {start}, {thread['cpu_seconds']:.1f} s of CPU, {kind}")
    else:
        lines.append(f"faulting thread {exc['thread_id']} (this dump has no thread timing)")
    meaning = KNOWN_SIGNATURES.get((exc["module"], exc["rva"]))
    lines.append("known signature: " + (meaning if meaning else "no, not seen before"))
    return "\n".join(lines)


def log_tail(path, count=12):
    """The last `count` log entries. UE4SS joins some entries without a newline, so split on the timestamps."""
    with open(path, "rb") as handle:
        text = handle.read().decode("utf-8", errors="replace")
    entries = [entry.strip() for entry in re.split(r"(?=\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\])", text) if entry.strip()]
    return entries[-count:]


def find_dumps(win64=None):
    paths = []
    if win64:
        paths += glob.glob(os.path.join(win64, "crash_*.dmp"))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        paths += glob.glob(os.path.join(local, "freddys", "Saved", "Crashes", "*", "UE4Minidump.dmp"))
    paths = [p for p in paths if os.path.getsize(p) > 0]
    return sorted(paths, key=os.path.getmtime, reverse=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("dumps", nargs="*")
    parser.add_argument("--win64", help="the game's Binaries\\Win64 folder (crash_*.dmp and UE4SS.log live there)")
    parser.add_argument("--log", help="UE4SS.log; its last entries are printed (default: <win64>\\UE4SS.log)")
    parser.add_argument("--latest", type=int, default=3, help="how many of the newest dumps to show when none are named")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # log lines can hold any character

    dumps = args.dumps or find_dumps(args.win64)[:args.latest]
    if not dumps:
        print("no crash dumps found")
    for path in dumps:
        try:
            with open(path, "rb") as handle:
                print(describe(parse_minidump(handle.read()), os.path.basename(os.path.dirname(path)) if path.endswith("UE4Minidump.dmp") else os.path.basename(path)))
        except (OSError, ValueError, struct.error) as error:
            print(f"== {path}\ncannot read: {error}")
        print()

    log = args.log or (os.path.join(args.win64, "UE4SS.log") if args.win64 else None)
    if log and os.path.exists(log):
        print(f"== last entries of {os.path.basename(log)} (it is overwritten at every launch: this is the LAST session only)")
        for entry in log_tail(log):
            print("  " + entry[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
