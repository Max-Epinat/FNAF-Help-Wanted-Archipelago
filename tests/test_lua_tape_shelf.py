"""tape_shelf.lua: each Glitch Tape item is one log, and the tape room shows exactly the logs received (unique tapes, 2026-10-26).

How the room works (read from the game's Blueprint code, docs/game-research.md "The tape room"): 16 shelf slots (AquiredLog_C), slot n has
LogNumber n and plays log n; when the room loads a slot stays only if LogNumber <= the tape count (derived_counters.lua makes that count the
number of tape items received), else it removes itself. A slot that stays then runs SetupLog, which sets its label widget's Text (0 by default)
to its LogNumber. The mod gives the K slots that stayed the K logs received, in order: no gaps.
VERIFIED in game once (2026-10-26 probe, flat mode): setting LogNumber + the label widget's Text and calling its PreConstruct(false) again
relabelled a slot (TAPE #2 -> TAPE #5) and it played log 5; ~10 s after the load FindAllOf still returned the 13 slots that removed
themselves, without a label widget object. The user saw the whole feature work in a real room (2026-10-26) with the relabel ~5 s after entry.
Faster relabel (2026-10-27, HYPOTHESIS until seen in game): the shelf job alone may run during the 0.4.2 pause, only while the map the
diagnostics last saw is the tape room, at least 0.5 s after the room was noticed, every 0.25 s for 2 s at most. Safety rule: a slot is touched
only when its label already shows its own number (SetupLog ran, so the slot already decided to stay); relabelling a slot before that decision
would make it remove itself and the tape would be lost.
The game is stubbed: these tests check the module's decisions, not what the game does with them.
"""

import sys
import unittest
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tests.test_lua_logic import LIB, LuaCase  # noqa: E402

ROOM = "Cassete_DarkRoom"
HUB = "Main_Menu_With_Showtime"
FIRST_TAPE_ID = 101000061  # "Glitch Tape #01 (Intro)": item code 61 + ITEM_OFFSET 101000000; log n = id - 101000060
OLD_TAPE_ID = 101000001    # the retired "Glitch Tape" item (code 1) of rooms generated before unique tapes

SLOTS = r"""
-- A shelf slot as the game shows it: LogNumber, a label widget component. Only slots the game kept have a label widget object, and its Text
-- is 0 until the slot's SetupLog ran (ready = false), then the slot's own number.
function __slot(n, labelled, ready)
    local widget = nil
    if labelled then
        widget = { Text = (ready == false) and 0 or n, pre = 0 }
        function widget:IsValid() return true end
        function widget:PreConstruct(design_time) self.pre = self.pre + 1; self.design_time = design_time end
    end
    local component = {}
    function component:GetUserWidgetObject()
        if widget then return widget end
        return { IsValid = function() return false end }
    end
    local slot = { LogNumber = n, Widget = component, label = widget, name = "AquiredLog" .. (15 + n) }
    function slot:IsValid() return true end
    function slot:GetFullName()
        return "AquiredLog_C /Game/Scenes/Cassete_DarkRoom.Cassete_DarkRoom:PersistentLevel." .. self.name
    end
    return slot
end
-- the room after a load with K tapes: 16 slots (the game lists them last to first), labels only on 1..K
function __shelf(k)
    local list = {}
    for n = 16, 1, -1 do list[#list + 1] = __slot(n, n <= k) end
    return list
end
-- the slot finishes its SetupLog: the label shows its number
function __setup(slot) slot.label.Text = slot.LogNumber end
"""


def tape_id(log):
    return FIRST_TAPE_ID + log - 1


