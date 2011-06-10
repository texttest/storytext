
""" Don't load any Java stuff at global scope, needs to be importable by CPython also """

import usecase.guishared, os, types
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

    def getDescriptionInfo(self):
        return "SWT", "javaswt", "event types", \
               "http://help.eclipse.org/helios/index.jsp?topic=/org.eclipse.platform.doc.isv/reference/api/"

    def getDocName(self, className):
        return className.replace(".", "/")
    
    def getRecordReplayInfo(self, module):
        from simulator import WidgetMonitor
        info = {}
        for widgetClass, eventTypes in WidgetMonitor.getWidgetEventTypeNames():
            className = self.getClassName(widgetClass, module)
            info[className] = sorted(eventTypes)
        return info

    def getClassName(self, widgetClass, *args):
        return widgetClass.__module__ + "." + widgetClass.__name__

    def getClassNameColumnSize(self):
        return 40 # seems to work, mostly

    def getSupportedLogWidgets(self):
        from describer import Describer
        return Describer.statelessWidgets + Describer.stateWidgets

        
class UseCaseReplayer(usecase.guishared.ThreadedUseCaseReplayer):
    def __init__(self, *args):
        # Set up used for recording
        usecase.guishared.ThreadedUseCaseReplayer.__init__(self, *args)
        self.setThreadCallbacks()

    def setThreadCallbacks(self):
        if self.isActive():
            self.uiMap.scriptEngine.setTestThreadAction(self.runReplay)
        else:
            self.uiMap.scriptEngine.setTestThreadAction(self.setUpMonitoring)

    def getMonitorClass(self):
        from simulator import WidgetMonitor
        return WidgetMonitor

    def setUpMonitoring(self):
        from org.eclipse.swtbot.swt.finder.utils import SWTUtils
        SWTUtils.waitForDisplayToAppear()
        monitor = self.getMonitorClass()(self.uiMap)
        monitor.setUp()
        return monitor
    
    def runReplay(self):
        monitor = self.setUpMonitoring()
        from simulator import runOnUIThread
        # Can't make this a member, otherwise fail with classloader problems for RCP
        describer = self.getDescriberClass()()
        runOnUIThread(describer.addFilters, monitor.getDisplay())
        def describe():
            runOnUIThread(describer.describeWithUpdates, monitor.getActiveShell())
        self.describeAndRun(describe)

    def getDescriberClass(self):
        from describer import Describer
        return Describer
