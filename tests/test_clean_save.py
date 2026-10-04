"""The clean Playerarchi.sav generator must start a new seed from a fresh game state, even when the template
(`Player00.sav`) is a completed save, and must never modify the template.

The synthetic template is built from the GVAS layout the generator itself walks; `100percent.sav` (a real completed
save, gitignored) is used as well when it is present.
"""

import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tests.gvas_fixtures import (
    bool_prop,
    completed_template,
    fstring,
    header,
    int_prop,
    int_set,
    name_array,
    object_set,
    set_prop,
    str_prop,
    walk,
)
from ap_client.save_reader import (
    _RESET_SETS,
    _empty_set_property,
    create_clean_playerarchi_data,
    ensure_clean_archipelago_save,
)

REAL_COMPLETED_SAVE = project_root / "100percent.sav"


EMPTY_SET = struct.pack("<II", 0, 0)


class TestEmptySetHelper(unittest.TestCase):
    def test_helper_is_byte_identical_to_the_original_hand_written_blocks(self):
        glitches = (
            b"\x12\x00\x00\x00CollectedGlitches\x00" b"\x0c\x00\x00\x00SetProperty\x00" b"\x08\x00\x00\x00\x00\x00\x00\x00"
            b"\x0c\x00\x00\x00IntProperty\x00" b"\x00" b"\x00\x00\x00\x00" b"\x00\x00\x00\x00"
        )
        coins = (
            b"\x0f\x00\x00\x00CollectedCoins\x00" b"\x0c\x00\x00\x00SetProperty\x00" b"\x08\x00\x00\x00\x00\x00\x00\x00"
            b"\x0c\x00\x00\x00IntProperty\x00" b"\x00" b"\x00\x00\x00\x00" b"\x00\x00\x00\x00"
        )
        self.assertEqual(_empty_set_property("CollectedGlitches", "IntProperty"), glitches)
        self.assertEqual(_empty_set_property("CollectedCoins", "IntProperty"), coins)


class TestCleanSyntheticCompletedSave(unittest.TestCase):
    def setUp(self):
        self.template = completed_template()
        self.clean = create_clean_playerarchi_data(self.template)
        self.props = walk(self.clean)

    def test_template_walk_sanity(self):
        before = walk(self.template)
        self.assertEqual(set(before), {
            "Prizes", "CollectedGlitches", "HasPlayedMenuInstructions", "GlitchesListenedTo", "HUBUpdateVOListenedTo",
            "HUBUpdateVOCollected", "NumberOfGamesWon", "NumberOfGamesLost", "ObjectsEaten", "CollectedCoins",
            "EULAAgreed", "GammaSettings",
        })
        self.assertNotEqual(before["GlitchesListenedTo"][1], EMPTY_SET)

    def test_progress_sets_are_empty(self):
        for name in _RESET_SETS:
            self.assertEqual(self.props[name][1], EMPTY_SET, name)

    def test_listened_tapes_and_hub_audio_are_reset(self):
        for name in ("GlitchesListenedTo", "HUBUpdateVOListenedTo", "HUBUpdateVOCollected", "ObjectsEaten"):
            self.assertEqual(self.props[name][1], EMPTY_SET, name)

    def test_prizes_and_games_won_are_reset(self):
        self.assertEqual(self.props["Prizes"][1], struct.pack("<I", 0))
        self.assertEqual(self.props["NumberOfGamesWon"][1], struct.pack("<i", 0))

    def test_settings_and_flags_are_kept(self):
        before = walk(self.template)
        for name in ("HasPlayedMenuInstructions", "EULAAgreed", "GammaSettings", "NumberOfGamesLost"):
            self.assertEqual(self.props[name], before[name], name)

    def test_no_property_is_lost_and_order_is_kept(self):
        self.assertEqual(list(self.props), list(walk(self.template)))

    def test_cleaning_is_idempotent(self):
        self.assertEqual(create_clean_playerarchi_data(self.clean), self.clean)


@unittest.skipUnless(REAL_COMPLETED_SAVE.exists(), "100percent.sav (real completed save, gitignored) not present")
class TestCleanRealCompletedSave(unittest.TestCase):
    def test_real_completed_save_comes_out_fresh(self):
        template = REAL_COMPLETED_SAVE.read_bytes()
        before = walk(template)
        self.assertNotEqual(before["GlitchesListenedTo"][1], EMPTY_SET)  # it really was completed
        clean = create_clean_playerarchi_data(template)
        after = walk(clean)
        self.assertEqual(list(after), list(before))
        for name in _RESET_SETS:
            if name in after:
                self.assertEqual(after[name][1], EMPTY_SET, name)
        self.assertEqual(after["Prizes"][1], struct.pack("<I", 0))
        self.assertEqual(after["GammaSettings"], before["GammaSettings"])
        self.assertEqual(after["EULAAgreed"], before["EULAAgreed"])


class TestTemplateIsOnlyRead(unittest.TestCase):
    def test_ensure_clean_save_never_modifies_the_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            template = tmp / "Player00.sav"
            template.write_bytes(completed_template())
            digest = hashlib.sha256(template.read_bytes()).hexdigest()
            target = tmp / "Playerarchi.sav"
            ensure_clean_archipelago_save(target, template)
            self.assertEqual(hashlib.sha256(template.read_bytes()).hexdigest(), digest)
            self.assertEqual(walk(target.read_bytes())["GlitchesListenedTo"][1], EMPTY_SET)


if __name__ == "__main__":
    unittest.main()
