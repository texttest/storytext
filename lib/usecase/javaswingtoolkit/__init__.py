
import usecase.guishared, time
from javax import swing
from java.awt import Frame
import SwingLibrary
import simulator

simulator.swinglib = SwingLibrary()
    
class ScriptEngine(usecase.guishared.ScriptEngine):
    eventTypes = [
        (swing.JFrame       , [ simulator.FrameCloseEvent ]),
        (swing.JButton      , [ simulator.SelectEvent ]),
        (swing.JRadioButton , [ simulator.SelectEvent]),
        (swing.JCheckBox    , [ simulator.SelectEvent]),
        (swing.JMenuItem    , [ simulator.MenuSelectEvent]),
        (swing.JTabbedPane  , [ simulator.TabSelectEvent]),
        (swing.JDialog       , [ simulator.FrameCloseEvent ]),
        ]
    
    def __init__(self, *args, **kw):
        usecase.guishared.ScriptEngine.__init__(self, *args, **kw)
        
    def createReplayer(self, universalLogging=False):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder)
    
    def run_python_file(self, *args):
        usecase.guishared.ScriptEngine.run_python_file(self, *args)
        if self.replayerActive():
            simulator.swinglib.runKeyword("selectMainWindow", [])
            self.replayer.describeAndRun()
        else:
            self.replayer.handleNewWindows()           
            while self.shouldWait() :
                time.sleep(0.1)
                   
    def _createSignalEvent(self, eventName, eventDescriptor, widget, argumentParseData):
        # TODO: identical to code in SWT and wx, very similar to Tkinter, refactor!
        for eventClass in self.findEventClassesFor(widget):
            if eventDescriptor in eventClass.getAssociatedSignatures(widget):
                return eventClass(eventName, widget, argumentParseData)
                
    def shouldWait(self):
#        showing = True
#        fr = Frame.getFrames()
#        count = len(fr)
        return any((frame.isShowing() for frame in Frame.getFrames()))
#        for i in range(count):
#            if not fr[i].isShowing():
#                showing = False
#                break
#        return showing
           
class UseCaseReplayer(usecase.guishared.UseCaseReplayer):
    def __init__(self, *args, **kw):
        usecase.guishared.UseCaseReplayer.__init__(self, *args, **kw)
        self.describer = self.getDescriberClass()()
        
    def enableReplayHandler(self, *args):
        pass
           
    def tryAddDescribeHandler(self):
        from simulator import Filter
        self.filter = Filter()
        self.filter.startListening()
    
    def describeAndRun(self):
        self.handleNewWindows()
        while True:
            #runOnUIThread(theDescriber.describeWithUpdates, monitor.getActiveShell())
            if self.delay:
                time.sleep(self.delay)
            if not self.runNextCommand():
                break
                
    def findWindowsForMonitoring(self):
        return Frame.getFrames()
    
    def describeNewWindow(self, frame):
        self.describer.describe(frame)

    def getDescriberClass(self):
        from describer import Describer
        return Describer
    
        