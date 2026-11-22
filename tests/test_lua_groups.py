"""The mod side of the group toggles, run in a real Lua interpreter (lupa).

`RANDOMIZED_GROUPS prizes=0|1 faz_tokens=0|1 tapes=0|1` (written by the client in every connect block) tells the mod which groups are randomized.
A group that is NOT randomized is vanilla in game: the tape room and the TV show what the save really holds, not the item counts.
The default (no line, a key missing, a value that is not 0 or 1) is "randomized": exactly the behaviour of the versions before the toggles.
"""

import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tests.test_lua_logic import LIB, LuaCase

TAPE_ITEM = 101000061  # "Glitch Tape #01 (Intro)"; the n-th tape item is TAPE_ITEM + n - 1
TOKEN_ITEM = 101000011
GETTER = "/Game/ProductionAssets/Blueprints/Data/SaveGame/FNAFSaveGame.FNAFSaveGame_C:GetGlitchCount"
TOTAL_COINS = "/Game/ProductionAssets/Blueprints/Data/SaveGame/FNAFSaveGame.FNAFSaveGame_C:GetTotalCoinCount"
COIN_COUNT = "/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:GetCoinCount"


class RetHelper(LuaCase):
    def setUp(self):
        super().setUp()
        self.lua.execute("""
            __ret = function(value)
                local r = {v = value}
                function r:get() return self.v end
                function r:set(x) self.v = x end
                return r
            end
        """)

    def ret(self, vanilla):
        return self.lua.globals()["__ret"](vanilla)


class TestInboxLine(LuaCase):
    def bridge(self, tmp, **handlers):
        env = self.lua.table(
            outbox_path=str(Path(tmp) / "ap_outbox.txt"), inbox_path=str(Path(tmp) / "ap_inbox.txt"), bridge_dir=tmp,
            emitted_location_names=self.lua.table(), on_item=lambda *a: None)
        for key, value in handlers.items():
            env[key] = value
        return self.load("bridge_io.lua")(env)

    def deliver(self, text, **handlers):
        seen = []

        def on_groups(groups):
            seen.append({key: bool(groups[key]) for key in ("prizes", "faz_tokens", "tapes")})

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ap_inbox.txt").write_text(text, encoding="utf-8")
            self.bridge(tmp, on_randomized_groups=on_groups, **handlers).poll_inbox()
        return seen

    def test_the_line_reaches_its_handler_with_one_boolean_per_group(self):
        self.assertEqual(self.deliver("RANDOMIZED_GROUPS prizes=0 faz_tokens=1 tapes=0\n"),
                         [{"prizes": False, "faz_tokens": True, "tapes": False}])
        self.assertEqual(self.deliver("RANDOMIZED_GROUPS prizes=1 faz_tokens=0 tapes=1\n"),
                         [{"prizes": True, "faz_tokens": False, "tapes": True}])

    def test_a_missing_or_unreadable_key_means_randomized(self):
        self.assertEqual(self.deliver("RANDOMIZED_GROUPS tapes=0\n"), [{"prizes": True, "faz_tokens": True, "tapes": False}])
        self.assertEqual(self.deliver("RANDOMIZED_GROUPS prizes=maybe faz_tokens= tapes=2\n"),
                         [{"prizes": True, "faz_tokens": True, "tapes": True}])
        self.assertEqual(self.deliver("RANDOMIZED_GROUPS\n"), [{"prizes": True, "faz_tokens": True, "tapes": True}])

    def test_the_line_does_not_disturb_its_neighbours(self):
        calls = []
        seen = self.deliver(
            "DEATH_LINK_GIFT_BOX 0\nRANDOMIZED_GROUPS tapes=0\nGATE_TABLE 4=FNAF1\nDEATHLINK Bob::fell\n",
            on_death_link_gift_box=lambda spec: calls.append(("gift", str(spec))),
            on_gate_table=lambda spec: calls.append(("gate", str(spec))),
            on_deathlink=lambda spec, replay: calls.append(("death", str(spec))))
        self.assertEqual(len(seen), 1)
        self.assertEqual(calls, [("gift", "0"), ("gate", "4=FNAF1"), ("death", "Bob::fell")])

    def test_an_old_mod_style_environment_without_a_handler_ignores_the_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ap_inbox.txt").write_text("RANDOMIZED_GROUPS tapes=0\n", encoding="utf-8")
            self.bridge(tmp).poll_inbox()  # must not raise

    def test_only_the_last_connect_block_of_the_history_counts_at_launch(self):
        seen = self.deliver(
            "CONNECTED\nSESSION_SYNC old\nRANDOMIZED_GROUPS tapes=0\n"
            "CONNECTED\nSESSION_SYNC new\nRANDOMIZED_GROUPS tapes=1 faz_tokens=0\n")
        self.assertEqual(seen, [{"prizes": True, "faz_tokens": False, "tapes": True}])

    def test_main_lua_wires_the_line_to_both_counters(self):
        main = (LIB.parent / "main.lua").read_text(encoding="utf-8")
        self.assertIn("on_randomized_groups", main)
        self.assertIn("derived_counters.set_randomized", main)
        self.assertIn("tape_shelf.set_randomized", main)
        self.assertIn("faz_tokens.set_randomized", main)


