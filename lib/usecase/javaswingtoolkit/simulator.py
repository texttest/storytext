import usecase.guishared, logging, util, sys, threading
from java.awt import AWTEvent, Toolkit, Component
from java.awt.event import AWTEventListener, MouseAdapter, MouseEvent, KeyEvent, WindowAdapter, \
WindowEvent, ComponentEvent
from javax import swing
import SwingLibrary

swinglib = SwingLibrary()

def selectWindow(widget):
    w = checkWidget(widget)
    window = swing.SwingUtilities.getWindowAncestor(w)
    if isinstance(window, swing.JFrame):
        swinglib.runKeyword("selectWindow", [ window.getTitle() ])
    elif isinstance(window, swing.JDialog):
        swinglib.runKeyword("selectDialog", [ window.getTitle() ])

def checkWidget(widget):
    if isinstance(widget, swing.JMenuItem):
        return widget.getParent().getInvoker()
    return widget
        
class WidgetAdapter(usecase.guishared.WidgetAdapter):
    # All the standard message box texts
    dialogTexts = [ "OK", "Cancel", "Yes", "No", "Abort", "Retry", "Ignore" ]
    
    def getChildWidgets(self):
        if isinstance(self.widget, swing.JMenu):
            return self.widget.getPopupMenu().getSubElements()
        else:
            return self.widget.getComponents()
        
    def getName(self):
        return self.widget.getName() or ""
    
    def getWidgetTitle(self):
        if hasattr(self.widget, "getTitle"):
            return self.widget.getTitle()
        else:
            return ""
            
    def isAutoGenerated(self, name):
        return name == "frame0" or name.startswith("OptionPane") or len(name) == 0
    
    def getLabel(self):
        text = ""
        if hasattr(self.widget, "getLabel"):
            text =  self.widget.getLabel()
        else:
            return ""
        if text in self.dialogTexts:
            dialogTitle = self.getDialogTitle()
            if dialogTitle:
                return text + ", Dialog=" + dialogTitle
        return text
    
    def getDialogTitle(self):
        return swing.SwingUtilities.getWindowAncestor(self.widget).getTitle()

usecase.guishared.WidgetAdapter.adapterClass = WidgetAdapter

class SignalEvent(usecase.guishared.GuiEvent):
                
    def generate(self, *args):
        self.setNameIfNeeded()
        selectWindow(self.widget.widget)
        self._generate(*args)
            
    def connectRecord(self, method):
        class ClickListener(MouseAdapter):
            def mousePressed(listenerSelf, event):
                listenerSelf.pressedEvent = event
            
            def mouseReleased(listenerSelf, event):
                method(listenerSelf.pressedEvent, self)
              
        util.runOnEventDispatchThread(self.widget.widget.addMouseListener, ClickListener())
        
    def shouldRecord(self, event, *args):
        return Filter.getEventFromUser(event)
    
    def setNameIfNeeded(self):
        mapId = self.widget.getUIMapIdentifier()
        if not mapId.startswith("Name="):
            name = "PyUseCase map ID: " + mapId
            self.widget.setName(name)

    def delayLevel(self):
        # If there are events for other shells, implies we should delay as we're in a dialog
        return len(Filter.eventsFromUser)
    
class FrameCloseEvent(SignalEvent):
    def _generate(self, *args):
        # What happens here if we don't have a title?
        swinglib.runKeyword("closeWindow", [ self.widget.getTitle() ])
  
    def connectRecord(self, method):
        class WindowCloseListener(WindowAdapter):
            def windowClosing(listenerSelf, event):
                method(event, self)
            
            def windowClosed(listenerSelf, event):
                Filter.stopListening()
                        
        util.runOnEventDispatchThread(self.widget.widget.addWindowListener, WindowCloseListener())
        
    @classmethod
    def getAssociatedSignal(cls, *args):
        return "Close"

class SelectEvent(SignalEvent):
    def _generate(self, *args):
        swinglib.runKeyword("clickOnComponent", [ self.widget.getName()])
        
    @classmethod
    def getAssociatedSignal(cls, *args):
        return "Click"

    def shouldRecord(self, event, *args):
        return Filter.getEventFromUser(event) and event.getModifiers() & MouseEvent.BUTTON1_MASK != 0

    
class MenuSelectEvent(SelectEvent):                            
    def connectRecord(self, method):
        class ClickListener(MouseAdapter):
            def mousePressed(listenerSelf, event):
                if not isinstance(event.getSource(), swing.JMenu):
                    listenerSelf.pressedEvent = event
                    
            def mouseReleased(listenerSelf, event):
                if not isinstance(event.getSource(), swing.JMenu):
                    method(listenerSelf.pressedEvent, self)
                    
        util.runOnEventDispatchThread(self.widget.widget.addMouseListener, ClickListener())      
        
    def _generate(self, *args):
        path = util.getMenuPathString(self.widget)
        swinglib.runKeyword("selectFromMenuAndWait", [ path ])

