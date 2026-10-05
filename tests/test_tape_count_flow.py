"""The tape count end to end, offline.

`test_lua_logic.TestDerivedCounters` tests `derived_counters.lua` alone. Here the real client core (`BridgeCore`) writes the real
`ap_inbox.txt`, and the real Lua modules of the mod (`bridge_io`, `item_sync`, `derived_counters`, `exact_hooks`), wired like `main.lua`,
read it in a Lua interpreter. The "room" is the value the `FNAFSaveGame_C:GetGlitchCount` hook returns (the number of tapes the tape
room shows).

What this can NOT tell: which tapes the room draws for a given count, or whether the game behaves the same on every launch. Those stay
in-game checks (see docs/testing.md, "Tape count"). No test here touches a real save: LOCALAPPDATA is redirected.
"""

import hashlib
import random
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from lupa import LuaRuntime
except ImportError:  # pragma: no cover
    LuaRuntime = None

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ap_client.bridge_core import BridgeCore, SaveAPI
from tests.gvas_fixtures import completed_template, walk
from tests.localappdata_isolation import SAVE_SUBDIR, isolate_localappdata
from tests.test_bridge_core import FakeSaveAPI
from tests.test_lua_logic import LIB, PRELUDE

GETTER = "/Game/ProductionAssets/Blueprints/Data/SaveGame/FNAFSaveGame.FNAFSaveGame_C:GetGlitchCount"
GI = "/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:"
TAPE, TOKEN, PASS = 101000001, 101000011, 101000002
EMPTY_SET = struct.pack("<II", 0, 0)


class GameRun:
    """One launch of the game: a fresh Lua state with the mod's modules wired like main.lua. A game restart is a new GameRun."""

    def __init__(self, bridge_dir, save=None):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(PRELUDE)
        loader = self.lua.eval("function(src, name) return load(src, '=' .. name)() end")

        def module(name):
            return loader((LIB / name).read_text(encoding="utf-8"), name)

        self.applied = []  # (index, item id) of every effect the game applied in this run
        self.counters = module("derived_counters.lua").init()
        self.lua.globals()["__loops"][1]()  # the hook registration loop runs once the game is ready
        self.items = module("item_sync.lua").init(self.lua.table(
            apply=self._apply, ack=lambda count: self.bridge.append_outbox(f"ITEMS_APPLIED {int(count)}")))
        self.emitted = self.lua.table()
        self.bridge = module("bridge_io.lua")(self.lua.table(
            outbox_path=str(Path(bridge_dir) / "ap_outbox.txt"), inbox_path=str(Path(bridge_dir) / "ap_inbox.txt"),
            bridge_dir=str(bridge_dir), emitted_location_names=self.emitted, on_item=lambda *a: None,
            on_session_sync=self._on_session_sync, on_received_snapshot=self._on_snapshot,
            on_applied_items=lambda spec: self.items.on_applied(spec)))
        self.lua.execute("__gi = {SaveSlotName = 'Playerarchi', IsValid = function() return true end, SaveGameRef = {}}")
        self.hooks_api = module("exact_hooks.lua").init(self.lua.table(
            APBridge=self.bridge.APBridge,
            locations_data=self.lua.table(row_id_to_location=self.lua.table(), location_name_to_id=self.lua.table()),
            emitted_location_names=self.emitted, baseline_location_names=self.bridge.baseline_location_names,
            game_instance=lambda: self.lua.globals()["__gi"]))

    def _apply(self, item_id, index):
        self.applied.append((int(index), int(item_id)))
        return True

    def _on_session_sync(self, session_id):
        self.items.on_session_sync(session_id)
        self.counters.on_session_sync(session_id)

    def _on_snapshot(self, spec):
        self.items.on_snapshot(spec)
        self.counters.on_snapshot(spec)

    def poll(self):
        self.bridge.poll_inbox()

    def tick(self):
        self.items.tick()

    def room(self):
        """The number of tapes the room shows: what the GetGlitchCount hook returns (None = the game's own, vanilla value)."""
        value = self.lua.globals()["__hooks"][GETTER](None)
        return None if value is None else int(value)

    def item_status(self):
        session, applied, total = self.items.status()
        return session, int(applied), int(total)

    def save_has_tapes(self, ids):
        """Make the in-memory save hold these tape ids (CollectedGlitches), as the game's own save would."""
        self.lua.globals()["__ids"] = self.lua.table_from(list(ids))
        self.lua.execute("__gi.SaveGameRef.CollectedGlitches = {ForEach = function(self, cb) for _, id in ipairs(__ids) do cb(id) end end}")

    def award_glitch(self, gid):
        self.lua.globals()["__hooks"][GI + "AwardGlitch"](None, str(gid))

    def poll_save(self):
        self.hooks_api.poll_savegame_state()

    def log(self):
        log = self.lua.globals()["__log"]
        return [log[i] for i in range(1, len(log) + 1)]


