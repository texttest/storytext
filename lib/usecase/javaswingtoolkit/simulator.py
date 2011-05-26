import usecase.guishared, logging, util, sys, threading
from usecase import applicationEvent
from usecase.definitions import UseCaseScriptError
from java.awt import AWTEvent, Toolkit, Component
from java.awt.event import AWTEventListener, MouseAdapter, MouseEvent, KeyEvent, WindowAdapter, \
WindowEvent, ComponentEvent, ActionListener
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
                method(listenerSelf.pressedEvent, event, self)
                      
        util.runOnEventDispatchThread(self.widget.widget.addMouseListener, ClickListener())
        

    def shouldRecord(self, event, *args):
        return Filter.getEventFromUser(event)
    
    def setNameIfNeeded(self):
        mapId = self.widget.getUIMapIdentifier()
        if not mapId.startswith("Name="):
            name = "PyUseCase map ID: " + mapId + str(id(self))
            self.widget.setName(name)

    def delayLevel(self):
        # If there are events for other windows, implies we should delay as we're in a dialog
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
        if event.getModifiers() & MouseEvent.BUTTON1_MASK != 0 and event.getClickCount() == 1:
            return Filter.getEventFromUser(event)
        return False

class DoubleClickEvent(SignalEvent):
    @classmethod
    def getAssociatedSignal(cls, *args):
        return "DoubleClick"
    
    def shouldRecord(self, oldEvent, newEvent, *args):
        return Filter.getEventFromUser(oldEvent) and newEvent.getModifiers() & \
        MouseEvent.BUTTON1_MASK != 0 and newEvent.getClickCount() == 2
        
class ButtonClickEvent(SelectEvent):
    def connectRecord(self, method):
        SelectEvent.connectRecord(self, method)
        class FakeActionListener(ActionListener):
            def actionPerformed(lself, event):
                if isinstance(event.getSource(), swing.JButton) and event.getActionCommand().startswith("ApplicationEvent"):
                    applicationEvent(event.getActionCommand().replace("ApplicationEvent", "").lstrip())
                    
        util.runOnEventDispatchThread(self.widget.widget.addActionListener, FakeActionListener())
    
class StateChangeEvent(SelectEvent):
    def outputForScript(self, *args):
        return ' '.join([self.name, self.getStateText(*args) ])

    def isStateChange(self, *args):
        return True
    
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
        #Should be used when more than one TabbedPane exist: swinglib.runKeyword("selectTabPane", [ self.widget.getLabel() ])
        text = swinglib.runKeyword("getSelectedTabLabel", [])
        return ' '.join([self.name, text])
     
    def implies(self, *args):
        # State change because it can be implied by TabCloseEvents
        # But don't amalgamate them together, allow several tabs to be selected in sequence
        return False

class ListSelectEvent(StateChangeEvent):
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Select" 
    
    def _generate(self, argumentString):
        selected = argumentString.split(", ")
        params = [ self.widget.getName() ]
        try:
            swinglib.runKeyword("selectFromList", params + selected)
        except:
            raise UseCaseScriptError, "Could not find item labeled '" + argumentString + "' in list."
    
    def getStateText(self, *args):
        return self.getSelectedValues()
    
    def getSelectedValues(self):
        return ", ".join(self.widget.getSelectedValues())
    
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        currOutput = self.outputForScript(*args)
        return currOutput.startswith(stateChangeOutput)

class TableSelectEvent(ListSelectEvent):
    def __init__(self, *args, **kw):
        ListSelectEvent.__init__(self, *args, **kw)
        self.indexer = None

    def _generate(self, argumentString):
        # To be used when using multi-selection: selectedCells = argumentString.split(", ")
        params = [ self.widget.getName() ]
        row, column = self.getIndexer().getViewCellIndices(argumentString)
        try:
            # It seems to be a bug in SwingLibrary. Using Column name as argument doesn't work as expected. It throws exceptions
            # for some cell values. 
            swinglib.runKeyword("selectTableCell", params + [row, column])
        except:
            raise UseCaseScriptError, "Could not find value labeled '" + argumentString + "' in table."

    def getStateText(self, *args):
        return self.getSelectedCells()
        
    def getSelectedCells(self):
        text = []
        
        for row in self.widget.getSelectedRows():
            for col in self.widget.getSelectedColumns():
                text.append(self.getIndexer().getCellDescription(row, col))
        return ", ".join(text)
    
    def getSelectionWidget(self):
        return self.widget.widget.getSelectionModel()

    def getIndexer(self):
        if self.indexer is None:
            self.indexer = TableIndexer.getIndexer(self.widget.widget)
        return self.indexer

class CellDoubleClickEvent(DoubleClickEvent):
    def _generate(self, argumentString):
        row, column = TableIndexer.getIndexer(self.widget.widget).getViewCellIndices(argumentString)            
        try:
            swinglib.runKeyword("clickOnTableCell", [self.widget.getName(), row, column, 2, "BUTTON1_MASK" ])
        except:
            raise UseCaseScriptError, "Could not find value labeled '" + argumentString + "' in table."
    
    def outputForScript(self, event, *args):
        predefined = DoubleClickEvent.outputForScript(self,event, *args)
        row = self.widget.getSelectedRow()
        col = self.widget.getSelectedColumn()
        desc = TableIndexer.getIndexer(self.widget.widget).getCellDescription(row, col)
        return predefined + " " + desc

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
        eventMask = AWTEvent.MOUSE_EVENT_MASK | AWTEvent.KEY_EVENT_MASK | AWTEvent.WINDOW_EVENT_MASK | \
        AWTEvent.COMPONENT_EVENT_MASK | AWTEvent.ACTION_EVENT_MASK
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
            self.monitorNewComponent(event)
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

    def monitorNewComponent(self, event):
        if isinstance(event.getSource(), (swing.JFrame, swing.JDialog)):
            self.uiMap.scriptEngine.replayer.handleNewWindow(event.getSource())
        else:
            self.uiMap.scriptEngine.replayer.handleNewWidget(event.getSource())

