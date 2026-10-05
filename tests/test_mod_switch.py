"""`archipelago_enabled = false` in the mod's config.lua turns the whole mod off (vanilla game, normal save).

The real `Scripts/main.lua` is run in a Lua interpreter (lupa) from a temporary copy of the mod folder, with the game's functions stubbed. What this cannot
tell: that UE4SS really leaves the game untouched (no hook is registered, so nothing can be), which is only confirmed by a launch.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from lupa import LuaRuntime
except ImportError:  # pragma: no cover
    LuaRuntime = None

from tests.test_lua_logic import PRELUDE

project_root = Path(__file__).resolve().parent.parent
MOD_SOURCE = project_root / "ue4ss_mod" / "FNAFHWArchipelago"
OFF_LINE = "archipelago_enabled = false in config.lua: the mod is OFF"


@unittest.skipIf(LuaRuntime is None, "lupa is not installed")
class TestArchipelagoEnabledSwitch(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="fnafhw_switch_"))
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.mod = self.temp / "FNAFHWArchipelago"
        shutil.copytree(MOD_SOURCE, self.mod, ignore=shutil.ignore_patterns("config.lua", "*.log", "ap_class_*.txt"))
        self.bridge = self.temp / "bridge"
        self.bridge.mkdir()
        shutil.copy(MOD_SOURCE / "locations.json", self.bridge / "locations.json")

    def run_mod(self, extra_config=""):
        (self.mod / "config.lua").write_text(
            f'return {{\n    bridge_dir = "{self.bridge.as_posix()}",\n    {extra_config}\n}}\n', encoding="utf-8")
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute(PRELUDE)
        lua.execute("""
            ExecuteInGameThread = function(fn) end
            RegisterKeyBind = function() end
            StaticFindObject = nil
        """)
        main = self.mod / "Scripts" / "main.lua"
        loader = lua.eval("function(src, name) return load(src, name) end")
        chunk = loader(main.read_text(encoding="utf-8"), "@" + main.as_posix())
        chunk()
        log = lua.globals()["__log"]
        self.log = [log[i] for i in range(1, len(log) + 1)]
        self.hooks = len(list(lua.globals()["__hooks"].keys()))
        self.commands = len(list(lua.globals()["__cmds"].keys()))
        self.loops = len(lua.globals()["__loops"])

    def bridge_files(self):
        return sorted(p.name for p in self.bridge.iterdir() if p.name != "locations.json")

    def test_false_turns_the_whole_mod_off(self):
        self.run_mod("archipelago_enabled = false,")
        self.assertTrue(any(OFF_LINE in line for line in self.log), self.log)
        self.assertEqual((self.hooks, self.commands, self.loops), (0, 0, 0))
        self.assertEqual(self.bridge_files(), [])  # no inbox, no outbox: the bridge is not touched
        self.assertFalse(any("Initializing Archipelago Mod" in line for line in self.log))
        self.assertFalse(any("Hook registered" in line or "SaveSlotName" in line for line in self.log))

    def test_a_missing_key_keeps_the_mod_on(self):
        self.run_mod()
        self.assertFalse(any(OFF_LINE in line for line in self.log))
        self.assertTrue(any("Initializing Archipelago Mod" in line for line in self.log), self.log)
        self.assertGreater(self.hooks + self.commands + self.loops, 0)
        self.assertEqual(self.bridge_files(), ["ap_inbox.txt", "ap_outbox.txt"])

    def test_only_the_value_false_disables_it(self):
        for value in ("true", '"false"', "0", "nil"):
            with self.subTest(value=value):
                self.run_mod(f"archipelago_enabled = {value},")
                self.assertFalse(any(OFF_LINE in line for line in self.log), self.log)
                self.assertTrue(any("Initializing Archipelago Mod" in line for line in self.log))

    def test_the_documented_line_is_in_the_example_and_the_install_guide(self):
        example = (MOD_SOURCE / "config.lua.example").read_text(encoding="utf-8")
        self.assertIn("-- archipelago_enabled = false,", example)  # commented out: the example keeps the mod on
        guide = (project_root / "docs" / "installation.md").read_text(encoding="utf-8")
        self.assertIn("archipelago_enabled = false,", guide)
        self.assertIn("FNAFHWArchipelago : 0", guide)


if __name__ == "__main__":
    unittest.main()