class ShelfCase(LuaCase):
    """The module alone; the scheduler is simulated: the job runs only while the map is the tape room, with the visit number."""

    def setUp(self):
        super().setUp()
        self.lua.execute(SLOTS)
        self.module = self.load("tape_shelf.lua")
        self.map = [HUB]
        self.visit = 0
        self.shelf = self.lua.eval("__shelf(0)")
        self.finds = 0
        self.jobs = []

        def find_all(class_name):
            self.finds += 1
            self.assertEqual(str(class_name), "AquiredLog_C")
            return self.shelf

        def every_in_tape_room(name, ms, fn):
            self.jobs.append((str(name), ms, fn))

        self.instance = self.module.init(self.lua.table(every_in_tape_room=every_in_tape_room, find_all=find_all))

    # --- helpers -------------------------------------------------------------------------------------------------------------
    def tick(self, times=1):
        """Scheduler ticks: the job runs only in the tape room (game_thread.every_in_tape_room)."""
        for _ in range(times):
            if self.map[0] == ROOM:
                for _, _, fn in self.jobs:
                    fn(self.visit)

    def wait_ticks(self):
        return self.module.WAIT_RUNS

    def connect(self, logs, session="seed_slot", extra=()):
        self.instance.on_session_sync(session)
        self.instance.on_snapshot(",".join([str(tape_id(n)) for n in logs] + [str(i) for i in extra]))

    def enter_room(self, k):
        self.shelf = self.lua.eval("__shelf")(k)
        self.map[0] = ROOM
        self.visit += 1

    def leave(self):
        self.map[0] = HUB

    def relabel_now(self):
        """The ticks up to and including the first pass."""
        self.tick(self.wait_ticks() + 1)

    def slot(self, original):
        for i in range(1, len(self.shelf) + 1):
            if self.shelf[i].name == "AquiredLog%d" % (15 + original):
                return self.shelf[i]
        raise KeyError(original)

    def numbers(self, k):
        """(LogNumber, label Text) of the slots that were 1..k when the room loaded."""
        return [(self.slot(n).LogNumber, self.slot(n).label.Text) for n in range(1, k + 1)]


class TestPure(ShelfCase):
    def test_log_of_every_tape_item(self):
        for log in range(1, 17):
            self.assertEqual(self.module.log_of_item(tape_id(log)), log)
        for other in (OLD_TAPE_ID, FIRST_TAPE_ID - 1, FIRST_TAPE_ID + 16, 101000011, 101000060):
            self.assertIsNone(self.module.log_of_item(other))

    def test_received_logs_are_sorted_and_each_log_counts_once(self):
        logs, old, err = self.module.received_logs("%d,%d,101000011,%d,%d" % (tape_id(9), tape_id(2), tape_id(9), tape_id(14)))
        self.assertEqual(list(logs.values()), [2, 9, 14])
        self.assertEqual((old, err), (0, None))

    def test_the_old_glitch_tape_item_is_no_log(self):
        logs, old, err = self.module.received_logs("%d,%d,%d" % (OLD_TAPE_ID, OLD_TAPE_ID, tape_id(3)))
        self.assertEqual(list(logs.values()), [3])
        self.assertEqual((old, err), (2, None))

    def test_a_bad_list_is_an_error(self):
        logs, old, err = self.module.received_logs("1,x")
        self.assertIsNone(logs)
        self.assertIn("bad item id", str(err))
        self.assertEqual(list(self.module.received_logs("")[0].values()), [])
        self.assertEqual(list(self.module.received_logs(None)[0].values()), [])

    def test_the_schedule_is_short(self):
        """Every 0.25 s; wait 2 runs (at least 0.5 s after the room was noticed), then at most 8 passes (2 s)."""
        self.assertEqual(self.jobs[0][1], 250)
        self.assertEqual(self.module.WAIT_RUNS, 2)
        self.assertEqual(self.module.PASSES, 8)


