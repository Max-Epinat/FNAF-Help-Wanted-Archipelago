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
        self.assertEqual(lines, ["[WATCH] Office_C:PlayJumpscare called (#1)", "[WATCH] Office_C:PlayJumpscare called (#2)",
                                 "[WATCH] Office_C:PlayJumpscare called (#3)", "[WATCH] Office_C:PlayJumpscare called (#50)",
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
        self.assertIn("[WATCH] JumpScare_C:Stop called (#1)", self.log())
        self.assertEqual(tools.hook_class("/Game/Blueprints/JumpScare.JumpScare_C"), 0)  # never twice
        self.assertEqual(tools.hook_class("/Game/Nope.Nope_C"), 0)
        self.assertEqual(tools.hook_class(""), 0)

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


if __name__ == "__main__":
    unittest.main()
