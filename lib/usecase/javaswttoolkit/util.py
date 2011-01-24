
""" SWT utilities """
from org.eclipse import swt

def checkInstance(widget, widgetClass):
    # Classloader problems with the swt.custom module mean isinstance doesn't work from RCP applications
    return isinstance(widget, widgetClass) or widget.__class__.__name__ == widgetClass.__name__


def getTextLabel(widget):
    """ Text widgets often are preceeded by a label, use this as their text, if it exists """
    parent = widget.getParent()
    if isinstance(parent, swt.widgets.Composite):
        children = parent.getChildren()
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

# For some reason StackLayout does not affect visible properties, so things that are hidden get marked as visible
# Workaround these things
def getTopControl(widget):
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
