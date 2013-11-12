
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
        return "NatTable with " + str(self.table.getRowCount()) + " rows and " + str(self.table.getColumnCount()) + " columns."
