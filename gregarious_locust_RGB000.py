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

class MyExperiment(ExperimentBase):

    def __init__(self, *args, **kwargs):
        ExperimentBase.__init__(self, *args, **kwargs)
        t = time.localtime()
        current_time = time.strftime("%H:%M:%S", t)
        print("INFO: START TIME is ", current_time)
        self.unload_all()  
        self._olock = threading.Lock()
        self.prevworld = [0,0]
        self.deltas = [0,0]

    def run_forever(self):
        BaitDis = 0.04
        FocalHeading = 0
        posBaitx = BaitDis * np.cos(FocalHeading)
        posBaity = BaitDis * np.sin(FocalHeading)
        orientation = FocalHeading - 1.57
        Locust = self.load_osg('/home/loopbio/Documents/LocustVR2_2/Stimulus/Locust.osgt')
        time.sleep(10) 
        Locust.move(posBaitx,posBaity, 0.06, orientation_z = orientation, hidden=False)
        self.Cylinder = self.load_osg('/home/loopbio/Documents/LocustVR2_2/Stimulus/greyworld.osgt') 
        time.sleep(10) 
        self.Cylinder.move(0.0, 0.0, 0.0, hidden=False, scale=3)

        try:
            while True:
                print("present a locust")
        except KeyboardInterrupt:
            self.unload_all()
            self.process.terminate()  
            exit()            
  
    #store locust position and call super class to move the osg file
    # def move_world(self, x, y, z):
    #     with self._olock:  
    #         if self.prevworld == [0,0]:
    #             self.prevworld = [x,y]  

    #         self.deltas[0] = x-self.prevworld[0]
    #         self.deltas[1] = y-self.prevworld[1]
    #         self.prevworld = [x,y]

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



