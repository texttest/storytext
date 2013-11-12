
""" Module for handling Nebula's NatTable, if present """

from storytext.javaswttoolkit import simulator
from org.eclipse.nebula.widgets import nattable
import org.eclipse.swtbot.swt.finder as swtbot
from simulator import WidgetMonitor
import storytext.guishared, util
from org.eclipse import swt
    
class BasicLayerListener(nattable.layer.ILayerListener):
    def __init__(self, method, event, eventClass):
        self.method = method
        self.event = event
        self.eventClass = eventClass
        
    def handleLayerEvent(self, e):
        if isinstance(e, self.eventClass):
            storytext.guishared.catchAll(self.method, e, self.event)
            
        
class NatTableIndexer(simulator.TableIndexer):
    def getRowCount(self):
        return self.widget.getRowCount()
    
    def getColumnCount(self):
        return self.widget.getColumnCount()

    def getCellValue(self, row, col):
        data = self.widget.getDataValueByPosition(col, row)
        return str(data) if data else ""
    
    def getColumnText(self, col):
        return self.getCellValue(0, col)
    
    def canBePrimaryKeyColumn(self, column, uniqueEntries):
        # Exclude automatically added row header counting, which seems very common
        return simulator.TableIndexer.canBePrimaryKeyColumn(self, column, uniqueEntries) and not self.isDefaultRowHeader(column)
    
    def isDefaultRowHeader(self, column):
        return column[1:] == map(str, range(1, len(column)))


class FakeSWTBotNatTable(swtbot.widgets.AbstractSWTBot):
    def __init__(self, *args, **kw):
        swtbot.widgets.AbstractSWTBot.__init__(self, *args, **kw)
        self.eventPoster = simulator.EventPoster(self.display)
        
    def clickOnCenter(self, row, col):
        bounds = self.widget.getBoundsByPosition(col, row)
        x = util.getInt(bounds.x) + util.getInt(bounds.width) / 2
        y = util.getInt(bounds.y) + util.getInt(bounds.height) / 2
        displayLoc = simulator.runOnUIThread(self.display.map, self.widget, None, x, y)
        self.eventPoster.moveClickAndReturn(displayLoc.x, displayLoc.y)
        
        
class NatTableSelectEvent(simulator.TableSelectEvent):
    def getIndexer(self):
        return NatTableIndexer.getIndexer(self.widget.widget.widget)
    
    def connectRecord(self, method):
        simulator.runOnUIThread(self.widget.widget.widget.addLayerListener, BasicLayerListener(method, self, nattable.selection.event.CellSelectionEvent))
        
    def shouldRecord(self, event, *args):
        return event.getRowPosition() is not None and event.getColumnPosition() is not None
        
    def findCell(self, event):
        return event.getRowPosition(), event.getColumnPosition()
    
    def isTriggeringEvent(self, e):
        return e.type == swt.SWT.MouseDown and e.widget is self.widget.widget.widget
    
    def _generate(self, cell):
        self.widget.clickOnCenter(*cell)


WidgetMonitor.swtbotMap[nattable.NatTable] = (FakeSWTBotNatTable, [])

customEventTypes = [ (FakeSWTBotNatTable,   [ NatTableSelectEvent ]) ]
