"""
Regression tests for server-authoritative AP state model.

These tests verify the core architectural requirement:
  CURRENT ARCHIPELAGO SERVER STATE → Playerarchi.sav → compare against ACTUAL FNAF progression

Test Scenarios:
  A: Fresh AP session — stale local state must not leak
  B: Current server has some checks — local must reflect only those
  C: Server switch — old checks must not persist
  D: Genuine new FNAF progression — must be sent
  E: Already checked on current server — must NOT be re-sent
  F: Pending check — must survive reconnection
  G: Bonnie Plush startup false positive — must not occur
  H: Baseline re-snapshot on resume — prevents stale sends
"""

import asyncio
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tests.localappdata_isolation import isolate_localappdata
from ap_client.main import BridgeIO, BridgeState, APBridgeClient, STATUS_CONNECTED
from ap_client.save_reader import extract_earned_locations


class TestServerAuthority(unittest.IsolatedAsyncioTestCase):
    """Core regression tests for server-authoritative state model."""

    async def asyncSetUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="fnafhw_auth_"))
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

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _connect_to(self, seed: str, slot: str, server_checked: list[int]):
        """Simulate connecting to an AP server with the given state."""
        self.client.current_seed_name = seed
        self.client.slot = slot
        self.client._on_connected({
            "cmd": "Connected",
            "checked_locations": server_checked,
            "slot": 1,
            "slot_data": {},
        })

    def _id(self, name: str) -> int:
        return self.client.location_name_to_id[name]

    # =========================================================================
    # Scenario A: Fresh AP session — stale local state must not leak
    # =========================================================================

    async def test_scenario_a_fresh_session_no_false_positives(self):
        """
        Scenario A: Fresh AP session.

        Server: checked = {}
        Local old Playerarchi.sav: may have historical AP checks from a previous session.

        Expected: After synchronization, Playerarchi.sav reflects current server
        state (empty), NOT the old historical state. No old checks should be
        blindly emitted as newly earned.
        """
        # First, create a session with Server A that has several checks
        self._connect_to("SeedA", "Player1", [])
        cake_id = self._id("Prize - Food/Drink: Slice of Cake")
        bonnie_plush_id = self._id("Prize - Plushie: Bonnie Plush")
        night1_id = self._id("Beat FNAF 2 - Night 1")

        # Simulate earning and confirming checks on Server A
        self.client.state.checked_locations.update({cake_id, bonnie_plush_id, night1_id})
        self.client.bridge.save_state(self.client.state, self.client.location_id_to_name)

        # Now connect to a fresh Server B (same seed, new session with 0 checks)
        # This simulates a new room with the same seed
        self._connect_to("SeedA", "Player1", [])  # Server says 0 checks

        # SERVER IS AUTHORITATIVE: local state must reflect server's empty state
        self.assertEqual(
            len(self.client.state.checked_locations), 0,
            "Fresh server must have 0 checked locations, not stale local state"
        )
        self.assertEqual(
            len(self.client.state.pending_locations), 0,
            "No pending locations should exist on fresh reconnect"
        )

    # =========================================================================
    # Scenario B: Current server has some checks — local must reflect only those
    # =========================================================================

    async def test_scenario_b_server_has_some_checks(self):
        """
        Scenario B: Server has some checks.

        Server: {Cake, FNAF 2 Night 1}
        Expected local state: Cake=checked, FNAF 2 Night 1=checked.
        Old unrelated checks must not leak.
        """
        cake_id = self._id("Prize - Food/Drink: Slice of Cake")
        night1_id = self._id("Beat FNAF 2 - Night 1")

        # First create an old session with lots of checks
        self._connect_to("SeedX", "Player1", [])
        bonnie_id = self._id("Prize - Plushie: Bonnie Plush")
        freddy_id = self._id("Prize - Plushie: Freddy Plush")
        self.client.state.checked_locations.update({cake_id, night1_id, bonnie_id, freddy_id})
        self.client.bridge.save_state(self.client.state, self.client.location_id_to_name)

        # Now connect to server that says only Cake and Night 1 are checked
        self._connect_to("SeedX", "Player1", [cake_id, night1_id])

        self.assertEqual(
            self.client.state.checked_locations,
            {cake_id, night1_id},
            "Only server-confirmed checks should be in checked_locations"
        )
        self.assertNotIn(bonnie_id, self.client.state.checked_locations,
                         "Bonnie Plush was not on server — must NOT be in local state")
        self.assertNotIn(freddy_id, self.client.state.checked_locations,
                         "Freddy Plush was not on server — must NOT be in local state")

    # =========================================================================
    # Scenario C: Server switch — old checks must not persist
    # =========================================================================

    async def test_scenario_c_server_switch_isolation(self):
        """
        Scenario C: Server switch.

        Server A: {Bonnie Plush, Cake, Tape 07}
        Then connect to Server B: {}

        Expected: Server B local AP state = {}
        Server A checks must not remain authoritative.
        """
        bonnie_id = self._id("Prize - Plushie: Bonnie Plush")
        cake_id = self._id("Prize - Food/Drink: Slice of Cake")
        tape07_id = self._id("Collect Glitch Tape 07")

        # Connect to Server A with checks
        self._connect_to("SeedC", "Player1", [bonnie_id, cake_id, tape07_id])
        self.assertEqual(len(self.client.state.checked_locations), 3)
        self.client.bridge.save_state(self.client.state, self.client.location_id_to_name)

        # Connect to Server B (different seed) with zero checks
        self._connect_to("SeedD", "Player1", [])

        self.assertEqual(
            len(self.client.state.checked_locations), 0,
            "Server B has 0 checks — local state must be empty"
        )
        self.assertNotIn(bonnie_id, self.client.state.checked_locations)
        self.assertNotIn(cake_id, self.client.state.checked_locations)
        self.assertNotIn(tape07_id, self.client.state.checked_locations)

    # =========================================================================
    # Scenario D: Genuine new FNAF progression — must be sent
    # =========================================================================

    async def test_scenario_d_genuine_progression_sends(self):
        """
        Scenario D: Genuine new FNAF progression.

        Current server: {}
        Actual Player00.sav / runtime says: Cake earned

        Expected: send Cake. After server confirmation, Cake becomes checked locally.
        """
        import ap_client.main as apm

        self._connect_to("SeedE", "Player1", [])
        self.client.status = STATUS_CONNECTED

        cake_name = "Prize - Food/Drink: Slice of Cake"
        cake_id = self._id(cake_name)

        # Simulate _poll_savegame finding Cake in the save
        orig_extract = apm.extract_earned_locations
        apm.extract_earned_locations = lambda parsed: [cake_name]
        try:
            self.client._last_sav_mtime = 0.0
            self.client._last_sav_poll_time = 0.0
            await self.client._poll_savegame()

            self.assertIn(cake_id, self.client.state.pending_locations,
                          "Cake should be pending after detection from save")
        finally:
            apm.extract_earned_locations = orig_extract

        # Server confirms it
        self.client._on_room_update({
            "cmd": "RoomUpdate",
            "checked_locations": [cake_id],
        })

        self.assertIn(cake_id, self.client.state.checked_locations,
                      "Cake should be checked after server confirmation")
        self.assertNotIn(cake_id, self.client.state.pending_locations,
                         "Cake should no longer be pending")

    # =========================================================================
    # Scenario E: Already checked on current server — must NOT be re-sent
    # =========================================================================

    async def test_scenario_e_already_checked_not_resent(self):
        """
        Scenario E: Already checked current server location.

        Server: {Cake}
        FNAF progression: Cake earned

        Expected: DO NOT SEND Cake again.
        """
        import ap_client.main as apm

        cake_name = "Prize - Food/Drink: Slice of Cake"
        cake_id = self._id(cake_name)

        # Connect with Cake already checked on server
        self._connect_to("SeedF", "Player1", [cake_id])
        self.client.status = STATUS_CONNECTED

        # Simulate _poll_savegame finding Cake
        orig_extract = apm.extract_earned_locations
        apm.extract_earned_locations = lambda parsed: [cake_name]
        try:
            self.client._last_sav_mtime = 0.0
            self.client._last_sav_poll_time = 0.0
            await self.client._poll_savegame()
        finally:
            apm.extract_earned_locations = orig_extract

        # Cake must NOT be added to pending
        self.assertNotIn(cake_id, self.client.state.pending_locations,
                         "Already-checked location must NOT be re-queued")

    # =========================================================================
    # Scenario F: Pending check — must survive reconnection
    # =========================================================================

    async def test_scenario_f_pending_check_survives_reconnect(self):
        """
        Scenario F: Pending check.

        FNAF progression says: Bonnie Action Figure earned.
        Server has not yet confirmed it.
        Client disconnects and reconnects.

        Expected: keep it pending, retry, do not lose it.
        """
        bonnie_af_id = self._id("Prize - Action Figure: Bonnie Action Figure")

        # Connect and earn a check
        self._connect_to("SeedG", "Player1", [])
        self.client.state.pending_locations.add(bonnie_af_id)
        self.client.bridge.save_state(self.client.state, self.client.location_id_to_name)

        # Reconnect — server still has 0 checks (hasn't confirmed Bonnie AF yet)
        self._connect_to("SeedG", "Player1", [])

        self.assertIn(bonnie_af_id, self.client.state.pending_locations,
                      "Pending check must survive reconnection when server hasn't confirmed it")

    # =========================================================================
    # Scenario G: Bonnie Plush startup false positive — must not occur
    # =========================================================================

    async def test_scenario_g_bonnie_plush_startup_false_positive(self):
        """
        Scenario G: Bonnie Plush startup false positive.

        This is the confirmed bug scenario:
        - Playerarchi.sav on disk contains Bonnie Plush (prize row 30)
        - Client reconnects to server that does NOT have Bonnie Plush checked
        - The old save content must NOT be treated as new progression

        The baseline must be re-snapshotted on resume to prevent this.
        """
        import ap_client.main as apm

        bonnie_plush_name = "Prize - Plushie: Bonnie Plush"
        bonnie_plush_id = self._id(bonnie_plush_name)

        # Connect to initial session
        self._connect_to("SeedH", "Player1", [])
        self.client.status = STATUS_CONNECTED
        self.client.bridge.save_state(self.client.state, self.client.location_id_to_name)

        # Simulate: The game wrote Bonnie Plush to Playerarchi.sav during gameplay.
        # On reconnect, _poll_savegame will find it.
        # But the BASELINE should now include it too (re-snapshotted on resume).
        bonnie_content = [bonnie_plush_name, "Prize - Food/Drink: Stick of Butter"]

        # Mock savegame path to return content that has Bonnie Plush
        orig_extract = apm.extract_earned_locations
        apm.extract_earned_locations = lambda parsed: bonnie_content

        try:
            # Simulate reconnect: server does NOT have Bonnie Plush checked
            self._connect_to("SeedH", "Player1", [])
            self.client.status = STATUS_CONNECTED

            # The baseline should include Bonnie Plush now (re-snapshotted from disk)
            # But since we're mocking extract_earned_locations, the baseline snapshot
            # during _on_connected also uses the same mock. Let's verify the logic
            # by checking that baseline includes what's in the save.
            self.assertIn(bonnie_plush_name, self.client.state.savegame_baseline,
                          "Baseline must include Bonnie Plush from re-snapshotted save")

            # Now _poll_savegame runs — Bonnie Plush is in baseline, so it should NOT be sent
            self.client._last_sav_mtime = 0.0
            self.client._last_sav_poll_time = 0.0
            await self.client._poll_savegame()

            self.assertNotIn(bonnie_plush_id, self.client.state.pending_locations,
                             "Bonnie Plush must NOT be queued as a false positive!")
        finally:
            apm.extract_earned_locations = orig_extract

    # =========================================================================
    # Scenario H: Baseline re-snapshot on resume prevents stale sends
    # =========================================================================

    async def test_scenario_h_baseline_resnapshot_prevents_stale_sends(self):
        """
        Scenario H: Baseline re-snapshot on resume.

        After gameplay, Playerarchi.sav accumulates earned locations.
        On reconnect, the baseline must be re-snapshotted from the current save,
        not from the original clean save baseline.

        This prevents ALL pre-existing save content from being treated as new checks.
        """
        import ap_client.main as apm

        # Initial connection
        self._connect_to("SeedI", "Player1", [])
        self.client.status = STATUS_CONNECTED

        # During gameplay, multiple things were earned and written to save
        gameplay_content = [
            "Prize - Plushie: Bonnie Plush",
            "Prize - Plushie: Freddy Plush",
            "Prize - Food/Drink: Stick of Butter",
            "Complete Parts and Service - Bonnie",
            "Collect Faz Token 13",
        ]

        # Save the session (simulating client exit)
        self.client.bridge.save_state(self.client.state, self.client.location_id_to_name)

        # Mock the save reader to return accumulated content
        orig_extract = apm.extract_earned_locations
        apm.extract_earned_locations = lambda parsed: gameplay_content

        try:
            # Reconnect to same session, server has confirmed NOTHING
            self._connect_to("SeedI", "Player1", [])
            self.client.status = STATUS_CONNECTED

            # Baseline must now include all accumulated content
            for loc_name in gameplay_content:
                self.assertIn(loc_name, self.client.state.savegame_baseline,
                              f"'{loc_name}' must be in re-snapshotted baseline")

            # _poll_savegame should find NOTHING new (all in baseline)
            self.client._last_sav_mtime = 0.0
            self.client._last_sav_poll_time = 0.0
            await self.client._poll_savegame()

            self.assertEqual(len(self.client.state.pending_locations), 0,
                             "No pending locations — all content is in baseline")
        finally:
            apm.extract_earned_locations = orig_extract

    # =========================================================================
    # Scenario I: Genuine new progression AFTER baseline is detected correctly
    # =========================================================================

    async def test_scenario_i_new_progression_after_baseline(self):
        """
        After reconnecting with a baseline, GENUINELY NEW game progression
        (not in the baseline) must still be detected and sent.
        """
        import ap_client.main as apm

        # Initial connection
        self._connect_to("SeedJ", "Player1", [])
        self.client.status = STATUS_CONNECTED

        # During session, some content exists in save at reconnect time
        existing_content = ["Prize - Plushie: Bonnie Plush", "Collect Faz Token 13"]

        # Mock for baseline snapshot during reconnect
        orig_extract = apm.extract_earned_locations
        apm.extract_earned_locations = lambda parsed: existing_content
        self.client.bridge.save_state(self.client.state, self.client.location_id_to_name)

        # Reconnect
        self._connect_to("SeedJ", "Player1", [])
        self.client.status = STATUS_CONNECTED

        # Verify baseline captured existing content
        self.assertIn("Prize - Plushie: Bonnie Plush", self.client.state.savegame_baseline)
        self.assertIn("Collect Faz Token 13", self.client.state.savegame_baseline)

        # Now simulate NEW progression: Cake is earned during gameplay
        new_content = existing_content + ["Prize - Food/Drink: Slice of Cake"]
        apm.extract_earned_locations = lambda parsed: new_content

        self.client._last_sav_mtime = 0.0
        self.client._last_sav_poll_time = 0.0
        await self.client._poll_savegame()

        cake_id = self._id("Prize - Food/Drink: Slice of Cake")
        self.assertIn(cake_id, self.client.state.pending_locations,
                      "New Cake check must be detected as new progression beyond baseline")

        # And the old content must NOT be pending
        bonnie_id = self._id("Prize - Plushie: Bonnie Plush")
        token13_id = self._id("Collect Faz Token 13")
        self.assertNotIn(bonnie_id, self.client.state.pending_locations,
                         "Baseline content must NOT trigger new checks")
        self.assertNotIn(token13_id, self.client.state.pending_locations,
                         "Baseline content must NOT trigger new checks")

        apm.extract_earned_locations = orig_extract