@unittest.skipIf(LuaRuntime is None, "lupa is not installed")
class TapeFlowCase(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="fnafhw_tapes_"))
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        isolate_localappdata(self, self.temp)
        self.bridge_dir = self.temp / "bridge"
        self.bridge_dir.mkdir()
        shutil.copy(project_root / "ue4ss_mod" / "FNAFHWArchipelago" / "locations.json", self.bridge_dir / "locations.json")
        self.sav = self.temp / "Playerarchi_fake.sav"
        self.sav.write_bytes(b"x")
        self.games = []

    def new_core(self, seed="SeedA", slot="HWtest", save_api=None):
        core = BridgeCore(self.bridge_dir, save_api=save_api or FakeSaveAPI(self.sav))
        core.slot = slot
        core.current_seed_name = seed
        return core

    def new_game(self):
        game = GameRun(self.bridge_dir)
        self.games.append(game)
        return game

    @staticmethod
    def connect(core, checked=()):
        return core.on_connected({"cmd": "Connected", "checked_locations": list(checked), "slot_data": {}})

    @staticmethod
    def send(core, start_index, ids):
        """What the server sends: ReceivedItems from `start_index`."""
        core.on_received_items({"index": start_index, "items": [
            {"item": i, "location": 1, "player": 1, "flags": 0} for i in ids]})

    def resend_all(self, core, ids):
        """After a (re)connect the server sends the whole list again, but only when the slot has items."""
        if ids:
            self.send(core, 0, ids)

    @staticmethod
    def pump(core):
        """What the client does with the game's outbox: returns the packets it would send to the server."""
        packets = []
        for line in core.bridge.read_outbox_lines(core.state):
            cmd, _, arg = line.partition(" ")
            packets.extend(core.game_command_packets(cmd.upper(), arg.strip()))
        return packets

    def settle(self, core, game):
        """The game polls the inbox, applies what is pending and acknowledges; the client reads the acknowledgement."""
        game.poll()
        game.tick()
        self.pump(core)


class TestSeveralItemsInARow(TapeFlowCase):
    def test_every_tape_item_adds_one_tape_and_other_items_add_none(self):
        core, game = self.new_core(), self.new_game()
        self.connect(core)
        self.settle(core, game)
        self.assertEqual(game.room(), 0)  # a session with no items: no tape, not the save's own count
        received = []
        for ids in ([TAPE], [TAPE], [TOKEN], [TAPE], [PASS, TAPE, TAPE]):
            self.send(core, len(received), ids)
            received += ids
            self.settle(core, game)
            self.assertEqual(game.room(), received.count(TAPE), received)
            self.assertEqual(game.item_status()[1:], (len(received), len(received)))
        self.assertEqual(game.room(), 5)

    def test_every_getter_call_of_one_room_visit_sees_the_same_number(self):
        core, game = self.new_core(), self.new_game()
        self.connect(core)
        self.send(core, 0, [TAPE, TAPE, TAPE])
        self.settle(core, game)
        self.assertEqual({game.room() for _ in range(16)}, {3})  # the room asks 16 times when it loads
        self.assertIn("calls=16", game.counters.status())

    def test_sixteen_is_the_most_the_world_hands_out(self):
        """The tape room has 16 AquiredLog_C actors and the world creates 16 Glitch Tape items; the mod does not clamp (see the report)."""
        data = (project_root / "fnaf_help_wanted" / "data.py").read_text(encoding="utf-8")
        self.assertIn('"Glitch Tape": ItemData(1, quantity=16', data)
        core, game = self.new_core(), self.new_game()
        self.connect(core)
        self.send(core, 0, [TAPE] * 16)
        self.settle(core, game)
        self.assertEqual(game.room(), 16)

    def test_the_counter_registers_one_hook_on_the_getter_and_calls_nothing_in_the_game(self):
        game = self.new_game()
        self.assertEqual([str(k) for k in game.lua.globals()["__hooks"].keys() if "GetGlitchCount" in str(k)], [GETTER])
        self.assertEqual(list(game.lua.globals()["__unhooked"].values()), [])
        self.assertEqual(game.lua.globals()["__calls"][1], None)  # no game function was called by anything the counter does