class TestRelabel(ShelfCase):
    def test_the_kept_slots_get_the_received_logs_in_order_with_no_gaps(self):
        self.connect([14, 2, 9])
        self.enter_room(3)
        self.relabel_now()
        self.assertEqual(self.numbers(3), [(2, 2), (9, 9), (14, 14)])
        for n in (1, 2, 3):
            self.assertEqual(self.slot(n).label.pre, 1)
            self.assertFalse(self.slot(n).label.design_time)

    def test_nothing_before_the_minimum_wait(self):
        self.connect([14, 2, 9])
        self.enter_room(3)
        self.tick(self.wait_ticks())
        self.assertEqual(self.finds, 0)
        self.assertEqual(self.numbers(3), [(1, 1), (2, 2), (3, 3)])

    def test_only_labelled_slots_are_touched(self):
        """The slots the game removes still show up for a while (VERIFIED 2026-10-26), without a label widget object."""
        self.connect([5, 7])
        self.enter_room(2)
        self.tick(20)
        for n in range(3, 17):
            self.assertEqual(self.slot(n).LogNumber, n)
            self.assertIsNone(self.slot(n).label)
        self.assertEqual(self.numbers(2), [(5, 5), (7, 7)])

    def test_a_slot_without_a_label_is_never_touched_even_when_a_log_waits_for_its_place(self):
        """Four logs, but slots 3 and 4 have no label object (yet): they keep their number, however long the passes go on. The game may hand
        back either nothing or an invalid object for a missing label: slot 3 gives nil, slot 4 an invalid object."""
        self.connect([2, 5, 9, 12])
        self.enter_room(2)  # slots 1 and 2 labelled, slot 3 and up without a label
        self.lua.execute("function __no_object(slot) slot.Widget = { GetUserWidgetObject = function() return nil end } end")
        self.lua.globals()["__no_object"](self.slot(3))
        self.tick(30)
        self.assertEqual(self.numbers(2), [(2, 2), (5, 5)])
        self.assertEqual((self.slot(3).LogNumber, self.slot(4).LogNumber), (3, 4))

    def test_a_slot_whose_label_does_not_show_its_own_number_is_never_touched(self):
        """Text 0 = its SetupLog has not run: the slot has not decided yet whether it stays. Touching it could make it remove itself."""
        self.connect([5, 7])
        self.shelf = self.lua.eval("function() local l = __shelf(0); for i, s in ipairs(l) do if s.LogNumber <= 2 then "
                                   "l[i] = __slot(s.LogNumber, true, false) end end; return l end")()
        self.map[0] = ROOM
        self.visit += 1
        self.tick(20)
        self.assertEqual([(self.slot(n).LogNumber, self.slot(n).label.Text, self.slot(n).label.pre) for n in (1, 2)], [(1, 0, 0), (2, 0, 0)])
        self.slot(1).label.Text = 4  # any number that is not its own
        self.instance.on_session_sync("seed_slot_2")
        self.instance.on_snapshot("%d,%d" % (tape_id(5), tape_id(7)))
        self.leave()
        self.map[0] = ROOM
        self.visit += 1
        self.tick(20)
        self.assertEqual((self.slot(1).LogNumber, self.slot(1).label.pre), (1, 0))

    def test_a_slot_that_finishes_its_setup_during_the_passes_is_relabelled(self):
        self.connect([6, 9])
        self.shelf = self.lua.eval("function() local l = __shelf(1); for i, s in ipairs(l) do if s.LogNumber == 2 then "
                                   "l[i] = __slot(2, true, false) end end; return l end")()
        self.map[0] = ROOM
        self.visit += 1
        self.relabel_now()
        self.assertEqual((self.slot(1).LogNumber, self.slot(2).LogNumber), (6, 2))
        self.lua.globals()["__setup"](self.slot(2))
        self.tick()
        self.assertEqual(self.numbers(2), [(6, 6), (9, 9)])
        self.assertEqual(self.slot(1).label.pre, 1)  # slot 1 was not redone

    def test_each_slot_gets_the_log_of_its_own_place(self):
        """Slot n gets the n-th log received, whatever order the game lists the slots in and whichever slot is ready first."""
        self.connect([4, 11, 16, 1])
        self.shelf = self.lua.eval("function() local l = __shelf(4); for i, s in ipairs(l) do if s.LogNumber <= 2 then "
                                   "l[i] = __slot(s.LogNumber, true, false) end end; return l end")()
        self.map[0] = ROOM
        self.visit += 1
        self.relabel_now()
        self.assertEqual([self.slot(n).LogNumber for n in (1, 2, 3, 4)], [1, 2, 11, 16])
        self.lua.globals()["__setup"](self.slot(2))
        self.tick()
        self.lua.globals()["__setup"](self.slot(1))
        self.tick()
        self.assertEqual(self.numbers(4), [(1, 1), (4, 4), (11, 11), (16, 16)])

    def test_a_slot_already_showing_its_log_is_left_alone(self):
        self.connect([1, 2, 8])
        self.enter_room(3)
        self.relabel_now()
        self.assertEqual(self.numbers(3), [(1, 1), (2, 2), (8, 8)])
        self.assertEqual([self.slot(n).label.pre for n in (1, 2, 3)], [0, 0, 1])

    def test_a_slot_beyond_the_logs_received_is_left_alone(self):
        """More kept slots than logs only happens with a forced count (ap_counter_force): the extra slots keep their number."""
        self.connect([5])
        self.enter_room(3)
        self.tick(20)
        self.assertEqual(self.numbers(3), [(5, 5), (2, 2), (3, 3)])

    def test_the_passes_stop_once_every_log_is_on_the_shelf(self):
        self.connect([6, 9])
        self.enter_room(2)
        self.relabel_now()
        finds = self.finds
        self.tick(20)
        self.assertEqual(self.finds, finds)

    def test_the_passes_stop_at_the_cap(self):
        self.connect([6, 9])
        self.shelf = self.lua.eval("function() local l = __shelf(1); for i, s in ipairs(l) do if s.LogNumber == 2 then "
                                   "l[i] = __slot(2, true, false) end end; return l end")()  # slot 2 never gets ready
        self.map[0] = ROOM
        self.visit += 1
        self.tick(self.wait_ticks() + self.module.PASSES)
        self.assertEqual(self.finds, self.module.PASSES)
        self.tick(30)
        self.assertEqual(self.finds, self.module.PASSES)
        self.assertTrue(any("[ARCHI] Tape shelf" in line and "1 of 2" in line for line in self.log()), self.log())

    def test_a_new_room_visit_relabels_again(self):
        self.connect([6, 9])
        self.enter_room(2)
        self.tick(30)
        self.leave()
        self.tick()
        self.connect([3, 6, 9])
        self.enter_room(3)  # new actors, original numbers again
        self.relabel_now()
        self.assertEqual(self.numbers(3), [(3, 3), (6, 6), (9, 9)])

    def test_the_snapshot_that_arrives_while_in_the_room_is_used(self):
        self.instance.on_session_sync("seed_slot")
        self.enter_room(2)
        self.tick(4)  # no item list yet: nothing to do, no pass used
        self.assertEqual(self.numbers(2), [(1, 1), (2, 2)])
        self.instance.on_snapshot("%d,%d" % (tape_id(3), tape_id(12)))
        self.tick()
        self.assertEqual(self.numbers(2), [(3, 3), (12, 12)])

    def test_the_relabel_is_logged_once(self):
        self.connect([2, 9])
        self.enter_room(2)
        self.tick(20)
        lines = [line for line in self.log() if "[ARCHI] Tape shelf" in line]
        self.assertEqual(len(lines), 1, self.log())
        self.assertIn("2 of 2 log(s)", lines[0])


