
import usecase.guishared, time, os
from javax import swing
from java.awt import Frame
import simulator, describer, util

    
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
        (swing.JTable       , [ simulator.TableSelectEvent, simulator.CellDoubleClickEvent, simulator.CellEditEvent]),
        (swing.table.JTableHeader   , [ simulator.TableHeaderEvent, simulator.HeaderDoubleClickEvent]),
        (swing.text.JTextComponent  , [ simulator.TextEditEvent]),
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

        self.replayer.runTestThread()
        
    def checkType(self, widget):
        return any((isinstance(widget, clazz) for clazz in [type for type,signals in self.eventTypes]))

class UseCaseReplayer(usecase.guishared.ThreadedUseCaseReplayer):
    def __init__(self, *args, **kw):
        usecase.guishared.ThreadedUseCaseReplayer.__init__(self, *args, **kw)
        self.describer = describer.Describer()
        self.filter = simulator.Filter(self.uiMap)
        self.filter.startListening(self.handleNewComponent)

    def handleNewComponent(self, widget):
        inWindow = isinstance(widget, swing.JComponent) and widget.getTopLevelAncestor() is not None and \
                   widget.getTopLevelAncestor() in self.uiMap.windows
        isWindow = isinstance(widget, (swing.JFrame, swing.JDialog))
        if self.uiMap and (self.isActive() or self.recorder.isActive()):
            if isWindow:
                self.uiMap.monitorAndStoreWindow(widget)
            elif inWindow:
                self.uiMap.monitor(usecase.guishared.WidgetAdapter.adapt(widget))
        if self.loggerActive and (isWindow or inWindow):
            self.describer.setWidgetShown(widget)

    def describe(self):
        util.runOnEventDispatchThread(self.describer.describeWithUpdates)

    def runTestThread(self):
        while not self.frameShowing():
            time.sleep(0.1)
                
        if self.isActive():
            self.describeAndRun(self.describe)
        else: # pragma: no cover - replayer disabled, cannot create automated tests
            while self.frameShowing():
                time.sleep(0.1)

    def frameShowing(self): # pragma: no cover - replayer disabled, cannot create automated tests
        return any((frame.isShowing() for frame in Frame.getFrames()))