class TestTapeCountIsVanillaWhenTapesAreNotRandomized(RetHelper):
    def setUp(self):
        super().setUp()
        self.module = self.load("derived_counters.lua")
        self.instance = self.module.init()
        self.lua.globals()["__loops"][1]()
        self.hook = self.hooks()[GETTER]

    def start(self, tapes=2):
        self.instance.on_session_sync("seed_slot")
        self.instance.on_snapshot(",".join(str(TAPE_ITEM + n) for n in range(tapes)))

    def test_randomized_is_the_default_and_follows_the_items(self):
        self.start(2)
        self.assertEqual(self.hook(None), 2)

    def test_not_randomized_leaves_the_games_own_count_alone(self):
        self.start(2)
        self.instance.set_randomized("tapes", False)
        self.assertIsNone(self.hook(None))  # nothing returned: the save's real tapes stand
        ret = self.ret(5)
        self.assertIsNone(self.hook(None, ret))
        self.assertEqual(ret.v, 5)

    def test_not_randomized_even_when_no_item_ever_arrives(self):
        self.instance.on_session_sync("seed_slot")
        self.instance.on_snapshot("")  # a seed without Glitch Tape items: the list has none
        self.assertEqual(self.hook(None), 0)  # still randomized: 0 items = 0 tapes (old behaviour)
        self.instance.set_randomized("tapes", False)
        self.assertIsNone(self.hook(None))

    def test_it_can_be_switched_back_and_the_debug_override_still_wins(self):
        self.start(2)
        self.instance.set_randomized("tapes", False)
        self.instance.set_randomized("tapes", True)
        self.assertEqual(self.hook(None), 2)
        self.instance.set_randomized("tapes", False)
        self.instance.force("tapes", 7)
        self.assertEqual(self.hook(None), 7)

    def test_unknown_counters_are_ignored_and_the_status_shows_the_mode(self):
        self.start(1)
        self.assertFalse(self.instance.set_randomized("nope", False))
        self.instance.set_randomized("tapes", False)
        self.assertIn("randomized=false", str(self.instance.status()))
        self.assertIn("effective=nil", str(self.instance.status()))

    def test_a_new_session_starts_randomized_again(self):
        """SESSION_SYNC comes before RANDOMIZED_GROUPS in every connect block, so the line always has the last word."""
        self.start(2)
        self.instance.set_randomized("tapes", False)
        self.instance.on_session_sync("another_seed_slot")
        self.instance.on_snapshot(str(TAPE_ITEM))
        self.assertEqual(self.hook(None), 1)


