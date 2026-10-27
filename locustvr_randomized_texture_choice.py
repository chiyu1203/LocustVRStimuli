#!/usr/bin/env python
# Original experiment code: Sercan Sayin (Sayin et al., 2025).
# Later contributions: Aljoscha Markus, Jonathan Ernst, and Chi-Yu Lee.
# Current design: nine fully shuffled trials per block, randomized bait texture,
# 20-second choice phase, 25-35-second ISI, and a 60-minute safety cutoff.
"""LocustVR simultaneous two-choice experiment.

Based on the experiment created for Sayin et al. (2025) and later modified by
Aljoscha Markus, Jonathan Ernst, and Chi-Yu Lee.

Each block contains nine independently shuffled trials: one trial for each
identical pair (black-black, yellow-yellow, gregarious-gregarious) and two
side-swapped trials for each mixed pair.  Sixty blocks produce 540 planned
trials.  Every trial receives a random black, yellow, or gregarious bait
texture, recorded in the label as ``BT<texture>``.

Stimuli are shown for 20 seconds, followed by a random 25-35 second ISI.  The
experiment retains the 360,000-loop cutoff (about 60 minutes at 100 Hz).
Tracking is saved in the original 13-column ``data.dat`` format, and a copy of
this source file is placed in the result folder.

Requires LocustVR, FreemooVR/StimulusOSG2, ``realtime_orientation``, the four
configured OSG assets, and the tracking callback ``move_world(x, y, z)``.
Use ``--validate-plan-only`` to check the schedule without hardware.
"""

import argparse
import datetime
import logging
import math
import os
import random
import shutil
import sys
import threading
import time
from ctypes import c_double
from multiprocessing import Process, Value


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(SCRIPT_DIR)

# Python 2.7 has no time.monotonic().  LocustVR installations using Python 2
# therefore fall back to time.time(); Python 3 keeps the monotonic clock.
CLOCK = getattr(time, "monotonic", time.time)

# Hardware imports are optional only so that --validate-plan-only can run on a
# development machine.  A real experiment refuses to start without them.
HARDWARE_IMPORT_ERROR = None
try:
    from locustvr.experiment import ExperimentBase
    from freemoovr.proxy.stimulus_osg import StimulusOSG2Controller  # noqa: F401
    from realtime_orientation import get_orientation
except ImportError as exc:  # pragma: no cover - depends on the lab machine
    HARDWARE_IMPORT_ERROR = exc

    class ExperimentBase(object):
        """Placeholder used only for hardware-independent plan validation."""


TEXTURE_BLACK = "black"
TEXTURE_YELLOW = "yellow"
TEXTURE_GREGARIOUS = "gregarious"
TEXTURES = (TEXTURE_BLACK, TEXTURE_YELLOW, TEXTURE_GREGARIOUS)

# Codes 0-2 are mixed-texture conditions with both side arrangements.
# Codes 3-5 are identical-texture conditions presented once per block.
CONDITIONS = (
    {"code": 0, "name": "black-gregarious", "a": TEXTURE_BLACK,
     "b": TEXTURE_GREGARIOUS, "side_swap": True},
    {"code": 1, "name": "yellow-gregarious", "a": TEXTURE_YELLOW,
     "b": TEXTURE_GREGARIOUS, "side_swap": True},
    {"code": 2, "name": "black-yellow", "a": TEXTURE_BLACK,
     "b": TEXTURE_YELLOW, "side_swap": True},
    {"code": 3, "name": "black-black", "a": TEXTURE_BLACK,
     "b": TEXTURE_BLACK, "side_swap": False},
    {"code": 4, "name": "yellow-yellow", "a": TEXTURE_YELLOW,
     "b": TEXTURE_YELLOW, "side_swap": False},
    {"code": 5, "name": "gregarious-gregarious", "a": TEXTURE_GREGARIOUS,
     "b": TEXTURE_GREGARIOUS, "side_swap": False},
)

TRIALS_PER_BLOCK = 9


