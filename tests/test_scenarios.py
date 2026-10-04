import asyncio
import json
import shutil
import tempfile
import unittest
from pathlib import Path

# Add project root to sys.path
import sys
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tests.localappdata_isolation import isolate_localappdata
from ap_client.main import BridgeIO, BridgeState, APBridgeClient
from ap_client.save_reader import parse_gvas_save, extract_earned_locations
from tests.gvas_fixtures import completed_template


class TestSessionScoping(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="fnafhw_test_"))
        self.bridge_dir = self.temp_dir / "bridge"
        self.bridge_dir.mkdir(parents=True, exist_ok=True)
        self.bridge = BridgeIO(self.bridge_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_bridge_session_persistence_and_isolation(self):
        """Verify BridgeIO creates separate session files and keeps state strictly isolated."""
        session_a = "SeedAlpha_Player1"
        session_b = "SeedBeta_Player1"

        state_a = BridgeState(
            session_id=session_a,
            seed_name="SeedAlpha",
            slot="Player1",
            checked_locations={101100010, 101100011},
            pending_locations=set(),
            next_item_index=3,
            outbox_position=100,
            savegame_baseline={"Beat FNAF 1 - Night 1"}
        )
        self.bridge.save_session(state_a)

        # File for session A must exist
        path_a = self.bridge.get_session_path(session_a)
        self.assertTrue(path_a.exists(), f"Expected session file at {path_a}")

        # Loading session A must return its exact state
        loaded_a = self.bridge.load_session(session_a)
        self.assertIsNotNone(loaded_a)
        self.assertEqual(loaded_a.checked_locations, {101100010, 101100011})
        self.assertEqual(loaded_a.next_item_index, 3)
        self.assertEqual(loaded_a.savegame_baseline, {"Beat FNAF 1 - Night 1"})

        # Session B does not exist yet
        self.assertIsNone(self.bridge.load_session(session_b))

        # Create session B
        state_b = BridgeState(
            session_id=session_b,
            seed_name="SeedBeta",
            slot="Player1",
            checked_locations={101100028},
            pending_locations=set(),
            next_item_index=0,
            outbox_position=200,
            savegame_baseline={"Beat FNAF 1 - Night 1", "Collect Faz Token 01"}
        )
        self.bridge.save_session(state_b)

        # Ensure session A was not overwritten by session B
        loaded_a_again = self.bridge.load_session(session_a)
        self.assertEqual(loaded_a_again.checked_locations, {101100010, 101100011})
        self.assertEqual(loaded_a_again.savegame_baseline, {"Beat FNAF 1 - Night 1"})

        loaded_b = self.bridge.load_session(session_b)
        self.assertEqual(loaded_b.checked_locations, {101100028})
        self.assertEqual(loaded_b.savegame_baseline, {"Beat FNAF 1 - Night 1", "Collect Faz Token 01"})


class TestScenariosAThroughE(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="fnafhw_scenarios_"))
        isolate_localappdata(self, self.temp_dir)
        self.bridge_dir = self.temp_dir / "bridge"
        self.bridge_dir.mkdir(parents=True, exist_ok=True)

        # Copy locations.json to test bridge
        real_locations_json = project_root / "ue4ss_mod" / "FNAFHWArchipelago" / "locations.json"
        shutil.copy(real_locations_json, self.bridge_dir / "locations.json")

        self.client = APBridgeClient(self.bridge_dir)

    async def asyncTearDown(self):
        self.client.release_single_instance_lock()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_scenarios_a_b_c_d_e(self):
        """
        Executes Tests A, B, C, D, and E in a controlled simulation:
        - Test A: Fresh server + fresh save -> checks work normally.
        - Test B: Complete checks -> reconnect to same server -> already-sent checks are not duplicated.
        - Test C: Connect to new server/seed -> old server's check state does not carry over.
        - Test D: Save contains old completed content -> does not cause check bleeding on new seed.
        - Test E: Restart client -> reconnect -> correct state is maintained.
        """
        # =====================================================================
        # TEST A: Fresh server + fresh save -> checks work normally
        # =====================================================================
        print("\n--- Running Test A: Fresh server + fresh game save ---")
        self.client.slot = "Player1"
        self.client.current_seed_name = "Seed_Alpha"

        # Server sends Connected packet for Seed_Alpha with 0 checked locations
        connected_packet_a = {
            "cmd": "Connected",
            "checked_locations": [],
            "slot": 1,
            "slot_data": {
                "location_name_to_id": self.client.location_name_to_id
            }
        }
        self.client._on_connected(connected_packet_a)

        self.assertEqual(self.client.state.session_id, "Seed_Alpha_Player1")
        self.assertEqual(len(self.client.state.checked_locations), 0)

        # Simulate live check earned (e.g. from hook or outbox)
        loc_night_1_id = self.client.location_name_to_id["Beat FNAF 1 - Night 1"]
        await self.client._command_location_check(str(loc_night_1_id))

        self.assertIn(loc_night_1_id, self.client.state.pending_locations)

        # Server confirms check
        room_update_a = {
            "cmd": "RoomUpdate",
            "checked_locations": [loc_night_1_id]
        }
        self.client._on_room_update(room_update_a)

        self.assertIn(loc_night_1_id, self.client.state.checked_locations)
        self.assertNotIn(loc_night_1_id, self.client.state.pending_locations)
        print("[Test A PASS] Live check earned and confirmed on fresh session.")

        # =====================================================================
        # TEST B: Complete checks -> reconnect to same server -> no duplicates
        # =====================================================================
        print("\n--- Running Test B: Reconnect to same server/seed ---")
        # Simulate disconnect
        self.client.status = "DISCONNECTED"

        # Reconnect to Seed_Alpha
        self.client.current_seed_name = "Seed_Alpha"
        reconnect_packet_a = {
            "cmd": "Connected",
            "checked_locations": [loc_night_1_id],
            "slot": 1,
            "slot_data": {}
        }
        self.client._on_connected(reconnect_packet_a)

        self.assertEqual(self.client.state.session_id, "Seed_Alpha_Player1")
        self.assertEqual(self.client.state.checked_locations, {loc_night_1_id})
        self.assertEqual(len(self.client.state.pending_locations), 0, "Pending locations should be empty (no duplicates)")
        print("[Test B PASS] Reconnected to same seed without duplicating checks.")

        # =====================================================================
        # TEST C & D: Connect to a completely new server/seed with existing save content
        # =====================================================================
        print("\n--- Running Test C & D: Connect to brand new seed with pre-existing completions ---")
        # A completed save (synthetic, built like a real one) must not bleed into a new seed
        real_sav_path = self.temp_dir / "completed_template.sav"
        real_sav_path.write_bytes(completed_template())

        parsed_real_sav = parse_gvas_save(real_sav_path.read_bytes())
        real_earned = extract_earned_locations(parsed_real_sav)
        self.assertGreater(len(real_earned), 0, "Save must contain completions")
        print(f"Old completed save contains {len(real_earned)} pre-existing completions: {sorted(real_earned)[:4]}...")

        # Switch to Server B: Seed_Beta
        self.client.current_seed_name = "Seed_Beta"
        # Manually create mock save file in a mocked get_active_savegame_path
        test_sav_file = self.temp_dir / "old_save.sav"
        shutil.copy(real_sav_path, test_sav_file)

        # Patch get_active_savegame_path in ap_client.main to point to test_sav_file
        import ap_client.main as apm
        orig_get_save = apm.get_active_savegame_path
        apm.get_active_savegame_path = lambda: test_sav_file

        try:
            connected_packet_b = {
                "cmd": "Connected",
                "checked_locations": [],  # Brand new seed! Server has 0 checks!
                "slot": 1,
                "slot_data": {},
            }
            self.client._on_connected(connected_packet_b)

            # Assert new session ID
            self.assertEqual(self.client.state.session_id, "Seed_Beta_Player1")
            # In the clean Playerarchi architecture, baseline of the fresh save has 0 checks
            # and Player00.sav is never leaked into the session
            self.assertEqual(len(self.client.state.checked_locations), 0)
            self.assertEqual(len(self.client.state.pending_locations), 0)

            # Run _poll_savegame
            self.client._last_sav_mtime = 0.0  # Force poll
            self.client._last_sav_poll_time = 0.0
            await self.client._poll_savegame()

            # CRUCIAL ASSERTION: Server B must NOT receive any checks from Player00.sav!
            self.assertEqual(
                len(self.client.state.pending_locations), 0,
                f"Bleed detected! Client queued {self.client.state.pending_locations} to new server!",
            )
            print("[Test C & D PASS] Zero checks carried over from old seed or Player00.sav content!")

            # Test Delta Savegame Polling:
            # If the player beat Night 2 and it got written to Playerarchi.sav, verify _poll_savegame catches it!
            loc_night_2_name = "Beat FNAF 1 - Night 2"
            loc_night_2_id = self.client.location_name_to_id[loc_night_2_name]

            # Mock extract_earned_locations returning [Night 2]
            orig_extract = apm.extract_earned_locations
            apm.extract_earned_locations = lambda parsed: [loc_night_2_name]
            try:
                self.client._last_sav_mtime = 0.0  # Force poll
                self.client._last_sav_poll_time = 0.0  # Bypass throttle
                await self.client._poll_savegame()
                self.assertIn(loc_night_2_id, self.client.state.pending_locations)
                print(f"[Test C & D PASS] Delta savegame check '{loc_night_2_name}' accurately detected beyond baseline!")
            finally:
                apm.extract_earned_locations = orig_extract

            # Confirm Night 2
            self.client._on_room_update({"cmd": "RoomUpdate", "checked_locations": [loc_night_2_id]})
            self.assertIn(loc_night_2_id, self.client.state.checked_locations)
            self.assertNotIn(loc_night_2_id, self.client.state.pending_locations)

        finally:
            apm.get_active_savegame_path = orig_get_save

        # =====================================================================
        # TEST E: Restart client -> reconnect -> correct state maintained
        # =====================================================================
        print("\n--- Running Test E: Restart client process & reconnect ---")
        self.client.release_single_instance_lock()

        # Create brand-new client instance referencing the same bridge directory
        new_client = APBridgeClient(self.bridge_dir)
        new_client.slot = "Player1"
        new_client.current_seed_name = "Seed_Beta"

        reconnect_packet_b = {
            "cmd": "Connected",
            "checked_locations": [loc_night_2_id],
            "slot": 1,
            "slot_data": {}
        }
        new_client._on_connected(reconnect_packet_b)

        self.assertEqual(new_client.state.session_id, "Seed_Beta_Player1")
        self.assertEqual(new_client.state.checked_locations, {loc_night_2_id})
        self.assertEqual(new_client.state.savegame_baseline, self.client.state.savegame_baseline)
        print("[Test E PASS] Client restart successfully restored session state without duplicate checks.")
        new_client.release_single_instance_lock()


if __name__ == "__main__":
    unittest.main()
