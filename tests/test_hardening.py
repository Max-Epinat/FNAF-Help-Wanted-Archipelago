"""Regression tests for the hardening of the standalone client and the connection panel (security audit, 2026-11-01).

No unauthenticated local command port; no silent downgrade from TLS to plaintext; the password never goes through the append-only outbox;
a bad command or packet never stops the client; the bridge and save files are written atomically.
"""

import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import ap_client.main as standalone
from ap_client import save_reader
from ap_client.bridge_core import BridgeIO, BridgeState, write_text_atomic
from ap_client.main import APBridgeClient
from tests.localappdata_isolation import isolate_localappdata
from tests.test_lua_logic import LIB, LuaCase, LuaRuntime

ROOT = project_root


class ClientCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="fnafhw_hard_"))
        isolate_localappdata(self, self.temp)
        self.bridge_dir = self.temp / "bridge"
        self.client = APBridgeClient(self.bridge_dir)

    async def asyncTearDown(self):
        self.client.release_single_instance_lock()
        shutil.rmtree(self.temp, ignore_errors=True)

    def inbox(self):
        return self.client.bridge.inbox_path.read_text(encoding="utf-8").splitlines()


class TestNoLocalCommandPort(unittest.TestCase):
    def test_the_standalone_client_opens_no_listening_socket(self):
        for name in ("IPC_PORT", "_start_ipc_server", "_handle_ipc_client"):
            self.assertFalse(hasattr(standalone, name) or hasattr(APBridgeClient, name), name)
        self.assertNotIn("start_server", Path(standalone.__file__).read_text(encoding="utf-8"))


class TestTransportSecurity(ClientCase):
    def uris(self, host, scheme=""):
        self.client.profile.update(server_host=host, server_port=38281, server_scheme=scheme)
        return self.client._build_uris()

    async def test_the_official_host_is_wss_only(self):
        self.assertEqual(self.uris("archipelago.gg"), ["wss://archipelago.gg:38281"])
        self.assertEqual(self.uris("eu.archipelago.gg"), ["wss://eu.archipelago.gg:38281"])

    async def test_another_host_tries_ws_then_wss_and_an_explicit_scheme_is_the_only_one(self):
        self.assertEqual(self.uris("my.server"), ["ws://my.server:38281", "wss://my.server:38281"])
        self.assertEqual(self.uris("my.server", "wss"), ["wss://my.server:38281"])

    async def test_a_dropped_session_is_not_retried_on_the_other_scheme(self):
        self.client.profile.update(server_host="my.server", server_port=38281, server_scheme="")
        calls = []

        class Dropped:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *exc):
                return False

            async def recv(self_inner):
                raise ConnectionResetError("network gone")

        def fake_connect(uri, **kwargs):
            calls.append(uri)
            return Dropped()

        with mock.patch.object(standalone.websockets, "connect", fake_connect):
            await self.client._session_loop()
        self.assertEqual(calls, ["ws://my.server:38281"])  # the wss attempt is for a server that never answered, not for a dropped session

    async def test_a_server_that_never_answers_still_falls_through_to_the_next_scheme(self):
        self.client.profile.update(server_host="my.server", server_port=38281, server_scheme="")
        calls = []

        def refuse(uri, **kwargs):
            calls.append(uri)
            raise ConnectionRefusedError("nobody home")

        with mock.patch.object(standalone.websockets, "connect", refuse):
            await self.client._session_loop()
        self.assertEqual(calls, ["ws://my.server:38281", "wss://my.server:38281"])


class TestOneCheapPoller(ClientCase):
    async def test_the_session_loop_leaves_the_outbox_and_the_save_to_run(self):
        self.client.profile.update(server_host="my.server", server_port=38281, server_scheme="ws")

        class Dropped:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *exc):
                return False

            async def recv(self_inner):
                raise ConnectionResetError("network gone")

        with mock.patch.object(standalone.websockets, "connect", lambda uri, **kw: Dropped()), \
                mock.patch.object(self.client, "_poll_outbox") as outbox, mock.patch.object(self.client, "_poll_savegame") as save:
            await self.client._session_loop()
        outbox.assert_not_called()  # two pollers could run the game's commands out of order
        save.assert_not_called()

    async def test_run_still_polls_both_every_cycle(self):
        calls = []

        async def outbox():
            calls.append("outbox")

        async def save():
            calls.append("save")
            raise asyncio.CancelledError  # end the endless loop after one cycle

        with mock.patch.object(self.client, "_poll_outbox", outbox), mock.patch.object(self.client, "_poll_savegame", save):
            with self.assertRaises(asyncio.CancelledError):
                await self.client.run()
        self.assertEqual(calls, ["outbox", "save"])

    async def test_an_outbox_with_nothing_new_is_not_opened(self):
        outbox = self.client.bridge.outbox_path
        outbox.write_text("SYNC\n", encoding="utf-8")
        self.client.state.outbox_position = outbox.stat().st_size
        with mock.patch("pathlib.Path.open", side_effect=AssertionError("opened for nothing")):
            self.assertEqual(self.client.bridge.read_outbox_lines(self.client.state), [])

    async def test_new_lines_are_still_read_once_and_only_once(self):
        outbox = self.client.bridge.outbox_path
        outbox.write_text("SYNC\n", encoding="utf-8")
        self.client.state.outbox_position = 0
        self.assertEqual(self.client.bridge.read_outbox_lines(self.client.state), ["SYNC"])
        self.assertEqual(self.client.bridge.read_outbox_lines(self.client.state), [])
        with outbox.open("a", encoding="utf-8") as handle:
            handle.write("GOAL\n")
        self.assertEqual(self.client.bridge.read_outbox_lines(self.client.state), ["GOAL"])

    async def test_a_shortened_outbox_is_read_again_from_the_start(self):
        outbox = self.client.bridge.outbox_path
        outbox.write_text("A\nB\nC\n", encoding="utf-8")
        self.client.state.outbox_position = outbox.stat().st_size
        outbox.write_text("X\n", encoding="utf-8")
        self.assertEqual(self.client.bridge.read_outbox_lines(self.client.state), ["X"])


class TestNoInventedSession(ClientCase):
    async def test_a_server_that_gives_no_seed_name_starts_no_session(self):
        await self.client._handle_server_payload(json.dumps([{"cmd": "RoomInfo", "seed_name": ""}]))
        self.client.slot = "HWtest"
        before = sorted(p.name for p in self.client.bridge.sessions_dir.iterdir())
        with mock.patch.object(self.client.save_api, "ensure_clean_save") as clean:
            await self.client._handle_server_payload(json.dumps([{"cmd": "Connected", "checked_locations": [], "slot_data": {}}]))
        self.assertEqual(self.client.status, standalone.STATUS_ERROR)
        self.assertIn("did not tell the seed name", self.client.last_error)
        self.assertTrue(self.client.disconnect_requested)
        self.assertEqual(sorted(p.name for p in self.client.bridge.sessions_dir.iterdir()), before)  # no "unknown_seed_HWtest" session
        clean.assert_not_called()  # and no save was archived or created
        self.assertFalse(any(line.startswith("SESSION_SYNC") for line in self.inbox()))

    async def test_a_real_seed_still_starts_the_session(self):
        await self.client._handle_server_payload(json.dumps([{"cmd": "RoomInfo", "seed_name": "SeedZ"}]))
        self.client.slot = "HWtest"
        await self.client._handle_server_payload(json.dumps([{"cmd": "Connected", "checked_locations": [], "slot_data": {}}]))
        self.assertEqual(self.client.status, standalone.STATUS_CONNECTED)
        self.assertEqual(self.client.state.session_id, "SeedZ_HWtest")


class TestNoDeadLuaIsShipped(unittest.TestCase):
    def test_every_module_in_lib_is_loaded_by_the_mod(self):
        scripts = LIB.parent
        loaders = "\n".join(path.read_text(encoding="utf-8") for path in [scripts / "main.lua", *sorted(LIB.glob("*.lua"))])
        for module in sorted(LIB.glob("*.lua")):
            self.assertIn(f"/Scripts/lib/{module.name}", loaders, f"{module.name} is shipped but nothing loads it: delete it, or load it")


