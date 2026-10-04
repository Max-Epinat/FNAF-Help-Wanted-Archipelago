import asyncio
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tests.gvas_fixtures import starter_player00
from tests.localappdata_isolation import SAVE_SUBDIR, isolate_localappdata
from ap_client.main import BridgeIO, BridgeState, APBridgeClient
from ap_client.save_reader import (
    DEFAULT_ROW_MAP,
    DEFAULT_PRIZE_MAP,
    extract_earned_locations,
    get_active_savegame_path,
    parse_gvas_save,
)


class TestFullValidation(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="fnafhw_val_"))
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

    def test_01_basic_check_detection(self):
        """Test 1: Verify basic check resolution from row IDs and SaveGame properties."""
        # Row 19 is Bonnie repair
        self.assertIn(19, DEFAULT_ROW_MAP)
        self.assertEqual(DEFAULT_ROW_MAP[19], "Complete Parts and Service - Bonnie")

        # Mock a save with row 19 completed and coin 13 collected
        mock_save = {
            "LevelInfo": {"19": True, "0": False},
            "CollectedCoins": [13],
            "CollectedGlitches": [14],
        }
        earned = extract_earned_locations(mock_save)
        self.assertIn("Complete Parts and Service - Bonnie", earned)
        self.assertIn("Collect Faz Token 13", earned)
        self.assertIn("Collect Prize Counter Intro Tape", earned)

    def test_02_multiple_checks_detection(self):
        """Test 2: Verify multiple checks are cleanly detected without dropping or collision."""
        mock_save = {
            "LevelInfo": {"4": True, "5": True, "19": True},
            "CollectedCoins": [1, 2, 12, 13, 29],
            "CollectedGlitches": [6, 14],
            "Prizes": ["61"],  # Stick of Butter
        }
        earned = extract_earned_locations(mock_save)
        self.assertEqual(len(earned), 11)
        self.assertIn("Beat FNAF 1 - Night 1", earned)
        self.assertIn("Beat FNAF 1 - Night 2", earned)
        self.assertIn("Complete Parts and Service - Bonnie", earned)
        self.assertIn("Collect Faz Token 01", earned)
        self.assertIn("Collect Faz Token 02", earned)
        self.assertIn("Collect Faz Token 12", earned)
        self.assertIn("Collect Faz Token 13", earned)
        self.assertIn("Collect Faz Token 29", earned)
        self.assertIn("Collect Prize Counter Intro Tape", earned)
        self.assertIn("Collect Glitch Tape 07", earned)
        self.assertIn("Prize - Food/Drink: Stick of Butter", earned)

    def test_03_fnaf1_night1_vs_fnaf2_withered(self):
        """Test 3: Verify FNAF 1 Night 1 (Row 4) and FNAF 2 Withered (Row 40) are strictly distinct."""
        self.assertEqual(DEFAULT_ROW_MAP[4], "Beat FNAF 1 - Night 1")
        self.assertEqual(DEFAULT_ROW_MAP[40], "Beat FNAF 2 - Withered")
        self.assertNotEqual(DEFAULT_ROW_MAP[4], DEFAULT_ROW_MAP[40])

        # A save with only Night 1 completed must NEVER award Withered
        save_fnaf1 = {"LevelInfo": {"4": True, "40": False}}
        earned_fnaf1 = extract_earned_locations(save_fnaf1)
        self.assertIn("Beat FNAF 1 - Night 1", earned_fnaf1)
        self.assertNotIn("Beat FNAF 2 - Withered", earned_fnaf1)

    def test_04_fnaf2_withered_check(self):
        """Test 4: Verify FNAF 2 Withered (Row 40) check is accurately awarded when completed."""
        save_withered = {"LevelInfo": {"4": False, "40": True}}
        earned = extract_earned_locations(save_withered)
        self.assertIn("Beat FNAF 2 - Withered", earned)
        self.assertNotIn("Beat FNAF 1 - Night 1", earned)

    async def test_05_new_seed_separation(self):
        """Test 5: Verify new seed separation - checks from Seed A do NOT carry over to Seed B."""
        # 1. Connect to Seed A
        self.client.current_seed_name = "Seed_Alpha"
        self.client.slot = "HWtest"
        self.client._on_connected({
            "cmd": "Connected",
            "team": 0,
            "slot": 1,
            "checked_locations": [101100010],  # Token 01
            "missing_locations": [101100138, 101100139],
        })

        # Earn check in Seed A
        await self.client._command_location_check("101100138")
        self.assertIn(101100138, self.client.state.pending_locations)

        # Confirm check on server A
        self.client.state.checked_locations.add(101100138)
        self.client.state.pending_locations.discard(101100138)
        self.client.bridge.save_session(self.client.state)
        self.client.release_single_instance_lock()

        # 2. Connect to completely new Seed B
        client_b = APBridgeClient(self.bridge_dir)
        client_b.current_seed_name = "Seed_Beta"
        client_b.slot = "HWtest"
        client_b._on_connected({
            "cmd": "Connected",
            "team": 0,
            "slot": 1,
            "checked_locations": [],  # Brand new seed, 0 checks
            "missing_locations": [101100010, 101100138, 101100139],
        })

        # Ensure Seed B has 0 checked and 0 pending locations
        self.assertEqual(len(client_b.state.checked_locations), 0)
        self.assertEqual(len(client_b.state.pending_locations), 0)
        client_b.release_single_instance_lock()

    async def test_06_restart_client_and_reconnect(self):
        """Test 6: Verify client restart and reconnect to same seed resumes state without duplicates."""
        self.client.current_seed_name = "Seed_Gamma"
        self.client.slot = "HWtest"
        self.client._on_connected({
            "cmd": "Connected",
            "team": 0,
            "slot": 1,
            "checked_locations": [101100138],  # FNAF 1 Night 1 checked
            "missing_locations": [101100139],
        })
        self.client.bridge.save_session(self.client.state)
        self.client.release_single_instance_lock()

        # Restart client process simulation
        restarted = APBridgeClient(self.bridge_dir)
        restarted.current_seed_name = "Seed_Gamma"
        restarted.slot = "HWtest"
        restarted._on_connected({
            "cmd": "Connected",
            "team": 0,
            "slot": 1,
            "checked_locations": [101100138],
            "missing_locations": [101100139],
        })

        self.assertIn(101100138, restarted.state.checked_locations)
        self.assertEqual(len(restarted.state.pending_locations), 0)
        restarted.release_single_instance_lock()

    def test_07_normal_save_protection(self):
        """Test 7: Starting an AP session creates Playerarchi.sav from Player00.sav and must never modify Player00.sav."""
        import hashlib

        save_dir = Path(os.environ["LOCALAPPDATA"]) / SAVE_SUBDIR
        p00 = save_dir / "Player00.sav"
        data = p00.read_bytes()
        self.assertTrue(data.startswith(b"GVAS"), "Player00.sav header must be valid GVAS")
        parsed = parse_gvas_save(data)
        # the starter save contains only the starting basketball (row 3)
        self.assertEqual(parsed.get("Prizes"), ["3"])
        digest = hashlib.sha256(data).hexdigest()

        self.client.current_seed_name = "Seed_Protect"
        self.client.slot = "Player1"
        self.client._on_connected({"cmd": "Connected", "checked_locations": [], "slot": 1, "slot_data": {}})

        self.assertTrue((save_dir / "Playerarchi.sav").exists(), "a new session must create Playerarchi.sav")
        self.assertEqual(hashlib.sha256(p00.read_bytes()).hexdigest(), digest, "Player00.sav must be left untouched")

    def test_08_archipelago_save_operation(self):
        """Test 8: Verify get_active_savegame_path prioritizes Playerarchi.sav over Player00.sav."""
        fake_save_dir = self.temp_dir / "SaveGames"
        fake_save_dir.mkdir(parents=True, exist_ok=True)

        p00 = fake_save_dir / "Player00.sav"
        p00.write_bytes(b"GVAS_DUMMY_00")

        # When only Player00 exists, fallback to Player00
        orig_localappdata = os.environ.get("LOCALAPPDATA")
        try:
            os.environ["LOCALAPPDATA"] = str(self.temp_dir)
            # Create freddys/Saved/SaveGames structure
            game_save_dir = self.temp_dir / "freddys" / "Saved" / "SaveGames"
            game_save_dir.mkdir(parents=True, exist_ok=True)

            (game_save_dir / "Player00.sav").write_bytes(starter_player00())

            # With prefer_archi=True, Player00.sav must NEVER be returned!
            path = get_active_savegame_path(prefer_archi=True)
            if path is not None:
                self.assertNotEqual(path.name, "Player00.sav")

            # With prefer_archi=False, Player00.sav is strictly returned
            path_norm = get_active_savegame_path(prefer_archi=False)
            self.assertEqual(path_norm.name, "Player00.sav")

            # Now create Playerarchi.sav via clean generator
            from ap_client.save_reader import ensure_clean_archipelago_save
            ensure_clean_archipelago_save(game_save_dir / "Playerarchi.sav", game_save_dir / "Player00.sav")

            path2 = get_active_savegame_path(prefer_archi=True)
            self.assertIsNotNone(path2)
            self.assertEqual(path2.name, "Playerarchi.sav")
        finally:
            if orig_localappdata:
                os.environ["LOCALAPPDATA"] = orig_localappdata

    async def test_09_offline_checks_detection(self):
        """Test 9: Verify checks completed offline in Playerarchi.sav are queued and sent upon reconnection."""
        self.client.current_seed_name = "Seed_Offline_Test"
        self.client.slot = "Player1"
        self.client._on_connected({
            "cmd": "Connected",
            "checked_locations": [],
            "slot": 1,
            "slot_data": {},
        })

        # Simulate offline progress written to Playerarchi.sav:
        # Beat FNAF 2 Night 1 (row 9), Faz Token 04 (coin 4), Toy Chica Plush (prize '26')
        offline_save = {
            "LevelInfo": {"9": True},
            "CollectedCoins": [4],
            "Prizes": ["26"],
        }
        earned = extract_earned_locations(offline_save)
        self.assertIn("Beat FNAF 2 - Night 1", earned)
        self.assertIn("Collect Faz Token 04", earned)
        self.assertIn("Prize - Plushie: Toy Chica Plush", earned)

        # Mock savegame polling
        import ap_client.main as apm
        orig_extract = apm.extract_earned_locations
        apm.extract_earned_locations = lambda parsed: earned
        try:
            self.client._last_sav_mtime = 0.0
            self.client._last_sav_poll_time = 0.0
            await self.client._poll_savegame()

            # All 3 offline checks must be queued in pending_locations
            loc_fnaf2_n1 = self.client.location_name_to_id["Beat FNAF 2 - Night 1"]
            loc_coin_04 = self.client.location_name_to_id["Collect Faz Token 04"]
            loc_toy_chica = self.client.location_name_to_id["Prize - Plushie: Toy Chica Plush"]

            self.assertIn(loc_fnaf2_n1, self.client.state.pending_locations)
            self.assertIn(loc_coin_04, self.client.state.pending_locations)
            self.assertIn(loc_toy_chica, self.client.state.pending_locations)
            self.assertEqual(len(self.client.state.pending_locations), 3)
        finally:
            apm.extract_earned_locations = orig_extract

    def test_10_fnaf2_night1_prize_isolation(self):
        """Test 10: Verify FNAF 2 Night 1 prize '26' is strictly Toy Chica Plush and row '3' is not in prize map."""
        self.assertEqual(DEFAULT_PRIZE_MAP["26"], "Prize - Plushie: Toy Chica Plush")
        self.assertNotIn("3", DEFAULT_PRIZE_MAP, "Row 3 (Basketball) must never map to Freddy Plush")
        self.assertEqual(DEFAULT_PRIZE_MAP["33"], "Prize - Plushie: Freddy Plush")

        # When save contains only prize '26'
        save_toy_chica = {"Prizes": ["26"]}
        earned = extract_earned_locations(save_toy_chica)
        self.assertIn("Prize - Plushie: Toy Chica Plush", earned)
        self.assertNotIn("Prize - Other: Prize Counter Poster", earned)
        self.assertEqual(len(earned), 1, "Only one check must be awarded for Toy Chica Plush")

    def test_11_fazcoin_direct_mapping_no_drift(self):
        """Test 11: Verify Fazcoins 1..30 map strictly and individually to their exact location IDs."""
        for cid in range(1, 31):
            expected_name = f"Collect Faz Token {cid:02d}"
            self.assertIn(expected_name, self.client.location_name_to_id)
            save_single_coin = {"CollectedCoins": [cid]}
            earned = extract_earned_locations(save_single_coin)
            self.assertEqual(earned, [expected_name])


    def test_12_bonnie_plush_startup_false_positive_prevention(self):
        """Test 12: Verify props (Basketball, White Balloon, etc.) never produce Bonnie Plush or Freddy Plush."""
        # Unmapped props: 3 (Basketball), 75 (White Balloon), 2 (Roach)
        # Legitimate prizes: 86 (Slice of Cake), 43 (Bonnie Action Figure)
        props_and_prizes_save = {"Prizes": ["3", "75", "2", "86", "43"]}
        earned = extract_earned_locations(props_and_prizes_save)

        # Props must NOT be mapped to plushies by index/position
        self.assertNotIn("Prize - Plushie: Bonnie Plush", earned, "Props must never trigger Bonnie Plush false positive!")
        self.assertNotIn("Prize - Plushie: Freddy Plush", earned, "Props must never trigger Freddy Plush false positive!")

        # Legitimate prizes must be cleanly preserved
        self.assertIn("Prize - Food/Drink: Slice of Cake", earned)
        self.assertIn("Prize - Action Figure: Bonnie Action Figure", earned)
        self.assertEqual(len(earned), 2)

        # Genuine Bonnie Plush (Row 30) and Freddy Plush (Row 33) must still be earned when actually present
        self.assertEqual(extract_earned_locations({"Prizes": ["30"]}), ["Prize - Plushie: Bonnie Plush"])
        self.assertEqual(extract_earned_locations({"Prizes": ["33"]}), ["Prize - Plushie: Freddy Plush"])

    async def test_13_poll_savegame_disconnected_guard(self):
        """Test 13: Verify _poll_savegame is strictly ignored while client is disconnected."""
        from ap_client.main import STATUS_DISCONNECTED
        self.assertEqual(self.client.status, STATUS_DISCONNECTED)

        # Even if a save with new checks exists on disk, it must not be polled while disconnected
        self.client._last_sav_poll_time = 0.0
        self.client._last_sav_mtime = 0.0
        await self.client._poll_savegame()

        self.assertEqual(len(self.client.state.pending_locations), 0)


if __name__ == "__main__":
    unittest.main()
