"""The save reader walks a file another program (the game) writes, and may read it half-written or damaged.

A bad length or count must end in one clear error (GvasError), quickly, and never in a hang, an endless allocation or some other exception.
A valid save must parse exactly as before.
"""

import random
import struct
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ap_client import save_reader
from ap_client.save_reader import GvasError, create_clean_playerarchi_data, ensure_clean_archipelago_save, parse_gvas_save
from tests.gvas_fixtures import completed_template, fstring, header, name_array

TIME_LIMIT_SECONDS = 2.0


def array_with_raw_elements(name, count, element_bytes):
    body = struct.pack("<I", count) + element_bytes
    return fstring(name) + fstring("ArrayProperty") + struct.pack("<Q", len(body)) + fstring("NameProperty") + b"\x00" + body


def save(*properties):
    return header() + b"".join(properties) + fstring("None")


def parse_quickly(data):
    started = time.monotonic()
    try:
        return parse_gvas_save(data)
    finally:
        assert time.monotonic() - started < TIME_LIMIT_SECONDS, "the parser took too long: a hang"


class TestValidSavesParseAsBefore(unittest.TestCase):
    def test_the_template_properties_are_read(self):
        parsed = parse_gvas_save(completed_template())
        self.assertEqual(parsed["Prizes"], ["Prize_A", "Prize_B", "Prize_C"])
        self.assertEqual(parsed["CollectedGlitches"], [1, 2, 3, 4])
        self.assertEqual(parsed["CollectedCoins"], [1, 2, 3])
        self.assertEqual(parsed["NumberOfGamesWon"], 7)
        self.assertIs(parsed["EULAAgreed"], True)

    def test_a_set_of_objects_is_skipped_not_misread_as_numbers(self):
        self.assertEqual(parse_gvas_save(completed_template())["ObjectsEaten"], [])

    def test_a_utf16_string_in_an_array_is_decoded(self):
        text = "Café"
        utf16 = struct.pack("<i", -(len(text) + 1)) + (text + "\x00").encode("utf-16-le")
        parsed = parse_gvas_save(save(array_with_raw_elements("Prizes", 2, fstring("Plain") + utf16)))
        self.assertEqual(parsed["Prizes"], ["Plain", text])

    def test_an_empty_array_and_an_empty_string_element(self):
        self.assertEqual(parse_gvas_save(save(name_array("Prizes", [])))["Prizes"], [])
        self.assertEqual(parse_gvas_save(save(array_with_raw_elements("Prizes", 1, struct.pack("<i", 0))))["Prizes"], [""])

    def test_something_that_is_not_gvas_gives_an_empty_result(self):
        self.assertEqual(parse_gvas_save(b""), {})
        self.assertEqual(parse_gvas_save(b"NOTGVAS" + bytes(100)), {})


class TestDamagedSaves(unittest.TestCase):
    def assertRejected(self, data):
        with self.assertRaises(GvasError):
            parse_quickly(data)

    def test_an_array_that_claims_billions_of_elements(self):
        self.assertRejected(save(array_with_raw_elements("Prizes", 0xFFFFFFFF, fstring("x"))))

    def test_elements_with_a_negative_length_cannot_loop_in_place(self):
        # four bytes of -4 repeated: with the old walk every element "consumed" nothing and the loop ran for its whole count
        count = 50_000
        self.assertRejected(save(array_with_raw_elements("Prizes", count, struct.pack("<i", -4) * count)))

    def test_an_element_longer_than_the_file(self):
        self.assertRejected(save(array_with_raw_elements("Prizes", 1, struct.pack("<i", 1_000_000) + b"abc")))

    def test_a_set_that_claims_billions_of_elements(self):
        body = struct.pack("<II", 0, 0xFFFFFFFF)
        self.assertRejected(save(fstring("CollectedCoins") + fstring("SetProperty") + struct.pack("<Q", len(body)) + fstring("IntProperty") + b"\x00" + body))

    def test_a_map_that_claims_billions_of_entries(self):
        body = struct.pack("<II", 0, 0xFFFFFFFF)
        prop = (fstring("LevelInfo") + fstring("MapProperty") + struct.pack("<Q", len(body)) + fstring("NameProperty") + fstring("StructProperty")
                + b"\x00" + body)
        self.assertRejected(save(prop))

    def test_header_lengths_that_point_outside_the_file(self):
        good = completed_template()
        build_id_at = 4 + 4 + 4 + 6 + 4
        for forged in (0xFFFFFFFF, 0x7FFFFFFF, len(good) + 1):
            self.assertRejected(good[:build_id_at] + struct.pack("<I", forged) + good[build_id_at + 4:])

    def test_a_type_name_that_is_not_a_name(self):
        body = struct.pack("<I", 0)
        prop = fstring("Prizes") + fstring("ArrayProperty") + struct.pack("<Q", len(body)) + struct.pack("<i", -5) + b"\x00" + body
        self.assertRejected(save(prop))

    def test_a_file_far_larger_than_any_save(self):
        self.assertRejected(completed_template() + bytes(save_reader.MAX_SAVE_BYTES))

    def test_cutting_a_valid_save_anywhere_gives_a_result_or_gvaserror_never_anything_else(self):
        data = completed_template()
        for cut in range(0, len(data)):
            try:
                parse_quickly(data[:cut])
            except GvasError:
                pass

    def test_random_damage_gives_a_result_or_gvaserror_never_anything_else(self):
        data = bytearray(completed_template())
        rng = random.Random(20261101)
        started = time.monotonic()
        for _ in range(1500):
            damaged = bytearray(data)
            for _ in range(rng.randint(1, 6)):
                damaged[rng.randrange(len(damaged))] = rng.randrange(256)
            try:
                parse_gvas_save(bytes(damaged))
            except GvasError:
                pass
        self.assertLess(time.monotonic() - started, 30, "1500 damaged saves should take a fraction of a second each at most")


