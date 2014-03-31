
""" Module for handling Nebula's NatTable, if present """

#Java-style imports. See NatTableSimulator comment for why
from org.eclipse.nebula.widgets.nattable import NatTable
from org.eclipse.nebula.widgets.nattable.config import CellConfigAttributes
from org.eclipse.nebula.widgets.nattable.style import DisplayMode
from org.eclipse.nebula.widgets.nattable.painter.cell import CheckBoxPainter

import util

class CanvasDescriber(util.CanvasDescriber):
    @classmethod
    def canDescribe(cls, widget):
        return isinstance(widget, NatTable)
            
    def addRowData(self, rowPos, rowToAddTo, prevRowSpans):
        prevColSpans = set()
        for col in range(self.canvas.getColumnCount()):
            dataStr = ""
            data = self.canvas.getDataValueByPosition(col, rowPos)
            if data is not None:
                cell = self.canvas.getCellByPosition(col, rowPos)
                if self.cellVisible(cell) and not self.cellIsLaterSpan(cell, rowPos, col, prevRowSpans, prevColSpans):
                    labels = cell.getConfigLabels().getLabels()
                    converter = self.findConverter(labels)
                    painter = self.findPainter(labels)
                    displayData = converter.canonicalToDisplayValue(data)
                    if isinstance(painter, CheckBoxPainter):
                        dataStr = "[x]" if data else "[ ]"
                    else:
                        dataStr = str(displayData)
                        displayMode = self.canvas.getDisplayModeByPosition(col, rowPos)
                        if displayMode == DisplayMode.SELECT:
                            dataStr += " (selected)"
                        elif displayMode == DisplayMode.EDIT:
                            dataStr += " (editing)"
            rowToAddTo.append(dataStr)
            
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
            
    def getCanvasDescription(self, *args):
        desc = "Table :\n"
        dataRows = []
        headerRows = []
        dataStartPos = self.findDataStartPosition()
        rowSpans = set()
        for rowPos in range(0, dataStartPos):
            headerRows.append([])
            self.addRowData(rowPos, headerRows[-1], rowSpans)
        for rowPos in range(dataStartPos, self.canvas.getRowCount()):
            dataRows.append([])
            self.addRowData(rowPos, dataRows[-1], rowSpans)
                
        return desc + self.formatTableMultilineHeader(headerRows, dataRows, max(1, self.canvas.getColumnCount()))

