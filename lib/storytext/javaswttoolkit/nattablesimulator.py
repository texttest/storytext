
""" Module for handling Nebula's NatTable, if present """

from storytext.javaswttoolkit import simulator
from storytext.definitions import UseCaseScriptError
from org.eclipse.nebula.widgets import nattable
import org.eclipse.swtbot.swt.finder as swtbot
from simulator import WidgetMonitor
import storytext.guishared, util
from org.eclipse import swt
import inspect
                
        
class NatTableIndexer(simulator.TableIndexer):
    def __init__(self, table):
        self.setOffsets(table)
        simulator.TableIndexer.__init__(self, table)
        self.logger.debug("NatTable indexer with row offset " + str(self.rowOffset) + " and column offset " + str(self.colOffset))

    def setOffsets(self, table):
        lastRow = table.getRowCount() - 1
        self.rowOffset = lastRow - table.getRowIndexByPosition(lastRow)
        lastColumn = table.getColumnCount() - 1
        self.colOffset = lastColumn - table.getColumnIndexByPosition(lastColumn)
        
    def rebuildCache(self):
        self.setOffsets(self.widget)
        simulator.TableIndexer.rebuildCache(self)
    
    def getRowCount(self):
        return self.widget.getRowCount() - self.rowOffset
    
    def getRowName(self, rowIndex):
        self.checkNameCache()
        return self.rowNames[rowIndex]
    
    def getColumnCount(self):
        return self.widget.getColumnCount() - self.colOffset
    
    def findColumnPosition(self, columnName):
        colIndex = self.findColumnIndex(columnName)
        if colIndex is None:
            raise UseCaseScriptError, "Could not find column labelled '" + columnName + "' in table."
        return colIndex + self.colOffset

    def getCellValue(self, rowIndex, colIndex):
        rowPos = rowIndex + self.rowOffset
        colPos = colIndex + self.colOffset
        data = self.widget.getDataValueByPosition(colPos, rowPos)
        return str(data) if data else ""
    
    def getColumnText(self, colIndex):
        colPos = colIndex + self.colOffset
        return self.widget.getDataValueByPosition(colPos, 0)
    
    def getViewCellIndices(self, description):
        row, col = simulator.TableIndexer.getViewCellIndices(self, description)
        return row + self.rowOffset, col + self.colOffset
    

class FakeSWTBotNatTable(swtbot.widgets.AbstractSWTBot):
    def __init__(self, *args, **kw):
        swtbot.widgets.AbstractSWTBot.__init__(self, *args, **kw)
        self.eventPoster = simulator.EventPoster(self.display)
        
    def clickOnCenter(self, row, col, clickCount):
        bounds = self.widget.getBoundsByPosition(col, row)
        x = util.getInt(bounds.x) + util.getInt(bounds.width) / 2
        y = util.getInt(bounds.y) + util.getInt(bounds.height) / 2
        displayLoc = simulator.runOnUIThread(self.display.map, self.widget, None, x, y)
        self.eventPoster.moveClickAndReturn(displayLoc.x, displayLoc.y, count=clickCount)
        
class NatTableEventHelper:
    def connectRecord(self, method):
        table = self.widget.widget.widget
        layerListenerInterface = self.findLayerListenerInterface(table)
        eventClass = self.getEventClass()
        class BasicLayerListener(layerListenerInterface):        
            def handleLayerEvent(lself, e): #@NoSelf
                if util.isinstance_any_classloader(e, eventClass):
                    storytext.guishared.catchAll(method, e, self)

        simulator.runOnUIThread(table.addLayerListener, BasicLayerListener())

    def findLayerListenerInterface(self, table):
        for baseClass in inspect.getmro(table.__class__):
            if baseClass.__name__ == "ILayerListener":
                return baseClass

    def getIndexer(self):
        return NatTableIndexer.getIndexer(self.widget.widget.widget)
    
    def isTriggeringEvent(self, e):
        return e.type == swt.SWT.MouseDown and e.widget is self.widget.widget.widget
    
    def _generate(self, cell):
        row, col = cell
        self.widget.clickOnCenter(row, col, self.clickCount())
    
class NatTableCellEventHelper(NatTableEventHelper):
    def shouldRecord(self, event, *args):
        swtEvent = simulator.DisplayFilter.instance.getEventOfType(swt.SWT.MouseDown, self.widget.widget.widget)
        if not swtEvent or swtEvent.count != self.clickCount():
            return False
            
        return event.getRowPosition() >= 0 and event.getColumnPosition() >= 0
        
    def findCell(self, event):
        table = self.widget.widget.widget
        return table.getRowIndexByPosition(event.getRowPosition()), table.getColumnIndexByPosition(event.getColumnPosition())
    
    def getEventClass(self):
        return nattable.selection.event.CellSelectionEvent

        
class NatTableCellSelectEvent(NatTableCellEventHelper, simulator.TableSelectEvent):
    pass
    
class NatTableCellDoubleClickEvent(NatTableCellEventHelper, simulator.TableDoubleClickEvent):
    pass
    
class NatTableRowSelectEvent(NatTableEventHelper, simulator.TableSelectEvent):
    def getEventClass(self):
        return nattable.selection.event.RowSelectionEvent

    def shouldRecord(self, event, *args):
        return event.getRowPositionToMoveIntoViewport() > 0
            
    @classmethod
    def getAssociatedSignatures(cls, widget):
        return [ "RowSelection" ]
    
    def getStateText(self, event, *args):
        rowNum = self.widget.widget.widget.getRowIndexByPosition(event.getRowPositionToMoveIntoViewport())
        return self.getIndexer().getRowName(rowNum)
    
    def parseArguments(self, description):
        row, _ = simulator.TableSelectEvent.parseArguments(self, description)
        return row, 0 
        

class NatTableColumnSelectEvent(NatTableEventHelper, simulator.TableSelectEvent):
    def getEventClass(self):
        return nattable.selection.event.ColumnSelectionEvent

    def shouldRecord(self, event, *args):
        return len(event.getColumnPositionRanges()) > 0
            
    @classmethod
    def getAssociatedSignatures(cls, widget):
        return [ "ColumnSelection" ]
    
    def getStateText(self, event, *args):
        # It's a list, but how to trigger this multiple selection. Can't work it out.
        # Take the first one for now
        colNum = self.widget.widget.widget.getColumnIndexByPosition(event.getColumnPositionRanges()[0].start)
        return self.getIndexer().getColumnTextToUse(colNum)
        
    def parseArguments(self, argumentString):
        return 0, self.getIndexer().findColumnPosition(argumentString)
    

util.classLoaderFail.add(nattable.NatTable)
WidgetMonitor.swtbotMap[nattable.NatTable] = (FakeSWTBotNatTable, [])
util.cellParentData.append((nattable.NatTable, "NatTableCell"))

customEventTypes = [ (FakeSWTBotNatTable,   [ NatTableCellSelectEvent, NatTableCellDoubleClickEvent, NatTableRowSelectEvent, NatTableColumnSelectEvent ]) ]
