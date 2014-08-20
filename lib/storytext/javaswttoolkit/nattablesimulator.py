
""" Module for handling Nebula's NatTable, if present """

from storytext.javaswttoolkit import simulator
from storytext.definitions import UseCaseScriptError
from simulator import WidgetMonitor
import util

from org.eclipse.nebula.widgets.nattable import NatTable
from org.eclipse.nebula.widgets.nattable.grid.layer import GridLayer
from org.eclipse.nebula.widgets.nattable.layer.cell import ILayerCell
from org.eclipse.nebula.widgets.nattable.viewport import ViewportLayer
from org.eclipse.nebula.widgets.nattable.config import IConfigRegistry, CellConfigAttributes
from org.eclipse.nebula.widgets.nattable.style import CellStyleUtil, DisplayMode
from org.eclipse.nebula.widgets.nattable.painter.cell import CheckBoxPainter

from org.eclipse.swtbot.swt.finder.widgets import AbstractSWTBot

from org.eclipse.swt import SWT
from org.eclipse.swt.widgets import Listener, Menu, Table

class NatTableIndexer(simulator.TableIndexer):
    def __init__(self, table):
        self.rowOffset = 0
        self.colOffset = 0
        self.setOffsets(table)
        simulator.TableIndexer.__init__(self, table)
        self.logger.debug("NatTable indexer with row offset " + str(self.rowOffset) + " and column offset " + str(self.colOffset))
        if self.colOffset == 0:
            # Probably no data yet if we have no offset at the start, best to keep an open mind...
            self.primaryKeyColumn = None
        
    def setOffsets(self, table):
        lastRow = table.getRowCount() - 1
        newRowOffset = lastRow - table.getRowIndexByPosition(lastRow)
        if newRowOffset >= 0: # Otherwise we've scrolled, and then we have no idea any more. Assume it doesn't change
            self.rowOffset = newRowOffset
        lastColumn = table.getColumnCount() - 1
        newColOffset = lastColumn - table.getColumnIndexByPosition(lastColumn)
        if newColOffset >= 0:
            self.colOffset = newColOffset
        
    def updateTableInfo(self):
        simulator.runOnUIThread(self.setOffsets, self.widget)
        self.logger.debug("Updated NatTable indexer with row offset " + str(self.rowOffset) + " and column offset " + str(self.colOffset))
        simulator.TableIndexer.updateTableInfo(self)
    
    def getRowCount(self):
        return self.widget.getRowCount() - self.rowOffset
    
    def getRowName(self, rowPos):
        self.checkNameCache()
        return self.rowNames[rowPos - self.rowOffset]
    
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
        if isinstance(data, (str, unicode)):
            return data
        elif data is not None:
            return str(data)
        else:
            return ""
    
    def getColumnTextByPosition(self, colPos):
        return self.widget.getDataValueByPosition(colPos, 0)
    
    def getColumnText(self, colIndex):
        return self.getColumnTextByPosition(colIndex + self.colOffset)
    
    def getViewCellIndices(self, description):
        row, col = simulator.TableIndexer.getViewCellIndices(self, description)
        return row + self.rowOffset, col + self.colOffset
    
    def getCellDescription(self, row, col, **kw):
        return simulator.TableIndexer.getCellDescription(self, row - self.rowOffset, col - self.colOffset, **kw)
    

