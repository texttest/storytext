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
        invoker=  parent.getInvoker()
        if isinstance(invoker, swing.JMenu):
            result.append(invoker.getText())
            parent = invoker.getParent()
        else:
            parent = None

    return "|".join(reversed(result)) 

def getComponentTextElements(component):
    elements = []
    if isinstance(component, swing.JCheckBox):
        elements.append("[x]" if component.isSelected() else "[ ]")
    elif hasattr(component, "getText"):
        elements.append(component.getText())
    for child in component.getComponents():
        elements += getComponentTextElements(child)
    return elements    

def getComponentText(component, multiline=True):
    elements = getComponentTextElements(component)
    return "\n".join(elements) if multiline else elements[0]
 

def getJListText(jlist, index, **kw):
    value = jlist.getModel().getElementAt(index) or ""
    renderer = jlist.getCellRenderer()
    # Don't check isinstance, any subclasses might be doing all sorts of stuff
    if renderer.__class__ is swing.DefaultListCellRenderer:
        return value

    isSelected = jlist.isSelectedIndex(index)
    component = renderer.getListCellRendererComponent(jlist, value, index, isSelected, False)
    return getComponentText(component, **kw)

def getJTableHeaderText(table, columnIndex, **kw):
    column = table.getColumnModel().getColumn(columnIndex)
    renderer = column.getHeaderRenderer()
    headerValue = column.getHeaderValue()
    if renderer is None:
        return str(headerValue)
        
    component = renderer.getTableCellRendererComponent(table, headerValue, False, False, 0, columnIndex)
    return getComponentText(component, **kw)

# Designed to filter out buttons etc which are details of other widgets, such as calendars, scrollbars, tables etc
def hasComplexAncestors(widget):
    if any((swing.SwingUtilities.getAncestorOfClass(widgetClass, widget) is not None
            for widgetClass in [ swing.JTable, swing.JScrollBar ])):
        return True
    
    # If we're in a popup menu that's attached to something with complex ancestors, that's clearly even more complex :)
    popup = swing.SwingUtilities.getAncestorOfClass(swing.JPopupMenu, widget)
    return popup is not None and hasComplexAncestors(popup.getInvoker())

def belongsMenubar(menuItem):
    parent = menuItem.getParent()
    while parent is not None:
        if isinstance(parent, swing.JMenuBar):
            return True
        if hasattr(parent, "getInvoker") and parent.getInvoker() is not None:
            if isinstance(parent.getInvoker(), swing.JMenu):
                parent = parent.getInvoker().getParent()
            else:
                parent = parent.getInvoker()
        else:
            parent = None
    return False

def hasPopupMenu(widget):
    return any((isinstance(item, (swing.JPopupMenu)) for item in widget.getComponents()))