def build_trial_plan(number_of_blocks, seed=None):
    """Build and validate the randomized block schedule.

    ``state`` retains the historical meaning for different pairs:
    state 1 is the condition's canonical a-left/b-right arrangement and state
    2 is its side-swapped b-left/a-right arrangement.  Identical pairs have no
    meaningful side order and therefore use state 1.
    """
    if number_of_blocks <= 0:
        raise ValueError("number_of_blocks must be greater than zero")

    if seed is None:
        seed = random.SystemRandom().randrange(0, 2 ** 63)
    rng = random.Random(seed)
    plan = []

    for block_index in range(1, number_of_blocks + 1):
        block_trials = []

        for condition in CONDITIONS:
            if condition["side_swap"]:
                arrangements = (
                    (condition["a"], condition["b"], 1),
                    (condition["b"], condition["a"], 2),
                )
            else:
                arrangements = ((condition["a"], condition["b"], 1),)

            pair_size = len(arrangements)
            for pair_position, arrangement in enumerate(arrangements, start=1):
                left_texture, right_texture, state = arrangement
                block_trials.append({
                    "block": block_index,
                    "condition_code": condition["code"],
                    "condition": condition["name"],
                    "pair_position": pair_position,
                    "pair_size": pair_size,
                    "left_texture": left_texture,
                    "right_texture": right_texture,
                    "state": state,
                    "seed": seed,
                })

        # Shuffle the nine actual trials, not six condition units.  Therefore,
        # the two side arrangements of a mixed condition are not tied together.
        rng.shuffle(block_trials)
        for block_position, trial in enumerate(block_trials, start=1):
            trial["trial_index"] = len(plan)
            trial["block_position"] = block_position
            plan.append(trial)

    # Assign one independently randomized bait texture to every trial.
    # This is reproducible from the seed but not forced to equal texture counts.
    bait_rng = random.Random(seed ^ 0xBA17BA17)
    for trial in plan:
        trial["bait_texture"] = bait_rng.choice(TEXTURES)

    validate_trial_plan(plan, number_of_blocks)
    return plan, seed


def validate_trial_plan(plan, number_of_blocks):
    """Raise AssertionError if counts, positions, or side swaps are wrong."""
    expected_total = number_of_blocks * TRIALS_PER_BLOCK
    assert len(plan) == expected_total, (
        "Expected {} trials, found {}".format(expected_total, len(plan))
    )
    assert all(row["bait_texture"] in TEXTURES for row in plan)

    for block_index in range(1, number_of_blocks + 1):
        block_trials = [row for row in plan if row["block"] == block_index]
        assert len(block_trials) == TRIALS_PER_BLOCK
        assert {row["block_position"] for row in block_trials} == set(
            range(1, TRIALS_PER_BLOCK + 1)
        )

        for condition in CONDITIONS:
            rows = [
                row for row in block_trials
                if row["condition_code"] == condition["code"]
            ]
            expected_count = 2 if condition["side_swap"] else 1
            assert len(rows) == expected_count

            if condition["side_swap"]:
                assert {row["state"] for row in rows} == {1, 2}
                assert rows[0]["left_texture"] == rows[1]["right_texture"]
                assert rows[0]["right_texture"] == rows[1]["left_texture"]
            else:
                assert rows[0]["left_texture"] == rows[0]["right_texture"]
                assert rows[0]["pair_size"] == 1


def segment_reaches_radius(x0, y0, x1, y1, radius):
    """Return True when a movement segment enters the trigger circle.

    Checking the complete segment prevents a large tracker update from jumping
    from one side of the focal animal to the other without ever producing an
    endpoint whose distance is below the trigger threshold.
    """
    movement_x = x1 - x0
    movement_y = y1 - y0
    movement_squared = movement_x ** 2 + movement_y ** 2

    if movement_squared == 0.0:
        closest_x = x0
        closest_y = y0
    else:
        projection = -(
            x0 * movement_x + y0 * movement_y
        ) / movement_squared
        projection = max(0.0, min(1.0, projection))
        closest_x = x0 + projection * movement_x
        closest_y = y0 + projection * movement_y

    return closest_x ** 2 + closest_y ** 2 <= radius ** 2


