from java.lang import Runnable
from javax import swing

def runOnEventDispatchThread(method, *args):
    class EDTRunnable(Runnable):
        def run(self):
            method(*args)
    
    if swing.SwingUtilities.isEventDispatchThread():
        method(*args)
    else:
        swing.SwingUtilities.invokeAndWait(EDTRunnable())
       
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
    if renderer.__class__ is swing.DefaultListCellRenderer:
        # Don't check isinstance, any subclasses might be doing all sorts of stuff
        return value

    isSelected = jlist.isSelectedIndex(index)
    component = renderer.getListCellRendererComponent(jlist, value, index, isSelected, False)
    return component.getText()
