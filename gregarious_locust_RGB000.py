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
#from realtime_orientation import get_orientation




class MyExperiment(ExperimentBase):

    def __init__(self, *args, **kwargs):
        ExperimentBase.__init__(self, *args, **kwargs)

        t = time.localtime()
        current_time = time.strftime("%H:%M:%S", t)
        print("INFO: START TIME is ", current_time)

        self.unload_all()  

        self._olock = threading.Lock()
        
        #self.FocalAngle = Value(c_double, 0.0)  # Shared memory
        #self.process = Process(target=self.update_orientation)
        #self.process.start()
 

        self.prevworld = [0,0]
        self.deltas = [0,0]
        
 

    def run_forever(self):


        self.Cylinder = self.load_osg('/home/loopbio/Documents/LocustVR2_2/Stimulus/greyworld.osgt') 
        time.sleep(10) 
        self.Cylinder.move(0.0, 0.0, 0.0, hidden=False, scale=3)

        state = 0
        iterator = 0
        iterator2 = 0
        trialNum = 0

        WorldBorder = 0.30
        BaitDis = 0.04
        BaitSpeed = 0.0000000000001
        TriggerDist = 0.08
        TestDisLateral = 0.25
        TestDis = 0.1
        TestAngleBet = np.arctan2(TestDisLateral/2,TestDis)
        TestSpeed = 0.0001
        TestTime = 6000
        ISI = TestTime + random.randint(2500,3500)
        ExperimentTime = 120000 #(60sec*100Hz*20,minutes)

        FocalHeading = 0
        
        spdBaitx = BaitSpeed * np.cos(FocalHeading)
        spdBaity = BaitSpeed * np.sin(FocalHeading)
        posBaitx = BaitDis * np.cos(FocalHeading)
        posBaity = BaitDis * np.sin(FocalHeading)
        orientation = FocalHeading + 1.57



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
        LocustC = Locust.clone(name, how='shallow')
        LocustC.move(posBaitx,posBaity, 0.06, orientation_z = orientation, hidden=True)
        LocustC.animation_start('ArmatureAction')


        LocustC.move(posBaitx,posBaity, 0.06, orientation_z = orientation, hidden = False)


        while 1:

            if state == 0:
                
                BaitPos = np.sqrt(posBaitx**2+posBaity**2)

                if TriggerDist < BaitPos < WorldBorder: 

                    posBaitx += spdBaitx + self.deltas[0]
                    posBaity += spdBaity + self.deltas[1]
                    LocustC.move(posBaitx,posBaity, 0.06, orientation_z = orientation, hidden = False)

                if WorldBorder < BaitPos: 


                    FocalHeading = 0
                    
                    spdBaitx = 0.0001 * np.cos(FocalHeading)
                    spdBaity = 0.0001 * np.sin(FocalHeading)
                    posBaitx = BaitDis * np.cos(FocalHeading)
                    posBaity = BaitDis * np.sin(FocalHeading)
                    orientation = FocalHeading + 1.57
                    LocustC.move(posBaitx,posBaity, 0.06, orientation_z = orientation, hidden=False)

                if TriggerDist > BaitPos: 

                    posCx, posCy = 100, 100
                    LocustC.move(posBaitx,posBaity, 0.06, orientation_z = orientation, hidden = True)

                    FocalHeading = 0

                    pos1[0] = TestDis *np.cos(FocalHeading-TestAngleBet) 
                    pos1[1] = TestDis *np.sin(FocalHeading-TestAngleBet) 
                    pos2[0] = TestDis *np.cos(FocalHeading+TestAngleBet) 
                    pos2[1] = TestDis *np.sin(FocalHeading+TestAngleBet) 
                                        
                    orientation1 = FocalHeading + 1.57 - TestAngleBet
                    orientation2 = FocalHeading + 1.57 + TestAngleBet

                    Locust1.move(pos1[0],pos1[1], 0.06, orientation_z = orientation1,hidden = False)
                    Locust2.move(pos2[0],pos2[1], 0.06, orientation_z = orientation2,hidden = False)


                    trialNum += 1
                    if trialNum % 2 ==0:
                        state = 1
                        spdTestx = TestSpeed * np.cos(FocalHeading-TestAngleBet)
                        spdTesty = TestSpeed * np.sin(FocalHeading-TestAngleBet)
                    else:
                        state = 2
                        spdTestx = TestSpeed * np.cos(FocalHeading+TestAngleBet)
                        spdTesty = TestSpeed * np.sin(FocalHeading+TestAngleBet)

  
            time.sleep(0.01-time.time()*100%1/100)
            iterator += 1


            if(iterator % ExperimentTime == 0): #20 min
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

    #def update_orientation(self):
    #    for angle in get_orientation():
    #        self.FocalAngle.value = angle
 
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



