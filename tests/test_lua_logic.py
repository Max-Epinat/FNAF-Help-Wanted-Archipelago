"""The mod's Lua logic, run for real in a Lua interpreter (lupa) with the game's functions stubbed.

Covers the pure decisions of death_link.lua (including the registered hook and the console experiment commands), level_gate.lua and
item_sync.lua. What it cannot cover is the game itself: whether a hook fires, what a game function does. Those stay in-game checks.
Skipped when lupa is not installed (pip install lupa).
"""

import unittest
from pathlib import Path

try:
    from lupa import LuaRuntime
except ImportError:  # pragma: no cover
    LuaRuntime = None

project_root = Path(__file__).resolve().parent.parent
LIB = project_root / "ue4ss_mod" / "FNAFHWArchipelago" / "Scripts" / "lib"

PRELUDE = """
__log = {}
print = function(...)
    local parts = {}
    for i = 1, select('#', ...) do parts[#parts + 1] = tostring((select(i, ...))) end
    __log[#__log + 1] = table.concat(parts, " ")
end
__hooks, __loops, __cmds, __unhooked = {}, {}, {}, {}
RegisterHook = function(path, cb) __hooks[path] = cb; return 11, 12 end
UnregisterHook = function(path, pre, post)
    if not __hooks[path] then error("not registered: " .. path) end
    __hooks[path] = nil
    __unhooked[#__unhooked + 1] = path
end
LoopAsync = function(ms, fn) __loops[#__loops + 1] = fn end
RegisterConsoleCommandHandler = function(name, fn) __cmds[name] = fn end
__calls = {}
FindFirstOf = function(class_name)
    local object = {}
    function object:IsValid() return true end
    setmetatable(object, { __index = function(_, name)
        return function(self) __calls[#__calls + 1] = name end
    end })
    return object
end
"""


