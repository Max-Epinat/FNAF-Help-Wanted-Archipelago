"""The mod side of one save per multiworld: the client names the save slot (`SAVE_SLOT <name>`, in every connect block) and the mod uses it
instead of the fixed `Playerarchi`. Run in a real Lua interpreter (lupa), with the game's save functions stubbed.

What this cannot show: whether the real game loads and writes a slot with such a name (the mod already forced `Playerarchi` the same way,
VERIFIED in game 2026-10-05 with the fixed name; a per-session name is HYPOTHESIS until seen).
"""

import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tests.test_lua_logic import LIB, LuaCase

GI = "/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:"


class TestInboxLine(LuaCase):
    def deliver(self, text, **handlers):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ap_inbox.txt").write_text(text, encoding="utf-8")
            env = self.lua.table(
                outbox_path=str(Path(tmp) / "ap_outbox.txt"), inbox_path=str(Path(tmp) / "ap_inbox.txt"), bridge_dir=tmp,
                emitted_location_names=self.lua.table(), on_item=lambda *a: None)
            for key, value in handlers.items():
                env[key] = value
            self.load("bridge_io.lua")(env).poll_inbox()

    def test_the_line_reaches_its_handler_with_the_name(self):
        seen = []
        self.deliver("SAVE_SLOT Playerarchi_SeedA_HWtest\n", on_save_slot=lambda name: seen.append(str(name)))
        self.assertEqual(seen, ["Playerarchi_SeedA_HWtest"])

    def test_it_is_not_mistaken_for_its_neighbours_and_they_are_not_mistaken_for_it(self):
        calls = []
        self.deliver(
            "SESSION_SYNC s1\nSAVE_SLOT Playerarchi_s1\nSLOT_DATA {}\nDEATH_LINK_MODE 1\n",
            on_session_sync=lambda spec: calls.append(("sync", str(spec))),
            on_save_slot=lambda name: calls.append(("slot", str(name))),
            on_death_link_mode=lambda spec: calls.append(("mode", str(spec))))
        self.assertEqual(calls, [("sync", "s1"), ("slot", "Playerarchi_s1"), ("mode", "1")])

    def test_an_old_mod_style_environment_without_a_handler_ignores_the_line(self):
        self.deliver("SAVE_SLOT Playerarchi_x\n")  # must not raise

    def test_only_the_last_connect_block_of_the_history_counts_at_launch(self):
        seen = []
        self.deliver("CONNECTED\nSESSION_SYNC a\nSAVE_SLOT Playerarchi_a\nCONNECTED\nSESSION_SYNC b\nSAVE_SLOT Playerarchi_b\n",
                     on_save_slot=lambda name: seen.append(str(name)))
        self.assertEqual(seen, ["Playerarchi_b"])

    def test_main_lua_wires_the_line_and_resets_the_slot_at_every_session_sync(self):
        main = (LIB.parent / "main.lua").read_text(encoding="utf-8")
        self.assertIn("on_save_slot", main)
        self.assertIn("exact_hooks.set_save_slot(name)", main)
        sync = main.split("on_session_sync = function(session_id)", 1)[1].split("end,", 1)[0]
        self.assertIn("set_save_slot(nil)", sync)  # an old client sends no SAVE_SLOT line: back to the shared Playerarchi


