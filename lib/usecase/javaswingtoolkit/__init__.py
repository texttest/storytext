
import usecase.guishared, time, os
from javax import swing
from java.awt import Frame
import simulator, util

    
class ScriptEngine(usecase.guishared.ScriptEngine):
    eventTypes = [
        (swing.JFrame       , [ simulator.FrameCloseEvent ]),
        (swing.JButton      , [ simulator.ButtonClickEvent ]),
        (swing.JRadioButton , [ simulator.SelectEvent]),
        (swing.JCheckBox    , [ simulator.SelectEvent]),
        (swing.JMenuItem    , [ simulator.MenuSelectEvent]),
        (swing.JTabbedPane  , [ simulator.TabSelectEvent]),
        (swing.JDialog      , [ simulator.FrameCloseEvent ]),
        (swing.JList        , [ simulator.ListSelectEvent]),
        (swing.JTable       , [ simulator.TableSelectEvent]),
        ]
    
    def createReplayer(self, universalLogging=False):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder)
    
    def run_python_file(self, args):
        # Two options here: either a Jython program and hence a .py file, or a Java class
        # If it's a file, assume it's Python
        if os.path.isfile(args[0]):
            usecase.guishared.ScriptEngine.run_python_file(self, args)
        else:
            exec "import " + args[0] + " as _className"
            _className.main(args)

        while not self.frameShowing():
            time.sleep(0.1)
                
        if self.replayerActive():
            self.replayer.describeAndRun()
        else: # pragma: no cover - replayer disabled, cannot create automated tests
            self.replayer.handleNewWindows()
            while self.frameShowing():
                time.sleep(0.1)

    def frameShowing(self): # pragma: no cover - replayer disabled, cannot create automated tests
        return any((frame.isShowing() for frame in Frame.getFrames()))
           
class UseCaseReplayer(usecase.guishared.UseCaseReplayer):
    def __init__(self, *args, **kw):
        self.waiting = False
        self.describer = self.getDescriberClass()()
        usecase.guishared.UseCaseReplayer.__init__(self, *args, **kw)
        
        
    def enableReplayHandler(self, *args):
        pass
           
    def tryAddDescribeHandler(self):
        self.filter = simulator.Filter(self.uiMap)
        self.filter.startListening()
        
    def describeAndRun(self):
        if self.waiting:
            self.waitForReenable()
        while True:
            util.runOnEventDispatchThread(self.describer.describeWithUpdates)
            if self.delay:
                time.sleep(self.delay)
            if not self.runNextCommand():
                self.waiting = not self.waitingCompleted()
                if self.waiting:
                    self.waitForReenable()
                else:
                    break

    def enableReading(self):
        if self.waiting:
            self.waiting = False
            
    def waitForReenable(self):
        self.logger.debug("Waiting for replaying to be re-enabled...")
        while self.waiting:
            time.sleep(0.1) # don't use the whole CPU while waiting

                
    def findWindowsForMonitoring(self):
        return []

    def getDescriberClass(self):
        from describer import Describer
        return Describer
    
    def handleNewWindow(self, window):
        if self.uiMap and (self.isActive() or self.recorder.isActive()):
            self.uiMap.monitorAndStoreWindow(window)
        if self.loggerActive:
            self.describer.setWidgetShown(window)

    def handleNewWidget(self, widget):
        if self.uiMap and (self.isActive() or self.recorder.isActive()):
            self.uiMap.monitor(usecase.guishared.WidgetAdapter.adapt(widget))
        if self.loggerActive:
            self.describer.setWidgetShown(widget)
