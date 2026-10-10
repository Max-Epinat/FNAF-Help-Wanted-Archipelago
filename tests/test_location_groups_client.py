"""The client side of the group toggles, on the real BridgeCore (no sockets, a fake save reader, an isolated LOCALAPPDATA).

A check for a location that is not in this multiworld (its group is off) must never be sent, queued, persisted or turn into an error,
whether it comes from the mod (LOCATION_CHECK / LOCATION_CHECK_NAME) or from the save poll. What is in the multiworld is what the server's
Connected packet says (checked + missing locations). A packet without `missing_locations` (old rooms, old tests) filters nothing.
"""

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tests.test_bridge_core import CoreTestCase

LEVEL, TOKEN, TAPE, PRIZE = 101, 201, 301, 401
NAMES = {
    LEVEL: "Beat FNAF 1 - Night 1",
    TOKEN: "Collect Faz Token 01",
    TAPE: "Collect Glitch Tape 02",
    PRIZE: "Prize - Plushie: Freddy Plush",
}


class GroupCase(CoreTestCase):
    def setUp(self):
        super().setUp()
        self.core.location_id_to_name = dict(NAMES)  # the apworld's launcher client knows every location, in the seed or not
        self.core.location_name_to_id = {name: loc_id for loc_id, name in NAMES.items()}

    def connect_with(self, in_seed, checked=(), slot_data=None):
        """A real server's Connected packet: every location of the slot is either checked or missing."""
        return self.core.on_connected({
            "cmd": "Connected", "checked_locations": list(checked),
            "missing_locations": [loc for loc in in_seed if loc not in checked], "slot_data": slot_data or {}})

    def poll(self):
        self.core._last_sav_poll_time = 0.0
        self.core._last_sav_mtime = 0.0
        return self.core.collect_savegame_packets()

    def persisted_pending(self):
        """What a restart would read back: the session file, after the core saved its state."""
        self.core._save_state()
        state = json.loads((self.core.bridge.sessions_dir / "SeedX_HWtest.json").read_text(encoding="utf-8"))
        return set(state["pending_locations"])


class TestModChecks(GroupCase):
    def test_a_check_for_a_group_that_is_off_is_dropped_everywhere(self):
        self.connect_with([LEVEL])  # tokens, tapes and prizes are not randomized in this seed
        for loc_id in (TOKEN, TAPE, PRIZE):
            self.assertEqual(self.core.location_check_packets(str(loc_id)), [], loc_id)
            self.assertEqual(self.core.location_check_name_packets(NAMES[loc_id]), [], loc_id)
        self.assertEqual(self.core.state.pending_locations, set())
        self.assertEqual(self.persisted_pending(), set())
        self.assertTrue(any("not part of this multiworld" in line for line in self.inbox()))

    def test_a_check_in_the_seed_is_still_sent(self):
        self.connect_with([LEVEL, TOKEN])
        self.assertEqual(self.core.location_check_packets(str(LEVEL)), [{"cmd": "LocationChecks", "locations": [LEVEL]}])
        self.assertEqual(self.core.location_check_name_packets(NAMES[TOKEN]),
                         [{"cmd": "LocationChecks", "locations": [TOKEN]}])

    def test_each_group_is_independent(self):
        self.connect_with([LEVEL, TOKEN, PRIZE])  # only the tapes are off
        self.assertEqual(self.core.location_check_packets(str(TAPE)), [])
        self.assertEqual(self.core.location_check_packets(str(PRIZE)), [{"cmd": "LocationChecks", "locations": [PRIZE]}])
        self.assertEqual(self.core.location_check_packets(str(TOKEN)), [{"cmd": "LocationChecks", "locations": [TOKEN]}])

    def test_an_id_nobody_knows_is_dropped_without_an_error(self):
        self.connect_with([LEVEL])
        self.assertEqual(self.core.location_check_packets("999999"), [])
        self.assertEqual(self.core.location_check_name_packets("Nope"), [])  # unchanged: unknown name

    def test_a_room_that_sends_no_location_lists_filters_nothing(self):
        """Old setups and the existing tests: the packet has no `missing_locations`, so behaviour is exactly the old one."""
        self.connect()
        self.assertEqual(self.core.location_check_packets(str(TOKEN)), [{"cmd": "LocationChecks", "locations": [TOKEN]}])
        self.assertIn(TOKEN, self.core.state.pending_locations)

    def test_an_old_room_with_every_location_filters_nothing(self):
        self.connect_with(list(NAMES))
        for loc_id in NAMES:
            self.assertEqual(self.core.location_check_packets(str(loc_id)), [{"cmd": "LocationChecks", "locations": [loc_id]}])

    def test_the_set_follows_the_latest_connect(self):
        self.connect_with([LEVEL])
        self.assertEqual(self.core.location_check_packets(str(TOKEN)), [])
        self.connect_with([LEVEL, TOKEN])  # e.g. the same slot in another room
        self.assertEqual(self.core.location_check_packets(str(TOKEN)), [{"cmd": "LocationChecks", "locations": [TOKEN]}])


