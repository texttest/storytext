
""" Don't load any Java stuff at global scope, needs to be importable by CPython also """

import usecase.guishared, os
from threading import Thread

class ScriptEngine(usecase.guishared.ScriptEngine):
    eventTypes = [] # Can't set them up until the Eclipse class loader is available
    signalDescs = {}
    def __init__(self, *args, **kw):
        self.testThread = None
        usecase.guishared.ScriptEngine.__init__(self, *args, **kw)
        
    def createReplayer(self, universalLogging=False):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder)

    def setTestThreadAction(self, method):
        self.testThread = Thread(target=method)
        
    def run_python_file(self, args):
        self.testThread.start()
        
        # Two options here: either a Jython program and hence a .py file, or a Java class
        # If it's a file, assume it's Python
        if os.path.isfile(args[0]):
            usecase.guishared.ScriptEngine.run_python_file(self, args)
        else:
            exec "from " + args[0] + " import Main"
            Main.main(args)

    def _createSignalEvent(self, eventName, eventDescriptor, widget, argumentParseData):
        for eventClass in self.findEventClassesFor(widget):
            if eventDescriptor in eventClass.getAssociatedSignatures(widget):
                return eventClass(eventName, widget, argumentParseData)

        
class UseCaseReplayer(usecase.guishared.UseCaseReplayer):
    def tryAddDescribeHandler(self):
        # Set up used for recording
        self.uiMap.scriptEngine.setTestThreadAction(self.setUpMonitoring)
    
    def enableReading(self):
        self.uiMap.scriptEngine.setTestThreadAction(self.runReplay)

    def setUpMonitoring(self):
        from org.eclipse.swtbot.swt.finder.utils import SWTUtils
        SWTUtils.waitForDisplayToAppear()
        from simulator import WidgetMonitor, eventTypes
        monitor = WidgetMonitor()
        monitor.forceShellActive()
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
