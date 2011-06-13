from java.lang import Runnable
from javax import swing
import usecase.guishared

def runOnEventDispatchThread(method, *args):
    class EDTRunnable(Runnable):
        def run(self):
            method(*args)
    
    if swing.SwingUtilities.isEventDispatchThread():
        method(*args)
    else:
        swing.SwingUtilities.invokeAndWait(EDTRunnable())

def getTextLabel(widget):
    return usecase.guishared.getTextLabel(widget, "getComponents", swing.JLabel)
       
def getMenuPathString(widget):
    result = [ widget.getText() ]    
    parent = widget.getParent()
    while isinstance(parent, swing.JMenu) or isinstance(parent, swing.JPopupMenu):
        result.append(parent.getInvoker().getText())
        parent = parent.getInvoker().getParent()
    
    return "|".join(reversed(result)) 

def getJListText(jlist, index):
    value = jlist.getModel().getElementAt(index) or ""
    renderer = jlist.getCellRenderer()
    # Don't check isinstance, any subclasses might be doing all sorts of stuff
    if renderer.__class__ is swing.DefaultListCellRenderer:
        return value

    isSelected = jlist.isSelectedIndex(index)
    component = renderer.getListCellRendererComponent(jlist, value, index, isSelected, False)
    return component.getText()

# Designed to filter out buttons etc which are details of other widgets, such as calendars, scrollbars, tables etc
def hasComplexAncestors(widget):
    return any((swing.SwingUtilities.getAncestorOfClass(widgetClass, widget) is not None
                for widgetClass in [ swing.JTable, swing.JScrollBar ]))
