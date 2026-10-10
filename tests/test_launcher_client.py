"""The Archipelago launcher client (fnaf_help_wanted/client.py), run against stubbed Archipelago modules.

The package is assembled exactly like scripts/build-apworld.ps1 does (client.py, data.py and the vendored bridge_core.py /
save_reader.py from scripts/vendored_client_files.json) and imported under a private name, so the real relative imports and the
real glue code run. The Archipelago framework itself (CommonClient, kvui, Utils) is replaced by minimal stubs: what is NOT covered
here is the framework's real behaviour, which can only be checked by launching the client from the Archipelago launcher.
"""

import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tests.localappdata_isolation import isolate_localappdata

PKG = "fnafhw_launcher_pkg"
STUBBED = ("Utils", "CommonClient", "kvui", "colorama")


class StubClientCommandProcessor:
    def __init__(self, ctx):
        self.ctx = ctx
        self.lines = []

    def output(self, text):
        self.lines.append(text)


class StubCommonContext:
    def __init__(self, server_address, password):
        self.server_address = server_address
        self.password = password
        self.auth = None
        self.seed_name = ""
        self.server = None
        self.exit_event = asyncio.Event()
        self.sent = []
        self.connect_sent = False
        self.disconnected = False

    async def send_msgs(self, msgs):
        self.sent.append(list(msgs))

    async def get_username(self):
        self.auth = self.auth or "HWtest"

    async def send_connect(self):
        self.connect_sent = True

    async def server_auth(self, password_requested=False):
        pass

    async def connection_closed(self):
        pass

    async def disconnect(self, allow_autoreconnect=False):
        self.disconnected = True

    async def shutdown(self):
        pass


def install_stubs():
    saved = {name: sys.modules.get(name) for name in STUBBED}
    common = types.ModuleType("CommonClient")
    common.ClientCommandProcessor = StubClientCommandProcessor
    common.CommonContext = StubCommonContext
    common.get_base_parser = lambda description="": None
    common.gui_enabled = False
    common.logger = logging.getLogger("fnafhw-launcher-test")
    common.server_loop = lambda ctx: None
    sys.modules["CommonClient"] = common
    sys.modules["Utils"] = types.ModuleType("Utils")
    sys.modules["kvui"] = types.ModuleType("kvui")
    sys.modules["colorama"] = types.ModuleType("colorama")
    return saved


def assemble_package(target: Path) -> Path:
    """The vendored apworld layout, without Archipelago's own modules."""
    pkg_dir = target / "fnaf_help_wanted"
    pkg_dir.mkdir(parents=True)
    for name in ("client.py", "data.py"):
        shutil.copy(project_root / "fnaf_help_wanted" / name, pkg_dir / name)
    for entry in json.loads((project_root / "scripts" / "vendored_client_files.json").read_text(encoding="utf-8")):
        shutil.copy(project_root / entry["source"], pkg_dir / entry["target"])
    return pkg_dir