class TabSelectEvent(SelectEvent):
    def isStateChange(self):
        return True
                    
    def _generate(self, argumentString):
        swinglib.runKeyword("selectTab", [ argumentString ])
    
    def outputForScript(self, event, *args):
        swinglib.runKeyword("selectWindow", [ swing.SwingUtilities.getWindowAncestor(self.widget.widget).getTitle()])
        #Should be used when more than oene TabbedPane is used: swinglib.runKeyword("selectTabPane", [ self.widget.getLabel() ])
        text = swinglib.runKeyword("getSelectedTabLabel", [])
        return ' '.join([self.name, text])
     
    def implies(self, *args):
        # State change because it can be implied by TabCloseEvents
        # But don't amalgamate them together, allow several tabs to be selected in sequence
        return False

              
class Filter:
    eventsFromUser = []
    logger = None
    eventListener = None
    def __init__(self, uiMap):
        Filter.logger = logging.getLogger("usecase record")
        self.uiMap = uiMap
        
    @classmethod
    def getEventFromUser(cls, event):
        if event in cls.eventsFromUser:
            cls.eventsFromUser.remove(event)
            return True
        else:
            if len(cls.eventsFromUser) == 0:
                cls.logger.debug("Rejecting event, it has not yet been seen in the display filter")
            else:
                cls.logger.debug("Received event " + repr(event))
                cls.logger.debug("Rejecting event, not yet processed " + repr([ repr(e) for e in cls.eventsFromUser ]))
            return False
        
    def getWindow(self, widget):
        return swing.SwingUtilities.getWindowAncestor(widget)
    
    def hasEventOnWindow(self, widget):
        currWindow = self.getWindow(widget)
        if not currWindow:
            return False

        for event in self.eventsFromUser:
            if self.getWindow(event.getSource()) is currWindow:
                return True
        return False
    
    def startListening(self):
        eventMask = AWTEvent.MOUSE_EVENT_MASK | AWTEvent.KEY_EVENT_MASK | AWTEvent.WINDOW_EVENT_MASK | AWTEvent.COMPONENT_EVENT_MASK
        # Should be commented out if we need to listen to these events:
        #| AWTEvent.WINDOW_EVENT_MASK | AWTEvent.COMPONENT_EVENT_MASK | AWTEvent.ACTION_EVENT_MASK
        #| AWTEvent.ITEM_EVENT_MASK | AWTEvent.INPUT_METHOD_EVENT_MASk
        
        class AllEventListener(AWTEventListener):
            def eventDispatched(listenerSelf, event):
                # Primarily to make coverage work, it doesn't get enabled in threads made by Java
                if hasattr(threading, "_trace_hook") and threading._trace_hook:
                    sys.settrace(threading._trace_hook)
                self.handleEvent(event)
        
        self.eventListener = AllEventListener()
        util.runOnEventDispatchThread(Toolkit.getDefaultToolkit().addAWTEventListener, self.eventListener, eventMask)
    
    @classmethod
    def stopListening(cls):
        util.runOnEventDispatchThread(Toolkit.getDefaultToolkit().removeAWTEventListener, cls.eventListener)
    
    def handleEvent(self, event):
        if event.getID() == ComponentEvent.COMPONENT_SHOWN:
            self.monitorNewWindow(event)
        elif isinstance(event.getSource(), Component):
            if self.addToFilter(event) and not self.hasEventOnWindow(event.getSource()):
                self.logger.debug("Filter for event " + event.toString())    
                self.eventsFromUser.append(event)
    
    def addToFilter(self, event):
        for cls in [ MouseEvent, KeyEvent, WindowEvent, ComponentEvent ]:
            if isinstance(event, cls):
                return getattr(self, "handle" + cls.__name__)(event)
        return True
            
    def handleMouseEvent(self, event):
        return event.getID() == MouseEvent.MOUSE_PRESSED and not isinstance(event.getSource(), swing.JMenu)
            
    def handleKeyEvent(self, event):
        # TODO: to be implemented
        return False
        
    def handleWindowEvent(self, event):
        return event.getID() == WindowEvent.WINDOW_CLOSING or self.handleComponentEvent(event)
    
    def handleComponentEvent(self, event):            
        return False #TODO: return event.getID() == ComponentEvent.COMPONENT_RESIZED

    def monitorNewWindow(self, event):
        if isinstance(event.getSource(), (swing.JFrame, swing.JDialog)):
            self.uiMap.scriptEngine.replayer.handleNewWindow(event.getSource())