class TestCommandsNeverStopTheClient(ClientCase):
    async def test_a_bad_port_is_refused_and_changes_nothing(self):
        before = dict(self.client.profile)
        for line in ("CONNECT host notaport slot", "CONNECT host 0 slot", "CONNECT host 70000 slot", "CONNECT host", "SAVE_PROFILE h ² s"):
            await self.client._execute_command(line)
        self.assertEqual(self.client.profile, before)
        self.assertFalse(self.client.connect_event.is_set())
        self.assertIn("PRINT Invalid connection settings, expected: <host> <port 1-65535> <slot> [password]", self.inbox())

    async def test_the_explicit_form_is_still_accepted_and_saved(self):
        await self.client._execute_command("CONNECT my.server 4000 Slot1 secret")
        self.assertTrue(self.client.connect_event.is_set())
        saved = json.loads(self.client.bridge.profile_path.read_text(encoding="utf-8"))
        self.assertEqual((saved["server_host"], saved["server_port"], saved["slot"]), ("my.server", 4000, "Slot1"))
        self.assertNotIn("password", saved)  # it is in the encrypted store (TestThePasswordFlowThroughTheClient)

    async def test_a_bare_connect_uses_the_saved_profile_whatever_the_slot_name(self):
        self.client.profile.update(server_host="my.server", server_port=4000, slot="Player One", password="with space")
        self.client.bridge.save_profile(self.client.profile)  # a bare CONNECT reads the saved profile, as the window and the panel save it first
        await self.client._execute_command("CONNECT")
        self.assertTrue(self.client.connect_event.is_set())
        self.assertEqual(self.client.slot, "Player One")
        self.assertEqual(self.client.profile["password"], "with space")  # not cut at the spaces, not blanked

    async def test_a_bare_connect_reads_the_profile_the_game_panel_just_wrote(self):
        # the F1 panel writes connection_profile.json and sends a bare CONNECT; the client loaded the profile once, at start
        self.client.bridge.profile_path.write_text(
            json.dumps({"server_host": "panel.host", "server_port": 5555, "slot": "FromPanel"}), encoding="utf-8")
        await self.client._execute_command("CONNECT")
        self.assertEqual((self.client.server_str, self.client.slot), ("panel.host:5555", "FromPanel"))

    async def test_a_profile_that_cannot_be_read_keeps_the_settings_in_use(self):
        self.client.profile.update(server_host="kept.host", server_port=4000, slot="Kept")
        self.client.bridge.profile_path.write_text("{ not json", encoding="utf-8")
        with mock.patch("builtins.print"):
            await self.client._execute_command("CONNECT")
        self.assertEqual((self.client.server_str, self.client.slot), ("kept.host:4000", "Kept"))  # not archipelago.gg / Player1

    async def test_one_bad_outbox_line_does_not_stop_the_others(self):
        self.client.bridge.outbox_path.write_text("FIRST\nSECOND\n", encoding="utf-8")
        self.client.state.outbox_position = 0
        with mock.patch.object(self.client, "_execute_command", side_effect=[ValueError("boom"), None]) as spy:
            await self.client._poll_outbox()
        self.assertEqual(spy.call_count, 2)  # the second line was still executed

    async def test_odd_server_packets_are_skipped_and_do_not_raise(self):
        await self.client._handle_server_payload(json.dumps(["not a dict", 5, None, {"cmd": "RoomUpdate", "checked_locations": ["x"]}]))
        await self.client._handle_server_payload("not json at all")

    async def test_a_connected_packet_that_fails_ends_the_attempt_with_an_error(self):
        with mock.patch.object(self.client, "on_connected", side_effect=RuntimeError("cannot start")):
            await self.client._handle_server_payload(json.dumps([{"cmd": "Connected"}]))
        self.assertTrue(self.client.disconnect_requested)
        self.assertEqual(self.client.status, standalone.STATUS_ERROR)

    async def test_a_failing_scheduled_command_is_reported_not_lost(self):
        future = asyncio.get_running_loop().create_future()
        future.set_exception(ValueError("nope"))
        with mock.patch("builtins.print") as printed:
            APBridgeClient._report_command_failure(future)
        self.assertIn("nope", str(printed.call_args))


class TestAnUnreadableOutboxNeverStopsTheClient(ClientCase):
    """The outbox is a file another program appends to. A strict UTF-8 decode raised in read_outbox_lines, outside the per-line protection, and
    ended the client's loop for good (found in the real game: the lock was released, nothing was polled any more, the check behind the bad
    line was never sent)."""

    def outbox(self, data: bytes):
        path = self.client.bridge.outbox_path
        path.write_bytes(data)
        self.client.state.outbox_position = 0
        return path

    def read(self):
        return self.client.bridge.read_outbox_lines(self.client.state)

    async def test_a_binary_line_is_skipped_and_the_lines_around_it_are_read(self):
        path = self.outbox(b"SYNC\n\xff\xfe\x00\x01 junk \x80\nLOCATION_CHECK_NAME Beat FNAF 1 - Night 4\n")
        with mock.patch("builtins.print") as said:
            lines = self.read()
        self.assertEqual(len(lines), 3)
        self.assertEqual((lines[0], lines[2]), ("SYNC", "LOCATION_CHECK_NAME Beat FNAF 1 - Night 4"))
        self.assertIn("�", lines[1])  # read with replacement characters: an unknown command, ignored by the executor
        self.assertEqual(self.client.state.outbox_position, path.stat().st_size)  # past the bad line, nothing is read twice
        self.assertEqual(self.read(), [])
        self.assertTrue(any("not valid UTF-8" in str(call) for call in said.call_args_list))  # and it is said

    async def test_a_multibyte_character_cut_in_half_is_read_complete_on_the_next_pass(self):
        full = "LOCATION_CHECK_NAME Café Bar".encode("utf-8")
        cut = full.index("é".encode("utf-8")) + 1  # the write stops after the first byte of the 2-byte character
        path = self.outbox(b"SYNC\n" + full[:cut])
        self.assertEqual(self.read(), ["SYNC"])  # the half-written line is left alone, not read cut or with a replacement character
        self.assertEqual(self.client.state.outbox_position, len(b"SYNC\n"))
        self.assertEqual(self.read(), [])
        with path.open("ab") as handle:
            handle.write(full[cut:] + b"\n")
        self.assertEqual(self.read(), ["LOCATION_CHECK_NAME Café Bar"])  # the whole line, nothing lost
        self.assertEqual(self.client.state.outbox_position, path.stat().st_size)

    async def test_a_whole_last_line_without_a_line_break_is_still_read_at_once(self):
        self.outbox(b"SYNC\nGOAL")
        self.assertEqual(self.read(), ["SYNC", "GOAL"])
        self.assertEqual(self.read(), [])

    async def test_a_line_with_a_whole_multibyte_character_is_unchanged(self):
        self.outbox("SAY héllo 世界 \U0001f600\n".encode("utf-8"))
        self.assertEqual(self.read(), ["SAY héllo 世界 \U0001f600"])

    async def test_the_poll_executes_the_valid_line_after_a_binary_one(self):
        self.outbox(b"\xff\xfe\x00 junk\nLOCATION_CHECK_NAME Beat FNAF 1 - Night 4\n")
        seen = []

        async def execute(line):
            seen.append(line)

        self.client._execute_command = execute
        with mock.patch("builtins.print"):
            await self.client._poll_outbox()
        self.assertEqual(seen[-1], "LOCATION_CHECK_NAME Beat FNAF 1 - Night 4")

    async def test_a_failed_read_does_not_end_the_poll_and_is_said_once(self):
        self.client.bridge.read_outbox_lines = mock.Mock(side_effect=[OSError("denied"), OSError("denied"), ["SYNC"]])
        seen = []

        async def execute(line):
            seen.append(line)

        self.client._execute_command = execute
        with mock.patch("builtins.print") as said:
            await self.client._poll_outbox()  # must not raise
            await self.client._poll_outbox()
            self.assertEqual(seen, [])
            await self.client._poll_outbox()  # the next read works: the loop was never lost
        self.assertEqual(seen, ["SYNC"])
        self.assertEqual(sum("Could not read the game's outbox" in str(call) for call in said.call_args_list), 1)


