
""" Module for handling Nebula's NatTable, if present """

from org.eclipse.nebula.widgets import nattable
import util

class CanvasDescriber(util.CanvasDescriber):
    @classmethod
    def canDescribe(cls, widget):
        return util.isinstance_any_classloader(widget, nattable.NatTable)
            
    def addRowData(self, rowPos, rowToAddTo, converters, prevRowSpans):
        prevColSpans = set()
        for col in range(self.canvas.getColumnCount()):
            dataStr = ""
            data = self.canvas.getDataValueByPosition(col, rowPos)
            if data:
                cell = self.canvas.getCellByPosition(col, rowPos)
                if not self.cellIsLaterSpan(cell, rowPos, col, prevRowSpans, prevColSpans):
                    labels = cell.getConfigLabels().getLabels()
                    converter = self.findConverter(converters, labels)
                    dataStr = converter.canonicalToDisplayValue(data)
                
                    displayMode = self.canvas.getDisplayModeByPosition(col, rowPos)
                    if displayMode == nattable.style.DisplayMode.SELECT:
                        dataStr += " (selected)"
                    elif displayMode == nattable.style.DisplayMode.EDIT:
                        dataStr += " (editing)"
            rowToAddTo.append(dataStr)
            
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
        
    def findConverter(self, converters, labels):
        for converterMap in converters:
            for label in labels:
                converter = converterMap.get(label)
                if converter:
                    return converter
        return converters[0].get(None)
    
    def getAllConverters(self):
        # The correct code is commented out here. Like much else, this fails due to classloader clashes
        # return self.canvas.getConfigRegistry().getConfigAttribute(nattable.config.CellConfigAttributes.DISPLAY_CONVERTER,  
        #                nattable.style.DisplayMode.NORMAL, [])
        # With this code, we can't tell the difference between DISPLAY_CONVERTER and FILTER_DISPLAY_CONVERTER. So we send both along
        # and hope for the best
        registryMap = util.getPrivateField(self.canvas.getConfigRegistry(), "configRegistry")
        #print registryMap
        converters = []
        for obj in registryMap.values():
            normalData = obj.get(nattable.style.DisplayMode.NORMAL)
            storedObject = normalData.get(None)
            if hasattr(storedObject, "canonicalToDisplayValue"):
                converters.append(normalData)
        return converters
        
    def getCanvasDescription(self, *args):
        desc = "Table :\n"
        dataRows = []
        headerRows = []
        converters = self.getAllConverters()
        dataStartPos = self.findDataStartPosition()
        rowSpans = set()
        for rowPos in range(0, dataStartPos):
            headerRows.append([])
            self.addRowData(rowPos, headerRows[-1], converters, rowSpans)
        for rowPos in range(dataStartPos, self.canvas.getRowCount()):
            dataRows.append([])
            self.addRowData(rowPos, dataRows[-1], converters, rowSpans)
                
        return desc + self.formatTableMultilineHeader(headerRows, dataRows, max(1, self.canvas.getColumnCount()))
