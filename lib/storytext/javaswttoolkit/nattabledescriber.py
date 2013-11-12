
""" Module for handling Nebula's NatTable, if present """

from storytext import guishared
from org.eclipse.nebula.widgets import nattable
import util

class CanvasDescriber(util.CanvasDescriber):
    @classmethod
    def canDescribe(cls, widget):
        return isinstance(widget, nattable.NatTable)
        
    def getCanvasDescription(self, *args):
        desc = "NatTable :\n"
        rows = []
        for row in range(self.canvas.getRowCount()):
            rows.append([])
            for col in range(self.canvas.getColumnCount()):
                data = self.canvas.getDataValueByPosition(col, row)
                dataStr = str(data) if data else ""
                displayMode = self.canvas.getDisplayModeByPosition(col, row)
                if displayMode == nattable.style.DisplayMode.SELECT:
                    dataStr += " (selected)"
                elif displayMode == nattable.style.DisplayMode.EDIT:
                    dataStr += " (editing)"
                rows[-1].append(dataStr)
        return desc + self.formatTable(rows[0], rows[1:], max(1, self.canvas.getColumnCount()))