class TestAtomicWrites(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fnafhw_atomic_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def leftovers(self):
        return [p.name for p in self.tmp.rglob("*.tmp")]

    def test_a_text_write_replaces_the_file_and_leaves_no_temp_file(self):
        target = self.tmp / "state.json"
        target.write_text("old", encoding="utf-8")
        write_text_atomic(target, "new")
        self.assertEqual(target.read_text(encoding="utf-8"), "new")
        self.assertEqual(self.leftovers(), [])

    def test_a_replace_that_windows_refuses_falls_back_to_writing_in_place(self):
        target = self.tmp / "state.json"
        target.write_text("old", encoding="utf-8")
        with mock.patch("os.replace", side_effect=PermissionError("open in the game")):
            write_text_atomic(target, "new")
        self.assertEqual(target.read_text(encoding="utf-8"), "new")
        self.assertEqual(self.leftovers(), [])

    def test_an_interrupted_write_keeps_the_previous_file(self):
        target = self.tmp / "state.json"
        target.write_text("good", encoding="utf-8")
        with mock.patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                write_text_atomic(target, "half")
        self.assertEqual(target.read_text(encoding="utf-8"), "good")

    def test_the_bridge_state_is_written_atomically_and_a_failure_is_reported_not_raised(self):
        bridge = BridgeIO(self.tmp / "bridge")
        state = BridgeState(session_id="Seed_Slot", checked_locations={1, 2})
        bridge.save_state(state)
        self.assertEqual(json.loads(bridge.state_path.read_text(encoding="utf-8"))["checked_locations"], [1, 2])
        self.assertEqual(self.leftovers(), [])
        bridge.state_path.unlink()
        bridge.state_path.mkdir()  # a directory where the file should be: every way of writing it fails
        with mock.patch("builtins.print") as printed:
            bridge.save_state(BridgeState())
        self.assertTrue(any("Could not write ap_state.json" in str(call) for call in printed.call_args_list))

    def test_an_unreadable_state_file_is_reported(self):
        bridge = BridgeIO(self.tmp / "bridge")
        bridge.state_path.write_text("{not json", encoding="utf-8")
        with mock.patch("builtins.print") as printed:
            self.assertEqual(bridge.load_state().session_id, "")
        self.assertTrue(any("Could not read ap_state.json" in str(call) for call in printed.call_args_list))

    def test_the_clean_save_is_written_atomically(self):
        target = self.tmp / "Playerarchi_x.sav"
        template = self.tmp / "Player00.sav"
        template.write_bytes(b"template")
        with mock.patch.object(save_reader, "create_clean_playerarchi_data", return_value=b"clean"):
            save_reader.ensure_clean_archipelago_save(target_path=target, template_path=template)
        self.assertEqual(target.read_bytes(), b"clean")
        self.assertEqual(self.leftovers(), [])
        with mock.patch("os.replace", side_effect=PermissionError("the game has it open")):
            with mock.patch.object(save_reader, "create_clean_playerarchi_data", return_value=b"clean2"):
                save_reader.ensure_clean_archipelago_save(target_path=target, template_path=template)
        self.assertEqual(target.read_bytes(), b"clean2")
        self.assertEqual(self.leftovers(), [])


class TestConnectionPanelCredentials(LuaCase):
    """The panel never writes the password into the profile: a new one goes to a drop file the client encrypts and deletes."""

    def panel(self, tmp):
        sent = []
        module = self.load("connection_ui.lua")
        bridge = self.lua.table(append_outbox=lambda command: sent.append(str(command)))
        module.init(self.lua.table(bridge_dir=tmp, APBridge=bridge, mod_dir=tmp))
        return module, sent

    def profile(self, tmp):
        return json.loads((Path(tmp) / "connection_profile.json").read_text(encoding="utf-8"))

    def drop(self, tmp):
        path = Path(tmp) / "connection_password.txt"
        return path.read_bytes().decode("utf-8") if path.exists() else None

    def test_connecting_sends_a_bare_command_and_the_password_never_enters_the_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            module, sent = self.panel(tmp)
            module.fields.host, module.fields.port, module.fields.slot, module.fields.password = "my.server", "4000", "Player One", "s3cret"
            module.password_dirty = True
            module.connect()
            self.assertEqual(sent, ["CONNECT"])
            self.assertNotIn("s3cret", " ".join(sent))
            profile = self.profile(tmp)
            self.assertEqual((profile["server_host"], profile["server_port"], profile["slot"]), ("my.server", 4000, "Player One"))
            self.assertNotIn("password", profile)
            self.assertNotIn("s3cret", (Path(tmp) / "connection_profile.json").read_text(encoding="utf-8"))
            self.assertEqual(self.drop(tmp), "s3cret")  # waiting for the client to encrypt it
            self.assertEqual(str(module.fields.password), "")  # not kept in the panel once handed over
            self.assertTrue(module.password_saved)

    def test_a_password_with_quotes_and_backslashes_is_handed_over_exactly(self):
        tricky = 'a"b\\c","auto_connect":false é'
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self.panel(tmp)
            module.fields.password = tricky
            module.password_dirty = True
            module.fields.slot = 'Sl"ot'
            module.connect()
            profile = self.profile(tmp)  # valid JSON, nothing injected
            self.assertIs(profile["auto_connect"], True)
            self.assertEqual(self.drop(tmp), tricky)
            reloaded, _ = self.panel(tmp)  # a fresh panel reads the rest back
            self.assertEqual(str(reloaded.fields.slot), 'Sl"ot')

    def test_a_connect_without_a_new_password_touches_no_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "connection_secret.dat").write_text("plain:c2VjcmV0", encoding="utf-8")  # the client's encrypted store
            module, _ = self.panel(tmp)
            self.assertEqual(str(module.password_text()), "(saved)")
            module.connect()
            self.assertIsNone(self.drop(tmp))  # nothing handed over: the saved password stays
            self.assertTrue((Path(tmp) / "connection_secret.dat").exists())

    def test_the_password_row_shows_none_saved_or_asterisks_and_never_the_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = self.panel(tmp)
            self.assertEqual(str(module.password_text()), "(none)")
            module.fields.password = "abcd"
            self.assertEqual(str(module.password_text()), "****")
            module.fields.password = ""
            (Path(tmp) / "connection_secret.dat").write_text("plain:c2VjcmV0", encoding="utf-8")
            module.update_state()
            self.assertEqual(str(module.password_text()), "(saved)")

    def test_a_password_cleared_in_the_panel_is_handed_over_as_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.lua.execute("__keys = {}  RegisterKeyBind = function(key, fn) __keys[key] = fn end  Key = setmetatable({}, {__index = function(_, k) return k end})")
            (Path(tmp) / "connection_secret.dat").write_text("plain:c2VjcmV0", encoding="utf-8")
            module, _ = self.panel(tmp)
            module.is_visible = True
            module.selected_index = 4
            self.lua.globals()["__keys"]["BACKSPACE"]()  # Backspace on the "(saved)" row forgets it
            self.assertEqual(str(module.password_text()), "(none)")
            module.connect()
            self.assertEqual(self.drop(tmp), "")
            module.update_state()
            self.assertEqual(str(module.password_text()), "(none)")  # an empty drop is "no password", not "saved"

    def test_ap_connect_with_all_arguments_sets_the_password_and_without_one_clears_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.panel(tmp)
            command = self.lua.globals()["__cmds"]["ap_connect"]
            command("ap_connect", "h.example 1234 Slot1 pw")
            self.assertEqual(self.drop(tmp), "pw")
            command("ap_connect", "h.example 1234 Slot1")
            self.assertEqual(self.drop(tmp), "")

    def test_ap_connect_takes_its_parameters_as_a_table_the_way_ue4ss_passes_them(self):
        # UE4SS calls a console handler with (full command, table of parameter words, output device): a string-only handler failed with
        # "bad argument #1 to 'gmatch' (string expected, got table)" in the real game
        with tempfile.TemporaryDirectory() as tmp:
            module, sent = self.panel(tmp)
            command = self.lua.globals()["__cmds"]["ap_connect"]
            command("ap_connect", self.lua.table("h.example", "1234", "Slot1", "pw"))
            self.assertEqual(self.drop(tmp), "pw")
            self.assertEqual(sent, ["CONNECT"])
            self.assertEqual((str(module.fields.host), str(module.fields.port), str(module.fields.slot)), ("h.example", "1234", "Slot1"))
            command("ap_connect", self.lua.table("h.example", "1234", "Slot1"))
            self.assertEqual(self.drop(tmp), "")
            profile = self.profile(tmp)
            self.assertEqual((profile["server_host"], profile["server_port"], profile["slot"]), ("h.example", 1234, "Slot1"))
            self.assertNotIn("password", profile)

    def test_a_bare_ap_connect_connects_with_the_saved_settings(self):
        for params in (self.lua.table(), None):  # UE4SS passes an empty table; nothing at all is accepted too
            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / "connection_profile.json").write_text(
                    json.dumps({"server_host": "kept.example", "server_port": 4321, "slot": "Kept"}), encoding="utf-8")
                module, sent = self.panel(tmp)
                command = self.lua.globals()["__cmds"]["ap_connect"]
                command("ap_connect", params)
                self.assertEqual(sent, ["CONNECT"])
                self.assertEqual((str(module.fields.host), str(module.fields.port), str(module.fields.slot)), ("kept.example", "4321", "Kept"))
                self.assertFalse((Path(tmp) / "connection_password.txt").exists())  # no new password: the saved one is not touched

    def test_a_password_left_in_an_old_profile_is_not_read_by_the_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "connection_profile.json").write_text(
                json.dumps({"server_host": "h.example", "server_port": 1234, "slot": "Café \"X\"", "password": "p\\w"}), encoding="utf-8")
            module, _ = self.panel(tmp)
            self.assertEqual(str(module.fields.slot), 'Café "X"')
            self.assertEqual(str(module.fields.port), "1234")
            self.assertEqual(str(module.fields.password), "")  # the client moves it into its encrypted store


