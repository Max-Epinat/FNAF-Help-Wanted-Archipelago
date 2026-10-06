"""BridgeCore is the transport-independent client logic. These tests drive it directly: no sockets, no private save
files (a fake save reader is injected), and a temp bridge folder with LOCALAPPDATA redirected.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ap_client.bridge_core import STATUS_CONNECTED, BridgeCore, InstanceLock, SaveAPI
from tests.localappdata_isolation import isolate_localappdata


class FakeSaveAPI(SaveAPI):
    def __init__(self, sav_path: Path):
        self.sav_path = sav_path
        self.earned: list[str] = []
        self.clean_calls = 0

    def parse(self, data):
        return data

    def extract_earned(self, parsed):
        return list(self.earned)

    def archipelago_save_path(self):
        return self.sav_path

    def ensure_clean_save(self):
        self.clean_calls += 1
        self.sav_path.write_bytes(b"clean")


class CoreTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="fnafhw_core_"))
        isolate_localappdata(self, self.temp)
        self.bridge_dir = self.temp / "bridge"
        self.sav = self.temp / "Playerarchi.sav"
        self.sav.write_bytes(b"x")
        self.save_api = FakeSaveAPI(self.sav)
        self.core = BridgeCore(self.bridge_dir, save_api=self.save_api)
        self.core.location_name_to_id = {"Beat FNAF 1 - Night 1": 101, "Beat FNAF 1 - Night 2": 102}
        self.core.location_id_to_name = {101: "Beat FNAF 1 - Night 1", 102: "Beat FNAF 1 - Night 2"}
        self.core.slot = "HWtest"
        self.core.current_seed_name = "SeedX"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp, ignore_errors=True)

    def inbox(self):
        return self.core.bridge.inbox_path.read_text(encoding="utf-8").splitlines()

    def connect(self, checked=(), slot_data=None):
        return self.core.on_connected({"cmd": "Connected", "checked_locations": list(checked), "slot_data": slot_data or {}})


class TestCoreIsTransportFree(unittest.TestCase):
    def test_imports_without_websockets_tkinter_or_archipelago(self):
        code = (
            "import sys\n"
            "for name in ('websockets', 'tkinter', 'BaseClasses', 'CommonClient', 'worlds'):\n"
            "    sys.modules[name] = None\n"  # makes any import of them raise ImportError
            f"sys.path.insert(0, {str(project_root)!r})\n"
            "import ap_client.bridge_core as core\n"
            "print(core.BridgeCore.__name__)\n"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "BridgeCore")


class TestConnect(CoreTestCase):
    def test_new_session_creates_a_clean_save_and_tells_the_game(self):
        outgoing = self.connect(slot_data={
            "level_gates": {"4": "FNAF1"}, "gate_items": {"101000002": "FNAF1"},
        })
        self.assertEqual(outgoing, [])
        self.assertEqual(self.save_api.clean_calls, 1)
        self.assertEqual(self.core.status, STATUS_CONNECTED)
        lines = self.inbox()
        self.assertIn("SESSION_SYNC SeedX_HWtest", lines)
        for expected in ("GATE_TABLE 4=FNAF1", "GATE_ITEMS 101000002=FNAF1", "APPLIED_ITEMS 0", "RECEIVED_SNAPSHOT"):
            self.assertIn(expected, lines)
        # order matters: session first, then table, items, applied count, empty snapshot
        self.assertLess(lines.index("SESSION_SYNC SeedX_HWtest"), lines.index("GATE_TABLE 4=FNAF1"))
        self.assertLess(lines.index("GATE_TABLE 4=FNAF1"), lines.index("GATE_ITEMS 101000002=FNAF1"))

    def test_resumed_session_does_not_recreate_the_save_and_server_is_authoritative(self):
        self.connect()
        self.core.state.checked_locations.update({101, 102})  # local belief
        self.core._save_state()
        self.connect(checked=[101])  # the server only knows 101
        self.assertEqual(self.save_api.clean_calls, 1)  # not recreated on resume
        self.assertEqual(self.core.state.checked_locations, {101})

    def test_pending_checks_are_returned_for_the_transport_to_flush(self):
        self.connect()
        self.core.state.pending_locations.add(102)
        self.core._save_state()
        outgoing = self.connect()
        self.assertEqual(outgoing, [{"cmd": "LocationChecks", "locations": [102]}])

    def test_baseline_is_the_earned_set_at_connect(self):
        self.save_api.earned = ["Beat FNAF 1 - Night 1"]
        self.connect()
        self.assertEqual(self.core.state.savegame_baseline, {"Beat FNAF 1 - Night 1"})


class TestCommands(CoreTestCase):
    def test_offline_commands_send_nothing(self):
        for cmd, arg in (("GOAL", ""), ("SAY", "hi"), ("SYNC", ""), ("DEATHLINK", "x")):
            self.assertEqual(self.core.game_command_packets(cmd, arg), [], cmd)

    def test_connected_commands_return_packets(self):
        self.connect()
        self.assertEqual(self.core.game_command_packets("GOAL", ""), [{"cmd": "StatusUpdate", "status": 30}])
        self.assertEqual(self.core.game_command_packets("SAY", "hi"), [{"cmd": "Say", "text": "hi"}])
        self.assertEqual(self.core.game_command_packets("SYNC", ""), [{"cmd": "Sync"}])
        self.assertEqual(self.core.game_command_packets("DEATHLINK", "boom"), [])  # DeathLink is off unless the slot enabled it
        self.assertEqual(self.core.game_command_packets("SAY", ""), [])  # empty chat is dropped

    def test_location_check_by_id_and_name(self):
        self.connect()
        self.assertEqual(self.core.game_command_packets("LOCATION_CHECK", "101"), [{"cmd": "LocationChecks", "locations": [101]}])
        self.assertEqual(self.core.game_command_packets("LOCATION_CHECK_NAME", "Beat FNAF 1 - Night 2"),
                         [{"cmd": "LocationChecks", "locations": [102]}])
        self.assertIn(101, self.core.state.pending_locations)

    def test_already_confirmed_check_is_not_resent(self):
        self.connect(checked=[101])
        self.assertEqual(self.core.game_command_packets("LOCATION_CHECK", "101"), [])
        self.assertIn("PRINT Location already checked: Beat FNAF 1 - Night 1", self.inbox())

    def test_check_is_queued_when_the_transport_cannot_send(self):
        self.connect()
        self.core.can_send = lambda: False
        self.assertEqual(self.core.game_command_packets("LOCATION_CHECK", "102"), [])
        self.assertIn(102, self.core.state.pending_locations)
        self.assertIn("PRINT Queued check (offline): Beat FNAF 1 - Night 2 (102)", self.inbox())

    def test_unknown_and_invalid_locations_are_reported_to_the_game(self):
        self.connect()
        self.assertEqual(self.core.game_command_packets("LOCATION_CHECK", "abc"), [])
        self.assertEqual(self.core.game_command_packets("LOCATION_CHECK_NAME", "No such level"), [])
        self.assertIn("PRINT Invalid location ID: abc", self.inbox())
        self.assertIn("PRINT Unknown location name: No such level", self.inbox())

    def test_items_applied_only_moves_forward_and_is_echoed(self):
        self.connect()
        self.core.game_command_packets("ITEMS_APPLIED", "3")
        self.core.game_command_packets("ITEMS_APPLIED", "2")
        self.core.game_command_packets("ITEMS_APPLIED", "junk")
        self.assertEqual(self.core.state.applied_item_count, 3)
        self.assertEqual(self.inbox().count("APPLIED_ITEMS 3"), 1)


class TestReceivedItems(CoreTestCase):
    def test_snapshot_and_items_are_forwarded_and_server_list_clamps_the_applied_count(self):
        self.connect()
        self.core.state.applied_item_count = 5
        self.core.on_received_items({"index": 0, "items": [{"item": 101000002, "player": 1, "location": -2, "flags": 0}]})
        lines = self.inbox()
        self.assertIn("ITEM 101000002 1 -2 0 0", lines)
        self.assertIn("APPLIED_ITEMS 1 reset", lines)
        self.assertEqual([l for l in lines if l.startswith("RECEIVED_SNAPSHOT")][-1], "RECEIVED_SNAPSHOT 101000002")
        self.assertEqual(self.core.state.applied_item_count, 1)
        self.assertEqual(self.core.state.next_item_index, 1)

    def test_already_delivered_indexes_are_not_sent_as_items_again(self):
        self.connect()
        packet = {"index": 0, "items": [{"item": 7, "player": 1, "location": 1, "flags": 0}]}
        self.core.on_received_items(packet)
        self.core.on_received_items(packet)
        self.assertEqual(sum(1 for l in self.inbox() if l.startswith("ITEM 7 ")), 1)


class TestSavePolling(CoreTestCase):
    def poll(self):
        self.core._last_sav_poll_time = 0.0
        self.core._last_sav_mtime = 0.0
        return self.core.collect_savegame_packets()

    def test_baseline_is_never_sent_and_new_progress_is_sent_once(self):
        self.save_api.earned = ["Beat FNAF 1 - Night 1"]
        self.connect()
        self.assertEqual(self.poll(), [])  # in the baseline
        self.save_api.earned = ["Beat FNAF 1 - Night 1", "Beat FNAF 1 - Night 2"]
        self.assertEqual(self.poll(), [{"cmd": "LocationChecks", "locations": [102]}])
        self.assertIn(102, self.core.state.pending_locations)

    def test_confirmed_locations_are_not_resent(self):
        self.connect(checked=[102])
        self.save_api.earned = ["Beat FNAF 1 - Night 2"]
        self.assertEqual(self.poll(), [])

    def test_progress_is_kept_pending_when_the_transport_cannot_send(self):
        self.connect()
        self.core.can_send = lambda: False
        self.save_api.earned = ["Beat FNAF 1 - Night 2"]
        self.assertEqual(self.poll(), [])
        self.assertIn(102, self.core.state.pending_locations)

    def test_nothing_is_read_while_disconnected(self):
        self.save_api.earned = ["Beat FNAF 1 - Night 2"]
        self.assertEqual(self.poll(), [])  # status is not CONNECTED yet


class TestPacketsFromTheServer(CoreTestCase):
    def test_connect_packet(self):
        packet = self.core.build_connect_packet("uuid-1")
        self.assertEqual((packet["cmd"], packet["name"], packet["uuid"], packet["items_handling"], packet["slot_data"]),
                         ("Connect", "HWtest", "uuid-1", 7, True))

    def test_print_reaches_the_game(self):
        self.core.on_print({"data": [{"text": "Hello "}, {"text": "world"}]})
        self.assertIn("PRINT Hello world", self.inbox())

    def test_room_update_confirms_checks(self):
        self.connect()
        self.core.state.pending_locations.add(101)
        self.core.on_room_update({"checked_locations": [101]})
        self.assertIn(101, self.core.state.checked_locations)
        self.assertNotIn(101, self.core.state.pending_locations)
        self.assertIn("CONFIRMED_CHECK 101 Beat FNAF 1 - Night 1", self.inbox())

    def test_connection_refused_sets_error_and_requests_disconnect(self):
        self.core.on_connection_refused({"errors": ["InvalidSlot"]})
        self.assertTrue(self.core.disconnect_requested)
        self.assertEqual(self.core.last_error, "InvalidSlot")


class TestDeathLink(CoreTestCase):
    def enable(self):
        return self.connect(slot_data={"death_link": True})

    def test_off_by_default_nothing_is_subscribed_sent_or_forwarded(self):
        outgoing = self.connect()
        self.assertEqual(outgoing, [])  # no ConnectUpdate: the DeathLink tag is not requested
        self.assertIn("DEATH_LINK_MODE 0", self.inbox())
        self.assertFalse(self.core.death_link_enabled)
        self.core.on_bounced({"tags": ["DeathLink"], "data": {"source": "Bob", "cause": "fell", "time": 1.0}})
        self.assertFalse(any(line.startswith("DEATHLINK") for line in self.inbox()))
        self.assertEqual(self.core.game_command_packets("DEATHLINK", "boom"), [])

    def test_enabled_subscribes_to_the_tag_and_tells_the_game(self):
        outgoing = self.enable()
        self.assertIn({"cmd": "ConnectUpdate", "tags": ["AP", "DeathLink"]}, outgoing)
        self.assertIn("DEATH_LINK_MODE 1", self.inbox())

    def test_a_death_from_the_game_becomes_a_bounce(self):
        self.enable()
        bounce = self.core.game_command_packets("DEATHLINK", "boom")[0]
        self.assertEqual((bounce["cmd"], bounce["tags"]), ("Bounce", ["DeathLink"]))
        self.assertEqual((bounce["data"]["source"], bounce["data"]["cause"]), ("HWtest", "boom"))
        self.assertIsInstance(bounce["data"]["time"], float)

    def test_not_sent_while_the_transport_cannot_send(self):
        self.enable()
        self.core.can_send = lambda: False
        self.assertEqual(self.core.game_command_packets("DEATHLINK", "boom"), [])

    def test_a_death_from_someone_else_reaches_the_game_once(self):
        self.enable()
        packet = {"tags": ["DeathLink"], "data": {"source": "Bob", "cause": "fell" + chr(10) + "into a pit", "time": 5.0}}
        self.core.on_bounced(packet)
        self.core.on_bounced(packet)  # the same death delivered twice
        self.assertEqual([l for l in self.inbox() if l.startswith("DEATHLINK")], ["DEATHLINK Bob::fell into a pit"])

    def test_our_own_death_bounced_back_is_ignored(self):
        self.enable()
        sent = self.core.game_command_packets("DEATHLINK", "boom")[0]
        self.core.on_bounced({"tags": ["DeathLink"], "data": sent["data"]})  # same source and time
        self.core.on_bounced({"tags": ["DeathLink"], "data": {"source": "HWtest", "cause": "x", "time": 99.0}})  # same source
        self.assertFalse(any(l.startswith("DEATHLINK") for l in self.inbox()))

    def test_other_bounces_are_ignored(self):
        self.enable()
        self.core.on_bounced({"tags": ["SomethingElse"], "data": {"source": "Bob", "time": 1.0}})
        self.assertFalse(any(l.startswith("DEATHLINK") for l in self.inbox()))

    def test_reconnecting_to_a_slot_without_deathlink_turns_it_off(self):
        self.enable()
        self.assertTrue(self.core.death_link_enabled)
        self.connect()
        self.assertFalse(self.core.death_link_enabled)
        self.assertEqual([l for l in self.inbox() if l.startswith("DEATH_LINK_MODE")][-1], "DEATH_LINK_MODE 0")


class TestDeathLinkGiftBox(CoreTestCase):
    """`death_link_gift_box` (slot_data) is forwarded to the mod as DEATH_LINK_GIFT_BOX 1|0, right after DEATH_LINK_MODE, at every connect."""

    def gift_line(self):
        return [line for line in self.inbox() if line.startswith("DEATH_LINK_GIFT_BOX")]

    def test_the_value_of_the_slot_is_forwarded(self):
        self.connect(slot_data={"death_link": True, "death_link_gift_box": False})
        self.assertEqual(self.gift_line(), ["DEATH_LINK_GIFT_BOX 0"])
        self.connect(slot_data={"death_link": True, "death_link_gift_box": True})
        self.assertEqual(self.gift_line()[-1], "DEATH_LINK_GIFT_BOX 1")

    def test_a_room_made_before_the_option_existed_keeps_sending(self):
        self.connect(slot_data={"death_link": True})
        self.assertEqual(self.gift_line(), ["DEATH_LINK_GIFT_BOX 1"])
        self.connect()
        self.assertEqual(self.gift_line()[-1], "DEATH_LINK_GIFT_BOX 1")

    def test_it_follows_deathlink_mode_in_the_connect_block(self):
        self.connect(slot_data={"death_link": True, "death_link_gift_box": False})
        lines = self.inbox()
        mode = lines.index("DEATH_LINK_MODE 1")
        self.assertEqual(lines[mode + 1], "DEATH_LINK_GIFT_BOX 0")

    def test_it_does_not_turn_deathlink_on_or_change_what_is_subscribed(self):
        outgoing = self.connect(slot_data={"death_link": False, "death_link_gift_box": False})
        self.assertEqual(outgoing, [])
        self.assertFalse(self.core.death_link_enabled)
        self.assertIn("DEATH_LINK_MODE 0", self.inbox())
        self.assertEqual(self.core.game_command_packets("DEATHLINK", "boom"), [])

    def test_sending_a_death_from_the_game_is_unchanged(self):
        self.connect(slot_data={"death_link": True, "death_link_gift_box": False})
        self.assertEqual(self.core.game_command_packets("DEATHLINK", "boom")[0]["cmd"], "Bounce")  # the mod decides what it reports
class TestStandaloneEntryPoint(unittest.TestCase):
    def test_without_a_bridge_folder_it_exits_with_instructions_and_creates_nothing(self):
        import ap_client.main as standalone

        original = standalone.find_bridge_dir
        standalone.find_bridge_dir = lambda *a, **k: None
        try:
            with self.assertRaises(SystemExit) as raised:
                standalone.main()
        finally:
            standalone.find_bridge_dir = original
        self.assertEqual(raised.exception.code, 1)


class TestInstanceLock(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="fnafhw_lock_"))
        self.path = self.dir / "ap_client.lock"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_acquire_writes_our_pid_and_release_removes_the_file(self):
        lock = InstanceLock(self.path)
        lock.acquire()
        self.assertTrue(lock.acquired)
        self.assertEqual(self.path.read_text(encoding="utf-8"), str(os.getpid()))
        lock.release()
        self.assertFalse(self.path.exists())
        self.assertFalse(lock.acquired)

    def test_a_second_client_is_refused_while_the_owner_is_alive(self):
        first = InstanceLock(self.path)
        first.acquire()
        try:
            with self.assertRaises(RuntimeError):
                InstanceLock(self.path).acquire()
            self.assertEqual(self.path.read_text(encoding="utf-8"), str(os.getpid()))  # still the first owner
        finally:
            first.release()

    def test_a_stale_lock_of_a_dead_process_is_cleared(self):
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        self.path.write_text(str(proc.pid), encoding="utf-8")  # that process has exited
        lock = InstanceLock(self.path)
        lock.acquire()
        self.assertEqual(self.path.read_text(encoding="utf-8"), str(os.getpid()))
        lock.release()

    def test_garbage_lock_file_is_treated_as_stale(self):
        self.path.write_text("not a pid", encoding="utf-8")
        lock = InstanceLock(self.path)
        lock.acquire()
        self.assertTrue(lock.acquired)
        lock.release()

    def test_release_without_acquire_does_not_delete_someone_elses_lock(self):
        self.path.write_text(str(os.getpid()), encoding="utf-8")
        InstanceLock(self.path).release()
        self.assertTrue(self.path.exists())


if __name__ == "__main__":
    unittest.main()