class TestServerSwitchIsolation(unittest.IsolatedAsyncioTestCase):
    """Tests that server/seed/slot changes isolate AP state correctly."""

    async def asyncSetUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="fnafhw_iso_"))
        isolate_localappdata(self, self.temp_dir)
        self.bridge_dir = self.temp_dir / "bridge"
        self.bridge_dir.mkdir(parents=True, exist_ok=True)
        real_locations_json = project_root / "ue4ss_mod" / "FNAFHWArchipelago" / "locations.json"
        shutil.copy(real_locations_json, self.bridge_dir / "locations.json")
        self.client = APBridgeClient(self.bridge_dir)

    async def asyncTearDown(self):
        self.client.release_single_instance_lock()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_seed_a_to_seed_b_isolation(self):
        """
        Full end-to-end seed switch test.

        Connect to Seed A, check 5 locations.
        Connect to Seed B (0 checks).
        Verify: Seed B has 0 checked, 0 pending.
        """
        self.client.current_seed_name = "SeedAlpha"
        self.client.slot = "TestSlot"

        loc_ids = [
            self.client.location_name_to_id["Collect Faz Token 01"],
            self.client.location_name_to_id["Collect Faz Token 02"],
            self.client.location_name_to_id["Collect Faz Token 04"],
            self.client.location_name_to_id["Collect Prize Counter Intro Tape"],
            self.client.location_name_to_id["Beat FNAF 2 - Night 1"],
        ]

        # Connect to Seed A with those checks
        self.client._on_connected({
            "cmd": "Connected",
            "checked_locations": loc_ids,
            "slot": 1,
            "slot_data": {},
        })
        self.assertEqual(len(self.client.state.checked_locations), 5)
        self.client.bridge.save_state(self.client.state, self.client.location_id_to_name)

        # Now connect to completely different Seed B
        self.client.current_seed_name = "SeedBeta"
        self.client._on_connected({
            "cmd": "Connected",
            "checked_locations": [],  # Brand new server, 0 checks
            "slot": 1,
            "slot_data": {},
        })

        self.assertEqual(len(self.client.state.checked_locations), 0,
                         "Seed B must have 0 checked locations")
        self.assertEqual(len(self.client.state.pending_locations), 0,
                         "Seed B must have 0 pending locations")

        # Verify no Seed A IDs leaked
        for lid in loc_ids:
            self.assertNotIn(lid, self.client.state.checked_locations,
                             f"Seed A check {lid} must NOT appear in Seed B state")

    async def test_same_seed_different_slot(self):
        """Verify different slots on the same seed are isolated."""
        seed = "SharedSeed"

        # Slot A
        self.client.current_seed_name = seed
        self.client.slot = "SlotA"
        night1_id = self.client.location_name_to_id["Beat FNAF 1 - Night 1"]
        self.client._on_connected({
            "cmd": "Connected",
            "checked_locations": [night1_id],
            "slot": 1,
            "slot_data": {},
        })
        self.client.bridge.save_state(self.client.state, self.client.location_id_to_name)

        # Slot B — same seed, different slot
        self.client.slot = "SlotB"
        self.client._on_connected({
            "cmd": "Connected",
            "checked_locations": [],
            "slot": 2,
            "slot_data": {},
        })

        self.assertEqual(len(self.client.state.checked_locations), 0,
                         "Different slot must not inherit Slot A checks")
        self.assertNotIn(night1_id, self.client.state.checked_locations)


if __name__ == "__main__":
    unittest.main()