class TestReconnectAndRestart(TapeFlowCase):
    def prepare(self, n_tapes=3):
        core, game = self.new_core(), self.new_game()
        self.connect(core)
        ids = [TAPE] * n_tapes
        self.send(core, 0, ids)
        self.settle(core, game)
        self.assertEqual(game.room(), n_tapes)
        return core, game, ids

    def test_a_dropped_connection_keeps_the_count(self):
        core, game, _ = self.prepare()
        core.update_status("DISCONNECTED", message="connection lost")
        self.settle(core, game)
        self.assertEqual(game.room(), 3)

    def test_a_reconnect_gives_the_same_count_and_applies_nothing_again(self):
        core, game, ids = self.prepare()
        core.update_status("DISCONNECTED")
        self.connect(core)
        self.resend_all(core, ids)
        self.settle(core, game)
        self.assertEqual(game.room(), 3)
        self.assertEqual(game.item_status()[1:], (3, 3))
        self.assertEqual(len(game.applied), 3)  # each item's effect applied once, never again

    def test_a_reconnect_reads_zero_between_the_connect_and_the_servers_item_list(self):
        """KNOWN, not a bug to fix now: every connect starts from an EMPTY snapshot (so stale authorization cannot survive), and the
        server's list follows a moment later. A tape room that loaded exactly between the two lines would show no tape."""
        core, game, ids = self.prepare()
        self.connect(core)
        game.poll()
        self.assertEqual(game.room(), 0)
        self.resend_all(core, ids)
        game.poll()
        self.assertEqual(game.room(), 3)

    def test_a_game_restart_brings_the_count_back_without_applying_anything(self):
        core, game, _ = self.prepare()
        game2 = self.new_game()  # new Lua state: replays the inbox history
        game2.poll()
        self.assertEqual(game2.room(), 3)
        self.assertEqual(game2.item_status()[1:], (3, 3))  # applied=3 of 3 straight from the replay
        game2.tick()
        self.assertEqual(game2.applied, [])

    def test_a_game_restart_before_the_acknowledgement_reached_the_client_still_shows_the_count(self):
        """The count comes from the received list, not from what was applied: losing an acknowledgement cannot change what the room shows."""
        core, game = self.new_core(), self.new_game()
        self.connect(core)
        self.send(core, 0, [TAPE, TAPE])
        game.poll()
        game.tick()  # applied, but the client never read ITEMS_APPLIED
        game2 = self.new_game()
        game2.poll()
        self.assertEqual(game2.room(), 2)
        self.assertEqual(game2.item_status()[1:], (0, 2))  # applied again (Glitch Tape has no one-shot effect: harmless)
        game2.tick()
        self.assertEqual(game2.item_status()[1:], (2, 2))
        self.assertEqual(game2.room(), 2)

    def test_a_client_restart_and_a_game_restart_together(self):
        core, game, ids = self.prepare()
        core2 = self.new_core()  # the client process restarted: it resumes the session from disk
        self.connect(core2)
        self.resend_all(core2, ids)
        game2 = self.new_game()
        self.settle(core2, game2)
        self.assertEqual(game2.room(), 3)
        self.assertEqual(game2.item_status()[1:], (3, 3))
        self.assertEqual(game2.applied, [])

    def test_a_game_started_with_the_client_off_uses_the_last_known_list(self):
        self.prepare(4)
        game2 = self.new_game()  # no client at all, only the inbox file
        game2.poll()
        self.assertEqual(game2.room(), 4)

    def test_a_shorter_server_list_after_a_room_reset_lowers_the_count(self):
        core, game, _ = self.prepare(3)
        self.connect(core)
        self.send(core, 0, [TAPE])  # the room was restarted: only one item left
        self.settle(core, game)
        self.assertEqual(game.room(), 1)
        self.assertEqual(game.item_status()[1:], (1, 1))