class LauncherTestCase(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_pkg = Path(tempfile.mkdtemp(prefix="fnafhw_pkg_"))
        cls.saved_modules = install_stubs()
        pkg_dir = assemble_package(cls.tmp_pkg)
        package = types.ModuleType(PKG)
        package.__path__ = [str(pkg_dir)]
        sys.modules[PKG] = package
        import importlib

        cls.client = importlib.import_module(f"{PKG}.client")
        cls.bridge_core = importlib.import_module(f"{PKG}.bridge_core")
        cls.data = importlib.import_module(f"{PKG}.data")

    @classmethod
    def tearDownClass(cls):
        for name in [n for n in sys.modules if n == PKG or n.startswith(PKG + ".")]:
            del sys.modules[name]
        for name, module in cls.saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        shutil.rmtree(cls.tmp_pkg, ignore_errors=True)

    async def asyncSetUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="fnafhw_launcher_"))
        isolate_localappdata(self, self.temp)
        self.bridge_dir = self.temp / "bridge"
        self.bridge_dir.mkdir()
        self._old_env = os.environ.get("FNAFHW_BRIDGE_DIR")
        os.environ["FNAFHW_BRIDGE_DIR"] = str(self.bridge_dir)
        self.contexts = []

    async def asyncTearDown(self):
        for ctx in self.contexts:
            if ctx.instance_lock is not None:
                ctx.instance_lock.release()
        if self._old_env is None:
            os.environ.pop("FNAFHW_BRIDGE_DIR", None)
        else:
            os.environ["FNAFHW_BRIDGE_DIR"] = self._old_env
        shutil.rmtree(self.temp, ignore_errors=True)

    def make_ctx(self):
        ctx = self.client.FNAFHWContext("archipelago.gg:1", None)
        self.contexts.append(ctx)
        return ctx

    def connect(self, ctx, checked=(), seed="SeedL", slot_data=None):
        ctx.auth = "HWtest"
        ctx.server = types.SimpleNamespace(socket=types.SimpleNamespace(open=True))
        ctx.on_package("RoomInfo", {"cmd": "RoomInfo", "seed_name": seed})
        ctx.on_package("Connected", {"cmd": "Connected", "checked_locations": list(checked), "slot_data": slot_data or {}})

    def inbox(self, ctx):
        return ctx.core.bridge.inbox_path.read_text(encoding="utf-8").splitlines()


class TestFindingTheBridge(unittest.TestCase):
    """Pure helpers: no Archipelago stubs needed beyond importing the module."""

    @classmethod
    def setUpClass(cls):
        LauncherTestCase.setUpClass.__func__(LauncherTestCase)
        cls.client = LauncherTestCase.client
        cls.bridge_core = LauncherTestCase.bridge_core

    @classmethod
    def tearDownClass(cls):
        LauncherTestCase.tearDownClass.__func__(LauncherTestCase)

    def test_parse_bridge_dir_from_the_mods_config_lua(self):
        text = '''return {
    -- Bridge directory path (where ap_inbox, ap_outbox, and connection profiles are stored)
    bridge_dir = "C:/Users/me/Desktop/FNAF HW archi/bridge",
    ui_key = "F1",
}'''
        self.assertEqual(self.bridge_core.parse_bridge_dir_from_config(text), "C:/Users/me/Desktop/FNAF HW archi/bridge")

    def test_commented_out_or_empty_or_missing_bridge_dir_is_not_used(self):
        for text in ('-- bridge_dir = "x"\nreturn {}', 'return { bridge_dir = "" }', "return {}", ""):
            self.assertIsNone(self.bridge_core.parse_bridge_dir_from_config(text), text)

    def test_steam_library_roots(self):
        vdf = '"libraryfolders" { "0" { "path"\t\t"C:\\\\Program Files (x86)\\\\Steam" } "1" { "path" "D:\\\\SteamLibrary" } }'
        roots = self.bridge_core.steam_library_roots(vdf)
        self.assertEqual(roots[1], Path("D:\\SteamLibrary") / "steamapps" / "common" / "FNAFVRHelpWanted")
        self.assertEqual(len(roots), 2)

    def test_find_bridge_dir_prefers_the_environment_then_the_installed_mods_config(self):
        tmp = Path(tempfile.mkdtemp(prefix="fnafhw_find_"))
        try:
            bridge = tmp / "bridge"
            bridge.mkdir()
            game = tmp / "game"
            config = game / self.bridge_core.MOD_CONFIG_SUBPATH
            config.parent.mkdir(parents=True)
            config.write_text(f'return {{ bridge_dir = "{bridge.as_posix()}" }}', encoding="utf-8")

            self.assertEqual(self.bridge_core.find_bridge_dir({}, [game]), bridge)  # from the mod's config.lua
            other = tmp / "other"
            other.mkdir()
            self.assertEqual(self.bridge_core.find_bridge_dir({"FNAFHW_BRIDGE_DIR": str(other)}, [game]), other)  # env wins
            self.assertEqual(self.bridge_core.find_bridge_dir({"FNAFHW_BRIDGE_DIR": str(tmp / "nope")}, [game]), bridge)
            self.assertIsNone(self.bridge_core.find_bridge_dir({}, [tmp / "no_game_here"]))
            config.write_text(f'return {{ bridge_dir = "{(tmp / "gone").as_posix()}" }}', encoding="utf-8")
            self.assertIsNone(self.bridge_core.find_bridge_dir({}, [game]))  # configured folder does not exist
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestVendoredLayout(LauncherTestCase):
    async def test_save_reader_and_prize_list_resolve_inside_the_package(self):
        ctx = self.make_ctx()
        reader = ctx.core.save_api._reader()
        self.assertEqual(reader.__name__, f"{PKG}.save_reader")  # the vendored copy, not a path lookup
        prizes = reader.load_prize_checks()
        self.assertEqual(prizes, list(self.data.PRIZE_CHECKS))  # imported from data.py: works inside a zip too
        self.assertGreater(len(prizes), 50)