class TestNothingOutsideItsCase(ShelfCase):
    def test_the_job_is_only_handed_to_the_tape_room_scheduler(self):
        self.assertEqual([name for name, _, _ in self.jobs], ["tape_shelf"])
        source = (LIB / "tape_shelf.lua").read_text(encoding="utf-8")
        code = "\n".join(line.split("--")[0] for line in source.splitlines())
        self.assertNotIn("every(", code.replace("every_in_tape_room(", ""))

    def test_nothing_happens_without_a_session(self):
        self.instance.on_snapshot("%d,%d" % (tape_id(5), tape_id(9)))
        self.enter_room(2)
        self.tick(20)
        self.assertEqual(self.numbers(2), [(1, 1), (2, 2)])

    def test_nothing_happens_when_the_tapes_are_not_randomized(self):
        self.connect([5, 9])
        self.instance.set_randomized(False)
        self.enter_room(2)
        self.tick(20)
        self.assertEqual(self.numbers(2), [(1, 1), (2, 2)])
        self.instance.on_session_sync("seed_slot")  # every connect block starts randomized until RANDOMIZED_GROUPS says otherwise
        self.instance.on_snapshot("%d,%d" % (tape_id(5), tape_id(9)))
        self.leave()
        self.enter_room(2)
        self.relabel_now()
        self.assertEqual(self.numbers(2), [(5, 5), (9, 9)])

    def test_a_new_session_forgets_the_old_logs(self):
        self.connect([5, 9], session="seed_a")
        self.instance.on_session_sync("seed_b")
        self.enter_room(2)
        self.tick(20)
        self.assertEqual(self.numbers(2), [(1, 1), (2, 2)])

    def test_a_bad_snapshot_keeps_the_last_good_logs(self):
        self.connect([5, 9])
        self.instance.on_snapshot("101000061,oops")
        self.enter_room(2)
        self.relabel_now()
        self.assertEqual(self.numbers(2), [(5, 5), (9, 9)])
        self.assertTrue(any("bad snapshot ignored" in line for line in self.log()))

    def test_a_slot_that_breaks_does_not_stop_the_others(self):
        self.connect([5, 9])
        self.enter_room(2)
        self.lua.execute("function __break(slot) slot.label.PreConstruct = function() error('boom') end end")
        self.lua.globals()["__break"](self.slot(1))
        self.relabel_now()
        self.assertEqual(self.slot(2).LogNumber, 9)
        self.assertTrue(any("[WARN]" in line and "Tape shelf" in line for line in self.log()), self.log())