class TestThePasswordIsNotInPlainSight(unittest.TestCase):
    """connection_profile.json never holds the password; it lives encrypted in connection_secret.dat (Windows DPAPI: this account only)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fnafhw_secret_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bridge = BridgeIO(self.tmp)

    def profile_text(self):
        return self.bridge.profile_path.read_text(encoding="utf-8")

    def test_a_saved_password_is_not_in_the_profile_and_is_not_readable_in_the_secret_file(self):
        profile = self.bridge.load_profile()
        profile["password"] = "s3cret ünï \"q\""
        self.bridge.save_profile(profile)
        self.assertNotIn("password", json.loads(self.profile_text()))
        self.assertNotIn("s3cret", self.profile_text())
        stored = self.bridge.secret_path.read_bytes()
        self.assertNotIn(b"s3cret", stored)
        self.assertNotIn(base64.b64encode("s3cret".encode()), stored)
        if os.name == "nt":
            self.assertTrue(stored.startswith(b"dpapi:"))
        self.assertEqual(self.bridge.load_profile()["password"], "s3cret ünï \"q\"")

    @unittest.skipUnless(os.name == "nt", "DPAPI is Windows only")
    def test_the_blob_only_opens_with_this_programs_entropy(self):
        from ap_client import bridge_core

        blob = bridge_core._dpapi(b"hello", True)
        self.assertNotIn(b"hello", blob)
        self.assertEqual(bridge_core._dpapi(blob, False), b"hello")
        with mock.patch.object(bridge_core, "SECRET_ENTROPY", b"another program"):
            with self.assertRaises(OSError):
                bridge_core._dpapi(blob, False)

    def test_the_window_thread_and_the_client_thread_can_save_at_the_same_time(self):
        import threading

        from ap_client.bridge_core import protect_secret, unprotect_secret

        failures = []

        def worker(number):
            try:
                for turn in range(60):
                    text = f"pw-{number}-{turn}-é"
                    if unprotect_secret(protect_secret(text)) != text:
                        failures.append(f"wrong text for {text}")
            except Exception as e:  # an ArgumentError from shared argtypes would land here
                failures.append(repr(e))

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        self.assertEqual(failures, [])

    def test_the_other_settings_survive_and_the_password_is_replaced_or_cleared(self):
        profile = self.bridge.load_profile()
        profile.update(server_host="h.example", server_port=1234, slot="S", password="one")
        self.bridge.save_profile(profile)
        profile["password"] = "two"
        self.bridge.save_profile(profile)
        loaded = self.bridge.load_profile()
        self.assertEqual((loaded["server_host"], loaded["server_port"], loaded["slot"], loaded["password"]), ("h.example", 1234, "S", "two"))
        profile["password"] = ""
        self.bridge.save_profile(profile)
        self.assertFalse(self.bridge.secret_path.exists())
        self.assertEqual(self.bridge.load_profile()["password"], "")

    def test_a_password_from_an_older_version_is_moved_out_of_the_profile(self):
        self.bridge.profile_path.write_text(json.dumps({"server_host": "old.host", "server_port": 99, "slot": "Old", "password": "plain-old"}), encoding="utf-8")
        with mock.patch("builtins.print") as printed:
            loaded = self.bridge.load_profile()
        self.assertEqual((loaded["password"], loaded["server_host"]), ("plain-old", "old.host"))
        self.assertNotIn("plain-old", self.profile_text())
        self.assertNotIn("password", json.loads(self.profile_text()))
        self.assertTrue(any("Moved the password out of" in str(call) for call in printed.call_args_list))
        self.assertEqual(self.bridge.load_profile()["password"], "plain-old")  # and it is still there the next time

    def test_an_empty_password_in_an_old_profile_does_not_wipe_the_saved_one(self):
        self.bridge.save_profile({**self.bridge.load_profile(), "password": "kept"})
        data = json.loads(self.profile_text())
        data["password"] = ""
        self.bridge.profile_path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.bridge.load_profile()["password"], "kept")
        self.assertNotIn("password", json.loads(self.profile_text()))

    def test_the_panels_drop_file_is_encrypted_and_deleted(self):
        self.bridge.load_profile()
        self.bridge.password_drop_path.write_bytes("from panel é".encode("utf-8"))
        loaded = self.bridge.load_profile()
        self.assertEqual(loaded["password"], "from panel é")
        self.assertFalse(self.bridge.password_drop_path.exists())
        self.assertNotIn(b"from panel", self.bridge.secret_path.read_bytes())

    def test_an_empty_drop_file_clears_the_saved_password(self):
        self.bridge.save_profile({**self.bridge.load_profile(), "password": "old"})
        self.bridge.password_drop_path.write_bytes(b"")
        self.assertEqual(self.bridge.load_profile()["password"], "")
        self.assertFalse(self.bridge.secret_path.exists())
        self.assertFalse(self.bridge.password_drop_path.exists())

    def test_a_new_password_from_the_panel_beats_an_old_one_in_the_profile(self):
        self.bridge.profile_path.write_text(json.dumps({"slot": "S", "password": "stale"}), encoding="utf-8")
        self.bridge.password_drop_path.write_bytes(b"fresh")
        self.assertEqual(self.bridge.load_profile()["password"], "fresh")
        self.assertNotIn("stale", self.profile_text())

    def test_when_it_cannot_be_encrypted_nothing_is_lost_and_nothing_is_written_in_the_clear_elsewhere(self):
        self.bridge.profile_path.write_text(json.dumps({"slot": "S", "password": "keep-me"}), encoding="utf-8")
        with mock.patch("ap_client.bridge_core.protect_secret", side_effect=OSError("no key")), mock.patch("builtins.print"):
            loaded = self.bridge.load_profile()
        self.assertEqual(loaded["password"], "keep-me")  # still usable this run, and still where it was: not silently dropped
        self.assertFalse(self.bridge.secret_path.exists())
        self.bridge.password_drop_path.write_bytes(b"panel")
        with mock.patch("ap_client.bridge_core.protect_secret", side_effect=OSError("no key")), mock.patch("builtins.print"):
            self.bridge.load_profile()
        self.assertTrue(self.bridge.password_drop_path.exists())  # kept so the player's input is not lost

    def test_a_secret_this_account_cannot_read_gives_no_password_and_no_crash(self):
        self.bridge.load_profile()
        self.bridge.secret_path.write_text("dpapi:AAAA", encoding="utf-8")
        with mock.patch("builtins.print") as printed:
            self.assertEqual(self.bridge.load_profile()["password"], "")
        self.assertTrue(any("cannot be read here" in str(call) for call in printed.call_args_list))
        self.bridge.secret_path.write_text("garbage", encoding="utf-8")
        with mock.patch("builtins.print"):
            self.assertEqual(self.bridge.load_profile()["password"], "")

    def test_no_temp_files_are_left_behind(self):
        self.bridge.save_profile({**self.bridge.load_profile(), "password": "x"})
        self.assertEqual([p.name for p in self.tmp.rglob("*.tmp")], [])


class TestGoingBackToAnOlderRoom(ClientCase):
    """Each session saves its own read position in the outbox. Returning to room A after playing room B must not re-read what B's game wrote."""

    def join(self, seed, slot="P"):
        self.client.current_seed_name = seed
        self.client.slot = slot
        with mock.patch("builtins.print"):
            self.client.on_connected({"cmd": "Connected", "checked_locations": [], "slot_data": {}})

    def play(self, *lines):
        with self.client.bridge.outbox_path.open("a", encoding="utf-8", newline="") as handle:
            for line in lines:
                handle.write(line + "\n")
        got = self.client.bridge.read_outbox_lines(self.client.state)
        self.client.bridge.save_state(self.client.state, self.client.location_id_to_name)
        return got

    async def test_the_lines_of_another_room_are_not_read_again(self):
        self.join("SeedA")
        self.assertEqual(self.play("LOCATION_CHECK_NAME Beat FNAF 1 - Night 1"), ["LOCATION_CHECK_NAME Beat FNAF 1 - Night 1"])
        self.join("SeedB")
        self.assertEqual(self.play("LOCATION_CHECK_NAME Beat FNAF 1 - Night 2"), ["LOCATION_CHECK_NAME Beat FNAF 1 - Night 2"])
        self.join("SeedA")  # back to room A
        self.assertEqual(self.client.bridge.read_outbox_lines(self.client.state), [])  # room B's check is not room A's
        self.assertEqual(self.play("LOCATION_CHECK_NAME Beat FNAF 1 - Night 3"), ["LOCATION_CHECK_NAME Beat FNAF 1 - Night 3"])  # new lines still arrive

    async def test_reconnecting_to_the_same_room_loses_nothing(self):
        self.join("SeedA")
        self.play("LOCATION_CHECK_NAME one")
        self.client.bridge.outbox_path.open("a", encoding="utf-8", newline="").write("LOCATION_CHECK_NAME written while the client was between rooms\n")
        self.join("SeedA")
        self.assertEqual(self.client.bridge.read_outbox_lines(self.client.state), ["LOCATION_CHECK_NAME written while the client was between rooms"])