class TestContextSetup(LauncherTestCase):
    async def test_opens_the_bridge_takes_the_lock_and_knows_every_location(self):
        ctx = self.make_ctx()
        self.assertIsNotNone(ctx.core, ctx.bridge_error)
        self.assertEqual(ctx.bridge_dir, self.bridge_dir)
        self.assertTrue((self.bridge_dir / "ap_client.lock").exists())
        self.assertEqual(len(ctx.core.location_name_to_id), len(self.data.LOCATION_TABLE))
        self.assertEqual(ctx.core.location_name_to_id["Beat FNAF 1 - Night 1"], self.data.LOCATION_OFFSET + self.data.LOCATION_TABLE["Beat FNAF 1 - Night 1"].code)

    async def test_a_second_client_is_refused_and_explains_why(self):
        first = self.make_ctx()
        second = self.make_ctx()
        self.assertIsNotNone(first.core)
        self.assertIsNone(second.core)
        self.assertIn("already running", second.bridge_error)
        self.assertIn("Close the other client", second.bridge_error)

    async def test_missing_bridge_folder_is_reported_not_raised(self):
        os.environ["FNAFHW_BRIDGE_DIR"] = str(self.temp / "does_not_exist")
        old_roots = self.bridge_core.candidate_game_roots
        self.bridge_core.candidate_game_roots = lambda env=None: []
        try:
            ctx = self.make_ctx()
        finally:
            self.bridge_core.candidate_game_roots = old_roots
        self.assertIsNone(ctx.core)
        self.assertIn("could not find the bridge folder", ctx.bridge_error)
        ctx.on_package("Connected", {"cmd": "Connected"})  # must not raise without a core

    async def test_shutdown_releases_the_lock(self):
        ctx = self.make_ctx()
        await ctx.shutdown()
        self.assertFalse((self.bridge_dir / "ap_client.lock").exists())

    async def test_is_connected_follows_the_server_endpoint(self):
        ctx = self.make_ctx()
        self.assertFalse(ctx.is_connected())
        ctx.server = types.SimpleNamespace(socket=types.SimpleNamespace(open=True))
        self.assertTrue(ctx.is_connected())
        ctx.server.socket.open = False
        self.assertFalse(ctx.is_connected())