class TestSavePoll(GroupCase):
    def test_what_the_save_holds_for_a_group_that_is_off_is_never_sent_or_queued(self):
        self.connect_with([LEVEL])
        self.save_api.earned = [NAMES[LEVEL], NAMES[TOKEN], NAMES[TAPE], NAMES[PRIZE]]
        self.assertEqual(self.poll(), [{"cmd": "LocationChecks", "locations": [LEVEL]}])
        self.assertEqual(self.core.state.pending_locations, {LEVEL})
        self.assertEqual(self.persisted_pending(), {LEVEL})

    def test_nothing_is_sent_when_only_off_groups_changed(self):
        self.connect_with([LEVEL])
        self.save_api.earned = [NAMES[TOKEN], NAMES[PRIZE]]
        self.assertEqual(self.poll(), [])
        self.assertEqual(self.core.state.pending_locations, set())

    def test_the_log_names_each_ignored_location_once_not_at_every_poll(self):
        self.connect_with([LEVEL])
        self.save_api.earned = [NAMES[TOKEN]]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for _ in range(3):
                self.poll()
        text = out.getvalue()
        self.assertEqual(text.count("not part of this multiworld"), 1, text)
        self.assertIn(NAMES[TOKEN], text)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("[WARN] [Save Watcher]", text)

    def test_a_group_that_is_on_is_read_as_before(self):
        self.connect_with([LEVEL, TOKEN, TAPE, PRIZE])
        self.save_api.earned = [NAMES[TOKEN], NAMES[TAPE], NAMES[PRIZE]]
        packet = self.poll()
        self.assertEqual(sorted(packet[0]["locations"]), sorted([TOKEN, TAPE, PRIZE]))

    def test_without_location_lists_the_poll_is_unchanged(self):
        self.connect()
        self.save_api.earned = [NAMES[TOKEN]]
        self.assertEqual(self.poll(), [{"cmd": "LocationChecks", "locations": [TOKEN]}])


class TestPendingChecks(GroupCase):
    def test_a_check_for_a_group_that_is_off_is_not_queued_while_offline_either(self):
        from ap_client.bridge_core import STATUS_DISCONNECTED
        self.connect_with([LEVEL])
        self.core.update_status(STATUS_DISCONNECTED)
        self.assertEqual(self.core.location_check_packets(str(TOKEN)), [])
        self.assertEqual(self.core.location_check_packets(str(LEVEL)), [])  # a real check is queued as before
        self.assertEqual(self.core.state.pending_locations, {LEVEL})
        self.core._save_state()  # the watcher does this after every outbox line
        self.assertEqual(self.connect_with([LEVEL]), [{"cmd": "LocationChecks", "locations": [LEVEL]}])

    def test_pending_checks_of_a_resumed_session_that_are_not_in_the_seed_are_dropped(self):
        self.connect_with([LEVEL, TOKEN])
        self.core.state.pending_locations.update({LEVEL, TOKEN})
        self.core._save_state()
        outgoing = self.connect_with([LEVEL])
        self.assertEqual(outgoing, [{"cmd": "LocationChecks", "locations": [LEVEL]}])
        self.assertEqual(self.core.state.pending_locations, {LEVEL})

    def test_nothing_is_flushed_when_every_pending_check_is_off(self):
        self.connect_with([LEVEL, TOKEN])
        self.core.state.pending_locations.add(TOKEN)
        self.core._save_state()
        self.assertEqual(self.connect_with([LEVEL]), [])


class TestTellingTheGame(GroupCase):
    def test_the_connect_block_carries_the_groups_after_the_session_line(self):
        self.connect_with([LEVEL], slot_data={"randomize_prizes": False, "randomize_faz_tokens": True, "randomize_glitch_tapes": False})
        lines = self.inbox()
        self.assertIn("RANDOMIZED_GROUPS prizes=0 faz_tokens=1 tapes=0", lines)
        self.assertLess(lines.index("SESSION_SYNC SeedX_HWtest"), lines.index("RANDOMIZED_GROUPS prizes=0 faz_tokens=1 tapes=0"))
        self.assertLess(lines.index("DEATH_LINK_GIFT_BOX 1"), lines.index("RANDOMIZED_GROUPS prizes=0 faz_tokens=1 tapes=0"))

    def test_a_slot_without_the_keys_is_fully_randomized(self):
        self.connect_with([LEVEL])
        self.assertIn("RANDOMIZED_GROUPS prizes=1 faz_tokens=1 tapes=1", self.inbox())

    def test_every_connect_repeats_the_line_so_a_game_restart_replays_it(self):
        self.connect_with([LEVEL], slot_data={"randomize_glitch_tapes": False})
        self.connect_with([LEVEL], slot_data={"randomize_glitch_tapes": False})
        self.assertEqual(self.inbox().count("RANDOMIZED_GROUPS prizes=1 faz_tokens=1 tapes=0"), 2)

    def test_the_real_total_goes_into_the_status_file(self):
        self.connect_with([LEVEL, TOKEN], checked=[LEVEL])
        status = json.loads(self.core.bridge.status_path.read_text(encoding="utf-8"))
        self.assertEqual(status["total_count"], 2)
        self.assertEqual(status["checked_count"], 1)

    def test_the_total_is_left_out_when_the_server_gave_no_list(self):
        self.connect()
        status = json.loads(self.core.bridge.status_path.read_text(encoding="utf-8"))
        self.assertNotIn("total_count", status)  # the in-game panel then keeps its old default


if __name__ == "__main__":
    unittest.main()
