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