class TestNewSeedStartsAtZero(TapeFlowCase):
    def test_a_new_seed_resets_the_count_in_a_running_game(self):
        core_a, game = self.new_core("SeedA"), self.new_game()
        self.connect(core_a)
        self.send(core_a, 0, [TAPE, TAPE, TAPE])
        self.settle(core_a, game)
        self.assertEqual(game.room(), 3)

        core_b = self.new_core("SeedB")  # a different seed, same slot name, an empty slot
        self.connect(core_b)
        self.settle(core_b, game)
        self.assertEqual(game.room(), 0)
        self.assertEqual(game.item_status(), ("SeedB_HWtest", 0, 0))
        self.send(core_b, 0, [TAPE])
        self.settle(core_b, game)
        self.assertEqual(game.room(), 1)

    def test_between_the_new_sessions_first_line_and_its_empty_snapshot_the_old_count_is_gone(self):
        """The connect block is written line by line. Fed one line at a time: right after SESSION_SYNC the old seed's count is already
        forgotten (the room is vanilla, i.e. the save's own number, for that instant) and the empty snapshot then makes it 0."""
        inbox = self.bridge_dir / "ap_inbox.txt"
        core_a, game = self.new_core("SeedA"), self.new_game()
        self.connect(core_a)
        self.send(core_a, 0, [TAPE, TAPE, TAPE])
        self.settle(core_a, game)
        self.assertEqual(game.room(), 3)
        before = inbox.read_bytes()

        self.connect(self.new_core("SeedB"))
        block = inbox.read_bytes()[len(before):].decode("utf-8").splitlines()
        sync = block.index("SESSION_SYNC SeedB_HWtest")
        empty_snapshot = block.index("RECEIVED_SNAPSHOT")
        self.assertLess(sync, empty_snapshot)
        inbox.write_bytes(before)  # rewind, then deliver the block in two parts
        with inbox.open("ab") as handle:
            handle.write("".join(line + "\n" for line in block[:sync + 1]).encode("utf-8"))
        game.poll()
        self.assertIsNone(game.room())
        with inbox.open("ab") as handle:
            handle.write("".join(line + "\n" for line in block[sync + 1:]).encode("utf-8"))
        game.poll()
        self.assertEqual(game.room(), 0)

    def test_a_game_restart_after_a_new_seed_does_not_see_the_old_seed(self):
        core_a, game = self.new_core("SeedA"), self.new_game()
        self.connect(core_a)
        self.send(core_a, 0, [TAPE] * 5)
        self.settle(core_a, game)
        core_b = self.new_core("SeedB")
        self.connect(core_b)
        game2 = self.new_game()
        game2.poll()
        self.assertEqual(game2.room(), 0)  # not 5, and not the save's own count (None would mean "vanilla")
        self.assertEqual(game2.item_status(), ("SeedB_HWtest", 0, 0))

    def test_going_back_to_the_old_seed_gets_its_own_count_again(self):
        core_a, game = self.new_core("SeedA"), self.new_game()
        self.connect(core_a)
        self.send(core_a, 0, [TAPE, TAPE])
        self.settle(core_a, game)
        core_b = self.new_core("SeedB")
        self.connect(core_b)
        self.send(core_b, 0, [TAPE] * 4)
        self.settle(core_b, game)
        self.assertEqual(game.room(), 4)
        core_a2 = self.new_core("SeedA")
        self.connect(core_a2)
        self.send(core_a2, 0, [TAPE, TAPE])
        self.settle(core_a2, game)
        self.assertEqual(game.room(), 2)

    def test_the_new_seed_save_has_no_tapes_and_the_real_save_is_not_touched(self):
        """A completed normal save (4 tapes) is the template: the Archipelago save made from it must hold none, and Player00.sav stays as it was."""
        temp = Path(tempfile.mkdtemp(prefix="fnafhw_tapes_real_"))
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        fake = isolate_localappdata(self, temp, starter_save=False)
        save_dir = fake / SAVE_SUBDIR
        save_dir.mkdir(parents=True, exist_ok=True)
        normal = save_dir / "Player00.sav"
        normal.write_bytes(completed_template())
        before = hashlib.sha256(normal.read_bytes()).hexdigest()
        self.assertNotEqual(walk(normal.read_bytes())["CollectedGlitches"][1], EMPTY_SET)

        core, game = self.new_core("SeedC", save_api=SaveAPI()), self.new_game()
        self.connect(core)
        self.settle(core, game)

        archi = walk((save_dir / "Playerarchi.sav").read_bytes())
        self.assertEqual(archi["CollectedGlitches"][1], EMPTY_SET)
        self.assertEqual(archi["GlitchesListenedTo"][1], EMPTY_SET)
        self.assertEqual(game.room(), 0)
        self.assertEqual(hashlib.sha256(normal.read_bytes()).hexdigest(), before)

    def test_without_a_session_the_game_keeps_its_own_count(self):
        game = self.new_game()
        game.poll()
        self.assertIsNone(game.room())  # no SESSION_SYNC yet: vanilla (the mod is inert by design)