class TestTokenCountIsVanillaWhenTokensAreNotRandomized(RetHelper):
    def setUp(self):
        super().setUp()
        self.lua.execute("__gi = {PlayerCoins = 3}")
        self.module = self.load("faz_tokens.lua")
        self.instance = self.module.init(self.lua.table(game_instance=self.lua.eval("function() return __gi end")))
        self.lua.globals()["__loops"][1]()  # registers the three hooks

    def start(self, tokens=5):
        self.instance.on_session_sync("seed_slot")
        self.instance.on_snapshot(",".join([str(TOKEN_ITEM)] * tokens))

    def count(self, vanilla):
        ret = self.ret(vanilla)
        self.hooks()[TOTAL_COINS](None, ret)
        return ret.v

    def test_randomized_is_the_default_and_follows_the_items(self):
        self.start(5)
        self.assertEqual(self.count(2), 5)
        self.assertEqual(self.lua.globals()["__gi"].PlayerCoins, 5)

    def test_not_randomized_gives_the_game_its_own_count_and_cache_back(self):
        self.start(5)
        self.instance.set_randomized(False)
        self.assertEqual(self.count(2), 2)  # the TV shows the coins really picked up
        ret = self.ret(9)
        self.hooks()[COIN_COUNT](None, ret)
        self.assertEqual(ret.v, 9)
        self.assertEqual(self.lua.globals()["__gi"].PlayerCoins, 3)  # the cache the game had before we wrote it

    def test_not_randomized_stays_hands_off_when_items_arrive_later(self):
        self.start(0)
        self.instance.set_randomized(False)
        self.instance.on_snapshot(",".join([str(TOKEN_ITEM)] * 40))  # filler Faz Tokens still arrive: they do nothing
        self.assertEqual(self.count(2), 2)
        self.assertEqual(self.lua.globals()["__gi"].PlayerCoins, 3)

    def test_it_can_be_switched_back(self):
        self.start(5)
        self.instance.set_randomized(False)
        self.instance.set_randomized(True)
        self.assertEqual(self.count(2), 5)

    def test_the_debug_override_still_wins(self):
        self.start(5)
        self.instance.set_randomized(False)
        self.instance.force(11)
        self.assertEqual(self.count(2), 11)

    def test_a_new_session_starts_randomized_again(self):
        self.start(5)
        self.instance.set_randomized(False)
        self.instance.on_session_sync("another_seed_slot")
        self.instance.on_snapshot(",".join([str(TOKEN_ITEM)] * 4))
        self.assertEqual(self.count(2), 4)

    def test_the_status_shows_the_mode(self):
        self.start(1)
        self.instance.set_randomized(False)
        self.assertIn("randomized=false", str(self.instance.status()))


class TestConnectionPanelTotal(LuaCase):
    def test_the_panel_reads_the_real_total_and_keeps_146_without_one(self):
        source = (LIB / "connection_ui.lua").read_text(encoding="utf-8")
        self.assertIn('"total_count"', source)
        self.assertNotIn("%d / 146", source)  # no hard-coded total in the drawing code any more
        module = self.load("connection_ui.lua")
        with tempfile.TemporaryDirectory() as tmp:
            ui = module.init(self.lua.table(bridge_dir=tmp, APBridge=self.lua.table(), mod_dir=tmp))
            self.assertIn("/ 146", str(module.counter_text()))  # nothing written yet: the default (every group on)
            (Path(tmp) / "connection_state.json").write_text(
                '{"status": "CONNECTED", "checked_count": 4, "received_count": 7, "total_count": 50}', encoding="utf-8")
            module.update_state()
            self.assertIn("4 / 50", str(module.counter_text()))
            self.assertIn("Items Received: 7", str(module.counter_text()))
            (Path(tmp) / "connection_state.json").write_text(
                '{"status": "CONNECTED", "checked_count": 5, "received_count": 7}', encoding="utf-8")
            module.update_state()
            self.assertIn("5 / 50", str(module.counter_text()))  # a status file without the key keeps the last known total


COUNT_FORMATS = """
    __formats = 0
    local real_format = string.format
    string.format = function(...) __formats = __formats + 1 return real_format(...) end
"""


class TestPollingHooksDoNotRebuildTheirLogLine(RetHelper):
    """The game's UI calls these hooks constantly. Each distinct outcome is logged once; the line must not be built again on every call."""

    def formats(self):
        return self.lua.globals()["__formats"]

    def observed_lines(self):
        return [line for line in self.log() if "observed" in str(line)]

    def test_the_tape_count_hook(self):
        module = self.load("derived_counters.lua")
        instance = module.init()
        self.lua.globals()["__loops"][1]()
        instance.on_session_sync("seed_slot")
        instance.on_snapshot(",".join(str(TAPE_ITEM + n) for n in range(2)))
        hook = self.hooks()[GETTER]
        self.lua.execute(COUNT_FORMATS)
        self.assertEqual(hook(None), 2)
        built_for_first_call = self.formats()
        self.assertEqual(built_for_first_call, 1)
        for _ in range(200):
            self.assertEqual(hook(None), 2)
        self.assertEqual(self.formats(), built_for_first_call)  # nothing built again for the same outcome
        self.assertEqual(len(self.observed_lines()), 1)
        instance.on_snapshot(",".join(str(TAPE_ITEM + n) for n in range(3)))  # a new outcome is logged again
        self.assertEqual(hook(None), 3)
        self.assertEqual(len(self.observed_lines()), 2)

    def test_the_token_count_hook(self):
        self.lua.execute("__gi = {PlayerCoins = 3}")
        module = self.load("faz_tokens.lua")
        instance = module.init(self.lua.table(game_instance=self.lua.eval("function() return __gi end")))
        self.lua.globals()["__loops"][1]()
        instance.on_session_sync("seed_slot")
        instance.on_snapshot(",".join([str(TOKEN_ITEM)] * 5))
        hook = self.hooks()[TOTAL_COINS]
        self.lua.execute(COUNT_FORMATS)
        ret = self.lua.eval("function() local r = {v = 2} function r:get() return self.v end function r:set(x) self.v = x end return r end")()
        hook(None, ret)
        built_for_first_call = self.formats()
        self.assertGreaterEqual(built_for_first_call, 1)
        for _ in range(200):
            ret.v = 2
            hook(None, ret)
            self.assertEqual(ret.v, 5)
        self.assertEqual(self.formats(), built_for_first_call)
        self.assertEqual(len(self.observed_lines()), 1)