class TestOldPasswordsInTheOutboxAreMasked(unittest.TestCase):
    OLD = ("CONNECT my.server 4000 Slot1 hunter2\r\n"
           "LOCATION_CHECK 5\r\n"
           "SAVE_PROFILE other.host 38281 Player2 pässword\n"
           "CONNECT\n"
           "CONNECT a.b 1 slot\n")
    LATER = "CONNECT new.host 5 Slot9 not-yet-executed\n"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fnafhw_outbox_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bridge = BridgeIO(self.tmp)
        self.bridge.outbox_path.write_bytes((self.OLD + self.LATER).encode("utf-8"))
        self.executed = len(self.OLD.encode("utf-8"))

    def text(self):
        return self.bridge.outbox_path.read_bytes().decode("utf-8")

    def test_only_the_executed_part_is_masked_and_the_file_keeps_its_size(self):
        size = self.bridge.outbox_path.stat().st_size
        self.assertEqual(self.bridge.scrub_outbox_passwords(self.executed), 2)
        text = self.text()
        self.assertNotIn("hunter2", text)
        self.assertNotIn("pässword", text)
        self.assertIn("CONNECT my.server 4000 Slot1 *******\r\n", text)
        self.assertEqual(self.bridge.outbox_path.stat().st_size, size)  # byte for byte, so the saved read position is still right
        self.assertTrue(text.endswith(self.LATER))  # not executed yet: left as the game wrote it
        self.assertIn("LOCATION_CHECK 5\r\n", text)
        self.assertIn("\nCONNECT\nCONNECT a.b 1 slot\n", text)  # no password there, nothing to mask

    def test_a_second_pass_changes_nothing(self):
        self.bridge.scrub_outbox_passwords(self.executed)
        once = self.bridge.outbox_path.read_bytes()
        self.assertEqual(self.bridge.scrub_outbox_passwords(self.executed), 0)
        self.assertEqual(self.bridge.outbox_path.read_bytes(), once)

    def test_nothing_is_masked_before_anything_was_executed_or_without_a_file(self):
        before = self.bridge.outbox_path.read_bytes()
        self.assertEqual(self.bridge.scrub_outbox_passwords(0), 0)
        self.assertEqual(self.bridge.outbox_path.read_bytes(), before)
        self.bridge.outbox_path.unlink()
        self.assertEqual(self.bridge.scrub_outbox_passwords(100), 0)

    def test_a_position_past_the_end_is_clamped(self):
        self.assertEqual(self.bridge.scrub_outbox_passwords(10 ** 9), 3)

    def test_starting_a_client_core_masks_what_it_already_ran(self):
        from ap_client.bridge_core import BridgeCore

        (self.tmp / "ap_state.json").write_text(json.dumps({"outbox_position": self.executed}), encoding="utf-8")
        with mock.patch("builtins.print") as printed:
            BridgeCore(self.tmp, bridge=self.bridge)
        self.assertNotIn("hunter2", self.text())
        self.assertIn("not-yet-executed", self.text())
        self.assertTrue(any("Masked 2 password(s)" in str(call) for call in printed.call_args_list))


class TestThePasswordFlowThroughTheClient(ClientCase):
    async def test_the_explicit_old_form_stores_the_password_encrypted(self):
        await self.client._execute_command("CONNECT my.server 4000 Slot1 secret")
        self.assertNotIn("secret", self.client.bridge.profile_path.read_text(encoding="utf-8"))
        self.assertEqual(self.client.bridge.read_password(), "secret")
        self.assertEqual(self.client.profile["password"], "secret")

    async def test_a_password_set_in_the_game_panel_is_used_by_the_next_connect(self):
        bridge = self.client.bridge
        bridge.profile_path.write_text(json.dumps({"server_host": "panel.host", "server_port": 5555, "slot": "FromPanel"}), encoding="utf-8")
        bridge.password_drop_path.write_bytes(b"panel pw")
        await self.client._execute_command("CONNECT")
        self.assertEqual(self.client.profile["password"], "panel pw")
        self.assertEqual(self.client.build_connect_packet("u")["password"], "panel pw")
        self.assertFalse(bridge.password_drop_path.exists())

    async def test_the_window_saves_then_connects_and_the_password_survives_the_reload(self):
        self.client.profile.update(server_host="my.server", server_port=4000, slot="Player One", password="with space")
        self.client.bridge.save_profile(self.client.profile)  # what the window does before it sends CONNECT
        await self.client._execute_command("CONNECT")
        self.assertEqual((self.client.slot, self.client.profile["password"]), ("Player One", "with space"))

    async def test_a_client_start_moves_an_old_plaintext_password_out_of_the_profile(self):
        self.client.release_single_instance_lock()
        (self.bridge_dir / "connection_profile.json").write_text(json.dumps({"slot": "S", "password": "legacy"}), encoding="utf-8")
        with mock.patch("builtins.print"):
            self.client = APBridgeClient(self.bridge_dir)
        self.assertEqual(self.client.profile["password"], "legacy")
        self.assertNotIn("legacy", (self.bridge_dir / "connection_profile.json").read_text(encoding="utf-8"))


def snapshot(count):
    return "RECEIVED_SNAPSHOT " + ",".join(str(101000000 + i) for i in range(count))


def connect_block(session, items, extra=()):
    """One connect block as the client writes it, with a snapshot after every item (a long session) and the lines around them."""
    lines = [f"STATUS CONNECTED Connected as '{session}'", "CONNECTED", f"SESSION_SYNC {session}", "SESSION_BASELINE Beat FNAF 1 - Night 1",
             "CONFIRMED_CHECK 5 Beat FNAF 1 - Night 1", "DEATH_LINK_MODE 1", "GATE_TABLE 5=FNAF1_NIGHT2", "APPLIED_ITEMS 0", "RECEIVED_SNAPSHOT"]
    for count in range(1, items + 1):
        lines += [f"ITEM {101000000 + count} 1 0 0 {count - 1}", "APPLIED_ITEMS 0", snapshot(count), f"STATUS CONNECTED Received item #{count}",
                  f"PRINT Check sent to server: location {count}"]
    return lines + list(extra)


def long_history():
    return (connect_block("old_a", 60) + connect_block("old_b", 60)
            + connect_block("current", 80, ["DEATHLINK Bob::fell", "CONFIRMED_CHECK 6 Beat FNAF 1 - Night 2"]))


