"""One Archipelago save file per multiworld: `Playerarchi_<seed>_<slot>.sav` (the session id is seed + slot, from the server's RoomInfo).

Before, every session shared `Playerarchi.sav`: connecting to a new room archived the old save, and going back to the old room showed the NEW save.
Now a session keeps its own file, other sessions' files are never touched, and the client tells the mod which save slot to use (`SAVE_SLOT <name>`).
Sessions made before this change keep using `Playerarchi.sav` (their file), so nobody's progress moves.
The real BridgeCore and the real save reader run here, on a synthetic template save, with LOCALAPPDATA redirected (no real save is touched).
"""

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ap_client.bridge_core import LEGACY_SAVE_SLOT, BridgeCore, save_slot_for_session
from ap_client.save_reader import ensure_clean_archipelago_save, get_archipelago_savegame_path
from tests.localappdata_isolation import SAVE_SUBDIR, isolate_localappdata


class TestSlotNames(unittest.TestCase):
    def test_the_name_is_playerarchi_plus_the_session_id(self):
        self.assertEqual(save_slot_for_session("91431206794269387946_helpDev"), "Playerarchi_91431206794269387946_helpDev")

    def test_it_is_never_the_legacy_name_and_different_sessions_differ(self):
        names = {save_slot_for_session(s) for s in ("1_a", "1_b", "2_a", "2_b")}
        self.assertEqual(len(names), 4)
        self.assertNotIn(LEGACY_SAVE_SLOT, names)

    def test_only_safe_characters_reach_the_file_name(self):
        for hostile in ("../../evil_x", "a b:c*d?", "seed\\slot", "é_Ü", "x" * 400 + "_y", ""):
            name = save_slot_for_session(hostile)
            self.assertRegex(name, r"^Playerarchi_[A-Za-z0-9_-]*$", hostile)
            self.assertLessEqual(len(name), 120, hostile)

    def test_the_core_and_the_save_reader_agree_on_the_shared_name(self):
        from ap_client.save_reader import DEFAULT_SAVE_SLOT
        self.assertEqual(DEFAULT_SAVE_SLOT, LEGACY_SAVE_SLOT)
        self.assertEqual(get_archipelago_savegame_path(), get_archipelago_savegame_path(LEGACY_SAVE_SLOT))

    def test_the_save_reader_refuses_a_slot_name_that_could_leave_the_save_folder(self):
        for bad in ("../x", "a/b", "a\\b", "x.sav", "a b", ""):
            with self.assertRaises(ValueError, msg=bad):
                get_archipelago_savegame_path(bad)


class SessionSavesCase(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="fnafhw_saves_"))
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        isolate_localappdata(self, self.temp)
        self.save_dir = Path(os.environ["LOCALAPPDATA"]) / SAVE_SUBDIR
        self.bridge_dir = self.temp / "bridge"

    def core(self, seed, slot="HWtest"):
        core = BridgeCore(self.bridge_dir)
        core.slot, core.current_seed_name = slot, seed
        return core

    @staticmethod
    def connect(core, **slot_data):
        return core.on_connected({"cmd": "Connected", "checked_locations": [], "slot_data": slot_data})

    def files(self):
        return sorted(p.name for p in self.save_dir.iterdir())

    def inbox(self, core):
        return core.bridge.inbox_path.read_text(encoding="utf-8").splitlines()


