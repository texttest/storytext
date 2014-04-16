import storytext.guishared, time, os, threading, sys
import simulator, describer, util

from java.awt import Frame, AWTEvent, Toolkit
from java.awt.event import AWTEventListener, ComponentEvent, ContainerEvent
from java.lang import Thread, Runtime

from javax.swing import JButton, JComboBox, JComponent, JDialog, JFrame, JList, JMenuItem, JPopupMenu, JSpinner, \
    JTabbedPane, JTable, JTextField, JToggleButton
from javax.swing.plaf.basic import BasicInternalFrameTitlePane
from javax.swing.table import JTableHeader
from javax.swing.text import JTextComponent


class ScriptEngine(storytext.guishared.ScriptEngine):
    eventTypes = [
        (JFrame       , [ simulator.FrameCloseEvent, simulator.KeyPressForTestingEvent ]),
        (JButton      , [ simulator.ButtonClickEvent ]),
        (JToggleButton, [ simulator.ClickEvent ]),
        (JMenuItem    , [ simulator.MenuSelectEvent ]),
        (JTabbedPane  , [ simulator.TabSelectEvent, simulator.TabPopupActivateEvent]),
        (JDialog      , [ simulator.FrameCloseEvent ]),
        (JList        , [ simulator.ListSelectEvent ]),
        (JTable       , [ simulator.TableSelectEvent, simulator.TableHeaderEvent,
                                simulator.CellDoubleClickEvent, simulator.CellEditEvent,
                                simulator.CellPopupMenuActivateEvent ]),
        (JTextComponent  , [ simulator.TextEditEvent ]),
        (JTextField   , [ simulator.TextEditEvent, simulator.TextActivateEvent, simulator.PopupActivateEvent ]),
        (JSpinner     , [ simulator.SpinnerEvent ]),
        (BasicInternalFrameTitlePane, [ simulator.InternalFrameDoubleClickEvent ]),
        (JComponent   , [ simulator.PopupActivateEvent ]),
        (JPopupMenu   , []), # Don't monitor PopupActivateEvent here, seems to cause trouble
        (JComboBox    , [ simulator.ComboBoxEvent ])
        ]
    def run(self, options, args):
        if options.supported or options.supported_html:
            return storytext.guishared.ScriptEngine.run(self, options, args)

        class ShutdownHook(Thread):
            def run(tself):#@NoSelf
                self.cleanup(options.interface)
                
        if not options.disable_usecase_names:
            hook = ShutdownHook()
            Runtime.getRuntime().addShutdownHook(hook)

        return storytext.scriptengine.ScriptEngine.run(self, options, args)
    
    def createReplayer(self, universalLogging=False, **kw):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder, **kw)
    
    def runSystemUnderTest(self, args):
        self.run_python_or_java(args)
        self.replayer.runTestThread()

    def cleanup(self, interface):
        for frame in Frame.getFrames():
            if frame.isValid() and frame.isDisplayable():
                frame.setVisible(False) # don't leave the window up, looks weird
        self.replaceAutoRecordingForUsecase(interface, exitHook=True)
    
    def checkType(self, widget):
        # Headers are connected to the table to use any identification that is there
        recordWidgetTypes = [ cls for cls, signals in self.eventTypes ] + [ JTableHeader ]
        return any((isinstance(widget, cls) for cls in recordWidgetTypes))

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


class UseCaseReplayer(storytext.guishared.ThreadedUseCaseReplayer):
    def __init__(self, *args, **kw):
        storytext.guishared.ThreadedUseCaseReplayer.__init__(self, *args, **kw)
        self.describer = describer.Describer()
        self.listenForComponents()
        self.physicalEventManager = simulator.PhysicalEventManager()
        self.physicalEventManager.startListening()
        self.appearedWidgets = set()

    def listenForComponents(self):
        class NewComponentListener(AWTEventListener):
            def eventDispatched(listenerSelf, event):#@NoSelf
                # Primarily to make coverage work, it doesn't get enabled in threads made by Java
                if hasattr(threading, "_trace_hook") and threading._trace_hook:
                    sys.settrace(threading._trace_hook)
    
                if event.getID() == ComponentEvent.COMPONENT_SHOWN:
                    storytext.guishared.catchAll(self.handleNewComponent, event.getSource())
                elif event.getID() == ContainerEvent.COMPONENT_ADDED:
                    storytext.guishared.catchAll(self.handleNewComponent, event.getChild())

        eventMask = AWTEvent.COMPONENT_EVENT_MASK | AWTEvent.CONTAINER_EVENT_MASK
        util.runOnEventDispatchThread(Toolkit.getDefaultToolkit().addAWTEventListener, NewComponentListener(), eventMask)

    def handleNewComponent(self, widget):
        inWindow = isinstance(widget, JComponent) and widget.getTopLevelAncestor() is not None and \
                   widget.getTopLevelAncestor() in self.uiMap.windows
        isWindow = isinstance(widget, (JFrame, JDialog))
        appEventButton = hasattr(widget, "getText") and unicode(widget.getText()).startswith("ApplicationEvent")
        popupMenu = isinstance(widget, JPopupMenu) and not util.belongsMenubar(widget.getInvoker())
        if self.uiMap and (self.isActive() or self.recorder.isActive()):
            if isWindow:
                self.uiMap.monitorAndStoreWindow(widget)
                self.setAppeared(widget)
            elif (popupMenu or inWindow or appEventButton) and widget not in self.appearedWidgets:
                self.logger.debug("New widget of type " + widget.__class__.__name__ + " appeared: monitoring")
                self.uiMap.monitor(storytext.guishared.WidgetAdapter.adapt(widget))
                self.setAppeared(widget)
            elif isinstance(widget, JPopupMenu):
                self.setAppeared(widget.getParent())
        if self.loggerActive and (isWindow or inWindow or popupMenu):
            self.describer.setWidgetShown(widget)

    def setAppeared(self, widget):
        self.appearedWidgets.add(widget)
        if hasattr(widget, "getComponents"):
            for child in widget.getComponents():
                self.setAppeared(child)

    def describe(self):
        util.runOnEventDispatchThread(self.describer.describeWithUpdates)

    def runTestThread(self):
        util.runOnEventDispatchThread(self.waitForApplicationToAppear)
        if self.isActive():
            self.describeAndRun(self.describe)
        else: # pragma: no cover - replayer disabled, cannot create automated tests
            while self.frameShowing():
                time.sleep(0.1)

    def frameShowing(self): # pragma: no cover - replayer disabled, cannot create automated tests
        return any((frame.isShowing() for frame in Frame.getFrames()))

    def waitForApplicationToAppear(self):
        while not self.frameShowing():
            time.sleep(0.1)