class TestSessionSafety(LauncherTestCase):
    """A wrong session id archives the player's Playerarchi.sav and starts a fresh one: the seed must come from the server."""

    def save_state(self):
        sav = Path(os.environ["LOCALAPPDATA"]) / "freddys" / "Saved" / "SaveGames"
        return sorted(p.name for p in sav.iterdir()), sorted(p.name for p in (self.bridge_dir / "sessions").iterdir())

    async def test_seed_comes_from_roominfo_not_from_a_guess(self):
        ctx = self.make_ctx()
        ctx.auth = "HWtest"
        ctx.on_package("RoomInfo", {"cmd": "RoomInfo", "seed_name": "RealSeed123"})
        ctx.on_package("Connected", {"cmd": "Connected", "checked_locations": [], "slot_data": {}})
        self.assertEqual(ctx.core.state.session_id, "RealSeed123_HWtest")
        self.assertNotIn("unknown_seed", "".join(self.inbox(ctx)))

    async def test_without_a_seed_nothing_is_started_and_no_save_is_touched(self):
        ctx = self.make_ctx()
        ctx.auth = "HWtest"
        before = self.save_state()
        sav = Path(os.environ["LOCALAPPDATA"]) / "freddys" / "Saved" / "SaveGames" / "Player00.sav"
        ctx.on_package("Connected", {"cmd": "Connected", "checked_locations": [], "slot_data": {}})  # no RoomInfo before it
        self.assertEqual(self.save_state(), before)  # no Playerarchi.sav archived or created, no session file
        self.assertEqual(ctx.core.state.session_id, "")
        self.assertEqual(ctx.core.status, "ERROR")
        self.assertNotIn("SESSION_SYNC", " ".join(self.inbox(ctx)))
        self.assertTrue(sav.exists())

    async def test_reconnecting_to_the_same_room_resumes_and_does_not_archive_the_save(self):
        ctx = self.make_ctx()
        self.connect(ctx, seed="SeedKeep")
        sav_dir = Path(os.environ["LOCALAPPDATA"]) / "freddys" / "Saved" / "SaveGames"
        playerarchi = sav_dir / "Playerarchi_SeedKeep_HWtest.sav"  # one save per multiworld: seed + slot
        playerarchi.write_bytes(playerarchi.read_bytes() + b"\x00")  # the player progressed in game
        digest = playerarchi.read_bytes()
        self.connect(ctx, seed="SeedKeep")  # same seed + slot: resume
        self.assertEqual(playerarchi.read_bytes(), digest)
        self.assertEqual([p.name for p in sav_dir.iterdir() if p.name.endswith(".bak")], [])


class TestPackets(LauncherTestCase):
    async def test_connected_starts_the_session_and_tells_the_game(self):
        ctx = self.make_ctx()
        self.connect(ctx, slot_data={"level_gates": {"4": "FNAF1"}, "gate_items": {"101000002": "FNAF1"}})
        self.assertEqual(ctx.core.state.session_id, "SeedL_HWtest")
        lines = self.inbox(ctx)
        for expected in ("CONNECTED", "SESSION_SYNC SeedL_HWtest", "GATE_TABLE 4=FNAF1", "GATE_ITEMS 101000002=FNAF1", "RECEIVED_SNAPSHOT"):
            self.assertIn(expected, lines)

    async def test_pending_checks_are_flushed_on_reconnect(self):
        ctx = self.make_ctx()
        self.connect(ctx)
        ctx.core.state.pending_locations.add(101100139)
        ctx.core._save_state()
        self.connect(ctx)
        await asyncio.sleep(0)  # let the scheduled send run
        self.assertEqual(ctx.sent, [[{"cmd": "LocationChecks", "locations": [101100139]}]])

    async def test_received_items_and_room_updates_reach_the_game(self):
        ctx = self.make_ctx()
        self.connect(ctx)
        ctx.on_package("ReceivedItems", {"cmd": "ReceivedItems", "index": 0,
                                         "items": [{"item": 101000002, "player": 1, "location": -2, "flags": 0}]})
        ctx.on_package("RoomUpdate", {"cmd": "RoomUpdate", "checked_locations": [101100138]})
        ctx.on_package("PrintJSON", {"cmd": "PrintJSON", "data": [{"text": "hello"}]})
        lines = self.inbox(ctx)
        self.assertIn("ITEM 101000002 1 -2 0 0", lines)
        self.assertIn("RECEIVED_SNAPSHOT 101000002", lines)
        self.assertIn("CONFIRMED_CHECK 101100138 Beat FNAF 1 - Night 1", lines)
        self.assertIn("PRINT hello", lines)

    async def test_deathlink_slot_subscribes_to_the_tag_and_forwards_deaths(self):
        ctx = self.make_ctx()
        self.connect(ctx, slot_data={"death_link": True})
        await asyncio.sleep(0)  # let the scheduled send run
        self.assertIn([{"cmd": "ConnectUpdate", "tags": ["AP", "DeathLink"]}], ctx.sent)
        ctx.on_package("Bounced", {"cmd": "Bounced", "tags": ["DeathLink"], "data": {"source": "Bob", "cause": "x", "time": 1.0}})
        self.assertIn("DEATHLINK Bob::x", self.inbox(ctx))

    async def test_without_deathlink_nothing_is_subscribed_and_deaths_are_dropped(self):
        ctx = self.make_ctx()
        self.connect(ctx)
        await asyncio.sleep(0)
        self.assertFalse(any(m and m[0].get("cmd") == "ConnectUpdate" for m in ctx.sent))
        ctx.on_package("Bounced", {"cmd": "Bounced", "tags": ["DeathLink"], "data": {"source": "Bob", "cause": "x", "time": 1.0}})
        self.assertFalse(any(l.startswith("DEATHLINK") for l in self.inbox(ctx)))

    async def test_connection_closed_marks_the_bridge_disconnected(self):
        ctx = self.make_ctx()
        self.connect(ctx)
        await ctx.connection_closed()
        self.assertEqual(ctx.core.status, "DISCONNECTED")
        self.assertIn("STATUS DISCONNECTED Disconnected.", self.inbox(ctx))

    async def test_server_auth_reports_authenticating_and_connects(self):
        ctx = self.make_ctx()
        ctx.server_address = "archipelago.gg:1"
        await ctx.server_auth(False)
        self.assertTrue(ctx.connect_sent)
        self.assertEqual(ctx.core.slot, "HWtest")
        self.assertTrue(any(line.startswith("STATUS AUTHENTICATING") for line in self.inbox(ctx)))


