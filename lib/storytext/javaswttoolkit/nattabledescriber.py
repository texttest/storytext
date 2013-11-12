
""" Module for handling Nebula's NatTable, if present """

from storytext import guishared
from org.eclipse.nebula.widgets import nattable

class CanvasDescriber(guishared.Describer):
    @classmethod
    def canDescribe(cls, widget):
        return isinstance(widget, nattable.NatTable)
    
    def __init__(self, table):
        self.table = table
        guishared.Describer.__init__(self)
    
    def getCanvasDescription(self, *args):
        desc = "NatTable :\n"
        rows = []
        for row in range(self.table.getRowCount()):
            rows.append([])
            for col in range(self.table.getColumnCount()):
                data = self.table.getDataValueByPosition(col, row)
                dataStr = str(data) if data else ""
                rows[-1].append(dataStr)
        return desc + self.formatTable(rows[0], rows[1:], max(1, self.table.getColumnCount()))