class TestExactHooksUseTheSlot(LuaCase):
    def setUp(self):
        super().setUp()
        self.lua.execute("""
            __loaded, __asked = {}, {}
            __disk = { Playerarchi = true, Playerarchi_SeedA_HWtest = true }
            __statics = {
                DoesSaveGameExist = function(self, slot, index) __asked[#__asked + 1] = slot; return __disk[slot] == true end,
                LoadGameFromSlot = function(self, slot, index)
                    __loaded[#__loaded + 1] = slot
                    return { IsValid = function() return true end, from_slot = slot }
                end,
            }
            StaticFindObject = function(path) return __statics end
            __gi = { SaveSlotName = "Player00", IsValid = function() return true end, SaveGameRef = {} }
        """)
        self.api = self.load("exact_hooks.lua").init(self.lua.table(
            APBridge=self.lua.table(send_location_check_name=lambda n: None, send_goal=lambda: None),
            locations_data=self.lua.table(row_id_to_location=self.lua.table(), location_name_to_id=self.lua.table()),
            emitted_location_names=self.lua.table(), baseline_location_names=self.lua.table(),
            game_instance=lambda: self.lua.globals()["__gi"]))
        self.gi = self.lua.globals()["__gi"]
        self.lua.execute("__loaded, __asked = {}, {}; __gi.SaveSlotName = 'Player00'")  # forget what init did: the game starts on its normal slot

    def loaded(self):
        t = self.lua.globals()["__loaded"]
        return [str(t[i]) for i in range(1, len(t) + 1)]

    def test_without_a_name_the_shared_playerarchi_is_used_as_before(self):
        self.api.try_register_all()
        self.assertEqual(str(self.gi.SaveSlotName), "Playerarchi")
        self.assertEqual(self.loaded(), ["Playerarchi"])

    def test_the_clients_name_is_enforced_and_that_save_is_loaded_into_memory(self):
        self.assertTrue(self.api.set_save_slot("Playerarchi_SeedA_HWtest"))
        self.api.try_register_all()
        self.assertEqual(str(self.gi.SaveSlotName), "Playerarchi_SeedA_HWtest")
        self.assertEqual(self.loaded(), ["Playerarchi_SeedA_HWtest"])
        self.assertEqual(str(self.gi.SaveGameRef.from_slot), "Playerarchi_SeedA_HWtest")

    def test_switching_session_while_the_game_runs_switches_the_save_once(self):
        self.api.try_register_all()  # shared save, as at launch
        self.api.set_save_slot("Playerarchi_SeedA_HWtest")
        self.api.try_register_all()
        self.api.try_register_all()  # the hook loop runs every second: nothing more is loaded
        self.assertEqual(self.loaded(), ["Playerarchi", "Playerarchi_SeedA_HWtest"])
        self.assertEqual(str(self.gi.SaveSlotName), "Playerarchi_SeedA_HWtest")

    def test_a_slot_with_no_file_on_disk_is_named_but_not_loaded(self):
        self.api.set_save_slot("Playerarchi_NoFile_x")
        self.api.try_register_all()
        self.assertEqual(str(self.gi.SaveSlotName), "Playerarchi_NoFile_x")
        self.assertEqual(self.loaded(), [])

    def test_nil_goes_back_to_the_shared_save(self):
        self.api.set_save_slot("Playerarchi_SeedA_HWtest")
        self.api.try_register_all()
        self.api.set_save_slot(None)
        self.api.try_register_all()
        self.assertEqual(str(self.gi.SaveSlotName), "Playerarchi")

    def test_a_name_that_is_not_a_safe_slot_name_is_refused_and_the_old_one_stays(self):
        self.api.set_save_slot("Playerarchi_SeedA_HWtest")
        for bad in ("", "../evil", "a b", "x.sav", "a/b", "Ünï", "x" * 300):
            self.assertFalse(self.api.set_save_slot(bad), bad)
        self.api.try_register_all()
        self.assertEqual(str(self.gi.SaveSlotName), "Playerarchi_SeedA_HWtest")
        self.assertTrue(any("not a safe save slot name" in line for line in self.log()))

    def test_the_save_hooks_keep_the_current_slot_not_the_fixed_one(self):
        self.api.set_save_slot("Playerarchi_SeedA_HWtest")
        self.api.try_register_all()
        for hook in ("InitSaveGame", "SaveGame"):
            self.gi.SaveSlotName = "Player00"  # the game resets it
            self.hooks()[GI + hook](self.gi)
            self.assertEqual(str(self.gi.SaveSlotName), "Playerarchi_SeedA_HWtest", hook)

    def test_the_source_no_longer_hard_codes_the_slot_outside_its_default(self):
        source = (LIB / "exact_hooks.lua").read_text(encoding="utf-8")
        code = "\n".join(line for line in source.splitlines() if not line.strip().startswith("--"))
        self.assertEqual(code.count('"Playerarchi"'), 1, "only the default may name it")


if __name__ == "__main__":
    unittest.main()
