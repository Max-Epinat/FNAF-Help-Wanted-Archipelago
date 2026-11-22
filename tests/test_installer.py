"""scripts/install-mod.ps1 against a fake game folder, a fake Archipelago folder and a fake release layout.

The release layout is what a player gets from the zip: install-mod.ps1 with mod\\FNAFHWArchipelago and fnaf_help_wanted.apworld next to
it. Nothing here touches a real game or Archipelago installation. Windows only (PowerShell).
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
SCRIPT = project_root / "scripts" / "install-mod.ps1"
MOD_SOURCE = project_root / "ue4ss_mod" / "FNAFHWArchipelago"


@unittest.skipUnless(sys.platform == "win32", "the installer is a Windows PowerShell script")
class InstallerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fnafhw_install_"))
        # a release folder, as unpacked from the zip
        self.release = self.tmp / "release"
        (self.release / "mod").mkdir(parents=True)
        shutil.copytree(MOD_SOURCE, self.release / "mod" / "FNAFHWArchipelago",
                        ignore=shutil.ignore_patterns("config.lua", "*.log", "ap_name_dump.txt"))
        # the developer's machine-specific config must never travel: simulate one in the source
        (self.release / "mod" / "FNAFHWArchipelago" / "config.lua").write_text(
            'return { bridge_dir = "C:/Users/someone/Desktop/elsewhere/bridge" }', encoding="utf-8")
        shutil.copy(SCRIPT, self.release / "install-mod.ps1")
        (self.release / "fnaf_help_wanted.apworld").write_bytes(b"PK-fake-apworld")
        # a fake game with UE4SS, and a fake Archipelago
        self.game = self.tmp / "game"
        self.win64 = self.game / "freddys" / "Binaries" / "Win64"
        (self.win64 / "Mods").mkdir(parents=True)
        for name in ("UE4SS.dll", "dwmapi.dll", "freddys-Win64-Shipping.exe"):
            (self.win64 / name).write_bytes(b"x")
        self.archipelago = self.tmp / "Archipelago"
        (self.archipelago / "custom_worlds").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_installer(self, *extra, cwd=None, game=None):
        args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.release / "install-mod.ps1"),
                "-GameRoot", str(game or self.game), "-ArchipelagoDir", str(self.archipelago), *extra]
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd or self.tmp)
        return result.returncode, result.stdout + result.stderr

    @property
    def mod(self):
        return self.win64 / "Mods" / "FNAFHWArchipelago"


class TestInstall(InstallerTestCase):
    def test_installs_mod_bridge_config_modstxt_and_apworld(self):
        code, out = self.run_installer()
        self.assertEqual(code, 0, out)
        self.assertTrue((self.mod / "Scripts" / "main.lua").is_file())
        self.assertTrue((self.mod / "Scripts" / "lib" / "death_link.lua").is_file())
        bridge = self.mod / "bridge"
        self.assertTrue((bridge / "locations.json").is_file(), "the mod looks for locations.json in its bridge folder")
        config = (self.mod / "config.lua").read_text(encoding="utf-8")
        self.assertIn(f'bridge_dir = "{bridge.as_posix()}"', config)
        self.assertNotIn("someone", config, "the config of the source machine must not be copied")
        self.assertEqual((self.win64 / "Mods" / "mods.txt").read_text(encoding="utf-8").count("FNAFHWArchipelago : 1"), 1)
        self.assertEqual((self.archipelago / "custom_worlds" / "fnaf_help_wanted.apworld").read_bytes(), b"PK-fake-apworld")

    def test_is_idempotent_and_keeps_other_mods_enabled(self):
        mods_txt = self.win64 / "Mods" / "mods.txt"
        mods_txt.write_text("SomeOtherMod : 1\r\n", encoding="utf-8")
        self.assertEqual(self.run_installer()[0], 0)
        self.assertEqual(self.run_installer()[0], 0)
        text = mods_txt.read_text(encoding="utf-8")
        self.assertEqual(text.count("FNAFHWArchipelago : 1"), 1)
        self.assertIn("SomeOtherMod : 1", text)

    def test_custom_bridge_folder_is_used(self):
        custom = self.tmp / "my bridge"
        code, out = self.run_installer("-BridgeDir", str(custom))
        self.assertEqual(code, 0, out)
        self.assertTrue((custom / "locations.json").is_file())
        self.assertIn(f'bridge_dir = "{custom.as_posix()}"', (self.mod / "config.lua").read_text(encoding="utf-8"))
        self.assertFalse((self.mod / "bridge").exists())

    def test_skip_apworld(self):
        code, out = self.run_installer("-SkipApworld")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.archipelago / "custom_worlds" / "fnaf_help_wanted.apworld").exists())

    def test_without_archipelago_the_mod_is_installed_and_the_apworld_is_explained(self):
        shutil.rmtree(self.archipelago)
        code, out = self.run_installer()
        self.assertEqual(code, 0, out)
        self.assertTrue((self.mod / "Scripts" / "main.lua").is_file())
        self.assertIn("Install fnaf_help_wanted.apworld yourself", out)

    def test_works_from_a_different_working_directory(self):
        code, out = self.run_installer(cwd=self.game)
        self.assertEqual(code, 0, out)


class TestUpdateKeepsThePlayersChoices(InstallerTestCase):
    """Re-running the installer (an update) must not throw away what the player set up."""

    def config(self):
        return (self.mod / "config.lua").read_text(encoding="utf-8")

    def test_config_settings_survive_and_only_bridge_dir_moves(self):
        self.assertEqual(self.run_installer()[0], 0)
        (self.mod / "config.lua").write_text(
            f'return {{\n    -- my notes\n    bridge_dir = "{(self.mod / "bridge").as_posix()}",\n    enable_debug_commands = true,\n'
            '    -- bridge_dir = "this comment is not the setting",\n    enable_research_tools = true,\n}\n', encoding="utf-8")
        custom = self.tmp / "my bridge"
        code, out = self.run_installer("-BridgeDir", str(custom))
        self.assertEqual(code, 0, out)
        config = self.config()
        self.assertIn(f'bridge_dir = "{custom.as_posix()}",', config)
        self.assertEqual(config.count(f'bridge_dir = "{custom.as_posix()}"'), 1)
        for kept in ("-- my notes", "enable_debug_commands = true,", "enable_research_tools = true,", '-- bridge_dir = "this comment is not the setting",'):
            self.assertIn(kept, config)
        self.assertIn("your settings were kept", out)

    def test_a_config_without_bridge_dir_gets_one_and_keeps_its_other_lines(self):
        self.assertEqual(self.run_installer()[0], 0)
        (self.mod / "config.lua").write_text("return {\n    enable_debug_commands = true,\n}\n", encoding="utf-8")
        self.assertEqual(self.run_installer()[0], 0)
        config = self.config()
        self.assertIn(f'bridge_dir = "{(self.mod / "bridge").as_posix()}",', config)
        self.assertIn("enable_debug_commands = true,", config)

    def test_a_config_the_mod_could_not_read_is_replaced_by_a_fresh_one(self):
        self.assertEqual(self.run_installer()[0], 0)
        (self.mod / "config.lua").write_text("this is not lua config at all", encoding="utf-8")
        self.assertEqual(self.run_installer()[0], 0)
        config = self.config()
        self.assertTrue(config.startswith("return {"))
        self.assertIn(f'bridge_dir = "{(self.mod / "bridge").as_posix()}"', config)
        self.assertNotIn("ui_key", config)  # keys nothing ever read are not written any more

    def test_a_mod_the_player_switched_off_stays_off_and_the_installer_says_so(self):
        self.assertEqual(self.run_installer()[0], 0)
        (self.mod / "config.lua").write_text(
            f'return {{\n    bridge_dir = "{(self.mod / "bridge").as_posix()}",\n    archipelago_enabled = false,\n}}\n', encoding="utf-8")
        mods_txt = self.win64 / "Mods" / "mods.txt"
        mods_txt.write_text("SomeOtherMod : 1\r\nFNAFHWArchipelago : 0\r\n", encoding="utf-8")
        code, out = self.run_installer()
        self.assertEqual(code, 0, out)
        self.assertIn("archipelago_enabled = false,", self.config())
        text = mods_txt.read_text(encoding="utf-8")
        self.assertEqual(text.count("FNAFHWArchipelago"), 1)  # no second line next to the ": 0" one
        self.assertIn("FNAFHWArchipelago : 0", text)
        self.assertIn("archipelago_enabled = false", out)
        self.assertIn("mods.txt has 'FNAFHWArchipelago : 0'", out)

    def test_mods_txt_without_a_final_line_break_keeps_its_last_entry_intact(self):
        mods_txt = self.win64 / "Mods" / "mods.txt"
        mods_txt.write_bytes(b"SomeOtherMod : 1")
        self.assertEqual(self.run_installer()[0], 0)
        lines = mods_txt.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, ["SomeOtherMod : 1", "FNAFHWArchipelago : 1"])

    def test_files_of_a_previous_version_are_removed_from_scripts_and_nothing_else(self):
        self.assertEqual(self.run_installer()[0], 0)
        stale = self.mod / "Scripts" / "lib" / "module_removed_in_a_later_version.lua"
        stale_dir_file = self.mod / "Scripts" / "old_folder" / "old.lua"
        stale_dir_file.parent.mkdir()
        keep = [self.mod / "bridge" / "ap_inbox.txt", self.mod / "ap_name_dump.txt", self.mod / "UE4SS_notes.txt"]
        for path in (stale, stale_dir_file, *keep):
            path.write_text("x", encoding="utf-8")
        code, out = self.run_installer()
        self.assertEqual(code, 0, out)
        self.assertFalse(stale.exists())
        self.assertFalse(stale_dir_file.exists())
        for path in keep:
            self.assertTrue(path.exists(), path.name)
        for module in (MOD_SOURCE / "Scripts").rglob("*.lua"):
            self.assertTrue((self.mod / "Scripts" / module.relative_to(MOD_SOURCE / "Scripts")).is_file(), module.name)
        self.assertIn("2 file(s) of a previous version removed", out)


class TestScripts(unittest.TestCase):
    SCRIPTS = project_root / "scripts"

    @unittest.skipUnless(sys.platform == "win32", "PowerShell")
    def test_every_powershell_script_parses(self):
        for script in sorted(self.SCRIPTS.glob("*.ps1")):
            command = ("$e = $null; $t = $null; [void][System.Management.Automation.Language.Parser]::ParseFile("
                       f"'{script}', [ref]$t, [ref]$e); $e | ForEach-Object {{ $_.Message + ' @' + $_.Extent.StartLineNumber }}")
            result = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.stdout.strip(), "", f"{script.name}: {result.stdout}")

    def test_a_virtual_environment_is_only_deleted_after_checking_it_is_this_repositorys(self):
        for name in ("launch-game.ps1", "run-client.ps1"):
            text = (self.SCRIPTS / name).read_text(encoding="utf-8")
            self.assertLess(text.index("Refusing to delete"), text.index("Remove-Item -Path $venvDir"), name)

    def test_the_client_script_installs_dependencies_only_when_they_changed(self):
        text = (self.SCRIPTS / "run-client.ps1").read_text(encoding="utf-8")
        self.assertNotIn("--upgrade pip", text)
        self.assertIn("requirements.sha256", text)
        self.assertLess(text.index("Get-FileHash"), text.index("pip install -r"))


class TestPrerequisites(InstallerTestCase):
    def test_missing_ue4ss_stops_with_a_link_and_installs_nothing(self):
        (self.win64 / "UE4SS.dll").unlink()
        code, out = self.run_installer()
        self.assertEqual(code, 3, out)
        self.assertIn("https://github.com/UE4SS-RE/RE-UE4SS/releases", out)
        self.assertIn("not included in this package", out)
        self.assertFalse(self.mod.exists())
        self.assertFalse((self.archipelago / "custom_worlds" / "fnaf_help_wanted.apworld").exists())

    def test_missing_proxy_dll_counts_as_missing_ue4ss(self):
        (self.win64 / "dwmapi.dll").unlink()
        self.assertEqual(self.run_installer()[0], 3)

    def test_xinput_proxy_is_accepted(self):
        (self.win64 / "dwmapi.dll").unlink()
        (self.win64 / "xinput1_3.dll").write_bytes(b"x")
        self.assertEqual(self.run_installer()[0], 0)

    def test_game_not_found_reports_how_to_point_at_it(self):
        code, out = self.run_installer(game=self.tmp / "no_such_game")
        self.assertNotEqual(code, 0)
        self.assertIn("freddys", out)

    def test_check_only_changes_nothing(self):
        code, out = self.run_installer("-CheckOnly")
        self.assertEqual(code, 0, out)
        self.assertIn("Check only", out)
        self.assertFalse(self.mod.exists())
        self.assertFalse((self.archipelago / "custom_worlds" / "fnaf_help_wanted.apworld").exists())


class TestRepositoryLayout(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "PowerShell")
    def test_repository_mode_finds_the_mod_in_ue4ss_mod(self):
        tmp = Path(tempfile.mkdtemp(prefix="fnafhw_repo_install_"))
        try:
            win64 = tmp / "game" / "freddys" / "Binaries" / "Win64"
            (win64 / "Mods").mkdir(parents=True)
            for name in ("UE4SS.dll", "dwmapi.dll"):
                (win64 / name).write_bytes(b"x")
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), "-GameRoot", str(tmp / "game"),
                 "-SkipApworld", "-BridgeDir", str(tmp / "bridge")],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((win64 / "Mods" / "FNAFHWArchipelago" / "Scripts" / "main.lua").is_file())
            self.assertTrue((tmp / "bridge" / "locations.json").is_file())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
