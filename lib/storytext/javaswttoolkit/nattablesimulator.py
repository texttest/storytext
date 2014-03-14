
""" Module for handling Nebula's NatTable, if present """

from storytext.javaswttoolkit import simulator
from storytext.definitions import UseCaseScriptError
from org.eclipse.nebula.widgets import nattable
from org.eclipse.nebula.widgets.nattable.grid.layer import GridLayer
from org.eclipse.nebula.widgets.nattable.viewport import ViewportLayer
import org.eclipse.swtbot.swt.finder as swtbot
from simulator import WidgetMonitor
import util
from org.eclipse import swt

class NatTableIndexer(simulator.TableIndexer):
    def __init__(self, table):
        self.setOffsets(table)
        simulator.TableIndexer.__init__(self, table)
        self.logger.debug("NatTable indexer with row offset " + str(self.rowOffset) + " and column offset " + str(self.colOffset))

    def setOffsets(self, table):
        lastRow = table.getRowCount() - 1
        self.rowOffset = lastRow - simulator.runOnUIThread(table.getRowIndexByPosition,lastRow)
        lastColumn = table.getColumnCount() - 1
        self.colOffset = lastColumn - table.getColumnIndexByPosition(lastColumn)
        
    def rebuildCache(self):
        self.setOffsets(self.widget)
        simulator.TableIndexer.rebuildCache(self)


    def checkNameCache(self):
        self.rebuildCache()
    
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
        
    def clickOnCenter(self, row, col, clickCount, button):
        bounds = simulator.runOnUIThread(self.widget.getBoundsByPosition, col, row)
        x = util.getInt(bounds.x) + util.getInt(bounds.width) / 2
        y = util.getInt(bounds.y) + util.getInt(bounds.height) / 2
        displayLoc = simulator.runOnUIThread(self.display.map, self.widget, None, x, y)
        self.eventPoster.moveClickAndReturn(displayLoc.x, displayLoc.y, count=clickCount, button=button)

    def scrollToY(self, layer, offset):
        yCoord = layer.getOrigin().getY()
        simulator.runOnUIThread(layer.setOriginY, yCoord + offset)

class InstantMenuDescriber(swt.widgets.Listener):
    def __init__(self, widget):
        self.widget = widget
        
    def handleEvent(self, e):
        if isinstance(e.widget, swt.widgets.Menu) and e.widget.getItemCount():
            self.describeMenu(e.widget)
            self.removeFilter()
    
    def describeMenu(self, menu):
        from describer import Describer
        desc = Describer()
        desc.logger.info("\nShowing Popup Menu:")
        desc.logger.info(desc.getMenuDescription(menu))
        
    def addFilter(self, *args):
        self.widget.widget.widget.getDisplay().addFilter(swt.SWT.Show, self)
    
    def removeFilter(self, *args):
        self.widget.widget.widget.getDisplay().removeFilter(swt.SWT.Show, self)
    
        
class NatTableEventHelper:        
    def shouldRecord(self, event, *args):
        return event.count == self.clickCount() and event.button == self.mouseButton() and self.isCorrectRegion(event)
    
    def isCorrectRegion(self, event):
        labels = self.widget.widget.widget.getRegionLabelsByXY(event.x, event.y).getLabels()
        return self.getRegionLabel() in labels

    def getIndexer(self):
        return NatTableIndexer.getIndexer(self.widget.widget.widget)
    
    def _generate(self, cell):
        row, col = cell
        button = self.mouseButton()
        if button == 3:
            desc = InstantMenuDescriber(self.widget)
            simulator.runOnUIThread(desc.addFilter)
        self.widget.clickOnCenter(row, col, self.clickCount(), button)
        
    def mouseButton(self):
        return 1
    
    def getViewportLayer(self):
        topLayer = self.widget.widget.widget.getLayer()
        if isinstance(topLayer, nattable.grid.layer.GridLayer):
            return self.findViewport(topLayer.getBodyLayer())
        else:
            return self.findViewport(topLayer)
    
    def findViewport(self, layer):
        if layer is None:
            return
        elif isinstance(layer, nattable.viewport.ViewportLayer):
            return layer
        else:
            return self.findViewport(layer.getUnderlyingLayerByPosition(0,0))
        