class TestInboxCompaction(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fnafhw_compact_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bridge = BridgeIO(self.tmp / "bridge")

    def write(self, lines):
        self.bridge.inbox_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def read(self):
        return self.bridge.inbox_path.read_text(encoding="utf-8").splitlines()

    def test_it_keeps_the_last_connect_block_with_only_the_newest_snapshot(self):
        self.write(long_history())
        before = self.bridge.inbox_path.stat().st_size
        saved = self.bridge.compact_inbox()
        lines = self.read()
        self.assertGreater(saved, 50_000)  # the two old blocks and 80 whole-list snapshots; what is left is a few dozen lines
        self.assertEqual(self.bridge.inbox_path.stat().st_size, before - saved)
        self.assertEqual(lines[:2], ["CONNECTED", "SESSION_SYNC current"])  # the block still starts the way the mod looks for
        self.assertEqual([line for line in lines if line.startswith("SESSION_SYNC")], ["SESSION_SYNC current"])
        self.assertEqual([line for line in lines if line.startswith("RECEIVED_SNAPSHOT")], [snapshot(80)])
        self.assertEqual([line for line in lines if line.startswith("APPLIED_ITEMS")], ["APPLIED_ITEMS 0"])
        self.assertFalse(any(line.startswith(("STATUS", "PRINT")) for line in lines))
        for state_line in ("SESSION_BASELINE Beat FNAF 1 - Night 1", "CONFIRMED_CHECK 5 Beat FNAF 1 - Night 1", "CONFIRMED_CHECK 6 Beat FNAF 1 - Night 2",
                           "DEATH_LINK_MODE 1", "GATE_TABLE 5=FNAF1_NIGHT2", "DEATHLINK Bob::fell"):
            self.assertIn(state_line, lines)
        self.assertEqual([p.name for p in self.tmp.rglob("*.tmp")], [])

    def test_the_newest_applied_count_wins_even_after_a_reset(self):
        self.write(connect_block("s", 70) + ["APPLIED_ITEMS 9", "APPLIED_ITEMS 4 reset", snapshot(3)])
        self.bridge.compact_inbox()
        self.assertEqual([line for line in self.read() if line.startswith("APPLIED_ITEMS")], ["APPLIED_ITEMS 4 reset"])

    def test_a_small_inbox_a_file_without_a_connect_block_and_a_missing_file_are_left_alone(self):
        self.write(connect_block("s", 3))
        before = self.bridge.inbox_path.read_text(encoding="utf-8")
        self.assertEqual(self.bridge.compact_inbox(), 0)
        self.assertEqual(self.bridge.inbox_path.read_text(encoding="utf-8"), before)
        self.write([f"STATUS DISCONNECTED line {i}" * 20 for i in range(100)])  # big, but no SESSION_SYNC: not ours to judge
        self.assertEqual(self.bridge.compact_inbox(), 0)
        self.bridge.inbox_path.unlink()
        self.assertEqual(self.bridge.compact_inbox(), 0)

    def test_starting_a_client_core_compacts_the_inbox(self):
        from ap_client.bridge_core import BridgeCore

        self.write(long_history())
        before = self.bridge.inbox_path.stat().st_size
        BridgeCore(self.tmp / "bridge", bridge=self.bridge)
        self.assertLess(self.bridge.inbox_path.stat().st_size, before // 10)


class TestDebugCommandsAreOptIn(LuaCase):
    """Commands that change the room or the game exist only with enable_debug_commands; the status commands never go away."""

    # module file -> (commands that need the flag, commands that are always there)
    MODULES = {
        "level_gate.lua": (("ap_gate_grant", "ap_gate_revoke"), ("ap_gate_status",)),
        "death_link.lua": (("ap_dl_kill", "ap_dl_call", "ap_dl_unhook", "ap_dl_rehook"), ("ap_dl_status",)),
        "faz_tokens.lua": (("ap_coin_force",), ("ap_coin_status",)),
        "derived_counters.lua": (("ap_counter_force",), ("ap_counter_status",)),
    }

    def commands_after_init(self, filename, **params):
        self.lua.execute("__cmds = {}")
        self.load(filename).init(self.lua.table(loop_async=lambda ms, fn: None, every=lambda *a: None, now=lambda: 0, **params))
        cmds = self.lua.globals()["__cmds"]
        return {name for name in sum((tuple(group) for group in self.MODULES[filename]), ()) if cmds[name] is not None}

    def test_without_the_flag_only_the_status_commands_exist(self):
        for filename, (debug, status) in self.MODULES.items():
            self.assertEqual(self.commands_after_init(filename, debug_commands=False), set(status), filename)

    def test_with_the_flag_every_command_exists(self):
        for filename, (debug, status) in self.MODULES.items():
            self.assertEqual(self.commands_after_init(filename, debug_commands=True), set(debug) | set(status), filename)

    def test_a_module_started_without_the_parameter_keeps_its_commands(self):
        for filename, (debug, status) in self.MODULES.items():
            self.assertEqual(self.commands_after_init(filename), set(debug) | set(status), filename)

    def test_main_registers_the_goal_key_and_the_check_commands_only_with_the_flag(self):
        source = (LIB.parent / "main.lua").read_text(encoding="utf-8")
        self.assertIn('local debug_commands = user_config.enable_debug_commands == true', source)
        lines = source.splitlines()

        def line_before(needle):
            index = next(i for i, line in enumerate(lines) if needle in line)
            return lines[index - 1].strip()

        self.assertEqual(line_before('RegisterConsoleCommandHandler("ap_check_name"'), "if debug_commands then")
        self.assertEqual(line_before('RegisterConsoleCommandHandler("ap_goal"'), "if debug_commands then")
        # ap_check_id sits in the same block as ap_check_name, before the always-on status commands
        self.assertLess(source.index('"ap_check_name"'), source.index('"ap_check_id"'))
        self.assertLess(source.index('"ap_check_id"'), source.index('"ap_items_status"'))
        self.assertIn("if debug_commands and RegisterKeyBind and Key then\n    RegisterKeyBind(Key.F7", source.replace("\r\n", "\n"))
        for module in ("level_gate", "death_link", "faz_tokens", "derived_counters"):
            self.assertRegex(source, rf"{module}\.lua\"\)\.init\(\{{[^}}]*debug_commands = debug_commands", module)


class TestAStuckItemDoesNotHoldBackTheOthers(LuaCase):
    def setUp(self):
        super().setUp()
        self.module = self.load("item_sync.lua")
        self.clock = {"t": 1000}
        self.applied, self.acks = [], []
        self.broken = {1}  # indexes whose effect can never be applied

        def apply(item_id, index):
            self.applied.append(index)
            return index not in self.broken

        self.sync = self.module.init(self.lua.table(apply=apply, ack=lambda count: self.acks.append(count), now=lambda: self.clock["t"]))
        self.sync.on_session_sync("seed_slot")
        self.sync.on_snapshot("101,102,103,104")

    def at(self, seconds):
        self.clock["t"] = 1000 + seconds
        self.sync.tick()

    def test_it_is_retried_and_blocks_the_rest_until_the_limit(self):
        self.at(0)
        self.assertEqual(self.applied, [0, 1])  # index 2 and 3 are not tried while 1 is stuck
        self.assertEqual(self.acks, [1])
        self.at(self.module.GIVE_UP_SECONDS - 1)
        self.assertEqual(self.acks, [1])  # still waiting
        self.assertEqual(tuple(self.sync.status())[1], 1)

    def test_after_the_limit_it_is_given_up_loudly_and_the_items_behind_it_go_through(self):
        self.at(0)
        self.at(self.module.GIVE_UP_SECONDS)
        self.assertEqual(self.applied[-3:], [1, 2, 3])
        self.assertEqual(self.acks, [1, 4])  # acknowledged up to the end: the client will not offer them again
        self.assertEqual(tuple(self.sync.status())[1], 4)
        self.assertTrue(any(line.startswith("[ERROR] [GAME] Item 102 (index 1) could not be applied") for line in self.log()))

    def test_an_item_that_works_again_in_time_is_applied_and_the_timer_starts_over(self):
        self.at(0)
        self.at(200)
        self.broken = set()
        self.at(201)  # applied after all: no give-up
        self.assertEqual(self.acks[-1], 4)
        self.assertFalse(any("giving it up" in line for line in self.log()))

    def test_the_timer_is_per_item_not_cumulative(self):
        self.broken = {0, 1}
        self.sync.on_snapshot("101,102")
        self.at(0)
        self.at(self.module.GIVE_UP_SECONDS)  # item 0 given up, item 1 only starts failing now
        self.assertEqual(tuple(self.sync.status())[1], 1)
        self.at(self.module.GIVE_UP_SECONDS + 10)
        self.assertEqual(tuple(self.sync.status())[1], 1)  # not yet: its own 300 s have not passed
        self.at(2 * self.module.GIVE_UP_SECONDS)
        self.assertEqual(tuple(self.sync.status())[1], 2)


class TestDeathLinkHookComesBack(LuaCase):
    def setUp(self):
        super().setUp()
        self.module = self.load("death_link.lua")
        self.lua.execute("__now = function() return 1000 end")
        self.jobs, self.delayed = [], []
        self.instance = self.module.init(self.lua.table(
            send=lambda cause: None, now=self.lua.globals()["__now"], current_map=lambda: "NightGuard_Office01",
            on_game_thread=lambda fn: self.jobs.append(fn), later=lambda ms, fn: self.delayed.append(fn)))
        self.lua.globals()["__loops"][1]()
        self.instance.set_mode("1")
        self.assertEqual(len(list(self.hooks().keys())), 1)

    def kill_and_fail_to_rehook(self, failures):
        self.lua.execute(f"""
            __fail = {failures}
            RegisterHook = function(path, cb)
                if __fail > 0 then __fail = __fail - 1; error("hook table busy") end
                __hooks[path] = cb
                return 11, 12
            end
        """)
        self.instance.on_incoming("Bob::fell")
        for job in self.jobs:
            job()
        self.assertEqual(list(self.hooks().keys()), [])

    def run_delayed(self):
        ran = 0
        while self.delayed:
            self.delayed.pop(0)()
            ran += 1
        return ran

    def test_a_failed_attempt_is_retried_and_the_hook_comes_back(self):
        self.kill_and_fail_to_rehook(2)
        ran = self.run_delayed()
        self.assertEqual(ran, 3)  # two failures, then it worked
        self.assertEqual(len(list(self.hooks().keys())), 1)
        self.assertEqual(len([line for line in self.log() if "could not hook LevelDefeat again" in line]), 2)
        self.assertFalse(any(line.startswith("[ERROR] [DEATHLINK] could not hook") for line in self.log()))

    def test_when_it_never_works_it_stops_trying_and_says_deaths_are_not_sent(self):
        self.kill_and_fail_to_rehook(1000)
        ran = self.run_delayed()
        self.assertEqual(ran, self.module.REHOOK_ATTEMPTS)
        errors = [line for line in self.log() if line.startswith("[ERROR] [DEATHLINK] could not hook LevelDefeat again")]
        self.assertEqual(len(errors), 1)
        self.assertIn("NOT sent until the game is restarted", errors[0])

    def test_an_unhook_by_the_user_in_between_is_respected(self):
        self.kill_and_fail_to_rehook(0)
        self.instance.state().user_unhooked = True
        self.run_delayed()
        self.assertEqual(list(self.hooks().keys()), [])  # it stays off, and no error is reported for it
        self.assertFalse(any("could not hook" in line for line in self.log()))


class TestInboxCompactionAndTheMod(LuaCase):
    """The compacted inbox must leave the mod in the same state as the full history, and a running mod must cope with the file shrinking."""

    def run_mod(self, tmp, steps):
        seen = []

        def record(name):
            return lambda spec, *rest: seen.append((name, str(spec), *[bool(r) for r in rest]))

        env = self.lua.table(
            outbox_path=str(Path(tmp) / "ap_outbox.txt"), inbox_path=str(Path(tmp) / "ap_inbox.txt"), bridge_dir=tmp,
            emitted_location_names=self.lua.table(), on_item=lambda *a: None,
            on_session_sync=record("session"), on_gate_table=record("gate_table"), on_received_snapshot=record("snapshot"),
            on_applied_items=record("applied"), on_death_link_mode=record("dl_mode"), on_deathlink=record("deathlink"))
        bridge = self.load("bridge_io.lua")(env)
        for step in steps:
            step()
            bridge.poll_inbox()
        return seen

    @staticmethod
    def final_state(seen):
        state = {}
        for entry in seen:
            state[entry[0]] = entry[1]
        return state

    def test_the_mod_ends_in_the_same_state_with_the_compacted_file(self):
        results = {}
        for name in ("full", "compacted"):
            with tempfile.TemporaryDirectory() as tmp:
                bridge = BridgeIO(Path(tmp))
                bridge.inbox_path.write_text("\n".join(long_history()) + "\n", encoding="utf-8")
                if name == "compacted":
                    bridge.compact_inbox()
                results[name] = self.run_mod(tmp, [lambda: None])
        self.assertEqual(self.final_state(results["full"]), self.final_state(results["compacted"]))
        self.assertLess(len(results["compacted"]), len(results["full"]))  # and it had less to do to get there

    def test_a_running_mod_reads_a_compacted_file_again_as_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = BridgeIO(Path(tmp))

            def append_death():
                with bridge.inbox_path.open("a", encoding="utf-8") as handle:
                    handle.write("DEATHLINK Eve::new death\n")

            seen = self.run_mod(tmp, [
                lambda: bridge.inbox_path.write_text("\n".join(long_history()) + "\n", encoding="utf-8"),  # the game starts: replay
                lambda: None,                                                                                # nothing new
                bridge.compact_inbox,                                                                        # a client starts and compacts
                append_death,                                                                                # then a death arrives
            ])
        self.assertEqual(len([entry for entry in seen if entry[0] == "session"]), 2)  # once at launch, once after the compaction
        deaths = [entry for entry in seen if entry[0] == "deathlink"]
        self.assertEqual(deaths, [("deathlink", "Bob::fell", True),     # at launch: history, never applied
                                  ("deathlink", "Bob::fell", True),     # read again after the compaction: still history
                                  ("deathlink", "Eve::new death", False)])  # one that arrives afterwards is news


class TestReconnectAfterALostSession(ClientCase):
    """A session that had started and is then lost (server restart, network gone) is picked up again; nothing else is retried."""

    def script_attempts(self, outcomes):
        """`_session_once` answers `outcomes` in turn (True: the room accepted us) and asks to stop after the last. Returns (calls, waits)."""
        calls, waits = [], []

        async def once():
            calls.append(1)
            if len(calls) >= len(outcomes):
                self.client.disconnect_requested = True  # the user presses Disconnect after the last scripted attempt
            return outcomes[len(calls) - 1]

        async def wait(seconds):
            waits.append(seconds)

        self.client._session_once = once
        self.client._wait_to_retry = wait
        return calls, waits

    async def test_a_lost_session_is_retried_with_growing_waits(self):
        calls, waits = self.script_attempts([True, False, False, False, False])
        await self.client._session_loop()
        self.assertEqual(len(calls), 5)
        self.assertEqual(waits, [2, 5, 10, 30])  # the last attempt ends with Disconnect: no wait after it

    async def test_the_wait_stops_growing_at_a_minute(self):
        calls, waits = self.script_attempts([True] + [False] * 7 + [False])
        await self.client._session_loop()
        self.assertEqual(waits, [2, 5, 10, 30, 60, 60, 60, 60])

    async def test_a_session_that_comes_back_starts_the_waits_over(self):
        calls, waits = self.script_attempts([True, False, False, True, False, False])
        await self.client._session_loop()
        self.assertEqual(waits, [2, 5, 10, 2, 5])

    async def test_a_connection_that_never_started_a_session_is_not_retried(self):
        calls, waits = self.script_attempts([False, False, False])
        await self.client._session_loop()
        self.assertEqual((len(calls), waits), (1, []))  # a wrong host, slot or password fails the same way again: say so once

    async def test_a_refusal_or_a_disconnect_is_not_retried(self):
        async def accepted_then_refused():
            self.client.disconnect_requested = True  # what ConnectionRefused, a failed start and the Disconnect command all set
            return True

        waited = []

        async def wait(seconds):
            waited.append(seconds)

        self.client._session_once = accepted_then_refused
        self.client._wait_to_retry = wait
        await self.client._session_loop()
        self.assertEqual(waited, [])

    async def test_the_game_is_told_what_is_happening(self):
        self.script_attempts([True, False])
        await self.client._session_loop()
        self.assertIn("Reconnecting in 2 s", self.client.last_message)
        self.assertEqual(self.client.status, standalone.STATUS_CONNECTING)  # the window's button then reads "Disconnect"

    async def test_a_disconnect_ends_the_wait_within_a_second(self):
        self.client.disconnect_requested = False
        loop = asyncio.get_running_loop()
        loop.call_later(0.2, setattr, self.client, "disconnect_requested", True)
        started = loop.time()
        await self.client._wait_to_retry(60)
        self.assertLess(loop.time() - started, 1.5)

    async def test_the_wait_takes_the_time_asked(self):
        loop = asyncio.get_running_loop()
        started = loop.time()
        await self.client._wait_to_retry(0.3)
        self.assertGreaterEqual(loop.time() - started, 0.25)

    async def test_with_a_real_server_that_drops_the_first_session(self):
        sessions = []

        async def room(connection):
            sessions.append(connection)
            await connection.send(json.dumps([{"cmd": "RoomInfo", "seed_name": "SeedReconnect"}]))
            async for raw in connection:
                for packet in json.loads(raw):
                    if packet.get("cmd") == "Connect":
                        await connection.send(json.dumps([{"cmd": "Connected", "slot": 1, "team": 0, "checked_locations": [], "slot_data": {}}]))
                        if len(sessions) == 1:
                            await connection.close()  # the server restarts: the first session is lost
                            return

        async with standalone.websockets.serve(room, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            self.client.profile.update(server_host="127.0.0.1", server_port=port, server_scheme="ws", slot="P1")
            self.client.slot = "P1"
            with mock.patch.object(standalone, "RECONNECT_DELAYS_SECONDS", (0.05,)):
                task = asyncio.create_task(self.client._session_loop())
                try:
                    async with asyncio.timeout(15):
                        while not (len(sessions) == 2 and self.client.status == standalone.STATUS_CONNECTED):
                            await asyncio.sleep(0.05)
                finally:
                    self.client.disconnect_requested = True
                    await asyncio.wait_for(task, 5)
        self.assertEqual(len(sessions), 2)  # it joined, was dropped, and joined again by itself

    async def test_the_sends_after_connecting_are_held_until_they_end(self):
        sent = []

        async def send(packet):
            sent.append(packet)

        self.client._send_packet = send
        with mock.patch.object(self.client, "on_connected", return_value=[{"cmd": "Sync"}, {"cmd": "LocationChecks", "locations": []}]):
            self.client._on_connected({})
        self.assertEqual(len(self.client._send_tasks), 2)
        await asyncio.wait(list(self.client._send_tasks))
        await asyncio.sleep(0)
        self.assertEqual(self.client._send_tasks, set())
        self.assertEqual([packet["cmd"] for packet in sent], ["Sync", "LocationChecks"])

    async def test_a_failed_send_after_connecting_is_reported_not_lost(self):
        async def broken(packet):
            raise ConnectionError("socket closed")

        self.client._send_packet = broken
        with mock.patch.object(self.client, "on_connected", return_value=[{"cmd": "Sync"}]), mock.patch("builtins.print") as printed:
            self.client._on_connected({})
            await asyncio.wait(list(self.client._send_tasks))
            await asyncio.sleep(0)
        self.assertTrue(any("socket closed" in str(call) for call in printed.call_args_list))
        self.assertEqual(self.client._send_tasks, set())


class TestGeneratedLuaStrings(unittest.TestCase):
    """json.dumps writes \\uXXXX for non-ASCII characters, which Lua cannot read: the generator has its own string writer."""

    @classmethod
    def setUpClass(cls):
        import importlib.util

        spec = importlib.util.spec_from_file_location("generate_locations_lua", ROOT / "scripts" / "generate_locations_lua.py")
        cls.generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.generator)  # only defines functions: nothing is written on import

    def test_plain_text(self):
        self.assertEqual(self.generator.lua_string("Collect Faz Token 01"), '"Collect Faz Token 01"')

    def test_quotes_and_backslashes_are_escaped(self):
        self.assertEqual(self.generator.lua_string('a "b" \\ c'), '"a \\"b\\" \\\\ c"')

    def test_non_ascii_stays_as_utf8_and_never_becomes_a_json_escape(self):
        text = self.generator.lua_string("Café 日本")
        self.assertEqual(text, '"Café 日本"')
        self.assertNotIn("\\u", text)

    def test_control_characters_become_decimal_escapes(self):
        self.assertEqual(self.generator.lua_string("a\tb\nc\x7f"), '"a\\009b\\010c\\127"')

    @unittest.skipIf(LuaRuntime is None, "lupa is not installed")
    def test_what_it_writes_reads_back_as_the_same_string_in_lua(self):
        for text in ("plain", 'say "hi"', "back\\slash", "Café 日本", "tab\there", "line\nbreak"):
            literal = self.generator.lua_string(text)
            self.assertEqual(LuaRuntime().eval(literal), text)

    def test_the_committed_lua_file_is_exactly_what_the_generator_writes(self):
        data = json.loads((ROOT / "ue4ss_mod" / "FNAFHWArchipelago" / "locations.json").read_text(encoding="utf-8"))
        committed = (ROOT / "ue4ss_mod" / "FNAFHWArchipelago" / "Scripts" / "lib" / "locations_data.lua").read_bytes()
        self.assertEqual(committed.replace(b"\r\n", b"\n"), self.generator.render(data).encode("utf-8"))


class TestTheActivityLogStaysBounded(unittest.TestCase):
    def make_gui(self):
        import tkinter

        try:
            root = tkinter.Tk()
        except tkinter.TclError as exc:
            self.skipTest(f"no display for Tk: {exc}")
        root.withdraw()
        self.addCleanup(root.destroy)
        gui = standalone.DesktopGUI.__new__(standalone.DesktopGUI)
        gui.root = root
        gui.log_box = tkinter.Text(root)
        return gui

    def test_only_the_newest_lines_are_kept(self):
        gui = self.make_gui()
        limit = standalone.GUI_LOG_MAX_LINES
        for number in range(limit + 50):
            gui.log(f"line {number}")
        gui.root.update()
        lines = gui.log_box.get("1.0", "end-1c").splitlines()
        self.assertEqual(len(lines), limit)
        self.assertTrue(lines[-1].endswith("line %d" % (limit + 49)))
        self.assertTrue(lines[0].endswith("line 50"))

    def test_a_log_before_the_cap_is_untouched(self):
        gui = self.make_gui()
        for number in range(5):
            gui.log(f"line {number}")
        gui.root.update()
        self.assertEqual(len(gui.log_box.get("1.0", "end-1c").splitlines()), 5)

    def test_a_window_that_is_going_away_does_not_break_the_client_thread(self):
        gui = standalone.DesktopGUI.__new__(standalone.DesktopGUI)
        gui.root = mock.Mock()
        gui.root.after.side_effect = RuntimeError("main thread is not in main loop")
        gui.log("late line")  # must not raise
        gui._post(lambda: None)  # nor this


@unittest.skipUnless(sys.platform == "win32", "build-apworld.ps1 is a Windows PowerShell script")
class TestBuildCleansUpAfterItself(unittest.TestCase):
    def run_build(self, vendored):
        tmp = Path(tempfile.mkdtemp(prefix="fnafhw_build_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        scripts = tmp / "repo" / "scripts"
        scripts.mkdir(parents=True)
        for name in ("build-apworld.ps1", "zip-helpers.ps1"):
            shutil.copy(ROOT / "scripts" / name, scripts / name)
        (scripts / "vendored_client_files.json").write_text(json.dumps(vendored), encoding="utf-8")
        (tmp / "repo" / "fnaf_help_wanted").mkdir()
        (tmp / "repo" / "fnaf_help_wanted" / "__init__.py").write_text("", encoding="utf-8")
        (tmp / "repo" / "ap_client").mkdir()
        (tmp / "repo" / "ap_client" / "present.py").write_text("x = 1\n", encoding="utf-8")
        scratch = tmp / "temp"
        scratch.mkdir()
        env = dict(os.environ, TEMP=str(scratch), TMP=str(scratch))
        result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(scripts / "build-apworld.ps1")],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        return result, scratch, tmp / "repo" / "dist"

    def test_a_failed_build_leaves_no_temp_folder(self):
        result, scratch, _ = self.run_build([{"source": "ap_client/missing.py", "target": "missing.py"}])
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Missing vendored client file", result.stderr + result.stdout)
        self.assertEqual(list(scratch.iterdir()), [])

    def test_a_good_build_leaves_none_either_and_makes_the_apworld(self):
        result, scratch, dist = self.run_build([{"source": "ap_client/present.py", "target": "present.py"}])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(list(scratch.iterdir()), [])
        self.assertTrue((dist / "fnaf_help_wanted.apworld").is_file())


if __name__ == "__main__":
    unittest.main()
