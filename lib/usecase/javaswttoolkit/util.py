
""" SWT utilities """
from org.eclipse import swt
from java.text import SimpleDateFormat

def checkInstance(widget, widgetClass):
    # Classloader problems with the swt.custom module mean isinstance doesn't work from RCP applications
    return isinstance(widget, widgetClass) or widget.__class__.__name__ == widgetClass.__name__


def getTextLabel(widget):
    """ Text widgets often are preceeded by a label, use this as their text, if it exists """
    parent = widget.getParent()
    if parent:
        children = parent.getChildren()
        if len(children) == 1:
            return getTextLabel(parent)
    
        textPos = children.index(widget)
        while textPos > 0:
            prevWidget = children[textPos -1]
            if isinstance(prevWidget, swt.widgets.Label):
                text = prevWidget.getText()
                if text:
                    return text
                else:
                    textPos -= 1
            else:
                break
    return ""

def getDateFormat(dateType):
    if dateType == swt.SWT.TIME:
        # Default format is locale-dependent, no reason to make tests fail in different locales
        return SimpleDateFormat("kk:mm:ss")
    else:
        # Seems to be default format for swt.SWT.DATE, should be locale-independent
        return SimpleDateFormat("M/d/yyyy") 

# For some reason StackLayout does not affect visible properties, so things that are hidden get marked as visible
# Workaround these things
def getTopControl(widget):
    if hasattr(widget, "getLayout"):
        layout = widget.getLayout()
        if hasattr(layout, "topControl"):
            return layout.topControl

def isVisible(widget):
    if not hasattr(widget, "getVisible"):
        return True
    if not widget.getVisible():
        return False

    parent = widget.getParent()
    if not parent:
        return True
    topControl = getTopControl(parent)
    if topControl and topControl is not widget:
        return False
    else:
        return isVisible(parent)

# Picks up all initial show and paint events, used in both simulator and describer
class MonitorListener(swt.widgets.Listener):
    callbacks = []
    def __init__(self, bot, matcher):
        self.bot = bot
        self.matcher = matcher
        self.widgetsShown = set()

    @classmethod
    def addCallback(cls, callback):
        if callback not in cls.callbacks:
            cls.callbacks.append(callback)

    def addToCache(self, widgets):
        self.widgetsShown.update(widgets)
        
    def handleEvent(self, e):
        seenBefore = e.widget in self.widgetsShown
        if seenBefore and not isinstance(e.widget, swt.widgets.Canvas):
            return

        if e.type == swt.SWT.Show:
            self.bot.getFinder().setShouldFindInvisibleControls(True)
        widgets = self.findDescendants(e.widget)
        if e.type == swt.SWT.Show:
            self.bot.getFinder().setShouldFindInvisibleControls(False)

        self.addToCache(widgets)
        for callback in self.callbacks:
            callback(e.widget, widgets, e.type, seenBefore)

    def recordableEvent(self, e):
        # Called from a filter - basic point is to be a failsafe against
        # unexpected things requiring recording immanently.
        if e.widget not in self.widgetsShown:
            self.widgetsShown.add(e.widget)
            for callback in self.callbacks:
                callback(e.widget, [ e.widget ], e.type, False)

    def findDescendants(self, widget):
        return self.bot.widgets(self.matcher, widget)