class TestEachSessionHasItsOwnSave(SessionSavesCase):
    def test_a_new_session_creates_its_own_file_and_not_the_shared_one(self):
        core = self.core("SeedA")
        self.connect(core)
        self.assertIn("Playerarchi_SeedA_HWtest.sav", self.files())
        self.assertNotIn("Playerarchi.sav", self.files())
        self.assertEqual(core.save_api.archipelago_save_path().name, "Playerarchi_SeedA_HWtest.sav")

    def test_a_second_session_does_not_touch_or_archive_the_first_ones_save(self):
        first = self.core("SeedA")
        self.connect(first)
        path_a = self.save_dir / "Playerarchi_SeedA_HWtest.sav"
        path_a.write_bytes(path_a.read_bytes() + b"\x00progress")  # the player progressed in game
        before = path_a.read_bytes()
        second = self.core("SeedB")
        self.connect(second)
        self.assertEqual(path_a.read_bytes(), before)
        self.assertIn("Playerarchi_SeedB_HWtest.sav", self.files())
        self.assertEqual([f for f in self.files() if f.endswith(".bak")], [])
        self.assertEqual(second.save_api.archipelago_save_path().name, "Playerarchi_SeedB_HWtest.sav")

    def test_going_back_to_the_first_room_finds_the_first_save_again(self):
        core = self.core("SeedA")
        self.connect(core)
        core.current_seed_name = "SeedB"
        self.connect(core)
        self.assertEqual(core.save_api.archipelago_save_path().name, "Playerarchi_SeedB_HWtest.sav")
        core.current_seed_name = "SeedA"
        self.connect(core)  # resume
        self.assertEqual(core.save_api.archipelago_save_path().name, "Playerarchi_SeedA_HWtest.sav")
        self.assertEqual(core.state.save_slot, "Playerarchi_SeedA_HWtest")
        self.assertEqual([f for f in self.files() if f.endswith(".bak")], [])

    def test_two_slots_of_the_same_multiworld_have_two_saves(self):
        self.connect(self.core("SeedA", "Alice"))
        self.connect(self.core("SeedA", "Bob"))
        self.assertEqual([f for f in self.files() if f.startswith("Playerarchi_")],
                         ["Playerarchi_SeedA_Alice.sav", "Playerarchi_SeedA_Bob.sav"])

    def test_the_normal_save_is_never_modified(self):
        import hashlib
        normal = self.save_dir / "Player00.sav"
        digest = hashlib.sha256(normal.read_bytes()).hexdigest()
        for seed in ("SeedA", "SeedB"):
            self.connect(self.core(seed))
        self.assertEqual(hashlib.sha256(normal.read_bytes()).hexdigest(), digest)

    def test_a_stale_file_with_the_sessions_own_name_is_archived_not_overwritten_silently(self):
        """The session file was deleted but its save was not: a NEW session must not inherit it."""
        stale = self.save_dir / "Playerarchi_SeedA_HWtest.sav"
        stale.write_bytes(b"stale progress")
        self.connect(self.core("SeedA"))
        self.assertTrue(any(f.startswith("Playerarchi_SeedA_HWtest_") and f.endswith(".sav.bak") for f in self.files()), self.files())
        self.assertNotEqual(stale.read_bytes(), b"stale progress")


class TestResumingASession(SessionSavesCase):
    def test_a_deleted_save_of_a_resumed_session_is_recreated_clean(self):
        core = self.core("SeedA")
        self.connect(core)
        (self.save_dir / "Playerarchi_SeedA_HWtest.sav").unlink()
        self.connect(self.core("SeedA"))
        self.assertIn("Playerarchi_SeedA_HWtest.sav", self.files())

    def test_a_stored_slot_that_is_not_a_safe_file_name_is_not_trusted(self):
        sessions = self.bridge_dir / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "SeedA_HWtest.json").write_text(json.dumps({
            "session_id": "SeedA_HWtest", "seed_name": "SeedA", "slot": "HWtest", "save_slot": "../../evil", "checked_locations": [],
            "pending_locations": [], "next_item_index": 0, "applied_item_count": 0, "outbox_position": 0, "savegame_baseline": []}), encoding="utf-8")
        core = self.core("SeedA")
        self.connect(core)  # must not raise
        self.assertEqual(core.state.save_slot, LEGACY_SAVE_SLOT)
        self.assertIn(f"SAVE_SLOT {LEGACY_SAVE_SLOT}", self.inbox(core))

    def test_the_save_slot_survives_a_client_restart(self):
        self.connect(self.core("SeedA"))
        restarted = self.core("SeedA")
        self.assertEqual(restarted.state.save_slot, "Playerarchi_SeedA_HWtest")  # loaded from ap_state.json
        session = json.loads((self.bridge_dir / "sessions" / "SeedA_HWtest.json").read_text(encoding="utf-8"))
        self.assertEqual(session["save_slot"], "Playerarchi_SeedA_HWtest")