class MyExperiment(ExperimentBase):
    """LocustVR experiment controller."""

    LOOP_INTERVAL_SECONDS = 0.01  # 100 Hz
    TEST_TIME_TICKS = 2000         # 20 seconds at 100 Hz
    ISI_MIN_TICKS = 2500           # additional 25 seconds
    ISI_MAX_TICKS = 3500           # additional 35 seconds
    EXPERIMENT_TIME_TICKS = 360000  # historical ~60-minute safety cutoff
    DEFAULT_BLOCKS = 60

    DEFAULT_STIMULUS_DIR = "/home/loopbio/Documents/LocustVR2_2/Stimulus"
    DEFAULT_DATA_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "Data"))

    def __init__(self, *args, **kwargs):
        ExperimentBase.__init__(self, *args, **kwargs)

        current_time = time.strftime("%H:%M:%S", time.localtime())
        print("INFO: START TIME is {}".format(current_time))

        self.unload_all()
        self._olock = threading.Lock()
        self._world_initialized = False

        self.FocalAngle = Value(c_double, 0.0)
        self.process = Process(target=self.update_orientation)
        # Prevent a setup error before the main try/finally block from leaving
        # an orphaned process that keeps Python alive.
        self.process.daemon = True
        self.process.start()

        self.prevworld = [0.0, 0.0]
        self.deltas = [0.0, 0.0]

        # These may be overridden by command-line arguments after new_osg2().
        self.number_of_blocks = self.DEFAULT_BLOCKS
        self.plan_seed = None
        self.stimulus_dir = self.DEFAULT_STIMULUS_DIR
        self.data_dir = self.DEFAULT_DATA_DIR

    def _asset_path(self, filename):
        path = os.path.join(self.stimulus_dir, filename)
        if not os.path.isfile(path):
            raise IOError(
                "Required stimulus asset not found: {}. "
                "Check --stimulus-dir.".format(path)
            )
        return path

    @staticmethod
    def _hide_choice_objects(choice_objects):
        for texture_objects in choice_objects.values():
            for stimulus in texture_objects:
                stimulus.move(hidden=True)

    @staticmethod
    def _hide_bait_objects(bait_objects):
        for stimulus in bait_objects.values():
            stimulus.move(hidden=True)

    def _consume_world_delta(self):
        """Return accumulated tracker motion and consume it exactly once."""
        with self._olock:
            delta_x = self.deltas[0]
            delta_y = self.deltas[1]
            self.deltas[0] = 0.0
            self.deltas[1] = 0.0
        return delta_x, delta_y

    def _stop_orientation_process(self):
        process = getattr(self, "process", None)
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout=2.0)

    def run_forever(self):
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = "six_texture_conditions_{}blocks".format(self.number_of_blocks)
        self.folder_path = os.path.join(
            os.path.abspath(self.data_dir), timestamp_str + "_" + suffix
        )
        os.makedirs(self.folder_path)

        shutil.copy2(
            os.path.abspath(__file__),
            os.path.join(self.folder_path, os.path.basename(__file__)),
        )
        self.output = os.path.join(self.folder_path, "data.dat")

        trial_plan, actual_seed = build_trial_plan(
            self.number_of_blocks, self.plan_seed
        )

        print("INFO: randomization seed: {}".format(actual_seed))
        print("INFO: planned trials: {}".format(len(trial_plan)))
        print("INFO: output folder: {}".format(self.folder_path))

        # state 0 = bait phase; states 1 and 2 = the two side arrangements.
        # Choice stimuli last 20 s; the following ISI lasts 25-35 s.
        state = 0
        trial_num = 0
        trial_tick = 0
        trial_label = None
        current_trial = None
        isi_end_tick = None

        z_pos = 0.065
        world_border = 0.30
        bait_distance = 0.12
        bait_speed = 0.0002
        trigger_distance = 0.08
        test_angle = math.radians(60.0)
        test_distance = 0.06

        focal_heading = self.FocalAngle.value
        bait_speed_x = bait_speed * math.cos(focal_heading)
        bait_speed_y = bait_speed * math.sin(focal_heading)
        bait_x = bait_distance * math.cos(focal_heading)
        bait_y = bait_distance * math.sin(focal_heading)
        bait_orientation = focal_heading + math.pi / 2.0

        left_position = [100.0, 100.0]
        right_position = [100.0, 100.0]
        left_orientation = math.pi / 2.0
        right_orientation = math.pi / 2.0

        # Load hidden base assets used as clone sources, plus the visible arena.
        gregarious_base = self.load_osg(
            self._asset_path("Locust_066x.osgt")
        )
        gregarious_base.move(hidden=True)

        black_base = self.load_osg(
            self._asset_path("Locust_066x_black.osgt")
        )
        black_base.move(hidden=True)

        yellow_base = self.load_osg(
            self._asset_path("Locust_066x_yellow.osgt")
        )
        yellow_base.move(hidden=True)

        cylinder = self.load_osg(self._asset_path("greyworld_05.osgt"))
        cylinder.move(0.0, 0.0, 0.0, hidden=False, scale=3)

        # One dedicated bait object per texture.  Only the bait assigned to the
        # upcoming trial is visible during its pre-choice phase.
        bait_objects = {
            TEXTURE_GREGARIOUS: gregarious_base.clone(
                "bait_gregarious", how="shallow"
            ),
            TEXTURE_BLACK: black_base.clone("bait_black", how="shallow"),
            TEXTURE_YELLOW: yellow_base.clone("bait_yellow", how="shallow"),
        }
        for bait_object in bait_objects.values():
            bait_object.move(
                bait_x, bait_y, z_pos,
                orientation_z=bait_orientation,
                hidden=True,
            )
            bait_object.animation_start("ArmatureAction")

        active_bait_texture = trial_plan[0]["bait_texture"]
        active_bait = bait_objects[active_bait_texture]
        active_bait.move(
            bait_x, bait_y, z_pos,
            orientation_z=bait_orientation,
            hidden=False,
        )

        # Two choice instances per texture allow identical left/right pairs.
        choice_objects = {
            TEXTURE_GREGARIOUS: (
                gregarious_base.clone("gregarious_left", how="shallow"),
                gregarious_base.clone("gregarious_right", how="shallow"),
            ),
            TEXTURE_BLACK: (
                black_base.clone("black_left", how="shallow"),
                black_base.clone("black_right", how="shallow"),
            ),
            TEXTURE_YELLOW: (
                yellow_base.clone("yellow_left", how="shallow"),
                yellow_base.clone("yellow_right", how="shallow"),
            ),
        }
        self._hide_choice_objects(choice_objects)

        rng = random.Random(actual_seed ^ 0x5A17C0DE)
        next_tick_deadline = CLOCK()
        experiment_complete = False
        control_loop_tick = 0
        termination_reason = None

        try:
            with open(self.output, "a", buffering=1) as data_file:
                while not experiment_complete:
                    focal_heading = self.FocalAngle.value
                    world_delta_x, world_delta_y = self._consume_world_delta()

                    if state == 0:
                        trial_label = None
                        previous_bait_x = bait_x
                        previous_bait_y = bait_y
                        bait_x += bait_speed_x + world_delta_x
                        bait_y += bait_speed_y + world_delta_y
                        bait_position = math.hypot(bait_x, bait_y)
                        reached_trigger = segment_reaches_radius(
                            previous_bait_x,
                            previous_bait_y,
                            bait_x,
                            bait_y,
                            trigger_distance,
                        )

                        if reached_trigger:
                            if trial_num >= len(trial_plan):
                                experiment_complete = True
                                termination_reason = "schedule_complete"
                            else:
                                current_trial = trial_plan[trial_num]
                                state = current_trial["state"]
                                trial_tick = 0
                                isi_end_tick = self.TEST_TIME_TICKS + rng.randint(
                                    self.ISI_MIN_TICKS, self.ISI_MAX_TICKS
                                )

                                active_bait.move(hidden=True)

                                left_position = [
                                    test_distance * math.cos(focal_heading - test_angle),
                                    test_distance * math.sin(focal_heading - test_angle),
                                ]
                                right_position = [
                                    test_distance * math.cos(focal_heading + test_angle),
                                    test_distance * math.sin(focal_heading + test_angle),
                                ]
                                left_orientation = (
                                    focal_heading + math.pi / 2.0 - test_angle
                                )
                                right_orientation = (
                                    focal_heading + math.pi / 2.0 + test_angle
                                )

                                self._hide_choice_objects(choice_objects)
                                left_object = choice_objects[
                                    current_trial["left_texture"]
                                ][0]
                                right_object = choice_objects[
                                    current_trial["right_texture"]
                                ][1]
                                left_object.move(
                                    left_position[0], left_position[1], z_pos,
                                    orientation_z=left_orientation,
                                    hidden=False,
                                )
                                right_object.move(
                                    right_position[0], right_position[1], z_pos,
                                    orientation_z=right_orientation,
                                    hidden=False,
                                )

                                trial_label = (
                                    "T{trial}_CD{distance}_CS{code}_S{state}_"
                                    "L{left}_R{right}_BT{bait}"
                                ).format(
                                    trial=trial_num,
                                    distance=int(round(test_distance * 100)),
                                    code=current_trial["condition_code"],
                                    state=state,
                                    left=current_trial["left_texture"],
                                    right=current_trial["right_texture"],
                                    bait=current_trial["bait_texture"],
                                )

                                print(
                                    "Trial {}/{} | block {} | {} | left={} | "
                                    "right={} | bait={} | state={} | label={}".format(
                                        trial_num + 1,
                                        len(trial_plan),
                                        current_trial["block"],
                                        current_trial["condition"],
                                        current_trial["left_texture"],
                                        current_trial["right_texture"],
                                        current_trial["bait_texture"],
                                        state,
                                        trial_label,
                                    )
                                )
                        elif bait_position >= world_border:
                            bait_speed_x = bait_speed * math.cos(focal_heading)
                            bait_speed_y = bait_speed * math.sin(focal_heading)
                            bait_x = bait_distance * math.cos(focal_heading)
                            bait_y = bait_distance * math.sin(focal_heading)
                            bait_orientation = focal_heading + math.pi / 2.0
                            active_bait.move(
                                bait_x, bait_y, z_pos,
                                orientation_z=bait_orientation,
                                hidden=False,
                            )
                        else:
                            active_bait.move(
                                bait_x, bait_y, z_pos,
                                orientation_z=bait_orientation,
                                hidden=False,
                            )

                    if state in (1, 2):
                        if trial_tick < self.TEST_TIME_TICKS:
                            left_object = choice_objects[
                                current_trial["left_texture"]
                            ][0]
                            right_object = choice_objects[
                                current_trial["right_texture"]
                            ][1]
                            left_object.move(
                                left_position[0], left_position[1], z_pos,
                                orientation_z=left_orientation,
                                hidden=False,
                            )
                            right_object.move(
                                right_position[0], right_position[1], z_pos,
                                orientation_z=right_orientation,
                                hidden=False,
                            )
                            trial_tick += 1

                        elif trial_tick < isi_end_tick:
                            self._hide_choice_objects(choice_objects)
                            left_position = [100.0, 100.0]
                            right_position = [100.0, 100.0]
                            trial_tick += 1

                        if trial_tick >= isi_end_tick:
                            self._hide_choice_objects(choice_objects)
                            bait_speed_x = bait_speed * math.cos(focal_heading)
                            bait_speed_y = bait_speed * math.sin(focal_heading)
                            bait_x = bait_distance * math.cos(focal_heading)
                            bait_y = bait_distance * math.sin(focal_heading)
                            bait_orientation = focal_heading + math.pi / 2.0

                            trial_tick = 0
                            state = 0
                            trial_num += 1
                            current_trial = None
                            trial_label = None
                            experiment_complete = trial_num >= len(trial_plan)
                            if experiment_complete:
                                termination_reason = "schedule_complete"
                            else:
                                active_bait_texture = trial_plan[trial_num][
                                    "bait_texture"
                                ]
                                active_bait = bait_objects[active_bait_texture]
                                active_bait.move(
                                    bait_x, bait_y, z_pos,
                                    orientation_z=bait_orientation,
                                    hidden=False,
                                )

                    data_file.write(
                        "{} {} {} {} {} {} {} {} {} {} {} {} {}\n".format(
                            world_delta_x,
                            world_delta_y,
                            focal_heading,
                            time.time(),
                            trial_num,
                            state,
                            trial_label,
                            left_position[0],
                            left_position[1],
                            right_position[0],
                            right_position[1],
                            bait_x,
                            bait_y,
                        )
                    )

                    control_loop_tick += 1
                    if (
                        not experiment_complete
                        and control_loop_tick >= self.EXPERIMENT_TIME_TICKS
                    ):
                        experiment_complete = True
                        termination_reason = "time_limit"

                    next_tick_deadline += self.LOOP_INTERVAL_SECONDS
                    sleep_seconds = next_tick_deadline - CLOCK()
                    if sleep_seconds > 0:
                        time.sleep(sleep_seconds)
                    elif sleep_seconds < -1.0:
                        # Do not attempt to catch up thousands of missed frames.
                        logging.warning(
                            "Control loop is more than one second behind; "
                            "resetting its timing deadline."
                        )
                        next_tick_deadline = CLOCK()

            if termination_reason == "time_limit":
                print(
                    "INFO: 60-minute cutoff reached after {} completed "
                    "trials; {} of {} planned trials remain.".format(
                        trial_num,
                        len(trial_plan) - trial_num,
                        len(trial_plan),
                    )
                )
            else:
                print(
                    "INFO: completed all {} planned trials".format(
                        len(trial_plan)
                    )
                )
        finally:
            self._stop_orientation_process()
            try:
                self._hide_choice_objects(choice_objects)
                self._hide_bait_objects(bait_objects)
            finally:
                self.unload_all()

    def move_world(self, x, y, z):
        """Store world-motion deltas; called by the LocustVR tracker."""
        del z  # retained callback signature; vertical motion is not used here
        with self._olock:
            if not self._world_initialized:
                self.prevworld = [x, y]
                self._world_initialized = True

            # Accumulate every callback.  The control loop may run at a
            # different frequency and consumes the sum exactly once.
            self.deltas[0] += x - self.prevworld[0]
            self.deltas[1] += y - self.prevworld[1]
            self.prevworld = [x, y]

    def update_orientation(self):
        """Continuously copy focal-animal heading into shared memory."""
        for angle in get_orientation():
            self.FocalAngle.value = angle


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the 540-trial LocustVR texture-choice experiment."
    )
    parser.add_argument(
        "-d", "--debug-display", action="store_true", default=False,
        help="also run on the debug display server",
    )
    parser.add_argument(
        "--blocks", type=int, default=MyExperiment.DEFAULT_BLOCKS,
        help="number of blocks (default: 60; 9 trials per block)",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="optional randomization seed for a reproducible schedule",
    )
    parser.add_argument(
        "--stimulus-dir", default=MyExperiment.DEFAULT_STIMULUS_DIR,
        help="directory containing the four required .osgt assets",
    )
    parser.add_argument(
        "--data-dir", default=MyExperiment.DEFAULT_DATA_DIR,
        help="parent directory for timestamped result folders",
    )
    parser.add_argument(
        "--validate-plan-only", action="store_true",
        help="build and validate the plan, print a summary, then exit",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.blocks <= 0:
        raise SystemExit("--blocks must be greater than zero")

    if args.validate_plan_only:
        plan, seed = build_trial_plan(args.blocks, args.seed)
        print("Plan valid: {} blocks, {} trials, seed {}".format(
            args.blocks, len(plan), seed
        ))
        return 0

    if HARDWARE_IMPORT_ERROR is not None:
        raise SystemExit(
            "LocustVR hardware modules could not be imported: {}\n"
            "Run this file on the LocustVR control computer or use "
            "--validate-plan-only.".format(HARDWARE_IMPORT_ERROR)
        )

    logging.basicConfig(level=logging.INFO)
    experiment = MyExperiment.new_osg2(debug=args.debug_display)
    experiment.number_of_blocks = args.blocks
    experiment.plan_seed = args.seed
    experiment.stimulus_dir = os.path.abspath(args.stimulus_dir)
    experiment.data_dir = os.path.abspath(args.data_dir)
    experiment.start(record=False)
    experiment.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