class TestOldGlitchTapeItem(ShelfCase):
    """Rooms generated before unique tapes hand out the retired "Glitch Tape" (id 101000001): ignored, one clear line, no crash."""

    def test_the_old_item_is_ignored_with_one_log_line(self):
        self.connect([], extra=(OLD_TAPE_ID, OLD_TAPE_ID, 101000011))
        self.instance.on_snapshot("%d,%d,%d" % (OLD_TAPE_ID, OLD_TAPE_ID, OLD_TAPE_ID))
        self.enter_room(0)
        self.tick(20)
        lines = [line for line in self.log() if str(OLD_TAPE_ID) in line]
        self.assertEqual(len(lines), 1, self.log())
        self.assertIn("regenerate", lines[0].lower())
        self.assertTrue(lines[0].startswith("[WARN]"))
        self.assertEqual(self.instance.status().count("logs=none"), 1)

    def test_the_old_item_next_to_new_ones_changes_nothing(self):
        self.connect([4], extra=(OLD_TAPE_ID,))
        self.enter_room(1)
        self.relabel_now()
        self.assertEqual(self.numbers(1), [(4, 4)])

    def test_the_line_comes_again_for_another_session(self):
        self.connect([], session="seed_a", extra=(OLD_TAPE_ID,))
        self.connect([], session="seed_b", extra=(OLD_TAPE_ID,))
        self.assertEqual(len([line for line in self.log() if str(OLD_TAPE_ID) in line]), 2)