class TestBridgeWatcher(LauncherTestCase):
    def write_outbox(self, ctx, *lines):
        with ctx.core.bridge.outbox_path.open("a", encoding="utf-8") as handle:
            for line in lines:
                handle.write(line + "\n")

    async def test_game_check_is_sent_to_the_server(self):
        ctx = self.make_ctx()
        self.connect(ctx)
        self.write_outbox(ctx, "LOCATION_CHECK 101100139")
        await self.client.watch_bridge_once(ctx)
        self.assertEqual(ctx.sent, [[{"cmd": "LocationChecks", "locations": [101100139]}]])
        self.assertIn(101100139, ctx.core.state.pending_locations)
        await self.client.watch_bridge_once(ctx)  # the outbox line is consumed, not replayed
        self.assertEqual(len(ctx.sent), 1)

    async def test_connection_commands_from_the_game_are_ignored(self):
        ctx = self.make_ctx()
        self.connect(ctx)
        self.write_outbox(ctx, "CONNECT archipelago.gg 1 HWtest", "DISCONNECT", "SHOW_UI", "SAVE_PROFILE a 1 b")
        await self.client.watch_bridge_once(ctx)
        self.assertEqual(ctx.sent, [])
        self.assertEqual(ctx.core.status, "CONNECTED")

    async def test_items_applied_ack_and_goal(self):
        ctx = self.make_ctx()
        self.connect(ctx)
        self.write_outbox(ctx, "ITEMS_APPLIED 3", "GOAL")
        await self.client.watch_bridge_once(ctx)
        self.assertEqual(ctx.core.state.applied_item_count, 3)
        self.assertEqual(ctx.sent, [[{"cmd": "StatusUpdate", "status": 30}]])

    async def test_checks_are_queued_while_disconnected_and_flushed_on_connect(self):
        ctx = self.make_ctx()
        self.write_outbox(ctx, "LOCATION_CHECK 101100139")
        await self.client.watch_bridge_once(ctx)
        self.assertEqual(ctx.sent, [])
        self.assertIn(101100139, ctx.core.state.pending_locations)
        self.connect(ctx)  # a new session starts with its own pending set
        self.assertEqual(ctx.core.state.pending_locations, set())

    async def test_new_progress_in_the_save_is_sent_and_the_baseline_is_not(self):
        ctx = self.make_ctx()
        earned = ["Beat FNAF 1 - Night 1"]
        ctx.core.save_api.extract_earned = lambda parsed: list(earned)
        self.connect(ctx)  # the clean save is created from the starter template, baseline = earned now
        self.assertEqual(ctx.core.state.savegame_baseline, {"Beat FNAF 1 - Night 1"})
        earned.append("Beat FNAF 1 - Night 2")
        ctx.core._last_sav_poll_time = 0.0
        ctx.core._last_sav_mtime = 0.0
        await self.client.watch_bridge_once(ctx)
        night2 = self.data.LOCATION_OFFSET + self.data.LOCATION_TABLE["Beat FNAF 1 - Night 2"].code
        self.assertEqual(ctx.sent, [[{"cmd": "LocationChecks", "locations": [night2]}]])

    async def test_watcher_loop_survives_errors_and_stops_on_exit(self):
        ctx = self.make_ctx()
        calls = []

        async def exploding(_ctx):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")
            ctx.exit_event.set()

        original = self.client.watch_bridge_once
        self.client.watch_bridge_once = exploding
        try:
            await asyncio.wait_for(self.client.game_watcher(ctx), timeout=5)
        finally:
            self.client.watch_bridge_once = original
        self.assertEqual(len(calls), 2)  # the first error did not end the loop


