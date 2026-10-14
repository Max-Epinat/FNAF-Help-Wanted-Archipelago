"""scripts/install-mod.bat: the double-click installer for players who do not want to open a terminal.

It only wraps install-mod.ps1 (which has its own tests in test_installer.py): it must pass the arguments through, keep the window open at the
end, hand back the installer's exit code, and, when the game folder is not found (exit code 2), ask for it and run the installer again.
The "ask" cases use a stub install-mod.ps1 so they do not depend on whether this machine has the real game. Windows only.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
BAT = project_root / "scripts" / "install-mod.bat"
SCRIPT = project_root / "scripts" / "install-mod.ps1"
MOD_SOURCE = project_root / "ue4ss_mod" / "FNAFHWArchipelago"


def run_bat(bat: Path, *args, stdin_text: str = "", cwd=None):
    result = subprocess.run(["cmd", "/c", str(bat), *args], input=stdin_text, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", cwd=cwd)
    return result.returncode, result.stdout + result.stderr


@unittest.skipUnless(sys.platform == "win32", "a Windows batch file")
class TestBatchFileExists(unittest.TestCase):
    def test_exists_next_to_the_installer_with_windows_line_endings(self):
        self.assertTrue(BAT.is_file(), "scripts/install-mod.bat is missing")
        data = BAT.read_bytes()
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""), "a batch file must use CRLF line endings")

    def test_calls_the_installer_that_sits_next_to_it_and_bypasses_the_execution_policy(self):
        text = BAT.read_text(encoding="utf-8")
        self.assertIn("%~dp0install-mod.ps1", text)
        self.assertIn("-ExecutionPolicy Bypass", text)
        self.assertIn("pause", text.lower(), "the window must stay open so the player can read the result")


@unittest.skipUnless(sys.platform == "win32", "a Windows batch file")
class TestWithTheRealInstaller(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fnafhw_bat_"))
        self.release = self.tmp / "release folder"  # a space in the path, like a real Downloads folder
        (self.release / "mod").mkdir(parents=True)
        shutil.copytree(MOD_SOURCE, self.release / "mod" / "FNAFHWArchipelago", ignore=shutil.ignore_patterns("config.lua", "*.log"))
        shutil.copy(SCRIPT, self.release / "install-mod.ps1")
        shutil.copy(BAT, self.release / "install-mod.bat")
        (self.release / "fnaf_help_wanted.apworld").write_bytes(b"PK-fake-apworld")
        self.game = self.tmp / "game"
        self.win64 = self.game / "freddys" / "Binaries" / "Win64"
        (self.win64 / "Mods").mkdir(parents=True)
        for name in ("UE4SS.dll", "dwmapi.dll", "freddys-Win64-Shipping.exe"):
            (self.win64 / name).write_bytes(b"x")
        self.archipelago = self.tmp / "Archipelago"
        (self.archipelago / "custom_worlds").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def args(self, game=None):
        return ["-GameRoot", str(game or self.game), "-ArchipelagoDir", str(self.archipelago)]

    def test_installs_and_returns_zero(self):
        code, out = run_bat(self.release / "install-mod.bat", *self.args())
        self.assertEqual(code, 0, out)
        self.assertTrue((self.win64 / "Mods" / "FNAFHWArchipelago" / "Scripts" / "main.lua").is_file())
        self.assertIn("FNAFHWArchipelago : 1", (self.win64 / "Mods" / "mods.txt").read_text(encoding="utf-8"))

    def test_runs_from_another_working_directory(self):
        code, out = run_bat(self.release / "install-mod.bat", *self.args(), cwd=self.game)
        self.assertEqual(code, 0, out)

    def test_hands_back_the_installers_exit_code(self):
        (self.win64 / "UE4SS.dll").unlink()
        code, out = run_bat(self.release / "install-mod.bat", *self.args())
        self.assertEqual(code, 3, out)
        self.assertIn("https://github.com/UE4SS-RE/RE-UE4SS/releases", out)


@unittest.skipUnless(sys.platform == "win32", "a Windows batch file")
class TestAsksForTheGameFolder(unittest.TestCase):
    """A stub installer: exit code 2 (game not found) unless it is given -GameRoot, and it records the arguments it received."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fnafhw_bat_stub_"))
        self.folder = self.tmp / "release folder"
        self.folder.mkdir()
        shutil.copy(BAT, self.folder / "install-mod.bat")
        self.record = self.tmp / "args.txt"
        (self.folder / "install-mod.ps1").write_text(
            'param([string]$GameRoot = "", [switch]$CheckOnly)\r\n'
            f'Add-Content -Path "{self.record}" -Value ("GameRoot=[" + $GameRoot + "] CheckOnly=" + $CheckOnly.IsPresent)\r\n'
            'if ($GameRoot -eq "") { exit 2 }\r\nexit 0\r\n', encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def calls(self):
        return self.record.read_text(encoding="utf-8").splitlines() if self.record.exists() else []

    def test_asks_and_installs_with_the_pasted_folder(self):
        code, out = run_bat(self.folder / "install-mod.bat", stdin_text="D:\\SteamLibrary\\steamapps\\common\\FNAFVRHelpWanted\r\n")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.calls(), ["GameRoot=[] CheckOnly=False",
                                        "GameRoot=[D:\\SteamLibrary\\steamapps\\common\\FNAFVRHelpWanted] CheckOnly=False"])

    def test_a_pasted_folder_with_quotes_and_a_trailing_backslash_still_works(self):
        # Explorer's "copy as path" adds quotes; a trailing backslash before the closing quote would swallow it
        code, out = run_bat(self.folder / "install-mod.bat", stdin_text='"D:\\Games\\FNAF Help Wanted\\"\r\n')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.calls()[-1], "GameRoot=[D:\\Games\\FNAF Help Wanted] CheckOnly=False")

    def test_an_empty_answer_gives_up_with_the_installers_code(self):
        code, out = run_bat(self.folder / "install-mod.bat", stdin_text="\r\n")
        self.assertEqual(code, 2, out)
        self.assertEqual(len(self.calls()), 1, "no second run without a folder")

    def test_does_not_ask_when_a_game_folder_was_given(self):
        code, out = run_bat(self.folder / "install-mod.bat", "-GameRoot", "D:\\x", stdin_text="")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.calls(), ["GameRoot=[D:\\x] CheckOnly=False"])

    def test_other_arguments_are_kept_on_the_second_run(self):
        code, out = run_bat(self.folder / "install-mod.bat", "-CheckOnly", stdin_text="D:\\x\r\n")
        self.assertEqual(self.calls(), ["GameRoot=[] CheckOnly=True", "GameRoot=[D:\\x] CheckOnly=True"], out)

    def test_arguments_are_passed_through(self):
        code, out = run_bat(self.folder / "install-mod.bat", "-GameRoot", "D:\\x", "-CheckOnly")
        self.assertEqual(self.calls(), ["GameRoot=[D:\\x] CheckOnly=True"], out)


if __name__ == "__main__":
    unittest.main()