class TestTheRealScheduler(LuaCase):
    """With the real game_thread.lua: the shelf job may run during the 0.4.2 pause, but only in the tape room and only itself; every other job
    is still held for the full pause, and in the hub nothing changes."""

    def setUp(self):
        super().setUp()
        self.lua.execute(SLOTS)
        self.clock = [100.0]
        self.loops, self.queue = [], []
        gt_module = self.load("game_thread.lua")
        self.gt_module = gt_module
        self.quiet = gt_module.QUIET_SECONDS
        # now() counts whole seconds like the real os.time; the loops fire every quarter of a second
        self.gt = gt_module.init(self.lua.table(
            now=lambda: int(self.clock[0]), in_game_thread=lambda: True,
            loop_async=lambda ms, fn: self.loops.append((ms, fn)), run_on_game_thread=lambda body: self.queue.append(body)))
        self.map = ["TitleMain"]
        self.gt.start_diagnostics(lambda: self.map[0])
        self.other = []
        self.gt.every("other", 1000, lambda: self.other.append(self.clock[0]))
        self.shelf = self.lua.eval("__shelf")(2)
        self.finds = 0

        def find_all(_):
            self.finds += 1
            return self.shelf

        shelf_module = self.load("tape_shelf.lua")
        self.wait_runs = shelf_module.WAIT_RUNS
        self.instance = shelf_module.init(self.lua.table(every_in_tape_room=self.gt.every_in_tape_room, find_all=find_all))
        self.instance.on_session_sync("seed_slot")
        self.instance.on_snapshot("%d,%d" % (tape_id(7), tape_id(13)))
        self.quarter()  # the diagnostics see the first map

    def quarter(self):
        """A quarter of a second: every loop fires once (the 1 s loops too: firing them more often only makes the test stricter), then the
        game thread runs what was queued."""
        for _, fn in self.loops:
            fn()
        queue, self.queue = self.queue, []
        for body in queue:
            body()
        self.clock[0] += 0.25

    def first_slot(self):
        for i in range(1, 17):
            if self.shelf[i].name == "AquiredLog16":
                return self.shelf[i]

    def go(self, map_name):
        self.map[0] = map_name

    def test_the_shelf_job_is_registered_every_quarter_second(self):
        self.assertIn(250, [ms for ms, _ in self.loops])

    def test_in_the_tape_room_it_runs_during_the_pause_after_the_minimum_wait(self):
        self.go(HUB)
        for _ in range(4 * (self.quiet + 1)):
            self.quarter()
        self.go(ROOM)
        quarters = 0
        while self.first_slot().LogNumber != 7:
            self.quarter()
            quarters += 1
            self.assertLess(quarters, 4 * self.quiet, "no relabel during the pause")
        # the room is noticed on the first quarter (the diagnostics tick), the shelf job then waits WAIT_RUNS runs: >= 0.5 s
        self.assertGreaterEqual(quarters, 1 + self.wait_runs)
        self.assertLessEqual(quarters, 1 + self.wait_runs + 1)

    def test_every_other_job_is_still_held_for_the_full_pause(self):
        self.go(ROOM)
        self.quarter()  # the diagnostics see the change: the pause starts
        start = self.clock[0]
        self.other.clear()
        while not self.other:
            self.quarter()
            self.assertLess(self.clock[0] - start, self.quiet + 2)
        # the pause as 0.4.2 made it: QUIET_SECONDS on a whole-second clock, so 4 to 5 s after the change was noticed (unchanged)
        self.assertGreaterEqual(self.other[0] - start, self.quiet - 1)
        self.assertEqual(self.first_slot().LogNumber, 7)  # the shelf did its work long before

    def test_nothing_runs_in_the_hub_or_any_other_map(self):
        for map_name in (HUB, "Gallery", "Repair_Bonnie_Game", "", "TitleMain", "Level_Victory"):
            self.go(map_name)
            for _ in range(4 * (self.quiet + 2)):
                self.quarter()
        self.assertEqual(self.finds, 0)
        self.assertEqual(self.first_slot().LogNumber, 1)

    def test_a_second_visit_is_a_new_visit(self):
        self.go(ROOM)
        for _ in range(12):
            self.quarter()
        self.assertEqual(self.first_slot().LogNumber, 7)
        self.go(HUB)
        for _ in range(4 * (self.quiet + 1)):
            self.quarter()
        self.shelf = self.lua.eval("__shelf")(2)  # the room is loaded again: new slots
        self.go(ROOM)
        for _ in range(12):
            self.quarter()
        self.assertEqual(self.first_slot().LogNumber, 7)

    def test_without_the_diagnostics_the_shelf_never_runs(self):
        gt = self.gt_module.init(self.lua.table(now=lambda: int(self.clock[0]), in_game_thread=lambda: True,
                                                loop_async=lambda ms, fn: self.loops.append((ms, fn)),
                                                run_on_game_thread=lambda body: self.queue.append(body)))
        runs = []
        gt.every_in_tape_room("probe", 250, lambda visit: runs.append(visit))
        self.go(ROOM)
        for _ in range(20):
            self.quarter()
        self.assertEqual(runs, [])

    def test_the_exemption_belongs_to_the_shelf_alone(self):
        scripts = LIB.parent
        users = []
        for path in [scripts / "main.lua"] + sorted(LIB.glob("*.lua")):
            code = "\n".join(line.split("--")[0] for line in path.read_text(encoding="utf-8").splitlines())
            if "every_in_tape_room" in code and path.name != "game_thread.lua":
                users.append(path.name)
        self.assertEqual(sorted(set(users)), ["main.lua", "tape_shelf.lua"])  # main.lua only hands it to the shelf
        main = (scripts / "main.lua").read_text(encoding="utf-8")
        self.assertEqual(main.count("every_in_tape_room"), 2)  # the one line that hands it to the shelf
        self.assertEqual(main.count("every_in_tape_room = game_thread.every_in_tape_room"), 1)
        source = (LIB / "game_thread.lua").read_text(encoding="utf-8")
        self.assertIn('GameThread.TAPE_ROOM_MAP = "Cassete_DarkRoom"', source)
        self.assertEqual(source.count("{ always = true }"), 1)  # still only the diagnostics run in every map during the pause


class TestWiring(unittest.TestCase):
    def test_main_lua_loads_the_shelf_and_feeds_it(self):
        main = (LIB.parent / "main.lua").read_text(encoding="utf-8")
        for call in ("tape_shelf.lua", "tape_shelf.on_session_sync(session_id)", "tape_shelf.on_snapshot(spec)",
                     "tape_shelf.set_randomized(groups.tapes)", "every_in_tape_room = game_thread.every_in_tape_room"):
            self.assertIn(call, main)

    def test_the_tape_count_counts_the_sixteen_tape_items(self):
        source = (LIB / "derived_counters.lua").read_text(encoding="utf-8")
        code = "\n".join(line.split("--")[0] for line in source.splitlines())
        self.assertNotIn(str(OLD_TAPE_ID), code)  # no code line counts the retired id
        self.assertIn("101000061", code)


if __name__ == "__main__":
    unittest.main()
