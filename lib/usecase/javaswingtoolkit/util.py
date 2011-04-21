from java.lang import Runnable, InterruptedException
from java.lang.reflect import InvocationTargetException
from javax import swing

def runOnEventDispatchThread(method, *args):
    class EDTRunnable(Runnable):
        def run(self):
            method(*args)
    
    if(swing.SwingUtilities.isEventDispatchThread()):
        method(*args)
    else:
        try:
            swing.SwingUtilities.invokeAndWait(EDTRunnable())
        except InterruptedException, e:
            print "EXCEPTION", e
        except InvocationTargetException, e:
            print "EXCEPTION", e

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