class TableIndexer():
    allIndexers = {}
    
    def __init__(self, table):
        self.tableModel = table.getModel()
        self.table = table
        self.nameToIndex = {}
        self.indexToName = {}
        self.uniqueNames = {}
        self.logger = logging.getLogger("TableModelIndexer")
        self.populateMapping()
    
    @classmethod
    def getIndexer(cls, table):
        return cls.allIndexers.setdefault(table, cls(table))
    
    def getIndex(self, name):
        return self.nameToIndex.get(name)

    def isKey(self, name):
        return not self.uniqueNames.has_key(name) and self.nameToIndex.has_key(name)

    def checkKey(self, key, rowColumnIndex):
        if self.isKey(key):
            return rowColumnIndex in self.nameToIndex.get(key)
        return False

    def getKeyAtRow(self, row):
        currentName = None
        for name, indices in self.nameToIndex.items():
            if row in [index[:1][0]for index in indices]:
                currentName = name
                break
        if not self.uniqueNames.has_key(currentName):
            return currentName
        # Used when "primary key column" doesn't exist in the table
        for uniqueName in self.uniqueNames.get(currentName):
            for rowColIndices in self.findAllIndices(uniqueName):
                if row in rowColIndices:
                    return uniqueName
        return currentName
    
    def getViewCellIndices(self, description, cellContent=False):
        if len(description.split(" for ")) == 1:
            indices = self.getIndex(description)
            return self.getViewIndices(rowColumnIndices=indices)
        else:
            columnName, keyValue = description.split(" for ")
            if cellContent:
                key, value = keyValue.split("=")
            else:
                key = keyValue
            indices = self.getIndex(key)
            col = self.table.getColumn(columnName).getModelIndex()
            if indices:
                return self.getViewIndices(row=indices[0][0], column=col)
        return [None, None]
            
    def getViewIndices(self, row=-1, column=-1, rowColumnIndices=None):
        viewIndices = []
        if rowColumnIndices:
            viewIndices.append(self.table.convertRowIndexToView(rowColumnIndices[0][0]))
            viewIndices.append(self.table.convertColumnIndexToView(rowColumnIndices[0][1]))
        else:
            viewIndices.append(self.table.convertRowIndexToView(row))
            viewIndices.append(self.table.convertColumnIndexToView(column))
        return viewIndices
        
    def getCellDescription(self, row, col, cellContent=False):
        text = ""
        name = self.table.getValueAt(row, col)
        if self.checkKey(name, [self.table.convertRowIndexToModel(row), self.table.convertColumnIndexToModel(col)]):
            text = name
        else:
            key = self.getKeyAtRow(self.table.convertRowIndexToModel(row))
            if key:
                text = self.getTableSelectionString(key, row, col, cellContent)
        return text
    
    def getTableSelectionString(self, key, row, column, cellContent=False):
        text =  self.table.getColumnName(column) + " for " + key
        if cellContent:
            text += "=" + str(self.table.getValueAt(row, column))
        return text
  
    def populateMapping(self):
        rowCount = self.tableModel.getRowCount()
        colCount = self.tableModel.getColumnCount()
        for col in range(colCount):
            tmpUniqueNames = {}
            tmpNameToIndex = {}
            for row in range(rowCount):
                index = [row, col]
                name = self.tableModel.getValueAt(row, col)
                if self.store(index, name):
                    indices = tmpNameToIndex.setdefault(name, [])
                    indices.append( index)
                    allIndices = self.findAllIndices(name)
                    if len(allIndices) > 1:
                        newNames = self.getNewNames(allIndices, name)
                        if newNames is None:
                            newNames = ""
                        self.uniqueNames[name] = newNames
                        tmpUniqueNames[name] = newNames
                        for rowColIndex, newName in zip(allIndices, newNames):
                            self.store(rowColIndex, newName)
            if len (tmpUniqueNames) == 0:
                self.uniqueNames = tmpUniqueNames
                self.nameToIndex = tmpNameToIndex
                break
    
    def findAllIndices(self, name):
        storedIndices = self.nameToIndex.get(name, [])
        if len(storedIndices) > 0:
            validIndices = filter(lambda r: len(r) == 2, storedIndices)
            self.nameToIndex[name] = validIndices
            return validIndices
        else:
            return storedIndices
    
    def getNewNames(self, indices, oldName):
        if oldName is None:
            oldName = ""
        newNames = [ oldName ] * len(indices) 
        newName = oldName
        for i in range(len(indices)):
            newNames[i] = newName + " (" + str(indices[i][0]) +  "," + str(indices[i][1]) + ")"
        return newNames
                
    def store(self, index, name):
        indices = self.nameToIndex.setdefault(name, [])
        if not index in indices:
            self.logger.debug("Storing value named " + repr(name) + " in table cell with index " + repr(index))
            indices.append(index)
            return True
        else:
            return False

            
