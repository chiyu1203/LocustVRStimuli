## The original code was created by Sercan Sayin for the work published in Sayin et al., 2025
## modified by Jonathan Ernst and Chi-Yu Lee in 26/11/2025

### Things to do before running: create inter-stimulus interval. When the trial duration is fixed (e.g. the constant speed vs. constant distance experiment),
### this is implemented by adding random distribution of an interval on top of the trial duration.
### And then create a seperate iterator or counter to track the time within a trial including the inter-stimulus interval
import time
import threading
import logging
import sys
import shutil
import os
import random
import numpy as np
import datetime
import math
 
from multiprocessing import Process, Value
from ctypes import c_double

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from locustvr.experiment import ExperimentBase
from freemoovr.proxy.stimulus_osg import StimulusOSG2Controller
from realtime_orientation import get_orientation

# 2 speed, x 2 texture x 2 direction 
# list of speed x texture
# state 0 as pre choice phase
# state 1 means approaching from left ## need to confirm this 
# state 2 means approaching from right ## need to confirm this 
# texture 1 means gregarious texture
# texture 0 means black texture



class MyExperiment(ExperimentBase):

    def __init__(self, *args, **kwargs):
        ExperimentBase.__init__(self, *args, **kwargs)

        t = time.localtime()
        current_time = time.strftime("%H:%M:%S", t)
        print("INFO: START TIME is ", current_time)

        # Make sure no previous OSG objects are left over
        self.unload_all()

        self._olock = threading.Lock()

        # Shared memory for the focal heading (orientation of the animal)
        self.FocalAngle = Value(c_double, 0.0)
        self.process = Process(target=self.update_orientation)
        self.process.start()

        # For tracking world movement (used in move_world)
        self.prevworld = [0, 0]
        self.deltas = [0, 0]

    def run_forever(self):
        #time.sleep(300)# remind Jonny that we does not include the 5 min waiting period anymore
        timestamp_str = '{expdate:%Y%m%d_%H%M_%s}'.format(expdate=datetime.datetime.now())
        optional_suffix = "one_agent_collision"
        self.folder_path = sys.path[0] + '/../Data/' + timestamp_str + "_" + optional_suffix
        os.makedirs(self.folder_path)
        shutil.copy(os.path.abspath(__file__), self.folder_path + '/' + os.path.basename(__file__))
        self.output = self.folder_path + '/' + 'data' + '.dat'
        state = 0              # 0 = pre-choice (bait), 1/2 = choice phase (left/right)
        iterator = 0           # global loop counter
        trialNum = 0           # trial counter
        Trial_label = None     # label of current trial
        z_pos = 0.065

        # Flags for the test Locust
        #has_test = False       # becomes True once we spawned a test Locust. This boolean is not used yet.
        test_hidden = False    # True if test Locust is currently hidden
        reappeared = False     # True after it has reappeared on the other side
        # distance at which test Locust was first shown (TestDis)
        WorldBorder = 0.6
        ExperimentTime = 360000  # (60-minute experiment at 100 Hz)
        BaitDis = 0.12
        BaitSpeed = 0.0002
        TriggerDist = 0.08
        TestAngleBet = np.radians(90)
        ISI = random.randint(2500,3500) #this specify the end time point of Inter-stimulus Interval
        TestDis = 0.20     # spawn distances for test Locust
        SpeedInit = [0.0001,0.0004]    # test speeds (m/frame)
        TextureInit = [0,1] 

        

        # Distance threshold for hiding the test Locust
        hide_distance = 0.02  # m
        Repeats = 30
        base_conditions = list(
            np.array(np.meshgrid(TextureInit, SpeedInit)).T.reshape(-1, 2)
        )
        ConditionsInit = []
        for _ in range(Repeats):
            shuffled = base_conditions[:]
            random.shuffle(shuffled)
            ConditionsInit.extend(shuffled)
        ConditionsInit = np.array(ConditionsInit)

        # Toggle for left/right balancing (states 1 vs 2)
        base_toggle = [1, 2]
        ToggleInit = []
        for _ in range(Repeats * len(TextureInit) * len(SpeedInit)):
            toggle_pair = base_toggle[:]
            random.shuffle(toggle_pair)
            ToggleInit.append(toggle_pair)
        ToggleInit = np.array(ToggleInit)
        FocalHeading = self.FocalAngle.value 
        
        spdBaitx = BaitSpeed * np.cos(FocalHeading)
        spdBaity = BaitSpeed * np.sin(FocalHeading)
        posBaitx = BaitDis * np.cos(FocalHeading)
        posBaity = BaitDis * np.sin(FocalHeading)
        orientation_bait = FocalHeading + 1.57


        # Load base Locust model (used for cloning)
        Locust = self.load_osg('/home/loopbio/Documents/LocustVR2_2/Stimulus/Locust_066x.osgt')
        Locust.move(hidden=True)  # keep base object hidden
        Cylinder = self.load_osg('/home/loopbio/Documents/LocustVR2_2/Stimulus/greyworld_05.osgt') 
        Cylinder.move(0.0, 0.0, 0.0, hidden=False, scale=3)

        # Bait Locust
        Locust_preChoice = Locust.clone('bait', how='shallow')
        Locust_preChoice.move(posBaitx, posBaity, z_pos, orientation_z=orientation_bait, hidden=True)
        Locust_preChoice.animation_start('ArmatureAction')
        Locust_preChoice.move(posBaitx, posBaity, z_pos, orientation_z=orientation_bait, hidden=False)

        
        orientation_test = FocalHeading - 1.57
        pos1 = [100, 100]   # placeholder for test Locust position
        # Test Locust (for choice phase)
        Locust1 = Locust.clone('test', how='shallow')
        Locust1.move(pos1[0], pos1[1], z_pos, orientation_z= -1.57, hidden=True)
        #Locust1.animation_start('ArmatureAction')
        Locust2 = self.load_osg('/home/loopbio/Documents/LocustVR2_2/Stimulus/Locust_066x_black.osgt')
        Locust2.move(pos1[0], pos1[1], z_pos, orientation_z= -1.57, hidden=True)
        #Locust2.animation_start('ArmatureAction')

    
        while 1:
            FocalHeading = self.FocalAngle.value

            # Bait distance for logging and state 0 logic
            BaitPos = math.sqrt(posBaitx**2 + posBaity**2)
            if state == 0:
                Trial_label = None

                # Bait moves between TriggerDist and WorldBorder
                if TriggerDist < BaitPos < WorldBorder:
                    posBaitx += spdBaitx + self.deltas[0]
                    posBaity += spdBaity + self.deltas[1]
                    Locust_preChoice.move(posBaitx, posBaity, z_pos, orientation_z=orientation_bait, hidden=False)

                # If bait passes WorldBorder: respawn in front of the animal
                if WorldBorder < BaitPos:
                    spdBaitx = 0.0001 * np.cos(FocalHeading)
                    spdBaity = 0.0001 * np.sin(FocalHeading)
                    posBaitx = BaitDis * np.cos(FocalHeading)
                    posBaity = BaitDis * np.sin(FocalHeading)
                    orientation_bait = FocalHeading + 1.57
                
                    Locust_preChoice.move(posBaitx, posBaity, z_pos, orientation_z=orientation_bait, hidden=False)

                if TriggerDist > BaitPos:

                    # Select condition for this trial pair (distance and speed)
                    Condition = ConditionsInit[trialNum // 2]
                    LocustTexture = Condition[0]       # which texture to use in this trial
                    TestSpeed = Condition[1]     # movement speed of test Locust


                    ISI_end_distance = random.randint(2500,3500) * TestSpeed + TestDis

                    # Hide bait Locust
                    Locust_preChoice.move(posBaitx, posBaity, z_pos, orientation_z=orientation_bait, hidden=True)

                    print("Trial number (state 0): {}".format(trialNum))

                    # Left-right counterbalancing: state = 1 (left), 2 (right)
                    if trialNum % 2 == 0:
                        state = ToggleInit[trialNum // 2][0]
                    else:
                        state = ToggleInit[trialNum // 2][1]

                    # Determine spawn angle for the test Locust
                    if state == 1:
                        angle_test = FocalHeading - TestAngleBet   # left side
                        orientation_test = FocalHeading + 3.1415
                    else:
                        angle_test = FocalHeading + TestAngleBet   # right side
                        orientation_test = FocalHeading 

                    # Spawn test Locust at radial distance TestDis
                    pos1[0] = TestDis * np.cos(angle_test)
                    pos1[1] = TestDis * np.sin(angle_test)

                    # Movement direction towards the animal (radially inward)
                    spdTestx = -TestSpeed * np.cos(angle_test)
                    spdTesty = -TestSpeed * np.sin(angle_test)

                    # Initial distance at appearance
                    #has_test = True
                    test_hidden = False
                    reappeared = False

                    # Show test Locust at spawn position
                    if LocustTexture == 1:
                        Locust1.move(
                            pos1[0], pos1[1],
                            z_pos,
                            orientation_z=orientation_test,
                            hidden=False
                        )
                        Locust2.move(
                            pos1[0], pos1[1],
                            z_pos,
                            orientation_z=orientation_test,
                            hidden=True
                        )
                    else:
                        Locust1.move(
                            pos1[0], pos1[1],
                            z_pos,
                            orientation_z=orientation_test,
                            hidden=True
                        )
                        Locust2.move(
                            pos1[0], pos1[1],
                            z_pos,
                            orientation_z=orientation_test,
                            hidden=False
                        )

                    # Create label for saving
                    Trial_label = 'T{}_Texture{}_CS{}_S{}'.format(
                        trialNum,
                        LocustTexture,
                        round(TestSpeed * 10000),
                        state
                    )

                    print("State: {}".format(state))
                    print("LocustTexture: {} ".format(LocustTexture))
                    print("Speed: {} cm/s".format(TestSpeed * 10000))
                    print("Trial label: {}".format(Trial_label))
                    
            if state in (1, 2):

                # One step of movement along the same straight line
                pos1[0] += spdTestx
                pos1[1] += spdTesty
                #print(pos1[0],pos1[1])

                # Current radial distance from the origin (animal)
                current_distance_from_origin = math.sqrt(pos1[0]**2 + pos1[1]**2)
                #print(current_distance_from_origin)

                if not test_hidden:
                    # Visible part, moving towards center
                    if current_distance_from_origin <= hide_distance:
                        # Crossed inside the hide-threshold: hide test Locust
                        Locust1.move(
                            pos1[0], pos1[1],
                            z_pos,
                            orientation_z=orientation_test,
                            hidden=True
                        )
                        Locust2.move(
                            pos1[0], pos1[1],
                            z_pos,
                            orientation_z=orientation_test,
                            hidden=True
                        )
                        test_hidden = True

                    elif LocustTexture == 1:
                        # hide distance is smaller than the distance to origin so one of the agent appear
                        Locust1.move(
                            pos1[0], pos1[1],
                            z_pos,
                            orientation_z=orientation_test,
                            hidden=False
                        )
                        Locust2.move(
                            pos1[0], pos1[1],
                            z_pos,
                            orientation_z=orientation_test,
                            hidden=True
                        )
                    else:
                        Locust1.move(
                            pos1[0], pos1[1],
                            z_pos,
                            orientation_z=orientation_test,
                            hidden=True
                        )
                        Locust2.move(
                            pos1[0], pos1[1],
                            z_pos,
                            orientation_z=orientation_test,
                            hidden=False
                        )
                else:
                    # this section is after collision point
                    if not reappeared:
                        # from the start of collision point,current_distance_from_origin will start to increase until it pass the hide disstance
                        if current_distance_from_origin < hide_distance:
                            #still within the hide distance
                            Locust1.move(
                                pos1[0], pos1[1],
                                z_pos,
                                orientation_z=orientation_test,
                                hidden=True
                            )
                            Locust2.move(
                            pos1[0], pos1[1],
                            z_pos,
                            orientation_z=orientation_test,
                            hidden=True
                        )
                        elif LocustTexture == 1:
                            #one of the locusts reappeared
                            Locust1.move(
                                pos1[0], pos1[1],
                                z_pos,
                                orientation_z=orientation_test,
                                hidden=False
                            )
                            Locust2.move(
                                pos1[0], pos1[1],
                                z_pos,
                                orientation_z=orientation_test,
                                hidden=True
                            )
                            reappeared = True
                        else:
                            #one of the locusts reappeared
                            Locust1.move(
                                pos1[0], pos1[1],
                                z_pos,
                                orientation_z=orientation_test,
                                hidden=True
                            )
                            Locust2.move(
                                pos1[0], pos1[1],
                                z_pos,
                                orientation_z=orientation_test,
                                hidden=False
                            )
                            reappeared = True
                    else:
                        #from the start of reappearance, agent should keep its toward the same direction until it reaches the initial spawning distance.
                        if LocustTexture == 1:
                            Locust1.move(
                                pos1[0], pos1[1],
                                z_pos,
                                orientation_z=orientation_test,
                                hidden=False
                            )
                            Locust2.move(
                                pos1[0], pos1[1],
                                z_pos,
                                orientation_z=orientation_test,
                                hidden=True
                            )
                        else:
                            Locust1.move(
                                pos1[0], pos1[1],
                                z_pos,
                                orientation_z=orientation_test,
                                hidden=True
                            )
                            Locust2.move(
                                pos1[0], pos1[1],
                                z_pos,
                                orientation_z=orientation_test,
                                hidden=False
                            )

                        if ISI_end_distance > current_distance_from_origin >= TestDis:
                            Locust1.move(
                                pos1[0], pos1[1],
                                z_pos,
                                orientation_z=orientation_test,
                                hidden=True
                            )
                            Locust2.move(
                                pos1[0], pos1[1],
                                z_pos,
                                orientation_z=orientation_test,
                                hidden=True
                            )

                        if current_distance_from_origin >= ISI_end_distance:   
                            Locust1.move(
                                pos1[0], pos1[1],
                                z_pos,
                                orientation_z=orientation_test,
                                hidden=True
                            )
                            Locust2.move(
                                pos1[0], pos1[1],
                                z_pos,
                                orientation_z=orientation_test,
                                hidden=True
                            ) 
                            #has_test = False
                            test_hidden = False
                            reappeared = False
                            pos1 = [100, 100]  # moved the two agent to indicate the start of inter-stimulus_interval;

                            # Respawn bait Locust for the next pre-choice phase
                            spdBaitx = BaitSpeed * np.cos(FocalHeading)
                            spdBaity = BaitSpeed * np.sin(FocalHeading)
                            posBaitx = BaitDis * np.cos(FocalHeading)
                            posBaity = BaitDis * np.sin(FocalHeading)
                            orientation_bait = FocalHeading + 1.57
                        

                            Locust_preChoice.move(
                                posBaitx, posBaity,
                                z_pos,
                                orientation_z=orientation_bait,
                                hidden=False
                            )

                            # Prepare next trial: back to bait phase
                            state = 0
                            trialNum += 1
                            Trial_label = None
            with open(self.output, "a") as myfile:

                s = "{} {} {} {} {} {} {} {} {} {} {}\n".format(
                    self.deltas[0],
                    self.deltas[1],
                    FocalHeading,
                    time.time(),
                    trialNum,
                    state,
                    Trial_label,
                    pos1[0], pos1[1],
                    posBaitx, posBaity
                )
                myfile.write(s)
            time.sleep(0.01 - time.time() * 100 % 1 / 100)
            iterator += 1

            if (iterator % ExperimentTime) == 0:
                self.unload_all()
                self.process.terminate()
                exit()
    def move_world(self, x, y, z):
        with self._olock:
            if self.prevworld == [0, 0]:
                self.prevworld = [x, y]

            self.deltas[0] = x - self.prevworld[0]
            self.deltas[1] = y - self.prevworld[1]
            self.prevworld = [x, y]
    def update_orientation(self):
        for angle in get_orientation():
            self.FocalAngle.value = angle


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-d', '--debug-display',
        action='store_true',
        default=False,
        help='also run on the debug display server'
    )
    args = parser.parse_args()

    e = MyExperiment.new_osg2(debug=args.debug_display)
    e.start(record=False)
    e.run_forever()


