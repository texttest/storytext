
from threading import Thread
import os, time

def poll_file(fileName, eventName, appEventMethod):
    eventName = eventName or fileName + " to be updated"
    startState = os.path.exists(fileName)
    class PollThread(Thread):
        def run(self):
            while os.path.exists(fileName) == startState:
                time.sleep(0.1)
            appEventMethod(eventName, category="file poll")
            
    thread = PollThread()
    thread.setDaemon(True)
    thread.start()