class TestCleanSaveFromADamagedTemplate(unittest.TestCase):
    def test_a_template_that_is_not_a_save_is_refused(self):
        with self.assertRaises(GvasError):
            create_clean_playerarchi_data(b"this is not a save file at all")

    def test_cutting_or_damaging_a_template_gives_bytes_or_gvaserror(self):
        data = completed_template()
        rng = random.Random(7)
        cases = [data[:cut] for cut in range(4, len(data), 3)]
        for _ in range(600):
            damaged = bytearray(data)
            for _ in range(rng.randint(1, 5)):
                damaged[rng.randrange(len(damaged))] = rng.randrange(256)
            cases.append(bytes(damaged))
        started = time.monotonic()
        for case in cases:
            try:
                create_clean_playerarchi_data(case)
            except GvasError:
                pass
        self.assertLess(time.monotonic() - started, 30)

    def test_a_template_cut_inside_a_value_does_not_grow(self):
        # assigning past the end of a bytearray slice APPENDS: a cut right after "NumberOfGamesWon" must not turn into a longer file
        data = completed_template()
        cut = data.index(b"NumberOfGamesWon\x00") + len(b"NumberOfGamesWon\x00") + 6
        try:
            result = create_clean_playerarchi_data(data[:cut])
        except GvasError:
            return
        self.assertLessEqual(len(result), cut + 200)

    def test_a_damaged_template_does_not_stop_the_connection_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = Path(tmp) / "Player00.sav"
            template.write_bytes(b"GVAS" + bytes(18) + struct.pack("<I", 0xFFFFFFFF) + bytes(40))  # a build id "length" far outside the file
            target = Path(tmp) / "Playerarchi_x.sav"
            with mock.patch("builtins.print") as printed:
                self.assertEqual(ensure_clean_archipelago_save(target_path=target, template_path=template), target)
            self.assertFalse(target.exists())
            self.assertFalse(list(Path(tmp).glob("*.tmp")))
            self.assertTrue(any("could not be used as the template" in str(call) for call in printed.call_args_list))

    def test_a_good_template_still_makes_the_clean_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = Path(tmp) / "Player00.sav"
            template.write_bytes(completed_template())
            target = Path(tmp) / "Playerarchi_x.sav"
            ensure_clean_archipelago_save(target_path=target, template_path=template)
            parsed = parse_gvas_save(target.read_bytes())
            self.assertEqual((parsed["Prizes"], parsed["CollectedGlitches"], parsed["CollectedCoins"], parsed["NumberOfGamesWon"]), ([], [], [], 0))


class TestExtractingChecksDoesNoWorkItDoesNotNeed(unittest.TestCase):
    def test_it_never_loads_the_prize_list(self):
        with mock.patch.object(save_reader, "load_prize_checks", side_effect=AssertionError("the prize list is not needed here")):
            self.assertEqual(save_reader.extract_earned_locations({"Prizes": ["30"], "CollectedCoins": [1]}),
                             ["Collect Faz Token 01", "Prize - Plushie: Bonnie Plush"])


if __name__ == "__main__":
    unittest.main()
