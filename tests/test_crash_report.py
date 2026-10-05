"""scripts/crash_report.py on synthetic minidumps (built here, nothing from a real game run)."""

import io
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "scripts"))

import crash_report  # noqa: E402

UE4SS_BASE = 0x7FFF71400000
EXE_BASE = 0x7FF754600000


def build_dump(fault_module, fault_rva, parameters=(0, 0x18), uptime=787, worker_thread=True, with_thread_info=True):
    """A minimal valid minidump: module list, exception, misc info, thread list and (optionally) thread timing."""
    modules = [(EXE_BASE, 0x5000000, "C:\\Game\\freddys-Win64-Shipping.exe"), (UE4SS_BASE, 0x1000000, "C:\\Game\\UE4SS.dll"),
               (0x7FFF00000000, 0x200000, "C:\\Windows\\System32\\ucrtbase.dll")]
    bases = {name.split("\\")[-1]: base for base, _, name in modules}
    timestamp = 1_790_000_000
    streams = []  # (type, bytes)

    module_names = []  # the name strings follow the module list inside the same stream
    for _, _, name in modules:
        raw = name.encode("utf-16le")
        module_names.append(struct.pack("<I", len(raw)) + raw + b"\0\0")

    thread_id, other_thread_id = 3544, 100
    exception = struct.pack("<II", thread_id, 0) + struct.pack(
        "<IIQQI", 0xC0000005, 0, 0, bases[fault_module] + fault_rva, len(parameters)) + struct.pack("<I", 0)
    exception += struct.pack("<15Q", *(list(parameters) + [0] * (15 - len(parameters)))) + struct.pack("<II", 0, 0)
    misc = struct.pack("<IIIIII", 24, 1, 1234, timestamp - uptime, 0, 0)
    threads = struct.pack("<I", 2) + b"\0" * 96
    start_ucrt = bases["ucrtbase.dll"] + 0x2CD00
    start_exe = bases["freddys-Win64-Shipping.exe"] + 0x34CE310
    # created, thread id, start address, user time. The game's main thread is the first one created.
    rows = [
        (1000, other_thread_id, start_exe, 1_635_000_000),
        (5000, thread_id, start_ucrt, 259_000_000)]
    if not worker_thread:
        rows = [(1000, thread_id, start_exe, 1_635_000_000), (5000, other_thread_id, start_ucrt, 259_000_000)]
    info_list = struct.pack("<III", 12, 64, len(rows))
    for created, tid, start, user in rows:
        info_list += struct.pack("<IIIIQQQQQQ", tid, 0, 0, 0, created, 0, 0, user, start, 0)

    stream_defs = [(4, None), (6, exception), (15, misc), (3, threads)]
    if with_thread_info:
        stream_defs.append((17, info_list))
    directory_size = 12 * len(stream_defs)
    cursor = 32 + directory_size

    module_list_size = 4 + 108 * len(modules)
    names_start = cursor + module_list_size
    name_rvas, position = [], names_start
    for raw in module_names:
        name_rvas.append(position)
        position += len(raw)
    module_list = struct.pack("<I", len(modules))
    for (base, size, _), name_rva in zip(modules, name_rvas):
        module_list += struct.pack("<QIIII", base, size, 0, 0, name_rva) + b"\0" * 84
    assert len(module_list) == module_list_size

    payloads = {4: module_list + b"".join(module_names)}
    for kind, content in stream_defs:
        if content is not None:
            payloads[kind] = content
    out_directory = b""
    data = b""
    for kind, _ in stream_defs:
        content = payloads[kind]
        out_directory += struct.pack("<III", kind, len(content), cursor + len(data))
        data += content
    header = struct.pack("<4sIIIIIQ", b"MDMP", 0xA793, len(stream_defs), 32, 0, timestamp, 0)
    return header + out_directory + data


class TestCrashReport(unittest.TestCase):
    def report(self, **kwargs):
        return crash_report.describe(crash_report.parse_minidump(build_dump(**kwargs)), "synthetic")

    def test_the_object_scan_crash_on_a_worker_thread(self):
        text = self.report(fault_module="UE4SS.dll", fault_rva=0x52DBB9)
        self.assertIn("UE4SS.dll+0x52dbb9", text)
        self.assertIn("read of address 0x18", text)
        self.assertIn("process uptime 787 s", text)
        self.assertIn("started at ucrtbase.dll+0x2cd00", text)
        self.assertIn("NOT the first thread", text)
        self.assertIn("object-array scan", text)

    def test_the_game_thread_is_recognised(self):
        text = self.report(fault_module="UE4SS.dll", fault_rva=0x3C4113, parameters=(0, 0xFFFFFFFE), worker_thread=False)
        self.assertIn("the game's first (main) thread", text)
        self.assertIn("FString:ToString", text)
        self.assertNotIn("a null pointer plus", text)  # 0xfffffffe is not a small offset

    def test_the_known_launch_crash_is_labelled_as_not_the_mods(self):
        text = self.report(fault_module="freddys-Win64-Shipping.exe", fault_rva=0x92D06F, parameters=(0, 0), uptime=5)
        self.assertIn("launch crash", text)
        self.assertIn("not caused by the mod", text)

    def test_an_unknown_signature_and_a_dump_without_thread_timing(self):
        text = self.report(fault_module="UE4SS.dll", fault_rva=0x1234, with_thread_info=False)
        self.assertIn("not seen before", text)
        self.assertIn("no thread timing", text)

    def test_an_empty_or_truncated_dump_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "crash_empty.dmp"
            empty.write_bytes(b"")
            output = io.StringIO()
            with redirect_stdout(output):
                crash_report.main([str(empty)])
        self.assertIn("cannot read", output.getvalue())

    def test_log_tail_splits_entries_that_joined_without_a_newline(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "UE4SS.log"
            log.write_text("[2026-10-04 21:55:52] [Lua] one[2026-10-04 21:55:53] [Lua] two\n[2026-10-04 21:55:54] [Lua] three\n",
                           encoding="utf-8")
            tail = crash_report.log_tail(str(log), 2)
            self.assertEqual(len(tail), 2)
            self.assertTrue(tail[0].endswith("] two") and tail[1].endswith("] three"), tail)

    def test_main_reads_a_dump_and_the_log_from_a_win64_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "crash_2026_10_04_21_57_18.dmp").write_bytes(build_dump("UE4SS.dll", 0x52DBB9))
            (Path(tmp) / "UE4SS.log").write_text("[2026-10-04 21:57:16] [Lua] [DIAG] map: 'A' -> 'B' (up 700s)\n", encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(crash_report.main(["--win64", tmp]), 0)
        text = output.getvalue()
        self.assertIn("crash_2026_10_04_21_57_18.dmp", text)
        self.assertIn("[DIAG] map: 'A' -> 'B'", text)


if __name__ == "__main__":
    unittest.main()
