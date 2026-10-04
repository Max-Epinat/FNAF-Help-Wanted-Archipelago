"""What ships to players stays consistent: the apworld manifest, the yaml template, and the release package.

The yaml template is checked against options.py (read statically: importing it needs Archipelago), so adding or renaming an option
without updating the template fails here instead of surprising a player.
"""

import ast
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
WORLD = project_root / "fnaf_help_wanted"
TEMPLATE = project_root / "templates" / "Five Nights at Freddy's Help Wanted.yaml"


def load_data():
    spec = importlib.util.spec_from_file_location("_fnafhw_pkg_data", WORLD / "data.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def project_version() -> str:
    return re.search(r'^version\s*=\s*"([^"]+)"', (project_root / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)


def option_classes():
    """{class name: {"choices": {name: value}, "fields": ...}} and the dataclass fields {option name: class name}."""
    tree = ast.parse((WORLD / "options.py").read_text(encoding="utf-8"))
    classes, fields = {}, {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "FNAFHWOptions":
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    fields[stmt.target.id] = stmt.annotation.id
        elif isinstance(node, ast.ClassDef):
            choices = {}
            ranges = {}
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
                    name = stmt.targets[0].id
                    if name.startswith("option_"):
                        choices[name[len("option_"):]] = stmt.value.value
                    elif name in ("range_start", "range_end", "default"):
                        ranges[name] = stmt.value.value
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            classes[node.name] = {"choices": choices, "ranges": ranges, "bases": bases}
    return classes, fields


def template_options() -> dict[str, list[str]]:
    """{option name: [value keys]} from the game section of the yaml template (plain text, no yaml dependency)."""
    options: dict[str, list[str]] = {}
    current = None
    in_game = False
    for line in TEMPLATE.read_text(encoding="utf-8").splitlines():
        if line.startswith("'Five Nights at Freddy''s: Help Wanted':"):
            in_game = True
            continue
        if not in_game:
            continue
        match = re.match(r"^  ([a-z_]+):\s*$", line)
        if match:
            current = match.group(1)
            options[current] = []
            continue
        value = re.match(r"^    ('?[A-Za-z0-9_-]+'?):\s*(\d+)", line)
        if value and current:
            options[current].append(value.group(1).strip("'"))
    return options


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((WORLD / "archipelago.json").read_text(encoding="utf-8"))

    def test_game_name_matches_the_world(self):
        self.assertEqual(self.manifest["game"], load_data().GAME_NAME)

    def test_version_matches_pyproject(self):
        self.assertEqual(self.manifest["world_version"], project_version())

    def test_has_the_fields_archipelago_reads(self):
        for key in ("game", "authors", "world_version", "minimum_ap_version", "compatible_version", "version"):
            self.assertIn(key, self.manifest)


class TestYamlTemplate(unittest.TestCase):
    def setUp(self):
        self.classes, self.fields = option_classes()
        self.template = template_options()

    def test_every_world_option_is_in_the_template_and_nothing_else(self):
        generic = {"progression_balancing", "accessibility", "local_items", "non_local_items", "start_inventory",
                   "start_hints", "start_location_hints", "exclude_locations", "priority_locations", "item_links", "plando_items"}
        self.assertEqual(set(self.template) - generic, set(self.fields))

    def test_every_choice_and_toggle_value_is_offered(self):
        for option, class_name in self.fields.items():
            info = self.classes.get(class_name, {"choices": {}, "ranges": {}, "bases": []})  # imported ones (DeathLink) are not defined here
            if info["choices"]:
                self.assertEqual(set(self.template[option]), set(info["choices"]), option)
            elif "Toggle" in info["bases"] or "DeathLink" in info["bases"] or class_name == "DeathLink":
                self.assertEqual(set(self.template[option]), {"false", "true"}, option)

    def test_death_link_is_offered_and_off_by_default(self):
        self.assertIn("death_link", self.template)
        text = TEMPLATE.read_text(encoding="utf-8")
        block = text[text.index("  death_link:"):text.index("  unlock_mode:")]
        self.assertIn("'false': 50", block)
        self.assertIn("'true': 0", block)

    def test_range_defaults_are_the_world_defaults(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        for option, class_name in self.fields.items():
            ranges = self.classes.get(class_name, {"ranges": {}})["ranges"]
            if "range_end" in ranges:
                block = text[text.index(f"  {option}:"):]
                self.assertRegex(block, rf"\n    {ranges['default']}: 50")

    def test_the_text_shown_to_players_is_not_stale(self):
        text = TEMPLATE.read_text(encoding="utf-8").lower()
        self.assertNotIn("previous level of its chain", text)  # the chain rule was removed
        self.assertIn("the item alone unlocks the level", text)

    def test_the_options_docstring_matches_the_template_claim(self):
        source = (WORLD / "options.py").read_text(encoding="utf-8")
        self.assertNotIn("previous level of its chain", source)
        self.assertIn("the item alone unlocks the level", source)


def short_temp_folder(parent: Path) -> Path:
    """A temp folder given as an 8.3 short path (RUNNER~1 style), like on GitHub's Windows runners. Falls back to the plain path."""
    import ctypes
    long_dir = parent / "fnafhw a long temp folder name"
    long_dir.mkdir(exist_ok=True)
    buffer = ctypes.create_unicode_buffer(1024)
    if ctypes.windll.kernel32.GetShortPathNameW(str(long_dir), buffer, 1024) and buffer.value:
        return Path(buffer.value)
    return long_dir


@unittest.skipUnless(sys.platform == "win32", "release packaging is a PowerShell script")
class TestReleasePackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        cls.out = Path(tempfile.mkdtemp(prefix="fnafhw_release_"))
        # Seen on GitHub Actions: the build's temp folder was a short path while file names came back long, which cut entry names in
        # the middle ("ge/fnaf_help_wanted/..."). Build the way the runner does, and with a compiled cache present in the world folder.
        cls.short_temp = short_temp_folder(cls.out)
        env = dict(os.environ, TEMP=str(cls.short_temp), TMP=str(cls.short_temp))
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(project_root / "scripts" / "build-release.ps1"),
             "-OutputDir", str(cls.out)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        cls.result = result
        zips = list(cls.out.glob("*.zip"))
        cls.zip_path = zips[0] if zips else None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def names(self):
        self.assertIsNotNone(self.zip_path, self.result.stdout + self.result.stderr)
        with zipfile.ZipFile(self.zip_path) as z:
            return z.namelist()

    def test_build_succeeds_and_is_named_after_the_version(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertIn(project_version(), self.zip_path.name)

    def test_contains_everything_a_player_needs(self):
        names = [n.split("/", 1)[1] for n in self.names() if "/" in n]
        for expected in ("fnaf_help_wanted.apworld", "install-mod.ps1", "README.md", "LICENSE",
                         "templates/Five Nights at Freddy's Help Wanted.yaml",
                         "mod/FNAFHWArchipelago/Scripts/main.lua", "mod/FNAFHWArchipelago/locations.json"):
            self.assertIn(expected, names)

    def test_contains_nothing_machine_specific_or_private(self):
        for name in self.names():
            lower = name.lower()
            self.assertFalse(lower.endswith(("config.lua", ".sav", ".log", ".bak", ".lock")), name)
            self.assertNotIn("/scratch/", lower)
            self.assertNotIn("/.git", lower)
            self.assertNotIn("/tests/", lower)

    def test_zip_entries_use_forward_slashes_in_the_release_and_in_the_apworld(self):
        # ZipInfo.filename is normalized by Python on Windows, so look at the names as stored (orig_filename): a zip with
        # backslashes does not extract properly on Linux, for example on an Archipelago host that loads the apworld there.
        with zipfile.ZipFile(self.zip_path) as z:
            self.assertEqual([i.orig_filename for i in z.infolist() if "\\" in i.orig_filename], [])
            apworld = [n for n in z.namelist() if n.endswith("fnaf_help_wanted.apworld")][0]
            (Path(self.out) / "stored.apworld").write_bytes(z.read(apworld))
        with zipfile.ZipFile(Path(self.out) / "stored.apworld") as z:
            names = [i.orig_filename for i in z.infolist()]
        self.assertEqual([n for n in names if "\\" in n], [])
        self.assertIn("fnaf_help_wanted/__init__.py", names)

    def test_the_apworld_has_only_clean_entries_even_with_a_short_temp_folder(self):
        with zipfile.ZipFile(self.zip_path) as z:
            apworld = [n for n in z.namelist() if n.endswith("fnaf_help_wanted.apworld")][0]
            (Path(self.out) / "clean.apworld").write_bytes(z.read(apworld))
        with zipfile.ZipFile(Path(self.out) / "clean.apworld") as z:
            names = z.namelist()
        self.assertTrue(all(n.startswith("fnaf_help_wanted/") for n in names), names)
        self.assertEqual([n for n in names if "__pycache__" in n or n.endswith(".pyc")], [])

    def test_the_packaged_apworld_is_complete(self):
        with zipfile.ZipFile(self.zip_path) as z:
            apworld = [n for n in z.namelist() if n.endswith("fnaf_help_wanted.apworld")][0]
            inner = Path(self.out) / "inner.apworld"
            inner.write_bytes(z.read(apworld))
        with zipfile.ZipFile(inner) as z:
            names = z.namelist()
        for expected in ("fnaf_help_wanted/__init__.py", "fnaf_help_wanted/archipelago.json", "fnaf_help_wanted/client.py",
                         "fnaf_help_wanted/bridge_core.py", "fnaf_help_wanted/save_reader.py"):
            self.assertIn(expected, names)
        self.assertFalse([n for n in names if n.endswith("locations.json")], "the stale locations.json must not ship")


if __name__ == "__main__":
    unittest.main()
