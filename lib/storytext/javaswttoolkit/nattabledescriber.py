
""" Module for handling Nebula's NatTable, if present """

import util

from org.eclipse.nebula.widgets.nattable import NatTable
from org.eclipse.nebula.widgets.nattable.config import CellConfigAttributes
from org.eclipse.nebula.widgets.nattable.style import DisplayMode
from org.eclipse.nebula.widgets.nattable.painter.cell import CheckBoxPainter, CellPainterWrapper
from org.eclipse.swt.graphics import Image
from org.eclipse.swt import SWT
from org.eclipse.swt.widgets import Event

class CanvasDescriber(util.CanvasDescriber):
    @classmethod
    def canDescribe(cls, widget):
        return isinstance(widget, NatTable)
            
    def addRowData(self, rowPos, rowToAddTo, prevRowSpans, normalDescriber, tooltip=None):
        prevColSpans = set()
        for col in range(self.canvas.getColumnCount()):
            elements = []
            data = self.canvas.getDataValueByPosition(col, rowPos)
            if data is not None:
                cell = self.canvas.getCellByPosition(col, rowPos)
                if self.cellVisible(cell) and not self.cellIsLaterSpan(cell, rowPos, col, prevRowSpans, prevColSpans):
                    labels = cell.getConfigLabels().getLabels()
                    converter = self.findConverter(labels)
                    painter = self.findPainter(labels)
                    displayData = converter.canonicalToDisplayValue(data)
                    if isinstance(painter, CheckBoxPainter):
                        elements.append("[x]" if data else "[ ]")
                    else:
                        elements.append(str(displayData))
                        displayMode = self.canvas.getDisplayModeByPosition(col, rowPos)
                        if displayMode == DisplayMode.SELECT:
                            elements.append("selected")
                        elif displayMode == DisplayMode.EDIT:
                            elements.append("editing")
                        if isinstance(painter, CellPainterWrapper):
                            image = self.getPainterImage(painter)
                            if image:
                                elements.append(normalDescriber.imageDescriber.getImageDescription(image))
                    if tooltip and self.describeClass("Tooltip"):
                        text = self.getTooltipText(tooltip, cell)
                        if text:
                            elements.append(self.combineMultiline([ "Tooltip '", text + "'" ]))
                        
            rowToAddTo.append(self.combineElements(elements))
            
    def iterateAttributes(self, painter):
        if hasattr(painter, "__dict__"):
            for obj in painter.__dict__.values():
                yield obj
        else:
            for field in painter.getClass().getDeclaredFields():
                field.setAccessible(True)
                yield field.get(painter)
            
    def getPainterImage(self, painter):
        for obj in self.iterateAttributes(painter):
            if isinstance(obj, Image):
                return obj
            
    def getTooltipText(self, tooltip, cell):
        event = self.makeToolTipEvent(cell)
        if util.callPrivateMethod(tooltip, "shouldCreateToolTip", [ event ]):
            return util.callPrivateMethod(tooltip, "getText", [ event ])
        
    def makeToolTipEvent(self, cell):
        event = Event()
        event.type = SWT.MouseHover
        event.widget = self.canvas
        bounds = cell.getBounds()
        event.x = util.getInt(bounds.x) + util.getInt(bounds.width) / 2
        event.y = util.getInt(bounds.y) + util.getInt(bounds.height) / 2
        return event
            
    def cellVisible(self, cell):
        bounds = cell.getBounds()
        return util.getInt(bounds.width) > 0 and util.getInt(bounds.height) > 0
            
    def cellIsLaterSpan(self, cell, row, col, prevRowSpans, prevColSpans):
        rowSpan = cell.getRowSpan()
        colSpan = cell.getColumnSpan()
        if rowSpan > 1:
            prevRowSpans.add((row, col))
        if colSpan > 1:
            prevColSpans.add(col)
            return col - 1 in prevColSpans
        elif rowSpan > 1:
            return (row - 1, col) in prevRowSpans
        else:
            return False
            
    def findDataStartPosition(self):
        for row in range(self.canvas.getRowCount()):
            labels = self.canvas.getConfigLabelsByPosition(1, row).getLabels()
            if "CORNER" not in labels and "COLUMN_HEADER" not in labels:
                return row
        return self.canvas.getRowCount()
        
    def findConverter(self, labels):
        return self.canvas.getConfigRegistry().getConfigAttribute(CellConfigAttributes.DISPLAY_CONVERTER, DisplayMode.NORMAL, labels)
    
    def findPainter(self, labels):
        return self.canvas.getConfigRegistry().getConfigAttribute(CellConfigAttributes.CELL_PAINTER, DisplayMode.NORMAL, labels)
            
    def getCanvasDescription(self, normalDescriber):
        desc = "Table :\n"
        dataRows = []
        headerRows = []
        tooltip = util.getJfaceTooltip(self.canvas)
        dataStartPos = self.findDataStartPosition()
        rowSpans = set()
        for rowPos in range(0, dataStartPos):
            headerRows.append([])
            self.addRowData(rowPos, headerRows[-1], rowSpans, normalDescriber)
        for rowPos in range(dataStartPos, self.canvas.getRowCount()):
            dataRows.append([])
            self.addRowData(rowPos, dataRows[-1], rowSpans, normalDescriber, tooltip)
                
        return desc + self.formatTableMultilineHeader(headerRows, dataRows, max(1, self.canvas.getColumnCount()))

