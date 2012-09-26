
""" SWT utilities """
from org.eclipse import swt
from java.text import SimpleDateFormat
import storytext.guishared

def getRealUrl(browser):
    url = browser.getUrl()
    return url if url != "about:blank" else ""

class TextLabelFinder(storytext.guishared.TextLabelFinder):
    def getLabelClass(self):
        return swt.widgets.Label, swt.custom.CLabel

    def getChildren(self, widget):
        return widget.getChildren()
    
    def getEarliestRelevantIndex(self, widgetPos, children, parent):
        if not isinstance(parent.getLayout(), swt.layout.GridLayout):
            return 0
        
        numColumns = parent.getLayout().numColumns
        if numColumns == 1: # If there's only one column, don't worry about it...
            return 0
        
        currIndex = 0
        rows = {}
        for ix, child in enumerate(children):
            span = min(child.getLayoutData().horizontalSpan, numColumns)
            row = currIndex / numColumns
            rows.setdefault(row, []).append(ix)
            if ix == widgetPos:
                return rows[row][0]
            else:
                currIndex += span

ignoreLabels = []
def getTextLabel(widget):
    return TextLabelFinder(widget, ignoreLabels).find()

def getInt(intOrMethod):
    return intOrMethod if isinstance(intOrMethod, int) else intOrMethod()

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

