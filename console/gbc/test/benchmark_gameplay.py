"""Benchmark controller-only gameplay at the fixed two-display-frame deadline.

Levels are numbered 1..54. Each level/scenario starts in a fresh emulator and
is selected through Driver's real menu/button APIs. No guest RAM, registers,
save states, or completion flags are injected. Ordinary death/finish ends a
case; it never triggers a retry. --steps is a maximum, not a survival claim.

Timing follows profile_play: joypad entry through the first main-loop vsync
after the completed update, including presentation/physics/object/clock work
and excluding idle wait. The limit is always 280896 SM83 T-cycles (two CGB
double-speed display frames), regardless of the measured ROM's performance.

The fidelity boundary is physics_step's actual stack return address, after
the 109-byte Bike and 52-byte gbc_bike export, BEFORE the caller advances its
clock or checks objects. A second snapshot at the completed-update vsync
includes those clock/object/death/finish effects. Both snapshots are compared
byte-for-byte; absolute emulator cycles/frames and timing counters are not.

Example (from console/gbc):
  .venv/bin/python test/benchmark_gameplay.py --rom build/elma-gbc-v0.90-8m.gbc \
    --gen build/gen-8m --out build/gameplay-baseline --levels 1,44 --steps 100 \
    --scenario neutral gas seeded
  # Repeat with a candidate ROM and --reference build/gameplay-baseline/report.json

report.json is always written on runtime/timing/reference failure. The gzip
JSON-lines trace contains one metadata line followed by one line per case;
either the report or trace may be supplied as --reference. Timing failures
do not truncate the requested corpus, and there is no relaxed-budget option.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import random
import sys
import time
import traceback

# Importable helpers only; several other test scripts parse arguments at import.
sys.dont_write_bytecode = True
from play import BASE, DEAD, Driver, FINISHED, MENU, RIDING
from profile_play import Profiler


SCHEMA = 1
CONTROLLER_VERSION = 1
DISPLAY_CYCLES = 140448
UPDATE_BUDGET = 280896
LEVEL_COUNT = 54
SCENARIOS = ("neutral", "gas", "brake", "seeded")
STATE_NAMES = {0: "riding", 1: "dead", 2: "finished", 3: "paused", 4: "menu"}
STATE_FIELDS = ("step", "bike_hex", "gbc_bike_hex", "state", "apples_left", "time_frames")
GDMA_LIMITATION = ("PyBoy 2.9.0 does not charge the 64 double-speed T-cycle CPU stall per GDMA block. "
                   "The additive surcharge below counts world_upload_tile commands only; it is a margin estimate, "
                   "not a hardware timing simulation, and does not reproduce shifted LCD/interrupt scheduling.")


def selected_levels(value):
    """Parse a bounded, one-based list such as 1,4-8,44 or all."""
    if value.lower() == "all":
        return list(range(1, LEVEL_COUNT + 1))
    result = []
    try:
        for part in value.split(","):
            ends = part.split("-")
            if len(ends) not in (1, 2):
                raise ValueError
            first, last = int(ends[0]), int(ends[-1])
            if not 1 <= first <= last <= LEVEL_COUNT:
                raise ValueError
            for level in range(first, last + 1):
                if level not in result:
                    result.append(level)
    except ValueError:
        raise argparse.ArgumentTypeError("levels must be all or numbers/ranges within 1..54") from None
    if not result:
        raise argparse.ArgumentTypeError("select at least one level")
    return result


def bounded_steps(value):
    try:
        count = int(value)
    except ValueError:
        count = 0
    if not 1 <= count <= 10000:
        raise argparse.ArgumentTypeError("steps must be within 1..10000")
    return count


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def statistics(values):
    ordered = sorted(values)
    return {"count": len(ordered), "min_cycles": ordered[0] if ordered else None,
            "mean_cycles": sum(ordered) / len(ordered) if ordered else None,
            "p95_cycles": ordered[math.ceil(.95 * len(ordered)) - 1] if ordered else None,
            "max_cycles": ordered[-1] if ordered else None}


def controller_plan(scenario, seed, level, count):
    # The sequence depends only on these settings, never on host frame timing.
    rng = random.Random(f"gbc-gameplay-v{CONTROLLER_VERSION}:{seed}:{level}")
    plan = []
    for index in range(count):
        keys = set()
        if scenario == "gas":
            keys.add("a")
        elif scenario == "brake":
            keys.add("a" if index < min(60, max(1, count // 3)) else "b")
        elif scenario == "seeded":
            drive = rng.randrange(8)
            if drive < 5:
                keys.add("a")
            elif drive == 5:
                keys.add("b")
            if rng.randrange(8) == 0:
                keys.add(rng.choice(("left", "right")))
            if rng.randrange(40) == 0:
                keys.add("up")
        plan.append(sorted(keys))
    return plan


class GameplayProfiler(Profiler):
    """Extend the existing exact-cycle/stack observer with fidelity records."""

    def __init__(self, driver, level, plan):
        self.level = level
        self.plan = plan
        self.initial = None
        self.base_steps = None
        self.physics = []
        self.started_updates = 0
        self.finished = False
        self.end_reason = None
        self.errors = []
        self.internal_vsyncs = 0
        self.irq_entry_repeats = Counter()
        super().__init__(driver)
        address = self.symbols["_ph_step"]
        self.p.hook_register(address >> 16, address & 65535, self._core_entry, self)
        self.gdma_sites = self.observe_gdma()

    def observe_gdma(self):
        start = self.symbols.get("_world_upload_tile")
        if start is None:
            return []
        bank, address = start >> 16, start & 65535
        following = [value & 65535 for value in self.symbols.values()
                     if value >> 16 == bank and address < (value & 65535) < 0x8000]
        if not following:
            return []
        end = min(following)
        code = self.d.rom_far((bank, address), end - address)
        # Walk instruction boundaries instead of hooking an accidental E0 55
        # inside an immediate argument. This bounded function has no data table.
        three = {0x01, 0x08, 0x11, 0x21, 0x31, 0xc2, 0xc3, 0xc4, 0xca, 0xcc,
                 0xcd, 0xd2, 0xd4, 0xda, 0xdc, 0xea, 0xfa}
        two = {0x06, 0x0e, 0x10, 0x16, 0x18, 0x1e, 0x20, 0x26, 0x28, 0x2e,
               0x30, 0x36, 0x38, 0x3e, 0xc6, 0xcb, 0xce, 0xd6, 0xde, 0xe0,
               0xe6, 0xe8, 0xee, 0xf0, 0xf6, 0xf8, 0xfe}
        sites, offset = [], 0
        while offset < len(code):
            if code[offset:offset + 2] == b"\xe0\x55" or code[offset:offset + 3] == b"\xea\x55\xff":
                self.p.hook_register(bank, address + offset, self._gdma_launch, self)
                sites.append({"bank": bank, "address": address + offset})
            offset += 3 if code[offset] in three else 2 if code[offset] in two else 1
        return sites

    @staticmethod
    def _gdma_launch(profiler):
        if profiler.active is None:
            return
        command = profiler.p.register_file.A
        if command & 128:
            profiler.active["hdma_commands"] += 1
        else:
            profiler.active["gdma_commands"] += 1
            profiler.active["gdma_blocks"] += (command & 127) + 1

    def snapshot(self):
        d = self.d
        internal = self.symbols["_Bike"]
        public = self.symbols["_gbc_bike"]
        steps = d.word("game_steps")
        return {"step": (steps - self.base_steps) & 65535,
                "game_steps": steps, "game_frames": d.word("game_frames"),
                "bike_hex": bytes(self.p.memory[internal:internal + 109]).hex(),
                "gbc_bike_hex": bytes(self.p.memory[public:public + 52]).hex(),
                "state": d.byte("game_state"), "apples_left": d.byte("game_apples_left"),
                "time_frames": d.time_frames(), "overruns": d.word("game_overruns"),
                "camera": [d.word("game_camera_x"), d.word("game_camera_y")]}

    def enter(self, name):
        # Ignore menu/loading work; only a RIDING input sample opens a case update.
        if self.active is None:
            return
        if self.entry_repeated(name):
            return
        super().enter(name)
        self.stack[-1]["update"] = self.active["index"]

    def entry_repeated(self, name):
        # PyBoy can observe a hooked first instruction before servicing a
        # pending IRQ, then observe the same instruction again on IRQ return.
        # An unreturned call at the same stack depth is still that one call.
        if (self.stack and self.stack[-1]["name"] == name
                and self.stack[-1]["return_sp"] == (self.p.register_file.SP + 2) & 65535):
            self.irq_entry_repeats[name] += 1
            return True
        return False

    @staticmethod
    def _input_entry(profiler):
        d = profiler.d
        Driver._input_entry(d)
        if profiler.finished or d.byte("game_state") != RIDING:
            return
        if d.level_index() + 1 != profiler.level or not d.byte("game_ready"):
            return
        if profiler.active is not None:
            raise AssertionError("new controller sample before the preceding update closed")
        if profiler.initial is None:
            profiler.base_steps = d.word("game_steps")
            profiler.initial = profiler.snapshot()
        index = profiler.started_updates
        if index >= len(profiler.plan):
            raise AssertionError("more riding updates than the requested step limit")
        # Start is held only to launch the menu selection, not a gameplay control.
        keys = sorted(d.held - {"start"})
        if keys != profiler.plan[index]:
            profiler.errors.append(f"update {index + 1}: sampled buttons {keys} != {profiler.plan[index]}")
        profiler.active = {"index": index + 1, "start_cycle": profiler.p._cycles(),
                           "frame": profiler.p.frame_count, "buttons": keys,
                           "steps_before": d.word("game_steps"),
                           "frames_before": d.word("game_frames"),
                           "overruns_before": d.word("game_overruns"), "physics": [],
                           "gdma_commands": 0, "gdma_blocks": 0, "hdma_commands": 0}
        profiler.started_updates += 1

    @staticmethod
    def _physics_entry(profiler):
        if profiler.entry_repeated("_physics_step"):
            return
        Driver._physics_entry(profiler.d)
        if profiler.active is None:
            return
        profiler.physics_count += 1
        profiler.enter("_physics_step")
        # GBDK BANKED stack ABI: return PC/banking frame occupies six bytes.
        # ph_step below independently observes the translated register argument.
        argument = profiler.p.memory[(profiler.p.register_file.SP + 6) & 65535]
        profiler.stack[-1]["physics_input"] = argument
        profiler.stack[-1]["core_input"] = None

    @staticmethod
    def _core_entry(profiler):
        if profiler.active is None:
            return
        calls = [call for call in profiler.stack if call["name"] == "_physics_step"]
        if len(calls) != 1 or calls[0]["core_input"] is not None:
            raise AssertionError("ph_step did not belong to one observed physics_step")
        # The unbanked SM83 SDCC register ABI passes uint8_t input in A.
        calls[0]["core_input"] = profiler.p.register_file.A

    @staticmethod
    def _return(context):
        profiler, _ = context
        before = len(profiler.records)
        Profiler._return(context)
        for call in profiler.records[before:]:
            if call["name"] != "_physics_step":
                continue
            argument = call["physics_input"]
            translated = (argument & 3) | ((argument & 4) << 1) | ((argument & 8) >> 1)
            if call["core_input"] != translated:
                profiler.errors.append(f"physics {len(profiler.physics) + 1}: input ABI/translation mismatch")
            record = {"index": len(profiler.physics) + 1, "update": call["update"],
                      "physics_input": argument, "core_input": call["core_input"],
                      "start_cycle": call["start_cycle"], "end_cycle": call["end_cycle"],
                      "cycles": call["cycles"], "frame": call["frame"],
                      "return_state": profiler.snapshot()}
            profiler.physics.append(record)
            profiler.active["physics"].append(record["index"])

    @staticmethod
    def _vsync_entry(profiler):
        if profiler.active is None:
            return
        d = profiler.d
        update = profiler.active
        if profiler.stack or d.word("game_frames") == update["frames_before"]:
            # An internal presentation wait is still active work, not loop idle.
            profiler.internal_vsyncs += 1
            return
        update["end_cycle"] = profiler.p._cycles()
        update["end_frame"] = profiler.p.frame_count
        update["cycles"] = update["end_cycle"] - update["start_cycle"]
        update["gdma_surcharge_cycles"] = update["gdma_blocks"] * 64
        update["cycles_with_gdma_surcharge"] = update["cycles"] + update["gdma_surcharge_cycles"]
        update["overruns_after"] = d.word("game_overruns")
        update["state_after"] = profiler.snapshot()
        profiler.work.append(update)
        profiler.active = None
        if len(update["physics"]) != 1 or ((d.word("game_steps") - update["steps_before"]) & 65535) != 1:
            profiler.errors.append(f"update {update['index']}: expected exactly one completed physics step")
        state = update["state_after"]["state"]
        if state != RIDING:
            profiler.finished = True
            profiler.end_reason = STATE_NAMES.get(state, f"unknown-{state}")
            if state not in (DEAD, FINISHED):
                profiler.errors.append("game left riding without death/finish")
        elif len(profiler.work) >= len(profiler.plan):
            profiler.finished = True
            profiler.end_reason = "step_limit"

    def timing_report(self):
        costs = {}
        for call in self.records:
            costs.setdefault(call["name"], []).append(call["cycles"])
        worst = []
        for update in sorted(self.work, key=lambda item: item["cycles"], reverse=True)[:10]:
            inclusive, calls = Counter(), Counter()
            for record in self.records:
                if record["update"] == update["index"]:
                    inclusive[record["name"]] += record["cycles"]
                    calls[record["name"]] += 1
            state = update["state_after"]
            worst.append({"update": update["index"], "cycles": update["cycles"],
                          "cycles_with_gdma_surcharge": update["cycles_with_gdma_surcharge"],
                          "gdma_blocks": update["gdma_blocks"],
                          "frame": update["frame"], "end_frame": update["end_frame"],
                          "buttons": update["buttons"], "state": state["state"],
                          "time_frames": state["time_frames"], "camera": state["camera"],
                          "function_cycles": dict(inclusive), "function_calls": dict(calls),
                          "other_loop_cycles": update["cycles"] - inclusive["_game_present"] - inclusive["_physics_step"]})
        before = self.initial["overruns"] if self.initial else None
        after = self.work[-1]["overruns_after"] if self.work else before
        return {"whole_active_update": statistics([update["cycles"] for update in self.work]),
                "functions": {name: statistics(values) for name, values in sorted(costs.items())},
                "update_budget_cycles": UPDATE_BUDGET,
                "updates_exceeding_budget": sum(update["cycles"] > UPDATE_BUDGET for update in self.work),
                "active_update_with_gdma_surcharge": statistics([update["cycles_with_gdma_surcharge"] for update in self.work]),
                "updates_exceeding_budget_with_gdma_surcharge": sum(
                    update["cycles_with_gdma_surcharge"] > UPDATE_BUDGET for update in self.work),
                "gdma": {"launch_sites": self.gdma_sites, "coverage": "world_upload_tile only",
                         "commands": sum(update["gdma_commands"] for update in self.work),
                         "blocks": sum(update["gdma_blocks"] for update in self.work),
                         "surcharge_cycles": sum(update["gdma_surcharge_cycles"] for update in self.work),
                         "hdma_commands_not_surcharged": sum(update["hdma_commands"] for update in self.work),
                         "limitation": GDMA_LIMITATION},
                "game_overruns_before": before, "game_overruns_after": after,
                "game_overruns_delta": after - before if before is not None else None,
                "worst_active_updates": worst, "internal_vsyncs": self.internal_vsyncs,
                "irq_entry_repeats": dict(self.irq_entry_repeats),
                "unfinished_observed_calls": len(self.stack),
                "unfinished_active_update": self.active is not None}


def run_case(args, level, scenario, names):
    started = time.monotonic()
    case_id = f"level-{level:02d}-{scenario}"
    plan = controller_plan(scenario, args.seed, level, args.steps)
    driver = observer = None
    errors = []
    result = {"id": case_id, "level": level, "name": names[level - 1], "scenario": scenario,
              "requested_steps": args.steps, "status": "failed"}
    trace = {"id": case_id, "controller_plan": plan, "initial": None,
             "physics": [], "updates": [], "final": None, "end_reason": "error"}
    try:
        driver = Driver(args.rom, args.out / "driver" / case_id, args.gen)
        required = ("_Bike", "_ph_step", "_game_level_index", "_vsync", "__current_bank")
        missing = [name for name in required if name not in driver.symbols]
        if missing:
            raise AssertionError("missing benchmark symbols: " + ", ".join(missing))
        result["runtime"] = {"physics_interval": driver.frame_interval,
                             "present_interval": driver.present_interval,
                             "physics_hz": driver.rom_constant("game_physics_hz", 0)}
        if result["runtime"] != {"physics_interval": 2, "present_interval": 2, "physics_hz": 30}:
            raise AssertionError("benchmark requires unchanged 30 Hz physics and two-display-frame presentation")
        if not driver.level_manifest or len(driver.level_manifest["levels"]) != LEVEL_COUNT:
            raise AssertionError("benchmark requires the generated 54-course manifest")
        driver.ready()
        driver.level_menu()
        if driver.byte("game_state") != MENU:
            raise AssertionError("fresh emulator did not open the level menu")
        current = driver.level_index() + 1
        distance = (level - current) % LEVEL_COUNT
        key, count = ("down", distance) if distance <= LEVEL_COUNT // 2 else ("up", LEVEL_COUNT - distance)
        for _ in range(count):
            driver.pulse(key)
        observer = GameplayProfiler(driver, level, plan)
        # Use Driver.tick/buttons to launch without pulse()'s extra riding loops.
        # Once the menu changes to RIDING, stage scenario controls while its
        # level finishes loading, before the next main-loop controller sample.
        for _ in range(600):
            driver.tick(1, ["start"])
            if driver.byte("game_state") == RIDING:
                break
        else:
            raise AssertionError("controller level launch exceeded 600 display frames")
        if driver.level_index() + 1 != level:
            raise AssertionError("menu selected a different course")
        if observer.started_updates:
            raise AssertionError("menu launch consumed gameplay input before scenario controls were staged")
        last_progress = driver.p.frame_count
        progress = observer.started_updates
        for _ in range(args.steps * 60 + 600):
            if observer.finished:
                break
            # PyBoy applies buttons at the next host tick, not inside a hook.
            # Stage the next input immediately after observing the current
            # sample, before the next vsync can sample it. This stays identical
            # when the ongoing physics/presentation spans more display frames.
            next_input = min(observer.started_updates, args.steps - 1)
            driver.tick(1, plan[next_input])
            if progress != observer.started_updates:
                progress = observer.started_updates
                last_progress = driver.p.frame_count
            if driver.byte("game_ready") and driver.p.frame_count - last_progress > 120:
                raise AssertionError("no completed gameplay progress within 120 display frames")
        else:
            raise AssertionError("bounded gameplay frame limit exhausted")
        if not observer.physics or not observer.finished:
            raise AssertionError("no complete observed gameplay case")
    except Exception as error:
        errors.append(f"{type(error).__name__}: {error}")
        result["exception"] = traceback.format_exc()
    finally:
        if observer is not None:
            errors.extend(observer.errors)
            trace.update(initial=observer.initial, physics=observer.physics, updates=observer.work,
                         final=observer.work[-1]["state_after"] if observer.work else None,
                         end_reason=observer.end_reason or "error", calls=observer.records)
            result["timing"] = observer.timing_report()
            result["completed_steps"] = len(observer.physics)
            result["completed_updates"] = len(observer.work)
            result["end_reason"] = trace["end_reason"]
            result["final"] = trace["final"]
            if observer.active is not None:
                trace["incomplete_update"] = observer.active
                errors.append("active update did not reach its completed vsync boundary")
            if observer.stack:
                trace["incomplete_calls"] = observer.stack
                errors.append("observed function calls did not return")
        if driver is not None:
            try:
                driver.close()
            except Exception as error:
                errors.append(f"close: {type(error).__name__}: {error}")
        result["errors"] = errors
        result["correctness_checks_passed"] = not errors and observer is not None and observer.finished
        timing = result.get("timing", {})
        result["performance_requirement_met"] = bool(timing.get("whole_active_update", {}).get("count")) and (
            timing.get("updates_exceeding_budget") == 0 and timing.get("game_overruns_delta") == 0
            and timing.get("updates_exceeding_budget_with_gdma_surcharge") == 0)
        result["status"] = "passed" if result["correctness_checks_passed"] and result["performance_requirement_met"] else "failed"
        result["host_seconds"] = time.monotonic() - started
    return result, trace


def fidelity_record(trace):
    def state(value):
        return {key: value[key] for key in STATE_FIELDS} if value is not None else None
    return {"initial": state(trace["initial"]), "final": state(trace["final"]),
            "end_reason": trace["end_reason"],
            "physics": [{"index": item["index"], "physics_input": item["physics_input"],
                         "core_input": item["core_input"], "state": state(item["return_state"])}
                        for item in trace["physics"]],
            "updates": [{"index": item["index"], "buttons": item["buttons"],
                         "state": state(item["state_after"])} for item in trace["updates"]]}


def differences(actual, expected, path="", found=None):
    """Retain at most ten useful first-difference diagnostics."""
    found = [] if found is None else found
    if actual == expected or len(found) >= 10:
        return found
    if isinstance(actual, dict) and isinstance(expected, dict):
        for key in sorted(actual.keys() | expected.keys()):
            differences(actual.get(key), expected.get(key), f"{path}.{key}".lstrip("."), found)
    elif isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            found.append({"path": path + ".length", "actual": len(actual), "reference": len(expected)})
        for index, (left, right) in enumerate(zip(actual, expected)):
            differences(left, right, f"{path}[{index}]", found)
            if len(found) >= 10:
                break
    elif path.endswith("_hex") and isinstance(actual, str) and isinstance(expected, str):
        left, right = bytes.fromhex(actual), bytes.fromhex(expected)
        offsets = [index for index, (a, b) in enumerate(zip(left, right)) if a != b]
        found.append({"path": path, "actual_bytes": len(left), "reference_bytes": len(right),
                      "different_bytes": len(offsets),
                      "first_bytes": [{"offset": index, "actual": left[index], "reference": right[index]}
                                      for index in offsets[:8]]})
    else:
        found.append({"path": path, "actual": actual, "reference": expected})
    return found


def load_reference(path):
    if path.is_dir():
        path = path / "report.json"
    if not (path.name.endswith(".jsonl") or path.name.endswith(".jsonl.gz")):
        report = json.loads(path.read_text())
        path = path.parent / report["trace_file"]
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        header = json.loads(next(stream))
        if header.get("kind") != "header" or header.get("schema") != SCHEMA:
            raise ValueError("reference is not a supported gameplay benchmark trace")
        cases = {}
        for line in stream:
            item = json.loads(line)
            if item.get("kind") != "case" or item["trace"]["id"] in cases:
                raise ValueError("invalid/duplicate case in reference trace")
            cases[item["trace"]["id"]] = item
    return {"path": str(path.resolve()), "sha256": digest(path), "header": header, "cases": cases}


def compare_reference(result, trace, reference, settings):
    match = reference["cases"].get(trace["id"])
    problems = []
    reference_settings = reference["header"]["settings"]
    for key in ("steps", "seed", "controller_version"):
        if settings[key] != reference_settings[key]:
            problems.append({"path": "settings." + key, "actual": settings[key],
                             "reference": reference_settings[key]})
    if match is None:
        problems.append({"path": "case", "error": "case is missing from reference"})
    else:
        problems.extend(differences(fidelity_record(trace), fidelity_record(match["trace"])))
    comparison = {"passed": not problems, "first_differences": problems[:10]}
    if match is not None:
        old = match["summary"].get("timing", {}).get("whole_active_update", {})
        new = result.get("timing", {}).get("whole_active_update", {})
        comparison["timing_delta_cycles"] = {
            name: new[name] - old[name] if new.get(name) is not None and old.get(name) is not None else None
            for name in ("mean_cycles", "p95_cycles", "max_cycles")}
        comparison["reference_status"] = match["summary"]["status"]
    return comparison


def write_report(path, report):
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--gen", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=BASE / "build/gameplay-benchmark")
    parser.add_argument("--levels", type=selected_levels, default=list(range(1, LEVEL_COUNT + 1)),
                        help="one-based comma-separated numbers/ranges, or all (default all 54)")
    parser.add_argument("--steps", type=bounded_steps, default=300, help="maximum physics steps per case (1..10000)")
    parser.add_argument("--scenario", nargs="+", choices=SCENARIOS, default=list(SCENARIOS),
                        help="one or more scenarios (default all four)")
    parser.add_argument("--seed", type=lambda value: int(value, 0), default=0xE6B0)
    parser.add_argument("--reference", type=Path, help="prior report.json, trace.jsonl[.gz], or output directory")
    args = parser.parse_args()
    args.rom, args.gen, args.out = args.rom.resolve(), args.gen.resolve(), args.out.resolve()
    args.scenario = list(dict.fromkeys(args.scenario))
    args.out.mkdir(parents=True, exist_ok=True)
    settings = {"levels": args.levels, "scenarios": args.scenario, "steps": args.steps, "seed": args.seed,
                "controller_version": CONTROLLER_VERSION, "display_cycles": DISPLAY_CYCLES,
                "update_budget_cycles": UPDATE_BUDGET, "sound_emulated": False,
                "brake_policy": "gas for min(60, max(1, steps // 3)) updates, then hold B",
                "seeded_policy": "per-update seeded gas/brake/neutral, occasional left/right and Up"}
    report = {"schema": SCHEMA, "status": "running", "rom": str(args.rom), "gen": str(args.gen),
              "started_utc": datetime.now(timezone.utc).isoformat(), "settings": settings,
              "source": "controller-only real ROM; read-only entry/return hooks; no guest-state injection",
              "state_boundary": "physics_step return before caller clock/object checks; completed-update vsync after them",
              "state_sizes_bytes": {"Bike": 109, "gbc_bike": 52},
              "emulator_timing_limitation": GDMA_LIMITATION,
              "performance_requirement_scope": "fixed budget for emulator cycles and GDMA surcharge estimate, plus zero game_overruns",
              "trace_file": "trace.jsonl.gz", "cases": [], "errors": [],
              "deadline_budget_relaxed_for_diagnostics": False, "hardware_tested": False}
    reference = None
    trace_stream = None
    try:
        report.update(rom_sha256=digest(args.rom), symbols_sha256=digest(args.rom.with_suffix(".noi")),
                      level_manifest_sha256=digest(args.gen / "level_manifest.json"),
                      physics_constants_sha256=digest(args.gen / "riding_constants.h"),
                      emulator={"name": "PyBoy", "version": version("pyboy"), "python": platform.python_version()})
        manifest = json.loads((args.gen / "level_manifest.json").read_text())
        names = [level["name"] for level in manifest["levels"]]
        if len(names) != LEVEL_COUNT:
            raise ValueError("expected exactly 54 generated levels")
        # PyBoy may load an existing battery file beside the ROM; record it,
        # and Driver.close(save=False) ensures this benchmark never changes it.
        battery = Path(str(args.rom) + ".ram")
        report["battery_sha256"] = digest(battery) if battery.exists() else None
        if args.reference:
            reference = load_reference(args.reference.resolve())
            if Path(reference["path"]) == args.out / report["trace_file"]:
                raise ValueError("reference trace and output trace must be different paths")
            report["reference"] = {"path": reference["path"], "sha256": reference["sha256"],
                                   "rom_sha256": reference["header"].get("rom_sha256")}
        trace_stream = gzip.open(args.out / report["trace_file"], "wt", encoding="utf-8")
        header = {key: value for key, value in report.items() if key not in ("cases", "errors", "status")}
        trace_stream.write(json.dumps({"kind": "header", **header}, separators=(",", ":")) + "\n")
        write_report(args.out / "report.json", report)
        for level in args.levels:
            for scenario in args.scenario:
                summary, trace = run_case(args, level, scenario, names)
                if reference:
                    summary["reference_comparison"] = compare_reference(summary, trace, reference, settings)
                    if not summary["reference_comparison"]["passed"]:
                        summary["status"] = "failed"
                report["cases"].append(summary)
                trace_stream.write(json.dumps({"kind": "case", "summary": summary, "trace": trace}, separators=(",", ":")) + "\n")
                trace_stream.flush()
                write_report(args.out / "report.json", report)
                timing = summary.get("timing", {})
                peak = timing.get("whole_active_update", {}).get("max_cycles")
                print(f"{summary['id']}: {summary['status']} steps={summary.get('completed_steps', 0)} "
                      f"max_cycles={peak} overruns={timing.get('game_overruns_delta')} "
                      f"end={summary.get('end_reason', 'error')}", flush=True)
    except (Exception, KeyboardInterrupt) as error:
        report["errors"].append(f"{type(error).__name__}: {error}")
        report["exception"] = traceback.format_exc()
    finally:
        if trace_stream is not None:
            trace_stream.close()
        cases = report["cases"]
        expected = len(args.levels) * len(args.scenario)
        report["requested_cases"] = expected
        report["completed_cases"] = len(cases)
        report["correctness_checks_passed"] = len(cases) == expected and not report["errors"] and all(
            case["correctness_checks_passed"] for case in cases)
        report["performance_requirement_met"] = len(cases) == expected and all(
            case["performance_requirement_met"] for case in cases)
        report["reference_comparison_passed"] = (all(case.get("reference_comparison", {}).get("passed", False)
                                                       for case in cases) and len(cases) == expected) if args.reference else None
        report["status"] = "passed" if (report["correctness_checks_passed"] and report["performance_requirement_met"]
                                              and report["reference_comparison_passed"] is not False) else "failed"
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_report(args.out / "report.json", report)
    print(f"{report['status']}: {args.out / 'report.json'}", flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
