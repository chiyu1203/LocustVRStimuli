## The original code was created by Sercan Sayin for the work published in Sayin et al., 2025
## modified by Aljoscha Markus in 24/6/2025
## modified by Chi-Yu Lee in 26/11/2025
import time
import threading
import logging
import sys
import shutil
import os
import random
import numpy as np
import datetime
 
from multiprocessing import Process, Value
from ctypes import c_double

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from locustvr.experiment import ExperimentBase
from freemoovr.proxy.stimulus_osg import StimulusOSG2Controller
from realtime_orientation import get_orientation


class MyExperiment(ExperimentBase):

    def __init__(self, *args, **kwargs):
        ExperimentBase.__init__(self, *args, **kwargs)

        t = time.localtime()
        current_time = time.strftime("%H:%M:%S", t)
        print("INFO: START TIME is ", current_time)

        self.unload_all()  

        self._olock = threading.Lock()
        
        self.FocalAngle = Value(c_double, 0.0)  # Shared memory
        self.process = Process(target=self.update_orientation)
        self.process.start()
 

        self.prevworld = [0,0]
        self.deltas = [0,0]
        
 

    def run_forever(self):
        #time.sleep(300) 
        # init result folder for experiment
        timestamp_str =  '{expdate:%Y%m%d_%H%M_%s}'.format(expdate=datetime.datetime.now())
        optional_suffix = "constant_speed_vs_constant_distance"
        self.folder_path = sys.path[0]  + '/../Data/'+ timestamp_str + "_" + optional_suffix
        os.makedirs(self.folder_path) 
        shutil.copy(os.path.abspath(__file__), self.folder_path + '/' + os.path.basename(__file__))
        self.output = self.folder_path + '/' + 'data' + '.dat'

        state = 0
        iterator = 0
        iterator2 = 0
        trialNum = 0
        Trial_label = None # Lable of trial

        WorldBorder = 0.30
        TestTime = 3000 #(the time of trial in sec * 100 Hz)
        ISI = TestTime + random.randint(2500,3500) #this specify the end time point of Inter-stimulus Interval
        ExperimentTime = 360000 #(60-minute experiment at 100Hz)
        
        #parameters for pre choice phase
        BaitDis = 0.12
        BaitSpeed = 0.0002
        TriggerDist = 0.08
        #TestDisLateral = 0.25
        #TestDis = 0.1
        #TestAngleBet = np.arctan2(TestDisLateral/2,TestDis)
        #TestSpeed = 0.0001


        #parameters for choice phase
        TestAngleBet = np.radians(60)
        DistancesInit = [0.1, 0.06] # m
        SpeedInit = [0.000001,0.0001, 0.0005] # meter/frame
        
        #parameters for randomise parameter combinations
        Repeats = 30
        #Here to randomly shuffle the combination of different parameters
        base_conditions = list(np.array(np.meshgrid(DistancesInit, SpeedInit)).T.reshape(-1, 2))
        ConditionsInit = []
        for a in range(Repeats):
            shuffled = base_conditions[:]
            random.shuffle(shuffled)
            ConditionsInit.extend(shuffled)
        ConditionsInit = np.array(ConditionsInit)
        #print(ConditionsInit)

        base_toggle = [1, 2]
        ToggleInit = []
        for i in range(Repeats * len(DistancesInit)*len(SpeedInit)):
            toggle_pair = base_toggle[:]
            random.shuffle(toggle_pair)
            ToggleInit.append(toggle_pair)
        ToggleInit = np.array(ToggleInit)

        #print(ToggleInit)
        #Doucle check the following code  about randomising the position of the biat animal in the pre-choice phase
        FocalHeading = self.FocalAngle.value 
        
        spdBaitx = BaitSpeed * np.cos(FocalHeading)
        spdBaity = BaitSpeed * np.sin(FocalHeading)
        posBaitx = BaitDis * np.cos(FocalHeading)
        posBaity = BaitDis * np.sin(FocalHeading)
        orientation = FocalHeading + 1.57

        #Doucle check the above code about randomising the position of the biat animal in the pre-choice phase
        pos1 = [100,100]
        pos2 = [100,100]

        Locust = self.load_osg('/home/loopbio/Documents/LocustVR2_2/Stimulus/Locust.osgt')
        Locust.move(hidden=True)


        name = 'copy' + str(1)
        Locust1 = Locust.clone(name, how='shallow')
        Locust1.move(pos1[0],pos1[1], 0.06, orientation_z = 1.57, hidden=True)
        Locust1.animation_start('ArmatureAction')

        name = 'copy' + str(2)
        Locust2 = Locust.clone(name, how='shallow')
        Locust2.move(pos2[0],pos2[1], 0.06, orientation_z = 1.57, hidden=True)
        Locust2.animation_start('ArmatureAction')

        name = 'copy' + str(3)
        Locust_preChoice = Locust.clone(name, how='shallow')
        Locust_preChoice.move(posBaitx,posBaity, 0.06, orientation_z = orientation, hidden=True)
        Locust_preChoice.animation_start('ArmatureAction')


        Locust_preChoice.move(posBaitx,posBaity, 0.06, orientation_z = orientation, hidden = False)


        while 1:
            FocalHeading = self.FocalAngle.value 
            if state == 0:#pre choice phase
                Trial_label = None
                #trial += 1
                BaitPos = np.sqrt(posBaitx**2+posBaity**2)

                if TriggerDist < BaitPos < WorldBorder: 

                    posBaitx += spdBaitx + self.deltas[0]
                    posBaity += spdBaity + self.deltas[1]
                    Locust_preChoice.move(posBaitx,posBaity, 0.06, orientation_z = orientation, hidden = False)

                if WorldBorder < BaitPos: 


                    #FocalHeading = self.FocalAngle.value 
                    
                    spdBaitx = 0.0001 * np.cos(FocalHeading)
                    spdBaity = 0.0001 * np.sin(FocalHeading)
                    posBaitx = BaitDis * np.cos(FocalHeading)
                    posBaity = BaitDis * np.sin(FocalHeading)
                    orientation = FocalHeading + 1.57
                    Locust_preChoice.move(posBaitx,posBaity, 0.06, orientation_z = orientation, hidden=False)

                if TriggerDist > BaitPos:


                    # select the condition for this and the left-right counterblance trial
                    Condition = ConditionsInit[trialNum // 2]
                    TestDis = Condition[0]
                    TestSpeed = Condition[1]

                    posCx, posCy = 100, 100
                    Locust_preChoice.move(posBaitx,posBaity, 0.06, orientation_z = orientation, hidden = True)

                    

                    pos1[0] = TestDis *np.cos(FocalHeading-TestAngleBet) 
                    pos1[1] = TestDis *np.sin(FocalHeading-TestAngleBet) 
                    pos2[0] = TestDis *np.cos(FocalHeading+TestAngleBet) 
                    pos2[1] = TestDis *np.sin(FocalHeading+TestAngleBet) 
                                        
                    orientation1 = FocalHeading + 1.57 - TestAngleBet
                    orientation2 = FocalHeading + 1.57 + TestAngleBet

                    Locust1.move(pos1[0],pos1[1], 0.06, orientation_z = orientation1,hidden = False)
                    Locust2.move(pos2[0],pos2[1], 0.06, orientation_z = orientation2,hidden = False)
                    print("Trial number (state 0): {}".format(trialNum))
                    
                    # select symetry
                    if trialNum % 2 == 0:
                        state = ToggleInit[trialNum // 2][0]
                    else:
                        state = ToggleInit[trialNum // 2][1]

                    if state == 1:
                        spdTestx = TestSpeed * np.cos(FocalHeading-TestAngleBet)
                        spdTesty = TestSpeed * np.sin(FocalHeading-TestAngleBet)
                    else:
                        spdTestx = TestSpeed * np.cos(FocalHeading+TestAngleBet)
                        spdTesty = TestSpeed * np.sin(FocalHeading+TestAngleBet)

                    Trial_label = 'T{}_CD{}_CS{}_S{}'.format(trialNum, round(TestDis * 100), round(TestSpeed * 10000), state)

                    print('Trial number: {}'.format(trialNum))
                    print("State: {}".format(state))
                    print("Distance: {} cm".format(TestDis * 100))
                    print("Speed: {} cm/s".format(TestSpeed * 10000))
                    print("Trial lable: {}".format(Trial_label))

                    #trialNum += 1

            if state == 1:
                if iterator2 < TestTime:
                    
                    pos1[0] += spdTestx
                    pos1[1] += spdTesty

                    Locust1.move(pos1[0],pos1[1], 0.06, orientation_z = orientation1,hidden = False)# constant speed group
                    Locust2.move(pos2[0],pos2[1], 0.06, orientation_z = orientation2,hidden = False)# constant distance group

                    iterator2 += 1

                if TestTime <= iterator2 < ISI:

                    pos1 = [100,100]
                    pos2 = [100,100] 
                    Locust1.move(pos1[0],pos1[1], 0.06, orientation_z = orientation1,hidden = True)
                    Locust2.move(pos2[0],pos2[1], 0.06, orientation_z = orientation2,hidden = True)

                    iterator2 += 1

                if iterator2 == ISI: 

                    #FocalHeading = self.FocalAngle.value 

                    spdBaitx = TestSpeed * np.cos(FocalHeading)
                    spdBaity = TestSpeed * np.sin(FocalHeading)
                    posBaitx = BaitDis * np.cos(FocalHeading)
                    posBaity = BaitDis * np.sin(FocalHeading)
                    orientation = FocalHeading + 1.57

                    Locust_preChoice.move(posBaitx,posBaity, 0.06, orientation_z = orientation, hidden=False)

                    iterator2 = 0
                    state = 0

                    trialNum += 1
                    Trial_label = None

            if state == 2:
                if iterator2 < TestTime:
                    
                    pos2[0] += spdTestx
                    pos2[1] += spdTesty

                    Locust1.move(pos1[0],pos1[1], 0.06, orientation_z = orientation1,hidden = False)
                    Locust2.move(pos2[0],pos2[1], 0.06, orientation_z = orientation2,hidden = False)

                    iterator2 += 1

                if TestTime <= iterator2 < ISI:

                    pos1 = [100,100]
                    pos2 = [100,100] 
                    Locust1.move(pos1[0],pos1[1], 0.06, orientation_z = orientation1,hidden = True)
                    Locust2.move(pos2[0],pos2[1], 0.06, orientation_z = orientation2,hidden = True)


                    iterator2 += 1

                if iterator2 == ISI: 
                    
                    #FocalHeading = self.FocalAngle.value 

                    spdBaitx = TestSpeed * np.cos(FocalHeading)
                    spdBaity = TestSpeed * np.sin(FocalHeading)
                    posBaitx = BaitDis * np.cos(FocalHeading)
                    posBaity = BaitDis * np.sin(FocalHeading)
                    orientation = FocalHeading + 1.57

                    Locust_preChoice.move(posBaitx,posBaity, 0.06, orientation_z = orientation, hidden=False)
                    
                    iterator2 = 0
                    state = 0

                    trialNum += 1
                    Trial_label = None

            with open(self.output, "a") as myfile:
                    #s = "{} {} {} {} {} {} {} {} {} {} {}\n".format(posBaitx, posBaity, pos1[0], pos1[1], pos2[0], pos2[1], self.deltas[0], self.deltas[1], trialNum, state, time.time())
                    s = "{} {} {} {} {} {} {} {} {} {} {} {} {}\n".format(self.deltas[0], self.deltas[1],FocalHeading,time.time(),trialNum, state, Trial_label,pos1[0], pos1[1], pos2[0], pos2[1],posBaitx, posBaity)
                    myfile.write(s) 

            time.sleep(0.01-time.time()*100%1/100)
            iterator += 1


            if(iterator % ExperimentTime == 0): #using the residual as a readout to see if the time is over
                self.unload_all()
                self.process.terminate()  
                exit()            
  
    #store locust position and call super class to move the osg file
    def move_world(self, x, y, z):
        with self._olock:  
            if self.prevworld == [0,0]:
                self.prevworld = [x,y]  

            self.deltas[0] = x-self.prevworld[0]
            self.deltas[1] = y-self.prevworld[1]
            self.prevworld = [x,y]

    def update_orientation(self):
        for angle in get_orientation():
            self.FocalAngle.value = angle
 
if __name__ == '__main__':
    import argparse

    # self._motif.call()
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--debug-display', action='store_true', default=False,
                        help='also run on the debug display server')
    args = parser.parse_args()

    e = MyExperiment.new_osg2(debug=args.debug_display)
    e.start(record=False)
    e.run_forever()