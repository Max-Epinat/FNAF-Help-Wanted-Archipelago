import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ap_client.main import (
    APBridgeClient,
    format_gate_items_line,
    format_gate_table_line,
    format_items_snapshot_line,
)


class TestFormatGateTableLine(unittest.TestCase):
    def test_valid_table_is_sorted_and_formatted(self):
        line = format_gate_table_line({"6": "FNAF1_NIGHT3", "5": "FNAF1_NIGHT2"})
        self.assertEqual(line, "GATE_TABLE 5=FNAF1_NIGHT2,6=FNAF1_NIGHT3")

    def test_missing_or_empty_table_gives_none(self):
        for value in (None, {}, [], "5=FNAF1_NIGHT2"):
            self.assertIsNone(format_gate_table_line(value))

    def test_invalid_entries_are_dropped_not_forwarded(self):
        line = format_gate_table_line({"5": "FNAF1_NIGHT2", "x": "OK_GATE", "7": "bad id", "8": 3})
        self.assertEqual(line, "GATE_TABLE 5=FNAF1_NIGHT2")

    def test_all_invalid_gives_none(self):
        self.assertIsNone(format_gate_table_line({"x": "A", "7": "lower"}))


class TestClientForwardsGateTable(unittest.TestCase):
    """_on_connected archives/creates Playerarchi.sav under %LOCALAPPDATA%: redirect it to a temp dir."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="fnafhw_gate_"))
        self.bridge_dir = self.temp_dir / "bridge"
        self.bridge_dir.mkdir(parents=True)
        shutil.copy(project_root / "ue4ss_mod" / "FNAFHWArchipelago" / "locations.json", self.bridge_dir / "locations.json")
        self._orig_localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = str(self.temp_dir / "localappdata")
        self.client = APBridgeClient(self.bridge_dir)
        self.client.current_seed_name = "GateSeed"
        self.client.slot = "GateSlot"

    def tearDown(self):
        self.client.release_single_instance_lock()
        if self._orig_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._orig_localappdata
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _inbox(self):
        return self.bridge_dir.joinpath("ap_inbox.txt").read_text(encoding="utf-8").splitlines()

    def _connect(self, **packet_extra):
        self.client._on_connected({"cmd": "Connected", "checked_locations": [], **packet_extra})

    def test_gate_table_follows_session_sync(self):
        self._connect(slot_data={"level_gates": {"5": "FNAF1_NIGHT2"}})
        lines = self._inbox()
        sync_idx = next(i for i, l in enumerate(lines) if l.startswith("SESSION_SYNC "))
        gate_idx = next(i for i, l in enumerate(lines) if l.startswith("GATE_TABLE "))
        self.assertGreater(gate_idx, sync_idx)
        self.assertEqual(lines[gate_idx], "GATE_TABLE 5=FNAF1_NIGHT2")

    def test_no_level_gates_sends_no_table(self):
        self._connect(slot_data={"goal": 0})
        self.assertFalse(any(l.startswith("GATE_TABLE") for l in self._inbox()))

    def test_no_slot_data_at_all_still_connects(self):
        self._connect()
        self.assertTrue(any(l.startswith("SESSION_SYNC ") for l in self._inbox()))
        self.assertFalse(any(l.startswith("GATE_TABLE") for l in self._inbox()))

    def test_gate_items_forwarded_after_gate_table(self):
        self._connect(slot_data={"level_gates": {"5": "FNAF1_NIGHT2"}, "gate_items": {"101000050": "FNAF1_NIGHT2"}})
        lines = self._inbox()
        table_idx = next(i for i, l in enumerate(lines) if l.startswith("GATE_TABLE "))
        items_idx = next(i for i, l in enumerate(lines) if l.startswith("GATE_ITEMS "))
        self.assertGreater(items_idx, table_idx)
        self.assertEqual(lines[items_idx], "GATE_ITEMS 101000050=FNAF1_NIGHT2")

    def test_no_gate_items_sends_no_map(self):
        self._connect(slot_data={"level_gates": {"5": "FNAF1_NIGHT2"}})
        self.assertFalse(any(l.startswith("GATE_ITEMS") for l in self._inbox()))

    def test_connect_starts_from_an_empty_snapshot_after_the_gate_lines(self):
        # a server with no items sends no ReceivedItems, so connect itself must reset authorization
        self._connect(slot_data={"level_gates": {"5": "FNAF1_NIGHT2"}, "gate_items": {"101000050": "FNAF1_NIGHT2"}})
        lines = self._inbox()
        items_idx = next(i for i, l in enumerate(lines) if l.startswith("GATE_ITEMS "))
        snap_idx = next(i for i, l in enumerate(lines) if l == "RECEIVED_SNAPSHOT")
        self.assertGreater(snap_idx, items_idx)

    def test_connect_without_slot_data_still_sends_empty_snapshot(self):
        self._connect()
        self.assertIn("RECEIVED_SNAPSHOT", self._inbox())

    def test_connect_clears_previous_connection_items(self):
        self.client._on_received_items({"index": 0, "items": [{"item": 10, "location": 1, "player": 1, "flags": 0}]})
        self._connect()
        # a later ReceivedItems(index 0) must not be merged with the previous connection's list
        self.client._on_received_items({"index": 0, "items": [{"item": 20, "location": 1, "player": 1, "flags": 0}]})
        self.assertEqual([l for l in self._inbox() if l.startswith("RECEIVED_SNAPSHOT")][-1], "RECEIVED_SNAPSHOT 20")

    def test_malformed_level_gates_does_not_break_connect(self):
        self._connect(slot_data={"level_gates": "garbage"})
        self.assertTrue(any(l.startswith("SESSION_SYNC ") for l in self._inbox()))
        self.assertFalse(any(l.startswith("GATE_TABLE") for l in self._inbox()))


class TestFormatGateItemsLines(unittest.TestCase):
    def test_gate_items_sorted_and_formatted(self):
        line = format_gate_items_line({"101000051": "FNAF1_NIGHT3", "101000050": "FNAF1_NIGHT2"})
        self.assertEqual(line, "GATE_ITEMS 101000050=FNAF1_NIGHT2,101000051=FNAF1_NIGHT3")

    def test_gate_items_missing_or_invalid(self):
        for value in (None, {}, "x"):
            self.assertIsNone(format_gate_items_line(value))
        self.assertEqual(
            format_gate_items_line({"101000050": "FNAF1_NIGHT2", "abc": "G", "5": "bad id"}),
            "GATE_ITEMS 101000050=FNAF1_NIGHT2",
        )

    def test_snapshot_line(self):
        self.assertEqual(format_items_snapshot_line([101000002, 101000011]), "RECEIVED_SNAPSHOT 101000002,101000011")
        self.assertEqual(format_items_snapshot_line([]).strip(), "RECEIVED_SNAPSHOT")

    def test_snapshot_prefix_does_not_collide_with_item_lines(self):
        # the Lua ITEM handler matches by 4-char prefix; the snapshot line must not start with it
        self.assertFalse(format_items_snapshot_line([1]).startswith("ITEM"))


def _item(item_id, location=1, player=1):
    return {"item": item_id, "location": location, "player": player, "flags": 0}


class TestReceivedItemsSnapshot(unittest.TestCase):
    """The snapshot is rebuilt from the server's full list; it must not depend on next_item_index."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="fnafhw_snap_"))
        self.bridge_dir = self.temp_dir / "bridge"
        self.bridge_dir.mkdir(parents=True)
        shutil.copy(project_root / "ue4ss_mod" / "FNAFHWArchipelago" / "locations.json", self.bridge_dir / "locations.json")
        self._orig_localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = str(self.temp_dir / "localappdata")
        self.client = APBridgeClient(self.bridge_dir)

    def tearDown(self):
        self.client.release_single_instance_lock()
        if self._orig_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._orig_localappdata
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _lines(self, prefix):
        text = self.bridge_dir.joinpath("ap_inbox.txt").read_text(encoding="utf-8").splitlines()
        return [l for l in text if l == prefix or l.startswith(prefix + " ")]

    def test_snapshot_includes_items_below_next_item_index(self):
        self.client.state.next_item_index = 3  # items 0..2 were already delivered in an earlier run
        self.client._on_received_items({"index": 0, "items": [_item(10), _item(11), _item(12), _item(13), _item(14)]})
        self.assertEqual(self._lines("RECEIVED_SNAPSHOT"), ["RECEIVED_SNAPSHOT 10,11,12,13,14"])
        # one-shot ITEM lines keep their old behaviour: only the new indexes 3 and 4
        self.assertEqual([l.split()[1] for l in self._lines("ITEM")], ["13", "14"])
        self.assertEqual(self.client.state.next_item_index, 5)

    def test_incremental_packet_extends_the_snapshot(self):
        self.client._on_received_items({"index": 0, "items": [_item(10), _item(11)]})
        self.client._on_received_items({"index": 2, "items": [_item(12)]})
        self.assertEqual(self._lines("RECEIVED_SNAPSHOT")[-1], "RECEIVED_SNAPSHOT 10,11,12")

    def test_replaying_the_same_list_is_idempotent(self):
        packet = {"index": 0, "items": [_item(10), _item(11)]}
        self.client._on_received_items(packet)
        self.client._on_received_items(packet)
        snaps = self._lines("RECEIVED_SNAPSHOT")
        self.assertEqual(snaps, ["RECEIVED_SNAPSHOT 10,11", "RECEIVED_SNAPSHOT 10,11"])
        # and the one-shot ITEM lines are not duplicated by the replay
        self.assertEqual(len(self._lines("ITEM")), 2)

    def test_new_connection_rebuilds_from_index_zero(self):
        self.client._on_received_items({"index": 0, "items": [_item(10), _item(11), _item(12)]})
        self.client._on_received_items({"index": 0, "items": [_item(20)]})  # e.g. a different slot/seed
        self.assertEqual(self._lines("RECEIVED_SNAPSHOT")[-1], "RECEIVED_SNAPSHOT 20")

    def test_empty_first_packet_sends_an_empty_snapshot(self):
        self.client._on_received_items({"index": 0, "items": []})
        self.assertEqual(self._lines("RECEIVED_SNAPSHOT"), ["RECEIVED_SNAPSHOT"])

    def test_gap_sends_no_snapshot(self):
        self.client._on_received_items({"index": 3, "items": [_item(13)]})  # never saw 0..2
        self.assertEqual(self._lines("RECEIVED_SNAPSHOT"), [])


if __name__ == "__main__":
    unittest.main()