@unittest.skipIf(LuaRuntime is None, "lupa is not installed")
class LuaCase(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(PRELUDE)
        self.loader = self.lua.eval("function(src, name) return load(src, '=' .. name)() end")

    def load(self, filename):
        return self.loader((LIB / filename).read_text(encoding="utf-8"), filename)

    def log(self):
        return [self.lua.globals()["__log"][i] for i in range(1, len(self.lua.globals()["__log"]) + 1)]

    def hooks(self):
        return self.lua.globals()["__hooks"]

    def calls(self):
        calls = self.lua.globals()["__calls"]
        return [calls[i] for i in range(1, len(calls) + 1)]


class TestDeathLinkPure(LuaCase):
    def setUp(self):
        super().setUp()
        self.module = self.load("death_link.lua")

    def test_parse_mode(self):
        self.assertTrue(self.module.parse_mode("1"))
        self.assertFalse(self.module.parse_mode(" 0 "))
        for bad in ("", "2", "yes", None):
            self.assertIsNone(self.module.parse_mode(bad))

    def test_parse_death(self):
        self.assertEqual(tuple(self.module.parse_death("Bob::fell into a pit")), ("Bob", "fell into a pit"))
        self.assertEqual(tuple(self.module.parse_death("Bob::")), ("Bob", "Died."))
        self.assertEqual(tuple(self.module.parse_death("::boom")), ("Someone", "boom"))
        self.assertEqual(tuple(self.module.parse_death("just a name")), ("just a name", "Died."))
        self.assertEqual(tuple(self.module.parse_death("")), ("Someone", "Died."))

    def decide(self, **state):
        base = self.lua.table(enabled=True, suppress_until=0)
        for key, value in state.items():
            base[key] = value
        send, reason = self.module.decide_send(base, 100)
        return send, str(reason)

    def test_decide_send(self):
        self.assertTrue(self.decide()[0])
        self.assertEqual(self.decide(enabled=False), (False, "DeathLink is off for this slot"))
        self.assertFalse(self.decide(suppress_until=105)[0])  # an incoming death caused this defeat
        self.assertTrue(self.decide(suppress_until=99)[0])
        self.assertFalse(self.decide(last_sent=98)[0])  # same defeat within the debounce window
        self.assertTrue(self.decide(last_sent=96)[0])


class TestDeathLinkRuntime(LuaCase):
    def setUp(self):
        super().setUp()
        self.module = self.load("death_link.lua")
        self.sent = []
        self.clock = self.lua.table(t=1000)
        self.lua.globals()["__clock"] = self.clock
        self.lua.execute("__now = function() return __clock.t end")
        self.instance = self.module.init(self.lua.table(
            send=lambda cause: self.sent.append(cause), now=self.lua.globals()["__now"]))
        # the registration loop runs once the game is ready
        self.lua.globals()["__loops"][1]()
        self.defeat = self.hooks()[
            "/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:LevelDefeat"]

    def advance(self, seconds):
        self.clock.t = self.clock.t + seconds

    def test_the_defeat_hook_is_registered_by_the_loop(self):
        self.assertIsNotNone(self.defeat)
        self.assertEqual(len(list(self.hooks().keys())), 1)  # only LevelDefeat: the other probes are gone
        self.assertIn("[DEATHLINK] watching LevelDefeat", self.log())

    def test_nothing_is_sent_while_deathlink_is_off(self):
        self.defeat(None)
        self.assertEqual(self.sent, [])
        self.assertTrue(any("DeathLink is off" in line for line in self.log()))

    def test_a_defeat_is_sent_once_with_a_cause(self):
        self.instance.set_mode("1")
        self.defeat(None)
        self.assertEqual(self.sent, ["lost a level"])

    def test_the_same_defeat_is_not_sent_twice_but_a_later_one_is(self):
        self.instance.set_mode("1")
        self.defeat(None)
        self.advance(1)
        self.defeat(None)
        self.assertEqual(len(self.sent), 1)
        self.advance(5)
        self.defeat(None)
        self.assertEqual(len(self.sent), 2)

    def test_turning_deathlink_off_stops_sending(self):
        self.instance.set_mode("1")
        self.instance.set_mode("0")
        self.defeat(None)
        self.assertEqual(self.sent, [])

    def test_a_bad_mode_value_changes_nothing(self):
        self.instance.set_mode("1")
        self.instance.set_mode("maybe")
        self.assertTrue(self.instance.is_enabled())
        self.assertTrue(any("bad value" in line for line in self.log()))

    def test_an_incoming_death_with_deathlink_off_is_ignored(self):
        self.assertFalse(self.instance.on_incoming("Bob::fell"))
        self.assertTrue(any("not applied: DeathLink is off" in line for line in self.log()))

    def test_a_failing_send_does_not_break_the_hook(self):
        failing = self.module.init(self.lua.table(send=lambda cause: (_ for _ in ()).throw(RuntimeError("bridge")),
                                                  now=self.lua.globals()["__now"]))
        failing.set_mode("1")
        self.lua.globals()["__loops"][2]()
        hook = self.hooks()["/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:LevelDefeat"]
        hook(None)  # must not raise into the game
        self.assertTrue(any("[ERROR] DeathLink defeat hook" in line for line in self.log()))


LEVEL_DEFEAT = "/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:LevelDefeat"


class TestDeathLinkReceiving(LuaCase):
    """An incoming death makes the player lose the level (v1: levels only, never history, one at a time)."""

    def setUp(self):
        super().setUp()
        self.module = self.load("death_link.lua")
        self.clock = self.lua.table(t=1000)
        self.lua.globals()["__clock"] = self.clock
        self.lua.execute("__now = function() return __clock.t end")
        self.sent = []
        self.map_name = "NightGuard_Office01"
        self.game_thread_jobs = []
        self.delayed = []
        self.instance = self.module.init(self.lua.table(
            send=lambda cause: self.sent.append(cause),
            now=self.lua.globals()["__now"],
            current_map=lambda: self.map_name,
            on_game_thread=lambda fn: self.game_thread_jobs.append(fn),
            later=lambda ms, fn: self.delayed.append((ms, fn)),
        ))
        self.lua.globals()["__loops"][1]()
        self.instance.set_mode("1")

    def run_game_thread(self):
        jobs, self.game_thread_jobs = self.game_thread_jobs, []
        for job in jobs:
            job()

    def test_a_death_in_a_level_calls_level_defeat_on_the_game_thread_only(self):
        self.assertTrue(self.instance.on_incoming("Bob::fell"))
        self.assertEqual(self.calls(), [])  # nothing runs on the caller's thread
        self.run_game_thread()
        self.assertEqual(self.calls(), ["LevelDefeat"])
        self.assertEqual(self.instance.state().applied, 1)

    def test_the_hook_is_removed_for_the_call_and_comes_back_later(self):
        self.assertIn(LEVEL_DEFEAT, list(self.hooks().keys()))
        self.instance.on_incoming("Bob::fell")
        self.run_game_thread()
        self.assertEqual(list(self.hooks().keys()), [])  # calling a hooked function crashed the game before
        self.assertEqual(len(self.delayed), 1)
        self.delayed[0][1]()
        self.assertIn(LEVEL_DEFEAT, list(self.hooks().keys()))
        self.assertGreaterEqual(self.delayed[0][0], 1000)

    def test_the_hook_comes_back_even_when_the_call_fails(self):
        self.lua.execute("""
            FindFirstOf = function() return { IsValid = function() return true end, LevelDefeat = function() error('boom') end } end
        """)
        self.instance.on_incoming("Bob::fell")
        self.run_game_thread()
        self.assertTrue(any("LevelDefeat failed" in line for line in self.log()))
        self.assertEqual(self.instance.state().applied, 0)
        self.delayed[0][1]()
        self.assertIn(LEVEL_DEFEAT, list(self.hooks().keys()))

    def test_the_defeat_we_cause_is_not_sent_back(self):
        self.instance.on_incoming("Bob::fell")
        self.run_game_thread()
        self.delayed[0][1]()
        self.hooks()[LEVEL_DEFEAT](None)  # the game reports the defeat that we forced
        self.assertEqual(self.sent, [])

    def test_in_the_hub_or_unknown_map_nothing_happens(self):
        for name in ("", "HUB_Main", "Finale_Ending", None):
            self.map_name = name
            self.assertFalse(self.instance.on_incoming("Bob::fell"), name)
        self.run_game_thread()
        self.assertEqual(self.calls(), [])
        self.assertTrue(any("not in a level" in line for line in self.log()))

    def test_deaths_that_were_already_in_the_inbox_at_launch_are_history(self):
        self.assertFalse(self.instance.on_incoming("Bob::fell", True))
        self.run_game_thread()
        self.assertEqual(self.calls(), [])
        self.assertTrue(any("before the game started" in line for line in self.log()))

    def test_one_death_at_a_time(self):
        self.assertTrue(self.instance.on_incoming("Bob::fell"))
        self.assertFalse(self.instance.on_incoming("Eve::fell"))
        self.run_game_thread()
        self.assertEqual(self.calls(), ["LevelDefeat"])
        self.clock.t = self.clock.t + 11
        self.assertTrue(self.instance.on_incoming("Eve::fell"))

    def test_nothing_happens_when_deathlink_is_off(self):
        self.instance.set_mode("0")
        self.assertFalse(self.instance.on_incoming("Bob::fell"))
        self.run_game_thread()
        self.assertEqual(self.calls(), [])

    def test_a_user_who_unhooked_keeps_the_hook_off(self):
        self.lua.globals()["__cmds"]["ap_dl_unhook"]("ap_dl_unhook", self.lua.table_from([]))
        self.instance.on_incoming("Bob::fell")
        self.run_game_thread()
        self.assertEqual(self.calls(), ["LevelDefeat"])
        self.assertEqual(self.delayed, [])
        self.assertEqual(list(self.hooks().keys()), [])

    def test_ap_dl_kill_works_like_an_incoming_death_even_with_deathlink_off(self):
        self.instance.set_mode("0")
        self.lua.globals()["__cmds"]["ap_dl_kill"]("ap_dl_kill", self.lua.table_from([]))
        self.run_game_thread()
        self.assertEqual(self.calls(), ["LevelDefeat"])
        self.assertFalse(self.instance.is_enabled())  # the flag is restored

    def test_level_maps_match_the_location_data(self):
        import json
        data = json.loads((LIB.parent.parent / "locations.json").read_text(encoding="utf-8"))
        maps = {entry["map_name"] for entry in data["minigames"]} - {"Finale_Ending"}
        in_lua = {str(k) for k in self.module.LEVEL_MAPS.keys()}
        self.assertEqual(in_lua, maps)


class TestDeathLinkExperimentCommands(LuaCase):
    """ap_dl_* console commands used to find out which game function makes the player lose."""

    def setUp(self):
        super().setUp()
        module = self.load("death_link.lua")
        self.clock = self.lua.table(t=1000)
        self.lua.globals()["__clock"] = self.clock
        self.lua.execute("__now = function() return __clock.t end")
        self.sent = []
        self.instance = module.init(self.lua.table(send=lambda cause: self.sent.append(cause), now=self.lua.globals()["__now"]))
        self.lua.globals()["__loops"][1]()
        self.cmds = self.lua.globals()["__cmds"]

    def command(self, name, *args):
        self.cmds[name](name + " " + " ".join(args), self.lua.table_from(list(args)))

    def test_commands_exist(self):
        for name in ("ap_dl_status", "ap_dl_unhook", "ap_dl_rehook", "ap_dl_call", "ap_dl_kill"):
            self.assertIsNotNone(self.cmds[name], name)

    def test_calling_a_hooked_function_is_refused(self):
        self.command("ap_dl_call", "LevelDefeat")
        self.assertEqual(self.calls(), [])
        self.assertTrue(any("refused" in line for line in self.log()))

    def test_unknown_functions_are_refused(self):
        self.command("ap_dl_call", "SaveLevelVictory")
        self.command("ap_dl_call")
        self.assertEqual(self.calls(), [])
        self.assertTrue(any("usage:" in line for line in self.log()))

    def test_unhook_then_call_reaches_the_game_instance_and_marks_the_defeat_as_ours(self):
        self.instance.set_mode("1")
        self.command("ap_dl_unhook")
        self.assertEqual(len(list(self.hooks().keys())), 0)
        self.command("ap_dl_call", "LevelDefeat")
        self.assertEqual(self.calls(), ["LevelDefeat"])
        self.command("ap_dl_rehook")
        self.assertEqual(len(list(self.hooks().keys())), 1)
        # the defeat that our own call caused fires the hook: it must not become a DeathLink
        hook = list(self.hooks().values())[0]
        hook(None)
        self.assertEqual(self.sent, [])
        self.clock.t = self.clock.t + 11  # later, a real defeat is sent again
        hook(None)
        self.assertEqual(self.sent, ["lost a level"])

    def test_the_registration_loop_does_not_undo_an_unhook(self):
        # seen in game (2026-10-04): the loop kept running after it succeeded and re-hooked LevelDefeat one second after
        # ap_dl_unhook, so the following ap_dl_call was refused
        self.command("ap_dl_unhook")
        self.assertEqual(len(list(self.hooks().keys())), 0)
        for _ in range(3):
            self.lua.globals()["__loops"][1]()  # the loop fires again
        self.assertEqual(len(list(self.hooks().keys())), 0)
        self.command("ap_dl_call", "LevelDefeat")
        self.assertEqual(self.calls(), ["LevelDefeat"])  # not refused any more
        self.command("ap_dl_rehook")
        self.assertEqual(len(list(self.hooks().keys())), 1)

    def test_other_candidates_can_be_called_while_the_hook_stays(self):
        self.command("ap_dl_call", "LoadGameOver")
        self.assertEqual(self.calls(), ["LoadGameOver"])

    def test_unhooking_twice_is_harmless_and_status_reports(self):
        self.command("ap_dl_unhook")
        self.command("ap_dl_unhook")
        self.command("ap_dl_status")
        self.assertTrue(any("not hooked" in line for line in self.log()))
        self.assertTrue(any(line.startswith("[DEATHLINK] enabled=") for line in self.log()))


class TestLevelGateLogic(LuaCase):
    def setUp(self):
        super().setUp()
        self.gate = self.load("level_gate.lua")
        self.gate.GATED_ROWS = self.lua.table_from({5: "FNAF1_NIGHT2", 6: "FNAF1_NIGHT3"})

    def decide(self, row, vanilla, session, authorized):
        unlocked, reason = self.gate.decide(row, vanilla, session, self.lua.table_from({g: True for g in authorized}))
        return unlocked, str(reason)

    def test_an_authorized_gate_opens_the_level_even_when_the_game_says_locked(self):
        self.assertEqual(self.decide(6, False, True, ["FNAF1_NIGHT3"]), (True, "authorized (vanilla prerequisite waived)"))
        self.assertEqual(self.decide(6, True, True, ["FNAF1_NIGHT3"]), (True, "authorized"))

    def test_without_the_item_the_level_is_locked_even_when_the_game_says_open(self):
        self.assertEqual(self.decide(5, True, True, []), (False, "denied"))
        self.assertEqual(self.decide(5, False, True, ["FNAF1_NIGHT3"]), (False, "denied"))

    def test_ungated_rows_and_missing_sessions_keep_the_games_answer(self):
        self.assertEqual(self.decide(29, True, True, []), (True, "not gated"))
        self.assertEqual(self.decide(29, False, True, []), (False, "not gated"))
        self.assertEqual(self.decide(5, True, False, []), (True, "no AP session (vanilla behaviour)"))
        self.assertEqual(self.decide(5, False, False, []), (False, "no AP session (vanilla behaviour)"))

    def test_gate_table_parsing(self):
        rows, err = self.gate.parse_table("5=FNAF1_NIGHT2, 6=FNAF1_NIGHT3")
        self.assertEqual((rows[5], rows[6], err), ("FNAF1_NIGHT2", "FNAF1_NIGHT3", None))
        for bad in ("", "5=lower", "x=A", "5"):
            rows, err = self.gate.parse_table(bad)
            self.assertIsNone(rows, bad)
            self.assertIsNotNone(err)

    def test_gate_item_map_and_authorization_from_items(self):
        item_map, err = self.gate.parse_gate_items("101000020=DARK_PLUSHTRAP,101000024=FNAF1_NIGHT1")
        self.assertIsNone(err)
        ids, err = self.gate.parse_item_ids("101000024,101000099")
        self.assertIsNone(err)
        gates = self.gate.gates_for_items(ids, item_map)
        self.assertTrue(gates["FNAF1_NIGHT1"])
        self.assertIsNone(gates["DARK_PLUSHTRAP"])  # item not received
        empty, err = self.gate.parse_item_ids("")
        self.assertEqual(len(empty), 0)
        bad, err = self.gate.parse_item_ids("12,x")
        self.assertIsNone(bad)


class TestItemSyncLogic(LuaCase):
    def setUp(self):
        super().setUp()
        self.sync = self.load("item_sync.lua")

    def test_pending_items_follow_server_order_beyond_the_applied_count(self):
        ids = self.lua.table_from([101000039, 101000026, 101000011])
        pending = self.sync.pending(1, ids)
        self.assertEqual([(pending[i]["index"], pending[i]["item_id"]) for i in (1, 2)], [(1, 101000026), (2, 101000011)])
        self.assertEqual(len(self.sync.pending(3, ids)), 0)

    def test_parse_applied(self):
        self.assertEqual(tuple(self.sync.parse_applied("5")), (5, False))
        self.assertEqual(tuple(self.sync.parse_applied("1 reset")), (1, True))
        count, err = self.sync.parse_applied("nope")
        self.assertIsNone(count)

    def test_tick_applies_in_order_acknowledges_and_stops_at_the_first_failure(self):
        applied, acks = [], []
        instance = self.sync.init(self.lua.table(
            apply=lambda item_id, index: (applied.append(index) or index != 2),
            ack=lambda count: acks.append(count)))
        instance.on_session_sync("seed_slot")
        instance.on_snapshot("101,102,103,104")
        instance.tick()
        self.assertEqual(applied, [0, 1, 2])  # index 2 failed: nothing after it is tried
        self.assertEqual(acks, [2])  # only what really succeeded is acknowledged
        self.assertEqual(tuple(instance.status())[1:], (2, 4))

    def test_the_clients_applied_count_is_not_applied_again(self):
        applied = []
        instance = self.sync.init(self.lua.table(apply=lambda item_id, index: (applied.append(index) or True), ack=lambda count: None))
        instance.on_session_sync("seed_slot")
        instance.on_applied("3")
        instance.on_snapshot("101,102,103,104,105")
        instance.tick()
        self.assertEqual(applied, [3, 4])


class TestResearchTools(LuaCase):
    """ap_scan / ap_watch: read-only research console commands."""

    OBJECTS = [
        "Function /Game/Blueprints/Office.Office_C:PlayJumpscare",
        "Function /Game/Blueprints/Office.Office_C:JumpscareTick",
        "Function /Game/Blueprints/Foxy.Foxy_C:Jumpscare",
        "Function /Script/Engine.Actor:ReceiveTick",
        "BlueprintGeneratedClass /Game/Blueprints/Freddy.Freddy_C",
        "Foxy_JumpscareAnim_C /Game/Maps/Night.Night:PersistentLevel.Foxy_JumpscareAnim_C_0",
        "Function /Game/Blueprints/Office.Office_C:LightsOn",
    ]

    def setUp(self):
        super().setUp()
        self.module = self.load("research_tools.lua")
        self.lua.execute("""
            __objects = {}
            function __add(name)
                local object = {}
                function object:GetFullName() if name == "BROKEN" then error("boom") end return name end
                __objects[#__objects + 1] = object
            end
            __for_each = function(callback) for _, o in ipairs(__objects) do callback(o) end end
        """)
        for name in self.OBJECTS + ["BROKEN", self.OBJECTS[0]]:  # one object that throws, one duplicate
            self.lua.globals()["__add"](name)
        self.written = {}
        self.tools = self.module.init(self.lua.table(
            output_dir="OUT", for_each=self.lua.globals()["__for_each"],
            write=lambda path, text: self.written.__setitem__(path, text) or True))

    def test_pure_helpers(self):
        self.assertTrue(self.module.matches("Foo_JUMPSCARE_Bar", "jumpscare"))
        self.assertFalse(self.module.matches("Foo", "bar"))
        self.assertFalse(self.module.matches("Foo", ""))
        self.assertEqual(self.module.function_hook_path("Function /Game/X/Y.Y_C:DoIt"), "/Game/X/Y.Y_C:DoIt")
        self.assertIsNone(self.module.function_hook_path("Function /Script/Engine.Actor:ReceiveTick"))
        self.assertIsNone(self.module.function_hook_path("BlueprintGeneratedClass /Game/X/Y.Y_C"))
        self.assertEqual(self.module.short_name("/Game/X/Y.Y_C:DoIt"), "Y_C:DoIt")
        self.assertTrue(self.module.is_noisy("/Game/X/Y.Y_C:JumpscareTick"))
        self.assertFalse(self.module.is_noisy("/Game/X/Y.Y_C:PlayJumpscare"))
        self.assertEqual(self.module.safe_word("a b/c"), "a_b_c")

    def test_scan_writes_every_match_once_and_counts_functions(self):
        found = self.tools.scan("jumpscare")
        self.assertEqual(len(list(found.values())), 4)  # 3 functions + the animation actor, no duplicate, no broken object
        text = self.written["OUT/ap_scan_jumpscare.txt"]
        self.assertIn("3 of them functions", text.splitlines()[0])
        self.assertEqual(text.count("PlayJumpscare"), 1)  # the duplicate is listed once
        self.assertNotIn("LightsOn", text)

    def test_scan_respects_the_maximum_and_a_missing_word(self):
        self.assertEqual(len(list(self.tools.scan("jumpscare", 2).values())), 2)
        self.assertIsNone(self.tools.scan(""))
        self.assertTrue(any("usage: ap_scan" in line for line in self.log()))

    def test_scan_reports_when_the_ue4ss_function_is_missing(self):
        tools = self.module.init(self.lua.table(output_dir="OUT", write=lambda path, text: True))
        self.lua.execute("ForEachUObject = nil")
        self.assertIsNone(tools.scan("x"))
        self.assertTrue(any("not available" in line for line in self.log()))

    def test_watch_hooks_only_game_functions_that_are_not_noisy(self):
        added = self.tools.watch("jumpscare")
        self.assertEqual(added, 2)  # PlayJumpscare and Foxy:Jumpscare; JumpscareTick is noisy, the actor is not a function
        hooked = sorted(str(k) for k in self.hooks().keys())
        self.assertEqual(hooked, ["/Game/Blueprints/Foxy.Foxy_C:Jumpscare", "/Game/Blueprints/Office.Office_C:PlayJumpscare"])

    def test_watch_respects_its_maximum_and_never_hooks_twice(self):
        self.assertEqual(self.tools.watch("jumpscare", 1), 1)
        self.assertEqual(self.tools.watch("jumpscare", 5), 1)  # the first one is already watched, one more is added

    def test_a_watched_function_logs_its_first_calls_then_only_now_and_then(self):
        self.tools.watch("PlayJumpscare")
        hook = self.hooks()["/Game/Blueprints/Office.Office_C:PlayJumpscare"]
        for _ in range(120):
            hook(None)
        lines = [line for line in self.log() if line.startswith("[WATCH]")]
        # the first three calls also say how many parameters the hook received; the later ones stay short
        self.assertEqual(lines, ["[WATCH] Office_C:PlayJumpscare called (#1) args=0 []", "[WATCH] Office_C:PlayJumpscare called (#2) args=0 []",
                                 "[WATCH] Office_C:PlayJumpscare called (#3) args=0 []", "[WATCH] Office_C:PlayJumpscare called (#50)",
                                 "[WATCH] Office_C:PlayJumpscare called (#100)"])

    def test_clear_removes_every_watch_hook(self):
        self.tools.watch("jumpscare")
        self.assertEqual(self.tools.clear(), 2)
        self.assertEqual(len(list(self.hooks().keys())), 0)
        self.assertEqual(self.tools.clear(), 0)

    def make_class_tools(self):
        self.lua.execute("""
            function __named(full, extra)
                local object = extra or {}
                function object:GetFullName() return full end
                function object:IsValid() return true end
                return object
            end
            local parent = __named("BlueprintGeneratedClass /Script/Engine.Actor")
            function parent:ForEachFunction(cb) cb(__named("Function /Script/Engine.Actor:ReceiveTick")) end
            function parent:ForEachProperty(cb) end
            local child = __named("BlueprintGeneratedClass /Game/Blueprints/JumpScare.JumpScare_C")
            function child:ForEachFunction(cb)
                cb(__named("Function /Game/Blueprints/JumpScare.JumpScare_C:PlayJumpScare"))
                cb(__named("Function /Game/Blueprints/JumpScare.JumpScare_C:Stop"))
                cb(__named("Function /Game/Blueprints/JumpScare.JumpScare_C:Timeline_0__UpdateFunc"))
                cb(__named("Function /Game/Blueprints/JumpScare.JumpScare_C:FadeOutWithLevelLoad"))
            end
            function child:ForEachProperty(cb) cb(__named("ObjectProperty /Game/Blueprints/JumpScare.JumpScare_C:Anim")) end
            function child:GetSuperStruct() return parent end
            __classes = { ["/Game/Blueprints/JumpScare.JumpScare_C"] = child }
            __find_object = function(path) return __classes[path] end
            __find_all = function(name)
                if name == "JumpScare_C" then return { __named("JumpScare_C /Game/Maps/Hub.Hub:PersistentLevel.JumpScare_C_0") } end
                return nil
            end
        """)
        self.written = {}
        return self.module.init(self.lua.table(
            output_dir="OUT", find_object=self.lua.globals()["__find_object"], find_all=self.lua.globals()["__find_all"],
            write=lambda path, text: self.written.__setitem__(path, text) or True))

    def test_class_info_lists_functions_and_properties_up_to_the_engine_class(self):
        tools = self.make_class_tools()
        lines = [str(line) for line in tools.class_info("/Game/Blueprints/JumpScare.JumpScare_C").values()]
        self.assertIn("  FUNCTION Function /Game/Blueprints/JumpScare.JumpScare_C:PlayJumpScare", lines)
        self.assertIn("  PROPERTY ObjectProperty /Game/Blueprints/JumpScare.JumpScare_C:Anim", lines)
        self.assertIn("  FUNCTION Function /Script/Engine.Actor:ReceiveTick", lines)  # the parent is walked, then it stops
        text = self.written["OUT/ap_class_JumpScare_C.txt"]
        self.assertIn("PlayJumpScare", text)

    def test_describe_flags(self):
        self.assertEqual(str(self.module.describe_flags(0x44400400)).split()[0], "0x44400400")
        names = str(self.module.describe_flags(0x44400400)).split()[1:]
        self.assertEqual(sorted(names), ["BlueprintCallable", "Const", "HasOutParms", "Native"])
        self.assertEqual(str(self.module.describe_flags(0)), "0x00000000 ")
        self.assertEqual(str(self.module.describe_flags(None)), "?")

    def test_class_info_lists_each_functions_flags_and_survives_functions_that_cannot_give_them(self):
        tools = self.make_class_tools()
        self.lua.execute('''
            local fn = __named("Function /Game/Blueprints/JumpScare.JumpScare_C:GetCount")
            function fn:GetFunctionFlags() return 0x04400000 end
            local broken = __named("Function /Game/Blueprints/JumpScare.JumpScare_C:Broken")
            function broken:GetFunctionFlags() error("nope") end
            local child = __classes["/Game/Blueprints/JumpScare.JumpScare_C"]
            function child:ForEachFunction(cb)
                cb(fn)
                cb(broken)
                cb(__named("Function /Game/Blueprints/JumpScare.JumpScare_C:Plain"))
            end
        ''')
        lines = [str(line) for line in tools.class_info("/Game/Blueprints/JumpScare.JumpScare_C").values()]
        at = lines.index("  FUNCTION Function /Game/Blueprints/JumpScare.JumpScare_C:GetCount")
        self.assertEqual(lines[at + 1], "    FLAGS 0x04400000 HasOutParms BlueprintCallable")
        self.assertEqual(lines[at + 2], "  FUNCTION Function /Game/Blueprints/JumpScare.JumpScare_C:Broken")  # the error is swallowed
        self.assertEqual(lines[at + 3], "  FUNCTION Function /Game/Blueprints/JumpScare.JumpScare_C:Plain")

    def test_describe_args_shows_count_types_and_values_and_never_raises(self):
        self.lua.execute('''
            __param = function(kind, value)
                return {type = function() return kind end, get = function() return value end}
            end
            __bad = {type = function() error("x") end, get = function() error("y") end}
        ''')
        g = self.lua.globals()
        args = self.lua.table_from([g["__param"]("IntProperty", 4), g["__param"]("BoolProperty", True), g["__bad"]])
        self.assertEqual(str(self.module.describe_args(args, 3)), "args=3 [IntProperty=4, BoolProperty=true, ?=<unreadable>]")
        self.assertEqual(str(self.module.describe_args(self.lua.table_from([]), 0)), "args=0 []")

    def test_a_hooked_function_logs_its_arguments_on_the_first_calls_only(self):
        tools = self.make_class_tools()
        self.assertTrue(tools.hook_function("/Game/X/Y.Y_C:DoIt"))
        self.lua.execute('''
            __p = {type = function() return "IntProperty" end, get = function() return 7 end}
        ''')
        hook = self.hooks()["/Game/X/Y.Y_C:DoIt"]
        for _ in range(4):
            hook(None, self.lua.globals()["__p"])
        lines = [line for line in self.log() if "[WATCH] Y_C:DoIt" in line]
        self.assertEqual(lines[0], "[WATCH] Y_C:DoIt called (#1) args=1 [IntProperty=7]")
        self.assertEqual(len(lines), 3)  # #1..#3 only; #4 is not logged and carries no detail
        hook(None)
        self.assertEqual(len([line for line in self.log() if "[WATCH] Y_C:DoIt" in line]), 3)

    def test_instances_shows_the_class_path_when_the_object_can_tell_it(self):
        self.make_class_tools()
        self.lua.execute('''
            __find_one = function(name)
                local object = __named("AquiredLog_C /Game/Scenes/Room.Room:PersistentLevel.AquiredLog31")
                function object:GetClass()
                    return __named("BlueprintGeneratedClass /Game/ProductionAssets/Actors/AquiredLog.AquiredLog_C")
                end
                return { object, __named("Plain_C /Game/Scenes/Room.Room:PersistentLevel.Plain") }
            end
        ''')
        tools = self.module.init(self.lua.table(
            output_dir="OUT", find_object=self.lua.globals()["__find_object"], find_all=self.lua.globals()["__find_one"],
            write=lambda path, text: True))
        names = [str(n) for n in tools.instances("AquiredLog_C").values()]
        self.assertEqual(names[0], "AquiredLog_C /Game/Scenes/Room.Room:PersistentLevel.AquiredLog31   [class /Game/ProductionAssets/Actors/AquiredLog.AquiredLog_C]")
        self.assertEqual(names[1], "Plain_C /Game/Scenes/Room.Room:PersistentLevel.Plain")  # no GetClass: just the name

    def test_instances_is_capped(self):
        tools = self.make_class_tools()
        self.lua.execute('''
            __find_many = function(name)
                local list = {}
                for i = 1, 5 do list[i] = __named("Foo_C /Game/Maps/M.M:PersistentLevel.Foo_C_" .. i) end
                return list
            end
        ''')
        capped = self.module.init(self.lua.table(
            output_dir="OUT", find_object=self.lua.globals()["__find_object"], find_all=self.lua.globals()["__find_many"],
            write=lambda path, text: True))
        names = list(capped.instances("Foo_C", 2).values())
        self.assertEqual(len(names), 2)
        self.assertTrue(any("5 live object(s) of Foo_C (showing the first 2)" in line for line in self.log()), self.log())

    def test_class_info_reports_a_missing_class_and_a_missing_argument(self):
        tools = self.make_class_tools()
        self.assertIsNone(tools.class_info("/Game/Nope.Nope_C"))
        self.assertIsNone(tools.class_info(""))
        self.assertTrue(any("class not found" in line for line in self.log()))
        self.assertEqual(self.written, {})

    def test_hook_class_hooks_the_functions_the_class_declares_and_skips_noise_and_parents(self):
        tools = self.make_class_tools()
        self.assertEqual(tools.hook_class("/Game/Blueprints/JumpScare.JumpScare_C"), 2)
        self.assertEqual(sorted(str(k) for k in self.hooks().keys()),
                         ["/Game/Blueprints/JumpScare.JumpScare_C:PlayJumpScare", "/Game/Blueprints/JumpScare.JumpScare_C:Stop"])
        self.hooks()["/Game/Blueprints/JumpScare.JumpScare_C:Stop"](None)
        self.assertIn("[WATCH] JumpScare_C:Stop called (#1) args=0 []", self.log())
        self.assertEqual(tools.hook_class("/Game/Blueprints/JumpScare.JumpScare_C"), 0)  # never twice
        self.assertEqual(tools.hook_class("/Game/Nope.Nope_C"), 0)
        self.assertEqual(tools.hook_class(""), 0)

    def test_unsafe_functions_are_never_hooked_by_class_and_need_force_by_name(self):
        tools = self.make_class_tools()
        tools.hook_class("/Game/Blueprints/JumpScare.JumpScare_C")
        self.assertNotIn("/Game/Blueprints/JumpScare.JumpScare_C:FadeOutWithLevelLoad", [str(k) for k in self.hooks().keys()])
        self.assertTrue(any("1 unsafe skipped" in line for line in self.log()), self.log())
        path = "/Game/X/Y.Y_C:LoadCasetteRoom"
        self.assertFalse(tools.hook_function(path))
        self.assertTrue(any("refused" in line and "force" in line for line in self.log()))
        self.assertNotIn(path, [str(k) for k in self.hooks().keys()])
        self.assertTrue(tools.hook_function(path, "force"))
        self.assertIn(path, [str(k) for k in self.hooks().keys()])

    def test_is_unsafe_names_the_functions_that_blacked_out_the_tape_area_and_spares_the_getters(self):
        prefix = "/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:"
        for name in ("FadeOut", "FadeOutWithLevelLoad", "FadeOutWithTimerEvent", "AfterFadeLevelLoader", "RunFadeOut", "LoadCasetteRoom",
                     "LoadLevel", "RestartCurrentLevel", "ExecuteUbergraph_BP_FNAF_GameInstance", "GetAchievementData",
                     "CheckforAchievementCompletion", "GetLevelInstructions", "SpawnLevelDatabase", "ReceiveInit"):
            self.assertTrue(self.module.is_unsafe(prefix + name), name)
        save = "/Game/ProductionAssets/Blueprints/Data/SaveGame/FNAFSaveGame.FNAFSaveGame_C:"
        for path in (save + "GetGlitchCount", save + "HasGlitch", save + "HasListenedToGlitch", save + "HasPrize",
                     save + "GetTotalCoinCount", prefix + "HasCoin", prefix + "HasGlitch", prefix + "GetCoinCount", prefix + "LevelDefeat"):
            self.assertFalse(self.module.is_unsafe(path), path)
        # only the function name counts, not the class path
        self.assertFalse(self.module.is_unsafe("/Game/Load/Fade.Fade_C:Stop"))

    def test_hook_function_hooks_one_path(self):
        tools = self.make_class_tools()
        self.assertTrue(tools.hook_function("/Game/X/Y.Y_C:DoIt"))
        self.assertFalse(tools.hook_function("/Game/X/Y.Y_C:DoIt"))
        self.assertFalse(tools.hook_function(""))
        self.assertEqual(len(list(self.hooks().keys())), 1)

    def test_instances_lists_live_objects_and_survives_no_result(self):
        tools = self.make_class_tools()
        self.assertEqual(len(list(tools.instances("JumpScare_C").values())), 1)
        self.assertEqual(len(list(tools.instances("Nothing_C").values())), 0)
        self.assertTrue(any("1 live object(s) of JumpScare_C" in line for line in self.log()))

    def test_console_commands_are_registered_and_take_words(self):
        cmds = self.lua.globals()["__cmds"]
        for name in ("ap_scan", "ap_watch", "ap_watch_clear", "ap_watch_status", "ap_class", "ap_instances", "ap_hookclass", "ap_hookfn"):
            self.assertIsNotNone(cmds[name], name)
        cmds["ap_watch"]("ap_watch jumpscare 1", self.lua.table_from(["jumpscare", "1"]))
        self.assertEqual(len(list(self.hooks().keys())), 1)
        cmds["ap_watch_status"]("ap_watch_status", self.lua.table_from([]))
        self.assertTrue(any("1 function(s) watched" in line for line in self.log()))


@unittest.skipIf(LuaRuntime is None, "lupa is not installed")
class TestEveryLuaFileCompiles(unittest.TestCase):
    """A syntax error in any mod file would only show up in the game's log at startup (or silently disable a feature)."""

    def test_all_mod_lua_files_compile(self):
        lua = LuaRuntime()
        compile_source = lua.eval("function(src, name) local fn, err = load(src, '=' .. name) return fn ~= nil, err end")
        files = sorted((project_root / "ue4ss_mod").rglob("*.lua"))
        self.assertGreater(len(files), 15)
        for path in files:
            ok, err = compile_source(path.read_text(encoding="utf-8"), path.name)
            self.assertTrue(ok, f"{path.relative_to(project_root)}: {err}")


@unittest.skipIf(LuaRuntime is None, "lupa is not installed")
class TestInboxReplay(LuaCase):
    """The inbox is append-only and read from the start at every game launch: the first pass is history."""

    def test_only_deaths_appended_after_the_first_poll_are_live(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "ap_inbox.txt"
            inbox.write_text("DEATHLINK Old::from last night\n", encoding="utf-8")
            seen = []
            builder = self.load("bridge_io.lua")
            bridge = builder(self.lua.table(
                outbox_path=str(Path(tmp) / "ap_outbox.txt"), inbox_path=str(inbox), bridge_dir=tmp,
                emitted_location_names=self.lua.table(), on_item=lambda *a: None,
                on_deathlink=lambda spec, is_replay: seen.append((str(spec), bool(is_replay)))))
            bridge.poll_inbox()
            with inbox.open("a", encoding="utf-8") as handle:
                handle.write("DEATHLINK New::just now\n")
            bridge.poll_inbox()
            bridge.poll_inbox()  # nothing new: nothing delivered twice
        self.assertEqual(seen, [("Old::from last night", True), ("New::just now", False)])



@unittest.skipIf(LuaRuntime is None, "lupa is not installed")
class TestGameThread(LuaCase):
    """lib/game_thread.lua: timers that run on the game thread, a cached game instance, diagnostics.

    Background: a crash dump of the 2026-10-04 playtest showed a UE4SS worker thread (where LoopAsync runs) inside the object-array
    scan behind FindFirstOf, on an object that was being destroyed.
    """

    def setUp(self):
        super().setUp()
        self.module = self.load("game_thread.lua")
        self.clock = [100]
        self.scans = 0
        self.on_game_thread = True
        self.queue = []
        self.loops = []
        self.make_instance = self.lua.eval(
            "function(state) return {IsValid = function() return state.valid end} end")

    def build(self, game_thread_support=True, found=True, thread_check=True):
        state = self.lua.table(valid=True)
        self.state = state

        def find_first(class_name):
            self.scans += 1
            self.last_class = str(class_name)
            return self.make_instance(state) if found else None

        params = self.lua.table(
            find_first=find_first, now=lambda: self.clock[0],
            loop_async=lambda ms, fn: self.loops.append(fn))
        if thread_check:
            params["in_game_thread"] = lambda: self.on_game_thread
        if game_thread_support:
            params["run_on_game_thread"] = lambda body: self.queue.append(body)
        return self.module.init(params)

    def run_queue(self):
        queue, self.queue = self.queue, []
        for body in queue:
            body()

    def test_the_game_instance_is_found_once_and_cached(self):
        instance = self.build()
        self.assertIsNotNone(instance.game_instance())
        for _ in range(50):
            self.assertIsNotNone(instance.game_instance())
        self.assertEqual(self.scans, 1)
        self.assertEqual(self.last_class, "BP_FNAF_GameInstance_C")

    def test_the_object_array_is_never_scanned_off_the_game_thread(self):
        instance = self.build()
        self.on_game_thread = False
        self.assertIsNone(instance.game_instance())
        self.assertEqual(self.scans, 0)
        self.on_game_thread = True
        self.assertIsNotNone(instance.game_instance())
        self.assertEqual(self.scans, 1)

    def test_without_is_in_game_thread_no_scan_happens_before_a_job_ran_on_the_game_thread(self):
        instance = self.build(thread_check=False)
        instance.every("job", 1000, lambda: None)
        self.assertIsNone(instance.game_instance())  # e.g. the call made while the mod is still loading
        self.assertEqual(self.scans, 0)
        self.loops[0]()
        self.run_queue()  # a job ran on the game thread
        self.assertIsNotNone(instance.game_instance())
        self.assertEqual(self.scans, 1)

    def test_while_the_instance_is_missing_the_rescan_is_rate_limited(self):
        instance = self.build(found=False)
        for _ in range(20):
            self.assertIsNone(instance.game_instance())
        self.assertEqual(self.scans, 1)
        self.clock[0] += 3
        self.assertIsNone(instance.game_instance())
        self.assertEqual(self.scans, 2)

    def test_a_destroyed_instance_is_dropped_and_found_again(self):
        instance = self.build()
        self.assertIsNotNone(instance.game_instance())
        self.state.valid = False
        self.clock[0] += 3
        # the cached object is invalid: it is dropped, the rescan returns the same (still invalid) object and refuses it
        self.assertIsNone(instance.game_instance())
        self.assertEqual(self.scans, 2)
        self.state.valid = True
        self.clock[0] += 3
        self.assertIsNotNone(instance.game_instance())

    def test_every_only_schedules_from_the_worker_thread_and_runs_on_the_game_thread(self):
        instance = self.build()
        ran = []
        instance.every("job", 1000, lambda: ran.append(1))
        self.assertEqual(len(self.loops), 1)
        self.loops[0]()  # the worker thread ticks
        self.assertEqual(ran, [])  # nothing ran yet: the body was only queued for the game thread
        self.assertEqual(len(self.queue), 1)
        self.run_queue()
        self.assertEqual(ran, [1])

    def test_a_tick_is_skipped_while_the_previous_one_has_not_run(self):
        instance = self.build()
        ran = []
        instance.every("job", 1000, lambda: ran.append(1))
        for _ in range(5):  # the game thread is stalled (loading screen)
            self.loops[0]()
        self.assertEqual(len(self.queue), 1)  # no backlog
        self.run_queue()
        self.assertEqual(ran, [1])
        self.loops[0]()
        self.run_queue()
        self.assertEqual(ran, [1, 1])
        self.assertIn("job=2/4", str(instance.stats("")))

    def test_a_job_returning_true_stops_its_loop(self):
        instance = self.build()
        ran = []
        instance.every("once", 1000, lambda: (ran.append(1) or True))
        self.assertFalse(self.loops[0]())
        self.run_queue()
        self.assertTrue(self.loops[0]())  # the next worker tick tells UE4SS to stop looping
        self.run_queue()
        self.assertEqual(ran, [1])

    def test_an_error_in_a_job_is_logged_once_and_does_not_stop_the_loop(self):
        instance = self.build()
        boom = self.lua.eval("function() error('boom') end")
        instance.every("bad", 1000, boom)
        for _ in range(3):
            self.loops[0]()
            self.run_queue()
        errors = [line for line in self.log() if "[ERROR] [LOOP] bad" in line]
        self.assertEqual(len(errors), 1)
        self.assertIn("boom", errors[0])
        self.assertFalse(self.loops[0]())

    def test_without_execute_in_game_thread_the_job_runs_inline(self):
        instance = self.build(game_thread_support=False)
        ran = []
        instance.every("job", 1000, lambda: ran.append(1))
        self.loops[0]()
        self.loops[0]()
        self.assertEqual(ran, [1, 1])

    def test_diagnostics_log_map_changes_and_a_heartbeat(self):
        instance = self.build()
        maps = ["", "Main_Menu_With_Showtime", "Main_Menu_With_Showtime", "Repair_Bonnie_Game"]
        position = [0]

        def current_map():
            value = maps[min(position[0], len(maps) - 1)]
            position[0] += 1
            return value

        instance.start_diagnostics(current_map)
        for _ in range(61):
            self.loops[-1]()
            self.run_queue()
        lines = self.log()
        changes = [line for line in lines if line.startswith("[DIAG] map:")]
        self.assertEqual(len(changes), 3)
        self.assertIn("'Main_Menu_With_Showtime' -> 'Repair_Bonnie_Game'", changes[-1])
        heartbeat = [line for line in lines if line.startswith("[DIAG] up=")]
        self.assertEqual(len(heartbeat), 1)
        self.assertIn("map='Repair_Bonnie_Game'", heartbeat[0])
        self.assertIn("gi_scans=0", heartbeat[0])
        self.assertIn("diag=", heartbeat[0])

    def test_main_lua_has_no_raw_loops(self):
        main = (LIB.parent / "main.lua").read_text(encoding="utf-8")
        code = "\n".join(line for line in main.splitlines() if not line.strip().startswith("--"))
        self.assertNotIn("LoopAsync(", code)
        self.assertNotIn("FindFirstOf", code)


@unittest.skipIf(LuaRuntime is None, "lupa is not installed")
class TestInboxReplayCollapse(LuaCase):
    """Only the last connect block of the inbox history is replayed at launch (every connect is self-contained)."""

    def bridge(self, tmp, **handlers):
        builder = self.load("bridge_io.lua")
        env = self.lua.table(
            outbox_path=str(Path(tmp) / "ap_outbox.txt"), inbox_path=str(Path(tmp) / "ap_inbox.txt"), bridge_dir=tmp,
            emitted_location_names=self.lua.table(), on_item=lambda *a: None)
        for key, value in handlers.items():
            env[key] = value
        return builder(env)

    def replay_start(self, lines):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            bridge = self.bridge(tmp)
            return bridge.replay_start(self.lua.table_from(lines))

    def test_replay_start(self):
        self.assertEqual(self.replay_start([]), 1)
        self.assertEqual(self.replay_start(["PRINT hello", "STATUS CONNECTED x"]), 1)  # no connect block: everything
        self.assertEqual(self.replay_start(["SESSION_SYNC a", "RECEIVED_SNAPSHOT 1"]), 1)
        lines = ["CONNECTED", "SESSION_SYNC a", "RECEIVED_SNAPSHOT 1", "CONNECTED", "SESSION_SYNC b", "RECEIVED_SNAPSHOT 2"]
        self.assertEqual(self.replay_start(lines), 4)  # the CONNECTED line in front of the last SESSION_SYNC goes with it
        self.assertEqual(self.replay_start(["SESSION_SYNC a", "PRINT x", "SESSION_SYNC b"]), 3)

    def test_the_first_pass_replays_only_the_last_connect_and_later_lines_are_all_delivered(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "ap_inbox.txt"
            inbox.write_text("\n".join([
                "CONNECTED", "SESSION_SYNC old_a", "RECEIVED_SNAPSHOT 11,11,11", "DEATHLINK Old::died",
                "CONNECTED", "SESSION_SYNC old_b", "RECEIVED_SNAPSHOT 11",
                "CONNECTED", "SESSION_SYNC current", "RECEIVED_SNAPSHOT 11,12", "APPLIED_ITEMS 2",
            ]) + "\n", encoding="utf-8")
            calls = []
            bridge = self.bridge(
                tmp,
                on_session_sync=lambda spec: calls.append(("sync", str(spec))),
                on_received_snapshot=lambda spec: calls.append(("snapshot", str(spec))),
                on_applied_items=lambda spec: calls.append(("applied", str(spec))),
                on_deathlink=lambda spec, is_replay: calls.append(("death", str(spec), bool(is_replay))))
            bridge.poll_inbox()
            self.assertEqual(calls, [("sync", "current"), ("snapshot", "11,12"), ("applied", "2")])
            self.assertTrue(any("skipped 7 line(s) of older sessions" in line for line in self.log()), self.log())
            with inbox.open("a", encoding="utf-8") as handle:
                handle.write("RECEIVED_SNAPSHOT 11,12,13\nDEATHLINK New::now\n")
            bridge.poll_inbox()
            bridge.poll_inbox()  # unchanged file: nothing more
            self.assertEqual(calls[3:], [("snapshot", "11,12,13"), ("death", "New::now", False)])

    def test_an_inbox_without_a_connect_block_is_replayed_whole(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ap_inbox.txt").write_text("RECEIVED_SNAPSHOT 1\nRECEIVED_SNAPSHOT 1,2\n", encoding="utf-8")
            calls = []
            bridge = self.bridge(tmp, on_received_snapshot=lambda spec: calls.append(str(spec)))
            bridge.poll_inbox()
            self.assertEqual(calls, ["1", "1,2"])


@unittest.skipIf(LuaRuntime is None, "lupa is not installed")
class TestExactHooksCrashFixes(LuaCase):
    """The two ways the mod fed garbage to Lua's FString:ToString (the access violation in the playtest crash dump)."""

    GI = "/Game/ProductionAssets/Blueprints/System/BP_FNAF_GameInstance.BP_FNAF_GameInstance_C:"

    def setUp(self):
        super().setUp()
        self.sent = []
        self.lua.execute("""
            __bomb = setmetatable({}, {__index = function() error("a prize id was decoded") end,
                                       __tostring = function() error("a prize id was decoded") end})
            __world = {
                IsValid = function() return true end,
                GetFullName = function() return "World /Game/Scenes/Repair_Games/Repair_Bonnie_Game.Repair_Bonnie_Game" end,
                GetName = function() error("World:GetName() must not be used") end,
            }
            __gi = {
                SaveSlotName = "Playerarchi",
                IsValid = function() return true end,
                GetWorld = function() return __world end,
                SaveGameRef = {Prizes = {ForEach = function(self, callback) callback(__bomb) callback(__bomb) callback(__bomb) end}},
            }
        """)
        module = self.load("exact_hooks.lua")
        self.hooks_api = module.init(self.lua.table(
            APBridge=self.lua.table(
                send_location_check_name=lambda name: self.sent.append(str(name)), send_goal=lambda: self.sent.append("GOAL")),
            locations_data=self.lua.table(row_id_to_location=self.lua.table(), location_name_to_id=self.lua.table()),
            emitted_location_names=self.lua.table(), baseline_location_names=self.lua.table(),
            game_instance=lambda: self.lua.globals()["__gi"]))

    def test_the_prize_poll_counts_without_decoding_a_single_prize_id(self):
        self.hooks_api.poll_savegame_state()
        self.assertTrue(any("Save prize count changed: 0 -> 3" in line for line in self.log()), self.log())
        self.assertEqual(self.sent, [])  # prize locations come from the client's save poll only

    def test_a_prize_award_logs_and_counts_but_sends_nothing(self):
        self.hooks()[self.GI + "AwardRandomPrize"](self.lua.globals()["__gi"], "55")
        self.assertTrue(any("Prize award trigger fired" in line for line in self.log()))
        self.assertTrue(any("Save prize count changed: 0 -> 3" in line for line in self.log()))
        self.assertEqual(self.sent, [])

    def test_the_map_name_comes_from_get_full_name(self):
        self.assertEqual(str(self.hooks_api.current_map_name()), "Repair_Bonnie_Game")

    def test_a_level_victory_resolves_the_map_without_get_name(self):
        self.hooks()[self.GI + "SaveLevelVictory"](self.lua.globals()["__gi"])
        self.assertTrue(any("Map='Repair_Bonnie_Game'" in line for line in self.log()), self.log())
        self.assertEqual(self.sent, ["Complete Parts and Service - Bonnie"])



@unittest.skipIf(LuaRuntime is None, "lupa is not installed")
class TestDerivedCounters(LuaCase):
    """derived_counters.lua: the tape count the game shows follows the Glitch Tape items received."""

    PATH = "/Game/ProductionAssets/Blueprints/Data/SaveGame/FNAFSaveGame.FNAFSaveGame_C:GetGlitchCount"
    TAPE = 101000001
    TOKEN = 101000011

    def setUp(self):
        super().setUp()
        self.module = self.load("derived_counters.lua")
        self.instance = self.module.init()
        self.lua.globals()["__loops"][1]()  # the hook registration loop runs once the game is ready
        self.lua.execute("""
            __ret = function(value)
                local r = {v = value}
                function r:get() return self.v end
                function r:set(x) self.v = x end
                return r
            end
        """)

    def call_getter(self, vanilla):
        ret = self.lua.globals()["__ret"](vanilla)
        self.hooks()[self.PATH](None, ret)
        return ret.v

    def test_the_getter_is_hooked_by_the_loop(self):
        self.assertIn(self.PATH, [str(k) for k in self.hooks().keys()])
        self.assertTrue(self.lua.globals()["__loops"][1]())  # all hooked: the loop stops

    def test_count_items(self):
        self.assertEqual(tuple(self.module.count_items("101000001,101000011,101000001", self.TAPE)), (2, None))
        self.assertEqual(tuple(self.module.count_items("", self.TAPE)), (0, None))
        self.assertEqual(tuple(self.module.count_items(None, self.TAPE)), (0, None))
        count, err = self.module.count_items("1,x", self.TAPE)
        self.assertIsNone(count)
        self.assertIn("bad item id", str(err))

    def test_vanilla_until_a_session_and_its_item_list_exist(self):
        self.assertEqual(self.call_getter(4), 4)  # no session: the game's own number
        self.instance.on_session_sync("seed_slot")
        self.assertEqual(self.call_getter(4), 4)  # session, but the list has not arrived yet
        self.instance.on_snapshot("101000001,101000001,101000001,101000011")
        self.assertEqual(self.call_getter(4), 3)  # 3 Glitch Tape items, whatever the save says
        self.assertEqual(self.call_getter(0), 3)

    def test_items_without_a_session_never_override_the_game(self):
        self.instance.on_snapshot("101000001,101000001")  # no SESSION_SYNC yet
        self.assertEqual(self.call_getter(4), 4)

    def test_without_a_return_value_parameter_the_value_is_returned_from_the_callback(self):
        """GetGlitchCount reaches its hook with no parameters: the only lever left is the callback's own return value."""
        hook = self.hooks()[self.PATH]
        self.assertIsNone(hook(None))  # nothing to override: the game's value stands
        self.instance.force("tapes", 2)
        self.assertEqual(hook(None), 2)
        self.assertTrue(any("(returned from the callback)" in line for line in self.log()))
        # with a return-value parameter the parameter is set and nothing is returned
        ret = self.lua.globals()["__ret"](9)
        self.assertIsNone(hook(None, ret))
        self.assertEqual(ret.v, 2)

    def test_an_empty_list_means_zero_tapes(self):
        self.instance.on_session_sync("seed_slot")
        self.instance.on_snapshot("")
        self.assertEqual(self.call_getter(4), 0)

    def test_only_glitch_tape_items_count_and_the_latest_snapshot_replaces_the_count(self):
        self.instance.on_session_sync("seed_slot")
        self.instance.on_snapshot("101000011,101000011,101000001")
        self.assertEqual(self.call_getter(9), 1)
        self.instance.on_snapshot("101000001,101000001,101000011")
        self.assertEqual(self.call_getter(9), 2)

    def test_a_bad_snapshot_changes_nothing(self):
        self.instance.on_session_sync("seed_slot")
        self.instance.on_snapshot("101000001")
        self.instance.on_snapshot("101000001,oops")
        self.assertEqual(self.call_getter(9), 1)
        self.assertTrue(any("bad snapshot ignored" in line for line in self.log()))

    def test_a_new_session_forgets_the_old_count_until_its_own_list_arrives(self):
        self.instance.on_session_sync("seed_a")
        self.instance.on_snapshot("101000001,101000001")
        self.assertEqual(self.call_getter(7), 2)
        self.instance.on_session_sync("seed_a")  # a reconnect to the same session keeps it
        self.assertEqual(self.call_getter(7), 2)
        self.instance.on_session_sync("seed_b")
        self.assertEqual(self.call_getter(7), 7)  # vanilla, not seed_a's tapes
        self.instance.on_snapshot("101000001")
        self.assertEqual(self.call_getter(7), 1)

    def test_force_overrides_without_a_session_and_off_restores_vanilla(self):
        self.assertTrue(self.instance.force("tapes", 2))
        self.assertEqual(self.call_getter(16), 2)
        self.instance.force("tapes", None)
        self.assertEqual(self.call_getter(16), 16)
        self.assertFalse(self.instance.force("nope", 1))

    def test_each_distinct_outcome_is_logged_once(self):
        self.instance.on_session_sync("seed_slot")
        self.instance.on_snapshot("101000001")
        for _ in range(5):
            self.call_getter(4)
        lines = [line for line in self.log() if "[GAME] tapes observed" in line]
        self.assertEqual(len(lines), 1)
        self.assertIn("vanilla=4 -> 1", lines[0])

    def test_console_commands(self):
        cmds = self.lua.globals()["__cmds"]
        cmds["ap_counter_force"]("ap_counter_force tapes 3", self.lua.table_from(["tapes", "3"]))
        self.assertEqual(self.call_getter(16), 3)
        cmds["ap_counter_force"]("ap_counter_force tapes off", self.lua.table_from(["tapes", "off"]))
        self.assertEqual(self.call_getter(16), 16)
        cmds["ap_counter_force"]("ap_counter_force nope 1", self.lua.table_from(["nope", "1"]))
        self.assertTrue(any("Usage: ap_counter_force" in line for line in self.log()))
        cmds["ap_counter_status"]("ap_counter_status", self.lua.table_from([]))
        self.assertTrue(any(line.startswith("[ARCHI] Derived counters: tapes:") and "hooked=1/1" in line for line in self.log()))

    def test_main_lua_feeds_the_session_and_every_snapshot_to_the_counters(self):
        main = (LIB.parent / "main.lua").read_text(encoding="utf-8")
        for call in ("derived_counters.on_session_sync(session_id)", "derived_counters.on_snapshot(spec)", "derived_counters.lua"):
            self.assertIn(call, main)

    def test_the_tape_item_id_matches_the_world(self):
        # ITEM_OFFSET (101000000) + the code of "Glitch Tape" (1) in fnaf_help_wanted/data.py
        data = (project_root / "fnaf_help_wanted" / "data.py").read_text(encoding="utf-8")
        self.assertIn("ITEM_OFFSET = 101000000", data)
        self.assertIn('"Glitch Tape": ItemData(1,', data)
        self.assertEqual(self.module.DEFINITIONS[1]["item_id"], 101000001)


class TestDeathLinkGiftBoxPure(LuaCase):
    """`death_link_gift_box`: the game over that follows the prize box jumpscare (map Level_Victory) can be kept out of DeathLink."""

    def setUp(self):
        super().setUp()
        self.module = self.load("death_link.lua")

    def decide(self, map_name, **state):
        base = self.lua.table(enabled=True, suppress_until=0)
        for key, value in state.items():
            base[key] = value
        send, reason = self.module.decide_send(base, 100, map_name)
        return bool(send), str(reason)

    def test_the_gift_box_map_is_the_victory_screen_and_never_a_level(self):
        maps = self.module.GIFT_BOX_MAPS
        self.assertEqual([str(key) for key in maps.keys()], ["Level_Victory"])
        for level in self.module.LEVEL_MAPS.keys():
            self.assertIsNone(maps[level], level)

    def test_by_default_the_gift_box_defeat_is_sent_like_before(self):
        self.assertTrue(self.decide("Level_Victory")[0])  # the state has no send_gift_box field at all
        self.assertTrue(self.decide("Level_Victory", send_gift_box=True)[0])

    def test_with_the_option_off_only_the_gift_box_defeat_is_held_back(self):
        send, reason = self.decide("Level_Victory", send_gift_box=False)
        self.assertFalse(send)
        self.assertIn("gift box", reason)
        for other in ("Repair_Bonnie_Game", "NightGuard_Office01", "Main_Menu_With_Showtime", "Level_GameOver", "", None):
            self.assertTrue(self.decide(other, send_gift_box=False)[0], other)

    def test_the_option_never_matters_while_deathlink_is_off(self):
        for gift in (True, False):
            self.assertEqual(self.decide("Level_Victory", enabled=False, send_gift_box=gift),
                             (False, "DeathLink is off for this slot"))

    def test_an_unknown_map_stays_a_normal_defeat(self):
        self.assertTrue(self.decide(None, send_gift_box=False)[0])  # decide_send called as before, without a map
        self.assertTrue(bool(self.module.decide_send(self.lua.table(enabled=True, suppress_until=0, send_gift_box=False), 100)[0]))


class TestDeathLinkGiftBoxRuntime(LuaCase):
    def setUp(self):
        super().setUp()
        self.module = self.load("death_link.lua")
        self.sent = []
        self.map = ["Repair_Bonnie_Game"]
        self.clock = self.lua.table(t=1000)
        self.lua.globals()["__clock"] = self.clock
        self.lua.execute("__now = function() return __clock.t end")

        def current_map():
            if self.map[0] is None:
                raise RuntimeError("no world")
            return self.map[0]

        self.instance = self.module.init(self.lua.table(
            send=lambda cause: self.sent.append(cause), now=self.lua.globals()["__now"], current_map=current_map))
        self.lua.globals()["__loops"][1]()
        self.defeat = self.hooks()[LEVEL_DEFEAT]

    def advance(self, seconds):
        self.clock.t = self.clock.t + seconds

    def lose_on(self, map_name):
        self.map[0] = map_name
        self.defeat(None)

    def test_default_sends_the_gift_box_defeat_and_says_where_it_happened(self):
        self.instance.set_mode("1")
        self.lose_on("Level_Victory")
        self.assertEqual(self.sent, ["lost a level"])
        self.assertTrue(any("Level_Victory" in line for line in self.log()), self.log())

    def test_a_fresh_mod_sends_the_gift_box_defeat(self):
        self.assertTrue(self.instance.state().send_gift_box)  # before any line of the inbox was read
        self.instance.state().enabled = True  # DeathLink on without a DEATH_LINK_MODE line having reset anything
        self.lose_on("Level_Victory")
        self.assertEqual(self.sent, ["lost a level"])
    def test_option_off_holds_back_the_gift_box_defeat_and_logs_why(self):
        self.instance.set_mode("1")
        self.instance.set_gift_box_mode("0")
        self.lose_on("Level_Victory")
        self.assertEqual(self.sent, [])
        self.assertTrue(any("not sent" in line and "gift box" in line and "Level_Victory" in line for line in self.log()), self.log())

    def test_option_off_still_sends_a_defeat_inside_a_level(self):
        self.instance.set_mode("1")
        self.instance.set_gift_box_mode("0")
        self.lose_on("Repair_Bonnie_Game")
        self.assertEqual(self.sent, ["lost a level"])

    def test_a_held_back_gift_box_defeat_does_not_start_the_debounce_window(self):
        self.instance.set_mode("1")
        self.instance.set_gift_box_mode("0")
        self.lose_on("Level_Victory")
        self.advance(1)
        self.lose_on("Repair_Bonnie_Game")
        self.assertEqual(self.sent, ["lost a level"])

    def test_option_off_with_deathlink_off_sends_nothing_either_way(self):
        self.instance.set_gift_box_mode("0")
        self.lose_on("Level_Victory")
        self.advance(5)
        self.lose_on("Repair_Bonnie_Game")
        self.assertEqual(self.sent, [])
        self.assertTrue(any("DeathLink is off" in line for line in self.log()))

    def test_a_new_connect_goes_back_to_the_default_before_its_own_line_is_read(self):
        # DEATH_LINK_MODE is followed by DEATH_LINK_GIFT_BOX in every connect block; a client without the second line must not inherit "off"
        self.instance.set_mode("1")
        self.instance.set_gift_box_mode("0")
        self.instance.set_mode("1")
        self.lose_on("Level_Victory")
        self.assertEqual(self.sent, ["lost a level"])
        self.advance(5)
        self.instance.set_gift_box_mode("0")  # and the line that follows it applies
        self.lose_on("Level_Victory")
        self.assertEqual(len(self.sent), 1)

    def test_a_bad_value_changes_nothing_and_warns(self):
        self.instance.set_mode("1")
        self.instance.set_gift_box_mode("0")
        self.instance.set_gift_box_mode("maybe")
        self.lose_on("Level_Victory")
        self.assertEqual(self.sent, [])
        self.assertTrue(any("bad value" in line and "maybe" in line for line in self.log()), self.log())

    def test_an_unreadable_map_is_a_normal_defeat(self):
        self.instance.set_mode("1")
        self.instance.set_gift_box_mode("0")
        self.lose_on(None)  # current_map raises
        self.assertEqual(self.sent, ["lost a level"])
        self.advance(5)
        self.lose_on("")
        self.assertEqual(len(self.sent), 2)

    def test_receiving_is_untouched_by_the_option(self):
        self.instance.set_mode("1")
        self.instance.set_gift_box_mode("0")
        self.map[0] = "Level_Victory"
        self.assertFalse(self.instance.on_incoming("Bob::fell", False))  # not in a level, as before
        self.map[0] = "Repair_Bonnie_Game"
        self.assertTrue(self.instance.on_incoming("Bob::fell", False))  # inside a level, as before


class TestDeathLinkGiftBoxLine(LuaCase):
    """DEATH_LINK_GIFT_BOX 1|0 in the inbox reaches the mod, wired like main.lua, and does not disturb the DEATH_LINK_MODE / DEATHLINK lines."""

    def bridge(self, tmp, **handlers):
        env = self.lua.table(
            outbox_path=str(Path(tmp) / "ap_outbox.txt"), inbox_path=str(Path(tmp) / "ap_inbox.txt"), bridge_dir=tmp,
            emitted_location_names=self.lua.table(), on_item=lambda *a: None)
        for key, value in handlers.items():
            env[key] = value
        return self.load("bridge_io.lua")(env)

    def test_the_line_is_routed_to_its_own_handler_only(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ap_inbox.txt").write_text(
                "DEATH_LINK_MODE 1\nDEATH_LINK_GIFT_BOX 0\nDEATHLINK Bob::fell\n", encoding="utf-8")
            seen = []
            bridge = self.bridge(
                tmp,
                on_death_link_mode=lambda spec: seen.append(("mode", str(spec))),
                on_death_link_gift_box=lambda spec: seen.append(("gift", str(spec))),
                on_deathlink=lambda spec, is_replay: seen.append(("death", str(spec))))
            bridge.poll_inbox()
        self.assertEqual(seen, [("mode", "1"), ("gift", "0"), ("death", "Bob::fell")])

    def test_a_mod_without_a_handler_ignores_the_line(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ap_inbox.txt").write_text("DEATH_LINK_GIFT_BOX 0\n", encoding="utf-8")
            self.bridge(tmp).poll_inbox()  # must not raise

    def test_wired_like_main_lua_the_replayed_connect_block_decides_what_is_sent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ap_inbox.txt").write_text(
                "CONNECTED\nSESSION_SYNC old\nDEATH_LINK_MODE 1\nDEATH_LINK_GIFT_BOX 1\n"
                "CONNECTED\nSESSION_SYNC new\nDEATH_LINK_MODE 1\nDEATH_LINK_GIFT_BOX 0\nAPPLIED_ITEMS 0\n", encoding="utf-8")
            sent = []
            map_name = ["Level_Victory"]
            death_link = self.load("death_link.lua").init(self.lua.table(
                send=lambda cause: sent.append(cause), current_map=lambda: map_name[0]))
            self.lua.globals()["__loops"][1]()
            bridge = self.bridge(
                tmp,
                on_death_link_mode=lambda spec: death_link.set_mode(spec),
                on_death_link_gift_box=lambda spec: death_link.set_gift_box_mode(spec))
            bridge.poll_inbox()  # the launch replay: only the last block counts
            self.hooks()[LEVEL_DEFEAT](None)
            self.assertEqual(sent, [])
            map_name[0] = "Repair_Bonnie_Game"
            self.hooks()[LEVEL_DEFEAT](None)
            self.assertEqual(sent, ["lost a level"])

    def test_main_lua_wires_the_line_to_the_mod(self):
        main = (LIB.parent / "main.lua").read_text(encoding="utf-8")
        self.assertIn("on_death_link_gift_box", main)
        self.assertIn("death_link.set_gift_box_mode(spec)", main)


if __name__ == "__main__":
    unittest.main()
