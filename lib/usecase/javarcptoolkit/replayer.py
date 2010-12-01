
""" Basic replayer set up, although confusingly also sets up recorder...
    No Eclipse stuff should be imported at global scope """

import sys, os, usecase.guishared
import time, sys
from java.lang import Runnable, Thread

class TestRunner(Runnable):
    def __init__(self, method, *args):
        self.method = method
        self.args = args
            
    def run(self):
        # Eclipse uses a different class loader, set Jython's class loader
        # to use the same one, or things won't work
        sys.classLoader = Thread.currentThread().getContextClassLoader()
        self.method(*self.args)

        
class UseCaseReplayer(usecase.guishared.UseCaseReplayer):
    def tryAddDescribeHandler(self):
        # Set up used for recording
        runner = TestRunner(self.setUpMonitoring)
        recordExitRunner = TestRunner(self.uiMap.scriptEngine.replaceAutoRecordingForUsecase, "javarcp")
        self.setTestRunnables(runner, recordExitRunner)
    
    def enableReading(self):
        runner = TestRunner(self.runReplay)
        self.setTestRunnables(runner)

    def setTestRunnables(self, runner, exitRunner=None):
        from org.eclipse.swtbot.testscript import TestRunnableStore
        TestRunnableStore.setTestRunnables(runner, exitRunner)

    def setUpMonitoring(self):
        from simulator import WidgetMonitor, eventTypes
        monitor = WidgetMonitor()
        self.uiMap.scriptEngine.eventTypes = eventTypes
        for widget in monitor.findAllWidgets():
            self.uiMap.monitorWidget(widget)
        return monitor
    
    def runReplay(self):
        monitor = self.setUpMonitoring()
        self.runCommands(monitor)

    def runCommands(self, monitor):
        from describer import Describer
        theDescriber = Describer()
        while True:
            monitor.describe(theDescriber)
            if not self.runNextCommand():
                break
