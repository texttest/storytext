
""" Don't load any Java stuff at global scope, needs to be importable by CPython also """

import storytext.guishared, os, types
from threading import Thread

class ScriptEngine(storytext.guishared.ScriptEngine):
    eventTypes = [] # Can't set them up until the Eclipse class loader is available
    signalDescs = {}
    def __init__(self, *args, **kw):
        self.testThread = None
        storytext.guishared.ScriptEngine.__init__(self, *args, **kw)
        
    def createReplayer(self, universalLogging=False, **kw):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder, **kw)

    def setTestThreadAction(self, method):
        self.testThread = Thread(target=method)
        
    def runSystemUnderTest(self, args):
        self.testThread.start()
        self.run_python_or_java(args)
        
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

        
class UseCaseReplayer(storytext.guishared.ThreadedUseCaseReplayer):
    def __init__(self, *args, **kw):
        # Set up used for recording
        storytext.guishared.ThreadedUseCaseReplayer.__init__(self, *args, **kw)
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
        # (replayer constructed before Eclipse classloader set)
        describer = self.getDescriberClass()()
        runOnUIThread(describer.addFilters, monitor.getDisplay())
        def describe():
            runOnUIThread(describer.describeWithUpdates, monitor.getActiveShell)
        self.describeAndRun(describe, monitor.handleReplayFailure)

    def getDescriberClass(self):
        try:
            from draw2ddescriber import Describer
            return Describer
        except ImportError:
            from describer import Describer
            return Describer