class ContextEventHelper:
    def mouseButton(self):
        return 3
        
    
class NatTableCellEventHelper(NatTableEventHelper):
    def getRegionLabel(self):
        return "BODY"
            
    def findCell(self, event):
        table = self.widget.widget.widget
        rowPos = table.getRowPositionByY(event.y)
        colPos = table.getColumnPositionByX(event.x)
        return table.getRowIndexByPosition(rowPos), table.getColumnIndexByPosition(colPos)
    
        
class NatTableCellSelectEvent(NatTableCellEventHelper, simulator.TableSelectEvent):
    pass
    
class NatTableCellDoubleClickEvent(NatTableCellEventHelper, simulator.TableDoubleClickEvent):
    pass
    
class NatTableRowSelectEvent(NatTableEventHelper, simulator.TableSelectEvent):
    @classmethod
    def getAssociatedSignatures(cls, widget):
        return [ "RowSelection" ]
    
    def getRegionLabel(self):
        return "ROW_HEADER"
    
    def getStateText(self, event, *args):
        table = self.widget.widget.widget
        rowPos = table.getRowPositionByY(event.y)
        rowNum = table.getRowIndexByPosition(rowPos)
        return self.getIndexer().getRowName(rowNum)
    
    def parseArguments(self, description):
        row, _ = simulator.TableSelectEvent.parseArguments(self, description)
        return row, 0 
        

class NatTableColumnSelectEvent(NatTableEventHelper, simulator.TableSelectEvent):
    @classmethod
    def getAssociatedSignatures(cls, widget):
        return [ "ColumnSelection" ]
    
    def getRegionLabel(self):
        return "COLUMN_HEADER"
                
    def getStateText(self, event, *args):
        table = self.widget.widget.widget
        colPos = table.getColumnPositionByX(event.x)
        colNum = table.getColumnIndexByPosition(colPos)
        return self.getIndexer().getColumnTextToUse(colNum)
        
    def parseArguments(self, argumentString):
        return 0, self.getIndexer().findColumnPosition(argumentString)
    
class NatTableCellContextEvent(ContextEventHelper,NatTableCellSelectEvent):
    @classmethod
    def getAssociatedSignatures(cls, widget):
        return [ "CellContextMenu" ]

class NatTableRowContextEvent(ContextEventHelper, NatTableRowSelectEvent):
    @classmethod
    def getAssociatedSignatures(cls, widget):
        return [ "RowContextMenu" ]
    
class NatTableColumnContextEvent(ContextEventHelper, NatTableColumnSelectEvent):
    @classmethod
    def getAssociatedSignatures(cls, widget):
        return [ "ColumnContextMenu" ]
    
class NatTableCornerContextEvent(ContextEventHelper, NatTableEventHelper, simulator.TableSelectEvent):
    @classmethod
    def getAssociatedSignatures(cls, widget):
        return [ "CornerContextMenu" ]

    def getRegionLabel(self):
        return "CORNER"
    
    def outputForScript(self, *args):
        return self.name
    
    def parseArguments(self, argumentString):
        return 0, 0

class WidgetMonitor(simulator.WidgetMonitor):
    def handleReplayFailure(self, errorText, events):
        if "Could not find row identified by" in errorText:
            for event in events:
                if hasattr(event, "getViewportLayer"):
                    viewportLayer = event.getViewportLayer()
                    if viewportLayer:
                        event.widget.widget.scrollToY(viewportLayer, 200)
        simulator.WidgetMonitor.handleReplayFailure(self, errorText, events)

WidgetMonitor.swtbotMap[nattable.NatTable] = (FakeSWTBotNatTable, [])
util.cellParentData[nattable.NatTable] = "NatTableCell", "Table"

customEventTypes = [ (FakeSWTBotNatTable,   [ NatTableCellSelectEvent, NatTableCellDoubleClickEvent, NatTableRowSelectEvent, NatTableColumnSelectEvent,
                                              NatTableCellContextEvent, NatTableRowContextEvent, NatTableColumnContextEvent, NatTableCornerContextEvent ]) ]
