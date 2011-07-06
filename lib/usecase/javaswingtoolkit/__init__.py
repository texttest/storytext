import usecase.guishared, time, os
from javax import swing
from java.awt import Frame
import simulator, describer, util

    
class ScriptEngine(usecase.guishared.ScriptEngine):
    eventTypes = [
        (swing.JFrame       , [ simulator.FrameCloseEvent ]),
        (swing.JButton      , [ simulator.ButtonClickEvent ]),
        (swing.JRadioButton , [ simulator.SelectEvent ]),
        (swing.JCheckBox    , [ simulator.SelectEvent ]),
        (swing.JMenuItem    , [ simulator.MenuSelectEvent ]),
        (swing.JTabbedPane  , [ simulator.TabSelectEvent]),
        (swing.JDialog      , [ simulator.FrameCloseEvent ]),
        (swing.JList        , [ simulator.ListSelectEvent ]),
        (swing.JTable       , [ simulator.TableSelectEvent, simulator.CellDoubleClickEvent, simulator.CellEditEvent ]),
        (swing.table.JTableHeader   , [ simulator.TableHeaderEvent ]),
        (swing.text.JTextComponent  , [ simulator.TextEditEvent ]),
        (swing.JTextField  , [ simulator.TextEditEvent, simulator.TextActivateEvent ]),
        ]
    
    def createReplayer(self, universalLogging=False):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder)
    
    def runSystemUnderTest(self, args):
        self.run_python_or_java(args)
        self.replayer.runTestThread()
        
    def checkType(self, widget):
        return any((isinstance(widget, clazz) for clazz in [type for type,signals in self.eventTypes]))

    def getDescriptionInfo(self):
        return "Swing", "javaswing", "event types", \
               "http://download.oracle.com/javase/6/docs/api/"
    
    def getClassName(self, widgetClass, *args):
        return widgetClass.__module__ + "." + widgetClass.__name__

    def getDocName(self, className):
        return className.replace(".", "/")

    def getClassNameColumnSize(self):
        return 40 # seems to work, mostly

    def getSupportedLogWidgets(self):
        from describer import Describer
        return Describer.statelessWidgets + Describer.stateWidgets


class UseCaseReplayer(usecase.guishared.ThreadedUseCaseReplayer):
    def __init__(self, *args, **kw):
        usecase.guishared.ThreadedUseCaseReplayer.__init__(self, *args, **kw)
        self.describer = describer.Describer()
        self.filter = simulator.Filter(self.uiMap)
        self.filter.startListening(self.handleNewComponent)
        self.appearedWidgets = set()

    def handleNewComponent(self, widget):
        inWindow = isinstance(widget, swing.JComponent) and widget.getTopLevelAncestor() is not None and \
                   widget.getTopLevelAncestor() in self.uiMap.windows
        isWindow = isinstance(widget, (swing.JFrame, swing.JDialog))
        if self.uiMap and (self.isActive() or self.recorder.isActive()):
            if isWindow:
                if widget.getDefaultCloseOperation() == swing.WindowConstants.EXIT_ON_CLOSE:
                    widget.setDefaultCloseOperation(swing.WindowConstants.DISPOSE_ON_CLOSE)
                self.uiMap.monitorAndStoreWindow(widget)
                self.setAppeared(widget)
            elif inWindow and widget not in self.appearedWidgets:
                self.uiMap.monitor(usecase.guishared.WidgetAdapter.adapt(widget))
                self.setAppeared(widget)
        if self.loggerActive and (isWindow or inWindow):
            self.describer.setWidgetShown(widget)

    def setAppeared(self, widget):
        self.appearedWidgets.add(widget)
        for child in widget.getComponents():
            self.setAppeared(child)

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
