import json
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
    BridgeIO,
    BridgeState,
    format_applied_items_line,
)
from tests.localappdata_isolation import isolate_localappdata


def _item(item_id):
    return {"item": item_id, "location": 1, "player": 1, "flags": 0}


class _ClientCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="fnafhw_items_"))
        isolate_localappdata(self, self.temp_dir)
        self.bridge_dir = self.temp_dir / "bridge"
        self.bridge_dir.mkdir()
        shutil.copy(project_root / "ue4ss_mod" / "FNAFHWArchipelago" / "locations.json", self.bridge_dir / "locations.json")
        self.client = self._new_client()

    async def asyncTearDown(self):
        for c in getattr(self, "_clients", []):
            c.release_single_instance_lock()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _new_client(self):
        client = APBridgeClient(self.bridge_dir)
        client.current_seed_name = "ItemSeed"
        client.slot = "ItemSlot"
        self._clients = getattr(self, "_clients", []) + [client]
        return client

    def _inbox(self):
        return self.bridge_dir.joinpath("ap_inbox.txt").read_text(encoding="utf-8").splitlines()

    def _lines(self, prefix):
        return [l for l in self._inbox() if l == prefix or l.startswith(prefix + " ")]

    def _connect(self, client=None):
        (client or self.client)._on_connected({"cmd": "Connected", "checked_locations": []})


class TestAppliedCountPersistence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="fnafhw_applied_"))
        self.bridge = BridgeIO(self.temp_dir / "bridge")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_round_trip(self):
        state = BridgeState(session_id="S_A", seed_name="S", slot="A", next_item_index=5, applied_item_count=3)
        self.bridge.save_session(state)
        self.assertEqual(self.bridge.load_session("S_A").applied_item_count, 3)

    def test_legacy_session_without_the_field_starts_from_next_item_index(self):
        path = self.bridge.get_session_path("S_OLD")
        path.write_text(json.dumps({"session_id": "S_OLD", "next_item_index": 5}), encoding="utf-8")
        self.assertEqual(self.bridge.load_session("S_OLD").applied_item_count, 5)

    def test_legacy_ap_state_without_the_field_starts_from_next_item_index(self):
        self.bridge.state_path.write_text(json.dumps({"session_id": "S_OLD", "next_item_index": 4}), encoding="utf-8")
        self.assertEqual(self.bridge.load_state().applied_item_count, 4)

    def test_new_state_defaults_to_zero(self):
        self.assertEqual(BridgeState().applied_item_count, 0)

    def test_format_line(self):
        self.assertEqual(format_applied_items_line(3), "APPLIED_ITEMS 3")
        self.assertEqual(format_applied_items_line(1, reset=True), "APPLIED_ITEMS 1 reset")


class TestConnectAnnouncesAppliedCount(_ClientCase):
    async def test_new_session_announces_zero_before_the_empty_snapshot(self):
        self._connect()
        lines = self._inbox()
        applied_idx = lines.index("APPLIED_ITEMS 0")
        self.assertEqual(lines[applied_idx + 1], "RECEIVED_SNAPSHOT")

    async def test_resumed_session_keeps_its_applied_count(self):
        # regression: the resume path rebuilds BridgeState field by field; losing the count would
        # make the game re-apply every one-shot item on each reconnect
        self._connect()
        self.client.state.applied_item_count = 3
        self.client.bridge.save_session(self.client.state)
        self.client.release_single_instance_lock()

        second = self._new_client()
        self._connect(second)
        self.assertEqual(second.state.applied_item_count, 3)
        self.assertEqual(self._lines("APPLIED_ITEMS")[-1], "APPLIED_ITEMS 3")


class TestReceivedItemsAnnounceAppliedCount(_ClientCase):
    async def test_applied_line_precedes_the_snapshot(self):
        self._connect()
        self.client.state.applied_item_count = 1
        self.client._on_received_items({"index": 0, "items": [_item(10), _item(11), _item(12)]})
        lines = self._inbox()
        snap_idx = max(i for i, l in enumerate(lines) if l.startswith("RECEIVED_SNAPSHOT "))
        self.assertEqual(lines[snap_idx - 1], "APPLIED_ITEMS 1")
        self.assertEqual(lines[snap_idx], "RECEIVED_SNAPSHOT 10,11,12")

    async def test_applied_count_above_the_server_list_is_clamped_and_persisted(self):
        self._connect()
        self.client.state.applied_item_count = 5  # e.g. the room was restarted and its list is shorter
        self.client._on_received_items({"index": 0, "items": [_item(10)]})
        self.assertEqual(self.client.state.applied_item_count, 1)
        self.assertEqual(self._lines("APPLIED_ITEMS")[-1], "APPLIED_ITEMS 1 reset")
        persisted = self.client.bridge.load_session(self.client.state.session_id)
        self.assertEqual(persisted.applied_item_count, 1)

    async def test_items_below_the_applied_count_are_not_offered_again(self):
        self._connect()
        self.client.state.applied_item_count = 2
        self.client._on_received_items({"index": 0, "items": [_item(10), _item(11), _item(12)]})
        self.assertEqual(self.client.state.applied_item_count, 2)  # unchanged: nothing to clamp


class TestItemsAppliedCommand(_ClientCase):
    async def _prime(self, n_items=4):
        self._connect()
        self.client._on_received_items({"index": 0, "items": [_item(10 + i) for i in range(n_items)]})

    async def test_ack_advances_persists_and_echoes(self):
        await self._prime()
        await self.client._execute_command("ITEMS_APPLIED 3")
        self.assertEqual(self.client.state.applied_item_count, 3)
        self.assertEqual(self.client.bridge.load_session(self.client.state.session_id).applied_item_count, 3)
        self.assertEqual(self._lines("APPLIED_ITEMS")[-1], "APPLIED_ITEMS 3")

    async def test_ack_never_moves_backwards(self):
        await self._prime()
        await self.client._execute_command("ITEMS_APPLIED 3")
        await self.client._execute_command("ITEMS_APPLIED 1")
        self.assertEqual(self.client.state.applied_item_count, 3)

    async def test_ack_before_the_item_list_is_known_is_kept(self):
        # the game may ack while the client was down or still connecting
        self._connect()
        await self.client._execute_command("ITEMS_APPLIED 3")
        self.assertEqual(self.client.state.applied_item_count, 3)

    async def test_ack_above_the_real_list_is_clamped_when_the_list_arrives(self):
        self._connect()
        await self.client._execute_command("ITEMS_APPLIED 9")
        self.client._on_received_items({"index": 0, "items": [_item(10), _item(11)]})
        self.assertEqual(self.client.state.applied_item_count, 2)
        self.assertEqual(self._lines("APPLIED_ITEMS")[-1], "APPLIED_ITEMS 2 reset")

    async def test_malformed_ack_is_ignored(self):
        await self._prime()
        for bad in ("", "abc", "-"):
            await self.client._execute_command(f"ITEMS_APPLIED {bad}".strip())
        self.assertEqual(self.client.state.applied_item_count, 0)

    async def test_ack_survives_a_client_restart(self):
        await self._prime()
        await self.client._execute_command("ITEMS_APPLIED 4")
        self.client.release_single_instance_lock()
        second = self._new_client()
        self._connect(second)
        self.assertEqual(second.state.applied_item_count, 4)


if __name__ == "__main__":
    unittest.main()