class TestSessionsMadeBeforeThisChange(SessionSavesCase):
    """Their save is Playerarchi.sav: it stays where it is and nothing is renamed, archived or created."""

    def make_legacy_session(self):
        ensure_clean_archipelago_save(self.save_dir / "Playerarchi.sav", self.save_dir / "Player00.sav")
        sessions = self.bridge_dir / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "OldSeed_HWtest.json").write_text(json.dumps({
            "session_id": "OldSeed_HWtest", "seed_name": "OldSeed", "slot": "HWtest", "checked_locations": [], "pending_locations": [],
            "next_item_index": 3, "applied_item_count": 3, "outbox_position": 0, "savegame_baseline": []}), encoding="utf-8")
        return self.save_dir / "Playerarchi.sav"

    def test_a_resumed_old_session_keeps_using_the_shared_file(self):
        legacy = self.make_legacy_session()
        before = legacy.read_bytes()
        core = self.core("OldSeed")
        self.connect(core)
        self.assertEqual(core.state.save_slot, LEGACY_SAVE_SLOT)
        self.assertEqual(core.save_api.archipelago_save_path(), legacy)
        self.assertEqual(legacy.read_bytes(), before)
        self.assertEqual(self.files().count("Playerarchi.sav"), 1)
        self.assertEqual([f for f in self.files() if f.startswith("Playerarchi_")], [])
        self.assertIn(f"SAVE_SLOT {LEGACY_SAVE_SLOT}", self.inbox(core))

    def test_an_old_session_whose_shared_file_is_gone_does_not_get_a_new_one_made(self):
        legacy = self.make_legacy_session()
        legacy.unlink()
        self.connect(self.core("OldSeed"))
        self.assertNotIn("Playerarchi.sav", self.files())  # as before: the game starts its own

    def test_a_new_session_next_to_an_old_one_leaves_the_old_save_alone_and_the_old_session_finds_it_again(self):
        legacy = self.make_legacy_session()
        before = legacy.read_bytes()
        new = self.core("NewSeed")
        self.connect(new)
        self.assertEqual(legacy.read_bytes(), before)  # before this change it was archived
        self.assertEqual([f for f in self.files() if f.endswith(".bak")], [])
        old = self.core("OldSeed")
        self.connect(old)
        self.assertEqual(old.save_api.archipelago_save_path(), legacy)


class TestTellingTheMod(SessionSavesCase):
    def test_the_connect_block_names_the_save_slot_after_the_session_line(self):
        core = self.core("SeedA")
        self.connect(core)
        lines = self.inbox(core)
        self.assertIn("SAVE_SLOT Playerarchi_SeedA_HWtest", lines)
        self.assertLess(lines.index("SESSION_SYNC SeedA_HWtest"), lines.index("SAVE_SLOT Playerarchi_SeedA_HWtest"))
        self.assertLess(lines.index("RANDOMIZED_GROUPS prizes=1 faz_tokens=1 tapes=1"), lines.index("SAVE_SLOT Playerarchi_SeedA_HWtest"))

    def test_every_connect_repeats_the_line_so_a_game_restart_replays_it(self):
        core = self.core("SeedA")
        self.connect(core)
        self.connect(core)
        self.assertEqual(self.inbox(core).count("SAVE_SLOT Playerarchi_SeedA_HWtest"), 2)

    def test_the_name_in_the_line_is_safe_for_the_mod(self):
        core = self.core("../Seed X", "Né on")
        self.connect(core)
        line = next(l for l in self.inbox(core) if l.startswith("SAVE_SLOT "))
        self.assertRegex(line, r"^SAVE_SLOT [A-Za-z0-9_-]+$")


if __name__ == "__main__":
    unittest.main()
