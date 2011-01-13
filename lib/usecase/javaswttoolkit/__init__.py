
""" Don't load any Java stuff at global scope, needs to be importable by CPython also """

import usecase.guishared, os, time
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
            exec "import " + args[0] + " as _className"
            _className.main(args)

    def _createSignalEvent(self, eventName, eventDescriptor, widget, argumentParseData):
        for eventClass in self.findEventClassesFor(widget):
            if eventDescriptor in eventClass.getAssociatedSignatures(widget):
                return eventClass(eventName, widget, argumentParseData)

        
class UseCaseReplayer(usecase.guishared.UseCaseReplayer):
    def __init__(self, *args, **kw):
        self.waiting = False
        usecase.guishared.UseCaseReplayer.__init__(self, *args, **kw)
        
    def tryAddDescribeHandler(self):
        # Set up used for recording
        self.uiMap.scriptEngine.setTestThreadAction(self.setUpMonitoring)

    def addScript(self, script):
        # Don't process initial application events any differently
        # We need to make sure the replay thread actually hangs around to do something
        self.scripts.append(script)
        self.enableReading()
            
    def enableReading(self):
        if self.waiting:
            self.waiting = False
        else:
            self.enableReplayInitially()

    def enableReplayInitially(self):
        self.uiMap.scriptEngine.setTestThreadAction(self.runReplay)

    def createMonitor(self, botClass=None):
        from org.eclipse.swtbot.swt.finder.utils import SWTUtils
        SWTUtils.waitForDisplayToAppear()
        from simulator import WidgetMonitor
        return WidgetMonitor(self.uiMap, botClass)

    def setUpMonitoring(self):
        monitor = self.createMonitor()
        monitor.setUp()
        return monitor
    
    def runReplay(self):
        monitor = self.setUpMonitoring()
        self.runCommands(monitor)

    def runCommands(self, monitor):
        from describer import Describer
        theDescriber = Describer()
        while True:
            monitor.describe(theDescriber)
            if self.delay:
                time.sleep(self.delay)
            if not self.runNextCommand():
                if self.waitingCompleted():
                    break
                else:
                    self.logger.debug("Waiting for replaying to be re-enabled...")
                    self.waitForReenable()

    def waitForReenable(self):
        self.waiting = True
        while self.waiting:
            time.sleep(0.1) # don't use the whole CPU while waiting