class TestTapeChecksAlongsideTheCount(TapeFlowCase):
    LOCATION = "Collect Glitch Tape 06"  # GlitchID 5

    def test_picking_up_a_tape_sends_its_check_once_whatever_the_count(self):
        for received in (0, 3, 16):
            with self.subTest(received=received):
                core, game = self.new_core(f"Seed{received}"), self.new_game()
                self.connect(core)
                if received:
                    self.send(core, 0, [TAPE] * received)
                self.settle(core, game)
                self.assertEqual(game.room(), received)
                game.award_glitch(5)
                game.award_glitch(5)  # AwardGlitch and SetGlitchListenedTo both fire for one tape
                loc_id = core.location_name_to_id[self.LOCATION]
                self.assertEqual(self.pump(core), [{"cmd": "LocationChecks", "locations": [loc_id]}])
                self.assertEqual(game.room(), received)  # a pickup alone never changes what the room shows

    def test_the_tape_the_server_hands_back_raises_the_count_by_exactly_one(self):
        core, game = self.new_core(), self.new_game()
        self.connect(core)
        self.settle(core, game)
        game.award_glitch(5)
        self.assertEqual(len(self.pump(core)), 1)
        self.assertEqual(game.room(), 0)  # the check is out, the item has not come back yet
        self.send(core, 0, [TAPE])  # our own location held a Glitch Tape for us
        self.settle(core, game)
        self.assertEqual(game.room(), 1)
        self.assertEqual(self.pump(core), [])  # and nothing is sent again

    def test_the_save_poll_still_sends_every_tape_the_save_holds_while_the_count_is_zero(self):
        core, game = self.new_core(), self.new_game()
        self.connect(core)
        self.settle(core, game)
        game.save_has_tapes([5, 6])
        game.poll_save()
        names = sorted(line for line in core.bridge.outbox_path.read_text(encoding="utf-8").splitlines())
        self.assertEqual(names, ["LOCATION_CHECK_NAME Collect Glitch Tape 06", "LOCATION_CHECK_NAME Collect Glitch Tape 07"])
        self.assertEqual(game.room(), 0)

    def test_a_tape_the_server_already_has_checked_is_not_sent_again_after_a_reconnect(self):
        core, game = self.new_core(), self.new_game()
        self.connect(core)
        self.settle(core, game)
        game.award_glitch(5)
        loc_id = core.location_name_to_id[self.LOCATION]
        self.assertEqual(len(self.pump(core)), 1)
        self.connect(core, checked=[loc_id])  # reconnect: the server lists the check
        self.send(core, 0, [TAPE])
        self.settle(core, game)
        game.award_glitch(5)
        self.assertEqual(self.pump(core), [])
        self.assertEqual(game.room(), 1)


class TestTheCountNeverDriftsFromTheServersList(TapeFlowCase):
    def test_a_gap_in_the_item_list_leaves_the_last_complete_count_and_a_later_fill_repairs_it(self):
        core, game = self.new_core(), self.new_game()
        self.connect(core)
        self.send(core, 0, [TAPE, TAPE])
        self.settle(core, game)
        self.send(core, 3, [TAPE])  # index 2 never arrived: the client sends no snapshot rather than a wrong one
        self.settle(core, game)
        self.assertEqual(game.room(), 2)
        self.send(core, 2, [TAPE])
        self.settle(core, game)
        self.assertEqual(game.room(), 4)  # indexes 0..3 are now all known: 4 tapes

    def test_a_long_random_session_never_disagrees_with_the_server(self):
        """Items, drops, reconnects, client restarts and game restarts in any order: after every step the room shows exactly the Glitch
        Tape items in the server's list, and the game's applied count equals the list length (each index applied once, ever)."""
        rng = random.Random(20261005)
        core = self.new_core("SeedRandom")
        game = self.new_game()
        self.connect(core)
        server = []
        for step in range(300):
            op = rng.choice(["items", "items", "items", "reconnect", "client_restart", "game_restart", "drop"])
            if op == "items":
                batch = [rng.choice([TAPE, TAPE, TOKEN, PASS]) for _ in range(rng.randint(1, 3))]
                self.send(core, len(server), batch)
                server += batch
            elif op == "reconnect":
                self.connect(core)
                self.resend_all(core, server)
            elif op == "client_restart":
                core = self.new_core("SeedRandom")
                self.connect(core)
                self.resend_all(core, server)
            elif op == "game_restart":
                game = self.new_game()
            else:
                core.update_status("DISCONNECTED")
            self.settle(core, game)
            self.assertEqual(game.room(), server.count(TAPE), (step, op))
            self.assertEqual(game.item_status()[1:], (len(server), len(server)), (step, op))
        applied = sorted(index for run in self.games for index, _ in run.applied)
        self.assertEqual(applied, list(range(len(server))))


if __name__ == "__main__":
    unittest.main()