class TestPanelStateIsNotReadEveryFrame(LuaCase):
    def test_the_hud_refresh_is_at_most_twice_a_second(self):
        module = self.load("connection_ui.lua")
        with tempfile.TemporaryDirectory() as tmp:
            module.init(self.lua.table(bridge_dir=tmp, APBridge=self.lua.table(), mod_dir=tmp))
            state = Path(tmp) / "connection_state.json"
            state.write_text('{"status": "CONNECTING", "checked_count": 1}', encoding="utf-8")
            self.assertTrue(module.refresh_state_if_due(10.0))
            self.assertEqual(str(module.status), "CONNECTING")
            state.write_text('{"status": "CONNECTED", "checked_count": 2}', encoding="utf-8")
            for frame in range(1, 30):  # a frame every 16 ms
                self.assertFalse(module.refresh_state_if_due(10.0 + frame * 0.016))
            self.assertEqual(str(module.status), "CONNECTING")  # not read again yet
            self.assertTrue(module.refresh_state_if_due(10.51))
            self.assertEqual(str(module.status), "CONNECTED")
            self.assertEqual(module.checked_count, 2)

    def test_a_missing_state_file_is_fine(self):
        module = self.load("connection_ui.lua")
        with tempfile.TemporaryDirectory() as tmp:
            module.init(self.lua.table(bridge_dir=tmp, APBridge=self.lua.table(), mod_dir=tmp))
            module.update_state()  # no connection_state.json yet: nothing changes, nothing raises
            self.assertEqual(str(module.status), "DISCONNECTED")

    def test_the_hud_hook_draws_every_row_and_never_the_password(self):
        module = self.load("connection_ui.lua")
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "connection_secret.dat").write_text("plain:c2VjcmV0", encoding="utf-8")
            module.init(self.lua.table(bridge_dir=tmp, APBridge=self.lua.table(), mod_dir=tmp))
            self.lua.execute("""
                __drawn = {}
                __canvas = {}
                function __canvas:IsValid() return true end
                function __canvas:K2_DrawText(font, text) __drawn[#__drawn + 1] = text end
                __hud = { Canvas = __canvas }
            """)
            hook = self.hooks()["/Script/Engine.HUD:ReceiveDrawHUD"]
            hook(self.lua.globals()["__hud"], 1920, 1080)
            self.assertEqual(len(self.lua.globals()["__drawn"]), 0)  # the panel is closed: nothing is drawn
            module.is_visible = True
            hook(self.lua.globals()["__hud"], 1920, 1080)  # must not raise
            drawn = [str(self.lua.globals()["__drawn"][i]) for i in range(1, len(self.lua.globals()["__drawn"]) + 1)]
            self.assertTrue(any("4. Password" in line and "(saved)" in line for line in drawn), drawn)
            self.assertFalse(any("secret" in line.lower() and "Password" in line for line in drawn))
            self.assertTrue(any("Locations Checked" in line for line in drawn))

    def test_the_hud_hook_uses_the_throttled_refresh(self):
        source = (LIB / "connection_ui.lua").read_text(encoding="utf-8")
        hook_body = source.split('"/Script/Engine.HUD:ReceiveDrawHUD"', 1)[1]
        self.assertIn("refresh_state_if_due(os.clock())", hook_body)
        self.assertNotIn("ConnectionUI.update_state()", hook_body)


if __name__ == "__main__":
    unittest.main()