class FakeSWTBotNatTable(AbstractSWTBot):
    def __init__(self, *args, **kw):
        AbstractSWTBot.__init__(self, *args, **kw)
        self.eventPoster = simulator.EventPoster(self.display)
        
    def clickOnCell(self, row, col, clickCount, button):
        bounds = self.widget.getBoundsByPosition(col, row)
        painter = self.getCellPainter(row, col)
        if isinstance(painter, CheckBoxPainter):
            x, y = self.getCheckBoxCoordinates(row, col, painter, bounds)
        else:
            x, y = self.getCenterCoordinates(bounds)

        displayLoc = self.display.map(self.widget, None, x, y)
        self.eventPoster.moveClickAndReturn(displayLoc.x, displayLoc.y, count=clickCount, button=button)

    def getCellPainter(self, row, col):
        cell = self.widget.getCellByPosition(col, row)
        labels = cell.getConfigLabels().getLabels()
        return self.widget.getConfigRegistry().getConfigAttribute(CellConfigAttributes.CELL_PAINTER, DisplayMode.NORMAL, labels)
        
    def getCheckBoxCoordinates(self, row, col, painter, bounds):
        cell = self.widget.getCellByPosition(col, row)
        configRegistry = self.widget.getConfigRegistry()
        image = util.callPrivateMethod(painter, "getImage", [ cell, configRegistry ], [ ILayerCell, IConfigRegistry ])
        imageBounds = image.getBounds()
        imageWidth = util.getInt(imageBounds.width)
        imageHeight = util.getInt(imageBounds.height)
        cellStyle = CellStyleUtil.getCellStyle(cell, configRegistry)
        x = bounds.x + CellStyleUtil.getHorizontalAlignmentPadding(cellStyle, bounds, imageWidth) + imageWidth / 2
        y = bounds.y + CellStyleUtil.getVerticalAlignmentPadding(cellStyle, bounds, imageHeight) + imageHeight / 2
        return x, y
           
    def getCenterCoordinates(self, bounds):
        x = util.getInt(bounds.x) + util.getInt(bounds.width) / 2
        y = util.getInt(bounds.y) + util.getInt(bounds.height) / 2
        return x, y
        
    def scrollToY(self, layer, offset):
        yCoord = layer.getOrigin().getY()
        simulator.runOnUIThread(layer.setOriginY, yCoord + offset)
        
    def checkRowInViewport(self, row):
        clientAreaHeight = simulator.runOnUIThread(self.widget.getClientArea).height
        bounds = simulator.runOnUIThread(self.widget.getBoundsByPosition, 0, row)
        y = util.getInt(bounds.y) + util.getInt(bounds.height) / 2
        if y > clientAreaHeight:
            raise UseCaseScriptError, "Could not select row, it is outside the viewport"
        
class InstantMenuDescriber(Listener):
    def __init__(self, widget):
        self.widget = widget
        
    def handleEvent(self, e):
        if isinstance(e.widget, Menu) and e.widget.getItemCount():
            self.describeMenu(e.widget)
            self.removeFilter()
    
    def describeMenu(self, menu):
        from describer import Describer
        desc = Describer()
        desc.logger.info("\nShowing Popup Menu:")
        desc.logger.info(desc.getMenuDescription(menu))
        
    def addFilter(self, *args):
        self.widget.widget.widget.getDisplay().addFilter(SWT.Show, self)
    
    def removeFilter(self, *args):
        self.widget.widget.widget.getDisplay().removeFilter(SWT.Show, self)
    
        
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
        simulator.runOnUIThread(self.widget.clickOnCell, row, col, self.clickCount(), button)
        
    def mouseButton(self):
        return 1

    def scrollDown(self):    
        viewportLayer = self.getViewportLayer()
        if viewportLayer:
            self.widget.scrollToY(viewportLayer, 200)
            self.getIndexer().updateTableInfo()
    
    def getViewportLayer(self):
        topLayer = self.widget.widget.widget.getLayer()
        if isinstance(topLayer, GridLayer):
            return self.findViewport(topLayer.getBodyLayer())
        else:
            return self.findViewport(topLayer)
    
    def findViewport(self, layer):
        if layer is None:
            return
        elif isinstance(layer, ViewportLayer):
            return layer
        else:
            return self.findViewport(layer.getUnderlyingLayerByPosition(0,0))
        
    def parseArguments(self, description):
        row, col = simulator.TableSelectEvent.parseArguments(self, description)
        self.widget.checkRowInViewport(row)
        return row, col
        
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
        return rowPos, colPos
    
        
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
        return self.getIndexer().getRowName(rowPos)
    
    def parseArguments(self, description):
        row, _ = NatTableEventHelper.parseArguments(self, description)
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
        return self.getIndexer().getColumnTextByPosition(colPos)
        
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

class FailureHandler():
    def handleReplayFailure(self, errorText, events):
        if "Could not find row identified by" in errorText or "outside the viewport" in errorText:
            for event in events:
                if hasattr(event, "scrollDown"):
                    event.scrollDown()
 
def getContextNameForNatCombo(widget, *args):
    if isinstance(widget, Table):
        for listener in widget.getListeners(SWT.Selection):
            if hasattr(listener, "getEventListener"):
                eventListener = listener.getEventListener()
                if "NatCombo" in eventListener.__class__.__name__:
                    return "NatCombo"

simulator.WidgetAdapter.contextFinders.append(getContextNameForNatCombo)
WidgetMonitor.swtbotMap[NatTable] = (FakeSWTBotNatTable, [])
util.cellParentData[NatTable] = "NatTableCell", "Table"

customEventTypes = [ (FakeSWTBotNatTable,   [ NatTableCellSelectEvent, NatTableCellDoubleClickEvent, NatTableRowSelectEvent, NatTableColumnSelectEvent,
                                              NatTableCellContextEvent, NatTableRowContextEvent, NatTableColumnContextEvent, NatTableCornerContextEvent ]) ]
