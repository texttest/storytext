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
    result = []
    parent = widget.getParent()
    result.append(widget.getText())    
    while isinstance(parent, swing.JMenu) or isinstance(parent, swing.JPopupMenu):
        result.append('|') 
        result.append(parent.getInvoker().getText())
        parent = parent.getInvoker().getParent()
    
    result.reverse()    
    return "".join(result) 


