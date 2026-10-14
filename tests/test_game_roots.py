"""No hardcoded drive letters: where the game, Steam and Archipelago are is looked up, never assumed to be on C:.

A player report (game on D:, the mod never started) made us check; the places that named C: were the client's search for the mod's config.lua,
the mod's last-resort folder, the installer's candidate list and its default Archipelago folder. Everything here uses temporary folders only.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

try:
    from lupa import LuaRuntime
except ImportError:  # pragma: no cover
    LuaRuntime = None

from ap_client import bridge_core
from tests.test_lua_logic import PRELUDE

project_root = Path(__file__).resolve().parent.parent
MOD_SOURCE = project_root / "ue4ss_mod" / "FNAFHWArchipelago"
INSTALLER = project_root / "scripts" / "install-mod.ps1"

# files that must not name a drive: the code that finds things, not examples in a message (install-mod.bat shows D:\... as an example)
NO_DRIVE_LETTERS = [
    project_root / "ap_client" / "bridge_core.py",
    project_root / "ap_client" / "main.py",
    project_root / "scripts" / "generator_check.py",
    project_root / "scripts" / "install-mod.ps1",
    MOD_SOURCE / "Scripts" / "main.lua",
]
DRIVE_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]")


def make_game(root: Path, with_exe: bool = True) -> Path:
    win64 = root / "freddys" / "Binaries" / "Win64"
    (win64 / "Mods").mkdir(parents=True)
    if with_exe:
        (win64 / "freddys-Win64-Shipping.exe").write_bytes(b"x")
    return root


class TestNoDriveLettersInTheCode(unittest.TestCase):
    def test_no_file_names_a_drive(self):
        for path in NO_DRIVE_LETTERS:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                self.assertIsNone(DRIVE_PATH.search(line), f"{path.name}:{number}: {line.strip()}")


class TestSteamAndGameFolders(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fnafhw_roots_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.steam = self.tmp / "Steam"  # "Steam on one drive"
        (self.steam / "steamapps").mkdir(parents=True)
        self.library = self.tmp / "OtherDrive" / "SteamLibrary"  # "the game on another drive"
        self.game = make_game(self.library / "steamapps" / "common" / "FNAFVRHelpWanted")

    def write_vdf(self, *libraries: Path):
        body = "".join(f'"{i}" {{ "path" "{str(p).replace(chr(92), chr(92) * 2)}" }} ' for i, p in enumerate(libraries))
        (self.steam / "steamapps" / "libraryfolders.vdf").write_text('"libraryfolders" { ' + body + "}", encoding="utf-8")

    def test_steam_folders_come_from_the_registry_then_program_files_and_without_duplicates(self):
        registry = [Path("R1"), Path("R2")]
        env = {"ProgramFiles(x86)": "PF86", "ProgramFiles": "PF"}
        self.assertEqual(bridge_core.steam_install_dirs(env, registry), [Path("R1"), Path("R2"), Path("PF86") / "Steam", Path("PF") / "Steam"])
        self.assertEqual(bridge_core.steam_install_dirs({}, []), [])
        self.assertEqual(bridge_core.steam_install_dirs({"ProgramFiles": "R1/.."}, [Path("R1")]), [Path("R1"), Path("R1/..") / "Steam"])
        self.assertEqual(bridge_core.steam_install_dirs({}, [Path("R1"), Path("R1")]), [Path("R1")])

    def test_reading_the_registry_never_raises(self):
        found = bridge_core.registry_steam_dirs()
        self.assertIsInstance(found, list)

    def test_a_game_in_another_library_is_found_through_libraryfolders_vdf(self):
        self.write_vdf(self.steam, self.library)
        roots = bridge_core.candidate_game_roots({}, [self.steam])
        self.assertEqual(roots, [self.game])
        self.assertEqual(bridge_core.find_game_root({}, [self.steam]), self.game)

    def test_a_leftover_game_folder_without_the_game_is_skipped(self):
        stale = make_game(self.steam / "steamapps" / "common" / "FNAFVRHelpWanted", with_exe=False)  # first in line, but no game in it
        self.write_vdf(self.steam, self.library)
        self.assertTrue((stale / "freddys" / "Binaries" / "Win64").is_dir())
        self.assertEqual(bridge_core.candidate_game_roots({}, [self.steam]), [self.game])

    def test_the_first_real_game_wins_and_every_library_is_listed_once(self):
        first = make_game(self.steam / "steamapps" / "common" / "FNAFVRHelpWanted")
        self.write_vdf(self.steam, self.library, self.library)
        self.assertEqual(bridge_core.candidate_game_roots({}, [self.steam]), [first, self.game])
        self.assertEqual(bridge_core.find_game_root({}, [self.steam]), first)

    def test_the_environment_variable_comes_first_and_needs_no_check(self):
        self.write_vdf(self.steam, self.library)
        mine = self.tmp / "my game folder"
        roots = bridge_core.candidate_game_roots({"FNAFHW_GAME_ROOT": str(mine)}, [self.steam])
        self.assertEqual(roots, [mine, self.game])

    def test_an_environment_folder_without_the_game_does_not_hide_the_real_one(self):
        self.write_vdf(self.steam, self.library)
        empty = make_game(self.tmp / "no exe here", with_exe=False)
        self.assertEqual(bridge_core.find_game_root({"FNAFHW_GAME_ROOT": str(empty)}, [self.steam]), self.game)

    def test_a_folder_named_twice_is_listed_once(self):
        self.write_vdf(self.steam, self.library)
        self.assertEqual(bridge_core.candidate_game_roots({"FNAFHW_GAME_ROOT": str(self.game)}, [self.steam]), [self.game])

    @unittest.skipUnless(sys.platform == "win32", "the registry")
    def test_a_missing_registry_key_is_not_an_error(self):
        with unittest.mock.patch("winreg.OpenKey", side_effect=FileNotFoundError):
            self.assertEqual(bridge_core.registry_steam_dirs(), [])

    def test_nothing_found_gives_none_not_an_error(self):
        self.assertEqual(bridge_core.candidate_game_roots({}, []), [])
        self.assertIsNone(bridge_core.find_game_root({}, [self.tmp / "no steam here"]))
        (self.steam / "steamapps" / "libraryfolders.vdf").write_bytes(b"\xff\xfe not a vdf")  # unreadable text is not fatal
        self.assertEqual(bridge_core.candidate_game_roots({}, [self.steam]), [])

    def test_the_bridge_folder_is_found_in_a_game_on_another_drive(self):
        bridge = self.tmp / "bridge"
        bridge.mkdir()
        config = self.game / bridge_core.MOD_CONFIG_SUBPATH
        config.parent.mkdir(parents=True)
        config.write_text(f'return {{ bridge_dir = "{bridge.as_posix()}" }}', encoding="utf-8")
        self.write_vdf(self.steam, self.library)
        self.assertEqual(bridge_core.find_bridge_dir({}, bridge_core.candidate_game_roots({}, [self.steam])), bridge)


@unittest.skipIf(LuaRuntime is None, "lupa is not installed")
class TestModWithoutAKnownFolder(unittest.TestCase):
    def test_a_script_that_cannot_tell_where_it_is_stops_instead_of_guessing_a_path(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.execute(PRELUDE)
        lua.execute("ExecuteInGameThread = function(fn) end  RegisterKeyBind = function() end  StaticFindObject = nil")
        loader = lua.eval("function(src, name) return load(src, name) end")
        source = (MOD_SOURCE / "Scripts" / "main.lua").read_text(encoding="utf-8")
        loader(source, "=somewhere_without_a_path")()
        log = lua.globals()["__log"]
        lines = [log[i] for i in range(1, len(log) + 1)]
        self.assertTrue(any("could not work out its own folder" in line for line in lines), lines)
        self.assertFalse(any("Initializing Archipelago Mod" in line for line in lines), lines)
        self.assertEqual(len(list(lua.globals()["__hooks"].keys())), 0)


@unittest.skipUnless(sys.platform == "win32", "the installer is a PowerShell script")
class TestInstallerFindsThingsWithoutDriveLetters(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fnafhw_inst_roots_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.release = self.tmp / "release"
        (self.release / "mod").mkdir(parents=True)
        shutil.copytree(MOD_SOURCE, self.release / "mod" / "FNAFHWArchipelago", ignore=shutil.ignore_patterns("config.lua", "*.log"))
        shutil.copy(INSTALLER, self.release / "install-mod.ps1")
        (self.release / "fnaf_help_wanted.apworld").write_bytes(b"PK-fake-apworld")
        self.game = make_game(self.tmp / "game")
        for name in ("UE4SS.dll", "dwmapi.dll"):
            (self.game / "freddys" / "Binaries" / "Win64" / name).write_bytes(b"x")

    def run_installer(self, env_extra, *args):
        env = dict(os.environ, **env_extra)
        result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.release / "install-mod.ps1"), *args],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=self.tmp)
        return result.returncode, result.stdout + result.stderr

    # -CheckOnly everywhere: these tests only read what the installer reports, so nothing can be copied into a real Archipelago or game folder
    # even if the code under test is wrong (an earlier version of this test overwrote a real apworld that way).
    def test_the_game_folder_can_be_given_with_the_environment_variable(self):
        code, out = self.run_installer({"FNAFHW_GAME_ROOT": str(self.game)}, "-CheckOnly")
        self.assertEqual(code, 0, out)
        self.assertIn(str(self.game), out)
        self.assertFalse((self.game / "freddys" / "Binaries" / "Win64" / "Mods" / "FNAFHWArchipelago").exists())

    def test_the_default_archipelago_folder_follows_programdata(self):
        code, out = self.run_installer({"ProgramData": str(self.tmp / "ProgramData")}, "-GameRoot", str(self.game), "-CheckOnly")
        self.assertEqual(code, 0, out)
        self.assertIn(str(self.tmp / "ProgramData" / "Archipelago"), out)


if __name__ == "__main__":
    unittest.main()