class TestClientArguments(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        LauncherTestCase.setUpClass.__func__(LauncherTestCase)
        cls.client = LauncherTestCase.client

    @classmethod
    def tearDownClass(cls):
        LauncherTestCase.tearDownClass.__func__(LauncherTestCase)

    def test_unknown_launcher_arguments_do_not_end_the_client(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--connect", default=None)
        parser.add_argument("--password", default=None)
        args = self.client.parse_client_args(parser, ["FNAF Help Wanted Client", "--connect", "host:1", "--weird", "x"])
        self.assertEqual(args.connect, "host:1")
        self.assertIsNone(args.password)

    def test_name_option_is_supported_even_when_the_base_parser_lacks_it(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--connect", default=None)
        args = self.client.parse_client_args(parser, ["--connect", "host:1", "--name", "HWtest"])
        self.assertEqual((args.connect, args.name), ("host:1", "HWtest"))
        # a parser that already has --name must not break
        parser2 = argparse.ArgumentParser()
        parser2.add_argument("--name", default=None)
        self.assertEqual(self.client.parse_client_args(parser2, ["--name", "X"]).name, "X")

    def test_a_component_name_in_the_url_slot_is_not_treated_as_a_link(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("url", nargs="?")
        parser.add_argument("--connect", default=None)
        parser.add_argument("--password", default=None)
        # argparse.error() would raise SystemExit for a bad url: the client must carry on instead
        args = self.client.parse_client_args(parser, ["FNAF Help Wanted Client"])
        self.assertIsNone(args.connect)


class TestMergeLocationChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        LauncherTestCase.setUpClass.__func__(LauncherTestCase)
        cls.merge = staticmethod(LauncherTestCase.client.merge_location_checks)

    @classmethod
    def tearDownClass(cls):
        LauncherTestCase.tearDownClass.__func__(LauncherTestCase)

    def test_duplicates_are_merged_and_other_packets_keep_their_order(self):
        packets = [
            {"cmd": "Say", "text": "hi"},
            {"cmd": "LocationChecks", "locations": [3, 1]},
            {"cmd": "Sync"},
            {"cmd": "LocationChecks", "locations": [1, 2]},
        ]
        self.assertEqual(self.merge(packets), [
            {"cmd": "Say", "text": "hi"},
            {"cmd": "LocationChecks", "locations": [3, 1, 2]},
            {"cmd": "Sync"},
        ])

    def test_no_location_packets_is_unchanged_and_empty_is_empty(self):
        self.assertEqual(self.merge([{"cmd": "Sync"}]), [{"cmd": "Sync"}])
        self.assertEqual(self.merge([]), [])


class TestNoBridge(LauncherTestCase):
    """A client whose bridge could not start (another client holds the lock, or the folder is missing) must say so loudly and refuse to connect.
    It used to join the room silently and write nothing, so the game kept replaying the previous session and its save (found 2026-10-10)."""

    def second_client(self):
        self.make_ctx()  # the first client holds the lock
        second = self.make_ctx()
        self.assertIsNone(second.core)
        return second

    async def test_authenticating_without_a_bridge_logs_an_error_does_not_connect_and_disconnects(self):
        second = self.second_client()
        with self.assertLogs("fnafhw-launcher-test", level="ERROR") as logs:
            await second.server_auth()
        text = "\n".join(logs.output)
        self.assertIn("NOT connecting", text)
        self.assertIn("already running", text)
        self.assertIn("/disconnect does not release it", text)
        self.assertIn("close its window", text)
        self.assertFalse(second.connect_sent)
        self.assertTrue(second.disconnected)

    async def test_the_error_comes_back_at_every_attempt(self):
        second = self.second_client()
        for _ in range(2):
            with self.assertLogs("fnafhw-launcher-test", level="ERROR") as logs:
                await second.server_auth()
            self.assertIn("NOT connecting", "\n".join(logs.output))

    async def test_a_missing_bridge_folder_is_refused_the_same_way(self):
        os.environ["FNAFHW_BRIDGE_DIR"] = str(self.temp / "does_not_exist")
        old_roots = self.bridge_core.candidate_game_roots
        self.bridge_core.candidate_game_roots = lambda env=None: []
        try:
            ctx = self.make_ctx()
        finally:
            self.bridge_core.candidate_game_roots = old_roots
        with self.assertLogs("fnafhw-launcher-test", level="ERROR") as logs:
            await ctx.server_auth()
        self.assertIn("could not find the bridge folder", "\n".join(logs.output))
        self.assertFalse(ctx.connect_sent)
        self.assertTrue(ctx.disconnected)

    async def test_a_connected_packet_that_still_arrives_without_a_bridge_is_reported_not_swallowed(self):
        second = self.second_client()
        with self.assertLogs("fnafhw-launcher-test", level="ERROR") as logs:
            second.on_package("Connected", {"cmd": "Connected", "checked_locations": [], "slot_data": {}})
        self.assertIn("NOT connecting", "\n".join(logs.output))

    async def test_a_working_bridge_connects_without_any_error(self):
        ctx = self.make_ctx()
        with self.assertNoLogs("fnafhw-launcher-test", level="ERROR"):
            await ctx.server_auth()
        self.assertTrue(ctx.connect_sent)
        self.assertFalse(ctx.disconnected)

    async def test_closing_the_first_client_lets_a_new_one_start(self):
        first = self.make_ctx()
        await first.shutdown()
        second = self.make_ctx()
        self.assertIsNotNone(second.core, second.bridge_error)


class TestCommandProcessor(LauncherTestCase):
    async def test_bridge_command_reports_state_or_the_setup_error(self):
        ctx = self.make_ctx()
        self.connect(ctx)
        proc = self.client.FNAFHWCommandProcessor(ctx)
        proc._cmd_bridge()
        self.assertTrue(any("Bridge folder:" in line for line in proc.lines))
        self.assertTrue(any("SeedL_HWtest" in line for line in proc.lines))
        self.assertTrue(any("Save file: Playerarchi_SeedL_HWtest.sav" in line for line in proc.lines), proc.lines)

        broken = self.client.FNAFHWContext.__new__(self.client.FNAFHWContext)
        broken.core, broken.bridge_error = None, "no bridge"
        proc2 = self.client.FNAFHWCommandProcessor(broken)
        proc2._cmd_bridge()
        self.assertIn("Bridge not available: no bridge", proc2.lines[0])


if __name__ == "__main__":
    unittest.main()
