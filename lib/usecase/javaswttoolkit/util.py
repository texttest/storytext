
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
        if textPos > 0:
            prevWidget = children[textPos -1]
            if isinstance(prevWidget, swt.widgets.Label):
                return prevWidget.getText()
    return ""
